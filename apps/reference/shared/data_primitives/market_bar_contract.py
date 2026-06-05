from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

MARKET_BAR_CORE_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "datetime",
    "symbol",
    "tf_sec",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "source_mode",
    "close_boundary_ts_ms",
    "gap_state",
    "gap_policy_action",
    "gap_bars_skipped",
    "is_gap_bar",
    "ready",
    "not_ready_reasons",
    "pm_norm",
    "pm_raw",
    "pm_norm_10s",
    "pm_norm_60s",
    "pm_norm_300s",
    "pm_norm_900s",
    "regime",
    "regime_conf",
    "regime_join_status",
    "regime_join_mode",
    "regime_event_ts_ms",
    "regime_last_update_ts_ms",
    "regime_age_ms",
    "regime_layer",
    "regime_scope",
    "regime_owner",
    "regime_source_model",
    "regime_structural_regime_ref",
    "regime_warmup_full_ready",
    "regime_warmup_reasons",
    "regime_data_drops",
    "regime_data_notes",
)

MARKET_BAR_CORE_DTYPES: dict[str, str] = {
    "timestamp": "Int64",
    "datetime": "string",
    "symbol": "string",
    "tf_sec": "Int64",
    "open": "string",
    "high": "string",
    "low": "string",
    "close": "string",
    "volume": "string",
    "trade_count": "Int64",
    "source_mode": "string",
    "close_boundary_ts_ms": "Int64",
    "gap_state": "string",
    "gap_policy_action": "string",
    "gap_bars_skipped": "Int64",
    "is_gap_bar": "boolean",
    "ready": "boolean",
    "not_ready_reasons": "string",
    "pm_norm": "string",
    "pm_raw": "string",
    "pm_norm_10s": "float64",
    "pm_norm_60s": "float64",
    "pm_norm_300s": "float64",
    "pm_norm_900s": "float64",
    "regime": "string",
    "regime_conf": "float64",
    "regime_join_status": "string",
    "regime_join_mode": "string",
    "regime_event_ts_ms": "Int64",
    "regime_last_update_ts_ms": "Int64",
    "regime_age_ms": "Int64",
    "regime_layer": "string",
    "regime_scope": "string",
    "regime_owner": "string",
    "regime_source_model": "string",
    "regime_structural_regime_ref": "string",
    "regime_warmup_full_ready": "boolean",
    "regime_warmup_reasons": "string",
    "regime_data_drops": "string",
    "regime_data_notes": "string",
}

RECORDER_FEATURE_COLUMNS: tuple[str, ...] = (
    "feat_price",
    "feat_obi",
    "feat_tfi",
    "feat_delta_price",
    "feat_absorption",
    "feat_liquidity_kappa",
    "feat_ema_bias",
    "feat_volume_spike",
    "feat_volatility_state",
    "feat_depth_imbalance",
    "feat_macro_sync",
    "feat_spread_bps",
    "feat_large_trade_imbalance",
    "feat_volume_zscore",
    "feat_macro_resid",
    "feat_regime",
    "feat_regime_conf",
    "feat_regime_age_ms",
    "feat_regime_layer",
    "feat_pillar_sum",
    "feat_pillar_tactician",
    "feat_pillar_operator",
    "feat_pillar_strategist",
)

RECORDER_STABLE_COLUMNS: tuple[str, ...] = (
    *MARKET_BAR_CORE_COLUMNS,
    *RECORDER_FEATURE_COLUMNS,
)


def build_stable_recorder_row(row_dict: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    dropped = [key for key in row_dict.keys() if key not in RECORDER_STABLE_COLUMNS]
    normalized: dict[str, Any] = {}
    for column in RECORDER_STABLE_COLUMNS:
        value = row_dict.get(column, "")
        normalized[column] = "" if value is None else value
    return normalized, dropped


def read_named_csv_rows(
    path: str | Path,
    *,
    requested_columns: Iterable[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    csv_path = Path(path)
    requested = [str(column) for column in requested_columns]
    rows: list[dict[str, str]] = []
    accounting: dict[str, Any] = {
        "path": str(csv_path),
        "header": [],
        "available_columns": [],
        "missing_columns": [],
        "rows_read": 0,
        "rows_returned": 0,
        "bad_lines": 0,
    }
    if not csv_path.exists():
        return rows, accounting

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        accounting["header"] = header
        accounting["available_columns"] = [column for column in requested if column in header]
        accounting["missing_columns"] = [column for column in requested if column not in header]
        for row in reader:
            accounting["rows_read"] += 1
            if row is None:
                accounting["bad_lines"] += 1
                continue
            if None in row:
                accounting["bad_lines"] += 1
            rows.append({column: row.get(column, "") for column in accounting["available_columns"]})
    accounting["rows_returned"] = len(rows)
    return rows, accounting
