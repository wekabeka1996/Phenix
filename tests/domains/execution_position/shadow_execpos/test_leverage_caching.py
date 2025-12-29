"""
LEVERAGE-FIX: Test that API leverage is cached and used for ROI-based bracket calculation.

Problem: Previously, ROI calculation used config max_leverage (e.g., 20x) instead of
actual API leverage (e.g., 75x or 100x). This caused incorrect SL/TP distances.

Fix: Cache leverage from position updates and use it in _get_bracket_cfg().
"""
import pytest
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
)


class TestLeverageCaching:
    """Test that API leverage is cached and prioritized over config."""

    def test_leverage_cached_from_position_update(self):
        """Verify leverage is cached when position update includes it."""
        ep_cfg = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(
                enabled=True,
                sl_roi_pct=35.0,
                tp_roi_pct=50.0,
            ),
            trailing=TrailingConfig(),
            close=CloseConfig(),
        )

        rt = ExecPosRuntimeV2(
            config={"instruments": {"SOLUSDT": {
                "limits": {"max_leverage": 20}}}},
            adapter=None,
            price_service=None,
            ep_config=ep_cfg,
        )

        # Initially no cached leverage
        assert rt._leverage_by_symbol.get("SOLUSDT") is None

        # Simulate position update WITH leverage from API
        import asyncio

        async def update():
            await rt._handle_single_position_update({
                "symbol": "SOLUSDT",
                "positionAmt": 1.0,
                "entryPrice": 140.0,
                "leverage": 75,  # API leverage = 75x
            })

        asyncio.get_event_loop().run_until_complete(update())

        # Verify leverage is cached
        assert rt._leverage_by_symbol.get("SOLUSDT") == 75

    def test_bracket_cfg_uses_cached_leverage(self):
        """Verify _get_bracket_cfg uses cached API leverage, not config."""
        ep_cfg = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(
                enabled=True,
                sl_roi_pct=35.0,
                tp_roi_pct=50.0,
            ),
            trailing=TrailingConfig(),
            close=CloseConfig(),
        )

        rt = ExecPosRuntimeV2(
            config={"instruments": {"SOLUSDT": {
                "limits": {"max_leverage": 20}}}},
            adapter=None,
            price_service=None,
            ep_config=ep_cfg,
        )

        # Pre-cache API leverage
        rt._leverage_by_symbol["SOLUSDT"] = 75

        # Get bracket config
        cfg = rt._get_bracket_cfg("SOLUSDT")

        # With leverage=75, sl_pct = 35% / 75 = 0.00467 (0.467%)
        # With leverage=20, sl_pct = 35% / 20 = 0.0175 (1.75%)
        expected_sl_pct_approx = 0.35 / 75.0  # ~0.00467

        assert abs(cfg.sl_pct - expected_sl_pct_approx) < 0.0001, (
            f"Expected sl_pct ~{expected_sl_pct_approx:.5f} (75x), got {cfg.sl_pct:.5f}"
        )

    def test_bracket_cfg_falls_back_to_config_leverage(self):
        """Verify fallback to config leverage when no cached API leverage."""
        ep_cfg = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(
                enabled=True,
                sl_roi_pct=35.0,
                tp_roi_pct=50.0,
            ),
            trailing=TrailingConfig(),
            close=CloseConfig(),
        )

        rt = ExecPosRuntimeV2(
            config={"instruments": {"SOLUSDT": {
                "limits": {"max_leverage": 20}}}},
            adapter=None,
            price_service=None,
            ep_config=ep_cfg,
        )

        # No cached leverage
        assert rt._leverage_by_symbol.get("SOLUSDT") is None

        # Get bracket config
        cfg = rt._get_bracket_cfg("SOLUSDT")

        # With config leverage=20, sl_pct = 35% / 20 = 0.0175 (1.75%)
        expected_sl_pct_approx = 0.35 / 20.0  # 0.0175

        assert abs(cfg.sl_pct - expected_sl_pct_approx) < 0.0001, (
            f"Expected sl_pct ~{expected_sl_pct_approx:.5f} (20x config), got {cfg.sl_pct:.5f}"
        )


class TestLeverageImpactOnBrackets:
    """Test the practical impact of leverage on SL/TP prices."""

    @pytest.mark.parametrize("leverage,expected_sl_pct", [
        (10, 0.035),    # 35% ROI / 10x = 3.5% price distance
        (20, 0.0175),   # 35% ROI / 20x = 1.75% price distance
        (50, 0.007),    # 35% ROI / 50x = 0.7% price distance
        (75, 0.00467),  # 35% ROI / 75x = 0.467% price distance
        (100, 0.0035),  # 35% ROI / 100x = 0.35% price distance
        (125, 0.0028),  # 35% ROI / 125x = 0.28% price distance
    ])
    def test_sl_pct_scales_with_leverage(self, leverage, expected_sl_pct):
        """Verify SL% correctly scales inversely with leverage."""
        ep_cfg = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(
                enabled=True,
                sl_roi_pct=35.0,  # 35% ROI target for SL
                tp_roi_pct=50.0,
            ),
            trailing=TrailingConfig(),
            close=CloseConfig(),
        )

        rt = ExecPosRuntimeV2(
            config={},
            adapter=None,
            price_service=None,
            ep_config=ep_cfg,
        )

        # Set cached leverage
        rt._leverage_by_symbol["SOLUSDT"] = leverage

        cfg = rt._get_bracket_cfg("SOLUSDT")

        assert abs(cfg.sl_pct - expected_sl_pct) < 0.0001, (
            f"At {leverage}x: expected sl_pct={expected_sl_pct}, got {cfg.sl_pct}"
        )

    def test_sl_tp_prices_for_high_leverage(self):
        """Test actual SL/TP prices with 75x leverage (realistic testnet scenario)."""
        ep_cfg = ExecutionPositionConfig(
            aggregated_oco=AggregatedOcoConfig(
                enabled=True,
                sl_roi_pct=35.0,
                tp_roi_pct=50.0,
            ),
            trailing=TrailingConfig(),
            close=CloseConfig(),
        )

        rt = ExecPosRuntimeV2(
            config={},
            adapter=None,
            price_service=None,
            ep_config=ep_cfg,
        )

        # Simulate: SOL entry at $140, leverage 75x
        entry_price = 140.0
        leverage = 75
        rt._leverage_by_symbol["SOLUSDT"] = leverage

        cfg = rt._get_bracket_cfg("SOLUSDT")

        # Calculate expected prices
        sl_pct = 0.35 / 75.0  # 0.00467 = 0.467%
        tp_pct = 0.50 / 75.0  # 0.00667 = 0.667%
        tp_rr = tp_pct / sl_pct  # 50/35 = 1.4286

        # For LONG position:
        expected_sl = entry_price * (1 - sl_pct)  # 140 * 0.99533 = 139.35
        expected_tp = entry_price * \
            (1 + sl_pct * tp_rr)  # 140 * 1.00667 = 140.93

        # Verify via position_to_dict
        from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
        pos = PositionState(symbol="SOLUSDT", qty=1.0,
                            avg_entry_price=entry_price)
        result = rt._position_to_dict(pos)

        assert result["leverage_used"] == leverage
        assert abs(result["sl_pct"] - sl_pct) < 0.0001
        assert abs(result["target_sl_price"] - expected_sl) < 0.1, (
            f"Expected SL={expected_sl:.2f}, got {result['target_sl_price']:.2f}"
        )
        assert abs(result["target_tp_price"] - expected_tp) < 0.1, (
            f"Expected TP={expected_tp:.2f}, got {result['target_tp_price']:.2f}"
        )
