"""
RiskManagement domain component.

Calculates risk parameters (kelly_fraction, cvar_limit_usd, max_drawdown_percent, is_trading_allowed)
from features data and emits EVT:RISK_ASSESSMENT_COMPLETED events.
"""
import decimal
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message

if TYPE_CHECKING:
    from vfoundation.core import FSMCore


logger = logging.getLogger(__name__)
chain_logger = logging.getLogger('event_chain')


class RiskManagement:
    """
    Risk management component that processes features and calculates risk parameters.

    Subscribes to EVT:FEATURES_CALCULATED and emits EVT:RISK_ASSESSMENT_COMPLETED.
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # Portfolio state tracking for holistic risk management
        self.portfolio_state: Optional[Dict[str, Any]] = None
        self.peak_equity: Optional[decimal.Decimal] = None
        self.current_daily_drawdown = decimal.Decimal('0')
        self.current_day: Optional[str] = None  # Track current trading day for daily drawdown reset

        # Subscribe to events
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features_calculated)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", self.on_portfolio_state_updated)

    def start(self) -> None:
        """Start the risk management component (subscription already done in __init__)."""
        pass

    def on_features_calculated(self, event: Message) -> None:
        """
        Handle incoming features calculated event and calculate risk parameters.

        Args:
            event: FSM event with features payload
        """
        # Generate RID for this processing chain
        rid = str(uuid.uuid4())

        self.logger.info("Handling EVT:FEATURES_CALCULATED...")
        payload = event.pld

        # Log event receipt to chain
        chain_logger.info("Event received", extra={
            'rid': rid,
            'event_type': 'EVT:FEATURES_CALCULATED',
            'domain': 'risk_management',
            'symbol': payload.get('symbol'),
            'stage': 'input'
        })

        # Extract required fields from payload
        symbol = payload["symbol"]
        timestamp = payload["ts"]
        features = payload["features"]

        # Calculate risk parameters
        risk_parameters = self._calculate_risk_parameters(features)

        # Create risk assessment payload
        risk_payload = {
            "symbol": symbol,
            "ts": timestamp,
            "risk_parameters": risk_parameters
        }

        # Emit risk assessment completed event
        self.logger.info("Emitting EVT:RISK_ASSESSMENT_COMPLETED...")
        self.fsm.emit(
            "EVT:RISK_ASSESSMENT_COMPLETED",
            payload=risk_payload,
            why="Risk parameters calculated based on new features."
        )

        # Log event emission to chain
        chain_logger.info("Event emitted", extra={
            'rid': rid,
            'event_type': 'EVT:RISK_ASSESSMENT_COMPLETED',
            'domain': 'risk_management',
            'symbol': symbol,
            'stage': 'output',
            'risk_assessment': {
                'is_trading_allowed': risk_parameters.get('is_trading_allowed'),
                'risk_score': risk_parameters.get('risk_score')
            }
        })

        symbol = event.pld.get("symbol", "unknown")
        self.logger.info(f"🎯 RiskManagement received FEATURES_CALCULATED for {symbol}")

    def on_portfolio_state_updated(self, event: Message) -> None:
        """
        Handle portfolio state updates to calculate portfolio-level risk metrics.
        """
        self.logger.info("Handling EVT:PORTFOLIO_STATE_UPDATED for risk assessment...")
        self.portfolio_state = event.pld
        current_equity = decimal.Decimal(str(self.portfolio_state.get('equity', '0')))

        # Check if we need to reset daily peak equity (new trading day)
        timestamp_ms = self.portfolio_state.get('ts', 0)
        current_date = datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d')

        if self.current_day != current_date:
            # New trading day - reset peak equity for daily drawdown calculation
            self.logger.info(f"New trading day detected ({current_date}). Resetting daily peak equity for drawdown calculation.")
            self.peak_equity = None
            self.current_day = current_date

        if self.peak_equity is None:
            self.peak_equity = current_equity

        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            self.current_daily_drawdown = drawdown if drawdown > 0 else decimal.Decimal('0')
            self.logger.info(
                f"Portfolio risk update: Equity=${current_equity:.2f}, "
                f"Peak Equity=${self.peak_equity:.2f}, Drawdown={self.current_daily_drawdown:.2%}"
            )

    def _calculate_risk_parameters(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculate risk parameters from features and portfolio state.
        This acts as a gatekeeper, checking both portfolio-level and instrument-level risk.
        """
        # 1. Portfolio-level risk check (Circuit Breaker)
        risk_config = self.config.get('risk', {})
        max_drawdown = decimal.Decimal(str(risk_config.get('max_daily_drawdown_limit', '0.10')))  # 10% default

        if self.current_daily_drawdown > max_drawdown:
            self.logger.critical(
                f"PORTFOLIO RISK BREACH: Daily drawdown {self.current_daily_drawdown:.2%} > {max_drawdown:.2%}. "
                f"Disabling all trading."
            )
            return {"is_trading_allowed": False}

        # 2. Instrument-level risk check (if portfolio risk is OK)
        # Extract features as Decimal
        obi = decimal.Decimal(str(features.get("obi", 0.0)))
        tfi = decimal.Decimal(str(features.get("tfi", 0.0)))
        delta_price = decimal.Decimal(str(features.get("delta_price", 0.0)))
        absorption = decimal.Decimal(str(features.get("absorption", 0.0)))

        # Calculate risk score for trading permission only
        # Using absorption and volatility as risk indicators
        score_weights = self.config.get('risk', {}).get('score_weights', {})
        delta_price_weight = decimal.Decimal(str(score_weights.get('delta_price', '0.1')))
        obi_weight = decimal.Decimal(str(score_weights.get('obi', '0.3')))
        tfi_weight = decimal.Decimal(str(score_weights.get('tfi', '0.3')))
        absorption_inverse_weight = decimal.Decimal(str(score_weights.get('absorption_inverse', '0.3')))
        # BUGFIX: delta_price is absolute ($), normalize to relative (%)
        # Get current price to calculate percentage change
        price_str = features.get("price")
        if price_str is None:
            self.logger.error("CRITICAL: Price data missing from features - disabling trading for safety")
            return {
                "is_trading_allowed": False,
                "error": "missing_price_data"
            }
        
        try:
            price = decimal.Decimal(str(price_str))
            if price <= 0:
                self.logger.error(f"CRITICAL: Invalid price {price} - disabling trading for safety")
                return {
                    "is_trading_allowed": False,
                    "error": "invalid_price_data"
                }
        except (ValueError, decimal.InvalidOperation) as e:
            self.logger.error(f"CRITICAL: Failed to parse price '{price_str}' - disabling trading for safety: {e}")
            return {
                "is_trading_allowed": False,
                "error": "price_parse_error"
            }
        
        delta_price_pct = abs(delta_price) / price
        # Risk score uses normalized features (all in [0, 1] range approximately)
        # - delta_price_pct: percentage change (0.01 = 1%)
        # - obi, tfi, absorption: already normalized to [-1, 1] or [0, 1]
        risk_score = (
            delta_price_pct * delta_price_weight
            + abs(obi) * obi_weight
            + abs(tfi) * tfi_weight
            + (decimal.Decimal('1') - absorption) * absorption_inverse_weight
        )
        # Determine if trading is allowed based on risk thresholds
        thresholds = self.config.get('risk', {}).get('trading_allowed_thresholds', {})
        max_risk_score = decimal.Decimal(str(thresholds.get('max_risk_score', '0.8')))
        is_trading_allowed = risk_score <= max_risk_score

        self.logger.info(
            f"Risk assessment: risk_score={float(risk_score):.4f}, "
            f"max_allowed={float(max_risk_score):.4f}, trading_allowed={is_trading_allowed}"
        )

        return {
            "is_trading_allowed": is_trading_allowed
            # Note: kelly_fraction and cvar_limit_usd are calculated in DecisionMaking from SSOT
        }

    def stop(self) -> None:
        """Stop the risk management component."""
        self.logger.info("RiskManagement stopped")
