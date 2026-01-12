"""
Amygdala - Valuation Engine

Responsible for assigning 'Importance' (Value) to experiences.
Used for Prioritized Experience Replay (PER) and Advantage Estimation.
"""

from collections import deque
from typing import Deque, Tuple
import logging

from logic.ingest.observation import MarketObservation

logger = logging.getLogger(__name__)

TRACE_DECAY_DEFAULT = 0.95
MAX_TRACE_LEN = 100
EPSILON = 1e-5

class ValuationEngine:
    """
    Computes intrinsic and extrinsic value of observations.
    
    Current Logic (Phase 1):
    - Importance = |Reward| (Simple extrinsic magnitude)
    
    Future Logic (Phase 3):
    - GAE (Generalized Advantage Estimation)
    - TD-Error (Temporal Difference)
    - Eligibility Traces
    """
    
    def __init__(self, trace_decay: float = TRACE_DECAY_DEFAULT):
        self.trace_decay = trace_decay
        # Buffer to store recent (obs, value_estimate) for trace calculation
        # Each item: (timestamp, estimated_value)
        self.trace_buffer: Deque[Tuple[float, float]] = deque(maxlen=MAX_TRACE_LEN)
        
    def update(self, obs: MarketObservation, reward: float = 0.0) -> float:
        """
        Calculate importance score for the given observation.
        
        Args:
            obs: The market snapshot
            reward: Immediate reward received (if any)
            
        Returns:
            float: Importance score (positive scalar)
        """
        # TODO [Phase 3]: Implement Value Network forward pass
        # v_pred = self.value_net(obs.to_tensor())
        
        # simplified Phase 1 logic:
        # Importance is high if we got a significant reward/penalty
        importance = abs(reward)
        
        # Base importance for every tick (so we don't discard everything)
        # TODO: removing this might be wanted for sparse storage, 
        # but for now we want to keep data flowing.
        # Let's use a small epsilon.
        importance = max(importance, EPSILON)
        
        # Trace management (Placeholder)
        self.trace_buffer.append((obs.ts, 0.0)) # 0.0 value estimate for now
        
        return importance
        
    def reset(self):
        """Clear trace buffers."""
        self.trace_buffer.clear()
