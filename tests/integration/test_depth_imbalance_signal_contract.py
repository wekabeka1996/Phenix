from __future__ import annotations

import decimal


def test_depth_imbalance_signal_contract_buy_and_sell_deterministic() -> None:
    """Deterministic contract: depth_imbalance alone must be able to drive BUY and SELL.

    This does NOT use production config.
    It asserts the minimal scoring math contract of AuroraScoringKernel.
    """

    from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel

    symbol = "TSTUSDT"
    price = decimal.Decimal("100")

    # Minimal scoring config:
    # score = (depth_imbalance - 0.5) / 1.0
    # BUY when score >= thr_buy
    # SELL when score <= -thr_sell
    weights = {"depth_imbalance": 1.0}
    neutrals = {"depth_imbalance": 0.5}
    essential = ["depth_imbalance"]

    direction_strength_cfg = {
        "directional_features": ["depth_imbalance"],
        "strength_features": [],
        "strength_alpha": 0.0,
        "strength_cap": 1.0,
    }

    # BUY case: phi far above neutral
    buy = AuroraScoringKernel.compute(
        symbol=symbol,
        features={"price": str(price), "delta_price": "0", "depth_imbalance": "0.90"},
        warmup_readiness={"depth_imbalance": True},
        price=price,
        signal_weights=weights,
        feature_neutrals=neutrals,
        essential_features=essential,
        base_threshold=decimal.Decimal("0.10"),
        regime_name="DEFAULT",
        regime_thresholds={"DEFAULT": 1.0},
        side_bias_state=None,
        direction_strength_cfg=direction_strength_cfg,
        delta_price_cap_pct=decimal.Decimal("0.005"),
        normalize_mode="signed_v2",
    )
    assert not buy.deferred
    assert buy.side == "buy"

    # SELL case: phi far below neutral
    sell = AuroraScoringKernel.compute(
        symbol=symbol,
        features={"price": str(price), "delta_price": "0", "depth_imbalance": "0.10"},
        warmup_readiness={"depth_imbalance": True},
        price=price,
        signal_weights=weights,
        feature_neutrals=neutrals,
        essential_features=essential,
        base_threshold=decimal.Decimal("0.10"),
        regime_name="DEFAULT",
        regime_thresholds={"DEFAULT": 1.0},
        side_bias_state=None,
        direction_strength_cfg=direction_strength_cfg,
        delta_price_cap_pct=decimal.Decimal("0.005"),
        normalize_mode="signed_v2",
    )
    assert not sell.deferred
    assert sell.side == "sell"
