from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.gateway.protocol import GateOutcome
from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway


def test_unhandled_gate_block_is_persisted_as_terminal_rejection() -> None:
    gateway = StrategyGateway.__new__(StrategyGateway)
    gateway._dm = SimpleNamespace(_record_blocked_intent=MagicMock())
    gateway._reject = MagicMock()
    terminal_result = SimpleNamespace(
        outcome=GateOutcome.BLOCK,
        context_update={},
        why_extra=["risk_skew"],
        reason_code="NRR-RISK-SKEW-UNTIL-REFRESH",
        reason=None,
        context="strategy_signal_gateway:risk_skew",
        details=None,
        gate_name="risk_skew",
    )
    chain_result = SimpleNamespace(terminal_result=terminal_result)
    gate_ctx = SimpleNamespace(
        symbol="BTCUSDT", rid="rid-risk-skew", accumulated={})
    payload = {"symbol": "BTCUSDT", "strategy_id": "aurora", "side": "BUY"}

    gateway._dispatch_gate_result(
        chain_result,
        gate_ctx,
        payload,
        ["signal"],
        strategy_id="aurora",
        side="BUY",
    )

    gateway._reject.assert_called_once()
    assert gateway._reject.call_args.kwargs["reason_code"] == \
        "NRR-RISK-SKEW-UNTIL-REFRESH"


def test_gate_block_with_existing_defer_is_not_duplicated() -> None:
    gateway = StrategyGateway.__new__(StrategyGateway)
    gateway._dm = SimpleNamespace(_record_blocked_intent=MagicMock())
    gateway._reject = MagicMock()
    gateway._block = MagicMock()
    terminal_result = SimpleNamespace(
        outcome=GateOutcome.BLOCK,
        context_update={"_terminal_or_defer_emitted": True},
        why_extra=[],
        reason_code="WARMUP_NOT_READY",
        reason=None,
        context="strategy_signal_gateway:warmup_gate",
        details=None,
        gate_name="warmup",
    )

    gateway._dispatch_gate_result(
        SimpleNamespace(terminal_result=terminal_result),
        SimpleNamespace(symbol="ETHUSDT", rid="rid-warmup", accumulated={}),
        {"symbol": "ETHUSDT", "strategy_id": "aurora", "side": "BUY"},
        [],
        strategy_id="aurora",
        side="BUY",
    )

    gateway._block.assert_called_once_with("ETHUSDT")
    gateway._reject.assert_not_called()
