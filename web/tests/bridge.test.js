"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const path = require("node:path");

test("End-to-End Bridge: Node proxy -> Python QUBO backend", async t => {
  const pythonPort = 5005;
  const nodePort = 4195;
  const rootDir = path.join(__dirname, "..", "..");

  // 1. Start Python backend
  const pythonChild = spawn("python", [path.join(rootDir, "server.py")], {
    cwd: rootDir,
    env: { ...process.env, PYTHON_OPTIMIZER_PORT: String(pythonPort) },
    stdio: ["ignore", "pipe", "pipe"]
  });

  t.after(() => {
    pythonChild.kill();
  });

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Python backend startup timed out.")), 10000);
    pythonChild.stdout.on("data", chunk => {
      if (String(chunk).includes("running at")) {
        clearTimeout(timer);
        resolve();
      }
    });
    pythonChild.stderr.on("data", chunk => {
      if (String(chunk).includes("running at")) {
        clearTimeout(timer);
        resolve();
      }
    });
    pythonChild.once("error", reject);
    pythonChild.once("exit", code => {
      if (code) reject(new Error(`Python backend exited with code ${code}.`));
    });
  });

  // 2. Start Node server configured to point to Python backend
  const nodeChild = spawn(process.execPath, [path.join(rootDir, "web", "server.js")], {
    cwd: rootDir,
    env: {
      ...process.env,
      PORT: String(nodePort),
      PYTHON_OPTIMIZER_PORT: String(pythonPort)
    },
    stdio: ["ignore", "pipe", "pipe"]
  });

  t.after(() => {
    nodeChild.kill();
  });

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Node backend startup timed out.")), 5000);
    nodeChild.stdout.on("data", chunk => {
      if (String(chunk).includes("running at")) {
        clearTimeout(timer);
        resolve();
      }
    });
    nodeChild.once("error", reject);
    nodeChild.once("exit", code => {
      if (code) reject(new Error(`Node backend exited with code ${code}.`));
    });
  });

  // 3. Verify Health Check reports Python connected
  const health = await fetch(`http://127.0.0.1:${nodePort}/api/health`).then(res => res.json());
  assert.equal(health.ok, true);
  assert.equal(health.pythonBackend, "connected");

  // 4. Test Single Intersection Request (Task 2 example)
  const singlePayload = {
    intersection_id: "J1",
    vehicle_count: 24,
    traffic_density: 0.72,
    road_capacity: 100,
    current_signal_phase: 0,
    phase_0_queue: 20,
    phase_2_queue: 4,
    solver: "exact"
  };

  const singleRes = await fetch(`http://127.0.0.1:${nodePort}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(singlePayload)
  });
  assert.equal(singleRes.status, 200);
  const singleData = await singleRes.json();
  assert.equal(singleData.intersection_id, "J1");
  assert.equal(singleData.solver, "exact");
  assert.equal(singleData.phase_0_green_seconds, 40);
  assert.equal(singleData.phase_2_green_seconds, 22);
  assert.equal(singleData.valid, true);
  assert.ok(typeof singleData.objective === "number");

  // 5. Test Batch Simulation State Request
  const batchPayload = {
    states: [
      {
        intersectionId: 0,
        nsQueue: 20,
        ewQueue: 4,
        trafficDensity: 0.5,
        vehicleCount: 24,
        roadCapacity: 100
      }
    ]
  };
  const batchRes = await fetch(`http://127.0.0.1:${nodePort}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(batchPayload)
  });
  assert.equal(batchRes.status, 200);
  const batchData = await batchRes.json();
  assert.ok(Array.isArray(batchData.decisions));
  assert.equal(batchData.decisions.length, 1);
  assert.equal(batchData.decisions[0].nsGreen, 40);
  assert.equal(batchData.decisions[0].ewGreen, 22);
  assert.equal(batchData.decisions[0].valid, true);

  // 6. Test Multi-Intersection Batch through Bridge (J1-J4)
  const multiPayload = {
    solver: "exact",
    states: [
      {
        intersection_id: "J1",
        vehicle_count: 24,
        queue_lengths: { north: 12, south: 8, east: 2, west: 2 }
      },
      {
        intersection_id: "J2",
        vehicle_count: 20,
        queue_lengths: { north: 2, south: 1, east: 10, west: 7 }
      },
      {
        intersection_id: "J3",
        vehicle_count: 10,
        queue_lengths: { north: 5, south: 5, east: 5, west: 5 }
      },
      {
        intersection_id: "J4",
        vehicle_count: 8,
        queue_lengths: { north: 4, south: 2, east: 1, west: 1 }
      }
    ]
  };
  const multiRes = await fetch(`http://127.0.0.1:${nodePort}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(multiPayload)
  });
  assert.equal(multiRes.status, 200);
  const multiData = await multiRes.json();
  assert.ok(Array.isArray(multiData.results));
  assert.equal(multiData.results.length, 4);
  assert.equal(multiData.results[0].intersection_id, "J1");
  assert.equal(multiData.results[1].intersection_id, "J2");
  assert.equal(multiData.results[2].intersection_id, "J3");
  assert.equal(multiData.results[3].intersection_id, "J4");
  assert.equal(multiData.results[0].phase_0_green_seconds, 40);
  assert.equal(multiData.results[1].phase_2_green_seconds, 40);

  // 7. Test Error Handling through proxy (negative queue)
  const invalidPayload = {
    intersection_id: "J1",
    phase_0_queue: -5,
    phase_2_queue: 10
  };
  const errorRes = await fetch(`http://127.0.0.1:${nodePort}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(invalidPayload)
  });
  assert.equal(errorRes.status, 400);
  const errorData = await errorRes.json();
  assert.ok(errorData.error.includes("negative"));

  // 8. Test Emergency Green Corridor through Bridge (J1 -> J4)
  const emergencyPayload = {
    emergency_vehicle_id: "AMB101",
    current_intersection_id: "J1",
    destination_intersection_id: "J4",
    route: ["J1", "J2", "J4"],
    priority: "high",
    timestamp: Date.now() / 1000
  };
  const emergencyRes = await fetch(`http://127.0.0.1:${nodePort}/api/emergency/corridor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(emergencyPayload)
  });
  assert.equal(emergencyRes.status, 200);
  const emergencyData = await emergencyRes.json();
  assert.equal(emergencyData.emergency_vehicle_id, "AMB101");
  assert.equal(emergencyData.corridor_status, "active");
  assert.equal(emergencyData.valid, true);
  assert.deepEqual(emergencyData.affected_intersections, ["J1", "J2", "J4"]);
  assert.ok(emergencyData.temporary_timing_decisions["J1"]);
  assert.ok(emergencyData.temporary_timing_decisions["J2"]);
  assert.ok(emergencyData.temporary_timing_decisions["J4"]);

  // 9. Test Dynamic Traffic Events through Bridge
  const now = Date.now() / 1000;
  const eventPayload = {
    event_id: "ACC_BRIDGE_01",
    event_type: "accident",
    affected_intersection_ids: ["J2"],
    affected_approaches: ["east"],
    severity: "high",
    start_time: now,
    end_time: now + 300
  };
  const eventPostRes = await fetch(`http://127.0.0.1:${nodePort}/api/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(eventPayload)
  });
  assert.equal(eventPostRes.status, 200);
  const eventPostData = await eventPostRes.json();
  assert.equal(eventPostData.event_id, "ACC_BRIDGE_01");
  assert.equal(eventPostData.accepted, true);
  assert.deepEqual(eventPostData.affected_intersections, ["J2"]);

  const eventGetRes = await fetch(`http://127.0.0.1:${nodePort}/api/events`);
  assert.equal(eventGetRes.status, 200);
  const eventGetData = await eventGetRes.json();
  assert.ok(eventGetData.count >= 1);

  const eventDelRes = await fetch(`http://127.0.0.1:${nodePort}/api/events/ACC_BRIDGE_01`, {
    method: "DELETE"
  });
  assert.equal(eventDelRes.status, 200);
  const eventDelData = await eventDelRes.json();
  assert.equal(eventDelData.status, "cancelled");
});
