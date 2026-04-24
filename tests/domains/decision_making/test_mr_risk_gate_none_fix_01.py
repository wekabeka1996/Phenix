import logging
import time
from types import SimpleNamespace

import pytest
from vfoundation.core.protocol import Message


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


def _mk_dm(*, max_risk_score=0.96, aurora_override=None):
    from apps.reference.domains.decision_making.core.facade import DecisionMaking
    from apps.reference.core.time.clock import LiveClock

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.fsm = _DummyFsm()
    dm._clock = LiveClock()
    dm.logger = logging.getLogger("tests.mr_risk_gate_none_fix")
    dm.symbol_states = {}
    dm.features_ttl_sec = 60

    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            risk_management=SimpleNamespace(
                trading_allowed_thresholds=SimpleNamespace(max_risk_score=max_risk_score)
            ),
            decision_making=SimpleNamespace(
                directional_sanity=SimpleNamespace(
                    enabled=False,
                    min_abs_delta_price=0.0,
                    min_confidence=0.0,
                    consecutive_bars=2,
                ),
                price_motion_sanity=SimpleNamespace(
                    enabled=False,
                    k_vol=2.0,
                    flash_window_sec=10,
                    bleed_window_sec=300,
                    flash_threshold_norm=1.0,
                    bleed_threshold_norm=0.7,
                    require_bleed_ready=True,
                ),
            ),
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(decision=SimpleNamespace(retry_ttl_ms=10_000)),
        ),
    )

    dm._check_strategy_arbitration = lambda *_a, **_k: {"allowed": True, "reason": None}
    dm._get_risk_skew_config = lambda *_a, **_k: 9999
    dm._stable_retry_key = lambda **_k: "retry"
    dm._record_blocked_intent = lambda *_a, **_k: None
    dm._record_accepted_intent = lambda *_a, **_k: None
    dm._qos_allow = lambda *_a, **_k: (True, None)
    dm._handle_flip_orchestration = lambda *_a, **_k: None
    dm._warmup_gate_before_trade_intent = lambda **_k: False
    dm._precheck_exposure_cache = lambda *_a, **_k: True
    dm._emit_trade_intent_rejected = lambda **_k: None
    dm._emit_intent_deferred_v1 = lambda **kw: dm.fsm.emit("EVT:INTENT_DEFERRED", kw)

    if aurora_override is None:
        dm._get_aurora_instrument_cfg = lambda _symbol: None
    else:
        dm._get_aurora_instrument_cfg = lambda _symbol: SimpleNamespace(max_risk_score=aurora_override)

    from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
    dm._gateway = StrategyGateway(dm)

    return dm


def test_gateway_does_not_crash_on_missing_risk_score_emits_deferred(caplog):
    dm = _mk_dm()
    now_ms = int(time.time() * 1000)
    dm.symbol_states["DOGEUSDT"] = {
        "features": {"ts": now_ms},
        "risk": {"ts": now_ms, "risk_parameters": {"is_trading_allowed": True, "risk_score": None}},
        "risk_skew_guard": {},
    }

    evt = Message(
        op="EVT",
        verb="STRATEGY_SIGNAL_PRODUCED",
        src="strategy",
        dst="decision_making",
        rid="rid-1",
        pld={
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "rid": "sig-1",
            "why_chain": [],
            "ts_ms": now_ms,
            "price_ctx": {"entry_price": "0.13"},
            "readiness": {"warmup_ok": True},
        },
        why="test",
    )

    with caplog.at_level(logging.WARNING):
        dm._on_strategy_signal_gateway(evt)

    assert any("RISK_SCORE_MISSING" in rec.message for rec in caplog.records)
    assert any(name == "EVT:INTENT_DEFERRED" for name, _ in dm.fsm.emitted)
    assert not any(name == "EVT:TRADE_INTENT_PROPOSED" for name, _ in dm.fsm.emitted)


def test_gateway_uses_override_threshold_when_present(caplog):
    from apps.reference.config_models import MaxRiskScoreConfig

    dm = _mk_dm(aurora_override=MaxRiskScoreConfig(enabled=True, value=0.10))
    now_ms = int(time.time() * 1000)
    dm.symbol_states["DOGEUSDT"] = {
        "features": {"ts": now_ms},
        "risk": {"ts": now_ms, "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.20}},
        "risk_skew_guard": {},
    }

    evt = Message(
        op="EVT",
        verb="STRATEGY_SIGNAL_PRODUCED",
        src="strategy",
        dst="decision_making",
        rid="rid-1",
        pld={
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "rid": "sig-1",
            "why_chain": [],
            "ts_ms": now_ms,
            "price_ctx": {"entry_price": "0.13"},
            "readiness": {"warmup_ok": True},
        },
        why="test",
    )

    with caplog.at_level(logging.WARNING):
        dm._on_strategy_signal_gateway(evt)

    assert any("used_override=True" in rec.message for rec in caplog.records)
    assert not any(name == "EVT:TRADE_INTENT_PROPOSED" for name, _ in dm.fsm.emitted)


def test_gateway_uses_global_threshold_when_override_missing(caplog):
    dm = _mk_dm(max_risk_score=0.96, aurora_override=None)
    now_ms = int(time.time() * 1000)
    dm.symbol_states["DOGEUSDT"] = {
        "features": {"ts": now_ms},
        "risk": {"ts": now_ms, "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.97}},
        "risk_skew_guard": {},
    }

    evt = Message(
        op="EVT",
        verb="STRATEGY_SIGNAL_PRODUCED",
        src="strategy",
        dst="decision_making",
        rid="rid-1",
        pld={
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "rid": "sig-1",
            "why_chain": [],
            "ts_ms": now_ms,
            "price_ctx": {"entry_price": "0.13"},
            "readiness": {"warmup_ok": True},
        },
        why="test",
    )

    with caplog.at_level(logging.WARNING):
        dm._on_strategy_signal_gateway(evt)

    assert any("used_override=False" in rec.message for rec in caplog.records)
    assert not any(name == "EVT:TRADE_INTENT_PROPOSED" for name, _ in dm.fsm.emitted)
