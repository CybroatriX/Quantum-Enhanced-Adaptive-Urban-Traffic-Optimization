"""Data models and state contracts for Emergency Green Corridor priority."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from time import time
from typing import Any, Mapping, Sequence


class CorridorState(str, Enum):
    """Lifecycle states of an emergency green corridor."""

    IDLE = "idle"
    REQUESTED = "requested"
    VALIDATED = "validated"
    ACTIVE = "active"
    PASSED = "passed"
    RELEASED = "released"
    EXPIRED = "expired"
    REJECTED = "rejected"


PRIORITY_RANKS: dict[str, int] = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 0,
}


@dataclass(frozen=True)
class EmergencyRequest:
    """Request for emergency vehicle priority corridor across intersections."""

    emergency_vehicle_id: str
    current_intersection_id: str
    destination_intersection_id: str
    route: tuple[str, ...]
    priority: str = "high"
    timestamp: float = field(default_factory=time)
    speed_mps: float = 15.0
    approach_hints: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        veh_id = str(self.emergency_vehicle_id).strip()
        if not veh_id:
            raise ValueError("Field 'emergency_vehicle_id' must be a non-empty string.")
        object.__setattr__(self, "emergency_vehicle_id", veh_id)

        curr_id = str(self.current_intersection_id).strip()
        if not curr_id:
            raise ValueError("Field 'current_intersection_id' must be a non-empty string.")
        object.__setattr__(self, "current_intersection_id", curr_id)

        dest_id = str(self.destination_intersection_id).strip()
        if not dest_id:
            raise ValueError("Field 'destination_intersection_id' must be a non-empty string.")
        object.__setattr__(self, "destination_intersection_id", dest_id)

        if not isinstance(self.route, (tuple, list)) or not self.route:
            raise ValueError("Field 'route' must be a non-empty sequence of intersection IDs.")
        cleaned_route = tuple(str(x).strip() for x in self.route if str(x).strip())
        if not cleaned_route:
            raise ValueError("Route cannot contain only empty strings.")
        if curr_id not in cleaned_route:
            raise ValueError(f"current_intersection_id '{curr_id}' must be part of route.")
        if dest_id not in cleaned_route:
            raise ValueError(f"destination_intersection_id '{dest_id}' must be part of route.")
        object.__setattr__(self, "route", cleaned_route)

        prio = str(self.priority).lower().strip()
        if prio not in PRIORITY_RANKS:
            raise ValueError(
                f"Invalid priority '{self.priority}'. Must be one of {list(PRIORITY_RANKS.keys())}."
            )
        object.__setattr__(self, "priority", prio)

        try:
            ts = float(self.timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamp must be a float.") from exc
        if ts < 0.0:
            raise ValueError("timestamp cannot be negative.")
        object.__setattr__(self, "timestamp", ts)

    @property
    def priority_rank(self) -> int:
        return PRIORITY_RANKS.get(self.priority, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "emergency_vehicle_id": self.emergency_vehicle_id,
            "current_intersection_id": self.current_intersection_id,
            "destination_intersection_id": self.destination_intersection_id,
            "route": list(self.route),
            "priority": self.priority,
            "timestamp": self.timestamp,
            "speed_mps": self.speed_mps,
            "approach_hints": dict(self.approach_hints),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EmergencyRequest:
        if not isinstance(data, (dict, Mapping)):
            raise ValueError("EmergencyRequest data must be a dictionary.")

        veh_id = data.get("emergency_vehicle_id") or data.get("vehicleId") or ""
        curr_id = data.get("current_intersection_id") or data.get("currentIntersectionId") or ""
        dest_id = data.get("destination_intersection_id") or data.get("destinationIntersectionId") or ""
        raw_route = data.get("route", ())
        priority = data.get("priority", "high")
        ts = data.get("timestamp")
        timestamp = float(ts) if ts is not None else time()
        speed = float(data.get("speed_mps", 15.0))
        hints = data.get("approach_hints", {})

        return cls(
            emergency_vehicle_id=str(veh_id),
            current_intersection_id=str(curr_id),
            destination_intersection_id=str(dest_id),
            route=tuple(raw_route),
            priority=str(priority),
            timestamp=timestamp,
            speed_mps=speed,
            approach_hints=dict(hints) if isinstance(hints, (dict, Mapping)) else {},
        )

    @classmethod
    def from_json(cls, json_str: str) -> EmergencyRequest:
        return cls.from_dict(json.loads(json_str))

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class IntersectionPriorityPlan:
    """Priority timing and approach allocation for one intersection along the corridor."""

    intersection_id: str
    priority_approach: str  # "north", "south", "east", "west"
    priority_phase: int  # 0 or 2
    priority_green_seconds: int = 40
    non_priority_green_seconds: int = 22
    status: CorridorState = CorridorState.REQUESTED
    estimated_arrival_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "intersection_id": self.intersection_id,
            "priority_approach": self.priority_approach,
            "priority_phase": self.priority_phase,
            "phase_0_green_seconds": (
                self.priority_green_seconds if self.priority_phase == 0 else self.non_priority_green_seconds
            ),
            "phase_2_green_seconds": (
                self.priority_green_seconds if self.priority_phase == 2 else self.non_priority_green_seconds
            ),
            "status": self.status.value,
            "estimated_arrival_seconds": round(self.estimated_arrival_seconds, 2),
        }


@dataclass
class CorridorMetrics:
    """Evaluation metrics for emergency corridor traversal and impact."""

    emergency_vehicle_id: str
    route: tuple[str, ...]
    intersections_affected: int
    signal_overrides_count: int
    activation_timestamp: float
    corridor_id: str = ""
    completion_timestamp: float | None = None
    corridor_activation_duration: float = 0.0
    emergency_travel_time: float = 0.0
    baseline_estimated_travel_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CorridorPlan:
    """Complete multi-intersection corridor status and timing plan."""

    emergency_vehicle_id: str
    corridor_status: CorridorState
    affected_intersections: list[str]
    intersection_plans: dict[str, IntersectionPriorityPlan]
    validation_result: str
    is_valid: bool
    metrics: CorridorMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "emergency_vehicle_id": self.emergency_vehicle_id,
            "corridor_status": self.corridor_status.value,
            "affected_intersections": list(self.affected_intersections),
            "intersection_plans": {k: v.to_dict() for k, v in self.intersection_plans.items()},
            "validation_result": self.validation_result,
            "is_valid": self.is_valid,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }
