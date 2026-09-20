"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const path = require("node:path");

test("npm backend serves the dashboard and QUBO API", async t => {
  const port = 4188;
  const child = spawn(process.execPath, [path.join(__dirname, "..", "server.js")], {
    env: { ...process.env, PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"]
  });
  t.after(() => child.kill());
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Backend startup timed out.")), 5000);
    child.stdout.on("data", chunk => {
      if (String(chunk).includes("running at")) { clearTimeout(timer); resolve(); }
    });
    child.once("error", reject);
    child.once("exit", code => { if (code) reject(new Error(`Backend exited with ${code}.`)); });
  });

  const health = await fetch(`http://127.0.0.1:${port}/api/health`).then(response => response.json());
  assert.equal(health.ok, true);
  const optimization = await fetch(`http://127.0.0.1:${port}/api/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ states: [{ intersectionId: 7, nsQueue: 19, ewQueue: 3, trafficDensity: .5, vehicleCount: 26, roadCapacity: 48 }] })
  }).then(response => response.json());
  assert.equal(optimization.decisions.length, 1);
  assert.equal(optimization.decisions[0].intersectionId, 7);
  assert.equal(optimization.decisions[0].method, "QUBO exact");
  const page = await fetch(`http://127.0.0.1:${port}/`).then(response => response.text());
  assert.match(page, /FlowQ/);
});
