"""Future hybrid quantum-classical traffic optimizer."""
"""Phase 3A QUBO formulation and exact classical validation."""

from optimization.quantum.qubo import QuboModel, TimingCandidate, build_qubo
from optimization.quantum.qaoa import QaoaResult, qubo_to_ising, run_qaoa
from optimization.quantum.solver import ExactSolution, solve_exact

__all__ = [
    "ExactSolution",
    "QaoaResult",
    "QuboModel",
    "TimingCandidate",
    "build_qubo",
    "qubo_to_ising",
    "run_qaoa",
    "solve_exact",
]
