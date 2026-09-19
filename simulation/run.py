"""CLI entry point for the Phase-1 fixed-time SUMO simulation."""

from __future__ import annotations

import argparse
from pathlib import Path

from config.loader import load_config
from metrics.collector import MetricsCollector
from simulation.network.build_network import build_network
from simulation.runner import SumoRunner
from simulation.signals.adaptive import AdaptiveSignalController
from simulation.signals.fixed_time import FixedTimeController
from simulation.state_reader import TrafficStateReader
from simulation.traffic.demand import generate_routes


def run_simulation(
    config_path: str | None = None,
    scenario: str | None = None,
    duration: int | None = None,
    controller_mode: str | None = None,
) -> dict[str, object]:
    """Run one reproducible fixed or classical-adaptive traffic experiment."""
    config = load_config(config_path)
    if duration is not None:
        config["simulation"]["duration_seconds"] = duration
    selected_scenario = scenario or config["traffic"]["default_scenario"]
    selected_controller = controller_mode or config["controller"]["default_mode"]
    if selected_controller not in {"fixed", "adaptive"}:
        raise ValueError("controller_mode must be 'fixed' or 'adaptive'.")
    if not Path(config["network"]["network_file"]).exists():
        build_network()
    generate_routes(config, selected_scenario)
    sim_config = config["simulation"]
    with SumoRunner(config["network"]["sumo_config_file"], sim_config["step_length_seconds"], sim_config["gui"], sim_config["random_seed"]) as traci_connection:
        intersection_ids = config["network"]["intersection_ids"]
        if selected_controller == "fixed":
            controller = FixedTimeController(traci_connection, config["signals"]["fixed_time"])
        else:
            controller = AdaptiveSignalController(traci_connection, config["signals"]["adaptive"])
        controller.configure(intersection_ids)
        reader = TrafficStateReader(traci_connection, config["network"]["vehicles_per_lane_capacity"])
        metrics = MetricsCollector(traci_connection)
        latest_state = []
        for _ in range(int(sim_config["duration_seconds"] / sim_config["step_length_seconds"])):
            traci_connection.simulationStep()
            latest_state = reader.read_all(intersection_ids)
            if selected_controller == "adaptive":
                controller.step(latest_state)
            metrics.record_step(latest_state)
        return {
            "scenario": selected_scenario,
            "controller": selected_controller,
            "duration_seconds": sim_config["duration_seconds"],
            "random_seed": sim_config["random_seed"],
            "intersections": [state.to_dict() for state in latest_state],
            "metrics": metrics.snapshot().to_dict(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a fixed or classical-adaptive traffic simulation.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--scenario", choices=["low", "normal", "high"], default=None)
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--controller", choices=["fixed", "adaptive"], default=None)
    args = parser.parse_args()
    print(run_simulation(args.config, args.scenario, args.duration, args.controller))


if __name__ == "__main__":
    main()
