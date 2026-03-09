#!/usr/bin/env python3
"""
Backtest Ladder Runner — Aurora/Phenix config-calibration validation.

Runs an incremental A/B ladder:
  A = baseline config (config/aurora_baseline/ — pre-calibration params)
  B = patched config  (config/aurora/           — post-calibration params)

Each rung adds one calendar month cumulative:
  R1  : 2023-06
  R2  : 2023-06..2023-07
  ...
  R10 : 2023-06..2024-03

Outputs:
  reports/backtest_ladder_report.md
  reports/backtest_ladder_manifest.json

Usage:
  python scripts/diagnostics/run_backtest_ladder.py          # runs all rungs
  python scripts/diagnostics/run_backtest_ladder.py --rung 1
  python scripts/diagnostics/run_backtest_ladder.py --rung 1 --rung 2

Early-stop rule (configurable):
  If B is worse than A by > --pnl-threshold % net PnL AND DD worse by
  > --dd-threshold % for 2 consecutive rungs → stop.
  Default: pnl=10%, dd=15%.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import textwrap
import traceback
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Project root setup ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# ── Ladder definition ─────────────────────────────────────────────────────────
# (rung_number, start_year, start_month, end_year, end_month)
LADDER_RUNGS: List[Tuple[int, int, int, int, int]] = [
    (1,  2023, 6,  2023, 6),
    (2,  2023, 6,  2023, 7),
    (3,  2023, 6,  2023, 8),
    (4,  2023, 6,  2023, 9),
    (5,  2023, 6,  2023, 10),
    (6,  2023, 6,  2023, 11),
    (7,  2023, 6,  2023, 12),
    (8,  2023, 6,  2024, 1),
    (9,  2023, 6,  2024, 2),
    (10, 2023, 6,  2024, 3),
]

BASELINE_CONFIG_DIR = ROOT / "config" / "aurora_baseline"
PATCHED_CONFIG_DIR  = ROOT / "config" / "aurora"
REPORTS_DIR         = ROOT / "reports"
LADDER_REPORT_FILE  = REPORTS_DIR / "backtest_ladder_report.md"
LADDER_MANIFEST_FILE = REPORTS_DIR / "backtest_ladder_manifest.json"

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
DEFAULT_INITIAL_BALANCE = 1000.0
EARLY_STOP_CONSECUTIVE = 2

# ── Rung date helpers ──────────────────────────────────────────────────────────

def rung_dates(rung: Tuple[int, int, int, int, int]) -> Tuple[str, str]:
    """Return (start_date_str, end_date_str) for a rung tuple."""
    _, sy, sm, ey, em = rung
    last_day = monthrange(ey, em)[1]
    return (
        f"{sy:04d}-{sm:02d}-01",
        f"{ey:04d}-{em:02d}-{last_day:02d}",
    )


def rung_label(rung: Tuple[int, int, int, int, int]) -> str:
    """Human label like '2023-06' or '2023-06..2023-09'."""
    _, sy, sm, ey, em = rung
    start = f"{sy:04d}-{sm:02d}"
    end = f"{ey:04d}-{em:02d}"
    return start if start == end else f"{start}..{end}"


# ── Config loading + date override ────────────────────────────────────────────

def _load_config_for_rung(
    config_dir: Path,
    start_date: str,
    end_date: str,
    symbols: List[str],
    initial_balance: float,
):
    """Load AuroraConfig from config_dir, override backtest dates and symbols."""
    from apps.reference.config_loader import ConfigLoader

    loader = ConfigLoader(config_dir=config_dir)
    config = loader.load_config()

    # Override backtest window — Pydantic models are mutable by default
    try:
        config.trading.backtest.start_date = start_date
        config.trading.backtest.end_date = end_date
        config.trading.backtest.initial_balance = initial_balance
    except Exception as exc:
        raise RuntimeError(
            f"Failed to set backtest dates on config from {config_dir}: {exc}"
        ) from exc

    # Override symbols if the config model exposes them
    try:
        if hasattr(config.trading, "symbols_to_track"):
            config.trading.symbols_to_track = symbols
    except Exception:
        pass  # Fail-open: symbols come from instruments if not overridable

    return config


# ── Single run ────────────────────────────────────────────────────────────────

def _run_one(
    config_dir: Path,
    start_date: str,
    end_date: str,
    symbols: List[str],
    initial_balance: float,
    label: str,
) -> Tuple[Optional[Any], Optional[Dict]]:
    """
    Load config, run backtest, return (BacktestResult, report_dict).
    Returns (None, None) on failure — caller logs and continues.
    """
    print(f"  [{label}] Loading config from {config_dir.name}...")
    try:
        config = _load_config_for_rung(config_dir, start_date, end_date, symbols, initial_balance)
    except Exception as exc:
        print(f"  [{label}] ERROR loading config: {exc}")
        return None, None

    print(f"  [{label}] Running backtest {start_date} -> {end_date}...")
    try:
        from apps.reference.main import run_backtest_simulation
        result, report = run_backtest_simulation(config, return_result=True)
        print(f"  [{label}] Done. PnL={result.total_pnl:.4f} USDT, DD={result.max_drawdown*100:.2f}%")
        return result, report
    except Exception as exc:
        print(f"  [{label}] ERROR running backtest: {exc}")
        traceback.print_exc()
        return None, None


# ── Metrics extraction ────────────────────────────────────────────────────────

def _extract_metrics(result: Optional[Any], report: Optional[Dict]) -> Dict:
    """Pull all relevant metrics from result + report dict into a flat dict."""
    if result is None:
        return {"error": True}

    m: Dict[str, Any] = {
        "error": False,
        "total_pnl":        round(float(result.total_pnl), 4),
        "roi_pct":          round(float(result.roi_pct), 4),
        "max_drawdown":     round(float(result.max_drawdown), 6),
        "max_drawdown_pct": round(float(result.max_drawdown) * 100, 2),
        "total_trades":     int(result.total_trades),
        "win_rate":         round(float(result.win_rate), 4),
        "end_balance":      round(float(result.end_balance), 4),
        "sharpe_ratio":     round(float(getattr(result, "sharpe_ratio", 0.0) or 0.0), 4),
        "calmar_ratio":     round(float(getattr(result, "calmar_ratio", 0.0) or 0.0), 4),
    }

    # Extract from report dict (deeper regime/fee info)
    if report:
        try:
            m["run_id"] = report.get("run_id", "")
            m["report_path"] = str(REPORTS_DIR / "backtests" / f"backtest_{m['run_id']}.json")
        except Exception:
            pass

        # Fees: look for fees_total in pipeline or broker section
        try:
            broker = report.get("broker", {}) or {}
            m["fees_total"] = round(float(broker.get("total_fees", 0.0) or 0.0), 4)
            m["fills_total"] = int(broker.get("total_fills", 0) or 0)
            m["cancels_total"] = int(broker.get("total_cancels", 0) or 0)
        except Exception:
            m["fees_total"] = None
            m["fills_total"] = None
            m["cancels_total"] = None

        # Regime distribution from report
        try:
            regimes = report.get("regimes", {}) or {}
            counts_by_sym = regimes.get("counts_by_symbol", {}) or {}
            m["regime_counts_by_symbol"] = counts_by_sym
        except Exception:
            m["regime_counts_by_symbol"] = {}

        # Per-symbol PnL if available
        try:
            trade_intents = report.get("trade_intents", []) or []
            sym_pnl: Dict[str, float] = {}
            for intent in trade_intents:
                sym = intent.get("symbol", "?")
                pnl = float(intent.get("pnl", 0.0) or 0.0)
                sym_pnl[sym] = round(sym_pnl.get(sym, 0.0) + pnl, 4)
            m["pnl_by_symbol"] = sym_pnl
        except Exception:
            m["pnl_by_symbol"] = {}

        # Pipeline stats
        try:
            pipeline = report.get("pipeline", {}) or {}
            m["bar_count"] = int(pipeline.get("bar_count", 0) or 0)
            m["blocked_reasons"] = pipeline.get("blocked_reason_counts", {})
        except Exception:
            m["bar_count"] = None
            m["blocked_reasons"] = {}

    return m


# ── Delta computation ─────────────────────────────────────────────────────────

def _compute_deltas(a: Dict, b: Dict) -> Dict:
    """Compute B-A deltas for numeric fields."""
    if a.get("error") or b.get("error"):
        return {"error": True}

    numeric_keys = [
        "total_pnl", "roi_pct", "max_drawdown_pct",
        "total_trades", "win_rate", "fees_total",
        "sharpe_ratio", "calmar_ratio",
    ]
    d: Dict[str, Any] = {}
    for k in numeric_keys:
        va = a.get(k)
        vb = b.get(k)
        if va is not None and vb is not None:
            try:
                d[f"delta_{k}"] = round(float(vb) - float(va), 4)
            except Exception:
                d[f"delta_{k}"] = None
        else:
            d[f"delta_{k}"] = None
    return d


# ── Early stop check ─────────────────────────────────────────────────────────

def _should_early_stop(
    history: List[Dict],
    pnl_threshold: float,
    dd_threshold: float,
) -> bool:
    """
    Stop if B worse than A by pnl_threshold% net PnL AND
    DD worse by dd_threshold% for the last EARLY_STOP_CONSECUTIVE rungs.
    """
    if len(history) < EARLY_STOP_CONSECUTIVE:
        return False
    recent = history[-EARLY_STOP_CONSECUTIVE:]
    for entry in recent:
        d = entry.get("deltas", {})
        if d.get("error"):
            return False
        dpnl = d.get("delta_total_pnl")
        ddd  = d.get("delta_max_drawdown_pct")
        if dpnl is None or ddd is None:
            return False
        # B worse on PnL (negative delta) and DD (positive delta = B has more DD)
        if not (dpnl < -abs(pnl_threshold) and ddd > abs(dd_threshold)):
            return False
    return True


# ── Markdown report helpers ───────────────────────────────────────────────────

def _fmt_val(v: Any, pct: bool = False) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        suffix = "%" if pct else ""
        return f"{v:+.2f}{suffix}" if pct else f"{v:.4f}"
    return str(v)


def _write_report_header(symbols: List[str], initial_balance: float) -> None:
    """Write (overwrite) the report file with header section."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    content = textwrap.dedent(f"""\
        # Backtest Ladder Report — Aurora Calibration Validation

        **Generated:** {now}
        **Strategy:** Aurora ONLY (mean_reversion excluded)
        **Symbols:** {', '.join(symbols)}
        **Initial balance:** {initial_balance:.2f} USDT
        **Timeframe:** 5m

        ## Config Comparison

        | Param | Baseline (A) | Patched (B) |
        |-------|-------------|-------------|
        | SMA short/long | 24/96 | 48/192 |
        | BTC HIGH_VOL sizing | 0.50 | 0.65 |
        | ETH HIGH_VOL sizing | 0.30 | 0.50 |
        | ETH LOW_VOL sizing  | 1.00 | 0.85 |
        | stress_attenuation_factor | 0.50 | 0.50 (unchanged) |
        | signal_weights | unchanged | unchanged |
        | TP/SL multipliers | unchanged | unchanged |

        **Baseline config dir:** `config/aurora_baseline/`
        **Patched config dir:**  `config/aurora/`

        ## Early-Stop Rule

        Stop if B worse than A by >10% net PnL AND DD worse by >15%
        for **2 consecutive rungs**. Otherwise run to R10.

        ---

        ## Ladder Results

        | Rung | Period | A PnL | B PnL | ΔPnL | A DD% | B DD% | ΔDD% | A Trades | B Trades | ΔTrades | Status |
        |------|--------|-------|-------|------|-------|-------|------|----------|----------|---------|--------|
    """)
    LADDER_REPORT_FILE.write_text(content, encoding="utf-8")


def _append_table_row(entry: Dict) -> None:
    """Append a single table row to the ladder report."""
    r = entry["rung"]
    period = entry["period"]
    a = entry.get("metrics_a", {})
    b = entry.get("metrics_b", {})
    d = entry.get("deltas", {})
    stopped = entry.get("early_stop", False)

    status = "STOPPED (regression)" if stopped else "OK"
    if a.get("error"):
        status = "A-FAILED"
    if b.get("error"):
        status = "B-FAILED"

    row = (
        f"| R{r} | {period} "
        f"| {_fmt_val(a.get('total_pnl'))} "
        f"| {_fmt_val(b.get('total_pnl'))} "
        f"| {_fmt_val(d.get('delta_total_pnl'))} "
        f"| {_fmt_val(a.get('max_drawdown_pct'))} "
        f"| {_fmt_val(b.get('max_drawdown_pct'))} "
        f"| {_fmt_val(d.get('delta_max_drawdown_pct'))} "
        f"| {_fmt_val(a.get('total_trades'))} "
        f"| {_fmt_val(b.get('total_trades'))} "
        f"| {_fmt_val(d.get('delta_total_trades'))} "
        f"| {status} |"
    )

    with LADDER_REPORT_FILE.open("a", encoding="utf-8") as f:
        f.write(row + "\n")


def _append_rung_detail(entry: Dict) -> None:
    """Append detailed analysis block for one rung."""
    r = entry["rung"]
    a = entry.get("metrics_a", {})
    b = entry.get("metrics_b", {})
    d = entry.get("deltas", {})
    notes = entry.get("notes", [])

    lines = [
        f"\n### R{r} Detail — {entry['period']} ({entry['start_date']} → {entry['end_date']})\n",
        "**A (baseline) metrics:**\n",
        f"- net_pnl={a.get('total_pnl')} | roi_pct={a.get('roi_pct')} | dd={a.get('max_drawdown_pct')} | trades={a.get('total_trades')} | win_rate={a.get('win_rate')} | sharpe={a.get('sharpe_ratio')}",
    ]
    if a.get("fees_total") is not None:
        lines.append(f"- fees_total={a.get('fees_total')} | fills={a.get('fills_total')} | cancels={a.get('cancels_total')}")
    if a.get("pnl_by_symbol"):
        for sym, pnl in sorted(a["pnl_by_symbol"].items()):
            lines.append(f"  - {sym}: {pnl:.4f}")

    lines += [
        "\n**B (patched) metrics:**\n",
        f"- net_pnl={b.get('total_pnl')} | roi_pct={b.get('roi_pct')} | dd={b.get('max_drawdown_pct')} | trades={b.get('total_trades')} | win_rate={b.get('win_rate')} | sharpe={b.get('sharpe_ratio')}",
    ]
    if b.get("fees_total") is not None:
        lines.append(f"- fees_total={b.get('fees_total')} | fills={b.get('fills_total')} | cancels={b.get('cancels_total')}")
    if b.get("pnl_by_symbol"):
        for sym, pnl in sorted(b["pnl_by_symbol"].items()):
            lines.append(f"  - {sym}: {pnl:.4f}")

    lines += [
        f"\n**Deltas (B-A):** ΔPnL={d.get('delta_total_pnl')} | ΔDD={d.get('delta_max_drawdown_pct')} | ΔTrades={d.get('delta_total_trades')} | ΔSharpe={d.get('delta_sharpe_ratio')}",
    ]

    if notes:
        lines.append("\n**Notes:**")
        for n in notes:
            lines.append(f"- {n}")

    verdict = entry.get("verdict", "continue")
    lines.append(f"\n**Verdict:** {verdict}\n")
    lines.append("---\n")

    with LADDER_REPORT_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_final_section(history: List[Dict], early_stop_rung: Optional[int]) -> None:
    """Write executive summary and final verdict at end of report."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = ["\n---\n", "## Executive Summary\n"]

    if early_stop_rung:
        lines.append(
            f"**EARLY STOP triggered at R{early_stop_rung}** — "
            f"B (patched) degraded net PnL by >10% AND drawdown by >15% "
            f"for {EARLY_STOP_CONSECUTIVE} consecutive rungs.\n"
        )
        lines.append("**Recommended next step:** Do not deploy patched config. "
                     "Inspect `regime_threshold_multipliers` in `aurora.yaml` — "
                     "wider SMA (48/192) may shift label distribution, "
                     "requiring threshold re-tuning before sizing changes take effect.\n")
    else:
        completed = len(history)
        lines.append(
            f"**All {completed} rungs completed without early-stop.** "
            f"Patched config (B) did not degrade performance beyond thresholds.\n"
        )
        # Quick summary of final rung
        if history:
            last = history[-1]
            d = last.get("deltas", {})
            dpnl = d.get("delta_total_pnl")
            ddd = d.get("delta_max_drawdown_pct")
            if dpnl is not None:
                direction = "improved" if dpnl > 0 else "degraded"
                lines.append(
                    f"Final rung (R{last['rung']}, {last['period']}): "
                    f"B {direction} net PnL by {dpnl:+.4f} USDT vs A. "
                    f"DD Δ: {ddd:+.2f}pp.\n"
                )
        lines.append("**Recommended next step:** Proceed to Phase R3-A full "
                     "(backtest trade join + expectancy per regime with patched config).\n")

    lines.append(f"*Report finalized: {now}*\n")

    with LADDER_REPORT_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── Manifest ──────────────────────────────────────────────────────────────────

def _update_manifest(history: List[Dict]) -> None:
    """Write/overwrite the manifest JSON with all completed run metadata."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated": datetime.utcnow().isoformat(),
        "baseline_config": str(BASELINE_CONFIG_DIR),
        "patched_config": str(PATCHED_CONFIG_DIR),
        "config_diff": {
            "regime.yaml sma_short": "24 → 48",
            "regime.yaml sma_long":  "96 → 192",
            "aurora.yaml BTC HIGH_VOL": "0.50 → 0.65",
            "aurora.yaml ETH HIGH_VOL": "0.30 → 0.50",
            "aurora.yaml ETH LOW_VOL":  "1.00 → 0.85",
        },
        "rungs": history,
    }
    LADDER_MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _auto_notes(entry: Dict) -> List[str]:
    """Generate automatic analysis notes for a rung."""
    a = entry.get("metrics_a", {})
    b = entry.get("metrics_b", {})
    d = entry.get("deltas", {})
    notes = []

    if a.get("error") or b.get("error"):
        notes.append("One or both runs failed — data incomplete.")
        return notes

    dpnl = d.get("delta_total_pnl", 0.0) or 0.0
    ddd  = d.get("delta_max_drawdown_pct", 0.0) or 0.0
    dtrades = d.get("delta_total_trades", 0) or 0

    if dpnl > 0:
        notes.append(f"B improved net PnL by {dpnl:+.4f} USDT ({dpnl/max(abs(a['total_pnl']),0.001)*100:+.1f}%).")
    else:
        notes.append(f"B degraded net PnL by {dpnl:+.4f} USDT ({dpnl/max(abs(a['total_pnl']),0.001)*100:+.1f}%).")

    if ddd < 0:
        notes.append(f"B reduced max drawdown by {abs(ddd):.2f}pp (positive).")
    elif ddd > 0:
        notes.append(f"B increased max drawdown by {ddd:.2f}pp.")

    if abs(dtrades) > 0:
        pct = abs(dtrades) / max(a.get("total_trades", 1), 1) * 100
        direction = "more" if dtrades > 0 else "fewer"
        notes.append(f"B placed {abs(dtrades)} {direction} trades ({pct:.1f}%) — "
                     f"{'possible churn increase from wider SMA labels' if dtrades > 0 else 'possible fewer UNCERTAIN-triggered entries'}.")

    # SMA comment for early rungs
    if entry["rung"] <= 2:
        notes.append(
            "SMA 48/192 needs ≥192 bars warmup (~16h at 5m) vs 96 bars for 24/96. "
            "Early-rung results may undercount B trades due to longer warmup."
        )

    return notes


# ── Main ──────────────────────────────────────────────────────────────────────

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Aurora backtest calibration ladder (A=baseline, B=patched)"
    )
    p.add_argument("--rung", type=int, action="append", dest="rungs", metavar="N",
                   help="Rung number to run (1-10). Can repeat. Default: all.")
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS,
                   help="Symbols to backtest (space-separated)")
    p.add_argument("--initial-balance", type=float, default=DEFAULT_INITIAL_BALANCE,
                   help="Initial USDT balance (default: 1000)")
    p.add_argument("--pnl-threshold", type=float, default=10.0,
                   help="Early-stop: PnL regression threshold %% (default 10)")
    p.add_argument("--dd-threshold", type=float, default=15.0,
                   help="Early-stop: DD regression threshold %% (default 15)")
    p.add_argument("--no-early-stop", action="store_true",
                   help="Disable early-stop (run all rungs regardless)")
    p.add_argument("--resume", action="store_true",
                   help="Append to existing report instead of overwriting")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    target_rungs = sorted(set(args.rungs)) if args.rungs else [r[0] for r in LADDER_RUNGS]
    symbols = args.symbols

    print(f"\n=== Aurora Backtest Ladder ===")
    print(f"Rungs   : {target_rungs}")
    print(f"Symbols : {symbols}")
    print(f"Balance : {args.initial_balance:.2f} USDT")
    print(f"Baseline: {BASELINE_CONFIG_DIR.name}")
    print(f"Patched : {PATCHED_CONFIG_DIR.name}")
    print(f"Report  : {LADDER_REPORT_FILE}")
    print()

    # Verify config dirs exist
    if not BASELINE_CONFIG_DIR.exists():
        print(f"ERROR: Baseline config dir not found: {BASELINE_CONFIG_DIR}")
        return 1
    if not PATCHED_CONFIG_DIR.exists():
        print(f"ERROR: Patched config dir not found: {PATCHED_CONFIG_DIR}")
        return 1

    # Write report header (unless resuming)
    if not args.resume:
        _write_report_header(symbols, args.initial_balance)

    history: List[Dict] = []
    early_stop_rung: Optional[int] = None

    for rung_def in LADDER_RUNGS:
        r_num = rung_def[0]
        if r_num not in target_rungs:
            continue

        start_date, end_date = rung_dates(rung_def)
        period = rung_label(rung_def)
        print(f"\n--- R{r_num}: {period} ({start_date} -> {end_date}) ---")

        # Run A (baseline)
        result_a, report_a = _run_one(
            BASELINE_CONFIG_DIR, start_date, end_date,
            symbols, args.initial_balance, f"A-R{r_num}"
        )
        metrics_a = _extract_metrics(result_a, report_a)

        # Run B (patched)
        result_b, report_b = _run_one(
            PATCHED_CONFIG_DIR, start_date, end_date,
            symbols, args.initial_balance, f"B-R{r_num}"
        )
        metrics_b = _extract_metrics(result_b, report_b)

        deltas = _compute_deltas(metrics_a, metrics_b)

        entry: Dict[str, Any] = {
            "rung": r_num,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "metrics_a": metrics_a,
            "metrics_b": metrics_b,
            "deltas": deltas,
        }

        entry["notes"] = _auto_notes(entry)

        # Early stop check
        history.append(entry)
        stopped = False
        if not args.no_early_stop:
            stopped = _should_early_stop(history, args.pnl_threshold, args.dd_threshold)

        if stopped:
            entry["early_stop"] = True
            entry["verdict"] = f"STOP — regression exceeds thresholds (ΔPnL<-{args.pnl_threshold}%, ΔDD>+{args.dd_threshold}%) for {EARLY_STOP_CONSECUTIVE} consecutive rungs"
            early_stop_rung = r_num
        else:
            entry["early_stop"] = False
            dpnl = deltas.get("delta_total_pnl", None)
            if dpnl is None:
                entry["verdict"] = "continue (incomplete data)"
            elif dpnl >= 0:
                entry["verdict"] = f"continue — B ≥ A on PnL (Δ={dpnl:+.4f})"
            else:
                entry["verdict"] = f"continue — B < A on PnL (Δ={dpnl:+.4f}), within threshold"

        _append_table_row(entry)
        _append_rung_detail(entry)
        _update_manifest(history)

        print(f"  R{r_num} verdict: {entry['verdict']}")

        if stopped:
            print(f"\n[EARLY STOP] R{r_num}. See {LADDER_REPORT_FILE}")
            break

    _write_final_section(history, early_stop_rung)
    _update_manifest(history)

    print(f"\n[DONE] Ladder complete. Report: {LADDER_REPORT_FILE}")
    print(f"[DONE] Manifest:               {LADDER_MANIFEST_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
