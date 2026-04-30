from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from apps.reference.domains.neocortex.contracts.control_decision import (
    AuthorityMode,
    ControlDecisionAction,
    ControlDecisionRequest,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import ObservationEnvelope
from apps.reference.domains.neocortex.logic.datasets.time_provenance import CausalTimeProvenance
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


class _BaselineController:
    def __init__(self, decision: str) -> None:
        self._decision = decision

    def state_vector_from_snapshot(self, _snapshot):
        return [0.8]

    def predict_intent(self, _state_vector):
        return self._decision


def _config(tmp_path: Path, *, trust_enabled: bool, mode: AuthorityMode = AuthorityMode.SHADOW):
    return SimpleNamespace(
        trust_enabled=trust_enabled,
        authority=SimpleNamespace(mode=mode.value, deadline_ms=10),
        system=SimpleNamespace(data_dir=tmp_path),
    )


def _request() -> ControlDecisionRequest:
    observation = ObservationEnvelope(
        observation_id="decision-1",
        symbol="BTCUSDT",
        decision_basis_ts_ms=1_700_000_000_000,
        source_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
        source_event_id="rid-1",
        event_time_source=CausalTimeProvenance.AURORA_EVENT,
        event_time_is_causal=True,
        trainable=True,
        dataset_visibility="trainable",
        freshness={"snapshot_age_ms": 0},
        missingness={"market_features_missing": False},
        market_features={"signal_score": 0.8},
        regime_state={"label": "TREND_UP"},
        risk_state={"risk_score": 0.2},
        portfolio_state={"side": "FLAT"},
        system_stress_state={"trigger_event_type": "EVT:AUTHORITY_DECISION"},
        candidate_intent_summary={"side": "BUY", "reduce_only": False},
        gate_trace_summary={"final_outcome": "PASS"},
        state_vector=(0.8,),
        context_vector=(1.0,),
    )
    return ControlDecisionRequest(
        decision_id="decision-1",
        rid="rid-1",
        symbol="BTCUSDT",
        authority_mode=AuthorityMode.SHADOW,
        decision_basis_ts_ms=1_700_000_000_000,
        deadline_ms=10,
        expires_at_ms=1_700_000_000_010,
        observation=observation,
        candidate_intent_summary={"side": "BUY"},
        idempotent_key="decision-1",
    )


def test_short_circuit_reason_is_trust_disabled(tmp_path: Path) -> None:
    bridge = NeocortexAuthorityBridge(
        config=_config(tmp_path, trust_enabled=False),
        baseline_controller=_BaselineController("ALLOW"),
    )

    assert bridge.short_circuit_reason == "TRUST_DISABLED"


def test_bridge_uses_baseline_controller_allow_when_enabled(tmp_path: Path) -> None:
    bridge = NeocortexAuthorityBridge(
        config=_config(tmp_path, trust_enabled=True,
                       mode=AuthorityMode.ADVISORY),
        baseline_controller=_BaselineController("ALLOW"),
    )

    response = bridge.decide(_request())

    assert response.action == ControlDecisionAction.ALLOW
    assert response.reason_code == "MODEL_ALLOW"


def test_bridge_falls_back_when_symbol_is_already_inflight(tmp_path: Path) -> None:
    bridge = NeocortexAuthorityBridge(
        config=_config(tmp_path, trust_enabled=True),
        baseline_controller=_BaselineController("ALLOW"),
    )
    assert bridge._try_acquire_symbol("BTCUSDT") is True
    metric_before = _metric_value(
        "neocortex_authority_fallback_total",
        policy="authority_guard",
        reason_code="BRIDGE_UNAVAILABLE",
    )

    response = bridge.decide(_request())

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.reason_code == "BRIDGE_UNAVAILABLE"
    assert _metric_value(
        "neocortex_authority_fallback_total",
        policy="authority_guard",
        reason_code="BRIDGE_UNAVAILABLE",
    ) == metric_before + 1.0
