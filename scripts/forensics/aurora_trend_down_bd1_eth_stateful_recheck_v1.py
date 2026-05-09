#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DATE_TAG = "2026_05_04"

DATASET_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"
ANATOMY_JSON = REPORTS / "AURORA_TREND_DOWN_BAR_ANATOMY_FORENSIC_V1_2026_05_04.json"

OUT_MD = REPORTS / \
    f"AURORA_TREND_DOWN_BD1_ETH_STATEFUL_RECHECK_V1_{DATE_TAG}.md"
OUT_JSON = REPORTS / \
    f"AURORA_TREND_DOWN_BD1_ETH_STATEFUL_RECHECK_V1_{DATE_TAG}.json"
OUT_TRADES = REPORTS / \
    f"AURORA_TREND_DOWN_BD1_ETH_STATEFUL_TRADES_{DATE_TAG}.csv"

SYMBOL = "ETHUSDT"
REGIME = "TREND_DOWN"


@dataclass(frozen=True)
class Scenario:
    name: str
    tp_bps: float
    sl_bps: float
    timeout_bars: int
    exit_on_regime_change: bool


SCENARIOS: List[Scenario] = [
    Scenario("S0_BD1_ETH_STATEFUL_RC_ON", 70.0, 110.0, 36, True),
    Scenario("S1_BD1_ETH_STATEFUL_RC_OFF", 70.0, 110.0, 36, False),
    Scenario("S2_BD1_ETH_STATEFUL_TIMEOUT_24_RC_ON", 70.0, 110.0, 24, True),
    Scenario("S2_BD1_ETH_STATEFUL_TIMEOUT_24_RC_OFF", 70.0, 110.0, 24, False),
    Scenario("S3_BD1_ETH_STATEFUL_TIMEOUT_18_RC_ON", 70.0, 110.0, 18, True),
    Scenario("S3_BD1_ETH_STATEFUL_TIMEOUT_18_RC_OFF", 70.0, 110.0, 18, False),
    Scenario("S4_BD1_ETH_STATEFUL_TP55_SL110_RC_ON", 55.0, 110.0, 36, True),
    Scenario("S4_BD1_ETH_STATEFUL_TP55_SL110_RC_OFF", 55.0, 110.0, 36, False),
    Scenario("S5_BD1_ETH_STATEFUL_TP70_SL90_RC_ON", 70.0, 90.0, 36, True),
    Scenario("S5_BD1_ETH_STATEFUL_TP70_SL90_RC_OFF", 70.0, 90.0, 36, False),
]


def _safe_div(a: float, b: float) -> float:
    if abs(b) <= 1e-12:
        return float("nan")
    return a / b


def _max_drawdown_from_trade_series(trade_pnl_pct: np.ndarray) -> float:
    if len(trade_pnl_pct) == 0:
        return 0.0
    eq = np.cumsum(trade_pnl_pct)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return float(np.min(dd))


def _rows_to_md(rows: List[Dict[str, Any]], cols: List[str], max_rows: int = 30) -> str:
    if not rows:
        return "(empty)"
    rows = rows[:max_rows]
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [head, sep]
    for r in rows:
        vals: List[str] = []
        for c in cols:
            v = r.get(c)
            if isinstance(v, (float, np.floating)):
                vals.append("null" if not np.isfinite(
                    float(v)) else f"{float(v):.4f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def load_eth_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_CSV)
    df = df[df["symbol"] == SYMBOL].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def add_bd1_features(df: pd.DataFrame) -> pd.DataFrame:
    s = df.copy().reset_index(drop=True)

    o = s["open"].astype(float).values
    h = s["high"].astype(float).values
    l = s["low"].astype(float).values
    c = s["close"].astype(float).values

    bar_range = h - l
    denom = bar_range.copy()
    denom[denom <= 1e-12] = np.nan

    s["signed_body_bps"] = (c - o) / o * 10000.0
    s["close_position_in_bar"] = (c - l) / denom

    # Exact BD1 definition from prior anatomy forensic:
    # regime == TREND_DOWN, signed_body_bps > 0, close_position_in_bar >= 0.50
    s["bd1_signal"] = (
        (s["regime"] == REGIME)
        & (s["signed_body_bps"] > 0)
        & (s["close_position_in_bar"] >= 0.50)
    )

    return s


def run_stateful_scenario(df: pd.DataFrame, sc: Scenario) -> tuple[pd.DataFrame, Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    ts = df["timestamp"].values
    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    reg = df["regime"].astype(str).values
    signal = df["bd1_signal"].fillna(False).values.astype(bool)

    raw_signal_count = int(signal.sum())
    skipped_signals_open_position = 0
    same_bar_tp_sl_conflict_count = 0

    position: Dict[str, Any] | None = None
    trades: List[Dict[str, Any]] = []

    # i is the current bar where pending signal from i-1 may enter at OPEN(i).
    for i in range(1, len(df)):
        pending_signal = bool(signal[i - 1])

        # Entry decision happens at bar open before any intrabar exit checks.
        if pending_signal:
            if position is None:
                position = {
                    "entry_idx": i,
                    "entry_ts": ts[i],
                    "entry_price": float(o[i]),
                    "signal_idx": i - 1,
                    "signal_ts": ts[i - 1],
                }
            else:
                skipped_signals_open_position += 1

        if position is None:
            continue

        entry_idx = int(position["entry_idx"])
        entry_price = float(position["entry_price"])
        bars_held = int(i - entry_idx + 1)

        tp_price = entry_price * (1.0 - sc.tp_bps / 10000.0)
        sl_price = entry_price * (1.0 + sc.sl_bps / 10000.0)

        low_hit_tp = bool(l[i] <= tp_price)
        high_hit_sl = bool(h[i] >= sl_price)
        rc_trigger = bool(sc.exit_on_regime_change and (reg[i] != REGIME))
        timeout_trigger = bool(bars_held >= sc.timeout_bars)

        # Conflict counting is informational; conservative execution uses SL priority.
        if low_hit_tp and high_hit_sl:
            same_bar_tp_sl_conflict_count += 1

        exit_reason = None
        exit_price = None

        if high_hit_sl:
            exit_reason = "SL"
            exit_price = sl_price
        elif low_hit_tp:
            exit_reason = "TP"
            exit_price = tp_price
        elif rc_trigger:
            exit_reason = "REGIME_CHANGE"
            exit_price = float(c[i])
        elif timeout_trigger:
            exit_reason = "TIMEOUT"
            exit_price = float(c[i])

        if exit_reason is None:
            continue

        pnl_pct = (entry_price - float(exit_price)) / entry_price * 100.0
        pnl_bps = pnl_pct * 100.0
        r = _safe_div(pnl_bps, sc.sl_bps)

        trades.append(
            {
                "scenario": sc.name,
                "symbol": SYMBOL,
                "signal_timestamp": pd.Timestamp(position["signal_ts"]),
                "entry_timestamp": pd.Timestamp(position["entry_ts"]),
                "exit_timestamp": pd.Timestamp(ts[i]),
                "entry_index": int(entry_idx),
                "exit_index": int(i),
                "entry_price": entry_price,
                "exit_price": float(exit_price),
                "tp_bps": sc.tp_bps,
                "sl_bps": sc.sl_bps,
                "timeout_bars": sc.timeout_bars,
                "exit_on_regime_change": sc.exit_on_regime_change,
                "bars_held": bars_held,
                "exit_reason": exit_reason,
                "same_bar_tp_sl_conflict": bool(low_hit_tp and high_hit_sl),
                "pnl_pct": pnl_pct,
                "pnl_bps": pnl_bps,
                "r_multiple": r,
                "net_4bps_pct": pnl_pct - 0.04,
                "net_6bps_pct": pnl_pct - 0.06,
                "net_8bps_pct": pnl_pct - 0.08,
                "net_10bps_pct": pnl_pct - 0.10,
            }
        )

        position = None

    tdf = pd.DataFrame(trades)

    if tdf.empty:
        summary = {
            "scenario": sc.name,
            "tp_bps": sc.tp_bps,
            "sl_bps": sc.sl_bps,
            "timeout_bars": sc.timeout_bars,
            "exit_on_regime_change": sc.exit_on_regime_change,
            "raw_signal_count": raw_signal_count,
            "skipped_signals_open_position": skipped_signals_open_position,
            "actual_trade_count": 0,
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "regime_change_exit_count": 0,
            "win_rate_pct": 0.0,
            "gross_pnl_pct": 0.0,
            "net_pnl_pct_4bps": 0.0,
            "net_pnl_pct_6bps": 0.0,
            "net_pnl_pct_8bps": 0.0,
            "net_pnl_pct_10bps": 0.0,
            "avg_pnl_pct_per_trade": 0.0,
            "avg_R": 0.0,
            "total_R": 0.0,
            "max_drawdown_pct": 0.0,
            "average_bars_held": 0.0,
            "median_bars_held": 0.0,
            "same_bar_tp_sl_conflict_count": same_bar_tp_sl_conflict_count,
        }
        monthly = pd.DataFrame()
        rolling7 = pd.DataFrame()
        return tdf, summary, monthly, rolling7

    tp_count = int((tdf["exit_reason"] == "TP").sum())
    sl_count = int((tdf["exit_reason"] == "SL").sum())
    timeout_count = int((tdf["exit_reason"] == "TIMEOUT").sum())
    rc_count = int((tdf["exit_reason"] == "REGIME_CHANGE").sum())

    summary = {
        "scenario": sc.name,
        "tp_bps": sc.tp_bps,
        "sl_bps": sc.sl_bps,
        "timeout_bars": sc.timeout_bars,
        "exit_on_regime_change": sc.exit_on_regime_change,
        "raw_signal_count": raw_signal_count,
        "skipped_signals_open_position": skipped_signals_open_position,
        "actual_trade_count": int(len(tdf)),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "regime_change_exit_count": rc_count,
        "win_rate_pct": float((tdf["pnl_pct"] > 0).mean() * 100.0),
        "gross_pnl_pct": float(tdf["pnl_pct"].sum()),
        "net_pnl_pct_4bps": float(tdf["net_4bps_pct"].sum()),
        "net_pnl_pct_6bps": float(tdf["net_6bps_pct"].sum()),
        "net_pnl_pct_8bps": float(tdf["net_8bps_pct"].sum()),
        "net_pnl_pct_10bps": float(tdf["net_10bps_pct"].sum()),
        "avg_pnl_pct_per_trade": float(tdf["pnl_pct"].mean()),
        "avg_R": float(tdf["r_multiple"].mean()),
        "total_R": float(tdf["r_multiple"].sum()),
        "max_drawdown_pct": _max_drawdown_from_trade_series(tdf["pnl_pct"].values),
        "average_bars_held": float(tdf["bars_held"].mean()),
        "median_bars_held": float(tdf["bars_held"].median()),
        "same_bar_tp_sl_conflict_count": same_bar_tp_sl_conflict_count,
    }

    x = tdf.copy()
    x["exit_day"] = pd.to_datetime(x["exit_timestamp"], utc=True).dt.floor("D")
    x["exit_month"] = pd.to_datetime(
        x["exit_timestamp"], utc=True).dt.strftime("%Y-%m")

    monthly = (
        x.groupby("exit_month", as_index=False)
        .agg(
            trades=("pnl_pct", "count"),
            gross_pnl_pct=("pnl_pct", "sum"),
            net_4bps_pct=("net_4bps_pct", "sum"),
            net_6bps_pct=("net_6bps_pct", "sum"),
            net_8bps_pct=("net_8bps_pct", "sum"),
            net_10bps_pct=("net_10bps_pct", "sum"),
            win_rate_pct=("pnl_pct", lambda s: float((s > 0).mean() * 100.0)),
        )
        .sort_values("exit_month")
        .reset_index(drop=True)
    )
    monthly.insert(0, "scenario", sc.name)

    daily = (
        x.groupby("exit_day", as_index=False)
        .agg(
            daily_gross_pnl_pct=("pnl_pct", "sum"),
            daily_net_6bps_pct=("net_6bps_pct", "sum"),
            trades=("pnl_pct", "count"),
        )
        .sort_values("exit_day")
        .reset_index(drop=True)
    )
    daily["exit_day"] = pd.to_datetime(
        daily["exit_day"], utc=True).dt.strftime("%Y-%m-%d")
    daily["rolling_7d_net_6bps_pct"] = daily["daily_net_6bps_pct"].rolling(
        7, min_periods=1).sum()
    daily["rolling_7d_gross_pct"] = daily["daily_gross_pnl_pct"].rolling(
        7, min_periods=1).sum()
    daily.insert(0, "scenario", sc.name)
    rolling7 = daily

    return tdf, summary, monthly, rolling7


def derive_verdict(summary_df: pd.DataFrame) -> str:
    if summary_df.empty:
        return "NEEDS_MORE_DATA"

    base_row = summary_df[summary_df["scenario"]
                          == "S0_BD1_ETH_STATEFUL_RC_ON"]
    if base_row.empty:
        return "NEEDS_MORE_DATA"

    base = base_row.iloc[0]
    raw_signals = float(base["raw_signal_count"])
    trades = float(base["actual_trade_count"])

    overlap_ratio = 0.0 if raw_signals <= 0 else (
        raw_signals - trades) / raw_signals
    net6 = float(base["net_pnl_pct_6bps"])
    net10 = float(base["net_pnl_pct_10bps"])

    if net6 <= 0 and overlap_ratio >= 0.50:
        return "REJECTED_OVERLAP_ARTIFACT"

    if net6 > 0 and net10 > 0:
        # Require at least 4 positive scenario rows at 6bps to call testnet-prep.
        positives = int((summary_df["net_pnl_pct_6bps"] > 0).sum())
        if positives >= 4:
            return "ACCEPTED_FOR_TESTNET_PREP"
        return "CANDIDATE_SURVIVES_BUT_WEAK"

    if net6 > 0 and net10 <= 0:
        return "CANDIDATE_SURVIVES_BUT_WEAK"

    return "NEEDS_MORE_DATA"


def run() -> None:
    started = datetime.now(timezone.utc)

    df = load_eth_dataset()
    df = add_bd1_features(df)

    all_trades: List[pd.DataFrame] = []
    all_summary: List[Dict[str, Any]] = []
    all_monthly: List[pd.DataFrame] = []
    all_rolling7: List[pd.DataFrame] = []

    for sc in SCENARIOS:
        tdf, summary, monthly, rolling7 = run_stateful_scenario(df, sc)
        all_trades.append(tdf)
        all_summary.append(summary)
        if not monthly.empty:
            all_monthly.append(monthly)
        if not rolling7.empty:
            all_rolling7.append(rolling7)

    trades_df = pd.concat(
        all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    summary_df = pd.DataFrame(all_summary)
    monthly_df = pd.concat(
        all_monthly, ignore_index=True) if all_monthly else pd.DataFrame()
    rolling7_df = pd.concat(
        all_rolling7, ignore_index=True) if all_rolling7 else pd.DataFrame()

    verdict = derive_verdict(summary_df)

    # Critical questions.
    q: Dict[str, Any] = {}
    s0 = summary_df[summary_df["scenario"] == "S0_BD1_ETH_STATEFUL_RC_ON"]
    s1 = summary_df[summary_df["scenario"] == "S1_BD1_ETH_STATEFUL_RC_OFF"]

    if not s0.empty:
        b = s0.iloc[0]
        q["q1_remains_positive_after_no_overlap"] = bool(
            float(b["net_pnl_pct_6bps"]) > 0)
        q["q2_signals_to_actual_trades"] = {
            "raw_signal_count": int(b["raw_signal_count"]),
            "actual_trade_count": int(b["actual_trade_count"]),
            "skipped_signals_open_position": int(b["skipped_signals_open_position"]),
        }
        q["q3_overlap_inflation_likely"] = bool(
            int(b["actual_trade_count"]) < int(b["raw_signal_count"]))
        q["q7_survive_6bps"] = bool(float(b["net_pnl_pct_6bps"]) > 0)
        q["q7_survive_10bps"] = bool(float(b["net_pnl_pct_10bps"]) > 0)

    if not s0.empty and not s1.empty:
        q["q4_rc_help_or_hurt"] = {
            "rc_on_net6": float(s0.iloc[0]["net_pnl_pct_6bps"]),
            "rc_off_net6": float(s1.iloc[0]["net_pnl_pct_6bps"]),
            "rc_helps": bool(float(s0.iloc[0]["net_pnl_pct_6bps"]) > float(s1.iloc[0]["net_pnl_pct_6bps"])),
        }

    # Best timeout by RC mode at net6.
    timeout_rows = summary_df[
        summary_df["scenario"].str.contains(
            "TIMEOUT_24|TIMEOUT_18|S0_BD1_ETH_STATEFUL_RC_ON|S1_BD1_ETH_STATEFUL_RC_OFF")
    ].copy()
    if not timeout_rows.empty:
        q["q5_timeout_36_remains_best"] = timeout_rows.sort_values("net_pnl_pct_6bps", ascending=False).head(1)[
            ["scenario", "net_pnl_pct_6bps"]
        ].to_dict(orient="records")

    # Best TP/SL by RC mode.
    tpsl_rows = summary_df[
        summary_df["scenario"].str.contains(
            "TP55_SL110|TP70_SL90|S0_BD1_ETH_STATEFUL_RC_ON|S1_BD1_ETH_STATEFUL_RC_OFF")
    ].copy()
    if not tpsl_rows.empty:
        q["q6_tp70_sl110_remains_best"] = tpsl_rows.sort_values("net_pnl_pct_6bps", ascending=False).head(1)[
            ["scenario", "tp_bps", "sl_bps", "net_pnl_pct_6bps"]
        ].to_dict(orient="records")

    if not monthly_df.empty:
        monthly_score = (
            monthly_df.groupby("scenario", as_index=False)
            .agg(months=("exit_month", "count"), pos_months=("net_6bps_pct", lambda s: int((s > 0).sum())))
        )
        monthly_score["positive_month_share"] = monthly_score["pos_months"] / \
            monthly_score["months"]
        q["q8_monthly_stability"] = monthly_score.sort_values(
            "positive_month_share", ascending=False).to_dict(orient="records")

    q["q9_testnet_prep_worthy"] = verdict == "ACCEPTED_FOR_TESTNET_PREP"

    # FACT / INFERENCE / ASSUMPTION / UNKNOWN
    facts: List[str] = []
    inferences: List[str] = []
    assumptions: List[str] = []
    unknowns: List[str] = []

    facts.append(
        "Stateful replay enforces one open ETHUSDT short at a time; overlapping entries are impossible.")
    facts.append(
        "Entry is next bar open after BD1 signal bar; while open, new signals are counted as skipped.")
    facts.append(
        "Exit precedence is conservative: SL > TP > REGIME_CHANGE > TIMEOUT.")
    facts.append("Same-bar TP/SL conflicts are counted for diagnostics.")

    if not s0.empty:
        b = s0.iloc[0]
        facts.append(
            "S0 summary: "
            f"raw_signals={int(b['raw_signal_count'])}, skipped={int(b['skipped_signals_open_position'])}, "
            f"trades={int(b['actual_trade_count'])}, net6={float(b['net_pnl_pct_6bps']):.4f}%, net10={float(b['net_pnl_pct_10bps']):.4f}%."
        )

    if verdict == "ACCEPTED_FOR_TESTNET_PREP":
        inferences.append(
            "Candidate remains positive after stateful de-overlap checks and survives higher costs in core scenarios.")
    elif verdict == "CANDIDATE_SURVIVES_BUT_WEAK":
        inferences.append(
            "Candidate survives at 6 bps but stability/cost-robustness is not strong enough for direct testnet prep.")
    elif verdict == "REJECTED_OVERLAP_ARTIFACT":
        inferences.append(
            "Original edge was largely an overlap artifact and does not survive stateful replay.")
    else:
        inferences.append(
            "Evidence is mixed or insufficient to issue a hard acceptance/rejection.")

    assumptions.append(
        "BD1 definition is exact from prior anatomy forensic: TREND_DOWN and signed_body_bps>0 and close_position_in_bar>=0.50.")
    assumptions.append(
        "Regime-change exit uses current bar regime value at evaluation bar close.")
    assumptions.append(
        "Monthly and rolling 7-day stability are computed on trade exit timestamp buckets.")

    if trades_df.empty:
        unknowns.append(
            "No trades generated under current conditions; candidate may be too sparse or data mismatch exists.")

    # Save trades CSV.
    if not trades_df.empty:
        trades_df = trades_df.sort_values(
            ["scenario", "entry_timestamp"]).reset_index(drop=True)
    trades_df.to_csv(OUT_TRADES, index=False)

    # Build report payload.
    payload: Dict[str, Any] = {
        "report_id": "AURORA_TREND_DOWN_BD1_ETH_STATEFUL_RECHECK_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "candidate": "BD1_ETH_SHORT_AFTER_GREEN_PULLBACK_IN_TREND_DOWN",
        "candidate_definition": {
            "regime": REGIME,
            "is_green": "close > open",
            "pullback": "close_position_in_bar >= 0.50",
            "entry": "next bar open",
        },
        "hard_rules_enforced": {
            "historical_replay_only": True,
            "no_overlapping_positions": True,
            "one_open_position_per_symbol": True,
            "entry_next_bar_open": True,
            "exit_tp_sl_timeout_rc": True,
            "costs_4_6_8_10_reported": True,
        },
        "scenarios": summary_df.to_dict(orient="records"),
        "monthly_performance": monthly_df.to_dict(orient="records"),
        "rolling_7d_performance": rolling7_df.to_dict(orient="records"),
        "critical_questions": q,
        "verdict": verdict,
        "facts": facts,
        "inferences": inferences,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "acceptance_gate": {
            "stateful_replay": True,
            "overlapping_entries_impossible": True,
            "skipped_signals_counted": True,
            "costs_4_6_8_10_reported": True,
            "rc_on_off_compared": True,
            "rolling_and_monthly_stability_reported": True,
            "explicit_verdict": verdict,
        },
    }

    OUT_JSON.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown report.
    md: List[str] = []
    md.append("# AURORA_TREND_DOWN_BD1_ETH_STATEFUL_RECHECK_V1")
    md.append("")
    md.append("## Verdict")
    md.append("")
    md.append(verdict)
    md.append("")

    md.append("## FACT")
    md.append("")
    for x in facts:
        md.append(f"- {x}")
    md.append("")

    md.append("## INFERENCE")
    md.append("")
    for x in inferences:
        md.append(f"- {x}")
    md.append("")

    md.append("## ASSUMPTION")
    md.append("")
    for x in assumptions:
        md.append(f"- {x}")
    md.append("")

    md.append("## UNKNOWN")
    md.append("")
    if unknowns:
        for x in unknowns:
            md.append(f"- {x}")
    else:
        md.append(
            "- No material unknowns beyond finite-sample and regime non-stationarity risk.")
    md.append("")

    md.append("## Scenario comparison")
    md.append("")
    md.append(
        _rows_to_md(
            summary_df.sort_values(
                "net_pnl_pct_6bps", ascending=False).to_dict(orient="records"),
            [
                "scenario",
                "raw_signal_count",
                "skipped_signals_open_position",
                "actual_trade_count",
                "tp_count",
                "sl_count",
                "timeout_count",
                "regime_change_exit_count",
                "win_rate_pct",
                "gross_pnl_pct",
                "net_pnl_pct_4bps",
                "net_pnl_pct_6bps",
                "net_pnl_pct_8bps",
                "net_pnl_pct_10bps",
                "avg_pnl_pct_per_trade",
                "avg_R",
                "total_R",
                "max_drawdown_pct",
                "average_bars_held",
                "median_bars_held",
                "same_bar_tp_sl_conflict_count",
            ],
            max_rows=30,
        )
    )
    md.append("")

    md.append("## Monthly performance")
    md.append("")
    md.append(
        _rows_to_md(
            monthly_df.sort_values(
                ["scenario", "exit_month"]).to_dict(orient="records"),
            [
                "scenario",
                "exit_month",
                "trades",
                "gross_pnl_pct",
                "net_4bps_pct",
                "net_6bps_pct",
                "net_8bps_pct",
                "net_10bps_pct",
                "win_rate_pct",
            ],
            max_rows=120,
        )
    )
    md.append("")

    md.append("## Rolling 7-day performance")
    md.append("")
    if not rolling7_df.empty:
        roll_view = (
            rolling7_df.sort_values("rolling_7d_net_6bps_pct", ascending=False)
            .groupby("scenario", as_index=False)
            .head(2)
            .to_dict(orient="records")
        )
    else:
        roll_view = []
    md.append(
        _rows_to_md(
            roll_view,
            [
                "scenario",
                "exit_day",
                "trades",
                "daily_net_6bps_pct",
                "rolling_7d_net_6bps_pct",
                "rolling_7d_gross_pct",
            ],
            max_rows=40,
        )
    )
    md.append("")

    md.append("## Critical questions")
    md.append("")
    for k in [
        "q1_remains_positive_after_no_overlap",
        "q2_signals_to_actual_trades",
        "q3_overlap_inflation_likely",
        "q4_rc_help_or_hurt",
        "q5_timeout_36_remains_best",
        "q6_tp70_sl110_remains_best",
        "q7_survive_6bps",
        "q7_survive_10bps",
        "q8_monthly_stability",
        "q9_testnet_prep_worthy",
    ]:
        md.append(f"- {k}: {q.get(k)}")
    md.append("")

    md.append("## Acceptance gate")
    md.append("")
    for k, v in payload["acceptance_gate"].items():
        md.append(f"- {k}: {v}")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"Wrote {OUT_TRADES.name} ({len(trades_df):,} rows)")
    print(f"Wrote {OUT_JSON.name}")
    print(f"Wrote {OUT_MD.name}")
    print(f"Verdict: {verdict}")
    print(f"Elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    run()
