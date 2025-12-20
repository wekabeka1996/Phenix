import pytest

from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from apps.reference.domains.execution_position.order_index import OrderIndex


class _DummyFSMCore:
    def __init__(self, order_index=None):
        self.order_index = order_index
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, rid: str) -> None:
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
