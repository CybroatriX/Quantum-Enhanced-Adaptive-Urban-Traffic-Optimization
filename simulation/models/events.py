"""Data models and state contracts for Dynamic Traffic Events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from time import time
from typing import Any, Mapping, Sequence

from perception.models import VALID_APPROACHES


class EventType(str, Enum):
    """Supported types of dynamic urban traffic events."""

    ACCIDENT = "accident"
    ROAD_CLOSURE = "road_closure"
    LANE_BLOCKAGE = "lane_blockage"
    TRAFFIC_SURGE = "traffic_surge"
    PEDESTRIAN_SURGE = "pedestrian_surge"
    PEDESTRIAN_DEMAND = "pedestrian_demand"


class EventSeverity(str, Enum):
    """Severity levels for dynamic events."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(str, Enum):
    """Lifecycle states of a dynamic event."""

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


SEVERITY_FACTORS: dict[str, dict[str, float]] = {
    "low": {"capacity_factor": 0.85, "demand_multiplier": 1.25, "queue_adder": 3},
    "medium": {"capacity_factor": 0.65, "demand_multiplier": 1.60, "queue_adder": 6},
    "high": {"capacity_factor": 0.40, "demand_multiplier": 2.20, "queue_adder": 12},
    "critical": {"capacity_factor": 0.15, "demand_multiplier": 3.00, "queue_adder": 20},
}


@dataclass(frozen=True)
class DynamicEvent:
    """Dynamic traffic event modifying local road and traffic conditions."""

    event_id: str
    event_type: str
    affected_intersection_ids: tuple[str, ...]
    affected_approaches: tuple[str, ...]
    severity: str = "medium"
    start_time: float = field(default_factory=time)
    end_time: float = field(default_factory=lambda: time() + 300.0)
    capacity_factor: float = 1.0
    demand_multiplier: float = 1.0
    queue_adder: int = 0
    min_pedestrian_green: int = 0
    description: str = ""

    def __post_init__(self) -> None:
        # 1. Event ID
        eid = str(self.event_id).strip()
        if not eid:
            raise ValueError("Field 'event_id' must be a non-empty string.")
        object.__setattr__(self, "event_id", eid)

        # 2. Event Type
        etype = str(self.event_type).lower().strip()
        valid_types = {t.value for t in EventType}
        if etype not in valid_types:
            raise ValueError(f"Invalid event_type '{self.event_type}'. Must be one of {sorted(valid_types)}.")
        object.__setattr__(self, "event_type", etype)

        # 3. Affected Intersections
        if not isinstance(self.affected_intersection_ids, (tuple, list)) or not self.affected_intersection_ids:
            raise ValueError("Field 'affected_intersection_ids' must be a non-empty sequence of intersection IDs.")
        cleaned_iids = tuple(str(x).strip() for x in self.affected_intersection_ids if str(x).strip())
        if not cleaned_iids:
            raise ValueError("affected_intersection_ids cannot contain only empty strings.")
        object.__setattr__(self, "affected_intersection_ids", cleaned_iids)

        # 4. Affected Approaches
        if not isinstance(self.affected_approaches, (tuple, list)) or not self.affected_approaches:
            raise ValueError("Field 'affected_approaches' must be a non-empty sequence of approaches.")
        cleaned_apprs = []
        for app in self.affected_approaches:
            app_str = str(app).lower().strip()
            if app_str not in VALID_APPROACHES and app_str != "all":
                raise ValueError(f"Invalid approach '{app}'. Must be one of {list(VALID_APPROACHES)} or 'all'.")
            if app_str == "all":
                cleaned_apprs.extend(VALID_APPROACHES)
            else:
                cleaned_apprs.append(app_str)
        # Deduplicate while preserving order
        dedup_apprs = tuple(dict.fromkeys(cleaned_apprs))
        object.__setattr__(self, "affected_approaches", dedup_apprs)

        # 5. Severity
        sev = str(self.severity).lower().strip()
        valid_sevs = {s.value for s in EventSeverity}
        if sev not in valid_sevs:
            raise ValueError(f"Invalid severity '{self.severity}'. Must be one of {sorted(valid_sevs)}.")
        object.__setattr__(self, "severity", sev)

        # 6. Timestamps
        try:
            st = float(self.start_time)
            et = float(self.end_time)
        except (TypeError, ValueError) as exc:
            raise ValueError("start_time and end_time must be valid floats.") from exc
        if st < 0.0 or et < 0.0:
            raise ValueError("Timestamps cannot be negative.")
        if st > et:
            raise ValueError(f"start_time ({st}) must be less than or equal to end_time ({et}).")
        object.__setattr__(self, "start_time", st)
        object.__setattr__(self, "end_time", et)

        # 7. Impact Parameters
        cap_factor = float(self.capacity_factor)
        if not (0.0 <= cap_factor <= 1.0):
            raise ValueError("capacity_factor must be between 0.0 and 1.0.")
        object.__setattr__(self, "capacity_factor", cap_factor)

        dem_mult = float(self.demand_multiplier)
        if dem_mult < 0.0:
            raise ValueError("demand_multiplier cannot be negative.")
        object.__setattr__(self, "demand_multiplier", dem_mult)

        q_add = int(self.queue_adder)
        if q_add < 0:
            raise ValueError("queue_adder cannot be negative.")
        object.__setattr__(self, "queue_adder", q_add)

        ped_green = int(self.min_pedestrian_green)
        if ped_green < 0:
            raise ValueError("min_pedestrian_green cannot be negative.")
        object.__setattr__(self, "min_pedestrian_green", ped_green)

    def is_active_at(self, current_time: float) -> bool:
        """Check whether the event is active at current_time."""
        return self.start_time <= current_time <= self.end_time

    def status_at(self, current_time: float) -> EventStatus:
        """Get the lifecycle status of the event at current_time."""
        if current_time < self.start_time:
            return EventStatus.SCHEDULED
        if current_time <= self.end_time:
            return EventStatus.ACTIVE
        return EventStatus.EXPIRED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "affected_intersection_ids": list(self.affected_intersection_ids),
            "affected_approaches": list(self.affected_approaches),
            "severity": self.severity,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "capacity_factor": self.capacity_factor,
            "demand_multiplier": self.demand_multiplier,
            "queue_adder": self.queue_adder,
            "min_pedestrian_green": self.min_pedestrian_green,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DynamicEvent:
        """Construct a validated DynamicEvent from a dictionary with sensible defaults."""
        if not isinstance(data, (dict, Mapping)):
            raise ValueError("DynamicEvent data must be a dictionary.")

        eid = data.get("event_id") or data.get("eventId") or ""
        etype = data.get("event_type") or data.get("eventType") or "accident"

        # Intersections
        raw_iids = (
            data.get("affected_intersection_ids")
            or data.get("affectedIntersectionIds")
            or data.get("intersection_ids")
            or data.get("intersections")
            or ()
        )
        if isinstance(raw_iids, str):
            raw_iids = [raw_iids]

        # Approaches
        raw_apprs = (
            data.get("affected_approaches")
            or data.get("affectedApproaches")
            or data.get("approaches")
            or ()
        )
        if isinstance(raw_apprs, str):
            raw_apprs = [raw_apprs]

        severity = str(data.get("severity", "medium")).lower()

        # Timestamps
        now = time()
        st_val = data.get("start_time", data.get("startTime"))
        start_time = float(st_val) if st_val is not None else now
        et_val = data.get("end_time", data.get("endTime"))
        end_time = float(et_val) if et_val is not None else start_time + 300.0

        # Automatic impact defaults based on event type and severity if not explicitly provided
        sev_info = SEVERITY_FACTORS.get(severity, SEVERITY_FACTORS["medium"])
        default_cap = 1.0
        default_dem = 1.0
        default_q = 0
        default_ped = 0

        clean_etype = str(etype).lower().strip()
        if clean_etype == EventType.ACCIDENT.value:
            default_cap = sev_info["capacity_factor"]
            default_q = sev_info["queue_adder"]
        elif clean_etype == EventType.ROAD_CLOSURE.value:
            default_cap = 0.05  # Near zero capacity (closed)
            default_q = sev_info["queue_adder"] * 2
        elif clean_etype == EventType.LANE_BLOCKAGE.value:
            default_cap = max(0.5, sev_info["capacity_factor"])
            default_q = sev_info["queue_adder"] // 2
        elif clean_etype == EventType.TRAFFIC_SURGE.value:
            default_dem = sev_info["demand_multiplier"]
            default_q = sev_info["queue_adder"]
        elif clean_etype in (EventType.PEDESTRIAN_SURGE.value, EventType.PEDESTRIAN_DEMAND.value):
            default_ped = 25  # Minimum pedestrian crossing green seconds requirement

        cap_factor = float(data.get("capacity_factor", data.get("capacityFactor", default_cap)))
        dem_mult = float(data.get("demand_multiplier", data.get("demandMultiplier", default_dem)))
        q_add = int(data.get("queue_adder", data.get("queueAdder", default_q)))
        ped_green = int(data.get("min_pedestrian_green", data.get("minPedestrianGreen", default_ped)))
        desc = str(data.get("description", ""))

        return cls(
            event_id=str(eid),
            event_type=clean_etype,
            affected_intersection_ids=tuple(raw_iids),
            affected_approaches=tuple(raw_apprs),
            severity=severity,
            start_time=start_time,
            end_time=end_time,
            capacity_factor=cap_factor,
            demand_multiplier=dem_mult,
            queue_adder=q_add,
            min_pedestrian_green=ped_green,
            description=desc,
        )

    @classmethod
    def from_json(cls, json_str: str) -> DynamicEvent:
        return cls.from_dict(json.loads(json_str))

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class EventMetrics:
    """Evaluation metrics for dynamic event impact, captured for Phase K analysis."""

    event_id: str
    event_type: str
    affected_intersections: list[str]
    start_time: float
    end_time: float
    activation_duration: float = 0.0
    queues_before: dict[str, int] = field(default_factory=dict)
    queues_during: dict[str, int] = field(default_factory=dict)
    queues_after: dict[str, int] = field(default_factory=dict)
    throughput_before: float = 0.0
    throughput_during: float = 0.0
    throughput_after: float = 0.0
    signal_overrides_count: int = 0
    emergency_preemptions_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
