"""
DMEventHandlers — FSM event listeners for DecisionMaking domain.

Extracted from decision_making.py (Phase 14A decomposition).
Handles: on_features, on_risk, on_portfolio, on_regime, update_exposure_cache.

LOC budget: <=500 (Constitution S3).
"""

import json
import logging
from collections import deque
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

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

# Alpha models (optional, graceful degrade)
try:
    from apps.reference.domains.alpha_search import (
        AlphaModelRegistry,
        MomentumAlphaModel,
        VolatilityAlphaModel,
    )
    ALPHA_MODELS_AVAILABLE = True
except ImportError:
    ALPHA_MODELS_AVAILABLE = False

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock


class DMEventHandlers:
    """FSM event listeners for the DecisionMaking domain.

    Mutates shared state dicts (symbol_states, per_symbol_regimes) and
    the ``shared_state`` dict for reassignable scalars.
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

    # -- on_features --------------------------------------------------------

    def on_features(self, event: Message) -> None:
        try:
            try:
                if isinstance(event.pld, dict):
                    symbol = event.pld["symbol"] if "symbol" in event.pld else "unknown"
                elif hasattr(event, 'pld') and event.pld:
                    symbol = event.pld.symbol if hasattr(event.pld, 'symbol') else "unknown"
                else:
                    symbol = "unknown"
            except (AttributeError, TypeError):
                symbol = "unknown"

            # LEGACY-02-INT (bar-only law): ignore tick-level feature events
            tf_sec = None
            try:
                if isinstance(event.pld, dict):
                    tf_sec = event.pld.get("tf_sec")
            except Exception:
                tf_sec = None
            if tf_sec is not None and int(tf_sec or 0) <= 0:
                now_ms = self._clock.now_ms()
                state = self.symbol_states[symbol]
                last_ms = int(state.get("_tick_features_reject_last_ts_ms", 0) or 0)
                if (now_ms - last_ms) >= 300_000:
                    state["_tick_features_reject_last_ts_ms"] = now_ms
                    try:
                        write_trade_intent_rejected(
                            symbol=symbol,
                            tf_sec=int(tf_sec or 0) if tf_sec is not None else None,
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

            self.logger.debug(f"on_features() accepted for {symbol} tf_sec={tf_sec}")
            if symbol not in self.symbol_states:
                self.symbol_states[symbol] = {}

            self.symbol_states[symbol]["features"] = event.pld
            self.symbol_states[symbol]["features"]["_received_ts"] = self._clock.now_ms()

            # Commit 5: Clear risk-skew until-refresh state on data refresh
            try:
                guard = self.symbol_states[symbol].get("risk_skew_guard") or {}
                if guard.get("until_refresh"):
                    self.symbol_states[symbol]["risk_skew_guard"] = {
                        "defer_count": 0,
                        "window_start_ms": self._clock.now_ms(),
                        "until_refresh": False,
                    }
                    self.logger.info(f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on features refresh")
            except Exception:
                pass

            # Extract features for alpha / delta_price
            try:
                if isinstance(event.pld, dict):
                    feats = (event.pld or {}).get("features") or {}
                elif hasattr(event, 'pld') and event.pld:
                    feats = event.pld.features if hasattr(event.pld, 'features') else {}
                else:
                    feats = {}
            except (AttributeError, TypeError):
                feats = {}

            # DM-DIR-FORENSIC-01: Capture delta_price history
            try:
                dp_raw = feats.get("delta_price")
                dp_val = float(dp_raw) if dp_raw not in (None, "") else None
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

            # Alpha scores calculation (optional)
            if self.alpha_registry and feats:
                self._compute_alpha_scores(symbol, feats)

            pass  # No fallback trigger (P0-6 Safety Audit)

        except ConfigContractError as e:
            reason = normalize_config_error(e)
            caught_symbol = e.symbol or symbol
            nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_MISSING
            if "CFG_INVALID" in reason:
                nrr_code = NormalizedRejectReasons.CONFIG_CONTRACT_INVALID

            inc_config_contract_violation(path=e.path or "unknown", symbol=caught_symbol or "unknown")
            self.logger.critical(f"[{caught_symbol or 'unknown'}] CONFIG BLOCK: {reason} - {e.why}")
            if caught_symbol:
                self._record_blocked(caught_symbol)

            try:
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
                self._fsm.emit("EVT:DECISION_BLOCKED", payload_obj.model_dump(), why=f"decision_blocked:{nrr_code}")
                inc_decision_blocked(stage="on_features", reason_code=nrr_code)
            except Exception as ex:
                self.logger.error(f"Failed to emit DECISION_BLOCKED: {ex}")
            return

    def _compute_alpha_scores(self, symbol: str, feats: dict) -> None:
        """Compute and emit alpha scores (extracted helper for on_features)."""
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
                    data_ref=[f"model_{score.model_name}" for score in alpha_scores],
                )

                # WAL traceability
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
                            {k: json_safe_value(v) for k, v in score.dict().items()}
                            for score in alpha_scores
                        ],
                        "timestamp": self._clock.now_ms(),
                        "why": "alpha_calculation",
                    }
                    wal.append(wal_record)
                except Exception as wal_e:
                    self.logger.warning(f"Failed to write alpha scores to WAL: {wal_e}")

                self.logger.info(f"Alpha scores calculated for {symbol}: {len(alpha_scores)} models")
            else:
                self.logger.debug(f"No alpha scores calculated for {symbol} - missing required features")
        except ConfigContractError:
            raise
        except Exception as e:
            self.logger.error(f"Error calculating alpha scores for {symbol}: {e}")

    # -- on_risk ------------------------------------------------------------

    def on_risk(self, event: Message) -> None:
        try:
            if isinstance(event.pld, dict):
                symbol = event.pld["symbol"] if "symbol" in event.pld else "unknown"
            elif hasattr(event, 'pld') and event.pld:
                symbol = event.pld.symbol if hasattr(event.pld, 'symbol') else "unknown"
            else:
                symbol = "unknown"
        except (AttributeError, TypeError):
            symbol = "unknown"

        self.logger.info(f"on_risk() called for {symbol}. Risk params: {event.pld}")
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
                self.logger.info(f"[{symbol}] RISK_SKEW_GUARD: cleared until_refresh on risk refresh")
        except Exception as e:
            self.logger.warning(f"Error extracting symbol from feature event: {e}")

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

    # -- on_portfolio -------------------------------------------------------

    def on_portfolio(self, event: Message) -> None:
        self.logger.info("on_portfolio() called - portfolio state received!")
        portfolio_data = event.pld

        # Cache equity_free_usdt
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

        # Cache equity_cross_usdt
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
        positions = portfolio_data["positions"] if isinstance(portfolio_data, dict) and "positions" in portfolio_data else []
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
        pld = event.pld if isinstance(event.pld, dict) else {}
        if not is_structural_regime_payload(pld):
            return
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
                latest_structural_regimes = self._shared.setdefault("latest_structural_regime_by_symbol", {})
                if isinstance(latest_structural_regimes, dict):
                    latest_structural_regimes[symbol] = dict(event.pld)
                latest_structural_warmup = self._shared.setdefault("latest_structural_warmup_by_symbol", {})
                if isinstance(latest_structural_warmup, dict):
                    latest_structural_warmup[symbol] = warmup
                ts_ms = event.pld.get("ts_ms") or event.pld.get("ts")
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
                    "structural_regime_ref": event.pld.get("structural_regime_ref") or structural_regime_ref(symbol, ts_ms),
                }
                self.logger.debug(
                    f"[{symbol}] Regime updated: {self._per_symbol_regimes[symbol].get('regime')}"
                )
                self._handle_regime_flip(symbol, self._per_symbol_regimes[symbol])

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

        # Minimal behavior FSM mapping
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
        """Update exposure cache from EVT:EXPOSURE_SUMMARY_UPDATED events."""
        try:
            payload = event.pld or {}
            exposure_summary = payload["exposure_summary"] if "exposure_summary" in payload else {}
            if exposure_summary:
                self._shared["exposure_cache"] = exposure_summary
                self._shared["exposure_cache_timestamp"] = self._clock.now_sec()
                self.logger.debug(
                    f"Exposure cache updated: {len(exposure_summary)} symbols")
        except Exception as e:
            self.logger.warning(f"Failed to update exposure cache: {e}")
