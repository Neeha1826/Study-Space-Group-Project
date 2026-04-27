const SPACES_DEMO = [
  {
    id: "assl",
    name: "Arts and Social Studies Library",
    address: "Colum Dr, Cardiff",
    postcode: "CF10 3LB",
    capacity: 750,
    occupied: 400,
    noiseDb: 38,
    tempC: 24.8,
    humidity: 56,
    camera: { online: true, model: "EdgeCam v2", confidence: 0.91, lastSeenSec: 6 },
    history: [40, 42, 44, 49, 52, 54, 50, 48, 53, 55, 54, 53]
  },
  {
    id: "abacws",
    name: "Abacws",
    address: "Senghennydd Rd, Cardiff",
    postcode: "CF24 4AG",
    capacity: 520,
    occupied: 460,
    noiseDb: 52,
    tempC: 22.1,
    humidity: 48,
    camera: { online: true, model: "EdgeCam v2", confidence: 0.88, lastSeenSec: 10 },
    history: [65, 66, 70, 74, 78, 80, 83, 85, 86, 88, 87, 89]
  },
  {
    id: "mainlib",
    name: "Main Library",
    address: "The Parade, Cardiff",
    postcode: "CF10 3AY",
    capacity: 1100,
    occupied: 980,
    noiseDb: 61,
    tempC: 25.7,
    humidity: 62,
    camera: { online: true, model: "EdgeCam v1", confidence: 0.84, lastSeenSec: 4 },
    history: [78, 80, 82, 85, 88, 90, 91, 92, 91, 93, 94, 95]
  },
  {
    id: "talyb",
    name: "Talybont Study Hub",
    address: "Talybont North, Cardiff",
    postcode: "CF14 3AX",
    capacity: 380,
    occupied: 140,
    noiseDb: 34,
    tempC: 21.6,
    humidity: 45,
    camera: { online: false, model: "EdgeCam v2", confidence: 0.0, lastSeenSec: 420 },
    history: [18, 20, 22, 25, 28, 26, 24, 23, 21, 20, 22, 24]
  }
];

function cloneSpaces(arr) {
  return JSON.parse(JSON.stringify(arr));
}

let spaces = cloneSpaces(SPACES_DEMO);
let dataSource = "client-demo";
let tbWarning = null;

function updateDataSourcePill() {
  const el = document.getElementById("dataSourcePill");
  if (!el) return;
  el.className = "source-pill";
  let label = "Demo (no API)";
  if (dataSource === "thingsboard") {
    el.classList.add("tb");
    label = "ThingsBoard";
  } else if (dataSource === "client-demo") {
    el.classList.add("demo");
    label = "Demo (Simulated)";
  } else {
    el.classList.add("offline");
  }
  el.textContent = label;
  el.title = tbWarning ? tbWarning : "Live data via ThingsBoard.";
}

const TB_BASE_URL = "https://eu.thingsboard.cloud";
const TB_DEVICE_ID = "f947bef0-4194-11f1-9a3c-1fb54f58cf69";
const TB_USERNAME = "viewer@cardiff.ac.uk";
const TB_PASSWORD = "test123";

let tbJwtToken = null;

async function getTbToken() {
  if (tbJwtToken) return tbJwtToken;

  const res = await fetch(`${TB_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: TB_USERNAME, password: TB_PASSWORD })
  });

  if (!res.ok) throw new Error("TB Auth Failed");
  const data = await res.json();
  tbJwtToken = data.token;
  return tbJwtToken;
}

async function loadRemoteSpaces() {
  try {
    const token = await getTbToken();

    const keys = "temperature,humidity,occupancy,noiseLevel";
    const res = await fetch(`${TB_BASE_URL}/api/plugins/telemetry/DEVICE/${TB_DEVICE_ID}/values/timeseries?keys=${keys}`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'X-Authorization': `Bearer ${token}`
      }
    });

    if (res.status === 401) {
      tbJwtToken = null;
      throw new Error("Token expired");
    }
    if (!res.ok) throw new Error("Failed to fetch telemetry");

    const tbData = await res.json();

    const liveTemp = tbData.temperature ? parseFloat(tbData.temperature[0].value) : null;
    const liveHum = tbData.humidity ? parseFloat(tbData.humidity[0].value) : null;
    const liveOcc = tbData.occupancy ? parseInt(tbData.occupancy[0].value) : null;
    const liveNoise = tbData.noiseLevel ? parseInt(tbData.noiseLevel[0].value) : null;

    const targetSpace = spaces.find(s => s.id === "assl");

    if (targetSpace) {
      if (liveTemp !== null) targetSpace.tempC = liveTemp;
      if (liveHum !== null) targetSpace.humidity = liveHum;
      if (liveOcc !== null) targetSpace.occupied = liveOcc;
      if (liveNoise !== null) targetSpace.noiseDb = liveNoise;

      targetSpace.camera.online = true;
      targetSpace.camera.lastSeenSec = 0;
      targetSpace.camera.confidence = 0.95;

      const ratio = targetSpace.occupied / targetSpace.capacity;
      targetSpace.history.shift();
      targetSpace.history.push(Math.round(ratio * 100));
    }

    dataSource = "thingsboard";
    tbWarning = null;
    updateDataSourcePill();

  } catch (e) {
    console.error("ThingsBoard Error:", e);
    dataSource = "client-demo";
    tbWarning = "Live connection lost. Using simulated data.";
    updateDataSourcePill();
  }
}

// ==========================================
// UI & Logic
// ==========================================
const prefs = { cap: "empty", noise: "quiet", temp: "comfortable" };

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const recommendedList = $("#recommendedList");
const allList = $("#allList");
const recommendedEmpty = $("#recommendedEmpty");
const allEmpty = $("#allEmpty");
const q = $("#q");
const sortBy = $("#sortBy");

const drawer = $("#drawer");
const drawerBackdrop = $("#drawerBackdrop");
const drawerClose = $("#drawerClose");
const drawerTitle = $("#drawerTitle");
const drawerSub = $("#drawerSub");
const drawerBody = $("#drawerBody");

const toastRoot = $("#toastRoot");

const favourites = new Set();
const pinnedToRecommended = new Set();

function occupancyRatio(s) { return s.capacity <= 0 ? 1 : s.occupied / s.capacity; }
function pct(n) { return Math.round(n); }

function capClass(r) {
  if (r <= 0.10) return "empty";
  if (r < 0.30) return "quiet";
  if (r < 0.70) return "moderate";
  if (r < 0.90) return "busy";
  return "full";
}
function noiseClass(db) {
  if (db < 42) return "quiet";
  if (db < 55) return "moderate";
  return "loud";
}
function tempClass(c) {
  if (c < 19) return "cold";
  if (c < 24) return "comfortable";
  if (c < 27) return "warm";
  return "hot";
}
function dotClassFor(kind, value) {
  if (kind === "cap") return (value === "empty" || value === "quiet") ? "good" : (value === "moderate" ? "warn" : "bad");
  if (kind === "noise") return value === "quiet" ? "good" : (value === "moderate" ? "warn" : "bad");
  if (kind === "temp") return value === "comfortable" ? "good" : (value === "warm" ? "warn" : "bad");
  if (kind === "cam") return value ? "good" : "bad";
  return "good";
}
function capLabel(c) {
  return c.charAt(0).toUpperCase() + c.slice(1);
}

function matchScore(s) {
  const r = occupancyRatio(s);
  const capC = capClass(r);
  const noiseC = noiseClass(s.noiseDb);
  const tempC = tempClass(s.tempC);

  const capMatch = capC === prefs.cap ? 1 : 0;
  const noiseMatch = noiseC === prefs.noise ? 1 : 0;
  const tempMatch = tempC === prefs.temp ? 1 : 0;

  const freeSeatsQuality = 1 - r;
  const cameraPenalty = s.camera.online ? 0 : -0.25;

  return (freeSeatsQuality * 3.0 + capMatch * 1.4 + noiseMatch * 1.1 + tempMatch * 0.9 + cameraPenalty);
}

function escapeHtml(str) {
  return String(str).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function renderCard(s, { mode, index }) {
  const r = occupancyRatio(s);
  const capC = capClass(r);
  const noiseC = noiseClass(s.noiseDb);
  const tempC = tempClass(s.tempC);
  const score = matchScore(s);

  const el = document.createElement("div");
  el.className = "card ripple";
  el.dataset.open = s.id;

  el.style.opacity = "0";
  el.style.transform = "translateY(8px)";
  el.style.transition = "opacity .35s ease, transform .35s ease, box-shadow .18s ease, background .18s ease";
  el.style.transitionDelay = `${Math.min(index * 18, 120)}ms`;

  const freeSeats = Math.max(0, s.capacity - s.occupied);

  el.innerHTML = `
    <div class="card-main">
      <div class="title-row">
        <h3 class="space-title">${escapeHtml(s.name)}</h3>
        <div class="badge" title="Smart score based on preference + live data">
          <span class="dot"></span>Score ${score.toFixed(2)}
        </div>
      </div>
      <div class="addr">${escapeHtml(s.address)} • ${escapeHtml(s.postcode)}</div>
      <div class="badges">
        <span class="badge" title="${pct(r*100)}% occupancy">
          <span class="dot ${dotClassFor("cap", capC)}"></span>Capacity: ${capLabel(capC)} (${s.occupied}/${s.capacity})
        </span>
        <span class="badge" title="${s.noiseDb} dB">
          <span class="dot ${dotClassFor("noise", noiseC)}"></span>Noise: ${capLabel(noiseC)}
        </span>
        <span class="badge" title="${s.tempC.toFixed(1)}°C">
          <span class="dot ${dotClassFor("temp", tempC)}"></span>Temp: ${capLabel(tempC)}
        </span>
      </div>
    </div>
    <div class="side">
      <div class="metric">
        <div class="label"><span>Occupancy</span><span>${pct(r*100)}%</span></div>
        <div class="value">${freeSeats} seats free</div>
        <div class="bar"><i style="width:${Math.min(100, Math.max(0, pct(r*100)))}%"></i></div>
        <div class="cam">
          <div class="status" title="Data source: camera + sensors">
            <span class="${s.camera.online ? "pulse" : "dot bad"}"></span>Camera ${s.camera.online ? "Online" : "Offline"}
          </div>
          <div class="badge" title="Last update from camera/sensor feed">
            <span class="dot ${dotClassFor("cam", s.camera.online)}"></span>${s.camera.online ? `${s.camera.lastSeenSec}s ago` : `stale`}
          </div>
        </div>
      </div>
      <div class="actions" onclick="event.stopPropagation()">
        ${ mode === "all" ? `<button class="icon-btn primary ripple" data-pin="${s.id}" title="Add to Recommended">+</button>` : `<button class="icon-btn ripple" data-unpin="${s.id}" title="Remove from Recommended">×</button>` }
        <button class="icon-btn ripple" data-fav="${s.id}" title="Toggle favourite">${favourites.has(s.id) ? "★" : "☆"}</button>
      </div>
    </div>
  `;

  requestAnimationFrame(() => { el.style.opacity = "1"; el.style.transform = "translateY(0)"; });
  return el;
}

function searchFilter(list) {
  const term = q.value.trim().toLowerCase();
  if (!term) return list;
  return list.filter(s => `${s.name} ${s.address} ${s.postcode}`.toLowerCase().includes(term));
}

function sortAll(list) {
  const key = sortBy.value;
  const copy = [...list];
  if (key === "score") return copy.sort((a,b) => matchScore(b) - matchScore(a));
  if (key === "occupancy") return copy.sort((a,b) => occupancyRatio(a) - occupancyRatio(b));
  if (key === "temp") return copy.sort((a,b) => a.tempC - b.tempC);
  if (key === "hum") return copy.sort((a,b) => a.humidity - b.humidity);
  if (key === "noise") return copy.sort((a,b) => a.noiseDb - b.noiseDb);
  return copy;
}

function recommendedBase(list) {
  const scored = [...list].sort((a,b) => matchScore(b) - matchScore(a));
  const top = scored.slice(0, 3);
  const pinned = list.filter(s => pinnedToRecommended.has(s.id) && !top.some(t => t.id === s.id));
  return [...top, ...pinned];
}

function openDrawer(space) {
  drawerTitle.textContent = space.name;
  drawerSub.textContent = `${space.address} • ${space.postcode}`;

  const r = occupancyRatio(space);
  const capC = capClass(r);
  const noiseC = noiseClass(space.noiseDb);
  const tempC = tempClass(space.tempC);
  const score = matchScore(space);
  const alerts = buildAlerts(space);

  drawerBody.innerHTML = `
    <div class="kpi">
      <div class="box"><div class="label"><span>Smart score</span><span>Rank</span></div><div class="value">${score.toFixed(2)} • ${rankText(score)}</div></div>
      <div class="box"><div class="label"><span>Data freshness</span><span>Source</span></div><div class="value">${space.camera.online ? `${space.camera.lastSeenSec}s ago` : `Stale`} • Camera</div></div>
      <div class="box"><div class="label"><span>Occupancy</span><span>${pct(r*100)}%</span></div><div class="value">${space.occupied}/${space.capacity} • ${capLabel(capC)}</div></div>
      <div class="box"><div class="label"><span>Camera</span><span>Confidence</span></div><div class="value">${space.camera.online ? "Online" : "Offline"} • ${Math.round(space.camera.confidence*100)}%</div></div>
    </div>
    <div class="row">
      <h4>Camera detection</h4>
      <p>Model: <b>${escapeHtml(space.camera.model)}</b><br/>People count is estimated by edge vision + smoothing. Confidence reflects detection quality.</p>
      <hr class="sep"/>
      <p>
        <b>Last update:</b> ${space.camera.online ? `${space.camera.lastSeenSec}s ago` : "offline"}<br/>
        <b>Estimated occupancy:</b> ${space.occupied} people<br/>
        <b>Noise (raw):</b> ${space.noiseDb} dB • ${capLabel(noiseC)}<br/>
        <b>Temp (raw):</b> ${space.tempC.toFixed(1)}°C • ${capLabel(tempC)}<br/>
        <b>Humidity (raw):</b> ${space.humidity}%<br/>
      </p>
    </div>
    <div class="row">
      <h4>Occupancy trend (last 12 samples)</h4>
      <p>Quick glance trend line for crowding pattern.</p>
      <canvas id="spark" width="360" height="90" style="width:100%; border-radius:14px; background: rgba(15,23,42,.02); border:1px solid rgba(15,23,42,.08)"></canvas>
    </div>
    <div class="row">
      <h4>Alerts</h4>
      <p>${alerts.length ? alerts.map(a => `• ${escapeHtml(a)}`).join("<br/>") : "No alerts. Conditions look good."}</p>
    </div>
  `;

  drawSparkline($("#spark"), space.history);

  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  drawerBackdrop.hidden = false;
}

function closeDrawer() {
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  drawerBackdrop.hidden = true;
}

function rankText(score){
  if(score >= 4.2) return "Excellent";
  if(score >= 3.4) return "Good";
  if(score >= 2.8) return "OK";
  return "Avoid";
}

function buildAlerts(s) {
  const alerts = [];
  const r = occupancyRatio(s);
  if (!s.camera.online) alerts.push("Camera offline — occupancy may be stale.");
  if (r >= 0.90) alerts.push("Very crowded (≥ 90%). Consider another space.");
  if (r >= 0.75 && r < 0.90) alerts.push("Busy (75–90%). You may struggle to find seats.");
  if (s.tempC >= 27) alerts.push("Temperature high — may feel uncomfortable.");
  if (s.humidity >= 65) alerts.push("Humidity high — ventilation may be limited.");
  return alerts;
}

function drawSparkline(canvas, series) {
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const pad = 12, innerW = w - pad*2, innerH = h - pad*2;
  const min = Math.min(...series), max = Math.max(...series), span = Math.max(1, max - min);

  ctx.lineWidth = 1; ctx.strokeStyle = "rgba(15,23,42,.10)";
  ctx.beginPath(); ctx.moveTo(pad, h - pad); ctx.lineTo(w - pad, h - pad); ctx.stroke();

  ctx.lineWidth = 2; ctx.strokeStyle = "rgba(37,99,235,.80)"; ctx.beginPath();
  series.forEach((v, i) => {
    const x = pad + (i/(series.length-1)) * innerW, y = pad + (1 - (v - min)/span) * innerH;
    if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();

  ctx.globalAlpha = 0.12; ctx.fillStyle = "rgba(37,99,235,.55)";
  ctx.lineTo(w - pad, h - pad); ctx.lineTo(pad, h - pad); ctx.closePath(); ctx.fill();

  const last = series[series.length - 1], lx = pad + innerW, ly = pad + (1 - (last - min)/span) * innerH;
  ctx.globalAlpha = 1; ctx.fillStyle = "rgba(22,163,74,.85)";
  ctx.beginPath(); ctx.arc(lx, ly, 4, 0, Math.PI*2); ctx.fill();
}

function toast(title, sub) {
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div class="t-title">${escapeHtml(title)}</div><div class="t-sub">${escapeHtml(sub)}</div>`;
  toastRoot.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateY(6px)"; el.style.transition = "opacity .22s ease, transform .22s ease"; }, 2200);
  setTimeout(() => el.remove(), 2600);
}

function render() {
  const filtered = searchFilter(spaces);
  const allSorted = sortAll(filtered);
  allList.innerHTML = "";
  allEmpty.hidden = allSorted.length !== 0;
  allSorted.forEach((s, i) => allList.appendChild(renderCard(s, { mode: "all", index: i })));

  const rec = recommendedBase(filtered);
  recommendedList.innerHTML = "";
  recommendedEmpty.hidden = rec.length !== 0;
  rec.forEach((s, i) => recommendedList.appendChild(renderCard(s, { mode: "rec", index: i })));
}

function simulateUpdate() {
  spaces.forEach(s => {
    // PROTECT LIVE DATA: If this is ASSL and TB is connected, skip the simulation
    if (s.id === "assl" && dataSource === "thingsboard") return;

    if (Math.random() < 0.04) s.camera.online = !s.camera.online;
    s.camera.lastSeenSec = s.camera.online ? randInt(2, 14) : randInt(180, 900);
    s.camera.confidence = s.camera.online ? clampFloat(s.camera.confidence + randFloat(-0.05, 0.05), 0.75, 0.97) : 0;

    const delta = s.camera.online ? randInt(-40, 40) : randInt(-10, 10);
    s.occupied = clampInt(s.occupied + delta, 0, s.capacity);

    s.tempC = clampFloat(s.tempC + randFloat(-0.5, 0.5), 18, 29);
    s.humidity = clampInt(s.humidity + randInt(-3, 3), 30, 75);
    s.noiseDb = clampInt(s.noiseDb + randInt(-3, 3), 28, 70);

    const r = occupancyRatio(s);
    s.history = [...s.history.slice(1), clampInt(Math.round(r * 100), 0, 100)];
  });
}

function bindEvents() {
  $$(".chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const pref = btn.dataset.pref, value = btn.dataset.value;
      const group = btn.closest(".chip-group");
      group.querySelectorAll(".chip").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      prefs[pref] = value;
      render();
    });
  });

  q.addEventListener("input", render);
  $("#clearSearch").addEventListener("click", () => { q.value = ""; render(); });
  sortBy.addEventListener("change", render);

  $("#refresh").addEventListener("click", async () => {
    await loadRemoteSpaces();
    simulateUpdate();
    render();
    toast("Live update", "Refreshed ThingsBoard & simulated feeds.");
  });

  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawerBackdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  document.addEventListener("click", (e) => {
    const pinId = e.target?.dataset?.pin, unpinId = e.target?.dataset?.unpin, favId = e.target?.dataset?.fav;
    const openId = e.target?.closest?.("[data-open]")?.dataset?.open;

    if (pinId) { pinnedToRecommended.add(pinId); toast("Added to Recommended", "Pinned space."); render(); return; }
    if (unpinId) { pinnedToRecommended.delete(unpinId); toast("Removed from Recommended", "Unpinned space."); render(); return; }
    if (favId) {
      if (favourites.has(favId)) { favourites.delete(favId); toast("Unfavourited", "Removed from favourites."); }
      else { favourites.add(favId); toast("Favourited", "Added to favourites."); }
      render(); return;
    }
    if (openId && !e.target.closest("[data-pin],[data-unpin],[data-fav],button")) {
      const space = spaces.find(s => s.id === openId);
      if (space) openDrawer(space);
    }
  });

  document.addEventListener("click", (e) => {
    const target = e.target.closest(".btn, .icon-btn, .chip, .card, select");
    if (!target) return;
    target.classList.add("ripple");
    const r = document.createElement("span"); r.className = "r";
    const rect = target.getBoundingClientRect(), size = Math.max(rect.width, rect.height);
    r.style.width = r.style.height = `${size}px`; r.style.left = `${e.clientX - rect.left - size/2}px`; r.style.top  = `${e.clientY - rect.top  - size/2}px`;
    target.appendChild(r);
    setTimeout(() => r.remove(), 600);
  }, true);
}

function randInt(a,b){ return Math.floor(Math.random()*(b-a+1))+a; }
function randFloat(a,b){ return Math.random()*(b-a)+a; }
function clampInt(x,min,max){ return Math.min(max, Math.max(min, Math.round(x))); }
function clampFloat(x,min,max){ return Math.min(max, Math.max(min, x)); }

// Initialize
bindEvents();

// Initial load
(async function init() {
  await loadRemoteSpaces();
  render();
})();

// Main Hybrid Loop
setInterval(async () => {
  await loadRemoteSpaces();
  simulateUpdate();
  render();

  if (drawer.classList.contains("open")) {
    const name = drawerTitle.textContent;
    const space = spaces.find(s => s.name === name);
    if (space) openDrawer(space);
  }
}, 12000);
