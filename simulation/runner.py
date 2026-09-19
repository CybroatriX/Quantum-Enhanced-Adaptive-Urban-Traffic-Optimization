"""Lifecycle management for SUMO and TraCI."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


def find_sumo_tool(name: str) -> str:
    """Locate a SUMO executable from PATH, SUMO_HOME, or Windows installer path."""
    if executable := shutil.which(name):
        return executable
    if sumo_home := os.environ.get("SUMO_HOME"):
        candidate = Path(sumo_home) / "bin" / f"{name}.exe"
        if candidate.exists():
            return str(candidate)
    # Eclipse SUMO's standard Windows installer location. This fallback makes
    # the project work before a terminal is restarted after a PATH update.
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidate = Path(program_files_x86) / "Eclipse" / "Sumo" / "bin" / f"{name}.exe"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError(f"SUMO tool '{name}' was not found. Install SUMO and configure PATH or SUMO_HOME.")


def find_sumo_binary(gui: bool = False) -> str:
    return find_sumo_tool("sumo-gui" if gui else "sumo")


class SumoRunner:
    """Own a TraCI connection, keeping controller code independently testable."""

    def __init__(self, sumo_config: str, step_length: float, gui: bool = False, seed: int = 42) -> None:
        self._sumo_config = sumo_config
        self._step_length = step_length
        self._gui = gui
        self._seed = seed
        self.traci: Any | None = None

    def start(self) -> Any:
        sumo_binary = find_sumo_binary(self._gui)
        # The PyPI TraCI package uses SUMO_HOME for optional schema validation.
        # Populate it from an auto-detected installation when the user has not.
        if not os.environ.get("SUMO_HOME"):
            os.environ["SUMO_HOME"] = str(Path(sumo_binary).resolve().parents[1])
        try:
            import traci
        except ImportError as error:
            raise RuntimeError("The 'traci' package is required. Run: pip install -r requirements.txt") from error
        traci.start([sumo_binary, "-c", self._sumo_config, "--step-length", str(self._step_length), "--seed", str(self._seed), "--no-step-log", "true", "--quit-on-end", "true"], label="phase1")
        self.traci = traci.getConnection("phase1")
        return self.traci

    def stop(self) -> None:
        if self.traci is not None:
            self.traci.close()
            self.traci = None

    def __enter__(self) -> Any:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.stop()
