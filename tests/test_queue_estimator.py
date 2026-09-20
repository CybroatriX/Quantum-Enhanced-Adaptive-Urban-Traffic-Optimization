"""Unit tests for prototype queue length estimation and motion state classification."""

import pytest

from config.loader import load_config
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.aggregator import TrafficAggregator
from perception.models import VehicleDetection
from perception.queue_estimator import MotionState, QueueEstimator


def test_motion_classification_thresholds():
    estimator = QueueEstimator(
        stopped_speed_threshold=5.0,
        slow_speed_threshold=15.0,
    )

    # Frame 1 at t=0
    det_stopped = VehicleDetection("car", 0.9, (10, 10, 30, 30), (20, 20), track_id=1)
    det_slow = VehicleDetection("car", 0.9, (50, 50, 70, 70), (60, 60), track_id=2)
    det_moving = VehicleDetection("car", 0.9, (100, 100, 120, 120), (110, 110), track_id=3)

    estimator.update_tracks([det_stopped, det_slow, det_moving], timestamp=0.0)

    # Frame 2 at t=1.0
    # Track 1 moved 2 pixels (speed = 2.0 px/s <= 5.0 -> STOPPED)
    det_stopped_f2 = VehicleDetection("car", 0.9, (10, 12, 30, 32), (20, 22), track_id=1)
    # Track 2 moved 10 pixels (speed = 10.0 px/s <= 15.0 -> SLOW)
    det_slow_f2 = VehicleDetection("car", 0.9, (50, 60, 70, 80), (60, 70), track_id=2)
    # Track 3 moved 40 pixels (speed = 40.0 px/s > 15.0 -> MOVING)
    det_moving_f2 = VehicleDetection("car", 0.9, (100, 140, 120, 160), (110, 150), track_id=3)

    speeds = estimator.update_tracks([det_stopped_f2, det_slow_f2, det_moving_f2], timestamp=1.0)

    assert estimator.classify_motion(1, speeds) == MotionState.STOPPED
    assert estimator.classify_motion(2, speeds) == MotionState.SLOW
    assert estimator.classify_motion(3, speeds) == MotionState.MOVING


def test_queue_estimation_multiple_approaches():
    estimator = QueueEstimator(
        stopped_speed_threshold=5.0,
        slow_speed_threshold=15.0,
        include_slow_in_queue=True,
    )

    # Setup 4 tracked vehicles across approaches:
    # North: Track 1 (stopped), Track 2 (moving)
    # South: Track 3 (slow)
    # East: Track 4 (stopped)
    # West: None

    # Frame 1 at t=0
    f1 = [
        VehicleDetection("car", 0.9, (10, 10, 30, 30), (20, 20), track_id=1),     # north
        VehicleDetection("car", 0.9, (40, 10, 60, 30), (50, 20), track_id=2),     # north
        VehicleDetection("car", 0.9, (10, 300, 30, 320), (20, 310), track_id=3),  # south
        VehicleDetection("truck", 0.9, (400, 10, 420, 30), (410, 20), track_id=4), # east
    ]
    approaches = ["north", "north", "south", "east"]
    estimator.estimate_queues(f1, approaches, timestamp=0.0)

    # Frame 2 at t=1.0: apply displacements
    f2 = [
        # Track 1 moved 1 pixel (speed 1.0 -> STOPPED -> in queue)
        VehicleDetection("car", 0.9, (10, 11, 30, 31), (20, 21), track_id=1),
        # Track 2 moved 30 pixels (speed 30.0 -> MOVING -> NOT in queue)
        VehicleDetection("car", 0.9, (40, 40, 60, 60), (50, 50), track_id=2),
        # Track 3 moved 8 pixels (speed 8.0 -> SLOW -> in queue)
        VehicleDetection("car", 0.9, (10, 308, 30, 328), (20, 318), track_id=3),
        # Track 4 moved 0 pixels (speed 0.0 -> STOPPED -> in queue)
        VehicleDetection("truck", 0.9, (400, 10, 420, 30), (410, 20), track_id=4),
    ]

    queues = estimator.estimate_queues(f2, approaches, timestamp=1.0)

    # North has 2 vehicles, but only Track 1 is queued
    assert queues["north"] == 1
    # South has 1 vehicle which is slow -> queued
    assert queues["south"] == 1
    # East has 1 vehicle which is stopped -> queued
    assert queues["east"] == 1
    # West has 0 vehicles
    assert queues["west"] == 0


def test_queue_estimation_untracked_and_first_frame():
    # Test safe handling when track IDs are None or history has only 1 observation
    estimator = QueueEstimator(
        first_frame_default_state=MotionState.STOPPED,
        untracked_default_state=MotionState.STOPPED,
    )

    detections = [
        # First-frame tracked vehicle
        VehicleDetection("car", 0.9, (10, 10, 30, 30), (20, 20), track_id=99),
        # Completely untracked vehicle (track_id is None)
        VehicleDetection("bus", 0.85, (10, 40, 30, 60), (20, 50), track_id=None),
    ]

    queues = estimator.estimate_queues(detections, ["north", "south"], timestamp=10.0)
    assert queues["north"] == 1
    assert queues["south"] == 1


def test_queue_estimation_empty_detections():
    estimator = QueueEstimator()
    queues = estimator.estimate_queues([], [], timestamp=0.0)
    assert queues == {"north": 0, "south": 0, "east": 0, "west": 0}


def test_queue_estimation_with_aggregator_and_qubo_optimization():
    config = load_config()
    aggregator = TrafficAggregator(
        approach_regions={
            "north": [0, 0, 200, 200],
            "south": [0, 300, 200, 500],
            "east": [300, 0, 500, 200],
            "west": [300, 300, 500, 500],
        }
    )

    # Step 1: Initial observation at t=0
    # North: 3 vehicles (tids: 1, 2, 3)
    # East: 1 vehicle (tid: 4)
    frame_1 = [
        VehicleDetection("car", 0.9, (20, 20, 50, 50), (35, 35), track_id=1),
        VehicleDetection("car", 0.9, (60, 20, 90, 50), (75, 35), track_id=2),
        VehicleDetection("bus", 0.95, (100, 20, 130, 50), (115, 35), track_id=3),
        VehicleDetection("truck", 0.88, (320, 20, 350, 50), (335, 35), track_id=4),
    ]
    aggregator.aggregate(frame_1, intersection_id="J1", timestamp=0.0)

    # Step 2: Observation at t=1.0
    # Track 1 & 2 stopped (speed = 0)
    # Track 3 moving fast (speed = 40 px/s)
    # Track 4 stopped (speed = 0)
    frame_2 = [
        VehicleDetection("car", 0.9, (20, 20, 50, 50), (35, 35), track_id=1),     # stopped
        VehicleDetection("car", 0.9, (60, 20, 90, 50), (75, 35), track_id=2),     # stopped
        VehicleDetection("bus", 0.95, (100, 60, 130, 90), (115, 75), track_id=3), # moving (dy=40)
        VehicleDetection("truck", 0.88, (320, 20, 350, 50), (335, 35), track_id=4), # stopped
    ]
    obs = aggregator.aggregate(frame_2, intersection_id="J1", timestamp=1.0)

    # Total vehicle count = 4
    assert obs.vehicle_count == 4
    # North queue: Track 1 & 2 stopped -> 2 queued (out of 3 vehicles)
    assert obs.queue_lengths["north"] == 2
    # East queue: Track 4 stopped -> 1 queued
    assert obs.queue_lengths["east"] == 1
    assert obs.queue_lengths["south"] == 0
    assert obs.queue_lengths["west"] == 0

    # Convert observation to IntersectionTrafficState
    state = obs.to_intersection_traffic_state(road_capacity=100)
    assert state.intersection_id == "J1"
    # Phase 0 = North queue (2) + South queue (0) = 2
    # Phase 2 = East queue (1) + West queue (0) = 1
    assert state.green_phase_queues == ((0, 2), (2, 1))
    assert state.queue_length == 3

    # Feed state directly to canonical QUBO and exact solver
    model = build_qubo(state, config["optimization"]["phase3a"])
    solution = solve_exact(model)
    assert solution.candidate.valid is True
    # Verify candidate green times are computed safely
    assert solution.candidate.first_green_seconds in config["optimization"]["phase3a"]["candidate_green_seconds"]
    assert solution.candidate.second_green_seconds in config["optimization"]["phase3a"]["candidate_green_seconds"]
