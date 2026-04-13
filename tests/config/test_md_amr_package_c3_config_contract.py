from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import MDAMRHoldQualityConfig


def test_current_aurora_config_loads_md_amr_hold_quality_block() -> None:
    cfg = ConfigLoader(Path("config/aurora")).load_config()

    hold_quality = cfg.strategies.md_amr.hold_quality
    assert hold_quality.expected_progress_grace_frac == pytest.approx(0.25)
    assert hold_quality.time_decay_weight == pytest.approx(0.35)
    assert hold_quality.progress_deficit_weight == pytest.approx(0.45)


def test_md_amr_hold_quality_config_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MDAMRHoldQualityConfig(
            expected_progress_grace_frac=0.25,
            time_decay_weight=0.35,
            progress_deficit_weight=0.45,
            unknown_field=True,
        )


def test_md_amr_hold_quality_config_rejects_penalty_budget_above_one() -> None:
    with pytest.raises(ValidationError):
        MDAMRHoldQualityConfig(
            expected_progress_grace_frac=0.25,
            time_decay_weight=0.70,
            progress_deficit_weight=0.45,
        )
