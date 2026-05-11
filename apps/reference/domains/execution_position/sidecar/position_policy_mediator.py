from typing import TYPE_CHECKING, Any, Dict, Optional

from apps.reference.core.time import get_clock
from apps.reference.telemetry.trade_lifecycle_logger import (
    POSITION_POLICY_SIDECAR_RECORD_KIND,
    append_trade_lifecycle_record,
)
try:
    from ..telemetry.lifecycle_stats_ledger import ExecutionLifecycleStatsLedger
except ImportError:
    ExecutionLifecycleStatsLedger = None

from .position_policy_sidecar import (
    ACTION_PACKAGE_VERSION,
    CLOSE_REQUEST_COMMAND_TOPIC,
    PositionPolicyCloseRequest,
    PositionPolicySidecarConfig,
)
from ..state.truth_hardening import get_execution_truth_hardening
from vfoundation.core.fsm_emit_compat import Message

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM


class PositionPolicyMediator:
    """
    Downstream command-bridge contour for position policy sidecar recommendations.

    Acts as the admissibility gatekeeper, scope parser, and execution truth
    bridge translating sidecar evaluative signals safely into standard CMD:CLOSE requests
    while suppressing duplicates and natively tracking state requests.
    """

    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm
        self._position_policy_close_requests: Dict[str, Dict[str, Any]] = {}
        self.position_policy_close_request_type = PositionPolicyCloseRequest

    def _lifecycle_stats_ledger(self) -> Optional["ExecutionLifecycleStatsLedger"]:
        ledger = getattr(self._fsm, "_lifecycle_stats_ledger", None)
        if ledger is not None:
            return ledger
        if ExecutionLifecycleStatsLedger is None:
            return None
        try:
            ledger = ExecutionLifecycleStatsLedger()
        except Exception:
            return None
        setattr(self._fsm, "_lifecycle_stats_ledger", ledger)
        return ledger

    def _is_entry_order_ref(self, order_index: Any, ref: Any) -> bool:
        classifier = getattr(order_index, "_is_entry_ref", None)
        if callable(classifier):
            try:
                return bool(classifier(ref))
            except Exception:
                pass
        return str(getattr(ref, "order_kind", "") or "").strip().upper() == "ENTRY"

    def _recover_lifecycle_from_order_index(
        self,
        *,
        symbol: str,
        request_payload: Dict[str, Any],
        manage_flow: Any,
    ) -> str:
        order_index = getattr(self._fsm, "_order_index", None)
        if order_index is None or not hasattr(order_index, "get"):
            return ""

        fill_correlation = dict(request_payload.get("fill_correlation") or {})
        candidate_keys = (
            ("rid", fill_correlation.get("rid")),
            ("clientOrderId", fill_correlation.get("client_order_id")),
            ("exchangeOrderId", fill_correlation.get("order_id")),
            ("clientOrderId", getattr(manage_flow, "entry_client_order_id", None)),
            ("exchangeOrderId", getattr(manage_flow, "entry_order_id", None)),
        )
        seen: set[tuple[str, str]] = set()
        for lookup_key, raw_value in candidate_keys:
            lookup_value = str(raw_value or "").strip()
            if not lookup_value:
                continue
            candidate = (lookup_key, lookup_value)
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                ref = order_index.get(**{lookup_key: lookup_value})
            except Exception:
                ref = None
            if ref is None:
                continue
            ref_symbol = str(getattr(ref, "symbol", "") or "").strip().upper()
            if ref_symbol and ref_symbol != symbol:
                continue
            if not self._is_entry_order_ref(order_index, ref):
                continue
            lifecycle_id = str(
                getattr(ref, "idempotent_key", "") or "").strip()
            if lifecycle_id:
                return lifecycle_id
        return ""

    def _resolve_close_request_lifecycle_id(
        self,
        request_payload: Dict[str, Any],
        *,
        manage_flow: Any = None,
    ) -> str:
        symbol = str(request_payload.get("symbol") or "").strip().upper()
        if not symbol:
            return ""
        fill_correlation = dict(request_payload.get("fill_correlation") or {})
        lifecycle_id = str(
            request_payload.get("lifecycle_id")
            or fill_correlation.get("lifecycle_id")
            or getattr(self._fsm, "_last_lifecycle_ikey_by_symbol", {}).get(symbol)
            or ""
        ).strip()
        if lifecycle_id:
            return lifecycle_id
        if manage_flow is None:
            manage_flow = self._fsm.manage_flows.get(symbol)
        return self._recover_lifecycle_from_order_index(
            symbol=symbol,
            request_payload=request_payload,
            manage_flow=manage_flow,
        )

    def _reseed_close_request_lifecycle_context(
        self,
        request_payload: Dict[str, Any],
        *,
        lifecycle_id: str,
    ) -> None:
        lifecycle_id = str(lifecycle_id or "").strip()
        if not lifecycle_id:
            return
        symbol = str(request_payload.get("symbol") or "").strip().upper()
        if not symbol:
            return
        request_payload["lifecycle_id"] = lifecycle_id
        fill_correlation = dict(request_payload.get("fill_correlation") or {})
        fill_correlation.setdefault("lifecycle_id", lifecycle_id)
        request_payload["fill_correlation"] = fill_correlation
        lifecycle_cache = getattr(
            self._fsm, "_last_lifecycle_ikey_by_symbol", None)
        if isinstance(lifecycle_cache, dict):
            lifecycle_cache[symbol] = lifecycle_id
            return
        setattr(self._fsm, "_last_lifecycle_ikey_by_symbol",
                {symbol: lifecycle_id})

    def _mark_lifecycle_close_requested(self, request_payload: Dict[str, Any]) -> None:
        ledger = self._lifecycle_stats_ledger()
        if ledger is None:
            return
        symbol = str(request_payload.get("symbol") or "").strip().upper()
        if not symbol:
            return
        lifecycle_id = self._resolve_close_request_lifecycle_id(
            request_payload)
        if not lifecycle_id:
            return
        current_unrealized_raw = (
            dict(request_payload.get("position_snapshot")
                 or {}).get("unrealized_pnl_usdt")
        )
        try:
            current_unrealized = (
                None
                if current_unrealized_raw in (None, "", "None")
                else float(current_unrealized_raw)
            )
        except (TypeError, ValueError):
            current_unrealized = None
        close_actor = str(
            request_payload.get("policy_source") or "position_policy_sidecar"
        ).strip().upper()
        try:
            ledger.mark_close_requested(
                lifecycle_id=lifecycle_id,
                current_unrealized=current_unrealized,
                close_actor=close_actor,
                source=CLOSE_REQUEST_COMMAND_TOPIC,
            )
        except KeyError:
            return
        except Exception:
            return

    def on_position_policy_close_request(self, event: Message) -> None:
        payload = dict(getattr(event, "pld", None) or {})
        request, request_payload, parse_error = self._parse_position_policy_close_request(
            payload
        )
        if request is None:
            self._emit_position_policy_close_request_state(
                request_payload,
                request_state="suppressed",
                why="position_policy_sidecar:close_request_invalid",
                extra={"suppression_reason": parse_error or "invalid_request"},
            )
            return

        symbol = request.symbol
        allowed_scope = self._position_policy_allowed_scope()
        request_payload["allowed_action_scope"] = dict(allowed_scope)

        suppression_reason: Optional[str] = None
        incumbent_owner: Optional[str] = None
        manage_flow = self._fsm.manage_flows.get(symbol)

        if not request.policy_source.startswith("position_policy_sidecar"):
            suppression_reason = "invalid_policy_source"
        elif request.requested_action != "SOFT_CLOSE":
            suppression_reason = "unsupported_requested_action"
        elif request.target_mode != "symbol_current_net_only":
            suppression_reason = "exact_targeting_forbidden"
        elif request.requested_qty not in (None, "", "0", 0):
            suppression_reason = "partial_reduce_forbidden"
        elif not bool(allowed_scope.get("soft_close_symbol_current_net_only")):
            suppression_reason = "soft_close_scope_disabled"
        elif bool(allowed_scope.get("partial_reduce")):
            suppression_reason = "partial_reduce_forbidden"
        elif bool(allowed_scope.get("bracket_mutation")):
            suppression_reason = "bracket_mutation_forbidden"
        elif bool(allowed_scope.get("exact_targeting")):
            suppression_reason = "exact_targeting_forbidden"
        elif manage_flow is None:
            suppression_reason = "no_manage_flow_for_symbol"
        elif hasattr(manage_flow, "has_active_lifecycle") and not manage_flow.has_active_lifecycle():
            suppression_reason = "manage_flow_has_no_active_lifecycle"
        elif bool(getattr(manage_flow, "_closing_position", False)):
            suppression_reason = "manage_flow_close_in_progress"
            incumbent_owner = "ManageFlowFSM"

        portfolio_state = self._fsm._get_portfolio_state_for_symbol(symbol)
        position_signature = self._fsm._get_portfolio_position_signature(
            symbol)

        if suppression_reason is None and portfolio_state == "UNKNOWN":
            suppression_reason = "portfolio_state_unknown"
        elif suppression_reason is None and portfolio_state == "FLAT":
            suppression_reason = "portfolio_flat_no_live_net_position"
        elif suppression_reason is None and position_signature == "UNKNOWN":
            suppression_reason = "portfolio_position_signature_unknown"

        hardening = get_execution_truth_hardening(self._fsm)
        if suppression_reason is None and hardening is not None:
            close_decision = hardening.evaluate_close_command(
                symbol=symbol,
                requested_qty=request.requested_qty,
                position_signature=position_signature,
                rid=request.request_id,
            )
            if close_decision.suppress:
                suppression_reason = f"close_guard:{close_decision.reason}"
                incumbent_owner = incumbent_owner or "ExecutionTruthHardening"

        if suppression_reason is not None:
            self._emit_position_policy_close_request_state(
                request_payload,
                request_state="suppressed",
                why="position_policy_sidecar:close_request_suppressed",
                extra={
                    "suppression_reason": suppression_reason,
                    "incumbent_owner": incumbent_owner,
                    "portfolio_state": portfolio_state,
                    "portfolio_position_signature": position_signature,
                },
            )
            return

        lifecycle_id = self._resolve_close_request_lifecycle_id(
            request_payload,
            manage_flow=manage_flow,
        )
        self._reseed_close_request_lifecycle_context(
            request_payload,
            lifecycle_id=lifecycle_id,
        )

        policy_context = self._position_policy_context_from_request_payload(
            request_payload
        )
        self._position_policy_close_requests[symbol] = dict(policy_context)
        close_msg = Message(
            op="CMD",
            verb="CLOSE",
            src="execution_position.position_policy_sidecar",
            dst="execution_position",
            rid=request.request_id,
            why="position_policy_sidecar_soft_close",
            pld={
                "symbol": symbol,
                "reason": "position_policy_sidecar_soft_close",
                "trigger": CLOSE_REQUEST_COMMAND_TOPIC,
                "trace": request.trace_id,
                "idempotent_key": request.request_id,
                "close_guard_prevalidated": True,
                "policy_context": policy_context,
            },
        )
        result = self._fsm.handle(close_msg)
        if result is None or getattr(result, "op", None) != "DEC" or getattr(result, "verb", None) not in {"CLOSE", "CLOSE_POSITION"}:
            self._position_policy_close_requests.pop(symbol, None)
            self._emit_position_policy_close_request_state(
                request_payload,
                request_state="suppressed",
                why="position_policy_sidecar:close_command_not_emitted",
                extra={
                    "suppression_reason": "close_command_not_emitted",
                    "portfolio_state": portfolio_state,
                    "portfolio_position_signature": position_signature,
                },
            )
            return

        self._mark_lifecycle_close_requested(request_payload)

        self._emit_position_policy_close_request_state(
            request_payload,
            request_state="close_command_emitted",
            why="position_policy_sidecar:close_command_emitted",
            extra={
                "close_cmd_rid": request.request_id,
                "execution_shadow_mode": bool(self._fsm.shadow_mode),
                "adapter_present": bool(self._fsm.adapter),
                "portfolio_state": portfolio_state,
                "portfolio_position_signature": position_signature,
            },
        )

    def on_execution_close_reconciled(self, event: Message) -> None:
        """
        Intersect EXECUTION_CLOSE_RECONCILED natively to track completions across
        position_policy recommendation payloads gracefully releasing internal map locks.
        """
        payload = dict(getattr(event, "pld", None) or {})
        symbol = str(payload.get("symbol") or "").strip().upper()
        request_context = self._position_policy_close_requests.get(symbol)
        if request_context is not None:
            self._emit_position_policy_close_request_state(
                request_context,
                request_state="reconciled",
                why="position_policy_sidecar:close_reconciled",
                extra={
                    "business_close_reconciled": bool(
                        payload.get("business_close_reconciled")
                    ),
                    "reconcile_source": payload.get("source"),
                    "reconcile_rid": payload.get("rid"),
                    "reconcile_why": payload.get("why"),
                },
            )
            self._position_policy_close_requests.pop(symbol, None)

    def _parse_position_policy_close_request(
        self,
        payload: Dict[str, Any],
    ) -> tuple[Optional[PositionPolicyCloseRequest], Dict[str, Any], Optional[str]]:
        normalized = dict(payload)
        symbol = str(normalized.get("symbol") or "").strip().upper()
        normalized["symbol"] = symbol
        normalized.setdefault(
            "event_type", "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED")
        normalized.setdefault("policy_source", "position_policy_sidecar")
        normalized.setdefault(
            "source_event_type", "POSITION_POLICY_SIDECAR_RECOMMENDED"
        )
        normalized.setdefault("requested_action", "SOFT_CLOSE")
        normalized.setdefault("target_mode", "symbol_current_net_only")
        normalized.setdefault("action_package_version", ACTION_PACKAGE_VERSION)
        normalized.setdefault("allowed_action_scope", {})
        normalized.setdefault("reason_codes", [])
        normalized.setdefault("score_snapshot", {})
        normalized.setdefault("position_snapshot", {})
        normalized.setdefault("feature_ref", {})
        normalized.setdefault("regime_ref", {})
        normalized.setdefault("freshness_snapshot", {})
        normalized.setdefault("fill_correlation", {})
        normalized.setdefault("portfolio_correlation", {})
        normalized["request_id"] = str(
            normalized.get("request_id") or "").strip()
        normalized["trace_id"] = str(normalized.get("trace_id") or "").strip()
        normalized["requested_qty"] = normalized.get("requested_qty")
        try:
            normalized["ts_ms"] = int(normalized.get(
                "ts_ms") or get_clock().now_ms())
        except (TypeError, ValueError):
            normalized["ts_ms"] = get_clock().now_ms()

        if not normalized["request_id"]:
            return None, normalized, "missing_request_id"
        if not normalized["trace_id"]:
            return None, normalized, "missing_trace_id"
        if not symbol:
            return None, normalized, "missing_symbol"

        request = self.position_policy_close_request_type(
            ts_ms=normalized["ts_ms"],
            request_id=normalized["request_id"],
            trace_id=normalized["trace_id"],
            symbol=symbol,
            source_event_type=str(normalized.get(
                "source_event_type") or "POSITION_POLICY_SIDECAR_RECOMMENDED"),
            event_type=str(normalized.get("event_type")
                           or "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED"),
            requested_action=str(normalized.get(
                "requested_action") or "SOFT_CLOSE"),
            requested_qty=(
                None
                if normalized.get("requested_qty") in (None, "", "0", 0)
                else str(normalized.get("requested_qty"))
            ),
            target_mode=str(normalized.get("target_mode")
                            or "symbol_current_net_only"),
            policy_source=str(normalized.get("policy_source")
                              or "position_policy_sidecar"),
            action_package_version=str(normalized.get(
                "action_package_version") or ACTION_PACKAGE_VERSION),
            allowed_action_scope=dict(
                normalized.get("allowed_action_scope") or {}),
            reason_codes=tuple(str(code) for code in (
                normalized.get("reason_codes") or [])),
            score_snapshot=dict(normalized.get("score_snapshot") or {}),
            position_snapshot=dict(normalized.get("position_snapshot") or {}),
            feature_ref=dict(normalized.get("feature_ref") or {}),
            regime_ref=dict(normalized.get("regime_ref") or {}),
            freshness_snapshot=dict(
                normalized.get("freshness_snapshot") or {}),
            fill_correlation=dict(normalized.get("fill_correlation") or {}),
            portfolio_correlation=dict(
                normalized.get("portfolio_correlation") or {}),
        )
        request_payload = dict(normalized)
        request_payload.update(request.to_payload())
        return request, request_payload, None

    def _position_policy_allowed_scope(self) -> Dict[str, bool]:
        try:
            candidate = self._fsm.config.domains.execution_position.position_policy_sidecar
        except Exception:
            candidate = None
        if not isinstance(candidate, PositionPolicySidecarConfig):
            return {
                "soft_close_symbol_current_net_only": False,
                "partial_reduce": False,
                "bracket_mutation": False,
                "exact_targeting": False,
            }
        return {
            "soft_close_symbol_current_net_only": bool(
                candidate.allowed_actions.soft_close_symbol_current_net_only
            ),
            "partial_reduce": bool(candidate.allowed_actions.partial_reduce),
            "bracket_mutation": bool(candidate.allowed_actions.bracket_mutation),
            "exact_targeting": bool(candidate.allowed_actions.exact_targeting),
        }

    @staticmethod
    def _position_policy_context_from_request_payload(
        request_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "symbol": request_payload.get("symbol"),
            "policy_source": request_payload.get("policy_source"),
            "source_event_type": request_payload.get("source_event_type"),
            "source_trace_id": request_payload.get("trace_id"),
            "request_id": request_payload.get("request_id"),
            "request_event_type": request_payload.get("event_type"),
            "requested_action": request_payload.get("requested_action"),
            "requested_qty": request_payload.get("requested_qty"),
            "target_mode": request_payload.get("target_mode"),
            "allowed_action_scope": dict(
                request_payload.get("allowed_action_scope") or {}
            ),
            "reason_codes": list(request_payload.get("reason_codes") or []),
            "score_snapshot": dict(request_payload.get("score_snapshot") or {}),
            "position_snapshot": dict(request_payload.get("position_snapshot") or {}),
            "feature_ref": dict(request_payload.get("feature_ref") or {}),
            "regime_ref": dict(request_payload.get("regime_ref") or {}),
            "freshness_snapshot": dict(
                request_payload.get("freshness_snapshot") or {}
            ),
            "fill_correlation": dict(request_payload.get("fill_correlation") or {}),
            "portfolio_correlation": dict(
                request_payload.get("portfolio_correlation") or {}
            ),
            "action_package_version": request_payload.get("action_package_version"),
            "lifecycle_id": request_payload.get("lifecycle_id"),
            "request_ts_ms": request_payload.get("ts_ms"),
        }

    def _emit_position_policy_close_request_state(
        self,
        request_context: Dict[str, Any],
        *,
        request_state: str,
        why: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "ts_ms": int(get_clock().now_sec() * 1000),
            "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE",
            "request_state": request_state,
            "symbol": request_context.get("symbol")
            or (
                request_context.get("position_snapshot") or {}
            ).get("symbol"),
            "request_id": request_context.get("request_id"),
            "trace_id": request_context.get("trace_id")
            or request_context.get("source_trace_id"),
            "policy_source": request_context.get("policy_source")
            or "position_policy_sidecar",
            "policy_context": self._position_policy_context_from_request_payload(
                request_context
            )
            if "trace_id" in request_context
            else dict(request_context),
            "why": why,
        }
        if extra:
            payload.update({k: v for k, v in extra.items() if v is not None})
        self._fsm._emit_execution_bus_event(
            "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE",
            payload,
        )
        append_trade_lifecycle_record(
            {
                "record_kind": POSITION_POLICY_SIDECAR_RECORD_KIND,
                **payload,
            },
            log_file=self._fsm._trade_lifecycle_log_path(),
        )
