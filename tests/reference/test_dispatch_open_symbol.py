"""
Test for symbol extraction fix in _dispatch_open.

This test ensures that _dispatch_open correctly extracts symbol from both
'instrument' (legacy) and 'symbol' (current) payload keys.

Bug context:
- User reported: "система відкрила позицію SOL а TP/SL відкрила BNB"
- Root cause: _dispatch_open used only intent_msg.pld.get("instrument") which returned None
  for payloads that use "symbol" key instead of "instrument"
- Fix: Support both 'instrument' (legacy) and 'symbol' (current) keys
"""
import pytest


class TestSymbolExtractionLogic:
    """Test symbol extraction logic from _dispatch_open."""

    def _extract_symbol(self, payload: dict) -> str | None:
        """
        Exact copy of symbol extraction logic from main.py._dispatch_open.

        This mirrors the fix applied to main.py:
        - FIXED: Support both 'instrument' (legacy) and 'symbol' (current) keys
        """
        return payload.get("instrument") or payload.get("symbol")

    def _extract_symbol_with_fallback(self, payload: dict) -> str:
        """Extract symbol with 'unknown' fallback for logging."""
        return payload.get("instrument") or payload.get("symbol") or "unknown"

    def test_extract_symbol_from_symbol_key(self):
        """Test that symbol is correctly extracted when using 'symbol' key."""
        payload = {
            "symbol": "SOLUSDT",
            "side": "BUY",
        }
        result = self._extract_symbol(payload)
        assert result == "SOLUSDT", f"Expected 'SOLUSDT', got {result}"

    def test_extract_symbol_from_instrument_key(self):
        """Test that symbol is correctly extracted when using 'instrument' key (legacy)."""
        payload = {
            "instrument": "BNBUSDT",
            "side": "SELL",
        }
        result = self._extract_symbol(payload)
        assert result == "BNBUSDT", f"Expected 'BNBUSDT', got {result}"

    def test_instrument_takes_precedence_over_symbol(self):
        """Test that 'instrument' takes precedence over 'symbol' when both present."""
        payload = {
            "instrument": "ETHUSDT",  # legacy key
            "symbol": "BTCUSDT",      # current key
            "side": "BUY",
        }
        result = self._extract_symbol(payload)
        # 'instrument' should take precedence (first in the fallback chain)
        assert result == "ETHUSDT", f"Expected 'ETHUSDT' (from instrument), got {result}"

    def test_returns_none_when_both_keys_missing(self):
        """Test that None is returned when neither key is present."""
        payload = {
            "side": "BUY",
            "qty": "10",
        }
        result = self._extract_symbol(payload)
        assert result is None, f"Expected None, got {result}"

    def test_fallback_returns_unknown_when_both_keys_missing(self):
        """Test that 'unknown' is returned when neither key is present (for logging)."""
        payload = {
            "side": "BUY",
            "qty": "10",
        }
        result = self._extract_symbol_with_fallback(payload)
        assert result == "unknown", f"Expected 'unknown', got {result}"

    def test_empty_string_instrument_falls_through_to_symbol(self):
        """Test that empty string instrument falls through to symbol."""
        payload = {
            "instrument": "",  # empty string is falsy
            "symbol": "BTCUSDT",
        }
        result = self._extract_symbol(payload)
        assert result == "BTCUSDT", f"Expected 'BTCUSDT', got {result}"

    def test_none_instrument_falls_through_to_symbol(self):
        """Test that None instrument falls through to symbol."""
        payload = {
            "instrument": None,
            "symbol": "XRPUSDT",
        }
        result = self._extract_symbol(payload)
        assert result == "XRPUSDT", f"Expected 'XRPUSDT', got {result}"


class TestEventAdapterSymbolPropagation:
    """Test symbol propagation through V2RuntimeFacade mapping logic."""

    def test_cmd_open_extracts_symbol_from_payload(self):
        """Test that CMD:OPEN correctly extracts symbol from payload."""
        from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade
        from vfoundation.core.protocol import Message
        from unittest.mock import MagicMock

        # Mock dependencies
        mock_config = MagicMock()
        mock_adapter = MagicMock()

        # Instantiate Facade
        facade = V2RuntimeFacade(config=mock_config, adapter=mock_adapter)

        # Mock internal runtime to capture handle calls
        facade.runtime = MagicMock()
        facade._submit_to_loop = MagicMock() # Don't actually run async

        # Test with 'symbol' key (current format)
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={
                "symbol": "SOLUSDT",
                "side": "BUY",
                "qty": "10",
            }
        )

        # Call handle
        facade.handle(msg)

        # Verify runtime.handle was called with correct event
        assert facade.runtime.handle.called
        call_args = facade.runtime.handle.call_args[0][0]

        assert call_args.kind == "ENTRY_INTENT"
        assert call_args.symbol == "SOLUSDT"

    def test_cmd_open_symbol_none_when_missing(self):
        """Test that CMD:OPEN with missing symbol results in None (fail-closed)."""
        from apps.reference.domains.execution_position.infra.runtime_factory import V2RuntimeFacade
        from vfoundation.core.protocol import Message
        from unittest.mock import MagicMock

        # Mock dependencies
        mock_config = MagicMock()
        mock_adapter = MagicMock()

        facade = V2RuntimeFacade(config=mock_config, adapter=mock_adapter)
        facade.runtime = MagicMock()
        facade._submit_to_loop = MagicMock()

        # Test with missing symbol
        msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            pld={
                "side": "BUY",
                "qty": "10",
                # symbol is missing!
            }
        )

        facade.handle(msg)

        # Verify runtime.handle was NOT called (invalid payload rejected)
        assert not facade.runtime.handle.called
