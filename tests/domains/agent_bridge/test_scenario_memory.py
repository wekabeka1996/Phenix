from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.reference.domains.agent_bridge.action_review import (
    ActionReviewLedger,
    finalize_action_review,
    review_ref,
)
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer
from apps.reference.domains.agent_bridge.routes import register_agent_feed_routes
from apps.reference.domains.agent_bridge.scenario_memory import (
    INDEX_REF,
    ScenarioMemoryIndexV0,
    ScenarioMemoryQueryResultV0,
    ScenarioMemoryStore,
    ScenarioMemorySummaryV0,
)


NOW = 1_800_000_000_000


def _data(*, review_id="review_memory_btc_001", packet_id="afp_aaaaaaaa", symbol="BTCUSDT", horizon="next_packet", agent_id="p10.local.fixture"):
    packet_ref = f"agent-feed://packet/{packet_id}"
    return {
        "review_id": review_id,
        "revision": 1,
        "created_ts_ms": NOW,
        "updated_ts_ms": NOW,
        "mode": "no_execution",
        "source": "deterministic_fixture",
        "agent_id": agent_id,
        "packet_ref": packet_ref,
        "symbol": symbol,
        "horizon": horizon,
        "pre_action_note": {
            "review_id": review_id,
            "packet_id": packet_id,
            "symbol": symbol,
            "horizon": horizon,
            "proposed_action": "OBSERVE",
            "thesis": "Observe a bounded packet window without creating execution authority.",
            "invalidation": "The source packet becomes stale or unavailable.",
            "expected_scenarios": [{
                "scenario_id": "no_clear_scenario",
                "confidence": 0.7,
                "thesis": "The short window may remain inconclusive.",
                "evidence_refs": [packet_ref],
            }],
            "data_refs_used": [packet_ref],
            "tool_refs_used": ["agent-memory://deterministic-fixture"],
            "confidence": 0.6,
            "no_execution": True,
        },
        "execution_note": {
            "status": "not_submitted_p9_no_execution",
            "submitted": False,
            "detail": "Memory fixture does not expose an execution route.",
            "no_execution": True,
        },
        "raw_refs": [packet_ref],
        "compact_summary": "Bounded no-model observation memory with no submitted action.",
        "token_estimate": 1,
    }


def _complete(first, *, realized="no_clear_scenario", future=False):
    data = first.model_dump(mode="python")
    data.update({
        "revision": 2,
        "supersedes_ref": review_ref(first.review_id, 1),
        "updated_ts_ms": NOW + 1000,
        "outcome_review": {
            "observed_from_packet_ref": first.packet_ref,
            "observed_to_packet_ref": "agent-feed://packet/afp_bbbbbbbb",
            "observation_window_ms": 1000,
            "what_happened": "The bounded follow-up packet remained inconclusive and no action occurred.",
            "realized_scenario": realized,
            "scenario_confidence": 0.8,
            "evidence_refs": [first.packet_ref, "agent-feed://packet/afp_bbbbbbbb"],
            "expected_result_achieved": realized == "no_clear_scenario",
            "outcome_unexpected": realized != "no_clear_scenario",
            "logical_explanation": "A deterministic taxonomy comparison produced the realized label.",
            "lesson_to_remember": "Keep short-window uncertainty descriptive and separate from trading permission.",
            "future_review_needed": future,
            "no_trade_pnl_claim": True,
        },
        "raw_refs": [first.packet_ref, "agent-feed://packet/afp_bbbbbbbb"],
        "compact_summary": "Completed deterministic review with descriptive scenario memory only.",
        "token_estimate": 1,
    })
    return finalize_action_review(data)


def _store(tmp_path: Path):
    ledger = ActionReviewLedger(tmp_path / "ops" / "agent_bridge" / "action_reviews")
    btc = finalize_action_review(_data())
    ledger.append(btc)
    ledger.append(_complete(btc))
    eth = finalize_action_review(_data(
        review_id="review_memory_eth_001", packet_id="afp_cccccccc", symbol="ETHUSDT", horizon="5m"
    ))
    ledger.append(eth)
    return ScenarioMemoryStore(tmp_path, now_ms_fn=lambda: NOW + 2000), btc, eth


def test_index_selects_latest_revision_and_builds_calibration(tmp_path: Path) -> None:
    store, _, _ = _store(tmp_path)
    index = store.build_index(persist=True)
    assert ScenarioMemoryIndexV0.model_validate(index)
    assert index.review_count == 2
    assert index.completed_count == 1
    assert index.unresolved_count == 1
    assert index.completed_by_provenance == {"archived_or_prior": 1}
    assert index.latest_reviews_by_symbol["BTCUSDT"][0].revision == 2
    assert index.scenario_counts["no_clear_scenario"] == {
        "expected": 2, "realized": 1, "expected_realized": 1
    }
    assert index.expected_realized_matrix["no_clear_scenario"]["no_clear_scenario"] == 1
    assert index.calibration.sample_size_warning is True
    assert index.retention_summary.raw_rows_retained == 3
    assert index.retention_summary.deletion_performed is False
    assert len(index.source_hash) == 64
    assert store.index_path.exists()


def test_index_splits_prior_p12_and_p13_provenance(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    cases = (
        ("review_prior_001", "afp_11111111", "p11.deterministic.corpus"),
        ("review_p12_001", "afp_22222222", "p12.deterministic.fresh-runtime-corpus"),
        ("review_p13_001", "afp_33333333", "p13.deterministic.fresh-runtime-corpus"),
    )
    for review_id, packet_id, agent_id in cases:
        first = finalize_action_review(_data(review_id=review_id, packet_id=packet_id, agent_id=agent_id))
        ledger.append(first)
        ledger.append(_complete(first))
    index = ScenarioMemoryStore(tmp_path).build_index()
    assert index.completed_by_provenance == {
        "archived_or_prior": 1,
        "p12_fresh_runtime": 1,
        "p13_fresh_runtime": 1,
    }


def test_index_counts_p14_sessions_separately(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    for number, session_id in enumerate(("p14s1", "p14s2", "p14s3"), 1):
        first = finalize_action_review(_data(
            review_id=f"review_p14_{number:03d}",
            packet_id=f"afp_{number:08x}",
            agent_id=f"p14.{session_id}.deterministic.multi-session-corpus",
        ))
        ledger.append(first)
        ledger.append(_complete(first))
    index = ScenarioMemoryStore(tmp_path).build_index()
    assert index.completed_by_provenance == {"p14_fresh_runtime": 3}
    assert index.completed_by_session == {"p14s1": 1, "p14s2": 1, "p14s3": 1}


def test_index_counts_p15_cross_time_provenance(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    first = finalize_action_review(_data(
        review_id="review_p15_current_001",
        packet_id="afp_15151515",
        agent_id="p15.current.deterministic.cross-time-corpus",
    ))
    ledger.append(first)
    ledger.append(_complete(first))
    index = ScenarioMemoryStore(tmp_path).build_index()
    assert index.completed_by_provenance == {"p15_fresh_runtime": 1}
    assert index.completed_by_session == {"current": 1}


def test_index_counts_p16_cross_day_provenance(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    first = finalize_action_review(_data(
        review_id="review_p16_utc20260703_001",
        packet_id="afp_16161616",
        agent_id="p16.utc20260703.deterministic.cross-day-corpus",
    ))
    ledger.append(first)
    ledger.append(_complete(first))
    index = ScenarioMemoryStore(tmp_path).build_index()
    assert index.completed_by_provenance == {"p16_fresh_runtime": 1}
    assert index.completed_by_session == {"utc20260703": 1}


def test_read_cache_hits_and_invalidates_after_ledger_append(tmp_path: Path) -> None:
    store, _, _ = _store(tmp_path)
    assert store.query(query_type="completed").result_count == 1
    first_info = store.cache_info()
    assert first_info["latest_cached"] is True
    assert store.query(query_type="completed").result_count == 1
    assert store.cache_info()["hits"] > first_info["hits"]
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    extra = finalize_action_review(_data(
        review_id="review_cache_new_001", packet_id="afp_99999999", symbol="BTCUSDT"
    ))
    ledger.append(extra)
    ledger.append(_complete(extra))
    assert store.query(query_type="completed").result_count == 2
    assert store.cache_info()["misses"] > first_info["misses"]


def test_index_counts_p17_second_window_provenance(tmp_path: Path) -> None:
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    first = finalize_action_review(_data(
        review_id="review_p17_second_001",
        packet_id="afp_17171717",
        agent_id="p17.second_utc20260703.deterministic.second-window-corpus",
    ))
    ledger.append(first)
    ledger.append(_complete(first))
    index = ScenarioMemoryStore(tmp_path).build_index()
    assert index.completed_by_provenance == {"p17_fresh_runtime": 1}
    assert index.completed_by_session == {"second_utc20260703": 1}


def test_reducer_reuses_injected_memory_store_cache(tmp_path: Path) -> None:
    store, _, _ = _store(tmp_path)
    reducer = AgentFeedReducer(
        project_root=tmp_path, now_ms=NOW + 10_000, scenario_memory_store=store
    )
    reducer.build_packet(symbols=["BTCUSDT", "ETHUSDT"])
    first_hits = store.cache_info()["hits"]
    reducer.build_packet(symbols=["BTCUSDT", "ETHUSDT"])
    assert store.cache_info()["hits"] > first_hits


def test_invalid_rows_are_excluded_and_reported(tmp_path: Path) -> None:
    store, _, _ = _store(tmp_path)
    with store.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")
    index = store.build_index()
    assert index.review_count == 2
    assert index.retention_summary.invalid_rows_excluded == 1
    assert index.validation_status == "degraded"
    assert index.validation_errors


def test_required_queries_and_packet_lookup(tmp_path: Path) -> None:
    store, btc, _ = _store(tmp_path)
    assert store.query(query_type="latest", symbol="BTCUSDT").result_count == 1
    assert store.query(query_type="completed").result_count == 1
    unresolved = store.query(query_type="unresolved")
    assert unresolved.result_count == 1 and unresolved.items[0]["symbol"] == "ETHUSDT"
    assert store.query(query_type="lessons", symbol="BTCUSDT").items[0]["lesson"]
    packet = store.query(query_type="packet", packet_id=btc.pre_action_note.packet_id)
    assert packet.items[0]["review_id"] == btc.review_id
    accuracy = store.query(query_type="scenario_accuracy")
    assert accuracy.items[0]["descriptive_only"] is True
    confusion = store.query(query_type="confusion")
    assert "expected_realized_matrix" in confusion.items[0]
    for result in (unresolved, packet, accuracy, confusion):
        assert ScenarioMemoryQueryResultV0.model_validate(result)
        assert result.estimated_tokens <= 1200


def test_token_bounded_summary_and_packet_projection(tmp_path: Path) -> None:
    store, _, _ = _store(tmp_path)
    summary = store.summary(["BTCUSDT", "ETHUSDT"], max_tokens=600)
    assert ScenarioMemorySummaryV0.model_validate(summary)
    assert summary.estimated_tokens <= 600
    assert summary.items[0].latest_lesson
    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW + 3000).build_packet(
        symbols=["BTCUSDT", "ETHUSDT"]
    )
    assert packet.action_review_memory.scenario_memory_index_ref == INDEX_REF
    assert packet.action_review_memory.unresolved_by_symbol == {"BTCUSDT": 0, "ETHUSDT": 1}
    assert packet.budget.estimated_tokens <= 4400


def test_memory_routes_are_get_only_and_validate_params(tmp_path: Path) -> None:
    store, btc, _ = _store(tmp_path)
    store.build_index(persist=True)
    app = FastAPI()
    register_agent_feed_routes(app, project_root=tmp_path)
    client = TestClient(app)
    paths = {route.path: route.methods for route in app.routes if route.path.startswith("/agent-memory/v0")}
    assert set(paths) == {
        "/agent-memory/v0/health", "/agent-memory/v0/index",
        "/agent-memory/v0/query", "/agent-memory/v0/summary",
    }
    assert all(methods == {"GET"} for methods in paths.values())
    assert client.get("/agent-memory/v0/index").status_code == 200
    assert client.get("/agent-memory/v0/query", params={
        "query_type": "packet", "packet_id": btc.pre_action_note.packet_id
    }).status_code == 200
    response = client.get("/agent-memory/v0/summary", params={
        "symbols": "BTCUSDT,ETHUSDT", "max_tokens": 600
    })
    assert response.status_code == 200
    assert response.json()["estimated_tokens"] <= 600
    assert client.get("/agent-memory/v0/query", params={"scenario": "unknown"}).status_code == 422


def test_source_has_no_model_or_execution_client_surface() -> None:
    source = (Path(__file__).resolve().parents[3] / "apps/reference/domains/agent_bridge/scenario_memory.py").read_text().lower()
    for forbidden in (
        "openai", "anthropic", "gemini", "api_key", "api_secret",
        ".create_order(", ".place_order(", ".cancel_order(", ".modify_order(",
        "requests.post", "httpx.post",
    ):
        assert forbidden not in source
