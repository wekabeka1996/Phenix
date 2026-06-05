import json

import pytest

from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from apps.reference.domains.execution_position.state.order_index import OrderIndex
from apps.reference.domains.execution_position.state.truth_hardening import ExecutionTruthHardening


class _DummyFSMCore:
    def __init__(self, order_index=None, order_guardian=None, hardening=None):
        self.order_index = order_index
        self.order_guardian = order_guardian
        self._execution_truth_hardening = hardening
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, rid: str) -> None:
        hardening = getattr(self, "_execution_truth_hardening", None)
        if hardening is not None and event_name == "EVT:TRADE_EXECUTED":
            decision = hardening.evaluate_trade_executed(
                payload,
                order_index=self.order_index,
            )
            if decision.suppress:
                return
        self.emitted.append((event_name, payload, rid))


@pytest.mark.integration
class TestBinanceWSOrderIndexCorrelation:
    def test_ws_update_without_order_index_skips_emit(self) -> None:
        fsm_core = _DummyFSMCore(order_index=None)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 123,
            "o": {
                "c": "cid1",
                "i": "ex1",
                "X": "FILLED",
                "s": "BTCUSDT",
                "z": "0.01",
                "S": "BUY",
                "o": "MARKET",
            },
        }

        client._handle_ws_message(msg)
        assert fsm_core.emitted == []

    def test_ws_update_with_order_index_emits_and_marks_terminal(self) -> None:
        idx = OrderIndex(ttl_sec=600)
        ref = idx.upsert_from_open(
            rid="r1",
            idempotent_key="idem1",
            clientOrderId="cid1",
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
        )
        idx.attach_exchange_id(clientOrderId="cid1", exchangeOrderId="ex1")

        fsm_core = _DummyFSMCore(order_index=idx)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 123,
            "o": {
                "c": "cid1",
                "i": "ex1",
                "X": "FILLED",
                "s": "BTCUSDT",
                "z": "0.01",
                "S": "BUY",
                "o": "MARKET",
                "q": "0.01",
                "p": "100.0",
            },
        }

        client._handle_ws_message(msg)

        assert len(fsm_core.emitted) == 1
        event_name, payload, rid = fsm_core.emitted[0]
        assert event_name == "EVT:TRADE_EXECUTED"
        assert rid == "WS_ORDER_UPDATE_FILLED"

        assert payload["rid"] == "r1"
        assert payload["idempotent_key"] == "idem1"
        assert payload["clientOrderId"] == "cid1"
        assert payload["exchangeOrderId"] == "ex1"
        assert payload["symbol"] == "BTCUSDT"
        assert payload["status"] == "FILLED"
        assert payload["side"] == "buy"
        assert payload["order_type"] == "market"

        assert ref.terminal is True

    @pytest.mark.parametrize(
        ("kind", "client_order_id", "tracked_order_id",
         "incoming_order_id", "order_type"),
        [
            ("SL", "SJGknqkssjcrviz2pCUMMi",
             "1000000041481020", "8631145709", "STOP_MARKET"),
            ("TP", "QqUbuNUcHmIDLOvoqP1taG", "1000000041481025",
             "8631145710", "TAKE_PROFIT_MARKET"),
        ],
    )
    def test_ws_terminal_bracket_update_correlates_via_orderindex_canonical(
        self,
        tmp_path,
        monkeypatch,
        kind: str,
        client_order_id: str,
        tracked_order_id: str,
        incoming_order_id: str,
        order_type: str,
    ) -> None:
        """Bracket child terminal updates correlate through OrderIndex canonical registration."""
        monkeypatch.chdir(tmp_path)

        idx = OrderIndex(ttl_sec=600)
        idx.register_bracket_child(
            rid="aurora_ETHUSDT_1775247901546",
            idempotent_key="idem-1",
            clientOrderId=client_order_id,
            exchangeOrderId=incoming_order_id,
            symbol="ETHUSDT",
            side="SELL",
            order_type=order_type,
            order_kind=kind,
        )

        fsm_core = _DummyFSMCore(order_index=idx)
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
                "c": client_order_id,
                "i": incoming_order_id,
                "X": "FILLED",
                "s": "ETHUSDT",
                "z": "0.10",
                "l": "0.10",
                "S": "SELL",
                "o": order_type,
                "q": "0.10",
                "ap": "1990.0",
                "p": "1990.0",
            },
        }

        client._handle_ws_message(msg)

        assert len(fsm_core.emitted) == 1
        event_name, payload, rid = fsm_core.emitted[0]
        assert event_name == "EVT:TRADE_EXECUTED"
        assert rid == "WS_ORDER_UPDATE_FILLED"
        assert payload["rid"] == f"aurora_ETHUSDT_1775247901546:{kind}"
        assert payload["clientOrderId"] == client_order_id
        assert payload["orderId"] == incoming_order_id
        assert payload["bracket_role"] == kind
        assert payload["terminal_correlation_source"] == "order_index_canonical"

    def test_ws_unknown_terminal_bracket_update_remains_fail_closed(self, tmp_path, monkeypatch) -> None:
        """Unknown close-bearing terminal update with no OrderIndex record is dropped fail-closed."""
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
                "c": "unknown-algo-id",
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

        assert fsm_core.emitted == []
        rows = [
            json.loads(line)
            for line in (tmp_path / "logs" / "trade_lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert rows[-1]["record_kind"] == "execution_ws_terminal"
        assert rows[-1]["event_type"] == "EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS"
        assert rows[-1]["client_order_id"] == "unknown-algo-id"

    def test_ws_duplicate_close_terminal_after_cleanup_uses_identity_cache_bridge(self, tmp_path, monkeypatch) -> None:
        """Late duplicate CLOSE terminal updates bridge via exact fill identity after OrderIndex cleanup."""
        monkeypatch.chdir(tmp_path)

        idx = OrderIndex(ttl_sec=600)
        idx.upsert_from_open(
            rid="close-rid-1",
            idempotent_key="close-idem-1",
            clientOrderId="CLOSE-btc-1",
            symbol="BTCUSDT",
            side="SELL",
            order_type="MARKET",
            order_kind="CLOSE",
        )
        idx.attach_exchange_id(
            clientOrderId="CLOSE-btc-1",
            exchangeOrderId="9997771",
        )
        hardening = ExecutionTruthHardening(
            fill_dedup_max_size=32,
            fill_dedup_ttl_ms=60_000,
            close_guard_ttl_ms=60_000,
            warm_state_enabled=False,
            warm_state_storage_path=None,
            warm_state_max_entries=32,
        )

        fsm_core = _DummyFSMCore(order_index=idx, hardening=hardening)
        client = BinanceWebSocketClient(
            api_key="k",
            base_url="http://example.invalid",
            use_testnet=True,
            fsm_core=fsm_core,
        )

        msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1710000124567,
            "o": {
                "c": "CLOSE-btc-1",
                "i": "9997771",
                "X": "FILLED",
                "s": "BTCUSDT",
                "z": "0.095",
                "l": "0.095",
                "S": "SELL",
                "o": "MARKET",
                "q": "0.095",
                "ap": "79705.2",
                "p": "0.0",
                "n": "1.23",
                "N": "USDT",
                "rp": "-21.39",
                "t": "trade-close-1",
                "R": True,
            },
        }

        client._handle_ws_message(msg)
        assert len(fsm_core.emitted) == 1

        removed = idx.expire()
        assert removed == 1
        assert idx.get(clientOrderId="CLOSE-btc-1") is None

        client._handle_ws_message(msg)

        assert len(fsm_core.emitted) == 1
        rows = [
            json.loads(line)
            for line in (tmp_path / "logs" / "trade_lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert rows[-1]["record_kind"] == "execution_ws_terminal"
        assert rows[-1]["event_type"] == "EXECUTION_WS_TERMINAL_DUPLICATE_IDENTITY_CACHE_HIT"
        assert rows[-1]["client_order_id"] == "CLOSE-btc-1"
        assert rows[-1]["exchange_order_id"] == "9997771"
        assert rows[-1]["terminal_correlation_source"] == "execution_truth_hardening_exact_identity"
        assert not any(
            row.get("event_type") == "EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS"
            for row in rows
        )
