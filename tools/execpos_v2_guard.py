"""
ExecPosRuntimeV2 Regression Guard
==================================

Analyzes V2 runtime logs to detect anomalies and regressions.

Usage:
    python -m tools.execpos_v2_guard --log-file logs/execpos_v2_runtime.jsonl --last-n 1000
    python -m tools.execpos_v2_guard --metrics-file metrics_snapshot.json
"""
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List
from collections import Counter


class V2GuardStatus:
    OK = "OK"
    WARN = "WARN"
    ALERT = "ALERT"


class ExecPosV2Guard:
    """Regression guard for V2 runtime."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Default thresholds
        self.execution_failure_threshold = self.config.get("execution_failure_threshold", 0.1)  # 10%
        self.watchdog_violation_threshold = self.config.get("watchdog_violation_threshold", 0.05)  # 5%
        self.duplicate_fill_threshold = self.config.get("duplicate_fill_threshold", 0.2)  # 20%
    
    def analyze_logs(self, log_lines: List[str]) -> Dict[str, Any]:
        """
        Analyze JSONL log lines and compute health metrics.
        
        Returns:
            dict with status, metrics, and issues
        """
        events = [json.loads(line) for line in log_lines if line.strip()]
        
        if not events:
            return {
                "status": V2GuardStatus.OK,
                "message": "No events to analyze",
                "metrics": {},
                "issues": []
            }
        
        # Count outcomes
        total_events = len(events)
        rejected = sum(1 for e in events if e.get("action") == "rejected")
        executed_success = sum(1 for e in events if e.get("action") == "executed" and e.get("result") == "success")
        executed_failed = sum(1 for e in events if e.get("action") == "executed" and e.get("result") == "failed")
        
        # Compute ratios
        execution_total = executed_success + executed_failed
        execution_failure_rate = executed_failed / execution_total if execution_total > 0 else 0.0
        rejection_rate = rejected / total_events if total_events > 0 else 0.0
        
        # Count watchdog events
        watchdog_events = [e for e in events if e.get("event_kind") == "WATCHDOG_ACTION"]
        watchdog_rate = len(watchdog_events) / total_events if total_events > 0 else 0.0
        
        # Determine status
        issues = []
        status = V2GuardStatus.OK
        
        if execution_failure_rate > self.execution_failure_threshold:
            issues.append(f"Execution failure rate {execution_failure_rate:.2%} exceeds threshold {self.execution_failure_threshold:.2%}")
            status = V2GuardStatus.ALERT
        
        if watchdog_rate > self.watchdog_violation_threshold:
            issues.append(f"Watchdog violation rate {watchdog_rate:.2%} exceeds threshold {self.watchdog_violation_threshold:.2%}")
            if status == V2GuardStatus.OK:
                status = V2GuardStatus.WARN
        
        if rejection_rate > 0.5:  # More than 50% rejected
            issues.append(f"High rejection rate: {rejection_rate:.2%}")
            if status == V2GuardStatus.OK:
                status = V2GuardStatus.WARN
        
        return {
            "status": status,
            "message": "All checks passed" if status == V2GuardStatus.OK else f"{len(issues)} issues detected",
            "metrics": {
                "total_events": total_events,
                "rejected": rejected,
                "executed_success": executed_success,
                "executed_failed": executed_failed,
                "execution_failure_rate": execution_failure_rate,
                "rejection_rate": rejection_rate,
                "watchdog_events": len(watchdog_events),
                "watchdog_rate": watchdog_rate
            },
            "issues": issues
        }
    
    def analyze_metrics_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a metrics snapshot from runtime.get_metrics_snapshot().
        
        Returns:
            dict with status, metrics, and issues
        """
        execution_total = snapshot.get("execution_success", 0) + snapshot.get("execution_failed", 0)
        execution_failure_rate = snapshot.get("execution_failed", 0) / execution_total if execution_total > 0 else 0.0
        
        fills_total = snapshot.get("fills_processed", 0) + snapshot.get("fills_duplicate", 0)
        duplicate_fill_rate = snapshot.get("fills_duplicate", 0) / fills_total if fills_total > 0 else 0.0
        
        watchdog_rate = snapshot.get("watchdog_violations", 0) / snapshot.get("events_total", 1)
        
        issues = []
        status = V2GuardStatus.OK
        
        if execution_failure_rate > self.execution_failure_threshold:
            issues.append(f"Execution failure rate {execution_failure_rate:.2%} exceeds threshold")
            status = V2GuardStatus.ALERT
        
        if duplicate_fill_rate > self.duplicate_fill_threshold:
            issues.append(f"Duplicate fill rate {duplicate_fill_rate:.2%} exceeds threshold")
            if status == V2GuardStatus.OK:
                status = V2GuardStatus.WARN
        
        if watchdog_rate > self.watchdog_violation_threshold:
            issues.append(f"Watchdog violation rate {watchdog_rate:.2%} exceeds threshold")
            if status == V2GuardStatus.OK:
                status = V2GuardStatus.WARN
        
        return {
            "status": status,
            "message": "All checks passed" if status == V2GuardStatus.OK else f"{len(issues)} issues detected",
            "metrics": {
                "events_total": snapshot.get("events_total", 0),
                "execution_success": snapshot.get("execution_success", 0),
                "execution_failed": snapshot.get("execution_failed", 0),
                "execution_failure_rate": execution_failure_rate,
                "fills_processed": snapshot.get("fills_processed", 0),
                "fills_duplicate": snapshot.get("fills_duplicate", 0),
                "duplicate_fill_rate": duplicate_fill_rate,
                "watchdog_violations": snapshot.get("watchdog_violations", 0),
                "watchdog_rate": watchdog_rate
            },
            "issues": issues
        }


def main():
    parser = argparse.ArgumentParser(description="ExecPosRuntimeV2 Regression Guard")
    parser.add_argument("--log-file", type=str, help="Path to JSONL log file")
    parser.add_argument("--last-n", type=int, default=1000, help="Analyze last N log lines")
    parser.add_argument("--metrics-file", type=str, help="Path to metrics snapshot JSON")
    
    args = parser.parse_args()
    
    guard = ExecPosV2Guard()
    
    if args.log_file:
        log_path = Path(args.log_file)
        if not log_path.exists():
            print(f"❌ Log file not found: {args.log_file}")
            return 1
        
        # Read last N lines
        with open(log_path, 'r') as f:
            lines = f.readlines()
            lines = lines[-args.last_n:]  # Take last N
        
        result = guard.analyze_logs(lines)
        
    elif args.metrics_file:
        metrics_path = Path(args.metrics_file)
        if not metrics_path.exists():
            print(f"❌ Metrics file not found: {args.metrics_file}")
            return 1
        
        with open(metrics_path, 'r') as f:
            snapshot = json.load(f)
        
        result = guard.analyze_metrics_snapshot(snapshot)
    
    else:
        print("❌ Please specify either --log-file or --metrics-file")
        return 1
    
    # Print results
    status_emoji = {
        V2GuardStatus.OK: "✅",
        V2GuardStatus.WARN: "⚠️",
        V2GuardStatus.ALERT: "🚨"
    }
    
    print(f"\n{status_emoji[result['status']]} Status: {result['status']}")
    print(f"Message: {result['message']}\n")
    
    print("Metrics:")
    for key, value in result['metrics'].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")
    
    if result['issues']:
        print("\nIssues:")
        for issue in result['issues']:
            print(f"  - {issue}")
    
    # Exit code: 0 for OK, 1 for WARN, 2 for ALERT
    exit_code = {
        V2GuardStatus.OK: 0,
        V2GuardStatus.WARN: 1,
        V2GuardStatus.ALERT: 2
    }
    
    return exit_code[result['status']]


if __name__ == "__main__":
    exit(main())
