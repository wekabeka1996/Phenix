"""Build the validated P14 multi-session corpus and cross-session evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger
from apps.reference.domains.agent_bridge.scenario_corpus import (
    generate_corpus,
    load_multi_session_packet_observations,
)
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore
from apps.reference.domains.agent_bridge.threshold_sensitivity import run_threshold_sensitivity


SESSION_IDS = ("p14s1", "p14s2", "p14s3")
SESSION_FILES = {"p14s1": "session1.jsonl", "p14s2": "session2.jsonl", "p14s3": "session3.jsonl"}


def _tag_and_combine(root: Path, session_dir: Path, output: Path) -> None:
    lines: list[str] = []
    for session_id in SESSION_IDS:
        path = session_dir / SESSION_FILES[session_id]
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            envelope = json.loads(raw)
            envelope["p14_session_id"] = session_id
            lines.append(json.dumps(envelope, separators=(",", ":")))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--session-dir", default="scratch/p14_runtime")
    parser.add_argument("--output-dir", default="reports/agent_control_p14_multi_session_memory/samples")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    session_dir = root / args.session_dir
    output = root / args.output_dir
    combined = output / "runtime_agent_feed_packets_p14.jsonl"
    _tag_and_combine(root, session_dir, combined)
    sessions = load_multi_session_packet_observations(combined)
    if tuple(sessions) != SESSION_IDS:
        raise RuntimeError(f"unexpected session order: {tuple(sessions)}")
    source_specs = [(session_id, session_dir / SESSION_FILES[session_id], 10) for session_id in SESSION_IDS]
    rows = generate_corpus(
        source_specs, corpus_phase="p14", require_fresh_runtime=True, spread_windows=True
    )
    completed = [row for row in rows if row.revision == 2 and row.outcome_review is not None]
    if len(completed) < 120:
        raise RuntimeError(f"expected at least 120 completed reviews, got {len(completed)}")
    per_session: dict[str, Counter[str]] = {session_id: Counter() for session_id in SESSION_IDS}
    per_symbol: dict[str, Counter[str]] = defaultdict(Counter)
    per_horizon: dict[str, Counter[str]] = defaultdict(Counter)
    matrices: dict[str, dict[str, Counter[str]]] = {
        session_id: defaultdict(Counter) for session_id in SESSION_IDS
    }
    lessons: Counter[str] = Counter()
    for row in completed:
        session_id = next(session for session in SESSION_IDS if f"review_p14_{session}_" in row.review_id)
        outcome = row.outcome_review
        assert outcome is not None
        per_session[session_id][outcome.realized_scenario] += 1
        per_symbol[row.symbol][outcome.realized_scenario] += 1
        per_horizon[row.horizon][outcome.realized_scenario] += 1
        lessons[outcome.lesson_to_remember] += 1
        for expected in row.pre_action_note.expected_scenarios:
            matrices[session_id][expected.scenario_id][outcome.realized_scenario] += 1
    sensitivity_sessions = {
        session_id: run_threshold_sensitivity(observations, window_count=10)
        for session_id, observations in sessions.items()
    }
    sensitivity = {
        "schema_version": "threshold-sensitivity/p14",
        "diagnostic_only": True,
        "sessions": sensitivity_sessions,
        "production_heuristics_changed": False,
        "existing_reviews_rewritten": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "threshold_sensitivity_p14.json").write_text(
        json.dumps(sensitivity, indent=2) + "\n", encoding="utf-8"
    )
    ledger = ActionReviewLedger(root / "ops/agent_bridge/action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    (output / "p14_action_review_corpus_v1.jsonl").write_text(
        "".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8"
    )
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    index = store.build_index(persist=True)
    rebuild_ms = round((time.perf_counter() - started) * 1000, 3)
    (output / "scenario_memory_index_p14_v0.json").write_text(
        index.model_dump_json(exclude_none=True, indent=2) + "\n", encoding="utf-8"
    )
    query_specs = (
        {"query_type": "completed", "symbol": "BTCUSDT", "limit": 5},
        {"query_type": "lessons", "symbol": "ETHUSDT", "limit": 5},
        {"query_type": "confusion"},
        {"query_type": "packet", "packet_id": rows[0].pre_action_note.packet_id},
    )
    queries, latencies = [], []
    for spec in query_specs:
        started = time.perf_counter()
        result = store.query(**spec)
        latencies.append(round((time.perf_counter() - started) * 1000, 3))
        queries.append(result.model_dump(mode="json", exclude_none=True))
    boundaries = {
        session_id: {
            "first_ts_ms": observations[0].produced_ts_ms,
            "last_ts_ms": observations[-1].produced_ts_ms,
            "duration_ms": observations[-1].produced_ts_ms - observations[0].produced_ts_ms,
            "packet_count": len(observations),
        }
        for session_id, observations in sessions.items()
    }
    evidence = {
        "schema_version": "scenario-memory-query-samples/p14",
        "session_boundaries": boundaries,
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(completed),
        "appended_revisions": appended,
        "scenario_distribution_by_session": {k: dict(sorted(v.items())) for k, v in per_session.items()},
        "scenario_distribution_by_symbol": {k: dict(sorted(v.items())) for k, v in sorted(per_symbol.items())},
        "scenario_distribution_by_horizon": {k: dict(sorted(v.items())) for k, v in sorted(per_horizon.items())},
        "expected_realized_by_session": {
            session: {expected: dict(sorted(realized.items())) for expected, realized in sorted(matrix.items())}
            for session, matrix in matrices.items()
        },
        "repeated_lessons": dict(lessons.most_common()),
        "completed_by_provenance": index.completed_by_provenance,
        "completed_by_session": index.completed_by_session,
        "index_completed_count": index.completed_count,
        "index_unresolved_count": index.unresolved_count,
        "rebuild_ms": rebuild_ms,
        "query_latency_ms": latencies,
        "items": queries,
    }
    (output / "scenario_memory_query_results_p14.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
