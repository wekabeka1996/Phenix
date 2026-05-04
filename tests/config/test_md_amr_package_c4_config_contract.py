from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import (
    MDAMRContextValidityConfig,
    MDAMRProgressTrackingConfig,
    MDAMRSetupQualityConfig,
    MDAMRWeightsConfig,
)


def test_current_aurora_config_loads_md_amr_context_validity_block() -> None:
    cfg = ConfigLoader(Path("config/aurora")).load_config()

    progress_tracking = cfg.strategies.md_amr.progress_tracking
    assert progress_tracking.early_progress_max_pct == pytest.approx(0.25)
    assert progress_tracking.partial_progress_max_pct == pytest.approx(0.70)
    assert progress_tracking.near_completion_max_pct == pytest.approx(1.00)

    setup_quality = cfg.strategies.md_amr.setup_quality
    assert setup_quality.penetration_depth_full_scale == pytest.approx(0.50)
    assert setup_quality.channel_width_pct_full_scale == pytest.approx(1.00)
    assert setup_quality.volatility_z_full_penalty == pytest.approx(3.00)

    context_validity = cfg.strategies.md_amr.context_validity
    assert context_validity.regime_confidence_floor == pytest.approx(0.35)
    assert context_validity.regime_confidence_valid == pytest.approx(0.60)
    assert context_validity.valid_score_min == pytest.approx(0.70)
    assert context_validity.invalid_score_max == pytest.approx(0.35)


def test_md_amr_progress_tracking_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValidationError):
        MDAMRProgressTrackingConfig(
            early_progress_max_pct=0.70,
            partial_progress_max_pct=0.25,
            near_completion_max_pct=1.00,
        )


def test_md_amr_setup_quality_rejects_non_positive_scales() -> None:
    with pytest.raises(ValidationError):
        MDAMRSetupQualityConfig(
            penetration_depth_full_scale=0.0,
            channel_width_pct_full_scale=1.00,
            volatility_z_full_penalty=3.00,
        )


def test_md_amr_weights_reject_zero_sum_budget() -> None:
    with pytest.raises(ValidationError):
        MDAMRWeightsConfig(d1=0.0, h1=0.0, m30=0.0, m15=0.0)


def test_md_amr_context_validity_config_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MDAMRContextValidityConfig(
            regime_confidence_floor=0.35,
            regime_confidence_valid=0.60,
            volatility_z_weakening=1.50,
            volatility_z_invalid=3.00,
            channel_width_pct_floor=0.10,
            channel_width_pct_valid=1.00,
            regime_weight=0.35,
            volatility_weight=0.20,
            structure_weight=0.20,
            progress_alignment_weight=0.25,
            valid_score_min=0.70,
            invalid_score_max=0.35,
            unknown_field=True,
        )


def test_md_amr_context_validity_config_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValidationError):
        MDAMRContextValidityConfig(
            regime_confidence_floor=0.60,
            regime_confidence_valid=0.35,
            volatility_z_weakening=1.50,
            volatility_z_invalid=3.00,
            channel_width_pct_floor=0.10,
            channel_width_pct_valid=1.00,
            regime_weight=0.35,
            volatility_weight=0.20,
            structure_weight=0.20,
            progress_alignment_weight=0.25,
            valid_score_min=0.70,
            invalid_score_max=0.35,
        )


def test_md_amr_context_validity_config_rejects_weight_sum_drift() -> None:
    with pytest.raises(ValidationError):
        MDAMRContextValidityConfig(
            regime_confidence_floor=0.35,
            regime_confidence_valid=0.60,
            volatility_z_weakening=1.50,
            volatility_z_invalid=3.00,
            channel_width_pct_floor=0.10,
            channel_width_pct_valid=1.00,
            regime_weight=0.40,
            volatility_weight=0.20,
            structure_weight=0.20,
            progress_alignment_weight=0.25,
            valid_score_min=0.70,
            invalid_score_max=0.35,
        )
