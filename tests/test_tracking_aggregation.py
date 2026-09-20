"""Unit tests for tracking, traffic aggregation, approach ROI classification, and deduplication."""

import pytest

from config.loader import load_config
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.aggregator import TrafficAggregator, point_in_polygon
from perception.models import TrafficObservation, VehicleDetection


def test_point_in_polygon():
    # Square polygon: (0,0) -> (10,0) -> (10,10) -> (0,10)
    square = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))
    assert point_in_polygon(5.0, 5.0, square) is True
    assert point_in_polygon(15.0, 5.0, square) is False
    assert point_in_polygon(-1.0, -1.0, square) is False


def test_configurable_approach_roi_validation():
    # Valid box and polygon ROIs
    valid_rois = {
        "north": [0, 0, 100, 50],
        "south": [(0, 60), (100, 60), (100, 120), (0, 120)],
    }
    agg = TrafficAggregator(approach_regions=valid_rois)
    assert "north" in agg.approach_regions
    assert "south" in agg.approach_regions

    # Invalid ROI: x1 > x2
    with pytest.raises(ValueError, match="requires x1<=x2"):
        TrafficAggregator(approach_regions={"north": [100, 0, 50, 50]})

    # Invalid ROI: less than 3 points for polygon
    with pytest.raises(ValueError, match="either a 4-element bounding box"):
        TrafficAggregator(approach_regions={"east": [(0, 0), (10, 10)]})

    # Invalid ROI: non-numeric
    with pytest.raises(ValueError):
        TrafficAggregator(approach_regions={"west": ["a", "b", "c", "d"]})


def test_approach_classification_box_and_polygon():
    rois = {
        "north": [100.0, 0.0, 300.0, 200.0],
        "south": [100.0, 300.0, 300.0, 500.0],
        "east": [(350.0, 150.0), (500.0, 150.0), (500.0, 350.0), (350.0, 350.0)],
    }
    agg = TrafficAggregator(approach_regions=rois)

    # Box matches
    assert agg.classify_approach(200.0, 100.0) == "north"
    assert agg.classify_approach(200.0, 400.0) == "south"
    # Polygon match
    assert agg.classify_approach(400.0, 250.0) == "east"


def test_traffic_aggregation_counts_and_metrics():
    rois = {
        "north": [0.0, 0.0, 200.0, 200.0],
        "south": [0.0, 300.0, 200.0, 500.0],
    }
    agg = TrafficAggregator(approach_regions=rois)

    detections = [
        VehicleDetection("car", 0.90, (10, 10, 40, 40), (25, 25), track_id=101),
        VehicleDetection("car", 0.80, (20, 20, 50, 50), (35, 35), track_id=102),
        VehicleDetection("motorcycle", 0.70, (10, 320, 30, 350), (20, 335), track_id=103),
        VehicleDetection("bus", 0.95, (40, 330, 80, 400), (60, 365), track_id=None),  # untracked
        VehicleDetection("truck", 0.85, (50, 350, 90, 420), (70, 385), track_id=104),
    ]

    obs = agg.aggregate(detections, intersection_id="J1")

    assert obs.intersection_id == "J1"
    assert obs.vehicle_count == 5
    assert obs.tracked_vehicle_count == 4
    assert obs.tracking_available is True
    # Average confidence: (0.90 + 0.80 + 0.70 + 0.95 + 0.85) / 5 = 4.2 / 5 = 0.84
    assert obs.average_confidence == 0.84

    # Class counts
    assert obs.class_counts["car"] == 2
    assert obs.class_counts["motorcycle"] == 1
    assert obs.class_counts["bus"] == 1
    assert obs.class_counts["truck"] == 1

    # Approach counts: 2 north, 3 south
    assert obs.approach_counts["north"] == 2
    assert obs.approach_counts["south"] == 3


def test_duplicate_track_id_deduplication():
    agg = TrafficAggregator()

    # Two detections sharing track_id=42, one with higher confidence
    detections = [
        VehicleDetection("car", 0.65, (10, 10, 50, 50), (30, 30), track_id=42),
        VehicleDetection("car", 0.92, (12, 12, 52, 52), (32, 32), track_id=42),
        VehicleDetection("truck", 0.88, (100, 100, 150, 150), (125, 125), track_id=43),
    ]

    obs = agg.aggregate(detections, intersection_id="J1")

    # Should count track_id 42 only once, keeping the higher confidence (0.92)
    assert obs.vehicle_count == 2
    assert obs.tracked_vehicle_count == 2
    assert len(obs.detections) == 2
    # Ensure the retained track 42 has confidence 0.92
    track_42 = [d for d in obs.detections if d.track_id == 42][0]
    assert track_42.confidence == 0.92


def test_empty_detections_aggregation():
    agg = TrafficAggregator()
    obs = agg.aggregate([], intersection_id="J1")
    assert obs.vehicle_count == 0
    assert obs.tracked_vehicle_count == 0
    assert obs.average_confidence == 0.0
    assert obs.tracking_available is False
    assert all(c == 0 for c in obs.class_counts.values())
    assert all(c == 0 for c in obs.approach_counts.values())


def test_observation_compatibility_with_optimization_backend():
    config = load_config()
    agg = TrafficAggregator(approach_regions={
        "north": [0, 0, 100, 100],
        "south": [0, 101, 100, 200],
        "east": [101, 0, 200, 100],
        "west": [101, 101, 200, 200],
    })

    # 18 North, 12 South (Phase 0 total = 30)
    # 4 East, 3 West (Phase 2 total = 7)
    detections = []
    tid = 1
    for _ in range(18):
        detections.append(VehicleDetection("car", 0.9, (10, 10, 50, 50), (20, 20), track_id=tid))
        tid += 1
    for _ in range(12):
        detections.append(VehicleDetection("car", 0.85, (10, 110, 50, 150), (20, 120), track_id=tid))
        tid += 1
    for _ in range(4):
        detections.append(VehicleDetection("bus", 0.9, (110, 10, 150, 50), (120, 20), track_id=tid))
        tid += 1
    for _ in range(3):
        detections.append(VehicleDetection("truck", 0.88, (110, 110, 150, 150), (120, 120), track_id=tid))
        tid += 1

    obs = agg.aggregate(detections, intersection_id="J1")
    assert obs.vehicle_count == 37
    assert obs.approach_counts == {"north": 18, "south": 12, "east": 4, "west": 3}
    assert obs.class_counts == {"car": 30, "motorcycle": 0, "bus": 4, "truck": 3}
    assert obs.tracked_vehicle_count == 37

    # Convert to canonical IntersectionTrafficState
    state = obs.to_intersection_traffic_state(road_capacity=100)
    assert state.intersection_id == "J1"
    assert state.vehicle_count == 37
    assert state.green_phase_queues == ((0, 30), (2, 7))

    # Feed into canonical QUBO and exact solver
    model = build_qubo(state, config["optimization"]["phase3a"])
    solution = solve_exact(model)
    assert solution.candidate.valid is True
    # Phase 0 had 30 vs Phase 2 had 7, so phase 0 gets 40s green and phase 2 gets 22s green
    assert solution.candidate.first_green_seconds == 40
    assert solution.candidate.second_green_seconds == 22
