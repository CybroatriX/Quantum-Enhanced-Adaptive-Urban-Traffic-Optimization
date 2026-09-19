from __future__ import annotations

from copy import deepcopy

import pytest

from config.loader import load_config
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from simulation.models.state import IntersectionTrafficState, SignalState


def settings() -> dict:
    return deepcopy(load_config()["optimization"]["phase3a"])


def state(first_queue: int = 6, second_queue: int = 6) -> IntersectionTrafficState:
    return IntersectionTrafficState(
        "J1", first_queue + second_queue + 4, first_queue + second_queue, 0.2, 96,
        SignalState.GREEN, 0, green_phase_queues=((0, first_queue), (2, second_queue)),
    )


def test_qubo_has_one_binary_variable_per_timing_pair() -> None:
    model = build_qubo(state(), settings())
    assert len(model.variable_names) == 9
    assert model.variable_names[0] == "x_p0_22_p2_22"
    assert len(model.matrix) == len(model.matrix[0]) == 9


def test_qubo_matrix_uses_upper_triangular_representation() -> None:
    model = build_qubo(state(), settings())
    assert model.offset == model.one_hot_penalty
    assert all(model.matrix[row][column] == 0.0 for row in range(9) for column in range(row))
    assert model.matrix[0][1] == 2 * model.one_hot_penalty


def test_one_hot_constraint_penalizes_zero_and_multiple_selections() -> None:
    model = build_qubo(state(), settings())
    selected = (1,) + (0,) * 8
    none = (0,) * 9
    multiple = (1, 1) + (0,) * 7
    assert model.energy(selected) < model.energy(none)
    assert model.energy(selected) < model.energy(multiple)


def test_invalid_candidate_receives_an_explicit_penalty() -> None:
    custom_settings = settings()
    custom_settings["candidate_green_seconds"] = [10, 30]
    model = build_qubo(state(), custom_settings)
    invalid_index = next(index for index, candidate in enumerate(model.candidates) if not candidate.valid)
    valid_index = next(index for index, candidate in enumerate(model.candidates) if candidate.valid)
    invalid = tuple(int(index == invalid_index) for index in range(4))
    valid = tuple(int(index == valid_index) for index in range(4))
    assert model.energy(invalid) > model.energy(valid)


def test_exact_solver_enumerates_every_binary_assignment_and_returns_valid_plan() -> None:
    model = build_qubo(state(20, 4), settings())
    solution = solve_exact(model)
    assert solution.assignments_evaluated == 2 ** len(model.variable_names)
    assert sum(solution.assignment) == 1
    assert solution.candidate.valid is True
    assert solution.candidate.first_green_seconds > solution.candidate.second_green_seconds


def test_balanced_and_reverse_imbalanced_states_choose_different_valid_timings() -> None:
    balanced = solve_exact(build_qubo(state(6, 6), settings())).candidate
    reverse = solve_exact(build_qubo(state(4, 20), settings())).candidate
    assert (balanced.first_green_seconds, balanced.second_green_seconds) == (30, 30)
    assert reverse.second_green_seconds > reverse.first_green_seconds


def test_missing_phase_queue_measurements_are_rejected() -> None:
    incomplete = IntersectionTrafficState("J1", 10, 5, 0.1, 96, SignalState.GREEN, 0)
    with pytest.raises(ValueError, match="exactly two"):
        build_qubo(incomplete, settings())
