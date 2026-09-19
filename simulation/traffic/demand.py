"""Generate deterministic SUMO route flows for a selected demand scenario."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE_FILE = PROJECT_ROOT / "data" / "sumo" / "traffic.rou.xml"

# Each route crosses two connected signalized intersections.
ROUTES: dict[str, str] = {
    "west_east_north": "W1_J1 J1_J2 J2_E1",
    "east_west_north": "E1_J2 J2_J1 J1_W1",
    "north_south_west": "N1_J1 J1_J3 J3_S1",
    "south_north_west": "S1_J3 J3_J1 J1_N1",
    "west_east_south": "W2_J3 J3_J4 J4_E2",
    "east_west_south": "E2_J4 J4_J3 J3_W2",
    "north_south_east": "N2_J2 J2_J4 J4_S2",
    "south_north_east": "S2_J4 J4_J2 J2_N2",
}


def generate_routes(config: dict[str, Any], scenario: str, output_file: Path = ROUTE_FILE) -> Path:
    """Write equal per-route traffic flows from the selected scenario's YAML rate."""
    scenarios = config["traffic"]["scenarios"]
    if scenario not in scenarios:
        raise ValueError(f"Unknown scenario '{scenario}'. Choose one of: {', '.join(scenarios)}")
    rate = int(scenarios[scenario]["vehicles_per_hour_per_route"])
    duration = int(config["simulation"]["duration_seconds"])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["<routes>", '    <vType id="passenger" accel="2.6" decel="4.5" length="5" maxSpeed="13.89" sigma="0.5"/>']
    for route_id, edges in ROUTES.items():
        lines.append(f'    <route id="{route_id}" edges="{edges}"/>')
        lines.append(f'    <flow id="flow_{route_id}" type="passenger" route="{route_id}" begin="0" end="{duration}" vehsPerHour="{rate}" departLane="best" departSpeed="max"/>')
    lines.append("</routes>")
    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_file
