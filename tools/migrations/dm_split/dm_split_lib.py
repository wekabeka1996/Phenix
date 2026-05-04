"""Shared helpers for the decision_making split migration."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[3]
DM_ROOT = ROOT / "apps" / "reference" / "domains" / "decision_making"
MOVE_MAP = ROOT / "tools" / "migrations" / "dm_split" / "dm_move_map.csv"
ARTIFACTS = ROOT / "tools" / "migrations" / "dm_split" / "artifacts"
OLD_PREFIX = "apps.reference.domains.decision_making"


@dataclass(frozen=True)
class MoveRow:
    source_path: str
    target_path: str

    @property
    def source(self) -> Path:
        return ROOT / self.source_path

    @property
    def target(self) -> Path:
        return ROOT / self.target_path

    @property
    def old_module(self) -> str:
        return path_to_module(self.source_path)

    @property
    def new_module(self) -> str:
        return path_to_module(self.target_path)


def path_to_module(path: str) -> str:
    return path[:-3].replace("/", ".").replace("\\", ".")


def module_to_path(module: str) -> Path:
    return ROOT / (module.replace(".", "/") + ".py")


def load_move_map(path: Path = MOVE_MAP) -> list[MoveRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows: list[MoveRow] = []
        for row in csv.DictReader(handle):
            source_path = row.get("source_path") or row.get("source")
            target_path = row.get("target_path") or row.get("destination")
            if not source_path or not target_path:
                raise ValueError(f"Unsupported move-map row in {path}: {row}")
            rows.append(MoveRow(source_path, target_path))
        return rows


def build_rename_plan(rows: Iterable[MoveRow]) -> dict[str, str]:
    return {
        row.old_module: row.new_module
        for row in rows
        if row.old_module != row.new_module
    }


def write_json(path: Path, payload: object, *, dry_run: bool) -> None:
    if dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    sort_keys=True) + "\n", encoding="utf-8")


def iter_python_files(paths: Iterable[str] = ("apps", "tests", "tools", "scripts")) -> Iterable[Path]:
    for rel in paths:
        root = ROOT / rel
        if root.exists():
            for path in root.rglob("*.py"):
                if "__pycache__" not in path.parts:
                    yield path


def run_git_mv(source: Path, target: Path, *, dry_run: bool) -> None:
    if source == target:
        return
    if not source.exists() and target.exists():
        return
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "mv", str(source.relative_to(ROOT)),
           str(target.relative_to(ROOT))]
    if dry_run:
        print(" ".join(cmd))
        return
    subprocess.run(cmd, cwd=ROOT, check=True)


def main_guard() -> None:
    if not ROOT.exists():
        print("Cannot resolve repository root", file=sys.stderr)
        raise SystemExit(2)
