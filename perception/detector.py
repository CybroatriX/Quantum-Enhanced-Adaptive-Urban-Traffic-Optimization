"""YOLOv8 vehicle detection backend for traffic monitoring."""

from __future__ import annotations

import logging
from pathlib import Path
from time import time
from typing import Any, Mapping, Sequence, Union

from perception.aggregator import TrafficAggregator
<<<<<<< HEAD
from perception.models import TrafficObservation, VALID_VEHICLE_CLASSES, VehicleDetection

logger = logging.getLogger(__name__)

=======
from perception.models import (
    PedestrianDetection,
    TrafficObservation,
    VALID_VEHICLE_CLASSES,
    VehicleDetection,
)

logger = logging.getLogger(__name__)

# COCO 80 dataset class indices for pedestrian (person)
COCO_PERSON_CLASS = {
    0: "person",
}

>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
# COCO 80 dataset class indices for relevant road vehicles
COCO_VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

<<<<<<< HEAD
=======
# All permitted detection targets: pedestrians + vehicles only
COCO_TARGET_CLASSES = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

>>>>>>> a608c39 (Update Quantum Traffic Optimization project)

class YOLOVehicleDetector:
    """Ultralytics YOLOv8 vehicle detector for images, video frames, and streams."""

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
        self.aggregator = TrafficAggregator(approach_regions=approach_regions)
        self._model = None

    @property
    def approach_regions(self) -> dict[str, Any]:
        return self.aggregator.approach_regions

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_name)
            return self._model
        except Exception as exc:
            logger.warning("Could not load Ultralytics YOLO (%s). Running in mock/fallback mode.", exc)
            return None

    def detect(
        self,
        source: Any,
        intersection_id: str = "J1",
        track: bool = False,
        timestamp: float | None = None,
<<<<<<< HEAD
=======
        detect_pedestrians: bool = True,
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
    ) -> TrafficObservation:
        """Run vehicle detection on an image, video frame, or array.

        Args:
            source: Image path, URL, OpenCV/numpy frame, or PIL Image.
            intersection_id: Target intersection ID for this camera/feed.
            track: Whether to run multi-object tracking (MOT) to assign track_ids.
            timestamp: Optional timestamp in seconds (defaults to current time).

        Returns:
            TrafficObservation with structured detections, approach counts, class counts, and tracking.
        """
        now = time() if timestamp is None else float(timestamp)
        model = self._load_model()

        if model is None:
            # Fallback when ultralytics weights are not installed
            return self.aggregator.aggregate(
                detections=(),
                intersection_id=intersection_id,
                timestamp=now,
                source="fallback",
            )

        try:
<<<<<<< HEAD
            target_classes = list(COCO_VEHICLE_CLASSES.keys())
=======
            target_class_map = COCO_TARGET_CLASSES if detect_pedestrians else COCO_VEHICLE_CLASSES
            target_classes = list(target_class_map.keys())

>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
            if track:
                results = model.track(
                    source=source,
                    classes=target_classes,
                    conf=self.confidence_threshold,
                    device=self.device,
                    verbose=False,
                    persist=True,
                )
            else:
                results = model.predict(
                    source=source,
                    classes=target_classes,
                    conf=self.confidence_threshold,
                    device=self.device,
                    verbose=False,
                )

            raw_detections: list[VehicleDetection] = []
<<<<<<< HEAD
=======
            raw_pedestrians: list[PedestrianDetection] = []
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
            frame_shape = None

            if results and len(results) > 0:
                result = results[0]
                frame_shape = result.orig_shape if hasattr(result, "orig_shape") else None
                boxes = result.boxes
                if boxes is not None and len(boxes) > 0:
                    for i in range(len(boxes)):
                        cls_id = int(boxes.cls[i].item())
<<<<<<< HEAD
                        class_name = COCO_VEHICLE_CLASSES.get(cls_id)
                        if not class_name:
=======
                        # Strictly filter: only accept targeted classes
                        if cls_id not in target_class_map:
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
                            continue

                        conf = float(boxes.conf[i].item())
                        xyxy = boxes.xyxy[i].cpu().numpy().tolist()
                        x1, y1, x2, y2 = xyxy[0], xyxy[1], xyxy[2], xyxy[3]
                        cx = (x1 + x2) / 2.0
                        cy = (y1 + y2) / 2.0

                        track_id = None
                        if boxes.id is not None:
                            try:
                                track_id = int(boxes.id[i].item())
                            except (IndexError, TypeError):
                                pass

<<<<<<< HEAD
                        det = VehicleDetection(
                            class_name=class_name,
                            confidence=conf,
                            bbox=(x1, y1, x2, y2),
                            center=(cx, cy),
                            track_id=track_id,
                        )
                        raw_detections.append(det)
=======
                        if cls_id == 0:
                            # Pedestrian target
                            ped_det = PedestrianDetection(
                                class_name="person",
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                center=(cx, cy),
                                track_id=track_id,
                            )
                            raw_pedestrians.append(ped_det)
                        elif cls_id in COCO_VEHICLE_CLASSES:
                            # Vehicle target
                            veh_class = COCO_VEHICLE_CLASSES[cls_id]
                            det = VehicleDetection(
                                class_name=veh_class,
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                center=(cx, cy),
                                track_id=track_id,
                            )
                            raw_detections.append(det)
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)

            return self.aggregator.aggregate(
                detections=raw_detections,
                intersection_id=intersection_id,
                timestamp=now,
                source="yolov8",
                frame_shape=frame_shape,
<<<<<<< HEAD
=======
                pedestrian_detections=raw_pedestrians,
>>>>>>> a608c39 (Update Quantum Traffic Optimization project)
            )

        except Exception as exc:
            logger.error("YOLO detection failed: %s", exc)
            return self.aggregator.aggregate(
                detections=(),
                intersection_id=intersection_id,
                timestamp=now,
                source="error",
            )

    def _classify_approach(
        self, cx: float, cy: float, frame_shape: tuple[int, int] | None = None
    ) -> str:
        """Classify detection center into an approach direction (north/south/east/west)."""
        return self.aggregator.classify_approach(cx, cy, frame_shape)
