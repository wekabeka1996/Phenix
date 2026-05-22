from __future__ import annotations

from bisect import bisect_right
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from tools.analysis.order_reconstruction_tp_sl_common import (
    iso_utc,
    load_yaml_file,
    payload_get,
    stringify,
    to_float,
    to_int,
    try_parse_timestamp_ms,
    write_csv,
)

from .config_loader import _resolve_aurora_root
from .exit_policies import compute_tpsl_geometry, materialize_trade_result
from .models import CanonicalEntry, ExitEvent, ScenarioRuntime

QUADRATIC_REGIME_SCENARIO_ID = "quadratic_regime_trend_down_sell_actual_forensics"


@dataclass(frozen=True)
class VariantSpec:
    id: str
    family: str
    description: str
    evaluator: Callable[[dict[str, Any]], tuple[bool, str]]


def _normalize_side(raw_side: Any) -> str:
    side = (stringify(raw_side) or "").upper()
    if side in {"BUY", "LONG"}:
        return "BUY"
    if side in {"SELL", "SHORT"}:
        return "SELL"
    return side


def _actual_close_reason(entry: CanonicalEntry) -> str:
    status = (entry.actual_outcome_status or "").strip().upper()
    if status == "TP":
        return "actual_close_tp"
    if status == "SL":
        return "actual_close_sl"
    if status:
        return f"actual_close_{status.lower()}"
    return "actual_close_unresolved"


def actual_close_only_exit(
    entry: CanonicalEntry,
    runtime: ScenarioRuntime,
) -> tuple[ExitEvent, dict[str, Any]]:
    geometry = compute_tpsl_geometry(entry, runtime)
    extras = {
        "tp_price": geometry.get("tp_price", ""),
        "sl_price": geometry.get("sl_price", ""),
        "tpsl_context": geometry.get("context") if isinstance(geometry, dict) else {},
    }
    if entry.actual_close_ts_ms is None or entry.actual_close_price is None:
        return (
            ExitEvent(
                reason=_actual_close_reason(entry),
                ts_ms=None,
                price=None,
                source="order_log_actual_close",
                support_quality="runtime_open_or_missing_close_truth",
            ),
            extras,
        )
    return (
        ExitEvent(
            reason=_actual_close_reason(entry),
            ts_ms=int(entry.actual_close_ts_ms),
            price=float(entry.actual_close_price),
            source="order_log_actual_close",
            support_quality="runtime_close_truth",
        ),
        extras,
    )


def _load_shadow_index(
    runtime_root: Path,
    strategy_id: str,
    target_rids: set[str],
) -> dict[str, dict[str, Any]]:
    path = runtime_root / "shadow_critical_event_journal_v1.jsonl"
    if not path.exists() or not target_rids:
        return {}
    index: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = None
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            rid = stringify(payload.get("rid")) or ""
            if rid not in target_rids:
                continue
            fragment = payload.get("payload_fragment") or {}
            event_strategy_id = stringify(payload.get("strategy_id")) or stringify(fragment.get("strategy_id")) or ""
            if event_strategy_id and event_strategy_id != strategy_id:
                continue
            slot = index.setdefault(rid, {})
            event_name = stringify(payload.get("event_name")) or ""
            if event_name == "EVT:QUADRATIC_DECISION_TRACE":
                slot["quadratic_trace"] = fragment
                slot["quadratic_trace_line"] = line_no
            elif event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
                slot["strategy_signal"] = fragment
                slot["strategy_signal_line"] = line_no
            elif event_name == "EVT:DECISION_TRACE_EMITTED":
                slot["decision_trace"] = fragment
                slot["decision_trace_line"] = line_no
    return index


def _load_confidence_audit_index(
    runtime_root: Path,
    strategy_id: str,
    target_rids: set[str],
) -> dict[str, dict[str, Any]]:
    path = runtime_root / "regime_confidence_audit_v1.jsonl"
    if not path.exists() or not target_rids:
        return {}
    index: dict[str, dict[str, Any]] = {}
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
            if rid not in target_rids:
                continue
            if stringify(payload.get("record_type")) not in {"decision", ""}:
                continue
            if stringify(payload.get("strategy_id")) != strategy_id:
                continue
            payload["_source_line"] = line_no
            index[rid] = payload
    return index


def _load_decision_config(workspace_root: Path) -> dict[str, Any]:
    aurora_cfg = load_yaml_file(workspace_root / "config" / "aurora" / "strategies" / "aurora.yaml") or {}
    aurora_root = _resolve_aurora_root(aurora_cfg)
    decision_cfg = aurora_root.get("decision") or {}
    gates_cfg = decision_cfg.get("gates") or {}
    scoring_engine_cfg = decision_cfg.get("scoring_engine") or {}
    danger_zone_cfg = scoring_engine_cfg.get("danger_zone_shield") or {}
    return {
        "signal_threshold": to_float(decision_cfg.get("signal_threshold")),
        "decision_geometry": decision_cfg.get("decision_geometry") or {},
        "gates": {
            "enabled": bool(gates_cfg.get("enabled", False)),
            "anti_flat_sigma": to_float(gates_cfg.get("anti_flat_sigma")),
            "anti_fomo_sigma": to_float(gates_cfg.get("anti_fomo_sigma")),
            "motion_window_sec": to_int(gates_cfg.get("motion_window_sec")),
        },
        "danger_zone_shield": {
            "enabled": bool(danger_zone_cfg.get("enabled", False)),
            "motion_threshold": to_float(danger_zone_cfg.get("motion_threshold")),
            "vol_threshold": to_float(danger_zone_cfg.get("vol_threshold")),
            "spread_threshold": to_float(danger_zone_cfg.get("spread_threshold")),
        },
    }


def _load_recorder_series(
    workspace_root: Path,
    cache: dict[tuple[str, int], list[dict[str, Any]]],
    symbol: str,
    tf_sec: int,
) -> list[dict[str, Any]]:
    key = (symbol, tf_sec)
    if key in cache:
        return cache[key]
    root = workspace_root / "data" / "recorder"
    rows_by_ts: dict[int, dict[str, Any]] = {}
    if root.exists():
        for path in sorted(root.rglob(f"{symbol}_{tf_sec}.csv")):
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                reader = csv.DictReader(handle)
                for raw in reader:
                    ts_ms = to_int(raw.get("timestamp"))
                    if ts_ms is None:
                        continue
                    row = dict(raw)
                    row["_source_path"] = str(path)
                    rows_by_ts[ts_ms] = row
    rows = [rows_by_ts[ts] for ts in sorted(rows_by_ts)]
    cache[key] = rows
    return rows


def _series_index_at_or_before(rows: list[dict[str, Any]], ts_ms: int) -> int | None:
    if not rows:
        return None
    timestamps = [to_int(row.get("timestamp")) or 0 for row in rows]
    idx = bisect_right(timestamps, ts_ms) - 1
    if idx < 0:
        return None
    return idx


def _side_move_pct(side: str, start_price: float, end_price: float) -> float:
    if not start_price:
        return 0.0
    if side == "BUY":
        return (end_price - start_price) / start_price * 100.0
    return (start_price - end_price) / start_price * 100.0


def _path_metric(
    rows: list[dict[str, Any]],
    idx: int | None,
    side: str,
    *,
    lookback_bars: int = 0,
    lookahead_bars: int = 0,
) -> float | None:
    if idx is None:
        return None
    if lookback_bars:
        start_idx = idx - lookback_bars
        if start_idx < 0:
            return None
        start_price = to_float(rows[start_idx].get("close"))
        end_price = to_float(rows[idx].get("close"))
        if start_price is None or end_price is None:
            return None
        return round(_side_move_pct(side, float(start_price), float(end_price)), 8)
    if lookahead_bars:
        end_idx = idx + lookahead_bars
        if end_idx >= len(rows):
            return None
        start_price = to_float(rows[idx].get("close"))
        end_price = to_float(rows[end_idx].get("close"))
        if start_price is None or end_price is None:
            return None
        return round(_side_move_pct(side, float(start_price), float(end_price)), 8)
    return None


def _signal_ts_ms(entry: CanonicalEntry) -> int:
    for path in ("timestamp", "ts_ms", "event_ts_ms"):
        value = try_parse_timestamp_ms(payload_get(entry.raw_surface, path))
        if value is not None:
            return value
    return entry.entry_ts_ms


def _bool_text(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _float_or_blank(value: Any) -> float | str:
    numeric = to_float(value)
    return round(float(numeric), 8) if numeric is not None else ""


def _extract_feature_snapshot(
    rows: list[dict[str, Any]],
    idx: int | None,
    prefix: str,
) -> dict[str, Any]:
    if idx is None:
        return {
            f"{prefix}_row_ts_ms": "",
            f"{prefix}_row_time_iso": "",
        }
    row = rows[idx]
    snapshot = {
        f"{prefix}_row_ts_ms": to_int(row.get("timestamp")) or "",
        f"{prefix}_row_time_iso": stringify(row.get("datetime")) or "",
    }
    for field in (
        "regime",
        "regime_conf",
        "regime_source_model",
        "regime_join_status",
        "regime_join_mode",
        "pm_norm",
        "pm_raw",
        "feat_delta_price",
        "feat_ema_bias",
        "feat_tfi",
        "feat_obi",
        "feat_macro_resid",
        "feat_macro_sync",
        "feat_volume_spike",
        "feat_volatility_state",
        "feat_depth_imbalance",
        "feat_absorption",
        "feat_liquidity_kappa",
        "feat_spread_bps",
        "feat_volume_zscore",
        "feat_large_trade_imbalance",
        "feat_pillar_operator",
        "feat_pillar_strategist",
        "feat_pillar_sum",
        "feat_pillar_tactician",
        "open",
        "high",
        "low",
        "close",
    ):
        snapshot[f"{prefix}_{field}"] = row.get(field, "")
    return snapshot


def _variant_specs() -> list[VariantSpec]:
    return [
        VariantSpec(
            id="baseline_current_runtime",
            family="baseline",
            description="Mirror the current runtime: no extra forensic blocking.",
            evaluator=lambda case: (True, "current_runtime_allow"),
        ),
        VariantSpec(
            id="confidence_floor_0_25",
            family="confidence",
            description="Block if regime confidence for TREND_DOWN/SELL is below 0.25.",
            evaluator=lambda case: (
                (case["regime_confidence_at_entry"] or 0.0) >= 0.25,
                (
                    "confidence>=0.25"
                    if (case["regime_confidence_at_entry"] or 0.0) >= 0.25
                    else "confidence_below_0.25"
                ),
            ),
        ),
        VariantSpec(
            id="confidence_floor_0_35",
            family="confidence",
            description="Block if regime confidence for TREND_DOWN/SELL is below 0.35.",
            evaluator=lambda case: (
                (case["regime_confidence_at_entry"] or 0.0) >= 0.35,
                (
                    "confidence>=0.35"
                    if (case["regime_confidence_at_entry"] or 0.0) >= 0.35
                    else "confidence_below_0.35"
                ),
            ),
        ),
        VariantSpec(
            id="raw_regime_alignment_required",
            family="quadratic",
            description="Block if emitted TREND_DOWN was only hysteresis-carried while raw regime already drifted elsewhere.",
            evaluator=lambda case: (
                not bool(case["raw_regime_mismatch"]),
                "raw_regime_aligned" if not bool(case["raw_regime_mismatch"]) else "raw_regime_mismatch",
            ),
        ),
        VariantSpec(
            id="score_margin_abs_ge_0_002",
            family="quadratic",
            description="Require absolute quadratic score margin of at least 0.002 over the active threshold.",
            evaluator=lambda case: (
                (case["score_margin_abs"] or 0.0) >= 0.002,
                "score_margin>=0.002" if (case["score_margin_abs"] or 0.0) >= 0.002 else "score_margin_lt_0.002",
            ),
        ),
        VariantSpec(
            id="abs_motion_sigma_lt_3_0",
            family="quadratic",
            description="Block if the retained 300s motion sigma magnitude is at or above 3.0.",
            evaluator=lambda case: (
                (case["motion_abs_sigma"] is not None and case["motion_abs_sigma"] < 3.0),
                (
                    "abs_motion_sigma_lt_3"
                    if case["motion_abs_sigma"] is not None and case["motion_abs_sigma"] < 3.0
                    else "abs_motion_sigma_ge_3_or_missing"
                ),
            ),
        ),
        VariantSpec(
            id="combined_safe_short_v2",
            family="combined",
            description="Require confidence>=0.35, raw-regime alignment, score margin>=0.002, and abs motion sigma<3.0.",
            evaluator=lambda case: _combined_rule(case, min_conf=0.35, min_margin=0.002, max_abs_motion=3.0),
        ),
        VariantSpec(
            id="combined_safe_short_v3_zero_entry",
            family="combined",
            description="Maximum-defensive slice: confidence>=0.35, raw-regime alignment, score margin>=0.006, abs motion sigma<3.0.",
            evaluator=lambda case: _combined_rule(case, min_conf=0.35, min_margin=0.006, max_abs_motion=3.0),
        ),
    ]


def _combined_rule(
    case: dict[str, Any],
    *,
    min_conf: float,
    min_margin: float,
    max_abs_motion: float,
) -> tuple[bool, str]:
    reasons: list[str] = []
    confidence = case["regime_confidence_at_entry"] or 0.0
    if confidence < min_conf:
        reasons.append(f"confidence_lt_{min_conf}")
    if bool(case["raw_regime_mismatch"]):
        reasons.append("raw_regime_mismatch")
    margin = case["score_margin_abs"]
    if margin is None or margin < min_margin:
        reasons.append(f"score_margin_lt_{min_margin}")
    motion_abs = case["motion_abs_sigma"]
    if motion_abs is None or motion_abs >= max_abs_motion:
        reasons.append(f"abs_motion_sigma_ge_{max_abs_motion}")
    if reasons:
        return False, "|".join(reasons)
    return True, "combined_rule_pass"


def _entry_bucket(case: dict[str, Any]) -> str:
    actual_reason = stringify(case.get("actual_exit_reason")) or ""
    actual_status = stringify(case.get("actual_trade_status")) or ""
    if actual_status == "loss" and actual_reason == "actual_close_sl":
        return "loss_sl"
    if actual_status == "loss" and actual_reason == "actual_close_tp":
        return "loss_tp_tag"
    if actual_status == "win":
        return "win"
    if actual_status == "unresolved":
        return "unresolved"
    return actual_status or "unknown"


def _variant_rows(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matrix_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for variant in _variant_specs():
        allowed_cases: list[dict[str, Any]] = []
        blocked_cases: list[dict[str, Any]] = []
        for case in cases:
            allowed, rule_reason = variant.evaluator(case)
            row = {
                "variant_id": variant.id,
                "variant_family": variant.family,
                "variant_description": variant.description,
                "entry_id": case["entry_id"],
                "symbol": case["symbol"],
                "side": case["side"],
                "allowed": _bool_text(allowed),
                "rule_reason": rule_reason,
                "actual_trade_status": case["actual_trade_status"],
                "actual_exit_reason": case["actual_exit_reason"],
                "actual_net_pnl_roi_pct": case["actual_net_pnl_roi_pct"] if case["actual_net_pnl_roi_pct"] != "" else "",
                "regime_confidence_at_entry": case["regime_confidence_at_entry"],
                "score_margin_abs": case["score_margin_abs"] if case["score_margin_abs"] is not None else "",
                "motion_abs_sigma": case["motion_abs_sigma"] if case["motion_abs_sigma"] is not None else "",
                "raw_regime_mismatch": _bool_text(case["raw_regime_mismatch"]),
                "signal_to_fill_sec": case["signal_to_fill_sec"] if case["signal_to_fill_sec"] is not None else "",
            }
            matrix_rows.append(row)
            (allowed_cases if allowed else blocked_cases).append(case)

        allowed_net_values = [
            float(case["actual_net_pnl_roi_pct"])
            for case in allowed_cases
            if case["actual_net_pnl_roi_pct"] != ""
        ]
        summary_rows.append(
            {
                "variant_id": variant.id,
                "variant_family": variant.family,
                "variant_description": variant.description,
                "sample_size": len(cases),
                "allowed_entries": len(allowed_cases),
                "blocked_entries": len(blocked_cases),
                "allowed_loss_entries": sum(1 for case in allowed_cases if case["actual_trade_status"] == "loss"),
                "blocked_loss_entries": sum(1 for case in blocked_cases if case["actual_trade_status"] == "loss"),
                "allowed_unresolved_entries": sum(1 for case in allowed_cases if case["actual_trade_status"] == "unresolved"),
                "blocked_unresolved_entries": sum(1 for case in blocked_cases if case["actual_trade_status"] == "unresolved"),
                "blocked_loss_sl_entries": sum(1 for case in blocked_cases if _entry_bucket(case) == "loss_sl"),
                "blocked_loss_tp_tag_entries": sum(1 for case in blocked_cases if _entry_bucket(case) == "loss_tp_tag"),
                "total_net_roi_allowed": round(sum(allowed_net_values), 8) if allowed_net_values else 0.0,
                "avg_net_roi_allowed": round(mean(allowed_net_values), 8) if allowed_net_values else 0.0,
            }
        )
    return matrix_rows, summary_rows


def _confidence_sweep_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in (0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5):
        allowed_cases = [case for case in cases if (case["regime_confidence_at_entry"] or 0.0) >= threshold]
        blocked_cases = [case for case in cases if case not in allowed_cases]
        allowed_net_values = [
            float(case["actual_net_pnl_roi_pct"])
            for case in allowed_cases
            if case["actual_net_pnl_roi_pct"] != ""
        ]
        rows.append(
            {
                "threshold": threshold,
                "sample_size": len(cases),
                "allowed_entries": len(allowed_cases),
                "blocked_entries": len(blocked_cases),
                "blocked_loss_entries": sum(1 for case in blocked_cases if case["actual_trade_status"] == "loss"),
                "blocked_loss_sl_entries": sum(1 for case in blocked_cases if _entry_bucket(case) == "loss_sl"),
                "blocked_loss_tp_tag_entries": sum(1 for case in blocked_cases if _entry_bucket(case) == "loss_tp_tag"),
                "blocked_unresolved_entries": sum(1 for case in blocked_cases if case["actual_trade_status"] == "unresolved"),
                "total_net_roi_allowed": round(sum(allowed_net_values), 8) if allowed_net_values else 0.0,
                "avg_net_roi_allowed": round(mean(allowed_net_values), 8) if allowed_net_values else 0.0,
            }
        )
    return rows


def _build_case(
    entry: CanonicalEntry,
    runtime: ScenarioRuntime,
    shadow_index: dict[str, dict[str, Any]],
    confidence_index: dict[str, dict[str, Any]],
    decision_cfg: dict[str, Any],
    recorder_cache: dict[tuple[str, int], list[dict[str, Any]]],
) -> dict[str, Any]:
    signal_ts_ms = _signal_ts_ms(entry)
    signal_time_iso = iso_utc(signal_ts_ms) or ""
    detector_event = payload_get(entry.raw_surface, "regime_provenance.detector_event") or {}
    shadow = shadow_index.get(entry.rid) or {}
    quadratic_trace = shadow.get("quadratic_trace") or {}
    anti_peak = quadratic_trace.get("anti_peak_observability") or {}
    score_path = anti_peak.get("score_path") or {}
    motion = anti_peak.get("motion") or {}
    context_shield = anti_peak.get("context_shield") or {}
    danger_zone_shield = anti_peak.get("danger_zone_shield") or {}
    confidence_audit = confidence_index.get(entry.rid) or {}

    recorder_300_rows = _load_recorder_series(runtime.workspace_root, recorder_cache, entry.symbol, 300)
    recorder_900_rows = _load_recorder_series(runtime.workspace_root, recorder_cache, entry.symbol, 900)
    idx_300 = _series_index_at_or_before(recorder_300_rows, signal_ts_ms)
    idx_900 = _series_index_at_or_before(recorder_900_rows, signal_ts_ms)

    signal_close_price = None
    if idx_300 is not None:
        signal_close_price = to_float(recorder_300_rows[idx_300].get("close"))

    exit_event, exit_extras = actual_close_only_exit(entry, runtime)
    actual_trade_row = materialize_trade_result(
        QUADRATIC_REGIME_SCENARIO_ID,
        entry,
        runtime,
        exit_event,
        exit_extras,
    )

    score_before = to_float(score_path.get("score_before_shields"))
    final_score = to_float(score_path.get("final_score"))
    signal_threshold = to_float(score_path.get("signal_threshold"))
    score_margin_abs = None
    if final_score is not None and signal_threshold is not None:
        score_margin_abs = round(abs(final_score) - abs(signal_threshold), 8)
    motion_sigma = to_float(motion.get("motion_norm_sigma"))
    motion_abs_sigma = abs(float(motion_sigma)) if motion_sigma is not None else None
    danger_zone_motion_threshold = to_float(payload_get(anti_peak, "danger_zone_shield.thresholds.motion_threshold"))
    if danger_zone_motion_threshold is None:
        danger_zone_motion_threshold = to_float(decision_cfg.get("danger_zone_shield", {}).get("motion_threshold"))

    signal_to_fill_sec = None
    if signal_ts_ms and entry.entry_ts_ms:
        signal_to_fill_sec = round((entry.entry_ts_ms - signal_ts_ms) / 1000.0, 3)

    case = {
        "entry_id": entry.entry_id,
        "rid": entry.rid,
        "symbol": entry.symbol,
        "side": entry.side,
        "entry_time_iso": entry.entry_time_iso,
        "entry_ts_ms": entry.entry_ts_ms,
        "entry_price": entry.entry_price,
        "signal_ts_ms": signal_ts_ms,
        "signal_time_iso": signal_time_iso,
        "signal_to_fill_sec": signal_to_fill_sec,
        "actual_outcome_status": entry.actual_outcome_status,
        "actual_exit_reason": actual_trade_row["exit_reason"],
        "actual_trade_status": actual_trade_row["status"],
        "actual_net_pnl_roi_pct": actual_trade_row["net_pnl_roi_pct"],
        "actual_gross_pnl_roi_pct": actual_trade_row["gross_pnl_roi_pct"],
        "actual_exit_ts_ms": actual_trade_row["exit_ts_ms"],
        "actual_exit_time_iso": actual_trade_row["exit_time_iso"],
        "actual_exit_price": actual_trade_row["exit_price"],
        "regime_at_entry": entry.regime_at_entry,
        "regime_confidence_at_entry": entry.regime_confidence_at_entry,
        "resolved_min_regime_confidence": entry.resolved_min_regime_confidence,
        "resolved_min_regime_confidence_source": entry.resolved_min_regime_confidence_source,
        "resolved_max_regime_confidence": entry.resolved_max_regime_confidence,
        "resolved_max_regime_confidence_source": entry.resolved_max_regime_confidence_source,
        "confidence_threshold_reason": stringify(confidence_audit.get("threshold_reason")) or "",
        "confidence_gate_verdict": stringify(confidence_audit.get("regime_confidence_gate_verdict")) or "",
        "detector_source_model": stringify(detector_event.get("source_model")) or "",
        "detector_pre_cutoff_source_model": stringify(detector_event.get("pre_cutoff_source_model")) or "",
        "detector_pre_cutoff_regime": stringify(detector_event.get("pre_cutoff_regime")) or "",
        "detector_pre_cutoff_confidence": _float_or_blank(detector_event.get("pre_cutoff_confidence")),
        "detector_raw_regime": stringify(detector_event.get("raw_regime")) or "",
        "detector_raw_confidence": _float_or_blank(detector_event.get("raw_confidence")),
        "detector_carried_previous_stable": bool(detector_event.get("carried_previous_stable")),
        "detector_emitted_confidence_kind": stringify(detector_event.get("emitted_confidence_kind")) or "",
        "detector_hysteresis_confirm_count": to_int(detector_event.get("hysteresis_confirm_count")) or "",
        "detector_hysteresis_bars": to_int(detector_event.get("hysteresis_bars")) or "",
        "detector_reason_summary": stringify(detector_event.get("reason_summary")) or "",
        "raw_regime_mismatch": bool(detector_event.get("carried_previous_stable")) and (
            stringify(detector_event.get("raw_regime")) or ""
        ) not in {"", entry.regime_at_entry},
        "score_before_shields": score_before,
        "final_score": final_score,
        "signal_threshold": signal_threshold,
        "score_margin_abs": score_margin_abs,
        "motion_norm_sigma": motion_sigma,
        "motion_abs_sigma": round(motion_abs_sigma, 8) if motion_abs_sigma is not None else None,
        "anti_flat_triggered": motion.get("anti_flat_triggered"),
        "anti_fomo_triggered": motion.get("anti_fomo_triggered"),
        "motion_missing_reason": stringify(motion.get("missing_reason")) or "",
        "context_shield_missing_reason": stringify(context_shield.get("missing_reason")) or "",
        "danger_zone_missing_reason": stringify(danger_zone_shield.get("missing_reason")) or "",
        "danger_zone_motion_threshold": danger_zone_motion_threshold,
        "danger_zone_abs_motion_over_threshold": (
            motion_abs_sigma is not None and danger_zone_motion_threshold is not None and motion_abs_sigma >= danger_zone_motion_threshold
        ),
        "strategy_signal_why_chain": "|".join(shadow.get("strategy_signal", {}).get("why_chain") or []),
        "decision_trace_reject_reason": stringify(shadow.get("decision_trace", {}).get("reject_reason")) or "",
        "signal_close_price_300": round(float(signal_close_price), 8) if signal_close_price is not None else "",
        "entry_vs_signal_close_side_move_pct": (
            round(_side_move_pct(entry.side, float(signal_close_price), entry.entry_price), 8)
            if signal_close_price is not None
            else ""
        ),
        "pre_5m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookback_bars=1),
        "pre_10m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookback_bars=2),
        "pre_15m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookback_bars=3),
        "pre_30m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookback_bars=6),
        "post_5m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookahead_bars=1),
        "post_10m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookahead_bars=2),
        "post_15m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookahead_bars=3),
        "post_30m_side_move_pct": _path_metric(recorder_300_rows, idx_300, entry.side, lookahead_bars=6),
        "actual_trade_row": actual_trade_row,
    }
    case.update(_extract_feature_snapshot(recorder_300_rows, idx_300, "tf300"))
    case.update(_extract_feature_snapshot(recorder_900_rows, idx_900, "tf900"))
    return case


def _write_report(
    scenario_root: Path,
    cases: list[dict[str, Any]],
    decision_cfg: dict[str, Any],
    confidence_sweep_rows: list[dict[str, Any]],
    variant_summary_rows: list[dict[str, Any]],
) -> None:
    losses = [case for case in cases if case["actual_trade_status"] == "loss"]
    raw_regime_mismatches = [case for case in cases if case["raw_regime_mismatch"]]
    high_abs_motion = [
        case for case in cases
        if case["motion_abs_sigma"] is not None and case["motion_abs_sigma"] >= 3.0
    ]
    best_confidence_floor = next(
        (row for row in confidence_sweep_rows if row["threshold"] == 0.35),
        None,
    )
    combined_v2 = next(
        (row for row in variant_summary_rows if row["variant_id"] == "combined_safe_short_v2"),
        None,
    )
    combined_v3 = next(
        (row for row in variant_summary_rows if row["variant_id"] == "combined_safe_short_v3_zero_entry"),
        None,
    )
    target_ids = [case["entry_id"] for case in cases if case["symbol"] in {"BTCUSDT", "DOGEUSDT", "ETHUSDT"}]
    lines = [
        f"# Scenario Report: {QUADRATIC_REGIME_SCENARIO_ID}",
        "",
        "Verdict: CURRENT_RUNTIME_LATE_SHORT_AUDIT_COMPLETE",
        "",
        "## FACTS",
        f"- Target cohort: {len(cases)} actual `TREND_DOWN/SELL` entries reconstructed from `order_log_v1.jsonl`.",
        f"- Resolved net-loss entries in this cohort: {len(losses)}.",
        f"- Entries with raw-regime mismatch via hysteresis carry: {len(raw_regime_mismatches)}.",
        f"- Entries with retained absolute motion sigma >= 3.0: {len(high_abs_motion)}.",
        f"- Current global motion gates config: anti_flat_sigma={decision_cfg['gates'].get('anti_flat_sigma')} anti_fomo_sigma={decision_cfg['gates'].get('anti_fomo_sigma')} motion_window_sec={decision_cfg['gates'].get('motion_window_sec')}.",
        f"- Current danger-zone motion threshold config: {decision_cfg['danger_zone_shield'].get('motion_threshold')}.",
        f"- Confidence floor 0.35 sweep row: {json.dumps(best_confidence_floor, ensure_ascii=False) if best_confidence_floor else '{}'}",
        f"- Combined safe short v2 row: {json.dumps(combined_v2, ensure_ascii=False) if combined_v2 else '{}'}",
        f"- Combined safe short v3 row: {json.dumps(combined_v3, ensure_ascii=False) if combined_v3 else '{}'}",
        f"- Focus control cases included in artifacts: {', '.join(target_ids) if target_ids else 'none'}.",
        "",
        "## INFERENCES",
        "- BTCUSDT looked like a regime-label problem first: the emitted `TREND_DOWN` label was hysteresis-carried while the raw detector regime had already drifted to `MEAN_REVERSION`.",
        "- DOGEUSDT looked like a stretched late short first: the move was already materially favorable over the prior 10-15 minutes, the fill came materially later than the signal, and the quadratic score margin over threshold stayed thin.",
        "- ETHUSDT is not a clean 'good short' from a financial standpoint because the actual close still lost after fees, but its post-signal price path continued in the short direction and therefore it is a better control for entry-direction correctness than for close economics.",
        "- A pure confidence-only fix is insufficient: confidence 0.35 blocks the current BTC and DOGE short cases, but the retained quadratic stretch/mismatch evidence is stronger than confidence alone.",
        "- The most promising config-only candidate from this slice is a side-aware min-confidence raise for `TREND_DOWN/SELL`, but the most promising structural candidate is an absolute-motion late-entry guard because the retained traces show motion stretch beyond 3 sigma on the bad shorts.",
        "- No current evidence proves that these losing shorts should have been inverted into BUY entries. BTC shows rebound behavior after the signal, but DOGE still had mixed short-follow-through and ETH continued down; the safer conclusion is 'no short' rather than 'explicit long'.",
        "- `ta_features` / `ta_ensemble` are not proven to be part of the hot entry path in this slice. The verb exists in the registry, but this audit did not find retained TA events tied to these entries, and no direct `decision_making` consumer was evidenced in the inspected hot-path files.",
        "",
        "## ASSUMPTIONS",
        "- Recorder 300s/900s bars are treated as the authoritative retained bar-level microstructure surface for this audit.",
        "- Actual close economics are reconstructed from `actual_close_price`, configured leverage, and configured fee bps, not from a separate account-ledger PnL export.",
        "- The variant matrix is forensic and counterfactual; it does not prove that every blocked entry would remain blocked after all downstream runtime gates and execution timing are applied.",
        "",
        "## UNKNOWNS",
        "- This workspace slice has no `wal/` directory, so no WAL-level counterfactual join was available for the requested comparison.",
        "- The local slice does not retain authoritative `TA_FEATURES_CALCULATED` events for these `rid`s, so TA alignment cannot be proven close-source for the exact entry moments.",
        "- Full strict `1m` TP/SL replay for the 2026-05-19 slice is still data-gapped locally, so this report prioritizes actual-close truth plus recorder-bar microstructure over new 24h TP/SL replay claims.",
    ]
    (scenario_root / "QUADRATIC_REGIME_FORENSIC_REPORT.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _write_artifacts(
    scenario_root: Path,
    cases: list[dict[str, Any]],
    decision_cfg: dict[str, Any],
) -> None:
    scenario_root.mkdir(parents=True, exist_ok=True)
    case_headers = [
        "entry_id",
        "rid",
        "symbol",
        "side",
        "entry_time_iso",
        "entry_ts_ms",
        "signal_time_iso",
        "signal_ts_ms",
        "signal_to_fill_sec",
        "entry_price",
        "signal_close_price_300",
        "entry_vs_signal_close_side_move_pct",
        "actual_outcome_status",
        "actual_exit_reason",
        "actual_trade_status",
        "actual_net_pnl_roi_pct",
        "actual_gross_pnl_roi_pct",
        "actual_exit_time_iso",
        "actual_exit_price",
        "regime_at_entry",
        "regime_confidence_at_entry",
        "resolved_min_regime_confidence",
        "resolved_min_regime_confidence_source",
        "resolved_max_regime_confidence",
        "resolved_max_regime_confidence_source",
        "confidence_gate_verdict",
        "confidence_threshold_reason",
        "detector_source_model",
        "detector_pre_cutoff_source_model",
        "detector_pre_cutoff_regime",
        "detector_pre_cutoff_confidence",
        "detector_raw_regime",
        "detector_raw_confidence",
        "detector_carried_previous_stable",
        "detector_emitted_confidence_kind",
        "detector_hysteresis_confirm_count",
        "detector_hysteresis_bars",
        "detector_reason_summary",
        "raw_regime_mismatch",
        "score_before_shields",
        "final_score",
        "signal_threshold",
        "score_margin_abs",
        "motion_norm_sigma",
        "motion_abs_sigma",
        "anti_flat_triggered",
        "anti_fomo_triggered",
        "motion_missing_reason",
        "context_shield_missing_reason",
        "danger_zone_missing_reason",
        "danger_zone_motion_threshold",
        "danger_zone_abs_motion_over_threshold",
        "strategy_signal_why_chain",
        "decision_trace_reject_reason",
        "pre_5m_side_move_pct",
        "pre_10m_side_move_pct",
        "pre_15m_side_move_pct",
        "pre_30m_side_move_pct",
        "post_5m_side_move_pct",
        "post_10m_side_move_pct",
        "post_15m_side_move_pct",
        "post_30m_side_move_pct",
        "tf300_row_time_iso",
        "tf300_regime",
        "tf300_regime_conf",
        "tf300_regime_source_model",
        "tf300_regime_join_status",
        "tf300_feat_delta_price",
        "tf300_feat_ema_bias",
        "tf300_feat_tfi",
        "tf300_feat_obi",
        "tf300_feat_macro_resid",
        "tf300_feat_macro_sync",
        "tf300_feat_volume_spike",
        "tf300_feat_volatility_state",
        "tf300_feat_depth_imbalance",
        "tf300_feat_absorption",
        "tf300_feat_liquidity_kappa",
        "tf300_feat_spread_bps",
        "tf300_feat_large_trade_imbalance",
        "tf900_row_time_iso",
        "tf900_feat_delta_price",
        "tf900_feat_tfi",
        "tf900_feat_obi",
        "tf900_feat_macro_resid",
        "tf900_feat_macro_sync",
        "tf900_feat_volatility_state",
    ]
    write_csv(
        scenario_root / "target_entries.csv",
        case_headers,
        [{header: case.get(header, "") for header in case_headers} for case in cases],
    )

    compare_rows = [
        case for case in cases
        if case["symbol"] in {"BTCUSDT", "DOGEUSDT", "ETHUSDT"}
    ]
    write_csv(
        scenario_root / "feature_snapshot_compare.csv",
        case_headers,
        [{header: case.get(header, "") for header in case_headers} for case in compare_rows],
    )

    matrix_rows, summary_rows = _variant_rows(cases)
    write_csv(
        scenario_root / "quadratic_variant_matrix.csv",
        list(matrix_rows[0].keys()) if matrix_rows else [
            "variant_id",
            "variant_family",
            "variant_description",
            "entry_id",
            "symbol",
            "side",
            "allowed",
            "rule_reason",
            "actual_trade_status",
            "actual_exit_reason",
            "actual_net_pnl_roi_pct",
            "regime_confidence_at_entry",
            "score_margin_abs",
            "motion_abs_sigma",
            "raw_regime_mismatch",
            "signal_to_fill_sec",
        ],
        matrix_rows,
    )
    write_csv(
        scenario_root / "quadratic_variant_summary.csv",
        list(summary_rows[0].keys()) if summary_rows else [
            "variant_id",
            "variant_family",
            "variant_description",
            "sample_size",
            "allowed_entries",
            "blocked_entries",
            "allowed_loss_entries",
            "blocked_loss_entries",
            "allowed_unresolved_entries",
            "blocked_unresolved_entries",
            "blocked_loss_sl_entries",
            "blocked_loss_tp_tag_entries",
            "total_net_roi_allowed",
            "avg_net_roi_allowed",
        ],
        summary_rows,
    )

    confidence_sweep_rows = _confidence_sweep_rows(cases)
    write_csv(
        scenario_root / "confidence_floor_sweep.csv",
        list(confidence_sweep_rows[0].keys()) if confidence_sweep_rows else [
            "threshold",
            "sample_size",
            "allowed_entries",
            "blocked_entries",
            "blocked_loss_entries",
            "blocked_loss_sl_entries",
            "blocked_loss_tp_tag_entries",
            "blocked_unresolved_entries",
            "total_net_roi_allowed",
            "avg_net_roi_allowed",
        ],
        confidence_sweep_rows,
    )

    market_cases = []
    for case in cases:
        market_cases.append(
            {
                "entry_id": case["entry_id"],
                "symbol": case["symbol"],
                "signal_ts_ms": case["signal_ts_ms"],
                "entry_ts_ms": case["entry_ts_ms"],
                "signal_to_fill_sec": case["signal_to_fill_sec"],
                "detector": {
                    "source_model": case["detector_source_model"],
                    "pre_cutoff_regime": case["detector_pre_cutoff_regime"],
                    "raw_regime": case["detector_raw_regime"],
                    "carried_previous_stable": case["detector_carried_previous_stable"],
                    "emitted_confidence_kind": case["detector_emitted_confidence_kind"],
                    "reason_summary": case["detector_reason_summary"],
                },
                "quadratic": {
                    "score_before_shields": case["score_before_shields"],
                    "final_score": case["final_score"],
                    "signal_threshold": case["signal_threshold"],
                    "score_margin_abs": case["score_margin_abs"],
                    "motion_norm_sigma": case["motion_norm_sigma"],
                    "motion_abs_sigma": case["motion_abs_sigma"],
                    "anti_flat_triggered": case["anti_flat_triggered"],
                    "anti_fomo_triggered": case["anti_fomo_triggered"],
                    "danger_zone_motion_threshold": case["danger_zone_motion_threshold"],
                    "danger_zone_abs_motion_over_threshold": case["danger_zone_abs_motion_over_threshold"],
                },
                "confidence": {
                    "regime_confidence_at_entry": case["regime_confidence_at_entry"],
                    "resolved_min_regime_confidence": case["resolved_min_regime_confidence"],
                    "resolved_max_regime_confidence": case["resolved_max_regime_confidence"],
                    "threshold_reason": case["confidence_threshold_reason"],
                },
                "path": {
                    "pre_15m_side_move_pct": case["pre_15m_side_move_pct"],
                    "post_5m_side_move_pct": case["post_5m_side_move_pct"],
                    "post_15m_side_move_pct": case["post_15m_side_move_pct"],
                    "post_30m_side_move_pct": case["post_30m_side_move_pct"],
                    "entry_vs_signal_close_side_move_pct": case["entry_vs_signal_close_side_move_pct"],
                },
                "features_300": {
                    "delta_price": case["tf300_feat_delta_price"],
                    "ema_bias": case["tf300_feat_ema_bias"],
                    "tfi": case["tf300_feat_tfi"],
                    "obi": case["tf300_feat_obi"],
                    "macro_resid": case["tf300_feat_macro_resid"],
                    "macro_sync": case["tf300_feat_macro_sync"],
                    "volatility_state": case["tf300_feat_volatility_state"],
                    "depth_imbalance": case["tf300_feat_depth_imbalance"],
                    "spread_bps": case["tf300_feat_spread_bps"],
                },
                "actual": {
                    "exit_reason": case["actual_exit_reason"],
                    "trade_status": case["actual_trade_status"],
                    "net_pnl_roi_pct": case["actual_net_pnl_roi_pct"],
                },
            }
        )
    (scenario_root / "market_state_cases.json").write_text(
        json.dumps(market_cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_report(
        scenario_root,
        cases,
        decision_cfg,
        confidence_sweep_rows,
        summary_rows,
    )


def build_quadratic_regime_trend_down_sell_entry_set(
    entries: list[CanonicalEntry],
    runtime: ScenarioRuntime,
) -> list[CanonicalEntry]:
    target_entries = [
        entry
        for entry in entries
        if entry.entry_origin == "actual_order_log_fill"
        and entry.side == "SELL"
        and entry.regime_at_entry == "TREND_DOWN"
    ]
    scenario_root = runtime.report_root / QUADRATIC_REGIME_SCENARIO_ID
    scenario_root.mkdir(parents=True, exist_ok=True)
    strategy_id = stringify(runtime.config.get("strategy_id")) or "aurora"
    target_rids = {entry.rid for entry in target_entries if entry.rid}
    shadow_index = _load_shadow_index(runtime.runtime_root, strategy_id, target_rids)
    confidence_index = _load_confidence_audit_index(runtime.runtime_root, strategy_id, target_rids)
    decision_cfg = _load_decision_config(runtime.workspace_root)
    recorder_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
    cases = [
        _build_case(
            entry,
            runtime,
            shadow_index,
            confidence_index,
            decision_cfg,
            recorder_cache,
        )
        for entry in target_entries
    ]
    _write_artifacts(scenario_root, cases, decision_cfg)
    return target_entries
