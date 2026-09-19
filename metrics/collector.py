"""Waiting-time, queue, and throughput collector for a live SUMO run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from simulation.models.state import IntersectionTrafficState


@dataclass(frozen=True)
class MetricsSnapshot:
    simulation_time_seconds: float
    completed_vehicles: int
    average_waiting_time_seconds: float
    average_queue_length: float
    throughput_vehicles_per_hour: float
    total_waiting_time_seconds: float
    fuel_litres: float | None = None
    co2_grams: float | None = None

    def to_dict(self) -> dict[str, float | int | None]:
        return self.__dict__.copy()


class MetricsCollector:
    """Tracks actual values from TraCI; fuel/CO2 are intentionally unset in Phase 1."""

    def __init__(self, traci_connection: Any) -> None:
        self._traci = traci_connection
        self._known_vehicle_waits: dict[str, float] = {}
        self._completed_waits: list[float] = []
        self._queue_samples: list[int] = []

    def record_step(self, intersections: Iterable[IntersectionTrafficState]) -> None:
        current_ids = set(self._traci.vehicle.getIDList())
        for vehicle_id in current_ids:
            self._known_vehicle_waits[vehicle_id] = float(self._traci.vehicle.getAccumulatedWaitingTime(vehicle_id))
        for vehicle_id in set(self._known_vehicle_waits) - current_ids:
            self._completed_waits.append(self._known_vehicle_waits.pop(vehicle_id))
        self._queue_samples.append(sum(state.queue_length for state in intersections))

    def snapshot(self) -> MetricsSnapshot:
        simulation_time = float(self._traci.simulation.getTime())
        completed = len(self._completed_waits)
        return MetricsSnapshot(
            simulation_time_seconds=simulation_time,
            completed_vehicles=completed,
            average_waiting_time_seconds=round(sum(self._completed_waits) / completed, 3) if completed else 0.0,
            average_queue_length=round(sum(self._queue_samples) / len(self._queue_samples), 3) if self._queue_samples else 0.0,
            throughput_vehicles_per_hour=round(completed / simulation_time * 3600, 3) if simulation_time else 0.0,
            total_waiting_time_seconds=round(sum(self._completed_waits), 3),
        )
