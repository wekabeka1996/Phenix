"""
Unit tests for Backtest Diagnostics Generator.

Tests:
T1: Peak/giveback calculation from synthetic trades
T2: Stable/raw regime switches from synthetic intents
T3: CANCEL_STALE_REGIME parsing from temporary JSONL
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

# Import the module under test
from tools.backtest_diagnostics import (
    compute_equity_metrics,
    compute_regime_metrics,
    compute_cancel_stale_regime,
    generate_backtest_diagnostics,
)


class TestEquityMetrics:
    """T1: Peak/giveback calculation tests."""
    
    def test_peak_and_giveback_calculation(self):
        """Peak and giveback should be computed correctly from trades."""
        result = {
            'config': {'initial_balance': 1000.0},
            'closed_trades': [
                {'exit_ts_ms': 1000001, 'pnl_usdt_net': 200.0},   # equity: 1200
                {'exit_ts_ms': 1000002, 'pnl_usdt_net': 300.0},   # equity: 1500 (PEAK)
                {'exit_ts_ms': 1000003, 'pnl_usdt_net': -100.0},  # equity: 1400
                {'exit_ts_ms': 1000004, 'pnl_usdt_net': -200.0},  # equity: 1200
                {'exit_ts_ms': 1000005, 'pnl_usdt_net': 50.0},    # equity: 1250 (END)
            ]
        }
        
        metrics = compute_equity_metrics(result)
        
        assert metrics['initial_balance'] == 1000.0
        assert metrics['equity_peak'] == 1500.0
        assert metrics['t_peak_ms'] == 1000002
        assert metrics['min_after_peak'] == 1200.0
        assert metrics['equity_end'] == 1250.0
        
        # giveback = (1200 - 1500) / 1500 * 100 = -20%
        assert abs(metrics['giveback_pct'] - (-20.0)) < 0.01
    
    def test_no_trades(self):
        """Empty trades should return initial balance."""
        result = {
            'config': {'initial_balance': 500.0},
            'closed_trades': []
        }
        
        metrics = compute_equity_metrics(result)
        
        assert metrics['initial_balance'] == 500.0
        assert metrics['equity_peak'] == 500.0
        assert metrics['equity_end'] == 500.0
        assert metrics['giveback_pct'] == 0.0
    
    def test_nested_exit_timestamp(self):
        """Should handle nested exit.ts_ms format."""
        result = {
            'config': {'initial_balance': 1000.0},
            'closed_trades': [
                {'exit': {'ts_ms': 1000001}, 'pnl_usdt_net': 100.0},
                {'exit': {'ts_ms': 1000002}, 'pnl_usdt_net': 50.0},
            ]
        }
        
        metrics = compute_equity_metrics(result)
        
        assert metrics['equity_end'] == 1150.0
        assert metrics['trade_count'] == 2


class TestRegimeMetrics:
    """T2: Stable/raw regime switches tests."""
    
    def test_stable_switches_count(self):
        """Stable regime switches should be counted correctly."""
        result = {
            'intents': [
                {'market_regime': 'UNCERTAIN'},
                {'market_regime': 'UNCERTAIN'},
                {'market_regime': 'HIGH_VOLATILITY'},  # switch 1
                {'market_regime': 'HIGH_VOLATILITY'},
                {'market_regime': 'TREND_UP'},         # switch 2
                {'market_regime': 'UNCERTAIN'},        # switch 3
            ]
        }
        
        metrics = compute_regime_metrics(result, t_peak_ms=None)
        
        assert metrics['stable_switches'] == 3
        assert metrics['intent_count'] == 6
    
    def test_raw_switches_and_storm_rejected(self):
        """Raw switches and storm_rejected should be counted."""
        result = {
            'intents': [
                {'market_regime': 'UNCERTAIN', 'raw_regime': 'HIGH_VOLATILITY', 'storm_rejected': True},
                {'market_regime': 'UNCERTAIN', 'raw_regime': 'HIGH_VOLATILITY', 'storm_rejected': True},
                {'market_regime': 'UNCERTAIN', 'raw_regime': 'TREND_UP', 'storm_rejected': False},  # raw switch
                {'market_regime': 'HIGH_VOLATILITY', 'raw_regime': 'HIGH_VOLATILITY'},
            ]
        }
        
        metrics = compute_regime_metrics(result, t_peak_ms=None)
        
        assert metrics['raw_switches'] == 2  # HIGH_VOL -> TREND_UP, TREND_UP -> HIGH_VOL
        assert metrics['storm_rejected_count'] == 2
    
    def test_regime_counts(self):
        """Regime distribution should be calculated."""
        result = {
            'intents': [
                {'market_regime': 'HIGH_VOLATILITY'},
                {'market_regime': 'HIGH_VOLATILITY'},
                {'market_regime': 'TREND_UP'},
                {'market_regime': 'UNCERTAIN'},
            ]
        }
        
        metrics = compute_regime_metrics(result, t_peak_ms=None)
        
        assert metrics['regime_counts']['HIGH_VOLATILITY'] == 2
        assert metrics['regime_counts']['TREND_UP'] == 1
        assert metrics['regime_counts']['UNCERTAIN'] == 1
        assert metrics['top_regime'] == 'HIGH_VOLATILITY'


class TestCancelStaleRegime:
    """T3: CANCEL_STALE_REGIME parsing tests."""
    
    def test_cancel_stale_regime_parsing(self):
        """CANCEL_STALE_REGIME events should be counted with pre/post peak split."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            lines = [
                {'ts_ms': 1000, 'reason': 'FILLED'},
                {'ts_ms': 1500, 'reason': 'CANCEL_STALE_REGIME'},      # pre-peak
                {'ts_ms': 1800, 'reason': 'CANCEL_STALE_REGIME'},      # pre-peak
                {'ts_ms': 2500, 'reason': 'FILLED'},
                {'ts_ms': 3000, 'reason': 'CANCEL_STALE_REGIME'},      # post-peak
                {'ts_ms': 3500, 'reason': 'EXPIRED'},
            ]
            for line in lines:
                f.write(json.dumps(line) + '\n')
            temp_path = f.name
        
        try:
            t_peak_ms = 2000  # Peak at 2000ms
            
            metrics, missing = compute_cancel_stale_regime(temp_path, t_peak_ms)
            
            assert metrics['cancel_stale_regime_count'] == 3
            assert metrics['cancel_stale_regime_pre_peak'] == 2
            assert metrics['cancel_stale_regime_post_peak'] == 1
            assert missing == []
        finally:
            os.unlink(temp_path)
    
    def test_missing_order_log(self):
        """Missing order log should return null values and missing_artifacts."""
        metrics, missing = compute_cancel_stale_regime(None, t_peak_ms=1000)
        
        assert metrics['cancel_stale_regime_count'] is None
        assert 'order_log_jsonl' in missing
    
    def test_nonexistent_order_log(self):
        """Non-existent path should be treated as missing."""
        metrics, missing = compute_cancel_stale_regime('/nonexistent/path.jsonl', t_peak_ms=1000)
        
        assert metrics['cancel_stale_regime_count'] is None
        assert 'order_log_jsonl' in missing


class TestFullDiagnostics:
    """Integration test for full diagnostics generation."""
    
    def test_generate_full_diagnostics(self):
        """Full diagnostics should be generated from result.json."""
        with tempfile.TemporaryDirectory() as run_dir:
            # Create result.json
            result = {
                'config': {'initial_balance': 1000.0},
                'closed_trades': [
                    {'exit_ts_ms': 1001, 'pnl_usdt_net': 100.0},
                    {'exit_ts_ms': 1002, 'pnl_usdt_net': -50.0},
                ],
                'intents': [
                    {'market_regime': 'HIGH_VOLATILITY'},
                    {'market_regime': 'UNCERTAIN'},
                ],
            }
            with open(os.path.join(run_dir, 'result.json'), 'w') as f:
                json.dump(result, f)
            
            # Generate diagnostics
            diagnostics = generate_backtest_diagnostics(run_dir)
            
            assert 'equity' in diagnostics
            assert 'regime' in diagnostics
            assert 'order_log' in diagnostics
            assert 'missing_artifacts' in diagnostics  # No order log
            assert diagnostics['equity']['equity_end'] == 1050.0
            assert diagnostics['regime']['stable_switches'] == 1
