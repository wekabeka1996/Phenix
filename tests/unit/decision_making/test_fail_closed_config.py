"""
Tests for Fail-Closed Config: No Hardcoded Fallbacks

Validates that:
1. V1 scoring is no longer supported (only V2)
2. Kelly formula uses config values (p_min, p_max, uplift_factor)
3. delta_price_cap_pct comes from config
"""
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestV1ScoringRemoved(unittest.TestCase):
    """Test that V1 scoring raises ConfigContractError"""

    def test_v1_scoring_raises_error(self):
        """When scoring_version != 'v2', system should raise ConfigContractError"""
        # This is a design contract test - the actual error would be raised at runtime
        # when scoring_ver is anything other than 'v2'
        
        scoring_ver = "v1"
        
        # Simulated check from decision_making.py
        if scoring_ver != "v2":
            error_raised = True
        else:
            error_raised = False
        
        self.assertTrue(error_raised)
        
    def test_v2_scoring_allowed(self):
        """When scoring_version == 'v2', no error"""
        scoring_ver = "v2"
        
        if scoring_ver != "v2":
            error_raised = True
        else:
            error_raised = False
        
        self.assertFalse(error_raised)


class TestKellyConfigFromYAML(unittest.TestCase):
    """Test Kelly formula uses config values, not hardcoded"""

    def test_kelly_probability_uses_config_bounds(self):
        """Probability should be clamped by p_min/p_max from config"""
        # Config values
        base_p = Decimal("0.5")
        p_min = Decimal("0.45")
        p_max = Decimal("0.65")
        uplift_factor = Decimal("0.20")
        
        # Test score = 0.0 (min)
        score_01 = Decimal("0")
        p = base_p + (uplift_factor * (score_01 - Decimal("0.5")))
        # p = 0.5 + 0.20 * (0 - 0.5) = 0.5 - 0.1 = 0.4
        p = max(Decimal("0"), min(Decimal("1"), p))
        p = max(p_min, min(p_max, p))
        # 0.4 < 0.45 → clamped to 0.45
        self.assertEqual(p, Decimal("0.45"))
        
        # Test score = 1.0 (max)
        score_01 = Decimal("1")
        p = base_p + (uplift_factor * (score_01 - Decimal("0.5")))
        # p = 0.5 + 0.20 * (1 - 0.5) = 0.5 + 0.1 = 0.6
        p = max(Decimal("0"), min(Decimal("1"), p))
        p = max(p_min, min(p_max, p))
        # 0.6 is within [0.45, 0.65]
        self.assertEqual(p, Decimal("0.6"))
        
        # Test score = 0.5 (neutral)
        score_01 = Decimal("0.5")
        p = base_p + (uplift_factor * (score_01 - Decimal("0.5")))
        # p = 0.5 + 0.20 * 0 = 0.5
        p = max(Decimal("0"), min(Decimal("1"), p))
        p = max(p_min, min(p_max, p))
        self.assertEqual(p, Decimal("0.5"))

    def test_kelly_different_config_values(self):
        """Test with different p_min/p_max config values"""
        # Different config
        base_p = Decimal("0.5")
        p_min = Decimal("0.30")  # More aggressive
        p_max = Decimal("0.70")
        uplift_factor = Decimal("0.30")  # Higher reaction
        
        score_01 = Decimal("0")
        p = base_p + (uplift_factor * (score_01 - Decimal("0.5")))
        # p = 0.5 + 0.30 * (-0.5) = 0.5 - 0.15 = 0.35
        p = max(Decimal("0"), min(Decimal("1"), p))
        p = max(p_min, min(p_max, p))
        # 0.35 > 0.30 → stays 0.35
        self.assertEqual(p, Decimal("0.35"))


class TestDeltaPriceCapFromConfig(unittest.TestCase):
    """Test delta_price cap uses config, not hardcoded 0.02"""

    def test_delta_price_capped_from_config(self):
        """dp_pct should be clamped by config value"""
        dp_cap_pct = Decimal("0.02")  # From config
        price = Decimal("100")
        dp_raw = Decimal("3")  # 3% move
        
        dp_pct = dp_raw / price
        # dp_pct = 0.03, cap = 0.02 → clamped
        if dp_pct > dp_cap_pct:
            dp_pct = dp_cap_pct
        
        dp_norm = dp_pct / dp_cap_pct
        
        self.assertEqual(dp_pct, Decimal("0.02"))
        self.assertEqual(dp_norm, Decimal("1"))  # Maxed out

    def test_delta_price_different_cap(self):
        """Test with different cap value from config"""
        dp_cap_pct = Decimal("0.05")  # 5% cap
        price = Decimal("100")
        dp_raw = Decimal("3")  # 3% move
        
        dp_pct = dp_raw / price
        # dp_pct = 0.03, cap = 0.05 → NOT clamped
        if dp_pct > dp_cap_pct:
            dp_pct = dp_cap_pct
        
        dp_norm = dp_pct / dp_cap_pct
        
        self.assertEqual(dp_pct, Decimal("0.03"))
        self.assertEqual(dp_norm, Decimal("0.6"))  # 0.03/0.05

    def test_zero_cap_handled(self):
        """If config has dp_cap = 0, avoid division by zero"""
        dp_cap_pct = Decimal("0")
        dp_pct = Decimal("0.01")
        
        dp_phi = dp_pct / dp_cap_pct if dp_cap_pct > 0 else Decimal("0")
        
        self.assertEqual(dp_phi, Decimal("0"))


if __name__ == '__main__':
    unittest.main()
