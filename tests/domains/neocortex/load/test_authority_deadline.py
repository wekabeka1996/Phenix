from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from apps.reference.domains.neocortex.contracts.control_decision import (
    AuthorityMode,
    ControlDecisionAction,
    ControlDecisionApplyResult,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    get_failure_outcome_counts,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.transport.authority_bridge import NeocortexAuthorityBridge
from apps.reference.telemetry.metrics import generate_latest


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    label_fragments = [f'{key}="{value}"' for key, value in labels.items()]
    pattern = re.compile(r" (-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)$")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(fragment in line for fragment in label_fragments):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        match = pattern.search(line)
        if match is not None:
            return float(match.group(1))
    return 0.0


class _CountingBaselineController:
    def __init__(self) -> None:
        self.state_vector_calls = 0
        self.predict_calls = 0

    def state_vector_from_snapshot(self, _snapshot):
        self.state_vector_calls += 1
        return [0.8]

    def predict_intent(self, _state_vector):
        self.predict_calls += 1
        return "ALLOW"


class _DMStub:
    def __init__(self, bridge, projection, *, now_ms: int, allow_snapshot: bool = True) -> None:
        self.logger = logging.getLogger("tests.phase5.authority.load")
        self._clock = SimpleNamespace(now_ms=lambda: now_ms)
        self._neocortex_authority_bridge = bridge
        if allow_snapshot:
            self._build_pre_authority_snapshot = lambda **_kwargs: (
                projection, {})
        else:
            self._build_pre_authority_snapshot = MagicMock(
                side_effect=AssertionError("snapshot builder should not run"))
        self.fsm = SimpleNamespace(emit=MagicMock())
        self.blocked_symbols: list[str] = []

    def _record_blocked_intent(self, symbol: str) -> None:
        self.blocked_symbols.append(symbol)


def _config(tmp_path: Path, *, trust_enabled: bool, mode: AuthorityMode, deadline_ms: int = 10):
    return SimpleNamespace(
        trust_enabled=trust_enabled,
        authority=SimpleNamespace(mode=mode.value, deadline_ms=deadline_ms),
        system=SimpleNamespace(data_dir=tmp_path),
    )


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


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1,
                int((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


@pytest.fixture(autouse=True)
def _reset_failure_outcomes_fixture():
    reset_failure_outcomes()
    yield
    reset_failure_outcomes()


def test_trust_disabled_fast_path_is_side_effect_free_and_under_1ms(tmp_path: Path) -> None:
    baseline = _CountingBaselineController()
    bridge = NeocortexAuthorityBridge(
        config=_config(tmp_path, trust_enabled=False,
                       mode=AuthorityMode.SHADOW),
        baseline_controller=baseline,
    )
    bridge.decide = MagicMock(side_effect=AssertionError(
        "kill switch must not call decide"))
    gateway = StrategyGateway(
        _DMStub(bridge, _projection(), now_ms=1_700_000_000_000, allow_snapshot=False))
    metric_before = _metric_value(
        "neocortex_authority_kill_switch_active_total")

    durations_ms: list[float] = []
    for _ in range(1000):
        started = time.perf_counter_ns()
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
        durations_ms.append((time.perf_counter_ns() - started) / 1_000_000.0)
        assert blocked is False
        assert authority_context["apply_result"] == ControlDecisionApplyResult.TRUST_DISABLED_FASTPATH.value

    assert _percentile(durations_ms, 99.0) < 1.0
    assert baseline.state_vector_calls == 0
    assert baseline.predict_calls == 0
    assert bridge.decide.call_count == 0
    assert get_failure_outcome_counts() == {}
    assert not (tmp_path / "authority_request_journal_v1.jsonl").exists()
    assert not (tmp_path / "authority_response_journal_v1.jsonl").exists()
    assert _metric_value(
        "neocortex_authority_kill_switch_active_total") == metric_before + 1000.0


def test_deadline_budget_hits_99_5_percent_for_1000_calls(tmp_path: Path) -> None:
    def _allow(request):
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.ALLOW,
            reason_code="MODEL_ALLOW",
            reason_text="allowed",
            returned_at_ms=int(time.time() * 1000),
            model_ref="baseline_controller",
            policy_ref="baseline_controller",
            idempotent_key=request.idempotent_key,
        )

    bridge = NeocortexAuthorityBridge(
        config=_config(tmp_path, trust_enabled=True,
                       mode=AuthorityMode.GATED, deadline_ms=10),
        authority_fn=_allow,
    )
    gateway = StrategyGateway(
        _DMStub(bridge, _projection(), now_ms=int(time.time() * 1000)))

    durations_ms: list[float] = []
    on_time = 0
    for _ in range(1000):
        decision_start_ms = int(time.time() * 1000)
        started = time.perf_counter_ns()
        authority_context, blocked = gateway._evaluate_neocortex_authority(
            symbol="BTCUSDT",
            side="BUY",
            rid="rid-1",
            strategy_id="aurora",
            qty_dec=0.5,
            entry_price_dec=50000.0,
            decision_basis_ts_ms=decision_start_ms,
            latest_risk=_latest_risk(),
            gate_ctx=_gate_ctx(),
            chain_result=_chain_result(),
        )
        durations_ms.append((time.perf_counter_ns() - started) / 1_000_000.0)
        assert blocked is False
        if authority_context["apply_result"] != ControlDecisionApplyResult.LATE_IGNORED.value:
            on_time += 1

    hit_rate = (on_time / 1000.0) * 100.0
    assert hit_rate >= 99.5
    assert _percentile(durations_ms, 99.0) < 10.0
