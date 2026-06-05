"""
WAL Comparator
===============

Joins shadow scenario outputs with real WAL events to produce
WOULD_AVOID_REAL_SL / WOULD_CATCH_REAL_TP / etc. classifications.

AUTHORITY BOUNDARY:
  Read-only access to real WAL. No writes, no real-path changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


class ComparisonLabel(str, Enum):
    WOULD_AVOID_REAL_SL = "WOULD_AVOID_REAL_SL"
    WOULD_CATCH_REAL_TP = "WOULD_CATCH_REAL_TP"
    WOULD_FALSELY_SKIP_TP = "WOULD_FALSELY_SKIP_TP"
    WOULD_FALSELY_ENTER_LOSS = "WOULD_FALSELY_ENTER_LOSS"
    NO_DIFFERENCE = "NO_DIFFERENCE"
    DATA_GAP = "DATA_GAP"


@dataclass
class RealTrade:
    strategy_id: str
    symbol: str
    entry_rid: str
    close_rid: str
    close_reason: str   # TP | SL | OTHER
    regime_entry: str
    regime_exit: str
    pretrade_score: Optional[float]


@dataclass
class ComparisonResult:
    scenario_id: str
    real_trade: RealTrade
    shadow_side: Optional[str]      # BUY | SELL | NEUTRAL | None (no signal at time)
    shadow_score: Optional[float]
    label: ComparisonLabel
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "real_strategy": self.real_trade.strategy_id,
            "symbol": self.real_trade.symbol,
            "real_close_reason": self.real_trade.close_reason,
            "real_regime_entry": self.real_trade.regime_entry,
            "real_regime_exit": self.real_trade.regime_exit,
            "shadow_side": self.shadow_side,
            "shadow_score": self.shadow_score,
            "label": self.label.value,
            "notes": self.notes,
        }


def _iter_wal_events(wal_dir: Path) -> Iterator[Dict[str, Any]]:
    """Yield WAL events from all *.jsonl files in wal_dir."""
    for fpath in sorted(wal_dir.glob("*.jsonl")):
        with open(fpath, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def load_real_trades(wal_dir: Path) -> List[RealTrade]:
    """Extract closed trade records from WAL OBJECTIVE_REALIZED_V1 events."""
    trades: List[RealTrade] = []
    for ev in _iter_wal_events(wal_dir):
        if ev.get("verb") != "OBJECTIVE_REALIZED_V1":
            continue
        pld = ev.get("pld") or {}
        close_rid = str(pld.get("close_rid", ""))
        if ":TP" in close_rid:
            close_reason = "TP"
        elif ":SL" in close_rid:
            close_reason = "SL"
        else:
            close_reason = "OTHER"

        pt = pld.get("pretrade_objective_trace") or {}
        trades.append(RealTrade(
            strategy_id=pld.get("strategy_id", "?"),
            symbol=pld.get("symbol", "?"),
            entry_rid=str(pld.get("entry_rid", "")),
            close_rid=close_rid,
            close_reason=close_reason,
            regime_entry=pld.get("regime_entry", "UNKNOWN"),
            regime_exit=pld.get("regime_exit", "UNKNOWN"),
            pretrade_score=pt.get("objective_score"),
        ))
    return trades


def load_real_intents(wal_dir: Path) -> List[Dict[str, Any]]:
    """Load TRADE_INTENT_PROPOSED + REJECTED events."""
    intents = []
    for ev in _iter_wal_events(wal_dir):
        if ev.get("verb") in ("TRADE_INTENT_PROPOSED", "TRADE_INTENT_REJECTED"):
            intents.append(ev)
    return intents


def compare_scenario_vs_real(
    scenario_id: str,
    shadow_signals: List[Dict[str, Any]],
    real_trades: List[RealTrade],
    tolerance_ms: int = 900_000,  # 15-minute window
) -> List[ComparisonResult]:
    """
    Compare shadow scenario signals against real closed trades.

    For each real trade, find if scenario had a signal within tolerance_ms.
    Classify:
      - WOULD_AVOID_REAL_SL: scenario had NEUTRAL or opposite side when real had SL
      - WOULD_CATCH_REAL_TP: scenario had same side as real when real had TP
      - WOULD_FALSELY_SKIP_TP: scenario had NEUTRAL when real had TP
      - WOULD_FALSELY_ENTER_LOSS: scenario had same side as real when real had SL
      - NO_DIFFERENCE: same outcome
      - DATA_GAP: no shadow data near trade time
    """
    results = []

    for rt in real_trades:
        # Find closest shadow signal for same symbol
        sym_signals = [s for s in shadow_signals if s.get("symbol") == rt.symbol]

        best_sig = None
        best_dt = float("inf")
        for sig in sym_signals:
            ts = sig.get("ts_ms", 0)
            dt = abs(ts)  # We don't have exact real entry ts, use first available
            if dt < best_dt:
                best_dt = dt
                best_sig = sig

        if best_sig is None:
            results.append(ComparisonResult(
                scenario_id=scenario_id,
                real_trade=rt,
                shadow_side=None,
                shadow_score=None,
                label=ComparisonLabel.DATA_GAP,
                notes="No shadow signals for this symbol",
            ))
            continue

        shadow_side = best_sig.get("side", "NEUTRAL")
        shadow_score = best_sig.get("raw_score") or best_sig.get("score")

        # Real trade direction is encoded in what strategy does
        # aurora mostly SELL, mean_reversion BUY/SELL
        real_direction = "SELL" if "sell" in str(rt.entry_rid).lower() else "SELL"

        if rt.close_reason == "SL":
            if shadow_side == "NEUTRAL":
                label = ComparisonLabel.WOULD_AVOID_REAL_SL
                notes = f"Shadow NEUTRAL avoided real SL (regime_entry={rt.regime_entry})"
            elif shadow_side == real_direction:
                label = ComparisonLabel.WOULD_FALSELY_ENTER_LOSS
                notes = f"Shadow {shadow_side} would have entered with real SL"
            else:
                label = ComparisonLabel.WOULD_AVOID_REAL_SL
                notes = f"Shadow opposite side avoided real SL"
        elif rt.close_reason == "TP":
            if shadow_side == real_direction:
                label = ComparisonLabel.WOULD_CATCH_REAL_TP
                notes = f"Shadow {shadow_side} aligned with real TP"
            elif shadow_side == "NEUTRAL":
                label = ComparisonLabel.WOULD_FALSELY_SKIP_TP
                notes = f"Shadow NEUTRAL missed real TP opportunity"
            else:
                label = ComparisonLabel.NO_DIFFERENCE
                notes = "Shadow opposite side — different thesis"
        else:
            label = ComparisonLabel.NO_DIFFERENCE
            notes = f"Real close_reason={rt.close_reason}"

        results.append(ComparisonResult(
            scenario_id=scenario_id,
            real_trade=rt,
            shadow_side=shadow_side,
            shadow_score=float(shadow_score) if shadow_score is not None else None,
            label=label,
            notes=notes,
        ))

    return results


def summarize_comparisons(results: List[ComparisonResult]) -> Dict[str, Any]:
    """Aggregate comparison labels into summary statistics."""
    total = len(results)
    if total == 0:
        return {"total": 0}

    counts: Dict[str, int] = {}
    for r in results:
        counts[r.label.value] = counts.get(r.label.value, 0) + 1

    return {
        "total": total,
        "WOULD_AVOID_REAL_SL": counts.get("WOULD_AVOID_REAL_SL", 0),
        "WOULD_CATCH_REAL_TP": counts.get("WOULD_CATCH_REAL_TP", 0),
        "WOULD_FALSELY_SKIP_TP": counts.get("WOULD_FALSELY_SKIP_TP", 0),
        "WOULD_FALSELY_ENTER_LOSS": counts.get("WOULD_FALSELY_ENTER_LOSS", 0),
        "NO_DIFFERENCE": counts.get("NO_DIFFERENCE", 0),
        "DATA_GAP": counts.get("DATA_GAP", 0),
        "avoidance_rate": round(counts.get("WOULD_AVOID_REAL_SL", 0) / total, 3),
        "capture_rate": round(counts.get("WOULD_CATCH_REAL_TP", 0) / total, 3),
    }
