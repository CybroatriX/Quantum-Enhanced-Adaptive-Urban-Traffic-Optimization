"""Real-world perception service layer for camera, video, image, and RTSP stream processing.

Integrates YOLOv8 vehicle detection, multi-object tracking, approach ROI aggregation,
and prototype queue estimation into canonical TrafficObservation contracts and prototype
signal timing recommendations.

NOTE: This is a research/prototype interface. Detection and queue estimates depend on
camera placement, calibration, visibility, detection confidence, tracking quality,
weather, lighting, occlusion, and other environmental factors.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from enum import Enum
import io
import json
import logging
from pathlib import Path
import re
from time import time
from typing import Any, Generator, Mapping, Sequence
from urllib.parse import urlparse, urlunparse

import numpy as np

from config.loader import load_config
from optimization.quantum.qaoa import run_qaoa
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.aggregator import TrafficAggregator
from perception.detector import YOLOVehicleDetector
from perception.models import TrafficObservation, VALID_APPROACHES, VALID_VEHICLE_CLASSES, VehicleDetection
from perception.queue_estimator import QueueEstimator
from simulation.models.state import IntersectionTrafficState

logger = logging.getLogger(__name__)

# Supported image and video file extensions
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

HARDWARE_DISCLAIMER = (
    "This is a research/prototype signal timing recommendation for simulation and analysis. "
    "It does not directly interface with physical traffic light hardware."
)
PERCEPTION_DISCLAIMER = (
    "This is a research/prototype interface. Detection and queue estimates depend on "
    "camera placement, calibration, visibility, detection confidence, tracking quality, "
    "weather, lighting, occlusion, and other environmental factors."
)


def sanitize_rtsp_url(url: str) -> str:
    """Mask credentials in an RTSP URL for safe logging and telemetry display.

    Example:
        rtsp://admin:secret123@192.168.1.100:554/stream -> rtsp://admin:***@192.168.1.100:554/stream
    """
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            sanitized = urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
            return sanitized
        # Regex fallback for non-standard schemes or partial URLs
        return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)
    except Exception:
        return "rtsp://***"


class SourceType(str, Enum):
    """Supported real-world perception input source types."""

    IMAGE = "image"
    VIDEO = "video"
    CAMERA = "camera"
    RTSP = "rtsp"
    SYNTHETIC = "synthetic"


@dataclass
class PerceptionConfig:
    """Configuration for real-world perception and camera intersection mapping."""

    intersection_id: str = "J1"
    source_type: str = SourceType.IMAGE.value
    source_path: str | None = None
    camera_index: int = 0
    rtsp_url: str | None = None
    model_name: str = "yolov8n.pt"
    confidence_threshold: float = 0.35
    device: str | None = None
    track: bool = True
    frame_sampling_rate: int = 1
    road_capacity: int = 100
    approach_regions: dict[str, Any] | None = None
    stopped_speed_threshold: float = 5.0
    slow_speed_threshold: float = 15.0
    rtsp_timeout_seconds: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("rtsp_url"):
            d["rtsp_url"] = sanitize_rtsp_url(d["rtsp_url"])
        return d


class RealWorldPerceptionService:
    """Service layer managing camera feeds, video processing, image detection, and signal recommendations."""

    def __init__(
        self,
        config: PerceptionConfig | None = None,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.35,
        device: str | None = None,
        approach_regions: Mapping[str, Any] | None = None,
    ) -> None:
        self.config = config or PerceptionConfig(
            model_name=model_name,
            confidence_threshold=confidence_threshold,
            device=device,
            approach_regions=dict(approach_regions) if approach_regions else None,
        )
        self.detector = YOLOVehicleDetector(
            model_name=self.config.model_name,
            confidence_threshold=self.config.confidence_threshold,
            device=self.config.device,
            approach_regions=self.config.approach_regions,
        )

    # -------------------------------------------------------------------------
    # Image Mode
    # -------------------------------------------------------------------------

    def process_image(
        self,
        source: str | Path | np.ndarray | Any,
        intersection_id: str = "J1",
        approach_regions: Mapping[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> TrafficObservation:
        """Process a single image and produce a canonical TrafficObservation.

        Args:
            source: Image file path, numpy ndarray, or PIL Image.
            intersection_id: Target intersection identifier.
            approach_regions: Optional custom approach ROIs.
            timestamp: Optional observation timestamp.

        Returns:
            TrafficObservation with vehicle count, class counts, approach counts,
            and prototype queue estimates.
        """
        now = time() if timestamp is None else float(timestamp)

        # 1. Validate file extension if source is a path
        if isinstance(source, (str, Path)):
            path_obj = Path(source)
            if not path_obj.exists():
                raise FileNotFoundError(f"Image file not found: {source}")
            if path_obj.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                raise ValueError(
                    f"Unsupported image extension '{path_obj.suffix}'. "
                    f"Supported formats: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}"
                )

        # 2. Configure approach regions if supplied
        if approach_regions is not None:
            self.detector.aggregator.set_approach_regions(approach_regions)

        # 3. In single image mode, tracking history is absent.
        # Run detection without track persistence; QueueEstimator handles single-frame
        # observations safely using first_frame_default_state (prototype estimate).
        raw_obs = self.detector.detect(
            source=source,
            intersection_id=intersection_id,
            track=False,
            timestamp=now,
        )

        # 4. Canonical TrafficObservation enforces all 4 approaches and 4 classes
        obs = TrafficObservation(
            timestamp=raw_obs.timestamp,
            source=SourceType.IMAGE.value,
            intersection_id=intersection_id,
            vehicle_count=raw_obs.vehicle_count,
            tracked_vehicle_count=raw_obs.tracked_vehicle_count,
            average_confidence=raw_obs.average_confidence,
            approach_counts=raw_obs.approach_counts,
            queue_lengths=raw_obs.queue_lengths,
            class_counts=raw_obs.class_counts,
            detections=raw_obs.detections,
            tracking_available=False,
        )
        return obs

    # -------------------------------------------------------------------------
    # Video Mode
    # -------------------------------------------------------------------------

    def process_video(
        self,
        video_path: str | Path,
        intersection_id: str = "J1",
        frame_sampling_rate: int = 1,
        approach_regions: Mapping[str, Any] | None = None,
        max_frames: int | None = None,
        track: bool = True,
    ) -> list[TrafficObservation]:
        """Process a video file sequentially while preserving tracking across frames.

        Args:
            video_path: Path to video file.
            intersection_id: Target intersection identifier.
            frame_sampling_rate: Process every N-th frame (>= 1).
            approach_regions: Optional custom approach ROIs.
            max_frames: Optional upper limit on processed frames.
            track: Whether to enable multi-object tracking (MOT).

        Returns:
            List of TrafficObservation objects, one per sampled frame.
        """
        import cv2

        path_obj = Path(video_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if path_obj.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            raise ValueError(
                f"Unsupported video extension '{path_obj.suffix}'. "
                f"Supported formats: {sorted(SUPPORTED_VIDEO_EXTENSIONS)}"
            )

        if frame_sampling_rate < 1:
            raise ValueError("frame_sampling_rate must be at least 1.")

        if approach_regions is not None:
            self.detector.aggregator.set_approach_regions(approach_regions)

        cap = cv2.VideoCapture(str(path_obj))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {video_path}")

        observations: list[TrafficObservation] = []
        frame_idx = 0
        processed_count = 0
        start_time = time()

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            if fps <= 0:
                fps = 30.0

            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                if frame_idx % frame_sampling_rate == 0:
                    simulated_timestamp = start_time + (frame_idx / fps)
                    raw_obs = self.detector.detect(
                        source=frame,
                        intersection_id=intersection_id,
                        track=track,
                        timestamp=simulated_timestamp,
                    )
                    obs = TrafficObservation(
                        timestamp=simulated_timestamp,
                        source=SourceType.VIDEO.value,
                        intersection_id=intersection_id,
                        vehicle_count=raw_obs.vehicle_count,
                        tracked_vehicle_count=raw_obs.tracked_vehicle_count,
                        average_confidence=raw_obs.average_confidence,
                        approach_counts=raw_obs.approach_counts,
                        queue_lengths=raw_obs.queue_lengths,
                        class_counts=raw_obs.class_counts,
                        detections=raw_obs.detections,
                        tracking_available=track,
                    )
                    observations.append(obs)
                    processed_count += 1
                    if max_frames is not None and processed_count >= max_frames:
                        break

                frame_idx += 1
        finally:
            cap.release()

        return observations

    # -------------------------------------------------------------------------
    # Observation Exporters (JSON, JSONL, CSV)
    # -------------------------------------------------------------------------

    @staticmethod
    def export_observations(
        observations: Sequence[TrafficObservation],
        output_format: str = "json",
        output_path: str | Path | None = None,
    ) -> str:
        """Export a sequence of video/camera observations to JSON, JSONL, or CSV summary.

        Raw detection bounding boxes are omitted from summary exports to conserve space.
        """
        fmt = output_format.lower().strip()
        data_str = ""

        if fmt == "json":
            serializable = [obs.to_dict() for obs in observations]
            data_str = json.dumps(serializable, indent=2)
        elif fmt in ("jsonl", "ndjson"):
            lines = [json.dumps(obs.to_dict()) for obs in observations]
            data_str = "\n".join(lines)
        elif fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "timestamp",
                "source",
                "intersection_id",
                "vehicle_count",
                "tracked_vehicle_count",
                "average_confidence",
                "north_count",
                "south_count",
                "east_count",
                "west_count",
                "north_queue",
                "south_queue",
                "east_queue",
                "west_queue",
                "car_count",
                "motorcycle_count",
                "bus_count",
                "truck_count",
            ])
            for obs in observations:
                ac = obs.approach_counts
                ql = obs.queue_lengths
                cc = obs.class_counts
                writer.writerow([
                    obs.timestamp,
                    obs.source,
                    obs.intersection_id,
                    obs.vehicle_count,
                    obs.tracked_vehicle_count,
                    obs.average_confidence,
                    ac.get("north", 0),
                    ac.get("south", 0),
                    ac.get("east", 0),
                    ac.get("west", 0),
                    ql.get("north", 0),
                    ql.get("south", 0),
                    ql.get("east", 0),
                    ql.get("west", 0),
                    cc.get("car", 0),
                    cc.get("motorcycle", 0),
                    cc.get("bus", 0),
                    cc.get("truck", 0),
                ])
            data_str = output.getvalue()
        else:
            raise ValueError(f"Unsupported export format '{output_format}'. Supported: json, jsonl, csv.")

        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data_str, encoding="utf-8")

        return data_str

    # -------------------------------------------------------------------------
    # Webcam Mode
    # -------------------------------------------------------------------------

    def capture_camera_frame(
        self,
        camera_index: int = 0,
        intersection_id: str = "J1",
        approach_regions: Mapping[str, Any] | None = None,
    ) -> tuple[TrafficObservation | None, dict[str, Any]]:
        """Attempt to capture and process a single frame from a local webcam device.

        Returns:
            Tuple of (TrafficObservation or None, status_dictionary).
        """
        import cv2

        cap = None
        try:
            cap = cv2.VideoCapture(camera_index)
            if not cap.isOpened():
                return None, {
                    "status": "unavailable",
                    "camera_index": camera_index,
                    "error": f"Camera index {camera_index} is unavailable or failed to open.",
                }

            ret, frame = cap.read()
            if not ret or frame is None:
                return None, {
                    "status": "read_failed",
                    "camera_index": camera_index,
                    "error": f"Failed to read frame from camera index {camera_index}.",
                }

            if approach_regions is not None:
                self.detector.aggregator.set_approach_regions(approach_regions)

            raw_obs = self.detector.detect(
                source=frame,
                intersection_id=intersection_id,
                track=False,
                timestamp=time(),
            )
            obs = TrafficObservation(
                timestamp=raw_obs.timestamp,
                source=SourceType.CAMERA.value,
                intersection_id=intersection_id,
                vehicle_count=raw_obs.vehicle_count,
                tracked_vehicle_count=raw_obs.tracked_vehicle_count,
                average_confidence=raw_obs.average_confidence,
                approach_counts=raw_obs.approach_counts,
                queue_lengths=raw_obs.queue_lengths,
                class_counts=raw_obs.class_counts,
                detections=raw_obs.detections,
                tracking_available=False,
            )
            return obs, {"status": "connected", "camera_index": camera_index}

        except Exception as exc:
            logger.warning("Webcam capture failed: %s", exc)
            return None, {
                "status": "error",
                "camera_index": camera_index,
                "error": str(exc),
            }
        finally:
            if cap is not None:
                cap.release()

    # -------------------------------------------------------------------------
    # RTSP Stream Mode
    # -------------------------------------------------------------------------

    def capture_rtsp_frame(
        self,
        rtsp_url: str,
        intersection_id: str = "J1",
        timeout_seconds: float = 5.0,
        approach_regions: Mapping[str, Any] | None = None,
    ) -> tuple[TrafficObservation | None, dict[str, Any]]:
        """Attempt to connect to an RTSP stream and capture a single frame.

        Safeguards:
            Never logs or exposes plaintext RTSP credentials.
            Sets connection timeout to prevent hanging.
        """
        import cv2

        if not rtsp_url or not isinstance(rtsp_url, str) or not rtsp_url.strip():
            return None, {
                "status": "invalid_url",
                "error": "RTSP URL cannot be empty.",
            }

        sanitized_url = sanitize_rtsp_url(rtsp_url)
        logger.info("Attempting connection to RTSP stream: %s", sanitized_url)

        # Pre-flight socket reachability probe with user timeout to prevent OpenCV default 30s block
        parsed = urlparse(rtsp_url)
        host = parsed.hostname
        port = parsed.port or 554
        if host:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(min(float(timeout_seconds), 2.0))
            try:
                sock.connect((host, port))
                sock.close()
            except Exception as conn_err:
                sock.close()
                return None, {
                    "status": "unavailable",
                    "stream_url": sanitized_url,
                    "error": f"RTSP stream connection timed out or unreachable: {sanitized_url}",
                }

        cap = None
        try:
            # Configure OpenCV timeout where supported
            timeout_ms = int(max(1.0, timeout_seconds) * 1000)
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)

            if not cap.isOpened():
                return None, {
                    "status": "unavailable",
                    "stream_url": sanitized_url,
                    "error": f"RTSP stream connection timed out or unreachable: {sanitized_url}",
                }

            ret, frame = cap.read()
            if not ret or frame is None:
                return None, {
                    "status": "stream_read_failed",
                    "stream_url": sanitized_url,
                    "error": f"Failed to read frame from RTSP stream: {sanitized_url}",
                }

            if approach_regions is not None:
                self.detector.aggregator.set_approach_regions(approach_regions)

            raw_obs = self.detector.detect(
                source=frame,
                intersection_id=intersection_id,
                track=False,
                timestamp=time(),
            )
            obs = TrafficObservation(
                timestamp=raw_obs.timestamp,
                source=SourceType.RTSP.value,
                intersection_id=intersection_id,
                vehicle_count=raw_obs.vehicle_count,
                tracked_vehicle_count=raw_obs.tracked_vehicle_count,
                average_confidence=raw_obs.average_confidence,
                approach_counts=raw_obs.approach_counts,
                queue_lengths=raw_obs.queue_lengths,
                class_counts=raw_obs.class_counts,
                detections=raw_obs.detections,
                tracking_available=False,
            )
            return obs, {"status": "connected", "stream_url": sanitized_url}

        except Exception as exc:
            logger.warning("RTSP capture error on %s: %s", sanitized_url, exc)
            return None, {
                "status": "error",
                "stream_url": sanitized_url,
                "error": f"RTSP connection error: {exc}",
            }
        finally:
            if cap is not None:
                cap.release()

    # -------------------------------------------------------------------------
    # Optimization & Prototype Signal Recommendation
    # -------------------------------------------------------------------------

    def recommend_signal_timing(
        self,
        observation: TrafficObservation,
        solver: str = "exact",
        road_capacity: int = 100,
    ) -> dict[str, Any]:
        """Generate a Prototype Signal Recommendation from a TrafficObservation using canonical QUBO/QAOA.

        Pipeline:
            TrafficObservation
                    ↓
            IntersectionTrafficState
                    ↓
            build_qubo()
                    ↓
            solve_exact() / run_qaoa()
                    ↓
            Prototype Signal Recommendation
        """
        config = load_config()
        opt_cfg = config["optimization"]["phase3a"]
        qaoa_cfg = config.get("optimization", {}).get("phase3b", {})

        # Convert observation to canonical state
        state = observation.to_intersection_traffic_state(road_capacity=road_capacity)
        model = build_qubo(state, opt_cfg)

        solver_mode = solver.lower().strip()
        if solver_mode == "qaoa":
            sol = run_qaoa(model, qaoa_cfg)
            if sol.best_valid_solution is None:
                raise RuntimeError("QAOA did not produce a valid signal-timing candidate.")
            candidate = sol.best_valid_solution.candidate
            objective_val = sol.best_valid_solution.objective_value
            method_label = "QAOA research mode"
        else:
            sol = solve_exact(model)
            candidate = sol.candidate
            objective_val = sol.objective_value
            method_label = "QUBO exact"

        p0_green = candidate.first_green_seconds
        p2_green = candidate.second_green_seconds

        recommendation = {
            "recommendation_type": "Prototype Signal Recommendation",
            "intersection_id": observation.intersection_id,
            "source": observation.source,
            "solver": solver_mode,
            "method": method_label,
            "phase_0_green_seconds": p0_green,
            "phase_2_green_seconds": p2_green,
            "yellow_seconds": 4,
            "cycle_length_seconds": p0_green + p2_green + 8,
            "objective": round(float(objective_val), 6),
            "valid": candidate.valid,
            "vehicle_count": observation.vehicle_count,
            "queue_lengths": observation.queue_lengths,
            "approach_counts": observation.approach_counts,
            "timestamp": observation.timestamp,
            "hardware_disclaimer": HARDWARE_DISCLAIMER,
            "perception_disclaimer": PERCEPTION_DISCLAIMER,
        }
        return recommendation
