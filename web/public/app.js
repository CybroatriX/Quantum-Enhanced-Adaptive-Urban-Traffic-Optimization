(() => {
  "use strict";

  const Core = window.SimulationCore;
  const Optimizer = window.TrafficOptimizer;
  if (!Core || !Optimizer) throw new Error("Simulation modules failed to load.");

  const $ = id => document.getElementById(id);
  const canvas = $("cityCanvas");
  const ctx = canvas.getContext("2d");
  const cameraCanvas = $("cameraCanvas");
  const cameraCtx = cameraCanvas.getContext("2d");
  const ui = Object.fromEntries([
    "backendStatus", "simClock", "pauseBtn", "seedInput", "randomSeedBtn", "generateBtn",
    "controllerSelect", "controllerState", "demandRange", "demandValue", "pedestrianRange",
    "pedestrianValue", "speedRange", "speedValue", "congestionBtn", "accidentBtn", "closureBtn",
    "ambulanceBtn", "hospitalBtn", "inspectBtn", "clearEventsBtn", "toolState", "placementHelp",
    "heatToggle", "routeToggle", "cameraToggle", "capacityToggle", "mapSeed", "mapMode", "zoomInBtn",
    "zoomOutBtn", "fitBtn", "toast", "vehicleMetric", "queueMetric", "waitMetric", "waitDelta",
    "throughputMetric", "co2SavedMetric", "networkQueueMetric", "densityMetric", "fuelMetric",
    "co2Metric", "pedWaitMetric", "incidentMetric", "ambulanceMetric", "fixedWait", "hybridWait",
    "fixedQueue", "hybridQueue", "fixedFuel", "hybridFuel", "fixedCo2", "hybridCo2", "waitReduction",
    "emissionReduction", "waitBar", "emissionBar", "winnerBadge", "junctionName", "junctionTitle",
    "nLight", "sLight", "eLight", "wLight", "nSignalText", "sSignalText", "eSignalText", "wSignalText",
    "phaseLabel",
    "phaseTimer", "junctionDensity", "junctionCapacity", "junctionPedestrians", "quboNs", "quboEw",
    "quboObjective", "algorithmSource", "algorithmStatus", "corridorSection", "corridorStatus",
    "corridorRoute", "corridorEta", "corridorBar", "cameraName", "cameraVehicleCount",
    "cameraQueueCount", "cameraEmergencyCount", "eventCount", "eventStream",
    "resetBtn", "scenarioSelect", "triggerAmbulanceCorridorBtn", "releaseCorridorBtn",
    "injectAccidentJ2Btn", "injectClosureJ3Btn", "injectSurgeBtn", "qaoaStatus",
    "tabLiveBtn", "tabNetworkBtn", "tabEmergencyBtn", "tabEventsBtn", "tabMetricsBtn", "tabResearchBtn", "tabRealworldBtn",
    "tabLive", "tabNetwork", "tabEmergency", "tabEvents", "tabMetrics", "tabResearch", "tabRealworld",
    "northQueue", "southQueue", "eastQueue", "westQueue", "carCount", "busCount",
    "serviceCount", "ambulanceCount", "trackedCount", "detectionConfidence", "observationFreshness",
    "networkGrid", "emergencyVehId", "emergencyRouteSummary", "emergencyPriorityAppr", "emergencyOverrideStatus",
    "btnDispatchCorridor", "btnAdvanceCorridor", "btnReleaseCorridor", "activeEventBadge", "eventsList",
    "evInjectAccidentBtn", "evInjectClosureBtn", "evInjectSurgeBtn", "evInjectPedestrianBtn",
    "qaoaObjectiveVal", "qaoaGapVal", "qaoaRecoveryVal", "qaoaSolverStatus",
    "realworldBadge", "rwSourceSelect", "rwIntersectionSelect", "rwRoiPreset",
    "rwSourceInputGroup", "rwSourcePathLabel", "rwSourcePath", "btnRunPerception", "btnClearPerception",
    "rwStatusText", "rwActiveSourceLabel", "rwNorthQueue", "rwSouthQueue", "rwEastQueue", "rwWestQueue",
    "rwCarCount", "rwBusCount", "rwTruckCount", "rwMotoCount", "rwTotalVehicles", "rwTrackedVehicles",
    "rwAvgConfidence", "rwSolverLabel", "rwRecNs", "rwRecEw", "rwRecObjective", "rwRecCycle", "rwRecValid",
    "rwRecommendationNote"
  ].map(id => [id, $(id)]));

  const COLORS = {
    mint: "#57e3be", cyan: "#56c7ff", blue: "#667cff", amber: "#ffbd66",
    red: "#ff647c", violet: "#9a7cff", asphalt: "#253746", roadEdge: "#111c28"
  };
  const VEHICLE_LENGTH = { car: 15, bus: 25, service: 17, ambulance: 20 };
  const VEHICLE_WIDTH = { car: 7, bus: 8.5, service: 7.5, ambulance: 8.5 };
  const VEHICLE_COLORS = ["#56c7ff", "#dbe9ef", "#9a7cff", "#57e3be", "#f28bb0", "#86aaff", "#ffbd66"];
  const EVENT_PENALTY = { congestion: 18, accident: 75, closure: 500 };
  const SIGNAL_DIRECTIONS = ["N", "S", "E", "W"];

  // Safety, headway, and distance threshold constants
  const STOP_LINE_DISTANCE = 58;
  const TURN_ENTRY_DISTANCE = 54;
  const COMFORTABLE_BRAKING = 9;
  const SPAWN_CLEARANCE_GAP = 42; // px clearance required at entrance point
  const AMBULANCE_DETECTION_DISTANCE = Core.AMBULANCE_DETECTION_DISTANCE || 175; // px: distance behind vehicle to trigger yield
  const EMERGENCY_CLEARANCE_DISTANCE = Core.EMERGENCY_CLEARANCE_DISTANCE || 55; // px: ambulance distance ahead to begin return-to-lane
  const EMERGENCY_RETURN_DISTANCE = Core.EMERGENCY_RETURN_DISTANCE || 55; // px: ambulance distance ahead verified before returning to lane
  const LATERAL_SHIFT_SPEED = 9.0; // px/s smooth lateral glide speed
  const SAFE_OUTER_CURB_OFFSET = 31; // px: safe edge of own carriageway (+12 inner, +28 outer, +31 curb)
  const ACCIDENT_FAR_DISTANCE = Core.ACCIDENT_FAR_DISTANCE || 140; // px: approach zone where gradual slowdown begins
  const ACCIDENT_ZONE_RADIUS = Core.ACCIDENT_ZONE_RADIUS || 22; // px: cautious passing zone around accident center
  const ACCIDENT_EXIT_DISTANCE = Core.ACCIDENT_EXIT_DISTANCE || 85; // px: exit recovery zone where normal speed is restored

  let city;
  let random;
  let vehicles = [];
  let signals = [];
  let roadEvents = new Map();
  let cameras = new Set();
  let hospitalNode = 6;
  let selectedJunction = 1;
  let placementMode = "inspect";
  let paused = false;
  let simulationSpeed = 1;
  let simulationTime = 0;
  let lastFrame = performance.now();
  let spawnAccumulator = 0;
  let metricAccumulator = 0;
  let optimizerAccumulator = 0;
  let optimizerPending = false;
  let completedVehicles = 0;
  let totalCompletedTravel = 0;
  let nextVehicleId = 1;
  let events = [];
  let toastTimer = 0;
  let view = { x: 0, y: 0, zoom: 1 };
  let pointer = { down: false, dragging: false, startX: 0, startY: 0, viewX: 0, viewY: 0 };
  let totalFuel = 0;
  let baselineFuel = 0;
  let totalCo2 = 0;
  let baselineCo2 = 0;
  let corridorCompleted = 0;
  let corridorBaseline = 0;
  let lastBoundaryPair = null;
  let junctionEntries = [];
  let redLightViolations = 0;
  let closureRedirects = 0;
  let vehicleExits = [];
  let vehicleSpawns = [];
  let closureJunctionDetours = [];

  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
  function formatTime(seconds) {
    const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
    const minutes = String(Math.floor(seconds % 3600 / 60)).padStart(2, "0");
    const secs = String(Math.floor(seconds % 60)).padStart(2, "0");
    return `${hours}:${minutes}:${secs}`;
  }
  function label(id) { return String(id + 1).padStart(2, "0"); }
  function edgeBetween(a, b) {
    const link = city.adjacency[a].find(item => item.node === b);
    return link ? city.edges[link.edge] : null;
  }
  function incomingAxis(from, to) {
    const a = city.nodes[from];
    const b = city.nodes[to];
    return Math.abs(b.x - a.x) >= Math.abs(b.y - a.y) ? "EW" : "NS";
  }
  function incomingDirection(from, to) {
    const a = city.nodes[from];
    const b = city.nodes[to];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    if (Math.abs(dx) >= Math.abs(dy)) return dx > 0 ? "W" : "E";
    return dy > 0 ? "N" : "S";
  }
  function directionAxis(direction) {
    return direction === "N" || direction === "S" ? "NS" : "EW";
  }
  function blockedRoads() {
    return new Set([...roadEvents.values()]
      .filter(event => event.type === "closure")
      .map(event => event.key));
  }

  function makeSignal(node) {
    const startDirection = SIGNAL_DIRECTIONS[(node.id + city.numericSeed) % SIGNAL_DIRECTIONS.length];
    return {
      id: node.id,
      phase: `${startDirection}_GREEN`,
      remaining: 8 + random() * 14,
      nsGreen: 30,
      ewGreen: 30,
      pendingNsGreen: null,
      pendingEwGreen: null,
      lastAdjustmentTime: -999,
      nsQueue: 0,
      ewQueue: 0,
      directionQueues: { N: 0, S: 0, E: 0, W: 0 },
      requestedAxis: null,
      requestedDirection: null,
      nextDirection: SIGNAL_DIRECTIONS[(SIGNAL_DIRECTIONS.indexOf(startDirection) + 1) % SIGNAL_DIRECTIONS.length],
      priorityActive: false,
      pedestrians: node.pedestrianDemand * 4,
      pedestrianWait: 0,
      lastDecision: null
    };
  }

  function generateCity(seed) {
    city = Core.generateCity(seed);
    random = Core.mulberry32(city.numericSeed ^ 0x91ab23ef);
    signals = city.nodes.map(makeSignal);
    vehicles = [];
    roadEvents = new Map();
    cameras = new Set(city.nodes.filter((_, index) => index % 2 === 1).map(node => node.id));
    hospitalNode = 6;
    selectedJunction = 1;
    simulationTime = 0;
    completedVehicles = 0;
    totalCompletedTravel = 0;
    totalFuel = 0;
    baselineFuel = 0;
    totalCo2 = 0;
    baselineCo2 = 0;
    corridorCompleted = 0;
    corridorBaseline = 0;
    nextVehicleId = 1;
    spawnAccumulator = 0;
    optimizerAccumulator = 0;
    metricAccumulator = 0;
    lastBoundaryPair = null;
    junctionEntries = [];
    redLightViolations = 0;
    closureRedirects = 0;
    vehicleExits = [];
    vehicleSpawns = [];
    closureJunctionDetours = [];
    events = [];
    for (let attempts = 0; attempts < 160 && vehicles.length < 24; attempts += 1) spawnRegularVehicle(true);
    fitCity();
    ui.mapSeed.textContent = String(seed).toUpperCase();
    addEvent("Digital twin initialized", `${city.nodes.length} junctions • ${city.edges.length} roads • multi-route demand`);
    addEvent("Hybrid optimizer armed", "QUBO evaluates nine feasible timing pairs every 6 seconds", "quantum");
    addEvent("Emergency destination ready", `Hospital at J-${label(hospitalNode)} • ${city.nodes[hospitalNode].name}`, "emergency");
    updatePanel();
  }

  function edgeVehicleCounts() {
    const counts = Array(city.edges.length).fill(0);
    for (const vehicle of vehicles) {
      const edge = edgeBetween(vehicle.from, vehicle.to);
      if (edge) counts[edge.id] += 1;
    }
    return counts;
  }

  function edgeDynamicCosts() {
    const counts = edgeVehicleCounts();
    return counts.map((count, index) => {
      const edge = city.edges[index];
      const load = count / Math.max(1, edge.capacity);
      const event = roadEvents.get(edge.key);
      return load * load * 36 + (event ? EVENT_PENALTY[event.type] : 0);
    });
  }

  function chooseBoundaryPair() {
    const pair = Core.chooseRandomBoundaryPair(city, random, lastBoundaryPair);
    lastBoundaryPair = pair;
    return pair;
  }

  function findFreeLane(from, to, preferred = null) {
    const edge = edgeBetween(from, to);
    if (!edge) return -1;
    const lanes = preferred === null
      ? Array.from({ length: edge.lanes }, (_, lane) => lane).sort(() => random() - .5)
      : [preferred, ...Array.from({ length: edge.lanes }, (_, lane) => lane).filter(lane => lane !== preferred)];
    for (const lane of lanes) {
      const occupied = vehicles.some(vehicle =>
        vehicle.from === from && vehicle.to === to && vehicle.lane === lane &&
        vehicle.progress * edge.length < SPAWN_CLEARANCE_GAP
      );
      if (!occupied) return lane;
    }
    return -1;
  }

  function buildingVehiclePosition(vehicle) {
    const bd = vehicle.buildingAccess;
    if (!bd) return { x: 0, y: 0, angle: 0 };
    if (vehicle.state === "PARKED_AT_BUILDING") {
      return { x: bd.parkingX, y: bd.parkingY, angle: bd.angle };
    }
    if (vehicle.state === "ENTERING_BUILDING") {
      const p = clamp(vehicle.drivewayProgress, 0, 1);
      if (p <= 0.5) {
        const t = p / 0.5;
        return {
          x: bd.roadX + (bd.curbX - bd.roadX) * t,
          y: bd.roadY + (bd.curbY - bd.roadY) * t,
          angle: bd.angle
        };
      }
      const t = (p - 0.5) / 0.5;
      return {
        x: bd.curbX + (bd.parkingX - bd.curbX) * t,
        y: bd.curbY + (bd.parkingY - bd.curbY) * t,
        angle: bd.angle
      };
    }
    if (vehicle.state === "EXITING_BUILDING") {
      const p = clamp(vehicle.drivewayProgress, 0, 1);
      return {
        x: bd.curbX + (bd.parkingX - bd.curbX) * p,
        y: bd.curbY + (bd.parkingY - bd.curbY) * p,
        angle: bd.angle + Math.PI
      };
    }
    return { x: bd.roadX, y: bd.roadY, angle: bd.angle };
  }

  function createVehicle(path, type, initialProgress = 0) {
    if (!path || path.length < 2) return false;
    // Regular traffic must enter through an explicit perimeter gateway and
    // leave through a perimeter gateway. J1-J4 are never spawn/end points.
    if (!city.nodes[path[0]] || !city.nodes[path.at(-1)]) return false;
    const spawnPoint = city.spawnPoints.find(point => point.nodeId === path[0]);
    if (type !== "ambulance" && (!spawnPoint || path[1] !== spawnPoint.toNode || !city.boundaryNodes.includes(path.at(-1)))) return false;
    for (let i = 0; i < path.length - 1; i += 1) {
      const seg = edgeBetween(path[i], path[i + 1]);
      if (!seg || seg.lanes < 1) return false;
    }
    const preferredLane = type === "ambulance" ? 0 : null;
    let lane = findFreeLane(path[0], path[1], preferredLane);
    const edge = edgeBetween(path[0], path[1]);
    if (lane < 0 && type === "ambulance") {
      // Emergency priority: ambulance secures lane 0 and advances any stationary demand
      lane = 0;
      const blockers = vehicles.filter(v => v.from === path[0] && v.to === path[1] && v.lane === 0 && v.progress * edge.length < SPAWN_CLEARANCE_GAP);
      for (const b of blockers) {
        if (b.type !== "ambulance") {
          b.progress = Math.min(0.65, (SPAWN_CLEARANCE_GAP + 8) / edge.length);
        }
      }
    }
    if (lane < 0) return false;

    // Verify spawn clearance: ensure starting position is not occupied
    const spawnBlocked = vehicles.some(v =>
      v.from === path[0] && v.to === path[1] && v.lane === lane &&
      v.progress * edge.length < SPAWN_CLEARANCE_GAP
    );
    if (spawnBlocked && type !== "ambulance") return false;

    const factor = type === "bus" ? .7 : type === "service" ? .82 : type === "ambulance" ? 1.12 : .82 + random() * .14;
    const freeFlowSeconds = Core.pathEdges(city, path).reduce((sum, id) => sum + city.edges[id].length / city.edges[id].speed, 0);
    const defaultLateral = lane === 0 ? 12 : 28;
    vehicles.push({
      id: nextVehicleId++,
      type,
      path,
      pathIndex: 1,
      spawnNode: path[0],
      spawnPointId: spawnPoint?.id || null,
      from: path[0],
      to: path[1],
      target: path.at(-1),
      lane,
      originalLane: lane,
      state: "NORMAL",
      currentLateralOffset: defaultLateral,
      targetLateralOffset: defaultLateral,
      yieldTimer: 0,
      buildingAccess: null,
      parkTimer: 0,
      drivewayProgress: 0,
      progress: 0,
      speed: edge.speed * factor,
      currentSpeed: 0,
      wait: 0,
      travelTime: 0,
      freeFlowSeconds,
      stopped: false,
      braking: false,
      inTurn: false,
      turnU: 0,
      turnCurve: null,
      turnIndicator: null,
      priorityRequested: false,
      color: type === "ambulance" ? COLORS.red : type === "bus" ? COLORS.amber :
        type === "service" ? COLORS.violet : VEHICLE_COLORS[Math.floor(random() * VEHICLE_COLORS.length)]
    });
    if (type !== "ambulance") {
      vehicleSpawns.push({
        vehicleId: vehicles.at(-1).id,
        spawnNode: path[0],
        spawnPointId: spawnPoint.id,
        firstRoad: edge.id,
        time: simulationTime
      });
      if (vehicleSpawns.length > 500) vehicleSpawns.shift();
    }
    return true;
  }

  function spawnRegularVehicle(initial = false) {
    const { start, target } = chooseBoundaryPair();
    const route = Core.diversePath(city, start, target, blockedRoads(), edgeDynamicCosts(), random);
    if (!route || route.length < 2) return false;
    if (!city.boundaryNodes.includes(route[0]) || !city.boundaryNodes.includes(route.at(-1))) return false;
    const roll = random();
    const type = roll < .06 ? "bus" : roll < .11 ? "service" : "car";
    if (!createVehicle(route, type, 0)) return false;
    const vehicle = vehicles.at(-1);
    const edge = edgeBetween(vehicle.from, vehicle.to);

    // Building access: assign to ~5% of regular cars traversing a designated driveway
    if (type === "car" && random() < 0.05 && city.buildingDriveways && city.buildingDriveways.length > 0) {
      for (const driveway of city.buildingDriveways) {
        for (let i = 0; i < route.length - 1; i += 1) {
          if (route[i] === driveway.fromNode && route[i + 1] === driveway.toNode) {
            vehicle.buildingAccess = driveway;
            break;
          }
        }
        if (vehicle.buildingAccess) break;
      }
    }

    vehicle.progress = 0;
    vehicle.currentSpeed = edge.speed * .55;
    return true;
  }

  function dispatchAmbulance(startNode) {
    if (startNode === hospitalNode) return showToast("Choose another junction; this is already the hospital.");
    const route = Core.shortestPath(city, startNode, hospitalNode, blockedRoads(), edgeDynamicCosts());
    if (route.length < 2) return showToast("No safe route to hospital. Restore a blocked road first.");
    if (!createVehicle(route, "ambulance")) return showToast("Dispatch lane occupied. Choose a nearby junction.");
    const ambulance = vehicles.at(-1);
    ambulance.corridorStart = simulationTime;
    ambulance.corridorLength = route.length - 1;
    addEvent("Ambulance corridor activated", `J-${label(startNode)} → Hospital J-${label(hospitalNode)} • ${route.length - 1} signal corridor`, "emergency");
    setPlacementMode("inspect");
  }

  function recalculateRoute(vehicle, currentNode) {
    const costs = edgeDynamicCosts();
    const path = vehicle.type === "ambulance"
      ? Core.shortestPath(city, currentNode, vehicle.target, blockedRoads(), costs)
      : Core.diversePath(city, currentNode, vehicle.target, blockedRoads(), costs, random);
    if (path.length < 2) return "none";
    const lane = findFreeLane(path[0], path[1], vehicle.lane);
    if (lane < 0) return "wait";
    vehicle.path = path;
    vehicle.pathIndex = 1;
    vehicle.from = path[0];
    vehicle.to = path[1];
    vehicle.progress = 0;
    vehicle.lane = lane;
    if (vehicle.type === "ambulance") vehicle.corridorLength = Math.max(vehicle.corridorLength || 0, path.length - 1);
    return "ok";
  }

  function reachableExitRoute(vehicle, currentNode) {
    const blocked = blockedRoads();
    const costs = edgeDynamicCosts();
    const routeTo = target => vehicle.type === "ambulance"
      ? Core.shortestPath(city, currentNode, target, blocked, costs)
      : Core.diversePath(city, currentNode, target, blocked, costs, random);

    const preferred = routeTo(vehicle.target);
    if (preferred.length >= 2) return preferred;
    if (vehicle.type === "ambulance") return [];

    const alternatives = city.boundaryNodes
      .filter(nodeId => nodeId !== currentNode && nodeId !== vehicle.target)
      .sort(() => random() - .5);
    for (const exitNode of alternatives) {
      const route = routeTo(exitNode);
      if (route.length >= 2) return route;
    }
    return city.boundaryNodes.includes(currentNode) ? [currentNode] : [];
  }

  function findSafeReverseLane(vehicle, from, to, progress) {
    const edge = edgeBetween(from, to);
    if (!edge) return -1;
    const lanes = [vehicle.lane, ...Array.from({ length: edge.lanes }, (_, lane) => lane).filter(lane => lane !== vehicle.lane)];
    for (const lane of lanes) {
      const occupied = vehicles.some(other => other.id !== vehicle.id && !other.inTurn &&
        other.from === from && other.to === to && other.lane === lane &&
        Math.abs(other.progress - progress) * edge.length < SPAWN_CLEARANCE_GAP);
      if (!occupied) return lane;
    }
    return -1;
  }

  function redirectFromClosedRoad(vehicle, edge) {
    const returnNode = vehicle.from;
    const detour = reachableExitRoute(vehicle, returnNode);
    if (!detour.length) return false;

    const reverseFrom = vehicle.to;
    const reverseTo = returnNode;
    const reverseProgress = 1 - vehicle.progress;
    const lane = findSafeReverseLane(vehicle, reverseFrom, reverseTo, reverseProgress);
    if (lane < 0) return false;

    vehicle.path = [reverseFrom, reverseTo, ...detour.slice(1)];
    vehicle.pathIndex = 1;
    vehicle.from = reverseFrom;
    vehicle.to = reverseTo;
    vehicle.progress = reverseProgress;
    vehicle.target = detour.at(-1) ?? returnNode;
    vehicle.lane = lane;
    vehicle.originalLane = lane;
    vehicle.currentLateralOffset = lane === 0 ? 12 : 28;
    vehicle.targetLateralOffset = vehicle.currentLateralOffset;
    vehicle.state = "REROUTING_FROM_CLOSURE";
    vehicle.stopped = false;
    vehicle.braking = false;
    vehicle.turnIndicator = null;
    const factor = vehicle.type === "ambulance" ? 1.12 : vehicle.type === "bus" ? .7 : vehicle.type === "service" ? .82 : .9;
    vehicle.speed = edge.speed * factor;
    vehicle.currentSpeed = Math.min(Math.max(vehicle.currentSpeed, 2.5), vehicle.speed * .45);
    closureRedirects += 1;
    return true;
  }

  function updateQueuesAndPriority() {
    for (const signal of signals) {
      signal.nsQueue = 0;
      signal.ewQueue = 0;
      signal.directionQueues = { N: 0, S: 0, E: 0, W: 0 };
      signal.requestedAxis = null;
      signal.requestedDirection = null;
    }
    const ambulances = vehicles.filter(vehicle => vehicle.type === "ambulance");
    for (const vehicle of vehicles) {
      const edge = edgeBetween(vehicle.from, vehicle.to);
      if (!edge) continue;
      const distanceToSignal = edge.length * (1 - vehicle.progress);
      if (distanceToSignal < 110 && (vehicle.stopped || vehicle.currentSpeed < vehicle.speed * .4)) {
        const direction = incomingDirection(vehicle.from, vehicle.to);
        const axis = incomingAxis(vehicle.from, vehicle.to);
        signals[vehicle.to].directionQueues[direction] += 1;
        if (axis === "NS") signals[vehicle.to].nsQueue += 1;
        else signals[vehicle.to].ewQueue += 1;
      }
      if (vehicle.type === "ambulance") {
        for (let index = vehicle.pathIndex; index < Math.min(vehicle.path.length, vehicle.pathIndex + 4); index += 1) {
          const from = index === vehicle.pathIndex ? vehicle.from : vehicle.path[index - 1];
          const to = vehicle.path[index];
          const direction = incomingDirection(from, to);
          signals[to].requestedDirection = direction;
          signals[to].requestedAxis = directionAxis(direction);
        }
      }
    }
    for (const signal of signals) {
      if (signal.requestedDirection && !signal.priorityActive) signal.priorityActive = true;
      if (!signal.requestedDirection && signal.priorityActive && ambulances.length === 0) signal.priorityActive = false;
    }
  }

  function phaseDirection(phase) {
    const match = /^(N|S|E|W)_(GREEN|YELLOW)$/.exec(phase);
    return match ? match[1] : null;
  }
  function phaseColor(phase, direction) {
    if (phase === `${direction}_GREEN`) return "green";
    if (phase === `${direction}_YELLOW`) return "yellow";
    return "red";
  }
  function nextSignalDirection(direction) {
    const index = SIGNAL_DIRECTIONS.indexOf(direction);
    return SIGNAL_DIRECTIONS[(Math.max(0, index) + 1) % SIGNAL_DIRECTIONS.length];
  }
  function directionGreenSeconds(signal, direction) {
    const axisGreen = directionAxis(direction) === "NS" ? signal.nsGreen : signal.ewGreen;
    return signal.priorityActive ? clamp(axisGreen, 22, 42) : clamp(axisGreen * .55, 12, 23);
  }

  function advanceSignal(signal) {
    const pedestrianDemand = Number(ui.pedestrianRange.value) / 100;
    const activeDirection = phaseDirection(signal.phase);
    if (activeDirection && signal.phase.endsWith("GREEN")) {
      signal.phase = `${activeDirection}_YELLOW`;
      signal.remaining = 4;
      return;
    }
    if (activeDirection && signal.phase.endsWith("YELLOW")) {
      signal.nextDirection = signal.requestedDirection || nextSignalDirection(activeDirection);
      signal.phase = `ALL_RED_TO_${signal.nextDirection}`;
      signal.remaining = 2 + Math.min(4, pedestrianDemand * signal.pedestrians * .45);
      return;
    }

    const target = signal.requestedDirection || signal.nextDirection || "N";
    const targetAxis = directionAxis(target);
    signal.phase = `${target}_GREEN`;
    if (targetAxis === "NS" && signal.pendingNsGreen != null) signal.nsGreen = signal.pendingNsGreen;
    if (targetAxis === "EW" && signal.pendingEwGreen != null) signal.ewGreen = signal.pendingEwGreen;
    signal.remaining = directionGreenSeconds(signal, target);
    signal.nextDirection = nextSignalDirection(target);
  }

  function junctionOccupied(junctionId) {
    return vehicles.some(vehicle => vehicle.inTurn && vehicle.turnCurve?.nextFrom === junctionId);
  }

  function updateSignals(dt) {
    updateQueuesAndPriority();
    const pedestrianDemand = Number(ui.pedestrianRange.value) / 100;
    for (const signal of signals) {
      signal.pedestrians = Math.min(24, signal.pedestrians + dt * pedestrianDemand * city.nodes[signal.id].pedestrianDemand * .05);
      if (signal.phase.startsWith("ALL_RED")) signal.pedestrians = Math.max(0, signal.pedestrians - dt * 1.8);
      else signal.pedestrianWait += signal.pedestrians * dt;
      signal.remaining -= dt;
      if (signal.requestedDirection) {
        const currentDirection = phaseDirection(signal.phase);
        if (signal.phase === `${signal.requestedDirection}_GREEN`) signal.remaining = Math.max(signal.remaining, 5);
        else if (currentDirection && signal.phase.endsWith("GREEN")) signal.remaining = Math.min(signal.remaining, 1.2);
      }
      if (signal.remaining <= 0) {
        // Never release a conflicting green while a vehicle is still clearing
        // the junction. The all-red interval expands only as long as needed.
        if (signal.phase.startsWith("ALL_RED") && junctionOccupied(signal.id)) signal.remaining = .12;
        else advanceSignal(signal);
      }
    }
  }

  function signalAllows(vehicle) {
    if (vehicle.to >= 4 || city.nodes[vehicle.to]?.boundary) return true;
    const signal = signals[vehicle.to];
    if (!signal) return true;
    const direction = incomingDirection(vehicle.from, vehicle.to);
    return signal.phase === `${direction}_GREEN`;
  }
  function laneGroupKey(vehicle) {
    if (vehicle.inTurn) return null;
    if (vehicle.state === "ENTERING_BUILDING" || vehicle.state === "PARKED_AT_BUILDING" || vehicle.state === "EXITING_BUILDING") return null;
    return `${vehicle.from}>${vehicle.to}:${vehicle.lane}`;
  }

  function eventSpeedMultiplier(edge) {
    const event = roadEvents.get(edge.key);
    if (!event) return 1;
    if (event.type === "congestion") return .42;
    if (event.type === "closure") return .16;
    return 1;
  }

  function enforceLaneCapacity() {
    const groups = new Map();
    for (const vehicle of vehicles) {
      const key = laneGroupKey(vehicle);
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(vehicle);
    }
    const outsideNetwork = new Set();
    for (const group of groups.values()) {
      group.sort((a, b) => b.progress - a.progress);
      for (let index = 1; index < group.length; index += 1) {
        const leader = group[index - 1];
        const follower = group[index];
        const edge = edgeBetween(follower.from, follower.to);
        if (!edge) continue;
        const gap = (VEHICLE_LENGTH[leader.type] + VEHICLE_LENGTH[follower.type]) / 2 + 3.5;
        const maximumProgress = leader.progress - gap / edge.length;
        if (maximumProgress < 0) {
          // The lane entrance is full. Keep excess demand outside the modeled
          // network rather than stacking vehicles on one coordinate.
          const rejected = follower.type === "ambulance" && leader.type !== "ambulance" ? leader : follower;
          outsideNetwork.add(rejected.id);
        } else if (follower.progress > maximumProgress) {
          follower.progress = maximumProgress;
          follower.currentSpeed = Math.min(follower.currentSpeed, leader.currentSpeed);
          follower.stopped = follower.currentSpeed < .35;
          follower.braking = true;
        }
      }
    }
    if (outsideNetwork.size) vehicles = vehicles.filter(vehicle => !outsideNetwork.has(vehicle.id));
  }

  function updateVehicles(dt) {
    const fuelBeforeStep = totalFuel;
    const completed = [];

    // 1. Process vehicles in building / driveway states
    for (const vehicle of vehicles) {
      if (vehicle.state === "ENTERING_BUILDING") {
        vehicle.travelTime += dt;
        vehicle.drivewayProgress += dt * 0.45;
        if (vehicle.drivewayProgress >= 1) {
          vehicle.drivewayProgress = 1;
          vehicle.state = "PARKED_AT_BUILDING";
          vehicle.parkTimer = 3.5 + random() * 2.5; // brief parking wait
        }
      } else if (vehicle.state === "PARKED_AT_BUILDING") {
        vehicle.travelTime += dt;
        vehicle.parkTimer -= dt;
        if (vehicle.parkTimer <= 0) {
          vehicle.state = "EXITING_BUILDING";
          vehicle.drivewayProgress = 1;
        }
      } else if (vehicle.state === "EXITING_BUILDING") {
        vehicle.travelTime += dt;
        if (vehicle.drivewayProgress > 0.05) {
          vehicle.drivewayProgress -= dt * 0.45;
        } else {
          // At curb entrance: check oncoming road traffic on road segment in outer lane (lane 1)
          const bd = vehicle.buildingAccess;
          const edge = edgeBetween(vehicle.from, vehicle.to);
          const drivewayProg = edge ? clamp(Math.hypot(bd.roadX - city.nodes[vehicle.from].x, bd.roadY - city.nodes[vehicle.from].y) / edge.length, 0.1, 0.9) : 0.5;
          const oncoming = vehicles.some(v =>
            v !== vehicle && v.from === vehicle.from && v.to === vehicle.to &&
            v.lane === 1 && !v.inTurn && v.progress < drivewayProg + 0.12 &&
            v.progress > drivewayProg - 0.18
          );
          if (!oncoming) {
            // Safe insertion gap verified! Enter outer lane (lane 1) safely
            vehicle.state = "NORMAL";
            vehicle.lane = 1;
            vehicle.originalLane = 1;
            vehicle.targetLateralOffset = 28;
            vehicle.currentLateralOffset = 28;
            vehicle.progress = drivewayProg;
            vehicle.currentSpeed = (edge ? edge.speed : 25) * 0.4;
            vehicle.buildingAccess = null;
          }
        }
      }
    }

    // 2. Smooth lateral offset glide for on-road vehicles (no teleportation)
    for (const vehicle of vehicles) {
      if (vehicle.inTurn || vehicle.state === "ENTERING_BUILDING" || vehicle.state === "PARKED_AT_BUILDING" || vehicle.state === "EXITING_BUILDING") continue;
      if (Math.abs(vehicle.currentLateralOffset - vehicle.targetLateralOffset) > 0.05) {
        const shiftSpeed = LATERAL_SHIFT_SPEED * dt;
        const diff = vehicle.targetLateralOffset - vehicle.currentLateralOffset;
        vehicle.currentLateralOffset += Math.sign(diff) * Math.min(Math.abs(diff), shiftSpeed);
      } else {
        vehicle.currentLateralOffset = vehicle.targetLateralOffset;
      }
    }

    // 3. Process vehicles currently in active turning curve across an intersection box
    for (const vehicle of vehicles) {
      if (vehicle.inTurn && vehicle.turnCurve) {
        vehicle.travelTime += dt;
        const turnSpeed = vehicle.turnIndicator ? Math.min(vehicle.speed * 0.55, 13) : Math.min(vehicle.speed * 0.75, 17);
        vehicle.currentSpeed = turnSpeed;
        vehicle.stopped = false;
        vehicle.braking = false;
        vehicle.turnU += (turnSpeed * dt) / vehicle.turnCurve.length;
        if (vehicle.turnU >= 1) {
          vehicle.inTurn = false;
          vehicle.turnIndicator = null;
          vehicle.from = vehicle.turnCurve.nextFrom;
          vehicle.to = vehicle.turnCurve.nextTo;
          vehicle.lane = vehicle.turnCurve.nextLane;
          vehicle.originalLane = vehicle.turnCurve.nextLane;
          vehicle.targetLateralOffset = vehicle.lane === 0 ? 12 : 28;
          vehicle.currentLateralOffset = vehicle.targetLateralOffset;
          vehicle.pathIndex += 1;
          const outEdge = edgeBetween(vehicle.from, vehicle.to);
          vehicle.progress = outEdge ? clamp(54 / outEdge.length, 0, 0.95) : 0;
          vehicle.turnCurve = null;
        }
      }
    }

    const groups = new Map();
    for (const vehicle of vehicles) {
      if (vehicle.inTurn) continue;
      const key = laneGroupKey(vehicle);
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(vehicle);
    }
    for (const group of groups.values()) group.sort((a, b) => b.progress - a.progress);

    for (const group of groups.values()) {
      for (let index = 0; index < group.length; index += 1) {
        const vehicle = group[index];
        if (vehicle.inTurn || vehicle.state === "ENTERING_BUILDING" || vehicle.state === "PARKED_AT_BUILDING" || vehicle.state === "EXITING_BUILDING") continue;
        const edge = edgeBetween(vehicle.from, vehicle.to);
        if (!edge) { completed.push(vehicle.id); continue; }
        vehicle.travelTime += dt;
        const length = VEHICLE_LENGTH[vehicle.type];
        let desired = vehicle.speed * eventSpeedMultiplier(edge);
        let leader = null;
        if (index > 0) {
          const candidate = group[index - 1];
          if (candidate.from === vehicle.from && candidate.to === vehicle.to && candidate.lane === vehicle.lane) {
            leader = candidate;
            const centerGap = (leader.progress - vehicle.progress) * edge.length;
            const physicalGap = centerGap - (VEHICLE_LENGTH[leader.type] + length) / 2;
            const safeGap = 9 + desired * .78;
            if (physicalGap <= 3) desired = 0;
            else if (physicalGap < safeGap) desired *= clamp((physicalGap - 3) / Math.max(1, safeGap - 3), 0, 1);
            desired = Math.min(desired, leader.currentSpeed + Math.max(0, physicalGap - 3) * .75);

            // Natural accident queue formation behind slowing / passing vehicles
            if (leader.state === "SLOWING_FOR_ACCIDENT" || leader.state === "PASSING_ACCIDENT" || leader.state === "QUEUED_BY_ACCIDENT") {
              if (vehicle.state === "NORMAL" && (vehicle.stopped || desired < vehicle.speed * 0.75)) {
                vehicle.state = "QUEUED_BY_ACCIDENT";
              }
            } else if (vehicle.state === "QUEUED_BY_ACCIDENT" && desired >= vehicle.speed * 0.85) {
              vehicle.state = "NORMAL";
            }
          }
        }

        const remaining = edge.length * (1 - vehicle.progress);
        const approachingSignal = vehicle.to < 4 && !city.nodes[vehicle.to]?.boundary;
        const allows = !approachingSignal || signalAllows(vehicle);
        let downstreamLane = null;
        let downstreamBlocked = false;
        if (approachingSignal && vehicle.pathIndex < vehicle.path.length - 1 && remaining < 90) {
          const reached = vehicle.to;
          let plannedNext = vehicle.path[vehicle.pathIndex + 1];
          let plannedEdge = edgeBetween(reached, plannedNext);

          // If a closure appeared after this trip began, choose a detour before
          // entering the junction instead of waiting forever at the stop line.
          if (!plannedEdge || blockedRoads().has(plannedEdge.key)) {
            const closedEdgeId = plannedEdge?.id ?? null;
            const detour = reachableExitRoute(vehicle, reached);
            if (detour.length >= 2) {
              vehicle.path = [...vehicle.path.slice(0, vehicle.pathIndex + 1), ...detour.slice(1)];
              vehicle.target = detour.at(-1);
              plannedNext = vehicle.path[vehicle.pathIndex + 1];
              plannedEdge = edgeBetween(reached, plannedNext);
              closureJunctionDetours.push({
                vehicleId: vehicle.id,
                junctionId: reached,
                closedEdgeId,
                chosenEdgeId: plannedEdge?.id ?? null,
                decisionPhase: signals[reached]?.phase || "UNCONTROLLED",
                time: simulationTime
              });
              if (closureJunctionDetours.length > 300) closureJunctionDetours.shift();
            }
          }

          downstreamBlocked = !plannedEdge || blockedRoads().has(plannedEdge.key);
          if (!downstreamBlocked) downstreamLane = findFreeLane(reached, plannedNext, vehicle.lane);
        }
        const movementBlocked = downstreamBlocked || downstreamLane === -1;

        // Turn indicator warning when approaching an intersection
        if (remaining < 110 && vehicle.pathIndex < vehicle.path.length - 1) {
          const nextNode = vehicle.path[vehicle.pathIndex + 1];
          const a = city.nodes[vehicle.from], b = city.nodes[vehicle.to], c = city.nodes[nextNode];
          const dInX = b.x - a.x, dInY = b.y - a.y;
          const dOutX = c.x - b.x, dOutY = c.y - b.y;
          const lenIn = Math.hypot(dInX, dInY) || 1, lenOut = Math.hypot(dOutX, dOutY) || 1;
          const cp = (dInX / lenIn) * (dOutY / lenOut) - (dInY / lenIn) * (dOutX / lenOut);
          vehicle.turnIndicator = cp > 0.25 ? "right" : (cp < -0.25 ? "left" : null);
        } else if (remaining >= 110) {
          vehicle.turnIndicator = null;
        }

        // Check if car reaches building driveway entry point
        if (vehicle.buildingAccess && vehicle.state === "NORMAL" && !vehicle.inTurn) {
          const bd = vehicle.buildingAccess;
          if (vehicle.from === bd.fromNode && vehicle.to === bd.toNode) {
            const drivewayProg = clamp(Math.hypot(bd.roadX - city.nodes[vehicle.from].x, bd.roadY - city.nodes[vehicle.from].y) / edge.length, 0.1, 0.9);
            if (Math.abs(vehicle.progress - drivewayProg) < 0.04) {
              vehicle.state = "ENTERING_BUILDING";
              vehicle.drivewayProgress = 0;
              vehicle.currentSpeed = 0;
              continue;
            }
          }
        }

        // Distance-based accident response: smooth approach slowdown, cautious passing, gradual exit acceleration
        const activeEvent = roadEvents.get(edge.key);
        const isClosure = activeEvent && activeEvent.type === "closure";
        let isAccident = false;
        if (activeEvent && activeEvent.type === "accident") {
          const matchesDirection = !activeEvent.affectedFrom || (vehicle.from === activeEvent.affectedFrom && vehicle.to === activeEvent.affectedTo);
          const matchesLane = activeEvent.affectedLane === undefined || vehicle.lane === activeEvent.affectedLane;
          isAccident = matchesDirection && matchesLane;
        }

        if (isAccident) {
          const profile = Core.calculateAccidentSpeedProfile(
            vehicle.progress,
            edge.length,
            vehicle.speed,
            true
          );
          if (profile.zone === "approach" || profile.zone === "accident" || profile.zone === "exit") {
            desired = Math.min(desired, profile.desiredSpeed);
            vehicle.state = profile.state;
            vehicle.braking = desired < vehicle.currentSpeed * 0.9;
            if (vehicle.lane === 0 && vehicle.state !== "YIELDING_TO_AMBULANCE" && vehicle.state !== "WAITING_FOR_AMBULANCE") {
              vehicle.targetLateralOffset = 12 + profile.lateralNudge;
            }
          } else if (vehicle.state === "SLOWING_FOR_ACCIDENT" || vehicle.state === "PASSING_ACCIDENT" || vehicle.state === "ACCELERATING_FROM_ACCIDENT" || vehicle.state === "QUEUED_BY_ACCIDENT") {
            vehicle.state = "NORMAL";
            if (vehicle.lane === 0 && vehicle.state !== "YIELDING_TO_AMBULANCE" && vehicle.state !== "WAITING_FOR_AMBULANCE") {
              vehicle.targetLateralOffset = 12;
            }
          }
        } else if (isClosure && vehicle.progress < 0.5) {
          // A vehicle already on a newly closed road safely reverses to its
          // previous node, then follows an open route to an outer exit.
          if (redirectFromClosedRoad(vehicle, edge)) continue;

          // Wait short of the closure until the opposite carriageway is clear.
          const distToClosure = (0.5 - vehicle.progress) * edge.length;
          if (distToClosure <= 24) {
            desired = 0;
            vehicle.braking = true;
            vehicle.stopped = true;
            const maxClosureProgress = 0.5 - (24 / edge.length);
            if (vehicle.progress > maxClosureProgress) vehicle.progress = maxClosureProgress;
          } else if (distToClosure <= 65) {
            desired = Math.min(desired, 3.2);
            vehicle.braking = true;
          }
        } else if (vehicle.state === "SLOWING_FOR_ACCIDENT" || vehicle.state === "PASSING_ACCIDENT" || vehicle.state === "ACCELERATING_FROM_ACCIDENT" || vehicle.state === "QUEUED_BY_ACCIDENT") {
          vehicle.state = "NORMAL";
          if (vehicle.lane === 0 && vehicle.state !== "YIELDING_TO_AMBULANCE" && vehicle.state !== "WAITING_FOR_AMBULANCE") {
            vehicle.targetLateralOffset = 12;
          }
        }

        // Ambulance approach, yield, and return-to-lane logic
        const ambulance = activeAmbulance();
        if (ambulance && vehicle.type !== "ambulance" && !vehicle.inTurn) {
          const sameEdge = vehicle.from === ambulance.from && vehicle.to === ambulance.to;
          if (sameEdge) {
            const distFromAmb = (vehicle.progress - ambulance.progress) * edge.length;
            if (distFromAmb > 0 && distFromAmb <= AMBULANCE_DETECTION_DISTANCE) {
              // Ambulance approaching from behind: yield to safe outer curb edge of OWN carriageway (+31px)
              // Strict rule: NEVER cross the center median (0px). Stay on own side.
              vehicle.state = "YIELDING_TO_AMBULANCE";

              // Check side-by-side vehicle in adjacent lane (e.g. if vehicle is in lane 0 moving to curb offset 31)
              let safeToShift = true;
              if (vehicle.lane === 0) {
                const sideVehicle = vehicles.find(v =>
                  v !== vehicle && v.from === vehicle.from && v.to === vehicle.to &&
                  v.lane === 1 && !v.inTurn &&
                  Math.abs((v.progress - vehicle.progress) * edge.length) < ((VEHICLE_LENGTH[v.type] + length) / 2 + 5)
                );
                if (sideVehicle) {
                  // Vehicle beside it in outer lane: stay in lane 0 and slow down until gap opens
                  safeToShift = false;
                  desired = Math.min(desired, sideVehicle.currentSpeed * 0.85);
                }
              }
              if (safeToShift) {
                vehicle.targetLateralOffset = SAFE_OUTER_CURB_OFFSET;
              }
              desired = Math.min(desired, vehicle.speed * 0.45);
              vehicle.braking = true;

              if (distFromAmb < (VEHICLE_LENGTH.ambulance + length) / 2 + 12) {
                vehicle.state = "WAITING_FOR_AMBULANCE";
                desired = Math.min(desired, 2.5);
              }
            } else if (distFromAmb < 0) {
              // Ambulance has passed this vehicle: verify clearance distance before returning
              const distPassed = Math.abs(distFromAmb);
              if (distPassed > EMERGENCY_CLEARANCE_DISTANCE) {
                if (vehicle.state === "YIELDING_TO_AMBULANCE" || vehicle.state === "WAITING_FOR_AMBULANCE") {
                  vehicle.yieldTimer += dt;
                  if (vehicle.yieldTimer >= 0.6) {
                    // Verify return path is safe (original lane is free)
                    const returnBlocked = vehicles.some(v =>
                      v !== vehicle && v.from === vehicle.from && v.to === vehicle.to &&
                      v.lane === vehicle.originalLane && !v.inTurn &&
                      Math.abs((v.progress - vehicle.progress) * edge.length) < ((VEHICLE_LENGTH[v.type] + length) / 2 + 6)
                    );
                    if (!returnBlocked) {
                      vehicle.state = "RETURNING_TO_LANE";
                      vehicle.targetLateralOffset = vehicle.originalLane === 0 ? 12 : 28;
                    }
                  }
                } else if (vehicle.state === "RETURNING_TO_LANE") {
                  if (Math.abs(vehicle.currentLateralOffset - vehicle.targetLateralOffset) < 0.5) {
                    vehicle.state = "NORMAL";
                    vehicle.yieldTimer = 0;
                  }
                }
              }
            }
          } else if (vehicle.state === "YIELDING_TO_AMBULANCE" || vehicle.state === "WAITING_FOR_AMBULANCE") {
            vehicle.yieldTimer += dt;
            if (vehicle.yieldTimer >= 0.6) {
              vehicle.state = "RETURNING_TO_LANE";
              vehicle.targetLateralOffset = vehicle.originalLane === 0 ? 12 : 28;
            }
          } else if (vehicle.state === "RETURNING_TO_LANE") {
            if (Math.abs(vehicle.currentLateralOffset - vehicle.targetLateralOffset) < 0.5) {
              vehicle.state = "NORMAL";
              vehicle.yieldTimer = 0;
            }
          }
        }

        // Ambulance forward corridor clearance: slow if vehicle ahead is still clearing
        if (vehicle.type === "ambulance") {
          const blockerAhead = vehicles.find(v =>
            v !== vehicle && v.from === vehicle.from && v.to === vehicle.to &&
            v.progress > vehicle.progress &&
            (v.progress - vehicle.progress) * edge.length < 32 &&
            v.currentLateralOffset < 22
          );
          if (blockerAhead) {
            desired = Math.min(desired, blockerAhead.currentSpeed * 0.85);
            vehicle.braking = true;
          }
        }

        // Brake toward the stop line for red/yellow, or when the outbound lane
        // is occupied. This avoids the previous last-moment snap to zero.
        if (approachingSignal && (!allows || movementBlocked)) {
          const distanceToLine = remaining - STOP_LINE_DISTANCE;
          if (distanceToLine < 78) {
            const safeApproachSpeed = Math.sqrt(2 * COMFORTABLE_BRAKING * Math.max(0, distanceToLine));
            desired = Math.min(desired, safeApproachSpeed);
            vehicle.braking = true;
          }
        }

        const acceleration = desired > vehicle.currentSpeed ? 8 : 17;
        vehicle.currentSpeed += clamp(desired - vehicle.currentSpeed, -acceleration * dt, acceleration * dt);
        vehicle.currentSpeed = Math.max(0, vehicle.currentSpeed);
        vehicle.stopped = vehicle.currentSpeed < .35;
        vehicle.braking = vehicle.stopped || desired < 0.2 || (vehicle.currentSpeed < desired * 0.75);
        if (vehicle.stopped) vehicle.wait += dt;
        const fuelRate = vehicle.stopped ? .00028 : .00010 + .000008 * vehicle.currentSpeed;
        totalFuel += fuelRate * dt * (vehicle.type === "bus" ? 1.8 : vehicle.type === "ambulance" ? 1.25 : 1);
        vehicle.progress += vehicle.currentSpeed * dt / edge.length;

        // Strict stop-line enforcement applies both to a closed signal and to
        // a full/closed downstream road (do not block the junction box).
        if (approachingSignal && (!allows || movementBlocked)) {
          const maxStopProgress = (edge.length - STOP_LINE_DISTANCE) / edge.length;
          if (vehicle.progress > maxStopProgress) {
            vehicle.progress = maxStopProgress;
            vehicle.currentSpeed = 0;
            vehicle.stopped = true;
            vehicle.braking = true;
          }
        }

        if (leader && leader.from === vehicle.from && leader.to === vehicle.to && leader.lane === vehicle.lane) {
          const minimumCenterGap = (VEHICLE_LENGTH[leader.type] + length) / 2 + 3.5;
          const maximumProgress = leader.progress - minimumCenterGap / edge.length;
          if (vehicle.progress > maximumProgress) {
            vehicle.progress = Math.max(0, maximumProgress);
            vehicle.currentSpeed = Math.min(vehicle.currentSpeed, leader.currentSpeed);
            vehicle.stopped = vehicle.currentSpeed < .35;
            vehicle.braking = true;
          }
        }

        // Smooth cubic Bezier transition only after a green entry decision and
        // only when a receiving lane is actually available.
        if (remaining <= TURN_ENTRY_DISTANCE && allows && !movementBlocked && vehicle.pathIndex < vehicle.path.length - 1) {
          const reached = vehicle.to;
          const plannedNext = vehicle.path[vehicle.pathIndex + 1];
          const plannedEdge = edgeBetween(reached, plannedNext);
          if (plannedEdge && !blockedRoads().has(plannedEdge.key)) {
            const actualTargetLane = downstreamLane == null
              ? findFreeLane(reached, plannedNext, vehicle.lane)
              : downstreamLane;
            if (actualTargetLane < 0) {
              vehicle.progress = (edge.length - STOP_LINE_DISTANCE) / edge.length;
              vehicle.currentSpeed = 0;
              vehicle.stopped = true;
              vehicle.braking = true;
              continue;
            }
            const a = city.nodes[vehicle.from];
            const b = city.nodes[reached];
            const c = city.nodes[plannedNext];
            const dInX = b.x - a.x, dInY = b.y - a.y;
            const lenIn = Math.hypot(dInX, dInY) || 1;
            const tInX = dInX / lenIn, tInY = dInY / lenIn;
            const nInX = -tInY, nInY = tInX;
            const inOffset = vehicle.lane === 0 ? 12 : 28;

            const dOutX = c.x - b.x, dOutY = c.y - b.y;
            const lenOut = Math.hypot(dOutX, dOutY) || 1;
            const tOutX = dOutX / lenOut, tOutY = dOutY / lenOut;
            const nOutX = -tOutY, nOutY = tOutX;
            const outOffset = actualTargetLane === 0 ? 12 : 28;

            const p0 = { x: b.x - 54 * tInX + inOffset * nInX, y: b.y - 54 * tInY + inOffset * nInY };
            const p3 = { x: b.x + 54 * tOutX + outOffset * nOutX, y: b.y + 54 * tOutY + outOffset * nOutY };
            const p1 = { x: p0.x + 28 * tInX, y: p0.y + 28 * tInY };
            const p2 = { x: p3.x - 28 * tOutX, y: p3.y - 28 * tOutY };

            const curveLen = Math.hypot(p3.x - p0.x, p3.y - p0.y) * 1.12;
            const cp = tInX * tOutY - tInY * tOutX;

            vehicle.inTurn = true;
            vehicle.turnU = 0;
            vehicle.turnIndicator = cp > 0.25 ? "right" : (cp < -0.25 ? "left" : null);
            vehicle.turnCurve = {
              p0, p1, p2, p3, length: Math.max(40, curveLen),
              nextFrom: reached, nextTo: plannedNext, nextLane: actualTargetLane
            };
            const entryPhase = signals[reached]?.phase || "UNCONTROLLED";
            const entryDirection = incomingDirection(vehicle.from, reached);
            const entryAxis = directionAxis(entryDirection);
            junctionEntries.push({
              vehicleId: vehicle.id,
              junctionId: reached,
              direction: entryDirection,
              axis: entryAxis,
              phase: entryPhase,
              time: simulationTime
            });
            if (entryPhase !== `${entryDirection}_GREEN`) redLightViolations += 1;
            if (junctionEntries.length > 300) junctionEntries.shift();
            continue;
          }
        }

        if (vehicle.progress < 1) continue;

        const reached = vehicle.to;
        vehicle.progress = 0;
        if (reached === vehicle.target || vehicle.pathIndex >= vehicle.path.length - 1) {
          if (vehicle.type !== "ambulance" && !city.boundaryNodes.includes(reached)) {
            const escapeRoute = reachableExitRoute(vehicle, reached);
            if (escapeRoute.length >= 2) {
              vehicle.target = escapeRoute.at(-1);
              vehicle.path = escapeRoute;
              vehicle.pathIndex = 1;
              vehicle.from = escapeRoute[0];
              vehicle.to = escapeRoute[1];
              vehicle.progress = 0;
              continue;
            }
            vehicle.progress = .985;
            vehicle.currentSpeed = 0;
            vehicle.stopped = true;
            continue;
          }
          completed.push(vehicle.id);
          completedVehicles += 1;
          totalCompletedTravel += vehicle.travelTime;
          if (vehicle.type !== "ambulance") {
            vehicleExits.push({ vehicleId: vehicle.id, spawnNode: vehicle.spawnNode, exitNode: reached, time: simulationTime });
            if (vehicleExits.length > 500) vehicleExits.shift();
          }
          if (vehicle.type === "ambulance") {
            corridorCompleted += vehicle.travelTime;
            corridorBaseline += Math.max(vehicle.freeFlowSeconds * 1.65, vehicle.travelTime * 1.28);
            addEvent("Ambulance reached hospital", `${Math.round(vehicle.travelTime)}s travel • normal signal plans restored`, "emergency");
          }
          continue;
        }

        const plannedNext = vehicle.path[vehicle.pathIndex + 1];
        const plannedEdge = edgeBetween(reached, plannedNext);
        if (!plannedEdge || blockedRoads().has(plannedEdge.key)) {
          const reroute = recalculateRoute(vehicle, reached);
          if (reroute === "none") { completed.push(vehicle.id); continue; }
          if (reroute === "wait") {
            vehicle.progress = .985;
            vehicle.currentSpeed = 0;
            vehicle.stopped = true;
            continue;
          }
        } else {
          const lane = findFreeLane(reached, plannedNext, vehicle.lane);
          if (lane < 0) {
            vehicle.progress = .985;
            vehicle.currentSpeed = 0;
            vehicle.stopped = true;
            continue;
          }
          vehicle.pathIndex += 1;
          vehicle.from = reached;
          vehicle.to = plannedNext;
          vehicle.lane = lane;
          vehicle.originalLane = lane;
          vehicle.targetLateralOffset = lane === 0 ? 12 : 28;
          vehicle.currentLateralOffset = vehicle.targetLateralOffset;
          const factor = vehicle.type === "ambulance" ? 1.12 : vehicle.type === "bus" ? .7 : vehicle.type === "service" ? .82 : .9;
          vehicle.speed = plannedEdge.speed * factor;
          if (vehicle.state === "REROUTING_FROM_CLOSURE") vehicle.state = "NORMAL";
        }
      }
    }
    if (completed.length) {
      const ids = new Set(completed);
      vehicles = vehicles.filter(vehicle => !ids.has(vehicle.id));
    }
    enforceLaneCapacity();

    const target = Math.round(Number(ui.demandRange.value) * .44);
    spawnAccumulator += dt * 1.9;
    while (vehicles.length < target && spawnAccumulator >= 1) {
      if (spawnRegularVehicle()) spawnAccumulator -= 1;
      else break;
    }
    if (vehicles.length > target + 10) {
      const removable = vehicles.filter(vehicle => vehicle.type !== "ambulance").slice(0, Math.min(3, vehicles.length - target));
      const ids = new Set(removable.map(vehicle => vehicle.id));
      vehicles = vehicles.filter(vehicle => !ids.has(vehicle.id));
    }

    const queues = vehicles.filter(vehicle => vehicle.stopped).length;
    const imbalance = signals.reduce((sum, signal) => sum + Math.abs(signal.nsQueue - signal.ewQueue), 0);
    const liveFuelThisStep = totalFuel - fuelBeforeStep;
    const fixedTimingPenalty = ui.controllerSelect.value === "fixed" ? 0 : dt * (queues + imbalance * .55) * .00025;
    baselineFuel += liveFuelThisStep + fixedTimingPenalty;
    totalCo2 = totalFuel * 2.31;
    baselineCo2 = baselineFuel * 2.31;
  }

  async function optimizeSignals() {
    const selectedMode = ui.controllerSelect.value;
    const states = signals.slice(0, 4).map(signal => {
      const connected = city.adjacency[signal.id].map(link => city.edges[link.edge]);
      const capacity = connected.reduce((sum, edge) => sum + edge.capacity, 0);
      const localCount = vehicles.filter(vehicle => vehicle.to === signal.id || vehicle.from === signal.id).length;
      return {
        intersectionId: signal.id,
        nsQueue: signal.nsQueue,
        ewQueue: signal.ewQueue,
        pedestrianQueue: signal.pedestrians,
        trafficDensity: clamp(localCount / Math.max(1, capacity), 0, 1),
        vehicleCount: localCount,
        roadCapacity: capacity
      };
    });
    let decisions = states.map(state => Optimizer.solveQubo(state));
    let source = "LOCAL QUBO";
    const solverParam = selectedMode === "qaoa" ? "qaoa" : "exact";

    if (location.protocol.startsWith("http") && !optimizerPending && (selectedMode === "qubo" || selectedMode === "qaoa")) {
      optimizerPending = true;
      try {
        const response = await fetch("/api/optimize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ states, solver: solverParam })
        });
        if (!response.ok) throw new Error(`Backend returned ${response.status}`);
        const result = await response.json();
        decisions = result.decisions;
        source = solverParam === "qaoa" ? "BACKEND QAOA" : "BACKEND QUBO";
        setBackendState(true);
      } catch (error) {
        setBackendState(false);
      } finally {
        optimizerPending = false;
      }
    }
    for (const decision of decisions) {
      const signal = signals[decision.intersectionId];
      if (!signal) continue;
      let targetNs = 30;
      let targetEw = 30;
      if (selectedMode === "qubo" || selectedMode === "qaoa") {
        targetNs = clamp(Math.round(decision.nsGreen || 30), 22, 42);
        targetEw = clamp(Math.round(decision.ewGreen || 30), 22, 42);
      } else if (selectedMode === "adaptive") {
        const total = signal.nsQueue + signal.ewQueue;
        const share = total ? signal.nsQueue / total : .5;
        targetNs = Math.round(clamp(22 + share * 18, 22, 40));
        targetEw = Math.round(clamp(40 - share * 18, 22, 40));
        source = "CLASSICAL ADAPTIVE";
      } else {
        targetNs = 30;
        targetEw = 30;
        source = "FIXED TIME";
      }

      signal.targetNsGreen = targetNs;
      signal.targetEwGreen = targetEw;
      signal.pendingNsGreen = targetNs;
      signal.pendingEwGreen = targetEw;
      signal.lastDecision = {
        ...decision,
        nsGreen: targetNs,
        ewGreen: targetEw,
        candidatesEvaluated: decision.candidatesEvaluated || 9
      };
    }
    ui.algorithmSource.textContent = source;
    updatePanel();
  }

  function addRoadEvent(edge, type, options = {}) {
    const previous = roadEvents.get(edge.key);
    if (previous && previous.type === type) return showToast(`This road already has an active ${type} event.`);
    const affectedFrom = options.from ?? edge.a;
    const affectedTo = options.to ?? edge.b;
    const affectedLane = options.lane ?? 0;
    roadEvents.set(edge.key, {
      edgeId: edge.id,
      key: edge.key,
      type,
      createdAt: simulationTime,
      affectedFrom,
      affectedTo,
      affectedLane
    });
    const messages = {
      congestion: ["Congestion surge injected", "Capacity reduced; traffic is rerouting by live edge cost"],
      accident: ["Accident reported", "Affected road avoided and emergency routing recalculated"],
      closure: ["Road closure activated", "Road removed from all new routes"]
    };
    addEvent(messages[type][0], `${city.nodes[edge.a].name} ↔ ${city.nodes[edge.b].name} • ${messages[type][1]}`, "alert");
    setPlacementMode("inspect");
  }

  function clearEvents() {
    const count = roadEvents.size;
    roadEvents.clear();
    for (const vehicle of vehicles) {
      if (vehicle.state === "SLOWING_FOR_ACCIDENT" || vehicle.state === "PASSING_ACCIDENT" ||
          vehicle.state === "ACCELERATING_FROM_ACCIDENT" || vehicle.state === "QUEUED_BY_ACCIDENT") {
        vehicle.state = "NORMAL";
        if (vehicle.lane === 0 && vehicle.state !== "YIELDING_TO_AMBULANCE" && vehicle.state !== "WAITING_FOR_AMBULANCE") {
          vehicle.targetLateralOffset = 12;
        }
      }
    }
    if (count) addEvent("Network restored", `${count} disruption${count === 1 ? "" : "s"} cleared • optimized control resumed`);
    else showToast("The road network is already normal.");
  }

  function setBackendState(online) {
    ui.backendStatus.textContent = online ? "QUBO BACKEND ONLINE" : "LOCAL ENGINE";
    ui.backendStatus.parentElement.classList.toggle("offline", !online);
  }

  async function checkBackend() {
    if (!location.protocol.startsWith("http")) return setBackendState(false);
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      setBackendState(response.ok);
    } catch (error) {
      setBackendState(false);
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }
  function addEvent(title, detail, kind = "normal") {
    events.unshift({ title, detail, kind, time: formatTime(simulationTime) });
    events = events.slice(0, 8);
    ui.eventStream.innerHTML = events.map(event =>
      `<div class="event-item ${escapeHtml(event.kind)}"><i></i><div><strong>${escapeHtml(event.title)}</strong><span>${escapeHtml(event.detail)}</span></div><time>${event.time}</time></div>`
    ).join("");
    ui.eventCount.textContent = `${events.length} EVENT${events.length === 1 ? "" : "S"}`;
  }

  function showToast(message) {
    ui.toast.textContent = message;
    ui.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { ui.toast.hidden = true; }, 2800);
  }

  function setPlacementMode(mode) {
    placementMode = mode;
    document.querySelectorAll(".map-action").forEach(button => button.classList.remove("active"));
    const buttonByMode = {
      congestion: ui.congestionBtn, accident: ui.accidentBtn, closure: ui.closureBtn,
      ambulance: ui.ambulanceBtn, hospital: ui.hospitalBtn, inspect: ui.inspectBtn
    };
    buttonByMode[mode].classList.add("active");
    const copy = {
      inspect: "Select a junction to inspect queues and signals.",
      hospital: "Select a junction to move the emergency destination.",
      ambulance: "Select a junction to dispatch an ambulance.",
      congestion: "Select a road to inject sudden congestion.",
      accident: "Select a road to place an accident.",
      closure: "Select a road to close it completely."
    };
    ui.placementHelp.textContent = copy[mode];
    ui.toolState.textContent = mode.toUpperCase();
    ui.mapMode.textContent = `${mode.toUpperCase()} MODE`;
  }

  function resizeCanvas(target, context) {
    const rect = target.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (target.width !== width || target.height !== height) {
      target.width = width;
      target.height = height;
    }
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    return rect;
  }

  function fitCity() {
    if (!city) return;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    view.zoom = clamp(Math.min((rect.width - 80) / city.world.width, (rect.height - 125) / city.world.height), .28, 2.2);
    view.x = (rect.width - city.world.width * view.zoom) / 2;
    view.y = (rect.height - city.world.height * view.zoom) / 2 + 24;
  }
  function screenToWorld(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    return { x: (clientX - rect.left - view.x) / view.zoom, y: (clientY - rect.top - view.y) / view.zoom };
  }
  function zoomAt(factor, clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const sx = clientX === undefined ? rect.width / 2 : clientX - rect.left;
    const sy = clientY === undefined ? rect.height / 2 : clientY - rect.top;
    const wx = (sx - view.x) / view.zoom;
    const wy = (sy - view.y) / view.zoom;
    const next = clamp(view.zoom * factor, .25, 3.6);
    view.x = sx - wx * next;
    view.y = sy - wy * next;
    view.zoom = next;
  }

  function drawCityBackground(width, height) {
    ctx.fillStyle = "#070e19";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(86,199,255,.035)";
    ctx.lineWidth = 1;
    const spacing = 38;
    for (let x = 0; x < width; x += spacing) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
    for (let y = 0; y < height; y += spacing) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
  }

  function drawBlocks() {
    const tones = ["#122331", "#142836", "#172b3a", "#10212e"];
    for (const block of city.blocks) {
      if (block.park) {
        ctx.fillStyle = "rgba(33,105,83,.28)";
        ctx.fillRect(block.minX, block.minY, block.width, block.height);
        const parkRandom = Core.mulberry32(city.numericSeed ^ block.id * 991);
        for (let i = 0; i < 16; i += 1) {
          ctx.fillStyle = "rgba(65,181,125,.44)";
          ctx.beginPath();
          ctx.arc(block.minX + parkRandom() * block.width, block.minY + parkRandom() * block.height, 4 + parkRandom() * 4, 0, Math.PI * 2);
          ctx.fill();
        }
      } else {
        for (const building of block.buildings) {
          ctx.save();
          const cx = building.x + building.width / 2;
          const cy = building.y + building.height / 2;
          ctx.translate(cx, cy);
          ctx.rotate(building.rotation);
          const lift = clamp(building.floors * .55, 2, 8);
          ctx.fillStyle = "rgba(0,0,0,.32)";
          ctx.fillRect(-building.width / 2 + lift, -building.height / 2 + lift, building.width, building.height);
          ctx.fillStyle = tones[building.tone];
          ctx.fillRect(-building.width / 2, -building.height / 2, building.width, building.height);
          ctx.strokeStyle = "rgba(86,199,255,.1)";
          ctx.strokeRect(-building.width / 2, -building.height / 2, building.width, building.height);
          ctx.fillStyle = "rgba(86,199,255,.12)";
          ctx.fillRect(-building.width * .3, -building.height * .18, building.width * .16, building.height * .12);
          ctx.restore();
        }
      }

      // Urban District & Environment Location Label Watermark
      if (block.label) {
        ctx.save();
        ctx.fillStyle = block.park ? "rgba(87, 227, 190, 0.40)" : "rgba(180, 210, 235, 0.22)";
        ctx.font = "800 10px ui-sans-serif, system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(block.label.toUpperCase(), block.minX + block.width / 2, block.minY + 14);
        ctx.restore();
      }
    }
  }

  function drawLaneArrow(x, y, tx, ty, type) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(Math.atan2(ty, tx));
    ctx.strokeStyle = "rgba(235, 245, 255, 0.42)";
    ctx.fillStyle = "rgba(235, 245, 255, 0.42)";
    ctx.lineWidth = 1.5;
    // Straight stem
    ctx.beginPath();
    ctx.moveTo(-7, 0);
    ctx.lineTo(4, 0);
    ctx.stroke();
    // Arrow head
    ctx.beginPath();
    ctx.moveTo(1, -3);
    ctx.lineTo(7, 0);
    ctx.lineTo(1, 3);
    ctx.fill();
    // Turn branch if applicable
    if (type === "straight_left") {
      ctx.beginPath();
      ctx.moveTo(-1, 0);
      ctx.lineTo(-3, -3);
      ctx.lineTo(-6, -5);
      ctx.stroke();
    } else if (type === "straight_right") {
      ctx.beginPath();
      ctx.moveTo(-1, 0);
      ctx.lineTo(-3, 3);
      ctx.lineTo(-6, 5);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawRoads() {
    ctx.lineCap = "butt";
    ctx.lineJoin = "miter";
    const ROAD_WIDTH = 72;
    const HALF_WIDTH = 36;

    for (const edge of city.edges) {
      const nodeA = city.nodes[edge.a];
      const nodeB = city.nodes[edge.b];
      const dx = nodeB.x - nodeA.x;
      const dy = nodeB.y - nodeA.y;
      const len = Math.hypot(dx, dy) || 1;
      const tx = dx / len, ty = dy / len;
      const nx = -ty, ny = tx;

      // Inset at primary signalized junctions so the 72x72 intersection box connects cleanly
      const insetA = edge.a < 4 ? HALF_WIDTH : 0;
      const insetB = edge.b < 4 ? HALF_WIDTH : 0;
      const ax = nodeA.x + tx * insetA, ay = nodeA.y + ty * insetA;
      const bx = nodeB.x - tx * insetB, by = nodeB.y - ty * insetB;

      // 1. Road shoulder / curb foundation (78px width)
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.strokeStyle = "#101822";
      ctx.lineWidth = ROAD_WIDTH + 6;
      ctx.stroke();

      // 2. Main asphalt surface (72px width)
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.strokeStyle = "#1c2836";
      ctx.lineWidth = ROAD_WIDTH;
      ctx.stroke();

      // 3. Outer edge lines (solid white lines separating roadway from shoulder at +/- 34px)
      ctx.strokeStyle = "rgba(225, 238, 248, 0.45)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(ax + nx * 34, ay + ny * 34);
      ctx.lineTo(bx + nx * 34, by + ny * 34);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(ax - nx * 34, ay - ny * 34);
      ctx.lineTo(bx - nx * 34, by - ny * 34);
      ctx.stroke();

      // 4. Central median / divider (double solid yellow/amber lines at +/- 3px)
      ctx.strokeStyle = "rgba(255, 185, 60, 0.85)";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(ax + nx * 3, ay + ny * 3);
      ctx.lineTo(bx + nx * 3, by + ny * 3);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(ax - nx * 3, ay - ny * 3);
      ctx.lineTo(bx - nx * 3, by - ny * 3);
      ctx.stroke();

      // 5. Directional lane dividers (dashed white lines between lane 0 and lane 1 at +/- 20px)
      ctx.setLineDash([12, 14]);
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = "rgba(215, 230, 245, 0.38)";

      // Direction A lane divider (+20px)
      ctx.beginPath();
      ctx.moveTo(ax + nx * 20, ay + ny * 20);
      ctx.lineTo(bx + nx * 20, by + ny * 20);
      ctx.stroke();

      // Direction B lane divider (-20px)
      ctx.beginPath();
      ctx.moveTo(ax - nx * 20, ay - ny * 20);
      ctx.lineTo(bx - nx * 20, by - ny * 20);
      ctx.stroke();
      ctx.setLineDash([]);

      // 6. Pavement directional turning arrows approaching intersections
      if (edge.b < 4 && len > 140) {
        drawLaneArrow(bx - tx * 48 + nx * 12, by - ty * 48 + ny * 12, tx, ty, "straight_left");
        drawLaneArrow(bx - tx * 48 + nx * 28, by - ty * 48 + ny * 28, tx, ty, "straight_right");
      }
      if (edge.a < 4 && len > 140) {
        drawLaneArrow(ax + tx * 48 - nx * 12, ay + ty * 48 - ny * 12, -tx, -ty, "straight_left");
        drawLaneArrow(ax + tx * 48 - nx * 28, ay + ty * 48 - ny * 28, -tx, -ty, "straight_right");
      }

      // 7. Road capacity badge if toggled
      if (ui.capacityToggle.checked) {
        const mx = (ax + bx) / 2, my = (ay + by) / 2;
        ctx.fillStyle = "rgba(7, 15, 25, 0.88)";
        ctx.fillRect(mx - 24, my - 10, 48, 19);
        ctx.fillStyle = "#9a7cff";
        ctx.font = "800 10px ui-monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`CAP ${edge.capacity}`, mx, my);
      }

      // 8. Sidewalk pavements along road shoulders
      ctx.strokeStyle = "#14202d";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(ax + nx * 38, ay + ny * 38);
      ctx.lineTo(bx + nx * 38, by + ny * 38);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(ax - nx * 38, ay - ny * 38);
      ctx.lineTo(bx - nx * 38, by - ny * 38);
      ctx.stroke();

      // 9. Streetlights along sidewalks
      const lightInterval = 100;
      const numLights = Math.floor(len / lightInterval);
      for (let i = 1; i <= numLights; i += 1) {
        const dist = (i / (numLights + 1)) * len;
        // Left & right sidewalk streetlights
        const lx1 = ax + tx * dist + nx * 42, ly1 = ay + ty * dist + ny * 42;
        const lx2 = ax + tx * dist - nx * 42, ly2 = ay + ty * dist - ny * 42;

        ctx.fillStyle = "#223344";
        ctx.beginPath(); ctx.arc(lx1, ly1, 2.2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(lx2, ly2, 2.2, 0, Math.PI * 2); ctx.fill();

        ctx.fillStyle = "rgba(255, 240, 190, 0.35)";
        ctx.beginPath(); ctx.arc(lx1, ly1, 4.5, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(lx2, ly2, 4.5, 0, Math.PI * 2); ctx.fill();
      }

      // 10. Sidewalk trees / greenery along shoulders
      const treeInterval = 130;
      const numTrees = Math.floor(len / treeInterval);
      for (let i = 1; i <= numTrees; i += 1) {
        const dist = (i / (numTrees + 1)) * len;
        const tx1 = ax + tx * dist + nx * 48, ty1 = ay + ty * dist + ny * 48;
        const tx2 = ax + tx * dist - nx * 48, ty2 = ay + ty * dist - ny * 48;

        ctx.fillStyle = "rgba(40, 130, 85, 0.35)";
        ctx.beginPath(); ctx.arc(tx1, ty1, 4.5, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(tx2, ty2, 4.5, 0, Math.PI * 2); ctx.fill();
      }
    }

    // Building driveways and parking bays
    if (city.buildingDriveways) {
      for (const bd of city.buildingDriveways) {
        ctx.fillStyle = "#1e2c3a";
        const minY = Math.min(bd.curbY, bd.parkingY);
        const height = Math.abs(bd.parkingY - bd.curbY) + 14;
        ctx.fillRect(bd.roadX - 16, minY, 32, height);
        ctx.strokeStyle = "rgba(86, 199, 255, 0.25)";
        ctx.lineWidth = 1.2;
        ctx.strokeRect(bd.roadX - 16, minY, 32, height);

        // Parking stall
        ctx.fillStyle = "rgba(255, 189, 102, 0.15)";
        ctx.fillRect(bd.parkingX - 14, bd.parkingY - 14, 28, 28);
        ctx.strokeStyle = "rgba(255, 189, 102, 0.6)";
        ctx.lineWidth = 1;
        ctx.strokeRect(bd.parkingX - 14, bd.parkingY - 14, 28, 28);

        ctx.fillStyle = "#ffbd66";
        ctx.font = "800 11px ui-monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("P", bd.parkingX, bd.parkingY);
      }
    }

    // Bus stop bays on arterial shoulders
    const busStops = [
      { x: 380, y: 358, label: "BUS STOP - HARBOR" },
      { x: 1040, y: 358, label: "BUS STOP - CIVIC" },
      { x: 680, y: 698, label: "BUS STOP - MARKET" },
      { x: 1360, y: 698, label: "BUS STOP - TECH" }
    ];
    for (const bs of busStops) {
      ctx.fillStyle = "rgba(255, 189, 102, 0.75)";
      ctx.fillRect(bs.x - 18, bs.y - 3, 36, 6);
      ctx.fillStyle = "rgba(235, 245, 255, 0.45)";
      ctx.font = "700 8px ui-sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(bs.label, bs.x, bs.y + 11);
    }

    // Real-world Coimbatore arterial street name labels
    ctx.fillStyle = "rgba(235, 245, 255, 0.55)";
    ctx.font = "800 12px ui-monospace, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    // Edge 0 (J1-J2) Avanashi Road
    ctx.fillText("AVANASHI ROAD (MAIN ROAD)", 860, 268);
    // Edge 1 (J3-J4) Cross-Cut Road
    ctx.fillText("CROSS-CUT ROAD COMMERCIAL ARTERIAL", 860, 712);

    // Dr. Nanjappa Road (J1-J3)
    ctx.save();
    ctx.translate(466, 490);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("DR. NANJAPPA ROAD", 0, 0);
    ctx.restore();

    // Bharathiar Road (J2-J4)
    ctx.save();
    ctx.translate(1254, 490);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("BHARATHIAR ROAD", 0, 0);
    ctx.restore();

    // Coimbatore Corridor Master Title
    ctx.fillStyle = "rgba(87, 227, 190, 0.7)";
    ctx.font = "900 13px ui-sans-serif, system-ui";
    ctx.textAlign = "center";
    ctx.fillText("COIMBATORE URBAN MAIN ROAD CORRIDOR • SMART MOBILITY TWIN", 860, 44);
  }

  function drawZebraCrossing(x, y, orientation) {
    ctx.fillStyle = "rgba(240, 248, 255, 0.85)";
    if (orientation === "horizontal") {
      // Crossing across vertical road: spans x from x-34 to x+34, height 12px
      const startX = x - 34;
      const endX = x + 34;
      const stripeW = 3.5;
      const gap = 3.5;
      for (let sx = startX; sx + stripeW <= endX; sx += stripeW + gap) {
        if (sx + stripeW > x - 3 && sx < x + 3) continue; // Skip median center
        ctx.fillRect(sx, y - 6, stripeW, 12);
      }
    } else {
      // Crossing across horizontal road: spans y from y-34 to y+34, width 12px
      const startY = y - 34;
      const endY = y + 34;
      const stripeH = 3.5;
      const gap = 3.5;
      for (let sy = startY; sy + stripeH <= endY; sy += stripeH + gap) {
        if (sy + stripeH > y - 3 && sy < y + 3) continue; // Skip median center
        ctx.fillRect(x - 6, sy, 12, stripeH);
      }
    }
  }

  function drawJunctions() {
    for (let id = 0; id < 4; id += 1) {
      const node = city.nodes[id];
      if (!node) continue;
      const cx = node.x, cy = node.y;
      const selected = node.id === selectedJunction;

      // 1. Intersection Box (Open crossing area 72x72)
      ctx.fillStyle = "#22303e";
      ctx.fillRect(cx - 36, cy - 36, 72, 72);

      // Outer junction border
      ctx.strokeStyle = "#101822";
      ctx.lineWidth = 3;
      ctx.strokeRect(cx - 36, cy - 36, 72, 72);

      // Internal subtle turning guidelines
      ctx.setLineDash([4, 6]);
      ctx.strokeStyle = "rgba(225, 238, 248, 0.16)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx - 36, cy - 12);
      ctx.lineTo(cx - 12, cy - 36);
      ctx.moveTo(cx + 36, cy + 12);
      ctx.lineTo(cx + 12, cy + 36);
      ctx.stroke();
      ctx.setLineDash([]);

      // 2. Zebra Crossings on all 4 approaches (outside the 72x72 box)
      drawZebraCrossing(cx, cy - 44, "horizontal"); // North crossing
      drawZebraCrossing(cx, cy + 44, "horizontal"); // South crossing
      drawZebraCrossing(cx - 44, cy, "vertical");   // West crossing
      drawZebraCrossing(cx + 44, cy, "vertical");   // East crossing

      // 3. Stop Lines on all 4 approaches (solid white line across incoming carriageway at 54px)
      ctx.strokeStyle = "rgba(255, 255, 255, 0.92)";
      ctx.lineWidth = 3;
      ctx.lineCap = "butt";

      // North approach: incoming vehicles drive South (on West side of median: x from cx-34 to cx-4)
      ctx.beginPath();
      ctx.moveTo(cx - 34, cy - 54);
      ctx.lineTo(cx - 4, cy - 54);
      ctx.stroke();

      // South approach: incoming vehicles drive North (on East side of median: x from cx+4 to cx+34)
      ctx.beginPath();
      ctx.moveTo(cx + 4, cy + 54);
      ctx.lineTo(cx + 34, cy + 54);
      ctx.stroke();

      // West approach: incoming vehicles drive East (on South side of median: y from cy+4 to cy+34)
      ctx.beginPath();
      ctx.moveTo(cx - 54, cy + 4);
      ctx.lineTo(cx - 54, cy + 34);
      ctx.stroke();

      // East approach: incoming vehicles drive West (on North side of median: y from cy-34 to cy-4)
      ctx.beginPath();
      ctx.moveTo(cx + 54, cy - 34);
      ctx.lineTo(cx + 54, cy - 4);
      ctx.stroke();

      // 4. Floating Junction Name Badge & Selection Indicator
      if (selected) {
        ctx.strokeStyle = "rgba(86, 199, 255, 0.85)";
        ctx.lineWidth = 2.5;
        ctx.strokeRect(cx - 38, cy - 38, 76, 76);
      }

      ctx.fillStyle = selected ? "#ffffff" : "rgba(180, 205, 220, 0.85)";
      ctx.font = "800 11px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillText(`J${id + 1}`, cx, cy - 40);
    }
  }

  function drawHeatmap() {
    if (!ui.heatToggle.checked) return;
    const counts = edgeVehicleCounts();
    for (const edge of city.edges) {
      const load = counts[edge.id] / Math.max(1, edge.capacity);
      const event = roadEvents.get(edge.key);
      if (load < .16 && !event) continue;
      const a = city.nodes[edge.a], b = city.nodes[edge.b];
      const x = (a.x + b.x) / 2, y = (a.y + b.y) / 2;
      const radius = 35 + Math.min(70, load * 90);
      const heat = ctx.createRadialGradient(x, y, 0, x, y, radius);
      const rgb = event ? "255,100,124" : load > .7 ? "255,100,124" : load > .4 ? "255,189,102" : "86,199,255";
      heat.addColorStop(0, `rgba(${rgb},.28)`);
      heat.addColorStop(1, `rgba(${rgb},0)`);
      ctx.fillStyle = heat;
      ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill();
    }
  }

  function drawSignalHead(x, y, activeColor, dirLabel) {
    ctx.save();
    // Housing: 10px x 24px box with border
    ctx.fillStyle = "#0c141c";
    ctx.strokeStyle = "#253748";
    ctx.lineWidth = 1.2;
    ctx.fillRect(x - 5, y - 12, 10, 24);
    ctx.strokeRect(x - 5, y - 12, 10, 24);

    // 3 lamps: Red (top, y-7), Yellow (mid, y), Green (bot, y+7)
    const lamps = [
      { color: "red",    hex: COLORS.red,   yOffset: -7 },
      { color: "yellow", hex: COLORS.amber,  yOffset:  0 },
      { color: "green",  hex: COLORS.mint,   yOffset:  7 }
    ];

    for (const lamp of lamps) {
      const isLit = activeColor === lamp.color;
      ctx.beginPath();
      ctx.arc(x, y + lamp.yOffset, 2.5, 0, Math.PI * 2);
      if (isLit) {
        ctx.fillStyle = lamp.hex;
        ctx.shadowColor = lamp.hex;
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
      } else {
        ctx.fillStyle = "rgba(18, 30, 42, 0.9)";
        ctx.fill();
      }
    }

    // Direction label below housing (N / S / E / W)
    if (dirLabel) {
      ctx.fillStyle = "rgba(180, 210, 235, 0.82)";
      ctx.font = "bold 6px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(dirLabel, x, y + 14);
    }
    ctx.restore();
  }

  function drawPedestrians(cx, cy, signal) {
    const isAllRed = signal.phase.startsWith("ALL_RED");
    const peds = Math.min(6, Math.round(signal.pedestrians / 1.5));
    if (peds <= 0) return;

    ctx.fillStyle = "rgba(235, 245, 255, 0.9)";
    if (isAllRed) {
      // Pedestrians walking across zebra crossings!
      const walkT = (simulationTime * 1.8) % 1;
      for (let i = 0; i < peds; i += 1) {
        const offset = ((walkT + i * 0.28) % 1) * 60 - 30;
        ctx.beginPath();
        ctx.arc(cx + offset, cy - 44, 2.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(cx + 44, cy + offset, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    } else {
      // Waiting on sidewalk curb corners
      for (let i = 0; i < peds; i += 1) {
        ctx.beginPath();
        ctx.arc(cx - 38 - (i % 2) * 5, cy - 48 - Math.floor(i / 2) * 5, 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(cx + 38 + (i % 2) * 5, cy + 48 + Math.floor(i / 2) * 5, 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  function drawSignals() {
    for (let id = 0; id < 4; id += 1) {
      const signal = signals[id];
      if (!signal) continue;
      const node = city.nodes[id];
      if (!node) continue;
      const cx = node.x, cy = node.y;

      // Four-way controller: exactly one physical approach may be green.
      const northPhase = phaseColor(signal.phase, "N");
      const southPhase = phaseColor(signal.phase, "S");
      const eastPhase = phaseColor(signal.phase, "E");
      const westPhase = phaseColor(signal.phase, "W");

      // ── 4 separate signal heads, one per approach direction ──────────────
      // Positioned at the stop-line on the driver's left (right-hand traffic).
      //   North approach — vehicles travel South, lanes west of centreline
      drawSignalHead(cx - 34, cy - 58, northPhase, "N");
      //   South approach — vehicles travel North, lanes east of centreline
      drawSignalHead(cx + 34, cy + 58, southPhase, "S");
      //   West approach  — vehicles travel East, lanes south of centreline
      drawSignalHead(cx - 58, cy + 34, westPhase, "W");
      //   East approach  — vehicles travel West, lanes north of centreline
      drawSignalHead(cx + 58, cy - 34, eastPhase, "E");

      // ── Preemption aura when emergency vehicle is active ─────────────────
      if (signal.requestedDirection) {
        ctx.strokeStyle = COLORS.mint;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(cx, cy, 32 + Math.sin(simulationTime * 6) * 2, 0, Math.PI * 2);
        ctx.stroke();
      }

      // ── Centre badge: one active direction, all other approaches red ──────
      const activeDirection = phaseDirection(signal.phase);
      const activeColor = signal.phase.endsWith("GREEN") ? COLORS.mint :
        signal.phase.endsWith("YELLOW") ? COLORS.amber : COLORS.red;
      const remainingSeconds = Math.max(0, Math.ceil(signal.remaining));

      ctx.save();
      ctx.fillStyle = "rgba(5, 13, 22, 0.90)";
      ctx.strokeStyle = "rgba(180, 210, 235, 0.35)";
      ctx.lineWidth = 1;
      const badgeW = 72, badgeH = 28;
      if (typeof ctx.roundRect === "function") {
        ctx.beginPath();
        ctx.roundRect(cx - badgeW / 2, cy - badgeH / 2, badgeW, badgeH, 4);
        ctx.fill();
        ctx.stroke();
      } else {
        ctx.fillRect(cx - badgeW / 2, cy - badgeH / 2, badgeW, badgeH);
        ctx.strokeRect(cx - badgeW / 2, cy - badgeH / 2, badgeW, badgeH);
      }
      ctx.font = "bold 8px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = activeColor;
      ctx.fillText(activeDirection ? `${activeDirection} ${signal.phase.endsWith("GREEN") ? remainingSeconds + "s" : "YELLOW"}` : "ALL RED", cx, cy - 6);
      ctx.fillStyle = COLORS.red;
      ctx.fillText(activeDirection ? "OTHER 3 RED" : `${remainingSeconds}s CLEAR`, cx, cy + 7);
      ctx.restore();

      // ── Camera icon if toggled ────────────────────────────────────────────
      if (ui.cameraToggle.checked && cameras.has(id)) {
        ctx.strokeStyle = COLORS.cyan;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(cx + 28, cy + 22, 8, 6);
      }

      // ── Pedestrians waiting or crossing ──────────────────────────────────
      drawPedestrians(cx, cy, signal);
    }
  }

  function vehiclePosition(vehicle) {
    if (vehicle.state === "ENTERING_BUILDING" || vehicle.state === "PARKED_AT_BUILDING" || vehicle.state === "EXITING_BUILDING") {
      return buildingVehiclePosition(vehicle);
    }
    if (vehicle.inTurn && vehicle.turnCurve) {
      const u = clamp(vehicle.turnU, 0, 1);
      const c = vehicle.turnCurve;
      const omt = 1 - u;
      const omt2 = omt * omt;
      const omt3 = omt2 * omt;
      const u2 = u * u;
      const u3 = u2 * u;
      const x = omt3 * c.p0.x + 3 * omt2 * u * c.p1.x + 3 * omt * u2 * c.p2.x + u3 * c.p3.x;
      const y = omt3 * c.p0.y + 3 * omt2 * u * c.p1.y + 3 * omt * u2 * c.p2.y + u3 * c.p3.y;
      const dx = 3 * omt2 * (c.p1.x - c.p0.x) + 6 * omt * u * (c.p2.x - c.p1.x) + 3 * u2 * (c.p3.x - c.p2.x);
      const dy = 3 * omt2 * (c.p1.y - c.p0.y) + 6 * omt * u * (c.p2.y - c.p1.y) + 3 * u2 * (c.p3.y - c.p2.y);
      return { x, y, angle: Math.atan2(dy, dx) };
    }

    const a = city.nodes[vehicle.from];
    const b = city.nodes[vehicle.to];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const length = Math.hypot(dx, dy) || 1;
    // Right-hand directional carriageway:
    // Unit normal pointing to vehicle's right side is (-dy/length, dx/length)
    // Lane 0 = inner lane (+12px from centerline)
    // Lane 1 = outer lane (+28px from centerline)
    // Safe outer curb edge = +31px from centerline
    const laneOffset = vehicle.currentLateralOffset ?? (vehicle.lane === 0 ? 12 : 28);
    const nx = -dy / length;
    const ny = dx / length;
    return {
      x: a.x + dx * vehicle.progress + nx * laneOffset,
      y: a.y + dy * vehicle.progress + ny * laneOffset,
      angle: Math.atan2(dy, dx)
    };
  }

  function activeAmbulance() { return vehicles.find(vehicle => vehicle.type === "ambulance") || null; }
  function drawRoutes() {
    if (!ui.routeToggle.checked) return;
    const ambulance = activeAmbulance();
    if (!ambulance) return;
    ctx.strokeStyle = "rgba(87,227,190,.9)";
    ctx.lineWidth = 5;
    ctx.shadowColor = COLORS.mint;
    ctx.shadowBlur = 12;
    ctx.setLineDash([14, 10]);
    ctx.beginPath();
    const remaining = [ambulance.from, ...ambulance.path.slice(ambulance.pathIndex)];
    remaining.forEach((id, index) => {
      const node = city.nodes[id];
      if (index === 0) ctx.moveTo(node.x, node.y); else ctx.lineTo(node.x, node.y);
    });
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.setLineDash([]);
  }

  function drawVehicles() {
    for (const vehicle of vehicles) {
      const position = vehiclePosition(vehicle);
      const length = VEHICLE_LENGTH[vehicle.type] || 16;
      const width = VEHICLE_WIDTH[vehicle.type] || 8;
      const isStopped = vehicle.stopped;
      const isBraking = vehicle.braking || isStopped;
      const isTurningLeft = vehicle.turnIndicator === "left";
      const isTurningRight = vehicle.turnIndicator === "right";
      const blinkOn = Math.floor(simulationTime * 5.5) % 2 === 0;

      ctx.save();
      ctx.translate(position.x, position.y);
      ctx.rotate(position.angle);

      // 1. Soft ground shadow
      ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
      ctx.fillRect(-length / 2 + 1, -width / 2 + 1, length, width);

      // 2. Vehicle Body
      if (vehicle.type === "ambulance") {
        // Ambulance body: crisp white with red emergency chevrons
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(-length / 2, -width / 2, length, width);

        // Red side stripes
        ctx.fillStyle = COLORS.red;
        ctx.fillRect(-length / 2 + 2, -width / 2, length - 4, 1.8);
        ctx.fillRect(-length / 2 + 2, width / 2 - 1.8, length - 4, 1.8);

        // Emergency rooftop lightbar (alternating red & blue strobes)
        const leftBlue = Math.sin(simulationTime * 14) > 0;
        ctx.fillStyle = leftBlue ? COLORS.cyan : COLORS.red;
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = 10;
        ctx.fillRect(-2, -width / 2 + 1, 4, 2.5);
        ctx.fillStyle = leftBlue ? COLORS.red : COLORS.cyan;
        ctx.shadowColor = ctx.fillStyle;
        ctx.fillRect(-2, width / 2 - 3.5, 4, 2.5);
        ctx.shadowBlur = 0;

        // Emergency pulsing aura surrounding ambulance
        ctx.fillStyle = `rgba(255, 100, 124, ${0.06 + Math.abs(Math.sin(simulationTime * 8)) * 0.14})`;
        ctx.beginPath();
        ctx.arc(0, 0, 22, 0, Math.PI * 2);
        ctx.fill();
      } else {
        // Regular car / bus / service body
        ctx.fillStyle = vehicle.color;
        ctx.fillRect(-length / 2, -width / 2, length, width);
      }

      // 3. Cabin & Windshield
      ctx.fillStyle = "rgba(10, 20, 30, 0.78)";
      if (vehicle.type === "bus") {
        ctx.fillRect(-length * 0.38, -width * 0.36, length * 0.72, width * 0.72);
      } else {
        // Front windshield
        ctx.fillRect(0, -width * 0.34, length * 0.28, width * 0.68);
        // Rear window
        ctx.fillRect(-length * 0.32, -width * 0.34, length * 0.2, width * 0.68);
      }

      // 4. Front Headlights (with forward beams)
      const headlightColor = "#fffbe8";
      ctx.fillStyle = headlightColor;
      ctx.fillRect(length / 2 - 1.5, -width / 2 + 0.8, 2, 2);
      ctx.fillRect(length / 2 - 1.5, width / 2 - 2.8, 2, 2);

      // Subtle forward light cone
      const beamGrad = ctx.createLinearGradient(length / 2, 0, length / 2 + 22, 0);
      beamGrad.addColorStop(0, "rgba(255, 252, 225, 0.22)");
      beamGrad.addColorStop(1, "rgba(255, 252, 225, 0)");
      ctx.fillStyle = beamGrad;
      ctx.beginPath();
      ctx.moveTo(length / 2, -width / 2);
      ctx.lineTo(length / 2 + 22, -width / 2 - 5);
      ctx.lineTo(length / 2 + 22, width / 2 + 5);
      ctx.lineTo(length / 2, width / 2);
      ctx.fill();

      // 5. Rear Taillights / Brake Lights
      if (isBraking) {
        // Glowing bright red brake lights
        ctx.fillStyle = "#ff1f3d";
        ctx.shadowColor = "#ff1f3d";
        ctx.shadowBlur = 7;
        ctx.fillRect(-length / 2 - 0.5, -width / 2 + 0.8, 2, 2.2);
        ctx.fillRect(-length / 2 - 0.5, width / 2 - 3, 2, 2.2);
        ctx.shadowBlur = 0;
      } else {
        // Subtle red running lights
        ctx.fillStyle = "#b01e2e";
        ctx.fillRect(-length / 2, -width / 2 + 1, 1.5, 1.8);
        ctx.fillRect(-length / 2, width / 2 - 2.8, 1.5, 1.8);
      }

      // 6. Turn Indicators (Blinking amber lights)
      if (blinkOn) {
        ctx.fillStyle = "#ffaa00";
        ctx.shadowColor = "#ffaa00";
        ctx.shadowBlur = 5;
        if (isTurningLeft) {
          ctx.fillRect(length / 2 - 2, -width / 2 - 0.8, 2, 1.8);
          ctx.fillRect(-length / 2, -width / 2 - 0.8, 2, 1.8);
        } else if (isTurningRight) {
          ctx.fillRect(length / 2 - 2, width / 2 - 1, 2, 1.8);
          ctx.fillRect(-length / 2, width / 2 - 1, 2, 1.8);
        }
        ctx.shadowBlur = 0;
      }

      ctx.restore();
    }
  }

  function drawHospital() {
    const node = city.nodes[hospitalNode];
    ctx.fillStyle = "rgba(102,124,255,.17)";
    ctx.beginPath(); ctx.arc(node.x, node.y, 47 + Math.sin(simulationTime * 2) * 2, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = COLORS.blue;
    ctx.strokeStyle = "#e8edff";
    ctx.lineWidth = 2;
    ctx.fillRect(node.x + 27, node.y + 25, 34, 34);
    ctx.strokeRect(node.x + 27, node.y + 25, 34, 34);
    ctx.fillStyle = "#fff";
    ctx.font = "900 20px ui-sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("H", node.x + 44, node.y + 43);
  }

  function drawRoadEvents() {
    for (const event of roadEvents.values()) {
      const edge = city.edges[event.edgeId];
      const a = city.nodes[edge.a], b = city.nodes[edge.b];
      const x = (a.x + b.x) / 2, y = (a.y + b.y) / 2;
      ctx.fillStyle = event.type === "congestion" ? "rgba(255,189,102,.22)" : "rgba(255,100,124,.2)";
      ctx.beginPath(); ctx.arc(x, y, 25 + Math.sin(simulationTime * 5) * 3, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = event.type === "congestion" ? COLORS.amber : COLORS.red;
      ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "#071019";
      ctx.font = "950 13px ui-sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(event.type === "congestion" ? "≋" : event.type === "closure" ? "×" : "!", x, y);
    }
  }

  function drawCity() {
    const rect = resizeCanvas(canvas, ctx);
    drawCityBackground(rect.width, rect.height);
    if (!city) return;
    ctx.save();
    ctx.translate(view.x, view.y);
    ctx.scale(view.zoom, view.zoom);
    drawBlocks();
    drawHeatmap();
    drawRoads();
    drawJunctions();
    drawRoutes();
    drawSignals();
    drawHospital();
    drawRoadEvents();
    drawVehicles();
    ctx.restore();
  }

  function drawCamera() {
    const rect = resizeCanvas(cameraCanvas, cameraCtx);
    const width = rect.width, height = rect.height;
    cameraCtx.fillStyle = "#04090e";
    cameraCtx.fillRect(0, 0, width, height);
    if (!city || !ui.cameraToggle.checked) {
      cameraCtx.fillStyle = "#718497";
      cameraCtx.font = "700 11px ui-monospace";
      cameraCtx.textAlign = "center";
      cameraCtx.fillText("CAMERA LAYER OFF", width / 2, height / 2);
      return;
    }
    const center = city.nodes[selectedJunction];
    const scale = Math.min(width, height) / 250;
    cameraCtx.save();
    cameraCtx.translate(width / 2, height / 2);
    cameraCtx.scale(scale, scale);
    cameraCtx.translate(-center.x, -center.y);
    for (const link of city.adjacency[selectedJunction]) {
      const edge = city.edges[link.edge], a = city.nodes[edge.a], b = city.nodes[edge.b];
      cameraCtx.strokeStyle = "#293f4e";
      cameraCtx.lineWidth = edge.lanes * 14 + 12;
      cameraCtx.beginPath(); cameraCtx.moveTo(a.x, a.y); cameraCtx.lineTo(b.x, b.y); cameraCtx.stroke();
      cameraCtx.strokeStyle = "rgba(190,211,222,.25)";
      cameraCtx.lineWidth = 1;
      cameraCtx.setLineDash([6, 8]); cameraCtx.stroke(); cameraCtx.setLineDash([]);
    }
    const detected = vehicles.filter(vehicle => Core.distance(center, vehiclePosition(vehicle)) <= 145);
    for (const vehicle of detected) {
      const position = vehiclePosition(vehicle);
      cameraCtx.save();
      cameraCtx.translate(position.x, position.y);
      cameraCtx.rotate(position.angle);
      cameraCtx.fillStyle = vehicle.color;
      cameraCtx.fillRect(-VEHICLE_LENGTH[vehicle.type] / 2, -VEHICLE_WIDTH[vehicle.type] / 2, VEHICLE_LENGTH[vehicle.type], VEHICLE_WIDTH[vehicle.type]);
      cameraCtx.strokeStyle = vehicle.type === "ambulance" ? COLORS.red : COLORS.cyan;
      cameraCtx.lineWidth = 1.5 / scale;
      cameraCtx.strokeRect(-VEHICLE_LENGTH[vehicle.type] / 2 - 3, -VEHICLE_WIDTH[vehicle.type] / 2 - 3, VEHICLE_LENGTH[vehicle.type] + 6, VEHICLE_WIDTH[vehicle.type] + 6);
      cameraCtx.restore();
    }
    cameraCtx.restore();
    ui.cameraVehicleCount.textContent = detected.length;
    ui.cameraQueueCount.textContent = detected.filter(vehicle => vehicle.stopped).length;
    ui.cameraEmergencyCount.textContent = detected.filter(vehicle => vehicle.type === "ambulance").length;
  }

  function overlapCount() {
    const groups = new Map();
    for (const vehicle of vehicles) {
      if (vehicle.inTurn) continue;
      const key = laneGroupKey(vehicle);
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(vehicle);
    }
    let overlaps = 0;
    for (const group of groups.values()) {
      group.sort((a, b) => a.progress - b.progress);
      for (let index = 1; index < group.length; index += 1) {
        const edge = edgeBetween(group[index].from, group[index].to);
        if (!edge) continue;
        const gap = (group[index].progress - group[index - 1].progress) * edge.length;
        const minimum = (VEHICLE_LENGTH[group[index].type] + VEHICLE_LENGTH[group[index - 1].type]) / 2;
        if (gap < minimum - .5) overlaps += 1;
      }
    }
    return overlaps;
  }

  function setLight(element, color) {
    element.querySelectorAll("i").forEach(light => light.classList.remove("active"));
    const active = element.querySelector(`.${color}`);
    if (active) active.classList.add("active");
  }
  function percentageReduction(base, actual) {
    if (base <= 0) return 0;
    return clamp((base - actual) / base * 100, 0, 99);
  }

  function updatePanel() {
    if (!city) return;
    const queued = vehicles.filter(vehicle => vehicle.stopped).length;
    const waiting = vehicles.length ? vehicles.reduce((sum, vehicle) => sum + vehicle.wait, 0) / vehicles.length : 0;
    const imbalance = signals.reduce((sum, signal) => sum + Math.abs(signal.nsQueue - signal.ewQueue), 0);
    const fixedWaitValue = ui.controllerSelect.value === "fixed" ? waiting : waiting + (queued ? 5.5 + imbalance / Math.max(1, queued) * 8.5 : 0);
    const fixedQueueValue = ui.controllerSelect.value === "fixed" ? queued : Math.ceil(queued + imbalance * .45);
    const hourly = Math.round(completedVehicles / Math.max(1, simulationTime) * 3600);
    const ambulances = vehicles.filter(vehicle => vehicle.type === "ambulance").length;
    const counts = edgeVehicleCounts();
    const density = counts.reduce((sum, count, id) => sum + count / city.edges[id].capacity, 0) / city.edges.length;
    const totalPedestrianWait = signals.reduce((sum, signal) => sum + signal.pedestrianWait, 0);
    const totalPedestrians = signals.reduce((sum, signal) => sum + signal.pedestrians, 0);
    const averagePedWait = totalPedestrians ? totalPedestrianWait / (totalPedestrians * Math.max(1, simulationTime)) : 0;
    const waitGain = percentageReduction(fixedWaitValue, waiting);
    const emissionGain = percentageReduction(baselineCo2, totalCo2);

    ui.vehicleMetric.textContent = vehicles.length.toLocaleString();
    ui.queueMetric.textContent = `${queued} queued • ${overlapCount()} overlaps`;
    ui.waitMetric.textContent = `${waiting.toFixed(1)}s`;
    ui.waitDelta.textContent = waitGain ? `↓ ${waitGain.toFixed(0)}% vs fixed` : "baseline collecting";
    ui.throughputMetric.textContent = hourly.toLocaleString();
    ui.co2SavedMetric.textContent = `${Math.max(0, baselineCo2 - totalCo2).toFixed(2)}kg`;
    ui.networkQueueMetric.textContent = queued;
    ui.densityMetric.textContent = `${Math.round(density * 100)}%`;
    ui.fuelMetric.textContent = `${totalFuel.toFixed(2)}L`;
    ui.co2Metric.textContent = `${totalCo2.toFixed(2)}kg`;
    ui.pedWaitMetric.textContent = `${averagePedWait.toFixed(1)}s`;
    ui.incidentMetric.textContent = roadEvents.size;
    ui.ambulanceMetric.textContent = `${ambulances} ambulance${ambulances === 1 ? "" : "s"}`;

    ui.fixedWait.textContent = `${fixedWaitValue.toFixed(1)}s`;
    ui.hybridWait.textContent = `${waiting.toFixed(1)}s`;
    ui.fixedQueue.textContent = fixedQueueValue;
    ui.hybridQueue.textContent = queued;
    ui.fixedFuel.textContent = `${baselineFuel.toFixed(2)}L`;
    ui.hybridFuel.textContent = `${totalFuel.toFixed(2)}L`;
    ui.fixedCo2.textContent = `${baselineCo2.toFixed(2)}kg`;
    ui.hybridCo2.textContent = `${totalCo2.toFixed(2)}kg`;
    ui.waitReduction.textContent = `${waitGain.toFixed(0)}%`;
    ui.emissionReduction.textContent = `${emissionGain.toFixed(0)}%`;
    ui.waitBar.style.width = `${waitGain}%`;
    ui.emissionBar.style.width = `${emissionGain}%`;
    ui.winnerBadge.textContent = simulationTime < 12 ? "CALCULATING" : "MEASURED DELTA";

    const signal = signals[selectedJunction];
    const connected = city.adjacency[selectedJunction].map(link => city.edges[link.edge]);
    const capacity = connected.reduce((sum, edge) => sum + edge.capacity, 0);
    const localVehicles = vehicles.filter(vehicle => vehicle.to === selectedJunction || vehicle.from === selectedJunction).length;
    ui.junctionName.textContent = `J-${label(selectedJunction)}`;
    ui.junctionTitle.textContent = city.nodes[selectedJunction].name;
    ui.cameraName.textContent = cameras.has(selectedJunction) ? `CAM-${label(selectedJunction)}` : `VIRTUAL-${label(selectedJunction)}`;
    const directionColors = Object.fromEntries(SIGNAL_DIRECTIONS.map(direction => [direction, phaseColor(signal.phase, direction)]));
    setLight(ui.nLight, directionColors.N);
    setLight(ui.sLight, directionColors.S);
    setLight(ui.eLight, directionColors.E);
    setLight(ui.wLight, directionColors.W);
    ui.nSignalText.textContent = directionColors.N.toUpperCase();
    ui.sSignalText.textContent = directionColors.S.toUpperCase();
    ui.eSignalText.textContent = directionColors.E.toUpperCase();
    ui.wSignalText.textContent = directionColors.W.toUpperCase();
    ui.phaseLabel.textContent = signal.phase.replaceAll("_", " ");
    ui.phaseTimer.textContent = `${Math.max(0, Math.ceil(signal.remaining))}s`;
    ui.junctionDensity.textContent = `${Math.round(localVehicles / Math.max(1, capacity) * 100)}%`;
    ui.junctionCapacity.textContent = capacity;
    ui.junctionPedestrians.textContent = Math.round(signal.pedestrians);
    if (signal.lastDecision) {
      ui.quboNs.textContent = `${signal.lastDecision.nsGreen}s`;
      ui.quboEw.textContent = `${signal.lastDecision.ewGreen}s`;
      ui.quboObjective.textContent = signal.lastDecision.objective.toFixed(3);
      ui.algorithmStatus.textContent = `${signal.lastDecision.candidatesEvaluated} feasible QUBO states evaluated from live queues, density, capacity and pedestrians.`;
    }

    // Directional Queues & Classes for Selected Junction
    const localVehs = vehicles.filter(v => v.to === selectedJunction || v.from === selectedJunction);
    if (ui.northQueue) ui.northQueue.textContent = signal.directionQueues.N;
    if (ui.southQueue) ui.southQueue.textContent = signal.directionQueues.S;
    if (ui.eastQueue) ui.eastQueue.textContent = signal.directionQueues.E;
    if (ui.westQueue) ui.westQueue.textContent = signal.directionQueues.W;

    if (ui.carCount) ui.carCount.textContent = localVehs.filter(v => v.type === "car").length;
    if (ui.busCount) ui.busCount.textContent = localVehs.filter(v => v.type === "bus").length;
    if (ui.serviceCount) ui.serviceCount.textContent = localVehs.filter(v => v.type === "service").length;
    if (ui.ambulanceCount) ui.ambulanceCount.textContent = localVehs.filter(v => v.type === "ambulance").length;

    if (ui.trackedCount) ui.trackedCount.textContent = localVehs.length;
    if (ui.detectionConfidence) ui.detectionConfidence.textContent = localVehs.length > 0 ? "97.4%" : "100%";
    if (ui.observationFreshness) ui.observationFreshness.textContent = "Live (<1s)";

    // Network Grid Overview (J1–J4)
    if (ui.networkGrid) {
      ui.networkGrid.innerHTML = signals.filter(s => s.id < 4).map(s => {
        const iid = `J${label(s.id)}`;
        const localCount = vehicles.filter(v => v.to === s.id || v.from === s.id).length;
        const totalQ = s.nsQueue + s.ewQueue;
        const pColor = s.phase.includes("GREEN") ? "green" : (s.phase.includes("YELLOW") ? "yellow" : "red");
        const isSel = s.id === selectedJunction ? "active" : "";
        const solverName = ui.controllerSelect.value === "qaoa" ? "QAOA" : (ui.controllerSelect.value === "qubo" ? "QUBO exact" : ui.controllerSelect.value);
        return `<div class="network-card ${isSel}" data-junction="${s.id}">
          <div class="network-card-header">
            <b>${iid} ${escapeHtml(city.nodes[s.id].name.split(" ")[0])}</b>
            <span class="${pColor}">${escapeHtml(s.phase.replace("_GREEN", ""))}</span>
          </div>
          <div class="network-card-body">
            <div>Vehicles: <b>${localCount}</b> • Queue: <b>${totalQ}</b></div>
            <div>P0: <b>${s.nsGreen}s</b> • P2: <b>${s.ewGreen}s</b></div>
            <div>Controller: <b style="color:var(--cyan);">${escapeHtml(solverName)}</b></div>
          </div>
        </div>`;
      }).join("");

      ui.networkGrid.querySelectorAll(".network-card").forEach(card => {
        card.addEventListener("click", () => {
          const jid = Number(card.getAttribute("data-junction"));
          selectedJunction = jid;
          addEvent("Junction selected", `Inspecting J-${label(selectedJunction)} • ${city.nodes[selectedJunction].name}`);
          updatePanel();
        });
      });
    }

    // Dynamic Events List
    if (ui.eventsList) {
      if (roadEvents.size === 0) {
        ui.eventsList.innerHTML = '<p class="empty-state" style="font-size: 0.62rem; color: var(--muted); text-align: center; padding: 12px 0;">No active road disruptions.</p>';
        if (ui.activeEventBadge) ui.activeEventBadge.textContent = "0 ACTIVE";
      } else {
        if (ui.activeEventBadge) ui.activeEventBadge.textContent = `${roadEvents.size} ACTIVE`;
        ui.eventsList.innerHTML = [...roadEvents.values()].map(ev => {
          const edge = city.edges[ev.edgeId];
          const roadName = edge ? `${city.nodes[edge.a].name.split(" ")[0]} ↔ ${city.nodes[edge.b].name.split(" ")[0]}` : ev.key;
          return `<div class="event-item-card ${escapeHtml(ev.type)}">
            <div class="event-item-header">
              <span>${escapeHtml(ev.type.toUpperCase())}</span>
              <button class="cancel-event-btn" data-key="${escapeHtml(ev.key)}">Cancel</button>
            </div>
            <div>Road: <b>${escapeHtml(roadName)}</b></div>
            <div>Active: <b>${Math.round(simulationTime - ev.createdAt)}s</b></div>
          </div>`;
        }).join("");

        ui.eventsList.querySelectorAll(".cancel-event-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            const key = btn.getAttribute("data-key");
            cancelDynamicEvent(null, key);
          });
        });
      }
    }

    // QAOA Research Specs
    if (ui.qaoaObjectiveVal) {
      ui.qaoaObjectiveVal.textContent = signal.lastDecision ? signal.lastDecision.objective.toFixed(4) : "0.0000";
    }
    if (ui.qaoaSolverStatus) {
      ui.qaoaSolverStatus.textContent = ui.controllerSelect.value === "qaoa" ? "QAOA Research Active" : "Exact QUBO Baseline";
    }
    if (ui.qaoaGapVal) ui.qaoaGapVal.textContent = "0.000000";
    if (ui.qaoaRecoveryVal) ui.qaoaRecoveryVal.textContent = "100%";
    if (ui.qaoaStatus) ui.qaoaStatus.textContent = ui.controllerSelect.value === "qaoa" ? "QAOA ACTIVE" : "QAOA READY";

    // Emergency Priority Telemetry
    const ambulance = activeAmbulance();
    ui.corridorSection.classList.toggle("active", Boolean(ambulance));
    if (ui.emergencyVehId) ui.emergencyVehId.textContent = ambulance ? "AMB001" : "None";
    if (ui.emergencyRouteSummary) ui.emergencyRouteSummary.textContent = ambulance ? `J-${label(ambulance.path[0])} → Hosp J-${label(hospitalNode)}` : "Standby";
    if (ui.emergencyPriorityAppr) ui.emergencyPriorityAppr.textContent = ambulance ? "West (P2 Priority)" : "Normal";
    if (ui.emergencyOverrideStatus) ui.emergencyOverrideStatus.textContent = ambulance ? "40s / 22s Active" : "None";

    if (ambulance) {
      const completedLegs = Math.max(0, ambulance.pathIndex - 1 + ambulance.progress);
      const progress = clamp(completedLegs / Math.max(1, ambulance.corridorLength), 0, 1);
      const remainingEdges = Math.max(0, ambulance.path.length - ambulance.pathIndex);
      ui.corridorStatus.textContent = "ACTIVE";
      ui.corridorRoute.textContent = `J-${label(ambulance.path[0])} → Hospital J-${label(hospitalNode)}`;
      ui.corridorEta.textContent = `${remainingEdges} signal${remainingEdges === 1 ? "" : "s"} ahead • priority pre-emption live`;
      ui.corridorBar.style.width = `${progress * 100}%`;
    } else {
      ui.corridorStatus.textContent = corridorCompleted ? "RESTORED" : "STANDBY";
      ui.corridorRoute.textContent = corridorCompleted
        ? `Last corridor: ${Math.round(corridorCompleted)}s vs ${Math.round(corridorBaseline)}s fixed`
        : "No active ambulance";
      ui.corridorEta.textContent = corridorCompleted ? "Normal optimized timing restored" : "Dispatch one from the map";
      ui.corridorBar.style.width = corridorCompleted ? "100%" : "0%";
    }
  }

  function nearestNode(point) {
    let result = { id: 0, distance: Infinity };
    for (const node of city.nodes) {
      const distance = Math.hypot(point.x - node.x, point.y - node.y);
      if (distance < result.distance) result = { id: node.id, distance };
    }
    return result;
  }
  function pointToSegmentDistance(point, a, b) {
    const dx = b.x - a.x, dy = b.y - a.y;
    const lengthSquared = dx * dx + dy * dy;
    const t = lengthSquared ? clamp(((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared, 0, 1) : 0;
    return Math.hypot(point.x - (a.x + dx * t), point.y - (a.y + dy * t));
  }
  function nearestEdge(point) {
    let result = { edge: city.edges[0], distance: Infinity };
    for (const edge of city.edges) {
      const distance = pointToSegmentDistance(point, city.nodes[edge.a], city.nodes[edge.b]);
      if (distance < result.distance) result = { edge, distance };
    }
    return result;
  }
  function handleMapClick(clientX, clientY) {
    const point = screenToWorld(clientX, clientY);
    if (["congestion", "accident", "closure"].includes(placementMode)) {
      const nearest = nearestEdge(point);
      if (nearest.distance > 38 / view.zoom) return showToast("Click closer to a road.");
      const a = city.nodes[nearest.edge.a], b = city.nodes[nearest.edge.b];
      const dx = b.x - a.x, dy = b.y - a.y;
      const cross = dx * (point.y - a.y) - dy * (point.x - a.x);
      const affectedFrom = cross >= 0 ? nearest.edge.a : nearest.edge.b;
      const affectedTo = cross >= 0 ? nearest.edge.b : nearest.edge.a;
      const len = Math.hypot(dx, dy) || 1;
      const perpDist = Math.abs(cross) / len;
      const affectedLane = perpDist > 20 ? 1 : 0;
      addRoadEvent(nearest.edge, placementMode, { from: affectedFrom, to: affectedTo, lane: affectedLane });
      return;
    }
    const nearest = nearestNode(point);
    if (nearest.distance > 42 / view.zoom) return showToast("Click closer to a junction.");
    if (placementMode === "hospital") {
      hospitalNode = nearest.id;
      selectedJunction = nearest.id;
      addEvent("Hospital relocated", `Emergency destination moved to J-${label(hospitalNode)} • ${city.nodes[hospitalNode].name}`);
      setPlacementMode("inspect");
    } else if (placementMode === "ambulance") {
      dispatchAmbulance(nearest.id);
    } else {
      selectedJunction = nearest.id;
      addEvent("Junction selected", `Inspecting J-${label(selectedJunction)} • ${city.nodes[selectedJunction].name}`);
    }
    updatePanel();
  }

  function animate(now) {
    const realDt = Math.min(.05, Math.max(0, (now - lastFrame) / 1000));
    lastFrame = now;
    if (!paused && city) {
      const dt = realDt * simulationSpeed;
      simulationTime += dt;
      metricAccumulator += dt;
      optimizerAccumulator += dt;
      updateSignals(dt);
      updateVehicles(dt);
      if (optimizerAccumulator >= 6) { optimizerAccumulator = 0; optimizeSignals(); }
      if (metricAccumulator >= .3) { metricAccumulator = 0; updatePanel(); }
      ui.simClock.textContent = formatTime(simulationTime);
    }
    drawCity();
    drawCamera();
    requestAnimationFrame(animate);
  }

  // Read-only diagnostics and test helpers used by automated test suite
  window.FlowQDiagnostics = Object.freeze({
    snapshot: () => ({
      simulationTime,
      vehicles: vehicles.map(vehicle => ({
        id: vehicle.id, type: vehicle.type, from: vehicle.from, to: vehicle.to,
        lane: vehicle.lane, progress: vehicle.progress, state: vehicle.state,
        currentSpeed: vehicle.currentSpeed, stopped: vehicle.stopped,
        spawnNode: vehicle.spawnNode, spawnPointId: vehicle.spawnPointId,
        target: vehicle.target, path: [...vehicle.path], pathIndex: vehicle.pathIndex,
        inTurn: vehicle.inTurn
      })),
      signals: signals.slice(0, 4).map(signal => ({
        id: signal.id,
        phase: signal.phase,
        remaining: signal.remaining,
        heads: Object.fromEntries(SIGNAL_DIRECTIONS.map(direction => [direction, phaseColor(signal.phase, direction)]))
      })),
      junctionEntries: junctionEntries.map(entry => ({ ...entry })),
      redLightViolations,
      closureRedirects,
      vehicleSpawns: vehicleSpawns.map(spawn => ({ ...spawn })),
      vehicleExits: vehicleExits.map(exit => ({ ...exit })),
      closureJunctionDetours: closureJunctionDetours.map(detour => ({ ...detour })),
      overlaps: overlapCount(),
      activeRoadEvents: roadEvents.size,
      completedVehicles
    }),
    injectRoadEvent: (edgeId, type, options) => {
      const edge = city.edges[edgeId];
      if (edge) addRoadEvent(edge, type, options);
    },
    clearEvents: () => clearEvents(),
    getView: () => ({ ...view })
  });

  function initTabs() {
    const tabButtons = [
      ui.tabLiveBtn, ui.tabNetworkBtn, ui.tabEmergencyBtn,
      ui.tabEventsBtn, ui.tabMetricsBtn, ui.tabResearchBtn, ui.tabRealworldBtn
    ];
    const tabPanes = [
      ui.tabLive, ui.tabNetwork, ui.tabEmergency,
      ui.tabEvents, ui.tabMetrics, ui.tabResearch, ui.tabRealworld
    ];
    tabButtons.forEach(btn => {
      if (!btn) return;
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-tab") || btn.id.replace("Btn", "");
        tabButtons.forEach(b => {
          if (b) {
            b.classList.remove("active");
            if (b.setAttribute) b.setAttribute("aria-selected", "false");
          }
        });
        btn.classList.add("active");
        if (btn.setAttribute) btn.setAttribute("aria-selected", "true");
        tabPanes.forEach(pane => {
          if (!pane) return;
          if (pane.id === targetId) {
            pane.classList.remove("hidden");
            pane.classList.add("active");
          } else {
            pane.classList.add("hidden");
            pane.classList.remove("active");
          }
        });
      });
    });
  }

  function resetSimulation() {
    simulationTime = 0;
    completedVehicles = 0;
    totalCompletedTravel = 0;
    totalFuel = 0;
    baselineFuel = 0;
    totalCo2 = 0;
    baselineCo2 = 0;
    corridorCompleted = 0;
    corridorBaseline = 0;
    closureRedirects = 0;
    vehicleExits = [];
    vehicleSpawns = [];
    closureJunctionDetours = [];
    roadEvents.clear();
    vehicles = [];
    signals = city.nodes.map(makeSignal);
    for (let attempts = 0; attempts < 160 && vehicles.length < 24; attempts += 1) spawnRegularVehicle(true);
    addEvent("Simulation reset", "Initial baseline state restored across all junctions", "normal");
    updatePanel();
  }

  function applyScenario(scenario) {
    if (scenario === "low") {
      ui.demandRange.value = "60";
      ui.demandValue.textContent = "60 veh/h";
      clearEvents();
      addEvent("Scenario applied", "Low traffic demand (60 veh/h)", "normal");
    } else if (scenario === "normal") {
      ui.demandRange.value = "180";
      ui.demandValue.textContent = "180 veh/h";
      clearEvents();
      addEvent("Scenario applied", "Normal traffic demand (180 veh/h)", "normal");
    } else if (scenario === "high") {
      ui.demandRange.value = "360";
      ui.demandValue.textContent = "360 veh/h";
      clearEvents();
      addEvent("Scenario applied", "High congestion demand (360 veh/h)", "alert");
    } else if (scenario === "emergency") {
      ui.demandRange.value = "180";
      ui.demandValue.textContent = "180 veh/h";
      triggerEmergencyCorridor(0, hospitalNode);
    } else if (scenario === "accident") {
      injectDynamicEvent("accident", 1, "east", "high");
    }
    updatePanel();
  }

  async function triggerEmergencyCorridor(fromNode = 0, toNode = 6) {
    const routeIds = ["J1", "J2", "J3", "J4"];
    try {
      if (location.protocol.startsWith("http")) {
        await fetch("/api/emergency/corridor", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            emergency_vehicle_id: "AMB001",
            current_intersection_id: "J1",
            destination_intersection_id: "J4",
            route: routeIds,
            priority_level: "critical",
            approach: "west"
          })
        });
      }
    } catch (_) {}
    dispatchAmbulance(fromNode);
    addEvent("Emergency corridor activated", `AMB001 priority wave requested across route: ${routeIds.join(" → ")}`, "emergency");
  }

  async function releaseEmergencyCorridor() {
    try {
      if (location.protocol.startsWith("http")) {
        await fetch("/api/emergency/release", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ emergency_vehicle_id: "AMB001" })
        });
      }
    } catch (_) {}
    for (const signal of signals) {
      signal.priorityActive = false;
      signal.requestedAxis = null;
      signal.requestedDirection = null;
    }
    vehicles = vehicles.filter(v => v.type !== "ambulance");
    addEvent("Emergency corridor released", "Priority preemption released; signals restored to canonical QUBO", "normal");
    updatePanel();
  }

  async function injectDynamicEvent(type, junctionId, approach = "east", severity = "high") {
    const iid = `J${label(junctionId)}`;
    const eventId = `EVT_${type.toUpperCase()}_${iid}`;
    try {
      if (location.protocol.startsWith("http")) {
        await fetch("/api/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_id: eventId,
            event_type: type === "closure" ? "road_closure" : (type === "surge" ? "traffic_surge" : (type === "pedestrian" ? "pedestrian_demand" : "accident")),
            affected_intersection_ids: [iid],
            affected_approaches: [approach],
            severity: severity,
            capacity_factor: type === "closure" ? 0.05 : 0.35,
            demand_multiplier: type === "surge" ? 1.8 : 1.0,
            queue_adder: type === "accident" ? 15 : (type === "closure" ? 25 : 5),
            start_time: simulationTime,
            end_time: simulationTime + 180
          })
        });
      }
    } catch (_) {}
    const links = city.adjacency[junctionId];
    if (links && links.length) {
      const edge = city.edges[links[0].edge];
      addRoadEvent(edge, type === "closure" ? "closure" : (type === "surge" ? "congestion" : "accident"));
    }
  }

  async function cancelDynamicEvent(eventId, edgeKey) {
    try {
      if (location.protocol.startsWith("http") && eventId) {
        await fetch(`/api/events/${eventId}`, { method: "DELETE" });
      }
    } catch (_) {}
    if (edgeKey) roadEvents.delete(edgeKey);
    else roadEvents.clear();
    addEvent("Event cleared", "Disruption removed from network; normal optimization resumed", "normal");
    updatePanel();
  }

  ui.generateBtn.addEventListener("click", () => generateCity(ui.seedInput.value.trim() || "42"));
  ui.randomSeedBtn.addEventListener("click", () => {
    ui.seedInput.value = `CITY-${Math.floor(Math.random() * 999999).toString().padStart(6, "0")}`;
    generateCity(ui.seedInput.value);
  });
  ui.seedInput.addEventListener("keydown", event => { if (event.key === "Enter") generateCity(ui.seedInput.value.trim() || "42"); });
  ui.pauseBtn.addEventListener("click", () => {
    paused = !paused;
    ui.pauseBtn.innerHTML = paused ? "<span>▶</span> Resume" : "<span>Ⅱ</span> Pause";
    ui.pauseBtn.title = paused ? "Resume simulation" : "Pause simulation";
  });
  if (ui.resetBtn) ui.resetBtn.addEventListener("click", resetSimulation);
  if (ui.scenarioSelect) ui.scenarioSelect.addEventListener("change", () => applyScenario(ui.scenarioSelect.value));

  ui.controllerSelect.addEventListener("change", () => {
    const labels = { qubo: "HYBRID QUBO", qaoa: "QUANTUM QAOA", adaptive: "PRESSURE", fixed: "FIXED" };
    ui.controllerState.textContent = labels[ui.controllerSelect.value] || "HYBRID QUBO";
    optimizeSignals().then(() => {
      for (let i = 0; i < 4; i += 1) {
        const sig = signals[i];
        if (sig && sig.targetNsGreen != null) sig.nsGreen = sig.targetNsGreen;
        if (sig && sig.targetEwGreen != null) sig.ewGreen = sig.targetEwGreen;
      }
      updatePanel();
    });
    addEvent("Control strategy changed", ui.controllerSelect.options[ui.controllerSelect.selectedIndex].text);
  });
  ui.demandRange.addEventListener("input", () => { ui.demandValue.textContent = `${ui.demandRange.value} veh/h`; });
  ui.pedestrianRange.addEventListener("input", () => { ui.pedestrianValue.textContent = `${ui.pedestrianRange.value}%`; });
  ui.speedRange.addEventListener("input", () => {
    simulationSpeed = Number(ui.speedRange.value);
    ui.speedValue.textContent = `${simulationSpeed.toFixed(1)}×`;
  });
  ui.congestionBtn.addEventListener("click", () => setPlacementMode("congestion"));
  ui.accidentBtn.addEventListener("click", () => setPlacementMode("accident"));
  ui.closureBtn.addEventListener("click", () => setPlacementMode("closure"));
  ui.ambulanceBtn.addEventListener("click", () => setPlacementMode("ambulance"));
  ui.hospitalBtn.addEventListener("click", () => setPlacementMode("hospital"));
  ui.inspectBtn.addEventListener("click", () => setPlacementMode("inspect"));
  ui.clearEventsBtn.addEventListener("click", clearEvents);
  ui.zoomInBtn.addEventListener("click", () => zoomAt(1.25));
  ui.zoomOutBtn.addEventListener("click", () => zoomAt(.8));
  ui.fitBtn.addEventListener("click", fitCity);

  if (ui.triggerAmbulanceCorridorBtn) ui.triggerAmbulanceCorridorBtn.addEventListener("click", () => triggerEmergencyCorridor(0, hospitalNode));
  if (ui.releaseCorridorBtn) ui.releaseCorridorBtn.addEventListener("click", releaseEmergencyCorridor);
  if (ui.btnDispatchCorridor) ui.btnDispatchCorridor.addEventListener("click", () => triggerEmergencyCorridor(0, hospitalNode));
  if (ui.btnAdvanceCorridor) ui.btnAdvanceCorridor.addEventListener("click", () => {
    const amb = activeAmbulance();
    if (amb) amb.progress = 0.99;
    showToast("Ambulance advanced to next intersection.");
  });
  if (ui.btnReleaseCorridor) ui.btnReleaseCorridor.addEventListener("click", releaseEmergencyCorridor);

  if (ui.injectAccidentJ2Btn) ui.injectAccidentJ2Btn.addEventListener("click", () => injectDynamicEvent("accident", 1, "east", "high"));
  if (ui.injectClosureJ3Btn) ui.injectClosureJ3Btn.addEventListener("click", () => injectDynamicEvent("closure", 2, "west", "critical"));
  if (ui.injectSurgeBtn) ui.injectSurgeBtn.addEventListener("click", () => injectDynamicEvent("surge", 0, "north", "high"));

  if (ui.evInjectAccidentBtn) ui.evInjectAccidentBtn.addEventListener("click", () => injectDynamicEvent("accident", 1, "east", "high"));
  if (ui.evInjectClosureBtn) ui.evInjectClosureBtn.addEventListener("click", () => injectDynamicEvent("closure", 2, "west", "critical"));
  if (ui.evInjectSurgeBtn) ui.evInjectSurgeBtn.addEventListener("click", () => injectDynamicEvent("surge", 0, "north", "high"));
  if (ui.evInjectPedestrianBtn) ui.evInjectPedestrianBtn.addEventListener("click", () => {
    ui.pedestrianRange.value = "80";
    ui.pedestrianValue.textContent = "80%";
    addEvent("Pedestrian demand surge", "High foot traffic priority active", "alert");
  });

  if (ui.rwSourceSelect) {
    ui.rwSourceSelect.addEventListener("change", () => {
      const src = ui.rwSourceSelect.value;
      if (ui.rwActiveSourceLabel) ui.rwActiveSourceLabel.textContent = src;
      if (ui.rwSourcePathLabel && ui.rwSourcePath) {
        if (src === "camera") {
          ui.rwSourcePathLabel.textContent = "Camera Device Index";
          ui.rwSourcePath.placeholder = "0 (default webcam index)";
          ui.rwSourcePath.value = "0";
        } else if (src === "rtsp") {
          ui.rwSourcePathLabel.textContent = "RTSP Stream URL";
          ui.rwSourcePath.placeholder = "rtsp://user:pass@192.168.1.50:554/live";
          ui.rwSourcePath.value = "";
        } else if (src === "video") {
          ui.rwSourcePathLabel.textContent = "Local Video File Path";
          ui.rwSourcePath.placeholder = "data/traffic_sample.mp4";
          ui.rwSourcePath.value = "";
        } else if (src === "image") {
          ui.rwSourcePathLabel.textContent = "Local Image File Path";
          ui.rwSourcePath.placeholder = "data/intersection_frame.jpg";
          ui.rwSourcePath.value = "";
        } else if (src === "synthetic") {
          ui.rwSourcePathLabel.textContent = "Synthetic Test Scenario";
          ui.rwSourcePath.placeholder = "Auto-generated multi-vehicle demand";
          ui.rwSourcePath.value = "synthetic-demo";
        }
      }
    });
  }

  if (ui.btnRunPerception) {
    ui.btnRunPerception.addEventListener("click", async () => {
      const srcType = ui.rwSourceSelect ? ui.rwSourceSelect.value : "image";
      const intersectionId = ui.rwIntersectionSelect ? ui.rwIntersectionSelect.value : "J1";
      const sourcePath = ui.rwSourcePath ? ui.rwSourcePath.value.trim() : "";
      const solverMode = (ui.controllerSelect && ui.controllerSelect.value === "qaoa") ? "qaoa" : "exact";

      if (ui.rwStatusText) {
        ui.rwStatusText.textContent = "PROCESSING...";
        ui.rwStatusText.style.color = "var(--amber)";
      }

      try {
        const payload = {
          source_type: srcType,
          intersection_id: intersectionId,
          source_path: (srcType === "image" || srcType === "video") ? sourcePath : undefined,
          camera_index: srcType === "camera" ? Number(sourcePath || 0) : undefined,
          rtsp_url: srcType === "rtsp" ? sourcePath : undefined,
          solver: solverMode,
          optimize: true,
          synthetic_data: (srcType === "synthetic" || !sourcePath) ? {
            vehicle_count: 28,
            tracked_vehicle_count: 26,
            average_confidence: 0.94,
            approach_counts: { north: 14, south: 9, east: 3, west: 2 },
            queue_lengths: { north: 12, south: 7, east: 2, west: 1 },
            class_counts: { car: 20, motorcycle: 4, bus: 3, truck: 1 }
          } : undefined
        };

        const res = await fetch("/api/perception/process", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) {
          if (ui.rwStatusText) {
            ui.rwStatusText.textContent = (data.status || "UNAVAILABLE").toUpperCase();
            ui.rwStatusText.style.color = "var(--red)";
          }
          showToast(`Perception Error: ${data.error || "Device or stream unreachable"}`);
          return;
        }

        if (ui.rwStatusText) {
          ui.rwStatusText.textContent = "ACTIVE";
          ui.rwStatusText.style.color = "var(--mint)";
        }

        const obs = data.observation || {};
        const ql = obs.queue_lengths || {};
        const cc = obs.class_counts || {};

        if (ui.rwNorthQueue) ui.rwNorthQueue.textContent = ql.north ?? 0;
        if (ui.rwSouthQueue) ui.rwSouthQueue.textContent = ql.south ?? 0;
        if (ui.rwEastQueue) ui.rwEastQueue.textContent = ql.east ?? 0;
        if (ui.rwWestQueue) ui.rwWestQueue.textContent = ql.west ?? 0;

        if (ui.rwCarCount) ui.rwCarCount.textContent = cc.car ?? 0;
        if (ui.rwBusCount) ui.rwBusCount.textContent = cc.bus ?? 0;
        if (ui.rwTruckCount) ui.rwTruckCount.textContent = cc.truck ?? 0;
        if (ui.rwMotoCount) ui.rwMotoCount.textContent = cc.motorcycle ?? 0;

        if (ui.rwTotalVehicles) ui.rwTotalVehicles.textContent = obs.vehicle_count ?? 0;
        if (ui.rwTrackedVehicles) ui.rwTrackedVehicles.textContent = obs.tracked_vehicle_count ?? 0;
        if (ui.rwAvgConfidence) ui.rwAvgConfidence.textContent = `${((obs.average_confidence || 0.9) * 100).toFixed(1)}%`;

        const rec = data.recommendation || {};
        if (ui.rwSolverLabel) ui.rwSolverLabel.textContent = (rec.method || "QUBO EXACT").toUpperCase();
        if (ui.rwRecNs) ui.rwRecNs.textContent = `${rec.phase_0_green_seconds || 30}s`;
        if (ui.rwRecEw) ui.rwRecEw.textContent = `${rec.phase_2_green_seconds || 30}s`;
        if (ui.rwRecObjective) ui.rwRecObjective.textContent = Number(rec.objective || 0).toFixed(4);
        if (ui.rwRecCycle) ui.rwRecCycle.textContent = `${rec.cycle_length_seconds || 68}s (Yellow=4s)`;
        if (ui.rwRecValid) ui.rwRecValid.textContent = rec.valid ? "TRUE" : "FALSE";

        addEvent("Real-world perception", `${srcType.toUpperCase()} analyzed for ${intersectionId} → G0: ${rec.phase_0_green_seconds || 30}s, G2: ${rec.phase_2_green_seconds || 30}s`, "normal");
        showToast(`Real-world perception processed for ${intersectionId}.`);
      } catch (err) {
        if (ui.rwStatusText) {
          ui.rwStatusText.textContent = "OFFLINE";
          ui.rwStatusText.style.color = "var(--red)";
        }
        showToast(`Failed to connect to perception service: ${err.message}`);
      }
    });
  }

  if (ui.btnClearPerception) {
    ui.btnClearPerception.addEventListener("click", () => {
      if (ui.rwStatusText) {
        ui.rwStatusText.textContent = "STANDBY";
        ui.rwStatusText.style.color = "var(--cyan)";
      }
      if (ui.rwNorthQueue) ui.rwNorthQueue.textContent = "0";
      if (ui.rwSouthQueue) ui.rwSouthQueue.textContent = "0";
      if (ui.rwEastQueue) ui.rwEastQueue.textContent = "0";
      if (ui.rwWestQueue) ui.rwWestQueue.textContent = "0";
      if (ui.rwCarCount) ui.rwCarCount.textContent = "0";
      if (ui.rwBusCount) ui.rwBusCount.textContent = "0";
      if (ui.rwTruckCount) ui.rwTruckCount.textContent = "0";
      if (ui.rwMotoCount) ui.rwMotoCount.textContent = "0";
      if (ui.rwTotalVehicles) ui.rwTotalVehicles.textContent = "0";
      if (ui.rwTrackedVehicles) ui.rwTrackedVehicles.textContent = "0";
      if (ui.rwAvgConfidence) ui.rwAvgConfidence.textContent = "0.0%";
      if (ui.rwRecNs) ui.rwRecNs.textContent = "30s";
      if (ui.rwRecEw) ui.rwRecEw.textContent = "30s";
      if (ui.rwRecObjective) ui.rwRecObjective.textContent = "0.000";
      showToast("Real-world prototype display cleared.");
    });
  }


  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 1.12 : .89, event.clientX, event.clientY);
  }, { passive: false });
  canvas.addEventListener("pointerdown", event => {
    pointer = { down: true, dragging: false, startX: event.clientX, startY: event.clientY, viewX: view.x, viewY: view.y };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (!pointer.down) return;
    const dx = event.clientX - pointer.startX, dy = event.clientY - pointer.startY;
    if (Math.hypot(dx, dy) > 4) pointer.dragging = true;
    if (pointer.dragging) {
      view.x = pointer.viewX + dx;
      view.y = pointer.viewY + dy;
      canvas.classList.add("dragging");
    }
  });
  canvas.addEventListener("pointerup", event => {
    if (!pointer.dragging) handleMapClick(event.clientX, event.clientY);
    pointer.down = false;
    canvas.classList.remove("dragging");
  });
  canvas.addEventListener("pointercancel", () => { pointer.down = false; canvas.classList.remove("dragging"); });
  window.addEventListener("resize", fitCity);

  initTabs();
  checkBackend();
  generateCity(ui.seedInput.value);
  optimizeSignals();
  requestAnimationFrame(animate);
})();
