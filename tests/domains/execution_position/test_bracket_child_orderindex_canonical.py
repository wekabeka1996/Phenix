"""
Tests for canonical bracket child order registration in OrderIndex.

Package: BRACKET_CHILD_ORDERINDEX_CANONICAL_REGISTRATION_AND_FAIL_CLOSED_CORRELATION

Proves:
1. Bracket child orders (SL/TP) are registered in OrderIndex at placement time
2. Terminal WS correlation for bracket children works through OrderIndex (no fallback)
3. OrderIndex miss on close-bearing terminal event -> fail-closed (contract breach)
4. Entry/close order registration is not broken (no regression)
5. register_bracket_child contract enforces required fields
"""

from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
import json
import pytest

from apps.reference.domains.execution_position.order_index import (
    OrderIndex,
    OrderRef,
)


# ---------------------------------------------------------------------------
# 1. register_bracket_child – unit tests
# ---------------------------------------------------------------------------

class TestRegisterBracketChild:
    """Canonical bracket child registration into OrderIndex."""

    @pytest.fixture
    def idx(self):
        return OrderIndex(ttl_sec=600)

    def test_sl_child_present_in_all_three_indexes(self, idx):
        """After registration, SL child is findable by rid, clientOrderId, exchangeOrderId."""
        ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        assert ref.order_kind == "SL"
        assert ref.clientOrderId == "SL-abc123"
        assert ref.exchangeOrderId == "9990001"
        assert ref.symbol == "ETHUSDT"
        assert ref.side == "SELL"
        assert ref.order_type == "STOP_MARKET"
        assert ref.terminal is False

        # Lookup by clientOrderId
        assert idx.get(clientOrderId="SL-abc123") is ref
        # Lookup by exchangeOrderId
        assert idx.get(exchangeOrderId="9990001") is ref
        # Lookup by synthetic rid
        assert idx.get(rid="parent-rid-1:SL") is ref

    def test_tp_child_present_in_all_three_indexes(self, idx):
        """After registration, TP child is findable by rid, clientOrderId, exchangeOrderId."""
        ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="TP-def456",
            exchangeOrderId="9990002",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            order_kind="TP",
        )
        assert ref.order_kind == "TP"
        assert idx.get(clientOrderId="TP-def456") is ref
        assert idx.get(exchangeOrderId="9990002") is ref
        assert idx.get(rid="parent-rid-1:TP") is ref

    def test_sl_and_tp_from_same_parent_coexist(self, idx):
        """Both SL and TP children sharing the same parent rid coexist without collision."""
        sl_ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        tp_ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="TP-def456",
            exchangeOrderId="9990002",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            order_kind="TP",
        )
        assert sl_ref is not tp_ref
        assert idx.get(clientOrderId="SL-abc123") is sl_ref
        assert idx.get(clientOrderId="TP-def456") is tp_ref
        assert idx.get(exchangeOrderId="9990001") is sl_ref
        assert idx.get(exchangeOrderId="9990002") is tp_ref

    def test_mark_terminal_works_for_bracket_child(self, idx):
        """Bracket child can be marked terminal just like entry orders."""
        ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        assert ref.terminal is False
        idx.mark_terminal(ref)
        assert ref.terminal is True

    def test_expire_removes_terminal_bracket_child(self, idx):
        """Terminal bracket children are cleaned up by expire()."""
        ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        idx.mark_terminal(ref)
        removed = idx.expire()
        assert removed >= 1
        assert idx.get(clientOrderId="SL-abc123") is None
        assert idx.get(exchangeOrderId="9990001") is None

    def test_requires_client_order_id(self, idx):
        """Missing clientOrderId raises ValueError."""
        with pytest.raises(ValueError, match="clientOrderId"):
            idx.register_bracket_child(
                rid="parent-rid-1",
                idempotent_key="idem-1",
                clientOrderId="",
                exchangeOrderId="9990001",
                symbol="ETHUSDT",
                side="SELL",
                order_type="STOP_MARKET",
                order_kind="SL",
            )

    def test_requires_exchange_order_id(self, idx):
        """Missing exchangeOrderId raises ValueError."""
        with pytest.raises(ValueError, match="exchangeOrderId"):
            idx.register_bracket_child(
                rid="parent-rid-1",
                idempotent_key="idem-1",
                clientOrderId="SL-abc123",
                exchangeOrderId="",
                symbol="ETHUSDT",
                side="SELL",
                order_type="STOP_MARKET",
                order_kind="SL",
            )

    def test_rejects_invalid_order_kind(self, idx):
        """order_kind must be 'SL' or 'TP'."""
        with pytest.raises(ValueError, match="order_kind"):
            idx.register_bracket_child(
                rid="parent-rid-1",
                idempotent_key="idem-1",
                clientOrderId="CLOSE-abc123",
                exchangeOrderId="9990001",
                symbol="ETHUSDT",
                side="SELL",
                order_type="MARKET",
                order_kind="CLOSE",
            )

    def test_bracket_child_not_detected_as_entry(self, idx):
        """Bracket children must NOT be confused with entry orders."""
        ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        assert OrderIndex._is_entry_ref(ref) is False

    def test_entry_and_bracket_children_coexist(self, idx):
        """Entry order + SL + TP all coexist in the same index without collision."""
        entry_ref = idx.upsert_from_open(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="ENTRY-abc123",
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
        )
        idx.attach_exchange_id(
            clientOrderId="ENTRY-abc123", exchangeOrderId="8880001")

        sl_ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        tp_ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="TP-abc123",
            exchangeOrderId="9990002",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            order_kind="TP",
        )

        # All three are distinct and independently accessible
        assert idx.get(clientOrderId="ENTRY-abc123") is entry_ref
        assert idx.get(clientOrderId="SL-abc123") is sl_ref
        assert idx.get(clientOrderId="TP-abc123") is tp_ref
        assert idx.get(exchangeOrderId="8880001") is entry_ref
        assert idx.get(exchangeOrderId="9990001") is sl_ref
        assert idx.get(exchangeOrderId="9990002") is tp_ref

    def test_shadow_journal_receives_bracket_registration(self, idx):
        """Shadow journal is called for bracket child registration."""
        transitions = []

        class FakeJournal:
            def record_transition(self, **kwargs):
                transitions.append(kwargs)

        idx.attach_shadow_journal(FakeJournal())
        idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        assert len(transitions) == 1
        assert transitions[0]["event_name"] == "ORDER_INDEX:REGISTER_BRACKET_CHILD"
        assert transitions[0]["payload"]["order_kind"] == "SL"
        assert transitions[0]["payload"]["parent_rid"] == "parent-rid-1"


# ---------------------------------------------------------------------------
# 2. WS terminal correlation through OrderIndex for bracket children
# ---------------------------------------------------------------------------


class _DummyFSMCore:
    def __init__(self, order_index=None, order_guardian=None):
        self.order_index = order_index
        self.order_guardian = order_guardian
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, rid: str) -> None:
        self.emitted.append((event_name, payload, rid))


class TestWSBracketChildCorrelationCanonical:
    """Terminal WS updates for bracket children correlate via OrderIndex, not fallback."""

    @pytest.fixture
    def idx(self):
        return OrderIndex(ttl_sec=600)

    def _make_client(self, idx):
        fsm_core = _DummyFSMCore(order_index=idx)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )
        return client, fsm_core

    def _make_ws_msg(self, *, client_order_id, exchange_order_id, symbol, order_type, status="FILLED"):
        return {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000123456,
            "o": {
                "c": client_order_id,
                "i": exchange_order_id,
                "X": status,
                "s": symbol,
                "z": "0.10",
                "l": "0.10",
                "S": "SELL",
                "o": order_type,
                "q": "0.10",
                "ap": "1990.0",
                "p": "1990.0",
            },
        }

    def test_sl_terminal_fill_correlates_via_orderindex(self, idx, tmp_path, monkeypatch):
        """SL bracket child FILLED correlates through OrderIndex canonical path."""
        monkeypatch.chdir(tmp_path)
        idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        client, fsm = self._make_client(idx)
        msg = self._make_ws_msg(
            client_order_id="SL-abc123",
            exchange_order_id="9990001",
            symbol="ETHUSDT",
            order_type="STOP_MARKET",
        )
        client._handle_ws_message(msg)

        assert len(fsm.emitted) == 1
        event_name, payload, _ = fsm.emitted[0]
        assert event_name == "EVT:TRADE_EXECUTED"
        assert payload["bracket_role"] == "SL"
        assert payload["close_reason"] == "SL"
        assert payload["terminal_correlation_source"] == "order_index_canonical"
        assert payload["symbol"] == "ETHUSDT"

    def test_tp_terminal_fill_correlates_via_orderindex(self, idx, tmp_path, monkeypatch):
        """TP bracket child FILLED correlates through OrderIndex canonical path."""
        monkeypatch.chdir(tmp_path)
        idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="TP-def456",
            exchangeOrderId="9990002",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            order_kind="TP",
        )
        client, fsm = self._make_client(idx)
        msg = self._make_ws_msg(
            client_order_id="TP-def456",
            exchange_order_id="9990002",
            symbol="ETHUSDT",
            order_type="TAKE_PROFIT_MARKET",
        )
        client._handle_ws_message(msg)

        assert len(fsm.emitted) == 1
        event_name, payload, _ = fsm.emitted[0]
        assert event_name == "EVT:TRADE_EXECUTED"
        assert payload["bracket_role"] == "TP"
        assert payload["terminal_correlation_source"] == "order_index_canonical"

    def test_sl_cancel_correlates_via_orderindex(self, idx, tmp_path, monkeypatch):
        """SL bracket CANCELED correlates and marks terminal."""
        monkeypatch.chdir(tmp_path)
        ref = idx.register_bracket_child(
            rid="parent-rid-1",
            idempotent_key="idem-1",
            clientOrderId="SL-abc123",
            exchangeOrderId="9990001",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            order_kind="SL",
        )
        client, fsm = self._make_client(idx)
        msg = self._make_ws_msg(
            client_order_id="SL-abc123",
            exchange_order_id="9990001",
            symbol="ETHUSDT",
            order_type="STOP_MARKET",
            status="CANCELED",
        )
        client._handle_ws_message(msg)

        assert len(fsm.emitted) == 1
        event_name, payload, _ = fsm.emitted[0]
        assert event_name == "EVT:ORDER_STATE_CHANGED"
        assert ref.terminal is True


# ---------------------------------------------------------------------------
# 3. OrderIndex miss on close-bearing bracket terminal event -> fail-closed
# ---------------------------------------------------------------------------

class TestWSBracketChildOrderIndexMissFailClosed:
    """When a close-bearing terminal event has no OrderIndex record, fail-closed."""

    def test_unregistered_sl_terminal_is_dropped_failclosed(self, tmp_path, monkeypatch):
        """STOP_MARKET FILLED with no OrderIndex record -> contract breach, no emit."""
        monkeypatch.chdir(tmp_path)
        idx = OrderIndex(ttl_sec=600)
        fsm_core = _DummyFSMCore(order_index=idx)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000123999,
            "o": {
                "c": "SL-unknown",
                "i": "8631145799",
                "X": "FILLED",
                "s": "ETHUSDT",
                "z": "0.10",
                "l": "0.10",
                "S": "SELL",
                "o": "STOP_MARKET",
                "q": "0.10",
                "ap": "1990.0",
                "p": "1990.0",
            },
        }

        client._handle_ws_message(msg)

        # No event emitted
        assert fsm_core.emitted == []

        # Lifecycle record written with contract breach event type
        rows = [
            json.loads(line)
            for line in (tmp_path / "logs" / "trade_lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(
            r.get("event_type") == "EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS"
            for r in rows
        )

    def test_unregistered_tp_terminal_is_dropped_failclosed(self, tmp_path, monkeypatch):
        """TAKE_PROFIT_MARKET FILLED with no OrderIndex record -> fail-closed."""
        monkeypatch.chdir(tmp_path)
        idx = OrderIndex(ttl_sec=600)
        fsm_core = _DummyFSMCore(order_index=idx)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000123999,
            "o": {
                "c": "TP-unknown",
                "i": "8631145800",
                "X": "FILLED",
                "s": "BTCUSDT",
                "z": "0.001",
                "l": "0.001",
                "S": "SELL",
                "o": "TAKE_PROFIT_MARKET",
                "q": "0.001",
                "ap": "70000.0",
                "p": "70000.0",
            },
        }

        client._handle_ws_message(msg)
        assert fsm_core.emitted == []

    def test_guardian_fallback_not_used(self, tmp_path, monkeypatch):
        """Even with guardian data, if OrderIndex misses, event is dropped (no fallback)."""
        monkeypatch.chdir(tmp_path)
        from apps.reference.domains.execution_position.order_guardian import (
            InMemoryStore,
            OrderGuardian,
        )

        guardian = OrderGuardian(
            adapter=None, store=InMemoryStore(), bus=None, config=None,
        )
        guardian.register_entry(
            symbol="ETHUSDT", order_id="entry-1",
            client_order_id="ENTRY-1", side="BUY", qty=0.10,
            corr_id="corr-1", rid="rid-1",
        )
        guardian.register_bracket(
            symbol="ETHUSDT", parent_order_id="entry-1",
            order_id="9990001", client_order_id="SL-abc123",
            kind="SL", corr_id="corr-1", rid="rid-1",
        )

        # OrderIndex is empty — bracket child was NOT registered
        idx = OrderIndex(ttl_sec=600)
        fsm_core = _DummyFSMCore(order_index=idx, order_guardian=guardian)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000123456,
            "o": {
                "c": "SL-abc123",
                "i": "9990001",
                "X": "FILLED",
                "s": "ETHUSDT",
                "z": "0.10",
                "l": "0.10",
                "S": "SELL",
                "o": "STOP_MARKET",
                "q": "0.10",
                "ap": "1990.0",
                "p": "1990.0",
            },
        }

        client._handle_ws_message(msg)

        # Guardian has the data but NO emit should happen — fail-closed
        assert fsm_core.emitted == []


# ---------------------------------------------------------------------------
# 4. No regression for entry/close orders
# ---------------------------------------------------------------------------

class TestEntryCloseRegressionGuard:
    """Entry and close order flows remain unbroken."""

    def test_entry_order_still_correlates(self, tmp_path, monkeypatch):
        """Normal entry FILLED still works through OrderIndex as before."""
        monkeypatch.chdir(tmp_path)
        idx = OrderIndex(ttl_sec=600)
        ref = idx.upsert_from_open(
            rid="r1", idempotent_key="idem1",
            clientOrderId="ENTRY-eth1", symbol="ETHUSDT",
            side="BUY", order_type="MARKET",
        )
        idx.attach_exchange_id(clientOrderId="ENTRY-eth1",
                               exchangeOrderId="8880001")

        fsm_core = _DummyFSMCore(order_index=idx)
        client = BinanceWebSocketClient(
            api_key="k", base_url="http://example.invalid",
            use_testnet=True, fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 123,
            "o": {
                "c": "ENTRY-eth1", "i": "8880001",
                "X": "FILLED", "s": "ETHUSDT",
                "z": "0.10", "l": "0.10",
                "S": "BUY", "o": "MARKET",
                "q": "0.10", "ap": "2000.0", "p": "2000.0",
            },
        }

        client._handle_ws_message(msg)
        assert len(fsm_core.emitted) == 1
        event_name, payload, _ = fsm_core.emitted[0]
        assert event_name == "EVT:TRADE_EXECUTED"
        assert payload["rid"] == "r1"
        assert ref.terminal is True

    def test_non_close_bearing_unknown_order_silently_skipped(self, tmp_path, monkeypatch):
        """Non-close-bearing order not in OrderIndex is skipped (not contract breach)."""
        monkeypatch.chdir(tmp_path)
        idx = OrderIndex(ttl_sec=600)
        fsm_core = _DummyFSMCore(order_index=idx)
        client = BinanceWebSocketClient(
            api_key="k", base_url="http://example.invalid",
            use_testnet=True, fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 123,
            "o": {
                "c": "UNKNOWN-123", "i": "7770001",
                "X": "NEW", "s": "BTCUSDT",
                "z": "0", "S": "BUY",
                "o": "LIMIT", "q": "0.01",
                "p": "50000.0",
            },
        }

        client._handle_ws_message(msg)
        assert fsm_core.emitted == []


# ---------------------------------------------------------------------------
# 5. Schema / contract additive compatibility
# ---------------------------------------------------------------------------

class TestOrderRefSchemaCompatibility:
    """OrderRef fields are additive-only — no existing fields broken."""

    def test_order_kind_field_exists(self):
        """OrderRef has order_kind field (pre-existing, EP-01.6)."""
        ref = OrderRef(rid="r1", idempotent_key="ik1")
        assert hasattr(ref, "order_kind")
        assert ref.order_kind is None

    def test_bracket_child_sets_order_kind(self):
        """register_bracket_child sets order_kind to SL/TP."""
        idx = OrderIndex(ttl_sec=600)
        sl_ref = idx.register_bracket_child(
            rid="r1", idempotent_key="ik1",
            clientOrderId="SL-1", exchangeOrderId="e1",
            symbol="ETHUSDT", side="SELL",
            order_type="STOP_MARKET", order_kind="SL",
        )
        assert sl_ref.order_kind == "SL"

        tp_ref = idx.register_bracket_child(
            rid="r1", idempotent_key="ik1",
            clientOrderId="TP-1", exchangeOrderId="e2",
            symbol="ETHUSDT", side="SELL",
            order_type="TAKE_PROFIT_MARKET", order_kind="TP",
        )
        assert tp_ref.order_kind == "TP"

    def test_entry_order_kind_still_unset_by_default(self):
        """upsert_from_open does not set order_kind — backwards compatible."""
        idx = OrderIndex(ttl_sec=600)
        ref = idx.upsert_from_open(
            rid="r1", idempotent_key="ik1",
            clientOrderId="ENTRY-1", symbol="ETHUSDT",
            side="BUY", order_type="MARKET",
        )
        assert ref.order_kind is None
