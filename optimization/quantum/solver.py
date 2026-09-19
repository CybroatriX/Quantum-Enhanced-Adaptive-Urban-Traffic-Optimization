"""Exact classical validation for the small Phase 3A QUBO."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from optimization.quantum.qubo import QuboModel, TimingCandidate


@dataclass(frozen=True)
class ExactSolution:
    assignment: tuple[int, ...]
    candidate: TimingCandidate
    objective_value: float
    assignments_evaluated: int


def solve_exact(model: QuboModel) -> ExactSolution:
    """Enumerate every binary assignment and return the minimum valid plan."""
    assignments = product((0, 1), repeat=len(model.variable_names))
    valid_assignments: list[tuple[float, tuple[int, ...]]] = []
    assignments_evaluated = 0
    for assignment in assignments:
        assignments_evaluated += 1
        try:
            model.selected_candidate(assignment)
        except ValueError:
            continue
        valid_assignments.append((model.energy(assignment), assignment))
    if not valid_assignments:
        raise RuntimeError("No valid signal-timing assignment exists for this QUBO.")
    objective_value, assignment = min(valid_assignments, key=lambda item: (item[0], item[1]))
    return ExactSolution(
        assignment=assignment,
        candidate=model.selected_candidate(assignment),
        objective_value=objective_value,
        assignments_evaluated=assignments_evaluated,
    )
