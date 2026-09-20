"""QUBO-driven adaptive signal controller for live simulation.

Computes optimal green-phase durations using canonical Phase-3A QUBO formulation
and exact classical solver (or QAOA), applying durations safely at green-phase
boundaries via TraCI without skipping or modifying yellow/red clearance intervals.
"""

from __future__ import annotations

from typing import Any, Mapping

from optimization.quantum.qaoa import run_qaoa
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from simulation.models.state import IntersectionTrafficState
from simulation.state_reader import TrafficStateReader


class QuboSignalController:
    """Dynamically applies QUBO-optimized timing to SUMO traffic signals at safe phase boundaries."""

    def __init__(
        self,
        traci_connection: Any,
        qubo_settings: Mapping[str, Any],
        qaoa_settings: Mapping[str, Any] | None = None,
        solver: str = "exact",
        reevaluation_interval_seconds: float = 15.0,
        minimum_seconds_between_adjustments: float = 50.0,
    ) -> None:
        self._traci = traci_connection
        self._qubo_settings = dict(qubo_settings)
        self._qaoa_settings = dict(qaoa_settings) if qaoa_settings else None
        self._solver = solver.lower()
        if self._solver not in ("exact", "qaoa"):
            raise ValueError("Solver must be either 'exact' or 'qaoa'.")
        if self._solver == "qaoa" and not self._qaoa_settings:
            raise ValueError("qaoa_settings required when solver='qaoa'.")

        self._reevaluation_interval = float(reevaluation_interval_seconds)
        self._min_adjustment_interval = float(minimum_seconds_between_adjustments)
        self._validate_settings()

        self._last_evaluation_time = float("-inf")
        self._pending_green_durations: dict[tuple[str, int], int] = {}
        self._last_phase: dict[str, int] = {}
        self._last_adjustment_time: dict[str, float] = {}
        self._last_decisions: dict[str, Any] = {}

    def configure(self, intersection_ids: list[str]) -> None:
        """Normalize yellow/red durations; preserve SUMO's safe phase sequence."""
        for intersection_id in intersection_ids:
            logics = self._traci.trafficlight.getAllProgramLogics(intersection_id)
            if not logics:
                raise RuntimeError(f"No traffic-light program found for {intersection_id}")
            logic = logics[0]
            for phase in logic.phases:
                if self._is_green(phase.state):
                    # Set initial baseline green
                    phase.duration = int(self._qubo_settings.get("target_total_green_seconds", 60) / 2)
                    phase.minDur = int(self._qubo_settings["min_green_seconds"])
                    phase.maxDur = int(self._qubo_settings["max_green_seconds"])
                elif self._is_yellow(phase.state):
                    phase.duration = int(self._qubo_settings["yellow_seconds"])
                    phase.minDur = phase.duration
                    phase.maxDur = phase.duration
            self._traci.trafficlight.setProgramLogic(intersection_id, logic)

    def step(self, states: list[IntersectionTrafficState]) -> None:
        """Re-evaluate QUBO periodically and apply timing when a green phase begins."""
        now = float(self._traci.simulation.getTime())
        if now - self._last_evaluation_time >= self._reevaluation_interval:
            self._evaluate(states)
            self._last_evaluation_time = now

        for state in states:
            intersection_id = state.intersection_id
            phase = self._traci.trafficlight.getPhase(intersection_id)
            previous_phase = self._last_phase.get(intersection_id)
            self._last_phase[intersection_id] = phase

            # Only apply duration adjustments at the boundary of a green phase
            if previous_phase == phase or not self._is_green(self._phase_state(intersection_id, phase)):
                continue

            desired_duration = self._pending_green_durations.pop((intersection_id, phase), None)
            if desired_duration is None or not self._can_adjust(intersection_id, now):
                continue

            spent = self._spent_duration(intersection_id)
            # Ensure duration is strictly positive and bounded
            clamped = self._clamp_green(desired_duration)
            remaining = max(1, int(clamped - spent))
            self._traci.trafficlight.setPhaseDuration(intersection_id, remaining)
            self._last_adjustment_time[intersection_id] = now

    def _evaluate(self, states: list[IntersectionTrafficState]) -> None:
        for state in states:
            intersection_id = state.intersection_id
            if len(state.green_phase_queues) != 2:
                continue

            try:
                model = build_qubo(state, self._qubo_settings)
                if self._solver == "exact":
                    solution = solve_exact(model)
                    candidate = solution.candidate
                    self._last_decisions[intersection_id] = {
                        "solver": "exact",
                        "objective": solution.objective_value,
                        "candidate": candidate,
                    }
                else:
                    qaoa_res = run_qaoa(model, self._qaoa_settings)
                    if qaoa_res.best_valid_solution is None:
                        continue
                    candidate = qaoa_res.best_valid_solution.candidate
                    self._last_decisions[intersection_id] = {
                        "solver": "qaoa",
                        "objective": qaoa_res.best_valid_solution.objective_value,
                        "candidate": candidate,
                    }

                # Map candidate green durations to phase numbers
                sorted_phases = sorted(state.green_phase_queues)
                phase_0 = sorted_phases[0][0]
                phase_1 = sorted_phases[1][0]

                self._pending_green_durations[(intersection_id, phase_0)] = candidate.first_green_seconds
                self._pending_green_durations[(intersection_id, phase_1)] = candidate.second_green_seconds

            except (ValueError, RuntimeError):
                # Retain baseline timing if state is not currently valid for QUBO
                continue

    def _phase_state(self, intersection_id: str, phase: int) -> str:
        return self._traci.trafficlight.getAllProgramLogics(intersection_id)[0].phases[phase].state

    def _spent_duration(self, intersection_id: str) -> float:
        getter = getattr(self._traci.trafficlight, "getSpentDuration", None)
        return float(getter(intersection_id)) if getter else 0.0

    def _clamp_green(self, seconds: int) -> int:
        return max(
            int(self._qubo_settings["min_green_seconds"]),
            min(int(self._qubo_settings["max_green_seconds"]), seconds),
        )

    def _can_adjust(self, intersection_id: str, now: float) -> bool:
        last_adjustment = self._last_adjustment_time.get(intersection_id, float("-inf"))
        return now - last_adjustment >= self._min_adjustment_interval

    def _validate_settings(self) -> None:
        minimum = int(self._qubo_settings["min_green_seconds"])
        maximum = int(self._qubo_settings["max_green_seconds"])
        if minimum <= 0 or maximum < minimum:
            raise ValueError("QUBO green duration limits are invalid.")
        if "yellow_seconds" not in self._qubo_settings:
            raise ValueError("yellow_seconds is required in qubo_settings.")

    @staticmethod
    def _is_green(state: str) -> bool:
        return any(color in state for color in "Gg")

    @staticmethod
    def _is_yellow(state: str) -> bool:
        return any(color in state for color in "Yy")
