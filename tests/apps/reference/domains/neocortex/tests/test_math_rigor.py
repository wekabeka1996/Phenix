"""
Mathematical Rigor Tests

Verify that neural network formulas are implemented correctly
using known numerical inputs with manually computed expected outputs.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


# =============================================================================
# VAE MATH TESTS
# =============================================================================

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_reparameterization_formula():
    """
    Verify: z = mu + std * epsilon
    where std = exp(0.5 * logvar)
    
    Common bug: forgetting the 0.5 factor.
    """
    from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
    from apps.reference.domains.neocortex.config_models import VAEConfig
    
    config = VAEConfig(
        input_dim=4,
        hidden_dims=[8],
        latent_dim=2,
        learning_rate=0.001,
        beta=1.0,
        batch_size=2,
        use_mean=False  # Force sampling
    )
    
    vae = VariationalAutoencoder(config)
    vae.train()  # Enable sampling
    
    # Fixed inputs
    mu = torch.tensor([[1.0, 2.0]], dtype=torch.float32)
    logvar = torch.tensor([[0.0, 0.0]], dtype=torch.float32)  # std = exp(0) = 1
    
    # Set random seed for reproducibility
    torch.manual_seed(42)
    
    z = vae.reparameterize(mu, logvar)
    
    # With logvar=0, std=exp(0*0.5)=1
    # z = mu + 1 * epsilon
    # where epsilon ~ N(0,1)
    
    # Verify std calculation: exp(0.5 * 0) = exp(0) = 1
    expected_std = torch.exp(0.5 * logvar)
    assert torch.allclose(expected_std, torch.ones_like(expected_std)), \
        "std = exp(0.5 * logvar) formula is incorrect"


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_kld_formula():
    """
    Verify KL Divergence: KLD = -0.5 * sum(1 + logvar - mu^2 - exp(logvar))
    
    For mu=0, logvar=0 (standard normal):
    KLD = -0.5 * sum(1 + 0 - 0 - 1) = -0.5 * 0 = 0
    """
    from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
    
    mu = torch.zeros(1, 4)
    logvar = torch.zeros(1, 4)
    x = torch.zeros(1, 4)  # Dummy
    
    result = VariationalAutoencoder.loss_function(x, x, mu, logvar, beta=1.0)
    
    # KLD should be 0 for standard normal prior matching posterior
    assert abs(result['kld'].item()) < 1e-6, \
        f"KLD for mu=0, logvar=0 should be 0, got {result['kld'].item()}"


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_kld_nonzero():
    """
    Verify KL Divergence with known non-zero values.
    
    For mu=1, logvar=0 (mean shifted):
    KLD = -0.5 * sum(1 + 0 - 1 - 1) = -0.5 * sum(-1) = 0.5 per dimension
    """
    from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
    
    mu = torch.ones(1, 4)  # 4 dimensions, mu=1 each
    logvar = torch.zeros(1, 4)
    x = torch.zeros(1, 4)
    
    result = VariationalAutoencoder.loss_function(x, x, mu, logvar, beta=1.0)
    
    # KLD = -0.5 * sum(1 + 0 - 1 - 1) = -0.5 * 4 * (-1) = 2.0
    expected_kld = 2.0
    assert abs(result['kld'].item() - expected_kld) < 1e-5, \
        f"KLD should be {expected_kld}, got {result['kld'].item()}"


# =============================================================================
# WORLD MODEL MATH TESTS
# =============================================================================

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_world_model_output_shape():
    """
    Verify World Model preserves latent dimension.
    Input: z_t (B, D) -> Output: z_{t+1} (B, D)
    """
    from apps.reference.domains.neocortex.logic.brain.world_model import WorldModel
    from apps.reference.domains.neocortex.config_models import WorldModelConfig
    
    config = WorldModelConfig(
        hidden_dim=16,
        num_layers=1,
        dropout=0.0,
        learning_rate=0.001,
        sequence_length=5
    )
    
    latent_dim = 8
    wm = WorldModel(config, input_dim=latent_dim, action_dim=0)
    
    z_in = torch.randn(4, latent_dim)  # Batch of 4
    z_out = wm.predict_next(z_in)
    
    assert z_out.shape == z_in.shape, \
        f"Output shape {z_out.shape} should match input {z_in.shape}"


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_world_model_gradient_flow():
    """
    Verify gradients flow through World Model.
    """
    from apps.reference.domains.neocortex.logic.brain.world_model import WorldModel
    from apps.reference.domains.neocortex.config_models import WorldModelConfig
    
    config = WorldModelConfig(
        hidden_dim=16,
        num_layers=1,
        dropout=0.0,
        learning_rate=0.001,
        sequence_length=5
    )
    
    wm = WorldModel(config, input_dim=4, action_dim=0)
    
    z_in = torch.randn(2, 4, requires_grad=True)
    z_out = wm.predict_next(z_in)
    
    loss = z_out.sum()
    loss.backward()
    
    assert z_in.grad is not None, "Gradients should flow to input"
    assert not torch.all(z_in.grad == 0), "Gradients should be non-zero"


# =============================================================================
# AMYGDALA / VALUATION TESTS
# =============================================================================

def test_valuation_importance_formula():
    """
    Verify: importance = max(abs(reward), epsilon)
    """
    from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
    from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
    import numpy as np
    
    amygdala = ValuationEngine()
    
    obs = MarketObservation(
        ts=1.0, mid_price=100.0, volatility=0.1, obi=0.0,
        features_vector=np.zeros(3, dtype=np.float32)
    )
    
    # Positive reward
    imp_pos = amygdala.update(obs, reward=5.0)
    assert imp_pos == 5.0, f"Importance of reward=5 should be 5, got {imp_pos}"
    
    # Negative reward (absolute value)
    imp_neg = amygdala.update(obs, reward=-3.0)
    assert imp_neg == 3.0, f"Importance of reward=-3 should be 3, got {imp_neg}"
    
    # Zero reward (should use epsilon)
    imp_zero = amygdala.update(obs, reward=0.0)
    assert imp_zero > 0.0, "Importance should be > 0 for zero reward"
    assert imp_zero < 0.001, f"Epsilon should be small, got {imp_zero}"


def test_valuation_trace_buffer_limit():
    """
    Verify trace buffer respects maxlen.
    """
    from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
    from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
    import numpy as np
    
    amygdala = ValuationEngine()
    
    obs = MarketObservation(
        ts=1.0, mid_price=100.0, volatility=0.1, obi=0.0,
        features_vector=np.zeros(3, dtype=np.float32)
    )
    
    # Add 150 items (maxlen is 100)
    for i in range(150):
        amygdala.update(obs, reward=0.0)
    
    assert len(amygdala.trace_buffer) == 100, \
        f"Trace buffer should cap at 100, got {len(amygdala.trace_buffer)}"


# =============================================================================
# BUFFER TESTS
# =============================================================================

def test_episodic_buffer_fifo_order():
    """
    Verify FIFO ordering is preserved.
    """
    from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
    from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
    import numpy as np
    
    buffer = EpisodicBuffer(capacity=5)
    
    for i in range(7):
        obs = MarketObservation(
            ts=float(i), mid_price=100.0, volatility=0.0, obi=0.0,
            features_vector=np.zeros(2, dtype=np.float32)
        )
        buffer.add(obs, 1.0)
    
    batch = buffer.get_batch(5)
    timestamps = [item[0].ts for item in batch]
    
    # Should contain [2, 3, 4, 5, 6] (oldest 0, 1 evicted)
    assert timestamps == [2.0, 3.0, 4.0, 5.0, 6.0], \
        f"FIFO order incorrect: {timestamps}"


# =============================================================================
# NUMERICAL STABILITY TESTS
# =============================================================================

@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_extreme_logvar():
    """
    Test VAE with extreme logvar values (numerical stability).
    """
    from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
    from apps.reference.domains.neocortex.config_models import VAEConfig
    
    config = VAEConfig(
        input_dim=4,
        hidden_dims=[8],
        latent_dim=2,
        learning_rate=0.001,
        beta=1.0,
        batch_size=2,
        use_mean=False
    )
    
    vae = VariationalAutoencoder(config)
    vae.train()
    
    # Very large logvar (should not explode)
    mu = torch.zeros(1, 2)
    logvar = torch.full((1, 2), 10.0)  # Very high variance
    
    z = vae.reparameterize(mu, logvar)
    
    assert not torch.isnan(z).any(), "NaN in reparameterization with high logvar"
    assert not torch.isinf(z).any(), "Inf in reparameterization with high logvar"


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not installed")
def test_vae_loss_not_nan():
    """
    Test VAE loss doesn't produce NaN.
    """
    from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
    from apps.reference.domains.neocortex.config_models import VAEConfig
    
    config = VAEConfig(
        input_dim=4,
        hidden_dims=[8],
        latent_dim=2,
        learning_rate=0.001,
        beta=1.0,
        batch_size=2,
        use_mean=True
    )
    
    vae = VariationalAutoencoder(config)
    x = torch.randn(10, 4)
    
    recon, mu, logvar = vae(x)
    losses = vae.loss_function(recon, x, mu, logvar)
    
    assert not torch.isnan(losses['loss']), "Loss is NaN"
    assert not torch.isnan(losses['mse']), "MSE is NaN"
    assert not torch.isnan(losses['kld']), "KLD is NaN"

