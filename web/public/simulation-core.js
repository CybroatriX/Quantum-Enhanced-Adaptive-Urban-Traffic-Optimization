(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SimulationCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function hashSeed(value) {
    const text = String(value || "42");
    let hash = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function mulberry32(seed) {
    let value = seed >>> 0;
    return function random() {
      let t = value += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function distance(a, b) { return Math.hypot(b.x - a.x, b.y - a.y); }
  function edgeKey(a, b) { return a < b ? `${a}-${b}` : `${b}-${a}`; }

  /*
   * 4-intersection 2x2 urban arterial network:
   * J1 ---- J2
   *  |       |
   *  |       |
   * J3 ---- J4
   * With dual-carriageway directional roads (2 lanes per direction)
   * and perimeter external approaches around the network perimeter.
   */
  function generateCity(seedValue) {
    const seed = hashSeed(seedValue);
    const random = mulberry32(seed);
    const world = { width: 1720, height: 940 };

    // 4 primary signalized intersections (J1-J4) in a 2x2 grid
    // + 8 perimeter approach gateways on the outer perimeter
    const nodes = [
      // Primary signalized intersections (J1 - J4)
      { id: 0, x: 520, y: 320, name: "J1 Harbor Gate", boundary: false, isPrimary: true, pedestrianDemand: .32 + random() * .35 },
      { id: 1, x: 1200, y: 320, name: "J2 Civic Square", boundary: false, isPrimary: true, pedestrianDemand: .32 + random() * .35 },
      { id: 2, x: 520, y: 660, name: "J3 Market Circle", boundary: false, isPrimary: true, pedestrianDemand: .32 + random() * .35 },
      { id: 3, x: 1200, y: 660, name: "J4 Tech Park", boundary: false, isPrimary: true, pedestrianDemand: .32 + random() * .35 },
      // Perimeter approach gateways (incoming / outgoing)
      { id: 4, x: 520, y: 70, name: "North Gateway 1", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 5, x: 1200, y: 70, name: "North Gateway 2", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 6, x: 120, y: 320, name: "West Gateway 1", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 7, x: 1600, y: 320, name: "East Gateway 1", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 8, x: 120, y: 660, name: "West Gateway 2", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 9, x: 1600, y: 660, name: "East Gateway 2", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 10, x: 520, y: 870, name: "South Gateway 1", boundary: true, isPrimary: false, pedestrianDemand: .12 },
      { id: 11, x: 1200, y: 870, name: "South Gateway 2", boundary: true, isPrimary: false, pedestrianDemand: .12 }
    ];

    // 12 bidirectional road corridors:
    // 4 internal arterials connecting J1-J4 + 8 perimeter approaches
    const definitions = [
      [0, 1, "arterial"], // 0: J1 <-> J2 (North Arterial)
      [2, 3, "arterial"], // 1: J3 <-> J4 (South Arterial)
      [0, 2, "arterial"], // 2: J1 <-> J3 (West Connector)
      [1, 3, "arterial"], // 3: J2 <-> J4 (East Connector)
      [0, 4, "arterial"], // 4: J1 <-> North Gateway 1
      [1, 5, "arterial"], // 5: J2 <-> North Gateway 2
      [0, 6, "arterial"], // 6: J1 <-> West Gateway 1
      [1, 7, "arterial"], // 7: J2 <-> East Gateway 1
      [2, 8, "arterial"], // 8: J3 <-> West Gateway 2
      [3, 9, "arterial"], // 9: J4 <-> East Gateway 2
      [2, 10, "arterial"], // 10: J3 <-> South Gateway 1
      [3, 11, "arterial"]  // 11: J4 <-> South Gateway 2
    ];

    const edges = [];
    const adjacency = Array.from({ length: nodes.length }, () => []);
    definitions.forEach(([a, b, roadClass], id) => {
      const first = nodes[a];
      const second = nodes[b];
      const lanes = 2; // 2 lanes per direction
      const speed = 25;
      const dx = second.x - first.x;
      const dy = second.y - first.y;
      const edge = {
        id,
        key: edgeKey(a, b),
        a,
        b,
        orientation: Math.abs(dx) >= Math.abs(dy) ? "horizontal" : "vertical",
        roadClass,
        lanes,
        speed,
        capacity: 68,
        length: distance(first, second),
        curve: 0
      };
      edges.push(edge);
      adjacency[a].push({ node: b, edge: id });
      adjacency[b].push({ node: a, edge: id });
    });

    // Rectangular urban city blocks arranged neatly around the road corridors
    const blocks = [];
    const blockSeeds = [
      [150, 90, 310, 170],   // 0: NW sector
      [580, 90, 270, 170],   // 1: N-mid-west
      [870, 90, 270, 170],   // 2: N-mid-east
      [1260, 90, 310, 170],  // 3: NE sector
      [150, 380, 310, 220],  // 4: W-mid sector
      [580, 380, 270, 220],  // 5: Central plaza / park
      [870, 380, 270, 220],  // 6: Central commercial
      [1260, 380, 310, 220], // 7: E-mid sector
      [150, 720, 310, 130],  // 8: SW sector
      [580, 720, 270, 130],  // 9: S-mid-west
      [870, 720, 270, 130],  // 10: S-mid-east
      [1260, 720, 310, 130]  // 11: SE sector
    ];
    const blockLabels = [
      "Residential Area",           // 0: NW sector
      "Office Zone",                // 1: N-mid-west
      "Commercial Area",            // 2: N-mid-east
      "Shopping Area",              // 3: NE sector
      "Market District",            // 4: W-mid sector
      "Central Park & Greenery",    // 5: Central plaza / park
      "Commercial Zone",            // 6: Central commercial
      "Office Zone",                // 7: E-mid sector
      "Residential Area",           // 8: SW sector
      "Shopping Area",              // 9: S-mid-west
      "Urban Market",               // 10: S-mid-east
      "Tech Park"                   // 11: SE sector
    ];

    blockSeeds.forEach(([x, y, width, height], id) => {
      const park = id === 5 || (id === 1 && random() < .25);
      const buildings = [];
      if (!park) {
        const count = 2 + Math.floor(random() * 3);
        for (let index = 0; index < count; index += 1) {
          const w = 45 + random() * Math.max(30, width * .34);
          const h = 35 + random() * Math.max(25, height * .32);
          buildings.push({
            x: x + 14 + random() * Math.max(1, width - w - 28),
            y: y + 12 + random() * Math.max(1, height - h - 24),
            width: w,
            height: h,
            rotation: (random() - .5) * .04,
            floors: 3 + Math.floor(random() * 12),
            tone: Math.floor(random() * 4)
          });
        }
      }
      blocks.push({ id, minX: x, minY: y, width, height, park, label: blockLabels[id], buildings });
    });

    // 8 explicit outer road entry spawn points
    const spawnPoints = [
      { id: "SP_N1", nodeId: 4, name: "North Gateway 1", toNode: 0, roadSegment: 4, direction: "southbound", lane: 0, lanes: [0, 1], x: 520, y: 70, position: { x: 520, y: 70 } },
      { id: "SP_N2", nodeId: 5, name: "North Gateway 2", toNode: 1, roadSegment: 5, direction: "southbound", lane: 0, lanes: [0, 1], x: 1200, y: 70, position: { x: 1200, y: 70 } },
      { id: "SP_W1", nodeId: 6, name: "West Gateway 1", toNode: 0, roadSegment: 6, direction: "eastbound", lane: 0, lanes: [0, 1], x: 120, y: 320, position: { x: 120, y: 320 } },
      { id: "SP_E1", nodeId: 7, name: "East Gateway 1", toNode: 1, roadSegment: 7, direction: "westbound", lane: 0, lanes: [0, 1], x: 1600, y: 320, position: { x: 1600, y: 320 } },
      { id: "SP_W2", nodeId: 8, name: "West Gateway 2", toNode: 2, roadSegment: 8, direction: "eastbound", lane: 0, lanes: [0, 1], x: 120, y: 660, position: { x: 120, y: 660 } },
      { id: "SP_E2", nodeId: 9, name: "East Gateway 2", toNode: 3, roadSegment: 9, direction: "westbound", lane: 0, lanes: [0, 1], x: 1600, y: 660, position: { x: 1600, y: 660 } },
      { id: "SP_S1", nodeId: 10, name: "South Gateway 1", toNode: 2, roadSegment: 10, direction: "northbound", lane: 0, lanes: [0, 1], x: 520, y: 870, position: { x: 520, y: 870 } },
      { id: "SP_S2", nodeId: 11, name: "South Gateway 2", toNode: 3, roadSegment: 11, direction: "northbound", lane: 0, lanes: [0, 1], x: 1200, y: 870, position: { x: 1200, y: 870 } }
    ];

    // Controlled building driveway access locations
    const buildingDriveways = [
      {
        id: "BD_NORTH_TECH",
        name: "Tech Park Commercial Parking",
        roadSegment: 0,
        fromNode: 0,
        toNode: 1,
        direction: "eastbound",
        roadX: 780,
        roadY: 348,
        curbX: 780,
        curbY: 356,
        parkingX: 780,
        parkingY: 416,
        angle: Math.PI / 2
      },
      {
        id: "BD_SOUTH_MALL",
        name: "Avanashi City Mall Parking",
        roadSegment: 1,
        fromNode: 3,
        toNode: 2,
        direction: "westbound",
        roadX: 940,
        roadY: 632,
        curbX: 940,
        curbY: 624,
        parkingX: 940,
        parkingY: 564,
        angle: -Math.PI / 2
      }
    ];

    return {
      seed: String(seedValue),
      numericSeed: seed,
      world,
      nodes,
      edges,
      adjacency,
      blocks,
      boundaryNodes: [4, 5, 6, 7, 8, 9, 10, 11],
      spawnPoints,
      buildingDriveways
    };
  }

  function shortestPath(city, start, goal, blocked = new Set(), edgeCosts = null) {
    if (start === goal) return [start];
    const distances = Array(city.nodes.length).fill(Infinity);
    const previous = Array(city.nodes.length).fill(-1);
    const visited = new Set();
    distances[start] = 0;
    while (visited.size < city.nodes.length) {
      let current = -1;
      let best = Infinity;
      for (let id = 0; id < distances.length; id += 1) {
        if (!visited.has(id) && distances[id] < best) { best = distances[id]; current = id; }
      }
      if (current < 0 || current === goal) break;
      visited.add(current);
      for (const link of city.adjacency[current]) {
        const edge = city.edges[link.edge];
        if (blocked.has(edge.key)) continue;
        const dynamic = edgeCosts ? Number(edgeCosts[edge.id] || 0) : 0;
        const cost = edge.length / edge.speed + dynamic;
        if (distances[current] + cost < distances[link.node]) {
          distances[link.node] = distances[current] + cost;
          previous[link.node] = current;
        }
      }
    }
    if (!Number.isFinite(distances[goal])) return [];
    const path = [];
    for (let at = goal; at >= 0; at = previous[at]) {
      path.push(at);
      if (at === start) break;
    }
    return path.reverse();
  }

  function pathEdges(city, path) {
    const ids = [];
    for (let index = 1; index < path.length; index += 1) {
      const link = city.adjacency[path[index - 1]].find(item => item.node === path[index]);
      if (link) ids.push(link.edge);
    }
    return ids;
  }

  function routeCost(city, path, congestion = []) {
    return pathEdges(city, path).reduce((sum, edgeId) => {
      const edge = city.edges[edgeId];
      return sum + edge.length / edge.speed + Number(congestion[edgeId] || 0);
    }, 0);
  }

  function candidatePaths(city, start, goal, blocked = new Set(), maxHops = 8) {
    if (start === goal) return [[start]];
    const paths = [];
    const visited = new Set([start]);
    const path = [start];

    function visit(node) {
      if (path.length - 1 > maxHops) return;
      if (node === goal) {
        paths.push([...path]);
        return;
      }
      for (const link of city.adjacency[node]) {
        const edge = city.edges[link.edge];
        if (blocked.has(edge.key) || visited.has(link.node)) continue;
        visited.add(link.node);
        path.push(link.node);
        visit(link.node);
        path.pop();
        visited.delete(link.node);
      }
    }

    visit(start);
    return paths;
  }

  function chooseRandomBoundaryPair(city, random = Math.random, previousPair = null) {
    const boundary = city.boundaryNodes || city.nodes.filter(node => node.boundary).map(node => node.id);
    if (boundary.length < 2) return { start: -1, target: -1 };

    const allPairs = [];
    for (const start of boundary) {
      for (const target of boundary) {
        if (start === target) continue;
        if (previousPair && previousPair.start === start && previousPair.target === target) continue;
        allPairs.push({ start, target });
      }
    }
    const pool = allPairs.length ? allPairs : boundary.flatMap(start =>
      boundary.filter(target => target !== start).map(target => ({ start, target }))
    );
    return pool[Math.floor(random() * pool.length) % pool.length];
  }

  function diversePath(city, start, goal, blocked = new Set(), congestion = [], random = Math.random) {
    const base = shortestPath(city, start, goal, blocked, congestion);
    if (base.length < 2) return base;
    const baseCost = routeCost(city, base, congestion);
    const maxHops = Math.min(Math.max(base.length + 3, 6), city.nodes.length - 1);
    const enumerated = candidatePaths(city, start, goal, blocked, maxHops);
    const reasonable = enumerated
      .map(path => ({ path, cost: routeCost(city, path, congestion) }))
      .filter(item => item.cost <= baseCost * 2.35 + 1)
      .sort((a, b) => a.cost - b.cost)
      .slice(0, 8);

    if (!reasonable.length) return base;

    // Weighted random selection keeps most cars on efficient routes while
    // still distributing traffic across valid alternatives and districts.
    const scale = Math.max(1, baseCost * .35);
    const weighted = reasonable.map(item => ({
      ...item,
      weight: Math.exp(-(item.cost - baseCost) / scale)
    }));
    const totalWeight = weighted.reduce((sum, item) => sum + item.weight, 0);
    let pick = random() * totalWeight;
    for (const item of weighted) {
      pick -= item.weight;
      if (pick <= 0) return item.path;
    }
    return weighted.at(-1).path;
  }

  const ACCIDENT_FAR_DISTANCE = 140; // px: approach zone starts
  const ACCIDENT_ZONE_RADIUS = 22;   // px: cautious passing zone [-22, +22] around accident center
  const ACCIDENT_EXIT_DISTANCE = 85; // px: exit recovery zone [+22, +85]

  function calculateAccidentSpeedProfile(progress, edgeLength, baseSpeed, isAccident) {
    if (!isAccident) {
      return {
        zone: "none",
        speedFactor: 1.0,
        desiredSpeed: baseSpeed,
        state: "NORMAL",
        lateralNudge: 0
      };
    }
    const distAlong = (progress - 0.5) * edgeLength;
    const cautiousFactor = 0.42;
    const minPassingSpeed = 8.5;
    const cautiousSpeed = Math.max(baseSpeed * cautiousFactor, minPassingSpeed);

    if (distAlong < -ACCIDENT_FAR_DISTANCE) {
      // Zone 1: Far before accident -> normal speed
      return {
        zone: "before",
        speedFactor: 1.0,
        desiredSpeed: baseSpeed,
        state: "NORMAL",
        lateralNudge: 0
      };
    } else if (distAlong < -ACCIDENT_ZONE_RADIUS) {
      // Zone 2: Approach zone -> gradual deceleration
      const approachDist = -distAlong;
      const frac = (approachDist - ACCIDENT_ZONE_RADIUS) / (ACCIDENT_FAR_DISTANCE - ACCIDENT_ZONE_RADIUS);
      const desiredSpeed = cautiousSpeed + (baseSpeed - cautiousSpeed) * frac;
      return {
        zone: "approach",
        speedFactor: desiredSpeed / baseSpeed,
        desiredSpeed,
        state: "SLOWING_FOR_ACCIDENT",
        lateralNudge: 4
      };
    } else if (distAlong <= ACCIDENT_ZONE_RADIUS) {
      // Zone 3: Accident zone -> continue moving at reduced cautious passing speed (DOES NOT STOP)
      return {
        zone: "accident",
        speedFactor: cautiousSpeed / baseSpeed,
        desiredSpeed: cautiousSpeed,
        state: "PASSING_ACCIDENT",
        lateralNudge: 4
      };
    } else if (distAlong <= ACCIDENT_EXIT_DISTANCE) {
      // Zone 4: Exit zone -> gradual acceleration back to normal speed
      const exitFrac = (distAlong - ACCIDENT_ZONE_RADIUS) / (ACCIDENT_EXIT_DISTANCE - ACCIDENT_ZONE_RADIUS);
      const desiredSpeed = cautiousSpeed + (baseSpeed - cautiousSpeed) * exitFrac;
      return {
        zone: "exit",
        speedFactor: desiredSpeed / baseSpeed,
        desiredSpeed,
        state: "ACCELERATING_FROM_ACCIDENT",
        lateralNudge: 0
      };
    } else {
      // Zone 5: Past accident -> 100% normal speed, no further slowdown
      return {
        zone: "past",
        speedFactor: 1.0,
        desiredSpeed: baseSpeed,
        state: "NORMAL",
        lateralNudge: 0
      };
    }
  }

  const AMBULANCE_DETECTION_DISTANCE = 175; // px: distance behind vehicle to trigger yield
  const EMERGENCY_CLEARANCE_DISTANCE = 55;  // px: distance ahead before beginning return
  const EMERGENCY_RETURN_DISTANCE = 55;     // px: distance ahead verified before returning to lane

  return {
    hashSeed,
    mulberry32,
    distance,
    edgeKey,
    generateCity,
    shortestPath,
    diversePath,
    candidatePaths,
    chooseRandomBoundaryPair,
    pathEdges,
    calculateAccidentSpeedProfile,
    ACCIDENT_FAR_DISTANCE,
    ACCIDENT_ZONE_RADIUS,
    ACCIDENT_EXIT_DISTANCE,
    AMBULANCE_DETECTION_DISTANCE,
    EMERGENCY_CLEARANCE_DISTANCE,
    EMERGENCY_RETURN_DISTANCE
  };
});
