#!/usr/bin/env python3
"""Offline audit for logs/order_log_v1.jsonl.

This script is read-only. It normalizes the live order log, joins evidence from
order-log sidecars, replays proposal rows against recorder bars, reconstructs
actual runtime entry groups, and emits a deterministic report tree.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ANALYSIS_ROOT = ROOT / "tools" / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from apps.reference.config_loader import ConfigLoader
from order_reconstruction_tp_sl_common import AuthorityRow, classify_order_role, iso_utc, normalize_side, reconstruct_entries, stringify, to_float, to_int


ORDER_LOG_PATH = ROOT / "logs" / "order_log_v1.jsonl"
TRADE_LIFECYCLE_PATH = ROOT / "logs" / "trade_lifecycle.jsonl"
SHADOW_JOURNAL_PATH = ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"
RECORDER_ROOT = ROOT / "data" / "recorder"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "order_log_counterfactual_replay"
COMMON_RECONSTRUCTION_ROOT = DEFAULT_REPORT_ROOT / "_common_reconstruction"

PROPOSAL_ROLES = {
    "trade_intent",
    "exec_submit_intent",
    "decision_reject",
    "reservation_intent",
}

EVIDENCE_ROLES = {
    "order_placed",
    "limit_price_adjusted",
    "entry_fill",
    "exit_fill",
    "fill_other",
    "order_timeout",
    "order_cancelled",
    "order_rejected",
    "position_closed",
}

ID_KEYS = {
    "rid",
    "lifecycle_id",
    "reservation_id",
    "client_order_id",
    "clientOrderId",
    "order_id",
    "orderId",
    "trace_id",
    "traceId",
    "corr_id",
    "idempotent_key",
}


@dataclass(frozen=True)
class Bar:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    source_file: str


def stable_hash(text: str, size: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def nested_get(node: Any, path: str, default: Any = None) -> Any:
    current = node
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def as_text(value: Any) -> str:
    return stringify(value) or ""


def safe_float(value: Any) -> float | None:
    return to_float(value)


def safe_int(value: Any) -> int | None:
    return to_int(value)


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        for child in sorted(path.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    path.mkdir(parents=True, exist_ok=True)


def write_json_file(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def write_jsonl_file(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n")


def flatten_for_csv(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_csv_file(path: Path, headers: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: flatten_for_csv(row.get(key)) for key in headers})


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield line_no, payload


def extract_identity_values(node: Any) -> set[str]:
    values: set[str] = set()

    def walk(current: Any, parent_key: str | None = None) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                if key in ID_KEYS and child not in (None, ""):
                    values.add(str(child))
                walk(child, key)
        elif isinstance(current, list):
            for child in current:
                walk(child, parent_key)

    walk(node)
    return values


def collect_identity_fields(row: dict[str, Any]) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for key in ("rid", "lifecycle_id", "reservation_id", "order_id", "client_order_id"):
        value = row.get(key)
        if value not in (None, ""):
            fields.append((key, str(value)))
    detector_rid = nested_get(row, "regime_provenance.detector_event.rid")
    if detector_rid not in (None, ""):
        fields.append(("detector_rid", str(detector_rid)))
    corr_id = nested_get(row, "metadata.corr_id")
    if corr_id not in (None, ""):
        fields.append(("corr_id", str(corr_id)))
    idempotent_key = nested_get(row, "metadata.idempotent_key")
    if idempotent_key not in (None, ""):
        fields.append(("idempotent_key", str(idempotent_key)))
    return fields


def proposal_uid_seed(row: dict[str, Any], strategy_id: str) -> str:
    source_file = as_text(row.get("source_file")) or "logs/order_log_v1.jsonl"
    source_line = safe_int(row.get("source_line")) or 0
    timestamp_ms = safe_int(row.get("timestamp")) or 0
    symbol = as_text(row.get("symbol"))
    side = as_text(row.get("side"))
    return f"{source_file}:{source_line}:{timestamp_ms}:{symbol}:{side}:{strategy_id}"


def proposal_uid(row: dict[str, Any], strategy_id: str) -> str:
    return stable_hash(proposal_uid_seed(row, strategy_id), size=24)


def detailed_row_role(row: dict[str, Any]) -> str:
    event_type = as_text(row.get("event_type"))
    source_fsm = as_text(row.get("source_fsm"))
    order_kind = as_text(row.get("order_kind") or nested_get(row, "metadata.order_kind"))
    if event_type == "BOOT":
        return "system_boot"
    if event_type == "ORDER_INTENT" and source_fsm == "DecisionMaking":
        return "trade_intent"
    if event_type == "ORDER_INTENT" and source_fsm == "ExecPosFSM":
        return "exec_submit_intent"
    if event_type == "ORDER_INTENT" and source_fsm == "ExposureGuard":
        return "reservation_intent"
    if event_type == "DECISION_INTENT_REJECTED":
        return "decision_reject"
    if event_type == "ORDER_PLACED":
        return "order_placed"
    if event_type == "LIMIT_PRICE_ADJUSTED":
        return "limit_price_adjusted"
    if event_type == "ORDER_FILLED" and order_kind == "ENTRY":
        return "entry_fill"
    if event_type == "ORDER_FILLED" and order_kind in {"SL", "TP", "CLOSE"}:
        return "exit_fill"
    if event_type == "ORDER_FILLED":
        return "fill_other"
    if event_type == "ORDER_TIMEOUT":
        return "order_timeout"
    if event_type == "ORDER_CANCELLED":
        return "order_cancelled"
    if event_type == "ORDER_REJECTED":
        return "order_rejected"
    if event_type == "POSITION_CLOSED":
        return "position_closed"
    return "other_evidence"


def load_config_snapshot() -> dict[str, Any]:
    cfg = ConfigLoader().load_config().model_dump()
    aurora = cfg.get("strategies", {}).get("aurora", {})
    execution = aurora.get("execution", {})
    trade_gate = cfg.get("domains", {}).get("decision_making", {}).get("low_vol_cost_floor_gate", {})
    fees = trade_gate.get("fee", {})
    slippage = trade_gate.get("slippage", {})
    watchdog = cfg.get("trading", {}).get("execution", {}).get("watchdog", {})
    order_params = cfg.get("trading", {}).get("execution", {}).get("order_params", {})
    execution_position = cfg.get("domains", {}).get("execution_position", {})

    symbol_profiles: dict[str, dict[str, Any]] = {}
    for symbol, asset_cfg in (aurora.get("assets") or {}).items():
        exit_cfg = asset_cfg.get("exit") or {}
        tpsl_cfg = exit_cfg.get("regime_tpsl") or {}
        take_profit_cfg = asset_cfg.get("take_profit") or {}
        symbol_profiles[str(symbol)] = {
            "sl_pct": safe_float(exit_cfg.get("sl_pct")),
            "max_hold_sec": safe_int(exit_cfg.get("max_hold_sec")),
            "tp_low_ratio": safe_float(take_profit_cfg.get("tp_low_ratio")),
            "tp_high_ratio": safe_float(take_profit_cfg.get("tp_high_ratio")),
            "regime_tpsl": {
                "enabled": bool(tpsl_cfg.get("enabled", False)),
                "mode": as_text(tpsl_cfg.get("mode")) or "",
                "sl_mult": tpsl_cfg.get("sl_mult") or {},
                "tp_mult": tpsl_cfg.get("tp_mult") or {},
                "min_sl_pct": safe_float(tpsl_cfg.get("min_sl_pct")),
                "max_sl_pct": safe_float(tpsl_cfg.get("max_sl_pct")),
                "min_tp_rr": safe_float(tpsl_cfg.get("min_tp_rr")),
                "max_tp_rr": safe_float(tpsl_cfg.get("max_tp_rr")),
                "min_dist_bps": safe_int(tpsl_cfg.get("min_dist_bps")),
            },
        }

    return {
        "root": cfg,
        "strategy_id": "aurora",
        "timeframe_sec": safe_int(aurora.get("timeframe_sec")) or 300,
        "entry_order_type": as_text(execution.get("entry_order_type")) or "LIMIT",
        "entry_tif": as_text(execution.get("entry_tif")) or "GTX",
        "exit_tif": as_text(execution.get("exit_tif")) or "",
        "gtx_retry_max": safe_int(execution.get("gtx_retry_max")) or 0,
        "gtx_retry_offset_bps": safe_float(execution.get("gtx_retry_offset_bps")) or 0.0,
        "watchdog_fill_ttl_ms": safe_int(watchdog.get("fill_ttl_ms")) or 1800000,
        "ack_ttl_ms": safe_int(watchdog.get("ack_ttl_ms")) or 0,
        "order_params": order_params,
        "execution_position": execution_position,
        "fees": {
            "open_fee_bps": safe_float(fees.get("open_fee_bps")) or 0.0,
            "close_fee_bps": safe_float(fees.get("close_fee_bps")) or 0.0,
            "fee_source": as_text(fees.get("fee_source")) or "explicit_config",
        },
        "slippage": {
            "buffer_bps": safe_float(slippage.get("buffer_bps")) or 0.0,
            "source": as_text(slippage.get("source")) or "explicit_config",
        },
        "symbol_profiles": symbol_profiles,
        "market_order_params": order_params.get("MARKET") or {},
    }


def load_order_log_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, payload in iter_jsonl(path):
        payload = dict(payload)
        payload["source_file"] = path.relative_to(ROOT).as_posix()
        payload["source_line"] = line_no
        rows.append(payload)
    return rows


def load_bars_300(root: Path) -> tuple[dict[str, list[Bar]], dict[str, dict[str, Any]]]:
    bars_by_symbol: dict[str, list[Bar]] = defaultdict(list)
    coverage: dict[str, dict[str, Any]] = {}
    for csv_path in sorted(root.rglob("*_300.csv")):
        symbol = csv_path.name.split("_", 1)[0]
        valid_rows = 0
        first_ts: int | None = None
        last_ts: int | None = None
        with csv_path.open("r", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ts_ms = safe_int(row.get("timestamp"))
                open_price = safe_float(row.get("open"))
                high_price = safe_float(row.get("high"))
                low_price = safe_float(row.get("low"))
                close_price = safe_float(row.get("close"))
                if ts_ms is None or open_price is None or high_price is None or low_price is None or close_price is None:
                    continue
                bars_by_symbol[symbol].append(
                    Bar(
                        timestamp_ms=ts_ms,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        source_file=csv_path.relative_to(ROOT).as_posix(),
                    )
                )
                valid_rows += 1
                first_ts = ts_ms if first_ts is None else min(first_ts, ts_ms)
                last_ts = ts_ms if last_ts is None else max(last_ts, ts_ms)
        coverage[symbol] = {
            "symbol": symbol,
            "file_count": len(list(root.rglob(f"{symbol}_300.csv"))),
            "valid_rows": valid_rows,
            "first_ts_ms": first_ts,
            "last_ts_ms": last_ts,
            "first_ts_iso": iso_utc(first_ts),
            "last_ts_iso": iso_utc(last_ts),
        }
    for symbol in bars_by_symbol:
        bars_by_symbol[symbol].sort(key=lambda bar: bar.timestamp_ms)
    return bars_by_symbol, coverage


def load_relevant_sidecar_rows(path: Path, candidate_ids: set[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    matches: list[dict[str, Any]] = []
    for line_no, payload in iter_jsonl(path):
        ids = extract_identity_values(payload)
        if not ids.intersection(candidate_ids):
            continue
        matches.append(
            {
                "source_file": path.relative_to(ROOT).as_posix(),
                "source_line": line_no,
                "raw": payload,
                "ids": sorted(ids),
            }
        )
    return matches


def index_records_by_id(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        ids = record.get("ids") or extract_identity_values(record.get("raw") or record)
        if isinstance(ids, set):
            iterable = ids
        else:
            iterable = set(ids)
        for identity in iterable:
            index[str(identity)].append(record)
    for identity in index:
        index[identity].sort(key=lambda item: (safe_int(item.get("source_line")) or 0, item.get("source_file") or ""))
    return index


def bar_timestamp_list(bars: list[Bar]) -> list[int]:
    return [bar.timestamp_ms for bar in bars]


def nearest_causal_bar(symbol: str, timestamp_ms: int, bars_by_symbol: dict[str, list[Bar]]) -> Bar | None:
    bars = bars_by_symbol.get(symbol) or []
    if not bars:
        return None
    ts_list = bar_timestamp_list(bars)
    idx = bisect_right(ts_list, timestamp_ms) - 1
    if idx < 0:
        return None
    return bars[idx]


def scan_limit_fill(symbol: str, side: str, entry_price: float, entry_ts_ms: int, ttl_ms: int, bars_by_symbol: dict[str, list[Bar]]) -> tuple[bool, int | None, Bar | None, int | None]:
    if entry_price <= 0:
        return False, None, None, None
    bars = bars_by_symbol.get(symbol) or []
    if not bars:
        return False, None, None, None
    ts_list = bar_timestamp_list(bars)
    start_idx = bisect_right(ts_list, entry_ts_ms)
    end_idx = bisect_right(ts_list, entry_ts_ms + ttl_ms)
    for idx in range(start_idx, end_idx):
        bar = bars[idx]
        if side == "BUY":
            hit = bar.low <= entry_price
        else:
            hit = bar.high >= entry_price
        if hit:
            return True, bar.timestamp_ms, bar, idx
    return False, None, bars[end_idx - 1] if end_idx > start_idx else None, (end_idx - 1 if end_idx > start_idx else None)


def compute_tpsl_geometry(symbol: str, side: str, entry_price: float, regime: str, config: dict[str, Any]) -> dict[str, Any]:
    if entry_price <= 0:
        return {"status": "INVALID_ENTRY_PRICE"}
    symbol_cfg = (config.get("symbol_profiles") or {}).get(symbol) or {}
    regime_cfg = symbol_cfg.get("regime_tpsl") or {}
    if not regime_cfg.get("enabled", False):
        return {"status": "TPSL_DISABLED"}
    if as_text(regime_cfg.get("mode")) != "pct_mult":
        return {"status": "UNSUPPORTED_TPSL_MODE"}

    sl_pct_base = symbol_cfg.get("sl_pct")
    tp_low_ratio = symbol_cfg.get("tp_low_ratio")
    if sl_pct_base is None or tp_low_ratio is None:
        return {"status": "CONFIG_MISSING"}

    sl_mult_map = regime_cfg.get("sl_mult") or {}
    tp_mult_map = regime_cfg.get("tp_mult") or {}
    sl_mult = safe_float(sl_mult_map.get(regime))
    if sl_mult is None:
        sl_mult = safe_float(sl_mult_map.get("DEFAULT"))
    tp_mult = safe_float(tp_mult_map.get(regime))
    if tp_mult is None:
        tp_mult = safe_float(tp_mult_map.get("DEFAULT"))
    if sl_mult is None or tp_mult is None:
        return {"status": "MULTIPLIER_MISSING"}

    sl_pct_eff = sl_pct_base * sl_mult
    tp_rr_eff = tp_low_ratio * tp_mult

    min_sl_pct = safe_float(regime_cfg.get("min_sl_pct")) or 0.003
    max_sl_pct = safe_float(regime_cfg.get("max_sl_pct")) or 0.06
    min_tp_rr = safe_float(regime_cfg.get("min_tp_rr")) or 0.3
    max_tp_rr = safe_float(regime_cfg.get("max_tp_rr")) or 3.0
    min_dist_bps = safe_int(regime_cfg.get("min_dist_bps")) or 15

    guardrail_notes: list[str] = []
    if sl_pct_eff < min_sl_pct:
        sl_pct_eff = min_sl_pct
        guardrail_notes.append("sl_clamped_min")
    elif sl_pct_eff > max_sl_pct:
        sl_pct_eff = max_sl_pct
        guardrail_notes.append("sl_clamped_max")

    tp_pct = sl_pct_eff * tp_rr_eff
    rr_eff = tp_rr_eff
    current_rr = tp_pct / sl_pct_eff if sl_pct_eff > 0 else 0.0
    if current_rr < min_tp_rr:
        tp_pct = sl_pct_eff * min_tp_rr
        rr_eff = min_tp_rr
        guardrail_notes.append("rr_clamped_min")
    elif current_rr > max_tp_rr:
        tp_pct = sl_pct_eff * max_tp_rr
        rr_eff = max_tp_rr
        guardrail_notes.append("rr_clamped_max")

    min_dist = min_dist_bps / 10000.0
    if sl_pct_eff < min_dist:
        return {"status": "SL_BELOW_MIN_DIST_BPS", "guardrail_notes": guardrail_notes}
    if tp_pct < min_dist:
        return {"status": "TP_BELOW_MIN_DIST_BPS", "guardrail_notes": guardrail_notes}

    if side == "BUY":
        stop_price = entry_price * (1.0 - sl_pct_eff)
        target_price = entry_price * (1.0 + tp_pct)
    else:
        stop_price = entry_price * (1.0 + sl_pct_eff)
        target_price = entry_price * (1.0 - tp_pct)

    return {
        "status": "OK",
        "stop_price": stop_price,
        "target_price": target_price,
        "sl_pct_eff": sl_pct_eff,
        "tp_pct_eff": tp_pct,
        "tp_rr_eff": rr_eff,
        "guardrail_notes": guardrail_notes,
        "min_dist_bps": min_dist_bps,
    }


def simulate_tp_sl_path(symbol: str, side: str, entry_price: float, entry_ts_ms: int, stop_price: float, target_price: float, bars_by_symbol: dict[str, list[Bar]], horizon_ts_ms: int | None = None) -> dict[str, Any]:
    if entry_price <= 0:
        return {"status": "INVALID_ENTRY_PRICE"}
    bars = bars_by_symbol.get(symbol) or []
    if not bars:
        return {"status": "NO_MARKET_DATA"}
    ts_list = bar_timestamp_list(bars)
    start_idx = bisect_right(ts_list, entry_ts_ms)
    end_idx = len(bars) if horizon_ts_ms is None else bisect_right(ts_list, horizon_ts_ms)
    if start_idx >= len(bars):
        return {"status": "NO_FORWARD_BARS"}

    mfe_pct = None
    mae_pct = None
    primary_reason = None
    primary_close_price = None
    primary_close_ts_ms = None
    primary_close_bar_idx = None
    secondary_reason = None
    secondary_close_price = None
    secondary_close_ts_ms = None
    secondary_close_bar_idx = None
    ambiguous = False

    for idx in range(start_idx, end_idx):
        bar = bars[idx]
        high = bar.high
        low = bar.low
        if side == "BUY":
            favorable = (high - entry_price) / entry_price
            adverse = (low - entry_price) / entry_price
            hit_stop = low <= stop_price
            hit_tp = high >= target_price
        else:
            favorable = (entry_price - low) / entry_price
            adverse = (entry_price - high) / entry_price
            hit_stop = high >= stop_price
            hit_tp = low <= target_price
        mfe_pct = favorable if mfe_pct is None else max(mfe_pct, favorable)
        mae_pct = adverse if mae_pct is None else min(mae_pct, adverse)

        if hit_stop and hit_tp:
            ambiguous = True
            primary_reason = "SL_HIT"
            primary_close_price = stop_price
            primary_close_ts_ms = bar.timestamp_ms
            primary_close_bar_idx = idx
            secondary_reason = "TP_HIT"
            secondary_close_price = target_price
            secondary_close_ts_ms = bar.timestamp_ms
            secondary_close_bar_idx = idx
            break
        if hit_stop:
            primary_reason = "SL_HIT"
            primary_close_price = stop_price
            primary_close_ts_ms = bar.timestamp_ms
            primary_close_bar_idx = idx
            secondary_reason = primary_reason
            secondary_close_price = primary_close_price
            secondary_close_ts_ms = primary_close_ts_ms
            secondary_close_bar_idx = primary_close_bar_idx
            break
        if hit_tp:
            primary_reason = "TP_HIT"
            primary_close_price = target_price
            primary_close_ts_ms = bar.timestamp_ms
            primary_close_bar_idx = idx
            secondary_reason = primary_reason
            secondary_close_price = primary_close_price
            secondary_close_ts_ms = primary_close_ts_ms
            secondary_close_bar_idx = primary_close_bar_idx
            break

    if primary_reason is None:
        last_bar = bars[end_idx - 1] if end_idx > start_idx else bars[min(start_idx, len(bars) - 1)]
        primary_reason = "OBSERVATION_END"
        primary_close_price = last_bar.close
        primary_close_ts_ms = last_bar.timestamp_ms
        primary_close_bar_idx = max(end_idx - 1, start_idx)
        secondary_reason = primary_reason
        secondary_close_price = primary_close_price
        secondary_close_ts_ms = primary_close_ts_ms
        secondary_close_bar_idx = primary_close_bar_idx

    return {
        "status": "OK",
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "close_reason_primary": primary_reason,
        "close_price_primary": primary_close_price,
        "close_ts_ms_primary": primary_close_ts_ms,
        "close_bar_idx_primary": primary_close_bar_idx,
        "close_reason_secondary": secondary_reason,
        "close_price_secondary": secondary_close_price,
        "close_ts_ms_secondary": secondary_close_ts_ms,
        "close_bar_idx_secondary": secondary_close_bar_idx,
        "ambiguous_intrabar": ambiguous,
        "bars_considered": max(0, end_idx - start_idx),
    }


def resolve_fee_bps(config: dict[str, Any]) -> tuple[float, float, float]:
    fees = config.get("fees") or {}
    slippage = config.get("slippage") or {}
    open_fee_bps = safe_float(fees.get("open_fee_bps")) or 0.0
    close_fee_bps = safe_float(fees.get("close_fee_bps")) or 0.0
    slippage_buffer_bps = safe_float(slippage.get("buffer_bps")) or 0.0
    return open_fee_bps, close_fee_bps, slippage_buffer_bps


def pnl_from_prices(side: str, entry_price: float, exit_price: float, quantity: float | None) -> tuple[float | None, float | None, float | None]:
    if entry_price <= 0 or exit_price <= 0:
        return None, None, None
    gross_pct = ((exit_price - entry_price) / entry_price) if side == "BUY" else ((entry_price - exit_price) / entry_price)
    if quantity is None:
        return gross_pct, None, None
    notional = quantity * entry_price
    gross_usd = quantity * ((exit_price - entry_price) if side == "BUY" else (entry_price - exit_price))
    return gross_pct, gross_usd, notional


def enrich_price_context(row: dict[str, Any], role: str, bars_by_symbol: dict[str, list[Bar]], config: dict[str, Any]) -> tuple[float | None, str, int | None, dict[str, Any]]:
    symbol = as_text(row.get("symbol"))
    timestamp_ms = safe_int(row.get("timestamp")) or 0
    price = safe_float(row.get("price"))
    adjusted_price = safe_float(row.get("adjusted_price"))
    original_price = safe_float(row.get("original_price"))
    entry_price = first_non_null(adjusted_price, price, original_price)
    price_source = "row.price"
    if adjusted_price is not None:
        price_source = "row.adjusted_price"
    elif price is not None:
        price_source = "row.price"
    elif original_price is not None:
        price_source = "row.original_price"

    if entry_price is None and role == "decision_reject":
        causal_bar = nearest_causal_bar(symbol, timestamp_ms, bars_by_symbol)
        if causal_bar is not None:
            entry_price = causal_bar.close
            price_source = "nearest_causal_bar_close"
    if entry_price is None and role == "reservation_intent":
        causal_bar = nearest_causal_bar(symbol, timestamp_ms, bars_by_symbol)
        if causal_bar is not None:
            entry_price = causal_bar.close
            price_source = "nearest_causal_bar_close"
    if entry_price is None:
        return None, price_source, None, {"entry_price_note": "missing"}

    causal_bar = nearest_causal_bar(symbol, timestamp_ms, bars_by_symbol)
    causal_ts = causal_bar.timestamp_ms if causal_bar else None
    extra = {
        "causal_bar_ts_ms": causal_ts,
        "causal_bar_close": causal_bar.close if causal_bar else None,
    }
    return entry_price, price_source, causal_ts, extra


def build_normalized_row(row: dict[str, Any], strategy_id: str, config: dict[str, Any]) -> dict[str, Any]:
    role = detailed_row_role(row)
    event_type = as_text(row.get("event_type"))
    source_fsm = as_text(row.get("source_fsm"))
    symbol = as_text(row.get("symbol"))
    side = normalize_side(row.get("side"))
    timestamp_ms = safe_int(row.get("timestamp"))
    regime = as_text(row.get("regime"))
    regime_confidence = safe_float(row.get("regime_confidence"))
    quantity = first_non_null(safe_float(row.get("quantity")), safe_float(nested_get(row, "metadata.reserve_margin")))
    order_kind = as_text(row.get("order_kind")) or as_text(nested_get(row, "metadata.order_kind"))
    price = first_non_null(safe_float(row.get("price")), safe_float(row.get("adjusted_price")), safe_float(row.get("original_price")))
    proposal_seed = proposal_uid_seed(row, strategy_id)
    proposal_hash = stable_hash(proposal_seed, size=24)
    chain_uid = first_non_null(as_text(row.get("lifecycle_id")), as_text(row.get("rid")), as_text(row.get("reservation_id")), as_text(row.get("client_order_id")), as_text(row.get("order_id")))
    chain_uid_source = "lifecycle_id" if row.get("lifecycle_id") not in (None, "") else "rid"
    if not chain_uid:
        chain_uid = proposal_hash
        chain_uid_source = "proposal_uid"
    row_kind = "proposal" if role in PROPOSAL_ROLES else ("evidence" if role in EVIDENCE_ROLES else "system")
    normalized = {
        "source_file": row.get("source_file"),
        "source_line": row.get("source_line"),
        "timestamp_ms": timestamp_ms,
        "timestamp_iso": iso_utc(timestamp_ms),
        "event_type": event_type,
        "row_role": role,
        "row_kind": row_kind,
        "proposal_uid": proposal_hash,
        "proposal_uid_seed": proposal_seed,
        "chain_uid": chain_uid,
        "chain_uid_source": chain_uid_source,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "side": side,
        "regime": regime,
        "regime_confidence": regime_confidence,
        "source_fsm": source_fsm,
        "rid": as_text(row.get("rid")),
        "lifecycle_id": as_text(row.get("lifecycle_id")),
        "reservation_id": as_text(row.get("reservation_id")),
        "order_id": as_text(row.get("order_id")),
        "client_order_id": as_text(row.get("client_order_id")),
        "order_kind": order_kind,
        "quantity": quantity,
        "price": price,
        "adjusted_price": safe_float(row.get("adjusted_price")),
        "original_price": safe_float(row.get("original_price")),
        "nrr_code": as_text(row.get("nrr_code")),
        "why": as_text(row.get("why")),
        "reason": as_text(row.get("reason")),
        "close_reason": as_text(row.get("close_reason")),
        "status": as_text(row.get("status")),
        "entry_order_type": as_text(nested_get(row, "metadata.type")) or as_text(nested_get(row, "adapter_response.type")),
        "entry_tif": as_text(nested_get(row, "metadata.tif")) or as_text(nested_get(row, "adapter_response.timeInForce")),
        "threshold_verdict": as_text(nested_get(row, "metadata.threshold_verdict")),
        "threshold_reason": as_text(nested_get(row, "metadata.threshold_reason")),
        "deny_reason": as_text(nested_get(row, "metadata.deny_reason")),
        "reject_reason": as_text(nested_get(row, "metadata.reject_reason")),
        "intent_proposed": bool(nested_get(row, "metadata.intent_proposed", False)),
        "source_identity_values": sorted(extract_identity_values(row)),
    }
    return normalized


def build_identity_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for key, value in collect_identity_fields(row):
            index[value].append(row)
    for key in index:
        index[key].sort(key=lambda item: (safe_int(item.get("timestamp_ms")) or 0, safe_int(item.get("source_line")) or 0))
    return index


def proposal_analysis_class(role: str, price: float | None, quantity: float | None) -> str:
    if role == "reservation_intent":
        return "RESERVATION_ONLY"
    if role == "decision_reject" and price is None:
        return "FORCED_OPEN_SIGNAL_DIAGNOSTIC"
    if role in {"trade_intent", "exec_submit_intent"} and price is not None and quantity is not None:
        return "EXECUTION_FEASIBLE_COUNTERFACTUAL"
    if role in {"trade_intent", "exec_submit_intent", "decision_reject"}:
        return "UNREPLAYABLE_OR_LOW_SUPPORT"
    return "EVIDENCE_ONLY"


def build_proposal_casebook(
    proposal_rows: list[dict[str, Any]],
    proposal_index: dict[str, list[dict[str, Any]]],
    order_log_evidence_index: dict[str, list[dict[str, Any]]],
    sidecar_index: dict[str, list[dict[str, Any]]],
    bars_by_symbol: dict[str, list[Bar]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter[str], list[dict[str, Any]]]:
    open_fee_bps, close_fee_bps, slippage_buffer_bps = resolve_fee_bps(config)
    round_trip_cost_bps = open_fee_bps + close_fee_bps + slippage_buffer_bps
    entry_ttl_ms = safe_int(config.get("watchdog_fill_ttl_ms")) or 1800000

    casebook: list[dict[str, Any]] = []
    join_counts: Counter[str] = Counter()
    bridge_rows: list[dict[str, Any]] = []

    for row in sorted(proposal_rows, key=lambda item: (safe_int(item.get("timestamp")) or 0, safe_int(item.get("source_line")) or 0, as_text(item.get("rid")))):
        role = as_text(row.get("row_role"))
        symbol = as_text(row.get("symbol"))
        side = as_text(row.get("side"))
        strategy_id = as_text(row.get("strategy_id")) or config.get("strategy_id") or "aurora"
        proposal_id = as_text(row.get("proposal_uid")) or proposal_uid(row, strategy_id)
        proposal_seed = proposal_uid_seed(row, strategy_id)
        chain_uid = as_text(row.get("chain_uid")) or proposal_id
        source_line = safe_int(row.get("source_line")) or 0
        timestamp_ms = safe_int(row.get("timestamp_ms")) or 0
        quantity = safe_float(row.get("quantity"))
        proposal_price = safe_float(row.get("price"))
        entry_price, price_source, causal_ts, causal_extra = enrich_price_context(row, role, bars_by_symbol, config)

        evidence_matches: list[dict[str, Any]] = []
        evidence_ids = []
        for _, value in collect_identity_fields(row):
            evidence_ids.append(value)
            evidence_matches.extend(order_log_evidence_index.get(value, []))
            evidence_matches.extend(sidecar_index.get(value, []))

        unique_evidence: list[dict[str, Any]] = []
        seen_evidence_keys: set[tuple[str, int, str]] = set()
        for match in evidence_matches:
            key = (
                as_text(match.get("source_file")),
                safe_int(match.get("source_line")) or 0,
                as_text((match.get("raw") or {}).get("event_type") if isinstance(match.get("raw"), dict) else match.get("event_type")),
            )
            if key in seen_evidence_keys:
                continue
            seen_evidence_keys.add(key)
            unique_evidence.append(match)

        evidence_event_types = Counter()
        evidence_source_files = Counter()
        for match in unique_evidence:
            raw = match.get("raw") or match
            evidence_event_types[as_text(raw.get("event_type") if isinstance(raw, dict) else raw.get("event_type"))] += 1
            evidence_source_files[as_text(match.get("source_file"))] += 1

        has_exact_order_log_evidence = any(as_text((match.get("raw") or match).get("source_fsm")) in {"ExecPosFSM", "DecisionMaking", "ExposureGuard"} for match in unique_evidence if isinstance(match.get("raw") or match, dict))
        has_sidecar_match = any(as_text(match.get("source_file")) in {TRADE_LIFECYCLE_PATH.relative_to(ROOT).as_posix(), SHADOW_JOURNAL_PATH.relative_to(ROOT).as_posix()} for match in unique_evidence)
        if has_exact_order_log_evidence and has_sidecar_match:
            join_quality = "JOIN_EXACT"
        elif any(as_text(match.get("source_file")) == ORDER_LOG_PATH.relative_to(ROOT).as_posix() for match in unique_evidence):
            join_quality = "JOIN_RID"
        elif unique_evidence:
            join_quality = "JOIN_TRACE_ID"
        else:
            causal_bar = nearest_causal_bar(symbol, timestamp_ms, bars_by_symbol)
            join_quality = "JOIN_SYMBOL_TIME_WINDOW" if causal_bar is not None else "JOIN_NONE"
        if role == "decision_reject" and join_quality == "JOIN_NONE":
            causal_bar = nearest_causal_bar(symbol, timestamp_ms, bars_by_symbol)
            if causal_bar is not None:
                join_quality = "JOIN_SYMBOL_TIME_WINDOW"

        join_counts[join_quality] += 1

        analysis_class = proposal_analysis_class(role, entry_price, quantity)
        support_quality = "HIGH"
        if analysis_class == "RESERVATION_ONLY":
            support_quality = "LOW"
        elif analysis_class == "FORCED_OPEN_SIGNAL_DIAGNOSTIC":
            support_quality = "MEDIUM" if join_quality != "JOIN_NONE" else "LOW"
        elif analysis_class == "UNREPLAYABLE_OR_LOW_SUPPORT":
            support_quality = "LOW"

        linked_entry_ids = []
        for key, matches in proposal_index.items():
            if key in {row.get("rid"), row.get("lifecycle_id"), row.get("reservation_id"), row.get("client_order_id"), row.get("order_id")}:
                linked_entry_ids.extend([as_text(match.get("entry_id")) for match in matches if as_text(match.get("entry_id"))])
        linked_entry_id = linked_entry_ids[0] if linked_entry_ids else ""

        fill_status = "DIAGNOSTIC_ONLY" if analysis_class == "FORCED_OPEN_SIGNAL_DIAGNOSTIC" else ("RESERVATION_ONLY" if analysis_class == "RESERVATION_ONLY" else "NOT_FILLED")
        close_reason_primary = ""
        close_reason_secondary = ""
        close_price_primary = None
        close_price_secondary = None
        close_ts_primary = None
        close_ts_secondary = None
        bars_held_primary = None
        gross_pnl_pct_primary = None
        gross_pnl_usd_primary = None
        net_pnl_pct_primary = None
        net_pnl_usd_primary = None
        mfe_pct = None
        mae_pct = None
        protective_vs_harmful = "indeterminate"
        notes: list[str] = []

        if role == "reservation_intent":
            notes.append("exposure_guard_reservation")
        elif role == "decision_reject":
            notes.append(row.get("deny_reason") or row.get("nrr_code") or "decision_reject")
        elif role == "trade_intent":
            if entry_price is None:
                notes.append("missing_explicit_price")
            else:
                filled, fill_ts_ms, fill_bar, fill_idx = scan_limit_fill(symbol, side, entry_price, timestamp_ms, entry_ttl_ms, bars_by_symbol)
                if filled and fill_bar is not None and fill_ts_ms is not None:
                    fill_status = "FILLED_WITHIN_TTL"
                    close_horizon_ts = None
                    symbol_profile = (config.get("symbol_profiles") or {}).get(symbol) or {}
                    max_hold_sec = safe_int(symbol_profile.get("max_hold_sec"))
                    if max_hold_sec is not None:
                        close_horizon_ts = fill_ts_ms + (max_hold_sec * 1000)
                    tpsl = compute_tpsl_geometry(symbol, side, entry_price, as_text(row.get("regime")), config)
                    if tpsl.get("status") == "OK":
                        tp_sl_path = simulate_tp_sl_path(symbol, side, entry_price, fill_ts_ms, tpsl["stop_price"], tpsl["target_price"], bars_by_symbol, close_horizon_ts)
                        if tp_sl_path.get("status") == "OK":
                            close_reason_primary = as_text(tp_sl_path.get("close_reason_primary"))
                            close_reason_secondary = as_text(tp_sl_path.get("close_reason_secondary"))
                            close_price_primary = safe_float(tp_sl_path.get("close_price_primary"))
                            close_price_secondary = safe_float(tp_sl_path.get("close_price_secondary"))
                            close_ts_primary = safe_int(tp_sl_path.get("close_ts_ms_primary"))
                            close_ts_secondary = safe_int(tp_sl_path.get("close_ts_ms_secondary"))
                            bars_held_primary = safe_int(tp_sl_path.get("bars_considered"))
                            mfe_pct = safe_float(tp_sl_path.get("mfe_pct"))
                            mae_pct = safe_float(tp_sl_path.get("mae_pct"))
                            gross_pnl_pct_primary, gross_pnl_usd_primary, notional = pnl_from_prices(side, entry_price, close_price_primary or entry_price, quantity)
                            if gross_pnl_pct_primary is not None:
                                net_pnl_pct_primary = gross_pnl_pct_primary - (round_trip_cost_bps / 10000.0)
                                if notional is not None:
                                    net_pnl_usd_primary = gross_pnl_usd_primary - (notional * round_trip_cost_bps / 10000.0)
                            if close_reason_primary == "TP_HIT":
                                protective_vs_harmful = "harmful" if role == "decision_reject" and (net_pnl_pct_primary or 0.0) > 0 else "profit"
                            elif close_reason_primary == "SL_HIT":
                                protective_vs_harmful = "protective"
                            else:
                                protective_vs_harmful = "indeterminate"
                            if tp_sl_path.get("ambiguous_intrabar"):
                                notes.append("intrabar_ambiguous_conservative_sl_first")
                        else:
                            close_reason_primary = "UNREPLAYABLE_TPSL"
                            notes.append("tpsl_path_error")
                    else:
                        close_reason_primary = as_text(tpsl.get("status"))
                        notes.append(close_reason_primary)
                else:
                    fill_status = "NOT_FILLED_WITHIN_TTL"
                    close_reason_primary = "ENTRY_TIMEOUT_OR_STALE"
                    close_ts_primary = timestamp_ms + entry_ttl_ms
                    notes.append("entry_not_touched_within_ttl")
                    if fill_bar is not None:
                        notes.append(f"last_observed_bar={iso_utc(fill_bar.timestamp_ms)}")
        elif analysis_class == "FORCED_OPEN_SIGNAL_DIAGNOSTIC":
            if entry_price is not None:
                symbol_profile = (config.get("symbol_profiles") or {}).get(symbol) or {}
                max_hold_sec = safe_int(symbol_profile.get("max_hold_sec"))
                diag_horizon_ts = None if max_hold_sec is None else timestamp_ms + (max_hold_sec * 1000)
                tpsl = compute_tpsl_geometry(symbol, side, entry_price, as_text(row.get("regime")), config)
                if tpsl.get("status") == "OK":
                    tp_sl_path = simulate_tp_sl_path(symbol, side, entry_price, timestamp_ms, tpsl["stop_price"], tpsl["target_price"], bars_by_symbol, diag_horizon_ts)
                    if tp_sl_path.get("status") == "OK":
                        close_reason_primary = as_text(tp_sl_path.get("close_reason_primary"))
                        close_reason_secondary = as_text(tp_sl_path.get("close_reason_secondary"))
                        close_price_primary = safe_float(tp_sl_path.get("close_price_primary"))
                        close_price_secondary = safe_float(tp_sl_path.get("close_price_secondary"))
                        close_ts_primary = safe_int(tp_sl_path.get("close_ts_ms_primary"))
                        close_ts_secondary = safe_int(tp_sl_path.get("close_ts_ms_secondary"))
                        bars_held_primary = safe_int(tp_sl_path.get("bars_considered"))
                        mfe_pct = safe_float(tp_sl_path.get("mfe_pct"))
                        mae_pct = safe_float(tp_sl_path.get("mae_pct"))
                        gross_pnl_pct_primary, gross_pnl_usd_primary, notional = pnl_from_prices(side, entry_price, close_price_primary or entry_price, quantity)
                        if gross_pnl_pct_primary is not None:
                            net_pnl_pct_primary = gross_pnl_pct_primary - (round_trip_cost_bps / 10000.0)
                            if notional is not None:
                                net_pnl_usd_primary = gross_pnl_usd_primary - (notional * round_trip_cost_bps / 10000.0)
                        if close_reason_primary == "TP_HIT":
                            protective_vs_harmful = "harmful" if (net_pnl_pct_primary or 0.0) > 0 else "harmful"
                        elif close_reason_primary == "SL_HIT":
                            protective_vs_harmful = "protective"
                        else:
                            protective_vs_harmful = "indeterminate"
                        if tp_sl_path.get("ambiguous_intrabar"):
                            notes.append("intrabar_ambiguous_conservative_sl_first")
                    else:
                        close_reason_primary = "UNREPLAYABLE_TPSL"
                        notes.append("tpsl_path_error")
                else:
                    close_reason_primary = as_text(tpsl.get("status"))
                    notes.append(close_reason_primary)
        elif analysis_class == "RESERVATION_ONLY":
            notes.append("reservation_not_tradeable")

        evidence_summary = []
        if unique_evidence:
            for match in unique_evidence[:8]:
                raw = match.get("raw") or {}
                evidence_summary.append(
                    f"{as_text(match.get('source_file'))}:{safe_int(match.get('source_line')) or 0}:{as_text(raw.get('event_type')) or as_text(raw.get('event_name'))}"
                )
        bridge_rows.append(
            {
                "proposal_uid": proposal_id,
                "proposal_uid_seed": proposal_seed,
                "source_file": row.get("source_file"),
                "source_line": source_line,
                "timestamp_ms": timestamp_ms,
                "timestamp_iso": iso_utc(timestamp_ms),
                "symbol": symbol,
                "side": side,
                "row_role": role,
                "analysis_class": analysis_class,
                "join_quality": join_quality,
                "support_quality": support_quality,
                "proposal_price": proposal_price,
                "effective_entry_price": entry_price,
                "price_source": price_source,
                "quantity": quantity,
                "entry_order_type": as_text(row.get("entry_order_type")) or config.get("entry_order_type"),
                "entry_tif": as_text(row.get("entry_tif")) or config.get("entry_tif"),
                "ttl_ms": entry_ttl_ms,
                "round_trip_cost_bps": round_trip_cost_bps,
                "sl_pct": first_non_null((config.get("symbol_profiles") or {}).get(symbol, {}).get("sl_pct")),
                "tp_low_ratio": first_non_null((config.get("symbol_profiles") or {}).get(symbol, {}).get("tp_low_ratio")),
                "close_reason_primary": close_reason_primary,
                "close_reason_secondary": close_reason_secondary,
                "close_price_primary": close_price_primary,
                "close_price_secondary": close_price_secondary,
                "close_ts_primary": close_ts_primary,
                "close_ts_secondary": close_ts_secondary,
                "bars_held_primary": bars_held_primary,
                "gross_pnl_pct_primary": gross_pnl_pct_primary,
                "gross_pnl_usd_primary": gross_pnl_usd_primary,
                "net_pnl_pct_primary": net_pnl_pct_primary,
                "net_pnl_usd_primary": net_pnl_usd_primary,
                "mfe_pct": mfe_pct,
                "mae_pct": mae_pct,
                "protective_vs_harmful": protective_vs_harmful,
                "fill_status": fill_status,
                "linked_actual_entry_id": linked_entry_id,
                "evidence_count": len(unique_evidence),
                "evidence_summary": evidence_summary,
                "notes": notes,
                "causal_bar_ts_ms": causal_ts,
                "causal_bar_close": causal_extra.get("causal_bar_close"),
                "entry_fill_ttl_ms": entry_ttl_ms,
                "order_watchdog_fill_ttl_ms": config.get("watchdog_fill_ttl_ms"),
                "strategy_timeframe_sec": config.get("timeframe_sec"),
            }
        )

        casebook.append(bridge_rows[-1])

    return casebook, join_counts, bridge_rows


def build_actual_runtime_casebook(
    reconstructed_entries: list[dict[str, Any]],
    entry_groups: dict[str, Any],
    bars_by_symbol: dict[str, list[Bar]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    open_fee_bps, close_fee_bps, slippage_buffer_bps = resolve_fee_bps(config)
    round_trip_cost_bps = open_fee_bps + close_fee_bps + slippage_buffer_bps
    casebook: list[dict[str, Any]] = []

    for entry in sorted(reconstructed_entries, key=lambda row: (safe_int(row.get("entry_ts_ms")) or 0, as_text(row.get("entry_id")))):
        entry_id = as_text(entry.get("entry_id"))
        symbol = as_text(entry.get("symbol"))
        side = as_text(entry.get("side"))
        entry_ts_ms = safe_int(entry.get("entry_ts_ms")) or 0
        entry_price = safe_float(entry.get("entry_price")) or 0.0
        qty = safe_float(entry.get("qty"))
        close_ts_ms = safe_int(entry.get("close_ts_ms"))
        close_price = safe_float(entry.get("close_price"))
        actual_status = as_text(entry.get("actual_outcome_status"))
        reconstruction_confidence = as_text(entry.get("reconstruction_confidence"))
        timestamp_quality = as_text(entry.get("timestamp_quality"))
        notes = as_text(entry.get("notes"))

        group = entry_groups.get(entry_id)
        intent_rows = getattr(group, "intent_rows", []) if group is not None else []
        placed_rows = getattr(group, "placed_rows", []) if group is not None else []
        entry_fill_rows = getattr(group, "entry_fill_rows", []) if group is not None else []
        close_fill_rows = getattr(group, "close_fill_rows", []) if group is not None else []
        timeout_rows = getattr(group, "timeout_rows", []) if group is not None else []
        cancel_rows = getattr(group, "cancel_rows", []) if group is not None else []

        linked_proposal_uids = []
        linked_proposal_lines = []
        for row_group in intent_rows + placed_rows + entry_fill_rows + close_fill_rows + timeout_rows + cancel_rows:
            payload = row_group.payload if hasattr(row_group, "payload") else row_group
            linked_proposal_uids.append(proposal_uid(payload, config.get("strategy_id") or "aurora"))
            linked_proposal_lines.append(safe_int(payload.get("source_line")) or 0)

        symbol_profile = (config.get("symbol_profiles") or {}).get(symbol) or {}
        max_hold_sec = safe_int(symbol_profile.get("max_hold_sec"))
        close_horizon_ts = None if max_hold_sec is None else entry_ts_ms + (max_hold_sec * 1000)
        tpsl = compute_tpsl_geometry(symbol, side, entry_price, as_text(entry.get("regime")) or "", config)
        replay_status = "UNREPLAYABLE"
        replay_reason_primary = ""
        replay_reason_secondary = ""
        replay_close_price_primary = None
        replay_close_price_secondary = None
        replay_close_ts_primary = None
        replay_close_ts_secondary = None
        replay_mfe_pct = None
        replay_mae_pct = None
        replay_bars = None
        match_kind = "NO_MATCH"
        actual_close_reason = ""

        if actual_status not in {"OPEN", "OPEN_WITH_CANCEL_TIMEOUT_ARTIFACTS", "CLOSE_FILL_ONLY"}:
            actual_close_reason = actual_status

        if tpsl.get("status") == "OK":
            tp_sl_path = simulate_tp_sl_path(symbol, side, entry_price, entry_ts_ms, tpsl["stop_price"], tpsl["target_price"], bars_by_symbol, close_horizon_ts)
            if tp_sl_path.get("status") == "OK":
                replay_status = "OK"
                replay_reason_primary = as_text(tp_sl_path.get("close_reason_primary"))
                replay_reason_secondary = as_text(tp_sl_path.get("close_reason_secondary"))
                replay_close_price_primary = safe_float(tp_sl_path.get("close_price_primary"))
                replay_close_price_secondary = safe_float(tp_sl_path.get("close_price_secondary"))
                replay_close_ts_primary = safe_int(tp_sl_path.get("close_ts_ms_primary"))
                replay_close_ts_secondary = safe_int(tp_sl_path.get("close_ts_ms_secondary"))
                replay_mfe_pct = safe_float(tp_sl_path.get("mfe_pct"))
                replay_mae_pct = safe_float(tp_sl_path.get("mae_pct"))
                replay_bars = safe_int(tp_sl_path.get("bars_considered"))
                if actual_close_reason:
                    if "SL" in actual_close_reason and replay_reason_primary == "SL_HIT":
                        match_kind = "MATCH_SL"
                    elif "TP" in actual_close_reason and replay_reason_primary == "TP_HIT":
                        match_kind = "MATCH_TP"
                    elif "TIMEOUT" in actual_close_reason and replay_reason_primary in {"OBSERVATION_END", "ENTRY_TIMEOUT_OR_STALE"}:
                        match_kind = "MATCH_TIMEOUT"
                    elif replay_reason_primary == actual_close_reason:
                        match_kind = "MATCH_REASON"
                    else:
                        match_kind = "MISMATCH"
                else:
                    match_kind = "NO_ACTUAL_CLOSE_REASON"
                gross_pnl_pct, gross_pnl_usd, notional = pnl_from_prices(side, entry_price, replay_close_price_primary or entry_price, qty)
                net_pnl_pct = None if gross_pnl_pct is None else gross_pnl_pct - (round_trip_cost_bps / 10000.0)
                net_pnl_usd = None if gross_pnl_usd is None or notional is None else gross_pnl_usd - (notional * round_trip_cost_bps / 10000.0)
            else:
                replay_status = as_text(tp_sl_path.get("status")) or "UNREPLAYABLE"
                match_kind = "NO_MATCH"
                replay_reason_primary = replay_status
                replay_close_price_primary = None
                replay_close_ts_primary = None
                replay_reason_secondary = replay_reason_primary
                replay_close_price_secondary = replay_close_price_primary
                replay_close_ts_secondary = replay_close_ts_primary
                replay_mfe_pct = None
                replay_mae_pct = None
                replay_bars = None
                gross_pnl_pct = None
                gross_pnl_usd = None
                net_pnl_pct = None
                net_pnl_usd = None
        else:
            replay_status = as_text(tpsl.get("status"))
            replay_reason_primary = replay_status
            replay_reason_secondary = replay_status
            gross_pnl_pct = None
            gross_pnl_usd = None
            net_pnl_pct = None
            net_pnl_usd = None
            net_pnl_usd = None
            replay_close_price_primary = None
            replay_close_ts_primary = None
            replay_close_price_secondary = None
            replay_close_ts_secondary = None

        casebook.append(
            {
                "entry_id": entry_id,
                "symbol": symbol,
                "side": side,
                "entry_ts_ms": entry_ts_ms,
                "entry_ts_iso": iso_utc(entry_ts_ms),
                "entry_price": entry_price,
                "qty": qty,
                "close_ts_ms": close_ts_ms,
                "close_ts_iso": iso_utc(close_ts_ms),
                "close_price": close_price,
                "actual_outcome_status": actual_status,
                "actual_close_reason": actual_close_reason,
                "reconstruction_confidence": reconstruction_confidence,
                "timestamp_quality": timestamp_quality,
                "notes": notes,
                "linked_proposal_uids": linked_proposal_uids,
                "linked_proposal_source_lines": linked_proposal_lines,
                "replay_status": replay_status,
                "replay_reason_primary": replay_reason_primary,
                "replay_reason_secondary": replay_reason_secondary,
                "replay_close_price_primary": replay_close_price_primary,
                "replay_close_price_secondary": replay_close_price_secondary,
                "replay_close_ts_primary": replay_close_ts_primary,
                "replay_close_ts_secondary": replay_close_ts_secondary,
                "replay_bars": replay_bars,
                "replay_mfe_pct": replay_mfe_pct,
                "replay_mae_pct": replay_mae_pct,
                "gross_pnl_pct": gross_pnl_pct,
                "gross_pnl_usd": gross_pnl_usd,
                "net_pnl_pct": net_pnl_pct,
                "net_pnl_usd": net_pnl_usd,
                "match_kind": match_kind,
                "round_trip_cost_bps": round_trip_cost_bps,
                "max_hold_sec": max_hold_sec,
            }
        )

    return casebook


def summarize_casebook(casebook: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in casebook:
        counter[as_text(row.get(key))] += 1
    return counter


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# AGENT REPORT V1",
        "",
        "## Scope",
        f"- Source log: {summary['source_log_path']}",
        f"- Raw rows: {summary['raw_rows_total']}",
        f"- Proposal rows: {summary['proposal_rows_total']}",
        f"- Evidence rows: {summary['evidence_rows_total']}",
        f"- Reconstructed actual entries: {summary['actual_runtime_entries_total']}",
        f"- Recorder symbols covered at 300s: {', '.join(sorted(summary['bar_coverage_symbols']))}",
        "",
        "## Main Findings",
        f"- Entry replay TTL used for LIMIT+GTX orders: {summary['watchdog_fill_ttl_ms']} ms.",
        f"- Deterministic TP/SL geometry supported for {summary['tpsl_supported_count']} proposal rows.",
        f"- Protective rejects: {summary['protective_rejects']}.",
        f"- Harmful rejects: {summary['harmful_rejects']}.",
        f"- Indeterminate rejects: {summary['indeterminate_rejects']}.",
        f"- Actual runtime matches (replay vs reconstructed close reason): {summary['actual_replay_matches']} of {summary['actual_runtime_close_reason_comparable_total']} comparable entries.",
        "",
        "## Outcome Mix",
        f"- Proposal close reasons: {json.dumps(summary['proposal_close_reason_counts'], ensure_ascii=False, sort_keys=True)}",
        f"- Replay close reasons on reconstructed actual entries: {json.dumps(summary['actual_close_reason_counts'], ensure_ascii=False, sort_keys=True)}",
        f"- Join quality counts: {json.dumps(summary['join_quality_counts'], ensure_ascii=False, sort_keys=True)}",
        "",
        "## Evidence",
        f"- Trade lifecycle sidecar matches: {summary['trade_lifecycle_matches']}",
        f"- Shadow journal matches: {summary['shadow_journal_matches']}",
        f"- Optional aurora_events.jsonl: absent in this workspace.",
        "",
        "## Caveats",
        "- Rejected rows without explicit price were replayed as forced-diagnostic opens using the nearest causal 300s bar close; those rows are not treated as executable PnL.",
        "- Conservative intrabar resolution chooses SL first when TP and SL land in the same candle; the optimistic secondary path is recorded separately.",
        "- Rows with no explicit max-hold exit remain observation-bounded rather than silently assigned an invented timeout.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only order_log_v1 counterfactual replay audit")
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--order-log", type=Path, default=ORDER_LOG_PATH)
    parser.add_argument("--recorder-root", type=Path, default=RECORDER_ROOT)
    args = parser.parse_args(argv)

    report_root = args.report_root
    ensure_clean_dir(report_root)

    config = load_config_snapshot()
    write_json_file(report_root / "config_snapshot.json", config)

    raw_rows = load_order_log_rows(args.order_log)
    normalized_rows: list[dict[str, Any]] = []
    proposal_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()

    for row in raw_rows:
        normalized = build_normalized_row(row, config["strategy_id"], config)
        normalized_rows.append(normalized)
        candidate_ids.update(normalized.get("source_identity_values") or [])
        if normalized["row_kind"] == "proposal":
            proposal_rows.append(normalized)
        elif normalized["row_kind"] == "evidence":
            evidence_rows.append(normalized)

    order_log_evidence_index = build_identity_index(evidence_rows)
    trade_lifecycle_rows = load_relevant_sidecar_rows(TRADE_LIFECYCLE_PATH, candidate_ids)
    shadow_rows = load_relevant_sidecar_rows(SHADOW_JOURNAL_PATH, candidate_ids)
    sidecar_index = index_records_by_id(trade_lifecycle_rows + shadow_rows)

    authority_rows = [
        AuthorityRow(
            source_file=row["source_file"],
            source_line=row["source_line"],
            payload={k: v for k, v in row.items() if k not in {"source_file", "source_line"}},
            timestamp_ms=first_non_null(safe_int(row.get("timestamp_ms")), safe_int(row.get("timestamp"))),
            timestamp_iso=iso_utc(first_non_null(safe_int(row.get("timestamp_ms")), safe_int(row.get("timestamp")))),
            timestamp_quality="exact",
            timestamp_source="order_log_timestamp",
            timestamp_support="live_log",
            sequence_token=f"{safe_int(row.get('source_line')) or 0:08d}",
        )
        for row in raw_rows
    ]

    strategy_context = {
        "instruments": {
            symbol: {
                "target_leverage": safe_float((config.get("root", {}).get("strategies", {}).get("aurora", {}).get("assets", {}).get(symbol, {}) or {}).get("leverage")),
                "margin_mode": as_text((config.get("root", {}).get("trading", {}).get("execution", {}) or {}).get("margin_mode")),
            }
            for symbol in (config.get("symbol_profiles") or {})
        },
        "fees": config.get("fees") or {},
    }

    reconstructed_entries, unresolved_rows, entry_groups = reconstruct_entries(authority_rows, strategy_context, COMMON_RECONSTRUCTION_ROOT)

    proposal_to_entry_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in reconstructed_entries:
        entry_id = as_text(entry.get("entry_id"))
        if not entry_id:
            continue
        group = entry_groups.get(entry_id)
        if group is None:
            continue
        group_rows = (
            getattr(group, "intent_rows", [])
            + getattr(group, "reservation_rows", [])
            + getattr(group, "placed_rows", [])
            + getattr(group, "entry_fill_rows", [])
            + getattr(group, "close_fill_rows", [])
            + getattr(group, "position_closed_rows", [])
            + getattr(group, "timeout_rows", [])
            + getattr(group, "cancel_rows", [])
        )
        for group_row in group_rows:
            payload = group_row.payload if hasattr(group_row, "payload") else group_row
            for _, identity in collect_identity_fields(payload):
                proposal_to_entry_index[identity].append({"entry_id": entry_id, "entry": entry})

    bars_by_symbol, bar_coverage = load_bars_300(args.recorder_root)

    proposal_casebook, join_counts, bridge_rows = build_proposal_casebook(
        proposal_rows=proposal_rows,
        proposal_index=proposal_to_entry_index,
        order_log_evidence_index=order_log_evidence_index,
        sidecar_index=sidecar_index,
        bars_by_symbol=bars_by_symbol,
        config=config,
    )

    actual_runtime_casebook = build_actual_runtime_casebook(
        reconstructed_entries=reconstructed_entries,
        entry_groups=entry_groups,
        bars_by_symbol=bars_by_symbol,
        config=config,
    )

    proposal_close_reason_counts = Counter(as_text(row.get("close_reason_primary")) or "UNSET" for row in proposal_casebook)
    actual_close_reason_counts = Counter(as_text(row.get("replay_reason_primary")) or "UNSET" for row in actual_runtime_casebook)
    proposal_analysis_counts = Counter(as_text(row.get("analysis_class")) for row in bridge_rows)
    protective_rejects = sum(1 for row in bridge_rows if row.get("row_role") == "decision_reject" and row.get("protective_vs_harmful") == "protective")
    harmful_rejects = sum(1 for row in bridge_rows if row.get("row_role") == "decision_reject" and row.get("protective_vs_harmful") == "harmful")
    indeterminate_rejects = sum(1 for row in bridge_rows if row.get("row_role") == "decision_reject" and row.get("protective_vs_harmful") == "indeterminate")
    tpsl_supported_count = sum(1 for row in bridge_rows if row.get("close_reason_primary") in {"TP_HIT", "SL_HIT", "OBSERVATION_END", "ENTRY_TIMEOUT_OR_STALE"})
    actual_runtime_close_reason_comparable_total = sum(1 for row in actual_runtime_casebook if as_text(row.get("actual_close_reason")))
    actual_replay_matches = sum(1 for row in actual_runtime_casebook if row.get("match_kind") in {"MATCH_SL", "MATCH_TP", "MATCH_TIMEOUT", "MATCH_REASON"})

    runtime_overlap_rows: list[dict[str, Any]] = []
    for row in trade_lifecycle_rows + shadow_rows:
        raw = row.get("raw") or {}
        runtime_overlap_rows.append(
            {
                "source_file": row.get("source_file"),
                "source_line": row.get("source_line"),
                "event_type": as_text(raw.get("event_type") or raw.get("event_name")),
                "record_kind": as_text(raw.get("record_kind")),
                "symbol": as_text(raw.get("symbol")),
                "side": as_text(raw.get("side")),
                "ts_ms": safe_int(raw.get("ts_ms") or raw.get("timestamp") or raw.get("timestamp_ms")),
                "rid": as_text(raw.get("rid")),
                "trace_id": as_text(raw.get("trace_id")),
                "match_ids": row.get("ids") or [],
            }
        )

    summary = {
        "source_log_path": args.order_log.relative_to(ROOT).as_posix(),
        "raw_rows_total": len(raw_rows),
        "proposal_rows_total": len(proposal_rows),
        "evidence_rows_total": len(evidence_rows),
        "actual_runtime_entries_total": len(reconstructed_entries),
        "unresolved_rows_total": len(unresolved_rows),
        "watchdog_fill_ttl_ms": config.get("watchdog_fill_ttl_ms"),
        "bar_coverage_symbols": sorted(bar_coverage.keys()),
        "tpsl_supported_count": tpsl_supported_count,
        "proposal_close_reason_counts": dict(sorted(proposal_close_reason_counts.items())),
        "actual_close_reason_counts": dict(sorted(actual_close_reason_counts.items())),
        "join_quality_counts": dict(sorted(join_counts.items())),
        "proposal_analysis_counts": dict(sorted(proposal_analysis_counts.items())),
        "protective_rejects": protective_rejects,
        "harmful_rejects": harmful_rejects,
        "indeterminate_rejects": indeterminate_rejects,
        "actual_replay_matches": actual_replay_matches,
        "actual_runtime_close_reason_comparable_total": actual_runtime_close_reason_comparable_total,
        "trade_lifecycle_matches": len(trade_lifecycle_rows),
        "shadow_journal_matches": len(shadow_rows),
        "entry_order_type": config.get("entry_order_type"),
        "entry_tif": config.get("entry_tif"),
        "entry_fill_ttl_ms": config.get("watchdog_fill_ttl_ms"),
    }

    write_jsonl_file(report_root / "normalized_rows.jsonl", normalized_rows)
    write_jsonl_file(report_root / "proposal_casebook.jsonl", bridge_rows)
    write_jsonl_file(report_root / "actual_runtime_casebook.jsonl", actual_runtime_casebook)
    write_csv_file(
        report_root / "proposal_casebook.csv",
        [
            "proposal_uid",
            "proposal_uid_seed",
            "source_file",
            "source_line",
            "timestamp_ms",
            "timestamp_iso",
            "symbol",
            "side",
            "row_role",
            "analysis_class",
            "join_quality",
            "support_quality",
            "proposal_price",
            "effective_entry_price",
            "price_source",
            "quantity",
            "entry_order_type",
            "entry_tif",
            "ttl_ms",
            "round_trip_cost_bps",
            "close_reason_primary",
            "close_reason_secondary",
            "close_price_primary",
            "close_price_secondary",
            "close_ts_primary",
            "close_ts_secondary",
            "bars_held_primary",
            "gross_pnl_pct_primary",
            "gross_pnl_usd_primary",
            "net_pnl_pct_primary",
            "net_pnl_usd_primary",
            "mfe_pct",
            "mae_pct",
            "protective_vs_harmful",
            "fill_status",
            "linked_actual_entry_id",
            "evidence_count",
            "evidence_summary",
            "notes",
        ],
        bridge_rows,
    )
    write_csv_file(
        report_root / "actual_runtime_casebook.csv",
        [
            "entry_id",
            "symbol",
            "side",
            "entry_ts_ms",
            "entry_ts_iso",
            "entry_price",
            "qty",
            "close_ts_ms",
            "close_ts_iso",
            "close_price",
            "actual_outcome_status",
            "reconstruction_confidence",
            "timestamp_quality",
            "notes",
            "linked_proposal_uids",
            "linked_proposal_source_lines",
            "replay_status",
            "replay_reason_primary",
            "replay_reason_secondary",
            "replay_close_price_primary",
            "replay_close_price_secondary",
            "replay_close_ts_primary",
            "replay_close_ts_secondary",
            "replay_bars",
            "replay_mfe_pct",
            "replay_mae_pct",
            "gross_pnl_pct",
            "gross_pnl_usd",
            "net_pnl_pct",
            "net_pnl_usd",
            "match_kind",
            "round_trip_cost_bps",
            "max_hold_sec",
        ],
        actual_runtime_casebook,
    )
    write_csv_file(
        report_root / "runtime_overlap_sanity.csv",
        [
            "source_file",
            "source_line",
            "event_type",
            "record_kind",
            "symbol",
            "side",
            "ts_ms",
            "rid",
            "trace_id",
            "match_ids",
        ],
        runtime_overlap_rows,
    )
    write_json_file(report_root / "bar_coverage.json", bar_coverage)
    write_json_file(report_root / "summary.json", summary)
    write_csv_file(
        report_root / "evidence_join_matrix.csv",
        [
            "proposal_uid",
            "proposal_uid_seed",
            "source_file",
            "source_line",
            "timestamp_ms",
            "timestamp_iso",
            "symbol",
            "side",
            "row_role",
            "analysis_class",
            "join_quality",
            "support_quality",
            "proposal_price",
            "effective_entry_price",
            "price_source",
            "evidence_count",
            "linked_actual_entry_id",
            "evidence_summary",
        ],
        bridge_rows,
    )

    (report_root / "AGENT_REPORT_V1.md").write_text(render_report(summary), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())