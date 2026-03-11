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


def _objective_trace() -> dict:
    return {
        "trace_id": "obj-md-1",
        "multiplier": 0.85,
        "objective_score": 0.42,
        "components": {"cost": -0.1, "edge": 0.2},
        "raw_metrics": {"spread_bps": 1.2},
    }


def test_md_amr_full_close_routes_to_reduce_only_close() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)
    trace = _md_amr_trace()
    trace["objective"] = _objective_trace()

    event = _StubEvent(
        {
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "intent_kind": "FULL_CLOSE",
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": False,
                "mode": "PROTECT_ONLY",
            },
            "trace": trace,
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
    assert close_call["strategy_trace"]["objective"]["trace_id"] == "obj-md-1"


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
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": False,
                "mode": "PROTECT_ONLY",
            },
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


def test_reduce_path_allows_manage_existing_risk_when_warmup_not_ok() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)

    event = _StubEvent(
        {
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "intent_kind": "FULL_CLOSE",
            "readiness": {"warmup_ok": False},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": False,
                "mode": "PROTECT_ONLY",
            },
            "trace": _md_amr_trace(),
            "exit_reason_code": "EDGE_GONE_KILLSWITCH",
            "why_chain": ["analytics_restore_partial"],
            "ts_ms": 1_700_000_000_000,
            "rid": "md-full-close-cold-restart",
        }
    )

    gateway.process_signal(event)

    assert not dm.rejections
    assert len(dm.close_calls) == 1
    assert dm.close_calls[0]["reason"] == "EDGE_GONE_KILLSWITCH"


def test_md_amr_entry_invalid_objective_trace_fails_closed() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)
    trace = _md_amr_trace()
    trace["objective"] = {
        "trace_id": "",
        "multiplier": 0.9,
        "objective_score": 0.3,
        "components": {"edge": 0.1},
        "raw_metrics": {"spread_bps": 1.0},
    }

    event = _StubEvent(
        {
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "intent_kind": "ENTRY",
            "readiness": {"warmup_ok": True},
            "trace": trace,
            "ts_ms": 1_700_000_000_000,
            "rid": "md-entry-1",
            "why_chain": [],
        }
    )

    gateway.process_signal(event)

    assert len(dm.rejections) == 1
    assert dm.rejections[0]["reason_code"] == "WAL_TRACE_INVALID"


def test_entry_rejects_when_runtime_permissions_deny_open_new_risk() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)

    event = _StubEvent(
        {
            "strategy_id": "md_amr",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "intent_kind": "ENTRY",
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": False,
                "mode": "PROTECT_ONLY",
            },
            "trace": _md_amr_trace(),
            "ts_ms": 1_700_000_000_000,
            "rid": "md-entry-protect-only",
            "why_chain": [],
        }
    )

    gateway.process_signal(event)

    assert len(dm.rejections) == 1
    assert dm.rejections[0]["reason_code"] == "READINESS_OPEN_NEW_RISK_NOT_ALLOWED"
