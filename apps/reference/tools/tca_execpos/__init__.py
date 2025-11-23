"""
ExecPos TCA (Transaction Cost Analysis) Tool
============================================

Provides analytics for execution quality, slippage, and fees based on ExecPos WAL records.
"""
from .model import ExecPosTCATradeRecord, ExecPosTCASummary
from .engine import compute_tca_for_period
