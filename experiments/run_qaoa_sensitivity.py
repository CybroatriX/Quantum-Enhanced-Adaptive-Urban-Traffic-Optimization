"""Seed-only robustness experiment for the existing Phase 3B QAOA workflow."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from config.loader import load_config
from experiments.run_qubo_demo import validation_states
from optimization.quantum.qaoa import matches_exact, run_qaoa
from optimization.quantum.sensitivity import SensitivityRecord, summarize_sensitivity
from optimization.quantum.validation import validate_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = PROJECT_ROOT / "data" / "results" / "phase3b_qaoa_sensitivity.csv"
SUMMARY_PATH = PROJECT_ROOT / "data" / "results" / "phase3b_qaoa_sensitivity_summary.csv"


def run_sensitivity(
    output_path: Path = RESULT_PATH, summary_path: Path = SUMMARY_PATH
) -> tuple[list[SensitivityRecord], dict[str, object]]:
    config = load_config()
    phase3a_settings = config["optimization"]["phase3a"]
    base_qaoa_settings = dict(config["optimization"]["phase3b"])
    records: list[SensitivityRecord] = []
    for seed in base_qaoa_settings["sensitivity_seeds"]:
        qaoa_settings = {**base_qaoa_settings, "random_seed": int(seed)}
        for label, state in validation_states():
            exact = validate_state(state, phase3a_settings)
            qaoa = run_qaoa(exact.model, qaoa_settings)
            sampled = qaoa.best_valid_solution
            qaoa_objective = sampled.objective_value if sampled else None
            records.append(
                SensitivityRecord(
                    state_label=label,
                    seed=int(seed),
                    exact_objective=exact.solution.objective_value,
                    qaoa_objective=qaoa_objective,
                    exact_match=matches_exact(qaoa_objective, exact.solution.objective_value)
                    if sampled
                    else False,
                    objective_gap=qaoa_objective - exact.solution.objective_value if sampled else None,
                    selected_first_green_seconds=sampled.candidate.first_green_seconds if sampled else None,
                    selected_second_green_seconds=sampled.candidate.second_green_seconds if sampled else None,
                    shots=qaoa.options.shots,
                    repetitions=qaoa.options.repetitions,
                )
            )

    summary = summarize_sensitivity(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(asdict(records[0])))
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)
    summary_row: dict[str, object] = {
        "observations": summary.observations,
        "exact_optimum_recovery_rate": summary.exact_optimum_recovery_rate,
        "average_objective_gap": summary.average_objective_gap,
        **{f"{label}_recovery_rate": rate for label, rate in summary.per_state_recovery_rate.items()},
    }
    with summary_path.open("w", newline="", encoding="utf-8") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=list(summary_row))
        writer.writeheader()
        writer.writerow(summary_row)
    return records, summary_row


def main() -> None:
    records, summary = run_sensitivity()
    print(f"Wrote {len(records)} seed/state rows to {RESULT_PATH}")
    print(f"Wrote recovery summary to {SUMMARY_PATH}")
    print(
        f"exact_recovery_rate={summary['exact_optimum_recovery_rate']:.3f}, "
        f"average_objective_gap={summary['average_objective_gap']}"
    )


if __name__ == "__main__":
    main()
