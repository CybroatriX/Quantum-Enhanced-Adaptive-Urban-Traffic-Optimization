"""Reusable helpers for state -> QUBO -> exact classical validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from optimization.quantum.qubo import QuboModel, build_qubo
from optimization.quantum.solver import ExactSolution, solve_exact
from simulation.models.state import IntersectionTrafficState


@dataclass(frozen=True)
class ValidationResult:
    state: IntersectionTrafficState
    model: QuboModel
    solution: ExactSolution


def validate_state(
    state: IntersectionTrafficState, settings: Mapping[str, Any]
) -> ValidationResult:
    model = build_qubo(state, settings)
    return ValidationResult(state=state, model=model, solution=solve_exact(model))
