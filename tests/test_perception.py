"""Unit tests for perception models, YOLO detection schemas, and observation conversion."""

from time import time
import pytest

from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from config.loader import load_config
from perception.detector import YOLOVehicleDetector
from perception.models import TrafficObservation, VehicleDetection


def test_vehicle_detection_validation():
    # Valid detection
    det = VehicleDetection(
        class_name="car",
        confidence=0.92,
        bbox=(100.0, 150.0, 200.0, 280.0),
        center=(150.0, 215.0),
        track_id=12,
    )
    assert det.class_name == "car"
    assert det.track_id == 12

    # Serialization
    d = det.to_dict()
    assert d["class_name"] == "car"
    assert d["confidence"] == 0.92
    assert d["track_id"] == 12

    # Invalid class rejection
    with pytest.raises(ValueError, match="Invalid vehicle class"):
        VehicleDetection(class_name="airplane", confidence=0.8, bbox=(0, 0, 10, 10), center=(5, 5))

    # Invalid confidence
    with pytest.raises(ValueError, match="Confidence"):
        VehicleDetection(class_name="bus", confidence=1.5, bbox=(0, 0, 10, 10), center=(5, 5))


def test_traffic_observation_and_qubo_conversion():
    config = load_config()
    obs = TrafficObservation(
        timestamp=time(),
        source="yolov8",
        intersection_id="J1",
        vehicle_count=24,
        approach_counts={"north": 12, "south": 8, "east": 3, "west": 1},
        queue_lengths={"north": 12, "south": 8, "east": 3, "west": 1},
        class_counts={"car": 20, "motorcycle": 2, "bus": 1, "truck": 1},
        detections=(
            VehicleDetection("car", 0.9, (10, 10, 50, 50), (30, 30), 1),
            VehicleDetection("bus", 0.85, (60, 60, 120, 140), (90, 100), 2),
        ),
        tracking_available=True,
    )

    # Convert observation to canonical IntersectionTrafficState
    state = obs.to_intersection_traffic_state(road_capacity=100)
    assert state.intersection_id == "J1"
    assert state.vehicle_count == 24
    # Phase 0 = North (12) + South (8) = 20
    # Phase 2 = East (3) + West (1) = 4
    assert state.green_phase_queues == ((0, 20), (2, 4))
    assert state.queue_length == 24
    assert state.traffic_density == 0.24

    # Directly feed into canonical QUBO and exact solver
    model = build_qubo(state, config["optimization"]["phase3a"])
    solution = solve_exact(model)
    assert solution.candidate.valid is True
    # North-South had 20 vs East-West 4, so candidate duration should be optimal (40s vs 22s)
    assert solution.candidate.first_green_seconds == 40
    assert solution.candidate.second_green_seconds == 22


def test_yolo_detector_approach_classification():
    custom_regions = {
        "north": [0, 0, 500, 250],
        "south": [0, 251, 500, 500],
        "east": [501, 0, 1000, 500],
    }
    detector = YOLOVehicleDetector(approach_regions=custom_regions)

    # In north region
    assert detector._classify_approach(250, 100) == "north"
    # In south region
    assert detector._classify_approach(250, 350) == "south"
    # In east region
    assert detector._classify_approach(700, 200) == "east"


def test_yolo_detector_fallback_observation():
    detector = YOLOVehicleDetector(model_name="non_existent_weights.pt")
    obs = detector.detect("dummy_path.jpg", intersection_id="J2")
    assert obs.intersection_id == "J2"
    assert obs.vehicle_count == 0
    assert obs.source in ("fallback", "error")


def test_yolo_detector_live_inference():
    import numpy as np
    detector = YOLOVehicleDetector(model_name="yolov8n.pt")
    frame = np.zeros((320, 320, 3), dtype=np.uint8)
    obs = detector.detect(frame, intersection_id="J1")
    assert obs.intersection_id == "J1"
    assert obs.source == "yolov8"
    assert isinstance(obs.detections, tuple)
    assert isinstance(obs.class_counts, dict)
    assert set(obs.class_counts.keys()) == {"car", "motorcycle", "bus", "truck"}
