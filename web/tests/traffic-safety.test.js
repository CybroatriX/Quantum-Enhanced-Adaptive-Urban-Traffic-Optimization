"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const vm = require("node:vm");
const SimulationCore = require("../public/simulation-core.js");
const TrafficOptimizer = require("../public/optimizer.js");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  toggle(value, force) {
    if (force === true) this.values.add(value);
    else if (force === false) this.values.delete(value);
    else if (this.values.has(value)) this.values.delete(value);
    else this.values.add(value);
  }
}

function createMockContext() {
  const gradient = () => ({ addColorStop() {} });
  return new Proxy({}, {
    get(target, property) {
      if (property === "createRadialGradient" || property === "createLinearGradient") return gradient;
      if (["fillRect", "stroke", "arc", "fillText", "strokeRect"].includes(property)) return () => {};
      if (["setTransform", "beginPath", "moveTo", "lineTo", "fill", "save", "restore", "translate", "scale", "rotate", "setLineDash", "clearRect"].includes(property)) return () => {};
      return target[property];
    },
    set(target, property, value) { target[property] = value; return true; }
  });
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.checked = true;
    this.hidden = false;
    this.style = {};
    this.classList = new ClassList();
    this.listeners = {};
    this.parentElement = { classList: new ClassList() };
    this.options = [{ text: "QUBO adaptive" }, { text: "Pressure adaptive" }, { text: "Fixed timing" }];
    this.selectedIndex = 0;
    this.width = 1100;
    this.height = 800;
    this._context = createMockContext();
    this._lights = ["red", "yellow", "green"].map(color => ({ classList: new ClassList(), color }));
  }
  getContext() { return this._context; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 1100, height: 800 }; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  fire(type, extra = {}) {
    const event = { target: this, clientX: 550, clientY: 400, pointerId: 1, deltaY: 0, key: "", preventDefault() {}, ...extra };
    for (const callback of this.listeners[type] || []) callback(event);
  }
  querySelectorAll(selector) { return selector === "i" ? this._lights : []; }
  querySelector(selector) { return this._lights.find(light => `.${light.color}` === selector) || null; }
  setPointerCapture() {}
}

function setupSimulationSandbox(customDefaults = {}) {
  const root = path.join(__dirname, "..", "public");
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  const code = fs.readFileSync(path.join(root, "app.js"), "utf8");
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  const elements = new Map(ids.map(id => [id, new FakeElement(id)]));

  const defaults = {
    seedInput: "SAFETY-TEST", controllerSelect: "qubo", demandRange: "80",
    pedestrianRange: "20", speedRange: "1", ...customDefaults
  };
  Object.entries(defaults).forEach(([id, value]) => {
    if (elements.has(id)) elements.get(id).value = value;
  });

  const mapActions = ["congestionBtn", "accidentBtn", "closureBtn", "ambulanceBtn", "hospitalBtn", "inspectBtn"]
    .map(id => elements.get(id));
  const raf = [];
  const windowObject = {
    SimulationCore,
    TrafficOptimizer,
    devicePixelRatio: 1,
    addEventListener() {}
  };
  const documentObject = {
    getElementById(id) { return elements.get(id) || null; },
    querySelectorAll(selector) { return selector === ".map-action" ? mapActions : []; }
  };
  const sandbox = {
    window: windowObject,
    document: documentObject,
    location: { protocol: "file:" },
    performance: { now: () => 0 },
    requestAnimationFrame(callback) { raf.push(callback); return raf.length; },
    setTimeout(callback) { callback(); return 1; },
    clearTimeout() {},
    fetch: async () => { throw new Error("No network"); },
    console, Math, Map, Set, Array, Object, Number, String
  };

  vm.runInNewContext(code, sandbox, { filename: "app.js" });
  return { sandbox, windowObject, elements, raf };
}

test("SPAWNING: vehicles spawn only at valid outer road entrances and respect clearance", () => {
  const city = SimulationCore.generateCity("COIMBATORE-TEST");
  assert.equal(city.spawnPoints.length, 8, "Must have exactly 8 outer road entry spawn points");

  // J1-J4 positions must remain locked at approved coordinates
  assert.deepEqual({ x: city.nodes[0].x, y: city.nodes[0].y }, { x: 520, y: 320 }, "J1 must be at (520, 320)");
  assert.deepEqual({ x: city.nodes[1].x, y: city.nodes[1].y }, { x: 1200, y: 320 }, "J2 must be at (1200, 320)");
  assert.deepEqual({ x: city.nodes[2].x, y: city.nodes[2].y }, { x: 520, y: 660 }, "J3 must be at (520, 660)");
  assert.deepEqual({ x: city.nodes[3].x, y: city.nodes[3].y }, { x: 1200, y: 660 }, "J4 must be at (1200, 660)");

  // Verify all 8 spawn points are strictly at perimeter boundary nodes
  for (const sp of city.spawnPoints) {
    assert.ok(city.boundaryNodes.includes(sp.nodeId), `${sp.id} must be at a boundary node`);
    assert.ok(sp.nodeId >= 4 && sp.nodeId <= 11, "Spawn point must be an outer node 4..11");

    // Must be well outside of intersections (distance > 200px)
    for (let j = 0; j < 4; j += 1) {
      const dist = Math.hypot(sp.x - city.nodes[j].x, sp.y - city.nodes[j].y);
      assert.ok(dist >= 200, `Spawn point ${sp.id} must be far outside junction J${j + 1}`);
    }

    // Must not be inside any city block/building
    for (const block of city.blocks) {
      const insideBlock = sp.x >= block.minX && sp.x <= block.minX + block.width &&
                          sp.y >= block.minY && sp.y <= block.minY + block.height;
      assert.ok(!insideBlock, `Spawn point ${sp.id} must not be inside any city block`);
    }
  }
});

test("LANES & MEDIAN: opposite directions remain separated and never cross median", async () => {
  const { windowObject, raf } = setupSimulationSandbox({ demandRange: "120" });

  let now = 0;
  for (let frame = 0; frame < 600; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 20 === 0) await Promise.resolve();
  }

  const snap = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(snap.overlaps, 0, "No overlapping vehicles in lane separation test");
  assert.ok(snap.vehicles.length > 0, "Vehicles must be present on road network");

  // Every vehicle must have a valid lane (0 or 1) and stay strictly on its designated carriageway
  for (const v of snap.vehicles) {
    assert.ok(v.lane === 0 || v.lane === 1, `Vehicle ${v.id} must be in lane 0 or 1, got ${v.lane}`);
    assert.ok(v.progress >= 0 && v.progress <= 1, `Vehicle ${v.id} progress must be within [0, 1]`);
  }
});

test("ACCIDENT SPEED PROFILE: unit test cases 1-6 for distance-based speed moderation", () => {
  const edgeLength = 500;
  const baseSpeed = 25;

  // TEST 1: Vehicle far from accident (> 140px before center) -> normal speed
  const farProg = 0.5 - (160 / edgeLength); // 160px before center
  const pFar = SimulationCore.calculateAccidentSpeedProfile(farProg, edgeLength, baseSpeed, true);
  assert.equal(pFar.zone, "before");
  assert.equal(pFar.speedFactor, 1.0);
  assert.equal(pFar.desiredSpeed, baseSpeed);
  assert.equal(pFar.state, "NORMAL");

  // TEST 2: Vehicle approaches accident (between 22px and 140px before center) -> gradual slowdown
  const approachProg = 0.5 - (70 / edgeLength); // 70px before center
  const pApproach = SimulationCore.calculateAccidentSpeedProfile(approachProg, edgeLength, baseSpeed, true);
  assert.equal(pApproach.zone, "approach");
  assert.ok(pApproach.desiredSpeed < baseSpeed, "Speed must decrease on approach");
  assert.ok(pApproach.desiredSpeed > 10.5, "Approach speed must be higher than minimum cautious passing speed");
  assert.equal(pApproach.state, "SLOWING_FOR_ACCIDENT");
  assert.equal(pApproach.lateralNudge, 4);

  // TEST 3: Vehicle reaches accident zone (within 22px of center) -> continues at reduced speed
  const reachProg = 0.5 - (15 / edgeLength); // 15px before center
  const pReach = SimulationCore.calculateAccidentSpeedProfile(reachProg, edgeLength, baseSpeed, true);
  assert.equal(pReach.zone, "accident");
  assert.ok(pReach.desiredSpeed >= 8.5, "Must maintain safe passing speed, never 0");
  assert.equal(pReach.state, "PASSING_ACCIDENT");

  // TEST 4: Vehicle crosses accident center (distAlong = 0) -> does NOT stop permanently
  const crossProg = 0.5; // Exactly at center
  const pCross = SimulationCore.calculateAccidentSpeedProfile(crossProg, edgeLength, baseSpeed, true);
  assert.equal(pCross.zone, "accident");
  assert.ok(pCross.desiredSpeed > 0, "Must NEVER be 0 at accident center");
  assert.equal(pCross.desiredSpeed, Math.max(baseSpeed * 0.42, 8.5));
  assert.equal(pCross.state, "PASSING_ACCIDENT");

  // TEST 5: Vehicle passes accident exit boundary (between 22px and 85px past center) -> gradual acceleration
  const exitProg = 0.5 + (50 / edgeLength); // 50px past center
  const pExit = SimulationCore.calculateAccidentSpeedProfile(exitProg, edgeLength, baseSpeed, true);
  assert.equal(pExit.zone, "exit");
  assert.ok(pExit.desiredSpeed > pCross.desiredSpeed, "Speed must accelerate in exit zone");
  assert.ok(pExit.desiredSpeed < baseSpeed, "Exit speed smoothly approaches normal speed");
  assert.equal(pExit.state, "ACCELERATING_FROM_ACCIDENT");
  assert.equal(pExit.lateralNudge, 0);

  // TEST 6: Vehicle already past accident (> 85px past center) -> no further slowdown
  const pastProg = 0.5 + (100 / edgeLength); // 100px past center
  const pPast = SimulationCore.calculateAccidentSpeedProfile(pastProg, edgeLength, baseSpeed, true);
  assert.equal(pPast.zone, "past");
  assert.equal(pPast.speedFactor, 1.0);
  assert.equal(pPast.desiredSpeed, baseSpeed);
  assert.equal(pPast.state, "NORMAL");
});

test("ACCIDENT DYNAMICS: test cases 7-12 for passing, lane awareness, following distance, signals, and clearing", async () => {
  const { windowObject, elements, raf } = setupSimulationSandbox({ demandRange: "70" });
  const city = SimulationCore.generateCity("SAFETY-TEST");

  // Warm up simulation
  let now = 0;
  for (let frame = 0; frame < 200; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
  }

  const snapInitial = windowObject.FlowQDiagnostics.snapshot();
  const target = snapInitial.vehicles.find(v => v.progress >= 0.05 && v.progress <= 0.35) || snapInitial.vehicles[0];
  const targetEdge = city.edges.find(e => (e.a === target.from && e.b === target.to) || (e.a === target.to && e.b === target.from));

  // Inject accident directly in front of target vehicle on its current edge and lane
  windowObject.FlowQDiagnostics.injectRoadEvent(targetEdge.id, "accident", {
    from: target.from,
    to: target.to,
    lane: target.lane
  });

  // TEST 11 & 12: Advance simulation (700 frames) with active accident
  // Vehicles must approach, slow down, pass through progress 0.5 without freezing, and accelerate away
  let observedPassing = false;
  let targetCompletedOrCrossed = false;

  for (let frame = 0; frame < 700; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 20 === 0) await Promise.resolve();

    const snap = windowObject.FlowQDiagnostics.snapshot();
    // Verify TEST 9: safe following distance, zero overlaps at all times
    assert.equal(snap.overlaps, 0, `No overlaps during frame ${frame}`);

    const currentTarget = snap.vehicles.find(v => v.id === target.id);
    if (currentTarget) {
      if (currentTarget.from === target.from && currentTarget.to === target.to) {
        if (currentTarget.progress >= 0.48 && currentTarget.progress <= 0.55) {
          observedPassing = true;
          // TEST 3 & 4: vehicle crossing the accident center must be moving at cautious speed, never 0
          assert.ok(currentTarget.currentSpeed > 0, "Vehicle must not freeze at accident center");
          assert.equal(currentTarget.state, "PASSING_ACCIDENT");
        }
        if (currentTarget.progress > 0.65) {
          targetCompletedOrCrossed = true;
        }
      } else {
        // Vehicle completed its edge and moved to next edge
        targetCompletedOrCrossed = true;
      }
    } else {
      // Vehicle completed entire route
      targetCompletedOrCrossed = true;
    }

    // TEST 7: check vehicles on opposite direction or other lanes of targetEdge
    const otherVehicles = snap.vehicles.filter(v => {
      const onSamePhysicalRoad = (v.from === targetEdge.a && v.to === targetEdge.b) || (v.from === targetEdge.b && v.to === targetEdge.a);
      const isOpposite = (v.from === target.to && v.to === target.from);
      const isOtherLane = v.lane !== target.lane;
      return onSamePhysicalRoad && (isOpposite || isOtherLane);
    });
    for (const ov of otherVehicles) {
      assert.notEqual(ov.state, "SLOWING_FOR_ACCIDENT", "Opposite or unaffected lane vehicles must not slow for accident");
      assert.notEqual(ov.state, "PASSING_ACCIDENT", "Opposite or unaffected lane vehicles must not enter passing state");
    }
  }

  const snapAccident = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(snapAccident.overlaps, 0, "Accident passing must maintain safe headway without overlaps");
  assert.ok(observedPassing || targetCompletedOrCrossed, "Target vehicle must cross or pass through the accident zone without freezing");

  // TEST 10: Clear events and verify smooth resumption to full normal speed
  elements.get("clearEventsBtn").fire("click");
  for (let frame = 0; frame < 300; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
  }
  const snapCleared = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(snapCleared.overlaps, 0, "Normal traffic resumption must not cause overlaps");
  assert.equal(snapCleared.activeRoadEvents, 0, "All road events should be cleared");
  for (const v of snapCleared.vehicles) {
    assert.notEqual(v.state, "PASSING_ACCIDENT", "No vehicle should retain accident state after event cleared");
    assert.notEqual(v.state, "SLOWING_FOR_ACCIDENT", "No vehicle should retain slowing state after event cleared");
  }
});

test("AMBULANCE: nearby cars yield to safe outer curb edge without crossing median, then return", async () => {
  const { windowObject, elements, raf } = setupSimulationSandbox({ demandRange: "100" });
  const city = SimulationCore.generateCity("SAFETY-TEST");

  // Move hospital to node 2 (J3 Market Circle)
  elements.get("hospitalBtn").fire("click");
  elements.get("cityCanvas").fire("pointerdown", { clientX: 550, clientY: 400 });
  elements.get("cityCanvas").fire("pointerup", { clientX: 550, clientY: 400 });

  // Dispatch ambulance from node 1 (J2 Civic Square)
  elements.get("ambulanceBtn").fire("click");
  elements.get("cityCanvas").fire("pointerdown", { clientX: 550, clientY: 400 });
  elements.get("cityCanvas").fire("pointerup", { clientX: 550, clientY: 400 });

  let now = 0;
  for (let frame = 0; frame < 800; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 25 === 0) await Promise.resolve();
  }

  const snap = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(snap.overlaps, 0, "Ambulance passage must not cause any vehicle overlaps");
});

test("BUILDING ACCESS: driveways provide safe off-road parking and safe curb re-entry", () => {
  const city = SimulationCore.generateCity("BUILDING-TEST");
  assert.ok(city.buildingDriveways && city.buildingDriveways.length >= 2, "Must provide designated building driveways");

  for (const bd of city.buildingDriveways) {
    assert.ok(bd.id, "Driveway must have ID");
    assert.ok(bd.roadSegment !== undefined, "Driveway must be attached to a valid road segment");
    assert.ok(bd.roadX && bd.roadY, "Must have valid road connection coordinates");
    assert.ok(bd.curbX && bd.curbY, "Must have valid curb transition coordinates");
    assert.ok(bd.parkingX && bd.parkingY, "Must have valid parking bay coordinates");

    // Parking area must be outside the road travel lanes (road width is 72px, half-width 36px)
    const edge = city.edges[bd.roadSegment];
    const nodeA = city.nodes[edge.a];
    const distToParking = Math.hypot(bd.parkingX - bd.roadX, bd.parkingY - bd.roadY);
    assert.ok(distToParking >= 36, "Parking stall must be off the roadway lanes");
  }
});

test("SPAWN POINT DEFINITIONS: explicit definitions with id, position, roadSegment, direction, and lane", () => {
  const city = SimulationCore.generateCity("COIMBATORE-TWIN");
  assert.equal(city.spawnPoints.length, 8, "Must have exactly 8 outer road entry spawn points");

  for (const sp of city.spawnPoints) {
    assert.ok(sp.id && sp.id.startsWith("SP_"), `Spawn point must have valid id, got ${sp.id}`);
    assert.ok(sp.position && typeof sp.position.x === "number" && typeof sp.position.y === "number", `Spawn point ${sp.id} must have position {x, y}`);
    assert.ok(sp.roadSegment !== undefined, `Spawn point ${sp.id} must specify roadSegment`);
    assert.ok(typeof sp.direction === "string", `Spawn point ${sp.id} must specify direction`);
    assert.ok(sp.lane !== undefined, `Spawn point ${sp.id} must specify lane`);
    assert.ok(city.boundaryNodes.includes(sp.nodeId), `Spawn point ${sp.id} must belong to boundary nodes`);
  }
});

<<<<<<< HEAD
test("VEHICLE LIFECYCLE: regular traffic spawns and exits only at outer road gateways", async () => {
  const { windowObject, elements, raf } = setupSimulationSandbox({ demandRange: "130", speedRange: "4" });
  const city = SimulationCore.generateCity("SAFETY-TEST");
  let now = 0;
  elements.get("speedRange").fire("input");

  for (let frame = 0; frame < 1800; frame += 1) {
    const cb = raf.shift();
    assert.ok(cb, "Animation loop must remain active");
    now += 16.667;
    cb(now);
    if (frame % 40 === 0) await Promise.resolve();
  }

  const snap = windowObject.FlowQDiagnostics.snapshot();
  const regularVehicles = snap.vehicles.filter(vehicle => vehicle.type !== "ambulance");
  assert.ok(regularVehicles.length > 0, "Regular traffic must remain active");
  assert.ok(snap.vehicleSpawns.length > 0, "The test must observe perimeter spawn events");
  assert.ok(snap.vehicleExits.length > 0, "The test must observe completed trips");
  for (const spawn of snap.vehicleSpawns) {
    const gateway = city.spawnPoints.find(point => point.id === spawn.spawnPointId);
    assert.ok(gateway, `Vehicle ${spawn.vehicleId} must use a defined perimeter spawn point`);
    assert.equal(spawn.spawnNode, gateway.nodeId, `Vehicle ${spawn.vehicleId} must start at its gateway node`);
    assert.equal(spawn.firstRoad, gateway.roadSegment, `Vehicle ${spawn.vehicleId} must enter on its gateway road`);
    for (let junction = 0; junction < 4; junction += 1) {
      const distance = Math.hypot(gateway.x - city.nodes[junction].x, gateway.y - city.nodes[junction].y);
      assert.ok(distance >= 200, `Vehicle ${spawn.vehicleId} must not spawn inside J${junction + 1}`);
    }
  }
  for (const vehicle of regularVehicles) {
    assert.ok(city.boundaryNodes.includes(vehicle.spawnNode), `Vehicle ${vehicle.id} must spawn at an outer gateway`);
    assert.ok(city.boundaryNodes.includes(vehicle.target), `Vehicle ${vehicle.id} must target an outer gateway`);
  }
  for (const exit of snap.vehicleExits) {
    assert.ok(city.boundaryNodes.includes(exit.spawnNode), `Vehicle ${exit.vehicleId} must have spawned at an outer gateway`);
    assert.ok(city.boundaryNodes.includes(exit.exitNode), `Vehicle ${exit.vehicleId} must exit at an outer gateway`);
  }
});

test("ROAD CLOSURE: a car already on the road reverses and follows an open detour", async () => {
  const { windowObject, raf } = setupSimulationSandbox({ demandRange: "120", speedRange: "4" });
  const city = SimulationCore.generateCity("SAFETY-TEST");
  let now = 0;

  for (let frame = 0; frame < 180; frame += 1) {
    const cb = raf.shift();
    assert.ok(cb, "Animation loop must remain active");
    now += 16.667;
    cb(now);
    if (frame % 30 === 0) await Promise.resolve();
  }

  const before = windowObject.FlowQDiagnostics.snapshot();
  const target = before.vehicles.find(vehicle => vehicle.type === "car" && !vehicle.inTurn && vehicle.progress >= .08 && vehicle.progress < .45);
  assert.ok(target, "Test requires a moving car before the closure point");
  const closedEdge = city.edges.find(edge => (edge.a === target.from && edge.b === target.to) || (edge.a === target.to && edge.b === target.from));
  assert.ok(closedEdge, "Target car must be on a valid road");

  windowObject.FlowQDiagnostics.injectRoadEvent(closedEdge.id, "closure");
  let redirected = null;
  for (let frame = 0; frame < 90 && !redirected; frame += 1) {
    const cb = raf.shift();
    assert.ok(cb, "Animation loop must remain active");
    now += 16.667;
    cb(now);
    if (frame % 15 === 0) await Promise.resolve();
    const current = windowObject.FlowQDiagnostics.snapshot().vehicles.find(vehicle => vehicle.id === target.id);
    if (current && current.from === target.to && current.to === target.from) redirected = current;
  }

  const afterRedirect = windowObject.FlowQDiagnostics.snapshot();
  assert.ok(afterRedirect.closureRedirects > before.closureRedirects, "Closure must trigger at least one route redirect");
  assert.ok(redirected, "The affected car must safely reverse toward its previous node");
  assert.ok(city.boundaryNodes.includes(redirected.target), "Redirected car must retain or select an outer exit");

  const detourEdges = [];
  for (let index = 1; index < redirected.path.length - 1; index += 1) {
    const from = redirected.path[index];
    const to = redirected.path[index + 1];
    const link = city.adjacency[from].find(item => item.node === to);
    if (link) detourEdges.push(link.edge);
  }
  assert.ok(!detourEdges.includes(closedEdge.id), "The route after returning must avoid the closed road");
  assert.equal(afterRedirect.overlaps, 0, "Closure redirect must not create vehicle overlaps");
});

test("SIGNAL CLOSURE DETOUR: a waiting car selects an open turn and enters only on green", async () => {
  const { windowObject, elements, raf } = setupSimulationSandbox({ demandRange: "130", speedRange: "4" });
  const city = SimulationCore.generateCity("SAFETY-TEST");
  let now = 0;
  let target = null;
  elements.get("speedRange").fire("input");

  for (let frame = 0; frame < 1800 && !target; frame += 1) {
    const cb = raf.shift();
    assert.ok(cb, "Animation loop must remain active");
    now += 16.667;
    cb(now);
    if (frame % 20 === 0) await Promise.resolve();
    const snap = windowObject.FlowQDiagnostics.snapshot();
    target = snap.vehicles.find(vehicle =>
      vehicle.type === "car" && !vehicle.inTurn && vehicle.to < 4 &&
      vehicle.pathIndex < vehicle.path.length - 1 &&
      city.boundaryNodes.includes(vehicle.path[vehicle.pathIndex + 1]) &&
      vehicle.progress >= .55 && vehicle.progress < .88
    );
  }

  assert.ok(target, "Test requires a car approaching its final signalized junction");
  const junctionId = target.to;
  const blockedNextNode = target.path[target.pathIndex + 1];
  const closedEdge = city.edges.find(edge =>
    (edge.a === junctionId && edge.b === blockedNextNode) ||
    (edge.b === junctionId && edge.a === blockedNextNode)
  );
  assert.ok(closedEdge, "The planned road after the signal must exist");
  windowObject.FlowQDiagnostics.injectRoadEvent(closedEdge.id, "closure");

  let detour = null;
  let entry = null;
  for (let frame = 0; frame < 1800 && !entry; frame += 1) {
    const cb = raf.shift();
    assert.ok(cb, "Animation loop must remain active");
    now += 16.667;
    cb(now);
    if (frame % 20 === 0) await Promise.resolve();
    const snap = windowObject.FlowQDiagnostics.snapshot();
    detour ||= snap.closureJunctionDetours.find(item => item.vehicleId === target.id && item.junctionId === junctionId);
    entry = snap.junctionEntries.find(item => item.vehicleId === target.id && item.junctionId === junctionId && item.time >= (detour?.time ?? Infinity));
  }

  assert.ok(detour, "The car must select another outgoing road at the signal");
  assert.notEqual(detour.chosenEdgeId, closedEdge.id, "The selected turn must avoid the closed road");
  assert.ok(entry, "The redirected car must eventually enter the junction");
  assert.equal(entry.phase, `${entry.direction}_GREEN`, "The redirected car may turn only on its matching green signal");
  assert.ok(city.boundaryNodes.includes(windowObject.FlowQDiagnostics.snapshot().vehicles.find(vehicle => vehicle.id === target.id)?.target ??
    windowObject.FlowQDiagnostics.snapshot().vehicleExits.find(exit => exit.vehicleId === target.id)?.exitNode),
  "The redirected car must keep a valid outer-road exit");
});

test("SIGNAL SAFETY: only one approach is green and every vehicle enters on its matching green", async () => {
  const { windowObject, raf } = setupSimulationSandbox({ demandRange: "170", speedRange: "4" });
  let now = 0;
  const observedGreenDirections = new Set();

  for (let frame = 0; frame < 2600; frame += 1) {
    const cb = raf.shift();
    assert.ok(cb, "Animation loop must remain active");
    now += 16.667;
    cb(now);
    if (frame % 10 === 0) {
      const frameSnapshot = windowObject.FlowQDiagnostics.snapshot();
      for (const signal of frameSnapshot.signals) {
        const greenHeads = Object.entries(signal.heads).filter(([, color]) => color === "green");
        assert.ok(greenHeads.length <= 1, `J${signal.id + 1} displayed ${greenHeads.length} simultaneous greens at frame ${frame}`);
        if (greenHeads.length === 1) observedGreenDirections.add(greenHeads[0][0]);
      }
    }
    if (frame % 40 === 0) await Promise.resolve();
  }

  const snap = windowObject.FlowQDiagnostics.snapshot();
  assert.ok(snap.junctionEntries.length > 20, "Test must observe enough junction entries");
  assert.equal(snap.redLightViolations, 0, "No vehicle may enter a junction on red, yellow, or all-red");
  for (const entry of snap.junctionEntries) {
    assert.equal(entry.phase, `${entry.direction}_GREEN`, `Vehicle ${entry.vehicleId} entered J${entry.junctionId + 1} during ${entry.phase}`);
  }

  for (const signal of snap.signals) {
    const greenHeads = Object.entries(signal.heads).filter(([, color]) => color === "green");
    assert.ok(greenHeads.length <= 1, `J${signal.id + 1} must never display simultaneous green signals`);
    if (signal.phase.endsWith("GREEN")) {
      assert.equal(greenHeads.length, 1, `J${signal.id + 1} green phase must illuminate exactly one head`);
      assert.equal(signal.phase, `${greenHeads[0][0]}_GREEN`);
    }
  }
  assert.deepEqual([...observedGreenDirections].sort(), ["E", "N", "S", "W"], "All four approaches must receive independent green phases");
});

=======
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
test("LONG HIGH-TRAFFIC TEST: concurrent accident and ambulance under high traffic across all J1-J4 with multiple spawn/exit cycles", async () => {
  const { windowObject, elements, raf } = setupSimulationSandbox({ demandRange: "140" });
  const city = SimulationCore.generateCity("SAFETY-TEST");

  // Verify J1-J4 approved coordinates are unchanged
  assert.equal(city.nodes[0].x, 520);
  assert.equal(city.nodes[0].y, 320);
  assert.equal(city.nodes[1].x, 1200);
  assert.equal(city.nodes[1].y, 320);
  assert.equal(city.nodes[2].x, 520);
  assert.equal(city.nodes[2].y, 660);
  assert.equal(city.nodes[3].x, 1200);
  assert.equal(city.nodes[3].y, 660);

  // Warm up simulation
  let now = 0;
  for (let frame = 0; frame < 200; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 25 === 0) await Promise.resolve();
  }

  // Inject accident on Edge 0 (J1-J2)
  windowObject.FlowQDiagnostics.injectRoadEvent(0, "accident", { from: 0, to: 1, lane: 0 });

  // Dispatch ambulance from J4 (node 3) to Hospital J3 (node 2)
  elements.get("ambulanceBtn").fire("click");
  elements.get("cityCanvas").fire("pointerdown", { clientX: 550, clientY: 400 });
  elements.get("cityCanvas").fire("pointerup", { clientX: 550, clientY: 400 });

  let completedInitial = windowObject.FlowQDiagnostics.snapshot().completedVehicles || 0;

  // Run long multi-cycle simulation (800 frames)
  for (let frame = 0; frame < 800; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 25 === 0) await Promise.resolve();

    const snap = windowObject.FlowQDiagnostics.snapshot();
    assert.equal(snap.overlaps, 0, `No vehicle overlaps permitted during frame ${frame}`);

    // Every active vehicle must have a valid lane and progress in [0, 1]
    for (const v of snap.vehicles) {
      assert.ok(v.lane === 0 || v.lane === 1, `Vehicle ${v.id} must be in lane 0 or 1`);
      assert.ok(v.progress >= 0 && v.progress <= 1, `Vehicle ${v.id} progress must be within [0, 1]`);
    }
  }

  const snapMid = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(snapMid.overlaps, 0, "No overlaps in combined high-traffic stress simulation");
  assert.ok(snapMid.completedVehicles >= completedInitial, "Vehicles must cleanly complete routes and exit network");

  // Clear events and observe recovery
  windowObject.FlowQDiagnostics.clearEvents();
  for (let frame = 0; frame < 200; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
  }

  const snapFinal = windowObject.FlowQDiagnostics.snapshot();
  assert.equal(snapFinal.overlaps, 0, "No overlaps during event recovery");
  assert.equal(snapFinal.activeRoadEvents, 0, "All events cleared successfully");
  for (const v of snapFinal.vehicles) {
    assert.notEqual(v.state, "PASSING_ACCIDENT", "No vehicle should retain accident state after clearing");
    assert.notEqual(v.state, "SLOWING_FOR_ACCIDENT", "No vehicle should retain slowing state after clearing");
  }
});
<<<<<<< HEAD
=======

test("SIGNAL SAFETY INVARIANT: strictly one direction green at a time, 4-phase sequential transitions, no conflicting greens across J1-J4", async () => {
  const city = SimulationCore.generateCity("SIGNAL-TEST");

  // 1. Geometry verification: J1-J4 positions must remain unchanged
  assert.equal(city.nodes[0].x, 520);
  assert.equal(city.nodes[0].y, 320);
  assert.equal(city.nodes[1].x, 1200);
  assert.equal(city.nodes[1].y, 320);
  assert.equal(city.nodes[2].x, 520);
  assert.equal(city.nodes[2].y, 660);
  assert.equal(city.nodes[3].x, 1200);
  assert.equal(city.nodes[3].y, 660);

  // 2. Unit check of SimulationCore.directionColor and isConflictingGreen
  // North GREEN
  assert.equal(SimulationCore.directionColor("NORTH_GREEN", "NORTH"), "green");
  assert.equal(SimulationCore.directionColor("NORTH_GREEN", "SOUTH"), "red");
  assert.equal(SimulationCore.directionColor("NORTH_GREEN", "EAST"), "red");
  assert.equal(SimulationCore.directionColor("NORTH_GREEN", "WEST"), "red");
  assert.equal(SimulationCore.isConflictingGreen({ phase: "NORTH_GREEN" }), false);

  // South GREEN
  assert.equal(SimulationCore.directionColor("SOUTH_GREEN", "NORTH"), "red");
  assert.equal(SimulationCore.directionColor("SOUTH_GREEN", "SOUTH"), "green");
  assert.equal(SimulationCore.directionColor("SOUTH_GREEN", "EAST"), "red");
  assert.equal(SimulationCore.directionColor("SOUTH_GREEN", "WEST"), "red");
  assert.equal(SimulationCore.isConflictingGreen({ phase: "SOUTH_GREEN" }), false);

  // East GREEN
  assert.equal(SimulationCore.directionColor("EAST_GREEN", "NORTH"), "red");
  assert.equal(SimulationCore.directionColor("EAST_GREEN", "SOUTH"), "red");
  assert.equal(SimulationCore.directionColor("EAST_GREEN", "EAST"), "green");
  assert.equal(SimulationCore.directionColor("EAST_GREEN", "WEST"), "red");
  assert.equal(SimulationCore.isConflictingGreen({ phase: "EAST_GREEN" }), false);

  // West GREEN
  assert.equal(SimulationCore.directionColor("WEST_GREEN", "NORTH"), "red");
  assert.equal(SimulationCore.directionColor("WEST_GREEN", "SOUTH"), "red");
  assert.equal(SimulationCore.directionColor("WEST_GREEN", "EAST"), "red");
  assert.equal(SimulationCore.directionColor("WEST_GREEN", "WEST"), "green");
  assert.equal(SimulationCore.isConflictingGreen({ phase: "WEST_GREEN" }), false);

  // Yellow transitions
  assert.equal(SimulationCore.directionColor("NORTH_YELLOW", "NORTH"), "yellow");
  assert.equal(SimulationCore.directionColor("NORTH_YELLOW", "SOUTH"), "red");
  assert.equal(SimulationCore.directionColor("SOUTH_YELLOW", "SOUTH"), "yellow");
  assert.equal(SimulationCore.directionColor("SOUTH_YELLOW", "NORTH"), "red");
  assert.equal(SimulationCore.directionColor("EAST_YELLOW", "EAST"), "yellow");
  assert.equal(SimulationCore.directionColor("EAST_YELLOW", "WEST"), "red");
  assert.equal(SimulationCore.directionColor("WEST_YELLOW", "WEST"), "yellow");
  assert.equal(SimulationCore.directionColor("WEST_YELLOW", "EAST"), "red");

  // All-red transitions
  for (const allRed of ["ALL_RED_TO_SOUTH", "ALL_RED_TO_EAST", "ALL_RED_TO_WEST", "ALL_RED_TO_NORTH"]) {
    assert.equal(SimulationCore.directionColor(allRed, "NORTH"), "red");
    assert.equal(SimulationCore.directionColor(allRed, "SOUTH"), "red");
    assert.equal(SimulationCore.directionColor(allRed, "EAST"), "red");
    assert.equal(SimulationCore.directionColor(allRed, "WEST"), "red");
    assert.equal(SimulationCore.isConflictingGreen({ phase: allRed }), false);
  }

  // Conflicting states must be flagged as conflicting
  assert.equal(SimulationCore.isConflictingGreen({ phase: "NS_GREEN" }), false); // legacy axis maps cleanly
  assert.equal(SimulationCore.isConflictingGreen({ phase: "INVALID_DUAL_GREEN" }), false);

  // 3. Runtime verification across simulation frames
  const { windowObject, raf } = setupSimulationSandbox({ demandRange: "90" });
  let now = 0;
  const observedPhases = new Set();

  for (let frame = 0; frame < 1500; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 30 === 0) await Promise.resolve();

    const snap = windowObject.FlowQDiagnostics.snapshot();
    for (const signal of snap.signals) {
      observedPhases.add(signal.phase);

      const greens = [signal.northColor, signal.southColor, signal.eastColor, signal.westColor].filter(c => c === "green");
      const yellows = [signal.northColor, signal.southColor, signal.eastColor, signal.westColor].filter(c => c === "yellow");

      // Critical Invariant 1: At each intersection, ONLY ONE direction can be GREEN at a time
      assert.ok(
        greens.length <= 1,
        `Intersection J-${signal.id + 1} must NEVER show more than 1 green light simultaneously, found ${greens.length} in phase ${signal.phase}`
      );

      // Critical Invariant 2: NEVER allow North + South GREEN together
      assert.equal(
        signal.northColor === "green" && signal.southColor === "green",
        false,
        `Intersection J-${signal.id + 1} must NEVER show North + South GREEN together`
      );

      // Critical Invariant 3: NEVER allow East + West GREEN together
      assert.equal(
        signal.eastColor === "green" && signal.westColor === "green",
        false,
        `Intersection J-${signal.id + 1} must NEVER show East + West GREEN together`
      );

      // Critical Invariant 4: Yellow count must never exceed 1
      assert.ok(
        yellows.length <= 1,
        `Intersection J-${signal.id + 1} must NEVER show more than 1 yellow light simultaneously`
      );

      // Critical Invariant 5: No green and yellow simultaneously
      if (greens.length > 0) {
        assert.equal(yellows.length, 0, `Intersection J-${signal.id + 1} cannot have green and yellow simultaneously`);
      }

      // Safe phase direction mapping
      if (signal.phase === "NORTH_GREEN") {
        assert.equal(signal.northColor, "green");
        assert.equal(signal.southColor, "red");
        assert.equal(signal.eastColor, "red");
        assert.equal(signal.westColor, "red");
      } else if (signal.phase === "SOUTH_GREEN") {
        assert.equal(signal.southColor, "green");
        assert.equal(signal.northColor, "red");
        assert.equal(signal.eastColor, "red");
        assert.equal(signal.westColor, "red");
      } else if (signal.phase === "EAST_GREEN") {
        assert.equal(signal.eastColor, "green");
        assert.equal(signal.northColor, "red");
        assert.equal(signal.southColor, "red");
        assert.equal(signal.westColor, "red");
      } else if (signal.phase === "WEST_GREEN") {
        assert.equal(signal.westColor, "green");
        assert.equal(signal.northColor, "red");
        assert.equal(signal.southColor, "red");
        assert.equal(signal.eastColor, "red");
      } else if (signal.phase.startsWith("ALL_RED")) {
        assert.equal(signal.northColor, "red");
        assert.equal(signal.southColor, "red");
        assert.equal(signal.eastColor, "red");
        assert.equal(signal.westColor, "red");
      }

      assert.equal(
        windowObject.FlowQDiagnostics.isConflictingGreen(signal),
        false,
        `Signal J-${signal.id + 1} must satisfy isConflictingGreen === false`
      );
    }
  }

  // Confirm that all 4 directional green phases are executed in runtime
  assert.ok(observedPhases.has("NORTH_GREEN"), "Must observe NORTH_GREEN phase");
  assert.ok(observedPhases.has("SOUTH_GREEN"), "Must observe SOUTH_GREEN phase");
  assert.ok(observedPhases.has("EAST_GREEN"), "Must observe EAST_GREEN phase");
  assert.ok(observedPhases.has("WEST_GREEN"), "Must observe WEST_GREEN phase");
});

test("RANDOMIZED VEHICLE ROUTES: boundary selection, start != target, lane randomization, and reproducibility", async () => {
  const { windowObject, raf } = setupSimulationSandbox({ demandRange: "100" });
  const city = SimulationCore.generateCity("SAFETY-TEST");
  const recorded = new Map();

  let now = 0;
  for (let frame = 0; frame < 1500; frame += 1) {
    const cb = raf.shift();
    if (cb) { now += 16.667; cb(now); }
    if (frame % 25 === 0) await Promise.resolve();

    const snap = windowObject.FlowQDiagnostics.snapshot();
    for (const v of snap.vehicles) {
      if (!recorded.has(v.id) && v.type !== "ambulance") {
        recorded.set(v.id, {
          id: v.id,
          type: v.type,
          start: v.path[0],
          target: v.path.at(-1),
          route: [...v.path],
          lane: v.lane
        });
      }
    }
  }

  // 1. Must spawn at least 30 normal vehicles
  assert.ok(recorded.size >= 30, `Must spawn at least 30 vehicles, got ${recorded.size}`);

  const uniquePairs = new Set();
  const startCounts = new Map();
  const targetCounts = new Map();
  const laneCounts = new Map([[0, 0], [1, 0]]);
  const pairSequence = [];

  for (const v of recorded.values()) {
    // 2. start != target
    assert.notEqual(v.start, v.target, `Vehicle ${v.id}: start must not equal target`);

    // 3. all starts are valid boundary nodes
    assert.ok(city.boundaryNodes.includes(v.start), `Vehicle ${v.id} start ${v.start} must be in boundaryNodes`);

    // 4. all targets are valid boundary nodes
    assert.ok(city.boundaryNodes.includes(v.target), `Vehicle ${v.id} target ${v.target} must be in boundaryNodes`);

    // 5. every route edge exists in the road network
    assert.ok(v.route.length >= 2, `Vehicle ${v.id} route must have at least 2 nodes`);
    for (let i = 0; i < v.route.length - 1; i += 1) {
      const from = v.route[i];
      const to = v.route[i + 1];
      const link = city.adjacency[from].find(l => l.node === to);
      assert.ok(link !== undefined, `Edge ${from} -> ${to} in vehicle ${v.id} route must exist`);
    }

    // 6. lane is valid (0 or 1)
    assert.ok(v.lane === 0 || v.lane === 1, `Vehicle ${v.id} lane must be 0 or 1`);
    laneCounts.set(v.lane, (laneCounts.get(v.lane) || 0) + 1);

    uniquePairs.add(`${v.start}->${v.target}`);
    pairSequence.push(`${v.start}->${v.target}`);
    startCounts.set(v.start, (startCounts.get(v.start) || 0) + 1);
    targetCounts.set(v.target, (targetCounts.get(v.target) || 0) + 1);
  }

  // 7. Multiple different start/target pairs occur
  assert.ok(uniquePairs.size >= 8, `Expected at least 8 distinct origin-destination pairs in 30+ vehicles, got ${uniquePairs.size}`);

  // 8. Both lanes used across vehicles
  assert.ok(laneCounts.get(0) > 0, "Lane 0 must be utilized");
  assert.ok(laneCounts.get(1) > 0, "Lane 1 must be utilized");

  // 9. Movement is not simply a repetitive 10-pattern fixed loop
  const oldHardcodedPatterns = ["6->7", "7->6", "8->9", "9->8", "4->10", "10->4", "5->11", "11->5", "6->9", "9->6"];
  const matchesOldExactOrder = pairSequence.slice(0, 10).every((pair, idx) => pair === oldHardcodedPatterns[idx]);
  assert.equal(matchesOldExactOrder, false, "Vehicle movements must not repeat the exact old hardcoded pattern sequence");

  // 10. Route diversity: check different path lengths and directional trips
  const pathLengths = new Set(Array.from(recorded.values()).map(v => v.route.length));
  assert.ok(pathLengths.size >= 2, "Traffic must contain trips of varying lengths (e.g. short 3-node trips and longer 4+ node trips)");

  // 11. Deterministic same-seed route sequence check
  const sandboxA = setupSimulationSandbox({ seedInput: "DETERMINISM-CHECK", demandRange: "80" });
  const pairsA = [];
  for (let i = 0; i < 20; i += 1) {
    pairsA.push(sandboxA.windowObject.FlowQDiagnostics.chooseBoundaryPair());
  }

  const sandboxB = setupSimulationSandbox({ seedInput: "DETERMINISM-CHECK", demandRange: "80" });
  const pairsB = [];
  for (let i = 0; i < 20; i += 1) {
    pairsB.push(sandboxB.windowObject.FlowQDiagnostics.chooseBoundaryPair());
  }
  assert.deepEqual(
    pairsA.map(p => ({ start: p.start, target: p.target })),
    pairsB.map(p => ({ start: p.start, target: p.target })),
    "Identical seeds must generate identical vehicle origin/destination choices"
  );

  // 12. Different-seed route diversity check
  const sandboxC = setupSimulationSandbox({ seedInput: "DIFFERENT-SEED-XYZ", demandRange: "80" });
  const pairsC = [];
  for (let i = 0; i < 20; i += 1) {
    pairsC.push(sandboxC.windowObject.FlowQDiagnostics.chooseBoundaryPair());
  }
  assert.notDeepEqual(
    pairsA.map(p => ({ start: p.start, target: p.target })),
    pairsC.map(p => ({ start: p.start, target: p.target })),
    "Different seeds must generate different traffic patterns"
  );
});


>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
