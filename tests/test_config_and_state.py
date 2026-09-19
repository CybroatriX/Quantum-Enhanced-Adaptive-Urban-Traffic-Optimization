from config.loader import load_config
from simulation.models.state import IntersectionTrafficState, SignalState
from simulation.state_reader import TrafficStateReader


def test_configuration_loads_and_declares_four_intersections() -> None:
    config = load_config()
    assert config["network"]["intersection_ids"] == ["J1", "J2", "J3", "J4"]
    assert config["signals"]["fixed_time"]["green_seconds"] > 0


def test_traffic_state_serializes_to_primitive_api_data() -> None:
    state = IntersectionTrafficState(
        "J1", 8, 3, 0.25, 32, SignalState.GREEN, 0, green_phase_queues=((0, 2), (2, 1))
    )
    assert state.to_dict()["signal_state"] == "green"
    assert state.to_dict()["emergency_status"] is False
    assert state.to_dict()["green_phase_queues"] == ((0, 2), (2, 1))


def test_state_reader_exposes_green_phase_queues_in_sumo_phase_order() -> None:
    class Lane:
        @staticmethod
        def getLastStepHaltingNumber(lane: str) -> int:
            return {"north": 3, "south": 2, "east": 5}[lane]

    class TrafficLight:
        @staticmethod
        def getControlledLinks(_intersection_id: str):
            return ((('north', '', ''),), (('south', '', ''),), (('east', '', ''),))

        @staticmethod
        def getAllProgramLogics(_intersection_id: str):
            return [
                type(
                    "Logic",
                    (),
                    {"phases": [type("Phase", (), {"state": "GGrr"})(), type("Phase", (), {"state": "rrGG"})()]},
                )()
            ]

    fake_traci = type("Traci", (), {"trafficlight": TrafficLight(), "lane": Lane()})()
    assert TrafficStateReader.green_phase_queues(fake_traci, "J1") == ((0, 5), (1, 5))
