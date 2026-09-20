"""Real-time camera and video perception engine for vehicles and pedestrians.

Provides decoupled background capture, multi-object tracking, target filtering (vehicles + pedestrians),
overlay rendering, and live MJPEG streaming with zero signal control actuation.
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from typing import Any, Generator, Mapping, Sequence

import cv2
import numpy as np

from perception.detector import COCO_TARGET_CLASSES, COCO_VEHICLE_CLASSES, YOLOVehicleDetector
from perception.models import (
    PedestrianDetection,
    TrafficObservation,
    VALID_APPROACHES,
    VALID_VEHICLE_CLASSES,
    VehicleDetection,
)

logger = logging.getLogger(__name__)

# Color palette for overlays (BGR format for OpenCV)
COLOR_VEHICLE = (248, 189, 56)      # Cyan / Light blue #38bdf8
COLOR_PEDESTRIAN = (94, 63, 244)    # Coral / Rose #f43f5e
COLOR_CAR = (255, 199, 86)          # Bright Cyan
COLOR_BUS = (190, 227, 87)          # Mint green
COLOR_TRUCK = (102, 189, 255)       # Amber
COLOR_MOTORCYCLE = (255, 124, 154)  # Violet
COLOR_TEXT_BG = (15, 23, 42)        # Slate dark #0f172a
COLOR_HEADER_BG = (10, 15, 26)      # Dark Navy


class RealtimeDetectionEngine:
    """Threaded real-time vehicle and pedestrian detection and streaming engine.

    Decouples frame capture from YOLO inference, filters detections strictly to
    vehicles and pedestrians, renders bounding box overlays, and produces live
    status metrics with signal control explicitly disabled.
    """

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.35,
        device: str | None = None,
        approach_regions: Mapping[str, Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.confidence_threshold = float(confidence_threshold)
        self.device = device
        self.approach_regions = dict(approach_regions) if approach_regions else None

        self.detector = YOLOVehicleDetector(
            model_name=self.model_name,
            confidence_threshold=self.confidence_threshold,
            device=self.device,
            approach_regions=self.approach_regions,
        )

        self._lock = threading.Lock()
        self._running = False
        self._capture_thread: threading.Thread | None = None
        self._inference_thread: threading.Thread | None = None

        self._cap: cv2.VideoCapture | None = None
        self._latest_raw_frame: np.ndarray | None = None
        self._latest_annotated_frame: np.ndarray | None = None
        self._latest_jpeg: bytes | None = None

        self._status = "stopped"
        self._error_message: str | None = None
        self._source_type: str = "camera"
        self._camera_index: int = 0
        self._video_path: str | None = None
        self._intersection_id: str = "J1"
        self._inference_fps: float = 10.0
        self._actual_fps: float = 0.0
        self._last_inference_time: float = 0.0

        # Latest observation
        self._latest_observation: TrafficObservation = TrafficObservation(
            timestamp=time.time(),
            source="realtime_detector",
            intersection_id="J1",
            vehicle_count=0,
            pedestrian_count=0,
            tracked_vehicle_count=0,
            tracked_pedestrian_count=0,
            average_confidence=0.0,
            tracking_available=False,
        )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def get_status(self) -> dict[str, Any]:
        """Return the current engine telemetry, detection counts, and camera status."""
        with self._lock:
            obs = self._latest_observation
            total_tracked = obs.tracked_vehicle_count + obs.tracked_pedestrian_count
            return {
                "status": self._status,
                "error": self._error_message,
                "source_type": self._source_type,
                "camera_index": self._camera_index,
                "video_path": self._video_path,
                "intersection_id": self._intersection_id,
                "yolo_status": "READY" if self.detector._load_model() is not None else "FALLBACK",
                "tracking_status": "ACTIVE" if obs.tracking_available else "STANDBY",
                "signal_control": "DISABLED",
                "mode": "REAL-TIME DETECTION ONLY",
                "inference_fps_target": self._inference_fps,
                "inference_fps_actual": round(self._actual_fps, 1),
                "confidence_threshold": self.confidence_threshold,
                "counts": {
                    "total_vehicles": obs.vehicle_count,
                    "total_pedestrians": obs.pedestrian_count,
                    "total_tracked_entities": total_tracked,
                    "cars": obs.class_counts.get("car", 0),
                    "motorcycles": obs.class_counts.get("motorcycle", 0),
                    "buses": obs.class_counts.get("bus", 0),
                    "trucks": obs.class_counts.get("truck", 0),
                    "average_confidence": round(obs.average_confidence * 100, 1),
                },
                "approaches": {
                    "vehicles": obs.approach_counts,
                    "pedestrians": obs.pedestrian_approach_counts,
                },
                "queue_lengths": obs.queue_lengths,
                "observation": obs.to_dict(),
            }

    def start(
        self,
        source_type: str = "camera",
        camera_index: int = 0,
        video_path: str | None = None,
        intersection_id: str = "J1",
        confidence_threshold: float = 0.35,
        inference_fps: float = 10.0,
        approach_regions: Mapping[str, Any] | None = None,
    ) -> bool:
        """Start background capture and inference threads.

        Returns True on successful initiation, False if the camera/source cannot be opened.
        """
        self.stop()

        with self._lock:
            self._source_type = str(source_type).lower().strip()
            self._camera_index = int(camera_index)
            self._video_path = str(video_path) if video_path else None
            self._intersection_id = str(intersection_id).strip() or "J1"
            self.confidence_threshold = max(0.05, min(0.95, float(confidence_threshold)))
            self._inference_fps = max(1.0, min(30.0, float(inference_fps)))
            self.detector.confidence_threshold = self.confidence_threshold

            if approach_regions is not None:
                self.approach_regions = dict(approach_regions)
                self.detector.aggregator.set_approach_regions(approach_regions)

            # Open video capture device
            cap = None
            try:
                if self._source_type == "video":
                    if not self._video_path or not Path(self._video_path).exists():
                        self._status = "unavailable"
                        self._error_message = f"Video file not found: {self._video_path}"
                        return False
                    cap = cv2.VideoCapture(self._video_path)
                else:
                    # Camera mode
                    cap = cv2.VideoCapture(self._camera_index)
                    if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    self._status = "unavailable"
                    self._error_message = f"Failed to open {self._source_type} (index: {self._camera_index})."
                    if cap is not None:
                        cap.release()
                    return False

                self._cap = cap
                self._running = True
                self._status = "connected"
                self._error_message = None

            except Exception as exc:
                self._status = "error"
                self._error_message = f"Capture initialization error: {exc}"
                if cap is not None:
                    cap.release()
                return False

        # Launch background threads
        self._capture_thread = threading.Thread(
            target=self._capture_worker, name="flowq-cam-capture", daemon=True
        )
        self._inference_thread = threading.Thread(
            target=self._inference_worker, name="flowq-cam-inference", daemon=True
        )

        self._capture_thread.start()
        self._inference_thread.start()
        logger.info(
            "Realtime detection started on %s (%s) at target %s FPS.",
            self._source_type,
            self._camera_index if self._source_type == "camera" else self._video_path,
            self._inference_fps,
        )
        return True

    def stop(self) -> None:
        """Gracefully release camera/video capture, stop threads, and clear state."""
        with self._lock:
            if not self._running and self._status == "stopped":
                return
            self._running = False
            self._status = "stopped"
            cap = self._cap
            self._cap = None

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self._inference_thread and self._inference_thread.is_alive():
            self._inference_thread.join(timeout=1.0)

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

        with self._lock:
            self._status = "stopped"
            self._running = False
            self._capture_thread = None
            self._inference_thread = None
            self._latest_raw_frame = None
            self._latest_annotated_frame = None
            self._latest_jpeg = None
            self.detector.aggregator.reset_tracking()
            self._latest_observation = TrafficObservation(
                timestamp=time.time(),
                source="realtime_detector",
                intersection_id=self._intersection_id,
                vehicle_count=0,
                pedestrian_count=0,
                tracked_vehicle_count=0,
                tracked_pedestrian_count=0,
                average_confidence=0.0,
                tracking_available=False,
            )

        logger.info("Realtime detection engine stopped cleanly.")

    def _capture_worker(self) -> None:
        """Worker thread continuously reading the freshest frame from OpenCV."""
        while True:
            with self._lock:
                if not self._running or self._cap is None:
                    break
                cap = self._cap

            ret, frame = cap.read()
            if not ret or frame is None:
                # Video file loop or camera disconnect
                if self._source_type == "video":
                    with self._lock:
                        if self._cap is not None:
                            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            continue
                else:
                    logger.warning("Camera frame read failed or camera disconnected.")
                    with self._lock:
                        self._status = "unavailable"
                        self._error_message = "Camera disconnected or failed to read frame."
                        self._running = False
                    break

            with self._lock:
                self._latest_raw_frame = frame

            time.sleep(0.005)

    def _inference_worker(self) -> None:
        """Worker thread running YOLO detection and tracking at configured FPS."""
        fps_tracker_time = time.time()
        frames_computed = 0

        while True:
            with self._lock:
                if not self._running:
                    break
                target_interval = 1.0 / max(1.0, self._inference_fps)
                frame = self._latest_raw_frame.copy() if self._latest_raw_frame is not None else None
                intersection_id = self._intersection_id

            loop_start = time.time()

            if frame is not None:
                try:
                    # Run YOLOv8 detection & tracking
                    obs = self.detector.detect(
                        source=frame,
                        intersection_id=intersection_id,
                        track=True,
                        timestamp=loop_start,
                        detect_pedestrians=True,
                    )

                    # Render overlays onto frame
                    annotated = self._render_overlays(frame, obs)

                    # Encode to JPEG
                    ret, jpeg_buffer = cv2.imencode(
                        ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80]
                    )
                    jpeg_bytes = jpeg_buffer.tobytes() if ret else None

                    frames_computed += 1
                    now = time.time()
                    if now - fps_tracker_time >= 1.0:
                        self._actual_fps = frames_computed / (now - fps_tracker_time)
                        fps_tracker_time = now
                        frames_computed = 0

                    with self._lock:
                        if not self._running:
                            break
                        self._latest_observation = obs
                        self._latest_annotated_frame = annotated
                        self._latest_jpeg = jpeg_bytes
                        self._status = "running"
                        self._error_message = None

                except Exception as exc:
                    logger.error("Inference worker error: %s", exc)
                    with self._lock:
                        self._error_message = f"Inference error: {exc}"

            elapsed = time.time() - loop_start
            sleep_time = max(0.001, target_interval - elapsed)
            time.sleep(sleep_time)

    def _render_overlays(
        self, frame: np.ndarray, obs: TrafficObservation
    ) -> np.ndarray:
        """Draw bounding boxes, labels, and top telemetry banner."""
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # 1. Top banner background (Navy glass)
        banner_h = 36
        banner_overlay = annotated.copy()
        cv2.rectangle(banner_overlay, (0, 0), (w, banner_h), COLOR_HEADER_BG, -1)
        cv2.addWeighted(banner_overlay, 0.88, annotated, 0.12, 0, annotated)
        cv2.line(annotated, (0, banner_h), (w, banner_h), (60, 80, 100), 1)

        # Header telemetry text
        header_text = (
            f"FLOWQ DETECTION ONLY | "
            f"VEHICLES: {obs.vehicle_count}  "
            f"PEDESTRIANS: {obs.pedestrian_count}  "
            f"TRACKED: {obs.tracked_vehicle_count + obs.tracked_pedestrian_count}  "
            f"CONF: {int(obs.average_confidence * 100)}% | "
            f"SIGNAL CONTROL: DISABLED"
        )
        cv2.putText(
            annotated,
            header_text,
            (12, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (240, 245, 250),
            1,
            cv2.LINE_AA,
        )

        # 2. Render Vehicle Bounding Boxes
        for det in obs.detections:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)

            color = COLOR_CAR
            if det.class_name == "bus":
                color = COLOR_BUS
            elif det.class_name == "truck":
                color = COLOR_TRUCK
            elif det.class_name == "motorcycle":
                color = COLOR_MOTORCYCLE

            # Bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Label badge
            label = f"{det.class_name.capitalize()}"
            if det.track_id is not None:
                label += f" #{det.track_id}"
            label += f" {int(det.confidence * 100)}%"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            badge_y1 = max(banner_h + 2, y1 - th - 6)
            badge_y2 = badge_y1 + th + 6
            badge_x2 = min(w, x1 + tw + 8)

            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), COLOR_TEXT_BG, -1)
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), color, 1)
            cv2.putText(
                annotated,
                label,
                (x1 + 4, badge_y2 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

        # 3. Render Pedestrian Bounding Boxes
        for ped in obs.pedestrian_detections:
            x1, y1, x2, y2 = [int(v) for v in ped.bbox]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)

            color = COLOR_PEDESTRIAN
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = "Pedestrian"
            if ped.track_id is not None:
                label += f" #{ped.track_id}"
            label += f" {int(ped.confidence * 100)}%"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            badge_y1 = max(banner_h + 2, y1 - th - 6)
            badge_y2 = badge_y1 + th + 6
            badge_x2 = min(w, x1 + tw + 8)

            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), COLOR_TEXT_BG, -1)
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), color, 1)
            cv2.putText(
                annotated,
                label,
                (x1 + 4, badge_y2 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )

        return annotated

    def get_latest_jpeg(self) -> bytes:
        """Return the latest encoded JPEG frame or generate an informative standby card."""
        with self._lock:
            if self._latest_jpeg is not None:
                return self._latest_jpeg
            status_text = self._status.upper()
            err = self._error_message or "Camera stopped"

        # Generate a clean dark standby card if no frame is currently active
        card = np.zeros((360, 640, 3), dtype=np.uint8)
        card[:] = (15, 23, 42)  # Dark slate

        cv2.putText(
            card,
            "FLOWQ REAL-TIME TRAFFIC PERCEPTION",
            (80, 130),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (240, 245, 250),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            card,
            f"STATUS: {status_text}",
            (180, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (87, 227, 190) if status_text in ("CONNECTED", "RUNNING") else (255, 100, 124),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            card,
            err[:50],
            (140, 220),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (160, 180, 200),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            card,
            "Signal Control: DISABLED",
            (190, 260),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 189, 102),
            1,
            cv2.LINE_AA,
        )

        ret, buf = cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ret else b""

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield multipart HTTP chunk frames for real-time MJPEG browser streaming."""
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        while True:
            frame_bytes = self.get_latest_jpeg()
            yield boundary + frame_bytes + b"\r\n"
            time.sleep(0.08)  # ~12.5 FPS stream yield rate
