"""Qiskit Aer QAOA validation for the unchanged Phase-3A QUBO."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Any, Mapping

from optimization.quantum.qubo import QuboModel, TimingCandidate


@dataclass(frozen=True)
class IsingCostHamiltonian:
    """Diagonal Ising form of a QUBO, excluding its global-energy constant."""

    constant: float
    z_coefficients: tuple[float, ...]
    zz_coefficients: tuple[tuple[int, int, float], ...]

    @property
    def num_qubits(self) -> int:
        return len(self.z_coefficients)


@dataclass(frozen=True)
class QaoaOptions:
    repetitions: int
    shots: int
    random_seed: int
    optimizer: str
    optimizer_maxiter: int

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> "QaoaOptions":
        options = cls(
            repetitions=int(settings["repetitions"]),
            shots=int(settings["shots"]),
            random_seed=int(settings["random_seed"]),
            optimizer=str(settings["optimizer"]),
            optimizer_maxiter=int(settings["optimizer_maxiter"]),
        )
        if options.repetitions <= 0 or options.shots <= 0 or options.optimizer_maxiter <= 0:
            raise ValueError("QAOA repetitions, shots, and optimizer iterations must be positive.")
        if options.optimizer.upper() != "COBYLA":
            raise ValueError("Phase 3B currently supports the COBYLA optimizer only.")
        return options


@dataclass(frozen=True)
class QaoaSolution:
    bitstring: str
    assignment: tuple[int, ...]
    candidate: TimingCandidate
    objective_value: float
    sample_count: int


@dataclass(frozen=True)
class QaoaResult:
    hamiltonian: IsingCostHamiltonian
    options: QaoaOptions
    optimized_parameters: tuple[float, ...]
    expected_qubo_objective: float
    counts: dict[str, int]
    best_valid_solution: QaoaSolution | None


def qubo_to_ising(model: QuboModel) -> IsingCostHamiltonian:
    """Map x_i=(1-Z_i)/2 without changing the Phase-3A QUBO energy."""
    size = len(model.variable_names)
    constant = model.offset
    z = [0.0] * size
    zz: list[tuple[int, int, float]] = []
    for index in range(size):
        diagonal = model.matrix[index][index]
        constant += diagonal / 2.0
        z[index] -= diagonal / 2.0
    for first in range(size):
        for second in range(first + 1, size):
            coefficient = model.matrix[first][second]
            if not coefficient:
                continue
            constant += coefficient / 4.0
            z[first] -= coefficient / 4.0
            z[second] -= coefficient / 4.0
            zz.append((first, second, coefficient / 4.0))
    return IsingCostHamiltonian(constant, tuple(z), tuple(zz))


def assignment_from_bitstring(bitstring: str, number_of_qubits: int) -> tuple[int, ...]:
    """Convert Qiskit's high-to-low count key into QUBO variable order."""
    normalized = bitstring.replace(" ", "")
    if len(normalized) != number_of_qubits or set(normalized) - {"0", "1"}:
        raise ValueError("Bitstring does not match the QUBO qubit count.")
    return tuple(int(bit) for bit in reversed(normalized))


def build_qaoa_circuit(
    hamiltonian: IsingCostHamiltonian,
    repetitions: int,
    measure: bool = False,
):
    """Build |+> -> alternating cost/mixer layers -> optional measurement."""
    if repetitions <= 0:
        raise ValueError("QAOA repetitions must be positive.")
    QuantumCircuit, ParameterVector = _qiskit_circuit_types()
    circuit = QuantumCircuit(hamiltonian.num_qubits)
    gamma = ParameterVector("gamma", repetitions)
    beta = ParameterVector("beta", repetitions)
    circuit.h(range(hamiltonian.num_qubits))
    for layer in range(repetitions):
        for qubit, coefficient in enumerate(hamiltonian.z_coefficients):
            if coefficient:
                circuit.rz(2.0 * gamma[layer] * coefficient, qubit)
        for first, second, coefficient in hamiltonian.zz_coefficients:
            circuit.rzz(2.0 * gamma[layer] * coefficient, first, second)
        for qubit in range(hamiltonian.num_qubits):
            circuit.rx(2.0 * beta[layer], qubit)
    if measure:
        circuit.measure_all()
    return circuit, tuple(gamma) + tuple(beta)


def run_qaoa(model: QuboModel, settings: Mapping[str, Any]) -> QaoaResult:
    """Optimize QAOA on Aer, then score samples with the original QUBO."""
    options = QaoaOptions.from_settings(settings)
    AerSimulator, minimize, numpy, transpile = _qiskit_runtime_types()
    hamiltonian = qubo_to_ising(model)
    ansatz, parameters = build_qaoa_circuit(hamiltonian, options.repetitions)
    statevector_backend = AerSimulator(method="statevector", seed_simulator=options.random_seed)
    transpiled_ansatz = transpile(ansatz, statevector_backend, seed_transpiler=options.random_seed)
    generator = numpy.random.default_rng(options.random_seed)
    initial_parameters = numpy.concatenate(
        (
            generator.uniform(0.0, 2.0 * numpy.pi, options.repetitions),
            generator.uniform(0.0, numpy.pi, options.repetitions),
        )
    )

    def expected_objective(values):
        bound = transpiled_ansatz.assign_parameters(dict(zip(parameters, values)), inplace=False)
        bound.save_statevector()
        result = statevector_backend.run(bound).result()
        vector = numpy.asarray(result.get_statevector(bound))
        probabilities = numpy.abs(vector) ** 2
        return float(
            sum(
                float(probability) * model.energy(tuple((index >> qubit) & 1 for qubit in range(hamiltonian.num_qubits)))
                for index, probability in enumerate(probabilities)
            )
        )

    optimization = minimize(
        expected_objective,
        initial_parameters,
        method=options.optimizer,
        options={"maxiter": options.optimizer_maxiter},
    )
    optimized = tuple(float(value) for value in optimization.x)
    measured, measured_parameters = build_qaoa_circuit(hamiltonian, options.repetitions, measure=True)
    bound_measured = measured.assign_parameters(dict(zip(measured_parameters, optimized)), inplace=False)
    sampling_backend = AerSimulator(seed_simulator=options.random_seed)
    transpiled_measured = transpile(bound_measured, sampling_backend, seed_transpiler=options.random_seed)
    counts = dict(sampling_backend.run(transpiled_measured, shots=options.shots).result().get_counts())
    valid_solutions = _valid_sampled_solutions(model, counts)
    return QaoaResult(
        hamiltonian=hamiltonian,
        options=options,
        optimized_parameters=optimized,
        expected_qubo_objective=expected_objective(optimized),
        counts=counts,
        best_valid_solution=min(valid_solutions, key=lambda result: (result.objective_value, -result.sample_count))
        if valid_solutions
        else None,
    )


def matches_exact(qaoa_objective: float, exact_objective: float) -> bool:
    return isclose(qaoa_objective, exact_objective, rel_tol=1e-9, abs_tol=1e-9)


def _valid_sampled_solutions(model: QuboModel, counts: Mapping[str, int]) -> list[QaoaSolution]:
    solutions: list[QaoaSolution] = []
    for bitstring, sample_count in counts.items():
        assignment = assignment_from_bitstring(bitstring, len(model.variable_names))
        try:
            candidate = model.selected_candidate(assignment)
        except ValueError:
            continue
        solutions.append(
            QaoaSolution(bitstring, assignment, candidate, model.energy(assignment), int(sample_count))
        )
    return solutions


def _qiskit_circuit_types():
    try:
        from qiskit import QuantumCircuit
        from qiskit.circuit import ParameterVector
    except ImportError as error:
        raise RuntimeError("Qiskit is required for Phase 3B. Install requirements.txt.") from error
    return QuantumCircuit, ParameterVector


def _qiskit_runtime_types():
    try:
        import numpy
        from qiskit import transpile
        from qiskit_aer import AerSimulator
        from scipy.optimize import minimize
    except ImportError as error:
        raise RuntimeError("Qiskit, Qiskit Aer, NumPy, and SciPy are required for Phase 3B.") from error
    return AerSimulator, minimize, numpy, transpile
