#!/usr/bin/env python3
"""Phase 2B bounded aggression-grid search for md_amr.

Analysis-only orchestration layer over the Phase 2A-updated md_amr calibrator.
This tool never mutates canonical YAML and only emits overlay-only candidate
artifacts under artifacts/strategy_calibration/phase2b/.
"""

from __future__ import annotations
from tools.simulation.md_amr_data_adapter import compute_md_amr_features, load_recorder_900
from calibrators.strategies import calibrate_md_amr_weights as calibrator

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TARGET_SYMBOLS = (
    ("XRPUSDT", calibrator.LIVE_ASSIGNED, "xrp"),
    ("ETHUSDT", calibrator.NOT_LIVE_ASSIGNED, "eth"),
    ("SOLUSDT", calibrator.NOT_LIVE_ASSIGNED, "sol"),
)


FEATURE_COLUMNS = (
    "avg_open_12",
    "avg_high_12",
    "avg_low_12",
    "avg_close_12",
    "true_range",
    "atr_current",
    "atr_ma_n",
    "atr_std_n",
    "dir_d1",
    "dir_h1",
    "dir_m30",
    "dir_m15",
)


@dataclass(frozen=True)
class SymbolTarget:
    symbol: str
    expected_live_status: str
    artifact_slug: str


@dataclass(frozen=True)
class GridFamily:
    name: str
    title: str
    mutate_dimensions: tuple[str, ...]
    trials: int
    top_k: int
    freeze_weights: bool


@dataclass(frozen=True)
class SharedConfig:
    recorder_dir: Path
    md_amr_yaml: Path
    strategies_yaml: Path
    tf_sec: int
    start: date
    end: date
    validation_days: int
    forward_days: int
    min_train_days: int
    min_trades: int
    max_dd_limit: float
    min_activity_ratio: float
    max_activity_ratio: float
    warmup_bars: int
    artifacts_root: Path
    reports_root: Path


@dataclass(frozen=True)
class SymbolContext:
    target: SymbolTarget
    shared: SharedConfig
    base_params: dict[str, Any]
    baseline_weights: dict[str, float]
    asset_cfgs: dict[str, dict[str, Any]]
    symbol_scope: list[dict[str, Any]]
    df_raw: pd.DataFrame
    df_features: pd.DataFrame
    windows: calibrator.WindowSpec
    guardrails: calibrator.GuardrailCfg
    recorder_files: tuple[Path, ...]


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _target_specs() -> list[SymbolTarget]:
    return [SymbolTarget(symbol=item[0], expected_live_status=item[1], artifact_slug=item[2]) for item in TARGET_SYMBOLS]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 2B bounded aggression-grid search for md_amr. "
            "Runs data-quality gating, baseline reconfirmation, and multiple overlay-only grid families."
        )
    )
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument(
        "--md-amr-yaml", default="config/aurora/strategies/md_amr.yaml")
    parser.add_argument("--strategies-yaml",
                        default="config/aurora/strategies.yaml")
    parser.add_argument("--tf-sec", type=int, default=900)
    parser.add_argument("--start", type=_parse_date, default=None)
    parser.add_argument("--end", type=_parse_date, default=None,
                        help="End date exclusive. Defaults to the latest common recorder day + 1.")
    parser.add_argument("--analysis-days", type=int, default=14,
                        help="If --start is omitted, use the trailing common recorder window of this many days.")
    parser.add_argument("--validation-days", type=int, default=2)
    parser.add_argument("--forward-days", type=int, default=2)
    parser.add_argument("--min-train-days", type=int, default=6)
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--max-dd-limit", type=float, default=0.35)
    parser.add_argument("--min-activity-ratio", type=float, default=0.5)
    parser.add_argument("--max-activity-ratio", type=float, default=2.5)
    parser.add_argument("--warmup-bars", type=int, default=96)
    parser.add_argument("--threshold-confidence-trials", type=int, default=24)
    parser.add_argument("--window-lifecycle-trials", type=int, default=24)
    parser.add_argument("--regime-allowlist-trials", type=int, default=12)
    parser.add_argument("--weight-threshold-trials", type=int, default=24)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--artifacts-root",
                        default="artifacts/strategy_calibration/phase2b")
    parser.add_argument("--reports-root", default="reports")
    return parser


def _grid_families(args: argparse.Namespace) -> list[GridFamily]:
    return [
        GridFamily(
            name="threshold_confidence_grid",
            title="Threshold / Confidence Grid",
            mutate_dimensions=(
                "threshold_z",
                "thr_base",
                "thr_floor",
                "hysteresis_mult",
                "volatility_dampening_factor",
                "alpha",
                "conf_min",
            ),
            trials=max(1, int(args.threshold_confidence_trials)),
            top_k=max(1, int(args.top_k)),
            freeze_weights=True,
        ),
        GridFamily(
            name="window_lifecycle_grid",
            title="Window / Lifecycle Grid",
            mutate_dimensions=(
                "channel_window_bars",
                "atr_window",
                "atr_stats_window",
                "max_hold_bars",
                "target_approach_pct",
            ),
            trials=max(1, int(args.window_lifecycle_trials)),
            top_k=max(1, int(args.top_k)),
            freeze_weights=True,
        ),
        GridFamily(
            name="regime_allowlist_grid",
            title="Regime Allowlist Grid",
            mutate_dimensions=("allowed_regimes",),
            trials=max(1, int(args.regime_allowlist_trials)),
            top_k=max(1, int(args.top_k)),
            freeze_weights=True,
        ),
        GridFamily(
            name="weight_threshold_combined_grid",
            title="Weight + Threshold Combined Grid",
            mutate_dimensions=("threshold_z", "thr_base",
                               "thr_floor", "conf_min"),
            trials=max(1, int(args.weight_threshold_trials)),
            top_k=max(1, int(args.top_k)),
            freeze_weights=False,
        ),
    ]


def _available_days_for_symbol(recorder_dir: Path, symbol: str, tf_sec: int) -> list[date]:
    out: list[date] = []
    if not recorder_dir.exists():
        return out
    for day_dir in sorted((item for item in recorder_dir.iterdir() if item.is_dir()), key=lambda item: item.name):
        try:
            day_value = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        if (day_dir / f"{symbol}_{int(tf_sec)}.csv").exists():
            out.append(day_value)
    return out


def _resolve_common_window(
    *,
    recorder_dir: Path,
    targets: Sequence[SymbolTarget],
    tf_sec: int,
    start: date | None,
    end: date | None,
    analysis_days: int,
    validation_days: int,
    forward_days: int,
    min_train_days: int,
) -> tuple[date, date, list[str]]:
    availability: list[set[date]] = []
    for target in targets:
        days = set(_available_days_for_symbol(
            recorder_dir, target.symbol, tf_sec))
        if not days:
            raise calibrator.CalibrationError(
                "INSUFFICIENT_DATA",
                f"No recorder files found for {target.symbol} tf_sec={tf_sec}.",
            )
        availability.append(days)
    common_days = sorted(set.intersection(*availability))
    if not common_days:
        raise calibrator.CalibrationError(
            "INSUFFICIENT_DATA",
            "No common recorder days exist across the requested Phase 2B symbol set.",
        )

    resolved_end = end or (common_days[-1] + timedelta(days=1))
    filtered = [item for item in common_days if item <
                resolved_end and (start is None or item >= start)]
    if not filtered:
        raise calibrator.CalibrationError(
            "INSUFFICIENT_DATA",
            "No common recorder days remain inside the requested Phase 2B date window.",
        )
    resolved_start = start or filtered[max(
        0, len(filtered) - max(1, int(analysis_days)))]
    selected = [item for item in filtered if item >= resolved_start]
    required_days = int(validation_days) + \
        int(forward_days) + int(min_train_days)
    if len(selected) < required_days:
        raise calibrator.CalibrationError(
            "INSUFFICIENT_DATA",
            (
                "Not enough common recorder days for the shared Phase 2B split policy. "
                f"Need at least {required_days}, found {len(selected)}."
            ),
            details={
                "required_days": required_days,
                "selected_days": [item.isoformat() for item in selected],
            },
        )
    return resolved_start, resolved_end, [item.isoformat() for item in selected]


def _count_malformed_csv_rows(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"data_rows": 0, "malformed_rows": 0}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            return {"data_rows": 0, "malformed_rows": 0}
        expected_len = len(header)
        malformed_rows = 0
        data_rows = 0
        for row in reader:
            if not row or all(not str(cell).strip() for cell in row):
                continue
            data_rows += 1
            if len(row) != expected_len:
                malformed_rows += 1
    return {"data_rows": int(data_rows), "malformed_rows": int(malformed_rows)}


def _count_valid_feature_rows(df_features: pd.DataFrame) -> int:
    if df_features.empty:
        return 0
    available = [
        column for column in FEATURE_COLUMNS if column in df_features.columns]
    if not available:
        return 0
    mask = pd.Series(True, index=df_features.index)
    for column in available:
        numeric = pd.to_numeric(df_features[column], errors="coerce")
        mask = mask & numeric.notna()
    return int(mask.sum())


def _format_ratio(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100.0:.2f}%"


def _format_float(value: Any, *, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                    ensure_ascii=False), encoding="utf-8")


def _markdown_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _metrics_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_trades": int(metrics.get("total_trades", 0)),
        "net_return_ratio": float(metrics.get("net_return_ratio", 0.0)),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown_ratio": float(metrics.get("max_drawdown_ratio", 0.0)),
        "avg_holding_bars": float(metrics.get("avg_holding_bars", 0.0)),
        "selection_score": metrics.get("selection_score"),
    }


def _window_stats_with_status(
    *,
    df_raw: pd.DataFrame,
    windows: calibrator.WindowSpec,
    symbol: str,
    warmup_bars: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for window_name, days in (
        ("train", windows.train_days),
        ("validation", windows.validation_days),
        ("forward", windows.forward_days),
    ):
        window_df = calibrator._slice_window(df_raw, list(days))
        stats = calibrator._window_stats(window_df, symbols=[symbol])
        status = {"ok": True, "message": "ok"}
        try:
            calibrator._validate_window_coverage(
                window_name, stats, warmup_bars=warmup_bars)
        except calibrator.CalibrationError as exc:
            status = {"ok": False, "message": str(
                exc), "details": dict(exc.details)}
        out[window_name] = {"days": list(
            days), "stats": stats, "coverage": status}
    return out


def _prepare_symbol_context(
    *,
    target: SymbolTarget,
    shared: SharedConfig,
    md_amr_cfg: dict[str, Any],
    strategies_cfg: dict[str, Any],
) -> tuple[dict[str, Any], SymbolContext | None]:
    day_cursor = shared.start
    requested_days: list[date] = []
    while day_cursor < shared.end:
        requested_days.append(day_cursor)
        day_cursor = day_cursor + timedelta(days=1)
    recorder_files = tuple(
        path
        for path in (
            shared.recorder_dir / day.isoformat() /
            f"{target.symbol}_{int(shared.tf_sec)}.csv"
            for day in requested_days
        )
        if path.exists()
    )
    file_quality = [_count_malformed_csv_rows(path) for path in recorder_files]
    malformed_rows = int(sum(item["malformed_rows"] for item in file_quality))
    parse_fallback_files = int(
        sum(1 for item in file_quality if item["malformed_rows"] > 0))

    base_params = calibrator._extract_base_params(md_amr_cfg)
    baseline_weights = calibrator._normalize_weights(
        calibrator._extract_baseline_weights(md_amr_cfg))
    asset_cfgs = calibrator._extract_asset_configs(md_amr_cfg, [target.symbol])
    symbol_scope = calibrator._resolve_symbol_scope(
        symbols=[target.symbol],
        tf_sec=int(shared.tf_sec),
        strategies_cfg=strategies_cfg,
        strategies_yaml=shared.strategies_yaml,
        md_amr_yaml=shared.md_amr_yaml,
    )
    actual_live_status = str((symbol_scope[0] or {}).get(
        "live_status") or "") if symbol_scope else ""

    blockers: list[str] = []
    warnings: list[str] = []

    if actual_live_status != target.expected_live_status:
        blockers.append(
            f"live_status_mismatch expected={target.expected_live_status} actual={actual_live_status or 'UNKNOWN'}"
        )

    df_raw = load_recorder_900(
        shared.recorder_dir,
        symbols=[target.symbol],
        start=shared.start,
        end=shared.end,
        basis_tf_sec=int(shared.tf_sec),
    )
    if df_raw.empty:
        blockers.append("no_recorder_rows")
        summary = {
            "symbol": target.symbol,
            "artifact_slug": target.artifact_slug,
            "expected_live_status": target.expected_live_status,
            "actual_live_status": actual_live_status or "UNKNOWN",
            "rows_available": 0,
            "valid_feature_rows": 0,
            "malformed_csv_rows": malformed_rows,
            "parse_fallback_file_count": parse_fallback_files,
            "gap_count": 0,
            "max_gap_sec": 0.0,
            "unique_days": [],
            "contiguous_window_status": {},
            "regime_coverage": {},
            "warmup_sufficient": False,
            "forward_window_sufficient": False,
            "eligible_for_grid_search": False,
            "status": "GRID_BLOCKED",
            "blockers": blockers,
            "warnings": warnings,
            "recorder_files": [str(path) for path in recorder_files],
        }
        return summary, None

    df_raw = calibrator._annotate_day_utc(df_raw)
    df_raw = df_raw.copy()
    df_raw["regime"] = calibrator._compute_regime_labels(df_raw)
    df_features = calibrator._annotate_day_utc(compute_md_amr_features(df_raw))
    valid_feature_rows = _count_valid_feature_rows(df_features)

    if malformed_rows > 0:
        warnings.append(f"malformed_csv_rows={malformed_rows}")

    gap_count = int(pd.Series(df_raw.get("gap_reset", pd.Series(
        dtype=bool))).fillna(False).astype(bool).sum())
    gap_diffs = pd.to_numeric(
        df_raw.groupby("symbol")["timestamp"].diff(),
        errors="coerce",
    )
    significant_gaps = gap_diffs[gap_diffs > (int(shared.tf_sec) * 2 * 1000)]
    max_gap_sec = float(significant_gaps.max() /
                        1000.0) if not significant_gaps.empty else 0.0
    if gap_count > 0:
        warnings.append(f"gap_count={gap_count}")

    try:
        windows = calibrator._resolve_windows(
            df_raw,
            validation_days=int(shared.validation_days),
            forward_days=int(shared.forward_days),
            min_train_days=int(shared.min_train_days),
        )
        window_status = _window_stats_with_status(
            df_raw=df_raw,
            windows=windows,
            symbol=target.symbol,
            warmup_bars=int(shared.warmup_bars),
        )
    except calibrator.CalibrationError as exc:
        blockers.append(str(exc))
        windows = None
        window_status = {}

    if windows is not None:
        for payload in window_status.values():
            if not bool((payload.get("coverage") or {}).get("ok", False)):
                blockers.append(str((payload.get("coverage") or {}).get(
                    "message") or "window_coverage_failed"))

    if valid_feature_rows < int(shared.warmup_bars) + 1:
        blockers.append(
            f"valid_feature_rows_below_warmup required>={int(shared.warmup_bars) + 1} actual={valid_feature_rows}"
        )

    regime_coverage = {
        str(key): int(value)
        for key, value in df_raw["regime"].value_counts(dropna=False).to_dict().items()
        if str(key)
    }

    guardrails = calibrator.GuardrailCfg(
        min_trades=max(1, int(shared.min_trades)),
        max_drawdown_ratio=float(shared.max_dd_limit),
        min_train_days=max(1, int(shared.min_train_days)),
        min_activity_ratio=float(shared.min_activity_ratio),
        max_activity_ratio=float(shared.max_activity_ratio),
    )

    summary = {
        "symbol": target.symbol,
        "artifact_slug": target.artifact_slug,
        "expected_live_status": target.expected_live_status,
        "actual_live_status": actual_live_status or "UNKNOWN",
        "rows_available": int(len(df_raw)),
        "valid_feature_rows": int(valid_feature_rows),
        "malformed_csv_rows": int(malformed_rows),
        "parse_fallback_file_count": int(parse_fallback_files),
        "gap_count": int(gap_count),
        "max_gap_sec": float(max_gap_sec),
        "unique_days": calibrator._unique_days(df_raw),
        "contiguous_window_status": window_status,
        "regime_coverage": regime_coverage,
        "warmup_sufficient": bool(windows is not None and all(bool((payload.get("coverage") or {}).get("ok", False)) for payload in window_status.values())),
        "forward_window_sufficient": bool((window_status.get("forward") or {}).get("coverage", {}).get("ok", False)),
        "eligible_for_grid_search": not blockers,
        "status": "ELIGIBLE" if not blockers else "GRID_BLOCKED",
        "blockers": blockers,
        "warnings": warnings,
        "recorder_files": [str(path) for path in recorder_files],
    }

    if blockers or windows is None:
        return summary, None

    context = SymbolContext(
        target=target,
        shared=shared,
        base_params=base_params,
        baseline_weights=baseline_weights,
        asset_cfgs=asset_cfgs,
        symbol_scope=symbol_scope,
        df_raw=df_raw,
        df_features=df_features,
        windows=windows,
        guardrails=guardrails,
        recorder_files=recorder_files,
    )
    return summary, context


def _baseline_no_go_reasons(metrics_by_window: dict[str, dict[str, Any]], *, min_trades: int) -> list[str]:
    reasons: list[str] = []
    for window_name in ("validation", "forward"):
        metrics = metrics_by_window[window_name]
        if int(metrics.get("total_trades", 0)) < int(min_trades):
            reasons.append(f"{window_name}_min_trade_count")
        if metrics.get("selection_score") is None:
            reasons.append(f"{window_name}_selection_score_ineligible")
        if float(metrics.get("net_return_ratio", 0.0)) < 0.0:
            reasons.append(f"{window_name}_negative_net_return")
    return reasons


def _compute_baseline_summary(context: SymbolContext) -> dict[str, Any]:
    train_df = calibrator._slice_window(
        context.df_raw, context.windows.train_days)
    validation_df = calibrator._slice_window(
        context.df_raw, context.windows.validation_days)
    forward_df = calibrator._slice_window(
        context.df_raw, context.windows.forward_days)

    train_metrics = calibrator._evaluate_window(
        train_df,
        symbols=[context.target.symbol],
        base_params=context.base_params,
        weights=context.baseline_weights,
        asset_cfgs=context.asset_cfgs,
        tf_sec=int(context.shared.tf_sec),
        warmup_bars=int(context.shared.warmup_bars),
        guardrails=context.guardrails,
    )
    validation_metrics = calibrator._evaluate_window(
        validation_df,
        symbols=[context.target.symbol],
        base_params=context.base_params,
        weights=context.baseline_weights,
        asset_cfgs=context.asset_cfgs,
        tf_sec=int(context.shared.tf_sec),
        warmup_bars=int(context.shared.warmup_bars),
        guardrails=context.guardrails,
    )
    forward_metrics = calibrator._evaluate_window(
        forward_df,
        symbols=[context.target.symbol],
        base_params=context.base_params,
        weights=context.baseline_weights,
        asset_cfgs=context.asset_cfgs,
        tf_sec=int(context.shared.tf_sec),
        warmup_bars=int(context.shared.warmup_bars),
        guardrails=context.guardrails,
    )

    baseline_dir = context.shared.artifacts_root / \
        context.target.artifact_slug / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    per_regime = calibrator._run_per_regime_analysis(
        context.df_raw,
        symbols=[context.target.symbol],
        baseline_base_params=context.base_params,
        baseline_weights=context.baseline_weights,
        baseline_asset_cfgs=context.asset_cfgs,
        candidate_base_params=None,
        candidate_weights=None,
        candidate_asset_cfgs=None,
        tf_sec=int(context.shared.tf_sec),
        warmup_bars=int(context.shared.warmup_bars),
        guardrails=context.guardrails,
        out_dir=baseline_dir,
    )
    blocked_regimes = {
        "train": int(sum((train_metrics.get("per_symbol") or {}).get(context.target.symbol, {}).get("regime_blocked_count", 0) for _ in [0])),
        "validation": int(sum((validation_metrics.get("per_symbol") or {}).get(context.target.symbol, {}).get("regime_blocked_count", 0) for _ in [0])),
        "forward": int(sum((forward_metrics.get("per_symbol") or {}).get(context.target.symbol, {}).get("regime_blocked_count", 0) for _ in [0])),
    }
    summary = {
        "symbol": context.target.symbol,
        "artifact_slug": context.target.artifact_slug,
        "live_status": context.target.expected_live_status,
        "base_config_source": str(context.shared.md_amr_yaml),
        "windows": {
            "train_days": list(context.windows.train_days),
            "validation_days": list(context.windows.validation_days),
            "forward_days": list(context.windows.forward_days),
        },
        "metrics": {
            "train": train_metrics,
            "validation": validation_metrics,
            "forward": forward_metrics,
        },
        "blocked_regimes": blocked_regimes,
        "per_regime": per_regime,
        "no_go_reasons": _baseline_no_go_reasons(
            {"train": train_metrics, "validation": validation_metrics,
                "forward": forward_metrics},
            min_trades=int(context.guardrails.min_trades),
        ),
        "artifact_paths": {
            "baseline_summary": str(baseline_dir / "baseline_summary.json"),
            "per_regime_analysis": str(baseline_dir / "per_regime_analysis.json"),
        },
    }
    _json_dump(baseline_dir / "baseline_summary.json", summary)
    return summary


def _build_run_args(context: SymbolContext, family: GridFamily, out_dir: Path) -> list[str]:
    argv = [
        "--recorder-dir",
        str(context.shared.recorder_dir),
        "--md-amr-yaml",
        str(context.shared.md_amr_yaml),
        "--strategies-yaml",
        str(context.shared.strategies_yaml),
        "--symbols",
        context.target.symbol,
        "--start",
        context.shared.start.isoformat(),
        "--end",
        context.shared.end.isoformat(),
        "--tf-sec",
        str(int(context.shared.tf_sec)),
        "--validation-days",
        str(int(context.shared.validation_days)),
        "--forward-days",
        str(int(context.shared.forward_days)),
        "--min-train-days",
        str(int(context.shared.min_train_days)),
        "--trials",
        str(int(family.trials)),
        "--top-k",
        str(int(family.top_k)),
        "--min-trades",
        str(int(context.shared.min_trades)),
        "--max-dd-limit",
        str(float(context.shared.max_dd_limit)),
        "--min-activity-ratio",
        str(float(context.shared.min_activity_ratio)),
        "--max-activity-ratio",
        str(float(context.shared.max_activity_ratio)),
        "--warmup-bars",
        str(int(context.shared.warmup_bars)),
        "--mutate-base-params",
        ",".join(family.mutate_dimensions),
        "--per-regime",
        "--out-dir",
        str(out_dir),
    ]
    if family.freeze_weights:
        argv.append("--freeze-weights")
    return argv


def _command_string(argv: Sequence[str]) -> str:
    return "c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m tools.calibration.calibrate_md_amr_weights " + " ".join(argv)


def _label_candidate(
    *,
    manifest: dict[str, Any],
    validation_artifact: dict[str, Any] | None,
    forward_artifact: dict[str, Any] | None,
    per_regime_payload: dict[str, Any] | None,
    data_quality: dict[str, Any],
    requested_dimensions: Sequence[str],
    allowed_dimensions: Sequence[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    requested_set = {str(item) for item in requested_dimensions}
    allowed_set = {str(item) for item in allowed_dimensions}
    if not requested_set.issubset(allowed_set):
        reasons.append("unsupported_dimension_requested")
        return "PROMOTION_FORBIDDEN", reasons

    if str(manifest.get("status") or "") != "completed":
        failure = (manifest.get("failure") or {}) if isinstance(
            manifest.get("failure"), dict) else {}
        reasons.append(str(failure.get("message") or manifest.get(
            "verdict") or "calibrator_failed_closed"))
        return "NO_GO", reasons

    validation_artifact = validation_artifact or {}
    forward_artifact = forward_artifact or {}
    validation_candidate = validation_artifact.get("candidate") or {}
    validation_baseline = validation_artifact.get("baseline") or {}
    forward_candidate = forward_artifact.get("candidate") or {}
    forward_baseline = forward_artifact.get("baseline") or {}
    concentration = (per_regime_payload or {}).get(
        "candidate_regime_concentration") or {}

    if int(validation_candidate.get("total_trades", 0)) < int((manifest.get("guardrails") or {}).get("min_trades", 0)):
        reasons.append("validation_trades_below_min")
    if int(forward_candidate.get("total_trades", 0)) < int((manifest.get("guardrails") or {}).get("min_trades", 0)):
        reasons.append("forward_trades_below_min")
    if float((validation_artifact.get("delta") or {}).get("net_return_ratio", 0.0)) < 0.0:
        reasons.append("validation_net_return_worse_than_baseline")
    if float((forward_artifact.get("delta") or {}).get("net_return_ratio", 0.0)) < 0.0:
        reasons.append("forward_net_return_worse_than_baseline")
    validation_pf = validation_candidate.get("profit_factor")
    validation_pf_baseline = validation_baseline.get("profit_factor")
    if validation_pf is not None and validation_pf_baseline is not None and float(validation_pf) < float(validation_pf_baseline):
        reasons.append("validation_profit_factor_below_baseline")
    forward_pf = forward_candidate.get("profit_factor")
    forward_pf_baseline = forward_baseline.get("profit_factor")
    if forward_pf is not None and forward_pf_baseline is not None and float(forward_pf) < float(forward_pf_baseline):
        reasons.append("forward_profit_factor_below_baseline")
    if bool(concentration.get("single_positive_regime_only", False)):
        reasons.append("single_positive_regime_only")
    validation_trade_delta = int(
        (validation_artifact.get("delta") or {}).get("total_trades", 0))
    forward_trade_delta = int(
        (forward_artifact.get("delta") or {}).get("total_trades", 0))
    validation_expectancy_delta = float((validation_artifact.get(
        "delta") or {}).get("avg_trade_return_ratio", 0.0) or 0.0)
    forward_expectancy_delta = float((forward_artifact.get(
        "delta") or {}).get("avg_trade_return_ratio", 0.0) or 0.0)
    if validation_trade_delta > 0 and validation_expectancy_delta < 0.0:
        reasons.append("validation_trade_count_up_expectancy_down")
    if forward_trade_delta > 0 and forward_expectancy_delta < 0.0:
        reasons.append("forward_trade_count_up_expectancy_down")

    if reasons:
        return "NO_GO", reasons

    data_warnings = list(data_quality.get("warnings") or [])
    artifact_warnings = list(validation_artifact.get(
        "warnings") or []) + list(forward_artifact.get("warnings") or [])
    if data_warnings or artifact_warnings:
        reasons.extend(data_warnings)
        reasons.extend(artifact_warnings)
        return "SHADOW_ONLY", reasons

    validation_pass = bool(validation_artifact.get("all_passed", False))
    forward_pass = bool(forward_artifact.get("all_passed", False))
    if validation_pass and forward_pass:
        return "CANDIDATE_FOR_OPERATOR_REVIEW", ["validation_and_forward_guardrails_passed"]

    reasons.append("sample_or_window_quality_weaker_than_operator_review_bar")
    return "SHADOW_ONLY", reasons


def _run_grid_family(
    *,
    context: SymbolContext,
    family: GridFamily,
    data_quality: dict[str, Any],
) -> dict[str, Any]:
    out_dir = context.shared.artifacts_root / \
        context.target.artifact_slug / family.name
    argv = _build_run_args(context, family, out_dir)
    rc = calibrator.main(argv)
    manifest_path = out_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(
        encoding="utf-8")) if manifest_path.exists() else {}
    baseline_metrics = json.loads((out_dir / "baseline_metrics.json").read_text(
        encoding="utf-8")) if (out_dir / "baseline_metrics.json").exists() else {}
    candidate_metrics = json.loads((out_dir / "candidate_metrics.json").read_text(
        encoding="utf-8")) if (out_dir / "candidate_metrics.json").exists() else {}
    validation_metrics = json.loads((out_dir / "validation_metrics.json").read_text(
        encoding="utf-8")) if (out_dir / "validation_metrics.json").exists() else {}
    forward_metrics = json.loads((out_dir / "forward_metrics.json").read_text(
        encoding="utf-8")) if (out_dir / "forward_metrics.json").exists() else {}
    per_regime = json.loads((out_dir / "per_regime_analysis.json").read_text(
        encoding="utf-8")) if (out_dir / "per_regime_analysis.json").exists() else {}
    overlay_text = (out_dir / "candidate_md_amr_strategy_overlay.yaml").read_text(
        encoding="utf-8") if (out_dir / "candidate_md_amr_strategy_overlay.yaml").exists() else ""

    selected_candidate = (candidate_metrics.get("selected_candidate") or {
    }) if isinstance(candidate_metrics, dict) else {}
    mutation_values = (selected_candidate.get("mutation_values") or {
    }) if isinstance(selected_candidate, dict) else {}
    candidate_label, label_reasons = _label_candidate(
        manifest=manifest,
        validation_artifact=validation_metrics,
        forward_artifact=forward_metrics,
        per_regime_payload=per_regime,
        data_quality=data_quality,
        requested_dimensions=family.mutate_dimensions,
        allowed_dimensions=calibrator._BASE_PARAM_MUTATION_ORDER,
    )
    summary = {
        "symbol": context.target.symbol,
        "artifact_slug": context.target.artifact_slug,
        "live_status": context.target.expected_live_status,
        "grid_family": family.name,
        "grid_family_title": family.title,
        "freeze_weights": bool(family.freeze_weights),
        "requested_dimensions": list(family.mutate_dimensions),
        "command": _command_string(argv),
        "calibrator_rc": int(rc),
        "status": str(manifest.get("status") or "unknown"),
        "verdict": str(manifest.get("verdict") or "NO_GO_CANDIDATE"),
        "candidate_label": candidate_label,
        "candidate_label_reasons": label_reasons,
        "base_config_source": str((selected_candidate.get("base_config_source") or context.shared.md_amr_yaml)),
        "mutated_dimensions": list(mutation_values.get("mutated_dimensions") or []),
        "old_values": mutation_values.get("old_values") or {},
        "new_values": mutation_values.get("candidate_values") or {},
        "train_metrics": _metrics_snapshot((selected_candidate.get("train") or {})),
        "validation_metrics": _metrics_snapshot((validation_metrics.get("candidate") or {})),
        "forward_metrics": _metrics_snapshot((forward_metrics.get("candidate") or {})),
        "baseline_train_metrics": _metrics_snapshot((baseline_metrics.get("train") or {})),
        "baseline_validation_metrics": _metrics_snapshot((validation_metrics.get("baseline") or {})),
        "baseline_forward_metrics": _metrics_snapshot((forward_metrics.get("baseline") or {})),
        "validation_net_return_lift": float((validation_metrics.get("delta") or {}).get("net_return_ratio", 0.0) or 0.0),
        "forward_net_return_lift": float((forward_metrics.get("delta") or {}).get("net_return_ratio", 0.0) or 0.0),
        "validation_profit_factor_lift": float(((validation_metrics.get("candidate") or {}).get("profit_factor") or 0.0) - ((validation_metrics.get("baseline") or {}).get("profit_factor") or 0.0)),
        "forward_profit_factor_lift": float(((forward_metrics.get("candidate") or {}).get("profit_factor") or 0.0) - ((forward_metrics.get("baseline") or {}).get("profit_factor") or 0.0)),
        "validation_drawdown_change": float((validation_metrics.get("delta") or {}).get("max_drawdown_ratio", 0.0) or 0.0),
        "forward_drawdown_change": float((forward_metrics.get("delta") or {}).get("max_drawdown_ratio", 0.0) or 0.0),
        "validation_holding_change": float(((validation_metrics.get("candidate") or {}).get("avg_holding_bars") or 0.0) - ((validation_metrics.get("baseline") or {}).get("avg_holding_bars") or 0.0)),
        "forward_holding_change": float(((forward_metrics.get("candidate") or {}).get("avg_holding_bars") or 0.0) - ((forward_metrics.get("baseline") or {}).get("avg_holding_bars") or 0.0)),
        "regime_concentration": (per_regime.get("candidate_regime_concentration") or {}),
        "per_regime": (per_regime.get("per_regime") or {}),
        "sample_adequacy": {
            "min_trades": int(context.shared.min_trades),
            "validation_trades": int((validation_metrics.get("candidate") or {}).get("total_trades", 0)),
            "forward_trades": int((forward_metrics.get("candidate") or {}).get("total_trades", 0)),
            "data_quality_status": str(data_quality.get("status") or "UNKNOWN"),
            "data_quality_warnings": list(data_quality.get("warnings") or []),
        },
        "rejection_reason": "; ".join(label_reasons) if label_reasons else "",
        "artifact_paths": {
            "out_dir": str(out_dir),
            "run_manifest": str(out_dir / "run_manifest.json"),
            "baseline_metrics": str(out_dir / "baseline_metrics.json"),
            "candidate_metrics": str(out_dir / "candidate_metrics.json"),
            "validation_metrics": str(out_dir / "validation_metrics.json"),
            "forward_metrics": str(out_dir / "forward_metrics.json"),
            "overlay": str(out_dir / "candidate_md_amr_strategy_overlay.yaml"),
            "per_regime_analysis": str(out_dir / "per_regime_analysis.json"),
            "report": str(out_dir / "report.md"),
        },
        "overlay_yaml": overlay_text,
    }
    _json_dump(out_dir / "phase2b_candidate_summary.json", summary)
    return summary


def _label_priority(label: str) -> int:
    return {
        "CANDIDATE_FOR_OPERATOR_REVIEW": 0,
        "SHADOW_ONLY": 1,
        "NO_GO": 2,
        "PROMOTION_FORBIDDEN": 3,
    }.get(str(label), 9)


def _sort_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            _label_priority(str(item.get("candidate_label") or "")),
            -float(item.get("forward_net_return_lift", 0.0) or 0.0),
            -float(item.get("validation_net_return_lift", 0.0) or 0.0),
            -int((item.get("forward_metrics") or {}).get("total_trades", 0) or 0),
            -int((item.get("validation_metrics") or {}).get("total_trades", 0) or 0),
        ),
    )


def _write_candidate_ranking(paths_root: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    ranking_json = paths_root / "candidate_ranking.json"
    ranking_csv = paths_root / "candidate_ranking.csv"
    _json_dump(ranking_json, rows)
    flat_rows: list[dict[str, Any]] = []
    for row in rows:
        flat_rows.append(
            {
                "symbol": row["symbol"],
                "live_status": row["live_status"],
                "grid_family": row["grid_family"],
                "candidate_label": row["candidate_label"],
                "verdict": row["verdict"],
                "mutated_dimensions": json.dumps(row.get("mutated_dimensions") or []),
                "validation_trades": int((row.get("validation_metrics") or {}).get("total_trades", 0)),
                "forward_trades": int((row.get("forward_metrics") or {}).get("total_trades", 0)),
                "validation_net_return_lift": float(row.get("validation_net_return_lift", 0.0) or 0.0),
                "forward_net_return_lift": float(row.get("forward_net_return_lift", 0.0) or 0.0),
                "validation_profit_factor_lift": float(row.get("validation_profit_factor_lift", 0.0) or 0.0),
                "forward_profit_factor_lift": float(row.get("forward_profit_factor_lift", 0.0) or 0.0),
                "validation_drawdown_change": float(row.get("validation_drawdown_change", 0.0) or 0.0),
                "forward_drawdown_change": float(row.get("forward_drawdown_change", 0.0) or 0.0),
                "rejection_reason": str(row.get("rejection_reason") or ""),
                "out_dir": str((row.get("artifact_paths") or {}).get("out_dir") or ""),
            }
        )
    ranking_csv.parent.mkdir(parents=True, exist_ok=True)
    with ranking_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()) if flat_rows else [
            "symbol",
            "live_status",
            "grid_family",
            "candidate_label",
            "verdict",
            "mutated_dimensions",
            "validation_trades",
            "forward_trades",
            "validation_net_return_lift",
            "forward_net_return_lift",
            "validation_profit_factor_lift",
            "forward_profit_factor_lift",
            "validation_drawdown_change",
            "forward_drawdown_change",
            "rejection_reason",
            "out_dir",
        ])
        writer.writeheader()
        for row in flat_rows:
            writer.writerow(row)
    return {"json": str(ranking_json), "csv": str(ranking_csv)}


def _build_data_quality_report(
    *,
    window_days: list[str],
    shared: SharedConfig,
    summaries: list[dict[str, Any]],
) -> str:
    lines = [
        "# MD_AMR_PHASE2B_DATA_QUALITY_REPORT",
        "",
        "## Shared Window",
        f"- Start: {shared.start.isoformat()}",
        f"- End exclusive: {shared.end.isoformat()}",
        f"- Common recorder days: {json.dumps(window_days)}",
        f"- tf_sec: {int(shared.tf_sec)}",
        f"- validation_days: {int(shared.validation_days)}",
        f"- forward_days: {int(shared.forward_days)}",
        f"- min_train_days: {int(shared.min_train_days)}",
        f"- warmup_bars: {int(shared.warmup_bars)}",
        "",
    ]
    for summary in summaries:
        lines.extend(
            [
                f"## {summary['symbol']}",
                f"- Expected live_status: {summary['expected_live_status']}",
                f"- Actual live_status: {summary['actual_live_status']}",
                f"- Status: {summary['status']}",
                f"- Rows available: {summary['rows_available']}",
                f"- Valid feature rows: {summary['valid_feature_rows']}",
                f"- Malformed CSV rows: {summary['malformed_csv_rows']}",
                f"- Parse fallback file count: {summary['parse_fallback_file_count']}",
                f"- Gap count: {summary['gap_count']}",
                f"- Max gap seconds: {summary['max_gap_sec']}",
                f"- Unique days: {json.dumps(summary['unique_days'])}",
                f"- Regime coverage: {json.dumps(summary['regime_coverage'], sort_keys=True)}",
                f"- Warmup sufficient: {bool(summary['warmup_sufficient'])}",
                f"- Forward window sufficient: {bool(summary['forward_window_sufficient'])}",
                f"- Eligible for grid search: {bool(summary['eligible_for_grid_search'])}",
                f"- Blockers: {json.dumps(summary['blockers'])}",
                f"- Warnings: {json.dumps(summary['warnings'])}",
            ]
        )
        if summary.get("contiguous_window_status"):
            lines.append("- Window coverage:")
            for window_name, payload in summary["contiguous_window_status"].items():
                stats = payload.get("stats") or {}
                per_symbol = (stats.get("per_symbol") or {}
                              ).get(summary["symbol"], {})
                coverage = payload.get("coverage") or {}
                lines.append(
                    (
                        f"  - {window_name}: ok={bool(coverage.get('ok', False))} "
                        f"rows={int(per_symbol.get('rows', 0))} longest_segment_rows={int(per_symbol.get('longest_segment_rows', 0))} "
                        f"segments={int(per_symbol.get('segments', 0))} days={json.dumps(payload.get('days') or [])}"
                    )
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_baseline_report(shared: SharedConfig, baselines: list[dict[str, Any]]) -> str:
    lines = [
        "# MD_AMR_PHASE2B_BASELINE_CONFIRMATION_REPORT",
        "",
        "## Shared Split Policy",
        f"- Start: {shared.start.isoformat()}",
        f"- End exclusive: {shared.end.isoformat()}",
        f"- validation_days: {int(shared.validation_days)}",
        f"- forward_days: {int(shared.forward_days)}",
        f"- min_train_days: {int(shared.min_train_days)}",
        f"- min_trades: {int(shared.min_trades)}",
        "",
    ]
    for baseline in baselines:
        metrics = baseline["metrics"]
        lines.extend(
            [
                f"## {baseline['symbol']}",
                f"- live_status: {baseline['live_status']}",
                f"- base config source: {baseline['base_config_source']}",
                f"- Windows: train={json.dumps(baseline['windows']['train_days'])} validation={json.dumps(baseline['windows']['validation_days'])} forward={json.dumps(baseline['windows']['forward_days'])}",
                f"- Train trades/net/PF/DD/holding: {int(metrics['train'].get('total_trades', 0))} / {_format_ratio(metrics['train'].get('net_return_ratio'))} / {_format_float(metrics['train'].get('profit_factor'))} / {_format_ratio(metrics['train'].get('max_drawdown_ratio'))} / {_format_float(metrics['train'].get('avg_holding_bars'))}",
                f"- Validation trades/net/PF/DD/holding: {int(metrics['validation'].get('total_trades', 0))} / {_format_ratio(metrics['validation'].get('net_return_ratio'))} / {_format_float(metrics['validation'].get('profit_factor'))} / {_format_ratio(metrics['validation'].get('max_drawdown_ratio'))} / {_format_float(metrics['validation'].get('avg_holding_bars'))}",
                f"- Forward trades/net/PF/DD/holding: {int(metrics['forward'].get('total_trades', 0))} / {_format_ratio(metrics['forward'].get('net_return_ratio'))} / {_format_float(metrics['forward'].get('profit_factor'))} / {_format_ratio(metrics['forward'].get('max_drawdown_ratio'))} / {_format_float(metrics['forward'].get('avg_holding_bars'))}",
                f"- Blocked regimes: {json.dumps(baseline['blocked_regimes'], sort_keys=True)}",
                f"- No-go reasons: {json.dumps(baseline['no_go_reasons'])}",
                f"- Per-regime summary path: {baseline['artifact_paths']['per_regime_analysis']}",
            ]
        )
        per_regime = (baseline.get("per_regime") or {}).get("per_regime") or {}
        if per_regime:
            lines.append("- Per-regime trades/net/PF:")
            for regime_label, payload in per_regime.items():
                baseline_payload = payload.get("baseline") or {}
                lines.append(
                    (
                        f"  - {regime_label}: trades={int(baseline_payload.get('total_trades', 0))} "
                        f"net={_format_ratio(baseline_payload.get('net_return_ratio'))} "
                        f"pf={_format_float(baseline_payload.get('profit_factor'))}"
                    )
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_aggression_grid_report(
    *,
    shared: SharedConfig,
    families: list[GridFamily],
    data_quality: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    ranking_paths: dict[str, str],
) -> str:
    best_by_symbol: dict[str, dict[str, Any]] = {}
    for row in _sort_candidate_rows(candidate_rows):
        best_by_symbol.setdefault(str(row["symbol"]), row)

    lines = [
        "# MD_AMR_PHASE2B_AGGRESSION_GRID_REPORT",
        "",
        "## Scope",
        f"- Start: {shared.start.isoformat()}",
        f"- End exclusive: {shared.end.isoformat()}",
        f"- tf_sec: {int(shared.tf_sec)}",
        f"- min_trades: {int(shared.min_trades)}",
        "",
        "## Data Quality By Symbol",
    ]
    for summary in data_quality:
        lines.append(
            f"- {summary['symbol']}: status={summary['status']} rows={summary['rows_available']} valid_feature_rows={summary['valid_feature_rows']} malformed_rows={summary['malformed_csv_rows']} gaps={summary['gap_count']} warnings={json.dumps(summary['warnings'])}"
        )
    lines.extend(["", "## Grid Families Run"])
    for family in families:
        lines.append(
            f"- {family.title}: name={family.name} mutate_dimensions={json.dumps(list(family.mutate_dimensions))} trials={int(family.trials)} top_k={int(family.top_k)} freeze_weights={bool(family.freeze_weights)}"
        )
    lines.extend(["", "## Best Candidates By Symbol"])
    for symbol in [item.symbol for item in _target_specs()]:
        best = best_by_symbol.get(symbol)
        if best is None:
            lines.append(f"- {symbol}: no candidate runs executed")
            continue
        lines.append(
            (
                f"- {symbol}: label={best['candidate_label']} family={best['grid_family']} verdict={best['verdict']} "
                f"validation_lift={_format_ratio(best.get('validation_net_return_lift'))} "
                f"forward_lift={_format_ratio(best.get('forward_net_return_lift'))} "
                f"mutated_dimensions={json.dumps(best.get('mutated_dimensions') or [])}"
            )
        )
    lines.extend([
        "",
        "## Machine-Readable Ranking",
        f"- JSON: {ranking_paths['json']}",
        f"- CSV: {ranking_paths['csv']}",
        "",
        "## Candidate Labels",
        "- NO_GO: fails validation/forward guardrails or other explicit rejection rules.",
        "- SHADOW_ONLY: avoids hard promotion claims but carries data-quality or stability caveats.",
        "- CANDIDATE_FOR_OPERATOR_REVIEW: passes bounded analysis gates without obvious overfit markers.",
        "- PROMOTION_FORBIDDEN: would cross unsupported package boundaries.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _build_candidate_overlays_report(candidate_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# MD_AMR_PHASE2B_CANDIDATE_OVERLAYS_REPORT",
        "",
    ]
    for row in _sort_candidate_rows(candidate_rows):
        lines.extend(
            [
                f"## {row['symbol']} / {row['grid_family']}",
                f"- live_status: {row['live_status']}",
                f"- base config source: {row['base_config_source']}",
                f"- candidate label: {row['candidate_label']}",
                f"- verdict: {row['verdict']}",
                f"- mutated dimensions: {json.dumps(row.get('mutated_dimensions') or [])}",
                f"- old values: {json.dumps(row.get('old_values') or {}, sort_keys=True)}",
                f"- new values: {json.dumps(row.get('new_values') or {}, sort_keys=True)}",
                f"- train metrics: {json.dumps(row.get('train_metrics') or {}, sort_keys=True)}",
                f"- validation metrics: {json.dumps(row.get('validation_metrics') or {}, sort_keys=True)}",
                f"- forward metrics: {json.dumps(row.get('forward_metrics') or {}, sort_keys=True)}",
                f"- per-regime metrics: {json.dumps(row.get('per_regime') or {}, sort_keys=True)}",
                f"- regime concentration: {json.dumps(row.get('regime_concentration') or {}, sort_keys=True)}",
                f"- rejection reason: {row.get('rejection_reason') or 'n/a'}",
                f"- overlay path: {(row.get('artifact_paths') or {}).get('overlay')}",
                f"- overlay yaml:\n",
                "```yaml",
                str(row.get("overlay_yaml") or "").rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if int(args.tf_sec) != 900:
        raise calibrator.CalibrationError(
            "INPUT_CONTRACT_VIOLATION",
            f"Phase 2B md_amr aggression grid currently supports only tf_sec=900, got {args.tf_sec}.",
        )

    targets = _target_specs()
    recorder_dir = Path(args.recorder_dir)
    artifacts_root = Path(args.artifacts_root)
    reports_root = Path(args.reports_root)

    start, end, common_days = _resolve_common_window(
        recorder_dir=recorder_dir,
        targets=targets,
        tf_sec=int(args.tf_sec),
        start=args.start,
        end=args.end,
        analysis_days=max(1, int(args.analysis_days)),
        validation_days=max(1, int(args.validation_days)),
        forward_days=max(1, int(args.forward_days)),
        min_train_days=max(1, int(args.min_train_days)),
    )

    shared = SharedConfig(
        recorder_dir=recorder_dir,
        md_amr_yaml=Path(args.md_amr_yaml),
        strategies_yaml=Path(args.strategies_yaml),
        tf_sec=int(args.tf_sec),
        start=start,
        end=end,
        validation_days=max(1, int(args.validation_days)),
        forward_days=max(1, int(args.forward_days)),
        min_train_days=max(1, int(args.min_train_days)),
        min_trades=max(1, int(args.min_trades)),
        max_dd_limit=float(args.max_dd_limit),
        min_activity_ratio=float(args.min_activity_ratio),
        max_activity_ratio=float(args.max_activity_ratio),
        warmup_bars=max(1, int(args.warmup_bars)),
        artifacts_root=artifacts_root,
        reports_root=reports_root,
    )

    calibrator._require_md_amr_runtime()
    md_amr_cfg = calibrator._load_md_amr_yaml(shared.md_amr_yaml)
    strategies_cfg = calibrator._load_strategies_registry(
        shared.strategies_yaml)

    data_quality_summaries: list[dict[str, Any]] = []
    contexts: list[SymbolContext] = []
    for target in targets:
        summary, context = _prepare_symbol_context(
            target=target,
            shared=shared,
            md_amr_cfg=md_amr_cfg,
            strategies_cfg=strategies_cfg,
        )
        data_quality_summaries.append(summary)
        symbol_root = shared.artifacts_root / target.artifact_slug
        _json_dump(symbol_root / "data_quality.json", summary)
        if context is not None:
            contexts.append(context)

    baseline_summaries = [_compute_baseline_summary(
        context) for context in contexts]
    grid_rows: list[dict[str, Any]] = []
    families = _grid_families(args)
    data_quality_by_symbol = {item["symbol"]                              : item for item in data_quality_summaries}
    for context in contexts:
        for family in families:
            grid_rows.append(
                _run_grid_family(
                    context=context,
                    family=family,
                    data_quality=data_quality_by_symbol[context.target.symbol],
                )
            )

    ranking_rows = _sort_candidate_rows(grid_rows)
    ranking_paths = _write_candidate_ranking(
        shared.artifacts_root, ranking_rows)

    phase2b_manifest = {
        "package": "PHASE2B_MD_AMR_AGGRESSION_GRID_SEARCH",
        "window": {
            "start": shared.start.isoformat(),
            "end_exclusive": shared.end.isoformat(),
            "common_days": common_days,
        },
        "shared_policy": {
            "validation_days": int(shared.validation_days),
            "forward_days": int(shared.forward_days),
            "min_train_days": int(shared.min_train_days),
            "min_trades": int(shared.min_trades),
            "warmup_bars": int(shared.warmup_bars),
        },
        "families": [
            {
                "name": family.name,
                "title": family.title,
                "mutate_dimensions": list(family.mutate_dimensions),
                "trials": int(family.trials),
                "top_k": int(family.top_k),
                "freeze_weights": bool(family.freeze_weights),
            }
            for family in families
        ],
        "data_quality": data_quality_summaries,
        "baseline_summaries": baseline_summaries,
        "candidate_rows": ranking_rows,
        "ranking_paths": ranking_paths,
        "report_paths": {
            "data_quality_report": str(shared.reports_root / "MD_AMR_PHASE2B_DATA_QUALITY_REPORT.md"),
            "baseline_report": str(shared.reports_root / "MD_AMR_PHASE2B_BASELINE_CONFIRMATION_REPORT.md"),
            "aggression_grid_report": str(shared.reports_root / "MD_AMR_PHASE2B_AGGRESSION_GRID_REPORT.md"),
            "candidate_overlays_report": str(shared.reports_root / "MD_AMR_PHASE2B_CANDIDATE_OVERLAYS_REPORT.md"),
        },
    }
    _json_dump(shared.artifacts_root /
               "phase2b_manifest.json", phase2b_manifest)

    _markdown_write(
        shared.reports_root / "MD_AMR_PHASE2B_DATA_QUALITY_REPORT.md",
        _build_data_quality_report(
            window_days=common_days, shared=shared, summaries=data_quality_summaries),
    )
    _markdown_write(
        shared.reports_root / "MD_AMR_PHASE2B_BASELINE_CONFIRMATION_REPORT.md",
        _build_baseline_report(shared, baseline_summaries),
    )
    _markdown_write(
        shared.reports_root / "MD_AMR_PHASE2B_AGGRESSION_GRID_REPORT.md",
        _build_aggression_grid_report(
            shared=shared,
            families=families,
            data_quality=data_quality_summaries,
            candidate_rows=ranking_rows,
            ranking_paths=ranking_paths,
        ),
    )
    _markdown_write(
        shared.reports_root / "MD_AMR_PHASE2B_CANDIDATE_OVERLAYS_REPORT.md",
        _build_candidate_overlays_report(ranking_rows),
    )

    print(
        f"phase2b_start={shared.start.isoformat()} phase2b_end_exclusive={shared.end.isoformat()}")
    print(
        f"eligible_symbols={json.dumps([item.target.symbol for item in contexts])}")
    print(
        f"grid_blocked_symbols={json.dumps([item['symbol'] for item in data_quality_summaries if item['status'] == 'GRID_BLOCKED'])}")
    print(f"candidate_ranking_json={ranking_paths['json']}")
    print(f"candidate_ranking_csv={ranking_paths['csv']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
