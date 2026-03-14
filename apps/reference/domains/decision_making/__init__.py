"""
Decision Making Domain

Central decision engine: receives upstream data (features, risk, regime,
portfolio, exposure), dispatches to strategy handlers, and produces trade
intents (proposed / rejected / deferred).

Components:
    - DecisionMaking: Main FSM component (thin facade)
    - AuroraHandler / MdAmrHandler / MeanReversionHandler: Strategy handlers
    - NormalizedRejectReasons: Standardized rejection reason mapping (NRR SSOT)
    - DeferredIntentScheduler: QoS retry scheduling after cooldowns
    - WhyCode: Re-export from vfoundation/core/why_codes.py (canonical SSOT)
    - DecisionLog: Structured JSON logging for decision tracing
    - QuadraticScoringKernel: Canonical scoring engine

See README.md for full file map and event contracts.

Version: 2.0.0
"""

from .decision_making import DecisionMaking
from .normalized_reject_reasons import NormalizedRejectReasons
from .deferred_scheduler import DeferredIntentScheduler
from .why_codes import WhyCode, get_why_description, format_why_with_details
from .dm_log_adapter import DecisionLog
from .schemas import PortfolioStatePayload, PositionData
from .schemas_decision_blocked import DecisionBlockedPayload

# Track B: Mean Reversion handler (optional import)
try:
    from .mean_reversion_handler import MeanReversionHandler
except ImportError:
    MeanReversionHandler = None  # type: ignore

__all__ = [
    "DecisionMaking",
    "NormalizedRejectReasons",
    "DeferredIntentScheduler",
    "WhyCode",
    "get_why_description",
    "format_why_with_details",
    "DecisionLog",
    "PortfolioStatePayload",
    "PositionData",
    "DecisionBlockedPayload",
    "MeanReversionHandler",
]

__version__ = "2.0.0"
