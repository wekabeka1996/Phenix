"""
Episodic Buffer Tests
"""

import pytest
import numpy as np
from logic.memory.buffer import EpisodicBuffer
from logic.ingest.observation import MarketObservation

def create_obs(ts: float):
    return MarketObservation(
        ts=ts,
        mid_price=100.0,
        volatility=0.0,
        obi=0.0,
        features_vector=np.zeros(2, dtype=np.float32)
    )

def test_buffer_fifo():
    buf = EpisodicBuffer(capacity=3)
    
    # Fill buffer
    buf.add(create_obs(1.0), 1.0)
    buf.add(create_obs(2.0), 1.0)
    buf.add(create_obs(3.0), 1.0)
    
    assert len(buf) == 3
    
    # Overflow
    buf.add(create_obs(4.0), 1.0)
    
    # Check simple length
    assert len(buf) == 3
    
    # Check contents (FIFO)
    batch = buf.get_batch(3)
    timestamps = [item[0].ts for item in batch]
    assert timestamps == [2.0, 3.0, 4.0]

def test_get_batch_slicing():
    buf = EpisodicBuffer(capacity=10)
    for i in range(5):
        buf.add(create_obs(float(i)), 1.0)
        
    # Get last 2
    batch = buf.get_batch(2)
    assert len(batch) == 2
    assert batch[0][0].ts == 3.0
    assert batch[1][0].ts == 4.0
    
    # Get more than available
    batch = buf.get_batch(10)
    assert len(batch) == 5
    assert batch[0][0].ts == 0.0

def test_sample_random():
    buf = EpisodicBuffer(capacity=100)
    for i in range(10):
        buf.add(create_obs(float(i)), 1.0)
        
    sample = buf.sample_random(5)
    assert len(sample) == 5
    # Since set logic comparison for objects might be tricky without defined eq,
    # we verify timestamps are unique if we put unique ones in
    ts_set = set(item[0].ts for item in sample)
    assert len(ts_set) == 5
