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
    from ..flows.manage.fsm_manage import ManageFlowFSM
    from vfoundation.core.fsm_emit_compat import Message

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.position_policy_sidecar"
)

SIDECAR_VERSION = "1.0.0"
EVALUATION_MODE = "bounded_soft_close_policy"
POLICY_RECORD_KIND = "position_policy_sidecar"
ACTION_PACKAGE_VERSION = "phase2_action_package_v1"
CLOSE_REQUEST_EVENT_TYPE = "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED"
CLOSE_REQUEST_COMMAND_TOPIC = "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST"
IDLE_SUPPRESSION_HEARTBEAT_MS = 120_000
IDLE_SUPPRESSION_REASONS = frozenset(
    {
        "no_manage_flow_for_symbol",
        "manage_flow_has_no_active_lifecycle",
    }
)


@dataclass(frozen=True)
class PositionPolicyCloseRequest:
    """Bounded soft-close request object for EP-owned close translation."""

    ts_ms: int
    request_id: str
    trace_id: str
    symbol: str
    source_event_type: str = "POSITION_POLICY_SIDECAR_RECOMMENDED"
    event_type: str = CLOSE_REQUEST_EVENT_TYPE
    requested_action: str = "SOFT_CLOSE"
    requested_qty: Optional[str] = None
    target_mode: str = "symbol_current_net_only"
    policy_source: str = "position_policy_sidecar"
    action_package_version: str = ACTION_PACKAGE_VERSION
    allowed_action_scope: Dict[str, bool] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    score_snapshot: Dict[str, float] = field(default_factory=dict)
    position_snapshot: Dict[str, Any] = field(default_factory=dict)
    feature_ref: Dict[str, Any] = field(default_factory=dict)
    regime_ref: Dict[str, Any] = field(default_factory=dict)
    freshness_snapshot: Dict[str, Any] = field(default_factory=dict)
    fill_correlation: Dict[str, Any] = field(default_factory=dict)
    portfolio_correlation: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "ts_ms": int(self.ts_ms),
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "symbol": self.symbol,
            "source_event_type": self.source_event_type,
            "event_type": self.event_type,
            "requested_action": self.requested_action,
            "requested_qty": self.requested_qty,
            "target_mode": self.target_mode,
            "policy_source": self.policy_source,
            "action_package_version": self.action_package_version,
            "allowed_action_scope": dict(self.allowed_action_scope),
            "reason_codes": list(self.reason_codes),
            "score_snapshot": dict(self.score_snapshot),
            "position_snapshot": dict(self.position_snapshot),
            "feature_ref": dict(self.feature_ref),
            "regime_ref": dict(self.regime_ref),
            "freshness_snapshot": dict(self.freshness_snapshot),
            "fill_correlation": dict(self.fill_correlation),
            "portfolio_correlation": dict(self.portfolio_correlation),
        }


@dataclass
class _Envelope:
    payload: Dict[str, Any] = field(default_factory=dict)
    ts_ms: int = 0
    update_count: int = 0


@dataclass
class _ShadowPercentNotionalArmCandidateState:
    peak_edge_usd: float = 0.0
    is_armed: bool = False
    first_arm_ts_ms: Optional[int] = None


@dataclass
class _ShadowFeeAwareArmCandidateState:
    peak_edge_usd: float = 0.0
    is_armed: bool = False
    first_arm_ts_ms: Optional[int] = None
    has_emitted_arm_event: bool = False
    has_emitted_trigger_event: bool = False


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
    last_idle_suppression_signature: Optional[tuple] = None
    last_idle_suppression_emit_ts_ms: int = 0
    idle_suppression_dedup_count: int = 0
    last_recommendation_signature: Optional[tuple] = None
    last_recommendation_ts_ms: int = 0
    recommendation_dedup_suppressed_count: int = 0
    # R7A: Peak giveback state
    peak_edge_usd: float = 0.0
    is_armed: bool = False
    shadow_percent_notional_arm_states: Dict[str,
                                             _ShadowPercentNotionalArmCandidateState] = field(default_factory=dict)
    shadow_fee_aware_arm_states: Dict[str,
                                      _ShadowFeeAwareArmCandidateState] = field(default_factory=dict)


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
        lifecycle_fee_getter: Optional[Callable[[
            str], Optional[float]]] = None,
    ) -> None:
        self.config = config
        self.mode = config.mode
        self._bus = bus
        self._manage_flow_getter = manage_flow_getter
        self._known_symbols_getter = known_symbols_getter
        self._lifecycle_fee_getter = lifecycle_fee_getter or (
            lambda _symbol: None)
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
            "sidecar_config_snapshot": self._sidecar_config_snapshot(),
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
            state.last_recommendation_signature = None
            state.recommendation_dedup_suppressed_count = 0
            # R7A: Reset peak giveback state on new entry
            state.peak_edge_usd = 0.0
            state.is_armed = False
            # R7O: Shadow candidate state must not leak across lifecycles.
            state.shadow_percent_notional_arm_states = {}
            state.shadow_fee_aware_arm_states = {}
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

        # R7A: Peak giveback evaluation
        # We allow peak giveback to trigger even if profitable_guard is active,
        # but NOT if other critical suppressions are active (e.g. stale data, close-in-progress).
        giveback_trigger: Optional[Dict[str, Any]] = None
        if suppression is None or suppression.get("reason_code") == "profitable_guard":
            giveback_trigger = self._evaluate_peak_giveback(
                symbol=symbol,
                state=state,
                position_snapshot=base_payload["position_snapshot"],
            )
            if giveback_trigger:
                base_payload["peak_giveback_snapshot"] = self._peak_giveback_snapshot(
                    state=state,
                    position_snapshot=base_payload["position_snapshot"],
                    freshness_snapshot=base_payload["freshness_snapshot"],
                    suppression=suppression,
                    giveback_result=giveback_trigger,
                )
                base_payload["reason_codes"] = self._merged_reason_codes(
                    base_payload.get("reason_codes", []),
                    base_payload["peak_giveback_snapshot"].get(
                        "reason_codes", []),
                )
                self._handle_peak_giveback_trigger(
                    symbol=symbol,
                    state=state,
                    base_payload=base_payload,
                    giveback_result=giveback_trigger,
                    trigger_event=trigger_event,
                )
                return

        base_payload["peak_giveback_snapshot"] = self._peak_giveback_snapshot(
            state=state,
            position_snapshot=base_payload["position_snapshot"],
            freshness_snapshot=base_payload["freshness_snapshot"],
            suppression=suppression,
            giveback_result=giveback_trigger,
        )
        base_payload["reason_codes"] = self._merged_reason_codes(
            base_payload.get("reason_codes", []),
            base_payload["peak_giveback_snapshot"].get("reason_codes", []),
        )

        # R7T: Emit shadow standalone events for fee-aware candidate state transitions
        fee_aware_snapshot = base_payload["peak_giveback_snapshot"].get("peak_giveback_shadow_arms", {}).get("fee_aware", {})
        if fee_aware_snapshot.get("enabled"):
            for candidate in fee_aware_snapshot.get("candidates", []):
                fee_multiple_value = candidate.get("fee_multiple")
                optional_pct_floor = candidate.get("optional_pct_floor")
                optional_pct_floor_val = optional_pct_floor.get("candidate_pct") if optional_pct_floor else None
                
                c_state = self._shadow_fee_aware_candidate_state(
                    state=state,
                    fee_multiple=fee_multiple_value,
                    optional_pct_floor=optional_pct_floor_val,
                )
                
                transitions = []
                if candidate.get("is_armed") and not getattr(c_state, "has_emitted_arm_event", False):
                    transitions.append("ARMED")
                    c_state.has_emitted_arm_event = True
                
                if candidate.get("would_trigger") and not getattr(c_state, "has_emitted_trigger_event", False):
                    transitions.append("TRIGGERED")
                    c_state.has_emitted_trigger_event = True
                
                if transitions:
                    shadow_payload = {
                        "ts_ms": now_ms,
                        "trace_id": base_payload["trace_id"],
                        "symbol": symbol,
                        "sidecar_version": base_payload["sidecar_version"],
                        "event_type": "POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE",
                        "reason_codes": [f"shadow_fee_aware_{t.lower()}" for t in transitions],
                        "shadow_only": True,
                        "authority_applied": False,
                        "no_effect": True,
                        "trigger_event": trigger_event,
                        "transitions": transitions,
                        "candidate_state": candidate,
                        "position_snapshot": base_payload["position_snapshot"],
                    }
                    self._publish("EVT:POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE", shadow_payload)

        if suppression is not None:
            payload = dict(base_payload)
            payload["event_type"] = "POSITION_POLICY_SIDECAR_SUPPRESSED"
            payload["reason_codes"] = self._merged_reason_codes(
                payload.get("reason_codes", []),
                [suppression["reason_code"]],
            )
            payload["suppression_reason"] = suppression["suppression_reason"]
            payload["incumbent_owner"] = suppression.get("incumbent_owner")
            payload["score_snapshot"] = suppression.get("score_snapshot", {})
            state.last_suppression_reason = suppression["suppression_reason"]
            if not self._should_publish_idle_suppression(
                state=state,
                now_ms=now_ms,
                payload=payload,
            ):
                return
            self._publish("EVT:POSITION_POLICY_SIDECAR_SUPPRESSED", payload)
            return

        self._reset_idle_suppression_dedup(state)
        score_snapshot = self._compute_scores(
            state=state, manage_flow=manage_flow)
        state.last_evaluation_ts_ms = now_ms

        scores_payload = dict(base_payload)
        scores_payload["event_type"] = "POSITION_POLICY_SIDECAR_SCORES"
        scores_payload["reason_codes"] = self._merged_reason_codes(
            scores_payload.get("reason_codes", []),
            ["scores_computed"],
        )
        scores_payload["score_snapshot"] = score_snapshot
        self._publish("EVT:POSITION_POLICY_SIDECAR_SCORES", scores_payload)

        evaluated_payload = dict(base_payload)
        evaluated_payload["event_type"] = "POSITION_POLICY_SIDECAR_EVALUATED"
        evaluated_payload["reason_codes"] = self._merged_reason_codes(
            evaluated_payload.get("reason_codes", []),
            ["evaluation_completed"],
        )
        evaluated_payload["score_snapshot"] = score_snapshot
        self._publish("EVT:POSITION_POLICY_SIDECAR_EVALUATED",
                      evaluated_payload)

        if score_snapshot["soft_close_pressure"] < self.config.thresholds.recommend_soft_close_at:
            return

        position_snapshot = base_payload["position_snapshot"]
        fill_correlation = base_payload["fill_correlation"]
        signature = self._recommendation_signature(
            score_snapshot=score_snapshot,
            position_snapshot=position_snapshot,
            fill_correlation=fill_correlation,
        )

        if state.last_recommendation_signature == signature:
            state.recommendation_dedup_suppressed_count += 1
            dedup_payload = dict(base_payload)
            dedup_payload["event_type"] = "POSITION_POLICY_SIDECAR_SUPPRESSED"
            dedup_payload["reason_codes"] = self._merged_reason_codes(
                dedup_payload.get("reason_codes", []),
                ["recommendation_duplicate_same_state"],
            )
            dedup_payload["suppression_reason"] = "recommendation_duplicate_same_state"
            dedup_payload["score_snapshot"] = score_snapshot
            dedup_payload["dedup_detail"] = {
                "suppressed_count": state.recommendation_dedup_suppressed_count,
                "last_recommendation_ts_ms": state.last_recommendation_ts_ms,
                "signature_fields": list(signature),
            }
            state.last_suppression_reason = "recommendation_duplicate_same_state"
            self._publish(
                "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED", dedup_payload)
            return

        state.last_recommendation_signature = signature
        state.last_recommendation_ts_ms = now_ms
        state.recommendation_dedup_suppressed_count = 0

        recommended_payload = dict(base_payload)
        recommended_payload["event_type"] = "POSITION_POLICY_SIDECAR_RECOMMENDED"
        recommended_payload["reason_codes"] = self._merged_reason_codes(
            recommended_payload.get("reason_codes", []),
            ["recommend_soft_close_threshold_met"],
        )
        recommended_payload["policy_source"] = "position_policy_sidecar"
        recommended_payload["score_snapshot"] = score_snapshot
        self._publish("EVT:POSITION_POLICY_SIDECAR_RECOMMENDED",
                      recommended_payload)

        if self.mode == PositionPolicySidecarMode.ENABLE:
            close_request = self.position_policy_close_request_type(
                ts_ms=now_ms,
                request_id=f"ppsreq:{trace_id}",
                trace_id=trace_id,
                symbol=symbol,
                allowed_action_scope=self._allowed_action_scope(),
                reason_codes=tuple(recommended_payload["reason_codes"]),
                score_snapshot=dict(score_snapshot),
                position_snapshot=dict(
                    recommended_payload["position_snapshot"]),
                feature_ref=dict(recommended_payload["feature_ref"]),
                regime_ref=dict(recommended_payload["regime_ref"]),
                freshness_snapshot=dict(
                    recommended_payload["freshness_snapshot"]),
                fill_correlation=dict(recommended_payload["fill_correlation"]),
                portfolio_correlation=dict(
                    recommended_payload["portfolio_correlation"]),
            )
            request_payload = dict(recommended_payload)
            request_payload.update(close_request.to_payload())
            self._publish(CLOSE_REQUEST_COMMAND_TOPIC, request_payload)

    def _evaluate_peak_giveback(
        self,
        symbol: str,
        state: _SymbolState,
        position_snapshot: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """R7A: Evaluate whether the position gave back too much from peak edge."""
        cfg = self.config.peak_giveback_close
        if not cfg.enabled:
            return None

        pnl_usdt = _coerce_float(position_snapshot.get("unrealized_pnl_usdt"))
        if pnl_usdt is None:
            return None

        # Update peak edge (only if profitable)
        if pnl_usdt > state.peak_edge_usd:
            state.peak_edge_usd = pnl_usdt

        # Arm if threshold reached
        if not state.is_armed and state.peak_edge_usd >= cfg.edge_arm_usd:
            state.is_armed = True
            LOG.info(
                "[%s] Sidecar peak-giveback ARMED: peak=%.2f arm=%.2f",
                symbol, state.peak_edge_usd, cfg.edge_arm_usd
            )

        if not state.is_armed:
            return None

        # Trigger check: compute giveback from peak
        # Only trigger if peak edge is meaningful
        if state.peak_edge_usd <= 0:
            return None

        giveback_usd = state.peak_edge_usd - pnl_usdt
        giveback_pct = (giveback_usd / state.peak_edge_usd) * 100.0

        if giveback_pct >= cfg.giveback_trigger_pct:
            return {
                "peak_edge_usd": float(state.peak_edge_usd),
                "current_edge_usd": float(pnl_usdt),
                "giveback_pct": float(giveback_pct),
                "threshold_pct": float(cfg.giveback_trigger_pct),
            }

        return None

    def _handle_peak_giveback_trigger(
        self,
        *,
        symbol: str,
        state: _SymbolState,
        base_payload: Dict[str, Any],
        giveback_result: Dict[str, Any],
        trigger_event: str,
    ) -> None:
        """Initiate bounded soft-close request after peak giveback trigger."""
        now_ms = get_clock().now_ms()
        trace_id = base_payload["trace_id"]

        # 1. Log recommendation
        recommended_payload = dict(base_payload)
        recommended_payload["event_type"] = "POSITION_POLICY_SIDECAR_RECOMMENDED"
        recommended_payload["reason_codes"] = self._merged_reason_codes(
            recommended_payload.get("reason_codes", []),
            ["peak_giveback_threshold_met"],
        )
        recommended_payload["policy_source"] = "position_policy_sidecar:peak_giveback"
        recommended_payload["peak_giveback_detail"] = giveback_result
        # Synthetic score for traceability
        recommended_payload["score_snapshot"] = {
            "soft_close_pressure": 1.0,
            "peak_edge_usd": giveback_result["peak_edge_usd"],
            "current_edge_usd": giveback_result["current_edge_usd"],
            "giveback_pct": giveback_result["giveback_pct"],
            "giveback_trigger_pct": giveback_result["threshold_pct"],
        }
        self._publish("EVT:POSITION_POLICY_SIDECAR_RECOMMENDED",
                      recommended_payload)

        # 2. Emit action command if enabled
        if self.mode == PositionPolicySidecarMode.ENABLE:
            close_request = self.position_policy_close_request_type(
                ts_ms=now_ms,
                request_id=f"ppsreq:{trace_id}",
                trace_id=trace_id,
                symbol=symbol,
                allowed_action_scope=self._allowed_action_scope(),
                reason_codes=tuple(recommended_payload["reason_codes"]),
                requested_action="SOFT_CLOSE",
                policy_source="position_policy_sidecar:peak_giveback",
                score_snapshot=dict(recommended_payload["score_snapshot"]),
                position_snapshot=dict(base_payload["position_snapshot"]),
                feature_ref=dict(base_payload["feature_ref"]),
                regime_ref=dict(base_payload["regime_ref"]),
                freshness_snapshot=dict(base_payload["freshness_snapshot"]),
                fill_correlation=dict(base_payload["fill_correlation"]),
                portfolio_correlation=dict(
                    base_payload["portfolio_correlation"]),
            )
            request_payload = dict(recommended_payload)
            request_payload.update(close_request.to_payload())
            self._publish(CLOSE_REQUEST_COMMAND_TOPIC, request_payload)

            # 3. Reset state to avoid repeated emission for the same lifecycle
            state.is_armed = False
            state.peak_edge_usd = 0.0

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

    def _recommendation_signature(
        self,
        *,
        score_snapshot: Dict[str, float],
        position_snapshot: Dict[str, Any],
        fill_correlation: Dict[str, Any],
    ) -> tuple:
        """Build a hashable state-signature for recommendation dedup.

        Two evaluations with the same signature in the same lifecycle
        represent no meaningful state change and the second should be
        suppressed as a duplicate.
        """
        return (
            round(score_snapshot.get("soft_close_pressure", 0.0), 4),
            position_snapshot.get("manage_state"),
            position_snapshot.get("side"),
            position_snapshot.get("position_qty"),
            str(position_snapshot.get("portfolio_position_amt")),
            fill_correlation.get("canonical_fill_trace_id"),
        )

    @staticmethod
    def _reset_idle_suppression_dedup(state: _SymbolState) -> None:
        state.last_idle_suppression_signature = None
        state.last_idle_suppression_emit_ts_ms = 0
        state.idle_suppression_dedup_count = 0

    def _should_publish_idle_suppression(
        self,
        *,
        state: _SymbolState,
        now_ms: int,
        payload: Dict[str, Any],
    ) -> bool:
        """Rate-limit unchanged no-position telemetry while preserving transitions."""
        reason = str(payload.get("suppression_reason") or "")
        if reason not in IDLE_SUPPRESSION_REASONS:
            self._reset_idle_suppression_dedup(state)
            return True

        position = payload.get("position_snapshot") or {}
        fill = payload.get("fill_correlation") or {}
        signature = (
            reason,
            position.get("manage_state"),
            position.get("side"),
            str(position.get("position_qty") or ""),
            str(position.get("portfolio_position_amt")),
            position.get("portfolio_snapshot_status"),
            position.get("portfolio_symbol_present"),
            fill.get("canonical_fill_trace_id"),
        )
        elapsed_ms = now_ms - state.last_idle_suppression_emit_ts_ms
        if (
            signature == state.last_idle_suppression_signature
            and state.last_idle_suppression_emit_ts_ms > 0
            and elapsed_ms < IDLE_SUPPRESSION_HEARTBEAT_MS
        ):
            state.idle_suppression_dedup_count += 1
            return False

        if state.idle_suppression_dedup_count > 0:
            payload["dedup_detail"] = {
                "suppressed_count": state.idle_suppression_dedup_count,
                "heartbeat_ms": IDLE_SUPPRESSION_HEARTBEAT_MS,
                "last_emit_ts_ms": state.last_idle_suppression_emit_ts_ms,
            }
        state.last_idle_suppression_signature = signature
        state.last_idle_suppression_emit_ts_ms = now_ms
        state.idle_suppression_dedup_count = 0
        return True

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

    def _sidecar_config_snapshot(self) -> Dict[str, Any]:
        source_config_path = self._config_source_path()
        return {
            "mode": self.mode.value,
            "peak_giveback_close": {
                "enabled": self.config.peak_giveback_close.enabled,
                "edge_arm_usd": float(self.config.peak_giveback_close.edge_arm_usd),
                "giveback_trigger_pct": float(self.config.peak_giveback_close.giveback_trigger_pct),
            },
            "shadow_percent_notional_arm": {
                "enabled": self.config.shadow_percent_notional_arm.enabled,
                "candidate_pcts": [
                    float(candidate)
                    for candidate in self.config.shadow_percent_notional_arm.candidate_pcts
                ],
                "candidate_unit": "percent",
            },
            "shadow_fee_aware_arm": {
                "enabled": self.config.shadow_fee_aware_arm.enabled,
                "fee_source_priority": [
                    getattr(source, "value", str(source))
                    for source in self.config.shadow_fee_aware_arm.fee_source_priority
                ],
                "candidate_fee_multiples": [
                    float(candidate)
                    for candidate in self.config.shadow_fee_aware_arm.candidate_fee_multiples
                ],
                "configured_fee_model": {
                    "enabled": self.config.shadow_fee_aware_arm.configured_fee_model.enabled,
                    "round_trip_fee_bps": _coerce_float(
                        self.config.shadow_fee_aware_arm.configured_fee_model.round_trip_fee_bps
                    ),
                },
                "optional_pct_notional_floor": {
                    "enabled": self.config.shadow_fee_aware_arm.optional_pct_notional_floor.enabled,
                    "candidate_unit": "percent",
                    "candidate_pcts": [
                        float(candidate)
                        for candidate in self.config.shadow_fee_aware_arm.optional_pct_notional_floor.candidate_pcts
                    ],
                },
            },
            "freshness": {
                "portfolio_max_age_ms": self.config.freshness.portfolio_max_age_ms,
                "features_max_age_ms": self.config.freshness.features_max_age_ms,
                "regime_max_age_ms": self.config.freshness.regime_max_age_ms,
                "order_state_max_age_ms": self.config.freshness.order_state_max_age_ms,
            },
            "source_config_path": source_config_path,
        }

    def _shadow_percent_notional_candidate_state(
        self,
        *,
        state: _SymbolState,
        candidate_pct: float,
    ) -> _ShadowPercentNotionalArmCandidateState:
        state_key = f"{float(candidate_pct):.8f}"
        if state_key not in state.shadow_percent_notional_arm_states:
            state.shadow_percent_notional_arm_states[state_key] = _ShadowPercentNotionalArmCandidateState(
            )
        return state.shadow_percent_notional_arm_states[state_key]

    def _shadow_percent_notional_snapshot(
        self,
        *,
        state: _SymbolState,
        position_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        cfg = self.config.shadow_percent_notional_arm
        percent_notional: Dict[str, Any] = {
            "enabled": bool(cfg.enabled),
            "candidate_unit": "percent",
            "giveback_trigger_pct": float(self.config.peak_giveback_close.giveback_trigger_pct),
            "candidates": [],
        }

        candidate_pcts = [float(candidate)
                          for candidate in cfg.candidate_pcts]
        current_edge_usd = _coerce_float(
            position_snapshot.get("unrealized_pnl_usdt"))

        entry_price = _coerce_float(position_snapshot.get("entry_price"))
        if entry_price is None:
            entry_price = _coerce_float(
                position_snapshot.get("portfolio_entry_price"))

        position_qty = _coerce_float(position_snapshot.get("position_qty"))
        if position_qty is None:
            portfolio_position_amt = _coerce_float(
                position_snapshot.get("portfolio_position_amt"))
            if portfolio_position_amt is not None:
                position_qty = abs(portfolio_position_amt)

        notional_usdt: Optional[float] = None
        if current_edge_usd is not None and entry_price is not None and position_qty is not None:
            computed_notional = abs(position_qty) * entry_price
            if computed_notional > 0.0:
                notional_usdt = computed_notional

        if not cfg.enabled:
            percent_notional["null_reason"] = "shadow_percent_notional_arm_disabled"
        elif current_edge_usd is None:
            percent_notional["null_reason"] = "missing_unrealized_pnl_usdt"
        elif notional_usdt is None:
            percent_notional["null_reason"] = "missing_position_notional_usdt"

        now_ms = get_clock().now_ms()
        for candidate_pct in candidate_pcts:
            candidate_state = self._shadow_percent_notional_candidate_state(
                state=state,
                candidate_pct=candidate_pct,
            )

            candidate_null_reasons: Dict[str, str] = {}
            arm_threshold_usd: Optional[float] = None
            if notional_usdt is None:
                candidate_null_reasons["arm_threshold_usd"] = "missing_position_notional_usdt"
            else:
                arm_threshold_usd = (notional_usdt * candidate_pct) / 100.0

            if (
                cfg.enabled
                and current_edge_usd is not None
                and current_edge_usd > candidate_state.peak_edge_usd
            ):
                candidate_state.peak_edge_usd = float(current_edge_usd)

            if (
                cfg.enabled
                and arm_threshold_usd is not None
                and not candidate_state.is_armed
                and candidate_state.peak_edge_usd >= arm_threshold_usd
            ):
                candidate_state.is_armed = True
                if candidate_state.first_arm_ts_ms is None:
                    candidate_state.first_arm_ts_ms = int(now_ms)

            giveback_pct: Optional[float] = None
            if current_edge_usd is None:
                candidate_null_reasons["giveback_pct"] = "missing_unrealized_pnl_usdt"
            elif candidate_state.peak_edge_usd > 0.0:
                giveback_pct = (
                    (candidate_state.peak_edge_usd - current_edge_usd)
                    / candidate_state.peak_edge_usd
                ) * 100.0
            else:
                candidate_null_reasons["giveback_pct"] = "peak_edge_not_positive"

            threshold_met: Optional[bool] = None
            if not cfg.enabled:
                candidate_null_reasons["threshold_met_under_current_giveback_trigger_pct"] = "shadow_percent_notional_arm_disabled"
            elif current_edge_usd is None:
                candidate_null_reasons["threshold_met_under_current_giveback_trigger_pct"] = "missing_unrealized_pnl_usdt"
            elif notional_usdt is None:
                candidate_null_reasons["threshold_met_under_current_giveback_trigger_pct"] = "missing_position_notional_usdt"
            elif not candidate_state.is_armed:
                threshold_met = False
            elif giveback_pct is None:
                candidate_null_reasons["threshold_met_under_current_giveback_trigger_pct"] = "missing_giveback_pct"
            else:
                threshold_met = (
                    giveback_pct >= self.config.peak_giveback_close.giveback_trigger_pct
                )

            if not cfg.enabled:
                candidate_state_label = "shadow_percent_notional_disabled"
            elif current_edge_usd is None:
                candidate_state_label = "shadow_percent_notional_unavailable_economics_missing"
            elif notional_usdt is None:
                candidate_state_label = "shadow_percent_notional_unavailable_notional_missing"
            elif not candidate_state.is_armed:
                candidate_state_label = "shadow_percent_notional_not_armed_below_edge"
            elif threshold_met:
                candidate_state_label = "shadow_percent_notional_threshold_met"
            else:
                candidate_state_label = "shadow_percent_notional_below_trigger"

            percent_notional["candidates"].append(
                {
                    "candidate_pct": float(candidate_pct),
                    "arm_threshold_usd": arm_threshold_usd,
                    "is_armed": bool(candidate_state.is_armed),
                    "first_arm_ts_ms": candidate_state.first_arm_ts_ms,
                    "peak_edge_usd": float(candidate_state.peak_edge_usd),
                    "giveback_pct": giveback_pct,
                    "threshold_met_under_current_giveback_trigger_pct": threshold_met,
                    "would_trigger": threshold_met,
                    "state": candidate_state_label,
                    "null_reasons": candidate_null_reasons,
                }
            )

        return {"percent_notional": percent_notional}

    def _shadow_fee_aware_candidate_state(
        self,
        *,
        state: _SymbolState,
        fee_multiple: float,
        optional_pct_floor: Optional[float],
    ) -> _ShadowFeeAwareArmCandidateState:
        optional_pct_key = "none" if optional_pct_floor is None else f"{float(optional_pct_floor):.8f}"
        state_key = f"{float(fee_multiple):.8f}:{optional_pct_key}"
        if state_key not in state.shadow_fee_aware_arm_states:
            state.shadow_fee_aware_arm_states[state_key] = _ShadowFeeAwareArmCandidateState(
            )
        return state.shadow_fee_aware_arm_states[state_key]

    def _position_notional_usdt(self, position_snapshot: Dict[str, Any]) -> Optional[float]:
        entry_price = _coerce_float(position_snapshot.get("entry_price"))
        if entry_price is None:
            entry_price = _coerce_float(
                position_snapshot.get("portfolio_entry_price"))

        position_qty = _coerce_float(position_snapshot.get("position_qty"))
        if position_qty is None:
            portfolio_position_amt = _coerce_float(
                position_snapshot.get("portfolio_position_amt"))
            if portfolio_position_amt is not None:
                position_qty = abs(portfolio_position_amt)

        if entry_price is None or position_qty is None:
            return None

        notional_usdt = abs(position_qty) * entry_price
        if notional_usdt <= 0.0:
            return None
        return float(notional_usdt)

    def _resolve_fee_aware_source(
        self,
        *,
        symbol: str,
        state: _SymbolState,
        position_notional_usdt: Optional[float],
    ) -> tuple[Optional[float], Optional[str], str, Dict[str, str]]:
        cfg = self.config.shadow_fee_aware_arm
        null_reasons: Dict[str, str] = {}

        for source in cfg.fee_source_priority:
            source_name = getattr(source, "value", str(source))

            if source_name == "realized_lifecycle_fee":
                lifecycle_fee = _coerce_float(
                    self._lifecycle_fee_getter(symbol))
                if lifecycle_fee is None:
                    null_reasons[source_name] = "missing_observed_lifecycle_fee"
                    continue
                if lifecycle_fee < 0.0:
                    null_reasons[source_name] = "invalid_observed_lifecycle_fee"
                    continue
                return (
                    float(lifecycle_fee),
                    source_name,
                    "observed_symbol_lifecycle_fee",
                    null_reasons,
                )

            if source_name == "order_log_fee":
                order_log_fee = _lookup_nested_numeric(
                    state.last_fill.payload,
                    ("fill_fees", "fees", "commission"),
                )
                if order_log_fee is None:
                    null_reasons[source_name] = "missing_order_log_fee"
                    continue
                if order_log_fee < 0.0:
                    null_reasons[source_name] = "invalid_order_log_fee"
                    continue
                return (
                    float(order_log_fee),
                    source_name,
                    "observed_order_fill_fee",
                    null_reasons,
                )

            if source_name == "configured_fee_model":
                configured_fee_model = cfg.configured_fee_model
                if not configured_fee_model.enabled:
                    null_reasons[source_name] = "configured_fee_model_disabled"
                    continue
                if position_notional_usdt is None:
                    null_reasons[source_name] = "missing_position_notional_usdt"
                    continue
                round_trip_fee_bps = _coerce_float(
                    configured_fee_model.round_trip_fee_bps)
                if round_trip_fee_bps is None:
                    null_reasons[source_name] = "missing_configured_round_trip_fee_bps"
                    continue
                if round_trip_fee_bps < 0.0:
                    null_reasons[source_name] = "invalid_configured_round_trip_fee_bps"
                    continue
                return (
                    float(position_notional_usdt *
                          (round_trip_fee_bps / 10000.0)),
                    source_name,
                    "configured_round_trip_bps_model",
                    null_reasons,
                )

            null_reasons[source_name] = "unsupported_fee_source"

        return None, None, "unavailable", null_reasons

    def _shadow_fee_aware_snapshot(
        self,
        *,
        state: _SymbolState,
        position_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        cfg = self.config.shadow_fee_aware_arm
        fee_aware: Dict[str, Any] = {
            "enabled": bool(cfg.enabled),
            "fee_source_priority": [
                getattr(source, "value", str(source)) for source in cfg.fee_source_priority
            ],
            "candidate_fee_multiples": [
                float(candidate) for candidate in cfg.candidate_fee_multiples
            ],
            "giveback_trigger_pct": float(self.config.peak_giveback_close.giveback_trigger_pct),
            "optional_pct_notional_floor": {
                "enabled": bool(cfg.optional_pct_notional_floor.enabled),
                "candidate_unit": "percent",
                "candidate_pcts": [
                    float(candidate) for candidate in cfg.optional_pct_notional_floor.candidate_pcts
                ],
            },
            "candidates": [],
        }

        current_edge_usd = _coerce_float(
            position_snapshot.get("unrealized_pnl_usdt"))
        position_notional_usdt = self._position_notional_usdt(
            position_snapshot)
        symbol = _normalize_symbol(position_snapshot.get("symbol"))
        estimated_fee_usd, fee_source, fee_source_confidence, source_null_reasons = self._resolve_fee_aware_source(
            symbol=symbol,
            state=state,
            position_notional_usdt=position_notional_usdt,
        )

        if not cfg.enabled:
            fee_aware["null_reason"] = "shadow_fee_aware_arm_disabled"
        elif current_edge_usd is None:
            fee_aware["null_reason"] = "missing_unrealized_pnl_usdt"
        elif estimated_fee_usd is None:
            fee_aware["null_reason"] = "missing_fee_source"

        optional_pct_candidates: list[Optional[float]]
        if cfg.optional_pct_notional_floor.enabled:
            optional_pct_candidates = [
                float(candidate) for candidate in cfg.optional_pct_notional_floor.candidate_pcts
            ]
        else:
            optional_pct_candidates = [None]

        now_ms = get_clock().now_ms()
        for fee_multiple in cfg.candidate_fee_multiples:
            fee_multiple_value = float(fee_multiple)
            for optional_pct_floor in optional_pct_candidates:
                candidate_state = self._shadow_fee_aware_candidate_state(
                    state=state,
                    fee_multiple=fee_multiple_value,
                    optional_pct_floor=optional_pct_floor,
                )

                candidate_null_reasons = dict(source_null_reasons)
                fee_floor_required_edge: Optional[float] = None
                optional_pct_required_edge: Optional[float] = None
                optional_pct_floor_payload: Optional[Dict[str, Any]] = None

                if estimated_fee_usd is None:
                    candidate_null_reasons["estimated_fee_usd"] = "missing_fee_source"
                    candidate_null_reasons["required_edge_usd"] = "missing_fee_source"
                else:
                    fee_floor_required_edge = float(
                        estimated_fee_usd) * fee_multiple_value

                if optional_pct_floor is not None:
                    if position_notional_usdt is None:
                        candidate_null_reasons["optional_pct_floor.required_edge_usd"] = "missing_position_notional_usdt"
                    else:
                        optional_pct_required_edge = (
                            position_notional_usdt * optional_pct_floor) / 100.0
                    optional_pct_floor_payload = {
                        "candidate_pct": float(optional_pct_floor),
                        "required_edge_usd": optional_pct_required_edge,
                    }

                required_edge_usd: Optional[float] = None
                if fee_floor_required_edge is not None:
                    required_edge_usd = fee_floor_required_edge
                    if optional_pct_required_edge is not None:
                        required_edge_usd = max(
                            required_edge_usd, optional_pct_required_edge)

                if cfg.enabled and current_edge_usd is not None and current_edge_usd > candidate_state.peak_edge_usd:
                    candidate_state.peak_edge_usd = float(current_edge_usd)

                if (
                    cfg.enabled
                    and required_edge_usd is not None
                    and not candidate_state.is_armed
                    and candidate_state.peak_edge_usd >= required_edge_usd
                ):
                    candidate_state.is_armed = True
                    if candidate_state.first_arm_ts_ms is None:
                        candidate_state.first_arm_ts_ms = int(now_ms)

                giveback_pct: Optional[float] = None
                if current_edge_usd is None:
                    candidate_null_reasons["giveback_pct"] = "missing_unrealized_pnl_usdt"
                elif candidate_state.peak_edge_usd > 0.0:
                    giveback_pct = (
                        (candidate_state.peak_edge_usd - current_edge_usd)
                        / candidate_state.peak_edge_usd
                    ) * 100.0
                else:
                    candidate_null_reasons["giveback_pct"] = "peak_edge_not_positive"

                threshold_met: Optional[bool] = None
                if not cfg.enabled:
                    candidate_null_reasons["would_trigger_under_current_giveback_trigger_pct"] = "shadow_fee_aware_arm_disabled"
                elif current_edge_usd is None:
                    candidate_null_reasons["would_trigger_under_current_giveback_trigger_pct"] = "missing_unrealized_pnl_usdt"
                elif estimated_fee_usd is None:
                    candidate_null_reasons["would_trigger_under_current_giveback_trigger_pct"] = "missing_fee_source"
                elif required_edge_usd is None:
                    candidate_null_reasons["would_trigger_under_current_giveback_trigger_pct"] = "required_edge_not_computable"
                elif not candidate_state.is_armed:
                    threshold_met = False
                elif giveback_pct is None:
                    candidate_null_reasons["would_trigger_under_current_giveback_trigger_pct"] = "missing_giveback_pct"
                else:
                    threshold_met = (
                        giveback_pct >= self.config.peak_giveback_close.giveback_trigger_pct
                    )

                if not cfg.enabled:
                    candidate_state_label = "shadow_fee_aware_disabled"
                elif current_edge_usd is None:
                    candidate_state_label = "shadow_fee_aware_unavailable_economics_missing"
                elif estimated_fee_usd is None:
                    candidate_state_label = "shadow_fee_aware_unavailable_fee_missing"
                elif not candidate_state.is_armed:
                    candidate_state_label = "shadow_fee_aware_not_armed_below_edge"
                elif threshold_met:
                    candidate_state_label = "shadow_fee_aware_threshold_met"
                else:
                    candidate_state_label = "shadow_fee_aware_below_trigger"

                fee_aware["candidates"].append(
                    {
                        "fee_multiple": fee_multiple_value,
                        "estimated_fee_usd": estimated_fee_usd,
                        "fee_source": fee_source,
                        "fee_source_confidence": fee_source_confidence,
                        "optional_pct_floor": optional_pct_floor_payload,
                        "required_edge_usd": required_edge_usd,
                        "current_edge_usd": current_edge_usd,
                        "is_armed": bool(candidate_state.is_armed),
                        "first_arm_ts_ms": candidate_state.first_arm_ts_ms,
                        "peak_edge_usd": float(candidate_state.peak_edge_usd),
                        "giveback_pct": giveback_pct,
                        "would_trigger_under_current_giveback_trigger_pct": threshold_met,
                        "would_trigger": threshold_met,
                        "state": candidate_state_label,
                        "null_reasons": candidate_null_reasons,
                    }
                )

        return {"fee_aware": fee_aware}

    def _config_source_path(self) -> Optional[str]:
        for attr in (
            "source_config_path",
            "config_source_path",
            "_source_config_path",
            "__config_source_path__",
        ):
            value = _coerce_str(getattr(self.config, attr, None))
            if value is not None:
                return value
        return None

    def _peak_giveback_snapshot(
        self,
        *,
        state: _SymbolState,
        position_snapshot: Dict[str, Any],
        freshness_snapshot: Dict[str, Any],
        suppression: Optional[Dict[str, Any]],
        giveback_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        cfg = self.config.peak_giveback_close
        null_reasons: Dict[str, str] = {}

        mark_price = _coerce_float(position_snapshot.get("mark_price"))
        if mark_price is None:
            null_reasons["mark_price"] = "missing_mark_price"

        entry_price = _coerce_float(position_snapshot.get("entry_price"))
        if entry_price is None:
            entry_price = _coerce_float(
                position_snapshot.get("portfolio_entry_price"))
        if entry_price is None:
            null_reasons["entry_price"] = "missing_entry_price"

        position_qty = _coerce_float(position_snapshot.get("position_qty"))
        if position_qty is None:
            portfolio_position_amt = _coerce_float(
                position_snapshot.get("portfolio_position_amt")
            )
            if portfolio_position_amt is not None:
                position_qty = abs(portfolio_position_amt)
        if position_qty is None:
            null_reasons["position_qty"] = "missing_position_qty"

        side = _coerce_str(position_snapshot.get("side"))
        if side is None:
            null_reasons["side"] = "missing_position_side"

        unrealized_pnl_usdt = _coerce_float(
            position_snapshot.get("unrealized_pnl_usdt"))
        if unrealized_pnl_usdt is None:
            null_reasons["unrealized_pnl_usdt"] = "missing_unrealized_pnl_usdt"

        unrealized_pnl_pct = _coerce_float(
            position_snapshot.get("unrealized_pnl_pct"))
        if unrealized_pnl_pct is None:
            null_reasons["unrealized_pnl_pct"] = "missing_unrealized_pnl_pct"

        current_edge_usd = unrealized_pnl_usdt
        if current_edge_usd is None:
            null_reasons["current_edge_usd"] = "missing_unrealized_pnl_usdt"

        peak_edge_usd = float(state.peak_edge_usd)
        giveback_pct: Optional[float] = None
        if giveback_result is not None:
            giveback_pct = float(giveback_result["giveback_pct"])
        elif current_edge_usd is not None and peak_edge_usd > 0.0:
            giveback_pct = (
                (peak_edge_usd - current_edge_usd) / peak_edge_usd) * 100.0
        elif current_edge_usd is None:
            null_reasons["giveback_pct"] = "missing_current_edge_usd"
        else:
            null_reasons["giveback_pct"] = "peak_edge_not_positive"

        suppression_reason_code = suppression.get(
            "reason_code") if suppression is not None else None
        stale_reason_codes = {
            "portfolio_stale",
            "features_stale",
            "regime_stale",
            "portfolio_missing",
        }

        if not cfg.enabled:
            peak_giveback_state = "peak_giveback_disabled"
            peak_reason_codes = [peak_giveback_state]
        elif suppression_reason_code == "close_in_progress":
            peak_giveback_state = "peak_giveback_suppressed_close_in_progress"
            peak_reason_codes = [peak_giveback_state]
        elif suppression_reason_code in stale_reason_codes or (
            suppression_reason_code is None
            and (
                freshness_snapshot.get("portfolio_fresh") is False
                or freshness_snapshot.get("features_fresh") is False
                or freshness_snapshot.get("regime_fresh") is False
            )
        ):
            peak_giveback_state = "peak_giveback_suppressed_stale_inputs"
            peak_reason_codes = [peak_giveback_state]
        elif suppression_reason_code not in (None, "profitable_guard"):
            peak_giveback_state = "peak_giveback_not_ready"
            peak_reason_codes = [peak_giveback_state]
        elif giveback_result is not None:
            peak_giveback_state = "peak_giveback_threshold_met"
            peak_reason_codes = ["peak_giveback_armed", peak_giveback_state]
        elif unrealized_pnl_usdt is None:
            peak_giveback_state = "peak_giveback_unavailable_economics_missing"
            peak_reason_codes = [peak_giveback_state]
        elif state.is_armed:
            peak_giveback_state = "peak_giveback_below_trigger"
            peak_reason_codes = ["peak_giveback_armed", peak_giveback_state]
        else:
            peak_giveback_state = "peak_giveback_not_armed_below_edge"
            peak_reason_codes = [peak_giveback_state]

        threshold_crossed: Optional[bool]
        if giveback_result is not None:
            threshold_crossed = True
        elif giveback_pct is not None and cfg.enabled and state.is_armed:
            threshold_crossed = giveback_pct >= cfg.giveback_trigger_pct
        elif cfg.enabled and unrealized_pnl_usdt is not None and not state.is_armed:
            threshold_crossed = False
        else:
            threshold_crossed = None
            null_reasons["threshold_crossed"] = "threshold_not_evaluable"

        shadow_arms = self._shadow_percent_notional_snapshot(
            state=state,
            position_snapshot=position_snapshot,
        )
        shadow_arms.update(
            self._shadow_fee_aware_snapshot(
                state=state,
                position_snapshot=position_snapshot,
            )
        )

        return {
            "policy_enabled": cfg.enabled,
            "mark_price": mark_price,
            "entry_price": entry_price,
            "position_qty": position_qty,
            "side": side,
            "unrealized_pnl_usdt": unrealized_pnl_usdt,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "peak_edge_usd": peak_edge_usd,
            "current_edge_usd": current_edge_usd,
            "giveback_pct": giveback_pct,
            "is_armed": bool(state.is_armed),
            "arm_threshold_usd": float(cfg.edge_arm_usd),
            "giveback_trigger_pct": float(cfg.giveback_trigger_pct),
            "threshold_crossed": threshold_crossed,
            "peak_giveback_state": peak_giveback_state,
            "peak_giveback_shadow_arms": shadow_arms,
            "reason_codes": peak_reason_codes,
            "null_reasons": null_reasons,
        }

    def _merged_reason_codes(self, *groups: Iterable[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for reason_code in group:
                reason = str(reason_code or "").strip()
                if not reason or reason in seen:
                    continue
                merged.append(reason)
                seen.add(reason)
        return merged

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

    @property
    def position_policy_close_request_type(self) -> type[PositionPolicyCloseRequest]:
        return PositionPolicyCloseRequest

    def _allowed_action_scope(self) -> Dict[str, bool]:
        return {
            "soft_close_symbol_current_net_only": self.config.allowed_actions.soft_close_symbol_current_net_only,
            "partial_reduce": self.config.allowed_actions.partial_reduce,
            "bracket_mutation": self.config.allowed_actions.bracket_mutation,
            "exact_targeting": self.config.allowed_actions.exact_targeting,
        }

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
