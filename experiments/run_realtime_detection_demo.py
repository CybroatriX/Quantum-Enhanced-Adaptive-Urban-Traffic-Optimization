"""Real-time camera vehicle and pedestrian detection CLI demonstration.

Demonstrates live detection and tracking of vehicles (car, motorcycle, bus, truck)
and pedestrians (person) using Ultralytics YOLOv8n. Signal control is explicitly
disabled and the optimization pipeline is never called.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2

from perception.detector import YOLOVehicleDetector
from perception.models import TrafficObservation


def run_demo(
    source_type: str = "camera",
    camera_index: int = 0,
    video_source: str | None = None,
    confidence_threshold: float = 0.35,
    max_frames: int | None = None,
    duration_seconds: float | None = None,
    intersection_id: str = "J1",
) -> int:
    print("=" * 60)
    print("REAL-TIME DETECTION DEMO")
    print("=" * 60)

    source_label = f"Webcam {camera_index}" if source_type == "camera" else f"Video ({video_source})"
    print(f"Source: {source_label}")

    detector = YOLOVehicleDetector(
        model_name="yolov8n.pt",
        confidence_threshold=confidence_threshold,
    )

    yolo_model = detector._load_model()
    yolo_status = "ready" if yolo_model is not None else "fallback"
    print(f"YOLOv8: {yolo_status}")
    print(f"Tracking: active")
    print(f"Signal Control: DISABLED")
    print("-" * 60)

    cap = None
    try:
        if source_type == "video":
            if not video_source or not Path(video_source).exists():
                print(f"Error: Video file not found: {video_source}")
                return 1
            cap = cv2.VideoCapture(video_source)
        else:
            cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            print(f"Error: Unable to open {source_label}.")
            print("Physical real-time camera verification was not available.")
            return 1

        frame_count = 0
        start_time = time.time()
        last_obs: TrafficObservation | None = None

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                if source_type == "video":
                    # Finished video
                    break
                else:
                    print("Warning: Failed to capture camera frame.")
                    break

            frame_count += 1
            now = time.time()

            obs = detector.detect(
                source=frame,
                intersection_id=intersection_id,
                track=True,
                timestamp=now,
                detect_pedestrians=True,
            )
            last_obs = obs

            total_tracked = obs.tracked_vehicle_count + obs.tracked_pedestrian_count

            # Continuous report
            print(
                f"[Frame {frame_count:04d}] "
                f"Vehicles: {obs.vehicle_count} (Car: {obs.class_counts.get('car', 0)}, "
                f"Moto: {obs.class_counts.get('motorcycle', 0)}, "
                f"Bus: {obs.class_counts.get('bus', 0)}, "
                f"Truck: {obs.class_counts.get('truck', 0)}) | "
                f"Pedestrians: {obs.pedestrian_count} | "
                f"Tracked: {total_tracked} | "
                f"Avg Conf: {obs.average_confidence:.1%}"
            )

            if max_frames is not None and frame_count >= max_frames:
                break
            if duration_seconds is not None and (now - start_time) >= duration_seconds:
                break

            time.sleep(0.05)

        print("-" * 60)
        print("REAL-TIME DETECTION DEMO SUMMARY")
        print("-" * 60)
        if last_obs is not None:
            cc = last_obs.class_counts
            total_tracked = last_obs.tracked_vehicle_count + last_obs.tracked_pedestrian_count
            print("Vehicles:")
            print(f"  Car: {cc.get('car', 0)}")
            print(f"  Motorcycle: {cc.get('motorcycle', 0)}")
            print(f"  Bus: {cc.get('bus', 0)}")
            print(f"  Truck: {cc.get('truck', 0)}")
            print(f"Total Vehicles: {last_obs.vehicle_count}")
            print(f"Pedestrians: {last_obs.pedestrian_count}")
            print(f"Tracked Entities: {total_tracked}")
            print(f"Average Confidence: {last_obs.average_confidence:.1%}")
            print("Signal Control: DISABLED")
        else:
            print("No frames were processed.")

        print("=" * 60)
        return 0

    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
        return 0
    except Exception as exc:
        print(f"Demo error: {exc}")
        return 1
    finally:
        if cap is not None:
            cap.release()
            print("Camera hardware released cleanly.")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowQ Real-Time Detection Demo")
    parser.add_argument("--camera", type=int, default=None, help="Webcam device index (e.g. 0, 1)")
    parser.add_argument("--source", type=str, default=None, help="Video file path or source")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold (0.0 - 1.0)")
    parser.add_argument("--max-frames", type=int, default=15, help="Maximum number of frames to run")
    parser.add_argument("--duration", type=float, default=None, help="Run duration in seconds")
    parser.add_argument("--intersection", type=str, default="J1", help="Target intersection ID")

    args = parser.parse_args()

    if args.source is not None:
        source_type = "video"
        video_source = args.source
        cam_idx = 0
    else:
        source_type = "camera"
        cam_idx = args.camera if args.camera is not None else 0
        video_source = None

    sys.exit(
        run_demo(
            source_type=source_type,
            camera_index=cam_idx,
            video_source=video_source,
            confidence_threshold=args.conf,
            max_frames=args.max_frames,
            duration_seconds=args.duration,
            intersection_id=args.intersection,
        )
    )


if __name__ == "__main__":
    main()
