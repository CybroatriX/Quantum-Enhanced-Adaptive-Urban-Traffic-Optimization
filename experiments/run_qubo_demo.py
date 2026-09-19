"""Run the reproducible Phase 3A state -> QUBO -> exact-solver validation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from config.loader import load_config
from optimization.quantum.validation import validate_state
from simulation.models.state import IntersectionTrafficState, SignalState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = PROJECT_ROOT / "data" / "results" / "phase3a_qubo_validation.csv"


def validation_states() -> list[tuple[str, IntersectionTrafficState]]:
    """Deterministic representative states using the real state data contract.

    They are deliberately declared here instead of presented as measured SUMO
    outcomes.  A later online controller can pass states emitted by
    TrafficStateReader directly to the same validation function.
    """
    return [
        (
            "balanced",
            IntersectionTrafficState(
                "J1", 16, 12, 0.125, 96, SignalState.GREEN, 0,
                green_phase_queues=((0, 6), (2, 6)),
            ),
        ),
        (
            "phase_0_heavy",
            IntersectionTrafficState(
                "J1", 30, 24, 0.3125, 96, SignalState.GREEN, 0,
                green_phase_queues=((0, 20), (2, 4)),
            ),
        ),
        (
            "phase_2_heavy",
            IntersectionTrafficState(
                "J1", 30, 24, 0.3125, 96, SignalState.GREEN, 2,
                green_phase_queues=((0, 4), (2, 20)),
            ),
        ),
    ]


def run_demo(output_path: Path = RESULT_PATH) -> list[dict[str, object]]:
    settings = load_config()["optimization"]["phase3a"]
    rows: list[dict[str, object]] = []
    for label, state in validation_states():
        result = validate_state(state, settings)
        selected_index = result.solution.candidate.variable_index
        cost = result.model.candidate_costs[selected_index]
        row: dict[str, object] = {
            "state_label": label,
            "intersection_id": state.intersection_id,
            "vehicle_count": state.vehicle_count,
            "queue_length": state.queue_length,
            "traffic_density": state.traffic_density,
            "road_capacity": state.road_capacity,
            "current_signal_phase": state.signal_phase,
            "green_phase_queues": json.dumps(dict(state.green_phase_queues)),
            "selected_variable": result.model.variable_names[selected_index],
            "selected_green_phase_0_seconds": result.solution.candidate.first_green_seconds,
            "selected_green_phase_2_seconds": result.solution.candidate.second_green_seconds,
            "objective_value": round(result.solution.objective_value, 6),
            "waiting_term": round(cost.waiting, 6),
            "imbalance_term": round(cost.imbalance, 6),
            "cycle_term": round(cost.cycle, 6),
            "assignments_evaluated": result.solution.assignments_evaluated,
            "variable_mapping": json.dumps(list(result.model.variable_names)),
            "qubo_upper_triangular_matrix": json.dumps(result.model.matrix_as_lists()),
        }
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    rows = run_demo()
    print(f"Wrote {len(rows)} exact-validation rows to {RESULT_PATH}")
    for row in rows:
        print(
            f"{row['state_label']}: "
            f"phase 0={row['selected_green_phase_0_seconds']}s, "
            f"phase 2={row['selected_green_phase_2_seconds']}s, "
            f"objective={row['objective_value']}"
        )


if __name__ == "__main__":
    main()
