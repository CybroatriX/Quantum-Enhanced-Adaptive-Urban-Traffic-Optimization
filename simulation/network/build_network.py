"""Build the SUMO network from version-controlled node/edge sources."""

from __future__ import annotations

import subprocess
from pathlib import Path

from simulation.runner import find_sumo_tool

NETWORK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = NETWORK_DIR.parents[1]
OUTPUT_FILE = PROJECT_ROOT / "data" / "sumo" / "four_intersection.net.xml"


def build_network() -> Path:
    netconvert = find_sumo_tool("netconvert")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([netconvert, "--node-files", str(NETWORK_DIR / "four_intersection.nod.xml"), "--edge-files", str(NETWORK_DIR / "four_intersection.edg.xml"), "--output-file", str(OUTPUT_FILE), "--tls.guess", "true", "--tls.default-type", "static", "--no-turnarounds", "true"], check=True)
    return OUTPUT_FILE


if __name__ == "__main__":
    print(f"Built SUMO network: {build_network()}")
