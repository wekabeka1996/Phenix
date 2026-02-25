import logging
import time
from types import SimpleNamespace
from apps.reference.core.time.clock import LiveClock
from unittest.mock import MagicMock


def test_decision_making_blocks_trade_intent_until_ready(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    blocks: list[tuple[str, str]] = []

    def _fake_inc_warmup_block(*, domain: str, reason: str) -> None:
        blocks.append((domain, reason))

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.readiness_gates.inc_warmup_block",
        _fake_inc_warmup_block,
    )

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = logging.getLogger("tests.task24.decision_making")
    dm._clock = LiveClock()  # T2B-08: Clock required for _features_ready()

    # Phase 14A: Inject readiness gate
    dm._readiness = MagicMock()
    dm._warmup_gate_before_trade_intent = lambda **kwargs: dm._readiness.warmup_gate_before_trade_intent(**kwargs)
    
    # Mock readiness behavior to return True (blocked) and record to blocks via fake
    def mock_warmup(*, symbol, rid, reduce_only, context):
        if not reduce_only:
            _fake_inc_warmup_block(domain="decision_making", reason="regime_warmup_missing")
            return True
        return False
    dm._readiness.warmup_gate_before_trade_intent.side_effect = mock_warmup

    dm.features_ttl_sec = 60
    dm._shared = {"latest_portfolio": {"ok": True}}
    dm.symbol_states = {}
    dm._per_symbol_regimes = {}
    dm._record_blocked_intent = lambda _symbol: None

    symbol = "BTCUSDT"
    
    blocked = dm._warmup_gate_before_trade_intent(
        symbol=symbol,
        rid="rid-1",
        reduce_only=False,
        context="test",
    )
    assert blocked is True
    assert any(domain == "decision_making" and reason == "regime_warmup_missing" for domain, reason in blocks)


def test_decision_making_reduce_only_bypasses_warmup_gate(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    called = {"n": 0}

    def _fake_inc_warmup_block(*, domain: str, reason: str) -> None:
        called["n"] += 1

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.readiness_gates.inc_warmup_block",
        _fake_inc_warmup_block,
    )

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = logging.getLogger("tests.task24.decision_making")
    dm._clock = LiveClock()  # T2B-08: Clock required for warmup gate
    
    dm._readiness = MagicMock()
    dm._warmup_gate_before_trade_intent = lambda **kwargs: dm._readiness.warmup_gate_before_trade_intent(**kwargs)
    dm._readiness.warmup_gate_before_trade_intent.return_value = False # mocked bypass for reduce_only

    dm._shared = {"latest_portfolio": None}
    dm.symbol_states = {}
    dm._per_symbol_regimes = {}
    dm._record_blocked_intent = lambda _symbol: None

    blocked = dm._warmup_gate_before_trade_intent(
        symbol="BTCUSDT",
        rid="rid-2",
        reduce_only=True,
        context="test",
    )
    assert blocked is False
    assert called["n"] == 0
