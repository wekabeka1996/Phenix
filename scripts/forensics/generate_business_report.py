#!/usr/bin/env python3
"""
Package D: Business Analysis Report Generator
Generates stratified PnL metrics, regime analysis, reject economics, and observability debt.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT_DIR / "reports"

def load_data():
    trades = pd.read_csv(REPORTS_DIR / "executed_trades_master.csv")
    rejections = pd.read_csv(REPORTS_DIR / "rejected_attempts_master.csv")
    counterfactuals = pd.read_csv(REPORTS_DIR / "rejected_counterfactuals.csv")
    all_attempts = pd.read_csv(REPORTS_DIR / "order_attempts_master.csv")
    return trades, rejections, counterfactuals, all_attempts

def extract_strategy(attempt_id: str) -> str:
    if pd.isna(attempt_id):
        return "unknown"
    aid = str(attempt_id)
    if aid.startswith("mdamr-"):
        return "md_amr"
    elif aid.startswith("aurora_"):
        return "aurora"
    elif aid.startswith("SYN_"):
        return "synthetic_unresolved"
    elif aid.startswith("unlinked"):
        return "unlinked"
    else:
        return "other"

def compute_drawdown(pnl_series: pd.Series) -> float:
    """Compute maximum drawdown from a PnL series."""
    if pnl_series.empty:
        return 0.0
    cumulative = pnl_series.cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    return drawdown.min()

def format_report_section(title: str, content: str) -> str:
    divider = "-" * 70
    return f"\n{divider}\n  {title}\n{divider}\n{content}\n"

def main():
    print("--> Loading data artifacts...")
    trades, rejections, counterfactuals, all_attempts = load_data()

    # ─── PREPARE TRADES ───────────────────────────────────────────────────
    trades['intent_ts'] = pd.to_datetime(trades['intent_ts'], utc=True, errors='coerce')
    trades['hour'] = trades['intent_ts'].dt.hour
    trades['strategy'] = trades['attempt_id'].apply(extract_strategy)
    trades['has_pnl'] = trades['realized_pnl'].fillna(0.0) != 0.0
    trades['net_pnl'] = trades['realized_pnl'].fillna(0.0) - trades['commission'].fillna(0.0)
    trades['is_win'] = trades['net_pnl'] > 0

    # ─── PREPARE REJECTIONS ───────────────────────────────────────────────
    rejections['intent_ts'] = pd.to_datetime(rejections['intent_ts'], utc=True, errors='coerce')
    rejections['hour'] = rejections['intent_ts'].dt.hour
    rejections['strategy'] = rejections['attempt_id'].apply(extract_strategy)

    # ─── COUNTERFACTUAL PREP ──────────────────────────────────────────────
    cf = counterfactuals.copy()
    cf['intent_ts'] = pd.to_datetime(cf['intent_ts'], utc=True, errors='coerce')

    lines = []
    lines.append("# AURORA FORENSIC BUSINESS ANALYSIS REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Evidence basis: {len(all_attempts)} total attempts reconstructed from 2.2M+ events\n")

    # ─── SECTION 1: COVERAGE LEDGER ──────────────────────────────────────
    ledger = all_attempts.groupby(['outcome','confidence']).size().unstack(fill_value=0)
    sec1 = ledger.to_string()
    sec1 += f"\n\nTOTAL CANONICAL ATTEMPTS : {len(all_attempts)}"
    sec1 += f"\nEXECUTED (incl. partial) : {len(trades)}"
    sec1 += f"\nEXECT ROUNDTRIPS         : {trades['exact_roundtrip'].sum()}"
    sec1 += f"\nREJECTED (all stages)    : {len(rejections)}"
    sec1 += f"\nWEAK JOIN ROWS           : {(all_attempts['confidence']=='weak').sum()}"
    sec1 += f"\nUNLINKED ROWS            : {(all_attempts['confidence']=='unlinked').sum()}"
    lines.append(format_report_section("1. CANONICAL COVERAGE LEDGER", sec1))

    # ─── SECTION 2: EXECUTED TRADE ECONOMICS ─────────────────────────────
    roundtrips = trades[trades['exact_roundtrip'] == True]
    proxy_exits = trades[(trades['outcome'] == 'executed') & (trades['exact_roundtrip'] == False)]

    total_pnl = roundtrips['net_pnl'].sum()
    total_commission = roundtrips['commission'].sum()
    win_rate = roundtrips['is_win'].mean() * 100 if len(roundtrips) > 0 else 0.0
    max_dd = compute_drawdown(roundtrips['net_pnl'])

    sec2 = f"  Exact Roundtrips       : {len(roundtrips)}\n"
    sec2 += f"  Proxy Exit (no close)  : {len(proxy_exits)}\n\n"
    sec2 += f"  TOTAL NET PnL          : {total_pnl:+.4f} USDT (exact roundtrips only)\n"
    sec2 += f"  TOTAL COMMISSION PAID  : {total_commission:.4f} USDT\n"
    sec2 += f"  WIN RATE               : {win_rate:.1f}%\n"
    sec2 += f"  MAX DRAWDOWN           : {max_dd:+.4f} USDT\n"
    sec2 += f"  AVG WIN PnL            : {roundtrips[roundtrips['is_win']]['net_pnl'].mean():.4f}\n"
    sec2 += f"  AVG LOSS PnL           : {roundtrips[~roundtrips['is_win']]['net_pnl'].mean():.4f}\n"
    lines.append(format_report_section("2. EXECUTED TRADE ECONOMICS (Exact Roundtrips Only)", sec2))

    # ─── SECTION 3: PnL BY SYMBOL ────────────────────────────────────────
    sym_stats = roundtrips.groupby('symbol').agg(
        trades=('net_pnl', 'count'),
        net_pnl=('net_pnl', 'sum'),
        win_rate=('is_win', 'mean'),
        avg_pnl=('net_pnl', 'mean'),
        max_win=('net_pnl', 'max'),
        max_loss=('net_pnl', 'min')
    ).sort_values('net_pnl', ascending=True)
    sym_stats['win_rate'] = (sym_stats['win_rate'] * 100).round(1)
    sym_stats['net_pnl'] = sym_stats['net_pnl'].round(4)
    sym_stats['avg_pnl'] = sym_stats['avg_pnl'].round(4)
    lines.append(format_report_section("3. PnL BY SYMBOL (Worst to Best)", sym_stats.to_string()))

    # ─── SECTION 4: PnL BY REGIME ─────────────────────────────────────────
    regime_stats = roundtrips.groupby('regime').agg(
        trades=('net_pnl', 'count'),
        net_pnl=('net_pnl', 'sum'),
        win_rate=('is_win', 'mean'),
    ).sort_values('net_pnl', ascending=True)
    regime_stats['win_rate'] = (regime_stats['win_rate'] * 100).round(1)
    regime_stats['net_pnl'] = regime_stats['net_pnl'].round(4)

    # Counterfactual without TREND_UP
    no_trend = roundtrips[roundtrips['regime'] != 'TREND_UP']
    sec4 = regime_stats.to_string()
    sec4 += f"\n\n  --- Counterfactual: Remove TREND_UP trades ---"
    sec4 += f"\n  Net PnL (no TREND_UP)   : {no_trend['net_pnl'].sum():+.4f} USDT"
    sec4 += f"\n  Win Rate (no TREND_UP)  : {no_trend['is_win'].mean()*100:.1f}%"
    sec4 += f"\n  Trade Count (no TREND_UP): {len(no_trend)}"
    lines.append(format_report_section("4. PnL BY REGIME + TREND_UP Counterfactual", sec4))

    # ─── SECTION 5: PnL BY STRATEGY ───────────────────────────────────────
    strat_stats = roundtrips.groupby('strategy').agg(
        trades=('net_pnl', 'count'),
        net_pnl=('net_pnl', 'sum'),
        win_rate=('is_win', 'mean'),
        avg_pnl=('net_pnl', 'mean'),
    ).sort_values('net_pnl', ascending=True)
    strat_stats['win_rate'] = (strat_stats['win_rate'] * 100).round(1)
    strat_stats['net_pnl'] = strat_stats['net_pnl'].round(4)
    lines.append(format_report_section("5. PnL BY STRATEGY", strat_stats.to_string()))

    # ─── SECTION 6: PnL BY HOUR ───────────────────────────────────────────
    hour_stats = roundtrips.groupby('hour').agg(
        trades=('net_pnl', 'count'),
        net_pnl=('net_pnl', 'sum'),
        win_rate=('is_win', 'mean'),
    ).sort_values('net_pnl', ascending=True)
    hour_stats['win_rate'] = (hour_stats['win_rate'] * 100).round(1)
    hour_stats['net_pnl'] = hour_stats['net_pnl'].round(4)
    sec6 = hour_stats.to_string()
    sec6 += "\n\n  Best hours  (UTC): " + str(hour_stats.sort_values('net_pnl', ascending=False).head(3).index.tolist())
    sec6 += "\n  Worst hours (UTC): " + str(hour_stats.sort_values('net_pnl').head(3).index.tolist())
    lines.append(format_report_section("6. PnL BY HOUR OF DAY (UTC)", sec6))

    # ─── SECTION 7: SIDE BREAKDOWN ─────────────────────────────────────────
    side_stats = roundtrips.groupby('side').agg(
        trades=('net_pnl', 'count'),
        net_pnl=('net_pnl', 'sum'),
        win_rate=('is_win', 'mean'),
    ).sort_values('net_pnl')
    side_stats['win_rate'] = (side_stats['win_rate'] * 100).round(1)
    lines.append(format_report_section("7. PnL BY DIRECTION (BUY/SELL)", side_stats.to_string()))

    # ─── SECTION 8: LOW_VOLATILITY REGIME SYMBOL ACCESS ──────────────────
    lv_all = all_attempts[all_attempts['regime'] == 'LOW_VOLATILITY']
    lv_exec = trades[trades['regime'] == 'LOW_VOLATILITY']
    sec8 = f"  Symbols that ATTEMPTED in LOW_VOLATILITY:\n{lv_all['symbol'].value_counts().to_string()}"
    sec8 += f"\n\n  Symbols that EXECUTED in LOW_VOLATILITY:\n{lv_exec['symbol'].value_counts().to_string() if len(lv_exec) > 0 else '  (none)'}"
    if len(lv_exec) > 0:
        sec8 += f"\n\n  LOW_VOLATILITY Executed Net PnL: {lv_exec['net_pnl'].sum():+.4f}"
        sec8 += f"\n  LOW_VOLATILITY Win Rate        : {lv_exec['is_win'].mean()*100:.1f}%"
    lines.append(format_report_section("8. LOW_VOLATILITY REGIME — SYMBOL ACCESS AUDIT", sec8))

    # ─── SECTION 9: REJECT ECONOMICS (COUNTERFACTUAL) ────────────────────
    cf_classified = cf[~cf['excursion_classification'].str.startswith('missing', na=True)]
    cf_summary = cf_classified.groupby('excursion_classification').agg(
        count=('mfe_pct', 'count'),
        avg_mfe=('mfe_pct', 'mean'),
        avg_mae=('mae_pct', 'mean'),
    ).round(3)

    sec9 = f"  Classified rejects: {len(cf_classified)} / {len(cf)} total\n"
    sec9 += f"  Missing OHLCV data : {cf['excursion_classification'].str.startswith('missing', na=True).sum()} rows\n\n"
    sec9 += cf_summary.to_string()
    sec9 += "\n\n  Per reject-reason economics (classified only):\n"
    reason_grp = cf_classified.groupby(['reject_reason_short', 'excursion_classification']).size().unstack(fill_value=0) \
        if 'reject_reason_short' in cf_classified.columns \
        else cf_classified.groupby(['outcome', 'excursion_classification']).size().unstack(fill_value=0)
    sec9 += reason_grp.to_string()
    lines.append(format_report_section("9. REJECT ECONOMICS (45-min OHLCV Counterfactual)", sec9))

    # ─── SECTION 10: OBSERVABILITY DEBT ──────────────────────────────────
    total_att = len(all_attempts)
    unlinked = (all_attempts['confidence'] == 'unlinked').sum()
    timeout = (all_attempts['outcome'] == 'timeout_non_fill').sum()
    unknown_sym = (all_attempts['symbol'] == 'UNKNOWN').sum()
    no_regime = (all_attempts['regime'].isna() | (all_attempts['regime'] == '')).sum()

    sec10 = f"  CRITICAL OBSERVABILITY GAPS:\n"
    sec10 += f"  Unlinked attempts (no join found)  : {unlinked} / {total_att} = {unlinked/total_att*100:.1f}%\n"
    sec10 += f"  timeout_non_fill (no resolution)   : {timeout} / {total_att} = {timeout/total_att*100:.1f}%\n"
    sec10 += f"  UNKNOWN symbol (regex failed)      : {unknown_sym} / {total_att} = {unknown_sym/total_att*100:.1f}%\n"
    sec10 += f"  Missing regime tag                 : {no_regime} / {total_att} = {no_regime/total_att*100:.1f}%\n"
    sec10 += f"\n  ROOT CAUSES:\n"
    sec10 += f"  - Most 'timeout_non_fill' rows are DECISION_INTENT_REJECTED from trade_lifecycle.jsonl\n"
    sec10 += f"    that are NEVER explicitly resolved in order_log_v1.jsonl (no cross-reference by ts+sym).\n"
    sec10 += f"  - 'UNKNOWN' symbol rows originate from text-log rejections embedded in aurora_core.log\n"
    sec10 += f"    where symbol context was propagated via [SYMBOL] bracket prefix but omitted in some lines.\n"
    sec10 += f"  - 'Missing regime' is structural: only ORDER_LOG v1 JSON has regime metadata populated.\n"
    sec10 += f"    text-log intent lines do not carry regime directly.\n"
    sec10 += f"\n  RECOMMENDATIONS:\n"
    sec10 += f"  1. Add 'symbol' field to all gateway-reject audit lines in DecisionMaking domain.\n"
    sec10 += f"  2. Propagate 'regime' and 'strategy_id' to ORDER_PLACED events in execution domain.\n"
    sec10 += f"  3. Emit a unique 'lifecycle_id' on TRADE_INTENT_PROPOSED that is forwarded to\n"
    sec10 += f"     DECISION_INTENT_REJECTED, order_log, and fill events for zero-loss tracing.\n"
    lines.append(format_report_section("10. OBSERVABILITY DEBT & ROOT CAUSE ANALYSIS", sec10))

    # ─── WRITE REPORT ────────────────────────────────────────────────────
    report_text = "\n".join(lines)
    out_path = REPORTS_DIR / "ORDER_FLOW_FINAL.md"
    out_path.write_text(report_text, encoding="utf-8")
    print(f"--> Final report written to: {out_path}")
    # Print summary stats only (ASCII-safe)
    print(f"\nTOTAL ATTEMPTS: {len(all_attempts)}")
    print(f"EXECUTED (exact roundtrips): {len(roundtrips)}")
    print(f"REJECTED: {len(rejections)}")
    print(f"NET PnL: {total_pnl:+.4f} USDT")
    print(f"WIN RATE: {win_rate:.1f}%")
    print(f"MAX DRAWDOWN: {max_dd:+.4f} USDT")

if __name__ == "__main__":
    main()
