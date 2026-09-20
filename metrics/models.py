"""Canonical data models for traffic metrics, fuel consumption, and CO2 emissions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Mapping, Sequence

from perception.models import VALID_APPROACHES


@dataclass
class ApproachMetrics:
    """Traffic metrics for a single intersection approach."""

    approach: str
    queue_length: int = 0
    vehicle_count: int = 0
    average_waiting_time_seconds: float = 0.0
    throughput_vehicles_per_hour: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntersectionMetrics:
    """Comprehensive performance metrics for a single intersection."""

    intersection_id: str
    vehicle_count: int = 0
    average_waiting_time_seconds: float = 0.0
    total_waiting_time_seconds: float = 0.0
    queue_length: int = 0
    max_queue_length: int = 0
    throughput_vehicles_per_hour: float = 0.0
    average_travel_time_seconds: float = 0.0
    fuel_consumption_litres: float = 0.0
    co2_emissions_grams: float = 0.0
    fuel_source: str = "simulation_proxy"  # "sumo_measured" or "simulation_proxy"
    co2_source: str = "simulation_proxy"   # "sumo_measured" or "simulation_proxy"
    signal_changes_count: int = 0
    approach_metrics: dict[str, ApproachMetrics] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.approach_metrics:
            self.approach_metrics = {app: ApproachMetrics(approach=app) for app in VALID_APPROACHES}

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["approach_metrics"] = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.approach_metrics.items()}
        return res


@dataclass
class NetworkMetrics:
    """Deterministically aggregated metrics across multiple connected intersections."""

    network_id: str = "urban_network"
    intersections_count: int = 0
    total_vehicle_count: int = 0
    network_total_waiting_time_seconds: float = 0.0
    network_average_waiting_time_seconds: float = 0.0
    network_total_queue: int = 0
    network_average_queue: float = 0.0
    network_max_queue: int = 0
    network_throughput_vehicles_per_hour: float = 0.0
    network_average_travel_time_seconds: float = 0.0
    network_total_fuel_consumption_litres: float = 0.0
    network_total_co2_emissions_grams: float = 0.0
    fuel_source: str = "simulation_proxy"
    co2_source: str = "simulation_proxy"
    intersection_metrics: dict[str, IntersectionMetrics] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["intersection_metrics"] = {
            k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.intersection_metrics.items()
        }
        return res

    @classmethod
    def aggregate_intersections(
        cls,
        intersection_list: Sequence[IntersectionMetrics],
        network_id: str = "urban_network",
    ) -> NetworkMetrics:
        """Deterministically aggregate a sequence of per-intersection metrics."""
        if not intersection_list:
            return cls(network_id=network_id)

        n = len(intersection_list)
        total_veh = sum(im.vehicle_count for im in intersection_list)
        total_wait = sum(im.total_waiting_time_seconds for im in intersection_list)
        total_q = sum(im.queue_length for im in intersection_list)
        max_q = max(im.max_queue_length for im in intersection_list)
        total_throughput = sum(im.throughput_vehicles_per_hour for im in intersection_list)
        avg_travel = sum(im.average_travel_time_seconds for im in intersection_list) / max(1, n)
        total_fuel = sum(im.fuel_consumption_litres for im in intersection_list)
        total_co2 = sum(im.co2_emissions_grams for im in intersection_list)

        # Determine source label
        all_sumo_fuel = all(im.fuel_source == "sumo_measured" for im in intersection_list)
        all_sumo_co2 = all(im.co2_source == "sumo_measured" for im in intersection_list)

        avg_wait = total_wait / max(1, total_veh) if total_veh > 0 else 0.0

        return cls(
            network_id=network_id,
            intersections_count=n,
            total_vehicle_count=total_veh,
            network_total_waiting_time_seconds=round(total_wait, 3),
            network_average_waiting_time_seconds=round(avg_wait, 3),
            network_total_queue=total_q,
            network_average_queue=round(total_q / max(1, n), 3),
            network_max_queue=max_q,
            network_throughput_vehicles_per_hour=round(total_throughput, 3),
            network_average_travel_time_seconds=round(avg_travel, 3),
            network_total_fuel_consumption_litres=round(total_fuel, 4),
            network_total_co2_emissions_grams=round(total_co2, 2),
            fuel_source="sumo_measured" if all_sumo_fuel else "simulation_proxy",
            co2_source="sumo_measured" if all_sumo_co2 else "simulation_proxy",
            intersection_metrics={im.intersection_id: im for im in intersection_list},
        )


@dataclass
class EmergencyEvaluationMetrics:
    """Evaluation metrics for emergency green corridor priority runs."""

    emergency_vehicle_id: str
    route: list[str]
    emergency_travel_time_seconds: float
    baseline_travel_time_seconds: float
    time_saved_seconds: float
    corridor_activation_duration_seconds: float
    intersections_affected: int
    signal_overrides_count: int
    time_spent_in_priority_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EventEvaluationMetrics:
    """Evaluation metrics for dynamic traffic events impact."""

    event_id: str
    event_type: str
    affected_intersections: list[str]
    activation_duration_seconds: float
    queue_before: int
    queue_during: int
    queue_after: int
    throughput_before: float
    throughput_during: float
    throughput_after: float
    signal_adaptations_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControllerComparisonRecord:
    """Benchmark record comparing one controller run under a specific traffic scenario."""

    scenario: str
    seed: int
    controller: str
    solver: str
    simulation_duration_seconds: float
    vehicle_demand: int
    average_waiting_time_seconds: float
    average_queue_length: float
    throughput_vehicles_per_hour: float
    travel_time_seconds: float
    fuel_consumption_litres: float
    co2_emissions_grams: float
    fuel_source: str = "simulation_proxy"
    co2_source: str = "simulation_proxy"
    qaoa_recovery_rate: float | None = None
    qaoa_objective_gap: float | None = None
    solver_runtime_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
