"""Traffic aggregation and approach/ROI assignment for vehicle detections."""

from __future__ import annotations

import logging
from time import time
from typing import Any, Mapping, Sequence, Union

from perception.models import TrafficObservation, VALID_VEHICLE_CLASSES, VehicleDetection
from perception.queue_estimator import QueueEstimator

logger = logging.getLogger(__name__)

# Supported ROI representation:
# Bounding box: (x1, y1, x2, y2)
# Polygon: sequence of at least 3 (x, y) points
RoiType = Union[Sequence[float], Sequence[tuple[float, float]]]


def point_in_polygon(x: float, y: float, polygon: Sequence[tuple[float, float]]) -> bool:
    """Ray casting algorithm to determine if point (x, y) is inside a 2D polygon."""
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


class TrafficAggregator:
    """Aggregates raw VehicleDetection objects into structured traffic measurements.

    Assigns detections to configurable approach regions, deduplicates multiple detections
    sharing the same track_id, and computes vehicle, class, approach, and tracking totals.
    """

    def __init__(
        self,
        approach_regions: Mapping[str, Any] | None = None,
        frame_shape: tuple[int, int] | None = None,
        track_history_ttl_seconds: float = 30.0,
        queue_estimator: QueueEstimator | None = None,
    ) -> None:
        self.frame_shape = frame_shape
        self.track_history_ttl = float(track_history_ttl_seconds)
        self._approach_regions = self._validate_and_store_regions(approach_regions)
        self._seen_tracks: dict[int, dict[str, Any]] = {}
        self.queue_estimator = queue_estimator or QueueEstimator()

    @property
    def approach_regions(self) -> dict[str, Any]:
        return self._approach_regions

    def _validate_and_store_regions(self, regions: Mapping[str, Any] | None) -> dict[str, Any]:
        if not regions:
            return {}
        validated = {}
        for name, roi in regions.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Approach name must be a non-empty string.")

            if not isinstance(roi, (list, tuple)):
                raise ValueError(f"ROI for approach '{name}' must be a sequence of coordinates.")

            if len(roi) == 4 and all(isinstance(v, (int, float)) for v in roi):
                # Bounding box: [x1, y1, x2, y2]
                x1, y1, x2, y2 = [float(v) for v in roi]
                if x1 > x2 or y1 > y2:
                    raise ValueError(f"Invalid bounding box ROI for '{name}': [x1, y1, x2, y2] requires x1<=x2 and y1<=y2.")
                validated[name] = ("box", (x1, y1, x2, y2))
            elif len(roi) >= 3 and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) for p in roi):
                # Polygon: sequence of (x, y)
                points = tuple((float(p[0]), float(p[1])) for p in roi)
                validated[name] = ("polygon", points)
            else:
                raise ValueError(
                    f"ROI for '{name}' must be either a 4-element bounding box [x1, y1, x2, y2] "
                    f"or a polygon with >=3 points [(x, y), ...]."
                )
        return validated

    def set_approach_regions(self, regions: Mapping[str, Any]) -> None:
        """Update approach regions with validation."""
        self._approach_regions = self._validate_and_store_regions(regions)

    def classify_approach(self, cx: float, cy: float, frame_shape: tuple[int, int] | None = None) -> str:
        """Classify a vehicle center point (cx, cy) into an approach region."""
        # 1. Check user-configured ROIs
        for name, (kind, coords) in self._approach_regions.items():
            if kind == "box":
                x1, y1, x2, y2 = coords
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    return name
            elif kind == "polygon":
                if point_in_polygon(cx, cy, coords):
                    return name

        # 2. Quadrant fallback if frame dimensions are available
        shape = frame_shape or self.frame_shape
        if shape and len(shape) >= 2:
            h, w = shape[0], shape[1]
            rel_x = cx / w
            rel_y = cy / h
            if rel_y < 0.45:
                return "north"
            elif rel_y > 0.55:
                return "south"
            elif rel_x < 0.5:
                return "west"
            else:
                return "east"

        return "north"

    def deduplicate_detections(
        self, detections: Sequence[VehicleDetection]
    ) -> list[VehicleDetection]:
        """Deduplicate detections in a single frame.

        If multiple detections share the same track_id, retain the detection with higher confidence.
        Detections without track_id are preserved.
        """
        tracked: dict[int, VehicleDetection] = {}
        untracked: list[VehicleDetection] = []

        for det in detections:
            if det.track_id is None:
                untracked.append(det)
            else:
                tid = det.track_id
                if tid not in tracked or det.confidence > tracked[tid].confidence:
                    tracked[tid] = det

        return list(tracked.values()) + untracked

    def aggregate(
        self,
        detections: Sequence[VehicleDetection],
        intersection_id: str = "J1",
        timestamp: float | None = None,
        source: str = "yolov8",
        frame_shape: tuple[int, int] | None = None,
    ) -> TrafficObservation:
        """Aggregate vehicle detections into a structured TrafficObservation."""
        now = time() if timestamp is None else float(timestamp)

        # 1. Clean track history past TTL
        self._prune_track_history(now)

        # 2. Deduplicate within the frame
        clean_detections = self.deduplicate_detections(detections)

        # 3. Initialize metrics
        class_counts: dict[str, int] = {k: 0 for k in sorted(VALID_VEHICLE_CLASSES)}
        approach_counts: dict[str, int] = {"north": 0, "south": 0, "east": 0, "west": 0}
        total_confidence = 0.0
        frame_track_ids: set[int] = set()
        approaches: list[str] = []

        for det in clean_detections:
            class_counts[det.class_name] = class_counts.get(det.class_name, 0) + 1
            approach = self.classify_approach(det.center[0], det.center[1], frame_shape)
            approaches.append(approach)
            approach_counts[approach] = approach_counts.get(approach, 0) + 1
            total_confidence += det.confidence

            if det.track_id is not None:
                frame_track_ids.add(det.track_id)
                self._seen_tracks[det.track_id] = {
                    "last_seen": now,
                    "class_name": det.class_name,
                    "approach": approach,
                }

        # Estimate queue lengths using velocity and tracking history
        queue_lengths = self.queue_estimator.estimate_queues(clean_detections, approaches, timestamp=now)

        vehicle_count = len(clean_detections)
        avg_confidence = round(total_confidence / vehicle_count, 4) if vehicle_count > 0 else 0.0
        tracked_count = len(frame_track_ids)
        tracking_available = tracked_count > 0 or len(self._seen_tracks) > 0

        return TrafficObservation(
            timestamp=now,
            source=source,
            intersection_id=intersection_id,
            vehicle_count=vehicle_count,
            approach_counts=approach_counts,
            queue_lengths=queue_lengths,
            class_counts=class_counts,
            detections=tuple(clean_detections),
            tracking_available=tracking_available,
            tracked_vehicle_count=tracked_count,
            average_confidence=avg_confidence,
        )

    def _prune_track_history(self, now: float) -> None:
        expired = [tid for tid, info in self._seen_tracks.items() if now - info["last_seen"] > self.track_history_ttl]
        for tid in expired:
            del self._seen_tracks[tid]

    def reset_tracking(self) -> None:
        """Reset historical tracking state."""
        self._seen_tracks.clear()
