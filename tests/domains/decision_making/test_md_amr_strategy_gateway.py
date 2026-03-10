import decimal
import logging
from types import SimpleNamespace

from apps.reference.domains.decision_making.strategy_gateway import StrategyGateway


class _StubEvent:
    def __init__(self, payload):
        self.pld = payload


class _DMStub:
    def __init__(self) -> None:
        self.logger = logging.getLogger("tests.md_amr.gateway")
        self._clock = SimpleNamespace(now_ms=lambda: 1_700_000_000_000)
        self.config = SimpleNamespace(
            domains=SimpleNamespace(
                decision_making=SimpleNamespace(
                    risk_skew=SimpleNamespace(until_refresh_retry_sec=1)
                )
            ),
            strategies=SimpleNamespace(),
        )
        self.symbol_states = {"BTCUSDT": {"risk_skew_guard": {}, "risk": {"risk_parameters": {}}}}
        self.rejections = []
        self.blocked = []
        self.close_calls = []
        self.proposals = []

    def _emit_trade_intent_rejected(self, **kwargs):
        self.rejections.append(kwargs)

    def _record_blocked_intent(self, symbol: str):
        self.blocked.append(symbol)

    def _check_strategy_arbitration(self, symbol: str, strategy_id: str, ts_ms=None, commit=True):
        return {"allowed": True, "reason": None}

    def _emit_reduce_only_close(self, **kwargs):
        self.close_calls.append(kwargs)
        return True

    def _get_portfolio_position_qty_signed(self, symbol: str):
        return decimal.Decimal("2.0"), {"symbol": symbol}

    def _propose_trade_intent(self, **kwargs):
        self.proposals.append(kwargs)


def _md_amr_trace() -> dict:
    return {
        "dir_score": 0.25,
        "thr_buy": 0.20,
        "thr_sell": 0.30,
        "w_raw": {"d1": 0.25, "h1": 0.25, "m30": 0.25, "m15": 0.25},
        "w_norm": {"d1": 0.25, "h1": 0.25, "m30": 0.25, "m15": 0.25},
        "qty_base": 2.0,
        "qty_new": 1.0,
        "conf_ratio": 0.8,
    }


def test_md_amr_full_close_routes_to_reduce_only_close() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)

    event = _StubEvent(
        {
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "intent_kind": "FULL_CLOSE",
            "readiness": {"warmup_ok": True},
            "trace": _md_amr_trace(),
            "exit_reason_code": "EDGE_GONE_KILLSWITCH",
            "why_chain": ["EDGE_GONE_KILLSWITCH"],
            "ts_ms": 1_700_000_000_000,
            "rid": "md-full-close-1",
        }
    )

    gateway.process_signal(event)

    assert not dm.rejections
    assert len(dm.close_calls) == 1
    close_call = dm.close_calls[0]
    assert close_call["symbol"] == "BTCUSDT"
    assert close_call["reason"] == "EDGE_GONE_KILLSWITCH"
    assert close_call["strategy_id"] == "md_amr"
    assert close_call["strategy_trace"]["md_amr"]["conf_ratio"] == 0.8


def test_md_amr_partial_close_proposes_reduce_only_intent() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)

    event = _StubEvent(
        {
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "intent_kind": "PARTIAL_CLOSE",
            "scaleout_fraction": 0.25,
            "readiness": {"warmup_ok": True},
            "trace": _md_amr_trace(),
            "exit_reason_code": "FEE_AWARE_SCALEOUT",
            "why_chain": ["FEE_AWARE_SCALEOUT"],
            "ts_ms": 1_700_000_000_000,
            "rid": "md-partial-close-1",
        }
    )

    gateway.process_signal(event)

    assert not dm.rejections
    assert len(dm.proposals) == 1
    proposal = dm.proposals[0]
    assert proposal["symbol"] == "BTCUSDT"
    assert proposal["side"] == "SELL"
    assert proposal["qty"] == decimal.Decimal("0.50")
    assert proposal["reduce_only"] is True
    assert proposal["strategy_id"] == "md_amr"
    assert proposal["strategy_trace"]["md_amr"]["qty_base"] == 2.0
    assert proposal["why_chain"][-1] == "md_amr_partial_close"
