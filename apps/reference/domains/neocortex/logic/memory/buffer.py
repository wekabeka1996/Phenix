"""
Episodic Memory Buffer

Stores sequential market observations.
Used for:
1. PPO Rollout collection (Sequence of N states)
2. Experience Replay (if off-policy)
3. Context window for models
"""

from collections import deque
from typing import List, Tuple, Any
import logging
import random

from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation

logger = logging.getLogger(__name__)

class EpisodicBuffer:
    """
    Fixed-size rolling buffer for market experiences.
    """
    
    def __init__(self, capacity: int):
        if capacity < 2:
            raise ValueError(f"Capacity must be >= 2, got {capacity}")
        self.capacity = capacity
        # Stores (MarketObservation, importance_score)
        self._buffer: deque = deque(maxlen=capacity)
        
    def add(self, obs: MarketObservation, importance: float):
        """
        Add a new experience to memory.
        
        Args:
            obs: Market state
            importance: Priority/Value score
        """
        self._buffer.append((obs, importance))
        
    def get_batch(self, size: int) -> List[Tuple[MarketObservation, float]]:
        """
        Get a batch of experiences.
        
        Configurable behavior:
        by default, for PPO, we usually need trajectories.
        However, standard 'get_batch' often implies random sampling.
        
        For Phase 1 & PPO Rollouts, we return the *most recent* N items (Sequence).
        This preserves temporal order which is critical for Financial Time Series.
        
        Args:
            size: Number of items to retrieve
            
        Returns:
            List of (Observation, Importance), ordered by time (Oldest -> Newest)
        """
        if size > len(self._buffer):
            # Return everything we have if requested size > current size
            return list(self._buffer)
            
        # Efficiently slice the last N items from deque
        # Deque doesn't support slicing directly, so we convert to list
        # Optimization: indices are (len - size) to end
        # But list(deque) is O(N). For buffer ~10k, this is fine (~100us).
        
        all_items = list(self._buffer)
        return all_items[-size:]
    
    def sample_random(self, size: int) -> List[Tuple[MarketObservation, float]]:
        """Return random batch (for Off-Policy training)."""
        if len(self._buffer) < size:
            return list(self._buffer)
        return random.sample(self._buffer, size)

    def __len__(self):
        return len(self._buffer)
        
    def clear(self):
        self._buffer.clear()

