"""Unit tests for non-executable agent proposal ledger records."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.agent_proposals import (
    AgentProposalRecord,
    AgentProposalStore,
)


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def test_trade_intent_draft_is_non_executable_but_allows_bias_metadata():
    proposal = AgentProposalRecord(
        session_id="session-1",
        agent_id="agent-3",
        agent_number=3,
        kind="trade_intent_draft",
        confidence=0.62,
        rationale="BTC momentum is changing, request operator review.",
        source_refs=["report:p35c"],
        payload={
            "symbol": "BTCUSDT",
            "side_bias": "long",
            "rationale": "Funding and flow context shifted.",
            "refs": ["market-note:1"],
        },
    )

    assert proposal.execution_authority is False
    assert proposal.status == "pending"
    assert proposal.payload["side_bias"] == "long"


def test_model_rejects_top_level_extra_and_execution_authority():
    with pytest.raises(Exception):
        AgentProposalRecord(
            session_id="session-1",
            agent_id="agent-3",
            agent_number=3,
            kind="analysis_note",
            rationale="not executable",
            leverage=5,
        )

    with pytest.raises(Exception):
        AgentProposalRecord(
            session_id="session-1",
            agent_id="agent-3",
            agent_number=3,
            kind="analysis_note",
            rationale="not executable",
            execution_authority=True,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"order": {"symbol": "BTCUSDT"}},
        {"draft": {"sizing": {"risk": "1%"}}},
        {"leverage": 5},
        {"quantity": "0.1"},
        {"notional": 1000},
        {"exchange_order_id": "abc"},
        {"client_order_id": "abc"},
    ],
)
def test_model_rejects_forbidden_payload_fields(payload):
    with pytest.raises(ValueError):
        AgentProposalRecord(
            session_id="session-1",
            agent_id="agent-3",
            agent_number=3,
            kind="trade_intent_draft",
            rationale="operator review only",
            payload=payload,
        )


def test_store_create_list_get_records(tmp_path):
    store = AgentProposalStore(make_settings(), root_dir=tmp_path)

    created = store.create_proposal(
        session_id="session-1",
        agent_id="agent-3",
        agent_number=3,
        kind="memory_refresh",
        rationale="Refresh memory after accepted report.",
        source_refs=["report:p35c"],
        payload={"section": "session-memory"},
    )

    target = (
        tmp_path
        / ".agent_memory"
        / "sessions"
        / "session-1"
        / "agent_proposals"
        / f"{created.proposal_id}.dsproposal.json"
    )
    assert target.exists()
    assert store.get_proposal(created.proposal_id).rationale == "Refresh memory after accepted report."
    assert store.list_proposals(session_id="session-1")[0].proposal_id == created.proposal_id
