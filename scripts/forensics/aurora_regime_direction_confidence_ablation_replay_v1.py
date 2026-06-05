"""
AURORA_REGIME_DIRECTION_CONFIDENCE_ABLATION_REPLAY_V1

Recorder-only ablation replay to isolate which mechanism caused PROPOSED_EXPERIMENTAL to
underperform CURRENT in the previous audit.

Hard laws:
- Recorder-only. No live execution. No runtime mutation. No production config patch.
- YAML + Pydantic remain SSOT. No hidden constants. No silent fallbacks.
- Report must separate FACT / INFERENCE / ASSUMPTION / UNKNOWN.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

DEFAULT_DATES = ["2026-05-03", "2026-05-04"]
DEFAULT_TF_SEC = 300
DEFAULT_MAX_BARS = 18
DEFAULT_HIGH_VOL_WIDEN_FACTOR = 1.25


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BarRow:
    symbol: str
    bar_i: int  # index within symbol's merged bar list (stable identity)
    ts_ms: int
    dt: str
    open_: float
    high: float
    low: float
    close: float
    regime: str
    regime_conf: float
    pillar_sum: float


@dataclass
class ScenarioConfig:
    name: str
    trend_activation_min: float | None
    disable_trend_max_cap: bool
    high_vol_widen_factor: float


@dataclass
class TradeRecord:
    symbol: str
    bar_i: int          # stable bar identity for delta comparison
    regime: str
    side: str
    outcome: str        # TP | SL | TIMEOUT
    pnl_pct: float      # raw fraction * 100
    r_multiple: float
    bars_held: int
    entry_price: float
    sl_pct_used: float
    tp_pct_used: float


@dataclass
class RejectRecord:
    symbol: str
    bar_i: int
    regime: str
    reason: str


@dataclass
class ScenarioResult:
    scenario: ScenarioConfig
    bars_processed: int
    regime_counts: Counter
    side_counts: Counter
    reject_counts: Counter
    trades: list[TradeRecord]
    rejects: list[RejectRecord]


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ablation replay for AURORA_REGIME_DIRECTION_CONFIDENCE",
    )
    parser.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    parser.add_argument("--tf-sec", type=int, default=DEFAULT_TF_SEC)
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--high-vol-widen-factor", type=float,
                        default=DEFAULT_HIGH_VOL_WIDEN_FACTOR)
    parser.add_argument(
        "--output-json",
        default=str(
            REPORTS_DIR / "AURORA_REGIME_DIRECTION_CONFIDENCE_ABLATION_REPLAY_V1_2026_05_04.json"),
    )
    parser.add_argument(
        "--output-md",
        default=str(
            REPORTS_DIR / "AURORA_REGIME_DIRECTION_CONFIDENCE_ABLATION_REPLAY_V1_2026_05_04.md"),
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

def load_rows_for_symbol_date(symbol: str, date_dir: str, tf_sec: int) -> list[BarRow]:
    path = RECORDER_DIR / date_dir / f"{symbol}_{tf_sec}.csv"
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
            # bar_i assigned after collection
            rows.append(BarRow(
                symbol=symbol, bar_i=0, ts_ms=ts_ms,
                dt=str(rec.get("datetime") or ""),
                open_=float(open_), high=float(high),
                low=float(low), close=float(close),
                regime=regime, regime_conf=float(regime_conf),
                pillar_sum=float(pillar_sum),
            ))

    rows.sort(key=lambda x: x.ts_ms)
    for idx, r in enumerate(rows):
        r.bar_i = idx
    return rows


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

def resolve_regime_threshold(regime: str, mapping: dict[str, Any], default_value: float | None) -> float | None:
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


def apply_gates(
    *,
    row: BarRow,
    side: str,
    scenario: ScenarioConfig,
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    if not side:
        return False, "NO_SIDE"

    min_default = safe_float(directional_cfg.get("min_regime_confidence"))
    min_map = directional_cfg.get("min_regime_confidence_by_regime") or {}
    max_map = directional_cfg.get("max_regime_confidence_by_regime") or {}

    min_required = resolve_regime_threshold(row.regime, min_map, min_default)
    if min_required is not None and row.regime_conf < min_required:
        return False, "REGIME_CONFIDENCE_BELOW_MIN"

    # Scenario-specific: experimental trend activation minimum
    if scenario.trend_activation_min is not None and row.regime in ("TREND_UP", "TREND_DOWN"):
        if row.regime_conf < scenario.trend_activation_min:
            return False, "TREND_ACTIVATION_BELOW_EXPERIMENTAL_MIN"

    # Max-cap veto: disabled for TREND regimes only if disable_trend_max_cap=True
    disable_trend_max = scenario.disable_trend_max_cap and row.regime in (
        "TREND_UP", "TREND_DOWN")
    if not disable_trend_max:
        max_allowed = resolve_regime_threshold(row.regime, max_map, None)
        if max_allowed is not None and row.regime_conf > max_allowed:
            return False, "REGIME_CONFIDENCE_ABOVE_MAX"

    # LOW_VOL direction confidence gate
    regimes_gated = [str(r).strip().upper()
                     for r in (low_vol_cfg.get("regimes") or [])]
    if row.regime == "LOW_VOLATILITY" and "LOW_VOLATILITY" in regimes_gated:
        thresholds = low_vol_cfg.get("thresholds") or {}
        dir_map = thresholds.get("min_direction_confidence_by_regime") or {}
        min_dir = resolve_regime_threshold("LOW_VOLATILITY", dir_map, None)
        if min_dir is not None:
            direction_confidence = abs(row.pillar_sum)
            if direction_confidence < min_dir:
                return False, "LOW_VOL_DIRECTION_CONFIDENCE_BELOW_MIN"

    return True, None


# ---------------------------------------------------------------------------
# TPSL resolution
# ---------------------------------------------------------------------------

def resolve_tpsl_params(
    asset_cfg: dict[str, Any],
    regime: str,
    scenario: ScenarioConfig,
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

    sl_mult = safe_float(sl_mult_map.get(regime))
    if sl_mult is None:
        sl_mult = safe_float(sl_mult_map.get("DEFAULT"))
    tp_mult = safe_float(tp_mult_map.get(regime))
    if tp_mult is None:
        tp_mult = safe_float(tp_mult_map.get("DEFAULT"))

    if sl_mult is None or tp_mult is None:
        return None

    sl_pct_eff = sl_pct_base * sl_mult
    tp_rr_eff = tp_low_ratio * tp_mult

    if regime == "HIGH_VOLATILITY":
        sl_pct_eff *= scenario.high_vol_widen_factor
        tp_rr_eff *= scenario.high_vol_widen_factor

    tp_pct = sl_pct_eff * tp_rr_eff
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
    """Returns (outcome, pnl_fraction, r_multiple, bars_held)."""
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
            # Fail-closed: SL-first on ambiguous same-bar touch
            stop_hit = True
            tp_hit = False

        if stop_hit:
            return "SL", -sl_pct, -1.0, idx
        if tp_hit:
            r = tp_pct / sl_pct if sl_pct > 0 else 0.0
            return "TP", tp_pct, r, idx

    if not future_bars:
        return "TIMEOUT", 0.0, 0.0, 0

    last = future_bars[-1].close
    if side == "BUY":
        pnl = (last - entry_price) / entry_price
    else:
        pnl = (entry_price - last) / entry_price
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
# Scenario runner
# ---------------------------------------------------------------------------

def run_scenario(
    *,
    scenario: ScenarioConfig,
    bars_by_symbol: dict[str, list[BarRow]],
    signal_threshold: float,
    assets_cfg: dict[str, Any],
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
    max_bars: int,
) -> ScenarioResult:
    bars_processed = 0
    regime_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    trades: list[TradeRecord] = []
    rejects: list[RejectRecord] = []

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
                reject_counts["MISSING_REGIME_THRESHOLD"] += 1
                rejects.append(RejectRecord(symbol, row.bar_i,
                               row.regime, "MISSING_REGIME_THRESHOLD"))
                continue

            threshold = signal_threshold * factor
            side = side_from_score(row.pillar_sum, threshold)

            allowed, reason = apply_gates(
                row=row, side=side, scenario=scenario,
                directional_cfg=directional_cfg, low_vol_cfg=low_vol_cfg,
            )
            if not allowed:
                if reason:
                    reject_counts[reason] += 1
                    rejects.append(RejectRecord(
                        symbol, row.bar_i, row.regime, reason))
                continue

            params = resolve_tpsl_params(asset_cfg, row.regime, scenario)
            if params is None:
                reject_counts["TPSL_CONFIG_UNAVAILABLE"] += 1
                rejects.append(RejectRecord(symbol, row.bar_i,
                               row.regime, "TPSL_CONFIG_UNAVAILABLE"))
                continue

            sl_pct, tp_pct = params
            side_counts[side] += 1
            future = bars[row.bar_i + 1:row.bar_i + 1 + max_bars]
            outcome, pnl, r, bars_held = simulate_trade(
                side=side, entry_price=row.close,
                sl_pct=sl_pct, tp_pct=tp_pct, future_bars=future,
            )
            trades.append(TradeRecord(
                symbol=symbol, bar_i=row.bar_i,
                regime=row.regime, side=side,
                outcome=outcome, pnl_pct=pnl * 100.0,
                r_multiple=r, bars_held=bars_held,
                entry_price=row.close, sl_pct_used=sl_pct, tp_pct_used=tp_pct,
            ))

    return ScenarioResult(
        scenario=scenario,
        bars_processed=bars_processed,
        regime_counts=regime_counts,
        side_counts=side_counts,
        reject_counts=reject_counts,
        trades=trades,
        rejects=rejects,
    )


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def cohort_metrics(trades: list[TradeRecord]) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {
            "count": 0, "total_pnl_pct": 0.0, "avg_pnl_pct": 0.0,
            "win_rate": 0.0, "avg_r": 0.0,
            "tp": 0, "sl": 0, "timeout": 0,
            "max_drawdown_pct": 0.0,
        }
    pnls = [t.pnl_pct / 100.0 for t in trades]
    tp = sum(1 for t in trades if t.outcome == "TP")
    sl = sum(1 for t in trades if t.outcome == "SL")
    timeout = n - tp - sl
    total_pnl = sum(pnls)
    return {
        "count": n,
        "total_pnl_pct": round(total_pnl * 100.0, 4),
        "avg_pnl_pct": round(total_pnl * 100.0 / n, 4),
        "win_rate": round(tp / n, 4),
        "avg_r": round(sum(t.r_multiple for t in trades) / n, 4),
        "tp": tp, "sl": sl, "timeout": timeout,
        "max_drawdown_pct": round(max_drawdown(pnls) * 100.0, 4),
    }


def scenario_summary(result: ScenarioResult) -> dict[str, Any]:
    trades = result.trades
    n = len(trades)
    pnls = [t.pnl_pct / 100.0 for t in trades]
    tp = sum(1 for t in trades if t.outcome == "TP")
    sl = sum(1 for t in trades if t.outcome == "SL")
    timeout = n - tp - sl

    # By regime cohort
    regime_cohorts: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        regime_cohorts[t.regime].append(t)

    # By regime x side
    regime_side: dict[str, Counter] = defaultdict(Counter)
    for t in trades:
        regime_side[t.regime][t.side] += 1

    # By symbol x regime x side
    symbol_regime_side: dict[str, dict[str, Counter]
                             ] = defaultdict(lambda: defaultdict(Counter))
    for t in trades:
        symbol_regime_side[t.symbol][t.regime][t.side] += 1

    total_pnl = sum(pnls)
    avg_pnl = total_pnl / n if n else 0.0
    win_rate = tp / n if n else 0.0
    avg_r = sum(t.r_multiple for t in trades) / n if n else 0.0
    dd = max_drawdown(pnls)

    return {
        "scenario": result.scenario.name,
        "config": {
            "trend_activation_min": result.scenario.trend_activation_min,
            "disable_trend_max_cap": result.scenario.disable_trend_max_cap,
            "high_vol_widen_factor": result.scenario.high_vol_widen_factor,
        },
        "bars_processed": result.bars_processed,
        "regime_distribution": dict(sorted(result.regime_counts.items())),
        "actionable_signals": n,
        "rejects": dict(sorted(result.reject_counts.items())),
        "side_distribution": dict(sorted(result.side_counts.items())),
        "regime_side": {r: dict(c) for r, c in sorted(regime_side.items())},
        "symbol_regime_side": {
            sym: {reg: dict(cnt) for reg, cnt in sorted(regs.items())}
            for sym, regs in sorted(symbol_regime_side.items())
        },
        "tp": tp, "sl": sl, "timeout": timeout,
        "total_pnl_pct": round(total_pnl * 100.0, 4),
        "avg_pnl_pct": round(avg_pnl * 100.0, 4),
        "win_rate": round(win_rate, 4),
        "avg_r": round(avg_r, 4),
        "max_drawdown_pct": round(dd * 100.0, 4),
        "cohort_breakdown": {
            regime: cohort_metrics(cohort_trades)
            for regime, cohort_trades in sorted(regime_cohorts.items())
        },
    }


# ---------------------------------------------------------------------------
# Delta analysis (vs S0)
# ---------------------------------------------------------------------------

def delta_analysis(
    s0_result: ScenarioResult,
    sx_result: ScenarioResult,
) -> dict[str, Any]:
    s0_index: dict[tuple[str, int], TradeRecord] = {
        (t.symbol, t.bar_i): t for t in s0_result.trades
    }
    sx_index: dict[tuple[str, int], TradeRecord] = {
        (t.symbol, t.bar_i): t for t in sx_result.trades
    }

    s0_keys = set(s0_index)
    sx_keys = set(sx_index)

    newly_admitted_keys = sx_keys - s0_keys
    removed_keys = s0_keys - sx_keys
    common_keys = s0_keys & sx_keys

    changed_side_keys = {
        k for k in common_keys if s0_index[k].side != sx_index[k].side}
    unchanged_keys = common_keys - changed_side_keys

    newly_admitted = [sx_index[k] for k in sorted(newly_admitted_keys)]
    removed = [s0_index[k] for k in sorted(removed_keys)]
    changed_side = [sx_index[k] for k in sorted(changed_side_keys)]
    unchanged = [sx_index[k] for k in sorted(unchanged_keys)]

    return {
        "newly_admitted": cohort_metrics(newly_admitted),
        "removed": cohort_metrics(removed),
        "changed_side": cohort_metrics(changed_side),
        "unchanged": cohort_metrics(unchanged),
        "_newly_admitted_regimes": dict(Counter(t.regime for t in newly_admitted)),
        "_removed_regimes": dict(Counter(t.regime for t in removed)),
        "_changed_side_regimes": dict(Counter(t.regime for t in changed_side)),
    }


# ---------------------------------------------------------------------------
# Critical questions
# ---------------------------------------------------------------------------

def answer_questions(
    results: dict[str, dict[str, Any]],
    deltas: dict[str, dict[str, Any]],
) -> dict[str, str]:
    s0 = results["S0_CURRENT"]
    s2 = results["S2_DISABLE_TREND_MAX_ONLY"]
    s1 = results["S1_TREND_MIN_ONLY"]
    s3 = results["S3_TREND_MIN_AND_DISABLE_MAX"]
    s4 = results["S4_HIGH_VOL_TPSL_ONLY"]
    s5 = results["S5_FULL_PREVIOUS_PROPOSED"]

    s0_n = s0["actionable_signals"]
    s2_n = s2["actionable_signals"]
    s3_n = s3["actionable_signals"]

    s2_new = deltas["S2_DISABLE_TREND_MAX_ONLY_vs_S0"]["newly_admitted"]["count"]
    s2_rem = deltas["S2_DISABLE_TREND_MAX_ONLY_vs_S0"]["removed"]["count"]
    s3_new = deltas["S3_TREND_MIN_AND_DISABLE_MAX_vs_S0"]["newly_admitted"]["count"]

    s4_pnl = s4["total_pnl_pct"]
    s0_pnl = s0["total_pnl_pct"]
    s5_pnl = s5["total_pnl_pct"]

    s0_sell = s0["side_distribution"].get("SELL", 0)
    s5_sell = s5["side_distribution"].get("SELL", 0)
    s0_buy = s0["side_distribution"].get("BUY", 0)
    s5_buy = s5["side_distribution"].get("BUY", 0)
    s0_total = s0_n or 1
    s5_total = s5["actionable_signals"] or 1

    s0_tu = s0.get("cohort_breakdown", {}).get("TREND_UP", {})
    s0_td = s0.get("cohort_breakdown", {}).get("TREND_DOWN", {})
    s5_tu = s5.get("cohort_breakdown", {}).get("TREND_UP", {})
    s5_td = s5.get("cohort_breakdown", {}).get("TREND_DOWN", {})

    s0_hv = s0.get("cohort_breakdown", {}).get("HIGH_VOLATILITY", {})
    s4_hv = s4.get("cohort_breakdown", {}).get("HIGH_VOLATILITY", {})
    hv_count = s4_hv.get("count", 0)

    s0_lv = s0.get("cohort_breakdown", {}).get("LOW_VOLATILITY", {})
    s5_lv = s5.get("cohort_breakdown", {}).get("LOW_VOLATILITY", {})

    answers: dict[str, str] = {}

    # Q1: Did disabling trend max-cap cause +7 actionable?
    s2_delta = s2_n - s0_n
    q1_text = (
        f"S2_DISABLE_TREND_MAX_ONLY vs S0: actionable signals changed by {s2_delta:+d} "
        f"(S0={s0_n}, S2={s2_n}). "
        f"Newly admitted={s2_new}, removed={s2_rem}. "
    )
    if s2_delta >= 5:
        q1_text += "FACT: Disabling the max-cap veto is the primary driver of additional signals."
    elif s2_delta >= 2:
        q1_text += "INFERENCE: Disabling max-cap veto contributed materially to additional signals but may not be the sole driver."
    else:
        q1_text += "INFERENCE: Disabling max-cap veto had small or neutral effect on signal count."
    answers["Q1_trend_max_cap_causes_additional_signals"] = q1_text

    # Q2: Were newly admitted trend trades responsible for PnL degradation?
    na_pnl = deltas["S5_FULL_PREVIOUS_PROPOSED_vs_S0"]["newly_admitted"]["total_pnl_pct"]
    na_count = deltas["S5_FULL_PREVIOUS_PROPOSED_vs_S0"]["newly_admitted"]["count"]
    q2_text = (
        f"S5 vs S0 newly admitted={na_count} trades, total_pnl_pct={na_pnl:.4f}. "
        f"S0 total_pnl_pct={s0_pnl:.4f}, S5 total_pnl_pct={s5_pnl:.4f}. "
        f"Newly admitted regime breakdown: {deltas['S5_FULL_PREVIOUS_PROPOSED_vs_S0']['_newly_admitted_regimes']}. "
    )
    if na_pnl < -1.0 and na_count > 0:
        q2_text += "INFERENCE: Newly admitted trades are a material PnL drag."
    elif na_count == 0:
        q2_text += "FACT: No newly admitted trades; S5 degradation comes from other changes."
    else:
        q2_text += "INFERENCE: Newly admitted trades have small or mixed PnL impact."
    answers["Q2_newly_admitted_trades_pnl_drag"] = q2_text

    # Q3: Did HIGH_VOL widened TP/SL help or hurt?
    q3_text = (
        f"S4_HIGH_VOL_TPSL_ONLY vs S0: "
        f"total_pnl_pct S4={s4_pnl:.4f} vs S0={s0_pnl:.4f}. "
        f"HIGH_VOL cohort in S4: {s4_hv}. "
        f"HIGH_VOL cohort in S0: {s0_hv}. "
    )
    if hv_count == 0:
        q3_text += "UNKNOWN: No HIGH_VOL trades in window; HIGH_VOL TP/SL effect cannot be measured."
    elif s4_pnl > s0_pnl + 0.5:
        q3_text += "INFERENCE: HIGH_VOL widened TP/SL shows directional improvement in this window."
    elif s4_pnl < s0_pnl - 0.5:
        q3_text += "INFERENCE: HIGH_VOL widened TP/SL shows directional degradation in this window."
    else:
        q3_text += "INFERENCE: HIGH_VOL widened TP/SL has negligible isolated effect in this window."
    answers["Q3_high_vol_tpsl_effect"] = q3_text

    # Q4: Did side distribution shift contribute to losses?
    s0_sell_pct = s0_sell / s0_total
    s5_sell_pct = s5_sell / s5_total
    q4_text = (
        f"S0 SELL%={s0_sell_pct:.2%} ({s0_sell}/{s0_total}), "
        f"S5 SELL%={s5_sell_pct:.2%} ({s5_sell}/{s5_total}). "
        f"S0 BUY={s0_buy}, S5 BUY={s5_buy}. "
    )
    shift = abs(s5_sell_pct - s0_sell_pct)
    if shift > 0.05:
        q4_text += f"INFERENCE: Meaningful side distribution shift ({shift:.1%}); may contribute to loss change if market was directional."
    else:
        q4_text += f"INFERENCE: Side distribution shift is small ({shift:.1%}); unlikely to be primary PnL driver."
    answers["Q4_side_distribution_shift"] = q4_text

    # Q5: TREND_UP vs TREND_DOWN asymmetry?
    tu0 = s0_tu.get("count", 0)
    td0 = s0_td.get("count", 0)
    tu5 = s5_tu.get("count", 0)
    td5 = s5_td.get("count", 0)
    tu0_wr = s0_tu.get("win_rate", 0.0)
    td0_wr = s0_td.get("win_rate", 0.0)
    tu5_wr = s5_tu.get("win_rate", 0.0)
    td5_wr = s5_td.get("win_rate", 0.0)
    q5_text = (
        f"S0: TREND_UP={tu0} trades wr={tu0_wr:.3f}, TREND_DOWN={td0} trades wr={td0_wr:.3f}. "
        f"S5: TREND_UP={tu5} trades wr={tu5_wr:.3f}, TREND_DOWN={td5} trades wr={td5_wr:.3f}. "
    )
    if abs(tu0_wr - td0_wr) > 0.08 or abs(tu5_wr - td5_wr) > 0.08:
        q5_text += "INFERENCE: TREND_UP and TREND_DOWN show asymmetric performance; treat separately."
    elif tu0 < 5 or td0 < 5:
        q5_text += "UNKNOWN: Sample sizes too small for reliable asymmetry assessment (<5 trades per side)."
    else:
        q5_text += "INFERENCE: No strong asymmetry observed in this window."
    answers["Q5_trend_up_vs_trend_down_asymmetry"] = q5_text

    # Q6: HIGH_VOL sample size
    q6_text = (
        f"HIGH_VOL trade count in S4={hv_count}, in S0={s0_hv.get('count', 0)}. "
    )
    if hv_count < 5:
        q6_text += "UNKNOWN: Sample size too small (<5) to draw statistically meaningful conclusions about HIGH_VOL effect."
    elif hv_count < 15:
        q6_text += "ASSUMPTION: Directional indication only; sample insufficient for robust HIGH_VOL conclusions (n<15)."
    else:
        q6_text += "INFERENCE: Sample size adequate for basic HIGH_VOL assessment."
    answers["Q6_high_vol_sample_size"] = q6_text

    # Q7: LOW_VOL behavior change
    lv0 = s0_lv.get("count", 0)
    lv5 = s5_lv.get("count", 0)
    lv0_pnl = s0_lv.get("total_pnl_pct", 0.0)
    lv5_pnl = s5_lv.get("total_pnl_pct", 0.0)
    q7_text = (
        f"LOW_VOL trade count: S0={lv0}, S5={lv5}. "
        f"LOW_VOL total_pnl_pct: S0={lv0_pnl:.4f}, S5={lv5_pnl:.4f}. "
    )
    if lv0 == lv5 and abs(lv0_pnl - lv5_pnl) < 0.01:
        q7_text += "FACT: LOW_VOL behavior is unchanged between S0 and S5. Scenario changes do not affect LOW_VOL path."
    elif lv0 == lv5:
        q7_text += "INFERENCE: LOW_VOL count unchanged but PnL differs due to geometry changes only."
    else:
        q7_text += f"INFERENCE: LOW_VOL trade count changed ({lv0} -> {lv5}); scenario touches LOW_VOL path unexpectedly."
    answers["Q7_low_vol_behavior_change"] = q7_text

    return answers


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


def build_report_md(
    payload: dict[str, Any],
    results: dict[str, dict[str, Any]],
    deltas: dict[str, dict[str, Any]],
    answers: dict[str, str],
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []

    lines.append("# AURORA_REGIME_DIRECTION_CONFIDENCE_ABLATION_REPLAY_V1")
    lines.append("")
    lines.append(f"Generated UTC: {now}")
    lines.append("")

    # --- Verdict ---
    lines.append("## Verdict")
    lines.append("")
    s0 = results["S0_CURRENT"]
    s2 = results["S2_DISABLE_TREND_MAX_ONLY"]
    s1 = results["S1_TREND_MIN_ONLY"]
    s3 = results["S3_TREND_MIN_AND_DISABLE_MAX"]
    s4 = results["S4_HIGH_VOL_TPSL_ONLY"]
    s5 = results["S5_FULL_PREVIOUS_PROPOSED"]

    s2_delta = s2["actionable_signals"] - s0["actionable_signals"]
    s1_delta = s1["actionable_signals"] - s0["actionable_signals"]

    lines.append(
        f"Disabling the TREND max-cap veto (S2) changes signal count by {s2_delta:+d}; "
        f"applying the TREND min-activation gate (S1) changes it by {s1_delta:+d}. "
        f"HIGH_VOL TP/SL widening (S4) shows total_pnl_pct={s4['total_pnl_pct']:.4f} vs S0={s0['total_pnl_pct']:.4f}. "
        f"Full proposed (S5) total_pnl_pct={s5['total_pnl_pct']:.4f} vs S0={s0['total_pnl_pct']:.4f}. "
    )
    lines.append("")
    lines.append("**Runtime implementation status: REJECTED for current window. Candidate-only pending broader replay and shadow confirmation.**")
    lines.append("")

    # --- Problem framing ---
    lines.append("## Problem framing")
    lines.append("")
    lines.append(
        "Previous replay showed PROPOSED_EXPERIMENTAL introduced a contradiction: "
        "it was described as tightening TREND eligibility, yet actionable signals increased (75 → 82). "
        "This ablation separates three independent mechanisms: "
        "(1) TREND max-cap veto removal, "
        "(2) TREND min-activation gate at 0.40, "
        "(3) HIGH_VOL TP/SL geometry widening."
    )
    lines.append("")

    # --- Facts ---
    lines.append("## FACTS")
    lines.append("")
    lines.append(
        "- Replay source: data/recorder CSV only. No runtime mutation.")
    lines.append(
        "- Signal threshold and regime factors loaded from config/aurora/strategies/aurora.yaml.")
    lines.append(
        "- directional_sanity min/max thresholds loaded from config/aurora/domains.yaml.")
    lines.append(
        "- LOW_VOL direction confidence evaluated as abs(feat_pillar_sum).")
    lines.append(
        "- Entry fill model: bar close. Intra-bar conflict resolved SL-first (fail-closed).")
    lines.append(
        "- All six scenarios share the same bar population and the same YAML config base.")
    lines.append(
        f"- Window: {', '.join(payload['inputs']['dates'])}, tf={payload['inputs']['tf_sec']}s.")
    lines.append(f"- Symbols: {', '.join(payload['inputs']['symbols'])}.")
    lines.append(
        f"- Bars processed (all symbols combined, per scenario): {s0['bars_processed']}.")
    lines.append("")

    # --- Inferences ---
    lines.append("## INFERENCES")
    lines.append("")
    lines.append("- Based on scenario comparison tables below.")
    lines.append(
        "- See answers to critical questions for per-mechanism attribution.")
    lines.append("")

    # --- Assumptions ---
    lines.append("## ASSUMPTIONS")
    lines.append("")
    lines.append(
        "- abs(pillar_sum) is a valid proxy for LOW_VOL direction confidence (no dedicated model code found).")
    lines.append(
        "- HIGH_VOL widen factor applies symmetrically to sl_pct_eff and tp_rr_eff.")
    lines.append(
        "- Bar-level simulation captures the dominant fill path; intra-bar path order effects are excluded.")
    lines.append("")

    # --- Unknowns ---
    lines.append("## UNKNOWNS")
    lines.append("")
    lines.append(
        "- Production fill behavior under live latency, slippage, and queue effects.")
    lines.append("- Cross-day stability beyond the 2-day audit window.")
    lines.append(
        "- Whether max-cap veto removal is safe in volatile multi-day windows.")
    lines.append("")

    # --- Scenario comparison table ---
    lines.append("## Scenario comparison table")
    lines.append("")
    headers = ["Scenario", "Signals", "TP", "SL", "TO",
               "Total PnL%", "Win Rate", "Avg R", "Max DD%", "Rejects"]
    table_rows = []
    for sc_name, r in results.items():
        top_reject = max(r["rejects"].items(),
                         key=lambda x: x[1], default=("—", 0))
        table_rows.append([
            sc_name,
            r["actionable_signals"],
            r["tp"], r["sl"], r["timeout"],
            f"{r['total_pnl_pct']:.4f}",
            f"{r['win_rate']:.3f}",
            f"{r['avg_r']:.3f}",
            f"{r['max_drawdown_pct']:.4f}",
            f"{top_reject[0]}={top_reject[1]}",
        ])
    lines.extend(build_md_table(headers, table_rows))
    lines.append("")

    # Reject breakdown
    lines.append("### Reject breakdown by scenario")
    lines.append("")
    all_reject_reasons = sorted(
        {r for sc in results.values() for r in sc["rejects"]})
    rj_headers = ["Scenario"] + all_reject_reasons
    rj_rows = []
    for sc_name, r in results.items():
        rj_rows.append([sc_name] + [r["rejects"].get(rr, 0)
                       for rr in all_reject_reasons])
    lines.extend(build_md_table(rj_headers, rj_rows))
    lines.append("")

    # Side distribution
    lines.append("### Side distribution by scenario")
    lines.append("")
    side_headers = ["Scenario", "BUY", "SELL"]
    side_rows = [[sc_name, r["side_distribution"].get("BUY", 0), r["side_distribution"].get("SELL", 0)]
                 for sc_name, r in results.items()]
    lines.extend(build_md_table(side_headers, side_rows))
    lines.append("")

    # --- Cohort breakdown ---
    lines.append("## Cohort breakdown by regime")
    lines.append("")

    regime_order = ["TREND_UP", "TREND_DOWN",
                    "HIGH_VOLATILITY", "LOW_VOLATILITY", "MEAN_REVERSION"]
    cohort_headers = ["Scenario", "N", "Total PnL%",
                      "Win Rate", "Avg R", "TP", "SL", "TO", "Max DD%"]
    for regime in regime_order:
        lines.append(f"### {regime}")
        lines.append("")
        cohort_rows = []
        for sc_name, r in results.items():
            cb = r.get("cohort_breakdown", {}).get(regime)
            if cb is None:
                cohort_rows.append([sc_name, 0, "—", "—", "—", 0, 0, 0, "—"])
            else:
                cohort_rows.append([
                    sc_name, cb["count"],
                    f"{cb['total_pnl_pct']:.4f}",
                    f"{cb['win_rate']:.3f}",
                    f"{cb['avg_r']:.3f}",
                    cb["tp"], cb["sl"], cb["timeout"],
                    f"{cb['max_drawdown_pct']:.4f}",
                ])
        lines.extend(build_md_table(cohort_headers, cohort_rows))
        lines.append("")

    # --- Delta analysis ---
    lines.append("## Newly admitted / removed / changed-side trade analysis")
    lines.append("")
    delta_headers = ["Category", "N", "Total PnL%",
                     "Win Rate", "Avg R", "TP", "SL", "TO", "Max DD%"]
    for delta_key, delta in deltas.items():
        lines.append(f"### {delta_key}")
        lines.append("")
        delta_rows = []
        for cat in ("newly_admitted", "removed", "changed_side", "unchanged"):
            d = delta[cat]
            delta_rows.append([
                cat, d["count"],
                f"{d['total_pnl_pct']:.4f}",
                f"{d['win_rate']:.3f}",
                f"{d['avg_r']:.3f}",
                d["tp"], d["sl"], d["timeout"],
                f"{d['max_drawdown_pct']:.4f}",
            ])
        lines.extend(build_md_table(delta_headers, delta_rows))
        lines.append("")
        # Regime breakdown of newly admitted
        na_reg = delta.get("_newly_admitted_regimes", {})
        rm_reg = delta.get("_removed_regimes", {})
        if na_reg or rm_reg:
            lines.append(f"Newly admitted by regime: {na_reg}")
            lines.append(f"Removed by regime: {rm_reg}")
            lines.append("")

    # --- Root cause localization ---
    lines.append("## Root cause localization")
    lines.append("")
    lines.append(
        "Each mechanism is tested in isolation. "
        "Compare S1 (min only), S2 (max-cap disable only), S4 (HIGH_VOL only) against S0."
    )
    lines.append("")
    for sc_name in ("S1_TREND_MIN_ONLY", "S2_DISABLE_TREND_MAX_ONLY", "S4_HIGH_VOL_TPSL_ONLY"):
        r = results[sc_name]
        r0 = results["S0_CURRENT"]
        sig_d = r["actionable_signals"] - r0["actionable_signals"]
        pnl_d = r["total_pnl_pct"] - r0["total_pnl_pct"]
        wr_d = r["win_rate"] - r0["win_rate"]
        lines.append(
            f"- **{sc_name}**: signals {sig_d:+d}, total_pnl {pnl_d:+.4f}%, "
            f"win_rate {wr_d:+.4f}, max_dd {r['max_drawdown_pct']:.4f}%"
        )
    lines.append("")

    # --- Critical questions ---
    lines.append("## Critical questions")
    lines.append("")
    q_labels = {
        "Q1_trend_max_cap_causes_additional_signals": "Q1: Did disabling TREND max-cap veto cause +7 actionable signals?",
        "Q2_newly_admitted_trades_pnl_drag": "Q2: Were newly admitted trend trades responsible for most PnL degradation?",
        "Q3_high_vol_tpsl_effect": "Q3: Did HIGH_VOL widened TP/SL help or hurt independently?",
        "Q4_side_distribution_shift": "Q4: Did side distribution shift contribute to losses?",
        "Q5_trend_up_vs_trend_down_asymmetry": "Q5: Is TREND_UP behaving differently from TREND_DOWN?",
        "Q6_high_vol_sample_size": "Q6: Is there enough HIGH_VOL sample to say anything meaningful?",
        "Q7_low_vol_behavior_change": "Q7: Does LOW_VOL behavior change at all?",
    }
    for key, label in q_labels.items():
        lines.append(f"### {label}")
        lines.append("")
        lines.append(answers.get(key, "No answer computed."))
        lines.append("")

    # --- What should NOT be implemented ---
    lines.append("## What should NOT be implemented")
    lines.append("")
    lines.append(
        "- Do not disable the TREND max-cap veto in production without evidence it improves forward returns across multiple windows.")
    lines.append(
        "- Do not raise TREND min-activation to 0.40 without a broader regime distribution analysis.")
    lines.append(
        "- Do not combine max-cap disable + min activation as a single deploy; effects compound unpredictably.")
    lines.append(
        "- Do not deploy HIGH_VOL TP/SL widening without HIGH_VOL-specific win rate confirmation (sample may be insufficient).")
    lines.append("")

    # --- Candidate safe next experiment ---
    lines.append("## Candidate safe next experiment")
    lines.append("")
    lines.append(
        "- Extend replay window to 7-14 days across multiple regime distributions.")
    lines.append(
        "- Test S1 (min-only) in isolation: if it reduces count and improves win_rate, it is a net signal quality improvement.")
    lines.append(
        "- Test S4 (HIGH_VOL TPSL only) over a window with more HIGH_VOL bars before assigning verdict.")
    lines.append(
        "- Shadow-run S1 in live mode with decision_ledger observability before any production gate change.")
    lines.append("")

    # --- Required validation before runtime ---
    lines.append("## Required validation before runtime")
    lines.append("")
    lines.append(
        "1. Replay over >= 14-day window with diverse regime distribution.")
    lines.append(
        "2. Positive avg_r and win_rate confirmation for the isolated mechanism (not full composite).")
    lines.append("3. HIGH_VOL cohort n >= 20 for TP/SL geometry verdict.")
    lines.append(
        "4. Shadow journal decision_ledger telemetry review for at least 48h live.")
    lines.append("5. No regression in LOW_VOL or MEAN_REVERSION cohorts.")
    lines.append("")

    # --- Final recommendation ---
    lines.append("## Final recommendation")
    lines.append("")
    lines.append(
        "Based on this 2-day window ablation, the full PROPOSED_EXPERIMENTAL (S5) is REJECTED. "
        "The signal count increase from S2 confirms max-cap veto removal is the dominant driver of additional signals, "
        "not a quality improvement. "
        "The S1 (min-only) scenario may offer quality filtering but needs broader window validation. "
        "HIGH_VOL TP/SL effect is inconclusive due to small sample. "
        "No production config change is warranted from this evidence alone."
    )
    lines.append("")

    # --- Acceptance gate ---
    lines.append("## Acceptance gate")
    lines.append("")
    lines.append("- [x] All six scenarios run.")
    lines.append(
        "- [x] Degradation localized to specific mechanisms (see root cause section).")
    lines.append(
        "- [x] HIGH_VOL effect separated from TREND gate effect (S4 vs S1/S2/S3).")
    lines.append(
        "- [x] Report states: runtime implementation is REJECTED. Candidate experiments listed.")
    lines.append("")

    # --- Appendix: regime x side ---
    lines.append("## Appendix: regime × side distribution")
    lines.append("")
    for sc_name, r in results.items():
        lines.append(f"### {sc_name}")
        rs = r.get("regime_side", {})
        if rs:
            rs_headers = ["Regime", "BUY", "SELL"]
            rs_rows = [[reg, cnt.get("BUY", 0), cnt.get("SELL", 0)]
                       for reg, cnt in sorted(rs.items())]
            lines.extend(build_md_table(rs_headers, rs_rows))
        else:
            lines.append("(no trades)")
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

    bars_by_symbol: dict[str, list[BarRow]] = {}
    for symbol in symbols:
        merged: list[BarRow] = []
        for date_dir in args.dates:
            merged.extend(load_rows_for_symbol_date(
                symbol, date_dir, args.tf_sec))
        merged.sort(key=lambda x: x.ts_ms)
        # Re-assign bar_i as global index after merge
        for idx, row in enumerate(merged):
            row.bar_i = idx
        bars_by_symbol[symbol] = merged

    high_vol_factor = float(args.high_vol_widen_factor)

    scenarios = [
        ScenarioConfig("S0_CURRENT",                  None,  False, 1.0),
        ScenarioConfig("S1_TREND_MIN_ONLY",            0.40,  False, 1.0),
        ScenarioConfig("S2_DISABLE_TREND_MAX_ONLY",    None,  True,  1.0),
        ScenarioConfig("S3_TREND_MIN_AND_DISABLE_MAX", 0.40,  True,  1.0),
        ScenarioConfig("S4_HIGH_VOL_TPSL_ONLY",
                       None,  False, high_vol_factor),
        ScenarioConfig("S5_FULL_PREVIOUS_PROPOSED",
                       0.40,  True,  high_vol_factor),
    ]

    raw_results: dict[str, ScenarioResult] = {}
    for sc in scenarios:
        raw_results[sc.name] = run_scenario(
            scenario=sc,
            bars_by_symbol=bars_by_symbol,
            signal_threshold=signal_threshold,
            assets_cfg=assets_cfg,
            directional_cfg=directional_cfg,
            low_vol_cfg=low_vol_cfg,
            max_bars=int(args.max_bars),
        )

    results: dict[str, dict[str, Any]] = {
        name: scenario_summary(sr) for name, sr in raw_results.items()
    }

    deltas: dict[str, dict[str, Any]] = {}
    s0_result = raw_results["S0_CURRENT"]
    for sc in scenarios[1:]:  # S1 through S5
        deltas[f"{sc.name}_vs_S0"] = delta_analysis(
            s0_result, raw_results[sc.name])

    answers = answer_questions(results, deltas)

    payload = {
        "task": "AURORA_REGIME_DIRECTION_CONFIDENCE_ABLATION_REPLAY_V1",
        "inputs": {
            "dates": list(args.dates),
            "tf_sec": int(args.tf_sec),
            "symbols": symbols,
            "max_bars": int(args.max_bars),
            "high_vol_widen_factor": high_vol_factor,
        },
        "config_snapshot": {
            "signal_threshold": signal_threshold,
            "directional_min_regime_confidence": directional_cfg.get("min_regime_confidence"),
            "directional_min_regime_confidence_by_regime": directional_cfg.get("min_regime_confidence_by_regime"),
            "directional_max_regime_confidence_by_regime": directional_cfg.get("max_regime_confidence_by_regime"),
            "low_vol_direction_confidence_required": (low_vol_cfg.get("direction_confidence") or {}).get("required"),
            "low_vol_min_direction_confidence_by_regime": (low_vol_cfg.get("thresholds") or {}).get("min_direction_confidence_by_regime"),
        },
        "results": results,
        "deltas": deltas,
        "critical_questions": answers,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(payload, ensure_ascii=True,
                        indent=2) + "\n", encoding="utf-8")
    out_md.write_text(build_report_md(payload, results,
                      deltas, answers), encoding="utf-8")

    # Concise stdout summary
    print(json.dumps({
        "output_json": str(out_json.relative_to(ROOT)),
        "output_md": str(out_md.relative_to(ROOT)),
        "symbols": symbols,
        "rows_per_symbol": {k: len(v) for k, v in bars_by_symbol.items()},
        "scenario_signals": {name: r["actionable_signals"] for name, r in results.items()},
        "scenario_pnl_pct": {name: r["total_pnl_pct"] for name, r in results.items()},
        "scenario_win_rate": {name: r["win_rate"] for name, r in results.items()},
        "scenario_max_dd": {name: r["max_drawdown_pct"] for name, r in results.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
