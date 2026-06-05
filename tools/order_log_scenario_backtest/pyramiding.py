from __future__ import annotations

from bisect import bisect_right
import json
from pathlib import Path
from typing import Any

from tools.analysis.order_reconstruction_tp_sl_common import iso_utc, stringify, to_float, to_int, write_csv

from .models import CanonicalEntry, ScenarioRuntime

PYRAMIDING_SCENARIO_ID = "pyramiding_enabled_tp_sl_only"


def _ceil_to_minute_close_ts(ts_ms: int) -> int:
    remainder = ts_ms % 60000
    if remainder == 59999:
        return ts_ms
    return ((ts_ms // 60000) + 1) * 60000 - 1


def _next_candle_open_proxy_ts_ms(signal_ts_ms: int) -> int:
    return _ceil_to_minute_close_ts(signal_ts_ms) + 1


def _iter_pyramiding_rejects(runtime_root: Path, strategy_id: str) -> list[dict[str, Any]]:
    path = runtime_root / "shadow_critical_event_journal_v1.jsonl"
    if not path.exists():
        return []

    trace_by_rid: dict[str, dict[str, Any]] = {}
    rejects: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue

            rid = stringify(payload.get("rid")) or ""
            if not rid:
                continue
            event_name = stringify(payload.get("event_name")) or ""
            fragment = payload.get("payload_fragment") or {}
            event_strategy_id = stringify(payload.get("strategy_id")) or stringify(fragment.get("strategy_id")) or ""
            if event_strategy_id and event_strategy_id != strategy_id:
                continue

            if event_name == "EVT:QUADRATIC_DECISION_TRACE":
                anti_peak = fragment.get("anti_peak_observability") or {}
                score_path = anti_peak.get("score_path") or {}
                trace_by_rid[rid] = {
                    "regime_at_entry": stringify(fragment.get("regime")) or "UNKNOWN",
                    "regime_confidence_at_entry": to_float(fragment.get("regime_confidence")),
                    "signal_ts_ms": to_int(fragment.get("ts_ms")) or to_int(payload.get("ts_ms")) or 0,
                    "signal_score": to_float(score_path.get("final_score")),
                    "signal_threshold": to_float(score_path.get("signal_threshold")),
                    "raw_trace_payload": fragment,
                }
                continue

            if event_name != "EVT:TRADE_INTENT_REJECTED":
                continue

            reason_code = stringify(fragment.get("reason_code")) or ""
            if reason_code != "ANTI_PYRAMIDING_BLOCK":
                continue

            trace = trace_by_rid.get(rid) or {}
            signal_ts_ms = (
                to_int(trace.get("signal_ts_ms"))
                or to_int(fragment.get("ts_ms"))
                or to_int(payload.get("ts_ms"))
                or 0
            )
            rejects.append(
                {
                    "rid": rid,
                    "symbol": stringify(payload.get("symbol")) or stringify(fragment.get("symbol")) or "",
                    "side": (stringify(payload.get("side")) or stringify(fragment.get("side")) or "").upper(),
                    "strategy_id": event_strategy_id or strategy_id,
                    "reason_code": reason_code,
                    "signal_ts_ms": signal_ts_ms,
                    "regime_at_entry": stringify(trace.get("regime_at_entry")) or "UNKNOWN",
                    "regime_confidence_at_entry": to_float(trace.get("regime_confidence_at_entry")),
                    "signal_score": to_float(trace.get("signal_score")),
                    "signal_threshold": to_float(trace.get("signal_threshold")),
                    "why_chain": fragment.get("why_chain") or [],
                    "raw_surface": trace.get("raw_trace_payload") or fragment,
                    "source_line": line_no,
                }
            )
    return rejects


def _group_actual_entries(entries: list[CanonicalEntry]) -> dict[tuple[str, str], list[CanonicalEntry]]:
    grouped: dict[tuple[str, str], list[CanonicalEntry]] = {}
    for entry in entries:
        grouped.setdefault((entry.symbol, entry.side.upper()), []).append(entry)
    for key in grouped:
        grouped[key].sort(key=lambda item: (item.entry_ts_ms, item.entry_id))
    return grouped


def _active_reference_entries(
    grouped_entries: dict[tuple[str, str], list[CanonicalEntry]],
    *,
    symbol: str,
    side: str,
    signal_ts_ms: int,
) -> list[CanonicalEntry]:
    active: list[CanonicalEntry] = []
    for entry in grouped_entries.get((symbol, side.upper()), []):
        if entry.entry_ts_ms > signal_ts_ms:
            continue
        if entry.actual_close_ts_ms is not None and entry.actual_close_ts_ms <= signal_ts_ms:
            continue
        active.append(entry)
    return active


def _resolve_proxy_price(
    symbol: str,
    signal_ts_ms: int,
    runtime: ScenarioRuntime,
    *,
    materialize_price_proxy: bool,
) -> tuple[int | None, float | None, str]:
    proxy_entry_ts_ms = _next_candle_open_proxy_ts_ms(signal_ts_ms)
    if not materialize_price_proxy:
        return proxy_entry_ts_ms, 0.0, "next_candle_open_proxy_pending"

    series = runtime.candles_by_symbol.get(symbol)
    if series is None:
        return None, None, "symbol_candles_missing"

    next_candle_idx = bisect_right(series.timestamps, _ceil_to_minute_close_ts(signal_ts_ms))
    if next_candle_idx >= len(series.rows):
        return None, None, "next_candle_open_missing"

    candle = series.rows[next_candle_idx]
    return int(candle["timestamp"]) - 59999, float(candle["open"]), "next_candle_open_proxy"


def _resolve_leverage(runtime: ScenarioRuntime, symbol: str, reference_entry: CanonicalEntry) -> float:
    instruments = runtime.config.get("instruments") or {}
    instrument_cfg = instruments.get(symbol) or {}
    leverage = to_float(instrument_cfg.get("target_leverage"))
    if leverage is not None:
        return float(leverage)
    return float(reference_entry.leverage)


def build_pyramiding_enabled_entry_set(
    entries: list[CanonicalEntry],
    runtime: ScenarioRuntime,
    *,
    materialize_price_proxy: bool,
    emit_artifacts: bool,
) -> list[CanonicalEntry]:
    grouped_actual_entries = _group_actual_entries(entries)
    strategy_id = stringify(runtime.config.get("strategy_id")) or "aurora"
    rejects = _iter_pyramiding_rejects(runtime.runtime_root, strategy_id)
    synthetic_entries: list[CanonicalEntry] = []
    seen_entry_ids = {entry.entry_id for entry in entries}
    audit_rows: list[dict[str, Any]] = []

    for reject in rejects:
        symbol = reject["symbol"]
        side = reject["side"]
        signal_ts_ms = int(reject["signal_ts_ms"] or 0)
        active_refs = _active_reference_entries(
            grouped_actual_entries,
            symbol=symbol,
            side=side,
            signal_ts_ms=signal_ts_ms,
        )
        audit_row = {
            "scenario_id": PYRAMIDING_SCENARIO_ID,
            "rid": reject["rid"],
            "symbol": symbol,
            "side": side,
            "strategy_id": reject["strategy_id"],
            "signal_ts_ms": signal_ts_ms,
            "signal_time_iso": iso_utc(signal_ts_ms) or "",
            "reference_entry_id": "",
            "reference_lifecycle_id": "",
            "active_reference_count": len(active_refs),
            "proxy_entry_ts_ms": "",
            "proxy_entry_time_iso": "",
            "proxy_entry_price": "",
            "leverage": "",
            "status": "skipped",
            "detail": "",
            "source_line": reject["source_line"],
        }
        if not symbol or not side or signal_ts_ms <= 0:
            audit_row["detail"] = "reject_identity_incomplete"
            audit_rows.append(audit_row)
            continue
        if not active_refs:
            audit_row["detail"] = "no_active_same_side_reference_entry"
            audit_rows.append(audit_row)
            continue

        reference_entry = active_refs[-1]
        proxy_entry_ts_ms, proxy_entry_price, proxy_quality = _resolve_proxy_price(
            symbol,
            signal_ts_ms,
            runtime,
            materialize_price_proxy=materialize_price_proxy,
        )
        if proxy_entry_ts_ms is None or proxy_entry_price is None:
            audit_row["reference_entry_id"] = reference_entry.entry_id
            audit_row["reference_lifecycle_id"] = reference_entry.lifecycle_id
            audit_row["detail"] = proxy_quality
            audit_rows.append(audit_row)
            continue

        entry_id = f"pyramid_add:{reject['rid']}"
        if entry_id in seen_entry_ids:
            audit_row["reference_entry_id"] = reference_entry.entry_id
            audit_row["reference_lifecycle_id"] = reference_entry.lifecycle_id
            audit_row["detail"] = "duplicate_candidate_entry_id"
            audit_rows.append(audit_row)
            continue

        leverage = _resolve_leverage(runtime, symbol, reference_entry)
        audit_row.update(
            {
                "reference_entry_id": reference_entry.entry_id,
                "reference_lifecycle_id": reference_entry.lifecycle_id,
                "proxy_entry_ts_ms": proxy_entry_ts_ms,
                "proxy_entry_time_iso": iso_utc(proxy_entry_ts_ms) or "",
                "proxy_entry_price": proxy_entry_price,
                "leverage": leverage,
                "status": "converted",
                "detail": proxy_quality,
            }
        )
        candidate = CanonicalEntry(
            entry_id=entry_id,
            lifecycle_id=entry_id,
            rid=reject["rid"],
            trade_id="",
            symbol=symbol,
            side=side,
            strategy_id=reject["strategy_id"],
            entry_ts_ms=proxy_entry_ts_ms,
            entry_time_iso=iso_utc(proxy_entry_ts_ms) or "",
            entry_price=float(proxy_entry_price),
            qty=0.0,
            leverage=leverage,
            timestamp_quality=proxy_quality,
            reconstruction_confidence="counterfactual_proxy",
            regime_at_entry=reject["regime_at_entry"] or reference_entry.regime_at_entry,
            regime_confidence_at_entry=reject["regime_confidence_at_entry"],
            regime_source="shadow_quadratic_trace",
            entry_origin="synthetic_pyramiding_reject_proxy",
            notes=(
                "counterfactual_same_side_pyramiding_add",
                "source_reason_code=ANTI_PYRAMIDING_BLOCK",
                "entry_price_proxy=next_candle_open",
                "qty_non_authoritative=0",
                f"reference_entry_id={reference_entry.entry_id}",
            ),
            raw_surface={
                "signal_ts_ms": signal_ts_ms,
                "signal_score": reject["signal_score"],
                "signal_threshold": reject["signal_threshold"],
                "why_chain": list(reject["why_chain"]),
                "reference_entry_id": reference_entry.entry_id,
                "reference_lifecycle_id": reference_entry.lifecycle_id,
                "source_line": reject["source_line"],
                "raw_trace_payload": reject["raw_surface"],
            },
        )
        synthetic_entries.append(candidate)
        seen_entry_ids.add(entry_id)
        audit_rows.append(audit_row)

    if emit_artifacts:
        summary = {
            "scenario_id": PYRAMIDING_SCENARIO_ID,
            "rejects_seen": len(rejects),
            "synthetic_entries": len(synthetic_entries),
            "skipped_candidates": sum(1 for row in audit_rows if row["status"] != "converted"),
        }
        write_csv(
            runtime.report_root / "pyramiding_candidate_audit.csv",
            [
                "scenario_id",
                "rid",
                "symbol",
                "side",
                "strategy_id",
                "signal_ts_ms",
                "signal_time_iso",
                "reference_entry_id",
                "reference_lifecycle_id",
                "active_reference_count",
                "proxy_entry_ts_ms",
                "proxy_entry_time_iso",
                "proxy_entry_price",
                "leverage",
                "status",
                "detail",
                "source_line",
            ],
            audit_rows,
        )
        (runtime.report_root / "pyramiding_candidate_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    combined_entries = list(entries) + synthetic_entries
    combined_entries.sort(key=lambda entry: (entry.entry_ts_ms, entry.entry_id))
    return combined_entries
