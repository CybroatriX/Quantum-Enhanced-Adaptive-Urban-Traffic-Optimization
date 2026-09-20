"""Phase G Demo: Common TrafficObservation Contract Pipeline.

Demonstrates:
  SUMO / YOLO input
          ↓
  TrafficObservation (canonical schema)
          ↓
  IntersectionTrafficState
          ↓
  Optimization API (/api/optimize)
          ↓
  QUBO solver
          ↓
  Signal timing
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.loader import load_config
from optimization.service import create_app
from perception.models import TrafficObservation, VehicleDetection
from simulation.models.state import IntersectionTrafficState, SignalState


def run_pipeline(title: str, observation: TrafficObservation) -> None:
    print(f"--- Pipeline: {title} ---")
    print(f"Source: {observation.source} | Intersection: {observation.intersection_id}")
    print(f"Total Vehicles: {observation.vehicle_count} | Tracked: {observation.tracked_vehicle_count}")
    print(f"Approach Counts: {observation.approach_counts}")
    print(f"Queue Lengths:   {observation.queue_lengths}")
    print(f"Class Counts:    {observation.class_counts}")

    # 1. JSON Contract serialization
    json_payload = observation.to_json(indent=2, include_detections=False)
    print("\n1. Canonical TrafficObservation JSON Contract:")
    print(json_payload)

    # 2. Convert to IntersectionTrafficState
    traffic_state = observation.to_intersection_traffic_state(road_capacity=100)
    print("\n2. Converted IntersectionTrafficState:")
    print(f"  Intersection ID:     {traffic_state.intersection_id}")
    print(f"  Vehicle Count:       {traffic_state.vehicle_count}")
    print(f"  Total Queue:         {traffic_state.queue_length}")
    print(f"  Traffic Density:     {traffic_state.traffic_density}")
    print(f"  Green Phase Queues:  {traffic_state.green_phase_queues}")

    # 3. Optimization API consumption
    app = create_app()
    with app.test_client() as client:
        response = client.post("/api/optimize", json=observation.to_dict())
        decision = response.get_json()

    print("\n3. Optimization API & QUBO Solver Decision:")
    print(f"  Phase 0 (North/South) Green: {decision['phase_0_green_seconds']}s")
    print(f"  Phase 2 (East/West) Green:   {decision['phase_2_green_seconds']}s")
    print(f"  QUBO Objective Cost:         {decision['objective']}")
    print(f"  Timing Plan Valid:           {decision['valid']}")
    print("-" * 55 + "\n")


def main() -> None:
    print("=======================================================")
    print("  FlowQ Phase G: Common TrafficObservation Contract")
    print("=======================================================\n")

    # Pipeline A: YOLO Perception Input
    yolo_detections = (
        VehicleDetection("car", 0.94, (120, 50, 160, 100), (140, 75), track_id=1),
        VehicleDetection("car", 0.89, (120, 110, 160, 160), (140, 135), track_id=2),
        VehicleDetection("bus", 0.96, (120, 170, 170, 230), (145, 200), track_id=3),
        VehicleDetection("truck", 0.91, (350, 180, 410, 240), (380, 210), track_id=4),
        VehicleDetection("motorcycle", 0.85, (360, 250, 390, 290), (375, 270), track_id=5),
    )
    yolo_obs = TrafficObservation(
        timestamp=1789840100.0,
        source="yolov8",
        intersection_id="J1",
        vehicle_count=5,
        approach_counts={"north": 3, "south": 0, "east": 2, "west": 0},
        queue_lengths={"north": 3, "south": 0, "east": 1, "west": 0},
        class_counts={"car": 2, "bus": 1, "truck": 1, "motorcycle": 1},
        detections=yolo_detections,
        tracking_available=True,
        tracked_vehicle_count=5,
        average_confidence=0.91,
    )
    run_pipeline("YOLOv8 Real-Time Perception", yolo_obs)

    # Pipeline B: SUMO Simulation Input
    sumo_state = IntersectionTrafficState(
        intersection_id="J2",
        vehicle_count=18,
        queue_length=11,
        traffic_density=0.18,
        road_capacity=100,
        signal_state=SignalState.GREEN,
        signal_phase=0,
        green_phase_queues=((0, 8), (2, 3)),
    )
    sumo_obs = TrafficObservation.from_intersection_traffic_state(
        sumo_state, source="sumo", timestamp=1789840101.0
    )
    run_pipeline("SUMO Simulation State Reader", sumo_obs)

    print("Canonical contract successfully unified perception and simulation inputs!")


if __name__ == "__main__":
    main()
