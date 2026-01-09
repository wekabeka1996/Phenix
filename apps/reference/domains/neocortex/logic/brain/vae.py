"""
Variational Autoencoder (VAE)

Compresses market observations into a stochastic latent representation.
Architecture:
    Encoder: x -> MLP -> (mu, logvar) -> z
    Decoder: z -> MLP -> x_hat
"""

from typing import List, Tuple, Optional
import logging
import numpy as np

try:
    import torch
    import torch.nn as nn
    from torch.nn import functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    # Mock classes for type hinting / runtime safety if torch missing
    class nn:
        Module = object
    class torch:
        Tensor = object
        def randn(*args): return object()

from config_models import VAEConfig

logger = logging.getLogger(__name__)

class VariationalAutoencoder(nn.Module):
    """
    VAE Module for Market Representation Learning.
    """
    
    def __init__(self, config: VAEConfig):
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for VAE")
            
        super().__init__()
        self.config = config
        self.latent_dim = config.latent_dim
        
        # --- Encoder ---
        # Build MLP layers: input -> hidden[0] -> ... -> hidden[-1]
        encoder_dims = [config.input_dim] + config.hidden_dims
        layers = []
        for i in range(len(encoder_dims) - 1):
            layers.append(nn.Linear(encoder_dims[i], encoder_dims[i+1]))
            layers.append(nn.ReLU())
            
        self.encoder_body = nn.Sequential(*layers)
        
        # Heads for Mu and LogVar
        last_hidden = config.hidden_dims[-1]
        self.fc_mu = nn.Linear(last_hidden, self.latent_dim)
        self.fc_logvar = nn.Linear(last_hidden, self.latent_dim)
        
        # --- Decoder ---
        # Reverse hidden dims: latent -> hidden[-1] -> ... -> hidden[0] -> output
        decoder_dims = [self.latent_dim] + list(reversed(config.hidden_dims))
        layers = []
        for i in range(len(decoder_dims) - 1):
            layers.append(nn.Linear(decoder_dims[i], decoder_dims[i+1]))
            layers.append(nn.ReLU())
            
        self.decoder_body = nn.Sequential(*layers)
        
        # Final reconstruction layer
        self.fc_recon = nn.Linear(config.hidden_dims[0], config.input_dim)
        
        # Initialize weights (Use Kaiming init)
        self.apply(self._init_weights)
        
        logger.info(f"VAE Initialized: {config.input_dim} -> {config.hidden_dims} -> {config.latent_dim}")

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)

    def encode(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Encode input into latent parameters.
        Returns: (mu, logvar)
        """
        h = self.encoder_body(x)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        return mu, logvar

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """
        Reparameterization trick: z = mu + std * epsilon
        """
        # If evaluation mode or use_mean, return mu
        if not self.training or self.config.use_mean:
            return mu
            
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + std * eps

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """
        Decode latent z back to observation space.
        """
        h = self.decoder_body(z)
        return self.fc_recon(h)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass.
        Returns: (recon_x, mu, logvar)
        """
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        recon_x = self.decode(z)
        return recon_x, mu, logvar

    @staticmethod
    def loss_function(
        recon_x: torch.Tensor, 
        x: torch.Tensor, 
        mu: torch.Tensor, 
        logvar: torch.Tensor,
        beta: float = 1.0
    ) -> dict:
        """
        Compute VAE Loss = MSE + beta * KLD
        
        Args:
            recon_x: Reconstructed input
            x: Original input
            mu: Latent mean
            logvar: Latent log variance
            beta: KL divergence weight (beta-VAE)
            
        Returns:
            dict containing 'loss', 'mse', 'kld'
        """
        # Reconstruction Loss (MSE)
        # Reduction='sum' or 'mean'? Usually sum over batch, mean over features?
        # Or mean over everything. Standard implementation often sums.
        # We will use Mean to match scale with KLD if we normalize KLD.
        # But commonly sum is used. Let's start with Sum and normalize by batch size later.
        # Actually PyTorch functional.mse_loss default is Mean.
        # Let's use Sum to be explicit about magnitude.
        
        mse = F.mse_loss(recon_x, x, reduction='sum')
        
        # KL Divergence
        # KLD = -0.5 * sum(1 + logvar - mu^2 - logvar.exp())
        kld = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
        
        total_loss = mse + beta * kld
        
        return {
            "loss": total_loss,
            "mse": mse,
            "kld": kld
        }
