"""
DecisionMaking domain component.

Aggregates features, risk assessment, and portfolio state to make trading decisions
and emit EVT:TRADE_INTENT_PROPOSED events.
"""
import decimal
import hashlib
import logging
import time
from typing import Dict, Any, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


class DecisionMaking:
    """
    Decision making component that aggregates analytical data streams
    and generates trade intents based on aurora decision logic.
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # DEBUG: Log config information
        self.logger.info(f"DEBUG DecisionMaking init: Config type: {type(self.config)}")
        if hasattr(self.config, 'keys'):
            self.logger.info(f"DEBUG DecisionMaking init: Config keys: {list(self.config.keys())}")
        else:
            self.logger.info("DEBUG DecisionMaking init: Config has no keys method")

        # Internal storage for latest data from each stream
        self.latest_features: Optional[Dict[str, Any]] = None
        self.latest_risk: Optional[Dict[str, Any]] = None
        self.latest_portfolio: Optional[Dict[str, Any]] = None
        self.latest_regime: Optional[Dict[str, Any]] = None  # Market regime from regime_detector
        self.prev_equity: Optional[decimal.Decimal] = None  # Track previous equity for logging (FIXED BUG-P2-001: removed duplicate)

        # Default portfolio state for initial decisions (will be updated from account)
        self._default_portfolio = {
            "equity": 0.0,  # Will be loaded from account
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "positions": {}
        }

        # Cache configuration values for helper methods
        trading_config = self.config.get('trading', {})
        if 'decision' not in trading_config:
            raise ValueError("Configuration key missing: 'decision'")
        if 'tca_prefs' not in trading_config:
            raise ValueError("Configuration key missing: 'tca_prefs'")
        if 'risk_budgets' not in trading_config:
            raise ValueError("Configuration key missing: 'risk_budgets'")
        
        sizing_config = trading_config.get('decision', {}).get('position_sizing', {})
        try:
            self.min_pos_size_usd = decimal.Decimal(str(sizing_config.get('min_position_size_usd', 10)))
        except (decimal.InvalidOperation, ValueError, TypeError) as e:
            self.logger.warning(f"Invalid min_position_size_usd in config, using default 10: {e}")
            self.min_pos_size_usd = decimal.Decimal("10")
        
        try:
            self.liq_cap_usd = decimal.Decimal(str(sizing_config.get('liquidity_based_cap_usd', 10000)))
        except (decimal.InvalidOperation, ValueError, TypeError) as e:
            self.logger.warning(f"Invalid liquidity_based_cap_usd in config, using default 10000: {e}")
            self.liq_cap_usd = decimal.Decimal("10000")

        # Subscribe to input events
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
        self.fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", self.on_risk)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio)

    def start(self) -> None:
        """Start the decision making component."""
        # Component is event-driven, no background processing needed
        pass

    def on_features(self, event: Message) -> None:
        """Handle EVT:FEATURES_CALCULATED event."""
        self.logger.info("Handling EVT:FEATURES_CALCULATED...")
        self.latest_features = event.pld
        self._try_make_decision()

    def on_risk(self, event: Message) -> None:
        """Handle EVT:RISK_ASSESSMENT_COMPLETED event."""
        self.logger.info("Handling EVT:RISK_ASSESSMENT_COMPLETED...")
        self.latest_risk = event.pld
        self._try_make_decision()

    def on_portfolio(self, event: Message) -> None:
        """Handle EVT:PORTFOLIO_STATE_UPDATED event."""
        self.logger.info("Handling EVT:PORTFOLIO_STATE_UPDATED...")
        self.latest_portfolio = event.pld
        self._try_make_decision()

    def on_regime(self, event: Message) -> None:
        """Handle EVT:REGIME_DETECTED event."""
        self.logger.info(f"Handling EVT:REGIME_DETECTED for {event.pld.get('symbol')}...")
        self.latest_regime = event.pld
        # No _try_make_decision() call - regime is advisory data, not a trigger

    def _try_make_decision(self) -> None:
        """
        Attempt to make a trading decision when all required data is available.

        Implements Fail-Closed behavior: detailed logging of decision process
        and reasons for rejection. No trade intent emitted if any validation fails.
        """
        try:
            # 1. === GUARD CLAUSES & DATA VALIDATION (AURORA_STATE_SYNC_V1) ===
            # Block until all data streams have provided at least one update.
            if not all([self.latest_features, self.latest_risk, self.latest_portfolio]):
                missing_parts = []
                if not self.latest_features:
                    missing_parts.append("Features")
                if not self.latest_risk:
                    missing_parts.append("Risk")
                if not self.latest_portfolio:
                    missing_parts.append("Portfolio")
                
                self.logger.info(f"[STATE_SYNC] Waiting for fresh data: missing {', '.join(missing_parts)}")
                return

            # 1.5 === CONFIG VALIDATION (FAIL-FAST) ===
            trading_config = self.config.get('trading', {})
            if 'decision' not in trading_config:
                raise KeyError("'decision'")
            if 'tca_prefs' not in trading_config:
                raise KeyError("'tca_prefs'")
            if 'risk_budgets' not in trading_config:
                raise KeyError("'risk_budgets'")

            # Assertions for type safety after guard clauses
            assert self.latest_features is not None
            assert self.latest_risk is not None
            assert self.latest_portfolio is not None

            # Extract data from payloads
            features = self.latest_features["features"]
            risk_params = self.latest_risk["risk_parameters"]
            portfolio = self.latest_portfolio
            symbol = self.latest_features["symbol"]

            self.logger.info(f"All data available for {symbol}. Evaluating trade intent.")

            # Validate that portfolio equity is a positive number
            equity = decimal.Decimal(str(portfolio.get("equity", 0.0)))
            if self.prev_equity is not None and self.prev_equity != equity:
                self.logger.info(f"Equity updated: ${float(self.prev_equity):.2f} → ${float(equity):.2f}")
            self.prev_equity = equity
            if equity <= decimal.Decimal('0'):
                self.logger.warning(f"Trade intent rejected for {symbol}: Invalid equity ${equity:.2f}")
                self.clear_internal_state()
                return

            # Validate that risk assessment allows trading
            if not risk_params.get("is_trading_allowed", False):
                self.logger.info(f"Trade intent rejected for {symbol}: Trading not allowed by risk manager.")
                self.clear_internal_state()
                return

            # === CONFIG & PARAMETER LOADING (moved before position gating) ===
            trading_config = self.config['trading']
            decision_config = trading_config['decision']

            # === POSITION GATING: Allow reverse trades, block position accumulation ===
            # Prevents uncontrolled position accumulation but allows closing/reversing positions
            
            # Pre-calculate signal to determine trade direction for position gating
            obi = decimal.Decimal(str(features.get("obi", 0.0)))
            tfi = decimal.Decimal(str(features.get("tfi", 0.0)))
            absorption = decimal.Decimal(str(features.get("absorption", 0.0)))
            signal_weights = decision_config['signal_weights']
            obi_weight = decimal.Decimal(str(signal_weights['obi']))
            tfi_weight = decimal.Decimal(str(signal_weights['tfi']))
            absorption_weight = decimal.Decimal(str(signal_weights['absorption']))
            signal_score = (obi * obi_weight) + (tfi * tfi_weight) + (absorption * absorption_weight)
            signal_threshold = decimal.Decimal(str(decision_config.get('signal_threshold', '0.1')))
            
            # Determine trade direction for position gating
            if signal_score > signal_threshold:
                intended_side = "buy"
            elif signal_score < -signal_threshold:
                intended_side = "sell"
            else:
                self.logger.info(f"Trade intent rejected for {symbol}: Neutral signal score {signal_score:.3f}")
                self.clear_internal_state()
                return
            
            positions_list = portfolio.get("positions", [])
            self.logger.info(f"[POSITION_GATE] Checking positions for {symbol}: total_positions={len(positions_list)}")
            
            # Find if symbol already has a position
            existing_position = None
            for pos in positions_list:
                if pos.get("symbol") == symbol:
                    existing_position = pos
                    break
            
            if existing_position:
                current_qty = decimal.Decimal(str(existing_position.get("net_position", 0)))
                self.logger.info(f"[POSITION_GATE] Found position for {symbol}: qty={current_qty}")
                
                # Determine if this is a reverse trade (closing/opposite direction)
                if current_qty > decimal.Decimal('1e-9') and intended_side == "sell":
                    self.logger.info(f"[POSITION_GATE] ✅ Allowing SELL for {symbol}: closing existing LONG position")
                elif current_qty < -decimal.Decimal('1e-9') and intended_side == "buy":
                    self.logger.info(f"[POSITION_GATE] ✅ Allowing BUY for {symbol}: closing existing SHORT position")
                else:
                    # Same direction trade - block to prevent accumulation
                    self.logger.warning(f"[POSITION_GATE] ❌ Trade intent BLOCKED for {symbol}: Same direction as existing position (qty={current_qty}, intended_side={intended_side})")
                    self.clear_internal_state()
                    return
            else:
                self.logger.info(f"[POSITION_GATE] ✅ No position for {symbol}, allowing new trade")

            # 2. === CONFIG & PARAMETER LOADING (already loaded before position gating) ===
            sizing_config = decision_config['position_sizing']
            tca_prefs = trading_config['tca_prefs']
            risk_budgets = trading_config['risk_budgets']
            signal_weights = decision_config['signal_weights']
            prob_bounds = decision_config['probability_bounds']
            signal_threshold = decimal.Decimal(str(decision_config.get('signal_threshold', '0.1')))
            p_calibration_version = decision_config.get('p_calibration_version', 'calibrated_v1')

            # 3. === DECISION CALCULATION ===
            # Signal already calculated for position gating, just assign side
            side = intended_side
            
            # === REGIME-ADAPTIVE FILTER ===
            # Block counter-trend trades based on current market regime
            if self.latest_regime and self.latest_regime.get("symbol") == symbol:
                current_regime = self.latest_regime.get("regime")
                
                # Rule 1: Block SELL signals in TREND_UP regime (counter-trend)
                if current_regime == "TREND_UP" and side == "sell":
                    self.logger.info(
                        f"Trade intent for {symbol} ({side}) rejected by regime filter "
                        f"(current regime: {current_regime})."
                    )
                    self.clear_internal_state()
                    return
                
                # Rule 2: Block BUY signals in TREND_DOWN regime (counter-trend)
                if current_regime == "TREND_DOWN" and side == "buy":
                    self.logger.info(
                        f"Trade intent for {symbol} ({side}) rejected by regime filter "
                        f"(current regime: {current_regime})."
                    )
                    self.clear_internal_state()
                    return
            
            # === REGIME-ADAPTIVE SIZING ===
            # Apply regime-based position size adjustments
            regime_size_multiplier = decimal.Decimal("1.0")  # Default: no adjustment
            
            if self.latest_regime and self.latest_regime.get("symbol") == symbol:
                current_regime = self.latest_regime.get("regime")
                
                # Rule 3: Reduce position size in UNCERTAIN regime (safer approach)
                if current_regime == "UNCERTAIN":
                    regime_size_multiplier = decimal.Decimal("0.5")  # 50% reduction
                    self.logger.info(
                        f"Trade intent for {symbol} ({side}) size reduced by 50% due to "
                        f"UNCERTAIN regime (safer sizing in unclear market conditions)."
                    )
            
            base_prob = decimal.Decimal(str(prob_bounds['base']))
            max_prob = decimal.Decimal(str(prob_bounds['max_prob']))
            min_prob = decimal.Decimal(str(prob_bounds.get('min_prob', '0.1')))
            
            # Calculate p pipeline with transparency
            # Use abs(signal_score) to ensure probability is always positive
            # Direction (buy/sell) is already determined, we need signal strength for sizing
            p_raw = base_prob + abs(signal_score)  # Raw probability before calibration
            p_cal = p_raw  # Placeholder for calibration (isotonic/platt scaling)
            p_ceiling = max_prob  # Configurable ceiling
            p = min(p_ceiling, max(min_prob, p_cal))  # Final probability with bounds

            # Calculate EV and Kelly
            payoff_ratio_r = decimal.Decimal(str(decision_config['payoff_ratio_r']))
            ev_raw = self._calculate_expected_value(p, payoff_ratio_r)  # Using helper method
            full_kelly = (p - (decimal.Decimal('1') - p) / payoff_ratio_r) if payoff_ratio_r > decimal.Decimal('0') else decimal.Decimal('0')
            kelly_cap = decimal.Decimal(str(self.config.get('system', {}).get('kelly', {}).get('fraction_cap', '0.85')))
            kelly_alpha = decimal.Decimal(str(sizing_config.get('kelly_alpha', '0.5')))
            kelly_used = min(kelly_cap, kelly_alpha * full_kelly)

            # Calculate CVaR limits in USD
            cvar_trade_usd = equity * decimal.Decimal(str(risk_budgets['trade_cvar95_max_bps'])) / decimal.Decimal('10000')
            cvar_session_usd = equity * decimal.Decimal(str(risk_budgets['session_cvar95_max_bps'])) / decimal.Decimal('10000')
            
            # Quality metrics using helper method
            quality_grade = self._compute_quality_grade(p)
            # Placeholder for calibration metrics
            p_calib_metrics = decision_config.get('calib_metrics_placeholder', 'ECE=0.05, Brier=0.08')

            # 4. === POSITION SIZING ===
            # === DIAGNOSTIC LOGGING START [RID: AURORA_QTY0_DIAG_V1] ===
            self.logger.debug(f"[QTY_DIAG] ===== Position Sizing for {symbol} =====")
            self.logger.debug("[QTY_DIAG] Input Data:")
            self.logger.debug(f"[QTY_DIAG]   - Portfolio Equity: ${equity}")
            self.logger.debug(f"[QTY_DIAG]   - Signal Score: {signal_score}")
            self.logger.debug(f"[QTY_DIAG]   - Side: {side}")
            self.logger.debug(f"[QTY_DIAG]   - Probability (p): {p} (raw={p_raw}, cal={p_cal}, min={min_prob}, max={max_prob})")
            self.logger.debug(f"[QTY_DIAG]   - Kelly Used: {kelly_used} (full={full_kelly}, alpha={kelly_alpha}, cap={kelly_cap})")
            self.logger.debug(f"[QTY_DIAG]   - CVaR Trade Limit: ${cvar_trade_usd}")
            self.logger.debug(f"[QTY_DIAG]   - CVaR Session Limit: ${cvar_session_usd}")
            
            # Use calculated kelly_used instead of risk_params kelly_fraction
            kelly_fraction = kelly_used  # Now dynamic based on p and r

            kelly_conservative_factor = decimal.Decimal(str(sizing_config['kelly_conservative_factor']))
            min_position_size = decimal.Decimal(str(sizing_config['min_position_size_usd']))
            max_position_size = decimal.Decimal(str(sizing_config['max_position_size_usd']))
            default_notional_cap = decimal.Decimal(str(sizing_config['default_notional_cap_usd']))
            
            self.logger.debug("[QTY_DIAG] Config Parameters:")
            self.logger.debug(f"[QTY_DIAG]   - Kelly Conservative Factor: {kelly_conservative_factor}")
            self.logger.debug(f"[QTY_DIAG]   - Min Position Size USD: ${min_position_size}")
            self.logger.debug(f"[QTY_DIAG]   - Max Position Size USD: ${max_position_size}")
            self.logger.debug(f"[QTY_DIAG]   - Default Notional Cap USD: ${default_notional_cap}")
            
            # Dynamic cap: min of Kelly-based, CVaR-based, and liquidity-based
            kelly_based_cap = kelly_used * equity
            cvar_based_cap = cvar_trade_usd  # Use trade CVaR as primary limit
            liquidity_based_cap = decimal.Decimal(str(sizing_config.get('liquidity_based_cap_usd', '10000')))
            notional_cap = min(kelly_based_cap, cvar_based_cap, liquidity_based_cap, default_notional_cap)

            self.logger.debug("[QTY_DIAG] Cap Calculations:")
            self.logger.debug(f"[QTY_DIAG]   - Kelly Based Cap: ${kelly_based_cap}")
            self.logger.debug(f"[QTY_DIAG]   - CVaR Based Cap: ${cvar_based_cap}")
            self.logger.debug(f"[QTY_DIAG]   - Liquidity Based Cap: ${liquidity_based_cap}")
            self.logger.debug(f"[QTY_DIAG]   - Final Notional Cap: ${notional_cap} (minimum of all caps)")

            kelly_based_size = equity * kelly_fraction * kelly_conservative_factor
            position_size = min(max_position_size, kelly_based_size, notional_cap)
            
            # Apply regime-based size adjustment
            position_size = position_size * regime_size_multiplier

            self.logger.debug("[QTY_DIAG] Size Calculations:")
            self.logger.debug(f"[QTY_DIAG]   - Kelly Based Size: ${kelly_based_size}")
            self.logger.debug(f"[QTY_DIAG]   - Position Size (before regime adjustment): ${position_size / regime_size_multiplier}")
            self.logger.debug(f"[QTY_DIAG]   - Regime Size Multiplier: {regime_size_multiplier}")
            self.logger.debug(f"[QTY_DIAG]   - Position Size (after regime adjustment): ${position_size}")

            if position_size < min_position_size:
                self.logger.info(f"[QTY_DIAG] ❌ Trade intent REJECTED for {symbol}: Calculated size ${position_size:.2f} is below minimum ${min_position_size:.2f}")
                self.clear_internal_state()
                return
            
            self.logger.debug(f"[QTY_DIAG] ✅ Position size ${position_size} passed minimum threshold")
            
            # Get instrument specs for order conversion (needed for leverage check)
            instrument_specs = trading_config['instruments'].get(symbol, {})
            step_size = decimal.Decimal(str(instrument_specs.get('step_size', '0.001')))
            tick_size = decimal.Decimal(str(instrument_specs.get('tick_size', '0.01')))
            
            # === LEVERAGE-AWARE MARGIN CHECK [RID: AURORA_LEVERAGE_QTY_V1] ===
            # Verify that position size respects available margin when leverage is used
            leverage = decimal.Decimal(str(instrument_specs.get('leverage', 1)))
            margin_safety_factor = decimal.Decimal(str(sizing_config.get('margin_safety_factor', 0.9)))
            
            # Get available margin from portfolio (updated via EVT:ACCOUNT_UPDATE_RECEIVED)
            available_margin = decimal.Decimal(str(portfolio.get('available_balance', equity)))
            
            # Calculate required initial margin for this position
            required_margin = position_size / leverage if leverage > 0 else position_size
            max_usable_margin = available_margin * margin_safety_factor
            
            self.logger.debug("[QTY_DIAG] === Leverage-Aware Margin Check ===")
            self.logger.debug(f"[QTY_DIAG]   - Leverage: {leverage}x")
            self.logger.debug(f"[QTY_DIAG]   - Desired Position Size: ${position_size}")
            self.logger.debug(f"[QTY_DIAG]   - Required Margin: ${required_margin} (position / leverage)")
            self.logger.debug(f"[QTY_DIAG]   - Available Margin: ${available_margin}")
            self.logger.debug(f"[QTY_DIAG]   - Margin Safety Factor: {margin_safety_factor}")
            self.logger.debug(f"[QTY_DIAG]   - Max Usable Margin: ${max_usable_margin}")
            
            if required_margin > max_usable_margin:
                # Cap position size based on available margin
                capped_position_size = max_usable_margin * leverage
                
                self.logger.warning(
                    f"[QTY_DIAG] ⚠️ Position size CAPPED due to insufficient margin for {symbol}:"
                )
                self.logger.warning(f"[QTY_DIAG]   - Desired: ${position_size:.2f}, Required margin: ${required_margin:.2f}")
                self.logger.warning(f"[QTY_DIAG]   - Available: ${available_margin:.2f}, Max usable: ${max_usable_margin:.2f}")
                self.logger.warning(f"[QTY_DIAG]   - Capped to: ${capped_position_size:.2f} (usable_margin * leverage)")
                
                position_size = capped_position_size
                
                # Re-check minimum after capping
                if position_size < min_position_size:
                    self.logger.info(
                        f"[QTY_DIAG] ❌ Trade intent REJECTED for {symbol}: "
                        f"Margin-capped size ${position_size:.2f} below minimum ${min_position_size:.2f}"
                    )
                    self.clear_internal_state()
                    return
            else:
                self.logger.debug(f"[QTY_DIAG] ✅ Sufficient margin available (required ${required_margin:.2f} <= usable ${max_usable_margin:.2f})")
            # === END LEVERAGE-AWARE MARGIN CHECK ===
            
            # === DIAGNOSTIC LOGGING END ===
            
            self.logger.debug(f"[QTY_DIAG] Instrument Specs for {symbol}:")
            self.logger.debug(f"[QTY_DIAG]   - Step Size: {step_size}")
            self.logger.debug(f"[QTY_DIAG]   - Tick Size: {tick_size}")
            self.logger.debug(f"[QTY_DIAG]   - Full Instrument Config: {instrument_specs}")
            
            # Get reference price from latest market data
            price_ref = decimal.Decimal('0')
            if self.latest_features and 'price' in self.latest_features.get('features', {}):
                price_ref = decimal.Decimal(str(self.latest_features['features']['price']))
                self.logger.debug(f"[QTY_DIAG] Price source: latest_features['price'] = {price_ref}")
            elif self.latest_portfolio and 'last_price' in self.latest_portfolio:
                price_ref = decimal.Decimal(str(self.latest_portfolio['last_price']))
                self.logger.debug(f"[QTY_DIAG] Price source: latest_portfolio['last_price'] = {price_ref}")
            else:
                # Fallback to mid price from features if available
                features = self.latest_features.get('features', {}) if self.latest_features else {}
                bid = decimal.Decimal(str(features.get('bid', '0')))
                ask = decimal.Decimal(str(features.get('ask', '0')))
                if bid > 0 and ask > 0:
                    price_ref = (bid + ask) / 2
                    self.logger.debug(f"[QTY_DIAG] Price source: mid(bid={bid}, ask={ask}) = {price_ref}")
                else:
                    self.logger.debug(f"[QTY_DIAG] Price source: NONE (bid={bid}, ask={ask})")
            
            # FIXED BUG-P1-004: Fail-closed pattern - never use hardcoded fallback prices
            if price_ref <= 0:
                self.logger.error(f"[QTY_DIAG] ❌ CRITICAL: No valid price reference available for {symbol}. Cannot make trading decision without reliable price data.")
                self.clear_internal_state()
                return  # Fail-closed: reject decision instead of using dangerous fallback
            
            # Convert notional to quantity
            qty_raw = position_size / price_ref
            qty = (qty_raw // step_size) * step_size  # Floor to step size
            price = ((price_ref // tick_size) * tick_size).quantize(tick_size)  # Round to tick size
            
            self.logger.debug("[QTY_DIAG] Quantity Conversion:")
            self.logger.debug(f"[QTY_DIAG]   - Position Size USD: ${position_size}")
            self.logger.debug(f"[QTY_DIAG]   - Reference Price: {price_ref}")
            self.logger.debug(f"[QTY_DIAG]   - Raw Qty (before floor): {qty_raw}")
            self.logger.debug(f"[QTY_DIAG]   - Final Qty (after step_size floor): {qty}")
            self.logger.debug(f"[QTY_DIAG]   - Rounded Price: {price}")
            
            # Ensure minimum quantity
            min_qty = decimal.Decimal(str(instrument_specs.get('min_qty', '0.001')))
            self.logger.debug("[QTY_DIAG] Minimum Quantity Check:")
            self.logger.debug(f"[QTY_DIAG]   - Min Qty from config: {min_qty}")
            self.logger.debug(f"[QTY_DIAG]   - Calculated Qty: {qty}")
            
            if qty < min_qty:
                self.logger.info(f"[QTY_DIAG] ❌ Trade intent REJECTED for {symbol}: Calculated qty {qty:.6f} below minimum {min_qty}")
                self.logger.info("[QTY_DIAG] Root cause analysis:")
                self.logger.info(f"[QTY_DIAG]   - Position size too small (${position_size}) OR")
                self.logger.info(f"[QTY_DIAG]   - Price too high ({price_ref}) OR")
                self.logger.info(f"[QTY_DIAG]   - Step size too large ({step_size}) caused excessive floor rounding")
                self.clear_internal_state()
                return
            
            self.logger.debug(f"[QTY_DIAG] ✅ Quantity {qty} passed minimum threshold {min_qty}")

            # === REGIME-ADAPTIVE POSITION SIZING ===
            # Apply regime-based position size modifiers to manage risk dynamically
            if self.latest_regime and self.latest_regime.get("symbol") == symbol:
                current_regime = self.latest_regime.get("regime")
                
                # Get sizing modifiers from config (default: no modification)
                sizing_modifiers = decision_config.get('sizing_modifiers', {})
                
                # PRIORITY 1: Volatility-based sizing (HIGH_VOLATILITY, LOW_VOLATILITY)
                if current_regime in ["HIGH_VOLATILITY", "LOW_VOLATILITY"] and current_regime in sizing_modifiers:
                    modifier = decimal.Decimal(str(sizing_modifiers[current_regime]))
                    self.logger.info(
                        f"Position size for {symbol} modified by factor {modifier} due to {current_regime} regime."
                    )
                    position_size *= modifier
                    # Recalculate qty with modified position_size
                    qty_raw = position_size / price_ref
                    qty = (qty_raw // step_size) * step_size  # Floor to step size
                    
                    # Re-validate minimum quantity after modification
                    if qty < min_qty:
                        self.logger.info(f"Trade intent rejected for {symbol}: Modified qty {qty:.6f} below minimum {min_qty}")
                        self.clear_internal_state()
                        return
                
                # PRIORITY 2: Mean reversion sizing (backward compatibility with existing logic)
                elif current_regime == "MEAN_REVERSION":
                    # Use sizing_modifiers if available, otherwise fallback to hardcoded 50% reduction
                    if "MEAN_REVERSION" in sizing_modifiers:
                        modifier = decimal.Decimal(str(sizing_modifiers["MEAN_REVERSION"]))
                        self.logger.info(
                            f"Position size for {symbol} modified by factor {modifier} due to {current_regime} regime."
                        )
                        position_size *= modifier
                    else:
                        # Backward compatibility: hardcoded 50% reduction
                        self.logger.info(
                            f"Position size for {symbol} reduced by 50% due to {current_regime} regime."
                        )
                        position_size *= decimal.Decimal("0.5")
                    
                    # Recalculate qty with reduced position_size
                    qty_raw = position_size / price_ref
                    qty = (qty_raw // step_size) * step_size  # Floor to step size
                    
                    # Re-validate minimum quantity after reduction
                    if qty < min_qty:
                        self.logger.info(f"Trade intent rejected for {symbol}: Reduced qty {qty:.6f} below minimum {min_qty}")
                        self.clear_internal_state()
                        return

            # === LIQUIDATION DISTANCE GUARD [RID: AURORA_LIQUIDATION_GUARD_V1] ===
            # Calculate approximate liquidation price and ensure safe distance
            risk_config = trading_config.get('risk', {})
            min_liq_distance_pct = decimal.Decimal(str(risk_config.get('min_liquidation_distance_pct', 5.0)))
            mmr = decimal.Decimal(str(risk_config.get('maintenance_margin_rate', 0.004)))  # 0.4% default
            
            # Calculate liquidation price (simplified formula for cross margin)
            # For LONG: LiqPrice ≈ EntryPrice × (1 - 1/Leverage + MMR)
            # For SHORT: LiqPrice ≈ EntryPrice × (1 + 1/Leverage - MMR)
            entry_price = price_ref
            imr = decimal.Decimal('1') / leverage if leverage > 0 else decimal.Decimal('1')  # Initial Margin Ratio
            
            if side == 'buy':  # LONG position
                liq_price = entry_price * (decimal.Decimal('1') - imr + mmr)
            else:  # SHORT position
                liq_price = entry_price * (decimal.Decimal('1') + imr - mmr)
            
            # Calculate distance to liquidation as percentage of entry price
            distance_to_liq = abs(entry_price - liq_price)
            distance_pct = (distance_to_liq / entry_price) * decimal.Decimal('100')
            
            self.logger.debug("[LIQUIDATION_GUARD] === Liquidation Distance Check ===")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Side: {side}")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Entry Price: ${entry_price}")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Leverage: {leverage}x")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Initial Margin Ratio: {imr:.4f} (1/leverage)")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Maintenance Margin Rate: {mmr:.4f}")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Calculated Liquidation Price: ${liq_price:.2f}")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Distance to Liquidation: ${distance_to_liq:.2f} ({distance_pct:.2f}%)")
            self.logger.debug(f"[LIQUIDATION_GUARD]   - Minimum Required Distance: {min_liq_distance_pct:.2f}%")
            
            # Apply guard: reject if too close to liquidation
            if distance_pct < min_liq_distance_pct:
                self.logger.error(
                    f"[LIQUIDATION_GUARD] ❌ Trade intent REJECTED for {symbol}: "
                    f"Position would be too close to liquidation price!"
                )
                self.logger.error(
                    f"[LIQUIDATION_GUARD]   Entry: ${entry_price:.2f}, "
                    f"Liquidation: ${liq_price:.2f}, "
                    f"Distance: {distance_pct:.2f}% (min required: {min_liq_distance_pct:.2f}%)"
                )
                self.logger.error(
                    f"[LIQUIDATION_GUARD]   Leverage: {leverage}x, Side: {side}, "
                    f"Position Size: ${position_size:.2f}"
                )
                self.clear_internal_state()
                return  # Reject trade to protect from liquidation risk
            else:
                self.logger.info(
                    f"[LIQUIDATION_GUARD] ✅ Liquidation distance check PASSED for {symbol}: "
                    f"{distance_pct:.2f}% >= {min_liq_distance_pct:.2f}% "
                    f"(Entry: ${entry_price:.2f}, Liq: ${liq_price:.2f})"
                )
            # === END LIQUIDATION DISTANCE GUARD ===

            # 5. === IDEMPOTENCY KEY GENERATION (AURORA_IDEMPOTENCY_V1) ===
            # Generate unique idempotent_key for this intent to prevent duplicate orders
            idempotency_config = trading_config.get('idempotency', {})
            if idempotency_config.get('enabled', False):
                current_ts_ms = int(time.time() * 1000)
                ts_bucket_ms = idempotency_config.get('ts_bucket_ms', 1000)
                # Round timestamp to bucket (e.g., 1-second intervals)
                ts_bucket = (current_ts_ms // ts_bucket_ms) * ts_bucket_ms
                
                # Generate key from template
                key_template = idempotency_config.get('key_template', '{symbol}:{side}:{ts_bucket_ms}')
                idem_key_raw = key_template.format(
                    symbol=symbol,
                    side=side.lower(),
                    ts_bucket_ms=ts_bucket
                )
                
                # Hash to SHA256 and take first 16 bytes (32 hex chars) for Binance compatibility
                # Binance newClientOrderId: max 36 chars, alphanumeric + - _
                idem_key_hash = hashlib.sha256(idem_key_raw.encode('utf-8')).hexdigest()[:32]
                idempotent_key = idem_key_hash
                
                self.logger.info(f"[IDEMPOTENCY] Generated key: {idempotent_key} (from: {idem_key_raw})")
            else:
                # Fallback: use symbol + timestamp if idempotency disabled
                idempotent_key = f"{symbol}_{int(time.time() * 1000)}"
                self.logger.warning("[IDEMPOTENCY] Disabled in config, using fallback key")

            # 6. === TRADE INTENT CONSTRUCTION ===
            # FIXED BUG-P1-001: Use str() instead of float() to preserve Decimal precision
            payoff_ratio_r = decimal.Decimal(str(decision_config['payoff_ratio_r']))
            valid_for_ms = self.config.get('system', {}).get('trade_intent_validity_ms', 30000)

            trade_intent_payload = {
                "instrument": symbol,
                "side": side,
                "idempotent_key": idempotent_key,  # For order deduplication
                "p": str(p),  # Preserve Decimal precision as string
                "payoff_ratio_r": str(payoff_ratio_r),  # Preserve Decimal precision as string
                "tca_budget": {
                    "max_slippage_bps": str(tca_prefs['max_slippage_bps']),  # Preserve Decimal precision as string
                    "max_latency_ms": int(tca_prefs['max_latency_ms']),  # Integer is safe
                    "maker_preference": str(tca_prefs['maker_preference'])
                },
                "risk_budget": {
                    "trade_cvar95_max_bps": str(risk_budgets['trade_cvar95_max_bps']),  # Preserve Decimal precision as string
                    "session_cvar95_max_bps": str(risk_budgets['session_cvar95_max_bps'])  # Preserve Decimal precision as string
                },
                "size": {
                    "kelly_fraction": str(kelly_fraction),  # Preserve Decimal precision as string
                    "notional_cap_usd": str(position_size)  # Preserve Decimal precision as string
                },
                "order": {
                    "price_ref": str(price_ref),  # Preserve Decimal precision as string
                    "qty": str(qty),  # Preserve Decimal precision as string
                    "price": str(price),  # Preserve Decimal precision as string
                    "reduce_only": False  # Opening position
                },
                "valid_for_ms": int(valid_for_ms),
                "why": [
                    f"Decision based on signal_score={float(signal_score):.3f}, p_src='{p_calibration_version}'",
                    f"Features: obi={float(obi):.3f}, tfi={float(tfi):.3f}, absorption={float(absorption):.3f}",
                    f"Probability: p_raw={float(p_raw):.3f}, p_cal={float(p_cal):.3f}, p={float(p):.3f} (ceiling={float(p_ceiling):.3f})",
                    f"EV: raw={float(ev_raw):.3f}, full_kelly={float(full_kelly):.4f}, kelly_used={float(kelly_used):.4f}",
                    f"CVaR: trade_usd=${float(cvar_trade_usd):.2f}, session_usd=${float(cvar_session_usd):.2f}",
                    f"Quality: grade={quality_grade}, p_calib={p_calib_metrics}",
                    "Risk approved: trading_allowed=True",
                    f"Position sizing: equity=${float(equity):.2f}, kelly_based_usd=${float(kelly_used * equity):.2f}, final=${float(position_size):.2f}"
                ],
                "dto_version": "1.0.0",
                "schema_ref": "https://aurora.scalp/shared/dto/trade_intent.schema.json"
            }

            # 6. === EMIT EVENT ===
            self.logger.info(f"Trade intent approved: {symbol} {side} p={float(p):.3f} size=${float(position_size):.2f}")
            
            # PRECISION VERIFICATION: Log payload sample to verify str() preservation
            self.logger.info(f"PRECISION CHECK - order.qty: {trade_intent_payload['order']['qty']} (type: {type(trade_intent_payload['order']['qty']).__name__})")
            self.logger.info(f"PRECISION CHECK - order.price: {trade_intent_payload['order']['price']} (type: {type(trade_intent_payload['order']['price']).__name__})")
            self.logger.info(f"PRECISION CHECK - order.price_ref: {trade_intent_payload['order']['price_ref']} (type: {type(trade_intent_payload['order']['price_ref']).__name__})")
            
            self.fsm.emit(
                "EVT:TRADE_INTENT_PROPOSED",
                payload=trade_intent_payload,
                why="Decision based on features, risk, and portfolio state."
            )

            # Clear state after successful decision emission to await a new full set of data
            self.clear_internal_state()

        except KeyError as e:
            self.logger.critical(f"Configuration key missing: {e}. System cannot make decisions. Please check trading.yaml. Halting decision.")
        except Exception as e:
            self.logger.error(f"Unexpected error in decision making: {e}", exc_info=True)
        finally:
            # Only clear state after a successful decision emission to await a new full set of data
            # Do NOT clear state when waiting for more data - that would lose partial progress
            pass

    def clear_internal_state(self) -> None:
        """
        Clear all internal state to prepare for the next decision cycle.

        This ensures that stale data doesn't persist between decision attempts
        and that each decision is made with a fresh set of current data.
        
        AURORA_STATE_SYNC_V1: Clearing portfolio forces re-fetch of fresh data,
        preventing position gating bypass with stale positions.
        """
        self.logger.debug("Clearing internal state for next decision cycle")
        self.latest_features = None
        self.latest_risk = None
        self.latest_portfolio = None  # FIXED: Clear portfolio to force fresh data (AURORA_STATE_SYNC_V1)

    def _validate_trade_intent(self, trade_intent: dict) -> bool:
        """
        Final validation of trade intent before emission.

        Args:
            trade_intent: The trade intent payload to validate

        Returns:
            bool: True if valid, False otherwise
        """
        try:
            # Validate required fields
            required_fields = ["instrument", "side", "p", "size"]
            for field in required_fields:
                if field not in trade_intent:
                    self.logger.error(f"Trade intent missing required field: {field}")
                    return False

            # Validate side
            if trade_intent["side"] not in ["buy", "sell"]:
                self.logger.error(f"Invalid trade side: {trade_intent['side']}")
                return False

            # Validate probability
            p = trade_intent.get("p", 0.0)
            if not (0.0 < p <= 1.0):
                self.logger.error(f"Invalid probability: {p}")
                return False

            # Validate size
            size = trade_intent.get("size", {})
            notional_cap = size.get("notional_cap_usd", 0.0)
            if notional_cap <= 0:
                self.logger.error(f"Invalid position size: {notional_cap}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error validating trade intent: {e}")
            return False

    def _compute_quality_grade(self, p: decimal.Decimal) -> str:
        """
        Compute quality grade based on probability.

        Args:
            p: Probability of success (0-1)

        Returns:
            str: Quality grade (A/B/C/D/F)
        """
        if p >= decimal.Decimal('0.8'):
            return "A"
        elif p >= decimal.Decimal('0.7'):
            return "B"
        elif p >= decimal.Decimal('0.6'):
            return "C"
        elif p >= decimal.Decimal('0.5'):
            return "D"
        else:
            return "F"

    def _calculate_expected_value(self, p: decimal.Decimal, r: decimal.Decimal) -> decimal.Decimal:
        """
        Calculate expected value of a trade.

        Args:
            p: Probability of success (0-1)
            r: Reward-to-risk ratio

        Returns:
            decimal.Decimal: Expected value
        """
        return p - (decimal.Decimal('1') - p) / r

    def _apply_caps(self, proposed_size: decimal.Decimal, cvar_cap: decimal.Decimal) -> decimal.Decimal:
        """
        Apply multi-cap constraints to proposed position size.

        Args:
            proposed_size: Kelly-based proposed size
            cvar_cap: CVaR-based cap

        Returns:
            decimal.Decimal: Final position size after caps, or 0 if below minimum
        """
        # Apply minimum size constraint first
        if proposed_size < self.min_pos_size_usd:
            return decimal.Decimal('0')

        # Apply multi-cap: min of proposed, CVaR, and liquidity
        final_size = min(proposed_size, cvar_cap, self.liq_cap_usd)
        return final_size