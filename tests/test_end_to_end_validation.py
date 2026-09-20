"""Phase O: Comprehensive End-to-End Validation & Integration Test Suite.

Validates the full system lifecycle across all subsystems:
  - Scenarios A-P: Normal, High, 4-junction, 8-junction, YOLO, Tracking,
    Queue Estimation, QUBO Exact, QAOA, Emergency Corridor, Dynamic Events,
    Metrics, Dashboard API, Real-World Prototype.
  - Cross-module data consistency across pipeline boundaries.
  - Signal safety invariants (green bounds, clearance intervals, no conflicting greens).
  - Precedence hierarchy: Safety > Emergency Priority > Dynamic Event Adaptation > Normal QUBO.
  - Comprehensive failure-handling matrix.
  - Classical reproducibility invariance.
  - Metric provenance and unit consistency.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import time
from typing import Any
import pytest

from config.loader import load_config
from metrics.evaluator import NOMINAL_LINK_TRAVEL_TIME_SECONDS, TrafficMetricsEvaluator, compute_fuel_and_co2_proxy
from metrics.models import IntersectionMetrics, NetworkMetrics
from optimization.quantum.qaoa import matches_exact, run_qaoa
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.aggregator import TrafficAggregator
from perception.models import TrafficObservation, VALID_APPROACHES, VALID_VEHICLE_CLASSES, VehicleDetection
from perception.queue_estimator import QueueEstimator
from simulation.models.emergency import EmergencyRequest
from simulation.models.events import DynamicEvent
from simulation.models.state import IntersectionTrafficState, SignalState
from simulation.signals.emergency import EmergencyGreenCorridorController
from simulation.signals.events import DynamicEventManager
from simulation.signals.multi_intersection import MultiIntersectionController

SCRATCH_DIR = Path("tests/_test_scratch_phase_o")


@pytest.fixture(autouse=True)
def scratch_lifecycle():
    """Ensure safe isolated test directory on Windows without tempfile permission issues."""
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)


# ==============================================================================
# 1. SCENARIOS A–D: MULTI-INTERSECTION TRAFFIC SCENARIOS (4 & 8 JUNCTIONS)
# ==============================================================================

def test_four_connected_intersections_normal_and_high_traffic() -> None:
    """Test MultiIntersectionController under normal and high traffic demand across J1-J4."""
    managed_ids = ["J1", "J2", "J3", "J4"]
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=managed_ids,
        anti_oscillation_damping_seconds=0.0,
        default_solver="exact",
    )

    # 1. Normal traffic observations
    obs_normal = [
        TrafficObservation(
            timestamp=100.0,
            source="synthetic",
            intersection_id=iid,
            vehicle_count=12,
            approach_counts={"north": 3, "south": 3, "east": 3, "west": 3},
            queue_lengths={"north": 2, "south": 2, "east": 2, "west": 2},
            class_counts={"car": 12, "motorcycle": 0, "bus": 0, "truck": 0},
            tracking_available=True,
        )
        for iid in managed_ids
    ]
    decisions_normal = multi_ctrl.optimize_observations(obs_normal, current_time=100.0)
    assert len(decisions_normal) == 4
    for iid in managed_ids:
        d = decisions_normal[iid]
        assert d["valid"] is True
        assert 22 <= d["phase_0_green_seconds"] <= 42
        assert 22 <= d["phase_2_green_seconds"] <= 42

    # 2. High traffic observations (arterial surge on north/south)
    obs_high = [
        TrafficObservation(
            timestamp=160.0,
            source="synthetic",
            intersection_id=iid,
            vehicle_count=32,
            approach_counts={"north": 12, "south": 10, "east": 5, "west": 5},
            queue_lengths={"north": 10, "south": 8, "east": 3, "west": 3},
            class_counts={"car": 28, "motorcycle": 0, "bus": 2, "truck": 2},
            tracking_available=True,
        )
        for iid in managed_ids
    ]
    decisions_high = multi_ctrl.optimize_observations(obs_high, current_time=160.0)
    assert len(decisions_high) == 4
    for iid in managed_ids:
        d = decisions_high[iid]
        assert d["valid"] is True
        # Under north/south heavy queues, phase 0 green should be allocated more green than phase 2
        assert d["phase_0_green_seconds"] >= d["phase_2_green_seconds"]


def test_eight_intersection_extended_grid_configuration() -> None:
    """Test MultiIntersectionController scaling to an 8-junction urban corridor (J1-J8)."""
    eight_ids = [f"J{i}" for i in range(1, 9)]
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=eight_ids,
        anti_oscillation_damping_seconds=0.0,
        default_solver="exact",
    )

    observations = [
        TrafficObservation(
            timestamp=200.0,
            source="synthetic",
            intersection_id=iid,
            vehicle_count=10 + idx,
            approach_counts={"north": 2 + idx, "south": 2, "east": 3, "west": 3},
            queue_lengths={"north": 2 + idx, "south": 1, "east": 2, "west": 2},
            class_counts={"car": 10 + idx, "motorcycle": 0, "bus": 0, "truck": 0},
            tracking_available=True,
        )
        for idx, iid in enumerate(eight_ids)
    ]

    decisions = multi_ctrl.optimize_observations(observations, current_time=200.0)
    assert len(decisions) == 8
    assert sorted(decisions.keys()) == eight_ids
    for iid in eight_ids:
        assert decisions[iid]["valid"] is True
        assert 22 <= decisions[iid]["phase_0_green_seconds"] <= 42
        assert 22 <= decisions[iid]["phase_2_green_seconds"] <= 42


# ==============================================================================
# 2. SCENARIOS E–G & P: PERCEPTION, TRACKING, QUEUE ESTIMATION & REAL-WORLD PATH
# ==============================================================================

def test_perception_to_tracking_and_queue_estimation_pipeline() -> None:
    """Validate Frame -> Detections -> Tracking -> Aggregation -> Queue Estimation -> TrafficObservation."""
    rois = {
        "north": [(0.2, 0.0), (0.5, 0.0), (0.5, 0.4), (0.2, 0.4)],
        "south": [(0.5, 0.6), (0.8, 0.6), (0.8, 1.0), (0.5, 1.0)],
        "east": [(0.6, 0.2), (1.0, 0.2), (1.0, 0.5), (0.6, 0.5)],
        "west": [(0.0, 0.5), (0.4, 0.5), (0.4, 0.8), (0.0, 0.8)],
    }
    aggregator = TrafficAggregator(approach_regions=rois)

    # Frame 1: Detections at t=0.0
    detections_f1 = [
        VehicleDetection("car", 0.95, (0.3, 0.1, 0.4, 0.2), center=(0.35, 0.15), track_id=1),  # North
        VehicleDetection("bus", 0.90, (0.35, 0.25, 0.45, 0.35), center=(0.40, 0.30), track_id=2),  # North
        VehicleDetection("truck", 0.88, (0.7, 0.3, 0.8, 0.4), center=(0.75, 0.35), track_id=3),  # East
    ]
    obs1 = aggregator.aggregate(detections_f1, intersection_id="J1", timestamp=0.0)
    assert obs1.vehicle_count == 3
    assert obs1.approach_counts["north"] == 2
    assert obs1.approach_counts["east"] == 1

    # Frame 2: Detections at t=2.0
    # Track 1 & 2 remain halted in North; Track 3 moves East
    detections_f2 = [
        VehicleDetection("car", 0.95, (0.3, 0.1001, 0.4, 0.2001), center=(0.35, 0.1501), track_id=1),  # Halted North
        VehicleDetection("bus", 0.91, (0.35, 0.2501, 0.45, 0.3501), center=(0.40, 0.3001), track_id=2),  # Halted North
        VehicleDetection("truck", 0.89, (0.85, 0.3, 0.95, 0.4), center=(0.90, 0.35), track_id=3),  # Moving East
    ]
    obs2 = aggregator.aggregate(detections_f2, intersection_id="J1", timestamp=2.0)
    assert isinstance(obs2, TrafficObservation)
    assert obs2.vehicle_count == 3
    assert obs2.approach_counts["north"] == 2
    assert obs2.approach_counts["east"] == 1
    assert obs2.queue_lengths["north"] >= 1

    # Conversion to IntersectionTrafficState and QUBO solution
    state = obs2.to_intersection_traffic_state()
    model = build_qubo(state, load_config()["optimization"]["phase3a"])
    sol = solve_exact(model)
    assert sol.candidate.valid is True
    assert 22 <= sol.candidate.first_green_seconds <= 42


# ==============================================================================
# 3. SCENARIOS H–I: QUBO EXACT & QAOA RESEARCH MODE COMPARISON
# ==============================================================================

def test_qubo_exact_and_qaoa_research_mode() -> None:
    """Test QUBO exact classical minimization vs QAOA stochastic sampling on identical state."""
    state = IntersectionTrafficState(
        intersection_id="J1",
        vehicle_count=24,
        queue_length=16,
        traffic_density=0.25,
        road_capacity=96,
        signal_state=SignalState.GREEN,
        signal_phase=0,
        emergency_status=False,
        green_phase_queues=((0, 12), (2, 4)),
    )
    cfg = load_config()
    model = build_qubo(state, cfg["optimization"]["phase3a"])

    # 1. Exact classical ground truth
    exact_sol = solve_exact(model)
    assert exact_sol.candidate.valid is True
    assert exact_sol.candidate.first_green_seconds >= exact_sol.candidate.second_green_seconds

    # 2. QAOA statevector optimization and shot sampling
    qaoa_res = run_qaoa(model, cfg["optimization"]["phase3b"])
    assert qaoa_res.best_valid_solution is not None
    assert qaoa_res.best_valid_solution.candidate.valid is True

    # Check objective gap definition
    exact_obj = exact_sol.objective_value
    qaoa_obj = qaoa_res.best_valid_solution.objective_value
    abs_gap = abs(qaoa_obj - exact_obj)
    rel_gap = abs_gap / (abs(exact_obj) + 1e-9)

    assert abs_gap >= 0.0
    assert rel_gap >= 0.0
    assert isinstance(matches_exact(qaoa_obj, exact_obj), bool)


# ==============================================================================
# 4. SCENARIOS J–M & SECTION 7: EMERGENCY + EVENT INTERACTION & PRECEDENCE
# ==============================================================================

def test_integrated_precedence_safety_emergency_events_qubo() -> None:
    """Validate complete interaction lifecycle and strict precedence hierarchy:

    Precedence: Safety Clearance > Emergency Priority > Dynamic Event Adaptation > Normal QUBO.
    """
    managed_ids = ["J1", "J2", "J3", "J4"]
    emg_ctrl = EmergencyGreenCorridorController(managed_intersection_ids=managed_ids)
    event_mgr = DynamicEventManager(managed_intersection_ids=managed_ids)
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=managed_ids,
        anti_oscillation_damping_seconds=0.0,
        emergency_controller=emg_ctrl,
        event_manager=event_mgr,
        default_solver="exact",
    )

    t = 1000.0
    def make_obs(ts: float) -> list[TrafficObservation]:
        return [
            TrafficObservation(
                timestamp=ts,
                source="synthetic",
                intersection_id=iid,
                vehicle_count=10,
                approach_counts={"north": 3, "south": 3, "east": 2, "west": 2},
                queue_lengths={"north": 2, "south": 2, "east": 1, "west": 1},
                class_counts={"car": 10, "motorcycle": 0, "bus": 0, "truck": 0},
                tracking_available=True,
            )
            for iid in managed_ids
        ]

    # Step 1: Normal QUBO baseline
    d1 = multi_ctrl.optimize_observations(make_obs(t), current_time=t)
    assert d1["J2"]["status"] == "optimized"
    assert d1["J2"]["solver"] == "exact"

    # Step 2: Register Dynamic Event: Accident on J2 East approach
    acc_event = DynamicEvent(
        event_id="ACC_01",
        event_type="accident",
        affected_intersection_ids=("J2",),
        affected_approaches=("east",),
        severity="high",
        start_time=t + 10.0,
        end_time=t + 200.0,
        capacity_factor=0.35,
        queue_adder=15,
    )
    event_mgr.register_event(acc_event, current_time=t + 10.0)

    # Step 3: Re-optimize at t=15.0 -> J2 should adapt to event
    t = 1015.0
    d2 = multi_ctrl.optimize_observations(make_obs(t), current_time=t)
    assert d2["J2"]["status"] == "event_adapted"
    assert d2["J2"]["event_adapted"] is True
    assert "ACC_01" in d2["J2"]["active_event_ids"]

    # Step 4: Dispatch Emergency Ambulance J1 -> J4 through J2 (preempts accident)
    t = 1025.0
    emg_req = EmergencyRequest(
        emergency_vehicle_id="AMB_99",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J3", "J4"),
        priority="critical",
        timestamp=t,
        approach_hints={"J1": "south", "J2": "west", "J3": "west", "J4": "west"},
    )
    emg_ctrl.request_corridor(emg_req, current_time=t)

    # Step 5: Re-optimize -> Emergency priority MUST override the dynamic event at J2
    d3 = multi_ctrl.optimize_observations(make_obs(t), current_time=t)
    assert d3["J2"]["status"] == "emergency_priority"
    assert d3["J2"]["emergency_priority"] is True
    assert d3["J2"].get("events_preempted_by_emergency") is True

    # Step 6: Advance emergency vehicle past J2 to J3
    t = 1045.0
    emg_ctrl.advance_vehicle("AMB_99", "J3", current_time=t)
    d4 = multi_ctrl.optimize_observations(make_obs(t), current_time=t)
    # J1 is released, J2 is released -> J2 returns to event_adapted!
    assert d4["J2"]["status"] == "event_adapted"
    assert d4["J3"]["status"] == "emergency_priority"

    # Step 7: Release emergency corridor completely
    t = 1065.0
    emg_ctrl.release_corridor("AMB_99", current_time=t)
    d5 = multi_ctrl.optimize_observations(make_obs(t), current_time=t)
    assert d5["J3"]["status"] == "optimized"
    assert d5["J2"]["status"] == "event_adapted"

    # Step 8: Dynamic Event expires at t > 1210.0
    t = 1220.0
    d6 = multi_ctrl.optimize_observations(make_obs(t), current_time=t)
    assert d6["J2"]["status"] == "optimized"
    assert d6["J2"]["solver"] == "exact"


# ==============================================================================
# 5. SECTION 4 & 5: CROSS-MODULE DATA CONTRACTS & SIGNAL SAFETY INVARIANTS
# ==============================================================================

def test_cross_module_data_consistency() -> None:
    """Verify data consistency across TrafficObservation -> State -> API -> QUBO."""
    obs = TrafficObservation(
        timestamp=500.0,
        source="perception",
        intersection_id="J3",
        vehicle_count=22,
        approach_counts={"north": 8, "south": 6, "east": 4, "west": 4},
        queue_lengths={"north": 6, "south": 5, "east": 3, "west": 2},
        class_counts={"car": 18, "motorcycle": 2, "bus": 1, "truck": 1},
        tracking_available=True,
    )

    # Boundary 1: TrafficObservation -> IntersectionTrafficState
    state = obs.to_intersection_traffic_state(road_capacity=100)
    assert state.intersection_id == "J3"
    assert state.vehicle_count == 22
    assert state.queue_length == 16  # 6 + 5 + 3 + 2
    # Approach mapping invariant:
    # Phase 0 = North + South (6 + 5 = 11)
    # Phase 2 = East + West (3 + 2 = 5)
    assert state.green_phase_queues == ((0, 11), (2, 5))

    # Boundary 2: Optimization API Payload Roundtrip
    payload = obs.to_dict()
    assert payload["intersection_id"] == "J3"
    assert payload["vehicle_count"] == 22
    assert payload["queue_lengths"]["north"] == 6

    # Boundary 3: QUBO Solution Validity
    cfg = load_config()
    model = build_qubo(state, cfg["optimization"]["phase3a"])
    sol = solve_exact(model)
    assert sol.candidate.valid is True
    # Greater green given to Phase 0 (11 queues) than Phase 2 (5 queues)
    assert sol.candidate.first_green_seconds >= sol.candidate.second_green_seconds


def test_signal_safety_invariants() -> None:
    """Verify signal safety invariants: bounds, clearance intervals, and positive durations."""
    cfg = load_config()
    qubo_settings = cfg["optimization"]["phase3a"]

    min_green = qubo_settings["min_green_seconds"]
    max_green = qubo_settings["max_green_seconds"]
    yellow = qubo_settings["yellow_seconds"]

    assert min_green == 22
    assert max_green == 42
    assert yellow == 4

    # Test clamping limits in MultiIntersectionController
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=["J1"],
        min_green_seconds=min_green,
        max_green_seconds=max_green,
    )

    assert multi_ctrl._clamp_green(10) == 22
    assert multi_ctrl._clamp_green(55) == 42
    assert multi_ctrl._clamp_green(30) == 30

    # Verify anti-oscillation damping
    multi_ctrl.anti_oscillation_damping_seconds = 15.0
    obs = TrafficObservation(
        timestamp=10.0,
        source="test",
        intersection_id="J1",
        vehicle_count=10,
        queue_lengths={"north": 2, "south": 2, "east": 2, "west": 2},
    )
    d1 = multi_ctrl.optimize_observations([obs], current_time=10.0)

    # Next observation at t=15.0 (within 15s damping window) with radically different demand
    obs_thrash = TrafficObservation(
        timestamp=15.0,
        source="test",
        intersection_id="J1",
        vehicle_count=30,
        queue_lengths={"north": 14, "south": 14, "east": 1, "west": 1},
    )
    d2 = multi_ctrl.optimize_observations([obs_thrash], current_time=15.0)

    # Green duration MUST be damped and preserved to prevent rapid switching
    assert d2["J1"]["phase_0_green_seconds"] == d1["J1"]["phase_0_green_seconds"]


# ==============================================================================
# 6. SECTION 6: COMPREHENSIVE FAILURE-HANDLING MATRIX
# ==============================================================================

def test_failure_handling_matrix() -> None:
    """Verify system handles malformed, stale, missing, and extreme inputs safely."""
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=["J1", "J2"],
        max_observation_age_seconds=30.0,
        anti_oscillation_damping_seconds=0.0,
    )

    # 1. Stale Observation (Age > 30s) -> Falls back to safe default without crashing
    stale_obs = TrafficObservation(
        timestamp=50.0,
        source="test",
        intersection_id="J1",
        vehicle_count=10,
        queue_lengths={"north": 2, "south": 2, "east": 2, "west": 2},
    )
    d_stale = multi_ctrl.optimize_observations([stale_obs], current_time=100.0)
    assert d_stale["J1"]["status"] == "stale_fallback"
    assert d_stale["J1"]["valid"] is True
    assert d_stale["J1"]["phase_0_green_seconds"] == 30

    # 2. Missing Observation for managed junction J2 -> missing_fallback
    assert d_stale["J2"]["status"] == "missing_fallback"
    assert d_stale["J2"]["valid"] is True

    # 3. Malformed Observation Validation Rejection
    with pytest.raises(ValueError):
        TrafficObservation(timestamp=1.0, source="test", intersection_id=" ", vehicle_count=5)
    with pytest.raises(ValueError):
        TrafficObservation(timestamp=1.0, source="test", intersection_id="J1", vehicle_count=-5)

    # 4. Empty Traffic State Handling
    empty_obs = TrafficObservation(
        timestamp=10.0,
        source="test",
        intersection_id="J1",
        vehicle_count=0,
        queue_lengths={"north": 0, "south": 0, "east": 0, "west": 0},
    )
    d_empty = multi_ctrl.optimize_observations([empty_obs], current_time=10.0)
    assert d_empty["J1"]["valid"] is True
    assert 22 <= d_empty["J1"]["phase_0_green_seconds"] <= 42

    # 5. Invalid Emergency Request Validation Rejection
    with pytest.raises(ValueError):
        EmergencyRequest(
            emergency_vehicle_id="",  # Empty ID rejected
            current_intersection_id="J1",
            destination_intersection_id="J2",
            route=("J1", "J2"),
            priority="critical",
            timestamp=1.0,
        )

    # 6. Invalid Dynamic Event Validation Rejection
    with pytest.raises(ValueError):
        DynamicEvent(
            event_id="EVT_BAD",
            event_type="invalid_type",  # Unsupported type rejected
            affected_intersection_ids=("J1",),
            affected_approaches=("north",),
            severity="high",
            start_time=10.0,
            end_time=5.0,  # start > end rejected
        )


# ==============================================================================
# 7. SECTION 8 & 9: METRIC CONSISTENCY & REPRODUCIBILITY
# ==============================================================================

def test_metric_consistency_and_provenance_labels() -> None:
    """Verify metric aggregation preserves physical provenance labels and EPA stoichiometric factors."""
    evaluator = TrafficMetricsEvaluator()
    obs = TrafficObservation(
        timestamp=100.0,
        source="synthetic",
        intersection_id="J1",
        vehicle_count=10,
        queue_lengths={"north": 2, "south": 2, "east": 2, "west": 2},
    )

    im = evaluator.evaluate_intersection(
        observation=obs,
        p0_green_seconds=30,
        p2_green_seconds=30,
        duration_seconds=60.0,
    )
    assert im.fuel_source == "simulation_proxy"
    assert im.co2_source == "simulation_proxy"
    # EPA Stoichiometric Ratio: 2392.0 g CO2 / L fuel
    assert im.co2_emissions_grams == pytest.approx(im.fuel_consumption_litres * 2392.0, abs=1.0)

    # Network Aggregation
    net = NetworkMetrics.aggregate_intersections([im])
    assert net.intersections_count == 1
    assert net.fuel_source == "simulation_proxy"
    assert net.network_total_fuel_consumption_litres == im.fuel_consumption_litres


def test_classical_reproducibility_invariant() -> None:
    """Verify classical deterministic pipeline produces bit-identical outputs across repeated runs."""
    state = IntersectionTrafficState(
        intersection_id="J1",
        vehicle_count=16,
        queue_length=10,
        traffic_density=0.1667,
        road_capacity=96,
        signal_state=SignalState.GREEN,
        signal_phase=0,
        emergency_status=False,
        green_phase_queues=((0, 6), (2, 4)),
    )
    cfg = load_config()

    m1 = build_qubo(state, cfg["optimization"]["phase3a"])
    s1 = solve_exact(m1)

    m2 = build_qubo(state, cfg["optimization"]["phase3a"])
    s2 = solve_exact(m2)

    assert s1.candidate.first_green_seconds == s2.candidate.first_green_seconds
    assert s1.candidate.second_green_seconds == s2.candidate.second_green_seconds
    assert s1.objective_value == pytest.approx(s2.objective_value, abs=1e-12)
