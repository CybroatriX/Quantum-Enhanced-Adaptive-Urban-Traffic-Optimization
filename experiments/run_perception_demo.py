import json
import sys
from pathlib import Path
from time import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.loader import load_config
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.aggregator import TrafficAggregator
from perception.models import VehicleDetection


def main() -> None:
    print("=== FlowQ Phase E: Tracking & Traffic Aggregation Demo ===\n")
    config = load_config()

    # 1. Define configurable approach ROIs
    approach_rois = {
        "north": [100.0, 0.0, 300.0, 200.0],
        "south": [100.0, 300.0, 300.0, 500.0],
        "east": [350.0, 150.0, 550.0, 350.0],
        "west": [0.0, 150.0, 80.0, 350.0],
    }
    aggregator = TrafficAggregator(approach_regions=approach_rois)

    # 2. Simulate raw vehicle detections from YOLO tracking
    print("1. Ingesting synthetic vehicle detections with track IDs...")
    detections = [
        # North approach
        VehicleDetection("car", 0.94, (120, 30, 160, 80), (140, 55), track_id=1),
        VehicleDetection("car", 0.89, (180, 50, 220, 100), (200, 75), track_id=2),
        VehicleDetection("bus", 0.96, (130, 110, 190, 180), (160, 145), track_id=3),
        # South approach
        VehicleDetection("car", 0.91, (140, 320, 180, 370), (160, 345), track_id=4),
        VehicleDetection("motorcycle", 0.82, (210, 340, 230, 380), (220, 360), track_id=5),
        # East approach
        VehicleDetection("truck", 0.88, (380, 200, 440, 260), (410, 230), track_id=6),
        # West approach
        VehicleDetection("car", 0.87, (20, 210, 60, 260), (40, 235), track_id=7),
    ]

    # 3. Aggregate into TrafficObservation
    print("2. Aggregating detections into TrafficObservation...")
    obs = aggregator.aggregate(detections, intersection_id="J1", timestamp=time(), source="yolov8")

    obs_summary = {
        "intersection_id": obs.intersection_id,
        "source": obs.source,
        "vehicle_count": obs.vehicle_count,
        "tracked_vehicle_count": obs.tracked_vehicle_count,
        "average_confidence": obs.average_confidence,
        "approach_counts": obs.approach_counts,
        "class_counts": obs.class_counts,
    }
    print("TrafficObservation Summary:\n", json.dumps(obs_summary, indent=2))

    # 4. Convert to canonical IntersectionTrafficState
    print("\n3. Converting TrafficObservation to canonical IntersectionTrafficState...")
    state = obs.to_intersection_traffic_state(road_capacity=100)
    print(f"State: ID={state.intersection_id}, Count={state.vehicle_count}, Queues={state.green_phase_queues}")

    # 5. Optimize with canonical QUBO exact solver
    print("\n4. Optimizing signal timing using canonical QUBO exact solver...")
    model = build_qubo(state, config["optimization"]["phase3a"])
    solution = solve_exact(model)
    candidate = solution.candidate

    print(f"\nOptimization Result:")
    print(f"  Phase 0 (North/South) Green: {candidate.first_green_seconds}s")
    print(f"  Phase 2 (East/West) Green:   {candidate.second_green_seconds}s")
    print(f"  QUBO Objective:             {solution.objective_value:.6f}")
    print(f"  Valid Candidate:            {candidate.valid}")
    print("\n=== End of Demo ===")


if __name__ == "__main__":
    main()
