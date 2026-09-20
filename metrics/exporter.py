"""Export utilities for metrics evaluation results in CSV and JSON formats."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

PROTECTED_FILES = {
    "phase2_classical_comparison.csv",
    "phase3a_qubo_validation.csv",
    "phase3b_qaoa_sensitivity.csv",
    "phase3b_qaoa_sensitivity_summary.csv",
    "phase3b_qaoa_validation.csv",
}


def _verify_safe_path(filepath: Path) -> None:
    """Ensure we never overwrite existing validation results from previous phases."""
    if filepath.name in PROTECTED_FILES and filepath.exists():
        raise RuntimeError(f"Safety guard: Cannot overwrite protected baseline result file '{filepath.name}'.")


def export_metrics_csv(
    records: Sequence[Mapping[str, Any] | Any],
    filepath: Path | str,
) -> Path:
    """Export a list of metric records or dictionaries to CSV."""
    path = Path(filepath)
    _verify_safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        path.write_text("", encoding="utf-8")
        return path

    # Convert dataclasses to dicts if needed
    dict_rows: list[dict[str, Any]] = []
    for r in records:
        if hasattr(r, "to_dict"):
            dict_rows.append(r.to_dict())
        elif isinstance(r, dict):
            dict_rows.append(dict(r))
        else:
            dict_rows.append(vars(r))

    fieldnames = list(dict_rows[0].keys())

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in dict_rows:
            # Flatten non-primitive fields if any
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (list, tuple, dict)):
                    clean_row[k] = json.dumps(v)
                else:
                    clean_row[k] = v
            writer.writerow(clean_row)

    return path


def export_metrics_json(
    data: Any,
    filepath: Path | str,
    indent: int = 2,
) -> Path:
    """Export structured metrics data to JSON."""
    path = Path(filepath)
    _verify_safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def serializer(obj: Any) -> Any:
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, default=serializer, indent=indent)

    return path


def export_summary_csv(
    records: Sequence[Mapping[str, Any] | Any],
    filepath: Path | str,
) -> Path:
    """Export compact comparison summary table to CSV."""
    return export_metrics_csv(records, filepath)
