"""Unit and integration tests for the canonical TrafficObservation data contract."""

import json
import pytest

from config.loader import load_config
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from optimization.service import create_app, parse_state_data
from perception.models import (
    TrafficObservation,
    VALID_APPROACHES,
    VALID_VEHICLE_CLASSES,
    VehicleDetection,
)
from simulation.models.state import IntersectionTrafficState, SignalState


def test_valid_traffic_observation():
    detection = VehicleDetection(
        class_name="car",
        confidence=0.95,
        bbox=(100.0, 150.0, 160.0, 220.0),
        center=(130.0, 185.0),
        track_id=1,
    )
    obs = TrafficObservation(
        timestamp=100.5,
        source="yolov8",
        intersection_id="J1",
        vehicle_count=1,
        approach_counts={"north": 1, "south": 0, "east": 0, "west": 0},
        queue_lengths={"north": 1, "south": 0, "east": 0, "west": 0},
        class_counts={"car": 1, "motorcycle": 0, "bus": 0, "truck": 0},
        detections=(detection,),
        tracking_available=True,
        tracked_vehicle_count=1,
        average_confidence=0.95,
    )

    assert obs.timestamp == 100.5
    assert obs.source == "yolov8"
    assert obs.intersection_id == "J1"
    assert obs.vehicle_count == 1
    assert obs.tracked_vehicle_count == 1
    assert obs.average_confidence == 0.95
    assert obs.tracking_available is True
    assert len(obs.detections) == 1
    assert obs.detections[0].track_id == 1


def test_missing_optional_fields_defaults():
    obs = TrafficObservation(
        timestamp=50.0,
        source="camera_feed",
        intersection_id="J2",
        vehicle_count=0,
    )

    # All 4 approaches must be present with default 0
    assert obs.approach_counts == {"north": 0, "south": 0, "east": 0, "west": 0}
    assert obs.queue_lengths == {"north": 0, "south": 0, "east": 0, "west": 0}

    # All 4 vehicle classes must be present with default 0
    assert obs.class_counts == {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}

    # Safe defaults for other fields
    assert obs.detections == ()
    assert obs.tracking_available is False
    assert obs.tracked_vehicle_count == 0
    assert obs.average_confidence == 0.0


def test_missing_approach_keys_auto_filled():
    obs = TrafficObservation(
        timestamp=10.0,
        source="synthetic",
        intersection_id="J3",
        vehicle_count=5,
        approach_counts={"north": 3, "east": 2},
        queue_lengths={"north": 2},
    )

    assert set(obs.approach_counts.keys()) == set(VALID_APPROACHES)
    assert obs.approach_counts["north"] == 3
    assert obs.approach_counts["east"] == 2
    assert obs.approach_counts["south"] == 0
    assert obs.approach_counts["west"] == 0

    assert set(obs.queue_lengths.keys()) == set(VALID_APPROACHES)
    assert obs.queue_lengths["north"] == 2
    assert obs.queue_lengths["south"] == 0
    assert obs.queue_lengths["east"] == 0
    assert obs.queue_lengths["west"] == 0


def test_missing_class_keys_auto_filled():
    obs = TrafficObservation(
        timestamp=10.0,
        source="synthetic",
        intersection_id="J1",
        vehicle_count=4,
        class_counts={"bus": 1, "car": 3},
    )

    assert set(obs.class_counts.keys()) == set(VALID_VEHICLE_CLASSES)
    assert obs.class_counts["bus"] == 1
    assert obs.class_counts["car"] == 3
    assert obs.class_counts["motorcycle"] == 0
    assert obs.class_counts["truck"] == 0


def test_invalid_values_validation():
    # Empty intersection_id
    with pytest.raises(ValueError, match="intersection_id"):
        TrafficObservation(timestamp=1.0, source="test", intersection_id="   ", vehicle_count=0)

    # Empty source
    with pytest.raises(ValueError, match="source"):
        TrafficObservation(timestamp=1.0, source="", intersection_id="J1", vehicle_count=0)

    # Negative timestamp
    with pytest.raises(ValueError, match="timestamp"):
        TrafficObservation(timestamp=-5.0, source="test", intersection_id="J1", vehicle_count=0)

    # Negative vehicle_count
    with pytest.raises(ValueError, match="vehicle_count"):
        TrafficObservation(timestamp=1.0, source="test", intersection_id="J1", vehicle_count=-1)

    # Negative tracked_vehicle_count
    with pytest.raises(ValueError, match="tracked_vehicle_count"):
        TrafficObservation(timestamp=1.0, source="test", intersection_id="J1", vehicle_count=0, tracked_vehicle_count=-2)

    # Out of range average_confidence
    with pytest.raises(ValueError, match="average_confidence"):
        TrafficObservation(timestamp=1.0, source="test", intersection_id="J1", vehicle_count=0, average_confidence=1.5)

    # Negative count in approach_counts
    with pytest.raises(ValueError, match="approach_counts"):
        TrafficObservation(
            timestamp=1.0,
            source="test",
            intersection_id="J1",
            vehicle_count=0,
            approach_counts={"north": -1},
        )

    # Negative count in queue_lengths
    with pytest.raises(ValueError, match="queue_lengths"):
        TrafficObservation(
            timestamp=1.0,
            source="test",
            intersection_id="J1",
            vehicle_count=0,
            queue_lengths={"south": -3},
        )

    # Negative count in class_counts
    with pytest.raises(ValueError, match="class_counts"):
        TrafficObservation(
            timestamp=1.0,
            source="test",
            intersection_id="J1",
            vehicle_count=0,
            class_counts={"car": -2},
        )

    # Invalid vehicle class in detection
    with pytest.raises(ValueError, match="Invalid vehicle class"):
        VehicleDetection("bicycle", 0.9, (0, 0, 10, 10), (5, 5))


def test_json_serialization_deserialization():
    detection = VehicleDetection("truck", 0.88, (10, 20, 60, 80), (35, 50), track_id=42)
    obs = TrafficObservation(
        timestamp=123.456,
        source="sensor_gateway",
        intersection_id="J_MAIN",
        vehicle_count=3,
        approach_counts={"north": 1, "south": 0, "east": 2, "west": 0},
        queue_lengths={"north": 1, "south": 0, "east": 1, "west": 0},
        class_counts={"car": 2, "motorcycle": 0, "bus": 0, "truck": 1},
        detections=(detection,),
        tracking_available=True,
        tracked_vehicle_count=1,
        average_confidence=0.88,
    )

    # To dict & to JSON
    d = obs.to_dict()
    json_str = obs.to_json(indent=2)
    assert isinstance(json_str, str)

    # Round trip from dict
    from_d = TrafficObservation.from_dict(d)
    assert from_d == obs

    # Round trip from JSON
    from_j = TrafficObservation.from_json(json_str)
    assert from_j == obs
    assert len(from_j.detections) == 1
    assert from_j.detections[0].class_name == "truck"
    assert from_j.detections[0].track_id == 42


def test_yolo_observation_to_intersection_traffic_state():
    obs = TrafficObservation(
        timestamp=200.0,
        source="yolov8",
        intersection_id="J1",
        vehicle_count=8,
        approach_counts={"north": 4, "south": 2, "east": 1, "west": 1},
        queue_lengths={"north": 3, "south": 2, "east": 1, "west": 0},
        class_counts={"car": 6, "motorcycle": 1, "bus": 1, "truck": 0},
    )

    state = obs.to_intersection_traffic_state(road_capacity=80)
    assert isinstance(state, IntersectionTrafficState)
    assert state.intersection_id == "J1"
    assert state.vehicle_count == 8
    # Phase 0 queue = north (3) + south (2) = 5
    # Phase 2 queue = east (1) + west (0) = 1
    assert state.green_phase_queues == ((0, 5), (2, 1))
    assert state.queue_length == 6
    assert state.traffic_density == round(8 / 80, 4)
    assert state.road_capacity == 80

    # Ensure canonical QUBO exact solver processes this state
    config = load_config()
    model = build_qubo(state, config["optimization"]["phase3a"])
    sol = solve_exact(model)
    assert sol.candidate.valid is True
    assert sol.candidate.first_green_seconds in (22, 30, 40)
    assert sol.candidate.second_green_seconds in (22, 30, 40)


def test_sumo_observation_to_canonical_contract():
    # Simulation generates IntersectionTrafficState
    sim_state = IntersectionTrafficState(
        intersection_id="J2",
        vehicle_count=14,
        queue_length=9,
        traffic_density=0.14,
        road_capacity=100,
        signal_state=SignalState.GREEN,
        signal_phase=0,
        green_phase_queues=((0, 6), (2, 3)),
    )

    # Convert to canonical TrafficObservation
    obs = TrafficObservation.from_intersection_traffic_state(sim_state, source="sumo")
    assert obs.source == "sumo"
    assert obs.intersection_id == "J2"
    assert obs.vehicle_count == 14

    # Verify queues map to approaches and sum correctly
    p0_q = obs.queue_lengths["north"] + obs.queue_lengths["south"]
    p2_q = obs.queue_lengths["east"] + obs.queue_lengths["west"]
    assert p0_q == 6
    assert p2_q == 3

    # All 4 approaches and vehicle classes present
    assert set(obs.approach_counts.keys()) == set(VALID_APPROACHES)
    assert set(obs.class_counts.keys()) == set(VALID_VEHICLE_CLASSES)
    assert sum(obs.approach_counts.values()) == 14

    # Roundtrip back to IntersectionTrafficState
    roundtrip = obs.to_intersection_traffic_state(road_capacity=100)
    assert roundtrip.intersection_id == "J2"
    assert roundtrip.green_phase_queues == ((0, 6), (2, 3))
    assert roundtrip.vehicle_count == 14
    assert roundtrip.queue_length == 9


def test_canonical_state_to_optimization_api():
    app = create_app()
    client = app.test_client()

    obs = TrafficObservation(
        timestamp=300.0,
        source="yolov8",
        intersection_id="J3",
        vehicle_count=10,
        approach_counts={"north": 3, "south": 3, "east": 2, "west": 2},
        queue_lengths={"north": 3, "south": 2, "east": 1, "west": 1},
        class_counts={"car": 8, "motorcycle": 1, "bus": 0, "truck": 1},
    )

    # 1. Post TrafficObservation dict directly to /api/optimize
    resp = client.post("/api/optimize", json=obs.to_dict())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["intersection_id"] == "J3"
    assert data["valid"] is True
    assert "phase_0_green_seconds" in data
    assert "phase_2_green_seconds" in data

    # 2. Post minimal canonical state without perception-specific fields
    minimal = {
        "intersection_id": "J3",
        "queue_lengths": {"north": 3, "south": 2, "east": 1, "west": 1},
    }
    resp_min = client.post("/api/optimize", json=minimal)
    assert resp_min.status_code == 200
    min_data = resp_min.get_json()
    assert min_data["valid"] is True
    assert min_data["phase_0_green_seconds"] == data["phase_0_green_seconds"]


def test_backward_compatibility_phases_a_to_f():
    # 1. Snake-case API payload
    state1, solver1 = parse_state_data({
        "intersection_id": "J1",
        "phase_0_queue": 8,
        "phase_2_queue": 3,
        "vehicle_count": 11,
    })
    assert state1.intersection_id == "J1"
    assert state1.green_phase_queues == ((0, 8), (2, 3))
    assert solver1 == "exact"

    # 2. Browser camelCase simulation payload
    state2, solver2 = parse_state_data({
        "intersectionId": "J2",
        "nsQueue": 5,
        "ewQueue": 2,
        "vehicleCount": 7,
    })
    assert state2.intersection_id == "J2"
    assert state2.green_phase_queues == ((0, 5), (2, 2))
    assert solver2 == "exact"

    # 3. IntersectionTrafficState green_phase_queues payload
    state3, _ = parse_state_data({
        "intersection_id": "J3",
        "green_phase_queues": [[0, 10], [2, 4]],
    })
    assert state3.green_phase_queues == ((0, 10), (2, 4))
