"""Canonical normalized reject-reason surface for decision-making paths.

This module is the SSOT for class-level NRR codes used directly by
decision_making and adjacent domains. It also provides three helper surfaces:

- ``normalize()`` collapses raw reject strings, short helper codes, and
    already-normalized NRR strings onto a canonical NRR code;
- ``get_description()`` returns optional operator-facing text for codes that
    currently have a local description entry;
- ``normalize_trade_intent_rejected_payload()`` canonicalizes the shared
    TRADE_INTENT_REJECTED payload shape without taking ownership of emission,
    WAL writes, or lifecycle closure.

The module does not emit events or persist diagnostics on its own. Its job is
to keep the reject taxonomy stable and deterministic for callers that already
chose to reject, defer, or classify an outcome.
"""

import re
import time
from typing import Any, Dict, Mapping, Optional

from vfoundation.core.protocol import Message, truncate_why


TRADE_INTENT_REJECTED_CANONICAL_KEYS = frozenset(
    {
        "ts_ms",
        "symbol",
        "tf_sec",
        "bar_close_ts",
        "reason_code",
        "strategy_id",
        "side",
        "rid",
        "stage",
        "why",
        "context",
        "why_chain",
        "details",
        "entry_plan",
    }
)

TRADE_INTENT_REJECTED_ALLOWED_STAGES = frozenset(
    {"RISK", "STRATEGY", "DECISION", "EXECUTION"}
)


def _stringify_payload_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_payload_text(payload: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = _stringify_payload_value(payload.get(key))
        if value is not None:
            return value
    return None


def _resolve_payload_ts_ms(
    payload: Mapping[str, Any], fallback_ts_ms: Optional[int]
) -> int:
    for key in ("ts_ms", "timestamp", "ts", "bar_close_ts"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue

    if fallback_ts_ms is not None:
        return int(fallback_ts_ms)

    return int(time.time() * 1000)


def _normalize_trade_intent_rejected_side(value: Any) -> Optional[str]:
    text = _stringify_payload_value(value)
    if text is None:
        return None
    side = text.lower()
    return side if side in {"buy", "sell"} else None


def stringify_trade_intent_rejected_value(value: Any) -> Optional[str]:
    """Return a trimmed string for shared reject payload helpers."""

    return _stringify_payload_value(value)


def resolve_trade_intent_rejected_rid(
    payload: Mapping[str, Any], fallback_rid: Optional[str] = None
) -> Optional[str]:
    """Resolve the canonical RID used by reject event/WAL artifacts."""

    return _first_payload_text(payload, "rid") or _stringify_payload_value(
        fallback_rid
    )


def build_trade_intent_rejected_message(
    payload: Mapping[str, Any],
    *,
    src: str,
    rid: Optional[str] = None,
    dst: str = "any",
) -> Message:
    """Build the canonical event-shaped TRADE_INTENT_REJECTED record.

    The helper is pure: callers decide whether to emit, append to WAL, or both.
    """

    raw = dict(payload or {})
    symbol = _first_payload_text(raw, "symbol", "instrument") or "unknown"
    reason_code = _first_payload_text(raw, "reason_code") or "UNKNOWN"
    ts_ms = _resolve_payload_ts_ms(raw, None)
    msg_rid = resolve_trade_intent_rejected_rid(raw, fallback_rid=rid)

    return Message(
        op="EVT",
        verb="TRADE_INTENT_REJECTED",
        src=str(src),
        dst=str(dst),
        rid=msg_rid or f"rej:{symbol}:{ts_ms}",
        ts=ts_ms,
        why=truncate_why(f"trade_intent_rejected:{reason_code}"),
        pld=raw,
    )


def normalize_trade_intent_rejected_payload(
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
    fallback_ts_ms: Optional[int] = None,
    fallback_symbol: Optional[str] = None,
    fallback_reason_code: Optional[str] = None,
    fallback_stage: Optional[str] = None,
    fallback_why: Optional[str] = None,
) -> Dict[str, Any]:
    """Canonicalize the shared TRADE_INTENT_REJECTED payload surface.

    This helper is intentionally pure: it normalizes payload fields and legacy
    compatibility aliases, but does not emit events, write WAL, or close
    lifecycle state. Domain owners keep those decisions locally.
    """

    normalized: Dict[str, Any] = {}
    raw = dict(payload or {})

    normalized["ts_ms"] = _resolve_payload_ts_ms(raw, fallback_ts_ms)

    symbol = _first_payload_text(raw, "symbol", "instrument") or _stringify_payload_value(
        fallback_symbol
    )
    if symbol is not None:
        normalized["symbol"] = symbol

    tf_sec = raw.get("tf_sec")
    if tf_sec is not None:
        try:
            normalized["tf_sec"] = int(tf_sec)
        except (TypeError, ValueError):
            pass

    bar_close_ts = raw.get("bar_close_ts")
    if bar_close_ts is not None:
        try:
            normalized["bar_close_ts"] = int(bar_close_ts)
        except (TypeError, ValueError):
            pass

    reason_code = _first_payload_text(raw, "reason_code") or _stringify_payload_value(
        fallback_reason_code
    )
    if reason_code is not None:
        normalized["reason_code"] = reason_code

    strategy_id = _first_payload_text(raw, "strategy_id")
    if strategy_id is not None:
        normalized["strategy_id"] = strategy_id

    side = _normalize_trade_intent_rejected_side(raw.get("side"))
    if side is not None:
        normalized["side"] = side

    rid = _first_payload_text(
        raw, "rid") or _stringify_payload_value(fallback_rid)
    if rid is not None:
        normalized["rid"] = rid

    stage = _first_payload_text(raw, "stage")
    stage_upper = stage.upper() if stage is not None else None
    if stage_upper not in TRADE_INTENT_REJECTED_ALLOWED_STAGES:
        fallback_stage_text = _stringify_payload_value(fallback_stage)
        stage_upper = (
            fallback_stage_text.upper() if fallback_stage_text is not None else None
        )
    if stage_upper in TRADE_INTENT_REJECTED_ALLOWED_STAGES:
        normalized["stage"] = stage_upper

    why = _first_payload_text(raw, "why", "reason") or _stringify_payload_value(
        fallback_why
    )
    if why is not None:
        normalized["why"] = why[:240]

    context = _first_payload_text(raw, "context")
    if context is not None:
        normalized["context"] = context

    why_chain = raw.get("why_chain")
    if isinstance(why_chain, (list, tuple)):
        normalized["why_chain"] = [
            str(item) for item in why_chain if _stringify_payload_value(item)
        ]

    details = raw.get("details")
    if isinstance(details, dict):
        normalized["details"] = dict(details)

    entry_plan = raw.get("entry_plan")
    if isinstance(entry_plan, dict):
        normalized["entry_plan"] = dict(entry_plan)

    legacy_top_level_keys = sorted(
        key
        for key in raw.keys()
        if key not in TRADE_INTENT_REJECTED_CANONICAL_KEYS and key != "instrument"
    )
    if legacy_top_level_keys:
        compat_details = dict(normalized.get("details") or {})
        compat_details.setdefault(
            "compat_dropped_top_level_keys", legacy_top_level_keys
        )
        normalized["details"] = compat_details

    return normalized


class NormalizedRejectReasons:
    """Canonical NRR codes plus normalization helpers.

    Most consumers use the class attributes directly as stable reason codes.
    ``normalize()`` exists for compatibility paths where callers still provide
    free-text messages or local helper codes instead of the final NRR value.
    """

    # Canonical class-level codes. Tests guard both identity and format because
    # this class is treated as the single source of truth across domains.
    INSUFFICIENT_BALANCE = "NRR-001"
    INVALID_ORDER_PARAMS = "NRR-002"
    MARKET_CLOSED = "NRR-003"
    SYMBOL_NOT_TRADING = "NRR-004"
    PRICE_OUT_OF_RANGE = "NRR-005"
    QUANTITY_TOO_SMALL = "NRR-006"
    QUANTITY_TOO_LARGE = "NRR-007"
    ORDER_WOULD_TRIGGER_LIQ = "NRR-008"
    REDUCE_ONLY_VIOLATION = "NRR-009"
    POSITION_SIZE_EXCEEDED = "NRR-010"
    EXPOSURE_LIMIT_EXCEEDED = "NRR-011"
    # Per-side limit exceeded (EXP-DIRECTION)
    SIDE_EXPOSURE_EXCEEDED = "NRR-012"
    # Directional imbalance limit exceeded (EXP-DIRECTION)
    DIRECTIONAL_RATIO_EXCEEDED = "NRR-013"
    RATE_LIMIT_EXCEEDED = "NRR-014"
    NETWORK_ERROR = "NRR-015"
    TIMEOUT_ERROR = "NRR-016"
    SYMBOL_COOLDOWN_ACTIVE = "NRR-017"
    EXCHANGE_REJECTED_ORDER = "NRR-018"
    ORDER_TIMEOUT_EXPIRED = "NRR-019"
    # TASK47c-B: Leverage/Margin verification codes
    LEVERAGE_MISMATCH = "NRR-020"
    MARGIN_MODE_MISMATCH = "NRR-021"
    LEVERAGE_SET_FAILED = "NRR-022"
    MARGIN_MODE_SET_FAILED = "NRR-023"
    LEVERAGE_VERIFY_FAILED = "NRR-024"
    # Domain-level gating: upstream data/warmup not ready
    DATA_NOT_READY = "NRR-025"
    # DM-DIR-FORENSIC-01: Directional sanity gate
    INSUFFICIENT_TREND_CONFIRMATION = "NRR-026"
    DIRECTIONAL_SANITY_BLOCKED = "NRR-027"
    PRICE_MOTION_INSUFFICIENT = "NRR-028"
    PRICE_MOTION_FLASH_BLOCKED = "NRR-029"
    PRICE_MOTION_BLEED_BLOCKED = "NRR-030"
    REGIME_CONFIDENCE_ABOVE_MAX = "NRR-063"
    # Phase 4: Net-Zero Score Readiness & Liquidity Codes
    FEATURES_NOT_READY = "NRR-031"
    FEATURES_MISSING = "NRR-032"
    LIQUIDITY_LOW = "NRR-033"
    LIQUIDITY_NOT_READY = "NRR-034"  # If kappa missing entirely
    REGIME_UNSUPPORTED = "NRR-035"
    # Direction/Strength scoring hardening
    NORMALIZE_LEGACY_FORBIDDEN_LIVE = "NRR-036"
    NO_DIRECTIONAL_FEATURES_ACTIVE = "NRR-037"
    NO_STRENGTH_FEATURES_ACTIVE = "NRR-038"
    # P0-0: Readiness Contract Audit
    CONFIG_CONTRACT_MISSING = "NRR-CFG-001"
    CONFIG_CONTRACT_INVALID = "NRR-CFG-002"
    MISSING_READY_KEYS = "NRR-039"
    FULL_READY_INVARIANT_VIOLATED = "NRR-040"
    # P0-1: Volatility Overflow
    VOLATILITY_OVERFLOW = "NRR-041"
    # P0-2: Book Feed Health
    BOOK_FEED_UNHEALTHY = "NRR-042"
    SPREAD_UNHEALTHY = "NRR-043"
    # P0-3: Feature Sanity Firewall
    FEATURE_NAN_INF = "NRR-044"
    FEATURE_OUT_OF_RANGE = "NRR-045"
    # OBS/LEGACY: Missing timeframe context (tf_sec missing/0 where forbidden)
    MISSING_TF_SEC = "NRR-046"
    # ORDER-POLICY-01: Order type/tif policy validation
    ORDER_TYPE_MISSING = "NRR-047"
    UNSUPPORTED_ORDER_TYPE = "NRR-048"
    UNSUPPORTED_TIF = "NRR-049"
    LIMIT_PRICE_MISSING = "NRR-050"
    MARKET_PRICE_PRESENT = "NRR-051"
    TIF_REQUIRED_FOR_LIMIT = "NRR-052"
    # DM-SAFETY-BYPASSES-P1: Fail-closed exposure cache and safety gates config
    EXPOSURE_CACHE_UNAVAILABLE = "NRR-053"
    CONFIG_SAFETY_GATES_MISSING = "NRR-054"
    # Phase 5: Execution Gates
    HARD_VETO_BLOCKED = "NRR-055"
    SHIELD_INVARIANT_VIOLATED = "NRR-056"
    SHIELD_VETO_BLOCKED = "NRR-057"
    STRUCTURAL_GATE_BLOCKED = "NRR-058"
    # Phase 0.5: System Stress Overlay gate (EXTREME state blocks new entries)
    SYSTEM_STRESS_ENTRY_BLOCKED = "NRR-059"
    # Vector 1: Microstructure Veto (MR handler overlay)
    MICROSTRUCTURE_VETO = "NRR-060"
    # Regime loss embargo: shared entry gate block
    REGIME_LOSS_EMBARGO_BLOCKED = "NRR-061"
    # LVC-2: LOW_VOLATILITY fee-adjusted entry gate
    LOW_VOL_COST_FLOOR_BLOCKED = "NRR-062"
    UNKNOWN_ERROR = "NRR-999"

    # Regex normalization is intentionally partial: not every NRR constant is
    # expected to be discovered from arbitrary free-text messages.
    PATTERNS = {
        INSUFFICIENT_BALANCE: [
            r"insufficient.*balance",
            r"account.*insufficient",
            r"not enough.*funds",
            r"balance.*not.*sufficient",
        ],
        INVALID_ORDER_PARAMS: [
            r"invalid.*order.*param",
            r"order.*param.*invalid",
            r"bad.*request.*order",
        ],
        MARKET_CLOSED: [r"market.*closed", r"trading.*suspended", r"market.*not.*open"],
        SYMBOL_NOT_TRADING: [
            r"symbol.*not.*trading",
            r"instrument.*not.*available",
            r"symbol.*suspended",
        ],
        PRICE_OUT_OF_RANGE: [
            r"price.*out.*range",
            r"price.*too.*high",
            r"price.*too.*low",
            r"invalid.*price",
        ],
        QUANTITY_TOO_SMALL: [
            r"quantity.*too.*small",
            r"lot.*size.*minimum",
            r"min.*quantity",
        ],
        QUANTITY_TOO_LARGE: [
            r"quantity.*too.*large",
            r"max.*quantity",
            r"lot.*size.*maximum",
        ],
        ORDER_WOULD_TRIGGER_LIQ: [
            r"would.*trigger.*liquidation",
            r"liquidation.*risk",
            r"margin.*insufficient",
        ],
        REDUCE_ONLY_VIOLATION: [r"reduce.*only", r"position.*cannot.*increase"],
        POSITION_SIZE_EXCEEDED: [
            r"position.*size.*exceeded",
            r"max.*position",
            r"position.*limit",
        ],
        EXPOSURE_LIMIT_EXCEEDED: [
            r"exposure.*limit",
            r"risk.*limit.*exceeded",
            r"exposure.*exceeded",
            r"trading.*not.*allowed.*risk.*manager",
            r"risk.*score.*too.*high",
        ],
        SIDE_EXPOSURE_EXCEEDED: [
            r"side.*exposure.*exceeded",
            r"long.*limit.*exceeded",
            r"short.*limit.*exceeded",
        ],
        DIRECTIONAL_RATIO_EXCEEDED: [
            r"directional.*ratio.*exceeded",
            r"ratio.*limit.*exceeded",
            r"imbalance.*limit",
        ],
        RATE_LIMIT_EXCEEDED: [
            r"rate.*limit",
            r"too.*many.*requests",
            r"request.*rate.*exceeded",
        ],
        NETWORK_ERROR: [r"network.*error", r"connection.*failed", r"timeout.*network"],
        TIMEOUT_ERROR: [r"timeout", r"request.*timed.*out", r"operation.*timeout"],
        SYMBOL_COOLDOWN_ACTIVE: [r"symbol.*cooldown.*active", r"cooldown.*remaining"],
        EXCHANGE_REJECTED_ORDER: [r"exchange.*reject", r"order.*reject.*exchange", r"-1013", r"-1021", r"-2010"],
        ORDER_TIMEOUT_EXPIRED: [r"order.*timeout.*expired", r"ack.*timeout", r"fill.*timeout"],
        DATA_NOT_READY: [
            r"data.*not.*ready",
            r"not yet received",
            r"warmup.*missing",
            r"warmup.*not.*ready",
            r"regime.*missing",
            r"features.*missing",
            r"risk.*missing",
            r"features.*stale",
        ],
        INSUFFICIENT_TREND_CONFIRMATION: [
            r"insufficient.*trend",
            r"trend.*not.*confirmed",
            r"insufficient.*confirmation",
        ],
        DIRECTIONAL_SANITY_BLOCKED: [
            r"directional.*sanity",
            r"trend.*contradict",
            r"contra.*trend",
        ],
        REGIME_CONFIDENCE_ABOVE_MAX: [
            r"regime.*confidence.*above.*max",
            r"confidence.*above.*max",
            r"above.*max.*regime.*confidence",
        ],
        PRICE_MOTION_INSUFFICIENT: [
            r"price_motion.*insufficient",
            r"price motion.*insufficient",
            r"price_motion.*not.*ready",
        ],
        PRICE_MOTION_FLASH_BLOCKED: [
            r"price_motion.*flash",
            r"price motion.*flash",
        ],
        PRICE_MOTION_BLEED_BLOCKED: [
            r"price_motion.*bleed",
            r"price motion.*bleed",
        ],
        FEATURES_NOT_READY: [
            r"features.*not.*ready",
            r"essential.*feature.*not.*ready",
        ],
        FEATURES_MISSING: [
            r"feature.*missing",
            r"essential.*feature.*missing",
        ],
        LIQUIDITY_LOW: [
            r"liquidity.*low",
            r"liquidity.*gate.*blocked",
        ],
        LIQUIDITY_NOT_READY: [
            r"liquidity.*unknown",
            r"liquidity.*missing",
        ],
        REGIME_UNSUPPORTED: [
            r"regime.*unsupported",
            r"regime.*blocked",
        ],
        NORMALIZE_LEGACY_FORBIDDEN_LIVE: [
            r"normalize.*legacy.*forbidden",
            r"legacy_v1.*forbidden",
        ],
        NO_DIRECTIONAL_FEATURES_ACTIVE: [
            r"no.*directional.*features",
            r"directional.*features.*active",
        ],
        NO_STRENGTH_FEATURES_ACTIVE: [
            r"no.*strength.*features",
            r"strength.*features.*active",
        ],
    }

    @classmethod
    def normalize(cls, raw_reason: Optional[str]) -> str:
        """
        Normalize a caller-supplied reject reason to a canonical NRR code.

        Supported input shapes:
        - already-normalized NRR codes, optionally followed by details;
        - internal short helper codes used by sizing/validation paths;
        - free-text messages matched against the regex map below.

        Inputs that are empty or cannot be mapped fall back to UNKNOWN_ERROR.

        Args:
            raw_reason: Raw reason string, helper code, or canonical NRR code.

        Returns:
            Canonical NRR code
        """
        if not raw_reason:
            return cls.UNKNOWN_ERROR

        raw_clean = raw_reason.strip()

        # Preserve canonical codes first so callers can safely normalize an NRR
        # value multiple times without drifting into regex-based remaps.
        try:
            all_codes = {
                v
                for k, v in vars(cls).items()
                if isinstance(k, str)
                and k.isupper()
                and isinstance(v, str)
                and v.startswith("NRR-")
            }
        except Exception:
            all_codes = set()

        raw_upper_direct = raw_clean.upper()
        for code in all_codes:
            if raw_upper_direct == code or raw_upper_direct.startswith(code + ":") or raw_upper_direct.startswith(code + " "):
                return code

        # Internal helper codes are matched before regex so local validation
        # reasons map deterministically even when their text also matches a more
        # generic pattern.
        raw_upper = raw_upper_direct
        short_code_map = {
            "ZERO_QUANTITY": cls.INVALID_ORDER_PARAMS,
            "MIN_QTY": cls.QUANTITY_TOO_SMALL,
            "MIN_NOTIONAL": cls.QUANTITY_TOO_SMALL,
            # DecisionMaking gate strings (look like NRR but aren't numeric SSOT).
            "NRR-DATA-NOT-READY": cls.DATA_NOT_READY,
            "NRR-REGIME-MISSING": cls.DATA_NOT_READY,
            "NRR-ARMING-NOT-READY": cls.DATA_NOT_READY,
            "NRR-ARMING-WARMUP-MISSING": cls.DATA_NOT_READY,
            # Risk gate drift strings (DecisionMaking).
            "RISK_SCORE_MISSING": cls.DATA_NOT_READY,
            "RISK_SCORE_INVALID": cls.DATA_NOT_READY,
            # DM-DIR-FORENSIC-01
            "INSUFFICIENT_TREND_CONFIRMATION": cls.INSUFFICIENT_TREND_CONFIRMATION,
            "DIRECTIONAL_SANITY_BLOCKED": cls.DIRECTIONAL_SANITY_BLOCKED,
            "NRR-INSUFFICIENT-TREND-CONFIRMATION": cls.INSUFFICIENT_TREND_CONFIRMATION,
            "NRR-DIRECTIONAL-SANITY-BLOCKED": cls.DIRECTIONAL_SANITY_BLOCKED,
            "REGIME_CONFIDENCE_ABOVE_MAX": cls.REGIME_CONFIDENCE_ABOVE_MAX,
            "NRR-REGIME-CONFIDENCE-ABOVE-MAX": cls.REGIME_CONFIDENCE_ABOVE_MAX,
            # PRICE-MOTION-V1
            "PRICE_MOTION_INSUFFICIENT": cls.PRICE_MOTION_INSUFFICIENT,
            "PRICE_MOTION_FLASH_BLOCKED": cls.PRICE_MOTION_FLASH_BLOCKED,
            "PRICE_MOTION_BLEED_BLOCKED": cls.PRICE_MOTION_BLEED_BLOCKED,
            "NRR-PRICE-MOTION-INSUFFICIENT": cls.PRICE_MOTION_INSUFFICIENT,
            "NRR-PRICE-MOTION-FLASH-BLOCKED": cls.PRICE_MOTION_FLASH_BLOCKED,
            "NRR-PRICE-MOTION-BLEED-BLOCKED": cls.PRICE_MOTION_BLEED_BLOCKED,
            # Phase 4
            "NRR-FEATURES-NOT-READY": cls.FEATURES_NOT_READY,
            "NRR-FEATURES-MISSING": cls.FEATURES_MISSING,
            "NRR-LIQUIDITY-LOW": cls.LIQUIDITY_LOW,
            "NRR-LIQUIDITY-GATE-BLOCKED": cls.LIQUIDITY_LOW,
            "NRR-LIQUIDITY-NOT-READY": cls.LIQUIDITY_NOT_READY,
            "NRR-REGIME-UNSUPPORTED": cls.REGIME_UNSUPPORTED,
            "LOW_VOL_COST_FLOOR_BLOCKED": cls.LOW_VOL_COST_FLOOR_BLOCKED,
            "LOW_VOL_COST_FLOOR": cls.LOW_VOL_COST_FLOOR_BLOCKED,
        }
        for short_code, nrr_code in short_code_map.items():
            if raw_upper == short_code or raw_upper.startswith(short_code + ":") or raw_upper.startswith(short_code + " "):
                return nrr_code

        # Prefix grouping keeps families of degraded-context reasons stable even
        # when callers add detail after the shared prefix.
        if raw_upper.startswith("NRR-ARMING-"):
            return cls.DATA_NOT_READY

        if raw_upper.startswith("RISK_SCORE_"):
            return cls.DATA_NOT_READY

        raw_lower = raw_clean.lower()

        for nrr_code, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, raw_lower, re.IGNORECASE):
                    return nrr_code

        return cls.UNKNOWN_ERROR

    @classmethod
    def get_description(cls, nrr_code: str) -> Optional[str]:
        """
        Return the local human-readable description for an NRR code.

        Not every canonical code currently has a description entry in this
        method; callers must handle ``None`` as "no local copy defined".

        Args:
            nrr_code: The NRR code

        Returns:
            Description string or None if code not found
        """
        descriptions = {
            cls.INSUFFICIENT_BALANCE: "Account has insufficient balance for the operation",
            cls.INVALID_ORDER_PARAMS: "Order parameters are invalid or malformed",
            cls.MARKET_CLOSED: "Market is currently closed or trading suspended",
            cls.SYMBOL_NOT_TRADING: "Symbol is not currently available for trading",
            cls.PRICE_OUT_OF_RANGE: "Order price is outside acceptable range",
            cls.QUANTITY_TOO_SMALL: "Order quantity is below minimum allowed",
            cls.QUANTITY_TOO_LARGE: "Order quantity exceeds maximum allowed",
            cls.ORDER_WOULD_TRIGGER_LIQ: "Order would trigger account liquidation",
            cls.REDUCE_ONLY_VIOLATION: "Order violates reduce-only position rules",
            cls.POSITION_SIZE_EXCEEDED: "Position size would exceed limits",
            cls.EXPOSURE_LIMIT_EXCEEDED: "Operation would exceed total exposure limits",
            cls.SIDE_EXPOSURE_EXCEEDED: "Operation would exceed per-side exposure limits",
            cls.DIRECTIONAL_RATIO_EXCEEDED: "Operation would exceed directional imbalance limits",
            cls.RATE_LIMIT_EXCEEDED: "Request rate limit has been exceeded",
            cls.NETWORK_ERROR: "Network connectivity or communication error",
            cls.TIMEOUT_ERROR: "Operation timed out",
            cls.SYMBOL_COOLDOWN_ACTIVE: "Symbol cooldown period is active",
            cls.EXCHANGE_REJECTED_ORDER: "Exchange rejected the order",
            cls.ORDER_TIMEOUT_EXPIRED: "Order timeout expired",
            # TASK47c-B: Leverage/Margin verification descriptions
            cls.LEVERAGE_MISMATCH: "Exchange leverage does not match expected value",
            cls.MARGIN_MODE_MISMATCH: "Exchange margin mode does not match expected value",
            cls.LEVERAGE_SET_FAILED: "Failed to set leverage on exchange",
            cls.MARGIN_MODE_SET_FAILED: "Failed to set margin mode on exchange",
            cls.LEVERAGE_VERIFY_FAILED: "Failed to verify leverage settings (API error)",
            cls.CONFIG_CONTRACT_MISSING: "Configuration contract violation: Required key missing",
            cls.CONFIG_CONTRACT_INVALID: "Configuration contract violation: Invalid value type or range",
            cls.DATA_NOT_READY: "Required upstream data/warmup is missing or not yet ready",
            cls.INSUFFICIENT_TREND_CONFIRMATION: "Trend is not confidently confirmed (fail-closed)",
            cls.DIRECTIONAL_SANITY_BLOCKED: "Trade intent contradicts confirmed trend direction",
            cls.PRICE_MOTION_INSUFFICIENT: "Price motion features are missing/not warmed up (fail-closed)",
            cls.PRICE_MOTION_FLASH_BLOCKED: "Flash price motion gate blocked opening against fast move",
            cls.PRICE_MOTION_BLEED_BLOCKED: "Bleed price motion gate blocked opening against sustained move",
            cls.REGIME_CONFIDENCE_ABOVE_MAX: "Regime confidence is too strong for this strategy/regime band",
            cls.FEATURES_NOT_READY: "Essential features are not yet ready (warmup)",
            cls.FEATURES_MISSING: "Essential features are missing from payload",
            cls.LIQUIDITY_LOW: "Liquidity is too low (kappa gate)",
            cls.LIQUIDITY_NOT_READY: "Liquidity metrics are missing",
            cls.REGIME_UNSUPPORTED: "Current regime is not allowed for trading",
            cls.EXPOSURE_CACHE_UNAVAILABLE: "Exposure cache missing/stale/error (fail-closed)",
            cls.CONFIG_SAFETY_GATES_MISSING: "Strategy safety_gates.enabled config missing (fail-closed)",
            cls.REGIME_LOSS_EMBARGO_BLOCKED: "Symbol is blocked by the regime loss embargo policy",
            cls.LOW_VOL_COST_FLOOR_BLOCKED: "LOW_VOL entry blocked by the fee-adjusted cost-floor gate",
            cls.UNKNOWN_ERROR: "Unknown or unmapped error condition",
        }

        return descriptions.get(nrr_code)
