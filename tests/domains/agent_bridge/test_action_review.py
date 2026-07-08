from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.domains.agent_bridge.action_review import (
    ActionReviewLedger,
    ActionReviewV1,
    LEDGER_FILENAME,
    SCENARIO_IDS,
    estimate_review_tokens,
    finalize_action_review,
    lint_action_review,
    review_ref,
    validate_ledger,
)
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer


NOW = 1_800_000_000_000


def _review_data(*, review_id="review_p9_btc_001", packet_id="afp_aaaaaaaa", symbol="BTCUSDT"):
    packet_ref = f"agent-feed://packet/{packet_id}"
    return {
        "schema_version": "action-review/v1",
        "review_id": review_id,
        "revision": 1,
        "supersedes_ref": None,
        "created_ts_ms": NOW,
        "updated_ts_ms": NOW,
        "mode": "no_execution",
        "source": "deterministic_fixture",
        "agent_id": "p9.no-model.fixture",
        "model_id": None,
        "model_call_ref": None,
        "operator_ref": "p9://deterministic-test-author",
        "packet_ref": packet_ref,
        "symbol": symbol,
        "horizon": "next_packet",
        "pre_action_note": {
            "review_id": review_id,
            "packet_id": packet_id,
            "symbol": symbol,
            "horizon": "next_packet",
            "proposed_action": "OBSERVE",
            "thesis": "Deterministic no-model fixture waits for another packet before any conclusion.",
            "invalidation": "The source packet becomes stale or the parity state changes.",
            "expected_scenarios": [{
                "scenario_id": "no_clear_scenario",
                "confidence": 0.6,
                "thesis": "One short observation window may not establish a clear scenario.",
                "evidence_refs": [packet_ref],
            }],
            "warnings_acknowledged": ["filter parity acknowledgement may be missing"],
            "data_refs_used": [packet_ref],
            "tool_refs_used": ["agent-bridge://deterministic-fixture/v1"],
            "confidence": 0.55,
            "no_execution": True,
        },
        "execution_note": {
            "status": "not_submitted_p9_no_execution",
            "submitted": False,
            "detail": "P9 records memory only; no execution route is available.",
            "no_execution": True,
        },
        "outcome_review": None,
        "raw_refs": [packet_ref],
        "compact_summary": "No-model OBSERVE note linked to one packet; no action was submitted.",
        "token_estimate": 1,
        "validation_status": "valid",
    }


def _review(**kwargs) -> ActionReviewV1:
    return finalize_action_review(_review_data(**kwargs))


def _outcome_revision(first: ActionReviewV1) -> ActionReviewV1:
    data = first.model_dump(mode="python")
    later_ref = "agent-feed://packet/afp_bbbbbbbb"
    data.update({
        "revision": 2,
        "supersedes_ref": review_ref(first.review_id, 1),
        "updated_ts_ms": NOW + 5_000,
        "outcome_review": {
            "observed_from_packet_ref": first.packet_ref,
            "observed_to_packet_ref": later_ref,
            "observation_window_ms": 5_000,
            "what_happened": "A later packet arrived without enough evidence for a directional scenario.",
            "realized_scenario": "no_clear_scenario",
            "scenario_confidence": 0.7,
            "evidence_refs": [first.packet_ref, later_ref],
            "expected_result_achieved": True,
            "outcome_unexpected": False,
            "logical_explanation": "The bounded window was intentionally short and observational.",
            "lesson_to_remember": "Keep the scenario unresolved when packet evidence is insufficient.",
            "future_review_needed": False,
            "no_trade_pnl_claim": True,
        },
        "raw_refs": [first.packet_ref, later_ref],
        "compact_summary": "No clear scenario realized in the next packet; preserve uncertainty and no execution.",
        "token_estimate": 1,
    })
    return finalize_action_review(data)


def test_scenario_taxonomy_is_small_complete_and_unique() -> None:
    assert len(SCENARIO_IDS) == 11
    assert len(set(SCENARIO_IDS)) == len(SCENARIO_IDS)
    assert {"continuation", "chop_fee_trap", "data_stale_or_missing", "no_clear_scenario"} <= set(SCENARIO_IDS)


def test_action_review_contract_is_no_model_and_no_execution() -> None:
    review = _review()
    assert review.schema_version == "action-review/v1"
    assert review.model_id is None and review.model_call_ref is None
    assert review.pre_action_note.no_execution is True
    assert review.execution_note.submitted is False
    assert review.execution_note.status == "not_submitted_p9_no_execution"
    assert lint_action_review(review) == []
    assert review.token_estimate == estimate_review_tokens(review)


def test_model_refs_submitted_state_and_order_identity_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        ActionReviewV1.model_validate({**_review_data(), "model_call_ref": "fake://model-call"})
    submitted = _review_data()
    submitted["execution_note"]["submitted"] = True
    with pytest.raises(ValidationError):
        ActionReviewV1.model_validate(submitted)
    order_identity = _review_data()
    order_identity["execution_note"]["order_id"] = "12345"
    with pytest.raises(ValidationError):
        ActionReviewV1.model_validate(order_identity)


def test_hypothetical_actions_require_hypothetical_no_submit_status() -> None:
    data = _review_data()
    data["mode"] = "hypothetical"
    data["pre_action_note"]["proposed_action"] = "HYPOTHETICAL_OPEN_LONG"
    data["execution_note"]["status"] = "not_submitted_hypothetical"
    assert finalize_action_review(data).mode == "hypothetical"
    data["execution_note"]["status"] = "future_field_unset"
    with pytest.raises(ValidationError, match="incompatible"):
        ActionReviewV1.model_validate(data)


def test_secret_looking_content_fails_ledger_lint(tmp_path: Path) -> None:
    data = _review_data()
    data["compact_summary"] = "Secret-looking fixture sk-abcdefghijklmnop must be rejected from memory."
    review = finalize_action_review(data)
    assert "secret-looking value detected" in lint_action_review(review)
    with pytest.raises(ValueError, match="secret-looking"):
        ActionReviewLedger(tmp_path).append(review)


def test_append_is_idempotent_and_concurrent_rows_remain_valid(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path)
    first = _review()
    assert ledger.append(first) is True
    assert ledger.append(first) is False

    reviews = [
        _review(review_id=f"review_p9_{index:03d}", packet_id=f"afp_{index + 1:08x}")
        for index in range(8)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(ledger.append, reviews))
    assert len(ledger.rows()) == 9
    assert validate_ledger(tmp_path / LEDGER_FILENAME) == []


def test_outcome_is_append_only_revision_with_explicit_supersession(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path)
    first = _review()
    second = _outcome_revision(first)
    assert ledger.append(first)
    assert ledger.append(second)
    rows = ledger.rows()
    assert [row.revision for row in rows] == [1, 2]
    assert rows[1].supersedes_ref == review_ref(first.review_id, 1)
    assert rows[1].outcome_review.realized_scenario == "no_clear_scenario"
    assert rows[1].outcome_review.no_trade_pnl_claim is True
    assert ledger.latest()[first.review_id].revision == 2

    changed = second.model_copy(update={"symbol": "ETHUSDT", "revision": 3, "supersedes_ref": review_ref(first.review_id, 2)})
    with pytest.raises(ValueError, match="immutable"):
        ledger.append(changed)


def test_packet_summary_links_latest_revision_and_stays_bounded(tmp_path: Path) -> None:
    ledger_dir = tmp_path / "ops" / "agent_bridge" / "action_reviews"
    ledger = ActionReviewLedger(ledger_dir)
    first = _review()
    ledger.append(first)
    ledger.append(_outcome_revision(first))
    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW + 6_000).build_packet(
        symbols=["BTCUSDT"]
    )
    memory = packet.action_review_memory
    assert memory.latest_review_ids_by_symbol == {"BTCUSDT": first.review_id}
    assert memory.latest_scenario_memory[0].revision == 2
    assert memory.latest_scenario_memory[0].realized_scenario == "no_clear_scenario"
    assert memory.latest_scenario_memory[0].unresolved is False
    assert packet.budget.estimated_tokens <= 4_400


def test_wrong_packet_ref_and_invalid_revision_fail_closed() -> None:
    with pytest.raises(ValidationError, match="packet_ref"):
        ActionReviewV1.model_validate({**_review_data(), "packet_ref": "agent-feed://packet/afp_deadbeef"})
    with pytest.raises(ValidationError, match="supersedes"):
        ActionReviewV1.model_validate({**_review_data(), "revision": 2})


def test_outcome_expected_and_unexpected_flags_follow_taxonomy() -> None:
    first = _review()
    data = _outcome_revision(first).model_dump(mode="python")
    data["outcome_review"]["expected_result_achieved"] = False
    data["token_estimate"] = 1
    with pytest.raises(ValidationError, match="expected_result_achieved"):
        ActionReviewV1.model_validate(data)
