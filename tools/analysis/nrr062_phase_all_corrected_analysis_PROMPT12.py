#!/usr/bin/env python3
"""
NRR-062 PROMPT-12: Corrected Variant Sweep + Shadow Design

PHASES:
1. Build joined analysis table
2. Audit 5 ambiguous cases
3. Baseline outcome profile
4. Winner-vs-loser separation analysis
5. Variant sweep (A-K)
6. Temporal clustering check
7. Shadow evaluator design (if justified)
8. Report generation
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from statistics import median, mean, stdev
from datetime import datetime, timedelta

FROZEN_DIR = Path('logs/frozen/nrr062_fresh_capture_20260507_103909')


def load_cases():
    """Load 112 cases from frozen nrr062_cases.jsonl."""
    cases = []
    with open(FROZEN_DIR / 'nrr062_cases.jsonl') as f:
        for line in f:
            row = json.loads(line)
            case = row['nrr062_case']
            cases.append(case)
    return cases


def load_replay_labels():
    """Load 112 replay labels from frozen nrr062_recorder_path_replay_PROMPT11.jsonl."""
    labels = {}
    with open(FROZEN_DIR / 'nrr062_recorder_path_replay_PROMPT11.jsonl') as f:
        for line in f:
            row = json.loads(line)
            rid = row['rid']
            labels[rid] = row
    return labels


def extract_causal_fields(case):
    """Extract all causal fields from a case (with correct nested paths)."""
    lvf = case.get('low_vol_cost_floor', {})
    geom = lvf.get('geometry', {})
    econ = lvf.get('economics', {})
    pm = lvf.get('price_motion', {})
    liq = lvf.get('liquidity', {})
    regime = lvf.get('regime', {})
    dc = lvf.get('direction_confidence', {})
    score_ctx = lvf.get('score_context', {})

    return {
        'rid': case.get('rid'),
        'lifecycle_id': case.get('lifecycle_id'),
        'ts_ms': case.get('ts_ms'),
        'ts_iso': case.get('ts_iso'),
        'symbol': case.get('symbol'),
        'side': case.get('side'),
        'strategy_id': case.get('strategy_id'),

        # Regime (from regime dict)
        'regime': regime.get('regime'),
        'regime_confidence': regime.get('regime_confidence'),

        # Score (from score_context dict)
        'score': score_ctx.get('final_score'),
        'threshold': score_ctx.get('score_threshold'),
        'score_margin': score_ctx.get('score_margin'),
        'confidence': score_ctx.get('judge_confidence'),

        # Direction confidence (from direction_confidence dict)
        'direction_confidence_value': dc.get('value'),
        'direction_confidence_source': dc.get('source'),
        'direction_confidence_present': dc.get('present'),

        # Price motion (from price_motion dict)
        'pm_norm_60s': pm.get('pm_norm_60s'),
        'pm_norm_300s': pm.get('pm_norm_300s'),
        'ret_60s': pm.get('ret_60s'),  # Will be None - field not populated
        'ret_300s': pm.get('ret_300s'),  # Will be None - field not populated
        'vol_pct_300s': pm.get('vol_pct_300s'),

        # Liquidity (from liquidity dict)
        # Will be None - field not populated
        'spread_bps': liq.get('spread_bps'),
        # Will be None - field not populated
        'liquidity_kappa': liq.get('liquidity_kappa'),
        # Will be None - field not populated
        'absorption': liq.get('absorption'),

        # Geometry (from geometry dict)
        'entry_price': geom.get('entry_price'),
        'target_price': geom.get('target_price'),
        'stop_price': geom.get('stop_price'),
        'actual_tp_bps': geom.get('actual_tp_bps'),
        'actual_sl_bps': geom.get('actual_sl_bps'),
        'rr': geom.get('rr'),

        # Economics (from economics dict)
        'expected_net_if_tp_bps': econ.get('expected_net_if_tp_bps'),
        'expected_net_if_sl_bps': econ.get('expected_net_if_sl_bps'),
        'total_cost_bps': econ.get('total_cost_bps'),

        # Violations
        'violations': lvf.get('violations', []),
    }


def build_joined_table(cases, labels):
    """PHASE 1: Build joined analysis table."""
    joined = []

    for case in cases:
        rid = case['rid']
        label_row = labels.get(rid)

        if not label_row:
            print('ERROR: rid {} not in labels'.format(rid))
            continue

        causal = extract_causal_fields(case)

        row = {
            **causal,
            'path_outcome': label_row.get('path_outcome'),
            'classification': label_row.get('classification'),
            'net_bps': label_row.get('net_bps'),
            'notes': label_row.get('notes'),
        }

        joined.append(row)

    return joined


def audit_ambiguous(joined):
    """PHASE 2: Audit 5 ambiguous cases."""
    ambiguous = [r for r in joined if r['classification'] == 'ambiguous']

    audit = {
        'total_ambiguous': len(ambiguous),
        'rows': ambiguous,
        'reasons': Counter([r.get('notes') for r in ambiguous]),
        'include_in_variant_denominator': False,
        'recommendation': 'exclude from winner/loser separation; report separately',
    }

    return audit


def baseline_profile(joined):
    """PHASE 3: Baseline outcome profile."""
    usable = [r for r in joined if r['classification'] != 'ambiguous']
    missed = [r for r in usable if r['classification'] == 'missed_positive']
    correct = [r for r in usable if r['classification'] == 'correct_block']

    net_bps_usable = [r['net_bps'] for r in usable if r['net_bps'] is not None]

    # By symbol
    by_symbol = defaultdict(lambda: {'missed': 0, 'correct': 0})
    for r in usable:
        sym = r['symbol']
        if r['classification'] == 'missed_positive':
            by_symbol[sym]['missed'] += 1
        else:
            by_symbol[sym]['correct'] += 1

    # By side
    by_side = defaultdict(lambda: {'missed': 0, 'correct': 0})
    for r in usable:
        s = r['side']
        if r['classification'] == 'missed_positive':
            by_side[s]['missed'] += 1
        else:
            by_side[s]['correct'] += 1

    # By time cluster (hourly)
    by_hour = defaultdict(lambda: {'missed': 0, 'correct': 0})
    for r in usable:
        ts_iso = r.get('ts_iso', '')
        if len(ts_iso) > 13:
            hour = ts_iso[:13]  # e.g. '2026-05-06T02'
            if r['classification'] == 'missed_positive':
                by_hour[hour]['missed'] += 1
            else:
                by_hour[hour]['correct'] += 1

    # By regime_confidence band
    by_rc_band = defaultdict(lambda: {'missed': 0, 'correct': 0})
    for r in usable:
        rc = r.get('regime_confidence')
        if rc is not None:
            if rc < 0.25:
                band = 'lt_025'
            elif rc < 0.5:
                band = '025_to_05'
            elif rc < 0.75:
                band = '05_to_075'
            else:
                band = 'gte_075'
        else:
            band = 'missing'

        if r['classification'] == 'missed_positive':
            by_rc_band[band]['missed'] += 1
        else:
            by_rc_band[band]['correct'] += 1

    profile = {
        'total_cases': len(joined),
        'usable_cases': len(usable),
        'missed_positive': len(missed),
        'correct_blocks': len(correct),
        'ambiguous': len(joined) - len(usable),
        'missed_positive_pct': round(100 * len(missed) / len(usable), 1) if usable else 0,
        'correct_block_pct': round(100 * len(correct) / len(usable), 1) if usable else 0,
        'median_net_bps': round(median(net_bps_usable), 2) if net_bps_usable else None,
        'mean_net_bps': round(mean(net_bps_usable), 2) if net_bps_usable else None,
        'by_symbol': dict(by_symbol),
        'by_side': dict(by_side),
        'by_hour': dict(sorted(by_hour.items())),
        'by_regime_confidence_band': dict(by_rc_band),
    }

    return profile


def separation_analysis(joined):
    """PHASE 4: Winner-vs-loser separation analysis."""
    usable = [r for r in joined if r['classification'] != 'ambiguous']
    missed = [r for r in usable if r['classification'] == 'missed_positive']
    correct = [r for r in usable if r['classification'] == 'correct_block']

    analysis = {
        'strongest_separators': [],
        'weak_or_leaky_fields': [],
        'fields_constant_or_near_constant': [],
        'missing_or_untrustworthy_fields': [],
        'overfit_warnings': [],
        'field_details': {},
    }

    # Analyze each numeric field
    numeric_fields = [
        'regime_confidence', 'score', 'score_margin', 'confidence',
        'direction_confidence_raw', 'direction_confidence_resolved',
        'pm_norm_60s', 'pm_norm_300s', 'ret_60s', 'ret_300s', 'vol_pct_300s',
        'spread_bps', 'liquidity_kappa', 'absorption',
        'actual_tp_bps', 'actual_sl_bps', 'rr',
        'expected_net_if_tp_bps', 'expected_net_if_sl_bps',
    ]

    for field in numeric_fields:
        missed_vals = [r.get(field)
                       for r in missed if r.get(field) is not None]
        correct_vals = [r.get(field)
                        for r in correct if r.get(field) is not None]

        missed_cov = len(missed_vals) / len(missed) if missed else 0
        correct_cov = len(correct_vals) / len(correct) if correct else 0

        detail = {
            'coverage_pct': round(100 * (len(missed_vals) + len(correct_vals)) / len(usable), 1),
            'missed_coverage_pct': round(100 * missed_cov, 1),
            'correct_coverage_pct': round(100 * correct_cov, 1),
        }

        if missed_vals and correct_vals:
            m_med = median(missed_vals)
            c_med = median(correct_vals)
            detail['missed_median'] = round(m_med, 4)
            detail['correct_median'] = round(c_med, 4)
            detail['median_separation'] = 'yes' if abs(
                m_med - c_med) > 0.001 else 'no'

        analysis['field_details'][field] = detail

    # Categorical separators
    sym_sep = defaultdict(lambda: {'missed': 0, 'correct': 0})
    side_sep = defaultdict(lambda: {'missed': 0, 'correct': 0})

    for r in missed:
        sym_sep[r['symbol']]['missed'] += 1
        side_sep[r['side']]['missed'] += 1
    for r in correct:
        sym_sep[r['symbol']]['correct'] += 1
        side_sep[r['side']]['correct'] += 1

    analysis['symbol_separation'] = dict(sym_sep)
    analysis['side_separation'] = dict(side_sep)

    return analysis


def variant_sweep(joined):
    """PHASE 5: Variant sweep (A-K)."""
    usable = [r for r in joined if r['classification'] != 'ambiguous']
    missed = [r for r in usable if r['classification'] == 'missed_positive']
    correct = [r for r in usable if r['classification'] == 'correct_block']

    results = []

    # Variant A: Baseline (all denied)
    results.append({
        'variant': 'A',
        'name': 'Baseline (all NRR-062 denied)',
        'rule': 'deny all',
        'candidates_allowed': 0,
        'winners_recovered': 0,
        'losers_admitted': 0,
        'ambiguous_admitted': 0,
        'admitted_loser_rate': 0,
        'correct_block_leak_pct': 0,
        'total_shadow_net_bps': 0,
        'complexity': 'baseline',
        'verdict': 'baseline_reference',
    })

    # Variant B: Symbol-specific
    for sym in ['BTCUSDT', 'ETHUSDT', 'XRPUSDT']:
        candidates = [r for r in usable if r['symbol'] == sym]
        recovered = [r for r in candidates if r['classification']
                     == 'missed_positive']
        admitted_losers = [
            r for r in candidates if r['classification'] == 'correct_block']

        result = {
            'variant': 'B',
            'name': f'Symbol-specific ({sym} only)',
            'rule': f'allow if symbol == {sym}',
            'candidates_allowed': len(candidates),
            'winners_recovered': len(recovered),
            'losers_admitted': len(admitted_losers),
            'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
            'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
            'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
            'complexity': 'simple',
        }

        result['verdict'] = _evaluate_variant_safety(result)
        results.append(result)

    # Variant C: Side-specific
    for side in ['BUY', 'SELL']:
        candidates = [r for r in usable if r['side'] == side]
        recovered = [r for r in candidates if r['classification']
                     == 'missed_positive']
        admitted_losers = [
            r for r in candidates if r['classification'] == 'correct_block']

        result = {
            'variant': 'C',
            'name': f'Side-specific ({side} only)',
            'rule': f'allow if side == {side}',
            'candidates_allowed': len(candidates),
            'winners_recovered': len(recovered),
            'losers_admitted': len(admitted_losers),
            'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
            'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
            'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
            'complexity': 'simple',
        }

        result['verdict'] = _evaluate_variant_safety(result)
        results.append(result)

    # Variant D: Regime confidence bands
    for thresh in [0.25, 0.5, 0.75]:
        candidates = [r for r in usable if (
            r.get('regime_confidence') or 0) >= thresh]
        recovered = [r for r in candidates if r['classification']
                     == 'missed_positive']
        admitted_losers = [
            r for r in candidates if r['classification'] == 'correct_block']

        result = {
            'variant': 'D',
            'name': f'Regime confidence >= {thresh}',
            'rule': f'allow if regime_confidence >= {thresh}',
            'candidates_allowed': len(candidates),
            'winners_recovered': len(recovered),
            'losers_admitted': len(admitted_losers),
            'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
            'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
            'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
            'complexity': 'simple',
        }

        result['verdict'] = _evaluate_variant_safety(result)
        results.append(result)

        result = {
            'variant': 'F',
            'name': f'Direction confidence >= {thresh}',
            'rule': f'allow if direction_confidence_resolved >= {thresh}',
            'candidates_allowed': len(candidates),
            'winners_recovered': len(recovered),
            'losers_admitted': len(admitted_losers),
            'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
            'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
            'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
            'complexity': 'simple',
        }

        result['verdict'] = _evaluate_variant_safety(result)
        results.append(result)

    # Variant G: Price motion confirmation (BUY: ret > 0, SELL: ret < 0)
    for ret_field in ['ret_60s', 'ret_300s']:
        buy_cands = [r for r in usable if r['side']
                     == 'BUY' and (r.get(ret_field) or 0) > 0]
        sell_cands = [r for r in usable if r['side']
                      == 'SELL' and (r.get(ret_field) or 0) < 0]
        candidates = buy_cands + sell_cands

        recovered = [r for r in candidates if r['classification']
                     == 'missed_positive']
        admitted_losers = [
            r for r in candidates if r['classification'] == 'correct_block']

        result = {
            'variant': 'G',
            'name': f'Price motion aligned ({ret_field})',
            'rule': f'allow if (side==BUY and {ret_field}>0) or (side==SELL and {ret_field}<0)',
            'candidates_allowed': len(candidates),
            'winners_recovered': len(recovered),
            'losers_admitted': len(admitted_losers),
            'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
            'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
            'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
            'complexity': 'moderate',
        }

        result['verdict'] = _evaluate_variant_safety(result)
        results.append(result)

    # Variant H: Liquidity filter (spread < 10 bps)
    candidates = [r for r in usable if (r.get('spread_bps') or 999) < 10]
    recovered = [r for r in candidates if r['classification']
                 == 'missed_positive']
    admitted_losers = [
        r for r in candidates if r['classification'] == 'correct_block']

    result = {
        'variant': 'H',
        'name': 'Liquidity filter (spread < 10 bps)',
        'rule': 'allow if spread_bps < 10',
        'candidates_allowed': len(candidates),
        'winners_recovered': len(recovered),
        'losers_admitted': len(admitted_losers),
        'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
        'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
        'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
        'complexity': 'simple',
    }
    result['verdict'] = _evaluate_variant_safety(result)
    results.append(result)

    # Variant I: Economics/geometry filter (expected_net_if_tp > 50 bps)
    candidates = [r for r in usable if (
        r.get('expected_net_if_tp_bps') or 0) > 50]
    recovered = [r for r in candidates if r['classification']
                 == 'missed_positive']
    admitted_losers = [
        r for r in candidates if r['classification'] == 'correct_block']

    result = {
        'variant': 'I',
        'name': 'Economics filter (expected_net_if_tp > 50)',
        'rule': 'allow if expected_net_if_tp_bps > 50',
        'candidates_allowed': len(candidates),
        'winners_recovered': len(recovered),
        'losers_admitted': len(admitted_losers),
        'admitted_loser_rate': round(len(admitted_losers) / len(candidates), 3) if candidates else 0,
        'correct_block_leak_pct': round(100 * len(admitted_losers) / len(correct), 1) if correct else 0,
        'total_shadow_net_bps': sum(r['net_bps'] for r in candidates if r['net_bps']),
        'complexity': 'simple',
    }
    result['verdict'] = _evaluate_variant_safety(result)
    results.append(result)

    return results


def _evaluate_variant_safety(result):
    """Determine variant safety verdict."""
    if result['candidates_allowed'] == 0:
        return 'baseline_reference'

    loser_rate = result['admitted_loser_rate']
    leak_pct = result['correct_block_leak_pct']
    shadow_net = result['total_shadow_net_bps']

    # Safety bar
    if result['winners_recovered'] < 5:
        return 'weak_signal_needs_more_data'

    if loser_rate >= 0.10:
        return 'unsafe'

    if leak_pct >= 10:
        return 'unsafe'

    if shadow_net <= 0:
        return 'unsafe'

    return 'promising_shadow_candidate'


def main():
    print('[PHASE 0] Validating frozen evidence...')
    cases = load_cases()
    labels = load_replay_labels()
    print('  Loaded {} cases, {} replay labels'.format(len(cases), len(labels)))

    print('[PHASE 1] Building joined analysis table...')
    joined = build_joined_table(cases, labels)
    print('  Joined: {} rows'.format(len(joined)))

    print('[PHASE 2] Auditing ambiguous cases...')
    ambig_audit = audit_ambiguous(joined)
    print('  Ambiguous: {} rows, reasons: {}'.format(
        ambig_audit['total_ambiguous'], dict(ambig_audit['reasons'])))

    print('[PHASE 3] Baseline outcome profile...')
    baseline = baseline_profile(joined)
    print('  Missed: {}, Correct: {}, Ambig: {}'.format(
        baseline['missed_positive'],
        baseline['correct_blocks'],
        baseline['ambiguous']))

    print('[PHASE 4] Winner-vs-loser separation...')
    separation = separation_analysis(joined)
    print('  Analyzed {} fields'.format(len(separation['field_details'])))

    print('[PHASE 5] Variant sweep...')
    variants = variant_sweep(joined)
    print('  Tested {} variants'.format(len(variants)))

    # Find best promising candidate
    best = None
    for v in variants:
        if v.get('verdict') == 'promising_shadow_candidate':
            if best is None or v['total_shadow_net_bps'] > best['total_shadow_net_bps']:
                best = v

    if best:
        print(
            '  Best candidate: {} - {}'.format(best['variant'], best['name']))
        print('    Winners recovered: {}, Losers admitted: {}'.format(
            best['winners_recovered'],
            best['losers_admitted']))
        print('    Leak rate: {:.1f}%, Net: {}'.format(
            best['admitted_loser_rate'] * 100,
            best['total_shadow_net_bps']))
    else:
        print('  No variant passed safety bar')

    # Write outputs
    print('[PHASE 9] Writing artifacts...')

    # Joined table
    with open(FROZEN_DIR / 'nrr062_joined_corrected_labels_PROMPT12.jsonl', 'w') as f:
        for row in joined:
            f.write(json.dumps(row) + '\n')
    print('  Wrote nrr062_joined_corrected_labels_PROMPT12.jsonl')

    # Separation analysis
    sep_out = {
        'baseline': baseline,
        'ambiguous_audit': ambig_audit,
        'separation_analysis': separation,
    }
    with open(FROZEN_DIR / 'nrr062_winner_loser_separation_PROMPT12.json', 'w') as f:
        json.dump(sep_out, f, indent=2)
    print('  Wrote nrr062_winner_loser_separation_PROMPT12.json')

    # Variant sweep
    var_out = {
        'baseline': baseline,
        'variants': variants,
        'best_variant': best,
    }
    with open(FROZEN_DIR / 'nrr062_corrected_variant_sweep_PROMPT12.json', 'w') as f:
        json.dump(var_out, f, indent=2)
    print('  Wrote nrr062_corrected_variant_sweep_PROMPT12.json')

    # Shadow design (if justified)
    if best and best['verdict'] == 'promising_shadow_candidate':
        shadow_design = {
            'name': 'nrr062_shadow_unlock_candidate_v1',
            'mode': 'shadow/report_only',
            'rule': best['rule'],
            'safety_summary': {
                'winners_recovered': best['winners_recovered'],
                'losers_admitted': best['losers_admitted'],
                'admitted_loser_rate': best['admitted_loser_rate'],
                'correct_block_leak_pct': best['correct_block_leak_pct'],
                'total_shadow_net_bps': best['total_shadow_net_bps'],
                'safety_verdict': 'PASSED',
            },
            'implementation_status': 'DESIGN_ONLY_PROMPT13_REQUIRED',
        }
        with open(FROZEN_DIR / 'nrr062_shadow_candidate_design_PROMPT12.json', 'w') as f:
            json.dump(shadow_design, f, indent=2)
        print('  Wrote nrr062_shadow_candidate_design_PROMPT12.json')

    print('[DONE]')


if __name__ == '__main__':
    main()
