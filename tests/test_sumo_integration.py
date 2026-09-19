"""Live checks execute only on a host with SUMO and TraCI installed."""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET

import pytest

from simulation.network.build_network import build_network
from simulation.runner import find_sumo_binary, find_sumo_tool

try:
    find_sumo_binary()
    find_sumo_tool("netconvert")
    SUMO_READY = bool(importlib.util.find_spec("traci"))
except RuntimeError:
    SUMO_READY = False
pytestmark = pytest.mark.skipif(not SUMO_READY, reason="Requires SUMO, netconvert, and the traci package.")


def test_network_builds_and_contains_four_signalized_intersections() -> None:
    root = ET.parse(build_network()).getroot()
    traffic_lights = {node.attrib["id"] for node in root.findall("junction") if node.attrib.get("type") == "traffic_light"}
    assert {"J1", "J2", "J3", "J4"}.issubset(traffic_lights)


@pytest.mark.parametrize("controller", ["fixed", "adaptive"])
def test_simulation_starts_generates_vehicles_reads_state_and_collects_metrics(controller: str) -> None:
    from simulation.run import run_simulation

    result = run_simulation(scenario="normal", duration=30, controller_mode=controller)
    assert result["controller"] == controller
    assert len(result["intersections"]) == 4
    assert {state["intersection_id"] for state in result["intersections"]} == {"J1", "J2", "J3", "J4"}
    assert result["metrics"]["simulation_time_seconds"] == 30.0
