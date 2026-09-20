"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { solveQubo, isValidTiming } = require("../public/optimizer.js");
const {
  generateCity,
  shortestPath,
  diversePath,
  chooseRandomBoundaryPair,
  mulberry32
} = require("../public/simulation-core.js");

test("seed creates deterministic 4-intersection arterial network with perimeter gateways", () => {
  const first = generateCity("cybroatrix-42");
  const second = generateCity("cybroatrix-42");
  assert.equal(first.nodes.filter(n => n.isPrimary).length, 4);
  assert.equal(first.nodes.length, 12);
  assert.equal(first.edges.length, 12);
  assert.deepEqual(first.nodes, second.nodes);
  assert.deepEqual(first.blocks, second.blocks);
});

test("different seeds create different road and building geometry", () => {
  const first = generateCity("seed-one");
  const second = generateCity("seed-two");
  assert.notDeepEqual(first.nodes, second.nodes);
  assert.notDeepEqual(first.blocks, second.blocks);
});

test("every generated city has a route across the network", () => {
  const city = generateCity("route-test");
  const route = shortestPath(city, 0, 7);
  assert.equal(route[0], 0);
  assert.equal(route.at(-1), 7);
  assert.ok(route.length >= 3);
});

test("random demand uses every gateway and multiple valid paths", () => {
  const city = generateCity("random-route-test");
  const random = mulberry32(city.numericSeed ^ 0x51adbeef);
  const gateways = new Set();
  const pairs = new Set();
  const routes = new Set();
  let previous = null;

  for (let index = 0; index < 240; index += 1) {
    const pair = chooseRandomBoundaryPair(city, random, previous);
    assert.notDeepEqual(pair, previous, "Consecutive origin/destination pairs must not repeat");
    assert.ok(city.boundaryNodes.includes(pair.start));
    assert.ok(city.boundaryNodes.includes(pair.target));
    assert.notEqual(pair.start, pair.target);

    const route = diversePath(city, pair.start, pair.target, new Set(), [], random);
    assert.equal(route[0], pair.start);
    assert.equal(route.at(-1), pair.target);
    for (let step = 1; step < route.length; step += 1) {
      assert.ok(city.adjacency[route[step - 1]].some(link => link.node === route[step]), "Every route step must follow a real road");
    }

    gateways.add(pair.start);
    gateways.add(pair.target);
    pairs.add(`${pair.start}>${pair.target}`);
    routes.add(route.join("-"));
    previous = pair;
  }

  assert.equal(gateways.size, city.boundaryNodes.length, "Random demand must use all eight gateways");
  assert.ok(pairs.size >= 40, "Demand must cover a broad set of origin/destination pairs");
  assert.ok(routes.size >= 45, "Vehicles must use a broad mix of valid network paths");
});

test("random routing never includes a closed road when a detour exists", () => {
  const city = generateCity("closure-detour-test");
  const blockedEdge = city.edges[0];
  const blocked = new Set([blockedEdge.key]);
  const random = mulberry32(12345);

  for (let index = 0; index < 40; index += 1) {
    const route = diversePath(city, 6, 7, blocked, [], random);
    assert.equal(route[0], 6);
    assert.equal(route.at(-1), 7);
    for (let step = 1; step < route.length; step += 1) {
      const link = city.adjacency[route[step - 1]].find(item => item.node === route[step]);
      assert.ok(link, "Detour must stay on the road graph");
      assert.notEqual(city.edges[link.edge].key, blockedEdge.key, "Detour must exclude the closed road");
    }
  }
});

test("QUBO timing stays inside supplied Python model constraints", () => {
  const decision = solveQubo({ intersectionId: 4, nsQueue: 18, ewQueue: 4, pedestrianQueue: 7, trafficDensity: 0.42, vehicleCount: 28, roadCapacity: 48 });
  assert.ok(isValidTiming(decision.nsGreen, decision.ewGreen));
  assert.equal(decision.method, "QUBO exact");
  assert.ok(decision.nsGreen >= decision.ewGreen);
  assert.equal(decision.candidatesEvaluated, 9);
});

test("QUBO solver accepts canonical TrafficObservation contract", () => {
  const canonicalObservation = {
    timestamp: 1234567.89,
    source: "yolov8",
    intersection_id: "J1",
    vehicle_count: 22,
    tracked_vehicle_count: 22,
    average_confidence: 0.91,
    approach_counts: { north: 10, south: 4, east: 5, west: 3 },
    queue_lengths: { north: 12, south: 6, east: 2, west: 2 },
    class_counts: { car: 18, motorcycle: 2, bus: 1, truck: 1 },
    tracking_available: true
  };
  const decision = solveQubo(canonicalObservation);
  assert.ok(isValidTiming(decision.nsGreen, decision.ewGreen));
  assert.equal(decision.method, "QUBO exact");
  assert.equal(decision.intersectionId, "J1");
  assert.ok(decision.nsGreen >= decision.ewGreen);
});
