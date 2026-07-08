from __future__ import annotations

import json
from pathlib import Path

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger, lint_action_review
from apps.reference.domains.agent_bridge.scenario_corpus import (
    PacketObservation,
    build_review_pair,
    classify_scenario,
    classify_scenario_with_thresholds,
    generate_corpus,
    load_fresh_packet_observations,
    load_multi_session_packet_observations,
)
from apps.reference.domains.agent_bridge.threshold_sensitivity import run_threshold_sensitivity
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore
from apps.reference.domains.agent_bridge.reducer import AgentFeedReducer


NOW = 1_800_000_000_000


def _packet(packet_id: str, *, price=100.0, volatility=1.0, fresh=8, stale=0):
    return PacketObservation(
        packet_id=packet_id,
        produced_ts_ms=NOW + int(packet_id[-2:], 16),
        source_ref=f"fixture://{packet_id}",
        payload={
            "packet_id": packet_id,
            "produced_ts_ms": NOW,
            "freshness_summary": {"fresh": fresh, "stale": stale, "missing": 0, "unknown": 0},
            "symbol_markets": [{"symbol": "BTCUSDT", "close_price": price}, {"symbol": "ETHUSDT", "close_price": price}],
            "feature_signals": [{"symbol": "BTCUSDT", "volatility": volatility}, {"symbol": "ETHUSDT", "volatility": volatility}],
        },
    )


def test_deterministic_scenario_heuristics() -> None:
    base = _packet("afp_00000001")
    assert classify_scenario(base, _packet("afp_00000002", stale=8, fresh=0), symbol="BTCUSDT", horizon="micro_observation")[0] == "data_stale_or_missing"
    assert classify_scenario(base, _packet("afp_00000003", price=100.2), symbol="BTCUSDT", horizon="micro_observation")[0] == "continuation"
    assert classify_scenario(base, _packet("afp_00000004", volatility=1.3), symbol="BTCUSDT", horizon="micro_observation")[0] == "volatility_expansion"
    assert classify_scenario(base, _packet("afp_00000005", volatility=0.7), symbol="BTCUSDT", horizon="micro_observation")[0] == "volatility_compression"
    assert classify_scenario(base, _packet("afp_00000006", price=100.01), symbol="BTCUSDT", horizon="micro_observation")[0] == "no_clear_scenario"


def test_threshold_sensitivity_is_offline_and_does_not_change_baseline() -> None:
    base = _packet("afp_00000001")
    directional = _packet("afp_00000002", price=100.045)
    assert classify_scenario(base, directional, symbol="BTCUSDT", horizon="micro_observation")[0] == "no_clear_scenario"
    assert classify_scenario_with_thresholds(
        base, directional, symbol="BTCUSDT", horizon="micro_observation",
        directional_scale=0.75, volatility_threshold=0.25,
    )[0] == "continuation"
    volatility = _packet("afp_00000003", volatility=1.22)
    assert classify_scenario_with_thresholds(
        base, volatility, symbol="BTCUSDT", horizon="micro_observation",
        directional_scale=1.0, volatility_threshold=0.20,
    )[0] == "volatility_expansion"
    diagnostic = run_threshold_sensitivity([base, directional, volatility, directional], window_count=2)
    assert diagnostic["diagnostic_only"] is True
    assert diagnostic["production_heuristics_changed"] is False
    assert set(diagnostic["distributions"]) == {
        "p12_baseline", "directional_lower", "directional_higher",
        "volatility_lower", "volatility_higher",
    }


def test_review_pair_is_packet_linked_no_model_and_no_execution() -> None:
    first, second = build_review_pair(
        _packet("afp_00000011"), _packet("afp_00000012", price=100.2),
        symbol="BTCUSDT", horizon="micro_observation", sequence=1, source_label="test",
    )
    assert first.model_id is None and second.model_call_ref is None
    assert first.execution_note.submitted is False
    assert second.outcome_review is not None and second.outcome_review.no_trade_pnl_claim is True
    assert second.outcome_review.observed_from_packet_ref == first.packet_ref
    assert second.revision == 2 and second.supersedes_ref
    assert lint_action_review(first) == [] and lint_action_review(second) == []


def _write_packets(path: Path, count: int, *, stale: bool) -> None:
    rows = []
    for index in range(count):
        packet = _packet(f"afp_{index + 1:08x}", stale=8 if stale else 0, fresh=0 if stale else 8).payload
        packet["produced_ts_ms"] = NOW + index * 1000
        rows.append(json.dumps({"packet": packet}))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_fresh_runtime_packets(path: Path, count: int) -> None:
    rows = []
    for index in range(count):
        packet = _packet(f"afp_{index + 1:08x}").payload
        packet.update({
            "read_only": True,
            "produced_ts_ms": NOW + index * 1000,
            "execution_body": {
                "meta": {"freshness": "fresh", "source_ownership": "direct_main_publication"},
                "invariants": [{"name": "no_order_execution_isolation", "status": "ready"}],
            },
        })
        for market in packet["symbol_markets"]:
            market["meta"] = {"freshness": "fresh", "source_ownership": "direct_main_publication"}
        rows.append(json.dumps({"packet": packet}))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_fresh_loader_requires_direct_main_and_no_order_guard(tmp_path: Path) -> None:
    source = tmp_path / "fresh-runtime.jsonl"
    _write_fresh_runtime_packets(source, 4)
    assert len(load_fresh_packet_observations(source)) == 4
    payload = json.loads(source.read_text(encoding="utf-8").splitlines()[0])
    payload["packet"]["execution_body"]["invariants"][0]["status"] = "missing"
    source.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    try:
        load_fresh_packet_observations(source)
    except ValueError as exc:
        assert "no-order isolation" in str(exc)
    else:
        raise AssertionError("unsafe fresh-runtime packet was accepted")


def test_p12_spread_corpus_uses_full_fresh_window_and_phase_identity(tmp_path: Path) -> None:
    source = tmp_path / "fresh-runtime.jsonl"
    _write_fresh_runtime_packets(source, 40)
    rows = generate_corpus(
        [("fresh", source, 5)], corpus_phase="p12", require_fresh_runtime=True, spread_windows=True
    )
    assert len(rows) == 40
    completed = [row for row in rows if row.revision == 2]
    assert all(row.review_id.startswith("review_p12_") for row in completed)
    assert all(row.agent_id == "p12.deterministic.fresh-runtime-corpus" for row in completed)
    assert max(row.outcome_review.observation_window_ms for row in completed if row.outcome_review) == 7000


def test_multi_session_loader_requires_boundaries_and_unique_packets(tmp_path: Path) -> None:
    target = tmp_path / "sessions.jsonl"
    tagged = []
    for session_index, session_id in enumerate(("p14s1", "p14s2", "p14s3")):
        source = tmp_path / f"{session_id}.jsonl"
        _write_fresh_runtime_packets(source, 4)
        for packet_index, line in enumerate(source.read_text(encoding="utf-8").splitlines()):
            envelope = json.loads(line)
            packet = envelope["packet"]
            packet["packet_id"] = f"afp_{session_index + 1:02x}{packet_index + 1:06x}"
            packet["produced_ts_ms"] = NOW + session_index * 100_000 + packet_index * 1000
            envelope["p14_session_id"] = session_id
            tagged.append(json.dumps(envelope))
    target.write_text("\n".join(tagged) + "\n", encoding="utf-8")
    sessions = load_multi_session_packet_observations(
        target, minimum_sessions=3, minimum_packets_per_session=4
    )
    assert list(sessions) == ["p14s1", "p14s2", "p14s3"]
    assert all(len(rows) == 4 for rows in sessions.values())
    bad = json.loads(tagged[4])
    bad["packet"]["packet_id"] = json.loads(tagged[0])["packet"]["packet_id"]
    lines = tagged.copy()
    lines[4] = json.dumps(bad)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        load_multi_session_packet_observations(target, minimum_sessions=3, minimum_packets_per_session=4)
    except ValueError as exc:
        assert "reused across sessions" in str(exc)
    else:
        raise AssertionError("cross-session packet reuse was accepted")


def test_bounded_corpus_reaches_20_completed_reviews_and_rebuilds_index(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh.jsonl"
    stale = tmp_path / "stale.jsonl"
    _write_packets(fresh, 6, stale=False)
    _write_packets(stale, 4, stale=True)
    rows = generate_corpus([("fresh", fresh, 3), ("stale", stale, 2)])
    assert len(rows) == 40
    completed = [row for row in rows if row.revision == 2]
    assert len(completed) == 20
    assert {row.symbol for row in completed} == {"BTCUSDT", "ETHUSDT"}
    assert {row.horizon for row in completed} == {"micro_observation", "scalp_observation"}
    ledger = ActionReviewLedger(tmp_path / "ops/agent_bridge/action_reviews")
    assert sum(ledger.append(row) for row in rows) == 40
    assert sum(ledger.append(row) for row in rows) == 0
    index = ScenarioMemoryStore(tmp_path).build_index(persist=True)
    assert index.review_count == 20
    assert index.completed_count == 20
    assert index.unresolved_count == 0
    assert index.calibration.completed_by_symbol == {"BTCUSDT": 10, "ETHUSDT": 10}
    assert index.calibration.completed_by_horizon == {"micro_observation": 10, "scalp_observation": 10}
    packet = AgentFeedReducer(project_root=tmp_path, now_ms=NOW + 10_000).build_packet(
        symbols=["BTCUSDT", "ETHUSDT"]
    )
    assert len(packet.action_review_memory.latest_scenario_memory) == 1
    assert packet.budget.estimated_tokens <= 4_400
    assert packet.budget.truncated is False


def test_generator_source_has_no_model_or_execution_clients() -> None:
    source = (Path(__file__).resolve().parents[3] / "apps/reference/domains/agent_bridge/scenario_corpus.py").read_text().lower()
    for forbidden in (
        "openai", "anthropic", "gemini", "api_key", "api_secret",
        ".create_order(", ".place_order(", ".cancel_order(", ".modify_order(",
    ):
        assert forbidden not in source
