from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER_PATH = ROOT / "calibrators" / "datasets" / "nrr062_readonly_reject_economics" / "nrr062_reject_ledger.json"
DEFAULT_REPLAY_RESULTS_PATH = ROOT / "calibrators" / "datasets" / "nrr062_counterfactual_replay_dataset" / "nrr062_counterfactual_replay_results.json"
DEFAULT_REPLAY_ECONOMICS_PATH = ROOT / "calibrators" / "datasets" / "nrr062_counterfactual_replay_dataset" / "nrr062_counterfactual_replay_economics.json"
DEFAULT_OUTPUT_DIR = ROOT / "calibrators" / "datasets" / "nrr062_segment_logic"

CLASSIFICATION_JSON = "nrr062_segment_classification.json"
CLASSIFICATION_CSV = "NRR062_SEGMENT_CLASSIFICATION.csv"
CLASSIFICATION_MD = "NRR062_SEGMENT_CLASSIFICATION.md"
EVALUATION_JSON = "nrr062_segment_replay_evaluation.json"
EVALUATION_MD = "NRR062_SEGMENT_REPLAY_EVALUATION.md"
COMPARISON_JSON = "nrr062_segment_vs_broad_replay.json"
COMPARISON_MD = "NRR062_SEGMENT_VS_BROAD_REPLAY.md"
READINESS_JSON = "nrr062_segment_readiness_gates.json"
READINESS_MD = "NRR062_SEGMENT_READINESS_GATES.md"
IMPLEMENTATION_SKETCH_MD = "NRR062_MINIMAL_RUNTIME_IMPLEMENTATION_SKETCH.md"

CANDIDATE_NAME = "NRR062_LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL_CANDIDATE"
TARGET_NRR_CODE = "NRR-062"
TARGET_REGIME = "LOW_VOLATILITY"
INVALID_OUTCOMES = {"COUNTERFACTUAL_INVALID_INPUT", "COUNTERFACTUAL_NO_MARKET_PATH"}
EXCLUDED_AMBIGUOUS_OUTCOME = "COUNTERFACTUAL_AMBIGUOUS_TP_SL"

READINESS_MIN_ROWS = 20
READINESS_MIN_NET_PNL = 0.0
READINESS_MIN_PROFIT_FACTOR = 1.2

LEDGER_REQUIRED_FIELDS = (
    "rid",
    "nrr_code",
    "regime",
    "side",
    "selected_source",
    "selected_scale",
    "threshold_family",
    "structured_fields_present",
    "gross_tp_bps",
    "required_gross_tp_bps_floor",
    "min_rr",
    "violations",
    "direction_confidence",
    "regime_confidence",
)

REPLAY_REQUIRED_FIELDS = (
    "rid",
    "outcome_class",
    "replay_status",
    "estimated_gross_pnl_quote",
    "estimated_net_pnl_quote",
    "estimated_fee_quote",
)


@dataclass(frozen=True, slots=True)
class CandidateReadiness:
    classification: str
    gate_rows_minimum: bool
    gate_positive_net: bool
    gate_profit_factor: bool
    gate_timeout_share: bool
    gate_buy_excluded_negative: bool
    gate_dual_excluded_negative: bool
    gate_required_fields_complete: bool
    gate_no_runtime_mutation_needed: bool


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        rendered: list[str] = []
        for value in row:
            if isinstance(value, float):
                rendered.append(f"{value:.10f}".rstrip("0").rstrip("."))
            elif value is None:
                rendered.append("")
            elif isinstance(value, list):
                rendered.append(", ".join(str(item) for item in value))
            elif isinstance(value, dict):
                rendered.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
            else:
                rendered.append(str(value))
        lines.append("| " + " | ".join(rendered) + " |")
    return lines


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value == ""
    return False


def normalize_side(side: str | None) -> str | None:
    if side is None:
        return None
    upper = str(side).upper()
    if upper in {"SELL", "SHORT"}:
        return "SHORT"
    if upper in {"BUY", "LONG"}:
        return "LONG"
    return upper


def canonical_violation_pattern(ledger_row: Mapping[str, Any], replay_row: Mapping[str, Any] | None) -> str:
    if replay_row is not None:
        replay_pattern = replay_row.get("violation_pattern")
        if replay_pattern:
            return str(replay_pattern)
    violations = ledger_row.get("violations") or []
    if not isinstance(violations, list):
        return ""
    return "+".join(str(item) for item in violations if item)


def has_structured_low_vol_metadata(ledger_row: Mapping[str, Any]) -> bool:
    return bool(ledger_row.get("structured_fields_present")) and str(ledger_row.get("parse_quality") or "") == "STRUCTURED_METADATA_COMPLETE"


def missing_required_fields(ledger_row: Mapping[str, Any], replay_row: Mapping[str, Any] | None) -> list[str]:
    missing: list[str] = []
    for field_name in LEDGER_REQUIRED_FIELDS:
        if _is_missing(ledger_row.get(field_name)):
            missing.append(f"ledger.{field_name}")
    if replay_row is None:
        missing.append("replay.row")
        return missing
    for field_name in REPLAY_REQUIRED_FIELDS:
        if _is_missing(replay_row.get(field_name)):
            missing.append(f"replay.{field_name}")
    return missing


def classify_row(ledger_row: Mapping[str, Any], replay_row: Mapping[str, Any] | None) -> dict[str, Any]:
    rid = str(ledger_row.get("rid") or (replay_row or {}).get("rid") or "")
    normalized_side = normalize_side(ledger_row.get("position_side") or ledger_row.get("side") or (replay_row or {}).get("side"))
    violation_pattern = canonical_violation_pattern(ledger_row, replay_row)
    outcome_class = str((replay_row or {}).get("outcome_class") or "")
    replay_status = str((replay_row or {}).get("replay_status") or "")
    missing_fields = missing_required_fields(ledger_row, replay_row)

    candidate_would_allow = False
    candidate_reason: str | None = None
    exclusion_reason: str | None = None
    segment_class = "UNCLASSIFIED"
    data_quality = str((replay_row or {}).get("replay_data_quality") or "UNSPECIFIED")

    if missing_fields:
        segment_class = "EXCLUDED_MISSING_REQUIRED_FIELDS"
        exclusion_reason = "missing_required_fields"
        data_quality = "MISSING_REQUIRED_FIELDS"
    elif str(ledger_row.get("nrr_code") or "") != TARGET_NRR_CODE:
        segment_class = "EXCLUDED_NON_NRR062"
        exclusion_reason = "nrr_code_not_nrr062"
        data_quality = "NON_TARGET_NRR"
    elif str(ledger_row.get("regime") or "") != TARGET_REGIME:
        segment_class = "EXCLUDED_NON_LOW_VOL_REGIME"
        exclusion_reason = "regime_not_low_volatility"
        data_quality = "NON_TARGET_REGIME"
    elif not has_structured_low_vol_metadata(ledger_row):
        segment_class = "EXCLUDED_MISSING_STRUCTURED_METADATA"
        exclusion_reason = "missing_structured_low_vol_metadata"
        data_quality = "STRUCTURED_METADATA_MISSING"
    elif replay_status != "READY":
        segment_class = "EXCLUDED_INVALID_REPLAY"
        exclusion_reason = f"replay_status_{replay_status.lower() or 'missing'}"
        data_quality = "REPLAY_INPUT_INVALID"
    elif outcome_class in INVALID_OUTCOMES:
        segment_class = "EXCLUDED_INVALID_REPLAY"
        exclusion_reason = outcome_class.lower()
        data_quality = "REPLAY_INPUT_INVALID"
    elif normalized_side != "SHORT":
        segment_class = "EXCLUDED_BUY_OR_LONG"
        exclusion_reason = "buy_or_long"
    elif violation_pattern == "regime_confidence_below_threshold+direction_confidence_below_threshold":
        segment_class = "EXCLUDED_DUAL_FAILURE"
        exclusion_reason = "dual_regime_and_direction_failure"
    elif violation_pattern != "direction_confidence_below_threshold":
        segment_class = "EXCLUDED_NON_DIRECTION_ONLY"
        exclusion_reason = "not_direction_only_failure"
    elif str(ledger_row.get("selected_source") or "") != "signal_score":
        segment_class = "EXCLUDED_NON_SIGNAL_SCORE_SOURCE"
        exclusion_reason = "selected_source_not_signal_score"
    elif str(ledger_row.get("selected_scale") or "") != "raw_signed_score":
        segment_class = "EXCLUDED_NON_RAW_SIGNED_SCORE"
        exclusion_reason = "selected_scale_not_raw_signed_score"
    elif str(ledger_row.get("threshold_family") or "") != "raw_signed_score":
        segment_class = "EXCLUDED_NON_RAW_THRESHOLD_FAMILY"
        exclusion_reason = "threshold_family_not_raw_signed_score"
    elif outcome_class == EXCLUDED_AMBIGUOUS_OUTCOME:
        segment_class = "EXCLUDED_AMBIGUOUS_TP_SL"
        exclusion_reason = "ambiguous_tp_sl_excluded"
        data_quality = "AMBIGUOUS_TP_SL"
    else:
        candidate_would_allow = True
        segment_class = CANDIDATE_NAME
        if outcome_class == "COUNTERFACTUAL_TIMEOUT":
            candidate_reason = "matches_segment_rule_timeout_measured"
        else:
            candidate_reason = "matches_segment_rule"

    return {
        "rid": rid,
        "segment_class": segment_class,
        "candidate_would_allow": candidate_would_allow,
        "candidate_reason": candidate_reason,
        "exclusion_reason": exclusion_reason,
        "required_fields_present": not missing_fields,
        "missing_required_fields": missing_fields,
        "data_quality": data_quality,
        "nrr_code": ledger_row.get("nrr_code"),
        "symbol": ledger_row.get("symbol"),
        "side": ledger_row.get("side"),
        "position_side": ledger_row.get("position_side"),
        "normalized_side": normalized_side,
        "strategy_id": ledger_row.get("strategy_id"),
        "regime": ledger_row.get("regime"),
        "selected_source": ledger_row.get("selected_source"),
        "selected_scale": ledger_row.get("selected_scale"),
        "threshold_family": ledger_row.get("threshold_family"),
        "violation_pattern": violation_pattern,
        "structured_fields_present": bool(ledger_row.get("structured_fields_present")),
        "parse_quality": ledger_row.get("parse_quality"),
        "replay_status": replay_status,
        "outcome_class": outcome_class,
        "replay_data_quality": (replay_row or {}).get("replay_data_quality"),
        "timestamp_ms": ledger_row.get("timestamp_ms"),
        "timestamp_utc": ledger_row.get("timestamp_utc"),
        "direction_confidence": _safe_float(ledger_row.get("direction_confidence")),
        "regime_confidence": _safe_float(ledger_row.get("regime_confidence")),
        "gross_tp_bps": _safe_float(ledger_row.get("gross_tp_bps")),
        "required_gross_tp_bps_floor": _safe_float(ledger_row.get("required_gross_tp_bps_floor")),
        "min_rr": _safe_float(ledger_row.get("min_rr")),
        "estimated_gross_pnl_quote": _safe_float((replay_row or {}).get("estimated_gross_pnl_quote")),
        "estimated_net_pnl_quote": _safe_float((replay_row or {}).get("estimated_net_pnl_quote")),
        "estimated_fee_quote": _safe_float((replay_row or {}).get("estimated_fee_quote")),
        "direction_confidence_bucket": (replay_row or {}).get("direction_confidence_bucket") or ledger_row.get("direction_confidence_bucket"),
        "regime_confidence_bucket": (replay_row or {}).get("regime_confidence_bucket") or ledger_row.get("regime_confidence_bucket"),
    }


def classify_dataset(ledger_rows: list[Mapping[str, Any]], replay_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    replay_by_rid = {str(row.get("rid")): row for row in replay_rows}
    rows = [classify_row(ledger_row, replay_by_rid.get(str(ledger_row.get("rid")))) for ledger_row in ledger_rows]
    return sorted(rows, key=lambda row: (row.get("timestamp_ms") or 0, str(row.get("rid") or "")))


def _sum(values: Iterable[float | None]) -> float:
    return sum(value for value in values if value is not None)


def _profit_factor(rows: list[Mapping[str, Any]]) -> float | None:
    positive = _sum(row.get("estimated_net_pnl_quote") for row in rows if _safe_float(row.get("estimated_net_pnl_quote")) is not None and float(row["estimated_net_pnl_quote"]) > 0)
    negative = abs(_sum(row.get("estimated_net_pnl_quote") for row in rows if _safe_float(row.get("estimated_net_pnl_quote")) is not None and float(row["estimated_net_pnl_quote"]) < 0))
    if negative == 0:
        return None
    return positive / negative


def _median(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return float(statistics.median(cleaned))


def build_metrics(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    row_count = len(rows)
    outcome_counts = Counter(str(row.get("outcome_class") or "UNKNOWN") for row in rows)
    net_values = [_safe_float(row.get("estimated_net_pnl_quote")) for row in rows]
    gross_values = [_safe_float(row.get("estimated_gross_pnl_quote")) for row in rows]
    fee_values = [_safe_float(row.get("estimated_fee_quote")) for row in rows]
    valid_net_values = [value for value in net_values if value is not None]
    win_count = sum(1 for value in valid_net_values if value > 0)
    loss_count = sum(1 for value in valid_net_values if value < 0)
    estimated_gross_pnl_quote = _sum(gross_values)
    estimated_net_pnl_quote = _sum(net_values)
    estimated_fees_quote = _sum(fee_values)
    timeout_count = outcome_counts.get("COUNTERFACTUAL_TIMEOUT", 0)
    fee_drag_share_of_gross = None
    if estimated_gross_pnl_quote != 0:
        fee_drag_share_of_gross = estimated_fees_quote / abs(estimated_gross_pnl_quote)
    return {
        "row_count": row_count,
        "tp_count": outcome_counts.get("COUNTERFACTUAL_TP", 0),
        "sl_count": outcome_counts.get("COUNTERFACTUAL_SL", 0),
        "timeout_count": timeout_count,
        "ambiguous_count": outcome_counts.get(EXCLUDED_AMBIGUOUS_OUTCOME, 0),
        "estimated_gross_pnl_quote": estimated_gross_pnl_quote,
        "estimated_net_pnl_quote": estimated_net_pnl_quote,
        "estimated_fees_quote": estimated_fees_quote,
        "win_rate": (win_count / row_count * 100.0) if row_count else None,
        "profit_factor": _profit_factor(rows),
        "timeout_share": (timeout_count / row_count) if row_count else None,
        "median_direction_confidence": _median([_safe_float(row.get("direction_confidence")) for row in rows]),
        "median_regime_confidence": _median([_safe_float(row.get("regime_confidence")) for row in rows]),
        "symbol_distribution": dict(Counter(str(row.get("symbol") or "UNKNOWN") for row in rows)),
        "side_distribution": dict(Counter(str(row.get("side") or "UNKNOWN") for row in rows)),
        "fee_drag_quote": estimated_fees_quote,
        "fee_drag_share_of_gross": fee_drag_share_of_gross,
        "win_count": win_count,
        "loss_count": loss_count,
    }


def build_evaluation_payload(classification_rows: list[dict[str, Any]], replay_economics_payload: Mapping[str, Any]) -> dict[str, Any]:
    broad_summary = dict(replay_economics_payload.get("summary") or {})
    candidate_rows = [row for row in classification_rows if bool(row.get("candidate_would_allow"))]
    non_candidate_rows = [row for row in classification_rows if not bool(row.get("candidate_would_allow"))]
    buy_rows = [row for row in classification_rows if normalize_side(row.get("side")) == "LONG"]
    dual_failure_rows = [row for row in classification_rows if row.get("violation_pattern") == "regime_confidence_below_threshold+direction_confidence_below_threshold"]

    candidate_metrics = build_metrics(candidate_rows)
    non_candidate_metrics = build_metrics(non_candidate_rows)
    buy_metrics = build_metrics(buy_rows)
    dual_failure_metrics = build_metrics(dual_failure_rows)

    return {
        "generated_at_utc": _utc_now(),
        "candidate_name": CANDIDATE_NAME,
        "broad_summary_reference": broad_summary,
        "candidate_summary": candidate_metrics,
        "excluded_group_behavior": {
            "buy_excluded": buy_metrics,
            "dual_failure_excluded": dual_failure_metrics,
            "non_candidate": non_candidate_metrics,
            "excluded_tp_count": non_candidate_metrics["tp_count"],
            "excluded_sl_count": non_candidate_metrics["sl_count"],
            "non_candidate_timeout_share": non_candidate_metrics["timeout_share"],
        },
        "classification_summary": {
            "candidate_rows": len(candidate_rows),
            "excluded_rows": len(non_candidate_rows),
            "segment_class_counts": dict(Counter(str(row.get("segment_class") or "UNSPECIFIED") for row in classification_rows)),
            "exclusion_reason_counts": dict(Counter(str(row.get("exclusion_reason") or "NONE") for row in classification_rows if not row.get("candidate_would_allow"))),
        },
    }


def build_comparison_payload(classification_rows: list[dict[str, Any]], evaluation_payload: Mapping[str, Any], replay_results_payload: Mapping[str, Any]) -> dict[str, Any]:
    broad_summary = dict(evaluation_payload.get("broad_summary_reference") or {})
    candidate_summary = dict(evaluation_payload.get("candidate_summary") or {})
    buy_excluded = dict((evaluation_payload.get("excluded_group_behavior") or {}).get("buy_excluded") or {})
    dual_failure_excluded = dict((evaluation_payload.get("excluded_group_behavior") or {}).get("dual_failure_excluded") or {})

    broad_timeout_share = None
    total_replay_rows = broad_summary.get("total_replay_rows")
    timeout_count = broad_summary.get("timeout_count")
    if total_replay_rows:
        broad_timeout_share = float(timeout_count) / float(total_replay_rows)

    candidate_rows = int(candidate_summary.get("row_count") or 0)
    candidate_net = float(candidate_summary.get("estimated_net_pnl_quote") or 0.0)
    buy_net = float(buy_excluded.get("estimated_net_pnl_quote") or 0.0)
    dual_net = float(dual_failure_excluded.get("estimated_net_pnl_quote") or 0.0)

    questions = [
        {
            "question": "Does the candidate retain the positive replay signal?",
            "answer": "yes" if candidate_net > 0 else "no",
            "evidence": f"candidate_net={candidate_net}",
        },
        {
            "question": "Does it exclude most negative BUY exposure?",
            "answer": "yes" if buy_net < 0 else "no",
            "evidence": f"excluded_buy_net={buy_net}",
        },
        {
            "question": "Does it exclude dual-failure negative exposure?",
            "answer": "yes" if dual_net < 0 else "no",
            "evidence": f"excluded_dual_failure_net={dual_net}",
        },
        {
            "question": "Is timeout share still too high?",
            "answer": "yes" if candidate_summary.get("timeout_share") is not None and broad_timeout_share is not None and float(candidate_summary["timeout_share"]) > broad_timeout_share else "no",
            "evidence": f"candidate_timeout_share={candidate_summary.get('timeout_share')}, broad_timeout_share={broad_timeout_share}",
        },
        {
            "question": "Is candidate row count large enough to matter?",
            "answer": "yes" if candidate_rows >= READINESS_MIN_ROWS else "no",
            "evidence": f"candidate_rows={candidate_rows}, readiness_min_rows={READINESS_MIN_ROWS}",
        },
        {
            "question": "Would this be a reasonable future testnet implementation candidate?",
            "answer": "yes" if candidate_rows >= READINESS_MIN_ROWS and candidate_net > 0 else "no",
            "evidence": f"candidate_rows={candidate_rows}, candidate_net={candidate_net}",
        },
    ]

    return {
        "generated_at_utc": _utc_now(),
        "candidate_name": CANDIDATE_NAME,
        "broad_package_b": broad_summary,
        "candidate_segment": candidate_summary,
        "excluded_negative_surfaces": {
            "buy_rows": buy_excluded,
            "dual_failure_rows": dual_failure_excluded,
        },
        "question_assessment": questions,
        "replay_result_row_count": len(replay_results_payload.get("rows") or []),
    }


def assess_readiness(evaluation_payload: Mapping[str, Any]) -> CandidateReadiness:
    candidate_summary = dict(evaluation_payload.get("candidate_summary") or {})
    excluded_groups = dict(evaluation_payload.get("excluded_group_behavior") or {})
    broad_summary = dict(evaluation_payload.get("broad_summary_reference") or {})
    buy_excluded = dict(excluded_groups.get("buy_excluded") or {})
    dual_excluded = dict(excluded_groups.get("dual_failure_excluded") or {})

    broad_timeout_share = None
    broad_total_rows = broad_summary.get("total_replay_rows")
    broad_timeout_count = broad_summary.get("timeout_count")
    if broad_total_rows:
        broad_timeout_share = float(broad_timeout_count) / float(broad_total_rows)

    gate_rows_minimum = int(candidate_summary.get("row_count") or 0) >= READINESS_MIN_ROWS
    gate_positive_net = float(candidate_summary.get("estimated_net_pnl_quote") or 0.0) > READINESS_MIN_NET_PNL
    candidate_profit_factor = candidate_summary.get("profit_factor")
    gate_profit_factor = candidate_profit_factor is not None and float(candidate_profit_factor) > READINESS_MIN_PROFIT_FACTOR
    candidate_timeout_share = candidate_summary.get("timeout_share")
    gate_timeout_share = broad_timeout_share is not None and candidate_timeout_share is not None and float(candidate_timeout_share) <= float(broad_timeout_share)
    gate_buy_excluded_negative = float(buy_excluded.get("estimated_net_pnl_quote") or 0.0) < 0.0
    gate_dual_excluded_negative = float(dual_excluded.get("estimated_net_pnl_quote") or 0.0) < 0.0
    gate_required_fields_complete = int((evaluation_payload.get("classification_summary") or {}).get("segment_class_counts", {}).get("EXCLUDED_MISSING_REQUIRED_FIELDS", 0)) == 0
    gate_no_runtime_mutation_needed = True

    if not gate_required_fields_complete:
        classification = "BLOCKED_BY_DATA_QUALITY"
    elif int(candidate_summary.get("row_count") or 0) == 0 or not gate_positive_net:
        classification = "NO_SEGMENT_EDGE"
    elif not gate_rows_minimum:
        classification = "INSUFFICIENT_ROWS"
    elif not (gate_buy_excluded_negative and gate_dual_excluded_negative):
        classification = "UNSAFE_FALSE_POSITIVE_RISK"
    elif gate_profit_factor and gate_timeout_share and gate_no_runtime_mutation_needed:
        classification = "FUTURE_TESTNET_IMPLEMENTATION_CANDIDATE"
    else:
        classification = "PROMISING_BUT_TIMEOUT_DOMINATED"

    return CandidateReadiness(
        classification=classification,
        gate_rows_minimum=gate_rows_minimum,
        gate_positive_net=gate_positive_net,
        gate_profit_factor=gate_profit_factor,
        gate_timeout_share=gate_timeout_share,
        gate_buy_excluded_negative=gate_buy_excluded_negative,
        gate_dual_excluded_negative=gate_dual_excluded_negative,
        gate_required_fields_complete=gate_required_fields_complete,
        gate_no_runtime_mutation_needed=gate_no_runtime_mutation_needed,
    )


def build_readiness_payload(evaluation_payload: Mapping[str, Any]) -> dict[str, Any]:
    readiness = assess_readiness(evaluation_payload)
    candidate_summary = dict(evaluation_payload.get("candidate_summary") or {})
    broad_summary = dict(evaluation_payload.get("broad_summary_reference") or {})
    excluded_groups = dict(evaluation_payload.get("excluded_group_behavior") or {})
    broad_timeout_share = None
    if broad_summary.get("total_replay_rows"):
        broad_timeout_share = float(broad_summary.get("timeout_count") or 0) / float(broad_summary["total_replay_rows"])
    candidate_timeout_share = candidate_summary.get("timeout_share")
    return {
        "generated_at_utc": _utc_now(),
        "candidate_name": CANDIDATE_NAME,
        "classification": readiness.classification,
        "gates": {
            "candidate_rows_gte_20": {
                "passed": readiness.gate_rows_minimum,
                "evidence": f"candidate_rows={candidate_summary.get('row_count')}",
            },
            "candidate_estimated_net_positive": {
                "passed": readiness.gate_positive_net,
                "evidence": f"candidate_estimated_net_pnl_quote={candidate_summary.get('estimated_net_pnl_quote')}",
            },
            "candidate_profit_factor_gt_1_2": {
                "passed": readiness.gate_profit_factor,
                "evidence": f"candidate_profit_factor={candidate_summary.get('profit_factor')}",
            },
            "candidate_timeout_share_lte_broad": {
                "passed": readiness.gate_timeout_share,
                "evidence": f"candidate_timeout_share={candidate_timeout_share}; broad_timeout_share={broad_timeout_share}",
            },
            "buy_excluded_net_negative": {
                "passed": readiness.gate_buy_excluded_negative,
                "evidence": f"buy_excluded_net={excluded_groups.get('buy_excluded', {}).get('estimated_net_pnl_quote')}",
            },
            "dual_failure_excluded_net_negative": {
                "passed": readiness.gate_dual_excluded_negative,
                "evidence": f"dual_failure_excluded_net={excluded_groups.get('dual_failure_excluded', {}).get('estimated_net_pnl_quote')}",
            },
            "required_structured_fields_complete": {
                "passed": readiness.gate_required_fields_complete,
                "evidence": f"excluded_missing_required_fields={(evaluation_payload.get('classification_summary') or {}).get('segment_class_counts', {}).get('EXCLUDED_MISSING_REQUIRED_FIELDS', 0)}",
            },
            "no_yaml_or_runtime_mutation_needed": {
                "passed": readiness.gate_no_runtime_mutation_needed,
                "evidence": "offline calibrator only; no config/runtime mutation paths in this package",
            },
        },
    }


def _git_capture() -> dict[str, Any]:
    try:
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        status_output = subprocess.run(["git", "status", "--short"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
        return {
            "branch": branch,
            "commit_sha": commit_sha,
            "git_status_short": status_output,
        }
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {
            "branch": "UNKNOWN",
            "commit_sha": "UNKNOWN",
            "git_status_short": [],
        }


def _implementation_mode(classification: str) -> str:
    if classification == "FUTURE_TESTNET_IMPLEMENTATION_CANDIDATE":
        return "2. testnet-only explicit operator override"
    if classification == "PROMISING_BUT_TIMEOUT_DOMINATED":
        return "1. offline shadow analysis only"
    return "3. production never until future proof"


def render_classification_markdown(payload: Mapping[str, Any]) -> list[str]:
    summary = dict(payload.get("summary") or {})
    rows = list(payload.get("rows") or [])
    lines = [
        "# NRR062_SEGMENT_CLASSIFICATION",
        "",
        "## Summary",
    ]
    lines.extend(_markdown_table(
        ["Metric", "Value", "Notes"],
        [
            ["Candidate Name", payload.get("candidate_name"), "offline-only deterministic segment rule"],
            ["Total Rows", summary.get("total_rows"), "expected canonical reject cohort size"],
            ["Candidate Rows", summary.get("candidate_rows"), "rows that the offline candidate would allow"],
            ["Excluded Rows", summary.get("excluded_rows"), "rows retained as excluded risk surface"],
            ["Missing Required Fields", summary.get("missing_required_fields_rows"), "rows excluded for data quality"],
        ],
    ))
    lines.extend(["", "## Segment Classes"])
    lines.extend(_markdown_table(
        ["Segment Class", "Rows"],
        sorted((segment_class, count) for segment_class, count in dict(summary.get("segment_class_counts") or {}).items()),
    ))
    lines.extend(["", "## First Rows"])
    preview_rows = rows[:10]
    lines.extend(_markdown_table(
        ["RID", "Segment Class", "Candidate?", "Symbol", "Side", "Violation Pattern", "Outcome Class", "Exclusion Reason"],
        [
            [row.get("rid"), row.get("segment_class"), row.get("candidate_would_allow"), row.get("symbol"), row.get("side"), row.get("violation_pattern"), row.get("outcome_class"), row.get("exclusion_reason")]
            for row in preview_rows
        ],
    ))
    return lines


def render_evaluation_markdown(payload: Mapping[str, Any]) -> list[str]:
    candidate = dict(payload.get("candidate_summary") or {})
    excluded = dict(payload.get("excluded_group_behavior") or {})
    lines = [
        "# NRR062_SEGMENT_REPLAY_EVALUATION",
        "",
        "## Candidate Summary",
    ]
    lines.extend(_markdown_table(
        ["Metric", "Value", "Notes"],
        [
            ["Row Count", candidate.get("row_count"), "candidate_would_allow=true rows"],
            ["TP Count", candidate.get("tp_count"), "counterfactual TP rows"],
            ["SL Count", candidate.get("sl_count"), "counterfactual SL rows"],
            ["TIMEOUT Count", candidate.get("timeout_count"), "counterfactual TIMEOUT rows"],
            ["AMBIGUOUS Count", candidate.get("ambiguous_count"), "policy excludes ambiguous rows"],
            ["Estimated Gross PnL Quote", candidate.get("estimated_gross_pnl_quote"), "sum across candidate rows"],
            ["Estimated Net PnL Quote", candidate.get("estimated_net_pnl_quote"), "sum across candidate rows"],
            ["Estimated Fees Quote", candidate.get("estimated_fees_quote"), "sum across candidate rows"],
            ["Win Rate", candidate.get("win_rate"), "positive estimated net / candidate rows"],
            ["Profit Factor", candidate.get("profit_factor"), "sum positive net / abs(sum negative net)"],
            ["Timeout Share", candidate.get("timeout_share"), "timeouts / candidate rows"],
            ["Median Direction Confidence", candidate.get("median_direction_confidence"), "signed raw value from structured metadata"],
            ["Median Regime Confidence", candidate.get("median_regime_confidence"), "structured regime_confidence median"],
            ["Symbol Distribution", candidate.get("symbol_distribution"), "candidate symbol counts"],
            ["Side Distribution", candidate.get("side_distribution"), "candidate side counts"],
            ["Fee Drag", candidate.get("fee_drag_quote"), "quote-denominated fee drag"],
        ],
    ))
    lines.extend(["", "## Excluded Group Behavior"])
    lines.extend(_markdown_table(
        ["Excluded Segment", "Rows", "Net Proxy", "Timeout Share", "TP Count", "SL Count"],
        [
            ["BUY/LONG", excluded.get("buy_excluded", {}).get("row_count"), excluded.get("buy_excluded", {}).get("estimated_net_pnl_quote"), excluded.get("buy_excluded", {}).get("timeout_share"), excluded.get("buy_excluded", {}).get("tp_count"), excluded.get("buy_excluded", {}).get("sl_count")],
            ["Dual Regime+Direction Failure", excluded.get("dual_failure_excluded", {}).get("row_count"), excluded.get("dual_failure_excluded", {}).get("estimated_net_pnl_quote"), excluded.get("dual_failure_excluded", {}).get("timeout_share"), excluded.get("dual_failure_excluded", {}).get("tp_count"), excluded.get("dual_failure_excluded", {}).get("sl_count")],
            ["All Non-Candidate Rows", excluded.get("non_candidate", {}).get("row_count"), excluded.get("non_candidate", {}).get("estimated_net_pnl_quote"), excluded.get("non_candidate", {}).get("timeout_share"), payload.get("excluded_group_behavior", {}).get("excluded_tp_count"), payload.get("excluded_group_behavior", {}).get("excluded_sl_count")],
        ],
    ))
    return lines


def render_comparison_markdown(payload: Mapping[str, Any]) -> list[str]:
    broad = dict(payload.get("broad_package_b") or {})
    candidate = dict(payload.get("candidate_segment") or {})
    questions = list(payload.get("question_assessment") or [])
    lines = [
        "# NRR062_SEGMENT_VS_BROAD_REPLAY",
        "",
        "## Broad vs Candidate",
    ]
    lines.extend(_markdown_table(
        ["Metric", "Broad Package B", "Candidate Segment", "Interpretation"],
        [
            ["Rows", broad.get("total_replay_rows"), candidate.get("row_count"), "candidate is a strict subset of Package B replay surface"],
            ["TP Count", broad.get("tp_count"), candidate.get("tp_count"), "candidate kept TP subset"],
            ["SL Count", broad.get("sl_count"), candidate.get("sl_count"), "candidate retained SL subset"],
            ["TIMEOUT Count", broad.get("timeout_count"), candidate.get("timeout_count"), "timeout concentration check"],
            ["Estimated Net PnL Quote", broad.get("estimated_net_pnl_quote"), candidate.get("estimated_net_pnl_quote"), "positive signal retention check"],
            ["Profit Factor", broad.get("profit_factor"), candidate.get("profit_factor"), "candidate quality vs broad quality"],
            ["Timeout Share", (float(broad.get("timeout_count")) / float(broad.get("total_replay_rows"))) if broad.get("total_replay_rows") else None, candidate.get("timeout_share"), "timeout dominance check"],
        ],
    ))
    lines.extend(["", "## Questions"])
    lines.extend(_markdown_table(
        ["Question", "Answer", "Evidence"],
        [[item.get("question"), item.get("answer"), item.get("evidence")] for item in questions],
    ))
    return lines


def render_readiness_markdown(payload: Mapping[str, Any]) -> list[str]:
    gates = dict(payload.get("gates") or {})
    lines = [
        "# NRR062_SEGMENT_READINESS_GATES",
        "",
        f"Readiness classification: {payload.get('classification')}",
        "",
        "## Gates",
    ]
    lines.extend(_markdown_table(
        ["Gate", "Passed?", "Evidence"],
        [[gate, detail.get("passed"), detail.get("evidence")] for gate, detail in gates.items()],
    ))
    return lines


def render_implementation_sketch_markdown(readiness_payload: Mapping[str, Any]) -> list[str]:
    classification = str(readiness_payload.get("classification") or "UNKNOWN")
    return [
        "# NRR062_MINIMAL_RUNTIME_IMPLEMENTATION_SKETCH",
        "",
        "## likely_runtime_location",
        "- apps/reference/domains/decision_making/gates/low_vol_cost_floor.py would be the likely enforcement surface because it already owns LOW_VOL candidate blocking and exposes selected_source, selected_scale, threshold_family, side, regime, and violation metadata.",
        "- apps/reference/config/domains/decision_making.py would be the contract review surface only if an operator later permits explicit config/schema changes. This package does not touch that model.",
        "",
        "## existing_fields_needed",
        "- nrr_code",
        "- regime",
        "- side / position_side",
        "- selected_source",
        "- selected_scale",
        "- threshold_family",
        "- violations",
        "- gross_tp_bps",
        "- required_gross_tp_bps_floor",
        "- min_rr",
        "- replay outcome proxy artifacts for offline proof only",
        "",
        "## business_rule_risk",
        "- Hardcoding segment logic directly in runtime would be a business-rule risk because SELL-only + direction-only + raw-signal-only selection is not currently expressible in YAML/Pydantic and would create hidden operator policy outside SSOT config.",
        "- Any future runtime implementation should therefore be explicit, isolated, and operator-approved rather than smuggled in as an implicit branch inside the live gate.",
        "",
        "## preferred_implementation_mode",
        f"- {_implementation_mode(classification)}",
        "",
        "## rollback",
        "- If a future explicit implementation is attempted, keep it behind a testnet-only operator gate and remove that gate in one revertable change if BUY losses, dual-failure admissions, or timeout concentration worsen.",
        "- Rollback path should be a single code-path disablement, not a threshold rewrite.",
        "",
        "## required_tests",
        "- unit tests for side segmentation, dual-failure exclusion, and raw-signal family matching",
        "- import-boundary regression so apps/reference runtime still does not import calibrators",
        "- offline replay regression showing candidate metrics remain stable on the same 153-row cohort",
        "- future testnet-only integration tests before any operator rollout",
    ]


def _classification_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    segment_counts = Counter(str(row.get("segment_class") or "UNSPECIFIED") for row in rows)
    candidate_rows = sum(1 for row in rows if bool(row.get("candidate_would_allow")))
    excluded_rows = len(rows) - candidate_rows
    missing_required_fields_rows = segment_counts.get("EXCLUDED_MISSING_REQUIRED_FIELDS", 0)
    return {
        "total_rows": len(rows),
        "candidate_rows": candidate_rows,
        "excluded_rows": excluded_rows,
        "missing_required_fields_rows": missing_required_fields_rows,
        "segment_class_counts": dict(segment_counts),
    }


def _csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    csv_rows: list[dict[str, Any]] = []
    for row in rows:
        converted = dict(row)
        converted["missing_required_fields"] = ",".join(str(item) for item in row.get("missing_required_fields") or [])
        csv_rows.append(converted)
    return csv_rows


def generate_artifacts(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    replay_results_path: Path = DEFAULT_REPLAY_RESULTS_PATH,
    replay_economics_path: Path = DEFAULT_REPLAY_ECONOMICS_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    ledger_payload = _read_json(ledger_path)
    replay_results_payload = _read_json(replay_results_path)
    replay_economics_payload = _read_json(replay_economics_path)

    ledger_rows = list(ledger_payload.get("rows") or [])
    replay_rows = list(replay_results_payload.get("rows") or [])
    classification_rows = classify_dataset(ledger_rows, replay_rows)
    classification_payload = {
        "generated_at_utc": _utc_now(),
        "candidate_name": CANDIDATE_NAME,
        "git": _git_capture(),
        "inputs": {
            "ledger_path": str(ledger_path),
            "replay_results_path": str(replay_results_path),
            "replay_economics_path": str(replay_economics_path),
        },
        "summary": _classification_summary(classification_rows),
        "rows": classification_rows,
    }
    evaluation_payload = build_evaluation_payload(classification_rows, replay_economics_payload)
    comparison_payload = build_comparison_payload(classification_rows, evaluation_payload, replay_results_payload)
    readiness_payload = build_readiness_payload(evaluation_payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / CLASSIFICATION_JSON, classification_payload)
    _write_json(output_dir / EVALUATION_JSON, evaluation_payload)
    _write_json(output_dir / COMPARISON_JSON, comparison_payload)
    _write_json(output_dir / READINESS_JSON, readiness_payload)

    csv_fieldnames = [
        "rid",
        "segment_class",
        "candidate_would_allow",
        "candidate_reason",
        "exclusion_reason",
        "required_fields_present",
        "missing_required_fields",
        "data_quality",
        "nrr_code",
        "symbol",
        "side",
        "position_side",
        "normalized_side",
        "strategy_id",
        "regime",
        "selected_source",
        "selected_scale",
        "threshold_family",
        "violation_pattern",
        "structured_fields_present",
        "parse_quality",
        "replay_status",
        "outcome_class",
        "replay_data_quality",
        "timestamp_ms",
        "timestamp_utc",
        "direction_confidence",
        "regime_confidence",
        "gross_tp_bps",
        "required_gross_tp_bps_floor",
        "min_rr",
        "estimated_gross_pnl_quote",
        "estimated_net_pnl_quote",
        "estimated_fee_quote",
        "direction_confidence_bucket",
        "regime_confidence_bucket",
    ]
    _write_csv(output_dir / CLASSIFICATION_CSV, _csv_rows(classification_rows), csv_fieldnames)

    _write_markdown(output_dir / CLASSIFICATION_MD, render_classification_markdown(classification_payload))
    _write_markdown(output_dir / EVALUATION_MD, render_evaluation_markdown(evaluation_payload))
    _write_markdown(output_dir / COMPARISON_MD, render_comparison_markdown(comparison_payload))
    _write_markdown(output_dir / READINESS_MD, render_readiness_markdown(readiness_payload))
    _write_markdown(output_dir / IMPLEMENTATION_SKETCH_MD, render_implementation_sketch_markdown(readiness_payload))

    return {
        "classification": classification_payload,
        "evaluation": evaluation_payload,
        "comparison": comparison_payload,
        "readiness": readiness_payload,
        "outputs": {
            "classification_json": str(output_dir / CLASSIFICATION_JSON),
            "classification_csv": str(output_dir / CLASSIFICATION_CSV),
            "classification_md": str(output_dir / CLASSIFICATION_MD),
            "evaluation_json": str(output_dir / EVALUATION_JSON),
            "evaluation_md": str(output_dir / EVALUATION_MD),
            "comparison_json": str(output_dir / COMPARISON_JSON),
            "comparison_md": str(output_dir / COMPARISON_MD),
            "readiness_json": str(output_dir / READINESS_JSON),
            "readiness_md": str(output_dir / READINESS_MD),
            "implementation_sketch_md": str(output_dir / IMPLEMENTATION_SKETCH_MD),
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline segment-logic replay classifier for NRR-062 LOW_VOL_COST_FLOOR.")
    parser.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--replay-results-path", type=Path, default=DEFAULT_REPLAY_RESULTS_PATH)
    parser.add_argument("--replay-economics-path", type=Path, default=DEFAULT_REPLAY_ECONOMICS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = generate_artifacts(
        ledger_path=args.ledger_path,
        replay_results_path=args.replay_results_path,
        replay_economics_path=args.replay_economics_path,
        output_dir=args.output_dir,
    )
    summary = {
        "candidate_name": CANDIDATE_NAME,
        "classification": result["readiness"]["classification"],
        "candidate_rows": result["evaluation"]["candidate_summary"]["row_count"],
        "candidate_net": result["evaluation"]["candidate_summary"]["estimated_net_pnl_quote"],
        "candidate_timeout_share": result["evaluation"]["candidate_summary"]["timeout_share"],
        "output_dir": str(args.output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())