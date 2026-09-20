"""Stable data contracts consumed by later project phases."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class SignalState(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntersectionTrafficState:
    """One intersection's SUMO-derived traffic state at a single simulation step."""
    intersection_id: str
    vehicle_count: int
    queue_length: int
    traffic_density: float
    road_capacity: int
    signal_state: SignalState
    signal_phase: int
    emergency_status: bool = False
    # Queue totals for each green phase, e.g. ((0, 7), (2, 3)).  The phase
    # numbers deliberately match the SUMO program rather than assuming a
    # particular north/south road naming convention.
    green_phase_queues: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["signal_state"] = self.signal_state.value
        return result

    def to_observation(self, source: str = "sumo", timestamp: float | None = None) -> Any:
        """Convert this simulation traffic state to canonical TrafficObservation."""
        from perception.models import TrafficObservation
        return TrafficObservation.from_intersection_traffic_state(self, source=source, timestamp=timestamp)
