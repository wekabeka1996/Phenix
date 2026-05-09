"""Phase 9.0: Determinism foundation for close-submission contour replay.

This module provides helpers to prove that the same CMD:CLOSE input,
when processed by the close-submission contour, always produces the same
DEC:CLOSE and CloseSubmissionPayload outputs.

Non-goals:
- Authority transfer
- State mutation
- Time-dependent logic
- Hidden fallback synthesis

Goal:
Prove determinism by showing that bridge derivation and submission derivation
are pure functions with no side effects and no time-sensitive logic.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Dict, Optional

from apps.reference.domains.execution_position.flows.close.close_producer_bridge import (
    CloseProducerBridgeError,
    DecCloseBridgePayload,
    adapt_cmd_close_to_dec_close,
)
from apps.reference.domains.execution_position.flows.close.close_submission_adapter import (
    CloseSubmissionAdapterError,
    CloseSubmissionPayload,
)
from vfoundation.core.protocol import Message


def normalize_for_hash(value: Any) -> Any:
    """Normalize a value for hashing (determinism check).

    Goal: convert Pydantic models, decimals, and other types to
    JSON-serializable form for stable hashing.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): normalize_for_hash(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [normalize_for_hash(v) for v in value]
    if hasattr(value, 'model_dump'):
        try:
            return normalize_for_hash(value.model_dump())
        except Exception:
            pass
    if hasattr(value, '__dict__'):
        try:
            return normalize_for_hash(value.__dict__)
        except Exception:
            pass
    return str(value)


def hash_normalized(value: Any) -> str:
    """Hash a normalized value for determinism proof.

    Returns:
        Hex string of SHA256 hash
    """
    normalized = normalize_for_hash(value)
    serialized = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def deterministic_close_bridge(
    cmd_close_msg: Message,
) -> tuple[Optional[DecCloseBridgePayload], Optional[str]]:
    """Deterministically derive DEC:CLOSE from CMD:CLOSE.

    Args:
        cmd_close_msg: Incoming CMD:CLOSE message

    Returns:
        (DecCloseBridgePayload or None, error_reason or None)

    Semantics:
        - Success: returns (payload, None)
        - Failure: returns (None, reason_string)
        - No hidden fallback; explicit error on invalid input

    Proof of determinism:
        Same input message always produces same output (or same error).
    """
    try:
        intake, emission, result = adapt_cmd_close_to_dec_close(cmd_close_msg)
        return emission, None
    except CloseProducerBridgeError as exc:
        return None, str(exc)


def deterministic_close_submission(
    dec_close_payload: Dict[str, Any],
    position_amt: Decimal,
    requested_qty: Optional[Decimal] = None,
    idempotent_key: Optional[str] = None,
    symbol: Optional[str] = None,
) -> tuple[Optional[CloseSubmissionPayload], Optional[str]]:
    """Deterministically derive CloseSubmissionPayload from DEC:CLOSE.

    Args:
        dec_close_payload: Payload dict from DEC:CLOSE message
        position_amt: Accepted position amount (snapshot at request time)
        requested_qty: Partial close quantity if requested
        idempotent_key: Idempotent key (normalized from payload if not provided)
        symbol: Symbol (extracted from payload if not provided)

    Returns:
        (CloseSubmissionPayload or None, error_reason or None)

    Semantics:
        - Success: returns (payload, None)
        - Failure: returns (None, reason_string)
        - No hidden fallback or guessing
        - position_amt accepted as-given (do NOT replay position changes)

    Proof of determinism:
        Same inputs always produce same output (or same error).
    """
    sym = symbol or (dec_close_payload.get('symbol')
                     if isinstance(dec_close_payload, dict) else None)
    idem_key = idempotent_key or (dec_close_payload.get(
        'idempotent_key') if isinstance(dec_close_payload, dict) else None)

    try:
        payload = CloseSubmissionPayload.from_dec_close(
            symbol=sym,
            position_amt=position_amt,
            requested_qty=requested_qty,
            idempotent_key=idem_key,
        )
        return payload, None
    except CloseSubmissionAdapterError as exc:
        return None, str(exc)


class DeterminismProof:
    """Container for determinism test results."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.runs: list[Dict[str, Any]] = []
        self.all_match = True

    def add_run(self, run_id: int, input_hash: str, output_hash: str, error: Optional[str] = None):
        """Record a determinism run."""
        self.runs.append({
            'run_id': run_id,
            'input_hash': input_hash,
            'output_hash': output_hash,
            'error': error,
        })
        if len(self.runs) > 1:
            prev_run = self.runs[-2]
            if prev_run['output_hash'] != output_hash or prev_run['error'] != error:
                self.all_match = False

    def verdict(self) -> str:
        """Return determinism verdict."""
        if not self.runs:
            return "NO_RUNS"
        if self.all_match:
            return "PROVEN_DETERMINISTIC"
        return "INDETERMINATE_NONDETERMINISTIC"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize proof to dict."""
        return {
            'test_name': self.test_name,
            'run_count': len(self.runs),
            'verdict': self.verdict(),
            'all_match': self.all_match,
            'runs': self.runs,
        }
