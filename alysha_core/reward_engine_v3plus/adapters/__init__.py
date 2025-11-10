"""
ALYSHA Reward Engine V3Plus Adapters

This module provides adapters for integrating the ALYSHA reward engine with different
RL frameworks, primarily PPO.

CONFLICT RESOLUTION:
This __init__.py includes safeguards to prevent import conflicts caused by
duplicate class names between adapters.
"""

import warnings
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Import conflict detection and resolution
_MAIN_ADAPTER_AVAILABLE = False
_SIMPLE_ADAPTER_AVAILABLE = False

try:
    from .ppo_adapter import RewardEngineAPIV3Plus as MainRewardEngineAPIV3Plus
    _MAIN_ADAPTER_AVAILABLE = True
    logger.debug("✅ Main RewardEngineAPIV3Plus loaded from ppo_adapter.py")
except ImportError as e:
    logger.warning(f"❌ Failed to import main RewardEngineAPIV3Plus: {e}")
    MainRewardEngineAPIV3Plus = None

try:
    # NOTE: ppo_adapter_simple.py doesn't exist, commenting out for now
    # from .ppo_adapter_simple import SimpleRewardCalculator
    # _SIMPLE_ADAPTER_AVAILABLE = True
    # logger.debug("✅ SimpleRewardCalculator loaded from ppo_adapter_simple.py")
    _SIMPLE_ADAPTER_AVAILABLE = False
    SimpleRewardCalculator = None
    logger.debug("ℹ️ ppo_adapter_simple.py not available - using main adapter only")
except ImportError as e:
    logger.warning(f"❌ Failed to import SimpleRewardCalculator: {e}")
    SimpleRewardCalculator = None

# No conflict detection needed - RewardEngineAPIV3Plus is only in ppo_adapter.py
# Export main adapter as primary
if _MAIN_ADAPTER_AVAILABLE:
    RewardEngineAPIV3Plus = MainRewardEngineAPIV3Plus
    logger.info("✅ Exporting main RewardEngineAPIV3Plus as primary adapter")
else:
    RewardEngineAPIV3Plus = None
    logger.error("❌ No RewardEngineAPIV3Plus implementation available")

# Export functions for conflict resolution
def get_adapter_status() -> Dict[str, Any]:
    """
    Get status of adapter imports
    
    Returns:
        Dict with adapter availability status
    """
    return {
        'main_adapter_available': _MAIN_ADAPTER_AVAILABLE,
        'simple_adapter_available': _SIMPLE_ADAPTER_AVAILABLE,
        'active_adapter': 'main' if _MAIN_ADAPTER_AVAILABLE else ('simple' if _SIMPLE_ADAPTER_AVAILABLE else 'none'),
        'recommendation': get_recommendation()
    }

def get_recommendation() -> str:
    """Get recommendation for adapter usage"""
    if _MAIN_ADAPTER_AVAILABLE:
        return "Use RewardEngineAPIV3Plus (main adapter) - optimal choice"
    elif _SIMPLE_ADAPTER_AVAILABLE:
        return "Use SimpleRewardCalculator - only option available"
    else:
        return "No adapters available - check imports"

def resolve_conflict_safely():
    """
    Get available adapters for safe usage
    """
    return {
        'recommended': RewardEngineAPIV3Plus,
        'simple_adapter': SimpleRewardCalculator if _SIMPLE_ADAPTER_AVAILABLE else None
    }

# Module exports
__all__ = [
    'RewardEngineAPIV3Plus',          # Primary adapter (safe export)
    'SimpleRewardCalculator',         # Simple adapter (if available)
    'get_adapter_status',             # Status function
    'get_recommendation',             # Recommendation function
    'resolve_conflict_safely',        # Conflict resolution function
]

# Log module initialization status
logger.info(f"✅ ALYSHA adapters initialized successfully - using {get_adapter_status()['active_adapter']} adapter")
