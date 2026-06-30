#!/usr/bin/env python3
import os
import sys
import json
import shutil
import hashlib
import glob
from pathlib import Path
from datetime import datetime, timezone

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def extract_timestamps_jsonl(path: Path):
    first_ts = None
    last_ts = None
    malformed = 0
    parsed_rows = 0
    raw_lines = 0
    
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            raw_lines += 1
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                parsed_rows += 1
                
                # Check for timestamp
                ts = None
                for key in ["ts_ms", "updated_ts_ms", "timestamp", "time", "close_ts_ms"]:
                    val = obj.get(key)
                    if val is not None:
                        try:
                            ts = int(val)
                            break
                        except (ValueError, TypeError):
                            # Try float conversion (e.g. float timestamp in seconds or ms)
                            try:
                                ts = int(float(val))
                                break
                            except (ValueError, TypeError):
                                continue
                
                if ts is not None:
                    # Sanity check: if ts is in seconds (e.g. ~1.7e9), convert to ms
                    if ts < 10000000000:
                        ts = ts * 1000
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
            except Exception:
                malformed += 1
                
    return first_ts, last_ts, parsed_rows, malformed, raw_lines

def analyze_file(source_path: Path, frozen_path: Path, copy_time_utc: str):
    size_bytes = source_path.stat().st_size
    mtime = datetime.fromtimestamp(source_path.stat().st_mtime, tz=timezone.utc).isoformat()
    sha = sha256_file(frozen_path)
    
    is_jsonl = source_path.suffix.lower() == ".jsonl" or "jsonl" in source_path.name.lower()
    first_ts_ms = None
    last_ts_ms = None
    raw_line_count = 0
    parsed_rows = 0
    malformed_rows = 0
    timestamp_coverage_status = "unknown"
    
    if is_jsonl:
        first_ts_ms, last_ts_ms, parsed_rows, malformed_rows, raw_line_count = extract_timestamps_jsonl(frozen_path)
        timestamp_coverage_status = "present" if first_ts_ms is not None else "missing"
    else:
        # For non-jsonl text files, get line count
        try:
            with frozen_path.open("r", encoding="utf-8", errors="replace") as f:
                raw_line_count = sum(1 for _ in f)
            timestamp_coverage_status = "n/a"
        except Exception:
            raw_line_count = 0
            timestamp_coverage_status = "binary_or_unreadable"
            
    return {
        "original_path": str(source_path.resolve()),
        "frozen_path": str(frozen_path.resolve()),
        "size_bytes": size_bytes,
        "modified_time": mtime,
        "raw_line_count": raw_line_count,
        "parseable_json_rows": parsed_rows if is_jsonl else None,
        "malformed_rows": malformed_rows if is_jsonl else None,
        "sha256": sha,
        "first_ts_ms": first_ts_ms,
        "last_ts_ms": last_ts_ms,
        "copy_time_utc": copy_time_utc,
        "timestamp_coverage_status": timestamp_coverage_status
    }

def main():
    repo_root = Path("C:/Users/wekab/Music/Phenix").resolve()
    utc_now = datetime.now(timezone.utc)
    timestamp_str = utc_now.strftime("%Y%m%d_%H%M%SZ")
    bundle_name = f"sidecar_current_state_reset_{timestamp_str}"
    bundle_dir = repo_root / "frozen" / bundle_name
    bundle_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating frozen bundle: {bundle_dir}")
    
    # 1. Logs
    logs_to_copy = [
        "logs/trade_lifecycle.jsonl",
        "logs/order_log_v1.jsonl",
        "logs/shadow_critical_event_journal_v1.jsonl",
        "logs/execution_lifecycle_stats_v1.jsonl",
        "logs/event_chain.log",
        "logs/regime_confidence_audit_v1.jsonl",
        "logs/shadow_telemetry/decision_ledger_v1.jsonl"
    ]
    
    # Add glob logs
    log_globs = [
        "logs/aurora_core.log*",
        "logs/domain_execution_position.log*",
        "logs/order_guardian.log*",
        "logs/aurora_trades.log*",
        "logs/domain_feature_engineering.log*",
        "logs/domain_decision_making.log*",
        "logs/domain_regime_detector.log*"
    ]
    for pattern in log_globs:
        matched = glob.glob(str(repo_root / pattern))
        for m in matched:
            rel = Path(m).relative_to(repo_root)
            logs_to_copy.append(str(rel))
            
    # 2. Configs
    configs_to_copy = [
        "config/aurora/domains.yaml",
        "config/aurora/trading.yaml",
        "config/aurora/system.yaml",
        "config/aurora/observability.yaml",
        "config/aurora/strategies.yaml",
        "config/aurora/instruments.yaml",
        "config/aurora/regime.yaml",
        "config/aurora/strategies/aurora.yaml",
        "config/aurora/strategies/md_amr.yaml",
        "config/aurora/strategies/mean_reversion.yaml",
        "config/alpha_search.yaml",
        "apps/reference/dictionaries/verb_registry_v1.yaml"
    ]
    
    # 3. Runtime data
    data_to_copy = []
    # recorder recursive
    recorder_files = glob.glob(str(repo_root / "data/recorder/**"), recursive=True)
    for f in recorder_files:
        if os.path.isfile(f):
            rel = Path(f).relative_to(repo_root)
            data_to_copy.append(str(rel))
            
    # reports/
    report_patterns = [
        "reports/*SIDECAR*",
        "reports/*sidecar*",
        "reports/*runtime*"
    ]
    for pattern in report_patterns:
        matched = glob.glob(str(repo_root / pattern))
        for m in matched:
            if os.path.isfile(m):
                rel = Path(m).relative_to(repo_root)
                data_to_copy.append(str(rel))
            elif os.path.isdir(m):
                # add all files in directory
                dir_files = glob.glob(f"{m}/**", recursive=True)
                for df in dir_files:
                    if os.path.isfile(df):
                        rel = Path(df).relative_to(repo_root)
                        data_to_copy.append(str(rel))
                        
    # artifacts/position_policy_sidecar/**
    sidecar_artifacts = glob.glob(str(repo_root / "artifacts/position_policy_sidecar/**"), recursive=True)
    for f in sidecar_artifacts:
        if os.path.isfile(f):
            rel = Path(f).relative_to(repo_root)
            data_to_copy.append(str(rel))
            
    all_targets = logs_to_copy + configs_to_copy + data_to_copy
    
    # Remove duplicates
    all_targets = sorted(list(set(all_targets)))
    
    manifest_files = []
    missing_required = []
    
    copy_time_str = utc_now.isoformat()
    
    for rel_path in all_targets:
        source_file = repo_root / rel_path
        target_file = bundle_dir / rel_path
        
        # Check if it exists
        if not source_file.exists():
            # If it was in the primary requested logs or configs, mark it as missing
            is_required = (rel_path in logs_to_copy or rel_path in configs_to_copy)
            if is_required:
                missing_required.append(rel_path)
            continue
            
        # Copy file
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        
        # Analyze copied file
        metadata = analyze_file(source_file, target_file, copy_time_str)
        metadata["relative_path"] = rel_path
        manifest_files.append(metadata)
        
    # Write MANIFEST.json
    manifest = {
        "bundle_name": bundle_name,
        "frozen_at_utc": copy_time_str,
        "files_copied_count": len(manifest_files),
        "missing_required_files": missing_required,
        "files": manifest_files
    }
    
    manifest_path = bundle_dir / "MANIFEST.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    # Write FREEZE_REPORT.md
    report_lines = [
        f"# Freeze Report: {bundle_name}",
        f"**Frozen At (UTC):** {copy_time_str}",
        "",
        "## Summary",
        f"- Total files copied: {len(manifest_files)}",
        f"- Missing required files: {len(missing_required)}",
        ""
    ]
    
    if missing_required:
        report_lines.extend([
            "### Missing Required Files",
            "The following required files were not found in the live workspace:",
            ""
        ])
        for m in missing_required:
            report_lines.append(f"- `{m}`")
        report_lines.append("")
        
    report_lines.extend([
        "## File Manifest",
        "| File | Size (Bytes) | Lines | JSON Rows | Malformed Rows | SHA256 | Coverage |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    for f in manifest_files:
        rel = f["relative_path"]
        sz = f["size_bytes"]
        lns = f["raw_line_count"]
        p_rows = f["parseable_json_rows"] if f["parseable_json_rows"] is not None else "-"
        m_rows = f["malformed_rows"] if f["malformed_rows"] is not None else "-"
        sha = f["sha256"][:8] + "..."
        cov = f["timestamp_coverage_status"]
        report_lines.append(f"| `{rel}` | {sz} | {lns} | {p_rows} | {m_rows} | `{sha}` | {cov} |")
        
    report_path = bundle_dir / "FREEZE_REPORT.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Freeze complete. Manifest written to {manifest_path}")
    print(f"Freeze report written to {report_path}")
    
    # Return bundle name for the caller to parse
    print(f"BUNDLE_DIR={bundle_dir.resolve().as_posix()}")

if __name__ == "__main__":
    main()
