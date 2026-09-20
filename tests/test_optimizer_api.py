"""Unit and integration tests for the Python optimization HTTP API."""

import pytest
from optimization.service import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert "exact" in data["solvers"]
    assert "qaoa" in data["solvers"]


def test_optimize_valid_exact_request(client):
    payload = {
        "intersection_id": "J1",
        "vehicle_count": 24,
        "traffic_density": 0.72,
        "road_capacity": 100,
        "current_signal_phase": 0,
        "phase_0_queue": 20,
        "phase_2_queue": 4,
        "solver": "exact",
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 200
    data = response.get_json()

    # Verify required schema fields
    assert data["intersection_id"] == "J1"
    assert data["solver"] == "exact"
    assert data["phase_0_green_seconds"] == 40
    assert data["phase_2_green_seconds"] == 22
    assert isinstance(data["objective"], float)
    assert data["valid"] is True
    # Verify objective value matches canonical exact solver
    assert round(data["objective"], 4) == round(5.288126, 4)


def test_optimize_valid_qaoa_request(client):
    payload = {
        "intersection_id": "J1",
        "vehicle_count": 24,
        "traffic_density": 0.72,
        "road_capacity": 100,
        "current_signal_phase": 0,
        "phase_0_queue": 20,
        "phase_2_queue": 4,
        "solver": "qaoa",
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 200
    data = response.get_json()

    assert data["intersection_id"] == "J1"
    assert data["solver"] == "qaoa"
    assert data["phase_0_green_seconds"] in (22, 30, 40)
    assert data["phase_2_green_seconds"] in (22, 30, 40)
    assert data["valid"] is True
    assert isinstance(data["objective"], float)


def test_optimize_missing_required_fields(client):
    # Missing intersection_id
    res1 = client.post("/api/optimize", json={"phase_0_queue": 10, "phase_2_queue": 5})
    assert res1.status_code == 400
    assert "intersection_id" in res1.get_json()["error"]

    # Missing phase_0_queue
    res2 = client.post("/api/optimize", json={"intersection_id": "J1", "phase_2_queue": 5})
    assert res2.status_code == 400
    assert "phase_0_queue" in res2.get_json()["error"]

    # Missing phase_2_queue
    res3 = client.post("/api/optimize", json={"intersection_id": "J1", "phase_0_queue": 10})
    assert res3.status_code == 400
    assert "phase_2_queue" in res3.get_json()["error"]


def test_optimize_negative_queues(client):
    payload = {
        "intersection_id": "J1",
        "phase_0_queue": -5,
        "phase_2_queue": 10,
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 400
    assert "negative" in response.get_json()["error"]


def test_optimize_invalid_solver_name(client):
    payload = {
        "intersection_id": "J1",
        "phase_0_queue": 10,
        "phase_2_queue": 5,
        "solver": "quantum_annealing_dwave",
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 400
    assert "Unsupported solver" in response.get_json()["error"]


def test_optimize_malformed_json_and_types(client):
    # Non-dict JSON
    response = client.post("/api/optimize", data="not json", content_type="application/json")
    assert response.status_code == 400

    # Non-json content-type
    response = client.post("/api/optimize", data="hello", content_type="text/plain")
    assert response.status_code == 400


def test_optimize_batch_states_and_camelcase_compat(client):
    payload = {
        "states": [
            {
                "intersectionId": 0,
                "nsQueue": 18,
                "ewQueue": 4,
                "trafficDensity": 0.5,
                "vehicleCount": 22,
                "roadCapacity": 50,
            },
            {
                "intersectionId": 1,
                "nsQueue": 5,
                "ewQueue": 25,
                "trafficDensity": 0.6,
                "vehicleCount": 30,
                "roadCapacity": 60,
            },
        ],
        "solver": "exact",
    }
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert "decisions" in data
    assert len(data["decisions"]) == 2

    first = data["decisions"][0]
    assert first["intersectionId"] == 0
    assert first["nsGreen"] >= first["ewGreen"]  # ns had heavier queue
    assert first["valid"] is True

    second = data["decisions"][1]
    assert second["intersectionId"] == 1
    assert second["ewGreen"] >= second["nsGreen"]  # ew had heavier queue
    assert second["valid"] is True


def test_metrics_endpoint(client):
    payload = {
        "network_id": "test_net",
        "duration_seconds": 60.0,
        "observations": [
            {
                "intersection_id": "J1",
                "vehicle_count": 20,
                "queue_lengths": {"north": 5, "south": 5, "east": 1, "west": 1},
            },
            {
                "intersection_id": "J2",
                "vehicle_count": 24,
                "queue_lengths": {"north": 2, "south": 2, "east": 8, "west": 8},
            },
        ],
        "decisions": {
            "J1": {"phase_0_green_seconds": 40, "phase_2_green_seconds": 22},
            "J2": {"phase_0_green_seconds": 22, "phase_2_green_seconds": 40},
        },
    }
    response = client.post("/api/metrics", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["network_id"] == "test_net"
    assert "network_average_waiting_time_seconds" in data
    assert "network_total_fuel_consumption_litres" in data
    assert "network_total_co2_emissions_grams" in data
    assert "intersection_metrics" in data
    assert "J1" in data["intersection_metrics"]
    assert "J2" in data["intersection_metrics"]

