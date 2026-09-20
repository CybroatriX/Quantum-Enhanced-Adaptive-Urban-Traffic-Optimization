"""Unit and integration tests for Phase K Metrics, Fuel, and CO2 Evaluation."""

import json
from pathlib import Path
import pytest

from metrics.evaluator import (
    compute_fuel_and_co2_proxy,
    TrafficMetricsEvaluator,
    CO2_GRAMS_PER_LITRE,
    CRUISE_FUEL_RATE_LPS,
    IDLE_FUEL_RATE_LPS,
)
from metrics.exporter import (
    export_metrics_csv,
    export_metrics_json,
    export_summary_csv,
)
from metrics.models import (
    ApproachMetrics,
    ControllerComparisonRecord,
    EmergencyEvaluationMetrics,
    EventEvaluationMetrics,
    IntersectionMetrics,
    NetworkMetrics,
)
from perception.models import TrafficObservation


def make_test_obs(
    intersection_id: str = "J1",
    north_q: int = 5,
    south_q: int = 5,
    east_q: int = 3,
    west_q: int = 3,
    veh_count: int = 16,
) -> TrafficObservation:
    return TrafficObservation(
        timestamp=1000.0,
        source="yolov8",
        intersection_id=intersection_id,
        vehicle_count=veh_count,
        approach_counts={"north": north_q, "south": south_q, "east": east_q, "west": west_q},
        queue_lengths={"north": north_q, "south": south_q, "east": east_q, "west": west_q},
        class_counts={"car": veh_count, "motorcycle": 0, "bus": 0, "truck": 0},
    )


# 1. Metric Initialization
def test_metric_initialization():
    im = IntersectionMetrics(intersection_id="J1")
    assert im.intersection_id == "J1"
    assert im.vehicle_count == 0
    assert im.queue_length == 0
    assert im.fuel_source == "simulation_proxy"
    assert im.co2_source == "simulation_proxy"
    assert len(im.approach_metrics) == 4
    assert set(im.approach_metrics.keys()) == {"north", "south", "east", "west"}


# 2. Waiting Time Calculation
def test_waiting_time_calculation():
    evaluator = TrafficMetricsEvaluator()
    obs = make_test_obs(north_q=6, south_q=4, east_q=2, west_q=2, veh_count=14)
    # p0_green=40s, p2_green=22s
    # p0_q = 10, p2_q = 4
    # p0_wait = 10 * 22 * 0.5 = 110.0s
    # p2_wait = 4 * 40 * 0.5 = 80.0s
    # total_wait = 190.0s, avg_wait = 190.0 / 14 = 13.57s
    im = evaluator.evaluate_intersection(obs, p0_green_seconds=40, p2_green_seconds=22)
    assert im.total_waiting_time_seconds == 190.0
    assert im.average_waiting_time_seconds == pytest.approx(13.57, abs=0.01)


# 3. Queue Calculation & Max Queue
def test_queue_and_max_queue_calculation():
    evaluator = TrafficMetricsEvaluator()
    obs = make_test_obs(north_q=8, south_q=2, east_q=12, west_q=1, veh_count=23)
    im = evaluator.evaluate_intersection(obs, p0_green_seconds=30, p2_green_seconds=30)
    assert im.queue_length == 23
    assert im.max_queue_length == 12


# 4. Throughput Calculation
def test_throughput_calculation():
    evaluator = TrafficMetricsEvaluator()
    obs = make_test_obs(north_q=10, south_q=10, east_q=10, west_q=10, veh_count=40)
    # duration 60s, green 30s each
    # saturation flow rate = 0.5 veh/s
    # cleared p0 = min(20, 30*0.5) = 15
    # cleared p2 = min(20, 30*0.5) = 15
    # total cleared = 30 veh in 60s -> 30/60 * 3600 = 1800 veh/hr
    im = evaluator.evaluate_intersection(obs, p0_green_seconds=30, p2_green_seconds=30, duration_seconds=60.0)
    assert im.throughput_vehicles_per_hour == 1800.0


# 5. Travel Time Calculation
def test_travel_time_calculation():
    evaluator = TrafficMetricsEvaluator()
    obs = make_test_obs(north_q=2, south_q=2, east_q=2, west_q=2, veh_count=8)
    im = evaluator.evaluate_intersection(obs, p0_green_seconds=30, p2_green_seconds=30)
    # nominal 15s + avg_wait
    assert im.average_travel_time_seconds == pytest.approx(15.0 + im.average_waiting_time_seconds, abs=0.01)


# 6. Fuel and CO2 Proxy Formulas & Verification
def test_fuel_and_co2_proxy_formulas():
    wait_time = 100.0
    travel_time = 250.0
    veh_count = 10

    fuel, co2 = compute_fuel_and_co2_proxy(wait_time, travel_time, veh_count)
    # moving_time = 250 - 100 = 150
    # expected_fuel = (100 * 0.00025) + (150 * 0.00070) = 0.025 + 0.105 = 0.130 L
    # expected_co2 = 0.130 * 2392.0 = 310.96 g
    assert fuel == 0.13
    assert co2 == pytest.approx(310.96, abs=0.05)


# 7. SUMO-measured Fuel & CO2 vs Simulation Proxy Attribution
def test_sumo_vs_proxy_attribution():
    evaluator = TrafficMetricsEvaluator()
    obs = make_test_obs()

    # Case A: Proxy when SUMO outputs are None
    im_proxy = evaluator.evaluate_intersection(obs, 30, 30)
    assert im_proxy.fuel_source == "simulation_proxy"
    assert im_proxy.co2_source == "simulation_proxy"
    assert im_proxy.fuel_consumption_litres > 0.0
    assert im_proxy.co2_emissions_grams > 0.0

    # Case B: SUMO ground truth values provided
    im_sumo = evaluator.evaluate_intersection(
        obs, 30, 30, sumo_fuel_litres=0.456, sumo_co2_grams=1090.5
    )
    assert im_sumo.fuel_source == "sumo_measured"
    assert im_sumo.co2_source == "sumo_measured"
    assert im_sumo.fuel_consumption_litres == 0.456
    assert im_sumo.co2_emissions_grams == 1090.5


# 8. Network Aggregation (J1 - J4)
def test_network_aggregation_j1_to_j4():
    evaluator = TrafficMetricsEvaluator()
    observations = [
        make_test_obs("J1", 4, 4, 2, 2, veh_count=12),
        make_test_obs("J2", 2, 2, 6, 6, veh_count=16),
        make_test_obs("J3", 3, 3, 3, 3, veh_count=12),
        make_test_obs("J4", 5, 5, 1, 1, veh_count=12),
    ]
    decisions = {
        "J1": {"phase_0_green_seconds": 40, "phase_2_green_seconds": 22},
        "J2": {"phase_0_green_seconds": 22, "phase_2_green_seconds": 40},
        "J3": {"phase_0_green_seconds": 30, "phase_2_green_seconds": 30},
        "J4": {"phase_0_green_seconds": 40, "phase_2_green_seconds": 22},
    }

    net = evaluator.evaluate_network(observations, decisions, duration_seconds=60.0)

    assert net.intersections_count == 4
    assert net.total_vehicle_count == 12 + 16 + 12 + 12
    assert net.network_total_queue == (8 + 4) + (4 + 12) + (6 + 6) + (10 + 2)
    assert net.network_max_queue > 0
    assert net.network_throughput_vehicles_per_hour > 0.0
    assert net.network_total_fuel_consumption_litres > 0.0
    assert net.network_total_co2_emissions_grams > 0.0


# 9. 8-Intersection Network Scalability Aggregation
def test_eight_intersection_network_aggregation():
    evaluator = TrafficMetricsEvaluator()
    obs_list = [make_test_obs(f"J{i}", 3, 3, 3, 3, veh_count=12) for i in range(1, 9)]
    decisions = {f"J{i}": {"phase_0_green_seconds": 30, "phase_2_green_seconds": 30} for i in range(1, 9)}

    net = evaluator.evaluate_network(obs_list, decisions)
    assert net.intersections_count == 8
    assert net.total_vehicle_count == 96
    assert len(net.intersection_metrics) == 8


# 10. Emergency Metrics Integration
def test_emergency_evaluation_metrics():
    emg = EmergencyEvaluationMetrics(
        emergency_vehicle_id="AMB_001",
        route=["J1", "J2", "J3", "J4"],
        emergency_travel_time_seconds=58.2,
        baseline_travel_time_seconds=145.0,
        time_saved_seconds=86.8,
        corridor_activation_duration_seconds=62.0,
        intersections_affected=4,
        signal_overrides_count=4,
        time_spent_in_priority_seconds=58.2,
    )
    d = emg.to_dict()
    assert d["emergency_vehicle_id"] == "AMB_001"
    assert d["time_saved_seconds"] == 86.8
    assert d["intersections_affected"] == 4


# 11. Dynamic Event Metrics Integration
def test_event_evaluation_metrics():
    evt = EventEvaluationMetrics(
        event_id="ACC_001",
        event_type="accident",
        affected_intersections=["J2"],
        activation_duration_seconds=300.0,
        queue_before=6,
        queue_during=24,
        queue_after=5,
        throughput_before=900.0,
        throughput_during=420.0,
        throughput_after=880.0,
        signal_adaptations_count=5,
    )
    d = evt.to_dict()
    assert d["event_id"] == "ACC_001"
    assert d["queue_during"] == 24
    assert d["signal_adaptations_count"] == 5


# 12. Missing Metric Values and Zero-Vehicle Scenario
def test_zero_vehicle_scenario_safety():
    evaluator = TrafficMetricsEvaluator()
    empty_obs = make_test_obs(north_q=0, south_q=0, east_q=0, west_q=0, veh_count=0)
    im = evaluator.evaluate_intersection(empty_obs, 30, 30)

    assert im.vehicle_count == 0
    assert im.average_waiting_time_seconds == 0.0
    assert im.total_waiting_time_seconds == 0.0
    assert im.queue_length == 0
    assert im.fuel_consumption_litres == 0.0
    assert im.co2_emissions_grams == 0.0


# 13. Deterministic Repeated Run Consistency
def test_deterministic_reproducibility():
    evaluator = TrafficMetricsEvaluator()
    obs = make_test_obs("J1", 7, 3, 5, 2, veh_count=17)

    run1 = evaluator.evaluate_intersection(obs, 38, 24)
    run2 = evaluator.evaluate_intersection(obs, 38, 24)

    assert run1.total_waiting_time_seconds == run2.total_waiting_time_seconds
    assert run1.fuel_consumption_litres == run2.fuel_consumption_litres
    assert run1.co2_emissions_grams == run2.co2_emissions_grams
    assert run1.throughput_vehicles_per_hour == run2.throughput_vehicles_per_hour


# 14. CSV Export and Protection of Baseline Files
def test_csv_export_and_protection():
    records = [
        ControllerComparisonRecord(
            scenario="Normal",
            seed=42,
            controller="QUBO Exact",
            solver="exact",
            simulation_duration_seconds=60.0,
            vehicle_demand=50,
            average_waiting_time_seconds=12.5,
            average_queue_length=7.2,
            throughput_vehicles_per_hour=1400.0,
            travel_time_seconds=27.5,
            fuel_consumption_litres=0.35,
            co2_emissions_grams=837.2,
        )
    ]
    test_scratch = Path("data/results/_test_scratch")
    test_scratch.mkdir(parents=True, exist_ok=True)
    target_csv = test_scratch / "test_metrics.csv"
    try:
        res_path = export_metrics_csv(records, target_csv)
        assert res_path.exists()
        content = res_path.read_text(encoding="utf-8")
        assert "QUBO Exact" in content
        assert "837.2" in content

        # Test protection against overwriting previous phase results
        with pytest.raises(RuntimeError, match="Safety guard"):
            export_metrics_csv(records, Path("data/results/phase3a_qubo_validation.csv"))
    finally:
        if target_csv.exists():
            target_csv.unlink()
        if test_scratch.exists():
            test_scratch.rmdir()


# 15. JSON Export
def test_json_export():
    data = {
        "scenario": "High Traffic",
        "controllers": ["Fixed", "Adaptive", "QUBO"],
        "metrics": {"total_queue": 45, "fuel": 1.25},
    }
    test_scratch = Path("data/results/_test_scratch")
    test_scratch.mkdir(parents=True, exist_ok=True)
    target_json = test_scratch / "test_metrics.json"
    try:
        res_path = export_metrics_json(data, target_json)
        assert res_path.exists()
        loaded = json.loads(res_path.read_text(encoding="utf-8"))
        assert loaded["scenario"] == "High Traffic"
        assert loaded["metrics"]["fuel"] == 1.25
    finally:
        if target_json.exists():
            target_json.unlink()
        if test_scratch.exists():
            test_scratch.rmdir()


# 16. Controller Comparison Record Serialization
def test_controller_comparison_record_structure():
    rec = ControllerComparisonRecord(
        scenario="Low",
        seed=42,
        controller="QAOA",
        solver="qaoa",
        simulation_duration_seconds=60.0,
        vehicle_demand=20,
        average_waiting_time_seconds=8.4,
        average_queue_length=3.1,
        throughput_vehicles_per_hour=950.0,
        travel_time_seconds=23.4,
        fuel_consumption_litres=0.18,
        co2_emissions_grams=430.56,
        qaoa_recovery_rate=0.80,
        qaoa_objective_gap=0.015,
        solver_runtime_seconds=0.045,
    )
    d = rec.to_dict()
    assert d["controller"] == "QAOA"
    assert d["qaoa_recovery_rate"] == 0.80
    assert d["solver_runtime_seconds"] == 0.045
