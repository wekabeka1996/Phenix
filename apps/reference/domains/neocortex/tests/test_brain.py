"""
Brain Core Tests
"""

import pytest
import numpy as np

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from config_models import NeuroConfig, VAEConfig, PPOConfig, WorldModelConfig
from logic.brain.vae import VariationalAutoencoder
from logic.brain.world_model import WorldModel
from logic.brain.core import BrainCore

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def neuro_config():
    return NeuroConfig(
        vae={
            "input_dim": 10,
            "hidden_dims": [16, 8],
            "latent_dim": 4,
            "learning_rate": 0.001,
            "beta": 1.0,
            "batch_size": 32,
            "use_mean": True
        },
        world_model={
            "hidden_dim": 8,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.001,
            "sequence_length": 10
        },
        ppo={
            "state_dim": 10,
            "action_dim": 3,
            "hidden_dims": [16],
            "learning_rate": 0.001,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_epsilon": 0.2,
            "rollout_length": 100,
            "num_epochs": 2,
            "minibatch_size": 16
        },
        checkpoint_every_n_steps=100,
        keep_last_n_checkpoints=1
    )

# =============================================================================
# TESTS
# =============================================================================

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_shapes(neuro_config):
    """Test VAE Forward Pass shapes."""
    input_dim = neuro_config.vae.input_dim
    vae = VariationalAutoencoder(neuro_config.vae)
    
    # Batch of 5
    x = torch.randn(5, input_dim)
    recon, mu, logvar = vae(x)
    
    assert recon.shape == x.shape
    assert mu.shape == (5, neuro_config.vae.latent_dim)
    assert logvar.shape == (5, neuro_config.vae.latent_dim)

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_loss(neuro_config):
    """Test VAE Loss calculation."""
    vae = VariationalAutoencoder(neuro_config.vae)
    x = torch.randn(5, neuro_config.vae.input_dim)
    recon, mu, logvar = vae(x)
    
    losses = vae.loss_function(recon, x, mu, logvar)
    assert "loss" in losses
    assert "mse" in losses
    assert "kld" in losses
    assert not torch.isnan(losses["loss"])

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_world_model_step(neuro_config):
    """Test World Model single step prediction."""
    latent_dim = neuro_config.vae.latent_dim
    wm = WorldModel(neuro_config.world_model, input_dim=latent_dim)
    
    # Input: (Batch=3, Latent=4)
    z = torch.randn(3, latent_dim)
    
    # Predict next
    next_z = wm.predict_next(z)
    
    # Should maintain shape (Batch, Latent)
    assert next_z.shape == z.shape

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_brain_core_train(neuro_config):
    """Test full training step in BrainCore."""
    core = BrainCore(neuro_config, device='cpu')
    
    # Create valid batch: (Batch=10, Features=10)
    batch_obs = torch.randn(10, neuro_config.vae.input_dim)
    
    losses = core.train_batch(batch_obs)
    
    assert "vae_loss" in losses
    assert "wm_loss" in losses
    assert losses["wm_loss"] >= 0.0

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_brain_core_encode(neuro_config):
    """Test numpy encoding."""
    core = BrainCore(neuro_config, device='cpu')
    
    input_dim = neuro_config.vae.input_dim
    
    # Single vector
    obs = np.random.randn(input_dim).astype(np.float32)
    z = core.encode(obs)
    
    assert isinstance(z, np.ndarray)
    assert z.shape == (neuro_config.vae.latent_dim,)
    assert z.dtype == np.float32
    
    # Batch
    obs_batch = np.random.randn(5, input_dim).astype(np.float32)
    z_batch = core.encode(obs_batch)
    
    assert z_batch.shape == (5, neuro_config.vae.latent_dim)
