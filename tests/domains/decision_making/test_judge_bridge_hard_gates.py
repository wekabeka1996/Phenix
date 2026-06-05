from __future__ import annotations

import pytest

from apps.reference.config.domains.decision_making import JudgeBridgeConfig
from apps.reference.domains.decision_making.judge_bridge import evaluate_judge_bridge

from tests.config.test_judge_bridge_config_contract import hybrid_config_payload
from tests.domains.decision_making.test_judge_bridge_modes import _candidate, _verdict


MANDATORY_GATES = [
    "panic_killswitch",
    "exchange_filter_fail",
    "exposure_limit",
    "stale_features",
    "stale_regime",
    "order_guardian_block",
]


def _config() -> JudgeBridgeConfig:
    return JudgeBridgeConfig.model_validate(hybrid_config_payload())


@pytest.mark.parametrize("gate", MANDATORY_GATES)
def test_mandatory_hard_gate_failure_blocks_bridge(gate: str):
    candidate = _candidate("BUY")
    hard_gate_results = dict(candidate.hard_gate_results)
    hard_gate_results[gate] = False
    candidate = candidate.model_copy(
        update={
            "hard_gate_results": hard_gate_results,
            "hard_gate_blocking_reasons": [f"source:{gate}"],
        }
    )
    decision = evaluate_judge_bridge(_verdict("OPEN_LONG", 0.70), _config(), "testnet", candidate)
    assert decision.bridge_action == "blocked"
    assert decision.applied is False
    assert decision.no_effect is True
    assert f"hard_gate_blocked:{gate}" in decision.hard_gate_blocking_reasons
    assert f"source:{gate}" in decision.hard_gate_blocking_reasons


def test_hard_gate_failure_never_allows_before_confidence_band_action():
    candidate = _candidate("BUY").model_copy(
        update={
            "hard_gate_results": {
                **_candidate("BUY").hard_gate_results,
                "panic_killswitch": False,
            }
        }
    )
    decision = evaluate_judge_bridge(_verdict("OPEN_LONG", 0.70), _config(), "testnet", candidate)
    assert decision.bridge_action != "allow"
    assert decision.confidence_band_label is None
    assert decision.hard_gates_passed is False

