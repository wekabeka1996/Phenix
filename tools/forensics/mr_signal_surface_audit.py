#!/usr/bin/env python3
from __future__ import annotations
from apps.reference.domains.feature_engineering.bar_resampler import Bar
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRStrategyConfig,
    MeanReversion1mStrategy,
)
from apps.reference.domains.feature_engineering.regime_mapping import (
    FlatRegime,
    FlatRegimeThresholds,
    map_to_flat_regime,
)
from tools.objective_calibration.extract_recorder import load_recorder_rows

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


RECENT_MANIFEST = REPO_ROOT / "reports" / \
    "mean_reversion_real_run_validation" / "run_manifest.json"
EARLY_MANIFEST = REPO_ROOT / "reports" / \
    "mean_reversion_real_run_validation_early" / "run_manifest.json"


@dataclass(frozen=True)
class RunWindow:
    label: str
    start: date
    end_exclusive: date
    tf_sec: int
    train_days: list[str]
    validation_days: list[str]
    forward_days: list[str]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_run_window(path: Path, *, label: str) -> RunWindow:
    payload = _read_json(path)
    return RunWindow(
        label=label,
        start=date.fromisoformat(payload["input_contract"]["start"]),
        end_exclusive=date.fromisoformat(
            payload["input_contract"]["end_exclusive"]),
        tf_sec=int(payload["input_contract"]["tf_sec"]),
        train_days=list(payload["window_days"]["train"]),
        validation_days=list(payload["window_days"]["validation"]),
        forward_days=list(payload["window_days"]["forward"]),
    )


def _window_payload(window: RunWindow) -> dict[str, Any]:
    return {
        "label": window.label,
        "start": window.start.isoformat(),
        "end_exclusive": window.end_exclusive.isoformat(),
        "tf_sec": int(window.tf_sec),
        "train_days": list(window.train_days),
        "validation_days": list(window.validation_days),
        "forward_days": list(window.forward_days),
    }


def _normalize_dataset(df: pd.DataFrame, *, tf_sec: int) -> pd.DataFrame:
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    out["timestamp"] = out["timestamp"].astype("int64")
    out["regime"] = out.get("regime", "").fillna("").astype(str)
    out["tf_sec"] = pd.to_numeric(
        out.get("tf_sec", tf_sec), errors="coerce").fillna(int(tf_sec)).astype(int)
    out = out[out["tf_sec"] == int(tf_sec)].copy()
    out = out.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    out = out.sort_values(["symbol", "timestamp"],
                          kind="mergesort").reset_index(drop=True)
    out["day_utc"] = pd.to_datetime(
        out["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    out["prev_ts"] = out.groupby("symbol")["timestamp"].shift(1)
    out["gap_ms"] = out["timestamp"] - out["prev_ts"]
    out["gap_reset"] = out["gap_ms"] > (int(tf_sec) * 2 * 1000)
    out["segment_id"] = out.groupby("symbol")["gap_reset"].cumsum().astype(int)
    return out.drop(columns=["prev_ts", "gap_ms"])


def _load_mean_reversion_yaml() -> dict[str, Any]:
    raw = yaml.safe_load((REPO_ROOT / "config" / "aurora" / "strategies" /
                         "mean_reversion.yaml").read_text(encoding="utf-8"))
    return dict(raw["mean_reversion"])


def _effective_strategy_payload(root_cfg: dict[str, Any], symbol: str) -> dict[str, Any]:
    payload = dict(root_cfg["strategy"])
    asset_cfg = dict(root_cfg["assets"][symbol])
    asset_strategy = dict(asset_cfg.get("strategy") or {})
    payload.update(
        {key: value for key, value in asset_strategy.items() if value is not None})
    payload["allowed_regimes"] = list(asset_cfg.get(
        "allowed_regimes") or root_cfg.get("allowed_regimes") or [])
    return payload


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _build_strategy(root_cfg: dict[str, Any], symbol: str) -> MeanReversion1mStrategy:
    cfg = _effective_strategy_payload(root_cfg, symbol)
    typed = MRStrategyConfig(
        bb_window=int(cfg["bb_window"]),
        bb_num_std=float(cfg["bb_num_std"]),
        atr_window=int(cfg.get("atr_window", 14)),
        rsi_window=int(cfg.get("rsi_window", 14)),
        min_bars=int(cfg.get("min_bars", 25)),
        min_bb_width=_decimal(cfg["min_bb_width"]),
        max_bb_width=_decimal(cfg["max_bb_width"]),
        entry_threshold=_decimal(cfg["entry_threshold"]),
        rsi_oversold=_decimal(cfg.get("rsi_oversold", 30)),
        rsi_overbought=_decimal(cfg.get("rsi_overbought", 70)),
        sl_atr_mult=_decimal(cfg["sl_atr_mult"]),
        tp_to_mid=bool(cfg.get("tp_to_mid", True)),
        cooldown_sec=int(cfg["cooldown_sec"]),
        sl_buffer_pct=_decimal(cfg.get("sl_buffer_pct", 0)),
        tp_buffer_pct=_decimal(cfg.get("tp_buffer_pct", 0)),
        allowed_regimes=list(cfg.get("allowed_regimes") or []),
        flat_low_short_min_bb_width=(
            _decimal(cfg["flat_low_short_min_bb_width"])
            if cfg.get("flat_low_short_min_bb_width") is not None
            else None
        ),
        confidence_base=_decimal(cfg.get("confidence_base", 0.5)),
        confidence_bb_slope=_decimal(cfg.get("confidence_bb_slope", 2.0)),
        confidence_rsi_bonus=_decimal(cfg.get("confidence_rsi_bonus", 0.2)),
    )
    thresholds = FlatRegimeThresholds(
        high_vol_pct=_decimal(root_cfg["regime_thresholds"]["high_vol_pct"]),
        low_vol_pct=_decimal(root_cfg["regime_thresholds"]["low_vol_pct"]),
    )
    regime_sizing = dict(root_cfg.get("regime_sizing") or {})
    return MeanReversion1mStrategy(
        config=typed,
        timeframe_sec=int(root_cfg["timeframe_sec"]),
        regime_sizing=regime_sizing,
        regime_thresholds=thresholds,
    )


def _bar_from_row(row: pd.Series, tf_sec: int) -> Bar:
    return Bar(
        symbol=str(row["symbol"]).upper(),
        timeframe_sec=int(tf_sec),
        open=_decimal(row["open"]),
        high=_decimal(row["high"]),
        low=_decimal(row["low"]),
        close=_decimal(row["close"]),
        volume=_decimal(row.get("volume", 0)),
        start_ts_ms=int(row["timestamp"] - (int(tf_sec) * 1000)),
        end_ts_ms=int(row["timestamp"]),
        trade_count=int(float(row.get("trade_count", 0) or 0)),
    )


def _reason_bucket(raw: str) -> str:
    if raw.startswith("neutral:"):
        raw = raw[len("neutral:"):]
    if raw.startswith("regime_not_flat:"):
        return "regime_not_flat"
    if raw.startswith("regime_not_allowed:"):
        return "regime_not_allowed"
    if raw.startswith("bb_width_too_narrow:"):
        return "bb_width_too_narrow"
    if raw.startswith("bb_width_too_wide:"):
        return "bb_width_too_wide"
    if raw.startswith("flat_low_short_bb_width_too_narrow:"):
        return "flat_low_short_bb_width_too_narrow"
    if raw.startswith("squeeze_expansion_veto:"):
        return "squeeze_expansion_veto"
    if raw.startswith("momentum_separation_veto:"):
        return "momentum_separation_veto"
    if raw.startswith("no_signal:"):
        return "no_signal_threshold_not_crossed"
    return raw


def _split_for_day(day_utc: str, window: RunWindow) -> str | None:
    if day_utc in window.train_days:
        return "train"
    if day_utc in window.validation_days:
        return "validation"
    if day_utc in window.forward_days:
        return "forward"
    return None


def _serializable_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _run_audit_for_window(
    window: RunWindow,
    *,
    symbol: str,
    root_cfg: dict[str, Any],
    recorder_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    loaded = load_recorder_rows(
        recorder_dir,
        start=window.start,
        end=window.end_exclusive,
        symbols=[symbol],
        tf_sec=window.tf_sec,
    )
    df = _normalize_dataset(loaded, tf_sec=window.tf_sec)
    df = df[df["symbol"] == symbol].copy().reset_index(drop=True)

    records: list[dict[str, Any]] = []
    grouped = df.groupby("segment_id", sort=False)
    for segment_id, segment in grouped:
        strategy = _build_strategy(root_cfg, symbol)
        ordered = segment.sort_values(
            "timestamp", kind="mergesort").reset_index(drop=True)
        for _, row in ordered.iterrows():
            bar = _bar_from_row(row, window.tf_sec)
            strategy.set_regime(symbol, str(row.get("regime") or ""))
            result = strategy.on_bar(symbol, bar, int(row["timestamp"]))
            state = strategy.get_state(symbol)
            current_regime = strategy.get_regime(symbol)
            atr_pct = strategy._atr_pct.get(symbol)
            flat_regime = map_to_flat_regime(
                current_regime, atr_pct, strategy._flat_regime_thresholds)
            reason_raw = str(getattr(result, "why", "") or "")
            is_signal = bool(result is not None and result.is_signal)
            records.append(
                {
                    "run_label": window.label,
                    "split": _split_for_day(str(row["day_utc"]), window),
                    "segment_id": int(segment_id),
                    "timestamp": int(row["timestamp"]),
                    "day_utc": str(row["day_utc"]),
                    "session_day": str(row.get("session_day") or ""),
                    "regime": current_regime,
                    "mapped_flat_regime": flat_regime.name if flat_regime is not None else None,
                    "is_signal": is_signal,
                    "signal_type": getattr(result.signal_type, "name", None) if result is not None else None,
                    "reason_raw": reason_raw,
                    "reason_bucket": "signal" if is_signal else _reason_bucket(reason_raw),
                    "bb_width": _serializable_number(getattr(state.bb, "width", None)),
                    "pct_b": _serializable_number(getattr(state.bb, "pct_b", None)),
                    "atr": _serializable_number(state.atr),
                    "atr_pct": _serializable_number(atr_pct),
                    "rsi": _serializable_number(state.rsi),
                    "bars_seen": int(len(state.bars)),
                    "close": float(row["close"]),
                }
            )

    audit_df = pd.DataFrame.from_records(records)
    return audit_df, {
        "rows": int(len(df)),
        "unique_days": sorted(df["day_utc"].astype(str).unique().tolist()),
        "segments": int(df["segment_id"].nunique()) if not df.empty else 0,
    }


def _reason_summary(df: pd.DataFrame) -> dict[str, Any]:
    total = int(len(df))
    counts = Counter(df["reason_bucket"].astype(str).tolist())
    details = {
        key: {
            "count": int(value),
            "ratio": (float(value) / total) if total else 0.0,
        }
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }
    return {
        "total_bars": total,
        "reasons": details,
    }


def _stage_funnel(summary: dict[str, Any]) -> dict[str, Any]:
    total = int(summary["total_bars"])
    reason_counts = {name: int(payload["count"])
                     for name, payload in summary["reasons"].items()}
    insufficient = reason_counts.get("insufficient_bars", 0)
    cooldown = reason_counts.get("cooldown", 0)
    regime_not_flat = reason_counts.get("regime_not_flat", 0)
    regime_not_allowed = reason_counts.get("regime_not_allowed", 0)
    no_bb = reason_counts.get("no_bb", 0)
    narrow = reason_counts.get("bb_width_too_narrow", 0) + \
        reason_counts.get("flat_low_short_bb_width_too_narrow", 0)
    wide = reason_counts.get("bb_width_too_wide", 0)
    squeeze = reason_counts.get("squeeze_expansion_veto", 0)
    momentum = reason_counts.get("momentum_separation_veto", 0)
    no_signal = reason_counts.get("no_signal_threshold_not_crossed", 0)
    signals = reason_counts.get("signal", 0)
    return {
        "total": total,
        "after_min_bars": total - insufficient,
        "after_cooldown": total - insufficient - cooldown,
        "after_regime_mapping": total - insufficient - cooldown - regime_not_flat,
        "after_allowlist": total - insufficient - cooldown - regime_not_flat - regime_not_allowed,
        "after_bb_presence": total - insufficient - cooldown - regime_not_flat - regime_not_allowed - no_bb,
        "after_width_filters": total - insufficient - cooldown - regime_not_flat - regime_not_allowed - no_bb - narrow - wide,
        "after_pattern_vetoes": total - insufficient - cooldown - regime_not_flat - regime_not_allowed - no_bb - narrow - wide - squeeze - momentum,
        "threshold_cross_bars": signals,
        "threshold_neutral_bars": no_signal,
    }


def _quantiles(series: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {"min": None, "p25": None, "p50": None, "p75": None, "max": None}
    return {
        "min": float(clean.min()),
        "p25": float(clean.quantile(0.25)),
        "p50": float(clean.quantile(0.50)),
        "p75": float(clean.quantile(0.75)),
        "max": float(clean.max()),
    }


def _metric_summary(df: pd.DataFrame, *, min_bb_width: float, entry_threshold: float) -> dict[str, Any]:
    mature = df[df["reason_bucket"] != "insufficient_bars"].copy()
    post_cooldown = mature[mature["reason_bucket"] != "cooldown"].copy()
    flat_allowed = post_cooldown[
        (~post_cooldown["reason_bucket"].isin(
            ["regime_not_flat", "regime_not_allowed"]))
    ].copy()
    with_bb = flat_allowed[flat_allowed["bb_width"].notna()].copy()
    width_pass = with_bb[
        (with_bb["bb_width"] >= float(min_bb_width)) & (
            with_bb["bb_width"] <= 0.15)
    ].copy()
    threshold_cross = width_pass[
        (width_pass["pct_b"] < float(entry_threshold)) | (
            width_pass["pct_b"] > (1.0 - float(entry_threshold)))
    ].copy()
    between_thresholds = width_pass[
        (width_pass["pct_b"] >= float(entry_threshold)) & (
            width_pass["pct_b"] <= (1.0 - float(entry_threshold)))
    ].copy()
    potential_if_global_width = with_bb[
        (with_bb["bb_width"] >= 0.001) & (
            with_bb["bb_width"] < float(min_bb_width))
    ].copy()
    potential_if_global_width_threshold_cross = potential_if_global_width[
        (potential_if_global_width["pct_b"] < float(entry_threshold))
        | (potential_if_global_width["pct_b"] > (1.0 - float(entry_threshold)))
    ].copy()
    return {
        "mature_bars": int(len(mature)),
        "flat_allowed_bars": int(len(flat_allowed)),
        "bars_with_bb": int(len(with_bb)),
        "width_pass_bars": int(len(width_pass)),
        "threshold_cross_bars": int(len(threshold_cross)),
        "between_thresholds_bars": int(len(between_thresholds)),
        "bb_width_quantiles_flat_allowed": _quantiles(with_bb["bb_width"]),
        "pct_b_quantiles_width_pass": _quantiles(width_pass["pct_b"]),
        "potential_if_global_width": {
            "bars": int(len(potential_if_global_width)),
            "threshold_cross_bars": int(len(potential_if_global_width_threshold_cross)),
        },
    }


def _regime_summary(df: pd.DataFrame) -> dict[str, Any]:
    regime_counts = Counter(df["regime"].astype(str).tolist())
    mapped_counts = Counter(
        df["mapped_flat_regime"].fillna("NONE").astype(str).tolist())
    return {
        "input_regime_counts": dict(sorted(regime_counts.items(), key=lambda item: (-item[1], item[0]))),
        "mapped_flat_regime_counts": dict(sorted(mapped_counts.items(), key=lambda item: (-item[1], item[0]))),
    }


def build_report(*, recorder_dir: Path | None = None) -> dict[str, Any]:
    root_cfg = _load_mean_reversion_yaml()
    symbol = "DOGEUSDT"
    effective_cfg = _effective_strategy_payload(root_cfg, symbol)
    resolved_recorder_dir = recorder_dir or (REPO_ROOT / "data" / "recorder")
    windows = [
        _load_run_window(EARLY_MANIFEST, label="early_clean"),
        _load_run_window(RECENT_MANIFEST, label="recent_clean"),
    ]

    all_frames: list[pd.DataFrame] = []
    runs: dict[str, Any] = {}
    for window in windows:
        audit_df, dataset_stats = _run_audit_for_window(
            window,
            symbol=symbol,
            root_cfg=root_cfg,
            recorder_dir=resolved_recorder_dir,
        )
        all_frames.append(audit_df)
        split_payload: dict[str, Any] = {}
        for split_name in ("train", "validation", "forward"):
            split_df = audit_df[audit_df["split"] == split_name].copy()
            split_summary = _reason_summary(split_df)
            split_payload[split_name] = {
                **split_summary,
                "stage_funnel": _stage_funnel(split_summary),
                "regimes": _regime_summary(split_df),
                "metrics": _metric_summary(
                    split_df,
                    min_bb_width=float(effective_cfg["min_bb_width"]),
                    entry_threshold=float(effective_cfg["entry_threshold"]),
                ),
            }
        run_summary = _reason_summary(audit_df)
        runs[window.label] = {
            "window": _window_payload(window),
            "dataset_stats": dataset_stats,
            "all": {
                **run_summary,
                "stage_funnel": _stage_funnel(run_summary),
                "regimes": _regime_summary(audit_df),
                "metrics": _metric_summary(
                    audit_df,
                    min_bb_width=float(effective_cfg["min_bb_width"]),
                    entry_threshold=float(effective_cfg["entry_threshold"]),
                ),
            },
            "splits": split_payload,
        }

    combined = pd.concat(all_frames, ignore_index=True)
    combined_summary = _reason_summary(combined)
    combined_post_warmup = _reason_summary(
        combined[combined["reason_bucket"] != "insufficient_bars"].copy())
    dominant_reason = None
    if combined_post_warmup["reasons"]:
        dominant_reason = next(iter(combined_post_warmup["reasons"].keys()))

    return {
        "runtime_surface": {
            "symbol": symbol,
            "assigned_in_registry": True,
            "timeframe_sec": int(root_cfg["timeframe_sec"]),
            "allowed_regimes": list(effective_cfg["allowed_regimes"]),
            "effective_strategy": {
                "bb_window": int(effective_cfg["bb_window"]),
                "bb_num_std": float(effective_cfg["bb_num_std"]),
                "entry_threshold": float(effective_cfg["entry_threshold"]),
                "sl_atr_mult": float(effective_cfg["sl_atr_mult"]),
                "cooldown_sec": int(effective_cfg["cooldown_sec"]),
                "min_bb_width": float(effective_cfg["min_bb_width"]),
                "max_bb_width": float(effective_cfg["max_bb_width"]),
                "tp_to_mid": bool(effective_cfg.get("tp_to_mid", True)),
                "min_bars": int(effective_cfg.get("min_bars", root_cfg["strategy"]["min_bars"])),
                "atr_window": int(effective_cfg.get("atr_window", root_cfg["strategy"]["atr_window"])),
                "rsi_window": int(effective_cfg.get("rsi_window", root_cfg["strategy"]["rsi_window"])),
            },
            "global_overlays": {
                "microstructure_veto_enabled": bool((root_cfg.get("microstructure_veto") or {}).get("enabled", False)),
                "directional_bias_enabled": bool((root_cfg.get("directional_bias") or {}).get("enabled", False)),
                "safety_gates_enabled": bool((root_cfg.get("safety_gates") or {}).get("enabled", False)),
                "objective_enabled": bool((root_cfg.get("objective") or {}).get("enabled", False)),
                "liquidity_gate_present": bool(root_cfg.get("liquidity_gate")),
            },
        },
        "runs": runs,
        "combined": {
            "all": {
                **combined_summary,
                "stage_funnel": _stage_funnel(combined_summary),
                "regimes": _regime_summary(combined),
                "metrics": _metric_summary(
                    combined,
                    min_bb_width=float(effective_cfg["min_bb_width"]),
                    entry_threshold=float(effective_cfg["entry_threshold"]),
                ),
            },
            "post_warmup": combined_post_warmup,
            "dominant_reason_post_warmup": dominant_reason,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Mean Reversion signal surface on live-relevant DOGE recorder windows.")
    parser.add_argument(
        "--recorder-dir",
        default=str(REPO_ROOT / "data" / "recorder"),
    )
    parser.add_argument(
        "--output-json",
        default=str(REPO_ROOT / "reports" / "mean_reversion_signal_surface_audit_v1" /
                    "mr_no_signal_reason_distribution.json"),
    )
    args = parser.parse_args()

    payload = build_report(recorder_dir=Path(args.recorder_dir))
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(
        payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
