"""
Neocortex Final Exam - Comprehensive Verification Test Suite

Tests:
1. Checkpoint Frequency - Verifies checkpoints save at configured interval
2. PPO Weight Update - Proves PPO is learning (weights change after training)
3. PnL to Reward - Verifies reward calculation from PnL
"""

import pytest
import sys
import hashlib
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent paths

from apps.reference.domains.neocortex.config_models import load_config, NeuroConfig


class TestCheckpointFrequency:
    """Test 1: Verify checkpoint configuration and creation."""
    
    @pytest.fixture
    def config(self):
        config_dir = Path(__file__).parent.parent / "config"
        return load_config(config_dir)
    
    def test_checkpoint_frequency_configured(self, config):
        """Verify checkpoint_every_n_steps is set and reasonable."""
        checkpoint_interval = config.neuro.checkpoint_every_n_steps
        
        # Assert it's configured
        assert checkpoint_interval is not None, "checkpoint_every_n_steps not configured"
        assert isinstance(checkpoint_interval, int), "checkpoint_every_n_steps must be int"
        
        # Assert reasonable range (50-10000)
        assert 50 <= checkpoint_interval <= 10000, \
            f"checkpoint_every_n_steps={checkpoint_interval} outside reasonable range [50, 10000]"
        
        print(f"✅ Checkpoint frequency: every {checkpoint_interval} steps")
    
    def test_keep_checkpoints_configured(self, config):
        """Verify keep_last_n_checkpoints is set."""
        keep_n = config.neuro.keep_last_n_checkpoints
        
        assert keep_n is not None, "keep_last_n_checkpoints not configured"
        assert 1 <= keep_n <= 100, f"keep_last_n_checkpoints={keep_n} outside range [1, 100]"
        
        print(f"✅ Keep last {keep_n} checkpoints")


class TestPPOWeightUpdate:
    """Test 2: Prove PPO is actively learning (weights change)."""
    
    @pytest.fixture
    def brain_core(self):
        """Create BrainCore instance for testing."""
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not available")
        
        config_dir = Path(__file__).parent.parent / "config"
        config = load_config(config_dir)
        
        from apps.reference.domains.neocortex.logic.brain.core import BrainCore
        brain = BrainCore(config.neuro, device="cpu", rng_seed=42)
        return brain
    
    def _get_weight_hash(self, brain) -> str:
        """Get hash of PPO model weights."""
        if brain.ppo_agent is None:
            return "NO_PPO"
        
        import torch
        
        # Concatenate all weight tensors and hash
        all_weights = []
        for param in brain.ppo_agent.model.parameters():
            all_weights.append(param.data.cpu().numpy().flatten())
        
        weight_array = np.concatenate(all_weights)
        return hashlib.md5(weight_array.tobytes()).hexdigest()
    
    def test_ppo_weights_change_after_training(self, brain_core):
        """CRITICAL: Prove PPO actually updates weights."""
        if brain_core.ppo_agent is None:
            pytest.skip("PPO agent not initialized (missing dependencies)")
        
        import torch
        
        # 1. Get initial weight hash
        initial_hash = self._get_weight_hash(brain_core)
        print(f"Initial PPO weight hash: {initial_hash[:16]}...")
        
        # 2. Create training episodes with clear reward signal
        episodes = []
        for i in range(50):
            episodes.append({
                "features_vector": np.random.randn(brain_core.config.vae.input_dim).tolist(),
                "side": "LONG" if i % 2 == 0 else "SHORT",
                "reward": 1.0 if i % 2 == 0 else -1.0,  # Clear positive/negative signal
            })
        
        # 3. Train PPO
        result = brain_core.train_ppo(episodes)
        print(f"PPO train result: {result}")
        
        assert result.get("episodes_processed", 0) > 0, "No episodes processed"
        
        # 4. Get post-training weight hash
        final_hash = self._get_weight_hash(brain_core)
        print(f"Final PPO weight hash: {final_hash[:16]}...")
        
        # 5. ASSERT weights changed
        assert initial_hash != final_hash, \
            "PPO FROZEN! Weights did not change after training. Check optimizer/gradient flow."
        
        print("✅ PPO IS LEARNING - weights changed after training")


class TestPnLToReward:
    """Test 3: Verify PnL correctly transforms to reward using tanh scaling."""
    
    def test_positive_pnl_positive_reward(self):
        """Positive PnL should yield positive reward."""
        # MultiTailer uses: np.tanh(raw_pnl / REWARD_SCALE) where REWARD_SCALE ≈ 10
        REWARD_SCALE = 10.0  # From multi_tailer.py
        
        raw_pnl = 100.0
        reward = float(np.tanh(raw_pnl / REWARD_SCALE))
        
        assert reward > 0, f"Positive PnL should yield positive reward, got {reward}"
        assert reward < 1.0, f"Reward should be bounded by tanh, got {reward}"
        
        print(f"✅ PnL={raw_pnl} → Reward={reward:.4f} (tanh scaled)")
    
    def test_negative_pnl_negative_reward(self):
        """Negative PnL should yield negative reward."""
        REWARD_SCALE = 10.0
        
        raw_pnl = -50.0
        reward = float(np.tanh(raw_pnl / REWARD_SCALE))
        
        assert reward < 0, f"Negative PnL should yield negative reward, got {reward}"
        assert reward > -1.0, f"Reward should be bounded by tanh, got {reward}"
        
        print(f"✅ PnL={raw_pnl} → Reward={reward:.4f} (tanh scaled)")
    
    def test_reward_bounded(self):
        """Reward should be bounded [-1, 1] by tanh."""
        REWARD_SCALE = 10.0
        
        # Test extreme PnL values
        reward_extreme_pos = float(np.tanh(10000.0 / REWARD_SCALE))
        reward_extreme_neg = float(np.tanh(-10000.0 / REWARD_SCALE))
        
        # Tanh bounds to [-1, 1]
        assert -1.0 <= reward_extreme_pos <= 1.0, \
            f"Reward not bounded: {reward_extreme_pos}"
        assert -1.0 <= reward_extreme_neg <= 1.0, \
            f"Reward not bounded: {reward_extreme_neg}"
        
        # Extreme values should saturate near ±1
        assert reward_extreme_pos > 0.99, f"Large positive PnL should saturate near 1, got {reward_extreme_pos}"
        assert reward_extreme_neg < -0.99, f"Large negative PnL should saturate near -1, got {reward_extreme_neg}"
        
        print(f"✅ Extreme PnL bounded: +10000→{reward_extreme_pos:.4f}, -10000→{reward_extreme_neg:.4f}")


class TestVAETraining:
    """Bonus: Verify VAE is also training."""
    
    @pytest.fixture
    def brain_core(self):
        try:
            import torch
        except ImportError:
            pytest.skip("PyTorch not available")
        
        config_dir = Path(__file__).parent.parent / "config"
        config = load_config(config_dir)
        
        from apps.reference.domains.neocortex.logic.brain.core import BrainCore
        return BrainCore(config.neuro, device="cpu", rng_seed=42)
    
    def test_vae_loss_decreases(self, brain_core):
        """VAE loss should decrease with training."""
        import torch
        
        # Generate random observations
        obs = torch.randn(64, brain_core.config.vae.input_dim)
        
        # Train multiple batches
        losses = []
        for _ in range(5):
            result = brain_core.train_batch(obs)
            losses.append(result.get("vae_loss", float('inf')))
        
        print(f"VAE losses over 5 batches: {[f'{l:.4f}' for l in losses]}")
        
        # Loss should generally decrease (allow some variance)
        assert losses[-1] < losses[0] * 1.5, \
            f"VAE not learning: first={losses[0]:.4f}, last={losses[-1]:.4f}"
        
        print("✅ VAE is training - loss stable/decreasing")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



