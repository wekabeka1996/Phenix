"""
Test PPO Adapter Integration

Tests the compatibility and functionality of RewardEngineAPIV3Plus adapter
with existing PPO agent interfaces.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from alysha_core.reward_engine_v3plus.adapters.ppo_adapter import RewardEngineAPIV3Plus


class TestPPOAdapterIntegration:
    """Test suite for PPO adapter compatibility and functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        self.adapter = RewardEngineAPIV3Plus()
        
        # Sample context similar to what PPO agent would send
        self.sample_context = {
            'symbol': 'BTCUSDT',
            'price': 45000.0,
            'position_size': 1.5,
            'position_value': 67500.0,
            'unrealized_pnl': 1500.0,
            'realized_pnl': 300.0,
            'action_type': 'buy',
            'action_size': 0.5,
            'portfolio_value': 100000.0,
            'available_balance': 50000.0,
            'market_volatility': 0.03,
            'market_trend': 'bullish',
            'transaction_cost': 10.0,
            'slippage': 5.0,
            'metadata': {'strategy': 'test'}
        }
    
    def test_adapter_initialization(self):
        """Test adapter initializes correctly."""
        assert self.adapter is not None
        assert self.adapter.engine is not None
        assert self.adapter.config is not None
    
    def test_compute_reward_interface(self):
        """Test compute_reward method interface compatibility."""
        result = self.adapter.compute_reward(self.sample_context)
        
        # Check V2 API compatibility
        assert isinstance(result, dict)
        assert 'reward' in result
        assert 'trace' in result
        assert 'error' in result
        
        # Check reward is valid number
        assert isinstance(result['reward'], (int, float))
        assert not isinstance(result['reward'], bool)  # bool is subclass of int
        
        # Check trace structure
        trace = result['trace']
        assert isinstance(trace, dict)
        assert 'components' in trace
        assert 'total_reward' in trace
        
        print(f"✅ compute_reward result: {result}")
    
    def test_get_xai_trace_interface(self):
        """Test get_xai_trace method interface compatibility."""
        result = self.adapter.get_xai_trace(self.sample_context)
        
        # Check V2 API compatibility
        assert isinstance(result, dict)
        assert 'xai_trace' in result
        assert 'trace' in result
        assert 'error' in result
        
        # Check XAI trace structure
        if result['xai_trace'] is not None:
            xai_trace = result['xai_trace']
            assert 'component_contributions' in xai_trace
            assert 'explanation' in xai_trace
            assert 'importance_scores' in xai_trace
        
        print(f"✅ get_xai_trace result keys: {list(result.keys())}")
    
    def test_get_risk_report_interface(self):
        """Test get_risk_report method interface compatibility."""
        result = self.adapter.get_risk_report(self.sample_context)
        
        # Check V2 API compatibility
        assert isinstance(result, dict)
        assert 'risk_report' in result
        assert 'trace' in result
        assert 'error' in result
        
        # Check risk report structure
        if result['risk_report'] is not None:
            risk_report = result['risk_report']
            assert 'risk_score' in risk_report
            assert 'risk_level' in risk_report
            assert 'recommendations' in risk_report
        
        print(f"✅ get_risk_report result keys: {list(result.keys())}")
    
    def test_audit_log_interface(self):
        """Test audit_log method interface compatibility."""
        result = self.adapter.audit_log(self.sample_context)
        
        # Check V2 API compatibility
        assert isinstance(result, dict)
        assert 'audit_log' in result
        assert 'trace' in result
        assert 'error' in result
        
        # Check audit log structure
        if result['audit_log'] is not None:
            audit_log = result['audit_log']
            assert 'input_context' in audit_log
            assert 'engine_version' in audit_log
            assert 'timestamp' in audit_log
        
        print(f"✅ audit_log result keys: {list(result.keys())}")
    
    def test_error_handling(self):
        """Test error handling with invalid context."""
        invalid_context = {'invalid': 'data'}
        
        # Should not crash, should return error info
        result = self.adapter.compute_reward(invalid_context)
        
        assert isinstance(result, dict)
        assert 'reward' in result
        assert 'trace' in result
        assert 'error' in result
        
        # Reward should be valid even on error
        assert isinstance(result['reward'], (int, float))
        
        print(f"✅ Error handling result: {result}")
    
    def test_minimal_context(self):
        """Test with minimal context data."""
        minimal_context = {
            'symbol': 'BTCUSDT',
            'price': 45000.0
        }
        
        result = self.adapter.compute_reward(minimal_context)
        
        assert isinstance(result, dict)
        assert 'reward' in result
        assert isinstance(result['reward'], (int, float))
        
        print(f"✅ Minimal context result: {result}")
    
    def test_different_action_types(self):
        """Test different action types mapping."""
        action_types = ['buy', 'sell', 'hold', 'close', 'invalid']
        
        for action_type in action_types:
            context = self.sample_context.copy()
            context['action_type'] = action_type
            
            result = self.adapter.compute_reward(context)
            
            assert isinstance(result, dict)
            assert 'reward' in result
            assert isinstance(result['reward'], (int, float))
            
            print(f"✅ Action type '{action_type}' processed successfully")
    
    def test_performance_basic(self):
        """Basic performance test to ensure reasonable response times."""
        import time
        
        start_time = time.time()
        
        # Run multiple reward calculations
        for _ in range(10):
            result = self.adapter.compute_reward(self.sample_context)
            assert isinstance(result['reward'], (int, float))
        
        end_time = time.time()
        avg_time = (end_time - start_time) / 10
        
        # Should be fast enough for real-time trading
        assert avg_time < 0.1  # Less than 100ms per calculation
        
        print(f"✅ Average calculation time: {avg_time:.4f} seconds")


def test_integration_with_sample_data():
    """Integration test with sample trading data."""
    adapter = RewardEngineAPIV3Plus()
    
    # Test data similar to real trading scenarios
    test_scenarios = [
        {
            'name': 'Profitable Buy',
            'context': {
                'symbol': 'BTCUSDT',
                'price': 45000.0,
                'position_size': 1.0,
                'unrealized_pnl': 1000.0,
                'action_type': 'buy',
                'action_size': 0.5
            }
        },
        {
            'name': 'Loss Position',
            'context': {
                'symbol': 'ETHUSDT',
                'price': 3000.0,
                'position_size': -2.0,
                'unrealized_pnl': -500.0,
                'action_type': 'sell',
                'action_size': 1.0
            }
        },
        {
            'name': 'Hold Position',
            'context': {
                'symbol': 'ADAUSDT',
                'price': 0.5,
                'position_size': 0.0,
                'unrealized_pnl': 0.0,
                'action_type': 'hold',
                'action_size': 0.0
            }
        }
    ]
    
    for scenario in test_scenarios:
        print(f"\n🧪 Testing scenario: {scenario['name']}")
        
        result = adapter.compute_reward(scenario['context'])
        
        assert isinstance(result, dict)
        assert 'reward' in result
        assert isinstance(result['reward'], (int, float))
        
        print(f"   Reward: {result['reward']:.4f}")
        
        # Test XAI trace
        xai_result = adapter.get_xai_trace(scenario['context'])
        assert 'xai_trace' in xai_result
        
        if xai_result['xai_trace']:
            print(f"   Explanation: {xai_result['xai_trace'].get('explanation', 'N/A')}")
        
        print(f"✅ Scenario '{scenario['name']}' passed")


if __name__ == "__main__":
    # Run tests directly
    print("🚀 Running PPO Adapter Integration Tests")
    
    test_instance = TestPPOAdapterIntegration()
    test_instance.setup_method()
    
    try:
        test_instance.test_adapter_initialization()
        test_instance.test_compute_reward_interface()
        test_instance.test_get_xai_trace_interface()
        test_instance.test_get_risk_report_interface()
        test_instance.test_audit_log_interface()
        test_instance.test_error_handling()
        test_instance.test_minimal_context()
        test_instance.test_different_action_types()
        test_instance.test_performance_basic()
        
        test_integration_with_sample_data()
        
        print("\n🎉 All PPO Adapter Integration Tests PASSED!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise
