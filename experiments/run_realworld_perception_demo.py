"""End-to-end demo for Phase M: Real-World Prototype Interface.

Demonstrates processing media (images, videos, synthetic frames) through:
Media -> YOLOv8 -> Tracking -> Aggregation -> Queue Estimation ->
TrafficObservation -> IntersectionTrafficState -> QUBO Optimization ->
Prototype Signal Recommendation.

Usage:
    python experiments/run_realworld_perception_demo.py
    python experiments/run_realworld_perception_demo.py --source path/to/image.jpg --type image
    python experiments/run_realworld_perception_demo.py --source path/to/video.mp4 --type video --frames 20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import time

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import cv2
import numpy as np

from perception.service import (
    HARDWARE_DISCLAIMER,
    PERCEPTION_DISCLAIMER,
    PerceptionConfig,
    RealWorldPerceptionService,
    SourceType,
)


def create_synthetic_traffic_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Generate a synthetic road intersection frame with rendered vehicles for deterministic testing."""
    # Dark asphalt background
    frame = np.full((height, width, 3), 35, dtype=np.uint8)

    # Draw intersection roads
    # North-South road
    cv2.rectangle(frame, (220, 0), (420, height), (50, 50, 50), -1)
    # East-West road
    cv2.rectangle(frame, (0, 160), (width, 320), (50, 50, 50), -1)

    # Center junction box
    cv2.rectangle(frame, (220, 160), (420, 320), (45, 45, 45), -1)

    # Road lane markings
    cv2.line(frame, (320, 0), (320, 160), (200, 200, 200), 2)
    cv2.line(frame, (320, 320), (320, height), (200, 200, 200), 2)
    cv2.line(frame, (0, 240), (220, 240), (200, 200, 200), 2)
    cv2.line(frame, (420, 240), (width, 240), (200, 200, 200), 2)

    # Draw several synthetic vehicle rectangles
    # North queue
    cv2.rectangle(frame, (240, 40), (290, 90), (0, 180, 255), -1)  # Car
    cv2.putText(frame, "CAR", (245, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.rectangle(frame, (240, 105), (290, 150), (0, 220, 180), -1)  # Car
    # South queue
    cv2.rectangle(frame, (350, 340), (400, 390), (0, 180, 255), -1)  # Car
    # East queue
    cv2.rectangle(frame, (440, 250), (510, 300), (255, 120, 50), -1)  # Bus
    cv2.putText(frame, "BUS", (455, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    # West queue
    cv2.rectangle(frame, (120, 180), (190, 230), (180, 50, 255), -1)  # Truck
    cv2.putText(frame, "TRUCK", (130, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    return frame


def create_synthetic_traffic_video(output_path: Path, num_frames: int = 15, fps: float = 10.0) -> Path:
    """Generate a multi-frame synthetic video for video perception testing."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    try:
        for i in range(num_frames):
            frame = create_synthetic_traffic_frame(width, height)
            # Add motion to one vehicle
            offset_y = int(i * 3)
            cv2.rectangle(frame, (340, min(140, 20 + offset_y)), (390, min(190, 70 + offset_y)), (100, 255, 100), -1)
            out.write(frame)
    finally:
        out.release()

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowQ Phase M Real-World Perception Demo")
    parser.add_argument("--source", type=str, default=None, help="Path to image or video file, or camera index / RTSP URL")
    parser.add_argument("--type", type=str, choices=["image", "video", "camera", "rtsp"], default=None, help="Input source type")
    parser.add_argument("--intersection", type=str, default="J1", help="Intersection identifier (e.g. J1..J8)")
    parser.add_argument("--solver", type=str, choices=["exact", "qaoa"], default="exact", help="Signal optimizer solver")
    parser.add_argument("--frames", type=int, default=10, help="Max frames to process for video")
    parser.add_argument("--sampling", type=int, default=1, help="Frame sampling rate")
    args = parser.parse_args()

    print("=" * 70)
    print(" FlowQ: Quantum-Enhanced Adaptive Urban Traffic Optimization")
    print(" Phase M — Real-World Prototype Perception Demo")
    print("=" * 70)

    # Define standard 4-way approach regions for 640x480 frame
    approach_rois = {
        "north": [200.0, 0.0, 440.0, 200.0],
        "south": [200.0, 280.0, 440.0, 480.0],
        "east": [380.0, 140.0, 640.0, 340.0],
        "west": [0.0, 140.0, 260.0, 340.0],
    }

    service = RealWorldPerceptionService(approach_regions=approach_rois)
    source_path = args.source
    source_type = args.type

    # Real-media verification check (Requirement 17)
    if source_path is None:
        print("\n[Notice] No external media specified via --source.")
        print("[Notice] Checking project workspace for pre-existing media files...")
        existing_images = list(WORKSPACE_ROOT.glob("**/*.jpg")) + list(WORKSPACE_ROOT.glob("**/*.png"))
        existing_videos = list(WORKSPACE_ROOT.glob("**/*.mp4"))

        if existing_images and not source_type:
            source_path = str(existing_images[0])
            source_type = "image"
            print(f"[Real Media Found] Using existing image: {source_path}")
        elif existing_videos and not source_type:
            source_path = str(existing_videos[0])
            source_type = "video"
            print(f"[Real Media Found] Using existing video: {source_path}")
        else:
            print("[Info] No real camera/video media existed originally in repository.")
            print("[Action] Generating deterministic synthetic test media for verification...")
            synth_dir = WORKSPACE_ROOT / "data" / "synthetic"
            synth_dir.mkdir(parents=True, exist_ok=True)
            synth_image_path = synth_dir / "sample_traffic_frame.jpg"

            synth_frame = create_synthetic_traffic_frame()
            cv2.imwrite(str(synth_image_path), synth_frame)
            source_path = str(synth_image_path)
            source_type = "image"
            print(f"[Created Synthetic Media] Saved sample to: {synth_image_path}")

    if source_type is None:
        p = Path(source_path)
        if p.suffix.lower() in (".mp4", ".avi", ".mov", ".mkv"):
            source_type = "video"
        else:
            source_type = "image"

    print(f"\n[Configuration]")
    print(f"  Source Type:    {source_type}")
    print(f"  Source Path:    {source_path}")
    print(f"  Intersection:   {args.intersection}")
    print(f"  Solver:         {args.solver.upper()}")
    print(f"  Approach ROIs:  {list(approach_rois.keys())}")

    # Process media through perception pipeline
    print(f"\n[Pipeline Step 1] Ingesting media and running YOLOv8 detection...")
    start_t = time()

    if source_type == "image":
        observation = service.process_image(
            source=source_path,
            intersection_id=args.intersection,
            approach_regions=approach_rois,
        )
    elif source_type == "video":
        observations = service.process_video(
            video_path=source_path,
            intersection_id=args.intersection,
            frame_sampling_rate=args.sampling,
            approach_regions=approach_rois,
            max_frames=args.frames,
        )
        observation = observations[-1] if observations else None
        print(f"  Processed {len(observations)} video frames.")
    else:
        raise ValueError(f"Unsupported demo source type: {source_type}")

    proc_time = (time() - start_t) * 1000.0
    print(f"  Perception completed in {proc_time:.2f} ms.")

    if observation is None:
        print("[Error] No observation generated.")
        return

    # Print canonical TrafficObservation summary
    print(f"\n[Pipeline Step 2] Canonical TrafficObservation Generated:")
    print(f"  Timestamp:         {observation.timestamp:.3f}")
    print(f"  Source Label:      {observation.source}")
    print(f"  Intersection ID:   {observation.intersection_id}")
    print(f"  Total Vehicles:    {observation.vehicle_count}")
    print(f"  Tracked Vehicles:  {observation.tracked_vehicle_count}")
    print(f"  Avg Confidence:    {observation.average_confidence * 100:.1f}%")
    print(f"  Approach Counts:   {observation.approach_counts}")
    print(f"  Approach Queues:   {observation.queue_lengths}")
    print(f"  Class Breakdown:   {observation.class_counts}")

    # Pipeline Step 3: Optimization & Signal Timing Recommendation
    print(f"\n[Pipeline Step 3] Solving QUBO for Prototype Signal Recommendation...")
    opt_start = time()
    recommendation = service.recommend_signal_timing(
        observation=observation,
        solver=args.solver,
        road_capacity=100,
    )
    opt_time = (time() - opt_start) * 1000.0

    print(f"  QUBO optimization completed in {opt_time:.2f} ms.")
    print(f"\n" + "-" * 70)
    print(f" PROTOTYPE SIGNAL RECOMMENDATION")
    print(f"-" * 70)
    print(f"  Intersection:          {recommendation['intersection_id']}")
    print(f"  Algorithm / Solver:    {recommendation['method']} ({recommendation['solver']})")
    print(f"  Phase 0 Green (NS):    {recommendation['phase_0_green_seconds']} s")
    print(f"  Phase 2 Green (EW):    {recommendation['phase_2_green_seconds']} s")
    print(f"  Yellow Interval:       {recommendation['yellow_seconds']} s")
    print(f"  Total Cycle Length:    {recommendation['cycle_length_seconds']} s")
    print(f"  QUBO Objective Score:  {recommendation['objective']:.6f}")
    print(f"  Valid Timing Plan:     {recommendation['valid']}")
    print(f"\n[Research & Safety Disclaimers]")
    print(f"  * Hardware:   {recommendation['hardware_disclaimer']}")
    print(f"  * Perception: {recommendation['perception_disclaimer']}")
    print("=" * 70)
    print(" Phase M Demo Completed Successfully.")
    print("=" * 70)


if __name__ == "__main__":
    main()
