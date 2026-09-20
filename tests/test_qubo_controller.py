from types import SimpleNamespace

import pytest

from config.loader import load_config
from simulation.models.state import IntersectionTrafficState, SignalState
from simulation.signals.qubo import QuboSignalController


def qubo_settings() -> dict:
    return load_config()["optimization"]["phase3a"]


def qubo_state(p0_queue: int = 20, p2_queue: int = 4) -> IntersectionTrafficState:
    return IntersectionTrafficState(
        intersection_id="J1",
        vehicle_count=p0_queue + p2_queue,
        queue_length=p0_queue + p2_queue,
        traffic_density=0.5,
        road_capacity=100,
        signal_state=SignalState.GREEN,
        signal_phase=0,
        green_phase_queues=((0, p0_queue), (2, p2_queue)),
    )


class MockTrafficLight:
    def __init__(self) -> None:
        self.current_phase = 0
        self.spent_duration = 1.0
        self.duration_calls: list[tuple[str, int]] = []
        self.logic = SimpleNamespace(
            phases=[
                SimpleNamespace(state="GGrr", duration=30, minDur=22, maxDur=42),
                SimpleNamespace(state="yyrr", duration=4, minDur=4, maxDur=4),
                SimpleNamespace(state="rrGG", duration=30, minDur=22, maxDur=42),
                SimpleNamespace(state="rryy", duration=4, minDur=4, maxDur=4),
            ]
        )

    def getAllProgramLogics(self, _intersection_id):
        return [self.logic]

    def setProgramLogic(self, _intersection_id, logic) -> None:
        self.logic = logic

    def getPhase(self, _intersection_id) -> int:
        return self.current_phase

    def getSpentDuration(self, _intersection_id) -> float:
        return self.spent_duration

    def setPhaseDuration(self, intersection_id: str, duration: int) -> None:
        self.duration_calls.append((intersection_id, duration))


class MockSimulation:
    def __init__(self) -> None:
        self.time = 0.0

    def getTime(self) -> float:
        return self.time


def test_qubo_controller_initialization_and_validation() -> None:
    settings = qubo_settings()
    controller = QuboSignalController(None, settings)
    assert controller is not None

    # Invalid solver
    with pytest.raises(ValueError, match="Solver must be either"):
        QuboSignalController(None, settings, solver="dwave_sampler")

    # Invalid bounds
    bad_settings = dict(settings)
    bad_settings["min_green_seconds"] = 50
    bad_settings["max_green_seconds"] = 30
    with pytest.raises(ValueError, match="limits are invalid"):
        QuboSignalController(None, bad_settings)


def test_qubo_controller_applies_timing_at_safe_boundaries() -> None:
    settings = qubo_settings()
    tl = MockTrafficLight()
    sim = MockSimulation()
    fake = SimpleNamespace(trafficlight=tl, simulation=sim)
    controller = QuboSignalController(fake, settings, minimum_seconds_between_adjustments=10.0)

    # Initial step at t=0: re-evaluates state (queue 20 vs 4)
    state = qubo_state(20, 4)
    sim.time = 0.0
    tl.current_phase = 1  # in yellow phase
    controller.step([state])
    # In yellow phase: should NOT apply green duration
    assert len(tl.duration_calls) == 0

    # Transition to green phase 0 (previous_phase was 1)
    tl.current_phase = 0
    sim.time = 4.0
    controller.step([state])
    # Now in green phase: should apply timing
    assert len(tl.duration_calls) == 1
    junction_id, applied_duration = tl.duration_calls[0]
    assert junction_id == "J1"
    # Phase 0 had queue 20 vs 4, so candidate duration should be optimal (40s minus spent 1s = 39s)
    assert applied_duration >= settings["min_green_seconds"] - 1
    assert applied_duration <= settings["max_green_seconds"]

    # Stepping further during the SAME green phase should not re-trigger setPhaseDuration
    for t in range(5, 15):
        sim.time = float(t)
        controller.step([state])
    assert len(tl.duration_calls) == 1


def test_qubo_controller_anti_oscillation_damping() -> None:
    settings = qubo_settings()
    tl = MockTrafficLight()
    sim = MockSimulation()
    fake = SimpleNamespace(trafficlight=tl, simulation=sim)
    controller = QuboSignalController(fake, settings, minimum_seconds_between_adjustments=50.0)

    state = qubo_state(20, 4)
    sim.time = 0.0
    tl.current_phase = 1
    controller.step([state])

    # First green transition at t=4: applied
    tl.current_phase = 0
    sim.time = 4.0
    controller.step([state])
    assert len(tl.duration_calls) == 1

    # Transition to phase 2 at t=20 (< 50s since last adjustment)
    tl.current_phase = 2
    sim.time = 20.0
    controller.step([state])
    # Should be rejected by anti-oscillation rate-limiter
    assert len(tl.duration_calls) == 1

    # Transition after 50s at t=60: allowed
    tl.current_phase = 0
    sim.time = 60.0
    controller.step([state])
    assert len(tl.duration_calls) == 2


def test_qubo_controller_prevents_negative_durations() -> None:
    settings = qubo_settings()
    tl = MockTrafficLight()
    sim = MockSimulation()
    # Mock unusually high spent duration
    tl.spent_duration = 100.0
    fake = SimpleNamespace(trafficlight=tl, simulation=sim)
    controller = QuboSignalController(fake, settings, minimum_seconds_between_adjustments=0.0)

    state = qubo_state(10, 10)
    sim.time = 0.0
    tl.current_phase = 1
    controller.step([state])

    tl.current_phase = 0
    sim.time = 4.0
    controller.step([state])

    assert len(tl.duration_calls) == 1
    # Even with spent_duration=100, duration must never be <= 0
    assert tl.duration_calls[0][1] >= 1
