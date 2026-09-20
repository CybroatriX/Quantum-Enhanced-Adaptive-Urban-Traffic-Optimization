"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const publicDir = path.join(__dirname, "..", "public");

test("Real-Time Detection UI: tab and controls exist in index.html", () => {
  const html = fs.readFileSync(path.join(publicDir, "index.html"), "utf8");

  // Tab button and pane
  assert.ok(html.includes('id="tabRealtimeBtn"'), "tabRealtimeBtn must exist in tablist");
  assert.ok(html.includes('id="tabRealtime"'), "tabRealtime pane must exist");

  // Core controls
  assert.ok(html.includes('id="rtSourceSelect"'), "rtSourceSelect must exist");
  assert.ok(html.includes('id="rtIntersectionSelect"'), "rtIntersectionSelect must exist");
  assert.ok(html.includes('id="rtConfidenceSlider"'), "rtConfidenceSlider must exist");
  assert.ok(html.includes('id="rtInferenceFpsSelect"'), "rtInferenceFpsSelect must exist");
  assert.ok(html.includes('id="btnStartRealtime"'), "btnStartRealtime must exist");
  assert.ok(html.includes('id="btnStopRealtime"'), "btnStopRealtime must exist");

  // Live video viewport
  assert.ok(html.includes('id="rtLiveStreamImg"'), "rtLiveStreamImg must exist");
  assert.ok(html.includes('id="rtVideoViewport"'), "rtVideoViewport must exist");

  // Status badges
  assert.ok(html.includes('id="rtCamStatusText"'), "rtCamStatusText must exist");
  assert.ok(html.includes('id="rtYoloStatusText"'), "rtYoloStatusText must exist");
  assert.ok(html.includes('id="rtTrackingStatusText"'), "rtTrackingStatusText must exist");
  assert.ok(html.includes("SIGNAL CONTROL: DISABLED"), "Explicit disabled signal control notice must exist");

  // Metric displays
  assert.ok(html.includes('id="rtHeroVehicleCount"'), "rtHeroVehicleCount must exist");
  assert.ok(html.includes('id="rtHeroPedestrianCount"'), "rtHeroPedestrianCount must exist");
  assert.ok(html.includes('id="rtCountCar"'), "rtCountCar must exist");
  assert.ok(html.includes('id="rtCountMoto"'), "rtCountMoto must exist");
  assert.ok(html.includes('id="rtCountBus"'), "rtCountBus must exist");
  assert.ok(html.includes('id="rtCountTruck"'), "rtCountTruck must exist");
  assert.ok(html.includes('id="rtTotalTracked"'), "rtTotalTracked must exist");
  assert.ok(html.includes('id="rtConfidencePercent"'), "rtConfidencePercent must exist");

  // Approach regions
  assert.ok(html.includes('id="rtApprVehNorth"'), "rtApprVehNorth must exist");
  assert.ok(html.includes('id="rtApprPedNorth"'), "rtApprPedNorth must exist");
  assert.ok(html.includes("Directional pedestrian ROI not configured"), "Directional pedestrian ROI fallback notice must exist");
});

test("Real-Time Detection Logic: app.js contains live streaming and polling handlers", () => {
  const js = fs.readFileSync(path.join(publicDir, "app.js"), "utf8");

  assert.ok(js.includes("tabRealtimeBtn"), "app.js must register tabRealtimeBtn");
  assert.ok(js.includes("btnStartRealtime"), "app.js must handle btnStartRealtime");
  assert.ok(js.includes("btnStopRealtime"), "app.js must handle btnStopRealtime");
  assert.ok(js.includes("/api/perception/live/start"), "app.js must call live start endpoint");
  assert.ok(js.includes("/api/perception/live/stop"), "app.js must call live stop endpoint");
  assert.ok(js.includes("/api/perception/live/status"), "app.js must poll live status endpoint");
  assert.ok(js.includes("/api/perception/live/stream"), "app.js must bind live MJPEG stream");
});

test("Server Proxy: web/server.js proxies live perception stream and control routes", () => {
  const serverJs = fs.readFileSync(path.join(__dirname, "..", "server.js"), "utf8");

  assert.ok(serverJs.includes("/api/perception/live/stream"), "server.js must proxy live stream");
  assert.ok(serverJs.includes("/api/perception/live/frame"), "server.js must handle live frame endpoint");
  assert.ok(serverJs.includes("/api/perception/live/status"), "server.js must proxy live status");
  assert.ok(serverJs.includes("/api/perception/live/start"), "server.js must proxy live start");
  assert.ok(serverJs.includes("/api/perception/live/stop"), "server.js must proxy live stop");
  assert.ok(serverJs.includes("DISABLED"), "server.js must ensure signal control is disabled in fallback");
});
