import logging
import time
"""Stateful ingress handlers for the DecisionMaking domain.

This module owns the FSM listeners that cache feature, risk, portfolio, and
regime payloads into shared mutable state. It also emits alpha-score side
channel events and normalizes config-contract failures into
``EVT:DECISION_BLOCKED``.
"""

import logging
from collections import deque
from typing import Any, Callable, Dict, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from apps.reference.utils.accessors import aget
from apps.reference.telemetry.metrics import (
    inc_config_contract_violation,
    inc_decision_blocked,
)
from apps.reference.contracts.reject_reasons import normalize_config_error
from apps.reference.contracts.runtime_regime_layers import (
    is_structural_regime_payload,
    normalize_structural_regime_label,
    structural_regime_ref,
)
from vfoundation.core.protocol import Message
from vfoundation.dr import wal

from .decision_truth_artifacts import write_decision_blocked
from .normalized_reject_reasons import NormalizedRejectReasons
from .trade_intent_reject_wal import write_trade_intent_rejected
from .schemas_decision_blocked import DecisionBlockedPayload
from .dm_log_adapter import DecisionLog

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


class DMEventHandlers:
    """FSM event listeners for the DecisionMaking domain.

    Mutates shared state dicts (symbol_states, per_symbol_regimes) and
    the ``shared_state`` dict for reassignable scalars. The handler is not a
    pure adapter: it stores payloads by reference, annotates freshness data in
    place, and delegates regime-flip side effects to injected collaborators.
    """

    def __init__(
        self,
        *,
        fsm: Any,
        clock: "Clock",
        config: "AuroraConfig",
        symbol_states: Dict[str, Dict[str, Any]],
        per_symbol_regimes: Dict[str, Dict[str, Any]],
        shared_state: Dict[str, Any],
        dlog: DecisionLog,
        alpha_registry: Any,
        handle_regime_flip_fn: Callable,
        record_blocked_fn: Callable[[str], None],
        arming_require_regime_warmup: bool,
        behavior_enabled: bool,
        behavior_state: Dict[str, str],
        logger: logging.Logger,
    ) -> None:
        self._fsm = fsm
        self._clock = clock
        self.config = config
        self.symbol_states = symbol_states
        self._per_symbol_regimes = per_symbol_regimes
        self._shared = shared_state
        self.dlog = dlog
        self.alpha_registry = alpha_registry
        self._handle_regime_flip = handle_regime_flip_fn
        self._record_blocked = record_blocked_fn
        self.arming_require_regime_warmup = arming_require_regime_warmup
        self._behavior_enabled = behavior_enabled
        self._behavior_state = behavior_state
        self.logger = logger

    def _ensure_symbol_state(self, symbol: str) -> Dict[str, Any]:
        """Return the mutable per-symbol cache, creating it on first event."""
        return self.symbol_states.setdefault(symbol, {})

    # -- on_features --------------------------------------------------------

    def on_features(self, event: Message) -> None:
        """Cache feature payloads and emit alpha or blocked side-channel events.

        The cached payload is annotated in place with ``_received_ts`` because
        downstream freshness checks read that marker from symbol state.
        """
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

            state = self._ensure_symbol_state(symbol)

            # This listener is bar-driven; tick-level feature events are rejected
            # and only produce a throttled forensic record.
            tf_sec = None
            try:
                if isinstance(event.pld, dict):
                    tf_sec = event.pld.get("tf_sec")
            except Exception:
                tf_sec = None
            if tf_sec is not None and int(tf_sec or 0) <= 0:
                now_ms = self._clock.now_ms()
                last_ms = int(
                    state.get("_tick_features_reject_last_ts_ms", 0) or 0)
                # Throttle repeated reject WAL writes to once per 5 minutes per symbol.
                if (now_ms - last_ms) >= 300_000:
                    state["_tick_features_reject_last_ts_ms"] = now_ms
                    try:
                        write_trade_intent_rejected(
                            symbol=symbol,
                            tf_sec=int(
                                tf_sec or 0) if tf_sec is not None else None,
                            reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                            stage="DECISION",
                            why="Ignoring tick-level feature event (bar-only strategies)",
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

            state["features"] = event.pld
            state["features"]["_received_ts"] = self._clock.now_ms()

            # A fresh feature snapshot clears the temporary risk-skew latch that
            # blocks trading until new market data arrives.
            try:
                guard = state.get("risk_skew_guard") or {}
                if guard.get("until_refresh"):
                    state["risk_skew_guard"] = {
                        "defer_count": 0,
                        "window_start_ms": self._clock.now_ms(),
                        "until_refresh": False,
                    }
                    self.logger.info(
                        f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on features refresh")
            except Exception:
                pass

            # The handler accepts legacy payload objects, so feature extraction is
            # intentionally defensive before alpha scoring and delta-price history.
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

            # Keep a short delta_price history for downstream directional forensics.
            try:
                dp_raw = feats.get("delta_price")
                dp_val = float(dp_raw) if dp_raw not in (None, "") else None
            except Exception:
                dp_val = None

            if dp_val is not None:
                hist = state.get("_delta_price_hist")
                if not isinstance(hist, deque):
                    hist = deque(maxlen=20)
                    state["_delta_price_hist"] = hist
                hist.append(dp_val)
                state["_last_delta_price"] = dp_val

            self.dlog.write(
                "FEATURES_RX",
                aget(event, "rid", None),
                {"symbol": symbol, "keys": list(feats.keys())},
            )

            # Alpha scoring is optional and only runs when the registry is wired.
            if self.alpha_registry and feats:
                self._compute_alpha_scores(symbol, feats)

        except ConfigContractError as e:
            reason = normalize_config_error(e)
            caught_symbol = e.symbol or symbol
            nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_MISSING
            if "CFG_INVALID" in reason:
                nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_INVALID

            inc_config_contract_violation(
                path=e.path or "unknown", symbol=caught_symbol or "unknown")
            self.logger.critical(
                f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            if caught_symbol:
                self._record_blocked(caught_symbol)

            try:
                # Emit a typed blocked payload instead of letting contract errors
                # surface as generic runtime failures.
                payload_obj = DecisionBlockedPayload(
                    symbol=caught_symbol or "unknown",
                    reason=reason,
                    reason_code=nrr_code,
                    path=str(e.path),
                    why=str(e.why),
                    stage="on_features",
                    ts_ms=self._clock.now_ms(),
                    why_chain=["config_contract_violation"],
                    details={"path": e.path, "why": e.why},
                )
                write_decision_blocked(
                    symbol=payload_obj.symbol,
                    reason_code=payload_obj.reason_code,
                    reason=payload_obj.reason,
                    path=payload_obj.path,
                    why=payload_obj.why,
                    stage=payload_obj.stage,
                    src="decision_making:event_handlers",
                    ts_ms=payload_obj.ts_ms,
                    why_chain=payload_obj.why_chain,
                    details=payload_obj.details,
                )
                self._fsm.emit("EVT:DECISION_BLOCKED", payload_obj.model_dump(
                ), why=f"decision_blocked:{nrr_code}")
                inc_decision_blocked(stage="on_features", reason_code=nrr_code)
            except Exception as ex:
                self.logger.error(f"Failed to emit DECISION_BLOCKED: {ex}")
            return

    def _compute_alpha_scores(self, symbol: str, feats: dict) -> None:
        """Compute alpha scores for a feature snapshot and emit them best-effort.

        ``ConfigContractError`` is re-raised so ``on_features`` can normalize it
        into ``EVT:DECISION_BLOCKED``. Other failures are logged and suppressed.
        """
        try:
            alpha_scores = self.alpha_registry.calculate_all_alpha(
                symbol, {"current_price": feats.get("price")}, feats
            )
            if alpha_scores:
                alpha_payload = {
                    "symbol": symbol,
                    "scores": [score.dict() for score in alpha_scores],
                    "timestamp": self._clock.now_ms(),
                }
                self._fsm.emit(
                    "EVT:ALPHA_SCORE_CALCULATED",
                    payload=alpha_payload,
                    why="alpha_scores_calculated",
                    data_ref=[
                        f"model_{score.model_name}" for score in alpha_scores],
                )

                # WAL gets JSON-safe copies because model payloads can contain
                # Decimal or datetime values that are not natively serializable.
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

                    wal_record = {
                        "op": "EVT",
                        "verb": "ALPHA_SCORE_CALCULATED",
                        "symbol": symbol,
                        "scores": [
                            {k: json_safe_value(v)
                             for k, v in score.dict().items()}
                            for score in alpha_scores
                        ],
                        "timestamp": self._clock.now_ms(),
                        "why": "alpha_calculation",
                    }
                    wal.append(wal_record)
                except Exception as wal_e:
                    self.logger.warning(
                        f"Failed to write alpha scores to WAL: {wal_e}")

                self.logger.info(
                    f"Alpha scores calculated for {symbol}: {len(alpha_scores)} models")
            else:
                self.logger.debug(
                    f"No alpha scores calculated for {symbol} - missing required features")
        except ConfigContractError:
            raise
        except Exception as e:
            self.logger.error(
                f"Error calculating alpha scores for {symbol}: {e}")

    # -- on_risk ------------------------------------------------------------

    def on_risk(self, event: Message) -> None:
        """Cache the latest risk payload for a symbol.

        The raw payload is stored by reference because downstream gates inspect
        nested ``risk_parameters`` without an intermediate normalization layer.
        """
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

        state = self._ensure_symbol_state(symbol)
        self.logger.info(
            f"on_risk() called for {symbol}. Risk params: {event.pld}")
        state["risk"] = event.pld

        # A new risk snapshot also clears the temporary risk-skew latch.
        try:
            guard = state.get("risk_skew_guard") or {}
            if guard.get("until_refresh"):
                state["risk_skew_guard"] = {
                    "defer_count": 0,
                    "window_start_ms": self._clock.now_ms(),
                    "until_refresh": False,
                }
                self.logger.info(
                    f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on risk refresh")
        except Exception as e:
            self.logger.warning(
                f"Error updating risk skew guard from risk event: {e}")

        state["_cached_risk"] = event.pld
        state["_last_risk_time"] = self._clock.now_sec()

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

    # -- on_portfolio -------------------------------------------------------

    def on_portfolio(self, event: Message) -> None:
        """Cache the latest portfolio snapshot and selected equity mirrors."""
        self.logger.info("on_portfolio() called - portfolio state received!")
        portfolio_data = event.pld

        # Keep the last non-zero equity snapshot; zero/None leaves the prior
        # cache untouched for downstream consumers that read shared state.
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
            self._shared["cached_equity_free_usdt"] = equity_free_usdt
            self.logger.info(f"   Cached equity_free_usdt: {equity_free_usdt}")

        # Mirror the cross-margin equity snapshot under the same non-zero rule.
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
            self._shared["cached_equity_cross_usdt"] = equity_cross_usdt

        self._shared["latest_portfolio"] = portfolio_data
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
                    self._shared.get("cached_equity_free_usdt")
                    or (portfolio_data["equity_free_usdt"] if isinstance(portfolio_data, dict) and "equity_free_usdt" in portfolio_data else "0")
                ),
                "positions_count": len(positions),
            },
        )

    # -- on_regime ----------------------------------------------------------

    def on_regime(self, event: Message) -> None:
        """Cache structural regime updates and notify the flip coordinator."""
        pld = event.pld if isinstance(event.pld, dict) else {}
        # DecisionMaking only consumes structural regime events on this path.
        if not is_structural_regime_payload(pld):
            return

        # Preserve the legacy shared-state mirrors while building the richer
        # per-symbol regime snapshot used by downstream logic.
        self._shared["latest_regime"] = {
            "deprecated_last_writer_wins": True,
            "layer": pld.get("regime_layer", "structural"),
            "scope": pld.get("regime_scope", "per_symbol"),
            "symbol": pld.get("symbol"),
            "structural_regime_ref": pld.get("structural_regime_ref"),
        }

        if isinstance(event.pld, dict):
            warmup = event.pld["warmup"] if "warmup" in event.pld else {}
            self._shared["latest_warmup"] = {
                "deprecated_last_writer_wins": True,
                "symbol": event.pld.get("symbol"),
                "warmup": warmup,
            }
            symbol = event.pld.get("symbol")

            if symbol:
                regime_val = normalize_structural_regime_label(
                    event.pld.get("regime") or event.pld.get("overall_regime")
                )
                detector_ts_ms = _optional_int(
                    event.pld.get("ts_ms") or event.pld.get("ts"))
                detector_last_update_ts_ms = _optional_int(
                    event.pld.get("last_update_ts_ms"))
                detector_structural_ref = event.pld.get(
                    "structural_regime_ref") or structural_regime_ref(symbol, detector_ts_ms)
                cache_write_ts_ms = int(time.time() * 1000)
                cache_confidence = _optional_float(event.pld.get("confidence"))
                regime_provenance = {
                    "source_kind": "detector_event",
                    "detector_event": {
                        "event_name": "EVT:REGIME_DETECTED",
                        "rid": getattr(event, "rid", None),
                        "ts_ms": detector_ts_ms,
                        "last_update_ts_ms": detector_last_update_ts_ms,
                        "structural_regime_ref": detector_structural_ref,
                        "basis_tf_sec": event.pld.get("basis_tf_sec"),
                        "bar_close_ts_ms": event.pld.get("bar_close_ts_ms"),
                        "changed": event.pld.get("changed"),
                        "regime": regime_val,
                        "confidence": event.pld.get("confidence"),
                        "stable_confidence": event.pld.get("stable_confidence"),
                        "source_model": event.pld.get("source_model"),
                        "pre_cutoff_source_model": event.pld.get("pre_cutoff_source_model"),
                        "confidence_min": event.pld.get("confidence_min"),
                        "confidence_max": event.pld.get("confidence_max"),
                        "pre_cutoff_regime": event.pld.get("pre_cutoff_regime"),
                        "pre_cutoff_confidence": event.pld.get("pre_cutoff_confidence"),
                        "pre_cutoff_clamped_to_min": event.pld.get("pre_cutoff_clamped_to_min"),
                        "pre_cutoff_clamped_to_max": event.pld.get("pre_cutoff_clamped_to_max"),
                        "pre_cutoff_boundary_reason": event.pld.get("pre_cutoff_boundary_reason"),
                        "uncertain_cutoff": event.pld.get("uncertain_cutoff"),
                        "demoted_to_uncertain": event.pld.get("demoted_to_uncertain"),
                        "raw_regime": event.pld.get("raw_regime"),
                        "raw_confidence": event.pld.get("raw_confidence"),
                        "raw_boundary_reason": event.pld.get("raw_boundary_reason"),
                        "hysteresis_bars": event.pld.get("hysteresis_bars"),
                        "hysteresis_confirm_count": event.pld.get("hysteresis_confirm_count"),
                        "carried_previous_stable": event.pld.get("carried_previous_stable"),
                        "emitted_confidence_kind": event.pld.get("emitted_confidence_kind"),
                        "reason_summary": event.pld.get("reason_summary"),
                    },
                    "cache_snapshot": {
                        "cache_write_ts_ms": cache_write_ts_ms,
                        "regime": regime_val,
                        "confidence": cache_confidence,
                    },
                }
                latest_structural_regimes = self._shared.setdefault(
                    "latest_structural_regime_by_symbol", {})
                if isinstance(latest_structural_regimes, dict):
                    snapshot = dict(event.pld)
                    snapshot["cache_write_ts_ms"] = cache_write_ts_ms
                    snapshot["regime_provenance"] = regime_provenance
                    latest_structural_regimes[symbol] = snapshot
                latest_structural_warmup = self._shared.setdefault(
                    "latest_structural_warmup_by_symbol", {})
                if isinstance(latest_structural_warmup, dict):
                    latest_structural_warmup[symbol] = warmup
                ts_ms = detector_ts_ms
                self._per_symbol_regimes[symbol] = {
                    "symbol": symbol,
                    "regime": regime_val,
                    "warmup": warmup,
                    "confidence": event.pld.get("confidence"),
                    "axes": event.pld.get("axes"),
                    "layer": event.pld.get("regime_layer", "structural"),
                    "scope": event.pld.get("regime_scope", "per_symbol"),
                    "clock": event.pld.get("regime_clock", "bar"),
                    "ts_ms": ts_ms,
                    "structural_regime_ref": detector_structural_ref,
                    "changed": event.pld.get("changed"),
                    "basis_tf_sec": event.pld.get("basis_tf_sec"),
                    "bar_close_ts_ms": event.pld.get("bar_close_ts_ms"),
                    "source_model": event.pld.get("source_model"),
                    "pre_cutoff_source_model": event.pld.get("pre_cutoff_source_model"),
                    "confidence_min": event.pld.get("confidence_min"),
                    "confidence_max": event.pld.get("confidence_max"),
                    "pre_cutoff_regime": event.pld.get("pre_cutoff_regime"),
                    "pre_cutoff_confidence": event.pld.get("pre_cutoff_confidence"),
                    "pre_cutoff_clamped_to_min": event.pld.get("pre_cutoff_clamped_to_min"),
                    "pre_cutoff_clamped_to_max": event.pld.get("pre_cutoff_clamped_to_max"),
                    "pre_cutoff_boundary_reason": event.pld.get("pre_cutoff_boundary_reason"),
                    "uncertain_cutoff": event.pld.get("uncertain_cutoff"),
                    "demoted_to_uncertain": event.pld.get("demoted_to_uncertain"),
                    "raw_regime": event.pld.get("raw_regime"),
                    "raw_confidence": event.pld.get("raw_confidence"),
                    "raw_boundary_reason": event.pld.get("raw_boundary_reason"),
                    "stable_confidence": event.pld.get("stable_confidence"),
                    "hysteresis_bars": event.pld.get("hysteresis_bars"),
                    "last_update_ts_ms": detector_last_update_ts_ms,
                    "cache_write_ts_ms": cache_write_ts_ms,
                    "carried_previous_stable": event.pld.get("carried_previous_stable"),
                    "emitted_confidence_kind": event.pld.get("emitted_confidence_kind"),
                    "reason_summary": event.pld.get("reason_summary"),
                    "regime_provenance": regime_provenance,
                }
                self.logger.debug(
                    f"[{symbol}] Regime updated: {self._per_symbol_regimes[symbol].get('regime')}"
                )
                # The coordinator owns any close/flip side effects; this module
                # only persists the normalized regime snapshot and forwards it.
                self._handle_regime_flip(
                    symbol, self._per_symbol_regimes[symbol])

            # This handler only reports warmup state; it does not enforce it.
            full_ready = (
                bool(warmup["full_ready"] if "full_ready" in warmup else False)
                if self.arming_require_regime_warmup
                else bool(warmup["full_ready"] if "full_ready" in warmup else False)
            )
            if symbol and not full_ready:
                ticks_seen = warmup["ticks_seen"] if "ticks_seen" in warmup else 0
                self.logger.info(
                    f"[{symbol}] RegimeContract: warmup phase (full_ready=false, "
                    f"samples={ticks_seen})"
                )

        # Best-effort behavior overlay; it does not participate in regime
        # persistence and is intentionally isolated from the main cache path.
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

    # -- update_exposure_cache ----------------------------------------------

    def update_exposure_cache(self, event: Message) -> None:
        """Cache exposure summaries for downstream fail-closed safety checks.

        Malformed payloads are logged and ignored instead of raising back into
        the FSM listener loop.
        """
        try:
            payload = event.pld or {}
            exposure_summary = payload["exposure_summary"] if "exposure_summary" in payload else {
            }
            if exposure_summary:
                self._shared["exposure_cache"] = exposure_summary
                self._shared["exposure_cache_timestamp"] = self._clock.now_sec()
                self.logger.debug(
                    f"Exposure cache updated: {len(exposure_summary)} symbols")
        except Exception as e:
            self.logger.warning(f"Failed to update exposure cache: {e}")
