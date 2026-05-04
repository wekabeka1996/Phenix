#!/usr/bin/env python3
"""
Parse aurora_core.log files and aggregate key metrics into a single report.
Extracts: equity_free_usdt, equity, positions, risk_score, trading_allowed, price, etc.
"""

import re
import json
import glob
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from statistics import mean, median, stdev

def parse_aurora_logs():
    """Parse all aurora_core.log files in logs directory."""
    
    log_dir = Path("/home/wekabeka/Музыка/Phenix/logs")
    log_files = sorted(glob.glob(str(log_dir / "aurora_core.log*")), reverse=True)
    
    if not log_files:
        print("❌ No aurora_core.log files found")
        return
    
    print(f"📂 Found {len(log_files)} log files")
    
    metrics = {
        'equity_free_usdt': [],
        'equity': [],
        'positions_count': [],
        'risk_score': [],
        'trading_allowed': [],
        'price': [],
        'open_positions_usd': [],
        'margin': [],
    }
    
    events = defaultdict(int)
    timestamps = set()
    
    # Regex patterns for extraction
    patterns = {
        'equity_free_usdt': r'Cached equity_free_usdt:\s*([\d.]+)',
        'equity': r'Equity:\s*([\d.]+),\s*Positions:\s*(\d+)',
        'risk_score': r"risk_score=([0-9.]+)",
        'trading_allowed': r"is_trading_allowed':\s*(True|False)",
        'price': r'"price":\s*"([\d.]+)"',
        'equity_raw': r'equity_raw=([\d.]+)',
        'margin_raw': r'margin_raw=([\d.]+)',
        'event': r'(?:Emitting|Handling)\s+(EVT:\w+)',
    }
    
    for log_file in log_files:
        print(f"  Processing: {log_file}")
        
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Extract timestamp
                    ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)', line)
                    if ts_match:
                        timestamps.add(ts_match.group(1))
                    
                    # Extract metrics
                    if match := re.search(patterns['equity_free_usdt'], line):
                        metrics['equity_free_usdt'].append(float(match.group(1)))
                    
                    if match := re.search(patterns['equity'], line):
                        metrics['equity'].append(float(match.group(1)))
                        metrics['positions_count'].append(int(match.group(2)))
                    
                    if match := re.search(patterns['risk_score'], line):
                        metrics['risk_score'].append(float(match.group(1)))
                    
                    if match := re.search(patterns['trading_allowed'], line):
                        metrics['trading_allowed'].append(match.group(1) == 'True')
                    
                    if match := re.search(patterns['price'], line):
                        metrics['price'].append(float(match.group(1)))
                    
                    if match := re.search(patterns['equity_raw'], line):
                        # Only add if not already added from equity_free_usdt
                        if not re.search(patterns['equity_free_usdt'], line):
                            metrics['equity_free_usdt'].append(float(match.group(1)))
                    
                    if match := re.search(patterns['margin_raw'], line):
                        metrics['margin'].append(float(match.group(1)))
                    
                    if match := re.search(patterns['event'], line):
                        events[match.group(1)] += 1
        
        except Exception as e:
            print(f"    ❌ Error reading {log_file}: {e}")
    
    # Generate report
    report = generate_report(metrics, events, timestamps, log_files)
    
    # Save report
    output_file = log_dir / "aurora_aggregated_report.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Report saved to: {output_file}")
    
    # Print summary
    print_summary(report)

def generate_report(metrics, events, timestamps, log_files):
    """Generate aggregated report."""
    
    def safe_stats(values):
        """Calculate statistics safely."""
        if not values:
            return {}
        return {
            'count': len(values),
            'min': round(min(values), 8),
            'max': round(max(values), 8),
            'mean': round(mean(values), 8),
            'median': round(median(values), 8),
            'stdev': round(stdev(values), 8) if len(values) > 1 else 0,
            'sum': round(sum(values), 8),
        }
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'log_files': log_files,
        'unique_timestamps': len(timestamps),
        'metrics': {
            'equity_free_usdt': safe_stats(metrics['equity_free_usdt']),
            'equity': safe_stats(metrics['equity']),
            'positions_count': safe_stats(metrics['positions_count']),
            'risk_score': safe_stats(metrics['risk_score']),
            'price': safe_stats(metrics['price']),
            'margin': safe_stats(metrics['margin']),
        },
        'trading_stats': {
            'trading_allowed_true': sum(metrics['trading_allowed']),
            'trading_allowed_false': len(metrics['trading_allowed']) - sum(metrics['trading_allowed']),
            'trading_allowed_ratio': round(sum(metrics['trading_allowed']) / len(metrics['trading_allowed']), 4) if metrics['trading_allowed'] else 0,
        },
        'events': dict(sorted(events.items(), key=lambda x: x[1], reverse=True)),
    }
    
    return report

def print_summary(report):
    """Print human-readable summary."""
    
    print("\n" + "="*70)
    print("📊 AURORA LOGS AGGREGATION REPORT")
    print("="*70)
    
    print(f"\n📈 Metrics Summary:")
    print("-" * 70)
    
    for metric_name, stats in report['metrics'].items():
        if stats['count'] > 0:
            print(f"\n  {metric_name}:")
            print(f"    Count:    {stats['count']}")
            print(f"    Min:      {stats['min']}")
            print(f"    Max:      {stats['max']}")
            print(f"    Mean:     {stats['mean']}")
            print(f"    Median:   {stats['median']}")
            print(f"    StDev:    {stats['stdev']}")
    
    print(f"\n\n🎯 Trading Status:")
    print("-" * 70)
    print(f"  Allowed:      {report['trading_stats']['trading_allowed_true']}")
    print(f"  Not allowed:  {report['trading_stats']['trading_allowed_false']}")
    print(f"  Ratio:        {report['trading_stats']['trading_allowed_ratio'] * 100:.2f}%")
    
    print(f"\n\n📡 Event Count:")
    print("-" * 70)
    for event, count in list(report['events'].items())[:15]:
        print(f"  {event}: {count}")
    
    print(f"\n\n🕐 Coverage:")
    print("-" * 70)
    print(f"  Unique timestamps: {report['unique_timestamps']}")
    print(f"  Generated at: {report['generated_at']}")
    print("\n" + "="*70)

if __name__ == '__main__':
    parse_aurora_logs()
