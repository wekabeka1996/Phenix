#!/usr/bin/env python3
"""Production-grade MD-AMR weight calibrator.

This tool calibrates the active md_amr.weights surface against recorder data,
evaluates baseline versus candidate across train/validation/forward windows,
emits overlay-only artifacts, and never mutates canonical YAML automatically.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


WEIGHT_KEYS = ("d1", "h1", "m30", "m15")
NEGATIVE_FLOOR = -1.0e18
_LOAD_RECORDER_900: Any | None = None
_COMPUTE_MD_AMR_FEATURES: Any | None = None
_MD_AMR_STRATEGY_V11: Any | None = None
_REGIME_ALLOWLIST_CONTRACT: Any | None = None


class CalibrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = str(code)
        self.details = dict(details or {})


@dataclass(frozen=True)
class SearchCfg:
    trials: int
    top_k: int
    warmup_bars: int


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


def _require_md_amr_runtime() -> None:
    global _LOAD_RECORDER_900, _COMPUTE_MD_AMR_FEATURES, _MD_AMR_STRATEGY_V11, _REGIME_ALLOWLIST_CONTRACT

    if (
        _LOAD_RECORDER_900 is not None
        and _COMPUTE_MD_AMR_FEATURES is not None
        and _MD_AMR_STRATEGY_V11 is not None
        and _REGIME_ALLOWLIST_CONTRACT is not None
    ):
        return

    try:
        from tools.simulation.md_amr_data_adapter import (  # type: ignore
            compute_md_amr_features,
            load_recorder_900,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise CalibrationError(
            "RUNTIME_IMPORT_BLOCKED",
            "MD-AMR calibration requires tools/simulation/md_amr_data_adapter.py to be importable.",
        ) from exc

    try:
        from apps.reference.domains.strategies.runtimes.bridge import (  # type: ignore
            MDAMRStrategyV11,
        )
    except Exception as exc:  # pragma: no cover
        raise CalibrationError(
            "RUNTIME_IMPORT_BLOCKED",
            f"MD-AMR calibration requires the live MDAMRStrategyV11 runtime import path. Import error: {exc}",
        ) from exc

    _LOAD_RECORDER_900 = load_recorder_900
    _COMPUTE_MD_AMR_FEATURES = compute_md_amr_features
    _MD_AMR_STRATEGY_V11 = MDAMRStrategyV11

    try:
        from apps.reference.domains.regime_allowlist.contract import (  # type: ignore
            RegimeAllowlistContract,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise CalibrationError(
            "RUNTIME_IMPORT_BLOCKED",
            "MD-AMR calibration requires RegimeAllowlistContract.",
        ) from exc
    _REGIME_ALLOWLIST_CONTRACT = RegimeAllowlistContract


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


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
            "tf_sec": 900,
        }
    )
    out = out[(out["timestamp"] >= int(start_close_ms))
              & (out["timestamp"] <= int(end_close_ms))]
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    return out


def _canonicalize_ohlcv_900(df: pd.DataFrame) -> pd.DataFrame:
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
    out["tf_sec"] = 900
    out = out[np.isfinite(out["timestamp"])].copy()
    out["timestamp"] = out["timestamp"].astype(np.int64)
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    return out


def _recompute_segments(df: pd.DataFrame, *, basis_tf_sec: int = 900) -> pd.DataFrame:
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
    canonical_local = _canonicalize_ohlcv_900(local_df)
    if not enable:
        return _recompute_segments(canonical_local, basis_tf_sec=900)

    interval_ms = 900_000
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
        if fetch_end < fetch_start:
            sym_frames.append(local_sym)
            continue
        try:
            remote_sym = _fetch_binance_futures_klines(
                symbol=symbol,
                interval="15m",
                interval_ms=interval_ms,
                start_close_ms=fetch_start,
                end_close_ms=fetch_end,
                base_url=base_url,
                timeout_sec=timeout_sec,
                pause_sec=pause_sec,
            )
        except Exception as exc:
            raise CalibrationError(
                "BINANCE_HYDRATION_FAILED",
                f"Binance hydration failed for {symbol}: {exc}",
                details={"symbol": symbol},
            ) from exc

        if local_sym.empty:
            merged = remote_sym
            added = len(remote_sym)
        else:
            local_ts = set(local_sym["timestamp"].astype(np.int64).tolist())
            missing = remote_sym[~remote_sym["timestamp"].astype(
                np.int64).isin(local_ts)].copy()
            merged = pd.concat([local_sym, missing], ignore_index=True)
            added = len(missing)

        merged = merged.drop_duplicates(
            subset=["symbol", "timestamp"], keep="last")
        merged = merged.sort_values(
            ["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
        total_added += int(added)
        sym_frames.append(merged)

    if not sym_frames:
        raise CalibrationError(
            "DATASET_EMPTY", "Binance hydration produced no rows")

    out = pd.concat(sym_frames, ignore_index=True)
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    out = _recompute_segments(out, basis_tf_sec=900)
    out.attrs["binance_rows_added"] = int(total_added)
    return out


def _load_md_amr_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("md_amr"), dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            f"Invalid md_amr strategy YAML (expected top-level 'md_amr'): {path}",
        )
    return dict(raw["md_amr"])


def _extract_base_params(md_amr_cfg: dict[str, Any]) -> dict[str, Any]:
    required_keys = [
        "channel_window_bars",
        "hysteresis_mult",
        "threshold_z",
        "volatility_dampening_factor",
        "thr_base",
        "alpha",
        "conf_min",
        "max_hold_bars",
        "fee_bps",
        "slippage_buffer_bps",
        "scaleout_fraction",
        "atr_zscore_clamp",
        "atr_std_floor_pct",
        "thr_floor",
        "scaleout_cost_model",
        "atr_window",
        "atr_stats_window",
        "hold_edge_min",
        "target_approach_pct",
    ]
    missing = [key for key in required_keys if key not in md_amr_cfg]
    if missing:
        raise CalibrationError(
            "CONFIG_INVALID",
            f"md_amr config missing required keys: {missing}",
            details={"missing_keys": missing},
        )
    progress_tracking = md_amr_cfg.get("progress_tracking")
    if not isinstance(progress_tracking, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "md_amr.progress_tracking missing or invalid in strategy profile",
        )
    setup_quality = md_amr_cfg.get("setup_quality")
    if not isinstance(setup_quality, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "md_amr.setup_quality missing or invalid in strategy profile",
        )
    hold_quality = md_amr_cfg.get("hold_quality")
    if not isinstance(hold_quality, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "md_amr.hold_quality missing or invalid in strategy profile",
        )
    context_validity = md_amr_cfg.get("context_validity")
    if not isinstance(context_validity, dict):
        raise CalibrationError(
            "CONFIG_INVALID",
            "md_amr.context_validity missing or invalid in strategy profile",
        )
    return {
        "channel_window_bars": int(md_amr_cfg["channel_window_bars"]),
        "hysteresis_mult": float(md_amr_cfg["hysteresis_mult"]),
        "threshold_z": float(md_amr_cfg["threshold_z"]),
        "volatility_dampening_factor": float(md_amr_cfg["volatility_dampening_factor"]),
        "thr_base": float(md_amr_cfg["thr_base"]),
        "alpha": float(md_amr_cfg["alpha"]),
        "conf_min": float(md_amr_cfg["conf_min"]),
        "max_hold_bars": int(md_amr_cfg["max_hold_bars"]),
        "fee_bps": float(md_amr_cfg["fee_bps"]),
        "slippage_buffer_bps": float(md_amr_cfg["slippage_buffer_bps"]),
        "scaleout_fraction": float(md_amr_cfg["scaleout_fraction"]),
        "atr_zscore_clamp": float(md_amr_cfg["atr_zscore_clamp"]),
        "atr_std_floor_pct": float(md_amr_cfg["atr_std_floor_pct"]),
        "thr_floor": float(md_amr_cfg["thr_floor"]),
        "scaleout_cost_model": str(md_amr_cfg["scaleout_cost_model"]),
        "atr_window": int(md_amr_cfg["atr_window"]),
        "atr_stats_window": int(md_amr_cfg["atr_stats_window"]),
        "hold_edge_min": float(md_amr_cfg["hold_edge_min"]),
        "target_approach_pct": float(md_amr_cfg["target_approach_pct"]),
        "progress_tracking_early_progress_max_pct": float(progress_tracking["early_progress_max_pct"]),
        "progress_tracking_partial_progress_max_pct": float(progress_tracking["partial_progress_max_pct"]),
        "progress_tracking_near_completion_max_pct": float(progress_tracking["near_completion_max_pct"]),
        "setup_quality_penetration_depth_full_scale": float(setup_quality["penetration_depth_full_scale"]),
        "setup_quality_channel_width_pct_full_scale": float(setup_quality["channel_width_pct_full_scale"]),
        "setup_quality_volatility_z_full_penalty": float(setup_quality["volatility_z_full_penalty"]),
        "hold_quality_expected_progress_grace_frac": float(hold_quality["expected_progress_grace_frac"]),
        "hold_quality_time_decay_weight": float(hold_quality["time_decay_weight"]),
        "hold_quality_progress_deficit_weight": float(hold_quality["progress_deficit_weight"]),
        "context_validity_regime_confidence_floor": float(context_validity["regime_confidence_floor"]),
        "context_validity_regime_confidence_valid": float(context_validity["regime_confidence_valid"]),
        "context_validity_volatility_z_weakening": float(context_validity["volatility_z_weakening"]),
        "context_validity_volatility_z_invalid": float(context_validity["volatility_z_invalid"]),
        "context_validity_channel_width_pct_floor": float(context_validity["channel_width_pct_floor"]),
        "context_validity_channel_width_pct_valid": float(context_validity["channel_width_pct_valid"]),
        "context_validity_regime_weight": float(context_validity["regime_weight"]),
        "context_validity_volatility_weight": float(context_validity["volatility_weight"]),
        "context_validity_structure_weight": float(context_validity["structure_weight"]),
        "context_validity_progress_alignment_weight": float(context_validity["progress_alignment_weight"]),
        "context_validity_valid_score_min": float(context_validity["valid_score_min"]),
        "context_validity_invalid_score_max": float(context_validity["invalid_score_max"]),
    }


def _extract_baseline_weights(md_amr_cfg: dict[str, Any]) -> dict[str, float]:
    weights = md_amr_cfg.get("weights")
    if not isinstance(weights, dict):
        raise CalibrationError(
            "CONFIG_INVALID", "md_amr.weights missing or invalid in strategy profile")
    missing = [key for key in WEIGHT_KEYS if key not in weights]
    if missing:
        raise CalibrationError(
            "CONFIG_INVALID",
            f"md_amr.weights missing keys: {missing}",
            details={"missing_weight_keys": missing},
        )
    return {key: float(weights[key]) for key in WEIGHT_KEYS}


def _extract_asset_configs(md_amr_cfg: dict[str, Any], symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
    assets = md_amr_cfg.get("assets")
    if not isinstance(assets, dict):
        raise CalibrationError(
            "CONFIG_INVALID", "md_amr.assets missing or invalid in strategy profile")
    out: dict[str, dict[str, Any]] = {}
    for raw_symbol in symbols:
        symbol = str(raw_symbol).upper()
        asset_cfg = assets.get(symbol)
        if not isinstance(asset_cfg, dict):
            raise CalibrationError(
                "CONFIG_INVALID",
                f"md_amr.assets.{symbol} missing or invalid for requested calibration scope",
                details={"symbol": symbol},
            )
        if not bool(asset_cfg.get("enabled", True)):
            raise CalibrationError(
                "CONFIG_INVALID",
                f"md_amr.assets.{symbol}.enabled must be true for calibration scope",
                details={"symbol": symbol},
            )
        exit_cfg = asset_cfg.get("exit")
        if not isinstance(exit_cfg, dict):
            raise CalibrationError(
                "CONFIG_INVALID",
                f"md_amr.assets.{symbol}.exit missing or invalid for calibration scope",
                details={"symbol": symbol},
            )
        if exit_cfg.get("sl_pct") is None or exit_cfg.get("tp_rr") is None:
            raise CalibrationError(
                "CONFIG_INVALID",
                f"md_amr.assets.{symbol}.exit requires sl_pct and tp_rr",
                details={"symbol": symbol},
            )
        out[symbol] = dict(asset_cfg)
    return out


def _normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    vals = np.array([max(0.0, float(raw[key]))
                    for key in WEIGHT_KEYS], dtype=float)
    total = float(np.sum(vals))
    if total <= 1.0e-12:
        vals = np.array([0.25, 0.25, 0.25, 0.25], dtype=float)
        total = 1.0
    vals = vals / total
    return {key: float(value) for key, value in zip(WEIGHT_KEYS, vals)}


def _sample_weights(rng: np.random.Generator) -> dict[str, float]:
    vals = rng.dirichlet(np.ones(len(WEIGHT_KEYS), dtype=float))
    return {key: float(vals[idx]) for idx, key in enumerate(WEIGHT_KEYS)}


def _score_or_floor(value: float | None) -> float:
    if value is None or not math.isfinite(float(value)):
        return NEGATIVE_FLOOR
    return float(value)


def _default_out_dir(args: argparse.Namespace) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scope = "-".join(str(symbol).upper() for symbol in args.symbols)
    safe_scope = scope.replace("/", "_").replace(" ", "_")[:120]
    return Path("reports") / "calibration" / "md_amr" / f"{stamp}_{safe_scope}"


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


def _resolve_windows(df: pd.DataFrame, *, validation_days: int, forward_days: int, min_train_days: int) -> WindowSpec:
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
        "symbol", "timestamp"]
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
            "segments": int(sdf["segment_id"].nunique()) if "segment_id" in sdf.columns and not sdf.empty else (1 if not sdf.empty else 0),
        }
    return stats


def _validate_window_coverage(window_name: str, stats: dict[str, Any], *, warmup_bars: int) -> None:
    blockers: list[dict[str, Any]] = []
    required_rows = int(warmup_bars) + 1
    for symbol, payload in stats.get("per_symbol", {}).items():
        if int(payload.get("rows", 0)) < required_rows or int(payload.get("longest_segment_rows", 0)) < required_rows:
            blockers.append(
                {
                    "symbol": str(symbol),
                    "rows": int(payload.get("rows", 0)),
                    "longest_segment_rows": int(payload.get("longest_segment_rows", 0)),
                    "required_rows": required_rows,
                }
            )
    if blockers:
        raise CalibrationError(
            "INSUFFICIENT_DATA",
            f"{window_name} window lacks contiguous history for MD-AMR warmup.",
            details={"window": window_name, "blockers": blockers},
        )


def _dataset_fingerprint(df: pd.DataFrame) -> str:
    if df.empty:
        return "empty"
    key_columns = ["symbol", "timestamp",
                   "open", "high", "low", "close", "volume"]
    hashed = pd.util.hash_pandas_object(
        df[key_columns].reset_index(drop=True), index=False)
    return hashlib.sha256(hashed.values.tobytes()).hexdigest()


def _make_strategy(base_params: dict[str, Any], weights: dict[str, float]) -> Any:
    _require_md_amr_runtime()
    return _MD_AMR_STRATEGY_V11(
        channel_window_bars=int(base_params["channel_window_bars"]),
        hysteresis_mult=float(base_params["hysteresis_mult"]),
        threshold_z=float(base_params["threshold_z"]),
        volatility_dampening_factor=float(
            base_params["volatility_dampening_factor"]),
        thr_base=float(base_params["thr_base"]),
        alpha=float(base_params["alpha"]),
        conf_min=float(base_params["conf_min"]),
        max_hold_bars=int(base_params["max_hold_bars"]),
        fee_bps=float(base_params["fee_bps"]),
        slippage_buffer_bps=float(base_params["slippage_buffer_bps"]),
        scaleout_fraction=float(base_params["scaleout_fraction"]),
        weights=dict(weights),
        atr_zscore_clamp=float(base_params["atr_zscore_clamp"]),
        atr_std_floor_pct=float(base_params["atr_std_floor_pct"]),
        thr_floor=float(base_params["thr_floor"]),
        scaleout_cost_model=str(base_params["scaleout_cost_model"]),
        atr_window=int(base_params["atr_window"]),
        atr_stats_window=int(base_params["atr_stats_window"]),
        hold_edge_min=float(base_params["hold_edge_min"]),
        target_approach_pct=float(base_params["target_approach_pct"]),
        progress_tracking_early_progress_max_pct=float(
            base_params["progress_tracking_early_progress_max_pct"]),
        progress_tracking_partial_progress_max_pct=float(
            base_params["progress_tracking_partial_progress_max_pct"]),
        progress_tracking_near_completion_max_pct=float(
            base_params["progress_tracking_near_completion_max_pct"]),
        setup_quality_penetration_depth_full_scale=float(
            base_params["setup_quality_penetration_depth_full_scale"]),
        setup_quality_channel_width_pct_full_scale=float(
            base_params["setup_quality_channel_width_pct_full_scale"]),
        setup_quality_volatility_z_full_penalty=float(
            base_params["setup_quality_volatility_z_full_penalty"]),
        hold_quality_expected_progress_grace_frac=float(
            base_params["hold_quality_expected_progress_grace_frac"]),
        hold_quality_time_decay_weight=float(
            base_params["hold_quality_time_decay_weight"]),
        hold_quality_progress_deficit_weight=float(
            base_params["hold_quality_progress_deficit_weight"]),
        context_validity_regime_confidence_floor=float(
            base_params["context_validity_regime_confidence_floor"]),
        context_validity_regime_confidence_valid=float(
            base_params["context_validity_regime_confidence_valid"]),
        context_validity_volatility_z_weakening=float(
            base_params["context_validity_volatility_z_weakening"]),
        context_validity_volatility_z_invalid=float(
            base_params["context_validity_volatility_z_invalid"]),
        context_validity_channel_width_pct_floor=float(
            base_params["context_validity_channel_width_pct_floor"]),
        context_validity_channel_width_pct_valid=float(
            base_params["context_validity_channel_width_pct_valid"]),
        context_validity_regime_weight=float(
            base_params["context_validity_regime_weight"]),
        context_validity_volatility_weight=float(
            base_params["context_validity_volatility_weight"]),
        context_validity_structure_weight=float(
            base_params["context_validity_structure_weight"]),
        context_validity_progress_alignment_weight=float(
            base_params["context_validity_progress_alignment_weight"]),
        context_validity_valid_score_min=float(
            base_params["context_validity_valid_score_min"]),
        context_validity_invalid_score_max=float(
            base_params["context_validity_invalid_score_max"]),
    )


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CalibrationError(
            "DATASET_INVALID", f"Unable to coerce numeric value to Decimal: {value}") from exc


# ---------------------------------------------------------------------------
# Regime normalisation / expansion helpers
# Mirrors md_amr_handler._REGIME_ALIAS_MAP / _REGIME_COMPATIBILITY_MAP
# without importing the handler (which drags FSM/Message dependencies).
# ---------------------------------------------------------------------------
_REGIME_ALIAS_MAP: dict[str, str] = {
    "LOW_FLAT": "FLAT_LOW",
    "HIGH_FLAT": "FLAT_HIGH",
    "HIGHT_FLAT": "FLAT_HIGH",
    "NORMAL_FLAT": "FLAT_NORMAL",
    "HIGH_VOLATILYTY": "HIGH_VOLATILITY",
    "LOW_VOLATILYTY": "LOW_VOLATILITY",
    "HIGHT_VOLATILITY": "HIGH_VOLATILITY",
}

_REGIME_COMPATIBILITY_MAP: dict[str, tuple[str, ...]] = {
    "FLAT_LOW": ("FLAT_LOW", "LOW_VOLATILITY"),
    "LOW_VOLATILITY": ("LOW_VOLATILITY", "FLAT_LOW"),
    "FLAT_NORMAL": ("FLAT_NORMAL", "MEAN_REVERSION"),
    "MEAN_REVERSION": ("MEAN_REVERSION", "FLAT_NORMAL"),
    "FLAT_HIGH": ("FLAT_HIGH", "HIGH_VOLATILITY"),
    "HIGH_VOLATILITY": ("HIGH_VOLATILITY", "FLAT_HIGH"),
}


def _normalize_regime_for_calibrator(regime: Any) -> str:
    """Normalize a regime label using the same alias map as production handler."""
    raw = str(regime or "").strip().upper()
    return _REGIME_ALIAS_MAP.get(raw, raw)


def _expand_allowed_regimes(allowed_regimes: Sequence[str]) -> list[str]:
    """Expand an allowed_regimes list via the compatibility map (production parity)."""
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_regime in allowed_regimes:
        normalized = _normalize_regime_for_calibrator(raw_regime)
        compatible = _REGIME_COMPATIBILITY_MAP.get(normalized, (normalized,))
        for regime in compatible:
            if regime and regime not in seen:
                seen.add(regime)
                expanded.append(regime)
    return expanded


def _compute_regime_labels(df: pd.DataFrame) -> pd.Series:
    """Compute regime labels from OHLCV using simplified regime detector logic.

    Uses 15-min bar equivalents of the 5-min production regime detector
    (config/aurora/regime.yaml).  SMA periods scaled 3x: 48→16, 192→64.
    ATR baseline 288→96.  Priority cascade: VOL → MR → TREND → UNCERTAIN.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = close.shift(1)

    # True Range → Wilder EMA ATR(14) → ATR baseline MA(96)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
    atr_baseline = atr.rolling(96, min_periods=48).mean()
    vol_ratio = atr / atr_baseline

    # SMA short(16) / long(64)
    sma_short = close.rolling(16, min_periods=16).mean()
    sma_long = close.rolling(64, min_periods=64).mean()

    regime = pd.Series("UNCERTAIN", index=df.index)

    # Priority 1: Volatility
    regime = regime.where(~(vol_ratio > 2.0), "HIGH_VOLATILITY")
    regime = regime.where(~((vol_ratio < 0.7) & (regime == "UNCERTAIN")), "LOW_VOLATILITY")

    # Priority 2: Mean Reversion (only where still UNCERTAIN)
    mask_unc = regime == "UNCERTAIN"
    sma_spread = (sma_short - sma_long).abs() / sma_long
    dev_short = (close - sma_short).abs() / sma_short
    dev_long = (close - sma_long).abs() / sma_long
    mr_mask = mask_unc & (sma_spread < 0.005) & (dev_short < 0.005) & (dev_long < 0.005)
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


def _run_per_regime_analysis(
    df_raw: pd.DataFrame,
    *,
    symbols: list[str],
    base_params: dict[str, Any],
    weights: dict[str, float],
    asset_cfgs: dict[str, dict[str, Any]],
    tf_sec: int,
    warmup_bars: int,
    guardrails: GuardrailCfg,
    out_dir: Path,
) -> dict[str, Any]:
    """Run per-regime breakdown on computed-regime data.

    For each unique regime label found in df_raw["regime"], filter to only those
    rows, evaluate with baseline weights, and collect per-regime metrics.
    Prints a summary table and writes per_regime_analysis.json.
    """
    all_regimes = sorted(df_raw["regime"].dropna().unique().tolist())
    # Exclude passthrough labels
    passthrough = {"", "DEFAULT", "UNKNOWN", "PENDING", "NONE"}
    regimes = [r for r in all_regimes if r not in passthrough]

    results: dict[str, dict[str, Any]] = {}
    for regime_label in regimes:
        regime_df = df_raw[df_raw["regime"] == regime_label].copy()
        if regime_df.empty:
            continue
        metrics = _evaluate_window(
            regime_df,
            symbols=symbols,
            base_params=base_params,
            weights=weights,
            asset_cfgs=asset_cfgs,
            tf_sec=tf_sec,
            warmup_bars=warmup_bars,
            guardrails=guardrails,
        )
        results[regime_label] = metrics

    # Print table
    header = f"{'Regime':<20} {'Bars':>6} {'Entries':>8} {'Trades':>7} {'WR%':>6} {'PF':>7} {'Net%':>8} {'DD%':>7}"
    print("\n" + "=" * len(header))
    print("PER-REGIME BREAKDOWN (baseline weights)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for regime_label in regimes:
        m = results.get(regime_label)
        if m is None:
            continue
        wr = float(m.get("win_rate") or 0.0) * 100
        pf = float(m.get("profit_factor") or 0.0)
        net = float(m.get("net_return_ratio") or 0.0) * 100
        dd = float(m.get("max_drawdown_ratio") or 0.0) * 100
        print(
            f"{regime_label:<20} {m.get('rows', 0):>6} {m.get('entry_count', 0):>8} "
            f"{m.get('total_trades', 0):>7} {wr:>5.1f}% {pf:>7.2f} {net:>+7.2f}% {dd:>6.2f}%"
        )
    print("-" * len(header))

    # Serialize
    payload = {
        "regime_labels": regimes,
        "weights_used": weights,
        "per_regime": {
            label: {
                "rows": int(m.get("rows", 0)),
                "entry_count": int(m.get("entry_count", 0)),
                "total_trades": int(m.get("total_trades", 0)),
                "win_rate": float(m.get("win_rate", 0.0)),
                "profit_factor": float(m.get("profit_factor") or 0.0),
                "net_return_ratio": float(m.get("net_return_ratio", 0.0)),
                "max_drawdown_ratio": float(m.get("max_drawdown_ratio", 0.0)),
                "selection_score": m.get("selection_score"),
                "entries_per_day": float(m.get("entries_per_day", 0.0)),
                "avg_holding_bars": float(m.get("avg_holding_bars", 0.0)),
                "regime_blocked_count": int(sum(
                    sm.get("regime_blocked_count", 0)
                    for sm in (m.get("per_symbol") or {}).values()
                )),
            }
            for label, m in results.items()
        },
    }
    _write_json(out_dir / "per_regime_analysis.json", payload)
    print(f"\nPer-regime analysis written to {out_dir / 'per_regime_analysis.json'}")
    return payload


def _compute_tpsl_from_asset_cfg(
    *,
    entry_price: Decimal,
    side: str,
    regime: str,
    asset_cfg: dict[str, Any],
) -> dict[str, Any] | None:
    exit_cfg = asset_cfg.get("exit")
    if not isinstance(exit_cfg, dict):
        return None
    tpsl_cfg = exit_cfg.get("regime_tpsl")
    if not isinstance(tpsl_cfg, dict) or not bool(tpsl_cfg.get("enabled", False)):
        return None
    sl_pct_raw = exit_cfg.get("sl_pct")
    tp_rr_raw = exit_cfg.get("tp_rr")
    if sl_pct_raw is None or tp_rr_raw is None:
        return None

    sl_pct_base = float(sl_pct_raw)
    tp_rr_base = float(tp_rr_raw)
    sl_mult_map = dict(tpsl_cfg.get("sl_mult") or {})
    tp_mult_map = dict(tpsl_cfg.get("tp_mult") or {})

    regime_used = str(regime or "DEFAULT").upper()
    if regime_used in {"", "UNKNOWN"}:
        regime_used = "DEFAULT"
    sl_mult = float(sl_mult_map.get(
        regime_used, sl_mult_map.get("DEFAULT", 1.0)))
    tp_mult = float(tp_mult_map.get(
        regime_used, tp_mult_map.get("DEFAULT", 1.0)))

    sl_pct_eff = sl_pct_base * sl_mult
    tp_rr_eff = tp_rr_base * tp_mult
    sl_dec = Decimal(str(sl_pct_eff))
    tp_dist_dec = sl_dec * Decimal(str(tp_rr_eff))

    side_upper = str(side).upper()
    if side_upper == "BUY":
        stop_price = entry_price * (Decimal("1") - sl_dec)
        target_price = entry_price * (Decimal("1") + tp_dist_dec)
    elif side_upper == "SELL":
        stop_price = entry_price * (Decimal("1") + sl_dec)
        target_price = entry_price * (Decimal("1") - tp_dist_dec)
    else:
        return None

    return _apply_tpsl_guardrails(
        entry_price=entry_price,
        side=side_upper,
        stop_price=stop_price,
        target_price=target_price,
        tpsl_cfg=tpsl_cfg,
        tpsl_ctx={
            "mode": "pct_mult",
            "regime_used": regime_used,
            "sl_pct_base": sl_pct_base,
            "sl_mult": sl_mult,
            "sl_pct_eff": sl_pct_eff,
            "tp_rr_base": tp_rr_base,
            "tp_mult": tp_mult,
            "tp_rr_eff": tp_rr_eff,
        },
    )


def _apply_tpsl_guardrails(
    *,
    entry_price: Decimal,
    side: str,
    stop_price: Decimal,
    target_price: Decimal,
    tpsl_cfg: dict[str, Any],
    tpsl_ctx: dict[str, Any],
) -> dict[str, Any] | None:
    min_sl_pct = Decimal(str(tpsl_cfg.get("min_sl_pct", 0.003)))
    max_sl_pct = Decimal(str(tpsl_cfg.get("max_sl_pct", 0.060)))
    min_tp_rr = Decimal(str(tpsl_cfg.get("min_tp_rr", 0.3)))
    max_tp_rr = Decimal(str(tpsl_cfg.get("max_tp_rr", 3.0)))
    min_dist_bps = int(tpsl_cfg.get("min_dist_bps", 15))

    if side == "BUY":
        sl_dist_pct = (entry_price - stop_price) / entry_price
        tp_dist_pct = (target_price - entry_price) / entry_price
    else:
        sl_dist_pct = (stop_price - entry_price) / entry_price
        tp_dist_pct = (entry_price - target_price) / entry_price

    if sl_dist_pct <= 0 or tp_dist_pct <= 0:
        return None

    if sl_dist_pct < min_sl_pct:
        sl_dist_pct = min_sl_pct
        stop_price = entry_price * \
            (Decimal("1") - sl_dist_pct) if side == "BUY" else entry_price * \
            (Decimal("1") + sl_dist_pct)
        tpsl_ctx["guardrail_sl_clamp"] = "min"
    elif sl_dist_pct > max_sl_pct:
        sl_dist_pct = max_sl_pct
        stop_price = entry_price * \
            (Decimal("1") - sl_dist_pct) if side == "BUY" else entry_price * \
            (Decimal("1") + sl_dist_pct)
        tpsl_ctx["guardrail_sl_clamp"] = "max"

    actual_rr = tp_dist_pct / sl_dist_pct if sl_dist_pct > 0 else Decimal("0")
    if actual_rr < min_tp_rr:
        tp_dist_pct = sl_dist_pct * min_tp_rr
        target_price = entry_price * \
            (Decimal("1") + tp_dist_pct) if side == "BUY" else entry_price * \
            (Decimal("1") - tp_dist_pct)
        tpsl_ctx["guardrail_tp_clamp"] = "min"
        actual_rr = min_tp_rr
    elif actual_rr > max_tp_rr:
        tp_dist_pct = sl_dist_pct * max_tp_rr
        target_price = entry_price * \
            (Decimal("1") + tp_dist_pct) if side == "BUY" else entry_price * \
            (Decimal("1") - tp_dist_pct)
        tpsl_ctx["guardrail_tp_clamp"] = "max"
        actual_rr = max_tp_rr

    min_dist = entry_price * Decimal(str(min_dist_bps)) / Decimal("10000")
    if abs(entry_price - stop_price) < min_dist or abs(entry_price - target_price) < min_dist:
        return None

    tpsl_ctx["sl_pct_post"] = float(sl_dist_pct)
    tpsl_ctx["rr_post"] = float(actual_rr)
    return {"stop_price": stop_price, "target_price": target_price, "tpsl_ctx": dict(tpsl_ctx)}


def _resolve_intrabar_tpsl(
    *,
    side: str,
    bar_high: float,
    bar_low: float,
    stop_price: Decimal | None,
    target_price: Decimal | None,
) -> dict[str, Any] | None:
    if stop_price is None or target_price is None:
        return None
    stop_value = float(stop_price)
    target_value = float(target_price)
    side_upper = str(side).upper()
    if side_upper == "BUY":
        hit_stop = float(bar_low) <= stop_value
        hit_target = float(bar_high) >= target_value
    else:
        hit_stop = float(bar_high) >= stop_value
        hit_target = float(bar_low) <= target_value

    if not hit_stop and not hit_target:
        return None

    ambiguous = bool(hit_stop and hit_target)
    if hit_stop:
        return {
            "exit_price": stop_price,
            "reason": "TPSL_AMBIGUOUS_STOP_FIRST" if ambiguous else "STOP_PRICE_HIT",
            "ambiguous": ambiguous,
        }
    return {
        "exit_price": target_price,
        "reason": "TARGET_PRICE_HIT",
        "ambiguous": False,
    }


def _realize_leg(
    *,
    symbol: str,
    trade_id: str,
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    fraction_closed: float,
    entry_ts_ms: int,
    exit_ts_ms: int,
    exit_reason: str,
    per_side_cost_ratio: float,
) -> dict[str, Any]:
    if entry_price <= 0:
        gross_return_ratio = 0.0
    elif str(side).upper() == "BUY":
        gross_return_ratio = float((exit_price - entry_price) / entry_price)
    else:
        gross_return_ratio = float((entry_price - exit_price) / entry_price)
    net_return_ratio = float(
        fraction_closed) * (gross_return_ratio - 2.0 * float(per_side_cost_ratio))
    return {
        "symbol": str(symbol),
        "trade_id": str(trade_id),
        "side": str(side).upper(),
        "entry_ts_ms": int(entry_ts_ms),
        "exit_ts_ms": int(exit_ts_ms),
        "fraction_closed": float(fraction_closed),
        "exit_reason": str(exit_reason),
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "net_return_ratio": float(net_return_ratio),
        "gross_return_ratio": float(fraction_closed) * float(gross_return_ratio),
    }


def _trade_records_from_legs(legs: list[dict[str, Any]], *, tf_sec: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for leg in legs:
        trade_id = str(leg["trade_id"])
        record = grouped.setdefault(
            trade_id,
            {
                "trade_id": trade_id,
                "symbol": str(leg["symbol"]),
                "side": str(leg["side"]),
                "entry_ts_ms": int(leg["entry_ts_ms"]),
                "exit_ts_ms": int(leg["exit_ts_ms"]),
                "net_return_ratio": 0.0,
                "gross_return_ratio": 0.0,
                "leg_count": 0,
                "exit_reasons": [],
            },
        )
        record["exit_ts_ms"] = max(
            int(record["exit_ts_ms"]), int(leg["exit_ts_ms"]))
        record["net_return_ratio"] += float(leg["net_return_ratio"])
        record["gross_return_ratio"] += float(leg["gross_return_ratio"])
        record["leg_count"] += 1
        record["exit_reasons"].append(str(leg["exit_reason"]))
    out = []
    for record in grouped.values():
        holding_bars = max(1, int(round(
            (int(record["exit_ts_ms"]) - int(record["entry_ts_ms"])) / (int(tf_sec) * 1000.0))))
        record["holding_bars"] = holding_bars
        out.append(record)
    out.sort(key=lambda item: (int(item["exit_ts_ms"]), str(
        item["symbol"]), str(item["trade_id"])))
    return out


def _metrics_from_trade_records(
    trade_records: list[dict[str, Any]],
    *,
    row_count: int,
    unique_days: list[str],
    entry_count: int,
    signal_count: int,
    leg_count: int,
    forced_close_count: int,
    tpsl_exit_count: int,
    ambiguous_tpsl_count: int,
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
        gross_profit / gross_loss) if gross_loss > 0 else (None if gross_profit <= 0 else None)

    cumulative = 0.0
    running_peak = 0.0
    max_drawdown_ratio = 0.0
    for item in trade_records:
        cumulative += float(item["net_return_ratio"])
        running_peak = max(running_peak, cumulative)
        max_drawdown_ratio = max(max_drawdown_ratio, running_peak - cumulative)
    calmar_ratio = float(
        net_return_ratio / max_drawdown_ratio) if max_drawdown_ratio > 1.0e-12 else float(net_return_ratio)
    selection_score = None
    if total_trades >= int(guardrails.min_trades) and max_drawdown_ratio <= float(guardrails.max_drawdown_ratio):
        selection_score = float(calmar_ratio * math.log1p(total_trades))

    avg_holding_bars = float(sum(int(
        item["holding_bars"]) for item in trade_records) / total_trades) if total_trades else 0.0
    entries_per_day = float(entry_count / max(1, len(unique_days)))

    return {
        "rows": int(row_count),
        "unique_days": list(unique_days),
        "entry_count": int(entry_count),
        "signal_count": int(signal_count),
        "realized_leg_count": int(leg_count),
        "total_trades": int(total_trades),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": float(win_rate),
        "net_return_ratio": float(net_return_ratio),
        "gross_return_ratio": float(gross_return_ratio),
        "avg_trade_return_ratio": float(avg_trade_return_ratio),
        "profit_factor": profit_factor,
        "max_drawdown_ratio": float(max_drawdown_ratio),
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
    base_params: dict[str, Any],
    weights: dict[str, float],
    asset_cfg: dict[str, Any],
    tf_sec: int,
    warmup_bars: int,
    guardrails: GuardrailCfg,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    strategy = None
    legs: list[dict[str, Any]] = []
    entry_count = 0
    regime_blocked_count = 0
    signal_count = 0
    forced_close_count = 0
    tpsl_exit_count = 0
    ambiguous_tpsl_count = 0
    leg_count = 0
    trade_seq = 0
    per_side_cost_ratio = (float(
        base_params["fee_bps"]) + float(base_params["slippage_buffer_bps"])) / 10000.0

    # GAP 3: Pre-compute expanded allowed regimes (production parity with handler)
    raw_allowed = list(asset_cfg.get("allowed_regimes") or [])
    effective_allowed_regimes = _expand_allowed_regimes(raw_allowed) if raw_allowed else []
    # Regimes that indicate recorder hasn't captured a valid regime label yet.
    # When the recorder regime is unknown/pending, we SKIP the entry gate
    # (otherwise calibration produces 0 entries on recorder data without regime).
    _REGIME_PASSTHROUGH = frozenset({"", "DEFAULT", "UNKNOWN", "PENDING", "NONE"})

    _empty_position: dict[str, Any] = {
        "is_open": False,
        "side": None,
        "entry_price": None,
        "entry_ts_ms": None,
        "remaining_fraction": 0.0,
        "bars_held": 0,
        "stop_price": None,
        "target_price": None,
        "trade_id": None,
        "anchor_entry_price": None,
        "anchor_entry_target_price": None,
    }

    position = dict(_empty_position)

    grouped = (
        df_symbol.groupby("segment_id", sort=False)
        if "segment_id" in df_symbol.columns
        else [(0, df_symbol.copy())]
    )
    for _segment_id, segment in grouped:
        strategy = _make_strategy(base_params, weights)
        bars_seen = 0
        position = dict(_empty_position)

        for row in segment.itertuples(index=False):
            if position["is_open"]:
                exit_hit = _resolve_intrabar_tpsl(
                    side=str(position["side"]),
                    bar_high=float(getattr(row, "high")),
                    bar_low=float(getattr(row, "low")),
                    stop_price=position["stop_price"],
                    target_price=position["target_price"],
                )
                if exit_hit is not None:
                    legs.append(
                        _realize_leg(
                            symbol=symbol,
                            trade_id=str(position["trade_id"]),
                            side=str(position["side"]),
                            entry_price=position["entry_price"],
                            exit_price=exit_hit["exit_price"],
                            fraction_closed=float(
                                position["remaining_fraction"]),
                            entry_ts_ms=int(position["entry_ts_ms"]),
                            exit_ts_ms=int(getattr(row, "timestamp")),
                            exit_reason=str(exit_hit["reason"]),
                            per_side_cost_ratio=per_side_cost_ratio,
                        )
                    )
                    leg_count += 1
                    tpsl_exit_count += 1
                    if bool(exit_hit.get("ambiguous", False)):
                        ambiguous_tpsl_count += 1
                    position = dict(_empty_position)
                    continue

            bars_seen += 1
            if position["is_open"]:
                position["bars_held"] = int(position["bars_held"]) + 1

            # GAP 2: Extract per-bar regime context from recorder data
            bar_regime_raw = str(getattr(row, "regime", "DEFAULT") or "DEFAULT")
            bar_regime = _normalize_regime_for_calibrator(bar_regime_raw)
            bar_regime_conf = float(getattr(row, "regime_conf", 0.0) or 0.0)
            # If the regime is not a real captured label, treat it as passthrough
            # so the entry gate doesn't block on missing/stale recorder data.
            _regime_is_real = bar_regime not in _REGIME_PASSTHROUGH
            bar_regime_allowed = (
                _REGIME_ALLOWLIST_CONTRACT.is_regime_allowed(
                    current_regime=bar_regime,
                    allowed_regimes=effective_allowed_regimes,
                )
                if _REGIME_ALLOWLIST_CONTRACT is not None and _regime_is_real
                else True
            )

            # GAP 1 + GAP 2: Expanded position_ctx with entry anchors + regime context
            result = strategy.on_bar(
                bar={
                    "open": getattr(row, "open"),
                    "high": getattr(row, "high"),
                    "low": getattr(row, "low"),
                    "close": getattr(row, "close"),
                },
                position_ctx={
                    "qty_signed": float(position["remaining_fraction"]) if position["is_open"] and str(position["side"]) == "BUY" else (-float(position["remaining_fraction"]) if position["is_open"] else 0.0),
                    "bars_held": int(position["bars_held"]),
                    "entry_price": position["anchor_entry_price"],
                    "entry_target_price": position["anchor_entry_target_price"],
                    "context_regime": bar_regime,
                    "context_regime_confidence": bar_regime_conf,
                    "context_regime_allowed": bar_regime_allowed,
                },
                llm_blocked=False,
            )
            if result.get("status") == "SIGNAL":
                signal_count += 1

            if bars_seen <= int(warmup_bars):
                continue
            if result.get("status") != "SIGNAL":
                continue
            signal = result.get("signal")
            if signal is None:
                continue

            intent_kind = str(getattr(signal, "intent_kind", ""))
            signal_side = str(getattr(signal, "side", "")).upper()
            close_price = _to_decimal(getattr(signal, "price_ref"))
            row_regime = bar_regime

            if intent_kind == "ENTRY" and not position["is_open"]:
                # GAP 3: Regime entry gate — block entries when regime is not allowed
                if not bar_regime_allowed:
                    regime_blocked_count += 1
                    continue

                trade_seq += 1
                entry_count += 1
                bracket = _compute_tpsl_from_asset_cfg(
                    entry_price=close_price,
                    side=signal_side,
                    regime=row_regime,
                    asset_cfg=asset_cfg,
                )
                # GAP 1: Set entry anchors (mirrors handler lines 2105-2112)
                _ch = dict(getattr(signal, "channel_state", None) or {})
                _avg_close = float(
                    _ch.get("avg_close_12", float(close_price)))
                position = {
                    "is_open": True,
                    "side": signal_side,
                    "entry_price": close_price,
                    "entry_ts_ms": int(getattr(row, "timestamp")),
                    "remaining_fraction": 1.0,
                    "bars_held": 0,
                    "stop_price": bracket["stop_price"] if bracket else None,
                    "target_price": bracket["target_price"] if bracket else None,
                    "trade_id": f"{symbol}:{trade_seq}",
                    "anchor_entry_price": float(close_price),
                    "anchor_entry_target_price": _avg_close,
                }
                continue

            if not position["is_open"] or intent_kind not in {"FULL_CLOSE", "PARTIAL_CLOSE"}:
                continue

            if intent_kind == "PARTIAL_CLOSE":
                fraction_closed = min(
                    float(position["remaining_fraction"]),
                    max(0.0, float(getattr(signal, "scaleout_fraction", 0.0) or 0.0)),
                )
                if fraction_closed <= 1.0e-12:
                    continue
            else:
                fraction_closed = float(position["remaining_fraction"])

            legs.append(
                _realize_leg(
                    symbol=symbol,
                    trade_id=str(position["trade_id"]),
                    side=str(position["side"]),
                    entry_price=position["entry_price"],
                    exit_price=close_price,
                    fraction_closed=fraction_closed,
                    entry_ts_ms=int(position["entry_ts_ms"]),
                    exit_ts_ms=int(getattr(row, "timestamp")),
                    exit_reason=intent_kind,
                    per_side_cost_ratio=per_side_cost_ratio,
                )
            )
            leg_count += 1
            remaining_fraction = float(
                position["remaining_fraction"]) - float(fraction_closed)
            if remaining_fraction <= 1.0e-9 or intent_kind == "FULL_CLOSE":
                position = dict(_empty_position)
            else:
                position["remaining_fraction"] = remaining_fraction

        if position["is_open"]:
            last_row = segment.iloc[-1]
            legs.append(
                _realize_leg(
                    symbol=symbol,
                    trade_id=str(position["trade_id"]),
                    side=str(position["side"]),
                    entry_price=position["entry_price"],
                    exit_price=_to_decimal(last_row["close"]),
                    fraction_closed=float(position["remaining_fraction"]),
                    entry_ts_ms=int(position["entry_ts_ms"]),
                    exit_ts_ms=int(last_row["timestamp"]),
                    exit_reason="SEGMENT_END_FORCE_CLOSE",
                    per_side_cost_ratio=per_side_cost_ratio,
                )
            )
            leg_count += 1
            forced_close_count += 1

    unique_days = _unique_days(df_symbol)
    trade_records = _trade_records_from_legs(legs, tf_sec=tf_sec)
    metrics = _metrics_from_trade_records(
        trade_records,
        row_count=len(df_symbol),
        unique_days=unique_days,
        entry_count=entry_count,
        signal_count=signal_count,
        leg_count=leg_count,
        forced_close_count=forced_close_count,
        tpsl_exit_count=tpsl_exit_count,
        ambiguous_tpsl_count=ambiguous_tpsl_count,
        guardrails=guardrails,
    )
    metrics["regime_blocked_count"] = int(regime_blocked_count)
    return metrics, trade_records


def _evaluate_window(
    df_window: pd.DataFrame,
    *,
    symbols: list[str],
    base_params: dict[str, Any],
    weights: dict[str, float],
    asset_cfgs: dict[str, dict[str, Any]],
    tf_sec: int,
    warmup_bars: int,
    guardrails: GuardrailCfg,
) -> dict[str, Any]:
    per_symbol: dict[str, Any] = {}
    trade_records: list[dict[str, Any]] = []
    aggregate_entry_count = 0
    aggregate_signal_count = 0
    aggregate_leg_count = 0
    aggregate_forced_close_count = 0
    aggregate_tpsl_exit_count = 0
    aggregate_ambiguous_tpsl_count = 0

    for symbol in symbols:
        sdf = df_window[df_window["symbol"].astype(str) == symbol].copy()
        symbol_metrics, symbol_trade_records = _evaluate_symbol_window(
            sdf,
            symbol=symbol,
            base_params=base_params,
            weights=weights,
            asset_cfg=asset_cfgs[symbol],
            tf_sec=tf_sec,
            warmup_bars=warmup_bars,
            guardrails=guardrails,
        )
        per_symbol[symbol] = symbol_metrics
        trade_records.extend(symbol_trade_records)
        aggregate_entry_count += int(symbol_metrics["entry_count"])
        aggregate_signal_count += int(symbol_metrics["signal_count"])
        aggregate_leg_count += int(symbol_metrics["realized_leg_count"])
        aggregate_forced_close_count += int(
            symbol_metrics["forced_close_count"])
        aggregate_tpsl_exit_count += int(symbol_metrics["tpsl_exit_count"])
        aggregate_ambiguous_tpsl_count += int(
            symbol_metrics["ambiguous_tpsl_count"])

    trade_records.sort(key=lambda item: (
        int(item["exit_ts_ms"]), str(item["symbol"]), str(item["trade_id"])))
    aggregate = _metrics_from_trade_records(
        trade_records,
        row_count=len(df_window),
        unique_days=_unique_days(df_window),
        entry_count=aggregate_entry_count,
        signal_count=aggregate_signal_count,
        leg_count=aggregate_leg_count,
        forced_close_count=aggregate_forced_close_count,
        tpsl_exit_count=aggregate_tpsl_exit_count,
        ambiguous_tpsl_count=aggregate_ambiguous_tpsl_count,
        guardrails=guardrails,
    )
    aggregate["per_symbol"] = per_symbol
    return aggregate


def _candidate_sort_key(item: dict[str, Any]) -> tuple[float, float]:
    return (_score_or_floor(item.get("validation_score")), _score_or_floor(item.get("train_score")))


def _weight_signature(weights: dict[str, float]) -> tuple[float, float, float, float]:
    return tuple(round(float(weights[key]), 8) for key in WEIGHT_KEYS)


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


def _overlay_from_weights(weights: dict[str, float]) -> dict[str, Any]:
    return {
        "md_amr": {
            "weights": {key: float(weights[key]) for key in WEIGHT_KEYS},
        }
    }


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
    df_features: pd.DataFrame,
    windows: WindowSpec,
    symbols: list[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "recorder_dir": str(Path(args.recorder_dir)),
        "symbols": list(symbols),
        "date_range": {"start": args.start.isoformat(), "end_exclusive": args.end.isoformat()},
        "tf_sec": int(args.tf_sec),
        "rows_raw": int(len(df_raw)),
        "rows_feature_frame": int(len(df_features)),
        "unique_days": _unique_days(df_raw),
        "fingerprint": _dataset_fingerprint(df_raw),
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
        "binance_hydration": {
            "enabled": bool(args.hydrate_from_binance),
            "rows_added": int(df_raw.attrs.get("binance_rows_added", 0) or 0),
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                    ensure_ascii=False), encoding="utf-8")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False,
                    allow_unicode=False), encoding="utf-8")


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
    candidate_weights = ((candidate_payload or {}).get(
        "selected_candidate") or {}).get("weights") or {}
    baseline_train = ((baseline_metrics or {}).get("train") or {})
    baseline_validation = ((baseline_metrics or {}).get("validation") or {})
    baseline_forward = ((baseline_metrics or {}).get("forward") or {})
    candidate_train = ((candidate_payload or {}).get(
        "selected_candidate") or {}).get("train") or {}
    candidate_validation = (validation_artifact or {}).get("candidate") or {}
    candidate_forward = (forward_artifact or {}).get("candidate") or {}
    dataset_days = ((dataset_audit or {}).get("unique_days") or [])
    failure_lines = []
    if failure is not None:
        failure_lines = [
            f"- Failure code: {failure.code}",
            f"- Failure message: {failure}",
        ]

    risk_conclusions: list[str] = []
    risk_conclusions.append(
        "### Conclusion: Candidate verdict is fail-closed\n"
        f"- Facts: verdict={verdict}; validation_pass={bool((validation_artifact or {}).get('all_passed', False))}; forward_pass={bool((forward_artifact or {}).get('all_passed', False))}.\n"
        f"- Inferences: the tool separated candidate generation from acceptance and did not promote a candidate implicitly.\n"
        "- Assumptions: the recorder rows are representative for the requested date range and symbol scope.\n"
        "- Unknowns: live routing, arbitration, and exchange fill behavior are not proven by this bar-proxy calibration run.\n"
        f"- Symptom: the final verdict is {verdict}.\n"
        "- Root cause: acceptance depends on explicit out-of-sample guardrails rather than best-train-score alone.\n"
        "- Contributing factor: selection score is only a search metric; it is not a promotion override.\n"
        "- Masking layer: the old script printed best weights without a strict verdict contract.\n"
        "- Cause: validation/forward comparison plus guardrail contract.\n"
        "- Mechanism: candidate must survive min-trade, max-drawdown, activity, and baseline-relative checks.\n"
        "- Effect: weak or unstable candidates remain NO_GO even if train metrics look attractive.\n"
        "- Operational risk: operators could still misread overlay output as rollout-ready if they ignore the verdict."
    )
    risk_conclusions.append(
        "### Conclusion: Evaluation remains a bar-proxy, not a full live replay\n"
        f"- Facts: evaluation uses MDAMRStrategyV11 on recorder OHLC bars; dataset fingerprint={((dataset_audit or {}).get('fingerprint') or 'n/a')}.\n"
        "- Inferences: weight ranking is materially closer to runtime math than the previous missing vector-backtest dependency path.\n"
        "- Assumptions: intrabar TP/SL ambiguity is handled conservatively via stop-first policy.\n"
        "- Unknowns: queue position, GTX retry behavior, objective-engine gating, and arbitration are outside this calibrator's proof boundary.\n"
        "- Symptom: outputs are trustworthy for weight-surface comparison, but not equivalent to exchange-execution proof.\n"
        "- Root cause: this package intentionally scopes to a single calibrator skeleton and overlay-only artifacts.\n"
        "- Contributing factor: recorder datasets do not prove venue-side routing or fill quality.\n"
        "- Masking layer: attractive net-return proxies can hide execution-path mismatch if treated as production replay truth.\n"
        "- Cause: calibration uses fixed-notional bar-based trade accounting.\n"
        "- Mechanism: trades are generated from the live strategy core and local TP/SL contract, then summarized as proxy returns.\n"
        "- Effect: baseline-vs-candidate ordering is explicit, but absolute profitability remains approximate.\n"
        "- Operational risk: over-trusting the proxy could promote a candidate that degrades under real routing or fill semantics."
    )
    risk_conclusions.append(
        "### Conclusion: Runtime-surface evidence is partially conflicted\n"
        "- Facts: config/docs/md_amr_strategy_passport.md claims active MD-AMR assignments for XRPUSDT and BNBUSDT, but config/aurora/strategies.yaml in the current workspace does not list md_amr assignments.\n"
        "- Inferences: the weights surface itself is still a real typed/runtime contract, but assignment-level active-scope proof is not fully aligned on disk.\n"
        "- Assumptions: user-requested symbols plus md_amr asset blocks define the intended calibration scope for this package.\n"
        "- Unknowns: whether the live deployment uses a different registry snapshot than the checked-in strategies.yaml.\n"
        "- Symptom: active-surface status is strong for md_amr.weights, weaker for current assignment evidence.\n"
        "- Root cause: passport and runtime config are out of sync in the inspected workspace.\n"
        "- Contributing factor: repository documentation still reflects a different assignment state.\n"
        "- Masking layer: typed config and strategy code can make the assignment drift easy to miss.\n"
        "- Cause: checked-in registry and passport disagree.\n"
        "- Mechanism: one source lists md_amr live symbols while the other omits md_amr assignments.\n"
        "- Effect: the calibrator can be reused, but assignment proof should be reconciled before calling it fully live-scoped.\n"
        "- Operational risk: users may calibrate non-live symbol scope while assuming current deployment alignment."
    )

    report = [
        "# MD-AMR Weight Calibration Report",
        "",
        "## Scope",
        f"- Calibrator: {Path(__file__).name}",
        "- Calibration class: production-aligned stage-1 calibrator for md_amr.weights.",
        "- Mode: overlay-only. No canonical YAML mutation is performed.",
        f"- Symbols: {', '.join(str(symbol).upper() for symbol in args.symbols)}",
        f"- Date range: start={args.start.isoformat()} end_exclusive={args.end.isoformat()}",
        f"- Output dir: {manifest.get('out_dir')}",
        "- Non-goals: no multi-strategy tuning, no automatic rollout, no canonical writeback, no replay-framework rewrite.",
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
                f"- Feature-frame rows: {dataset_audit['rows_feature_frame']}",
                f"- Unique days: {len(dataset_days)} ({', '.join(dataset_days)})",
                f"- Dataset fingerprint: {dataset_audit['fingerprint']}",
                f"- Train days: {', '.join((windows.train_days if windows else []))}",
                f"- Validation days: {', '.join((windows.validation_days if windows else []))}",
                f"- Forward days: {', '.join((windows.forward_days if windows else []))}",
                f"- Binance hydration rows added: {dataset_audit['binance_hydration']['rows_added']}",
            ]
        )
    report.extend(
        [
            "",
            "## Runtime Surface Under Calibration",
            "- Primary runtime anchor: config/docs/md_amr_strategy_passport.md",
            "- Governance anchors: config/docs/CALIBRATION_STANDARD_V1.md and tools/calibration/README.md",
            "- Surface under calibration: md_amr.weights.d1/h1/m30/m15",
            "- Overlay artifact: candidate_md_amr_strategy_overlay.yaml",
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
                f"- Selected weights: {json.dumps(candidate_weights, sort_keys=True)}",
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
            "- Review the overlay manually and keep promotion separate from calibration. No automatic rollout is implied.")
    else:
        report.append(
            "- Treat the overlay as non-promotable until the failed guardrails or evidence gaps are resolved.")
    return "\n".join(report) + "\n"


def _write_failure_bundle(args: argparse.Namespace, out_dir: Path, error: CalibrationError) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "calibrator": "calibrate_md_amr_weights.py",
        "calibration_class": "production",
        "status": "failed_closed",
        "verdict": "NO_GO_CANDIDATE",
        "out_dir": str(out_dir),
        "failure": {"code": error.code, "message": str(error), "details": error.details},
        "runtime_truth_anchors": [
            "config/docs/md_amr_strategy_passport.md",
            "config/docs/CALIBRATION_STANDARD_V1.md",
            "tools/calibration/README.md",
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
            "Production-grade MD-AMR weight calibrator. Uses recorder data, emits overlay-only artifacts, "
            "compares baseline versus candidate across train/validation/forward windows, and never mutates canonical YAML."
        )
    )
    parser.add_argument(
        "--md-amr-yaml", default="config/aurora/strategies/md_amr.yaml")
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument("--symbols", nargs="+", required=True,
                        help="Symbols to calibrate. Must exist under md_amr.assets.")
    parser.add_argument("--start", type=_parse_date,
                        required=True, help="Start date inclusive (YYYY-MM-DD)")
    parser.add_argument("--end", type=_parse_date, required=True,
                        help="End date exclusive (YYYY-MM-DD)")
    parser.add_argument("--tf-sec", type=int, default=900,
                        help="Recorder timeframe seconds. Current MD-AMR contract supports only 900.")
    parser.add_argument("--trials", type=int, default=400,
                        help="Random search trials over the long-only weights simplex.")
    parser.add_argument("--top-k", type=int, default=5,
                        help="How many top train candidates to carry into validation selection.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-days", type=int, default=2,
                        help="Number of trailing unique days reserved for validation.")
    parser.add_argument("--forward-days", type=int, default=2,
                        help="Number of trailing unique days reserved for forward evaluation.")
    parser.add_argument("--min-train-days", type=int, default=2,
                        help="Minimum unique days required in the train window after holdouts.")
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--max-dd-limit", type=float, default=0.35)
    parser.add_argument("--min-activity-ratio", type=float, default=0.5)
    parser.add_argument("--max-activity-ratio", type=float, default=2.5)
    parser.add_argument("--warmup-bars", type=int, default=96)
    parser.add_argument("--out-dir", default=None,
                        help="Artifact output directory. If omitted, a timestamped path is used.")
    parser.add_argument(
        "--hydrate-from-binance",
        action="store_true",
        help="Explicitly backfill missing 15m candles from Binance Futures before calibration. Use with caution: this changes dataset provenance.",
    )
    parser.add_argument("--binance-base-url",
                        default="https://fapi.binance.com")
    parser.add_argument("--binance-timeout-sec", type=float, default=12.0)
    parser.add_argument("--binance-pause-sec", type=float, default=0.03)
    parser.add_argument("--binance-lookback-bars", type=int, default=96)
    parser.add_argument(
        "--per-regime",
        action="store_true",
        help="Compute regime labels from OHLCV and run per-regime breakdown analysis.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.symbols = [str(symbol).upper() for symbol in args.symbols]
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(args)

    try:
        if int(args.tf_sec) != 900:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION",
                f"MD-AMR calibration currently supports only tf_sec=900, got {args.tf_sec}.",
            )
        if args.end <= args.start:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION", "--end must be greater than --start.")
        if int(args.validation_days) <= 0 or int(args.forward_days) <= 0 or int(args.min_train_days) <= 0:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION", "window day arguments must be positive integers.")
        if float(args.max_dd_limit) <= 0.0:
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION", "--max-dd-limit must be positive.")
        if float(args.min_activity_ratio) <= 0.0 or float(args.max_activity_ratio) < float(args.min_activity_ratio):
            raise CalibrationError(
                "INPUT_CONTRACT_VIOLATION", "activity-ratio guardrails must satisfy 0 < min <= max.")

        _require_md_amr_runtime()

        md_amr_cfg = _load_md_amr_yaml(Path(args.md_amr_yaml))
        base_params = _extract_base_params(md_amr_cfg)
        baseline_weights = _normalize_weights(
            _extract_baseline_weights(md_amr_cfg))
        asset_cfgs = _extract_asset_configs(md_amr_cfg, args.symbols)
        search_cfg = SearchCfg(trials=max(1, int(args.trials)), top_k=max(
            1, int(args.top_k)), warmup_bars=max(1, int(args.warmup_bars)))
        guardrails = GuardrailCfg(
            min_trades=max(1, int(args.min_trades)),
            max_drawdown_ratio=float(args.max_dd_limit),
            min_train_days=max(1, int(args.min_train_days)),
            min_activity_ratio=float(args.min_activity_ratio),
            max_activity_ratio=float(args.max_activity_ratio),
        )

        local_df_raw = _LOAD_RECORDER_900(
            Path(args.recorder_dir),
            symbols=list(args.symbols),
            start=args.start,
            end=args.end,
            basis_tf_sec=int(args.tf_sec),
        )
        if local_df_raw.empty and not bool(args.hydrate_from_binance):
            raise CalibrationError(
                "INSUFFICIENT_DATA",
                "No recorder rows found for requested symbols/date range.",
            )
        df_raw = _maybe_hydrate_missing_from_binance(
            local_df=local_df_raw,
            symbols=list(args.symbols),
            start=args.start,
            end=args.end,
            enable=bool(args.hydrate_from_binance),
            lookback_bars=max(1, int(args.binance_lookback_bars)),
            base_url=str(args.binance_base_url),
            timeout_sec=float(args.binance_timeout_sec),
            pause_sec=max(0.0, float(args.binance_pause_sec)),
        )
        if df_raw.empty:
            raise CalibrationError(
                "INSUFFICIENT_DATA", "No rows after recorder/binance data assembly.")

        df_raw = _annotate_day_utc(df_raw)
        df_features = _annotate_day_utc(_COMPUTE_MD_AMR_FEATURES(df_raw))
        if df_features.empty:
            raise CalibrationError("INSUFFICIENT_DATA",
                                   "No rows after MD-AMR feature computation.")

        # Per-regime: compute regime from OHLCV and inject into data
        if bool(getattr(args, "per_regime", False)):
            for sym in args.symbols:
                sym_mask = df_raw["symbol"] == sym
                if sym_mask.any():
                    computed = _compute_regime_labels(df_raw.loc[sym_mask])
                    df_raw.loc[sym_mask, "regime"] = computed.values
            # Recompute features with regime-enriched raw data
            df_features = _annotate_day_utc(_COMPUTE_MD_AMR_FEATURES(df_raw))

        windows = _resolve_windows(
            df_raw,
            validation_days=int(args.validation_days),
            forward_days=int(args.forward_days),
            min_train_days=int(args.min_train_days),
        )
        dataset_audit = _build_dataset_audit(
            df_raw=df_raw, df_features=df_features, windows=windows, symbols=args.symbols, args=args)

        train_df = _slice_window(df_raw, windows.train_days)
        validation_df = _slice_window(df_raw, windows.validation_days)
        forward_df = _slice_window(df_raw, windows.forward_days)

        _validate_window_coverage(
            "train", dataset_audit["window_stats"]["train"], warmup_bars=search_cfg.warmup_bars)
        _validate_window_coverage(
            "validation", dataset_audit["window_stats"]["validation"], warmup_bars=search_cfg.warmup_bars)
        _validate_window_coverage(
            "forward", dataset_audit["window_stats"]["forward"], warmup_bars=search_cfg.warmup_bars)

        baseline_train = _evaluate_window(
            train_df,
            symbols=args.symbols,
            base_params=base_params,
            weights=baseline_weights,
            asset_cfgs=asset_cfgs,
            tf_sec=int(args.tf_sec),
            warmup_bars=search_cfg.warmup_bars,
            guardrails=guardrails,
        )
        baseline_validation = _evaluate_window(
            validation_df,
            symbols=args.symbols,
            base_params=base_params,
            weights=baseline_weights,
            asset_cfgs=asset_cfgs,
            tf_sec=int(args.tf_sec),
            warmup_bars=search_cfg.warmup_bars,
            guardrails=guardrails,
        )
        baseline_forward = _evaluate_window(
            forward_df,
            symbols=args.symbols,
            base_params=base_params,
            weights=baseline_weights,
            asset_cfgs=asset_cfgs,
            tf_sec=int(args.tf_sec),
            warmup_bars=search_cfg.warmup_bars,
            guardrails=guardrails,
        )

        rng = np.random.default_rng(int(args.seed))
        candidate_records: list[dict[str, Any]] = []
        seen_weights: set[tuple[float, float, float, float]] = set()
        for _ in range(int(search_cfg.trials)):
            weights = _normalize_weights(_sample_weights(rng))
            signature = _weight_signature(weights)
            if signature in seen_weights:
                continue
            seen_weights.add(signature)
            train_metrics = _evaluate_window(
                train_df,
                symbols=args.symbols,
                base_params=base_params,
                weights=weights,
                asset_cfgs=asset_cfgs,
                tf_sec=int(args.tf_sec),
                warmup_bars=search_cfg.warmup_bars,
                guardrails=guardrails,
            )
            candidate_records.append(
                {
                    "weights": weights,
                    "train": train_metrics,
                    "train_score": train_metrics.get("selection_score"),
                }
            )

        if not candidate_records:
            raise CalibrationError(
                "NO_CANDIDATE", "Search produced no candidate weight sets.")

        candidate_records.sort(key=lambda item: _score_or_floor(
            item.get("train_score")), reverse=True)
        top_candidates = candidate_records[:int(search_cfg.top_k)]
        for candidate in top_candidates:
            validation_metrics = _evaluate_window(
                validation_df,
                symbols=args.symbols,
                base_params=base_params,
                weights=candidate["weights"],
                asset_cfgs=asset_cfgs,
                tf_sec=int(args.tf_sec),
                warmup_bars=search_cfg.warmup_bars,
                guardrails=guardrails,
            )
            candidate["validation"] = validation_metrics
            candidate["validation_score"] = validation_metrics.get(
                "selection_score")

        selected_candidate = sorted(
            top_candidates, key=_candidate_sort_key, reverse=True)[0]
        selected_candidate["forward"] = _evaluate_window(
            forward_df,
            symbols=args.symbols,
            base_params=base_params,
            weights=selected_candidate["weights"],
            asset_cfgs=asset_cfgs,
            tf_sec=int(args.tf_sec),
            warmup_bars=search_cfg.warmup_bars,
            guardrails=guardrails,
        )

        baseline_metrics = {
            "train": baseline_train,
            "validation": baseline_validation,
            "forward": baseline_forward,
        }
        validation_artifact = _build_comparison_artifact(
            window_name="validation",
            baseline_metrics=baseline_validation,
            candidate_metrics=selected_candidate["validation"],
            guardrails=guardrails,
        )
        forward_artifact = _build_comparison_artifact(
            window_name="forward",
            baseline_metrics=baseline_forward,
            candidate_metrics=selected_candidate["forward"],
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
        if not verdict_reasons:
            verdict_reasons.append(
                "Candidate satisfied validation and forward guardrails against baseline.")

        selected_payload = {
            "weights": {key: float(selected_candidate["weights"][key]) for key in WEIGHT_KEYS},
            "train": selected_candidate["train"],
            "validation_score": selected_candidate.get("validation_score"),
            "validation": selected_candidate["validation"],
            "rank_within_top_k": 1 + next(index for index, item in enumerate(sorted(top_candidates, key=_candidate_sort_key, reverse=True)) if _weight_signature(item["weights"]) == _weight_signature(selected_candidate["weights"])),
        }

        candidate_payload = {
            "selection_basis": "best validation selection score among train-ranked candidates",
            "selected_candidate": selected_payload,
            "top_candidates": [
                {
                    "weights": {key: float(item["weights"][key]) for key in WEIGHT_KEYS},
                    "train_score": item.get("train_score"),
                    "validation_score": item.get("validation_score"),
                    "train_total_trades": int(item["train"]["total_trades"]),
                    "validation_total_trades": int((item.get("validation") or {}).get("total_trades", 0)),
                }
                for item in sorted(top_candidates, key=_candidate_sort_key, reverse=True)
            ],
            "search_space": {
                "type": "dirichlet_simplex_long_only",
                "weight_keys": list(WEIGHT_KEYS),
                "trials": int(search_cfg.trials),
                "top_k": int(search_cfg.top_k),
                "seed": int(args.seed),
            },
        }

        overlay = _overlay_from_weights(selected_candidate["weights"])
        manifest = {
            "calibrator": "calibrate_md_amr_weights.py",
            "calibration_class": "production",
            "status": "completed",
            "verdict": verdict,
            "verdict_reasons": verdict_reasons,
            "out_dir": str(out_dir),
            "runtime_truth_anchors": [
                "config/docs/md_amr_strategy_passport.md",
                "config/docs/CALIBRATION_STANDARD_V1.md",
                "tools/calibration/README.md",
                "config/aurora/strategies/md_amr.yaml",
            ],
            "non_goals": [
                "No canonical YAML mutation",
                "No multi-strategy calibration",
                "No automatic rollout or promotion",
                "No live strategy math changes",
                "No broad calibration framework rewrite",
            ],
            "input_contract": {
                "symbols": list(args.symbols),
                "start": args.start.isoformat(),
                "end_exclusive": args.end.isoformat(),
                "tf_sec": int(args.tf_sec),
                "search": {
                    "trials": int(search_cfg.trials),
                    "top_k": int(search_cfg.top_k),
                    "seed": int(args.seed),
                    "warmup_bars": int(search_cfg.warmup_bars),
                },
                "evaluation_windows": {
                    "train_days": list(windows.train_days),
                    "validation_days": list(windows.validation_days),
                    "forward_days": list(windows.forward_days),
                },
                "output_dir": str(out_dir),
            },
            "guardrails": {
                "min_trades": int(guardrails.min_trades),
                "max_drawdown_ratio": float(guardrails.max_drawdown_ratio),
                "min_activity_ratio": float(guardrails.min_activity_ratio),
                "max_activity_ratio": float(guardrails.max_activity_ratio),
                "validation_must_outperform_baseline": True,
                "forward_must_not_degrade_vs_baseline": True,
            },
            "dataset": dataset_audit,
            "canonical_yaml_writeback": False,
            "artifact_paths": {
                "run_manifest": "run_manifest.json",
                "baseline_metrics": "baseline_metrics.json",
                "candidate_metrics": "candidate_metrics.json",
                "validation_metrics": "validation_metrics.json",
                "forward_metrics": "forward_metrics.json",
                "overlay": "candidate_md_amr_strategy_overlay.yaml",
                "report": "report.md",
            },
        }

        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "run_manifest.json", manifest)
        _write_json(out_dir / "baseline_metrics.json", baseline_metrics)
        _write_json(out_dir / "candidate_metrics.json", candidate_payload)
        _write_json(out_dir / "validation_metrics.json", validation_artifact)
        _write_json(out_dir / "forward_metrics.json", forward_artifact)
        _write_yaml(out_dir / "candidate_md_amr_strategy_overlay.yaml", overlay)
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
        (out_dir / "report.md").write_text(report, encoding="utf-8")

        print(f"verdict={verdict} out_dir={out_dir}")
        print(
            f"baseline_weights={json.dumps(baseline_weights, sort_keys=True)}")
        print(
            f"candidate_weights={json.dumps(selected_candidate['weights'], sort_keys=True)}")
        print(
            f"validation_score_delta={_fmt_score(validation_artifact['delta'].get('selection_score'))}")
        print(
            f"forward_score_delta={_fmt_score(forward_artifact['delta'].get('selection_score'))}")

        # Per-regime breakdown (additive, after main calibration output)
        if bool(getattr(args, "per_regime", False)):
            _run_per_regime_analysis(
                df_raw,
                symbols=args.symbols,
                base_params=base_params,
                weights=baseline_weights,
                asset_cfgs=asset_cfgs,
                tf_sec=int(args.tf_sec),
                warmup_bars=search_cfg.warmup_bars,
                guardrails=guardrails,
                out_dir=out_dir,
            )

        return 0
    except CalibrationError as error:
        _write_failure_bundle(args, out_dir, error)
        print(f"NO_GO_CANDIDATE {error.code}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
