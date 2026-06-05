# QUARANTINED: legacy_runtime
"""
World Model (RNN Dynamics)

Predicts the future state of the market in latent space.
Architecture:
    z_t -> GRU -> z_{t+1}
    
Used for:
    - Hallucination / Dreaming (Simulating futures)
    - Planning (PPO state value estimation)
"""
__quarantined__ = True

from typing import Tuple, Optional
import logging

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class nn:
        Module = object
    class torch:
        Tensor = object

from apps.reference.domains.neocortex.config_models import WorldModelConfig

logger = logging.getLogger(__name__)

class WorldModel(nn.Module):
    """
    Recurrent Dynamics Model.
    Approximates P(z_{t+1} | z_t, a_t, h_t).
    """
    
    def __init__(self, config: WorldModelConfig, input_dim: int, action_dim: int = 0):
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for WorldModel")
            
        super().__init__()
        self.config = config
        self.input_dim = input_dim
        self.action_dim = action_dim
        
        # RNN Body
        # Input: Latent (z) + Action (a)
        rnn_input_size = input_dim + action_dim
        
        self.rnn = nn.GRU(
            input_size=rnn_input_size,
            hidden_size=config.hidden_dim,
            num_layers=config.num_layers,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
            batch_first=True
        )
        
        # Prediction Head
        # Predicts the *change* (delta) or the *next state*?
        # Predicting delta (residual) is usually more stable.
        # z_{t+1} = z_t + delta
        # But for basics, we'll predict z_{t+1} directly as requested.
        self.fc_out = nn.Linear(config.hidden_dim, input_dim)
        
        logger.info(f"WorldModel Initialized: Input={rnn_input_size} -> Hidden={config.hidden_dim} -> Out={input_dim}")

    def forward(self, z: torch.Tensor, action: Optional[torch.Tensor] = None, h: Optional[torch.Tensor] = None) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        One step forward dynamics.
        
        Args:
            z: Latent state (Batch, InputDim) or (Batch, Seq, InputDim)
            action: Action vector (Batch, ActionDim). Optional.
            h: Hidden state.
            
        Returns:
            next_z: Predicted next latent state
            next_h: New hidden state
        """
        # Ensure input is 3D (Batch, Seq, Feat) if RNN expects it
        if z.dim() == 2:
            z = z.unsqueeze(1) # (B, 1, F)
            
        if self.action_dim > 0:
            if action is None:
                # Default zero action
                batch_size, seq_len, _ = z.shape
                action = torch.zeros(batch_size, seq_len, self.action_dim, device=z.device)
            elif action.dim() == 2:
                action = action.unsqueeze(1)
                
            rnn_input = torch.cat([z, action], dim=-1)
        else:
            rnn_input = z
            
        # RNN Step
        out, next_h = self.rnn(rnn_input, h)
        
        # Project representation to latent space
        # Out shape: (Batch, Seq, Hidden)
        next_z = self.fc_out(out)
        
        return next_z, next_h

    def predict_next(self, z: torch.Tensor) -> torch.Tensor:
        """
        Simple stateless prediction (resetting hidden state).
        Useful for 1-step lookahead from a fresh state estimate.
        """
        next_z_seq, _ = self.forward(z)
        # Return matched shape (remove seq dim if input was 2D)
        if z.dim() == 2:
             return next_z_seq.squeeze(1)
        return next_z_seq

