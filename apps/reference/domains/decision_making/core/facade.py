"""DecisionMaking domain facade and compatibility surface.

Phase 14A moved most decision logic into focused helpers, but this module still
owns delegate construction, shared mutable state, event subscriptions, and a
small set of glue paths that preserve legacy imports and method names.
"""

import decimal
import logging
from collections.abc import Mapping
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
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
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.decision_making.core.config_resolver import DMConfigResolver
from apps.reference.domains.decision_making.gates.qos_rate_control import QoSRateControl
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries
from apps.reference.domains.decision_making.gates.readiness_gates import ReadinessGates
from apps.reference.domains.decision_making.intent.emitter import IntentEmitter
from apps.reference.domains.decision_making.intent.flip import FlipOrchestrator
from apps.reference.domains.decision_making.intent.payload_assembler import build_decision_trace_payload
from apps.reference.domains.decision_making.gates.low_vol_cost_floor import evaluate_low_vol_cost_floor_gate
from apps.reference.domains.decision_making.gates.safety_gates import apply_safety_gates
from apps.reference.domains.decision_making.intent.builder import IntentBuilder
from apps.reference.domains.decision_making.core.config_spec import DMConfigSpec
from apps.reference.domains.decision_making.core.state import DMState
from apps.reference.domains.decision_making.core.event_handlers import DMEventHandlers
from apps.reference.domains.decision_making.observability.log_adapter import DecisionLog
from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from apps.reference.domains.decision_making.gates.regime_loss_embargo import RegimeLossEmbargo
from apps.reference.domains.neocortex.config_models import load_config as load_neocortex_config
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
    coerce_causal_time_provenance,
    is_causal_time_provenance,
)
from apps.reference.domains.neocortex.transport.authority_bridge import NeocortexAuthorityBridge

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


_CAUSAL_PROVENANCE_KEYS = (
    "event_time_source",
    "event_time_provenance",
    "time_provenance",
    "feature_time_provenance",
)
_CAUSAL_TIMESTAMP_KEYS = (
    "event_ts_ms",
    "timestamp_ms",
    "timestamp",
    "ts_ms",
    "ts",
)


def _first_mapping_value(
    *mappings: object,
    aliases: tuple[str, ...],
) -> object | None:
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        for alias in aliases:
            if alias not in mapping:
                continue
            value = mapping.get(alias)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def _coerce_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if numeric < 1:
        return None
    return numeric


def _build_snapshot_causal_time_fields(
    feature_state: Mapping[str, Any],
    *,
    decision_basis_ts_ms: object,
) -> dict[str, Any]:
    payload = feature_state.get("payload") if isinstance(
        feature_state.get("payload"), Mapping) else None
    provenance_raw = _first_mapping_value(
        feature_state,
        payload,
        aliases=_CAUSAL_PROVENANCE_KEYS,
    )
    provenance = coerce_causal_time_provenance(provenance_raw)
    explicit_event_ts_ms = _coerce_positive_int(
        _first_mapping_value(
            feature_state,
            payload,
            aliases=_CAUSAL_TIMESTAMP_KEYS,
        )
    )
    explicit_decision_basis_ts_ms = _coerce_positive_int(decision_basis_ts_ms)
    causal_timestamp_present = (
        explicit_event_ts_ms is not None or explicit_decision_basis_ts_ms is not None
    )
    causal_supported = bool(
        provenance_raw is not None
        and is_causal_time_provenance(provenance)
        and causal_timestamp_present
    )

    fields: dict[str, Any] = {
        "event_time_source": (
            provenance.value
            if provenance_raw is not None
            else CausalTimeProvenance.UNKNOWN.value
        ),
        "event_time_is_causal": causal_supported,
        "trainable": causal_supported,
        "dataset_visibility": (
            "trainable" if causal_supported else "diagnostics_only"
        ),
    }
    if provenance_raw is not None:
        fields["feature_time_provenance"] = provenance.value
    if explicit_event_ts_ms is not None:
        fields["event_ts_ms"] = explicit_event_ts_ms
    if explicit_decision_basis_ts_ms is not None:
        fields["decision_basis_ts_ms"] = explicit_decision_basis_ts_ms
    return fields


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
        state = DMState.new(self._clock)
        self.symbol_states = state.symbol_states
        self._shared = state.shared_state
        self._per_symbol_regimes = state.per_symbol_regimes
        self._system_stress_states = state.system_stress_states
        self._side_intent_window = state.side_intent_window
        self._pending_flips = state.pending_flips
        self._arb_window_winner = state.arb_window_winner
        self._arb_signal_buffer = state.arb_signal_buffer
        self._qos_state = state.qos_state
        self._qos_next_allowed_ts = state.qos_next_allowed_ts
        self.intents_seen_total = state.intents_seen_total
        self.intents_blocked_total = state.intents_blocked_total
        self.last_alert_check_time = state.last_alert_check_time
        self._last_bar_index = state.last_bar_index
        self._behavior_state = state.behavior_state

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

        constructor_dm_cfg = DomainConfigResolver(
            self.config).get_decision_making()
        config_spec = DMConfigSpec.load(self.config, dm_cfg=constructor_dm_cfg)
        self.strategies_registry = config_spec.strategies_registry
        self._tca_prefs = config_spec.tca_prefs
        self._risk_budgets = config_spec.risk_budgets
        self._fail_closed_on_degraded_context = config_spec.fail_closed_on_degraded_context
        self._degraded_context_critical_keys = config_spec.degraded_context_critical_keys
        self._degraded_context_critical_keys_by_strategy = config_spec.degraded_context_critical_keys_by_strategy
        self._degraded_context_contracts_by_strategy = config_spec.degraded_context_contracts_by_strategy
        self.min_pos_size_usd = config_spec.min_pos_size_usd
        self.liq_cap_usd = config_spec.liq_cap_usd
        self.qos_exposure_block_cooldown_sec = config_spec.qos_exposure_block_cooldown_sec
        self.qos_max_intents_per_minute_per_symbol = config_spec.qos_max_intents_per_minute_per_symbol
        self.qos_mode = config_spec.qos_mode
        self._default_symbol_cooldown_sec = config_spec.default_symbol_cooldown_sec
        self.qos_enforce = config_spec.qos_enforce
        self._qos_apply_to_strategies = config_spec.qos_apply_to_strategies
        self.arming_require_regime_warmup = config_spec.arming_require_regime_warmup
        self.arming_retry_backoff_ms = config_spec.arming_retry_backoff_ms
        self.arming_max_attempts = config_spec.arming_max_attempts
        self.features_ttl_sec = config_spec.features_ttl_sec
        self.flip_global_enabled = config_spec.flip_global_enabled
        self.dlog = DecisionLog()
        self._bar_gating_enabled = config_spec.bar_gating_enabled
        self._bar_ms = config_spec.bar_ms
        self._behavior_enabled = config_spec.behavior_enabled
        self.normalize_signals_mode = config_spec.normalize_signals_mode

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
        self._regime_loss_embargo = RegimeLossEmbargo(
            config=self.config,
            symbol_states=self.symbol_states,
            clock=self._clock,
            logger=self.logger,
        )
        shadow_cfg = getattr(
            getattr(self.config, "domains", None), "shadow_telemetry", None)
        shadow_enabled = bool(getattr(shadow_cfg, "enabled", False))
        neocortex_config_dir = Path(__file__).resolve(
        ).parents[2] / "neocortex" / "config"
        self._neocortex_config = None
        neocortex_config_error: Exception | None = None
        try:
            self._neocortex_config = load_neocortex_config(
                neocortex_config_dir)
        except Exception as exc:
            neocortex_config_error = exc
            self.logger.warning(
                "Neocortex Phase 5 config load failed; authority seam will fail closed",
                exc_info=exc,
            )
        self._neocortex_authority_bridge = NeocortexAuthorityBridge(
            config=self._neocortex_config,
            config_error=neocortex_config_error,
            shadow_emit_fn=(
                self._emit_shadow_neocortex_decision_logged if shadow_enabled else None),
            logger=self.logger.getChild("neocortex_authority_phase5"),
        )
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
            authority_bridge=None,
            shadow_emit_fn=(
                self._emit_shadow_neocortex_decision_logged if shadow_enabled else None),
            causal_state_snapshot_fn=(
                self._build_shadow_causal_state_snapshot if shadow_enabled else None),
            get_regime_epoch_ref_fn=self._regime_loss_embargo.get_current_epoch_ref,
            side_intent_window=self._side_intent_window, logger=self.logger)
        self._evt = DMEventHandlers(
            fsm=self.fsm, clock=self._clock, config=self.config,
            symbol_states=self.symbol_states, per_symbol_regimes=self._per_symbol_regimes,
            shared_state=self._shared, dlog=self.dlog, alpha_registry=self.alpha_registry,
            handle_regime_flip_fn=self._handle_regime_flip,
            regime_loss_embargo=self._regime_loss_embargo,
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
        self.fsm.listen("EVT:POSITION_CLOSED", self.on_position_closed)
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

    def _build_prior_gate_low_vol_cost_floor_details(
        self,
        *,
        symbol: str,
        side: str,
        price: Any,
        target_price: Any,
        stop_price: Any,
        strategy_id: str,
        sg: Any,
    ) -> dict[str, Any] | None:
        if getattr(sg, "low_vol_cost_floor_details", None) is not None:
            return None
        if str(getattr(sg, "regime", "") or "") != "LOW_VOLATILITY":
            return None

        entry_decimal = self._safe_decimal(price)
        target_decimal = self._safe_decimal(target_price)
        stop_decimal = self._safe_decimal(stop_price)
        side_u = str(side).upper()

        actual_tp_bps: Decimal | None = None
        actual_sl_bps: Decimal | None = None
        geometry_available = (
            entry_decimal is not None
            and target_decimal is not None
            and stop_decimal is not None
            and entry_decimal > 0
        )
        if geometry_available:
            scale = Decimal("10000")
            if side_u == "BUY":
                actual_tp_bps = (target_decimal - entry_decimal) / \
                    entry_decimal * scale
                actual_sl_bps = (entry_decimal - stop_decimal) / \
                    entry_decimal * scale
            elif side_u == "SELL":
                actual_tp_bps = (entry_decimal - target_decimal) / \
                    entry_decimal * scale
                actual_sl_bps = (stop_decimal - entry_decimal) / \
                    entry_decimal * scale
            else:
                geometry_available = False

        return {
            "evaluation_stage": "prior_safety_gate",
            "evaluated": False,
            "geometry_available": geometry_available,
            "geometry_source": "facade_inputs",
            "entry_price": self._to_float(entry_decimal),
            "target_price": self._to_float(target_decimal),
            "stop_price": self._to_float(stop_decimal),
            "actual_tp_bps": self._to_float(actual_tp_bps),
            "actual_sl_bps": self._to_float(actual_sl_bps),
            "side": side_u if side_u in ("BUY", "SELL") else None,
            "regime": getattr(sg, "regime", None),
            "regime_confidence": getattr(sg, "regime_confidence", None),
            "strategy_id": str(strategy_id) if strategy_id is not None else None,
            "symbol": str(symbol).upper() if symbol is not None else None,
        }

    def _enrich_low_vol_cost_floor_details(
        self,
        *,
        details: Mapping[str, Any],
        sg: Any,
        rid: str,
        decision_ts_ms: Any,
        decision_outcome: str,
    ) -> dict[str, Any]:
        enriched = dict(details)

        trace_ts_ms: int | None = None
        for candidate in (decision_ts_ms, getattr(sg, "trace_ts_ms", None)):
            if candidate is None:
                continue
            try:
                trace_ts_ms = int(candidate)
            except (TypeError, ValueError):
                trace_ts_ms = None
            else:
                break

        order_logger_event = (
            "ORDER_INTENT" if decision_outcome == "ALLOW" else "DECISION_INTENT_REJECTED"
        )
        persistence_context = enriched.get("persistence_context")
        if not isinstance(persistence_context, dict):
            persistence_context = {}
        persistence_context = dict(persistence_context)
        persistence_context.update(
            {
                "rid": str(rid),
                "decision_ts_ms": trace_ts_ms,
                "trace_ts_ms": trace_ts_ms,
                "decision_outcome": decision_outcome,
                "decision_trace_event": "EVT:DECISION_TRACE_EMITTED",
                "order_logger_event": order_logger_event,
                "persisted_in": ["EVT:DECISION_TRACE_EMITTED", order_logger_event],
            }
        )
        enriched["persistence_context"] = persistence_context

        score_context = enriched.get("score_context")
        if isinstance(score_context, dict):
            score_context = dict(score_context)
            score_missing = score_context.get("missing")
            if not isinstance(score_missing, dict):
                score_missing = {}
            else:
                score_missing = dict(score_missing)
            if score_context.get("signal_score") is None and getattr(sg, "signal_score", None) is not None:
                score_context["signal_score"] = getattr(
                    sg, "signal_score", None)
            score_missing["signal_score"] = score_context.get(
                "signal_score") is None
            score_context["missing"] = score_missing
            enriched["score_context"] = score_context

        price_motion_context = enriched.get("price_motion_context")
        if not isinstance(price_motion_context, dict):
            price_motion_context = {}
        else:
            price_motion_context = dict(price_motion_context)
        price_motion_missing = price_motion_context.get("missing")
        if not isinstance(price_motion_missing, dict):
            price_motion_missing = {}
        else:
            price_motion_missing = dict(price_motion_missing)
        for key in (
            "pm_norm_10s",
            "pm_norm_60s",
            "pm_norm_300s",
            "vol_pct_10s",
            "vol_pct_60s",
            "vol_pct_300s",
        ):
            if price_motion_context.get(key) is None and getattr(sg, key, None) is not None:
                price_motion_context[key] = getattr(sg, key, None)
            price_motion_missing[key] = price_motion_context.get(key) is None
        if price_motion_context or price_motion_missing:
            price_motion_context["missing"] = price_motion_missing
            enriched["price_motion_context"] = price_motion_context

        missing_inputs = enriched.get("missing_inputs")
        if not isinstance(missing_inputs, dict):
            missing_inputs = {}
        else:
            missing_inputs = dict(missing_inputs)
        for key in (
            "pm_norm_10s",
            "pm_norm_60s",
            "pm_norm_300s",
            "vol_pct_10s",
            "vol_pct_60s",
            "vol_pct_300s",
        ):
            if isinstance(enriched.get("price_motion_context"), dict):
                missing_inputs[key] = enriched["price_motion_context"].get(
                    key) is None
        if isinstance(enriched.get("score_context"), dict):
            missing_inputs["signal_score"] = enriched["score_context"].get(
                "signal_score") is None
        enriched["missing_inputs"] = missing_inputs

        return enriched

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _emit_shadow_neocortex_decision_logged(
        self,
        event_name: str,
        payload: dict[str, Any],
        why: str,
    ) -> None:
        self.fsm.emit(event_name, payload=payload, why=why)

    def _build_shadow_causal_state_snapshot(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        symbol = str(kwargs.get("symbol") or "").upper()
        symbol_state = self.symbol_states.get(symbol) if isinstance(
            self.symbol_states, dict) else None
        feature_state = dict(symbol_state.get("features") or {}) if isinstance(
            symbol_state, dict) and isinstance(symbol_state.get("features"), dict) else {}

        regime_state_raw = self._per_symbol_regimes.get(symbol) if isinstance(
            getattr(self, "_per_symbol_regimes", None), dict) else None
        if isinstance(regime_state_raw, dict):
            regime_state = dict(regime_state_raw)
        elif hasattr(regime_state_raw, "model_dump"):
            regime_state = regime_state_raw.model_dump()
        else:
            regime_state = regime_state_raw

        latest_portfolio = self.latest_portfolio
        portfolio_position = None
        portfolio_ts_ms = None
        if isinstance(latest_portfolio, dict):
            portfolio_ts_ms = latest_portfolio.get(
                "ts_ms") or latest_portfolio.get("timestamp")
            positions = latest_portfolio.get("positions")
            if isinstance(positions, list):
                for position in positions:
                    if isinstance(position, dict) and str(position.get("symbol") or "").upper() == symbol:
                        portfolio_position = dict(position)
                        break

        raw_features = feature_state.get("features") if isinstance(
            feature_state.get("features"), dict) else feature_state or None
        decision_basis_ts_ms = kwargs.get("decision_basis_ts") or kwargs.get(
            "decision_ts_ms")
        feature_ts_ms = _coerce_positive_int(
            _first_mapping_value(feature_state, aliases=_CAUSAL_TIMESTAMP_KEYS)
        )
        sg = kwargs.get("sg")
        regime_label = getattr(sg, "regime", None) if sg is not None else None
        regime_confidence = getattr(
            sg, "regime_confidence", None) if sg is not None else None
        signal_score = getattr(
            sg, "signal_score", None) if sg is not None else None

        if not feature_state and regime_state is None and portfolio_position is None:
            return {}, {
                "snapshot_missing": True,
                "supports_counterfactual_join": False,
                "is_projection": True,
            }

        snapshot = {
            "snapshot_contract": "decision_making_projection_v1",
            "symbol": symbol,
            "tick_ts_ms": feature_ts_ms or decision_basis_ts_ms,
            "feature_event_ts_ms": feature_ts_ms,
            "portfolio_event_ts_ms": portfolio_ts_ms,
            "trigger_event_type": "EVT:AUTHORITY_DECISION",
            "observation": {
                "features": raw_features,
                "feature_state": feature_state or None,
            },
            "intent": {
                "rid": kwargs.get("rid"),
                "strategy_id": kwargs.get("strategy_id"),
                "side": str(kwargs.get("side") or "").upper() or None,
                "quantity": None if kwargs.get("qty") is None else str(kwargs.get("qty")),
                "reduce_only": bool(kwargs.get("reduce_only", False)),
                "proposed_action": kwargs.get("proposed_action"),
            },
            "regime_state": regime_state,
            "portfolio_position": portfolio_position,
            "safety_gate": {
                "regime": regime_label,
                "regime_confidence": regime_confidence,
                "signal_score": signal_score,
                "intent_side": getattr(sg, "intent_side", None) if sg is not None else None,
            },
        }
        snapshot.update(
            _build_snapshot_causal_time_fields(
                feature_state,
                decision_basis_ts_ms=decision_basis_ts_ms,
            )
        )
        return snapshot, {
            "snapshot_missing": False,
            "supports_counterfactual_join": False,
            "is_projection": True,
        }

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

    def _build_pre_authority_snapshot(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._build_shadow_causal_state_snapshot(**kwargs)

    def _propose_trade_intent(
        self, symbol, side, qty, price, why_chain, rid,
        reduce_only=False, strategy_id="aurora", decision_ts_ms=None,
        stop_price=None, target_price=None, entry_plan_trace=None,
        tf_sec=None, max_slippage_bps=None, max_latency_ms=None, risk_score=None,
        tpsl_owner_ctx=None,
        strategy_trace=None,
        authority_context=None,
        safety_gate_result=None,
    ):
        """Run safety-gate glue and forward allowed intents to IntentBuilder.

        When ``safety_gate_result`` is provided (from the gate chain), the
        internal safety-gate call is skipped — the chain already ran it.
        The reduce-only path still calls without it, so safety gates run
        internally as before.
        """
        if safety_gate_result is not None:
            # Safety gates already ran in the gate chain — use pre-computed result.
            sg = safety_gate_result
        else:
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
            prior_gate_low_vol_details = self._build_prior_gate_low_vol_cost_floor_details(
                symbol=symbol,
                side=side,
                price=price,
                target_price=target_price,
                stop_price=stop_price,
                strategy_id=strategy_id,
                sg=sg,
            )
            if prior_gate_low_vol_details is not None:
                sg.low_vol_cost_floor_details = self._enrich_low_vol_cost_floor_details(
                    details=prior_gate_low_vol_details,
                    sg=sg,
                    rid=str(rid),
                    decision_ts_ms=decision_ts_ms,
                    decision_outcome="DENY",
                )
            self._handle_safety_deny(
                symbol,
                side,
                rid,
                why_chain,
                sg,
                strategy_id=strategy_id,
            )
            return
        if str(getattr(sg, "regime", "") or "") == "LOW_VOLATILITY" and not reduce_only:
            try:
                gate_cfg = self.config.domains.decision_making.low_vol_cost_floor_gate
            except AttributeError:
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.CONFIG_CONTRACT_MISSING,
                    reason="DECISION",
                    context="low_vol_cost_floor_gate config missing",
                    why_chain=why_chain,
                    details={
                        "path": "domains.decision_making.low_vol_cost_floor_gate"},
                )
                self._record_blocked_intent(symbol)
                return
            trading_mode = getattr(self.config, "trading_mode", None)
            if not isinstance(trading_mode, str) or not trading_mode.strip():
                self._emit_trade_intent_rejected(
                    symbol=symbol,
                    strategy_id=str(strategy_id),
                    side=str(side),
                    rid=str(rid),
                    reason_code=NormalizedRejectReasons.CONFIG_CONTRACT_INVALID,
                    reason="DECISION",
                    context="low_vol_cost_floor_gate trading_mode invalid",
                    why_chain=why_chain,
                    details={"path": "trading_mode",
                             "value": str(trading_mode)},
                )
                self._record_blocked_intent(symbol)
                return
            low_vol_evaluation = evaluate_low_vol_cost_floor_gate(
                gate_cfg=gate_cfg,
                trading_mode=trading_mode.strip(),
                regime=getattr(sg, "regime", None),
                regime_confidence=getattr(sg, "regime_confidence", None),
                strategy_id=str(strategy_id),
                symbol=str(symbol),
                side=side,
                entry_price=price,
                target_price=target_price,
                stop_price=stop_price,
                strategy_trace=strategy_trace if isinstance(
                    strategy_trace, dict) else None,
                signal_score=getattr(sg, "signal_score", None),
                reduce_only=reduce_only,
            )
            if low_vol_evaluation.active:
                enriched_low_vol_details = self._enrich_low_vol_cost_floor_details(
                    details=low_vol_evaluation.details,
                    sg=sg,
                    rid=str(rid),
                    decision_ts_ms=decision_ts_ms,
                    decision_outcome="DENY" if low_vol_evaluation.block else "ALLOW",
                )
                sg.low_vol_cost_floor_details = enriched_low_vol_details
                merged_strategy_trace = dict(strategy_trace) if isinstance(
                    strategy_trace, dict) else {}
                merged_strategy_trace["low_vol_cost_floor"] = dict(
                    enriched_low_vol_details)
                strategy_trace = merged_strategy_trace
                if low_vol_evaluation.block:
                    sg.outcome = "DENY"
                    sg.deny_family = "LOW_VOL_COST_FLOOR"
                    sg.deny_reason = NormalizedRejectReasons.LOW_VOL_COST_FLOOR_BLOCKED
                    sg.why_short = "low_vol_cost_floor_blocked"
                    self._emit_trade_intent_rejected(
                        symbol=symbol,
                        strategy_id=str(strategy_id),
                        side=str(side),
                        rid=str(rid),
                        reason_code=NormalizedRejectReasons.LOW_VOL_COST_FLOOR_BLOCKED,
                        reason="DECISION",
                        context="LOW_VOL_COST_FLOOR_BLOCKED",
                        why_chain=why_chain,
                        details=dict(enriched_low_vol_details),
                    )
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
            authority_context=authority_context,
            normalize_mode=self.normalize_signals_mode, sg=sg)

    def _handle_safety_deny(self, symbol, side, rid, why_chain, sg, *, strategy_id: str) -> None:
        """Emit best-effort observability for a safety-gate denial."""
        def _g(a, d=None): return getattr(sg, a, d)  # noqa: E731
        deny_family = str(_g("deny_family", "SAFETY_GATES") or "SAFETY_GATES")
        trace = build_decision_trace_payload(
            rid=str(rid),
            symbol=str(symbol),
            strategy_id=str(strategy_id),
            trace_ts_ms=_g("trace_ts_ms"),
            intent_side=_g("intent_side"),
            order_side=str(side),
            lifecycle_id=None,
            sg=sg,
            regime_provenance=_g("regime_provenance") if isinstance(
                _g("regime_provenance"), dict) else None,
            tpsl_owner_ctx=None,
            gate_outcome="DENY",
            deny_reason=sg.deny_reason,
            why=_g("why_short", ""),
        )
        # Observability is best-effort here: a failed trace emit must not turn a
        # denied decision into a runtime exception.
        try:
            self.fsm.emit("EVT:DECISION_TRACE_EMITTED", payload=trace,
                          why="decision_trace", data_ref=why_chain)
        except Exception as emit_e:
            self.logger.error(
                f"[{symbol}] OBSERVABILITY: EVT:DECISION_TRACE_EMITTED emit failed. "
                f"RID={rid}. reason={emit_e}",
                exc_info=True,
            )
        side_u = str(side).upper() if str(
            side).upper() in ("BUY", "SELL") else "NONE"
        # Mirror the denial into an explicitly decision-local journal row so it
        # does not masquerade as canonical execution/runtime ORDER_REJECTED.
        try:
            order_logger.write({
                "rid": rid, "event_type": "DECISION_INTENT_REJECTED", "symbol": symbol, "side": side_u,
                "strategy_id": str(strategy_id),
                "origin_class": "decision_alias",
                "nrr_code": str(sg.deny_reason) if sg.deny_reason else None,
                "regime": _g("regime"),
                "regime_confidence": _g("regime_confidence"),
                "regime_provenance": _g("regime_provenance") if isinstance(_g("regime_provenance"), dict) else None,
                "why": f"{deny_family}:{_g('why_short', '')}", "source_fsm": "DecisionMaking",
                "metadata": {
                    "reject_reason": f"{deny_family}_DENY",
                    "deny_reason": sg.deny_reason,
                    "canonical_event_family": "TRADE_INTENT_REJECTED",
                    "alias_of": "TRADE_INTENT_REJECTED",
                    "resolved_regime_confidence_strategy_id": _g("resolved_regime_confidence_strategy_id"),
                    "resolved_regime_confidence_symbol": _g("resolved_regime_confidence_symbol"),
                    "resolved_regime_confidence_regime_key": _g("resolved_regime_confidence_regime_key"),
                    "min_regime_confidence": _g("min_regime_confidence"),
                    "resolved_min_regime_confidence": _g("resolved_min_regime_confidence"),
                    "resolved_min_regime_confidence_source": _g("resolved_min_regime_confidence_source"),
                    "resolved_min_regime_confidence_strategy_id": _g("resolved_min_regime_confidence_strategy_id"),
                    "resolved_min_regime_confidence_regime_key": _g("resolved_min_regime_confidence_regime_key"),
                    "resolved_max_regime_confidence": _g("resolved_max_regime_confidence"),
                    "resolved_max_regime_confidence_source": _g("resolved_max_regime_confidence_source"),
                    "resolved_max_regime_confidence_strategy_id": _g("resolved_max_regime_confidence_strategy_id"),
                    "resolved_max_regime_confidence_regime_key": _g("resolved_max_regime_confidence_regime_key"),
                    "resolved_regime_confidence_band_active": _g("resolved_regime_confidence_band_active"),
                    "regime_confidence_breach_kind": _g("regime_confidence_breach_kind"),
                    "regime_confidence_gate_verdict": _g("regime_confidence_gate_verdict"),
                    "threshold_applied": _g("threshold_applied"),
                    "threshold_verdict": _g("threshold_verdict"),
                    "threshold_reason": _g("threshold_reason"),
                    "low_vol_cost_floor": dict(_g("low_vol_cost_floor_details")) if isinstance(_g("low_vol_cost_floor_details"), dict) else None,
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
    def on_position_closed(self, event): self._evt.on_position_closed(event)

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
