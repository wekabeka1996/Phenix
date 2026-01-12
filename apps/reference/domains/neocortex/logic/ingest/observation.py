"""
Market Data Observation Structure

Defines the tensor-ready container for market states.
"""

from dataclasses import dataclass
from typing import Optional, Any
import numpy as np

# Conditional Torch Import (for future integration)
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass(frozen=True)
class MarketObservation:
    """
    Immutable snapshot of market state at a specific timestamp.
    
    Fields:
        ts (float): Unix timestamp
        mid_price (float): Current mid price (reference only, usually normalized out)
        volatility (float): Current volatility metric (e.g. BB Width or ATR)
        obi (float): Order Book Imbalance (-1.0 to 1.0)
        features_vector (np.ndarray): Normalized feature vector [float32]
        
    Note:
        - mid_price is kept for PnL calculation / reference
        - features_vector is the actual input to the Neural Network
    """
    ts: float
    mid_price: float
    volatility: float
    obi: float
    features_vector: np.ndarray
    normalized: bool = False
    
    def __post_init__(self):
        """Validation to ensure types are ML-ready."""
        if self.features_vector.dtype != np.float32:
            # We can't modify frozen dataclass, so we rely on caller or unsafe set
            # Ideally caller handles this. We raise error here to fail fast.
            raise ValueError(
                f"features_vector must be float32, got {self.features_vector.dtype}"
            )
            
    def to_tensor(self, device: str = "cpu") -> Any:
        """
        Convert feature vector to PyTorch tensor.
        
        Args:
            device: 'cpu' or 'cuda' feature device
            
        Returns:
            torch.Tensor: Shape (1, D) ready for model input
        """
        if not HAS_TORCH:
            raise ImportError("PyTorch not installed")
            
        # Convert numpy array to tensor
        # Unsqueeze(0) to add batch dimension -> (1, features)
        t = torch.from_numpy(self.features_vector).to(device)
        return t.unsqueeze(0)

    @property
    def feature_dim(self) -> int:
        return self.features_vector.shape[0]

    def __repr__(self):
        return (
            f"MarketObservation(ts={self.ts:.3f}, price={self.mid_price:.2f}, "
            f"dims={self.feature_dim}, normalized={self.normalized})"
        )
