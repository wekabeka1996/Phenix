from __future__ import annotations

from apps.reference.config_models import ObjectiveEngineDomainConfig, StrategyObjectiveConfig
from apps.reference.domains.objective_engine.pretrade_kernel import evaluate_pretrade_objective
from apps.reference.domains.objective_engine.types import ObjectiveInput, ObjectiveScore


def evaluate_objective(
    inputs: ObjectiveInput,
    domain_config: ObjectiveEngineDomainConfig,
    strategy_config: StrategyObjectiveConfig,
) -> ObjectiveScore:
    return evaluate_pretrade_objective(
        inputs=inputs,
        domain_config=domain_config,
        strategy_config=strategy_config,
    )
