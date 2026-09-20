"""Unit tests for Phase N: Classical vs Quantum Evaluation Benchmark.

Tests experiment configuration, deterministic repeatability, baseline deltas,
metrics collection, summary statistics, QAOA recovery analysis, failure handling,
and result serialization using small synthetic fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import pytest

from experiments.run_classical_vs_quantum import (
    calculate_baseline_deltas,
    calculate_qaoa_analysis,
    calculate_statistical_summary,
    export_results,
    load_experiment_config,
)
from optimization.quantum.qubo import build_qubo
from optimization.quantum.solver import solve_exact
from simulation.models.state import IntersectionTrafficState, SignalState

SCRATCH_DIR = Path("tests/_test_scratch_phase_n")


@pytest.fixture(autouse=True)
def clean_scratch():
    """Ensure safe isolated test directory on Windows without tempfile permission issues."""
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)


def test_experiment_config_validity() -> None:
    """Validate machine-readable experiment configuration schema and parameters."""
    config = load_experiment_config()

    assert config["phase"] == "Phase N"
    assert "Classical vs Quantum" in config["title"]

    # 4 controllers required
    ctrl_names = [c["name"] for c in config["controllers"]]
    assert ctrl_names == ["Fixed-Time", "Classical Adaptive", "QUBO Exact", "QAOA"]

    # Required scenarios
    assert set(config["traffic_scenarios"].keys()) == {"Low", "Normal", "High"}

    # Predefined reproducible seeds (minimum 5 seeds)
    seeds = config["seeds"]
    assert len(seeds) >= 5
    assert seeds == [42, 101, 202, 303, 404]

    # Identical simulation duration
    duration = config["simulation_parameters"]["duration_seconds"]
    assert duration > 0.0

    # QAOA parameters
    qaoa_cfg = next(c for c in config["controllers"] if c["name"] == "QAOA")["settings"]
    assert qaoa_cfg["repetitions_p"] == 2
    assert qaoa_cfg["shots"] == 2048
    assert qaoa_cfg["optimizer"] == "COBYLA"


def test_identical_conditions_invariant() -> None:
    """Verify that network, duration, and intersection set are invariant across controllers."""
    config = load_experiment_config()
    sim_params = config["simulation_parameters"]

    assert sim_params["intersection_ids"] == ["J1", "J2", "J3", "J4"]
    assert sim_params["duration_seconds"] == 60.0
    assert sim_params["step_length_seconds"] == 1.0
    assert Path(sim_params["network_file"]).name == "four_intersection.net.xml"


def test_deterministic_repeated_classical_runs() -> None:
    """Verify that exact QUBO solver produces identical results on identical traffic state."""
    state = IntersectionTrafficState(
        intersection_id="J1",
        vehicle_count=20,
        queue_length=14,
        traffic_density=0.2083,
        road_capacity=96,
        signal_state=SignalState.GREEN,
        signal_phase=0,
        emergency_status=False,
        green_phase_queues=((0, 10), (2, 4)),
    )
    from config.loader import load_config
    settings = load_config()["optimization"]["phase3a"]

    model1 = build_qubo(state, settings)
    sol1 = solve_exact(model1)

    model2 = build_qubo(state, settings)
    sol2 = solve_exact(model2)

    assert sol1.candidate.first_green_seconds == sol2.candidate.first_green_seconds
    assert sol1.candidate.second_green_seconds == sol2.candidate.second_green_seconds
    assert sol1.objective_value == pytest.approx(sol2.objective_value, abs=1e-9)
    assert sol1.candidate.valid is True


def test_baseline_deltas_calculation() -> None:
    """Test delta calculation: delta = controller - fixed_time without value inversion."""
    mock_runs = [
        {
            "scenario": "Normal",
            "seed": 42,
            "controller": "Fixed-Time",
            "average_waiting_time_seconds": 15.0,
            "average_queue_length": 6.0,
            "throughput_vehicles_per_hour": 1200.0,
            "average_travel_time_seconds": 30.0,
            "total_fuel_consumption_litres": 1.5,
            "total_co2_emissions_grams": 3588.0,
        },
        {
            "scenario": "Normal",
            "seed": 42,
            "controller": "Classical Adaptive",
            "average_waiting_time_seconds": 12.5,
            "average_queue_length": 5.2,
            "throughput_vehicles_per_hour": 1350.0,
            "average_travel_time_seconds": 27.5,
            "total_fuel_consumption_litres": 1.35,
            "total_co2_emissions_grams": 3229.2,
        },
        {
            "scenario": "Normal",
            "seed": 42,
            "controller": "QUBO Exact",
            "average_waiting_time_seconds": 10.0,
            "average_queue_length": 4.0,
            "throughput_vehicles_per_hour": 1400.0,
            "average_travel_time_seconds": 25.0,
            "total_fuel_consumption_litres": 1.20,
            "total_co2_emissions_grams": 2870.4,
        },
    ]

    deltas = calculate_baseline_deltas(mock_runs)
    fixed = deltas[0]
    adaptive = deltas[1]
    qubo = deltas[2]

    # Fixed deltas are identically zero
    assert fixed["delta_avg_waiting_time"] == 0.0
    assert fixed["delta_avg_queue"] == 0.0
    assert fixed["delta_throughput"] == 0.0

    # Adaptive deltas
    assert adaptive["delta_avg_waiting_time"] == pytest.approx(-2.5, abs=1e-3)
    assert adaptive["delta_avg_queue"] == pytest.approx(-0.8, abs=1e-3)
    assert adaptive["delta_throughput"] == pytest.approx(150.0, abs=1e-2)
    assert adaptive["delta_fuel"] == pytest.approx(-0.15, abs=1e-4)

    # QUBO deltas
    assert qubo["delta_avg_waiting_time"] == pytest.approx(-5.0, abs=1e-3)
    assert qubo["delta_avg_queue"] == pytest.approx(-2.0, abs=1e-3)
    assert qubo["delta_throughput"] == pytest.approx(200.0, abs=1e-2)


def test_qaoa_objective_gap_calculation() -> None:
    """Test absolute and relative objective gap formulas."""
    exact_obj = 1.265306
    qaoa_obj = 1.265306
    abs_gap = abs(qaoa_obj - exact_obj)
    rel_gap = abs_gap / (abs(exact_obj) + 1e-9)

    assert abs_gap == pytest.approx(0.0, abs=1e-9)
    assert rel_gap == pytest.approx(0.0, abs=1e-9)

    # Imperfect run
    suboptimal_qaoa_obj = 3.500000
    abs_gap_sub = abs(suboptimal_qaoa_obj - exact_obj)
    rel_gap_sub = abs_gap_sub / (abs(exact_obj) + 1e-9)

    assert abs_gap_sub == pytest.approx(2.234694, abs=1e-5)
    assert rel_gap_sub == pytest.approx(2.234694 / 1.265306, rel=1e-4)


def test_qaoa_recovery_rate_calculation() -> None:
    """Test exact optimum recovery rate formula: exact_recoveries / total_valid_runs."""
    decisions = [
        {"valid": True, "exact_optimum_recovered": True, "objective_gap": 0.0, "relative_objective_gap": 0.0, "runtime_seconds": 3.2},
        {"valid": True, "exact_optimum_recovered": True, "objective_gap": 0.0, "relative_objective_gap": 0.0, "runtime_seconds": 3.4},
        {"valid": True, "exact_optimum_recovered": False, "objective_gap": 1.5, "relative_objective_gap": 0.5, "runtime_seconds": 3.1},
        {"valid": False, "exact_optimum_recovered": False, "objective_gap": None, "relative_objective_gap": None, "runtime_seconds": 2.9},
    ]

    analysis = calculate_qaoa_analysis(decisions)
    assert analysis["total_qaoa_decisions"] == 4
    assert analysis["valid_qaoa_decisions"] == 3
    assert analysis["failed_qaoa_decisions"] == 1
    assert analysis["exact_optimum_recoveries"] == 2
    assert analysis["exact_optimum_recovery_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert analysis["average_absolute_objective_gap"] == pytest.approx(0.5, abs=1e-4)
    assert analysis["mean_optimization_runtime_seconds"] == pytest.approx(3.15, abs=1e-2)


def test_failed_run_recording_no_fabrication() -> None:
    """Verify failed runs are recorded explicitly without fabricating replacement metrics."""
    decisions = [
        {
            "scenario": "High",
            "seed": 404,
            "intersection_id": "J1",
            "solver": "qaoa",
            "valid": False,
            "failure_reason": "No valid 1-hot candidate sampled by QAOA",
            "qubo_objective": None,
            "objective_gap": None,
            "exact_optimum_recovered": False,
        }
    ]

    analysis = calculate_qaoa_analysis(decisions)
    assert analysis["total_qaoa_decisions"] == 1
    assert analysis["valid_qaoa_decisions"] == 0
    assert analysis["failed_qaoa_decisions"] == 1
    assert analysis["exact_optimum_recoveries"] == 0
    assert analysis["exact_optimum_recovery_rate"] == 0.0
    assert analysis["average_absolute_objective_gap"] == 0.0


def test_statistical_summary_aggregation() -> None:
    """Test aggregation of mean, median, stdev, min, max across multiple seeds."""
    records = [
        {
            "scenario": "Low",
            "seed": 42,
            "controller": "Fixed-Time",
            "average_waiting_time_seconds": 10.0,
            "total_waiting_time_seconds": 100.0,
            "average_queue_length": 2.0,
            "maximum_queue_length": 4,
            "throughput_vehicles_per_hour": 300.0,
            "average_travel_time_seconds": 25.0,
            "total_fuel_consumption_litres": 0.5,
            "total_co2_emissions_grams": 1196.0,
            "solver_runtime_seconds": 0.0,
            "delta_avg_waiting_time": 0.0,
            "delta_avg_queue": 0.0,
            "delta_throughput": 0.0,
            "delta_travel_time": 0.0,
            "delta_fuel": 0.0,
            "delta_co2": 0.0,
        },
        {
            "scenario": "Low",
            "seed": 101,
            "controller": "Fixed-Time",
            "average_waiting_time_seconds": 20.0,
            "total_waiting_time_seconds": 200.0,
            "average_queue_length": 4.0,
            "maximum_queue_length": 8,
            "throughput_vehicles_per_hour": 300.0,
            "average_travel_time_seconds": 35.0,
            "total_fuel_consumption_litres": 0.7,
            "total_co2_emissions_grams": 1674.4,
            "solver_runtime_seconds": 0.0,
            "delta_avg_waiting_time": 0.0,
            "delta_avg_queue": 0.0,
            "delta_throughput": 0.0,
            "delta_travel_time": 0.0,
            "delta_fuel": 0.0,
            "delta_co2": 0.0,
        },
    ]

    summaries = calculate_statistical_summary(records, [])
    assert len(summaries) == 1
    s = summaries[0]

    assert s["scenario"] == "Low"
    assert s["controller"] == "Fixed-Time"
    assert s["runs_count"] == 2
    assert s["avg_wait_mean"] == pytest.approx(15.0, abs=1e-3)
    assert s["avg_wait_median"] == pytest.approx(15.0, abs=1e-3)
    assert s["avg_wait_min"] == 10.0
    assert s["avg_wait_max"] == 20.0
    assert s["avg_queue_mean"] == pytest.approx(3.0, abs=1e-3)


def test_result_serialization() -> None:
    """Test exporting comparison records and summary files to CSV and JSON."""
    test_records = [
        {
            "scenario": "Low",
            "seed": 42,
            "controller": "Fixed-Time",
            "solver": "fixed",
            "simulation_duration_seconds": 60.0,
            "total_vehicles": 4,
            "average_waiting_time_seconds": 0.0,
            "total_waiting_time_seconds": 0.0,
            "average_queue_length": 2.2,
            "maximum_queue_length": 4,
            "throughput_vehicles_per_hour": 240.0,
            "average_travel_time_seconds": 15.0,
            "total_fuel_consumption_litres": 0.48,
            "total_co2_emissions_grams": 1148.16,
            "solver_runtime_seconds": 0.0,
            "qaoa_recovery_rate": None,
            "qaoa_objective_gap": None,
            "delta_avg_waiting_time": 0.0,
            "delta_avg_queue": 0.0,
            "delta_throughput": 0.0,
            "delta_travel_time": 0.0,
            "delta_fuel": 0.0,
            "delta_co2": 0.0,
        }
    ]
    test_summaries = [
        {
            "scenario": "Low",
            "controller": "Fixed-Time",
            "runs_count": 1,
            "avg_wait_mean": 0.0,
            "avg_queue_mean": 2.2,
        }
    ]
    test_qaoa = [
        {
            "scenario": "Low",
            "seed": 42,
            "intersection_id": "J1",
            "solver": "qaoa",
            "selected_phase_0_green_seconds": 30,
            "selected_phase_2_green_seconds": 30,
            "qubo_objective": 1.265306,
            "exact_objective": 1.265306,
            "objective_gap": 0.0,
            "relative_objective_gap": 0.0,
            "exact_optimum_recovered": True,
            "runtime_seconds": 3.45,
            "circuit_depth_p": 2,
            "shots": 2048,
            "valid": True,
            "failure_reason": None,
        }
    ]

    paths = export_results(
        run_records=test_records,
        summary_rows=test_summaries,
        qaoa_decisions=test_qaoa,
        emergency_eval={"scenario": "Emergency Corridor"},
        event_eval={"scenario": "Accident Disruption"},
        output_dir=SCRATCH_DIR,
    )

    assert paths["comparison_csv"].exists()
    assert paths["comparison_json"].exists()
    assert paths["summary_csv"].exists()
    assert paths["qaoa_analysis_csv"].exists()

    with paths["comparison_json"].open("r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["phase"] == "Phase N"
        assert len(data["runs"]) == 1
        assert data["runs"][0]["controller"] == "Fixed-Time"
