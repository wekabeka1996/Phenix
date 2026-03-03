from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_signals_config_requires_normalize_signals_mode() -> None:
    from apps.reference.config_models import SignalsConfig

    with pytest.raises(ValidationError):
        SignalsConfig(enable_new_metrics=True, delta_price_cap_pct=0.02)


def test_signals_config_rejects_net_zero() -> None:
    from apps.reference.config_models import SignalsConfig

    with pytest.raises(ValidationError):
        SignalsConfig(
            normalize_signals_mode="net_zero",
            enable_new_metrics=True,
            delta_price_cap_pct=0.02,
        )


def test_signals_config_accepts_signed_v2() -> None:
    from apps.reference.config_models import SignalsConfig

    cfg = SignalsConfig(
        normalize_signals_mode="signed_v2",
        enable_new_metrics=True,
        delta_price_cap_pct=0.02,
    )
    assert cfg.normalize_signals_mode == "signed_v2"

