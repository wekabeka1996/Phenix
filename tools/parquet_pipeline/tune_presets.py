"""Preset grid search for stress actuator hysteresis parameters.

Runs 6 ActuatorConfig presets against real OHLCV data (same z-scores for all)
and produces a single ``stress_tuning_report.md`` showing metrics per preset
plus a winner selection.

Usage::

    python -m tools.parquet_pipeline.tune_presets
    python -m tools.parquet_pipeline.tune_presets --symbol BTCUSDT --tf 5m --months 2024-01 2024-02 2024-03
    python -m tools.parquet_pipeline.tune_presets --output reports/stress_tuning_report.md
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, NamedTuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl  # noqa: E402

from tools.parquet_pipeline.actuator_rules import ActuatorConfig, run_actuator  # noqa: E402
from tools.parquet_pipeline.aggregation import compute_stress_level  # noqa: E402
from tools.parquet_pipeline.discovery import DEFAULT_RENAME, discover_files, parse_tf_minutes  # noqa: E402
from tools.parquet_pipeline.stress import STRESS_OUTPUT_COLUMNS, compute_stress_v0  # noqa: E402


# ── Thresholds / weights (shared across all presets) ────────────────

_THRESHOLDS = {
    "atr_sigma": 2.0,
    "vol_sigma": 2.0,
    "gap_sigma": 3.0,
    "range_sigma": 2.5,
    "volume_sigma": 0.0,
    "spread_sigma": 0.0,
    "depth_drop_pct": 0.0,
}

_WEIGHTS = {"atr": 0.30, "vol": 0.30, "gap": 0.20, "range": 0.20}


# ── Preset definitions ───────────────────────────────────────────────

@dataclass
class Preset:
    name: str
    description: str
    cfg: ActuatorConfig


def _presets() -> List[Preset]:
    return [
        Preset(
            name="A0",
            description="Baseline (current regime.yaml defaults)",
            cfg=ActuatorConfig(
                enter_stress=0.60, exit_stress=0.40,
                enter_extreme=0.85, exit_extreme=0.70,
                consecutive_bars_enter=3, consecutive_bars_exit=2,
                min_duration_bars=5,
                switch_window_bars=50, max_switches_per_window=3,
            ),
        ),
        Preset(
            name="A1",
            description="Moderate-1: longer confirmation, longer hold",
            cfg=ActuatorConfig(
                enter_stress=0.60, exit_stress=0.40,
                enter_extreme=0.85, exit_extreme=0.70,
                consecutive_bars_enter=5, consecutive_bars_exit=3,
                min_duration_bars=10,
                switch_window_bars=50, max_switches_per_window=3,
            ),
        ),
        Preset(
            name="A2",
            description="Moderate-2: tighter thresholds + longer confirmation",
            cfg=ActuatorConfig(
                enter_stress=0.65, exit_stress=0.35,
                enter_extreme=0.85, exit_extreme=0.70,
                consecutive_bars_enter=5, consecutive_bars_exit=3,
                min_duration_bars=10,
                switch_window_bars=50, max_switches_per_window=3,
            ),
        ),
        Preset(
            name="A3",
            description="Moderate-3: more inertia",
            cfg=ActuatorConfig(
                enter_stress=0.65, exit_stress=0.35,
                enter_extreme=0.85, exit_extreme=0.70,
                consecutive_bars_enter=6, consecutive_bars_exit=4,
                min_duration_bars=12,
                switch_window_bars=50, max_switches_per_window=3,
            ),
        ),
        Preset(
            name="A4",
            description="Anti-flip hard: wide CB window, strict limits",
            cfg=ActuatorConfig(
                enter_stress=0.60, exit_stress=0.40,
                enter_extreme=0.85, exit_extreme=0.70,
                consecutive_bars_enter=6, consecutive_bars_exit=4,
                min_duration_bars=15,
                switch_window_bars=200, max_switches_per_window=2,
            ),
        ),
        Preset(
            name="A5",
            description="Moderate-5: soft thresholds, high inertia",
            cfg=ActuatorConfig(
                enter_stress=0.62, exit_stress=0.38,
                enter_extreme=0.85, exit_extreme=0.70,
                consecutive_bars_enter=6, consecutive_bars_exit=4,
                min_duration_bars=12,
                switch_window_bars=100, max_switches_per_window=3,
            ),
        ),
    ]


# ── Metrics collection ───────────────────────────────────────────────

@dataclass
class PresetResult:
    preset: Preset
    total_bars: int
    switches: int
    switches_per_day: float
    pct_normal: float
    pct_stress: float
    pct_extreme: float
    longest_run_bars: int
    longest_run_state: str
    top_switch_rows: List[int]  # row indices in stress_df


def _collect_result(preset: Preset, stress_df: pl.DataFrame, total_days: float) -> PresetResult:
    sl_list = stress_df["stress_level"].to_list()
    result = run_actuator(sl_list, preset.cfg)

    n = len(result.states)
    switches = result.total_switches
    switches_per_day = switches / total_days if total_days > 0 else 0.0

    pct_normal = sum(1 for s in result.states if s == "NORMAL") / n * 100
    pct_stress = sum(1 for s in result.states if s == "STRESS") / n * 100
    pct_extreme = sum(1 for s in result.states if s == "EXTREME") / n * 100

    # Longest stable run
    longest = 0
    longest_state = ""
    run_len = 1
    for i in range(1, n):
        if result.states[i] == result.states[i - 1]:
            run_len += 1
        else:
            if run_len > longest:
                longest = run_len
                longest_state = result.states[i - 1]
            run_len = 1
    if run_len > longest:
        longest = run_len
        longest_state = result.states[-1] if result.states else ""

    # Switch row indices (first 10)
    top_rows: list[int] = []
    prev = 0
    for i, c in enumerate(result.switches_cumulative):
        if c > prev:
            top_rows.append(i)
        prev = c
    top_rows = top_rows[:10]

    return PresetResult(
        preset=preset,
        total_bars=n,
        switches=switches,
        switches_per_day=switches_per_day,
        pct_normal=pct_normal,
        pct_stress=pct_stress,
        pct_extreme=pct_extreme,
        longest_run_bars=longest,
        longest_run_state=longest_state,
        top_switch_rows=top_rows,
    )


# ── Report generation ────────────────────────────────────────────────

def _format_top_switches(pr: PresetResult, stress_df: pl.DataFrame) -> str:
    if not pr.top_switch_rows:
        return "_No switches._\n"
    z_cols = ["z_atr", "z_realized_vol", "z_gap", "z_bar_range"]
    rows_available = stress_df.height
    lines = ["| # | Timestamp (UTC) | stress_level | z_atr | z_vol | z_gap | z_range |"]
    lines.append("|---|-----------------|-------------|-------|-------|-------|---------|")
    for idx_num, row_idx in enumerate(pr.top_switch_rows, start=1):
        if row_idx >= rows_available:
            continue
        row = stress_df.row(row_idx, named=True)
        ts = str(row.get("timestamp", "?"))
        sl = row.get("stress_level", 0.0)
        z_atr = row.get("z_atr", 0.0)
        z_vol = row.get("z_realized_vol", 0.0)
        z_gap = row.get("z_gap", 0.0)
        z_rng = row.get("z_bar_range", 0.0)
        lines.append(
            f"| {idx_num} | {ts} | {sl:.3f} | {z_atr:.2f} | {z_vol:.2f} | {z_gap:.2f} | {z_rng:.2f} |"
        )
    return "\n".join(lines) + "\n"


def _select_winner(results: List[PresetResult]) -> PresetResult:
    """
    Primary: switches_per_day <= 1.5
    Secondary: pct_stress between 5% and 20%  (gate active but not dominant)
    Tiebreak: among equal-quality candidates, fewest switches then longest run.

    Logic:
    1. Candidates that satisfy BOTH primary + secondary → pick fewest switches.
    2. If none satisfy both, find closest preset by composite score:
       - distance from 1.5/day (primary) + penalty for STRESS% out of [5,20]
       This avoids selecting a "decorative" low-switch config.
    """
    # Best: meet both criteria
    both_ok = [
        r for r in results
        if r.switches_per_day <= 1.5 and 5.0 <= r.pct_stress <= 20.0
    ]
    if both_ok:
        both_ok.sort(key=lambda r: (r.switches, -r.longest_run_bars))
        return both_ok[0]

    # Otherwise: score by (overshoot of switches/day from 1.5) +
    #            (distance of STRESS% from midpoint of [5,20] = 12.5%)
    def _score(r: PresetResult) -> float:
        spd_penalty = max(0.0, r.switches_per_day - 1.5)
        stress_mid = 12.5
        stress_dist = abs(r.pct_stress - stress_mid) / stress_mid
        return spd_penalty + stress_dist

    return min(results, key=_score)


def generate_report(
    presets: List[Preset],
    stress_df: pl.DataFrame,
    total_days: float,
    symbol: str,
    tf: str,
    months: Optional[List[str]],
    window: int,
    burn_in: int,
) -> str:
    results = [_collect_result(p, stress_df, total_days) for p in presets]
    winner = _select_winner(results)

    lines = [
        "# Stress Actuator Preset Tuning Report",
        "",
        f"**Symbol:** {symbol}  ",
        f"**Timeframe:** {tf}  ",
        f"**Months:** {', '.join(months) if months else 'all'}  ",
        f"**Bars:** {len(stress_df):,}  ",
        f"**Period:** {total_days:.1f} days  ",
        f"**Window:** {window}  |  **Burn-in:** {burn_in}  ",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Comparison Table",
        "",
        "| Preset | Description | Switches | /day | NORMAL% | STRESS% | EXTREME% | Longest run |",
        "|--------|-------------|----------|------|---------|---------|----------|-------------|",
    ]

    for r in results:
        winner_mark = " 🏆" if r.preset.name == winner.preset.name else ""
        lines.append(
            f"| **{r.preset.name}**{winner_mark} | {r.preset.description} "
            f"| {r.switches} | {r.switches_per_day:.2f} "
            f"| {r.pct_normal:.1f}% | {r.pct_stress:.1f}% | {r.pct_extreme:.1f}% "
            f"| {r.longest_run_bars} bars ({r.longest_run_state}) |"
        )

    lines += [
        "",
        f"**Winner: {winner.preset.name}** — {winner.preset.description}",
        "",
        f"- Switches/day: **{winner.switches_per_day:.2f}** (target ≤1.5)",
        f"- STRESS%: **{winner.pct_stress:.1f}%** (target 5–20%)",
        f"- Longest stable run: **{winner.longest_run_bars} bars** ({winner.longest_run_state})",
        "",
        "---",
        "",
        "## Per-Preset Details",
        "",
    ]

    for r in results:
        winner_mark = " ← WINNER" if r.preset.name == winner.preset.name else ""
        lines += [
            f"### {r.preset.name}{winner_mark}: {r.preset.description}",
            "",
            f"- enter_stress={r.preset.cfg.enter_stress} / exit_stress={r.preset.cfg.exit_stress}",
            f"- consecutive_enter={r.preset.cfg.consecutive_bars_enter} / consecutive_exit={r.preset.cfg.consecutive_bars_exit}",
            f"- min_duration={r.preset.cfg.min_duration_bars} bars",
            f"- switch_window={r.preset.cfg.switch_window_bars} / max_switches={r.preset.cfg.max_switches_per_window}",
            "",
            f"**Switches:** {r.switches} ({r.switches_per_day:.2f}/day)  ",
            f"**NORMAL:** {r.pct_normal:.1f}%  |  **STRESS:** {r.pct_stress:.1f}%  |  **EXTREME:** {r.pct_extreme:.1f}%  ",
            f"**Longest stable run:** {r.longest_run_bars} bars ({r.longest_run_state})  ",
            "",
            f"**Top-{len(r.top_switch_rows)} switch events:**",
            "",
            _format_top_switches(r, stress_df),
        ]

    lines += [
        "---",
        "",
        "## Selection Criteria",
        "",
        "1. **Primary:** switches_per_day ≤ 1.5",
        "2. **Secondary:** STRESS% in [5%, 20%] (gate active but not dominant)",
        "3. **Tiebreak:** fewest total switches, then longest stable run",
        "",
        "## Winner Config (copy into regime.yaml state_mapping)",
        "",
        "```yaml",
        "state_mapping:",
        f"  enter_stress: {winner.preset.cfg.enter_stress}",
        f"  exit_stress: {winner.preset.cfg.exit_stress}",
        f"  enter_extreme: {winner.preset.cfg.enter_extreme}",
        f"  exit_extreme: {winner.preset.cfg.exit_extreme}",
        f"  consecutive_bars_enter: {winner.preset.cfg.consecutive_bars_enter}",
        f"  consecutive_bars_exit: {winner.preset.cfg.consecutive_bars_exit}",
        f"  min_duration_bars: {winner.preset.cfg.min_duration_bars}",
        f"  switch_window_bars: {winner.preset.cfg.switch_window_bars}",
        f"  max_switches_per_window: {winner.preset.cfg.max_switches_per_window}",
        "  circuit_breaker_mode: halt",
        "```",
        "",
    ]

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tune-presets",
        description="Grid-search ActuatorConfig presets, pick winner, write report.",
    )
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--tf", default="5m")
    p.add_argument("--months", nargs="+", default=["2024-01", "2024-02", "2024-03"])
    p.add_argument("--data-dir", default="data/processed")
    p.add_argument("--window", type=int, default=100)
    p.add_argument("--burn-in", type=int, default=120)
    p.add_argument(
        "--output",
        default="reports/stress_tuning_report.md",
        help="Output markdown path",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    data_dir = Path(args.data_dir)

    # ── Discover files ────────────────────────────────────────────────
    print(f"[discover] {args.symbol}/{args.tf} months={args.months}")
    try:
        files = discover_files(data_dir, args.symbol, args.tf, months=args.months)
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    print(f"[discover] {len(files)} file(s)")

    # ── Compute stress metrics (once, shared) ─────────────────────────
    print(f"[stress] window={args.window} burn_in={args.burn_in}...")
    lf = pl.scan_parquet([str(f) for f in files])
    rename = {k: v for k, v in DEFAULT_RENAME.items() if k in lf.collect_schema()}
    if rename:
        lf = lf.rename(rename)

    stress_lf = compute_stress_v0(lf, window=args.window, burn_in=args.burn_in)
    stress_df = stress_lf.select(STRESS_OUTPUT_COLUMNS).collect()
    print(f"[stress] {len(stress_df):,} rows")

    # ── Compute stress_level (aggregation, once, shared) ─────────────
    print("[agg] computing stress_level...")
    sl_lf = compute_stress_level(
        stress_df.lazy(),
        method="weighted_vote",
        weights=_WEIGHTS,
        thresholds=_THRESHOLDS,
    )
    stress_df = sl_lf.collect()

    # ── Compute total_days from timestamp range ───────────────────────
    ts_col = stress_df["timestamp"]
    ts_min = ts_col.min()
    ts_max = ts_col.max()
    total_days = (ts_max - ts_min).total_seconds() / 86400 if ts_min and ts_max else 91.0
    print(f"[info] {ts_min} to {ts_max} ({total_days:.1f} days)")

    # ── Run grid ──────────────────────────────────────────────────────
    presets = _presets()
    print(f"[grid] running {len(presets)} presets...")
    for p in presets:
        from tools.parquet_pipeline.actuator_rules import run_actuator as _ra
        r = _ra(stress_df["stress_level"].to_list(), p.cfg)
        spd = r.total_switches / total_days if total_days > 0 else 0
        print(f"  {p.name}: {r.total_switches} switches ({spd:.2f}/day)")

    # ── Generate report ───────────────────────────────────────────────
    report = generate_report(
        presets=presets,
        stress_df=stress_df,
        total_days=total_days,
        symbol=args.symbol,
        tf=args.tf,
        months=args.months,
        window=args.window,
        burn_in=args.burn_in,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"[report] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
