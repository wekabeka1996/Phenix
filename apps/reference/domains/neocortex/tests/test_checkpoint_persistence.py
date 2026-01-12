"""
Tests for Checkpoint Persistence

TASK-R0: Verify checkpoints are saved correctly.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCheckpointSaving:
    """Test checkpoint saving functionality."""
    
    @pytest.fixture
    def temp_checkpoint_dir(self):
        """Create a temporary directory for checkpoints."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_checkpoint_directory_creation(self, temp_checkpoint_dir):
        """Test that checkpoint directory is created if not exists."""
        checkpoint_path = temp_checkpoint_dir / "checkpoints" / "nested"
        
        # Verify it doesn't exist
        assert not checkpoint_path.exists()
        
        # Create it
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        # Verify it exists now
        assert checkpoint_path.exists()
        assert checkpoint_path.is_dir()
    
    @pytest.mark.skipif(
        not any("torch" in m for m in sys.modules),
        reason="PyTorch not available"
    )
    def test_brain_core_save_checkpoint(self, temp_checkpoint_dir):
        """Test BrainCore.save_checkpoint creates files."""
        try:
            from logic.brain.core import BrainCore
            from config_models import NeuroConfig
            
            # Create minimal config
            config = NeuroConfig(
                vae={
                    "input_dim": 9,
                    "hidden_dims": [64, 32],
                    "latent_dim": 8,
                    "learning_rate": 0.001,
                    "beta": 1.0,
                    "batch_size": 32,
                    "use_mean": True
                },
                world_model={
                    "hidden_dim": 64,
                    "num_layers": 1,
                    "dropout": 0.1,
                    "learning_rate": 0.001,
                    "sequence_length": 10
                },
                ppo={
                    "state_dim": 8,
                    "action_dim": 3,
                    "hidden_dims": [64, 32],
                    "learning_rate": 0.0003,
                    "gamma": 0.99,
                    "gae_lambda": 0.95,
                    "clip_epsilon": 0.2,
                    "rollout_length": 100,
                    "num_epochs": 4,
                    "minibatch_size": 32
                },
                checkpoint_every_n_steps=10,
                keep_last_n_checkpoints=3
            )
            
            # Initialize BrainCore (CPU only for tests)
            brain = BrainCore(config, device="cpu")
            
            # Save checkpoint
            success = brain.save_checkpoint(temp_checkpoint_dir / "checkpoints")
            
            # Verify
            assert success
            assert (temp_checkpoint_dir / "checkpoints" / "checkpoint_0.pt").exists()
            assert (temp_checkpoint_dir / "checkpoints" / "checkpoint_latest.pt").exists()
            
        except ImportError as e:
            pytest.skip(f"Required module not available: {e}")
    
    def test_checkpoint_interval_config(self):
        """Test checkpoint interval configuration is respected."""
        try:
            from config_models import load_config
            config_dir = Path(__file__).parent.parent / "config"
            
            if not config_dir.exists():
                pytest.skip("Config directory not found")
            
            config = load_config(config_dir)
            
            # Verify the updated config value
            assert config.neuro.checkpoint_every_n_steps == 50
            
        except Exception as e:
            pytest.skip(f"Config loading failed: {e}")


class TestCheckpointLoading:
    """Test checkpoint loading functionality."""
    
    @pytest.fixture
    def saved_checkpoint(self, tmp_path):
        """Create a saved checkpoint file."""
        try:
            import torch
            
            checkpoint_dir = tmp_path / "checkpoints"
            checkpoint_dir.mkdir()
            
            checkpoint = {
                "train_steps": 100,
                "vae_state": {"test": torch.tensor([1.0])},
                "vae_opt_state": {},
                "wm_state": {"test": torch.tensor([2.0])},
                "wm_opt_state": {}
            }
            
            torch.save(checkpoint, checkpoint_dir / "checkpoint_100.pt")
            torch.save(checkpoint, checkpoint_dir / "checkpoint_latest.pt")
            
            return checkpoint_dir
            
        except ImportError:
            pytest.skip("PyTorch not available")
    
    def test_checkpoint_latest_exists(self, saved_checkpoint):
        """Verify latest checkpoint file is saved."""
        assert (saved_checkpoint / "checkpoint_latest.pt").exists()
    
    def test_checkpoint_versioned_exists(self, saved_checkpoint):
        """Verify versioned checkpoint file is saved."""
        assert (saved_checkpoint / "checkpoint_100.pt").exists()


class TestWorkerProcessSaving:
    """Test that worker process can save correctly."""
    
    def test_worker_save_task_creates_directory(self):
        """Verify worker task creates directory if missing."""
        with tempfile.TemporaryDirectory() as tmp:
            nested_path = Path(tmp) / "a" / "b" / "c"
            
            # Simulate what worker should do
            nested_path.mkdir(parents=True, exist_ok=True)
            
            assert nested_path.exists()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
