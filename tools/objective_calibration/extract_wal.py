from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def _parse_day_from_filename(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    try:
        out = int(value)
    except Exception:
        return None
    return out if out > 0 else None


def _flatten_objective_trace(trace: dict[str, Any] | None, *, prefix: str) -> dict[str, Any]:
    if not isinstance(trace, dict):
        return {}
    payload: dict[str, Any] = {
        f"{prefix}_trace_id": trace.get("trace_id"),
        f"{prefix}_multiplier": trace.get("multiplier"),
        f"{prefix}_objective_score": trace.get("objective_score"),
    }
    components = trace.get("components")
    if isinstance(components, dict):
        for key, value in components.items():
            payload[f"{prefix}_component_{key}"] = value
    raw_metrics = trace.get("raw_metrics")
    if isinstance(raw_metrics, dict):
        for key, value in raw_metrics.items():
            payload[f"{prefix}_metric_{key}"] = value
    return payload


def _flatten_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    payload = raw.get("pld") if isinstance(raw.get("pld"), dict) else {}
    verb = str(raw.get("verb") or "")
    base = {
        "verb": verb,
        "ts_ms": _to_int(raw.get("ts") or raw.get("timestamp") or payload.get("ts_ms") or payload.get("ts")),
        "rid": payload.get("rid") or raw.get("rid"),
    }
    if verb == "TRADE_INTENT_PROPOSED":
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
        out = {
            **base,
            "strategy_id": payload.get("strategy") or payload.get("strategy_id"),
            "symbol": payload.get("instrument") or payload.get("symbol"),
            "side": payload.get("side"),
            "entry_rid": payload.get("rid") or raw.get("rid"),
            "signal_id": (
                trace.get("alpha_search", {}).get("signal_id")
                if isinstance(trace.get("alpha_search"), dict)
                else None
            ),
            "reduce_only": bool(order.get("reduce_only")),
            "regime": payload.get("regime"),
            "reason_code": None,
            "why": payload.get("why"),
            "price_ref": order.get("price_ref") or order.get("price"),
        }
        out.update(_flatten_objective_trace(trace.get("objective"), prefix="objective"))
        return out
    if verb.startswith("TRADE_INTENT_REJECTED"):
        return {
            **base,
            "strategy_id": payload.get("strategy_id") or payload.get("strategy"),
            "symbol": payload.get("symbol") or payload.get("instrument"),
            "side": payload.get("side"),
            "entry_rid": payload.get("rid") or raw.get("rid"),
            "signal_id": payload.get("signal_id"),
            "reduce_only": False,
            "regime": payload.get("regime"),
            "reason_code": payload.get("reason_code"),
            "why": payload.get("why") or payload.get("why_chain"),
            "price_ref": None,
        }
    if verb == "OBJECTIVE_REALIZED_V1":
        out = {
            **base,
            "strategy_id": payload.get("strategy_id"),
            "symbol": payload.get("symbol"),
            "side": None,
            "entry_rid": payload.get("entry_rid"),
            "close_rid": payload.get("close_rid"),
            "signal_id": payload.get("signal_id"),
            "reduce_only": False,
            "regime": payload.get("regime_entry"),
            "regime_exit": payload.get("regime_exit"),
            "reason_code": payload.get("close_reason"),
            "why": payload.get("close_reason"),
            "price_ref": None,
            "realized_quality_score": payload.get("realized_quality_score"),
            "realized_pnl": payload.get("realized_pnl"),
            "fees": payload.get("fees"),
            "duration_sec": payload.get("duration_sec"),
            "mae": payload.get("mae"),
            "mfe": payload.get("mfe"),
        }
        out.update(_flatten_objective_trace(payload.get("pretrade_objective_trace"), prefix="pretrade"))
        realized_components = payload.get("realized_components")
        if isinstance(realized_components, dict):
            for key, value in realized_components.items():
                out[f"realized_component_{key}"] = value
        return out
    return None


def load_wal_events(
    wal_dir: Path,
    *,
    start: date | None,
    end: date | None,
    verbs: Iterable[str] | None = None,
) -> pd.DataFrame:
    verb_allow = {str(verb) for verb in verbs} if verbs is not None else None
    rows: list[dict[str, Any]] = []
    if not wal_dir.exists():
        return pd.DataFrame()

    for path in sorted(wal_dir.glob("*.jsonl")):
        day = _parse_day_from_filename(path)
        if day is None:
            continue
        if start is not None and day < start:
            continue
        if end is not None and day >= end:
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    raw = json.loads(line)
                except Exception:
                    continue
                verb = str(raw.get("verb") or "")
                if verb_allow is not None and verb not in verb_allow:
                    continue
                flat = _flatten_event(raw)
                if flat is None:
                    continue
                flat["wal_day"] = day.isoformat()
                rows.append(flat)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "ts_ms" in df.columns:
        df["ts_ms"] = pd.to_numeric(df["ts_ms"], errors="coerce")
    return df.sort_values(["ts_ms", "verb"], kind="mergesort").reset_index(drop=True)
