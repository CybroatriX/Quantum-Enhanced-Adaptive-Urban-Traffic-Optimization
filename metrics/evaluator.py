"""Evaluation engine for computing traffic performance, fuel consumption, and CO2 emissions."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from metrics.models import (
    ApproachMetrics,
    ControllerComparisonRecord,
    EmergencyEvaluationMetrics,
    EventEvaluationMetrics,
    IntersectionMetrics,
    NetworkMetrics,
)
from perception.models import TrafficObservation, VALID_APPROACHES

logger = logging.getLogger(__name__)

# Documented physical parameters for simulation proxy models:
# - Idle fuel rate: 0.00025 L/s (~0.90 L/hour for passenger vehicles idling at red lights)
# - Moving fuel rate: 0.00070 L/s (~2.52 L/hour at urban cruising speeds 35-50 km/h)
# - Gasoline stoichiometric CO2 emission factor: 2392.0 g CO2 per litre of fuel (EPA/DEFRA standard)
IDLE_FUEL_RATE_LPS: float = 0.00025
CRUISE_FUEL_RATE_LPS: float = 0.00070
CO2_GRAMS_PER_LITRE: float = 2392.0
NOMINAL_LINK_TRAVEL_TIME_SECONDS: float = 15.0


def compute_fuel_and_co2_proxy(
    waiting_time_seconds: float,
    travel_time_seconds: float,
    vehicle_count: int,
) -> tuple[float, float]:
    """Calculate proxy fuel consumption and CO2 emissions for simulation environments.

    Explicitly labeled as 'simulation proxy' because physical vehicle engine
    kinematics are not directly modeled in browser/synthetic state evaluations.

    Formulas:
        moving_time = max(0.0, travel_time - waiting_time)
        fuel_litres = (waiting_time * 0.00025) + (moving_time * 0.00070)
        co2_grams   = fuel_litres * 2392.0
    """
    if vehicle_count <= 0:
        return 0.0, 0.0

    wait_sec = max(0.0, float(waiting_time_seconds))
    travel_sec = max(wait_sec, float(travel_time_seconds))
    moving_sec = max(0.0, travel_sec - wait_sec)

    fuel = (wait_sec * IDLE_FUEL_RATE_LPS) + (moving_sec * CRUISE_FUEL_RATE_LPS)
    co2 = fuel * CO2_GRAMS_PER_LITRE

    return round(fuel, 4), round(co2, 2)


class TrafficMetricsEvaluator:
    """Evaluates intersection and network-level traffic performance."""

    def __init__(self, default_link_length_meters: float = 200.0) -> None:
        self.link_length_meters = default_link_length_meters

    def evaluate_intersection(
        self,
        observation: TrafficObservation,
        p0_green_seconds: int = 30,
        p2_green_seconds: int = 30,
        duration_seconds: float = 60.0,
        sumo_fuel_litres: float | None = None,
        sumo_co2_grams: float | None = None,
        signal_changes_count: int = 0,
    ) -> IntersectionMetrics:
        """Evaluate performance metrics for a single intersection over a time window."""
        iid = observation.intersection_id
        veh_count = int(observation.vehicle_count)
        queues = observation.queue_lengths

        p0_q = queues.get("north", 0) + queues.get("south", 0)
        p2_q = queues.get("east", 0) + queues.get("west", 0)
        total_q = p0_q + p2_q
        max_q = max(queues.values()) if queues else 0

        # Waiting time estimation:
        # Phase 0 green: North/South move, East/West wait for p0 duration.
        # Phase 2 green: East/West move, North/South wait for p2 duration.
        # Delay accumulation = queue * red_duration * fractional cycle
        p0_wait = p0_q * max(1, p2_green_seconds) * 0.5
        p2_wait = p2_q * max(1, p0_green_seconds) * 0.5
        total_wait = p0_wait + p2_wait
        avg_wait = total_wait / max(1, veh_count) if veh_count > 0 else 0.0

        # Throughput estimation:
        # Saturation flow rate ~0.5 vehicles per second of green
        sat_flow = 0.5
        cleared_p0 = min(float(p0_q), p0_green_seconds * sat_flow)
        cleared_p2 = min(float(p2_q), p2_green_seconds * sat_flow)
        total_cleared = cleared_p0 + cleared_p2
        # Scale to vehicles per hour
        sim_duration = max(1.0, float(duration_seconds))
        throughput_vph = (total_cleared / sim_duration) * 3600.0

        # Travel time: nominal link traversing time + intersection waiting time
        avg_travel = NOMINAL_LINK_TRAVEL_TIME_SECONDS + avg_wait

        # Fuel and CO2
        if sumo_fuel_litres is not None:
            fuel = float(sumo_fuel_litres)
            fuel_source = "sumo_measured"
        else:
            fuel, _ = compute_fuel_and_co2_proxy(total_wait, avg_travel * max(1, veh_count), veh_count)
            fuel_source = "simulation_proxy"

        if sumo_co2_grams is not None:
            co2 = float(sumo_co2_grams)
            co2_source = "sumo_measured"
        else:
            _, co2 = compute_fuel_and_co2_proxy(total_wait, avg_travel * max(1, veh_count), veh_count)
            co2_source = "simulation_proxy"

        # Per-approach metrics
        approach_metrics: dict[str, ApproachMetrics] = {}
        for app in VALID_APPROACHES:
            q = queues.get(app, 0)
            app_veh = observation.approach_counts.get(app, q)
            # Determine waiting for this approach
            app_wait = q * (p2_green_seconds if app in ("north", "south") else p0_green_seconds) * 0.5
            app_avg_wait = app_wait / max(1, app_veh) if app_veh > 0 else 0.0
            app_cleared = min(float(q), (p0_green_seconds if app in ("north", "south") else p2_green_seconds) * sat_flow * 0.5)
            app_vph = (app_cleared / sim_duration) * 3600.0

            approach_metrics[app] = ApproachMetrics(
                approach=app,
                queue_length=q,
                vehicle_count=app_veh,
                average_waiting_time_seconds=round(app_avg_wait, 2),
                throughput_vehicles_per_hour=round(app_vph, 2),
            )

        return IntersectionMetrics(
            intersection_id=iid,
            vehicle_count=veh_count,
            average_waiting_time_seconds=round(avg_wait, 2),
            total_waiting_time_seconds=round(total_wait, 2),
            queue_length=total_q,
            max_queue_length=max_q,
            throughput_vehicles_per_hour=round(throughput_vph, 2),
            average_travel_time_seconds=round(avg_travel, 2),
            fuel_consumption_litres=round(fuel, 4),
            co2_emissions_grams=round(co2, 2),
            fuel_source=fuel_source,
            co2_source=co2_source,
            signal_changes_count=signal_changes_count,
            approach_metrics=approach_metrics,
        )

    def evaluate_network(
        self,
        observations: Sequence[TrafficObservation],
        decisions: Mapping[str, Mapping[str, Any]],
        duration_seconds: float = 60.0,
        network_id: str = "urban_network",
    ) -> NetworkMetrics:
        """Evaluate and aggregate performance across multiple intersections."""
        int_metrics_list: list[IntersectionMetrics] = []

        for obs in observations:
            iid = obs.intersection_id
            d = decisions.get(iid, {})
            p0 = int(d.get("phase_0_green_seconds", 30))
            p2 = int(d.get("phase_2_green_seconds", 30))
            im = self.evaluate_intersection(
                observation=obs,
                p0_green_seconds=p0,
                p2_green_seconds=p2,
                duration_seconds=duration_seconds,
            )
            int_metrics_list.append(im)

        return NetworkMetrics.aggregate_intersections(int_metrics_list, network_id=network_id)
