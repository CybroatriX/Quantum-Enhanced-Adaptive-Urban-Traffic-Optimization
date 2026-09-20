(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.TrafficOptimizer = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DEFAULT_SETTINGS = Object.freeze({
    candidateGreenSeconds: [22, 30, 40],
    targetTotalGreenSeconds: 60,
    minGreenSeconds: 22,
    maxGreenSeconds: 42,
    yellowSeconds: 4,
    minCycleSeconds: 52,
    maxCycleSeconds: 92,
    waitingWeight: 1,
    imbalanceWeight: 4,
    cycleWeight: 20,
    pedestrianWeight: 1.8
  });

  function candidateCost(firstGreen, secondGreen, state, settings = DEFAULT_SETTINGS) {
    let rawFirstQueue = state.phase_0_queue !== undefined ? state.phase_0_queue : state.nsQueue;
    if (rawFirstQueue === undefined && state.queue_lengths && typeof state.queue_lengths === "object") {
      rawFirstQueue = (Number(state.queue_lengths.north) || 0) + (Number(state.queue_lengths.south) || 0);
    }
    const firstQueue = Math.max(0, Number(rawFirstQueue) || 0);

    let rawSecondQueue = state.phase_2_queue !== undefined ? state.phase_2_queue : state.ewQueue;
    if (rawSecondQueue === undefined && state.queue_lengths && typeof state.queue_lengths === "object") {
      rawSecondQueue = (Number(state.queue_lengths.east) || 0) + (Number(state.queue_lengths.west) || 0);
    }
    const secondQueue = Math.max(0, Number(rawSecondQueue) || 0);

    const totalDemand = firstQueue + secondQueue;
    const demandShare = totalDemand ? firstQueue / totalDemand : 0.5;
    const vehicleCount = Math.max(0, Number(state.vehicle_count !== undefined ? state.vehicle_count : state.vehicleCount) || 0);
    const roadCapacity = Math.max(1, Number(state.road_capacity !== undefined ? state.road_capacity : state.roadCapacity) || 1);
    const density = Math.max(0, Number(state.traffic_density !== undefined ? state.traffic_density : state.trafficDensity) || (vehicleCount / roadCapacity));
    const pedestrianQueue = Math.max(0, Number(state.pedestrianQueue) || 0);
    const congestionScale = 1 + density + vehicleCount / roadCapacity;
    const maximumGreen = settings.maxGreenSeconds;
    const waiting = settings.waitingWeight * congestionScale * (
      firstQueue * Math.pow(1 - firstGreen / maximumGreen, 2) +
      secondQueue * Math.pow(1 - secondGreen / maximumGreen, 2)
    );
    const imbalance = settings.imbalanceWeight * totalDemand * Math.pow(
      firstGreen / (firstGreen + secondGreen) - demandShare,
      2
    );
    const cycle = settings.cycleWeight * Math.pow(
      (firstGreen + secondGreen - settings.targetTotalGreenSeconds) /
        settings.targetTotalGreenSeconds,
      2
    );
    const pedestrian = settings.pedestrianWeight * pedestrianQueue * Math.pow(
      (firstGreen + secondGreen) / (settings.maxCycleSeconds - 2 * settings.yellowSeconds),
      2
    );
    return { waiting, imbalance, cycle, pedestrian, total: waiting + imbalance + cycle + pedestrian };
  }

  function isValidTiming(firstGreen, secondGreen, settings = DEFAULT_SETTINGS) {
    const cycle = firstGreen + secondGreen + 2 * settings.yellowSeconds;
    return firstGreen >= settings.minGreenSeconds &&
      firstGreen <= settings.maxGreenSeconds &&
      secondGreen >= settings.minGreenSeconds &&
      secondGreen <= settings.maxGreenSeconds &&
      cycle >= settings.minCycleSeconds && cycle <= settings.maxCycleSeconds;
  }

  function solveQubo(state, customSettings = {}) {
    const settings = { ...DEFAULT_SETTINGS, ...customSettings };
    const candidates = [];
    for (const nsGreen of settings.candidateGreenSeconds) {
      for (const ewGreen of settings.candidateGreenSeconds) {
        if (!isValidTiming(nsGreen, ewGreen, settings)) continue;
        const cost = candidateCost(nsGreen, ewGreen, state, settings);
        candidates.push({ nsGreen, ewGreen, cost });
      }
    }
    if (!candidates.length) throw new Error("No valid signal timing candidate exists.");
    candidates.sort((a, b) => a.cost.total - b.cost.total || a.nsGreen - b.nsGreen || a.ewGreen - b.ewGreen);
    const best = candidates[0];
    return {
      intersectionId: state.intersection_id ?? state.intersectionId ?? null,
      nsGreen: best.nsGreen,
      ewGreen: best.ewGreen,
      objective: best.cost.total,
      breakdown: best.cost,
      candidatesEvaluated: candidates.length,
      method: "QUBO exact",
      source: "optimization/quantum/qubo.py"
    };
  }

  return { DEFAULT_SETTINGS, candidateCost, isValidTiming, solveQubo };
});
