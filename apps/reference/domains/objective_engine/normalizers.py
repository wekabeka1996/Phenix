import math

def sigmoid_normalize(value: float, center: float = 0.0, scale: float = 1.0) -> float:
    """
    Stateless non-linear normalizer.
    Maps unbounded values to (0, 1).
    """
    try:
        # Avoid math overflow
        z = (value - center) / scale
        if z > 20: return 1.0
        if z < -20: return 0.0
        return 1.0 / (1.0 + math.exp(-z))
    except OverflowError:
        return 1.0 if value > center else 0.0

def clip_normalize(value: float, min_val: float, max_val: float) -> float:
    """
    Stateless linear clip normalizer.
    Maps to [0, 1] linearly within bounds.
    """
    if value <= min_val: return 0.0
    if value >= max_val: return 1.0
    
    range_span = max_val - min_val
    if range_span <= 1e-8: return 0.0
    
    return (value - min_val) / range_span
