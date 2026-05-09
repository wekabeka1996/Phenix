#!/usr/bin/env python3
"""Phase 1: Audit case timestamps from frozen NRR-062 cohort."""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

FROZEN_DIR = Path('logs/frozen/nrr062_fresh_capture_20260507_103909')
CASES_FILE = FROZEN_DIR / 'nrr062_cases.jsonl'


def load_cases():
    """Load frozen case dataset."""
    cases = []
    with open(CASES_FILE) as f:
        for line in f:
            wrapper = json.loads(line)
            case = wrapper['nrr062_case']
            cases.append(case)
    return cases


def ts_ms_to_utc(ts_ms):
    """Convert milliseconds since epoch to UTC datetime."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def main():
    logging.info("=" * 80)
    logging.info("PHASE 1: CASE TIMESTAMP AUDIT")
    logging.info("=" * 80)

    cases = load_cases()
    logging.info(f"Loaded {len(cases)} cases")

    # Collect timestamps
    timestamps = [case['ts_ms'] for case in cases]
    timestamps.sort()

    min_ts_ms = min(timestamps)
    max_ts_ms = max(timestamps)

    min_ts_utc = ts_ms_to_utc(min_ts_ms)
    max_ts_utc = ts_ms_to_utc(max_ts_ms)

    # Replay horizon: 120 minutes after last signal
    replay_horizon_end_utc = max_ts_utc + timedelta(minutes=120)

    # Extract symbols and dates
    symbols = set(case['symbol'] for case in cases)
    dates_utc = set()
    dates_local = set()

    for ts_ms in timestamps:
        dt_utc = ts_ms_to_utc(ts_ms)
        dates_utc.add(dt_utc.strftime('%Y-%m-%d'))
        # Assume local is UTC offset -7 (PDT) for now
        dt_local = dt_utc.replace(tzinfo=None) + timedelta(hours=-7)
        dates_local.add(dt_local.strftime('%Y-%m-%d'))

    result = {
        'case_time_requirements': {
            'total_cases': len(cases),
            'min_case_ts_ms': min_ts_ms,
            'max_case_ts_ms': max_ts_ms,
            'min_case_ts_utc_iso': min_ts_utc.isoformat(),
            'max_case_ts_utc_iso': max_ts_utc.isoformat(),
            'replay_horizon_end_utc_iso': replay_horizon_end_utc.isoformat(),
            'symbols': sorted(list(symbols)),
            'required_utc_dates': sorted(list(dates_utc)),
            'required_local_dates_pdt': sorted(list(dates_local)),
            'timezone_note': 'Local dates assume PDT (UTC-7); recorder files may use UTC date folders or local folders',
        },
    }

    logging.info("\n" + "=" * 80)
    logging.info("CASE TIME REQUIREMENTS")
    logging.info("=" * 80)
    logging.info(
        f"Total cases: {result['case_time_requirements']['total_cases']}")
    logging.info(
        f"Min case timestamp (UTC): {result['case_time_requirements']['min_case_ts_utc_iso']}")
    logging.info(
        f"Max case timestamp (UTC): {result['case_time_requirements']['max_case_ts_utc_iso']}")
    logging.info(
        f"Replay horizon end (UTC): {result['case_time_requirements']['replay_horizon_end_utc_iso']}")
    logging.info(
        f"Symbols needed: {', '.join(result['case_time_requirements']['symbols'])}")
    logging.info(
        f"UTC dates needed: {', '.join(result['case_time_requirements']['required_utc_dates'])}")
    logging.info(
        f"Local dates needed (PDT): {', '.join(result['case_time_requirements']['required_local_dates_pdt'])}")

    # Save result
    output_path = FROZEN_DIR / 'case_time_requirements_PROMPT11.json'
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    logging.info(f"\nWrote {output_path}")
    logging.info("=" * 80)

    return result


if __name__ == '__main__':
    main()
