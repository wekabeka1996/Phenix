from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Optional

from apps.reference.config_models import (
    PositionPolicySidecarConfig,
    PositionPolicySidecarMode,
)
from apps.reference.contracts.runtime_regime_layers import normalize_structural_regime_label
from apps.reference.core.time import get_clock
from apps.reference.telemetry.trade_lifecycle_logger import append_trade_lifecycle_record

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(__name__)

SIDECAR_VERSION = "1.0.0"
EVALUATION_MODE = "phase1_recommendation_only"
POLICY_RECORD_KIND = "position_policy_sidecar"


@dataclass(frozen=True)
class PositionPolicyCloseRequest:
    """Deferred Phase-2 request object for EP-owned soft-close translation."""

    trace_id: str
    symbol: str
    requested_action: str = "SOFT_CLOSE"
    requested_qty: Optional[str] = None
    target_mode: str = "symbol_current_net_only"
    policy_source: str = "position_policy_sidecar"
    reason_codes: tuple[str, ...] = ()
    score_snapshot: Dict[str, float] = field(default_factory=dict)


@dataclass
class _Envelope:
    payload: Dict[str, Any] = field(default_factory=dict)
    ts_ms: int = 0
    update_count: int = 0


@dataclass
class _SymbolState:
    portfolio: _Envelope = field(default_factory=_Envelope)
    features: _Envelope = field(default_factory=_Envelope)
    regime: _Envelope = field(default_factory=_Envelope)
    order_state: _Envelope = field(default_factory=_Envelope)
    last_fill: _Envelope = field(default_factory=_Envelope)
    last_reconcile_ts_ms: int = 0
    last_evaluation_ts_ms: int = 0
    last_suppression_reason: str = ""


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _coerce_float(value: Any) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _coerce_str(value: Any) -> Optional[str]:
    if value in (None, "", "None"):
        return None
    return str(value).strip()


def _extract_ts_ms(payload: Dict[str, Any], fallback_ms: int) -> int:
    for key in (
        "event_ts_ms",
        "ts_ms",
        "timestamp_ms",
        "timestamp",
        "positions_last_ts_ms",
    ):
        value = _coerce_float(payload.get(key))
        if value is not None and value >= 0:
            return int(value)
    return int(fallback_ms)


def _first_present_value(payload: Dict[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        if alias in payload and payload.get(alias) not in (None, "", "None"):
            return payload.get(alias)
    return None


def _normalize_portfolio_position_snapshot(
    position: Dict[str, Any],
    *,
    snapshot_ts_ms: int,
    positions_last_ts_ms: Any,
) -> Dict[str, Any]:
    normalized = dict(position)
    retained_positions_last_ts_ms = _coerce_float(positions_last_ts_ms)
    normalized["positions_last_ts_ms"] = (
        int(retained_positions_last_ts_ms)
        if retained_positions_last_ts_ms is not None
        else int(snapshot_ts_ms)
    )
    normalized["portfolio_symbol_present"] = True
    normalized["portfolio_snapshot_status"] = "present"

    position_amt = _first_present_value(
        position, ("net_position", "positionAmt"))
    entry_price = _first_present_value(
        position,
        ("avg_entry_price", "entryPrice", "avgEntryPrice"),
    )
    if position_amt is not None:
        normalized["positionAmt"] = position_amt
    if entry_price is not None:
        normalized["entryPrice"] = entry_price

    if _coerce_float(normalized.get("positionAmt")) is None:
        normalized["portfolio_snapshot_status"] = "position_malformed"

    return normalized


def _missing_portfolio_position_snapshot(
    symbol: str,
    *,
    snapshot_ts_ms: int,
    positions_last_ts_ms: Any,
    status: str,
) -> Dict[str, Any]:
    retained_positions_last_ts_ms = _coerce_float(positions_last_ts_ms)
    return {
        "symbol": symbol,
        "positions_last_ts_ms": (
            int(retained_positions_last_ts_ms)
            if retained_positions_last_ts_ms is not None
            else int(snapshot_ts_ms)
        ),
        "portfolio_symbol_present": False,
        "portfolio_snapshot_status": status,
    }


def _portfolio_snapshot_is_usable(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False

    if payload.get("portfolio_symbol_present") is False:
        return False

    status = _coerce_str(payload.get("portfolio_snapshot_status"))
    if status is not None and status != "present":
        return False

    return _coerce_float(payload.get("positionAmt")) is not None


def _lookup_nested_numeric(payload: Dict[str, Any], aliases: Iterable[str]) -> Optional[float]:
    containers = [payload]
    for container_key in (
        "features",
        "feature_values",
        "values",
        "metrics",
        "microstructure",
        "context",
        "metadata",
    ):
        candidate = payload.get(container_key)
        if isinstance(candidate, dict):
            containers.append(candidate)

    for alias in aliases:
        for container in containers:
            value = _coerce_float(container.get(alias))
            if value is not None:
                return value
    return None


def _lookup_nested_string(payload: Dict[str, Any], aliases: Iterable[str]) -> str:
    containers = [payload]
    for container_key in ("regime", "context", "metadata"):
        candidate = payload.get(container_key)
        if isinstance(candidate, dict):
            containers.append(candidate)

    for alias in aliases:
        for container in containers:
            value = container.get(alias)
            if value not in (None, ""):
                return str(value).strip()
    return ""


class PositionPolicySidecar:
    """Explainable, derived-context evaluator for already-open positions."""

    def __init__(
        self,
        *,
        config: PositionPolicySidecarConfig,
        bus: Any,
        manage_flow_getter: Callable[[str], Optional["ManageFlowFSM"]],
        known_symbols_getter: Callable[[], Iterable[str]],
    ) -> None:
        self.config = config
        self.mode = config.mode
        self._bus = bus
        self._manage_flow_getter = manage_flow_getter
        self._known_symbols_getter = known_symbols_getter
        self._states: Dict[str, _SymbolState] = {}
        self._started_at_ms = get_clock().now_ms()
        self._trace_counter = 0

    def announce_mode_active(self) -> None:
        payload = {
            "ts_ms": get_clock().now_ms(),
            "trace_id": self._next_trace_id("__DOMAIN__"),
            "symbol": "__DOMAIN__",
            "sidecar_version": SIDECAR_VERSION,
            "mode": self.mode.value,
            "evaluation_mode": EVALUATION_MODE,
            "event_type": "POSITION_POLICY_SIDECAR_MODE_ACTIVE",
            "reason_codes": ["sidecar_initialized"],
            "position_snapshot": {},
            "feature_ref": {},
            "regime_ref": {},
            "freshness_snapshot": {},
        }
        self._publish("EVT:POSITION_POLICY_SIDECAR_MODE_ACTIVE", payload)

    def on_features_calculated(self, event: "Message") -> None:
        symbol = _normalize_symbol((event.pld or {}).get("symbol"))
        if not symbol:
            self._publish_malformed_payload(
                "FEATURES_CALCULATED", "missing_symbol")
            return
        self._update_envelope(symbol, "features", event.pld or {})
        self._evaluate_symbol(symbol, trigger_event="FEATURES_CALCULATED")

    def on_regime_detected(self, event: "Message") -> None:
        symbol = _normalize_symbol((event.pld or {}).get("symbol"))
        if not symbol:
            self._publish_malformed_payload(
                "REGIME_DETECTED", "missing_symbol")
            return
        self._update_envelope(symbol, "regime", event.pld or {})
        self._evaluate_symbol(symbol, trigger_event="REGIME_DETECTED")

    def on_trade_executed(self, event: "Message") -> None:
        self._on_fill_event(event, trigger_event="TRADE_EXECUTED")

    def on_order_fill(self, event: "Message") -> None:
        self._on_fill_event(event, trigger_event="ORDER_FILL")

    def _on_fill_event(self, event: "Message", *, trigger_event: str) -> None:
        payload = dict(event.pld or {})
        symbol = _normalize_symbol(payload.get("symbol"))
        if not symbol:
            self._publish_malformed_payload(trigger_event, "missing_symbol")
            return
        self._update_envelope(symbol, "last_fill", payload)
        reduce_only = _coerce_bool(
            payload.get("reduceOnly") if "reduceOnly" in payload else payload.get(
                "reduce_only")
        )
        if reduce_only is False:
            state = self._state(symbol)
            state.last_reconcile_ts_ms = 0
            state.order_state = _Envelope()
        self._evaluate_symbol(symbol, trigger_event=trigger_event)

    def on_order_state_changed(self, event: "Message") -> None:
        payload = dict(event.pld or {})
        symbol = _normalize_symbol(payload.get("symbol"))
        if not symbol:
            self._publish_malformed_payload(
                "ORDER_STATE_CHANGED", "missing_symbol")
            return
        self._update_envelope(symbol, "order_state", payload)
        self._evaluate_symbol(symbol, trigger_event="ORDER_STATE_CHANGED")

    def on_execution_close_reconciled(self, event: "Message") -> None:
        payload = dict(event.pld or {})
        symbol = _normalize_symbol(payload.get("symbol"))
        if not symbol:
            self._publish_malformed_payload(
                "EXECUTION_CLOSE_RECONCILED", "missing_symbol")
            return
        state = self._state(symbol)
        state.last_reconcile_ts_ms = _extract_ts_ms(
            payload, get_clock().now_ms())
        self._evaluate_symbol(
            symbol, trigger_event="EXECUTION_CLOSE_RECONCILED")

    def on_portfolio_state_updated(self, event: "Message") -> None:
        payload = dict(event.pld or {})
        now_ms = get_clock().now_ms()
        snapshot_ts_ms = _extract_ts_ms(payload, now_ms)
        positions_last_ts_ms = payload.get("positions_last_ts_ms")

        raw_positions = payload.get("positions")
        positions = raw_positions if isinstance(raw_positions, list) else []
        seen_symbols: set[str] = set()
        for position in positions:
            if not isinstance(position, dict):
                continue
            symbol = _normalize_symbol(position.get("symbol"))
            if not symbol:
                continue
            state = self._state(symbol)
            state.portfolio.payload = _normalize_portfolio_position_snapshot(
                position,
                snapshot_ts_ms=snapshot_ts_ms,
                positions_last_ts_ms=positions_last_ts_ms,
            )
            state.portfolio.ts_ms = snapshot_ts_ms
            state.portfolio.update_count += 1
            seen_symbols.add(symbol)

        candidate_symbols = seen_symbols | set(self._known_symbols_getter())
        missing_snapshot_status = (
            "positions_malformed"
            if raw_positions not in (None, []) and not isinstance(raw_positions, list)
            else "symbol_absent"
        )
        for symbol in candidate_symbols:
            if symbol not in seen_symbols:
                state = self._state(symbol)
                state.portfolio.payload = _missing_portfolio_position_snapshot(
                    symbol,
                    snapshot_ts_ms=snapshot_ts_ms,
                    positions_last_ts_ms=positions_last_ts_ms,
                    status=missing_snapshot_status,
                )
                state.portfolio.ts_ms = snapshot_ts_ms
                state.portfolio.update_count += 1
            self._evaluate_symbol(
                symbol, trigger_event="PORTFOLIO_STATE_UPDATED")

    def _state(self, symbol: str) -> _SymbolState:
        return self._states.setdefault(symbol, _SymbolState())

    def _update_envelope(self, symbol: str, attr: str, payload: Dict[str, Any]) -> None:
        envelope = getattr(self._state(symbol), attr)
        envelope.payload = dict(payload)
        envelope.ts_ms = _extract_ts_ms(payload, get_clock().now_ms())
        envelope.update_count += 1

    def _evaluate_symbol(self, symbol: str, *, trigger_event: str) -> None:
        if self.mode == PositionPolicySidecarMode.DISABLE:
            return

        symbol = _normalize_symbol(symbol)
        if not symbol:
            return

        state = self._state(symbol)
        trace_id = self._next_trace_id(symbol)
        now_ms = get_clock().now_ms()
        manage_flow = self._manage_flow_getter(symbol)

        base_payload = self._base_payload(
            symbol=symbol,
            trace_id=trace_id,
            trigger_event=trigger_event,
            state=state,
            manage_flow=manage_flow,
        )

        suppression = self._determine_suppression(
            now_ms=now_ms,
            state=state,
            manage_flow=manage_flow,
            trigger_event=trigger_event,
            base_payload=base_payload,
        )
        if suppression is not None:
            payload = dict(base_payload)
            payload["event_type"] = "POSITION_POLICY_SIDECAR_SUPPRESSED"
            payload["reason_codes"] = [
                f"trigger:{trigger_event.lower()}", suppression["reason_code"]]
            payload["suppression_reason"] = suppression["suppression_reason"]
            payload["incumbent_owner"] = suppression.get("incumbent_owner")
            payload["score_snapshot"] = suppression.get("score_snapshot", {})
            state.last_suppression_reason = suppression["suppression_reason"]
            self._publish("EVT:POSITION_POLICY_SIDECAR_SUPPRESSED", payload)
            return

        score_snapshot = self._compute_scores(
            state=state, manage_flow=manage_flow)
        state.last_evaluation_ts_ms = now_ms

        scores_payload = dict(base_payload)
        scores_payload["event_type"] = "POSITION_POLICY_SIDECAR_SCORES"
        scores_payload["reason_codes"] = [
            f"trigger:{trigger_event.lower()}", "scores_computed"]
        scores_payload["score_snapshot"] = score_snapshot
        self._publish("EVT:POSITION_POLICY_SIDECAR_SCORES", scores_payload)

        evaluated_payload = dict(base_payload)
        evaluated_payload["event_type"] = "POSITION_POLICY_SIDECAR_EVALUATED"
        evaluated_payload["reason_codes"] = [
            f"trigger:{trigger_event.lower()}", "evaluation_completed"]
        evaluated_payload["score_snapshot"] = score_snapshot
        self._publish("EVT:POSITION_POLICY_SIDECAR_EVALUATED",
                      evaluated_payload)

        if score_snapshot["soft_close_pressure"] < self.config.thresholds.recommend_soft_close_at:
            return

        recommended_payload = dict(base_payload)
        recommended_payload["event_type"] = "POSITION_POLICY_SIDECAR_RECOMMENDED"
        recommended_payload["reason_codes"] = [
            f"trigger:{trigger_event.lower()}",
            "recommend_soft_close_threshold_met",
        ]
        recommended_payload["score_snapshot"] = score_snapshot
        self._publish("EVT:POSITION_POLICY_SIDECAR_RECOMMENDED",
                      recommended_payload)

        if self.mode == PositionPolicySidecarMode.ENABLE:
            skipped_payload = dict(recommended_payload)
            skipped_payload["event_type"] = "POSITION_POLICY_SIDECAR_ACTION_SKIPPED"
            skipped_payload["reason_codes"] = [
                f"trigger:{trigger_event.lower()}",
                "phase1_recommendation_only",
            ]
            skipped_payload["why"] = "phase1_enable_mode_does_not_request_close"
            skipped_payload["allowed_action_scope"] = {
                "soft_close_symbol_current_net_only": self.config.allowed_actions.soft_close_symbol_current_net_only,
                "partial_reduce": self.config.allowed_actions.partial_reduce,
                "bracket_mutation": self.config.allowed_actions.bracket_mutation,
                "exact_targeting": self.config.allowed_actions.exact_targeting,
            }
            self._publish(
                "EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED", skipped_payload)

    def _determine_suppression(
        self,
        *,
        now_ms: int,
        state: _SymbolState,
        manage_flow: Optional["ManageFlowFSM"],
        trigger_event: str,
        base_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if now_ms - self._started_at_ms < self.config.startup_grace.startup_grace_ms:
            return {"reason_code": "startup_grace_active", "suppression_reason": "startup_grace_active"}

        if manage_flow is None:
            return {"reason_code": "no_active_lifecycle", "suppression_reason": "no_manage_flow_for_symbol"}

        if hasattr(manage_flow, "has_active_lifecycle") and not manage_flow.has_active_lifecycle():
            return {"reason_code": "no_active_lifecycle", "suppression_reason": "manage_flow_has_no_active_lifecycle"}

        if bool(getattr(manage_flow, "_closing_position", False)):
            return {
                "reason_code": "close_in_progress",
                "suppression_reason": "manage_flow_close_in_progress",
                "incumbent_owner": "ManageFlowFSM",
            }

        if state.last_reconcile_ts_ms > 0:
            if state.last_fill.ts_ms <= 0 or state.last_reconcile_ts_ms >= state.last_fill.ts_ms:
                return {
                    "reason_code": "close_reconciled",
                    "suppression_reason": "authoritative_close_reconciled",
                    "incumbent_owner": "OrderGuardian",
                }

        if state.last_fill.ts_ms > 0 and (
            now_ms - state.last_fill.ts_ms < self.config.startup_grace.post_fill_grace_ms
        ):
            return {"reason_code": "post_fill_grace_active", "suppression_reason": "post_fill_grace_active"}

        if (
            state.portfolio.update_count < self.config.startup_grace.min_portfolio_updates
            or state.features.update_count < self.config.startup_grace.min_feature_updates
            or state.regime.update_count < self.config.startup_grace.min_regime_updates
        ):
            return {"reason_code": "warmup_incomplete", "suppression_reason": "warmup_incomplete"}

        freshness = base_payload["freshness_snapshot"]
        if not freshness["portfolio_fresh"]:
            return {"reason_code": "portfolio_stale", "suppression_reason": "portfolio_snapshot_missing_or_stale"}
        if not freshness["features_fresh"]:
            return {"reason_code": "features_stale", "suppression_reason": "features_snapshot_missing_or_stale"}
        if not freshness["regime_fresh"]:
            return {"reason_code": "regime_stale", "suppression_reason": "regime_snapshot_missing_or_stale"}

        order_state_terminal = _coerce_bool(
            state.order_state.payload.get("terminal_non_fill"))
        if order_state_terminal and freshness["order_state_fresh"]:
            return {
                "reason_code": "terminal_order_state_recent",
                "suppression_reason": "recent_terminal_order_state_detected",
                "incumbent_owner": "OrderGuardian",
            }

        if not _portfolio_snapshot_is_usable(state.portfolio.payload):
            return {
                "reason_code": "portfolio_missing",
                "suppression_reason": "portfolio_snapshot_missing_or_stale",
            }

        position_snapshot = base_payload["position_snapshot"]
        if not position_snapshot.get("side"):
            return {
                "reason_code": "ambiguous_lifecycle_state",
                "suppression_reason": "missing_position_side_for_active_lifecycle",
            }

        portfolio_qty = _coerce_float(
            position_snapshot.get("portfolio_position_amt"))
        if portfolio_qty is not None and abs(portfolio_qty) <= 0.0 and manage_flow.has_active_lifecycle():
            return {
                "reason_code": "ambiguous_terminal_transition",
                "suppression_reason": "portfolio_flat_while_local_lifecycle_active",
            }

        if self._is_profitable(position_snapshot):
            score_snapshot = {
                "position_health_score": 1.0,
                "exit_pressure_score": 0.0,
                "hold_confidence": 1.0,
                "soft_close_pressure": 0.0,
                "microstructure_adverse_pressure": 0.0,
                "regime_exhaustion_hint": 0.0,
                "conviction_decay": 0.0,
                "unrealized_loss_pressure": 0.0,
            }
            return {
                "reason_code": "profitable_guard",
                "suppression_reason": "profitability_guard_active",
                "score_snapshot": score_snapshot,
            }

        if trigger_event == "EXECUTION_CLOSE_RECONCILED":
            return {
                "reason_code": "close_reconciled",
                "suppression_reason": "authoritative_close_reconciled",
                "incumbent_owner": "OrderGuardian",
            }

        return None

    def _compute_scores(
        self,
        *,
        state: _SymbolState,
        manage_flow: Optional["ManageFlowFSM"],
    ) -> Dict[str, float]:
        position_snapshot = self._position_snapshot(state, manage_flow)
        side_sign = 1.0 if position_snapshot.get("side") == "BUY" else -1.0

        feature_payload = state.features.payload
        regime_payload = state.regime.payload

        microstructure_from_payload = _lookup_nested_numeric(
            feature_payload,
            ("microstructure_adverse_pressure", "adverse_microstructure_pressure"),
        )
        if microstructure_from_payload is not None:
            microstructure_adverse_pressure = _clamp(
                microstructure_from_payload)
        else:
            imbalance = _lookup_nested_numeric(
                feature_payload,
                ("orderbook_imbalance", "book_imbalance", "microstructure_imbalance"),
            )
            adverse_price_distance_bps = _lookup_nested_numeric(
                feature_payload,
                ("price_vs_vwap_bps", "distance_from_vwap_bps", "vwap_distance_bps"),
            )
            imbalance_pressure = 0.0
            if imbalance is not None:
                raw_adverse = max(0.0, -side_sign * imbalance)
                imbalance_pressure = _clamp(
                    raw_adverse / self.config.thresholds.book_imbalance_full_pressure
                )
            distance_pressure = 0.0
            if adverse_price_distance_bps is not None:
                raw_bps = max(0.0, -side_sign * adverse_price_distance_bps)
                distance_pressure = _clamp(
                    raw_bps / self.config.thresholds.adverse_price_distance_bps_full_pressure
                )
            microstructure_adverse_pressure = max(
                imbalance_pressure, distance_pressure)

        regime_exhaustion_direct = _lookup_nested_numeric(
            regime_payload,
            ("regime_exhaustion_hint", "exhaustion_hint"),
        )
        if regime_exhaustion_direct is not None:
            regime_exhaustion_hint = _clamp(regime_exhaustion_direct)
        else:
            regime_confidence = _coerce_float(
                regime_payload.get("confidence")
                if "confidence" in regime_payload
                else regime_payload.get("regime_confidence")
            )
            confidence_pressure = 0.0
            if regime_confidence is not None:
                confidence_pressure = _clamp(
                    (
                        self.config.thresholds.regime_confidence_floor - regime_confidence
                    )
                    / self.config.thresholds.regime_confidence_floor
                )
            regime_label = normalize_structural_regime_label(
                _lookup_nested_string(
                    regime_payload, ("regime", "label", "name"))
            )
            adverse_labels = (
                self.config.thresholds.adverse_regimes_long
                if position_snapshot.get("side") == "BUY"
                else self.config.thresholds.adverse_regimes_short
            )
            adverse_label_pressure = 1.0 if regime_label in adverse_labels else 0.0
            regime_exhaustion_hint = max(
                confidence_pressure, adverse_label_pressure)

        conviction_decay_direct = _lookup_nested_numeric(
            feature_payload,
            ("conviction_decay", "hold_confidence_decay"),
        )
        if conviction_decay_direct is not None:
            conviction_decay = _clamp(conviction_decay_direct)
        else:
            signal_score = _lookup_nested_numeric(
                feature_payload,
                ("signal_score", "score", "entry_score", "conviction_score"),
            )
            conviction_decay = 0.0
            if signal_score is not None and signal_score < self.config.thresholds.signal_score_floor:
                gap = self.config.thresholds.signal_score_floor - signal_score
                denominator = abs(
                    self.config.thresholds.signal_score_floor) or 1.0
                conviction_decay = _clamp(gap / denominator)

        unrealized_loss_pressure = 0.0
        unrealized_pnl_pct = _coerce_float(
            position_snapshot.get("unrealized_pnl_pct"))
        if unrealized_pnl_pct is not None and unrealized_pnl_pct < 0.0:
            loss_bps = abs(unrealized_pnl_pct) * 100.0
            unrealized_loss_pressure = _clamp(
                loss_bps / self.config.thresholds.loss_bps_full_pressure
            )

        weights = self.config.scoring.weights
        caps = self.config.scoring.caps

        weighted_micro = min(microstructure_adverse_pressure,
                             caps.microstructure_adverse_pressure) * weights.microstructure_adverse_pressure
        weighted_regime = min(
            regime_exhaustion_hint, caps.regime_exhaustion_hint) * weights.regime_exhaustion_hint
        weighted_decay = min(
            conviction_decay, caps.conviction_decay) * weights.conviction_decay
        weighted_loss = min(unrealized_loss_pressure,
                            caps.unrealized_loss_pressure) * weights.unrealized_loss_pressure

        exit_pressure_score = _clamp(
            weighted_micro + weighted_regime + weighted_decay + weighted_loss)
        soft_close_pressure = exit_pressure_score
        hold_confidence = _clamp(1.0 - exit_pressure_score)
        position_health_score = _clamp(1.0 - soft_close_pressure)

        return {
            "position_health_score": position_health_score,
            "exit_pressure_score": exit_pressure_score,
            "hold_confidence": hold_confidence,
            "soft_close_pressure": soft_close_pressure,
            "microstructure_adverse_pressure": microstructure_adverse_pressure,
            "regime_exhaustion_hint": regime_exhaustion_hint,
            "conviction_decay": conviction_decay,
            "unrealized_loss_pressure": unrealized_loss_pressure,
        }

    def _base_payload(
        self,
        *,
        symbol: str,
        trace_id: str,
        trigger_event: str,
        state: _SymbolState,
        manage_flow: Optional["ManageFlowFSM"],
    ) -> Dict[str, Any]:
        return {
            "ts_ms": get_clock().now_ms(),
            "trace_id": trace_id,
            "symbol": symbol,
            "sidecar_version": SIDECAR_VERSION,
            "mode": self.mode.value,
            "evaluation_mode": EVALUATION_MODE,
            "trigger_event": trigger_event,
            "reason_codes": [f"trigger:{trigger_event.lower()}"],
            "position_snapshot": self._position_snapshot(state, manage_flow),
            "feature_ref": self._snapshot_ref(state.features),
            "regime_ref": self._snapshot_ref(state.regime),
            "freshness_snapshot": self._freshness_snapshot(state),
            "fill_correlation": self._fill_correlation(state),
            "portfolio_correlation": self._portfolio_correlation(state),
        }

    def _fill_correlation(self, state: _SymbolState) -> Dict[str, Any]:
        payload = state.last_fill.payload or {}
        return {
            "rid": payload.get("rid"),
            "order_id": payload.get("orderId"),
            "client_order_id": payload.get("clientOrderId") or payload.get("client_order_id"),
            "fill_source": payload.get("fill_source"),
            "canonical_fill_trace_id": payload.get("canonical_fill_trace_id"),
            "manage_flow_created": payload.get("manage_flow_created"),
            "manage_state_before": payload.get("manage_state_before"),
            "manage_state_after": payload.get("manage_state_after"),
        }

    def _portfolio_correlation(self, state: _SymbolState) -> Dict[str, Any]:
        fill_payload = state.last_fill.payload or {}
        portfolio_payload = state.portfolio.payload or {}
        portfolio_position_amt = portfolio_payload.get("positionAmt")
        if not _portfolio_snapshot_is_usable(portfolio_payload):
            portfolio_position_amt = None
        return {
            "position_signature": fill_payload.get("portfolio_position_signature"),
            "positions_last_ts_ms": portfolio_payload.get("positions_last_ts_ms"),
            "portfolio_snapshot_status": portfolio_payload.get("portfolio_snapshot_status"),
            "portfolio_position_amt": portfolio_position_amt,
        }

    def _position_snapshot(
        self,
        state: _SymbolState,
        manage_flow: Optional["ManageFlowFSM"],
    ) -> Dict[str, Any]:
        portfolio = state.portfolio.payload or {}
        symbol = _normalize_symbol(portfolio.get(
            "symbol") or getattr(manage_flow, "symbol", ""))

        side = ""
        if manage_flow is not None and getattr(manage_flow, "position_side", None):
            side = str(getattr(manage_flow, "position_side") or "").upper()
        if not side:
            portfolio_amt = _coerce_float(portfolio.get("positionAmt"))
            if portfolio_amt is not None and portfolio_amt > 0:
                side = "BUY"
            elif portfolio_amt is not None and portfolio_amt < 0:
                side = "SELL"

        unrealized_pnl_usdt = _coerce_float(
            portfolio.get("unrealizedProfit")
            if "unrealizedProfit" in portfolio
            else portfolio.get("unrealizedPnl")
        )
        unrealized_pnl_pct = self._compute_unrealized_pnl_pct(
            portfolio=portfolio,
            manage_flow=manage_flow,
            unrealized_pnl_usdt=unrealized_pnl_usdt,
            side=side,
        )

        manage_state = getattr(manage_flow, "state", None)
        if manage_state is not None and hasattr(manage_state, "value"):
            manage_state = manage_state.value

        return {
            "symbol": symbol,
            "manage_state": manage_state,
            "closing_position": bool(getattr(manage_flow, "_closing_position", False)),
            "side": side,
            "position_qty": str(getattr(manage_flow, "position_qty", "") or ""),
            "entry_price": str(getattr(manage_flow, "position_entry_price", "") or ""),
            "portfolio_position_amt": portfolio.get("positionAmt"),
            "portfolio_snapshot_status": portfolio.get("portfolio_snapshot_status"),
            "portfolio_symbol_present": portfolio.get("portfolio_symbol_present"),
            "mark_price": portfolio.get("markPrice"),
            "portfolio_entry_price": portfolio.get("entryPrice"),
            "unrealized_pnl_usdt": unrealized_pnl_usdt,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "position_open_ts": getattr(manage_flow, "position_open_ts", 0.0),
        }

    def _compute_unrealized_pnl_pct(
        self,
        *,
        portfolio: Dict[str, Any],
        manage_flow: Optional["ManageFlowFSM"],
        unrealized_pnl_usdt: Optional[float],
        side: str,
    ) -> Optional[float]:
        direct_pct = _coerce_float(
            portfolio.get("unrealized_pnl_pct")
            if "unrealized_pnl_pct" in portfolio
            else portfolio.get("unrealizedPnlPct")
        )
        if direct_pct is not None:
            return direct_pct

        entry_price = _coerce_float(portfolio.get("entryPrice"))
        mark_price = _coerce_float(portfolio.get("markPrice"))
        position_amt = _coerce_float(portfolio.get("positionAmt"))

        if entry_price is None and manage_flow is not None:
            entry_price = _coerce_float(
                getattr(manage_flow, "position_entry_price", None))
        if position_amt is None and manage_flow is not None:
            position_amt = _coerce_float(
                getattr(manage_flow, "position_qty", None))

        if unrealized_pnl_usdt is not None and entry_price not in (None, 0.0) and position_amt not in (None, 0.0):
            notional = abs(position_amt) * entry_price
            if notional > 0.0:
                return (unrealized_pnl_usdt / notional) * 100.0

        if entry_price in (None, 0.0) or mark_price is None:
            return None

        side_sign = 1.0 if side == "BUY" else -1.0
        return side_sign * ((mark_price - entry_price) / entry_price) * 100.0

    def _freshness_snapshot(self, state: _SymbolState) -> Dict[str, Any]:
        now_ms = get_clock().now_ms()
        portfolio_age_ms = now_ms - state.portfolio.ts_ms if state.portfolio.ts_ms else None
        features_age_ms = now_ms - state.features.ts_ms if state.features.ts_ms else None
        regime_age_ms = now_ms - state.regime.ts_ms if state.regime.ts_ms else None
        order_state_age_ms = now_ms - \
            state.order_state.ts_ms if state.order_state.ts_ms else None

        return {
            "portfolio_age_ms": portfolio_age_ms,
            "features_age_ms": features_age_ms,
            "regime_age_ms": regime_age_ms,
            "order_state_age_ms": order_state_age_ms,
            "portfolio_fresh": portfolio_age_ms is not None
            and portfolio_age_ms <= self.config.freshness.portfolio_max_age_ms,
            "features_fresh": features_age_ms is not None
            and features_age_ms <= self.config.freshness.features_max_age_ms,
            "regime_fresh": regime_age_ms is not None
            and regime_age_ms <= self.config.freshness.regime_max_age_ms,
            "order_state_fresh": order_state_age_ms is not None
            and order_state_age_ms <= self.config.freshness.order_state_max_age_ms,
            "last_reconcile_ts_ms": state.last_reconcile_ts_ms or None,
        }

    def _snapshot_ref(self, envelope: _Envelope) -> Dict[str, Any]:
        if envelope.ts_ms <= 0:
            return {}
        return {
            "ts_ms": envelope.ts_ms,
            "update_count": envelope.update_count,
        }

    def _is_profitable(self, position_snapshot: Dict[str, Any]) -> bool:
        if not self.config.profitability_guard.enabled:
            return False
        pnl_pct = _coerce_float(position_snapshot.get("unrealized_pnl_pct"))
        pnl_usdt = _coerce_float(position_snapshot.get("unrealized_pnl_usdt"))
        if pnl_pct is not None and pnl_pct >= self.config.profitability_guard.min_unrealized_pnl_pct:
            return True
        if pnl_usdt is not None and pnl_usdt >= self.config.profitability_guard.min_unrealized_pnl_usdt:
            return True
        return False

    def _next_trace_id(self, symbol: str) -> str:
        self._trace_counter += 1
        return f"pps:{symbol}:{get_clock().now_ms()}:{self._trace_counter}"

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        why = f"position_policy_sidecar:{payload['event_type'].lower()}"
        if self.config.logging.emit_internal_bus_events:
            try:
                self._bus.emit(topic, dict(payload), why=why)
            except Exception as exc:
                LOG.warning(
                    "PositionPolicySidecar failed to emit %s: %s", topic, exc)

        if self.config.logging.write_trade_lifecycle_jsonl:
            record = {
                "record_kind": POLICY_RECORD_KIND,
                **payload,
            }
            append_trade_lifecycle_record(
                record,
                log_file=self.config.logging.trade_lifecycle_log_path,
            )

    def _publish_malformed_payload(self, trigger_event: str, reason: str) -> None:
        payload = {
            "ts_ms": get_clock().now_ms(),
            "trace_id": self._next_trace_id("__UNKNOWN__"),
            "symbol": "__UNKNOWN__",
            "sidecar_version": SIDECAR_VERSION,
            "mode": self.mode.value,
            "evaluation_mode": EVALUATION_MODE,
            "event_type": "POSITION_POLICY_SIDECAR_SUPPRESSED",
            "trigger_event": trigger_event,
            "reason_codes": [f"trigger:{trigger_event.lower()}", "malformed_payload"],
            "position_snapshot": {},
            "feature_ref": {},
            "regime_ref": {},
            "freshness_snapshot": {},
            "suppression_reason": f"malformed_payload:{reason}",
            "score_snapshot": {},
        }
        self._publish("EVT:POSITION_POLICY_SIDECAR_SUPPRESSED", payload)
