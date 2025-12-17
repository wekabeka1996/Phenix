"""
DecisionMaking domain component.

Aggregates features, risk assessment, and portfolio state to make trading decisions
and emit EVT:TRADE_INTENT_PROPOSED events.

FTR-07: Refactored to use DecisionContext for type-safe feature access.
CFG-DOMAINS-STEP-02: Enforces AuroraConfig contract (not dict).
"""

import decimal
import logging
import time
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Dict, Any, Optional, TYPE_CHECKING, List, Tuple
from apps.reference.config_contract import ConfigContractError

from vfoundation.core.protocol import Message
from vfoundation.dr import wal

from .normalized_reject_reasons import NormalizedRejectReasons
from .deferred_scheduler import DeferredIntentScheduler
from .dm_log_adapter import (
    DecisionLog,
)
# FTR-07: Import DecisionContext for typed feature access
from .decision_context import DecisionContext, create_decision_context

# CFG-DOMAINS-STEP-02: Import AuroraConfig for type enforcement
from apps.reference.config_models import AuroraConfig

from apps.reference.telemetry.metrics import inc_decision_deferred, inc_config_contract_violation
from vfoundation.core.why_codes import WhyCode, format_why_with_details
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.contracts.reject_reasons import RejectReason, normalize_config_error

# CFG-DOMAINS-STEP-02: Import DomainConfigResolver for canonical config access
from apps.reference.domain_config import DomainConfigResolver

# Phase 0: Import Aurora per-instrument config
from apps.reference.config_models import AuroraInstrumentConfig

# Track B: Import Mean Reversion handler
try:
    from .mean_reversion_handler import MeanReversionHandler
    MEAN_REVERSION_AVAILABLE = True
except ImportError:
    MEAN_REVERSION_AVAILABLE = False
    MeanReversionHandler = None  # type: ignore

# Import AlertManager for risk gating
try:
    from apps.reference.telemetry.alerts import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    AlertManager = None  # type: ignore

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

chain_logger = logging.getLogger("event_chain")


class DecisionMaking:
    """
    Decision making component that aggregates analytical data streams
    and generates trade intents based on aurora decision logic.
    
    CFG-DOMAINS-STEP-02: Requires AuroraConfig (not dict).
    """

    def __init__(self, fsm: "FSMCore", config: AuroraConfig) -> None:
        """
        Initialize DecisionMaking domain.
        
        Args:
            fsm: Finite State Machine for event emission
            config: AuroraConfig instance (NOT dict)
            
        Raises:
            TypeError: If config is dict (legacy pattern)
        """
        # CFG-DOMAINS-STEP-02-FIX: Reject dict, accept AuroraConfig & subclasses
        if isinstance(config, dict):
            raise TypeError(
                f"DecisionMaking requires AuroraConfig, got dict. "
                "Pass config directly (not config.to_dict())"
            )
        
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None}
        )

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None}
        )

        # NOTE: __init__ continues below (keep attribute initialization contiguous).
        self.latest_portfolio: Optional[Dict[str, Any]] = None
        self.latest_regime: Optional[Dict[str, Any]] = None
        self._last_successful_features_ts: Dict[str, int] = {}  # Idempotency guard
        # Per-symbol regime cache: {symbol: {regime: str, warmup: dict, ...}}
        self._per_symbol_regimes: Dict[str, Dict[str, Any]] = {}
        # Contract State: pending flips {symbol: {desired_open_intent, created_ts, ...}}
        self._pending_flips: Dict[str, Dict[str, Any]] = {}

        # Cache for equity values to prevent zero-overwrite
        self._cached_equity_free_usdt: Optional[str] = None
        self._cached_equity_cross_usdt: Optional[str] = None

        # Risk gate metrics for AlertManager
        self.intents_seen_total: int = 0  # Total intents evaluated
        self.intents_blocked_total: int = 0  # Intents blocked by risk gate
        self.last_alert_check_time: float = time.time()
        self.alert_manager: Optional[AlertManager] = None
        if ALERT_MANAGER_AVAILABLE:
            try:
                self.alert_manager = AlertManager(
                    config=config, logger=self.logger.getChild("alerts"))
                self.logger.info("AlertManager initialized in DecisionMaking")
            except Exception as e:
                self.logger.warning(f"Failed to initialize AlertManager: {e}")

        # QoS state management (PACK EXP-4)
        self._qos_state: dict[str, Any] = {
            "last_exposure_block": 0.0,  # timestamp of last exposure block
            "symbol_cooldowns": {},  # symbol -> last_decision_timestamp
            "symbol_intent_counts": defaultdict(
                lambda: {"count": 0, "window_start": time.time()}
            ),  # symbol -> rate tracking
        }

        # QoS busy guard to prevent infinite defer loops
        # symbol -> ms timestamp
        self._qos_next_allowed_ts: dict[str, int] = {}
        self._deferred_scheduler = DeferredIntentScheduler()

        # Decision logging (DM breadcrumbs)
        self.dlog = DecisionLog()

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
            self.logger.warning("Strategies registry not configured - multi-strategy arbitration disabled")

        # CFG-DOMAINS-STEP-02-FIX: Strict Config Access (Task 18)
        # Direct Pydantic access - overrides handled by ConfigLoader
        trading_config = self.config.trading
        
        # TCA Preferences (Dict)
        self._tca_prefs = trading_config.tca_prefs
        if not self._tca_prefs:
             self.logger.warning("tca_prefs missing/empty - using conservative TCA mode")

        # Risk Budgets (Dict)
        self._risk_budgets = trading_config.risk_budgets
        if not self._risk_budgets:
             self.logger.warning("risk_budgets missing/empty - using conservative sizing mode")

        # CFG-DOMAINS-STEP-02: Domain configuration via DomainConfigResolver (CANONICAL)
        resolver = DomainConfigResolver(self.config)
        dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos

        # Position sizing config - SSOT from domains.yaml
        sizing_cfg = dm_cfg.position_sizing
        self.min_pos_size_usd = decimal.Decimal(str(sizing_cfg.min_position_size_usd))
        self.liq_cap_usd = decimal.Decimal(str(sizing_cfg.liquidity_based_cap_usd))
        
        # QoS exposure cooldown - from canonical domains
        self.qos_exposure_block_cooldown_sec = int(qos_cfg.exposure_block_cooldown_sec)
        
        # QoS max intents - from canonical domains
        self.qos_max_intents_per_minute_per_symbol = int(qos_cfg.max_intents_per_minute_per_symbol)
        
        # QoS mode - from canonical domains
        self.qos_mode = str(qos_cfg.mode)
        
        # Per-symbol cooldown fallback (for symbols not in aurora_instruments)
        # This is the ONLY fallback allowed - new symbols must be added to config
        self._default_symbol_cooldown_sec = int(qos_cfg.symbol_cooldown_sec)

        # Legacy enforce flag (from qos_cfg)
        self.qos_enforce = bool(qos_cfg.enforce)

        # P0-W1: Warmup/arming gate (from domain config)
        self.arming_require_regime_warmup = dm_cfg.arming.require_regime_warmup
        self.arming_retry_backoff_ms = dm_cfg.arming.retry_backoff_ms
        self.arming_max_attempts = dm_cfg.arming.max_attempts
        
        # Features TTL (from domain config)
        self.features_ttl_sec = dm_cfg.features.ttl_sec
        
        self.logger.info(
            f"QoS config: mode={self.qos_mode}, enforce={self.qos_enforce}, "
            f"exposure_cooldown={self.qos_exposure_block_cooldown_sec}s, "
            f"symbol_cooldown=per-symbol (default={self._default_symbol_cooldown_sec}s), "
            f"max_intents_per_min={self.qos_max_intents_per_minute_per_symbol}, "
            f"features_ttl={self.features_ttl_sec}s"
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

        # Signals Config (Strict Object)
        self._normalize_signals = bool(dm_cfg.signals.normalize)

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
        
        # Track B: Initialize Mean Reversion handler (feature-flagged)
        self._mr_handler: Optional[MeanReversionHandler] = None
        if MEAN_REVERSION_AVAILABLE:
            try:
                self._mr_handler = MeanReversionHandler(
                    fsm=self.fsm,
                    config=self.config,
                    decision_making=self
                )
                if self._mr_handler.enabled:
                    self.logger.info(
                        f"✅ MeanReversionHandler enabled for symbols: "
                        f"{list(self._mr_handler._enabled_symbols)}"
                    )
                    # Listen for tick events for MR processing
                    # FIX: MarketDataConnector emits EVT:MARKET_TICK_RECEIVED, not EVT:TICK_RECEIVED
                    self.fsm.listen("EVT:MARKET_TICK_RECEIVED", self._on_tick_for_mr)
                    
                    # STRICT SEQUENTIAL TRADING CONTRACT: Listen for MR signals in gateway mode
                    # When emit_trade_intent_directly=false, MR emits MR_SIGNAL_PRODUCED
                    # and DM applies all gates before emitting TRADE_INTENT_PROPOSED
                    self.fsm.listen("EVT:MR_SIGNAL_PRODUCED", self._on_mr_signal_gateway)
                else:
                    self.logger.info("MeanReversionHandler initialized but disabled by config")
            except Exception as e:
                self.logger.error(
                    f"CRITICAL: MeanReversionHandler FAILED to initialize: {e}. "
                    f"DOGE/XRP MR strategy will NOT trade! Check config/aurora/trading.yaml"
                )
                self._mr_handler = None
                self._mr_init_failed = True  # Flag for health checks
        else:
            self.logger.debug("MeanReversion module not available")

    def _on_tick_for_mr(self, event: Message) -> None:
        """
        Forward tick events to Mean Reversion handler.
        
        Track B: Wiring tick → BarResampler → MRSignal → TradeIntent
        """
        if not self._mr_handler or not self._mr_handler.enabled:
            return
        
        try:
            pld = event.pld
            if isinstance(pld, dict):
                symbol = pld.get("symbol", "")
                price = Decimal(str(pld.get("price", 0)))
                # Market tick contract uses `ts` (ms), not `timestamp_ms`.
                raw_ts = pld.get("timestamp_ms")
                if raw_ts in (None, 0, "0", ""):
                    raw_ts = pld.get("ts")
                timestamp_ms = int(raw_ts or 0)

                # Backward/forward compat: if ts is accidentally seconds, normalize to ms.
                # (Binance timestamps are ms; seconds here would stall BarResampler for hours.)
                if 0 < timestamp_ms < 1_000_000_000_000:
                    timestamp_ms = timestamp_ms * 1000

                # Market tick contract has buy/sell volumes, not a single `volume`.
                raw_vol = pld.get("volume")
                if raw_vol is None:
                    try:
                        bv = Decimal(str(pld.get("buy_volume", "0") or "0"))
                        sv = Decimal(str(pld.get("sell_volume", "0") or "0"))
                        raw_vol = bv + sv
                    except Exception:
                        raw_vol = Decimal("0")
                volume = Decimal(str(raw_vol or 0))
            elif hasattr(pld, 'symbol'):
                symbol = pld.symbol
                price = Decimal(str(getattr(pld, 'price', 0)))
                timestamp_ms = int(getattr(pld, 'timestamp_ms', 0) or getattr(pld, 'ts', 0) or 0)
                if 0 < timestamp_ms < 1_000_000_000_000:
                    timestamp_ms = timestamp_ms * 1000
                raw_vol = getattr(pld, 'volume', None)
                if raw_vol is None:
                    raw_vol = (getattr(pld, 'buy_volume', 0) or 0) + (getattr(pld, 'sell_volume', 0) or 0)
                volume = Decimal(str(raw_vol or 0))
            else:
                return
            
            if not symbol or not self._mr_handler.is_symbol_enabled(symbol):
                return
            
            # Get current regime for this symbol
            regime = None
            if symbol in self._per_symbol_regimes:
                regime = self._per_symbol_regimes[symbol].get("regime")
            elif self.latest_regime and isinstance(self.latest_regime, dict):
                regime = self.latest_regime.get("regime") or self.latest_regime.get("overall_regime")
            
            # Process tick through MR handler
            self._mr_handler.on_tick(symbol, price, volume, timestamp_ms, regime)
            
        except Exception as e:
            self.logger.warning(f"Error processing tick for MR: {e}")

    def _on_mr_signal_gateway(self, event: Message) -> None:
        """
        Gateway for MR signals: apply all gates before emitting TRADE_INTENT_PROPOSED.
        
        STRICT SEQUENTIAL TRADING CONTRACT (Commit 3):
        When emit_trade_intent_directly=false, MR emits EVT:MR_SIGNAL_PRODUCED.
        This handler applies the same gates as Aurora/Track A:
        1. Risk gate (is_trading_allowed, risk_score)
        2. Regime gate (check regime compatibility)
        3. QoS gate (cooldown, rate limiting)
        4. Exposure gate (portfolio limits)
        5. TTL gate (features freshness)
        
        Only after passing all gates, emit EVT:TRADE_INTENT_PROPOSED.
        """
        try:
            pld = event.pld
            if not isinstance(pld, dict):
                self.logger.warning("MR_SIGNAL_PRODUCED: invalid payload (not dict)")
                return
            
            symbol = pld.get("symbol")
            side = pld.get("side")
            rid = pld.get("rid", f"mr-{int(time.time())}")
            why_chain = pld.get("why_chain", [])
            
            if not symbol or not side:
                self.logger.warning(f"MR_SIGNAL_PRODUCED: missing symbol or side")
                return
            
            self.logger.info(f"[{symbol}] MR_SIGNAL_GATEWAY: Processing {side} signal rid={rid}")

            # === GATE 0: STRATEGY ARBITRATION ===
            # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Check if this strategy is allowed
            arbitration_result = self._check_strategy_arbitration(symbol, "mean_reversion_1m")
            if not arbitration_result["allowed"]:
                self.logger.info(
                    f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Strategy arbitration blocked: {arbitration_result['reason']}"
                )
                self._record_blocked_intent(symbol)
                return

            # Risk-skew limiter escalation state (Commit 5):
            # if until_refresh is active, fail-closed for this symbol until a new risk/features refresh clears it.
            guard_state = self.symbol_states[symbol].get("risk_skew_guard") or {}
            if guard_state.get("until_refresh"):
                now_ms = int(time.time() * 1000)
                retry_key = self._stable_retry_key(
                    prefix="mr",
                    symbol=symbol,
                    rid=rid,
                    side=side,
                    ts_ms=pld.get("ts"),
                )
                retry_sec = self._get_risk_skew_config("until_refresh_retry_sec", 30)
                self.logger.error(
                    f"[{symbol}] MR_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH (risk_skew_guard active)"
                )
                self._emit_intent_deferred_v1(
                    symbol=symbol,
                    reason="NRR-RISK-SKEW-UNTIL-REFRESH",
                    retry_key=retry_key,
                    next_allowed_ts=now_ms + int(retry_sec * 1000),
                    original_event_name="EVT:MR_SIGNAL_PRODUCED",
                    original_payload_min=dict(pld),
                    attempt=1,
                    max_attempts=5,
                    why_chain=(why_chain or []) + ["NO_TRADE_UNTIL_REFRESH", "risk_skew_guard"],
                    context="mr_signal_gateway:risk_skew_until_refresh",
                )
                self._record_blocked_intent(symbol)
                return
            
            # === GATE 1: RISK GATE ===
            # Use symbol_states SSOT (not self.latest_risk which doesn't exist)
            latest_risk = self.symbol_states[symbol].get("risk")
            
            # Fail-closed: if risk data not yet received, DEFER instead of crash
            if not latest_risk:
                self.logger.warning(
                    f"[{symbol}] MR_SIGNAL_GATEWAY: DEFER - Risk data not yet received (NRR-DATA-NOT-READY)"
                )
                now_ms = int(time.time() * 1000)
                retry_key = self._stable_retry_key(
                    prefix="mr",
                    symbol=symbol,
                    rid=rid,
                    side=side,
                    ts_ms=pld.get("ts"),
                )
                self._emit_intent_deferred_v1(
                    symbol=symbol,
                    reason="NRR-DATA-NOT-READY",
                    retry_key=retry_key,
                    next_allowed_ts=now_ms + 500,
                    original_event_name="EVT:MR_SIGNAL_PRODUCED",
                    original_payload_min=dict(pld),
                    attempt=1,
                    max_attempts=5,
                    why_chain=(why_chain or []) + ["missing:risk", "fail_closed"],
                    context="mr_signal_gateway:risk_not_ready",
                )
                self._record_blocked_intent(symbol)
                return
            
            if latest_risk:
                is_allowed = latest_risk.get("risk_parameters", {}).get("is_trading_allowed", True)
                risk_score = float(latest_risk.get("risk_parameters", {}).get("risk_score", 0))
                
                if not is_allowed:
                    self.logger.warning(
                        f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Risk gate blocked, is_trading_allowed=False"
                    )
                    self._record_blocked_intent(symbol)
                    return
                
                # Check risk score threshold (use aurora_instruments if available)
                # Check risk score threshold (use aurora_instruments if available)
                # Check risk score threshold (use aurora_instruments if available)
                # P1 FIX: No hardcoded default (was 0.96). Fail closed if config missing.
                # Must check GLOBAL SSOT if instrument override is missing.
                # If both missing -> BLOCK.
                max_risk = -1.0
                try:
                    instr_cfg = self._get_aurora_instrument_config(symbol)
                    if instr_cfg and hasattr(instr_cfg, 'max_risk_score'):
                        max_risk = float(instr_cfg.max_risk_score)
                    else:
                        # Fallback to Global SSOT (Config Contract)
                        # We must fetch the global max_risk_score from config
                        try:
                             # Access global config via self.config (passed in init)
                             # self.config is likely AuroraConfig or dict
                             # But DecisionMaking stores self.config
                             # Let's inspect self.config structure or assume Pydantic path
                             # Based on risk_management.py: domains.risk_management.trading_allowed_thresholds.max_risk_score
                             # We need to access it safely.
                             g_cfg = self.config
                             if hasattr(g_cfg, 'domains'):
                                 max_risk = float(g_cfg.domains.risk_management.trading_allowed_thresholds.max_risk_score)
                             else:
                                 # Dict access fallback
                                 max_risk = float(g_cfg["domains"]["risk_management"]["trading_allowed_thresholds"]["max_risk_score"])
                        except Exception as e:
                             raise ConfigContractError(
                                 path="domains.risk_management.trading_allowed_thresholds.max_risk_score",
                                 why=f"Global fallback missing: {e}",
                                 symbol=symbol
                             )
                except Exception as e:
                    self.logger.error(f"Config Contract Violation: {e}")
                    self._record_blocked_intent(symbol)
                    return # BLOCK TRADE
                
                if risk_score > max_risk:
                    self.logger.warning(
                        f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Risk score {risk_score:.3f} > {max_risk}"
                    )
                    self._record_blocked_intent(symbol)
                    return
                
                # === GATE 1.5: RISK SKEW GATE (Commit 5) ===
                # Check if risk.ts is too far from features.ts (stale risk data)
                risk_ts = latest_risk.get("ts", 0)
                # Use symbol_states SSOT (not self.latest_features which doesn't exist)
                features_data = self.symbol_states[symbol].get("features") or {}
                features_ts = features_data.get("ts", 0)
                
                if risk_ts > 0 and features_ts > 0:
                    skew_sec = abs(features_ts - risk_ts) / 1000
                    max_skew_sec = self._get_risk_skew_config("max_skew_sec", 5)
                    
                    if skew_sec > max_skew_sec:
                        max_defer = self._get_risk_skew_config("max_defer_count", 3)

                        # Track limiter state per symbol in symbol_states (SSOT)
                        now_ms = int(time.time() * 1000)
                        window_sec = self._get_risk_skew_config("defer_window_sec", 60)
                        state = self.symbol_states[symbol].setdefault(
                            "risk_skew_guard",
                            {"defer_count": 0, "window_start_ms": now_ms, "until_refresh": False},
                        )

                        try:
                            window_start_ms = int(state.get("window_start_ms", now_ms))
                        except Exception:
                            window_start_ms = now_ms
                            state["window_start_ms"] = now_ms

                        if now_ms - window_start_ms > int(window_sec * 1000):
                            state["defer_count"] = 0
                            state["window_start_ms"] = now_ms

                        try:
                            state["defer_count"] = int(state.get("defer_count", 0)) + 1
                        except Exception:
                            state["defer_count"] = 1

                        defer_count = int(state.get("defer_count", 1))
                        
                        if defer_count >= max_defer:
                            state["until_refresh"] = True
                            self.logger.error(
                                f"[{symbol}] MR_SIGNAL_GATEWAY: NO_TRADE_UNTIL_REFRESH - "
                                f"Risk skew exceeded {defer_count} times (max {max_defer}). "
                                f"NRR-RISK-STALE skew={skew_sec:.1f}s > max={max_skew_sec}s"
                            )
                        else:
                            self.logger.warning(
                                f"[{symbol}] MR_SIGNAL_GATEWAY: DEFER - "
                                f"NRR-RISK-STALE skew={skew_sec:.1f}s > max={max_skew_sec}s. "
                                f"Defer {defer_count}/{max_defer}"
                            )
                            now_ms = int(time.time() * 1000)
                            retry_key = self._stable_retry_key(
                                prefix="mr",
                                symbol=symbol,
                                rid=rid,
                                side=side,
                                ts_ms=pld.get("ts"),
                            )
                            cooldown_sec = self._get_risk_skew_config("defer_cooldown_sec", 2)
                            self._emit_intent_deferred_v1(
                                symbol=symbol,
                                reason="NRR-RISK-STALE",
                                retry_key=retry_key,
                                next_allowed_ts=now_ms + int(cooldown_sec * 1000),
                                original_event_name="EVT:MR_SIGNAL_PRODUCED",
                                original_payload_min=dict(pld),
                                attempt=defer_count,
                                max_attempts=max_defer,
                                why_chain=(why_chain or [])
                                + [
                                    "risk_skew",
                                    f"skew_sec:{skew_sec:.3f}",
                                    f"defer_count:{defer_count}",
                                ],
                                context="mr_signal_gateway:risk_skew",
                            )
                        self._record_blocked_intent(symbol)
                        return
            
            # === GATE 2: REGIME GATE ===
            regime_data = self._per_symbol_regimes.get(symbol, {})
            current_regime = regime_data.get("regime")
            
            # MR symbols only allowed in FLAT regimes
            # MR symbols allowed regimes (SSOT from config)
            mr_allowed_regimes = self._get_mr_allowed_regimes(symbol)
            
            if current_regime and current_regime not in mr_allowed_regimes:
                self.logger.info(
                    f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Regime {current_regime} not in MR allowed list"
                )
                self._record_blocked_intent(symbol)
                return
            
            # === GATE 2.5: FLAT/FLIP GATE (D3 - Flip Orchestration) ===
            # OPEN only allowed when position_state(symbol) == FLAT
            # If opposite-side position exists → initiate flip (close→wait→open)
            # If same-side position exists → BLOCK (anti-pyramiding)
            flip_result = self._handle_flip_orchestration(
                symbol=symbol,
                intent_side=side,
                original_pld=pld,
                source="mr"
            )
            
            if flip_result:
                # Intent was blocked or deferred
                if flip_result == "FLIP_CLOSE_PENDING":
                    self.logger.info(
                        f"[{symbol}] MR_SIGNAL_GATEWAY: FLIP initiated - close emitted, OPEN deferred"
                    )
                elif flip_result == "ANTI_PYRAMIDING_BLOCK":
                    self.logger.warning(
                        f"[{symbol}] MR_SIGNAL_GATEWAY: BLOCK - Same-side pyramiding not allowed"
                    )
                else:
                    # NRR-PORTFOLIO-UNKNOWN or other
                    self.logger.warning(
                        f"[{symbol}] MR_SIGNAL_GATEWAY: BLOCK - {flip_result}"
                    )
                    if flip_result == "NRR-PORTFOLIO-UNKNOWN":
                        now_ms = int(time.time() * 1000)
                        # Position Tracking Stale TTL (Strict)
                        stale_ttl_sec_f = float(getattr(self.config.domains.position_tracking, 'positions_stale_ttl_sec', 5.0))
                        retry_key = self._stable_retry_key(
                            prefix="mr",
                            symbol=symbol,
                            rid=rid,
                            side=side,
                            ts_ms=pld.get("ts"),
                        )
                        self._emit_intent_deferred_v1(
                            symbol=symbol,
                            reason="NRR-PORTFOLIO-UNKNOWN",
                            retry_key=retry_key,
                            next_allowed_ts=now_ms + int(stale_ttl_sec_f * 1000),
                            original_event_name="EVT:MR_SIGNAL_PRODUCED",
                            original_payload_min=dict(pld),
                            attempt=1,
                            max_attempts=5,
                            why_chain=(why_chain or []) + ["portfolio_unknown", "fail_closed"],
                            context="mr_gateway_flip_check",
                        )
                
                self._record_blocked_intent(symbol)
                return
            
            # === GATE 3: QOS GATE ===
            qos_allowed, qos_reason = self._qos_allow(symbol)
            if not qos_allowed:
                self.logger.info(f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - QoS blocked: {qos_reason}")
                self._record_blocked_intent(symbol)
                return
            
            # === GATE 4: EXPOSURE GATE (pre-check) ===
            # P1 FIX: No default 100.0. Signal must provide size or we block/error.
            # Using get() without default returns None if missing, so we check robustness
            position_size_usd = pld.get("position_size_usd")
            if position_size_usd is None:
                 self.logger.warning(f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Missing position_size_usd")
                 self._record_blocked_intent(symbol)
                 return
            
            if not self._precheck_exposure_cache(symbol, side, float(position_size_usd)):
                self.logger.info(f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Exposure limit exceeded")
                self._record_blocked_intent(symbol)
                return
            
            # === GATE 5: TTL GATE (features freshness) ===
            # Use symbol_states SSOT (not self.latest_features which doesn't exist)
            features_data = self.symbol_states[symbol].get("features") or {}
            features_ts = features_data.get("ts", 0)
            current_ms = int(time.time() * 1000)
            features_age_sec = (current_ms - features_ts) / 1000 if features_ts > 0 else float('inf')
            
            if features_age_sec > self.features_ttl_sec:
                self.logger.info(
                    f"[{symbol}] MR_SIGNAL_GATEWAY: REJECT - Features stale "
                    f"(age={features_age_sec:.1f}s > ttl={self.features_ttl_sec}s)"
                )
                self._record_blocked_intent(symbol)
                return
            
            # === ALL GATES PASSED: EMIT TRADE_INTENT_PROPOSED ===
            self.logger.info(f"[{symbol}] MR_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED")
            
            price_ctx = pld.get("price_ctx", {})
            
            trade_intent = {
                "instrument": symbol,
                "symbol": symbol,
                "side": side,
                "order": {
                    "qty": str(pld.get("qty_hint", "0")),
                    "price": str(price_ctx.get("entry_price", "0")),
                    "type": "LIMIT"
                },
                "strategy": "mean_reversion_1m",
                "strategy_id": "MR",
                "source": "dm_gateway",  # Indicates came through DM gateway
                "entry_price": str(price_ctx.get("entry_price")),
                "stop_price": str(price_ctx.get("stop_price")) if price_ctx.get("stop_price") else None,
                "target_price": str(price_ctx.get("target_price")) if price_ctx.get("target_price") else None,
                "position_size_usd": position_size_usd,
                "qty": str(pld.get("qty_hint", "0")),
                "regime": pld.get("flat_regime", "UNKNOWN"),
                "confidence": pld.get("confidence", 0.0),
                "rid": rid,
                "timestamp_ms": pld.get("ts", int(time.time() * 1000)),
                "why": ",".join(why_chain) if isinstance(why_chain, list) else str(why_chain),
                "why_chain": why_chain,
                "cooldown_class": pld.get("cooldown_class", "mr_entry"),
                "mr_params": pld.get("mr_params", {}),
            }
            
            self.fsm.emit(
                "EVT:TRADE_INTENT_PROPOSED",
                payload=trade_intent,
                why=f"MR_GATEWAY_{side}",
                data_ref=[f"mr_gateway_{rid}"]
            )
            
            self._record_accepted_intent(symbol)
            self._record_qos_intent(symbol)  # Update QoS state
            
            self.logger.info(
                f"[{symbol}] MR_SIGNAL_GATEWAY: EVT:TRADE_INTENT_PROPOSED emitted: {side}"
            )
            
        except ConfigContractError as e:
            # TASK 17: Central Interception Point for Config Contract Violations
            # 1. Normalize Reason
            reason = normalize_config_error(e)
            
            # 2. Block Trade (Implicitly by not emitting INTENT_PROPOSED and returning)
            
            # 3. Metric & Log
            caught_symbol = e.symbol or symbol
            inc_config_contract_violation(path=e.path or "unknown", symbol=caught_symbol or "unknown")
            self.logger.critical(f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            
            # 4. Record blocked intent (optional but good for visibility)
            if caught_symbol:
                self._record_blocked_intent(caught_symbol)
            return

        except Exception as e:
            self.logger.error(f"MR_SIGNAL_GATEWAY error: {e}", exc_info=True)

    def _qos_allow(
        self, symbol: str, is_exposure_block: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Check if decision is allowed based on QoS rules (PACK EXP-4).

        Args:
            symbol: Trading symbol
            is_exposure_block: Whether this check is due to exposure block

        Returns:
            Tuple of (allowed: bool, reject_reason: Optional[str])
        """
        current_time = time.time()

        # Check exposure block cooldown (only for exposure-related checks)
        if is_exposure_block:
            last_exposure_block: float = float(
                self._qos_state.get("last_exposure_block", 0.0))
            time_since_last_block = current_time - last_exposure_block
            if time_since_last_block < self.qos_exposure_block_cooldown_sec:
                remaining = self.qos_exposure_block_cooldown_sec - time_since_last_block
                reject_reason = (
                    f"exposure_block_cooldown_active_{remaining:.1f}s_remaining"
                )
                self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
                return False, NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

        # Check symbol cooldown (prevents rapid-fire decisions for same symbol)
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        time_since_last_decision = current_time - last_decision
        symbol_cooldown_limit = self._get_symbol_cooldown(symbol)
        if time_since_last_decision < symbol_cooldown_limit:
            remaining = symbol_cooldown_limit - time_since_last_decision
            reject_reason = f"symbol_cooldown_active_{remaining:.1f}s_remaining_limit={symbol_cooldown_limit}s"
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            # Return RATE_LIMIT_EXCEEDED for backward compatibility, but distinguish cooldown from rate limit
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        # Check rate limit (intents per minute per symbol) - separate from cooldown
        symbol_intent_counts: dict[str, Any] = self._qos_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts[symbol]
        window_elapsed = current_time - \
            intent_data.get("window_start", current_time)

        # Reset window if more than a minute has passed
        if window_elapsed >= 60:
            intent_data["count"] = 0
            intent_data["window_start"] = current_time

        if intent_data["count"] >= self.qos_max_intents_per_minute_per_symbol:
            reject_reason = (
                f"rate_limit_exceeded_{intent_data['count']}_intents_in_window"
            )
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        return True, None

    def _update_symbol_cooldown(self, symbol: str) -> None:
        """Update cooldown timestamp for symbol (prevents rapid-fire decisions)."""
        current_time = time.time()
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        symbol_cooldowns[symbol] = current_time
        self.logger.debug(
            f"[{symbol}] QoS cooldown updated: ts={current_time}")

    def _ensure_after_cooldown_retry(self, symbol: str, context: dict, rid: str) -> None:
        """Schedule one-time retry after QoS cooldown expires."""
        next_allowed_ts = self._calculate_next_allowed_time(symbol)
        cooldown_sec = max(0, next_allowed_ts - int(time.time() * 1000)) / 1000

        self.logger.info(
            f"[{symbol}] Scheduling QoS retry in {cooldown_sec:.1f}s (ts={next_allowed_ts})"
        )

        # Schedule one-time retry using DeferredIntentScheduler
        def retry_callback(rid_arg: str) -> None:
            self._retry_decision_after_cooldown(symbol, context, rid_arg)

        self._deferred_scheduler.schedule_once(
            symbol,
            int(cooldown_sec * 1000),
            retry_callback
        )

    def _retry_decision_after_cooldown(self, symbol: str, context: dict, rid: str) -> None:
        """Retry decision after cooldown period."""
        self.logger.info(
            f"[{symbol}] Retrying decision after cooldown - RID: {rid}")

        # Clear any cached state that might prevent re-decision
        if symbol in self.symbol_states:
            # Keep features and risk data fresh, but clear any deferral flags
            pass

        # Re-run decision logic
        self._make_decision_for_symbol(symbol, context, rid)

    def _update_intent_count(self, symbol: str) -> None:
        """Update intent count for rate limiting."""
        symbol_intent_counts: dict[str, Any] = self._qos_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(
            symbol, {"count": 0, "window_start": time.time()})
        intent_data["count"] += 1
        self.logger.debug(
            f"[{symbol}] QoS intent count updated: count={intent_data['count']}"
        )

    def _check_qos_rules(self, symbol: str) -> dict:
        """Check QoS rules for symbol and return result dict."""
        current_time = time.time()

        # Check exposure block cooldown
        last_exposure_block: float = float(
            self._qos_state.get("last_exposure_block", 0.0))
        if current_time - last_exposure_block < self.qos_exposure_block_cooldown_sec:
            return {"allowed": False, "reason": NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED}

        # Check symbol cooldown (per-symbol limit)
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        symbol_cooldown_limit = self._get_symbol_cooldown(symbol)
        if current_time - last_decision < symbol_cooldown_limit:
            return {"allowed": False, "reason": NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE}

        # Check rate limit
        symbol_intent_counts: dict[str, Any] = self._qos_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(
            symbol, {"count": 0, "window_start": current_time})
        window_end: float = float(intent_data.get(
            "window_start", current_time)) + 60
        intent_count: int = int(intent_data.get("count", 0))
        if current_time < window_end and intent_count >= self.qos_max_intents_per_minute_per_symbol:
            return {"allowed": False, "reason": NormalizedRejectReasons.RATE_LIMIT_EXCEEDED}

        return {"allowed": True, "reason": None}

    def _calculate_next_allowed_time(self, symbol: str) -> int:
        """Calculate next allowed timestamp for symbol based on QoS rules."""
        current_time = time.time()
        next_allowed = current_time

        # Check symbol cooldown (uses per-symbol resolver)
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        cooldown_duration = self._get_symbol_cooldown(symbol)

        cooldown_end: float = last_decision + cooldown_duration
        next_allowed = max(next_allowed, cooldown_end)

        # Check rate limit window
        symbol_intent_counts: dict[str, Any] = self._qos_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(
            symbol, {"count": 0, "window_start": current_time})
        window_end: float = float(intent_data.get(
            "window_start", current_time)) + 60
        intent_count: int = int(intent_data.get("count", 0))
        if intent_count >= self.qos_max_intents_per_minute_per_symbol:
            next_allowed = max(next_allowed, window_end)

        return int(next_allowed * 1000)  # Convert to milliseconds

    def _update_qos_state(self, symbol: str) -> None:
        """Update QoS state after making a decision."""
        current_time = time.time()

        # Update symbol cooldown
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        symbol_cooldowns[symbol] = current_time

        # Update rate limit counters
        symbol_intent_counts: dict[str, Any] = self._qos_state.get(
            "symbol_intent_counts", {})
        intent_data: dict[str, Any] = symbol_intent_counts.get(
            symbol, {"count": 0, "window_start": current_time})
        window_start: float = float(
            intent_data.get("window_start", current_time))
        window_end: float = window_start + 60

        if current_time >= window_end:
            # Reset window
            intent_data["window_start"] = current_time
            intent_data["count"] = 1
        else:
            intent_data["count"] += 1

        self.logger.debug(
            f"[{symbol}] QoS state updated: cooldown={current_time}, intents={intent_data['count']}")

    def _handle_exposure_block(self, symbol: str) -> None:
        """Handle exposure block event by updating QoS state."""
        current_time = time.time()
        self._qos_state["last_exposure_block"] = current_time
        self.logger.warning(
            f"[{symbol}] Exposure block recorded at {current_time}")

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

    def _get_aurora_instrument_cfg(self, symbol: str) -> Optional[AuroraInstrumentConfig]:
        """
        Get per-instrument Aurora configuration for a symbol.

        Fallback chain:
        1. config.aurora_instruments[SYMBOL] (CANONICAL SSOT from aurora_instruments.yaml)
        2. None (caller falls back to global trading.decision.*)

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            AuroraInstrumentConfig or None if not configured
        """
        # CFG-AURORA-INSTRUMENTS-SSOT-01-FIXPACK: Direct Pydantic access (no safe_get)
        if not self.config or not hasattr(self.config, 'aurora_instruments'):
            return None
        
        aurora_instruments = self.config.aurora_instruments
        if not isinstance(aurora_instruments, dict):
            return None
        
        return aurora_instruments.get(symbol)  # Already Pydantic-typed, no conversion needed

    def _check_strategy_arbitration(self, symbol: str, strategy_id: str) -> Dict[str, Any]:
        """
        Check if strategy is allowed to generate intent for symbol based on arbitration rules.
        
        CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Implements deterministic arbitration.
        
        Args:
            symbol: Trading pair symbol
            strategy_id: Strategy identifier ("aurora", "mean_reversion_1m")
            
        Returns:
            Dict with keys:
            - allowed (bool): Whether strategy can proceed
            - reason (str): If blocked, why (≤80 chars)
        """
        # If no strategies registry, allow (backward compat)
        if not self.strategies_registry:
            return {"allowed": True, "reason": ""}
        
        # Get assigned strategies for this symbol
        assignments = self.strategies_registry.assignments.get(symbol, [])
        
        # If symbol not in registry, block (fail-closed)
        if not assignments:
            return {
                "allowed": False, 
                "reason": f"ARBITRATION_REJECT:symbol_not_in_registry"
            }
        
        # If strategy not assigned to symbol, block
        if strategy_id not in assignments:
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:strategy_not_assigned_to_symbol"
            }
        
        # If only one strategy assigned, always allow
        if len(assignments) == 1:
            return {"allowed": True, "reason": ""}
        
        # Multi-strategy case: check arbitration
        arb = self.strategies_registry.arbitration
        
        if arb.mode == "priority":
            # Fail-closed: check that all assigned strategies have priorities
            for strat in assignments:
                if strat not in arb.priority:
                    return {
                        "allowed": False,
                        "reason": f"ARBITRATION_REJECT:missing_priority:{strat}"[:80]
                    }
            
            # Get priorities for all assigned strategies
            priorities = {s: arb.priority.get(s, 999) for s in assignments}
            
            # Current strategy priority
            current_priority = priorities.get(strategy_id, 999)
            
            # Find highest priority strategy (lowest number)
            highest_priority_strategy = min(assignments, key=lambda s: priorities.get(s, 999))
            highest_priority = priorities[highest_priority_strategy]
            
            # Allow if current strategy has highest priority
            if current_priority == highest_priority:
                return {"allowed": True, "reason": ""}
            else:
                return {
                    "allowed": False,
                    "reason": f"{arb.logging.rejected_why_prefix}:priority_{highest_priority_strategy}_wins"[:80]
                }
        else:
            # Unknown arbitration mode - fail-closed (defense-in-depth)
            return {
                "allowed": False,
                "reason": f"ARBITRATION_REJECT:unknown_mode_{arb.mode}"[:80]
            }

    def _get_mr_allowed_regimes(self, symbol: str) -> List[str]:
        """
        Get allowed regimes for MR strategy (SSOT).
        
        Fallback chain:
        1. mean_reversion_1m.assets.<SYMBOL>.allowed_regimes
        2. mean_reversion_1m.allowed_regimes (Global)
        3. Hardcoded default
        """
        default_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
        
        default_regimes = ["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH", "MEAN_REVERSION"]
        
        # Strict Config Access
        mr_config = self.config.mean_reversion_1m
        if not mr_config:
             return default_regimes

        # 1. Asset Override
        if symbol in mr_config.assets:
             asset_cfg = mr_config.assets[symbol]
             if asset_cfg.allowed_regimes:
                 return asset_cfg.allowed_regimes

        # 2. Global Config
        if mr_config.allowed_regimes:
             return mr_config.allowed_regimes

        return default_regimes

    def _get_symbol_cooldown(self, symbol: str) -> int:
        """
        Get per-symbol cooldown in seconds.

        Fallback chain:
        1. aurora_instruments.<SYMBOL>.cooldown_sec (per-instrument config)
        2. self._default_symbol_cooldown_sec (safe default = 3s)

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            Cooldown duration in seconds
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            cooldown = getattr(instr_cfg, 'cooldown_sec', None)
            if cooldown is not None:
                return int(cooldown)

        # 2. Fallback to safe default
        return self._default_symbol_cooldown_sec

    def _get_param(self, symbol: str, param: str, default: Any) -> Any:
        """
        Get configuration parameter with per-instrument override support.

        Fallback chain:
        1. aurora_instruments.<SYMBOL>.<param>
        2. trading.decision.<param> (global)
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
            value = getattr(instr_cfg, param, None)
            if value is not None:
                return value

        # 2. Fallback to global trading.decision.* (Strict)
        global_value = getattr(self.config.trading.decision, param, default)
        return global_value if global_value is not None else default

    def _get_side_bias_params(self, symbol: str) -> tuple:
        """
        Get side_bias parameters with per-instrument override.

        Fallback chain:
        1. aurora_instruments.<SYMBOL>.side_bias.* (per-instrument)
        2. trading.decision.side_bias_* (global)
        3. defaults

        Returns:
            (penalty_factor, window_sec, target_ratio)
        """
        # Defaults
        default_penalty = 0.50
        default_window = 60
        default_target = 0.60

        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None and getattr(instr_cfg, 'side_bias', None) is not None:
            sb = instr_cfg.side_bias
            penalty = getattr(sb, 'penalty_factor', None)
            window = getattr(sb, 'window_sec', None)
            target = getattr(sb, 'target_ratio', None)
            return (
                penalty if penalty is not None else default_penalty,
                window if window is not None else default_window,
                target if target is not None else default_target
            )

        # 2. Fallback to global
        # 2. Fallback to global (Strict Object)
        dm = self.config.trading.decision
        penalty = dm.side_bias_penalty_factor if dm.side_bias_penalty_factor is not None else default_penalty
        window = dm.side_bias_window_sec if dm.side_bias_window_sec is not None else default_window
        target = dm.side_bias_target_ratio if dm.side_bias_target_ratio is not None else default_target
        return (penalty, window, target)

    def _get_regime_thresholds(self, symbol: str) -> dict:
        """
        Get regime threshold multipliers with per-instrument override.

        Fallback chain:
        1. aurora_instruments.<SYMBOL>.regime_thresholds
        2. trading.decision.regime_threshold_multipliers (global)
        3. empty dict

        Returns:
            Dict mapping regime names to threshold multipliers
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            thresholds = getattr(instr_cfg, 'regime_thresholds', None)
            if thresholds is not None:
                return thresholds

        # 2. Fallback to global (Strict Object)
        dm = self.config.trading.decision
        global_thresholds = dm.regime_threshold_multipliers if dm.regime_threshold_multipliers is not None else {}
        return global_thresholds

    def _get_regime_sizing(self, symbol: str) -> dict:
        """
        Get regime sizing multipliers with per-instrument override.

        Fallback chain:
        1. aurora_instruments.<SYMBOL>.regime_sizing
        2. trading.decision.sizing_modifiers (global)
        3. empty dict

        Returns:
            Dict mapping regime names to sizing multipliers
        """
        # 1. Try per-instrument config
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            sizing = getattr(instr_cfg, 'regime_sizing', None)
            if sizing is not None:
                # Convert Pydantic model to dict if needed
                if hasattr(sizing, 'model_dump'):
                    return sizing.model_dump(exclude_none=True)
                elif isinstance(sizing, dict):
                    return sizing

        # 2. Fallback to global (Strict Object)
        dm = self.config.trading.decision
        global_sizing = dm.sizing_modifiers if dm.sizing_modifiers is not None else {}
        return global_sizing

    def _get_signal_threshold(self, symbol: str) -> decimal.Decimal:
        """
        Get signal threshold with per-instrument override (Phase 3+).

        Fallback chain:
        1. aurora_instruments.<SYMBOL>.signal_threshold (if enabled=True)
        2. trading.decision.signal_threshold (global - REQUIRED field)

        Returns:
            Signal threshold as Decimal
        
        Raises:
            AttributeError: If trading.decision.signal_threshold missing (fail-closed)
        """
        # 1. Try per-instrument config (Phase 3+)
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg is not None:
            st_cfg = getattr(instr_cfg, 'signal_threshold', None)
            if st_cfg is not None and st_cfg.enabled:
                if st_cfg.value is not None:
                    return decimal.Decimal(str(st_cfg.value))

        # 2. Direct Pydantic access (fail-closed: missing field → AttributeError)
        decision_config = self.config.trading.decision
        return decimal.Decimal(str(decision_config.signal_threshold))

    def _compute_risk_contract_cap_notional(
        self, symbol: str, equity: decimal.Decimal
    ) -> Optional[decimal.Decimal]:
        """
        Compute max notional cap based on risk_contract_v1 config.
        
        ETAP3: Cap = per_symbol_margin_fraction * equity * effective_leverage
        No fixed_notional_usd in runtime.
        
        Args:
            symbol: Trading pair symbol
            equity: Current account equity
            
        Returns:
            Decimal cap if risk_contract_v1 is enabled and symbol is configured,
            None otherwise (caller falls back to legacy sizing).
        """
        # Strict Config Access
        try:
             # trading.decision.position_sizing.risk_contract_v1
             rc = self.config.trading.decision.position_sizing.risk_contract_v1
        except AttributeError:
             rc = None
        
        if rc is None:
            return None
        
        # Direct Pydantic access only (fail-closed: missing field → AttributeError)
        if not rc.enabled:
            return None
        
        if equity <= 0:
            self.logger.warning(
                f"[{symbol}] risk_contract_v1 enabled but equity<=0, fallback to legacy sizing"
            )
            return None
        
        # Cap = per_symbol_margin_fraction * equity * effective_leverage
        try:
            margin_fracs = rc.per_symbol_margin_fraction or {}
            leverage = rc.effective_leverage
            
            margin_frac = margin_fracs.get(symbol)
            if margin_frac is None or margin_frac <= 0:
                self.logger.debug(
                    f"[{symbol}] not configured in risk_contract_v1.per_symbol_margin_fraction"
                )
                return None
            
            cap = (
                decimal.Decimal(str(margin_frac)) 
                * equity 
                * decimal.Decimal(str(leverage))
            )
            return cap if cap > 0 else None
            
        except Exception as e:
            self.logger.debug(f"[{symbol}] Error computing margin cap: {e}")
            return None

    def _compute_regime_scaled_notional(
        self,
        symbol: str,
        equity: decimal.Decimal,
        volatility_state: Optional[str],
        cap_notional: Optional[decimal.Decimal],
    ) -> Optional[decimal.Decimal]:
        """
        Compute regime-scaled notional based on volatility state (ETAP3).
        
        If regime_sizing is enabled for this symbol, computes:
        - base = margin_frac * equity * leverage
        - target = base * multiplier(volatility_state)
        - capped by cap_notional
        
        Args:
            symbol: Trading pair symbol
            equity: Current account equity
            volatility_state: Volatility regime (HIGH_VOLATILITY, LOW_VOLATILITY, etc)
            cap_notional: Cap from _compute_risk_contract_cap_notional
            
        Returns:
            Decimal target if regime sizing enabled for symbol,
            None otherwise (caller uses ETAP2 logic: cap-only).
        """
        # Strict Config Access
        try:
             # trading.decision.position_sizing.risk_contract_v1
             rc = self.config.trading.decision.position_sizing.risk_contract_v1
        except AttributeError:
             rc = None
        
        if rc is None:
            return None
        
        # Direct Pydantic access only (fail-closed: missing field → AttributeError)
        if not rc.enabled or equity <= 0:
            return None
        
        # Get per-symbol regime sizing config
        try:
            margin_fracs = rc.per_symbol_margin_fraction or {}
            leverage = rc.effective_leverage
            regime_sizing = rc.regime_sizing or {}
            
            margin_frac = margin_fracs.get(symbol)
            if margin_frac is None or margin_frac <= 0:
                return None
            
            # Get symbol's regime config
            sym_cfg = regime_sizing.get(symbol)
            if sym_cfg is None:
                return None
            
            # Check if regime sizing is enabled for this symbol
            # NOTE: sym_cfg can be dict (from YAML) or Pydantic model (if typed later)
            if isinstance(sym_cfg, dict):
                sym_enabled = sym_cfg.get("enabled", False)
                if "low_vol_multiplier" not in sym_cfg:
                     raise ConfigContractError(path=f"regime.multipliers.{symbol}.low_vol_multiplier", why="Missing low_vol_multiplier", symbol=symbol)
                low_mult = sym_cfg["low_vol_multiplier"]
                
                if "high_vol_multiplier" not in sym_cfg:
                     raise ConfigContractError(path=f"regime.multipliers.{symbol}.high_vol_multiplier", why="Missing high_vol_multiplier", symbol=symbol)
                high_mult = sym_cfg["high_vol_multiplier"]
            else:
                sym_enabled = sym_cfg.enabled
                low_mult = sym_cfg.low_vol_multiplier
                high_mult = sym_cfg.high_vol_multiplier
            
            if not sym_enabled:
                return None
            
            # Compute base notional
            base = (
                decimal.Decimal(str(margin_frac)) 
                * equity 
                * decimal.Decimal(str(leverage))
            )
            
            # Determine multiplier based on volatility state
            vol = (volatility_state or "").upper()
            if vol == "HIGH_VOLATILITY" or vol == "HIGH_VOL":
                mult = decimal.Decimal(str(high_mult))
            elif vol == "LOW_VOLATILITY" or vol == "LOW_VOL":
                mult = decimal.Decimal(str(low_mult))
            else:
                mult = decimal.Decimal("1.0")
            
            target = base * mult
            
            # Apply cap
            if cap_notional is not None and cap_notional > 0 and target > cap_notional:
                self.logger.info(
                    f"[{symbol}] RISK_CONTRACT_V1_REGIME_CAP: target {target} -> {cap_notional} "
                    f"(equity={equity}, vol={vol})"
                )
                target = cap_notional
            
            self.logger.debug(
                f"[{symbol}] regime_scaled_notional: base={base}, mult={mult}, target={target}"
            )
            return target
            
        except Exception as e:
            self.logger.debug(f"[{symbol}] Error computing regime-scaled notional: {e}")
            return None

    def _has_active_position_same_side(
        self,
        symbol: str,
        side: str,
    ) -> bool:
        """
        Check if there's an active position for this symbol in the same direction.
        
        ETAP4: Anti-pyramiding gate - prevents multiple entries in same direction.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            side: Intended trade side ('buy'/'long' or 'sell'/'short')
            
        Returns:
            True if a position exists in the same direction, False otherwise.
        """
        try:
            portfolio = self.latest_portfolio
            if not portfolio:
                return False
            
            positions = portfolio.get("positions") or []
            if not positions:
                return False
            
            # Normalize side to compare
            side_upper = side.upper()
            is_long_intent = side_upper in ("BUY", "LONG")
            
            for pos in positions:
                pos_symbol = pos.get("symbol")
                if pos_symbol != symbol:
                    continue
                
                # Get position quantity
                qty = pos.get("quantity") or pos.get("positionAmt") or pos.get("qty")
                if qty is None:
                    continue
                
                try:
                    qty_val = float(qty) if isinstance(qty, str) else qty
                except (ValueError, TypeError):
                    continue
                
                # Skip flat positions
                if abs(qty_val) < 1e-9:
                    continue
                
                # Check if same side
                pos_is_long = qty_val > 0
                
                if is_long_intent and pos_is_long:
                    self.logger.debug(
                        f"[{symbol}] Anti-pyramiding: existing LONG position (qty={qty_val})"
                    )
                    return True
                elif not is_long_intent and not pos_is_long:
                    self.logger.debug(
                        f"[{symbol}] Anti-pyramiding: existing SHORT position (qty={qty_val})"
                    )
                    return True
            
            return False
            
        except Exception as e:
            # Fail-closed: if we can't determine, assume no position (allow trade)
            self.logger.warning(f"[{symbol}] Anti-pyramiding check error: {e}")
            return False

    def on_features(self, event: Message) -> None:
        try:
            try:
                if isinstance(event.pld, dict):
                    symbol = event.pld.get("symbol", "unknown")
                elif hasattr(event, 'pld') and event.pld:
                    symbol = event.pld.symbol if hasattr(
                        event.pld, 'symbol') else "unknown"
                else:
                    symbol = "unknown"
            except (AttributeError, TypeError):
                symbol = "unknown"

            self.logger.info(f"✅ on_features() called for {symbol}")
            self.symbol_states[symbol]["features"] = event.pld

            # Commit 5: Clear risk-skew until-refresh state on data refresh
            try:
                guard = self.symbol_states[symbol].get("risk_skew_guard") or {}
                if guard.get("until_refresh"):
                    self.symbol_states[symbol]["risk_skew_guard"] = {
                        "defer_count": 0,
                        "window_start_ms": int(time.time() * 1000),
                        "until_refresh": False,
                    }
                    self.logger.info(f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on features refresh")
            except Exception:
                pass

            # Update per-symbol regime cache if available
            if isinstance(event.pld, dict):
                regime = event.pld.get("flat_regime")
                if regime:
                    if symbol not in self._per_symbol_regimes:
                        self._per_symbol_regimes[symbol] = {}
                    self._per_symbol_regimes[symbol]["regime"] = regime
                    self._per_symbol_regimes[symbol]["ts"] = time.time()
                # Also cache warmup status
                warmup = event.pld.get("warmup")
                if warmup and isinstance(warmup, dict):
                    if symbol not in self._per_symbol_regimes:
                        self._per_symbol_regimes[symbol] = {}
                    self._per_symbol_regimes[symbol]["warmup"] = warmup

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

            self.dlog.write(
                "FEATURES_RX",
                getattr(event, "rid", None),
                {"symbol": symbol, "keys": list(feats.keys())},
            )

            # Calculate alpha scores if alpha models are available
            if self.alpha_registry and feats:
                try:
                    alpha_scores = self.alpha_registry.calculate_all_alpha(
                        symbol, {"current_price": feats.get("price")}, feats
                    )
                    if alpha_scores:
                        # Emit alpha scores event
                        alpha_payload = {
                            "symbol": symbol,
                            "scores": [score.dict() for score in alpha_scores],
                            "timestamp": int(time.time() * 1000)
                        }
                        self.fsm.emit(
                            "EVT:ALPHA_SCORE_CALCULATED",
                            payload=alpha_payload,
                            why="alpha_calculation",
                            data_ref=[
                                f"model_{score.model_name}" for score in alpha_scores]
                        )

                        # VERIFY-ALPHA-CAPTURE: Write alpha scores to WAL for traceability
                        try:
                            wal_record = {
                                "op": "EVT",
                                "verb": "ALPHA_SCORE_CALCULATED",
                                "symbol": symbol,
                                "scores": [score.dict() for score in alpha_scores],
                                "timestamp": int(time.time() * 1000),
                                "why": "alpha_calculation"
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
                    raise # Propagate up to main catcher
                except Exception as e:
                    self.logger.error(
                        f"Error calculating alpha scores for {symbol}: {e}")
                    # Continue with normal flow - alpha calculation failure shouldn't block trading
                    # UNLESS it was a ConfigContractError (handled above)

            # Fallback trigger: if both features and risk present, ensure a decision attempt
            try:
                state = self.symbol_states[symbol]
                if state.get("features") and state.get("risk"):
                    decision_context = {
                        "features": state["features"],
                        "risk_params": state["risk"],
                        "portfolio": self.latest_portfolio,
                        "regime": self.latest_regime,
                    }
                    rid = str(uuid.uuid4())
                    self._make_decision_for_symbol(symbol, decision_context, rid)
            except ConfigContractError:
                raise # Propagate
            except Exception:
                pass # Ignore generic errors in fallback
        
        except ConfigContractError as e:
            # TASK 17: Central Interception Point
            reason = normalize_config_error(e)
            caught_symbol = e.symbol or symbol
            inc_config_contract_violation(path=e.path or "unknown", symbol=caught_symbol or "unknown")
            self.logger.critical(f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            if caught_symbol:
                self._record_blocked_intent(caught_symbol)
            return

    def on_risk(self, event: Message) -> None:
        try:
            if isinstance(event.pld, dict):
                symbol = event.pld.get("symbol", "unknown")
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
                    "window_start_ms": int(time.time() * 1000),
                    "until_refresh": False,
                }
                self.logger.info(f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on risk refresh")
        except Exception:
            pass

        # Cache risk data and timestamp for race condition handling
        if symbol not in self.symbol_states:
            self.symbol_states[symbol] = {}
        self.symbol_states[symbol]["_cached_risk"] = event.pld
        self.symbol_states[symbol]["_last_risk_time"] = time.time()

        self._check_and_trigger_decision_for_symbol(symbol)

        try:
            if hasattr(event, 'pld') and event.pld:
                rp = event.pld.risk_parameters if hasattr(
                    event.pld, 'risk_parameters') else {}
            elif isinstance(event.pld, dict):
                rp = (event.pld or {}).get("risk_parameters") or {}
            else:
                rp = {}
        except (AttributeError, TypeError):
            rp = {}

        self.dlog.write(
            "RISK_RX",
            getattr(event, "rid", None),
            {
                "symbol": symbol,
                "trading_allowed": bool(rp.get("is_trading_allowed", False)),
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
        self.logger.info(
            f"   Equity: {portfolio_data.get('equity')}, Positions: {len(portfolio_data.get('positions', []))}"
        )

        self.dlog.write(
            "PORTFOLIO_RX",
            getattr(event, "rid", None),
            {
                "equity": str(
                    self._cached_equity_free_usdt
                    or portfolio_data.get("equity_free_usdt", "0")
                ),
                "positions_count": len(portfolio_data.get("positions", [])),
            },
        )

    def on_regime(self, event: Message) -> None:
        self.latest_regime = event.pld
        
        # Contract v1.0: Extract and cache warmup state
        if isinstance(event.pld, dict):
            warmup = event.pld.get("warmup", {})
            self._latest_warmup = warmup
            symbol = event.pld.get("symbol")
            
            # Per-symbol regime cache: store regime for each symbol separately
            if symbol:
                regime_val = event.pld.get("regime") or event.pld.get("overall_regime")
                self._per_symbol_regimes[symbol] = {
                    "regime": regime_val,
                    "warmup": warmup,
                    "confidence": event.pld.get("confidence"),
                    "axes": event.pld.get("axes"),
                }
                self.logger.debug(
                    f"[{symbol}] Regime updated: {self._per_symbol_regimes[symbol].get('regime')}"
                )
                
                # Check for regime flip enforcement
                self._handle_regime_flip(symbol, self._per_symbol_regimes[symbol])
            
            # Guard: Block trades if not full_ready
            full_ready = bool(warmup.get("full_ready", False)) if self.arming_require_regime_warmup else bool(warmup.get("full_ready", True))
            if symbol and not full_ready:
                self.logger.info(
                    f"[{symbol}] RegimeContract: warmup phase (full_ready=false, " 
                    f"ticks={warmup.get('ticks_seen', 0)})"
                )
        
        # Track B: Forward regime to MR handler
        if self._mr_handler and self._mr_handler.enabled:
            try:
                pld = event.pld
                if isinstance(pld, dict):
                    symbol = pld.get("symbol")
                    regime = pld.get("regime") or pld.get("overall_regime")
                    if symbol and regime:
                        self._mr_handler.on_regime(symbol, regime)
            except Exception as e:
                self.logger.debug(f"Error forwarding regime to MR handler: {e}")
        
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
            regime = regime_data.get("regime") if isinstance(regime_data, dict) else str(regime_data)
            
            # Get current position
            portfolio = self.latest_portfolio
            if not portfolio:
                return

            pos_list = portfolio.get("positions", [])
            curr_pos = next((p for p in pos_list if p.get("symbol") == symbol), None)
            
            if not curr_pos:
                return
                
            qty_val = float(curr_pos.get("positionAmt", 0))
            if abs(qty_val) < 1e-9:
                return
                
            is_long = qty_val > 0
            
            should_close = False
            reason = ""
            
            # Regime Logic: STRICT enforcement
            if regime == "BULL_TREND" and not is_long:
                 should_close = True
                 reason = f"Short position in BULL_TREND"
            elif regime == "BEAR_TREND" and is_long:
                 should_close = True
                 reason = f"Long position in BEAR_TREND"
            elif regime == "UNCERTAIN":
                 should_close = True
                 reason = f"Position in UNCERTAIN regime"
                 
            if should_close:
                self.logger.warning(f"[{symbol}] REGIME FLIP ENFORCEMENT: {reason}. Closing {qty_val}.")
                
                # Construct Close Intent
                close_side = "SELL" if is_long else "BUY"
                
                # Provide dummy price 0 for Market order (or best effort fetch)
                # We use 0 so it defaults to Market in adapter if not specified otherwise
                price = decimal.Decimal("0")
                
                # Emit intent
                why_chain = ["regime_flip_enforcement", regime]
                rid = f"rf-{int(time.time())}"
                
                self._propose_trade_intent(
                    symbol=symbol,
                    side=close_side,
                    qty=decimal.Decimal(str(abs(qty_val))),
                    price=price,
                    why_chain=why_chain,
                    rid=rid,
                    reduce_only=True
                )
        except Exception as e:
            self.logger.warning(f"[{symbol}] Error in _handle_regime_flip: {e}")

    def _features_ready(self, symbol: str, features_data: dict) -> bool:
        """Check if features are fresh within TTL."""
        if not features_data or "ts" not in features_data:
            self.logger.debug(
                f"[{symbol}] _features_ready: no features_data or ts")
            return False

        now_ts = time.time() * 1000  # milliseconds
        features_ts = features_data["ts"]
        lag_ms = now_ts - features_ts
        ttl_ms = self.features_ttl_sec * 1000

        is_ready = lag_ms <= ttl_ms
        self.logger.debug(
            f"[{symbol}] _features_ready: now={now_ts:.0f}, features_ts={features_ts}, "
            f"lag={lag_ms:.0f}ms, ttl={ttl_ms}ms, ready={is_ready}"
        )

        return is_ready

    def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
        if not self.latest_portfolio:
            self.logger.debug(
                f"[{symbol}] Decision deferred: global portfolio state not yet available."
            )
            return

        state = self.symbol_states[symbol]
        has_features = bool(state.get("features"))
        has_risk = bool(state.get("risk"))

        # Check features readiness with TTL
        features_ready = False
        if has_features:
            features_ready = self._features_ready(symbol, state["features"])
            if not features_ready:
                # XAI instrumentation: features not ready
                now_ts = time.time() * 1000
                features_ts = state["features"].get("ts", 0)
                lag_ms = now_ts - features_ts
                ttl_ms = self.features_ttl_sec * 1000

                self.logger.warning(
                    format_why_with_details(
                        WhyCode.GUARD_RATE_LIMIT_EXCEEDED,  # closest match for stale data
                        f"features_stale symbol={symbol} rid=? now_ts={now_ts} "
                        f"last_features_ts={features_ts} lag_ms={lag_ms} ttl_ms={ttl_ms}"
                    )
                )
                inc_decision_deferred(symbol, "features_stale")

        # If we have both features and risk, make decision immediately
        # TTL gate enabled: requires fresh features within ttl_sec (default 30s)
        if has_features and has_risk and features_ready:
            # Optional bar gating (e.g., M15) to avoid multiple decisions per bar
            if self._bar_gating_enabled:
                feats = state["features"] or {}
                ts = int(feats.get("ts", 0))
                if ts > 0 and self._bar_ms > 0:
                    bar_index = ts // self._bar_ms
                    last_idx = self._last_bar_index.get(symbol)
                    if last_idx is not None and bar_index == last_idx:
                        self.logger.info(
                            f"[{symbol}] Bar gate: already processed bar_index={bar_index}, skipping decision")
                        return
                    self._last_bar_index[symbol] = bar_index
            
            # ========== REGIME GATING (Phase 2.2 Fix) ==========
            # Block trades in disallowed regimes (e.g., ETH in HIGH_VOLATILITY)
            instr_cfg = self._get_aurora_instrument_cfg(symbol)
            if instr_cfg:
                allowed_regimes = getattr(instr_cfg, 'allowed_regimes', None)
                if allowed_regimes:
                    # Get current regime name FOR THIS SYMBOL (per-symbol regime)
                    current_regime = None
                    # First try per-symbol regime cache
                    if symbol in self._per_symbol_regimes:
                        current_regime = self._per_symbol_regimes[symbol].get("regime")
                    # Fallback to global latest_regime (legacy)
                    elif self.latest_regime and isinstance(self.latest_regime, dict):
                        current_regime = self.latest_regime.get("regime") or self.latest_regime.get("overall_regime")
                    
                    if current_regime and current_regime not in allowed_regimes:
                        self.logger.info(
                            f"[{symbol}] REGIME_GATE_BLOCKED: {current_regime} not in {allowed_regimes}"
                        )
                        return  # Skip this symbol - regime not allowed
            # ==================================================
            
            # ========== CONTRACT v1.0: WARMUP GUARD (AURORA ONLY) ==========
            # Block trades if RegimeDetector is still in warmup phase
            # BUGFIX: Only apply to Aurora instruments, not MR strategy
            is_aurora_symbol = instr_cfg is not None and instr_cfg.enabled
            
            if is_aurora_symbol:
                # Get per-symbol warmup state
                warmup = None
                if symbol in self._per_symbol_regimes:
                    warmup = self._per_symbol_regimes[symbol].get("warmup")
                else:
                    warmup = getattr(self, "_latest_warmup", None)

                warmup_dict = warmup if isinstance(warmup, dict) else None
                warmup_full_ready = bool(warmup_dict.get("full_ready", False)) if warmup_dict else False

                if self.arming_require_regime_warmup and not warmup_full_ready:
                    now_ms = int(time.time() * 1000)
                    retry_key = self._stable_retry_key(prefix="arming", symbol=symbol, rid=rid, ts_ms=ts)
                    reason = "NRR-ARMING-NOT-READY" if warmup_dict else "NRR-ARMING-WARMUP-MISSING"
                    self.logger.warning(
                        f"[{symbol}] WARMUP_GUARD_DEFER (Aurora): {reason} warmup={bool(warmup_dict)} full_ready={warmup_full_ready}"
                    )
                    self._emit_intent_deferred_v1(
                        symbol=symbol,
                        reason=reason,
                        retry_key=retry_key,
                        next_allowed_ts=now_ms + max(0, int(self.arming_retry_backoff_ms)),
                        original_event_name="EVT:ARMING_RECHECK",
                        original_payload_min={"symbol": symbol, "rid": rid},
                        attempt=1,
                        max_attempts=int(self.arming_max_attempts),
                        why_chain=["arming_required", "warmup_not_ready"],
                        context="decision_making:on_features:warmup_guard",
                    )
                    self._record_blocked_intent(symbol)
                    return

                # Legacy behavior (arming disabled): only block when warmup explicitly says full_ready=false.
                if (not self.arming_require_regime_warmup) and warmup_dict and (not bool(warmup_dict.get("full_ready", True))):
                    ticks_seen = warmup_dict.get("ticks_seen", 0)
                    self.logger.info(
                        f"[{symbol}] WARMUP_GUARD_BLOCKED (Aurora): full_ready=false (ticks_seen={ticks_seen})"
                    )
                    return  # Skip - RegimeDetector not warmed up for Aurora
                
                # REMOVED: UNCERTAIN regime block - now handled via allowed_regimes config
            # ================================================================
            
            self.logger.info(
                f"[{symbol}] ✅ All data ready! Triggering decision...")
            
            # Use per-symbol regime with fallback to global
            symbol_regime = self._per_symbol_regimes.get(symbol, {}) if hasattr(self, '_per_symbol_regimes') else {}
            effective_regime = symbol_regime if symbol_regime else self.latest_regime
            
            decision_context = {
                "features": state["features"],
                "risk_params": state["risk"],
                "portfolio": self.latest_portfolio,
                "regime": effective_regime,
            }
            rid = str(uuid.uuid4())
            self.dlog.write("DECISION_TRIGGER", rid, {"symbol": symbol})
            self._make_decision_for_symbol(symbol, decision_context, rid)
            return

        # If we only have features but risk was already assessed earlier, check if we can use cached risk
        if has_features and not has_risk:
            # Check if risk assessment happened recently (within last 30 seconds)
            # This handles the race condition where features arrive after risk assessment
            risk_assessment_time = getattr(state, '_last_risk_time', 0)
            current_time = time.time()
            if current_time - risk_assessment_time < 30:  # 30 second window
                cached_risk = getattr(state, '_cached_risk', None)
                if cached_risk:
                    self.logger.info(
                        f"[{symbol}] ✅ Using cached risk assessment from "
                        f"{current_time - risk_assessment_time:.1f}s ago")
                    state["risk"] = cached_risk
                    
                    # Use per-symbol regime with fallback to global
                    symbol_regime = self._per_symbol_regimes.get(symbol, {}) if hasattr(self, '_per_symbol_regimes') else {}
                    effective_regime = symbol_regime if symbol_regime else self.latest_regime
                    
                    decision_context = {
                        "features": state["features"],
                        "risk_params": state["risk"],
                        "portfolio": self.latest_portfolio,
                        "regime": effective_regime,
                    }
                    rid = str(uuid.uuid4())
                    self.dlog.write("DECISION_TRIGGER", rid, {
                                    "symbol": symbol, "cached_risk": True})
                    self._make_decision_for_symbol(
                        symbol, decision_context, rid)
                    return

        # Defer decision if we don't have required data
        self.logger.warning(
            f"[{symbol}] ⚠️ Decision deferred: features={has_features}, "
            f"risk={has_risk}, features_ready={features_ready}"
        )
        # Track decision deferrals for observability
        if not has_features and not has_risk:
            reason = "both_missing"
        elif not has_features:
            reason = "features_missing"
        elif not has_risk:
            reason = "risk_missing"
        elif not features_ready:
            reason = "features_stale"
        else:
            reason = "unknown"
        inc_decision_deferred(symbol, reason)

    def _make_decision_for_symbol(self, symbol: str, context: dict, rid: str) -> None:
        self.logger.info(
            f"[{symbol}] 🚀 _make_decision_for_symbol() START - RID: {rid}"
        )

        # Check if Aurora strategy is enabled for this symbol
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and hasattr(instr_cfg, 'enabled') and not instr_cfg.enabled:
            self.logger.info(
                f"[{symbol}] Aurora strategy DISABLED for this instrument. Skipping decision."
            )
            return

        # P0-W1: Warmup/arming gate (fail-closed when enabled).
        is_aurora_symbol = bool(instr_cfg is not None and instr_cfg.enabled)
        if self.arming_require_regime_warmup and is_aurora_symbol:
            warmup = None
            if symbol in self._per_symbol_regimes:
                warmup = self._per_symbol_regimes[symbol].get("warmup")
            else:
                warmup = getattr(self, "_latest_warmup", None)

            warmup_dict = warmup if isinstance(warmup, dict) else None
            warmup_full_ready = bool(warmup_dict.get("full_ready", False)) if warmup_dict else False
            if not warmup_full_ready:
                now_ms = int(time.time() * 1000)
                retry_key = self._stable_retry_key(
                    prefix="arming",
                    symbol=symbol,
                    rid=rid,
                    ts_ms=int(context.get("features", {}).get("ts", 0)) or None,
                )
                reason = "NRR-ARMING-NOT-READY" if warmup_dict else "NRR-ARMING-WARMUP-MISSING"
                self._emit_intent_deferred_v1(
                    symbol=symbol,
                    reason=reason,
                    retry_key=retry_key,
                    next_allowed_ts=now_ms + max(0, int(self.arming_retry_backoff_ms)),
                    original_event_name="EVT:ARMING_RECHECK",
                    original_payload_min={"symbol": symbol, "rid": rid},
                    attempt=1,
                    max_attempts=int(self.arming_max_attempts),
                    why_chain=["arming_required", "warmup_not_ready"],
                    context="decision_making:_make_decision_for_symbol:warmup_guard",
                )
                self._record_blocked_intent(symbol)
                return

        # Busy guard: prevent infinite defer loops during cooldown
        current_time_ms = int(time.time() * 1000)  # Convert to milliseconds for comparison
        next_allowed = self._qos_next_allowed_ts.get(symbol, 0)  # Already in milliseconds
        if current_time_ms < next_allowed:
            remaining_sec = (next_allowed - current_time_ms) / 1000.0  # Convert back to seconds for logging
            self.logger.warning(
                f"[{symbol}] Busy guard active: decision blocked for {remaining_sec:.1f}s (cooldown active)"
            )
            # Schedule one-time retry after cooldown expires
            self._ensure_after_cooldown_retry(symbol, context, rid)
            return

        # Idempotency guard: prevent spam on same features (SSOT)
        features_data = context["features"]["features"]
        current_features_ts = context["features"].get("ts", 0)
        
        last_success_ts = self._last_successful_features_ts.get(symbol, 0)
        if current_features_ts > 0 and current_features_ts <= last_success_ts:
            # We already generated a successful intent for this feature snapshot.
            # Don't spam duplication or logs.
            # Exception: if we need to re-evaluate due to forced trigger? 
            # Assuming features are the clock signal for decisions.
            self.logger.debug(
                f"[{symbol}] Idempotency skip: features_ts={current_features_ts} <= last_success_ts={last_success_ts}"
            )
            return

        why_chain = []
        # features_data already extracted above
        risk_params = context["risk_params"]["risk_parameters"]
        portfolio = context["portfolio"]

        # FTR-07: Create typed DecisionContext for semantic feature access
        ts_ms = int(time.time() * 1000)
        ctx = create_decision_context(symbol, ts_ms, features_data)

        # QoS check (PACK EXP-4) - check rate limits and cooldowns
        qos_allowed, qos_reject_reason = self._qos_allow(
            symbol, is_exposure_block=False
        )
        if not qos_allowed:
            # Determine QoS enforcement mode
            effective_mode = self.qos_mode
            if self.qos_enforce and effective_mode == "defer":
                # Legacy enforce flag overrides defer mode
                effective_mode = "enforce"

            if effective_mode == "shadow":
                # Shadow mode: only log/metrics, continue with intent
                self.logger.warning(
                    f"[{symbol}] QoS shadow: passing intent downstream (reason: {qos_reject_reason})")
                inc_decision_deferred(symbol, "qos_shadow")
            elif effective_mode == "defer":
                # Defer mode: set busy guard and schedule one-time retry
                next_allowed_ts = self._calculate_next_allowed_time(symbol)
                next_allowed_sec = next_allowed_ts / 1000.0  # Convert to seconds

                self.logger.warning(
                    f"[{symbol}] QoS defer: setting busy guard until {next_allowed_sec} (reason: {qos_reject_reason})")

                # Set busy guard to prevent infinite defer loops
                self._qos_next_allowed_ts[symbol] = int(next_allowed_ts)

                # XAI instrumentation: qos_defer
                cooldown_left_ms = (next_allowed_ts - time.time() *
                                    1000) if next_allowed_ts > time.time() * 1000 else 0
                symbol_intent_counts: dict[str, Any] = self._qos_state.get(
                    "symbol_intent_counts", {})
                intent_data: dict[str, Any] = symbol_intent_counts.get(symbol, {
                                                                       "count": 0})
                intent_count: int = int(intent_data.get("count", 0))
                rate_state = f"count={intent_count}"
                self.logger.warning(
                    format_why_with_details(
                        WhyCode.GUARD_RATE_LIMIT_EXCEEDED,
                        f"cooldown_left_ms={cooldown_left_ms} rate_state={rate_state} code=NRR-012 why=qos_defer"
                    )
                )

                inc_decision_deferred(symbol, "qos_defer")

                # Update QoS state to record the deferral
                self._update_qos_state(symbol)

                # Schedule one-time retry after cooldown expires
                self._ensure_after_cooldown_retry(symbol, context, rid)

                # Log to OrderLoggerV1
                # Determine specific NRR code based on rejection reason
                if "symbol_cooldown" in str(qos_reject_reason):
                    nrr_code = NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE  # NRR-017
                else:
                    nrr_code = NormalizedRejectReasons.RATE_LIMIT_EXCEEDED  # NRR-012

                order_logger.write({
                    "rid": rid,
                    "timestamp": int(time.time() * 1000),
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "source_fsm": "decision_making",
                    "nrr_code": nrr_code,  # Use NRR-017 / NRR-012 for logging
                    "why": "qos_defer",
                    "metadata": {"detail": nrr_code}
                })

                self.clear_internal_state_for_symbol(symbol)
                return
            else:  # enforce mode
                # Enforce mode: block intent (legacy behavior)
                normalized_reason = NormalizedRejectReasons.normalize(
                    qos_reject_reason or "QoS rejection"
                )
                self.logger.warning(
                    f"[{symbol}] Trade intent rejected by QoS: {normalized_reason}"
                )
                self.dlog.write(
                    "DECISION_SKIP", rid, {
                        "symbol": symbol, "reason": "QOS_RATE_LIMITED"}
                )

                # Use specific NRR codes: NRR-017 for cooldown, NRR-012 for rate limit
                if "symbol_cooldown" in str(qos_reject_reason):
                    nrr_code = NormalizedRejectReasons.SYMBOL_COOLDOWN_ACTIVE  # NRR-017
                else:
                    nrr_code = NormalizedRejectReasons.RATE_LIMIT_EXCEEDED  # NRR-012

                # Log to OrderLoggerV1
                order_logger.write({
                    "rid": rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": "NONE",
                    "nrr_code": nrr_code,  # Use NRR-017 / NRR-012 for logging
                    "why": qos_reject_reason[:80] if qos_reject_reason else "QoS rejection",
                    "source_fsm": "DecisionMaking",
                    "metadata": {"reject_reason": "QOS_RATE_LIMITED", "detail": nrr_code}
                })

                self.clear_internal_state_for_symbol(symbol)
                return

        # Use cached equity_free_usdt instead of portfolio equity to prevent zero-overwrite
        equity_str = (
            self._cached_equity_free_usdt
            or portfolio.get("equity_free_usdt")
            or portfolio.get("equity", "0")
        )
        equity = decimal.Decimal(str(equity_str))

        self.logger.info(
            f"[{symbol}] Using equity for decision: {equity} (from cached: {self._cached_equity_free_usdt is not None})"
        )

        if equity <= 0:
            reject_reason = f"equity is zero or negative ({equity})"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "ZERO_EQUITY"}
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": "NRR-011",  # Exposure related
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "ZERO_EQUITY", "equity": str(equity)}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        regime = context.get("regime")

        if not risk_params.get("is_trading_allowed", False):
            reject_reason = "Trading not allowed by risk manager"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)

            # Record blocked intent for risk gate monitoring
            self._record_blocked_intent(symbol)

            # Check if this is an exposure block (PACK EXP-4)
            nrr_code = "NRR-011"  # Default to exposure
            if (
                "exposure_limit_exceeded" in str(risk_params).lower()
                or "exposure" in str(risk_params).lower()
            ):
                self._handle_exposure_block(symbol)
                normalized_reason = NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED
                nrr_code = "NRR-011"

            self.logger.info(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "RISK_DISALLOWED"}
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": nrr_code,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "RISK_DISALLOWED", "risk_params": risk_params}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # Strict Config Access
        trading_config = self.config.trading
        
        # Signal Weights:
        # 1. Try per-instrument (AuroraInstrument) - Dict[str, float]
        signal_weights = None
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and instr_cfg.weights:
             signal_weights = instr_cfg.weights
        
        # 2. Global Fallback - SignalWeights Object -> Dict
        if not signal_weights:
             signal_weights = trading_config.decision.signal_weights.model_dump()

        self.logger.info(f"DEBUG signal_weights for {symbol}: {signal_weights}")

        # Compute signal score; optionally normalize components into [0,1]
        # FTR-07: Use DecisionContext for typed access to features
        psi_vector: Dict[str, Any] = {}
        if self._normalize_signals:
            def _to_dec(val: Any) -> decimal.Decimal:
                try:
                    return decimal.Decimal(str(val))
                except Exception:
                    return decimal.Decimal("0")

            # FTR-07: Use ctx.price property instead of raw dict access
            price_dec = ctx.price

            # FTR-07: Use FlowView for OBI/TFI (already Decimal)
            obi_raw = ctx.flow.obi
            tfi_raw = ctx.flow.tfi

            # FTR-07: Use TrendView for delta_price
            dp_raw = ctx.trend.delta_price

            # FTR-07: Use TrendView for ema_bias (already [0,1])
            ema_bias_phi = ctx.trend.ema_bias

            # FTR-07: Use VolatilityView for volume/volatility metrics
            volume_spike_phi = ctx.volatility.volume_spike
            volatility_state_phi = ctx.volatility.volatility_state

            # FTR-07: Use LiquidityView for depth_imbalance
            depth_imbalance_phi = ctx.liquidity.depth_imbalance

            # macro_sync still from raw dict (not in Views yet)
            macro_sync_phi = _to_dec(features_data.get("macro_sync", 0))

            def _norm_m11_to_01(x: decimal.Decimal) -> decimal.Decimal:
                try:
                    # If already in [0,1], keep
                    if x >= 0 and x <= 1:
                        return x
                    return (x + 1) / 2
                except Exception:
                    return decimal.Decimal("0")

            obi_phi = _norm_m11_to_01(obi_raw)
            tfi_phi = _norm_m11_to_01(tfi_raw)
            if price_dec > 0:
                dp_pct = abs(dp_raw) / price_dec
            else:
                dp_pct = decimal.Decimal("0")
            # Clamp to 2% and scale to [0,1]
            if dp_pct < 0:
                dp_pct = decimal.Decimal("0")
            if dp_pct > decimal.Decimal("0.02"):
                dp_pct = decimal.Decimal("0.02")
            dp_phi = dp_pct / decimal.Decimal("0.02")

            # Build phi_map with all 8 metrics
            phi_map = {
                "obi": obi_phi,
                "tfi": tfi_phi,
                "delta_price": dp_phi,
                "ema_bias": ema_bias_phi,
                "volume_spike": volume_spike_phi,
                "volatility_state": volatility_state_phi,
                "depth_imbalance": depth_imbalance_phi,
                "macro_sync": macro_sync_phi,
            }
            signal_score = sum(
                decimal.Decimal(str(phi_map.get(f, 0))) *
                decimal.Decimal(str(w))
                for f, w in signal_weights.items()
            )

            # FTR-07: Add DecisionContext summary to psi_vector for XAI
            psi_vector = {
                "phi_OBI": float(obi_phi),
                "phi_TFI": float(tfi_phi),
                "phi_DeltaP": float(dp_phi),
                "phi_EMA_Bias": float(ema_bias_phi),
                "phi_Volume_Spike": float(volume_spike_phi),
                "phi_Volatility_State": float(volatility_state_phi),
                "phi_Depth_Imbalance": float(depth_imbalance_phi),
                "phi_Macro_Sync": float(macro_sync_phi),
                "weights": {k: float(v) for k, v in signal_weights.items()},
                # FTR-07: Semantic signals from DecisionContext
                "ctx_trend_bullish": ctx.trend.is_bullish,
                "ctx_trend_bearish": ctx.trend.is_bearish,
                "ctx_flow_buy_pressure": ctx.flow.is_buy_pressure,
                "ctx_flow_sell_pressure": ctx.flow.is_sell_pressure,
                "ctx_high_volatility": ctx.volatility.is_high_volatility,
                "ctx_illiquid": ctx.liquidity.is_illiquid,
                "ctx_crowded_long": ctx.crowding.is_crowded_long,
                "ctx_crowded_short": ctx.crowding.is_crowded_short,
            }
        else:
            signal_score = sum(
                decimal.Decimal(str(features_data.get(f, 0.0))) *
                decimal.Decimal(str(w))
                for f, w in signal_weights.items()
            )

        base_threshold = self._get_signal_threshold(symbol)  # Phase 3+: per-asset override
        # Regime-based threshold multiplier (Δθ); defaults to 1.0 if not configured or regime missing
        # Phase A1: Per-instrument regime thresholds with global fallback
        regime_thresholds_cfg = self._get_regime_thresholds(symbol)
        regime_name = (regime or {}).get("regime") if regime else None
        try:
            # Use regime_threshold_multipliers config (already loaded above as regime_thresholds_cfg)
            if regime_name and regime_name in regime_thresholds_cfg:
                factor_str = str(regime_thresholds_cfg.get(regime_name))
            elif "DEFAULT" in regime_thresholds_cfg:
                factor_str = str(regime_thresholds_cfg.get("DEFAULT"))
            else:
                 # P1 FIX: No hardcoded "1.0" fallback if DEFAULT missing.
                 # If config is present but missing keys, we must block/fail to prevent unintended trading.
                 raise ConfigContractError(
                     path=f"regime.thresholds.{regime_name}", 
                     why="Missing regime threshold and no DEFAULT",
                     symbol=symbol
                 )
            
            threshold_factor = decimal.Decimal(factor_str)
        except Exception as e:
            # Propagate error to inhibit signal (Fail Closed)
            self.logger.error(f"Regime threshold error: {e}")
            return None # Stop signal generation
        signal_threshold = base_threshold * threshold_factor

        # EXP-DIRECTION: Calculate side-bias penalty (Δθ_bias)
        # Phase A1: Per-instrument side_bias with global fallback
        current_time = time.time()
        sell_bias_penalty_factor_raw, bias_window_sec, sell_target_ratio = self._get_side_bias_params(symbol)
        sell_bias_penalty_factor = decimal.Decimal(str(sell_bias_penalty_factor_raw))

        # Track intents per side (you can also extract from order_logger if needed)
        if symbol not in getattr(self, '_side_intent_window', {}):
            self._side_intent_window = getattr(self, '_side_intent_window', {})
            self._side_intent_window[symbol] = {"buys": [], "sells": []}

        window_data = self._side_intent_window[symbol]
        # Remove old entries outside the window
        window_data["buys"] = [ts for ts in window_data["buys"]
                               if current_time - ts < bias_window_sec]
        window_data["sells"] = [ts for ts in window_data["sells"]
                                if current_time - ts < bias_window_sec]

        buy_count = len(window_data["buys"])
        sell_count = len(window_data["sells"])
        total_count = buy_count + sell_count

        # Calculate current SELL share
        if total_count > 0:
            sell_share = decimal.Decimal(
                str(sell_count)) / decimal.Decimal(str(total_count))
        else:
            sell_share = decimal.Decimal("0.5")  # Neutral if no history

        # Apply bias penalty to side that's oversold
        bias_multiplier = decimal.Decimal("1.0")
        if sell_share > decimal.Decimal(str(sell_target_ratio)):
            # Too many SELLs - raise SELL threshold (harder to short)
            bias_multiplier += sell_bias_penalty_factor
            self.logger.info(
                f"[{symbol}] SIDE_BIAS_PENALTY: sell_share={float(sell_share):.2%} > "
                f"target={float(sell_target_ratio):.2%}, raising SELL threshold by "
                f"{float(sell_bias_penalty_factor):.0%}"
            )
        elif sell_share < decimal.Decimal(str(1.0 - float(sell_target_ratio))):
            # Too many BUYs - raise BUY threshold (harder to long)
            bias_multiplier += sell_bias_penalty_factor
            self.logger.info(
                f"[{symbol}] SIDE_BIAS_PENALTY: buy_share={float(1.0 - float(sell_share)):.2%} > "
                f"target={float(sell_target_ratio):.2%}, raising BUY threshold by "
                f"{float(sell_bias_penalty_factor):.0%}"
            )

        signal_threshold_with_bias = signal_threshold * bias_multiplier

        side = ""
        if signal_score >= signal_threshold_with_bias:
            side = "buy"
        elif signal_score <= -signal_threshold_with_bias:
            side = "sell"
        else:
            reject_reason = f"Neutral signal score {signal_score:.4f} (threshold={signal_threshold_with_bias:.4f} with bias)"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            msg = ("Trade intent for {} rejected: {} "
                   "(NRR: {})".format(symbol, reject_reason, normalized_reason))  # noqa: E501
            self.logger.info(msg)
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "NEUTRAL_SIGNAL"}
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {
                    "reject_reason": "NEUTRAL_SIGNAL",
                    "signal_score": float(signal_score),
                    "threshold_base": float(signal_threshold),
                    "threshold_with_bias": float(signal_threshold_with_bias),
                    "sell_share": float(sell_share),
                    "bias_multiplier": float(bias_multiplier)
                }
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # FTR-07: Crowding Filter using DecisionContext (V2 Futures features)
        # Block entries into crowded positions to reduce adverse selection
        if side == "buy" and ctx.crowding.is_crowded_long:
            reject_reason = "crowding_filter_long_crowded"
            self.logger.warning(
                f"[{symbol}] Trade intent ({side}) rejected: funding rate indicates crowded LONG "
                f"(funding_normalized={ctx.crowding.funding_rate_normalized})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "CROWDING_FILTER", "side": side,
                    "funding_normalized": str(ctx.crowding.funding_rate_normalized)}
            )
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "CROWDING_FILTER_LONG"}
            })
            self.clear_internal_state_for_symbol(symbol)
            return

        if side == "sell" and ctx.crowding.is_crowded_short:
            reject_reason = "crowding_filter_short_crowded"
            self.logger.warning(
                f"[{symbol}] Trade intent ({side}) rejected: funding rate indicates crowded SHORT "
                f"(funding_normalized={ctx.crowding.funding_rate_normalized})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "CROWDING_FILTER", "side": side,
                    "funding_normalized": str(ctx.crowding.funding_rate_normalized)}
            )
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "CROWDING_FILTER_SHORT"}
            })
            self.clear_internal_state_for_symbol(symbol)
            return

        # FTR-07: Liquidity Filter using DecisionContext
        # Block trades in illiquid markets
        if ctx.liquidity.is_illiquid:
            reject_reason = "liquidity_filter_illiquid_market"
            self.logger.warning(
                f"[{symbol}] Trade intent ({side}) rejected: market is illiquid "
                f"(kappa={ctx.liquidity.liquidity_kappa}, spread={ctx.liquidity.effective_spread}bps)"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {
                    "symbol": symbol, "reason": "LIQUIDITY_FILTER", "side": side,
                    "kappa": str(ctx.liquidity.liquidity_kappa)}
            )
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "LIQUIDITY_FILTER"}
            })
            self.clear_internal_state_for_symbol(symbol)
            return

        # Record this intent side for future bias tracking
        window_data[f"{'sells' if side == 'sell' else 'buys'}"].append(
            current_time)

        # Attach PSI snapshot and regime info for explainability
        if self.latest_regime:
            try:
                psi_vector.update({
                    "regime": regime.get("regime") if regime else None,
                    "regime_conf": float(decimal.Decimal(str((regime or {}).get("confidence", 0))))
                })
            except Exception:
                pass
        self.dlog.write(
            "DECISION_EVAL",
            rid,
            {
                "symbol": symbol,
                "signal_score": float(signal_score),
                "signal_threshold": float(signal_threshold),
                "psi": psi_vector,
                "regime_threshold_factor": float(threshold_factor),
            },
        )

        if regime and regime.get("symbol") == symbol:
            current_regime = regime.get("regime")
            # Optional behavior FSM gate: allow entry only in IdleFlat
            if self._behavior_enabled:
                beh = self._behavior_state.get(symbol, "IdleFlat")
                if beh != "IdleFlat":
                    reject_reason = f"behavior_gate_{beh}_disallows_entry"
                    normalized_reason = NormalizedRejectReasons.normalize(
                        reject_reason)
                    self.logger.info(
                        f"Trade intent for {symbol} ({side}) rejected: {reject_reason} (NRR: {normalized_reason})"
                    )
                    self.dlog.write(
                        "DECISION_SKIP", rid, {
                            "symbol": symbol, "reason": "BEHAVIOR_GATE", "behavior_state": beh}
                    )
                    self.clear_internal_state_for_symbol(symbol)
                    return
            if (current_regime == "TREND_UP" and side == "sell") or (
                current_regime == "TREND_DOWN" and side == "buy"
            ):
                reject_reason = (
                    f"rejected by regime filter (current regime: {current_regime})"
                )
                normalized_reason = NormalizedRejectReasons.normalize(
                    reject_reason)
                self.logger.info(
                    f"Trade intent for {symbol} ({side}) rejected: {reject_reason} (NRR: {normalized_reason})"
                )
                self.dlog.write(
                    "DECISION_SKIP", rid, {
                        "symbol": symbol, "reason": "REGIME_FILTER"}
                )

                # Log to OrderLoggerV1
                order_logger.write({
                    "rid": rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": side.upper(),
                    "nrr_code": None,
                    "why": reject_reason[:80],
                    "source_fsm": "DecisionMaking",
                    "metadata": {"reject_reason": "REGIME_FILTER", "regime": current_regime}
                })

                self.clear_internal_state_for_symbol(symbol)
                return

        price_ref_str = features_data.get("price")
        if not price_ref_str:
            reject_reason = "No valid price reference"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.error(
                f"CRITICAL: {reject_reason} for {symbol}. Cannot make trading decision. (NRR: {normalized_reason})"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "NO_PRICE_REFERENCE"}
            })

            self.clear_internal_state_for_symbol(symbol)
            return
        price_ref = decimal.Decimal(str(price_ref_str))

        # Prepare sizing meta: regime multiplier and Kelly fraction (optional)
        sizing_meta: dict[str, Any] = {}
        # Phase A1: Regime multiplier with per-instrument fallback
        try:
            sizing_mods = self._get_regime_sizing(symbol)
            if regime_name not in sizing_mods:
                  raise ConfigContractError(path=f"regime.multipliers.{symbol}.{regime_name}", why="Missing specific regime multiplier", symbol=symbol)
            sizing_meta["regime_multiplier"] = decimal.Decimal(str(sizing_mods[regime_name]))
        except Exception:
            pass
        # Kelly fraction (optional): derive from config when available
        # Kelly fraction (optional): derive from config when available (Strict)
        # Kelly fraction (optional): derive from config when available (Strict)
        try:
            kelly_cfg = self.config.trading.decision.kelly
            if kelly_cfg.base_probability is not None:
                base_p = decimal.Decimal(str(kelly_cfg.base_probability))
                cap = decimal.Decimal(str(kelly_cfg.kelly_cap))
                alpha = decimal.Decimal(str(kelly_cfg.kelly_alpha))

                brackets_cfg = self.config.trading.execution.brackets
                if not brackets_cfg.sl.fixed_bps:
                     raise ConfigContractError(path="trading.execution.brackets.sl.fixed_bps", why="Missing fixed_bps", symbol=symbol)
                sl_bps_val = decimal.Decimal(str(brackets_cfg.sl.fixed_bps))

                if not brackets_cfg.tp.fixed_bps:
                     raise ConfigContractError(path="trading.execution.brackets.tp.fixed_bps", why="Missing fixed_bps", symbol=symbol)
                tp_bps_val = decimal.Decimal(str(brackets_cfg.tp.fixed_bps))

                if sl_bps_val <= 0:
                    self.logger.warning("SL_bps invalid <= 0")
                    return decimal.Decimal("0")

                payoff_r = tp_bps_val / sl_bps_val
                
                # Check Kelly override logic (Legacy compat or unused?)
                # Assuming valid payoff_r allows proceeding to Kelly calc
        except Exception as e:
            self.logger.error(f"Bracket/Kelly config error: {e}")
            return decimal.Decimal("0")

        try:
            score_01 = signal_score
            if score_01 < 0:
                score_01 = decimal.Decimal("0")
            elif score_01 > 1:
                score_01 = decimal.Decimal("1")

            # Simple uplift from base probability (centered), conservative range
            p = base_p + (decimal.Decimal("0.20") * (score_01 - decimal.Decimal("0.5")))
            
            p = max(decimal.Decimal("0"), min(decimal.Decimal("1"), p))
            
            # Temporary conservative clipping to [0.45, 0.65]
            p = max(decimal.Decimal("0.45"), min(decimal.Decimal("0.65"), p))

            # Kelly formula: f* = p - (1-p)/r
            # If r (payoff_r) is very small, this blows up, but checks above prevent r=0 div implies r safe?
            # payoff_r = tp/sl. if sl=0 handled. if tp=0, r=0.
            # Div by zero check?
            if payoff_r == 0:
                 full_kelly = decimal.Decimal("0")
            else:
                 full_kelly = p - (decimal.Decimal("1") - p) / payoff_r

            # Floor: if no positive edge, set to zero
            # Edge condition: p * (r+1) - 1 > 0  => p > 1/(r+1)
            # If not met, f* <= 0.
            if full_kelly < 0:
                 full_kelly = decimal.Decimal("0")

            kelly_fraction = full_kelly * alpha
            kelly_fraction = max(decimal.Decimal("0"), min(cap, kelly_fraction))
            
            sizing_meta["kelly_fraction"] = kelly_fraction
        except Exception as e:
            self.logger.warning(f"Kelly calculation error: {e}")
            pass

        # FTR-07: Use DecisionContext for volatility state in sizing
        if ctx.volatility.is_high_volatility:
            sizing_meta["volatility_state"] = "HIGH_VOL"
        elif ctx.volatility.is_low_volatility:
            sizing_meta["volatility_state"] = "LOW_VOL"
        else:
            sizing_meta["volatility_state"] = "NORMAL"

        # Call sizing with optional meta
        context["_sizing_meta"] = sizing_meta
        qty, why_sizing = self._calculate_position_size(
            symbol, price_ref, side, context
        )
        why_chain.append(why_sizing)

        if not qty or qty <= 0:
            reject_reason = f"quantity is zero or negative. Why: {why_sizing}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "quantity": float(qty) if qty else 0,
                "nrr_code": None,
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "ZERO_QUANTITY", "why_sizing": why_sizing}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # Update QoS state for successful decision
        self._update_qos_state(symbol)

        self.dlog.write(
            "INTENT_PROPOSED",
            rid,
            {
                "symbol": symbol,
                "side": side,
                "qty": str(qty),
                "price_ref": str(price_ref),
            },
        )

        # ✅ EXPOSURE_CACHE_PRECHECK: Check exposure limits before proposing intent
        notional_usd = float(qty * price_ref)
        if not self._precheck_exposure_cache(symbol, side, notional_usd):
            reject_reason = "exposure_limit_exceeded_cache_precheck"
            normalized_reason = NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED
            self.logger.warning(
                f"[{symbol}] Trade intent rejected by exposure cache precheck: {reject_reason} (NRR: {normalized_reason})"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": rid,
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": side.upper(),
                "quantity": float(qty),
                "nrr_code": "NRR-011",
                "why": reject_reason[:80],
                "source_fsm": "DecisionMaking",
                "metadata": {"reject_reason": "EXPOSURE_CACHE_BLOCK", "notional_usd": notional_usd}
            })

            self.clear_internal_state_for_symbol(symbol)
            return

        # === Strict Sequential Contract (Commit 4) ===
        # Replaces ETAP4 logic. Handles Flattening, Anti-Pyramiding, and Flip Orchestration.
        pld_for_flip = {
            "symbol": symbol,
            "side": side,
            "rid": rid,
            "why_chain": why_chain,
            # Pass full context for potential reconstruction
            "context_ref": "decision_making_aurora" 
        }
        flip_result = self._handle_flip_orchestration(
            symbol=symbol,
            intent_side=side,
            original_pld=pld_for_flip,
            source="aurora"
        )
        
        if flip_result:
            if flip_result == "ANTI_PYRAMIDING_BLOCK":
                 reject_reason = f"anti_pyramiding_active_position_{symbol}_{side.lower()}"
                 self.logger.info(
                     f"[{symbol}] DECISION NRR: {reject_reason} (existing position, blocking new entry)"
                 )
                 order_logger.write({
                    "rid": rid,
                    "event_type": "ORDER_REJECTED",
                    "symbol": symbol,
                    "side": side.upper(),
                    "quantity": float(qty),
                    "nrr_code": "NRR-020",
                    "why": reject_reason[:80],
                    "source_fsm": "DecisionMaking",
                    "metadata": {"reject_reason": "ANTI_PYRAMIDING_BLOCK"}
                })
            elif flip_result == "FLIP_CLOSE_PENDING":
                # Close intent and Deferral event already emitted by helper
                self.logger.info(f"[{symbol}] DECISION: Flip initiated. Open deferred.")
            elif flip_result == "NRR-PORTFOLIO-UNKNOWN":
                # Fail-closed
                pass
                
            self.clear_internal_state_for_symbol(symbol)
            return

        self._propose_trade_intent(
            symbol, side, qty, price_ref, why_chain, rid
        )

        # Update idempotency guard (SUCCESS)
        if current_features_ts > 0:
            self._last_successful_features_ts[symbol] = current_features_ts

    def _calculate_position_size(
        self, symbol: str, price: decimal.Decimal, side: str, context: dict
    ) -> tuple[Optional[decimal.Decimal], str]:
        why_chain = []
        portfolio = context["portfolio"]
        equity = decimal.Decimal(str(portfolio.get("equity", "0")))



        # Strict Config for Dynamic Sizing via Domains
        pos_config = self.config.domains.decision_making.position_sizing
        
        q_risk = pos_config.risk_fraction_q
        kappa_mode = str(pos_config.liquidity_kappa_mode).lower()
        kappa_liq = float(pos_config.liquidity_kappa)
        if kappa_mode == "dynamic":
            try:
                features_event = context.get("features", {}) or {}
                feats = features_event.get("features", {}) or {}
                lk = feats.get("liquidity_kappa")
                if lk is not None:
                    kappa_liq = decimal.Decimal(str(lk))
            except Exception:
                pass

        final_pos_size_usd: decimal.Decimal
        why_parts: list[str] = []
        if q_risk is not None:
            try:
                q_dec = decimal.Decimal(str(q_risk))
            except Exception:
                q_dec = decimal.Decimal("0.01")
            try:
                kappa_dec = decimal.Decimal(str(kappa_liq))
            except Exception:
                kappa_dec = decimal.Decimal("1")

            # brackets may be absent in some configs; guard accordingly
            # brackets: trading.execution.brackets.sl.fixed_bps
            sl_bps_val = self.config.trading.execution.brackets.sl.fixed_bps
            try:
                sl_bps_dec = decimal.Decimal(str(sl_bps_val))
            except Exception:
                sl_bps_dec = decimal.Decimal("50")
            if sl_bps_dec <= 0:
                sl_bps_dec = decimal.Decimal("50")

            denom = (sl_bps_dec / decimal.Decimal("10000")
                     ) if sl_bps_dec else decimal.Decimal("0.005")
            q_notional = (q_dec * equity / denom)
            # Kelly path (if provided)
            sizing_meta = context.get("_sizing_meta", {}) or {}
            kelly_fraction = sizing_meta.get("kelly_fraction")
            if isinstance(kelly_fraction, decimal.Decimal) and kelly_fraction > 0:
                kelly_notional = kelly_fraction * equity
                base_notional = min(q_notional, kelly_notional)
            else:
                base_notional = q_notional
            # NOTE: regime_multiplier is now applied at the END (Phase 2.1 fix)

            # Apply volatility-based multiplier to SL_bps for adaptive sizing
            volatility_multiplier = decimal.Decimal(
                "1.0")  # Default multiplier
            volatility_state = sizing_meta.get("volatility_state")
            if volatility_state == "HIGH_VOL":
                volatility_multiplier = decimal.Decimal("1.4")
            elif volatility_state == "LOW_VOL":
                volatility_multiplier = decimal.Decimal("0.8")
            # else: keep default 1.0 for other states

            # Recalculate with adjusted SL_bps
            adjusted_sl_bps = sl_bps_dec * volatility_multiplier
            adjusted_denom = (adjusted_sl_bps / decimal.Decimal("10000")
                              ) if adjusted_sl_bps else decimal.Decimal("0.005")
            adjusted_q_notional = (q_dec * equity / adjusted_denom)
            if isinstance(kelly_fraction, decimal.Decimal) and kelly_fraction > 0:
                adjusted_kelly_notional = kelly_fraction * equity
                base_notional = min(adjusted_q_notional,
                                    adjusted_kelly_notional)
            else:
                base_notional = adjusted_q_notional

            self.logger.debug(
                f"[{symbol}] SL_BPS_ADJUSTED: base={sl_bps_dec}, multiplier={volatility_multiplier}, final={adjusted_sl_bps}")

            # Apply liquidity kappa at the end
            try:
                kappa_dec = decimal.Decimal(str(kappa_liq))
            except Exception:
                kappa_dec = decimal.Decimal("1")
            pre_final = base_notional * kappa_dec
            
            # ========== REGIME SIZING FIX (Phase 2.1) ==========
            # Apply regime multiplier AFTER all base calculations
            # This fixes the SOL 2.0x LOW_VOL sizing bug
            regime_multiplier = sizing_meta.get("regime_multiplier")
            if isinstance(regime_multiplier, decimal.Decimal) and regime_multiplier > 0:
                pre_final = pre_final * regime_multiplier
                self.logger.info(
                    f"[{symbol}] REGIME_SIZING_APPLIED: base={base_notional}, "
                    f"kappa={kappa_dec}, mult={regime_multiplier}, result={pre_final}"
                )
            # ===================================================
            
            final_pos_size_usd = pre_final
            # Apply liquidity cap as a hard ceiling
            if final_pos_size_usd > self.liq_cap_usd:
                final_pos_size_usd = self.liq_cap_usd
            why_parts.append(
                f"sizing=slbps q={q_dec} sl_bps={adjusted_sl_bps} m_regime={sizing_meta.get('regime_multiplier','N/A')} m_vol={volatility_multiplier} kappa={kappa_dec}")
        else:
            final_pos_size_usd = min(
                self.liq_cap_usd, equity * decimal.Decimal("0.1")
            )  # Legacy sizing fallback
            why_parts.append("sizing=legacy_10pct_equity")

        msg = (
            f"[{symbol}] POSITION_SIZE_CALC: equity=${equity}, " +
            f"10%=${equity * decimal.Decimal('0.1')}, liq_cap=${self.liq_cap_usd}, " +
            f"final=${final_pos_size_usd}"
        )  # noqa: E501
        self.logger.info(msg)

        # ETAP3: Apply risk_contract_v1 regime sizing or cap
        rc_cap_notional = self._compute_risk_contract_cap_notional(symbol, equity)
        
        # Get volatility_state from sizing_meta (already computed above in legacy logic)
        vol_state = sizing_meta.get("volatility_state") if q_risk is not None else None
        
        # Try regime-scaled notional first (ETAP3: only for symbols with regime_sizing.enabled=true)
        regime_target = self._compute_regime_scaled_notional(
            symbol=symbol,
            equity=equity,
            volatility_state=vol_state,
            cap_notional=rc_cap_notional,
        )
        
        if regime_target is not None:
            # Regime sizing enabled for this symbol: use regime_target instead of legacy
            self.logger.info(
                f"[{symbol}] RISK_CONTRACT_V1_REGIME_SIZING: "
                f"legacy_notional={final_pos_size_usd}, regime_target={regime_target}, "
                f"equity={equity}, vol_state={vol_state}"
            )
            final_pos_size_usd = regime_target
            why_parts.append(f"rc_v1_regime={regime_target}")
        elif rc_cap_notional is not None:
            # No regime sizing, but cap is configured (ETAP2 behavior)
            if final_pos_size_usd > rc_cap_notional:
                self.logger.info(
                    f"[{symbol}] RISK_CONTRACT_V1_CAP: notional {final_pos_size_usd} -> {rc_cap_notional} "
                    f"(equity={equity})"
                )
                final_pos_size_usd = rc_cap_notional
                why_parts.append(f"rc_v1_cap={rc_cap_notional}")

        if final_pos_size_usd < self.min_pos_size_usd:
            reject_reason = f"position size {final_pos_size_usd} is below minimum {self.min_pos_size_usd}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(f"[{symbol}] REJECT: {reject_reason}")
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        why_chain.append(f"pos_size_usd={final_pos_size_usd}")
        if why_parts:
            why_chain.append(", ".join(why_parts))

        # CFG-INSTRUMENTS-STEP-02-DM-PRECISION: Use canonical config.instruments SSOT
        try:
            tick_size, step_size_float = self._get_precision(symbol)
            step_size = decimal.Decimal(str(step_size_float))
        except ValueError as e:
            reject_reason = f"Precision error: {e}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            self.logger.error(f"[{symbol}] REJECT: {reject_reason}")
            return None, f"{reject_reason} (NRR: {normalized_reason})"
        if price <= 0:
            reject_reason = "Invalid price for sizing"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.error(f"[{symbol}] REJECT: {reject_reason}")
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        qty = final_pos_size_usd / price
        rounded_qty = qty.quantize(step_size, rounding=decimal.ROUND_DOWN)

        self.logger.info(
            f"[{symbol}] QTY_CALC: price=${price}, "
            f"raw_qty={qty}, step_size={step_size}, "
            f"rounded_qty={rounded_qty}, "
            f"notional=${rounded_qty * price}"
        )

        if rounded_qty <= 0:
            reject_reason = f"qty rounded to zero from raw {qty}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(f"[{symbol}] REJECT: {reject_reason}")
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        return rounded_qty, ", ".join(why_chain)

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
    ) -> None:
        # CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION: Check strategy arbitration
        arbitration_result = self._check_strategy_arbitration(symbol, strategy_id)
        if not arbitration_result["allowed"]:
            self.logger.info(
                f"[{symbol}] TRADE_INTENT_BLOCKED: Strategy arbitration rejected: {arbitration_result['reason']}"
            )
            self._record_blocked_intent(symbol)
            return
        
        # Z-01 FIX: Read tca_prefs from config (Strict P1)
        tca = self._tca_prefs
        # Safe extraction helper (handles dict or Pydantic)
        def _get_strict(obj, key, err_msg):
            val = getattr(obj, key, None) if hasattr(obj, key) else (obj.get(key) if isinstance(obj, dict) else None)
            if val is None:
                raise ValueError(err_msg)
            return val

        try:
             # TCA Prefs
             max_slippage = str(_get_strict(tca, 'max_slippage_bps', "Missing max_slippage_bps"))
             max_latency = _get_strict(tca, 'max_latency_ms', "Missing max_latency_ms")
             maker_pref = _get_strict(tca, 'maker_preference', "Missing maker_preference")
        except ValueError as e:
             self.logger.error(f"TCA Config Block: {e}")
             return None # Block trade

        # Z-02 FIX: Read risk_budgets from config (Strict P1)
        rb = self._risk_budgets
        try:
             trade_cvar = str(_get_strict(rb, 'trade_cvar95_max_bps', "Missing trade_cvar95_max_bps"))
             session_cvar = str(_get_strict(rb, 'session_cvar95_max_bps', "Missing session_cvar95_max_bps"))
        except ValueError as e:
             self.logger.error(f"RiskBudget Config Block: {e}")
             return None # Block trade
        
        trade_intent = {
            "instrument": symbol,
            "side": side,
            "order": {
                "qty": str(qty),
                "price": str(price),
                "price_ref": str(price),
                "reduce_only": reduce_only,
            },
            "p": "0.75",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": max_slippage,
                "max_latency_ms": max_latency,
            },
            "risk_budget": {
                "trade_cvar95_max_bps": trade_cvar,
                "session_cvar95_max_bps": session_cvar,
            },
            "size": {"notional_cap_usd": str(qty * price), "kelly_fraction": "0.1"},
            "valid_for_ms": 5000,
            "why": why_chain,
            "dto_version": "1.0.0",
            "schema_ref": "...",
            "idempotent_key": str(uuid.uuid4()),
        }

        # Record accepted intent for risk gate monitoring
        self._record_accepted_intent(symbol)

        self.fsm.emit(
            "EVT:TRADE_INTENT_PROPOSED", payload=trade_intent, why="trade_intent", data_ref=why_chain
        )

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

    def _get_position_state(self, symbol: str) -> str:
        """
        Get current position state from SSOT (latest_portfolio).
        Returns: FLAT, LONG, SHORT, UNKNOWN
        """
        if not self.latest_portfolio:
            return "UNKNOWN"
            
        pos_list = self.latest_portfolio.get("positions", [])
        curr_pos = next((p for p in pos_list if p.get("symbol") == symbol), None)
        
        if not curr_pos:
            return "FLAT"
            
        try:
            qty = float(curr_pos.get("positionAmt", 0))
        except (ValueError, TypeError):
            return "UNKNOWN"
            
        if abs(qty) < 1e-9: # Equality tolerance
            return "FLAT"
            
        return "LONG" if qty > 0 else "SHORT"

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
        
    def _emit_reduce_only_close(self, symbol: str, reason: str, rid: str) -> None:
        """Emit immediate reduce-only close intent for Flip Orchestration."""
        pos_state = self._get_position_state(symbol)
        if pos_state not in ("LONG", "SHORT"):
            return # Nothing to close
            
        close_side = "SELL" if pos_state == "LONG" else "BUY"
        
        # Get qty from portfolio
        pos_list = self.latest_portfolio.get("positions", [])
        curr_pos = next((p for p in pos_list if p.get("symbol") == symbol), None)
        qty = abs(float(curr_pos.get("positionAmt", 0)))
        
        self.logger.info(f"[{symbol}] FLIP_ORCHESTRATION: Emitting CLOSE {close_side} {qty} (reduce_only)")
        
        self._propose_trade_intent(
            symbol=symbol,
            side=close_side,
            qty=decimal.Decimal(str(qty)),
            price=decimal.Decimal("0"), # Market/Best-effort
            why_chain=["flip_orchestration_close", reason],
            rid=rid,
            reduce_only=True
        )

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
            ts_ms = int(time.time() * 1000)
        if side:
            return f"{prefix}:{symbol}:{side}:{ts_ms}"
        return f"{prefix}:{symbol}:{ts_ms}"

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
        now_ms = int(time.time() * 1000)
        # Strict Config
        try:
             ttl_ms = self.config.trading.decision.retry_ttl_ms
        except AttributeError:
             ttl_ms = 300_000
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
        self.fsm.emit("EVT:INTENT_DEFERRED", payload)

    def _schedule_open_retry(self, symbol: str, original_context: dict, cooldown_ms: int, reason: str) -> None:
        """Emit EVT:INTENT_DEFERRED to schedule retry after close."""
        next_ts = int(time.time() * 1000) + cooldown_ms
        
        # Match schema intent_deferred_v1.json
        payload = {
            "retry_key": f"flip-{symbol}-{int(time.time())}", 
            "symbol": symbol,
            "reason": reason,
            "next_allowed_ts": next_ts,
            "attempt": 1, 
            "max_attempts": 3,
            "original_event": {
                "event_name": "EVT:TRADE_INTENT_PROPOSED", # Default assumption for open intent
                "payload_min": original_context
            },
            "created_ts": int(time.time() * 1000),
            "why_chain": ["flip_orchestration_defer"]
        }
        
        self.logger.info(f"[{symbol}] FLIP_ORCHESTRATION: Deferring OPEN until {next_ts} (reason: {reason})")
        self.fsm.emit("EVT:INTENT_DEFERRED", payload)

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

        current_time = time.time()
        if current_time - self.last_alert_check_time < 10.0:
            return  # Too soon, skip check

        self.last_alert_check_time = current_time

        # Calculate blocked percentage
        if self.intents_seen_total < 10:
            # Not enough data yet
            return

        blocked_pct = (self.intents_blocked_total /
                       self.intents_seen_total) * 100
        # Use lower threshold for testnet mode to increase exploration
        try:
            if hasattr(self.config, 'trading') and self.config.trading:
                mode = self.config.trading.mode if hasattr(
                    self.config.trading, 'mode') else "production"
            elif isinstance(self.config, dict):
                mode = self.config.trading.mode
            else:
                mode = "production"
        except (AttributeError, TypeError):
            mode = "production"

        threshold_pct = 20.0 if mode == "testnet" else 50.0  # Lower threshold for testnet

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
            exposure_summary = payload.get("exposure_summary", {})
            if exposure_summary:
                self._exposure_cache = exposure_summary
                self._exposure_cache_timestamp = time.time()
                self.logger.debug(
                    f"✅ Exposure cache updated: {len(exposure_summary)} symbols")
        except Exception as e:
            self.logger.warning(f"Failed to update exposure cache: {e}")

    def _precheck_exposure_cache(self, symbol: str, side: str, notional_usd: float) -> bool:
        """
        Pre-check exposure limits using cached exposure summary.

        Returns True if trade should be allowed, False if blocked by exposure limits.
        """
        if not self._exposure_cache:
            # No cache available, allow trade (fail-open for safety)
            return True

        try:
            # Check if cache is stale (older than 30 seconds)
            cache_age = time.time() - self._exposure_cache_timestamp
            if cache_age > 30.0:
                self.logger.debug(
                    f"Exposure cache stale ({cache_age:.1f}s), allowing trade")
                return True

            # Get exposure data for symbol
            symbol_exposure = self._exposure_cache.get(symbol, {})
            current_exposure = symbol_exposure.get("current_exposure_usd", 0.0)
            max_exposure = symbol_exposure.get(
                "max_exposure_usd", float('inf'))

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
            self.logger.warning(
                f"Error in exposure cache precheck: {e}, allowing trade")
            return True

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
        ts_ms = int(time.time() * 1000)
        return f"flip:{symbol}:{side}:{ts_ms}"
    
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
        # 1. Check State
        pos_state = self._get_position_state(symbol)
        
        if pos_state == "UNKNOWN":
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: State UNKNOWN, fail-closed (NRR-PORTFOLIO-UNKNOWN)"
            )
            return "NRR-PORTFOLIO-UNKNOWN"
            
        if pos_state == "FLAT":
            self.logger.debug(f"[{symbol}] FLIP_ORCHESTRATION: FLAT, allowing OPEN {intent_side}")
            return None
            
        # 2. Check Flip vs Same-Side
        is_flip = self._is_flip(symbol, intent_side, pos_state)
        
        if not is_flip:
            # Must be same-side (or some weird state), treat as Anti-Pyramiding
            self.logger.warning(
                f"[{symbol}] FLIP_ORCHESTRATION: BLOCK - Same-side pyramiding not allowed "
                f"(state={pos_state}, intent={intent_side})"
            )
            return "ANTI_PYRAMIDING_BLOCK"
            
        # 3. Handle Flip
        # Emit Reduce-Only Close
        rid = original_pld.get("rid", f"flip-{int(time.time())}")
        self._emit_reduce_only_close(symbol, "flip_orchestration", f"{rid}-close")
        
        # Schedule Retry (Defer Open)
        # Use simple cooldown for now (e.g. 5s) or fetch per-symbol config
        retry_key = self._generate_flip_retry_key(symbol, intent_side, seed=rid)
        now_ms = int(time.time() * 1000)
        
        # Get stale TTL for retry delay
        # Get stale TTL for retry delay (Strict)
        stale_ttl_sec = float(getattr(self.config.domains.position_tracking, 'positions_stale_ttl_sec', 5.0))
        next_allowed_ts = now_ms + int(stale_ttl_sec * 1000)
        
        # Prepare minimal original event for deferred retry
        original_event = {
            "event_name": f"EVT:{source.upper()}_SIGNAL_PRODUCED" if source != "aurora" else "EVT:FEATURES_CALCULATED",
            "payload_min": {
                "symbol": symbol,
                "side": intent_side,
                "qty_hint": original_pld.get("qty_hint", original_pld.get("position_size_usd")),
                "price_ctx": original_pld.get("price_ctx"),
                "strategy_id": original_pld.get("strategy_id", source),
                "cooldown_class": "flip",
                "rid": original_pld.get("rid", f"flip_{retry_key}"),
            }
        }
        
        # Build why_chain for debugging
        why_chain = original_pld.get("why_chain", []).copy() if isinstance(original_pld.get("why_chain"), list) else []
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
        
        return "FLIP_CLOSE_PENDING"

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
        retry_key = self._generate_flip_retry_key(symbol, intent_side, seed=original_pld.get("rid"))
        now_ms = int(time.time() * 1000)
        
        # Get stale TTL for retry delay
        # Get stale TTL for retry delay (Strict)
        stale_ttl_sec = float(getattr(self.config.domains.position_tracking, 'positions_stale_ttl_sec', 5.0))
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
            "rid": original_pld.get("rid", f"flip_close_{retry_key}"),
        }
        
        self.fsm.emit("CMD:CLOSE", close_pld)
        
        # Prepare minimal original event for deferred retry
        original_event = {
            "event_name": f"EVT:{source.upper()}_SIGNAL_PRODUCED" if source != "aurora" else "EVT:FEATURES_CALCULATED",
            "payload_min": {
                "symbol": symbol,
                "side": intent_side,
                "qty_hint": original_pld.get("qty_hint", original_pld.get("position_size_usd")),
                "price_ctx": original_pld.get("price_ctx"),
                "strategy_id": original_pld.get("strategy_id", source),
                "cooldown_class": "flip",
                "rid": original_pld.get("rid", f"flip_{retry_key}"),
            }
        }
        
        # Build why_chain for debugging
        why_chain = original_pld.get("why_chain", []).copy() if isinstance(original_pld.get("why_chain"), list) else []
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
            
            positions = self.latest_portfolio.get("positions", [])
            if not positions:
                return True  # Empty positions = confirmed FLAT
            
            for pos in positions:
                pos_symbol = pos.get("symbol", "")
                if pos_symbol != symbol:
                    continue
                    
                # Check positionAmt (Binance format)
                qty_str = pos.get("positionAmt", "0")
                try:
                    qty = abs(float(qty_str))
                except (ValueError, TypeError):
                    qty = 0.0
                
                # Position exists if qty > threshold
                flat_threshold = 1e-9
                if qty > flat_threshold:
                    self.logger.debug(f"[{symbol}] _check_symbol_is_flat: Position exists, qty={qty}")
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

    def _get_risk_skew_config(self, key: str, default: Any) -> Any:
        """
        Get risk_skew config value from domains config.
        
        Commit 5: Risk Skew Guard configuration.
        Config path: domains.decision_making.risk_skew.<key>
        
        Fail-closed: If risk_skew not configured or key missing → return default (NOT crash).
        This is P2 (diagnostics), not P0 (trading critical).
        """
        try:
            # Direct Pydantic access
            risk_skew = self.config.domains.decision_making.risk_skew
            if risk_skew:
                return getattr(risk_skew, key, default)
            return default
        except (AttributeError, TypeError):
            # Risk skew optional feature
            return default
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
        tick_size = getattr(spec, 'tick_size', None)
        step_size = getattr(spec, 'step_size', None)
        
        if tick_size is None or step_size is None:
            raise ValueError(
                f"Missing precision for {symbol}: tick_size={tick_size}, step_size={step_size}"
            )
        
        return float(tick_size), float(step_size)


# Backward-compat alias used by legacy runtime tests.
DecisionMakingLogic = DecisionMaking
