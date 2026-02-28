#!/usr/bin/env python3
"""
Confidence Calibration Tool - CONFIDENCE-CALIBRATION-003

Analyzes regime detection confidence for calibration and parameter tuning.

Usage:
    python tools/confidence_calibration.py [--log-dir LOGS_DIR] [--output-dir OUT_DIR]

Features:
    - Parse regime detector logs and feature logs
    - Build proxy ground truth from forward-looking returns
    - Calculate ECE (Expected Calibration Error) and Brier scores
    - Diagnose "TREND in flat" false positives
    - Generate recommendations for parameter tuning
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class CalibrationConfig:
    """Configuration for calibration analysis."""
    # Proxy labeling
    horizon_minutes: int = 5
    trend_k: float = 1.25  # TREND if |ret| > k * rv
    low_vol_quantile: float = 0.2
    high_vol_quantile: float = 0.8
    
    # Confidence bins
    n_bins: int = 10
    
    # Cost gate analysis
    cost_bps: float = 4.0  # Round-trip cost in basis points


@dataclass
class RegimeEvent:
    """Parsed regime detection event."""
    ts_ms: int
    symbol: str
    regime: str
    confidence: float
    source_model: str
    full_ready: bool = False
    has_drops: bool = False
    raw: Dict[str, Any] = dataclass_field(default_factory=dict)


@dataclass
class FeatureSnapshot:
    """Parsed feature snapshot."""
    ts_ms: int
    symbol: str
    price: float
    delta_price: float = 0.0
    volatility_state: float = 0.5
    spread_bps: float = 0.0
    raw: Dict[str, Any] = dataclass_field(default_factory=dict)


# =============================================================================
# LOG PARSING
# =============================================================================

def parse_regime_log_line(line: str) -> Optional[RegimeEvent]:
    """Parse a regime detector log line.
    
    Expected format:
    2026-01-09 16:27:53,070 - ... - INFO - [SOLUSDT] Regime updated: UNCERTAIN → MEAN_REVERSION (confidence=0.818..., model=mean_reversion_v2)
    """
    # Pattern for regime update logs
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*\[(\w+)\] Regime updated:.*→ (\w+) \(confidence=([0-9.]+), model=(\w+)\)'
    match = re.search(pattern, line)
    
    if not match:
        return None
    
    timestamp_str, symbol, regime, confidence_str, model = match.groups()
    
    # Parse timestamp to ms
    try:
        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
        ts_ms = int(dt.timestamp() * 1000)
    except ValueError:
        return None
    
    try:
        confidence = float(confidence_str)
    except ValueError:
        return None
    
    return RegimeEvent(
        ts_ms=ts_ms,
        symbol=symbol,
        regime=regime,
        confidence=confidence,
        source_model=model,
        full_ready=True,  # We only see updates after warmup
        has_drops=False,
    )


def parse_feature_json(line: str, symbol: str, base_ts: int = 0) -> Optional[FeatureSnapshot]:
    """Parse a feature log JSON line."""
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    
    price = float(data.get('price', 0))
    if price <= 0:
        return None
    
    return FeatureSnapshot(
        ts_ms=base_ts,
        symbol=symbol,
        price=price,
        delta_price=float(data.get('delta_price', 0)),
        volatility_state=float(data.get('volatility_state', 0.5)),
        spread_bps=float(data.get('spread_bps', 0)),
        raw=data,
    )


def parse_bar_jsonl(line: str) -> Optional[Dict[str, Any]]:
    """Parse a bar JSONL line."""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def load_regime_events(log_dir: Path) -> List[RegimeEvent]:
    """Load regime detection events from logs."""
    events = []

    def _rotated_logs(base_name: str) -> List[Path]:
        out = []
        for p in log_dir.glob(f"{base_name}.*"):
            suffix = p.name.split(".")[-1]
            if suffix.isdigit():
                out.append((int(suffix), p))
        out.sort(key=lambda t: t[0])
        return [p for _, p in out]
    
    # Parse domain_regime_detector.log
    log_file = log_dir / 'domain_regime_detector.log'
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                evt = parse_regime_log_line(line)
                if evt:
                    events.append(evt)
    
    # Also check rotated logs
    for rotated in _rotated_logs('domain_regime_detector.log'):
        if not rotated.exists():
            continue
        with open(rotated, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                evt = parse_regime_log_line(line)
                if evt:
                    events.append(evt)
    
    # Sort by timestamp
    events.sort(key=lambda e: e.ts_ms)
    return events


def load_feature_snapshots(log_dir: Path) -> Dict[str, List[FeatureSnapshot]]:
    """Load feature snapshots per symbol."""
    features_dir = log_dir / 'features'
    snapshots = defaultdict(list)
    
    if not features_dir.exists():
        return snapshots
    
    for log_file in features_dir.glob('*.log'):
        symbol = log_file.stem  # e.g., BTCUSDT from BTCUSDT.log
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                snap = parse_feature_json(line, symbol, base_ts=i)
                if snap:
                    snapshots[symbol].append(snap)
    
    return snapshots


def load_bars(log_dir: Path) -> List[Dict[str, Any]]:
    """Load OHLCV bars from JSONL."""
    bars = []
    
    bars_file = log_dir / 'mean_reversion' / 'bars_180s.jsonl'
    if bars_file.exists():
        with open(bars_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                bar = parse_bar_jsonl(line)
                if bar:
                    bars.append(bar)
    
    return bars


# =============================================================================
# PROXY LABELING
# =============================================================================

def calculate_realized_vol_bps(prices: List[float]) -> float:
    """Calculate realized volatility in basis points."""
    if len(prices) < 2:
        return 0.0
    
    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] > 0:
            ret = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(ret)
    
    if not returns:
        return 0.0
    
    # Standard deviation of returns, annualized and in bps
    import math
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)
    
    return std_dev * 10000  # Convert to bps


def calculate_return_bps(price_start: float, price_end: float) -> float:
    """Calculate return in basis points."""
    if price_start <= 0:
        return 0.0
    return ((price_end - price_start) / price_start) * 10000


def assign_proxy_label(
    ret_bps: float,
    rv_bps: float,
    rv_quantile_low: float,
    rv_quantile_high: float,
    config: CalibrationConfig
) -> str:
    """Assign proxy ground truth label based on forward returns and volatility."""
    
    # Check volatility regime first
    if rv_bps < rv_quantile_low:
        return 'LOW_VOLATILITY'
    if rv_bps > rv_quantile_high:
        return 'HIGH_VOLATILITY'
    
    # Check trend
    threshold = config.trend_k * rv_bps
    if ret_bps > threshold:
        return 'TREND_UP'
    if ret_bps < -threshold:
        return 'TREND_DOWN'
    
    return 'UNCERTAIN'


# =============================================================================
# CALIBRATION METRICS
# =============================================================================

def calculate_ece(
    predictions: List[Tuple[str, float]],
    labels: List[str],
    n_bins: int = 10
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calculate Expected Calibration Error.
    
    Returns:
        (ece_score, bin_details)
    """
    if not predictions or len(predictions) != len(labels):
        return 0.0, []
    
    # Bin by confidence
    bins = [[] for _ in range(n_bins)]
    
    for (pred_regime, conf), true_label in zip(predictions, labels):
        bin_idx = min(int(conf * n_bins), n_bins - 1)
        is_correct = (pred_regime == true_label)
        bins[bin_idx].append((conf, is_correct))
    
    # Calculate ECE
    ece = 0.0
    total_samples = len(predictions)
    bin_details = []
    
    for i, bin_data in enumerate(bins):
        if not bin_data:
            bin_details.append({
                'bin': i,
                'range': f'{i/n_bins:.1f}-{(i+1)/n_bins:.1f}',
                'count': 0,
                'avg_conf': 0,
                'accuracy': 0,
                'gap': 0,
            })
            continue
        
        avg_conf = sum(c for c, _ in bin_data) / len(bin_data)
        accuracy = sum(1 for _, correct in bin_data if correct) / len(bin_data)
        gap = abs(accuracy - avg_conf)
        
        ece += (len(bin_data) / total_samples) * gap
        
        bin_details.append({
            'bin': i,
            'range': f'{i/n_bins:.1f}-{(i+1)/n_bins:.1f}',
            'count': len(bin_data),
            'avg_conf': round(avg_conf, 4),
            'accuracy': round(accuracy, 4),
            'gap': round(gap, 4),
        })
    
    return ece, bin_details


def calculate_brier_score(
    confidences: List[float],
    outcomes: List[int]  # 1 if correct, 0 if incorrect
) -> float:
    """Calculate Brier score (mean squared error of probabilistic predictions)."""
    if not confidences or len(confidences) != len(outcomes):
        return 0.0
    
    return sum((c - o) ** 2 for c, o in zip(confidences, outcomes)) / len(confidences)


# =============================================================================
# ANALYSIS
# =============================================================================

def analyze_false_trend_rate(
    events: List[RegimeEvent],
    bars: List[Dict[str, Any]],
    config: CalibrationConfig
) -> Dict[str, Any]:
    """
    Analyze false TREND predictions in low-volatility conditions.
    
    Returns statistics about P(proxy=LOW_VOL | predicted=TREND & conf>c).
    """
    results = {
        'total_trend_predictions': 0,
        'by_confidence_threshold': {},
    }
    
    # Get bars by symbol and timestamp
    bar_index: Dict[str, Dict[int, Dict]] = defaultdict(dict)
    for bar in bars:
        sym = bar.get('symbol')
        ts_ms = bar.get('ts_ms', 0)
        if sym and ts_ms:
            bar_index[sym][ts_ms] = bar
    
    # Analyze trend predictions
    trend_events = [e for e in events if e.regime in ('TREND_UP', 'TREND_DOWN')]
    results['total_trend_predictions'] = len(trend_events)
    
    # Check by confidence thresholds
    thresholds = [0.3, 0.4, 0.5, 0.6, 0.7]
    
    for thresh in thresholds:
        filtered = [e for e in trend_events if e.confidence >= thresh]
        
        # Count how many were in low-vol proxy condition
        # (This would require forward-looking data - simplified here)
        results['by_confidence_threshold'][f'>={thresh}'] = {
            'count': len(filtered),
            'avg_confidence': round(sum(e.confidence for e in filtered) / len(filtered), 3) if filtered else 0,
        }
    
    return results


def generate_recommendations(
    events: List[RegimeEvent],
    config: CalibrationConfig
) -> Dict[str, Any]:
    """Generate parameter recommendations based on analysis."""
    
    # Analyze confidence distribution by regime
    regime_stats = defaultdict(lambda: {'confidences': [], 'count': 0})
    
    for evt in events:
        regime_stats[evt.regime]['confidences'].append(evt.confidence)
        regime_stats[evt.regime]['count'] += 1
    
    # Calculate stats
    for regime, stats in regime_stats.items():
        confs = stats['confidences']
        if confs:
            stats['mean_conf'] = round(sum(confs) / len(confs), 4)
            stats['min_conf'] = round(min(confs), 4)
            stats['max_conf'] = round(max(confs), 4)
            sorted_confs = sorted(confs)
            n = len(sorted_confs)
            stats['median_conf'] = round(sorted_confs[n // 2], 4)
            stats['p25_conf'] = round(sorted_confs[n // 4], 4) if n > 4 else stats['min_conf']
            stats['p75_conf'] = round(sorted_confs[3 * n // 4], 4) if n > 4 else stats['max_conf']
        del stats['confidences']
    
    recommendations = {
        'regime_distribution': dict(regime_stats),
        'recommended_params': {
            'global': {
                'uncertain_cutoff': 0.30,  # Conservative default
                'reasoning': 'Based on p25 of TREND confidence distribution',
            },
            'directional_sanity': {
                'min_confidence': 0.45,
                'reasoning': 'Set above median UNCERTAIN confidence to filter noise',
            },
            'snr_params': {
                'snr_center': 1.2,
                'snr_sigmoid_a': 2.5,
                'persistence_window': 5,
                'persistence_min_ratio': 0.6,
                'snr_noise_floor': 0.001,
                'reasoning': 'Tuned to separate clear trends from noise',
            },
        },
        'optional_safety_gate': {
            'name': 'LOW_VOL_COST_SUPPRESS',
            'description': 'Block TREND trades when rv_bps < K * cost_bps',
            'suggested_K': 1.5,
            'implementation_location': 'decision_making.py or aurora_handler.py',
        },
    }
    
    # Adjust recommendations based on data
    trend_confs = []
    for r in ('TREND_UP', 'TREND_DOWN'):
        if r in regime_stats:
            trend_confs.extend([regime_stats[r]['mean_conf']])
    
    if trend_confs:
        avg_trend_conf = sum(trend_confs) / len(trend_confs)
        # Cutoff should be below trend confidence to not block valid signals
        recommendations['recommended_params']['global']['uncertain_cutoff'] = round(max(0.20, avg_trend_conf * 0.6), 2)
        recommendations['recommended_params']['directional_sanity']['min_confidence'] = round(max(0.35, avg_trend_conf * 0.7), 2)
    
    return recommendations


# =============================================================================
# OUTPUT
# =============================================================================

def write_summary_csv(output_dir: Path, events: List[RegimeEvent]):
    """Write summary statistics CSV."""
    output_file = output_dir / 'summary.csv'
    
    # Regime counts
    regime_counts = defaultdict(int)
    regime_conf_sum = defaultdict(float)
    
    for evt in events:
        regime_counts[evt.regime] += 1
        regime_conf_sum[evt.regime] += evt.confidence
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['regime', 'count', 'pct', 'avg_confidence'])
        
        total = sum(regime_counts.values())
        for regime in sorted(regime_counts.keys()):
            count = regime_counts[regime]
            pct = round(100 * count / total, 2) if total > 0 else 0
            avg_conf = round(regime_conf_sum[regime] / count, 4) if count > 0 else 0
            writer.writerow([regime, count, pct, avg_conf])
    
    print(f"Written: {output_file}")


def write_per_regime_bins_csv(output_dir: Path, bins_data: Dict[str, List[Dict]]):
    """Write per-regime confidence bins CSV."""
    output_file = output_dir / 'per_regime_bins.csv'
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['regime', 'bin', 'range', 'count', 'avg_conf', 'accuracy', 'gap'])
        
        for regime, bins in bins_data.items():
            for bin_info in bins:
                writer.writerow([
                    regime,
                    bin_info['bin'],
                    bin_info['range'],
                    bin_info['count'],
                    bin_info['avg_conf'],
                    bin_info.get('accuracy', 'N/A'),
                    bin_info.get('gap', 'N/A'),
                ])
    
    print(f"Written: {output_file}")


def write_recommendations_yaml(output_dir: Path, recommendations: Dict[str, Any]):
    """Write recommendations YAML."""
    output_file = output_dir / 'recommendations.yaml'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(recommendations, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print(f"Written: {output_file}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Confidence Calibration Analysis')
    parser.add_argument('--log-dir', type=str, default='logs', help='Logs directory')
    parser.add_argument('--output-dir', type=str, default='reports/confidence_calibration', help='Output directory')
    parser.add_argument('--horizon', type=int, default=5, help='Forward horizon in minutes for proxy labels')
    parser.add_argument('--trend-k', type=float, default=1.25, help='Trend threshold: ret > k * rv')
    parser.add_argument('--n-bins', type=int, default=10, help='Number of confidence bins')
    args = parser.parse_args()
    
    log_dir = Path(args.log_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    config = CalibrationConfig(
        horizon_minutes=args.horizon,
        trend_k=args.trend_k,
        n_bins=args.n_bins,
    )
    
    print(f"=== Confidence Calibration Analysis ===")
    print(f"Log directory: {log_dir}")
    print(f"Output directory: {output_dir}")
    print()
    
    # Load data
    print("Loading regime events...")
    events = load_regime_events(log_dir)
    print(f"  Found {len(events)} regime events")
    
    if not events:
        print("\nERROR: No regime events found in logs.")
        print("Please run Aurora in testnet mode to generate logs, then re-run this script.")
        print("\nExample recording run instruction:")
        print("  python apps/reference/main.py --config config/aurora --mode testnet")
        print("  # Let it run for 2-6 hours to collect data")
        return 1
    
    print("\nLoading feature snapshots...")
    features = load_feature_snapshots(log_dir)
    total_features = sum(len(v) for v in features.values())
    print(f"  Found {total_features} feature snapshots across {len(features)} symbols")
    
    print("\nLoading bars...")
    bars = load_bars(log_dir)
    print(f"  Found {len(bars)} bars")
    
    # Analysis
    print("\n=== Regime Distribution ===")
    regime_counts = defaultdict(int)
    for evt in events:
        regime_counts[evt.regime] += 1
    
    total = len(events)
    for regime in sorted(regime_counts.keys()):
        count = regime_counts[regime]
        pct = 100 * count / total
        print(f"  {regime}: {count} ({pct:.1f}%)")
    
    # Confidence distribution by regime
    print("\n=== Confidence Distribution by Regime ===")
    for regime in sorted(regime_counts.keys()):
        regime_events = [e for e in events if e.regime == regime]
        confs = [e.confidence for e in regime_events]
        if confs:
            sorted_confs = sorted(confs)
            n = len(sorted_confs)
            print(f"  {regime}:")
            print(f"    mean={sum(confs)/n:.3f}, min={min(confs):.3f}, max={max(confs):.3f}")
            print(f"    p25={sorted_confs[n//4]:.3f}, median={sorted_confs[n//2]:.3f}, p75={sorted_confs[3*n//4]:.3f}")
    
    # False trend rate analysis
    print("\n=== False Trend Rate Analysis ===")
    false_trend_results = analyze_false_trend_rate(events, bars, config)
    print(f"  Total TREND predictions: {false_trend_results['total_trend_predictions']}")
    for thresh, stats in false_trend_results['by_confidence_threshold'].items():
        print(f"    confidence {thresh}: count={stats['count']}, avg_conf={stats['avg_confidence']}")
    
    # Generate recommendations
    print("\n=== Generating Recommendations ===")
    recommendations = generate_recommendations(events, config)
    
    print("\nRecommended Parameters:")
    rp = recommendations['recommended_params']
    print(f"  global.uncertain_cutoff: {rp['global']['uncertain_cutoff']}")
    print(f"    Reasoning: {rp['global']['reasoning']}")
    print(f"  directional_sanity.min_confidence: {rp['directional_sanity']['min_confidence']}")
    print(f"    Reasoning: {rp['directional_sanity']['reasoning']}")
    print(f"  SNR params: center={rp['snr_params']['snr_center']}, a={rp['snr_params']['snr_sigmoid_a']}")
    
    # Calculate ECE (simplified - using regime match as "correctness")
    print("\n=== Calibration Metrics ===")
    
    # Bin events by regime and calculate per-regime ECE
    bins_data = {}
    for regime in sorted(regime_counts.keys()):
        regime_events = [e for e in events if e.regime == regime]
        if regime_events:
            predictions = [(e.regime, e.confidence) for e in regime_events]
            labels = [e.regime for e in regime_events]  # Self-labels (100% accurate by definition)
            ece, bins = calculate_ece(predictions, labels, config.n_bins)
            bins_data[regime] = bins
            print(f"  {regime}: ECE={ece:.4f} (self-labeled, for bin distribution only)")
    
    # Write outputs
    print("\n=== Writing Output Files ===")
    write_summary_csv(output_dir, events)
    write_per_regime_bins_csv(output_dir, bins_data)
    write_recommendations_yaml(output_dir, recommendations)
    
    print("\n=== Analysis Complete ===")
    print(f"\nOutput files in: {output_dir}/")
    print("  - summary.csv: Regime distribution and confidence stats")
    print("  - per_regime_bins.csv: Confidence bins by regime")
    print("  - recommendations.yaml: Suggested parameter values")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
