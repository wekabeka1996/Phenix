#!/usr/bin/env python3
"""
Log Errors Summary Tool

Aggregates unique ERROR and WARNING signatures from log files (both .log and .jsonl formats).
Groups by normalized message signature, counts occurrences, and outputs to JSON.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from dataclasses import dataclass, asdict


@dataclass
class LogSignature:
    """Represents a unique log signature."""
    level: str
    logger: str
    signature: str
    sample_line: str
    count: int


class LogParser:
    """Parser for both plain .log and .jsonl log formats."""
    
    # Regex for standard Python logging format
    LOG_PATTERN = re.compile(
        r'^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+-\s+'
        r'(?P<logger>[^\s-]+(?:\.[^\s-]+)*)\s+-\s+'
        r'(?P<level>ERROR|WARNING|WARN)\s+-\s+'
        r'(?P<message>.+)$',
        re.MULTILINE
    )
    
    def __init__(self):
        self.signatures: Dict[str, LogSignature] = {}
        self.error_count = 0
        self.warning_count = 0
    
    @staticmethod
    def normalize_message(message: str) -> str:
        """
        Normalize log message to create a signature by removing variable parts.
        
        Examples:
        - "Order 12345 failed" -> "Order <ID> failed"
        - "symbol=BTCUSDT price=50000" -> "symbol=<SYMBOL> price=<PRICE>"
        """
        # Replace order IDs (numbers after "order", "orderId", etc.)
        msg = re.sub(r'\b(order[_\s]?id[=:\s]+)[\w-]+', r'\1<ID>', message, flags=re.IGNORECASE)
        msg = re.sub(r'\border\s+\d+', 'order <ID>', msg, flags=re.IGNORECASE)
        
        # Replace symbols (crypto pairs like BTCUSDT, ETHUSDT, etc.)
        msg = re.sub(r'\b[A-Z]{3,10}USDT?\b', '<SYMBOL>', msg)
        msg = re.sub(r'symbol[=:\s]+[A-Z]{3,10}USDT?', 'symbol=<SYMBOL>', msg, flags=re.IGNORECASE)
        
        # Replace numeric values after common keywords
        msg = re.sub(r'(price|quantity|qty|amount|size|value)[=:\s]+[\d.]+', r'\1=<NUM>', msg, flags=re.IGNORECASE)
        
        # Replace cycle_id, exec_id, etc.
        msg = re.sub(r'(cycle|exec|execution|request)[_\s]?id[=:\s]+[\w-]+', r'\1_id=<ID>', msg, flags=re.IGNORECASE)
        
        # Replace specific numeric IDs
        msg = re.sub(r'\bid[=:\s]+\d+', 'id=<ID>', msg, flags=re.IGNORECASE)
        
        # Replace timestamps within message
        msg = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,\.]?\d*', '<TIMESTAMP>', msg)
        
        # Replace standalone numbers (but keep things like "ERROR", "SL", "TP")
        msg = re.sub(r'\b\d{4,}\b', '<NUM>', msg)
        
        # Replace floating point numbers
        msg = re.sub(r'\b\d+\.\d+\b', '<NUM>', msg)
        
        return msg.strip()
    
    def parse_plain_log_line(self, line: str) -> None:
        """Parse a line from plain .log file."""
        match = self.LOG_PATTERN.match(line)
        if not match:
            return
        
        timestamp = match.group('timestamp')
        logger = match.group('logger')
        level = match.group('level')
        message = match.group('message')
        
        # Normalize to "ERROR" or "WARNING"
        level_normalized = "ERROR" if level == "ERROR" else "WARNING"
        
        # Create signature
        signature = self.normalize_message(message)
        key = f"{logger}::{level_normalized}::{signature}"
        
        if key in self.signatures:
            self.signatures[key].count += 1
        else:
            self.signatures[key] = LogSignature(
                level=level_normalized,
                logger=logger,
                signature=signature,
                sample_line=line.strip(),
                count=1
            )
        
        if level_normalized == "ERROR":
            self.error_count += 1
        else:
            self.warning_count += 1
    
    def parse_jsonl_line(self, line: str) -> None:
        """Parse a line from .jsonl file."""
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            return
        
        # Check if this is an error/warning log
        level = data.get('level', '').upper()
        if level not in ('ERROR', 'WARNING', 'WARN'):
            return
        
        level_normalized = "ERROR" if level == "ERROR" else "WARNING"
        
        # Extract fields
        logger = data.get('logger', data.get('name', 'unknown'))
        message = data.get('message', data.get('msg', ''))
        
        # For JSONL, sample line is the original JSON
        sample_line = line.strip()
        
        # Create signature
        signature = self.normalize_message(message)
        key = f"{logger}::{level_normalized}::{signature}"
        
        if key in self.signatures:
            self.signatures[key].count += 1
        else:
            self.signatures[key] = LogSignature(
                level=level_normalized,
                logger=logger,
                signature=signature,
                sample_line=sample_line,
                count=1
            )
        
        if level_normalized == "ERROR":
            self.error_count += 1
        else:
            self.warning_count += 1
    
    def parse_file(self, file_path: Path) -> None:
        """Parse a single log file."""
        print(f"  Parsing {file_path.name}...")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if file_path.suffix == '.jsonl':
                    for line in f:
                        if line.strip():
                            self.parse_jsonl_line(line)
                else:
                    for line in f:
                        if 'ERROR' in line or 'WARNING' in line or 'WARN' in line:
                            self.parse_plain_log_line(line)
        except Exception as e:
            print(f"    ⚠ Error reading {file_path.name}: {e}")
    
    def get_results(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get aggregated results grouped by level."""
        errors = []
        warnings = []
        
        for sig in self.signatures.values():
            sig_dict = asdict(sig)
            if sig.level == "ERROR":
                errors.append(sig_dict)
            else:
                warnings.append(sig_dict)
        
        # Sort by count (descending)
        errors.sort(key=lambda x: x['count'], reverse=True)
        warnings.sort(key=lambda x: x['count'], reverse=True)
        
        return {
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "total_errors": self.error_count,
                "total_warnings": self.warning_count,
                "unique_error_signatures": len(errors),
                "unique_warning_signatures": len(warnings)
            }
        }


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate unique ERROR/WARNING signatures from log files"
    )
    parser.add_argument(
        '--logs-dir',
        type=str,
        default='logs',
        help='Directory containing log files (default: logs)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='docs/EXEC_R2_LOG_ERRORS_RAW.json',
        help='Output JSON file path (default: docs/EXEC_R2_LOG_ERRORS_RAW.json)'
    )
    parser.add_argument(
        '--pattern',
        type=str,
        default='*',
        help='File pattern to match (default: *)'
    )
    
    args = parser.parse_args()
    
    logs_dir = Path(args.logs_dir)
    if not logs_dir.exists():
        print(f"❌ Error: Directory '{logs_dir}' does not exist")
        return 1
    
    print(f"📂 Scanning logs in: {logs_dir}")
    
    # Find log files
    log_files = list(logs_dir.glob('*.log')) + list(logs_dir.glob('*.jsonl'))
    
    if not log_files:
        print(f"❌ No log files found in {logs_dir}")
        return 1
    
    print(f"📋 Found {len(log_files)} log file(s)")
    
    # Parse all files
    log_parser = LogParser()
    for log_file in sorted(log_files):
        log_parser.parse_file(log_file)
    
    # Get results
    results = log_parser.get_results()
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total ERROR occurrences:   {results['summary']['total_errors']}")
    print(f"Unique ERROR signatures:   {results['summary']['unique_error_signatures']}")
    print(f"Total WARNING occurrences: {results['summary']['total_warnings']}")
    print(f"Unique WARNING signatures: {results['summary']['unique_warning_signatures']}")
    
    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results written to: {output_path}")
    print(f"\n💡 Next step: Analyze signatures in {output_path} and create audit report")
    
    return 0


if __name__ == '__main__':
    exit(main())
