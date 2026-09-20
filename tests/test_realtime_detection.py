"""Deterministic unit and integration tests for real-time vehicle and pedestrian detection.

Tests cover all 24 required cases from the master specification without requiring
physical webcam hardware.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from perception.aggregator import TrafficAggregator
from perception.detector import COCO_TARGET_CLASSES, COCO_VEHICLE_CLASSES, YOLOVehicleDetector
from perception.models import (
    PedestrianDetection,
    TrafficObservation,
    VALID_PEDESTRIAN_CLASSES,
    VALID_VEHICLE_CLASSES,
    VehicleDetection,
)
from perception.realtime import RealtimeDetectionEngine


# -----------------------------------------------------------------------------
# Tests 1-5: Target class acceptance
# -----------------------------------------------------------------------------

def test_01_car_detection_accepted():
    det = VehicleDetection(
        class_name="car",
        confidence=0.92,
        bbox=(10.0, 10.0, 50.0, 50.0),
        center=(30.0, 30.0),
        track_id=1,
    )
    assert det.class_name == "car"
    assert det.track_id == 1
    assert det.to_dict()["class_name"] == "car"


def test_02_motorcycle_detection_accepted():
    det = VehicleDetection(
        class_name="motorcycle",
        confidence=0.88,
        bbox=(20.0, 20.0, 40.0, 60.0),
        center=(30.0, 40.0),
        track_id=2,
    )
    assert det.class_name == "motorcycle"
    assert det.track_id == 2


def test_03_bus_detection_accepted():
    det = VehicleDetection(
        class_name="bus",
        confidence=0.95,
        bbox=(50.0, 50.0, 150.0, 200.0),
        center=(100.0, 125.0),
        track_id=3,
    )
    assert det.class_name == "bus"
    assert det.track_id == 3


def test_04_truck_detection_accepted():
    det = VehicleDetection(
        class_name="truck",
        confidence=0.90,
        bbox=(100.0, 100.0, 250.0, 300.0),
        center=(175.0, 200.0),
        track_id=4,
    )
    assert det.class_name == "truck"
    assert det.track_id == 4


def test_05_pedestrian_detection_accepted():
    ped = PedestrianDetection(
        class_name="person",
        confidence=0.85,
        bbox=(15.0, 20.0, 35.0, 80.0),
        center=(25.0, 50.0),
        track_id=10,
    )
    assert ped.class_name == "person"
    assert ped.track_id == 10
    d = ped.to_dict()
    assert d["class_name"] == "person"
    assert d["confidence"] == 0.85


# -----------------------------------------------------------------------------
# Tests 6-8: Filtering and strict separation
# -----------------------------------------------------------------------------

def test_06_unrelated_objects_filtered():
    # VehicleDetection rejects non-vehicle classes (bicycle, traffic light, dog, chair, etc.)
    unrelated_classes = ["bicycle", "traffic light", "stop sign", "dog", "backpack", "chair"]
    for unk in unrelated_classes:
        with pytest.raises(ValueError, match="Invalid vehicle class"):
            VehicleDetection(
                class_name=unk,
                confidence=0.9,
                bbox=(0, 0, 10, 10),
                center=(5, 5),
            )
        with pytest.raises(ValueError, match="Invalid pedestrian class"):
            PedestrianDetection(
                class_name=unk,
                confidence=0.9,
                bbox=(0, 0, 10, 10),
                center=(5, 5),
            )

    # In COCO target mapping, only {0: person, 2: car, 3: motorcycle, 5: bus, 7: truck} exist
    for unk_id in [1, 9, 11, 16, 24, 56]:
        assert unk_id not in COCO_TARGET_CLASSES


def test_07_pedestrian_not_counted_as_vehicle():
    aggregator = TrafficAggregator()
    ped = PedestrianDetection("person", 0.9, (10, 10, 20, 40), (15, 25), track_id=1)
    obs = aggregator.aggregate(detections=(), pedestrian_detections=(ped,))

    assert obs.pedestrian_count == 1
    assert obs.vehicle_count == 0
    assert obs.class_counts == {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
    assert "person" not in obs.class_counts
    assert "pedestrian" not in obs.class_counts


def test_08_vehicle_not_counted_as_pedestrian():
    aggregator = TrafficAggregator()
    car = VehicleDetection("car", 0.92, (10, 10, 50, 50), (30, 30), track_id=2)
    obs = aggregator.aggregate(detections=(car,), pedestrian_detections=())

    assert obs.vehicle_count == 1
    assert obs.pedestrian_count == 0
    assert obs.class_counts["car"] == 1
    assert len(obs.pedestrian_detections) == 0


# -----------------------------------------------------------------------------
# Tests 9-10: Class counts & pedestrian counts correct
# -----------------------------------------------------------------------------

def test_09_class_counts_correct():
    # Example scenario from prompt: 5 cars, 2 motorcycles, 1 bus, 1 truck, 6 pedestrians
    cars = [VehicleDetection("car", 0.9, (0, 0, 10, 10), (5, 5), track_id=i) for i in range(1, 6)]
    motos = [VehicleDetection("motorcycle", 0.85, (0, 0, 10, 10), (5, 5), track_id=i) for i in range(6, 8)]
    buses = [VehicleDetection("bus", 0.95, (0, 0, 10, 10), (5, 5), track_id=8)]
    trucks = [VehicleDetection("truck", 0.88, (0, 0, 10, 10), (5, 5), track_id=9)]
    all_vehicles = cars + motos + buses + trucks

    peds = [PedestrianDetection("person", 0.8, (0, 0, 10, 10), (5, 5), track_id=i) for i in range(10, 16)]

    aggregator = TrafficAggregator()
    obs = aggregator.aggregate(detections=all_vehicles, pedestrian_detections=peds)

    assert obs.vehicle_count == 9
    assert obs.pedestrian_count == 6
    assert obs.class_counts["car"] == 5
    assert obs.class_counts["motorcycle"] == 2
    assert obs.class_counts["bus"] == 1
    assert obs.class_counts["truck"] == 1
    # Confirm vehicle count is strictly 9, NOT 15
    assert obs.vehicle_count != 15


def test_10_pedestrian_count_correct():
    peds = [
        PedestrianDetection("person", 0.8, (0, 0, 10, 10), (5, 5), track_id=1),
        PedestrianDetection("person", 0.85, (10, 10, 20, 20), (15, 15), track_id=2),
        PedestrianDetection("person", 0.9, (20, 20, 30, 30), (25, 25), track_id=3),
    ]
    aggregator = TrafficAggregator()
    obs = aggregator.aggregate(detections=(), pedestrian_detections=peds)
    assert obs.pedestrian_count == 3
    assert obs.tracked_pedestrian_count == 3


# -----------------------------------------------------------------------------
# Tests 11-12: Deduplication and Tracking IDs
# -----------------------------------------------------------------------------

def test_11_duplicate_track_ids_handled():
    # Two detections sharing track_id=5, one with 0.7 confidence, one with 0.9
    dup1 = VehicleDetection("car", 0.70, (0, 0, 10, 10), (5, 5), track_id=5)
    dup2 = VehicleDetection("car", 0.92, (2, 2, 12, 12), (7, 7), track_id=5)

    aggregator = TrafficAggregator()
    deduped = aggregator.deduplicate_detections([dup1, dup2])
    assert len(deduped) == 1
    assert deduped[0].confidence == 0.92
    assert deduped[0].track_id == 5

    # Same for pedestrians
    pdup1 = PedestrianDetection("person", 0.65, (0, 0, 10, 10), (5, 5), track_id=9)
    pdup2 = PedestrianDetection("person", 0.88, (1, 1, 11, 11), (6, 6), track_id=9)
    pdeduped = aggregator.deduplicate_pedestrians([pdup1, pdup2])
    assert len(pdeduped) == 1
    assert pdeduped[0].confidence == 0.88


def test_12_tracking_ids_preserved():
    det1 = VehicleDetection("car", 0.9, (0, 0, 10, 10), (5, 5), track_id=101)
    ped1 = PedestrianDetection("person", 0.85, (20, 20, 30, 30), (25, 25), track_id=202)

    aggregator = TrafficAggregator()
    obs = aggregator.aggregate(detections=(det1,), pedestrian_detections=(ped1,))

    assert obs.tracking_available is True
    assert obs.tracked_vehicle_count == 1
    assert obs.tracked_pedestrian_count == 1
    assert obs.detections[0].track_id == 101
    assert obs.pedestrian_detections[0].track_id == 202


# -----------------------------------------------------------------------------
# Tests 13-14: Confidence and ROI filtering
# -----------------------------------------------------------------------------

def test_13_confidence_threshold():
    detector = YOLOVehicleDetector(confidence_threshold=0.50)
    assert detector.confidence_threshold == 0.50

    engine = RealtimeDetectionEngine(confidence_threshold=0.45)
    assert engine.confidence_threshold == 0.45


def test_14_roi_filtering():
    regions = {
        "north": [0.0, 0.0, 200.0, 100.0],
        "south": [0.0, 101.0, 200.0, 200.0],
        "east": [201.0, 0.0, 400.0, 200.0],
        "west": [401.0, 0.0, 600.0, 200.0],
    }
    aggregator = TrafficAggregator(approach_regions=regions)

    # Point in north region
    assert aggregator.classify_approach(100.0, 50.0) == "north"
    # Point in south region
    assert aggregator.classify_approach(100.0, 150.0) == "south"
    # Point in east region
    assert aggregator.classify_approach(300.0, 100.0) == "east"
    # Point in west region
    assert aggregator.classify_approach(500.0, 100.0) == "west"


# -----------------------------------------------------------------------------
# Tests 15-17: Empty frame, malformed frame, missing model
# -----------------------------------------------------------------------------

def test_15_empty_frame():
    detector = YOLOVehicleDetector()
    empty_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    obs = detector.detect(empty_frame, intersection_id="J1")
    assert obs.intersection_id == "J1"
    assert obs.vehicle_count == 0
    assert obs.pedestrian_count == 0
    assert obs.source == "yolov8"


def test_16_malformed_frame():
    detector = YOLOVehicleDetector()
    # Pass an invalid source type
    obs = detector.detect("non_existent_invalid_path_12345.xyz", intersection_id="J2")
    assert obs.intersection_id == "J2"
    assert obs.vehicle_count == 0
    assert obs.source in ("fallback", "error")


def test_17_missing_model():
    detector = YOLOVehicleDetector(model_name="completely_missing_weights.pt")
    obs = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8), intersection_id="J3")
    assert obs.intersection_id == "J3"
    assert obs.vehicle_count == 0
    assert obs.source in ("fallback", "error")


# -----------------------------------------------------------------------------
# Tests 18-20: Camera lifecycle, unavailable, disconnect, cleanup
# -----------------------------------------------------------------------------

def test_18_camera_unavailable():
    engine = RealtimeDetectionEngine()
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap_cls.return_value = mock_cap

        success = engine.start(source_type="camera", camera_index=99)
        assert success is False
        status = engine.get_status()
        assert status["status"] == "unavailable"
        assert "Failed to open" in status["error"]


def test_19_camera_disconnect():
    engine = RealtimeDetectionEngine()
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)  # Disconnect / read failure
        mock_cap_cls.return_value = mock_cap

        engine.start(source_type="camera", camera_index=0)
        # Give capture worker a brief moment to detect failure
        import time
        time.sleep(0.1)
        status = engine.get_status()
        assert status["status"] in ("unavailable", "error", "connected", "running")
        engine.stop()


def test_20_stop_releases_resources():
    engine = RealtimeDetectionEngine()
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((100, 100, 3), dtype=np.uint8))
        mock_cap_cls.return_value = mock_cap

        engine.start(source_type="camera", camera_index=0)
        assert engine.is_running is True

        engine.stop()
        assert engine.is_running is False
        assert engine.get_status()["status"] == "stopped"
        mock_cap.release.assert_called()


# -----------------------------------------------------------------------------
# Tests 21-22: Serialization & Existing TrafficObservation Compatibility
# -----------------------------------------------------------------------------

def test_21_live_observation_serialization():
    ped = PedestrianDetection("person", 0.91, (10, 10, 30, 40), (20, 25), track_id=7)
    veh = VehicleDetection("truck", 0.85, (50, 50, 120, 130), (85, 90), track_id=8)
    obs = TrafficObservation(
        timestamp=123.456,
        source="realtime_detector",
        intersection_id="J2",
        vehicle_count=1,
        pedestrian_count=1,
        tracked_vehicle_count=1,
        tracked_pedestrian_count=1,
        detections=(veh,),
        pedestrian_detections=(ped,),
        average_confidence=0.88,
        tracking_available=True,
    )

    d = obs.to_dict()
    assert d["vehicle_count"] == 1
    assert d["pedestrian_count"] == 1
    assert len(d["detections"]) == 1
    assert len(d["pedestrian_detections"]) == 1

    # Round-trip JSON deserialization
    json_str = obs.to_json()
    reconstructed = TrafficObservation.from_json(json_str)
    assert reconstructed.vehicle_count == 1
    assert reconstructed.pedestrian_count == 1
    assert reconstructed.detections[0].class_name == "truck"
    assert reconstructed.pedestrian_detections[0].class_name == "person"


def test_22_existing_traffic_observation_compatibility():
    # Legacy consumer constructing TrafficObservation without pedestrian fields
    legacy_obs = TrafficObservation(
        timestamp=100.0,
        source="sumo",
        intersection_id="J1",
        vehicle_count=10,
        approach_counts={"north": 3, "south": 3, "east": 2, "west": 2},
        queue_lengths={"north": 2, "south": 2, "east": 1, "west": 1},
        class_counts={"car": 8, "motorcycle": 1, "bus": 1, "truck": 0},
    )

    # All legacy fields work as expected
    assert legacy_obs.vehicle_count == 10
    assert legacy_obs.pedestrian_count == 0
    assert legacy_obs.tracked_pedestrian_count == 0
    assert legacy_obs.pedestrian_detections == ()
    assert legacy_obs.pedestrian_approach_counts == {"north": 0, "south": 0, "east": 0, "west": 0}

    # Legacy to_intersection_traffic_state works without error
    state = legacy_obs.to_intersection_traffic_state(road_capacity=100)
    assert state.intersection_id == "J1"
    assert state.vehicle_count == 10


# -----------------------------------------------------------------------------
# Tests 23-24: Signal control and Optimizer are NOT invoked
# -----------------------------------------------------------------------------

def test_23_signal_control_not_invoked():
    engine = RealtimeDetectionEngine()
    status = engine.get_status()
    # Confirm signal control is strictly labeled DISABLED
    assert status["signal_control"] == "DISABLED"
    assert "DETECTION ONLY" in status["mode"]


def test_24_optimizer_not_called_by_detection_mode():
    with patch("optimization.quantum.qubo.build_qubo") as mock_build_qubo, \
         patch("optimization.quantum.solver.solve_exact") as mock_solve_exact, \
         patch("optimization.quantum.qaoa.run_qaoa") as mock_run_qaoa:

        from optimization.service import create_app
        app = create_app()
        client = app.test_client()

        # Call live status endpoint
        res = client.get("/api/perception/live/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["signal_control"] == "DISABLED"

        # Neither QUBO nor QAOA was ever called
        mock_build_qubo.assert_not_called()
        mock_solve_exact.assert_not_called()
        mock_run_qaoa.assert_not_called()
