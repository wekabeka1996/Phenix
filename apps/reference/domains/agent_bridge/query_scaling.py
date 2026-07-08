"""Read-only component and cold/warm profiling for ScenarioMemory queries."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import statistics
import time
from typing import Any

from .action_review import ActionReviewV1, lint_action_review
from .scenario_memory import ScenarioMemoryIndexV0, ScenarioMemoryStore, _compact


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def profile_query_scaling(project_root: Path, *, packet_id: str, iterations: int = 3) -> dict[str, Any]:
    if not 1 <= iterations <= 20:
        raise ValueError("iterations must be between 1 and 20")
    root = Path(project_root).resolve()
    store = ScenarioMemoryStore(root)
    started = time.perf_counter()
    raw = store.ledger_path.read_bytes()
    file_io_ms = _elapsed_ms(started)
    started = time.perf_counter()
    parsed = []
    for line in raw.splitlines():
        row = ActionReviewV1.model_validate_json(line)
        errors = lint_action_review(row)
        if errors:
            raise ValueError(";".join(errors))
        parsed.append(row)
    ledger_parse_ms = _elapsed_ms(started)
    started = time.perf_counter()
    latest: dict[str, ActionReviewV1] = {}
    for row in parsed:
        current = latest.get(row.review_id)
        if current is None or row.revision > current.revision:
            latest[row.review_id] = row
    latest_rows = sorted(latest.values(), key=lambda row: (row.updated_ts_ms, row.review_id), reverse=True)
    latest_selection_ms = _elapsed_ms(started)
    started = time.perf_counter()
    index = ScenarioMemoryIndexV0.model_validate_json(store.index_path.read_bytes())
    index_load_ms = _elapsed_ms(started)
    started = time.perf_counter()
    filtered = [row for row in latest_rows if row.symbol == "BTCUSDT" and row.outcome_review is not None][:5]
    query_filtering_ms = _elapsed_ms(started)
    started = time.perf_counter()
    json.dumps([_compact(row).model_dump(mode="json", exclude_none=True) for row in filtered], separators=(",", ":"))
    response_serialization_ms = _elapsed_ms(started)
    specs = (
        {"query_type": "completed", "symbol": "BTCUSDT", "limit": 5},
        {"query_type": "lessons", "symbol": "ETHUSDT", "limit": 5},
        {"query_type": "confusion"},
        {"query_type": "packet", "packet_id": packet_id},
    )
    cold: dict[str, float] = {}
    for spec in specs:
        cold_store = ScenarioMemoryStore(root)
        started = time.perf_counter()
        cold_store.query(**spec)
        cold[str(spec["query_type"])] = _elapsed_ms(started)
    warm_store = ScenarioMemoryStore(root)
    for spec in specs:
        warm_store.query(**spec)
    warm_samples: dict[str, list[float]] = defaultdict(list)
    for _ in range(iterations):
        for spec in specs:
            started = time.perf_counter()
            warm_store.query(**spec)
            warm_samples[str(spec["query_type"])].append(_elapsed_ms(started))
    warm = {key: round(statistics.mean(values), 3) for key, values in warm_samples.items()}
    return {
        "schema_version": "scenario-memory-query-scaling/p17",
        "read_only": True,
        "ledger_bytes": len(raw),
        "raw_rows": len(parsed),
        "latest_rows": len(latest_rows),
        "persisted_index_source_hash": index.source_hash,
        "components_ms": {
            "file_io": file_io_ms,
            "ledger_parse_validation": ledger_parse_ms,
            "latest_revision_selection": latest_selection_ms,
            "persisted_index_load_validation": index_load_ms,
            "query_filtering": query_filtering_ms,
            "response_serialization": response_serialization_ms,
        },
        "cold_query_ms": cold,
        "warm_query_mean_ms": warm,
        "warm_iterations": iterations,
        "cache_info": warm_store.cache_info(),
        "raw_ledger_mutated": False,
    }


__all__ = ["profile_query_scaling"]
