from __future__ import annotations

import argparse
import glob
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .config_snapshot import capture_git_state, freeze_config_snapshot
except ImportError:  # pragma: no cover - direct script execution
    from config_snapshot import capture_git_state, freeze_config_snapshot


HORIZON_MS = 120 * 60 * 1000
TIMESTAMP_FIELD_CANDIDATES = (
    'ts_ms',
    'ts',
    'timestamp',
    'event_ts_ms',
    'request_ts_ms',
    'response_ts_ms',
    'close_ts_ms',
    'created_ts_ms',
    'updated_ts_ms',
    'snapshot_ts_ms',
    'order_ts_ms',
    'fill_ts_ms',
    'intent_ts_ms',
    'bar_close_ts_ms',
)

NRR062_CAPTURE_SURFACES: tuple[dict[str, Any], ...] = (
    {
        'relative_path': 'logs/order_log_v1.jsonl',
        'required': True,
        'evidence_role': 'primary_runtime_log',
        'authority_role': 'primary_nrr062_reject_and_override_surface',
        'parse_mode': 'jsonl',
        'notes': 'Primary runtime order log surface for NRR-062 probe and override admission truth.',
    },
    {
        'relative_path': 'logs/shadow_telemetry/decision_ledger_v1.jsonl',
        'required': True,
        'evidence_role': 'authority_runtime_log',
        'authority_role': 'decision_terminal_authority_surface',
        'parse_mode': 'jsonl',
        'notes': 'Decision-terminal authority surface required to seal terminal evidence at capture time.',
    },
    {
        'relative_path': 'logs/trade_lifecycle.jsonl',
        'required': True,
        'evidence_role': 'primary_runtime_log',
        'authority_role': 'trade_lifecycle_surface',
        'parse_mode': 'jsonl',
        'notes': 'Primary lifecycle surface for downstream fill and close evidence.',
    },
    {
        'relative_path': 'logs/shadow_critical_event_journal_v1.jsonl',
        'required': False,
        'evidence_role': 'primary_runtime_log',
        'authority_role': 'raw_override_truth_surface',
        'parse_mode': 'jsonl',
        'notes': 'Optional raw shadow journal surface for override truth and diagnostics.',
    },
    {
        'relative_path': 'logs/regime_confidence_audit_v1.jsonl',
        'required': False,
        'evidence_role': 'primary_runtime_log',
        'authority_role': 'regime_confidence_diagnostic_surface',
        'parse_mode': 'jsonl',
        'notes': 'Optional regime confidence audit surface.',
    },
)

REFERENCE_FILES: tuple[str, ...] = (
    'reports/nrr062_low_vol_cost_floor_observability_PROMPT4.md',
    'reports/nrr062_observability_fresh_runtime_audit_PROMPT5B.md',
    'reports/nrr062_zero_cohort_diagnostic_PROMPT6.md',
    'reports/nrr062_fresh_nonzero_cohort_audit_PROMPT7.md',
    'reports/data/nrr062_zero_cohort_diagnostic_PROMPT6_summary.json',
    'reports/data/nrr062_fresh_nonzero_summary_PROMPT7.json',
)


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
    candidates = [obj.get(key) for key in TIMESTAMP_FIELD_CANDIDATES] + [
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


def probe_override_rows(order_log: Path) -> dict[str, int]:
    override_rows = 0
    distinct_rids: set[str] = set()
    with order_log.open('r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            obj = safe_json(line)
            if obj is None:
                continue
            if obj.get('event_type') != 'ORDER_INTENT':
                continue
            low_vol = (obj.get('metadata') or {}).get('low_vol_cost_floor')
            if not isinstance(low_vol, dict):
                continue
            if low_vol.get('nrr062_segment_override_applied') is not True:
                continue
            override_rows += 1
            rid = obj.get('rid')
            if isinstance(rid, str) and rid:
                distinct_rids.add(rid)
    return {
        'override_rows': override_rows,
        'distinct_override_rids': len(distinct_rids),
    }


def _scan_recorder_ts_range(csv_path: Path) -> tuple[int | None, int | None, int, int]:
    min_ts = None
    max_ts = None
    row_count = 0
    parse_errors = 0
    with csv_path.open('r', encoding='utf-8', errors='replace') as fh:
        header = fh.readline().strip().split(',')
        ts_idx = None
        for i, col in enumerate(header):
            if col in {'open_time', 'ts', 'timestamp'}:
                ts_idx = i
                break
        if ts_idx is None:
            return None, None, 0, 0
        for line in fh:
            if not line.strip():
                continue
            row_count += 1
            parts = line.strip().split(',')
            if len(parts) <= ts_idx:
                parse_errors += 1
                continue
            try:
                ts = int(float(parts[ts_idx]))
            except Exception:
                parse_errors += 1
                continue
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
    return min_ts, max_ts, row_count, parse_errors


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
            min_ts, max_ts, row_count, parse_errors = _scan_recorder_ts_range(
                csv_path)
            covers = isinstance(max_ts, int) and max_ts >= required_end_ts
            tf_map[tf] = {
                'path': str(csv_path).replace('\\', '/'),
                'row_count': row_count,
                'min_ts_ms': min_ts,
                'max_ts_ms': max_ts,
                'covers_required_horizon_end': covers,
                'parse_errors': parse_errors,
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


def _iso_from_ts_ms(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).isoformat()


def _scan_jsonl_file(path: Path) -> dict[str, Any]:
    row_count = 0
    parse_errors = 0
    min_ts_ms = None
    max_ts_ms = None
    with path.open('r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if not line.strip():
                continue
            obj = safe_json(line)
            if obj is None:
                parse_errors += 1
                continue
            row_count += 1
            ts_ms = _extract_case_ts_ms(obj)
            if ts_ms is None:
                continue
            min_ts_ms = ts_ms if min_ts_ms is None else min(min_ts_ms, ts_ms)
            max_ts_ms = ts_ms if max_ts_ms is None else max(max_ts_ms, ts_ms)
    return {
        'row_count': row_count,
        'parse_errors': parse_errors,
        'min_ts_ms': min_ts_ms,
        'max_ts_ms': max_ts_ms,
        'min_ts_utc': _iso_from_ts_ms(min_ts_ms),
        'max_ts_utc': _iso_from_ts_ms(max_ts_ms),
    }


def _scan_csv_file(path: Path) -> dict[str, Any]:
    min_ts_ms, max_ts_ms, row_count, parse_errors = _scan_recorder_ts_range(
        path)
    return {
        'row_count': row_count,
        'parse_errors': parse_errors,
        'min_ts_ms': min_ts_ms,
        'max_ts_ms': max_ts_ms,
        'min_ts_utc': _iso_from_ts_ms(min_ts_ms),
        'max_ts_utc': _iso_from_ts_ms(max_ts_ms),
    }


def _collect_file_stats(path: Path, parse_mode: str | None) -> dict[str, Any]:
    if parse_mode == 'jsonl':
        return _scan_jsonl_file(path)
    if parse_mode == 'csv_open_time':
        return _scan_csv_file(path)
    return {
        'row_count': None,
        'parse_errors': None,
        'min_ts_ms': None,
        'max_ts_ms': None,
        'min_ts_utc': None,
        'max_ts_utc': None,
    }


def _build_manifest_item(
    *,
    root: Path,
    capture_dir: Path,
    source_path: Path,
    relative_path: str,
    required: bool,
    evidence_role: str,
    authority_role: str,
    parse_mode: str | None,
    notes: str,
) -> dict[str, Any]:
    dst = capture_dir / relative_path
    item: dict[str, Any] = {
        'source_path': relative_path,
        'frozen_path': str(dst.relative_to(root)).replace('\\', '/'),
        'required': required,
        'file_exists': source_path.exists(),
        'size_bytes': None,
        'mtime': None,
        'sha256': None,
        'copied_successfully': False,
        'evidence_role': evidence_role,
        'authority_role': authority_role,
        'parse_mode': parse_mode or 'none',
        'row_count': None,
        'min_ts_ms': None,
        'max_ts_ms': None,
        'min_ts_utc': None,
        'max_ts_utc': None,
        'parse_errors': None,
        'notes': notes,
    }
    if source_path.exists() and source_path.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dst)
        st = source_path.stat()
        item['size_bytes'] = st.st_size
        item['mtime'] = datetime.fromtimestamp(
            st.st_mtime, timezone.utc).isoformat()
        item['sha256'] = sha256_file(dst)
        item['copied_successfully'] = True
        item.update(_collect_file_stats(dst, parse_mode))
    else:
        item['notes'] = f'{notes} | source_missing_or_not_file'
    return item


def _format_bool(value: bool) -> str:
    return 'True' if value else 'False'


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |',
    ]
    for row in rows:
        rendered = []
        for value in row:
            if value is None:
                rendered.append('')
            else:
                rendered.append(str(value).replace('\n', ' '))
        lines.append('| ' + ' | '.join(rendered) + ' |')
    return '\n'.join(lines)


def _determine_capture_verdict(required_missing: list[str]) -> str:
    if not required_missing:
        return 'CAPTURE_COMPLETE'
    if required_missing == ['logs/shadow_telemetry/decision_ledger_v1.jsonl']:
        return 'CAPTURE_WITH_MISSING_DECISION_LEDGER'
    return 'CAPTURE_WITH_MISSING_REQUIRED_SURFACES'


def _render_freeze_report(
    *,
    root: Path,
    capture_dir: Path,
    manifest: dict[str, Any],
    surface_entries: list[dict[str, Any]],
) -> str:
    git_state = manifest['git']
    decision_ledger = next(
        entry
        for entry in surface_entries
        if entry['source_path'] == 'logs/shadow_telemetry/decision_ledger_v1.jsonl'
    )
    order_log = next(
        entry for entry in surface_entries if entry['source_path'] == 'logs/order_log_v1.jsonl'
    )
    config_summary = manifest['config_snapshot']['summary']
    summary_rows = [
        ['Bundle Root', str(capture_dir.relative_to(root)).replace('\\', '/')],
        ['Capture Scan UTC', manifest['scan_ts']],
        ['Branch', git_state['branch']],
        ['Commit SHA', git_state['commit_sha']],
        ['Dirty Worktree', _format_bool(git_state['dirty_worktree'])],
        ['Capture Verdict', manifest['capture_verdict']],
        ['Authority Complete', _format_bool(manifest['authority_complete'])],
        ['order_log row_count', order_log['row_count']],
        ['Probe order_log_nrr062_rows', manifest['probe']['order_log_nrr062_rows']],
        ['Override-applied ORDER_INTENT rows',
            manifest['probe']['order_log_override_rows']],
        ['Distinct override RIDs', manifest['probe']
            ['order_log_override_distinct_rids']],
        ['Decision Ledger Present', _format_bool(
            decision_ledger['file_exists'])],
        ['Decision Ledger row_count', decision_ledger['row_count']],
        ['Decision Ledger sha256', decision_ledger['sha256']],
        ['Config Snapshot Required Present',
            f"{config_summary['required_present']} / {config_summary['required_files']}"],
    ]

    required_rows: list[list[Any]] = []
    optional_rows: list[list[Any]] = []
    for entry in surface_entries:
        row = [
            entry['source_path'],
            _format_bool(entry['file_exists']),
            entry['row_count'],
            entry['min_ts_utc'],
            entry['max_ts_utc'],
            entry['parse_errors'],
            entry['authority_role'],
        ]
        if entry['required']:
            required_rows.append(row)
        else:
            optional_rows.append(row)

    missing_surfaces = manifest['required_missing'] + \
        manifest['optional_missing']
    warnings = manifest['warnings'] or ['none']

    sections = [
        '# FREEZE_REPORT',
        _markdown_table(['Metric', 'Value'], summary_rows),
        '## Required Surfaces\n\n'
        + _markdown_table(
            ['Surface', 'Present', 'row_count', 'min_ts_utc',
                'max_ts_utc', 'parse_errors', 'Authority Role'],
            required_rows,
        ),
        '## Optional Surfaces\n\n'
        + _markdown_table(
            ['Surface', 'Present', 'row_count', 'min_ts_utc',
                'max_ts_utc', 'parse_errors', 'Authority Role'],
            optional_rows,
        ),
        '## Missing Surfaces\n\n' +
        '\n'.join(f'- {value}' for value in missing_surfaces or ['none']),
        '## Warnings\n\n' + '\n'.join(f'- {value}' for value in warnings),
    ]
    return '\n\n'.join(sections)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = Path.cwd()
    logs = root / 'logs'

    order_log = logs / 'order_log_v1.jsonl'
    core_files = [Path(p) for p in sorted(
        glob.glob(str(logs / 'aurora_core.log*')))]

    if not order_log.exists():
        print(json.dumps(
            {
                'status': 'BLOCKED',
                'missing_required_files': ['logs/order_log_v1.jsonl'],
                'reason': 'order_log_required_for_nrr062_probe',
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 2

    nrr_count, malformed, nrr_rows = probe_order_nrr062(order_log)
    override_probe = probe_override_rows(order_log)

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
        'order_log_override_rows': override_probe['override_rows'],
        'order_log_override_distinct_rids': override_probe['distinct_override_rids'],
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
    git_state = capture_git_state(root)
    config_snapshot = freeze_config_snapshot(
        root, capture_dir, git_state=git_state)

    manifest: dict[str, Any] = {
        'scan_ts': now.isoformat(),
        'git': git_state,
        'probe': probe,
        'recorder_coverage': recorder_coverage,
        'config_snapshot': {
            'manifest_path': config_snapshot['manifest_path'],
            'snapshot_root': config_snapshot['snapshot_root'],
            'summary': config_snapshot['manifest']['summary'],
        },
        'files': [],
        'required_missing': [],
        'optional_missing': [],
        'warnings': [],
        'authority_complete': False,
        'capture_verdict': 'CAPTURE_COMPLETE',
    }

    surface_entries: list[dict[str, Any]] = []
    for surface in NRR062_CAPTURE_SURFACES:
        relative_path = str(surface['relative_path'])
        source_path = root / relative_path
        entry = _build_manifest_item(
            root=root,
            capture_dir=capture_dir,
            source_path=source_path,
            relative_path=relative_path,
            required=bool(surface['required']),
            evidence_role=str(surface['evidence_role']),
            authority_role=str(surface['authority_role']),
            parse_mode=str(surface['parse_mode']),
            notes=str(surface['notes']),
        )
        manifest['files'].append(entry)
        surface_entries.append(entry)

    for cp in core_files:
        relative_path = str(cp.relative_to(root)).replace('\\', '/')
        manifest['files'].append(
            _build_manifest_item(
                root=root,
                capture_dir=capture_dir,
                source_path=cp,
                relative_path=relative_path,
                required=False,
                evidence_role='primary_runtime_log',
                authority_role='runtime_text_log_surface',
                parse_mode=None,
                notes='Aurora core text log segment copied read-only for surrounding runtime context.',
            )
        )

    if args.include_recorder:
        recorder_root = root / 'data' / 'recorder'
        if recorder_root.exists():
            for d in sorted(recorder_root.glob('*')):
                if d.is_dir():
                    for fp in sorted(d.glob('*.csv')):
                        relative_path = str(
                            fp.relative_to(root)).replace('\\', '/')
                        manifest['files'].append(
                            _build_manifest_item(
                                root=root,
                                capture_dir=capture_dir,
                                source_path=fp,
                                relative_path=relative_path,
                                required=False,
                                evidence_role='recorder_market_data',
                                authority_role='recorder_bar_surface',
                                parse_mode='csv_open_time',
                                notes='Recorder market data copied because --include-recorder was requested.',
                            )
                        )

    for relative_path in REFERENCE_FILES:
        rp = root / relative_path
        role = 'reference_report' if rp.suffix.lower() == '.md' else 'summary_artifact'
        manifest['files'].append(
            _build_manifest_item(
                root=root,
                capture_dir=capture_dir,
                source_path=rp,
                relative_path=relative_path,
                required=False,
                evidence_role=role,
                authority_role='reference_context',
                parse_mode=None,
                notes='Reference artifact copied opportunistically when present.',
            )
        )

    manifest['required_missing'] = [
        entry['source_path']
        for entry in surface_entries
        if entry['required'] and not entry['file_exists']
    ]
    manifest['optional_missing'] = [
        entry['source_path']
        for entry in surface_entries
        if (not entry['required']) and not entry['file_exists']
    ]
    manifest['authority_complete'] = not bool(manifest['required_missing'])
    manifest['capture_verdict'] = _determine_capture_verdict(
        manifest['required_missing'])
    if 'logs/shadow_telemetry/decision_ledger_v1.jsonl' in manifest['required_missing']:
        manifest['warnings'].append(
            'decision_ledger missing: bundle is not authority-complete and downstream decision-terminal evidence is not sealed.'
        )
    if manifest['optional_missing']:
        manifest['warnings'].append(
            'optional surfaces missing: ' +
            ', '.join(manifest['optional_missing'])
        )
    if not manifest['authority_complete'] and not manifest['warnings']:
        manifest['warnings'].append('required capture surfaces missing.')

    manifest_path = capture_dir / 'MANIFEST.json'
    freeze_report_path = capture_dir / 'FREEZE_REPORT.md'

    freeze_report = _render_freeze_report(
        root=root,
        capture_dir=capture_dir,
        manifest=manifest,
        surface_entries=surface_entries,
    )
    freeze_report_path.write_text(freeze_report, encoding='utf-8')

    with manifest_path.open('w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    out = {
        'status': 'CAPTURED',
        'capture_verdict': manifest['capture_verdict'],
        'authority_complete': manifest['authority_complete'],
        'required_missing': manifest['required_missing'],
        'optional_missing': manifest['optional_missing'],
        'probe': probe,
        'freeze_path': str(capture_dir).replace('\\', '/'),
        'manifest_path': str(manifest_path).replace('\\', '/'),
        'freeze_report_path': str(freeze_report_path).replace('\\', '/'),
        'config_snapshot_manifest_path': config_snapshot['manifest_path'],
        'dataset_path': None,
        'summary_path': None,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
