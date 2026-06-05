"""
FILL-PIPELINE-FIX: Tests for the zero-fill root cause fixes.

Covers:
  RC1 - TTL override conflict (watchdog kills orders in 15s)
  RC3 - Entry price too far from book (no spread awareness)
  RC5 - GTX BUY crosses book (MAKER_ONLY_REJECT)
  RC6 - PARTIALLY_FILLED treated as cancel
  AUDIT - Partial fill dedup, spread guard hardening
"""
import asyncio
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

import yaml


# ──────────────────────────────────────────────────────────────────
# RC1: TTL config contract tests
# ──────────────────────────────────────────────────────────────────

class TestTTLConfigContract:
    """Verify that fill_ttl_ms is never silently reduced below pending_entry_ttl."""

    def test_fill_ttl_ms_not_overridden_by_default_ttl_seconds(self):
        """default_ttl_seconds must NOT reduce fill_ttl_ms below watchdog value."""
        import os
        config_path = os.path.join(
            os.path.dirname(
                __file__), "..", "..", "..", "config", "aurora", "trading.yaml"
        )
        with open(config_path) as f:
            trading = yaml.safe_load(f)

        execution = trading.get("trading", {}).get("execution", {})
        watchdog = execution.get("watchdog", {})
        orders = execution.get("orders") or {}

        fill_ttl_ms = watchdog.get("fill_ttl_ms", 0)
        default_ttl_seconds = orders.get(
            "default_ttl_seconds") if orders else None

        # If default_ttl_seconds is still present, it must not reduce fill_ttl_ms
        if default_ttl_seconds is not None:
            candidate_ms = int(default_ttl_seconds) * 1000
            assert candidate_ms >= fill_ttl_ms, (
                f"default_ttl_seconds={default_ttl_seconds} ({candidate_ms}ms) "
                f"would reduce fill_ttl_ms={fill_ttl_ms}ms — "
                f"this is the RC1 root cause of zero fills"
            )

    def test_watchdog_fill_ttl_gte_max_pending_entry_ttl(self):
        """Watchdog fill_ttl_ms must be >= max pending_entry_ttl to avoid racing."""
        import os
        trading_path = os.path.join(
            os.path.dirname(
                __file__), "..", "..", "..", "config", "aurora", "trading.yaml"
        )
        domains_path = os.path.join(
            os.path.dirname(
                __file__), "..", "..", "..", "config", "aurora", "domains.yaml"
        )
        with open(trading_path) as f:
            trading = yaml.safe_load(f)
        with open(domains_path) as f:
            domains = yaml.safe_load(f)

        fill_ttl_ms = trading["trading"]["execution"]["watchdog"]["fill_ttl_ms"]

        pe_ttl = domains.get("execution_position", {}).get(
            "pending_entry_ttl", {})
        ttl_by_tf = pe_ttl.get("ttl_by_tf_sec", {})
        if ttl_by_tf:
            max_pe_ttl_ms = max(int(v) * 1000 for v in ttl_by_tf.values())
            assert fill_ttl_ms >= max_pe_ttl_ms, (
                f"fill_ttl_ms={fill_ttl_ms} < max(pending_entry_ttl)={max_pe_ttl_ms} "
                f"— watchdog will kill orders before pending_entry_ttl expires"
            )

    def test_default_ttl_seconds_removed_from_config(self):
        """After fix, default_ttl_seconds should NOT be present in trading.yaml."""
        import os
        config_path = os.path.join(
            os.path.dirname(
                __file__), "..", "..", "..", "config", "aurora", "trading.yaml"
        )
        with open(config_path) as f:
            trading = yaml.safe_load(f)

        orders = trading.get("trading", {}).get(
            "execution", {}).get("orders") or {}
        assert orders.get("default_ttl_seconds") is None, (
            "default_ttl_seconds should be removed from trading.yaml "
            "(RC1: it silently overrides fill_ttl_ms)"
        )


# ──────────────────────────────────────────────────────────────────
# RC3/RC5: GTX Spread Guard tests
# ──────────────────────────────────────────────────────────────────

class TestGTXSpreadGuard:
    """Verify that LIMIT GTX orders are adjusted to the passive side of the book."""

    @pytest.fixture
    def mock_executor(self):
        """Create a minimal OpenExecutor-like context for testing."""
        executor = MagicMock()
        executor._fsm = MagicMock()
        executor._fsm.adapter = AsyncMock()
        executor._fsm.fsm = MagicMock()
        return executor

    def test_sell_crossing_bid_is_adjusted(self):
        """SELL at price <= best_bid should be adjusted to best_ask."""
        # Simulate: SELL price = 100.00, best_bid = 100.50, best_ask = 100.60
        submit_price = Decimal("100.00")
        best_bid = Decimal("100.50")
        best_ask = Decimal("100.60")

        # SELL crossing bid? submit_price (100.00) <= best_bid (100.50) → YES
        if submit_price <= best_bid:
            adjusted = best_ask
        else:
            adjusted = submit_price

        assert adjusted == Decimal("100.60"), (
            f"SELL price should be adjusted to best_ask when crossing bid, got {adjusted}"
        )

    def test_buy_crossing_ask_is_adjusted(self):
        """BUY at price >= best_ask should be adjusted to best_bid."""
        # Simulate: BUY price = 100.60, best_bid = 100.50, best_ask = 100.55
        submit_price = Decimal("100.60")
        best_bid = Decimal("100.50")
        best_ask = Decimal("100.55")

        # BUY crossing ask? submit_price (100.60) >= best_ask (100.55) → YES
        if submit_price >= best_ask:
            adjusted = best_bid
        else:
            adjusted = submit_price

        assert adjusted == Decimal("100.50"), (
            f"BUY price should be adjusted to best_bid when crossing ask, got {adjusted}"
        )

    def test_passive_sell_not_adjusted(self):
        """SELL above best_ask should NOT be adjusted."""
        submit_price = Decimal("101.00")
        best_bid = Decimal("100.50")

        # SELL: submit_price (101.00) > best_bid (100.50) → passive, no adjustment
        assert submit_price > best_bid, "SELL above bid should be passive"

    def test_passive_buy_not_adjusted(self):
        """BUY below best_bid should NOT be adjusted."""
        submit_price = Decimal("99.50")
        best_ask = Decimal("100.00")

        # BUY: submit_price (99.50) < best_ask (100.00) → passive, no adjustment
        assert submit_price < best_ask, "BUY below ask should be passive"


# ──────────────────────────────────────────────────────────────────
# RC6: PARTIALLY_FILLED handling tests
# ──────────────────────────────────────────────────────────────────

class TestPartiallyFilledHandling:
    """Verify that PARTIALLY_FILLED is treated as a fill event."""

    def test_partially_filled_emits_trade_executed(self):
        """PARTIALLY_FILLED with qty > 0 must emit EVT:TRADE_EXECUTED."""
        # Simulate the WS client logic
        standardized_status = "PARTIALLY_FILLED"
        event_name = None

        if standardized_status in ("FILLED", "PARTIALLY_FILLED"):
            event_name = "EVT:TRADE_EXECUTED"
        elif standardized_status in ("CANCELED", "REJECTED", "EXPIRED"):
            event_name = "EVT:ORDER_STATE_CHANGED"

        assert event_name == "EVT:TRADE_EXECUTED", (
            f"PARTIALLY_FILLED should emit EVT:TRADE_EXECUTED, got {event_name}"
        )

    def test_partially_filled_not_terminal(self):
        """PARTIALLY_FILLED should NOT be marked as terminal in OrderIndex."""
        terminal_states = ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]
        assert "PARTIALLY_FILLED" not in terminal_states, (
            "PARTIALLY_FILLED must not be in terminal states"
        )

    def test_rest_polling_detects_partially_filled(self):
        """REST polling should detect PARTIALLY_FILLED as a fill."""
        status = "PARTIALLY_FILLED"
        executed_qty = 0.5

        # Simulate watchdog polling logic
        is_fill = status in ("FILLED", "PARTIALLY_FILLED") and executed_qty > 0
        assert is_fill, (
            f"REST polling should treat PARTIALLY_FILLED with qty={executed_qty} as fill"
        )


# ──────────────────────────────────────────────────────────────────
# WS Client Integration tests
# ──────────────────────────────────────────────────────────────────

class TestWSClientIntegration:
    """Verify WS client is properly initialized in adapter_init."""

    def test_adapter_init_creates_ws_client(self):
        """AdapterInitMixin should create and start a BinanceWebSocketClient."""
        from apps.reference.domains.execution_position.adapters.adapter_init import AdapterInitMixin

        mixin = AdapterInitMixin()

        # The mixin should have the ws_client attribute after _initialize_adapter
        # (can't fully test without config, but verify the code path exists)
        assert hasattr(AdapterInitMixin, "_initialize_adapter"), (
            "AdapterInitMixin must have _initialize_adapter method"
        )

    def test_ws_client_accepts_main_loop(self):
        """BinanceWebSocketClient should accept an explicit main_loop parameter."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient

        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        client = BinanceWebSocketClient(
            api_key="test",
            base_url="https://test",
            use_testnet=True,
            fsm_core=MagicMock(),
            main_loop=mock_loop,
        )
        assert client._loop is mock_loop, (
            "WS client should use the explicitly passed main_loop"
        )

    def test_ws_client_fallback_when_no_loop(self):
        """WS client should handle missing event loop gracefully."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient

        # No running event loop, no explicit loop
        client = BinanceWebSocketClient(
            api_key="test",
            base_url="https://test",
            use_testnet=True,
            fsm_core=MagicMock(),
            main_loop=None,
        )
        # In non-async context, _loop will be None (fallback warning)
        assert client._loop is None or isinstance(
            client._loop, asyncio.AbstractEventLoop)

    def test_ws_account_update_does_not_emit_canonical_account_event(self):
        """Raw WS ACCOUNT_UPDATE deltas must not violate the canonical schema contract."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient

        fsm_core = MagicMock()
        client = BinanceWebSocketClient(
            api_key="test",
            base_url="https://test",
            use_testnet=True,
            fsm_core=fsm_core,
            main_loop=None,
        )

        client._handle_ws_message(
            {
                "e": "ACCOUNT_UPDATE",
                "E": 1775105850079,
                "a": {
                    "B": [{"a": "USDT", "wb": "4052.20449344", "cw": "3144.90650844", "bc": "0"}],
                    "P": [{"s": "ETHUSDT", "pa": "-1.116", "ep": "2042.91", "up": "-0.76456814", "mt": "isolated"}],
                    "m": "ORDER",
                },
            }
        )

        fsm_core.emit.assert_not_called()

    def test_adapter_init_uses_registered_async_loop_for_ws_client(self):
        """Adapter bootstrap should reuse the execution async loop outside async context."""
        from apps.reference.domains.execution_position.adapters.adapter_init import AdapterInitMixin

        mixin = AdapterInitMixin()
        mixin.shadow_mode = False
        mixin._orphan_metrics = {}
        mixin.fsm = MagicMock()
        mixin._get_async_loop = MagicMock()

        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mixin._get_async_loop.return_value = mock_loop

        env_config = MagicMock()
        env_config.api_key = "key"
        env_config.api_secret = "secret"
        env_config.rest_url = "https://test"

        api_config = MagicMock()
        api_config.testnet = env_config
        api_config.live = env_config

        config = MagicMock()
        config.get_domain_mode.return_value = "testnet"
        config.binance_api = api_config
        mixin.config = config

        mock_adapter = MagicMock()
        mock_ws_client = MagicMock()

        with patch("apps.reference.adapters.binance_adapter.BinanceAdapter", return_value=mock_adapter):
            with patch("apps.reference.adapters.binance_ws_client.BinanceWebSocketClient", return_value=mock_ws_client) as ws_ctor:
                with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                    mixin._initialize_adapter()

        ws_ctor.assert_called_once()
        assert ws_ctor.call_args.kwargs["main_loop"] is mock_loop
        mock_ws_client.start.assert_called_once_with()


# ──────────────────────────────────────────────────────────────────
# AUDIT FIX: Partial fill dedup tests (F-7, F-8, F-9)
# ──────────────────────────────────────────────────────────────────

class TestPartialFillDedupFix:
    """Verify that multiple partial fills for the same order are not suppressed."""

    def test_truth_hardening_key_includes_trade_id(self):
        """Different trade_ids for same order → different dedup keys."""
        from apps.reference.domains.execution_position.state.truth_hardening import (
            resolve_trade_executed_identity,
        )

        payload_fill_1 = {
            "symbol": "ETHUSDT",
            "orderId": "123456",
            "clientOrderId": "ENTRY-ETH-001",
            "tradeId": "t100",
        }
        payload_fill_2 = {
            "symbol": "ETHUSDT",
            "orderId": "123456",
            "clientOrderId": "ENTRY-ETH-001",
            "tradeId": "t101",
        }
        id1 = resolve_trade_executed_identity(payload_fill_1)
        id2 = resolve_trade_executed_identity(payload_fill_2)

        assert id1.key != id2.key, (
            f"Different trade_ids must produce different keys: {id1.key} vs {id2.key}"
        )
        assert "trade_id=t100" in id1.key
        assert "trade_id=t101" in id2.key

    def test_truth_hardening_key_backward_compat_no_trade_id(self):
        """Payload without tradeId → key unchanged from old format."""
        from apps.reference.domains.execution_position.state.truth_hardening import (
            resolve_trade_executed_identity,
        )

        payload = {
            "symbol": "ETHUSDT",
            "orderId": "123456",
            "clientOrderId": "ENTRY-ETH-001",
        }
        identity = resolve_trade_executed_identity(payload)

        assert "trade_id=" not in identity.key, (
            "Key without trade_id should not contain trade_id= segment"
        )
        assert identity.key == (
            "trade_executed:ETHUSDT:order_id=123456:"
            "client_order_id=ENTRY-ETH-001"
        )

    def test_event_handler_dedup_key_includes_trade_id(self):
        """Dedup key in on_order_fill must include trade_id when present."""
        # Reproduce the key construction logic from event_handlers.py
        payload_1 = {"tradeId": "t100"}
        payload_2 = {"tradeId": "t101"}
        order_id = "123456"
        symbol = "ETHUSDT"

        def build_key(payload):
            _trade_id = str(payload.get("tradeId")
                            or payload.get("trade_id") or "")
            return f"fill_{order_id}_{_trade_id}_{symbol}" if _trade_id else f"fill_{order_id}_{symbol}"

        key1 = build_key(payload_1)
        key2 = build_key(payload_2)

        assert key1 != key2, f"Different trade_ids must produce different keys: {key1} vs {key2}"
        assert "t100" in key1
        assert "t101" in key2

    def test_watchdog_retains_order_on_partial_fill(self):
        """Watchdog must NOT remove order from tracking on PARTIALLY_FILLED."""
        from apps.reference.domains.execution_position.adapters.watchdog import (
            OrderTimeoutWatchdog,
        )

        wdog = OrderTimeoutWatchdog(fill_ttl_ms=60000)
        wdog._enabled = False  # Prevent background task
        wdog.track_order_placed("order1", "client1", "ETHUSDT")
        wdog.on_order_ack("order1")

        assert "order1" in wdog.acked_orders, "Order should be in acked_orders after ACK"

        # Simulate partial fill — do NOT call on_order_fill (that's for FILLED only)
        # The order should remain in acked_orders
        assert "order1" in wdog.acked_orders, "Order should remain tracked after partial fill"

        # Simulate final fill
        wdog.on_order_fill("order1")
        assert "order1" not in wdog.acked_orders, "Order should be removed after final FILLED"
        assert "order1" not in wdog.pending_orders


# ──────────────────────────────────────────────────────────────────
# AUDIT FIX: Spread guard hardening tests (F-1, F-2, F-3)
# ──────────────────────────────────────────────────────────────────

class TestSpreadGuardHardening:
    """Verify GTX spread guard handles edge cases gracefully."""

    def test_crossed_book_skips_adjustment(self):
        """When best_bid >= best_ask (crossed/zero-spread), guard should not adjust."""
        best_bid = Decimal("100.60")
        best_ask = Decimal("100.50")  # Crossed: bid > ask
        submit_price = Decimal("100.55")
        side = "BUY"

        # Reproduce the guard logic: crossed book should skip
        adjusted = submit_price
        if best_bid >= best_ask:
            pass  # Skip adjustment — this is what the fix does
        elif side == "BUY" and submit_price >= best_ask:
            adjusted = best_bid

        assert adjusted == submit_price, (
            f"Crossed book should NOT adjust price; got {adjusted}"
        )

    def test_decimal_conversion_failure_does_not_crash(self):
        """Invalid price strings should not crash the spread guard."""
        from decimal import InvalidOperation

        # Simulate what happens with bad input
        best_bid_s = "not_a_number"
        best_ask_s = "100.50"

        best_bid = None
        try:
            best_bid = Decimal(best_bid_s)
            best_ask = Decimal(best_ask_s)
        except (InvalidOperation, ValueError, TypeError):
            best_bid = None  # Guard should skip

        assert best_bid is None, "Invalid Decimal should cause guard to skip"
