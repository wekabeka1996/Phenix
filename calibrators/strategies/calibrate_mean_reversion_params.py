#!/usr/bin/env python3
"""Production-grade Mean Reversion parameter calibrator.

This tool calibrates the active Mean Reversion parameter surface against
recorder bars, evaluates baseline versus candidate across train/validation/
forward windows, emits overlay-only artifacts, and never mutates canonical
YAML automatically.
"""

from __future__ import annotations
import yaml
import pandas as pd

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any, Sequence
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


NEGATIVE_FLOOR = -1.0e18
PARAM_KEYS = (
    "bb_window",
    "bb_num_std",
    "entry_threshold",
    "sl_atr_mult",
    "cooldown_sec",
    "min_bb_width",
    "max_bb_width",
)
SEARCH_BOUNDS: dict[str, dict[str, Any]] = {
    "bb_window": {
        "kind": "int",
        "min": 10,
        "max": 60,
        "scale_low": 0.75,
        "scale_high": 1.25,
    },
    "bb_num_std": {
        "kind": "float",
        "min": 1.2,
        "max": 3.5,
        "scale_low": 0.8,
        "scale_high": 1.2,
        "precision": 4,
    },
    "entry_threshold": {
        "kind": "float",
        "min": 0.01,
        "max": 0.40,
        "scale_low": 0.7,
        "scale_high": 1.3,
        "precision": 6,
    },
    "sl_atr_mult": {
        "kind": "float",
        "min": 0.5,
        "max": 4.0,
        "scale_low": 0.75,
        "scale_high": 1.25,
        "precision": 4,
    },
    "cooldown_sec": {
        "kind": "int",
        "min": 0,
        "max": 3600,
        "scale_low": 0.5,
        "scale_high": 1.5,
    },
    "min_bb_width": {
        "kind": "float",
        "min": 0.0001,
        "max": 0.05,
        "scale_low": 0.7,
        "scale_high": 1.3,
        "precision": 6,
    },
    "max_bb_width": {
        "kind": "float",
        "min": 0.01,
        "max": 0.30,
        "scale_low": 0.7,
        "scale_high": 1.3,
        "precision": 6,
    },
}

_LOAD_RECORDER_ROWS: Any | None = None
_MR_STRATEGY_CONFIG: Any | None = None
_MEAN_REVERSION_STRATEGY: Any | None = None
_BAR: Any | None = None
_FLAT_REGIME_THRESHOLDS: Any | None = None


class CalibrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.details = dict(details or {})


@dataclass(frozen=True)
class SearchCfg:
    trials: int
    top_k: int
    horizon_bars: int
    cost_bps_roundtrip: float


@dataclass(frozen=True)
class GuardrailCfg:
    min_trades: int
    max_drawdown_ratio: float
    min_train_days: int
    min_activity_ratio: float
    max_activity_ratio: float


@dataclass(frozen=True)
class WindowSpec:
    train_days: list[str]
    validation_days: list[str]
    forward_days: list[str]


def _require_mean_reversion_runtime() -> None:
    global _LOAD_RECORDER_ROWS, _MR_STRATEGY_CONFIG, _MEAN_REVERSION_STRATEGY, _BAR, _FLAT_REGIME_THRESHOLDS

    if (
        _LOAD_RECORDER_ROWS is not None
        and _MR_STRATEGY_CONFIG is not None
        and _MEAN_REVERSION_STRATEGY is not None
        and _BAR is not None
        and _FLAT_REGIME_THRESHOLDS is not None
    ):
        return

    try:
        from tools.objective_calibration.extract_recorder import load_recorder_rows  # type: ignore
        from apps.reference.domains.feature_engineering.bar_resampler import Bar  # type: ignore
        from apps.reference.domains.feature_engineering.mean_reversion_strategy import (  # type: ignore
            MRStrategyConfig,
            MeanReversion1mStrategy,
        )
        from apps.reference.domains.feature_engineering.regime_mapping import (  # type: ignore
            FlatRegimeThresholds,
        )
    except Exception as exc:  # pragma: no cover
        raise CalibrationError(
            "RUNTIME_IMPORT_BLOCKED",
            f"Mean Reversion calibration requires runtime imports to succeed. Import error: {exc}",
        ) from exc

    _LOAD_RECORDER_ROWS = load_recorder_rows
    _MR_STRATEGY_CONFIG = MRStrategyConfig
    _MEAN_REVERSION_STRATEGY = MeanReversion1mStrategy
    _BAR = Bar
    _FLAT_REGIME_THRESHOLDS = FlatRegimeThresholds


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _score_or_floor(value: float | None) -> float:
    if value is None or not math.isfinite(float(value)):
        return NEGATIVE_FLOOR
    return float(value)


def _default_out_dir(args: argparse.Namespace) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scope = "-".join(str(symbol).upper() for symbol in args.symbols)
    safe_scope = scope.replace("/", "_").replace(" ", "_")[:120]
    return Path("reports") / "calibration" / "mean_reversion" / f"{stamp}_{safe_scope}"


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CalibrationError(
            "CONFIG_INVALID",
            f"Unable to coerce numeric config value to Decimal: {value}",
        ) from exc


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "null", "None"):
        return None
    return _to_decimal(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _annotate_day_utc(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["day_utc"] = pd.Series(dtype=str)
        return out
    out = df.copy()
    out["day_utc"] = pd.to_datetime(
        out["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    return out


def _unique_days(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    if "day_utc" not in df.columns:
        df = _annotate_day_utc(df)
    return sorted(df["day_utc"].astype(str).unique().tolist())


def _recompute_segments(df: pd.DataFrame, *, basis_tf_sec: int) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["gap_reset"] = False
        out["segment_id"] = 0
        return out
    out = df.sort_values(["symbol", "timestamp"], kind="mergesort").copy()
    out["_prev_ts"] = out.groupby("symbol")["timestamp"].shift(1)
    out["_gap_ms"] = out["timestamp"] - out["_prev_ts"]
    out["gap_reset"] = out["_gap_ms"] > (int(basis_tf_sec) * 2 * 1000)
    out["segment_id"] = out.groupby("symbol")["gap_reset"].cumsum().astype(int)
    out = out.drop(columns=["_prev_ts", "_gap_ms"])
    return out.reset_index(drop=True)


def _resolve_windows(
    df: pd.DataFrame,
    *,
    validation_days: int,
    forward_days: int,
    min_train_days: int,
) -> WindowSpec:
    days = _unique_days(df)
    required_days = int(validation_days) + \
        int(forward_days) + int(min_train_days)
    if len(days) < required_days:
        raise CalibrationError(
            "INSUFFICIENT_DATA",
            (
                "Not enough unique days for train/validation/forward split. "
                f"Need at least {required_days}, found {len(days)}."
            ),
            details={
                "required_days": required_days,
                "available_days": len(days),
                "validation_days": int(validation_days),
                "forward_days": int(forward_days),
                "min_train_days": int(min_train_days),
            },
        )
    forward = days[-int(forward_days):]
    validation_end = len(days) - int(forward_days)
    validation_start = validation_end - int(validation_days)
    validation = days[validation_start:validation_end]
    train = days[:validation_start]
    if len(train) < int(min_train_days):
        raise CalibrationError(
            "INSUFFICIENT_DATA",
            f"Train window too small after holdouts. Need at least {min_train_days} days, found {len(train)}.",
            details={"train_days": train},
        )
    return WindowSpec(train_days=train, validation_days=validation, forward_days=forward)


def _slice_window(df: pd.DataFrame, days: list[str]) -> pd.DataFrame:
    if not days:
        return df.iloc[0:0].copy()
    if "day_utc" not in df.columns:
        df = _annotate_day_utc(df)
    out = df[df["day_utc"].isin(set(days))].copy()
    sort_cols = ["symbol", "segment_id", "timestamp"] if "segment_id" in out.columns else [
        "symbol",
        "timestamp",
    ]
    return out.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def _longest_segment_rows(df_symbol: pd.DataFrame) -> int:
    if df_symbol.empty:
        return 0
    if "segment_id" not in df_symbol.columns:
        return int(len(df_symbol))
    lengths = df_symbol.groupby("segment_id", sort=False).size()
    if lengths.empty:
        return 0
    return int(lengths.max())


def _window_stats(df_window: pd.DataFrame, *, symbols: list[str]) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "rows": int(len(df_window)),
        "unique_days": _unique_days(df_window),
        "per_symbol": {},
    }
    for symbol in symbols:
        sdf = df_window[df_window["symbol"].astype(str) == symbol].copy()
        stats["per_symbol"][symbol] = {
            "rows": int(len(sdf)),
            "longest_segment_rows": _longest_segment_rows(sdf),
            "segments": int(sdf["segment_id"].nunique())
            if "segment_id" in sdf.columns and not sdf.empty
            else (1 if not sdf.empty else 0),
        }
    return stats


def _validate_window_coverage(window_name: str, stats: dict[str, Any], *, required_rows: int) -> None:
    blockers: list[dict[str, Any]] = []
    for symbol, payload in stats.get("per_symbol", {}).items():
        if int(payload.get("rows", 0)) < required_rows or int(payload.get("longest_segment_rows", 0)) < required_rows:
            blockers.append(
                {
                    "symbol": str(symbol),
                    "rows": int(payload.get("rows", 0)),
                    "longest_segment_rows": int(payload.get("longest_segment_rows", 0)),
                    "required_rows": int(required_rows),
                }
            )
    if blockers:
        raise CalibrationError(
            "INSUFFICIENT_DATA",
            f"{window_name} window lacks contiguous history for Mean Reversion warmup.",
            details={"window": window_name, "blockers": blockers},
        )


def _dataset_fingerprint(df: pd.DataFrame) -> str:
    if df.empty:
        return "empty"
    key_columns = ["symbol", "timestamp",
                   "open", "high", "low", "close", "volume"]
    if "regime" in df.columns:
        key_columns.append("regime")
    hashed = pd.util.hash_pandas_object(
        df[key_columns].reset_index(drop=True), index=False)
    return hashlib.sha256(hashed.values.tobytes()).hexdigest()


def _load_mean_reversion_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("mean_reversion"), dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            f"Invalid mean_reversion strategy YAML (expected top-level 'mean_reversion'): {path}",
        )
    out = dict(raw["mean_reversion"])
    if not bool(out.get("enabled", False)):
        raise CalibrationError(
            "CONFIG_INVALID",
            f"Mean Reversion strategy is disabled in {path}.",
        )
    return out


def _load_assigned_symbols(path: Path, *, strategy_id: str) -> list[str]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assignments = raw.get("assignments") if isinstance(raw, dict) else None
    if not isinstance(assignments, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            f"Invalid strategies registry assignments block: {path}",
        )
    out: list[str] = []
    for symbol, strategy_list in assignments.items():
        if not isinstance(strategy_list, list):
            continue
        if str(strategy_id) in [str(item) for item in strategy_list]:
            out.append(str(symbol).upper())
    return sorted(out)


def _allowed_regimes(root_cfg: dict[str, Any], symbol: str) -> list[str]:
    assets = root_cfg.get("assets") or {}
    asset_cfg = assets.get(symbol) if isinstance(assets, dict) else {}
    regimes = (asset_cfg or {}).get(
        "allowed_regimes") or root_cfg.get("allowed_regimes") or []
    return [str(regime) for regime in regimes]


def _extract_effective_symbol_cfg(root_cfg: dict[str, Any], symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    assets = root_cfg.get("assets")
    if not isinstance(assets, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "mean_reversion.assets must be present and object-shaped.",
        )
    asset_cfg = assets.get(symbol)
    if not isinstance(asset_cfg, dict):
        raise CalibrationError(
            "SCOPE_INVALID",
            f"Requested symbol {symbol} is missing from mean_reversion.assets.",
            details={"symbol": symbol},
        )
    if not bool(asset_cfg.get("enabled", False)):
        raise CalibrationError(
            "SCOPE_INVALID",
            f"Requested symbol {symbol} is disabled under mean_reversion.assets.",
            details={"symbol": symbol},
        )
    strategy_root = root_cfg.get("strategy")
    if not isinstance(strategy_root, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "mean_reversion.strategy must be present and object-shaped.",
        )
    out = dict(strategy_root)
    asset_strategy = asset_cfg.get("strategy") or {}
    if not isinstance(asset_strategy, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            f"mean_reversion.assets.{symbol}.strategy must be object-shaped when present.",
        )
    out.update(
        {key: value for key, value in asset_strategy.items() if value is not None})
    out["allowed_regimes"] = _allowed_regimes(root_cfg, symbol)
    return out, asset_cfg


def _extract_baseline_candidate(root_cfg: dict[str, Any], symbols: list[str]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    per_symbol: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        effective_cfg, _asset_cfg = _extract_effective_symbol_cfg(
            root_cfg, symbol)
        candidate = {
            "bb_window": int(effective_cfg["bb_window"]),
            "bb_num_std": float(effective_cfg["bb_num_std"]),
            "entry_threshold": float(effective_cfg["entry_threshold"]),
            "sl_atr_mult": float(effective_cfg["sl_atr_mult"]),
            "cooldown_sec": int(effective_cfg["cooldown_sec"]),
            "min_bb_width": float(effective_cfg["min_bb_width"]),
            "max_bb_width": float(effective_cfg["max_bb_width"]),
        }
        if float(candidate["max_bb_width"]) <= float(candidate["min_bb_width"]):
            raise CalibrationError(
                "CONFIG_INVALID",
                f"Effective Mean Reversion config for {symbol} has max_bb_width <= min_bb_width.",
                details={"symbol": symbol, "candidate": candidate},
            )
        per_symbol[symbol] = candidate
    first_symbol = symbols[0]
    first_signature = _candidate_signature(per_symbol[first_symbol])
    mismatches = {
        symbol: candidate
        for symbol, candidate in per_symbol.items()
        if _candidate_signature(candidate) != first_signature
    }
    if mismatches:
        raise CalibrationError(
            "SCOPE_INVALID",
            "Requested symbols do not share the same effective baseline parameters. Calibrate one Mean Reversion symbol at a time for the common-overlay contract.",
            details={"effective_candidates": per_symbol},
        )
    return dict(per_symbol[first_symbol]), per_symbol


def _build_regime_thresholds(root_cfg: dict[str, Any]) -> Any:
    thresholds = root_cfg.get("regime_thresholds")
    if not isinstance(thresholds, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "mean_reversion.regime_thresholds must be present and object-shaped.",
        )
    high_vol_pct = thresholds.get("high_vol_pct")
    low_vol_pct = thresholds.get("low_vol_pct")
    if high_vol_pct is None or low_vol_pct is None:
        raise CalibrationError(
            "CONFIG_INVALID",
            "mean_reversion.regime_thresholds.high_vol_pct and low_vol_pct are required.",
        )
    return _FLAT_REGIME_THRESHOLDS(
        high_vol_pct=_to_decimal(high_vol_pct),
        low_vol_pct=_to_decimal(low_vol_pct),
    )


def _required_history_rows(root_cfg: dict[str, Any], *, horizon_bars: int) -> int:
    strategy_root = root_cfg.get("strategy") or {}
    min_bars = int(strategy_root.get("min_bars", 25))
    atr_window = int(strategy_root.get("atr_window", 14)) + 1
    rsi_window = int(strategy_root.get("rsi_window", 14)) + 1
    bb_window_cap = int(SEARCH_BOUNDS["bb_window"]["max"])
    return max(min_bars, atr_window, rsi_window, bb_window_cap) + max(1, int(horizon_bars))


def _normalize_recorder_dataset(df: pd.DataFrame, *, tf_sec: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if "regime" not in df.columns:
        df = df.copy()
        df["regime"] = ""
    required_columns = {"symbol", "timestamp",
                        "open", "high", "low", "close", "regime"}
    missing = sorted(required_columns.difference(df.columns))
    if missing:
        raise CalibrationError(
            "DATASET_INVALID",
            f"Recorder dataset missing required columns: {missing}",
            details={"missing_columns": missing},
        )
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if "volume" in out.columns:
        out["volume"] = pd.to_numeric(
            out["volume"], errors="coerce").fillna(0.0)
    else:
        out["volume"] = 0.0
    if "trade_count" in out.columns:
        out["trade_count"] = pd.to_numeric(
            out["trade_count"], errors="coerce").fillna(0).astype(int)
    else:
        out["trade_count"] = 0
    out["regime"] = out["regime"].fillna("").astype(str)
    if "tf_sec" in out.columns:
        out["tf_sec"] = pd.to_numeric(out["tf_sec"], errors="coerce")
        out = out[out["tf_sec"] == int(tf_sec)].copy()
    else:
        out["tf_sec"] = int(tf_sec)
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out["timestamp"] = out["timestamp"].astype("int64")
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    out = _recompute_segments(out, basis_tf_sec=int(tf_sec))
    out = _annotate_day_utc(out)
    return out


def _date_to_ms(day: date, *, end_exclusive: bool) -> int:
    dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if end_exclusive:
        dt = dt + timedelta(days=1)
    return int(dt.timestamp() * 1000)


def _fetch_binance_futures_klines(
    *,
    symbol: str,
    interval: str,
    interval_ms: int,
    start_close_ms: int,
    end_close_ms: int,
    base_url: str,
    timeout_sec: float,
    pause_sec: float,
) -> pd.DataFrame:
    start_open_ms = max(0, int(start_close_ms) - int(interval_ms))
    end_open_ms = int(end_close_ms)
    limit = 1500
    cursor = start_open_ms
    rows: list[list[Any]] = []

    while cursor <= end_open_ms:
        params = {
            "symbol": str(symbol).upper(),
            "interval": str(interval),
            "limit": int(limit),
            "startTime": int(cursor),
            "endTime": int(end_open_ms),
        }
        url = f"{base_url.rstrip('/')}/fapi/v1/klines?{urlencode(params)}"
        # nosec B310 - intentional Binance public endpoint
        with urlopen(url, timeout=float(timeout_sec)) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        last_open = int(payload[-1][0])
        next_cursor = last_open + int(interval_ms)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(payload) < limit:
            break
        if pause_sec > 0:
            import time
            time.sleep(float(pause_sec))

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "symbol": str(symbol).upper(),
            "timestamp": [int(row[6]) for row in rows],
            "open": [float(row[1]) for row in rows],
            "high": [float(row[2]) for row in rows],
            "low": [float(row[3]) for row in rows],
            "close": [float(row[4]) for row in rows],
            "volume": [float(row[5]) for row in rows],
            "tf_sec": 300,
        }
    )
    out = out[(out["timestamp"] >= int(start_close_ms))
              & (out["timestamp"] <= int(end_close_ms))]
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    return out


def _canonicalize_ohlcv_300(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume", "tf_sec"])
    required = {"symbol", "timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise CalibrationError(
            "DATASET_INVALID",
            f"Dataset missing required OHLC columns: {missing}",
            details={"missing_columns": missing},
        )
    out = pd.DataFrame()
    out["symbol"] = df["symbol"].astype(str).str.upper()
    for column in ("timestamp", "open", "high", "low", "close"):
        out[column] = pd.to_numeric(df[column], errors="coerce")
    if "volume" in df.columns:
        out["volume"] = pd.to_numeric(
            df["volume"], errors="coerce").fillna(0.0)
    else:
        out["volume"] = 0.0
    out["tf_sec"] = 300
    out = out[np.isfinite(out["timestamp"])].copy()
    out["timestamp"] = out["timestamp"].astype(np.int64)
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    return out


def _maybe_hydrate_missing_from_binance(
    *,
    local_df: pd.DataFrame,
    symbols: list[str],
    start: date,
    end: date,
    enable: bool,
    lookback_bars: int,
    base_url: str,
    timeout_sec: float,
    pause_sec: float,
) -> pd.DataFrame:
    canonical_local = _canonicalize_ohlcv_300(local_df)
    if not enable:
        return _recompute_segments(canonical_local, basis_tf_sec=300)

    interval_ms = 300_000
    sym_frames: list[pd.DataFrame] = []
    total_added = 0
    start_from_arg = _date_to_ms(start, end_exclusive=False)
    end_from_arg = _date_to_ms(end, end_exclusive=True) - 1

    for symbol in [str(item).upper() for item in symbols]:
        local_sym = canonical_local[canonical_local["symbol"] == symbol].copy()
        local_min = int(local_sym["timestamp"].min()
                        ) if not local_sym.empty else None
        local_max = int(local_sym["timestamp"].max()
                        ) if not local_sym.empty else None
        fetch_start = int(start_from_arg)
        fetch_end = int(end_from_arg)
        if local_min is not None:
            fetch_start = min(fetch_start, int(local_min) -
                              int(lookback_bars) * interval_ms)
        if local_max is not None:
            fetch_end = max(fetch_end, int(local_max))

        print(f"  Binance hydration: {symbol} fetching 5m klines ...")
        remote = _fetch_binance_futures_klines(
            symbol=symbol,
            interval="5m",
            interval_ms=interval_ms,
            start_close_ms=fetch_start,
            end_close_ms=fetch_end,
            base_url=base_url,
            timeout_sec=timeout_sec,
            pause_sec=pause_sec,
        )
        if remote.empty:
            print(f"    {symbol}: Binance returned 0 klines")
            sym_frames.append(local_sym)
            continue

        remote_canonical = _canonicalize_ohlcv_300(remote)
        merged = pd.concat([local_sym, remote_canonical], ignore_index=True)
        merged = merged.drop_duplicates(
            subset=["symbol", "timestamp"], keep="first")
        merged = merged.sort_values(
            ["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
        new_rows = len(merged) - len(local_sym)
        total_added += max(0, new_rows)
        print(
            f"    {symbol}: local={len(local_sym)} + binance_new={max(0, new_rows)} = {len(merged)}")
        sym_frames.append(merged)

    if not sym_frames:
        return _recompute_segments(canonical_local, basis_tf_sec=300)

    combined = pd.concat(sym_frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["symbol", "timestamp"], keep="first")
    combined = combined.sort_values(
        ["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    print(f"  Binance hydration total: +{total_added} rows")
    return _recompute_segments(combined, basis_tf_sec=300)


def _validate_requested_recorder_csvs(
    recorder_dir: Path,
    *,
    start: date,
    end: date,
    symbols: list[str],
    tf_sec: int,
) -> None:
    if not recorder_dir.exists():
        return
    bad_files: list[dict[str, Any]] = []
    for day_dir in sorted(path for path in recorder_dir.iterdir() if path.is_dir()):
        try:
            day = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        if day < start or day >= end:
            continue
        for symbol in symbols:
            csv_path = day_dir / f"{str(symbol).upper()}_{int(tf_sec)}.csv"
            if not csv_path.exists():
                continue
            try:
                pd.read_csv(csv_path)
            except pd.errors.ParserError:
                try:
                    fallback = pd.read_csv(
                        csv_path, engine="python", on_bad_lines="skip")
                    if fallback.empty:
                        bad_files.append(
                            {"path": str(csv_path), "error": "fallback: 0 rows after skipping bad lines"})
                except Exception as exc2:
                    bad_files.append(
                        {"path": str(csv_path), "error": f"fallback failed: {exc2}"})
            except Exception as exc:
                bad_files.append({"path": str(csv_path), "error": str(exc)})
    if bad_files:
        raise CalibrationError(
            "DATASET_INVALID",
            "Recorder CSV parse validation failed for one or more requested files.",
            details={"bad_files": bad_files},
        )


def _build_strategy_cfg(*, params: dict[str, Any], allowed_regimes: list[str]) -> Any:
    return _MR_STRATEGY_CONFIG(
        bb_window=int(params["bb_window"]),
        bb_num_std=float(params["bb_num_std"]),
        atr_window=int(params.get("atr_window", 14)),
        rsi_window=int(params.get("rsi_window", 14)),
        min_bars=int(params.get("min_bars", 25)),
        min_bb_width=_to_decimal(params["min_bb_width"]),
        max_bb_width=_to_decimal(params["max_bb_width"]),
        entry_threshold=_to_decimal(params["entry_threshold"]),
        rsi_oversold=_to_decimal(params.get("rsi_oversold", 30)),
        rsi_overbought=_to_decimal(params.get("rsi_overbought", 70)),
        sl_atr_mult=_to_decimal(params["sl_atr_mult"]),
        tp_to_mid=bool(params.get("tp_to_mid", True)),
        cooldown_sec=int(params["cooldown_sec"]),
        sl_buffer_pct=_to_decimal(params.get("sl_buffer_pct", 0)),
        tp_buffer_pct=_to_decimal(params.get("tp_buffer_pct", 0)),
        allowed_regimes=list(allowed_regimes),
        flat_low_short_min_bb_width=_optional_decimal(
            params.get("flat_low_short_min_bb_width")),
        confidence_base=_to_decimal(params.get("confidence_base", 0.5)),
        confidence_bb_slope=_to_decimal(
            params.get("confidence_bb_slope", 2.0)),
        confidence_rsi_bonus=_to_decimal(
            params.get("confidence_rsi_bonus", 0.2)),
        entry_threshold_long=_optional_decimal(
            params.get("entry_threshold_long")),
        entry_threshold_short=_optional_decimal(
            params.get("entry_threshold_short")),
    )


def _build_bar(row: pd.Series, tf_sec: int) -> Any:
    ts_ms = int(row["timestamp"])
    return _BAR(
        symbol=str(row["symbol"]).upper(),
        timeframe_sec=int(tf_sec),
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=Decimal(str(row.get("volume", 0.0) or 0.0)),
        trade_count=int(row.get("trade_count", 0) or 0),
        start_ts_ms=int(ts_ms - int(tf_sec) * 1000 + 1),
        end_ts_ms=int(ts_ms),
    )


def _simulate_signal_trade(
    *,
    signal_side: str,
    entry_price: Decimal,
    stop_price: Decimal | None,
    target_price: Decimal | None,
    future_bars: pd.DataFrame,
    search_cfg: SearchCfg,
) -> dict[str, Any]:
    horizon = max(1, int(search_cfg.horizon_bars))
    scoped = future_bars.head(horizon).copy()
    if scoped.empty:
        raise CalibrationError(
            "DATASET_INVALID",
            "Signal trade simulation received empty future scope.",
        )

    last_close = Decimal(str(scoped.iloc[-1]["close"]))
    exit_price = last_close
    exit_reason = "FORCED_CLOSE_HORIZON"
    ambiguous = False
    holding_bars = len(scoped)
    mfe = Decimal("0")
    mae = Decimal("0")

    for offset, row in enumerate(scoped.itertuples(index=False), start=1):
        high = Decimal(str(getattr(row, "high")))
        low = Decimal(str(getattr(row, "low")))
        holding_bars = offset

        # MFE/MAE tracking
        if entry_price > 0:
            if str(signal_side).upper() == "BUY":
                favorable = high - entry_price
                adverse = entry_price - low
            else:
                favorable = entry_price - low
                adverse = high - entry_price
            if favorable > mfe:
                mfe = favorable
            if adverse > mae:
                mae = adverse

        if str(signal_side).upper() == "BUY":
            hit_stop = stop_price is not None and low <= stop_price
            hit_target = target_price is not None and high >= target_price
        else:
            hit_stop = stop_price is not None and high >= stop_price
            hit_target = target_price is not None and low <= target_price
        if not hit_stop and not hit_target:
            continue
        ambiguous = bool(hit_stop and hit_target)
        if hit_stop:
            exit_price = Decimal(str(stop_price))
            exit_reason = "TPSL_AMBIGUOUS_STOP_FIRST" if ambiguous else "STOP_PRICE_HIT"
        else:
            exit_price = Decimal(str(target_price))
            exit_reason = "TARGET_PRICE_HIT"
        break

    if entry_price <= 0:
        gross_return_ratio = 0.0
        mfe_ratio = 0.0
        mae_ratio = 0.0
    else:
        if str(signal_side).upper() == "BUY":
            gross_return_ratio = float(
                (exit_price - entry_price) / entry_price)
        else:
            gross_return_ratio = float(
                (entry_price - exit_price) / entry_price)
        mfe_ratio = float(mfe / entry_price)
        mae_ratio = float(mae / entry_price)

    net_return_ratio = gross_return_ratio - \
        (float(search_cfg.cost_bps_roundtrip) / 10000.0)
    return {
        "gross_return_ratio": float(gross_return_ratio),
        "net_return_ratio": float(net_return_ratio),
        "holding_bars": int(holding_bars),
        "exit_reason": exit_reason,
        "ambiguous_tpsl": bool(ambiguous),
        "mfe_ratio": float(mfe_ratio),
        "mae_ratio": float(mae_ratio),
    }


def _max_drawdown_ratio(values: list[float]) -> float:
    if not values:
        return 0.0
    cumulative = 0.0
    running_peak = 0.0
    worst = 0.0
    for value in values:
        cumulative += float(value)
        running_peak = max(running_peak, cumulative)
        worst = min(worst, cumulative - running_peak)
    return abs(worst)


def _metrics_from_trade_records(
    trade_records: list[dict[str, Any]],
    *,
    row_count: int,
    unique_days: list[str],
    entry_count: int,
    signal_count: int,
    guardrails: GuardrailCfg,
) -> dict[str, Any]:
    total_trades = len(trade_records)
    net_return_ratio = float(
        sum(float(item["net_return_ratio"]) for item in trade_records))
    gross_return_ratio = float(
        sum(float(item["gross_return_ratio"]) for item in trade_records))
    wins = sum(1 for item in trade_records if float(
        item["net_return_ratio"]) > 0.0)
    losses = sum(1 for item in trade_records if float(
        item["net_return_ratio"]) < 0.0)
    win_rate = float(wins / total_trades) if total_trades else 0.0
    avg_trade_return_ratio = float(
        net_return_ratio / total_trades) if total_trades else 0.0
    gross_profit = float(
        sum(max(0.0, float(item["net_return_ratio"])) for item in trade_records))
    gross_loss = float(
        abs(sum(min(0.0, float(item["net_return_ratio"])) for item in trade_records)))
    profit_factor = float(
        gross_profit / gross_loss) if gross_loss > 0 else None
    max_drawdown_ratio = _max_drawdown_ratio(
        [float(item["net_return_ratio"]) for item in trade_records])
    calmar_ratio = (
        float(net_return_ratio / max_drawdown_ratio)
        if max_drawdown_ratio > 1.0e-12
        else float(net_return_ratio)
    )
    selection_score = None
    if total_trades >= int(guardrails.min_trades) and max_drawdown_ratio <= float(guardrails.max_drawdown_ratio):
        selection_score = float((net_return_ratio * 10000.0) -
                                (max_drawdown_ratio * 10000.0) + (win_rate * 100.0))
    avg_holding_bars = (
        float(sum(int(item["holding_bars"])
              for item in trade_records) / total_trades)
        if total_trades
        else 0.0
    )
    entries_per_day = float(entry_count / max(1, len(unique_days)))
    forced_close_count = sum(
        1 for item in trade_records if item["exit_reason"] == "FORCED_CLOSE_HORIZON")
    ambiguous_tpsl_count = sum(
        1 for item in trade_records if bool(item["ambiguous_tpsl"]))
    tpsl_exit_count = int(total_trades - forced_close_count)
    return {
        "rows": int(row_count),
        "unique_days": list(unique_days),
        "signal_count": int(signal_count),
        "entry_count": int(entry_count),
        "total_trades": int(total_trades),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": float(win_rate),
        "net_return_ratio": float(net_return_ratio),
        "net_pnl_bps": float(net_return_ratio * 10000.0),
        "gross_return_ratio": float(gross_return_ratio),
        "gross_pnl_bps": float(gross_return_ratio * 10000.0),
        "avg_trade_return_ratio": float(avg_trade_return_ratio),
        "avg_pnl_bps": float(avg_trade_return_ratio * 10000.0),
        "profit_factor": profit_factor,
        "max_drawdown_ratio": float(max_drawdown_ratio),
        "max_drawdown_bps": float(max_drawdown_ratio * 10000.0),
        "calmar_ratio": float(calmar_ratio),
        "selection_score": selection_score,
        "eligible_for_selection": bool(selection_score is not None),
        "avg_holding_bars": float(avg_holding_bars),
        "entries_per_day": float(entries_per_day),
        "forced_close_count": int(forced_close_count),
        "tpsl_exit_count": int(tpsl_exit_count),
        "ambiguous_tpsl_count": int(ambiguous_tpsl_count),
    }


def _evaluate_symbol_window(
    df_symbol: pd.DataFrame,
    *,
    symbol: str,
    root_cfg: dict[str, Any],
    candidate: dict[str, Any],
    tf_sec: int,
    search_cfg: SearchCfg,
    guardrails: GuardrailCfg,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    effective_params, _asset_cfg = _extract_effective_symbol_cfg(
        root_cfg, symbol)
    effective_params.update(candidate)
    allowed_regimes = _allowed_regimes(root_cfg, symbol)
    regime_sizing = dict(root_cfg.get("regime_sizing") or {})
    regime_thresholds = _build_regime_thresholds(root_cfg)

    trade_records: list[dict[str, Any]] = []
    signal_count = 0
    entry_count = 0

    grouped = (
        df_symbol.groupby("segment_id", sort=False)
        if "segment_id" in df_symbol.columns
        else [(0, df_symbol.copy())]
    )
    for _segment_id, segment in grouped:
        ordered = segment.sort_values(
            "timestamp", kind="mergesort").reset_index(drop=True)
        strategy = _MEAN_REVERSION_STRATEGY(
            config=_build_strategy_cfg(
                params=effective_params, allowed_regimes=allowed_regimes),
            timeframe_sec=int(tf_sec),
            regime_sizing=regime_sizing,
            regime_thresholds=regime_thresholds,
        )
        for idx, row in ordered.iterrows():
            symbol_upper = str(row["symbol"]).upper()
            strategy.set_regime(symbol_upper, str(row.get("regime") or ""))
            signal = strategy.on_bar(symbol_upper, _build_bar(
                row, int(tf_sec)), int(row["timestamp"]))
            if signal is None or not signal.is_signal:
                continue
            signal_count += 1
            future = ordered.iloc[idx + 1: idx +
                                  1 + int(search_cfg.horizon_bars)]
            if future.empty:
                continue
            entry_count += 1
            trade_records.append(
                _simulate_signal_trade(
                    signal_side=str(signal.side),
                    entry_price=Decimal(
                        str(signal.entry_price or signal.price)),
                    stop_price=Decimal(
                        str(signal.stop_price)) if signal.stop_price is not None else None,
                    target_price=Decimal(
                        str(signal.target_price)) if signal.target_price is not None else None,
                    future_bars=future,
                    search_cfg=search_cfg,
                )
            )

    metrics = _metrics_from_trade_records(
        trade_records,
        row_count=int(len(df_symbol)),
        unique_days=_unique_days(df_symbol),
        entry_count=int(entry_count),
        signal_count=int(signal_count),
        guardrails=guardrails,
    )
    return metrics, trade_records


def _evaluate_window(
    df_window: pd.DataFrame,
    *,
    symbols: list[str],
    root_cfg: dict[str, Any],
    candidate: dict[str, Any],
    tf_sec: int,
    search_cfg: SearchCfg,
    guardrails: GuardrailCfg,
) -> dict[str, Any]:
    per_symbol: dict[str, dict[str, Any]] = {}
    trade_records: list[dict[str, Any]] = []
    signal_count = 0
    entry_count = 0
    for symbol in symbols:
        df_symbol = df_window[df_window["symbol"] == symbol].copy()
        metrics, trades = _evaluate_symbol_window(
            df_symbol,
            symbol=symbol,
            root_cfg=root_cfg,
            candidate=candidate,
            tf_sec=int(tf_sec),
            search_cfg=search_cfg,
            guardrails=guardrails,
        )
        per_symbol[symbol] = metrics
        trade_records.extend(trades)
        signal_count += int(metrics["signal_count"])
        entry_count += int(metrics["entry_count"])
    aggregate = _metrics_from_trade_records(
        trade_records,
        row_count=int(len(df_window)),
        unique_days=_unique_days(df_window),
        entry_count=int(entry_count),
        signal_count=int(signal_count),
        guardrails=guardrails,
    )
    aggregate["per_symbol"] = per_symbol
    return aggregate


def _candidate_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(candidate["bb_window"]),
        round(float(candidate["bb_num_std"]), 6),
        round(float(candidate["entry_threshold"]), 6),
        round(float(candidate["sl_atr_mult"]), 6),
        int(candidate["cooldown_sec"]),
        round(float(candidate["min_bb_width"]), 6),
        round(float(candidate["max_bb_width"]), 6),
    )


def _mutate_candidate(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    for key, bounds in SEARCH_BOUNDS.items():
        raw = float(
            base[key]) * rng.uniform(float(bounds["scale_low"]), float(bounds["scale_high"]))
        clipped = min(float(bounds["max"]), max(float(bounds["min"]), raw))
        if bounds["kind"] == "int":
            candidate[key] = int(round(clipped))
        else:
            candidate[key] = round(clipped, int(bounds["precision"]))
    if float(candidate["max_bb_width"]) <= float(candidate["min_bb_width"]):
        gap = 0.001
        candidate["max_bb_width"] = round(
            min(float(SEARCH_BOUNDS["max_bb_width"]["max"]), float(
                candidate["min_bb_width"]) + gap),
            6,
        )
    if float(candidate["max_bb_width"]) <= float(candidate["min_bb_width"]):
        candidate["min_bb_width"] = round(
            max(float(SEARCH_BOUNDS["min_bb_width"]["min"]), float(
                candidate["max_bb_width"]) - 0.001),
            6,
        )
    return candidate


def _compute_regime_labels_300s(df: pd.DataFrame) -> pd.Series:
    """Compute regime labels from 5-min OHLCV using production regime detector logic.

    Uses production 5-min parameters directly (no scaling since MR already on 5-min bars):
    SMA short=48, long=192, ATR period=14, baseline=288.
    Priority cascade: VOL → MR → TREND → UNCERTAIN.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = close.shift(1)

    # True Range → Wilder EMA ATR(14) → ATR baseline MA(288)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
    atr_baseline = atr.rolling(288, min_periods=144).mean()
    vol_ratio = atr / atr_baseline

    # SMA short(48) / long(192)
    sma_short = close.rolling(48, min_periods=48).mean()
    sma_long = close.rolling(192, min_periods=192).mean()

    regime = pd.Series("UNCERTAIN", index=df.index)

    # Priority 1: Volatility
    regime = regime.where(~(vol_ratio > 2.0), "HIGH_VOLATILITY")
    regime = regime.where(~((vol_ratio < 0.7) & (
        regime == "UNCERTAIN")), "LOW_VOLATILITY")

    # Priority 2: Mean Reversion (only where still UNCERTAIN)
    mask_unc = regime == "UNCERTAIN"
    sma_spread = (sma_short - sma_long).abs() / sma_long
    dev_short = (close - sma_short).abs() / sma_short
    dev_long = (close - sma_long).abs() / sma_long
    mr_mask = mask_unc & (sma_spread < 0.005) & (
        dev_short < 0.005) & (dev_long < 0.005)
    regime = regime.where(~mr_mask, "MEAN_REVERSION")

    # Priority 3: SMA Trend (only where still UNCERTAIN)
    mask_unc = regime == "UNCERTAIN"
    regime = regime.where(
        ~(mask_unc & (sma_short > sma_long) & (close > sma_short)),
        "TREND_UP",
    )
    mask_unc = regime == "UNCERTAIN"
    regime = regime.where(
        ~(mask_unc & (sma_short < sma_long) & (close < sma_short)),
        "TREND_DOWN",
    )

    return regime


def _compute_flat_regime_labels(df: pd.DataFrame, regime_col: str = "computed_regime") -> pd.Series:
    """Map Aurora regimes to flat regimes (FLAT_LOW/FLAT_NORMAL/FLAT_HIGH) via regime_mapping.

    Non-MR-suitable regimes (TREND_UP, TREND_DOWN, HIGH_VOL, UNCERTAIN) map to empty string.
    """
    try:
        from apps.reference.domains.feature_engineering.regime_mapping import (
            map_to_flat_regime,
            FlatRegimeThresholds,
        )
    except ImportError:
        return pd.Series("", index=df.index)

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
    atr_pct = atr / close

    thresholds = FlatRegimeThresholds(
        high_vol_pct=Decimal("0.003"),
        low_vol_pct=Decimal("0.001"),
    )

    result = pd.Series("", index=df.index)
    for idx in df.index:
        aurora_regime = str(df.loc[idx, regime_col]
                            ) if regime_col in df.columns else ""
        atr_pct_val = float(atr_pct.loc[idx]) if pd.notna(
            atr_pct.loc[idx]) else 0.0
        flat = map_to_flat_regime(aurora_regime, atr_pct_val, thresholds)
        result.loc[idx] = str(flat) if flat else ""
    return result


def _run_per_regime_analysis(
    df_raw: pd.DataFrame,
    *,
    symbols: list[str],
    root_cfg: dict[str, Any],
    candidate: dict[str, Any],
    tf_sec: int,
    search_cfg: SearchCfg,
    guardrails: GuardrailCfg,
    out_dir: Path,
) -> dict[str, Any]:
    """Run dual per-regime breakdown (Aurora + Flat) on computed-regime data."""
    # Compute regime labels
    for sym in symbols:
        sym_mask = df_raw["symbol"] == sym
        sym_df = df_raw[sym_mask].copy()
        if sym_df.empty:
            continue
        computed = _compute_regime_labels_300s(sym_df)
        df_raw.loc[sym_mask, "computed_regime"] = computed.values
        flat = _compute_flat_regime_labels(
            sym_df.assign(computed_regime=computed.values))
        df_raw.loc[sym_mask, "flat_regime"] = flat.values

    # Aurora-level breakdown
    all_aurora = sorted(df_raw["computed_regime"].dropna().unique().tolist())
    passthrough = {"", "DEFAULT", "UNKNOWN", "PENDING", "NONE"}
    aurora_regimes = [r for r in all_aurora if r not in passthrough]

    aurora_results: dict[str, dict[str, Any]] = {}
    for regime_label in aurora_regimes:
        regime_df = df_raw[df_raw["computed_regime"] == regime_label].copy()
        if regime_df.empty:
            continue
        metrics = _evaluate_window(
            regime_df,
            symbols=symbols,
            root_cfg=root_cfg,
            candidate=candidate,
            tf_sec=int(tf_sec),
            search_cfg=search_cfg,
            guardrails=guardrails,
        )
        aurora_results[regime_label] = metrics

    # Flat-regime-level breakdown
    all_flat = sorted(df_raw["flat_regime"].dropna().unique().tolist())
    flat_regimes = [r for r in all_flat if r not in passthrough]

    flat_results: dict[str, dict[str, Any]] = {}
    for regime_label in flat_regimes:
        regime_df = df_raw[df_raw["flat_regime"] == regime_label].copy()
        if regime_df.empty:
            continue
        metrics = _evaluate_window(
            regime_df,
            symbols=symbols,
            root_cfg=root_cfg,
            candidate=candidate,
            tf_sec=int(tf_sec),
            search_cfg=search_cfg,
            guardrails=guardrails,
        )
        flat_results[regime_label] = metrics

    # Print Aurora table
    header = f"{'Regime':<20} {'Bars':>6} {'Entries':>8} {'Trades':>7} {'WR%':>6} {'PF':>7} {'Net%':>8} {'DD%':>7}"
    print("\n" + "=" * len(header))
    print("PER-REGIME BREAKDOWN — Aurora Regimes (baseline params)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for regime_label, m in sorted(aurora_results.items()):
        bars = int(m.get("row_count", 0))
        entries = int(m.get("entry_count", 0))
        trades = int(m.get("total_trades", 0))
        wr = float(m.get("win_rate", 0)) * 100
        pf = float(m.get("profit_factor") or 0.0)
        net = float(m.get("net_return_ratio", 0)) * 100
        dd = float(m.get("max_drawdown_ratio", 0)) * 100
        print(f"{regime_label:<20} {bars:>6} {entries:>8} {trades:>7} {wr:>5.1f}% {pf:>7.2f} {net:>+7.2f}% {dd:>6.2f}%")
    print("=" * len(header))

    # Print Flat table
    if flat_results:
        print(f"\n{'Flat Regime':<20} {'Bars':>6} {'Entries':>8} {'Trades':>7} {'WR%':>6} {'PF':>7} {'Net%':>8} {'DD%':>7}")
        print("-" * len(header))
        for regime_label, m in sorted(flat_results.items()):
            bars = int(m.get("row_count", 0))
            entries = int(m.get("entry_count", 0))
            trades = int(m.get("total_trades", 0))
            wr = float(m.get("win_rate", 0)) * 100
            pf = float(m.get("profit_factor") or 0.0)
            net = float(m.get("net_return_ratio", 0)) * 100
            dd = float(m.get("max_drawdown_ratio", 0)) * 100
            print(
                f"{regime_label:<20} {bars:>6} {entries:>8} {trades:>7} {wr:>5.1f}% {pf:>7.2f} {net:>+7.2f}% {dd:>6.2f}%")
        print("=" * len(header))

    result = {
        "aurora_regimes": {k: _sanitize_metrics(v) for k, v in aurora_results.items()},
        "flat_regimes": {k: _sanitize_metrics(v) for k, v in flat_results.items()},
    }
    _write_json(out_dir / "per_regime_analysis.json", result)
    print(
        f"  Wrote per_regime_analysis.json -> {out_dir / 'per_regime_analysis.json'}")
    return result


def _sanitize_metrics(m: dict[str, Any]) -> dict[str, Any]:
    """Make metrics JSON-serializable by handling None and non-finite floats."""
    out: dict[str, Any] = {}
    for k, v in m.items():
        if k == "per_symbol":
            out[k] = {sk: _sanitize_metrics(
                sv) for sk, sv in v.items()} if isinstance(v, dict) else v
        elif isinstance(v, float):
            out[k] = v if math.isfinite(v) else None
        elif v is None:
            out[k] = None
        else:
            out[k] = v
    return out


def _evaluate_window_with_trades(
    df_window: pd.DataFrame,
    *,
    symbols: list[str],
    root_cfg: dict[str, Any],
    candidate: dict[str, Any],
    tf_sec: int,
    search_cfg: SearchCfg,
    guardrails: GuardrailCfg,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Like _evaluate_window but also returns the raw trade records."""
    trade_records: list[dict[str, Any]] = []
    signal_count = 0
    entry_count = 0
    for symbol in symbols:
        df_symbol = df_window[df_window["symbol"] == symbol].copy()
        metrics, trades = _evaluate_symbol_window(
            df_symbol,
            symbol=symbol,
            root_cfg=root_cfg,
            candidate=candidate,
            tf_sec=int(tf_sec),
            search_cfg=search_cfg,
            guardrails=guardrails,
        )
        trade_records.extend(trades)
        signal_count += int(metrics["signal_count"])
        entry_count += int(metrics["entry_count"])
    aggregate = _metrics_from_trade_records(
        trade_records,
        row_count=int(len(df_window)),
        unique_days=_unique_days(df_window),
        entry_count=int(entry_count),
        signal_count=int(signal_count),
        guardrails=guardrails,
    )
    return aggregate, trade_records


def _run_tpsl_surface_scan(
    df_raw: pd.DataFrame,
    *,
    symbols: list[str],
    root_cfg: dict[str, Any],
    baseline_candidate: dict[str, Any],
    tf_sec: int,
    search_cfg: SearchCfg,
    guardrails: GuardrailCfg,
    out_dir: Path,
) -> dict[str, Any]:
    """Grid search over sl_atr_mult × tp_to_mid to find optimal exit configuration."""
    sl_grid = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    tp_grid = [True, False]

    results: list[dict[str, Any]] = []
    best_score: float | None = None
    best_cell: dict[str, Any] | None = None

    # Header
    header = f"{'sl_atr_mult':>12} {'tp_to_mid':>10} {'Trades':>7} {'WR%':>6} {'PF':>7} {'Net%':>8} {'DD%':>7} {'Score':>8}"
    print("\n" + "=" * len(header))
    print("SL/TP SURFACE SCAN (6×2 grid)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for sl_mult in sl_grid:
        for tp_mid in tp_grid:
            cell_candidate = dict(baseline_candidate)
            cell_candidate["sl_atr_mult"] = float(sl_mult)
            cell_candidate["tp_to_mid"] = bool(tp_mid)

            metrics = _evaluate_window(
                df_raw,
                symbols=symbols,
                root_cfg=root_cfg,
                candidate=cell_candidate,
                tf_sec=int(tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
            )
            score = _score_or_floor(metrics.get("selection_score"))
            trades = int(metrics.get("total_trades", 0))
            wr = float(metrics.get("win_rate", 0)) * 100
            pf = float(metrics.get("profit_factor") or 0.0)
            net = float(metrics.get("net_return_ratio", 0)) * 100
            dd = float(metrics.get("max_drawdown_ratio", 0)) * 100

            print(f"{sl_mult:>12.1f} {'mid' if tp_mid else 'outer':>10} {trades:>7} {wr:>5.1f}% {pf:>7.2f} {net:>+7.2f}% {dd:>6.2f}% {score:>8.3f}")

            cell = {
                "sl_atr_mult": float(sl_mult),
                "tp_to_mid": bool(tp_mid),
                "metrics": _sanitize_metrics(metrics),
            }
            results.append(cell)
            if best_score is None or score > best_score:
                best_score = score
                best_cell = cell

    print("=" * len(header))
    if best_cell:
        print(
            f"  Best cell: sl_atr_mult={best_cell['sl_atr_mult']}, tp_to_mid={best_cell['tp_to_mid']}, score={best_score:.3f}")

    output = {
        "grid": results,
        "best_cell": best_cell,
        "sl_grid": sl_grid,
        "tp_grid": ["mid", "outer"],
    }
    _write_json(out_dir / "tpsl_surface.json", output)
    print(f"  Wrote tpsl_surface.json -> {out_dir / 'tpsl_surface.json'}")
    return output


def _run_mfe_mae_analysis(
    df_raw: pd.DataFrame,
    *,
    symbols: list[str],
    root_cfg: dict[str, Any],
    baseline_candidate: dict[str, Any],
    tf_sec: int,
    search_cfg: SearchCfg,
    guardrails: GuardrailCfg,
    out_dir: Path,
) -> dict[str, Any]:
    """Collect MFE/MAE distribution from baseline evaluation."""
    _metrics, trade_records = _evaluate_window_with_trades(
        df_raw,
        symbols=symbols,
        root_cfg=root_cfg,
        candidate=baseline_candidate,
        tf_sec=int(tf_sec),
        search_cfg=search_cfg,
        guardrails=guardrails,
    )

    if not trade_records:
        output: dict[str, Any] = {"total_trades": 0,
                                  "mfe": {}, "mae": {}, "suggestion": {}}
        _write_json(out_dir / "mfe_mae_analysis.json", output)
        return output

    mfe_values = [float(t.get("mfe_ratio", 0.0)) for t in trade_records]
    mae_values = [float(t.get("mae_ratio", 0.0)) for t in trade_records]

    def _dist_stats(values: list[float]) -> dict[str, float]:
        arr = np.array(values)
        return {
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "max": float(np.max(arr)),
        }

    mfe_stats = _dist_stats(mfe_values)
    mae_stats = _dist_stats(mae_values)

    # Suggestions: SL at MAE p75, TP at MFE median
    suggestion = {
        "sl_pct_suggested": round(mae_stats["p75"] * 100, 3),
        "tp_pct_suggested": round(mfe_stats["median"] * 100, 3),
        "sl_atr_mult_note": f"Set SL to cover MAE p75={mae_stats['p75']:.4f} ({mae_stats['p75']*100:.2f}%)",
        "tp_note": f"Set TP at MFE median={mfe_stats['median']:.4f} ({mfe_stats['median']*100:.2f}%)",
    }

    print("\n" + "=" * 60)
    print("MFE/MAE EXCURSION ANALYSIS (baseline params)")
    print("=" * 60)
    print(f"  Total trades: {len(trade_records)}")
    print(f"  MFE (Max Favorable Excursion):")
    print(
        f"    mean={mfe_stats['mean']:.4f}  median={mfe_stats['median']:.4f}  p75={mfe_stats['p75']:.4f}  p95={mfe_stats['p95']:.4f}")
    print(f"  MAE (Max Adverse Excursion):")
    print(
        f"    mean={mae_stats['mean']:.4f}  median={mae_stats['median']:.4f}  p75={mae_stats['p75']:.4f}  p95={mae_stats['p95']:.4f}")
    print(f"  Suggested SL: {suggestion['sl_pct_suggested']:.3f}% (MAE p75)")
    print(
        f"  Suggested TP: {suggestion['tp_pct_suggested']:.3f}% (MFE median)")
    print("=" * 60)

    output = {
        "total_trades": len(trade_records),
        "mfe": mfe_stats,
        "mae": mae_stats,
        "suggestion": suggestion,
    }
    _write_json(out_dir / "mfe_mae_analysis.json", output)
    print(
        f"  Wrote mfe_mae_analysis.json -> {out_dir / 'mfe_mae_analysis.json'}")
    return output


def _build_comparison_artifact(
    *,
    window_name: str,
    baseline_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    guardrails: GuardrailCfg,
) -> dict[str, Any]:
    baseline_score = baseline_metrics.get("selection_score")
    candidate_score = candidate_metrics.get("selection_score")
    delta = {
        "selection_score": None if baseline_score is None or candidate_score is None else float(candidate_score - baseline_score),
        "net_return_ratio": float(candidate_metrics["net_return_ratio"] - baseline_metrics["net_return_ratio"]),
        "max_drawdown_ratio": float(candidate_metrics["max_drawdown_ratio"] - baseline_metrics["max_drawdown_ratio"]),
        "total_trades": int(candidate_metrics["total_trades"] - baseline_metrics["total_trades"]),
        "entry_count": int(candidate_metrics["entry_count"] - baseline_metrics["entry_count"]),
        "win_rate": float(candidate_metrics["win_rate"] - baseline_metrics["win_rate"]),
    }

    results: list[dict[str, Any]] = []
    results.append(
        {
            "name": f"{window_name}_min_trade_count",
            "passed": int(candidate_metrics["total_trades"]) >= int(guardrails.min_trades),
            "actual": int(candidate_metrics["total_trades"]),
            "threshold": int(guardrails.min_trades),
            "comparator": ">=",
        }
    )
    results.append(
        {
            "name": f"{window_name}_max_drawdown",
            "passed": float(candidate_metrics["max_drawdown_ratio"]) <= float(guardrails.max_drawdown_ratio),
            "actual": float(candidate_metrics["max_drawdown_ratio"]),
            "threshold": float(guardrails.max_drawdown_ratio),
            "comparator": "<=",
        }
    )

    if window_name == "validation":
        results.append(
            {
                "name": "validation_outperforms_baseline",
                "passed": candidate_score is not None and _score_or_floor(candidate_score) > _score_or_floor(baseline_score),
                "actual": None if delta["selection_score"] is None else float(delta["selection_score"]),
                "threshold": 0.0,
                "comparator": ">",
            }
        )
    else:
        results.append(
            {
                "name": "forward_no_degradation_vs_baseline",
                "passed": candidate_score is not None and _score_or_floor(candidate_score) >= _score_or_floor(baseline_score),
                "actual": None if delta["selection_score"] is None else float(delta["selection_score"]),
                "threshold": 0.0,
                "comparator": ">=",
            }
        )

    baseline_entries = int(baseline_metrics["entry_count"])
    if baseline_entries > 0:
        activity_ratio = float(
            candidate_metrics["entry_count"] / baseline_entries)
        results.append(
            {
                "name": f"{window_name}_activity_ratio_min",
                "passed": activity_ratio >= float(guardrails.min_activity_ratio),
                "actual": float(activity_ratio),
                "threshold": float(guardrails.min_activity_ratio),
                "comparator": ">=",
            }
        )
        results.append(
            {
                "name": f"{window_name}_activity_ratio_max",
                "passed": activity_ratio <= float(guardrails.max_activity_ratio),
                "actual": float(activity_ratio),
                "threshold": float(guardrails.max_activity_ratio),
                "comparator": "<=",
            }
        )
    else:
        results.append(
            {
                "name": f"{window_name}_activity_ratio_not_applicable",
                "passed": True,
                "actual": None,
                "threshold": None,
                "comparator": "n/a",
            }
        )

    return {
        "window": window_name,
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "delta": delta,
        "guardrails": results,
        "all_passed": all(bool(item["passed"]) for item in results),
    }


def _overlay_from_candidate(candidate: dict[str, Any], *, symbols: list[str]) -> dict[str, Any]:
    strategy_payload = {
        "bb_window": int(candidate["bb_window"]),
        "bb_num_std": float(candidate["bb_num_std"]),
        "entry_threshold": float(candidate["entry_threshold"]),
        "sl_atr_mult": float(candidate["sl_atr_mult"]),
        "cooldown_sec": int(candidate["cooldown_sec"]),
        "min_bb_width": float(candidate["min_bb_width"]),
        "max_bb_width": float(candidate["max_bb_width"]),
    }
    assets_payload = {
        str(symbol).upper(): {"strategy": dict(strategy_payload)}
        for symbol in symbols
    }
    return {"mean_reversion": {"assets": assets_payload}}


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100.0:.2f}%"


def _fmt_score(value: float | None) -> str:
    if value is None:
        return "ineligible"
    return f"{float(value):.4f}"


def _build_dataset_audit(
    *,
    df_raw: pd.DataFrame,
    windows: WindowSpec,
    symbols: list[str],
    args: argparse.Namespace,
    required_history_rows: int,
    binance_rows_added: int = 0,
) -> dict[str, Any]:
    return {
        "recorder_dir": str(Path(args.recorder_dir)),
        "symbols": list(symbols),
        "date_range": {"start": args.start.isoformat(), "end_exclusive": args.end.isoformat()},
        "tf_sec": int(args.tf_sec),
        "rows_raw": int(len(df_raw)),
        "unique_days": _unique_days(df_raw),
        "fingerprint": _dataset_fingerprint(df_raw),
        "required_history_rows": int(required_history_rows),
        "binance_hydration": {
            "enabled": bool(getattr(args, "hydrate_from_binance", False)),
            "rows_added": int(binance_rows_added),
        },
        "windows": {
            "train_days": list(windows.train_days),
            "validation_days": list(windows.validation_days),
            "forward_days": list(windows.forward_days),
        },
        "window_stats": {
            "train": _window_stats(_slice_window(df_raw, windows.train_days), symbols=symbols),
            "validation": _window_stats(_slice_window(df_raw, windows.validation_days), symbols=symbols),
            "forward": _window_stats(_slice_window(df_raw, windows.forward_days), symbols=symbols),
        },
    }


def _render_report(
    *,
    args: argparse.Namespace,
    windows: WindowSpec | None,
    dataset_audit: dict[str, Any] | None,
    baseline_metrics: dict[str, Any] | None,
    candidate_payload: dict[str, Any] | None,
    validation_artifact: dict[str, Any] | None,
    forward_artifact: dict[str, Any] | None,
    manifest: dict[str, Any],
    failure: CalibrationError | None,
) -> str:
    verdict = str(manifest.get("verdict") or "NO_GO_CANDIDATE")
    candidate_params = ((candidate_payload or {}).get(
        "selected_candidate") or {}).get("params") or {}
    baseline_train = ((baseline_metrics or {}).get("train") or {})
    baseline_validation = ((baseline_metrics or {}).get("validation") or {})
    baseline_forward = ((baseline_metrics or {}).get("forward") or {})
    candidate_train = ((candidate_payload or {}).get(
        "selected_candidate") or {}).get("train") or {}
    candidate_validation = (validation_artifact or {}).get("candidate") or {}
    candidate_forward = (forward_artifact or {}).get("candidate") or {}
    dataset_days = ((dataset_audit or {}).get("unique_days") or [])

    failure_lines: list[str] = []
    if failure is not None:
        failure_lines = [
            f"- Failure code: {failure.code}",
            f"- Failure message: {failure}",
        ]

    risk_conclusions = [
        "### Conclusion: Candidate verdict is fail-closed\n"
        f"- Facts: verdict={verdict}; validation_pass={bool((validation_artifact or {}).get('all_passed', False))}; forward_pass={bool((forward_artifact or {}).get('all_passed', False))}.\n"
        "- Inferences: the tool separates candidate generation from acceptance and does not promote a candidate implicitly.\n"
        "- Assumptions: recorder rows are representative for the requested Mean Reversion symbol scope and date range.\n"
        "- Unknowns: live routing, execution arbitration, and venue fill behavior are not proven by this bar-proxy calibration run.\n"
        f"- Symptom: the final verdict is {verdict}.\n"
        "- Root cause: acceptance depends on explicit out-of-sample guardrails rather than best-train-score alone.\n"
        "- Contributing factor: selection_score is only a search metric; it is not a promotion override.\n"
        "- Masking layer: the legacy script printed best params without a strict GO/NO_GO verdict contract.\n"
        "- Cause: validation/forward comparison plus guardrail contract.\n"
        "- Mechanism: candidate must survive min-trade, max-drawdown, activity, and baseline-relative checks.\n"
        "- Effect: weak or unstable candidates remain NO_GO even if train metrics look attractive.\n"
        "- Operational risk: operators could misread the overlay output as rollout-ready if they ignore the verdict.",
        "### Conclusion: Overlay path now matches the evaluated surface\n"
        "- Facts: current mean_reversion YAML uses per-asset strategy overrides for DOGEUSDT; the hardened overlay writes asset-scoped strategy overrides for each requested symbol.\n"
        "- Inferences: the emitted candidate now targets the same precedence path that was evaluated in memory.\n"
        "- Assumptions: requested symbol scope remains asset-driven rather than moving back to global-only strategy overrides later.\n"
        "- Unknowns: whether future runtime config refactors will change Mean Reversion parameter precedence.\n"
        "- Symptom: the old overlay contract could diverge from what was actually backtested.\n"
        "- Root cause: the legacy calibrator built candidates from effective asset config but serialized them under a global strategy path.\n"
        "- Contributing factor: per-asset overrides in canonical YAML out-rank global strategy overlays.\n"
        "- Masking layer: overlay-only language hid that the old overlay target did not mirror runtime precedence.\n"
        "- Cause: artifact surface mismatch.\n"
        "- Mechanism: global overlays would lose to existing asset-specific strategy blocks on live load.\n"
        "- Effect: the hardened candidate overlay is now materially more trustworthy for manual review and replayed comparison.\n"
        "- Operational risk: without this fix, operators could promote an overlay that does not actually reproduce the tested params.",
        "### Conclusion: Evaluation remains a recorder-bar proxy, not a full live replay\n"
        f"- Facts: evaluation uses MeanReversion1mStrategy on recorder OHLC bars; dataset fingerprint={((dataset_audit or {}).get('fingerprint') or 'n/a')}.\n"
        "- Inferences: ranking is materially closer to the runtime state machine than ad-hoc synthetic scoring, because the live strategy class, regime sizing, and regime thresholds are used directly.\n"
        "- Assumptions: stop-first treatment on ambiguous intrabar TP/SL is an acceptable fail-closed proxy.\n"
        "- Unknowns: queue position, execution pacing, objective-engine gating, and exchange-side rejects are outside this calibrator's proof boundary.\n"
        "- Symptom: outputs are trustworthy for parameter-surface comparison, but not equivalent to exchange-execution proof.\n"
        "- Root cause: this package intentionally scopes to a single calibrator skeleton and overlay-only artifacts.\n"
        "- Contributing factor: recorder datasets do not prove routing or fill quality.\n"
        "- Masking layer: attractive proxy returns can hide execution-path mismatch if treated as production replay truth.\n"
        "- Cause: calibration uses recorder bars plus horizon/TP/SL proxy trade accounting.\n"
        "- Mechanism: the live strategy emits signals, then the calibrator simulates bounded post-signal outcomes on future bars.\n"
        "- Effect: baseline-vs-candidate ordering is explicit, but absolute profitability remains approximate.\n"
        "- Operational risk: over-trusting proxy metrics could promote a candidate that degrades under live routing.",
        "### Conclusion: Runtime-surface proof is usable but documentation is partially drifted\n"
        "- Facts: config/aurora/strategies.yaml currently assigns DOGEUSDT to mean_reversion; the Mean Reversion passport still contains stale prose claiming no live assignment before a later correction note.\n"
        "- Inferences: strategies.yaml is the stronger runtime-truth anchor for current assignment state, while the passport remains useful for state-machine boundaries.\n"
        "- Assumptions: the checked-in strategies registry matches the intended deployment snapshot for this calibration package.\n"
        "- Unknowns: whether deployment uses a different registry snapshot than the inspected workspace.\n"
        "- Symptom: assignment truth is clear in code/config, less clean in documentation.\n"
        "- Root cause: the passport accumulated stale assignment text during later audits.\n"
        "- Contributing factor: owner-boundary corrections were appended without removing earlier contradictory prose.\n"
        "- Masking layer: the passport header still reads like a definitive live-state summary.\n"
        "- Cause: documentation drift.\n"
        "- Mechanism: stale assignment text and corrective notes coexist in the same document.\n"
        "- Effect: the calibrator can be used on DOGEUSDT with current registry proof, but assignment documentation still deserves cleanup.\n"
        "- Operational risk: future operators may misread dormant/live status if they rely on the stale header alone.",
    ]

    report = [
        "# Mean Reversion Parameter Calibration Report",
        "",
        "## Scope",
        f"- Calibrator: {Path(__file__).name}",
        "- Calibration class: production-aligned stage-1 calibrator for Mean Reversion asset strategy parameters.",
        "- Mode: overlay-only. No canonical YAML mutation is performed.",
        f"- Symbols: {', '.join(str(symbol).upper() for symbol in args.symbols)}",
        f"- Date range: start={args.start.isoformat()} end_exclusive={args.end.isoformat()}",
        f"- Output dir: {manifest.get('out_dir')}",
        "- Candidate search method: bounded local random mutation around the effective baseline, ranked on train and re-selected on validation.",
        "- Non-goals: no live strategy math rewrite, no auto-rollout, no canonical writeback, no execution-path proof claim.",
        "",
        "## Dataset",
    ]
    if dataset_audit is None:
        report.append("- Dataset audit unavailable due to early failure.")
    else:
        report.extend(
            [
                f"- Recorder dir: {dataset_audit['recorder_dir']}",
                f"- tf_sec: {dataset_audit['tf_sec']}",
                f"- Raw rows: {dataset_audit['rows_raw']}",
                f"- Unique days: {len(dataset_days)} ({', '.join(dataset_days)})",
                f"- Dataset fingerprint: {dataset_audit['fingerprint']}",
                f"- Required contiguous rows per symbol/window: {dataset_audit['required_history_rows']}",
                f"- Train days: {', '.join((windows.train_days if windows else []))}",
                f"- Validation days: {', '.join((windows.validation_days if windows else []))}",
                f"- Forward days: {', '.join((windows.forward_days if windows else []))}",
            ]
        )
    report.extend(
        [
            "",
            "## Runtime Surface Under Calibration",
            "- Primary runtime anchor: config/docs/mean_reversion_state_machine_passport.md",
            "- Assignment SSOT: config/aurora/strategies.yaml",
            "- Governance anchors: config/docs/CALIBRATION_STANDARD_V1.md and calibrators/README.md",
            "- Surface under calibration: mean_reversion.assets.<SYMBOL>.strategy.{bb_window, bb_num_std, entry_threshold, sl_atr_mult, cooldown_sec, min_bb_width, max_bb_width}",
            "- Overlay artifact: candidate_mean_reversion_strategy_overlay.yaml",
            "",
            "## Baseline",
        ]
    )
    if not baseline_metrics:
        report.append("- Baseline metrics unavailable.")
    else:
        report.extend(
            [
                f"- Train score: {_fmt_score(baseline_train.get('selection_score'))}",
                f"- Train trades: {baseline_train.get('total_trades', 0)}",
                f"- Train net return: {_fmt_ratio(baseline_train.get('net_return_ratio'))}",
                f"- Validation score: {_fmt_score(baseline_validation.get('selection_score'))}",
                f"- Validation trades: {baseline_validation.get('total_trades', 0)}",
                f"- Forward score: {_fmt_score(baseline_forward.get('selection_score'))}",
                f"- Forward trades: {baseline_forward.get('total_trades', 0)}",
            ]
        )
    report.extend(["", "## Candidate"])
    if not candidate_payload:
        report.append("- Candidate payload unavailable.")
    else:
        report.extend(
            [
                f"- Selected params: {json.dumps(candidate_params, sort_keys=True)}",
                f"- Selection basis: {candidate_payload.get('selection_basis')}",
                f"- Train score: {_fmt_score(candidate_train.get('selection_score'))}",
                f"- Train trades: {candidate_train.get('total_trades', 0)}",
                f"- Train net return: {_fmt_ratio(candidate_train.get('net_return_ratio'))}",
            ]
        )
    report.extend(["", "## Validation"])
    if not validation_artifact:
        report.append("- Validation comparison unavailable.")
    else:
        report.extend(
            [
                f"- Candidate score: {_fmt_score(candidate_validation.get('selection_score'))}",
                f"- Baseline score: {_fmt_score(baseline_validation.get('selection_score'))}",
                f"- Score delta: {_fmt_score(validation_artifact['delta'].get('selection_score'))}",
                f"- Guardrails passed: {validation_artifact.get('all_passed')}",
            ]
        )
    report.extend(["", "## Forward Evaluation"])
    if not forward_artifact:
        report.append("- Forward comparison unavailable.")
    else:
        report.extend(
            [
                f"- Candidate score: {_fmt_score(candidate_forward.get('selection_score'))}",
                f"- Baseline score: {_fmt_score(baseline_forward.get('selection_score'))}",
                f"- Score delta: {_fmt_score(forward_artifact['delta'].get('selection_score'))}",
                f"- Guardrails passed: {forward_artifact.get('all_passed')}",
            ]
        )
    report.extend(["", "## Guardrails"])
    report.extend(
        [
            f"- Minimum trade count: {manifest['guardrails']['min_trades']}",
            f"- Maximum drawdown ratio: {manifest['guardrails']['max_drawdown_ratio']}",
            f"- Minimum activity ratio vs baseline: {manifest['guardrails']['min_activity_ratio']}",
            f"- Maximum activity ratio vs baseline: {manifest['guardrails']['max_activity_ratio']}",
            "- Acceptance is fail-closed: validation must outperform baseline and forward must not degrade versus baseline.",
        ]
    )
    if failure_lines:
        report.extend(failure_lines)
    report.extend(["", "## Risks"])
    report.extend(risk_conclusions)
    report.extend(["", "## Verdict", f"- {verdict}"])
    if manifest.get("verdict_reasons"):
        for reason in manifest["verdict_reasons"]:
            report.append(f"- {reason}")
    report.extend(["", "## Next Action"])
    if verdict == "GO_CANDIDATE":
        report.append(
            "- Review the asset-scoped overlay manually and keep promotion separate from calibration. No automatic rollout is implied."
        )
    else:
        report.append(
            "- Treat the overlay as non-promotable until failed guardrails, assignment-doc drift, or evidence gaps are resolved."
        )
    return "\n".join(report) + "\n"


def _write_success_artifacts(
    *,
    out_dir: Path,
    manifest: dict[str, Any],
    baseline_metrics: dict[str, Any],
    candidate_payload: dict[str, Any],
    validation_artifact: dict[str, Any],
    forward_artifact: dict[str, Any],
    overlay: dict[str, Any],
    report: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "run_manifest.json", manifest)
    _write_json(out_dir / "baseline_metrics.json", baseline_metrics)
    _write_json(out_dir / "candidate_metrics.json", candidate_payload)
    _write_json(out_dir / "validation_metrics.json", validation_artifact)
    _write_json(out_dir / "forward_metrics.json", forward_artifact)
    _write_yaml(
        out_dir / "candidate_mean_reversion_strategy_overlay.yaml", overlay)
    _write_yaml(out_dir / "candidate_mean_reversion_overlay.yaml", overlay)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    _write_json(
        out_dir / "best_trial.json",
        {
            "overlay": overlay,
            "selected_candidate": candidate_payload.get("selected_candidate"),
            "validation": validation_artifact,
            "forward": forward_artifact,
            "verdict": manifest.get("verdict"),
            "seed": candidate_payload.get("search_space", {}).get("seed"),
        },
    )
    _write_json(
        out_dir / "candidate_bundle.json",
        {
            "selection_basis": candidate_payload.get("selection_basis"),
            "top_candidates": candidate_payload.get("top_candidates", []),
        },
    )


def _write_failure_bundle(args: argparse.Namespace, out_dir: Path, error: CalibrationError) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "calibrator": "calibrate_mean_reversion_params.py",
        "calibration_class": "production",
        "status": "failed_closed",
        "verdict": "NO_GO_CANDIDATE",
        "out_dir": str(out_dir),
        "failure": {"code": error.code, "message": str(error), "details": error.details},
        "runtime_truth_anchors": [
            "config/docs/mean_reversion_state_machine_passport.md",
            "config/aurora/strategies.yaml",
            "config/docs/CALIBRATION_STANDARD_V1.md",
            "calibrators/README.md",
        ],
        "input_contract": {
            "symbols": [str(symbol).upper() for symbol in args.symbols],
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
            "tf_sec": int(args.tf_sec),
            "trials": int(args.trials),
            "validation_days": int(args.validation_days),
            "forward_days": int(args.forward_days),
        },
        "canonical_yaml_writeback": False,
        "artifact_paths": {
            "run_manifest": "run_manifest.json",
            "report": "report.md",
        },
        "guardrails": {
            "min_trades": int(args.min_trades),
            "max_drawdown_ratio": float(args.max_dd_limit),
            "min_activity_ratio": float(args.min_activity_ratio),
            "max_activity_ratio": float(args.max_activity_ratio),
        },
        "verdict_reasons": [f"{error.code}: {error}"],
    }
    _write_json(out_dir / "run_manifest.json", manifest)
    report = _render_report(
        args=args,
        windows=None,
        dataset_audit=None,
        baseline_metrics=None,
        candidate_payload=None,
        validation_artifact=None,
        forward_artifact=None,
        manifest=manifest,
        failure=error,
    )
    (out_dir / "report.md").write_text(report, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Production-grade Mean Reversion parameter calibrator. Uses recorder data, emits overlay-only artifacts, "
            "compares baseline versus candidate across train/validation/forward windows, and never mutates canonical YAML."
        )
    )
    parser.add_argument(
        "--mr-yaml", default="config/aurora/strategies/mean_reversion.yaml")
    parser.add_argument("--strategies-registry",
                        default="config/aurora/strategies.yaml")
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Mean Reversion symbols to calibrate. Must be assigned to mean_reversion in the strategies registry.",
    )
    parser.add_argument("--start", type=_parse_date,
                        required=True, help="Start date inclusive (YYYY-MM-DD)")
    parser.add_argument("--end", type=_parse_date, required=True,
                        help="End date exclusive (YYYY-MM-DD)")
    parser.add_argument("--tf-sec", type=int, default=300,
                        help="Recorder timeframe seconds. Current Mean Reversion contract supports only 300.")
    parser.add_argument("--trials", type=int, default=120,
                        help="Random local-mutation trials around the effective baseline parameters.")
    parser.add_argument("--top-k", type=int, default=5,
                        help="How many top train candidates to carry into validation selection.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-days", type=int, default=14,
                        help="Number of trailing unique days reserved for validation.")
    parser.add_argument("--forward-days", type=int, default=7,
                        help="Number of trailing unique days reserved for forward evaluation.")
    parser.add_argument("--min-train-days", type=int, default=28,
                        help="Minimum unique days required in the train window after holdouts.")
    parser.add_argument("--horizon-bars", type=int, default=6,
                        help="How many future bars to simulate after each actionable signal.")
    parser.add_argument("--cost-bps-roundtrip", type=float, default=6.0)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--max-dd-limit", type=float, default=0.35)
    parser.add_argument("--min-activity-ratio", type=float, default=0.5)
    parser.add_argument("--max-activity-ratio", type=float, default=2.5)
    parser.add_argument("--out-dir", default=None,
                        help="Artifact output directory. If omitted, a timestamped path is used.")
    parser.add_argument("--hydrate-from-binance", action="store_true", default=False,
                        help="Fetch missing 5m klines from Binance Futures to fill recorder gaps.")
    parser.add_argument("--binance-base-url", default="https://fapi.binance.com",
                        help="Binance Futures REST base URL.")
    parser.add_argument("--binance-timeout-sec", type=float, default=15.0)
    parser.add_argument("--binance-pause-sec", type=float, default=0.25,
                        help="Pause between paginated Binance requests.")
    parser.add_argument("--binance-lookback-bars", type=int, default=96,
                        help="Extra historical bars to fetch before local data start.")
    parser.add_argument("--per-regime", action="store_true", default=False,
                        help="Run per-regime breakdown analysis after calibration.")
    parser.add_argument("--tpsl-surface", action="store_true", default=False,
                        help="Run SL/TP surface scan and MFE/MAE analysis.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.symbols = [str(symbol).upper() for symbol in args.symbols]
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(args)

    try:
        if args.end <= args.start:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                "--end must be greater than --start.",
            )
        if int(args.tf_sec) != 300:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                f"Mean Reversion calibration currently supports only tf_sec=300, got {args.tf_sec}.",
            )
        if int(args.validation_days) <= 0 or int(args.forward_days) <= 0 or int(args.min_train_days) <= 0:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                "window day arguments must be positive integers.",
            )
        if int(args.horizon_bars) <= 0:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                "--horizon-bars must be positive.",
            )
        if float(args.max_dd_limit) <= 0.0:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                "--max-dd-limit must be positive.",
            )
        if float(args.min_activity_ratio) <= 0.0 or float(args.max_activity_ratio) < float(args.min_activity_ratio):
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                "activity-ratio guardrails must satisfy 0 < min <= max.",
            )

        _require_mean_reversion_runtime()

        root_cfg = _load_mean_reversion_yaml(Path(args.mr_yaml))
        root_tf_sec = int(root_cfg.get("timeframe_sec", 0) or 0)
        if root_tf_sec != int(args.tf_sec):
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                f"Requested tf_sec={args.tf_sec} does not match mean_reversion.timeframe_sec={root_tf_sec}.",
            )

        assigned_symbols = _load_assigned_symbols(
            Path(args.strategies_registry), strategy_id="mean_reversion")
        unassigned = sorted(
            set(args.symbols).difference(set(assigned_symbols)))
        if unassigned:
            raise CalibrationError(
                "SCOPE_INVALID",
                "Requested symbols are not currently assigned to mean_reversion in the strategies registry.",
                details={
                    "requested_symbols": list(args.symbols),
                    "assigned_symbols": assigned_symbols,
                    "unassigned_symbols": unassigned,
                },
            )

        baseline_candidate, effective_baselines = _extract_baseline_candidate(
            root_cfg, args.symbols)
        search_cfg = SearchCfg(
            trials=max(1, int(args.trials)),
            top_k=max(1, int(args.top_k)),
            horizon_bars=max(1, int(args.horizon_bars)),
            cost_bps_roundtrip=float(args.cost_bps_roundtrip),
        )
        guardrails = GuardrailCfg(
            min_trades=max(1, int(args.min_trades)),
            max_drawdown_ratio=float(args.max_dd_limit),
            min_train_days=max(1, int(args.min_train_days)),
            min_activity_ratio=float(args.min_activity_ratio),
            max_activity_ratio=float(args.max_activity_ratio),
        )
        required_history_rows = _required_history_rows(
            root_cfg, horizon_bars=int(args.horizon_bars))

        _validate_requested_recorder_csvs(
            Path(args.recorder_dir),
            start=args.start,
            end=args.end,
            symbols=list(args.symbols),
            tf_sec=int(args.tf_sec),
        )

        df_raw = _LOAD_RECORDER_ROWS(
            Path(args.recorder_dir),
            start=args.start,
            end=args.end,
            symbols=list(args.symbols),
            tf_sec=int(args.tf_sec),
        )

        binance_rows_added = 0
        if bool(getattr(args, "hydrate_from_binance", False)):
            pre_hydrate_len = len(df_raw)
            df_raw = _maybe_hydrate_missing_from_binance(
                local_df=df_raw,
                symbols=list(args.symbols),
                start=args.start,
                end=args.end,
                enable=True,
                lookback_bars=int(getattr(args, "binance_lookback_bars", 96)),
                base_url=str(getattr(args, "binance_base_url",
                             "https://fapi.binance.com")),
                timeout_sec=float(getattr(args, "binance_timeout_sec", 15.0)),
                pause_sec=float(getattr(args, "binance_pause_sec", 0.25)),
            )
            binance_rows_added = max(0, len(df_raw) - pre_hydrate_len)

        df_raw = _normalize_recorder_dataset(df_raw, tf_sec=int(args.tf_sec))
        if df_raw.empty:
            raise CalibrationError(
                "INSUFFICIENT_DATA",
                "No recorder rows found for requested Mean Reversion symbols/date range.",
            )

        windows = _resolve_windows(
            df_raw,
            validation_days=int(args.validation_days),
            forward_days=int(args.forward_days),
            min_train_days=int(args.min_train_days),
        )
        dataset_audit = _build_dataset_audit(
            df_raw=df_raw,
            windows=windows,
            symbols=list(args.symbols),
            args=args,
            required_history_rows=required_history_rows,
            binance_rows_added=binance_rows_added,
        )
        _validate_window_coverage(
            "train",
            dataset_audit["window_stats"]["train"],
            required_rows=required_history_rows,
        )
        _validate_window_coverage(
            "validation",
            dataset_audit["window_stats"]["validation"],
            required_rows=required_history_rows,
        )
        _validate_window_coverage(
            "forward",
            dataset_audit["window_stats"]["forward"],
            required_rows=required_history_rows,
        )

        train_df = _slice_window(df_raw, windows.train_days)
        validation_df = _slice_window(df_raw, windows.validation_days)
        forward_df = _slice_window(df_raw, windows.forward_days)

        baseline_metrics = {
            "train": _evaluate_window(
                train_df,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                candidate=baseline_candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
            ),
            "validation": _evaluate_window(
                validation_df,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                candidate=baseline_candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
            ),
            "forward": _evaluate_window(
                forward_df,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                candidate=baseline_candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
            ),
        }

        seen_signatures = {_candidate_signature(baseline_candidate)}
        candidate_points: list[dict[str, Any]] = [
            {
                "params": dict(baseline_candidate),
                "train": baseline_metrics["train"],
                "validation": baseline_metrics["validation"],
            }
        ]

        rng = random.Random(int(args.seed))
        for _ in range(max(1, int(args.trials))):
            candidate = _mutate_candidate(baseline_candidate, rng)
            signature = _candidate_signature(candidate)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            train_metrics = _evaluate_window(
                train_df,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                candidate=candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
            )
            candidate_points.append(
                {"params": candidate, "train": train_metrics})

        ranked_train = sorted(
            candidate_points,
            key=lambda item: (
                _score_or_floor(item["train"].get("selection_score")),
                float(item["train"].get("net_return_ratio", 0.0)),
            ),
            reverse=True,
        )
        top_candidates = ranked_train[: max(1, int(args.top_k))]
        for item in top_candidates:
            if "validation" not in item:
                item["validation"] = _evaluate_window(
                    validation_df,
                    symbols=list(args.symbols),
                    root_cfg=root_cfg,
                    candidate=item["params"],
                    tf_sec=int(args.tf_sec),
                    search_cfg=search_cfg,
                    guardrails=guardrails,
                )

        selected = sorted(
            top_candidates,
            key=lambda item: (
                _score_or_floor(item["validation"].get("selection_score")),
                _score_or_floor(item["train"].get("selection_score")),
                float(item["validation"].get("net_return_ratio", 0.0)),
            ),
            reverse=True,
        )[0]
        selected_forward = _evaluate_window(
            forward_df,
            symbols=list(args.symbols),
            root_cfg=root_cfg,
            candidate=selected["params"],
            tf_sec=int(args.tf_sec),
            search_cfg=search_cfg,
            guardrails=guardrails,
        )

        candidate_payload = {
            "search_space": {
                "seed": int(args.seed),
                "top_k": int(args.top_k),
                "trials": int(args.trials),
                "type": "bounded_local_mutation",
                "param_keys": list(PARAM_KEYS),
                "bounds": SEARCH_BOUNDS,
                "effective_baselines": effective_baselines,
            },
            "selection_basis": "best validation selection score among train-ranked candidates",
            "selected_candidate": {
                "params": dict(selected["params"]),
                "train": selected["train"],
                "validation": selected["validation"],
                "validation_score": selected["validation"].get("selection_score"),
            },
            "top_candidates": [
                {
                    "params": dict(item["params"]),
                    "train_score": item["train"].get("selection_score"),
                    "train_total_trades": item["train"].get("total_trades"),
                    "validation_score": item["validation"].get("selection_score"),
                    "validation_total_trades": item["validation"].get("total_trades"),
                }
                for item in top_candidates
            ],
        }

        validation_artifact = _build_comparison_artifact(
            window_name="validation",
            baseline_metrics=baseline_metrics["validation"],
            candidate_metrics=selected["validation"],
            guardrails=guardrails,
        )
        forward_artifact = _build_comparison_artifact(
            window_name="forward",
            baseline_metrics=baseline_metrics["forward"],
            candidate_metrics=selected_forward,
            guardrails=guardrails,
        )

        verdict = "GO_CANDIDATE" if validation_artifact[
            "all_passed"] and forward_artifact["all_passed"] else "NO_GO_CANDIDATE"
        verdict_reasons: list[str] = []
        if not validation_artifact["all_passed"]:
            failed = [item["name"]
                      for item in validation_artifact["guardrails"] if not item["passed"]]
            verdict_reasons.append(
                f"Validation guardrails failed: {', '.join(failed)}")
        if not forward_artifact["all_passed"]:
            failed = [item["name"]
                      for item in forward_artifact["guardrails"] if not item["passed"]]
            verdict_reasons.append(
                f"Forward guardrails failed: {', '.join(failed)}")
        if not verdict_reasons and verdict == "GO_CANDIDATE":
            verdict_reasons.append(
                "Validation and forward guardrails passed. Promotion remains separate from calibration.")

        overlay = _overlay_from_candidate(
            selected["params"], symbols=list(args.symbols))
        manifest = {
            "calibrator": "calibrate_mean_reversion_params.py",
            "calibration_class": "production",
            "status": "completed",
            "verdict": verdict,
            "out_dir": str(out_dir),
            "runtime_truth_anchors": [
                "config/docs/mean_reversion_state_machine_passport.md",
                "config/aurora/strategies.yaml",
                "config/docs/CALIBRATION_STANDARD_V1.md",
                "calibrators/README.md",
            ],
            "input_contract": {
                "symbols": list(args.symbols),
                "start": args.start.isoformat(),
                "end_exclusive": args.end.isoformat(),
                "tf_sec": int(args.tf_sec),
                "search_controls": {
                    "trials": int(args.trials),
                    "top_k": int(args.top_k),
                    "seed": int(args.seed),
                    "horizon_bars": int(args.horizon_bars),
                    "cost_bps_roundtrip": float(args.cost_bps_roundtrip),
                },
                "evaluation_windows": {
                    "validation_days": int(args.validation_days),
                    "forward_days": int(args.forward_days),
                    "min_train_days": int(args.min_train_days),
                },
                "output_dir": str(out_dir),
            },
            "assignment_scope": {
                "requested_symbols": list(args.symbols),
                "assigned_symbols": assigned_symbols,
                "all_requested_symbols_assigned": True,
            },
            "dataset_audit": dataset_audit,
            "guardrails": {
                "min_trades": int(args.min_trades),
                "max_drawdown_ratio": float(args.max_dd_limit),
                "min_activity_ratio": float(args.min_activity_ratio),
                "max_activity_ratio": float(args.max_activity_ratio),
            },
            "window_days": {
                "train": list(windows.train_days),
                "validation": list(windows.validation_days),
                "forward": list(windows.forward_days),
            },
            "overlay_target_paths": [
                f"mean_reversion.assets.{symbol}.strategy" for symbol in args.symbols
            ],
            "canonical_yaml_writeback": False,
            "artifact_paths": {
                "run_manifest": "run_manifest.json",
                "baseline_metrics": "baseline_metrics.json",
                "candidate_metrics": "candidate_metrics.json",
                "validation_metrics": "validation_metrics.json",
                "forward_metrics": "forward_metrics.json",
                "candidate_overlay": "candidate_mean_reversion_strategy_overlay.yaml",
                "legacy_candidate_overlay": "candidate_mean_reversion_overlay.yaml",
                "report": "report.md",
                "best_trial": "best_trial.json",
                "candidate_bundle": "candidate_bundle.json",
            },
            "verdict_reasons": verdict_reasons,
        }
        report = _render_report(
            args=args,
            windows=windows,
            dataset_audit=dataset_audit,
            baseline_metrics=baseline_metrics,
            candidate_payload=candidate_payload,
            validation_artifact=validation_artifact,
            forward_artifact=forward_artifact,
            manifest=manifest,
            failure=None,
        )
        _write_success_artifacts(
            out_dir=out_dir,
            manifest=manifest,
            baseline_metrics=baseline_metrics,
            candidate_payload=candidate_payload,
            validation_artifact=validation_artifact,
            forward_artifact=forward_artifact,
            overlay=overlay,
            report=report,
        )
        print(
            f"Mean reversion calibration complete. verdict={verdict} out_dir={out_dir}")

        if bool(getattr(args, "per_regime", False)):
            _run_per_regime_analysis(
                df_raw,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                candidate=baseline_candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
                out_dir=out_dir,
            )

        if bool(getattr(args, "tpsl_surface", False)):
            _run_tpsl_surface_scan(
                df_raw,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                baseline_candidate=baseline_candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
                out_dir=out_dir,
            )
            _run_mfe_mae_analysis(
                df_raw,
                symbols=list(args.symbols),
                root_cfg=root_cfg,
                baseline_candidate=baseline_candidate,
                tf_sec=int(args.tf_sec),
                search_cfg=search_cfg,
                guardrails=guardrails,
                out_dir=out_dir,
            )

        return 0
    except CalibrationError as error:
        _write_failure_bundle(args, out_dir, error)
        print(
            f"Mean reversion calibration failed closed: {error.code} {error}")
        return 2
    except Exception as exc:  # pragma: no cover
        error = CalibrationError(
            "UNEXPECTED_ERROR",
            f"Unexpected Mean Reversion calibrator failure: {exc}",
        )
        _write_failure_bundle(args, out_dir, error)
        print(
            f"Mean reversion calibration failed closed: {error.code} {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
