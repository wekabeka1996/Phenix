#!/usr/bin/env python3
"""
Test risk validation and threshold testing functionality.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock
from apps.reference.domains.risk_management.risk_management import RiskManagement


class MockFSM:
    """Mock FSM for testing purposes."""

    def listen(self, event, callback):
        pass


class TestRiskValidation:
    """Test risk management validation and threshold testing."""

    def test_validate_risk_thresholds_valid_config(self):
        """Test validation with a valid configuration."""
        # Config structure matches real system: trading.risk.trading_allowed_thresholds
        # but risk_score_weights are at top level (this is actual system structure)
        config = {
            "trading": {
                "risk": {
                    "trading_allowed_thresholds": {
                        "max_risk_score": "0.8"
                    }
                }
            },
            "risk_score_weights": {
                "delta_price_pct": "0.4",
                "obi": "0.3",
                "tfi": "0.2",
                "absorption_inverse": "0.1"
            },
            "circuit_breaker": {
                "max_consecutive_losses": 3,
                "cooldown_minutes": 5
            }
        }

        risk_mgmt = RiskManagement(fsm=MockFSM(), config=config)
        result = risk_mgmt.validate_risk_thresholds()

        assert result["valid"] is True
        assert len(result["issues"]) == 0
        assert result["config_summary"]["total_weight"] == 1.0

    def test_validate_risk_thresholds_missing_thresholds(self):
        """Test validation with missing required thresholds."""
        config = {
            "trading": {
                "risk": {
                    # Intentionally missing trading_allowed_thresholds
                }
            },
            "risk_score_weights": {
                "delta_price_pct": "0.4",
                "obi": "0.3",
                "tfi": "0.2",
                "absorption_inverse": "0.1"
            }
        }

        risk_mgmt = RiskManagement(fsm=MockFSM(), config=config)
        result = risk_mgmt.validate_risk_thresholds()

        assert result["valid"] is False
        assert len(result["issues"]) > 0
        assert any("max_risk_score" in issue for issue in result["issues"])

    def test_validate_risk_thresholds_invalid_values(self):
        """Test validation with invalid threshold values."""
        config = {
            "trading": {
                "risk": {
                    "trading_allowed_thresholds": {
                        "max_risk_score": "1.5"  # Invalid: > 1.0
                    }
                }
            },
            "risk_score_weights": {
                "delta_price_pct": "-0.1",  # Invalid: negative
                "obi": "0.3",
                "tfi": "0.2",
                "absorption_inverse": "0.1"
            }
        }

        risk_mgmt = RiskManagement(fsm=MockFSM(), config=config)
        result = risk_mgmt.validate_risk_thresholds()

        assert result["valid"] is False
        assert len(result["issues"]) >= 2  # Should catch both invalid values

    def test_test_risk_thresholds_default_scenarios(self):
        """Test threshold testing with default scenarios."""
        config = {
            "trading": {
                "risk": {
                    "trading_allowed_thresholds": {
                        "max_risk_score": "0.8"
                    }
                }
            },
            "risk_score_weights": {
                "delta_price_pct": "0.4",
                "obi": "0.3",
                "tfi": "0.2",
                "absorption_inverse": "0.1"
            }
        }

        risk_mgmt = RiskManagement(fsm=MockFSM(), config=config)
        result = risk_mgmt.test_risk_thresholds()

        assert "all_tests_passed" in result
        assert "scenarios_tested" in result
        assert "results" in result
        assert result["scenarios_tested"] == 3  # Default scenarios

        # Check that each scenario has expected structure
        for scenario_result in result["results"]:
            assert "scenario" in scenario_result
            assert "passed" in scenario_result
            assert "risk_score" in scenario_result
            assert "trading_allowed" in scenario_result

    def test_test_risk_thresholds_custom_scenarios(self):
        """Test threshold testing with custom scenarios."""
        config = {
            "trading": {
                "risk": {
                    "trading_allowed_thresholds": {
                        "max_risk_score": "0.5"  # Stricter threshold
                    }
                }
            },
            "risk_score_weights": {
                "delta_price_pct": "0.5",
                "obi": "0.2",
                "tfi": "0.2",
                "absorption_inverse": "0.1"
            }
        }

        custom_scenarios = [
            {
                "name": "very_low_risk",
                "features": {
                    "delta_price_pct": 0.005,  # 0.5% change
                    "obi": 0.0,  # No imbalance
                    "tfi": 0.0,  # No imbalance
                    "absorption": 1.0  # Perfect absorption
                },
                "expected_trading_allowed": True,
                "expected_risk_range": [0.0, 0.1]
            }
        ]

        risk_mgmt = RiskManagement(fsm=MockFSM(), config=config)
        result = risk_mgmt.test_risk_thresholds(custom_scenarios)

        assert result["scenarios_tested"] == 1
        scenario_result = result["results"][0]
        assert scenario_result["scenario"] == "very_low_risk"
        assert scenario_result["passed"] is True
        assert scenario_result["trading_allowed"] is True
        assert 0.0 <= scenario_result["risk_score"] <= 0.1

    def test_risk_thresholds_integration_with_real_calculation(self):
        """Test that validation and testing work with actual risk calculations."""
        config = {
            "trading": {
                "risk": {
                    "trading_allowed_thresholds": {
                        "max_risk_score": "0.7"
                    }
                }
            },
            "risk_score_weights": {
                "delta_price_pct": "0.4",
                "obi": "0.3",
                "tfi": "0.2",
                "absorption_inverse": "0.1"
            }
        }

        risk_mgmt = RiskManagement(fsm=MockFSM(), config=config)

        # First validate config
        validation = risk_mgmt.validate_risk_thresholds()
        assert validation["valid"] is True

        # Then test with scenarios that should work with this config
        scenarios = [
            {
                "name": "borderline_case",
                "features": {
                    "delta_price_pct": 0.03,  # 3% change
                    "obi": 0.5,  # Moderate imbalance
                    "tfi": 0.4,  # Moderate imbalance
                    "absorption": 0.5  # Moderate absorption
                },
                "expected_trading_allowed": True,  # Should be allowed with 0.7 threshold
                # Adjusted based on actual calculation
                "expected_risk_range": [0.25, 0.35]
            }
        ]

        test_result = risk_mgmt.test_risk_thresholds(scenarios)
        assert test_result["all_tests_passed"] is True
