const API_REFRESH_MS = 10000;
const prefs = { cap: "empty", noise: "quiet", temp: "comfortable" };

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

let currentUser = null;
let spaces = [];
let refreshTimer = null;
const favourites = new Set();
const pinnedToRecommended = new Set();

function escapeHtml(str) {
  return String(str).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `Request failed (${response.status})`);
  return data;
}

function showAuth(message = "") {
  $("#authView").hidden = false;
  $("#appView").hidden = true;
  $("#authMessage").textContent = message;
  currentUser = null;
  if (refreshTimer) clearInterval(refreshTimer);
}

function showApp(user) {
  currentUser = user;
  $("#authView").hidden = true;
  $("#appView").hidden = false;
  const initials = `${user.first_name?.[0] || ""}${user.last_name?.[0] || ""}`.toUpperCase() || "ST";
  $("#avatar").textContent = initials;
  $("#userName").textContent = `${user.first_name} ${user.last_name}`;
  $("#userRole").textContent = `${user.course} • ${user.student_id}`;
  loadLiveData({ silent: true });
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => loadLiveData({ silent: true }), API_REFRESH_MS);
}

async function checkSession() {
  try {
    const data = await api("/api/session");
    if (data.authenticated) showApp(data.user);
    else showAuth();
  } catch (err) {
    showAuth(err.message);
  }
}

function setConnectionState(text, tone = "neutral") {
  const el = $("#connectionState");
  if (!el) return;
  el.textContent = text;
  el.className = `connection-state ${tone}`;
}

async function loadLiveData({ silent = false } = {}) {
  if (!currentUser) return;
  try {
    setConnectionState("Loading live data from Flask backend → ThingsBoard...", "neutral");
    const data = await api("/api/spaces");
    spaces = data.spaces || [];
    setConnectionState(`Connected • ${spaces.length} live space(s) • updated ${new Date().toLocaleTimeString()}`, "good");
    render();
    if (!silent) toast("Live data loaded", "The dashboard has refreshed from ThingsBoard.");
  } catch (err) {
    spaces = [];
    setConnectionState(`Backend/ThingsBoard error: ${err.message}`, "bad");
    render();
    if (!silent) toast("Connection error", err.message);
  }
}

function occupancyRatio(s) { return s.capacity <= 0 ? 1 : s.occupied / s.capacity; }
function pct(n) { return Math.round(n); }
function capClass(r) { if (r <= 0.10) return "empty"; if (r < 0.30) return "quiet"; if (r < 0.70) return "moderate"; if (r < 0.90) return "busy"; return "full"; }
function noiseClass(db) { if (db < 42) return "quiet"; if (db < 55) return "moderate"; return "loud"; }
function tempClass(c) { if (c < 19) return "cold"; if (c < 24) return "comfortable"; if (c < 27) return "warm"; return "hot"; }
function dotClassFor(kind, value) { if (kind === "cap") return (value === "empty" || value === "quiet") ? "good" : (value === "moderate" ? "warn" : "bad"); if (kind === "noise") return value === "quiet" ? "good" : (value === "moderate" ? "warn" : "bad"); if (kind === "temp") return value === "comfortable" ? "good" : (value === "warm" ? "warn" : "bad"); if (kind === "cam") return value ? "good" : "bad"; return "good"; }
function capLabel(c) { return String(c).charAt(0).toUpperCase() + String(c).slice(1); }

function matchScore(s) {
  const r = occupancyRatio(s);
  const capC = capClass(r);
  const noiseC = noiseClass(s.noiseDb);
  const tempC = tempClass(s.tempC);
  const cameraPenalty = s.camera?.online ? 0 : -0.25;
  return (1 - r) * 3.0 + (capC === prefs.cap ? 1.4 : 0) + (noiseC === prefs.noise ? 1.1 : 0) + (tempC === prefs.temp ? 0.9 : 0) + cameraPenalty;
}

function renderSetupCard() {
  const el = document.createElement("div");
  el.className = "setup-card";
  el.innerHTML = `
    <h3>Backend connected, but ThingsBoard is not configured yet</h3>
    <p>Your login system is working through Flask session. Now add the real ThingsBoard details as environment variables before running Flask.</p>
    <pre>export THINGSBOARD_HOST="https://your-school-thingsboard-url"
export THINGSBOARD_USERNAME="your_account"
export THINGSBOARD_PASSWORD="your_password"
export TB_DEVICE_ASSL="device_uuid_here"</pre>
    <p>Expected telemetry keys: <b>occupied</b>, <b>capacity</b>, <b>temperature</b>, <b>humidity</b>, <b>noiseDb</b>, <b>cameraOnline</b>, <b>cameraConfidence</b>.</p>`;
  return el;
}

function renderCard(s, { mode, index }) {
  const r = occupancyRatio(s);
  const capC = capClass(r);
  const noiseC = noiseClass(s.noiseDb);
  const tempC = tempClass(s.tempC);
  const score = matchScore(s);
  const freeSeats = Math.max(0, s.capacity - s.occupied);
  const camera = s.camera || { online: false, lastSeenSec: 999999, confidence: 0, model: "Unknown" };

  const el = document.createElement("div");
  el.className = "card ripple";
  el.dataset.open = s.id;
  el.style.opacity = "0";
  el.style.transform = "translateY(8px)";
  el.style.transition = "opacity .35s ease, transform .35s ease, box-shadow .18s ease, background .18s ease";
  el.style.transitionDelay = `${Math.min(index * 18, 120)}ms`;

  el.innerHTML = `
    <div class="card-main">
      <div class="title-row">
        <h3 class="space-title">${escapeHtml(s.name)}</h3>
        <div class="badge"><span class="dot"></span>Score ${score.toFixed(2)}</div>
      </div>
      <div class="addr">${escapeHtml(s.address)} • ${escapeHtml(s.postcode)}</div>
      <div class="badges">
        <span class="badge"><span class="dot ${dotClassFor("cap", capC)}"></span>Capacity: ${capLabel(capC)} (${s.occupied}/${s.capacity})</span>
        <span class="badge"><span class="dot ${dotClassFor("noise", noiseC)}"></span>Noise: ${capLabel(noiseC)} (${s.noiseDb} dB)</span>
        <span class="badge"><span class="dot ${dotClassFor("temp", tempC)}"></span>Temp: ${capLabel(tempC)} (${Number(s.tempC).toFixed(1)}°C)</span>
      </div>
    </div>
    <div class="side">
      <div class="metric">
        <div class="label"><span>Occupancy</span><span>${pct(r * 100)}%</span></div>
        <div class="value">${freeSeats} seats free</div>
        <div class="bar"><i style="width:${Math.min(100, Math.max(0, pct(r * 100)))}%"></i></div>
        <div class="cam">
          <div class="status"><span class="${camera.online ? "pulse" : "dot bad"}"></span>Device ${camera.online ? "Live" : "Stale"}</div>
          <div class="badge"><span class="dot ${dotClassFor("cam", camera.online)}"></span>${camera.lastSeenSec}s ago</div>
        </div>
      </div>
      <div class="actions" onclick="event.stopPropagation()">
        ${mode === "all" ? `<button class="icon-btn primary ripple" data-pin="${s.id}" title="Add to Recommended">+</button>` : `<button class="icon-btn ripple" data-unpin="${s.id}" title="Remove from Recommended">×</button>`}
        <button class="icon-btn ripple" data-fav="${s.id}" title="Toggle favourite">${favourites.has(s.id) ? "★" : "☆"}</button>
      </div>
    </div>`;

  requestAnimationFrame(() => { el.style.opacity = "1"; el.style.transform = "translateY(0)"; });
  return el;
}

function searchFilter(list) {
  const term = $("#q").value.trim().toLowerCase();
  if (!term) return list;
  return list.filter(s => `${s.name} ${s.address} ${s.postcode}`.toLowerCase().includes(term));
}

function sortAll(list) {
  const key = $("#sortBy").value;
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

function rankText(score){ if(score >= 4.2) return "Excellent"; if(score >= 3.4) return "Good"; if(score >= 2.8) return "OK"; return "Avoid"; }

function buildAlerts(s) {
  const alerts = [];
  const r = occupancyRatio(s);
  const camera = s.camera || {};
  if (!camera.online) alerts.push("Device telemetry is stale or cameraOnline is false.");
  if (r >= 0.90) alerts.push("Very crowded (≥ 90%). Consider another space.");
  if (r >= 0.75 && r < 0.90) alerts.push("Busy (75–90%). You may struggle to find seats.");
  if (s.tempC >= 27) alerts.push("Temperature high — may feel uncomfortable.");
  if (s.humidity >= 65) alerts.push("Humidity high — ventilation may be limited.");
  return alerts;
}

function openDrawer(space) {
  const camera = space.camera || { online: false, lastSeenSec: 999999, confidence: 0, model: "Unknown" };
  $("#drawerTitle").textContent = space.name;
  $("#drawerSub").textContent = `${space.address} • ${space.postcode}`;
  const r = occupancyRatio(space);
  const capC = capClass(r);
  const noiseC = noiseClass(space.noiseDb);
  const tempC = tempClass(space.tempC);
  const score = matchScore(space);
  const alerts = buildAlerts(space);

  $("#drawerBody").innerHTML = `
    <div class="kpi">
      <div class="box"><div class="label"><span>Smart score</span><span>Rank</span></div><div class="value">${score.toFixed(2)} • ${rankText(score)}</div></div>
      <div class="box"><div class="label"><span>Data freshness</span><span>ThingsBoard</span></div><div class="value">${camera.lastSeenSec}s ago</div></div>
      <div class="box"><div class="label"><span>Occupancy</span><span>${pct(r*100)}%</span></div><div class="value">${space.occupied}/${space.capacity} • ${capLabel(capC)}</div></div>
      <div class="box"><div class="label"><span>Device</span><span>Confidence</span></div><div class="value">${camera.online ? "Live" : "Stale"} • ${Math.round(camera.confidence*100)}%</div></div>
    </div>
    <div class="row">
      <h4>ThingsBoard telemetry</h4>
      <p><b>Device ID:</b> ${escapeHtml(space.deviceId || "")}
      <br/><b>Model/source:</b> ${escapeHtml(camera.model)}
      <br/><b>Occupied:</b> ${space.occupied}
      <br/><b>Capacity:</b> ${space.capacity}
      <br/><b>Noise:</b> ${space.noiseDb} dB • ${capLabel(noiseC)}
      <br/><b>Temperature:</b> ${Number(space.tempC).toFixed(1)}°C • ${capLabel(tempC)}
      <br/><b>Humidity:</b> ${space.humidity}%</p>
    </div>
    <div class="row"><h4>Alerts</h4><p>${alerts.length ? alerts.map(a => `• ${escapeHtml(a)}`).join("<br/>") : "No alerts. Conditions look good."}</p></div>
    <div class="row"><h4>Raw latest telemetry</h4><pre class="raw-json">${escapeHtml(JSON.stringify(space.rawTelemetry || {}, null, 2))}</pre></div>`;

  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#drawerBackdrop").hidden = false;
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#drawerBackdrop").hidden = true;
}

function toast(title, sub) {
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div class="t-title">${escapeHtml(title)}</div><div class="t-sub">${escapeHtml(sub)}</div>`;
  $("#toastRoot").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateY(6px)"; el.style.transition = "opacity .22s ease, transform .22s ease"; }, 2200);
  setTimeout(() => el.remove(), 2600);
}

function render() {
  const recommendedList = $("#recommendedList");
  const allList = $("#allList");
  recommendedList.innerHTML = "";
  allList.innerHTML = "";

  if (!spaces.length) {
    $("#allEmpty").hidden = true;
    $("#recommendedEmpty").hidden = true;
    allList.appendChild(renderSetupCard());
    recommendedList.appendChild(renderSetupCard());
    return;
  }

  const filtered = searchFilter(spaces);
  const allSorted = sortAll(filtered);
  $("#allEmpty").hidden = allSorted.length !== 0;
  allSorted.forEach((s, i) => allList.appendChild(renderCard(s, { mode: "all", index: i })));

  const rec = recommendedBase(filtered);
  $("#recommendedEmpty").hidden = rec.length !== 0;
  rec.forEach((s, i) => recommendedList.appendChild(renderCard(s, { mode: "rec", index: i })));
}

function bindAuthEvents() {
  $("#showLogin").addEventListener("click", () => {
    $("#showLogin").classList.add("active");
    $("#showRegister").classList.remove("active");
    $("#loginForm").hidden = false;
    $("#registerForm").hidden = true;
    $("#authMessage").textContent = "";
  });

  $("#showRegister").addEventListener("click", () => {
    $("#showRegister").classList.add("active");
    $("#showLogin").classList.remove("active");
    $("#loginForm").hidden = true;
    $("#registerForm").hidden = false;
    $("#authMessage").textContent = "";
  });

  $("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ email: $("#loginEmail").value, password: $("#loginPassword").value })
      });
      showApp(data.user);
    } catch (err) {
      $("#authMessage").textContent = err.message;
    }
  });

  $("#registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await api("/api/register", {
        method: "POST",
        body: JSON.stringify({
          firstName: $("#firstName").value,
          lastName: $("#lastName").value,
          studentId: $("#studentId").value,
          course: $("#course").value,
          email: $("#registerEmail").value,
          password: $("#registerPassword").value
        })
      });
      showApp(data.user);
    } catch (err) {
      $("#authMessage").textContent = err.message;
    }
  });

  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: JSON.stringify({}) });
    showAuth("Logged out successfully.");
  });
}

function bindDashboardEvents() {
  $$(".chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const pref = btn.dataset.pref;
      const value = btn.dataset.value;
      btn.closest(".chip-group").querySelectorAll(".chip").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      prefs[pref] = value;
      render();
    });
  });

  $("#q").addEventListener("input", render);
  $("#clearSearch").addEventListener("click", () => { $("#q").value = ""; render(); });
  $("#sortBy").addEventListener("change", render);
  $("#refresh").addEventListener("click", () => loadLiveData());
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawerBackdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  document.addEventListener("click", (e) => {
    const pinId = e.target?.dataset?.pin;
    const unpinId = e.target?.dataset?.unpin;
    const favId = e.target?.dataset?.fav;
    const openId = e.target?.closest?.("[data-open]")?.dataset?.open;

    if (pinId) { pinnedToRecommended.add(pinId); toast("Added to Recommended", "Pinned this space to your personalised list."); render(); return; }
    if (unpinId) { pinnedToRecommended.delete(unpinId); toast("Removed from Recommended", "Unpinned this space."); render(); return; }
    if (favId) { favourites.has(favId) ? favourites.delete(favId) : favourites.add(favId); render(); return; }
    if (openId && !e.target.closest("[data-pin],[data-unpin],[data-fav],button")) {
      const space = spaces.find(s => s.id === openId);
      if (space) openDrawer(space);
    }
  });
}

bindAuthEvents();
bindDashboardEvents();
checkSession();
