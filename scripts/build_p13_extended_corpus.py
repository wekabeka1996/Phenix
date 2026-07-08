"""Validate an extended fresh window, append P13 reviews, and build diagnostics."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger
from apps.reference.domains.agent_bridge.scenario_corpus import generate_corpus, load_fresh_packet_observations
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore
from apps.reference.domains.agent_bridge.threshold_sensitivity import run_threshold_sensitivity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--packets", default="reports/agent_control_p13_extended_memory_window/samples/runtime_agent_feed_packets_p13.jsonl")
    parser.add_argument("--output-dir", default="reports/agent_control_p13_extended_memory_window/samples")
    parser.add_argument("--minimum-packets", type=int, default=120)
    parser.add_argument("--windows", type=int, default=15)
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    packet_path = root / args.packets
    output = root / args.output_dir
    observations = load_fresh_packet_observations(packet_path)
    if len(observations) < args.minimum_packets:
        raise RuntimeError(f"expected at least {args.minimum_packets} fresh packets, got {len(observations)}")
    rows = generate_corpus(
        [("extended", packet_path, args.windows)],
        corpus_phase="p13", require_fresh_runtime=True, spread_windows=True,
    )
    completed = [row for row in rows if row.revision == 2 and row.outcome_review is not None]
    if len(completed) < 30:
        raise RuntimeError(f"expected at least 30 completed reviews, got {len(completed)}")
    output.mkdir(parents=True, exist_ok=True)
    sensitivity = run_threshold_sensitivity(observations, window_count=args.windows)
    (output / "threshold_sensitivity_p13.json").write_text(
        json.dumps(sensitivity, indent=2) + "\n", encoding="utf-8"
    )
    ledger = ActionReviewLedger(root / "ops" / "agent_bridge" / "action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    (output / "p13_action_review_corpus_v1.jsonl").write_text(
        "".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8"
    )
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    index = store.build_index(persist=True)
    rebuild_ms = round((time.perf_counter() - started) * 1000, 3)
    (output / "scenario_memory_index_p13_v0.json").write_text(
        index.model_dump_json(exclude_none=True, indent=2) + "\n", encoding="utf-8"
    )
    query_specs = (
        {"query_type": "completed", "symbol": "BTCUSDT", "limit": 5},
        {"query_type": "lessons", "symbol": "ETHUSDT", "limit": 5},
        {"query_type": "confusion"},
        {"query_type": "packet", "packet_id": rows[0].pre_action_note.packet_id},
    )
    queries = []
    latencies = []
    for spec in query_specs:
        started = time.perf_counter()
        result = store.query(**spec)
        latencies.append(round((time.perf_counter() - started) * 1000, 3))
        queries.append(result.model_dump(mode="json", exclude_none=True))
    realized = Counter(row.outcome_review.realized_scenario for row in completed if row.outcome_review)
    evidence = {
        "schema_version": "scenario-memory-query-samples/p13",
        "packet_count": len(observations),
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(completed),
        "appended_revisions": appended,
        "scenario_distribution": dict(sorted(realized.items())),
        "completed_by_provenance": index.completed_by_provenance,
        "index_completed_count": index.completed_count,
        "index_unresolved_count": index.unresolved_count,
        "rebuild_ms": rebuild_ms,
        "query_latency_ms": latencies,
        "items": queries,
    }
    (output / "scenario_memory_query_results_p13.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
