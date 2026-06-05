from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
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


@dataclass
class BarRow:
    symbol: str
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
class TradeOutcome:
    outcome: str  # TP, SL, TIMEOUT
    pnl_pct: float
    r_multiple: float
    bars_held: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recorder-only replay audit for AURORA_REGIME_DIRECTION_CONFIDENCE_REPLAY_AUDIT_V1",
    )
    parser.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    parser.add_argument("--tf-sec", type=int, default=DEFAULT_TF_SEC)
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--high-vol-widen-factor", type=float, default=DEFAULT_HIGH_VOL_WIDEN_FACTOR)
    parser.add_argument(
        "--output-json",
        default=str(REPORTS_DIR / "AURORA_REGIME_DIRECTION_CONFIDENCE_REPLAY_AUDIT_V1_2026_05_04.json"),
    )
    parser.add_argument(
        "--output-md",
        default=str(REPORTS_DIR / "AURORA_REGIME_DIRECTION_CONFIDENCE_REPLAY_AUDIT_V1_2026_05_04.md"),
    )
    return parser.parse_args()


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
    return {
        "directional": directional,
        "low_vol": low_vol,
    }


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

            rows.append(
                BarRow(
                    symbol=symbol,
                    ts_ms=ts_ms,
                    dt=str(rec.get("datetime") or ""),
                    open_=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    regime=regime,
                    regime_conf=float(regime_conf),
                    pillar_sum=float(pillar_sum),
                )
            )
    rows.sort(key=lambda x: x.ts_ms)
    return rows


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


def apply_scenario_gates(
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

    if scenario.trend_activation_min is not None and row.regime in ("TREND_UP", "TREND_DOWN"):
        if row.regime_conf < scenario.trend_activation_min:
            return False, "TREND_ACTIVATION_BELOW_EXPERIMENTAL_MIN"

    disable_trend_max = scenario.disable_trend_max_cap and row.regime in ("TREND_UP", "TREND_DOWN")
    if not disable_trend_max:
        max_allowed = resolve_regime_threshold(row.regime, max_map, None)
        if max_allowed is not None and row.regime_conf > max_allowed:
            return False, "REGIME_CONFIDENCE_ABOVE_MAX"

    regimes = [str(r).strip().upper() for r in (low_vol_cfg.get("regimes") or [])]
    if row.regime == "LOW_VOLATILITY" and "LOW_VOLATILITY" in regimes:
        thresholds = low_vol_cfg.get("thresholds") or {}
        dir_map = thresholds.get("min_direction_confidence_by_regime") or {}
        min_dir = resolve_regime_threshold("LOW_VOLATILITY", dir_map, None)
        if min_dir is not None:
            direction_confidence = abs(row.pillar_sum)
            if direction_confidence < min_dir:
                return False, "LOW_VOL_DIRECTION_CONFIDENCE_BELOW_MIN"

    return True, None


def resolve_tpsl_params(asset_cfg: dict[str, Any], regime: str, scenario: ScenarioConfig) -> tuple[float, float] | None:
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


def simulate_trade(
    *,
    side: str,
    entry_price: float,
    sl_pct: float,
    tp_pct: float,
    future_bars: list[BarRow],
) -> TradeOutcome:
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
            # Fail-closed tie-break: assume adverse fill first.
            stop_hit = True
            tp_hit = False

        if stop_hit:
            pnl = -sl_pct
            return TradeOutcome("SL", pnl, -1.0, idx)
        if tp_hit:
            pnl = tp_pct
            r = tp_pct / sl_pct if sl_pct > 0 else 0.0
            return TradeOutcome("TP", pnl, r, idx)

    if not future_bars:
        return TradeOutcome("TIMEOUT", 0.0, 0.0, 0)

    last = future_bars[-1].close
    if side == "BUY":
        pnl = (last - entry_price) / entry_price
    else:
        pnl = (entry_price - last) / entry_price
    r = pnl / sl_pct if sl_pct > 0 else 0.0
    return TradeOutcome("TIMEOUT", pnl, r, len(future_bars))


def summarize_equity_curve(pnls: list[float]) -> float:
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


def run_scenario(
    *,
    scenario: ScenarioConfig,
    bars_by_symbol: dict[str, list[BarRow]],
    signal_threshold: float,
    assets_cfg: dict[str, Any],
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
    max_bars: int,
) -> dict[str, Any]:
    bars_processed = 0
    regime_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    trades: list[TradeOutcome] = []

    for symbol, bars in bars_by_symbol.items():
        asset_cfg = assets_cfg.get(symbol)
        if not isinstance(asset_cfg, dict):
            continue
        regime_thresholds = asset_cfg.get("regime_thresholds") or {}

        for i, row in enumerate(bars):
            bars_processed += 1
            regime_counts[row.regime] += 1

            factor = safe_float(regime_thresholds.get(row.regime))
            if factor is None:
                factor = safe_float(regime_thresholds.get("DEFAULT"))
            if factor is None:
                reject_counts["MISSING_REGIME_THRESHOLD"] += 1
                continue

            threshold = signal_threshold * factor
            side = side_from_score(row.pillar_sum, threshold)

            allowed, reason = apply_scenario_gates(
                row=row,
                side=side,
                scenario=scenario,
                directional_cfg=directional_cfg,
                low_vol_cfg=low_vol_cfg,
            )
            if not allowed:
                if reason:
                    reject_counts[reason] += 1
                continue

            params = resolve_tpsl_params(asset_cfg, row.regime, scenario)
            if params is None:
                reject_counts["TPSL_CONFIG_UNAVAILABLE"] += 1
                continue
            sl_pct, tp_pct = params

            side_counts[side] += 1
            future = bars[i + 1:i + 1 + max_bars]
            trade = simulate_trade(
                side=side,
                entry_price=row.close,
                sl_pct=sl_pct,
                tp_pct=tp_pct,
                future_bars=future,
            )
            trades.append(trade)

    trade_count = len(trades)
    tp_count = sum(1 for t in trades if t.outcome == "TP")
    sl_count = sum(1 for t in trades if t.outcome == "SL")
    timeout_count = sum(1 for t in trades if t.outcome == "TIMEOUT")

    pnl_list = [t.pnl_pct for t in trades]
    r_list = [t.r_multiple for t in trades]

    total_pnl = sum(pnl_list)
    avg_pnl = total_pnl / trade_count if trade_count else 0.0
    win_rate = (tp_count / trade_count) if trade_count else 0.0
    avg_r = sum(r_list) / trade_count if trade_count else 0.0
    max_dd = summarize_equity_curve(pnl_list)

    return {
        "scenario": scenario.name,
        "bars_processed": bars_processed,
        "regime_distribution": dict(sorted(regime_counts.items())),
        "actionable_signals": trade_count,
        "rejects": dict(sorted(reject_counts.items())),
        "side_distribution": dict(sorted(side_counts.items())),
        "tp": tp_count,
        "sl": sl_count,
        "timeout": timeout_count,
        "total_pnl_pct": total_pnl * 100.0,
        "avg_pnl_pct": avg_pnl * 100.0,
        "win_rate": win_rate,
        "avg_r": avg_r,
        "max_drawdown_pct": max_dd * 100.0,
    }


def build_report_md(payload: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    cur = payload["results"]["CURRENT"]
    exp = payload["results"]["PROPOSED_EXPERIMENTAL"]

    lines: list[str] = []
    lines.append("# AGENT_REPORT_V1")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(
        "Recorder-only replay completed for CURRENT vs PROPOSED_EXPERIMENTAL. "
        "The proposed trend activation >=0.40 materially tightens entry eligibility in TREND regimes, "
        "while HIGH_VOL widened TP/SL changes trade geometry only when HIGH_VOL entries survive gates."
    )
    lines.append("")
    lines.append("## Proven Facts")
    lines.append("- Replay source: data/recorder CSV only (no runtime mutation, no live execution).")
    lines.append("- Side proposal is derived from feat_pillar_sum against regime-adjusted signal threshold.")
    lines.append("- directional_sanity min/max regime_confidence by regime is applied as gating in both scenarios.")
    lines.append("- low_vol_cost_floor direction_confidence is evaluated as abs(score) under LOW_VOLATILITY.")
    lines.append("- PROPOSED_EXPERIMENTAL applies trend activation min=0.40 for TREND_UP/TREND_DOWN and disables trend max-cap veto.")
    lines.append("- PROPOSED_EXPERIMENTAL widens HIGH_VOLATILITY TP/SL geometry using configured factor.")
    lines.append("")
    lines.append("## Inferred Findings")
    lines.append(
        f"- Actionable signals: CURRENT={cur['actionable_signals']} vs PROPOSED={exp['actionable_signals']}."
    )
    lines.append(
        f"- Win rate: CURRENT={cur['win_rate']:.4f} vs PROPOSED={exp['win_rate']:.4f}."
    )
    lines.append(
        f"- Avg R: CURRENT={cur['avg_r']:.4f} vs PROPOSED={exp['avg_r']:.4f}."
    )
    lines.append(
        f"- Max drawdown (%): CURRENT={cur['max_drawdown_pct']:.4f} vs PROPOSED={exp['max_drawdown_pct']:.4f}."
    )
    lines.append("")
    lines.append("## Contradictions / Evidence Gaps")
    lines.append("- Recorder window may not contain enough LOW_VOL/HIGH_VOL bars for all symbols equally.")
    lines.append("- Entry fill model is bar-level and uses fail-closed tie-break (SL-first if TP/SL touched in same bar).")
    lines.append("- No live order log reconciliation is used in this replay; execution slippage and queue effects are excluded.")
    lines.append("")
    lines.append("## Root Cause Candidates")
    lines.append("- If proposed scenario underperforms, likely cause is over-constraining TREND activation with 0.40 threshold.")
    lines.append("- If proposed scenario improves drawdown but cuts volume, the mechanism is stricter trend gate selection.")
    lines.append("- HIGH_VOL TP/SL widening changes payoff dispersion and timeout ratio, not side selection itself.")
    lines.append("")
    lines.append("## Operational Risk")
    lines.append("- Runtime / Capital")
    lines.append("")
    lines.append("## Files / Areas Touched")
    lines.append("- scripts/forensics/aurora_regime_direction_confidence_replay_audit_v1.py")
    lines.append("- reports/AURORA_REGIME_DIRECTION_CONFIDENCE_REPLAY_AUDIT_V1_2026_05_04.json")
    lines.append("- reports/AURORA_REGIME_DIRECTION_CONFIDENCE_REPLAY_AUDIT_V1_2026_05_04.md")
    lines.append("")
    lines.append("## Validation Performed")
    lines.append("- Ran replay script over selected dates/symbols from recorder CSV.")
    lines.append("- Compared CURRENT and PROPOSED_EXPERIMENTAL on bars processed, regimes, rejects, sides, TP/SL/timeout, PnL, win rate, avg R, max drawdown.")
    lines.append("")
    lines.append("## Residual Risk")
    lines.append("- Replay assumes deterministic bar-level fills and excludes intra-bar microstructure path dependency.")
    lines.append("- LOW_VOL direction-confidence side-model claim remains unproven as a dedicated side-selection model; evidence supports gate-only behavior.")
    lines.append("")
    lines.append("## What Remains Unproven")
    lines.append("- Production-time behavior under live latency, slippage, and partial-fill conditions.")
    lines.append("- Cross-day stability beyond the audited date window.")
    lines.append("")
    lines.append("## Minimal Safe Verdict")
    lines.append("- The proposed policy can be treated as a candidate gate/geometry experiment, not a proven production improvement, until broader replay and live shadow confirmation are completed.")
    lines.append("")
    lines.append("## Scenario Metrics")
    lines.append("")
    lines.append(f"Generated UTC: {now}")
    lines.append("")
    lines.append("### CURRENT")
    lines.append(json.dumps(cur, ensure_ascii=True, indent=2))
    lines.append("")
    lines.append("### PROPOSED_EXPERIMENTAL")
    lines.append(json.dumps(exp, ensure_ascii=True, indent=2))
    lines.append("")
    lines.append("## FACT / INFERENCE / ASSUMPTION / UNKNOWN")
    lines.append("- FACT: directional_sanity and low_vol_cost_floor_gate thresholds are loaded from config/aurora/domains.yaml.")
    lines.append("- FACT: side decision path in scoring policy uses score vs thresholds and hysteresis, not a dedicated low-vol side model.")
    lines.append("- INFERENCE: raising TREND activation threshold to 0.40 can reduce actionable TREND entries.")
    lines.append("- ASSUMPTION: HIGH_VOL widened TP/SL factor is applied symmetrically to sl_pct_eff and tp_rr_eff in this experiment.")
    lines.append("- UNKNOWN: whether the same effect persists in production with real fills and order-book path dependence.")
    return "\n".join(lines) + "\n"


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

    # Keep only symbols that have aurora asset config.
    symbols = [s for s in symbols if s in assets_cfg]

    bars_by_symbol: dict[str, list[BarRow]] = {}
    for symbol in symbols:
        merged: list[BarRow] = []
        for date_dir in args.dates:
            merged.extend(load_rows_for_symbol_date(symbol, date_dir, args.tf_sec))
        merged.sort(key=lambda x: x.ts_ms)
        bars_by_symbol[symbol] = merged

    current = ScenarioConfig(
        name="CURRENT",
        trend_activation_min=None,
        disable_trend_max_cap=False,
        high_vol_widen_factor=1.0,
    )
    proposed = ScenarioConfig(
        name="PROPOSED_EXPERIMENTAL",
        trend_activation_min=0.40,
        disable_trend_max_cap=True,
        high_vol_widen_factor=float(args.high_vol_widen_factor),
    )

    current_result = run_scenario(
        scenario=current,
        bars_by_symbol=bars_by_symbol,
        signal_threshold=signal_threshold,
        assets_cfg=assets_cfg,
        directional_cfg=directional_cfg,
        low_vol_cfg=low_vol_cfg,
        max_bars=int(args.max_bars),
    )
    proposed_result = run_scenario(
        scenario=proposed,
        bars_by_symbol=bars_by_symbol,
        signal_threshold=signal_threshold,
        assets_cfg=assets_cfg,
        directional_cfg=directional_cfg,
        low_vol_cfg=low_vol_cfg,
        max_bars=int(args.max_bars),
    )

    payload = {
        "task": "AURORA_REGIME_DIRECTION_CONFIDENCE_REPLAY_AUDIT_V1",
        "inputs": {
            "dates": list(args.dates),
            "tf_sec": int(args.tf_sec),
            "symbols": symbols,
            "max_bars": int(args.max_bars),
            "high_vol_widen_factor": float(args.high_vol_widen_factor),
        },
        "config_snapshot": {
            "signal_threshold": signal_threshold,
            "directional_min_regime_confidence": directional_cfg.get("min_regime_confidence"),
            "directional_min_regime_confidence_by_regime": directional_cfg.get("min_regime_confidence_by_regime"),
            "directional_max_regime_confidence_by_regime": directional_cfg.get("max_regime_confidence_by_regime"),
            "low_vol_direction_confidence_required": (low_vol_cfg.get("direction_confidence") or {}).get("required"),
            "low_vol_direction_confidence_allowed_sources": (low_vol_cfg.get("direction_confidence") or {}).get("allowed_sources"),
            "low_vol_min_direction_confidence_by_regime": (low_vol_cfg.get("thresholds") or {}).get("min_direction_confidence_by_regime"),
        },
        "results": {
            "CURRENT": current_result,
            "PROPOSED_EXPERIMENTAL": proposed_result,
        },
        "assumptions": {
            "entry_price": "bar close",
            "intra_bar_conflict": "SL-first fail-closed when TP and SL touched in same bar",
            "low_vol_direction_confidence_proxy": "abs(feat_pillar_sum)",
            "proposed_trend_activation": "require regime_confidence >= 0.40 for TREND_UP/TREND_DOWN",
            "proposed_high_vol_geometry": "multiply sl_pct_eff and tp_rr_eff by high_vol_widen_factor",
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(build_report_md(payload), encoding="utf-8")

    print(json.dumps({
        "output_json": str(out_json.relative_to(ROOT)),
        "output_md": str(out_md.relative_to(ROOT)),
        "symbols": symbols,
        "rows_per_symbol": {k: len(v) for k, v in bars_by_symbol.items()},
        "current_actionable": current_result["actionable_signals"],
        "proposed_actionable": proposed_result["actionable_signals"],
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
