"""Rule-based classical adaptive controller for Phase 2.

The controller changes green duration only. SUMO retains the generated phase
sequence and yellow phases, so this module never jumps directly between traffic
movements or creates unsafe signal transitions.
"""

from __future__ import annotations

from typing import Any

from simulation.models.state import IntersectionTrafficState
from simulation.state_reader import TrafficStateReader


class AdaptiveSignalController:
    """Independently adapt green times at each intersection from current demand."""

    def __init__(self, traci_connection: Any, settings: dict[str, float | int]) -> None:
        self._traci = traci_connection
        self._settings = settings
        self._validate_settings()
        self._last_evaluation_time = float("-inf")
        self._pending_green_durations: dict[tuple[str, int], int] = {}
        self._last_phase: dict[str, int] = {}
        self._last_adjustment_time: dict[str, float] = {}

    def configure(self, intersection_ids: list[str]) -> None:
        """Normalize yellow phases to configuration; retain SUMO's safe sequence."""
        for intersection_id in intersection_ids:
            logics = self._traci.trafficlight.getAllProgramLogics(intersection_id)
            if not logics:
                raise RuntimeError(f"No traffic-light program found for {intersection_id}")
            logic = logics[0]
            for phase in logic.phases:
                if self._is_green(phase.state):
                    # This is the no-imbalance plan. Adaptive control only
                    # overrides it when queue imbalance exceeds the threshold.
                    phase.duration = int(self._settings["base_green_seconds"])
                    phase.minDur = phase.duration
                    phase.maxDur = phase.duration
                elif self._is_yellow(phase.state):
                    phase.duration = int(self._settings["yellow_seconds"])
                    phase.minDur = phase.duration
                    phase.maxDur = phase.duration
            self._traci.trafficlight.setProgramLogic(intersection_id, logic)

    def step(self, states: list[IntersectionTrafficState]) -> None:
        """Refresh decisions periodically and apply one when a green phase begins."""
        now = float(self._traci.simulation.getTime())
        if now - self._last_evaluation_time >= float(self._settings["reevaluation_interval_seconds"]):
            self._evaluate(states)
            self._last_evaluation_time = now

        for state in states:
            intersection_id = state.intersection_id
            phase = self._traci.trafficlight.getPhase(intersection_id)
            previous_phase = self._last_phase.get(intersection_id)
            self._last_phase[intersection_id] = phase
            if previous_phase == phase or not self._is_green(self._phase_state(intersection_id, phase)):
                continue
            desired_duration = self._pending_green_durations.pop((intersection_id, phase), None)
            if desired_duration is None or not self._can_adjust(intersection_id, now):
                continue
            # SUMO expects a remaining duration. Subtract spent time so the full
            # green is never longer than the configured maximum.
            spent = self._spent_duration(intersection_id)
            remaining = max(1, int(desired_duration - spent))
            self._traci.trafficlight.setPhaseDuration(intersection_id, remaining)
            self._last_adjustment_time[intersection_id] = now

    def recommend_green_duration(
        self,
        state: IntersectionTrafficState,
        selected_phase_queue: int,
        all_green_phase_queues: list[int],
    ) -> int:
        """Return a stable duration that changes only for a material imbalance."""
        baseline = int(self._settings["base_green_seconds"])
        if not all_green_phase_queues:
            return baseline
        largest_queue = max(all_green_phase_queues)
        smallest_queue = min(all_green_phase_queues)
        imbalance = largest_queue - smallest_queue
        if (
            state.traffic_density <= float(self._settings["low_traffic_density_threshold"])
            and largest_queue <= int(self._settings["low_traffic_queue_threshold"])
        ):
            return self._clamp_green(int(self._settings["low_traffic_green_seconds"]))
        if imbalance < int(self._settings["demand_imbalance_threshold"]):
            return baseline
        if selected_phase_queue == largest_queue:
            extension = int(self._settings["green_extension_seconds"])
            if state.traffic_density >= float(self._settings["density_activation_threshold"]):
                extension += int(self._settings["density_extension_seconds"])
            return self._clamp_green(baseline + extension)
        if selected_phase_queue == smallest_queue:
            return self._clamp_green(baseline - int(self._settings["green_reduction_seconds"]))
        return baseline

    def _evaluate(self, states: list[IntersectionTrafficState]) -> None:
        for state in states:
            intersection_id = state.intersection_id
            phase_queues = self._green_phase_queues(intersection_id)
            all_queues = list(phase_queues.values())
            for phase, queue_length in phase_queues.items():
                recommendation = self.recommend_green_duration(
                    state, queue_length, all_queues
                )
                if recommendation != int(self._settings["base_green_seconds"]):
                    self._pending_green_durations[(intersection_id, phase)] = recommendation
                else:
                    self._pending_green_durations.pop((intersection_id, phase), None)

    def _green_phase_queues(self, intersection_id: str) -> dict[int, int]:
        """Map each green phase to its controlled incoming-lane queue."""
        return dict(TrafficStateReader.green_phase_queues(self._traci, intersection_id))

    def _phase_state(self, intersection_id: str, phase: int) -> str:
        return self._traci.trafficlight.getAllProgramLogics(intersection_id)[0].phases[phase].state

    def _spent_duration(self, intersection_id: str) -> float:
        getter = getattr(self._traci.trafficlight, "getSpentDuration", None)
        return float(getter(intersection_id)) if getter else 0.0

    def _clamp_green(self, seconds: int) -> int:
        return max(int(self._settings["min_green_seconds"]), min(int(self._settings["max_green_seconds"]), seconds))

    def _can_adjust(self, intersection_id: str, now: float) -> bool:
        last_adjustment = self._last_adjustment_time.get(intersection_id, float("-inf"))
        return now - last_adjustment >= float(self._settings["minimum_seconds_between_adjustments"])

    def _validate_settings(self) -> None:
        minimum = int(self._settings["min_green_seconds"])
        maximum = int(self._settings["max_green_seconds"])
        if minimum <= 0 or maximum < minimum:
            raise ValueError("Adaptive green duration limits are invalid.")
        if not minimum <= int(self._settings["base_green_seconds"]) <= maximum:
            raise ValueError("base_green_seconds must be within the green-duration limits.")
        if not minimum <= int(self._settings["low_traffic_green_seconds"]) <= maximum:
            raise ValueError("low_traffic_green_seconds must be within the green-duration limits.")
        # The generated four-way network has two green and two yellow phases.
        minimum_cycle = minimum * 2 + int(self._settings["yellow_seconds"]) * 2
        maximum_cycle = maximum * 2 + int(self._settings["yellow_seconds"]) * 2
        if minimum_cycle < int(self._settings["min_cycle_seconds"]):
            raise ValueError("min_cycle_seconds exceeds the achievable minimum cycle.")
        if maximum_cycle > int(self._settings["max_cycle_seconds"]):
            raise ValueError("max_cycle_seconds is below the achievable maximum cycle.")

    @staticmethod
    def _is_green(state: str) -> bool:
        return any(color in state for color in "Gg")

    @staticmethod
    def _is_yellow(state: str) -> bool:
        return any(color in state for color in "Yy")
