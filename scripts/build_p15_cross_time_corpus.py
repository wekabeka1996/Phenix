"""Build current P15 memory and cross-time evidence from validated prior windows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger, ActionReviewV1
from apps.reference.domains.agent_bridge.cross_time import (
    TimeWindowEvidence,
    classify_time_windows,
    cross_time_proof_established,
)
from apps.reference.domains.agent_bridge.scenario_corpus import (
    generate_corpus,
    load_fresh_packet_observations,
)
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore
from apps.reference.domains.agent_bridge.threshold_sensitivity import run_threshold_sensitivity


def _packets(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def _reviews(path: Path) -> list[ActionReviewV1]:
    return [ActionReviewV1.model_validate_json(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--packets", default="reports/agent_control_p15_cross_time_memory/samples/runtime_agent_feed_packets_p15.jsonl")
    parser.add_argument("--output-dir", default="reports/agent_control_p15_cross_time_memory/samples")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    current_path = root / args.packets
    output = root / args.output_dir
    current = load_fresh_packet_observations(current_path)
    if len(current) < 100:
        raise RuntimeError(f"expected at least 100 current packets, got {len(current)}")
    rows = generate_corpus(
        [("current", current_path, 10)], corpus_phase="p15",
        require_fresh_runtime=True, spread_windows=True,
    )
    completed = [row for row in rows if row.revision == 2 and row.outcome_review is not None]
    if len(completed) != 40:
        raise RuntimeError(f"expected 40 current completed reviews, got {len(completed)}")
    p13_packet_path = root / "reports/agent_control_p13_extended_memory_window/samples/runtime_agent_feed_packets_p13.jsonl"
    p14_packet_path = root / "reports/agent_control_p14_multi_session_memory/samples/runtime_agent_feed_packets_p14.jsonl"
    p13_envelopes = _packets(p13_packet_path)
    p14_envelopes = _packets(p14_packet_path)
    p14_groups: dict[str, list[dict]] = defaultdict(list)
    for envelope in p14_envelopes:
        p14_groups[envelope["p14_session_id"]].append(envelope)
    window_specs = [
        TimeWindowEvidence(
            window_id="p13_archived", first_ts_ms=p13_envelopes[0]["packet"]["produced_ts_ms"],
            last_ts_ms=p13_envelopes[-1]["packet"]["produced_ts_ms"], packet_count=len(p13_envelopes), archived=True,
        )
    ]
    for session_id in ("p14s1", "p14s2", "p14s3"):
        group = p14_groups[session_id]
        window_specs.append(TimeWindowEvidence(
            window_id=session_id, first_ts_ms=group[0]["packet"]["produced_ts_ms"],
            last_ts_ms=group[-1]["packet"]["produced_ts_ms"], packet_count=len(group), archived=True,
        ))
    window_specs.append(TimeWindowEvidence(
        window_id="p15_current", first_ts_ms=current[0].produced_ts_ms,
        last_ts_ms=current[-1].produced_ts_ms, packet_count=len(current),
    ))
    classified = classify_time_windows(window_specs)
    if not cross_time_proof_established(classified):
        raise RuntimeError("cross_time_proof_not_established")
    p13_reviews = _reviews(root / "reports/agent_control_p13_extended_memory_window/samples/p13_action_review_corpus_v1.jsonl")
    p14_reviews = _reviews(root / "reports/agent_control_p14_multi_session_memory/samples/p14_action_review_corpus_v1.jsonl")
    completed_by_window: dict[str, list[ActionReviewV1]] = {
        "p13_archived": [row for row in p13_reviews if row.revision == 2],
        "p14s1": [row for row in p14_reviews if row.revision == 2 and row.agent_id.startswith("p14.p14s1.")],
        "p14s2": [row for row in p14_reviews if row.revision == 2 and row.agent_id.startswith("p14.p14s2.")],
        "p14s3": [row for row in p14_reviews if row.revision == 2 and row.agent_id.startswith("p14.p14s3.")],
        "p15_current": completed,
    }
    by_window, by_temporal, by_symbol, by_horizon = {}, defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    class_by_window = {item.window_id: item.temporal_class for item in classified}
    for window_id, review_rows in completed_by_window.items():
        counts: Counter[str] = Counter()
        for row in review_rows:
            outcome = row.outcome_review
            assert outcome is not None
            counts[outcome.realized_scenario] += 1
            by_temporal[class_by_window[window_id]][outcome.realized_scenario] += 1
            by_symbol[row.symbol][outcome.realized_scenario] += 1
            by_horizon[row.horizon][outcome.realized_scenario] += 1
        by_window[window_id] = dict(sorted(counts.items()))
    sensitivity = {
        "schema_version": "threshold-sensitivity/p15",
        "diagnostic_only": True,
        "current": run_threshold_sensitivity(current, window_count=10),
        "prior_refs": [
            "reports/agent_control_p13_extended_memory_window/samples/threshold_sensitivity_p13.json",
            "reports/agent_control_p14_multi_session_memory/samples/threshold_sensitivity_p14.json",
        ],
        "production_heuristics_changed": False,
        "existing_reviews_rewritten": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "threshold_sensitivity_p15.json").write_text(json.dumps(sensitivity, indent=2) + "\n", encoding="utf-8")
    ledger = ActionReviewLedger(root / "ops/agent_bridge/action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    (output / "p15_action_review_corpus_v1.jsonl").write_text(
        "".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8"
    )
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    index = store.build_index(persist=True)
    rebuild_ms = round((time.perf_counter() - started) * 1000, 3)
    (output / "scenario_memory_index_p15_v0.json").write_text(index.model_dump_json(exclude_none=True, indent=2) + "\n", encoding="utf-8")
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
    evidence = {
        "schema_version": "scenario-memory-query-samples/p15",
        "cross_time_proof_established": True,
        "cross_day_proof_established": any(item.temporal_class == "different_day" for item in classified),
        "classified_windows": [item.model_dump(mode="json") for item in classified],
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(completed),
        "appended_revisions": appended,
        "scenario_distribution_by_window": by_window,
        "scenario_distribution_by_temporal_class": {k: dict(sorted(v.items())) for k, v in sorted(by_temporal.items())},
        "scenario_distribution_by_symbol": {k: dict(sorted(v.items())) for k, v in sorted(by_symbol.items())},
        "scenario_distribution_by_horizon": {k: dict(sorted(v.items())) for k, v in sorted(by_horizon.items())},
        "completed_by_provenance": index.completed_by_provenance,
        "completed_by_session": index.completed_by_session,
        "index_completed_count": index.completed_count,
        "index_unresolved_count": index.unresolved_count,
        "rebuild_ms": rebuild_ms,
        "query_latency_ms": latencies,
        "items": queries,
    }
    (output / "scenario_memory_query_results_p15.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
