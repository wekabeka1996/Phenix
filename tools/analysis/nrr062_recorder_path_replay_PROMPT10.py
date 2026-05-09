#!/usr/bin/env python3
"""
NRR-062 Frozen Recorder-Path Replay - PROMPT 10 CORRECTION
Resolves Prompt-9 geometry-only audit with true market-path replay
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import statistics
import csv

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

FROZEN_BASE = Path("logs/frozen/nrr062_fresh_capture_20260507_103909")
DATASET_PATH = FROZEN_BASE / "nrr062_cases.jsonl"
RECORDER_BASE = FROZEN_BASE / "data" / "recorder"

OUTPUT_DIR = FROZEN_BASE
REPLAY_RESULTS_PATH = OUTPUT_DIR / "nrr062_recorder_path_replay_PROMPT10.jsonl"
REPLAY_SUMMARY_PATH = OUTPUT_DIR / \
    "nrr062_recorder_path_replay_summary_PROMPT10.json"
VARIANT_SWEEP_PATH = OUTPUT_DIR / "nrr062_corrected_variant_sweep_PROMPT10.json"

# ============================================================================
# LOAD AND PARSE
# ============================================================================


def load_frozen_cases() -> List[Dict[str, Any]]:
    """Load frozen NRR-062 cases."""
    cases = []
    with open(DATASET_PATH, 'r') as f:
        for line in f:
            try:
                row = json.loads(line)
                nrr_case = row.get('nrr062_case', row)
                cases.append(nrr_case)
            except Exception as e:
                logger.warning(f"Skipped malformed row: {e}")
    logger.info(f"Loaded {len(cases)} cases")
    return cases


def get_safe_float(val, default=None):
    """Safely convert to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def find_recorder_file(symbol: str, ts_ms: int) -> Optional[Path]:
    """Find best frozen recorder CSV for symbol and timestamp."""
    from datetime import datetime, timedelta

    ts_dt = datetime.utcfromtimestamp(ts_ms / 1000)
    date_str = ts_dt.strftime('%Y-%m-%d')

    # Check exact date
    for tf in ['180s', '300s', '900s']:
        candidate = RECORDER_BASE / date_str / f"{symbol}_{tf}.csv"
        if candidate.exists():
            return candidate

    # Check adjacent dates
    for offset in [-1, 1]:
        adj_date = (ts_dt + timedelta(days=offset)).strftime('%Y-%m-%d')
        for tf in ['180s', '300s', '900s']:
            candidate = RECORDER_BASE / adj_date / f"{symbol}_{tf}.csv"
            if candidate.exists():
                return candidate

    return None


def load_recorder_bars(csv_path: Path, start_ts_ms: int) -> List[Dict[str, Any]]:
    """Load all bars from CSV after start_ts_ms."""
    bars = []
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    bar_ts_ms = int(row.get('ts_ms', 0))
                    if bar_ts_ms > start_ts_ms:
                        bars.append({
                            'ts_ms': bar_ts_ms,
                            'open': float(row.get('open', 0)),
                            'high': float(row.get('high', 0)),
                            'low': float(row.get('low', 0)),
                            'close': float(row.get('close', 0)),
                            'volume': float(row.get('volume', 0)),
                        })
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        logger.warning(f"Failed to read {csv_path}: {e}")
    return bars

# ============================================================================
# REPLAY
# ============================================================================


def replay_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    True market-path replay for a single case.
    Uses frozen recorder bars to determine actual outcome.
    """

    result = {
        'rid': case.get('rid'),
        'symbol': case.get('symbol'),
        'side': case.get('side'),
        'ts_ms': case.get('ts_ms'),
        'ts_iso': case.get('ts_iso'),
    }

    lvf = case.get('low_vol_cost_floor', {})
    geometry = lvf.get('geometry', {})
    econ = lvf.get('economics', {})

    # Geometry
    entry = get_safe_float(geometry.get('entry_price'))
    tp = get_safe_float(geometry.get('target_price'))
    sl = get_safe_float(geometry.get('stop_price'))
    actual_tp_bps = get_safe_float(geometry.get('actual_tp_bps'))
    actual_sl_bps = get_safe_float(geometry.get('actual_sl_bps'))
    rr = get_safe_float(geometry.get('rr'), 1.0)

    # Economics
    fee_bps = get_safe_float(econ.get('round_trip_fee_bps'), 8.0)
    slippage_bps = get_safe_float(econ.get('slippage_bps'), 2.0)
    total_cost_bps = fee_bps + slippage_bps

    # Context
    score_ctx = lvf.get('score_context', {})
    dc = lvf.get('direction_confidence', {})
    pm = lvf.get('price_motion', {})
    liq = lvf.get('liquidity', {})

    result.update({
        'entry_price': entry,
        'target_price': tp,
        'stop_price': sl,
        'actual_tp_bps': actual_tp_bps,
        'actual_sl_bps': actual_sl_bps,
        'rr': rr,
        'round_trip_fee_bps': fee_bps,
        'slippage_bps': slippage_bps,
        'total_cost_bps': total_cost_bps,
        'regime': lvf.get('regime', {}).get('regime'),
        'regime_confidence': get_safe_float(lvf.get('regime', {}).get('regime_confidence')),
        'direction_confidence': get_safe_float(dc.get('value')),
        'direction_confidence_source': dc.get('source'),
        'direction_confidence_passed': dc.get('passed'),
        'pm_norm_60s': get_safe_float(pm.get('pm_norm_60s')),
        'pm_norm_300s': get_safe_float(pm.get('pm_norm_300s')),
        'spread_bps': get_safe_float(liq.get('spread_bps')),
    })

    # Validate geometry
    if not (entry and tp and sl and entry > 0 and tp > 0 and sl > 0):
        result['path_outcome'] = 'INSUFFICIENT_FORWARD_DATA'
        result['classification'] = 'ambiguous'
        return result

    # Find recorder file
    recorder_file = find_recorder_file(result['symbol'], result['ts_ms'])
    if not recorder_file:
        result['path_outcome'] = 'INSUFFICIENT_FORWARD_DATA'
        result['classification'] = 'ambiguous'
        return result

    # Load bars
    bars = load_recorder_bars(recorder_file, result['ts_ms'])
    if not bars:
        result['path_outcome'] = 'INSUFFICIENT_FORWARD_DATA'
        result['classification'] = 'ambiguous'
        return result

    # Replay across 4 horizons
    horizons = [15*60*1000, 30*60*1000, 60*60*1000, 120*60*1000]  # ms
    closes = {}

    side = result['side']
    path_outcome = None
    net_bps_at_outcome = None
    mfe_bps = None
    mae_bps = None

    # Check first bar for TP/SL
    first_bar = bars[0]
    high_after = first_bar['high']
    low_after = first_bar['low']

    if side == "BUY":
        mfe = (high_after - entry) / entry * 10000
        mae = (entry - low_after) / entry * 10000

        tp_hit = high_after >= tp
        sl_hit = low_after <= sl

        if tp_hit and sl_hit:
            # Same bar ambiguity
            path_outcome = 'AMBIGUOUS_SAME_BAR'
            net_if_tp = actual_tp_bps - total_cost_bps
            net_if_sl = -(actual_sl_bps + total_cost_bps)
            net_bps_at_outcome = max(net_if_tp, net_if_sl)
        elif tp_hit:
            path_outcome = 'TP_FIRST'
            net_bps_at_outcome = actual_tp_bps - total_cost_bps
        elif sl_hit:
            path_outcome = 'SL_FIRST'
            net_bps_at_outcome = -(actual_sl_bps + total_cost_bps)
        else:
            # Check horizons
            for i, horizon_ms in enumerate(horizons):
                close_bars = [b for b in bars if b['ts_ms']
                              <= result['ts_ms'] + horizon_ms]
                if close_bars:
                    close = close_bars[-1]['close']
                    closes[horizon_ms] = close

            # Use 120m close
            if closes.get(horizons[-1]):
                close_120m = closes[horizons[-1]]
                net_120m = (close_120m - entry) / \
                    entry * 10000 - total_cost_bps
                path_outcome = 'HORIZON_CLOSE_120M'
                net_bps_at_outcome = net_120m
            else:
                path_outcome = 'INSUFFICIENT_FORWARD_DATA'

        mfe_bps = mfe
        mae_bps = mae

    else:  # SELL
        mfe = (entry - low_after) / entry * 10000
        mae = (high_after - entry) / entry * 10000

        tp_hit = low_after <= tp
        sl_hit = high_after >= sl

        if tp_hit and sl_hit:
            path_outcome = 'AMBIGUOUS_SAME_BAR'
            net_if_tp = actual_tp_bps - total_cost_bps
            net_if_sl = -(actual_sl_bps + total_cost_bps)
            net_bps_at_outcome = max(net_if_tp, net_if_sl)
        elif tp_hit:
            path_outcome = 'TP_FIRST'
            net_bps_at_outcome = actual_tp_bps - total_cost_bps
        elif sl_hit:
            path_outcome = 'SL_FIRST'
            net_bps_at_outcome = -(actual_sl_bps + total_cost_bps)
        else:
            for i, horizon_ms in enumerate(horizons):
                close_bars = [b for b in bars if b['ts_ms']
                              <= result['ts_ms'] + horizon_ms]
                if close_bars:
                    close = close_bars[-1]['close']
                    closes[horizon_ms] = close

            if closes.get(horizons[-1]):
                close_120m = closes[horizons[-1]]
                net_120m = (entry - close_120m) / \
                    entry * 10000 - total_cost_bps
                path_outcome = 'HORIZON_CLOSE_120M'
                net_bps_at_outcome = net_120m
            else:
                path_outcome = 'INSUFFICIENT_FORWARD_DATA'

        mfe_bps = mfe
        mae_bps = mae

    # Classify
    if path_outcome == 'TP_FIRST':
        classification = 'missed_positive'
    elif path_outcome == 'SL_FIRST':
        classification = 'correct_block'
    elif path_outcome == 'HORIZON_CLOSE_120M':
        if net_bps_at_outcome and net_bps_at_outcome > 0:
            classification = 'missed_positive'
        elif net_bps_at_outcome is not None:
            classification = 'correct_block'
        else:
            classification = 'ambiguous'
    else:
        classification = 'ambiguous'

    result.update({
        'path_outcome': path_outcome,
        'net_bps': net_bps_at_outcome,
        'mfe_bps': mfe_bps,
        'mae_bps': mae_bps,
        'classification': classification,
    })

    return result

# ============================================================================
# SUMMARY AND VARIANTS
# ============================================================================


def compute_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics from corrected replay."""

    missed = len([r for r in results if r.get(
        'classification') == 'missed_positive'])
    correct = len([r for r in results if r.get(
        'classification') == 'correct_block'])
    ambig = len([r for r in results if r.get('classification') == 'ambiguous'])

    tp_first = len([r for r in results if r.get('path_outcome') == 'TP_FIRST'])
    sl_first = len([r for r in results if r.get('path_outcome') == 'SL_FIRST'])
    horizon = len([r for r in results if r.get(
        'path_outcome') == 'HORIZON_CLOSE_120M'])
    same_bar = len([r for r in results if r.get(
        'path_outcome') == 'AMBIGUOUS_SAME_BAR'])
    insuff = len([r for r in results if r.get(
        'path_outcome') == 'INSUFFICIENT_FORWARD_DATA'])

    net_vals = [r.get('net_bps')
                for r in results if r.get('net_bps') is not None]

    # By symbol
    by_symbol = defaultdict(
        lambda: {'total': 0, 'missed': 0, 'correct': 0, 'ambig': 0, 'net_sum': 0})
    for r in results:
        by_symbol[r.get('symbol', 'UNKNOWN')]['total'] += 1
        if r.get('classification') == 'missed_positive':
            by_symbol[r.get('symbol', 'UNKNOWN')]['missed'] += 1
        elif r.get('classification') == 'correct_block':
            by_symbol[r.get('symbol', 'UNKNOWN')]['correct'] += 1
        else:
            by_symbol[r.get('symbol', 'UNKNOWN')]['ambig'] += 1
        if r.get('net_bps') is not None:
            by_symbol[r.get('symbol', 'UNKNOWN')
                      ]['net_sum'] += r.get('net_bps')

    # By side
    by_side = defaultdict(
        lambda: {'total': 0, 'missed': 0, 'correct': 0, 'ambig': 0, 'net_sum': 0})
    for r in results:
        by_side[r.get('side', 'UNKNOWN')]['total'] += 1
        if r.get('classification') == 'missed_positive':
            by_side[r.get('side', 'UNKNOWN')]['missed'] += 1
        elif r.get('classification') == 'correct_block':
            by_side[r.get('side', 'UNKNOWN')]['correct'] += 1
        else:
            by_side[r.get('side', 'UNKNOWN')]['ambig'] += 1
        if r.get('net_bps') is not None:
            by_side[r.get('side', 'UNKNOWN')]['net_sum'] += r.get('net_bps')

    return {
        'total_cases': len(results),
        'replayable_cases': len(results),
        'missed_positive': missed,
        'correct_blocks': correct,
        'ambiguous': ambig,
        'tp_first': tp_first,
        'sl_first': sl_first,
        'horizon_close_120m': horizon,
        'same_bar_ambiguous': same_bar,
        'insufficient_forward_data': insuff,
        'median_net_bps': statistics.median(net_vals) if net_vals else None,
        'mean_net_bps': statistics.mean(net_vals) if net_vals else None,
        'total_net_bps': sum(net_vals) if net_vals else None,
        'worst_case_bps': min(net_vals) if net_vals else None,
        'best_case_bps': max(net_vals) if net_vals else None,
        'p25_bps': sorted(net_vals)[len(net_vals)//4] if net_vals else None,
        'p75_bps': sorted(net_vals)[3*len(net_vals)//4] if net_vals else None,
        'by_symbol': dict(by_symbol),
        'by_side': dict(by_side),
    }


def sweep_variants(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Variant sweep using corrected labels."""

    variants = {}

    # Variant A: Baseline (all deny)
    variants['A_baseline'] = {
        'name': 'All deny (current)',
        'candidates_allowed': 0,
        'winners_recovered': 0,
        'losers_admitted': 0,
        'ambiguous_admitted': 0,
        'net_bps_sum': 0,
        'verdict': 'current_baseline',
    }

    # Variant B: Symbol-specific allows
    total_missed = len([r for r in results if r.get(
        'classification') == 'missed_positive'])
    total_correct = len([r for r in results if r.get(
        'classification') == 'correct_block'])

    for symbol in ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'BNBUSDT']:
        by_sym = [r for r in results if r.get('symbol') == symbol]
        if by_sym:
            missed_in_sym = len([r for r in by_sym if r.get(
                'classification') == 'missed_positive'])
            correct_in_sym = len([r for r in by_sym if r.get(
                'classification') == 'correct_block'])
            ambig_in_sym = len(
                [r for r in by_sym if r.get('classification') == 'ambiguous'])
            net_sum = sum([r.get('net_bps', 0)
                          for r in by_sym if r.get('net_bps') is not None])

            leak_rate = correct_in_sym / total_correct if total_correct > 0 else 0

            variants[f'B_{symbol}'] = {
                'name': f'Allow {symbol}',
                'candidates_allowed': len(by_sym),
                'winners_recovered': missed_in_sym,
                'losers_admitted': correct_in_sym,
                'ambiguous_admitted': ambig_in_sym,
                'net_bps_sum': net_sum,
                'loser_leak_rate': leak_rate,
                'verdict': 'promising_shadow' if missed_in_sym >= 5 and leak_rate <= 0.2 else 'risky' if correct_in_sym > missed_in_sym else 'needs_data',
            }

    return variants

# ============================================================================
# MAIN
# ============================================================================


def main():
    logger.info("="*80)
    logger.info("NRR-062 FROZEN RECORDER-PATH REPLAY - PROMPT 10 CORRECTION")
    logger.info("="*80)

    # Load
    cases = load_frozen_cases()
    logger.info(f"Loaded {len(cases)} cases")

    # Replay
    logger.info("\nRunning true recorder-path replay...")
    results = []
    for i, case in enumerate(cases):
        if (i + 1) % 20 == 0:
            logger.info(f"  Replayed {i+1}/{len(cases)}...")
        result = replay_case(case)
        results.append(result)

    # Summary
    logger.info("\nComputing summary...")
    summary = compute_summary(results)

    logger.info(f"  Missed positive: {summary['missed_positive']}")
    logger.info(f"  Correct blocks: {summary['correct_blocks']}")
    logger.info(f"  Ambiguous: {summary['ambiguous']}")
    logger.info(f"  TP first: {summary['tp_first']}")
    logger.info(f"  SL first: {summary['sl_first']}")
    logger.info(f"  Horizon close: {summary['horizon_close_120m']}")
    logger.info(f"  Median net bps: {summary['median_net_bps']}")

    # Variants
    logger.info("\nRunning variant sweep...")
    variants = sweep_variants(results)

    # Outputs
    logger.info("\nWriting outputs...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(REPLAY_RESULTS_PATH, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    logger.info(f"  Wrote {REPLAY_RESULTS_PATH}")

    with open(REPLAY_SUMMARY_PATH, 'w') as f:
        json.dump(summary, f, indent=2)
    logger.info(f"  Wrote {REPLAY_SUMMARY_PATH}")

    with open(VARIANT_SWEEP_PATH, 'w') as f:
        json.dump(variants, f, indent=2)
    logger.info(f"  Wrote {VARIANT_SWEEP_PATH}")

    logger.info("\n" + "="*80)
    logger.info("REPLAY COMPLETE")
    logger.info("="*80)

    return results, summary, variants


if __name__ == '__main__':
    results, summary, variants = main()
