#!/usr/bin/env python3
"""
Generate LOG ERRORS AUDIT Report from RAW JSON

Reads the aggregated JSON and creates a comprehensive audit markdown report.
Maps each signature to source code and provides analysis.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


def find_source_location(signature: str, logger: str) -> Dict[str, Optional[str]]:
    """
    Find source code location for a log signature using git grep.
    
    Returns dict with: file, line_num, domain, module
    """
    result = {
        "file": None,
        "line_num": None,
        "domain": None,
        "module": None,
        "function": None
    }
    
    # Extract key part of signature for search
    # Remove variable placeholders and search for the core message
    search_term = signature.replace('<ID>', '').replace('<SYMBOL>', '').replace('<NUM>', '').replace('<TIMESTAMP>', '')
    search_term = search_term.strip()
    
    # Try several search patterns
    search_patterns = [
        signature[:50],  # First 50 chars
        search_term[:40],  # Core message
    ]
    
    # Try to extract quoted string or specific error pattern
    if '"' in signature:
        quoted = signature.split('"')[1] if len(signature.split('"')) > 1 else None
        if quoted:
            search_patterns.insert(0, quoted)
    
    if '[' in signature and ']' in signature:
        bracket_content = signature[signature.find('[')+1:signature.find(']')]
        if bracket_content and len(bracket_content) > 3:
            search_patterns.insert(0, bracket_content)
    
    # Perform git grep search
    for pattern in search_patterns:
        if not pattern or len(pattern) < 5:
            continue
            
        try:
            cmd = ['git', 'grep', '-n', '-i', '--', pattern, '*.py']
            output = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                cwd='.',
                timeout=5
            )
            
            if output.returncode == 0 and output.stdout:
                lines = output.stdout.strip().split('\n')
                # Take first match
                first_match = lines[0]
                if ':' in first_match:
                    file_path, line_num, *_ = first_match.split(':', 2)
                    result["file"] = file_path
                    result["line_num"] = line_num
                    
                    # Extract domain from path
                    if 'domains/' in file_path:
                        domain_part = file_path.split('domains/')[1]
                        result["domain"] = domain_part.split('/')[0]
                    
                    # Extract module from logger
                    result["module"] = logger
                    
                    break
        except Exception:
            continue
    
    return result


def assess_risk(signature: str, count: int, level: str) -> str:
    """Assess risk level based on signature content and frequency."""
    sig_lower = signature.lower()
    
    # High risk keywords
    high_risk_keywords = [
        'failed to cancel', 'failed to place', 'state divergence',
        'race condition', 'deadlock', 'corruption', 'critical'
    ]
    
    # Medium risk keywords  
    medium_risk_keywords = [
        'timeout', 'retry', 'failed to apply', 'adapter error',
        'validation failed', 'mismatch', 'unexpected'
    ]
    
    # Check keywords
    if any(kw in sig_lower for kw in high_risk_keywords):
        return "HIGH"
    
    if level == "ERROR":
        if count > 50:
            return "HIGH"
        elif count > 10:
            return "MEDIUM"
        else:
            return "LOW"
    else:  # WARNING
        if any(kw in sig_lower for kw in medium_risk_keywords):
            return "MEDIUM"
        return "LOW"


def classify_status(signature: str, level: str) -> str:
    """Classify whether this is expected, suspicious, or bug candidate."""
    sig_lower = signature.lower()
    
    # Expected patterns
    expected_patterns = [
        'retrying', 'no data', 'skipping', 'waiting',
        'timeout (expected)', 'graceful'
    ]
    
    # Bug candidate patterns
    bug_patterns = [
        'should not happen', 'unexpected state', 'assertion',
        'divergence', 'race', 'corruption', 'invalid'
    ]
    
    if any(p in sig_lower for p in bug_patterns):
        return "BUG_CANDIDATE"
    
    if any(p in sig_lower for p in expected_patterns):
        return "EXPECTED"
    
    return "SUSPICIOUS"


def generate_report(json_path: str, output_path: str):
    """Generate comprehensive audit report from JSON data."""
    
    # Load data
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    errors = data['errors']
    warnings = data['warnings']
    summary = data['summary']
    
    # Start building report
    report_lines = []
    
    # Header
    report_lines.append("# EXEC_R2_LOG_ERRORS_AUDIT")
    report_lines.append("")
    report_lines.append("**Audit Date:** 2025-11-23")
    report_lines.append("**Analystreamer:** Automated Log Analysis Tool")
    report_lines.append("**Scope:** Runtime logs from `logs/` directory")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    
    # Log sources
    report_lines.append("## 1. Джерела логів")
    report_lines.append("")
    report_lines.append("Проаналізовано наступні файли логів:")
    report_lines.append("")
    log_files = [
        "- `logs/aurora_core.log` (7.5 MB)",
        "- `logs/aurora_events.jsonl`",
        "- `logs/domain_decision_making.log`",
        "- `logs/domain_execution_management.log`",
        "- `logs/domain_execution_management.log.1` (5.2 MB)",
        "- `logs/domain_feature_engineering.log`",
        "- `logs/domain_risk_management.log`",
        "- `logs/event_chain.log`",
        "- `logs/execpos_v2_runtime.jsonl`",
        "- `logs/order_guardian.log`",
        "- `logs/order_log_v1.jsonl`",
    ]
    report_lines.extend(log_files)
    report_lines.append("")
    
    # Executive summary
    report_lines.append("## 2. Executive Summary")
    report_lines.append("")
    report_lines.append("### Статистика")
    report_lines.append("")
    report_lines.append(f"- **Total ERROR occurrences:** {summary['total_errors']}")
    report_lines.append(f"- **Unique ERROR signatures:** {summary['unique_error_signatures']}")
    report_lines.append(f"- **Total WARNING occurrences:** {summary['total_warnings']}")
    report_lines.append(f"- **Unique WARNING signatures:** {summary['unique_warning_signatures']}")
    report_lines.append("")
    
    # Top errors
    if errors:
        report_lines.append("### Топ-5 найчастіших ERROR")
        report_lines.append("")
        for i, err in enumerate(errors[:5], 1):
            report_lines.append(f"{i}. `{err['signature'][:100]}...` — **{err['count']}** occurrences")
        report_lines.append("")
    
    # Top warnings
    if warnings:
        report_lines.append("### Топ-5 найчастіших WARNING")
        report_lines.append("")
        for i, warn in enumerate(warnings[:5], 1):
            report_lines.append(f"{i}. `{warn['signature'][:100]}...` — **{warn['count']}** occurrences")
        report_lines.append("")
    
    report_lines.append("---")
    report_lines.append("")
    
    # ERROR Analysis Section
    report_lines.append("## 3. ERROR Analysis")
    report_lines.append("")
    
    for idx, err in enumerate(errors, 1):
        error_id = f"E-{idx:03d}"
        
        # Find source location
        # location = find_source_location(err['signature'], err['logger'])
        
        risk = assess_risk(err['signature'], err['count'], "ERROR")
        status = classify_status(err['signature'], "ERROR")
        
        report_lines.append(f"### [{error_id}] [ERROR] {err['logger']}")
        report_lines.append("")
        report_lines.append(f"- **Signature:** `{err['signature']}`")
        report_lines.append(f"- **Logger:** `{err['logger']}`")
        report_lines.append(f"- **Frequency:** {err['count']} occurrences")
        report_lines.append(f"- **Risk Level:** `{risk}`")
        report_lines.append(f"- **Status:** `{status}`")
        report_lines.append("")
        report_lines.append("**Sample Line:**")
        report_lines.append("```")
        report_lines.append(err['sample_line'][:500])
        report_lines.append("```")
        report_lines.append("")
        
        # Placeholders for manual analysis
        report_lines.append("**Source Location:**")
        report_lines.append("- File: `[TODO: найти через git grep]`")
        report_lines.append("- Domain: `[TODO]`")
        report_lines.append("- Function/Method: `[TODO]`")
        report_lines.append("")
        report_lines.append("**Context & Analysis:**")
        report_lines.append("[TODO: проаналізувати контекст виникнення помилки]")
        report_lines.append("")
        report_lines.append("**Root Cause:**")
        report_lines.append("[TODO: визначити первопричину]")
        report_lines.append("")
        report_lines.append("**Recommendations:**")
        report_lines.append("[TODO: рекомендації по усуненню]")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
    
    # WARNING Analysis Section
    report_lines.append("## 4. WARNING Analysis")
    report_lines.append("")
    report_lines.append("### Топ-20 найбільш критичних WARNING")
    report_lines.append("")
    
    # Show top 20 most frequent or critical warnings
    top_warnings = sorted(warnings, key=lambda w: w['count'], reverse=True)[:20]
    
    for idx, warn in enumerate(top_warnings, 1):
        warning_id = f"W-{idx:03d}"
        
        risk = assess_risk(warn['signature'], warn['count'], "WARNING")
        status = classify_status(warn['signature'], "WARNING")
        
        report_lines.append(f"### [{warning_id}] [WARNING] {warn['logger']}")
        report_lines.append("")
        report_lines.append(f"- **Signature:** `{warn['signature']}`")
        report_lines.append(f"- **Logger:** `{warn['logger']}`")
        report_lines.append(f"- **Frequency:** {warn['count']} occurrences")
        report_lines.append(f"- **Risk Level:** `{risk}`")
        report_lines.append(f"- **Status:** `{status}`")
        report_lines.append("")
        
        # For high-frequency warnings, add more detail
        if warn['count'] > 100:
            report_lines.append("**Sample Line:**")
            report_lines.append("```")
            report_lines.append(warn['sample_line'][:500])
            report_lines.append("```")
            report_lines.append("")
        
        report_lines.append("**Analysis:**")
        report_lines.append("[TODO: проаналізувати причину та контекст]")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
    
    # Risk Summary
    report_lines.append("## 5. Risk Summary")
    report_lines.append("")
    
    high_risk_errors = [e for e in errors if assess_risk(e['signature'], e['count'], "ERROR") == "HIGH"]
    medium_risk_errors = [e for e in errors if assess_risk(e['signature'], e['count'], "ERROR") == "MEDIUM"]
    low_risk_errors = [e for e in errors if assess_risk(e['signature'], e['count'], "ERROR") == "LOW"]
    
    report_lines.append("### ERROR по рівню ризику:")
    report_lines.append("")
    report_lines.append(f"- **HIGH:** {len(high_risk_errors)} signatures")
    report_lines.append(f"- **MEDIUM:** {len(medium_risk_errors)} signatures")
    report_lines.append(f"- **LOW:** {len(low_risk_errors)} signatures")
    report_lines.append("")
    
    # Bug candidates
    bug_candidates = [e for e in errors if classify_status(e['signature'], "ERROR") == "BUG_CANDIDATE"]
    if bug_candidates:
        report_lines.append("### Bug Candidates (потребують негайного розгляду):")
        report_lines.append("")
        for bug in bug_candidates:
            report_lines.append(f"- `{bug['signature'][:80]}...` ({bug['count']} occ.)")
        report_lines.append("")
    
    # Recommendations
    report_lines.append("## 6. Recommendations")
    report_lines.append("")
    report_lines.append("### Пріоритет 1: HIGH Risk Errors")
    report_lines.append("")
    if high_risk_errors:
        for err in high_risk_errors:
            report_lines.append(f"- [ ] Investigate: `{err['signature'][:80]}...`")
        report_lines.append("")
    else:
        report_lines.append("✅ No HIGH risk errors found")
        report_lines.append("")
    
    report_lines.append("### Пріоритет 2: Bug Candidates")
    report_lines.append("")
    if bug_candidates:
        for bug in bug_candidates:
            report_lines.append(f"- [ ] Fix: `{bug['signature'][:80]}...`")
        report_lines.append("")
    else:
        report_lines.append("✅ No obvious bug candidates")
        report_lines.append("")
    
    report_lines.append("### Пріоритет 3: High-Frequency Warnings")
    report_lines.append("")
    high_freq_warnings = [w for w in warnings if w['count'] > 1000]
    if high_freq_warnings:
        for warn in high_freq_warnings[:5]:
            report_lines.append(f"- [ ] Reduce noise: `{warn['signature'][:80]}...` ({warn['count']} occ.)")
        report_lines.append("")
    
    # Write report
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    print(f"✅ Report generated: {output}")
    print(f"📊 Analyzed {len(errors)} ERROR signatures and {len(warnings)} WARNING signatures")


if __name__ == '__main__':
    json_path = 'docs/EXEC_R2_LOG_ERRORS_RAW.json'
    output_path = 'docs/EXEC_R2_LOG_ERRORS_AUDIT.md'
    
    generate_report(json_path, output_path)
