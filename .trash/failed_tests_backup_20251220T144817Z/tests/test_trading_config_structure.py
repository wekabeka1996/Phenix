"""
Sanity test for trading.yaml config structure.

Ensures:
1. No duplicate 'instruments' key (the critical bug we fixed)
2. Decision config lives under trading.decision
3. Exchange specs live under trading.instruments
4. Risk-Sizing V1 config is accessible via trading.decision.position_sizing.risk_contract_v1
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def trading_config():
    """Load trading.yaml config."""
    config_path = Path(__file__).parent.parent / "config" / "aurora" / "trading.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


class TestTradingConfigStructure:
    """Test trading.yaml structure to prevent duplicate key regression."""
    
    def test_no_duplicate_instruments_key(self, trading_config):
        """Ensure trading.instruments is not duplicated (critical regression test)."""
        trading = trading_config.get('trading', {})
        instruments = trading.get('instruments', {})
        
        # Should only have exchange spec keys (symbol names)
        expected_symbols = {'SOLUSDT', 'ETHUSDT', 'BTCUSDT', 'DOGEUSDT', 'XRPUSDT'}
        actual_symbols = set(instruments.keys())
        
        # Behavioral config should NOT be in trading.instruments
        behavioral_keys = {'behavior_fsm', 'regime_threshold_multipliers', 'position_sizing'}
        assert not behavioral_keys.intersection(actual_symbols), \
            "Behavioral config found in trading.instruments - duplicate key bug reintroduced!"
        
        assert expected_symbols.issubset(actual_symbols), \
            f"Missing exchange spec symbols. Found: {actual_symbols}"
    
    def test_decision_config_structure(self, trading_config):
        """Ensure all decision config is under trading.decision."""
        decision = trading_config.get('trading', {}).get('decision', {})
        
        # Required decision config keys
        expected_keys = [
            'signal_threshold',
            'neutral_threshold', 
            'symbols_to_track',
            'behavior_fsm',
            'regime_threshold_multipliers',
            'position_sizing',
            'sizing_modifiers',
            'kelly',
            'qos',
            'signal_weights'
        ]
        
        for key in expected_keys:
            assert key in decision, f"Missing key '{key}' in trading.decision"
    
    def test_position_sizing_accessible(self, trading_config):
        """Ensure position_sizing is accessible under trading.decision."""
        position_sizing = trading_config.get('trading', {}).get('decision', {}).get('position_sizing', {})
        
        assert position_sizing, "position_sizing not found under trading.decision"
        assert 'min_position_size_usd' in position_sizing
        assert 'risk_fraction_q' in position_sizing
    
    def test_risk_contract_v1_accessible(self, trading_config):
        """Ensure risk_contract_v1 is accessible under trading.decision.position_sizing."""
        ps = trading_config.get('trading', {}).get('decision', {}).get('position_sizing', {})
        rcv1 = ps.get('risk_contract_v1')
        
        assert rcv1 is not None, "risk_contract_v1 not found"
        assert rcv1.get('enabled') == False, "risk_contract_v1 should be disabled in ETAP1"
        assert rcv1.get('effective_leverage') == 10.0
        assert 'per_symbol_margin_fraction' in rcv1
        assert 'fixed_notional_usd' in rcv1
        assert 'sol_regime_multipliers' in rcv1
    
    def test_exchange_specs_structure(self, trading_config):
        """Ensure trading.instruments has proper exchange spec structure."""
        instruments = trading_config.get('trading', {}).get('instruments', {})
        
        for symbol in ['ETHUSDT', 'SOLUSDT', 'BTCUSDT']:
            spec = instruments.get(symbol)
            assert spec is not None, f"Missing spec for {symbol}"
            assert 'step_size' in spec, f"Missing step_size for {symbol}"
            assert 'tick_size' in spec, f"Missing tick_size for {symbol}"

