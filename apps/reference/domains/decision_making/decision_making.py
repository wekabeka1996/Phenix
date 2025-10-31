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
        self.logger.info("🚀 DecisionMaking initialized and registering event listeners")

        self.symbol_states: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'features': None, 'risk': None})
        self.latest_portfolio: Optional[Dict[str, Any]] = None
        self.latest_regime: Optional[Dict[str, Any]] = None
        self.pending_symbols: set[str] = set()

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
        self.risk_per_trade_pct = decimal.Decimal(str(sizing_config.get('risk_per_trade_pct', '0.01')))
        self.sl_bps_for_sizing = decimal.Decimal(str(sizing_config.get('sl_bps', '50')))

        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)
        self.fsm.listen("EVT:REGIME_DETECTED", self.on_regime)

    def on_features(self, event: Message) -> None:
        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"✅ on_features() called for {symbol}")
        self.logger.info(f"   Event payload keys: {list(event.pld.keys()) if event.pld else 'None'}")
        self.logger.info(f"   Event payload: {event.pld}")
        self.symbol_states[symbol]['features'] = event.pld
        self.logger.info(f"   Stored features for {symbol}: {bool(self.symbol_states[symbol]['features'])}")
        self._check_and_trigger_decision_for_symbol(symbol)

    def on_risk(self, event: Message) -> None:
        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"✅ on_risk() called for {symbol}. Risk params: {event.pld}")
        self.symbol_states[symbol]['risk'] = event.pld
        self._check_and_trigger_decision_for_symbol(symbol)

    def on_portfolio(self, event: Message) -> None:
        self.logger.info(f"✅ on_portfolio() called - portfolio state received!")
        self.latest_portfolio = event.pld
        equity = decimal.Decimal(str(self.latest_portfolio.get('equity', '0')))
        self.logger.info(f"   Equity: {equity}, Positions: {len(self.latest_portfolio.get('positions', []))}")

        # If we now have valid equity, re-trigger decisions for all tracked symbols
        if equity > 0:
            self.logger.info(f"🔄 Triggering decisions for all {len(self.config.get('trading', {}).get('symbols_to_track', []))} tracked symbols after portfolio update")
            for symbol in self.config.get('trading', {}).get('symbols_to_track', []):
                self._check_and_trigger_decision_for_symbol(symbol)

    def on_regime(self, event: Message) -> None:
        self.latest_regime = event.pld

    def _check_and_trigger_decision_for_symbol(self, symbol: str) -> None:
        self.logger.info(f"[{symbol}] 🔍 _check_and_trigger_decision_for_symbol() called")
        
        # CHECK 1: Portfolio state MUST exist AND have valid equity
        if not self.latest_portfolio or decimal.Decimal(str(self.latest_portfolio.get('equity', '0'))) <= 0:
            self.logger.debug(f"[{symbol}] Decision deferred: Portfolio state not yet available or equity is zero.")
            self.pending_symbols.add(symbol)
            return

        # If we have valid portfolio, remove from pending if present
        self.pending_symbols.discard(symbol)

        state = self.symbol_states[symbol]
        self.logger.info(f"[{symbol}] Current state keys: {list(state.keys())}")
        
        features_present = bool(state.get('features'))
        risk_present = bool(state.get('risk'))
        
        self.logger.info(f"[{symbol}] Features present: {features_present}, Risk present: {risk_present}")
        self.logger.info(f"[{symbol}] Features data: {state.get('features')}")
        self.logger.info(f"[{symbol}] Risk data: {state.get('risk')}")
        
        if not features_present or not risk_present:
            self.logger.warning(f"[{symbol}] ⚠️ Decision deferred: features={features_present}, risk={risk_present}")
            # DEBUG: Log the actual state content
            self.logger.warning(f"[{symbol}] DEBUG state keys: {list(state.keys())}")
            if state.get('features'):
                self.logger.warning(f"[{symbol}] DEBUG features content: {state['features']}")
            if state.get('risk'):
                self.logger.warning(f"[{symbol}] DEBUG risk content: {state['risk']}")
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
        
        signal_threshold = decimal.Decimal(str(decision_config.get('signal_threshold', '0.2')))
        
        signal_score = sum(
            decimal.Decimal(str(features_data.get(f, 0.0))) * decimal.Decimal(str(w))
            for f, w in signal_weights.items()
        )

        self.logger.info(f"[{symbol}] SIGNAL CALCULATION: score={signal_score:.6f}, threshold={signal_threshold}, features={features_data}")

        side = ""
        if signal_score > signal_threshold:
            side = "buy"
            self.logger.info(f"[{symbol}] SIGNAL DECISION: BUY (score {signal_score:.6f} > {signal_threshold})")
        elif signal_score < -signal_threshold:
            side = "sell"
            self.logger.info(f"[{symbol}] SIGNAL DECISION: SELL (score {signal_score:.6f} < -{signal_threshold})")
        else:
            self.logger.info(f"[{symbol}] REJECT: Neutral signal {signal_score:.4f} (Threshold: {signal_threshold})")
            self.clear_internal_state_for_symbol(symbol)
            return

        if regime and regime.get('symbol') == symbol:
            current_regime = regime.get('regime')
            if (current_regime == "TREND_UP" and side == "sell") or \
               (current_regime == "TREND_DOWN" and side == "buy"):
                self.logger.info(f"[{symbol}] REJECT: Counter-trend {side} blocked by regime {current_regime}")
                self.clear_internal_state_for_symbol(symbol)
                return

        price_ref_str = features_data.get('price')
        if not price_ref_str:
            self.logger.error(f"[{symbol}] CRITICAL: No valid price reference for {symbol}. Cannot make trading decision.")
            self.clear_internal_state_for_symbol(symbol)
            return
        price_ref = decimal.Decimal(str(price_ref_str))
        self.logger.info(f"[{symbol}] PRICE REF: {price_ref}")

        why_chain.append(f"Signal {signal_score:.4f} vs Threshold {signal_threshold}")
        self.logger.info(f"[{symbol}] CALCULATING POSITION SIZE...")
        qty, why_sizing = self._calculate_position_size(symbol, price_ref, side, context)
        why_chain.append(why_sizing)
        self.logger.info(f"[{symbol}] POSITION SIZE: qty={qty}, why='{why_sizing}'")

        if not qty or qty <= 0:
            self.logger.warning(f"[{symbol}] REJECT: quantity is zero or negative. Why: {why_sizing}")
            self.clear_internal_state_for_symbol(symbol)
            return

        self.logger.info(f"[{symbol}] ✅ PROPOSING TRADE INTENT: {side} {qty} @ {price_ref}")
        self._propose_trade_intent(symbol, side, qty, price_ref, why_chain, rid)

    def _calculate_risk_based_position_size_usd(self, equity: decimal.Decimal) -> tuple[Optional[decimal.Decimal], str]:
        """
        Розраховує розмір позиції в USD на основі моделі фіксованого ризику (Van Tharp).
        Position Size = (Risk Amount) / (Stop Loss %)
        """
        
        # 1. Визначити суму ризику (Risk Amount)
        risk_per_trade_usd = equity * self.risk_per_trade_pct
        
        # 2. Визначити Stop Loss %  
        if self.sl_bps_for_sizing <= 0:
            why_fail = f"Sizing failed: invalid sl_bps_for_sizing ({self.sl_bps_for_sizing})"
            self.logger.error(why_fail)
            return None, why_fail
            
        stop_loss_pct = self.sl_bps_for_sizing / decimal.Decimal('10000') # 50 bps = 0.005 (0.5%)

        # 3. Розрахувати розмір позиції
        # (Використовуємо context=decimal.Context(prec=10) для уникнення Inexact)
        ctx = decimal.Context(prec=10)
        calculated_pos_size_usd = ctx.divide(risk_per_trade_usd, stop_loss_pct)
        
        # 4. Застосувати ліміти (Liquidity Cap та Min Size)
        final_pos_size_usd = min(calculated_pos_size_usd, self.liq_cap_usd)
        
        why_chain = (
            f"pos_size_usd={final_pos_size_usd:.2f} "
            f"(Risk={risk_per_trade_usd:.2f} / SL={stop_loss_pct:.4f}, "
            f"CappedAt={self.liq_cap_usd})"
        )

        if final_pos_size_usd < self.min_pos_size_usd:
            why_fail = f"pos_size {final_pos_size_usd:.2f} is below minimum {self.min_pos_size_usd}"
            return None, why_fail

        return final_pos_size_usd, why_chain

    def _calculate_simple_position_size_usd(self, equity: decimal.Decimal) -> tuple[Optional[decimal.Decimal], str]:
        """Calculates a simple position size based on a fixed fraction of equity."""
        final_pos_size_usd = min(self.liq_cap_usd, equity * decimal.Decimal('0.1'))

        if final_pos_size_usd < self.min_pos_size_usd:
            return None, f"position size {final_pos_size_usd:.2f} is below minimum {self.min_pos_size_usd}"

        return final_pos_size_usd, f"pos_size_usd={final_pos_size_usd:.2f} (simple 10% equity cap)"

    def _calculate_position_size(self, symbol: str, price: decimal.Decimal, side: str, context: dict) -> tuple[Optional[decimal.Decimal], str]:
        portfolio = context['portfolio']
        equity = decimal.Decimal(str(portfolio.get('equity', '0')))

        final_pos_size_usd, why_sizing = self._calculate_simple_position_size_usd(equity)

        if final_pos_size_usd is None:
            return None, why_sizing

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

        return rounded_qty, why_sizing

    def _propose_trade_intent(self, symbol: str, side: str, qty: decimal.Decimal, price: decimal.Decimal, why_chain: list[str], rid: str) -> None:
        self.logger.info(f"[{symbol}] 🚀 EMITTING EVT:TRADE_INTENT_PROPOSED: {side} {qty} @ {price}")
        trade_intent = {
            "instrument": symbol, "symbol": symbol, "side": side,
            "order": {"qty": str(qty), "price": str(price), "price_ref": str(price), "reduce_only": False},
            "p": "0.75", "payoff_ratio_r": "2.0",
            "tca_budget": {"max_slippage_bps": "10", "max_latency_ms": 500, "maker_preference": "neutral"},
            "risk_budget": {"trade_cvar95_max_bps": "100", "session_cvar95_max_bps": "200"},
            "size": {"notional_cap_usd": str(qty*price), "kelly_fraction": "0.1"}, "valid_for_ms": 5000, "why": why_chain,
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
