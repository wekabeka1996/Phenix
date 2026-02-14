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
from apps.reference.telemetry.alerts import AlertManager, AlertLevel, AlertType

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
        try:
            self.alert_manager: Optional[AlertManager] = AlertManager(config, logger=self.logger)
        except Exception as e:
            self.alert_manager = None
            self.logger.warning(f"AlertManager unavailable in RiskManagement: {e}")
        
        # Initialize Domain Config Resolver
        from apps.reference.domain_config import DomainConfigResolver
        self.resolver = DomainConfigResolver(config)
        self.domain_config = self.resolver.get_risk_management()

        # TASK47: DEV/SHADOW ONLY — disable daily loss/drawdown gate (never enable in live/prod).
        self._debug_disable_daily_loss_limit = bool(
            getattr(getattr(config.domains, "debug", None), "disable_daily_loss_limit", False)
        )
        if self._debug_disable_daily_loss_limit:
            self.logger.warning(
                "TASK47: DEBUG OVERRIDE ACTIVE: disable_daily_loss_limit=True (DEV/SHADOW ONLY)"
            )
            try:
                self.fsm.emit(
                    "EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE",
                    payload={"flag": "disable_daily_loss_limit", "why": "daily_loss_gate_disabled"},
                    why="debug_override_active",
                )
            except Exception:
                pass
        
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
        try:
            # Generate RID for this processing chain
            rid = str(uuid.uuid4())

            self.logger.info("Handling EVT:FEATURES_CALCULATED...")
            payload = event.pld  # type: ignore[union-attr]

            # Log event receipt to chain
            chain_logger.info(
                "Event received",
                extra={
                    "rid": rid,
                    "event_type": "EVT:FEATURES_CALCULATED",
                    "domain": "risk_management",
                    "symbol": payload.get("symbol") if isinstance(payload, dict) else None,
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
        except Exception as e:
            self.logger.exception("RiskManagement crash in on_features_calculated (fail-closed)")
            try:
                if self.alert_manager:
                    self.alert_manager.raise_alert(
                        level=AlertLevel.CRITICAL,
                        alert_type=AlertType.SYSTEM_HEALTH,
                        title="Risk Logic Crash",
                        message=str(e),
                        details={"domain": "risk_management"},
                    )
            except Exception:
                # Never allow alerting failures to crash the pipeline.
                pass
            return {"is_trading_allowed": False, "reason": "RISK_INTERNAL_ERROR"}  # type: ignore[return-value]

    def on_portfolio_state_updated(self, event: Message) -> None:
        """
        Handle portfolio state updates to update DailyRiskState.
        """
        self.logger.info("Handling EVT:PORTFOLIO_STATE_UPDATED for risk assessment...")
        self.portfolio_state = event.pld
        
        # Delegate to SSOT
        now_dt: Optional[datetime] = None
        try:
            pld = self.portfolio_state
            ts_ms = None
            if isinstance(pld, dict):
                # Prefer explicit portfolio event time when available.
                ts_ms = (
                    pld.get("event_time_ms")
                    or pld.get("ts_ms")
                    or pld.get("timestamp_ms")
                    or pld.get("ts")
                )
            if ts_ms not in (None, "", 0, "0"):
                ts_ms_i = int(ts_ms)
                # Backward compat: seconds timestamps.
                if 0 < ts_ms_i < 1_000_000_000_000:
                    ts_ms_i *= 1000
                now_dt = datetime.fromtimestamp(ts_ms_i / 1000, tz=timezone.utc)
        except Exception:
            now_dt = None

        self.daily_risk_state.on_portfolio(self.portfolio_state, now=now_dt)

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
            if getattr(self, "_debug_disable_daily_loss_limit", False):
                # DEV/SHADOW override: allow opens but surface the would-block reason.
                self.logger.warning(
                    f"TASK47: Daily gate would block ({daily_reason.get('detail')}), "
                    "but override active; allowing (why=daily_loss_gate_disabled)"
                )
                try:
                    self.fsm.emit(
                        "EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE",
                        payload={
                            "flag": "disable_daily_loss_limit",
                            "why": "daily_loss_gate_disabled",
                        },
                        why="debug_override_active",
                    )
                except Exception:
                    pass
                daily_reason = dict(daily_reason or {})
                daily_reason["would_block"] = True
                daily_reason["would_block_reason"] = daily_reason.get("why") or "daily_gate_blocked"
            else:
                # Blocked by Daily Gate (Enforced or Legacy)
                self.logger.critical(
                    f"PORTFOLIO RISK BLOCK: {daily_reason.get('detail')} - {daily_reason.get('why')}"
                )
                # Log specific why code
                detail = daily_reason["detail"] if "detail" in daily_reason else "UNKNOWN"
                val = daily_reason["drawdown_pct"] if "drawdown_pct" in daily_reason else "0"
                limit = daily_reason["limit_pct"] if "limit_pct" in daily_reason else "0"
                
                logger.warning(
                    format_why_with_details(
                        WhyCode.RISK_DRAWDOWN_LIMIT if "DRAWDOWN" in str(detail) else WhyCode.RISK_NOT_ALLOWED,
                        f"gate={detail} value={val} limit={limit}"
                    )
                )
                return {"is_trading_allowed": False}
            
        # Check shadow mode warning
        if bool(daily_reason["would_block"]) if "would_block" in daily_reason else False:
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

        required_thresholds = ["max_risk_score"]

        for threshold_name in required_thresholds:
            try:
                threshold_val = getattr(self.domain_config.trading_allowed_thresholds, threshold_name)
            except AttributeError:
                threshold_val = None
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
        required_weights = ["delta_price_pct",
                            "obi", "tfi", "absorption_inverse"]

        total_weight = decimal.Decimal("0")
        for weight_name in required_weights:
            try:
                weight_val = getattr(self.domain_config.risk_score_weights, weight_name)
            except AttributeError:
                weight_val = None
            if weight_val is None:
                issues.append(f"Missing required risk weight: {weight_name}")
            else:
                value = weight_val
                try:
                    dec_value = _to_dec(value)
                    if dec_value < 0:
                        issues.append(
                            f"Risk weight {weight_name}={value} cannot be negative")
                    total_weight += dec_value
                except (ValueError, TypeError):
                    issues.append(
                        f"Invalid risk weight value for {weight_name}: {value}")

        # Check total weight is reasonable (configured range)
        weight_min = decimal.Decimal(str(self.domain_config.validation.total_weight_min))
        weight_max = decimal.Decimal(str(self.domain_config.validation.total_weight_max))
        if total_weight < weight_min or total_weight > weight_max:
            warnings.append(
                f"Total risk weights sum to {float(total_weight):.3f}, expected ~1.0")

        circuit_breaker: dict[str, Any] = {}

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "config_summary": {
                "thresholds": self.domain_config.trading_allowed_thresholds.model_dump(mode="json"),
                "risk_weights": self.domain_config.risk_score_weights.model_dump(mode="json"),
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
            ConfigContractError: If weights are empty/missing (fail-closed)
        """
        weights = self.domain_config.risk_score_weights
        if weights is None:
            raise ConfigContractError(
                path="domains.risk_management.risk_score_weights",
                why="risk_score_weights empty or missing",
            )
        return weights

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
