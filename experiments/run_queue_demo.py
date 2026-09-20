"""Phase F Demo: Detections -> Tracking -> Queue Estimation -> QUBO Optimization."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.loader import load_config
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.aggregator import TrafficAggregator
from perception.models import VehicleDetection
from perception.queue_estimator import QueueEstimator


def main() -> None:
    print("=== FlowQ Phase F: Motion-Based Queue Estimation Demo ===\n")
    config = load_config()

    # 1. Configurable Approach Regions
    approach_rois = {
        "north": [100.0, 0.0, 300.0, 250.0],
        "south": [100.0, 300.0, 300.0, 550.0],
        "east": [350.0, 150.0, 600.0, 400.0],
        "west": [0.0, 150.0, 80.0, 400.0],
    }

    # 2. Configurable Queue Estimator Thresholds
    queue_estimator = QueueEstimator(
        stopped_speed_threshold=5.0,   # px/s
        slow_speed_threshold=15.0,     # px/s
        include_slow_in_queue=True,
    )

    aggregator = TrafficAggregator(
        approach_regions=approach_rois,
        queue_estimator=queue_estimator,
    )

    # 3. Frame 1 at t=0.0
    print("1. Observing Frame 1 (t=0.0s): initial vehicle positions...")
    frame_1 = [
        # North approach (waiting at signal)
        VehicleDetection("car", 0.92, (150, 80, 190, 130), (170, 105), track_id=1),
        VehicleDetection("car", 0.88, (150, 140, 190, 190), (170, 165), track_id=2),
        VehicleDetection("bus", 0.95, (150, 200, 200, 250), (175, 225), track_id=3),
        # East approach (free flow)
        VehicleDetection("car", 0.90, (380, 200, 420, 250), (400, 225), track_id=4),
        VehicleDetection("truck", 0.89, (450, 200, 500, 260), (475, 230), track_id=5),
        # South approach (crawling)
        VehicleDetection("car", 0.85, (160, 350, 200, 400), (180, 375), track_id=6),
    ]
    aggregator.aggregate(frame_1, intersection_id="J1", timestamp=0.0)

    # 4. Frame 2 at t=1.0s: motion displacement
    print("2. Observing Frame 2 (t=1.0s): calculating velocities & queue status...")
    frame_2 = [
        # North: Track 1, 2, 3 stayed stationary (stopped in queue)
        VehicleDetection("car", 0.92, (150, 80, 190, 130), (170, 105), track_id=1),   # dy=0 px/s -> STOPPED
        VehicleDetection("car", 0.88, (150, 81, 190, 131), (170, 106), track_id=2),   # dy=1 px/s -> STOPPED
        VehicleDetection("bus", 0.95, (150, 200, 200, 250), (175, 225), track_id=3),  # dy=0 px/s -> STOPPED
        # East: Track 4 and 5 cruising fast (dx=35 px/s and 40 px/s -> MOVING)
        VehicleDetection("car", 0.90, (415, 200, 455, 250), (435, 225), track_id=4),  # dx=35 px/s -> MOVING
        VehicleDetection("truck", 0.89, (490, 200, 540, 260), (515, 230), track_id=5), # dx=40 px/s -> MOVING
        # South: Track 6 crawling slowly (dy=8 px/s -> SLOW)
        VehicleDetection("car", 0.85, (160, 358, 200, 408), (180, 383), track_id=6),  # dy=8 px/s -> SLOW
    ]
    obs = aggregator.aggregate(frame_2, intersection_id="J1", timestamp=1.0)

    print("\n3. Generated TrafficObservation:")
    summary = {
        "intersection_id": obs.intersection_id,
        "total_vehicles": obs.vehicle_count,
        "approach_counts": obs.approach_counts,
        "queue_lengths": obs.queue_lengths,
        "class_counts": obs.class_counts,
        "tracked_vehicle_count": obs.tracked_vehicle_count,
        "average_confidence": obs.average_confidence,
    }
    print(json.dumps(summary, indent=2))

    # 5. Convert to canonical IntersectionTrafficState
    state = obs.to_intersection_traffic_state(road_capacity=100)
    print(f"\n4. Converted IntersectionTrafficState:")
    print(f"  Intersection: {state.intersection_id}")
    print(f"  Vehicle Count: {state.vehicle_count}")
    print(f"  Estimated Green Queues: {state.green_phase_queues}")
    print(f"    - Phase 0 (North+South Queues): {state.green_phase_queues[0][1]}")
    print(f"    - Phase 2 (East+West Queues):   {state.green_phase_queues[1][1]}")

    # 6. Optimize with canonical QUBO solver
    print("\n5. Running Canonical Exact QUBO Solver...")
    model = build_qubo(state, config["optimization"]["phase3a"])
    solution = solve_exact(model)
    cand = solution.candidate

    print(f"\nOptimization Result:")
    print(f"  Phase 0 (North/South) Green Duration: {cand.first_green_seconds}s")
    print(f"  Phase 2 (East/West) Green Duration:   {cand.second_green_seconds}s")
    print(f"  QUBO Objective Cost:                 {solution.objective_value:.6f}")
    print(f"  Plan Validity:                        {cand.valid}")
    print("\n=== End of Phase F Demo ===")


if __name__ == "__main__":
    main()
