from types import SimpleNamespace

import pytest

from config.loader import load_config
from simulation.models.state import IntersectionTrafficState, SignalState
from simulation.signals.adaptive import AdaptiveSignalController
from simulation.signals.fixed_time import FixedTimeController


def adaptive_settings() -> dict:
    return load_config()["signals"]["adaptive"]


def traffic_state(density: float) -> IntersectionTrafficState:
    return IntersectionTrafficState("J1", 20, 8, density, 96, SignalState.GREEN, 0)


def test_adaptive_controller_initializes_with_valid_settings() -> None:
    controller = AdaptiveSignalController(None, adaptive_settings())
    assert controller is not None


def test_green_time_stays_within_configured_limits() -> None:
    controller = AdaptiveSignalController(None, adaptive_settings())
    settings = adaptive_settings()
    duration = controller.recommend_green_duration(traffic_state(0.9), 999, [0, 999])
    assert settings["min_green_seconds"] <= duration <= settings["max_green_seconds"]


def test_higher_queue_receives_more_green_than_a_low_queue() -> None:
    controller = AdaptiveSignalController(None, adaptive_settings())
    state = traffic_state(0.2)
    low_queue_duration = controller.recommend_green_duration(state, 1, [1, 15])
    high_queue_duration = controller.recommend_green_duration(state, 15, [1, 15])
    assert high_queue_duration > low_queue_duration


def test_small_queue_imbalance_keeps_the_baseline_green_time() -> None:
    settings = adaptive_settings()
    controller = AdaptiveSignalController(None, settings)
    state = traffic_state(0.2)
    duration = controller.recommend_green_duration(state, 6, [6, 8])
    assert duration == settings["base_green_seconds"]


def test_low_traffic_uses_a_valid_short_green() -> None:
    settings = adaptive_settings()
    controller = AdaptiveSignalController(None, settings)
    duration = controller.recommend_green_duration(traffic_state(0.01), 0, [0, 0])
    assert duration == settings["low_traffic_green_seconds"]
    assert settings["min_green_seconds"] <= duration <= settings["max_green_seconds"]


def test_invalid_green_limits_are_rejected() -> None:
    settings = adaptive_settings()
    settings["min_green_seconds"] = 51
    with pytest.raises(ValueError, match="limits"):
        AdaptiveSignalController(None, settings)


class FakeTrafficLight:
    def __init__(self) -> None:
        self.logic = SimpleNamespace(
            phases=[
                SimpleNamespace(state="GGrr", duration=20, minDur=20, maxDur=20),
                SimpleNamespace(state="yyrr", duration=3, minDur=3, maxDur=3),
                SimpleNamespace(state="rrGG", duration=20, minDur=20, maxDur=20),
            ]
        )

    def getAllProgramLogics(self, _intersection_id):
        return [self.logic]

    def setProgramLogic(self, _intersection_id, logic) -> None:
        self.logic = logic


class PhaseStableTrafficLight(FakeTrafficLight):
    def __init__(self) -> None:
        super().__init__()
        self.logic = SimpleNamespace(
            phases=[
                SimpleNamespace(state="Gr", duration=30, minDur=30, maxDur=30),
                SimpleNamespace(state="yr", duration=4, minDur=4, maxDur=4),
                SimpleNamespace(state="rG", duration=30, minDur=30, maxDur=30),
            ]
        )
        self.phase_duration_calls: list[int] = []

    def getPhase(self, _intersection_id) -> int:
        return 0

    def getControlledLinks(self, _intersection_id):
        return ((('lane_high', '', ''),), (('lane_low', '', ''),))

    def getSpentDuration(self, _intersection_id) -> float:
        return 1.0

    def setPhaseDuration(self, _intersection_id, duration: int) -> None:
        self.phase_duration_calls.append(duration)


class PhaseStableLane:
    def getLastStepHaltingNumber(self, lane: str) -> int:
        return 9 if lane == "lane_high" else 1


class PhaseStableSimulation:
    def __init__(self) -> None:
        self.time = 0.0

    def getTime(self) -> float:
        return self.time


def test_controller_does_not_repeatedly_change_one_green_phase() -> None:
    traffic_light = PhaseStableTrafficLight()
    simulation = PhaseStableSimulation()
    fake = SimpleNamespace(trafficlight=traffic_light, lane=PhaseStableLane(), simulation=simulation)
    controller = AdaptiveSignalController(fake, adaptive_settings())
    state = traffic_state(0.2)
    for second in range(1, 21):
        simulation.time = float(second)
        controller.step([state])
    # Only the phase-entry decision is applied; later re-evaluations do not
    # restart or repeatedly modify the unchanged active green phase.
    assert len(traffic_light.phase_duration_calls) == 1


def test_fixed_controller_still_applies_fixed_phase_durations() -> None:
    fake = SimpleNamespace(trafficlight=FakeTrafficLight())
    FixedTimeController(fake, {"green_seconds": 30, "yellow_seconds": 4, "all_red_seconds": 2}).configure(["J1"])
    assert [phase.duration for phase in fake.trafficlight.logic.phases] == [30, 4, 30]
