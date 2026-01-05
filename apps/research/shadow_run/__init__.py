"""
Shadow Run - Backtesting on Feature Logs

A system for testing strategy configurations against historical feature data
without risking real capital.

Main Components:
- ShadowEngine: Core simulation engine
- compare_configs: Compare multiple configurations
- run_optimization: Find optimal weights via grid search
"""

from apps.research.shadow_run.shadow_engine import (
    ShadowEngine,
    ShadowResults,
    Trade,
    Position,
)

__all__ = [
    "ShadowEngine",
    "ShadowResults", 
    "Trade",
    "Position",
]
