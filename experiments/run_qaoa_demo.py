"""Run Phase 3B QAOA/Aer validation against Phase 3A exact ground truth."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from config.loader import load_config
from experiments.run_qubo_demo import validation_states
from optimization.quantum.qaoa import matches_exact, run_qaoa
from optimization.quantum.validation import validate_state

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = PROJECT_ROOT / "data" / "results" / "phase3b_qaoa_validation.csv"


def run_demo(output_path: Path = RESULT_PATH) -> list[dict[str, object]]:
    config = load_config()
    phase3a_settings = config["optimization"]["phase3a"]
    qaoa_settings = config["optimization"]["phase3b"]
    rows: list[dict[str, object]] = []
    for label, state in validation_states():
        exact = validate_state(state, phase3a_settings)
        qaoa = run_qaoa(exact.model, qaoa_settings)
        sampled = qaoa.best_valid_solution
        qaoa_objective = sampled.objective_value if sampled else None
        exact_match = matches_exact(qaoa_objective, exact.solution.objective_value) if sampled else False
        objective_gap = qaoa_objective - exact.solution.objective_value if sampled else None
        approximation_ratio = (
            exact.solution.objective_value / qaoa_objective
            if sampled and qaoa_objective and qaoa_objective > 0
            else None
        )
        rows.append(
            {
                "state_label": label,
                "traffic_state": json.dumps(state.to_dict()),
                "exact_variable": exact.model.variable_names[exact.solution.candidate.variable_index],
                "exact_green_phase_0_seconds": exact.solution.candidate.first_green_seconds,
                "exact_green_phase_2_seconds": exact.solution.candidate.second_green_seconds,
                "exact_objective": round(exact.solution.objective_value, 6),
                "qaoa_variable": exact.model.variable_names[sampled.candidate.variable_index] if sampled else None,
                "qaoa_bitstring": sampled.bitstring if sampled else None,
                "qaoa_green_phase_0_seconds": sampled.candidate.first_green_seconds if sampled else None,
                "qaoa_green_phase_2_seconds": sampled.candidate.second_green_seconds if sampled else None,
                "qaoa_objective": round(qaoa_objective, 6) if sampled else None,
                "found_exact_optimum": exact_match,
                "objective_gap": round(objective_gap, 6) if objective_gap is not None else None,
                "approximation_ratio": round(approximation_ratio, 6) if approximation_ratio is not None else None,
                "qaoa_repetitions": qaoa.options.repetitions,
                "shots": qaoa.options.shots,
                "random_seed": qaoa.options.random_seed,
                "optimizer": qaoa.options.optimizer,
                "optimizer_maxiter": qaoa.options.optimizer_maxiter,
                "simulator": "Qiskit AerSimulator (statevector optimization; shot sampling)",
                "expected_qubo_objective": round(qaoa.expected_qubo_objective, 6),
                "valid_sampled_solution_count": 0,
                "sample_counts": json.dumps(qaoa.counts, sort_keys=True),
            }
        )
        # Count valid distinct bitstrings using the unmodified QUBO decoder.
        rows[-1]["valid_sampled_solution_count"] = sum(
            1
            for bitstring in qaoa.counts
            if _is_valid_bitstring(exact.model, bitstring)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _is_valid_bitstring(model, bitstring: str) -> bool:
    from optimization.quantum.qaoa import assignment_from_bitstring

    try:
        model.selected_candidate(assignment_from_bitstring(bitstring, len(model.variable_names)))
    except ValueError:
        return False
    return True


def main() -> None:
    rows = run_demo()
    print(f"Wrote {len(rows)} QAOA validation rows to {RESULT_PATH}")
    for row in rows:
        print(
            f"{row['state_label']}: exact={row['exact_objective']}, "
            f"qaoa={row['qaoa_objective']}, exact_match={row['found_exact_optimum']}"
        )


if __name__ == "__main__":
    main()
