#!/usr/bin/env python3
"""Economic PnL layer for reports/order_log_counterfactual_replay.

This script is intentionally narrow. It consumes the existing replay outputs,
adds a small economic layer on top, and writes deterministic row-level and
summary artifacts without rerunning the broad normalization pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "reports" / "order_log_counterfactual_replay"

SOURCE_ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
SOURCE_PROPOSAL_CASEBOOK = REPORT_ROOT / "proposal_casebook.jsonl"
SOURCE_PROPOSALS_NORMALIZED = REPORT_ROOT / "normalized_rows.jsonl"
SOURCE_EVIDENCE_MATRIX = REPORT_ROOT / "evidence_join_matrix.csv"
SOURCE_ACTUAL_RUNTIME_CASEBOOK = REPORT_ROOT / "actual_runtime_casebook.jsonl"

OUTPUT_REPLAYED_OUTCOMES = REPORT_ROOT / "replayed_outcomes.jsonl"
OUTPUT_PROPOSALS_NORMALIZED = REPORT_ROOT / "proposals_normalized.jsonl"
OUTPUT_ECONOMIC_OUTCOMES = REPORT_ROOT / "economic_outcomes.jsonl"
OUTPUT_ECONOMIC_OUTCOMES_CSV = REPORT_ROOT / "economic_outcomes.csv"
OUTPUT_FIELD_COVERAGE = REPORT_ROOT / "economic_field_coverage.json"
OUTPUT_SUMMARY_BY_SYMBOL = REPORT_ROOT / "economic_summary_by_symbol.csv"
OUTPUT_SUMMARY_BY_STRATEGY = REPORT_ROOT / "economic_summary_by_strategy.csv"
OUTPUT_SUMMARY_BY_REGIME = REPORT_ROOT / "economic_summary_by_regime.csv"
OUTPUT_SUMMARY_BY_REJECT_REASON = REPORT_ROOT / "economic_summary_by_reject_reason.csv"
OUTPUT_SUMMARY_BY_EVIDENCE_CLASS = REPORT_ROOT / "economic_summary_by_evidence_class.csv"
OUTPUT_REPORT = REPORT_ROOT / "ORDER_LOG_COUNTERFACTUAL_ECONOMIC_PNL_LAYER_REPORT.md"

TIMEOUT_LIKE_CLOSE_REASONS = {"ENTRY_TIMEOUT_OR_STALE", "OBSERVATION_END"}


@dataclass(frozen=True)
class CostProfile:
    open_fee_bps: float | None
    close_fee_bps: float | None
    slippage_bps: float | None
    notional_size: float | None = None
    source: str = ""


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    return loaded or {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True, default=json_default))
            handle.write("\n")


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=json_default)
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_side(value: Any) -> str:
    side = as_text(value).strip().upper()
    if side in {"BUY", "SELL"}:
        return side
    return ""


def is_positive_price(value: Any) -> bool:
    number = as_float(value)
    return number is not None and number > 0.0


def clean_number(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def find_first_value(node: Any, key_names: Iterable[str]) -> Any:
    keys = tuple(key_names)
    if isinstance(node, dict):
        for key in keys:
            if key in node and node[key] not in (None, ""):
                return node[key]
        for child in node.values():
            found = find_first_value(child, keys)
            if found not in (None, ""):
                return found
    elif isinstance(node, list):
        for child in node:
            found = find_first_value(child, keys)
            if found not in (None, ""):
                return found
    return None


def find_first_dict_with_keys(node: Any, required_keys: set[str]) -> dict[str, Any] | None:
    if isinstance(node, dict):
        if required_keys.issubset(node.keys()):
            return node
        for child in node.values():
            found = find_first_dict_with_keys(child, required_keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node:
            found = find_first_dict_with_keys(child, required_keys)
            if found is not None:
                return found
    return None


def looks_like_symbol(value: str) -> bool:
    upper = value.upper()
    return upper.endswith(("USDT", "USD")) and any(character.isalpha() for character in upper)


def collect_target_leverages(node: Any, path: tuple[str, ...] = ()) -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(node, dict):
        if "target_leverage" in node:
            symbol = next((part for part in reversed(path) if looks_like_symbol(part)), None)
            if symbol is not None:
                leverage = as_float(node.get("target_leverage"))
                if leverage is not None:
                    result[symbol.upper()] = leverage
        for key, child in node.items():
            result.update(collect_target_leverages(child, path + (as_text(key),)))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            result.update(collect_target_leverages(child, path + (str(index),)))
    return result


def load_cost_profiles() -> tuple[CostProfile, dict[str, CostProfile]]:
    domains = load_yaml(ROOT / "config" / "aurora" / "domains.yaml")
    aurora_strategy = load_yaml(ROOT / "config" / "aurora" / "strategies" / "aurora.yaml")
    md_amr = load_yaml(ROOT / "config" / "aurora" / "strategies" / "md_amr.yaml")
    mean_reversion = load_yaml(ROOT / "config" / "aurora" / "strategies" / "mean_reversion.yaml")
    alpha_search = load_yaml(ROOT / "config" / "alpha_search.yaml")

    fee_block = find_first_dict_with_keys(domains, {"open_fee_bps", "close_fee_bps"})
    slippage_block = find_first_dict_with_keys(domains, {"buffer_bps"})
    default_profile = CostProfile(
        open_fee_bps=as_float(fee_block.get("open_fee_bps")) if fee_block else None,
        close_fee_bps=as_float(fee_block.get("close_fee_bps")) if fee_block else None,
        slippage_bps=as_float(slippage_block.get("buffer_bps")) if slippage_block else None,
        source="config/aurora/domains.yaml",
    )

    strategy_profiles: dict[str, CostProfile] = {
        "aurora": default_profile,
        "mean_reversion": default_profile,
    }

    md_fee_bps = as_float(find_first_value(md_amr, ("fee_bps",)))
    md_slippage_bps = as_float(find_first_value(md_amr, ("slippage_buffer_bps",)))
    if md_fee_bps is not None or md_slippage_bps is not None:
        strategy_profiles["md_amr"] = CostProfile(
            open_fee_bps=md_fee_bps,
            close_fee_bps=md_fee_bps,
            slippage_bps=md_slippage_bps,
            source="config/aurora/strategies/md_amr.yaml",
        )

    alpha_fee_bps = as_float(find_first_value(alpha_search, ("fees_bps", "fee_bps")))
    alpha_slippage_bps = as_float(find_first_value(alpha_search, ("slippage_bps",)))
    alpha_notional_size = as_float(find_first_value(alpha_search, ("notional_size",)))
    if alpha_fee_bps is not None or alpha_slippage_bps is not None or alpha_notional_size is not None:
        strategy_profiles["alpha_search"] = CostProfile(
            open_fee_bps=alpha_fee_bps,
            close_fee_bps=alpha_fee_bps,
            slippage_bps=alpha_slippage_bps,
            notional_size=alpha_notional_size,
            source="config/alpha_search.yaml",
        )

    _ = aurora_strategy
    _ = mean_reversion
    return default_profile, strategy_profiles


def load_symbol_leverage_map() -> dict[str, float]:
    instruments = load_yaml(ROOT / "config" / "aurora" / "instruments.yaml")
    symbol_leverages = collect_target_leverages(instruments)
    return {symbol.upper(): leverage for symbol, leverage in symbol_leverages.items()}


def read_source_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]], int]:
    proposal_rows = load_jsonl(SOURCE_PROPOSAL_CASEBOOK)
    normalized_rows = load_jsonl(SOURCE_PROPOSALS_NORMALIZED)
    evidence_rows = load_csv(SOURCE_EVIDENCE_MATRIX)
    actual_runtime_rows = load_jsonl(SOURCE_ACTUAL_RUNTIME_CASEBOOK) if SOURCE_ACTUAL_RUNTIME_CASEBOOK.exists() else []

    raw_order_log_rows = 0
    if SOURCE_ORDER_LOG.exists():
        with SOURCE_ORDER_LOG.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    raw_order_log_rows += 1

    return proposal_rows, normalized_rows, evidence_rows, actual_runtime_rows, raw_order_log_rows


def build_indexes(normalized_rows: list[dict[str, Any]], evidence_rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, int], dict[str, Any]], dict[str, dict[str, str]]]:
    normalized_by_uid: dict[str, dict[str, Any]] = {}
    normalized_by_source_line: dict[tuple[str, int], dict[str, Any]] = {}
    for row in normalized_rows:
        if as_text(row.get("row_kind")) != "proposal":
            continue
        proposal_uid = as_text(row.get("proposal_uid"))
        if proposal_uid:
            normalized_by_uid[proposal_uid] = row
        source_file = as_text(row.get("source_file"))
        source_line = as_int(row.get("source_line"))
        if source_file and source_line is not None:
            normalized_by_source_line[(source_file, source_line)] = row

    evidence_by_uid: dict[str, dict[str, str]] = {}
    for row in evidence_rows:
        proposal_uid = as_text(row.get("proposal_uid"))
        if proposal_uid:
            evidence_by_uid[proposal_uid] = row

    return normalized_by_uid, normalized_by_source_line, evidence_by_uid


def derive_proposal_metadata(
    proposal_row: dict[str, Any],
    normalized_row: dict[str, Any] | None,
    evidence_row: dict[str, str] | None,
    default_profile: CostProfile,
    strategy_profiles: dict[str, CostProfile],
    symbol_leverages: dict[str, float],
) -> dict[str, Any]:
    strategy = as_text(first_present(
        normalized_row.get("strategy_id") if normalized_row else None,
        proposal_row.get("strategy_id"),
        proposal_row.get("strategy"),
        "aurora",
    )).strip() or "aurora"
    strategy = strategy.lower()

    cost_profile = strategy_profiles.get(strategy, default_profile)
    if cost_profile.open_fee_bps is None or cost_profile.close_fee_bps is None or cost_profile.slippage_bps is None:
        cost_profile = default_profile

    symbol = as_text(first_present(
        normalized_row.get("symbol") if normalized_row else None,
        evidence_row.get("symbol") if evidence_row else None,
        proposal_row.get("symbol"),
    )).upper()
    side = normalize_side(first_present(
        normalized_row.get("side") if normalized_row else None,
        proposal_row.get("side"),
        evidence_row.get("side") if evidence_row else None,
    ))
    row_role = as_text(first_present(
        normalized_row.get("row_role") if normalized_row else None,
        proposal_row.get("row_role"),
        evidence_row.get("row_role") if evidence_row else None,
    ))
    analysis_class = as_text(first_present(
        normalized_row.get("analysis_class") if normalized_row else None,
        proposal_row.get("analysis_class"),
        evidence_row.get("analysis_class") if evidence_row else None,
    ))
    join_quality = as_text(first_present(
        evidence_row.get("join_quality") if evidence_row else None,
        proposal_row.get("join_quality"),
    ))
    support_quality = as_text(first_present(
        evidence_row.get("support_quality") if evidence_row else None,
        proposal_row.get("support_quality"),
    ))
    reject_reason = as_text(first_present(
        normalized_row.get("reject_reason") if normalized_row else None,
        proposal_row.get("reject_reason"),
        proposal_row.get("deny_reason"),
    ))
    nrr_code = as_text(first_present(
        normalized_row.get("nrr_code") if normalized_row else None,
        proposal_row.get("nrr_code"),
    ))
    gate_verdict = as_text(first_present(
        normalized_row.get("threshold_verdict") if normalized_row else None,
        proposal_row.get("threshold_verdict"),
    ))
    gate_reason = as_text(first_present(
        normalized_row.get("threshold_reason") if normalized_row else None,
        proposal_row.get("threshold_reason"),
    ))

    entry_price = as_float(first_present(
        proposal_row.get("effective_entry_price"),
        proposal_row.get("entry_price"),
    ))
    close_price = as_float(first_present(
        proposal_row.get("close_price_primary"),
        proposal_row.get("close_price_secondary"),
        proposal_row.get("close_price"),
    ))
    entry_ts_ms = as_int(first_present(
        proposal_row.get("timestamp_ms"),
        normalized_row.get("timestamp_ms") if normalized_row else None,
    ))
    close_ts_ms = as_int(first_present(
        proposal_row.get("close_ts_primary"),
        proposal_row.get("close_ts_secondary"),
        proposal_row.get("close_ts"),
    ))
    close_reason = as_text(first_present(
        proposal_row.get("close_reason_primary"),
        proposal_row.get("close_reason_secondary"),
        proposal_row.get("close_reason"),
        proposal_row.get("actual_close_reason"),
    ))

    original_quantity = as_float(proposal_row.get("quantity"))
    if original_quantity is not None and original_quantity < 0:
        original_quantity = abs(original_quantity)

    explicit_notional = as_float(first_present(
        proposal_row.get("notional"),
        proposal_row.get("modeled_notional_usdt"),
        proposal_row.get("explicit_notional_usdt"),
        cost_profile.notional_size if strategy == "alpha_search" else None,
    ))

    leverage = symbol_leverages.get(symbol)
    if leverage is None and normalized_row is not None:
        leverage = as_float(normalized_row.get("target_leverage"))

    actual_qty_used = original_quantity is not None and original_quantity > 0
    modeled_notional_used = False
    qty_source = "missing"
    notional_source = "missing"
    quantity = original_quantity

    if actual_qty_used:
        qty_source = "row_quantity"
    elif explicit_notional is not None and entry_price is not None and entry_price > 0 and close_price is not None and close_price > 0:
        quantity = explicit_notional / entry_price
        modeled_notional_used = True
        qty_source = "derived_from_notional"
        notional_source = "explicit_config_diagnostic_notional"

    if actual_qty_used:
        open_notional = quantity * entry_price if quantity is not None and entry_price is not None else None
        notional_source = "row_quantity_x_entry_price" if open_notional is not None else "missing"
    elif modeled_notional_used and explicit_notional is not None:
        open_notional = explicit_notional
    else:
        open_notional = None

    close_notional = quantity * close_price if quantity is not None and close_price is not None else None
    margin_quote = open_notional / leverage if open_notional is not None and leverage not in (None, 0) else None

    open_fee_bps = cost_profile.open_fee_bps
    close_fee_bps = cost_profile.close_fee_bps
    slippage_bps = cost_profile.slippage_bps
    round_trip_fee_bps = open_fee_bps + close_fee_bps if open_fee_bps is not None and close_fee_bps is not None else None
    round_trip_cost_bps = round_trip_fee_bps + slippage_bps if round_trip_fee_bps is not None and slippage_bps is not None else None

    price_support = is_positive_price(entry_price) and is_positive_price(close_price)
    pnl_ready = side in {"BUY", "SELL"} and quantity is not None and quantity > 0 and price_support

    if row_role == "decision_reject":
        if analysis_class == "FORCED_OPEN_SIGNAL_DIAGNOSTIC":
            evidence_class = "FORCED_OPEN_DIAGNOSTIC"
        elif pnl_ready:
            evidence_class = "EXECUTION_FEASIBLE"
        else:
            evidence_class = "INDETERMINATE_LOW_SUPPORT"
    elif row_role == "reservation_intent":
        evidence_class = "RESERVATION_ONLY"
    elif pnl_ready:
        evidence_class = "EXECUTION_FEASIBLE"
    else:
        evidence_class = "INDETERMINATE_LOW_SUPPORT"

    if side == "":
        pnl_status = "PNL_UNREPLAYABLE_MISSING_SIDE"
    elif not is_positive_price(entry_price) or not is_positive_price(close_price):
        pnl_status = "PNL_UNREPLAYABLE_MISSING_PRICE"
    elif quantity is None or quantity <= 0:
        pnl_status = "PNL_MODELED_NOTIONAL_REQUIRED"
    else:
        pnl_status = "OK"

    pnl_mode = "UNREPLAYABLE"
    if pnl_ready and evidence_class == "EXECUTION_FEASIBLE":
        pnl_mode = "EXECUTION_FEASIBLE_MODELED_PNL"
    elif evidence_class == "FORCED_OPEN_DIAGNOSTIC":
        pnl_mode = "FORCED_OPEN_DIAGNOSTIC_PNL"

    gross_pnl_quote = None
    net_pnl_quote = None
    total_fees_quote = None
    total_slippage_quote = None
    gross_return_on_notional_pct = None
    net_return_on_notional_pct = None
    gross_return_on_margin_pct = None
    net_return_on_margin_pct = None

    if pnl_status == "OK" and pnl_ready:
        if side == "BUY":
            gross_pnl_quote = quantity * (close_price - entry_price)
        elif side == "SELL":
            gross_pnl_quote = quantity * (entry_price - close_price)

        open_fee_quote = open_notional * open_fee_bps / 10000.0 if open_notional is not None and open_fee_bps is not None else None
        close_fee_quote = close_notional * close_fee_bps / 10000.0 if close_notional is not None and close_fee_bps is not None else None
        slippage_quote = open_notional * slippage_bps / 10000.0 if open_notional is not None and slippage_bps is not None else None

        total_fees_quote = None if open_fee_quote is None or close_fee_quote is None else open_fee_quote + close_fee_quote
        total_slippage_quote = slippage_quote
        if gross_pnl_quote is not None and total_fees_quote is not None and total_slippage_quote is not None:
            net_pnl_quote = gross_pnl_quote - total_fees_quote - total_slippage_quote

        gross_return_on_notional_pct = safe_div(gross_pnl_quote, open_notional)
        if gross_return_on_notional_pct is not None:
            gross_return_on_notional_pct *= 100.0
        net_return_on_notional_pct = safe_div(net_pnl_quote, open_notional)
        if net_return_on_notional_pct is not None:
            net_return_on_notional_pct *= 100.0
        gross_return_on_margin_pct = safe_div(gross_pnl_quote, margin_quote)
        if gross_return_on_margin_pct is not None:
            gross_return_on_margin_pct *= 100.0
        net_return_on_margin_pct = safe_div(net_pnl_quote, margin_quote)
        if net_return_on_margin_pct is not None:
            net_return_on_margin_pct *= 100.0

    reject_economic_class = ""
    if row_role == "decision_reject":
        if evidence_class == "FORCED_OPEN_DIAGNOSTIC":
            reject_economic_class = "DIAGNOSTIC_ONLY_REJECT_SIGNAL"
        elif pnl_status == "OK" and net_pnl_quote is not None:
            reject_economic_class = "HARMFUL_REJECT_CANDIDATE" if net_pnl_quote > 0 else "PROTECTIVE_REJECT_CANDIDATE"
        else:
            reject_economic_class = "INDETERMINATE_LOW_SUPPORT"

    close_reason_effective = close_reason or as_text(proposal_row.get("actual_close_reason"))

    return {
        "proposal_uid": as_text(first_present(proposal_row.get("proposal_uid"), normalized_row.get("proposal_uid") if normalized_row else None)),
        "proposal_uid_seed": as_text(first_present(proposal_row.get("proposal_uid_seed"), normalized_row.get("proposal_uid_seed") if normalized_row else None)),
        "source_file": as_text(proposal_row.get("source_file")),
        "source_line": as_int(proposal_row.get("source_line")),
        "timestamp_ms": entry_ts_ms,
        "timestamp_iso": as_text(first_present(proposal_row.get("timestamp_iso"), normalized_row.get("timestamp_iso") if normalized_row else None)),
        "symbol": symbol,
        "side": side,
        "strategy": strategy,
        "regime": as_text(first_present(normalized_row.get("regime") if normalized_row else None, proposal_row.get("regime"))),
        "row_role": row_role,
        "analysis_class": analysis_class,
        "join_quality": join_quality,
        "support_quality": support_quality,
        "reject_reason": reject_reason,
        "nrr_code": nrr_code,
        "gate_verdict": gate_verdict,
        "gate_reason": gate_reason,
        "close_reason": close_reason_effective,
        "entry_price": clean_number(entry_price),
        "close_price": clean_number(close_price),
        "open_notional_quote": clean_number(open_notional),
        "close_notional_quote": clean_number(close_notional),
        "modeled_notional_quote": clean_number(explicit_notional if modeled_notional_used else None),
        "quantity": clean_number(quantity),
        "qty_source": qty_source,
        "notional_source": notional_source,
        "leverage": clean_number(leverage),
        "margin_quote": clean_number(margin_quote),
        "open_fee_bps": clean_number(open_fee_bps),
        "close_fee_bps": clean_number(close_fee_bps),
        "fee_bps": clean_number(round_trip_fee_bps),
        "slippage_bps": clean_number(slippage_bps),
        "round_trip_cost_bps": clean_number(round_trip_cost_bps),
        "close_ts_ms": close_ts_ms,
        "pnl_status": pnl_status,
        "pnl_mode": pnl_mode,
        "evidence_class": evidence_class,
        "reject_economic_class": reject_economic_class,
        "gross_pnl_quote": clean_number(gross_pnl_quote),
        "net_pnl_quote": clean_number(net_pnl_quote),
        "gross_return_on_notional_pct": clean_number(gross_return_on_notional_pct),
        "net_return_on_notional_pct": clean_number(net_return_on_notional_pct),
        "gross_return_on_margin_pct": clean_number(gross_return_on_margin_pct),
        "net_return_on_margin_pct": clean_number(net_return_on_margin_pct),
        "total_fees_quote": clean_number(total_fees_quote),
        "total_slippage_quote": clean_number(total_slippage_quote),
        "actual_qty_used": actual_qty_used,
        "modeled_notional_used": modeled_notional_used,
        "diagnostic_only": analysis_class == "FORCED_OPEN_SIGNAL_DIAGNOSTIC",
        "actual_runtime_support": False,
        "close_reason_timeout_like": close_reason_effective in TIMEOUT_LIKE_CLOSE_REASONS,
        "close_reason_source": "proposal_casebook",
        "source_join_actual_entry_id": as_text(evidence_row.get("linked_actual_entry_id")) if evidence_row else "",
        "evidence_count": as_int(evidence_row.get("evidence_count")) if evidence_row else None,
        "evidence_summary": evidence_row.get("evidence_summary") if evidence_row else "",
        "source_analysis_class": analysis_class,
        "source_strategy_id": strategy,
        "source_entry_order_type": as_text(proposal_row.get("entry_order_type")),
        "source_entry_tif": as_text(proposal_row.get("entry_tif")),
        "ttl_ms": as_int(proposal_row.get("ttl_ms")),
        "round_trip_cost_bps_source": as_float(proposal_row.get("round_trip_cost_bps")),
        "gross_pnl_pct_primary_source": as_float(proposal_row.get("gross_pnl_pct_primary")),
        "gross_pnl_usd_primary_source": as_float(proposal_row.get("gross_pnl_usd_primary")),
        "net_pnl_pct_primary_source": as_float(proposal_row.get("net_pnl_pct_primary")),
        "net_pnl_usd_primary_source": as_float(proposal_row.get("net_pnl_usd_primary")),
        "comparison_close_price_primary": as_float(proposal_row.get("close_price_primary")),
        "comparison_close_price_secondary": as_float(proposal_row.get("close_price_secondary")),
    }


def build_actual_runtime_support_summary(actual_runtime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows_total = len(actual_runtime_rows)
    rows_with_close_price = 0
    rows_closed = 0
    for row in actual_runtime_rows:
        close_price = first_present(row.get("close_price"), row.get("close_price_primary"), row.get("close_price_secondary"))
        if is_positive_price(close_price):
            rows_with_close_price += 1
        close_reason = as_text(first_present(row.get("close_reason"), row.get("actual_close_reason")))
        if close_reason:
            rows_closed += 1
    return {
        "rows_total": rows_total,
        "rows_with_close_price": rows_with_close_price,
        "rows_closed": rows_closed,
        "net_pnl_quote": 0.0 if rows_with_close_price == 0 else None,
    }


def enrich_rows(
    proposal_rows: list[dict[str, Any]],
    normalized_by_uid: dict[str, dict[str, Any]],
    normalized_by_source_line: dict[tuple[str, int], dict[str, Any]],
    evidence_by_uid: dict[str, dict[str, str]],
    default_profile: CostProfile,
    strategy_profiles: dict[str, CostProfile],
    symbol_leverages: dict[str, float],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for proposal_row in proposal_rows:
        proposal_uid = as_text(proposal_row.get("proposal_uid"))
        source_file = as_text(proposal_row.get("source_file"))
        source_line = as_int(proposal_row.get("source_line"))
        normalized_row = normalized_by_uid.get(proposal_uid)
        if normalized_row is None and source_file and source_line is not None:
            normalized_row = normalized_by_source_line.get((source_file, source_line))
        evidence_row = evidence_by_uid.get(proposal_uid)
        if evidence_row is None and normalized_row is not None:
            evidence_row = evidence_by_uid.get(as_text(normalized_row.get("proposal_uid")))
        enriched.append(
            derive_proposal_metadata(
                proposal_row=proposal_row,
                normalized_row=normalized_row,
                evidence_row=evidence_row,
                default_profile=default_profile,
                strategy_profiles=strategy_profiles,
                symbol_leverages=symbol_leverages,
            )
        )

    enriched.sort(key=lambda row: (row.get("timestamp_ms") is None, row.get("timestamp_ms") or 0, row.get("source_line") or 0, row.get("proposal_uid") or ""))
    return enriched


def build_normalized_proposals(normalized_rows: list[dict[str, Any]], evidence_by_uid: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    proposals = [row for row in normalized_rows if as_text(row.get("row_kind")) == "proposal"]
    proposals.sort(key=lambda row: (as_int(row.get("source_line")) or 0, as_text(row.get("proposal_uid"))))
    enriched: list[dict[str, Any]] = []
    for row in proposals:
        proposal_uid = as_text(row.get("proposal_uid"))
        evidence_row = evidence_by_uid.get(proposal_uid, {})
        projected = dict(row)
        projected["join_quality"] = as_text(evidence_row.get("join_quality"))
        projected["support_quality"] = as_text(evidence_row.get("support_quality"))
        projected["linked_actual_entry_id"] = as_text(evidence_row.get("linked_actual_entry_id"))
        projected["evidence_count"] = as_int(evidence_row.get("evidence_count"))
        projected["evidence_summary"] = evidence_row.get("evidence_summary", "")
        enriched.append(projected)
    return enriched


def compute_source_vs_economic_validation(economic_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl_rows = [row for row in economic_rows if row.get("pnl_status") == "OK"]
    gross_source_deltas: list[float] = []
    net_source_deltas: list[float] = []
    cost_source_deltas: list[float] = []
    tp_negative_sign_violations = 0
    sl_positive_sign_violations = 0
    timeout_positive_net_cases = 0

    for row in pnl_rows:
        gross_source = row.get("gross_pnl_usd_primary_source")
        net_source = row.get("net_pnl_usd_primary_source")
        gross_model = row.get("gross_pnl_quote")
        net_model = row.get("net_pnl_quote")
        if gross_source is not None and gross_model is not None:
            gross_source_deltas.append(abs(float(gross_model) - float(gross_source)))
        if net_source is not None and net_model is not None:
            net_source_deltas.append(abs(float(net_model) - float(net_source)))
        round_trip_source = row.get("round_trip_cost_bps_source")
        round_trip_model = row.get("round_trip_cost_bps")
        if round_trip_source is not None and round_trip_model is not None:
            cost_source_deltas.append(abs(float(round_trip_model) - float(round_trip_source)))

        close_reason = as_text(row.get("close_reason"))
        net_pnl = row.get("net_pnl_quote")
        if close_reason == "TP_HIT" and net_pnl is not None and net_pnl <= 0:
            tp_negative_sign_violations += 1
        if close_reason == "SL_HIT" and net_pnl is not None and net_pnl >= 0:
            sl_positive_sign_violations += 1
        if close_reason in TIMEOUT_LIKE_CLOSE_REASONS and net_pnl is not None and net_pnl > 0:
            timeout_positive_net_cases += 1

    return {
        "max_abs_gross_pnl_delta_vs_source": max(gross_source_deltas) if gross_source_deltas else None,
        "max_abs_net_pnl_delta_vs_source": max(net_source_deltas) if net_source_deltas else None,
        "max_abs_round_trip_cost_bps_delta_vs_source": max(cost_source_deltas) if cost_source_deltas else None,
        "tp_negative_sign_violations": tp_negative_sign_violations,
        "sl_positive_sign_violations": sl_positive_sign_violations,
        "timeout_positive_net_cases": timeout_positive_net_cases,
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = len(rows)
    pnl_rows = [row for row in rows if row.get("pnl_status") == "OK"]
    pnl_row_count = len(pnl_rows)
    gross_values = [float(row["gross_pnl_quote"]) for row in pnl_rows if row.get("gross_pnl_quote") is not None]
    net_values = [float(row["net_pnl_quote"]) for row in pnl_rows if row.get("net_pnl_quote") is not None]
    fees_values = [float(row["total_fees_quote"]) for row in pnl_rows if row.get("total_fees_quote") is not None]
    slippage_values = [float(row["total_slippage_quote"]) for row in pnl_rows if row.get("total_slippage_quote") is not None]
    qty_rows = [row for row in rows if row.get("actual_qty_used")]
    modeled_notional_rows = [row for row in rows if row.get("modeled_notional_used")]
    diagnostic_only_rows = [row for row in rows if row.get("diagnostic_only")]

    tp_rows = [row for row in rows if as_text(row.get("close_reason")) == "TP_HIT"]
    sl_rows = [row for row in rows if as_text(row.get("close_reason")) == "SL_HIT"]
    timeout_rows = [row for row in rows if as_text(row.get("close_reason")) in TIMEOUT_LIKE_CLOSE_REASONS]

    win_values = [value for value in net_values if value > 0]
    loss_values = [value for value in net_values if value < 0]
    flat_values = [value for value in net_values if value == 0]
    positive_net_rows = len(win_values)
    negative_net_rows = len(loss_values)
    flat_net_rows = len(flat_values)

    net_sum = sum(net_values) if net_values else 0.0
    gross_sum = sum(gross_values) if gross_values else 0.0
    fees_sum = sum(fees_values) if fees_values else 0.0
    slippage_sum = sum(slippage_values) if slippage_values else 0.0

    avg_net_pnl = mean(net_values) if net_values else None
    expectancy_per_proposal = safe_div(net_sum, total_rows)
    expectancy_per_filled = safe_div(net_sum, pnl_row_count)
    win_rate_net = safe_div(positive_net_rows, pnl_row_count)
    profit_factor = None
    if loss_values:
        profit_factor = sum(win_values) / abs(sum(loss_values)) if loss_values else None
    avg_win = mean(win_values) if win_values else None
    avg_loss = mean(loss_values) if loss_values else None
    payoff_ratio = None
    if avg_win is not None and avg_loss not in (None, 0):
        payoff_ratio = abs(avg_win / avg_loss)

    total_notional = sum(float(row["open_notional_quote"]) for row in pnl_rows if row.get("open_notional_quote") is not None)
    total_margin = sum(float(row["margin_quote"]) for row in pnl_rows if row.get("margin_quote") is not None)
    roi_on_notional = safe_div(net_sum, total_notional)
    if roi_on_notional is not None:
        roi_on_notional *= 100.0
    roi_on_margin = safe_div(net_sum, total_margin)
    if roi_on_margin is not None:
        roi_on_margin *= 100.0

    return {
        "rows_total": total_rows,
        "rows_with_pnl": pnl_row_count,
        "rows_without_pnl": total_rows - pnl_row_count,
        "actual_qty_rows": len(qty_rows),
        "modeled_notional_rows": len(modeled_notional_rows),
        "diagnostic_only_rows": len(diagnostic_only_rows),
        "gross_pnl_sum_quote": gross_sum,
        "net_pnl_sum_quote": net_sum,
        "total_fees_quote": fees_sum,
        "total_slippage_quote": slippage_sum,
        "avg_gross_pnl_quote": mean(gross_values) if gross_values else None,
        "avg_net_pnl_quote": avg_net_pnl,
        "expectancy_per_proposal_quote": expectancy_per_proposal,
        "expectancy_per_filled_quote": expectancy_per_filled,
        "win_rate_net": win_rate_net,
        "profit_factor": profit_factor,
        "avg_win_quote": avg_win,
        "avg_loss_quote": avg_loss,
        "payoff_ratio": payoff_ratio,
        "roi_on_open_notional_pct": roi_on_notional,
        "roi_on_margin_pct": roi_on_margin,
        "tp_rate": safe_div(len(tp_rows), total_rows),
        "sl_rate": safe_div(len(sl_rows), total_rows),
        "timeout_rate": safe_div(len(timeout_rows), total_rows),
        "tp_rows": len(tp_rows),
        "sl_rows": len(sl_rows),
        "timeout_rows": len(timeout_rows),
        "positive_net_rows": positive_net_rows,
        "negative_net_rows": negative_net_rows,
        "flat_net_rows": flat_net_rows,
        "pnl_rows": pnl_rows,
    }


def aggregate_by_group(rows: list[dict[str, Any]], group_fields: list[str], filter_fn: Any | None = None) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if filter_fn is not None and not filter_fn(row):
            continue
        key = tuple(as_text(row.get(field)) for field in group_fields)
        grouped[key].append(row)

    output: list[dict[str, Any]] = []
    for key in sorted(grouped.keys()):
        bucket = grouped[key]
        summary = summarize_rows(bucket)
        record = {field: value for field, value in zip(group_fields, key)}
        for metric_name in (
            "rows_total",
            "rows_with_pnl",
            "rows_without_pnl",
            "actual_qty_rows",
            "modeled_notional_rows",
            "diagnostic_only_rows",
            "gross_pnl_sum_quote",
            "net_pnl_sum_quote",
            "total_fees_quote",
            "total_slippage_quote",
            "avg_gross_pnl_quote",
            "avg_net_pnl_quote",
            "expectancy_per_proposal_quote",
            "expectancy_per_filled_quote",
            "win_rate_net",
            "profit_factor",
            "avg_win_quote",
            "avg_loss_quote",
            "payoff_ratio",
            "roi_on_open_notional_pct",
            "roi_on_margin_pct",
            "tp_rate",
            "sl_rate",
            "timeout_rate",
            "tp_rows",
            "sl_rows",
            "timeout_rows",
            "positive_net_rows",
            "negative_net_rows",
            "flat_net_rows",
        ):
            record[metric_name] = summary.get(metric_name)
        output.append(record)
    return output


def build_field_coverage(rows: list[dict[str, Any]], validation: dict[str, Any], raw_order_log_rows: int, actual_runtime_summary: dict[str, Any]) -> dict[str, Any]:
    total_rows = len(rows)
    counts = Counter()
    pnl_status_counts = Counter()
    evidence_class_counts = Counter()
    reject_class_counts = Counter()
    close_reason_counts = Counter()
    join_quality_counts = Counter()
    support_quality_counts = Counter()

    for row in rows:
        if row.get("entry_price") is not None:
            counts["entry_price_present"] += 1
        if row.get("close_price") is not None:
            counts["close_price_present"] += 1
        if row.get("quantity") is not None:
            counts["quantity_present"] += 1
        if row.get("open_notional_quote") is not None:
            counts["open_notional_present"] += 1
        if row.get("leverage") is not None:
            counts["leverage_present"] += 1
        if row.get("fee_bps") is not None:
            counts["fee_bps_present"] += 1
        if row.get("slippage_bps") is not None:
            counts["slippage_bps_present"] += 1
        if row.get("gross_pnl_quote") is not None:
            counts["gross_pnl_present"] += 1
        if row.get("net_pnl_quote") is not None:
            counts["net_pnl_present"] += 1
        if row.get("actual_qty_used"):
            counts["actual_qty_rows"] += 1
        if row.get("modeled_notional_used"):
            counts["modeled_notional_rows"] += 1
        if row.get("diagnostic_only"):
            counts["diagnostic_only_rows"] += 1
        if row.get("pnl_status"):
            pnl_status_counts[as_text(row.get("pnl_status"))] += 1
        if row.get("evidence_class"):
            evidence_class_counts[as_text(row.get("evidence_class"))] += 1
        if row.get("reject_economic_class"):
            reject_class_counts[as_text(row.get("reject_economic_class"))] += 1
        if row.get("close_reason"):
            close_reason_counts[as_text(row.get("close_reason"))] += 1
        if row.get("join_quality"):
            join_quality_counts[as_text(row.get("join_quality"))] += 1
        if row.get("support_quality"):
            support_quality_counts[as_text(row.get("support_quality"))] += 1

    return {
        "source_rows_total": total_rows,
        "source_order_log_rows_total": raw_order_log_rows,
        "source_actual_runtime_rows_total": actual_runtime_summary["rows_total"],
        "source_actual_runtime_rows_with_close_price": actual_runtime_summary["rows_with_close_price"],
        "source_actual_runtime_rows_closed": actual_runtime_summary["rows_closed"],
        "rows_with_entry_price": counts["entry_price_present"],
        "rows_with_close_price": counts["close_price_present"],
        "rows_with_quantity": counts["quantity_present"],
        "rows_with_open_notional": counts["open_notional_present"],
        "rows_with_leverage": counts["leverage_present"],
        "rows_with_fee_bps": counts["fee_bps_present"],
        "rows_with_slippage_bps": counts["slippage_bps_present"],
        "rows_with_gross_pnl": counts["gross_pnl_present"],
        "rows_with_net_pnl": counts["net_pnl_present"],
        "actual_qty_rows": counts["actual_qty_rows"],
        "modeled_notional_rows": counts["modeled_notional_rows"],
        "diagnostic_only_rows": counts["diagnostic_only_rows"],
        "pnl_status_counts": dict(sorted(pnl_status_counts.items())),
        "evidence_class_counts": dict(sorted(evidence_class_counts.items())),
        "reject_economic_class_counts": dict(sorted(reject_class_counts.items())),
        "close_reason_counts": dict(sorted(close_reason_counts.items())),
        "join_quality_counts": dict(sorted(join_quality_counts.items())),
        "support_quality_counts": dict(sorted(support_quality_counts.items())),
        "validation": validation,
    }


def build_reject_reclassification_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    protective = 0
    harmful = 0
    diagnostic_only = 0
    indeterminate = 0
    for row in rows:
        if as_text(row.get("row_role")) != "decision_reject":
            continue
        reject_class = as_text(row.get("reject_economic_class"))
        if reject_class == "PROTECTIVE_REJECT_CANDIDATE":
            protective += 1
        elif reject_class == "HARMFUL_REJECT_CANDIDATE":
            harmful += 1
        elif reject_class == "DIAGNOSTIC_ONLY_REJECT_SIGNAL":
            diagnostic_only += 1
        else:
            indeterminate += 1
    return {
        "protective_reject_candidates": protective,
        "harmful_reject_candidates": harmful,
        "diagnostic_only_rejects": diagnostic_only,
        "indeterminate_rejects": indeterminate,
    }


def build_economic_rows_for_csv(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_fields = [
        "proposal_uid",
        "source_line",
        "timestamp_ms",
        "timestamp_iso",
        "symbol",
        "side",
        "strategy",
        "regime",
        "row_role",
        "analysis_class",
        "join_quality",
        "support_quality",
        "reject_reason",
        "nrr_code",
        "gate_verdict",
        "gate_reason",
        "close_reason",
        "entry_price",
        "close_price",
        "quantity",
        "open_notional_quote",
        "close_notional_quote",
        "modeled_notional_quote",
        "leverage",
        "margin_quote",
        "fee_bps",
        "slippage_bps",
        "round_trip_cost_bps",
        "pnl_status",
        "pnl_mode",
        "evidence_class",
        "reject_economic_class",
        "gross_pnl_quote",
        "net_pnl_quote",
        "gross_return_on_notional_pct",
        "net_return_on_notional_pct",
        "gross_return_on_margin_pct",
        "net_return_on_margin_pct",
        "total_fees_quote",
        "total_slippage_quote",
        "actual_qty_used",
        "modeled_notional_used",
        "diagnostic_only",
        "close_reason_timeout_like",
        "close_reason_source",
        "evidence_count",
        "evidence_summary",
        "source_join_actual_entry_id",
        "round_trip_cost_bps_source",
        "gross_pnl_usd_primary_source",
        "net_pnl_usd_primary_source",
    ]
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        projected = {field: row.get(field) for field in ordered_fields}
        projected["source_line"] = as_int(projected["source_line"])
        projected["timestamp_ms"] = as_int(projected["timestamp_ms"])
        projected["actual_qty_used"] = bool(projected["actual_qty_used"])
        projected["modeled_notional_used"] = bool(projected["modeled_notional_used"])
        projected["diagnostic_only"] = bool(projected["diagnostic_only"])
        projected["close_reason_timeout_like"] = bool(projected["close_reason_timeout_like"])
        output_rows.append(projected)
    return output_rows


def render_report(
    overall_summary: dict[str, Any],
    execution_feasible_summary: dict[str, Any],
    forced_diagnostic_summary: dict[str, Any],
    validation: dict[str, Any],
    actual_runtime_summary: dict[str, Any],
    default_profile: CostProfile,
    strategy_profiles: dict[str, CostProfile],
    symbol_leverages: dict[str, float],
    source_counts: dict[str, int],
    reject_summary: dict[str, Any],
) -> str:
    summary_lines = [
        "# ORDER_LOG_COUNTERFACTUAL_ECONOMIC_PNL_LAYER_REPORT",
        "",
        "## Scope",
        "This layer consumes the existing counterfactual replay outputs and adds a narrow economic PnL view without rerunning the broad normalization pass.",
        "",
        "## Source Inputs",
        f"- {SOURCE_ORDER_LOG}",
        f"- {SOURCE_PROPOSAL_CASEBOOK}",
        f"- {SOURCE_PROPOSALS_NORMALIZED}",
        f"- {SOURCE_EVIDENCE_MATRIX}",
        f"- {SOURCE_ACTUAL_RUNTIME_CASEBOOK}",
        "",
        "## Cost Profile",
        f"- default source: {default_profile.source}",
        f"- default open fee bps: {default_profile.open_fee_bps}",
        f"- default close fee bps: {default_profile.close_fee_bps}",
        f"- default slippage bps: {default_profile.slippage_bps}",
        f"- strategy profiles: {', '.join(sorted(strategy_profiles.keys()))}",
        f"- leverage symbols: {', '.join(sorted(symbol_leverages.keys()))}",
        "",
        "## Coverage",
        f"- order log rows: {source_counts['order_log_rows']}",
        f"- proposal casebook rows: {source_counts['proposal_rows']}",
        f"- normalized proposal rows: {source_counts['normalized_rows']}",
        f"- evidence join rows: {source_counts['evidence_rows']}",
        f"- actual runtime rows: {source_counts['actual_runtime_rows']}",
        f"- rows with price pair and PnL: {overall_summary['rows_with_pnl']}",
        f"- rows without PnL: {overall_summary['rows_without_pnl']}",
        f"- actual qty rows: {overall_summary['actual_qty_rows']}",
        f"- modeled notional rows: {overall_summary['modeled_notional_rows']}",
        f"- diagnostic-only rows: {overall_summary['diagnostic_only_rows']}",
        "",
        "## Headline Metrics",
        f"- execution feasible net PnL: {execution_feasible_summary['net_pnl_sum_quote']}",
        f"- execution feasible profit factor: {execution_feasible_summary['profit_factor']}",
        f"- execution feasible win rate: {execution_feasible_summary['win_rate_net']}",
        f"- forced diagnostic net PnL: {forced_diagnostic_summary['net_pnl_sum_quote']}",
        f"- actual runtime net PnL: {actual_runtime_summary['net_pnl_quote']}",
        f"- ROI on open notional: {execution_feasible_summary['roi_on_open_notional_pct']}",
        f"- ROI on margin: {execution_feasible_summary['roi_on_margin_pct']}",
        "",
        "## Reject Reclassification",
        f"- protective reject candidates: {reject_summary['protective_reject_candidates']}",
        f"- harmful reject candidates: {reject_summary['harmful_reject_candidates']}",
        f"- diagnostic-only rejects: {reject_summary['diagnostic_only_rejects']}",
        f"- indeterminate rejects: {reject_summary['indeterminate_rejects']}",
        "",
        "## Validation",
        f"- max abs gross PnL delta vs source: {validation['max_abs_gross_pnl_delta_vs_source']}",
        f"- max abs net PnL delta vs source: {validation['max_abs_net_pnl_delta_vs_source']}",
        f"- max abs round-trip cost delta vs source: {validation['max_abs_round_trip_cost_bps_delta_vs_source']}",
        f"- TP sign violations: {validation['tp_negative_sign_violations']}",
        f"- SL sign violations: {validation['sl_positive_sign_violations']}",
        f"- timeout positive net cases: {validation['timeout_positive_net_cases']}",
        "",
        "## Outputs",
        f"- {OUTPUT_REPLAYED_OUTCOMES}",
        f"- {OUTPUT_PROPOSALS_NORMALIZED}",
        f"- {OUTPUT_ECONOMIC_OUTCOMES}",
        f"- {OUTPUT_ECONOMIC_OUTCOMES_CSV}",
        f"- {OUTPUT_FIELD_COVERAGE}",
        f"- {OUTPUT_SUMMARY_BY_SYMBOL}",
        f"- {OUTPUT_SUMMARY_BY_STRATEGY}",
        f"- {OUTPUT_SUMMARY_BY_REGIME}",
        f"- {OUTPUT_SUMMARY_BY_REJECT_REASON}",
        f"- {OUTPUT_SUMMARY_BY_EVIDENCE_CLASS}",
    ]
    return "\n".join(summary_lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the order-log counterfactual economic PnL layer.")
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    args = parser.parse_args(argv)

    report_root = args.report_root
    report_root.mkdir(parents=True, exist_ok=True)

    default_profile, strategy_profiles = load_cost_profiles()
    symbol_leverages = load_symbol_leverage_map()
    proposal_rows, normalized_rows, evidence_rows, actual_runtime_rows, raw_order_log_rows = read_source_rows()
    normalized_by_uid, normalized_by_source_line, evidence_by_uid = build_indexes(normalized_rows, evidence_rows)
    actual_runtime_summary = build_actual_runtime_support_summary(actual_runtime_rows)

    replayed_outcomes = enrich_rows(
        proposal_rows=proposal_rows,
        normalized_by_uid=normalized_by_uid,
        normalized_by_source_line=normalized_by_source_line,
        evidence_by_uid=evidence_by_uid,
        default_profile=default_profile,
        strategy_profiles=strategy_profiles,
        symbol_leverages=symbol_leverages,
    )
    normalized_projection = build_normalized_proposals(normalized_rows, evidence_by_uid)

    write_jsonl(OUTPUT_REPLAYED_OUTCOMES, replayed_outcomes)
    write_jsonl(OUTPUT_PROPOSALS_NORMALIZED, normalized_projection)

    economic_rows = build_economic_rows_for_csv(replayed_outcomes)
    write_jsonl(OUTPUT_ECONOMIC_OUTCOMES, economic_rows)
    economic_csv_fieldnames = list(economic_rows[0].keys()) if economic_rows else []
    write_csv(OUTPUT_ECONOMIC_OUTCOMES_CSV, economic_rows, economic_csv_fieldnames)

    overall_summary = summarize_rows(replayed_outcomes)
    execution_feasible_rows = [row for row in replayed_outcomes if as_text(row.get("evidence_class")) == "EXECUTION_FEASIBLE"]
    forced_diagnostic_rows = [row for row in replayed_outcomes if as_text(row.get("evidence_class")) == "FORCED_OPEN_DIAGNOSTIC"]
    execution_feasible_summary = summarize_rows(execution_feasible_rows)
    forced_diagnostic_summary = summarize_rows(forced_diagnostic_rows)
    reject_summary = build_reject_reclassification_summary(replayed_outcomes)
    validation = compute_source_vs_economic_validation(replayed_outcomes)
    coverage = build_field_coverage(replayed_outcomes, validation, raw_order_log_rows, actual_runtime_summary)

    summary_by_symbol = aggregate_by_group(replayed_outcomes, ["symbol"])
    summary_by_strategy = aggregate_by_group(replayed_outcomes, ["strategy"])
    summary_by_regime = aggregate_by_group(replayed_outcomes, ["regime"])
    summary_by_reject_reason = aggregate_by_group(
        replayed_outcomes,
        ["reject_reason", "nrr_code", "gate_verdict", "reject_economic_class"],
        filter_fn=lambda row: as_text(row.get("row_role")) == "decision_reject",
    )
    summary_by_evidence_class = aggregate_by_group(replayed_outcomes, ["evidence_class"])

    write_csv(OUTPUT_SUMMARY_BY_SYMBOL, summary_by_symbol, list(summary_by_symbol[0].keys()) if summary_by_symbol else ["symbol"])
    write_csv(OUTPUT_SUMMARY_BY_STRATEGY, summary_by_strategy, list(summary_by_strategy[0].keys()) if summary_by_strategy else ["strategy"])
    write_csv(OUTPUT_SUMMARY_BY_REGIME, summary_by_regime, list(summary_by_regime[0].keys()) if summary_by_regime else ["regime"])
    write_csv(
        OUTPUT_SUMMARY_BY_REJECT_REASON,
        summary_by_reject_reason,
        list(summary_by_reject_reason[0].keys()) if summary_by_reject_reason else ["reject_reason"],
    )
    write_csv(
        OUTPUT_SUMMARY_BY_EVIDENCE_CLASS,
        summary_by_evidence_class,
        list(summary_by_evidence_class[0].keys()) if summary_by_evidence_class else ["evidence_class"],
    )

    source_counts = {
        "order_log_rows": raw_order_log_rows,
        "proposal_rows": len(proposal_rows),
        "normalized_rows": len(normalized_rows),
        "evidence_rows": len(evidence_rows),
        "actual_runtime_rows": len(actual_runtime_rows),
    }

    report_text = render_report(
        overall_summary=overall_summary,
        execution_feasible_summary=execution_feasible_summary,
        forced_diagnostic_summary=forced_diagnostic_summary,
        validation=validation,
        actual_runtime_summary=actual_runtime_summary,
        default_profile=default_profile,
        strategy_profiles=strategy_profiles,
        symbol_leverages=symbol_leverages,
        source_counts=source_counts,
        reject_summary=reject_summary,
    )
    OUTPUT_REPORT.write_text(report_text, encoding="utf-8")

    field_coverage_payload = {
        **coverage,
        "overall_summary": {key: value for key, value in overall_summary.items() if key != "pnl_rows"},
        "reject_summary": reject_summary,
        "actual_runtime_summary": actual_runtime_summary,
        "source_counts": source_counts,
        "strategies_seen": sorted({as_text(row.get("strategy")) for row in replayed_outcomes}),
        "symbols_seen": sorted({as_text(row.get("symbol")) for row in replayed_outcomes}),
    }
    OUTPUT_FIELD_COVERAGE.write_text(json.dumps(field_coverage_payload, ensure_ascii=True, sort_keys=True, indent=2, default=json_default) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())