"""Build P17 second-window reviews, index, queries, and read-only scaling profile."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger, ActionReviewV1
from apps.reference.domains.agent_bridge.query_scaling import profile_query_scaling
from apps.reference.domains.agent_bridge.scenario_corpus import generate_corpus, load_fresh_packet_observations
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore


def _completed(path: Path) -> list[ActionReviewV1]:
    return [
        row for row in (ActionReviewV1.model_validate_json(line) for line in path.read_text(encoding="utf-8-sig").splitlines())
        if row.revision == 2
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--packets", default="reports/agent_control_p17_second_cross_day_and_query_scaling/samples/runtime_agent_feed_packets_p17.jsonl")
    parser.add_argument("--output-dir", default="reports/agent_control_p17_second_cross_day_and_query_scaling/samples")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    packet_path = root / args.packets
    output = root / args.output_dir
    observations = load_fresh_packet_observations(packet_path)
    if len(observations) < 100:
        raise RuntimeError(f"expected at least 100 fresh packets, got {len(observations)}")
    rows = generate_corpus(
        [("second_utc20260703", packet_path, 10)], corpus_phase="p17",
        require_fresh_runtime=True, spread_windows=True,
    )
    completed = [row for row in rows if row.revision == 2 and row.outcome_review is not None]
    if len(completed) != 40:
        raise RuntimeError(f"expected 40 completed P17 reviews, got {len(completed)}")
    phase_paths = {
        "p12": root / "reports/agent_control_p12_fresh_runtime_memory/samples/fresh_action_review_corpus_v1.jsonl",
        "p13": root / "reports/agent_control_p13_extended_memory_window/samples/p13_action_review_corpus_v1.jsonl",
        "p14": root / "reports/agent_control_p14_multi_session_memory/samples/p14_action_review_corpus_v1.jsonl",
        "p15": root / "reports/agent_control_p15_cross_time_memory/samples/p15_action_review_corpus_v1.jsonl",
        "p16": root / "reports/agent_control_p16_cross_day_memory/samples/p16_action_review_corpus_v1.jsonl",
    }
    distributions = {
        phase: dict(sorted(Counter(
            row.outcome_review.realized_scenario for row in _completed(path) if row.outcome_review
        ).items()))
        for phase, path in phase_paths.items()
    }
    distributions["p17"] = dict(sorted(Counter(
        row.outcome_review.realized_scenario for row in completed if row.outcome_review
    ).items()))
    output.mkdir(parents=True, exist_ok=True)
    ledger = ActionReviewLedger(root / "ops" / "agent_bridge" / "action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    (output / "p17_action_review_corpus_v1.jsonl").write_text(
        "".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8"
    )
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    index = store.build_index(persist=True)
    rebuild_ms = round((time.perf_counter() - started) * 1000, 3)
    (output / "scenario_memory_index_p17_v0.json").write_text(
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
    scaling = profile_query_scaling(root, packet_id=rows[0].pre_action_note.packet_id, iterations=5)
    (output / "query_scaling_profile_p17.json").write_text(json.dumps(scaling, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "schema_version": "scenario-memory-query-samples/p17",
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(completed),
        "appended_revisions": appended,
        "scenario_distribution_by_phase": distributions,
        "completed_by_provenance": index.completed_by_provenance,
        "completed_by_session": index.completed_by_session,
        "index_completed_count": index.completed_count,
        "index_unresolved_count": index.unresolved_count,
        "rebuild_ms": rebuild_ms,
        "optimized_query_latency_ms": latencies,
        "cache_info": store.cache_info(),
        "items": queries,
    }
    (output / "scenario_memory_query_results_p17.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
