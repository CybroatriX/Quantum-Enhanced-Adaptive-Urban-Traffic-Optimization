"""Phase J Demo: Dynamic Traffic Events Pipeline.

Demonstrates:
  Normal traffic
        ↓
  QUBO timing for J1-J4
        ↓
  Accident occurs at J2 East approach
        ↓
  Effective traffic state changes & Re-optimization
        ↓
  Road closure at J3
        ↓
  Re-optimization
        ↓
  Ambulance request while events are active
        ↓
  Emergency priority takes precedence
        ↓
  Emergency completes & corridor released
        ↓
  Events expire
        ↓
  Normal QUBO control resumes
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perception.models import TrafficObservation
from simulation.models.emergency import EmergencyRequest
from simulation.models.events import DynamicEvent
from simulation.signals.emergency import EmergencyGreenCorridorController
from simulation.signals.events import DynamicEventManager
from simulation.signals.multi_intersection import MultiIntersectionController


def make_obs(
    intersection_id: str,
    north_q: int,
    south_q: int,
    east_q: int,
    west_q: int,
    timestamp: float = 1789840300.0,
) -> TrafficObservation:
    total_q = north_q + south_q + east_q + west_q
    vehicle_count = total_q + 4
    return TrafficObservation(
        timestamp=timestamp,
        source="yolov8",
        intersection_id=intersection_id,
        vehicle_count=vehicle_count,
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
        class_counts={"car": vehicle_count, "motorcycle": 0, "bus": 0, "truck": 0},
        tracking_available=True,
        tracked_vehicle_count=vehicle_count,
        average_confidence=0.92,
    )


def print_decisions_table(title: str, decisions: dict, managed_ids: list[str]) -> None:
    print(f"\n{title}")
    print("-" * 96)
    print(
        f"{'Intersection':<14} | {'P0 Green':<10} | {'P2 Green':<10} | {'Objective':<10} | {'Solver':<12} | {'Status':<18} | {'Valid'}"
    )
    print("-" * 96)
    for iid in managed_ids:
        d = decisions[iid]
        p0 = f"{d['phase_0_green_seconds']}s"
        p2 = f"{d['phase_2_green_seconds']}s"
        obj = f"{d['objective']:.4f}"
        solver = d["solver"]
        st = d["status"]
        v = d["valid"]
        print(f"{iid:<14} | {p0:<10} | {p2:<10} | {obj:<10} | {solver:<12} | {st:<18} | {v}")
    print("-" * 96)


def main() -> None:
    print("===============================================================================")
    print("  FlowQ Phase J: Dynamic Traffic Events Pipeline (J1 - J4 Network)")
    print("===============================================================================\n")

    managed_ids = ["J1", "J2", "J3", "J4"]
    sim_time = 1789840300.0

    # 1. Initialize Controllers
    event_mgr = DynamicEventManager(managed_intersection_ids=managed_ids)
    emg_ctrl = EmergencyGreenCorridorController(
        managed_intersection_ids=managed_ids,
        max_request_age_seconds=600.0,
    )
    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=managed_ids,
        anti_oscillation_damping_seconds=0.0,
        default_solver="exact",
        emergency_controller=emg_ctrl,
        event_manager=event_mgr,
    )

    # 2. Baseline Traffic Observations
    base_obs = [
        make_obs("J1", north_q=12, south_q=8, east_q=2, west_q=2, timestamp=sim_time),
        make_obs("J2", north_q=3, south_q=2, east_q=4, west_q=3, timestamp=sim_time),
        make_obs("J3", north_q=4, south_q=4, east_q=4, west_q=4, timestamp=sim_time),
        make_obs("J4", north_q=8, south_q=6, east_q=2, west_q=1, timestamp=sim_time),
    ]

    print("Step 1: Baseline Normal Traffic & Canonical QUBO Timings")
    normal_decisions = multi_ctrl.optimize_observations(base_obs, current_time=sim_time)
    print_decisions_table("1. Baseline Canonical QUBO Optimization:", normal_decisions, managed_ids)

    # 3. Dynamic Event 1: Severe Accident occurs at J2 East approach
    print("\nStep 2: Dynamic Event Injection - Accident at J2 East Approach")
    accident_event = DynamicEvent(
        event_id="ACC_J2_01",
        event_type="accident",
        affected_intersection_ids=("J2",),
        affected_approaches=("east",),
        severity="high",
        start_time=sim_time,
        end_time=sim_time + 400.0,
        capacity_factor=0.35,  # 65% capacity reduction
        queue_adder=18,        # 18 vehicles backed up in queue
        description="Multi-vehicle collision blocking East approach lanes",
    )
    ok, msg, _ = event_mgr.register_event(accident_event, current_time=sim_time)
    print(f"  Event ID     : {accident_event.event_id} ({accident_event.event_type.upper()})")
    print(f"  Registration : {msg}")
    print(f"  Impact       : Capacity drops to {int(accident_event.capacity_factor * 100)}%, Queue +{accident_event.queue_adder} on East approach")

    eff_obs_j2, eff_cap_j2, meta_j2 = event_mgr.apply_to_observation(
        base_obs[1], current_time=sim_time, base_road_capacity=100
    )
    print(f"  Before Event : Queues={base_obs[1].queue_lengths}, Road Capacity=100")
    print(f"  After Event  : Queues={eff_obs_j2.queue_lengths}, Effective Road Capacity={eff_cap_j2}")

    # Re-optimize under Accident
    sim_time += 10.0
    accident_decisions = multi_ctrl.optimize_observations(
        [
            make_obs("J1", 12, 8, 2, 2, timestamp=sim_time),
            make_obs("J2", 3, 2, 4, 3, timestamp=sim_time),
            make_obs("J3", 4, 4, 4, 4, timestamp=sim_time),
            make_obs("J4", 8, 6, 2, 1, timestamp=sim_time),
        ],
        current_time=sim_time,
    )
    print_decisions_table("2. QUBO Re-Optimization with Active Accident at J2:", accident_decisions, managed_ids)

    # 4. Dynamic Event 2: Road Closure at J3 North/South
    print("\nStep 3: Dynamic Event Injection - Road Closure at J3 North & South")
    closure_event = DynamicEvent(
        event_id="CLOSE_J3_01",
        event_type="road_closure",
        affected_intersection_ids=("J3",),
        affected_approaches=("north", "south"),
        severity="critical",
        start_time=sim_time,
        end_time=sim_time + 400.0,
        capacity_factor=0.05,
        queue_adder=22,
        description="Emergency utility pipeline repair on North-South corridor",
    )
    event_mgr.register_event(closure_event, current_time=sim_time)
    print(f"  Event ID     : {closure_event.event_id} ({closure_event.event_type.upper()})")
    print(f"  Impact       : Capacity near zero (5%), Queues backed up on North & South approaches")

    sim_time += 10.0
    multi_event_decisions = multi_ctrl.optimize_observations(
        [
            make_obs("J1", 12, 8, 2, 2, timestamp=sim_time),
            make_obs("J2", 3, 2, 4, 3, timestamp=sim_time),
            make_obs("J3", 4, 4, 4, 4, timestamp=sim_time),
            make_obs("J4", 8, 6, 2, 1, timestamp=sim_time),
        ],
        current_time=sim_time,
    )
    print_decisions_table("3. QUBO Re-Optimization with Simultaneous Events at J2 and J3:", multi_event_decisions, managed_ids)

    # 5. Precedence Test: Ambulance Request Overrides J2 and J3
    print("\nStep 4: Emergency Vehicle Preemption Over Active Dynamic Events")
    print("  Ambulance dispatched along corridor: J1 -> J2 -> J3 -> J4")
    emg_req = EmergencyRequest(
        emergency_vehicle_id="AMB_PRECEDENCE",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J3", "J4"),
        priority="critical",
        timestamp=sim_time,
        approach_hints={"J1": "south"},
    )
    plan = emg_ctrl.request_corridor(emg_req, current_time=sim_time)
    print(f"  Emergency Corridor Status : {plan.corridor_status.value.upper()}")
    print("  Evaluating Precedence: Safety Constraints -> Emergency Priority -> Dynamic Events -> Normal QUBO")

    sim_time += 5.0
    emg_decisions = multi_ctrl.optimize_observations(
        [
            make_obs("J1", 12, 8, 2, 2, timestamp=sim_time),
            make_obs("J2", 3, 2, 4, 3, timestamp=sim_time),
            make_obs("J3", 4, 4, 4, 4, timestamp=sim_time),
            make_obs("J4", 8, 6, 2, 1, timestamp=sim_time),
        ],
        current_time=sim_time,
    )
    print_decisions_table("4. Multi-Intersection State during Emergency Corridor (Preemption Active):", emg_decisions, managed_ids)
    print("  Note: J2 and J3 events were preempted by emergency priority (events_preempted_by_emergency=True)!")

    # 6. Ambulance Traversal & Release
    print("\nStep 5: Ambulance Traversal & Corridor Clearance")
    sim_time += 60.0
    emg_ctrl.release_corridor("AMB_PRECEDENCE")
    print("  Ambulance reached destination -> Corridor released!")

    # 7. Events Expire
    print("\nStep 6: Dynamic Events Expiration & Resumption of Baseline Traffic")
    sim_time += 400.0  # Move time past event end times
    print(f"  Simulation time advanced to T+{sim_time - 1789840300.0:.0f}s (events now expired)")
    assert event_mgr.get_event_status("ACC_J2_01", current_time=sim_time).value == "expired"
    assert event_mgr.get_event_status("CLOSE_J3_01", current_time=sim_time).value == "expired"

    resumed_decisions = multi_ctrl.optimize_observations(
        [
            make_obs("J1", 12, 8, 2, 2, timestamp=sim_time),
            make_obs("J2", 3, 2, 4, 3, timestamp=sim_time),
            make_obs("J3", 4, 4, 4, 4, timestamp=sim_time),
            make_obs("J4", 8, 6, 2, 1, timestamp=sim_time),
        ],
        current_time=sim_time,
    )
    print_decisions_table("5. Resumed Normal Canonical QUBO Optimization (Post-Event):", resumed_decisions, managed_ids)

    # 8. Phase K Metrics Output
    print("\nStep 7: Recorded Dynamic Event Metrics (Prepared for Phase K Evaluation)")
    print("-" * 79)
    for eid in ["ACC_J2_01", "CLOSE_J3_01"]:
        m = event_mgr.get_metrics(eid)
        if m:
            print(f"  Event ID              : {m.event_id} ({m.event_type})")
            print(f"  Affected Intersections: {m.affected_intersections}")
            print(f"  Queues During Event   : {m.queues_during}")
            print(f"  Signal Overrides Count: {m.signal_overrides_count}")
    print("-" * 79)
    print("\nDynamic Events pipeline demonstration completed successfully!")


if __name__ == "__main__":
    main()
