from decimal import Decimal

from apps.reference.domains.execution_position.soft_clip import SoftClipEngine, SoftLimitConfig


def test_soft_clip_clips_by_margin_available_scaled_by_leverage():
    cfg = SoftLimitConfig(
        mode="clip",
        clip_min_notional_usdt=Decimal("10"),
        directional_ratio_max=Decimal("100"),
        side_exposure_usdt=Decimal("1e9"),
        margin_exposure_usdt=Decimal("1100"),
    )
    eng = SoftClipEngine(cfg)

    res = eng.calculate_clipped_size(
        notional_usd=Decimal("5000"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("0"),
        short_margin=Decimal("0"),
        total_margin_exposure=Decimal("1000"),
        symbol_leverage=Decimal("20"),
    )

    # allowed_extra_margin = 1100-1000 = 100; delta_margin_notional = 100*20 = 2000
    assert res.allowed is True
    assert res.clipped_notional == Decimal("2000")
    assert res.original_notional == Decimal("5000")
    assert res.reason == "CLIPPED"


def test_soft_clip_directional_ratio_exceeded_can_zero_out_and_fail_min_clip():
    cfg = SoftLimitConfig(
        mode="clip",
        clip_min_notional_usdt=Decimal("10"),
        directional_ratio_max=Decimal("3"),
        side_exposure_usdt=Decimal("1e9"),
        margin_exposure_usdt=Decimal("1e9"),
    )
    eng = SoftClipEngine(cfg)

    # BUY adds margin = notional/leverage = 1000/10 = 100 -> long=400, short=10 => ratio=40 > 3
    res = eng.calculate_clipped_size(
        notional_usd=Decimal("1000"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("300"),
        short_margin=Decimal("10"),
        total_margin_exposure=Decimal("0"),
        symbol_leverage=Decimal("10"),
    )

    assert res.allowed is False
    assert res.reason == "BELOW_CLIP_MIN"
    assert res.original_notional == Decimal("1000")
