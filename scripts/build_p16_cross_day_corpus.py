"""Build P16 current reviews and explicit different-UTC-date memory evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.action_review import ActionReviewLedger, ActionReviewV1
from apps.reference.domains.agent_bridge.cross_day import classify_cross_day_session
from apps.reference.domains.agent_bridge.scenario_corpus import generate_corpus, load_fresh_packet_observations
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore
from apps.reference.domains.agent_bridge.threshold_sensitivity import run_threshold_sensitivity


def _reviews(path: Path) -> list[ActionReviewV1]:
    return [ActionReviewV1.model_validate_json(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--packets", default="reports/agent_control_p16_cross_day_memory/samples/runtime_agent_feed_packets_p16.jsonl")
    parser.add_argument("--output-dir", default="reports/agent_control_p16_cross_day_memory/samples")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    packet_path = root / args.packets
    output = root / args.output_dir
    current = load_fresh_packet_observations(packet_path)
    if len(current) < 100:
        raise RuntimeError(f"expected at least 100 fresh P16 packets, got {len(current)}")
    p15_evidence = json.loads((
        root / "reports/agent_control_p15_cross_time_memory/samples/scenario_memory_query_results_p15.json"
    ).read_text(encoding="utf-8"))
    prior_windows = p15_evidence["classified_windows"]
    date_evidence = classify_cross_day_session(
        current_first_ts_ms=current[0].produced_ts_ms,
        current_last_ts_ms=current[-1].produced_ts_ms,
        prior_utc_dates=[item["utc_date"] for item in prior_windows],
        prior_last_ts_ms=max(item["last_ts_ms"] for item in prior_windows),
    )
    if not date_evidence.cross_day_proof_established:
        raise RuntimeError("cross_day_proof_not_established")
    source_label = "utc" + date_evidence.current_utc_date.replace("-", "")
    rows = generate_corpus(
        [(source_label, packet_path, 10)], corpus_phase="p16",
        require_fresh_runtime=True, spread_windows=True,
    )
    completed = [row for row in rows if row.revision == 2 and row.outcome_review is not None]
    if len(completed) != 40:
        raise RuntimeError(f"expected 40 completed P16 reviews, got {len(completed)}")
    phase_paths = {
        "p12": root / "reports/agent_control_p12_fresh_runtime_memory/samples/fresh_action_review_corpus_v1.jsonl",
        "p13": root / "reports/agent_control_p13_extended_memory_window/samples/p13_action_review_corpus_v1.jsonl",
        "p14": root / "reports/agent_control_p14_multi_session_memory/samples/p14_action_review_corpus_v1.jsonl",
        "p15": root / "reports/agent_control_p15_cross_time_memory/samples/p15_action_review_corpus_v1.jsonl",
    }
    completed_by_phase = {
        phase: [row for row in _reviews(path) if row.revision == 2]
        for phase, path in phase_paths.items()
    }
    completed_by_phase["p16"] = completed
    by_phase, by_symbol, by_horizon = {}, defaultdict(Counter), defaultdict(Counter)
    lessons: Counter[str] = Counter()
    for phase, phase_rows in completed_by_phase.items():
        counts: Counter[str] = Counter()
        for row in phase_rows:
            outcome = row.outcome_review
            assert outcome is not None
            counts[outcome.realized_scenario] += 1
            by_symbol[row.symbol][outcome.realized_scenario] += 1
            by_horizon[row.horizon][outcome.realized_scenario] += 1
            lessons[outcome.lesson_to_remember] += 1
        by_phase[phase] = dict(sorted(counts.items()))
    sensitivity = {
        "schema_version": "threshold-sensitivity/p16",
        "diagnostic_only": True,
        "current": run_threshold_sensitivity(current, window_count=10),
        "prior_refs": [
            "reports/agent_control_p13_extended_memory_window/samples/threshold_sensitivity_p13.json",
            "reports/agent_control_p14_multi_session_memory/samples/threshold_sensitivity_p14.json",
            "reports/agent_control_p15_cross_time_memory/samples/threshold_sensitivity_p15.json",
        ],
        "production_heuristics_changed": False,
        "existing_reviews_rewritten": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "threshold_sensitivity_p16.json").write_text(json.dumps(sensitivity, indent=2) + "\n", encoding="utf-8")
    ledger = ActionReviewLedger(root / "ops/agent_bridge/action_reviews")
    appended = sum(ledger.append(row) for row in rows)
    (output / "p16_action_review_corpus_v1.jsonl").write_text(
        "".join(row.model_dump_json(exclude_none=True) + "\n" for row in rows), encoding="utf-8"
    )
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    index = store.build_index(persist=True)
    rebuild_ms = round((time.perf_counter() - started) * 1000, 3)
    (output / "scenario_memory_index_p16_v0.json").write_text(index.model_dump_json(exclude_none=True, indent=2) + "\n", encoding="utf-8")
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
        "schema_version": "scenario-memory-query-samples/p16",
        "date_boundary_evidence": date_evidence.model_dump(mode="json"),
        "generated_revisions": len(rows),
        "generated_completed_reviews": len(completed),
        "appended_revisions": appended,
        "scenario_distribution_by_phase": by_phase,
        "scenario_distribution_by_symbol": {key: dict(sorted(value.items())) for key, value in sorted(by_symbol.items())},
        "scenario_distribution_by_horizon": {key: dict(sorted(value.items())) for key, value in sorted(by_horizon.items())},
        "repeated_lessons": dict(lessons.most_common()),
        "completed_by_provenance": index.completed_by_provenance,
        "completed_by_session": index.completed_by_session,
        "index_completed_count": index.completed_count,
        "index_unresolved_count": index.unresolved_count,
        "rebuild_ms": rebuild_ms,
        "query_latency_ms": latencies,
        "items": queries,
    }
    (output / "scenario_memory_query_results_p16.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
