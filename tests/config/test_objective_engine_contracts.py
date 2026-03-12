from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    ObjectiveFeedbackConfig,
    ProviderConfig,
)


def test_current_aurora_config_loads_objective_engine_contract() -> None:
    cfg = ConfigLoader(Path("config/aurora")).load_config()

    assert cfg.domains.objective_engine.enabled is True
    assert "risk" in cfg.domains.objective_engine.components
    assert "max_position_qty" not in cfg.domains.objective_engine.components["risk"].parameters
    assert cfg.strategies.aurora.objective.enabled is True
    assert cfg.strategies.md_amr.objective.enabled is True
    assert cfg.strategies.mean_reversion.objective.enabled is True
    assert cfg.strategies.mean_reversion.objective.regimes


def test_alpha_search_objective_feedback_requires_explicit_fields_when_enabled() -> None:
    with pytest.raises(ValidationError):
        AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(enabled=True),
            },
            objective_feedback=ObjectiveFeedbackConfig(enabled=True),
        )


def test_alpha_search_objective_feedback_window_contract() -> None:
    with pytest.raises(ValidationError):
        ObjectiveFeedbackConfig(
            enabled=True,
            window_trades=5,
            min_trades_before_reweight=6,
            rebalance_every_closed_trades=1,
            quality_metric_weights={"realized_quality_score": 1.0},
            min_provider_weight=0.1,
            max_provider_weight=0.5,
        )
