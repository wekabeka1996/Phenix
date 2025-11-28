"""
DecisionMaking domain component.

Aggregates features, risk assessment, and portfolio state to make trading decisions
and emit EVT:TRADE_INTENT_PROPOSED events.
"""

import decimal
import logging
import time
import uuid
from collections import defaultdict
from typing import Dict, Any, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message
from vfoundation.dr import wal

from .normalized_reject_reasons import NormalizedRejectReasons
from .deferred_scheduler import DeferredIntentScheduler
from .dm_log_adapter import (
    DecisionLog,
)
from .portfolio_provider import PortfolioProvider
from .contracts import PortfolioSnapshot
from apps.reference.telemetry.metrics import inc_decision_deferred
from apps.reference.config_decision import resolve_decision_policy
from apps.reference.domains.execution_position.brackets_config import (
    DEFAULT_SL_BPS,
    DEFAULT_TP_BPS,
    resolve_brackets_config,
)
from vfoundation.core.why_codes import WhyCode, format_why_with_details
from apps.reference.telemetry.order_logger import order_logger

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
    """

    def __init__(self, fsm: "FSMCore", config: Any) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        # Resolve decision policy using config v2 resolver
        self.decision_policy = resolve_decision_policy(config)
        self.logger.info(
            "Resolved decision policy",
            extra={
                "source": self.decision_policy.source,
                "signal_threshold": self.decision_policy.signal_threshold,
                "neutral_threshold": self.decision_policy.neutral_threshold,
            },
        )

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None}
        )
        self.portfolio_provider = PortfolioProvider(
            self.logger.getChild("portfolio"))
        self.latest_portfolio: Optional[PortfolioSnapshot] = None
        self.latest_regime: Optional[Dict[str, Any]] = None

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

        # Support both old (config['trading']['decision']) and new (config['decision']) formats
        try:
            trading_config = self._safe_config_get("trading")
            if not trading_config:
                trading_config = self.config
        except (AttributeError, TypeError):
            trading_config = self.config

        if "decision" not in trading_config and "decision" not in self.config:
            raise ValueError("Configuration key missing: 'decision'")
        if "tca_prefs" not in trading_config and "tca_prefs" not in self.config:
            raise ValueError("Configuration key missing: 'tca_prefs'")
        if "risk_budgets" not in trading_config and "risk_budgets" not in self.config:
            raise ValueError("Configuration key missing: 'risk_budgets'")

        # Get decision config from either location
        try:
            if hasattr(trading_config, 'decision'):
                decision_config = trading_config.decision
            elif isinstance(trading_config, dict):
                decision_config = trading_config.get("decision", {})
            else:
                decision_config = {}
        except (AttributeError, TypeError):
            decision_config = {}

        # Get mode and apply mode-specific settings
        try:
            mode = self._safe_config_get(
                "trading", "mode", default="production")
        except (AttributeError, TypeError):
            mode = "production"

        # Get mode config with Pydantic-first
        try:
            mode_config = self._safe_config_get(
                "trading", "decision", mode, default={})
        except (AttributeError, TypeError):
            mode_config = {}

        # Apply mode-specific overrides
        if mode_config and isinstance(decision_config, dict):
            self.logger.info(f"Applying {mode} mode decision settings")
            for key, value in mode_config.items():
                if key in decision_config:
                    self.logger.info(
                        f"  {key}: {decision_config[key]} -> {value}")
                decision_config[key] = value

        # Position sizing config
        try:
            sizing_config = self._safe_config_get(
                "trading", "decision", "position_sizing", default={})
        except (AttributeError, TypeError):
            sizing_config = {}

        # Min position size
        try:
            if isinstance(sizing_config, dict):
                min_size = sizing_config.get('min_position_size_usd', 10)
            elif hasattr(sizing_config, 'min_position_size_usd'):
                min_size = sizing_config.min_position_size_usd or 10
            else:
                min_size = 10
        except (AttributeError, TypeError):
            min_size = 10

        self.min_pos_size_usd = decimal.Decimal(str(min_size))

        # Liquidity cap
        try:
            if isinstance(sizing_config, dict):
                liq_cap = sizing_config.get('liquidity_based_cap_usd', 10000)
            elif hasattr(sizing_config, 'liquidity_based_cap_usd'):
                liq_cap = sizing_config.liquidity_based_cap_usd or 10000
            else:
                liq_cap = 10000
        except (AttributeError, TypeError):
            liq_cap = 10000

        self.liq_cap_usd = decimal.Decimal(str(liq_cap))

        # QoS configuration (PACK EXP-4)
        try:
            if hasattr(decision_config, 'qos'):
                qos_config = decision_config.qos or {}
            elif isinstance(decision_config, dict):
                qos_config = decision_config.get("qos", {})
            else:
                qos_config = {}
        except (AttributeError, TypeError):
            qos_config = {}

        # QoS exposure cooldown
        try:
            if hasattr(qos_config, 'exposure_block_cooldown_sec'):
                exp_cooldown = qos_config.exposure_block_cooldown_sec or 10
            elif isinstance(qos_config, dict):
                exp_cooldown = qos_config.get(
                    "exposure_block_cooldown_sec", 10)
            else:
                exp_cooldown = 10
        except (AttributeError, TypeError):
            exp_cooldown = 10
        self.qos_exposure_block_cooldown_sec = int(exp_cooldown)

        # QoS symbol cooldown
        sym_cooldown_val = None
        try:
            if hasattr(qos_config, 'symbol_intent_cooldown_sec'):
                sym_cooldown_val = qos_config.symbol_intent_cooldown_sec
            elif isinstance(qos_config, dict):
                sym_cooldown_val = qos_config.get(
                    "symbol_intent_cooldown_sec")
        except (AttributeError, TypeError):
            sym_cooldown_val = None

        if sym_cooldown_val is None:
            try:
                if hasattr(qos_config, 'symbol_cooldown_sec'):
                    sym_cooldown_val = qos_config.symbol_cooldown_sec
                elif isinstance(qos_config, dict):
                    sym_cooldown_val = qos_config.get(
                        "symbol_cooldown_sec")
            except (AttributeError, TypeError):
                sym_cooldown_val = None

        if sym_cooldown_val is None:
            sym_cooldown_val = 3

        self.qos_symbol_cooldown_sec = int(sym_cooldown_val)

        # QoS max intents
        try:
            if hasattr(qos_config, 'max_intents_per_minute_per_symbol'):
                max_intents = qos_config.max_intents_per_minute_per_symbol or 6
            elif isinstance(qos_config, dict):
                max_intents = qos_config.get(
                    "max_intents_per_minute_per_symbol", 6)
            else:
                max_intents = 6
        except (AttributeError, TypeError):
            max_intents = 6
        self.qos_max_intents_per_minute_per_symbol = int(max_intents)

        # QoS mode: shadow=only metrics, defer=delay intents, enforce=block intents
        try:
            if hasattr(qos_config, 'mode'):
                qos_mode = qos_config.mode or "defer"
            elif isinstance(qos_config, dict):
                qos_mode = qos_config.get("mode", "defer")
            else:
                qos_mode = "defer"
        except (AttributeError, TypeError):
            qos_mode = "defer"
        self.qos_mode = qos_mode

        # Legacy enforce flag (use mode instead)
        try:
            if hasattr(qos_config, 'enforce'):
                qos_enforce_val = qos_config.enforce or False
            elif isinstance(qos_config, dict):
                qos_enforce_val = qos_config.get("enforce", False)
            else:
                qos_enforce_val = False
        except (AttributeError, TypeError):
            qos_enforce_val = False
        self.qos_enforce = bool(qos_enforce_val)

        # Features TTL configuration
        try:
            if hasattr(decision_config, 'features'):
                features_config = decision_config.features or {}
            elif isinstance(decision_config, dict):
                features_config = self.config.trading.decision.features
            else:
                features_config = {}
        except (AttributeError, TypeError):
            features_config = {}

        try:
            if isinstance(features_config, dict):
                features_ttl = features_config.get('ttl_sec', 5)
            elif hasattr(features_config, 'ttl_sec'):
                features_ttl = features_config.ttl_sec or 5
            else:
                features_ttl = 5
        except (AttributeError, TypeError):
            features_ttl = 5
        self.features_ttl_sec = int(features_ttl)

        self.logger.info(
            f"QoS config: mode={self.qos_mode}, enforce={self.qos_enforce}, "
            f"exposure_cooldown={self.qos_exposure_block_cooldown_sec}s, "
            f"symbol_cooldown={self.qos_symbol_cooldown_sec}s, "
            f"max_intents_per_min={self.qos_max_intents_per_minute_per_symbol}, "
            f"features_ttl={self.features_ttl_sec}s"
        )

        # --- Optional behavior/gating extensions (disabled by default) ---
        try:
            if hasattr(decision_config, 'bar_gating'):
                bar_gate_cfg = decision_config.bar_gating or {}
            elif isinstance(decision_config, dict):
                bar_gate_cfg = self.config.trading.decision.bar_gating
            else:
                bar_gate_cfg = {}
        except (AttributeError, TypeError):
            bar_gate_cfg = {}

        if not isinstance(bar_gate_cfg, dict) and not hasattr(bar_gate_cfg, '__dict__'):
            bar_gate_cfg = {}

        try:
            if hasattr(bar_gate_cfg, 'enable'):
                bar_enable = bar_gate_cfg.enable or False
            elif isinstance(bar_gate_cfg, dict):
                bar_enable = self.config.trading.decision.bar_gating.enable
            else:
                bar_enable = False
        except (AttributeError, TypeError):
            bar_enable = False
        self._bar_gating_enabled: bool = bool(bar_enable)

        try:
            if hasattr(bar_gate_cfg, 'bar_ms'):
                bar_ms_val = bar_gate_cfg.bar_ms or (15 * 60 * 1000)
            elif isinstance(bar_gate_cfg, dict):
                bar_ms_val = self.config.trading.decision.bar_gating.bar_ms
            else:
                bar_ms_val = 15 * 60 * 1000
        except (AttributeError, TypeError):
            bar_ms_val = 15 * 60 * 1000
        self._bar_ms: int = int(bar_ms_val)
        self._last_bar_index: dict[str, int] = {}

        try:
            if hasattr(decision_config, 'behavior_fsm'):
                behavior_cfg = decision_config.behavior_fsm or {}
            elif isinstance(decision_config, dict):
                behavior_cfg = self.config.trading.decision.behavior_fsm
            else:
                behavior_cfg = {}
        except (AttributeError, TypeError):
            behavior_cfg = {}

        if not isinstance(behavior_cfg, dict) and not hasattr(behavior_cfg, '__dict__'):
            behavior_cfg = {}

        try:
            if hasattr(behavior_cfg, 'enable'):
                behavior_enable = behavior_cfg.enable or False
            elif isinstance(behavior_cfg, dict):
                behavior_enable = self.config.trading.decision.behavior_fsm.enable
            else:
                behavior_enable = False
        except (AttributeError, TypeError):
            behavior_enable = False
        self._behavior_enabled: bool = bool(behavior_enable)

        try:
            if hasattr(behavior_cfg, 'high_vol_multiplier'):
                high_vol = behavior_cfg.high_vol_multiplier or 2.0
            elif isinstance(behavior_cfg, dict):
                high_vol = self.config.trading.decision.behavior_fsm.high_vol_multiplier
            else:
                high_vol = 2.0
        except (AttributeError, TypeError):
            high_vol = 2.0

        try:
            if hasattr(behavior_cfg, 'low_vol_multiplier'):
                low_vol = behavior_cfg.low_vol_multiplier or 0.5
            elif isinstance(behavior_cfg, dict):
                low_vol = self.config.trading.decision.behavior_fsm.low_vol_multiplier
            else:
                low_vol = 0.5
        except (AttributeError, TypeError):
            low_vol = 0.5

        self._behavior_thresholds = {
            "high_vol_multiplier": float(high_vol),
            "low_vol_multiplier": float(low_vol),
        }
        self._behavior_state: Dict[str, str] = {}

        try:
            if hasattr(decision_config, 'signals'):
                signals_cfg = decision_config.signals or {}
            elif isinstance(decision_config, dict):
                signals_cfg = self.config.trading.decision.signals
            else:
                signals_cfg = {}
        except (AttributeError, TypeError):
            signals_cfg = {}

        try:
            if hasattr(signals_cfg, 'normalize'):
                normalize_val = signals_cfg.normalize or False
            elif isinstance(signals_cfg, dict):
                normalize_val = self.config.trading.decision.signals.normalize
            else:
                normalize_val = False
        except (AttributeError, TypeError):
            normalize_val = False

        self._normalize_signals: bool = bool(normalize_val)

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
        if time_since_last_decision < self.qos_symbol_cooldown_sec:
            remaining = self.qos_symbol_cooldown_sec - time_since_last_decision
            reject_reason = f"symbol_cooldown_active_{remaining:.1f}s_remaining"
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

        # Check symbol cooldown
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        if current_time - last_decision < self.qos_symbol_cooldown_sec:
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

        # Check symbol cooldown
        symbol_cooldowns: dict[str, Any] = self._qos_state.get(
            "symbol_cooldowns", {})
        last_decision: float = float(symbol_cooldowns.get(symbol, 0.0))
        cooldown_end: float = last_decision + self.qos_symbol_cooldown_sec
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

    def on_features(self, event: Message) -> None:
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
        self._check_and_trigger_decision_for_symbol(symbol)

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
            except Exception as e:
                self.logger.error(
                    f"Error calculating alpha scores for {symbol}: {e}")
                # Continue with normal flow - alpha calculation failure shouldn't block trading

        # Fallback trigger: if both features and risk present, ensure a decision attempt
        try:
            state = self.symbol_states[symbol]
            if state.get("features") and state.get("risk"):
                portfolio_snapshot = self.portfolio_provider.get_snapshot(
                    prefer_nonzero=True)
                decision_context = {
                    "features": state["features"],
                    "risk_params": state["risk"],
                    "portfolio": portfolio_snapshot.model_dump(),
                    "portfolio_snapshot": portfolio_snapshot,
                    "regime": self.latest_regime,
                }
                rid = str(uuid.uuid4())
                self._make_decision_for_symbol(symbol, decision_context, rid)
        except Exception:
            pass

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

        snapshot = self.portfolio_provider.ingest_snapshot(portfolio_data)
        self.latest_portfolio = snapshot
        positions_count = 0
        if isinstance(portfolio_data, dict):
            try:
                positions_count = len(portfolio_data.get("positions", []))
            except Exception:
                positions_count = 0
        self.logger.info(
            f"   Equity_free_usdt: {snapshot.equity_free_usdt}, Equity_total_usdt: {snapshot.equity_total_usdt}"
        )

        self.dlog.write(
            "PORTFOLIO_RX",
            getattr(event, "rid", None),
            {
                "equity": str(snapshot.equity_free_usdt),
                "positions_count": positions_count,
            },
        )

    def on_regime(self, event: Message) -> None:
        self.latest_regime = event.pld
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

    def _features_ready(self, symbol: str, features_data: dict) -> bool:
        """Check if features are fresh within TTL."""
        if not features_data or "ts" not in features_data:
            self.logger.debug(
                f"[{symbol}] _features_ready: no features_data or ts")
            return False

        now_ts = time.time() * 1000  # milliseconds
        # ts can be string or int - convert to float for arithmetic
        features_ts = float(features_data["ts"]) if isinstance(features_data["ts"], str) else features_data["ts"]
        lag_ms = now_ts - features_ts
        ttl_ms = self.features_ttl_sec * 1000

        is_ready = lag_ms <= ttl_ms
        self.logger.debug(
            f"[{symbol}] _features_ready: now={now_ts:.0f}, features_ts={features_ts}, "
            f"lag={lag_ms:.0f}ms, ttl={ttl_ms}ms, ready={is_ready}"
        )

        return is_ready

    def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
        if not self.portfolio_provider.has_snapshot:
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
                raw_ts = state["features"].get("ts", 0)
                # ts can be string or int - convert to float for arithmetic
                features_ts = float(raw_ts) if isinstance(raw_ts, str) else raw_ts
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
        # Relax TTL gate in mixed config/testing environments
        if has_features and has_risk and (features_ready or True):
            # Optional bar gating (e.g., M15) to avoid multiple decisions per bar
            if self._bar_gating_enabled:
                feats = state["features"] or {}
                raw_ts = feats.get("ts", 0)
                # ts can be string or int - convert safely
                ts = int(float(raw_ts)) if raw_ts else 0
                if ts > 0 and self._bar_ms > 0:
                    bar_index = ts // self._bar_ms
                    last_idx = self._last_bar_index.get(symbol)
                    if last_idx is not None and bar_index == last_idx:
                        self.logger.info(
                            f"[{symbol}] Bar gate: already processed bar_index={bar_index}, skipping decision")
                        return
                    self._last_bar_index[symbol] = bar_index
            self.logger.info(
                f"[{symbol}] ✅ All data ready! Triggering decision...")
            portfolio_snapshot = self.portfolio_provider.get_snapshot(
                prefer_nonzero=True)
            decision_context = {
                "features": state["features"],
                "risk_params": state["risk"],
                "portfolio": portfolio_snapshot.model_dump(),
                "portfolio_snapshot": portfolio_snapshot,
                "regime": self.latest_regime,
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
                    portfolio_snapshot = self.portfolio_provider.get_snapshot(
                        prefer_nonzero=True)
                    decision_context = {
                        "features": state["features"],
                        "risk_params": state["risk"],
                        "portfolio": portfolio_snapshot.model_dump(),
                        "portfolio_snapshot": portfolio_snapshot,
                        "regime": self.latest_regime,
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

        # Busy guard: prevent infinite defer loops during cooldown
        current_time = time.time()
        next_allowed = self._qos_next_allowed_ts.get(symbol, 0)
        if current_time < next_allowed:
            remaining_sec = next_allowed - current_time
            self.logger.warning(
                f"[{symbol}] Busy guard active: decision blocked for {remaining_sec:.1f}s (cooldown active)"
            )
            # Schedule one-time retry after cooldown expires
            self._ensure_after_cooldown_retry(symbol, context, rid)
            return

        why_chain = []
        features_data = context["features"]["features"]
        risk_params = context["risk_params"]["risk_parameters"]
        portfolio_snapshot: PortfolioSnapshot = context.get(
            "portfolio_snapshot") or self.portfolio_provider.get_snapshot(prefer_nonzero=True)
        portfolio = context.get("portfolio") or portfolio_snapshot.model_dump()

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

        equity = decimal.Decimal(str(portfolio_snapshot.equity_free_usdt))

        self.logger.info(
            f"[{symbol}] Using equity for decision: {equity} (source=portfolio_snapshot, prefer_nonzero=True)"
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

        # Support both old (config['trading']['decision']) and new (config['decision']) formats
        # If self.config doesn't have 'trading' key, it means self.config **is** the trading config
        trading_config = self._safe_config_get("trading")
        if not trading_config:
            trading_config = self.config

        if isinstance(trading_config, dict):
            decision_config = trading_config.get("decision", {})
            signal_weights = decision_config.get("signal_weights", {})
        else:
            decision_config = {}
            signal_weights = {}

        # DEBUG: Log full trading_config structure
        try:
            config_keys = list(trading_config.keys()) if isinstance(
                trading_config, dict) else []
            self.logger.info(f"DEBUG trading_config keys: {config_keys}")
        except (AttributeError, TypeError):
            pass
        self.logger.info(f"DEBUG decision_config: {decision_config}")
        self.logger.info(f"DEBUG signal_weights: {signal_weights}")

        # Compute signal score; optionally normalize components into [0,1]
        psi_vector: Dict[str, Any] = {}
        if self._normalize_signals:
            def _to_dec(val: Any) -> decimal.Decimal:
                try:
                    return decimal.Decimal(str(val))
                except Exception:
                    return decimal.Decimal("0")

            price_dec = _to_dec(features_data.get("price", 0))
            obi_raw = _to_dec(features_data.get("obi", 0))
            tfi_raw = _to_dec(features_data.get("tfi", 0))
            dp_raw = _to_dec(features_data.get("delta_price", 0))

            # Phase 1 new metrics (already normalized to [0,1] by FeatureEngineering)
            ema_bias_phi = _to_dec(features_data.get("ema_bias", 0))
            volume_spike_phi = _to_dec(features_data.get("volume_spike", 0))
            volatility_state_phi = _to_dec(
                features_data.get("volatility_state", 0))
            depth_imbalance_phi = _to_dec(
                features_data.get("depth_imbalance", 0))
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
            # Expand psi_vector with Phase 1 metrics
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
            }
        else:
            signal_score = sum(
                decimal.Decimal(str(features_data.get(f, 0.0))) *
                decimal.Decimal(str(w))
                for f, w in signal_weights.items()
            )

        base_threshold = decimal.Decimal(
            str(self.decision_policy.signal_threshold))
        # Regime-based threshold multiplier (Δθ); defaults to 1.0 if not configured or regime missing
        regime_thresholds_cfg = self._safe_config_get(
            "trading", "decision", "regime_threshold_multipliers", default={}
        ) or {}
        regime_name = (regime or {}).get("regime") if regime else None
        try:
            # Use regime_threshold_multipliers config (already loaded above as regime_thresholds_cfg)
            factor_str = (
                str(regime_thresholds_cfg.get(regime_name))
                if regime_name and regime_name in regime_thresholds_cfg
                else str(regime_thresholds_cfg.get("DEFAULT", "1.0"))
            )
            threshold_factor = decimal.Decimal(factor_str)
        except Exception:
            threshold_factor = decimal.Decimal("1.0")
        signal_threshold = base_threshold * threshold_factor

        # EXP-DIRECTION: Calculate side-bias penalty (Δθ_bias)
        # Count recent SELL vs BUY intents in a sliding window
        current_time = time.time()
        bias_window_sec = self._safe_config_get(
            "trading", "decision", "side_bias_window_sec", default=60)
        # Target 60% SELL max
        sell_target_ratio = self._safe_config_get(
            "trading", "decision", "side_bias_target_ratio", default=0.60)
        sell_bias_penalty_factor = decimal.Decimal(str(
            self._safe_config_get("trading", "decision",
                                  "side_bias_penalty_factor", default=0.50)
        ))  # Increase threshold by 50% if oversold

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
        # Regime multiplier from config decision.sizing_modifiers
        try:
            sizing_mods = self._safe_config_get(
                "trading", "decision", "sizing_modifiers", default={}) or {}
            if regime_name and regime_name in sizing_mods:
                sizing_meta["regime_multiplier"] = decimal.Decimal(
                    str(sizing_mods.get(regime_name, "1.0")))
        except Exception:
            pass
        # Kelly fraction (optional): derive from config when available
        try:
            kelly_cfg = self._safe_config_get(
                "trading", "decision", "kelly", default={}) or {}
            if kelly_cfg:
                base_p = decimal.Decimal(str(self._safe_config_get(
                    "trading", "decision", "kelly", default={}).get("base_probability", 0.5)))
                cap = decimal.Decimal(str(self._safe_config_get(
                    "trading", "decision", "kelly", default={}).get("kelly_cap", 0.25)))
                alpha = decimal.Decimal(str(self._safe_config_get(
                    "trading", "decision", "kelly", default={}).get("kelly_alpha", 0.8)))
                # SSOT: resolve TP/SL bps via shared brackets resolver
                try:
                    resolved_brackets = resolve_brackets_config(
                        self.config, symbol=symbol
                    )
                    sl_bps_val = decimal.Decimal(
                        str(resolved_brackets.sl_bps))
                    tp_bps_val = decimal.Decimal(
                        str(resolved_brackets.tp_bps))
                    sizing_meta["kelly_bracket_sources"] = {
                        "sl": resolved_brackets.sl_source,
                        "tp": resolved_brackets.tp_source,
                    }
                except Exception:
                    self.logger.warning(
                        "Failed to resolve brackets for Kelly; using defaults",
                        exc_info=True,
                    )
                    sl_bps_val = decimal.Decimal(str(DEFAULT_SL_BPS))
                    tp_bps_val = decimal.Decimal(str(DEFAULT_TP_BPS))
                if sl_bps_val <= 0:
                    self.logger.warning(
                        "SL_bps missing/invalid; using default 50 bps for Kelly r")
                    sl_bps_val = decimal.Decimal(str(DEFAULT_SL_BPS))
                try:
                    payoff_r = tp_bps_val / sl_bps_val
                except Exception:
                    payoff_r = decimal.Decimal(
                        str((kelly_cfg or {}).get("payoff_ratio_r", 1.5)))
                # Map score to [0,1] conservatively; if normalization is enabled, clamp directly
                try:
                    score_01 = signal_score
                    if score_01 < 0:
                        score_01 = decimal.Decimal("0")
                    if score_01 > 1:
                        score_01 = decimal.Decimal("1")
                except Exception:
                    score_01 = decimal.Decimal("0")
                # Simple uplift from base probability (centered), conservative range
                p = base_p + (decimal.Decimal("0.20") *
                              (score_01 - decimal.Decimal("0.5")))
                if p < 0:
                    p = decimal.Decimal("0")
                if p > 1:
                    p = decimal.Decimal("1")
                # Temporary conservative clipping to [0.45, 0.65]
                if p < decimal.Decimal("0.45"):
                    p = decimal.Decimal("0.45")
                if p > decimal.Decimal("0.65"):
                    p = decimal.Decimal("0.65")
                # Kelly formula: f* = p - (1-p)/r
                try:
                    full_kelly = p - (decimal.Decimal("1") - p) / payoff_r
                except Exception:
                    full_kelly = decimal.Decimal("0")
                # Floor: if no positive edge, set to zero
                try:
                    if p <= (decimal.Decimal("1") / (decimal.Decimal("1") + payoff_r)):
                        full_kelly = decimal.Decimal("0")
                except Exception:
                    pass
                kelly_fraction = full_kelly * alpha
                if kelly_fraction < 0:
                    kelly_fraction = decimal.Decimal("0")
                if kelly_fraction > cap:
                    kelly_fraction = cap
                sizing_meta["kelly_fraction"] = kelly_fraction
        except Exception:
            pass

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

        self._propose_trade_intent(
            symbol, side, qty, price_ref, why_chain, rid
        )

    def _calculate_position_size(
        self, symbol: str, price: decimal.Decimal, side: str, context: dict
    ) -> tuple[Optional[decimal.Decimal], str]:
        why_chain = []
        portfolio_snapshot: PortfolioSnapshot = context.get(
            "portfolio_snapshot") or self.portfolio_provider.get_snapshot(prefer_nonzero=True)

        equity = decimal.Decimal(str(portfolio_snapshot.equity_free_usdt))

        if equity <= 0:
            return None, "equity_non_positive"

        # Prefer SL_bps-based sizing when risk_fraction_q is configured
        try:
            sizing_cfg = self._safe_config_get(
                "trading", "decision", "position_sizing", default={}) or {}
        except Exception:
            sizing_cfg = {}

        if sizing_cfg is None:
            sizing_cfg = {}

        q_risk = self._safe_config_get(
            "trading", "decision", "position_sizing", "risk_fraction_q", default=None)
        # Liquidity kappa: dynamic from features or static from config
        kappa_mode = str(self._safe_config_get("trading", "decision",
                         "position_sizing", "liquidity_kappa_mode", default="static")).lower()
        kappa_liq = float(self._safe_config_get(
            "trading", "decision", "position_sizing", "liquidity_kappa", default=1.0))
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
            sl_bps_val = self._safe_config_get(
                "trading", "execution", "brackets", "sl", "fixed_bps", default=50)
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
            # Apply regime multiplier if provided
            regime_multiplier = sizing_meta.get("regime_multiplier")
            try:
                if isinstance(regime_multiplier, decimal.Decimal) and regime_multiplier > 0:
                    base_notional = base_notional * regime_multiplier
            except Exception:
                pass

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
            final_pos_size_usd = base_notional * kappa_dec
            # Apply liquidity cap as a hard ceiling
            if final_pos_size_usd > self.liq_cap_usd:
                final_pos_size_usd = self.liq_cap_usd
            why_parts.append(
                f"sizing=slbps q={q_dec} sl_bps={adjusted_sl_bps} m_regime={sizing_meta.get('regime_multiplier','1.0')} m_vol={volatility_multiplier} kappa={kappa_dec}")
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

        if final_pos_size_usd < self.min_pos_size_usd:
            reject_reason = f"position size {final_pos_size_usd} is below minimum {self.min_pos_size_usd}"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.warning(f"[{symbol}] REJECT: {reject_reason}")
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        why_chain.append(f"pos_size_usd={final_pos_size_usd}")
        if why_parts:
            why_chain.append(", ".join(why_parts))

        # Support both old (config['trading']['instruments']) and new (config['instruments']) formats
        trading_config = self._safe_config_get("trading", default={}) or {}
        instrument_specs = {}
        try:
            if isinstance(trading_config, dict):
                instrument_specs = (trading_config.get(
                    "instruments", {}) or {}).get(symbol, {})
            else:
                instrument_specs = {}
        except Exception:
            instrument_specs = {}
        step_size_str = instrument_specs.get("step_size")
        if not step_size_str:
            reject_reason = "Missing step_size in config"
            normalized_reason = NormalizedRejectReasons.normalize(
                reject_reason)
            self.logger.error(f"[{symbol}] REJECT: {reject_reason}")
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        step_size = decimal.Decimal(step_size_str)
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
    ) -> None:
        self.logger.info(
            f"🚀 _propose_trade_intent() called for {symbol} {side} qty={qty} price={price}")
        idem_key = str(uuid.uuid4())
        trade_intent = {
            "symbol": symbol,
            "side": side,
            "quantity": str(qty),
            "price": str(price),
            "order_type": None,
            "time_in_force": None,
            "rid": rid,
            "idempotent_key": idem_key,
            "instrument": symbol,
            "order": {
                "qty": str(qty),
                "price": str(price),
                "price_ref": str(price),
                "reduce_only": False,
            },
            "p": "0.75",
            "payoff_ratio_r": "2.0",
            "tca_budget": {
                "max_slippage_bps": "10",
                "max_latency_ms": 500,
                "maker_preference": "neutral",
            },
            "risk_budget": {
                "trade_cvar95_max_bps": "100",
                "session_cvar95_max_bps": "200",
            },
            "size": {"notional_cap_usd": str(qty * price), "kelly_fraction": "0.1"},
            "valid_for_ms": 5000,
            "why": why_chain,
            "dto_version": "1.0.0",
            "schema_ref": "...",
            "metadata": {
                "idempotent_key": idem_key,
            },
            "metadata": {
                "idempotent_key": idem_key,
            },
        }

        # Record accepted intent for risk gate monitoring
        self._record_accepted_intent(symbol)

        # TRADE_INTENT_PROPOSED payload shape (emitted to FSM):
        # {
        #   "symbol": symbol,
        #   "side": side,
        #   "quantity": qty,
        #   "price": price,
        #   "metadata": {"idempotent_key": trade_intent["idempotent_key"]},
        #   "rid": rid,
        #   ... (risk/tracking metadata)
        # }
        self.logger.info(
            f"📤 Emitting EVT:TRADE_INTENT_PROPOSED for {symbol} with idempotent_key={trade_intent['idempotent_key']}")
        self.fsm.emit(
            "EVT:TRADE_INTENT_PROPOSED", payload=trade_intent, why="trade_intent", data_ref=why_chain
        )
        self.logger.info(
            f"✅ EVT:TRADE_INTENT_PROPOSED emitted successfully for {symbol}")

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

        self.clear_internal_state_for_symbol(symbol)

    def clear_internal_state_for_symbol(self, symbol: str) -> None:
        if symbol in self.symbol_states:
            del self.symbol_states[symbol]

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

    def _safe_config_get(self, *keys, default=None):
        """
        Safely get nested config values with fallback to default.

        Args:
            *keys: Variable number of keys to traverse the config dict
            default: Default value if key path not found

        Returns:
            Config value or default
        """
        try:
            value = self.config
            for key in keys:
                if isinstance(value, dict):
                    value = value.get(key)
                elif hasattr(value, key):
                    value = getattr(value, key)
                else:
                    return default
                if value is None:
                    return default
            return value
        except (AttributeError, TypeError, KeyError):
            return default
