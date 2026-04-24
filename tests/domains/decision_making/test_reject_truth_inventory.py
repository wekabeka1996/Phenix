"""Inventory lock for the current TRADE_INTENT_REJECTED shaping surface."""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DM_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "decision_making"

EXPECTED_SHAPERS = {
    ("apps/reference/domains/decision_making/intent_emitter.py", "canonical"),
    ("apps/reference/domains/decision_making/aurora_handler.py", "handler_local_wal"),
    ("apps/reference/domains/decision_making/mean_reversion_handler.py", "handler_local_wal"),
    ("apps/reference/domains/decision_making/md_amr_handler.py", "handler_local_emit"),
}

WAL_PATTERN = re.compile(r"\bwrite_trade_intent_rejected\s*\(")
EMIT_PATTERN = re.compile(
    r'(?:(?:self\._fsm|self\.fsm|fsm)\.emit|emit_fn)\(\s*["\']EVT:TRADE_INTENT_REJECTED["\']'
)


def _relpath(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _classify_shaper(path: Path, text: str) -> str | None:
    rel = _relpath(path)
    has_wal = bool(WAL_PATTERN.search(text))
    has_emit = bool(EMIT_PATTERN.search(text))

    if rel == "apps/reference/domains/decision_making/intent_emitter.py":
        return "canonical" if has_wal and has_emit else None
    if rel in {
        "apps/reference/domains/decision_making/aurora_handler.py",
        "apps/reference/domains/decision_making/mean_reversion_handler.py",
    }:
        return "handler_local_wal" if has_wal else None
    if rel == "apps/reference/domains/decision_making/md_amr_handler.py":
        return "handler_local_emit" if has_emit and not has_wal else None
    return None


def test_reject_truth_inventory_matches_expected() -> None:
    """Lock the known split across the controller-authorized file inventory."""
    discovered = set()

    tracked_files = sorted(
        DM_DIR / Path(path).name
        for path, _kind in EXPECTED_SHAPERS
    )
    for path in tracked_files:
        text = path.read_text(encoding="utf-8")
        rel = _relpath(path)

        kind = _classify_shaper(path, text)
        if kind is not None:
            discovered.add((rel, kind))

    assert discovered == EXPECTED_SHAPERS
    assert _classify_shaper(DM_DIR / "trade_intent_reject_wal.py", (DM_DIR / "trade_intent_reject_wal.py").read_text(encoding="utf-8")) is None
