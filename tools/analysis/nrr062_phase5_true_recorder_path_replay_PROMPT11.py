#!/usr/bin/env python3
"""Phase 5: True recorder-path replay using frozen + extension data."""

import json
from pathlib import Path
from datetime import datetime, timezone
import logging
import csv
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

FROZEN_DIR = Path('logs/frozen/nrr062_fresh_capture_20260507_103909')
CASES_FILE = FROZEN_DIR / 'nrr062_cases.jsonl'
RECORDER_DIR = FROZEN_DIR / 'data' / 'recorder'
EXTENSION_DIR = None  # Will be discovered

# Recorder parameters
TOTAL_COST_BPS = 10  # fee (8) + slippage (2)


def ts_ms_to_utc(ts_ms):
    """Convert ms to UTC datetime."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def find_extension_dir():
    """Find the frozen recorder extension directory."""
    exts = list(FROZEN_DIR.glob('recorder_extension_*'))
    if exts:
        return exts[-1]  # Most recent
    return None


def load_cases():
    """Load frozen cases."""
    cases = []
    with open(CASES_FILE) as f:
        for line in f:
            case = json.loads(line)['nrr062_case']
            cases.append(case)
    return cases


def find_recorder_file(symbol, ts_ms):
    """Find best recorder CSV for symbol at timestamp."""

    ts_dt = ts_ms_to_utc(ts_ms)
    date_str = ts_dt.strftime('%Y-%m-%d')

    # Try frozen first, then extension
    sources = [RECORDER_DIR, None]
    if EXTENSION_DIR:
        sources = [RECORDER_DIR, EXTENSION_DIR / 'data']

    for source in sources:
        if not source:
            continue
        date_path = source / date_str
        if not date_path.exists():
            continue

        # Prefer 180, then 300, then 900
        for tf in [180, 300, 900]:
            csv_path = date_path / f"{symbol}_{tf}.csv"
            if csv_path.exists():
                return csv_path

    return None


def load_recorder_bars(csv_path, start_ts_ms):
    """Load bars from CSV starting after start_ts_ms."""
    bars = []
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_ms = int(row['timestamp'])
                    if ts_ms > start_ts_ms:
                        bars.append({
                            'ts_ms': ts_ms,
                            'open': float(row.get('open', 0)),
                            'high': float(row.get('high', 0)),
                            'low': float(row.get('low', 0)),
                            'close': float(row.get('close', 0)),
                            'volume': float(row.get('volume', 0)),
                        })
                except (ValueError, KeyError):
                    pass
    except Exception as e:
        logging.error(f"Error reading {csv_path}: {e}")

    return bars


def replay_case(case):
    """Run path-based replay for a single case."""

    rid = case['rid']
    symbol = case['symbol']
    side = case['side']
    ts_ms = case['ts_ms']

    # Geometry (nested in low_vol_cost_floor.geometry)
    lvf = case.get('low_vol_cost_floor', {})
    geom = lvf.get('geometry', {})
    entry_price = geom.get('entry_price')
    target_price = geom.get('target_price')
    stop_price = geom.get('stop_price')

    if not all([entry_price, target_price, stop_price]):
        return {
            'rid': rid,
            'symbol': symbol,
            'side': side,
            'path_outcome': 'INSUFFICIENT_DATA',
            'classification': 'ambiguous',
            'notes': 'missing_geometry',
        }

    # Find recorder file
    csv_path = find_recorder_file(symbol, ts_ms)
    if not csv_path:
        return {
            'rid': rid,
            'symbol': symbol,
            'side': side,
            'path_outcome': 'INSUFFICIENT_FORWARD_DATA',
            'classification': 'ambiguous',
            'notes': 'no_recorder_file',
        }

    # Load bars
    bars = load_recorder_bars(csv_path, ts_ms)
    if not bars:
        return {
            'rid': rid,
            'symbol': symbol,
            'side': side,
            'path_outcome': 'INSUFFICIENT_FORWARD_DATA',
            'classification': 'ambiguous',
            'notes': 'no_forward_bars',
        }

    # Replay logic
    if side == 'BUY':
        # First bar
        bar = bars[0]
        tp_hit = bar['high'] >= target_price
        sl_hit = bar['low'] <= stop_price

        if tp_hit and sl_hit:
            return {
                'rid': rid,
                'symbol': symbol,
                'side': side,
                'path_outcome': 'AMBIGUOUS_SAME_BAR',
                'classification': 'ambiguous',
            }
        elif tp_hit:
            actual_bps = (target_price - entry_price) / entry_price * 10000
            net_bps = actual_bps - TOTAL_COST_BPS
            return {
                'rid': rid,
                'symbol': symbol,
                'side': side,
                'path_outcome': 'TP_FIRST',
                'classification': 'missed_positive',
                'target_bps': actual_bps,
                'net_bps': net_bps,
            }
        elif sl_hit:
            actual_bps = (entry_price - stop_price) / entry_price * 10000
            net_bps = -(actual_bps + TOTAL_COST_BPS)
            return {
                'rid': rid,
                'symbol': symbol,
                'side': side,
                'path_outcome': 'SL_FIRST',
                'classification': 'correct_block',
                'stop_bps': actual_bps,
                'net_bps': net_bps,
            }
        else:
            # Check 120m horizon
            bar_120m = None
            for bar in bars:
                if bar['ts_ms'] >= ts_ms + 7200000:  # 120m
                    bar_120m = bar
                    break

            if bar_120m:
                close_bps = (bar_120m['close'] -
                             entry_price) / entry_price * 10000
                net_bps = close_bps - TOTAL_COST_BPS
                classification = 'missed_positive' if net_bps > 0 else 'correct_block'
                return {
                    'rid': rid,
                    'symbol': symbol,
                    'side': side,
                    'path_outcome': 'HORIZON_CLOSE_120M',
                    'classification': classification,
                    'close_bps': close_bps,
                    'net_bps': net_bps,
                }
            else:
                # Not enough data
                return {
                    'rid': rid,
                    'symbol': symbol,
                    'side': side,
                    'path_outcome': 'INSUFFICIENT_FORWARD_DATA',
                    'classification': 'ambiguous',
                    'notes': 'no_120m_bar',
                }

    else:  # SELL
        bar = bars[0]
        tp_hit = bar['low'] <= target_price
        sl_hit = bar['high'] >= stop_price

        if tp_hit and sl_hit:
            return {
                'rid': rid,
                'symbol': symbol,
                'side': side,
                'path_outcome': 'AMBIGUOUS_SAME_BAR',
                'classification': 'ambiguous',
            }
        elif tp_hit:
            actual_bps = (entry_price - target_price) / entry_price * 10000
            net_bps = actual_bps - TOTAL_COST_BPS
            return {
                'rid': rid,
                'symbol': symbol,
                'side': side,
                'path_outcome': 'TP_FIRST',
                'classification': 'missed_positive',
                'target_bps': actual_bps,
                'net_bps': net_bps,
            }
        elif sl_hit:
            actual_bps = (stop_price - entry_price) / entry_price * 10000
            net_bps = -(actual_bps + TOTAL_COST_BPS)
            return {
                'rid': rid,
                'symbol': symbol,
                'side': side,
                'path_outcome': 'SL_FIRST',
                'classification': 'correct_block',
                'stop_bps': actual_bps,
                'net_bps': net_bps,
            }
        else:
            # Check 120m
            bar_120m = None
            for bar in bars:
                if bar['ts_ms'] >= ts_ms + 7200000:
                    bar_120m = bar
                    break

            if bar_120m:
                close_bps = (
                    entry_price - bar_120m['close']) / entry_price * 10000
                net_bps = close_bps - TOTAL_COST_BPS
                classification = 'missed_positive' if net_bps > 0 else 'correct_block'
                return {
                    'rid': rid,
                    'symbol': symbol,
                    'side': side,
                    'path_outcome': 'HORIZON_CLOSE_120M',
                    'classification': classification,
                    'close_bps': close_bps,
                    'net_bps': net_bps,
                }
            else:
                return {
                    'rid': rid,
                    'symbol': symbol,
                    'side': side,
                    'path_outcome': 'INSUFFICIENT_FORWARD_DATA',
                    'classification': 'ambiguous',
                    'notes': 'no_120m_bar',
                }


def compute_summary(results):
    """Compute summary statistics."""

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

    summary = {
        'total_cases': len(results),
        'replayable_cases': missed + correct + len([r for r in results if r.get('path_outcome') in ['AMBIGUOUS_SAME_BAR']]),
        'missed_positive': missed,
        'correct_blocks': correct,
        'ambiguous': ambig,
        'tp_first': tp_first,
        'sl_first': sl_first,
        'horizon_close_120m': horizon,
        'same_bar_ambiguous': same_bar,
        'insufficient_forward_data': insuff,
        'median_net_bps': sorted(net_vals)[len(net_vals)//2] if net_vals else None,
        'mean_net_bps': sum(net_vals) / len(net_vals) if net_vals else None,
        'total_net_bps': sum(net_vals) if net_vals else None,
        'p25_net_bps': sorted(net_vals)[len(net_vals)//4] if net_vals else None,
        'p75_net_bps': sorted(net_vals)[3*len(net_vals)//4] if net_vals else None,
    }

    # By symbol
    by_symbol = defaultdict(lambda: {'missed': 0, 'correct': 0, 'ambig': 0})
    for r in results:
        sym = r.get('symbol', 'UNKNOWN')
        if r.get('classification') == 'missed_positive':
            by_symbol[sym]['missed'] += 1
        elif r.get('classification') == 'correct_block':
            by_symbol[sym]['correct'] += 1
        else:
            by_symbol[sym]['ambig'] += 1

    summary['by_symbol'] = dict(by_symbol)

    return summary


def main():
    global EXTENSION_DIR

    logging.info("=" * 80)
    logging.info("PHASE 5: TRUE RECORDER-PATH REPLAY - PROMPT 11")
    logging.info("=" * 80)

    # Discover extension
    EXTENSION_DIR = find_extension_dir()
    logging.info(f"Extension found: {EXTENSION_DIR}")

    # Load cases
    cases = load_cases()
    logging.info(f"Loaded {len(cases)} cases")

    # Replay
    logging.info("\nRunning true recorder-path replay...")
    results = []
    for i, case in enumerate(cases):
        if (i + 1) % 20 == 0:
            logging.info(f"  Replayed {i+1}/{len(cases)}...")
        result = replay_case(case)
        results.append(result)

    logging.info(f"  Replayed {len(cases)}/{len(cases)}... DONE")

    # Summary
    logging.info("\nComputing summary...")
    summary = compute_summary(results)

    logging.info("=" * 80)
    logging.info("CORRECTED REPLAY SUMMARY")
    logging.info("=" * 80)
    logging.info(f"Total cases: {summary['total_cases']}")
    logging.info(f"Missed positive: {summary['missed_positive']}")
    logging.info(f"Correct blocks: {summary['correct_blocks']}")
    logging.info(f"Ambiguous: {summary['ambiguous']}")
    logging.info(f"TP first: {summary['tp_first']}")
    logging.info(f"SL first: {summary['sl_first']}")
    logging.info(f"Horizon close: {summary['horizon_close_120m']}")
    logging.info(f"Median net bps: {summary.get('median_net_bps')}")
    logging.info(f"Total net bps: {summary.get('total_net_bps')}")

    # Write outputs
    logging.info("\nWriting outputs...")

    results_path = FROZEN_DIR / 'nrr062_recorder_path_replay_PROMPT11.jsonl'
    with open(results_path, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    logging.info(f"  Wrote {results_path}")

    summary_path = FROZEN_DIR / 'nrr062_recorder_path_replay_summary_PROMPT11.json'
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    logging.info(f"  Wrote {summary_path}")

    logging.info("=" * 80)
    logging.info("PHASE 5 COMPLETE")
    logging.info("=" * 80)

    return results, summary


if __name__ == '__main__':
    main()
