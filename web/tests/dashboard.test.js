"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const path = require("node:path");

test("Phase L: Integrated Dashboard Server, Tabs, and API Endpoints", async t => {
  const port = 4199;
  const child = spawn(process.execPath, [path.join(__dirname, "..", "server.js")], {
    env: { ...process.env, PORT: String(port), PYTHON_OPTIMIZER_PORT: "5999" }, // Point to dummy port to test proxy + fallback
    stdio: ["ignore", "pipe", "pipe"]
  });
  t.after(() => child.kill());

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Dashboard server startup timed out.")), 5000);
    child.stdout.on("data", chunk => {
      if (String(chunk).includes("running at")) { clearTimeout(timer); resolve(); }
    });
    child.once("error", reject);
    child.once("exit", code => { if (code) reject(new Error(`Server exited with ${code}.`)); });
  });

  const baseUrl = `http://127.0.0.1:${port}`;

  // 1. Verify index.html contains all Phase L dashboard sections & UI elements
  const html = await fetch(`${baseUrl}/`).then(res => res.text());
  assert.match(html, /FlowQ/);
  assert.match(html, /id="resetBtn"/, "Reset button must be present");
  assert.match(html, /id="scenarioSelect"/, "Scenario selection must be present");
  assert.match(html, /id="tabLiveBtn"/, "Junction tab button must be present");
  assert.match(html, /id="tabNetworkBtn"/, "Network tab button must be present");
  assert.match(html, /id="tabEmergencyBtn"/, "Emergency tab button must be present");
  assert.match(html, /id="tabEventsBtn"/, "Events tab button must be present");
  assert.match(html, /id="tabMetricsBtn"/, "Metrics tab button must be present");
  assert.match(html, /id="tabResearchBtn"/, "QAOA research tab button must be present");
  assert.match(html, /id="networkGrid"/, "Network grid container must be present");
  assert.match(html, /id="northQueue"/, "Directional north queue element must be present");
  assert.match(html, /id="southQueue"/, "Directional south queue element must be present");
  assert.match(html, /id="eastQueue"/, "Directional east queue element must be present");
  assert.match(html, /id="westQueue"/, "Directional west queue element must be present");
  assert.match(html, /SIMULATION PROXY \(UNCALIBRATED\)/, "Simulation proxy disclaimer must be clearly present");
  assert.match(html, /2-Qubit Ising Hamiltonian/, "QAOA circuit description must be present");

  // Research integrity: verify no winner or best-controller claim in the template
  assert.doesNotMatch(html, /HYBRID WINS/, "Winner labels must not be displayed");
  assert.doesNotMatch(html, /BEST CONTROLLER/, "Best controller labels must not be displayed");

  // 2. Test GET /api/health
  const health = await fetch(`${baseUrl}/api/health`).then(res => res.json());
  assert.equal(health.ok, true);
  assert.equal(health.service, "FlowQ hybrid traffic backend");

  // 3. Test POST /api/optimize (Fallback mode when Python offline)
  const optRes = await fetch(`${baseUrl}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      states: [
        { intersection_id: "J1", vehicle_count: 20, queue_lengths: { north: 10, south: 5, east: 2, west: 3 } },
        { intersection_id: "J2", vehicle_count: 15, queue_lengths: { north: 1, south: 1, east: 8, west: 5 } }
      ],
      solver: "exact"
    })
  });
  assert.equal(optRes.status, 200);
  const optData = await optRes.json();
  assert.equal(optData.decisions.length, 2);
  assert.equal(optData.results[0].valid, true);
  assert.ok(optData.decisions[0].nsGreen >= 22);

  // 4. Test POST /api/emergency/corridor
  const emRes = await fetch(`${baseUrl}/api/emergency/corridor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      emergency_vehicle_id: "AMB001",
      current_intersection_id: "J1",
      destination_intersection_id: "J4",
      route: ["J1", "J2", "J3", "J4"]
    })
  });
  assert.equal(emRes.status, 200);
  const emData = await emRes.json();
  assert.equal(emData.emergency_vehicle_id, "AMB001");
  assert.equal(emData.status, "active");

  // 5. Test POST & GET /api/events
  const evRes = await fetch(`${baseUrl}/api/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_id: "EVT_ACC_J2",
      event_type: "accident",
      affected_intersection_ids: ["J2"],
      severity: "high"
    })
  });
  assert.equal(evRes.status, 200);
  const evData = await evRes.json();
  assert.equal(evData.accepted, true);

  const evListRes = await fetch(`${baseUrl}/api/events`);
  assert.equal(evListRes.status, 200);

  // 6. Test POST /api/metrics endpoint (Node proxy + fallback)
  const metricsRes = await fetch(`${baseUrl}/api/metrics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      network_id: "flowq_dashboard_net",
      states: [
        { intersection_id: "J1", vehicle_count: 20, queue_lengths: { north: 5, south: 5, east: 2, west: 2 } },
        { intersection_id: "J2", vehicle_count: 25, queue_lengths: { north: 2, south: 2, east: 10, west: 8 } }
      ]
    })
  });
  assert.equal(metricsRes.status, 200);
  const metricsData = await metricsRes.json();
  assert.ok(metricsData.network_total_waiting_time_seconds >= 0);
  assert.ok(metricsData.network_total_fuel_consumption_litres >= 0);
  assert.ok(metricsData.network_total_co2_emissions_grams >= 0);
  assert.equal(metricsData.fuel_source, "simulation_proxy");
  assert.equal(metricsData.co2_source, "simulation_proxy");

  // 7. Test Phase M: Real-World Prototype Tab and POST /api/perception/process
  assert.match(html, /id="tabRealworldBtn"/, "Real-World tab button must be present");
  assert.match(html, /id="tabRealworld"/, "Real-World tab pane must be present");
  assert.match(html, /id="rwSourceSelect"/, "Input source dropdown must be present");
  assert.match(html, /id="btnRunPerception"/, "Run perception button must be present");
  assert.match(html, /PROTOTYPE RESEARCH INTERFACE — NOT CONNECTED TO PHYSICAL HARDWARE/, "Hardware disclaimer must be present");

  const percRes = await fetch(`${baseUrl}/api/perception/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_type: "image",
      intersection_id: "J1",
      solver: "exact",
      optimize: true
    })
  });
  assert.equal(percRes.status, 200);
  const percData = await percRes.json();
  assert.equal(percData.status, "success");
  assert.equal(percData.intersection_id, "J1");
  assert.ok(percData.observation);
  assert.equal(percData.recommendation.recommendation_type, "Prototype Signal Recommendation");
  assert.ok(percData.recommendation.phase_0_green_seconds >= 22);
  assert.ok(percData.recommendation.phase_2_green_seconds >= 22);
  assert.match(percData.hardware_disclaimer, /research\/prototype/);
});
