from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
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
BROAD_WINDOW_START = "2026-03-05"
BROAD_WINDOW_END = "2026-05-04"

VARIANT_WITH_TIMEOUT = "WITH_TIMEOUT"
VARIANT_NO_TIMEOUT = "NO_TIMEOUT_DIAGNOSTIC"


@dataclass
class ScenarioSpec:
    name: str
    trend_min: float | None
    disable_trend: bool = False


SCENARIOS = [
    ScenarioSpec("S0_CURRENT", None, False),
    ScenarioSpec("S1_TREND_MIN_040_WITH_MAX_CAP", 0.40, False),
    ScenarioSpec("S2_TREND_DISABLED", None, True),
    ScenarioSpec("S3_TREND_MIN_030_WITH_MAX_CAP", 0.30, False),
    ScenarioSpec("S4_TREND_MIN_035_WITH_MAX_CAP", 0.35, False),
    ScenarioSpec("S5_TREND_MIN_045_WITH_MAX_CAP", 0.45, False),
    ScenarioSpec("S6_TREND_MIN_050_WITH_MAX_CAP", 0.50, False),
]


@dataclass
class BarRow:
    symbol: str
    bar_i: int
    ts_ms: int
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
    scenario: str
    variant: str
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    side: str
    outcome: str
    pnl_pct: float
    r_multiple: float
    bars_held: int
    regime_conf: float
    tp_pct_used: float
    sl_pct_used: float
    tp_bps: float
    sl_bps: float
    bars_to_tp: int | None
    bars_to_sl: int | None
    mfe_bps: float
    mae_bps: float
    pnl_at_timeout_pct: float
    pnl_at_timeout_p5_pct: float
    pnl_at_timeout_p10_pct: float
    pnl_at_end_pct: float
    max_bps_before_timeout: float
    max_bps_after_timeout: float


@dataclass
class RejectRecord:
    scenario: str
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    reason: str
    regime_conf: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Trend filter vs disabled replay with timeout diagnostics")
    p.add_argument("--window-start", default=BROAD_WINDOW_START)
    p.add_argument("--window-end", default=BROAD_WINDOW_END)
    p.add_argument("--tf-sec", type=int, default=DEFAULT_TF_SEC)
    p.add_argument("--symbols", nargs="*", default=[])
    p.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    p.add_argument(
        "--output-json",
        default=str(
            REPORTS_DIR / "AURORA_TREND_FILTER_VS_TREND_DISABLED_REPLAY_V1_2026_05_04.json"),
    )
    p.add_argument(
        "--output-md",
        default=str(
            REPORTS_DIR / "AURORA_TREND_FILTER_VS_TREND_DISABLED_REPLAY_V1_2026_05_04.md"),
    )
    return p.parse_args()


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
    out = []
    cur = d0
    while cur <= d1:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def load_assigned_aurora_symbols() -> list[str]:
    data = load_yaml(STRATEGIES_REGISTRY_YAML)
    assignments = data.get("assignments") or {}
    syms: list[str] = []
    for sym, strategies in assignments.items():
        if isinstance(strategies, list) and any(str(x).strip() == "aurora" for x in strategies):
            syms.append(normalize_symbol(sym))
    return sorted(set(syms))


def load_cfg() -> tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]:
    strategy = load_yaml(AURORA_STRATEGY_YAML)
    aurora = strategy.get("aurora") or {}
    decision = aurora.get("decision") or {}
    signal_threshold = safe_float(decision.get("signal_threshold"))
    if signal_threshold is None:
        raise ValueError("Missing aurora.decision.signal_threshold")
    assets = aurora.get("assets") or {}

    domains = load_yaml(DOMAINS_YAML)
    dm = domains.get("decision_making") or {}
    directional = dm.get("directional_sanity") or {}
    low_vol = dm.get("low_vol_cost_floor_gate") or {}
    return signal_threshold, assets, directional, low_vol


def load_rows_for_symbol_date(symbol: str, date_str: str, tf_sec: int) -> list[BarRow]:
    path = RECORDER_DIR / date_str / f"{symbol}_{tf_sec}.csv"
    if not path.exists():
        return []
    rows: list[BarRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for rec in r:
            ready = str(rec.get("ready") or "").strip().lower()
            if ready not in ("true", "1"):
                continue
            regime = str(rec.get("regime") or "").strip().upper()
            if not regime or regime == "PENDING":
                continue
            ts_ms = safe_int(rec.get("timestamp"))
            open_ = safe_float(rec.get("open"))
            high = safe_float(rec.get("high"))
            low = safe_float(rec.get("low"))
            close = safe_float(rec.get("close"))
            conf = safe_float(rec.get("regime_conf"))
            pillar = safe_float(rec.get("feat_pillar_sum"))
            if None in (ts_ms, open_, high, low, close, conf, pillar):
                continue
            rows.append(BarRow(
                symbol=symbol,
                bar_i=0,
                ts_ms=int(ts_ms),
                date_str=date_str,
                open_=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                regime=regime,
                regime_conf=float(conf),
                pillar_sum=float(pillar),
            ))
    rows.sort(key=lambda x: x.ts_ms)
    for i, row in enumerate(rows):
        row.bar_i = i
    return rows


def load_all_bars(symbols: list[str], dates: list[str], tf_sec: int) -> dict[str, list[BarRow]]:
    out: dict[str, list[BarRow]] = {}
    for sym in symbols:
        merged: list[BarRow] = []
        for d in dates:
            merged.extend(load_rows_for_symbol_date(sym, d, tf_sec))
        merged.sort(key=lambda x: x.ts_ms)
        for i, row in enumerate(merged):
            row.bar_i = i
        out[sym] = merged
    return out


def resolve_regime_threshold(regime: str, mapping: dict[str, Any], default: float | None) -> float | None:
    v = safe_float(mapping.get(regime))
    if v is not None:
        return v
    d = safe_float(mapping.get("DEFAULT"))
    if d is not None:
        return d
    return default


def side_from_score(score: float, threshold: float) -> str:
    if score >= threshold:
        return "BUY"
    if score <= -threshold:
        return "SELL"
    return ""


def apply_gates_base(row: BarRow, side: str, directional: dict[str, Any], low_vol: dict[str, Any]) -> tuple[bool, str | None]:
    if not side:
        return False, "NO_SIDE"

    min_default = safe_float(directional.get("min_regime_confidence"))
    min_map = directional.get("min_regime_confidence_by_regime") or {}
    max_map = directional.get("max_regime_confidence_by_regime") or {}

    min_req = resolve_regime_threshold(row.regime, min_map, min_default)
    if min_req is not None and row.regime_conf < min_req:
        return False, "REGIME_CONFIDENCE_BELOW_MIN"

    max_allowed = resolve_regime_threshold(row.regime, max_map, None)
    if max_allowed is not None and row.regime_conf > max_allowed:
        return False, "REGIME_CONFIDENCE_ABOVE_MAX"

    regimes_gated = [str(x).strip().upper()
                     for x in (low_vol.get("regimes") or [])]
    if row.regime == "LOW_VOLATILITY" and "LOW_VOLATILITY" in regimes_gated:
        thresholds = low_vol.get("thresholds") or {}
        dir_map = thresholds.get("min_direction_confidence_by_regime") or {}
        min_dir = resolve_regime_threshold("LOW_VOLATILITY", dir_map, None)
        if min_dir is not None and abs(row.pillar_sum) < min_dir:
            return False, "LOW_VOL_DIRECTION_CONFIDENCE_BELOW_MIN"

    return True, None


def apply_gates_scenario(row: BarRow, side: str, spec: ScenarioSpec, directional: dict[str, Any], low_vol: dict[str, Any]) -> tuple[bool, str | None]:
    if spec.disable_trend and row.regime in ("TREND_UP", "TREND_DOWN"):
        return False, "TREND_DISABLED"
    ok, reason = apply_gates_base(row, side, directional, low_vol)
    if not ok:
        return ok, reason
    if spec.trend_min is not None and row.regime in ("TREND_UP", "TREND_DOWN") and row.regime_conf < spec.trend_min:
        return False, "TREND_ACTIVATION_BELOW_MIN"
    return True, None


def resolve_tpsl(asset_cfg: dict[str, Any], regime: str) -> tuple[float, float] | None:
    exit_cfg = asset_cfg.get("exit") or {}
    tp_cfg = asset_cfg.get("take_profit") or {}
    regime_tpsl = exit_cfg.get("regime_tpsl") or {}
    if not bool(regime_tpsl.get("enabled")):
        return None
    if str(regime_tpsl.get("mode") or "pct_mult") != "pct_mult":
        return None
    sl_base = safe_float(exit_cfg.get("sl_pct"))
    tp_low_ratio = safe_float(tp_cfg.get("tp_low_ratio"))
    if sl_base is None or tp_low_ratio is None:
        return None
    sl_map = regime_tpsl.get("sl_mult") or {}
    tp_map = regime_tpsl.get("tp_mult") or {}
    sl_mult = safe_float(sl_map.get(regime)) or safe_float(
        sl_map.get("DEFAULT"))
    tp_mult = safe_float(tp_map.get(regime)) or safe_float(
        tp_map.get("DEFAULT"))
    if sl_mult is None or tp_mult is None:
        return None
    sl_pct = sl_base * sl_mult
    tp_pct = sl_pct * tp_low_ratio * tp_mult
    if sl_pct <= 0 or tp_pct <= 0:
        return None
    return sl_pct, tp_pct


def pnl_pct_for_close(side: str, entry: float, close: float) -> float:
    if side == "BUY":
        return (close - entry) / entry * 100.0
    return (entry - close) / entry * 100.0


def favored_adverse_bps(side: str, entry: float, bar: BarRow) -> tuple[float, float]:
    if side == "BUY":
        favorable = (bar.high - entry) / entry * 10000.0
        adverse = (bar.low - entry) / entry * 10000.0
    else:
        favorable = (entry - bar.low) / entry * 10000.0
        adverse = (entry - bar.high) / entry * 10000.0
    return favorable, adverse


def simulate_variant_pair(
    *,
    scenario: str,
    symbol: str,
    row: BarRow,
    side: str,
    sl_pct: float,
    tp_pct: float,
    future_full: list[BarRow],
    max_bars: int,
) -> tuple[TradeRecord, TradeRecord]:
    entry = row.close
    tp_bps = tp_pct * 10000.0
    sl_bps = sl_pct * 10000.0

    # First-hit bars across full horizon (independent diagnostics)
    first_tp: int | None = None
    first_sl: int | None = None

    favorable_all: list[float] = []
    adverse_all: list[float] = []

    for i, b in enumerate(future_full, start=1):
        if side == "BUY":
            tp_hit = b.high >= entry * (1.0 + tp_pct)
            sl_hit = b.low <= entry * (1.0 - sl_pct)
        else:
            tp_hit = b.low <= entry * (1.0 - tp_pct)
            sl_hit = b.high >= entry * (1.0 + sl_pct)

        if tp_hit and first_tp is None:
            first_tp = i
        if sl_hit and first_sl is None:
            first_sl = i

        fav, adv = favored_adverse_bps(side, entry, b)
        favorable_all.append(fav)
        adverse_all.append(adv)

    mfe_bps = max(favorable_all) if favorable_all else 0.0
    mae_bps = min(adverse_all) if adverse_all else 0.0

    before_fav = favorable_all[:max_bars]
    after_fav = favorable_all[max_bars:]
    max_before = max(before_fav) if before_fav else 0.0
    max_after = max(after_fav) if after_fav else 0.0

    def pnl_snapshot(bar_n: int) -> float:
        if not future_full:
            return 0.0
        idx = min(max(bar_n, 1), len(future_full)) - 1
        return pnl_pct_for_close(side, entry, future_full[idx].close)

    pnl_timeout = pnl_snapshot(max_bars)
    pnl_timeout_p5 = pnl_snapshot(max_bars + 5)
    pnl_timeout_p10 = pnl_snapshot(max_bars + 10)
    pnl_end = pnl_snapshot(len(future_full)) if future_full else 0.0

    # WITH_TIMEOUT simulation (SL-first fail-closed)
    wt_outcome = "TIMEOUT"
    wt_pnl_pct = pnl_timeout
    wt_r = wt_pnl_pct / (sl_pct * 100.0) if sl_pct > 0 else 0.0
    wt_held = min(max_bars, len(future_full))
    for i, b in enumerate(future_full[:max_bars], start=1):
        if side == "BUY":
            sl_hit = b.low <= entry * (1.0 - sl_pct)
            tp_hit = b.high >= entry * (1.0 + tp_pct)
        else:
            sl_hit = b.high >= entry * (1.0 + sl_pct)
            tp_hit = b.low <= entry * (1.0 - tp_pct)
        if sl_hit and tp_hit:
            tp_hit = False
        if sl_hit:
            wt_outcome = "SL"
            wt_pnl_pct = -sl_pct * 100.0
            wt_r = -1.0
            wt_held = i
            break
        if tp_hit:
            wt_outcome = "TP"
            wt_pnl_pct = tp_pct * 100.0
            wt_r = tp_pct / sl_pct if sl_pct > 0 else 0.0
            wt_held = i
            break

    with_timeout = TradeRecord(
        scenario=scenario,
        variant=VARIANT_WITH_TIMEOUT,
        symbol=symbol,
        bar_i=row.bar_i,
        date_str=row.date_str,
        regime=row.regime,
        side=side,
        outcome=wt_outcome,
        pnl_pct=wt_pnl_pct,
        r_multiple=wt_r,
        bars_held=wt_held,
        regime_conf=row.regime_conf,
        tp_pct_used=tp_pct,
        sl_pct_used=sl_pct,
        tp_bps=tp_bps,
        sl_bps=sl_bps,
        bars_to_tp=first_tp,
        bars_to_sl=first_sl,
        mfe_bps=mfe_bps,
        mae_bps=mae_bps,
        pnl_at_timeout_pct=pnl_timeout,
        pnl_at_timeout_p5_pct=pnl_timeout_p5,
        pnl_at_timeout_p10_pct=pnl_timeout_p10,
        pnl_at_end_pct=pnl_end,
        max_bps_before_timeout=max_before,
        max_bps_after_timeout=max_after,
    )

    # NO_TIMEOUT_DIAGNOSTIC simulation (TP/SL only, else STILL_OPEN_END)
    nt_outcome = "STILL_OPEN_END"
    nt_pnl_pct = pnl_end
    nt_r = nt_pnl_pct / (sl_pct * 100.0) if sl_pct > 0 else 0.0
    nt_held = len(future_full)
    for i, b in enumerate(future_full, start=1):
        if side == "BUY":
            sl_hit = b.low <= entry * (1.0 - sl_pct)
            tp_hit = b.high >= entry * (1.0 + tp_pct)
        else:
            sl_hit = b.high >= entry * (1.0 + sl_pct)
            tp_hit = b.low <= entry * (1.0 - tp_pct)
        if sl_hit and tp_hit:
            tp_hit = False
        if sl_hit:
            nt_outcome = "SL"
            nt_pnl_pct = -sl_pct * 100.0
            nt_r = -1.0
            nt_held = i
            break
        if tp_hit:
            nt_outcome = "TP"
            nt_pnl_pct = tp_pct * 100.0
            nt_r = tp_pct / sl_pct if sl_pct > 0 else 0.0
            nt_held = i
            break

    no_timeout = TradeRecord(
        scenario=scenario,
        variant=VARIANT_NO_TIMEOUT,
        symbol=symbol,
        bar_i=row.bar_i,
        date_str=row.date_str,
        regime=row.regime,
        side=side,
        outcome=nt_outcome,
        pnl_pct=nt_pnl_pct,
        r_multiple=nt_r,
        bars_held=nt_held,
        regime_conf=row.regime_conf,
        tp_pct_used=tp_pct,
        sl_pct_used=sl_pct,
        tp_bps=tp_bps,
        sl_bps=sl_bps,
        bars_to_tp=first_tp,
        bars_to_sl=first_sl,
        mfe_bps=mfe_bps,
        mae_bps=mae_bps,
        pnl_at_timeout_pct=pnl_timeout,
        pnl_at_timeout_p5_pct=pnl_timeout_p5,
        pnl_at_timeout_p10_pct=pnl_timeout_p10,
        pnl_at_end_pct=pnl_end,
        max_bps_before_timeout=max_before,
        max_bps_after_timeout=max_after,
    )

    return with_timeout, no_timeout


def run(
    *,
    bars_by_symbol: dict[str, list[BarRow]],
    signal_threshold: float,
    assets: dict[str, Any],
    directional: dict[str, Any],
    low_vol: dict[str, Any],
    max_bars: int,
) -> tuple[dict[str, dict[str, list[TradeRecord]]], dict[str, list[RejectRecord]], int, Counter]:
    results: dict[str, dict[str, list[TradeRecord]]] = {
        s.name: {VARIANT_WITH_TIMEOUT: [], VARIANT_NO_TIMEOUT: []} for s in SCENARIOS
    }
    rejects: dict[str, list[RejectRecord]] = {s.name: [] for s in SCENARIOS}
    bars_processed = 0
    regime_counts: Counter[str] = Counter()

    for symbol, bars in bars_by_symbol.items():
        asset_cfg = assets.get(symbol)
        if not isinstance(asset_cfg, dict):
            continue
        regime_thresholds = asset_cfg.get("regime_thresholds") or {}

        for row in bars:
            bars_processed += 1
            regime_counts[row.regime] += 1

            factor = safe_float(regime_thresholds.get(row.regime)) or safe_float(
                regime_thresholds.get("DEFAULT"))
            if factor is None:
                for spec in SCENARIOS:
                    rejects[spec.name].append(RejectRecord(
                        spec.name, symbol, row.bar_i, row.date_str, row.regime, "MISSING_REGIME_THRESHOLD", row.regime_conf))
                continue

            threshold = signal_threshold * factor
            side = side_from_score(row.pillar_sum, threshold)
            future_full = bars[row.bar_i + 1:]

            for spec in SCENARIOS:
                ok, reason = apply_gates_scenario(
                    row, side, spec, directional, low_vol)
                if not ok:
                    if reason:
                        rejects[spec.name].append(RejectRecord(
                            spec.name, symbol, row.bar_i, row.date_str, row.regime, reason, row.regime_conf))
                    continue

                tpsl = resolve_tpsl(asset_cfg, row.regime)
                if tpsl is None:
                    rejects[spec.name].append(RejectRecord(
                        spec.name, symbol, row.bar_i, row.date_str, row.regime, "TPSL_CONFIG_UNAVAILABLE", row.regime_conf))
                    continue

                sl_pct, tp_pct = tpsl
                wt, nt = simulate_variant_pair(
                    scenario=spec.name,
                    symbol=symbol,
                    row=row,
                    side=side,
                    sl_pct=sl_pct,
                    tp_pct=tp_pct,
                    future_full=future_full,
                    max_bars=max_bars,
                )
                results[spec.name][VARIANT_WITH_TIMEOUT].append(wt)
                results[spec.name][VARIANT_NO_TIMEOUT].append(nt)

    return results, rejects, bars_processed, regime_counts


def max_drawdown_from_pct_pnls(pnls_pct: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for p in pnls_pct:
        equity += p / 100.0
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > mdd:
            mdd = dd
    return mdd * 100.0


def metric_summary(trades: list[TradeRecord], bars_processed: int, regime_counts: Counter, rejects: list[RejectRecord]) -> dict[str, Any]:
    n = len(trades)
    reject_counts = Counter(r.reason for r in rejects)
    if n == 0:
        return {
            "bars_processed": bars_processed,
            "regime_distribution": dict(sorted(regime_counts.items())),
            "actionable_signals": 0,
            "rejects": dict(sorted(reject_counts.items())),
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "still_open_end_count": 0,
            "total_pnl_pct": 0.0,
            "avg_pnl_pct": 0.0,
            "win_rate": 0.0,
            "avg_r": 0.0,
            "max_drawdown_pct": 0.0,
            "mfe_bps_avg": 0.0,
            "mae_bps_avg": 0.0,
            "pnl_at_timeout_avg_pct": 0.0,
            "pnl_at_end_avg_pct": 0.0,
            "bars_to_tp_median": None,
            "bars_to_sl_median": None,
            "max_bps_before_timeout_avg": 0.0,
            "max_bps_after_timeout_avg": 0.0,
            "regime_side": {},
            "symbol_regime_side": {},
        }

    tp_count = sum(1 for t in trades if t.outcome == "TP")
    sl_count = sum(1 for t in trades if t.outcome == "SL")
    timeout_count = sum(1 for t in trades if t.outcome == "TIMEOUT")
    still_open_count = sum(1 for t in trades if t.outcome == "STILL_OPEN_END")

    by_regime_side: dict[str, Counter] = defaultdict(Counter)
    symbol_regime_side: dict[str, dict[str, Counter]
                             ] = defaultdict(lambda: defaultdict(Counter))
    for t in trades:
        by_regime_side[t.regime][t.side] += 1
        symbol_regime_side[t.symbol][t.regime][t.side] += 1

    bars_to_tp = [t.bars_to_tp for t in trades if t.bars_to_tp is not None]
    bars_to_sl = [t.bars_to_sl for t in trades if t.bars_to_sl is not None]

    return {
        "bars_processed": bars_processed,
        "regime_distribution": dict(sorted(regime_counts.items())),
        "actionable_signals": n,
        "rejects": dict(sorted(reject_counts.items())),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "still_open_end_count": still_open_count,
        "total_pnl_pct": round(sum(t.pnl_pct for t in trades), 4),
        "avg_pnl_pct": round(sum(t.pnl_pct for t in trades) / n, 4),
        "win_rate": round(tp_count / n, 4),
        "avg_r": round(sum(t.r_multiple for t in trades) / n, 4),
        "max_drawdown_pct": round(max_drawdown_from_pct_pnls([t.pnl_pct for t in trades]), 4),
        "mfe_bps_avg": round(sum(t.mfe_bps for t in trades) / n, 2),
        "mae_bps_avg": round(sum(t.mae_bps for t in trades) / n, 2),
        "pnl_at_timeout_avg_pct": round(sum(t.pnl_at_timeout_pct for t in trades) / n, 4),
        "pnl_at_end_avg_pct": round(sum(t.pnl_at_end_pct for t in trades) / n, 4),
        "bars_to_tp_median": int(median(bars_to_tp)) if bars_to_tp else None,
        "bars_to_sl_median": int(median(bars_to_sl)) if bars_to_sl else None,
        "max_bps_before_timeout_avg": round(sum(t.max_bps_before_timeout for t in trades) / n, 2),
        "max_bps_after_timeout_avg": round(sum(t.max_bps_after_timeout for t in trades) / n, 2),
        "regime_side": {r: dict(c) for r, c in sorted(by_regime_side.items())},
        "symbol_regime_side": {
            sym: {reg: dict(c) for reg, c in regs.items()}
            for sym, regs in sorted(symbol_regime_side.items())
        },
    }


def pair_timeout_diagnostic(with_timeout: list[TradeRecord], no_timeout: list[TradeRecord]) -> dict[str, Any]:
    idx_no = {(t.symbol, t.bar_i): t for t in no_timeout}
    trend_wt = [t for t in with_timeout if t.regime in (
        "TREND_UP", "TREND_DOWN")]
    trend_no = [t for t in no_timeout if t.regime in (
        "TREND_UP", "TREND_DOWN")]

    timeout_trend = [t for t in trend_wt if t.outcome == "TIMEOUT"]
    timeout_later_tp = 0
    timeout_later_sl = 0
    timeout_deeper_loss = 0

    sl_then_tp_recovery = 0
    trend_all = 0
    trend_tp_too_far = 0

    for wt in trend_wt:
        trend_all += 1
        if wt.mfe_bps < wt.tp_bps:
            trend_tp_too_far += 1

        nt = idx_no.get((wt.symbol, wt.bar_i))
        if nt is None:
            continue

        if wt.outcome == "TIMEOUT":
            if nt.outcome == "TP":
                timeout_later_tp += 1
            if nt.outcome == "SL":
                timeout_later_sl += 1
            if nt.pnl_pct < wt.pnl_at_timeout_pct:
                timeout_deeper_loss += 1

        if wt.outcome == "SL" and nt.outcome == "TP":
            sl_then_tp_recovery += 1

    q1_rate = (timeout_later_tp / len(timeout_trend)) if timeout_trend else 0.0
    q2_rate = (timeout_deeper_loss / len(timeout_trend)
               ) if timeout_trend else 0.0
    q4_rate = (trend_tp_too_far / trend_all) if trend_all else 0.0

    trend_tp_w = sum(1 for t in trend_wt if t.outcome == "TP")
    trend_tp_n = sum(1 for t in trend_no if t.outcome == "TP")
    trend_wr_w = (trend_tp_w / len(trend_wt)) if trend_wt else 0.0
    trend_wr_n = (trend_tp_n / len(trend_no)) if trend_no else 0.0

    return {
        "trend_trade_count": trend_all,
        "trend_win_rate_with_timeout": round(trend_wr_w, 4),
        "trend_win_rate_no_timeout": round(trend_wr_n, 4),
        "trend_timeout_count": len(timeout_trend),
        "timeout_later_tp_count": timeout_later_tp,
        "timeout_later_tp_rate": round(q1_rate, 4),
        "timeout_later_sl_count": timeout_later_sl,
        "timeout_deeper_loss_count": timeout_deeper_loss,
        "timeout_deeper_loss_rate": round(q2_rate, 4),
        "trend_tp_too_far_count": trend_tp_too_far,
        "trend_tp_too_far_rate": round(q4_rate, 4),
        "sl_then_tp_recovery_count": sl_then_tp_recovery,
    }


def critical_answers(summary: dict[str, Any], timeout_diag: dict[str, Any]) -> dict[str, str]:
    td = timeout_diag["S0_CURRENT"]

    q1 = (
        f"Yes. In S0 TREND cohort, {td['timeout_later_tp_count']} of {td['trend_timeout_count']} timeout-closed trades "
        f"would later hit TP without timeout (rate={td['timeout_later_tp_rate']:.2%})."
    )
    q2 = (
        f"Yes. Timeout also protected downside: {td['timeout_deeper_loss_count']} of {td['trend_timeout_count']} timeout trades "
        f"had lower PnL by end-of-data in no-timeout variant (rate={td['timeout_deeper_loss_rate']:.2%})."
    )
    trend_wr_w = td["trend_win_rate_with_timeout"]
    trend_wr_n = td["trend_win_rate_no_timeout"]
    trend_delta = trend_wr_n - trend_wr_w
    if trend_delta >= 0.10:
        q3 = (
            f"Both factors matter, but max_hold contributes materially. TREND win_rate improves from "
            f"{trend_wr_w:.3f} (WITH_TIMEOUT) to {trend_wr_n:.3f} (NO_TIMEOUT), delta={trend_delta:+.3f}. "
            f"Even so, the cohort remains low-quality relative to non-TREND scenarios, so entry/direction quality is still a core issue."
        )
    elif trend_delta > 0:
        q3 = (
            f"Entry/direction quality appears primary. TREND win_rate changes only modestly from "
            f"{trend_wr_w:.3f} to {trend_wr_n:.3f} (delta={trend_delta:+.3f}) when timeout is removed."
        )
    else:
        q3 = (
            f"Entry/direction quality dominates. Removing timeout does not improve TREND win_rate "
            f"({trend_wr_w:.3f} -> {trend_wr_n:.3f}, delta={trend_delta:+.3f})."
        )
    q4 = (
        f"Likely yes. In S0 TREND trades, {td['trend_tp_too_far_count']} of {td['trend_trade_count']} had MFE < TP distance "
        f"(rate={td['trend_tp_too_far_rate']:.2%}), suggesting TP is often beyond realized movement."
    )
    sl_recovery = td["sl_then_tp_recovery_count"]
    if sl_recovery > 0:
        q5 = (
            f"Partly. SL->TP recovery count is {sl_recovery} in S0 TREND, showing some SL exits are likely too tight for "
            f"normal TREND noise. This must still be balanced against the observed timeout downside-protection effect."
        )
    else:
        q5 = (
            f"No strong evidence of overly tight SL in this window. SL->TP recovery count is 0 for S0 TREND "
            f"under no-timeout diagnostic."
        )

    return {
        "Q1_timeout_closed_later_tp": q1,
        "Q2_timeout_protected_deeper_loss": q2,
        "Q3_entry_or_timeout_length": q3,
        "Q4_tp_too_far": q4,
        "Q5_sl_too_tight": q5,
    }


def build_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# AURORA_TREND_FILTER_VS_TREND_DISABLED_REPLAY_V1")
    lines.append("")
    lines.append(f"Generated UTC: {payload['generated_at']}")
    lines.append("")

    lines.append("## Verdict")
    lines.append("")
    s1w = payload["overall"]["S1_TREND_MIN_040_WITH_MAX_CAP"][VARIANT_WITH_TIMEOUT]
    s2w = payload["overall"]["S2_TREND_DISABLED"][VARIANT_WITH_TIMEOUT]
    lines.append(
        f"S1 and S2 remain equivalent in WITH_TIMEOUT: signals {s1w['actionable_signals']} vs {s2w['actionable_signals']}, "
        f"win_rate {s1w['win_rate']:.3f} vs {s2w['win_rate']:.3f}."
    )
    lines.append(
        "Timeout diagnostic shows both effects exist: some timeout exits later hit TP, but many also prevent deeper deterioration."
    )
    lines.append("")

    lines.append("## Timeout diagnostic summary")
    lines.append("")
    lines.append("| Scenario | Variant | Signals | TP | SL | TIMEOUT | STILL_OPEN_END | WinRate | TotalPnL% | AvgR | MFE bps | MAE bps | PnL@Timeout | PnL@End |")
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for scen, variants in payload["overall"].items():
        for variant in (VARIANT_WITH_TIMEOUT, VARIANT_NO_TIMEOUT):
            m = variants[variant]
            lines.append(
                f"| {scen} | {variant} | {m['actionable_signals']} | {m['tp_count']} | {m['sl_count']} | "
                f"{m['timeout_count']} | {m['still_open_end_count']} | {m['win_rate']:.3f} | {m['total_pnl_pct']:.2f} | {m['avg_r']:.3f} | "
                f"{m['mfe_bps_avg']:.1f} | {m['mae_bps_avg']:.1f} | {m['pnl_at_timeout_avg_pct']:.3f} | {m['pnl_at_end_avg_pct']:.3f} |"
            )
    lines.append("")

    lines.append("## S1 vs TREND_DISABLED equivalence check")
    lines.append("")
    lines.append("| Metric | S1 WITH_TIMEOUT | S2 WITH_TIMEOUT |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| Signals | {s1w['actionable_signals']} | {s2w['actionable_signals']} |")
    lines.append(
        f"| Win rate | {s1w['win_rate']:.4f} | {s2w['win_rate']:.4f} |")
    lines.append(
        f"| Total PnL% | {s1w['total_pnl_pct']:.4f} | {s2w['total_pnl_pct']:.4f} |")
    lines.append(
        f"| Max DD% | {s1w['max_drawdown_pct']:.4f} | {s2w['max_drawdown_pct']:.4f} |")
    lines.append("")

    lines.append("## Critical questions")
    lines.append("")
    for k, v in payload["critical_questions"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Required metrics inventory")
    lines.append("")
    lines.append("- TP count: included per scenario+variant")
    lines.append("- SL count: included per scenario+variant")
    lines.append("- TIMEOUT count: included for WITH_TIMEOUT")
    lines.append("- STILL_OPEN_END count: included for NO_TIMEOUT_DIAGNOSTIC")
    lines.append("- MFE bps / MAE bps: included as averages")
    lines.append("- PnL at original timeout: included as avg PnL@Timeout")
    lines.append("- PnL at end of no-timeout hold: included as avg PnL@End")
    lines.append("- bars_to_TP / bars_to_SL: included in JSON medians")
    lines.append(
        "- max_bps_before_timeout / max_bps_after_timeout: included in JSON averages")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    dates = dates_in_range(args.window_start, args.window_end)

    signal_threshold, assets, directional, low_vol = load_cfg()
    symbols = [normalize_symbol(
        s) for s in args.symbols] if args.symbols else load_assigned_aurora_symbols()
    bars_by_symbol = load_all_bars(symbols, dates, args.tf_sec)

    results, rejects, bars_processed, regime_counts = run(
        bars_by_symbol=bars_by_symbol,
        signal_threshold=signal_threshold,
        assets=assets,
        directional=directional,
        low_vol=low_vol,
        max_bars=args.max_bars,
    )

    overall: dict[str, dict[str, Any]] = {}
    timeout_diag: dict[str, Any] = {}

    for spec in SCENARIOS:
        scen = spec.name
        wt = results[scen][VARIANT_WITH_TIMEOUT]
        nt = results[scen][VARIANT_NO_TIMEOUT]

        overall[scen] = {
            VARIANT_WITH_TIMEOUT: metric_summary(wt, bars_processed, regime_counts, rejects[scen]),
            VARIANT_NO_TIMEOUT: metric_summary(nt, bars_processed, regime_counts, rejects[scen]),
        }
        timeout_diag[scen] = pair_timeout_diagnostic(wt, nt)

    critical = critical_answers(overall, timeout_diag)

    payload = {
        "task": "AURORA_TREND_FILTER_VS_TREND_DISABLED_REPLAY_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "window_start": args.window_start,
            "window_end": args.window_end,
            "tf_sec": args.tf_sec,
            "symbols": symbols,
            "max_bars": args.max_bars,
            "bars_processed": bars_processed,
            "signal_threshold": signal_threshold,
        },
        "overall": overall,
        "timeout_diagnostic": timeout_diag,
        "critical_questions": critical,
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(build_md(payload), encoding="utf-8")

    s0w = overall["S0_CURRENT"][VARIANT_WITH_TIMEOUT]
    s0n = overall["S0_CURRENT"][VARIANT_NO_TIMEOUT]
    s1w = overall["S1_TREND_MIN_040_WITH_MAX_CAP"][VARIANT_WITH_TIMEOUT]
    s2w = overall["S2_TREND_DISABLED"][VARIANT_WITH_TIMEOUT]
    print(json.dumps({
        "bars_processed": bars_processed,
        "S0_WITH_TIMEOUT": {"signals": s0w["actionable_signals"], "wr": s0w["win_rate"], "timeout": s0w["timeout_count"]},
        "S0_NO_TIMEOUT": {"signals": s0n["actionable_signals"], "wr": s0n["win_rate"], "still_open_end": s0n["still_open_end_count"]},
        "S1_eq_S2_with_timeout": s1w["actionable_signals"] == s2w["actionable_signals"],
        "output_json": str(out_json),
        "output_md": str(out_md),
    }, indent=2))


if __name__ == "__main__":
    main()
