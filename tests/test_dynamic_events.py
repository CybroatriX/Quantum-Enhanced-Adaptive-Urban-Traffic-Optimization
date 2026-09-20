"""Comprehensive unit and integration tests for Phase J Dynamic Events."""

import time
import pytest

from optimization.service import create_app
from perception.models import TrafficObservation
from simulation.models.emergency import EmergencyRequest
from simulation.models.events import DynamicEvent, EventSeverity, EventStatus, EventType
from simulation.signals.emergency import EmergencyGreenCorridorController
from simulation.signals.events import DynamicEventManager
from simulation.signals.multi_intersection import MultiIntersectionController


def make_obs(
    intersection_id: str,
    north_q: int = 2,
    south_q: int = 2,
    east_q: int = 2,
    west_q: int = 2,
    timestamp: float = 1789840300.0,
) -> TrafficObservation:
    total_q = north_q + south_q + east_q + west_q
    return TrafficObservation(
        timestamp=timestamp,
        source="yolov8",
        intersection_id=intersection_id,
        vehicle_count=total_q + 4,
        approach_counts={
            "north": north_q + 1,
            "south": south_q + 1,
            "east": east_q + 1,
            "west": west_q + 1,
        },
        queue_lengths={
            "north": north_q,
            "south": south_q,
            "east": east_q,
            "west": west_q,
        },
        class_counts={"car": total_q + 4, "motorcycle": 0, "bus": 0, "truck": 0},
        tracking_available=True,
        tracked_vehicle_count=total_q + 4,
        average_confidence=0.92,
    )


# 1. Valid Event Creation
def test_valid_dynamic_event_creation():
    ev = DynamicEvent(
        event_id="ACC_001",
        event_type="accident",
        affected_intersection_ids=("J2",),
        affected_approaches=("east",),
        severity="high",
        start_time=100.0,
        end_time=400.0,
        capacity_factor=0.4,
        demand_multiplier=1.5,
        queue_adder=10,
    )
    assert ev.event_id == "ACC_001"
    assert ev.event_type == "accident"
    assert ev.affected_intersection_ids == ("J2",)
    assert ev.affected_approaches == ("east",)
    assert ev.severity == "high"
    assert ev.capacity_factor == 0.4
    assert ev.demand_multiplier == 1.5
    assert ev.queue_adder == 10

    # Serialization test
    d = ev.to_dict()
    assert d["event_id"] == "ACC_001"
    ev_copy = DynamicEvent.from_dict(d)
    assert ev_copy == ev


# 2. Invalid Event Validation
def test_invalid_dynamic_events():
    # Empty ID
    with pytest.raises(ValueError, match="event_id"):
        DynamicEvent(
            event_id="",
            event_type="accident",
            affected_intersection_ids=("J1",),
            affected_approaches=("north",),
        )

    # Invalid type
    with pytest.raises(ValueError, match="event_type"):
        DynamicEvent(
            event_id="EVT1",
            event_type="alien_invasion",
            affected_intersection_ids=("J1",),
            affected_approaches=("north",),
        )

    # Empty intersections
    with pytest.raises(ValueError, match="affected_intersection_ids"):
        DynamicEvent(
            event_id="EVT1",
            event_type="accident",
            affected_intersection_ids=(),
            affected_approaches=("north",),
        )

    # Invalid approach
    with pytest.raises(ValueError, match="approach"):
        DynamicEvent(
            event_id="EVT1",
            event_type="accident",
            affected_intersection_ids=("J1",),
            affected_approaches=("upwards",),
        )

    # Invalid severity
    with pytest.raises(ValueError, match="severity"):
        DynamicEvent(
            event_id="EVT1",
            event_type="accident",
            affected_intersection_ids=("J1",),
            affected_approaches=("north",),
            severity="extreme_catastrophe",
        )

    # Negative start time
    with pytest.raises(ValueError, match="negative"):
        DynamicEvent(
            event_id="EVT1",
            event_type="accident",
            affected_intersection_ids=("J1",),
            affected_approaches=("north",),
            start_time=-10.0,
        )

    # start_time > end_time
    with pytest.raises(ValueError, match="start_time .* must be less than or equal"):
        DynamicEvent(
            event_id="EVT1",
            event_type="accident",
            affected_intersection_ids=("J1",),
            affected_approaches=("north",),
            start_time=500.0,
            end_time=200.0,
        )


# 3. Event Lifecycle: Activation & Expiration
def test_event_lifecycle_activation_and_expiration():
    ev = DynamicEvent(
        event_id="SURGE_01",
        event_type="traffic_surge",
        affected_intersection_ids=("J1",),
        affected_approaches=("all",),
        start_time=200.0,
        end_time=500.0,
    )
    # Before start
    assert ev.status_at(150.0) == EventStatus.SCHEDULED
    assert not ev.is_active_at(150.0)

    # During event
    assert ev.status_at(200.0) == EventStatus.ACTIVE
    assert ev.status_at(350.0) == EventStatus.ACTIVE
    assert ev.status_at(500.0) == EventStatus.ACTIVE
    assert ev.is_active_at(350.0)

    # After end
    assert ev.status_at(500.1) == EventStatus.EXPIRED
    assert not ev.is_active_at(500.1)


# 4. Duplicate Event and Cancellation
def test_duplicate_event_and_cancellation():
    mgr = DynamicEventManager()
    now = 1000.0

    ev = DynamicEvent(
        event_id="EVT_DUP",
        event_type="lane_blockage",
        affected_intersection_ids=("J3",),
        affected_approaches=("north",),
        start_time=now,
        end_time=now + 300.0,
    )

    ok1, msg1, reg1 = mgr.register_event(ev, current_time=now)
    assert ok1 is True
    assert "registered successfully" in msg1

    # Duplicate registration of identical event is idempotent
    ok2, msg2, reg2 = mgr.register_event(ev, current_time=now)
    assert ok2 is True
    assert "idempotently" in msg2

    # Cancellation
    cancelled = mgr.cancel_event("EVT_DUP", current_time=now + 50.0)
    assert cancelled is True
    assert mgr.get_event("EVT_DUP") is None
    assert mgr.get_event_status("EVT_DUP") == EventStatus.CANCELLED
    assert not mgr.has_active_events("J3", current_time=now + 50.0)

    # Cancelling non-existent returns False
    assert mgr.cancel_event("NON_EXISTENT") is False


# 5. Stale / Expired Event Registration Rejection
def test_stale_expired_event_registration():
    mgr = DynamicEventManager()
    now = 1000.0
    stale_ev = DynamicEvent(
        event_id="STALE_01",
        event_type="accident",
        affected_intersection_ids=("J1",),
        affected_approaches=("west",),
        start_time=500.0,
        end_time=800.0,  # Already ended at now=1000.0
    )
    ok, msg, reg = mgr.register_event(stale_ev, current_time=now)
    assert ok is False
    assert reg is None
    assert "expired" in msg.lower()


# 6. Accident Impact on Observation & Capacity
def test_accident_impact_on_traffic_state():
    mgr = DynamicEventManager()
    now = 1000.0
    mgr.register_event(
        {
            "event_id": "ACC_J2",
            "event_type": "accident",
            "affected_intersection_ids": ["J2"],
            "affected_approaches": ["east"],
            "severity": "high",
            "capacity_factor": 0.40,
            "queue_adder": 14,
            "start_time": now,
            "end_time": now + 300.0,
        },
        current_time=now,
    )

    base_obs = make_obs("J2", north_q=2, south_q=2, east_q=3, west_q=2, timestamp=now)
    eff_obs, eff_cap, meta = mgr.apply_to_observation(base_obs, current_time=now, base_road_capacity=100)

    assert meta["events_applied"] is True
    assert "ACC_J2" in meta["active_event_ids"]
    assert eff_cap == 40  # 100 * 0.40
    assert eff_obs.queue_lengths["east"] == 3 + 14  # 17 vehicles
    assert eff_obs.queue_lengths["north"] == 2  # unchanged
    assert eff_obs.queue_lengths["west"] == 2  # unchanged


# 7. Road Closure Impact
def test_road_closure_impact():
    mgr = DynamicEventManager()
    now = 1000.0
    mgr.register_event(
        {
            "event_id": "CLOSE_J3",
            "event_type": "road_closure",
            "affected_intersection_ids": ["J3"],
            "affected_approaches": ["north", "south"],
            "capacity_factor": 0.05,
            "queue_adder": 20,
            "start_time": now,
            "end_time": now + 600.0,
        },
        current_time=now,
    )

    base_obs = make_obs("J3", north_q=1, south_q=1, east_q=5, west_q=5, timestamp=now)
    eff_obs, eff_cap, meta = mgr.apply_to_observation(base_obs, current_time=now, base_road_capacity=100)

    assert eff_cap == 5  # clamped to minimum safe capacity
    assert eff_obs.queue_lengths["north"] == 21
    assert eff_obs.queue_lengths["south"] == 21
    assert eff_obs.queue_lengths["east"] == 5


# 8. Demand Surge Impact
def test_traffic_surge_impact():
    mgr = DynamicEventManager()
    now = 1000.0
    mgr.register_event(
        {
            "event_id": "SURGE_J1",
            "event_type": "traffic_surge",
            "affected_intersection_ids": ["J1"],
            "affected_approaches": ["all"],
            "demand_multiplier": 2.0,
            "queue_adder": 5,
            "start_time": now,
            "end_time": now + 400.0,
        },
        current_time=now,
    )

    base_obs = make_obs("J1", north_q=5, south_q=5, east_q=2, west_q=2, timestamp=now)
    eff_obs, eff_cap, meta = mgr.apply_to_observation(base_obs, current_time=now, base_road_capacity=100)

    assert eff_cap == 100  # capacity untouched for surge
    # (5 + 5) * 2.0 = 20
    assert eff_obs.queue_lengths["north"] == 20
    assert eff_obs.queue_lengths["south"] == 20
    # (2 + 5) * 2.0 = 14
    assert eff_obs.queue_lengths["east"] == 14
    assert eff_obs.queue_lengths["west"] == 14


# 9. Pedestrian Demand Event Handling
def test_pedestrian_demand_event():
    mgr = DynamicEventManager()
    multi = MultiIntersectionController(
        managed_intersection_ids=["J1"],
        anti_oscillation_damping_seconds=0.0,
        event_manager=mgr,
    )
    now = 1000.0

    mgr.register_event(
        {
            "event_id": "PED_J1",
            "event_type": "pedestrian_demand",
            "affected_intersection_ids": ["J1"],
            "affected_approaches": ["east"],  # Crossing phase 2 (East-West)
            "min_pedestrian_green": 32,
            "start_time": now,
            "end_time": now + 300.0,
        },
        current_time=now,
    )

    # Base observation with minimal EW traffic
    base_obs = [make_obs("J1", north_q=15, south_q=10, east_q=0, west_q=0, timestamp=now)]
    decisions = multi.optimize_observations(base_obs, current_time=now)
    d = decisions["J1"]

    assert d["status"] == "event_adapted"
    # Even though EW traffic is 0, pedestrian demand guarantees at least 32s on Phase 2!
    assert d["phase_2_green_seconds"] >= 32
    assert d["valid"] is True


# 10. Multiple Simultaneous Events Compounding
def test_multiple_simultaneous_events():
    mgr = DynamicEventManager()
    now = 1000.0

    # Event 1: Lane blockage on North
    mgr.register_event(
        {
            "event_id": "LANE_01",
            "event_type": "lane_blockage",
            "affected_intersection_ids": ["J1"],
            "affected_approaches": ["north"],
            "capacity_factor": 0.70,
            "queue_adder": 4,
            "start_time": now,
            "end_time": now + 500.0,
        },
        current_time=now,
    )
    # Event 2: Traffic surge on all approaches
    mgr.register_event(
        {
            "event_id": "SURGE_02",
            "event_type": "traffic_surge",
            "affected_intersection_ids": ["J1"],
            "affected_approaches": ["all"],
            "demand_multiplier": 1.5,
            "queue_adder": 2,
            "start_time": now,
            "end_time": now + 500.0,
        },
        current_time=now,
    )

    base_obs = make_obs("J1", north_q=4, south_q=2, east_q=2, west_q=2, timestamp=now)
    eff_obs, eff_cap, meta = mgr.apply_to_observation(base_obs, current_time=now, base_road_capacity=100)

    assert meta["events_applied"] is True
    assert len(meta["active_event_ids"]) == 2
    assert eff_cap == 70
    # North had 4 -> +4 (LANE) = 8 -> +2 (SURGE) = 10 -> * 1.5 = 15
    assert eff_obs.queue_lengths["north"] == 15


# 11. Affected vs Unaffected Intersections Isolation
def test_affected_vs_unaffected_intersections():
    mgr = DynamicEventManager()
    multi = MultiIntersectionController(
        managed_intersection_ids=["J1", "J2", "J3", "J4"],
        anti_oscillation_damping_seconds=0.0,
        event_manager=mgr,
    )
    now = 1000.0

    # Event only at J2
    mgr.register_event(
        {
            "event_id": "ACC_J2_ONLY",
            "event_type": "accident",
            "affected_intersection_ids": ["J2"],
            "affected_approaches": ["east"],
            "severity": "high",
            "capacity_factor": 0.4,
            "queue_adder": 15,
            "start_time": now,
            "end_time": now + 300.0,
        },
        current_time=now,
    )

    obs_list = [
        make_obs("J1", north_q=4, south_q=4, east_q=2, west_q=2, timestamp=now),
        make_obs("J2", north_q=2, south_q=2, east_q=2, west_q=2, timestamp=now),
        make_obs("J3", north_q=3, south_q=3, east_q=3, west_q=3, timestamp=now),
        make_obs("J4", north_q=5, south_q=5, east_q=1, west_q=1, timestamp=now),
    ]

    decisions = multi.optimize_observations(obs_list, current_time=now)

    # J2 should be event_adapted
    assert decisions["J2"]["status"] == "event_adapted"
    assert decisions["J2"]["event_adapted"] is True
    assert decisions["J2"]["effective_capacity"] == 40
    # East approach queue surged from 2 to 17 -> Phase 2 (EW) gets dominant green
    assert decisions["J2"]["phase_2_green_seconds"] > decisions["J2"]["phase_0_green_seconds"]

    # J1, J3, J4 remain normal optimized
    assert decisions["J1"]["status"] == "optimized"
    assert "event_adapted" not in decisions["J1"]
    assert decisions["J3"]["status"] == "optimized"
    assert decisions["J4"]["status"] == "optimized"


# 12. Precedence Hierarchy: Emergency Corridor Preempts Dynamic Events
def test_emergency_preempts_dynamic_events():
    event_mgr = DynamicEventManager()
    emg_ctrl = EmergencyGreenCorridorController(managed_intersection_ids=["J1", "J2", "J3", "J4"])
    multi = MultiIntersectionController(
        managed_intersection_ids=["J1", "J2", "J3", "J4"],
        anti_oscillation_damping_seconds=0.0,
        emergency_controller=emg_ctrl,
        event_manager=event_mgr,
    )
    now = 1000.0

    # 1. Dynamic event active at J2 (accident on North, wanting Phase 0 green)
    event_mgr.register_event(
        {
            "event_id": "ACC_J2",
            "event_type": "accident",
            "affected_intersection_ids": ["J2"],
            "affected_approaches": ["north"],
            "queue_adder": 25,
            "start_time": now,
            "end_time": now + 600.0,
        },
        current_time=now,
    )

    # 2. Ambulance arrives traveling East-West through J2 (demanding Phase 2 green)
    emg_req = EmergencyRequest(
        emergency_vehicle_id="AMB_PRECEDENCE",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J4"),
        priority="critical",
        timestamp=now,
        approach_hints={"J2": "west"},  # West approach requires Phase 2 green
    )
    plan = emg_ctrl.request_corridor(emg_req, current_time=now)
    assert plan.corridor_status == "active"

    # 3. Optimize observations
    obs_list = [
        make_obs("J1", north_q=4, south_q=4, east_q=2, west_q=2, timestamp=now),
        make_obs("J2", north_q=10, south_q=10, east_q=2, west_q=2, timestamp=now),
        make_obs("J4", north_q=4, south_q=4, east_q=2, west_q=2, timestamp=now),
    ]
    decisions = multi.optimize_observations(obs_list, current_time=now)

    # Emergency Priority MUST take precedence over dynamic events!
    d2 = decisions["J2"]
    assert d2["status"] == "emergency_priority"
    assert d2["emergency_priority"] is True
    assert d2["phase_2_green_seconds"] == 40  # Priority phase given 40s
    assert d2["phase_0_green_seconds"] == 22  # Non-priority phase clamped to 22s
    assert d2.get("events_preempted_by_emergency") is True


# 13. Event + Canonical QUBO Matrix Solver Integration
def test_event_qubo_matrix_solving():
    mgr = DynamicEventManager()
    multi = MultiIntersectionController(
        managed_intersection_ids=["J1"],
        anti_oscillation_damping_seconds=0.0,
        default_solver="exact",
        event_manager=mgr,
    )
    now = 1000.0

    mgr.register_event(
        {
            "event_id": "SURGE_EW",
            "event_type": "traffic_surge",
            "affected_intersection_ids": ["J1"],
            "affected_approaches": ["east", "west"],
            "queue_adder": 18,
            "start_time": now,
            "end_time": now + 300.0,
        },
        current_time=now,
    )

    obs = [make_obs("J1", north_q=2, south_q=2, east_q=1, west_q=1, timestamp=now)]
    decisions = multi.optimize_observations(obs, current_time=now)
    d = decisions["J1"]

    assert d["valid"] is True
    assert 22 <= d["phase_0_green_seconds"] <= 42
    assert 22 <= d["phase_2_green_seconds"] <= 42
    assert d["phase_2_green_seconds"] == 40  # Massive EW queue surge dictates 40s green
    assert d["phase_0_green_seconds"] == 22
    assert isinstance(d["objective"], float)


# 14. 8-Intersection Network Scalability with Events
def test_eight_intersection_network_with_events():
    iids = [f"J{i}" for i in range(1, 9)]
    mgr = DynamicEventManager(managed_intersection_ids=iids)
    multi = MultiIntersectionController(
        managed_intersection_ids=iids,
        anti_oscillation_damping_seconds=0.0,
        event_manager=mgr,
    )
    now = 1000.0

    # Register events across J3 and J7
    mgr.register_event(
        {
            "event_id": "ACC_J3",
            "event_type": "accident",
            "affected_intersection_ids": ["J3"],
            "affected_approaches": ["north"],
            "queue_adder": 10,
            "start_time": now,
            "end_time": now + 300.0,
        },
        current_time=now,
    )
    mgr.register_event(
        {
            "event_id": "CLOSE_J7",
            "event_type": "road_closure",
            "affected_intersection_ids": ["J7"],
            "affected_approaches": ["east"],
            "queue_adder": 15,
            "start_time": now,
            "end_time": now + 300.0,
        },
        current_time=now,
    )

    obs_list = [make_obs(iid, north_q=3, south_q=3, east_q=3, west_q=3, timestamp=now) for iid in iids]
    decisions = multi.optimize_observations(obs_list, current_time=now)

    assert len(decisions) == 8
    assert decisions["J3"]["status"] == "event_adapted"
    assert decisions["J7"]["status"] == "event_adapted"
    # Unaffected intersections continue standard optimization
    for iid in ["J1", "J2", "J4", "J5", "J6", "J8"]:
        assert decisions[iid]["status"] == "optimized"


# 15. REST API: Dynamic Event Registration, Query, and Deletion
def test_dynamic_event_api_endpoints():
    app = create_app()
    client = app.test_client()
    now = time.time()

    # 1. POST valid event
    post_res = client.post(
        "/api/events",
        json={
            "event_id": "API_ACC_01",
            "event_type": "accident",
            "affected_intersection_ids": ["J2"],
            "affected_approaches": ["east"],
            "severity": "high",
            "start_time": now,
            "end_time": now + 500.0,
        },
    )
    assert post_res.status_code == 200
    data = post_res.get_json()
    assert data["event_id"] == "API_ACC_01"
    assert data["accepted"] is True
    assert data["active_status"] == "active"
    assert data["affected_intersections"] == ["J2"]

    # 2. GET events list
    get_res = client.get("/api/events")
    assert get_res.status_code == 200
    get_data = get_res.get_json()
    assert get_data["count"] >= 1
    found = any(e["event_id"] == "API_ACC_01" for e in get_data["events"])
    assert found is True

    # 3. GET with filter
    filter_res = client.get("/api/events?intersection_id=J2")
    assert filter_res.status_code == 200
    filter_data = filter_res.get_json()
    assert len(filter_data["events"]) >= 1

    # 4. DELETE event
    del_res = client.delete("/api/events/API_ACC_01")
    assert del_res.status_code == 200
    del_data = del_res.get_json()
    assert del_data["status"] == "cancelled"

    # 5. Invalid event payload returns 400
    bad_res = client.post("/api/events", json={"invalid": "payload"})
    assert bad_res.status_code == 400
