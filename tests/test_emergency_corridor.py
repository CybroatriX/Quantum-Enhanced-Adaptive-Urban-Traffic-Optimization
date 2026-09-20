"""Unit and integration tests for Emergency Green Corridor priority system."""

import time

import pytest

from optimization.service import create_app
from perception.models import TrafficObservation
from simulation.models.emergency import (
    CorridorPlan,
    CorridorState,
    EmergencyRequest,
    IntersectionPriorityPlan,
)
from simulation.signals.emergency import EmergencyGreenCorridorController
from simulation.signals.multi_intersection import MultiIntersectionController


def make_obs(intersection_id: str, north_q: int = 2, east_q: int = 2) -> TrafficObservation:
    total_q = north_q + east_q
    return TrafficObservation(
        timestamp=100.0,
        source="yolov8",
        intersection_id=intersection_id,
        vehicle_count=total_q + 2,
        approach_counts={"north": north_q + 1, "south": 0, "east": east_q + 1, "west": 0},
        queue_lengths={"north": north_q, "south": 0, "east": east_q, "west": 0},
        class_counts={"car": total_q + 2, "motorcycle": 0, "bus": 0, "truck": 0},
    )


def test_valid_emergency_request_creation():
    req = EmergencyRequest(
        emergency_vehicle_id="AMB001",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J4"),
        priority="critical",
        timestamp=100.0,
        speed_mps=20.0,
    )

    assert req.emergency_vehicle_id == "AMB001"
    assert req.current_intersection_id == "J1"
    assert req.destination_intersection_id == "J4"
    assert req.route == ("J1", "J2", "J4")
    assert req.priority == "critical"
    assert req.priority_rank == 3
    assert req.speed_mps == 20.0

    d = req.to_dict()
    roundtrip = EmergencyRequest.from_dict(d)
    assert roundtrip == req


def test_invalid_emergency_requests():
    # Empty vehicle ID
    with pytest.raises(ValueError, match="emergency_vehicle_id"):
        EmergencyRequest("", "J1", "J4", ("J1", "J4"))

    # Empty current intersection
    with pytest.raises(ValueError, match="current_intersection_id"):
        EmergencyRequest("AMB001", "", "J4", ("J1", "J4"))

    # Empty destination
    with pytest.raises(ValueError, match="destination_intersection_id"):
        EmergencyRequest("AMB001", "J1", "", ("J1", "J4"))

    # Empty route
    with pytest.raises(ValueError, match="route"):
        EmergencyRequest("AMB001", "J1", "J4", ())

    # Current intersection not in route
    with pytest.raises(ValueError, match="current_intersection_id 'J9' must be part of route"):
        EmergencyRequest("AMB001", "J9", "J4", ("J1", "J4"))

    # Destination intersection not in route
    with pytest.raises(ValueError, match="destination_intersection_id 'J9' must be part of route"):
        EmergencyRequest("AMB001", "J1", "J9", ("J1", "J4"))

    # Invalid priority
    with pytest.raises(ValueError, match="Invalid priority"):
        EmergencyRequest("AMB001", "J1", "J4", ("J1", "J4"), priority="ultra_fast")

    # Negative timestamp
    with pytest.raises(ValueError, match="timestamp"):
        EmergencyRequest("AMB001", "J1", "J4", ("J1", "J4"), timestamp=-1.0)


def test_four_intersection_corridor_activation():
    controller = EmergencyGreenCorridorController(
        managed_intersection_ids=["J1", "J2", "J3", "J4"],
        emergency_green_seconds=40,
        non_priority_green_seconds=22,
    )

    req = EmergencyRequest(
        emergency_vehicle_id="AMB001",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J4"),
        priority="high",
        timestamp=100.0,
    )

    plan = controller.request_corridor(req, current_time=100.0)
    assert plan.is_valid is True
    assert plan.corridor_status == CorridorState.ACTIVE
    assert plan.affected_intersections == ["J1", "J2", "J4"]

    # Verify each intersection priority plan
    for iid in ("J1", "J2", "J4"):
        i_plan = plan.intersection_plans[iid]
        assert i_plan.intersection_id == iid
        assert i_plan.status == CorridorState.ACTIVE
        assert i_plan.priority_green_seconds == 40
        assert i_plan.non_priority_green_seconds == 22
        assert i_plan.priority_phase in (0, 2)

    # Active override lookup
    override_j1 = controller.get_active_override("J1")
    assert override_j1 is not None
    assert override_j1.priority_green_seconds == 40

    # Non-affected intersection has no active override
    assert controller.get_active_override("J3") is None


def test_eight_intersection_corridor_scalability():
    controller = EmergencyGreenCorridorController()
    route = tuple(f"J{i}" for i in range(1, 9))
    req = EmergencyRequest(
        emergency_vehicle_id="POLICE_CONVOY",
        current_intersection_id="J1",
        destination_intersection_id="J8",
        route=route,
        priority="critical",
        timestamp=100.0,
    )

    plan = controller.request_corridor(req, current_time=100.0)
    assert plan.is_valid is True
    assert len(plan.affected_intersections) == 8
    assert plan.metrics is not None
    assert plan.metrics.intersections_affected == 8
    assert plan.metrics.signal_overrides_count == 8


def test_stale_expired_emergency_request():
    controller = EmergencyGreenCorridorController(max_request_age_seconds=60.0)
    stale_req = EmergencyRequest(
        emergency_vehicle_id="AMB002",
        current_intersection_id="J1",
        destination_intersection_id="J2",
        route=("J1", "J2"),
        timestamp=50.0,
    )

    # Submitted at current_time=200.0 (age = 150.0s > 60.0s)
    plan = controller.request_corridor(stale_req, current_time=200.0)
    assert plan.is_valid is False
    assert plan.corridor_status == CorridorState.EXPIRED
    assert "expired" in plan.validation_result.lower()


def test_duplicate_emergency_request_handling():
    controller = EmergencyGreenCorridorController()
    req = EmergencyRequest(
        emergency_vehicle_id="AMB001",
        current_intersection_id="J1",
        destination_intersection_id="J2",
        route=("J1", "J2"),
        timestamp=100.0,
    )

    plan1 = controller.request_corridor(req, current_time=100.0)
    assert plan1.corridor_status == CorridorState.ACTIVE

    # Second duplicate request as heartbeat
    plan2 = controller.request_corridor(req, current_time=105.0)
    assert plan2.corridor_status == CorridorState.ACTIVE
    assert plan2.emergency_vehicle_id == "AMB001"


def test_conflicting_emergency_requests_resolution():
    controller = EmergencyGreenCorridorController()

    # Request 1: AMB_A moving J1 -> J3 (North-South route, entering J3 from North -> Phase 0)
    req_a = EmergencyRequest(
        emergency_vehicle_id="AMB_A",
        current_intersection_id="J1",
        destination_intersection_id="J3",
        route=("J1", "J3"),
        priority="medium",
        timestamp=100.0,
    )
    plan_a = controller.request_corridor(req_a, current_time=100.0)
    assert plan_a.is_valid is True

    # Request 2: AMB_B enters J3 from West (East-West route -> Phase 2) with "critical" priority
    # Conflicting phase at J3!
    req_b = EmergencyRequest(
        emergency_vehicle_id="AMB_B",
        current_intersection_id="J3",
        destination_intersection_id="J4",
        route=("J3", "J4"),
        approach_hints={"J3": "west"},
        priority="critical",  # Higher priority!
        timestamp=101.0,
    )
    plan_b = controller.request_corridor(req_b, current_time=101.0)
    # Critical beats Medium -> plan_b succeeds
    assert plan_b.is_valid is True
    assert plan_b.corridor_status == CorridorState.ACTIVE

    # Now Request 3: AMB_C with lower priority ("low") attempts conflicting corridor
    req_c = EmergencyRequest(
        emergency_vehicle_id="AMB_C",
        current_intersection_id="J1",
        destination_intersection_id="J3",
        route=("J1", "J3"),
        approach_hints={"J3": "north"},
        priority="low",
        timestamp=102.0,
    )
    plan_c = controller.request_corridor(req_c, current_time=102.0)
    # Low priority rejected against Critical!
    assert plan_c.is_valid is False
    assert plan_c.corridor_status == CorridorState.REJECTED
    assert "Preempted" in plan_c.validation_result


def test_vehicle_progression_and_release():
    controller = EmergencyGreenCorridorController()
    req = EmergencyRequest(
        emergency_vehicle_id="AMB001",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J4"),
        timestamp=100.0,
    )
    controller.request_corridor(req, current_time=100.0)

    # 1. Ambulance advances to J2: J1 should be released
    adv_plan = controller.advance_vehicle("AMB001", "J2", current_time=110.0)
    assert adv_plan is not None
    assert adv_plan.intersection_plans["J1"].status == CorridorState.RELEASED
    assert controller.get_active_override("J1") is None
    assert controller.get_active_override("J2") is not None

    # 2. Ambulance advances to destination J4: all released
    final_plan = controller.advance_vehicle("AMB001", "J4", current_time=125.0)
    assert final_plan is not None
    assert final_plan.corridor_status == CorridorState.RELEASED
    assert controller.get_active_override("J4") is None
    assert final_plan.metrics is not None
    assert final_plan.metrics.completion_timestamp == 125.0
    assert final_plan.metrics.emergency_travel_time == 25.0
    assert final_plan.metrics.corridor_activation_duration == 25.0


def test_multi_intersection_controller_emergency_override_and_resumption():
    emergency_ctrl = EmergencyGreenCorridorController()
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=["J1", "J2", "J3", "J4"],
        emergency_controller=emergency_ctrl,
        anti_oscillation_damping_seconds=0.0,
    )

    # Initial observations: J1 has heavy East queue (favors Phase 2)
    obs_list = [
        make_obs("J1", north_q=1, east_q=15),
        make_obs("J2", north_q=2, east_q=2),
        make_obs("J3", north_q=2, east_q=2),
        make_obs("J4", north_q=2, east_q=2),
    ]

    # 1. Normal state -> QUBO runs
    d1 = multi_ctrl.optimize_observations(obs_list, current_time=100.0)
    # J1 favors Phase 2 (east queue is 15)
    assert d1["J1"]["phase_2_green_seconds"] == 40
    assert d1["J1"]["phase_0_green_seconds"] == 22
    assert d1["J1"]["status"] == "optimized"

    # 2. Activate emergency corridor prioritizing Phase 0 on J1 (North-South route)
    req = EmergencyRequest(
        emergency_vehicle_id="AMB999",
        current_intersection_id="J1",
        destination_intersection_id="J3",
        route=("J1", "J3"),
        approach_hints={"J1": "north", "J3": "north"},
        timestamp=105.0,
    )
    emergency_ctrl.request_corridor(req, current_time=105.0)

    # 3. Optimize observations while emergency corridor is ACTIVE
    d2 = multi_ctrl.optimize_observations(obs_list, current_time=106.0)
    # J1 should now be temporarily OVERRIDDEN to Phase 0 = 40s (emergency priority)!
    assert d2["J1"]["status"] == "emergency_priority"
    assert d2["J1"]["emergency_priority"] is True
    assert d2["J1"]["phase_0_green_seconds"] == 40
    assert d2["J1"]["phase_2_green_seconds"] == 22

    # J2 and J4 were not in the corridor -> still normal optimized
    assert d2["J2"]["status"] == "optimized"
    assert d2["J4"]["status"] == "optimized"

    # 4. Release corridor -> Normal QUBO immediately resumes
    emergency_ctrl.release_corridor("AMB999", current_time=120.0)
    d3 = multi_ctrl.optimize_observations(obs_list, current_time=121.0)
    assert d3["J1"]["status"] == "optimized"
    assert d3["J1"]["phase_2_green_seconds"] == 40
    assert d3["J1"]["phase_0_green_seconds"] == 22


def test_emergency_corridor_api_endpoints():
    app = create_app()
    client = app.test_client()

    # 1. Request corridor via API
    req_body = {
        "emergency_vehicle_id": "AMB_API",
        "current_intersection_id": "J1",
        "destination_intersection_id": "J4",
        "route": ["J1", "J2", "J4"],
        "priority": "high",
        "timestamp": time.time(),
    }

    res = client.post("/api/emergency/corridor", json=req_body)
    assert res.status_code == 200
    data = res.get_json()
    assert data["emergency_vehicle_id"] == "AMB_API"
    assert data["corridor_status"] == "active"
    assert data["valid"] is True
    assert data["affected_intersections"] == ["J1", "J2", "J4"]
    assert "temporary_timing_decisions" in data

    # 2. Query active corridors
    get_res = client.get("/api/emergency/corridor")
    assert get_res.status_code == 200
    get_data = get_res.get_json()
    assert get_data["count"] >= 1

    # 3. Advance vehicle
    adv_res = client.post(
        "/api/emergency/advance",
        json={"emergency_vehicle_id": "AMB_API", "current_intersection_id": "J2"},
    )
    assert adv_res.status_code == 200

    # 4. Release corridor
    rel_res = client.post(
        "/api/emergency/release",
        json={"emergency_vehicle_id": "AMB_API"},
    )
    assert rel_res.status_code == 200
    rel_data = rel_res.get_json()
    assert rel_data["corridor_status"] == "released"

    # 5. Invalid request returns 400
    bad_res = client.post("/api/emergency/corridor", json={"invalid": "payload"})
    assert bad_res.status_code == 400
