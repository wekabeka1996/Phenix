"""
DecisionMaking domain component.

Aggregates features, risk assessment, and portfolio state to make trading decisions
and emit EVT:TRADE_INTENT_PROPOSED events.
"""
import decimal
import logging
import uuid
from collections import defaultdict
from typing import Dict, Any, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

chain_logger = logging.getLogger('event_chain')


class DecisionMaking:
    """
    Decision making component that aggregates analytical data streams
    and generates trade intents based on aurora decision logic.
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'features': None, 'risk': None})
        self.latest_portfolio: Optional[Dict[str, Any]] = None
        self.latest_regime: Optional[Dict[str, Any]] = None

        # Support both old (config['trading']['decision']) and new (config['decision']) formats
        trading_config = self.config.get('trading', self.config)
        
        if 'decision' not in trading_config and 'decision' not in self.config:
            raise ValueError("Configuration key missing: 'decision'")
        if 'tca_prefs' not in trading_config and 'tca_prefs' not in self.config:
            raise ValueError("Configuration key missing: 'tca_prefs'")
        if 'risk_budgets' not in trading_config and 'risk_budgets' not in self.config:
            raise ValueError("Configuration key missing: 'risk_budgets'")
        
        # Get decision config from either location
        decision_config = trading_config.get('decision', self.config.get('decision', {}))
        sizing_config = decision_config.get('position_sizing', {})
        self.min_pos_size_usd = decimal.Decimal(str(sizing_config.get('min_position_size_usd', 10)))
        self.liq_cap_usd = decimal.Decimal(str(sizing_config.get('liquidity_based_cap_usd', 10000)))

        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)

    def on_features(self, event: Message) -> None:
        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"✅ on_features() called for {symbol}")
        self.symbol_states[symbol]['features'] = event.pld
        self._check_and_trigger_decision_for_symbol(symbol)

    def on_risk(self, event: Message) -> None:
        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"✅ on_risk() called for {symbol}. Risk params: {event.pld}")
        self.symbol_states[symbol]['risk'] = event.pld
        self._check_and_trigger_decision_for_symbol(symbol)

    def on_portfolio(self, event: Message) -> None:
        self.logger.info(f"✅ on_portfolio() called - portfolio state received!")
        self.latest_portfolio = event.pld
        self.logger.info(f"   Equity: {self.latest_portfolio.get('equity')}, Positions: {len(self.latest_portfolio.get('positions', []))}")

    def on_regime(self, event: Message) -> None:
        self.latest_regime = event.pld

    def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
        if not self.latest_portfolio:
            self.logger.debug(f"[{symbol}] Decision deferred: global portfolio state not yet available.")
            return

        state = self.symbol_states[symbol]
        if not state.get('features') or not state.get('risk'):
            self.logger.warning(f"[{symbol}] ⚠️ Decision deferred: features={bool(state.get('features'))}, risk={bool(state.get('risk'))}")
            return

        self.logger.info(f"[{symbol}] ✅ All data ready! Triggering decision...")
        decision_context = {
            "features": state['features'],
            "risk_params": state['risk'],
            "portfolio": self.latest_portfolio,
            "regime": self.latest_regime
        }
        rid = str(uuid.uuid4())
        self._make_decision_for_symbol(symbol, decision_context, rid)

    def _make_decision_for_symbol(self, symbol: str, context: dict, rid: str) -> None:
        self.logger.info(f"[{symbol}] 🚀 _make_decision_for_symbol() START - RID: {rid}")
        why_chain = []
        features_data = context['features']["features"]
        risk_params = context['risk_params']["risk_parameters"]
        portfolio = context['portfolio']
        equity = decimal.Decimal(str(portfolio.get('equity', '0')))
        if equity <= 0:
            self.logger.warning(f"Trade intent for {symbol} rejected: equity is zero or negative.")
            self.clear_internal_state_for_symbol(symbol)
            return
            
        regime = context.get('regime')

        if not risk_params.get('is_trading_allowed', False):
            self.logger.info(f"Trade intent for {symbol} rejected: Trading not allowed by risk manager.")
            self.clear_internal_state_for_symbol(symbol)
            return

        # Support both old (config['trading']['decision']) and new (config['decision']) formats
        # If self.config doesn't have 'trading' key, it means self.config **is** the trading config
        trading_config = self.config.get('trading', self.config)
        decision_config = trading_config.get('decision', {})
        signal_weights = decision_config.get('signal_weights', {})
        
        # DEBUG: Log full trading_config structure
        self.logger.info(f"DEBUG trading_config keys: {list(trading_config.keys())}")
        self.logger.info(f"DEBUG decision_config: {decision_config}")
        self.logger.info(f"DEBUG signal_weights: {signal_weights}")
        
        signal_score = sum(
            decimal.Decimal(str(features_data.get(f, 0.0))) * decimal.Decimal(str(w))
            for f, w in signal_weights.items()
        )

        signal_threshold = decimal.Decimal(str(decision_config.get('signal_threshold', '0.2')))
        side = ""
        if signal_score > signal_threshold:
            side = "buy"
        elif signal_score < -signal_threshold:
            side = "sell"
        else:
            self.logger.info(f"Trade intent for {symbol} rejected: Neutral signal score {signal_score:.4f}")
            self.clear_internal_state_for_symbol(symbol)
            return

        if regime and regime.get('symbol') == symbol:
            current_regime = regime.get('regime')
            if (current_regime == "TREND_UP" and side == "sell") or \
               (current_regime == "TREND_DOWN" and side == "buy"):
                self.logger.info(f"Trade intent for {symbol} ({side}) rejected by regime filter (current regime: {current_regime}).")
                self.clear_internal_state_for_symbol(symbol)
                return

        price_ref_str = features_data.get('price')
        if not price_ref_str:
            self.logger.error(f"CRITICAL: No valid price reference for {symbol}. Cannot make trading decision.")
            self.clear_internal_state_for_symbol(symbol)
            return
        price_ref = decimal.Decimal(str(price_ref_str))

        qty, why_sizing = self._calculate_position_size(symbol, price_ref, side, context)
        why_chain.append(why_sizing)

        if not qty or qty <= 0:
            self.logger.warning(f"Trade intent for {symbol} rejected: quantity is zero or negative. Why: {why_sizing}")
            self.clear_internal_state_for_symbol(symbol)
            return

        self._propose_trade_intent(symbol, side, qty, price_ref, ", ".join(why_chain), rid)

    def _calculate_position_size(self, symbol: str, price: decimal.Decimal, side: str, context: dict) -> tuple[Optional[decimal.Decimal], str]:
        why_chain = []
        portfolio = context['portfolio']
        equity = decimal.Decimal(str(portfolio.get('equity', '0')))
        
        final_pos_size_usd = min(self.liq_cap_usd, equity * decimal.Decimal('0.1')) # Simplified sizing
        
        if final_pos_size_usd < self.min_pos_size_usd:
            return None, f"position size {final_pos_size_usd} is below minimum {self.min_pos_size_usd}"
        
        why_chain.append(f"pos_size_usd={final_pos_size_usd}")

        # Support both old (config['trading']['instruments']) and new (config['instruments']) formats
        trading_config = self.config.get('trading', self.config)
        instrument_specs = trading_config.get('instruments', {}).get(symbol, {})
        step_size_str = instrument_specs.get('step_size')
        if not step_size_str:
            return None, "Missing step_size in config"
        
        step_size = decimal.Decimal(step_size_str)
        if price <= 0:
            return None, "Invalid price for sizing"

        qty = final_pos_size_usd / price
        rounded_qty = qty.quantize(step_size, rounding=decimal.ROUND_DOWN)

        if rounded_qty <= 0:
            return None, f"qty rounded to zero from raw {qty}"

        return rounded_qty, ", ".join(why_chain)

    def _propose_trade_intent(self, symbol: str, side: str, qty: decimal.Decimal, price: decimal.Decimal, why: str, rid: str) -> None:
        trade_intent = {
            "instrument": symbol, "side": side, 
            "order": {"qty": str(qty), "price": str(price), "price_ref": str(price), "reduce_only": False},
            "p": "0.75", "payoff_ratio_r": "2.0",
            "tca_budget": {"max_slippage_bps": "10", "max_latency_ms": 500, "maker_preference": "neutral"},
            "risk_budget": {"trade_cvar95_max_bps": "100", "session_cvar95_max_bps": "200"},
            "size": {"notional_cap_usd": str(qty*price), "kelly_fraction": "0.1"}, "valid_for_ms": 5000, "why": [why],
            "dto_version": "1.0.0", "schema_ref": "...", "idempotent_key": str(uuid.uuid4())
        }
        self.fsm.emit("EVT:TRADE_INTENT_PROPOSED", payload=trade_intent, why="trade_intent")
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
