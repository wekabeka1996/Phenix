from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
import json
from pathlib import Path
from statistics import mean
from typing import Any

from tools.analysis.order_reconstruction_tp_sl_common import iso_utc, stringify, to_float, to_int, write_csv

from .models import CanonicalEntry, ScenarioRuntime

REGIME_CONFIDENCE_SCENARIO_ID = "regime_confidence_disabled_tp_sl_only"
CONFIDENCE_DENY_REASONS = {"NRR-026", "NRR-063"}
CONFIDENCE_BREACH_KINDS = {"below_min", "above_max"}


def _ceil_to_minute_close_ts(ts_ms: int) -> int:
    remainder = ts_ms % 60000
    if remainder == 59999:
        return ts_ms
    return ((ts_ms // 60000) + 1) * 60000 - 1


def _next_candle_open_proxy_ts_ms(signal_ts_ms: int) -> int:
    return _ceil_to_minute_close_ts(signal_ts_ms) + 1


def _normalize_side(raw_side: Any) -> str:
    side = (stringify(raw_side) or "").upper()
    if side in {"BUY", "LONG"}:
        return "BUY"
    if side in {"SELL", "SHORT"}:
        return "SELL"
    return side


def _iter_confidence_denies(runtime_root: Path, strategy_id: str) -> list[dict[str, Any]]:
    path = runtime_root / "regime_confidence_audit_v1.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
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
            if stringify(payload.get("record_type")) not in {"decision", ""}:
                continue
            if stringify(payload.get("strategy_id")) != strategy_id:
                continue
            if stringify(payload.get("outcome")) != "DENY":
                continue
            breach_kind = stringify(payload.get("regime_confidence_breach_kind")) or ""
            deny_reason = stringify(payload.get("deny_reason")) or ""
            if breach_kind not in CONFIDENCE_BREACH_KINDS:
                continue
            if deny_reason not in CONFIDENCE_DENY_REASONS:
                continue
            if stringify(payload.get("regime_confidence_gate_verdict")) != "DENY":
                continue
            signal_ts_ms = to_int(payload.get("ts_ms")) or 0
            rid = stringify(payload.get("rid")) or ""
            symbol = stringify(payload.get("symbol")) or ""
            side = _normalize_side(payload.get("intent_side"))
            rows.append(
                {
                    "rid": rid,
                    "symbol": symbol,
                    "side": side,
                    "strategy_id": strategy_id,
                    "signal_ts_ms": signal_ts_ms,
                    "regime_at_signal": stringify(payload.get("regime_used")) or "UNKNOWN",
                    "regime_confidence_at_signal": to_float(payload.get("regime_confidence_used")),
                    "resolved_min_regime_confidence": to_float(payload.get("resolved_min_regime_confidence")),
                    "resolved_max_regime_confidence": to_float(payload.get("resolved_max_regime_confidence")),
                    "resolved_min_regime_confidence_source": stringify(
                        payload.get("resolved_min_regime_confidence_source")
                    )
                    or None,
                    "resolved_max_regime_confidence_source": stringify(
                        payload.get("resolved_max_regime_confidence_source")
                    )
                    or None,
                    "breach_kind": breach_kind,
                    "deny_reason": deny_reason,
                    "threshold_reason": stringify(payload.get("threshold_reason")) or "",
                    "why_short": stringify(payload.get("why_short")) or "",
                    "source_model": stringify(payload.get("source_model")) or "",
                    "detector_event_ts_ms": to_int(payload.get("detector_event_ts_ms")),
                    "bar_close_ts_ms": to_int(payload.get("bar_close_ts_ms")),
                    "basis_tf_sec": to_int(payload.get("basis_tf_sec")),
                    "audit_source_line": line_no,
                    "audit_payload": payload,
                }
            )
    return rows


def _load_shadow_details(runtime_root: Path, strategy_id: str) -> dict[str, dict[str, Any]]:
    path = runtime_root / "shadow_critical_event_journal_v1.jsonl"
    if not path.exists():
        return {}
    details: dict[str, dict[str, Any]] = {}
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
            fragment = payload.get("payload_fragment") or {}
            event_strategy_id = stringify(payload.get("strategy_id")) or stringify(fragment.get("strategy_id")) or ""
            if event_strategy_id and event_strategy_id != strategy_id:
                continue
            rid = stringify(payload.get("rid")) or ""
            if not rid:
                continue
            event_name = stringify(payload.get("event_name")) or ""
            slot = details.setdefault(rid, {})
            if event_name == "EVT:QUADRATIC_DECISION_TRACE":
                anti_peak = fragment.get("anti_peak_observability") or {}
                score_path = anti_peak.get("score_path") or {}
                slot.update(
                    {
                        "signal_score": to_float(score_path.get("final_score")),
                        "signal_threshold": to_float(score_path.get("signal_threshold")),
                        "shadow_signal_ts_ms": to_int(fragment.get("ts_ms")) or to_int(payload.get("ts_ms")),
                        "shadow_trace_payload": fragment,
                        "quadratic_source_line": line_no,
                    }
                )
            elif event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
                slot.update(
                    {
                        "why_chain": list(fragment.get("why_chain") or []),
                        "strategy_signal_source_line": line_no,
                    }
                )
            elif event_name == "EVT:DECISION_TRACE_EMITTED":
                slot.update(
                    {
                        "decision_trace_payload": fragment,
                        "decision_trace_source_line": line_no,
                    }
                )
    return details


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


def _resolve_leverage(runtime: ScenarioRuntime, symbol: str) -> float:
    instruments = runtime.config.get("instruments") or {}
    instrument_cfg = instruments.get(symbol) or {}
    leverage = to_float(instrument_cfg.get("target_leverage"))
    return float(leverage) if leverage is not None else 0.0


def _side_normalized_move_pct(side: str, start_price: float, end_price: float) -> float:
    if not start_price:
        return 0.0
    if side == "BUY":
        return (end_price - start_price) / start_price * 100.0
    return (start_price - end_price) / start_price * 100.0


def _microstructure_row(entry: CanonicalEntry, runtime: ScenarioRuntime) -> tuple[dict[str, Any], dict[str, Any]]:
    signal_ts_ms = to_int(entry.raw_surface.get("signal_ts_ms")) or entry.entry_ts_ms
    bar_close_ts_ms = to_int(entry.raw_surface.get("bar_close_ts_ms")) or _ceil_to_minute_close_ts(signal_ts_ms)
    series = runtime.candles_by_symbol.get(entry.symbol)
    base_row = {
        "scenario_id": REGIME_CONFIDENCE_SCENARIO_ID,
        "entry_id": entry.entry_id,
        "rid": entry.rid,
        "entry_origin": entry.entry_origin,
        "symbol": entry.symbol,
        "side": entry.side,
        "regime_at_entry": entry.regime_at_entry,
        "regime_confidence_at_entry": entry.regime_confidence_at_entry,
        "signal_ts_ms": signal_ts_ms,
        "signal_time_iso": iso_utc(signal_ts_ms) or "",
        "bar_close_ts_ms": bar_close_ts_ms,
        "bar_close_time_iso": iso_utc(bar_close_ts_ms) or "",
        "entry_ts_ms": entry.entry_ts_ms,
        "entry_time_iso": entry.entry_time_iso,
        "entry_price": entry.entry_price,
        "resolved_min_regime_confidence": entry.resolved_min_regime_confidence,
        "resolved_max_regime_confidence": entry.resolved_max_regime_confidence,
        "confidence_breach_kind": stringify(entry.raw_surface.get("breach_kind")) or "",
        "deny_reason": stringify(entry.raw_surface.get("deny_reason")) or "",
        "signal_score": to_float(entry.raw_surface.get("signal_score")),
        "signal_threshold": to_float(entry.raw_surface.get("signal_threshold")),
        "signal_margin_abs": "",
        "pre_3m_side_move_pct": "",
        "next_1m_side_move_pct": "",
        "next_3m_side_move_pct": "",
        "favorable_excursion_5m_pct": "",
        "adverse_excursion_5m_pct": "",
        "favorable_excursion_15m_pct": "",
        "adverse_excursion_15m_pct": "",
        "move_alignment_3m": "",
        "had_positive_excursion_5m": "",
        "had_positive_excursion_15m": "",
        "candles_available_15m": "false",
        "microstructure_quality": "missing_symbol_candles" if series is None else "ok",
    }
    signal_score = to_float(entry.raw_surface.get("signal_score"))
    signal_threshold = to_float(entry.raw_surface.get("signal_threshold"))
    if signal_score is not None and signal_threshold is not None:
        base_row["signal_margin_abs"] = round(abs(signal_score) - abs(signal_threshold), 8)

    if series is None:
        return base_row, {
            "entry_id": entry.entry_id,
            "symbol": entry.symbol,
            "signal_ts_ms": signal_ts_ms,
            "bar_close_ts_ms": bar_close_ts_ms,
            "bars_before": [],
            "anchor_bar": None,
            "bars_after": [],
        }

    anchor_idx = bisect_left(series.timestamps, bar_close_ts_ms)
    if anchor_idx >= len(series.rows) or series.timestamps[anchor_idx] != bar_close_ts_ms:
        anchor_idx = bisect_right(series.timestamps, bar_close_ts_ms) - 1
    if anchor_idx < 0:
        base_row["microstructure_quality"] = "anchor_bar_missing"
        return base_row, {
            "entry_id": entry.entry_id,
            "symbol": entry.symbol,
            "signal_ts_ms": signal_ts_ms,
            "bar_close_ts_ms": bar_close_ts_ms,
            "bars_before": [],
            "anchor_bar": None,
            "bars_after": [],
        }

    start_idx = max(0, anchor_idx - 3)
    end_idx = min(len(series.rows), anchor_idx + 16)
    anchor_bar = series.rows[anchor_idx]
    bars_before = series.rows[start_idx:anchor_idx]
    bars_after = series.rows[anchor_idx + 1 : min(len(series.rows), anchor_idx + 4)]
    if anchor_idx >= 3:
        prior_close = float(series.rows[anchor_idx - 3]["close"])
        base_row["pre_3m_side_move_pct"] = round(
            _side_normalized_move_pct(entry.side, prior_close, float(anchor_bar["close"])),
            8,
        )
    if anchor_idx + 1 < len(series.rows):
        close_1m = float(series.rows[anchor_idx + 1]["close"])
        base_row["next_1m_side_move_pct"] = round(
            _side_normalized_move_pct(entry.side, entry.entry_price, close_1m),
            8,
        )
    if anchor_idx + 3 < len(series.rows):
        close_3m = float(series.rows[anchor_idx + 3]["close"])
        next_3m = _side_normalized_move_pct(entry.side, entry.entry_price, close_3m)
        base_row["next_3m_side_move_pct"] = round(next_3m, 8)
        base_row["move_alignment_3m"] = "true" if next_3m > 0 else "false"

    def _excursions(limit_minutes: int) -> tuple[str, str]:
        slice_end = min(len(series.rows), anchor_idx + limit_minutes + 1)
        window = series.rows[anchor_idx:slice_end]
        if len(window) <= 1:
            return "", ""
        highs = [float(row["high"]) for row in window]
        lows = [float(row["low"]) for row in window]
        if entry.side == "BUY":
            favorable = (max(highs) - entry.entry_price) / entry.entry_price * 100.0
            adverse = (min(lows) - entry.entry_price) / entry.entry_price * 100.0
        else:
            favorable = (entry.entry_price - min(lows)) / entry.entry_price * 100.0
            adverse = (entry.entry_price - max(highs)) / entry.entry_price * 100.0
        return round(favorable, 8), round(adverse, 8)

    favorable_5m, adverse_5m = _excursions(5)
    favorable_15m, adverse_15m = _excursions(15)
    base_row["favorable_excursion_5m_pct"] = favorable_5m
    base_row["adverse_excursion_5m_pct"] = adverse_5m
    base_row["favorable_excursion_15m_pct"] = favorable_15m
    base_row["adverse_excursion_15m_pct"] = adverse_15m
    base_row["had_positive_excursion_5m"] = "true" if favorable_5m != "" and favorable_5m > 0 else "false"
    base_row["had_positive_excursion_15m"] = "true" if favorable_15m != "" and favorable_15m > 0 else "false"
    base_row["candles_available_15m"] = "true" if anchor_idx + 15 < len(series.rows) else "false"
    window_payload = {
        "entry_id": entry.entry_id,
        "symbol": entry.symbol,
        "side": entry.side,
        "entry_origin": entry.entry_origin,
        "regime_at_entry": entry.regime_at_entry,
        "signal_ts_ms": signal_ts_ms,
        "bar_close_ts_ms": bar_close_ts_ms,
        "bars_before": bars_before,
        "anchor_bar": anchor_bar,
        "bars_after": series.rows[anchor_idx + 1 : min(len(series.rows), anchor_idx + 4)],
    }
    return base_row, window_payload


def _write_microstructure_artifacts(
    scenario_root: Path,
    entries: list[CanonicalEntry],
    runtime: ScenarioRuntime,
) -> None:
    rows: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    for entry in entries:
        row, window = _microstructure_row(entry, runtime)
        rows.append(row)
        windows.append(window)

    write_csv(
        scenario_root / "microstructure_review.csv",
        [
            "scenario_id",
            "entry_id",
            "rid",
            "entry_origin",
            "symbol",
            "side",
            "regime_at_entry",
            "regime_confidence_at_entry",
            "signal_ts_ms",
            "signal_time_iso",
            "bar_close_ts_ms",
            "bar_close_time_iso",
            "entry_ts_ms",
            "entry_time_iso",
            "entry_price",
            "resolved_min_regime_confidence",
            "resolved_max_regime_confidence",
            "confidence_breach_kind",
            "deny_reason",
            "signal_score",
            "signal_threshold",
            "signal_margin_abs",
            "pre_3m_side_move_pct",
            "next_1m_side_move_pct",
            "next_3m_side_move_pct",
            "favorable_excursion_5m_pct",
            "adverse_excursion_5m_pct",
            "favorable_excursion_15m_pct",
            "adverse_excursion_15m_pct",
            "move_alignment_3m",
            "had_positive_excursion_5m",
            "had_positive_excursion_15m",
            "candles_available_15m",
            "microstructure_quality",
        ],
        rows,
    )
    (scenario_root / "microstructure_windows.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in windows) + "\n",
        encoding="utf-8",
    )

    synthetic_rows = [row for row in rows if row["entry_origin"] == "synthetic_regime_confidence_gate_proxy"]
    summary = {
        "scenario_id": REGIME_CONFIDENCE_SCENARIO_ID,
        "reviewed_entries": len(rows),
        "synthetic_entries": len(synthetic_rows),
        "actual_entries": sum(1 for row in rows if row["entry_origin"] != "synthetic_regime_confidence_gate_proxy"),
        "synthetic_alignment_3m_rate": round(
            sum(1 for row in synthetic_rows if row["move_alignment_3m"] == "true") / len(
                [row for row in synthetic_rows if row["move_alignment_3m"] in {"true", "false"}]
            ),
            6,
        )
        if any(row["move_alignment_3m"] in {"true", "false"} for row in synthetic_rows)
        else 0.0,
        "synthetic_positive_excursion_5m_rate": round(
            sum(1 for row in synthetic_rows if row["had_positive_excursion_5m"] == "true") / len(synthetic_rows),
            6,
        )
        if synthetic_rows
        else 0.0,
        "synthetic_avg_favorable_excursion_5m_pct": round(
            mean(
                float(row["favorable_excursion_5m_pct"])
                for row in synthetic_rows
                if row["favorable_excursion_5m_pct"] != ""
            ),
            8,
        )
        if any(row["favorable_excursion_5m_pct"] != "" for row in synthetic_rows)
        else 0.0,
        "synthetic_avg_adverse_excursion_5m_pct": round(
            mean(
                float(row["adverse_excursion_5m_pct"])
                for row in synthetic_rows
                if row["adverse_excursion_5m_pct"] != ""
            ),
            8,
        )
        if any(row["adverse_excursion_5m_pct"] != "" for row in synthetic_rows)
        else 0.0,
        "synthetic_breach_breakdown": dict(
            Counter(
                row["confidence_breach_kind"] or "UNKNOWN"
                for row in synthetic_rows
            )
        ),
        "synthetic_regime_breakdown": dict(
            Counter(
                row["regime_at_entry"] or "UNKNOWN"
                for row in synthetic_rows
            )
        ),
    }
    (scenario_root / "microstructure_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Microstructure Report: {REGIME_CONFIDENCE_SCENARIO_ID}",
        "",
        "## FACTS",
        f"- Reviewed entries: {summary['reviewed_entries']}",
        f"- Synthetic confidence-denied entries: {summary['synthetic_entries']}",
        f"- Actual opened entries inside scenario: {summary['actual_entries']}",
        f"- Synthetic 3m alignment rate: {summary['synthetic_alignment_3m_rate']}",
        f"- Synthetic positive 5m excursion rate: {summary['synthetic_positive_excursion_5m_rate']}",
        f"- Synthetic avg favorable 5m excursion: {summary['synthetic_avg_favorable_excursion_5m_pct']}",
        f"- Synthetic avg adverse 5m excursion: {summary['synthetic_avg_adverse_excursion_5m_pct']}",
        "",
        "## INFERENCES",
        "- Positive 3m alignment means the first three 1m bars after entry moved in the trade direction.",
        "- Positive excursion shows whether the market offered at least some in-trade edge shortly after the entry anchor.",
        "",
        "## ASSUMPTIONS",
        "- Microstructure anchoring uses the detector/audit bar_close_ts_ms when retained, otherwise the ceiling minute bar of the signal timestamp.",
        "- Synthetic confidence-denied entries use next-candle-open proxy pricing, so short-horizon microstructure is more reliable than exact ROI attribution.",
        "",
        "## UNKNOWNS",
        "- Recorder 1m bars do not preserve order-book depth or intra-minute path, so this is a bar-level microstructure review rather than tick-level proof.",
    ]
    (scenario_root / "microstructure_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_regime_confidence_disabled_entry_set(
    entries: list[CanonicalEntry],
    runtime: ScenarioRuntime,
    *,
    materialize_price_proxy: bool,
    emit_artifacts: bool,
) -> list[CanonicalEntry]:
    scenario_root = runtime.report_root / REGIME_CONFIDENCE_SCENARIO_ID
    if emit_artifacts:
        scenario_root.mkdir(parents=True, exist_ok=True)

    strategy_id = stringify(runtime.config.get("strategy_id")) or "aurora"
    denies = _iter_confidence_denies(runtime.runtime_root, strategy_id)
    shadow_details = _load_shadow_details(runtime.runtime_root, strategy_id)
    synthetic_entries: list[CanonicalEntry] = []
    seen_entry_ids = {entry.entry_id for entry in entries}
    audit_rows: list[dict[str, Any]] = []

    for deny in denies:
        rid = deny["rid"]
        symbol = deny["symbol"]
        side = deny["side"]
        signal_ts_ms = int(deny["signal_ts_ms"] or 0)
        audit_row = {
            "scenario_id": REGIME_CONFIDENCE_SCENARIO_ID,
            "rid": rid,
            "symbol": symbol,
            "side": side,
            "breach_kind": deny["breach_kind"],
            "deny_reason": deny["deny_reason"],
            "regime_at_signal": deny["regime_at_signal"],
            "regime_confidence_at_signal": deny["regime_confidence_at_signal"],
            "resolved_min_regime_confidence": deny["resolved_min_regime_confidence"],
            "resolved_max_regime_confidence": deny["resolved_max_regime_confidence"],
            "signal_ts_ms": signal_ts_ms,
            "signal_time_iso": iso_utc(signal_ts_ms) or "",
            "proxy_entry_ts_ms": "",
            "proxy_entry_time_iso": "",
            "proxy_entry_price": "",
            "leverage": "",
            "status": "skipped",
            "detail": "",
            "audit_source_line": deny["audit_source_line"],
        }
        if not rid or not symbol or side not in {"BUY", "SELL"} or signal_ts_ms <= 0:
            audit_row["detail"] = "deny_identity_incomplete"
            audit_rows.append(audit_row)
            continue
        proxy_entry_ts_ms, proxy_entry_price, proxy_quality = _resolve_proxy_price(
            symbol,
            signal_ts_ms,
            runtime,
            materialize_price_proxy=materialize_price_proxy,
        )
        if proxy_entry_ts_ms is None or proxy_entry_price is None:
            audit_row["detail"] = proxy_quality
            audit_rows.append(audit_row)
            continue
        entry_id = f"confidence_gate:{rid}"
        if entry_id in seen_entry_ids:
            audit_row["detail"] = "duplicate_candidate_entry_id"
            audit_rows.append(audit_row)
            continue

        shadow = shadow_details.get(rid) or {}
        leverage = _resolve_leverage(runtime, symbol)
        audit_row.update(
            {
                "proxy_entry_ts_ms": proxy_entry_ts_ms,
                "proxy_entry_time_iso": iso_utc(proxy_entry_ts_ms) or "",
                "proxy_entry_price": proxy_entry_price,
                "leverage": leverage,
                "status": "converted",
                "detail": proxy_quality,
            }
        )
        synthetic_entries.append(
            CanonicalEntry(
                entry_id=entry_id,
                lifecycle_id=entry_id,
                rid=rid,
                trade_id="",
                symbol=symbol,
                side=side,
                strategy_id=strategy_id,
                entry_ts_ms=proxy_entry_ts_ms,
                entry_time_iso=iso_utc(proxy_entry_ts_ms) or "",
                entry_price=float(proxy_entry_price),
                qty=0.0,
                leverage=leverage,
                timestamp_quality=proxy_quality,
                reconstruction_confidence="counterfactual_proxy",
                regime_at_entry=deny["regime_at_signal"],
                regime_confidence_at_entry=deny["regime_confidence_at_signal"],
                regime_source="regime_confidence_audit_v1",
                entry_origin="synthetic_regime_confidence_gate_proxy",
                notes=(
                    "counterfactual_confidence_gate_removed",
                    f"source_deny_reason={deny['deny_reason']}",
                    f"breach_kind={deny['breach_kind']}",
                    "entry_price_proxy=next_candle_open",
                    "qty_non_authoritative=0",
                ),
                resolved_min_regime_confidence=deny["resolved_min_regime_confidence"],
                resolved_min_regime_confidence_source=deny["resolved_min_regime_confidence_source"],
                resolved_max_regime_confidence=deny["resolved_max_regime_confidence"],
                resolved_max_regime_confidence_source=deny["resolved_max_regime_confidence_source"],
                raw_surface={
                    "signal_ts_ms": signal_ts_ms,
                    "bar_close_ts_ms": deny["bar_close_ts_ms"],
                    "detector_event_ts_ms": deny["detector_event_ts_ms"],
                    "basis_tf_sec": deny["basis_tf_sec"],
                    "breach_kind": deny["breach_kind"],
                    "deny_reason": deny["deny_reason"],
                    "threshold_reason": deny["threshold_reason"],
                    "why_short": deny["why_short"],
                    "source_model": deny["source_model"],
                    "signal_score": shadow.get("signal_score"),
                    "signal_threshold": shadow.get("signal_threshold"),
                    "why_chain": list(shadow.get("why_chain") or []),
                    "decision_trace_payload": shadow.get("decision_trace_payload") or {},
                    "quadratic_trace_payload": shadow.get("shadow_trace_payload") or {},
                    "audit_source_line": deny["audit_source_line"],
                },
            )
        )
        seen_entry_ids.add(entry_id)
        audit_rows.append(audit_row)

    combined_entries = list(entries) + synthetic_entries
    combined_entries.sort(key=lambda entry: (entry.entry_ts_ms, entry.entry_id))

    if emit_artifacts:
        summary = {
            "scenario_id": REGIME_CONFIDENCE_SCENARIO_ID,
            "confidence_denies_seen": len(denies),
            "synthetic_entries": len(synthetic_entries),
            "skipped_candidates": sum(1 for row in audit_rows if row["status"] != "converted"),
            "bypass_reasons": dict(Counter(deny["deny_reason"] for deny in denies)),
            "bypass_breach_kinds": dict(Counter(deny["breach_kind"] for deny in denies)),
        }
        write_csv(
            scenario_root / "candidate_audit.csv",
            [
                "scenario_id",
                "rid",
                "symbol",
                "side",
                "breach_kind",
                "deny_reason",
                "regime_at_signal",
                "regime_confidence_at_signal",
                "resolved_min_regime_confidence",
                "resolved_max_regime_confidence",
                "signal_ts_ms",
                "signal_time_iso",
                "proxy_entry_ts_ms",
                "proxy_entry_time_iso",
                "proxy_entry_price",
                "leverage",
                "status",
                "detail",
                "audit_source_line",
            ],
            audit_rows,
        )
        (scenario_root / "candidate_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _write_microstructure_artifacts(scenario_root, combined_entries, runtime)
    return combined_entries
