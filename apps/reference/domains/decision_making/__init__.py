"""
Decision Making Domain

Core trading decision engine that aggregates alpha signals, applies risk controls
and QoS, and generates executable trade intents based on portfolio state, market
regime, and risk budgets.

Components:
    - DecisionMaking: Main FSM component for trade intent generation
    - NormalizedRejectReasons: Standardized rejection reason mapping (NRR codes)
    - DeferredIntentScheduler: QoS retry scheduling after cooldowns
    - ROIExitStrategy: Position ROI monitoring and CMD:CLOSE emission
    - WhyCodes: Standardized WHY chain codes for observability
    - DecisionLog: Structured JSON logging for decision tracing
    - MeanReversionHandler: Track B integration for 1m MR strategy

Events Consumed:
    - EVT:FEATURES_CALCULATED
    - EVT:RISK_ASSESSMENT_COMPLETED
    - EVT:PORTFOLIO_STATE_UPDATED
    - EVT:REGIME_DETECTED
    - EVT:EXPOSURE_SUMMARY_UPDATED
    - EVT:TICK_RECEIVED (for MR handler)

Events Produced:
    - EVT:TRADE_INTENT_PROPOSED
    - EVT:ALPHA_SCORE_CALCULATED
    - CMD:CLOSE (via ROIExitStrategy)

Version: 1.3.0
"""

from .decision_making import DecisionMaking
from .normalized_reject_reasons import NormalizedRejectReasons
from .deferred_scheduler import DeferredIntentScheduler
from .roi_exit_strategy import ROIExitStrategy
from .why_codes import WhyCode, get_why_description, format_why_with_details
from .dm_log_adapter import DecisionLog
from .schemas import PortfolioStatePayload, PositionData

# Track B: Mean Reversion handler (optional import)
try:
    from .mean_reversion_handler import MeanReversionHandler
except ImportError:
    MeanReversionHandler = None  # type: ignore

__all__ = [
    "DecisionMaking",
    "NormalizedRejectReasons",
    "DeferredIntentScheduler",
    "ROIExitStrategy",
    "WhyCode",
    "get_why_description",
    "format_why_with_details",
    "DecisionLog",
    "PortfolioStatePayload",
    "PositionData",
    "MeanReversionHandler",
]

__version__ = "1.3.0"
