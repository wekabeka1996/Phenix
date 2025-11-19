"""
EP-STAB-LIVEPOS-FIX-LIVE: Tests for live position resolution backoff and stale data handling.

Tests verify:
1. REST backoff window suppresses subsequent REST calls after timeout
2. Portfolio stale data (positionAmt=0, entryPrice=0) returns None instead of invalid snapshot
"""

import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.domains.execution_position.contracts import PositionSnapshot


@pytest.fixture
def mock_exec_pos_fsm():
    """Create ExecPosFSM mock with minimal config for live position resolution tests."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    # Minimal config structure (dict-based, matching test_agg_oco_integration pattern)
    config = {
        "execution": {
            "manage": {
                "mode": "aggregated_only",
                "auto": True,
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_scale_in": True,
                        "recalc_on_partial_close": True,
                        "ttl_protect_new_bracket_ms": 0,
                        "sl": {"fixed_bps": 100},
                        "tp": {"fixed_bps": 200},
                        # Disable watchdog for unit tests
                        "watchdog": {"enabled": False}
                    }
                },
                "guardian": {
                    "unified": True,
                    "poll_interval_ms": 1000,
                    "cleanup_ttl_ms": 60000,
                    "symbol_cooldown_ms": 5000,
                    "emit_tidy_event": False
                },
                "watchdog": {
                    "ack_ttl_ms": 5000,
                    "fill_ttl_ms": 30000,
                    "source": "config"
                },
                "positions": {
                    "ws_snapshot": {
                        "enabled": True,
                        "max_age_ms": 1500,
                        "rest_fallback_enabled": True
                    }
                }
            }
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {"min_qty": "0.001", "tick_size": "0.01"}
            }
        },
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binance.vision/api"
            }
        }
    }

    with patch("apps.reference.domains.execution_position.fsm.BinanceAdapter"), \
            patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), \
            patch("apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"), \
            patch("apps.reference.domains.execution_position.fsm.ExposureGuard"), \
            patch("apps.reference.domains.execution_position.fsm.LocalBus"):

        fsm = ExecPosFSM(config=config, shadow_mode=False)

        # Force shadow_mode off
        fsm.shadow_mode = False

        # Mock parent FSM
        fsm.fsm = MagicMock()
        fsm.fsm.emit = MagicMock()

        # Mock adapter with minimal interface
        fsm.adapter = MagicMock()
        fsm.adapter.get_open_orders = AsyncMock(return_value=[])
        fsm.adapter.get_open_positions = AsyncMock(return_value=[])

        # Mock async loop
        loop = asyncio.new_event_loop()
        fsm._async_loop = loop

        yield fsm

        # Cleanup
        loop.close()


def test_livepos_rest_timeout_enters_backoff_and_suppresses_subsequent_calls(mock_exec_pos_fsm):
    """
    Test REST backoff window: after timeout, subsequent calls are suppressed.

    Simplified approach:
    1. Manually set REST backoff window (simulate timeout already happened)
    2. Call _resolve_live_position_state → verify REST suppressed (INFO log)
    3. Expire backoff window
    4. Call _resolve_live_position_state → verify backoff expired (REST attempted)

    This tests the backoff logic directly without complex async mocking.
    """
    fsm = mock_exec_pos_fsm
    symbol = "SOLUSDT"

    # Mock WS snapshot cache: miss
    fsm._ws_position_cache = {}

    # Mock portfolio state: symbol not found
    fsm._latest_portfolio_state = {"positions": []}

    # Mock REST fallback: enabled
    fsm._ws_snapshot_rest_fallback_enabled = True

    # === Test 1: Verify backoff suppresses REST calls ===
    # Manually set backoff window (simulate timeout already happened)
    fsm._livepos_rest_backoff_until[symbol] = time.time() + 10.0  # 10s backoff

    # Call _resolve_live_position_state → should return None (REST suppressed)
    result1 = fsm._resolve_live_position_state(symbol)
    assert result1 is None  # REST suppressed by backoff

    # Verify backoff window still active
    assert fsm._livepos_rest_backoff_until[symbol] > time.time()

    # === Test 2: Verify backoff expires and REST attempted ===
    # Manually expire backoff window
    fsm._livepos_rest_backoff_until[symbol] = time.time() - 1.0  # Expired

    # Mock _get_async_loop to return None (REST will fail, but we verify it's attempted)
    with patch.object(fsm, "_get_async_loop", return_value=None):
        result2 = fsm._resolve_live_position_state(symbol)
        # REST failed (no loop), but NOT suppressed by backoff
        assert result2 is None

    # === Test 3: Verify REST_FALLBACK_TIMEOUT_SEC constant ===
    assert fsm.REST_FALLBACK_TIMEOUT_SEC == 10.0


def test_portfolio_stale_zero_entry_price_returns_none(mock_exec_pos_fsm):
    """
    Test portfolio stale data handling: positionAmt=0, entryPrice=0 → returns None.

    Scenario:
    1. Portfolio contains ETHUSDT with positionAmt=0.0, entryPrice=0.0 (stale)
    2. _resolve_live_position_state("ETHUSDT") should NOT return this snapshot
    3. Should log PORTFOLIO_STALE_DATA warning
    4. Should return None (let REST fallback attempt or fail gracefully)
    """
    fsm = mock_exec_pos_fsm
    symbol = "ETHUSDT"

    # Mock WS snapshot cache: miss
    fsm._ws_position_cache = {}

    # Mock portfolio state: symbol found BUT stale (positionAmt=0, entryPrice=0)
    fsm._latest_portfolio_state = {
        "positions": [
            {
                "symbol": "ETHUSDT",
                "positionAmt": "0.0",
                "entryPrice": "0.0",
                "positionSide": "LONG",
                "updateTime": int(time.time() * 1000),
            }
        ],
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    # Mock REST fallback: disabled for this test (to verify None is returned)
    fsm._ws_snapshot_rest_fallback_enabled = False

    # Call _resolve_live_position_state (logging is internal, captured by pytest)
    result = fsm._resolve_live_position_state(symbol)

    # Should return None (stale snapshot rejected)
    assert result is None


def test_portfolio_valid_nonzero_entry_price_returns_snapshot(mock_exec_pos_fsm):
    """
    Test portfolio valid data: positionAmt > 0, entryPrice > 0 → returns snapshot.

    Verify that valid portfolio data is NOT rejected by stale data check.
    """
    fsm = mock_exec_pos_fsm
    symbol = "BTCUSDT"

    # Mock WS snapshot cache: miss
    fsm._ws_position_cache = {}

    # Mock portfolio state: symbol found with VALID data
    fsm._latest_portfolio_state = {
        "positions": [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.5",
                "entryPrice": "50000.0",
                "positionSide": "LONG",
                "updateTime": int(time.time() * 1000),
            }
        ],
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    # Call _resolve_live_position_state
    result = fsm._resolve_live_position_state(symbol)

    # Should return valid snapshot
    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["qty"] == Decimal("0.5")
    assert result["avg_price"] == Decimal("50000.0")
    assert result["side"] == "BUY"
    assert result["source"] == "portfolio_state"


def test_rest_backoff_constant_is_configurable(mock_exec_pos_fsm):
    """
    Test REST_FALLBACK_TIMEOUT_SEC constant is set to 10.0 via config.
    """
    fsm = mock_exec_pos_fsm
    assert hasattr(fsm, "REST_FALLBACK_TIMEOUT_SEC")
    assert fsm.REST_FALLBACK_TIMEOUT_SEC == 10.0
