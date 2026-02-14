"""Helper to convert search_space JSON → skopt dimensions"""
from __future__ import annotations

import json
from pathlib import Path
from skopt.space import Real, Integer, Categorical


def build_skopt_space(space_json: dict) -> tuple[list, list]:
    """
    Build skopt dimensions from standardized JSON search space.

    Returns:
        (dims, names) - skopt dimension objects and their names
    """
    dims = []
    names = []

    for d in space_json["dimensions"]:
        t = d["type"]
        names.append(d["name"])

        if t == "real":
            dims.append(
                Real(
                    d["low"],
                    d["high"],
                    prior=d.get("prior", "uniform"),
                    name=d["name"]
                )
            )
        elif t == "integer":
            dims.append(
                Integer(
                    d["low"],
                    d["high"],
                    prior=d.get("prior", "uniform"),
                    name=d["name"]
                )
            )
        elif t == "categorical":
            dims.append(
                Categorical(
                    d["categories"],
                    name=d["name"]
                )
            )
        else:
            raise ValueError(f"unknown dimension type: {t}")

    return dims, names


def load_search_space(json_path: str | Path) -> dict:
    """Load search space JSON from file."""
    with open(json_path) as f:
        return json.load(f)


if __name__ == "__main__":
    # Quick test
    stage0_path = Path(__file__).parent / "search_space_stage0.json"
    stage1_path = Path(__file__).parent / "search_space_stage1.json"

    if stage0_path.exists():
        space0 = load_search_space(stage0_path)
        dims0, names0 = build_skopt_space(space0)
        print(f"Stage 0: {len(dims0)} dimensions")
        for name in names0[:3]:
            print(f"  - {name}")

    if stage1_path.exists():
        space1 = load_search_space(stage1_path)
        dims1, names1 = build_skopt_space(space1)
        print(f"Stage 1: {len(dims1)} dimensions")
        for name in names1[:3]:
            print(f"  - {name}")
