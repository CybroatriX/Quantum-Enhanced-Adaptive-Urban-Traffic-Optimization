"""Small, inspectable QUBO models for Phase 3A signal-timing validation.

This module deliberately has no Qiskit dependency.  Phase 3A establishes the
classical ground truth that a later QAOA implementation must reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping

from simulation.models.state import IntersectionTrafficState


@dataclass(frozen=True)
class TimingCandidate:
    """One pair of green times for the two green SUMO phases."""

    variable_index: int
    first_green_seconds: int
    second_green_seconds: int
    valid: bool


@dataclass(frozen=True)
class CostBreakdown:
    waiting: float
    imbalance: float
    cycle: float

    @property
    def total(self) -> float:
        return self.waiting + self.imbalance + self.cycle

    def to_dict(self) -> dict[str, float]:
        return {
            "waiting": self.waiting,
            "imbalance": self.imbalance,
            "cycle": self.cycle,
            "total": self.total,
        }


@dataclass(frozen=True)
class QuboModel:
    """Upper-triangular QUBO: E(x) = offset + sum_i Qii*x_i + sum_i<j Qij*x_i*x_j."""

    state: IntersectionTrafficState
    phase_ids: tuple[int, int]
    phase_queues: tuple[float, float]
    variable_names: tuple[str, ...]
    candidates: tuple[TimingCandidate, ...]
    candidate_costs: tuple[CostBreakdown, ...]
    matrix: tuple[tuple[float, ...], ...]
    offset: float
    one_hot_penalty: float
    invalid_timing_penalty: float

    def energy(self, assignment: tuple[int, ...]) -> float:
        if len(assignment) != len(self.variable_names) or any(bit not in (0, 1) for bit in assignment):
            raise ValueError("Assignment must contain one binary value for every QUBO variable.")
        value = self.offset
        for row, bit in enumerate(assignment):
            if not bit:
                continue
            value += self.matrix[row][row]
            for column in range(row + 1, len(assignment)):
                if assignment[column]:
                    value += self.matrix[row][column]
        return value

    def selected_candidate(self, assignment: tuple[int, ...]) -> TimingCandidate:
        selected = [candidate for candidate, bit in zip(self.candidates, assignment) if bit]
        if len(selected) != 1:
            raise ValueError("A valid timing plan must select exactly one candidate.")
        if not selected[0].valid:
            raise ValueError("The selected timing plan violates the configured signal constraints.")
        return selected[0]

    def matrix_as_lists(self, digits: int = 6) -> list[list[float]]:
        return [[round(value, digits) for value in row] for row in self.matrix]


def build_qubo(
    state: IntersectionTrafficState, settings: Mapping[str, Any]
) -> QuboModel:
    """Build a one-hot QUBO from one SUMO-derived intersection state.

    The current four-way SUMO plan has exactly two green phases.  The state
    reader supplies their queue lengths in program order, avoiding a guessed
    directional split.  Candidate times are applied at a normal phase boundary
    by a later controller; this formulation never changes phase order.
    """
    phase_queues = tuple(sorted(state.green_phase_queues))
    if len(phase_queues) != 2:
        raise ValueError(
            "Phase 3A requires exactly two green-phase queue measurements in the traffic state."
        )
    phase_ids = (phase_queues[0][0], phase_queues[1][0])
    measured_first, measured_second = (float(phase_queues[0][1]), float(phase_queues[1][1]))
    if measured_first < 0 or measured_second < 0:
        raise ValueError("Green-phase queues cannot be negative.")

    # Keep any queue not assigned to a green phase in the model, split evenly
    # because its movement is not observable from the current SUMO program.
    unattributed_queue = max(0.0, float(state.queue_length) - measured_first - measured_second)
    demand = (measured_first + unattributed_queue / 2, measured_second + unattributed_queue / 2)
    candidate_seconds = tuple(int(value) for value in settings["candidate_green_seconds"])
    if not candidate_seconds:
        raise ValueError("At least one candidate green duration is required.")

    candidates = tuple(
        TimingCandidate(
            variable_index=index,
            first_green_seconds=first,
            second_green_seconds=second,
            valid=_is_valid_timing(first, second, settings),
        )
        for index, (first, second) in enumerate(product(candidate_seconds, repeat=2))
    )
    costs = tuple(_candidate_cost(candidate, demand, state, settings) for candidate in candidates)
    maximum_cost = max(cost.total for cost in costs)
    one_hot_penalty = max(float(settings["one_hot_penalty"]), maximum_cost + 1.0)
    invalid_timing_penalty = max(float(settings["invalid_timing_penalty"]), maximum_cost + 1.0)

    size = len(candidates)
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    for candidate, cost in zip(candidates, costs):
        matrix[candidate.variable_index][candidate.variable_index] = cost.total - one_hot_penalty
        if not candidate.valid:
            matrix[candidate.variable_index][candidate.variable_index] += invalid_timing_penalty
    for row in range(size):
        for column in range(row + 1, size):
            matrix[row][column] = 2.0 * one_hot_penalty

    variable_names = tuple(
        f"x_p{phase_ids[0]}_{candidate.first_green_seconds}_p{phase_ids[1]}_{candidate.second_green_seconds}"
        for candidate in candidates
    )
    return QuboModel(
        state=state,
        phase_ids=phase_ids,
        phase_queues=demand,
        variable_names=variable_names,
        candidates=candidates,
        candidate_costs=costs,
        matrix=tuple(tuple(row) for row in matrix),
        offset=one_hot_penalty,
        one_hot_penalty=one_hot_penalty,
        invalid_timing_penalty=invalid_timing_penalty,
    )


def _candidate_cost(
    candidate: TimingCandidate,
    demand: tuple[float, float],
    state: IntersectionTrafficState,
    settings: Mapping[str, Any],
) -> CostBreakdown:
    first_green = candidate.first_green_seconds
    second_green = candidate.second_green_seconds
    maximum_green = float(settings["max_green_seconds"])
    total_demand = sum(demand)
    demand_share = demand[0] / total_demand if total_demand else 0.5
    congestion_scale = 1.0 + float(state.traffic_density) + (
        float(state.vehicle_count) / max(1, int(state.road_capacity))
    )
    waiting = float(settings["waiting_weight"]) * congestion_scale * (
        demand[0] * (1.0 - first_green / maximum_green) ** 2
        + demand[1] * (1.0 - second_green / maximum_green) ** 2
    )
    imbalance = float(settings["imbalance_weight"]) * total_demand * (
        first_green / (first_green + second_green) - demand_share
    ) ** 2
    target_total = float(settings["target_total_green_seconds"])
    cycle = float(settings["cycle_weight"]) * (
        (first_green + second_green - target_total) / target_total
    ) ** 2
    return CostBreakdown(waiting=waiting, imbalance=imbalance, cycle=cycle)


def _is_valid_timing(first_green: int, second_green: int, settings: Mapping[str, Any]) -> bool:
    minimum = int(settings["min_green_seconds"])
    maximum = int(settings["max_green_seconds"])
    cycle_seconds = first_green + second_green + 2 * int(settings["yellow_seconds"])
    return (
        minimum <= first_green <= maximum
        and minimum <= second_green <= maximum
        and int(settings["min_cycle_seconds"]) <= cycle_seconds <= int(settings["max_cycle_seconds"])
    )
