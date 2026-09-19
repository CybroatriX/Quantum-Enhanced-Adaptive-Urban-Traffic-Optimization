from metrics.collector import MetricsCollector
from simulation.models.state import IntersectionTrafficState, SignalState


class FakeSimulation:
    def __init__(self) -> None:
        self.time = 0.0

    def getTime(self) -> float:
        return self.time


class FakeVehicle:
    def __init__(self, simulation: FakeSimulation) -> None:
        self.simulation = simulation

    def getIDList(self) -> list[str]:
        return ["vehicle_1"] if self.simulation.time in {1, 2} else []

    def getAccumulatedWaitingTime(self, vehicle_id: str) -> float:
        return 6.0 if self.simulation.time == 2 else 2.0


class FakeTraci:
    def __init__(self) -> None:
        self.simulation = FakeSimulation()
        self.vehicle = FakeVehicle(self.simulation)


def test_metrics_collect_completed_wait_and_queue() -> None:
    fake = FakeTraci()
    collector = MetricsCollector(fake)
    state = [IntersectionTrafficState("J1", 2, 4, 0.1, 40, SignalState.RED, 1)]
    for time in (1, 2, 3):
        fake.simulation.time = time
        collector.record_step(state)
    snapshot = collector.snapshot()
    assert snapshot.completed_vehicles == 1
    assert snapshot.average_waiting_time_seconds == 6.0
    assert snapshot.average_queue_length == 4.0
    assert snapshot.throughput_vehicles_per_hour == 1200.0
    assert snapshot.total_waiting_time_seconds == 6.0
