#!/usr/bin/env python3
"""
J6-S17-A Policy Cortex Forward Telemetry Preflight Audit

Read-only preflight validation of Policy Cortex telemetry before forward outcome join.

Outputs:
  - reports/alpha_search/j6_s17_a_policy_cortex_inventory.json
  - reports/alpha_search/j6_s17_a_policy_cortex_validation_summary.json
  - reports/alpha_search/j6_s17_a_policy_shadow_join_readiness.json
  - reports/alpha_search/j6_s17_a_policy_verdict_join_readiness.json
  - reports/alpha_search/j6_s17_a_unknown_diagnosis.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Expected repo root
REPO_ROOT = Path(__file__).parent.parent.parent


def discover_policy_cortex_files(root: Path) -> List[Path]:
    """Discover all policy_cortex_*.jsonl files under logs/judge_experts/"""
    base = root / "logs" / "judge_experts"
    if not base.exists():
        return []
    return sorted(base.glob("policy_cortex_*.jsonl"))


def discover_shadow_entry_plan_files(root: Path) -> List[Path]:
    """Discover all shadow_entry_plan_*.jsonl files."""
    base = root / "logs" / "judge_experts"
    if not base.exists():
        return []
    return sorted(base.glob("shadow_entry_plan_*.jsonl"))


def discover_verdict_files(root: Path) -> List[Path]:
    """Discover all verdict_*.jsonl files."""
    base = root / "logs" / "judge_experts"
    if not base.exists():
        return []
    return sorted(base.glob("verdict_*.jsonl"))


def count_jsonl_lines(path: Path) -> Tuple[int, int, int]:
    """Count valid, empty, and malformed lines in JSONL file.

    Returns:
        (valid_count, empty_count, malformed_count)
    """
    valid = 0
    empty = 0
    malformed = 0
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    empty += 1
                else:
                    try:
                        json.loads(line)
                        valid += 1
                    except (json.JSONDecodeError, ValueError):
                        malformed += 1
    except Exception as e:
        print(f"ERROR reading {path}: {e}", file=sys.stderr)
        return 0, 0, 0
    return valid, empty, malformed


def analyze_policy_cortex_files(
    files: List[Path],
) -> Dict[str, Any]:
    """Analyze all policy cortex files.

    Returns inventory and validation stats.
    """
    inventory: Dict[str, Any] = {
        "artifact_family": "policy_cortex_annotation_v1",
        "file_count": len(files),
        "total_records": 0,
        "total_valid": 0,
        "total_invalid": 0,
        "total_empty_lines": 0,
        "total_malformed_json": 0,
        "records_by_symbol": defaultdict(int),
        "records_by_date": defaultdict(int),
        "validation_summary": {
            "schema_valid_count": 0,
            "schema_invalid_count": 0,
            "invalid_reason_counts": defaultdict(int),
            "invalid_examples": [],
        },
        "cycle_key_analysis": {
            "total_records": 0,
            "with_cycle_key": 0,
            "without_cycle_key": 0,
            "null_cycle_key": 0,
            "empty_cycle_key": 0,
            "malformed_cycle_key": 0,
            "unique_cycle_keys": set(),
            "duplicate_cycle_keys": defaultdict(int),
            "examples_missing": [],
            "examples_duplicate": [],
            "examples_malformed": [],
        },
        "classifier_output_distribution": defaultdict(int),
        "final_shadow_policy_distribution": defaultdict(int),
        "matched_surface_label_distribution": defaultdict(int),
        "unknown_diagnosis": {
            "total_unknown": 0,
            "reason_code_distribution": defaultdict(int),
            "regime_distribution": defaultdict(int),
            "symbol_distribution": defaultdict(int),
            "side_distribution": defaultdict(int),
            "tf_sec_distribution": defaultdict(int),
            "surface_key_examples": [],
        },
        "files_analyzed": [],
    }

    all_cycle_keys = []
    SAMPLE_LIMIT = 10

    for fidx, fpath in enumerate(files):
        file_info = {
            "path": str(fpath),
            "size_bytes": fpath.stat().st_size if fpath.exists() else 0,
        }

        valid, empty, malformed = count_jsonl_lines(fpath)
        file_info["valid_lines"] = valid
        file_info["empty_lines"] = empty
        file_info["malformed_lines"] = malformed

        inventory["total_records"] += valid
        inventory["total_empty_lines"] += empty
        inventory["total_malformed_json"] += malformed
        inventory["files_analyzed"].append(file_info)

        # Extract symbol and date from filename
        # Pattern: policy_cortex_{SYMBOL}_{DATE}.jsonl
        parts = fpath.stem.split("_")
        if len(parts) >= 4:
            symbol = parts[2]
            date_str = parts[3]
            inventory["records_by_symbol"][symbol] += valid
            inventory["records_by_date"][date_str] += valid

        # Parse records
        try:
            with open(fpath) as f:
                line_num = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    line_num += 1

                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    # Quick schema check (no full validation)
                    required = {"symbol", "tf_sec", "surface_key",
                                "classifier_output", "reason_codes", "final_shadow_policy"}
                    if all(k in record for k in required):
                        inventory["validation_summary"]["schema_valid_count"] += 1
                    else:
                        inventory["validation_summary"]["schema_invalid_count"] += 1
                        missing = required - set(record.keys())
                        reason = f"missing:{','.join(missing)}"
                        inventory["validation_summary"]["invalid_reason_counts"][reason] += 1
                        if len(inventory["validation_summary"]["invalid_examples"]) < SAMPLE_LIMIT:
                            inventory["validation_summary"]["invalid_examples"].append({
                                "file": str(fpath),
                                "line": line_num,
                                "reason": reason,
                            })

                    # Analyze cycle_key
                    cycle_key_stats = inventory["cycle_key_analysis"]
                    cycle_key_stats["total_records"] += 1

                    cycle_key = record.get("cycle_key")
                    if cycle_key is not None and cycle_key != "":
                        cycle_key_stats["with_cycle_key"] += 1
                        cycle_key_stats["unique_cycle_keys"].add(cycle_key)
                        cycle_key_stats["duplicate_cycle_keys"][cycle_key] += 1
                    elif cycle_key is None:
                        cycle_key_stats["null_cycle_key"] += 1
                        if len(cycle_key_stats["examples_missing"]) < SAMPLE_LIMIT:
                            cycle_key_stats["examples_missing"].append({
                                "symbol": record.get("symbol"),
                                "side": record.get("side"),
                            })
                    elif cycle_key == "":
                        cycle_key_stats["empty_cycle_key"] += 1

                    # Classifier output distribution
                    classifier_out = record.get("classifier_output", "MISSING")
                    inventory["classifier_output_distribution"][classifier_out] += 1

                    final_policy = record.get("final_shadow_policy", "MISSING")
                    inventory["final_shadow_policy_distribution"][final_policy] += 1

                    matched_label = record.get("matched_surface_label")
                    inventory["matched_surface_label_distribution"][matched_label] += 1

                    # UNKNOWN diagnosis
                    if classifier_out == "UNKNOWN" or final_policy == "UNKNOWN":
                        unknown_stats = inventory["unknown_diagnosis"]
                        unknown_stats["total_unknown"] += 1

                        reason_codes = record.get("reason_codes", [])
                        for code in reason_codes:
                            unknown_stats["reason_code_distribution"][code] += 1

                        if record.get("regime"):
                            unknown_stats["regime_distribution"][record["regime"]] += 1
                        if record.get("symbol"):
                            unknown_stats["symbol_distribution"][record["symbol"]] += 1
                        if record.get("side"):
                            unknown_stats["side_distribution"][record["side"]] += 1
                        if record.get("tf_sec"):
                            unknown_stats["tf_sec_distribution"][record["tf_sec"]] += 1

                        if len(unknown_stats["surface_key_examples"]) < SAMPLE_LIMIT:
                            unknown_stats["surface_key_examples"].append({
                                "surface_key": record.get("surface_key"),
                                "matched_label": matched_label,
                                "classifier_output": classifier_out,
                            })
        except Exception as e:
            print(f"ERROR parsing {fpath}: {e}", file=sys.stderr)

        # Progress checkpoint
        if (fidx + 1) % 10 == 0:
            print(f"  Processed {fidx + 1}/{len(files)} files...")

    # Convert sets and defaultdicts to serializable form
    inventory["cycle_key_analysis"]["unique_cycle_keys"] = len(
        inventory["cycle_key_analysis"]["unique_cycle_keys"])
    inventory["cycle_key_analysis"]["duplicate_cycle_keys"] = dict(
        (k, v) for k, v in inventory["cycle_key_analysis"]["duplicate_cycle_keys"].items() if v > 1
    )

    inventory["records_by_symbol"] = dict(inventory["records_by_symbol"])
    inventory["records_by_date"] = dict(inventory["records_by_date"])
    inventory["classifier_output_distribution"] = dict(
        inventory["classifier_output_distribution"])
    inventory["final_shadow_policy_distribution"] = dict(
        inventory["final_shadow_policy_distribution"])
    inventory["matched_surface_label_distribution"] = dict(
        inventory["matched_surface_label_distribution"])
    inventory["validation_summary"]["invalid_reason_counts"] = dict(
        inventory["validation_summary"]["invalid_reason_counts"]
    )
    inventory["unknown_diagnosis"]["reason_code_distribution"] = dict(
        inventory["unknown_diagnosis"]["reason_code_distribution"]
    )
    inventory["unknown_diagnosis"]["regime_distribution"] = dict(
        inventory["unknown_diagnosis"]["regime_distribution"]
    )
    inventory["unknown_diagnosis"]["symbol_distribution"] = dict(
        inventory["unknown_diagnosis"]["symbol_distribution"]
    )
    inventory["unknown_diagnosis"]["side_distribution"] = dict(
        inventory["unknown_diagnosis"]["side_distribution"]
    )
    inventory["unknown_diagnosis"]["tf_sec_distribution"] = dict(
        inventory["unknown_diagnosis"]["tf_sec_distribution"]
    )

    return inventory


def analyze_join_readiness(
    policy_files: List[Path],
    shadow_files: List[Path],
    verdict_files: List[Path],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Analyze join readiness between policy cortex and shadow plans/verdicts.

    Returns:
        (policy_shadow_join_stats, policy_verdict_join_stats)
    """

    def load_cycle_keys(files: List[Path]) -> Dict[str, int]:
        """Load cycle keys from JSONL files."""
        keys: Dict[str, int] = defaultdict(int)
        for fpath in files:
            try:
                with open(fpath) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            cycle_key = record.get("cycle_key")
                            if cycle_key:
                                keys[cycle_key] += 1
                        except (json.JSONDecodeError, ValueError):
                            pass
            except Exception:
                pass
        return keys

    print("  Loading policy cycle keys...")
    policy_cycle_keys = load_cycle_keys(policy_files)
    policy_records_total = sum(policy_cycle_keys.values())

    print("  Loading shadow plan cycle keys...")
    shadow_cycle_keys = load_cycle_keys(shadow_files)
    shadow_records_total = sum(shadow_cycle_keys.values())

    print("  Loading verdict cycle keys...")
    verdict_cycle_keys = load_cycle_keys(verdict_files)
    verdict_records_total = sum(verdict_cycle_keys.values())

    # Compute policy ↔ shadow
    policy_shadow_stats: Dict[str, Any] = {
        "policy_records_total": policy_records_total,
        "shadow_plan_records_total": shadow_records_total,
        "policy_cycle_keys_unique": len(policy_cycle_keys),
        "shadow_plan_cycle_keys_unique": len(shadow_cycle_keys),
        "policy_keys_joined_to_any_shadow_plan": 0,
        "policy_to_shadow_join_rate_pct": 0.0,
        "avg_shadow_plans_per_joined_cycle": 0.0,
        "max_shadow_plans_per_cycle": 0,
        "unjoined_policy_keys": 0,
        "unjoined_shadow_keys": 0,
    }

    joined_count = 0
    shadow_counts = []
    max_shadow = 0

    for policy_key in policy_cycle_keys.keys():
        if policy_key in shadow_cycle_keys:
            joined_count += 1
            shadow_count = shadow_cycle_keys[policy_key]
            shadow_counts.append(shadow_count)
            if shadow_count > max_shadow:
                max_shadow = shadow_count

    policy_shadow_stats["policy_keys_joined_to_any_shadow_plan"] = joined_count
    if len(policy_cycle_keys) > 0:
        policy_shadow_stats["policy_to_shadow_join_rate_pct"] = (
            joined_count / len(policy_cycle_keys) * 100)
    if shadow_counts:
        policy_shadow_stats["avg_shadow_plans_per_joined_cycle"] = sum(
            shadow_counts) / len(shadow_counts)
    policy_shadow_stats["max_shadow_plans_per_cycle"] = max_shadow
    policy_shadow_stats["unjoined_policy_keys"] = len(
        policy_cycle_keys) - joined_count
    policy_shadow_stats["unjoined_shadow_keys"] = len(
        shadow_cycle_keys) - joined_count

    # Compute policy ↔ verdict
    policy_verdict_stats: Dict[str, Any] = {
        "policy_records_total": policy_records_total,
        "verdict_records_total": verdict_records_total,
        "policy_cycle_keys_unique": len(policy_cycle_keys),
        "verdict_cycle_keys_unique": len(verdict_cycle_keys),
        "policy_keys_joined_to_verdict": 0,
        "policy_to_verdict_join_rate_pct": 0.0,
        "unjoined_policy_keys": 0,
        "unjoined_verdict_keys": 0,
    }

    joined_count_v = 0
    for policy_key in policy_cycle_keys.keys():
        if policy_key in verdict_cycle_keys:
            joined_count_v += 1

    policy_verdict_stats["policy_keys_joined_to_verdict"] = joined_count_v
    if len(policy_cycle_keys) > 0:
        policy_verdict_stats["policy_to_verdict_join_rate_pct"] = (
            joined_count_v / len(policy_cycle_keys) * 100)
    policy_verdict_stats["unjoined_policy_keys"] = len(
        policy_cycle_keys) - joined_count_v
    policy_verdict_stats["unjoined_verdict_keys"] = len(
        verdict_cycle_keys) - joined_count_v

    return policy_shadow_stats, policy_verdict_stats


def main(root: Optional[Path] = None) -> int:
    """Run the preflight audit."""
    if root is None:
        root = REPO_ROOT

    print(f"J6-S17-A Policy Cortex Preflight Audit")
    print(f"Repo root: {root}")
    print()

    # Discover files
    print("Discovering artifacts...")
    policy_files = discover_policy_cortex_files(root)
    shadow_files = discover_shadow_entry_plan_files(root)
    verdict_files = discover_verdict_files(root)

    print(f"  Policy cortex files: {len(policy_files)}")
    print(f"  Shadow entry plan files: {len(shadow_files)}")
    print(f"  Verdict files: {len(verdict_files)}")
    print()

    # Analyze policy cortex files
    print("Analyzing policy cortex files...")
    policy_inventory = analyze_policy_cortex_files(policy_files)
    print(f"  Total records: {policy_inventory['total_records']}")
    print(
        f"  Valid: {policy_inventory['validation_summary']['schema_valid_count']}")
    print(
        f"  Invalid: {policy_inventory['validation_summary']['schema_invalid_count']}")
    print()

    # Analyze join readiness
    print("Analyzing join readiness...")
    shadow_join, verdict_join = analyze_join_readiness(
        policy_files, shadow_files, verdict_files)
    print(
        f"  Policy → Shadow join rate: {shadow_join['policy_to_shadow_join_rate_pct']:.1f}%")
    print(
        f"  Policy → Verdict join rate: {verdict_join['policy_to_verdict_join_rate_pct']:.1f}%")
    print()

    # Write outputs
    output_dir = root / "reports" / "alpha_search"
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = [
        (
            "j6_s17_a_policy_cortex_inventory.json",
            {
                "artifact_family": policy_inventory["artifact_family"],
                "file_count": policy_inventory["file_count"],
                "total_records": policy_inventory["total_records"],
                "total_valid": policy_inventory["validation_summary"]["schema_valid_count"],
                "total_invalid": policy_inventory["validation_summary"]["schema_invalid_count"],
                "total_empty_lines": policy_inventory["total_empty_lines"],
                "total_malformed_json": policy_inventory["total_malformed_json"],
                "records_by_symbol": policy_inventory["records_by_symbol"],
                "records_by_date": policy_inventory["records_by_date"],
                "files_analyzed": policy_inventory["files_analyzed"],
            },
        ),
        (
            "j6_s17_a_policy_cortex_validation_summary.json",
            policy_inventory["validation_summary"],
        ),
        (
            "j6_s17_a_policy_shadow_join_readiness.json",
            shadow_join,
        ),
        (
            "j6_s17_a_policy_verdict_join_readiness.json",
            verdict_join,
        ),
        (
            "j6_s17_a_unknown_diagnosis.json",
            policy_inventory["unknown_diagnosis"],
        ),
        (
            "j6_s17_a_cycle_key_analysis.json",
            policy_inventory["cycle_key_analysis"],
        ),
        (
            "j6_s17_a_classifier_distribution.json",
            {
                "classifier_output_distribution": policy_inventory["classifier_output_distribution"],
                "final_shadow_policy_distribution": policy_inventory["final_shadow_policy_distribution"],
                "matched_surface_label_distribution": policy_inventory["matched_surface_label_distribution"],
            },
        ),
    ]

    for filename, data in outputs:
        filepath = output_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✓ {filepath}")

    print()
    print("Preflight audit complete.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="J6-S17-A Policy Cortex Forward Telemetry Preflight"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: detected)",
    )
    args = parser.parse_args()
    sys.exit(main(args.root))
