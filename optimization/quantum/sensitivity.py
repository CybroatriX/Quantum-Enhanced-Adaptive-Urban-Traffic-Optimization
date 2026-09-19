"""Aggregation helpers for Phase 3B seed-sensitivity experiments."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean


@dataclass(frozen=True)
class SensitivityRecord:
    state_label: str
    seed: int
    exact_objective: float
    qaoa_objective: float | None
    exact_match: bool
    objective_gap: float | None
    selected_first_green_seconds: int | None
    selected_second_green_seconds: int | None
    shots: int
    repetitions: int


@dataclass(frozen=True)
class RecoverySummary:
    observations: int
    exact_optimum_recovery_rate: float
    average_objective_gap: float | None
    per_state_recovery_rate: dict[str, float]


def summarize_sensitivity(records: list[SensitivityRecord]) -> RecoverySummary:
    if not records:
        raise ValueError("At least one sensitivity record is required.")
    recovery_rate = sum(record.exact_match for record in records) / len(records)
    gaps = [record.objective_gap for record in records if record.objective_gap is not None]
    state_labels = sorted({record.state_label for record in records})
    per_state = {
        label: sum(record.exact_match for record in records if record.state_label == label)
        / sum(record.state_label == label for record in records)
        for label in state_labels
    }
    return RecoverySummary(
        observations=len(records),
        exact_optimum_recovery_rate=recovery_rate,
        average_objective_gap=fmean(gaps) if gaps else None,
        per_state_recovery_rate=per_state,
    )
