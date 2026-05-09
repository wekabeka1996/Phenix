from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.core.facade import (
    _build_snapshot_causal_time_fields,
)
from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from apps.reference.domains.neocortex.contracts.control_decision import (
    AuthorityMode,
    ControlDecisionAction,
    ControlDecisionApplyResult,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
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


class _BridgeStub:
    def __init__(
        self,
        tmp_path: Path,
        *,
        short_circuit_reason=None,
        authority_mode=AuthorityMode.SHADOW,
        responder=None,
        journal_only_responder=None,
        shadow_counterfactual_responder=None,
        journal_only_capture_enabled: bool = False,
        journal_only_response_journal_enabled: bool = False,
        journal_only_emit_shadow_decision_logged: bool = False,
        shadow_counterfactual_capture_enabled: bool = False,
        shadow_counterfactual_response_journal_enabled: bool = False,
        shadow_counterfactual_emit_shadow_decision_logged: bool = False,
    ):
        self.short_circuit_reason = short_circuit_reason
        self.authority_mode = authority_mode
        self.deadline_ms = 10
        self.data_dir = tmp_path
        self._responder = responder
        self._journal_only_responder = journal_only_responder
        self._shadow_counterfactual_responder = shadow_counterfactual_responder
        self.journal_only_capture_enabled = journal_only_capture_enabled
        self.journal_only_response_journal_enabled = (
            journal_only_response_journal_enabled
        )
        self.journal_only_emit_shadow_decision_logged = (
            journal_only_emit_shadow_decision_logged
        )
        self.shadow_counterfactual_capture_enabled = (
            shadow_counterfactual_capture_enabled
        )
        self.shadow_counterfactual_response_journal_enabled = (
            shadow_counterfactual_response_journal_enabled
        )
        self.shadow_counterfactual_emit_shadow_decision_logged = (
            shadow_counterfactual_emit_shadow_decision_logged
        )
        self.journal_only_calls: list[object] = []
        self.shadow_counterfactual_calls: list[object] = []

    def decide(self, request):
        if self._responder is None:
            raise AssertionError(
                "responder must be configured when trust is enabled")
        return self._responder(request)

    def journal_only_capture(self, request):
        if self._journal_only_responder is None:
            raise AssertionError(
                "journal_only_responder must be configured when journal-only capture is enabled"
            )
        self.journal_only_calls.append(request)
        return self._journal_only_responder(request)

    def shadow_counterfactual_capture(self, request):
        if self._shadow_counterfactual_responder is None:
            raise AssertionError(
                "shadow_counterfactual_responder must be configured when shadow-counterfactual capture is enabled"
            )
        self.shadow_counterfactual_calls.append(request)
        return self._shadow_counterfactual_responder(request)


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


def _projection(**overrides) -> dict:
    projection = {
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
    projection.update(overrides)
    return projection


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


def _build_observation(gateway: StrategyGateway):
    return gateway._build_authority_observation(
        decision_id="decision-1",
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


def test_trust_disabled_journal_only_capture_writes_journals_without_decide(
    tmp_path: Path,
) -> None:
    def _journal_only(request):
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.ALLOW,
            reason_code="JOURNAL_ONLY_CAPTURE",
            reason_text="journal-only capture",
            returned_at_ms=request.decision_basis_ts_ms + 1,
            model_ref="journal_only_capture",
            policy_ref="journal_only_capture",
            idempotent_key=request.idempotent_key,
            apply_result=ControlDecisionApplyResult.SHADOW_RECORDED,
        )

    bridge = _BridgeStub(
        tmp_path,
        short_circuit_reason="TRUST_DISABLED",
        authority_mode=AuthorityMode.SHADOW,
        journal_only_responder=_journal_only,
        journal_only_capture_enabled=True,
        journal_only_response_journal_enabled=True,
        journal_only_emit_shadow_decision_logged=True,
    )
    bridge.decide = MagicMock(side_effect=AssertionError(
        "kill switch must not call decide"))
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
    assert authority_context["capture_mode"] == "journal_only"
    assert authority_context["authority_applied"] is False
    assert authority_context["no_effect"] is True
    assert authority_context["apply_result"] == ControlDecisionApplyResult.SHADOW_RECORDED.value
    assert bridge.decide.call_count == 0
    assert len(bridge.journal_only_calls) == 1

    request_rows = [json.loads(line) for line in (
        tmp_path / "authority_request_journal_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    response_rows = [json.loads(line) for line in (
        tmp_path / "authority_response_journal_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(request_rows) == 1
    assert len(response_rows) == 1
    assert request_rows[0]["capture_mode"] == "journal_only"
    assert response_rows[0]["capture_mode"] == "journal_only"
    assert response_rows[0]["authority_applied"] is False
    assert response_rows[0]["no_effect"] is True


def test_trust_disabled_shadow_counterfactual_capture_writes_no_effect_evidence(
    tmp_path: Path,
) -> None:
    def _shadow_counterfactual(request):
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.DENY,
            reason_code="MODEL_DENY",
            reason_text="counterfactual deny",
            returned_at_ms=request.decision_basis_ts_ms + 1,
            model_ref="baseline_controller",
            policy_ref="baseline_controller",
            idempotent_key=request.idempotent_key,
            apply_result=ControlDecisionApplyResult.SHADOW_RECORDED,
        )

    bridge = _BridgeStub(
        tmp_path,
        short_circuit_reason="TRUST_DISABLED",
        authority_mode=AuthorityMode.SHADOW,
        shadow_counterfactual_responder=_shadow_counterfactual,
        shadow_counterfactual_capture_enabled=True,
        shadow_counterfactual_response_journal_enabled=True,
        shadow_counterfactual_emit_shadow_decision_logged=True,
    )
    bridge.decide = MagicMock(side_effect=AssertionError(
        "kill switch must not call decide"))
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
    assert authority_context["capture_mode"] == "shadow_counterfactual"
    assert authority_context["authority_applied"] is False
    assert authority_context["no_effect"] is True
    assert authority_context["action"] == ControlDecisionAction.DENY.value
    assert authority_context["returned_action"] == ControlDecisionAction.ALLOW.value
    assert authority_context["supports_counterfactual_join"] is True
    assert authority_context["counterfactual_evaluation"] is True
    assert bridge.decide.call_count == 0
    assert len(bridge.shadow_counterfactual_calls) == 1

    request_rows = [json.loads(line) for line in (
        tmp_path / "authority_request_journal_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    response_rows = [json.loads(line) for line in (
        tmp_path / "authority_response_journal_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(request_rows) == 1
    assert len(response_rows) == 1
    assert request_rows[0]["capture_mode"] == "shadow_counterfactual"
    assert response_rows[0]["capture_mode"] == "shadow_counterfactual"
    assert response_rows[0]["authority_applied"] is False
    assert response_rows[0]["no_effect"] is True
    assert response_rows[0]["returned_action"] == ControlDecisionAction.ALLOW.value
    assert response_rows[0]["supports_counterfactual_join"] is True
    assert response_rows[0]["counterfactual_evaluation"] is True


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
    metric_before = _metric_value(
        "neocortex_authority_requests_total",
        mode="gated",
        symbol="BTCUSDT",
        apply_result="GATED_DENY",
    )

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
    assert _metric_value(
        "neocortex_authority_requests_total",
        mode="gated",
        symbol="BTCUSDT",
        apply_result="GATED_DENY",
    ) == metric_before + 1.0
    dm.fsm.emit.assert_called_once()
    assert dm.fsm.emit.call_args.args[0] == "EVT:DECISION_BLOCKED"
    assert all(not str(call.args[0]).startswith("CMD:")
               for call in dm.fsm.emit.call_args_list)


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
    late_before = _metric_value("neocortex_authority_late_responses_total")
    miss_before = _metric_value("neocortex_authority_deadline_misses_total")
    request_before = _metric_value(
        "neocortex_authority_requests_total",
        mode="gated",
        symbol="BTCUSDT",
        apply_result="LATE_IGNORED",
    )

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
    assert _metric_value(
        "neocortex_authority_requests_total",
        mode="gated",
        symbol="BTCUSDT",
        apply_result="LATE_IGNORED",
    ) == request_before + 1.0
    assert _metric_value(
        "neocortex_authority_late_responses_total") == late_before + 1.0
    assert _metric_value(
        "neocortex_authority_deadline_misses_total") == miss_before + 1.0


def test_authority_journal_write_failure_increments_canonical_metric(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _allow(request):
        return ControlDecisionResponse(
            decision_id=request.decision_id,
            action=ControlDecisionAction.ALLOW,
            reason_code="MODEL_ALLOW",
            reason_text="allowed",
            returned_at_ms=request.decision_basis_ts_ms + 1,
            model_ref="baseline_controller",
            policy_ref="baseline_controller",
            idempotent_key=request.idempotent_key,
        )

    original_open = Path.open

    def _failing_open(self, *args, **kwargs):
        if self.name in {
            "authority_request_journal_v1.jsonl",
            "authority_response_journal_v1.jsonl",
        }:
            raise OSError("disk full")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _failing_open)

    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.GATED, responder=_allow)
    dm = _DMStub(bridge, _projection())
    gateway = StrategyGateway(dm)
    request_before = _metric_value(
        "neocortex_journal_write_failed_total",
        journal="authority_request_journal_v1.jsonl",
        reason_code="TELEMETRY_FLUSH_FAILED",
    )
    response_before = _metric_value(
        "neocortex_journal_write_failed_total",
        journal="authority_response_journal_v1.jsonl",
        reason_code="TELEMETRY_FLUSH_FAILED",
    )

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
    assert authority_context is not None
    assert _metric_value(
        "neocortex_journal_write_failed_total",
        journal="authority_request_journal_v1.jsonl",
        reason_code="TELEMETRY_FLUSH_FAILED",
    ) == request_before + 1.0
    assert _metric_value(
        "neocortex_journal_write_failed_total",
        journal="authority_response_journal_v1.jsonl",
        reason_code="TELEMETRY_FLUSH_FAILED",
    ) == response_before + 1.0


def test_missing_upstream_causal_proof_builds_diagnostics_only_observation(tmp_path: Path) -> None:
    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.SHADOW, responder=lambda request: None)
    dm = _DMStub(bridge, _projection())
    gateway = StrategyGateway(dm)

    observation = _build_observation(gateway)

    assert observation.event_time_source == CausalTimeProvenance.UNKNOWN
    assert observation.event_time_is_causal is False
    assert observation.trainable is False
    assert observation.dataset_visibility == "diagnostics_only"
    assert observation.missingness["causal_proof_missing"] is True
    assert observation.system_stress_state["truth_reason_code"] == "MISSING_REQUIRED_STATE"


def test_explicit_causal_upstream_proof_preserves_trainable_observation(tmp_path: Path) -> None:
    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.SHADOW, responder=lambda request: None)
    dm = _DMStub(
        bridge,
        _projection(
            feature_time_provenance=CausalTimeProvenance.AURORA_EVENT.value),
    )
    gateway = StrategyGateway(dm)

    observation = _build_observation(gateway)

    assert observation.event_time_source == CausalTimeProvenance.AURORA_EVENT
    assert observation.event_time_is_causal is True
    assert observation.trainable is True
    assert observation.dataset_visibility == "trainable"
    assert "truth_reason_code" not in observation.system_stress_state


def test_non_causal_upstream_proof_cannot_be_upgraded_to_trainable(tmp_path: Path) -> None:
    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.SHADOW, responder=lambda request: None)
    dm = _DMStub(
        bridge,
        _projection(
            feature_time_provenance=CausalTimeProvenance.CAPTURED_WALLCLOCK.value,
            event_time_is_causal=True,
            trainable=True,
            dataset_visibility="trainable",
        ),
    )
    gateway = StrategyGateway(dm)

    observation = _build_observation(gateway)

    assert observation.event_time_source == CausalTimeProvenance.CAPTURED_WALLCLOCK
    assert observation.event_time_is_causal is False
    assert observation.trainable is False
    assert observation.dataset_visibility == "diagnostics_only"
    assert observation.missingness["causal_proof_non_causal"] is True
    assert observation.system_stress_state["truth_reason_code"] == "NON_CAUSAL_TIME"


def test_snapshot_builder_emits_causal_fields_from_feature_state_proof() -> None:
    fields = _build_snapshot_causal_time_fields(
        {
            "timestamp_ms": 1_710_000_000_000,
            "time_provenance": CausalTimeProvenance.AURORA_EVENT.value,
        },
        decision_basis_ts_ms=1_710_000_000_100,
    )

    assert fields["event_time_source"] == CausalTimeProvenance.AURORA_EVENT.value
    assert fields["feature_time_provenance"] == CausalTimeProvenance.AURORA_EVENT.value
    assert fields["event_time_is_causal"] is True
    assert fields["trainable"] is True
    assert fields["dataset_visibility"] == "trainable"
    assert fields["event_ts_ms"] == 1_710_000_000_000
    assert fields["decision_basis_ts_ms"] == 1_710_000_000_100


def test_snapshot_builder_does_not_fake_causal_without_provenance() -> None:
    fields = _build_snapshot_causal_time_fields(
        {
            "timestamp_ms": 1_710_000_000_000,
        },
        decision_basis_ts_ms=1_710_000_000_100,
    )

    assert fields["event_time_source"] == CausalTimeProvenance.UNKNOWN.value
    assert fields["event_time_is_causal"] is False
    assert fields["trainable"] is False
    assert fields["dataset_visibility"] == "diagnostics_only"
    assert fields["decision_basis_ts_ms"] == 1_710_000_000_100
    assert fields["event_ts_ms"] == 1_710_000_000_000
    assert "feature_time_provenance" not in fields


def test_empty_state_vector_fallback_does_not_imply_trainable_truth(tmp_path: Path) -> None:
    bridge = _BridgeStub(
        tmp_path, authority_mode=AuthorityMode.SHADOW, responder=lambda request: None)
    projection = _projection()
    projection["observation"] = {"features": {}}
    dm = _DMStub(bridge, projection)
    gateway = StrategyGateway(dm)

    observation = _build_observation(gateway)

    assert observation.missingness["state_vector_fallback_used"] is True
    assert observation.trainable is False
    assert observation.dataset_visibility == "diagnostics_only"
