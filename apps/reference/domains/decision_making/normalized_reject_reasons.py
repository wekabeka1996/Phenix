"""
Normalized Reject Reasons (NRR) module.

Provides standardized error codes and normalization logic for consistent
error handling across the trading system.
"""

import re
from typing import Optional


class NormalizedRejectReasons:
    """
    Maps raw error messages to standardized NRR codes for analytics and debugging.
    """

    # NRR Code definitions
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
    # Phase 4: Net-Zero Score Readiness & Liquidity Codes
    FEATURES_NOT_READY = "NRR-031"
    FEATURES_MISSING = "NRR-032"
    LIQUIDITY_LOW = "NRR-033"
    LIQUIDITY_NOT_READY = "NRR-034" # If kappa missing entirely
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
    CONFIG_SAFETY_GATES_MISSING = "NRR-054"
    # Phase 5: Execution Gates
    HARD_VETO_BLOCKED = "NRR-055"
    SHIELD_INVARIANT_VIOLATED = "NRR-056"
    SHIELD_VETO_BLOCKED = "NRR-057"
    STRUCTURAL_GATE_BLOCKED = "NRR-058"
    # Phase 0.5: System Stress Overlay gate (EXTREME state blocks new entries)
    SYSTEM_STRESS_ENTRY_BLOCKED = "NRR-059"
    UNKNOWN_ERROR = "NRR-999"


    # Regex patterns for normalization
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
    def normalize(cls, raw_reason: str) -> str:
        """
        Normalize a raw reject reason to a standardized NRR code.

        Args:
            raw_reason: The raw error message from API or system

        Returns:
            Standardized NRR code
        """
        if not raw_reason:
            return cls.UNKNOWN_ERROR

        raw_clean = raw_reason.strip()

        # Idempotency: if the input is already a known NRR code (optionally with extra details),
        # preserve the canonical numeric code.
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

        # Explicit short-code mapping (used by internal sizing/validation helpers).
        # Keep this before regex so that stable internal codes map deterministically.
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
        }
        for short_code, nrr_code in short_code_map.items():
            if raw_upper == short_code or raw_upper.startswith(short_code + ":") or raw_upper.startswith(short_code + " "):
                return nrr_code

        # Prefix-based mapping for DM reasons we want to group under DATA_NOT_READY.
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
        Get human-readable description for an NRR code.

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
            cls.FEATURES_NOT_READY: "Essential features are not yet ready (warmup)",
            cls.FEATURES_MISSING: "Essential features are missing from payload",
            cls.LIQUIDITY_LOW: "Liquidity is too low (kappa gate)",
            cls.LIQUIDITY_NOT_READY: "Liquidity metrics are missing",
            cls.REGIME_UNSUPPORTED: "Current regime is not allowed for trading",
            cls.EXPOSURE_CACHE_UNAVAILABLE: "Exposure cache missing/stale/error (fail-closed)",
            cls.CONFIG_SAFETY_GATES_MISSING: "Strategy safety_gates.enabled config missing (fail-closed)",
            cls.UNKNOWN_ERROR: "Unknown or unmapped error condition",
        }


        return descriptions.get(nrr_code)
