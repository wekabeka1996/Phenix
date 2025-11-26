"""
E-004 Tests: Entry Price Flow Validation
R3-D1 Tests: Guard-loop and Account-update-sync anti-double-apply

RID: E-004-ENTRY-PRICE-FLOW
RID: R3-D1-BRACKET-GUARD

Tests that entryPrice is correctly extracted from:
1. Binance WS ACCOUNT_UPDATE (short keys: s, pa, ep)
2. REST positionRisk (long keys: symbol, positionAmt, entryPrice)
3. Ensures BRACKETS_SKIPPED_NO_VALID_ENTRY_PRICE never logs when position has valid data.

R3-D1 Tests:
4. Guard blocks guard_loop when in_flight/awaiting_snapshot
5. Guard blocks account_update_sync when in_flight/awaiting_snapshot
6. Guard allows trade_executed to proceed even when awaiting_snapshot
"""

import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2, BracketStatus


class TestAdapterAccountUpdateNormalization:
    """Test that adapter normalizes Binance WS short keys to long keys."""

    def test_account_update_normalizes_position_short_keys(self):
        """Binance WS uses short keys (s, pa, ep) -> adapter normalizes to (symbol, positionAmt, entryPrice)."""
        # Binance WS ACCOUNT_UPDATE raw format
        ws_message = {
            "e": "ACCOUNT_UPDATE",
            "E": 1732600000000,
            "T": 1732600000000,
            "a": {
                "m": "ORDER",
                "B": [{"a": "USDT", "wb": "1000.00", "cw": "1000.00", "bc": "0"}],
                "P": [
                    {
                        "s": "SOLUSDT",           # short key for symbol
                        "pa": "2.0",               # short key for positionAmt
                        "ep": "138.26",            # short key for entryPrice <-- CRITICAL
                        "cr": "0",                 # cumRealized
                        "up": "0.50",              # unrealizedProfit
                        "mt": "cross",             # marginType
                        "iw": "0",                 # isolatedWallet
                        "ps": "BOTH"               # positionSide
                    }
                ]
            }
        }

        # Mock adapter
        adapter = BinanceExecutionAdapter.__new__(BinanceExecutionAdapter)
        adapter._session = None
        adapter._shadow_mode = False
        adapter.fsm_core = MagicMock()
        adapter._server_time_offset_ms = 0

        # Capture emitted payload
        emitted_payloads = []

        def capture_emit(event_kind, payload, source):
            emitted_payloads.append(payload)
        adapter.fsm_core.emit = capture_emit

        # Call handler
        adapter._handle_account_update(ws_message)

        # Verify emit called
        assert len(emitted_payloads) == 1
        payload = emitted_payloads[0]

        # Verify positions normalized
        assert "positions" in payload
        positions = payload["positions"]
        assert len(positions) == 1

        pos = positions[0]
        # Long keys should be present after normalization
        assert pos["symbol"] == "SOLUSDT", "symbol should be normalized from 's'"
        assert pos["positionAmt"] == "2.0", "positionAmt should be normalized from 'pa'"
        assert pos["entryPrice"] == "138.26", "entryPrice should be normalized from 'ep'"
        assert pos["unrealizedProfit"] == "0.50", "unrealizedProfit should be normalized from 'up'"

    def test_account_update_handles_already_long_keys(self):
        """If WS sends long keys (testnet sometimes does), normalization still works."""
        ws_message = {
            "e": "ACCOUNT_UPDATE",
            "E": 1732600000000,
            "a": {
                "B": [],
                "P": [
                    {
                        "symbol": "BNBUSDT",       # already long key
                        "positionAmt": "-0.2",     # already long key
                        "entryPrice": "860.50",    # already long key
                        "unrealizedProfit": "-1.0"
                    }
                ]
            }
        }

        adapter = BinanceExecutionAdapter.__new__(BinanceExecutionAdapter)
        adapter._session = None
        adapter._shadow_mode = False
        adapter.fsm_core = MagicMock()
        adapter._server_time_offset_ms = 0

        emitted_payloads = []
        adapter.fsm_core.emit = lambda k, p, s: emitted_payloads.append(p)

        adapter._handle_account_update(ws_message)

        payload = emitted_payloads[0]
        pos = payload["positions"][0]

        assert pos["symbol"] == "BNBUSDT"
        assert pos["positionAmt"] == "-0.2"
        assert pos["entryPrice"] == "860.50"


class TestRuntimePositionUpdate:
    """Test that runtime parses normalized position payloads correctly."""

    @pytest.mark.asyncio
    async def test_handle_single_position_update_with_normalized_keys(self):
        """Runtime should extract entry_price from normalized 'entryPrice' key."""
        # Create minimal runtime
        runtime = ExecPosRuntimeV2.__new__(ExecPosRuntimeV2)
        runtime._positions_by_symbol = {}
        runtime._orders_snapshot_state = {}
        runtime._orders_snapshot_ts = {}
        runtime._position_snapshot_ts = {}
        runtime._open_orders_by_symbol = {}
        runtime._guard_loop_task = None
        runtime._metrics = {}

        # Mock methods that would be called
        runtime._mark_position_snapshot = MagicMock()
        runtime._ensure_guard_loop_running = MagicMock()
        runtime._run_watchdog_analysis = AsyncMock()
        runtime._maybe_stop_guard_loop = MagicMock()

        # Normalized payload (from adapter)
        normalized_payload = {
            "symbol": "SOLUSDT",
            "positionAmt": "2.0",
            "entryPrice": "138.26",
            "unrealizedProfit": "0.50",
            "marginType": "cross",
            "positionSide": "BOTH",
        }

        await runtime._handle_single_position_update(normalized_payload)

        # Verify position state
        assert "SOLUSDT" in runtime._positions_by_symbol
        pos = runtime._positions_by_symbol["SOLUSDT"]
        assert pos.qty == 2.0, "qty should be parsed from positionAmt"
        assert pos.avg_entry_price == 138.26, "avg_entry_price should be 138.26 from entryPrice"

    @pytest.mark.asyncio
    async def test_handle_single_position_update_fallback_to_short_keys(self):
        """Runtime should fallback to short keys (s, pa, ep) if long keys missing."""
        runtime = ExecPosRuntimeV2.__new__(ExecPosRuntimeV2)
        runtime._positions_by_symbol = {}
        runtime._orders_snapshot_state = {}
        runtime._orders_snapshot_ts = {}
        runtime._position_snapshot_ts = {}
        runtime._open_orders_by_symbol = {}
        runtime._guard_loop_task = None
        runtime._metrics = {}

        runtime._mark_position_snapshot = MagicMock()
        runtime._ensure_guard_loop_running = MagicMock()
        runtime._run_watchdog_analysis = AsyncMock()
        runtime._maybe_stop_guard_loop = MagicMock()

        # Raw WS payload (short keys - shouldn't happen after adapter fix, but defensive)
        raw_payload = {
            "s": "ETHUSDT",
            "pa": "-0.5",
            "ep": "3500.00",
        }

        await runtime._handle_single_position_update(raw_payload)

        assert "ETHUSDT" in runtime._positions_by_symbol
        pos = runtime._positions_by_symbol["ETHUSDT"]
        assert pos.qty == -0.5
        assert pos.avg_entry_price == 3500.0

    @pytest.mark.asyncio
    async def test_missing_entry_price_logs_warning(self, caplog):
        """If qty > 0 but entry_price = 0, should log warning."""
        import logging
        caplog.set_level(logging.WARNING)

        runtime = ExecPosRuntimeV2.__new__(ExecPosRuntimeV2)
        runtime._positions_by_symbol = {}
        runtime._orders_snapshot_state = {}
        runtime._orders_snapshot_ts = {}
        runtime._position_snapshot_ts = {}
        runtime._open_orders_by_symbol = {}
        runtime._guard_loop_task = None
        runtime._metrics = {}

        runtime._mark_position_snapshot = MagicMock()
        runtime._ensure_guard_loop_running = MagicMock()
        runtime._run_watchdog_analysis = AsyncMock()
        runtime._maybe_stop_guard_loop = MagicMock()

        # Broken payload: qty but no entry price
        broken_payload = {
            "symbol": "BTCUSDT",
            "positionAmt": "0.01",
            "entryPrice": "0",  # Invalid!
        }

        await runtime._handle_single_position_update(broken_payload)

        # Should log warning
        assert any("POSITION_UPDATE_MISSING_ENTRY_PRICE" in r.message for r in caplog.records), \
            "Should log warning when entry_price=0 with non-zero qty"


class TestE2EAccountUpdateToRuntimeFlow:
    """End-to-end test: WS ACCOUNT_UPDATE -> Adapter normalize -> Runtime parse."""

    @pytest.mark.asyncio
    async def test_full_flow_entry_price_preserved(self):
        """Full flow: WS message with short keys -> adapter normalizes -> runtime gets correct entry_price."""
        # Step 1: Simulate WS message
        ws_message = {
            "e": "ACCOUNT_UPDATE",
            "E": 1732600000000,
            "a": {
                "B": [],
                "P": [
                    {
                        "s": "SOLUSDT",
                        "pa": "1.0",
                        "ep": "140.00",  # This is the entry price we must preserve!
                        "up": "2.50",
                    }
                ]
            }
        }

        # Step 2: Adapter normalizes
        adapter = BinanceExecutionAdapter.__new__(BinanceExecutionAdapter)
        adapter._session = None
        adapter._shadow_mode = False
        adapter.fsm_core = MagicMock()
        adapter._server_time_offset_ms = 0

        captured_payload = []
        adapter.fsm_core.emit = lambda k, p, s: captured_payload.append(p)

        adapter._handle_account_update(ws_message)

        assert len(captured_payload) == 1
        normalized_positions = captured_payload[0]["positions"]
        assert normalized_positions[0]["entryPrice"] == "140.00"

        # Step 3: Runtime parses
        runtime = ExecPosRuntimeV2.__new__(ExecPosRuntimeV2)
        runtime._positions_by_symbol = {}
        runtime._orders_snapshot_state = {}
        runtime._orders_snapshot_ts = {}
        runtime._position_snapshot_ts = {}
        runtime._open_orders_by_symbol = {}
        runtime._guard_loop_task = None
        runtime._metrics = {}

        runtime._mark_position_snapshot = MagicMock()
        runtime._ensure_guard_loop_running = MagicMock()
        runtime._run_watchdog_analysis = AsyncMock()
        runtime._maybe_stop_guard_loop = MagicMock()

        await runtime._handle_single_position_update(normalized_positions[0])

        # Final verification: entry_price is 140.00, not 0!
        pos = runtime._positions_by_symbol["SOLUSDT"]
        assert pos.qty == 1.0
        assert pos.avg_entry_price == 140.0, \
            f"Expected entry_price=140.0 but got {pos.avg_entry_price}. E-004 BUG NOT FIXED!"


class TestR3D1BracketGuard:
    """
    R3-D1: Guard-loop and account_update_sync anti-double-apply protection.

    When brackets are in_flight or awaiting_snapshot, low-priority reasons
    (guard_loop, account_update_sync) should be blocked to prevent duplicates.
    High-priority reasons (trade_executed, brackets_recovery) should proceed.
    """

    def _make_runtime_with_bracket_status(self, symbol: str, status: BracketStatus):
        """Create minimal runtime with pre-set BracketStatus."""
        runtime = ExecPosRuntimeV2.__new__(ExecPosRuntimeV2)
        runtime._bracket_status = {symbol: status}
        runtime._metrics = {}
        runtime._execution_service = AsyncMock()
        runtime._execution_service.place_bracket_sl = AsyncMock(
            return_value="fake_order_id")
        runtime._execution_service.place_bracket_tp = AsyncMock(
            return_value="fake_order_id")
        runtime._execution_service.cancel_order = AsyncMock(return_value=True)
        runtime.guardian = None  # Mock guardian attribute
        return runtime

    @pytest.mark.asyncio
    async def test_guard_loop_blocked_when_awaiting_snapshot(self, caplog):
        """reason=guard_loop should be BLOCKED when awaiting_snapshot=True."""
        import logging
        caplog.set_level(logging.INFO)

        status = BracketStatus(
            last_reason="trade_executed",
            last_started_ts=time.time() - 1.0,
            in_flight=False,
            awaiting_snapshot=True  # <-- brackets placed, waiting for confirmation
        )
        runtime = self._make_runtime_with_bracket_status("SOLUSDT", status)

        # Mock position and plan
        position = MagicMock()
        position.qty = 1.0
        plan = MagicMock()
        plan.actions = []

        await runtime._apply_bracket_plan("SOLUSDT", position, plan, reason="guard_loop")

        # Should be skipped
        assert runtime._metrics.get(
            "brackets_skipped_guard_loop_in_flight", 0) == 1
        assert any(
            "SKIP_BRACKETS_LOW_PRIORITY" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_account_update_sync_blocked_when_awaiting_snapshot(self, caplog):
        """reason=account_update_sync should be BLOCKED when awaiting_snapshot=True (R3-D1 FIX)."""
        import logging
        caplog.set_level(logging.INFO)

        status = BracketStatus(
            last_reason="trade_executed",
            last_started_ts=time.time() - 0.5,  # trade_executed started 0.5s ago
            in_flight=False,
            awaiting_snapshot=True  # still waiting for snapshot confirmation
        )
        runtime = self._make_runtime_with_bracket_status("SOLUSDT", status)

        position = MagicMock()
        position.qty = 1.0
        plan = MagicMock()
        plan.actions = []

        await runtime._apply_bracket_plan("SOLUSDT", position, plan, reason="account_update_sync")

        # account_update_sync should now be blocked too!
        assert runtime._metrics.get(
            "brackets_skipped_guard_loop_in_flight", 0) == 1
        assert any("SKIP_BRACKETS_LOW_PRIORITY" in r.message and "account_update_sync" in r.message
                   for r in caplog.records), \
            "account_update_sync should be blocked by R3-D1 guard"

    @pytest.mark.asyncio
    async def test_trade_executed_allowed_even_when_in_flight(self):
        """reason=trade_executed should NOT be blocked (it's high priority)."""
        status = BracketStatus(
            last_reason="guard_loop",
            last_started_ts=time.time() - 0.1,
            in_flight=True,  # something in flight
            awaiting_snapshot=False
        )
        runtime = self._make_runtime_with_bracket_status("SOLUSDT", status)

        position = MagicMock()
        position.qty = 1.0
        plan = MagicMock()
        plan.actions = []  # empty plan so it returns early but doesn't skip

        await runtime._apply_bracket_plan("SOLUSDT", position, plan, reason="trade_executed")

        # trade_executed should NOT be blocked
        assert runtime._metrics.get(
            "brackets_skipped_guard_loop_in_flight", 0) == 0

    @pytest.mark.asyncio
    async def test_guard_not_triggered_when_awaiting_snapshot_false(self):
        """If awaiting_snapshot=False, guard_loop should proceed normally."""
        status = BracketStatus(
            last_reason="",
            last_started_ts=0,
            in_flight=False,
            awaiting_snapshot=False  # No pending brackets
        )
        runtime = self._make_runtime_with_bracket_status("SOLUSDT", status)

        position = MagicMock()
        position.qty = 1.0
        plan = MagicMock()
        plan.actions = []

        await runtime._apply_bracket_plan("SOLUSDT", position, plan, reason="guard_loop")

        # Should NOT be blocked
        assert runtime._metrics.get(
            "brackets_skipped_guard_loop_in_flight", 0) == 0
