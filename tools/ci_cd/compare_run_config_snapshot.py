#!/usr/bin/env python3
"""Compare config snapshot from a backtest run vs current configs.

Goal:
- Detect keys/fields present in the run snapshot but missing in current configs.
- Report type mismatches (dict vs scalar) which often indicate schema drift.

This script intentionally focuses on *field presence*, not value diffs.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


def _load_current_resolved_via_loader() -> dict[str, Any]:
    # Import locally to keep script usable even if apps/ not on path in other contexts.
    import os
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.append(str(repo_root))
    from apps.reference.config_loader import ConfigLoader  # type: ignore

    # Ensure deterministic CWD expectations for loader if it uses relative paths.
    os.chdir(repo_root)
    config = ConfigLoader().load_config()

    # Pydantic v2: JSON mode ensures JSON-compatible primitives.
    dumped = config.model_dump(mode="json")  # type: ignore[call-arg]
    if dumped is None:
        return {}
    if not isinstance(dumped, dict):
        raise TypeError(f"Expected dict from config.model_dump(), got {type(dumped).__name__}")
    return dumped


_YAML_CODEBLOCK_RE = re.compile(r"```(?P<lang>yaml|yml)\s*\n(?P<body>.*?)(?:\n)?```", re.DOTALL | re.IGNORECASE)
_JSON_CODEBLOCK_RE = re.compile(r"```(?P<lang>json)\s*\n(?P<body>.*?)(?:\n)?```", re.DOTALL | re.IGNORECASE)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_yaml_from_markdown(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    match = _YAML_CODEBLOCK_RE.search(text)
    if not match:
        raise ValueError(f"No YAML code block found in markdown: {path}")
    data = yaml.safe_load(match.group("body"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected YAML mapping at root in {path}, got {type(data).__name__}")
    return data


def _load_json_from_markdown(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    match = _JSON_CODEBLOCK_RE.search(text)
    if not match:
        raise ValueError(f"No JSON code block found in markdown: {path}")
    data = json.loads(match.group("body"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object at root in {path}, got {type(data).__name__}")
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(_read_text(path))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected YAML mapping at root in {path}, got {type(data).__name__}")
    return data


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__


@dataclass(frozen=True)
class DiffItem:
    kind: str  # missing_key | type_mismatch
    path: str
    snapshot_type: str | None = None
    current_type: str | None = None


def _iter_missing_and_mismatched(snapshot: Any, current: Any, base_path: str) -> Iterable[DiffItem]:
    # Only compare dict keys recursively.
    if _is_mapping(snapshot) and _is_mapping(current):
        for key, snap_val in snapshot.items():
            next_path = f"{base_path}.{key}" if base_path else str(key)
            if key not in current:
                yield DiffItem(kind="missing_key", path=next_path, snapshot_type=_type_name(snap_val))
                continue
            cur_val = current[key]
            snap_is_map = _is_mapping(snap_val)
            cur_is_map = _is_mapping(cur_val)
            if snap_is_map != cur_is_map:
                yield DiffItem(
                    kind="type_mismatch",
                    path=next_path,
                    snapshot_type=_type_name(snap_val),
                    current_type=_type_name(cur_val),
                )
                continue
            if snap_is_map and cur_is_map:
                yield from _iter_missing_and_mismatched(snap_val, cur_val, next_path)
        return

    # If snapshot is a mapping but current is not (or vice versa), caller handles.
    return


def _diff_files(snapshot_path: Path, current_path: Path, *, snapshot_is_markdown: bool) -> dict[str, Any]:
    if snapshot_is_markdown:
        snapshot = _load_yaml_from_markdown(snapshot_path)
    else:
        snapshot = _load_yaml(snapshot_path)

    current = _load_yaml(current_path)

    items = list(_iter_missing_and_mismatched(snapshot, current, base_path=""))
    return {
        "snapshot": str(snapshot_path),
        "current": str(current_path),
        "missing_keys": [i.path for i in items if i.kind == "missing_key"],
        "type_mismatches": [
            {
                "path": i.path,
                "snapshot_type": i.snapshot_type,
                "current_type": i.current_type,
            }
            for i in items
            if i.kind == "type_mismatch"
        ],
        "counts": {
            "missing_keys": sum(1 for i in items if i.kind == "missing_key"),
            "type_mismatches": sum(1 for i in items if i.kind == "type_mismatch"),
        },
    }


def _diff_dicts(snapshot: dict[str, Any], current: dict[str, Any], *, snapshot_label: str, current_label: str) -> dict[str, Any]:
    items = list(_iter_missing_and_mismatched(snapshot, current, base_path=""))
    return {
        "snapshot": snapshot_label,
        "current": current_label,
        "missing_keys": [i.path for i in items if i.kind == "missing_key"],
        "type_mismatches": [
            {
                "path": i.path,
                "snapshot_type": i.snapshot_type,
                "current_type": i.current_type,
            }
            for i in items
            if i.kind == "type_mismatch"
        ],
        "counts": {
            "missing_keys": sum(1 for i in items if i.kind == "missing_key"),
            "type_mismatches": sum(1 for i in items if i.kind == "type_mismatch"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--run-config-dir",
        default=None,
        help="Path to reports/backtests/<run_id>/config (defaults based on --run-id)",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Write JSON report to this path (defaults to ops/reports/...) ",
    )
    parser.add_argument(
        "--compare-resolved",
        action="store_true",
        help="Also compare run resolved_config.md (JSON) vs current reports/resolved_backtest_config.yaml",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    run_config_dir = Path(args.run_config_dir) if args.run_config_dir else repo_root / "reports" / "backtests" / args.run_id / "config"

    # Map snapshot -> current.
    # NOTE: For this repo layout, older runs often saved files under logical paths like
    # `config/aurora.yaml` and `config/ssot/*.yaml`, but the current workspace uses
    # `config/aurora/strategies/*.yaml` and `config/aurora/{system,trading,regime,...}.yaml`.
    comparisons: list[tuple[str, Path, Path, bool]] = [
        (
            "config/aurora.yaml (historical) -> config/aurora/strategies/aurora.yaml (current)",
            run_config_dir / "aurora.md",
            repo_root / "config" / "aurora" / "strategies" / "aurora.yaml",
            True,
        ),
        (
            "config/mean_reversion.yaml (historical) -> config/aurora/strategies/mean_reversion.yaml (current)",
            run_config_dir / "mean_reversion.md",
            repo_root / "config" / "aurora" / "strategies" / "mean_reversion.yaml",
            True,
        ),
        (
            "config/ssot/instruments.yaml (historical) -> config/aurora/instruments.yaml (current)",
            run_config_dir / "ssot" / "instruments.md",
            repo_root / "config" / "aurora" / "instruments.yaml",
            True,
        ),
        (
            "config/ssot/regime.yaml (historical) -> config/aurora/regime.yaml (current)",
            run_config_dir / "ssot" / "regime.md",
            repo_root / "config" / "aurora" / "regime.yaml",
            True,
        ),
        (
            "config/ssot/strategies.yaml (historical) -> config/aurora/strategies.yaml (current)",
            run_config_dir / "ssot" / "strategies.md",
            repo_root / "config" / "aurora" / "strategies.yaml",
            True,
        ),
        (
            "config/ssot/system.yaml (historical) -> config/aurora/system.yaml (current)",
            run_config_dir / "ssot" / "system.md",
            repo_root / "config" / "aurora" / "system.yaml",
            True,
        ),
        (
            "config/ssot/trading.yaml (historical) -> config/aurora/trading.yaml (current)",
            run_config_dir / "ssot" / "trading.md",
            repo_root / "config" / "aurora" / "trading.yaml",
            True,
        ),
    ]

    missing_files: list[str] = []
    mapping: list[dict[str, Any]] = []
    for note, snap, cur, _is_md in comparisons:
        mapping.append(
            {
                "note": note,
                "snapshot": str(snap),
                "current": str(cur),
                "snapshot_exists": snap.exists(),
                "current_exists": cur.exists(),
            }
        )
        if not snap.exists():
            missing_files.append(f"snapshot missing: {snap}")
        if not cur.exists():
            missing_files.append(f"current missing: {cur}")

    report: dict[str, Any] = {
        "run_id": args.run_id,
        "run_config_dir": str(run_config_dir),
        "path_mapping": mapping,
        "comparisons": [],
        "missing_files": missing_files,
    }

    if not missing_files:
        for note, snap, cur, is_md in comparisons:
            diff = _diff_files(snap, cur, snapshot_is_markdown=is_md)
            diff["note"] = note
            report["comparisons"].append(diff)

    # Resolved config comparison: broader surface (includes domains/observability/etc)
    if args.compare_resolved:
        run_resolved_md = repo_root / "reports" / "backtests" / args.run_id / "resolved_config.md"
        current_resolved_yaml = repo_root / "reports" / "resolved_backtest_config.yaml"
        resolved_missing: list[str] = []
        if not run_resolved_md.exists():
            resolved_missing.append(f"run resolved_config missing: {run_resolved_md}")
        # NOTE: we don't parse the YAML dump, since it can contain unsafe python tags (e.g. Decimal).
        # We load current resolved config via ConfigLoader instead.
        report["resolved"] = {
            "missing_files": resolved_missing,
            "diff": None,
        }
        if not resolved_missing:
            run_resolved = _load_json_from_markdown(run_resolved_md)
            current_resolved = _load_current_resolved_via_loader()
            report["resolved"]["diff"] = _diff_dicts(
                run_resolved,
                current_resolved,
                snapshot_label=str(run_resolved_md),
                current_label="ConfigLoader().load_config().model_dump(mode=json)",
            )

    out_path = Path(args.output_json) if args.output_json else (repo_root / "ops" / "reports" / f"config_missing_fields_vs_run_{args.run_id}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote report: {out_path}")
    hard_missing = bool(missing_files)

    resolved_diff = (report.get("resolved") or {}).get("diff")
    resolved_missing_files = (report.get("resolved") or {}).get("missing_files") or []

    if hard_missing or resolved_missing_files:
        print("Missing files detected; report contains details.")
        return 2

    total_missing = sum(c["counts"]["missing_keys"] for c in report["comparisons"]) + (
        resolved_diff["counts"]["missing_keys"] if resolved_diff else 0
    )
    total_mism = sum(c["counts"]["type_mismatches"] for c in report["comparisons"]) + (
        resolved_diff["counts"]["type_mismatches"] if resolved_diff else 0
    )
    print(f"Total missing keys: {total_missing}; type mismatches: {total_mism}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
