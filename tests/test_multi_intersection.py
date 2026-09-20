"""Unit and integration tests for MultiIntersectionController and multi-junction API."""

import pytest

from config.loader import load_config
from optimization.service import create_app
from perception.models import TrafficObservation
from simulation.signals.multi_intersection import MultiIntersectionController


def make_obs(
    intersection_id: str,
    north_q: int = 0,
    south_q: int = 0,
    east_q: int = 0,
    west_q: int = 0,
    timestamp: float = 100.0,
) -> TrafficObservation:
    total_q = north_q + south_q + east_q + west_q
    return TrafficObservation(
        timestamp=timestamp,
        source="yolov8",
        intersection_id=intersection_id,
        vehicle_count=total_q + 2,
        approach_counts={
            "north": north_q + 1,
            "south": south_q,
            "east": east_q + 1,
            "west": west_q,
        },
        queue_lengths={
            "north": north_q,
            "south": south_q,
            "east": east_q,
            "west": west_q,
        },
        class_counts={"car": total_q + 2, "motorcycle": 0, "bus": 0, "truck": 0},
    )


def test_four_intersections_independent_optimization():
    controller = MultiIntersectionController(anti_oscillation_damping_seconds=0.0)

    # 4 intersections with distinctly different demand profiles:
    # J1: Heavy North/South queue (15 + 10 = 25 vs 1 + 1 = 2) -> Favor Phase 0
    # J2: Heavy East/West queue (1 + 1 = 2 vs 16 + 12 = 28) -> Favor Phase 2
    # J3: Balanced demand (3 + 3 = 6 vs 3 + 3 = 6) -> Equal 30s/30s
    # J4: Moderate North/South queue (8 + 4 = 12 vs 2 + 1 = 3) -> Favor Phase 0
    obs_list = [
        make_obs("J1", north_q=15, south_q=10, east_q=1, west_q=1),
        make_obs("J2", north_q=1, south_q=1, east_q=16, west_q=12),
        make_obs("J3", north_q=3, south_q=3, east_q=3, west_q=3),
        make_obs("J4", north_q=8, south_q=4, east_q=2, west_q=1),
    ]

    decisions = controller.optimize_observations(obs_list, current_time=100.0)
    assert len(decisions) == 4
    assert set(decisions.keys()) == {"J1", "J2", "J3", "J4"}

    # J1 should favor Phase 0 (North/South)
    assert decisions["J1"]["phase_0_green_seconds"] > decisions["J1"]["phase_2_green_seconds"]
    assert decisions["J1"]["phase_0_green_seconds"] == 40
    assert decisions["J1"]["phase_2_green_seconds"] == 22

    # J2 should favor Phase 2 (East/West)
    assert decisions["J2"]["phase_2_green_seconds"] > decisions["J2"]["phase_0_green_seconds"]
    assert decisions["J2"]["phase_0_green_seconds"] == 22
    assert decisions["J2"]["phase_2_green_seconds"] == 40

    # J3 balanced demand
    assert decisions["J3"]["phase_0_green_seconds"] == 30
    assert decisions["J3"]["phase_2_green_seconds"] == 30

    # J4 moderate NS bias
    assert decisions["J4"]["phase_0_green_seconds"] >= decisions["J4"]["phase_2_green_seconds"]

    # Verify persistent records maintained independently
    for iid in ("J1", "J2", "J3", "J4"):
        rec = controller.get_intersection_record(iid)
        assert rec is not None
        assert rec.intersection_id == iid
        assert rec.status == "optimized"
        assert rec.valid is True
        assert rec.phase_0_green_seconds in (22, 30, 40)
        assert rec.phase_2_green_seconds in (22, 30, 40)


def test_eight_intersections_scalability():
    controller = MultiIntersectionController(anti_oscillation_damping_seconds=0.0)
    obs_list = [
        make_obs(f"J{i}", north_q=i * 2, south_q=i, east_q=2, west_q=2)
        for i in range(1, 9)
    ]

    decisions = controller.optimize_observations(obs_list, current_time=100.0)
    assert len(decisions) == 8
    for i in range(1, 9):
        iid = f"J{i}"
        assert iid in decisions
        assert decisions[iid]["valid"] is True
        assert 22 <= decisions[iid]["phase_0_green_seconds"] <= 42
        assert 22 <= decisions[iid]["phase_2_green_seconds"] <= 42


def test_identical_states_reproducible_decisions():
    controller = MultiIntersectionController(anti_oscillation_damping_seconds=0.0)
    # J1 and J2 receive identical observation traffic patterns
    obs_list = [
        make_obs("J1", north_q=10, south_q=5, east_q=2, west_q=1),
        make_obs("J2", north_q=10, south_q=5, east_q=2, west_q=1),
    ]

    decisions = controller.optimize_observations(obs_list, current_time=100.0)
    assert decisions["J1"]["phase_0_green_seconds"] == decisions["J2"]["phase_0_green_seconds"]
    assert decisions["J1"]["phase_2_green_seconds"] == decisions["J2"]["phase_2_green_seconds"]
    assert decisions["J1"]["objective"] == decisions["J2"]["objective"]


def test_missing_intersection_state_handling():
    controller = MultiIntersectionController(
        managed_intersection_ids=["J1", "J2", "J3", "J4"],
        default_green_seconds=(30, 30),
    )

    # Only provide observations for J1 and J2; J3 and J4 are missing
    obs_list = [
        make_obs("J1", north_q=10, south_q=5, east_q=1, west_q=1),
        make_obs("J2", north_q=2, south_q=2, east_q=12, west_q=8),
    ]

    decisions = controller.optimize_observations(obs_list, current_time=100.0)
    assert len(decisions) == 4
    assert decisions["J1"]["status"] == "optimized"
    assert decisions["J2"]["status"] == "optimized"

    # Missing intersections receive safe fallback
    assert decisions["J3"]["status"] == "missing_fallback"
    assert decisions["J3"]["phase_0_green_seconds"] == 30
    assert decisions["J3"]["phase_2_green_seconds"] == 30
    assert decisions["J3"]["valid"] is True

    assert decisions["J4"]["status"] == "missing_fallback"
    assert decisions["J4"]["phase_0_green_seconds"] == 30
    assert decisions["J4"]["phase_2_green_seconds"] == 30
    assert decisions["J4"]["valid"] is True


def test_stale_observation_freshness_policy():
    controller = MultiIntersectionController(
        max_observation_age_seconds=15.0,
        default_green_seconds=(30, 30),
    )

    # Observation recorded at t=50.0. Current time is t=80.0 (age = 30.0s > 15.0s)
    stale_obs = make_obs("J1", north_q=20, south_q=15, timestamp=50.0)
    decisions = controller.optimize_observations([stale_obs], current_time=80.0)

    assert decisions["J1"]["status"] == "stale_fallback"
    assert decisions["J1"]["stale_age_seconds"] == 30.0
    assert decisions["J1"]["phase_0_green_seconds"] == 30
    assert decisions["J1"]["phase_2_green_seconds"] == 30
    assert decisions["J1"]["valid"] is True


def test_malformed_observation_handling():
    controller = MultiIntersectionController()
    with pytest.raises(ValueError):
        controller.optimize_observations(["not_a_valid_observation"])


def test_duplicate_intersection_id_resolution():
    controller = MultiIntersectionController(anti_oscillation_damping_seconds=0.0)

    # Two observations for J1 in the same batch with different timestamps
    old_obs = make_obs("J1", north_q=1, south_q=1, east_q=10, west_q=10, timestamp=90.0)
    new_obs = make_obs("J1", north_q=15, south_q=10, east_q=1, west_q=1, timestamp=100.0)

    decisions = controller.optimize_observations([old_obs, new_obs], current_time=100.0)
    assert len(decisions) == 1
    # New observation has high NS queue -> Phase 0 = 40s
    assert decisions["J1"]["phase_0_green_seconds"] == 40
    assert decisions["J1"]["phase_2_green_seconds"] == 22


def test_qaoa_batch_processing():
    controller = MultiIntersectionController(default_solver="qaoa", anti_oscillation_damping_seconds=0.0)
    obs_list = [
        make_obs("J1", north_q=10, south_q=6, east_q=2, west_q=2),
        make_obs("J2", north_q=2, south_q=2, east_q=12, west_q=8),
    ]

    decisions = controller.optimize_observations(obs_list, current_time=100.0, solver="qaoa")
    assert len(decisions) == 2
    for iid in ("J1", "J2"):
        assert decisions[iid]["valid"] is True
        assert decisions[iid]["solver"] == "qaoa"
        assert decisions[iid]["phase_0_green_seconds"] in (22, 30, 40)
        assert decisions[iid]["phase_2_green_seconds"] in (22, 30, 40)


def test_signal_safety_invariants_multi_intersection():
    controller = MultiIntersectionController()
    obs_list = [make_obs(f"J{i}", north_q=i * 3, south_q=i, east_q=i, west_q=i) for i in range(1, 5)]

    decisions = controller.optimize_observations(obs_list, current_time=100.0)
    for iid, d in decisions.items():
        # Strictly positive
        assert d["phase_0_green_seconds"] > 0
        assert d["phase_2_green_seconds"] > 0
        # Within configured bounds [22, 42]
        assert 22 <= d["phase_0_green_seconds"] <= 42
        assert 22 <= d["phase_2_green_seconds"] <= 42
        assert d["valid"] is True


def test_api_batch_multi_intersection_and_backward_compatibility():
    app = create_app()
    client = app.test_client()

    # 1. Multi-intersection batch request using canonical TrafficObservation payloads
    batch_payload = {
        "solver": "exact",
        "states": [
            make_obs("J1", north_q=15, south_q=10, east_q=1, west_q=1).to_dict(),
            make_obs("J2", north_q=1, south_q=1, east_q=15, west_q=10).to_dict(),
            make_obs("J3", north_q=6, south_q=6, east_q=6, west_q=6).to_dict(),
            make_obs("J4", north_q=8, south_q=4, east_q=2, west_q=1).to_dict(),
        ],
    }

    res = client.post("/api/optimize", json=batch_payload)
    assert res.status_code == 200
    data = res.get_json()

    # Verify both 'results' and 'decisions' keys exist
    assert "results" in data
    assert "decisions" in data
    assert len(data["results"]) == 4

    results = data["results"]
    assert results[0]["intersection_id"] == "J1"
    assert results[0]["phase_0_green_seconds"] == 40
    assert results[0]["phase_2_green_seconds"] == 22
    assert results[0]["valid"] is True

    assert results[1]["intersection_id"] == "J2"
    assert results[1]["phase_0_green_seconds"] == 22
    assert results[1]["phase_2_green_seconds"] == 40
    assert results[1]["valid"] is True

    # 2. Backward compatibility with single-intersection request
    single_res = client.post(
        "/api/optimize",
        json={"intersection_id": "J1", "phase_0_queue": 20, "phase_2_queue": 4},
    )
    assert single_res.status_code == 200
    single_data = single_res.get_json()
    assert single_data["intersection_id"] == "J1"
    assert single_data["phase_0_green_seconds"] == 40
    assert single_data["phase_2_green_seconds"] == 22
    assert single_data["valid"] is True
