#!/usr/bin/env python3
"""NRR-062 Frozen Counterfactual Replay - PROMPT 9 (simplified, robust)"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
import statistics

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

FROZEN_BASE = Path("logs/frozen/nrr062_fresh_capture_20260507_103909")
DATASET_PATH = FROZEN_BASE / "nrr062_cases.jsonl"

OUTPUT_DIR = FROZEN_BASE
REPLAY_RESULTS_PATH = OUTPUT_DIR / "nrr062_replay_results_PROMPT9.jsonl"
REPLAY_SUMMARY_PATH = OUTPUT_DIR / "nrr062_replay_summary_PROMPT9.json"
VARIANT_SWEEP_PATH = OUTPUT_DIR / "nrr062_variant_sweep_PROMPT9.json"

# ============================================================================
# LOAD AND PARSE FROZEN COHORT
# ============================================================================


def load_frozen_cases() -> List[Dict[str, Any]]:
    """Load all frozen NRR-062 cases from JSONL."""
    logger.info("Loading frozen cohort...")
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

# ============================================================================
# REPLAY LOGIC
# ============================================================================


def get_safe_float(val, default=None):
    """Safely convert value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def classify_outcome(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a single case outcome based on frozen economics and geometry.
    Uses actual recorded TP/SL geometry to determine if gate correctly protected.
    """
    lvf = case.get('low_vol_cost_floor', {})
    geometry = lvf.get('geometry', {})
    econ = lvf.get('economics', {})
    score_ctx = lvf.get('score_context', {})
    dc = lvf.get('direction_confidence', {})
    pm = lvf.get('price_motion', {})
    liq = lvf.get('liquidity', {})

    entry = get_safe_float(geometry.get('entry_price'), 0)
    tp = get_safe_float(geometry.get('target_price'), 0)
    sl = get_safe_float(geometry.get('stop_price'), 0)
    actual_tp_bps = get_safe_float(geometry.get('actual_tp_bps'), 0)
    actual_sl_bps = get_safe_float(geometry.get('actual_sl_bps'), 0)
    rr = get_safe_float(geometry.get('rr'), 1.0)

    fee_bps = get_safe_float(econ.get('round_trip_fee_bps'), 8.0)
    slippage_bps = get_safe_float(econ.get('slippage_bps'), 2.0)
    total_cost_bps = fee_bps + slippage_bps

    # Net PnL if target or stop hit
    expected_net_if_tp = actual_tp_bps - total_cost_bps
    expected_net_if_sl = -(actual_sl_bps + total_cost_bps)

    side = case.get('side')
    symbol = case.get('symbol')

    # Determine if this was objectively a winner or loser
    # Winner: if TP would have been hit first and net > 0
    # Loser: if SL would have been hit first or net <= 0
    # (In a real scenario, you'd use recorded path data)

    # For now, use ex-post realized geometry
    is_objectively_winner = expected_net_if_tp > 0
    is_objectively_loser = expected_net_if_sl <= 0

    # Classification
    result = {
        'rid': case.get('rid'),
        'symbol': symbol,
        'side': side,
        'ts_ms': case.get('ts_ms'),
        'ts_iso': case.get('ts_iso'),
        'entry_price': entry,
        'target_price': tp,
        'stop_price': sl,
        'actual_tp_bps': actual_tp_bps,
        'actual_sl_bps': actual_sl_bps,
        'rr': rr,
        'round_trip_fee_bps': fee_bps,
        'slippage_bps': slippage_bps,
        'total_cost_bps': total_cost_bps,
        'expected_net_if_tp': expected_net_if_tp,
        'expected_net_if_sl': expected_net_if_sl,
        'is_objectively_winner': is_objectively_winner,
        'is_objectively_loser': is_objectively_loser,
        'net_bps': expected_net_if_tp if is_objectively_winner else expected_net_if_sl,

        # Context fields
        'regime': lvf.get('regime', {}).get('regime'),
        'regime_confidence': get_safe_float(lvf.get('regime', {}).get('regime_confidence')),
        'final_score': get_safe_float(score_ctx.get('final_score')),
        'signal_score': get_safe_float(score_ctx.get('signal_score')),
        'score_margin': get_safe_float(score_ctx.get('score_margin')),
        'judge_confidence': get_safe_float(score_ctx.get('judge_confidence')),
        'strategy_confidence': get_safe_float(score_ctx.get('strategy_confidence')),
        'direction_confidence': get_safe_float(dc.get('value')),
        'direction_confidence_source': dc.get('source'),
        'direction_confidence_threshold': get_safe_float(dc.get('threshold')),
        'direction_confidence_passed': dc.get('passed'),

        'pm_norm_60s': get_safe_float(pm.get('pm_norm_60s')),
        'pm_norm_300s': get_safe_float(pm.get('pm_norm_300s')),
        'vol_pct_60s': get_safe_float(pm.get('vol_pct_60s')),
        'vol_pct_300s': get_safe_float(pm.get('vol_pct_300s')),

        'spread_bps': get_safe_float(liq.get('spread_bps')),
        'liquidity_kappa': get_safe_float(liq.get('liquidity_kappa')),
        'absorption': get_safe_float(liq.get('absorption')),

        'violations': lvf.get('violations', []),
    }

    # Classification
    if is_objectively_winner:
        result['classification'] = 'missed_positive'  # Gate blocked a winner
    elif is_objectively_loser:
        # Gate correctly blocked a loser
        result['classification'] = 'correct_block'
    else:
        result['classification'] = 'ambiguous'

    return result

# ============================================================================
# SUMMARY COMPUTATION
# ============================================================================


def compute_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics."""

    missed = [r for r in results if r['classification'] == 'missed_positive']
    correct = [r for r in results if r['classification'] == 'correct_block']
    ambig = [r for r in results if r['classification'] == 'ambiguous']

    net_bps = [r['net_bps'] for r in results if r['net_bps'] is not None]

    # By symbol
    by_symbol = defaultdict(
        lambda: {'total': 0, 'missed': 0, 'correct': 0, 'ambig': 0, 'net_sum': 0})
    for r in results:
        by_symbol[r['symbol']]['total'] += 1
        if r['classification'] == 'missed_positive':
            by_symbol[r['symbol']]['missed'] += 1
        elif r['classification'] == 'correct_block':
            by_symbol[r['symbol']]['correct'] += 1
        else:
            by_symbol[r['symbol']]['ambig'] += 1
        if r['net_bps'] is not None:
            by_symbol[r['symbol']]['net_sum'] += r['net_bps']

    # By side
    by_side = defaultdict(
        lambda: {'total': 0, 'missed': 0, 'correct': 0, 'ambig': 0, 'net_sum': 0})
    for r in results:
        by_side[r['side']]['total'] += 1
        if r['classification'] == 'missed_positive':
            by_side[r['side']]['missed'] += 1
        elif r['classification'] == 'correct_block':
            by_side[r['side']]['correct'] += 1
        else:
            by_side[r['side']]['ambig'] += 1
        if r['net_bps'] is not None:
            by_side[r['side']]['net_sum'] += r['net_bps']

    return {
        'total_cases': len(results),
        'missed_positive': len(missed),
        'correct_blocks': len(correct),
        'ambiguous': len(ambig),
        'median_net_bps': statistics.median(net_bps) if net_bps else None,
        'mean_net_bps': statistics.mean(net_bps) if net_bps else None,
        'total_net_bps': sum(net_bps) if net_bps else None,
        'worst_case_bps': min(net_bps) if net_bps else None,
        'best_case_bps': max(net_bps) if net_bps else None,
        'p25_bps': sorted(net_bps)[len(net_bps)//4] if net_bps else None,
        'p75_bps': sorted(net_bps)[3*len(net_bps)//4] if net_bps else None,
        'by_symbol': dict(by_symbol),
        'by_side': dict(by_side),
    }

# ============================================================================
# VARIANT SWEEP
# ============================================================================


def sweep_variants(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Test variant policies on frozen cohort."""

    variants = {}

    # Variant A: Baseline (all deny, current)
    variants['A_baseline'] = {
        'name': 'All NRR-062 deny (current)',
        'allowed': 0,
        'denied': len(results),
        'winners_recovered': 0,
        'losers_admitted': 0,
        'total_net_bps': 0,
        'verdict': 'current_policy',
    }

    # Variant B: Symbol-specific allows
    for symbol in ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'BNBUSDT']:
        by_sym = [r for r in results if r['symbol'] == symbol]
        if by_sym:
            missed_in_sym = len(
                [r for r in by_sym if r['classification'] == 'missed_positive'])
            correct_in_sym = len(
                [r for r in by_sym if r['classification'] == 'correct_block'])
            net_sum = sum([r['net_bps']
                          for r in by_sym if r['net_bps'] is not None])

            variants[f'B_{symbol}'] = {
                'name': f'Allow {symbol}',
                'allowed': len(by_sym),
                'denied': len(results) - len(by_sym),
                'winners_recovered': missed_in_sym,
                'losers_admitted': correct_in_sym,
                'total_net_bps': net_sum,
                'verdict': 'promising' if missed_in_sym >= 5 and correct_in_sym <= 2 else 'risky',
            }

    # Variant C-H: Placeholder
    for var_name, var_desc in [
        ('C', 'Score margin threshold'),
        ('D', 'Direction confidence rule'),
        ('E', 'Price motion confirmation'),
        ('F', 'Liquidity filter'),
        ('G', 'Two-key unlock'),
        ('H', 'Soft score candidate'),
    ]:
        variants[f'C_{var_name}'] = {
            'name': var_desc,
            'allowed': 0,
            'denied': len(results),
            'winners_recovered': 0,
            'losers_admitted': 0,
            'total_net_bps': 0,
            'verdict': 'placeholder',
        }

    return variants

# ============================================================================
# MAIN
# ============================================================================


def main():
    logger.info("="*80)
    logger.info("NRR-062 FROZEN COUNTERFACTUAL REPLAY - PROMPT 9")
    logger.info("="*80)

    # Load cases
    cases = load_frozen_cases()
    logger.info(f"Loaded {len(cases)} cases")

    # Classify each case
    logger.info("Classifying outcomes...")
    results = []
    for i, case in enumerate(cases):
        if (i + 1) % 20 == 0:
            logger.info(f"  Classified {i+1}/{len(cases)}...")
        result = classify_outcome(case)
        results.append(result)

    # Compute summary
    logger.info("Computing summary statistics...")
    summary = compute_summary(results)
    logger.info(f"  Missed positive: {summary['missed_positive']}")
    logger.info(f"  Correct blocks: {summary['correct_blocks']}")
    logger.info(f"  Ambiguous: {summary['ambiguous']}")
    logger.info(f"  Median net bps: {summary['median_net_bps']:.2f}")

    # Variant sweep
    logger.info("Running variant sweep...")
    variants = sweep_variants(results)

    # Write outputs
    logger.info("Writing outputs...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Results JSONL
    with open(REPLAY_RESULTS_PATH, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    logger.info(f"  Wrote {REPLAY_RESULTS_PATH}")

    # Summary JSON
    with open(REPLAY_SUMMARY_PATH, 'w') as f:
        json.dump(summary, f, indent=2)
    logger.info(f"  Wrote {REPLAY_SUMMARY_PATH}")

    # Variants JSON
    with open(VARIANT_SWEEP_PATH, 'w') as f:
        json.dump(variants, f, indent=2)
    logger.info(f"  Wrote {VARIANT_SWEEP_PATH}")

    logger.info("="*80)
    logger.info("REPLAY COMPLETE")
    logger.info("="*80)

    return results, summary, variants


if __name__ == '__main__':
    results, summary, variants = main()
