#!/usr/bin/env python3
from __future__ import annotations
from apps.reference.telemetry.trade_lifecycle_logger import (
    EXECUTION_FILL_INGRESS_RECORD_KIND,
    POSITION_POLICY_SIDECAR_RECORD_KIND,
    iter_trade_lifecycle_records,
)

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_WAL_GLOB = "ops/wal/*.jsonl"
DEFAULT_ORDER_LOG = "logs/order_log_v1.jsonl"
DEFAULT_TRADE_LIFECYCLE = "logs/trade_lifecycle.jsonl"
DEFAULT_DOMAINS_CONFIG = PROJECT_ROOT / "config/aurora/domains.yaml"
INGRESS_EVENT_NAMES = (
    "PORTFOLIO_STATE_UPDATED",
    "ORDER_FILL",
    "TRADE_EXECUTED",
    "ORDER_STATE_CHANGED",
    "EXECUTION_CLOSE_RECONCILED",
    "FEATURES_CALCULATED",
    "REGIME_DETECTED",
)


def _load_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _trade_lifecycle_rows(path: Path) -> List[Dict[str, Any]]:
    return list(
        iter_trade_lifecycle_records(
            log_file=str(path),
            include_policy_records=True,
        )
    )


def _record_ts_ms(record: Dict[str, Any]) -> int:
    raw_value = record.get("ts_ms")
    if raw_value in (None, ""):
        raw_value = record.get("updated_ts_ms")
    if raw_value in (None, ""):
        raw_value = record.get("close_ts_ms")
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        try:
            return int(float(raw_value))
        except (TypeError, ValueError):
            return 0


def _policy_rows(path: Path) -> List[Dict[str, Any]]:
    return [
        record
        for record in _trade_lifecycle_rows(path)
        if record.get("record_kind") == POSITION_POLICY_SIDECAR_RECORD_KIND
    ]


def _fill_ingress_rows(path: Path) -> List[Dict[str, Any]]:
    return [
        record
        for record in _trade_lifecycle_rows(path)
        if record.get("record_kind") == EXECUTION_FILL_INGRESS_RECORD_KIND
    ]


def _load_recommend_threshold(config_path: Path) -> float | None:
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    raw_value = (
        ((config.get("execution_position") or {}).get(
            "position_policy_sidecar") or {})
        .get("thresholds", {})
        .get("recommend_soft_close_at")
    )
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _row_identity(row: Dict[str, Any]) -> str:
    trace_id = str(row.get("trace_id") or "").strip()
    if trace_id:
        return trace_id
    return f"{row.get('symbol')}:{_record_ts_ms(row)}:{row.get('event_type')}"


def _soft_close_pressure(row: Dict[str, Any]) -> float | None:
    score_snapshot = row.get("score_snapshot") or {}
    raw_value = score_snapshot.get("soft_close_pressure")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _top_counter_entry(counts: Counter) -> Dict[str, Any] | None:
    if not counts:
        return None
    reason, count = sorted(
        counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return {
        "reason": reason,
        "count": count,
    }


def _symbol_fill_ingress_counts(rows: Iterable[Dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            counts[symbol] += 1
    return counts


def _position_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return row.get("position_snapshot") or {}


def _freshness_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return row.get("freshness_snapshot") or {}


def _is_features_fresh(row: Dict[str, Any]) -> bool:
    return _freshness_snapshot(row).get("features_fresh") is True


def _is_regime_fresh(row: Dict[str, Any]) -> bool:
    return _freshness_snapshot(row).get("regime_fresh") is True


def _is_portfolio_present_status(position_snapshot: Dict[str, Any]) -> bool:
    return position_snapshot.get("portfolio_snapshot_status") == "present"


def _is_portfolio_present_candidate(row: Dict[str, Any]) -> bool:
    position_snapshot = _position_snapshot(row)
    return _has_manage_lifecycle(position_snapshot) and _is_portfolio_present(position_snapshot)


def _optional_ts_ms(record: Dict[str, Any] | None) -> int | None:
    if record is None:
        return None
    ts_ms = _record_ts_ms(record)
    return ts_ms or None


def _first_matching_ts_ms(
    rows: Iterable[Dict[str, Any]],
    predicate,
) -> int | None:
    for row in rows:
        if predicate(row):
            return _optional_ts_ms(row)
    return None


def _row_brief(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if row is None:
        return None
    position_snapshot = _position_snapshot(row)
    return {
        "ts_ms": _optional_ts_ms(row),
        "event_type": row.get("event_type"),
        "trigger_event": row.get("trigger_event"),
        "suppression_reason": row.get("suppression_reason"),
        "manage_state": position_snapshot.get("manage_state"),
        "portfolio_snapshot_status": position_snapshot.get("portfolio_snapshot_status"),
        "portfolio_symbol_present": position_snapshot.get("portfolio_symbol_present"),
        "features_fresh": _is_features_fresh(row),
        "regime_fresh": _is_regime_fresh(row),
    }


def _blocker_reason_sequence(rows: Iterable[Dict[str, Any]]) -> List[str]:
    sequence: List[str] = []
    last_reason: str | None = None
    for row in rows:
        if row.get("event_type") != "POSITION_POLICY_SIDECAR_SUPPRESSED":
            continue
        reason = str(row.get("suppression_reason") or "UNKNOWN")
        if reason != last_reason:
            sequence.append(reason)
            last_reason = reason
    return sequence


def _fill_ingress_operator_verdict(
    *,
    had_slice_fill_ingress: bool,
    post_fill_rows: List[Dict[str, Any]],
    ever_portfolio_present_candidate_after_fill: bool,
    ever_evaluated_after_fill: bool,
    latest_post_fill_event_type: str | None,
) -> str | None:
    if not had_slice_fill_ingress:
        return None
    if not post_fill_rows:
        return "ambiguous_from_logs"
    if not ever_portfolio_present_candidate_after_fill:
        return "never_became_candidate"
    if not ever_evaluated_after_fill:
        return "became_candidate_but_never_evaluated"
    if latest_post_fill_event_type in {
        "POSITION_POLICY_SIDECAR_EVALUATED",
        "POSITION_POLICY_SIDECAR_RECOMMENDED",
    }:
        return "ambiguous_from_logs"
    return "evaluated_then_decayed"


def _transition_diagnosis(
    *,
    had_slice_fill_ingress: bool,
    post_fill_rows: List[Dict[str, Any]],
    ever_portfolio_present_after_fill: bool,
    ever_portfolio_symbol_present_true_after_fill: bool,
    ever_features_fresh_after_fill: bool,
    ever_regime_fresh_after_fill: bool,
    ever_portfolio_present_candidate_after_fill: bool,
    ever_evaluated_after_fill: bool,
    operator_verdict: str | None,
) -> str | None:
    if not had_slice_fill_ingress:
        return None
    if not post_fill_rows:
        return "no_policy_rows_after_fill"
    if not ever_portfolio_present_after_fill and not ever_portfolio_symbol_present_true_after_fill:
        return "portfolio_truth_never_became_present"
    if not ever_features_fresh_after_fill:
        return "features_never_became_fresh"
    if not ever_regime_fresh_after_fill:
        return "regime_never_became_fresh"
    if not ever_portfolio_present_candidate_after_fill:
        return "lifecycle_stayed_absent_or_ambiguous"
    if not ever_evaluated_after_fill:
        return "candidate_never_reached_evaluated"
    if operator_verdict == "evaluated_then_decayed":
        return "evaluated_then_decayed"
    return "ambiguous_from_logs"


def _build_symbol_transition_history(
    *,
    policy_rows: List[Dict[str, Any]],
    fill_ingress_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    policy_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    fill_rows_by_symbol: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in policy_rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol or symbol == "__DOMAIN__":
            continue
        policy_rows_by_symbol[symbol].append(row)

    for row in fill_ingress_rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        fill_rows_by_symbol[symbol].append(row)

    symbols = sorted(set(policy_rows_by_symbol.keys())
                     | set(fill_rows_by_symbol.keys()))
    histories: List[Dict[str, Any]] = []

    for symbol in symbols:
        symbol_policy_rows = sorted(
            policy_rows_by_symbol.get(symbol, []), key=_record_ts_ms)
        symbol_fill_rows = sorted(
            fill_rows_by_symbol.get(symbol, []), key=_record_ts_ms)
        latest_row = symbol_policy_rows[-1] if symbol_policy_rows else None
        latest_position_snapshot = _position_snapshot(
            latest_row) if latest_row is not None else {}

        fill_ingress_count = len(symbol_fill_rows)
        first_fill_ts_ms = _optional_ts_ms(
            symbol_fill_rows[0]) if symbol_fill_rows else None
        last_fill_ts_ms = _optional_ts_ms(
            symbol_fill_rows[-1]) if symbol_fill_rows else None
        post_fill_rows = (
            [row for row in symbol_policy_rows if _record_ts_ms(
                row) >= first_fill_ts_ms]
            if first_fill_ts_ms is not None
            else []
        )
        latest_post_fill_row = post_fill_rows[-1] if post_fill_rows else None
        first_policy_row_after_fill = post_fill_rows[0] if post_fill_rows else None
        first_blocker_row = next(
            (
                row
                for row in post_fill_rows
                if row.get("event_type") == "POSITION_POLICY_SIDECAR_SUPPRESSED"
            ),
            None,
        )

        latest_classification_bucket = (
            _classify_symbol_population(
                latest_row,
                fill_ingress_count=fill_ingress_count,
            )
            if latest_row is not None
            else "no_policy_rows_observed"
        )

        ever_portfolio_present = any(
            _is_portfolio_present_status(_position_snapshot(row))
            for row in symbol_policy_rows
        )
        ever_portfolio_symbol_present_true = any(
            _position_snapshot(row).get("portfolio_symbol_present") is True
            for row in symbol_policy_rows
        )
        ever_features_fresh = any(_is_features_fresh(row)
                                  for row in symbol_policy_rows)
        ever_regime_fresh = any(_is_regime_fresh(row)
                                for row in symbol_policy_rows)
        ever_evaluated = any(
            row.get("event_type") == "POSITION_POLICY_SIDECAR_EVALUATED"
            for row in symbol_policy_rows
        )
        ever_recommended = any(
            row.get("event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED"
            for row in symbol_policy_rows
        )

        ever_portfolio_present_after_fill = any(
            _is_portfolio_present_status(_position_snapshot(row))
            for row in post_fill_rows
        )
        ever_portfolio_symbol_present_true_after_fill = any(
            _position_snapshot(row).get("portfolio_symbol_present") is True
            for row in post_fill_rows
        )
        ever_portfolio_present_candidate_after_fill = any(
            _is_portfolio_present_candidate(row)
            for row in post_fill_rows
        )
        ever_features_fresh_after_fill = any(
            _is_features_fresh(row) for row in post_fill_rows)
        ever_regime_fresh_after_fill = any(
            _is_regime_fresh(row) for row in post_fill_rows)
        ever_evaluated_after_fill = any(
            row.get("event_type") == "POSITION_POLICY_SIDECAR_EVALUATED"
            for row in post_fill_rows
        )
        ever_recommended_after_fill = any(
            row.get("event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED"
            for row in post_fill_rows
        )

        blocker_reason_sequence = _blocker_reason_sequence(post_fill_rows)
        operator_verdict = _fill_ingress_operator_verdict(
            had_slice_fill_ingress=fill_ingress_count > 0,
            post_fill_rows=post_fill_rows,
            ever_portfolio_present_candidate_after_fill=ever_portfolio_present_candidate_after_fill,
            ever_evaluated_after_fill=ever_evaluated_after_fill,
            latest_post_fill_event_type=(
                latest_post_fill_row or {}).get("event_type"),
        )

        histories.append(
            {
                "symbol": symbol,
                "policy_row_count": len(symbol_policy_rows),
                "fill_ingress_count": fill_ingress_count,
                "had_slice_fill_ingress": fill_ingress_count > 0,
                "first_fill_ingress_ts_ms": first_fill_ts_ms,
                "last_fill_ingress_ts_ms": last_fill_ts_ms,
                "first_portfolio_present_ts_ms": _first_matching_ts_ms(
                    symbol_policy_rows,
                    lambda row: _is_portfolio_present_status(
                        _position_snapshot(row)),
                ),
                "first_portfolio_symbol_present_true_ts_ms": _first_matching_ts_ms(
                    symbol_policy_rows,
                    lambda row: _position_snapshot(row).get(
                        "portfolio_symbol_present") is True,
                ),
                "first_features_fresh_ts_ms": _first_matching_ts_ms(
                    symbol_policy_rows,
                    _is_features_fresh,
                ),
                "first_regime_fresh_ts_ms": _first_matching_ts_ms(
                    symbol_policy_rows,
                    _is_regime_fresh,
                ),
                "first_evaluated_ts_ms": _first_matching_ts_ms(
                    symbol_policy_rows,
                    lambda row: row.get(
                        "event_type") == "POSITION_POLICY_SIDECAR_EVALUATED",
                ),
                "first_recommended_ts_ms": _first_matching_ts_ms(
                    symbol_policy_rows,
                    lambda row: row.get(
                        "event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED",
                ),
                "latest_policy_row_ts_ms": _optional_ts_ms(latest_row),
                "ever_portfolio_present": ever_portfolio_present,
                "ever_portfolio_symbol_present_true": ever_portfolio_symbol_present_true,
                "ever_features_fresh": ever_features_fresh,
                "ever_regime_fresh": ever_regime_fresh,
                "ever_evaluated": ever_evaluated,
                "ever_recommended": ever_recommended,
                "ever_portfolio_present_after_fill": ever_portfolio_present_after_fill,
                "ever_portfolio_symbol_present_true_after_fill": ever_portfolio_symbol_present_true_after_fill,
                "ever_portfolio_present_candidate_after_fill": ever_portfolio_present_candidate_after_fill,
                "ever_features_fresh_after_fill": ever_features_fresh_after_fill,
                "ever_regime_fresh_after_fill": ever_regime_fresh_after_fill,
                "ever_evaluated_after_fill": ever_evaluated_after_fill,
                "ever_recommended_after_fill": ever_recommended_after_fill,
                "first_portfolio_present_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    lambda row: _is_portfolio_present_status(
                        _position_snapshot(row)),
                ),
                "first_portfolio_symbol_present_true_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    lambda row: _position_snapshot(row).get(
                        "portfolio_symbol_present") is True,
                ),
                "first_portfolio_present_candidate_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    _is_portfolio_present_candidate,
                ),
                "first_features_fresh_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    _is_features_fresh,
                ),
                "first_regime_fresh_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    _is_regime_fresh,
                ),
                "first_evaluated_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    lambda row: row.get(
                        "event_type") == "POSITION_POLICY_SIDECAR_EVALUATED",
                ),
                "first_recommended_after_fill_ts_ms": _first_matching_ts_ms(
                    post_fill_rows,
                    lambda row: row.get(
                        "event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED",
                ),
                "latest_event_type": (latest_row or {}).get("event_type"),
                "latest_trigger_event": (latest_row or {}).get("trigger_event"),
                "latest_suppression_reason": (latest_row or {}).get("suppression_reason"),
                "latest_manage_state": latest_position_snapshot.get("manage_state"),
                "latest_portfolio_snapshot_status": latest_position_snapshot.get("portfolio_snapshot_status"),
                "latest_portfolio_symbol_present": latest_position_snapshot.get("portfolio_symbol_present"),
                "latest_features_fresh": _is_features_fresh(latest_row) if latest_row is not None else False,
                "latest_regime_fresh": _is_regime_fresh(latest_row) if latest_row is not None else False,
                "latest_classification_bucket": latest_classification_bucket,
                "ended_symbol_absent": _is_symbol_absent(latest_position_snapshot) if latest_row is not None else False,
                "ended_in_no_manage_flow": latest_classification_bucket == "no_lifecycle_no_manage_flow",
                "ended_in_ambiguous_lifecycle_state": latest_classification_bucket == "ambiguous_lifecycle_state",
                "first_policy_row_after_fill_ingress": _row_brief(first_policy_row_after_fill),
                "first_blocker_after_fill": (first_blocker_row or {}).get("suppression_reason"),
                "first_blocker_after_fill_ts_ms": _optional_ts_ms(first_blocker_row),
                "blocker_reason_changed_after_fill": len(blocker_reason_sequence) > 1,
                "blocker_reason_progression_after_fill": blocker_reason_sequence,
                "ever_escaped_suppression_after_fill": any(
                    row.get("event_type") != "POSITION_POLICY_SIDECAR_SUPPRESSED"
                    for row in post_fill_rows
                ),
                "latest_blocker": (
                    (latest_post_fill_row or {}).get("suppression_reason")
                    if (latest_post_fill_row or {}).get("event_type") == "POSITION_POLICY_SIDECAR_SUPPRESSED"
                    else None
                ),
                "latest_observed_blocker_after_fill": (
                    blocker_reason_sequence[-1] if blocker_reason_sequence else None
                ),
                "operator_verdict": operator_verdict,
                "transition_diagnosis": _transition_diagnosis(
                    had_slice_fill_ingress=fill_ingress_count > 0,
                    post_fill_rows=post_fill_rows,
                    ever_portfolio_present_after_fill=ever_portfolio_present_after_fill,
                    ever_portfolio_symbol_present_true_after_fill=ever_portfolio_symbol_present_true_after_fill,
                    ever_features_fresh_after_fill=ever_features_fresh_after_fill,
                    ever_regime_fresh_after_fill=ever_regime_fresh_after_fill,
                    ever_portfolio_present_candidate_after_fill=ever_portfolio_present_candidate_after_fill,
                    ever_evaluated_after_fill=ever_evaluated_after_fill,
                    operator_verdict=operator_verdict,
                ),
            }
        )

    return histories


def _fill_ingress_symbol_transition_summary(
    symbol_transition_history: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        {
            "symbol": item["symbol"],
            "had_fill_ingress": item["had_slice_fill_ingress"],
            "ever_portfolio_present": item["ever_portfolio_present_after_fill"],
            "ever_features_fresh": item["ever_features_fresh_after_fill"],
            "ever_regime_fresh": item["ever_regime_fresh_after_fill"],
            "ever_evaluated": item["ever_evaluated_after_fill"],
            "latest_classification_bucket": item["latest_classification_bucket"],
            "first_blocker_after_fill": item["first_blocker_after_fill"],
            "latest_blocker": item["latest_blocker"],
            "operator_verdict": item["operator_verdict"],
        }
        for item in symbol_transition_history
        if item["had_slice_fill_ingress"]
    ]


def _has_manage_lifecycle(position_snapshot: Dict[str, Any]) -> bool:
    manage_state = position_snapshot.get("manage_state")
    return manage_state not in (None, "")


def _is_portfolio_present(position_snapshot: Dict[str, Any]) -> bool:
    return (
        position_snapshot.get("portfolio_snapshot_status") == "present"
        and position_snapshot.get("portfolio_symbol_present") is True
    )


def _is_symbol_absent(position_snapshot: Dict[str, Any]) -> bool:
    return (
        position_snapshot.get("portfolio_snapshot_status") == "symbol_absent"
        or position_snapshot.get("portfolio_symbol_present") is False
    )


def _classify_symbol_population(
    latest_row: Dict[str, Any],
    *,
    fill_ingress_count: int,
) -> str:
    position_snapshot = latest_row.get("position_snapshot") or {}
    has_manage_lifecycle = _has_manage_lifecycle(position_snapshot)
    portfolio_present = _is_portfolio_present(position_snapshot)
    symbol_absent = _is_symbol_absent(position_snapshot)

    if has_manage_lifecycle and portfolio_present and fill_ingress_count > 0:
        return "fresh_portfolio_present_candidates"
    if has_manage_lifecycle and portfolio_present:
        return "portfolio_present_without_slice_fill_evidence"
    if has_manage_lifecycle and symbol_absent:
        return "carried_local_lifecycle_symbol_absent"
    if not has_manage_lifecycle:
        return "no_lifecycle_no_manage_flow"
    return "ambiguous_lifecycle_state"


def _candidate_classification(
    *,
    policy_rows: List[Dict[str, Any]],
    fill_ingress_rows: List[Dict[str, Any]],
    symbol_transition_history: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    fill_ingress_counts = _symbol_fill_ingress_counts(fill_ingress_rows)
    population_members: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    population_suppressions: Dict[str, Counter] = defaultdict(Counter)
    symbol_to_population: Dict[str, str] = {}

    transition_history = symbol_transition_history or _build_symbol_transition_history(
        policy_rows=policy_rows,
        fill_ingress_rows=fill_ingress_rows,
    )

    for item in transition_history:
        symbol = item["symbol"]
        population = item["latest_classification_bucket"]
        if population == "no_policy_rows_observed":
            continue
        symbol_to_population[symbol] = population
        population_members[population].append(
            {
                "symbol": symbol,
                "latest_ts_ms": item["latest_policy_row_ts_ms"],
                "latest_event_type": item["latest_event_type"],
                "latest_trigger_event": item["latest_trigger_event"],
                "latest_suppression_reason": item["latest_suppression_reason"],
                "manage_state": item["latest_manage_state"],
                "portfolio_snapshot_status": item["latest_portfolio_snapshot_status"],
                "portfolio_symbol_present": item["latest_portfolio_symbol_present"],
                "fill_ingress_count": fill_ingress_counts.get(symbol, 0),
                "ever_portfolio_present_after_fill": item["ever_portfolio_present_after_fill"],
                "ever_portfolio_present_candidate_after_fill": item["ever_portfolio_present_candidate_after_fill"],
                "ever_evaluated_after_fill": item["ever_evaluated_after_fill"],
                "first_portfolio_present_after_fill_ts_ms": item["first_portfolio_present_after_fill_ts_ms"],
                "operator_verdict": item["operator_verdict"],
            }
        )

    for row in policy_rows:
        if row.get("event_type") != "POSITION_POLICY_SIDECAR_SUPPRESSED":
            continue
        symbol = str(row.get("symbol") or "").strip()
        population = symbol_to_population.get(symbol)
        if population is None:
            continue
        population_suppressions[population][row.get(
            "suppression_reason", "UNKNOWN")] += 1

    populations = (
        "fresh_portfolio_present_candidates",
        "portfolio_present_without_slice_fill_evidence",
        "carried_local_lifecycle_symbol_absent",
        "no_lifecycle_no_manage_flow",
        "ambiguous_lifecycle_state",
    )
    result: Dict[str, Any] = {}
    for population in populations:
        members = sorted(population_members.get(
            population, []), key=lambda item: item["symbol"])
        suppression_counts = population_suppressions.get(population, Counter())
        result[population] = {
            "symbol_count": len(members),
            "symbols": [member["symbol"] for member in members],
            "latest_symbol_rows": members,
            "suppression_count_by_reason": dict(suppression_counts),
            "dominant_suppression_reason": _top_counter_entry(suppression_counts),
        }
    return result


def _restart_slices(
    *,
    policy_rows: List[Dict[str, Any]],
    fill_ingress_rows: List[Dict[str, Any]],
    close_rows: List[Dict[str, Any]],
    overlap_window_ms: int,
    recommend_threshold: float | None,
) -> List[Dict[str, Any]]:
    mode_active_rows = sorted(
        (
            row
            for row in policy_rows
            if row.get("event_type") == "POSITION_POLICY_SIDECAR_MODE_ACTIVE"
        ),
        key=_record_ts_ms,
    )
    slices: List[Dict[str, Any]] = []

    for index, mode_active_row in enumerate(mode_active_rows, start=1):
        slice_start_ts_ms = _record_ts_ms(mode_active_row)
        next_slice_start_ts_ms = (
            _record_ts_ms(mode_active_rows[index])
            if index < len(mode_active_rows)
            else None
        )
        slice_policy_rows = [
            row
            for row in policy_rows
            if _record_ts_ms(row) >= slice_start_ts_ms
            and (next_slice_start_ts_ms is None or _record_ts_ms(row) < next_slice_start_ts_ms)
        ]
        slice_fill_ingress_rows = [
            row
            for row in fill_ingress_rows
            if _record_ts_ms(row) >= slice_start_ts_ms
            and (next_slice_start_ts_ms is None or _record_ts_ms(row) < next_slice_start_ts_ms)
        ]

        event_type_counts: Counter = Counter()
        trigger_event_counts: Counter = Counter()
        suppression_counts: Counter = Counter()
        by_symbol_event_type_counts: Dict[str, Counter] = defaultdict(Counter)

        for row in slice_policy_rows:
            event_type = row.get("event_type", "UNKNOWN")
            symbol = row.get("symbol", "__UNKNOWN__")
            event_type_counts[event_type] += 1
            by_symbol_event_type_counts[symbol][event_type] += 1

            trigger_event = str(row.get("trigger_event") or "").strip()
            if trigger_event:
                trigger_event_counts[trigger_event] += 1

            if event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
                suppression_counts[row.get(
                    "suppression_reason", "UNKNOWN")] += 1

        fill_ingress_counts = _symbol_fill_ingress_counts(
            slice_fill_ingress_rows)
        symbol_transition_history = _build_symbol_transition_history(
            policy_rows=slice_policy_rows,
            fill_ingress_rows=slice_fill_ingress_rows,
        )
        candidate_classification = _candidate_classification(
            policy_rows=slice_policy_rows,
            fill_ingress_rows=slice_fill_ingress_rows,
            symbol_transition_history=symbol_transition_history,
        )
        slice_recommendation_rows = [
            row
            for row in slice_policy_rows
            if row.get("event_type") == "POSITION_POLICY_SIDECAR_RECOMMENDED"
        ]
        slice_overlaps = _recommendation_overlaps(
            recommendation_rows=slice_recommendation_rows,
            close_rows=close_rows,
            overlap_window_ms=overlap_window_ms,
        )
        recommendation_truth = _recommendation_truth_summary(
            policy_rows=slice_policy_rows,
            recommend_threshold=recommend_threshold,
            matched_recommendations=len(slice_overlaps),
        )
        slices.append(
            {
                "slice_index": index,
                "start_ts_ms": slice_start_ts_ms,
                "end_ts_ms": next_slice_start_ts_ms,
                "policy_row_count": len(slice_policy_rows),
                "event_type_counts": dict(event_type_counts),
                "trigger_event_counts": dict(trigger_event_counts),
                "suppression_count_by_reason": dict(suppression_counts),
                "dominant_suppression_reason": _top_counter_entry(suppression_counts),
                "execution_fill_ingress": {
                    "count": len(slice_fill_ingress_rows),
                    "count_by_symbol": dict(fill_ingress_counts),
                    "symbols": sorted(fill_ingress_counts.keys()),
                    "has_any": len(slice_fill_ingress_rows) > 0,
                },
                "symbol_transition_history": symbol_transition_history,
                "fill_ingress_symbol_transition_summary": _fill_ingress_symbol_transition_summary(
                    symbol_transition_history,
                ),
                "candidate_classification": candidate_classification,
                "recommendation_truth": recommendation_truth,
                "by_symbol_event_type_counts": {
                    symbol: dict(counts) for symbol, counts in by_symbol_event_type_counts.items()
                },
            }
        )

    return slices


def _latest_slice_verdict(restart_slices: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not restart_slices:
        return {
            "slice_index": None,
            "slice_start_ts_ms": None,
            "slice_end_ts_ms": None,
            "has_fill_ingress_evidence": False,
            "has_fresh_fill_open_candidate_proof": False,
            "ever_portfolio_present_fill_candidate_count": 0,
            "fill_ingress_symbol_count": 0,
            "fill_ingress_transition_verdict": None,
            "fill_ingress_transition_verdict_counts": {},
            "fresh_portfolio_present_candidate_count": 0,
            "portfolio_present_without_slice_fill_evidence_count": 0,
            "carried_local_lifecycle_symbol_absent_count": 0,
            "no_lifecycle_no_manage_flow_count": 0,
            "reached_evaluated": False,
            "evaluated_count": 0,
            "recommendation_count": 0,
            "recommendation_truth_classification": None,
            "threshold_crossing_evaluated_count": 0,
            "max_evaluated_soft_close_pressure": None,
            "dominant_suppression_reason": None,
            "non_evaluation_category": "no_mode_active_slice",
            "non_evaluation_detail": "missing_mode_active_row",
        }

    latest_slice = restart_slices[-1]
    recommendation_truth = latest_slice.get("recommendation_truth", {})
    classification = latest_slice["candidate_classification"]
    fresh_candidate_count = classification["fresh_portfolio_present_candidates"]["symbol_count"]
    present_without_fill_count = classification["portfolio_present_without_slice_fill_evidence"]["symbol_count"]
    carried_symbol_absent_count = classification["carried_local_lifecycle_symbol_absent"]["symbol_count"]
    no_lifecycle_count = classification["no_lifecycle_no_manage_flow"]["symbol_count"]
    event_type_counts = latest_slice["event_type_counts"]
    fill_histories = [
        item
        for item in latest_slice.get("symbol_transition_history", [])
        if item.get("had_slice_fill_ingress")
    ]
    fill_transition_verdict_counts: Counter = Counter(
        item["operator_verdict"]
        for item in fill_histories
        if item.get("operator_verdict") is not None
    )
    ever_portfolio_present_fill_candidate_count = sum(
        1
        for item in fill_histories
        if item.get("ever_portfolio_present_candidate_after_fill")
    )
    evaluated_count = event_type_counts.get(
        "POSITION_POLICY_SIDECAR_EVALUATED", 0)
    reached_evaluated = evaluated_count > 0
    has_fill_ingress_evidence = latest_slice["execution_fill_ingress"]["has_any"]
    has_fresh_fill_candidate_proof = ever_portfolio_present_fill_candidate_count > 0

    fill_ingress_transition_verdict = None
    if fill_histories:
        if all(
            item.get("operator_verdict") == "ambiguous_from_logs"
            for item in fill_histories
        ):
            fill_ingress_transition_verdict = "ambiguous_from_logs"
        elif has_fresh_fill_candidate_proof:
            if fill_transition_verdict_counts.get("evaluated_then_decayed", 0) > 0:
                fill_ingress_transition_verdict = "candidate_existed_then_degraded"
            elif fill_transition_verdict_counts.get("became_candidate_but_never_evaluated", 0) > 0:
                fill_ingress_transition_verdict = "candidate_existed_but_never_evaluated"
            else:
                fill_ingress_transition_verdict = "ambiguous_from_logs"
        else:
            fill_ingress_transition_verdict = "no_portfolio_present_candidate_proven"

    non_evaluation_category = None
    non_evaluation_detail = None
    if not reached_evaluated:
        if fresh_candidate_count == 0 and present_without_fill_count == 0 and not has_fresh_fill_candidate_proof:
            non_evaluation_category = "no_fresh_candidate_evidence"
            if has_fill_ingress_evidence and fill_histories:
                if fill_ingress_transition_verdict == "ambiguous_from_logs":
                    non_evaluation_detail = "fill_ingress_transition_ambiguous_from_logs"
                else:
                    non_evaluation_detail = "fill_ingress_never_reached_portfolio_present_candidate"
            elif carried_symbol_absent_count > 0:
                non_evaluation_detail = "carried_local_lifecycle_symbol_absent_dominant"
            elif no_lifecycle_count > 0:
                non_evaluation_detail = "no_lifecycle_or_no_manage_flow_dominant"
            else:
                dominant_overall = latest_slice.get(
                    "dominant_suppression_reason")
                non_evaluation_detail = dominant_overall["reason"] if dominant_overall else None
        else:
            non_evaluation_category = "gating_blocker"
            blocking_reason = None
            for population in (
                "fresh_portfolio_present_candidates",
                "portfolio_present_without_slice_fill_evidence",
            ):
                dominant_population_reason = classification[population]["dominant_suppression_reason"]
                if dominant_population_reason is not None:
                    blocking_reason = dominant_population_reason["reason"]
                    break
            if blocking_reason is None:
                for item in fill_histories:
                    if item.get("first_blocker_after_fill") is not None:
                        blocking_reason = item["first_blocker_after_fill"]
                        break
            if blocking_reason is None:
                dominant_overall = latest_slice.get(
                    "dominant_suppression_reason")
                blocking_reason = dominant_overall["reason"] if dominant_overall else None
            non_evaluation_detail = blocking_reason

    return {
        "slice_index": latest_slice["slice_index"],
        "slice_start_ts_ms": latest_slice["start_ts_ms"],
        "slice_end_ts_ms": latest_slice["end_ts_ms"],
        "has_fill_ingress_evidence": has_fill_ingress_evidence,
        "has_fresh_fill_open_candidate_proof": has_fresh_fill_candidate_proof,
        "ever_portfolio_present_fill_candidate_count": ever_portfolio_present_fill_candidate_count,
        "fill_ingress_symbol_count": len(fill_histories),
        "fill_ingress_transition_verdict": fill_ingress_transition_verdict,
        "fill_ingress_transition_verdict_counts": dict(fill_transition_verdict_counts),
        "fresh_portfolio_present_candidate_count": fresh_candidate_count,
        "portfolio_present_without_slice_fill_evidence_count": present_without_fill_count,
        "carried_local_lifecycle_symbol_absent_count": carried_symbol_absent_count,
        "no_lifecycle_no_manage_flow_count": no_lifecycle_count,
        "reached_evaluated": reached_evaluated,
        "evaluated_count": evaluated_count,
        "recommendation_count": event_type_counts.get("POSITION_POLICY_SIDECAR_RECOMMENDED", 0),
        "recommendation_truth_classification": recommendation_truth.get("classification"),
        "threshold_crossing_evaluated_count": recommendation_truth.get("threshold_crossing_evaluated_count", 0),
        "max_evaluated_soft_close_pressure": recommendation_truth.get("max_evaluated_soft_close_pressure"),
        "dominant_suppression_reason": latest_slice.get("dominant_suppression_reason"),
        "non_evaluation_category": non_evaluation_category,
        "non_evaluation_detail": non_evaluation_detail,
    }


def _ingress_event_counts(rows: Iterable[Dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for record in rows:
        raw_name = str(
            record.get("verb")
            or record.get("event_type")
            or record.get("event")
            or record.get("type")
            or ""
        ).strip()
        normalized = raw_name[4:] if raw_name.startswith("EVT:") else raw_name
        if normalized in INGRESS_EVENT_NAMES:
            counts[normalized] += 1
    return counts


def _close_rows(order_log_path: Path, trade_lifecycle_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in _load_jsonl(order_log_path):
        event_type = record.get("event_type")
        if event_type in {"ORDER_FILLED", "ORDER_REJECTED", "ORDER_STATE_CHANGED"}:
            rows.append(
                {
                    "source": "order_log",
                    "event_type": event_type,
                    "symbol": record.get("symbol"),
                    "ts_ms": record.get("timestamp") or record.get("ts_ms") or 0,
                    "rid": record.get("rid"),
                }
            )
    for record in iter_trade_lifecycle_records(log_file=str(trade_lifecycle_path)):
        rows.append(
            {
                "source": "trade_lifecycle",
                "event_type": record.get("status") or record.get("event_type"),
                "symbol": record.get("symbol"),
                "ts_ms": record.get("close_ts_ms") or record.get("updated_ts_ms") or 0,
                "rid": record.get("rid"),
            }
        )
    return rows


def _recommendation_overlaps(
    *,
    recommendation_rows: Iterable[Dict[str, Any]],
    close_rows: List[Dict[str, Any]],
    overlap_window_ms: int,
) -> List[Dict[str, Any]]:
    overlaps: List[Dict[str, Any]] = []
    for row in recommendation_rows:
        row_ts = int(row.get("ts_ms") or 0)
        row_symbol = row.get("symbol")
        candidate_closes = [
            close
            for close in close_rows
            if close.get("symbol") == row_symbol
            and abs(int(close.get("ts_ms") or 0) - row_ts) <= overlap_window_ms
        ]
        if not candidate_closes:
            continue
        closest = min(
            candidate_closes,
            key=lambda close: abs(int(close.get("ts_ms") or 0) - row_ts),
        )
        overlaps.append(
            {
                "trace_id": row.get("trace_id"),
                "symbol": row_symbol,
                "recommendation_ts_ms": row_ts,
                "close_source": closest["source"],
                "close_event_type": closest["event_type"],
                "close_ts_ms": closest["ts_ms"],
                "delta_ms": int(closest["ts_ms"] or 0) - row_ts,
            }
        )
    return overlaps


def _recommendation_truth_summary(
    *,
    policy_rows: Iterable[Dict[str, Any]],
    recommend_threshold: float | None,
    matched_recommendations: int | None,
) -> Dict[str, Any]:
    evaluated_with_scores_count = 0
    evaluated_rows = []
    recommended_rows = []
    threshold_crossings = []
    by_symbol: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "evaluated_count": 0,
            "recommended_count": 0,
            "threshold_crossing_evaluated_count": 0,
            "max_evaluated_soft_close_pressure": None,
            "max_evaluated_sample": None,
        }
    )

    for row in policy_rows:
        event_type = row.get("event_type")
        if event_type == "POSITION_POLICY_SIDECAR_EVALUATED":
            evaluated_rows.append(row)
        elif event_type == "POSITION_POLICY_SIDECAR_RECOMMENDED":
            recommended_rows.append(row)

    recommended_identities = {_row_identity(row) for row in recommended_rows}

    max_pressure = None
    max_pressure_sample = None
    for row in evaluated_rows:
        pressure = _soft_close_pressure(row)
        if pressure is None:
            continue

        evaluated_with_scores_count += 1
        symbol = str(row.get("symbol") or "__UNKNOWN__")
        by_symbol_entry = by_symbol[symbol]
        by_symbol_entry["evaluated_count"] += 1

        sample = {
            "symbol": symbol,
            "ts_ms": _record_ts_ms(row),
            "trace_id": row.get("trace_id"),
            "trigger_event": row.get("trigger_event"),
            "soft_close_pressure": pressure,
        }
        current_symbol_max = by_symbol_entry["max_evaluated_soft_close_pressure"]
        if current_symbol_max is None or pressure > current_symbol_max:
            by_symbol_entry["max_evaluated_soft_close_pressure"] = pressure
            by_symbol_entry["max_evaluated_sample"] = sample

        if max_pressure is None or pressure > max_pressure:
            max_pressure = pressure
            max_pressure_sample = sample

        if recommend_threshold is not None and pressure >= recommend_threshold:
            threshold_crossings.append(sample)
            by_symbol_entry["threshold_crossing_evaluated_count"] += 1

    for row in recommended_rows:
        symbol = str(row.get("symbol") or "__UNKNOWN__")
        by_symbol[symbol]["recommended_count"] += 1

    missing_recommendation_after_threshold_crossing = [
        item
        for item in threshold_crossings
        if _row_identity(
            {
                "trace_id": item.get("trace_id"),
                "symbol": item.get("symbol"),
                "ts_ms": item.get("ts_ms"),
                "event_type": "POSITION_POLICY_SIDECAR_EVALUATED",
            }
        )
        not in recommended_identities
    ]

    recommendation_count = len(recommended_rows)
    threshold_crossing_count = len(threshold_crossings)
    missing_recommendation_count = len(
        missing_recommendation_after_threshold_crossing)
    unmatched_recommendation_count = None
    if matched_recommendations is not None:
        unmatched_recommendation_count = max(
            recommendation_count - matched_recommendations,
            0,
        )

    if recommend_threshold is None:
        classification = "unknown_missing_threshold_config"
    elif evaluated_with_scores_count == 0:
        classification = "no_evaluated_rows"
    elif threshold_crossing_count == 0:
        if recommendation_count == 0:
            classification = "truthful_threshold_non_attainment"
        else:
            classification = "inconsistent_recommendation_without_threshold_crossing"
    elif missing_recommendation_count > 0 or recommendation_count == 0:
        classification = "recommendation_emission_gap"
    elif matched_recommendations is None:
        classification = "recommendations_observed"
    elif matched_recommendations == 0:
        classification = "recommendations_unmatched"
    elif matched_recommendations < recommendation_count:
        classification = "recommendations_partially_matched"
    else:
        classification = "recommendations_matched"

    return {
        "recommend_threshold": recommend_threshold,
        "classification": classification,
        "evaluated_with_score_count": evaluated_with_scores_count,
        "recommendation_count": recommendation_count,
        "threshold_crossing_evaluated_count": threshold_crossing_count,
        "matched_recommendations": matched_recommendations,
        "unmatched_recommendation_count": unmatched_recommendation_count,
        "missing_recommendation_after_threshold_crossing_count": missing_recommendation_count,
        "max_evaluated_soft_close_pressure": max_pressure,
        "max_evaluated_soft_close_pressure_sample": max_pressure_sample,
        "threshold_crossing_samples": threshold_crossings[:20],
        "missing_recommendation_after_threshold_crossing_samples": missing_recommendation_after_threshold_crossing[:20],
        "truthful_zero_recommendation": (
            classification == "truthful_threshold_non_attainment"
            and recommendation_count == 0
        ),
        "by_symbol": {
            symbol: by_symbol[symbol]
            for symbol in sorted(by_symbol.keys())
        },
    }


def build_report(
    *,
    wal_glob: str,
    order_log_path: Path,
    trade_lifecycle_path: Path,
    overlap_window_ms: int,
    recommend_threshold: float | None = None,
    domains_config_path: Path = DEFAULT_DOMAINS_CONFIG,
) -> Dict[str, Any]:
    wal_files = [Path(path) for path in glob.glob(wal_glob)]
    wal_event_count = 0
    wal_ingress_counts: Counter = Counter()
    for wal_file in wal_files:
        wal_rows = list(_load_jsonl(wal_file))
        wal_event_count += len(wal_rows)
        wal_ingress_counts.update(_ingress_event_counts(wal_rows))

    policy_rows = _policy_rows(trade_lifecycle_path)
    fill_ingress_rows = _fill_ingress_rows(trade_lifecycle_path)
    close_rows = _close_rows(order_log_path, trade_lifecycle_path)
    if recommend_threshold is None:
        recommend_threshold = _load_recommend_threshold(domains_config_path)

    suppression_counts = Counter()
    event_type_counts = Counter()
    trigger_event_counts = Counter()
    explainable_rows = 0
    recommendations = []
    by_symbol = defaultdict(Counter)

    for row in policy_rows:
        event_type = row.get("event_type", "UNKNOWN")
        symbol = row.get("symbol", "__UNKNOWN__")
        event_type_counts[event_type] += 1
        by_symbol[symbol][event_type] += 1
        trigger_event = str(row.get("trigger_event") or "").strip()
        if trigger_event:
            trigger_event_counts[trigger_event] += 1

        if row.get("trace_id") and row.get("reason_codes") is not None and row.get("freshness_snapshot") is not None:
            explainable_rows += 1

        if event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
            suppression_counts[row.get("suppression_reason", "UNKNOWN")] += 1

        if event_type == "POSITION_POLICY_SIDECAR_RECOMMENDED":
            recommendations.append(row)

    overlaps = _recommendation_overlaps(
        recommendation_rows=recommendations,
        close_rows=close_rows,
        overlap_window_ms=overlap_window_ms,
    )
    recommendation_truth = _recommendation_truth_summary(
        policy_rows=policy_rows,
        recommend_threshold=recommend_threshold,
        matched_recommendations=len(overlaps),
    )

    timing_deltas = [item["delta_ms"] for item in overlaps]
    mode_active_count = event_type_counts.get(
        "POSITION_POLICY_SIDECAR_MODE_ACTIVE", 0)
    restart_slices = _restart_slices(
        policy_rows=policy_rows,
        fill_ingress_rows=fill_ingress_rows,
        close_rows=close_rows,
        overlap_window_ms=overlap_window_ms,
        recommend_threshold=recommend_threshold,
    )
    latest_fill_ingress_summary = (
        restart_slices[-1]["fill_ingress_symbol_transition_summary"]
        if restart_slices
        else []
    )
    return {
        "wal": {
            "glob": wal_glob,
            "files_scanned": len(wal_files),
            "event_count": wal_event_count,
            "ingress_event_counts": {
                event_name: wal_ingress_counts.get(event_name, 0)
                for event_name in INGRESS_EVENT_NAMES
            },
        },
        "aggregate_summary": {
            "policy_row_count": len(policy_rows),
            "fill_ingress_row_count": len(fill_ingress_rows),
            "event_type_counts": dict(event_type_counts),
            "observed_trigger_event_counts": dict(trigger_event_counts),
            "suppression_count_by_reason": dict(suppression_counts),
            "recommendation_count": event_type_counts.get("POSITION_POLICY_SIDECAR_RECOMMENDED", 0),
            "action_skipped_count": event_type_counts.get("POSITION_POLICY_SIDECAR_ACTION_SKIPPED", 0),
            "mode_active_count": mode_active_count,
            "recommendation_truth_classification": recommendation_truth["classification"],
            "threshold_crossing_evaluated_count": recommendation_truth["threshold_crossing_evaluated_count"],
            "max_evaluated_soft_close_pressure": recommendation_truth["max_evaluated_soft_close_pressure"],
        },
        "policy_rows": {
            "total": len(policy_rows),
            "event_type_counts": dict(event_type_counts),
            "observed_trigger_event_counts": dict(trigger_event_counts),
            "suppression_count_by_reason": dict(suppression_counts),
            "recommendation_count": event_type_counts.get("POSITION_POLICY_SIDECAR_RECOMMENDED", 0),
            "action_skipped_count": event_type_counts.get("POSITION_POLICY_SIDECAR_ACTION_SKIPPED", 0),
            "scores_count": event_type_counts.get("POSITION_POLICY_SIDECAR_SCORES", 0),
            "evaluated_count": event_type_counts.get("POSITION_POLICY_SIDECAR_EVALUATED", 0),
            "fill_ingress_count": len(fill_ingress_rows),
            "explainability_completeness": (
                explainable_rows / len(policy_rows) if policy_rows else 0.0
            ),
        },
        "overlap": {
            "window_ms": overlap_window_ms,
            "matched_recommendations": len(overlaps),
            "mean_delta_ms": mean(timing_deltas) if timing_deltas else None,
            "samples": overlaps[:20],
        },
        "recommendation_truth": recommendation_truth,
        "bootstrap": {
            "mode_active_count": mode_active_count,
            "mode_active_present": mode_active_count > 0,
            "signal": None if mode_active_count > 0 else "missing_mode_active_row",
        },
        "restart_slices": restart_slices,
        "latest_slice_verdict": _latest_slice_verdict(restart_slices),
        "fill_ingress_symbol_transition_summary": latest_fill_ingress_summary,
        "remaining_blind_spots": [
            "Symbols with execution_fill_ingress but no subsequent Sidecar policy row remain ambiguous from current logs.",
            "Milestone flags are derived only from Sidecar rows; the validator cannot prove intermediate truth changes that were never emitted as Sidecar rows.",
        ],
        "slices": {
            "by_symbol": {symbol: dict(counts) for symbol, counts in by_symbol.items()},
        },
        "paths": {
            "order_log": str(order_log_path),
            "order_log_exists": order_log_path.exists(),
            "trade_lifecycle": str(trade_lifecycle_path),
            "trade_lifecycle_exists": trade_lifecycle_path.exists(),
            "domains_config": str(domains_config_path),
            "domains_config_exists": domains_config_path.exists(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Position Policy Sidecar shadow outputs.")
    parser.add_argument("--wal-glob", default=DEFAULT_WAL_GLOB)
    parser.add_argument("--order-log", default=DEFAULT_ORDER_LOG)
    parser.add_argument("--trade-lifecycle", default=DEFAULT_TRADE_LIFECYCLE)
    parser.add_argument("--overlap-window-ms", type=int,
                        default=15 * 60 * 1000)
    parser.add_argument("--recommend-threshold", type=float, default=None)
    parser.add_argument("--domains-config",
                        default=str(DEFAULT_DOMAINS_CONFIG))
    parser.add_argument(
        "--output-json", default="artifacts/position_policy_sidecar/package4_validation_summary.json")
    args = parser.parse_args()

    report = build_report(
        wal_glob=args.wal_glob,
        order_log_path=Path(args.order_log),
        trade_lifecycle_path=Path(args.trade_lifecycle),
        overlap_window_ms=args.overlap_window_ms,
        recommend_threshold=args.recommend_threshold,
        domains_config_path=Path(args.domains_config),
    )

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
