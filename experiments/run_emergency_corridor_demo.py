"""Phase I Demo: Emergency Green Corridor Priority System.

Demonstrates:
  Normal traffic state
          ↓
  QUBO timings for J1-J4
          ↓
  Ambulance request: J1 -> J4
          ↓
  Emergency corridor activation
          ↓
  Temporary signal priority at J1-J4
          ↓
  Ambulance passes
          ↓
  Corridor release
          ↓
  Normal QUBO control resumes
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perception.models import TrafficObservation
from simulation.models.emergency import EmergencyRequest
from simulation.signals.emergency import EmergencyGreenCorridorController
from simulation.signals.multi_intersection import MultiIntersectionController


def make_obs(
    intersection_id: str,
    north_q: int,
    south_q: int,
    east_q: int,
    west_q: int,
    timestamp: float = 1789840200.0,
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


def main() -> None:
    print("===============================================================================")
    print("  FlowQ Phase I: Emergency Green Corridor Priority System (J1 - J4 Corridor)")
    print("===============================================================================\n")

    managed_ids = ["J1", "J2", "J3", "J4"]
    current_sim_time = 1789840200.0

    # 1. Initialize EmergencyGreenCorridorController and MultiIntersectionController
    emergency_ctrl = EmergencyGreenCorridorController(
        managed_intersection_ids=managed_ids,
        emergency_green_seconds=40,
        non_priority_green_seconds=22,
        max_request_age_seconds=600.0,
    )

    multi_ctrl = MultiIntersectionController(
        managed_intersection_ids=managed_ids,
        default_solver="exact",
        anti_oscillation_damping_seconds=0.0,
        emergency_controller=emergency_ctrl,
    )

    # 2. Baseline Traffic State: Normal traffic with varying queue demands
    # J1: North/South dominant
    # J2: East/West dominant
    # J3: Balanced demand
    # J4: North/South dominant
    normal_obs = [
        make_obs("J1", north_q=14, south_q=8, east_q=2, west_q=1, timestamp=current_sim_time),
        make_obs("J2", north_q=2, south_q=1, east_q=16, west_q=10, timestamp=current_sim_time),
        make_obs("J3", north_q=4, south_q=4, east_q=4, west_q=4, timestamp=current_sim_time),
        make_obs("J4", north_q=11, south_q=6, east_q=2, west_q=2, timestamp=current_sim_time),
    ]

    print("Step 1: Normal Traffic State & Canonical QUBO Timing (J1 - J4)")
    print("-" * 79)
    normal_decisions = multi_ctrl.optimize_observations(normal_obs, current_time=current_sim_time)
    for iid in managed_ids:
        d = normal_decisions[iid]
        print(
            f"  [{iid}] Normal QUBO Timings: P0(NS)={d['phase_0_green_seconds']}s, "
            f"P2(EW)={d['phase_2_green_seconds']}s | Solver: {d['solver']} | Valid: {d['valid']}"
        )
    print("-" * 79)

    # 3. Ingest Emergency Vehicle Request (Ambulance J1 -> J4 via J2, J3)
    print("\nStep 2: Emergency Vehicle Dispatch & Priority Request")
    req = EmergencyRequest(
        emergency_vehicle_id="AMB_001",
        current_intersection_id="J1",
        destination_intersection_id="J4",
        route=("J1", "J2", "J3", "J4"),
        priority="critical",
        timestamp=current_sim_time,
        speed_mps=15.0,
        approach_hints={"J1": "south"},  # Arrives at J1 from South approach
    )
    print(f"  Vehicle ID    : {req.emergency_vehicle_id}")
    print(f"  Priority Level: {req.priority.upper()} (Rank {req.priority_rank})")
    print(f"  Corridor Route: {' -> '.join(req.route)}")
    print(f"  Timestamp     : {req.timestamp}")

    # 4. Activate Emergency Green Corridor
    print("\nStep 3: Emergency Corridor Activation & Safety Validation")
    plan = emergency_ctrl.request_corridor(req, current_time=current_sim_time)
    print(f"  Status        : {plan.corridor_status.value.upper()}")
    print(f"  Validation    : {plan.validation_result}")
    print(f"  Intersections : {plan.affected_intersections}")

    # 5. Multi-Intersection Optimization with Emergency Priority Active
    print("\nStep 4: Multi-Intersection Controller Override (Temporary Priority Timing)")
    print("-" * 88)
    print(
        f"{'Intersection':<14} | {'Normal Timing':<16} | {'Emergency Timing':<18} | {'Priority Appr':<14} | {'Corridor State':<14} | {'Valid'}"
    )
    print("-" * 88)

    emg_decisions = multi_ctrl.optimize_observations(normal_obs, current_time=current_sim_time + 5.0)

    for iid in managed_ids:
        nd = normal_decisions[iid]
        ed = emg_decisions[iid]
        iplan = plan.intersection_plans.get(iid)
        appr = iplan.priority_approach if iplan else "none"
        norm_str = f"P0={nd['phase_0_green_seconds']}s, P2={nd['phase_2_green_seconds']}s"
        emg_str = f"P0={ed['phase_0_green_seconds']}s, P2={ed['phase_2_green_seconds']}s"
        st = iplan.status.value if iplan else "idle"
        val = ed["valid"] and (iplan is not None)
        print(
            f"{iid:<14} | {norm_str:<16} | {emg_str:<18} | {appr:<14} | {st:<14} | {val}"
        )
    print("-" * 88)

    # 6. Simulate Vehicle Progression: Advance through corridor
    print("\nStep 5: Vehicle Traversal & Progressive Junction Release")
    # Vehicle passes J1 and arrives at J2
    current_sim_time += 20.0
    print(f"  [T+{current_sim_time - 1789840200.0:.0f}s] Ambulance passed J1, approaching J2...")
    plan_adv1 = emergency_ctrl.advance_vehicle("AMB_001", "J2", current_time=current_sim_time)
    print(f"    -> J1 status: {plan_adv1.intersection_plans['J1'].status.value} (Priority released)")
    print(f"    -> J2 status: {plan_adv1.intersection_plans['J2'].status.value} (Priority active)")

    # Vehicle passes J2, arrives at J3
    current_sim_time += 20.0
    print(f"  [T+{current_sim_time - 1789840200.0:.0f}s] Ambulance passed J2, approaching J3...")
    emergency_ctrl.advance_vehicle("AMB_001", "J3", current_time=current_sim_time)

    # Vehicle arrives at final junction J4 and clears corridor
    current_sim_time += 20.0
    print(f"  [T+{current_sim_time - 1789840200.0:.0f}s] Ambulance passed J4 -> Destination reached!")
    final_plan = emergency_ctrl.advance_vehicle("AMB_001", "J4", current_time=current_sim_time)
    print(f"    -> Corridor Status: {final_plan.corridor_status.value.upper()}")

    # 7. Resume Normal Canonical QUBO Control
    print("\nStep 6: Corridor Released -> Resuming Normal Canonical QUBO Optimization")
    print("-" * 79)
    post_obs = [
        make_obs("J1", north_q=14, south_q=8, east_q=2, west_q=1, timestamp=current_sim_time + 5.0),
        make_obs("J2", north_q=2, south_q=1, east_q=16, west_q=10, timestamp=current_sim_time + 5.0),
        make_obs("J3", north_q=4, south_q=4, east_q=4, west_q=4, timestamp=current_sim_time + 5.0),
        make_obs("J4", north_q=11, south_q=6, east_q=2, west_q=2, timestamp=current_sim_time + 5.0),
    ]
    resumed_decisions = multi_ctrl.optimize_observations(post_obs, current_time=current_sim_time + 5.0)
    for iid in managed_ids:
        rd = resumed_decisions[iid]
        ctrl_mode = rd.get("method", f"QUBO ({rd.get('solver', 'exact')})")
        print(
            f"  [{iid}] Resumed QUBO Timings: P0(NS)={rd['phase_0_green_seconds']}s, "
            f"P2(EW)={rd['phase_2_green_seconds']}s | Control: {ctrl_mode} | Overridden: {multi_ctrl.has_active_emergency(iid)}"
        )
    print("-" * 79)

    # 8. Evaluation Metrics for Phase K
    print("\nStep 7: Corridor Metrics (Recorded for Phase K Experimental Evaluation)")
    print("-" * 79)
    if final_plan.metrics:
        m = final_plan.metrics
        print(f"  Emergency Vehicle ID         : {m.emergency_vehicle_id}")
        print(f"  Corridor Route               : {' -> '.join(m.route)}")
        print(f"  Intersections Affected       : {m.intersections_affected}")
        print(f"  Signal Overrides Applied     : {m.signal_overrides_count}")
        print(f"  Activation Duration          : {m.corridor_activation_duration:.1f} s")
        print(f"  Measured Emergency Travel Time: {m.emergency_travel_time:.1f} s")
        print(f"  Baseline Estimated Travel Time: {m.baseline_estimated_travel_time:.1f} s")
        if m.baseline_estimated_travel_time > 0 and m.emergency_travel_time > 0:
            diff = m.baseline_estimated_travel_time - m.emergency_travel_time
            print(f"  Time Saved vs Baseline Delay : {diff:.1f} s (Experimental benchmark data)")
    print("-" * 79)
    print("\nEmergency Green Corridor demo completed successfully!")


if __name__ == "__main__":
    main()
