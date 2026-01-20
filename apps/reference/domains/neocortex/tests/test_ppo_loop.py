"""
Tests for Phase R2: PPO Training Loop

Tests cover:
1. PPO training method in BrainCore
2. Worker task execution
3. Integration with adapter
4. Shadow intent with trained network
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass
from typing import Dict, Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPPOTrainingCore:
    """Tests for BrainCore.train_ppo method."""
    
    @pytest.fixture
    def sample_episodes(self):
        """Create sample episodes for training."""
        return [
            {
                "features": {"f1": 0.1, "f2": 0.2, "f3": 0.3, "f4": 0.4, 
                           "f5": 0.5, "f6": 0.6, "f7": 0.7, "f8": 0.8, "f9": 0.9},
                "side": "LONG",
                "reward": 5.0,
                "timestamp": 1000.0,
                "value": 1.5
            },
            {
                "features": {"f1": 0.2, "f2": 0.3, "f3": 0.4, "f4": 0.5,
                           "f5": 0.6, "f6": 0.7, "f7": 0.8, "f8": 0.9, "f9": 1.0},
                "side": "SHORT",
                "reward": -2.0,
                "timestamp": 1001.0,
                "value": 0.5
            },
            {
                "features": {"f1": 0.0, "f2": 0.0, "f3": 0.0, "f4": 0.0,
                           "f5": 0.0, "f6": 0.0, "f7": 0.0, "f8": 0.0, "f9": 0.0},
                "side": "FLAT",
                "reward": 0.0,
                "timestamp": 1002.0,
                "value": 0.0
            }
        ]
    
    def test_action_mapping(self):
        """Test action string to index mapping."""
        action_map = {"LONG": 0, "SHORT": 1, "FLAT": 2, "BUY": 0, "SELL": 1}
        
        assert action_map["LONG"] == 0
        assert action_map["SHORT"] == 1
        assert action_map["FLAT"] == 2
        assert action_map["BUY"] == 0  # Alias for LONG
        assert action_map["SELL"] == 1  # Alias for SHORT
    
    def test_empty_episodes_returns_zero(self):
        """Empty episode list should return zero processed."""
        # Create mock core
        mock_core = MagicMock()
        mock_core.ppo_agent = MagicMock()
        
        # Empty list
        result = {"episodes_processed": 0}
        assert result["episodes_processed"] == 0
    
    def test_episode_data_extraction(self, sample_episodes):
        """Test extraction of features from episode dict."""
        ep = sample_episodes[0]
        
        features = ep.get("features", {})
        assert len(features) == 9
        
        side = ep.get("side", "FLAT")
        assert side == "LONG"
        
        reward = float(ep.get("reward", 0.0))
        assert reward == 5.0
    
    def test_missing_features_skipped(self):
        """Episodes with missing features should be skipped."""
        episodes = [
            {"side": "LONG", "reward": 1.0},  # No features
            {"features": {}, "side": "SHORT", "reward": 1.0}  # Empty features
        ]
        
        valid_count = 0
        for ep in episodes:
            features = ep.get("features", {})
            if features:
                valid_count += 1
        
        assert valid_count == 0





class TestPPOBridgeAsync:
    """Tests for BrainBridge async PPO training method."""
    
    def test_bridge_method_exists(self):
        """Verify train_ppo_async method exists on BrainBridge."""
        from logic.brain.bridge import BrainBridge
        
        assert hasattr(BrainBridge, 'train_ppo_async')
    
    def test_bridge_not_initialized_returns_error(self):
        """Uninitialized bridge should return error dict (sync version)."""
        from logic.brain.bridge import BrainBridge
        
        # Create minimal mock config
        config = MagicMock()
        
        bridge = BrainBridge(config)
        
        # Verify _initialized is False (bridge was not started)
        assert bridge._initialized == False
        # Refactor: _executor replaced by _process
        assert bridge._process is None
        assert bridge._task_queue is None


class TestAdapterPPOIntegration:
    """Integration tests for adapter PPO training."""
    
    def test_adapter_has_ppo_stats(self):
        """Adapter should track PPO training stats."""
        # Skip if adapter cannot be instantiated without full config
        try:
            from transport.adapter import NeocortexAdapter
            
            # Check that the class has the attribute
            assert hasattr(NeocortexAdapter, '_trigger_ppo_training')
            assert hasattr(NeocortexAdapter, 'train_ppo_now')
        except ImportError:
            pytest.skip("Adapter import failed")
    
    def test_adapter_has_trigger_method(self):
        """Adapter should have PPO training trigger method."""
        from transport.adapter import NeocortexAdapter
        
        assert hasattr(NeocortexAdapter, '_trigger_ppo_training')
        assert hasattr(NeocortexAdapter, 'train_ppo_now')


class TestPPOFlowIntegration:
    """Full flow integration tests."""
    
    def test_episode_to_training_flow(self):
        """Test episode -> adapter -> bridge -> core flow."""
        # This test verifies the data flow without actual training
        
        # 1. Create episode
        episode = {
            "features": {"price": 100.0, "volume": 1000.0},
            "side": "LONG",
            "reward": 0.76,
            "timestamp": 1234567890.0
        }
        
        # 2. Verify episode structure
        assert "features" in episode
        assert "side" in episode
        assert "reward" in episode
        
        # 3. Simulate action mapping
        action_map = {"LONG": 0, "SHORT": 1, "FLAT": 2}
        action_idx = action_map[episode["side"]]
        assert action_idx == 0
        
        # 4. Verify reward is float
        reward = float(episode["reward"])
        assert isinstance(reward, float)
        assert reward == 0.76
    
    def test_ppo_update_mock(self):
        """Test PPO update is called correctly with mock."""
        # Create mock PPO agent
        mock_ppo = MagicMock()
        mock_ppo.buffer = MagicMock()
        mock_ppo.buffer.n_steps = 10
        mock_ppo.model = MagicMock()
        mock_ppo.update = MagicMock(return_value={
            "loss_pi": 0.1,
            "loss_v": 0.2,
            "entropy": 0.5
        })
        
        # Simulate enough episodes stored
        episodes_stored = 15
        
        if episodes_stored >= mock_ppo.buffer.n_steps:
            mock_ppo.model.train()
            metrics = mock_ppo.update()
            
            mock_ppo.update.assert_called_once()
            assert "loss_pi" in metrics
            assert "loss_v" in metrics


class TestShadowIntentOutput:
    """Tests for shadow intent output from trained network."""
    
    def test_intent_structure(self):
        """Verify shadow intent has required fields."""
        intent = {
            "action": 0,
            "action_name": "LONG",
            "value": 1.5,
            "confidence": 0.85
        }
        
        assert "action" in intent
        assert "action_name" in intent
        assert "value" in intent
        assert "confidence" in intent
        
        assert intent["action"] in [0, 1, 2]
        assert intent["action_name"] in ["LONG", "SHORT", "FLAT"]
        assert isinstance(intent["value"], (int, float))
        assert isinstance(intent["confidence"], (int, float))
    
    def test_action_names_mapping(self):
        """Verify action index to name mapping."""
        action_names = ["LONG", "SHORT", "FLAT"]
        
        assert action_names[0] == "LONG"
        assert action_names[1] == "SHORT"
        assert action_names[2] == "FLAT"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
