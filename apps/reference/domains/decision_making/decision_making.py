"""
DecisionMaking domain component.

Aggregates features, risk assessment, and portfolio state to make trading decisions
and emit EVT:TRADE_INTENT_PROPOSED events.

FTR-07: Refactored to use DecisionContext for type-safe feature access.
CFG-DOMAINS-STEP-02: Enforces AuroraConfig contract (not dict).
T2B-08: Clock abstraction for deterministic testing (QoS timers, cooldowns).
"""

import decimal
import json
import logging
from collections import deque
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Any, Optional, TYPE_CHECKING, List, Tuple
from apps.reference.config_contract import ConfigContractError
from apps.reference.utils.accessors import aget, dget

# T2B-08: Clock abstraction for deterministic testing
from apps.reference.core.time.clock import Clock, LiveClock

from vfoundation.core.protocol import Message
from vfoundation.dr import wal

from .normalized_reject_reasons import NormalizedRejectReasons
from .deferred_scheduler import DeferredIntentScheduler
from .dm_log_adapter import (
    DecisionLog,
)
# FTR-07: Import DecisionContext for typed feature access
from .decision_context import DecisionContext, create_decision_context
from .schemas_decision_blocked import DecisionBlockedPayload
from .sizing_margin_first import (
    compute_notional_target,
    compute_qty,
    validate_exchange_constraints,
)
from .aurora_scoring_kernel import AuroraScoringKernel, ScoringResult, SideBiasState

# EP-01.2-INT: EntryPlan for ATR-based entry/SL/TP computation
from .entry_plan import EntryPlan, EntryPlanParams, EntryPlanResult, ObiMissingPolicy

# CFG-DOMAINS-STEP-02: Import AuroraConfig for type enforcement
from apps.reference.config_models import AuroraConfig

from apps.reference.telemetry.metrics import (
    inc_decision_deferred,
    inc_config_contract_violation,
    inc_decision_blocked,
    inc_warmup_block,
)
from vfoundation.core.why_codes import WhyCode, format_why_with_details
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.contracts.reject_reasons import RejectReason, normalize_config_error

# CFG-DOMAINS-STEP-02: Import DomainConfigResolver for canonical config access
from apps.reference.domain_config import DomainConfigResolver

# Phase 0: Import Aurora per-instrument config
from apps.reference.config_models import AuroraInstrumentConfig

from vfoundation.core.protocol import truncate_why
from .trade_intent_reject_wal import write_trade_intent_rejected

# Import AlertManager for risk gating
try:
    from apps.reference.telemetry.alerts import AlertManager as _AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    _AlertManager = None  # type: ignore[assignment]

# Import alpha models
try:
    from apps.reference.domains.alpha_search import (
        AlphaModelRegistry,
        MomentumAlphaModel,
        MeanReversionAlphaModel,
        VolatilityAlphaModel
    )
    ALPHA_MODELS_AVAILABLE = True
except ImportError:
    ALPHA_MODELS_AVAILABLE = False

if TYPE_CHECKING:
    from vfoundation.core import FSMCore
    from apps.reference.telemetry.alerts import AlertManager

chain_logger = logging.getLogger("event_chain")


class DecisionMaking:
    """
    Decision making component that aggregates analytical data streams
    and generates trade intents based on aurora decision logic.

    CFG-DOMAINS-STEP-02: Requires AuroraConfig (not dict).
    T2B-08: Supports Clock injection for deterministic testing.
    """

    def __init__(
        self,
        fsm: "FSMCore",
        config: AuroraConfig,
        *,
        clock: Optional[Clock] = None,
    ) -> None:
        """
        Initialize DecisionMaking domain.

        Args:
            fsm: Finite State Machine for event emission
            config: AuroraConfig instance (NOT dict)
            clock: Optional Clock for time abstraction (default: LiveClock)

        Raises:
            TypeError: If config is dict (legacy pattern)
        """
        # CFG-DOMAINS-STEP-02-FIX: Reject dict, accept AuroraConfig & subclasses
        if isinstance(config, dict):
            raise TypeError(
                f"DecisionMaking requires AuroraConfig, got dict. "
                "Pass AuroraConfig directly (not dict)"
            )

        self.fsm = fsm
        self.config = config
        # T2B-08: Clock abstraction for QoS timers (default: LiveClock)
        self._clock: Clock = clock or LiveClock()
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        self.seq_counter = 0

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None}
        )

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None}
        )

        # NOTE: __init__ continues below (keep attribute initialization contiguous).
        self.latest_portfolio: Optional[Dict[str, Any]] = None
        self.latest_regime: Optional[Dict[str, Any]] = None
        # Idempotency guard
        self._last_successful_features_ts: Dict[str, int] = {}
        # Per-symbol regime cache: {symbol: {regime: str, warmup: dict, ...}}
        self._per_symbol_regimes: Dict[str, Dict[str, Any]] = {}
        # Side-bias history (symbols -> {buys: [ts], sells: [ts]})
        self._side_intent_window: Dict[str, Dict[str, list[float]]] = {}
        # Contract State: pending flips {symbol: {desired_open_intent, created_ts, ...}}
        self._pending_flips: Dict[str, Dict[str, Any]] = {}

        # TASK47: Strategy arbitration is windowed (avoid permanent suppression on hybrid symbols).
        # State: symbol -> (window_id, winner_strategy_id)
        self._arb_window_winner: Dict[str, tuple[int, str]] = {}

        # DM-CRITICAL-PATCHES-02: Dedicated signal buffer for priority arbitration
        # symbol -> (ts_ms, strategy_id, rank)
        # Used for forensic logging and priority comparison within window_ms
        self._arb_signal_buffer: Dict[str, Tuple[int, str, int]] = {}

        # Cache for equity values to prevent zero-overwrite
        self._cached_equity_free_usdt: Optional[str] = None
        self._cached_equity_cross_usdt: Optional[str] = None

        # Risk gate metrics for AlertManager
        self.intents_seen_total: int = 0  # Total intents evaluated
        self.intents_blocked_total: int = 0  # Intents blocked by risk gate
        self.last_alert_check_time: float = self._clock.now_sec()
        self.alert_manager: Optional["AlertManager"] = None
        if ALERT_MANAGER_AVAILABLE and _AlertManager is not None:
            try:
                self.alert_manager = _AlertManager(
                    config=config, logger=self.logger.getChild("alerts"))
                self.logger.info("AlertManager initialized in DecisionMaking")
            except Exception as e:
                self.logger.warning(f"Failed to initialize AlertManager: {e}")

        # QoS state management (PACK EXP-4) — partitioned by strategy_id (v7).
        # This prevents one strategy from rate-limiting another (e.g. Aurora vs MeanReversion).
        # NOTE: window_start uses 0.0 as init; actual time is set when first symbol is accessed.
        self._qos_state: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "last_exposure_block": 0.0,  # timestamp of last exposure block
                "symbol_cooldowns": {},  # symbol -> last_decision_timestamp
                "symbol_intent_counts": defaultdict(
                    lambda: {"count": 0, "window_start": 0.0}
                ),  # symbol -> rate tracking; window_start set on first access
            }
        )

        # QoS busy guard to prevent infinite defer loops (legacy tick path) — partitioned by strategy_id.
        # strategy_id -> (symbol -> next_allowed_ms)
        self._qos_next_allowed_ts: dict[str,
                                        dict[str, int]] = defaultdict(dict)
        self._deferred_scheduler = DeferredIntentScheduler()

        # Decision logging (DM breadcrumbs)
        self.dlog = DecisionLog()

        # Risk Gate Alert counters (monitoring)
        self.intents_seen_total: int = 0
        self.intents_blocked_total: int = 0
        self.last_alert_check_time: float = self._clock.now_sec()

        # Initialize alpha model registry
        self.alpha_registry = None
        if ALPHA_MODELS_AVAILABLE:
            self.alpha_registry = AlphaModelRegistry()
            # Register baseline models
            self.alpha_registry.register(MomentumAlphaModel())
            self.alpha_registry.register(MeanReversionAlphaModel())
            self.alpha_registry.register(VolatilityAlphaModel())
            self.logger.info(
                f"Alpha models initialized: {self.alpha_registry.list_models()}")
        else:
            self.logger.warning(
                "Alpha models not available - alpha_search module not found")

        # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Load strategies registry
        self.strategies_registry = None
        if hasattr(self.config, 'strategies_registry') and self.config.strategies_registry:
            self.strategies_registry = self.config.strategies_registry
            self.logger.info(
                f"Strategies registry loaded: {len(self.strategies_registry.assignments)} symbols, "
                f"arbitration mode: {self.strategies_registry.arbitration.mode}"
            )
        else:
            self.logger.warning(
                "Strategies registry not configured - multi-strategy arbitration disabled")

        # CFG-DOMAINS-STEP-02-FIX: Strict Config Access (Task 18)
        # Direct Pydantic access - overrides handled by ConfigLoader
        trading_config = getattr(self.config, 'trading', self.config)

        # TCA Preferences (Dict or Object)
        self._tca_prefs = getattr(trading_config, 'tca_prefs', {})
        if not self._tca_prefs:
            self.logger.warning(
                "tca_prefs missing/empty - using conservative TCA mode")

        # Risk Budgets (Dict or Object)
        self._risk_budgets = getattr(trading_config, 'risk_budgets', {})
        if not self._risk_budgets:
            self.logger.warning(
                "risk_budgets missing/empty - using conservative sizing mode")

        # CFG-DOMAINS-STEP-02: Domain configuration via DomainConfigResolver (CANONICAL)
        resolver = DomainConfigResolver(self.config)
        dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos
        flip_cfg = getattr(dm_cfg, "flip", None)

        # P1: Degraded DecisionContext gate configuration (canonical domains.decision_making)
        # Default is disabled to preserve live behavior unless explicitly enabled.
        self._fail_closed_on_degraded_context = bool(
            getattr(dm_cfg, "fail_closed_on_degraded_context", False))
        try:
            critical_keys_raw = list(
                getattr(dm_cfg, "degraded_context_critical_keys", []) or [])
        except Exception:
            critical_keys_raw = []
        self._degraded_context_critical_keys = set(
            str(k) for k in critical_keys_raw if str(k))
        try:
            by_strategy_raw = getattr(
                dm_cfg, "degraded_context_critical_keys_by_strategy", {}) or {}
        except Exception:
            by_strategy_raw = {}
        self._degraded_context_critical_keys_by_strategy: dict[str, set[str]] = {
            str(strategy_id): set(str(k) for k in (keys or []) if str(k))
            for strategy_id, keys in (by_strategy_raw.items() if isinstance(by_strategy_raw, dict) else [])
        }
        if self._fail_closed_on_degraded_context:
            self.logger.warning(
                "Degraded DecisionContext gate ENABLED (fail-closed). "
                f"global_keys={sorted(self._degraded_context_critical_keys) if self._degraded_context_critical_keys else 'DEFAULT'} "
                f"strategy_overrides={list(self._degraded_context_critical_keys_by_strategy.keys())}"
            )

        # Position sizing config - SSOT from domains.yaml
        sizing_cfg = dm_cfg.position_sizing
        self.min_pos_size_usd = decimal.Decimal(
            str(sizing_cfg.min_position_size_usd))
        self.liq_cap_usd = decimal.Decimal(
            str(sizing_cfg.liquidity_based_cap_usd))

        # QoS exposure cooldown - from canonical domains
        self.qos_exposure_block_cooldown_sec = int(
            qos_cfg.exposure_block_cooldown_sec)

        # QoS max intents - from canonical domains
        self.qos_max_intents_per_minute_per_symbol = int(
            qos_cfg.max_intents_per_minute_per_symbol)

        # QoS mode - from canonical domains
        self.qos_mode = str(qos_cfg.mode)

        # Per-symbol cooldown fallback (for symbols not in strategies.aurora.assets)
        # This is the ONLY fallback allowed - new symbols must be added to config
        self._default_symbol_cooldown_sec = int(qos_cfg.symbol_cooldown_sec)

        # Legacy enforce flag (from qos_cfg)
        self.qos_enforce = bool(qos_cfg.enforce)

        # Optional per-strategy QoS allowlist (empty => apply to all strategies).
        try:
            apply_to = list(getattr(qos_cfg, "apply_to_strategies", []) or [])
        except Exception:
            apply_to = []
        self._qos_apply_to_strategies: set[str] = set(
            str(s) for s in apply_to if str(s))

        # P0-W1: Warmup/arming gate (from domain config)
        self.arming_require_regime_warmup = dm_cfg.arming.require_regime_warmup
        self.arming_retry_backoff_ms = dm_cfg.arming.retry_backoff_ms
        self.arming_max_attempts = dm_cfg.arming.max_attempts

        # Features TTL (from domain config)
        self.features_ttl_sec = dm_cfg.features.ttl_sec

        # Flip orchestration smoothing (domain config)
        # Flip orchestration (domain config)
        # STRICT SSOT: Global killswitch only (no defaults)
        # Per-symbol logic is in _get_flip_config()
        self.flip_global_enabled = dm_cfg.flip.enabled

        self.logger.info(
            f"QoS config: mode={self.qos_mode}, enforce={self.qos_enforce}, "
            f"exposure_cooldown={self.qos_exposure_block_cooldown_sec}s, "
            f"symbol_cooldown=per-symbol (default={self._default_symbol_cooldown_sec}s), "
            f"max_intents_per_min={self.qos_max_intents_per_minute_per_symbol}, "
            f"features_ttl={self.features_ttl_sec}s, "
            f"flip_global={'on' if self.flip_global_enabled else 'off'} "
            f"(per-symbol override instruments.yaml)"
        )
        if self._qos_apply_to_strategies:
            self.logger.info(
                f"QoS strategy allowlist: {sorted(self._qos_apply_to_strategies)}"
            )

        # Bar Gating (Strict Object)
        self._bar_gating_enabled = dm_cfg.bar_gating.enable
        self._bar_ms = int(dm_cfg.bar_gating.bar_ms)
        self._last_bar_index: dict[str, int] = {}

        # Behavior FSM (Strict Object)
        self._behavior_enabled = dm_cfg.behavior_fsm.enable
        self._behavior_thresholds = {
            "high_vol_multiplier": float(dm_cfg.behavior_fsm.high_vol_multiplier),
            "low_vol_multiplier": float(dm_cfg.behavior_fsm.low_vol_multiplier),
        }
        self._behavior_state: Dict[str, str] = {}

        # LOW_VOL_COST_SUPPRESS-IMPLEMENT-004: Cost-based volatility gate
        # VERIFY-005 HARDENING: Added proxy control and sanity guards
        lvcs_cfg = getattr(dm_cfg, 'low_vol_cost_suppress', None)
        if lvcs_cfg:
            self._low_vol_cost_suppress_enabled = bool(lvcs_cfg.enabled)
            self._low_vol_cost_suppress_factor = float(lvcs_cfg.factor)
            self._low_vol_cost_suppress_default_cost_bps = float(
                lvcs_cfg.default_cost_bps)
            self._low_vol_cost_suppress_regimes = set(
                lvcs_cfg.apply_to_regimes)
            self._low_vol_cost_suppress_allow_reduce_only = bool(
                lvcs_cfg.allow_reduce_only)
            self._low_vol_cost_suppress_allow_rv_proxy = bool(
                lvcs_cfg.allow_rv_proxy_from_volatility_state)
            self._low_vol_cost_suppress_rv_proxy_scale = float(
                lvcs_cfg.volatility_state_to_bps_scale)
            self._low_vol_cost_suppress_bps_sanity_max = float(
                lvcs_cfg.bps_sanity_max)
        else:
            self._low_vol_cost_suppress_enabled = False
            self._low_vol_cost_suppress_factor = 1.5
            self._low_vol_cost_suppress_default_cost_bps = 4.0
            self._low_vol_cost_suppress_regimes = {'TREND_UP', 'TREND_DOWN'}
            self._low_vol_cost_suppress_allow_reduce_only = True
            self._low_vol_cost_suppress_allow_rv_proxy = False
            self._low_vol_cost_suppress_rv_proxy_scale = 10.0
            self._low_vol_cost_suppress_bps_sanity_max = 200.0

        # Telemetry counters for gate effectiveness analysis
        self._low_vol_cost_suppress_stats = {
            "blocks": 0,
            "pass": 0,
            "mean_cost_bps": 0.0,
            "mean_rv_bps": 0.0,
        }

        # Exposure cache for pre-checking exposure limits
        self._exposure_cache: Optional[Dict[str, Any]] = None
        self._exposure_cache_timestamp: float = 0.0

        # FSM event listeners
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)
        self.fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED",
                        self.update_exposure_cache)
        self.fsm.listen("EVT:STRATEGY_SIGNAL_PRODUCED",
                        self._on_strategy_signal_gateway)
        self.logger.info(
            "Strategy-gateway enabled: listening for EVT:STRATEGY_SIGNAL_PRODUCED")

    def _safe_decimal(
        self,
        value: Any,
        default: Optional[Decimal] = None,
    ) -> Optional[Decimal]:
        """Best-effort Decimal parser for untrusted inputs.

        - Returns `default` (or None) for None/invalid/non-finite values.
        - Never raises.
        """
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value if value.is_finite() else default
        try:
            d = Decimal(str(value))
        except Exception:
            return default
        return d if d.is_finite() else default

    def _validate_md_amr_trace(self, trace: Any) -> tuple[bool, Dict[str, Any]]:
        """Validate md_amr trace block for WAL policy REJECT_TRADE."""
        required = ["dir_score", "thr_buy", "thr_sell", "w_raw",
                    "w_norm", "qty_base", "qty_new", "conf_ratio"]
        if not isinstance(trace, dict):
            return False, {"error": "trace_not_dict", "required": required}

        missing = [k for k in required if k not in trace]
        if missing:
            return False, {"error": "missing_keys", "missing": missing}

        def _num(v: Any) -> Optional[float]:
            try:
                d = Decimal(str(v))
            except Exception:
                return None
            if not d.is_finite():
                return None
            return float(d)

        w_required = ["d1", "h1", "m30", "m15"]
        normalized: Dict[str, Any] = {}
        for key in ("w_raw", "w_norm"):
            w = trace.get(key)
            if not isinstance(w, dict):
                return False, {"error": f"{key}_not_dict"}
            missing_w = [k for k in w_required if k not in w]
            if missing_w:
                return False, {"error": f"{key}_missing", "missing": missing_w}
            w_normed: Dict[str, float] = {}
            for wk in w_required:
                val = _num(w.get(wk))
                if val is None:
                    return False, {"error": f"{key}_{wk}_invalid"}
                w_normed[wk] = float(val)
            normalized[key] = w_normed

        scalar_fields = ["dir_score", "thr_buy",
                         "thr_sell", "qty_base", "qty_new", "conf_ratio"]
        for k in scalar_fields:
            val = _num(trace.get(k))
            if val is None:
                return False, {"error": f"{k}_invalid"}
            normalized[k] = float(val)

        if not (-1.0 <= normalized["dir_score"] <= 1.0):
            return False, {"error": "dir_score_out_of_range", "value": normalized["dir_score"]}
        if normalized["thr_buy"] <= 0.0 or normalized["thr_sell"] <= 0.0:
            return False, {"error": "threshold_non_positive"}
        if normalized["qty_base"] < 0.0 or normalized["qty_new"] < 0.0:
            return False, {"error": "qty_negative"}
        if not (0.0 <= normalized["conf_ratio"] <= 2.0):
            return False, {"error": "conf_ratio_out_of_range", "value": normalized["conf_ratio"]}

        for optional_key in ("atr_zscore", "bias", "dir_components"):
            if optional_key in trace:
                normalized[optional_key] = trace.get(optional_key)

        return True, {"normalized": normalized}

    def _on_strategy_signal_gateway(self, event: Message) -> None:
        """
        Gateway for strategy signals: apply universal gates before emitting TRADE_INTENT_PROPOSED.

        STRICT SEQUENTIAL TRADING CONTRACT (Commit 3):
        Strategies emit EVT:STRATEGY_SIGNAL_PRODUCED and DecisionMaking applies the same gates as Aurora:
        1. Risk gate (is_trading_allowed, risk_score)
        2. QoS gate (cooldown, rate limiting)
        3. Exposure gate (portfolio limits)
        4. TTL gate (features freshness)

        Only after passing all gates, emit EVT:TRADE_INTENT_PROPOSED.
        """
        try:
            pld = event.pld
            if not isinstance(pld, dict):
                self.logger.warning(
                    "STRATEGY_SIGNAL_PRODUCED: invalid payload (not dict)")
                return

            strategy_id = pld.get("strategy_id")
            symbol = pld.get("symbol")
            side = pld.get("side")
            rid = pld.get("rid") or f"sig-{uuid.uuid4()}"
            why_chain = pld["why_chain"] if "why_chain" in pld else []
            # EP-01.3-INT: Extract tf_sec for pending entry TTL calculation
            tf_sec = pld.get("tf_sec")
            if tf_sec is not None:
                try:
                    tf_sec = int(tf_sec)
                except (ValueError, TypeError):
                    tf_sec = None

            if not strategy_id or not symbol or not side:
                self.logger.warning(
                    "STRATEGY_SIGNAL_PRODUCED: missing strategy_id/symbol/side")
                return

            side = str(side).upper()
            if side not in ("BUY", "SELL"):
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: invalid side={side!r}")
                return

            strategy_id_s = str(strategy_id)
            intent_kind = str(pld.get("intent_kind") or "ENTRY").upper()
            md_amr_trace_norm: Optional[Dict[str, Any]] = None

            if strategy_id_s == "md_amr":
                valid_trace, trace_info = self._validate_md_amr_trace(
                    pld.get("trace"))
                if not valid_trace:
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=str(rid),
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_trace_invalid",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["wal_trace_invalid"],
                        details=trace_info,
                    )
                    self._record_blocked_intent(symbol)
                    return
                md_amr_trace_norm = trace_info.get("normalized")
                if intent_kind not in ("ENTRY", "FULL_CLOSE", "PARTIAL_CLOSE"):
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=strategy_id_s,
                        side=side,
                        rid=str(rid),
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context=f"strategy_signal_gateway:md_amr_invalid_intent_kind:{intent_kind}",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["invalid_intent_kind"],
                        details={"intent_kind": intent_kind},
                    )
                    self._record_blocked_intent(symbol)
                    return

            self.logger.info(
                f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: Processing {side} signal rid={rid} strategy_id={strategy_id}")

            # === READINESS CONTRACT (v7) ===
            # Fail-closed: strategy must explicitly declare warmup_ok in payload.readiness.
            readiness = pld.get("readiness")
            if not isinstance(readiness, dict):
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Missing readiness (required: readiness.warmup_ok)"
                )
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=side,
                    rid=str(rid),
                    reason_code="READINESS_MISSING",
                    reason="READINESS",
                    context="strategy_signal_gateway:readiness_missing",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []),
                    details={"required": "readiness.warmup_ok"},
                )
                self._record_blocked_intent(symbol)
                return
            warmup_ok = readiness.get("warmup_ok")
            if warmup_ok is not True:
                self.logger.info(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - STRATEGY_NOT_READY (warmup_ok={warmup_ok!r})"
                )
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=side,
                    rid=str(rid),
                    reason_code="READINESS_WARMUP_NOT_OK",
                    reason="READINESS",
                    context="strategy_signal_gateway:readiness_warmup_not_ok",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []),
                    details={"warmup_ok": warmup_ok},
                )
                self._record_blocked_intent(symbol)
                return

            if intent_kind == "ENTRY":
                current_regime = self._resolve_symbol_regime(
                    symbol,
                    preferred=pld.get("regime"),
                )
                if self._is_uncertain_hard_block(current_regime):
                    self.logger.info(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - UNCERTAIN hard block ({strategy_id})"
                    )
                    inc_decision_blocked(
                        stage="gateway", reason_code="REGIME_GATE_BLOCKED")
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=side,
                        rid=str(rid),
                        reason_code="REGIME_GATE_BLOCKED",
                        reason="DECISION",
                        context="strategy_signal_gateway:uncertain_hard_block",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["REGIME_GATE_BLOCKED", "UNCERTAIN"],
                        details={"regime": current_regime},
                    )
                    self._record_blocked_intent(symbol)
                    return

                symbol_busy = self._get_symbol_entry_block_reason(
                    symbol, reduce_only=False)
                if symbol_busy is not None:
                    self.logger.info(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - symbol busy ({symbol_busy.get('reason')})"
                    )
                    inc_decision_blocked(
                        stage="gateway", reason_code="NRR-SYMBOL-BUSY")
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=side,
                        rid=str(rid),
                        reason_code="NRR-SYMBOL-BUSY",
                        reason="DECISION",
                        context="strategy_signal_gateway:symbol_busy",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["NRR-SYMBOL-BUSY"],
                        details=symbol_busy,
                    )
                    self._record_blocked_intent(symbol)
                    return

            # === GATE 0: STRATEGY ARBITRATION ===
            # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Check if this strategy is allowed
            arbitration_result = self._check_strategy_arbitration(
                symbol,
                str(strategy_id),
                ts_ms=int(pld.get("ts_ms")) if pld.get(
                    "ts_ms") is not None else None,
                commit=False,
            )
            if not arbitration_result["allowed"]:
                self.logger.info(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Arbitration blocked ({strategy_id}): {arbitration_result['reason']}"
                )
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=side,
                    rid=str(rid),
                    reason_code="ARBITRATION_BLOCKED",
                    reason="ARBITRATION",
                    context="strategy_signal_gateway:arbitration",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []),
                    details={
                        "arbitration_reason": arbitration_result.get("reason")},
                )
                self._record_blocked_intent(symbol)
                return

            if strategy_id_s == "md_amr" and intent_kind in ("FULL_CLOSE", "PARTIAL_CLOSE"):
                exit_reason = str(pld.get("exit_reason_code") or "MD_AMR_EXIT")
                strategy_trace_payload = {
                    "md_amr": md_amr_trace_norm} if md_amr_trace_norm else None
                if intent_kind == "FULL_CLOSE":
                    emitted = self._emit_reduce_only_close(
                        symbol=symbol,
                        reason=exit_reason,
                        rid=str(rid),
                        strategy_id=str(strategy_id_s),
                        strategy_trace=strategy_trace_payload,
                    )
                    if not emitted:
                        self._emit_trade_intent_rejected(
                            symbol=symbol,
                            strategy_id=str(strategy_id_s),
                            side=side,
                            rid=str(rid),
                            reason_code="NO_POSITION_FOR_CLOSE",
                            reason="DECISION",
                            context="strategy_signal_gateway:md_amr_full_close_no_position",
                            why_chain=(why_chain if isinstance(
                                why_chain, list) else []) + [exit_reason],
                        )
                        self._record_blocked_intent(symbol)
                    return

                qty_signed, _curr = self._get_portfolio_position_qty_signed(
                    symbol)
                if qty_signed is None or abs(qty_signed) < Decimal("1e-9"):
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id_s),
                        side=side,
                        rid=str(rid),
                        reason_code="NO_POSITION_FOR_SCALEOUT",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_no_position",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + [exit_reason],
                    )
                    self._record_blocked_intent(symbol)
                    return

                scaleout_fraction_raw = pld.get("scaleout_fraction")
                try:
                    scaleout_fraction = float(scaleout_fraction_raw)
                except Exception:
                    scaleout_fraction = 0.0
                if not (0.0 < scaleout_fraction <= 1.0):
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id_s),
                        side=side,
                        rid=str(rid),
                        reason_code="WAL_TRACE_INVALID",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_invalid_fraction",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["invalid_scaleout_fraction"],
                        details={"scaleout_fraction": scaleout_fraction_raw},
                    )
                    self._record_blocked_intent(symbol)
                    return

                close_side = "SELL" if qty_signed > 0 else "BUY"
                close_qty = abs(qty_signed) * Decimal(str(scaleout_fraction))
                if close_qty <= Decimal("1e-9"):
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id_s),
                        side=side,
                        rid=str(rid),
                        reason_code="NO_POSITION_FOR_SCALEOUT",
                        reason="DECISION",
                        context="strategy_signal_gateway:md_amr_partial_close_zero_qty",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + [exit_reason],
                    )
                    self._record_blocked_intent(symbol)
                    return

                ts_ms = pld.get("ts_ms")
                if ts_ms in (None, 0, "0", ""):
                    timestamp_ms = self._clock.now_ms()
                else:
                    timestamp_ms = int(ts_ms)
                    if 0 < timestamp_ms < 1_000_000_000_000:
                        timestamp_ms *= 1000

                why_chain_close = (why_chain if isinstance(why_chain, list) else [
                ]) + [exit_reason, "md_amr_partial_close"]
                self._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(close_qty)),
                    price=decimal.Decimal("0"),
                    why_chain=why_chain_close,
                    rid=str(rid),
                    reduce_only=True,
                    strategy_id=str(strategy_id_s),
                    decision_ts_ms=timestamp_ms,
                    strategy_trace=strategy_trace_payload,
                )
                return

            # Risk-skew limiter escalation state (Commit 5):
            # if until_refresh is active, fail-closed for this symbol until a new risk/features refresh clears it.
            guard_state = self.symbol_states[symbol].get(
                "risk_skew_guard") or {}
            if guard_state.get("until_refresh"):
                now_ms = self._clock.now_ms()
                retry_key = self._stable_retry_key(
                    prefix=str(strategy_id),
                    symbol=symbol,
                    rid=rid,
                    side=side,
                    ts_ms=pld.get("ts_ms"),
                )
                retry_sec = self._get_risk_skew_config(
                    "until_refresh_retry_sec")
                self.logger.error(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH (risk_skew_guard active)"
                )
                self._emit_intent_deferred_v1(
                    symbol=symbol,
                    reason="NRR-RISK-SKEW-UNTIL-REFRESH",
                    retry_key=retry_key,
                    next_allowed_ts=now_ms + int(retry_sec * 1000),
                    original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                    original_payload_min=dict(pld),
                    attempt=1,
                    max_attempts=5,
                    why_chain=(why_chain or []) +
                    ["NO_TRADE_UNTIL_REFRESH", "risk_skew_guard"],
                    context="strategy_signal_gateway:risk_skew_until_refresh",
                )
                self._record_blocked_intent(symbol)
                return

            # === GATE 1: RISK GATE ===
            # Use symbol_states SSOT (not self.latest_risk which doesn't exist)
            latest_risk = self.symbol_states[symbol].get("risk")

            # Fail-closed: if risk data not yet received, DEFER instead of crash
            if not latest_risk:
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: DEFER - Risk data not yet received (NRR-DATA-NOT-READY)"
                )
                now_ms = self._clock.now_ms()
                retry_key = self._stable_retry_key(
                    prefix=str(strategy_id),
                    symbol=symbol,
                    rid=rid,
                    side=side,
                    ts_ms=pld.get("ts_ms"),
                )
                self._emit_intent_deferred_v1(
                    symbol=symbol,
                    reason="NRR-DATA-NOT-READY",
                    retry_key=retry_key,
                    next_allowed_ts=now_ms + 500,
                    original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                    original_payload_min=dict(pld),
                    attempt=1,
                    max_attempts=5,
                    why_chain=(why_chain or []) +
                    ["missing:risk", "fail_closed"],
                    context="strategy_signal_gateway:risk_not_ready",
                )
                self._record_blocked_intent(symbol)
                return

            if latest_risk:
                risk_params = latest_risk.get("risk_parameters") or {}
                is_allowed = risk_params["is_trading_allowed"] if "is_trading_allowed" in risk_params else True

                # MR-RISK-GATE-NONE-FIX-01: never allow float(None) from payload drift.
                risk_score_raw = risk_params["risk_score"] if "risk_score" in risk_params else None
                if risk_score_raw is None:
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: DEFER - missing risk_score (RISK_SCORE_MISSING)"
                    )
                    now_ms = self._clock.now_ms()
                    retry_key = self._stable_retry_key(
                        prefix=str(strategy_id),
                        symbol=symbol,
                        rid=rid,
                        side=side,
                        ts_ms=pld.get("ts_ms"),
                    )
                    self._emit_intent_deferred_v1(
                        symbol=symbol,
                        reason="RISK_SCORE_MISSING",
                        retry_key=retry_key,
                        next_allowed_ts=now_ms + 500,
                        original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                        original_payload_min=dict(pld),
                        attempt=1,
                        max_attempts=5,
                        why_chain=(why_chain or []) +
                        ["missing:risk_score", "fail_closed"],
                        context="strategy_signal_gateway:risk_score_missing",
                    )
                    self._record_blocked_intent(symbol)
                    return

                try:
                    risk_score = float(risk_score_raw)
                except Exception:
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: DEFER - invalid risk_score (RISK_SCORE_INVALID)"
                    )
                    now_ms = self._clock.now_ms()
                    retry_key = self._stable_retry_key(
                        prefix=str(strategy_id),
                        symbol=symbol,
                        rid=rid,
                        side=side,
                        ts_ms=pld.get("ts_ms"),
                    )
                    self._emit_intent_deferred_v1(
                        symbol=symbol,
                        reason="RISK_SCORE_INVALID",
                        retry_key=retry_key,
                        next_allowed_ts=now_ms + 500,
                        original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                        original_payload_min=dict(pld),
                        attempt=1,
                        max_attempts=5,
                        why_chain=(why_chain or []) +
                        ["invalid:risk_score", "fail_closed"],
                        context="strategy_signal_gateway:risk_score_invalid",
                    )
                    self._record_blocked_intent(symbol)
                    return

                if not is_allowed:
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Risk gate blocked, is_trading_allowed=False"
                    )
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=side,
                        rid=str(rid),
                        reason_code="RISK_TRADING_NOT_ALLOWED",
                        reason="RISK",
                        context="strategy_signal_gateway:risk_gate",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []),
                        details={"is_trading_allowed": False},
                    )
                    self._record_blocked_intent(symbol)
                    return

                # Risk score threshold (SSOT):
                # - Global: domains.risk_management.trading_allowed_thresholds.max_risk_score
                # - Optional per-symbol override: strategies.aurora.assets.<SYM>.max_risk_score (enabled + value)
                try:
                    max_risk = float(
                        self.config.domains.risk_management.trading_allowed_thresholds.max_risk_score)
                    instr_cfg = self._get_aurora_instrument_cfg(symbol)
                    mrs = instr_cfg.max_risk_score if instr_cfg is not None else None
                    used_override = False
                    if mrs is not None and mrs.enabled:
                        used_override = True
                        max_risk = float(mrs.value)
                except Exception as e:
                    self.logger.error(f"Config Contract Violation: {e}")
                    self._record_blocked_intent(symbol)
                    return  # BLOCK TRADE

                if risk_score > max_risk:
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - "
                        f"risk_score {risk_score:.3f} > max_risk_score {max_risk} (used_override={used_override})"
                    )
                    self._record_blocked_intent(symbol)
                    return

                # === GATE 1.5: RISK SKEW GATE (Commit 5) ===
                # Check if risk.ts is too far from features.ts (stale risk data)
                risk_ts = latest_risk["ts"] if "ts" in latest_risk else 0
                # Use symbol_states SSOT (not self.latest_features which doesn't exist)
                features_data = self.symbol_states[symbol].get(
                    "features") or {}
                features_ts = features_data["ts"] if "ts" in features_data else 0

                # P1: Degraded DecisionContext gate (opt-in, per-strategy overrides supported).
                # Purpose: detect when "neutral" defaults are masking missing/invalid feature inputs.
                if isinstance(features_data, dict):
                    feats_payload = features_data.get("features") or {}
                    if isinstance(feats_payload, dict):
                        ctx = create_decision_context(
                            symbol, self._clock.now_ms(), feats_payload)
                        if self._degraded_context_gate_should_defer(
                            symbol=symbol,
                            rid=rid,
                            ctx=ctx,
                            features_evt=features_data,
                            strategy_id=str(strategy_id),
                        ):
                            return

                if risk_ts > 0 and features_ts > 0:
                    skew_sec = abs(features_ts - risk_ts) / 1000
                    max_skew_sec = self._get_risk_skew_config("max_skew_sec")

                    if skew_sec > max_skew_sec:
                        max_defer = self._get_risk_skew_config(
                            "max_defer_count")

                        # Track limiter state per symbol in symbol_states (SSOT)
                        now_ms = self._clock.now_ms()
                        window_sec = self._get_risk_skew_config(
                            "defer_window_sec")
                        state = self.symbol_states[symbol].setdefault(
                            "risk_skew_guard",
                            {"defer_count": 0, "window_start_ms": now_ms,
                                "until_refresh": False},
                        )

                        try:
                            window_start_ms = int(
                                state["window_start_ms"] if "window_start_ms" in state else now_ms)
                        except Exception:
                            window_start_ms = now_ms
                            state["window_start_ms"] = now_ms

                        if now_ms - window_start_ms > int(window_sec * 1000):
                            state["defer_count"] = 0
                            state["window_start_ms"] = now_ms

                        try:
                            state["defer_count"] = int(
                                state["defer_count"] if "defer_count" in state else 0) + 1
                        except Exception:
                            state["defer_count"] = 1

                        defer_count = int(
                            state["defer_count"] if "defer_count" in state else 1)

                        if defer_count >= max_defer:
                            state["until_refresh"] = True
                            self.logger.error(
                                f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH - "
                                f"Risk skew exceeded {defer_count} times (max {max_defer}). "
                                f"NRR-RISK-STALE skew={skew_sec:.1f}s > max={max_skew_sec}s"
                            )
                        else:
                            self.logger.warning(
                                f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: DEFER - "
                                f"NRR-RISK-STALE skew={skew_sec:.1f}s > max={max_skew_sec}s. "
                                f"Defer {defer_count}/{max_defer}"
                            )
                            now_ms = self._clock.now_ms()
                            retry_key = self._stable_retry_key(
                                prefix=str(strategy_id),
                                symbol=symbol,
                                rid=rid,
                                side=side,
                                ts_ms=pld.get("ts_ms"),
                            )
                            cooldown_sec = self._get_risk_skew_config(
                                "defer_cooldown_sec")
                            self._emit_intent_deferred_v1(
                                symbol=symbol,
                                reason="NRR-RISK-STALE",
                                retry_key=retry_key,
                                next_allowed_ts=now_ms +
                                int(cooldown_sec * 1000),
                                original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                                original_payload_min=dict(pld),
                                attempt=defer_count,
                                max_attempts=max_defer,
                                why_chain=(why_chain or [])
                                + [
                                    "risk_skew",
                                    f"skew_sec:{skew_sec:.3f}",
                                    f"defer_count:{defer_count}",
                                ],
                                context="strategy_signal_gateway:risk_skew",
                            )
                        self._record_blocked_intent(symbol)
                        return

            # === GATE 2: FLIP GATE (D3 - Flip Orchestration) ===
            # OPEN only allowed when position_state(symbol) == FLAT
            # If opposite-side position exists → initiate flip (close→wait→open)
            # If same-side position exists → BLOCK (anti-pyramiding)
            flip_result = self._handle_flip_orchestration(
                symbol=symbol,
                intent_side=side,
                original_pld=pld,
                source=str(strategy_id)
            )

            if flip_result:
                # Intent was blocked or deferred
                if flip_result == "FLIP_CLOSE_PENDING":
                    self.logger.info(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: FLIP initiated - close emitted, OPEN deferred"
                    )
                elif flip_result == "NRR-FLIP-CLOSE-QTY-INVALID":
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: FLIP fail-closed - CLOSE qty invalid, OPEN deferred"
                    )
                elif flip_result == "ANTI_PYRAMIDING_BLOCK":
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: BLOCK - Same-side pyramiding not allowed"
                    )
                else:
                    # NRR-PORTFOLIO-UNKNOWN or other
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: BLOCK - {flip_result}"
                    )
                    if flip_result == "NRR-PORTFOLIO-UNKNOWN":
                        now_ms = self._clock.now_ms()
                        # Position Tracking Stale TTL (SSOT fail-closed)
                        stale_ttl_sec_f = self.config.domains.position_tracking.positions_stale_ttl_sec
                        if stale_ttl_sec_f is None:
                            raise ValueError(
                                "domains.position_tracking.positions_stale_ttl_sec is required (SSOT)")
                        retry_key = self._stable_retry_key(
                            prefix=str(strategy_id),
                            symbol=symbol,
                            rid=rid,
                            side=side,
                            ts_ms=pld.get("ts_ms"),
                        )
                        self._emit_intent_deferred_v1(
                            symbol=symbol,
                            reason="NRR-PORTFOLIO-UNKNOWN",
                            retry_key=retry_key,
                            next_allowed_ts=now_ms +
                            int(stale_ttl_sec_f * 1000),
                            original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                            original_payload_min=dict(pld),
                            attempt=1,
                            max_attempts=5,
                            why_chain=(why_chain or []) +
                            ["portfolio_unknown", "fail_closed"],
                            context="strategy_gateway_flip_check",
                        )

                self._record_blocked_intent(symbol)
                return

            # === GATE 3: QOS GATE ===
            qos_enabled = self._qos_enabled_for_strategy(str(strategy_id))
            if qos_enabled:
                # QOS-SPLIT-BRAIN-FIX: Pass strategy_id to ensure partition isolation
                qos_allowed, qos_reason = self._qos_allow(
                    symbol, strategy_id=str(strategy_id))
                if not qos_allowed:
                    effective_mode = self.qos_mode
                    if self.qos_enforce and effective_mode == "defer":
                        effective_mode = "enforce"

                    if effective_mode == "shadow":
                        # Shadow mode: only log/metrics, continue with intent.
                        self.logger.warning(
                            f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: QoS shadow - allowing intent (reason: {qos_reason})"
                        )
                    elif effective_mode == "defer":
                        # Defer mode: emit INTENT_DEFERRED (v1) and retry after cooldown.
                        now_ms = self._clock.now_ms()
                        # QOS-SPLIT-BRAIN-FIX: Pass strategy_id for correct partition
                        next_allowed_ts = int(self._calculate_next_allowed_time(
                            symbol, strategy_id=str(strategy_id)))
                        retry_key = self._stable_retry_key(
                            prefix=f"{strategy_id}:qos",
                            symbol=symbol,
                            rid=rid,
                            side=side,
                            ts_ms=pld.get("ts_ms"),
                        )
                        self.logger.warning(
                            f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: QoS defer - intent deferred until {next_allowed_ts} (reason: {qos_reason})"
                        )
                        self._emit_intent_deferred_v1(
                            symbol=symbol,
                            reason=str(qos_reason or "qos_defer"),
                            retry_key=retry_key,
                            next_allowed_ts=next_allowed_ts,
                            original_event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
                            original_payload_min=dict(pld),
                            attempt=1,
                            max_attempts=5,
                            why_chain=(why_chain or []) + ["qos", "defer"],
                            context="strategy_gateway_qos",
                        )
                        self._record_blocked_intent(symbol)
                        return
                    else:
                        # Enforce mode: block intent.
                        self.logger.info(
                            f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - QoS blocked: {qos_reason}"
                        )
                        self._record_blocked_intent(symbol)
                        return
            else:
                self.logger.debug(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: QoS skipped for strategy_id={strategy_id}"
                )

            # === GATE 4: EXPOSURE GATE (pre-check) ===
            # TASK39: Size is computed by DecisionMaking (Sizing Contract v2), not supplied by strategy.
            price_ctx = pld.get("price_ctx") if isinstance(
                pld.get("price_ctx"), dict) else {}
            entry_price = price_ctx.get("entry_price")
            if entry_price in (None, "", "0", 0):
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Missing entry_price")
                self._record_blocked_intent(symbol)
                return
            try:
                entry_price_dec = decimal.Decimal(str(entry_price))
            except Exception:
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Invalid entry_price")
                self._record_blocked_intent(symbol)
                return

            # NOTE: Gate 1 (Risk Data Readiness) is handled earlier at lines 532-560

            if not self.latest_portfolio:
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - portfolio_missing")
                self._record_blocked_intent(symbol)
                return

            llm_order = pld.get("order") if isinstance(
                pld.get("order"), dict) else {}
            llm_order_type: str | None = None
            llm_order_tif: str | None = None
            if strategy_id_s == "llm_microstructure":
                llm_order_type = str(llm_order.get("type") or "LIMIT").upper()
                llm_order_tif = str(llm_order.get(
                    "time_in_force") or "GTC").upper()

            sizing_ctx = {
                "portfolio": self.latest_portfolio,
                "features": self.symbol_states[symbol].get("features") if symbol in self.symbol_states else {},
            }
            # === Aurora Regime Sizing (per-symbol multiplier) ===
            # Optional: strategies.aurora.assets.<SYM>.regime_sizing[regime] scales margin_pct (margin-first sizing).
            regime_name = None
            scoring = pld.get("scoring") if isinstance(
                pld.get("scoring"), dict) else None
            if isinstance(scoring, dict):
                regime_name = scoring.get("regime")

            margin_pct_mult: decimal.Decimal | None = None
            if str(strategy_id) == "aurora" and regime_name:
                try:
                    instr_cfg = self._get_aurora_instrument_cfg(symbol)
                    rs = aget(instr_cfg, "regime_sizing",
                              None) if instr_cfg is not None else None
                    if isinstance(rs, dict) and rs:
                        mult_raw = rs.get(str(regime_name))
                        if mult_raw is None:
                            mult_raw = rs.get("DEFAULT")
                        if mult_raw is not None:
                            margin_pct_mult = decimal.Decimal(str(mult_raw))
                except Exception:
                    margin_pct_mult = None
            # === END Aurora Regime Sizing ===
            if strategy_id_s == "llm_microstructure":
                qty_raw = llm_order.get("qty")
                try:
                    qty_dec = decimal.Decimal(str(qty_raw))
                    if qty_dec <= decimal.Decimal("0"):
                        raise ValueError("qty must be > 0")
                    why_sizing = "llm_qty_passthrough"
                    sizing_reject_reason = None
                    _sizing_dbg = {"mode": "llm_qty_passthrough"}
                except Exception:
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=side,
                        rid=str(rid),
                        reason_code="INVALID_LLM_QTY",
                        reason="DECISION",
                        context="strategy_signal_gateway:llm_qty_invalid",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["llm_qty_invalid"],
                        details={"qty": qty_raw},
                    )
                    self._record_blocked_intent(symbol)
                    return
            else:
                try:
                    qty_dec, why_sizing, sizing_reject_reason, _sizing_dbg = self._calculate_position_size(
                        symbol, entry_price_dec, side, sizing_ctx, margin_pct_mult=margin_pct_mult
                    )
                except Exception as e:
                    self.logger.error(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: Sizing error: {e}", exc_info=True)
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=side,
                        rid=str(rid),
                        reason_code="SIZING_ERROR",
                        reason="DECISION",
                        context=f"strategy_signal_gateway:sizing_exception:{type(e).__name__}",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + ["sizing_exception"],
                        details={"error": str(e)},
                    )
                    self._record_blocked_intent(symbol)
                    return
            if qty_dec is None:
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - "
                    f"Sizing blocked ({sizing_reject_reason or 'UNKNOWN'}): {why_sizing}"
                )
                self._record_blocked_intent(symbol)
                return

            position_size_usd = float(qty_dec * entry_price_dec)
            if not self._precheck_exposure_cache(symbol, side, float(position_size_usd)):
                self.logger.info(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Exposure limit exceeded")
                self._record_blocked_intent(symbol)
                return

            # === GATE 5: TTL GATE (features freshness) ===
            # P1-2-FIX: Use signal ts_ms as reference (not cached features)
            signal_ts_ms = pld.get("ts_ms", 0)
            if signal_ts_ms in (None, 0, "0", ""):
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Missing ts_ms in signal"
                )
                self._record_blocked_intent(symbol)
                return

            current_ms = self._clock.now_ms()

            tf_sec_val = int(pld.get("tf_sec") or 0)
            is_bar = tf_sec_val > 0

            if is_bar:
                bar_ttl_ms = tf_sec_val * 1000 * 2
                sys_md = getattr(self.config.system, "market_data", None)
                if sys_md:
                    bar_ttl_ms = float(
                        getattr(sys_md, "bar_ttl_ms", bar_ttl_ms) or bar_ttl_ms)
                ttl_ms = bar_ttl_ms
            else:
                ttl_ms = self.features_ttl_sec * 1000

            signal_age_ms = current_ms - int(signal_ts_ms)

            if signal_age_ms > ttl_ms:
                self.logger.info(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Signal stale "
                    f"(age={signal_age_ms}ms > ttl={ttl_ms}ms, signal_ts={signal_ts_ms})"
                )
                self._record_blocked_intent(symbol)
                return

            # === GATE 6: WARMUP / READINESS (TASK24.B) ===
            if self._warmup_gate_before_trade_intent(
                symbol=symbol,
                rid=rid,
                reduce_only=False,
                context="strategy_signal_gateway:pre_emit",
            ):
                return

            # === ALL GATES PASSED: EMIT TRADE_INTENT_PROPOSED ===
            self.logger.info(
                f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED")

            ts_ms = pld.get("ts_ms")
            if ts_ms in (None, 0, "0", ""):
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Missing ts_ms")
                self._record_blocked_intent(symbol)
                return
            timestamp_ms = int(ts_ms)
            if 0 < timestamp_ms < 1_000_000_000_000:
                timestamp_ms = timestamp_ms * 1000

            if isinstance(why_chain, list):
                why_chain.append(str(why_sizing))

            # === STRATEGY PRIMACY FOR SL/TP (FIX: Silent Fallback Elimination) ===
            # STEP 1: Extract Strategy-provided SL/TP from price_ctx FIRST.
            # If Strategy did the math (e.g., MeanReversion ATR/BB), we MUST respect it.
            strategy_stop_price: str | None = price_ctx.get("stop_price")
            strategy_target_price: str | None = price_ctx.get("target_price")

            # Normalize to string (handle Decimal/float/None)
            if strategy_stop_price is not None:
                strategy_stop_price = str(
                    strategy_stop_price) if strategy_stop_price not in ("", "None") else None
            if strategy_target_price is not None:
                strategy_target_price = str(
                    strategy_target_price) if strategy_target_price not in ("", "None") else None

            def _validate_price_input(val: Any) -> Decimal | None | str:
                if val is None:
                    return None
                try:
                    d = Decimal(str(val))
                    if not d.is_finite() or d < 0:
                        raise ValueError("Non-finite/Negative")
                    return d
                except Exception:
                    return "INVALID"

            stop_valid = _validate_price_input(strategy_stop_price)
            target_valid = _validate_price_input(strategy_target_price)
            if stop_valid == "INVALID" or target_valid == "INVALID":
                invalid_fields = []
                if stop_valid == "INVALID":
                    invalid_fields.append("stop_price")
                if target_valid == "INVALID":
                    invalid_fields.append("target_price")
                self.logger.warning(
                    f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - Invalid price inputs: {invalid_fields}"
                )
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=side,
                    rid=str(rid),
                    reason_code="STRATEGY_INVALID_PRICES",
                    reason="STRATEGY_SIGNAL",
                    context="strategy_signal_gateway:invalid_prices",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []) + ["invalid_prices"],
                    details={
                        "invalid_fields": invalid_fields,
                        "stop_price": strategy_stop_price,
                        "target_price": strategy_target_price,
                    },
                )
                self._record_blocked_intent(symbol)
                return

            # Log Strategy Primacy usage
            if strategy_stop_price or strategy_target_price:
                self.logger.info(
                    f"[{symbol}] STRATEGY_PRIMACY: Using Strategy-provided SL={strategy_stop_price}, TP={strategy_target_price}"
                )
                if isinstance(why_chain, list):
                    why_chain.append(
                        f"strategy_prices:sl={strategy_stop_price},tp={strategy_target_price}")

            # === EP-01.2-INT: EntryPlan Computation (FALLBACK ONLY) ===
            # Extract volatility/liquidity from signal payload (propagated from AuroraHandler)
            volatility_data = pld.get("volatility") or {}
            liquidity_data = pld.get("liquidity") or {}

            atr_value = volatility_data.get("atr_14") if isinstance(
                volatility_data, dict) else None
            atr_ready = volatility_data.get("atr_ready", False) if isinstance(
                volatility_data, dict) else False
            obi_close = liquidity_data.get("obi_close") if isinstance(
                liquidity_data, dict) else None

            # Get EntryPlan config from domains
            ep_cfg = getattr(
                self.config.domains.decision_making, "entry_plan", None)
            ep_enabled = ep_cfg.enabled if ep_cfg else False

            # STEP 2: Initialize with Strategy values (Primacy), EntryPlan is fallback
            stop_price: str | None = strategy_stop_price
            target_price: str | None = strategy_target_price
            entry_plan_trace: dict | None = None

            # STEP 3: Only compute EntryPlan if Strategy did NOT provide prices
            if ep_enabled and (stop_price is None or target_price is None):
                # Build EntryPlanParams from config
                ep_params = EntryPlanParams(
                    atr_period=ep_cfg.atr_period,
                    entry_k_atr=ep_cfg.entry_k_atr,
                    sl_k_atr=ep_cfg.sl_k_atr,
                    tp_k_atr=ep_cfg.tp_k_atr,
                    obi_weight=ep_cfg.obi_weight,
                    obi_mod_clamp_min=ep_cfg.obi_mod_clamp_min,
                    obi_mod_clamp_max=ep_cfg.obi_mod_clamp_max,
                    require_atr=ep_cfg.require_atr,
                    obi_missing_policy=ObiMissingPolicy(
                        ep_cfg.obi_missing_policy),
                )

                # Validate inputs (fail-closed if ATR required but not ready)
                is_valid, error_reason = EntryPlan.validate_inputs(
                    side=side,
                    ref_price=entry_price_dec,
                    atr=atr_value,
                    atr_ready=atr_ready,
                    params=ep_params,
                )

                if not is_valid:
                    self.logger.warning(
                        f"[{symbol}] STRATEGY_SIGNAL_GATEWAY: REJECT - EntryPlan validation failed: {error_reason}"
                    )
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=side,
                        rid=str(rid),
                        reason_code=str(error_reason),
                        reason="ENTRY_PLAN_VALIDATION_FAILED",
                        context="strategy_signal_gateway:entry_plan",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []) + [str(error_reason)],
                        details={"atr_ready": atr_ready,
                                 "atr_value": atr_value},
                    )
                    self._record_blocked_intent(symbol)
                    return

                # Compute EntryPlan
                entry_plan = EntryPlan(ep_params)
                try:
                    ep_result: EntryPlanResult = entry_plan.compute(
                        side=side,
                        ref_price=entry_price_dec,
                        atr=atr_value,
                        obi=obi_close,
                    )
                    # STRATEGY PRIMACY: Only fill in MISSING values from EntryPlan
                    if stop_price is None:
                        stop_price = ep_result.stop_loss_price
                        self.logger.info(
                            f"[{symbol}] EntryPlan FALLBACK SL: {stop_price}")
                    if target_price is None:
                        target_price = ep_result.take_profit_price
                        self.logger.info(
                            f"[{symbol}] EntryPlan FALLBACK TP: {target_price}")

                    entry_plan_trace = {
                        "ref_price": ep_result.ref_price,
                        "atr": ep_result.atr,
                        "obi": ep_result.obi,
                        "obi_multiplier": ep_result.obi_multiplier,
                        "obi_policy_applied": ep_result.obi_policy_applied,
                        "strategy_sl_used": strategy_stop_price is not None,
                        "strategy_tp_used": strategy_target_price is not None,
                    }
                    self.logger.info(
                        f"[{symbol}] EntryPlan: SL={stop_price}, TP={target_price}, "
                        f"OBI_mult={ep_result.obi_multiplier:.3f}, "
                        f"strategy_primacy_sl={strategy_stop_price is not None}, "
                        f"strategy_primacy_tp={strategy_target_price is not None}"
                    )
                    if isinstance(why_chain, list):
                        why_chain.append(
                            f"entry_plan:sl={stop_price},tp={target_price}")
                except Exception as ep_err:
                    self.logger.warning(
                        f"[{symbol}] EntryPlan computation failed: {ep_err}")
                    # STRATEGY PRIMACY: Keep strategy prices even if EntryPlan fails
                    # Only clear if strategy didn't provide AND EntryPlan failed
                    if strategy_stop_price is None:
                        stop_price = None
                    if strategy_target_price is None:
                        target_price = None
                    entry_plan_trace = None

            # Extract TCA/Risk Context from latest_risk (SSOT)
            tca_budget = latest_risk.get("tca_budget") or {}
            max_slippage_bps = int(tca_budget.get(
                "max_slippage_bps", 0)) or None
            max_latency_ms = int(tca_budget.get("max_latency_ms", 0)) or None

            risk_params = latest_risk.get("risk_parameters") or {}
            # We already validated risk_score exists in Gate 1.5, safe to extract now
            # Note: We validated it as 'risk_score_raw' earlier, here we fetch fresh or re-use
            risk_score_val = float(risk_params.get("risk_score", 0.0))

            self._propose_trade_intent(
                symbol=symbol,
                side=side,
                qty=decimal.Decimal(str(qty_dec)),
                price=decimal.Decimal(str(entry_price_dec)),
                why_chain=why_chain if isinstance(why_chain, list) else [
                    str(why_chain)],
                rid=rid,
                reduce_only=False,
                strategy_id=str(strategy_id),
                decision_ts_ms=timestamp_ms,
                stop_price=stop_price,
                target_price=target_price,
                entry_plan_trace=entry_plan_trace,
                # EP-01.3-INT: Pass tf_sec for pending entry TTL
                tf_sec=tf_sec,
                # TCA & Risk Context (Degradation Report Point 3)
                max_slippage_bps=max_slippage_bps,
                max_latency_ms=max_latency_ms,
                risk_score=risk_score_val,
                strategy_trace={
                    "md_amr": md_amr_trace_norm} if md_amr_trace_norm is not None else None,
                entry_order_type_override=llm_order_type if strategy_id_s == "llm_microstructure" else None,
                entry_tif_override=llm_order_tif if strategy_id_s == "llm_microstructure" else None,
            )

            # Update QoS state for successful decision only if QoS is enabled for this strategy.
            if qos_enabled:
                self._update_qos_state(symbol, strategy_id)

        except ConfigContractError as e:
            # TASK 17: Central Interception Point for Config Contract Violations
            # 1. Normalize Reason
            reason = normalize_config_error(e)

            # 2. Map to NRR
            nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_MISSING
            if "CFG_INVALID" in reason:
                nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_INVALID

            # 3. Metric & Log
            caught_symbol = e.symbol or symbol
            inc_config_contract_violation(
                path=e.path or "unknown", symbol=caught_symbol or "unknown")
            self.logger.critical(
                f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")

            # 4. Record blocked intent
            if caught_symbol:
                self._record_blocked_intent(caught_symbol)

            # 5. Emit Rejection Event (No Ghosts)
            # TASK-CFG-REJECT-INTEGRATE-01
            self._emit_trade_intent_rejected(
                symbol=caught_symbol or "unknown",
                strategy_id=str(strategy_id),
                side=side,
                rid=str(rid),
                reason_code=nrr_code,
                reason=reason,
                context="strategy_signal_gateway:config_contract_violation",
                details={"path": e.path, "why": e.why,
                         "stage": "strategy_signal_gateway"},
                why_chain=why_chain or ["config_contract_violation"],
            )
            return

        except Exception as e:
            self.logger.error(
                f"STRATEGY_SIGNAL_GATEWAY error: {e}", exc_info=True)

    def _qos_enabled_for_strategy(self, strategy_id: str) -> bool:
        """Return True if QoS should be applied for this strategy_id in the strategy gateway."""
        allowlist = getattr(self, "_qos_apply_to_strategies", set()) or set()
        if not allowlist:
            return True
        return str(strategy_id) in allowlist

    def _qos_allow(
        self, symbol: str, strategy_id: str = "aurora", is_exposure_block: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Check if decision is allowed based on QoS rules (PACK EXP-4).
        Partitioned by strategy_id (v7) to prevent cross-strategy rate-limiting.

        Args:
            symbol: Trading symbol
            strategy_id: Strategy identifier for state partitioning
            is_exposure_block: Whether this check is due to exposure block

        Returns:
            Tuple of (allowed: bool, reject_reason: Optional[str])
        """
        current_time = self._clock.now_sec()
        # auto-creates via defaultdict
        strat_state = self._qos_state[strategy_id]

        # Check exposure block cooldown (only for exposure-related checks)
        if is_exposure_block:
            last_exposure_block: float = float(
                strat_state.get("last_exposure_block", 0.0))
            time_since_last_block = current_time - last_exposure_block
            if time_since_last_block < self.qos_exposure_block_cooldown_sec:
                remaining = self.qos_exposure_block_cooldown_sec - time_since_last_block
                reject_reason = (
                    f"exposure_block_cooldown_active_{remaining:.1f}s_remaining"
                )
                self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
                return False, NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

        # Check symbol cooldown (prevents rapid-fire decisions for same symbol)
        symbol_cooldowns: dict[str, Any] = strat_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        time_since_last_decision = current_time - last_decision
        symbol_cooldown_limit = self._get_symbol_cooldown(symbol, strategy_id)
        if time_since_last_decision < symbol_cooldown_limit:
            remaining = symbol_cooldown_limit - time_since_last_decision
            reject_reason = f"symbol_cooldown_active_{remaining:.1f}s_remaining_limit={symbol_cooldown_limit}s"
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        # Check rate limit (intents per minute per symbol) - separate from cooldown
        symbol_intent_counts: dict[str, Any] = strat_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(
            symbol, {"count": 0, "window_start": current_time})
        window_start = intent_data.get("window_start", current_time)
        window_elapsed = current_time - window_start

        # Reset window if more than a minute has passed
        if window_elapsed >= 60:
            intent_data["count"] = 0
            intent_data["window_start"] = current_time

        if intent_data.get("count", 0) >= self.qos_max_intents_per_minute_per_symbol:
            reject_reason = (
                f"rate_limit_exceeded_{intent_data['count']}_intents_in_window"
            )
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        return True, None

    def _update_symbol_cooldown(self, symbol: str, strategy_id: str = "aurora") -> None:
        """Update cooldown timestamp for symbol (prevents rapid-fire decisions).

        T2B-08: Uses injected Clock for deterministic testing.
        """
        current_time = self._clock.now_sec()
        strat_state = self._qos_state[strategy_id]
        if "symbol_cooldowns" not in strat_state:
            strat_state["symbol_cooldowns"] = {}
        strat_state["symbol_cooldowns"][symbol] = current_time
        self.logger.debug(
            f"[{symbol}] QoS cooldown updated: ts={current_time} strategy={strategy_id}")

    def _update_intent_count(self, symbol: str, strategy_id: str = "aurora") -> None:
        """Update intent count for rate limiting (partitioned by strategy_id)."""
        strat_state = self._qos_state[strategy_id]
        if "symbol_intent_counts" not in strat_state:
            strat_state["symbol_intent_counts"] = {}
        symbol_intent_counts = strat_state["symbol_intent_counts"]

        if symbol not in symbol_intent_counts:
            # T2B-08: Use Clock for rate-limit window start
            symbol_intent_counts[symbol] = {
                "count": 0, "window_start": self._clock.now_sec()}
        intent_data = symbol_intent_counts[symbol]
        intent_data["count"] = intent_data.get("count", 0) + 1
        self.logger.debug(
            f"[{symbol}] QoS intent count updated: count={intent_data['count']} strategy={strategy_id}"
        )

    # [DELETED] _check_qos_rules (Legacy/Unreachable code removed in P2-Lite Audit)

    def _calculate_next_allowed_time(self, symbol: str, strategy_id: str = "aurora") -> int:
        """Calculate next allowed timestamp for symbol based on QoS rules.

        T2B-08: Uses injected Clock for deterministic testing.
        QOS-SPLIT-BRAIN-FIX: Now strategy-aware (reads from correct partition).

        Args:
            symbol: Trading symbol
            strategy_id: Strategy identifier for state partitioning
        """
        current_time = self._clock.now_sec()
        next_allowed = current_time

        # QOS-SPLIT-BRAIN-FIX: Read from strategy-specific partition
        strat_state = self._qos_state[strategy_id]

        # Check symbol cooldown (uses per-symbol resolver)
        symbol_cooldowns: dict[str, Any] = strat_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        cooldown_duration = self._get_symbol_cooldown(symbol, strategy_id)

        cooldown_end: float = last_decision + cooldown_duration
        next_allowed = max(next_allowed, cooldown_end)

        # Check rate limit window
        symbol_intent_counts: dict[str, Any] = strat_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(
            symbol, {"count": 0, "window_start": current_time})
        window_start = float(intent_data.get("window_start", current_time))
        window_end: float = window_start + 60
        intent_count: int = int(intent_data.get("count", 0))
        if intent_count >= self.qos_max_intents_per_minute_per_symbol:
            next_allowed = max(next_allowed, window_end)

        return int(next_allowed * 1000)  # Convert to milliseconds

    def _update_qos_state(self, symbol: str, strategy_id: str = "aurora") -> None:
        """Update QoS state after making a decision.

        T2B-08: Uses injected Clock for deterministic testing.

        Args:
            symbol: Trading symbol
            strategy_id: Strategy ID for partitioning (default: aurora for legacy path)
        """
        current_time = self._clock.now_sec()

        # Get strategy-partitioned state (auto-initialize if missing)
        strategy_state = self._qos_state[strategy_id]

        # Update symbol cooldown
        strategy_state["symbol_cooldowns"][symbol] = current_time

        # Update rate limit counters
        symbol_intent_counts = strategy_state["symbol_intent_counts"]
        if symbol not in symbol_intent_counts:
            symbol_intent_counts[symbol] = {
                "count": 0, "window_start": current_time}

        intent_data: dict[str, Any] = symbol_intent_counts[symbol]
        window_start: float = float(
            intent_data.get("window_start", current_time))
        window_end: float = window_start + 60

        if current_time >= window_end:
            # Reset window
            intent_data["window_start"] = current_time
            intent_data["count"] = 1
        else:
            intent_data["count"] = intent_data.get("count", 0) + 1

        self.logger.debug(
            f"[{symbol}] QoS state updated ({strategy_id}): cooldown={current_time}, intents={intent_data['count']}")

    # TODO: [P2-REFACTOR] EXPOSURE BLOCK IS NOT WIRED!
    # This method is effectively dead code (no callers) and contains a bug (Split-Brain).
    # It writes to flat 'last_exposure_block' which is NEVER read by _qos_allow (which reads partitioned).
    # ACTION: Wire this to a relevant event (e.g. GUARD_REJECTION) AND refactor to use QoSState.
    def _handle_exposure_block(self, symbol: str) -> None:
        """Handle exposure block event by updating QoS state.

        T2B-08: Uses injected Clock for deterministic testing.
        """
        current_time = self._clock.now_sec()
        self._qos_state["last_exposure_block"] = current_time
        self.logger.warning(
            f"[{symbol}] Exposure block recorded at {current_time} (WARNING: This may have no effect due to Split-Brain bug)")

    # =========================================================================
    # Phase 3: Shadow Mode - Kernel Comparison
    # =========================================================================

    def _shadow_compare_kernel(
        self,
        symbol: str,
        *,
        legacy_score: decimal.Decimal,
        legacy_side: str,
        legacy_thr_buy: decimal.Decimal,
        legacy_thr_sell: decimal.Decimal,
        features: Dict[str, Any],
        warmup_readiness: Dict[str, bool],
        price: decimal.Decimal,
        signal_weights: Dict[str, float],
        feature_neutrals: Dict[str, float],
        essential_features: List[str],
        base_threshold: decimal.Decimal,
        regime_name: Optional[str],
        regime_thresholds: Dict[str, float],
        buy_count: int,
        sell_count: int,
    ) -> None:
        """
        Shadow mode: compare legacy scoring with kernel (no side effects).

        Logs divergences for validation before switching to kernel.
        """
        # Check if shadow mode is enabled
        aurora_cfg = getattr(self.config.strategies, "aurora", None)
        if not aurora_cfg or not getattr(aurora_cfg, "shadow_mode_enabled", False):
            return

        try:
            # Build side bias state
            side_bias_state = SideBiasState(
                buy_count=buy_count,
                sell_count=sell_count,
                window_sec=aurora_cfg.decision.side_bias_window_sec or 420,
                target_ratio=aurora_cfg.decision.side_bias_target_ratio or 0.72,
                penalty_factor=aurora_cfg.decision.side_bias_penalty_factor or 0.25,
                min_intents=aurora_cfg.decision.side_bias_min_intents or 18,
            )

            # Get direction strength config
            ds_cfg = getattr(aurora_cfg.decision,
                             "direction_strength_scoring", None)
            direction_strength_cfg = {
                "directional_features": list(ds_cfg.directional_features) if ds_cfg else [],
                "strength_features": list(ds_cfg.strength_features) if ds_cfg else [],
                "strength_alpha": ds_cfg.strength_alpha if ds_cfg else 0.5,
                "strength_cap": ds_cfg.strength_cap if ds_cfg else 1.5,
            }

            signals_cfg = getattr(aurora_cfg.decision, "signals", None)
            delta_price_cap_pct = decimal.Decimal(
                str(signals_cfg.delta_price_cap_pct)
            ) if signals_cfg and signals_cfg.delta_price_cap_pct else decimal.Decimal("0.005")
            normalize_mode = str(
                getattr(signals_cfg, "normalize_signals_mode", "signed_v2"))

            # Call kernel
            kernel_result = AuroraScoringKernel.compute(
                symbol=symbol,
                features=features,
                warmup_readiness=warmup_readiness,
                price=price,
                signal_weights=signal_weights,
                feature_neutrals=feature_neutrals,
                essential_features=essential_features,
                base_threshold=base_threshold,
                regime_name=regime_name,
                regime_thresholds=regime_thresholds,
                side_bias_state=side_bias_state,
                direction_strength_cfg=direction_strength_cfg,
                delta_price_cap_pct=delta_price_cap_pct,
                normalize_mode=normalize_mode,
            )

            # Compare results
            score_diff = abs(float(legacy_score) - float(kernel_result.score))
            thr_buy_diff = abs(float(legacy_thr_buy) -
                               float(kernel_result.thr_buy))
            thr_sell_diff = abs(float(legacy_thr_sell) -
                                float(kernel_result.thr_sell))
            side_match = legacy_side.lower() == kernel_result.side.lower()

            # Log divergence if significant
            threshold = 0.001  # 0.1% tolerance
            if score_diff > threshold or thr_buy_diff > threshold or thr_sell_diff > threshold or not side_match:
                self.logger.warning(
                    f"[{symbol}] SHADOW_DIVERGENCE: "
                    f"legacy_score={float(legacy_score):.4f} vs kernel={float(kernel_result.score):.4f} (diff={score_diff:.6f}) | "
                    f"legacy_side={legacy_side} vs kernel={kernel_result.side} (match={side_match}) | "
                    f"thr_buy_diff={thr_buy_diff:.6f} thr_sell_diff={thr_sell_diff:.6f}"
                )
            else:
                self.logger.debug(
                    f"[{symbol}] SHADOW_MATCH: score={float(legacy_score):.4f}, side={legacy_side}")

        except Exception as e:
            self.logger.error(f"[{symbol}] SHADOW_ERROR: {e}")

    # =========================================================================
    # Phase 0: Per-Instrument Aurora Configuration Helpers
    # =========================================================================

    # CFG-DOMAINS-STEP-02: _get_qos_config() REMOVED
    # QoS config now accessed via DomainConfigResolver in __init__
    # No fallback logic needed - fail-closed via resolver

    def _get_position_sizing_config(self):
        """
        Get position sizing configuration from domains.yaml. SSOT - no fallbacks.

        Returns:
            Config object with min_position_size_usd, liquidity_based_cap_usd

        Raises:
            ValueError: If config is missing required position_sizing section
        """
        # Try domains config (preferred)
        if hasattr(self.config, 'domains') and hasattr(self.config.domains, 'decision_making'):
            dm_cfg = self.config.domains.decision_making
            if hasattr(dm_cfg, 'position_sizing') and dm_cfg.position_sizing is not None:
                return dm_cfg.position_sizing

        # Direct Pydantic access (fail-closed)
        # If missing → AttributeError → crash at startup (intentional)
        return self.config.domains.decision_making.position_sizing

    def _is_strategy_assigned(self, symbol: str, strategy_id: str) -> bool:
        """
        Check if a specific strategy is assigned to a symbol in strategies_registry.

        STRATEGY-AWARE-GATES-FIX: This is the SSOT for strategy activation.
        Used to determine whether strategy-specific gates (warmup, regime, etc.) should apply.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            strategy_id: Strategy identifier (e.g., 'aurora', 'other')

        Returns:
            True if strategy_id is in assignments for symbol, False otherwise.
        """
        if not self.strategies_registry:
            # No registry → backward compat: assume aurora for all
            return strategy_id == "aurora"

        assignments = self.strategies_registry.assignments.get(symbol, [])
        return strategy_id in assignments

    def _get_aurora_instrument_cfg(self, symbol: str) -> Optional[AuroraInstrumentConfig]:
        """
        Get per-instrument Aurora configuration for a symbol.

        Fallback chain:
        1. config.strategies.aurora.assets[SYMBOL] (SSOT: strategies/aurora.yaml::aurora.assets)
        2. None (caller falls back to global strategies.aurora.decision.*)

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            AuroraInstrumentConfig or None if not configured
        """
        if not self.config:
            return None

        aurora = getattr(self.config.strategies, "aurora", None)
        if aurora is None:
            return None

        return aurora.assets.get(symbol)

    def _check_strategy_arbitration(
        self,
        symbol: str,
        strategy_id: str,
        *,
        ts_ms: int | None = None,
        commit: bool = False,
    ) -> Dict[str, Any]:
        """
        Check if strategy is allowed to generate intent for symbol based on arbitration rules.

        CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Implements deterministic arbitration.
        DM-CRITICAL-PATCHES-02: Uses dedicated signal buffer with priority ranks.

        Args:
            symbol: Trading pair symbol
            strategy_id: Strategy identifier (e.g., "aurora")
            ts_ms: Signal timestamp (monotonic)
            commit: If True, update buffer on success

        Returns:
            Dict with keys:
            - allowed (bool): Whether strategy can proceed
            - reason (str): If blocked, why (≤80 chars)
        """
        symbol_u = str(symbol).upper()
        strategy_u = str(strategy_id)

        # External LLM strategy has dedicated orchestration policy and does not require
        # registry assignment/priority rank to pass arbitration.
        if strategy_u == "llm_microstructure":
            llm_cfg = getattr(getattr(self.config, "trading",
                              None), "llm_orchestration", None)
            mode = str(getattr(llm_cfg, "mode", "baseline")).lower()
            llm_symbols = [str(s).upper() for s in (
                getattr(llm_cfg, "symbols_llm", []) or [])]
            allow = [str(s).upper()
                     for s in (getattr(llm_cfg, "allowlist_symbols", []) or [])]
            require_telemetry = bool(
                getattr(llm_cfg, "require_telemetry", False))

            if mode == "baseline":
                return {"allowed": False, "reason": "ARBITRATION_REJECT:llm_mode_baseline"}
            if llm_symbols and symbol_u not in llm_symbols:
                return {"allowed": False, "reason": "ARBITRATION_REJECT:llm_symbol_not_owned"}
            if allow and symbol_u not in allow:
                return {"allowed": False, "reason": "ARBITRATION_REJECT:llm_symbol_not_allowlisted"}
            if require_telemetry:
                shadow_cfg = getattr(
                    getattr(self.config, "domains", None), "shadow_telemetry", None)
                if not (shadow_cfg and bool(getattr(shadow_cfg, "enabled", False))):
                    return {"allowed": False, "reason": "ARBITRATION_REJECT:llm_telemetry_required"}
            return {"allowed": True, "reason": ""}

        llm_cfg = getattr(getattr(self.config, "trading",
                          None), "llm_orchestration", None)
        llm_symbols = [str(s).upper()
                       for s in (getattr(llm_cfg, "symbols_llm", []) or [])]
        if llm_symbols and symbol_u in llm_symbols:
            return {"allowed": False, "reason": "ARBITRATION_REJECT:symbol_owned_by_llm"}

        # If no strategies registry, allow (backward compat)
        if not self.strategies_registry:
            return {"allowed": True, "reason": ""}

        # Get assigned strategies for this symbol
        assignments = self.strategies_registry.assignments[symbol] if symbol in self.strategies_registry.assignments else [
        ]

        # If symbol not in registry, block (fail-closed)
        if not assignments:
            self.logger.warning(
                f"[{symbol}] ARBITRATION: symbol not in registry. Assignments: {list(self.strategies_registry.assignments.keys())}")
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:symbol_not_in_registry"
            }

        # If strategy not assigned to symbol, block
        if strategy_id not in assignments:
            self.logger.warning(
                f"[{symbol}] ARBITRATION: strategy {strategy_id!r} not in assignments {assignments!r}")
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:strategy_not_assigned_to_symbol"
            }

        # If only one strategy assigned, always allow
        if len(assignments) == 1:
            return {"allowed": True, "reason": ""}

        # Multi-strategy case: priority arbitration with dedicated buffer
        arb = self.strategies_registry.arbitration

        if arb.mode != "priority":
            # Unknown arbitration mode - fail-closed (defense-in-depth)
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:unknown_mode_{arb.mode}"[:80]
            }

        # DM-CRITICAL-PATCHES-02: Fail-closed if strategy has no priority rank
        rank = arb.priority.get(strategy_id)
        if rank is None:
            self.logger.error(
                f"[{symbol}] ARBITRATION: strategy {strategy_id!r} missing priority rank (fail-closed DROP)"
            )
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:missing_priority:{strategy_id}"[:80],
            }

        # Validate all assigned strategies have priorities (defense-in-depth)
        for strat in assignments:
            if strat not in arb.priority:
                return {
                    "allowed": False,
                    "reason": f"ARBITRATION_REJECT:missing_priority:{strat}"[:80],
                }

        # If no decision clock is provided, do NOT permanently suppress a strategy.
        if ts_ms is None:
            return {"allowed": True, "reason": ""}

        try:
            window_ms = int(arb.window_ms)
        except Exception:
            return {"allowed": False, "reason": "ARBITRATION_REJECT:invalid_window_ms"[:80]}
        if window_ms <= 0:
            return {"allowed": False, "reason": "ARBITRATION_REJECT:invalid_window_ms"[:80]}

        # DM-CRITICAL-PATCHES-02: Dedicated signal buffer arbitration
        now_ms = int(ts_ms)
        existing = self._arb_signal_buffer.get(symbol)

        if existing is not None:
            last_ts, last_sid, last_rank = existing
            delta_ms = now_ms - last_ts

            # Within window: compare ranks
            if delta_ms <= window_ms:
                if rank < last_rank:
                    # Higher priority (lower rank) wins - overwrite buffer
                    self.logger.info(
                        f"[{symbol}] ARBITRATION: {strategy_id}(rank={rank}) overrides "
                        f"{last_sid}(rank={last_rank}) delta={delta_ms}ms window={window_ms}ms"
                    )
                    if commit:
                        self._arb_signal_buffer[symbol] = (
                            now_ms, strategy_id, rank)
                        self._arb_window_winner[symbol] = (
                            now_ms // window_ms, strategy_id)
                    return {"allowed": True, "reason": ""}
                elif rank >= last_rank:
                    # Lower or equal priority - DROP
                    self.logger.info(
                        f"[{symbol}] ARBITRATION: dropped {strategy_id}(rank={rank}) - "
                        f"window claimed by {last_sid}(rank={last_rank}) delta={delta_ms}ms"
                    )
                    return {
                        "allowed": False,
                        "reason": f"{arb.logging.rejected_why_prefix}:lower_priority_vs_{last_sid}"[:80],
                    }
            # Window expired - allow and update buffer

        # No existing entry or window expired: allow and commit
        if commit:
            self._arb_signal_buffer[symbol] = (now_ms, strategy_id, rank)
            self._arb_window_winner[symbol] = (
                now_ms // window_ms, strategy_id)
        return {"allowed": True, "reason": ""}

    def _get_symbol_cooldown(self, symbol: str, strategy_id: str = "aurora") -> int:
        """
        Get per-symbol cooldown in seconds (partitioned by strategy_id).

        Fallback chain:
        1. strategies.<strategy_id>.assets.<SYMBOL>.cooldown_sec (per-instrument config)
        2. self._default_symbol_cooldown_sec (safe default = 3s)

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            strategy_id: Strategy identifier for config lookup

        Returns:
            Cooldown duration in seconds
        """
        # 1. Try per-instrument config (strategy-specific)
        if strategy_id == "aurora":
            instr_cfg = self._get_aurora_instrument_cfg(symbol)
            if instr_cfg is not None:
                cooldown = aget(instr_cfg, "cooldown_sec", None)
                if cooldown is not None:
                    return int(cooldown)
        # TODO: Add lookup for other strategies (via registry)

        # 2. Fallback to safe default
        return self._default_symbol_cooldown_sec

    def _get_param(self, symbol: str, param: str, default: Any) -> Any:
        """
        Get configuration parameter with per-instrument override support.

        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.<param>
        2. strategies.aurora.decision.<param> (global)
        3. default value

        Args:
            symbol: Trading pair symbol
            param: Parameter name (e.g., 'signal_weights', 'side_bias')
            default: Default value if not found

        Returns:
            Parameter value from per-instrument or global config
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            value = aget(instr_cfg, param, None)
            if value is not None:
                return value

        # 2. Fallback to global strategies.aurora.decision.* (Strict)
        global_value = aget(
            self.config.strategies.aurora.decision, param, default)
        return global_value if global_value is not None else default

    def _get_side_bias_params(self, symbol: str) -> tuple:
        """
        Get side_bias parameters with per-instrument override.

        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.side_bias.* (per-instrument)
        2. strategies.aurora.decision.side_bias_* (global SSOT)

        FAIL-CLOSED: ValueError if global config missing.

        Returns:
            (penalty_factor, window_sec, target_ratio, min_intents)
        """
        dm = self.config.strategies.aurora.decision
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        sb = aget(instr_cfg, "side_bias", None)

        def get_val(item_key, global_attr, default=None):
            val = aget(sb, item_key, None) if sb else None
            if val is not None:
                return val
            glob = getattr(dm, global_attr, None)
            return glob if glob is not None else default

        penalty = get_val("penalty_factor", "side_bias_penalty_factor")
        window = get_val("window_sec", "side_bias_window_sec")
        target = get_val("target_ratio", "side_bias_target_ratio")
        min_intents = get_val("min_intents", "side_bias_min_intents")

        # 2. SSOT Validation (fail-closed)
        if penalty is None:
            raise ValueError(
                f"side_bias_penalty_factor is required for {symbol}")
        if window is None:
            raise ValueError(f"side_bias_window_sec is required for {symbol}")
        if target is None:
            raise ValueError(
                f"side_bias_target_ratio is required for {symbol}")
        if min_intents is None:
            raise ValueError(f"side_bias_min_intents is required for {symbol}")

        return (penalty, window, target, min_intents)

    def _get_regime_thresholds(self, symbol: str) -> dict:
        """
        Get regime threshold multipliers with per-instrument override.

        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.regime_thresholds
        2. strategies.aurora.decision.regime_threshold_multipliers (global)
        3. empty dict

        Returns:
            Dict mapping regime names to threshold multipliers
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            thresholds = aget(instr_cfg, "regime_thresholds", None)
            if thresholds is not None:
                return thresholds

        # 2. Fallback to global (Strict Object)
        dm = self.config.strategies.aurora.decision
        global_thresholds = dm.regime_threshold_multipliers if dm.regime_threshold_multipliers is not None else {}
        return global_thresholds

    def _get_signal_threshold(self, symbol: str) -> decimal.Decimal:
        """
        Get signal threshold with per-instrument override (Phase 3+).

        Fallback chain:
        1. strategies.aurora.assets.<SYMBOL>.signal_threshold (if enabled=True)
        2. strategies.aurora.decision.signal_threshold (global - REQUIRED field)

        Returns:
            Signal threshold as Decimal

        Raises:
            AttributeError: If strategies.aurora.decision.signal_threshold missing (fail-closed)
        """
        # 1. Try per-instrument config (Phase 3+)
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            st_cfg = aget(instr_cfg, "signal_threshold", None)
            if st_cfg is not None and st_cfg.enabled:
                if st_cfg.value is not None:
                    return decimal.Decimal(str(st_cfg.value))

        # 2. Direct Pydantic access (fail-closed: missing field → AttributeError)
        decision_config = self.config.strategies.aurora.decision
        return decimal.Decimal(str(decision_config.signal_threshold))

    def _get_flip_config(self, symbol: str) -> Tuple[bool, float]:
        """Get flip orchestration config for symbol (STRICT - no defaults).

        Hierarchy:
        1. Global killswitch OFF → (False, 1.0)
        2. Per-symbol config from instruments.yaml (REQUIRED)

        Raises:
            ConfigContractError: if per-symbol flip config is missing for an active symbol.

        Returns:
            Tuple of (flip_enabled: bool, hysteresis_mult: float)
        """
        # 1. Global killswitch (fast path)
        if not self.flip_global_enabled:
            return (False, 1.0)

        # 2. Per-symbol config (REQUIRED)
        instr = self.config.instruments.get(symbol)
        if not instr:
            # Should be unreachable for active symbols if config validation passes,
            # but critical for runtime safety.
            raise ConfigContractError(
                path=f"instruments.{symbol}",
                why=f"Missing instruments config for active symbol {symbol}"
            )

        # Pydantic ensures instr.flip is present and valid if the model is loaded correctly.
        # But we double-check for absolute safety.
        if not instr.flip:
            raise ConfigContractError(
                path=f"instruments.{symbol}.flip",
                why=f"Missing REQUIRED flip config for symbol {symbol}. Add flip.enabled + flip.hysteresis_mult."
            )

        return (
            bool(instr.flip.enabled),
            max(1.0, float(instr.flip.hysteresis_mult)),
        )

    def on_features(self, event: Message) -> None:
        try:
            try:
                if isinstance(event.pld, dict):
                    symbol = event.pld["symbol"] if "symbol" in event.pld else "unknown"
                elif hasattr(event, 'pld') and event.pld:
                    symbol = event.pld.symbol if hasattr(
                        event.pld, 'symbol') else "unknown"
                else:
                    symbol = "unknown"
            except (AttributeError, TypeError):
                symbol = "unknown"

            # LEGACY-02-INT (bar-only law): ignore tick-level feature events (tf_sec missing/0)
            tf_sec = None
            try:
                if isinstance(event.pld, dict):
                    tf_sec = event.pld.get("tf_sec")
            except Exception:
                tf_sec = None
            if tf_sec is not None and int(tf_sec or 0) <= 0:
                # Throttle WAL spam: record at most once per symbol per 5 minutes.
                try:
                    now_ms = self._clock.now_ms()
                except Exception:
                    now_ms = self._clock.now_ms()
                state = self.symbol_states[symbol]
                last_ms = int(
                    state.get("_tick_features_reject_last_ts_ms", 0) or 0)
                if (now_ms - last_ms) >= 300_000:
                    state["_tick_features_reject_last_ts_ms"] = now_ms
                    try:
                        write_trade_intent_rejected(
                            symbol=symbol,
                            tf_sec=int(
                                tf_sec or 0) if tf_sec is not None else None,
                            reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                            stage="DECISION",
                            why="Ignoring tick-level EVT:FEATURES_CALCULATED (bar-only strategies)",
                            src="decision_making",
                            ts_ms=now_ms,
                            rid=aget(event, "rid", None),
                            context="decision_making:on_features",
                        )
                    except Exception:
                        pass
                return

            self.logger.debug(
                f"on_features() accepted for {symbol} tf_sec={tf_sec}")
            # Ensure per-symbol state exists (fail-safe for early events)
            if symbol not in self.symbol_states:
                self.symbol_states[symbol] = {}

            self.symbol_states[symbol]["features"] = event.pld
            # BAR-TTL-REFORM-01: Inject reception time for "received" mode TTL checks
            self.symbol_states[symbol]["features"]["_received_ts"] = self._clock.now_ms(
            )

            # Commit 5: Clear risk-skew until-refresh state on data refresh
            try:
                guard = self.symbol_states[symbol].get("risk_skew_guard") or {}
                if guard.get("until_refresh"):
                    self.symbol_states[symbol]["risk_skew_guard"] = {
                        "defer_count": 0,
                        "window_start_ms": self._clock.now_ms(),
                        "until_refresh": False,
                    }
                    self.logger.info(
                        f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on features refresh")
            except Exception:
                pass

            # Update per-symbol regime cache if available
            # NOTE: Regime + regime warmup are owned by RegimeDetector only (EVT:REGIME_DETECTED).
            # FeatureEngineering warmup must not be treated as RegimeDetector warmup.

            # Define feats for alpha calculation
            try:
                if isinstance(event.pld, dict):
                    feats = (event.pld or {}).get("features") or {}
                elif hasattr(event, 'pld') and event.pld:
                    feats = event.pld.features if hasattr(
                        event.pld, 'features') else {}
                else:
                    feats = {}
            except (AttributeError, TypeError):
                feats = {}

            # DM-DIR-FORENSIC-01: Capture delta_price history for trend inference.
            try:
                dp_raw = feats.get("delta_price")
                if dp_raw not in (None, ""):
                    dp_val = float(dp_raw)
                else:
                    dp_val = None
            except Exception:
                dp_val = None

            if dp_val is not None:
                hist = self.symbol_states[symbol].get("_delta_price_hist")
                if not isinstance(hist, deque):
                    hist = deque(maxlen=20)
                    self.symbol_states[symbol]["_delta_price_hist"] = hist
                hist.append(dp_val)
                self.symbol_states[symbol]["_last_delta_price"] = dp_val

            self.dlog.write(
                "FEATURES_RX",
                aget(event, "rid", None),
                {"symbol": symbol, "keys": list(feats.keys())},
            )

            # Calculate alpha scores if alpha models are available
            if self.alpha_registry and feats:
                try:
                    alpha_scores = self.alpha_registry.calculate_all_alpha(
                        symbol, {"current_price": feats.get("price")}, feats
                    )
                    if alpha_scores:
                        # Extract event context for unified payload
                        _pld = event.pld if isinstance(event.pld, dict) else {}
                        _tf_sec = _pld.get("tf_sec", 300)
                        _bar_close_ts = _pld.get("bar_close_ts", 0)
                        _ts_ms = self._clock.now_ms()

                        # Emit one event per score (unified schema)
                        for score in alpha_scores:
                            alpha_payload = {
                                "symbol": symbol,
                                "ts_ms": _ts_ms,
                                "tf_sec": _tf_sec,
                                "bar_close_ts": _bar_close_ts,
                                "provider_id": "dm_inline",
                                "model_name": score.model_name,
                                "score": float(score.score),
                                "confidence": float(score.confidence),
                                "threshold": 0.1,
                                "shadow": False,
                                "signal_id": f"dm_{symbol}_{score.model_name}_{_ts_ms}",
                                "features_used": score.features_used,
                                "why": score.why[:10],
                            }
                            self.fsm.emit(
                                "EVT:ALPHA_SCORE_CALCULATED",
                                payload=alpha_payload,
                                why=f"alpha_score:{score.model_name}",
                                data_ref=[f"model_{score.model_name}"],
                            )

                        # VERIFY-ALPHA-CAPTURE: Write alpha scores to WAL for traceability
                        try:
                            from decimal import Decimal as Dec
                            from datetime import datetime as dt

                            def json_safe_value(v):
                                if isinstance(v, Dec):
                                    return float(v)
                                elif isinstance(v, dt):
                                    return v.isoformat()
                                elif isinstance(v, dict):
                                    return {k: json_safe_value(val) for k, val in v.items()}
                                elif isinstance(v, (list, tuple)):
                                    return [json_safe_value(item) for item in v]
                                return v

                            def json_safe_dict(score):
                                d = score.dict()
                                return {k: json_safe_value(v) for k, v in d.items()}

                            for score in alpha_scores:
                                wal_record = {
                                    "op": "EVT",
                                    "verb": "ALPHA_SCORE_CALCULATED",
                                    "symbol": symbol,
                                    "provider_id": "dm_inline",
                                    "model_name": score.model_name,
                                    "score": float(score.score),
                                    "confidence": float(score.confidence),
                                    "ts_ms": _ts_ms,
                                    "why": "alpha_calculation",
                                }
                                wal.append(wal_record)
                        except Exception as wal_e:
                            self.logger.warning(
                                f"Failed to write alpha scores to WAL: {wal_e}")

                        self.logger.info(
                            f"✅ Alpha scores calculated for {symbol}: {len(alpha_scores)} models")
                    else:
                        self.logger.debug(
                            f"No alpha scores calculated for {symbol} - missing required features")
                except ConfigContractError:
                    raise  # Propagate up to main catcher
                except Exception as e:
                    self.logger.error(
                        f"Error calculating alpha scores for {symbol}: {e}")
                    # Continue with normal flow - alpha calculation failure shouldn't block trading
                    # UNLESS it was a ConfigContractError (handled above)

            # Fallback trigger: REMOVED per P0-6 Safety Audit
            # Dangerous bypass of orchestration checks.
            # Decision trigger is now handled exclusively via _check_and_trigger_decision_for_symbol
            pass

        except ConfigContractError as e:
            # TASK 17: Central Interception Point
            reason = normalize_config_error(e)
            caught_symbol = e.symbol or symbol

            # Map to NRR
            nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_MISSING
            if "CFG_INVALID" in reason:
                nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_INVALID

            inc_config_contract_violation(
                path=e.path or "unknown", symbol=caught_symbol or "unknown")
            self.logger.critical(
                f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            if caught_symbol:
                self._record_blocked_intent(caught_symbol)

            # Emit DECISION_BLOCKED (Option 4B: Additive Health Event)
            # Semantically distinct from TRADE_INTENT_REJECTED because no intent was formed yet.
            try:
                # Use Schema to ensure contract compliance
                payload_obj = DecisionBlockedPayload(
                    symbol=caught_symbol or "unknown",
                    reason=reason,
                    reason_code=nrr_code,
                    path=str(e.path),
                    why=str(e.why),
                    stage="on_features",
                    ts_ms=self._clock.now_ms(),
                )
                self.fsm.emit("EVT:DECISION_BLOCKED", payload_obj.model_dump(
                ), why=f"decision_blocked:{nrr_code}")
                # Metric
                inc_decision_blocked(stage="on_features", reason_code=nrr_code)
            except Exception as ex:
                self.logger.error(f"Failed to emit DECISION_BLOCKED: {ex}")

            return

    def on_risk(self, event: Message) -> None:
        try:
            if isinstance(event.pld, dict):
                symbol = event.pld["symbol"] if "symbol" in event.pld else "unknown"
            elif hasattr(event, 'pld') and event.pld:
                symbol = event.pld.symbol if hasattr(
                    event.pld, 'symbol') else "unknown"
            else:
                symbol = "unknown"
        except (AttributeError, TypeError):
            symbol = "unknown"

        self.logger.info(
            f"✅ on_risk() called for {symbol}. Risk params: {event.pld}")
        self.symbol_states[symbol]["risk"] = event.pld

        # Commit 5: Clear risk-skew until-refresh state on data refresh
        try:
            guard = self.symbol_states[symbol].get("risk_skew_guard") or {}
            if guard.get("until_refresh"):
                self.symbol_states[symbol]["risk_skew_guard"] = {
                    "defer_count": 0,
                    "window_start_ms": self._clock.now_ms(),
                    "until_refresh": False,
                }
                self.logger.info(
                    f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on risk refresh")
        except Exception as e:
            self.logger.warning(
                f"Error extracting symbol from feature event: {e}")

        # Cache risk data and timestamp for race condition handling
        if symbol not in self.symbol_states:
            self.symbol_states[symbol] = {}
        self.symbol_states[symbol]["_cached_risk"] = event.pld
        self.symbol_states[symbol]["_last_risk_time"] = self._clock.now_sec()

        try:
            if isinstance(event.pld, dict):
                rp = (event.pld or {}).get("risk_parameters") or {}
            elif hasattr(event, "pld") and event.pld and hasattr(event.pld, "risk_parameters"):
                rp = event.pld.risk_parameters or {}
            else:
                rp = {}
        except (AttributeError, TypeError):
            rp = {}

        self.dlog.write(
            "RISK_RX",
            aget(event, "rid", None),
            {
                "symbol": symbol,
                "trading_allowed": bool(rp["is_trading_allowed"] if "is_trading_allowed" in rp else False),
                "raw": rp,
            },
        )

    def on_portfolio(self, event: Message) -> None:
        self.logger.info(
            "✅ on_portfolio() called - portfolio state received!")
        portfolio_data = event.pld

        # Cache equity_free_usdt if present, but don't overwrite with zero/null
        try:
            if hasattr(portfolio_data, 'equity_free_usdt'):
                equity_free_usdt = portfolio_data.equity_free_usdt
            elif isinstance(portfolio_data, dict):
                equity_free_usdt = portfolio_data.get("equity_free_usdt")
            else:
                equity_free_usdt = None
        except (AttributeError, TypeError):
            equity_free_usdt = None

        if equity_free_usdt and equity_free_usdt not in ("0", "0.0"):
            self._cached_equity_free_usdt = equity_free_usdt
            self.logger.info(f"   Cached equity_free_usdt: {equity_free_usdt}")

        # Also cache equity_cross_usdt if present
        try:
            if hasattr(portfolio_data, 'equity_cross_usdt'):
                equity_cross_usdt = portfolio_data.equity_cross_usdt
            elif isinstance(portfolio_data, dict):
                equity_cross_usdt = portfolio_data.get("equity_cross_usdt")
            else:
                equity_cross_usdt = None
        except (AttributeError, TypeError):
            equity_cross_usdt = None

        if equity_cross_usdt and equity_cross_usdt not in ("0", "0.0"):
            self._cached_equity_cross_usdt = equity_cross_usdt

        self.latest_portfolio = portfolio_data
        positions = portfolio_data["positions"] if isinstance(
            portfolio_data, dict) and "positions" in portfolio_data else []
        self.logger.info(
            f"   Equity: {portfolio_data.get('equity') if isinstance(portfolio_data, dict) else None}, Positions: {len(positions)}"
        )

        self.dlog.write(
            "PORTFOLIO_RX",
            aget(event, "rid", None),
            {
                "equity": str(
                    self._cached_equity_free_usdt
                    or (portfolio_data["equity_free_usdt"] if isinstance(portfolio_data, dict) and "equity_free_usdt" in portfolio_data else "0")
                ),
                "positions_count": len(positions),
            },
        )

    def on_regime(self, event: Message) -> None:
        self.latest_regime = event.pld

        # Contract v1.0: Extract and cache warmup state
        if isinstance(event.pld, dict):
            warmup = event.pld["warmup"] if "warmup" in event.pld else {}
            self._latest_warmup = warmup
            symbol = event.pld.get("symbol")

            # Per-symbol regime cache: store regime for each symbol separately
            if symbol:
                regime_val = event.pld.get(
                    "regime") or event.pld.get("overall_regime")
                self._per_symbol_regimes[symbol] = {
                    "symbol": symbol,  # P0-3 Fix: Include symbol in payload
                    "regime": regime_val,
                    "warmup": warmup,
                    "confidence": event.pld.get("confidence"),
                    "axes": event.pld.get("axes"),
                }
                self.logger.debug(
                    f"[{symbol}] Regime updated: {self._per_symbol_regimes[symbol].get('regime')}"
                )

                # Check for regime flip enforcement
                self._handle_regime_flip(
                    symbol, self._per_symbol_regimes[symbol])

                # P0-4 Fix: Retrigger decision on Regime Update

            # Guard: Block trades if not full_ready
            full_ready = (
                bool(warmup["full_ready"] if "full_ready" in warmup else False)
                if self.arming_require_regime_warmup
                # P0-2 Fix: Default False
                else bool(warmup["full_ready"] if "full_ready" in warmup else False)
            )
            if symbol and not full_ready:
                ticks_seen = warmup["ticks_seen"] if "ticks_seen" in warmup else 0
                self.logger.info(
                    f"[{symbol}] RegimeContract: warmup phase (full_ready=false, "
                    f"ticks={ticks_seen})"
                )

        # Minimal behavior FSM mapping (if enabled)
        if self._behavior_enabled and event and event.pld:
            try:
                symbol = event.pld.get("symbol")
                regime = event.pld.get("regime")
                if regime in ("LOW_VOLATILITY", "MEAN_REVERSION"):
                    self._behavior_state[symbol] = "IdleFlat"
                elif regime in ("HIGH_VOLATILITY", "UNCERTAIN"):
                    self._behavior_state[symbol] = "Tension"
            except Exception:
                pass

    def _handle_regime_flip(self, symbol: str, regime_data: Any) -> None:
        """
        Check if new regime conflicts with existing position and close if needed.
        Enforces 'Immediate Closure' on regime flips.
        """
        try:
            regime = regime_data.get("regime") if isinstance(
                regime_data, dict) else str(regime_data)

            # Get current position
            portfolio = self.latest_portfolio
            if not portfolio:
                return

            pos_list = portfolio["positions"] if "positions" in portfolio else [
            ]
            curr_pos = next(
                (p for p in pos_list if p.get("symbol") == symbol), None)

            if not curr_pos:
                return

            qty_val = float(curr_pos["positionAmt"]
                            if "positionAmt" in curr_pos else 0)
            if abs(qty_val) < 1e-9:
                return

            is_long = qty_val > 0

            should_close = False
            reason = ""

            # Regime Logic: STRICT enforcement
            if regime == "TREND_UP" and not is_long:
                should_close = True
                reason = f"Short position in TREND_UP"
            elif regime == "TREND_DOWN" and is_long:
                should_close = True
                reason = f"Long position in TREND_DOWN"
            elif regime == "UNCERTAIN":
                should_close = True
                reason = f"Position in UNCERTAIN regime"

            if should_close:
                self.logger.warning(
                    f"[{symbol}] REGIME FLIP ENFORCEMENT: {reason}. Closing {qty_val}.")

                # Construct Close Intent
                close_side = "SELL" if is_long else "BUY"

                # Provide dummy price 0 for Market order (or best effort fetch)
                # We use 0 so it defaults to Market in adapter if not specified otherwise
                price = decimal.Decimal("0")

                # Emit intent
                why_chain = ["regime_flip_enforcement", regime]
                rid = f"rf-{int(self._clock.now_sec())}"
                strategy_id = regime_data.get("strategy_id", "aurora") if isinstance(
                    regime_data, dict) else "aurora"

                self._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(abs(qty_val))),
                    price=price,
                    why_chain=why_chain,
                    rid=rid,
                    reduce_only=True,
                    strategy_id=str(strategy_id),
                )
        except Exception as e:
            self.logger.warning(
                f"[{symbol}] Error in _handle_regime_flip: {e}")

    def _features_ready(self, symbol: str, features_data: dict) -> bool:
        """
        DM-BAR-TTL-PREEMIT-01: Check if features are fresh within TTL.

        Bar-aware logic (mirrors Gate 5):
        - For bars (tf_sec > 0): use bar_ttl_ms and bar_event_age_mode
        - For ticks (tf_sec == 0): use strict tick TTL (features_ttl_sec)

        Safety guard: even in "received" mode, reject bars older than
        max(tf_sec*1000, bar_ttl_ms) to prevent ancient bar leakage.
        """
        if not features_data or "ts" not in features_data:
            self.logger.debug(
                f"[{symbol}] _features_ready: no features_data or ts")
            return False

        now_ms = self._clock.now_ms()
        features_ts = features_data.get("ts", 0)
        tf_sec = int(features_data.get("tf_sec", 0) or 0)
        is_bar = tf_sec > 0

        if is_bar:
            # BAR-AWARE TTL: Use lenient bar_ttl_ms and age_mode
            sys_md = getattr(self.config.system, "market_data",
                             None) if self.config.system else None
            if sys_md:
                bar_ttl_ms = float(
                    getattr(sys_md, "bar_ttl_ms", 10000) or 10000)
                age_mode = str(
                    getattr(sys_md, "bar_event_age_mode", "received") or "received")
            else:
                bar_ttl_ms = 10000.0
                age_mode = "received"

            ttl_ms = bar_ttl_ms

            # Select age calculation based on mode
            if age_mode == "received":
                # Age from when we received the data, not when bar closed
                start_ts = features_data.get("_received_ts", features_ts)
            else:
                # Age from bar_close_ts / features_ts
                start_ts = features_ts

            lag_ms = now_ms - start_ts
            is_ready = lag_ms <= ttl_ms

            # SAFETY GUARD: Reject ancient bars even in received mode
            # A bar older than max(tf_sec*1000, bar_ttl_ms) is garbage data
            bar_close_ts = features_data.get("bar_close_ts", features_ts)
            max_bar_age_ms = max(tf_sec * 1000, bar_ttl_ms)
            bar_actual_age_ms = now_ms - bar_close_ts

            if bar_actual_age_ms > max_bar_age_ms:
                self.logger.debug(
                    f"[{symbol}] _features_ready: BAR_TOO_OLD bar_age={bar_actual_age_ms:.0f}ms > max={max_bar_age_ms:.0f}ms"
                )
                is_ready = False

            self.logger.debug(
                f"[{symbol}] _features_ready: BAR tf={tf_sec}s mode={age_mode} "
                f"lag={lag_ms:.0f}ms ttl={ttl_ms:.0f}ms bar_age={bar_actual_age_ms:.0f}ms ready={is_ready}"
            )
        else:
            # TICK: Use strict tick TTL (features_ttl_sec)
            ttl_ms = self.features_ttl_sec * 1000
            lag_ms = now_ms - features_ts
            is_ready = lag_ms <= ttl_ms

            self.logger.debug(
                f"[{symbol}] _features_ready: TICK lag={lag_ms:.0f}ms ttl={ttl_ms:.0f}ms ready={is_ready}"
            )

        return is_ready

    def _warmup_not_ready(self, symbol: str, reason: str, *, details: str | None = None) -> None:
        why = truncate_why(f"WARMUP_NOT_READY:{reason}")
        inc_warmup_block(domain="decision_making", reason=reason)
        if details:
            self.logger.warning(f"[{symbol}] {why} {details}")
        else:
            self.logger.warning(f"[{symbol}] {why}")

    def _warmup_gate_before_trade_intent(
        self,
        *,
        symbol: str,
        rid: str,
        reduce_only: bool,
        context: str,
    ) -> bool:
        """
        TASK24.B: Fail-closed readiness gate.

        Contract: while NOT_READY → no new TRADE_INTENT_PROPOSED (reduce_only closes allowed).
        """
        if reduce_only:
            return False

        # BYPASS IF WARN_ONLY (config-driven, not hardcoded)
        cfg_dm = self.config.domains.decision_making if hasattr(
            self.config.domains, "decision_making") else None
        if cfg_dm and hasattr(cfg_dm, "warmup") and cfg_dm.warmup.enforcement_mode == "warn_only":
            self.logger.debug(
                f"[{symbol}] WARMUP GATE BYPASS (warn_only mode)")
            return False

        if not self.latest_portfolio:
            self._warmup_not_ready(
                symbol, "portfolio_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        state = self.symbol_states.get(symbol) or {}
        features_evt = state.get("features") if isinstance(
            state, dict) else None
        if not isinstance(features_evt, dict):
            self._warmup_not_ready(
                symbol, "features_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True
        if not self._features_ready(symbol, features_evt):
            self._warmup_not_ready(
                symbol, "features_stale", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        risk_evt = state.get("risk") if isinstance(state, dict) else None
        if risk_evt is None:
            self._warmup_not_ready(
                symbol, "risk_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        warmup = None
        if symbol in self._per_symbol_regimes:
            warmup = self._per_symbol_regimes[symbol].get("warmup")

        # P0-1 Fix: Removed _latest_warmup fallback.
        # Strict Isolation: If per-symbol warmup is missing, we fail-closed.
        # if warmup is None:
        #    warmup = aget(self, "_latest_warmup", None)

        warmup_dict = warmup if isinstance(warmup, dict) else None
        if warmup_dict is None:
            self._warmup_not_ready(
                symbol, "regime_warmup_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True
        if not bool(warmup_dict["full_ready"] if "full_ready" in warmup_dict else False):
            ticks_seen = warmup_dict["ticks_seen"] if "ticks_seen" in warmup_dict else 0
            self._warmup_not_ready(
                symbol,
                "regime_not_ready",
                details=f"context={context} rid={rid} ticks_seen={ticks_seen}",
            )
            self._record_blocked_intent(symbol)
            return True

        # FeatureEngineering warmup contract (optional field in EVT:FEATURES_CALCULATED).
        fe_warmup = features_evt.get("warmup")
        fe_warmup_dict = fe_warmup if isinstance(fe_warmup, dict) else None
        if fe_warmup_dict is None:
            self._warmup_not_ready(
                symbol, "features_warmup_missing", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True
        if not bool(fe_warmup_dict["full_ready"] if "full_ready" in fe_warmup_dict else False):
            self._warmup_not_ready(
                symbol, "features_not_ready", details=f"context={context} rid={rid}")
            self._record_blocked_intent(symbol)
            return True

        return False

    def _calculate_position_size(
        self,
        symbol: str,
        price: decimal.Decimal,
        side: str,
        context: dict,
        *,
        margin_pct_mult: decimal.Decimal | None = None,
    ) -> tuple[Optional[decimal.Decimal], str, Optional[str], dict[str, Any]]:
        """Compute order quantity using margin-first SSOT.

        SSOT inputs:
        - instruments.<SYM>.sizing.margin_pct
        - instruments.<SYM>.execution.target_leverage
        - instruments.<SYM>.{step_size,min_qty,min_notional}

        Margin-first:
        - margin_usdt = equity * margin_pct
        - notional_target = margin_usdt * leverage
        - qty = floor_to_step(notional_target / price, step_size)
        """
        portfolio = context.get("portfolio") if isinstance(
            context, dict) else None
        if not isinstance(portfolio, dict):
            return None, "portfolio_missing", "PORTFOLIO_MISSING", {}

        equity = self._safe_decimal(portfolio.get(
            "equity", "0"), default=decimal.Decimal("0"))
        if equity is None:
            return None, "equity_invalid:None", "ZERO_EQUITY", {"equity": str(portfolio.get("equity"))}
        if equity <= 0:
            return None, f"equity_invalid:{equity}", "ZERO_EQUITY", {"equity": str(equity)}

        if price <= 0:
            return None, "price_invalid", "INVALID_PRICE", {"price": str(price)}

        # SSOT: per-symbol instruments config (constraints + execution + sizing)
        try:
            spec = self.config.instruments[symbol]
        except Exception as e:
            return None, f"unknown_instrument:{symbol}:{e}", "UNKNOWN_INSTRUMENT", {"symbol": str(symbol)}
        margin_pct_base = decimal.Decimal(str(spec.sizing.margin_pct))
        margin_pct = margin_pct_base
        if margin_pct_mult is not None:
            try:
                if margin_pct_mult <= 0:
                    return (
                        None,
                        f"invalid_margin_pct_mult:{margin_pct_mult}",
                        "CONFIG_REGIME_SIZING_INVALID",
                        {"margin_pct_mult": str(margin_pct_mult)},
                    )
                margin_pct = margin_pct_base * margin_pct_mult
                if margin_pct > decimal.Decimal("1"):
                    margin_pct = decimal.Decimal("1")
            except Exception as e:
                return (
                    None,
                    f"invalid_margin_pct_mult:{margin_pct_mult}:{e}",
                    "CONFIG_REGIME_SIZING_INVALID",
                    {"margin_pct_mult": str(margin_pct_mult), "error": str(e)},
                )
        leverage = int(spec.execution.target_leverage)
        step_size = decimal.Decimal(str(spec.step_size))
        min_qty = decimal.Decimal(str(spec.min_qty))
        min_notional = decimal.Decimal(str(spec.min_notional))

        margin_usdt, notional_target = compute_notional_target(
            equity=equity,
            margin_pct=margin_pct,
            leverage=leverage,
            notional_cap=self.liq_cap_usd,
        )

        raw_qty, rounded_qty = compute_qty(
            notional_target=notional_target,
            price=price,
            step_size=step_size,
        )
        order_notional = rounded_qty * price

        sizing_dbg: dict[str, Any] = {
            "equity": str(equity),
            "margin_pct_base": str(margin_pct_base),
            "margin_pct_mult": str(margin_pct_mult) if margin_pct_mult is not None else None,
            "margin_pct": str(margin_pct),
            "margin_usdt": str(margin_usdt),
            "leverage": int(leverage),
            "notional_target": str(notional_target),
            "price": str(price),
            "raw_qty": str(raw_qty),
            "rounded_qty": str(rounded_qty),
            "order_notional": str(order_notional),
            "step_size": str(step_size),
            "min_qty": str(min_qty),
            "min_notional": str(min_notional),
            "liq_cap_usd": str(self.liq_cap_usd),
            "min_position_size_usd": str(self.min_pos_size_usd),
        }

        self.logger.info(
            f"[{symbol}] MARGIN_FIRST_SIZING: equity=${equity}, margin_pct={margin_pct}, "
            f"margin_usdt=${margin_usdt}, leverage={leverage}, notional_target=${notional_target}, "
            f"liq_cap=${self.liq_cap_usd}"
        )
        self.logger.info(
            f"[{symbol}] QTY_CALC: price=${price}, raw_qty={raw_qty}, step_size={step_size}, "
            f"rounded_qty={rounded_qty}, notional=${order_notional}, "
            f"min_qty={min_qty}, min_notional={min_notional}"
        )

        reject_code, constraint_why = validate_exchange_constraints(
            qty=rounded_qty,
            price=price,
            min_qty=min_qty,
            min_notional=min_notional,
        )
        if reject_code is not None:
            reject_reason = f"exchange_constraints:{reject_code}:{constraint_why}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})", reject_code, sizing_dbg

        if order_notional < self.min_pos_size_usd:
            reject_reason = f"position notional {order_notional} is below minimum {self.min_pos_size_usd}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})", "MIN_POSITION_USD", sizing_dbg

        return rounded_qty, "margin_first_ok", None, sizing_dbg

    def _propose_trade_intent(
        self,
        symbol: str,
        side: str,
        qty: decimal.Decimal,
        price: decimal.Decimal,
        why_chain: list[str],
        rid: str,
        reduce_only: bool = False,
        strategy_id: str = "aurora",  # CFG-STRATEGIES-SSOT-01: Add strategy_id
        decision_ts_ms: int | None = None,
        # EP-01.2-INT: EntryPlan SL/TP parameters
        stop_price: str | None = None,
        target_price: str | None = None,
        entry_plan_trace: dict | None = None,
        # EP-01.3-INT: Timeframe for pending entry TTL calculation
        tf_sec: int | None = None,
        # TCA & Risk restoration
        max_slippage_bps: int | None = None,
        max_latency_ms: int | None = None,
        risk_score: float | None = None,
        strategy_trace: dict | None = None,
        entry_order_type_override: str | None = None,
        entry_tif_override: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        # DM-SAFETY-BYPASSES-P1: Config-based safety gates (no hardcoded strategy_id checks).
        # Directional/price-motion sanity are designed for trend-following entry safety.
        # Mean reversion intentionally trades against trend; set safety_gates.enabled=false.
        # FAIL-CLOSED: If safety_gates config is missing, BLOCK intent.
        apply_safety_gates = False
        try:
            strat_cfg = getattr(self.config.strategies, str(strategy_id), None)
            if strat_cfg is None:
                # Strategy not in config — cannot determine gates, FAIL-CLOSED
                self.logger.error(
                    f"[{symbol}] CONFIG_SAFETY_GATES_MISSING: strategy={strategy_id} not in config"
                )
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING,
                    reason="DECISION",
                    context="safety_gates config missing for strategy",
                    why_chain=why_chain,
                )
                self._record_blocked_intent(symbol)
                return
            safety_gates_cfg = getattr(strat_cfg, "safety_gates", None)
            if safety_gates_cfg is None:
                # safety_gates block missing — FAIL-CLOSED
                self.logger.error(
                    f"[{symbol}] CONFIG_SAFETY_GATES_MISSING: strategy={strategy_id}.safety_gates not configured"
                )
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING,
                    reason="DECISION",
                    context="safety_gates.enabled missing in strategy config",
                    why_chain=why_chain,
                )
                self._record_blocked_intent(symbol)
                return
            apply_safety_gates = bool(
                getattr(safety_gates_cfg, "enabled", False))
        except Exception as e:
            # Config access error — FAIL-CLOSED
            self.logger.error(
                f"[{symbol}] CONFIG_SAFETY_GATES_MISSING: error reading safety_gates: {e}"
            )
            self._emit_trade_intent_rejected(
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=str(side),
                rid=str(rid),
                reason_code=NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING,
                reason="DECISION",
                context=f"safety_gates config error: {str(e)[:40]}",
                why_chain=why_chain,
            )
            self._record_blocked_intent(symbol)
            return

        # DM-DIR-FORENSIC-01: Directional sanity gate (fail-closed when enabled).
        trace_ts_ms = int(
            decision_ts_ms) if decision_ts_ms is not None else self._clock.now_ms()
        intent_side = "LONG" if str(side).upper() == "BUY" else "SHORT"

        # PRICE-MOTION-V1: Extract latest price_motion block (best-effort, monitoring + gating).

        pm_norm_10s: float | None = None
        pm_norm_60s: float | None = None
        pm_norm_300s: float | None = None
        vol_pct_10s: float | None = None
        vol_pct_60s: float | None = None
        vol_pct_300s: float | None = None
        try:
            st = self.symbol_states.get(symbol) if hasattr(
                self, "symbol_states") else None
            feats_evt = st.get("features") if isinstance(st, dict) else None
            pm = feats_evt.get("price_motion") if isinstance(
                feats_evt, dict) else None
            if isinstance(pm, dict):
                pm_norm_10s = float(pm["pm_norm_10s"]) if pm.get(
                    "pm_norm_10s") is not None else None
                pm_norm_60s = float(pm["pm_norm_60s"]) if pm.get(
                    "pm_norm_60s") is not None else None
                pm_norm_300s = float(pm["pm_norm_300s"]) if pm.get(
                    "pm_norm_300s") is not None else None
                vol_pct_10s = float(pm["vol_pct_10s"]) if pm.get(
                    "vol_pct_10s") is not None else None
                vol_pct_60s = float(pm["vol_pct_60s"]) if pm.get(
                    "vol_pct_60s") is not None else None
                vol_pct_300s = float(pm["vol_pct_300s"]) if pm.get(
                    "vol_pct_300s") is not None else None
        except Exception:
            pm_norm_10s = None
            pm_norm_60s = None
            pm_norm_300s = None
            vol_pct_10s = None
            vol_pct_60s = None
            vol_pct_300s = None

        signal_score: float | None = None
        try:
            # Best-effort extraction from why_chain strings.
            for item in (why_chain or []):
                if not isinstance(item, str):
                    continue
                if "signal_score=" in item:
                    part = item.split("signal_score=", 1)[1]
                    token = part.split(",", 1)[0].split(" ", 1)[0]
                    signal_score = float(token)
                    break
        except Exception:
            signal_score = None

        regime: str | None = None
        regime_confidence: float | None = None
        try:
            r = self._per_symbol_regimes.get(symbol) if hasattr(
                self, "_per_symbol_regimes") else None
            if isinstance(r, dict):
                regime = r.get("regime")
                rc = r.get("confidence")
                regime_confidence = float(rc) if rc not in (None, "") else None
        except Exception:
            regime = None
            regime_confidence = None

        ds_cfg = self.config.domains.decision_making.directional_sanity
        ds_enabled = bool(ds_cfg.enabled)
        min_abs_delta = float(ds_cfg.min_abs_delta_price)
        min_conf = float(ds_cfg.min_confidence)
        consecutive = int(ds_cfg.consecutive_bars)

        # Compute trend from recent delta_price values (features SSOT).
        trend_dir = "UNKNOWN"
        delta_price: float | None = None
        trend_confidence: float = 0.0
        try:
            state = self.symbol_states.get(symbol) if hasattr(
                self, "symbol_states") else None
            hist = state.get("_delta_price_hist") if isinstance(
                state, dict) else None
            if isinstance(hist, deque) and len(hist) > 0:
                delta_price = float(hist[-1])
                if len(hist) >= consecutive:
                    # Ignore zero deltas (tick-level "no move") to avoid permanent UNKNOWN trend.
                    # Keep only deltas that pass the noise threshold and are non-zero.
                    filtered: list[float] = []
                    for x in list(hist):
                        try:
                            xf = float(x)
                        except Exception:
                            continue
                        if abs(xf) < float(min_abs_delta):
                            continue
                        if xf == 0.0:
                            continue
                        filtered.append(xf)

                    window = filtered[-consecutive:]
                    if len(window) >= consecutive:
                        if all(x > 0 for x in window):
                            trend_dir = "UP"
                            trend_confidence = 1.0
                        elif all(x < 0 for x in window):
                            trend_dir = "DOWN"
                            trend_confidence = 1.0
        except Exception:
            trend_dir = "UNKNOWN"
            delta_price = None
            trend_confidence = 0.0

        # Decide directional gate outcome
        gate_outcome = "ALLOW"
        deny_reason: str | None = None
        why_short = "ok"

        if reduce_only:
            # Never block reduce-only (safety: allow closing)
            gate_outcome = "ALLOW"
            why_short = "reduce_only"
        elif not apply_safety_gates:
            gate_outcome = "ALLOW"
            why_short = f"safety_gates_skipped:strategy={strategy_id}"
        elif not ds_enabled:
            gate_outcome = "ALLOW"
            why_short = "directional_sanity_disabled"
        else:
            effective_conf = max(
                float(regime_confidence or 0.0), float(trend_confidence or 0.0))
            if trend_dir not in ("UP", "DOWN"):
                gate_outcome = "DENY"
                deny_reason = NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION
                why_short = "insufficient trend confirmation"
            elif effective_conf < float(min_conf):
                gate_outcome = "DENY"
                deny_reason = NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION
                why_short = "insufficient confidence"
            elif trend_dir == "DOWN" and intent_side == "LONG":
                gate_outcome = "DENY"
                deny_reason = NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED
                why_short = "downtrend blocks long"
            elif trend_dir == "UP" and intent_side == "SHORT":
                gate_outcome = "DENY"
                deny_reason = NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED
                why_short = "uptrend blocks short"

        # PRICE-MOTION-V1: Multi-window sanity gate (fail-closed when enabled).
        if gate_outcome == "ALLOW":
            pm_cfg = self.config.domains.decision_making.price_motion_sanity
            pm_enabled = bool(pm_cfg.enabled)

            # BACKTEST-COMPATIBLE: Skip price_motion gate in backtest mode.
            # Bar-based backtests lack tick-level granularity for pm_norm_* computation,
            # causing pm_norm_60s/300s to be None and triggering fail-closed NRR-028.
            # This gate is designed for LIVE tick-level anti-FOMO protection.
            try:
                is_backtest = str(
                    getattr(self.config, "trading_mode", "")).strip().lower() == "backtest"
            except Exception:
                is_backtest = False

            def _select_pm(window_sec: int) -> float | None:
                if window_sec == 10:
                    return pm_norm_10s
                if window_sec == 60:
                    return pm_norm_60s
                if window_sec == 300:
                    return pm_norm_300s
                raise ConfigContractError(
                    path="domains.decision_making.price_motion_sanity",
                    why=f"Unsupported price_motion window_sec={window_sec}; expected 10/60/300",
                    symbol=symbol,
                )

            if (not apply_safety_gates) or reduce_only or (not pm_enabled) or is_backtest:
                pass
            else:
                flash_window = int(pm_cfg.flash_window_sec)
                bleed_window = int(pm_cfg.bleed_window_sec)
                t_flash = float(pm_cfg.flash_threshold_norm)
                t_bleed = float(pm_cfg.bleed_threshold_norm)
                require_bleed_ready = bool(pm_cfg.require_bleed_ready)

                pm_flash = _select_pm(flash_window)
                pm_bleed = _select_pm(bleed_window)

                if pm_flash is None:
                    gate_outcome = "DENY"
                    deny_reason = NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT
                    why_short = "price_motion flash insufficient"
                elif require_bleed_ready and (pm_bleed is None):
                    gate_outcome = "DENY"
                    deny_reason = NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT
                    why_short = "price_motion bleed insufficient"
                else:
                    # Flash gate
                    if intent_side == "LONG" and pm_flash <= -t_flash:
                        gate_outcome = "DENY"
                        deny_reason = NormalizedRejectReasons.PRICE_MOTION_FLASH_BLOCKED
                        why_short = "flash down blocks long"
                    elif intent_side == "SHORT" and pm_flash >= t_flash:
                        gate_outcome = "DENY"
                        deny_reason = NormalizedRejectReasons.PRICE_MOTION_FLASH_BLOCKED
                        why_short = "flash up blocks short"
                    # Bleed gate (only if ready)
                    elif pm_bleed is not None:
                        if intent_side == "LONG" and pm_bleed <= -t_bleed:
                            gate_outcome = "DENY"
                            deny_reason = NormalizedRejectReasons.PRICE_MOTION_BLEED_BLOCKED
                            why_short = "bleed down blocks long"
                        elif intent_side == "SHORT" and pm_bleed >= t_bleed:
                            gate_outcome = "DENY"
                            deny_reason = NormalizedRejectReasons.PRICE_MOTION_BLEED_BLOCKED
                            why_short = "bleed up blocks short"

        # If DENY: emit forensic trace immediately and stop (NO TRADE).
        if gate_outcome == "DENY":
            trace_payload = {
                "symbol": symbol,
                "ts": trace_ts_ms,
                "intent_side": intent_side,
                "signal_score": signal_score,
                "regime": regime,
                "regime_confidence": regime_confidence,
                "trend_dir": trend_dir,
                "delta_price": delta_price,
                "pm_norm_10s": pm_norm_10s,
                "pm_norm_60s": pm_norm_60s,
                "pm_norm_300s": pm_norm_300s,
                "vol_pct_10s": vol_pct_10s,
                "vol_pct_60s": vol_pct_60s,
                "vol_pct_300s": vol_pct_300s,
                "gate_outcome": "DENY",
                "deny_reason": deny_reason,
                "why": (str(why_short)[:80] if why_short is not None else "")
            }
            try:
                self.fsm.emit(
                    "EVT:DECISION_TRACE_EMITTED",
                    payload=trace_payload,
                    why="decision_trace",
                    data_ref=why_chain,
                )
            except Exception:
                # Monitoring-only: never block on trace emission
                pass

            self.logger.info(
                f"[{symbol}] SAFETY_GATES: DENY {intent_side} trend={trend_dir} reason={deny_reason}"
            )
            try:
                side_u = str(side).upper()
                if side_u not in ("BUY", "SELL"):
                    side_u = "NONE"
                nrr = str(deny_reason) if deny_reason else None
                order_logger.write(
                    {
                        "rid": rid,
                        "event_type": "ORDER_REJECTED",
                        "symbol": symbol,
                        "side": side_u,
                        "nrr_code": nrr,
                        "why": f"SAFETY_GATES:{why_short}"[:80],
                        "source_fsm": "DecisionMaking",
                        "metadata": {
                            "reject_reason": "SAFETY_GATES_DENY",
                            "deny_reason": deny_reason,
                            "intent_side": intent_side,
                            "trend_dir": trend_dir,
                            "delta_price": delta_price,
                            "pm_norm_10s": pm_norm_10s,
                            "pm_norm_60s": pm_norm_60s,
                            "pm_norm_300s": pm_norm_300s,
                            "vol_pct_10s": vol_pct_10s,
                            "vol_pct_60s": vol_pct_60s,
                            "vol_pct_300s": vol_pct_300s,
                            "signal_score": signal_score,
                            "regime": regime,
                            "regime_confidence": regime_confidence,
                        },
                    }
                )
            except Exception:
                # Observability must never block trading logic
                pass
            self._record_blocked_intent(symbol)
            return

        current_regime = self._resolve_symbol_regime(symbol, preferred=regime)
        if self._is_uncertain_hard_block(current_regime) and not reduce_only:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: UNCERTAIN hard block strategy={strategy_id}"
            )
            inc_decision_blocked(stage="decision", reason_code="REGIME_GATE_BLOCKED")
            self._emit_trade_intent_rejected(
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=str(side),
                rid=str(rid),
                reason_code="REGIME_GATE_BLOCKED",
                reason="DECISION",
                context="decision_making:uncertain_hard_block",
                why_chain=(why_chain or []) + ["REGIME_GATE_BLOCKED", "UNCERTAIN"],
                details={"regime": current_regime},
            )
            self._record_blocked_intent(symbol)
            return

        symbol_busy = self._get_symbol_entry_block_reason(
            symbol, reduce_only=reduce_only)
        if symbol_busy is not None:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: symbol busy ({symbol_busy.get('reason')})"
            )
            inc_decision_blocked(stage="decision", reason_code="NRR-SYMBOL-BUSY")
            self._emit_trade_intent_rejected(
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=str(side),
                rid=str(rid),
                reason_code="NRR-SYMBOL-BUSY",
                reason="DECISION",
                context="decision_making:symbol_busy",
                why_chain=(why_chain or []) + ["NRR-SYMBOL-BUSY"],
                details=symbol_busy,
            )
            self._record_blocked_intent(symbol)
            return

        # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Check strategy arbitration
        arbitration_result = self._check_strategy_arbitration(
            symbol, strategy_id, ts_ms=decision_ts_ms, commit=False
        )
        if not arbitration_result["allowed"]:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: Strategy arbitration rejected: {arbitration_result['reason']}"
            )
            self._record_blocked_intent(symbol)
            return

        if self._warmup_gate_before_trade_intent(
            symbol=symbol,
            rid=rid,
            reduce_only=reduce_only,
            context="decision_making:_propose_trade_intent",
        ):
            return

        # TASK49: Atomic CAS guard for ENTRY orders (fixes TOCTOU race from TASK40).
        # Uses try_reserve_entry() to atomically check + reserve in single lock hold.
        # This prevents duplicate ENTRY orders when multiple ticks arrive quickly.
        if not reduce_only:
            try:
                # type: ignore[attr-defined]
                if hasattr(self.fsm, "order_index") and self.fsm.order_index:
                    # Try atomic reservation - returns False if another ENTRY in-flight
                    # type: ignore[attr-defined]
                    if not self.fsm.order_index.try_reserve_entry(symbol, rid):
                        now_ms = self._clock.now_ms()
                        retry_key = f"order_in_flight:{symbol}:{rid}"
                        self.logger.info(
                            f"[{symbol}] TRADE_INTENT_DEFERRED: NRR-ORDER-IN-FLIGHT (retry_key={retry_key})"
                        )
                        inc_decision_deferred("NRR-ORDER-IN-FLIGHT", symbol)
                        self._emit_intent_deferred_v1(
                            symbol=symbol,
                            reason="NRR-ORDER-IN-FLIGHT",
                            retry_key=retry_key,
                            next_allowed_ts=now_ms + 1000,
                            original_event_name="EVT:TRADE_INTENT_PROPOSED",
                            original_payload_min={
                                "symbol": symbol,
                                "side": side,
                                "rid": rid,
                                "strategy_id": strategy_id,
                            },
                            attempt=1,
                            max_attempts=3,
                            why_chain=(why_chain or []) + ["order_in_flight"],
                            context="decision_making:one_open_order_guard",
                        )
                        self._record_blocked_intent(symbol)
                        return
                    # Reservation succeeded - intent will be emitted below
            except Exception as e:
                # P0-5 Fix: Fail-Closed on Order Index error
                self.logger.error(
                    f"[{symbol}] OrderIndex access failed: {e}", exc_info=True)
                self.fsm.emit(
                    "EVT:INTENT_DEFERRED",
                    {
                        "symbol": symbol,
                        "rid": rid,
                        "reason": "NRR-ORDER-INDEX-FAIL",
                        "next_allowed_ts": None,
                        "original_context": "decision_making:_propose_trade_intent",
                    },
                )
                self._record_blocked_intent(symbol)
                return

        # Z-01 FIX: Read tca_prefs from config (Strict P1)
        tca = self._tca_prefs
        # Safe extraction helper (handles dict or Pydantic)

        def _get_strict(obj, key, err_msg):
            if isinstance(obj, dict):
                val = obj[key] if key in obj else None
            else:
                val = aget(obj, key, None)
            if val is None:
                raise ValueError(err_msg)
            return val

        try:
            # TCA Prefs: Prefer passed arguments (from Risk Engine), fall back to config
            if max_slippage_bps is not None:
                max_slippage = str(max_slippage_bps)
            else:
                max_slippage = str(_get_strict(
                    tca, 'max_slippage_bps', "Missing max_slippage_bps"))

            if max_latency_ms is not None:
                max_latency = max_latency_ms
            else:
                max_latency = _get_strict(
                    tca, 'max_latency_ms', "Missing max_latency_ms")

            maker_pref = _get_strict(
                tca, 'maker_preference', "Missing maker_preference")
        except ValueError as e:
            self.logger.error(f"TCA Config Block: {e}")
            return None  # Block trade

        # Z-02 FIX: Read risk_budgets from config (Strict P1)
        rb = self._risk_budgets
        try:
            trade_cvar = str(_get_strict(
                rb, 'trade_cvar95_max_bps', "Missing trade_cvar95_max_bps"))
            session_cvar = str(_get_strict(
                rb, 'session_cvar95_max_bps', "Missing session_cvar95_max_bps"))
        except ValueError as e:
            self.logger.error(f"RiskBudget Config Block: {e}")
            return None  # Block trade

        # ORDER-POLICY-01: Resolve per-strategy execution policy (fail-closed).
        order_type: str | None = None
        tif: str | None = None
        exec_cfg = None
        try:
            strat_cfg = getattr(self.config.strategies, str(strategy_id), None)
            exec_cfg = getattr(strat_cfg, "execution",
                               None) if strat_cfg is not None else None
            if reduce_only:
                # EP-H2-SAFE-EXIT-DEGRADE:
                # Reduce-only close uses dedicated exit policy with fail-safe MARKET default.
                order_type = getattr(
                    exec_cfg, "exit_order_type", None) if exec_cfg is not None else None
                tif = getattr(exec_cfg, "exit_tif",
                              None) if exec_cfg is not None else None
                if not order_type:
                    order_type = "MARKET"
            else:
                order_type = getattr(
                    exec_cfg, "entry_order_type", None) if exec_cfg is not None else None
                tif = getattr(exec_cfg, "entry_tif",
                              None) if exec_cfg is not None else None
        except Exception:
            order_type = None
            tif = None

        if not reduce_only and entry_order_type_override:
            order_type = str(entry_order_type_override).upper()
        if not reduce_only and entry_tif_override:
            tif = str(entry_tif_override).upper()

        if not order_type:
            self._emit_trade_intent_rejected(
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=str(side),
                rid=str(rid),
                reason_code=NormalizedRejectReasons.ORDER_TYPE_MISSING,
                reason="DECISION",
                context="ORDER-POLICY-01: missing strategy execution.entry_order_type",
                why_chain=(why_chain if isinstance(why_chain, list) else []),
                details={"strategy_id": str(strategy_id)},
            )
            self._record_blocked_intent(symbol)
            return None

        order_type_u = str(order_type).upper()

        # Validate against global capabilities (SSOT).
        try:
            caps = self.config.domains.execution_position.order_capabilities
            supported_types = set(str(x).upper()
                                  for x in (caps.supported_order_types or []))
            supported_tifs = set(str(x).upper()
                                 for x in (caps.supported_tif or []))
        except Exception:
            supported_types = set()
            supported_tifs = set()

        degraded_from_order_type: str | None = None
        degraded_why: str | None = None

        if supported_types and order_type_u not in supported_types:
            if reduce_only:
                degraded_from_order_type = order_type_u
                order_type_u = "MARKET"
                tif = None
                degraded_why = "UNSUPPORTED_EXIT_ORDER_TYPE"
            else:
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.UNSUPPORTED_ORDER_TYPE,
                    reason="DECISION",
                    context=f"ORDER-POLICY-01: unsupported order_type={order_type_u}",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []),
                    details={"order_type": order_type_u,
                             "supported": sorted(supported_types)},
                )
                self._record_blocked_intent(symbol)
                return None

        if order_type_u == "LIMIT":
            if tif is None:
                if reduce_only:
                    degraded_from_order_type = degraded_from_order_type or "LIMIT"
                    order_type_u = "MARKET"
                    tif = None
                    degraded_why = degraded_why or "MISSING_TIF_FOR_LIMIT_EXIT"
                else:
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=str(side),
                        rid=str(rid),
                        reason_code=NormalizedRejectReasons.TIF_REQUIRED_FOR_LIMIT,
                        reason="DECISION",
                        context="ORDER-POLICY-01: LIMIT requires explicit tif (no defaults)",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []),
                        details={"order_type": "LIMIT"},
                    )
                    self._record_blocked_intent(symbol)
                    return None
            if order_type_u == "LIMIT":
                tif_u = str(tif).upper()
                if supported_tifs and tif_u not in supported_tifs:
                    if reduce_only:
                        degraded_from_order_type = degraded_from_order_type or "LIMIT"
                        order_type_u = "MARKET"
                        tif = None
                        degraded_why = degraded_why or "UNSUPPORTED_TIF_FOR_LIMIT_EXIT"
                    else:
                        self._emit_trade_intent_rejected(
                            symbol=symbol,
                            strategy_id=str(strategy_id),
                            side=str(side),
                            rid=str(rid),
                            reason_code=NormalizedRejectReasons.UNSUPPORTED_TIF,
                            reason="DECISION",
                            context=f"ORDER-POLICY-01: unsupported tif={tif_u}",
                            why_chain=(why_chain if isinstance(
                                why_chain, list) else []),
                            details={"tif": tif_u,
                                     "supported": sorted(supported_tifs)},
                        )
                        self._record_blocked_intent(symbol)
                        return None
                if order_type_u == "LIMIT":
                    tif = tif_u
        else:
            # MARKET: tif must be null (fail-closed; no silent ignore).
            if tif is not None and not reduce_only:
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.UNSUPPORTED_TIF,
                    reason="DECISION",
                    context="ORDER-POLICY-01: MARKET must have tif=null",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []),
                    details={"order_type": "MARKET", "tif": str(tif)},
                )
                self._record_blocked_intent(symbol)
                return None
            tif = None

        # EP-01.3-INT: Calculate valid_for_ms ONLY for LIMIT (pending entry TTL, fail-closed).
        valid_for_ms: int | None = None
        if order_type_u == "LIMIT":
            if reduce_only:
                exit_limit_ttl_ms = getattr(
                    exec_cfg, "exit_limit_ttl_ms", None) if exec_cfg is not None else None
                if exit_limit_ttl_ms is not None:
                    valid_for_ms = int(exit_limit_ttl_ms)
                else:
                    # Fail-safe for reduce_only close: never reject on missing tf_sec/TTL.
                    degraded_from_order_type = degraded_from_order_type or "LIMIT"
                    order_type_u = "MARKET"
                    tif = None
                    valid_for_ms = None
                    degraded_why = "MISSING_TTL_FOR_LIMIT_EXIT"
            elif tf_sec is None:
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                    reason="DECISION",
                    context="EP-01.3-INT: LIMIT requires tf_sec to derive valid_for_ms",
                    why_chain=(why_chain if isinstance(
                        why_chain, list) else []),
                    details={"order_type": "LIMIT"},
                )
                self._record_blocked_intent(symbol)
                return None

            if order_type_u == "LIMIT":
                try:
                    pe_ttl_cfg = self.config.domains.execution_position.pending_entry_ttl
                    if pe_ttl_cfg.enabled:
                        ttl_by_tf = pe_ttl_cfg.ttl_by_tf_sec
                        if tf_sec in ttl_by_tf:
                            valid_for_ms = int(ttl_by_tf[tf_sec]) * 1000
                            self.logger.debug(
                                f"[{symbol}] EP-01.3: valid_for_ms={valid_for_ms} (tf_sec={tf_sec})"
                            )
                        elif pe_ttl_cfg.reject_unknown_tf:
                            self._emit_trade_intent_rejected(
                                symbol=symbol,
                                strategy_id=str(strategy_id),
                                side=str(side),
                                rid=str(rid),
                                reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                                reason="DECISION",
                                context=f"EP-01.3-INT: tf_sec={tf_sec} not in ttl_by_tf_sec (reject_unknown_tf=true)",
                                why_chain=(why_chain if isinstance(
                                    why_chain, list) else []),
                                details={"tf_sec": int(
                                    tf_sec), "known_tfs": sorted(ttl_by_tf.keys())},
                            )
                            self._record_blocked_intent(symbol)
                            return None
                except Exception as e:
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=str(side),
                        rid=str(rid),
                        reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                        reason="DECISION",
                        context=f"EP-01.3-INT: failed to derive valid_for_ms: {e}",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []),
                    )
                    self._record_blocked_intent(symbol)
                    return None

                if valid_for_ms is None:
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=str(side),
                        rid=str(rid),
                        reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                        reason="DECISION",
                        context="EP-01.3-INT: LIMIT requires valid_for_ms (no fallback to global fill_ttl_ms)",
                        why_chain=(why_chain if isinstance(
                            why_chain, list) else []),
                        details={"order_type": "LIMIT"},
                    )
                    self._record_blocked_intent(symbol)
                    return None

        if reduce_only and degraded_from_order_type and degraded_why:
            self._emit_trade_intent_degraded(
                symbol=symbol,
                rid=str(rid),
                strategy_id=str(strategy_id),
                reduce_only=True,
                from_order_type=str(degraded_from_order_type),
                to_order_type=str(order_type_u),
                why=str(degraded_why)[:80],
                why_chain=(why_chain if isinstance(why_chain, list) else []),
            )

        # Sanitize strategy/EntryPlan SL/TP to avoid payload pollution ("nan", "inf", "None").
        stop_price_payload: str | None = None
        target_price_payload: str | None = None
        if stop_price not in (None, "", "None"):
            sd = self._safe_decimal(stop_price, default=None)
            stop_price_payload = str(sd) if sd is not None else None
        if target_price not in (None, "", "None"):
            td = self._safe_decimal(target_price, default=None)
            target_price_payload = str(td) if td is not None else None

        trade_intent = {
            # TASK40: Preserve stable business RID end-to-end (intent -> cmd -> execution).
            # Bridge uses pld["rid"] as authoritative correlation key when present.
            "rid": str(rid),
            "instrument": symbol,
            "side": side,
            # TASK32: Strategy-agnostic DecisionMaking still tags intents with the originating strategy_id.
            "strategy": strategy_id,
            "order": {
                "qty": str(qty),
                "price": str(price),
                "price_ref": str(price),
                "reduce_only": reduce_only,
                "order_type": order_type_u,
                "tif": tif,
            },
            "p": "0.75",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": max_slippage,
                "max_latency_ms": max_latency,
                "maker_preference": str(maker_pref),
            },
            # RESTORED: Risk Context (Degradation Report Point 3)
            "risk_context": {
                "risk_score": risk_score if risk_score is not None else 0.0,
            },
            "risk_budget": {
                "trade_cvar95_max_bps": trade_cvar,
                "session_cvar95_max_bps": session_cvar,
            },
            "size": {"notional_cap_usd": str(qty * price), "kelly_fraction": "0.1"},
            # EP-01.3-INT: LIMIT-only pending entry TTL (fail-closed: no silent fallback).
            "valid_for_ms": valid_for_ms,
            "why": why_chain,
            "dto_version": "1.0.0",
            "schema_ref": "trade_intent_v1.json",
            "idempotent_key": str(uuid.uuid4()),
            # EP-01.2-INT: EntryPlan SL/TP (null if not computed)
            "stop_price": stop_price_payload,
            "target_price": target_price_payload,
            "entry_plan": entry_plan_trace,
        }
        if isinstance(strategy_trace, dict) and strategy_trace:
            trade_intent["trace"] = strategy_trace
        if str(strategy_id) == "aurora":
            trade_intent["normalize_mode_effective"] = "signed_v2"

        # TASK47: Commit windowed arbitration only for intents that are about to be emitted.
        commit_result = self._check_strategy_arbitration(
            symbol, strategy_id, ts_ms=decision_ts_ms, commit=True)
        if not commit_result["allowed"]:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: Strategy arbitration rejected: {commit_result['reason']}"
            )
            self._record_blocked_intent(symbol)
            return

        # DM-DIR-FORENSIC-01: Emit forensic trace (monitoring-only) right before TRADE_INTENT_PROPOSED.
        trace_payload = {
            "symbol": symbol,
            "ts": trace_ts_ms,
            "intent_side": intent_side,
            "signal_score": signal_score,
            "regime": regime,
            "regime_confidence": regime_confidence,
            "trend_dir": trend_dir,
            "delta_price": delta_price,
            "pm_norm_10s": pm_norm_10s,
            "pm_norm_60s": pm_norm_60s,
            "pm_norm_300s": pm_norm_300s,
            "vol_pct_10s": vol_pct_10s,
            "vol_pct_60s": vol_pct_60s,
            "vol_pct_300s": vol_pct_300s,
            "gate_outcome": "ALLOW",
            "deny_reason": None,
            "why": (str(why_short)[:80] if why_short is not None else ""),
        }
        try:
            self.fsm.emit(
                "EVT:DECISION_TRACE_EMITTED",
                payload=trace_payload,
                why="decision_trace",
                data_ref=why_chain,
            )
        except Exception:
            # Monitoring-only: never block on trace emission
            pass

        # Record accepted intent for risk gate monitoring
        try:
            self._record_accepted_intent(symbol)
        except Exception as e:
            # Monitoring-only: never block trading on metrics
            self.logger.warning(
                f"Failed to record accepted intent metrics: {e}")

        # WAL: write the intent emission as a first-class event (not only OrderLoggerV1)
        # so WAL contains non-account lifecycle evidence even when no order gets placed.
        try:
            intent_evt = Message(
                op="EVT",
                verb="TRADE_INTENT_PROPOSED",
                src="decision_making",
                dst="bridge",
                rid=str(rid),
                pld=trade_intent,
                why=truncate_why("trade_intent") or "trade_intent",
                data_ref=[str(x) for x in why_chain] if isinstance(
                    why_chain, list) else [],
                intent="PROPOSAL",
            )
            res = wal.append(intent_evt.model_dump())
            if res is None:
                self.logger.error(
                    f"[{symbol}] CRITICAL: WAL WRITE FAILED (LOCK TIMEOUT). RID={rid}"
                )
        except Exception as wal_e:
            # Best-effort: do not block trading on WAL tap errors here.
            self.logger.warning(
                f"Failed to write TRADE_INTENT_PROPOSED to WAL: {wal_e}")

        self.fsm.emit(
            "EVT:TRADE_INTENT_PROPOSED", payload=trade_intent, why="trade_intent", data_ref=why_chain
        )

        # TAP LOG: DM intent emitted
        # Note: tf_sec not available in this context; use trace_ts_ms instead
        # Ensure seq_counter exists (defensive for mocked instances)
        if not hasattr(self, 'seq_counter'):
            self.seq_counter = 0
        log_entry = {
            "symbol": symbol,
            "tf_sec": None,  # Not available in _propose_trade_intent scope
            "bar_end_ts_ms": trace_ts_ms,
            "bar_id": f"{symbol}:intent:{trace_ts_ms}",
            "seq": self.seq_counter,
            "source": "dm_intent_emitted",
            "why": "intent_proposed"
        }
        print(json.dumps(log_entry), flush=True)
        self.seq_counter += 1

        # EXP-DIRECTION: Side-bias penalty relies on an accurate recent history of
        # accepted (emitted) intents. Maintain that window here so it reflects
        # the actual downstream proposals (not merely evaluated signals).
        try:
            if not reduce_only:
                side_intent_window = aget(self, "_side_intent_window", None)
                if side_intent_window is None:
                    side_intent_window = {}
                    self._side_intent_window = side_intent_window
                if symbol not in side_intent_window:
                    side_intent_window[symbol] = {"buys": [], "sells": []}

                window_data = side_intent_window[symbol]
                now_sec = self._clock.now_sec()
                _, bias_window_sec, _, _ = self._get_side_bias_params(symbol)
                window_data["buys"] = [
                    ts for ts in window_data["buys"] if now_sec - ts < bias_window_sec]
                window_data["sells"] = [
                    ts for ts in window_data["sells"] if now_sec - ts < bias_window_sec]

                if intent_side == "LONG":
                    window_data["buys"].append(now_sec)
                elif intent_side == "SHORT":
                    window_data["sells"].append(now_sec)
        except Exception:
            # Monitoring-only: never block trading on side-bias bookkeeping.
            pass

        # Log to OrderLoggerV1
        order_logger.write({
            "rid": rid,
            "event_type": "ORDER_INTENT",
            "symbol": symbol,
            "side": side.upper(),
            "quantity": float(qty),
            "price": float(price),
            "source_fsm": "DecisionMaking",
            "metadata": {"intent_proposed": True, "idempotent_key": trade_intent["idempotent_key"]}
        })

        # Update idempotency guard (SUCCESS)
        # Note: moved from _make_decision_for_symbol to here to capture ALL successful intents
        # But we need Features TS... passed via context? Or assume caller handles it?
        # The caller handles it. This method is just the emission mechanism.

        # CLEAR STATE IS DONE BY CALLER usually.
        return trade_intent

    def _get_position_state(self, symbol: str) -> str:
        """
        Get current position state from SSOT (latest_portfolio).
        Returns: FLAT, LONG, SHORT, UNKNOWN
        """
        qty_signed, _ = self._get_portfolio_position_qty_signed(symbol)
        if qty_signed is None:
            return "UNKNOWN"

        try:
            tol = decimal.Decimal("1e-9")
        except Exception:
            tol = decimal.Decimal(str(1e-9))

        if abs(qty_signed) < tol:  # Equality tolerance
            return "FLAT"

        return "LONG" if qty_signed > 0 else "SHORT"

    def _resolve_symbol_regime(
        self,
        symbol: str,
        *,
        preferred: Any = None,
    ) -> Optional[str]:
        if preferred not in (None, ""):
            return str(preferred)

        regime_evt = self._per_symbol_regimes.get(symbol)
        if isinstance(regime_evt, dict):
            regime = regime_evt.get("regime") or regime_evt.get("overall_regime")
            if regime not in (None, ""):
                return str(regime)

        if isinstance(self.latest_regime, dict):
            latest_symbol = self.latest_regime.get("symbol")
            if latest_symbol in (None, "", symbol):
                regime = self.latest_regime.get(
                    "regime") or self.latest_regime.get("overall_regime")
                if regime not in (None, ""):
                    return str(regime)

        return None

    @staticmethod
    def _is_uncertain_hard_block(regime: Any) -> bool:
        return str(regime or "").upper() == "UNCERTAIN"

    def _get_symbol_entry_block_reason(
        self,
        symbol: str,
        *,
        reduce_only: bool,
    ) -> Optional[Dict[str, Any]]:
        if reduce_only:
            return None

        qty_signed, curr_pos = self._get_portfolio_position_qty_signed(symbol)
        tol = decimal.Decimal("1e-9")
        if qty_signed is not None and abs(qty_signed) >= tol:
            return {
                "reason": "active_position",
                "qty_signed": str(qty_signed),
                "position_state": "LONG" if qty_signed > 0 else "SHORT",
                "position": curr_pos,
            }

        pending_flip = self._pending_flips.get(symbol)
        if isinstance(pending_flip, dict):
            return {
                "reason": "pending_flip_close",
                "pending_flip": pending_flip,
            }

        return None

    def _get_portfolio_position_qty_signed(
        self, symbol: str
    ) -> tuple[Optional[decimal.Decimal], Optional[dict]]:
        """Return signed position qty for a symbol from latest_portfolio (SSOT), or None if unknown."""
        if not isinstance(self.latest_portfolio, dict):
            return None, None

        positions = self.latest_portfolio.get("positions")
        if not isinstance(positions, list):
            return None, None

        curr_pos = next(
            (p for p in positions if isinstance(p, dict)
             and p.get("symbol") == symbol), None
        )
        if not curr_pos:
            return decimal.Decimal("0"), None

        qty_val: Any = None
        for key in (
            "net_position",  # SSOT: position_tracking
            "positionAmt",  # Binance futures payload
            "position_amount",
            "position_amt",
            "qty",
            "quantity",
        ):
            if key in curr_pos and curr_pos.get(key) not in (None, ""):
                qty_val = curr_pos.get(key)
                break

        if qty_val in (None, ""):
            return None, curr_pos

        try:
            return decimal.Decimal(str(qty_val)), curr_pos
        except Exception:
            return None, curr_pos

    def _is_flip(self, symbol: str, intent_side: str, position_state: str = None) -> bool:
        """Check if intent opposes current position."""
        if not position_state:
            position_state = self._get_position_state(symbol)

        if position_state == "FLAT" or position_state == "UNKNOWN":
            return False

        intent_side = intent_side.upper()
        if position_state == "LONG" and intent_side == "SELL":
            return True
        if position_state == "SHORT" and intent_side == "BUY":
            return True

        return False

    def _emit_reduce_only_close(
        self,
        symbol: str,
        reason: str,
        rid: str,
        *,
        strategy_id: str,
        strategy_trace: dict | None = None,
    ) -> bool:
        """Emit immediate reduce-only close intent for Flip Orchestration.

        IMPORTANT: Use the originating strategy_id for registry arbitration.
        Otherwise, the close can be silently blocked when the symbol is assigned to a
        different strategy, which leaves the position stuck and effectively halts
        trading (observed in backtests).
        """
        qty_signed, curr_pos = self._get_portfolio_position_qty_signed(symbol)
        if qty_signed is None:
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: CLOSE qty missing/invalid in portfolio; skip emit (pos={curr_pos})"
            )
            return False

        try:
            tol = decimal.Decimal("1e-9")
        except Exception:
            tol = decimal.Decimal(str(1e-9))

        if abs(qty_signed) < tol:
            return False  # Nothing to close

        close_side = "SELL" if qty_signed > 0 else "BUY"
        qty_abs = abs(qty_signed)
        if qty_abs <= 0:
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: CLOSE qty invalid/zero; skip emit (qty_signed={qty_signed})"
            )
            return False

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Emitting CLOSE {close_side} {qty_abs} (reduce_only)"
        )

        intent = self._propose_trade_intent(
            symbol=symbol,
            side=close_side,
            qty=decimal.Decimal(str(qty_abs)),
            price=decimal.Decimal("0"),  # Market/Best-effort
            why_chain=["flip_orchestration_close", reason],
            rid=rid,
            reduce_only=True,
            strategy_id=str(strategy_id),
            strategy_trace=strategy_trace,
        )
        return intent is not None

    def _stable_retry_key(
        self,
        *,
        prefix: str,
        symbol: str,
        rid: str | None,
        side: str | None = None,
        ts_ms: int | None = None,
    ) -> str:
        if rid:
            return f"{prefix}:{symbol}:{rid}"
        if ts_ms is None:
            ts_ms = self._clock.now_ms()
        if side:
            return f"{prefix}:{symbol}:{side}:{ts_ms}"
        return f"{prefix}:{symbol}:{ts_ms}"

    def _degraded_context_gate_should_defer(
        self,
        *,
        symbol: str,
        rid: str,
        ctx: DecisionContext,
        features_evt: dict,
        strategy_id: str | None = None,
    ) -> bool:
        """Optionally defer when critical DecisionContext features are missing/invalid.

        This is intentionally opt-in to avoid changing live behavior unless explicitly enabled.
        Enable by setting `self._fail_closed_on_degraded_context = True`.
        Optionally override critical keys via `self._degraded_context_critical_keys = {...}`.
        """

        if not bool(getattr(self, "_fail_closed_on_degraded_context", False)):
            return False

        default_critical_keys = {
            "price",
            "ema_bias",
            "obi",
            "tfi",
            "volatility_state",
            "depth_imbalance",
        }

        # Per-strategy override (if provided and present in config), else global list, else safe defaults.
        by_strategy = getattr(
            self, "_degraded_context_critical_keys_by_strategy", {}) or {}
        selected: set[str] | None = None
        if strategy_id and isinstance(by_strategy, dict):
            override = by_strategy.get(str(strategy_id))
            if override:
                selected = set(str(k) for k in override if str(k))

        if selected is None:
            global_keys = getattr(
                self, "_degraded_context_critical_keys", None)
            if global_keys:
                selected = set(str(k) for k in global_keys if str(k))
            else:
                selected = set(default_critical_keys)

        critical_keys = selected

        # Force lazy parsing to populate missing_fields.
        _ = ctx.price
        _ = ctx.trend
        _ = ctx.flow
        _ = ctx.volatility
        _ = ctx.liquidity

        missing_critical = {k: v for k, v in (
            ctx.missing_fields or {}).items() if k in critical_keys}
        if not missing_critical:
            return False

        now_ms = self._clock.now_ms()
        features_ts = int(features_evt["ts"] if "ts" in features_evt else 0)
        retry_prefix = f"ctx:{strategy_id}" if strategy_id else "ctx"
        retry_key = self._stable_retry_key(
            prefix=retry_prefix, symbol=symbol, rid=rid, ts_ms=features_ts)

        self.logger.warning(
            f"[{symbol}] DEFER degraded DecisionContext: missing_critical={missing_critical}"
        )

        # Match existing defer semantics: short backoff, bounded attempts.
        self._emit_intent_deferred_v1(
            symbol=symbol,
            reason=NormalizedRejectReasons.DATA_NOT_READY,
            retry_key=retry_key,
            next_allowed_ts=now_ms + 500,
            original_event_name="EVT:FEATURES_CALCULATED",
            original_payload_min={
                "symbol": symbol,
                "rid": rid,
                "features_ts": features_ts,
                "missing_critical": missing_critical,
            },
            attempt=1,
            max_attempts=5,
            why_chain=["fail_closed", "decision_context_degraded"],
            context="decision_making:_make_decision_for_symbol:degraded_context_gate",
        )
        self._record_blocked_intent(symbol)
        return True

    def _emit_intent_deferred_v1(
        self,
        *,
        symbol: str,
        reason: str,
        retry_key: str,
        next_allowed_ts: int,
        original_event_name: str,
        original_payload_min: Dict[str, Any],
        attempt: int = 1,
        max_attempts: int = 5,
        why_chain: list[str] | None = None,
        context: str | None = None,
    ) -> None:
        now_ms = self._clock.now_ms()
        try:
            ttl_ms = int(self.config.strategies.aurora.decision.retry_ttl_ms)
        except AttributeError as e:
            raise ConfigContractError(
                path="strategies.aurora.decision.retry_ttl_ms",
                why=f"Missing required strict config field: {e}",
                symbol=symbol,
            )
        payload: Dict[str, Any] = {
            "retry_key": retry_key,
            "symbol": symbol,
            "reason": reason,
            "next_allowed_ts": int(next_allowed_ts),
            "attempt": int(attempt),
            "max_attempts": int(max_attempts),
            "retry_policy": {
                "attempt": int(attempt),
                "max_attempts": int(max_attempts),
                "backoff_ms": max(0, int(next_allowed_ts) - now_ms),
                "ttl_ms": ttl_ms,
            },
            "original_event": {
                "event_name": original_event_name,
                "payload_min": original_payload_min,
            },
            "why_chain": why_chain or [],
            "created_ts": now_ms,
        }
        if context:
            payload["context"] = context
        self.fsm.emit("EVT:INTENT_DEFERRED", payload,
                      why=f"intent_deferred:{reason}")

    def _emit_trade_intent_rejected(
        self,
        *,
        symbol: str,
        strategy_id: str,
        side: str,
        rid: str,
        reason_code: str,
        reason: str,
        context: str,
        why_chain: list[str] | None = None,
        details: Dict[str, Any] | None = None,
    ) -> None:
        """Emit + persist an explicit rejection event so blocks are observable (Missed Opportunity)."""
        # Monitoring-only: rejection reporting must never throw.
        try:
            ts_ms = self._clock.now_ms()

            stage = str(reason).upper()
            if stage not in ("RISK", "STRATEGY", "DECISION", "EXECUTION"):
                stage = "DECISION"

            payload: Dict[str, Any] = {
                "ts_ms": ts_ms,
                "symbol": symbol,
                "strategy_id": str(strategy_id),
                "side": str(side).lower(),
                "rid": str(rid),
                "reason_code": str(reason_code),
                "stage": stage,
                "why": str(context),
                "context": str(context),
                "why_chain": list(why_chain or []),
            }
            if details:
                payload["details"] = details

            # SSOT persistence (WAL)
            write_trade_intent_rejected(
                symbol=symbol,
                strategy_id=str(strategy_id),
                side=str(side).lower(),
                rid=str(rid),
                reason_code=str(reason_code),
                stage=stage,  # type: ignore[arg-type]
                why=str(context),
                context=str(context),
                why_chain=list(why_chain or []),
                details=details,
                normalize_mode_effective="signed_v2" if str(
                    strategy_id) == "aurora" else None,
                src="decision_making",
                ts_ms=ts_ms,
            )

            # In-process event (optional)
            self.fsm.emit("EVT:TRADE_INTENT_REJECTED", payload,
                          why=f"intent_rejected:{reason_code}")
        except Exception:
            return

    def _emit_trade_intent_degraded(
        self,
        *,
        symbol: str,
        rid: str,
        strategy_id: str,
        reduce_only: bool,
        from_order_type: str,
        to_order_type: str,
        why: str,
        why_chain: list[str] | None = None,
    ) -> None:
        """Emit monitoring event for fail-safe order policy degradation."""
        try:
            payload: Dict[str, Any] = {
                "symbol": str(symbol),
                "rid": str(rid),
                "strategy_id": str(strategy_id),
                "reduce_only": bool(reduce_only),
                "from_order_type": str(from_order_type),
                "to_order_type": str(to_order_type),
                "why_chain": list(why_chain or []),
            }
            self.fsm.emit(
                "EVT:TRADE_INTENT_DEGRADED",
                payload=payload,
                why=str(why)[:80],
                data_ref=(list(why_chain or []) or None),
            )
        except Exception:
            return

    def _schedule_open_retry(self, symbol: str, original_context: dict, cooldown_ms: int, reason: str) -> None:
        """Emit EVT:INTENT_DEFERRED to schedule retry after close."""
        next_ts = self._clock.now_ms() + cooldown_ms

        # Match schema intent_deferred_v1.json
        payload = {
            "retry_key": f"flip-{symbol}-{int(self._clock.now_sec())}",
            "symbol": symbol,
            "reason": reason,
            "next_allowed_ts": next_ts,
            "attempt": 1,
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:TRADE_INTENT_PROPOSED",  # Default assumption for open intent
                "payload_min": original_context
            },
            "created_ts": self._clock.now_ms(),
            "why_chain": ["flip_orchestration_defer"]
        }

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Deferring OPEN until {next_ts} (reason: {reason})")
        self.fsm.emit("EVT:INTENT_DEFERRED", payload,
                      why=f"intent_deferred:{reason}")

    def clear_internal_state_for_symbol(self, symbol: str) -> None:
        # Do not clear state - it serves as SSOT cache for MR Gateway and other async strategies.
        # Data freshness is handled by TTL checks (Gate 5) and Risk Skew checks (Gate 1.5).
        pass

    def _record_blocked_intent(self, symbol: str) -> None:
        """Record a blocked intent and check alert thresholds."""
        self.intents_blocked_total += 1
        self.intents_seen_total += 1
        self._check_and_emit_risk_gate_alert()

    def _record_accepted_intent(self, symbol: str) -> None:
        """Record an accepted intent and check alert thresholds."""
        self.intents_seen_total += 1
        self._check_and_emit_risk_gate_alert()

    def _check_and_emit_risk_gate_alert(self) -> None:
        """
        Periodically check if blocked intents % exceeds threshold,
        and emit alert via AlertManager if available.
        Check every 10 seconds to avoid excessive calls.
        """
        if not self.alert_manager:
            return

        current_time = self._clock.now_sec()
        if current_time - self.last_alert_check_time < 10.0:
            return  # Too soon, skip check

        self.last_alert_check_time = current_time

        # Get risk_gate config (SSOT from domains.yaml)
        risk_gate_cfg = self.config.domains.decision_making.risk_gate
        min_intents = risk_gate_cfg.min_intents_for_check

        # Calculate blocked percentage
        if self.intents_seen_total < min_intents:
            # Not enough data yet
            return

        blocked_pct = (self.intents_blocked_total /
                       self.intents_seen_total) * 100

        # Get trading mode for threshold selection (FAIL-CLOSED: must be configured)
        mode = getattr(self.config.trading, "mode", None)
        if mode is None:
            raise ValueError(
                "FAIL-CLOSED: trading.mode is required for risk gate alerts. "
                "Configure trading.mode in trading.yaml (testnet or production)."
            )

        # SSOT: thresholds from domains.yaml risk_gate config
        if mode == "testnet":
            threshold_pct = risk_gate_cfg.threshold_pct_testnet
        else:
            threshold_pct = risk_gate_cfg.threshold_pct_production

        if blocked_pct > threshold_pct:
            self.logger.warning(
                f"Risk gate alert: {blocked_pct:.1f}% intents blocked "
                f"({self.intents_blocked_total}/{self.intents_seen_total})"
            )
            try:
                self.alert_manager.check_risk_gate(blocked_pct)
            except Exception as e:
                self.logger.error(f"Error emitting risk gate alert: {e}")

    def start(self) -> None:
        """Start the decision making component."""
        self.logger.info("DecisionMaking started")

    def stop(self) -> None:
        """Stop the decision making component."""
        self.logger.info("DecisionMaking stopped")

    def update_exposure_cache(self, event: Message) -> None:
        """Update exposure cache from EVT:EXPOSURE_SUMMARY_UPDATED events."""
        try:
            payload = event.pld or {}
            exposure_summary = payload["exposure_summary"] if "exposure_summary" in payload else {
            }
            if exposure_summary:
                self._exposure_cache = exposure_summary
                self._exposure_cache_timestamp = self._clock.now_sec()
                self.logger.debug(
                    f"✅ Exposure cache updated: {len(exposure_summary)} symbols")
        except Exception as e:
            self.logger.warning(f"Failed to update exposure cache: {e}")

    def _precheck_exposure_cache(self, symbol: str, side: str, notional_usd: float) -> bool:
        """
        Pre-check exposure limits using cached exposure summary.

        DM-SAFETY-BYPASSES-P1: FAIL-CLOSED behavior.
        Returns True if trade should be allowed, False if blocked.
        Missing/stale/error cache -> BLOCK (not allow).
        """
        if not self._exposure_cache:
            # DM-SAFETY-BYPASSES-P1: No cache = FAIL-CLOSED
            self.logger.warning(
                f"[{symbol}] EXPOSURE_CACHE_UNAVAILABLE: No cache, blocking trade"
            )
            return False

        try:
            # Check if cache is stale (older than 30 seconds)
            cache_age = self._clock.now_sec() - self._exposure_cache_timestamp
            if cache_age > 30.0:
                # DM-SAFETY-BYPASSES-P1: Stale cache = FAIL-CLOSED
                self.logger.warning(
                    f"[{symbol}] EXPOSURE_CACHE_UNAVAILABLE: stale ({cache_age:.1f}s>30s)"
                )
                return False

            # Get exposure data for symbol
            symbol_exposure = self._exposure_cache[symbol] if symbol in self._exposure_cache else {
            }
            current_exposure = symbol_exposure["current_exposure_usd"] if "current_exposure_usd" in symbol_exposure else 0.0
            max_exposure = symbol_exposure["max_exposure_usd"] if "max_exposure_usd" in symbol_exposure else float(
                "inf")

            # Calculate projected exposure after this trade
            projected_exposure = current_exposure + notional_usd

            if projected_exposure > max_exposure:
                self.logger.info(
                    f"[{symbol}] EXPOSURE_CACHE_BLOCK: projected={projected_exposure:.2f} > max={max_exposure:.2f}, "
                    f"blocking {side.upper()} trade"
                )
                return False

            self.logger.debug(
                f"[{symbol}] EXPOSURE_CACHE_ALLOW: current={current_exposure:.2f}, "
                f"projected={projected_exposure:.2f}, max={max_exposure:.2f}"
            )
            return True

        except Exception as e:
            # DM-SAFETY-BYPASSES-P1: Exception = FAIL-CLOSED
            self.logger.warning(
                f"[{symbol}] EXPOSURE_CACHE_UNAVAILABLE: error ({e}), blocking trade"
            )
            return False

    # === D3: FLIP ORCHESTRATION (Plan v1) ===

    def _is_same_side_position(self, position_side: str | None, intent_side: str) -> bool:
        """Check if intent side is same as current position side (pyramiding)."""
        if not position_side:
            return False
        return position_side == intent_side

    def _generate_flip_retry_key(self, symbol: str, side: str, seed: str | None = None) -> str:
        """Generate stable retry_key for a flip transaction."""
        if seed:
            return f"flip:{symbol}:{side}:{seed}"
        ts_ms = self._clock.now_ms()
        return f"flip:{symbol}:{side}:{ts_ms}"

    def _resolve_position_mode(self, *, symbol: str, source: str) -> str | None:
        """Resolve per-symbol position_mode for the emitting strategy (STRICT|DYNAMIC).

        SSOT:
        - strategies.<strategy_id>.assets.<SYMBOL>.position_mode
        """
        try:
            strategies = getattr(self.config, "strategies", None)
            strat_cfg = getattr(strategies, str(source),
                                None) if strategies is not None else None
            assets = getattr(strat_cfg, "assets",
                             None) if strat_cfg is not None else None
            asset_cfg = assets.get(symbol) if isinstance(
                assets, dict) else None
            mode_raw = getattr(asset_cfg, "position_mode",
                               None) if asset_cfg is not None else None
            if mode_raw is None:
                return None
            mode = str(mode_raw).upper()
            if mode in {"STRICT", "DYNAMIC"}:
                return mode
            return None
        except Exception:
            return None

    def _handle_flip_orchestration(
        self,
        symbol: str,
        intent_side: str,
        original_pld: Dict[str, Any],
        source: str = "aurora"
    ) -> Optional[str]:
        """
        D3: Handle flip orchestration when OPEN requested.
        STRICT SEQUENTIAL CONTRACT:
        1. UNKNOWN -> Fail-closed (Defer)
        2. FLAT -> Allow
        3. LONG/SHORT + Same Side -> Block (Anti-Pyramiding)
        4. LONG/SHORT + Opposite Side -> Flip Orchestration (Close -> Defer Open)
        """
        # 0. Get per-symbol flip config (instruments.yaml -> domains.yaml fallback)
        flip_enabled, flip_mult = self._get_flip_config(symbol)

        # 1. Check State (anti-pyramiding needs this even if flip is disabled)
        pos_state = self._get_position_state(symbol)

        if pos_state == "UNKNOWN":
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: State UNKNOWN, fail-closed (NRR-PORTFOLIO-UNKNOWN)"
            )
            return "NRR-PORTFOLIO-UNKNOWN"

        if pos_state == "FLAT":
            self.logger.debug(
                f"[{symbol}] FLIP_ORCHESTRATION: FLAT, allowing OPEN {intent_side}")
            return None

        # 2. Check Flip vs Same-Side
        is_flip = self._is_flip(symbol, intent_side, pos_state)

        if not is_flip:
            # Must be same-side (or some weird state), treat as Anti-Pyramiding
            position_mode = self._resolve_position_mode(
                symbol=symbol, source=source)
            if position_mode is None:
                self.logger.error(
                    f"[{symbol}] FLIP_ORCHESTRATION: BLOCK - position_mode missing/invalid "
                    f"(expected strategies.{source}.assets.{symbol}.position_mode)"
                )
                return "CONFIG_POSITION_MODE_INVALID"
            if position_mode == "DYNAMIC":
                self.logger.info(
                    f"[{symbol}] FLIP_ORCHESTRATION: Same-side pyramiding allowed (position_mode=DYNAMIC)"
                )
                return None
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: BLOCK - Same-side pyramiding not allowed "
                f"(state={pos_state}, intent={intent_side})"
            )
            return "ANTI_PYRAMIDING_BLOCK"

        # 2.1 Opposite-side while flip is disabled: allow OPEN (netting/exchange will reduce/flip).
        # Anti-pyramiding is still enforced above for same-side.
        if not flip_enabled:
            self.logger.debug(
                f"[{symbol}] FLIP_ORCHESTRATION: DISABLED for this symbol; allowing opposite-side OPEN "
                f"(state={pos_state}, intent={intent_side})"
            )
            return None

        # 3. Handle Flip
        # Optional hysteresis: require stronger opposite signal before closing.
        if flip_enabled and flip_mult > 1.0:
            try:
                score = float(original_pld.get("signal_score")) if original_pld.get(
                    "signal_score") is not None else None
                thr_buy = float(original_pld.get("thr_buy")) if original_pld.get(
                    "thr_buy") is not None else None
                thr_sell = float(original_pld.get("thr_sell")) if original_pld.get(
                    "thr_sell") is not None else None
            except Exception:
                score, thr_buy, thr_sell = None, None, None

            # If we don't have score/threshold context, we can't apply hysteresis safely.
            if score is not None and thr_buy is not None and thr_sell is not None:
                if str(intent_side).lower() == "buy":
                    required = thr_buy * flip_mult
                    if score < required:
                        self.logger.info(
                            f"[{symbol}] FLIP_ORCHESTRATION: HYSTERESIS_BLOCK (BUY) "
                            f"score={score:.4f} < required={required:.4f} (thr_buy={thr_buy:.4f}, mult={flip_mult})"
                        )
                        return "FLIP_HYSTERESIS_BLOCK"
                elif str(intent_side).lower() == "sell":
                    required = thr_sell * flip_mult
                    if score > -required:
                        self.logger.info(
                            f"[{symbol}] FLIP_ORCHESTRATION: HYSTERESIS_BLOCK (SELL) "
                            f"score={score:.4f} > -required={-required:.4f} (thr_sell={thr_sell:.4f}, mult={flip_mult})"
                        )
                        return "FLIP_HYSTERESIS_BLOCK"

        # Emit Reduce-Only Close
        rid = original_pld.get("rid") or f"flip-{int(self._clock.now_sec())}"
        close_emitted = self._emit_reduce_only_close(
            symbol,
            "flip_orchestration",
            f"{rid}-close",
            strategy_id=str(source),
        )

        # Schedule Retry (Defer Open)
        # Use simple cooldown for now (e.g. 5s) or fetch per-symbol config
        retry_key = self._generate_flip_retry_key(
            symbol, intent_side, seed=rid)
        now_ms = self._clock.now_ms()

        # Get stale TTL for retry delay (SSOT fail-closed)
        stale_ttl_sec = self.config.domains.position_tracking.positions_stale_ttl_sec
        if stale_ttl_sec is None:
            raise ValueError(
                "domains.position_tracking.positions_stale_ttl_sec is required (SSOT)")
        next_allowed_ts = now_ms + int(stale_ttl_sec * 1000)

        # Flip retry routing (v7): always retry via the strategy gateway signal path.
        # This ensures retries are handled uniformly for ALL strategies.
        original_payload_min = dict(original_pld) if isinstance(
            original_pld, dict) else {}
        original_payload_min["symbol"] = symbol
        original_payload_min["side"] = intent_side
        original_payload_min["strategy_id"] = original_payload_min.get(
            "strategy_id") or source
        original_payload_min["rid"] = original_payload_min.get(
            "rid") or f"flip_{retry_key}"
        # Flip retry is pre-validated: mark readiness ok so gateway accepts it (v7 contract)
        original_payload_min["readiness"] = {"warmup_ok": True}

        original_event = {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "payload_min": original_payload_min,
        }

        # Build why_chain for debugging
        why_chain_raw = original_pld.get("why_chain")
        why_chain = why_chain_raw.copy() if isinstance(why_chain_raw, list) else []
        why_chain.extend(["opposite_position_exists"])
        if close_emitted:
            why_chain.append("flip_close_emitted")
        else:
            why_chain.append("flip_close_skipped_invalid_qty")

        self._emit_intent_deferred_v1(
            symbol=symbol,
            reason="FLIP_CLOSE_PENDING" if close_emitted else "NRR-FLIP-CLOSE-QTY-INVALID",
            retry_key=retry_key,
            next_allowed_ts=next_allowed_ts,
            original_event_name=original_event["event_name"],
            original_payload_min=original_event["payload_min"],
            attempt=1,
            max_attempts=5,
            why_chain=why_chain,
            context=f"flip_orchestration_{source}",
        )

        return "FLIP_CLOSE_PENDING" if close_emitted else "NRR-FLIP-CLOSE-QTY-INVALID"

    def _initiate_flip_close(
        self,
        symbol: str,
        intent_side: str,
        original_pld: Dict[str, Any],
        source: str
    ) -> str:
        """
        D3: Initiate flip by emitting CMD:CLOSE and deferring OPEN intent.

        Returns:
            "FLIP_CLOSE_PENDING" reason (always blocks current intent)
        """
        retry_key = self._generate_flip_retry_key(
            symbol, intent_side, seed=original_pld.get("rid"))
        now_ms = self._clock.now_ms()

        # Get stale TTL for retry delay (SSOT fail-closed)
        stale_ttl_sec = self.config.domains.position_tracking.positions_stale_ttl_sec
        if stale_ttl_sec is None:
            raise ValueError(
                "domains.position_tracking.positions_stale_ttl_sec is required (SSOT)")
        next_allowed_ts = now_ms + int(stale_ttl_sec * 1000)

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Initiating flip - closing opposite position, "
            f"deferring {intent_side} OPEN (retry_key={retry_key})"
        )

        # Emit CMD:CLOSE to close existing position
        close_pld = {
            "symbol": symbol,
            "reason": "FLIP_CLOSE",
            "retry_key": retry_key,  # For idempotency
            "rid": original_pld["rid"] if "rid" in original_pld else f"flip_close_{retry_key}",
        }

        self.fsm.emit("CMD:CLOSE", close_pld)

        # Flip retry routing (v7): always retry via the strategy gateway signal path.
        original_payload_min = dict(original_pld) if isinstance(
            original_pld, dict) else {}
        original_payload_min["symbol"] = symbol
        original_payload_min["side"] = intent_side
        original_payload_min["strategy_id"] = original_payload_min.get(
            "strategy_id") or source
        original_payload_min["rid"] = original_payload_min.get(
            "rid") or f"flip_{retry_key}"
        # Flip retry is pre-validated: mark readiness ok so gateway accepts it (v7 contract)
        original_payload_min["readiness"] = {"warmup_ok": True}

        original_event = {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "payload_min": original_payload_min,
        }

        # Build why_chain for debugging
        why_chain_raw = original_pld.get("why_chain")
        why_chain = why_chain_raw.copy() if isinstance(why_chain_raw, list) else []
        why_chain.extend(["opposite_position_exists", "flip_close_emitted"])

        self._emit_intent_deferred_v1(
            symbol=symbol,
            reason="FLIP_CLOSE_PENDING",
            retry_key=retry_key,
            next_allowed_ts=next_allowed_ts,
            original_event_name=original_event["event_name"],
            original_payload_min=original_event["payload_min"],
            attempt=1,
            max_attempts=5,
            why_chain=why_chain,
            context=f"flip_orchestration_{source}",
        )

        self.logger.info(
            f"[{symbol}] FLIP_ORCHESTRATION: Emitted CMD:CLOSE + INTENT_DEFERRED "
            f"(next_allowed_ts={next_allowed_ts}, retry_key={retry_key})"
        )

        return "FLIP_CLOSE_PENDING"

    # === COMMIT 4: STRICT SEQUENTIAL TRADING CONTRACT HELPERS ===

    def _check_symbol_is_flat(self, symbol: str) -> bool:
        """
        Check if portfolio position for symbol is FLAT (no position).

        STRICT SEQUENTIAL TRADING CONTRACT:
        Per-symbol check - ETH position doesn't block DOGE OPEN.

        FAIL-CLOSED (Commit 4.1):
        - Unknown portfolio → NOT FLAT → DEFER
        - Exception → NOT FLAT → DEFER
        This prevents opening positions "in the dark".

        Returns:
            True if CONFIRMED no position exists (FLAT), False otherwise.
        """
        try:
            if not self.latest_portfolio:
                # FAIL-CLOSED: No portfolio data → NOT FLAT → DEFER
                self.logger.warning(
                    f"[{symbol}] _check_symbol_is_flat: No portfolio data, "
                    f"FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)"
                )
                return False  # NOT FLAT - will trigger DEFER

            portfolio = self.latest_portfolio
            positions = portfolio["positions"] if (isinstance(
                portfolio, dict) and "positions" in portfolio) else []
            if not positions:
                return True  # Empty positions = confirmed FLAT

            for pos in positions:
                pos_symbol = pos["symbol"] if "symbol" in pos else ""
                if pos_symbol != symbol:
                    continue

                # Check positionAmt (Binance format)
                qty_str = pos["positionAmt"] if "positionAmt" in pos else "0"
                try:
                    qty = abs(float(qty_str))
                except (ValueError, TypeError):
                    qty = 0.0

                # Position exists if qty > threshold
                flat_threshold = 1e-9
                if qty > flat_threshold:
                    self.logger.debug(
                        f"[{symbol}] _check_symbol_is_flat: Position exists, qty={qty}")
                    return False

            return True  # No matching position found = FLAT

        except Exception as e:
            # FAIL-CLOSED: Error → NOT FLAT → DEFER
            self.logger.warning(
                f"[{symbol}] _check_symbol_is_flat error: {e}, "
                f"FAIL-CLOSED (NRR-PORTFOLIO-UNKNOWN)"
            )
            return False  # NOT FLAT - will trigger DEFER
            return None

    def _get_risk_skew_config(self, key: str) -> Any:
        """
        Get risk_skew config value from domains config.

        Commit 5: Risk Skew Guard configuration.
        Config path: domains.decision_making.risk_skew.<key>

        FAIL-CLOSED: If risk_skew not configured or key missing → ValueError.
        SSOT: All values must be in domains.yaml.
        """
        risk_skew = self.config.domains.decision_making.risk_skew
        value = getattr(risk_skew, key, None)
        if value is None:
            raise ValueError(
                f"domains.decision_making.risk_skew.{key} is required (SSOT fail-closed)"
            )
        return value

    def _get_precision(self, symbol: str) -> tuple[float, float]:
        """Return (tick_size, step_size) from canonical config.instruments; fail-closed.

        CANONICAL: config.instruments only (SSOT from config/aurora/instruments.yaml).
        CFG-INSTRUMENTS-STEP-02-DM-PRECISION

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')

        Returns:
            (tick_size, step_size) as floats

        Raises:
            ValueError: If symbol missing or precision fields not set
        """
        instruments = self.config.instruments
        if not instruments or symbol not in instruments:
            raise ValueError(
                f"Missing instrument config for {symbol} in config.instruments (SSOT)"
            )

        spec = instruments[symbol]
        tick_size = aget(spec, "tick_size", None)
        step_size = aget(spec, "step_size", None)

        if tick_size is None or step_size is None:
            raise ValueError(
                f"Missing precision for {symbol}: tick_size={tick_size}, step_size={step_size}"
            )

        return float(tick_size), float(step_size)


# Backward-compat alias used by legacy runtime tests.
DecisionMakingLogic = DecisionMaking
