from __future__ import annotations

import decimal

import pytest


def _base_kwargs() -> dict:
    symbol = "TSTUSDT"
    price = decimal.Decimal("100")
    return {
        "symbol": symbol,
        "features": {"price": str(price), "delta_price": "0", "depth_imbalance": "0.90"},
        "warmup_readiness": {"depth_imbalance": True},
        "price": price,
        "signal_weights": {"depth_imbalance": 1.0},
        "feature_neutrals": {"depth_imbalance": 0.5},
        "essential_features": ["depth_imbalance"],
        "base_threshold": decimal.Decimal("0.10"),
        "regime_name": "DEFAULT",
        "regime_thresholds": {"DEFAULT": 1.0},
        "side_bias_state": None,
        "direction_strength_cfg": {
            "directional_features": ["depth_imbalance"],
            "strength_features": [],
            "strength_alpha": 0.0,
            "strength_cap": 1.0,
        },
        "delta_price_cap_pct": decimal.Decimal("0.005"),
        "scoring_version": "v2",
    }


def test_kernel_rejects_net_zero() -> None:
    from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel

    with pytest.raises(ValueError, match="NRR-NORMALIZE-MODE-INVALID"):
        AuroraScoringKernel.compute(**_base_kwargs(), normalize_mode="net_zero")


def test_kernel_accepts_signed_v2() -> None:
    from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel

    res = AuroraScoringKernel.compute(**_base_kwargs(), normalize_mode="signed_v2")
    assert res.deferred is False
