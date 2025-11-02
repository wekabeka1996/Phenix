"""
RiskManagement domain component.

Calculates risk parameters (kelly_fraction, cvar_limit_usd, max_drawdown_percent, is_trading_allowed)
from features data and emits EVT:RISK_ASSESSMENT_COMPLETED events.
"""

import decimal
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TYPE_CHECKING

from vfoundation.core.protocol import Message

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

from vfoundation.core.why_codes import WhyCode, format_why_with_details


logger = logging.getLogger(__name__)
chain_logger = logging.getLogger("event_chain")


def _to_dec(x, default=decimal.Decimal("0")):
    """Safely convert value to Decimal, handling None and invalid inputs."""
    try:
        if x is None:
            return default
        return decimal.Decimal(str(x))
    except (decimal.InvalidOperation, ValueError, TypeError):
        return default


class RiskManagement:
    """
    Risk management component that processes features and calculates risk parameters.

    Subscribes to EVT:FEATURES_CALCULATED and emits EVT:RISK_ASSESSMENT_COMPLETED.
    """

    def __init__(self, fsm: "FSMCore", config: dict[str, Any]) -> None:
        self.fsm = fsm
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        # Portfolio state tracking for holistic risk management
        self.portfolio_state: Optional[Dict[str, Any]] = None
        self.peak_equity: Optional[decimal.Decimal] = None
        self.current_daily_drawdown = decimal.Decimal("0")

        # AGENT-PATCH: Daily reset state
        # Opening equity of the day
        self._equity_open: Optional[decimal.Decimal] = None
        # Last date when reset occurred (YYYY-MM-DD)
        self._last_reset_day: Optional[str] = None

        # Subscribe to events
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features_calculated)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self.on_portfolio_state_updated)

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
        print(f"DEBUG: risk_management payload = {payload}")
        print(f"DEBUG: risk_management payload type = {type(payload)}")

        # Log event receipt to chain
        chain_logger.info(
            "Event received",
            extra={
                "rid": rid,
                "event_type": "EVT:FEATURES_CALCULATED",
                "domain": "risk_management",
                "symbol": payload.get("symbol"),
                "stage": "input",
            },
        )

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
            "risk_parameters": risk_parameters,
        }

        # Emit risk assessment completed event
        self.logger.info("Emitting EVT:RISK_ASSESSMENT_COMPLETED...")
        self.fsm.emit(
            "EVT:RISK_ASSESSMENT_COMPLETED",
            payload=risk_payload,
            why="Risk parameters calculated based on new features.",
        )

        # Log event emission to chain
        chain_logger.info(
            "Event emitted",
            extra={
                "rid": rid,
                "event_type": "EVT:RISK_ASSESSMENT_COMPLETED",
                "domain": "risk_management",
                "symbol": symbol,
                "stage": "output",
                "risk_assessment": {
                    "is_trading_allowed": risk_parameters.get("is_trading_allowed"),
                    "risk_score": risk_parameters.get("risk_score"),
                },
            },
        )

    def on_portfolio_state_updated(self, event: Message) -> None:
        """
        Handle portfolio state updates to calculate portfolio-level risk metrics.

        AGENT-PATCH: Implement daily reset at start of trading day.
        """
        self.logger.info(
            "Handling EVT:PORTFOLIO_STATE_UPDATED for risk assessment...")
        self.portfolio_state = event.pld
        current_equity = decimal.Decimal(
            str(self.portfolio_state.get("equity", "0")))

        # AGENT-PATCH: Daily reset logic
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._last_reset_day != today_str or self._equity_open is None:
            # New day or first update: reset opening equity
            self._equity_open = current_equity
            self._last_reset_day = today_str
            self.logger.info(
                f"Daily reset: opening_equity={float(current_equity):.2f}, day={today_str}")

        # Calculate daily drawdown from opening equity
        if self._equity_open and self._equity_open > 0:
            drawdown_pct = max(
                decimal.Decimal("0"),
                (self._equity_open - current_equity) / self._equity_open * 100
            )
            self.current_daily_drawdown = drawdown_pct
        else:
            self.current_daily_drawdown = decimal.Decimal("0")

        self.logger.info(
            f"Portfolio risk update: Equity=${current_equity:.2f}, "
            f"Opening=${self._equity_open:.2f}, Drawdown={float(self.current_daily_drawdown):.2f}%"
        )

    def _calculate_risk_parameters(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculate risk parameters from features and portfolio state.
        This acts as a gatekeeper, checking both portfolio-level and instrument-level risk.

        AGENT-PATCH: Daily drawdown check with correct threshold reading.
        """
        # 1. Portfolio-level risk check (Circuit Breaker)
        # AGENT-PATCH: Safe reading of max_allowed from overrides/config/fallback
        risk_config = self.config.get("risk", {})

        # Try to read max_daily_drawdown_pct from different paths
        max_drawdown_pct = (
            risk_config.get("max_daily_drawdown_pct") or
            self.config.get("system", {}).get("risk", {}).get("max_daily_drawdown_limit") or
            10.0  # Default 10%
        )

        try:
            max_drawdown_pct = float(max_drawdown_pct)
        except (TypeError, ValueError):
            max_drawdown_pct = 10.0

        # Compare drawdown_pct directly (both in %)
        if self.current_daily_drawdown > decimal.Decimal(str(max_drawdown_pct)):
            self.logger.critical(
                f"PORTFOLIO RISK BREACH: Daily drawdown {float(self.current_daily_drawdown):.2f}% > {max_drawdown_pct:.2f}%. "
                f"Disabling all trading."
            )
            # XAI instrumentation: daily_drawdown gate
            logger.warning(
                format_why_with_details(
                    WhyCode.RISK_DRAWDOWN_LIMIT,
                    f"gate=daily_drawdown value={float(self.current_daily_drawdown):.4f} threshold={max_drawdown_pct:.4f}"
                )
            )
            return {"is_trading_allowed": False}

        # 2. Instrument-level risk check (if portfolio risk is OK)
        # Extract features with safe parsing
        obi = _to_dec(features.get("obi"))
        tfi = _to_dec(features.get("tfi"))
        delta_price = _to_dec(features.get("delta_price"))
        absorption = _to_dec(features.get("absorption"))

        # Calculate risk score for trading permission only
        # Using absorption and volatility as risk indicators
        score_weights = self.config.get("score_weights", {})
        delta_price_weight = _to_dec(score_weights.get("delta_price", "0.1"))
        obi_weight = _to_dec(score_weights.get("obi", "0.3"))
        tfi_weight = _to_dec(score_weights.get("tfi", "0.3"))
        absorption_inverse_weight = _to_dec(
            score_weights.get("absorption_inverse", "0.3"))

        # BUGFIX: delta_price is absolute ($), normalize to relative (%)
        # Get current price to calculate percentage change
        price = _to_dec(features.get("price", 1.0))  # Current price
        delta_price_pct = (
            (abs(delta_price) / price) if price > 0 else decimal.Decimal("0")
        )

        # Risk score uses normalized features (all in [0, 1] range approximately)
        # - delta_price_pct: percentage change (0.01 = 1% change)
        # - obi, tfi, absorption: already normalized to [-1, 1] or [0, 1]
        risk_score = (
            delta_price_pct * delta_price_weight
            + abs(obi) * obi_weight
            + abs(tfi) * tfi_weight
            + (decimal.Decimal("1") - absorption) * absorption_inverse_weight
        )

        # Clamp risk_score to [0, 1] range
        if risk_score < 0:
            risk_score = decimal.Decimal("0")
        if risk_score > 1:
            risk_score = decimal.Decimal("1")

        # Determine if trading is allowed based on risk thresholds
        thresholds = self.config.get("trading_allowed_thresholds", {})
        max_risk_score = _to_dec(thresholds.get("max_risk_score", "0.8"))
        is_trading_allowed = risk_score <= max_risk_score

        if not is_trading_allowed:
            # XAI instrumentation: score gate
            logger.warning(
                format_why_with_details(
                    WhyCode.RISK_SCORE_HIGH,
                    f"gate=score value={float(risk_score):.4f} threshold={float(max_risk_score):.4f}"
                )
            )

        self.logger.info(
            f"Risk assessment: risk_score={float(risk_score):.4f}, "
            f"max_allowed={float(max_risk_score):.4f}, trading_allowed={is_trading_allowed}"
        )

        return {
            "is_trading_allowed": is_trading_allowed,
            "risk_score": float(risk_score),  # Always numeric, never null
            # Note: kelly_fraction and cvar_limit_usd are calculated in DecisionMaking from SSOT
        }

    def stop(self) -> None:
        """Stop the risk management component."""
        self.logger.info("RiskManagement stopped")
