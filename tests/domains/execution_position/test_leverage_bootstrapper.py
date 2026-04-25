"""
LeverageBootstrapper Guard Tests

P2: Verify startup leverage/margin synchronization logic.

Tests:
1. Success sync (margin + leverage changed)
2. Margin change failure blocks symbol
3. Leverage reduction failure blocks symbol
4. Already-correct state skips API calls
5. Full bootstrap run with mixed results
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import logging

# Import will work after implementation
from apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper import (
    LeverageBootstrapper,
    BootstrapResult,
)
from apps.reference.adapters.binance_adapter import (
    MarginChangeError,
    LeverageReductionError,
    MaxLeverageExceededError,
)
from apps.reference.config_models import LeverageConfig


@pytest.fixture
def mock_adapter():
    """Create mock adapter with default "wrong" values to force sync."""
    adapter = MagicMock()
    # Default: wrong margin mode (CROSSED instead of ISOLATED)
    adapter.get_margin_mode = AsyncMock(return_value="cross")
    # Default: wrong leverage (10x instead of target)
    adapter.get_current_leverage = AsyncMock(return_value=10)
    # Default: success on set operations
    adapter.set_margin_mode = AsyncMock(return_value=True)
    adapter.set_leverage = AsyncMock(return_value=True)
    return adapter


@pytest.fixture
def bootstrapper(mock_adapter):
    """Create bootstrapper with mock adapter."""
    return LeverageBootstrapper(
        adapter=mock_adapter,
        logger=logging.getLogger("test"),
    )


class TestSyncSymbol:
    """Test single symbol synchronization."""

    @pytest.mark.asyncio
    async def test_sync_success_changes_both(self, bootstrapper, mock_adapter):
        """Successful sync when both margin and leverage need changing."""
        target = LeverageConfig(
            target=20, mode="ISOLATED", max_notional_value=None)

        result = await bootstrapper.sync_symbol("BTCUSDT", target)

        assert result.success is True
        assert result.symbol == "BTCUSDT"
        assert result.margin_changed is True
        assert result.leverage_changed is True
        mock_adapter.set_margin_mode.assert_awaited_once_with(
            "BTCUSDT", "isolated")
        mock_adapter.set_leverage.assert_awaited_once_with("BTCUSDT", 20)

    @pytest.mark.asyncio
    async def test_sync_skips_when_already_correct(self, bootstrapper, mock_adapter):
        """Skip API calls when state already matches target."""
        # Mock: already correct state
        mock_adapter.get_margin_mode = AsyncMock(return_value="isolated")
        mock_adapter.get_current_leverage = AsyncMock(return_value=20)

        target = LeverageConfig(
            target=20, mode="ISOLATED", max_notional_value=None)
        result = await bootstrapper.sync_symbol("BTCUSDT", target)

        assert result.success is True
        assert result.margin_changed is False
        assert result.leverage_changed is False
        # Should NOT call set methods
        mock_adapter.set_margin_mode.assert_not_awaited()
        mock_adapter.set_leverage.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_margin_change_failure_blocks_symbol(self, bootstrapper, mock_adapter):
        """MarginChangeError blocks symbol and skips leverage change."""
        mock_adapter.set_margin_mode.side_effect = MarginChangeError(
            code=-4048, msg="Position exists"
        )

        target = LeverageConfig(
            target=20, mode="ISOLATED", max_notional_value=None)
        result = await bootstrapper.sync_symbol("ETHUSDT", target)

        assert result.success is False
        assert result.error_code == -4048
        assert "position" in result.error_msg.lower()
        # Should NOT try to set leverage after margin failure (fail-fast)
        mock_adapter.set_leverage.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_margin_change_failure_open_orders(self, bootstrapper, mock_adapter):
        """MarginChangeError with open orders."""
        mock_adapter.set_margin_mode.side_effect = MarginChangeError(
            code=-4047, msg="Open orders exist"
        )

        target = LeverageConfig(
            target=20, mode="ISOLATED", max_notional_value=None)
        result = await bootstrapper.sync_symbol("XRPUSDT", target)

        assert result.success is False
        assert result.error_code == -4047

    @pytest.mark.asyncio
    async def test_leverage_reduction_failure(self, bootstrapper, mock_adapter):
        """LeverageReductionError when trying to reduce in ISOLATED mode."""
        # Margin change OK
        mock_adapter.get_margin_mode = AsyncMock(return_value="isolated")
        # Current leverage higher than target
        mock_adapter.get_current_leverage = AsyncMock(return_value=50)
        mock_adapter.set_leverage.side_effect = LeverageReductionError(
            code=-4161, msg="Cannot reduce leverage in ISOLATED mode with open position"
        )

        # Trying to reduce from 50 to 20
        target = LeverageConfig(
            target=20, mode="ISOLATED", max_notional_value=None)
        result = await bootstrapper.sync_symbol("SOLUSDT", target)

        assert result.success is False
        assert result.error_code == -4161

    @pytest.mark.asyncio
    async def test_max_leverage_exceeded_failure(self, bootstrapper, mock_adapter):
        """MaxLeverageExceededError when position notional too large."""
        mock_adapter.get_margin_mode = AsyncMock(return_value="isolated")
        mock_adapter.set_leverage.side_effect = MaxLeverageExceededError(
            code=-2027, msg="Exceeded max allowable position"
        )

        target = LeverageConfig(
            target=125, mode="ISOLATED", max_notional_value=None)
        result = await bootstrapper.sync_symbol("BTCUSDT", target)

        assert result.success is False
        assert result.error_code == -2027


class TestFullBootstrap:
    """Test full bootstrap run with multiple symbols."""

    @pytest.mark.asyncio
    async def test_bootstrap_all_success(self, bootstrapper, mock_adapter):
        """All symbols sync successfully."""
        targets = {
            "BTCUSDT": LeverageConfig(target=20, mode="ISOLATED", max_notional_value=None),
            "ETHUSDT": LeverageConfig(target=20, mode="ISOLATED", max_notional_value=None),
        }

        results = await bootstrapper.run(targets)

        assert len(results.succeeded) == 2
        assert len(results.failed) == 0
        assert "BTCUSDT" in results.succeeded
        assert "ETHUSDT" in results.succeeded

    @pytest.mark.asyncio
    async def test_bootstrap_mixed_results(self, bootstrapper, mock_adapter):
        """Some symbols fail, some succeed."""
        # BTC will succeed, ETH will fail on margin
        async def margin_side_effect(symbol, mode):
            if symbol == "ETHUSDT":
                raise MarginChangeError(code=-4048, msg="Position exists")
            return True

        mock_adapter.set_margin_mode.side_effect = margin_side_effect

        targets = {
            "BTCUSDT": LeverageConfig(target=20, mode="ISOLATED", max_notional_value=None),
            "ETHUSDT": LeverageConfig(target=20, mode="ISOLATED", max_notional_value=None),
        }

        results = await bootstrapper.run(targets)

        assert len(results.succeeded) == 1
        assert len(results.failed) == 1
        assert "BTCUSDT" in results.succeeded
        assert "ETHUSDT" in results.failed
        # Check failed symbol has error details
        assert results.failures["ETHUSDT"].error_code == -4048

    @pytest.mark.asyncio
    async def test_bootstrap_empty_targets(self, bootstrapper):
        """Empty targets dict returns empty results."""
        results = await bootstrapper.run({})

        assert len(results.succeeded) == 0
        assert len(results.failed) == 0


class TestBootstrapResultAggregation:
    """Test BootstrapResult data structure."""

    def test_bootstrap_results_properties(self):
        """Test BootstrapResults aggregation."""
        from apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper import (
            BootstrapResults,
        )

        results = BootstrapResults()
        results.add_success("BTCUSDT", BootstrapResult(
            symbol="BTCUSDT", success=True, margin_changed=True, leverage_changed=True
        ))
        results.add_failure("ETHUSDT", BootstrapResult(
            symbol="ETHUSDT", success=False, error_code=-4048, error_msg="Position exists"
        ))

        assert results.all_succeeded is False
        assert len(results.succeeded) == 1
        assert len(results.failed) == 1
        assert results.has_failures is True
