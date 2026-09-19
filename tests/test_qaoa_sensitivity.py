from optimization.quantum.sensitivity import SensitivityRecord, summarize_sensitivity


def record(state_label: str, exact_match: bool, gap: float | None) -> SensitivityRecord:
    return SensitivityRecord(
        state_label=state_label,
        seed=42,
        exact_objective=1.0,
        qaoa_objective=1.0 + gap if gap is not None else None,
        exact_match=exact_match,
        objective_gap=gap,
        selected_first_green_seconds=30,
        selected_second_green_seconds=30,
        shots=2048,
        repetitions=2,
    )


def test_sensitivity_summary_calculates_overall_and_per_state_recovery_rates() -> None:
    summary = summarize_sensitivity(
        [
            record("balanced", True, 0.0),
            record("balanced", True, 0.0),
            record("phase_2_heavy", False, 2.0),
            record("phase_2_heavy", False, 4.0),
        ]
    )
    assert summary.observations == 4
    assert summary.exact_optimum_recovery_rate == 0.5
    assert summary.average_objective_gap == 1.5
    assert summary.per_state_recovery_rate == {"balanced": 1.0, "phase_2_heavy": 0.0}
