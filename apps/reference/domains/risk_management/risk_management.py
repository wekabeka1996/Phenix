"""
RiskManagement domain component.

Calculates risk parameters (kelly_fraction, cvar_limit_usd, max_drawdown_percent, is_trading_allowed)
from features data and emits EVT:RISK_ASSESSMENT_COMPLETED events.
"""

import decimal
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TYPE_CHECKING
from apps.reference.config_contract import ConfigContractError

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

    def __init__(self, fsm: "FSMCore", config: Any) -> None:
        """
        Initialize RiskManagement.
        
        Args:
            fsm: FSM core
            config: AuroraConfig object (Task 18: removed dict support)
        """
        self.fsm = fsm
        
        # Strict Object Config Check
        if isinstance(config, dict):
            raise TypeError("RiskManagement requires AuroraConfig, got dict")
            
        self.config = config
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        
        # Initialize Domain Config Resolver
        from apps.reference.domain_config import DomainConfigResolver
        self.resolver = DomainConfigResolver(config)
        self.domain_config = self.resolver.get_risk_management()
        
        # ETAP4: Unified Daily Risk State
        from apps.reference.domains.risk_management.daily_gate import DailyRiskState
        # Pass AuroraConfig directly (verified by DailyRiskState)
        self.daily_risk_state = DailyRiskState(config, logger=self.logger)
        
        # Portfolio state tracking for holistic risk management
        self.portfolio_state: Optional[Dict[str, Any]] = None

        # Subscribe to events
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features_calculated)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        self.on_portfolio_state_updated)
        
        # Listen to EVT:ORDER_FILLED to track realized PnL in DailyRiskState
        self.fsm.listen("EVT:ORDER_FILLED", self.on_order_filled)
        
        # D5: Cache absorption penalty flag (from strict object config)
        self._use_absorption_penalty = self.domain_config.use_absorption_penalty
        if not self._use_absorption_penalty:
            self.logger.warning(
                "D5: Absorption penalty DISABLED (use_absorption_penalty=False). "
                "Other risk weights are NOT rescaled."
            )

    def _get_use_absorption_penalty(self) -> bool:
        """Deprecated helper - removed."""
        return self.domain_config.use_absorption_penalty

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
        Handle portfolio state updates to update DailyRiskState.
        """
        self.logger.info("Handling EVT:PORTFOLIO_STATE_UPDATED for risk assessment...")
        self.portfolio_state = event.pld
        
        # Delegate to SSOT
        self.daily_risk_state.on_portfolio(self.portfolio_state)
        
    def on_order_filled(self, event: Message) -> None:
        """
        Handle order filled events to update realized PnL in DailyRiskState.
        """
        self.daily_risk_state.on_order_filled(event.pld)

    def _calculate_risk_parameters(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculate risk parameters from features and portfolio state.
        This acts as a gatekeeper, checking both portfolio-level and instrument-level risk.

        AGENT-PATCH: Daily drawdown check with correct threshold reading.
        """
        # 1. Portfolio-level risk check (Circuit Breaker)
        # 1. Portfolio-level risk check via DailyRiskState (SSOT)
        daily_allowed, daily_reason = self.daily_risk_state.can_open()
        
        if not daily_allowed:
            # Blocked by Daily Gate (Enforced or Legacy)
            self.logger.critical(
                f"PORTFOLIO RISK BLOCK: {daily_reason.get('detail')} - {daily_reason.get('why')}"
            )
            # Log specific why code
            detail = daily_reason.get("detail", "UNKNOWN")
            val = daily_reason.get("drawdown_pct", "0")
            limit = daily_reason.get("limit_pct", "0")
            
            logger.warning(
                format_why_with_details(
                    WhyCode.RISK_DRAWDOWN_LIMIT if "DRAWDOWN" in str(detail) else WhyCode.RISK_NOT_ALLOWED,
                    f"gate={detail} value={val} limit={limit}"
                )
            )
            return {"is_trading_allowed": False}
            
        # Check shadow mode warning
        if daily_reason.get("would_block", False):
             # Shadow mode detected a breach
             self.logger.warning(
                f"SHADOW RISK WARNING: {daily_reason.get('would_block_reason')} would block in enforced mode."
             )

        # 2. Instrument-level risk check (if portfolio risk is OK)
        # Extract features with safe parsing
        obi = _to_dec(features.get("obi"))
        tfi = _to_dec(features.get("tfi"))
        delta_price = _to_dec(features.get("delta_price"))
            # Absorption (Placeholder: default 0.0)
            # NOTE: D5 deprecation - absorption is now controlled by use_absorption_penalty flag.
            # When disabled, absorption term is excluded but other weights are NOT rescaled.
        absorption = _to_dec(features.get("absorption"))

        # Calculate risk score for trading permission only
        # Using absorption and volatility as risk indicators
        
        # SSOT: Get weights from config - REQUIRED, no fallbacks
        weights = self._get_risk_score_weights()
        delta_price_weight = decimal.Decimal(str(weights.delta_price_pct))
        obi_weight = decimal.Decimal(str(weights.obi))
        tfi_weight = decimal.Decimal(str(weights.tfi))
        
        # D5: Check absorption penalty flag
        if self._use_absorption_penalty:
            absorption_inverse_weight = decimal.Decimal(str(weights.absorption_inverse))
        else:
            # D5: Disable absorption term (weight=0) without rescaling other weights
            absorption_inverse_weight = decimal.Decimal("0")

        # BUGFIX: delta_price is absolute ($), normalize to relative (%)
        # Get current price to calculate percentage change
        price = _to_dec(features.get("price"))
        if price <= 0:
            raise ValueError(f"SSOT ERROR: Invalid price in features: {price}")
        delta_price_pct = abs(delta_price) / price

        # Risk score uses normalized features (all in [0, 1] range approximately)
        # - delta_price_pct: percentage change (0.01 = 1% change)
        # - obi, tfi, absorption: already normalized to [-1, 1] or [0, 1]
        # D5: absorption term is skipped when use_absorption_penalty=False
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

        # SSOT: Get max risk score threshold from config - REQUIRED
        max_risk_score = self._get_max_risk_score()

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

    def validate_risk_thresholds(self) -> dict[str, Any]:
        """
        Validate risk management thresholds and configuration.
        Returns validation results with any issues found.
        """
        issues = []
        warnings = []

        try:
            if hasattr(self.config, 'trading') and self.config.trading:
                thresholds = (
                    self.config.trading.risk.trading_allowed_thresholds
                    if self.config.trading.risk and self.config.trading.risk
                    else {}
                )
            elif isinstance(self.config, dict):
                thresholds = self.config.get("trading", {}).get(
                    "risk", {}).get("trading_allowed_thresholds", {})
            else:
                thresholds = {}
        except (AttributeError, TypeError):
            thresholds = {}

        required_thresholds = ["max_risk_score"]

        for threshold_name in required_thresholds:
            threshold_val = thresholds.get(threshold_name) if isinstance(thresholds, dict) else (
                getattr(thresholds, threshold_name, None) if hasattr(thresholds, threshold_name) else None)
            if threshold_val is None:
                issues.append(f"Missing required threshold: {threshold_name}")
            else:
                value = threshold_val
                try:
                    # Convert to decimal for validation
                    dec_value = _to_dec(value)
                    if dec_value < 0 or dec_value > 1:
                        issues.append(
                            f"Threshold {threshold_name}={value} must be in [0, 1] range")
                except (ValueError, TypeError):
                    issues.append(
                        f"Invalid threshold value for {threshold_name}: {value}")

        # Check risk score weights
        try:
            if hasattr(self.config, 'risk_score_weights') and self.config.risk_score_weights:
                risk_weights = self.config.risk_score_weights
            elif isinstance(self.config, dict):
                risk_weights = self.config.get("risk_score_weights", {})
            else:
                risk_weights = {}
        except (AttributeError, TypeError):
            risk_weights = {}

        required_weights = ["delta_price_pct",
                            "obi", "tfi", "absorption_inverse"]

        total_weight = decimal.Decimal("0")
        for weight_name in required_weights:
            weight_val = risk_weights.get(weight_name) if isinstance(risk_weights, dict) else (
                getattr(risk_weights, weight_name, None) if hasattr(risk_weights, weight_name) else None)
            if weight_val is None:
                issues.append(f"Missing required risk weight: {weight_name}")
            else:
                value = risk_weights[weight_name]
                try:
                    dec_value = _to_dec(value)
                    if dec_value < 0:
                        issues.append(
                            f"Risk weight {weight_name}={value} cannot be negative")
                    total_weight += dec_value
                except (ValueError, TypeError):
                    issues.append(
                        f"Invalid risk weight value for {weight_name}: {value}")

        # Check total weight is reasonable (should sum to ~1.0)
        if total_weight < decimal.Decimal("0.5") or total_weight > decimal.Decimal("2.0"):
            warnings.append(
                f"Total risk weights sum to {float(total_weight):.3f}, expected ~1.0")

        # Check circuit breaker settings
        try:
            if hasattr(self.config, 'circuit_breaker'):
                circuit_breaker = self.config.circuit_breaker if self.config.circuit_breaker else {}
            elif isinstance(self.config, dict):
                circuit_breaker = self.config.get("circuit_breaker", {})
            else:
                circuit_breaker = {}
        except (AttributeError, TypeError):
            circuit_breaker = {}

        if isinstance(circuit_breaker, dict) and "max_consecutive_losses" in circuit_breaker:
            max_losses = circuit_breaker["max_consecutive_losses"]
            if not isinstance(max_losses, int) or max_losses < 1:
                issues.append(
                    f"max_consecutive_losses must be positive integer, got: {max_losses}")
        elif hasattr(circuit_breaker, 'max_consecutive_losses'):
            max_losses = circuit_breaker.max_consecutive_losses
            if not isinstance(max_losses, int) or max_losses < 1:
                issues.append(
                    f"max_consecutive_losses must be positive integer, got: {max_losses}")

        if isinstance(circuit_breaker, dict) and "cooldown_minutes" in circuit_breaker:
            cooldown = circuit_breaker["cooldown_minutes"]
            if not isinstance(cooldown, (int, float)) or cooldown < 0:
                issues.append(
                    f"cooldown_minutes must be non-negative number, got: {cooldown}")
        elif hasattr(circuit_breaker, 'cooldown_minutes'):
            cooldown = circuit_breaker.cooldown_minutes
            if not isinstance(cooldown, (int, float)) or cooldown < 0:
                issues.append(
                    f"cooldown_minutes must be non-negative number, got: {cooldown}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "config_summary": {
                "thresholds": thresholds,
                "risk_weights": risk_weights,
                "total_weight": float(total_weight),
                "circuit_breaker": circuit_breaker
            }
        }

    def test_risk_thresholds(self, test_scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """
        Test risk thresholds against predefined scenarios to ensure they work as expected.
        Returns test results with pass/fail status.
        """
        if test_scenarios is None:
            # Default test scenarios
            test_scenarios = [
                {
                    "name": "low_risk_normal_market",
                    "features": {
                        "delta_price_pct": 0.01,  # 1% change
                        "obi": 0.1,  # Mild order book imbalance
                        "tfi": 0.05,  # Low trade flow imbalance
                        "absorption": 0.9  # Good absorption
                    },
                    "expected_trading_allowed": True,
                    "expected_risk_range": [0.0, 0.3]
                },
                {
                    "name": "high_risk_volatile_market",
                    "features": {
                        "delta_price_pct": 0.05,  # 5% change
                        "obi": 0.8,  # Strong order book imbalance
                        "tfi": 0.7,  # High trade flow imbalance
                        "absorption": 0.2  # Poor absorption
                    },
                    "expected_trading_allowed": False,
                    "expected_risk_range": [0.7, 1.0]
                },
                {
                    "name": "medium_risk_mixed_signals",
                    "features": {
                        "delta_price_pct": 0.02,  # 2% change
                        "obi": 0.4,  # Moderate order book imbalance
                        "tfi": 0.3,  # Moderate trade flow imbalance
                        "absorption": 0.6  # Moderate absorption
                    },
                    "expected_trading_allowed": True,
                    "expected_risk_range": [0.3, 0.7]
                }
            ]

        results = []
        all_passed = True

        for scenario in test_scenarios:
            try:
                # Calculate risk assessment for this scenario
                # Convert delta_price_pct back to absolute delta_price for the method
                features = scenario["features"].copy()
                if "delta_price_pct" in features:
                    # Assume a base price of 100 for testing
                    features["delta_price"] = features["delta_price_pct"] * 100
                    features["price"] = 100.0
                    del features["delta_price_pct"]

                assessment = self._calculate_risk_parameters(features)

                # Check expectations
                trading_allowed_ok = assessment["is_trading_allowed"] == scenario["expected_trading_allowed"]
                risk_in_range = (scenario["expected_risk_range"][0] <=
                                 assessment["risk_score"] <= scenario["expected_risk_range"][1])

                scenario_passed = trading_allowed_ok and risk_in_range

                results.append({
                    "scenario": scenario["name"],
                    "passed": scenario_passed,
                    "risk_score": assessment["risk_score"],
                    "trading_allowed": assessment["is_trading_allowed"],
                    "expected_trading_allowed": scenario["expected_trading_allowed"],
                    "expected_risk_range": scenario["expected_risk_range"],
                    "checks": {
                        "trading_allowed_correct": trading_allowed_ok,
                        "risk_in_expected_range": risk_in_range
                    }
                })

                if not scenario_passed:
                    all_passed = False

            except Exception as e:
                results.append({
                    "scenario": scenario["name"],
                    "passed": False,
                    "error": str(e)
                })
                all_passed = False

        return {
            "all_tests_passed": all_passed,
            "scenarios_tested": len(results),
            "results": results
        }

    def _get_risk_score_weights(self):
        """
        Get risk score weights from config. SSOT - no fallbacks.
        
        Returns:
            Config object with delta_price_pct, obi, tfi, absorption_inverse
            
        Raises:
            ValueError: If config is missing required section
        """
        # Try domains config (preferred)
        if hasattr(self.config, 'domains') and hasattr(self.config.domains, 'risk_management'):
            weights = getattr(self.config.domains.risk_management, 'risk_score_weights', None)
            if weights is not None:
                return weights
        
        # Try dict config
        if isinstance(self.config, dict):
            # Strict dict access (Contract P1)
            try:
                weights = self.config["domains"]["risk_management"]["risk_score_weights"]
            except KeyError:
                weights = None
            
            if not weights:
                raise ConfigContractError(path="domains.risk_management.risk_score_weights", why="Dict is empty or missing")

                # Convert to object-like for consistent access
                class WeightsObj:
                    pass
                obj = WeightsObj()
                
                # STRICT: No defaults. If key missing, let it be None (or fail validation downstream)
                # But here we want to ensure we don't inject defaults.
                # Actually earlier validation checks for None.
                for key in ["delta_price_pct", "obi", "tfi", "absorption_inverse"]:
                    if key not in weights:
                        raise ConfigContractError(
                            path=f"domains.risk_management.risk_score_weights.{key}", 
                            why="Missing required weight key"
                        )
                    setattr(obj, key, weights[key])
                return obj
        
        # FINAL FALLBACK: Fail closed
        # Production MUST have domains.risk_management.risk_score_weights
        raise ConfigContractError(
            path="domains.risk_management.risk_score_weights",
            why="empty or missing"
        )

    def _get_max_risk_score(self) -> decimal.Decimal:
        """
        Get max risk score threshold from config. SSOT - no fallbacks.
        
        Returns:
            Decimal threshold value
            
        Raises:
            ConfigContractError: If config is missing required value (fail-closed)
        """
        # Direct Pydantic access (fail-closed: missing field → AttributeError → crash)
        # Trading allowed thresholds are CRITICAL - no silent defaults
        try:
            thresholds = self.config.domains.risk_management.trading_allowed_thresholds
            max_risk = thresholds.max_risk_score
            return decimal.Decimal(str(max_risk))
        except AttributeError as e:
            # CRITICAL: trading_allowed_thresholds missing → BLOCK trading
            raise ConfigContractError(
                path="domains.risk_management.trading_allowed_thresholds.max_risk_score",
                why=f"Missing SSOT config: {e}"
            )
        
        # FINAL FALLBACK: Fail closed should not be reachable if try/except covers it, 
        # but if structure is wildly different:
        raise ConfigContractError(
            path="domains.risk_management.trading_allowed_thresholds.max_risk_score",
            why="Unreachable fallback triggered"
        )

    def stop(self) -> None:
        """Stop the risk management component."""
        self.logger.info("RiskManagement stopped")
