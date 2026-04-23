"""
LLM Judge expert output bridge.

Translates AlphaScore -> ExpertOutput, handles shadow-log writes, and keeps
structured verdict fields authoritative over free-text reasoning.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from apps.reference.domains.alpha_search.alpha_model import AlphaScore
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
)
from apps.reference.domains.alpha_search.judge.identity import utc_day_from_ts_ms

LOG = logging.getLogger(__name__)

_ENTRY_DECISION_TOKENS = (
    "OPEN_LONG",
    "OPEN_SHORT",
    "NO_ENTRY",
    "SUPPRESS",
    "UNKNOWN",
)


def _is_unknown_reason(reasoning: list[str]) -> bool:
    return any(str(item).startswith(("DEFER:", "NRR-")) for item in reasoning)


def _signal_direction_for_entry_verdict(entry_verdict: str) -> str:
    if entry_verdict == "OPEN_LONG":
        return "LONG"
    if entry_verdict == "OPEN_SHORT":
        return "SHORT"
    return "NEUTRAL"


def _contains_decision_token(line: str) -> bool:
    upper_line = str(line).upper()
    return any(token in upper_line for token in _ENTRY_DECISION_TOKENS)


def _build_reasoning_summary(
    *,
    entry_verdict: str,
    score: float,
    confidence: float,
    signal_threshold: float,
) -> str:
    return (
        f"authoritative_entry_verdict:{entry_verdict} "
        f"score={score:.4f} threshold={signal_threshold:.4f} "
        f"confidence={confidence:.4f}"
    )


def _normalize_reasoning(
    *,
    reasoning: list[str],
    entry_verdict: str,
    score: float,
    confidence: float,
    signal_threshold: float,
) -> list[str]:
    summary = _build_reasoning_summary(
        entry_verdict=entry_verdict,
        score=score,
        confidence=confidence,
        signal_threshold=signal_threshold,
    )
    preserved = [
        str(line)
        for line in reasoning
        if line and not _contains_decision_token(str(line))
    ]
    return [summary, *preserved] if preserved else [summary]


def _has_conflicting_decision_tokens(
    reasoning: list[str],
    *,
    authoritative_verdict: str,
) -> bool:
    authoritative_token = authoritative_verdict.upper()
    for line in reasoning[1:]:
        upper_line = str(line).upper()
        for token in _ENTRY_DECISION_TOKENS:
            if token == authoritative_token:
                continue
            if token in upper_line:
                return True
    return False


def alpha_score_to_expert_output(
    score: AlphaScore,
    *,
    expert_version: str,
    signal_threshold: float,
    tf_sec: int,
    ts_ms: Optional[int] = None,
) -> ExpertOutput:
    """Translate one AlphaScore into an entry-side ExpertOutput contract."""
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)

    float_score = float(score.score)
    float_conf = float(score.confidence)
    threshold = float(signal_threshold)
    if threshold <= 0.0:
        raise ValueError("signal_threshold must be > 0")

    raw_reasoning = [str(line) for line in (score.why or ["no-reasoning"])]

    if _is_unknown_reason(raw_reasoning):
        entry_verdict = "UNKNOWN"
    elif float_score > threshold:
        entry_verdict = "OPEN_LONG"
    elif float_score < -threshold:
        entry_verdict = "OPEN_SHORT"
    else:
        entry_verdict = "NO_ENTRY"

    signal_direction = _signal_direction_for_entry_verdict(entry_verdict)
    normalized_reasoning = _normalize_reasoning(
        reasoning=raw_reasoning,
        entry_verdict=entry_verdict,
        score=float_score,
        confidence=float_conf,
        signal_threshold=threshold,
    )

    if _has_conflicting_decision_tokens(
        normalized_reasoning,
        authoritative_verdict=entry_verdict,
    ):
        entry_verdict = "UNKNOWN"
        signal_direction = "NEUTRAL"
        normalized_reasoning = _normalize_reasoning(
            reasoning=raw_reasoning
            + ["normalization_failed:contradictory_decision_tokens"],
            entry_verdict=entry_verdict,
            score=float_score,
            confidence=float_conf,
            signal_threshold=threshold,
        )

    return ExpertOutput(
        expert_id=score.model_name,
        expert_version=expert_version,
        symbol=score.symbol,
        tf_sec=tf_sec,
        ts_ms=ts_ms,
        entry_verdict=entry_verdict,
        lifecycle_verdict=None,
        confidence=float_conf,
        signal_direction=signal_direction,
        reasoning=normalized_reasoning,
        schema_version="1",
    )


def write_jsonl_shadow_log(
    expert_output: ExpertOutput,
    log_dir: str,
) -> None:
    """Append ExpertOutput as one JSONL line to the shadow log file."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = utc_day_from_ts_ms(expert_output.ts_ms)
    filename = f"{expert_output.expert_id}_{expert_output.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = expert_output.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write shadow log to %s", filepath)


def write_jsonl_chamber_log(
    chamber_aggregate: ChamberAggregate,
    log_dir: str,
) -> None:
    """Append ChamberAggregate as one JSONL line to the chamber shadow log."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = utc_day_from_ts_ms(chamber_aggregate.ts_ms)
    filename = f"chamber_{chamber_aggregate.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = chamber_aggregate.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write chamber log to %s", filepath)


def write_jsonl_envelope_log(
    envelope: JudgeEvidenceEnvelope,
    log_dir: str,
) -> None:
    """Append JudgeEvidenceEnvelope as one JSONL line to the envelope log."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = utc_day_from_ts_ms(envelope.ts_ms)
    filename = f"envelope_{envelope.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = envelope.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write envelope log to %s", filepath)


def write_jsonl_verdict_log(
    verdict: JudgeVerdict,
    log_dir: str,
) -> None:
    """Append JudgeVerdict as one JSONL line to the verdict shadow log."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = utc_day_from_ts_ms(verdict.ts_ms)
    filename = f"verdict_{verdict.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = verdict.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write verdict log to %s", filepath)
