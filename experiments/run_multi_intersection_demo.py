"""Phase H Demo: Multi-Intersection Control Pipeline.

Demonstrates:
  4 Connected TrafficObservations (J1, J2, J3, J4)
              ↓
  MultiIntersectionController
              ↓
  J1 timing | J2 timing | J3 timing | J4 timing
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from perception.models import TrafficObservation, VehicleDetection
from simulation.signals.multi_intersection import MultiIntersectionController


def make_demo_obs(
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
    print("=======================================================================")
    print("  FlowQ Phase H: Multi-Intersection Control (J1 - J4 Network Demo)")
    print("=======================================================================\n")

    # 1. Initialize MultiIntersectionController managing 4 intersections
    controller = MultiIntersectionController(
        managed_intersection_ids=["J1", "J2", "J3", "J4"],
        max_observation_age_seconds=30.0,
        anti_oscillation_damping_seconds=0.0,
        default_solver="exact",
    )

    # 2. Synthesize 4 distinct TrafficObservations
    # J1: Heavy North/South corridor (commuter arterial)
    # J2: Heavy East/West cross-avenue (cross-traffic surge)
    # J3: Balanced demand across all 4 approaches
    # J4: Asymmetric moderate North-bound bias
    observations = [
        make_demo_obs("J1", north_q=16, south_q=10, east_q=1, west_q=1),
        make_demo_obs("J2", north_q=1, south_q=1, east_q=18, west_q=12),
        make_demo_obs("J3", north_q=3, south_q=3, east_q=3, west_q=3),
        make_demo_obs("J4", north_q=9, south_q=5, east_q=2, west_q=1),
    ]

    print("1. Ingesting 4 Canonical TrafficObservations:")
    for obs in observations:
        p0_q = obs.queue_lengths["north"] + obs.queue_lengths["south"]
        p2_q = obs.queue_lengths["east"] + obs.queue_lengths["west"]
        print(
            f"  [{obs.intersection_id}] Total Vehicles: {obs.vehicle_count:2d} | "
            f"Queues -> N:{obs.queue_lengths['north']:2d}, S:{obs.queue_lengths['south']:2d} (P0={p0_q:2d}) | "
            f"E:{obs.queue_lengths['east']:2d}, W:{obs.queue_lengths['west']:2d} (P2={p2_q:2d})"
        )

    # 3. Optimize through MultiIntersectionController
    print("\n2. Executing MultiIntersectionController.optimize_observations()...\n")
    decisions = controller.optimize_observations(observations, current_time=1789840200.0)

    # 4. Display Results
    print("-" * 75)
    print(f"{'Intersection':<14} | {'Vehicles':<8} | {'Queues (P0/P2)':<15} | {'Phase 0':<9} | {'Phase 2':<9} | {'Objective':<10} | {'Solver':<6} | {'Valid'}")
    print("-" * 75)

    for obs in observations:
        iid = obs.intersection_id
        d = decisions[iid]
        p0_q = obs.queue_lengths["north"] + obs.queue_lengths["south"]
        p2_q = obs.queue_lengths["east"] + obs.queue_lengths["west"]
        q_str = f"{p0_q} / {p2_q}"
        p0_str = f"{d['phase_0_green_seconds']}s"
        p2_str = f"{d['phase_2_green_seconds']}s"
        obj_str = f"{d['objective']:.4f}"
        print(
            f"{iid:<14} | {obs.vehicle_count:<8} | {q_str:<15} | {p0_str:<9} | {p2_str:<9} | {obj_str:<10} | {d['solver']:<6} | {d['valid']}"
        )
    print("-" * 75)

    print("\n3. Controller Persistent Intersection State Records:")
    records = controller.get_all_intersection_records()
    for iid, rec in sorted(records.items()):
        print(f"  [{iid}] Status: {rec.status} | Density: {rec.traffic_density:.4f} | Optimal Timings: P0={rec.phase_0_green_seconds}s, P2={rec.phase_2_green_seconds}s")

    print("\nMulti-intersection optimization complete and validated!")


if __name__ == "__main__":
    main()
