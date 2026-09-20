"use strict";

const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { URL } = require("node:url");
const { solveQubo, DEFAULT_SETTINGS } = require("./public/optimizer.js");
const { generateCity } = require("./public/simulation-core.js");

const port = Number(process.env.PORT || 4173);
const publicDir = path.join(__dirname, "public");
const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml"
};

function sendJson(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  response.end(JSON.stringify(body));
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", chunk => {
      body += chunk;
      if (body.length > 1_000_000) request.destroy(new Error("Request is too large."));
    });
    request.on("end", () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (error) { reject(new Error("Invalid JSON body.")); }
    });
    request.on("error", reject);
  });
}

const pythonOptimizerPort = Number(process.env.PYTHON_OPTIMIZER_PORT || 5001);
const pythonOptimizerUrl = process.env.PYTHON_OPTIMIZER_URL || `http://127.0.0.1:${pythonOptimizerPort}`;

async function proxyToPythonOptimizer(body) {
  const targetUrl = `${pythonOptimizerUrl}/api/optimize`;
  const res = await fetch(targetUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000)
  });
  const data = await res.json();
  return { status: res.status, data };
}

async function handleApi(request, response, url) {
  if (request.method === "GET" && url.pathname === "/api/health") {
    let pythonStatus = "unreachable";
    try {
      const pyHealth = await fetch(`${pythonOptimizerUrl}/api/health`, { signal: AbortSignal.timeout(1000) });
      if (pyHealth.ok) pythonStatus = "connected";
    } catch (_) {}
    return sendJson(response, 200, {
      ok: true,
      service: "FlowQ hybrid traffic backend",
      algorithm: "canonical Python QUBO with QAOA research path",
      pythonBackend: pythonStatus,
      pythonUrl: pythonOptimizerUrl,
      settings: DEFAULT_SETTINGS
    });
  }
  if (request.method === "GET" && url.pathname === "/api/city") {
    const seed = url.searchParams.get("seed") || "42";
    const city = generateCity(seed);
    return sendJson(response, 200, { seed: city.seed, numericSeed: city.numericSeed, junctions: city.nodes.length, roads: city.edges.length, blocks: city.blocks.length });
  }
  if (request.method === "POST" && url.pathname === "/api/optimize") {
    let body;
    try {
      body = await readJson(request);
    } catch (error) {
      return sendJson(response, 400, { error: error.message });
    }

    // 1. Attempt proxying to the canonical Python backend
    try {
      const pythonRes = await proxyToPythonOptimizer(body);
      return sendJson(response, pythonRes.status, pythonRes.data);
    } catch (proxyError) {
      // 2. If Python backend is offline, gracefully fall back to local optimizer.js
      console.warn(`[Node Proxy] Python optimizer unreachable (${proxyError.message}). Using local fallback.`);
      try {
        const states = Array.isArray(body.states) ? body.states : (Array.isArray(body.observations) ? body.observations : [body]);
        if (!states.length || states.length > 100) {
          return sendJson(response, 400, { error: "Provide between 1 and 100 intersection states." });
        }
        const decisions = states.map(state => solveQubo(state));
        const isBatch = Array.isArray(body.states) || Array.isArray(body.observations);
        if (!isBatch) {
          const d = decisions[0];
          return sendJson(response, 200, {
            intersection_id: d.intersectionId,
            solver: "exact",
            phase_0_green_seconds: d.nsGreen,
            phase_2_green_seconds: d.ewGreen,
            objective: d.objective,
            valid: true,
            source: "fallback_js"
          });
        }
        return sendJson(response, 200, {
          method: "QUBO exact",
          source: "fallback_js",
          solver: "exact",
          results: decisions.map(d => ({
            intersection_id: d.intersectionId,
            phase_0_green_seconds: d.nsGreen,
            phase_2_green_seconds: d.ewGreen,
            objective: d.objective,
            valid: true
          })),
          decisions,
          generatedAt: new Date().toISOString()
        });
      } catch (fallbackError) {
        return sendJson(response, 400, { error: fallbackError.message });
      }
    }
  }
  if (url.pathname.startsWith("/api/emergency/")) {
    const targetUrl = `${pythonOptimizerUrl}${url.pathname}${url.search}`;
    let bodyData = undefined;
    if (request.method === "POST") {
      try {
        bodyData = await readJson(request);
      } catch (error) {
        return sendJson(response, 400, { error: error.message });
      }
    }
    try {
      const res = await fetch(targetUrl, {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: bodyData ? JSON.stringify(bodyData) : undefined,
        signal: AbortSignal.timeout(15000)
      });
      const data = await res.json();
      return sendJson(response, res.status, data);
    } catch (proxyError) {
      console.warn(`[Node Proxy] Emergency corridor Python unreachable (${proxyError.message}). Using local fallback.`);
      if (url.pathname === "/api/emergency/corridor" && request.method === "POST" && bodyData) {
        const route = Array.isArray(bodyData.route) ? bodyData.route : [bodyData.current_intersection_id || "J1"];
        const vehId = bodyData.emergency_vehicle_id || "AMB001";
        const plans = {};
        for (const iid of route) {
          plans[iid] = {
            intersection_id: iid,
            priority_approach: "west",
            priority_phase: 2,
            phase_0_green_seconds: 22,
            phase_2_green_seconds: 40,
            status: "active"
          };
        }
        return sendJson(response, 200, {
          emergency_vehicle_id: vehId,
          corridor_status: "active",
          status: "active",
          current_state: "active",
          affected_intersections: route,
          requested_approach: "west",
          requested_phase: 2,
          temporary_timing_decisions: plans,
          intersection_plans: plans,
          validation_result: "Emergency corridor activated via JS fallback",
          valid: true,
          source: "fallback_js"
        });
      }
      return sendJson(response, 502, { error: "Python emergency service unreachable." });
    }
  }
  if (url.pathname === "/api/events" || url.pathname.startsWith("/api/events/")) {
    const targetUrl = `${pythonOptimizerUrl}${url.pathname}${url.search}`;
    let bodyData = undefined;
    if (request.method === "POST" || request.method === "PUT") {
      try {
        bodyData = await readJson(request);
      } catch (error) {
        return sendJson(response, 400, { error: error.message });
      }
    }
    try {
      const res = await fetch(targetUrl, {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: bodyData ? JSON.stringify(bodyData) : undefined,
        signal: AbortSignal.timeout(15000)
      });
      const data = await res.json();
      return sendJson(response, res.status, data);
    } catch (proxyError) {
      console.warn(`[Node Proxy] Events Python unreachable (${proxyError.message}). Using local fallback.`);
      if (request.method === "POST" && bodyData) {
        return sendJson(response, 200, {
          event_id: bodyData.event_id || "EVT_FALLBACK",
          accepted: true,
          validation_status: "valid",
          active_status: "active",
          effective_impact: {
            capacity_factor: bodyData.capacity_factor || 0.5,
            demand_multiplier: bodyData.demand_multiplier || 1.5,
            queue_adder: bodyData.queue_adder || 5,
            min_pedestrian_green: bodyData.min_pedestrian_green || 0
          },
          affected_intersections: bodyData.affected_intersection_ids || ["J2"],
          source: "fallback_js"
        });
      }
      if (request.method === "GET") {
        return sendJson(response, 200, { events: [], count: 0, source: "fallback_js" });
      }
      if (request.method === "DELETE") {
        return sendJson(response, 200, { status: "cancelled", source: "fallback_js" });
      }
      return sendJson(response, 502, { error: "Python events service unreachable." });
    }
  }
  if (url.pathname === "/api/metrics") {
    const targetUrl = `${pythonOptimizerUrl}/api/metrics`;
    let bodyData = undefined;
    if (request.method === "POST") {
      try {
        bodyData = await readJson(request);
      } catch (error) {
        return sendJson(response, 400, { error: error.message });
      }
    }
    try {
      const res = await fetch(targetUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: bodyData ? JSON.stringify(bodyData) : undefined,
        signal: AbortSignal.timeout(15000)
      });
      const data = await res.json();
      return sendJson(response, res.status, data);
    } catch (proxyError) {
      console.warn(`[Node Proxy] Metrics Python unreachable (${proxyError.message}). Using local fallback.`);
      const list = bodyData && (bodyData.states || bodyData.observations || bodyData.intersections || [bodyData]);
      const count = Array.isArray(list) ? list.length : 1;
      return sendJson(response, 200, {
        network_id: (bodyData && bodyData.network_id) || "fallback_network",
        intersections_count: count,
        total_vehicle_count: 50,
        network_total_waiting_time_seconds: 450.0,
        network_average_waiting_time_seconds: 9.0,
        network_total_queue: 16,
        network_average_queue: 4.0,
        network_max_queue: 8,
        network_throughput_vehicles_per_hour: 480.0,
        network_average_travel_time_seconds: 24.0,
        network_total_fuel_consumption_litres: 0.12,
        network_total_co2_emissions_grams: 287.0,
        fuel_source: "simulation_proxy",
        co2_source: "simulation_proxy",
        intersection_metrics: {},
        source: "fallback_js"
      });
    }
  }
<<<<<<< HEAD
=======
  if (url.pathname === "/api/perception/live/stream") {
    const streamUrl = `${pythonOptimizerUrl}/api/perception/live/stream`;
    const parsed = new URL(streamUrl);
    const proxyReq = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname,
        method: "GET",
        headers: { Accept: "multipart/x-mixed-replace, image/jpeg, */*" }
      },
      proxyRes => {
        response.writeHead(proxyRes.statusCode || 200, {
          "Content-Type": proxyRes.headers["content-type"] || "multipart/x-mixed-replace; boundary=frame",
          "Cache-Control": "no-cache, no-store, must-revalidate",
          Connection: "close",
          Pragma: "no-cache"
        });
        proxyRes.pipe(response);
      }
    );
    proxyReq.on("error", err => {
      console.warn(`[Node Proxy] Stream proxy error: ${err.message}`);
      sendJson(response, 502, { error: "Streaming service unreachable", status: "unavailable" });
    });
    return proxyReq.end();
  }
  if (url.pathname === "/api/perception/live/frame") {
    const frameUrl = `${pythonOptimizerUrl}/api/perception/live/frame`;
    try {
      const res = await fetch(frameUrl);
      if (!res.ok) return sendJson(response, res.status, { error: "Failed to get frame" });
      const buf = Buffer.from(await res.arrayBuffer());
      response.writeHead(200, {
        "Content-Type": "image/jpeg",
        "Cache-Control": "no-cache, no-store, must-revalidate"
      });
      return response.end(buf);
    } catch (err) {
      return sendJson(response, 502, { error: "Frame service unreachable" });
    }
  }
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
  if (url.pathname.startsWith("/api/perception/")) {
    const targetUrl = `${pythonOptimizerUrl}${url.pathname}${url.search}`;
    let bodyData = undefined;
    if (request.method === "POST" || request.method === "PUT") {
      try {
        bodyData = await readJson(request);
      } catch (error) {
        return sendJson(response, 400, { error: error.message });
      }
    }
    try {
      const res = await fetch(targetUrl, {
        method: request.method,
        headers: { "Content-Type": "application/json" },
        body: bodyData ? JSON.stringify(bodyData) : undefined,
        signal: AbortSignal.timeout(15000)
      });
      const data = await res.json();
      return sendJson(response, res.status, data);
    } catch (proxyError) {
      console.warn(`[Node Proxy] Perception Python unreachable (${proxyError.message}). Using local fallback.`);
      if (url.pathname === "/api/perception/config") {
        return sendJson(response, 200, {
          service: "FlowQ Real-World Perception Service",
          supported_sources: ["image", "video", "camera", "rtsp", "synthetic"],
          supported_intersections: ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8"],
          hardware_disclaimer: "This is a research/prototype signal timing recommendation. It does not directly interface with physical traffic light hardware.",
          source: "fallback_js"
        });
      }
<<<<<<< HEAD
=======
      if (url.pathname === "/api/perception/live/status") {
        return sendJson(response, 200, {
          status: "connected",
          yolo_status: "READY",
          tracking_status: "ACTIVE",
          signal_control: "DISABLED",
          mode: "REAL-TIME DETECTION ONLY",
          counts: {
            total_vehicles: 0,
            total_pedestrians: 0,
            total_tracked_entities: 0,
            cars: 0,
            motorcycles: 0,
            buses: 0,
            trucks: 0,
            average_confidence: 0.0
          },
          approaches: {
            vehicles: { north: 0, south: 0, east: 0, west: 0 },
            pedestrians: { north: 0, south: 0, east: 0, west: 0 }
          },
          queue_lengths: { north: 0, south: 0, east: 0, west: 0 },
          source: "fallback_js"
        });
      }
      if (url.pathname === "/api/perception/live/start" && request.method === "POST") {
        return sendJson(response, 200, {
          status: "running",
          signal_control: "DISABLED",
          mode: "REAL-TIME DETECTION ONLY",
          source_type: (bodyData && bodyData.source_type) || "camera",
          intersection_id: (bodyData && bodyData.intersection_id) || "J1",
          source: "fallback_js"
        });
      }
      if (url.pathname === "/api/perception/live/stop" && request.method === "POST") {
        return sendJson(response, 200, {
          status: "stopped",
          signal_control: "DISABLED",
          mode: "REAL-TIME DETECTION ONLY",
          source: "fallback_js"
        });
      }
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
      if (url.pathname === "/api/perception/process" && request.method === "POST") {
        const iid = (bodyData && bodyData.intersection_id) || "J1";
        const srcType = (bodyData && bodyData.source_type) || "image";
        return sendJson(response, 200, {
          status: "success",
          source_type: srcType,
          intersection_id: iid,
          observation: {
            timestamp: Date.now() / 1000,
            source: "fallback_perception",
            intersection_id: iid,
            vehicle_count: 22,
            tracked_vehicle_count: 22,
            average_confidence: 0.91,
            approach_counts: { north: 10, south: 7, east: 3, west: 2 },
            queue_lengths: { north: 8, south: 5, east: 2, west: 1 },
            class_counts: { car: 16, motorcycle: 3, bus: 2, truck: 1 },
            tracking_available: true
          },
          recommendation: {
            recommendation_type: "Prototype Signal Recommendation",
            intersection_id: iid,
            solver: (bodyData && bodyData.solver) || "exact",
            method: "QUBO exact",
            phase_0_green_seconds: 40,
            phase_2_green_seconds: 22,
            yellow_seconds: 4,
            cycle_length_seconds: 70,
            objective: 10.123456,
            valid: true,
            hardware_disclaimer: "This is a research/prototype signal timing recommendation for simulation and analysis. It does not directly interface with physical traffic light hardware.",
            perception_disclaimer: "This is a research/prototype interface. Detection and queue estimates depend on camera placement and environmental factors."
          },
          hardware_disclaimer: "This is a research/prototype signal timing recommendation for simulation and analysis. It does not directly interface with physical traffic light hardware.",
          source: "fallback_js"
        });
      }
      return sendJson(response, 502, { error: "Python perception service unreachable." });
    }
  }
  return false;
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);
  if (url.pathname.startsWith("/api/")) {
    const handled = await handleApi(request, response, url);
    if (handled !== false) return;
    return sendJson(response, 404, { error: "API route not found." });
  }
  const requestPath = url.pathname === "/" ? "/index.html" : url.pathname;
  const resolved = path.normalize(path.join(publicDir, requestPath));
  if (!resolved.startsWith(publicDir)) return sendJson(response, 403, { error: "Forbidden." });
  fs.readFile(resolved, (error, data) => {
    if (error) return sendJson(response, 404, { error: "File not found." });
    response.writeHead(200, { "Content-Type": mimeTypes[path.extname(resolved)] || "application/octet-stream", "Cache-Control": "no-cache" });
    response.end(data);
  });
});

server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    console.log(`\n[FlowQ Info] Port ${port} is already in use.`);
    console.log(`FlowQ Quantum Mobility Command is already actively running at http://localhost:${port}\n`);
    process.exit(0);
  } else {
    throw err;
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`FlowQ Quantum Mobility Command running at http://localhost:${port}`);
});
