"""
Test suite for D5 - Absorption Deprecation Flag.

Tests validate:
1. Flag=True → absorption impacts risk score (opt-in)
2. Flag=False → absorption does NOT impact risk score
3. Other weights are NOT rescaled when absorption disabled
4. Config loading works correctly
"""
import decimal
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any
import logging

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_fsm():
    """Create a mock FSMCore."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()
    return fsm


@pytest.fixture
def base_features():
    """Create base features for testing."""
    return {
        "symbol": "BTCUSDT",
        "price": 50000.0,
        "delta_price": 50.0,  # $50 change
        "obi": 0.3,  # Order book imbalance
        "tfi": 0.2,  # Trade flow imbalance
        "absorption": 0.0,  # Zero absorption (placeholder value)
    }


@pytest.fixture
def risk_management_with_absorption_enabled(mock_fsm):
    """Create RiskManagement with absorption enabled (default)."""
    from apps.reference.domains.risk_management.risk_management import RiskManagement
    
    config = MagicMock()
    config.domains = MagicMock()
    config.domains.risk_management = MagicMock()
    config.domains.risk_management.use_absorption_penalty = True
    config.domains.risk_management.risk_score_weights = MagicMock(
        delta_price_pct=0.1,
        obi=0.3,
        tfi=0.3,
        absorption_inverse=0.3,
    )
    config.domains.risk_management.trading_allowed_thresholds = MagicMock(
        max_risk_score=0.8
    )
    
    # Patch daily_gate import (imported inside __init__)
    with patch('apps.reference.domains.risk_management.daily_gate.DailyRiskState'):
        rm = RiskManagement(mock_fsm, config)
    
    return rm


@pytest.fixture
def risk_management_with_absorption_disabled(mock_fsm):
    """Create RiskManagement with absorption disabled."""
    from apps.reference.domains.risk_management.risk_management import RiskManagement
    
    config = MagicMock()
    config.domains = MagicMock()
    config.domains.risk_management = MagicMock()
    config.domains.risk_management.use_absorption_penalty = False  # DISABLED
    config.domains.risk_management.risk_score_weights = MagicMock(
        delta_price_pct=0.1,
        obi=0.3,
        tfi=0.3,
        absorption_inverse=0.3,  # Still configured, but ignored
    )
    config.domains.risk_management.trading_allowed_thresholds = MagicMock(
        max_risk_score=0.8
    )
    
    # Patch daily_gate import (imported inside __init__)
    with patch('apps.reference.domains.risk_management.daily_gate.DailyRiskState'):
        rm = RiskManagement(mock_fsm, config)
    
    return rm


# =============================================================================
# CONFIG LOADING TESTS
# =============================================================================

class TestAbsorptionConfigLoading:
    """Tests for use_absorption_penalty config loading."""

    def test_default_is_disabled(self, mock_fsm):
        """Default must be False so placeholder absorption never affects default risk."""
        from apps.reference.domains.risk_management.risk_management import RiskManagement
        
        # Config without use_absorption_penalty
        config = MagicMock()
        config.domains = MagicMock()
        config.domains.risk_management = MagicMock(spec=[])  # No use_absorption_penalty
        
        with patch('apps.reference.domains.risk_management.daily_gate.DailyRiskState'):
            rm = RiskManagement(mock_fsm, config)
        
        assert rm._use_absorption_penalty is False

    def test_config_true_is_enabled(self, risk_management_with_absorption_enabled):
        """Test that explicit True enables absorption."""
        rm = risk_management_with_absorption_enabled
        assert rm._use_absorption_penalty is True

    def test_config_false_is_disabled(self, risk_management_with_absorption_disabled):
        """Test that False disables absorption."""
        rm = risk_management_with_absorption_disabled
        assert rm._use_absorption_penalty is False


# =============================================================================
# RISK SCORE CALCULATION TESTS
# =============================================================================

class TestAbsorptionImpactOnRiskScore:
    """Tests for absorption's impact on risk score calculation."""

    def test_absorption_enabled_affects_score(self, risk_management_with_absorption_enabled, base_features):
        """Test that absorption=0.0 with flag=True adds penalty to risk score."""
        rm = risk_management_with_absorption_enabled
        
        # Mock daily risk state - must return tuple (allowed, reason_dict)
        rm.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        rm._get_risk_score_weights = MagicMock(return_value=MagicMock(
            delta_price_pct=0.1,
            obi=0.3,
            tfi=0.3,
            absorption_inverse=0.3,
        ))
        rm._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        
        result = rm._calculate_risk_parameters(base_features)
        
        risk_score = result["risk_score"]
        
        # With absorption=0.0 and weight=0.3: (1 - 0) * 0.3 = 0.3 added
        # Expected: delta_price_pct * 0.1 + obi * 0.3 + tfi * 0.3 + absorption_penalty * 0.3
        # 0.001 * 0.1 + 0.3 * 0.3 + 0.2 * 0.3 + 1.0 * 0.3 = 0.0001 + 0.09 + 0.06 + 0.3 = 0.4501
        assert risk_score > 0.3  # Absorption adds significant penalty

    def test_absorption_disabled_no_penalty(self, risk_management_with_absorption_disabled, base_features):
        """Test that absorption=0.0 with flag=False adds NO penalty."""
        rm = risk_management_with_absorption_disabled
        
        # Mock daily risk state - must return tuple (allowed, reason_dict)
        rm.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        rm._get_risk_score_weights = MagicMock(return_value=MagicMock(
            delta_price_pct=0.1,
            obi=0.3,
            tfi=0.3,
            absorption_inverse=0.3,  # Configured but ignored
        ))
        rm._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        
        result = rm._calculate_risk_parameters(base_features)
        
        risk_score = result["risk_score"]
        
        # With absorption disabled: no 0.3 penalty
        # Expected: delta_price_pct * 0.1 + obi * 0.3 + tfi * 0.3 = 0.0001 + 0.09 + 0.06 = 0.1501
        assert risk_score < 0.25  # Much lower without absorption penalty

    def test_default_config_placeholder_absorption_does_not_change_score(self, mock_fsm, base_features):
        """Placeholder absorption must not affect risk_score under default config."""
        from apps.reference.domains.risk_management.risk_management import RiskManagement

        config = MagicMock()
        config.domains = MagicMock()
        config.domains.risk_management = MagicMock(spec=[])

        with patch('apps.reference.domains.risk_management.daily_gate.DailyRiskState'):
            rm = RiskManagement(mock_fsm, config)

        rm.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        rm._get_risk_score_weights = MagicMock(return_value=MagicMock(
            delta_price_pct=0.1,
            obi=0.3,
            tfi=0.3,
            absorption_inverse=0.3,
        ))
        rm._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))

        low_abs = base_features.copy()
        low_abs["absorption"] = 0.0
        high_abs = base_features.copy()
        high_abs["absorption"] = 0.9

        score_low = rm._calculate_risk_parameters(low_abs)["risk_score"]
        score_high = rm._calculate_risk_parameters(high_abs)["risk_score"]
        assert abs(score_low - score_high) < 1e-9


# =============================================================================
# NO RESCALE TESTS
# =============================================================================

class TestNoRescaleOnAbsorptionDisable:
    """Tests that other weights are NOT rescaled when absorption disabled."""

    def test_other_weights_unchanged(self, risk_management_with_absorption_enabled, 
                                     risk_management_with_absorption_disabled, 
                                     base_features):
        """Test that obi, tfi, delta_price weights are same with/without absorption."""
        rm_enabled = risk_management_with_absorption_enabled
        rm_disabled = risk_management_with_absorption_disabled
        
        # Same weight config for both
        weights_config = MagicMock(
            delta_price_pct=0.1,
            obi=0.3,
            tfi=0.3,
            absorption_inverse=0.3,
        )
        
        rm_enabled._get_risk_score_weights = MagicMock(return_value=weights_config)
        rm_disabled._get_risk_score_weights = MagicMock(return_value=weights_config)
        rm_enabled._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        rm_disabled._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        rm_enabled.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        rm_disabled.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        
        # Features with absorption=1.0 (no penalty from absorption term)
        features_no_absorption_penalty = base_features.copy()
        features_no_absorption_penalty["absorption"] = 1.0
        
        result_enabled = rm_enabled._calculate_risk_parameters(features_no_absorption_penalty)
        result_disabled = rm_disabled._calculate_risk_parameters(features_no_absorption_penalty)
        
        # With absorption=1.0, the term is (1-1)*0.3 = 0 for enabled
        # For disabled, absorption term is always 0
        # So both should give same score when absorption=1.0
        assert abs(result_enabled["risk_score"] - result_disabled["risk_score"]) < 0.01

    def test_difference_only_in_absorption_term(self, risk_management_with_absorption_enabled,
                                                 risk_management_with_absorption_disabled,
                                                 base_features):
        """Test that the only difference is the absorption term."""
        rm_enabled = risk_management_with_absorption_enabled
        rm_disabled = risk_management_with_absorption_disabled
        
        weights_config = MagicMock(
            delta_price_pct=0.1,
            obi=0.3,
            tfi=0.3,
            absorption_inverse=0.3,
        )
        
        rm_enabled._get_risk_score_weights = MagicMock(return_value=weights_config)
        rm_disabled._get_risk_score_weights = MagicMock(return_value=weights_config)
        rm_enabled._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        rm_disabled._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        rm_enabled.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        rm_disabled.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        
        # absorption=0.0 → penalty = (1-0)*0.3 = 0.3
        features = base_features.copy()
        features["absorption"] = 0.0
        
        result_enabled = rm_enabled._calculate_risk_parameters(features)
        result_disabled = rm_disabled._calculate_risk_parameters(features)
        
        # The difference should be exactly the absorption penalty
        diff = result_enabled["risk_score"] - result_disabled["risk_score"]
        
        # Expected diff: (1 - 0) * 0.3 = 0.3
        assert abs(diff - 0.3) < 0.01


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestAbsorptionDeprecationRegression:
    """Regression tests for absorption deprecation."""

    def test_enabled_flag_is_backward_compatible(self, mock_fsm, base_features):
        """Test that enabled flag produces same results as before deprecation."""
        from apps.reference.domains.risk_management.risk_management import RiskManagement
        
        config = MagicMock()
        config.domains = MagicMock()
        config.domains.risk_management = MagicMock()
        config.domains.risk_management.use_absorption_penalty = True  # Enabled
        
        with patch('apps.reference.domains.risk_management.daily_gate.DailyRiskState'):
            rm = RiskManagement(mock_fsm, config)
        
        # The flag should be True
        assert rm._use_absorption_penalty is True
        
        # Risk calculation should include absorption term
        # (verified in other tests)

    def test_disabled_does_not_break_trading_allowed(self, risk_management_with_absorption_disabled, base_features):
        """Test that disabling absorption doesn't break is_trading_allowed logic."""
        rm = risk_management_with_absorption_disabled
        
        rm.daily_risk_state.can_open = MagicMock(return_value=(True, {}))
        rm._get_risk_score_weights = MagicMock(return_value=MagicMock(
            delta_price_pct=0.1, obi=0.3, tfi=0.3, absorption_inverse=0.3
        ))
        rm._get_max_risk_score = MagicMock(return_value=decimal.Decimal("0.8"))
        
        result = rm._calculate_risk_parameters(base_features)
        
        # Should have is_trading_allowed key
        assert "is_trading_allowed" in result
        assert isinstance(result["is_trading_allowed"], bool)
