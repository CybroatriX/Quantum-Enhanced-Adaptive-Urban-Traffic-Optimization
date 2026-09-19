"""Run fair fixed-versus-adaptive classical comparisons and write a CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from simulation.run import run_simulation


DEFAULT_OUTPUT = Path("data/results/classical_comparison.csv")


def run_comparison(duration: int = 900, output: str | Path = DEFAULT_OUTPUT) -> list[dict[str, object]]:
    """Run each controller with identical duration and seed within each scenario."""
    rows: list[dict[str, object]] = []
    for scenario in ("low", "normal", "high"):
        for controller in ("fixed", "adaptive"):
            result = run_simulation(scenario=scenario, duration=duration, controller_mode=controller)
            metrics = result["metrics"]
            rows.append(
                {
                    "scenario": scenario.title(),
                    "controller": controller.title(),
                    "duration_seconds": result["duration_seconds"],
                    "random_seed": result["random_seed"],
                    "average_waiting_time_seconds": metrics["average_waiting_time_seconds"],
                    "total_waiting_time_seconds": metrics["total_waiting_time_seconds"],
                    "average_queue_length": metrics["average_queue_length"],
                    "throughput_vehicles_per_hour": metrics["throughput_vehicles_per_hour"],
                }
            )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare fixed and classical adaptive SUMO controllers.")
    parser.add_argument("--duration", type=int, default=900)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    rows = run_comparison(args.duration, args.output)
    for row in rows:
        print(row)
    print(f"CSV written to: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
