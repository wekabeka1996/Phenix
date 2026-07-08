"""Build and append the bounded deterministic P11 ActionReview corpus."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger
from apps.reference.domains.agent_bridge.scenario_corpus import generate_corpus
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output", default="reports/agent_control_p11_memory_corpus_expansion/samples/action_review_corpus_v1.jsonl")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    sources = [
        ("p9fresh", root / "reports/agent_control_p9_action_review_ledger/samples/runtime_agent_feed_packets_p9.jsonl", 3),
        ("p10stale", root / "reports/agent_control_p10_scenario_memory_index/samples/runtime_agent_feed_packets_p10.jsonl", 2),
    ]
    rows = generate_corpus(sources)
    if len(rows) != 40:
        raise RuntimeError(f"expected 40 review revisions, got {len(rows)}")
    ledger = ActionReviewLedger(root / "ops" / "agent_bridge" / "action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8")
    store = ScenarioMemoryStore(root)
    index = store.build_index(persist=True)
    sample_dir = output.parent
    (sample_dir / "scenario_memory_index_p11_v0.json").write_text(
        index.model_dump_json(exclude_none=True, indent=2) + "\n", encoding="utf-8"
    )
    completed_query = store.query(query_type="completed", symbol="BTCUSDT", limit=5)
    lessons_query = store.query(query_type="lessons", symbol="ETHUSDT", limit=5)
    confusion_query = store.query(query_type="confusion")
    (sample_dir / "scenario_memory_query_results_p11.json").write_text(
        json.dumps({
            "schema_version": "scenario-memory-query-samples/p11",
            "items": [
                completed_query.model_dump(mode="json", exclude_none=True),
                lessons_query.model_dump(mode="json", exclude_none=True),
                confusion_query.model_dump(mode="json", exclude_none=True),
            ],
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    packet_lines: list[str] = []
    for _, path, _ in sources:
        packet_lines.extend(path.read_text(encoding="utf-8").splitlines())
    (sample_dir / "runtime_agent_feed_packets_p11.jsonl").write_text(
        "\n".join(packet_lines) + "\n", encoding="utf-8"
    )
    realized = Counter(
        row.outcome_review.realized_scenario
        for row in rows
        if row.revision == 2 and row.outcome_review is not None
    )
    print({
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(rows) // 2,
        "appended_revisions": appended,
        "scenario_distribution": dict(sorted(realized.items())),
        "index_review_count": index.review_count,
        "index_completed_count": index.completed_count,
        "index_unresolved_count": index.unresolved_count,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
