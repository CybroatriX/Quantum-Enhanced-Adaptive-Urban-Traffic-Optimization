from __future__ import annotations

from copy import deepcopy

import pytest

from config.loader import load_config
from optimization.quantum.qaoa import (
    QaoaOptions,
    assignment_from_bitstring,
    build_qaoa_circuit,
    matches_exact,
    qubo_to_ising,
    run_qaoa,
)
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from simulation.models.state import IntersectionTrafficState, SignalState


def model():
    settings = deepcopy(load_config()["optimization"]["phase3a"])
    state = IntersectionTrafficState(
        "J1", 16, 12, 0.125, 96, SignalState.GREEN, 0,
        green_phase_queues=((0, 6), (2, 6)),
    )
    return build_qubo(state, settings)


def test_qubo_to_ising_preserves_energy_for_every_binary_assignment() -> None:
    qubo = model()
    ising = qubo_to_ising(qubo)
    assert ising.num_qubits == len(qubo.variable_names) == 9
    for integer in range(2 ** ising.num_qubits):
        assignment = tuple((integer >> qubit) & 1 for qubit in range(ising.num_qubits))
        z_values = tuple(1 - 2 * value for value in assignment)
        ising_energy = ising.constant + sum(
            coefficient * z_values[index] for index, coefficient in enumerate(ising.z_coefficients)
        ) + sum(
            coefficient * z_values[first] * z_values[second]
            for first, second, coefficient in ising.zz_coefficients
        )
        assert ising_energy == pytest.approx(qubo.energy(assignment))


def test_qiskit_bitstring_order_maps_back_to_qubo_variables() -> None:
    assert assignment_from_bitstring("000000001", 9) == (1, 0, 0, 0, 0, 0, 0, 0, 0)
    assert assignment_from_bitstring("100000000", 9) == (0, 0, 0, 0, 0, 0, 0, 0, 1)


def test_qaoa_options_are_configurable_and_reproducible() -> None:
    options = QaoaOptions.from_settings(load_config()["optimization"]["phase3b"])
    assert options.repetitions == 2
    assert options.shots == 2048
    assert options.random_seed == 42


def test_qaoa_circuit_has_one_qubit_per_phase3a_binary_variable() -> None:
    pytest.importorskip("qiskit")
    circuit, parameters = build_qaoa_circuit(qubo_to_ising(model()), repetitions=2, measure=True)
    assert circuit.num_qubits == 9
    assert len(parameters) == 4
    assert circuit.num_clbits == 9


def test_aer_samples_decode_to_valid_timing_and_compare_with_exact() -> None:
    pytest.importorskip("qiskit_aer")
    qubo = model()
    qaoa = run_qaoa(qubo, load_config()["optimization"]["phase3b"])
    assert qaoa.counts
    assert qaoa.best_valid_solution is not None
    assert qaoa.best_valid_solution.candidate.valid is True
    exact = solve_exact(qubo)
    assert isinstance(matches_exact(qaoa.best_valid_solution.objective_value, exact.objective_value), bool)
