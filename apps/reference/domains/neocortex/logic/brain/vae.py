# QUARANTINED: legacy_runtime
"""
Variational Autoencoder (VAE)

Compresses market observations into a stochastic latent representation.
Architecture:
    Encoder: x -> MLP -> (mu, logvar) -> z
    Decoder: z -> MLP -> x_hat
"""
__quarantined__ = True

from typing import Tuple, Optional
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

from apps.reference.domains.neocortex.config_models import VAEConfig

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
        self.regime_head = None
        regime_aux_cfg = getattr(config, "regime_aux", None)
        self._regime_aux_num_classes = int(
            getattr(regime_aux_cfg, "num_classes", 5) if regime_aux_cfg is not None else 5
        )
        self._regime_aux_num_classes = max(2, self._regime_aux_num_classes)
        if regime_aux_cfg is not None and bool(getattr(regime_aux_cfg, "enabled", False)):
            self.regime_head = nn.Linear(self.latent_dim, self._regime_aux_num_classes)

        # EMA regime distribution for dynamic class-weighting.
        self.register_buffer(
            "regime_class_ema",
            torch.full(
                (self._regime_aux_num_classes,),
                fill_value=1.0 / float(self._regime_aux_num_classes),
                dtype=torch.float32,
            ),
            persistent=True,
        )
        
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

    def predict_regime_logits(self, mu: torch.Tensor) -> Optional[torch.Tensor]:
        """Return auxiliary regime logits from latent mean if head is enabled."""
        if self.regime_head is None:
            return None
        return self.regime_head(mu)

    def get_regime_class_weights(
        self,
        min_weight: float = 0.1,
        max_weight: float = 10.0,
    ) -> torch.Tensor:
        """
        Convert EMA class probabilities to inverse-frequency weights.
        We normalize to mean=1 so CE scale remains stable.
        """
        probs = self.regime_class_ema.clamp_min(1e-6)
        inv = 1.0 / probs
        weights = inv / inv.mean().clamp_min(1e-6)
        return torch.clamp(weights, min=min_weight, max=max_weight)

    def update_regime_class_ema(
        self,
        regime_targets: Optional[torch.Tensor],
        ema_decay: float = 0.99,
    ) -> torch.Tensor:
        """
        Update EMA regime distribution from current labels and return class weights.
        """
        ema_decay = float(np.clip(ema_decay, 0.0, 0.999999))
        if regime_targets is None or regime_targets.numel() == 0:
            return self.get_regime_class_weights()

        with torch.no_grad():
            targets = regime_targets.detach().long().view(-1)
            valid = (targets >= 0) & (targets < self.regime_class_ema.shape[0])
            if not torch.any(valid):
                return self.get_regime_class_weights()

            targets = targets[valid]
            counts = torch.bincount(
                targets,
                minlength=self.regime_class_ema.shape[0],
            ).to(dtype=self.regime_class_ema.dtype, device=self.regime_class_ema.device)
            total = counts.sum().clamp_min(1.0)
            batch_probs = counts / total

            self.regime_class_ema.mul_(ema_decay).add_(
                batch_probs * (1.0 - ema_decay)
            )

        return self.get_regime_class_weights()

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
        beta: float = 1.0,
        free_bits_per_dim: float = 0.0,
        regime_logits: Optional[torch.Tensor] = None,
        regime_targets: Optional[torch.Tensor] = None,
        aux_alpha: float = 0.0,
        class_weights: Optional[torch.Tensor] = None,
    ) -> dict:
        """
        Compute VAE Loss = MSE + beta * KLD
        
        Args:
            recon_x: Reconstructed input
            x: Original input
            mu: Latent mean
            logvar: Latent log variance
            beta: KL divergence weight (beta-VAE)
            regime_logits: Optional logits from auxiliary regime head
            regime_targets: Optional integer targets for auxiliary head
            aux_alpha: CE loss weight
            
        Returns:
            dict containing 'loss', 'mse', 'kld'
        """
        # Reconstruction Loss (scale-invariant to batch size)
        mse = F.mse_loss(recon_x, x, reduction="mean")

        # KL Divergence by latent dimension.
        # This enables per-dimension free-bits and avoids dimension hoarding.
        kld_dim = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp())
        kld_dim_mean = kld_dim.mean(dim=0)
        kld = kld_dim_mean.sum()

        if float(free_bits_per_dim) > 0.0:
            floor = torch.as_tensor(
                float(free_bits_per_dim),
                dtype=kld_dim_mean.dtype,
                device=kld_dim_mean.device,
            )
            kld_loss = torch.maximum(kld_dim_mean, floor).sum()
        else:
            kld_loss = kld

        regime_ce = torch.zeros((), dtype=mse.dtype, device=mse.device)
        if (
            regime_logits is not None
            and regime_targets is not None
            and aux_alpha > 0.0
            and regime_logits.shape[0] == regime_targets.shape[0]
        ):
            ce_weight = None
            if class_weights is not None and class_weights.numel() == regime_logits.shape[-1]:
                ce_weight = class_weights.to(device=regime_logits.device, dtype=regime_logits.dtype)
            regime_ce = F.cross_entropy(
                regime_logits,
                regime_targets.long(),
                weight=ce_weight,
            )

        total_loss = mse + (beta * kld_loss) + (float(aux_alpha) * regime_ce)
        
        return {
            "loss": total_loss,
            "mse": mse,
            "kld": kld,
            "kld_loss": kld_loss,
            "regime_ce": regime_ce,
        }

