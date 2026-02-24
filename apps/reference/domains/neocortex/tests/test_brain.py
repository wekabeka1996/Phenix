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

from apps.reference.domains.neocortex.config_models import NeuroConfig, VAEConfig, PPOConfig, WorldModelConfig
from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
from apps.reference.domains.neocortex.logic.brain.world_model import WorldModel
from apps.reference.domains.neocortex.logic.brain.core import BrainCore

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
            "hidden_dim": 16,
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
def test_vae_auxiliary_regime_head_loss():
    cfg = VAEConfig(
        input_dim=6,
        hidden_dims=[8, 4],
        latent_dim=3,
        learning_rate=0.001,
        beta=1.0,
        batch_size=8,
        use_mean=True,
        regime_aux={"enabled": True, "alpha": 0.2, "num_classes": 5},
    )
    vae = VariationalAutoencoder(cfg)

    x = torch.randn(8, cfg.input_dim)
    recon, mu, logvar = vae(x)
    logits = vae.predict_regime_logits(mu)
    targets = torch.randint(0, 5, (8,), dtype=torch.long)
    losses = vae.loss_function(
        recon,
        x,
        mu,
        logvar,
        beta=cfg.beta,
        regime_logits=logits,
        regime_targets=targets,
        aux_alpha=cfg.regime_aux.alpha,
    )

    assert logits is not None
    assert logits.shape == (8, 5)
    assert "regime_ce" in losses
    assert float(losses["regime_ce"]) >= 0.0

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


def test_get_action_fallback_when_ppo_raises(neuro_config):
    """BrainCore should fail-safe to FLAT when PPO.act raises."""

    class _BrokenPPO:
        def act(self, _z, deterministic=False):
            raise ValueError("invalid logits")

    core = BrainCore(neuro_config, device="cpu")
    core.ppo_agent = _BrokenPPO()

    result = core.get_action(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    assert result["action_name"] == "FLAT"
    assert result["action"] == 2
    assert result["value"] == 0.0
    assert result["confidence"] == 0.0


def test_get_action_sanitizes_non_finite_latent_and_outputs(neuro_config):
    """Non-finite latent/output values should not propagate to runtime actions."""

    captured = {}

    class _NaNOutputPPO:
        def act(self, z, deterministic=False):
            captured["z"] = np.asarray(z)
            return np.array([0.0]), np.array([np.nan]), np.array([np.inf])

    core = BrainCore(neuro_config, device="cpu")
    core.ppo_agent = _NaNOutputPPO()

    result = core.get_action(np.array([np.nan, np.inf, -np.inf, 1.0], dtype=np.float32))
    assert np.isfinite(captured["z"]).all()
    assert result["action_name"] == "FLAT"
    assert result["action"] == 2

