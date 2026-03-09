"""
optimization/research — Optuna Research Domain.

Lightweight, flexible hyperparameter tuning for selective weight optimization.
Does NOT replace the production 3-stage AuroraOptimizer pipeline.

Public API:
    from optimization.research import SelectiveOptimizer
    from optimization.research.weight_registry import list_groups, resolve_paths
"""

from optimization.research.selective_optimizer import (
    SelectiveOptimizer,
    ResearchObjectiveMode,
    ResearchStudyConfig,
    ResearchGates,
)

__all__ = [
    "SelectiveOptimizer",
    "ResearchObjectiveMode",
    "ResearchStudyConfig",
    "ResearchGates",
]
