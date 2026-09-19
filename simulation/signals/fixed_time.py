"""Phase-1 fixed-time controller configured from YAML."""

from __future__ import annotations

from typing import Any


class FixedTimeController:
    """Apply fixed green/yellow/red durations to generated SUMO signal programs."""

    def __init__(self, traci_connection: Any, timing: dict[str, int]) -> None:
        self._traci = traci_connection
        self._timing = timing

    def configure(self, intersection_ids: list[str]) -> None:
        # The generated state strings have SUMO-specific link lengths; retain them
        # and alter only duration, avoiding brittle hard-coded phase strings.
        for intersection_id in intersection_ids:
            logics = self._traci.trafficlight.getAllProgramLogics(intersection_id)
            if not logics:
                raise RuntimeError(f"No traffic-light program found for {intersection_id}")
            logic = logics[0]
            for phase in logic.phases:
                phase.duration = self._duration_for_state(phase.state)
                phase.minDur = phase.duration
                phase.maxDur = phase.duration
            self._traci.trafficlight.setProgramLogic(intersection_id, logic)

    def _duration_for_state(self, state: str) -> int:
        if any(color in state for color in "Gg"):
            return int(self._timing["green_seconds"])
        if any(color in state for color in "Yy"):
            return int(self._timing["yellow_seconds"])
        return int(self._timing["all_red_seconds"])
