"""Multi-Intersection Controller managing independent QUBO/QAOA signal timing.

Orchestrates multiple connected intersections using the canonical TrafficObservation
contract. Each intersection maintains its own observation history, traffic state,
queue metrics, and optimized signal timing decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import logging
from time import time
from typing import Any, Mapping, Sequence

from config.loader import load_config
from optimization.quantum.qaoa import run_qaoa
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from perception.models import TrafficObservation, VALID_APPROACHES
from simulation.models.state import IntersectionTrafficState, SignalState

logger = logging.getLogger(__name__)


@dataclass
class IntersectionRecord:
    """State and signal timing record maintained independently for each intersection."""

    intersection_id: str
    vehicle_count: int = 0
    approach_counts: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in VALID_APPROACHES}
    )
    queue_lengths: dict[str, int] = field(
        default_factory=lambda: {k: 0 for k in VALID_APPROACHES}
    )
    traffic_density: float = 0.0
    current_signal_state: SignalState = SignalState.GREEN
    current_signal_phase: int = 0
    phase_0_green_seconds: int = 30
    phase_2_green_seconds: int = 30
    last_observation_timestamp: float | None = None
    last_optimization_timestamp: float | None = None
    objective: float | None = None
    solver: str = "exact"
    status: str = "initialized"  # "optimized", "stale_fallback", "missing_fallback"
    valid: bool = True
    stale_age_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["current_signal_state"] = self.current_signal_state.value
        return data


class MultiIntersectionController:
    """Coordinates independent QUBO/QAOA signal timing across multiple intersections.

    Ensures that every intersection is optimized independently using the canonical
    TrafficObservation contract, with configurable observation freshness policies,
    anti-oscillation guards, and safe bounded fallbacks.
    """

    def __init__(
        self,
        qubo_settings: Mapping[str, Any] | None = None,
        qaoa_settings: Mapping[str, Any] | None = None,
        default_solver: str = "exact",
        max_observation_age_seconds: float = 30.0,
        default_green_seconds: tuple[int, int] = (30, 30),
        min_green_seconds: int = 22,
        max_green_seconds: int = 42,
        road_capacity: int = 100,
        managed_intersection_ids: Sequence[str] | None = None,
        anti_oscillation_damping_seconds: float = 15.0,
        emergency_controller: Any | None = None,
        event_manager: Any | None = None,
    ) -> None:
        cfg = load_config()
        self.qubo_settings = dict(qubo_settings) if qubo_settings is not None else cfg["optimization"]["phase3a"]
        self.qaoa_settings = dict(qaoa_settings) if qaoa_settings is not None else cfg["optimization"]["phase3b"]
        self.default_solver = default_solver.lower()
        if self.default_solver not in ("exact", "qaoa"):
            raise ValueError("default_solver must be either 'exact' or 'qaoa'.")

        self.max_observation_age_seconds = float(max_observation_age_seconds)
        if self.max_observation_age_seconds <= 0.0:
            raise ValueError("max_observation_age_seconds must be positive.")

        self.default_green_seconds = (int(default_green_seconds[0]), int(default_green_seconds[1]))
        self.min_green_seconds = int(min_green_seconds)
        self.max_green_seconds = int(max_green_seconds)
        if self.min_green_seconds <= 0 or self.max_green_seconds < self.min_green_seconds:
            raise ValueError("Invalid green timing limits: requires 0 < min_green <= max_green.")

        self.road_capacity = int(road_capacity)
        self.anti_oscillation_damping_seconds = float(anti_oscillation_damping_seconds)
        self.emergency_controller = emergency_controller
        self.event_manager = event_manager

        # Initialize managed records
        self._records: dict[str, IntersectionRecord] = {}
        if managed_intersection_ids:
            for iid in managed_intersection_ids:
                self._records[str(iid)] = IntersectionRecord(
                    intersection_id=str(iid),
                    phase_0_green_seconds=self.default_green_seconds[0],
                    phase_2_green_seconds=self.default_green_seconds[1],
                )

    def set_emergency_controller(self, emergency_controller: Any) -> None:
        """Attach or update an emergency green corridor controller."""
        self.emergency_controller = emergency_controller

    def set_event_manager(self, event_manager: Any) -> None:
        """Attach or update a dynamic traffic event manager."""
        self.event_manager = event_manager

    def has_active_emergency(self, intersection_id: str) -> bool:
        """Check if an intersection is currently overridden by an emergency corridor."""
        if self.emergency_controller is not None and hasattr(self.emergency_controller, "get_active_override"):
            return self.emergency_controller.get_active_override(intersection_id) is not None
        return False

    def has_active_event(self, intersection_id: str, current_time: float | None = None) -> bool:
        """Check if an intersection currently has active dynamic events."""
        if self.event_manager is not None and hasattr(self.event_manager, "has_active_events"):
            return self.event_manager.has_active_events(intersection_id, current_time=current_time)
        return False

    @property
    def managed_intersections(self) -> list[str]:
        return sorted(self._records.keys())

    def get_intersection_record(self, intersection_id: str) -> IntersectionRecord | None:
        return self._records.get(intersection_id)

    def get_all_intersection_records(self) -> dict[str, IntersectionRecord]:
        return dict(self._records)

    def _clamp_green(self, duration: int) -> int:
        return max(self.min_green_seconds, min(self.max_green_seconds, duration))

    def _deduplicate_observations(
        self, observations: Sequence[TrafficObservation | Mapping[str, Any]]
    ) -> dict[str, TrafficObservation]:
        """Group observations by intersection_id, resolving duplicates by latest timestamp."""
        grouped: dict[str, TrafficObservation] = {}
        for item in observations:
            if isinstance(item, TrafficObservation):
                obs = item
            elif isinstance(item, (dict, Mapping)):
                obs = TrafficObservation.from_dict(item)
            else:
                raise ValueError(f"Unsupported observation format: {type(item)}")

            iid = obs.intersection_id
            if iid not in grouped:
                grouped[iid] = obs
            else:
                # Resolve duplicate: retain observation with newer timestamp or higher vehicle count
                prev = grouped[iid]
                if obs.timestamp > prev.timestamp:
                    grouped[iid] = obs
                elif obs.timestamp == prev.timestamp and obs.vehicle_count > prev.vehicle_count:
                    grouped[iid] = obs
        return grouped

    def optimize_observations(
        self,
        observations: Sequence[TrafficObservation | Mapping[str, Any]],
        current_time: float | None = None,
        solver: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Compute independent optimization decisions for all observed and managed intersections.

        Returns:
            dict mapping intersection_id to decision dictionary.
        """
        now = time() if current_time is None else float(current_time)
        selected_solver = (solver or self.default_solver).lower()
        if selected_solver not in ("exact", "qaoa"):
            raise ValueError("Solver must be either 'exact' or 'qaoa'.")

        grouped_obs = self._deduplicate_observations(observations)

        # Union of explicitly observed intersections and statically managed intersections
        all_ids = sorted(set(self._records.keys()) | set(grouped_obs.keys()))
        decisions: dict[str, dict[str, Any]] = {}

        for iid in all_ids:
            # Ensure intersection has an internal record
            if iid not in self._records:
                self._records[iid] = IntersectionRecord(
                    intersection_id=iid,
                    phase_0_green_seconds=self.default_green_seconds[0],
                    phase_2_green_seconds=self.default_green_seconds[1],
                )
            rec = self._records[iid]

            # Case A: Missing observation
            if iid not in grouped_obs:
                rec.status = "missing_fallback"
                rec.solver = selected_solver
                rec.last_optimization_timestamp = now
                decisions[iid] = {
                    "intersection_id": iid,
                    "phase_0_green_seconds": rec.phase_0_green_seconds,
                    "phase_2_green_seconds": rec.phase_2_green_seconds,
                    "objective": rec.objective or 0.0,
                    "valid": True,
                    "status": "missing_fallback",
                    "solver": selected_solver,
                }
                continue

            obs = grouped_obs[iid]
            age = now - obs.timestamp

            # Case B: Stale observation (exceeds freshness window)
            if age > self.max_observation_age_seconds:
                rec.status = "stale_fallback"
                rec.stale_age_seconds = round(age, 2)
                rec.solver = selected_solver
                rec.last_optimization_timestamp = now
                logger.warning(
                    "Stale observation for intersection %s (age=%.1fs > max=%.1fs). Using fallback.",
                    iid,
                    age,
                    self.max_observation_age_seconds,
                )
                decisions[iid] = {
                    "intersection_id": iid,
                    "phase_0_green_seconds": rec.phase_0_green_seconds,
                    "phase_2_green_seconds": rec.phase_2_green_seconds,
                    "objective": rec.objective or 0.0,
                    "valid": True,
                    "status": "stale_fallback",
                    "stale_age_seconds": round(age, 2),
                    "solver": selected_solver,
                }
                continue

            # Priority Check: Check if an emergency green corridor has active priority on this junction
            emergency_override = None
            if self.emergency_controller:
                emergency_override = self.emergency_controller.get_active_override(iid)

            event_meta = None
            if emergency_override is not None:
                p0_green = (
                    emergency_override.priority_green_seconds
                    if emergency_override.priority_phase == 0
                    else emergency_override.non_priority_green_seconds
                )
                p2_green = (
                    emergency_override.priority_green_seconds
                    if emergency_override.priority_phase == 2
                    else emergency_override.non_priority_green_seconds
                )
                obj = 0.0
                valid = True
                status = "emergency_priority"
                solver_tag = "emergency_override"
            else:
                # Precedence Layer 2: Check for active dynamic events affecting this intersection
                eff_obs = obs
                eff_capacity = self.road_capacity
                if self.event_manager and self.event_manager.has_active_events(iid, current_time=now):
                    eff_obs, eff_capacity, event_meta = self.event_manager.apply_to_observation(
                        obs, current_time=now, base_road_capacity=self.road_capacity
                    )

                # Case C: Fresh observation -> Run canonical QUBO on effective traffic state
                state = eff_obs.to_intersection_traffic_state(road_capacity=eff_capacity)
                model = build_qubo(state, self.qubo_settings)

                if selected_solver == "exact":
                    solution = solve_exact(model)
                    cand = solution.candidate
                    p0_green = cand.first_green_seconds
                    p2_green = cand.second_green_seconds
                    obj = solution.objective_value
                    valid = cand.valid
                else:  # qaoa
                    qaoa_res = run_qaoa(model, self.qaoa_settings)
                    if qaoa_res.best_valid_solution is not None:
                        cand = qaoa_res.best_valid_solution.candidate
                        p0_green = cand.first_green_seconds
                        p2_green = cand.second_green_seconds
                        obj = qaoa_res.best_valid_solution.objective_value
                        valid = cand.valid
                    else:
                        # Safe fallback to exact solution if QAOA did not converge
                        fallback_sol = solve_exact(model)
                        cand = fallback_sol.candidate
                        p0_green = cand.first_green_seconds
                        p2_green = cand.second_green_seconds
                        obj = fallback_sol.objective_value
                        valid = cand.valid

                # Enforce minimum pedestrian crossing green if required by active pedestrian events
                if event_meta and event_meta.get("min_pedestrian_green", 0) > 0:
                    for eid in event_meta.get("active_event_ids", []):
                        ev = self.event_manager.get_event(eid)
                        if ev and ev.min_pedestrian_green > 0:
                            for app in ev.affected_approaches:
                                if app in ("north", "south"):
                                    p0_green = max(p0_green, ev.min_pedestrian_green)
                                elif app in ("east", "west"):
                                    p2_green = max(p2_green, ev.min_pedestrian_green)

                # Enforce safety bounds
                p0_green = self._clamp_green(p0_green)
                p2_green = self._clamp_green(p2_green)

                # Anti-oscillation guard: check if adjustment is permitted
                if rec.last_optimization_timestamp is not None:
                    elapsed = now - rec.last_optimization_timestamp
                    if elapsed < self.anti_oscillation_damping_seconds:
                        # Retain previously established green durations to prevent erratic thrashing
                        p0_green = rec.phase_0_green_seconds
                        p2_green = rec.phase_2_green_seconds

                if event_meta and event_meta.get("events_applied"):
                    status = "event_adapted"
                    solver_tag = f"{selected_solver} (event_adapted)"
                else:
                    status = "optimized"
                    solver_tag = selected_solver

            # Update persistent intersection record
            rec.vehicle_count = obs.vehicle_count
            rec.approach_counts = dict(obs.approach_counts)
            rec.queue_lengths = dict(obs.queue_lengths)
            rec.traffic_density = min(1.0, round(obs.vehicle_count / self.road_capacity, 4))
            rec.phase_0_green_seconds = p0_green
            rec.phase_2_green_seconds = p2_green
            rec.last_observation_timestamp = obs.timestamp
            rec.last_optimization_timestamp = now
            rec.objective = round(obj, 6)
            rec.solver = solver_tag
            rec.status = status
            rec.valid = bool(valid)
            rec.stale_age_seconds = None

            decisions[iid] = {
                "intersection_id": iid,
                "phase_0_green_seconds": p0_green,
                "phase_2_green_seconds": p2_green,
                "objective": rec.objective,
                "valid": bool(valid),
                "status": status,
                "solver": solver_tag,
            }
            if emergency_override is not None:
                decisions[iid]["emergency_priority"] = True
                decisions[iid]["priority_approach"] = emergency_override.priority_approach
                decisions[iid]["priority_phase"] = emergency_override.priority_phase
                if self.event_manager and self.event_manager.has_active_events(iid, current_time=now):
                    decisions[iid]["events_preempted_by_emergency"] = True
            elif event_meta and event_meta.get("events_applied"):
                decisions[iid]["event_adapted"] = True
                decisions[iid]["active_event_ids"] = event_meta.get("active_event_ids", [])
                decisions[iid]["active_event_types"] = event_meta.get("active_event_types", [])
                decisions[iid]["effective_capacity"] = event_meta.get("effective_capacity", self.road_capacity)
                decisions[iid]["effective_queues"] = event_meta.get("effective_queues", {})

        return decisions

    def to_results_list(self, decisions: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Format decisions dictionary into canonical results array sorted by intersection_id."""
        return [dict(decisions[k]) for k in sorted(decisions.keys())]

    def reset(self) -> None:
        """Reset all tracked intersection records to initial baseline."""
        for rec in self._records.values():
            rec.phase_0_green_seconds = self.default_green_seconds[0]
            rec.phase_2_green_seconds = self.default_green_seconds[1]
            rec.last_observation_timestamp = None
            rec.last_optimization_timestamp = None
            rec.objective = None
            rec.status = "initialized"
            rec.stale_age_seconds = None
