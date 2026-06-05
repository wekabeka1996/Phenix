#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.alpha_search.judge.config_models import (  # noqa: E402
    ShadowSimulatorConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (  # noqa: E402
    ShadowEntryPlan,
)
from apps.reference.domains.alpha_search.judge.shadow_simulator import (  # noqa: E402
    ShadowPlanSimulator,
)
from apps.reference.domains.alpha_search.judge.simulation_models import (  # noqa: E402
    ShadowSimulationResult,
)


CONFIDENCE_BUCKETS = [round(step / 10.0, 1) for step in range(11)]
BUY_VERDICTS = {"OPEN_LONG"}
SELL_VERDICTS = {"OPEN_SHORT"}
CONTRIBUTION_RE = re.compile(
    r"^(?:\[(?P<kind>dir|str)\]\s+)?(?P<feature>[^:]+):.*?→\s+(?P<contribution>[-+]?\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True)
class FileContext:
    symbol: str
    utc_date: str
    verdict_path: Path | None
    envelope_path: Path | None


def utc_date_from_ts_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def iso_from_ts_ms(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def to_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bool_from_any(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def join_list(values: Sequence[Any]) -> str:
    return "|".join(str(value) for value in values if value not in (None, ""))


def confidence_bucket(confidence: float | None) -> str:
    if confidence is None or math.isnan(confidence):
        return "UNKNOWN"
    for start, end in zip(CONFIDENCE_BUCKETS, CONFIDENCE_BUCKETS[1:]):
        if confidence < end:
            return f"{start:.1f}-{end:.1f}"
    return "0.9-1.0"


def safe_pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100.0, 4) if denominator else 0.0


def safe_mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def safe_median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 6)


def safe_profit_factor(values: Sequence[float]) -> float | None:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    if gross_loss == 0:
        return None
    return round(gross_profit / gross_loss, 6)


def infer_file_context(plans_file: Path) -> FileContext:
    stem = plans_file.stem
    prefix = "shadow_entry_plan_"
    if not stem.startswith(prefix):
        raise ValueError(
            f"Unsupported shadow plan filename: {plans_file.name}")
    tail = stem[len(prefix):]
    symbol, utc_date = tail.rsplit("_", 1)
    judge_dir = plans_file.parent
    verdict_path = judge_dir / f"verdict_{symbol}_{utc_date}.jsonl"
    envelope_path = judge_dir / f"envelope_{symbol}_{utc_date}.jsonl"
    return FileContext(
        symbol=symbol,
        utc_date=utc_date,
        verdict_path=verdict_path if verdict_path.exists() else None,
        envelope_path=envelope_path if envelope_path.exists() else None,
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    return load_jsonl(path)


def build_single_index(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_key = row.get(key)
        if raw_key is None:
            continue
        index[str(raw_key)] = dict(row)
    return index


def parse_contribution_summary(reasoning: Sequence[str], direction_sign: int) -> dict[str, Any]:
    parsed: list[tuple[str, str, float]] = []
    for line in reasoning:
        match = CONTRIBUTION_RE.match(str(line).strip())
        if not match:
            continue
        kind = match.group("kind") or "flat"
        feature = match.group("feature").strip()
        contribution = float(match.group("contribution"))
        parsed.append((kind, feature, contribution))

    if not parsed:
        return {
            "feature_count": 0,
            "aligned_contrib_abs": None,
            "opposing_contrib_abs": None,
            "support_ratio": None,
            "top_support_feature": None,
            "top_support_contribution": None,
            "top_oppose_feature": None,
            "top_oppose_contribution": None,
        }

    aligned = [item for item in parsed if item[2] * direction_sign > 0]
    opposing = [item for item in parsed if item[2] * direction_sign < 0]
    aligned_abs = sum(abs(item[2]) for item in aligned)
    opposing_abs = sum(abs(item[2]) for item in opposing)
    total_abs = aligned_abs + opposing_abs
    top_support = max(aligned, key=lambda item: abs(item[2]), default=None)
    top_oppose = max(opposing, key=lambda item: abs(item[2]), default=None)
    return {
        "feature_count": len(parsed),
        "aligned_contrib_abs": round(aligned_abs, 6),
        "opposing_contrib_abs": round(opposing_abs, 6),
        "support_ratio": round(aligned_abs / total_abs, 6) if total_abs else None,
        "top_support_feature": top_support[1] if top_support else None,
        "top_support_contribution": round(top_support[2], 6) if top_support else None,
        "top_oppose_feature": top_oppose[1] if top_oppose else None,
        "top_oppose_contribution": round(top_oppose[2], 6) if top_oppose else None,
    }


def build_expert_context(envelope: Mapping[str, Any] | None, entry_side: str | None) -> dict[str, Any]:
    chamber = envelope.get("chamber_aggregate") if isinstance(
        envelope, Mapping) else None
    expert_outputs = {}
    if isinstance(chamber, Mapping):
        for row in chamber.get("expert_outputs", []) or []:
            expert_id = str(row.get("expert_id") or "")
            if expert_id:
                expert_outputs[expert_id] = row

    direction_sign = 1 if entry_side == "BUY" else -1
    feature_neutrals = expert_outputs.get("judge.feature_neutrals_v1") or {}
    signal_weights = expert_outputs.get("judge.signal_weights_v1") or {}
    fn_conf = to_float(feature_neutrals.get("confidence"))
    sw_conf = to_float(signal_weights.get("confidence"))
    fn_summary = parse_contribution_summary(
        feature_neutrals.get("reasoning", []) or [], direction_sign)
    sw_summary = parse_contribution_summary(
        signal_weights.get("reasoning", []) or [], direction_sign)

    expert_verdicts = [
        str(feature_neutrals.get("entry_verdict") or "") or None,
        str(signal_weights.get("entry_verdict") or "") or None,
    ]
    filtered_verdicts = [verdict for verdict in expert_verdicts if verdict]
    expert_agreement = None
    if filtered_verdicts:
        expert_agreement = len(set(filtered_verdicts)) == 1

    return {
        "expert_feature_neutrals_verdict": feature_neutrals.get("entry_verdict"),
        "expert_feature_neutrals_confidence": fn_conf,
        "expert_feature_neutrals_top_support_feature": fn_summary["top_support_feature"],
        "expert_feature_neutrals_top_support_contribution": fn_summary["top_support_contribution"],
        "expert_feature_neutrals_top_oppose_feature": fn_summary["top_oppose_feature"],
        "expert_feature_neutrals_top_oppose_contribution": fn_summary["top_oppose_contribution"],
        "expert_feature_neutrals_support_ratio": fn_summary["support_ratio"],
        "expert_signal_weights_verdict": signal_weights.get("entry_verdict"),
        "expert_signal_weights_confidence": sw_conf,
        "expert_signal_weights_top_support_feature": sw_summary["top_support_feature"],
        "expert_signal_weights_top_support_contribution": sw_summary["top_support_contribution"],
        "expert_signal_weights_top_oppose_feature": sw_summary["top_oppose_feature"],
        "expert_signal_weights_top_oppose_contribution": sw_summary["top_oppose_contribution"],
        "expert_signal_weights_support_ratio": sw_summary["support_ratio"],
        "expert_confidence_spread": round(abs(fn_conf - sw_conf), 6) if fn_conf is not None and sw_conf is not None else None,
        "expert_agreement": expert_agreement,
        "expert_verdicts": filtered_verdicts,
        "expert_outputs_present": len(filtered_verdicts),
        "chamber_consensus_direction": chamber.get("consensus_direction") if isinstance(chamber, Mapping) else None,
        "chamber_consensus_strength": to_float(chamber.get("consensus_strength")) if isinstance(chamber, Mapping) else None,
    }


def build_recorder_context(feature_row: Mapping[str, Any] | None) -> dict[str, Any]:
    if feature_row is None:
        return {
            "recorder_row_found": False,
            "recorder_match_mode": "missing",
            "data_quality_issue": "MISSING_RECORDER_ROW",
        }

    ready = bool_from_any(feature_row.get("ready"))
    gap_state = str(feature_row.get("gap_state") or "") or None
    regime_join_status = str(feature_row.get(
        "regime_join_status") or "") or None
    if not ready:
        quality_issue = "RECORDER_NOT_READY"
    elif gap_state and gap_state != "CLEAR":
        quality_issue = f"GAP_{gap_state}"
    elif regime_join_status and regime_join_status != "MATCHED":
        quality_issue = f"REGIME_JOIN_{regime_join_status}"
    else:
        quality_issue = "CLEAR"

    selected_fields = {
        "recorder_row_found": True,
        "recorder_match_mode": feature_row.get("_match_mode", "exact"),
        "recorder_source_mode": feature_row.get("source_mode"),
        "recorder_ready": ready,
        "recorder_gap_state": gap_state,
        "recorder_gap_policy_action": feature_row.get("gap_policy_action"),
        "recorder_regime_join_status": regime_join_status,
        "recorder_regime_join_mode": feature_row.get("regime_join_mode"),
        "recorder_regime_age_ms": to_int(feature_row.get("regime_age_ms")),
        "recorder_regime": feature_row.get("regime"),
        "recorder_regime_conf": to_float(feature_row.get("regime_conf")),
        "recorder_pm_norm_10s": to_float(feature_row.get("pm_norm_10s")),
        "recorder_pm_norm_60s": to_float(feature_row.get("pm_norm_60s")),
        "recorder_pm_norm_300s": to_float(feature_row.get("pm_norm_300s")),
        "recorder_feat_obi": to_float(feature_row.get("feat_obi")),
        "recorder_feat_tfi": to_float(feature_row.get("feat_tfi")),
        "recorder_feat_delta_price": to_float(feature_row.get("feat_delta_price")),
        "recorder_feat_absorption": to_float(feature_row.get("feat_absorption")),
        "recorder_feat_liquidity_kappa": to_float(feature_row.get("feat_liquidity_kappa")),
        "recorder_feat_ema_bias": to_float(feature_row.get("feat_ema_bias")),
        "recorder_feat_volume_spike": to_float(feature_row.get("feat_volume_spike")),
        "recorder_feat_volatility_state": to_float(feature_row.get("feat_volatility_state")),
        "recorder_feat_depth_imbalance": to_float(feature_row.get("feat_depth_imbalance")),
        "recorder_feat_macro_sync": to_float(feature_row.get("feat_macro_sync")),
        "recorder_feat_spread_bps": to_float(feature_row.get("feat_spread_bps")),
        "recorder_feat_large_trade_imbalance": to_float(feature_row.get("feat_large_trade_imbalance")),
        "recorder_feat_volume_zscore": to_float(feature_row.get("feat_volume_zscore")),
        "recorder_feat_macro_resid": to_float(feature_row.get("feat_macro_resid")),
        "recorder_feat_pillar_sum": to_float(feature_row.get("feat_pillar_sum")),
        "recorder_feat_pillar_tactician": to_float(feature_row.get("feat_pillar_tactician")),
        "recorder_feat_pillar_operator": to_float(feature_row.get("feat_pillar_operator")),
        "recorder_feat_pillar_strategist": to_float(feature_row.get("feat_pillar_strategist")),
        "data_quality_issue": quality_issue,
    }
    return selected_fields


def flatten_for_csv(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    headers = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: flatten_for_csv(row.get(key))
                            for key in headers})


def pick_feature_row(bars: Any, ts_ms: int) -> Mapping[str, Any] | None:
    if bars is None or getattr(bars, "empty", True):
        return None
    exact = bars[bars["timestamp"] == ts_ms]
    if not exact.empty:
        row = exact.iloc[0].to_dict()
        row["_match_mode"] = "exact"
        return row
    later = bars[bars["timestamp"] >= ts_ms]
    if not later.empty:
        row = later.iloc[0].to_dict()
        row["_match_mode"] = "next_available"
        return row
    return None


def build_base_row(plan: ShadowEntryPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "cycle_key": plan.cycle_key,
        "symbol": plan.symbol,
        "tf_sec": plan.tf_sec,
        "plan_ts_ms": plan.ts_ms,
        "plan_ts_utc": iso_from_ts_ms(plan.ts_ms),
        "confidence": plan.confidence,
        "confidence_tier": plan.confidence_tier,
        "confidence_bucket": confidence_bucket(plan.confidence),
        "tier_min_confidence": plan.tier_min_confidence,
        "final_entry_verdict": plan.final_entry_verdict,
        "entry_side": plan.entry_side,
        "actionable": plan.actionable,
        "suppressed": plan.suppressed,
        "suppression_reason": plan.suppression_reason,
        "plan_reason_codes": list(plan.plan_reason_codes),
        "plan_reason_codes_joined": join_list(plan.plan_reason_codes),
        "limit_price": plan.limit_price,
        "tp_price": plan.tp_price,
        "sl_price": plan.sl_price,
        "risk_reward": plan.risk_reward,
        "limit_offset_bps": plan.limit_offset_bps,
        "tp_offset_pct": plan.tp_offset_pct,
        "sl_offset_pct": plan.sl_offset_pct,
        "source_verdict_id": plan.source_verdict_id,
        "source_envelope_id": plan.source_envelope_id,
        "authority_mode": plan.authority_mode,
        "entry_order_type": plan.entry_order_type,
        "simulation_status": None,
        "terminal_reason": None,
        "exit_reason": None,
        "outcome_available": False,
        "filled_trade": False,
        "fill_ts_ms": None,
        "fill_ts_utc": None,
        "fill_delay_ms": None,
        "entry_fill_price": None,
        "exit_ts_ms": None,
        "exit_ts_utc": None,
        "exit_price": None,
        "duration_bars": None,
        "gross_pnl_pct": None,
        "net_pnl_pct": None,
        "fees_paid_pct": None,
        "trade_pnl_class": None,
        "proposal_outcome_class": None,
        "in_primary_cohort": False,
        "primary_is_win": False,
        "skipped_reason": None,
        "invalid_reason": None,
    }


def apply_verdict_context(row: dict[str, Any], verdict: Mapping[str, Any] | None) -> None:
    if verdict is None:
        row["verdict_found"] = False
        row["verdict_consistency"] = "MISSING_VERDICT"
        return
    row["verdict_found"] = True
    row["verdict_dissent_noted"] = bool_from_any(verdict.get("dissent_noted"))
    row["verdict_reasoning"] = join_list(verdict.get("reasoning", []) or [])
    row["verdict_confidence"] = to_float(verdict.get("confidence"))
    row["verdict_entry_verdict"] = verdict.get("entry_verdict")
    row["verdict_consistency"] = "MATCH"
    if verdict.get("entry_verdict") != row["final_entry_verdict"]:
        row["verdict_consistency"] = "ENTRY_VERDICT_MISMATCH"
    verdict_confidence = to_float(verdict.get("confidence"))
    row_confidence = to_float(row.get("confidence"))
    if (
        verdict_confidence is not None
        and row_confidence is not None
        and not math.isclose(verdict_confidence, row_confidence, rel_tol=0.0, abs_tol=1e-9)
    ):
        row["verdict_consistency"] = "CONFIDENCE_MISMATCH"


def apply_envelope_context(row: dict[str, Any], envelope: Mapping[str, Any] | None) -> None:
    if envelope is None:
        row["envelope_found"] = False
        row["freshness_deadline_ms"] = None
        row["freshness_slack_ms"] = None
        return
    row["envelope_found"] = True
    row["envelope_regime"] = envelope.get("regime")
    row["envelope_regime_confidence"] = to_float(
        envelope.get("regime_confidence"))
    row["envelope_regime_source"] = envelope.get("regime_source")
    row["features_ref"] = envelope.get("features_ref")
    row["freshness_deadline_ms"] = to_int(
        envelope.get("freshness_deadline_ms"))
    if row["freshness_deadline_ms"] is not None:
        row["freshness_slack_ms"] = row["freshness_deadline_ms"] - row["plan_ts_ms"]
    row.update(build_expert_context(envelope, row.get("entry_side")))


def apply_result_context(row: dict[str, Any], result: ShadowSimulationResult) -> None:
    row["terminal_reason"] = result.outcome
    row["exit_reason"] = result.outcome_reason
    row["fill_ts_ms"] = result.fill_ts_ms
    row["fill_ts_utc"] = iso_from_ts_ms(result.fill_ts_ms)
    row["fill_delay_ms"] = result.fill_ts_ms - \
        row["plan_ts_ms"] if result.fill_ts_ms is not None else None
    row["entry_fill_price"] = result.fill_price
    row["exit_ts_ms"] = result.exit_ts_ms
    row["exit_ts_utc"] = iso_from_ts_ms(result.exit_ts_ms)
    row["exit_price"] = result.exit_price
    row["duration_bars"] = result.duration_bars
    row["filled_trade"] = result.fill_ts_ms is not None

    if result.outcome == "AMBIGUOUS_INTRABAR":
        row["simulation_status"] = "invalid"
        row["invalid_reason"] = "ambiguous_intrabar_exit_unresolved"
        row["proposal_outcome_class"] = "AMBIGUOUS"
        return
    if result.outcome == "ERROR":
        row["simulation_status"] = "error"
        row["invalid_reason"] = result.outcome_reason or "simulator_error"
        row["proposal_outcome_class"] = "ERROR"
        return

    row["simulation_status"] = "success"
    row["outcome_available"] = True
    row["gross_pnl_pct"] = result.gross_pnl_pct
    row["net_pnl_pct"] = result.net_pnl_pct
    row["fees_paid_pct"] = result.fees_paid_pct

    if result.outcome == "NOT_FILLED_TIMEOUT":
        row["proposal_outcome_class"] = "NO_FILL"
        row["trade_pnl_class"] = "NO_FILL"
    elif result.outcome == "FILLED_TP":
        row["proposal_outcome_class"] = "WIN"
        row["trade_pnl_class"] = "WIN"
    elif result.outcome == "FILLED_SL":
        row["proposal_outcome_class"] = "LOSS"
        row["trade_pnl_class"] = "LOSS"
    elif result.outcome == "FILLED_TIMEOUT":
        if result.net_pnl_pct > 0:
            row["proposal_outcome_class"] = "TIMEOUT_WIN"
            row["trade_pnl_class"] = "WIN"
        elif result.net_pnl_pct < 0:
            row["proposal_outcome_class"] = "TIMEOUT_LOSS"
            row["trade_pnl_class"] = "LOSS"
        else:
            row["proposal_outcome_class"] = "TIMEOUT_FLAT"
            row["trade_pnl_class"] = "FLAT"
    else:
        row["proposal_outcome_class"] = result.outcome
        row["trade_pnl_class"] = "FLAT"


def summarize_financial(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    denominator = len(rows)
    filled = [row for row in rows if bool_from_any(row.get("filled_trade"))]
    wins = [row for row in rows if row.get("trade_pnl_class") == "WIN"]
    losses = [row for row in rows if row.get("trade_pnl_class") == "LOSS"]
    flats = [row for row in rows if row.get("trade_pnl_class") == "FLAT"]
    no_fill = [row for row in rows if row.get(
        "proposal_outcome_class") == "NO_FILL"]
    tp_hits = [row for row in rows if row.get(
        "terminal_reason") == "FILLED_TP"]
    sl_hits = [row for row in rows if row.get(
        "terminal_reason") == "FILLED_SL"]
    timeout_filled = [row for row in rows if row.get(
        "terminal_reason") == "FILLED_TIMEOUT"]
    positive_net = [to_float(row.get("net_pnl_pct")) or 0.0 for row in wins]
    negative_net = [to_float(row.get("net_pnl_pct")) or 0.0 for row in losses]
    proposal_net = [to_float(row.get("net_pnl_pct")) or 0.0 for row in rows]
    filled_net = [to_float(row.get("net_pnl_pct")) or 0.0 for row in filled]
    return {
        "rows": denominator,
        "filled_rows": len(filled),
        "win_rows": len(wins),
        "loss_rows": len(losses),
        "flat_rows": len(flats),
        "no_fill_rows": len(no_fill),
        "tp_hits": len(tp_hits),
        "sl_hits": len(sl_hits),
        "filled_timeout_rows": len(timeout_filled),
        "proposal_win_rate_pct": safe_pct(len(wins), denominator),
        "filled_trade_win_rate_pct": safe_pct(len(wins), len(filled)),
        "fill_rate_pct": safe_pct(len(filled), denominator),
        "tp_rate_on_proposals_pct": safe_pct(len(tp_hits), denominator),
        "tp_rate_on_filled_pct": safe_pct(len(tp_hits), len(filled)),
        "total_net_pnl_pct": round(sum(proposal_net), 6),
        "total_gross_positive_pct": round(sum(positive_net), 6),
        "total_gross_negative_pct": round(sum(negative_net), 6),
        "expectancy_net_pnl_pct": safe_mean(proposal_net),
        "expectancy_filled_net_pnl_pct": safe_mean(filled_net),
        "median_net_pnl_pct": safe_median(proposal_net),
        "median_filled_net_pnl_pct": safe_median(filled_net),
        "profit_factor": safe_profit_factor(proposal_net),
        "outcome_distribution": dict(sorted(Counter(str(row.get("proposal_outcome_class") or "UNKNOWN") for row in rows).items())),
        "terminal_reason_distribution": dict(sorted(Counter(str(row.get("terminal_reason") or "UNKNOWN") for row in rows).items())),
    }


def make_group_summary(rows: Sequence[Mapping[str, Any]], key_name: str) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(key_name)
        if isinstance(value, bool):
            label = str(value).lower()
        else:
            label = str(value or "UNKNOWN")
        groups[label].append(row)
    return {label: summarize_financial(group_rows) for label, group_rows in sorted(groups.items())}


def make_multivalue_group_summary(rows: Sequence[Mapping[str, Any]], key_name: str) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        values = row.get(key_name) or []
        if not values:
            groups["NONE"].append(row)
            continue
        for value in values:
            groups[str(value)].append(row)
    return {label: summarize_financial(group_rows) for label, group_rows in sorted(groups.items())}


def build_top_feature_counts(rows: Sequence[Mapping[str, Any]], field_name: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        feature = str(row.get(field_name) or "")
        if feature:
            counter[feature] += 1
    return [{"feature": feature, "count": count} for feature, count in counter.most_common(10)]


def build_context_stats(rows: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(field_name)
        if isinstance(value, bool):
            label = str(value).lower()
        else:
            label = str(value or "UNKNOWN")
        counter[label] += 1
    return dict(sorted(counter.items()))


def numeric_stats(rows: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, Any]:
    values = [to_float(row.get(field_name)) for row in rows]
    clean = [value for value in values if value is not None]
    return {
        "count": len(clean),
        "mean": safe_mean(clean),
        "median": safe_median(clean),
        "min": min(clean) if clean else None,
        "max": max(clean) if clean else None,
    }


def build_consistency_checks(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checks = {
        "missing_verdict_rows": sum(1 for row in rows if not bool_from_any(row.get("verdict_found"))),
        "missing_envelope_rows": sum(1 for row in rows if not bool_from_any(row.get("envelope_found"))),
        "verdict_mismatch_rows": sum(1 for row in rows if row.get("verdict_consistency") == "ENTRY_VERDICT_MISMATCH"),
        "confidence_mismatch_rows": sum(1 for row in rows if row.get("verdict_consistency") == "CONFIDENCE_MISMATCH"),
        "missing_recorder_rows": sum(1 for row in rows if not bool_from_any(row.get("recorder_row_found"))),
        "entry_side_inconsistency_rows": sum(
            1
            for row in rows
            if (row.get("entry_side") == "BUY" and row.get("final_entry_verdict") not in BUY_VERDICTS)
            or (row.get("entry_side") == "SELL" and row.get("final_entry_verdict") not in SELL_VERDICTS)
        ),
    }
    checks["all_consistent"] = all(value == 0 for value in checks.values())
    return checks


def build_cognitive_summary(all_rows: Sequence[Mapping[str, Any]], primary_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expert_agreement = build_context_stats(all_rows, "expert_agreement")
    dissent_counts = build_context_stats(all_rows, "verdict_dissent_noted")
    data_quality_counts = build_context_stats(all_rows, "data_quality_issue")
    regime_join_counts = build_context_stats(
        all_rows, "recorder_regime_join_status")
    gap_state_counts = build_context_stats(all_rows, "recorder_gap_state")
    ready_counts = build_context_stats(all_rows, "recorder_ready")
    return {
        "expert_agreement_counts": expert_agreement,
        "dissent_counts": dissent_counts,
        "data_quality_issue_counts": data_quality_counts,
        "regime_join_status_counts": regime_join_counts,
        "gap_state_counts": gap_state_counts,
        "recorder_ready_counts": ready_counts,
        "freshness_slack_ms": numeric_stats(all_rows, "freshness_slack_ms"),
        "regime_age_ms": numeric_stats(all_rows, "recorder_regime_age_ms"),
        "confidence_spread": numeric_stats(all_rows, "expert_confidence_spread"),
        "profitability_by_dissent": make_group_summary(primary_rows, "verdict_dissent_noted"),
        "profitability_by_expert_agreement": make_group_summary(primary_rows, "expert_agreement"),
        "profitability_by_data_quality_issue": make_group_summary(primary_rows, "data_quality_issue"),
        "feature_neutrals_top_support_features": build_top_feature_counts(all_rows, "expert_feature_neutrals_top_support_feature"),
        "feature_neutrals_top_oppose_features": build_top_feature_counts(all_rows, "expert_feature_neutrals_top_oppose_feature"),
        "signal_weights_top_support_features": build_top_feature_counts(all_rows, "expert_signal_weights_top_support_feature"),
        "signal_weights_top_oppose_features": build_top_feature_counts(all_rows, "expert_signal_weights_top_oppose_feature"),
    }


def build_report(summary: Mapping[str, Any], output_dir: Path) -> str:
    meta = summary["meta"]
    financial = summary["financial"]["primary"]
    groups = summary["groupings"]["primary"]
    cognitive = summary["cognitive"]
    lines = [
        "# Shadow Plan Analysis Report",
        "",
        "## Scope",
        f"- Source file: {meta['source_file']}",
        f"- Symbol/date: {meta['symbol']} / {meta['utc_date']}",
        f"- Replay model: coarse recorder replay via ShadowPlanSimulator on {meta['recorder_root']}",
        f"- Fees/slippage: {meta['simulator_config']['fees_bps']} bps + {meta['simulator_config']['slippage_bps']} bps",
        "- Primary denominator: actionable, unsuppressed plans with successful replay output.",
        "- Limits: authority/ledger latency is not claimed as causal unless directly joined for this cohort.",
        "",
        "## Core Metrics",
        f"- Primary rows: {financial['rows']}",
        f"- Filled rows: {financial['filled_rows']}",
        f"- Proposal win rate: {financial['proposal_win_rate_pct']}%",
        f"- Filled-trade win rate: {financial['filled_trade_win_rate_pct']}%",
        f"- Fill rate: {financial['fill_rate_pct']}%",
        f"- Total net pnl pct: {financial['total_net_pnl_pct']}",
        f"- Expectancy net pnl pct: {financial['expectancy_net_pnl_pct']}",
        f"- Profit factor: {financial['profit_factor']}",
        "",
        "## Outcome Distribution",
    ]
    for label, count in financial["outcome_distribution"].items():
        lines.append(f"- {label}: {count}")
    lines.extend([
        "",
        "## Confidence Tier Summary",
    ])
    for label, item in groups["by_confidence_tier"].items():
        lines.append(
            f"- {label}: rows={item['rows']}, proposal_win_rate={item['proposal_win_rate_pct']}%, fill_rate={item['fill_rate_pct']}%, total_net={item['total_net_pnl_pct']}"
        )
    lines.extend([
        "",
        "## BUY/SELL Summary",
    ])
    for label, item in groups["by_entry_side"].items():
        lines.append(
            f"- {label}: rows={item['rows']}, proposal_win_rate={item['proposal_win_rate_pct']}%, fill_rate={item['fill_rate_pct']}%, total_net={item['total_net_pnl_pct']}"
        )
    lines.extend([
        "",
        "## Cognitive Signals",
        f"- Dissent counts: {json.dumps(cognitive['dissent_counts'], ensure_ascii=True)}",
        f"- Expert agreement counts: {json.dumps(cognitive['expert_agreement_counts'], ensure_ascii=True)}",
        f"- Data quality issue counts: {json.dumps(cognitive['data_quality_issue_counts'], ensure_ascii=True)}",
        f"- Regime join status counts: {json.dumps(cognitive['regime_join_status_counts'], ensure_ascii=True)}",
        f"- Freshness slack ms stats: {json.dumps(cognitive['freshness_slack_ms'], ensure_ascii=True)}",
        f"- Confidence spread stats: {json.dumps(cognitive['confidence_spread'], ensure_ascii=True)}",
        "",
        "## Output Artifacts",
        f"- Summary JSON: {(output_dir / 'summary.json').as_posix()}",
        f"- Per-plan JSONL: {(output_dir / 'per_plan_rows.jsonl').as_posix()}",
        f"- Per-plan CSV: {(output_dir / 'per_plan_rows.csv').as_posix()}",
    ])
    return "\n".join(lines) + "\n"


def load_plans(plans_file: Path) -> tuple[list[ShadowEntryPlan], list[dict[str, Any]]]:
    valid: list[ShadowEntryPlan] = []
    invalid: list[dict[str, Any]] = []
    for line_no, raw in enumerate(plans_file.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            plan = ShadowEntryPlan.model_validate_json(raw)
            valid.append(plan)
        except Exception as exc:  # noqa: BLE001
            invalid.append(
                {
                    "plan_id": None,
                    "cycle_key": None,
                    "symbol": None,
                    "tf_sec": None,
                    "plan_ts_ms": None,
                    "plan_ts_utc": None,
                    "confidence": None,
                    "confidence_tier": None,
                    "confidence_bucket": None,
                    "entry_side": None,
                    "actionable": False,
                    "suppressed": False,
                    "simulation_status": "invalid",
                    "terminal_reason": "plan_parse_error",
                    "proposal_outcome_class": "INVALID",
                    "skipped_reason": None,
                    "invalid_reason": f"line_{line_no}:{exc}",
                    "plan_reason_codes": [],
                }
            )
    return valid, invalid


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    plans_file = args.shadow_plan_file.resolve()
    context = infer_file_context(plans_file)
    verdict_rows = load_rows(context.verdict_path)
    envelope_rows = load_rows(context.envelope_path)
    verdict_by_id = build_single_index(verdict_rows, "verdict_id")
    verdict_by_cycle = build_single_index(verdict_rows, "cycle_key")
    envelope_by_id = build_single_index(envelope_rows, "envelope_id")
    envelope_by_cycle = build_single_index(envelope_rows, "cycle_key")
    plans, invalid_rows = load_plans(plans_file)

    simulator_cfg = ShadowSimulatorConfig(
        enabled=True,
        max_bars_after_signal=args.max_bars_after_signal,
        intrabar_ambiguity_policy=args.intrabar_ambiguity_policy,
        fees_bps=args.fees_bps,
        slippage_bps=args.slippage_bps,
    )
    simulator = ShadowPlanSimulator(simulator_cfg)
    bars_cache: dict[tuple[str, str, int], Any] = {}

    def get_bars(plan: ShadowEntryPlan) -> Any:
        date_key = utc_date_from_ts_ms(plan.ts_ms)
        cache_key = (date_key, plan.symbol, plan.tf_sec)
        if cache_key not in bars_cache:
            bars_cache[cache_key] = simulator._load_bars(
                args.recorder_root, date_key, plan.symbol, plan.tf_sec)
        return bars_cache[cache_key]

    rows: list[dict[str, Any]] = []
    for plan in plans:
        row = build_base_row(plan)
        verdict = verdict_by_cycle.get(
            plan.cycle_key) or verdict_by_id.get(plan.source_verdict_id)
        envelope = envelope_by_cycle.get(
            plan.cycle_key) or envelope_by_id.get(plan.source_envelope_id)
        apply_verdict_context(row, verdict)
        apply_envelope_context(row, envelope)

        feature_row = pick_feature_row(get_bars(plan), plan.ts_ms)
        row.update(build_recorder_context(feature_row))

        if plan.suppressed:
            row["simulation_status"] = "skipped"
            row["skipped_reason"] = "suppressed_plan"
            row["terminal_reason"] = "suppressed_plan"
            row["proposal_outcome_class"] = "SUPPRESSED"
            rows.append(row)
            continue

        if not plan.actionable:
            row["simulation_status"] = "skipped"
            row["skipped_reason"] = "non_actionable_plan"
            row["terminal_reason"] = "non_actionable_plan"
            row["proposal_outcome_class"] = "NON_ACTIONABLE"
            rows.append(row)
            continue

        if plan.entry_side not in {"BUY", "SELL"} or plan.limit_price is None or plan.tp_price is None or plan.sl_price is None:
            row["simulation_status"] = "invalid"
            row["invalid_reason"] = "incomplete_plan_geometry"
            row["terminal_reason"] = "incomplete_plan_geometry"
            row["proposal_outcome_class"] = "INVALID"
            rows.append(row)
            continue

        bars = get_bars(plan)
        if getattr(bars, "empty", True):
            row["simulation_status"] = "skipped"
            row["skipped_reason"] = "missing_ohlc_file"
            row["terminal_reason"] = "missing_ohlc_file"
            row["proposal_outcome_class"] = "MISSING_OHLC"
            rows.append(row)
            continue

        result = simulator.simulate_plan(plan, bars)
        apply_result_context(row, result)
        row["in_primary_cohort"] = row["simulation_status"] == "success"
        row["primary_is_win"] = bool(
            row["in_primary_cohort"] and row.get("trade_pnl_class") == "WIN")
        rows.append(row)

    rows.extend(invalid_rows)

    primary_rows = [row for row in rows if bool_from_any(
        row.get("in_primary_cohort"))]
    summary = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_file": plans_file.as_posix(),
            "output_dir": args.output_dir.as_posix(),
            "symbol": context.symbol,
            "utc_date": context.utc_date,
            "judge_log_dir": args.judge_log_dir.as_posix(),
            "recorder_root": args.recorder_root.as_posix(),
            "simulator_config": {
                "max_bars_after_signal": simulator_cfg.max_bars_after_signal,
                "intrabar_ambiguity_policy": simulator_cfg.intrabar_ambiguity_policy,
                "fees_bps": simulator_cfg.fees_bps,
                "slippage_bps": simulator_cfg.slippage_bps,
            },
            "limits": [
                "Coarse replay uses recorder bars at native tf_sec rather than strict 1m candles.",
                "USD ROI is not derived because no explicit notional/economics block is injected here.",
                "Authority and decision-ledger latency is context-only unless directly joined for this cohort.",
            ],
        },
        "counts": {
            "total_rows": len(rows),
            "valid_plan_rows": len(plans),
            "invalid_plan_rows": len(invalid_rows),
            "primary_rows": len(primary_rows),
            "skipped_rows": sum(1 for row in rows if row.get("simulation_status") == "skipped"),
            "invalid_rows": sum(1 for row in rows if row.get("simulation_status") == "invalid"),
            "error_rows": sum(1 for row in rows if row.get("simulation_status") == "error"),
        },
        "consistency_checks": build_consistency_checks(rows),
        "financial": {
            "primary": summarize_financial(primary_rows),
            "all_simulated_success": summarize_financial([row for row in rows if row.get("simulation_status") == "success"]),
        },
        "groupings": {
            "primary": {
                "by_confidence_tier": make_group_summary(primary_rows, "confidence_tier"),
                "by_confidence_bucket": make_group_summary(primary_rows, "confidence_bucket"),
                "by_entry_side": make_group_summary(primary_rows, "entry_side"),
                "by_tf_sec": make_group_summary(primary_rows, "tf_sec"),
                "by_final_entry_verdict": make_group_summary(primary_rows, "final_entry_verdict"),
                "by_regime": make_group_summary(primary_rows, "envelope_regime"),
                "by_dissent_noted": make_group_summary(primary_rows, "verdict_dissent_noted"),
                "by_data_quality_issue": make_group_summary(primary_rows, "data_quality_issue"),
                "by_plan_reason_code": make_multivalue_group_summary(primary_rows, "plan_reason_codes"),
            },
            "diagnostic_counts": {
                "by_simulation_status": build_context_stats(rows, "simulation_status"),
                "by_terminal_reason": build_context_stats(rows, "terminal_reason"),
                "by_confidence_tier": build_context_stats(rows, "confidence_tier"),
                "by_entry_side": build_context_stats(rows, "entry_side"),
                "by_actionable": build_context_stats(rows, "actionable"),
                "by_suppressed": build_context_stats(rows, "suppressed"),
                "by_data_quality_issue": build_context_stats(rows, "data_quality_issue"),
            },
        },
        "cognitive": build_cognitive_summary(rows, primary_rows),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "summary.json", summary)
    write_jsonl(args.output_dir / "per_plan_rows.jsonl", rows)
    write_csv(args.output_dir / "per_plan_rows.csv", rows)
    report = build_report(summary, args.output_dir)
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze one judge shadow_entry_plan JSONL file.")
    parser.add_argument("--shadow-plan-file", type=Path, required=True)
    parser.add_argument("--judge-log-dir", type=Path,
                        default=REPO_ROOT / "logs" / "judge_experts")
    parser.add_argument("--recorder-root", type=Path,
                        default=REPO_ROOT / "data" / "recorder")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-bars-after-signal", type=int, default=12)
    parser.add_argument(
        "--intrabar-ambiguity-policy",
        choices=["mark_ambiguous", "prioritize_sl", "prioritize_tp"],
        default="mark_ambiguous",
    )
    parser.add_argument("--fees-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = REPO_ROOT / "reports" / "judge" / args.shadow_plan_file.stem
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = analyze(args)
    primary = summary["financial"]["primary"]
    print(
        json.dumps(
            {
                "output_dir": args.output_dir.as_posix(),
                "primary_rows": primary["rows"],
                "proposal_win_rate_pct": primary["proposal_win_rate_pct"],
                "filled_trade_win_rate_pct": primary["filled_trade_win_rate_pct"],
                "fill_rate_pct": primary["fill_rate_pct"],
                "total_net_pnl_pct": primary["total_net_pnl_pct"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
