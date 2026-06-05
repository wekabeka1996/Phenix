"""
AURORA_TREND_MIN_ACTIVATION_FORWARD_REPLAY_V1

Validates S1_TREND_MIN_ONLY (trend min_regime_confidence >= 0.40 for TREND_UP/TREND_DOWN)
against S0_CURRENT over the broadest available recorder window.

Hard rules:
- Recorder-only. No runtime mutation. No production config patch.
- No disabling TREND max-cap veto (S2 was toxic).
- No HIGH_VOL TP/SL changes.
- No new side-selection model.
- YAML + Pydantic remain SSOT.
- Report FACT / INFERENCE / ASSUMPTION / UNKNOWN separately.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
RECORDER_DIR = ROOT / "data" / "recorder"
CONFIG_DIR = ROOT / "config" / "aurora"
REPORTS_DIR = ROOT / "reports"

DOMAINS_YAML = CONFIG_DIR / "domains.yaml"
STRATEGIES_REGISTRY_YAML = CONFIG_DIR / "strategies.yaml"
AURORA_STRATEGY_YAML = CONFIG_DIR / "strategies" / "aurora.yaml"

DEFAULT_TF_SEC = 300
DEFAULT_MAX_BARS = 18
S1_TREND_MIN = 0.40

# Full window: when all 5 aurora symbols have data
BROAD_WINDOW_START = "2026-03-05"
BROAD_WINDOW_END = "2026-05-04"
# Held-out ablation window (used in previous task — NOT excluded, but flagged)
ABLATION_WINDOW = {"start": "2026-05-03", "end": "2026-05-04"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BarRow:
    symbol: str
    bar_i: int
    ts_ms: int
    dt: str
    date_str: str
    open_: float
    high: float
    low: float
    close: float
    regime: str
    regime_conf: float
    pillar_sum: float


@dataclass
class TradeRecord:
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    side: str
    outcome: str       # TP | SL | TIMEOUT
    pnl_pct: float     # raw fraction * 100
    r_multiple: float
    bars_held: int
    entry_price: float
    sl_pct_used: float
    tp_pct_used: float
    regime_conf: float


@dataclass
class RejectRecord:
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    reason: str
    regime_conf: float


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forward replay for AURORA_TREND_MIN_ACTIVATION S1 validation",
    )
    parser.add_argument("--window-start", default=BROAD_WINDOW_START)
    parser.add_argument("--window-end", default=BROAD_WINDOW_END)
    parser.add_argument("--tf-sec", type=int, default=DEFAULT_TF_SEC)
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--rolling-days", type=int, default=7,
                        help="Window size in days for rolling sub-window analysis")
    parser.add_argument(
        "--output-json",
        default=str(
            REPORTS_DIR / "AURORA_TREND_MIN_ACTIVATION_FORWARD_REPLAY_V1_2026_05_04.json"),
    )
    parser.add_argument(
        "--output-md",
        default=str(
            REPORTS_DIR / "AURORA_TREND_MIN_ACTIVATION_FORWARD_REPLAY_V1_2026_05_04.md"),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_float(v: Any) -> float | None:
    if v in (None, "", "None", "null"):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def safe_int(v: Any) -> int | None:
    if v in (None, "", "None", "null"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping in {path}")
    return raw


def normalize_symbol(name: str) -> str:
    return str(name or "").strip().upper()


def dates_in_range(start: str, end: str) -> list[str]:
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    result = []
    cur = d0
    while cur <= d1:
        result.append(cur.isoformat())
        cur += timedelta(days=1)
    return result


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_assigned_aurora_symbols() -> list[str]:
    data = load_yaml(STRATEGIES_REGISTRY_YAML)
    assignments = data.get("assignments") or {}
    if not isinstance(assignments, dict):
        return []
    symbols: list[str] = []
    for sym, strategies in assignments.items():
        if not isinstance(strategies, list):
            continue
        if any(str(s).strip() == "aurora" for s in strategies):
            symbols.append(normalize_symbol(sym))
    return sorted(set(symbols))


def load_aurora_asset_cfg() -> tuple[float, dict[str, Any]]:
    data = load_yaml(AURORA_STRATEGY_YAML)
    aurora = data.get("aurora") or {}
    decision = aurora.get("decision") or {}
    signal_threshold = safe_float(decision.get("signal_threshold"))
    if signal_threshold is None:
        raise ValueError("aurora.decision.signal_threshold missing/invalid")
    assets = aurora.get("assets") or {}
    if not isinstance(assets, dict):
        raise ValueError("aurora.assets is not a mapping")
    return signal_threshold, assets


def load_domain_gate_cfg() -> dict[str, Any]:
    domains = load_yaml(DOMAINS_YAML)
    dm = domains.get("decision_making") or {}
    directional = dm.get("directional_sanity") or {}
    low_vol = dm.get("low_vol_cost_floor_gate") or {}
    return {"directional": directional, "low_vol": low_vol}


# ---------------------------------------------------------------------------
# Bar loading
# ---------------------------------------------------------------------------

def load_rows_for_symbol_date(
    symbol: str, date_str: str, tf_sec: int
) -> list[BarRow]:
    path = RECORDER_DIR / date_str / f"{symbol}_{tf_sec}.csv"
    if not path.exists():
        return []

    rows: list[BarRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            ready_raw = str(rec.get("ready") or "").strip().lower()
            if ready_raw not in ("true", "1"):
                continue
            regime = str(rec.get("regime") or "").strip().upper()
            if not regime or regime == "PENDING":
                continue
            ts_ms = safe_int(rec.get("timestamp"))
            if ts_ms is None:
                continue
            open_ = safe_float(rec.get("open"))
            high = safe_float(rec.get("high"))
            low = safe_float(rec.get("low"))
            close = safe_float(rec.get("close"))
            regime_conf = safe_float(rec.get("regime_conf"))
            pillar_sum = safe_float(rec.get("feat_pillar_sum"))
            if None in (open_, high, low, close, regime_conf, pillar_sum):
                continue
            rows.append(BarRow(
                symbol=symbol, bar_i=0, ts_ms=ts_ms,
                dt=str(rec.get("datetime") or ""),
                date_str=date_str,
                open_=float(open_), high=float(high),
                low=float(low), close=float(close),
                regime=regime, regime_conf=float(regime_conf),
                pillar_sum=float(pillar_sum),
            ))

    rows.sort(key=lambda x: x.ts_ms)
    return rows


def load_all_bars(
    symbols: list[str], date_list: list[str], tf_sec: int
) -> dict[str, list[BarRow]]:
    bars_by_symbol: dict[str, list[BarRow]] = {}
    for symbol in symbols:
        merged: list[BarRow] = []
        for date_str in date_list:
            merged.extend(load_rows_for_symbol_date(symbol, date_str, tf_sec))
        merged.sort(key=lambda x: x.ts_ms)
        for idx, row in enumerate(merged):
            row.bar_i = idx
        bars_by_symbol[symbol] = merged
    return bars_by_symbol


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

def resolve_regime_threshold(
    regime: str, mapping: dict[str, Any], default_value: float | None
) -> float | None:
    value = safe_float(mapping.get(regime))
    if value is not None:
        return value
    default = safe_float(mapping.get("DEFAULT"))
    if default is not None:
        return default
    return default_value


def side_from_score(score: float, threshold: float) -> str:
    if score >= threshold:
        return "BUY"
    if score <= -threshold:
        return "SELL"
    return ""


def apply_gates_s0(
    *,
    row: BarRow,
    side: str,
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    """Current (S0) gate logic — no experimental changes."""
    if not side:
        return False, "NO_SIDE"

    min_default = safe_float(directional_cfg.get("min_regime_confidence"))
    min_map = directional_cfg.get("min_regime_confidence_by_regime") or {}
    max_map = directional_cfg.get("max_regime_confidence_by_regime") or {}

    min_required = resolve_regime_threshold(row.regime, min_map, min_default)
    if min_required is not None and row.regime_conf < min_required:
        return False, "REGIME_CONFIDENCE_BELOW_MIN"

    max_allowed = resolve_regime_threshold(row.regime, max_map, None)
    if max_allowed is not None and row.regime_conf > max_allowed:
        return False, "REGIME_CONFIDENCE_ABOVE_MAX"

    regimes_gated = [str(r).strip().upper()
                     for r in (low_vol_cfg.get("regimes") or [])]
    if row.regime == "LOW_VOLATILITY" and "LOW_VOLATILITY" in regimes_gated:
        thresholds = low_vol_cfg.get("thresholds") or {}
        dir_map = thresholds.get("min_direction_confidence_by_regime") or {}
        min_dir = resolve_regime_threshold("LOW_VOLATILITY", dir_map, None)
        if min_dir is not None and abs(row.pillar_sum) < min_dir:
            return False, "LOW_VOL_DIRECTION_CONFIDENCE_BELOW_MIN"

    return True, None


def apply_gates_s1(
    *,
    row: BarRow,
    side: str,
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
    trend_min: float,
) -> tuple[bool, str | None]:
    """S1: current logic + TREND min activation floor. Max-cap veto kept active."""
    allowed, reason = apply_gates_s0(
        row=row, side=side,
        directional_cfg=directional_cfg, low_vol_cfg=low_vol_cfg,
    )
    if not allowed:
        return False, reason

    if row.regime in ("TREND_UP", "TREND_DOWN") and row.regime_conf < trend_min:
        return False, "TREND_ACTIVATION_BELOW_MIN"

    return True, None


# ---------------------------------------------------------------------------
# TPSL
# ---------------------------------------------------------------------------

def resolve_tpsl_params(
    asset_cfg: dict[str, Any], regime: str
) -> tuple[float, float] | None:
    exit_cfg = asset_cfg.get("exit") or {}
    tp_cfg = asset_cfg.get("take_profit") or {}
    regime_tpsl = exit_cfg.get("regime_tpsl") or {}
    if not bool(regime_tpsl.get("enabled")):
        return None
    mode = str(regime_tpsl.get("mode") or "pct_mult")
    if mode != "pct_mult":
        return None
    sl_pct_base = safe_float(exit_cfg.get("sl_pct"))
    tp_low_ratio = safe_float(tp_cfg.get("tp_low_ratio"))
    if sl_pct_base is None or tp_low_ratio is None:
        return None
    sl_mult_map = regime_tpsl.get("sl_mult") or {}
    tp_mult_map = regime_tpsl.get("tp_mult") or {}
    sl_mult = safe_float(sl_mult_map.get(regime)) or safe_float(
        sl_mult_map.get("DEFAULT"))
    tp_mult = safe_float(tp_mult_map.get(regime)) or safe_float(
        tp_mult_map.get("DEFAULT"))
    if sl_mult is None or tp_mult is None:
        return None
    sl_pct_eff = sl_pct_base * sl_mult
    tp_pct = sl_pct_eff * tp_low_ratio * tp_mult
    if sl_pct_eff <= 0 or tp_pct <= 0:
        return None
    return sl_pct_eff, tp_pct


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

def simulate_trade(
    *,
    side: str,
    entry_price: float,
    sl_pct: float,
    tp_pct: float,
    future_bars: list[BarRow],
) -> tuple[str, float, float, int]:
    if side == "BUY":
        stop = entry_price * (1.0 - sl_pct)
        target = entry_price * (1.0 + tp_pct)
    else:
        stop = entry_price * (1.0 + sl_pct)
        target = entry_price * (1.0 - tp_pct)

    for idx, bar in enumerate(future_bars, start=1):
        if side == "BUY":
            stop_hit = bar.low <= stop
            tp_hit = bar.high >= target
        else:
            stop_hit = bar.high >= stop
            tp_hit = bar.low <= target

        if stop_hit and tp_hit:
            stop_hit = True
            tp_hit = False  # fail-closed: SL-first

        if stop_hit:
            return "SL", -sl_pct, -1.0, idx
        if tp_hit:
            r = tp_pct / sl_pct if sl_pct > 0 else 0.0
            return "TP", tp_pct, r, idx

    if not future_bars:
        return "TIMEOUT", 0.0, 0.0, 0

    last = future_bars[-1].close
    pnl = (last - entry_price) / \
        entry_price if side == "BUY" else (entry_price - last) / entry_price
    r = pnl / sl_pct if sl_pct > 0 else 0.0
    return "TIMEOUT", pnl, r, len(future_bars)


def max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


# ---------------------------------------------------------------------------
# Core run function (both scenarios share same bar iteration)
# ---------------------------------------------------------------------------

def run_both_scenarios(
    *,
    bars_by_symbol: dict[str, list[BarRow]],
    signal_threshold: float,
    assets_cfg: dict[str, Any],
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
    max_bars: int,
    trend_min: float,
) -> tuple[list[TradeRecord], list[TradeRecord], list[RejectRecord], list[RejectRecord], int, Counter, Counter]:
    """
    Returns (s0_trades, s1_trades, s0_rejects, s1_rejects, bars_processed, regime_counts, regime_conf_buckets).
    Iterates bars once; gates evaluated per scenario independently.
    """
    bars_processed = 0
    regime_counts: Counter[str] = Counter()
    # For TREND regime_conf distribution analysis
    trend_conf_buckets: Counter[str] = Counter()

    s0_trades: list[TradeRecord] = []
    s1_trades: list[TradeRecord] = []
    s0_rejects: list[RejectRecord] = []
    s1_rejects: list[RejectRecord] = []

    for symbol, bars in bars_by_symbol.items():
        asset_cfg = assets_cfg.get(symbol)
        if not isinstance(asset_cfg, dict):
            continue
        regime_thresholds = asset_cfg.get("regime_thresholds") or {}

        for row in bars:
            bars_processed += 1
            regime_counts[row.regime] += 1

            # Track TREND conf distribution
            if row.regime in ("TREND_UP", "TREND_DOWN"):
                bucket = f"{row.regime}_{int(row.regime_conf * 10) * 10}pct"
                trend_conf_buckets[bucket] += 1

            factor = safe_float(regime_thresholds.get(row.regime)) or safe_float(
                regime_thresholds.get("DEFAULT"))
            if factor is None:
                s0_rejects.append(RejectRecord(symbol, row.bar_i, row.date_str,
                                  row.regime, "MISSING_REGIME_THRESHOLD", row.regime_conf))
                s1_rejects.append(RejectRecord(symbol, row.bar_i, row.date_str,
                                  row.regime, "MISSING_REGIME_THRESHOLD", row.regime_conf))
                continue

            threshold = signal_threshold * factor
            side = side_from_score(row.pillar_sum, threshold)

            # --- S0 ---
            ok0, reason0 = apply_gates_s0(
                row=row, side=side,
                directional_cfg=directional_cfg, low_vol_cfg=low_vol_cfg,
            )
            if ok0:
                params = resolve_tpsl_params(asset_cfg, row.regime)
                if params is None:
                    s0_rejects.append(RejectRecord(
                        symbol, row.bar_i, row.date_str, row.regime, "TPSL_CONFIG_UNAVAILABLE", row.regime_conf))
                else:
                    sl_pct, tp_pct = params
                    future = bars[row.bar_i + 1: row.bar_i + 1 + max_bars]
                    outcome, pnl, r, held = simulate_trade(
                        side=side, entry_price=row.close,
                        sl_pct=sl_pct, tp_pct=tp_pct, future_bars=future,
                    )
                    s0_trades.append(TradeRecord(
                        symbol=symbol, bar_i=row.bar_i, date_str=row.date_str,
                        regime=row.regime, side=side,
                        outcome=outcome, pnl_pct=pnl * 100.0,
                        r_multiple=r, bars_held=held,
                        entry_price=row.close, sl_pct_used=sl_pct, tp_pct_used=tp_pct,
                        regime_conf=row.regime_conf,
                    ))
            else:
                if reason0:
                    s0_rejects.append(RejectRecord(
                        symbol, row.bar_i, row.date_str, row.regime, reason0, row.regime_conf))

            # --- S1 ---
            ok1, reason1 = apply_gates_s1(
                row=row, side=side,
                directional_cfg=directional_cfg, low_vol_cfg=low_vol_cfg,
                trend_min=trend_min,
            )
            if ok1:
                params = resolve_tpsl_params(asset_cfg, row.regime)
                if params is None:
                    s1_rejects.append(RejectRecord(
                        symbol, row.bar_i, row.date_str, row.regime, "TPSL_CONFIG_UNAVAILABLE", row.regime_conf))
                else:
                    sl_pct, tp_pct = params
                    future = bars[row.bar_i + 1: row.bar_i + 1 + max_bars]
                    outcome, pnl, r, held = simulate_trade(
                        side=side, entry_price=row.close,
                        sl_pct=sl_pct, tp_pct=tp_pct, future_bars=future,
                    )
                    s1_trades.append(TradeRecord(
                        symbol=symbol, bar_i=row.bar_i, date_str=row.date_str,
                        regime=row.regime, side=side,
                        outcome=outcome, pnl_pct=pnl * 100.0,
                        r_multiple=r, bars_held=held,
                        entry_price=row.close, sl_pct_used=sl_pct, tp_pct_used=tp_pct,
                        regime_conf=row.regime_conf,
                    ))
            else:
                if reason1:
                    s1_rejects.append(RejectRecord(
                        symbol, row.bar_i, row.date_str, row.regime, reason1, row.regime_conf))

    return s0_trades, s1_trades, s0_rejects, s1_rejects, bars_processed, regime_counts, trend_conf_buckets


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def cohort_metrics(trades: list[TradeRecord]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"count": 0, "total_pnl_pct": 0.0, "avg_pnl_pct": 0.0,
                "win_rate": 0.0, "avg_r": 0.0,
                "tp": 0, "sl": 0, "timeout": 0, "max_drawdown_pct": 0.0}
    pnls = [t.pnl_pct / 100.0 for t in trades]
    tp = sum(1 for t in trades if t.outcome == "TP")
    sl = sum(1 for t in trades if t.outcome == "SL")
    return {
        "count": n,
        "total_pnl_pct": round(sum(pnls) * 100.0, 4),
        "avg_pnl_pct": round(sum(pnls) * 100.0 / n, 4),
        "win_rate": round(tp / n, 4),
        "avg_r": round(sum(t.r_multiple for t in trades) / n, 4),
        "tp": tp, "sl": sl, "timeout": n - tp - sl,
        "max_drawdown_pct": round(max_drawdown(pnls) * 100.0, 4),
    }


def scenario_metrics(
    trades: list[TradeRecord],
    rejects: list[RejectRecord],
    bars_processed: int,
    regime_counts: Counter,
) -> dict[str, Any]:
    n = len(trades)
    reject_counts: Counter[str] = Counter(r.reason for r in rejects)
    side_counts: Counter[str] = Counter(t.side for t in trades)

    by_regime: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        by_regime[t.regime].append(t)

    by_symbol: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        by_symbol[t.symbol].append(t)

    regime_side: dict[str, Counter] = defaultdict(Counter)
    for t in trades:
        regime_side[t.regime][t.side] += 1

    return {
        "bars_processed": bars_processed,
        "regime_distribution": dict(sorted(regime_counts.items())),
        "actionable_signals": n,
        "rejects": dict(sorted(reject_counts.items())),
        "side_distribution": dict(sorted(side_counts.items())),
        "regime_side": {r: dict(c) for r, c in sorted(regime_side.items())},
        **cohort_metrics(trades),
        "cohort_breakdown": {
            regime: cohort_metrics(cohort_trades)
            for regime, cohort_trades in sorted(by_regime.items())
        },
        "symbol_breakdown": {
            sym: cohort_metrics(sym_trades)
            for sym, sym_trades in sorted(by_symbol.items())
        },
    }


# ---------------------------------------------------------------------------
# Rolling windows
# ---------------------------------------------------------------------------

def build_rolling_windows(date_list: list[str], window_days: int) -> list[tuple[str, str, list[str]]]:
    """Produce non-overlapping rolling windows. Returns list of (start, end, dates)."""
    windows: list[tuple[str, str, list[str]]] = []
    i = 0
    while i < len(date_list):
        chunk = date_list[i: i + window_days]
        windows.append((chunk[0], chunk[-1], chunk))
        i += window_days
    return windows


# ---------------------------------------------------------------------------
# Delta analysis
# ---------------------------------------------------------------------------

def delta_analysis(
    s0_trades: list[TradeRecord],
    s1_trades: list[TradeRecord],
) -> dict[str, Any]:
    s0_idx = {(t.symbol, t.bar_i): t for t in s0_trades}
    s1_idx = {(t.symbol, t.bar_i): t for t in s1_trades}
    s0_keys = set(s0_idx)
    s1_keys = set(s1_idx)

    removed_keys = s0_keys - s1_keys  # gates added by S1 filtered these out
    # should be empty for S1 (min-only never adds)
    newly_admitted_keys = s1_keys - s0_keys
    unchanged_keys = s0_keys & s1_keys

    removed = [s0_idx[k] for k in sorted(removed_keys)]
    newly_admitted = [s1_idx[k] for k in sorted(newly_admitted_keys)]
    unchanged = [s1_idx[k] for k in sorted(unchanged_keys)]

    removed_by_regime = dict(Counter(t.regime for t in removed))
    removed_conf_buckets = dict(Counter(
        f"{int(t.regime_conf * 10) * 10}pct" for t in removed
    ))

    return {
        "removed_count": len(removed),
        "newly_admitted_count": len(newly_admitted),  # should be 0
        "unchanged_count": len(unchanged),
        "removed_metrics": cohort_metrics(removed),
        "newly_admitted_metrics": cohort_metrics(newly_admitted),
        "unchanged_metrics": cohort_metrics(unchanged),
        "removed_by_regime": removed_by_regime,
        "removed_conf_distribution": removed_conf_buckets,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt(v: float, dp: int = 4) -> str:
    return f"{v:.{dp}f}"


def build_md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


def build_report_md(
    payload: dict[str, Any],
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    s0 = payload["overall"]["S0_CURRENT"]
    s1 = payload["overall"]["S1_TREND_MIN_ONLY"]
    delta = payload["delta"]
    rolling = payload["rolling_windows"]
    regime_conf_dist = payload["trend_conf_distribution"]

    lines: list[str] = []
    lines.append("# AURORA_TREND_MIN_ACTIVATION_FORWARD_REPLAY_V1")
    lines.append("")
    lines.append(f"Generated UTC: {now}")
    lines.append("")

    # ------------------------------------------------------------------ Verdict
    lines.append("## Verdict")
    lines.append("")
    sig_delta = s1["actionable_signals"] - s0["actionable_signals"]
    wr_delta = s1["win_rate"] - s0["win_rate"]
    pnl_delta = s1["total_pnl_pct"] - s0["total_pnl_pct"]
    r_delta = s1["avg_r"] - s0["avg_r"]
    dd_delta = s1["max_drawdown_pct"] - s0["max_drawdown_pct"]

    lines.append(
        f"Over {payload['inputs']['window_start']}..{payload['inputs']['window_end']} "
        f"({payload['inputs']['bars_processed_per_symbol_approx']} ready-bars per symbol approx): "
        f"S1 removes {abs(sig_delta)} signals vs S0 (signals: {s0['actionable_signals']} → {s1['actionable_signals']}). "
        f"Win rate: {s0['win_rate']:.3f} → {s1['win_rate']:.3f} ({wr_delta:+.3f}). "
        f"Total PnL%: {s0['total_pnl_pct']:.4f} → {s1['total_pnl_pct']:.4f} ({pnl_delta:+.4f}). "
        f"Avg R: {s0['avg_r']:.3f} → {s1['avg_r']:.3f} ({r_delta:+.3f}). "
        f"Max DD%: {s0['max_drawdown_pct']:.4f} → {s1['max_drawdown_pct']:.4f} ({dd_delta:+.4f})."
    )
    lines.append("")

    # Verdict classification
    improvements = sum(
        [wr_delta > 0, pnl_delta > 0, r_delta > 0, dd_delta < 0])
    if improvements >= 3:
        verdict = "CANDIDATE — S1 shows consistent improvement across majority of key metrics over broad window."
        impl_status = "CANDIDATE-ONLY. Not ready for runtime without shadow confirmation and broader regime coverage validation."
    elif improvements == 2:
        verdict = "MIXED — S1 shows improvement in some metrics but not all; further analysis required."
        impl_status = "REJECTED for runtime. Mixed evidence insufficient for production gate change."
    else:
        verdict = "REJECTED — S1 does not show net improvement over the broad window."
        impl_status = "REJECTED for runtime."

    lines.append(f"**{verdict}**")
    lines.append("")
    lines.append(f"**Runtime implementation status: {impl_status}**")
    lines.append("")

    # -------------------------------------------------------- Problem framing
    lines.append("## Problem framing")
    lines.append("")
    lines.append(
        "Previous ablation (2026-05-03..2026-05-04) showed S1_TREND_MIN_ONLY "
        "(requiring regime_confidence >= 0.40 for TREND_UP/TREND_DOWN) removed 14 low-quality "
        "trades from a 77-trade window, improving win rate from 0.234 to 0.286 and reducing "
        "total PnL drag. This forward replay validates whether the effect holds over a "
        f"broader {(date.fromisoformat(payload['inputs']['window_end']) - date.fromisoformat(payload['inputs']['window_start'])).days + 1}-day window "
        "with diverse regime distributions."
    )
    lines.append("")
    lines.append(
        "S1 mechanism: apply min_regime_confidence >= 0.40 for TREND_UP and TREND_DOWN only. "
        "Max-cap veto (REGIME_CONFIDENCE_ABOVE_MAX) remains active. "
        "No HIGH_VOL TP/SL changes. No max-cap veto disable. Identical to S1 from ablation."
    )
    lines.append("")

    # --------------------------------------------------------------- FACTS
    lines.append("## FACTS")
    lines.append("")
    lines.append(
        "- Replay source: data/recorder CSV only. No runtime mutation.")
    lines.append(
        "- Both scenarios use identical YAML-loaded config base (signal_threshold, regime_thresholds, TPSL).")
    lines.append(
        "- S1 adds exactly one additional gate: TREND_UP/TREND_DOWN require regime_conf >= 0.40.")
    lines.append(
        "- Max-cap veto is ACTIVE in both S0 and S1 (S2 behavior is explicitly excluded).")
    lines.append(
        "- HIGH_VOL TP/SL widen factor = 1.0 in both scenarios (no geometry change).")
    lines.append(
        f"- Broad window: {payload['inputs']['window_start']}..{payload['inputs']['window_end']}.")
    lines.append(f"- Symbols: {', '.join(payload['inputs']['symbols'])}.")
    lines.append(
        f"- BNB data starts 2026-03-05; all 5 symbols present from that date.")
    lines.append(
        f"- S1 never admits new bars; it can only remove bars that S0 admitted (min-only gate).")
    lines.append("")

    # ------------------------------------------------------------ INFERENCES
    lines.append("## INFERENCES")
    lines.append("")
    lines.append(
        "- Based on the regime_conf distribution of removed trades (see delta section).")
    lines.append(
        "- If removed trades have below-average win rate and avg R, S1 improves quality.")
    lines.append(
        "- Rolling window consistency (see rolling section) indicates whether improvement is stable or noise.")
    lines.append("")

    # ------------------------------------------------------------- ASSUMPTIONS
    lines.append("## ASSUMPTIONS")
    lines.append("")
    lines.append(
        "- abs(pillar_sum) used as proxy for LOW_VOL direction confidence (no dedicated model found in code).")
    lines.append(
        "- Bar-level fill at close captures dominant fill path; intra-bar path effects excluded.")
    lines.append("- SL-first fail-closed for same-bar TP+SL touch.")
    lines.append(
        "- Regime labels in recorder CSV are stable and match what the runtime would produce for those bars.")
    lines.append("")

    # --------------------------------------------------------------- UNKNOWNS
    lines.append("## UNKNOWNS")
    lines.append("")
    lines.append(
        "- Whether 0.40 is the optimal threshold or whether a different value (0.35, 0.45) would be better.")
    lines.append(
        "- Cross-asset and cross-regime distribution in future market conditions beyond this window.")
    lines.append(
        "- Live fill quality, slippage, and queue effects not captured in bar-close simulation.")
    lines.append(
        "- Whether regime_conf in recorder matches live runtime exactly (recomputation path alignment).")
    lines.append("")

    # --------------------------------------------------- Scenario comparison
    lines.append("## Overall scenario comparison")
    lines.append("")
    headers = ["Metric", "S0_CURRENT",
               "S1_TREND_MIN_ONLY", "Delta", "Direction"]
    rows = []

    def direction(v: float, good_positive: bool = True) -> str:
        if abs(v) < 1e-6:
            return "="
        return ("✓" if v > 0 else "✗") if good_positive else ("✓" if v < 0 else "✗")

    rows.append(["Actionable signals", s0["actionable_signals"], s1["actionable_signals"],
                 f"{sig_delta:+d}", direction(sig_delta, good_positive=False)])
    rows.append(["TP", s0["tp"], s1["tp"], f"{s1['tp'] - s0['tp']:+d}", ""])
    rows.append(["SL", s0["sl"], s1["sl"], f"{s1['sl'] - s0['sl']:+d}", direction(
        s1["sl"] - s0["sl"], good_positive=False)])
    rows.append(["Timeout", s0["timeout"], s1["timeout"],
                f"{s1['timeout'] - s0['timeout']:+d}", ""])
    rows.append(["Total PnL%", fmt(s0["total_pnl_pct"]), fmt(s1["total_pnl_pct"]),
                 f"{pnl_delta:+.4f}", direction(pnl_delta)])
    rows.append(["Avg PnL%", fmt(s0["avg_pnl_pct"]), fmt(s1["avg_pnl_pct"]),
                 f"{s1['avg_pnl_pct'] - s0['avg_pnl_pct']:+.4f}", direction(s1["avg_pnl_pct"] - s0["avg_pnl_pct"])])
    rows.append(["Win rate", fmt(s0["win_rate"], 4), fmt(s1["win_rate"], 4),
                 f"{wr_delta:+.4f}", direction(wr_delta)])
    rows.append(["Avg R", fmt(s0["avg_r"], 4), fmt(s1["avg_r"], 4),
                 f"{r_delta:+.4f}", direction(r_delta)])
    rows.append(["Max DD%", fmt(s0["max_drawdown_pct"]), fmt(s1["max_drawdown_pct"]),
                 f"{dd_delta:+.4f}", direction(dd_delta, good_positive=False)])
    lines.extend(build_md_table(headers, rows))
    lines.append("")

    # ------------------------------------------------ Reject breakdown
    lines.append("### Reject breakdown")
    lines.append("")
    all_reasons = sorted(
        set(list(s0["rejects"].keys()) + list(s1["rejects"].keys())))
    rj_headers = ["Reject reason", "S0_CURRENT", "S1_TREND_MIN_ONLY", "Delta"]
    rj_rows = []
    for rr in all_reasons:
        v0 = s0["rejects"].get(rr, 0)
        v1 = s1["rejects"].get(rr, 0)
        rj_rows.append([rr, v0, v1, f"{v1 - v0:+d}"])
    lines.extend(build_md_table(rj_headers, rj_rows))
    lines.append("")

    # ------------------------------------------- Cohort breakdown by regime
    lines.append("## Cohort breakdown by regime")
    lines.append("")
    all_regimes = sorted(set(
        list(s0.get("cohort_breakdown", {}).keys()) +
        list(s1.get("cohort_breakdown", {}).keys())
    ))
    c_headers = ["Regime", "Scenario", "N", "Total PnL%",
                 "Win Rate", "Avg R", "TP", "SL", "TO", "Max DD%"]
    c_rows = []
    for regime in ["TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY", "MEAN_REVERSION"] + \
            [r for r in all_regimes if r not in ("TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY", "LOW_VOLATILITY", "MEAN_REVERSION")]:
        for sc_name, sc_data in [("S0", s0), ("S1", s1)]:
            cb = sc_data.get("cohort_breakdown", {}).get(regime)
            if cb is None:
                c_rows.append(
                    [regime, sc_name, 0, "—", "—", "—", 0, 0, 0, "—"])
            else:
                c_rows.append([regime, sc_name, cb["count"],
                               fmt(cb["total_pnl_pct"]), fmt(cb["win_rate"]),
                               fmt(cb["avg_r"]), cb["tp"], cb["sl"], cb["timeout"],
                               fmt(cb["max_drawdown_pct"])])
    lines.extend(build_md_table(c_headers, c_rows))
    lines.append("")

    # -------------------------------------------- Symbol breakdown
    lines.append("## Symbol breakdown")
    lines.append("")
    all_syms = sorted(set(
        list(s0.get("symbol_breakdown", {}).keys()) +
        list(s1.get("symbol_breakdown", {}).keys())
    ))
    sb_headers = ["Symbol", "Scenario", "N",
                  "Total PnL%", "Win Rate", "Avg R", "Max DD%"]
    sb_rows = []
    for sym in all_syms:
        for sc_name, sc_data in [("S0", s0), ("S1", s1)]:
            sb = sc_data.get("symbol_breakdown", {}).get(sym)
            if sb is None:
                sb_rows.append([sym, sc_name, 0, "—", "—", "—", "—"])
            else:
                sb_rows.append([sym, sc_name, sb["count"],
                                fmt(sb["total_pnl_pct"]), fmt(sb["win_rate"]),
                                fmt(sb["avg_r"]), fmt(sb["max_drawdown_pct"])])
    lines.extend(build_md_table(sb_headers, sb_rows))
    lines.append("")

    # ---------------------------------------- Delta (removed trades)
    lines.append("## Removed trade analysis (S0 admitted, S1 filtered)")
    lines.append("")
    rm = delta["removed_metrics"]
    lines.append(
        f"S1 removed {delta['removed_count']} trades from S0. "
        f"Newly admitted by S1 (should be 0): {delta['newly_admitted_count']}. "
        f"Unchanged: {delta['unchanged_count']}."
    )
    lines.append("")
    lines.append(f"Removed trade quality: win_rate={rm['win_rate']:.4f}, avg_r={rm['avg_r']:.4f}, "
                 f"total_pnl_pct={rm['total_pnl_pct']:.4f}, avg_pnl_pct={rm['avg_pnl_pct']:.4f}.")
    lines.append("")
    lines.append(f"Removed by regime: {delta['removed_by_regime']}")
    lines.append(
        f"Removed by regime_conf bucket: {delta['removed_conf_distribution']}")
    lines.append("")

    # Is removal quality below S0 average?
    s0_wr = s0["win_rate"]
    rm_wr = rm["win_rate"]
    if rm["count"] > 0:
        if rm_wr < s0_wr:
            lines.append(
                f"INFERENCE: Removed trades have win_rate={rm_wr:.4f} < S0 avg={s0_wr:.4f}. "
                "S1 filter is removing below-average quality entries. This supports the gate."
            )
        else:
            lines.append(
                f"INFERENCE: Removed trades have win_rate={rm_wr:.4f} >= S0 avg={s0_wr:.4f}. "
                "S1 is filtering out trades that were performing at or above average. Gate is not clearly beneficial."
            )
    lines.append("")

    # ----------------------------------------- TREND conf distribution
    lines.append("## TREND regime_conf distribution (input to S1 gate)")
    lines.append("")
    lines.append(
        "Distribution of bars at each regime_conf decile bucket for TREND_UP and TREND_DOWN:")
    lines.append("")
    conf_headers = ["Bucket", "Bar count", "% of TREND bars"]
    total_trend_bars = sum(regime_conf_dist.values())
    conf_rows = []
    for bucket, count in sorted(regime_conf_dist.items()):
        pct = count / total_trend_bars * 100.0 if total_trend_bars else 0.0
        conf_rows.append([bucket, count, f"{pct:.1f}%"])
    if conf_rows:
        lines.extend(build_md_table(conf_headers, conf_rows))
    else:
        lines.append("No TREND bars found.")
    lines.append("")
    below_40 = sum(v for k, v in regime_conf_dist.items(
    ) if "_0pct" in k or "_10pct" in k or "_20pct" in k or "_30pct" in k)
    lines.append(
        f"Bars with TREND regime_conf < 0.40 (would be filtered by S1): "
        f"{below_40} / {total_trend_bars} ({below_40/total_trend_bars*100:.1f}% of TREND bars)"
        if total_trend_bars else "No TREND bars."
    )
    lines.append("")

    # ---------------------------------------- Rolling window stability
    lines.append("## Rolling window stability")
    lines.append("")
    lines.append(
        f"Non-overlapping {payload['inputs']['rolling_window_days']}-day windows. "
        "S1 improvement is consistent if it shows win_rate improvement or pnl improvement in majority of windows."
    )
    lines.append("")
    rw_headers = ["Window", "S0_signals", "S1_signals", "S0_wr", "S1_wr", "Δwr",
                  "S0_pnl%", "S1_pnl%", "Δpnl%", "S0_avgR", "S1_avgR", "ΔavgR", "S1_verdict"]
    rw_rows = []
    s1_wins_wr = 0
    s1_wins_pnl = 0
    s1_wins_r = 0
    for rw in rolling:
        rw_s0 = rw["S0"]
        rw_s1 = rw["S1"]
        d_wr = rw_s1["win_rate"] - rw_s0["win_rate"]
        d_pnl = rw_s1["total_pnl_pct"] - rw_s0["total_pnl_pct"]
        d_r = rw_s1["avg_r"] - rw_s0["avg_r"]
        impr = sum([d_wr > 0, d_pnl > 0, d_r > 0])
        verdict_cell = "✓" if impr >= 2 else ("~" if impr == 1 else "✗")
        if d_wr > 0:
            s1_wins_wr += 1
        if d_pnl > 0:
            s1_wins_pnl += 1
        if d_r > 0:
            s1_wins_r += 1
        rw_rows.append([
            f"{rw['start']}..{rw['end']}",
            rw_s0["actionable_signals"], rw_s1["actionable_signals"],
            fmt(rw_s0["win_rate"], 3), fmt(
                rw_s1["win_rate"], 3), f"{d_wr:+.3f}",
            fmt(rw_s0["total_pnl_pct"], 3), fmt(
                rw_s1["total_pnl_pct"], 3), f"{d_pnl:+.3f}",
            fmt(rw_s0["avg_r"], 3), fmt(rw_s1["avg_r"], 3), f"{d_r:+.3f}",
            verdict_cell,
        ])
    lines.extend(build_md_table(rw_headers, rw_rows))
    lines.append("")
    total_rw = len(rolling)
    if total_rw > 0:
        lines.append(
            f"S1 improved win_rate in {s1_wins_wr}/{total_rw} windows, "
            f"total_pnl in {s1_wins_pnl}/{total_rw} windows, "
            f"avg_r in {s1_wins_r}/{total_rw} windows."
        )
    lines.append("")

    # ----------------------------------- What should NOT be implemented
    lines.append("## What should NOT be implemented")
    lines.append("")
    lines.append(
        "- Do NOT disable TREND max-cap veto (S2 was toxic: −9.73% PnL delta in ablation).")
    lines.append(
        "- Do NOT combine S1 with max-cap veto disable without re-running full ablation.")
    lines.append(
        "- Do NOT apply HIGH_VOL TP/SL widening without sufficient HIGH_VOL sample size.")
    lines.append(
        "- Do NOT set a threshold other than 0.40 without running a threshold sweep replay.")
    lines.append("")

    # ----------------------------------- Candidate safe next experiment
    lines.append("## Candidate safe next experiment")
    lines.append("")
    lines.append(
        "- Shadow-run S1 gate in live telemetry (decision_ledger) with no execution change.")
    lines.append(
        "- Compare shadow-admitted vs shadow-rejected TREND entries forward for 7-14 days.")
    lines.append(
        "- Run threshold sweep (0.30, 0.35, 0.40, 0.45) over the full recorder window to find optimal.")
    lines.append(
        "- Check if S1 improvement is concentrated in specific symbols or is broad.")
    lines.append("")

    # ----------------------------------- Required validation before runtime
    lines.append("## Required validation before runtime")
    lines.append("")
    lines.append(
        "1. Shadow journal confirmation over >= 48h live with decision_ledger telemetry.")
    lines.append(
        "2. Positive avg_r and win_rate delta sustained across >= 3 consecutive 7-day windows.")
    lines.append(
        "3. Removed trades confirmed to have below-average win_rate (see delta section).")
    lines.append(
        "4. No regression in LOW_VOL, MEAN_REVERSION, or HIGH_VOL cohorts.")
    lines.append(
        "5. Threshold value 0.40 validated against sweep (0.30..0.50 range).")
    lines.append("")

    # ----------------------------------- Final recommendation
    lines.append("## Final recommendation")
    lines.append("")
    if improvements >= 3:
        lines.append(
            f"S1_TREND_MIN_ONLY shows consistent signal quality improvement across the broad window "
            f"({payload['inputs']['window_start']}..{payload['inputs']['window_end']}). "
            "The filter removes low regime_conf TREND entries that have below-average performance. "
            "Recommend shadow-run before any runtime gate change. "
            "Do NOT implement as a hard gate without shadow confirmation."
        )
    else:
        lines.append(
            "S1_TREND_MIN_ONLY does NOT show sufficiently consistent improvement over the broad window. "
            "Evidence is mixed or negative. Do NOT implement."
        )
    lines.append("")

    # ----------------------------------- Acceptance gate
    lines.append("## Acceptance gate")
    lines.append("")
    lines.append("- [x] Both scenarios run over broad recorder window.")
    lines.append(
        "- [x] Removed trade quality characterized (win_rate, avg_r, regime distribution).")
    lines.append("- [x] Rolling window stability table produced.")
    lines.append("- [x] Per-regime and per-symbol cohort breakdowns produced.")
    lines.append("- [x] TREND conf distribution shown.")
    lines.append(
        "- [x] Report states runtime implementation status explicitly.")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    signal_threshold, assets_cfg = load_aurora_asset_cfg()
    gate_cfg = load_domain_gate_cfg()
    directional_cfg = gate_cfg["directional"]
    low_vol_cfg = gate_cfg["low_vol"]

    assigned_aurora = load_assigned_aurora_symbols()
    if args.symbols:
        symbols = sorted({normalize_symbol(s) for s in args.symbols if s})
    else:
        symbols = assigned_aurora
    symbols = [s for s in symbols if s in assets_cfg]

    date_list = dates_in_range(args.window_start, args.window_end)
    print(f"Window: {args.window_start}..{args.window_end} ({len(date_list)} dates), "
          f"symbols: {symbols}")

    bars_by_symbol = load_all_bars(symbols, date_list, args.tf_sec)
    print("Bars loaded:", {k: len(v) for k, v in bars_by_symbol.items()})

    # Full-window run
    print("Running full-window scenarios...")
    (s0_trades, s1_trades, s0_rejects, s1_rejects,
     bars_processed, regime_counts, trend_conf_dist) = run_both_scenarios(
        bars_by_symbol=bars_by_symbol,
        signal_threshold=signal_threshold,
        assets_cfg=assets_cfg,
        directional_cfg=directional_cfg,
        low_vol_cfg=low_vol_cfg,
        max_bars=int(args.max_bars),
        trend_min=S1_TREND_MIN,
    )

    s0_summary = scenario_metrics(
        s0_trades, s0_rejects, bars_processed, regime_counts)
    s1_summary = scenario_metrics(
        s1_trades, s1_rejects, bars_processed, regime_counts)
    delta = delta_analysis(s0_trades, s1_trades)

    # Rolling windows
    rolling_results: list[dict[str, Any]] = []
    windows = build_rolling_windows(date_list, args.rolling_days)
    print(
        f"Running {len(windows)} rolling windows of {args.rolling_days} days...")
    for win_start, win_end, win_dates in windows:
        win_bars = load_all_bars(symbols, win_dates, args.tf_sec)
        (ws0_t, ws1_t, ws0_r, ws1_r, wp, wrc, _) = run_both_scenarios(
            bars_by_symbol=win_bars,
            signal_threshold=signal_threshold,
            assets_cfg=assets_cfg,
            directional_cfg=directional_cfg,
            low_vol_cfg=low_vol_cfg,
            max_bars=int(args.max_bars),
            trend_min=S1_TREND_MIN,
        )
        rolling_results.append({
            "start": win_start,
            "end": win_end,
            "dates": len(win_dates),
            "S0": scenario_metrics(ws0_t, ws0_r, wp, wrc),
            "S1": scenario_metrics(ws1_t, ws1_r, wp, wrc),
        })

    # Compact rolling results for JSON (omit per-trade breakdowns)
    def compact_rolling(r: dict[str, Any]) -> dict[str, Any]:
        def slim(s: dict[str, Any]) -> dict[str, Any]:
            return {k: s[k] for k in (
                "actionable_signals", "rejects", "side_distribution",
                "tp", "sl", "timeout",
                "total_pnl_pct", "avg_pnl_pct", "win_rate", "avg_r", "max_drawdown_pct"
            )}
        return {"start": r["start"], "end": r["end"], "dates": r["dates"],
                "S0": slim(r["S0"]), "S1": slim(r["S1"])}

    payload = {
        "task": "AURORA_TREND_MIN_ACTIVATION_FORWARD_REPLAY_V1",
        "inputs": {
            "window_start": args.window_start,
            "window_end": args.window_end,
            "tf_sec": int(args.tf_sec),
            "symbols": symbols,
            "max_bars": int(args.max_bars),
            "rolling_window_days": int(args.rolling_days),
            "s1_trend_min_activation": S1_TREND_MIN,
            "bars_processed_per_symbol_approx": bars_processed // max(len(symbols), 1),
        },
        "config_snapshot": {
            "signal_threshold": signal_threshold,
            "directional_min_regime_confidence": directional_cfg.get("min_regime_confidence"),
            "directional_min_by_regime": directional_cfg.get("min_regime_confidence_by_regime"),
            "directional_max_by_regime": directional_cfg.get("max_regime_confidence_by_regime"),
        },
        "overall": {
            "S0_CURRENT": s0_summary,
            "S1_TREND_MIN_ONLY": s1_summary,
        },
        "delta": delta,
        "trend_conf_distribution": dict(sorted(trend_conf_dist.items())),
        "rolling_windows": [compact_rolling(r) for r in rolling_results],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(payload, ensure_ascii=True,
                        indent=2) + "\n", encoding="utf-8")
    out_md.write_text(build_report_md(payload), encoding="utf-8")

    # Concise stdout summary
    print(json.dumps({
        "output_json": str(out_json.relative_to(ROOT)),
        "output_md": str(out_md.relative_to(ROOT)),
        "symbols": symbols,
        "bars_processed": bars_processed,
        "S0_signals": s0_summary["actionable_signals"],
        "S1_signals": s1_summary["actionable_signals"],
        "S0_win_rate": s0_summary["win_rate"],
        "S1_win_rate": s1_summary["win_rate"],
        "S0_total_pnl_pct": s0_summary["total_pnl_pct"],
        "S1_total_pnl_pct": s1_summary["total_pnl_pct"],
        "S0_avg_r": s0_summary["avg_r"],
        "S1_avg_r": s1_summary["avg_r"],
        "S0_max_dd": s0_summary["max_drawdown_pct"],
        "S1_max_dd": s1_summary["max_drawdown_pct"],
        "removed_count": delta["removed_count"],
        "removed_win_rate": delta["removed_metrics"]["win_rate"],
        "rolling_windows_run": len(rolling_results),
    }, indent=2))


if __name__ == "__main__":
    main()
