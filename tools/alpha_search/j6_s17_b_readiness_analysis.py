#!/usr/bin/env python3
"""
J6-S17-B Outcome Join Readiness Analysis
Generates detailed JSON reports for classifier output and label distribution
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict
import csv


def analyze_readiness_by_classifier(csv_path: Path) -> Dict[str, Any]:
    """Analyze readiness metrics by classifier_output."""

    readiness = {
        'UNKNOWN': {
            'row_count': 0,
            'unique_cycles': set(),
            'rows_with_outcome': 0,
            'outcome_join_rate_pct': 0.0,
            'outcome_distribution': defaultdict(int),
        },
        'TRACK_ONLY': {
            'row_count': 0,
            'unique_cycles': set(),
            'rows_with_outcome': 0,
            'outcome_join_rate_pct': 0.0,
            'outcome_distribution': defaultdict(int),
        }
    }

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                classifier = row.get('classifier_output', 'UNKNOWN')
                cycle_key = row.get('cycle_key')
                outcome_available = row.get(
                    'outcome_available', '').lower() == 'true'
                outcome = row.get('outcome')

                if classifier in readiness:
                    readiness[classifier]['row_count'] += 1
                    if cycle_key:
                        readiness[classifier]['unique_cycles'].add(cycle_key)
                    if outcome_available and outcome:
                        readiness[classifier]['rows_with_outcome'] += 1
                        readiness[classifier]['outcome_distribution'][outcome] += 1

        # Convert sets to counts and compute percentages
        for classifier, stats in readiness.items():
            stats['unique_cycles'] = len(stats['unique_cycles'])
            if stats['row_count'] > 0:
                stats['outcome_join_rate_pct'] = (
                    stats['rows_with_outcome'] / stats['row_count']) * 100
            stats['outcome_distribution'] = dict(stats['outcome_distribution'])

    except Exception as e:
        print(f"Error analyzing CSV: {e}")

    return readiness


def analyze_readiness_by_label(csv_path: Path) -> Dict[str, Any]:
    """Analyze readiness metrics by matched_surface_label."""

    readiness = defaultdict(lambda: {
        'row_count': 0,
        'rows_with_outcome': 0,
        'outcome_join_rate_pct': 0.0,
        'outcomes': defaultdict(int),
        'symbols': set(),
        'regimes': set(),
    })

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                label = row.get('matched_surface_label') or 'NULL'
                outcome_available = row.get(
                    'outcome_available', '').lower() == 'true'
                outcome = row.get('outcome')
                symbol = row.get('symbol')
                regime = row.get('regime')

                readiness[label]['row_count'] += 1
                if outcome_available and outcome:
                    readiness[label]['rows_with_outcome'] += 1
                    readiness[label]['outcomes'][outcome] += 1
                if symbol:
                    readiness[label]['symbols'].add(symbol)
                if regime:
                    readiness[label]['regimes'].add(regime)

        # Compute percentages and convert sets
        for label, stats in readiness.items():
            if stats['row_count'] > 0:
                stats['outcome_join_rate_pct'] = (
                    stats['rows_with_outcome'] / stats['row_count']) * 100
            stats['outcomes'] = dict(stats['outcomes'])
            stats['symbols'] = list(stats['symbols'])
            stats['regimes'] = list(stats['regimes'])

    except Exception as e:
        print(f"Error analyzing CSV: {e}")

    return dict(readiness)


def analyze_coverage_by_dimension(csv_path: Path) -> Dict[str, Any]:
    """Analyze coverage by regime, symbol, side, tf."""

    coverage = {
        'regime': defaultdict(lambda: {'row_count': 0, 'with_outcome': 0}),
        'symbol': defaultdict(lambda: {'row_count': 0, 'with_outcome': 0}),
        'side': defaultdict(lambda: {'row_count': 0, 'with_outcome': 0}),
        'tf_sec': defaultdict(lambda: {'row_count': 0, 'with_outcome': 0}),
    }

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                outcome_available = row.get(
                    'outcome_available', '').lower() == 'true'

                for dim, key in [('regime', 'regime'), ('symbol', 'symbol'), ('side', 'side'), ('tf_sec', 'tf_sec')]:
                    value = row.get(key)
                    if value:
                        coverage[dim][str(value)]['row_count'] += 1
                        if outcome_available:
                            coverage[dim][str(value)]['with_outcome'] += 1

        # Convert and compute percentages
        for dim in coverage:
            coverage[dim] = dict(coverage[dim])
            for value in coverage[dim]:
                stats = coverage[dim][value]
                if stats['row_count'] > 0:
                    stats['join_rate_pct'] = (
                        stats['with_outcome'] / stats['row_count']) * 100

    except Exception as e:
        print(f"Error analyzing coverage: {e}")

    return coverage


def main():
    root = Path('c:\\Users\\user\\Music\\Phenix')
    reports_dir = root / 'reports' / 'alpha_search'
    csv_path = reports_dir / 'j6_s17_b_joined_policy_outcome_dataset.csv'

    if not csv_path.exists():
        print(f"Dataset not found: {csv_path}")
        return 1

    print("Analyzing classifier output readiness...")
    classifier_readiness = analyze_readiness_by_classifier(csv_path)
    with open(reports_dir / 'j6_s17_b_classifier_output_readiness.json', 'w') as f:
        json.dump(classifier_readiness, f, indent=2)
    print(f"  Wrote: j6_s17_b_classifier_output_readiness.json")

    print("Analyzing label readiness...")
    label_readiness = analyze_readiness_by_label(csv_path)
    with open(reports_dir / 'j6_s17_b_matched_label_readiness.json', 'w') as f:
        json.dump(label_readiness, f, indent=2)
    print(f"  Wrote: j6_s17_b_matched_label_readiness.json")

    print("Analyzing coverage by dimension...")
    coverage = analyze_coverage_by_dimension(csv_path)
    with open(reports_dir / 'j6_s17_b_coverage_by_dimension.json', 'w') as f:
        json.dump(coverage, f, indent=2)
    print(f"  Wrote: j6_s17_b_coverage_by_dimension.json")

    print("Analysis complete")
    return 0


if __name__ == '__main__':
    exit(main())
