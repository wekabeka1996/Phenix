"""Multi-symbol preset portability check.

Runs a single ActuatorConfig preset against multiple symbols and produces
a cross-symbol report to verify the preset generalises beyond the training
symbol (BTCUSDT).

Usage::

    python tools/parquet_pipeline/validate_preset.py
    python tools/parquet_pipeline/validate_preset.py --preset A4 --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT
    python tools/parquet_pipeline/validate_preset.py --output reports/my_report.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl  # noqa: E402

from tools.parquet_pipeline.actuator_rules import run_actuator  # noqa: E402
from tools.parquet_pipeline.aggregation import compute_stress_level  # noqa: E402
from tools.parquet_pipeline.discovery import DEFAULT_RENAME, discover_files  # noqa: E402
from tools.parquet_pipeline.stress import STRESS_OUTPUT_COLUMNS, compute_stress_v0  # noqa: E402
from tools.parquet_pipeline.tune_presets import _presets  # noqa: E402


# ── Acceptance thresholds ────────────────────────────────────────────

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

# Portability verdict thresholds
_PASS_SPD_MAX = 3.0      # switches/day <= this
_PASS_STRESS_MIN = 2.0   # STRESS% >= this (not decorative)
_PASS_STRESS_MAX = 35.0  # STRESS% <= this (not a panicker)
_WARN_SPD_MAX = 5.0      # warn if between 3 and 5
_WARN_STRESS_MIN = 1.0   # warn if STRESS% between 1 and 2


def _verdict(spd: float, pct_stress: float) -> str:
    if spd > _WARN_SPD_MAX or pct_stress < _WARN_STRESS_MIN or pct_stress > _PASS_STRESS_MAX:
        return "FAIL"
    if spd > _PASS_SPD_MAX or pct_stress < _PASS_STRESS_MIN:
        return "WARN"
    return "PASS"


# ── Per-symbol result ────────────────────────────────────────────────

class SymbolResult:
    def __init__(
        self,
        symbol: str,
        bars: int,
        total_days: float,
        switches: int,
        pct_normal: float,
        pct_stress: float,
        pct_extreme: float,
        longest_run_bars: int,
        longest_run_state: str,
        top_rows: List[int],
        stress_df: pl.DataFrame,
    ) -> None:
        self.symbol = symbol
        self.bars = bars
        self.total_days = total_days
        self.switches = switches
        self.switches_per_day = switches / total_days if total_days > 0 else 0.0
        self.pct_normal = pct_normal
        self.pct_stress = pct_stress
        self.pct_extreme = pct_extreme
        self.longest_run_bars = longest_run_bars
        self.longest_run_state = longest_run_state
        self.top_rows = top_rows
        self.stress_df = stress_df
        self.verdict = _verdict(self.switches_per_day, self.pct_stress)


def _run_symbol(
    symbol: str,
    tf: str,
    months: List[str],
    data_dir: Path,
    preset,
    window: int,
    burn_in: int,
) -> Optional[SymbolResult]:
    try:
        files = discover_files(data_dir, symbol, tf, months=months)
    except FileNotFoundError as exc:
        print(f"  [skip] {symbol}: {exc}", file=sys.stderr)
        return None

    lf = pl.scan_parquet([str(f) for f in files])
    rename = {k: v for k, v in DEFAULT_RENAME.items() if k in lf.collect_schema()}
    if rename:
        lf = lf.rename(rename)

    stress_lf = compute_stress_v0(lf, window=window, burn_in=burn_in)
    stress_df = stress_lf.select(STRESS_OUTPUT_COLUMNS).collect()

    # Aggregation
    sl_lf = compute_stress_level(
        stress_df.lazy(),
        method="weighted_vote",
        weights=_WEIGHTS,
        thresholds=_THRESHOLDS,
    )
    stress_df = sl_lf.collect()

    # Timestamp range
    ts_col = stress_df["timestamp"]
    ts_min = ts_col.min()
    ts_max = ts_col.max()
    total_days = (ts_max - ts_min).total_seconds() / 86400 if ts_min and ts_max else 91.0

    # Actuator
    sl_list = stress_df["stress_level"].to_list()
    result = run_actuator(sl_list, preset.cfg)

    n = len(result.states)
    pct_normal = sum(1 for s in result.states if s == "NORMAL") / n * 100
    pct_stress = sum(1 for s in result.states if s == "STRESS") / n * 100
    pct_extreme = sum(1 for s in result.states if s == "EXTREME") / n * 100

    # Longest run
    longest, longest_state = 0, ""
    run_len = 1
    for i in range(1, n):
        if result.states[i] == result.states[i - 1]:
            run_len += 1
        else:
            if run_len > longest:
                longest, longest_state = run_len, result.states[i - 1]
            run_len = 1
    if run_len > longest:
        longest, longest_state = run_len, result.states[-1] if result.states else ""

    # Top-5 switch rows
    top_rows: list[int] = []
    prev = 0
    for i, c in enumerate(result.switches_cumulative):
        if c > prev:
            top_rows.append(i)
        prev = c
    top_rows = top_rows[:5]

    return SymbolResult(
        symbol=symbol,
        bars=n,
        total_days=total_days,
        switches=result.total_switches,
        pct_normal=pct_normal,
        pct_stress=pct_stress,
        pct_extreme=pct_extreme,
        longest_run_bars=longest,
        longest_run_state=longest_state,
        top_rows=top_rows,
        stress_df=stress_df,
    )


def _format_top_switches(sr: SymbolResult) -> str:
    if not sr.top_rows:
        return "_No switches._\n"
    lines = [
        "| # | Timestamp (UTC) | stress_level | z_atr | z_vol | z_gap | z_range |",
        "|---|-----------------|-------------|-------|-------|-------|---------|",
    ]
    for num, row_idx in enumerate(sr.top_rows, 1):
        if row_idx >= sr.stress_df.height:
            continue
        row = sr.stress_df.row(row_idx, named=True)
        ts = str(row.get("timestamp", "?"))
        sl = row.get("stress_level", 0.0)
        lines.append(
            f"| {num} | {ts} "
            f"| {sl:.3f} "
            f"| {row.get('z_atr', 0.0):.2f} "
            f"| {row.get('z_realized_vol', 0.0):.2f} "
            f"| {row.get('z_gap', 0.0):.2f} "
            f"| {row.get('z_bar_range', 0.0):.2f} |"
        )
    return "\n".join(lines) + "\n"


def _is_portable(results: List[SymbolResult]) -> bool:
    return all(r.verdict == "PASS" for r in results)


def generate_report(
    preset,
    results: List[SymbolResult],
    tf: str,
    months: List[str],
    window: int,
    burn_in: int,
) -> str:
    portable = _is_portable(results)
    verdict_summary = "PORTABLE" if portable else (
        "WARN" if all(r.verdict in ("PASS", "WARN") for r in results) else "NOT PORTABLE"
    )

    lines = [
        "# Multi-Symbol Preset Portability Report",
        "",
        f"**Preset:** {preset.name} — {preset.description}  ",
        f"**Timeframe:** {tf}  ",
        f"**Months:** {', '.join(months)}  ",
        f"**Window:** {window}  |  **Burn-in:** {burn_in}  ",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Cross-Symbol Summary",
        "",
        "| Symbol | Bars | /day | NORMAL% | STRESS% | EXTREME% | Longest run | Verdict |",
        "|--------|------|------|---------|---------|----------|-------------|---------|",
    ]

    for r in results:
        lines.append(
            f"| **{r.symbol}** "
            f"| {r.bars:,} "
            f"| {r.switches_per_day:.2f} "
            f"| {r.pct_normal:.1f}% "
            f"| {r.pct_stress:.1f}% "
            f"| {r.pct_extreme:.1f}% "
            f"| {r.longest_run_bars} bars ({r.longest_run_state}) "
            f"| **{r.verdict}** |"
        )

    lines += [
        "",
        f"**Overall portability: {verdict_summary}**",
        "",
        "Acceptance thresholds:",
        f"- PASS: switches/day <= {_PASS_SPD_MAX} AND {_PASS_STRESS_MIN}% <= STRESS% <= {_PASS_STRESS_MAX}%",
        f"- WARN: switches/day <= {_WARN_SPD_MAX} OR STRESS% >= {_WARN_STRESS_MIN}%",
        "- FAIL: outside WARN bounds",
        "",
        "---",
        "",
        "## Per-Symbol Details",
        "",
    ]

    for r in results:
        lines += [
            f"### {r.symbol} — {r.verdict}",
            "",
            f"- Bars: {r.bars:,}  |  Period: {r.total_days:.1f} days",
            f"- Switches: {r.switches} ({r.switches_per_day:.2f}/day)",
            f"- NORMAL: {r.pct_normal:.1f}%  |  STRESS: {r.pct_stress:.1f}%  |  EXTREME: {r.pct_extreme:.1f}%",
            f"- Longest stable run: {r.longest_run_bars} bars ({r.longest_run_state})",
            "",
            f"**Top-{len(r.top_rows)} switch events:**",
            "",
            _format_top_switches(r),
        ]

    lines += [
        "---",
        "",
        "## Preset Config",
        "",
        "```yaml",
        "state_mapping:",
        f"  enter_stress: {preset.cfg.enter_stress}",
        f"  exit_stress: {preset.cfg.exit_stress}",
        f"  enter_extreme: {preset.cfg.enter_extreme}",
        f"  exit_extreme: {preset.cfg.exit_extreme}",
        f"  consecutive_bars_enter: {preset.cfg.consecutive_bars_enter}",
        f"  consecutive_bars_exit: {preset.cfg.consecutive_bars_exit}",
        f"  min_duration_bars: {preset.cfg.min_duration_bars}",
        f"  switch_window_bars: {preset.cfg.switch_window_bars}",
        f"  max_switches_per_window: {preset.cfg.max_switches_per_window}",
        "  circuit_breaker_mode: halt",
        "```",
        "",
    ]

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="validate-preset",
        description="Check preset portability across multiple symbols.",
    )
    p.add_argument(
        "--symbols", nargs="+",
        default=["BTCUSDT", "ETHUSDT", "DOGEUSDT", "1000PEPEUSDT"],
    )
    p.add_argument("--preset", default="A4", help="Preset name from tune_presets (A0–A5)")
    p.add_argument("--tf", default="5m")
    p.add_argument("--months", nargs="+", default=["2024-01", "2024-02", "2024-03"])
    p.add_argument("--data-dir", default="data/processed")
    p.add_argument("--window", type=int, default=100)
    p.add_argument("--burn-in", type=int, default=120)
    p.add_argument(
        "--output",
        default="reports/stress_a4_multiasset_report.md",
        help="Output markdown path",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    data_dir = Path(args.data_dir)

    # Find the requested preset
    all_presets = _presets()
    preset_map = {p.name: p for p in all_presets}
    if args.preset not in preset_map:
        print(f"[error] unknown preset {args.preset!r}. Choose from {list(preset_map)}", file=sys.stderr)
        return 2
    preset = preset_map[args.preset]

    print(f"[preset] {preset.name}: {preset.description}")
    print(f"[symbols] {args.symbols}")

    results: list[SymbolResult] = []
    for sym in args.symbols:
        print(f"[run] {sym}...")
        sr = _run_symbol(
            sym, args.tf, args.months, data_dir, preset,
            window=args.window, burn_in=args.burn_in,
        )
        if sr is None:
            continue
        print(
            f"  {sr.switches} switches ({sr.switches_per_day:.2f}/day)"
            f"  STRESS={sr.pct_stress:.1f}%  verdict={sr.verdict}"
        )
        results.append(sr)

    if not results:
        print("[error] no valid results", file=sys.stderr)
        return 3

    report = generate_report(
        preset=preset,
        results=results,
        tf=args.tf,
        months=args.months,
        window=args.window,
        burn_in=args.burn_in,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"[report] {out_path}")

    portable = _is_portable(results)
    verdict = "PORTABLE" if portable else (
        "WARN" if all(r.verdict in ("PASS", "WARN") for r in results) else "NOT PORTABLE"
    )
    print(f"[verdict] {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
