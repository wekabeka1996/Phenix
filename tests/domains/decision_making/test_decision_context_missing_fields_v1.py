from decimal import Decimal


def test_decision_context_tracks_missing_required_fields():
    from apps.reference.domains.decision_making.core.context import DecisionContext

    ctx = DecisionContext(symbol="BTCUSDT", ts=1, features={})

    # Force parsing.
    _ = ctx.price
    _ = ctx.trend
    _ = ctx.flow
    _ = ctx.volatility
    _ = ctx.liquidity

    assert ctx.missing_fields.get("price") == "missing"
    assert ctx.missing_fields.get("ema_bias") == "missing"
    assert ctx.missing_fields.get("obi") == "missing"
    assert ctx.missing_fields.get("tfi") == "missing"
    assert ctx.missing_fields.get("volatility_state") == "missing"
    assert ctx.missing_fields.get("depth_imbalance") == "missing"


def test_decision_context_tracks_invalid_fields_and_uses_defaults():
    from apps.reference.domains.decision_making.core.context import DecisionContext

    ctx = DecisionContext(
        symbol="BTCUSDT",
        ts=1,
        features={
            "price": "oops",
            "ema_bias": "oops",
            "obi": "oops",
            "tfi": "oops",
            "volatility_state": "oops",
            "depth_imbalance": "oops",
            "spread_bps": "oops",  # optional
        },
    )

    # Force parsing.
    assert ctx.price == Decimal("0")
    assert ctx.trend.ema_bias == Decimal("0.5")
    assert ctx.flow.obi == Decimal("0")
    assert ctx.flow.tfi == Decimal("0")
    assert ctx.volatility.volatility_state == Decimal("0.5")
    assert ctx.liquidity.depth_imbalance == Decimal("0.5")

    assert ctx.missing_fields.get("price") == "invalid"
    assert ctx.missing_fields.get("ema_bias") == "invalid"
    assert ctx.missing_fields.get("obi") == "invalid"
    assert ctx.missing_fields.get("tfi") == "invalid"
    assert ctx.missing_fields.get("volatility_state") == "invalid"
    assert ctx.missing_fields.get("depth_imbalance") == "invalid"

    # Optional: should be None and tracked as invalid_optional.
    assert ctx.liquidity.spread_bps is None
    assert ctx.missing_fields.get("spread_bps") == "invalid_optional"
