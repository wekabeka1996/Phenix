"""
Feature Event Parser

Responsible for converting raw event dictionaries (with string decimals)
into strict typed MarketObservation objects.
"""

from typing import Dict, Any, Union
import logging
import numpy as np

from config_models import IngestConfig
from logic.ingest.observation import MarketObservation

logger = logging.getLogger(__name__)

class FeatureParser:
    """Stateful parser that respects IngestConfig."""
    
    def __init__(self, config: IngestConfig):
        self.config = config
        self.feature_indices = {name: i for i, name in enumerate(config.feature_list)}
        self._feature_count = len(config.feature_list)
        
        # Performance optimization: pre-allocate zero vector
        self._empty_vector = np.zeros(self._feature_count, dtype=np.float32)

    def parse(self, payload: Dict[str, Any]) -> MarketObservation:
        """
        Parse raw event payload into MarketObservation.
        
        Args:
            payload: Dictionary containing 'timestamp' (or 'ts'), 'features' (dict),
                     and optional metadata like 'mid_price'.
                     
        Returns:
            MarketObservation
            
        Raises:
            ValueError: If critical fields (ts) are missing.
        """
        # 1. Extract Timestamp
        # Note: timestamp could be 0.0 which is valid but falsy
        ts = payload.get('timestamp')
        if ts is None:
            ts = payload.get('ts')
        if ts is None:
            raise ValueError("Payload missing timestamp")
        ts = float(ts)
        
        # 2. Extract Metadata (Best Effort)
        # Handle string decimals safely
        mid_price = self._safe_float(payload.get('mid_price'), 0.0)
        
        # Volatility & OBI might be in the payload root or inside features
        # We look in root first, then features
        features_dict = payload.get('features')
        
        # If no explicit 'features' dict, assume flat payload
        if features_dict is None:
            features_dict = payload
        elif not isinstance(features_dict, dict):
            logger.warning(f"Field 'features' is not a dict: {type(features_dict)}")
            features_dict = payload
            
        volatility = self._safe_float(payload.get('volatility'), 0.0)
        # Try to find specific features for metadata if not in root
        if volatility == 0.0:
            # Fallback: try 'bb_width' or 'atr' from features
            vol = features_dict.get('bb_width') or features_dict.get('atr')
            volatility = self._safe_float(vol, 0.0)
            
        obi = self._safe_float(payload.get('obi'), 0.0)
        if obi == 0.0:
             obi_val = features_dict.get('obi')
             obi = self._safe_float(obi_val, 0.0)

        # 3. Build Feature Vector
        vector = np.zeros(self._feature_count, dtype=np.float32)
        
        for i, name in enumerate(self.config.feature_list):
            raw_val = features_dict.get(name)
            
            if raw_val is None:
                if self.config.nan_strategy == "zero":
                    val = 0.0
                elif self.config.nan_strategy == "ignore":
                    val = 0.0 # Can't really 'ignore' in a dense vector, 0 is safest
                else: # ffill - not applicable for single observation parsing without state
                    # For a stateless parser, ffill is impossible.
                    # We might handle this in a buffer or wrapper. Here we default to 0.
                    val = 0.0
            else:
                try:
                    val = float(raw_val)
                    if np.isnan(val):
                        val = 0.0 if self.config.nan_strategy == "zero" else val
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse feature '{name}': {raw_val}")
                    val = 0.0
            
            vector[i] = val
            
        return MarketObservation(
            ts=ts,
            mid_price=mid_price,
            volatility=volatility,
            obi=obi,
            features_vector=vector
        )

    def _safe_float(self, value: Union[str, float, int, None], default: float) -> float:
        """Safely convert string/decimal to float."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
