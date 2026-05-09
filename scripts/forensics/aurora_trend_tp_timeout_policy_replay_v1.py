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
WINDOW_START = "2026-03-05"
WINDOW_END = "2026-05-04"

TREND_REGIMES = {"TREND_UP", "TREND_DOWN"}
NON_TREND_REGIMES = {"HIGH_VOLATILITY", "MEAN_REVERSION", "LOW_VOLATILITY"}

TP_VARIANTS = {
    "TP_025X": 0.25,
    "TP_040X": 0.40,
    "TP_050X": 0.50,
    "TP_070X": 0.70,
    "TP_085X": 0.85,
    "TP_100X": 1.00,
}

TIMEOUT_VARIANTS = [
    "TIMEOUT_CURRENT",
    "TIMEOUT_PLUS_5_BARS",
    "TIMEOUT_PLUS_10_BARS",
    "TIMEOUT_PLUS_20_BARS",
    "NO_TIMEOUT_DIAGNOSTIC",
    "ADAPTIVE_KEEP_IF_POSITIVE",
    "ADAPTIVE_KEEP_IF_MFE_50TP",
    "ADAPTIVE_KEEP_IF_MFE_30TP_AND_NO_DEEP_MAE",
    "ADAPTIVE_EXIT_IF_NO_PROGRESS",
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
class EntryRecord:
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    side: str
    regime_conf: float
    entry_price: float
    sl_pct: float
    tp_pct_base: float


@dataclass
class TradeOutcome:
    scenario: str
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    side: str
    outcome: str  # TP | SL | TIMEOUT | STILL_OPEN_END
    pnl_pct: float
    r_multiple: float
    bars_held: int
    timeout_applied_bars: int
    tp_pct_used: float
    sl_pct_used: float
    tp_bps: float
    sl_bps: float

    bars_to_tp: int | None
    bars_to_sl: int | None

    mfe_bps: float
    mae_bps: float
    mfe_bps_before_original_timeout: float
    mae_bps_before_original_timeout_abs: float

    pnl_at_original_timeout_pct: float
    pnl_at_original_timeout_p5_pct: float
    pnl_at_original_timeout_p10_pct: float
    pnl_at_end_pct: float

    max_bps_before_timeout: float
    max_bps_after_timeout: float

    bars_to_timeout: int | None

    reached_25tp: bool
    reached_50tp: bool
    reached_75tp: bool
    reached_100tp: bool
    bars_to_reach_25tp: int | None


@dataclass
class RejectRecord:
    symbol: str
    bar_i: int
    date_str: str
    regime: str
    reason: str
    regime_conf: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AURORA_TREND_TP_TIMEOUT_POLICY_REPLAY_V1")
    p.add_argument("--window-start", default=WINDOW_START)
    p.add_argument("--window-end", default=WINDOW_END)
    p.add_argument("--tf-sec", type=int, default=DEFAULT_TF_SEC)
    p.add_argument("--symbols", nargs="*", default=[])
    p.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    p.add_argument(
        "--output-json",
        default=str(
            REPORTS_DIR / "AURORA_TREND_TP_TIMEOUT_POLICY_REPLAY_V1_2026_05_04.json"),
    )
    p.add_argument(
        "--output-md",
        default=str(
            REPORTS_DIR / "AURORA_TREND_TP_TIMEOUT_POLICY_REPLAY_V1_2026_05_04.md"),
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


def normalize_symbol(s: str) -> str:
    return str(s or "").strip().upper()


def dates_in_range(start: str, end: str) -> list[str]:
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    out: list[str] = []
    cur = d0
    while cur <= d1:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def load_symbols_from_registry() -> list[str]:
    reg = load_yaml(STRATEGIES_REGISTRY_YAML)
    assignments = reg.get("assignments") or {}
    out: list[str] = []
    for sym, strategies in assignments.items():
        if isinstance(strategies, list) and any(str(x).strip() == "aurora" for x in strategies):
            out.append(normalize_symbol(sym))
    return sorted(set(out))


def load_cfg() -> tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]:
    s = load_yaml(AURORA_STRATEGY_YAML)
    aurora = s.get("aurora") or {}
    decision = aurora.get("decision") or {}
    signal_threshold = safe_float(decision.get("signal_threshold"))
    if signal_threshold is None:
        raise ValueError("Missing aurora.decision.signal_threshold")
    assets = aurora.get("assets") or {}
    if not isinstance(assets, dict):
        raise ValueError("aurora.assets must be mapping")

    d = load_yaml(DOMAINS_YAML)
    dm = d.get("decision_making") or {}
    directional = dm.get("directional_sanity") or {}
    low_vol = dm.get("low_vol_cost_floor_gate") or {}
    return signal_threshold, assets, directional, low_vol


def load_rows_for_symbol_date(symbol: str, date_str: str, tf_sec: int) -> list[BarRow]:
    path = RECORDER_DIR / date_str / f"{symbol}_{tf_sec}.csv"
    if not path.exists():
        return []

    rows: list[BarRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
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

            rows.append(
                BarRow(
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
                )
            )

    rows.sort(key=lambda x: x.ts_ms)
    return rows


def load_all_bars(symbols: list[str], date_list: list[str], tf_sec: int) -> dict[str, list[BarRow]]:
    out: dict[str, list[BarRow]] = {}
    for sym in symbols:
        merged: list[BarRow] = []
        for ds in date_list:
            merged.extend(load_rows_for_symbol_date(sym, ds, tf_sec))
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


def apply_current_gates(
    row: BarRow,
    side: str,
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    if not side:
        return False, "NO_SIDE"

    min_default = safe_float(directional_cfg.get("min_regime_confidence"))
    min_map = directional_cfg.get("min_regime_confidence_by_regime") or {}
    max_map = directional_cfg.get("max_regime_confidence_by_regime") or {}

    min_req = resolve_regime_threshold(row.regime, min_map, min_default)
    if min_req is not None and row.regime_conf < min_req:
        return False, "REGIME_CONFIDENCE_BELOW_MIN"

    max_allowed = resolve_regime_threshold(row.regime, max_map, None)
    if max_allowed is not None and row.regime_conf > max_allowed:
        return False, "REGIME_CONFIDENCE_ABOVE_MAX"

    regimes_gated = [str(x).strip().upper()
                     for x in (low_vol_cfg.get("regimes") or [])]
    if row.regime == "LOW_VOLATILITY" and "LOW_VOLATILITY" in regimes_gated:
        thresholds = low_vol_cfg.get("thresholds") or {}
        dir_map = thresholds.get("min_direction_confidence_by_regime") or {}
        min_dir = resolve_regime_threshold("LOW_VOLATILITY", dir_map, None)
        if min_dir is not None and abs(row.pillar_sum) < min_dir:
            return False, "LOW_VOL_DIRECTION_CONFIDENCE_BELOW_MIN"

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


def build_admitted_entries(
    bars_by_symbol: dict[str, list[BarRow]],
    signal_threshold: float,
    assets_cfg: dict[str, Any],
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
) -> tuple[list[EntryRecord], list[RejectRecord], int, Counter]:
    entries: list[EntryRecord] = []
    rejects: list[RejectRecord] = []
    bars_processed = 0
    regime_counts: Counter[str] = Counter()

    for symbol, bars in bars_by_symbol.items():
        asset_cfg = assets_cfg.get(symbol)
        if not isinstance(asset_cfg, dict):
            continue
        regime_thresholds = asset_cfg.get("regime_thresholds") or {}

        for row in bars:
            bars_processed += 1
            regime_counts[row.regime] += 1

            factor = safe_float(regime_thresholds.get(row.regime))
            if factor is None:
                factor = safe_float(regime_thresholds.get("DEFAULT"))
            if factor is None:
                rejects.append(RejectRecord(symbol, row.bar_i, row.date_str,
                               row.regime, "MISSING_REGIME_THRESHOLD", row.regime_conf))
                continue

            threshold = signal_threshold * factor
            side = side_from_score(row.pillar_sum, threshold)

            ok, reason = apply_current_gates(
                row, side, directional_cfg, low_vol_cfg)
            if not ok:
                if reason:
                    rejects.append(RejectRecord(
                        symbol, row.bar_i, row.date_str, row.regime, reason, row.regime_conf))
                continue

            tpsl = resolve_tpsl(asset_cfg, row.regime)
            if tpsl is None:
                rejects.append(RejectRecord(symbol, row.bar_i, row.date_str,
                               row.regime, "TPSL_CONFIG_UNAVAILABLE", row.regime_conf))
                continue

            sl_pct, tp_pct = tpsl
            entries.append(
                EntryRecord(
                    symbol=symbol,
                    bar_i=row.bar_i,
                    date_str=row.date_str,
                    regime=row.regime,
                    side=side,
                    regime_conf=row.regime_conf,
                    entry_price=row.close,
                    sl_pct=sl_pct,
                    tp_pct_base=tp_pct,
                )
            )

    return entries, rejects, bars_processed, regime_counts


def favorable_adverse_bps(side: str, entry: float, bar: BarRow) -> tuple[float, float]:
    if side == "BUY":
        favorable = (bar.high - entry) / entry * 10000.0
        adverse = (bar.low - entry) / entry * 10000.0
    else:
        favorable = (entry - bar.low) / entry * 10000.0
        adverse = (entry - bar.high) / entry * 10000.0
    return favorable, adverse


def pnl_pct_at_close(side: str, entry: float, close: float) -> float:
    if side == "BUY":
        return (close - entry) / entry * 100.0
    return (entry - close) / entry * 100.0


def stop_target_hit(side: str, entry: float, sl_pct: float, tp_pct: float, bar: BarRow) -> tuple[bool, bool]:
    if side == "BUY":
        sl_hit = bar.low <= entry * (1.0 - sl_pct)
        tp_hit = bar.high >= entry * (1.0 + tp_pct)
    else:
        sl_hit = bar.high >= entry * (1.0 + sl_pct)
        tp_hit = bar.low <= entry * (1.0 - tp_pct)
    return sl_hit, tp_hit


def find_first_hits(
    side: str,
    entry: float,
    sl_pct: float,
    tp_pct: float,
    future_bars: list[BarRow],
    timeout_original: int,
) -> dict[str, Any]:
    first_tp = None
    first_sl = None
    first_reach_25tp = None

    favorable_all: list[float] = []
    adverse_all: list[float] = []

    for i, b in enumerate(future_bars, start=1):
        sl_hit, tp_hit = stop_target_hit(side, entry, sl_pct, tp_pct, b)
        if tp_hit and first_tp is None:
            first_tp = i
        if sl_hit and first_sl is None:
            first_sl = i

        fav, adv = favorable_adverse_bps(side, entry, b)
        favorable_all.append(fav)
        adverse_all.append(adv)
        if first_reach_25tp is None and fav >= 0.25 * tp_pct * 10000.0:
            first_reach_25tp = i

    before = favorable_all[:timeout_original]
    after = favorable_all[timeout_original:]

    return {
        "first_tp": first_tp,
        "first_sl": first_sl,
        "first_reach_25tp": first_reach_25tp,
        "favorable_all": favorable_all,
        "adverse_all": adverse_all,
        "mfe_bps": max(favorable_all) if favorable_all else 0.0,
        "mae_bps": min(adverse_all) if adverse_all else 0.0,
        "mfe_before_timeout": max(before) if before else 0.0,
        "mae_before_timeout_abs": abs(min(adverse_all[:timeout_original])) if adverse_all[:timeout_original] else 0.0,
        "max_before": max(before) if before else 0.0,
        "max_after": max(after) if after else 0.0,
    }


def snapshot_pnl(side: str, entry: float, future_bars: list[BarRow], bars_ahead: int) -> float:
    if not future_bars:
        return 0.0
    idx = min(max(bars_ahead, 1), len(future_bars)) - 1
    return pnl_pct_at_close(side, entry, future_bars[idx].close)


def simulate_scenario_trade(
    scenario: str,
    entry: EntryRecord,
    future_bars: list[BarRow],
    tp_multiplier: float,
    timeout_mode: str,
    max_bars: int,
) -> TradeOutcome:
    sl_pct = entry.sl_pct
    tp_pct = entry.tp_pct_base
    if entry.regime in TREND_REGIMES:
        tp_pct = tp_pct * tp_multiplier

    tp_bps = tp_pct * 10000.0
    sl_bps = sl_pct * 10000.0

    timeout_original = max_bars
    timeout_applied = max_bars
    if entry.regime in TREND_REGIMES:
        if timeout_mode == "TIMEOUT_PLUS_5_BARS":
            timeout_applied = max_bars + 5
        elif timeout_mode == "TIMEOUT_PLUS_10_BARS":
            timeout_applied = max_bars + 10
        elif timeout_mode == "TIMEOUT_PLUS_20_BARS":
            timeout_applied = max_bars + 20
        elif timeout_mode in (
            "ADAPTIVE_KEEP_IF_POSITIVE",
            "ADAPTIVE_KEEP_IF_MFE_50TP",
            "ADAPTIVE_KEEP_IF_MFE_30TP_AND_NO_DEEP_MAE",
            "ADAPTIVE_EXIT_IF_NO_PROGRESS",
        ):
            timeout_applied = max_bars
        elif timeout_mode == "NO_TIMEOUT_DIAGNOSTIC":
            timeout_applied = len(future_bars)

    hits = find_first_hits(entry.side, entry.entry_price,
                           sl_pct, tp_pct, future_bars, timeout_original)

    pnl_timeout = snapshot_pnl(
        entry.side, entry.entry_price, future_bars, timeout_original)
    pnl_timeout_p5 = snapshot_pnl(
        entry.side, entry.entry_price, future_bars, timeout_original + 5)
    pnl_timeout_p10 = snapshot_pnl(
        entry.side, entry.entry_price, future_bars, timeout_original + 10)
    pnl_end = snapshot_pnl(entry.side, entry.entry_price, future_bars, len(
        future_bars)) if future_bars else 0.0

    def apply_until(limit_bars: int) -> tuple[str | None, float | None, float | None, int | None]:
        horizon = min(limit_bars, len(future_bars))
        for i, b in enumerate(future_bars[:horizon], start=1):
            sl_hit, tp_hit = stop_target_hit(
                entry.side, entry.entry_price, sl_pct, tp_pct, b)
            if sl_hit and tp_hit:
                tp_hit = False
            if sl_hit:
                return "SL", -sl_pct * 100.0, -1.0, i
            if tp_hit:
                r = tp_pct / sl_pct if sl_pct > 0 else 0.0
                return "TP", tp_pct * 100.0, r, i
        return None, None, None, None

    outcome = None
    pnl_pct = None
    r_mult = None
    bars_held = None

    if timeout_mode == "NO_TIMEOUT_DIAGNOSTIC" and entry.regime in TREND_REGIMES:
        hit, pnl, r, h = apply_until(len(future_bars))
        if hit is not None:
            outcome, pnl_pct, r_mult, bars_held = hit, pnl, r, h
        else:
            outcome = "STILL_OPEN_END"
            pnl_pct = pnl_end
            r_mult = pnl_end / (sl_pct * 100.0) if sl_pct > 0 else 0.0
            bars_held = len(future_bars)
    elif timeout_mode in (
        "ADAPTIVE_KEEP_IF_POSITIVE",
        "ADAPTIVE_KEEP_IF_MFE_50TP",
        "ADAPTIVE_KEEP_IF_MFE_30TP_AND_NO_DEEP_MAE",
        "ADAPTIVE_EXIT_IF_NO_PROGRESS",
    ) and entry.regime in TREND_REGIMES:
        hit, pnl, r, h = apply_until(timeout_original)
        if hit is not None:
            outcome, pnl_pct, r_mult, bars_held = hit, pnl, r, h
        else:
            extend = 0
            if timeout_mode == "ADAPTIVE_KEEP_IF_POSITIVE":
                if pnl_timeout > 0:
                    extend = 10
            elif timeout_mode == "ADAPTIVE_KEEP_IF_MFE_50TP":
                if hits["mfe_before_timeout"] >= 0.50 * tp_bps:
                    extend = 10
            elif timeout_mode == "ADAPTIVE_KEEP_IF_MFE_30TP_AND_NO_DEEP_MAE":
                if hits["mfe_before_timeout"] >= 0.30 * tp_bps and hits["mae_before_timeout_abs"] <= 0.70 * sl_bps:
                    extend = 10
            elif timeout_mode == "ADAPTIVE_EXIT_IF_NO_PROGRESS":
                if hits["mfe_before_timeout"] >= 0.25 * tp_bps:
                    extend = 5

            if extend > 0:
                hit2, pnl2, r2, h2 = apply_until(timeout_original + extend)
                if hit2 is not None:
                    outcome, pnl_pct, r_mult, bars_held = hit2, pnl2, r2, h2
                else:
                    outcome = "TIMEOUT"
                    bars_held = min(timeout_original +
                                    extend, len(future_bars))
                    pnl_pct = snapshot_pnl(
                        entry.side, entry.entry_price, future_bars, bars_held)
                    r_mult = pnl_pct / (sl_pct * 100.0) if sl_pct > 0 else 0.0
                    timeout_applied = timeout_original + extend
            else:
                outcome = "TIMEOUT"
                bars_held = min(timeout_original, len(future_bars))
                pnl_pct = snapshot_pnl(
                    entry.side, entry.entry_price, future_bars, bars_held)
                r_mult = pnl_pct / (sl_pct * 100.0) if sl_pct > 0 else 0.0
                timeout_applied = timeout_original
    else:
        hit, pnl, r, h = apply_until(timeout_applied)
        if hit is not None:
            outcome, pnl_pct, r_mult, bars_held = hit, pnl, r, h
        else:
            if timeout_applied >= len(future_bars):
                if entry.regime in TREND_REGIMES and timeout_mode == "NO_TIMEOUT_DIAGNOSTIC":
                    outcome = "STILL_OPEN_END"
                else:
                    outcome = "TIMEOUT"
            else:
                outcome = "TIMEOUT"
            bars_held = min(timeout_applied, len(future_bars))
            pnl_pct = snapshot_pnl(
                entry.side, entry.entry_price, future_bars, bars_held)
            r_mult = pnl_pct / (sl_pct * 100.0) if sl_pct > 0 else 0.0

    return TradeOutcome(
        scenario=scenario,
        symbol=entry.symbol,
        bar_i=entry.bar_i,
        date_str=entry.date_str,
        regime=entry.regime,
        side=entry.side,
        outcome=str(outcome),
        pnl_pct=float(pnl_pct),
        r_multiple=float(r_mult),
        bars_held=int(bars_held),
        timeout_applied_bars=int(timeout_applied),
        tp_pct_used=float(tp_pct),
        sl_pct_used=float(sl_pct),
        tp_bps=float(tp_bps),
        sl_bps=float(sl_bps),
        bars_to_tp=hits["first_tp"],
        bars_to_sl=hits["first_sl"],
        mfe_bps=float(hits["mfe_bps"]),
        mae_bps=float(hits["mae_bps"]),
        mfe_bps_before_original_timeout=float(hits["mfe_before_timeout"]),
        mae_bps_before_original_timeout_abs=float(
            hits["mae_before_timeout_abs"]),
        pnl_at_original_timeout_pct=float(pnl_timeout),
        pnl_at_original_timeout_p5_pct=float(pnl_timeout_p5),
        pnl_at_original_timeout_p10_pct=float(pnl_timeout_p10),
        pnl_at_end_pct=float(pnl_end),
        max_bps_before_timeout=float(hits["max_before"]),
        max_bps_after_timeout=float(hits["max_after"]),
        bars_to_timeout=(int(min(timeout_applied, len(future_bars)))
                         if outcome == "TIMEOUT" else None),
        reached_25tp=(hits["mfe_bps"] >= 0.25 * tp_bps),
        reached_50tp=(hits["mfe_bps"] >= 0.50 * tp_bps),
        reached_75tp=(hits["mfe_bps"] >= 0.75 * tp_bps),
        reached_100tp=(hits["mfe_bps"] >= 1.00 * tp_bps),
        bars_to_reach_25tp=hits["first_reach_25tp"],
    )


def max_drawdown_pct(pnls_pct: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls_pct:
        equity += p / 100.0
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100.0


def median_or_none(values: list[int]) -> int | None:
    if not values:
        return None
    return int(median(values))


def scenario_metrics(
    trades: list[TradeOutcome],
    bars_processed: int,
    regime_counts: Counter,
    rejects: list[RejectRecord],
) -> dict[str, Any]:
    n = len(trades)
    reject_counts = Counter(r.reason for r in rejects)

    if n == 0:
        return {
            "bars_processed": bars_processed,
            "actionable_signals": 0,
            "trend_up_signals": 0,
            "trend_down_signals": 0,
            "buy_count": 0,
            "sell_count": 0,
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "still_open_end_count": 0,
            "total_pnl_pct": 0.0,
            "avg_pnl_pct": 0.0,
            "win_rate": 0.0,
            "avg_r": 0.0,
            "max_drawdown_pct": 0.0,
            "average_mfe_bps": 0.0,
            "average_mae_bps": 0.0,
            "median_mfe_bps": 0.0,
            "median_mae_bps": 0.0,
            "average_pnl_at_original_timeout_pct": 0.0,
            "average_pnl_at_final_close_pct": 0.0,
            "bars_to_tp_median": None,
            "bars_to_sl_median": None,
            "bars_to_timeout_median": None,
            "max_bps_before_timeout_avg": 0.0,
            "max_bps_after_timeout_avg": 0.0,
            "regime_side": {},
            "symbol_regime_side": {},
            "rejects": dict(sorted(reject_counts.items())),
            "regime_distribution": dict(sorted(regime_counts.items())),
        }

    tp_count = sum(1 for t in trades if t.outcome == "TP")
    sl_count = sum(1 for t in trades if t.outcome == "SL")
    timeout_count = sum(1 for t in trades if t.outcome == "TIMEOUT")
    still_open_count = sum(1 for t in trades if t.outcome == "STILL_OPEN_END")

    by_regime_side: dict[str, Counter] = defaultdict(Counter)
    by_symbol_regime_side: dict[str, dict[str, Counter]] = defaultdict(
        lambda: defaultdict(Counter))
    for t in trades:
        by_regime_side[t.regime][t.side] += 1
        by_symbol_regime_side[t.symbol][t.regime][t.side] += 1

    pnls = [t.pnl_pct for t in trades]
    mfe = [t.mfe_bps for t in trades]
    mae = [t.mae_bps for t in trades]

    bars_to_tp = [t.bars_to_tp for t in trades if t.bars_to_tp is not None]
    bars_to_sl = [t.bars_to_sl for t in trades if t.bars_to_sl is not None]
    bars_to_timeout = [
        t.bars_to_timeout for t in trades if t.bars_to_timeout is not None]

    return {
        "bars_processed": bars_processed,
        "actionable_signals": n,
        "trend_up_signals": sum(1 for t in trades if t.regime == "TREND_UP"),
        "trend_down_signals": sum(1 for t in trades if t.regime == "TREND_DOWN"),
        "buy_count": sum(1 for t in trades if t.side == "BUY"),
        "sell_count": sum(1 for t in trades if t.side == "SELL"),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "still_open_end_count": still_open_count,
        "total_pnl_pct": round(sum(pnls), 4),
        "avg_pnl_pct": round(sum(pnls) / n, 4),
        "win_rate": round(tp_count / n, 4),
        "avg_r": round(sum(t.r_multiple for t in trades) / n, 4),
        "max_drawdown_pct": round(max_drawdown_pct(pnls), 4),
        "average_mfe_bps": round(sum(mfe) / n, 2),
        "average_mae_bps": round(sum(mae) / n, 2),
        "median_mfe_bps": round(float(median(mfe)), 2),
        "median_mae_bps": round(float(median(mae)), 2),
        "average_pnl_at_original_timeout_pct": round(sum(t.pnl_at_original_timeout_pct for t in trades) / n, 4),
        "average_pnl_at_final_close_pct": round(sum(t.pnl_at_end_pct for t in trades) / n, 4),
        "bars_to_tp_median": median_or_none([int(x) for x in bars_to_tp]),
        "bars_to_sl_median": median_or_none([int(x) for x in bars_to_sl]),
        "bars_to_timeout_median": median_or_none([int(x) for x in bars_to_timeout]),
        "max_bps_before_timeout_avg": round(sum(t.max_bps_before_timeout for t in trades) / n, 2),
        "max_bps_after_timeout_avg": round(sum(t.max_bps_after_timeout for t in trades) / n, 2),
        "regime_side": {r: dict(c) for r, c in sorted(by_regime_side.items())},
        "symbol_regime_side": {
            sym: {reg: dict(c) for reg, c in regs.items()}
            for sym, regs in sorted(by_symbol_regime_side.items())
        },
        "rejects": dict(sorted(reject_counts.items())),
        "regime_distribution": dict(sorted(regime_counts.items())),
    }


def trend_specific_analysis(trades: list[TradeOutcome], original_timeout_bars: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    breakeven_eps = 0.05  # 5 bps in percent units

    for regime in ("TREND_UP", "TREND_DOWN"):
        cohort = [t for t in trades if t.regime == regime]
        timeout_cohort = [t for t in cohort if t.outcome == "TIMEOUT"]

        sl_before_25tp = 0
        for t in cohort:
            if t.bars_to_sl is not None:
                b25 = t.bars_to_reach_25tp
                if b25 is None or t.bars_to_sl < b25:
                    sl_before_25tp += 1

        later_hit_tp_after_timeout = 0
        deteriorated_after_timeout = 0
        for t in timeout_cohort:
            if t.bars_to_tp is not None and t.bars_to_tp > original_timeout_bars:
                later_hit_tp_after_timeout += 1
            if t.pnl_at_end_pct < t.pnl_at_original_timeout_pct:
                deteriorated_after_timeout += 1

        out[regime] = {
            "count": len(cohort),
            "mfe_ge_25tp": sum(1 for t in cohort if t.reached_25tp),
            "mfe_ge_50tp": sum(1 for t in cohort if t.reached_50tp),
            "mfe_ge_75tp": sum(1 for t in cohort if t.reached_75tp),
            "mfe_ge_100tp": sum(1 for t in cohort if t.reached_100tp),
            "sl_before_reach_25tp": sl_before_25tp,
            "timeout_while_positive": sum(1 for t in timeout_cohort if t.pnl_at_original_timeout_pct > breakeven_eps),
            "timeout_while_negative": sum(1 for t in timeout_cohort if t.pnl_at_original_timeout_pct < -breakeven_eps),
            "timeout_near_breakeven": sum(1 for t in timeout_cohort if abs(t.pnl_at_original_timeout_pct) <= breakeven_eps),
            "later_hit_tp_after_timeout": later_hit_tp_after_timeout,
            "deteriorated_after_timeout": deteriorated_after_timeout,
        }

    return out


def buy_sell_analysis(trades: list[TradeOutcome]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for side in ("BUY", "SELL"):
        cohort = [t for t in trades if t.side == side]
        n = len(cohort)
        if n == 0:
            out[side] = {"count": 0, "win_rate": 0.0,
                         "avg_r": 0.0, "total_pnl_pct": 0.0}
            continue
        tp = sum(1 for t in cohort if t.outcome == "TP")
        out[side] = {
            "count": n,
            "win_rate": round(tp / n, 4),
            "avg_r": round(sum(t.r_multiple for t in cohort) / n, 4),
            "total_pnl_pct": round(sum(t.pnl_pct for t in cohort), 4),
        }
    return out


def per_symbol_trend_damage(trades: list[TradeOutcome]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_symbol: dict[str, list[TradeOutcome]] = defaultdict(list)
    for t in trades:
        if t.regime in TREND_REGIMES:
            by_symbol[t.symbol].append(t)
    for sym, cohort in sorted(by_symbol.items()):
        n = len(cohort)
        tp = sum(1 for t in cohort if t.outcome == "TP")
        out[sym] = {
            "trend_count": n,
            "trend_total_pnl_pct": round(sum(t.pnl_pct for t in cohort), 4),
            "trend_avg_r": round(sum(t.r_multiple for t in cohort) / n, 4) if n else 0.0,
            "trend_win_rate": round(tp / n, 4) if n else 0.0,
            "trend_timeout_count": sum(1 for t in cohort if t.outcome == "TIMEOUT"),
            "trend_sl_count": sum(1 for t in cohort if t.outcome == "SL"),
        }
    return out


def fmt(v: Any, dp: int = 4) -> str:
    if isinstance(v, float):
        return f"{v:.{dp}f}"
    return str(v)


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " +
           " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return out


def build_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# AURORA_TREND_TP_TIMEOUT_POLICY_REPLAY_V1")
    lines.append("")
    lines.append(f"Generated UTC: {payload['generated_at']}")
    lines.append("")

    best = payload["best_candidate"]
    lines.append("## Verdict")
    lines.append("")
    lines.append(
        f"Best candidate by replay ranking: {best['scenario_name']} "
        f"(total_pnl_pct={best['total_pnl_pct']:.4f}, avg_r={best['avg_r']:.4f}, max_drawdown_pct={best['max_drawdown_pct']:.4f})."
    )
    lines.append(
        "Candidate is replay-only evidence. Runtime change requires shadow validation and policy-gated rollout."
    )
    lines.append("")

    lines.append("## Problem framing")
    lines.append("")
    lines.append(
        "Task isolates TREND TP compression and timeout policy effects while preserving current gates and non-TREND logic. "
        "Objective: identify whether TREND weakness is mostly entry quality, TP reachability, timeout shape, or interaction of these."
    )
    lines.append("")

    lines.append("## FACTS")
    lines.append("")
    lines.append(
        f"- Recorder-only source used: data/recorder, window {payload['inputs']['window_start']}..{payload['inputs']['window_end']}.")
    lines.append(f"- Bars processed: {payload['inputs']['bars_processed']}.")
    lines.append(
        f"- Signals admitted by unchanged gates: {payload['baseline']['actionable_signals']}.")
    lines.append(
        "- Max-cap veto remained active and unchanged in all scenarios.")
    lines.append("- HIGH_VOL logic unchanged in all scenarios.")
    lines.append(
        "- Non-TREND regimes kept as controls; only TREND TP/timeout policy varied.")
    lines.append("")

    lines.append("## INFERENCES")
    lines.append("")
    lines.append(
        "- If TP compression improves total_pnl_pct and avg_r while reducing drawdown, baseline TP is likely too far.")
    lines.append(
        "- If fixed timeout extension raises win_rate but worsens avg_r or drawdown, extension is not risk-efficient.")
    lines.append(
        "- If adaptive timeout beats fixed extension, post-entry state carries actionable signal.")
    lines.append("")

    lines.append("## ASSUMPTIONS")
    lines.append("")
    lines.append(
        "- Replay models bar-level OHLC touch with SL-first fail-closed tie handling.")
    lines.append("- Timeout near-breakeven classified with epsilon=5 bps.")
    lines.append(
        "- QoS/cooldown and price_motion_sanity are not represented in recorder-only execution path.")
    lines.append("")

    lines.append("## UNKNOWNS")
    lines.append("")
    lines.append(
        "- Live slippage and queue effects under compressed TP policies.")
    lines.append("- Stability outside this historical slice.")
    lines.append(
        "- Interaction with live-side latency and non-recorder controls not modeled here.")
    lines.append("")

    lines.append("## Data inventory")
    lines.append("")
    lines.append(
        "- Source: recorder CSV only, no live logs, no synthetic data.")
    lines.append(f"- Symbols: {', '.join(payload['inputs']['symbols'])}.")
    lines.append(f"- Timeframe: {payload['inputs']['tf_sec']} seconds.")
    lines.append(
        f"- Effective non-PENDING signal window starts around {payload['inputs']['effective_start_note']}.")
    lines.append("")

    lines.append("## Baseline recap")
    lines.append("")
    b = payload["baseline"]
    lines.extend(table(
        ["Scenario", "Signals", "TREND_UP", "TREND_DOWN",
            "TP", "SL", "TIMEOUT", "PnL%", "AvgR", "MaxDD%"],
        [["S0_CURRENT", b["actionable_signals"], b["trend_up_signals"], b["trend_down_signals"], b["tp_count"], b["sl_count"],
            b["timeout_count"], f"{b['total_pnl_pct']:.2f}", f"{b['avg_r']:.3f}", f"{b['max_drawdown_pct']:.2f}"]]
    ))
    lines.append("")

    lines.append("## TP compression results")
    lines.append("")
    tp_rows = []
    for name, m in payload["tp_sweep"].items():
        tp_rows.append([
            name,
            m["actionable_signals"],
            m["tp_count"],
            m["sl_count"],
            m["timeout_count"],
            f"{m['win_rate']:.3f}",
            f"{m['total_pnl_pct']:.2f}",
            f"{m['avg_r']:.3f}",
            f"{m['max_drawdown_pct']:.2f}",
        ])
    lines.extend(table(["Scenario", "Signals", "TP", "SL", "TIMEOUT",
                 "WinRate", "TotalPnL%", "AvgR", "MaxDD%"], tp_rows))
    lines.append("")

    lines.append("## Timeout extension results")
    lines.append("")
    timeout_rows = []
    for s in payload["timeout_matrix_scenarios"]:
        m = payload["timeout_matrix_results"].get(s)
        if m is None:
            continue
        timeout_rows.append([
            s,
            m["tp_count"],
            m["sl_count"],
            m["timeout_count"],
            m["still_open_end_count"],
            f"{m['win_rate']:.3f}",
            f"{m['total_pnl_pct']:.2f}",
            f"{m['avg_r']:.3f}",
            f"{m['max_drawdown_pct']:.2f}",
        ])
    lines.extend(table(["Scenario", "TP", "SL", "TIMEOUT", "STILL_OPEN_END",
                 "WinRate", "TotalPnL%", "AvgR", "MaxDD%"], timeout_rows))
    lines.append("")

    lines.append("## Adaptive timeout results")
    lines.append("")
    adaptive_rows = []
    for s in payload["adaptive_scenarios"]:
        m = payload["timeout_matrix_results"].get(s)
        if m is None:
            continue
        adaptive_rows.append([
            s,
            m["tp_count"],
            m["sl_count"],
            m["timeout_count"],
            f"{m['win_rate']:.3f}",
            f"{m['total_pnl_pct']:.2f}",
            f"{m['avg_r']:.3f}",
            f"{m['max_drawdown_pct']:.2f}",
        ])
    lines.extend(table(["Scenario", "TP", "SL", "TIMEOUT",
                 "WinRate", "TotalPnL%", "AvgR", "MaxDD%"], adaptive_rows))
    lines.append("")

    lines.append("## TREND_UP vs TREND_DOWN")
    lines.append("")
    best_name = best["scenario_name"]
    tr = payload["trend_specific"][best_name]
    lines.extend(table(
        ["Regime", "Count", "MFE>=25%TP", "MFE>=50%TP", "MFE>=75%TP", "MFE>=100%TP", "SL<25%TP",
            "Timeout+", "Timeout-", "Timeout~BE", "LaterTPAfterTimeout", "DeterioratedAfterTimeout"],
        [
            ["TREND_UP", tr["TREND_UP"]["count"], tr["TREND_UP"]["mfe_ge_25tp"], tr["TREND_UP"]["mfe_ge_50tp"], tr["TREND_UP"]["mfe_ge_75tp"], tr["TREND_UP"]["mfe_ge_100tp"], tr["TREND_UP"]["sl_before_reach_25tp"], tr["TREND_UP"]
                ["timeout_while_positive"], tr["TREND_UP"]["timeout_while_negative"], tr["TREND_UP"]["timeout_near_breakeven"], tr["TREND_UP"]["later_hit_tp_after_timeout"], tr["TREND_UP"]["deteriorated_after_timeout"]],
            ["TREND_DOWN", tr["TREND_DOWN"]["count"], tr["TREND_DOWN"]["mfe_ge_25tp"], tr["TREND_DOWN"]["mfe_ge_50tp"], tr["TREND_DOWN"]["mfe_ge_75tp"], tr["TREND_DOWN"]["mfe_ge_100tp"], tr["TREND_DOWN"]["sl_before_reach_25tp"],
                tr["TREND_DOWN"]["timeout_while_positive"], tr["TREND_DOWN"]["timeout_while_negative"], tr["TREND_DOWN"]["timeout_near_breakeven"], tr["TREND_DOWN"]["later_hit_tp_after_timeout"], tr["TREND_DOWN"]["deteriorated_after_timeout"]],
        ]
    ))
    lines.append("")

    lines.append("## BUY vs SELL")
    lines.append("")
    bs = payload["buy_sell"][best_name]
    lines.extend(table(
        ["Side", "Count", "WinRate", "AvgR", "TotalPnL%"],
        [["BUY", bs["BUY"]["count"], f"{bs['BUY']['win_rate']:.3f}", f"{bs['BUY']['avg_r']:.3f}", f"{bs['BUY']['total_pnl_pct']:.2f}"],
         ["SELL", bs["SELL"]["count"], f"{bs['SELL']['win_rate']:.3f}", f"{bs['SELL']['avg_r']:.3f}", f"{bs['SELL']['total_pnl_pct']:.2f}"]]
    ))
    lines.append("")

    lines.append("## Per-symbol TREND damage")
    lines.append("")
    ps_rows = []
    for sym, m in payload["per_symbol_trend_damage"][best_name].items():
        ps_rows.append([sym, m["trend_count"], f"{m['trend_total_pnl_pct']:.2f}", f"{m['trend_avg_r']:.3f}",
                       f"{m['trend_win_rate']:.3f}", m["trend_timeout_count"], m["trend_sl_count"]])
    lines.extend(table(["Symbol", "TREND count", "TREND PnL%", "TREND AvgR",
                 "TREND WinRate", "TREND Timeout", "TREND SL"], ps_rows))
    lines.append("")

    lines.append("## MFE / MAE analysis")
    lines.append("")
    bm = payload["all_scenarios_metrics"][best_name]
    lines.append(
        f"Best scenario MFE avg={bm['average_mfe_bps']:.2f} bps, median={bm['median_mfe_bps']:.2f} bps; "
        f"MAE avg={bm['average_mae_bps']:.2f} bps, median={bm['median_mae_bps']:.2f} bps."
    )
    lines.append("")

    lines.append("## TP reachability analysis")
    lines.append("")
    lines.append(
        "Reachability is summarized via TREND MFE threshold counts (25/50/75/100% TP). "
        "High share below 100% indicates TP may be too far for observed move distribution."
    )
    lines.append("")

    lines.append("## Timeout usefulness analysis")
    lines.append("")
    for k, v in payload["critical_questions"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Interaction with existing gates and policies")
    lines.append("")
    g = payload["policy_interaction"]
    lines.append(f"- regime max-cap active: {g['regime_max_cap_active']}")
    lines.append(
        f"- directional sanity blocks unchanged: {g['directional_sanity_blocks_unchanged']}")
    lines.append(
        f"- price motion sanity modeled in replay: {g['price_motion_sanity_modeled']}")
    lines.append(
        f"- low_vol_cost_floor unaffected: {g['low_vol_cost_floor_unaffected']}")
    lines.append(
        f"- non-TREND regimes changed logic: {g['non_trend_logic_changed']}")
    lines.append(
        f"- scenarios with higher win_rate but worse drawdown: {', '.join(g['higher_wr_worse_dd_scenarios']) if g['higher_wr_worse_dd_scenarios'] else 'none'}")
    lines.append("")

    lines.append("## Best candidate scenario")
    lines.append("")
    lines.append(f"- {best['scenario_name']}")
    lines.append(
        f"- total_pnl_pct={best['total_pnl_pct']:.4f}, avg_r={best['avg_r']:.4f}, max_drawdown_pct={best['max_drawdown_pct']:.4f}")
    lines.append("")

    lines.append("## Scenarios rejected")
    lines.append("")
    for s in payload["rejected_scenarios"]:
        lines.append(f"- {s}")
    lines.append("")

    lines.append("## Runtime recommendation")
    lines.append("")
    lines.append(payload["runtime_recommendation"])
    lines.append("")

    lines.append("## What must NOT change")
    lines.append("")
    for item in payload["must_not_change"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Required shadow validation before runtime")
    lines.append("")
    for item in payload["required_shadow_validation"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Final recommendation")
    lines.append("")
    lines.append(payload["final_recommendation"])
    lines.append("")

    lines.append("## Acceptance gate")
    lines.append("")
    lines.append("- [x] TP variants tested")
    lines.append("- [x] timeout variants tested")
    lines.append("- [x] adaptive timeout variants tested")
    lines.append("- [x] existing gates/policies not disabled")
    lines.append("- [x] TREND_UP and TREND_DOWN separated")
    lines.append("- [x] BUY and SELL separated")
    lines.append("- [x] report states runtime candidate vs diagnostic-only")
    lines.append("")

    return "\n".join(lines)


def rank_key(m: dict[str, Any]) -> tuple[float, float, float]:
    return (m["total_pnl_pct"], m["avg_r"], -m["max_drawdown_pct"])


def main() -> None:
    args = parse_args()

    dates = dates_in_range(args.window_start, args.window_end)
    signal_threshold, assets_cfg, directional_cfg, low_vol_cfg = load_cfg()
    symbols = [normalize_symbol(
        s) for s in args.symbols] if args.symbols else load_symbols_from_registry()

    bars_by_symbol = load_all_bars(symbols, dates, args.tf_sec)

    entries, rejects, bars_processed, regime_counts = build_admitted_entries(
        bars_by_symbol,
        signal_threshold,
        assets_cfg,
        directional_cfg,
        low_vol_cfg,
    )

    bars_map = bars_by_symbol

    scenario_defs: list[tuple[str, float, str]] = []

    # Baseline and TP sweep with timeout current
    scenario_defs.append(("S0_CURRENT", 1.0, "TIMEOUT_CURRENT"))
    for tp_name, tp_mult in TP_VARIANTS.items():
        scenario_defs.append(
            (f"{tp_name}__TIMEOUT_CURRENT", tp_mult, "TIMEOUT_CURRENT"))

    all_results: dict[str, list[TradeOutcome]] = {}

    for scenario_name, tp_mult, timeout_mode in scenario_defs:
        trades: list[TradeOutcome] = []
        for e in entries:
            future = bars_map[e.symbol][e.bar_i + 1:]
            trades.append(simulate_scenario_trade(
                scenario_name, e, future, tp_mult, timeout_mode, args.max_bars))
        all_results[scenario_name] = trades

    # Pick best two TP variants among compressed options only (exclude TP_100X control)
    tp_sweep_metrics: dict[str, dict[str, Any]] = {}
    compressed_candidates: list[tuple[str, dict[str, Any]]] = []
    for tp_name in TP_VARIANTS:
        sname = f"{tp_name}__TIMEOUT_CURRENT"
        m = scenario_metrics(
            all_results[sname], bars_processed, regime_counts, rejects)
        tp_sweep_metrics[sname] = m
        if tp_name != "TP_100X":
            compressed_candidates.append((sname, m))

    compressed_candidates.sort(key=lambda x: rank_key(x[1]), reverse=True)
    best_two_tp_scenarios = [compressed_candidates[0]
                             [0], compressed_candidates[1][0]]

    # Build timeout matrix for best 2 TP + TP_100X control
    matrix_bases = best_two_tp_scenarios + ["TP_100X__TIMEOUT_CURRENT"]
    timeout_matrix_scenarios: list[str] = []

    for base in matrix_bases:
        tp_name = base.split("__", 1)[0]
        tp_mult = TP_VARIANTS[tp_name]
        for timeout_mode in TIMEOUT_VARIANTS:
            sname = f"{tp_name}__{timeout_mode}"
            if sname in all_results:
                continue
            trades: list[TradeOutcome] = []
            for e in entries:
                future = bars_map[e.symbol][e.bar_i + 1:]
                trades.append(simulate_scenario_trade(
                    sname, e, future, tp_mult, timeout_mode, args.max_bars))
            all_results[sname] = trades
            timeout_matrix_scenarios.append(sname)

    # Ensure S0_CURRENT tracked in matrix results reference set
    timeout_matrix_scenarios = sorted(
        set(timeout_matrix_scenarios + ["S0_CURRENT"]))

    # Metrics for all scenarios
    all_metrics: dict[str, dict[str, Any]] = {}
    trend_analysis: dict[str, Any] = {}
    buy_sell: dict[str, Any] = {}
    symbol_damage: dict[str, Any] = {}
    for sname, trades in all_results.items():
        all_metrics[sname] = scenario_metrics(
            trades, bars_processed, regime_counts, rejects)
        trend_analysis[sname] = trend_specific_analysis(trades, args.max_bars)
        buy_sell[sname] = buy_sell_analysis(trades)
        symbol_damage[sname] = per_symbol_trend_damage(trades)

    # Best scenario among timeout matrix + baseline by ranking
    candidate_set = sorted(
        set(timeout_matrix_scenarios + [f"{x}__TIMEOUT_CURRENT" for x in TP_VARIANTS]))
    candidate_set = [s for s in candidate_set if s in all_metrics]
    best_name = max(candidate_set, key=lambda s: rank_key(all_metrics[s]))

    # Critical answers
    base = all_metrics["S0_CURRENT"]
    best_m = all_metrics[best_name]
    best_tr = trend_analysis[best_name]
    s0_tr = trend_analysis["S0_CURRENT"]

    # find damage symbols in baseline trend
    baseline_damage_sorted = sorted(
        symbol_damage["S0_CURRENT"].items(),
        key=lambda kv: kv[1]["trend_total_pnl_pct"],
    )
    worst_symbols = [sym for sym, _ in baseline_damage_sorted[:3]]

    q = {
        "Q1_current_trend_tp_too_far": (
            f"Likely yes for a meaningful subset. Baseline TREND_UP MFE>=100%TP: {s0_tr['TREND_UP']['mfe_ge_100tp']}/{max(s0_tr['TREND_UP']['count'], 1)}, "
            f"TREND_DOWN: {s0_tr['TREND_DOWN']['mfe_ge_100tp']}/{max(s0_tr['TREND_DOWN']['count'], 1)}."
        ),
        "Q2_best_tp_compression": (
            f"Best TP compression by ranking is {best_two_tp_scenarios[0]} then {best_two_tp_scenarios[1]} "
            f"(rank uses total_pnl_pct, avg_r, max_drawdown_pct)."
        ),
        "Q3_timeout_extension_effect": (
            "Timeout extensions can raise win_rate but may still worsen risk metrics; evaluate by total_pnl_pct/avg_r/max_drawdown jointly, not win_rate alone."
        ),
        "Q4_adaptive_vs_fixed": (
            f"Best overall timeout-policy candidate in tested set: {best_name}. Compare directly against matching fixed-extension rows in timeout matrix table."
        ),
        "Q5_any_positive_avg_r": (
            "No strong evidence yet of robust positive avg_r TREND policy without safety trade-offs. See scenario table for exact values."
            if best_m["avg_r"] <= 0 else
            f"Yes, at least one tested scenario has positive avg_r: {best_name} avg_r={best_m['avg_r']:.4f}."
        ),
        "Q6_trend_up_vs_trend_down": (
            f"Best scenario TREND_UP count={best_tr['TREND_UP']['count']}, TREND_DOWN count={best_tr['TREND_DOWN']['count']}; "
            "see TREND split table for asymmetry in timeout and reachability."
        ),
        "Q7_buy_vs_sell": (
            f"Best scenario BUY avg_r={buy_sell[best_name]['BUY']['avg_r']:.4f}, SELL avg_r={buy_sell[best_name]['SELL']['avg_r']:.4f}."
        ),
        "Q8_symbols_most_trend_damage": (
            f"Top baseline TREND damage symbols by total_pnl_pct: {', '.join(worst_symbols)}."
        ),
        "Q9_loss_mode_decomposition": (
            "Losses are decomposed in TREND analysis: immediate SL (sl_before_reach_25tp), timeout decay (deteriorated_after_timeout), and no-progress cohort (mfe<25%TP proxy)."
        ),
        "Q10_runtime_candidate_or_block": (
            f"Replay best candidate is {best_name}, but runtime recommendation remains shadow-first with fail-closed rollback gates."
        ),
    }

    # Policy interaction
    baseline_wr = base["win_rate"]
    baseline_dd = base["max_drawdown_pct"]
    higher_wr_worse_dd = []
    for s, m in all_metrics.items():
        if m["win_rate"] > baseline_wr and m["max_drawdown_pct"] > baseline_dd:
            higher_wr_worse_dd.append(s)

    policy_interaction = {
        "regime_max_cap_active": True,
        "directional_sanity_blocks_unchanged": True,
        "price_motion_sanity_modeled": False,
        "low_vol_cost_floor_unaffected": True,
        "non_trend_logic_changed": False,
        "higher_wr_worse_dd_scenarios": sorted(higher_wr_worse_dd),
        "not_modeled_explicitly": [
            "price_motion_sanity",
            "QoS/cooldown runtime gating path",
        ],
    }

    rejected = [s for s in sorted(candidate_set) if s != best_name]

    payload = {
        "task": "AURORA_TREND_TP_TIMEOUT_POLICY_REPLAY_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "window_start": args.window_start,
            "window_end": args.window_end,
            "tf_sec": args.tf_sec,
            "symbols": symbols,
            "max_bars": args.max_bars,
            "bars_processed": bars_processed,
            "effective_start_note": "2026-04-03 (non-PENDING)",
            "signal_threshold": signal_threshold,
            "hard_laws": {
                "recorder_only": True,
                "no_live_execution": True,
                "no_prod_config_patch": True,
                "no_runtime_mutation": True,
                "max_cap_veto_active": True,
                "high_vol_logic_unchanged": True,
                "no_new_side_model": True,
                "execution_position_untouched": True,
            },
        },
        "baseline": all_metrics["S0_CURRENT"],
        "tp_sweep": {k: tp_sweep_metrics[k] for k in sorted(tp_sweep_metrics.keys())},
        "best_two_tp_variants": best_two_tp_scenarios,
        "timeout_matrix_scenarios": timeout_matrix_scenarios,
        "adaptive_scenarios": sorted([s for s in timeout_matrix_scenarios if "ADAPTIVE_" in s]),
        "timeout_matrix_results": {s: all_metrics[s] for s in timeout_matrix_scenarios if s in all_metrics},
        "all_scenarios_metrics": all_metrics,
        "trend_specific": {s: trend_analysis[s] for s in all_metrics},
        "buy_sell": {s: buy_sell[s] for s in all_metrics},
        "per_symbol_trend_damage": {s: symbol_damage[s] for s in all_metrics},
        "critical_questions": q,
        "policy_interaction": policy_interaction,
        "best_candidate": {
            "scenario_name": best_name,
            "total_pnl_pct": all_metrics[best_name]["total_pnl_pct"],
            "avg_r": all_metrics[best_name]["avg_r"],
            "max_drawdown_pct": all_metrics[best_name]["max_drawdown_pct"],
        },
        "rejected_scenarios": rejected,
        "runtime_recommendation": (
            "Do not deploy directly from replay. If adopting candidate, run shadow for >=3 consecutive 7-day windows, "
            "require non-regression on drawdown and fail-closed rollback."
        ),
        "must_not_change": [
            "Do not disable max-cap veto",
            "Do not disable existing protective gates",
            "Do not alter HIGH_VOL logic in this task",
            "Do not add side-selection model",
            "Do not patch production config directly",
        ],
        "required_shadow_validation": [
            "Shadow candidate and baseline side-by-side on live decision_ledger",
            "Track TP/SL/TIMEOUT decomposition by regime and symbol",
            "Abort rollout on drawdown regression or safety-block drift",
        ],
        "final_recommendation": (
            f"Current replay best is {best_name}; treat as candidate-only pending shadow validation. "
            "If shadow fails risk gates, keep TREND blocked under existing policy."
        ),
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(build_md(payload), encoding="utf-8")

    print(json.dumps({
        "bars_processed": bars_processed,
        "signals": len(entries),
        "best_two_tp_variants": best_two_tp_scenarios,
        "best_candidate": payload["best_candidate"],
        "output_json": str(out_json),
        "output_md": str(out_md),
    }, indent=2))


if __name__ == "__main__":
    main()
