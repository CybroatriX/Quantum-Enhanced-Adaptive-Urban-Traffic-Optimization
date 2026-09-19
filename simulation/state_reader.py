"""Read SUMO state into framework-independent project data contracts."""

from __future__ import annotations

from typing import Any

from simulation.models.state import IntersectionTrafficState, SignalState


class TrafficStateReader:
    def __init__(self, traci_connection: Any, vehicles_per_lane_capacity: int) -> None:
        self._traci = traci_connection
        self._vehicles_per_lane_capacity = vehicles_per_lane_capacity

    def read_intersection(self, intersection_id: str) -> IntersectionTrafficState:
        lanes = set(self._traci.trafficlight.getControlledLanes(intersection_id))
        vehicle_count = sum(self._traci.lane.getLastStepVehicleNumber(lane) for lane in lanes)
        queue_length = sum(self._traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)
        capacity = len(lanes) * self._vehicles_per_lane_capacity
        return IntersectionTrafficState(
            intersection_id=intersection_id,
            vehicle_count=vehicle_count,
            queue_length=queue_length,
            traffic_density=round(vehicle_count / capacity, 4) if capacity else 0.0,
            road_capacity=capacity,
            signal_state=self._classify_signal(self._traci.trafficlight.getRedYellowGreenState(intersection_id)),
            signal_phase=self._traci.trafficlight.getPhase(intersection_id),
            emergency_status=False,
            green_phase_queues=self.green_phase_queues(self._traci, intersection_id),
        )

    def read_all(self, intersection_ids: list[str]) -> list[IntersectionTrafficState]:
        return [self.read_intersection(intersection_id) for intersection_id in intersection_ids]

    @staticmethod
    def green_phase_queues(
        traci_connection: Any, intersection_id: str
    ) -> tuple[tuple[int, int], ...]:
        """Return queued vehicles for every green movement in SUMO phase order."""
        controlled_links = traci_connection.trafficlight.getControlledLinks(intersection_id)
        phase_queues: list[tuple[int, int]] = []
        for phase_index, phase in enumerate(
            traci_connection.trafficlight.getAllProgramLogics(intersection_id)[0].phases
        ):
            if not any(color in phase.state for color in "Gg"):
                continue
            lanes: set[str] = set()
            for link_index, signal in enumerate(phase.state):
                if signal not in "Gg" or link_index >= len(controlled_links):
                    continue
                for connection in controlled_links[link_index]:
                    lanes.add(connection[0])
            phase_queues.append(
                (
                    phase_index,
                    sum(
                        traci_connection.lane.getLastStepHaltingNumber(lane)
                        for lane in lanes
                    ),
                )
            )
        return tuple(phase_queues)

    @staticmethod
    def _classify_signal(state: str) -> SignalState:
        if any(color in state for color in "Gg"):
            return SignalState.GREEN
        if any(color in state for color in "Yy"):
            return SignalState.YELLOW
        if "r" in state or "R" in state:
            return SignalState.RED
        return SignalState.UNKNOWN
