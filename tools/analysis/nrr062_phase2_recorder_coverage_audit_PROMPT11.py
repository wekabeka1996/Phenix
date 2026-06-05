#!/usr/bin/env python3
"""Phase 2: Scan all recorder sources and audit coverage."""

import json
from pathlib import Path
from datetime import datetime, timezone
import logging
import csv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

FROZEN_DIR = Path('logs/frozen/nrr062_fresh_capture_20260507_103909')

# Recorder sources to check
RECORDER_SOURCES = [
    ('frozen_existing', FROZEN_DIR / 'data' / 'recorder'),
    ('workspace_current', Path('data') / 'recorder'),
    ('workspace_backup_forensics', Path('reports') / 'forensics' / 'recorder'),
]


def ts_ms_to_utc(ts_ms):
    """Convert milliseconds since epoch to UTC datetime."""
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def scan_recorder_file(csv_path):
    """Scan a single recorder CSV file for bar timestamps."""
    if not csv_path.exists():
        return None

    try:
        min_ts_ms = None
        max_ts_ms = None
        row_count = 0

        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_count += 1
                try:
                    ts_ms = int(row.get('timestamp', 0))
                    if ts_ms > 0:
                        if min_ts_ms is None or ts_ms < min_ts_ms:
                            min_ts_ms = ts_ms
                        if max_ts_ms is None or ts_ms > max_ts_ms:
                            max_ts_ms = ts_ms
                except (ValueError, KeyError):
                    pass

        if min_ts_ms is None:
            return None

        min_utc = ts_ms_to_utc(min_ts_ms)
        max_utc = ts_ms_to_utc(max_ts_ms)

        return {
            'min_ts_ms': min_ts_ms,
            'max_ts_ms': max_ts_ms,
            'min_bar_ts_utc': min_utc.isoformat() if min_utc else None,
            'max_bar_ts_utc': max_utc.isoformat() if max_utc else None,
            'row_count': row_count,
            'size_bytes': csv_path.stat().st_size,
        }
    except Exception as e:
        logging.error(f"Error reading {csv_path}: {e}")
        return None


def extract_symbol_timeframe(filename):
    """Extract symbol and timeframe from filename like BTCUSDT_180.csv."""
    # filename can be a string or Path
    if isinstance(filename, Path):
        name = filename.stem
    else:
        name = Path(filename).stem

    parts = name.split('_')
    if len(parts) >= 2:
        symbol = parts[0]
        try:
            timeframe_sec = int(parts[1])
            return symbol, timeframe_sec
        except ValueError:
            pass
    return None, None


def scan_source(source_name, source_path):
    """Scan a recorder source directory."""
    logging.info(f"\nScanning {source_name}: {source_path}")

    if not source_path.exists():
        logging.info(f"  → Source does not exist")
        return None

    files_found = []
    by_symbol = {}

    # Find all CSV files
    for csv_path in source_path.rglob('*.csv'):
        symbol, tf_sec = extract_symbol_timeframe(csv_path.name)
        if not symbol:
            continue

        data = scan_recorder_file(csv_path)
        if not data:
            continue

        rel_path = csv_path.relative_to(source_path)

        logging.info(f"  ✓ {csv_path.name}: rows={data['row_count']}, "
                     f"min={data['min_bar_ts_utc']}, max={data['max_bar_ts_utc']}")

        files_found.append({
            'filename': csv_path.name,
            'relative_path': str(rel_path),
            'symbol': symbol,
            'timeframe_sec': tf_sec,
            'data': data,
        })

        if symbol not in by_symbol:
            by_symbol[symbol] = {}
        if tf_sec not in by_symbol[symbol]:
            by_symbol[symbol][tf_sec] = []

        by_symbol[symbol][tf_sec].append({
            'filename': csv_path.name,
            'relative_path': str(rel_path),
            'data': data,
        })

    if not files_found:
        logging.info(f"  → No recorder files found")
        return None

    logging.info(f"  → Found {len(files_found)} CSV files")

    return {
        'source_name': source_name,
        'source_path': str(source_path),
        'files_found': len(files_found),
        'by_symbol': by_symbol,
        'all_files': files_found,
    }


def main():
    logging.info("=" * 80)
    logging.info("PHASE 2: RECORDER COVERAGE AUDIT")
    logging.info("=" * 80)

    # Load case requirements
    req_file = FROZEN_DIR / 'case_time_requirements_PROMPT11.json'
    with open(req_file) as f:
        case_reqs = json.load(f)['case_time_requirements']

    min_case_ts_ms = case_reqs['min_case_ts_ms']
    max_case_ts_ms = case_reqs['max_case_ts_ms']
    horizon_end_ms = int(datetime.fromisoformat(
        case_reqs['replay_horizon_end_utc_iso']).timestamp() * 1000)
    symbols = case_reqs['symbols']

    logging.info(f"\nCase requirements:")
    logging.info(f"  Min case: {case_reqs['min_case_ts_utc_iso']}")
    logging.info(f"  Max case: {case_reqs['max_case_ts_utc_iso']}")
    logging.info(f"  Horizon end: {case_reqs['replay_horizon_end_utc_iso']}")
    logging.info(f"  Symbols: {', '.join(symbols)}")

    # Scan all sources
    sources = {}
    for source_name, source_path in RECORDER_SOURCES:
        result = scan_source(source_name, source_path)
        if result:
            sources[source_name] = result

    # Analyze coverage
    logging.info("\n" + "=" * 80)
    logging.info("COVERAGE ANALYSIS")
    logging.info("=" * 80)

    coverage_matrix = {
        'case_requirements': case_reqs,
        'sources_scanned': list(sources.keys()),
        'by_source': {},
        'overall_coverage': {
            'all_cases_plus_120m_covered': False,
            'partial_coverage': False,
            'no_coverage': True,
        },
    }

    for source_name, source_data in sources.items():
        logging.info(f"\n{source_name}:")
        logging.info(f"  Files found: {source_data['files_found']}")

        by_symbol_matrix = {}
        source_covers_all = True

        for symbol in symbols:
            if symbol not in source_data['by_symbol']:
                by_symbol_matrix[symbol] = {
                    'available': False,
                    'files': [],
                    'best_timeframe_sec': None,
                }
                source_covers_all = False
                logging.info(f"  {symbol}: NOT FOUND")
                continue

            symbol_data = source_data['by_symbol'][symbol]

            # Pick best timeframe (prefer 180, then 300, then 900)
            best_tf = None
            best_tf_data = None
            for tf in [180, 300, 900]:
                if tf in symbol_data:
                    best_tf = tf
                    best_tf_data = symbol_data[tf]
                    break

            if not best_tf:
                by_symbol_matrix[symbol] = {
                    'available': False,
                    'files': [],
                    'best_timeframe_sec': None,
                }
                source_covers_all = False
                logging.info(f"  {symbol}: FOUND but no usable timeframe")
                continue

            # Check coverage
            file_info = best_tf_data[0]  # Use first file of best timeframe
            min_ts = file_info['data']['min_ts_ms']
            max_ts = file_info['data']['max_ts_ms']

            covers_start = min_ts <= min_case_ts_ms
            covers_horizon = max_ts >= horizon_end_ms
            covers_all = covers_start and covers_horizon

            by_symbol_matrix[symbol] = {
                'available': True,
                'best_timeframe_sec': best_tf,
                'files': [f['filename'] for f in best_tf_data],
                'min_bar_ts_utc': file_info['data']['min_bar_ts_utc'],
                'max_bar_ts_utc': file_info['data']['max_bar_ts_utc'],
                'covers_case_start': covers_start,
                'covers_horizon_end': covers_horizon,
                'covers_all': covers_all,
                'gap_before_start_ms': min_case_ts_ms - min_ts if not covers_start else 0,
                'gap_after_horizon_ms': max_ts - horizon_end_ms if not covers_horizon else 0,
            }

            if not covers_all:
                source_covers_all = False

            status = "✓ FULL" if covers_all else "⚠ PARTIAL" if covers_start or covers_horizon else "✗ NONE"
            logging.info(
                f"  {symbol} ({best_tf}s): {status} {file_info['filename']}")
            if not covers_all:
                logging.info(
                    f"    min_bar={file_info['data']['min_bar_ts_utc']}")
                logging.info(
                    f"    max_bar={file_info['data']['max_bar_ts_utc']}")

        coverage_matrix['by_source'][source_name] = {
            'files_found': source_data['files_found'],
            'by_symbol': by_symbol_matrix,
            'covers_all_cases_plus_120m': source_covers_all,
        }

        if source_covers_all:
            coverage_matrix['overall_coverage']['all_cases_plus_120m_covered'] = True
            coverage_matrix['overall_coverage']['no_coverage'] = False
            logging.info(f"  → FULL COVERAGE ✓")
        elif any(s.get('available') for s in by_symbol_matrix.values()):
            coverage_matrix['overall_coverage']['partial_coverage'] = True
            coverage_matrix['overall_coverage']['no_coverage'] = False
            logging.info(f"  → PARTIAL COVERAGE ⚠")
        else:
            logging.info(f"  → NO COVERAGE ✗")

    # Save coverage matrix
    output_path = FROZEN_DIR / 'nrr062_recorder_coverage_matrix_PROMPT11.json'
    with open(output_path, 'w') as f:
        json.dump(coverage_matrix, f, indent=2)

    logging.info(f"\nWrote {output_path}")
    logging.info("=" * 80)

    return coverage_matrix


if __name__ == '__main__':
    main()
