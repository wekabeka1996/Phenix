"""CLI entry point: ``python -m tools.parquet_pipeline``

Usage examples::

    python -m tools.parquet_pipeline --symbol BTCUSDT --tf 5m
    python -m tools.parquet_pipeline --symbol BTCUSDT --tf 5m --months 2024-01 2024-02
    python -m tools.parquet_pipeline --symbol BTCUSDT --tf 5m --audit-only
    python -m tools.parquet_pipeline --symbol BTCUSDT --tf 5m --emit-state
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl  # noqa: E402

from tools.parquet_pipeline.actuator_rules import (  # noqa: E402
    ActuatorConfig,
    run_actuator,
)
from tools.parquet_pipeline.aggregation import compute_stress_level  # noqa: E402
from tools.parquet_pipeline.audit import audit  # noqa: E402
from tools.parquet_pipeline.discovery import (  # noqa: E402
    DEFAULT_RENAME,
    discover_files,
    parse_tf_minutes,
)
from tools.parquet_pipeline.stress import (  # noqa: E402
    STRESS_OUTPUT_COLUMNS,
    STRESS_V0_METRICS,
    compute_stress_v0,
)


class PipelineError(RuntimeError):
    pass


# ── Default config values (used when regime.yaml unavailable) ────────

_DEFAULT_THRESHOLDS = {
    "atr_sigma": 2.0,
    "vol_sigma": 2.0,
    "gap_sigma": 3.0,
    "range_sigma": 2.5,
    "volume_sigma": 0.0,
    "spread_sigma": 0.0,
    "depth_drop_pct": 0.0,
}

_DEFAULT_WEIGHTS = {"atr": 0.30, "vol": 0.30, "gap": 0.20, "range": 0.20}

_DEFAULT_ACTUATOR = ActuatorConfig(
    enter_stress=0.60,
    exit_stress=0.40,
    enter_extreme=0.85,
    exit_extreme=0.70,
    consecutive_bars_enter=3,
    consecutive_bars_exit=2,
    min_duration_bars=5,
    switch_window_bars=50,
    max_switches_per_window=3,
)


# ── CLI ──────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="parquet-pipeline",
        description="Parquet audit + stress v0 extract + state actuator",
    )
    p.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT")
    p.add_argument("--tf", required=True, help="Timeframe, e.g. 5m")
    p.add_argument("--months", nargs="+", default=None,
                   help="Optional month filter, e.g. 2024-01 2024-02")
    p.add_argument("--data-dir", default="data/processed",
                   help="Root data directory")
    p.add_argument("--output-dir", default=None,
                   help="Output dir (default: <data-dir>/<symbol>/<tf>/stress_v0)")
    p.add_argument("--config-dir", default="config/aurora",
                   help="Config directory for system_stress params")
    p.add_argument("--audit-only", action="store_true",
                   help="Run audit only, skip stress extract")
    p.add_argument("--emit-state", action="store_true",
                   help="Run stress state actuator (aggregation + hysteresis FSM)")
    p.add_argument("--window", type=int, default=None,
                   help="Override rolling window (default: from config or 100)")
    p.add_argument("--burn-in", type=int, default=None,
                   help="Override burn-in bars (default: from config or 120)")
    return p.parse_args(argv)


# ── Config helpers ───────────────────────────────────────────────────

def _load_stress_config(config_dir: str):
    """Try to load system_stress config.  Returns None if unavailable."""
    try:
        from apps.reference.config_loader import ConfigLoader

        cfg = ConfigLoader(config_dir=Path(config_dir)).load_config()
        return cfg.system_stress  # may be None (disabled)
    except Exception:
        return None


def _extract_thresholds(stress_cfg) -> dict[str, float]:
    """Extract thresholds dict from Pydantic model or return defaults."""
    if stress_cfg is None or stress_cfg.thresholds is None:
        return dict(_DEFAULT_THRESHOLDS)
    t = stress_cfg.thresholds
    return {
        "atr_sigma": t.atr_sigma,
        "vol_sigma": t.vol_sigma,
        "gap_sigma": t.gap_sigma,
        "range_sigma": t.range_sigma,
        "volume_sigma": t.volume_sigma,
        "spread_sigma": t.spread_sigma,
        "depth_drop_pct": t.depth_drop_pct,
    }


def _extract_aggregation(stress_cfg) -> tuple[str, dict[str, float] | None, int | None]:
    """Extract (method, weights, k) from Pydantic model or return defaults."""
    if stress_cfg is None or stress_cfg.aggregation is None:
        return "weighted_vote", dict(_DEFAULT_WEIGHTS), None
    agg = stress_cfg.aggregation
    return agg.method, dict(agg.weights) if agg.weights else None, agg.k


def _extract_actuator_config(stress_cfg) -> ActuatorConfig:
    """Extract ActuatorConfig from Pydantic model or return defaults."""
    if stress_cfg is None or stress_cfg.state_mapping is None:
        return _DEFAULT_ACTUATOR
    sm = stress_cfg.state_mapping
    return ActuatorConfig(
        enter_stress=sm.enter_stress,
        exit_stress=sm.exit_stress,
        enter_extreme=sm.enter_extreme,
        exit_extreme=sm.exit_extreme,
        consecutive_bars_enter=sm.consecutive_bars_enter,
        consecutive_bars_exit=sm.consecutive_bars_exit,
        min_duration_bars=sm.min_duration_bars,
        switch_window_bars=sm.switch_window_bars,
        max_switches_per_window=sm.max_switches_per_window,
    )


# ── Summary / provenance ─────────────────────────────────────────────

def _generate_summary(
    df: pl.DataFrame,
    args: argparse.Namespace,
    window: int,
    burn_in: int,
    audit_report: dict,
    *,
    state_df: pl.DataFrame | None = None,
    actuator_total_switches: int | None = None,
) -> str:
    lines = [
        "# Stress v0 Summary",
        "",
        f"**Symbol:** {args.symbol}  ",
        f"**Timeframe:** {args.tf}  ",
        f"**Window:** {window}  ",
        f"**Burn-in:** {burn_in}  ",
        f"**Rows:** {len(df)}  ",
        f"**Time range:** "
        f"{audit_report.get('time_range', {}).get('min', '?')} "
        f"to {audit_report.get('time_range', {}).get('max', '?')}",
        "",
        "## Z-score Statistics",
        "",
        "| Metric | Mean | Std | P50 | P95 | P99 | Max |",
        "|--------|------|-----|-----|-----|-----|-----|",
    ]

    for m in STRESS_V0_METRICS:
        z_col = f"z_{m}"
        col = df[z_col].drop_nulls()
        if len(col) == 0:
            lines.append(f"| {z_col} | - | - | - | - | - | - |")
            continue
        lines.append(
            f"| {z_col} "
            f"| {col.mean():.3f} "
            f"| {col.std():.3f} "
            f"| {col.quantile(0.50):.3f} "
            f"| {col.quantile(0.95):.3f} "
            f"| {col.quantile(0.99):.3f} "
            f"| {col.max():.3f} |"
        )

    # ── State summary (if --emit-state) ──────────────────────────
    if state_df is not None and actuator_total_switches is not None:
        total_bars = len(state_df)
        lines.append("")
        lines.append("## State Summary")
        lines.append("")
        lines.append(f"**Total switches:** {actuator_total_switches}  ")

        # State distribution
        for state_name in ("NORMAL", "STRESS", "EXTREME"):
            count = int((state_df["state"] == state_name).sum())
            pct = count / total_bars * 100 if total_bars > 0 else 0
            lines.append(f"**{state_name}:** {count} bars ({pct:.1f}%)  ")

        # Longest stable run
        if total_bars > 0:
            runs = state_df.with_columns(
                (pl.col("state") != pl.col("state").shift(1))
                .fill_null(True)
                .cum_sum()
                .alias("_run_id")
            )
            run_lengths = runs.group_by("_run_id", "state").len()
            longest = run_lengths["len"].max()
            longest_state = run_lengths.filter(
                pl.col("len") == longest
            )["state"][0]
            lines.append(
                f"**Longest stable run:** {longest} bars ({longest_state})  "
            )

    # ── Audit issues ─────────────────────────────────────────────
    lines.append("")
    lines.append("## Audit Issues")
    lines.append("")
    issues = audit_report.get("issues", [])
    if issues:
        for i in issues:
            lines.append(f"- {i}")
    else:
        lines.append("None.")

    return "\n".join(lines) + "\n"


def _write_provenance(
    out_dir: Path,
    args: argparse.Namespace,
    files: list[Path],
    *,
    stress_computed: bool,
    state_computed: bool = False,
    window: int | None = None,
    burn_in: int | None = None,
) -> None:
    prov = {
        "symbol": args.symbol,
        "tf": args.tf,
        "months_filter": args.months,
        "data_dir": str(args.data_dir),
        "config_dir": str(args.config_dir),
        "files_processed": [str(f) for f in files],
        "stress_computed": stress_computed,
        "state_computed": state_computed,
        "window": window,
        "burn_in": burn_in,
        "output_dir": str(out_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    prov_path = out_dir / "provenance.json"
    prov_path.write_text(
        json.dumps(prov, indent=2, default=str), encoding="utf-8"
    )
    print(f"[provenance] {prov_path}")


# ── Main ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    data_dir = Path(args.data_dir)
    tf_minutes = parse_tf_minutes(args.tf)

    # ── Discover ─────────────────────────────────────────────────────
    print(f"[discover] {args.symbol}/{args.tf} in {data_dir}")
    try:
        files = discover_files(data_dir, args.symbol, args.tf, months=args.months)
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    print(f"[discover] {len(files)} file(s)")

    # ── Output dir ───────────────────────────────────────────────────
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = data_dir / args.symbol / args.tf / "stress_v0"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Audit ────────────────────────────────────────────────────────
    print("[audit] running...")
    report = audit(files, tf_minutes=tf_minutes)

    audit_path = out_dir / "audit_report.json"
    audit_path.write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    status = "PASSED" if report["passed"] else "ISSUES FOUND"
    print(f"[audit] {status} -> {audit_path}")

    if report.get("issues"):
        for issue in report["issues"]:
            print(f"  ! {issue}")

    if args.audit_only:
        _write_provenance(out_dir, args, files, stress_computed=False)
        return 0

    # Block on missing columns (stress needs OHLCV)
    if any("missing column" in i for i in report.get("issues", [])):
        print("[error] cannot compute stress: missing OHLCV columns",
              file=sys.stderr)
        return 3

    # ── Load stress config ───────────────────────────────────────────
    stress_cfg = _load_stress_config(args.config_dir)
    window = args.window or (
        stress_cfg.baseline_window if stress_cfg and stress_cfg.baseline_window else 100
    )
    burn_in = args.burn_in or (
        stress_cfg.burn_in_bars if stress_cfg else 120
    )

    # ── Stress extract ───────────────────────────────────────────────
    print(f"[stress] computing v0 (window={window}, burn_in={burn_in})...")

    lf = pl.scan_parquet([str(f) for f in files])
    rename = {k: v for k, v in DEFAULT_RENAME.items() if k in lf.collect_schema()}
    if rename:
        lf = lf.rename(rename)

    stress_lf = compute_stress_v0(lf, window=window, burn_in=burn_in)
    stress_df = stress_lf.select(STRESS_OUTPUT_COLUMNS).collect()

    stress_path = out_dir / "stress_timeseries.parquet"
    stress_df.write_parquet(str(stress_path))
    print(f"[stress] {len(stress_df)} rows -> {stress_path}")

    # ── State actuator (--emit-state) ────────────────────────────────
    state_df = None
    actuator_total_switches = None

    if args.emit_state:
        thresholds = _extract_thresholds(stress_cfg)
        method, weights, k = _extract_aggregation(stress_cfg)
        act_cfg = _extract_actuator_config(stress_cfg)

        print(f"[state] aggregation={method}, actuator running...")

        # Compute stress_level from z-scores
        stress_level_lf = compute_stress_level(
            stress_df.lazy(),
            method=method,
            weights=weights,
            thresholds=thresholds,
            k=k,
        )
        stress_level_df = stress_level_lf.collect()

        # Run actuator FSM
        sl_list = stress_level_df["stress_level"].to_list()
        result = run_actuator(sl_list, act_cfg)

        # Build state DataFrame
        state_df = pl.DataFrame({
            "timestamp": stress_level_df["timestamp"],
            "stress_level": stress_level_df["stress_level"],
            "state": result.states,
            "why": result.whys,
            "switches_total": result.switches_cumulative,
        })

        state_path = out_dir / "stress_state_timeseries.parquet"
        state_df.write_parquet(str(state_path))
        actuator_total_switches = result.total_switches

        print(
            f"[state] {len(state_df)} rows, "
            f"{actuator_total_switches} switches -> {state_path}"
        )

    # ── Summary ──────────────────────────────────────────────────────
    summary = _generate_summary(
        stress_df, args, window, burn_in, report,
        state_df=state_df,
        actuator_total_switches=actuator_total_switches,
    )
    summary_path = out_dir / "stress_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"[summary] {summary_path}")

    # ── Provenance ───────────────────────────────────────────────────
    _write_provenance(
        out_dir, args, files,
        stress_computed=True,
        state_computed=args.emit_state,
        window=window,
        burn_in=burn_in,
    )

    return 0


# ── R1: Market Structure Audit subcommand ────────────────────────────

def _parse_months_range(range_str: str) -> list[str]:
    """Parse '2023-06:2024-03' into ['2023-06', '2023-07', ..., '2024-03']."""
    parts = range_str.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid months-range format: {range_str!r}. Expected 'YYYY-MM:YYYY-MM'")
    start_y, start_m = map(int, parts[0].split("-"))
    end_y, end_m = map(int, parts[1].split("-"))
    months: list[str] = []
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _parse_r1_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="parquet-pipeline r1",
        description="Phase R1: Market Structure Audit — multi-symbol analysis",
    )
    p.add_argument(
        "--symbols", nargs="+",
        default=["BTCUSDT", "ETHUSDT", "DOGEUSDT", "1000PEPEUSDT"],
        help="Symbols to analyse (default: all 4 main)",
    )
    p.add_argument("--tf", default="5m", help="Timeframe (default: 5m)")
    p.add_argument(
        "--months", nargs="+", default=None,
        help="Explicit month filter, e.g. 2023-06 2023-07",
    )
    p.add_argument(
        "--months-range", default=None,
        help="Month range shorthand, e.g. 2023-06:2024-03",
    )
    p.add_argument("--data-dir", default="data/processed")
    p.add_argument(
        "--output-dir", default="reports",
        help="Output directory for reports (default: reports/)",
    )
    p.add_argument("--config-dir", default="config/aurora")
    p.add_argument(
        "--window", type=int, default=100,
        help="Rolling window for stress metrics (default: 100)",
    )
    p.add_argument(
        "--burn-in", type=int, default=120,
        help="Burn-in bars before emitting metrics (default: 120)",
    )
    p.add_argument(
        "--include-grid", action="store_true",
        help="(optional) Run stability grid simulation (Block 5) — slow",
    )
    return p.parse_args(argv)


def _generate_r1_report(
    results: dict,
    symbols: list[str],
    tf: str,
    months: list[str] | None,
) -> str:
    """Generate cross-symbol markdown report from per-symbol analysis results."""
    from datetime import date as _date

    lines = [
        "# Market Structure Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Symbols:** {', '.join(symbols)}  ",
        f"**Timeframe:** {tf}  ",
        f"**Period:** {months[0] if months else 'all'} — {months[-1] if months else 'all'}  ",
        "",
        "---",
        "",
        "## 1. Distribution Summary",
        "",
        "### ATR (Average True Range)",
        "",
        "| Symbol | p50 | p90 | p99 | tail_ratio | skew |",
        "|--------|-----|-----|-----|------------|------|",
    ]
    for sym in symbols:
        dist = results.get(sym, {}).get("distributions", {}).get("atr", {})
        if not dist:
            lines.append(f"| {sym} | — | — | — | — | — |")
            continue
        lines.append(
            f"| {sym} "
            f"| {dist.get('p50', '?'):.6f} "
            f"| {dist.get('p90', '?'):.6f} "
            f"| {dist.get('p99', '?'):.6f} "
            f"| {dist.get('tail_ratio', '?')} "
            f"| {dist.get('skew', '?'):.2f} |"
        )

    lines += [
        "",
        "### Log Return",
        "",
        "| Symbol | mean | std | skew | kurtosis | p99 |",
        "|--------|------|-----|------|----------|-----|",
    ]
    for sym in symbols:
        dist = results.get(sym, {}).get("distributions", {}).get("log_return", {})
        if not dist:
            lines.append(f"| {sym} | — | — | — | — | — |")
            continue
        lines.append(
            f"| {sym} "
            f"| {dist.get('mean', 0):.6f} "
            f"| {dist.get('std', 0):.6f} "
            f"| {dist.get('skew', 0):.2f} "
            f"| {dist.get('kurtosis', 0):.2f} "
            f"| {dist.get('p99', 0):.6f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 2. Persistence (State Runs)",
        "",
        "Proxy states based on normalized SMA slope (TREND_UP / TREND_DOWN / FLAT).",
        "",
        "| Symbol | TREND_UP runs | TREND_UP median | FLAT runs | FLAT median | FLAT longest |",
        "|--------|--------------|-----------------|-----------|-------------|--------------|",
    ]
    for sym in symbols:
        pers = results.get(sym, {}).get("persistence", {})
        tu = pers.get("TREND_UP", {})
        fl = pers.get("FLAT", {})
        lines.append(
            f"| {sym} "
            f"| {tu.get('count_runs', '—')} "
            f"| {tu.get('median_run_bars', '—')} "
            f"| {fl.get('count_runs', '—')} "
            f"| {fl.get('median_run_bars', '—')} "
            f"| {fl.get('longest_run_bars', '—')} |"
        )

    lines += [
        "",
        "| Symbol | autocorr(return, lag=1) | autocorr(vol, lag=1) |",
        "|--------|------------------------|----------------------|",
    ]
    for sym in symbols:
        pers = results.get(sym, {}).get("persistence", {})
        lines.append(
            f"| {sym} "
            f"| {pers.get('autocorr_return_lag1', '—')} "
            f"| {pers.get('autocorr_vol_lag1', '—')} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 3. Regime Separability",
        "",
        "Overlap > 0.70 → LOW_SEPARABILITY flag.",
        "",
        "### Vol (ATR) separability by directionality",
        "",
        "| Symbol | TREND_UP vs FLAT overlap | TREND_DOWN vs FLAT overlap | LOW_SEP flags |",
        "|--------|--------------------------|---------------------------|---------------|",
    ]
    for sym in symbols:
        sep = results.get(sym, {}).get("separability", {})
        vol_sep = sep.get("vol_separability_by_direction", {})
        tu_flat = vol_sep.get("TREND_UP_vs_FLAT", {})
        td_flat = vol_sep.get("TREND_DOWN_vs_FLAT", {})
        flags = [k for k, v in vol_sep.items() if v.get("low_separability")]
        lines.append(
            f"| {sym} "
            f"| {tu_flat.get('overlap_coefficient', '—')} "
            f"| {td_flat.get('overlap_coefficient', '—')} "
            f"| {', '.join(flags) if flags else 'none'} |"
        )

    lines += [
        "",
        "### Return separability by vol bucket",
        "",
        "| Symbol | LOW_VOL vs HIGH_VOL overlap | bhattacharyya | LOW_SEP |",
        "|--------|---------------------------|---------------|---------|",
    ]
    for sym in symbols:
        sep = results.get(sym, {}).get("separability", {})
        ret_sep = sep.get("return_separability_by_vol_bucket", {})
        lv_hv = ret_sep.get("LOW_VOL_vs_HIGH_VOL", {})
        low_sep = "YES" if lv_hv.get("low_separability") else "no"
        lines.append(
            f"| {sym} "
            f"| {lv_hv.get('overlap_coefficient', '—')} "
            f"| {lv_hv.get('bhattacharyya_distance', '—')} "
            f"| {low_sep} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 4. Structural Breaks",
        "",
        "Hurst < 0.45 = mean_reversion, 0.45–0.55 = random_walk, > 0.55 = trending.",
        "",
        "| Symbol | Hurst(return) | Hurst(vol) | vol_cluster_lag1 | Interpretation |",
        "|--------|--------------|------------|-----------------|----------------|",
    ]
    for sym in symbols:
        sb = results.get(sym, {}).get("structural_breaks", {})
        lines.append(
            f"| {sym} "
            f"| {sb.get('hurst_return', '—')} "
            f"| {sb.get('hurst_vol', '—')} "
            f"| {sb.get('vol_clustering_lag1', '—')} "
            f"| {sb.get('hurst_return_interpretation', '—')} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 5. Calibration Recommendations",
        "",
    ]
    for sym in symbols:
        sb = results.get(sym, {}).get("structural_breaks", {})
        pers = results.get(sym, {}).get("persistence", {})
        recs: list[str] = []

        hurst = sb.get("hurst_return")
        if hurst is not None:
            if hurst < 0.45:
                recs.append("Return is mean-reverting → consider increasing signal threshold for trend-following")
            elif hurst > 0.55:
                recs.append("Return is trending → trend-following signal weights appropriate")

        vol_lag1 = sb.get("vol_clustering_lag1")
        if vol_lag1 is not None and vol_lag1 > 0.90:
            recs.append(f"vol_clustering_lag1={vol_lag1:.3f} — vol regimes are very persistent → large min_duration_bars advisable")

        flat_median = pers.get("FLAT", {}).get("median_run_bars")
        if flat_median is not None:
            if flat_median > 100:
                recs.append(f"FLAT median run={flat_median} bars — regime is stable → hysteresis_bars can be increased safely")
            elif flat_median < 20:
                recs.append(f"FLAT median run={flat_median} bars — regime is noisy → increase consecutive_bars_enter")

        if not recs:
            recs.append("No strong signals; parameters in normal range.")

        lines.append(f"**{sym}:**")
        for rec in recs:
            lines.append(f"- {rec}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main_r1(argv: list[str] | None = None) -> int:
    """Phase R1: Market Structure Audit — multi-symbol runner."""
    from tools.parquet_pipeline.market_structure import (
        compute_distribution_stats,
        compute_persistence_stats,
        compute_regime_separability,
        compute_structural_breaks,
        simulate_stability_grid,
    )

    args = _parse_r1_args(argv)
    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tf_minutes = parse_tf_minutes(args.tf)

    # Resolve month filter
    months: list[str] | None = None
    if args.months_range:
        months = _parse_months_range(args.months_range)
    elif args.months:
        months = args.months

    print(f"[r1] symbols={args.symbols}  tf={args.tf}  months={months or 'all'}")

    all_results: dict[str, dict] = {}

    for symbol in args.symbols:
        print(f"\n[r1] ── {symbol} ──────────────────────────────────────────")

        # ── Discover + load ──────────────────────────────────────────────
        try:
            files = discover_files(data_dir, symbol, args.tf, months=months)
        except FileNotFoundError as e:
            print(f"[r1][{symbol}] SKIP: {e}")
            continue
        print(f"[r1][{symbol}] {len(files)} file(s) discovered")

        lf = pl.scan_parquet([str(f) for f in files])
        rename = {k: v for k, v in DEFAULT_RENAME.items() if k in lf.collect_schema()}
        if rename:
            lf = lf.rename(rename)

        stress_lf = compute_stress_v0(lf, window=args.window, burn_in=args.burn_in)
        stress_df = stress_lf.select(STRESS_OUTPUT_COLUMNS).collect()
        print(f"[r1][{symbol}] {len(stress_df)} bars after burn-in")

        sym_result: dict[str, dict] = {}

        # ── Block 1: Distributions ───────────────────────────────────────
        sym_result["distributions"] = compute_distribution_stats(stress_df)
        print(f"[r1][{symbol}] block1 distributions OK")

        # ── Block 2: Persistence (using proxy directionality states) ────
        # Label directionality for persistence analysis
        from tools.parquet_pipeline.market_structure import _proxy_labels
        labeled = _proxy_labels(stress_df).drop_nulls(["directionality"])
        sym_result["persistence"] = compute_persistence_stats(
            labeled, state_col="directionality"
        )
        print(f"[r1][{symbol}] block2 persistence OK")

        # ── Block 3: Separability ────────────────────────────────────────
        sym_result["separability"] = compute_regime_separability(stress_df)
        print(f"[r1][{symbol}] block3 separability OK")

        # ── Block 4: Structural breaks ───────────────────────────────────
        sym_result["structural_breaks"] = compute_structural_breaks(
            stress_df, rolling_window=args.window
        )
        print(f"[r1][{symbol}] block4 structural_breaks OK")

        # ── Block 5: Stability grid (optional) ──────────────────────────
        if args.include_grid:
            grid_df = simulate_stability_grid(
                stress_df,
                tf_minutes=tf_minutes,
            )
            grid_path = out_dir / f"stability_grid_{symbol}.parquet"
            grid_df.write_parquet(str(grid_path))
            # Store top-5 by switches_per_day ascending (most stable)
            sym_result["stability_grid_top5"] = grid_df.head(5).to_dicts()
            print(f"[r1][{symbol}] block5 stability_grid OK → {grid_path}")

        all_results[symbol] = sym_result

        # Per-symbol JSON
        sym_path = out_dir / f"market_structure_{symbol}.json"
        sym_path.write_text(
            json.dumps(sym_result, indent=2, default=str), encoding="utf-8"
        )
        print(f"[r1][{symbol}] → {sym_path}")

    if not all_results:
        print("[r1] No symbols processed — check data directory and month filters",
              file=sys.stderr)
        return 2

    # ── Cross-symbol report ──────────────────────────────────────────────
    report_md = _generate_r1_report(all_results, args.symbols, args.tf, months)
    report_path = out_dir / "market_structure_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\n[r1] report → {report_path}")

    # ── Manifest ─────────────────────────────────────────────────────────
    manifest = {
        "pipeline": "parquet_pipeline r1",
        "symbols": args.symbols,
        "symbols_processed": list(all_results.keys()),
        "tf": args.tf,
        "months": months,
        "window": args.window,
        "burn_in": args.burn_in,
        "include_grid": args.include_grid,
        "output_dir": str(out_dir),
        "files_written": [
            f"market_structure_{sym}.json" for sym in all_results
        ] + ["market_structure_report.md", "market_structure_manifest.json"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_dir / "market_structure_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(f"[r1] manifest → {manifest_path}")

    return 0


# ── R2: Regime Grid Calibration subcommand ──────────────────────────

def _parse_r2_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="parquet-pipeline r2",
        description="Phase R2: Regime Grid Calibration — parameter sweep for regime labels",
    )
    p.add_argument(
        "--symbols", nargs="+",
        default=["BTCUSDT", "ETHUSDT", "DOGEUSDT", "1000PEPEUSDT"],
        help="Symbols to analyse (default: all 4 main)",
    )
    p.add_argument("--tf", default="5m", help="Timeframe (default: 5m)")
    p.add_argument(
        "--months", nargs="+", default=None,
        help="Explicit month filter, e.g. 2023-06 2023-07",
    )
    p.add_argument(
        "--months-range", default=None,
        help="Month range shorthand, e.g. 2023-06:2024-03",
    )
    p.add_argument("--data-dir", default="data/processed")
    p.add_argument(
        "--output-dir", default="reports",
        help="Output directory for reports (default: reports/)",
    )
    p.add_argument(
        "--window", type=int, default=100,
        help="Rolling window for stress metrics (default: 100)",
    )
    p.add_argument(
        "--burn-in", type=int, default=120,
        help="Burn-in bars before emitting metrics (default: 120)",
    )
    return p.parse_args(argv)


def _generate_r2_report(
    results: dict,
    symbols: list[str],
    tf: str,
    months: list[str] | None,
) -> str:
    """Generate cross-symbol regime-grid markdown report."""
    lines = [
        "# Regime Grid Calibration Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Symbols:** {', '.join(symbols)}  ",
        f"**Timeframe:** {tf}  ",
        f"**Period:** {months[0] if months else 'all'} — {months[-1] if months else 'all'}  ",
        "",
        "---",
        "",
        "## 1. Top-5 Configurations (Cross-Symbol Average Score)",
        "",
    ]

    # Build cross-symbol average score table
    sym_grids = {
        sym: results[sym]["grid_df"]
        for sym in symbols
        if sym in results and results[sym].get("grid_df") is not None
    }

    if sym_grids:
        import polars as _pl
        # Concat with symbol column, average by params
        tagged = []
        for sym, gdf in sym_grids.items():
            tagged.append(gdf.with_columns(_pl.lit(sym).alias("_symbol")))
        combined = _pl.concat(tagged)
        param_cols = ["sma_short", "sma_long", "slope_threshold", "atr_window", "hysteresis_bars"]
        avg_score = (
            combined
            .group_by(param_cols)
            .agg(_pl.col("score").mean().round(4).alias("avg_score"))
            .sort("avg_score", descending=True)
            .head(5)
        )

        lines.append("| sma_short | sma_long | slope_thr | atr_win | hyst | avg_score |")
        lines.append("|-----------|----------|-----------|---------|------|-----------|")
        for row in avg_score.to_dicts():
            lines.append(
                f"| {row['sma_short']} "
                f"| {row['sma_long']} "
                f"| {row['slope_threshold']} "
                f"| {row['atr_window']} "
                f"| {row['hysteresis_bars']} "
                f"| {row['avg_score']:.4f} |"
            )
    else:
        lines.append("*No data available.*")

    lines += [
        "",
        "---",
        "",
        "## 2. Per-Symbol Top-3 Configurations",
        "",
    ]
    for sym in symbols:
        gdf = results.get(sym, {}).get("grid_df")
        if gdf is None:
            lines.append(f"### {sym}: *no data*\n")
            continue
        top3 = gdf.head(3)
        lines.append(f"### {sym}")
        lines.append("")
        lines.append("| # | sma_short | sma_long | slope_thr | atr_win | hyst | score | churn_spd | trend_ov | vol_ov | cov_ok |")
        lines.append("|---|-----------|----------|-----------|---------|------|-------|-----------|----------|--------|--------|")
        for i, row in enumerate(top3.to_dicts(), 1):
            lines.append(
                f"| {i} "
                f"| {row['sma_short']} "
                f"| {row['sma_long']} "
                f"| {row['slope_threshold']} "
                f"| {row['atr_window']} "
                f"| {row['hysteresis_bars']} "
                f"| {row['score']:.4f} "
                f"| {row['trend_switches_per_day']:.2f} "
                f"| {row['trend_return_overlap']:.3f} "
                f"| {row['vol_atr_overlap']:.3f} "
                f"| {'✓' if row['coverage_ok'] else '✗'} |"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "## 3. Parameter Sensitivity (Mean Score per Value)",
        "",
    ]
    if sym_grids:
        import polars as _pl
        tagged = []
        for sym, gdf in sym_grids.items():
            tagged.append(gdf.with_columns(_pl.lit(sym).alias("_symbol")))
        combined = _pl.concat(tagged)

        for param in ["sma_short", "sma_long", "slope_threshold", "atr_window", "hysteresis_bars"]:
            sens = (
                combined.group_by(param)
                .agg(_pl.col("score").mean().round(4).alias("mean_score"))
                .sort(param)
            )
            lines.append(f"**{param}:** " + "  |  ".join(
                f"{row[param]} → {row['mean_score']:.4f}"
                for row in sens.to_dicts()
            ))
            lines.append("")

    lines += [
        "---",
        "",
        "## 4. Coverage Check",
        "",
        "Configurations where `coverage_ok=False` (dominant state > 80% or any state < 1%):",
        "",
    ]
    for sym in symbols:
        gdf = results.get(sym, {}).get("grid_df")
        if gdf is None:
            continue
        bad = gdf.filter(~gdf["coverage_ok"])
        if len(bad) == 0:
            lines.append(f"**{sym}:** All {len(gdf)} configurations pass coverage check.")
        else:
            pct = round(100 * len(bad) / len(gdf), 1)
            lines.append(f"**{sym}:** {len(bad)}/{len(gdf)} ({pct}%) configurations fail coverage. "
                         f"min_state_pct range: "
                         f"[{bad['min_state_pct'].min():.4f}, {bad['min_state_pct'].max():.4f}]")
    lines.append("")

    lines += [
        "---",
        "",
        "## 5. Calibration Recommendations",
        "",
        "Recommended parameter ranges for `regime.yaml`:",
        "",
    ]
    if sym_grids:
        import polars as _pl
        tagged = []
        for sym, gdf in sym_grids.items():
            tagged.append(gdf.with_columns(_pl.lit(sym).alias("_symbol")))
        combined = _pl.concat(tagged)

        # Top-10% of configurations
        top_n = max(1, len(combined) // 10)
        top_rows = combined.sort("score", descending=True).head(top_n)

        lines.append("Based on top 10% of configurations by score:")
        lines.append("")
        lines.append("| Parameter | Min | Max | Mode |")
        lines.append("|-----------|-----|-----|------|")
        for param in ["sma_short", "sma_long", "slope_threshold", "atr_window", "hysteresis_bars"]:
            col = top_rows[param]
            lines.append(
                f"| {param} "
                f"| {col.min()} "
                f"| {col.max()} "
                f"| {col.mode()[0]} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main_r2(argv: list[str] | None = None) -> int:
    """Phase R2: Regime Grid Calibration — multi-symbol grid runner."""
    from tools.parquet_pipeline.regime_grid import run_regime_grid

    args = _parse_r2_args(argv)
    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tf_minutes = parse_tf_minutes(args.tf)

    # Resolve month filter
    months: list[str] | None = None
    if args.months_range:
        months = _parse_months_range(args.months_range)
    elif args.months:
        months = args.months

    print(f"[r2] symbols={args.symbols}  tf={args.tf}  months={months or 'all'}")

    all_results: dict[str, dict] = {}

    for symbol in args.symbols:
        print(f"\n[r2] ── {symbol} ──────────────────────────────────────────")

        # ── Discover + load ──────────────────────────────────────────────
        try:
            files = discover_files(data_dir, symbol, args.tf, months=months)
        except FileNotFoundError as e:
            print(f"[r2][{symbol}] SKIP: {e}")
            continue
        print(f"[r2][{symbol}] {len(files)} file(s) discovered")

        lf = pl.scan_parquet([str(f) for f in files])
        rename = {k: v for k, v in DEFAULT_RENAME.items() if k in lf.collect_schema()}
        if rename:
            lf = lf.rename(rename)

        stress_lf = compute_stress_v0(lf, window=args.window, burn_in=args.burn_in)
        stress_df = stress_lf.select(STRESS_OUTPUT_COLUMNS).collect()
        print(f"[r2][{symbol}] {len(stress_df)} bars after burn-in")

        # ── Run grid search ──────────────────────────────────────────────
        print(f"[r2][{symbol}] running regime grid (324 combos × metrics)...")
        grid_df = run_regime_grid(stress_df, tf_minutes=tf_minutes)
        print(f"[r2][{symbol}] {len(grid_df)} rows, top1 score={grid_df['score'][0]:.4f}")

        # ── Write per-symbol outputs ─────────────────────────────────────
        grid_parquet = out_dir / f"regime_grid_{symbol}.parquet"
        grid_df.write_parquet(str(grid_parquet))
        print(f"[r2][{symbol}] → {grid_parquet}")

        top20_path = out_dir / f"regime_grid_{symbol}_top20.json"
        top20_path.write_text(
            json.dumps(grid_df.head(20).to_dicts(), indent=2, default=str),
            encoding="utf-8",
        )
        print(f"[r2][{symbol}] → {top20_path}")

        all_results[symbol] = {
            "grid_df": grid_df,
            "top1": grid_df.head(1).to_dicts()[0],
            "n_bars": len(stress_df),
        }

    if not all_results:
        print("[r2] No symbols processed — check data directory and month filters",
              file=sys.stderr)
        return 2

    # ── Combined results ─────────────────────────────────────────────────
    combined_frames = [
        v["grid_df"].with_columns(pl.lit(sym).alias("symbol"))
        for sym, v in all_results.items()
    ]
    combined_df = pl.concat(combined_frames)
    combined_path = out_dir / "regime_grid_results.parquet"
    combined_df.write_parquet(str(combined_path))
    print(f"\n[r2] combined → {combined_path} ({len(combined_df)} rows)")

    # ── Markdown report ──────────────────────────────────────────────────
    report_md = _generate_r2_report(all_results, args.symbols, args.tf, months)
    report_path = out_dir / "regime_grid_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[r2] report → {report_path}")

    # ── Manifest ─────────────────────────────────────────────────────────
    manifest = {
        "pipeline": "parquet_pipeline r2",
        "symbols": args.symbols,
        "symbols_processed": list(all_results.keys()),
        "tf": args.tf,
        "months": months,
        "window": args.window,
        "burn_in": args.burn_in,
        "output_dir": str(out_dir),
        "n_grid_combos": len(all_results[next(iter(all_results))]["grid_df"]) if all_results else 0,
        "files_written": (
            [f"regime_grid_{sym}.parquet" for sym in all_results]
            + [f"regime_grid_{sym}_top20.json" for sym in all_results]
            + ["regime_grid_results.parquet", "regime_grid_report.md", "regime_grid_manifest.json"]
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_dir / "regime_grid_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(f"[r2] manifest → {manifest_path}")

    return 0


# ── Phase R3-B: Forward Separability ────────────────────────────────────────


def _parse_r3b_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m tools.parquet_pipeline r3b",
        description="Phase R3-B: forward separability analysis per regime label",
    )
    p.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    p.add_argument("--tf", default="5m")
    p.add_argument(
        "--months-range",
        default=None,
        help="Inclusive range YYYY-MM:YYYY-MM (uses _parse_months_range)",
    )
    p.add_argument("--months", nargs="+", default=None)
    p.add_argument("--data-dir", default="data/processed")
    p.add_argument("--output-dir", default="reports")
    p.add_argument("--window", type=int, default=100)
    p.add_argument("--burn-in", type=int, default=120)
    p.add_argument("--sma-short", type=int, default=48)
    p.add_argument("--sma-long", type=int, default=192)
    p.add_argument("--slope-threshold", type=float, default=0.002)
    p.add_argument("--atr-window", type=int, default=28)
    p.add_argument("--hysteresis-bars", type=int, default=3)
    p.add_argument("--horizons", nargs="+", type=int, default=[12, 24, 48])
    return p.parse_args(argv)


def _generate_r3b_report(
    results: dict,
    symbols: list[str],
    tf: str,
    months: list[str] | None,
    params: dict,
    horizons: list[int],
) -> str:
    lines: list[str] = []
    lines.append("# Forward Separability Report (Phase R3-B)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ")
    lines.append(f"**Symbols:** {', '.join(symbols)}  ")
    lines.append(f"**Timeframe:** {tf}  ")
    if months:
        lines.append(f"**Period:** {months[0]} -- {months[-1]}  ")
    lines.append(f"**Regime params:** sma={params['sma_short']}/{params['sma_long']}, "
                 f"slope_thr={params['slope_threshold']}, "
                 f"atr_win={params['atr_window']}, hyst={params['hysteresis_bars']}  ")
    lines.append(f"**Horizons (bars):** {horizons}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 1: Edge verdict summary ──────────────────────────────────
    lines.append("## 1. Edge Verdict Summary")
    lines.append("")
    lines.append("TREND_UP vs FLAT — Cohen's d and sign lift per horizon:")
    lines.append("")

    header = "| Symbol | Horizon | Cohen's d | Sign Lift | Sign Acc UP | Sign Acc FLAT | Verdict |"
    sep    = "|--------|---------|-----------|-----------|-------------|---------------|---------|"
    lines.append(header)
    lines.append(sep)
    for sym in symbols:
        res = results.get(sym)
        if res is None:
            continue
        for n in horizons:
            h_data = res.get("per_horizon", {}).get(n, {})
            cmp = h_data.get("UP_vs_FLAT", {})
            if not cmp:
                lines.append(f"| {sym} | {n} | n/a | n/a | n/a | n/a | n/a |")
                continue
            d = cmp.get("cohens_d", 0.0)
            lift = cmp.get("sign_lift", 0.0)
            sa_up = cmp.get("sign_accuracy_up", 0.0)
            sa_flat = cmp.get("sign_accuracy_flat", 0.0)
            ev = cmp.get("edge_verdict", "none")
            h_hours = round(n * res["tf_minutes"] / 60.0, 1)
            lines.append(
                f"| {sym} | {n}b ({h_hours}h) | {d:+.4f} | {lift:+.4f} | "
                f"{sa_up:.4f} | {sa_flat:.4f} | **{ev}** |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 2: TREND_DOWN vs FLAT ────────────────────────────────────
    lines.append("## 2. TREND_DOWN vs FLAT")
    lines.append("")
    header2 = "| Symbol | Horizon | Cohen's d | Sign Lift | Sign Acc DOWN | Sign Acc FLAT | Verdict |"
    sep2    = "|--------|---------|-----------|-----------|---------------|---------------|---------|"
    lines.append(header2)
    lines.append(sep2)
    for sym in symbols:
        res = results.get(sym)
        if res is None:
            continue
        for n in horizons:
            h_data = res.get("per_horizon", {}).get(n, {})
            cmp = h_data.get("DOWN_vs_FLAT", {})
            if not cmp:
                lines.append(f"| {sym} | {n} | n/a | n/a | n/a | n/a | n/a |")
                continue
            d = cmp.get("cohens_d", 0.0)
            lift = cmp.get("sign_lift", 0.0)
            sa_down = cmp.get("sign_accuracy_down", 0.0)
            sa_flat = cmp.get("sign_accuracy_flat", 0.0)
            ev = cmp.get("edge_verdict", "none")
            h_hours = round(n * res["tf_minutes"] / 60.0, 1)
            lines.append(
                f"| {sym} | {n}b ({h_hours}h) | {d:+.4f} | {lift:+.4f} | "
                f"{sa_down:.4f} | {sa_flat:.4f} | **{ev}** |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 3: Label distribution per symbol ──────────────────────────
    lines.append("## 3. Label Distribution")
    lines.append("")
    for sym in symbols:
        res = results.get(sym)
        if res is None:
            continue
        dist = res.get("label_distribution", {})
        lines.append(f"**{sym}:** ", )
        parts = [f"{lbl}={v['pct']:.1f}%" for lbl, v in dist.items()]
        lines[-1] += "  ".join(parts)
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Section 4: Vol interaction (top combos) ────────────────────────────
    lines.append("## 4. Vol Interaction (sign_accuracy by trend x vol, first horizon)")
    lines.append("")
    first_n = horizons[0] if horizons else 12
    for sym in symbols:
        res = results.get(sym)
        if res is None:
            continue
        matrix = res.get("vol_interaction", {}).get(first_n, {})
        if not matrix:
            continue
        lines.append(f"### {sym} @ horizon={first_n}b")
        lines.append("")
        lines.append("| Combination | n | Sign Acc | Mean Fwd Ret |")
        lines.append("|-------------|---|----------|--------------|")
        rows_sorted = sorted(
            matrix.items(),
            key=lambda kv: (kv[1].get("sign_accuracy") or 0.0),
            reverse=True,
        )
        for combo, stats in rows_sorted[:9]:
            n_c = stats.get("n", 0)
            sa = stats.get("sign_accuracy")
            mu = stats.get("mean")
            sa_s = f"{sa:.4f}" if sa is not None else "n/a"
            mu_s = f"{mu:.6f}" if mu is not None else "n/a"
            lines.append(f"| {combo} | {n_c} | {sa_s} | {mu_s} |")
        lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def main_r3b(argv: list[str] | None = None) -> int:
    from tools.parquet_pipeline.forward_separability import (
        run_forward_separability,
        flatten_separability_to_df,
    )

    args = _parse_r3b_args(argv)
    tf_minutes = parse_tf_minutes(args.tf)
    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = PROJECT_ROOT / args.data_dir

    months: list[str] | None = None
    if args.months_range:
        months = _parse_months_range(args.months_range)
    elif args.months:
        months = args.months

    params = {
        "sma_short": args.sma_short,
        "sma_long": args.sma_long,
        "slope_threshold": args.slope_threshold,
        "atr_window": args.atr_window,
        "hysteresis_bars": args.hysteresis_bars,
    }

    all_results: dict = {}
    all_flat_dfs: list = []

    for symbol in args.symbols:
        print(f"[r3b] {symbol} ...")
        parquet_files = discover_files(
            data_dir, symbol=symbol, tf=args.tf, months=months
        )
        if not parquet_files:
            print(f"[r3b] {symbol}: no parquet files found, skipping")
            continue

        frames: list = []
        for pf in parquet_files:
            raw = pl.read_parquet(pf).rename({
                k: v for k, v in DEFAULT_RENAME.items()
                if k in pl.read_parquet(pf).columns
            })
            frames.append(raw)
        raw_df = pl.concat(frames).sort("timestamp")

        # Compute stress_v0 to get bar_range (and other stress columns)
        stress_df = compute_stress_v0(
            raw_df.lazy(),
            window=args.window,
            burn_in=args.burn_in,
        ).collect()

        # Run forward separability
        result = run_forward_separability(
            stress_df,
            horizons=args.horizons,
            tf_minutes=tf_minutes,
            **params,
        )
        all_results[symbol] = result

        # Write per-symbol parquet (flat)
        flat_df = flatten_separability_to_df(result, symbol)
        all_flat_dfs.append(flat_df)
        sym_path = out_dir / f"r3_forward_separability_{symbol}.parquet"
        flat_df.write_parquet(sym_path)
        print(f"[r3b] {symbol} -> {sym_path}")

    if not all_results:
        print("[r3b] no symbols processed", file=sys.stderr)
        return 1

    # Combined parquet
    if all_flat_dfs:
        combined = pl.concat(all_flat_dfs)
        combined_path = out_dir / "r3_forward_separability_results.parquet"
        combined.write_parquet(combined_path)
        print(f"[r3b] combined -> {combined_path}")

    # Markdown report
    report_md = _generate_r3b_report(
        all_results, args.symbols, args.tf, months, params, args.horizons
    )
    report_path = out_dir / "r3_forward_separability_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[r3b] report -> {report_path}")

    # Manifest
    manifest = {
        "pipeline": "parquet_pipeline r3b",
        "symbols": args.symbols,
        "symbols_processed": list(all_results.keys()),
        "tf": args.tf,
        "months": months,
        "params": params,
        "horizons": args.horizons,
        "output_dir": str(out_dir),
        "files_written": (
            [f"r3_forward_separability_{sym}.parquet" for sym in all_results]
            + ["r3_forward_separability_results.parquet",
               "r3_forward_separability_report.md",
               "r3_forward_separability_manifest.json"]
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_dir / "r3_forward_separability_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(f"[r3b] manifest -> {manifest_path}")

    return 0


# ── Phase R3-A-lite: Market Policy Tables ────────────────────────────────────


def _parse_r3a_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m tools.parquet_pipeline r3a",
        description="Phase R3-A-lite: edge tables + Aurora/MR policy derivation",
    )
    p.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    p.add_argument("--tf", default="5m")
    p.add_argument("--months-range", default=None)
    p.add_argument("--months", nargs="+", default=None)
    p.add_argument("--data-dir", default="data/processed")
    p.add_argument("--output-dir", default="reports")
    p.add_argument("--window", type=int, default=100)
    p.add_argument("--burn-in", type=int, default=120)
    p.add_argument("--sma-short", type=int, default=48)
    p.add_argument("--sma-long", type=int, default=192)
    p.add_argument("--slope-threshold", type=float, default=0.002)
    p.add_argument("--atr-window", type=int, default=28)
    p.add_argument("--hysteresis-bars", type=int, default=3)
    p.add_argument("--horizons", nargs="+", type=int, default=[12, 24, 48])
    p.add_argument("--with-stress", action="store_true",
                   help="Run A4 actuator to attach stress state (slower)")
    return p.parse_args(argv)


def _generate_r3a_report(
    results: dict,
    symbols: list[str],
    tf: str,
    months: list[str] | None,
    params: dict,
    horizons: list[int],
) -> str:
    lines: list[str] = []
    lines.append("# Market Policy Tables Report (Phase R3-A-lite)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ")
    lines.append(f"**Symbols:** {', '.join(symbols)}  ")
    lines.append(f"**Timeframe:** {tf}  ")
    if months:
        lines.append(f"**Period:** {months[0]} -- {months[-1]}  ")
    lines.append(f"**Regime params:** sma={params['sma_short']}/{params['sma_long']}, "
                 f"slope_thr={params['slope_threshold']}, "
                 f"atr_win={params['atr_window']}, hyst={params['hysteresis_bars']}  ")
    lines.append(f"**Horizons (bars):** {horizons}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    for sym in symbols:
        res = results.get(sym)
        if res is None:
            continue

        lines.append(f"## {sym}")
        lines.append("")

        aurora_df = res.get("aurora_policy")
        if aurora_df is not None and len(aurora_df) > 0:
            lines.append("### Aurora Sizing Policy (primary_horizon=24b)")
            lines.append("")
            lines.append("| Trend | Vol | Stress | n | Mean Uplift | Tail Ratio | Size Mult | Signal |")
            lines.append("|-------|-----|--------|---|-------------|------------|-----------|--------|")
            for row in aurora_df.iter_rows(named=True):
                lines.append(
                    f"| {row['trend_label']} | {row['vol_label']} | {row['stress_state']} "
                    f"| {row['n']} | {row['mean_uplift']:+.6f} | {row['tail_ratio']:.3f} "
                    f"| **{row['sizing_mult']:.3f}** | {row['signal']} |"
                )
            lines.append("")

        mr_df = res.get("mr_policy")
        if mr_df is not None and len(mr_df) > 0:
            lines.append("### Mean-Reversion Entry Policy (primary_horizon=12b)")
            lines.append("")
            lines.append("| Trend | Vol | Stress | n | Sign Acc | Delta | CVaR-5% | Policy |")
            lines.append("|-------|-----|--------|---|----------|-------|---------|--------|")
            for row in mr_df.iter_rows(named=True):
                cvar_s = f"{row['cvar5']:.6f}" if row.get("cvar5") is not None else "n/a"
                lines.append(
                    f"| {row['trend_label']} | {row['vol_label']} | {row['stress_state']} "
                    f"| {row['n']} | {row['sign_acc']:.4f} | {row['sign_acc_delta']:+.4f} "
                    f"| {cvar_s} | **{row['entry_policy']}** |"
                )
            lines.append("")

        edge_df = res.get("edge_df")
        if edge_df is not None:
            subset = edge_df.filter(pl.col("horizon_bars") == 24)
            if len(subset) > 0:
                lines.append("### Edge Table @ 24b (sorted by mean_fwd_ret desc)")
                lines.append("")
                lines.append("| Trend | Vol | Stress | n | Mean | p05 | p50 | p95 | Sign Acc | CVaR-5% |")
                lines.append("|-------|-----|--------|---|------|-----|-----|-----|----------|---------|")
                for row in subset.sort("mean_fwd_ret", descending=True).iter_rows(named=True):
                    mu = row.get("mean_fwd_ret")
                    mu_s = f"{mu:.6f}" if mu is not None else "n/a"
                    p05_s = f"{row['p05']:.6f}" if row.get("p05") is not None else "n/a"
                    p50_s = f"{row['p50']:.6f}" if row.get("p50") is not None else "n/a"
                    p95_s = f"{row['p95']:.6f}" if row.get("p95") is not None else "n/a"
                    sa_s = f"{row['sign_acc']:.4f}" if row.get("sign_acc") is not None else "n/a"
                    cv_s = f"{row['cvar5']:.6f}" if row.get("cvar5") is not None else "n/a"
                    lines.append(
                        f"| {row['trend_label']} | {row['vol_label']} | {row['stress_state']} "
                        f"| {row['n']} | {mu_s} | {p05_s} | {p50_s} | {p95_s} | {sa_s} | {cv_s} |"
                    )
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main_r3a(argv: list[str] | None = None) -> int:
    from tools.parquet_pipeline.policy_tables import (
        compute_edge_table,
        derive_trend_policy,
        derive_mr_policy,
    )

    args = _parse_r3a_args(argv)
    tf_minutes = parse_tf_minutes(args.tf)
    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = PROJECT_ROOT / args.data_dir

    months: list[str] | None = None
    if args.months_range:
        months = _parse_months_range(args.months_range)
    elif args.months:
        months = args.months

    params = {
        "sma_short": args.sma_short,
        "sma_long": args.sma_long,
        "slope_threshold": args.slope_threshold,
        "atr_window": args.atr_window,
        "hysteresis_bars": args.hysteresis_bars,
    }

    all_results: dict = {}
    all_edge_dfs: list = []

    for symbol in args.symbols:
        print(f"[r3a] {symbol} ...")
        parquet_files = discover_files(
            data_dir, symbol=symbol, tf=args.tf, months=months
        )
        if not parquet_files:
            print(f"[r3a] {symbol}: no parquet files found, skipping")
            continue

        frames: list = []
        for pf in parquet_files:
            raw = pl.read_parquet(pf).rename({
                k: v for k, v in DEFAULT_RENAME.items()
                if k in pl.read_parquet(pf).columns
            })
            frames.append(raw)
        raw_df = pl.concat(frames).sort("timestamp")

        stress_df = compute_stress_v0(
            raw_df.lazy(),
            window=args.window,
            burn_in=args.burn_in,
        ).collect()

        stress_col: str | None = None
        if args.with_stress:
            try:
                from tools.parquet_pipeline.actuator_rules import ActuatorConfig, run_actuator
                from tools.parquet_pipeline.aggregation import compute_stress_level
                cfg = ActuatorConfig(
                    enter_stress=0.60,
                    exit_stress=0.40,
                    enter_extreme=0.85,
                    exit_extreme=0.70,
                    consecutive_bars_enter=6,
                    consecutive_bars_exit=5,
                    min_duration_bars=15,
                    switch_window_bars=200,
                    max_switches_per_window=2,
                )
                sl_df = compute_stress_level(
                    stress_df.lazy(), method="weighted_vote",
                    weights={"atr": 0.30, "vol": 0.30, "gap": 0.20, "range": 0.20},
                    thresholds={
                        "atr_sigma": 2.0, "vol_sigma": 2.0,
                        "gap_sigma": 3.0, "range_sigma": 2.5,
                    },
                    k=None,
                ).collect()
                result_act = run_actuator(sl_df["stress_level"].to_list(), cfg)
                stress_df = stress_df.with_columns(
                    pl.Series("state", result_act.states)
                )
                stress_col = "state"
                print(f"[r3a] {symbol}: stress attached ({result_act.total_switches} switches)")
            except Exception as exc:
                print(f"[r3a] {symbol}: stress attachment failed ({exc}), using NORMAL")

        edge_df = compute_edge_table(
            stress_df,
            horizons=args.horizons,
            tf_minutes=tf_minutes,
            stress_col=stress_col,
            **params,
        )
        edge_df = edge_df.with_columns(pl.lit(symbol).alias("symbol"))
        all_edge_dfs.append(edge_df)

        aurora_df = derive_trend_policy(edge_df, primary_horizon=24)
        mr_df = derive_mr_policy(edge_df, primary_horizon=12)

        all_results[symbol] = {
            "edge_df": edge_df,
            "aurora_policy": aurora_df,
            "mr_policy": mr_df,
        }

        edge_path = out_dir / f"r3a_edge_{symbol}.parquet"
        edge_df.write_parquet(edge_path)
        print(f"[r3a] {symbol} edge -> {edge_path}")
        if len(aurora_df) > 0:
            aurora_df.write_parquet(out_dir / f"r3a_aurora_policy_{symbol}.parquet")
        if len(mr_df) > 0:
            mr_df.write_parquet(out_dir / f"r3a_mr_policy_{symbol}.parquet")

    if not all_results:
        print("[r3a] no symbols processed", file=sys.stderr)
        return 1

    if all_edge_dfs:
        combined = pl.concat(all_edge_dfs)
        combined_path = out_dir / "r3a_edge_results.parquet"
        combined.write_parquet(combined_path)
        print(f"[r3a] combined edge -> {combined_path}")

    report_md = _generate_r3a_report(
        all_results, args.symbols, args.tf, months, params, args.horizons
    )
    report_path = out_dir / "r3a_market_policy_tables.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[r3a] report -> {report_path}")

    manifest = {
        "pipeline": "parquet_pipeline r3a",
        "symbols": args.symbols,
        "symbols_processed": list(all_results.keys()),
        "tf": args.tf,
        "months": months,
        "params": params,
        "horizons": args.horizons,
        "with_stress": args.with_stress,
        "output_dir": str(out_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_dir / "r3a_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(f"[r3a] manifest -> {manifest_path}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "r1":
        try:
            raise SystemExit(main_r1(sys.argv[2:]))
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    elif len(sys.argv) > 1 and sys.argv[1] == "r2":
        try:
            raise SystemExit(main_r2(sys.argv[2:]))
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    elif len(sys.argv) > 1 and sys.argv[1] == "r3b":
        try:
            raise SystemExit(main_r3b(sys.argv[2:]))
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    elif len(sys.argv) > 1 and sys.argv[1] == "r3a":
        try:
            raise SystemExit(main_r3a(sys.argv[2:]))
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    else:
        try:
            raise SystemExit(main())
        except PipelineError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
