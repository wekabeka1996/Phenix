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

from .normalized_reject_reasons import NormalizedRejectReasons
from vfoundation.apps.reference.domains.decision_making.dm_log_adapter import (
    DecisionLog,
)

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

chain_logger = logging.getLogger("event_chain")


class DecisionMaking:
    """
    Decision making component that aggregates analytical data streams
    and generates trade intents based on aurora decision logic.
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"features": None, "risk": None}
        )
        self.latest_portfolio: Optional[Dict[str, Any]] = None
        self.latest_regime: Optional[Dict[str, Any]] = None

        # Cache for equity values to prevent zero-overwrite
        self._cached_equity_free_usdt: Optional[str] = None
        self._cached_equity_cross_usdt: Optional[str] = None

        # QoS state management (PACK EXP-4)
        self._qos_state = {
            "last_exposure_block": 0,  # timestamp of last exposure block
            "symbol_cooldowns": {},  # symbol -> last_decision_timestamp
            "symbol_intent_counts": defaultdict(
                lambda: {"count": 0, "window_start": time.time()}
            ),  # symbol -> rate tracking
        }

        # Decision logging (DM breadcrumbs)
        self.dlog = DecisionLog()

        # Support both old (config['trading']['decision']) and new (config['decision']) formats
        trading_config = self.config.get("trading", self.config)

        if "decision" not in trading_config and "decision" not in self.config:
            raise ValueError("Configuration key missing: 'decision'")
        if "tca_prefs" not in trading_config and "tca_prefs" not in self.config:
            raise ValueError("Configuration key missing: 'tca_prefs'")
        if "risk_budgets" not in trading_config and "risk_budgets" not in self.config:
            raise ValueError("Configuration key missing: 'risk_budgets'")

        # Get decision config from either location
        decision_config = trading_config.get(
            "decision", self.config.get("decision", {})
        )
        sizing_config = decision_config.get("position_sizing", {})
        self.min_pos_size_usd = decimal.Decimal(
            str(sizing_config.get("min_position_size_usd", 10))
        )
        self.liq_cap_usd = decimal.Decimal(
            str(sizing_config.get("liquidity_based_cap_usd", 10000))
        )

        # QoS configuration (PACK EXP-4)
        qos_config = decision_config.get("qos", {})
        self.qos_exposure_block_cooldown_sec = qos_config.get(
            "exposure_block_cooldown_sec", 10
        )
        self.qos_symbol_cooldown_sec = qos_config.get("symbol_cooldown_sec", 3)
        self.qos_max_intents_per_minute_per_symbol = qos_config.get(
            "max_intents_per_minute_per_symbol", 6
        )

        self.logger.info(
            f"QoS config: exposure_cooldown={self.qos_exposure_block_cooldown_sec}s, "
            f"symbol_cooldown={self.qos_symbol_cooldown_sec}s, "
            f"max_intents_per_min={self.qos_max_intents_per_minute_per_symbol}"
        )

        # FSM event listeners
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)

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
            time_since_last_block = (
                current_time - self._qos_state["last_exposure_block"]
            )
            if time_since_last_block < self.qos_exposure_block_cooldown_sec:
                remaining = self.qos_exposure_block_cooldown_sec - time_since_last_block
                reject_reason = (
                    f"exposure_block_cooldown_active_{remaining:.1f}s_remaining"
                )
                self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
                return False, NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

        # Check symbol cooldown (prevents rapid-fire decisions for same symbol)
        last_decision = self._qos_state["symbol_cooldowns"].get(symbol, 0)
        time_since_last_decision = current_time - last_decision
        if time_since_last_decision < self.qos_symbol_cooldown_sec:
            remaining = self.qos_symbol_cooldown_sec - time_since_last_decision
            reject_reason = f"symbol_cooldown_active_{remaining:.1f}s_remaining"
            self.logger.warning(f"[{symbol}] QoS REJECT: {reject_reason}")
            return False, NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

        # Check rate limit (intents per minute per symbol) - separate from cooldown
        intent_data = self._qos_state["symbol_intent_counts"][symbol]
        window_elapsed = current_time - intent_data["window_start"]

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
        self._qos_state["symbol_cooldowns"][symbol] = current_time
        self.logger.debug(f"[{symbol}] QoS cooldown updated: ts={current_time}")

    def _update_intent_count(self, symbol: str) -> None:
        """Update intent count for rate limiting."""
        intent_data = self._qos_state["symbol_intent_counts"][symbol]
        intent_data["count"] += 1
        self.logger.debug(
            f"[{symbol}] QoS intent count updated: count={intent_data['count']}"
        )

    def _handle_exposure_block(self, symbol: str) -> None:
        """Handle exposure block event by updating QoS state."""
        current_time = time.time()
        self._qos_state["last_exposure_block"] = current_time
        self.logger.warning(f"[{symbol}] Exposure block recorded at {current_time}")

    def on_features(self, event: Message) -> None:
        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"✅ on_features() called for {symbol}")
        self.symbol_states[symbol]["features"] = event.pld
        self._check_and_trigger_decision_for_symbol(symbol)

        feats = (event.pld or {}).get("features") or {}
        self.dlog.write(
            "FEATURES_RX",
            getattr(event, "rid", None),
            {"symbol": symbol, "keys": list(feats.keys())},
        )

    def on_risk(self, event: Message) -> None:
        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"✅ on_risk() called for {symbol}. Risk params: {event.pld}")
        self.symbol_states[symbol]["risk"] = event.pld
        self._check_and_trigger_decision_for_symbol(symbol)

        rp = (event.pld or {}).get("risk_parameters") or {}
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
        self.logger.info(f"✅ on_portfolio() called - portfolio state received!")
        portfolio_data = event.pld

        # Cache equity_free_usdt if present, but don't overwrite with zero/null
        equity_free_usdt = portfolio_data.get("equity_free_usdt")
        if equity_free_usdt and equity_free_usdt not in ("0", "0.0"):
            self._cached_equity_free_usdt = equity_free_usdt
            self.logger.info(f"   Cached equity_free_usdt: {equity_free_usdt}")

        # Also cache equity_cross_usdt if present
        equity_cross_usdt = portfolio_data.get("equity_cross_usdt")
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

    def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
        if not self.latest_portfolio:
            self.logger.debug(
                f"[{symbol}] Decision deferred: global portfolio state not yet available."
            )
            return

        state = self.symbol_states[symbol]
        if not state.get("features") or not state.get("risk"):
            self.logger.warning(
                f"[{symbol}] ⚠️ Decision deferred: features={bool(state.get('features'))}, risk={bool(state.get('risk'))}"
            )
            return

        self.logger.info(f"[{symbol}] ✅ All data ready! Triggering decision...")
        decision_context = {
            "features": state["features"],
            "risk_params": state["risk"],
            "portfolio": self.latest_portfolio,
            "regime": self.latest_regime,
        }
        rid = str(uuid.uuid4())
        self.dlog.write("DECISION_TRIGGER", rid, {"symbol": symbol})
        self._make_decision_for_symbol(symbol, decision_context, rid)

    def _make_decision_for_symbol(self, symbol: str, context: dict, rid: str) -> None:
        self.logger.info(
            f"[{symbol}] 🚀 _make_decision_for_symbol() START - RID: {rid}"
        )
        why_chain = []
        features_data = context["features"]["features"]
        risk_params = context["risk_params"]["risk_parameters"]
        portfolio = context["portfolio"]

        # QoS check (PACK EXP-4) - check rate limits and cooldowns
        qos_allowed, qos_reject_reason = self._qos_allow(
            symbol, is_exposure_block=False
        )
        if not qos_allowed:
            normalized_reason = NormalizedRejectReasons.normalize(
                qos_reject_reason or "QoS rejection"
            )
            self.logger.warning(
                f"[{symbol}] Trade intent rejected by QoS: {normalized_reason}"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {"symbol": symbol, "reason": "QOS_RATE_LIMITED"}
            )
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
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            self.logger.warning(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {"symbol": symbol, "reason": "ZERO_EQUITY"}
            )
            self.clear_internal_state_for_symbol(symbol)
            return

        regime = context.get("regime")

        if not risk_params.get("is_trading_allowed", False):
            reject_reason = "Trading not allowed by risk manager"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)

            # Check if this is an exposure block (PACK EXP-4)
            if (
                "exposure_limit_exceeded" in str(risk_params).lower()
                or "exposure" in str(risk_params).lower()
            ):
                self._handle_exposure_block(symbol)
                normalized_reason = NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

            self.logger.info(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {"symbol": symbol, "reason": "RISK_DISALLOWED"}
            )
            self.clear_internal_state_for_symbol(symbol)
            return

        # Support both old (config['trading']['decision']) and new (config['decision']) formats
        # If self.config doesn't have 'trading' key, it means self.config **is** the trading config
        trading_config = self.config.get("trading", self.config)
        decision_config = trading_config.get("decision", {})
        signal_weights = decision_config.get("signal_weights", {})

        # DEBUG: Log full trading_config structure
        self.logger.info(f"DEBUG trading_config keys: {list(trading_config.keys())}")
        self.logger.info(f"DEBUG decision_config: {decision_config}")
        self.logger.info(f"DEBUG signal_weights: {signal_weights}")

        signal_score = sum(
            decimal.Decimal(str(features_data.get(f, 0.0))) * decimal.Decimal(str(w))
            for f, w in signal_weights.items()
        )

        signal_threshold = decimal.Decimal(
            str(decision_config.get("signal_threshold", "0.2"))
        )
        side = ""
        if signal_score > signal_threshold:
            side = "buy"
        elif signal_score < -signal_threshold:
            side = "sell"
        else:
            reject_reason = f"Neutral signal score {signal_score:.4f}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            self.logger.info(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.dlog.write(
                "DECISION_SKIP", rid, {"symbol": symbol, "reason": "NEUTRAL_SIGNAL"}
            )
            self.clear_internal_state_for_symbol(symbol)
            return

        self.dlog.write(
            "DECISION_EVAL",
            rid,
            {
                "symbol": symbol,
                "signal_score": float(signal_score),
                "signal_threshold": float(signal_threshold),
            },
        )

        if regime and regime.get("symbol") == symbol:
            current_regime = regime.get("regime")
            if (current_regime == "TREND_UP" and side == "sell") or (
                current_regime == "TREND_DOWN" and side == "buy"
            ):
                reject_reason = (
                    f"rejected by regime filter (current regime: {current_regime})"
                )
                normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
                self.logger.info(
                    f"Trade intent for {symbol} ({side}) rejected: {reject_reason} (NRR: {normalized_reason})"
                )
                self.dlog.write(
                    "DECISION_SKIP", rid, {"symbol": symbol, "reason": "REGIME_FILTER"}
                )
                self.clear_internal_state_for_symbol(symbol)
                return

        price_ref_str = features_data.get("price")
        if not price_ref_str:
            reject_reason = "No valid price reference"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            self.logger.error(
                f"CRITICAL: {reject_reason} for {symbol}. Cannot make trading decision. (NRR: {normalized_reason})"
            )
            self.clear_internal_state_for_symbol(symbol)
            return
        price_ref = decimal.Decimal(str(price_ref_str))

        qty, why_sizing = self._calculate_position_size(
            symbol, price_ref, side, context
        )
        why_chain.append(why_sizing)

        if not qty or qty <= 0:
            reject_reason = f"quantity is zero or negative. Why: {why_sizing}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            self.logger.warning(
                f"Trade intent for {symbol} rejected: {reject_reason} (NRR: {normalized_reason})"
            )
            self.clear_internal_state_for_symbol(symbol)
            return

        # Update QoS state for successful decision
        self._update_symbol_cooldown(symbol)
        self._update_intent_count(symbol)

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
        self._propose_trade_intent(
            symbol, side, qty, price_ref, ", ".join(why_chain), rid
        )

    def _calculate_position_size(
        self, symbol: str, price: decimal.Decimal, side: str, context: dict
    ) -> tuple[Optional[decimal.Decimal], str]:
        why_chain = []
        portfolio = context["portfolio"]
        equity = decimal.Decimal(str(portfolio.get("equity", "0")))

        final_pos_size_usd = min(
            self.liq_cap_usd, equity * decimal.Decimal("0.1")
        )  # Simplified sizing

        if final_pos_size_usd < self.min_pos_size_usd:
            reject_reason = f"position size {final_pos_size_usd} is below minimum {self.min_pos_size_usd}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        why_chain.append(f"pos_size_usd={final_pos_size_usd}")

        # Support both old (config['trading']['instruments']) and new (config['instruments']) formats
        trading_config = self.config.get("trading", self.config)
        instrument_specs = trading_config.get("instruments", {}).get(symbol, {})
        step_size_str = instrument_specs.get("step_size")
        if not step_size_str:
            reject_reason = "Missing step_size in config"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        step_size = decimal.Decimal(step_size_str)
        if price <= 0:
            reject_reason = "Invalid price for sizing"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        qty = final_pos_size_usd / price
        rounded_qty = qty.quantize(step_size, rounding=decimal.ROUND_DOWN)

        if rounded_qty <= 0:
            reject_reason = f"qty rounded to zero from raw {qty}"
            normalized_reason = NormalizedRejectReasons.normalize(reject_reason)
            return None, f"{reject_reason} (NRR: {normalized_reason})"

        return rounded_qty, ", ".join(why_chain)

    def _propose_trade_intent(
        self,
        symbol: str,
        side: str,
        qty: decimal.Decimal,
        price: decimal.Decimal,
        why: str,
        rid: str,
    ) -> None:
        trade_intent = {
            "instrument": symbol,
            "side": side,
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
            "why": [why],
            "dto_version": "1.0.0",
            "schema_ref": "...",
            "idempotent_key": str(uuid.uuid4()),
        }
        self.fsm.emit(
            "EVT:TRADE_INTENT_PROPOSED", payload=trade_intent, why="trade_intent"
        )
        self.clear_internal_state_for_symbol(symbol)

    def clear_internal_state_for_symbol(self, symbol: str) -> None:
        if symbol in self.symbol_states:
            del self.symbol_states[symbol]

    def start(self) -> None:
        """Start the decision making component."""
        self.logger.info("DecisionMaking started")

    def stop(self) -> None:
        """Stop the decision making component."""
        self.logger.info("DecisionMaking stopped")
