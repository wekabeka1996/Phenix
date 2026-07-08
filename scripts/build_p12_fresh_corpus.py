"""Validate fresh runtime packets, append P12 reviews, and rebuild memory artifacts."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger
from apps.reference.domains.agent_bridge.scenario_corpus import generate_corpus
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--packets", default="reports/agent_control_p12_fresh_runtime_memory/samples/runtime_agent_feed_packets_p12.jsonl")
    parser.add_argument("--output-dir", default="reports/agent_control_p12_fresh_runtime_memory/samples")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    packet_path = root / args.packets
    output = root / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    rows = generate_corpus(
        [("runtime", packet_path, 5)],
        corpus_phase="p12",
        require_fresh_runtime=True,
        spread_windows=True,
    )
    if len(rows) != 40:
        raise RuntimeError(f"expected 40 review revisions, got {len(rows)}")
    ledger = ActionReviewLedger(root / "ops" / "agent_bridge" / "action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    (output / "fresh_action_review_corpus_v1.jsonl").write_text(
        "".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8"
    )
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    index = store.build_index(persist=True)
    rebuild_ms = round((time.perf_counter() - started) * 1000, 3)
    (output / "scenario_memory_index_p12_v0.json").write_text(
        index.model_dump_json(exclude_none=True, indent=2) + "\n", encoding="utf-8"
    )
    queries = []
    query_latencies = []
    for spec in (
        {"query_type": "completed", "symbol": "BTCUSDT", "limit": 5},
        {"query_type": "lessons", "symbol": "ETHUSDT", "limit": 5},
        {"query_type": "confusion"},
        {"query_type": "packet", "packet_id": rows[0].pre_action_note.packet_id},
    ):
        started = time.perf_counter()
        result = store.query(**spec)
        query_latencies.append(round((time.perf_counter() - started) * 1000, 3))
        queries.append(result.model_dump(mode="json", exclude_none=True))
    completed = [row for row in rows if row.revision == 2 and row.outcome_review is not None]
    realized = Counter(row.outcome_review.realized_scenario for row in completed if row.outcome_review)
    evidence = {
        "schema_version": "scenario-memory-query-samples/p12",
        "rebuild_ms": rebuild_ms,
        "query_latency_ms": query_latencies,
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(completed),
        "appended_revisions": appended,
        "scenario_distribution": dict(sorted(realized.items())),
        "completed_by_provenance": index.completed_by_provenance,
        "items": queries,
    }
    (output / "scenario_memory_query_results_p12.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
