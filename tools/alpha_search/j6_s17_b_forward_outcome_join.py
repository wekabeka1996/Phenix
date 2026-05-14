#!/usr/bin/env python3
"""
J6-S17-B Forward Outcome Join Dataset Builder

Joins:
  policy_cortex_*.jsonl
  + verdict_*.jsonl
  + shadow_entry_plan_*.jsonl
  + simulator outcomes
  → joined dataset by cycle_key

Output:
  reports/alpha_search/j6_s17_b_*.json (CSV, JSONL, reports)

No runtime changes. Read-only join. Deterministic simulator.
"""

import json
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
import csv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

OutcomeJoinKey = Tuple[str, str]


@dataclass
class JoinMetrics:
    """Metrics for dataset join readiness."""
    policy_records_total: int = 0
    verdict_records_total: int = 0
    shadow_plan_records_total: int = 0

    policy_keys_unique: int = 0
    verdict_keys_unique: int = 0
    shadow_keys_unique: int = 0

    policy_verdict_join_rate_pct: float = 0.0
    policy_shadow_join_rate_pct: float = 0.0
    shadow_outcome_join_rate_pct: float = 0.0

    rows_with_outcome: int = 0
    rows_without_outcome: int = 0
    invalid_outcome_count: int = 0
    outcome_join_integrity_error_count: int = 0
    duplicate_canonical_outcome_key_count: int = 0
    missing_canonical_outcome_key_rows: int = 0
    duplicate_plan_id_count: int = 0
    canonical_outcome_join: str = 'cycle_key+tier'
    plan_id_usage: str = 'diagnostics_only'


@dataclass
class OutcomeIndexBuildResult:
    canonical_index: Dict[OutcomeJoinKey, Dict[str, Any]]
    duplicate_canonical_keys: set[OutcomeJoinKey]
    missing_canonical_key_rows: int = 0
    duplicate_plan_id_count: int = 0


def canonical_outcome_key(record: Mapping[str, Any]) -> OutcomeJoinKey | None:
    cycle_key = str(record.get('cycle_key') or '')
    tier = str(record.get('tier') or record.get('confidence_tier') or '')
    if not cycle_key or not tier:
        return None
    return cycle_key, tier


def format_canonical_outcome_key(key: OutcomeJoinKey) -> str:
    return f'{key[0]}::{key[1]}'


def build_outcome_index_from_records(records: List[Dict[str, Any]]) -> OutcomeIndexBuildResult:
    canonical_index: Dict[OutcomeJoinKey, Dict[str, Any]] = {}
    duplicate_canonical_keys: set[OutcomeJoinKey] = set()
    plan_id_counts: Counter[str] = Counter()
    missing_canonical_key_rows = 0

    for rec in records:
        plan_id = str(rec.get('plan_id') or '')
        if plan_id:
            plan_id_counts[plan_id] += 1

        key = canonical_outcome_key(rec)
        if key is None:
            missing_canonical_key_rows += 1
            continue

        if key in canonical_index:
            duplicate_canonical_keys.add(key)
            continue
        if key in duplicate_canonical_keys:
            continue
        canonical_index[key] = rec

    for key in duplicate_canonical_keys:
        canonical_index.pop(key, None)

    return OutcomeIndexBuildResult(
        canonical_index=canonical_index,
        duplicate_canonical_keys=duplicate_canonical_keys,
        missing_canonical_key_rows=missing_canonical_key_rows,
        duplicate_plan_id_count=sum(
            1 for count in plan_id_counts.values() if count > 1),
    )


def discover_artifacts(root: Path) -> Dict[str, List[Path]]:
    """Discover policy cortex, verdict, shadow, simulator artifacts."""
    artifacts = {
        'policy_cortex': [],
        'verdict': [],
        'shadow_entry_plan': [],
        'simulation_results': [],
    }

    logs_dir = root / 'logs' / 'judge_experts'
    if logs_dir.exists():
        artifacts['policy_cortex'] = sorted(
            logs_dir.glob('policy_cortex_*.jsonl'))
        artifacts['verdict'] = sorted(logs_dir.glob('verdict_*.jsonl'))
        artifacts['shadow_entry_plan'] = sorted(
            logs_dir.glob('shadow_entry_plan_*.jsonl'))
        artifacts['simulation_results'] = sorted(
            logs_dir.glob('shadow_simulation_*.jsonl'))

    reports_dir = root / 'reports' / 'alpha_search'
    if reports_dir.exists():
        artifacts['simulation_results'].extend(
            sorted(reports_dir.glob('*simulation*.jsonl')))

    return artifacts


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file."""
    records = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        f"Malformed JSON in {path.name}: {line[:100]}")
    except Exception as e:
        logger.error(f"Failed to read {path}: {e}")

    return records


def build_policy_index(artifacts: Dict[str, List[Path]]) -> Tuple[Dict[str, Dict], int]:
    """Load policy cortex records keyed by cycle_key."""
    policy_index = {}
    total_records = 0

    logger.info(
        f"Loading policy cortex ({len(artifacts['policy_cortex'])} files)...")
    for fpath in artifacts['policy_cortex']:
        records = load_jsonl(fpath)
        total_records += len(records)
        for rec in records:
            key = rec.get('cycle_key')
            if key:
                policy_index[key] = rec

    logger.info(
        f"  Loaded {total_records} policy records, {len(policy_index)} unique keys")
    return policy_index, total_records


def build_verdict_index(artifacts: Dict[str, List[Path]]) -> Tuple[Dict[str, Dict], int]:
    """Load verdict records keyed by cycle_key."""
    verdict_index = {}
    total_records = 0

    logger.info(f"Loading verdicts ({len(artifacts['verdict'])} files)...")
    for fpath in artifacts['verdict']:
        records = load_jsonl(fpath)
        total_records += len(records)
        for rec in records:
            key = rec.get('cycle_key')
            if key:
                verdict_index[key] = rec

    logger.info(
        f"  Loaded {total_records} verdict records, {len(verdict_index)} unique keys")
    return verdict_index, total_records


def build_shadow_index(artifacts: Dict[str, List[Path]]) -> Tuple[Dict[str, List[Dict]], int]:
    """Load shadow entry plans keyed by cycle_key, returns multiple plans per key."""
    shadow_index = defaultdict(list)
    total_records = 0

    logger.info(
        f"Loading shadow plans ({len(artifacts['shadow_entry_plan'])} files)...")
    for fpath in artifacts['shadow_entry_plan']:
        records = load_jsonl(fpath)
        total_records += len(records)
        for rec in records:
            key = rec.get('cycle_key')
            if key:
                shadow_index[key].append(rec)

    logger.info(
        f"  Loaded {total_records} shadow plan records, {len(shadow_index)} unique cycles")
    return dict(shadow_index), total_records


def build_outcome_index(artifacts: Dict[str, List[Path]]) -> Tuple[OutcomeIndexBuildResult, int]:
    """Load simulation outcomes keyed canonically by cycle_key+tier."""
    total_records = 0
    outcome_rows: List[Dict[str, Any]] = []

    if not artifacts['simulation_results']:
        logger.info("No simulation results found")
        return build_outcome_index_from_records([]), 0

    logger.info(
        f"Loading simulation outcomes ({len(artifacts['simulation_results'])} files)...")
    for fpath in artifacts['simulation_results']:
        records = load_jsonl(fpath)
        total_records += len(records)
        outcome_rows.extend(records)

    outcome_index = build_outcome_index_from_records(outcome_rows)

    logger.info(
        f"  Loaded {total_records} outcome records, {len(outcome_index.canonical_index)} canonical outcome keys")
    logger.info("  Canonical outcome join: cycle_key+tier")
    logger.info("  plan_id usage: diagnostics_only")
    if outcome_index.missing_canonical_key_rows > 0:
        logger.warning(
            f"  Ignored {outcome_index.missing_canonical_key_rows} outcome rows missing cycle_key+tier")
    if outcome_index.duplicate_canonical_keys:
        logger.warning(
            f"  Duplicate canonical outcome keys detected: {len(outcome_index.duplicate_canonical_keys)}")
    if outcome_index.duplicate_plan_id_count > 0:
        logger.info(
            f"  Duplicate plan_id values retained as diagnostics only: {outcome_index.duplicate_plan_id_count}")
    return outcome_index, total_records


def build_joined_dataset(
    policy_index: Dict[str, Dict],
    verdict_index: Dict[str, Dict],
    shadow_index: Dict[str, List[Dict]],
    outcome_index: OutcomeIndexBuildResult,
) -> Tuple[List[Dict[str, Any]], JoinMetrics]:
    """Build one row per shadow plan tier, joined with policy/verdict/outcome."""

    rows = []
    metrics = JoinMetrics(
        policy_records_total=len(policy_index),
        verdict_records_total=len(verdict_index),
        shadow_plan_records_total=sum(len(v) for v in shadow_index.values()),
        policy_keys_unique=len(policy_index),
        verdict_keys_unique=len(verdict_index),
        shadow_keys_unique=len(shadow_index),
    )

    policy_verdict_joined = 0
    policy_shadow_joined = 0
    metrics.duplicate_canonical_outcome_key_count = len(
        outcome_index.duplicate_canonical_keys)
    metrics.missing_canonical_outcome_key_rows = outcome_index.missing_canonical_key_rows
    metrics.duplicate_plan_id_count = outcome_index.duplicate_plan_id_count

    logger.info("Building joined dataset...")

    for cycle_key, policy_rec in policy_index.items():
        # Join verdict
        verdict_rec = verdict_index.get(cycle_key)
        if verdict_rec:
            policy_verdict_joined += 1

        # Join shadow plans
        shadow_plans = shadow_index.get(cycle_key, [])
        if shadow_plans:
            policy_shadow_joined += 1
        else:
            logger.warning(f"Policy key {cycle_key} has no shadow plans")
            continue

        for shadow_plan in shadow_plans:
            tier = shadow_plan.get(
                'confidence_tier') or shadow_plan.get('tier')
            row = {
                'cycle_key': cycle_key,
                'verdict_id': verdict_rec.get('verdict_id') if verdict_rec else None,
                'plan_id': shadow_plan.get('plan_id'),

                # Identity fields
                'symbol': policy_rec.get('symbol'),
                'side': policy_rec.get('side'),
                'tf_sec': policy_rec.get('tf_sec'),
                'ts_ms': policy_rec.get('ts_ms'),
                'regime': policy_rec.get('regime'),
                'strategy_id': policy_rec.get('strategy_id'),

                # Policy Cortex fields
                'surface_key': policy_rec.get('surface_key'),
                'matched_surface_label': policy_rec.get('matched_surface_label'),
                'classifier_output': policy_rec.get('classifier_output'),
                'final_shadow_policy': policy_rec.get('final_shadow_policy'),
                'reason_codes': policy_rec.get('reason_codes'),
                'sample_size': policy_rec.get('sample_size'),
                'authority_mode': policy_rec.get('authority_mode'),
                'applied': policy_rec.get('applied'),
                'advisory': policy_rec.get('advisory'),
                'production_authority': policy_rec.get('production_authority'),

                # Verdict fields
                'entry_verdict': verdict_rec.get('entry_verdict') if verdict_rec else None,
                'confidence': verdict_rec.get('confidence') if verdict_rec else None,
                'suppression_reason': verdict_rec.get('suppression_reason') if verdict_rec else None,

                # Shadow Plan fields
                'tier': tier,
                'actionable': shadow_plan.get('actionable'),
                'entry_price_ref': shadow_plan.get('entry_price_ref'),
                'limit_price': shadow_plan.get('limit_price'),
                'tp_price': shadow_plan.get('tp_price'),
                'sl_price': shadow_plan.get('sl_price'),
                'tp_offset_pct': shadow_plan.get('tp_offset_pct'),
                'sl_offset_pct': shadow_plan.get('sl_offset_pct'),
                'risk_reward': shadow_plan.get('risk_reward'),
                'canonical_outcome_join': metrics.canonical_outcome_join,
                'plan_id_usage': metrics.plan_id_usage,
                'outcome_join_warning': None,

                # Outcome fields (from simulator)
                'outcome_available': False,
                'outcome': None,
                'outcome_reason': None,
                'fill_ts_ms': None,
                'fill_price': None,
                'exit_ts_ms': None,
                'exit_price': None,
                'gross_pnl_pct': None,
                'net_pnl_pct': None,
                'fees_paid_pct': None,
            }

            join_key = canonical_outcome_key(
                {'cycle_key': cycle_key, 'tier': tier})
            if join_key is None:
                row['outcome_join_warning'] = 'missing_cycle_key_or_tier'
                metrics.rows_without_outcome += 1
                metrics.invalid_outcome_count += 1
            elif join_key in outcome_index.duplicate_canonical_keys:
                row['outcome_join_warning'] = 'duplicate_cycle_key_tier_in_outcomes'
                metrics.rows_without_outcome += 1
                metrics.invalid_outcome_count += 1
                metrics.outcome_join_integrity_error_count += 1
            else:
                outcome = outcome_index.canonical_index.get(join_key)
                if outcome is None:
                    row['outcome_join_warning'] = 'no_canonical_outcome_match'
                    metrics.rows_without_outcome += 1
                else:
                    row['outcome_available'] = True
                    row['outcome'] = outcome.get('outcome')
                    row['outcome_reason'] = outcome.get('outcome_reason')
                    row['fill_ts_ms'] = outcome.get('fill_ts_ms')
                    row['fill_price'] = outcome.get('fill_price')
                    row['exit_ts_ms'] = outcome.get('exit_ts_ms')
                    row['exit_price'] = outcome.get('exit_price')
                    row['gross_pnl_pct'] = outcome.get('gross_pnl_pct')
                    row['net_pnl_pct'] = outcome.get('net_pnl_pct')
                    row['fees_paid_pct'] = outcome.get('fees_paid_pct')
                    metrics.rows_with_outcome += 1

            rows.append(row)

    # Compute metrics
    if len(policy_index) > 0:
        metrics.policy_verdict_join_rate_pct = (
            policy_verdict_joined / len(policy_index)) * 100
        metrics.policy_shadow_join_rate_pct = (
            policy_shadow_joined / len(policy_index)) * 100

    if metrics.shadow_plan_records_total > 0:
        metrics.shadow_outcome_join_rate_pct = (
            metrics.rows_with_outcome / len(rows)) * 100 if rows else 0.0

    logger.info(f"Joined dataset: {len(rows)} rows")
    logger.info(
        f"  Policy ↔ Verdict join: {policy_verdict_joined}/{len(policy_index)} ({metrics.policy_verdict_join_rate_pct:.1f}%)")
    logger.info(
        f"  Policy ↔ Shadow join: {policy_shadow_joined}/{len(policy_index)} ({metrics.policy_shadow_join_rate_pct:.1f}%)")
    logger.info(
        f"  Shadow ↔ Outcome join: {metrics.rows_with_outcome}/{len(rows)} ({metrics.shadow_outcome_join_rate_pct:.1f}%)")
    logger.info(
        f"  Canonical outcome join: {metrics.canonical_outcome_join}; plan_id usage: {metrics.plan_id_usage}")

    return rows, metrics


def save_csv(rows: List[Dict[str, Any]], output_path: Path) -> None:
    """Save joined dataset as CSV."""
    if not rows:
        logger.warning(f"No rows to write to {output_path}")
        return

    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Wrote CSV: {output_path} ({len(rows)} rows)")
    except Exception as e:
        logger.error(f"Failed to write CSV {output_path}: {e}")


def save_jsonl(rows: List[Dict[str, Any]], output_path: Path) -> None:
    """Save joined dataset as JSONL."""
    if not rows:
        logger.warning(f"No rows to write to {output_path}")
        return

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps(row) + '\n')
        logger.info(f"Wrote JSONL: {output_path} ({len(rows)} rows)")
    except Exception as e:
        logger.error(f"Failed to write JSONL {output_path}: {e}")


def save_metrics_json(metrics: JoinMetrics, output_path: Path) -> None:
    """Save metrics as JSON."""
    try:
        with open(output_path, 'w') as f:
            json.dump(asdict(metrics), f, indent=2)
        logger.info(f"Wrote metrics: {output_path}")
    except Exception as e:
        logger.error(f"Failed to write metrics {output_path}: {e}")


def main(root: str = 'c:\\Users\\user\\Music\\Phenix') -> int:
    root_path = Path(root)
    if not root_path.exists():
        logger.error(f"Root path not found: {root_path}")
        return 1

    logger.info(f"J6-S17-B Forward Outcome Join Dataset Builder")
    logger.info(f"Root: {root_path}")

    # Discover artifacts
    logger.info("\n=== ARTIFACT DISCOVERY ===")
    artifacts = discover_artifacts(root_path)

    for artifact_type, paths in artifacts.items():
        logger.info(f"{artifact_type}: {len(paths)} files")

    # Check if we have required inputs
    if not artifacts['policy_cortex']:
        logger.error("No policy cortex artifacts found")
        return 1
    if not artifacts['verdict']:
        logger.error("No verdict artifacts found")
        return 1
    if not artifacts['shadow_entry_plan']:
        logger.error("No shadow entry plan artifacts found")
        return 1

    # Load data
    logger.info("\n=== DATA LOADING ===")
    policy_index, policy_total = build_policy_index(artifacts)
    verdict_index, verdict_total = build_verdict_index(artifacts)
    shadow_index, shadow_total = build_shadow_index(artifacts)
    outcome_index, outcome_total = build_outcome_index(artifacts)

    logger.info(
        f"\nOutcome artifacts: {outcome_total} records in {len(outcome_index)} keys")
    if outcome_total == 0:
        logger.warning(
            "No simulation outcomes found — dataset will have empty outcome fields")

    # Build joined dataset
    logger.info("\n=== JOIN OPERATION ===")
    rows, metrics = build_joined_dataset(
        policy_index, verdict_index, shadow_index, outcome_index)

    # Save outputs
    logger.info("\n=== WRITE OUTPUTS ===")
    reports_dir = root_path / 'reports' / 'alpha_search'
    reports_dir.mkdir(parents=True, exist_ok=True)

    save_csv(rows, reports_dir / 'j6_s17_b_joined_policy_outcome_dataset.csv')
    save_jsonl(rows, reports_dir /
               'j6_s17_b_joined_policy_outcome_dataset.jsonl')
    save_metrics_json(metrics, reports_dir /
                      'j6_s17_b_outcome_join_metrics.json')

    # Write artifact inventory
    inventory = {
        'timestamp': __import__('datetime').datetime.utcnow().isoformat(),
        'policy_cortex_files': len(artifacts['policy_cortex']),
        'verdict_files': len(artifacts['verdict']),
        'shadow_entry_plan_files': len(artifacts['shadow_entry_plan']),
        'simulation_result_files': len(artifacts['simulation_results']),
    }
    with open(reports_dir / 'j6_s17_b_outcome_artifact_inventory.json', 'w') as f:
        json.dump(inventory, f, indent=2)
    logger.info(
        f"Wrote artifact inventory: {reports_dir / 'j6_s17_b_outcome_artifact_inventory.json'}")

    logger.info("\n=== SUMMARY ===")
    logger.info(f"Policy records: {metrics.policy_records_total}")
    logger.info(f"Verdict records: {metrics.verdict_records_total}")
    logger.info(f"Shadow plan records: {metrics.shadow_plan_records_total}")
    logger.info(f"Joined rows: {len(rows)}")
    logger.info(
        f"Rows with outcome: {metrics.rows_with_outcome} ({metrics.shadow_outcome_join_rate_pct:.1f}%)")
    logger.info(f"Rows without outcome: {metrics.rows_without_outcome}")

    logger.info("\nJ6-S17-B complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
