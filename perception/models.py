"""Data models and canonical traffic contracts for detection, tracking, and simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from time import time
from typing import Any, Mapping, Sequence

from simulation.models.state import IntersectionTrafficState, SignalState

VALID_VEHICLE_CLASSES = ("car", "motorcycle", "bus", "truck")
VALID_APPROACHES = ("north", "south", "east", "west")


@dataclass(frozen=True)
class VehicleDetection:
    """One detected vehicle in a camera frame or video."""

    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    center: tuple[float, float]  # (cx, cy)
    track_id: int | None = None

    def __post_init__(self) -> None:
        c_name = str(self.class_name).lower().strip()
        if c_name not in VALID_VEHICLE_CLASSES:
            raise ValueError(
                f"Invalid vehicle class '{self.class_name}'. Must be one of {VALID_VEHICLE_CLASSES}."
            )
        object.__setattr__(self, "class_name", c_name)

        try:
            conf = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("Confidence must be a float.") from exc
        if not (0.0 <= conf <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0.")
        object.__setattr__(self, "confidence", round(conf, 4))

        if not isinstance(self.bbox, (tuple, list)) or len(self.bbox) != 4:
            raise ValueError("Bounding box must contain 4 coordinates (x1, y1, x2, y2).")
        try:
            bbox_tuple = tuple(float(x) for x in self.bbox)
        except (TypeError, ValueError) as exc:
            raise ValueError("All bounding box coordinates must be numeric.") from exc
        object.__setattr__(self, "bbox", bbox_tuple)

        if not isinstance(self.center, (tuple, list)) or len(self.center) != 2:
            raise ValueError("Center must contain 2 coordinates (cx, cy).")
        try:
            center_tuple = tuple(float(x) for x in self.center)
        except (TypeError, ValueError) as exc:
            raise ValueError("All center coordinates must be numeric.") from exc
        object.__setattr__(self, "center", center_tuple)

        if self.track_id is not None:
            try:
                tid = int(self.track_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("track_id must be an integer if provided.") from exc
            if tid < 0:
                raise ValueError("track_id cannot be negative.")
            object.__setattr__(self, "track_id", tid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox": [round(coord, 2) for coord in self.bbox],
            "center": [round(coord, 2) for coord in self.center],
            "track_id": self.track_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VehicleDetection:
        if not isinstance(data, (dict, Mapping)):
            raise ValueError("VehicleDetection data must be a dictionary.")

        raw_class = data.get("class_name", data.get("className", "car"))
        confidence = float(data.get("confidence", 1.0))

        raw_bbox = data.get("bbox")
        if raw_bbox is None or len(raw_bbox) != 4:
            raise ValueError("Bounding box must contain 4 coordinates (x1, y1, x2, y2).")
        bbox = tuple(float(x) for x in raw_bbox)

        raw_center = data.get("center")
        if raw_center is not None and len(raw_center) == 2:
            center = (float(raw_center[0]), float(raw_center[1]))
        else:
            # Fallback: compute center from bounding box
            center = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)

        track_id = data.get("track_id", data.get("trackId"))
        tid = int(track_id) if track_id is not None else None

        return cls(
            class_name=str(raw_class),
            confidence=confidence,
            bbox=bbox,  # type: ignore[arg-type]
            center=center,
            track_id=tid,
        )


@dataclass(frozen=True)
class TrafficObservation:
    """Universal traffic observation structure consumable across simulation and optimization."""

    timestamp: float
    source: str
    intersection_id: str
    vehicle_count: int
    approach_counts: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in VALID_APPROACHES}
    )
    queue_lengths: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in VALID_APPROACHES}
    )
    class_counts: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in VALID_VEHICLE_CLASSES}
    )
    detections: tuple[VehicleDetection, ...] = field(default_factory=tuple)
    tracking_available: bool = False
    tracked_vehicle_count: int = 0
    average_confidence: float = 0.0

    @staticmethod
    def _normalize_counter_dict(
        d: Mapping[str, Any] | None, required_keys: Sequence[str], field_name: str
    ) -> dict[str, int]:
        normalized: dict[str, int] = {k: 0 for k in required_keys}
        if d is not None:
            if not isinstance(d, (dict, Mapping)):
                raise ValueError(f"{field_name} must be a dictionary.")
            for k, v in d.items():
                str_k = str(k).lower().strip()
                try:
                    iv = int(v)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Value for '{k}' in {field_name} must be an integer.") from exc
                if iv < 0:
                    raise ValueError(f"Value for '{k}' in {field_name} cannot be negative.")
                normalized[str_k] = iv
        # Re-verify that all required keys are strictly present
        for req in required_keys:
            if req not in normalized:
                normalized[req] = 0
        return normalized

    def __post_init__(self) -> None:
        # 1. Intersection ID
        if not isinstance(self.intersection_id, str) or not self.intersection_id.strip():
            raise ValueError("Field 'intersection_id' must be a non-empty string.")
        object.__setattr__(self, "intersection_id", self.intersection_id.strip())

        # 2. Source
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("Field 'source' must be a non-empty string.")
        object.__setattr__(self, "source", self.source.strip())

        # 3. Timestamp
        try:
            ts = float(self.timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError("Field 'timestamp' must be a float.") from exc
        if ts < 0.0:
            raise ValueError("Field 'timestamp' cannot be negative.")
        object.__setattr__(self, "timestamp", ts)

        # 4. Normalize & validate approach_counts (all 4 approaches mandatory)
        norm_approaches = self._normalize_counter_dict(
            self.approach_counts, VALID_APPROACHES, "approach_counts"
        )
        object.__setattr__(self, "approach_counts", norm_approaches)

        # 5. Normalize & validate queue_lengths (all 4 approaches mandatory)
        norm_queues = self._normalize_counter_dict(
            self.queue_lengths, VALID_APPROACHES, "queue_lengths"
        )
        object.__setattr__(self, "queue_lengths", norm_queues)

        # 6. Normalize & validate class_counts (all 4 vehicle classes mandatory)
        norm_classes = self._normalize_counter_dict(
            self.class_counts, VALID_VEHICLE_CLASSES, "class_counts"
        )
        object.__setattr__(self, "class_counts", norm_classes)

        # 7. Vehicle count
        try:
            vc = int(self.vehicle_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("Field 'vehicle_count' must be an integer.") from exc
        if vc < 0:
            raise ValueError("Field 'vehicle_count' cannot be negative.")
        object.__setattr__(self, "vehicle_count", vc)

        # 8. Tracked vehicle count
        try:
            tc = int(self.tracked_vehicle_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("Field 'tracked_vehicle_count' must be an integer.") from exc
        if tc < 0:
            raise ValueError("Field 'tracked_vehicle_count' cannot be negative.")
        object.__setattr__(self, "tracked_vehicle_count", tc)

        # 9. Average confidence
        try:
            conf = float(self.average_confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("Field 'average_confidence' must be a float.") from exc
        if not (0.0 <= conf <= 1.0):
            raise ValueError("Field 'average_confidence' must be between 0.0 and 1.0.")
        object.__setattr__(self, "average_confidence", round(conf, 4))

        # 10. Detections tuple
        dets = tuple(self.detections) if self.detections else ()
        object.__setattr__(self, "detections", dets)

        # 11. Tracking available boolean
        object.__setattr__(self, "tracking_available", bool(self.tracking_available))

    def to_dict(self, include_detections: bool = True) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary matching canonical schema."""
        res: dict[str, Any] = {
            "timestamp": self.timestamp,
            "source": self.source,
            "intersection_id": self.intersection_id,
            "vehicle_count": self.vehicle_count,
            "tracked_vehicle_count": self.tracked_vehicle_count,
            "average_confidence": self.average_confidence,
            "approach_counts": dict(self.approach_counts),
            "queue_lengths": dict(self.queue_lengths),
            "class_counts": dict(self.class_counts),
            "tracking_available": self.tracking_available,
        }
        if include_detections:
            res["detections"] = [d.to_dict() for d in self.detections]
        return res

    def to_json(self, indent: int | None = None, include_detections: bool = True) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(include_detections=include_detections), indent=indent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrafficObservation:
        """Construct a validated TrafficObservation from a dictionary with safe defaults."""
        if not isinstance(data, (dict, Mapping)):
            raise ValueError("TrafficObservation data must be a dictionary.")

        timestamp = data.get("timestamp")
        ts = float(timestamp) if timestamp is not None else time()

        source = str(data.get("source", "unknown")).strip()
        if not source:
            source = "unknown"

        raw_id = data.get("intersection_id") if "intersection_id" in data else data.get("intersectionId")
        if raw_id is None or not str(raw_id).strip():
            raise ValueError("Field 'intersection_id' is required and cannot be empty.")
        intersection_id = str(raw_id).strip()

        approach_counts = data.get("approach_counts", data.get("approachCounts"))
        queue_lengths = data.get("queue_lengths", data.get("queueLengths"))
        class_counts = data.get("class_counts", data.get("classCounts"))

        # Parse detections if provided
        raw_dets = data.get("detections", ())
        detections: list[VehicleDetection] = []
        if raw_dets:
            for d in raw_dets:
                if isinstance(d, VehicleDetection):
                    detections.append(d)
                elif isinstance(d, (dict, Mapping)):
                    detections.append(VehicleDetection.from_dict(d))

        # Safe defaults for vehicle_count
        raw_vc = data.get("vehicle_count", data.get("vehicleCount"))
        if raw_vc is not None:
            vehicle_count = int(raw_vc)
        elif approach_counts and isinstance(approach_counts, (dict, Mapping)):
            vehicle_count = sum(int(v) for v in approach_counts.values() if isinstance(v, (int, float)))
        elif detections:
            vehicle_count = len(detections)
        elif class_counts and isinstance(class_counts, (dict, Mapping)):
            vehicle_count = sum(int(v) for v in class_counts.values() if isinstance(v, (int, float)))
        else:
            vehicle_count = 0

        # Safe defaults for tracked_vehicle_count
        raw_tc = data.get("tracked_vehicle_count", data.get("trackedVehicleCount"))
        if raw_tc is not None:
            tracked_count = int(raw_tc)
        elif detections:
            tracked_count = sum(1 for d in detections if d.track_id is not None)
        else:
            tracked_count = 0

        # Safe defaults for average_confidence
        raw_conf = data.get("average_confidence", data.get("averageConfidence"))
        if raw_conf is not None:
            avg_conf = float(raw_conf)
        elif detections:
            avg_conf = round(sum(d.confidence for d in detections) / len(detections), 4)
        else:
            avg_conf = 0.0

        # Safe default for tracking_available
        tracking_avail = data.get("tracking_available", data.get("trackingAvailable"))
        if tracking_avail is None:
            tracking_avail = tracked_count > 0

        return cls(
            timestamp=ts,
            source=source,
            intersection_id=intersection_id,
            vehicle_count=vehicle_count,
            approach_counts=approach_counts or {},
            queue_lengths=queue_lengths or {},
            class_counts=class_counts or {},
            detections=tuple(detections),
            tracking_available=bool(tracking_avail),
            tracked_vehicle_count=tracked_count,
            average_confidence=avg_conf,
        )

    @classmethod
    def from_json(cls, json_str: str) -> TrafficObservation:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def to_intersection_traffic_state(
        self,
        road_capacity: int = 100,
        current_phase: int = 0,
        signal_state: SignalState = SignalState.GREEN,
        emergency_status: bool = False,
    ) -> IntersectionTrafficState:
        """Convert canonical observation to IntersectionTrafficState for QUBO/QAOA."""
        p0_queue = int(self.queue_lengths.get("north", 0) + self.queue_lengths.get("south", 0))
        p2_queue = int(self.queue_lengths.get("east", 0) + self.queue_lengths.get("west", 0))

        capacity = max(1, road_capacity)
        density = min(1.0, float(self.vehicle_count) / float(capacity))
        total_queue = p0_queue + p2_queue

        return IntersectionTrafficState(
            intersection_id=self.intersection_id,
            vehicle_count=self.vehicle_count,
            queue_length=total_queue,
            traffic_density=round(density, 4),
            road_capacity=capacity,
            signal_state=signal_state,
            signal_phase=current_phase,
            emergency_status=emergency_status,
            green_phase_queues=((0, p0_queue), (2, p2_queue)),
        )

    @classmethod
    def from_intersection_traffic_state(
        cls,
        state: IntersectionTrafficState,
        source: str = "sumo",
        timestamp: float | None = None,
    ) -> TrafficObservation:
        """Construct canonical TrafficObservation from an IntersectionTrafficState."""
        now = time() if timestamp is None else float(timestamp)

        # Extract phase queues
        p0_queue = 0
        p2_queue = 0
        if state.green_phase_queues:
            gpq = dict(state.green_phase_queues)
            p0_queue = gpq.get(0, 0)
            p2_queue = gpq.get(2, 0)
        elif state.queue_length > 0:
            p0_queue = state.queue_length // 2 + state.queue_length % 2
            p2_queue = state.queue_length // 2

        # Map phase queues into directional approaches
        queue_lengths = {
            "north": p0_queue // 2 + p0_queue % 2,
            "south": p0_queue // 2,
            "east": p2_queue // 2 + p2_queue % 2,
            "west": p2_queue // 2,
        }

        # Approach counts: account for free non-queued vehicles
        total_q = p0_queue + p2_queue
        free_vehicles = max(0, state.vehicle_count - total_q)
        approach_counts = {
            "north": queue_lengths["north"] + free_vehicles // 4 + (1 if free_vehicles % 4 > 0 else 0),
            "south": queue_lengths["south"] + free_vehicles // 4 + (1 if free_vehicles % 4 > 1 else 0),
            "east": queue_lengths["east"] + free_vehicles // 4 + (1 if free_vehicles % 4 > 2 else 0),
            "west": queue_lengths["west"] + free_vehicles // 4,
        }

        class_counts = {
            "car": state.vehicle_count,
            "motorcycle": 0,
            "bus": 0,
            "truck": 0,
        }

        return cls(
            timestamp=now,
            source=source,
            intersection_id=state.intersection_id,
            vehicle_count=state.vehicle_count,
            approach_counts=approach_counts,
            queue_lengths=queue_lengths,
            class_counts=class_counts,
            detections=(),
            tracking_available=True,
            tracked_vehicle_count=state.vehicle_count,
            average_confidence=1.0,
        )
