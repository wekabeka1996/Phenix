"""Generate and measure a synthetic two-agent P41X session."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from deepseek_terminal_agent.config import DeepSeekConfig, Settings  # noqa: E402
from deepseek_terminal_agent.sessions.collective_memory import CollectiveMemoryStore  # noqa: E402
from deepseek_terminal_agent.sessions.collective_memory_models import PortfolioState, SourceReference  # noqa: E402
from deepseek_terminal_agent.sessions.coordination_config import load_coordination_config  # noqa: E402
from deepseek_terminal_agent.sessions.models import ModelProfile  # noqa: E402
from deepseek_terminal_agent.sessions.store import SessionStore  # noqa: E402


def run_benchmark(*, event_target: int, work_root: Path) -> dict:
    settings = Settings(deepseek=DeepSeekConfig(api_key="benchmark-non-secret"))
    sessions = SessionStore(settings, root_dir=work_root)
    session = sessions.create_session(
        title="P41X synthetic long session",
        default_profile=ModelProfile(
            profile_id="p41x-benchmark",
            name="P41X Benchmark",
            model_id="deepseek-v4-pro",
        ),
    )
    config = load_coordination_config()
    store = CollectiveMemoryStore(
        settings,
        root_dir=work_root,
        config=config,
        session_store=sessions,
    )
    store.initialize_session(session.session_id)
    agents = [
        ("api_agent_01", 1, ["ETHUSDT", "SOLUSDT"]),
        ("cli_agent_01", 2, ["XRPUSDT", "BNBUSDT"]),
    ]
    for index in range(event_target):
        agent_id, number, symbols = agents[index % 2]
        symbol = symbols[(index // 2) % 2]
        market_ref = SourceReference(
            source_id=f"market-{symbol}-{index}",
            source_type="synthetic_market_update",
        )
        store.publish_observation(
            session_id=session.session_id,
            agent_id=agent_id,
            agent_number=number,
            kind="market_regime" if index % 7 == 0 else "peer_observation",
            summary=f"{symbol} synthetic 30-second market update {index}",
            symbol=symbol,
            source_refs=[market_ref],
            idempotency_key=f"benchmark:publication:{index}",
        )
        if index % 55 == 0:
            store.publish_risk_warning(
                session_id=session.session_id,
                agent_id=agent_id,
                agent_number=number,
                summary=f"Synthetic risk warning {index} for {symbol}",
                symbol=symbol,
                source_refs=[market_ref],
                idempotency_key=f"benchmark:risk:{index}",
            )
        if index % 45 == 0:
            store.update_feature_trust(
                session_id=session.session_id,
                agent_id=agent_id,
                agent_number=number,
                feature_name=f"spread_quality:{symbol}",
                trust=0.4 + ((index // 30) % 5) * 0.1,
                reason=f"Synthetic feature review {index}",
                source_refs=[market_ref],
                idempotency_key=f"benchmark:feature:{index}",
            )
        if index % 75 == 0:
            store.write_private_reflection(
                session_id=session.session_id,
                actor_agent_id=agent_id,
                actor_agent_number=number,
                target_agent_id=agent_id,
                kind="reflection",
                summary=f"Private synthetic reflection {index}",
                source_refs=[market_ref],
                idempotency_key=f"benchmark:private:{index}",
            )
        if index % 90 == 0:
            store.append_evidence(
                session_id=session.session_id,
                event_type="AGENT_DECISION_RECORDED",
                category="agent_decision",
                agent_id=agent_id,
                agent_number=number,
                idempotency_key=f"benchmark:decision:{index}",
                source_refs=[market_ref],
                payload={
                    "symbol": symbol,
                    "decision": "observe" if index % 180 else "review_order_intent",
                    "decision_timeframe": "30m",
                },
            )
        if index % 95 == 0:
            store.append_evidence(
                session_id=session.session_id,
                event_type="SUBAGENT_REVIEW_RECORDED",
                category="subagent",
                agent_id=agent_id,
                agent_number=number,
                idempotency_key=f"benchmark:subagent:{index}",
                source_refs=[market_ref],
                payload={"symbol": symbol, "review": f"Synthetic review {index}"},
            )
        if index % 125 == 0:
            store.request_command(
                session_id=session.session_id,
                agent_id=agent_id,
                agent_number=number,
                command_kind="REQUEST_ORDER",
                symbol=symbol,
                rationale=f"Synthetic 30m decision intent {index}",
                intent_ref=f"intent://benchmark/{index}",
                sizing_ref="config://llm_microstructure/execution",
                command_id=f"cmd-benchmark-{index}",
                idempotency_key=f"benchmark:command:{index}",
            )
        if index % 200 == 0:
            for instruction_agent_id, instruction_number, _ in agents:
                store.ack_instructions(
                    session_id=session.session_id,
                    agent_id=instruction_agent_id,
                    agent_number=instruction_number,
                    manifest_version=f"synthetic-manifest-{index // 200}",
                    idempotency_key=f"benchmark:instruction:{instruction_agent_id}:{index}",
                )

    now = datetime.now(timezone.utc).isoformat()
    store.reconcile_portfolio(
        session_id=session.session_id,
        portfolio=PortfolioState(
            total_margin_usage=20.0,
            total_directional_exposure=35.0,
            correlated_exposure=25.0,
            active_positions=[
                {"symbol": "ETHUSDT", "side": "LONG"},
                {"symbol": "BNBUSDT", "side": "SHORT"},
            ],
            active_orders=[],
            global_drawdown_pct=0.8,
            risk_budget_available=80.0,
            emergency_stop=False,
            reconciled_at=now,
        ),
        idempotency_key="benchmark:portfolio:final",
        source_refs=[],
    )

    checkpoint_started = time.perf_counter()
    checkpoint = store.create_checkpoint(session.session_id)
    checkpoint_seconds = time.perf_counter() - checkpoint_started
    events_after_checkpoint = store.list_events(session.session_id)
    critical_ids = {event.event_id for event in events_after_checkpoint if event.critical}
    retained_critical = {
        event.event_id
        for segment in checkpoint.segments
        for event in segment.critical_events
    }

    store._state_path(session.session_id).unlink()
    restarted = CollectiveMemoryStore(
        settings,
        root_dir=work_root,
        config=config,
        session_store=sessions,
    )
    recovery_started = time.perf_counter()
    recovery = restarted.recover_session(session.session_id)
    recovery_seconds = time.perf_counter() - recovery_started
    recovered = restarted.get_state(session.session_id)

    stats = checkpoint.snapshot.compression_statistics
    assert stats is not None
    return {
        "session_id": session.session_id,
        "configured_event_target": event_target,
        "raw_event_count": checkpoint.manifest.raw_event_count,
        "raw_tokens": checkpoint.manifest.raw_tokens,
        "token_count_kind": checkpoint.manifest.token_count_kind,
        "active_context_tokens": checkpoint.manifest.active_context_tokens,
        "active_context_limit": config.memory.active_context_token_limit,
        "within_active_context_limit": (
            checkpoint.manifest.active_context_tokens <= config.memory.active_context_token_limit
        ),
        "checkpoint_bytes": stats.checkpoint_bytes,
        "compression_ratio": stats.compression_ratio,
        "critical_event_count": len(checkpoint.manifest.critical_event_ids),
        "critical_event_retention": set(checkpoint.manifest.critical_event_ids).issubset(retained_critical),
        "source_reference_count": len(checkpoint.manifest.source_references),
        "source_reference_retention": (
            len(checkpoint.manifest.source_references) == checkpoint.manifest.raw_event_count
        ),
        "replay_success": (
            recovery.checkpoint_id == checkpoint.checkpoint_id
            and recovered.last_sequence >= events_after_checkpoint[-1].sequence
        ),
        "checkpoint_seconds": checkpoint_seconds,
        "recovery_seconds": recovery_seconds,
        "pending_commands_recovered": recovery.pending_command_ids,
        "instruction_versions_restored": recovery.instruction_versions_restored,
        "semantic_quality_claimed": False,
        "raw_evidence_path": str(store._events_path(session.session_id)),
        "critical_ids_after_checkpoint_event": len(critical_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=600)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.events < 1:
        parser.error("--events must be positive")
    if args.work_root is None:
        with tempfile.TemporaryDirectory(prefix="p41x-benchmark-") as temp_dir:
            result = run_benchmark(event_target=args.events, work_root=Path(temp_dir))
    else:
        args.work_root.mkdir(parents=True, exist_ok=True)
        result = run_benchmark(event_target=args.events, work_root=args.work_root)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
