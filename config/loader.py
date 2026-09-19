"""YAML configuration loader kept independent from simulation implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "simulation.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration and resolve project-relative SUMO paths."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a mapping: {config_path}")
    for key in ("network_file", "sumo_config_file"):
        config["network"][key] = str((PROJECT_ROOT / config["network"][key]).resolve())
    return config
