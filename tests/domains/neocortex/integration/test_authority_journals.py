from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from apps.reference.domains.neocortex.contracts.control_decision import (
    AuthorityMode,
    ControlDecisionAction,
    ControlDecisionApplyResult,
    ControlDecisionResponse,
)


class _BridgeStub:
    def __init__(self, tmp_path: Path, *, short_circuit_reason=None, authority_mode=AuthorityMode.SHADOW, responder=None):
        self.short_circuit_reason = short_circuit_reason
        self.authority_mode = authority_mode
        self.deadline_ms = 10
        self.data_dir = tmp_path
        self._responder = responder

    def decide(self, request):
        if self._responder is None:
            raise AssertionError(
                "responder must be configured when trust is enabled")
        return self._responder(request)


class _DMStub:
    def __init__(self, bridge, projection):
        self.logger = logging.getLogger("tests.phase5.authority")
        self._clock = SimpleNamespace(now_ms=lambda: 1_700_000_000_000)
        self._neocortex_authority_bridge = bridge
        self._build_pre_authority_snapshot = lambda **_kwargs: (projection, {})
        self.fsm = SimpleNamespace(emit=MagicMock())
        self.blocked_symbols = []

    def _record_blocked_intent(self, symbol: str) -> None:
        self.blocked_symbols.append(symbol)


def _projection() -> dict:
    return {
        "symbol": "BTCUSDT",
        "tick_ts_ms": 1_700_000_000_000,
        "feature_event_ts_ms": 1_700_000_000_000,
        "portfolio_event_ts_ms": 1_700_000_000_000,
        "trigger_event_type": "EVT:AUTHORITY_DECISION",
        "observation": {"features": {"signal_score": 0.9, "spread_bps": 1.2}},
        "intent": {
            "rid": "rid-1",
            "strategy_id": "aurora",
            "side": "BUY",
            "quantity": "0.5",
            "reduce_only": False,
            "proposed_action": "OPEN_LONG",
        },
        "regime_state": {"label": "TREND_UP", "confidence": 0.85},
        "portfolio_position": {"side": "FLAT"},
    }


def _gate_ctx():
    return SimpleNamespace(accumulated={"_qos_enabled": False, "safety_gate_result": None})


def _chain_result():
    return SimpleNamespace(
        final_outcome=SimpleNamespace(value="PASS"),
        total_elapsed_ms=1.2,
        trace=[SimpleNamespace(
            gate_name="risk", outcome="PASS", reason_code="", elapsed_ms=0.4)],
    )


def _latest_risk() -> dict:
    return {"risk_parameters": {"risk_score": 0.2}}


def test_trust_disabled_fast_path_skips_journals(tmp_path: Path) -> None:
    bridge = _BridgeStub(
        tmp_path, short_circuit_reason="TRUST_DISABLED", authority_mode=AuthorityMode.SHADOW)
    dm = _DMStub(bridge, _projection())
    gateway = StrategyGateway(dm)

    authority_context, blocked = gateway._evaluate_neocortex_authority(
        symbol="BTCUSDT",
        side="BUY",
        rid="rid-1",
        strategy_id="aurora",
        qty_dec=SimpleNamespace(
            __float__=lambda self: 0.5, __str__=lambda self: "0.5"),
        entry_price_dec=SimpleNamespace(
            __float__=lambda self: 50000.0, __str__=lambda self: "50000"),
        decision_basis_ts_ms=1_700_000_000_000,
        latest_risk=_latest_risk(),
        gate_ctx=_gate_ctx(),
        chain_result=_chain_result(),
    )

    assert blocked is False
    assert authority_context["apply_result"] == ControlDecisionApplyResult.TRUST_DISABLED_FASTPATH.value
    assert not (tmp_path / "authority_request_journal_v1.jsonl").exists()
    assert not (tmp_path / "authority_response_journal_v1.jsonl").exists()


def test_gated_deny_writes_journals_and_blocks(tmp_path: Path) -> None:
    def _deny(request):
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.DENY,
            reason_code="MODEL_DENY",
            reason_text="denied",
            returned_at_ms=request.decision_basis_ts_ms + 1,
            model_ref="baseline_controller",
            policy_ref="baseline_controller",
            idempotent_key=request.idempotent_key,
        )

    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.GATED, responder=_deny)
    dm = _DMStub(bridge, _projection())
    gateway = StrategyGateway(dm)

    authority_context, blocked = gateway._evaluate_neocortex_authority(
        symbol="BTCUSDT",
        side="BUY",
        rid="rid-1",
        strategy_id="aurora",
        qty_dec=0.5,
        entry_price_dec=50000.0,
        decision_basis_ts_ms=1_700_000_000_000,
        latest_risk=_latest_risk(),
        gate_ctx=_gate_ctx(),
        chain_result=_chain_result(),
    )

    assert blocked is True
    assert authority_context["apply_result"] == ControlDecisionApplyResult.GATED_DENY.value
    request_rows = [json.loads(line) for line in (
        tmp_path / "authority_request_journal_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    response_rows = [json.loads(line) for line in (
        tmp_path / "authority_response_journal_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(request_rows) == 1
    assert len(response_rows) == 1
    assert response_rows[0]["apply_result"] == ControlDecisionApplyResult.GATED_DENY.value
    dm.fsm.emit.assert_called_once()


def test_late_response_is_recorded_but_ignored(tmp_path: Path) -> None:
    def _late(request):
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.DENY,
            reason_code="MODEL_DENY",
            reason_text="late deny",
            returned_at_ms=request.expires_at_ms + 1,
            model_ref="baseline_controller",
            policy_ref="baseline_controller",
            idempotent_key=request.idempotent_key,
        )

    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.GATED, responder=_late)
    dm = _DMStub(bridge, _projection())
    gateway = StrategyGateway(dm)

    authority_context, blocked = gateway._evaluate_neocortex_authority(
        symbol="BTCUSDT",
        side="BUY",
        rid="rid-1",
        strategy_id="aurora",
        qty_dec=0.5,
        entry_price_dec=50000.0,
        decision_basis_ts_ms=1_700_000_000_000,
        latest_risk=_latest_risk(),
        gate_ctx=_gate_ctx(),
        chain_result=_chain_result(),
    )

    assert blocked is False
    assert authority_context["apply_result"] == ControlDecisionApplyResult.LATE_IGNORED.value
