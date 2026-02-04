#!/usr/bin/env python3
"""
Backtest Diagnostics Generator

Generates post-processing diagnostics for backtest run bundles.
Outputs: diagnostics_metrics.json with equity curve, regime switches, and order log metrics.

Usage:
    python tools/backtest_diagnostics.py --run-dir reports/backtests/<run_id>
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def load_json(path: str) -> Optional[Dict]:
    """Load JSON file, return None if not found."""
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def load_jsonl(path: str) -> List[Dict]:
    """Load JSONL file, return empty list if not found."""
    if not os.path.exists(path):
        return []
    lines = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return lines


def compute_equity_metrics(result: Dict) -> Dict[str, Any]:
    """
    Compute equity curve metrics from trades.
    
    Returns:
        Dict with peak, giveback, end equity, etc.
    """
    # Get initial balance
    initial_balance = 1000.0
    if 'config' in result:
        ib = result['config'].get('initial_balance')
        if ib is not None:
            initial_balance = float(ib)
    
    # Get trades
    trades = result.get('closed_trades', result.get('trades', []))
    
    if not trades:
        return {
            'initial_balance': initial_balance,
            'equity_peak': initial_balance,
            't_peak_ms': None,
            'equity_end': initial_balance,
            'min_after_peak': initial_balance,
            'giveback_pct': 0.0,
            'trade_count': 0,
        }
    
    # Get exit timestamps
    def get_exit_ts(t):
        if 'exit' in t and 'ts_ms' in t['exit']:
            return t['exit']['ts_ms']
        return t.get('exit_ts_ms', t.get('timestamp', 0))
    
    valid_trades = [t for t in trades if get_exit_ts(t) > 0]
    sorted_trades = sorted(valid_trades, key=get_exit_ts)
    
    # Build equity curve
    equity = initial_balance
    peak = initial_balance
    t_peak = 0
    
    equity_series = []
    for t in sorted_trades:
        pnl = t.get('pnl_usdt_net', t.get('pnl_net', 0.0))
        ts = get_exit_ts(t)
        equity += float(pnl)
        equity_series.append((ts, equity))
        
        if equity > peak:
            peak = equity
            t_peak = ts
    
    # Find min after peak
    min_after_peak = peak
    for ts, eq in equity_series:
        if ts > t_peak:
            min_after_peak = min(min_after_peak, eq)
    
    giveback_pct = 0.0
    if peak > 0:
        giveback_pct = ((min_after_peak - peak) / peak) * 100
    
    equity_end = equity_series[-1][1] if equity_series else initial_balance
    
    return {
        'initial_balance': initial_balance,
        'equity_peak': peak,
        't_peak_ms': int(t_peak) if t_peak else None,
        't_peak_iso': datetime.utcfromtimestamp(t_peak / 1000).isoformat() if t_peak else None,
        'equity_end': equity_end,
        'min_after_peak': min_after_peak,
        'giveback_pct': round(giveback_pct, 2),
        'trade_count': len(sorted_trades),
    }


def compute_regime_metrics(result: Dict, t_peak_ms: Optional[int]) -> Dict[str, Any]:
    """
    Compute regime switch metrics from intents.
    
    Returns:
        Dict with stable_switches, raw_switches, storm_rejected_count, regime_counts
    """
    intents = result.get('intents', [])
    
    stable_switches = 0
    raw_switches = 0
    storm_rejected_count = 0
    regime_counts: Dict[str, int] = {}
    
    prev_stable = None
    prev_raw = None
    
    for intent in intents:
        stable = intent.get('market_regime')
        raw = intent.get('raw_regime')  # May not exist
        storm_rejected = intent.get('storm_rejected', False)
        
        # Count regime distribution
        if stable:
            regime_counts[stable] = regime_counts.get(stable, 0) + 1
        
        # Count switches
        if prev_stable is not None and stable != prev_stable:
            stable_switches += 1
        prev_stable = stable
        
        if raw is not None:
            if prev_raw is not None and raw != prev_raw:
                raw_switches += 1
            prev_raw = raw
        
        # Count storm_rejected
        if storm_rejected:
            storm_rejected_count += 1
    
    # Top regime
    top_regime = max(regime_counts, key=regime_counts.get) if regime_counts else None
    
    return {
        'stable_switches': stable_switches,
        'raw_switches': raw_switches,
        'storm_rejected_count': storm_rejected_count,
        'regime_counts': regime_counts,
        'top_regime': top_regime,
        'intent_count': len(intents),
    }


def compute_cancel_stale_regime(
    order_log_path: Optional[str],
    t_peak_ms: Optional[int]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Count CANCEL_STALE_REGIME events from order log.
    
    Returns:
        Tuple of (metrics dict, missing_artifacts list)
    """
    missing = []
    
    if not order_log_path or not os.path.exists(order_log_path):
        missing.append('order_log_jsonl')
        return {
            'cancel_stale_regime_count': None,
            'cancel_stale_regime_pre_peak': None,
            'cancel_stale_regime_post_peak': None,
        }, missing
    
    events = load_jsonl(order_log_path)
    
    total = 0
    pre_peak = 0
    post_peak = 0
    
    for event in events:
        reason = event.get('reason', event.get('close_reason', ''))
        if reason == 'CANCEL_STALE_REGIME':
            total += 1
            ts = event.get('ts_ms', event.get('timestamp', 0))
            if t_peak_ms and ts:
                if ts <= t_peak_ms:
                    pre_peak += 1
                else:
                    post_peak += 1
    
    return {
        'cancel_stale_regime_count': total,
        'cancel_stale_regime_pre_peak': pre_peak,
        'cancel_stale_regime_post_peak': post_peak,
    }, missing


def generate_backtest_diagnostics(run_dir: str) -> Dict[str, Any]:
    """
    Generate diagnostics metrics for a backtest run bundle.
    
    Args:
        run_dir: Path to backtest run directory (e.g., reports/backtests/<run_id>)
    
    Returns:
        Dict with all diagnostics metrics
    """
    result_path = os.path.join(run_dir, 'result.json')
    config_path = os.path.join(run_dir, 'resolved_config.json')
    
    result = load_json(result_path)
    if result is None:
        raise FileNotFoundError(f"result.json not found at {result_path}")
    
    config = load_json(config_path) or {}
    
    # Override initial_balance from config if available
    if 'trading' in config and 'backtest' in config['trading']:
        ib = config['trading']['backtest'].get('initial_balance')
        if ib is not None and 'config' not in result:
            result['config'] = {'initial_balance': float(ib)}
    
    # 1. Equity metrics
    equity_metrics = compute_equity_metrics(result)
    t_peak_ms = equity_metrics.get('t_peak_ms')
    
    # 2. Regime metrics
    regime_metrics = compute_regime_metrics(result, t_peak_ms)
    
    # 3. Cancel stale regime
    order_log_path = None
    artifacts = result.get('artifacts', {})
    if isinstance(artifacts, dict):
        order_log_rel = artifacts.get('order_log_jsonl')
        if order_log_rel:
            order_log_path = os.path.join(run_dir, order_log_rel)
    
    # Also try standard location
    if not order_log_path or not os.path.exists(order_log_path):
        default_order_log = os.path.join(run_dir, 'order_log.jsonl')
        if os.path.exists(default_order_log):
            order_log_path = default_order_log
    
    cancel_metrics, missing_artifacts = compute_cancel_stale_regime(order_log_path, t_peak_ms)
    
    # Build diagnostics
    diagnostics = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'run_dir': run_dir,
        'equity': equity_metrics,
        'regime': regime_metrics,
        'order_log': cancel_metrics,
    }
    
    if missing_artifacts:
        diagnostics['missing_artifacts'] = missing_artifacts
    
    return diagnostics


def save_diagnostics(run_dir: str, diagnostics: Dict[str, Any]) -> str:
    """Save diagnostics to analysis directory."""
    analysis_dir = os.path.join(run_dir, 'analysis')
    os.makedirs(analysis_dir, exist_ok=True)
    
    output_path = os.path.join(analysis_dir, 'diagnostics_metrics.json')
    with open(output_path, 'w') as f:
        json.dump(diagnostics, f, indent=2)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate backtest diagnostics')
    parser.add_argument('--run-dir', required=True, help='Path to backtest run directory')
    args = parser.parse_args()
    
    try:
        diagnostics = generate_backtest_diagnostics(args.run_dir)
        output_path = save_diagnostics(args.run_dir, diagnostics)
        print(f"Diagnostics saved to: {output_path}")
        print(json.dumps(diagnostics, indent=2))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
