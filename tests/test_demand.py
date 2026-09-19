from config.loader import load_config
from simulation.traffic.demand import ROUTES, ROUTE_FILE, generate_routes


def test_routes_are_generated_for_each_configured_flow() -> None:
    # The production route file is regenerated before every simulation, so this
    # idempotent check avoids a host-specific temporary-directory dependency.
    output = generate_routes(load_config(), "normal", ROUTE_FILE)
    xml = output.read_text(encoding="utf-8")
    assert xml.count("<flow ") == len(ROUTES)
    assert 'vehsPerHour="300"' in xml
