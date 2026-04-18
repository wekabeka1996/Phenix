"""Per-cycle expert accuracy helpers for Phase 5 Package 5C."""

from __future__ import annotations

from typing import Sequence

from apps.reference.domains.alpha_search.judge.contracts import ExpertOutput


def compute_expert_accuracy_for_cycle(
    *,
    strategy_id: str,
    symbol: str,
    tf_sec: int,
    bar_close_ts: int,
    expert_outputs: Sequence[ExpertOutput] | None,
    optimal_action: str,
) -> list[dict[str, object]]:
    """Compute deterministic expert-level accuracy records for one cycle."""

    if not expert_outputs:
        return []

    records: list[dict[str, object]] = []
    seen_expert_ids: set[str] = set()
    for expert_output in expert_outputs:
        if expert_output.expert_id in seen_expert_ids:
            continue
        seen_expert_ids.add(expert_output.expert_id)

        expert_action = expert_output.entry_verdict
        evaluated = expert_action in {"OPEN_LONG", "OPEN_SHORT", "NO_ENTRY"}
        is_correct = None
        skip_reason = None
        if evaluated:
            is_correct = expert_action == optimal_action
        else:
            skip_reason = "non_actionable_verdict"

        records.append(
            {
                "expert_id": expert_output.expert_id,
                "expert_version": expert_output.expert_version,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "tf_sec": tf_sec,
                "bar_close_ts": bar_close_ts,
                "expert_action": expert_action,
                "optimal_action": optimal_action,
                "confidence": expert_output.confidence,
                "evaluated": evaluated,
                "is_correct": is_correct,
                "skip_reason": skip_reason,
            }
        )

    return records


def aggregate_expert_accuracy(
    records: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Aggregate basic expert accuracy counts overall and by expert id."""

    by_expert: dict[str, dict[str, object]] = {}
    total_count = 0
    correct_count = 0
    skipped_count = 0

    for record in records:
        expert_id = str(record["expert_id"])
        expert_summary = by_expert.setdefault(
            expert_id,
            {
                "total_count": 0,
                "correct_count": 0,
                "accuracy_rate": None,
                "skipped_count": 0,
            },
        )

        evaluated = bool(record["evaluated"])
        is_correct = record["is_correct"] is True

        if evaluated:
            total_count += 1
            expert_summary["total_count"] = int(
                expert_summary["total_count"]) + 1
            if is_correct:
                correct_count += 1
                expert_summary["correct_count"] = int(
                    expert_summary["correct_count"]) + 1
        else:
            skipped_count += 1
            expert_summary["skipped_count"] = int(
                expert_summary["skipped_count"]) + 1

    accuracy_rate = None
    if total_count:
        accuracy_rate = correct_count / total_count

    for expert_summary in by_expert.values():
        expert_total_count = int(expert_summary["total_count"])
        if expert_total_count:
            expert_summary["accuracy_rate"] = (
                int(expert_summary["correct_count"]) / expert_total_count
            )

    return {
        "total_count": total_count,
        "correct_count": correct_count,
        "accuracy_rate": accuracy_rate,
        "skipped_count": skipped_count,
        "by_expert": by_expert,
    }
