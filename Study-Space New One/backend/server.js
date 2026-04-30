import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function loadEnvFromFile() {
  const envPath = path.join(__dirname, ".env");
  if (!fs.existsSync(envPath)) return;

  const content = fs.readFileSync(envPath, "utf-8");
  content.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) return;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (key && process.env[key] == null) {
      process.env[key] = value;
    }
  });
}

loadEnvFromFile();

const PORT = Number(process.env.PORT || 3000);
const TB_BASE_URL = process.env.TB_BASE_URL;
const TB_DEVICE_ID = process.env.TB_DEVICE_ID;
const TB_DEVICE_ID_2 = process.env.TB_DEVICE_ID_2;
const TB_DEVICE_IDS = [TB_DEVICE_ID, TB_DEVICE_ID_2].filter(Boolean);
const TB_USERNAME = process.env.TB_USERNAME;
const TB_PASSWORD = process.env.TB_PASSWORD;

let tbJwtToken = null;

function hasTbConfig() {
  return Boolean(TB_BASE_URL && TB_DEVICE_IDS.length && TB_USERNAME && TB_PASSWORD);
}

async function getTbToken() {
  if (!hasTbConfig()) {
    throw new Error("Missing ThingsBoard env vars.");
  }
  if (tbJwtToken) return tbJwtToken;

  const res = await fetch(`${TB_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: TB_USERNAME,
      password: TB_PASSWORD
    })
  });

  if (!res.ok) {
    throw new Error(`TB auth failed (${res.status})`);
  }

  const data = await res.json();
  tbJwtToken = data.token;
  return tbJwtToken;
}

async function fetchTelemetryWithToken(token, deviceId) {
  const keys = "temperature,humidity,occupancy,noiseLevel";
  const url = `${TB_BASE_URL}/api/plugins/telemetry/DEVICE/${deviceId}/values/timeseries?keys=${keys}`;

  return fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
      "X-Authorization": `Bearer ${token}`
    }
  });
}

async function loadDeviceTelemetry() {
  const token = await getTbToken();
  const results = [];

  for (const deviceId of TB_DEVICE_IDS) {
    let res = await fetchTelemetryWithToken(token, deviceId);
    if (res.status === 401) {
      tbJwtToken = null;
      const newToken = await getTbToken();
      res = await fetchTelemetryWithToken(newToken, deviceId);
    }

    if (!res.ok) {
      throw new Error(`TB telemetry failed for device ${deviceId} (${res.status})`);
    }

    const tbData = await res.json();
    results.push({
      id: deviceId,
      temperature: tbData.temperature?.[0]?.value ?? null,
      humidity: tbData.humidity?.[0]?.value ?? null,
      occupancy: tbData.occupancy?.[0]?.value ?? null,
      noiseLevel: tbData.noiseLevel?.[0]?.value ?? null
    });
  }

  if (results.length === 1) {
    const { id, ...data } = results[0];
    return data;
  }

  return { spaces: results };
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
  });
  res.end(JSON.stringify(payload));
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    });
    res.end();
    return;
  }

  if (req.method === "GET" && req.url === "/api/health") {
    sendJson(res, 200, {
    ok: true,
    service: "study-space-backend",
    tbConfigured: hasTbConfig()
  });
    return;
  }

  if (req.method === "GET" && req.url === "/api/tb/live") {
    try {
      const data = await loadDeviceTelemetry();
      sendJson(res, 200, {
      ok: true,
      source: "thingsboard",
      data
    });
      return;
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        source: "thingsboard",
        error: error.message
      });
      return;
    }
  }

  sendJson(res, 404, {
    ok: false,
    error: "Not found"
  });
});

server.listen(PORT, () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
