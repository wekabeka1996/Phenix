"""DecisionMaking domain facade and compatibility surface.

Phase 14A moved most decision logic into focused helpers, but this module still
owns delegate construction, shared mutable state, event subscriptions, and a
small set of glue paths that preserve legacy imports and method names.
"""

import decimal
import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from apps.reference.core.time.clock import Clock, LiveClock
from vfoundation.core.protocol import Message
from apps.reference.config_models import AuroraConfig
from apps.reference.domain_config import DomainConfigResolver
from apps.reference.telemetry.order_logger import order_logger
from apps.reference.telemetry.regime_confidence_audit import (
    emit_regime_decision_audit,
)
from vfoundation.obs.domain_bridge import DomainBridge

from apps.reference.config_contract import ConfigContractError
from .normalized_reject_reasons import NormalizedRejectReasons
from .config_resolver import DMConfigResolver
from .qos_rate_control import QoSRateControl
from .position_queries import PositionQueries
from .readiness_gates import ReadinessGates
from .intent_emitter import IntentEmitter
from .flip_orchestration import FlipOrchestrator
from .safety_gates import apply_safety_gates
from .intent_builder import IntentBuilder
from .event_handlers import DMEventHandlers
from .dm_log_adapter import DecisionLog
from .strategy_gateway import StrategyGateway

try:
    from apps.reference.telemetry.alerts import AlertManager as _AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    _AlertManager = None  # type: ignore[assignment]

try:
    from apps.reference.domains.alpha_search import (
        AlphaModelRegistry, MomentumAlphaModel, VolatilityAlphaModel,
    )
    ALPHA_MODELS_AVAILABLE = True
except ImportError:
    ALPHA_MODELS_AVAILABLE = False

if TYPE_CHECKING:
    from vfoundation.core import FSMCore
    from apps.reference.telemetry.alerts import AlertManager


class DecisionMaking:
    """Compose DecisionMaking delegates and expose the legacy facade API.

    The class is intentionally thin in the scoring/business-logic sense, but it
    still owns orchestration boundaries: shared state, helper wiring, bus
    listeners, safety-gate glue, and compatibility shims used by tests and
    callers during the strangler migration.
    """

    def __init__(self, fsm: "FSMCore", config: AuroraConfig, *, clock: Optional[Clock] = None) -> None:
        """Initialize shared state, helpers, and event listeners.

        Contract:
        - ``config`` must already be a typed AuroraConfig.
        - delegates receive shared state by reference, so this facade remains
          the canonical owner of those mutable containers.
        """
        if isinstance(config, dict):
            raise TypeError("DecisionMaking requires AuroraConfig, got dict")
        self.fsm = fsm
        self.config = config
        self._clock: Clock = clock or LiveClock()
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

        # These containers remain owned by the facade because multiple
        # delegates and tests still share them by reference.
        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None})
        self._shared: Dict[str, Any] = {
            "latest_portfolio": None, "latest_regime": None, "latest_warmup": None,
            "latest_structural_regime_by_symbol": {}, "latest_structural_warmup_by_symbol": {},
            "cached_equity_free_usdt": None, "cached_equity_cross_usdt": None,
            "exposure_cache": None, "exposure_cache_timestamp": 0.0,
        }
        self._per_symbol_regimes: Dict[str, Dict[str, Any]] = {}
        # Phase 0.5: per-symbol system stress state ("NORMAL"|"STRESS"|"EXTREME")
        self._system_stress_states: Dict[str, str] = {}
        self._side_intent_window: Dict[str, Dict[str, list]] = {}
        self._pending_flips: Dict[str, Dict[str, Any]] = {}
        self._arb_window_winner: Dict[str, tuple] = {}
        self._arb_signal_buffer: Dict[str, Tuple] = {}
        self._qos_state: dict = defaultdict(lambda: {
            "last_exposure_block": 0.0, "symbol_cooldowns": {},
            "symbol_intent_counts": defaultdict(lambda: {"count": 0, "window_start": 0.0}),
        })
        self._qos_next_allowed_ts: dict = defaultdict(dict)
        self.intents_seen_total: int = 0
        self.intents_blocked_total: int = 0
        self.last_alert_check_time: float = self._clock.now_sec()

        self.alert_manager: Optional["AlertManager"] = None
        if ALERT_MANAGER_AVAILABLE and _AlertManager is not None:
            try:
                self.alert_manager = _AlertManager(
                    config=config, logger=self.logger.getChild("alerts"))
            except Exception:
                self.logger.warning("AlertManager init failed", exc_info=True)

        self.alpha_registry = None
        if ALPHA_MODELS_AVAILABLE:
            self.alpha_registry = AlphaModelRegistry()
            self.alpha_registry.register(MomentumAlphaModel())
            self.alpha_registry.register(VolatilityAlphaModel())

        self.strategies_registry = None
        if hasattr(self.config, "strategies_registry") and self.config.strategies_registry:
            self.strategies_registry = self.config.strategies_registry

        trading_config = getattr(self.config, "trading", self.config)
        self._tca_prefs = getattr(trading_config, "tca_prefs", {})
        self._risk_budgets = getattr(trading_config, "risk_budgets", {})

        _res = DomainConfigResolver(self.config)
        dm_cfg = _res.get_decision_making()
        qos_cfg = dm_cfg.qos

        self._fail_closed_on_degraded_context = bool(
            getattr(dm_cfg, "fail_closed_on_degraded_context", False))
        try:
            _raw = list(
                getattr(dm_cfg, "degraded_context_critical_keys", []) or [])
        except Exception:
            _raw = []
        self._degraded_context_critical_keys: set = set(
            str(k) for k in _raw if str(k))
        try:
            _by_s = getattr(
                dm_cfg, "degraded_context_critical_keys_by_strategy", {}) or {}
        except Exception:
            _by_s = {}
        self._degraded_context_critical_keys_by_strategy: dict = {
            str(sid): set(str(k) for k in (keys or []) if str(k))
            for sid, keys in (_by_s.items() if isinstance(_by_s, dict) else [])
        }
        try:
            _contracts = getattr(
                dm_cfg, "degraded_context_contracts_by_strategy", {}) or {}
        except Exception:
            _contracts = {}
        self._degraded_context_contracts_by_strategy: dict = {}
        if isinstance(_contracts, dict):
            for sid, contract in _contracts.items():
                enabled = bool(getattr(contract, "enabled", False))
                keys_raw = list(getattr(contract, "critical_keys", []) or [])
                self._degraded_context_contracts_by_strategy[str(sid)] = {
                    "enabled": enabled,
                    "critical_keys": set(str(k) for k in keys_raw if str(k)),
                }

        sizing_cfg = dm_cfg.position_sizing
        self.min_pos_size_usd = decimal.Decimal(
            str(sizing_cfg.min_position_size_usd))
        self.liq_cap_usd = decimal.Decimal(
            str(sizing_cfg.liquidity_based_cap_usd))
        self.qos_exposure_block_cooldown_sec = int(
            qos_cfg.exposure_block_cooldown_sec)
        self.qos_max_intents_per_minute_per_symbol = int(
            qos_cfg.max_intents_per_minute_per_symbol)
        self.qos_mode = str(qos_cfg.mode)
        self._default_symbol_cooldown_sec = int(qos_cfg.symbol_cooldown_sec)
        self.qos_enforce = bool(qos_cfg.enforce)
        try:
            _apply_to = list(getattr(qos_cfg, "apply_to_strategies", []) or [])
        except Exception:
            _apply_to = []
        self._qos_apply_to_strategies: set = set(
            str(s) for s in _apply_to if str(s))

        self.arming_require_regime_warmup = dm_cfg.arming.require_regime_warmup
        self.arming_retry_backoff_ms = dm_cfg.arming.retry_backoff_ms
        self.arming_max_attempts = dm_cfg.arming.max_attempts
        self.features_ttl_sec = dm_cfg.features.ttl_sec
        self.flip_global_enabled = dm_cfg.flip.enabled
        self.dlog = DecisionLog()
        self._bar_gating_enabled = dm_cfg.bar_gating.enable
        self._bar_ms = int(dm_cfg.bar_gating.bar_ms)
        self._last_bar_index: dict = {}
        self._behavior_enabled = dm_cfg.behavior_fsm.enable
        self._behavior_state: Dict[str, str] = {}

        # normalize_signals_mode is mirrored here for intent/WAL observability.
        # The signed_v2 fallback only protects partial mocks and degraded test
        # fixtures; it is not meant to broaden the production config contract.
        try:
            _aurora = getattr(
                getattr(self.config, "strategies", None), "aurora", None)
            _decision = getattr(_aurora, "decision", None) if _aurora else None
            _signals = getattr(_decision, "signals",
                               None) if _decision else None
            self.normalize_signals_mode = str(
                _signals.normalize_signals_mode) if _signals is not None else "signed_v2"
        except Exception:
            self.normalize_signals_mode = "signed_v2"

        # Delegate composition happens once here; the wrapper methods below keep
        # the historical DecisionMaking method surface stable.
        self._cfg = DMConfigResolver(
            self.config, self.strategies_registry, self._arb_signal_buffer,
            self._arb_window_winner, self.flip_global_enabled, self.logger)

        self._qos = QoSRateControl(
            self._clock, self._qos_state, self._qos_apply_to_strategies,
            self.qos_exposure_block_cooldown_sec, self.qos_max_intents_per_minute_per_symbol,
            self._cfg.get_symbol_cooldown, self.logger)
        self._pos = PositionQueries(
            self.config, lambda: self.latest_portfolio,
            self.min_pos_size_usd, self.liq_cap_usd, self.logger)
        self._readiness = ReadinessGates(
            self._clock, self.config, self.features_ttl_sec,
            self.symbol_states, self._per_symbol_regimes,
            lambda: self.latest_portfolio,
            lambda: (self._exposure_cache, self._exposure_cache_timestamp),
            self._emit_intent_deferred_v1, self._record_blocked_intent,
            self._fail_closed_on_degraded_context, self._degraded_context_critical_keys,
            self._degraded_context_critical_keys_by_strategy, self.logger,
            degraded_context_contracts_by_strategy=self._degraded_context_contracts_by_strategy)
        self._emitter = IntentEmitter(
            self.fsm, self._clock, self.config, self.alert_manager,
            lambda: self.latest_portfolio,
            lambda **kw: self._propose_trade_intent(**kw),
            self.logger,
            emit_reduce_only_close_fn=lambda **kw: self._emit_reduce_only_close(
                **kw),
            registry_lookup_fn=self._get_registry_owners_for_symbol,
        )
        self._flip = FlipOrchestrator(
            self._clock, self.config, self.fsm,
            self._get_position_state, self._get_portfolio_position_qty_signed,
            lambda sym: self._get_flip_config(
                sym), lambda **kw: self._propose_trade_intent(**kw),
            self._emit_intent_deferred_v1, self.logger)
        self._builder = IntentBuilder(
            fsm=self.fsm, clock=self._clock, config=self.config,
            tca_prefs=self._tca_prefs, risk_budgets=self._risk_budgets,
            safe_decimal_fn=self._safe_decimal,
            check_strategy_arbitration_fn=self._check_strategy_arbitration,
            warmup_gate_fn=self._warmup_gate_before_trade_intent,
            emit_rejected_fn=self._emit_trade_intent_rejected,
            record_blocked_fn=self._record_blocked_intent,
            record_accepted_fn=self._record_accepted_intent,
            emit_deferred_fn=self._emit_intent_deferred_v1,
            get_side_bias_params_fn=self._get_side_bias_params,
            side_intent_window=self._side_intent_window, logger=self.logger)
        self._evt = DMEventHandlers(
            fsm=self.fsm, clock=self._clock, config=self.config,
            symbol_states=self.symbol_states, per_symbol_regimes=self._per_symbol_regimes,
            shared_state=self._shared, dlog=self.dlog, alpha_registry=self.alpha_registry,
            handle_regime_flip_fn=self._handle_regime_flip,
            record_blocked_fn=self._record_blocked_intent,
            arming_require_regime_warmup=self.arming_require_regime_warmup,
            behavior_enabled=self._behavior_enabled, behavior_state=self._behavior_state,
            logger=self.logger)
        self._gateway = StrategyGateway(self)

        # Listener registration stays in the facade so bootstrap does not need
        # to know which delegate currently owns a specific event path.
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)
        self.fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED",
                        self.update_exposure_cache)
        self.fsm.listen("EVT:STRATEGY_SIGNAL_PRODUCED",
                        self._on_strategy_signal_gateway)
        # Phase 0.5: system stress overlay state updates
        self.fsm.listen("EVT:SYSTEM_STRESS_STATE_UPDATED",
                        self._on_system_stress)
        self._domain_bridge = DomainBridge("decision_making", bus=self.fsm)
        self._domain_bridge.register_health_fn(self.is_healthy)
        self._last_status_ts = 0.0

    def _safe_decimal(self, value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value if value.is_finite() else default
        try:
            d = Decimal(str(value))
        except (decimal.InvalidOperation, TypeError, ValueError):
            return default
        return d if d.is_finite() else default

    @property
    def strategies_registry(self) -> Any:
        return getattr(self, "_strategies_registry", None)

    @strategies_registry.setter
    def strategies_registry(self, value: Any) -> None:
        self._strategies_registry = value
        cfg = getattr(self, "_cfg", None)
        if cfg is not None:
            cfg.strategies_registry = value

    @property
    def latest_portfolio(self) -> Any:
        s = getattr(self, "_shared", None)
        return s.get("latest_portfolio") if isinstance(s, dict) else None

    @latest_portfolio.setter
    def latest_portfolio(self, value: Any) -> None:
        if not isinstance(getattr(self, "_shared", None), dict):
            self._shared = {}
        self._shared["latest_portfolio"] = value

    @property
    def latest_regime(self) -> Any:
        s = getattr(self, "_shared", None)
        return s.get("latest_regime") if isinstance(s, dict) else None

    @property
    def _cached_equity_free_usdt(self) -> Any:
        s = getattr(self, "_shared", None)
        return s.get("cached_equity_free_usdt") if isinstance(s, dict) else None

    @property
    def _cached_equity_cross_usdt(self) -> Any:
        s = getattr(self, "_shared", None)
        return s.get("cached_equity_cross_usdt") if isinstance(s, dict) else None

    @property
    def _exposure_cache(self) -> Any:
        s = getattr(self, "_shared", None)
        return s.get("exposure_cache") if isinstance(s, dict) else None

    @_exposure_cache.setter
    def _exposure_cache(self, value: Any) -> None:
        if not isinstance(getattr(self, "_shared", None), dict):
            self._shared = {}
        self._shared["exposure_cache"] = value

    @property
    def _exposure_cache_timestamp(self) -> float:
        s = getattr(self, "_shared", None)
        return s.get("exposure_cache_timestamp", 0.0) if isinstance(s, dict) else 0.0

    @_exposure_cache_timestamp.setter
    def _exposure_cache_timestamp(self, value: Any) -> None:
        if not isinstance(getattr(self, "_shared", None), dict):
            self._shared = {}
        self._shared["exposure_cache_timestamp"] = float(
            value if value is not None else 0.0)

    def _on_strategy_signal_gateway(self, event: Message) -> None:
        self._gateway.process_signal(event)

    def _propose_trade_intent(
        self, symbol, side, qty, price, why_chain, rid,
        reduce_only=False, strategy_id="aurora", decision_ts_ms=None,
        stop_price=None, target_price=None, entry_plan_trace=None,
        tf_sec=None, max_slippage_bps=None, max_latency_ms=None, risk_score=None,
        tpsl_owner_ctx=None,
        strategy_trace=None,
    ):
        """Run safety-gate glue and forward allowed intents to IntentBuilder.

        This is one of the few non-trivial facade methods left in this module:
        it normalizes the safety-gate contract, emits rejection side effects for
        deny/config-error outcomes, and only then hands control to the builder.
        """
        system_stress_states = self._system_stress_states if hasattr(
            self, "_system_stress_states") else {}
        # Safety gates run before the builder so denied or misconfigured intents
        # never reach the downstream emission/arbitration pipeline.
        sg = apply_safety_gates(
            symbol=symbol, side=side, reduce_only=reduce_only, strategy_id=strategy_id,
            decision_ts_ms=decision_ts_ms, why_chain=why_chain, config=self.config,
            clock=self._clock, symbol_states=self.symbol_states,
            per_symbol_regimes=self._per_symbol_regimes,
            system_stress_states=system_stress_states)
        if sg.outcome == "CONFIG_ERROR":
            self._emit_trade_intent_rejected(
                symbol=symbol, strategy_id=str(strategy_id), side=str(side), rid=str(rid),
                reason_code=NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING,
                reason="DECISION", context=sg.config_error_context or "safety_gates config error",
                why_chain=why_chain)
            self._record_blocked_intent(symbol)
            return
        if sg.outcome == "DENY":
            self._handle_safety_deny(
                symbol,
                side,
                rid,
                why_chain,
                sg,
                strategy_id=strategy_id,
            )
            return
        # After this point the builder owns payload assembly, arbitration, QoS,
        # and intent emission side effects.
        self._builder.build_and_emit(
            symbol=symbol, side=side, qty=qty,
            price=price, why_chain=why_chain, rid=rid,
            reduce_only=reduce_only, strategy_id=strategy_id, decision_ts_ms=decision_ts_ms,
            stop_price=stop_price, target_price=target_price, entry_plan_trace=entry_plan_trace,
            tf_sec=tf_sec, max_slippage_bps=max_slippage_bps,
            max_latency_ms=max_latency_ms, risk_score=risk_score,
            tpsl_owner_ctx=tpsl_owner_ctx,
            strategy_trace=strategy_trace,
            normalize_mode=self.normalize_signals_mode, sg=sg)

    def _handle_safety_deny(self, symbol, side, rid, why_chain, sg, *, strategy_id: str) -> None:
        """Emit best-effort observability for a safety-gate denial."""
        def _g(a, d=None): return getattr(sg, a, d)  # noqa: E731
        trace = {
            "symbol": symbol, "ts": _g("trace_ts_ms"), "intent_side": _g("intent_side"),
            "signal_score": _g("signal_score"), "regime": _g("regime"),
            "regime_confidence": _g("regime_confidence"), "trend_dir": _g("trend_dir"),
            "trend_run_length": _g("trend_run_length"), "delta_price": _g("delta_price"), "pm_norm_10s": _g("pm_norm_10s"),
            "pm_norm_60s": _g("pm_norm_60s"), "pm_norm_300s": _g("pm_norm_300s"),
            "vol_pct_10s": _g("vol_pct_10s"), "vol_pct_60s": _g("vol_pct_60s"),
            "vol_pct_300s": _g("vol_pct_300s"),
            "gate_outcome": "DENY", "deny_reason": sg.deny_reason,
            "why": (str(_g("why_short", ""))[:80]),
        }
        if isinstance(_g("regime_provenance"), dict):
            trace["regime_provenance"] = _g("regime_provenance")
        # Observability is best-effort here: a failed trace emit must not turn a
        # denied decision into a runtime exception.
        try:
            self.fsm.emit("EVT:DECISION_TRACE_EMITTED", payload=trace,
                          why="decision_trace", data_ref=why_chain)
        except Exception:
            self.logger.debug(
                "EVT:DECISION_TRACE_EMITTED emit failed", exc_info=True)
        side_u = str(side).upper() if str(
            side).upper() in ("BUY", "SELL") else "NONE"
        # Mirror the denial into an explicitly decision-local journal row so it
        # does not masquerade as canonical execution/runtime ORDER_REJECTED.
        try:
            order_logger.write({
                "rid": rid, "event_type": "DECISION_INTENT_REJECTED", "symbol": symbol, "side": side_u,
                "origin_class": "decision_alias",
                "nrr_code": str(sg.deny_reason) if sg.deny_reason else None,
                "regime": _g("regime"),
                "regime_confidence": _g("regime_confidence"),
                "regime_provenance": _g("regime_provenance") if isinstance(_g("regime_provenance"), dict) else None,
                "why": f"SAFETY_GATES:{_g('why_short', '')}", "source_fsm": "DecisionMaking",
                "metadata": {
                    "reject_reason": "SAFETY_GATES_DENY",
                    "deny_reason": sg.deny_reason,
                    "canonical_event_family": "TRADE_INTENT_REJECTED",
                    "alias_of": "TRADE_INTENT_REJECTED",
                    "min_regime_confidence": _g("min_regime_confidence"),
                    "threshold_applied": _g("threshold_applied"),
                    "threshold_verdict": _g("threshold_verdict"),
                    "threshold_reason": _g("threshold_reason"),
                },
            })
        except Exception:
            self.logger.debug(
                "order_logger.write failed in _handle_safety_deny", exc_info=True)
        try:
            emit_regime_decision_audit(
                logger=self.logger,
                symbol=str(symbol),
                rid=str(rid),
                lifecycle_id=None,
                strategy_id=str(strategy_id),
                sg=sg,
                outcome="DENY",
            )
        except Exception:
            self.logger.debug(
                "REGIME_AUDIT decision emit failed in _handle_safety_deny",
                exc_info=True,
            )
        self._record_blocked_intent(symbol)

    def _get_risk_skew_config(self, key: str) -> Any:
        """Fail-closed accessor for risk_skew config (used by tests + strategy_gateway)."""
        try:
            value = getattr(self.config.domains.decision_making.risk_skew, key)
        except AttributeError:
            value = None
        if value is None:
            raise ValueError(
                f"risk_skew.{key} is required but not set in config (fail-closed)")
        return value

    # -- Config stubs ----------------------------------------------------------
    # These proxies intentionally preserve the legacy DecisionMaking surface
    # while the concrete logic lives in the composed helpers above.
    def _get_position_sizing_config(
        self): return self._cfg.get_position_sizing_config()

    def _is_strategy_assigned(
        self, symbol, strategy_id): return self._cfg.is_strategy_assigned(symbol, strategy_id)

    def _get_aurora_instrument_cfg(
        self, symbol): return self._cfg.get_aurora_instrument_cfg(symbol)

    def _get_symbol_cooldown(
        self, symbol, strategy_id="aurora"): return self._cfg.get_symbol_cooldown(symbol, strategy_id)

    def _get_param(self, symbol, param, default): return self._cfg.get_param(
        symbol, param, default)

    def _get_side_bias_params(
        self, symbol): return self._cfg.get_side_bias_params(symbol)

    def _get_regime_thresholds(
        self, symbol): return self._cfg.get_regime_thresholds(symbol)

    def _get_signal_threshold(
        self, symbol): return self._cfg.get_signal_threshold(symbol)

    def _get_flip_config(self, symbol):
        """Resolve effective flip config from global gate plus per-symbol SSOT.

        Global disabled -> return a deterministic disabled tuple.
        Global enabled -> per-symbol instruments.<SYM>.flip is mandatory.
        """
        if not self.flip_global_enabled:
            return (False, 1.0)
        instr = self.config.instruments.get(symbol)
        if not instr:
            raise ConfigContractError(
                path=f"instruments.{symbol}", why=f"Missing instruments config for active symbol {symbol}")
        if not instr.flip:
            raise ConfigContractError(
                path=f"instruments.{symbol}.flip", why=f"Missing REQUIRED flip config for symbol {symbol}. Add flip.enabled + flip.hysteresis_mult.")
        return (bool(instr.flip.enabled), max(1.0, float(instr.flip.hysteresis_mult)))

    def _get_precision(self, symbol): return self._cfg.get_precision(symbol)

    def _check_strategy_arbitration(self, symbol, strategy_id, *, ts_ms=None, commit=False):
        return self._cfg.check_strategy_arbitration(symbol, strategy_id, ts_ms=ts_ms, commit=commit)

    # -- QoS stubs -------------------------------------------------------------
    def _qos_enabled_for_strategy(
        self, strategy_id): return self._qos.qos_enabled_for_strategy(strategy_id)

    def _qos_allow(self, symbol, strategy_id="aurora", is_exposure_block=False): return self._qos.qos_allow(
        symbol, strategy_id, is_exposure_block)

    def _update_symbol_cooldown(
        self, symbol, strategy_id="aurora"): self._qos.update_symbol_cooldown(symbol, strategy_id)

    def _update_intent_count(
        self, symbol, strategy_id="aurora"): self._qos.update_intent_count(symbol, strategy_id)

    def _calculate_next_allowed_time(
        self, symbol, strategy_id="aurora"): return self._qos.calculate_next_allowed_time(symbol, strategy_id)

    def _update_qos_state(
        self, symbol, strategy_id="aurora"): self._qos.update_qos_state(symbol, strategy_id)

    def _handle_exposure_block(
        self, symbol): self._qos.handle_exposure_block(symbol)

    # -- Position stubs --------------------------------------------------------
    def _get_position_state(
        self, symbol): return self._pos.get_position_state(symbol)

    def _get_portfolio_position_qty_signed(
        self, symbol): return self._pos.get_portfolio_position_qty_signed(symbol)

    def _check_symbol_is_flat(
        self, symbol): return self._pos.check_symbol_is_flat(symbol)

    def _calculate_position_size(self, symbol, price, side, context, *, margin_pct_mult=None):
        return self._pos.calculate_position_size(symbol, price, side, context, margin_pct_mult=margin_pct_mult)

    # -- Event handler stubs ---------------------------------------------------
    def on_features(self, event): self._evt.on_features(event)
    def on_risk(self, event): self._evt.on_risk(event)
    def on_portfolio(self, event): self._evt.on_portfolio(event)
    def on_regime(self, event): self._evt.on_regime(event)

    def update_exposure_cache(
        self, event): self._evt.update_exposure_cache(event)

    def _on_system_stress(self, event: "Message") -> None:
        """Phase 0.5: cache latest system stress state per symbol."""
        try:
            pld = event.pld if isinstance(event.pld, dict) else {}
            symbol = pld.get("symbol")
            state = pld.get("state")
            if symbol and state in ("NORMAL", "STRESS", "EXTREME"):
                self._system_stress_states[symbol] = state
                self.logger.debug(
                    f"[{symbol}] SystemStress state cached: {state}")
        except Exception:
            self.logger.warning(
                "_on_system_stress: unexpected error", exc_info=True)

    # -- Readiness stubs -------------------------------------------------------
    def _features_ready(self, symbol, features_data): return self._readiness.features_ready(
        symbol, features_data)

    def _warmup_not_ready(self, symbol, reason, *,
                          details=None): self._readiness.warmup_not_ready(symbol, reason, details=details)

    def _precheck_exposure_cache(
        self, symbol, side, notional_usd): return self._readiness.precheck_exposure_cache(symbol, side, notional_usd)

    def _warmup_gate_before_trade_intent(self, *, symbol, rid, reduce_only, context):
        return self._readiness.warmup_gate_before_trade_intent(symbol=symbol, rid=rid, reduce_only=reduce_only, context=context)

    def _degraded_context_gate_should_defer(self, *, symbol, rid, ctx, features_evt, strategy_id=None):
        return self._readiness.degraded_context_gate_should_defer(symbol=symbol, rid=rid, ctx=ctx, features_evt=features_evt, strategy_id=strategy_id)

    # -- Emitter stubs ---------------------------------------------------------
    def _emit_trade_intent_rejected(
        self, **kw): self._emitter.emit_trade_intent_rejected(**kw)

    def _emit_intent_deferred_v1(
        self, **kw): self._emitter.emit_intent_deferred_v1(**kw)

    def _schedule_open_retry(self, symbol, original_context, cooldown_ms, reason): self._emitter.schedule_open_retry(
        symbol, original_context, cooldown_ms, reason)

    def _record_blocked_intent(
        self, symbol): self._emitter.record_blocked_intent(symbol)

    def _record_accepted_intent(
        self, symbol): self._emitter.record_accepted_intent(symbol)

    def _check_and_emit_risk_gate_alert(
        self): self._emitter.check_and_emit_risk_gate_alert()

    def _handle_regime_flip(
        self, symbol, regime_data): self._emitter.handle_regime_flip(symbol, regime_data)

    # -- Flip stubs ------------------------------------------------------------
    def _is_flip(self, symbol, intent_side, position_state=None): return self._flip.is_flip(
        symbol, intent_side, position_state)

    def _is_same_side_position(self, position_side, intent_side): return self._flip.is_same_side_position(
        position_side, intent_side)

    def _generate_flip_retry_key(
        self, symbol, side, seed=None): return self._flip.generate_flip_retry_key(symbol, side, seed)

    def _handle_flip_orchestration(self, symbol, intent_side, original_pld, source="aurora"):
        return self._flip.handle_flip_orchestration(symbol, intent_side, original_pld, source)

    def _emit_reduce_only_close(self, symbol, reason, rid, *, strategy_id, strategy_trace=None):
        return self._flip.emit_reduce_only_close(
            symbol,
            reason,
            rid,
            strategy_id=strategy_id,
            strategy_trace=strategy_trace,
        )

    def _resolve_position_mode(
        self, *, symbol, source): return self._flip.resolve_position_mode(symbol=symbol, source=source)

    def _initiate_flip_close(self, symbol, intent_side, original_pld, source):
        return self._flip.initiate_flip_close(symbol, intent_side, original_pld, source)

    def _get_registry_owners_for_symbol(self, symbol: str) -> list:
        """Return strategy_ids assigned to symbol in strategies_registry.

        Used by IntentEmitter.resolve_strategy_id_for_close for regime-flip closes.
        Returns empty list if no registry.
        """
        reg = self.strategies_registry
        if reg is None:
            return []
        assignments = getattr(reg, "assignments", {})
        return list(assignments.get(symbol, []))

    # -- Lifecycle -------------------------------------------------------------
    def clear_internal_state_for_symbol(self, symbol: str) -> None:
        """Compatibility no-op; current per-symbol caches are delegate-managed."""
        pass  # Per-symbol caches are TTL-managed

    def start(self) -> None:
        self.logger.info("DecisionMaking started")

    def stop(self) -> None:
        self.logger.info("DecisionMaking stopped")

    def is_healthy(self) -> bool:
        if self.alert_manager and hasattr(self.alert_manager, "is_healthy"):
            if not self.alert_manager.is_healthy():
                return False
        return True

    def handle_tick(self) -> None:
        """Emit periodic domain status without owning market-tick processing."""
        now = self._clock.now_sec()
        if now - self._last_status_ts >= 60:
            self._domain_bridge.emit_status()
            self._last_status_ts = now


# Backward-compat alias kept for legacy imports/tests.
DecisionMakingLogic = DecisionMaking
