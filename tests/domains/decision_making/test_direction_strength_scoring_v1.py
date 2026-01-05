from __future__ import annotations

from decimal import Decimal

from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
    compute_direction_strength_score,
)


def test_signed_v2_preserves_sign_and_scales_01_neutral_05_features():
    res = compute_direction_strength_score(
        features={"ema_bias": Decimal("0.25")},
        weights={"ema_bias": 1.0},
        neutrals={"ema_bias": 0.5},
        readiness={"ema_bias": True},
        essential_features={"ema_bias"},
        normalize_mode="signed_v2",
        directional_features=["ema_bias"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        symbol="BTCUSDT",
    )
    assert res.deferred is False
    assert res.dir_score < 0
    assert res.final_score == res.dir_score


def test_signed_v2_preserves_sign_delta_price_and_sell_is_reachable():
    res = compute_direction_strength_score(
        features={"delta_price": Decimal("-0.9")},
        weights={"delta_price": 1.0},
        neutrals={"delta_price": 0.0},
        readiness={"delta_price": True},
        essential_features={"delta_price"},
        normalize_mode="signed_v2",
        directional_features=["delta_price"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        symbol="BTCUSDT",
    )
    assert res.deferred is False
    assert res.final_score < 0


def test_strength_amplifies_magnitude_only_and_cannot_flip_sign():
    res = compute_direction_strength_score(
        features={"ema_bias": Decimal("0.0"), "volume_spike": Decimal("1.0")},
        weights={"ema_bias": 1.0, "volume_spike": 1.0},
        neutrals={"ema_bias": 0.5, "volume_spike": 0.0},
        readiness={"ema_bias": True, "volume_spike": True},
        essential_features={"ema_bias"},
        normalize_mode="signed_v2",
        directional_features=["ema_bias"],
        strength_features=["volume_spike"],
        strength_alpha=0.5,
        strength_cap=1.0,
        symbol="BTCUSDT",
    )
    assert res.deferred is False
    assert res.dir_score < 0
    assert res.strength_score >= 0
    assert res.final_score < 0
    assert abs(res.final_score) > abs(res.dir_score)


def test_fail_closed_when_no_directional_features_configured():
    res = compute_direction_strength_score(
        features={"obi": Decimal("1.0")},
        weights={"obi": 1.0},
        neutrals={"obi": 0.0},
        readiness={"obi": True},
        essential_features={"obi"},
        normalize_mode="signed_v2",
        directional_features=[],
        strength_features=["obi"],
        strength_alpha=0.5,
        strength_cap=1.0,
        symbol="BTCUSDT",
    )
    assert res.deferred is True
    assert res.deny_reason == "NRR-NO-DIRECTIONAL-FEATURES-ACTIVE"

