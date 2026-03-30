from __future__ import annotations

import logging
import os
from typing import Any, Optional

from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal

from .normalized_reject_reasons import NormalizedRejectReasons

logger = logging.getLogger(__name__)


CANONICAL_INTENT_DEFERRED_REASON_CODES = {
    "NRR-DATA-NOT-READY",
    "NRR-PORTFOLIO-UNKNOWN",
    "NRR-PORTFOLIO-STALE",
    "NRR-RISK-STALE",
    "NRR-RISK-SKEW-UNTIL-REFRESH",
    "FLIP_CLOSE_PENDING",
    "NRR-FLIP-CLOSE-QTY-INVALID",
    "NRR-ORDER-IN-FLIGHT",
    "NRR-ORDER-INDEX-FAIL",
    "QOS_BLOCKED",
    "COOLDOWN",
    "REGIME_BLOCKED",
}


def canonicalize_intent_deferred_reason(raw_reason: str) -> tuple[str, str, Optional[str]]:
    raw_clean = str(raw_reason or "").strip()
    if not raw_clean:
        raise ValueError("INTENT_DEFERRED reason is required")

    raw_upper = raw_clean.upper()
    explicit_map = {
        "NRR-DATA-NOT-READY": ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        NormalizedRejectReasons.DATA_NOT_READY: ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        "RISK_SCORE_MISSING": ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        "RISK_SCORE_INVALID": ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        # Aurora quadratic kernel anomaly/fail-closed reasons.
        "PILLAR_WARMUP": ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        "LINEAR_SCORE_INVALID": ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        "LINEAR_SCORE_NAN_INF": ("NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY"),
        "NRR-PORTFOLIO-UNKNOWN": ("NRR-PORTFOLIO-UNKNOWN", "NRR-PORTFOLIO-UNKNOWN"),
        "NRR-PORTFOLIO-STALE": ("NRR-PORTFOLIO-STALE", "NRR-PORTFOLIO-STALE"),
        "NRR-RISK-STALE": ("NRR-RISK-STALE", "NRR-RISK-STALE"),
        "NRR-RISK-SKEW-UNTIL-REFRESH": ("NRR-RISK-SKEW-UNTIL-REFRESH", "NRR-RISK-SKEW-UNTIL-REFRESH"),
        "FLIP_CLOSE_PENDING": ("FLIP_CLOSE_PENDING", "FLIP_CLOSE_PENDING"),
        "NRR-FLIP-CLOSE-QTY-INVALID": ("NRR-FLIP-CLOSE-QTY-INVALID", "NRR-FLIP-CLOSE-QTY-INVALID"),
        "NRR-ORDER-IN-FLIGHT": ("NRR-ORDER-IN-FLIGHT", "NRR-ORDER-IN-FLIGHT"),
        "NRR-ORDER-INDEX-FAIL": ("NRR-ORDER-INDEX-FAIL", "NRR-ORDER-INDEX-FAIL"),
        "QOS_BLOCKED": ("QOS_BLOCKED", "QOS_BLOCKED"),
        "RATE_LIMIT_EXCEEDED": ("QOS_BLOCKED", "QOS_BLOCKED"),
        NormalizedRejectReasons.RATE_LIMIT_EXCEEDED: ("QOS_BLOCKED", "QOS_BLOCKED"),
        "COOLDOWN": ("COOLDOWN", "COOLDOWN"),
        "SYMBOL_COOLDOWN_ACTIVE": ("COOLDOWN", "COOLDOWN"),
        NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE: ("COOLDOWN", "COOLDOWN"),
        "REGIME_BLOCKED": ("REGIME_BLOCKED", "REGIME_BLOCKED"),
    }
    if raw_upper in explicit_map:
        canonical_reason, reason_code = explicit_map[raw_upper]
        raw_reason_value = raw_clean if raw_clean != canonical_reason else None
        return canonical_reason, reason_code, raw_reason_value

    if raw_upper.startswith("MISSING_REGIME_THRESHOLD:"):
        return "NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY", raw_clean

    normalized = NormalizedRejectReasons.normalize(raw_clean)
    if normalized == NormalizedRejectReasons.DATA_NOT_READY:
        return "NRR-DATA-NOT-READY", "NRR-DATA-NOT-READY", raw_clean
    if normalized == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED:
        return "QOS_BLOCKED", "QOS_BLOCKED", raw_clean
    if normalized == NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE:
        return "COOLDOWN", "COOLDOWN", raw_clean

    raise ValueError(f"Unsupported INTENT_DEFERRED reason: {raw_clean}")


def _append_truth_event(
    *,
    verb: str,
    src: str,
    rid: Optional[str],
    ts_ms: int,
    payload: dict[str, Any],
    why: str,
) -> None:
    mode = str(os.getenv("DECISION_TRUTH_WAL_MODE", "wal")).strip().lower()
    if mode in ("off", "disabled"):
        return

    msg = Message(
        op="EVT",
        verb=verb,
        src=str(src),
        dst="any",
        rid=str(rid) if rid not in (None, "") else f"{verb.lower()}:{payload.get('symbol', 'unknown')}:{ts_ms}",
        ts=int(ts_ms),
        why=truncate_why(str(why)) or verb.lower(),
        pld=payload,
    )
    res = wal.append(msg.model_dump())
    if res is None:
        logger.error(
            "[%s] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT) verb=%s rid=%s",
            payload.get("symbol", "unknown"),
            verb,
            rid,
        )


def write_intent_deferred(
    *,
    symbol: str,
    reason: str,
    reason_code: str,
    retry_key: str,
    next_allowed_ts: int,
    attempt: int,
    max_attempts: int,
    original_event: dict[str, Any],
    src: str,
    ts_ms: int,
    rid: Optional[str] = None,
    why_chain: Optional[list[str]] = None,
    context: Optional[str] = None,
    retry_policy: Optional[dict[str, Any]] = None,
    raw_reason: Optional[str] = None,
    span_id: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "retry_key": str(retry_key),
        "symbol": str(symbol),
        "reason": str(reason),
        "reason_code": str(reason_code),
        "next_allowed_ts": int(next_allowed_ts),
        "attempt": int(attempt),
        "max_attempts": int(max_attempts),
        "original_event": dict(original_event),
        "why_chain": [str(x) for x in list(why_chain or []) if str(x)],
        "created_ts": int(ts_ms),
    }
    if retry_policy is not None:
        payload["retry_policy"] = dict(retry_policy)
    if context:
        payload["context"] = str(context)
    if rid not in (None, ""):
        payload["rid"] = str(rid)
    if span_id not in (None, ""):
        payload["span_id"] = str(span_id)
    if raw_reason:
        payload["raw_reason"] = str(raw_reason)

    _append_truth_event(
        verb="INTENT_DEFERRED",
        src=src,
        rid=rid,
        ts_ms=int(ts_ms),
        payload=payload,
        why=f"intent_deferred:{reason_code}",
    )
    return payload


def write_strategy_decision_blocked(
    *,
    strategy_id: str,
    symbol: str,
    reason_code: str,
    reason: str,
    context: str,
    src: str,
    ts_ms: int,
    rid: Optional[str] = None,
    why: Optional[str] = None,
    why_chain: Optional[list[str]] = None,
    details: Optional[dict[str, Any]] = None,
    tf_sec: Optional[int] = None,
    bar_close_ts: Optional[int] = None,
    span_id: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "strategy_id": str(strategy_id),
        "symbol": str(symbol),
        "reason_code": str(reason_code),
        "reason": str(reason),
        "stage": "STRATEGY",
        "context": str(context),
        "why": str(why or context),
        "ts_ms": int(ts_ms),
        "why_chain": [str(x) for x in list(why_chain or []) if str(x)],
    }
    if details:
        payload["details"] = details
    if rid not in (None, ""):
        payload["rid"] = str(rid)
    if tf_sec is not None:
        payload["tf_sec"] = int(tf_sec)
    if bar_close_ts is not None:
        payload["bar_close_ts"] = int(bar_close_ts)
    if span_id not in (None, ""):
        payload["span_id"] = str(span_id)

    _append_truth_event(
        verb="STRATEGY_DECISION_BLOCKED",
        src=src,
        rid=rid,
        ts_ms=int(ts_ms),
        payload=payload,
        why=f"strategy_decision_blocked:{reason_code}",
    )
    return payload


def write_decision_blocked(
    *,
    symbol: str,
    reason_code: str,
    reason: str,
    path: str,
    why: str,
    stage: str,
    src: str,
    ts_ms: int,
    rid: Optional[str] = None,
    why_chain: Optional[list[str]] = None,
    details: Optional[dict[str, Any]] = None,
    span_id: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "symbol": str(symbol),
        "stage": str(stage),
        "ts_ms": int(ts_ms),
        "reason_code": str(reason_code),
        "reason": str(reason),
        "path": str(path),
        "why": str(why),
        "why_chain": [str(x) for x in list(why_chain or []) if str(x)],
    }
    if rid not in (None, ""):
        payload["rid"] = str(rid)
    if details:
        payload["details"] = details
    if span_id not in (None, ""):
        payload["span_id"] = str(span_id)

    _append_truth_event(
        verb="DECISION_BLOCKED",
        src=src,
        rid=rid,
        ts_ms=int(ts_ms),
        payload=payload,
        why=f"decision_blocked:{reason_code}",
    )
    return payload
