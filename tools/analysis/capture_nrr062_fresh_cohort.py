from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HORIZON_MS = 120 * 60 * 1000


def safe_json(line: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(line)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _extract_case_ts_ms(obj: dict[str, Any]) -> int | None:
    candidates = [
        obj.get('ts_ms'),
        obj.get('ts'),
        obj.get('timestamp'),
        obj.get('event_ts_ms'),
        (obj.get('payload') or {}).get('ts_ms') if isinstance(
            obj.get('payload'), dict) else None,
        (obj.get('metadata') or {}).get('ts_ms') if isinstance(
            obj.get('metadata'), dict) else None,
    ]
    for raw in candidates:
        if raw in (None, ''):
            continue
        try:
            return int(float(raw))
        except Exception:
            continue
    return None


def probe_order_nrr062(order_log: Path) -> tuple[int, int, list[dict[str, Any]]]:
    nrr = 0
    malformed = 0
    rows: list[dict[str, Any]] = []
    with order_log.open('r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            obj = safe_json(line)
            if obj is None:
                malformed += 1
                continue
            if obj.get('event_type') == 'DECISION_INTENT_REJECTED' and obj.get('nrr_code') == 'NRR-062':
                nrr += 1
                rows.append(
                    {
                        'rid': obj.get('rid'),
                        'symbol': obj.get('symbol'),
                        'ts_ms': _extract_case_ts_ms(obj),
                    }
                )
    return nrr, malformed, rows


def _scan_recorder_ts_range(csv_path: Path) -> tuple[int | None, int | None]:
    min_ts = None
    max_ts = None
    with csv_path.open('r', encoding='utf-8', errors='replace') as fh:
        header = fh.readline().strip().split(',')
        ts_idx = None
        for i, col in enumerate(header):
            if col in {'open_time', 'ts', 'timestamp'}:
                ts_idx = i
                break
        if ts_idx is None:
            return None, None
        for line in fh:
            parts = line.strip().split(',')
            if len(parts) <= ts_idx:
                continue
            try:
                ts = int(float(parts[ts_idx]))
            except Exception:
                continue
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
    return min_ts, max_ts


def assess_recorder_coverage(recorder_root: Path, nrr_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, list[int]] = {}
    for row in nrr_rows:
        symbol = row.get('symbol')
        ts_ms = row.get('ts_ms')
        if not isinstance(symbol, str) or ts_ms is None:
            continue
        try:
            ts_int = int(ts_ms)
        except Exception:
            continue
        by_symbol.setdefault(symbol.upper(), []).append(ts_int)

    if not by_symbol:
        return {
            'evaluated': False,
            'reason': 'nrr_rows_missing_symbol_or_ts',
            'coverage_sufficient': False,
            'symbols': {},
        }

    result: dict[str, Any] = {'evaluated': True,
                              'coverage_sufficient': True, 'symbols': {}}

    for symbol, ts_list in sorted(by_symbol.items()):
        max_case_ts = max(ts_list)
        required_end_ts = max_case_ts + HORIZON_MS
        tf_map: dict[str, Any] = {}
        symbol_has_any_sufficient_tf = False

        for csv_path in sorted(recorder_root.glob(f'*/{symbol}_*.csv')):
            tf = csv_path.stem.split('_')[-1]
            min_ts, max_ts = _scan_recorder_ts_range(csv_path)
            covers = isinstance(max_ts, int) and max_ts >= required_end_ts
            tf_map[tf] = {
                'path': str(csv_path).replace('\\', '/'),
                'min_ts_ms': min_ts,
                'max_ts_ms': max_ts,
                'covers_required_horizon_end': covers,
            }
            if covers:
                symbol_has_any_sufficient_tf = True

        result['symbols'][symbol] = {
            'rows': len(ts_list),
            'max_case_ts_ms': max_case_ts,
            'required_horizon_end_ts_ms': required_end_ts,
            'has_any_sufficient_timeframe': symbol_has_any_sufficient_tf,
            'timeframes': tf_map,
        }

        if not symbol_has_any_sufficient_tf:
            result['coverage_sufficient'] = False

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Read-only capture of fresh NRR-062 cohort evidence into logs/frozen.'
    )
    parser.add_argument('--min-nrr062', type=int, default=1)
    parser.add_argument('--out-dir', type=Path, default=Path('logs/frozen'))
    parser.add_argument('--include-recorder', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    return parser


def resolve_and_validate_out_dir(root: Path, out_dir: Path) -> tuple[bool, str, Path]:
    resolved_root = root.resolve()
    resolved_frozen = (root / 'logs' / 'frozen').resolve()
    resolved_out = (out_dir if out_dir.is_absolute()
                    else (root / out_dir)).resolve()

    if not str(resolved_out).startswith(str(resolved_frozen)):
        out_norm = str(resolved_out).replace('\\', '/')
        return (
            False,
            f'out_dir_must_be_under_logs_frozen:{out_norm}',
            resolved_out,
        )
    if not str(resolved_out).startswith(str(resolved_root)):
        out_norm = str(resolved_out).replace('\\', '/')
        return (
            False,
            f'out_dir_must_be_within_repo_root:{out_norm}',
            resolved_out,
        )
    return True, '', resolved_out


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = Path.cwd()
    logs = root / 'logs'

    order_log = logs / 'order_log_v1.jsonl'
    shadow = logs / 'shadow_critical_event_journal_v1.jsonl'
    regime = logs / 'regime_confidence_audit_v1.jsonl'
    trade = logs / 'trade_lifecycle.jsonl'
    core_files = [Path(p) for p in sorted(
        glob.glob(str(logs / 'aurora_core.log*')))]

    required = [order_log, shadow, regime, trade]
    missing = [str(p).replace('\\', '/') for p in required if not p.exists()]
    if missing:
        print(json.dumps(
            {'status': 'BLOCKED', 'missing_required_files': missing}, ensure_ascii=False, indent=2))
        return 2

    nrr_count, malformed, nrr_rows = probe_order_nrr062(order_log)

    out_ok, out_err, resolved_out_dir = resolve_and_validate_out_dir(
        root, args.out_dir)
    if not out_ok:
        print(json.dumps({'status': 'BLOCKED',
              'error': out_err}, ensure_ascii=False, indent=2))
        return 2

    recorder_coverage = None
    if args.include_recorder:
        recorder_root = root / 'data' / 'recorder'
        recorder_coverage = assess_recorder_coverage(recorder_root, nrr_rows) if recorder_root.exists() else {
            'evaluated': False,
            'reason': 'recorder_root_missing',
            'coverage_sufficient': False,
            'symbols': {},
        }

    now = datetime.now(timezone.utc)
    tag = now.strftime('%Y%m%d_%H%M%S')
    capture_dir = resolved_out_dir / f'nrr062_fresh_capture_{tag}'

    probe = {
        'scan_ts': now.isoformat(),
        'order_log_nrr062_rows': nrr_count,
        'order_log_malformed_rows': malformed,
        'row_level_cohort_present': nrr_count >= args.min_nrr062,
        'min_nrr062': args.min_nrr062,
        'dry_run': bool(args.dry_run),
        'output_dir': str(resolved_out_dir).replace('\\', '/'),
        'recorder_coverage': recorder_coverage,
    }

    if args.dry_run or nrr_count < args.min_nrr062:
        print(
            json.dumps(
                {
                    'status': 'NO_CAPTURE',
                    'probe': probe,
                    'would_freeze_to': str(capture_dir).replace('\\', '/'),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    capture_dir.mkdir(parents=True, exist_ok=False)

    references = [
        root / 'reports' / 'nrr062_low_vol_cost_floor_observability_PROMPT4.md',
        root / 'reports' / 'nrr062_observability_fresh_runtime_audit_PROMPT5B.md',
        root / 'reports' / 'nrr062_zero_cohort_diagnostic_PROMPT6.md',
        root / 'reports' / 'nrr062_fresh_nonzero_cohort_audit_PROMPT7.md',
        root / 'reports' / 'data' / 'nrr062_zero_cohort_diagnostic_PROMPT6_summary.json',
        root / 'reports' / 'data' / 'nrr062_fresh_nonzero_summary_PROMPT7.json',
    ]

    copy_plan: list[tuple[Path, str]] = [
        (order_log, 'primary_runtime_log'),
        (shadow, 'primary_runtime_log'),
        (regime, 'primary_runtime_log'),
        (trade, 'primary_runtime_log'),
    ]
    for cp in core_files:
        copy_plan.append((cp, 'primary_runtime_log'))

    if args.include_recorder:
        recorder_root = root / 'data' / 'recorder'
        if recorder_root.exists():
            for d in sorted(recorder_root.glob('*')):
                if d.is_dir():
                    for fp in sorted(d.glob('*.csv')):
                        copy_plan.append((fp, 'recorder_market_data'))

    for rp in references:
        role = 'reference_report' if rp.suffix.lower() == '.md' else 'summary_artifact'
        copy_plan.append((rp, role))

    manifest: dict[str, Any] = {
        'scan_ts': now.isoformat(),
        'probe': probe,
        'recorder_coverage': recorder_coverage,
        'files': [],
    }

    for src, role in copy_plan:
        rel_src = str(src.relative_to(root)).replace(
            '\\', '/') if src.exists() and str(src).startswith(str(root)) else str(src)
        dst = capture_dir / rel_src
        item: dict[str, Any] = {
            'source_path': rel_src,
            'frozen_path': str(dst.relative_to(root)).replace('\\', '/'),
            'file_exists': src.exists(),
            'size_bytes': None,
            'mtime': None,
            'sha256': None,
            'copied_successfully': False,
            'evidence_role': role,
            'notes': '',
        }
        if src.exists() and src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            st = src.stat()
            item['size_bytes'] = st.st_size
            item['mtime'] = datetime.fromtimestamp(
                st.st_mtime, timezone.utc).isoformat()
            item['sha256'] = sha256_file(dst)
            item['copied_successfully'] = True
        else:
            item['notes'] = 'source_missing_or_not_file'
        manifest['files'].append(item)

    manifest_path = capture_dir / 'MANIFEST.json'
    with manifest_path.open('w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    out = {
        'status': 'CAPTURED',
        'probe': probe,
        'freeze_path': str(capture_dir).replace('\\', '/'),
        'manifest_path': str(manifest_path).replace('\\', '/'),
        'dataset_path': None,
        'summary_path': None,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
