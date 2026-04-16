"""
LLM Judge Phase 2+3+4 — Expert Output Bridge (Layer 2: Integration)

Translates AlphaScore → ExpertOutput, handles EVT:JUDGE_EXPERT_PRODUCED_V1
emission, and writes JSONL shadow logs.

Phase 3 addition: write_jsonl_chamber_log() for chamber aggregate logging.
Phase 4 addition: write_jsonl_envelope_log(), write_jsonl_verdict_log().

The bridge is NOT inside the expert modules. Score math stays in experts
(Layer 1); emission, logging, and contract bridging live here (Layer 2).

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md §11.1
           docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md §11.7
           docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §16
"""

import json
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

LOG = logging.getLogger(__name__)


def alpha_score_to_expert_output(
    score: AlphaScore,
    *,
    expert_version: str,
    tf_sec: int,
    ts_ms: Optional[int] = None,
) -> ExpertOutput:
    """Translate an AlphaScore into a Phase 1 ExpertOutput contract.

    Mapping:
      score > 0 with non-zero confidence → OPEN_LONG
      score < 0 with non-zero confidence → OPEN_SHORT
      score == 0 or confidence == 0       → NO_ENTRY  (if reasons don't start with DEFER/NRR)
      reasons start with DEFER/NRR        → UNKNOWN

    This function is deterministic and side-effect-free.
    """
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)

    float_score = float(score.score)
    float_conf = float(score.confidence)

    # Determine entry_verdict from score
    is_unknown = (
        float_conf == 0.0
        and score.why
        and any(
            r.startswith(("DEFER:", "NRR-")) for r in score.why
        )
    )

    if is_unknown:
        entry_verdict = "UNKNOWN"
        signal_direction = "NEUTRAL"
    elif float_score > 0 and float_conf > 0:
        entry_verdict = "OPEN_LONG"
        signal_direction = "LONG"
    elif float_score < 0 and float_conf > 0:
        entry_verdict = "OPEN_SHORT"
        signal_direction = "SHORT"
    else:
        entry_verdict = "NO_ENTRY"
        signal_direction = "NEUTRAL"

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
        reasoning=score.why if score.why else ["no-reasoning"],
        schema_version="1",
    )


def write_jsonl_shadow_log(
    expert_output: ExpertOutput,
    log_dir: str,
) -> None:
    """Append ExpertOutput as one JSONL line to the shadow log file.

    File path: {log_dir}/{expert_id}_{symbol}_{YYYY-MM-DD}.jsonl
    """
    from datetime import datetime, timezone

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{expert_output.expert_id}_{expert_output.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = expert_output.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write shadow log to %s", filepath)


def write_jsonl_chamber_log(
    chamber_aggregate: ChamberAggregate,
    log_dir: str,
) -> None:
    """Append ChamberAggregate as one JSONL line to the chamber shadow log.

    File path: {log_dir}/chamber_{symbol}_{YYYY-MM-DD}.jsonl
    """
    from datetime import datetime, timezone

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"chamber_{chamber_aggregate.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = chamber_aggregate.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write chamber log to %s", filepath)


def write_jsonl_envelope_log(
    envelope: JudgeEvidenceEnvelope,
    log_dir: str,
) -> None:
    """Append JudgeEvidenceEnvelope as one JSONL line to the envelope shadow log.

    File path: {log_dir}/envelope_{symbol}_{YYYY-MM-DD}.jsonl
    """
    from datetime import datetime, timezone

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"envelope_{envelope.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = envelope.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write envelope log to %s", filepath)


def write_jsonl_verdict_log(
    verdict: JudgeVerdict,
    log_dir: str,
) -> None:
    """Append JudgeVerdict as one JSONL line to the verdict shadow log.

    File path: {log_dir}/verdict_{symbol}_{YYYY-MM-DD}.jsonl
    """
    from datetime import datetime, timezone

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"verdict_{verdict.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = verdict.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write verdict log to %s", filepath)
