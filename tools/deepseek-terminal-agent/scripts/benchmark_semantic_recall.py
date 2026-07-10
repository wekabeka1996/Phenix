"""Deterministic semantic recall benchmark for P41Y memory surfaces."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from deepseek_terminal_agent.config import DeepSeekConfig, Settings  # noqa: E402
from deepseek_terminal_agent.sessions.collective_memory import CollectiveMemoryStore  # noqa: E402
from deepseek_terminal_agent.sessions.collective_memory_models import (  # noqa: E402
    FSMDispatchResult,
    SemanticFact,
    SourceReference,
)
from deepseek_terminal_agent.sessions.coordination_config import load_coordination_config  # noqa: E402
from deepseek_terminal_agent.sessions.models import ModelProfile  # noqa: E402
from deepseek_terminal_agent.sessions.store import SessionStore  # noqa: E402


EXPECTED_FACTS: dict[str, dict[str, Any]] = {
    "position:ETHUSDT:opened": {
        "value": {"state": "OPEN", "side": "LONG", "quantity": "0.01"},
        "agent_id": "api_agent_01",
        "symbol": "ETHUSDT",
        "critical": True,
    },
    "risk_warning:risk-semantic-1": {
        "value": {"summary": "ETH and BNB correlated exposure exceeded review threshold"},
        "agent_id": "api_agent_01",
        "symbol": "ETHUSDT",
        "critical": True,
    },
    "instruction:api_agent_01": {
        "value": {"manifest_version": "manifest-semantic-v3"},
        "agent_id": "api_agent_01",
        "symbol": None,
        "critical": True,
    },
    "feature_trust:api_agent_01:order_book_imbalance:v1": {
        "value": {
            "feature_name": "order_book_imbalance",
            "trust": 0.35,
            "version": 1,
        },
        "agent_id": "api_agent_01",
        "symbol": None,
        "critical": False,
    },
    "agent_disagreement:SOLUSDT": {
        "value": {"api_bias": "long", "cli_bias": "flat", "resolution": "unresolved"},
        "agent_id": "api_agent_01",
        "symbol": "SOLUSDT",
        "critical": False,
    },
    "command_intent:cmd-semantic-rejected": {
        "value": {
            "command_kind": "REQUEST_ORDER",
            "intent_ref": "intent://semantic/rejected",
            "status": "pending_fsm",
        },
        "agent_id": "api_agent_01",
        "symbol": "ETHUSDT",
        "critical": True,
    },
    "dispatch_in_doubt:cmd-semantic-rejected": {
        "value": {"dispatch_state": "dispatch_started"},
        "agent_id": "api_agent_01",
        "symbol": None,
        "critical": True,
    },
    "fsm_decision:cmd-semantic-rejected": {
        "value": {"accepted": False, "reason": "portfolio risk budget unavailable"},
        "agent_id": "api_agent_01",
        "symbol": None,
        "critical": True,
    },
    "command_intent:cmd-semantic-ambiguous": {
        "value": {
            "command_kind": "REQUEST_ORDER",
            "intent_ref": "intent://semantic/ambiguous",
            "status": "pending_fsm",
        },
        "agent_id": "cli_agent_01",
        "symbol": "XRPUSDT",
        "critical": True,
    },
    "dispatch_in_doubt:cmd-semantic-ambiguous": {
        "value": {"dispatch_state": "dispatch_started"},
        "agent_id": "cli_agent_01",
        "symbol": None,
        "critical": True,
    },
    "dispatch_reconciliation:cmd-semantic-ambiguous": {
        "value": {
            "status": "not_submitted",
            "reason": "venue and FSM journals contain no external submission",
        },
        "agent_id": "cli_agent_01",
        "symbol": None,
        "critical": True,
    },
    "position:ETHUSDT:closed": {
        "value": {"state": "CLOSED", "reason": "operator review"},
        "agent_id": "api_agent_01",
        "symbol": "ETHUSDT",
        "critical": True,
    },
}


def _semantic_payload(
    fact_key: str,
    category: str,
    value: dict[str, Any],
    *,
    agent_id: str | None,
    symbol: str | None,
) -> dict[str, Any]:
    return {
        "semantic_fact": {
            "fact_key": fact_key,
            "category": category,
            "value": value,
            "agent_id": agent_id,
            "symbol": symbol,
        }
    }


def _score_surface(
    facts: list[SemanticFact],
    *,
    raw_event_ids: set[str],
) -> dict[str, Any]:
    by_key = {fact.fact_key: fact for fact in facts}
    exact = 0
    agent_correct = 0
    symbol_correct = 0
    agent_total = 0
    symbol_total = 0
    critical_total = 0
    critical_correct = 0
    instruction_correct = False
    for key, expected in EXPECTED_FACTS.items():
        fact = by_key.get(key)
        if fact is not None and fact.value == expected["value"]:
            exact += 1
        if expected["agent_id"] is not None:
            agent_total += 1
            if fact is not None and fact.agent_id == expected["agent_id"]:
                agent_correct += 1
        if expected["symbol"] is not None:
            symbol_total += 1
            if fact is not None and fact.symbol == expected["symbol"]:
                symbol_correct += 1
        if expected["critical"]:
            critical_total += 1
            if fact is not None and fact.critical and fact.value == expected["value"]:
                critical_correct += 1
        if key == "instruction:api_agent_01":
            instruction_correct = fact is not None and fact.value == expected["value"]
    opened = by_key.get("position:ETHUSDT:opened")
    closed = by_key.get("position:ETHUSDT:closed")
    chronology_correct = bool(opened and closed and opened.sequence < closed.sequence)
    false_claims = sorted(set(by_key).difference(EXPECTED_FACTS))
    missing_expected = sorted(set(EXPECTED_FACTS).difference(by_key))
    missing_source_refs = [
        fact.fact_key
        for fact in facts
        if not fact.source_refs
        or not any(ref.source_id in raw_event_ids for ref in fact.source_refs)
    ]
    return {
        "expected_fact_count": len(EXPECTED_FACTS),
        "recalled_fact_count": len(EXPECTED_FACTS) - len(missing_expected),
        "exact_factual_recall": exact / len(EXPECTED_FACTS),
        "chronology_correct": chronology_correct,
        "agent_attribution": agent_correct / agent_total,
        "symbol_attribution": symbol_correct / symbol_total,
        "instruction_version_correct": instruction_correct,
        "critical_event_recall": critical_correct / critical_total,
        "false_claim_count": len(false_claims),
        "false_claims": false_claims,
        "missing_expected_facts": missing_expected,
        "missing_source_reference_count": len(missing_source_refs),
        "missing_source_references": missing_source_refs,
    }


def run_benchmark(work_root: Path) -> dict[str, Any]:
    settings = Settings(deepseek=DeepSeekConfig(api_key="semantic-benchmark-non-secret"))
    sessions = SessionStore(settings, root_dir=work_root)
    session = sessions.create_session(
        title="P41Y deterministic semantic recall",
        default_profile=ModelProfile(
            profile_id="semantic-recall",
            name="Semantic Recall",
            model_id="deepseek-v4-pro",
        ),
    )
    store = CollectiveMemoryStore(
        settings,
        root_dir=work_root,
        config=load_coordination_config(),
        session_store=sessions,
    )
    store.initialize_session(session.session_id)

    store.append_evidence(
        session_id=session.session_id,
        event_type="LIFECYCLE_EVENT",
        category="position_lifecycle",
        agent_id="api_agent_01",
        agent_number=1,
        event_id="evt-semantic-position-open",
        idempotency_key="semantic-position-open",
        critical=True,
        payload=_semantic_payload(
            "position:ETHUSDT:opened",
            "position_change",
            EXPECTED_FACTS["position:ETHUSDT:opened"]["value"],
            agent_id="api_agent_01",
            symbol="ETHUSDT",
        ),
    )
    store.append_evidence(
        session_id=session.session_id,
        event_type="RISK_WARNING_PUBLISHED",
        category="risk",
        agent_id="api_agent_01",
        agent_number=1,
        event_id="evt-semantic-risk-warning",
        idempotency_key="semantic-risk-warning",
        critical=True,
        payload={
            "publication_id": "risk-semantic-1",
            "kind": "risk_warning",
            "summary": EXPECTED_FACTS["risk_warning:risk-semantic-1"]["value"]["summary"],
            "symbol": "ETHUSDT",
            "source_refs": [],
        },
    )
    store.ack_instructions(
        session_id=session.session_id,
        agent_id="api_agent_01",
        agent_number=1,
        manifest_version="manifest-semantic-v3",
        idempotency_key="semantic-instruction-v3",
    )
    store.update_feature_trust(
        session_id=session.session_id,
        agent_id="api_agent_01",
        agent_number=1,
        feature_name="order_book_imbalance",
        trust=0.35,
        reason="feature degraded during spread expansion",
        source_refs=[],
        idempotency_key="semantic-feature-trust-v1",
    )
    store.append_evidence(
        session_id=session.session_id,
        event_type="AGENT_DISAGREEMENT_RECORDED",
        category="peer_coordination",
        agent_id="api_agent_01",
        agent_number=1,
        event_id="evt-semantic-disagreement",
        idempotency_key="semantic-disagreement",
        critical=False,
        payload=_semantic_payload(
            "agent_disagreement:SOLUSDT",
            "agent_disagreement",
            EXPECTED_FACTS["agent_disagreement:SOLUSDT"]["value"],
            agent_id="api_agent_01",
            symbol="SOLUSDT",
        ),
    )

    store.request_command(
        session_id=session.session_id,
        agent_id="api_agent_01",
        agent_number=1,
        command_kind="REQUEST_ORDER",
        symbol="ETHUSDT",
        rationale="semantic benchmark rejection",
        intent_ref="intent://semantic/rejected",
        sizing_ref="config://llm_microstructure/execution",
        command_id="cmd-semantic-rejected",
        idempotency_key="semantic-command-rejected",
    )
    store.dispatch_command_to_fsm(
        session_id=session.session_id,
        command_id="cmd-semantic-rejected",
        fsm_gateway=lambda _command: FSMDispatchResult(
            accepted=False,
            reason="portfolio risk budget unavailable",
            source_refs=[
                SourceReference(source_id="fsm-rejection-proof", source_type="fsm_decision")
            ],
        ),
    )

    store.request_command(
        session_id=session.session_id,
        agent_id="cli_agent_01",
        agent_number=2,
        command_kind="REQUEST_ORDER",
        symbol="XRPUSDT",
        rationale="semantic benchmark ambiguous dispatch",
        intent_ref="intent://semantic/ambiguous",
        sizing_ref="config://llm_microstructure/execution",
        command_id="cmd-semantic-ambiguous",
        idempotency_key="semantic-command-ambiguous",
    )
    try:
        store.dispatch_command_to_fsm(
            session_id=session.session_id,
            command_id="cmd-semantic-ambiguous",
            fsm_gateway=lambda _command: (_ for _ in ()).throw(
                RuntimeError("simulated response loss")
            ),
        )
    except RuntimeError:
        pass
    store.recover_session(
        session.session_id,
        exchange_reconciler=lambda commands: {
            commands[0].command_id: {
                "status": "not_submitted",
                "reason": "venue and FSM journals contain no external submission",
                "source_refs": [
                    SourceReference(
                        source_id="recovery-not-submitted-proof",
                        source_type="exchange_reconciliation",
                    ).model_dump()
                ],
            }
        },
    )
    store.append_evidence(
        session_id=session.session_id,
        event_type="LIFECYCLE_EVENT",
        category="position_lifecycle",
        agent_id="api_agent_01",
        agent_number=1,
        event_id="evt-semantic-position-close",
        idempotency_key="semantic-position-close",
        critical=True,
        payload=_semantic_payload(
            "position:ETHUSDT:closed",
            "position_change",
            EXPECTED_FACTS["position:ETHUSDT:closed"]["value"],
            agent_id="api_agent_01",
            symbol="ETHUSDT",
        ),
    )

    for index in range(320):
        if index % 2:
            agent_id, agent_number, symbol = "api_agent_01", 1, "SOLUSDT"
        else:
            agent_id, agent_number, symbol = "cli_agent_01", 2, "BNBUSDT"
        store.append_evidence(
            session_id=session.session_id,
            event_type="MARKET_CONTEXT_UPDATED",
            category="market_context",
            agent_id=agent_id,
            agent_number=agent_number,
            idempotency_key=f"semantic-pressure:{index}",
            critical=False,
            payload={
                "symbol": symbol,
                "cadence_seconds": 30,
                "update_index": index,
            },
        )

    checkpoint = store.create_checkpoint(session.session_id)
    raw_events = [
        event
        for event in store.list_events(session.session_id)
        if event.sequence <= checkpoint.manifest.end_sequence
    ]
    raw_ids = {event.event_id for event in raw_events}
    active_context = store.active_context_for_checkpoint(checkpoint)
    active_facts = [
        SemanticFact.model_validate(item) for item in active_context["semantic_facts"]
    ]
    checkpoint_source_ids = {ref.source_id for ref in checkpoint.manifest.source_references}
    retrieved_events = [event for event in raw_events if event.event_id in checkpoint_source_ids]
    surfaces = {
        "A_raw_evidence": store.extract_semantic_facts(raw_events),
        "B_active_context_only": active_facts,
        "C_checkpoint_plus_source_retrieval": store.extract_semantic_facts(retrieved_events),
        "D_carryover_bundle": checkpoint.carryover.semantic_facts,
    }
    scores = {
        name: _score_surface(facts, raw_event_ids=raw_ids)
        for name, facts in surfaces.items()
    }
    return {
        "session_id": session.session_id,
        "expected_fact_count": len(EXPECTED_FACTS),
        "raw_event_count": len(raw_events),
        "active_context_tokens": checkpoint.manifest.active_context_tokens,
        "token_count_kind": checkpoint.manifest.token_count_kind,
        "checkpoint_source_reference_count": len(checkpoint.manifest.source_references),
        "critical_source_reference_retention": (
            set(checkpoint.manifest.critical_event_ids).issubset(checkpoint_source_ids)
        ),
        "scores": scores,
        "llm_judge_used": False,
        "compression_ratio_used_as_quality_proof": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.work_root is None:
        with tempfile.TemporaryDirectory(prefix="p41y-semantic-") as temp_dir:
            result = run_benchmark(Path(temp_dir))
    else:
        args.work_root.mkdir(parents=True, exist_ok=True)
        result = run_benchmark(args.work_root)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
