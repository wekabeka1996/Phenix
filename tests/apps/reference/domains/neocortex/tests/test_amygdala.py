"""
Amygdala (Valuation) Tests
"""

import pytest
import numpy as np
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation

@pytest.fixture
def dummy_obs():
    return MarketObservation(
        ts=100.0, 
        mid_price=10.0, 
        volatility=0.1, 
        obi=0.0,
        features_vector=np.zeros(5, dtype=np.float32)
    )

def test_valuation_engine_update(dummy_obs):
    amygdala = ValuationEngine()
    
    # Test with standard reward
    imp = amygdala.update(dummy_obs, reward=1.0)
    assert imp == 1.0
    
    # Test with negative reward
    imp = amygdala.update(dummy_obs, reward=-5.5)
    assert imp == 5.5
    
    # Test with zero reward (should have small epsilon)
    imp = amygdala.update(dummy_obs, reward=0.0)
    assert imp > 0.0
    assert imp < 0.1  # Minimal epsilon

def test_trace_buffer_growth(dummy_obs):
    amygdala = ValuationEngine()
    
    for i in range(150):
        amygdala.update(dummy_obs, reward=0.0)
        
    # Should cap at 100
    assert len(amygdala.trace_buffer) == 100

