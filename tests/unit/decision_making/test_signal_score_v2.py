import unittest
from decimal import Decimal
from apps.reference.domains.decision_making.signal_score_v2 import SignalScoreV2, ScoreResult

class TestSignalScoreV2(unittest.TestCase):
    def setUp(self):
        self.weights = {
            "obi": 0.5,
            "tfi": 0.5,
            "delta_price": 0.2
        }
        self.neutrals = {
            "obi": 0.0,
            "tfi": 0.0,
            "delta_price": 0.0
        }
        self.readiness = {
            "obi": True,
            "tfi": True,
            "delta_price": True
        }
        self.essential = {"obi"}
        
    def test_basic_score(self):
        features = {
            "obi": 0.5,
            "tfi": 0.5,
            "delta_price": 0.1
        }
        # w_i * (val - neutral)
        # obi: 0.5 * (0.5 - 0) = 0.25
        # tfi: 0.5 * (0.5 - 0) = 0.25
        # dp:  0.2 * (0.1 - 0) = 0.02
        # sum = 0.52
        # wabs = 0.5+0.5+0.2 = 1.2
        # score = 0.52 / 1.2 = 0.4333
        
        result = SignalScoreV2.calculate_score(
            features, self.weights, self.neutrals, self.readiness, set(), "TEST"
        )
        self.assertAlmostEqual(float(result.score), 0.4333333, places=5)
        self.assertFalse(result.deferred)
        
    def test_neutral_offset(self):
        neutrals = self.neutrals.copy()
        neutrals["obi"] = 0.5
        
        features = {
            "obi": 0.5, # Should result in 0 contribution
            "tfi": 0.5,
            "delta_price": 0.1
        }
        # obi: 0.5 * (0.5 - 0.5) = 0
        # tfi: 0.5 * 0.5 = 0.25
        # dp: 0.02
        # sum = 0.27
        # wabs = 1.2
        # score = 0.225
        
        result = SignalScoreV2.calculate_score(
            features, self.weights, neutrals, self.readiness, set(), "TEST"
        )
        self.assertAlmostEqual(float(result.score), 0.225, places=5)

    def test_essential_missing(self):
        features = {
            "tfi": 0.5,
            "delta_price": 0.1
        }
        # 'obi' is essential but missing
        result = SignalScoreV2.calculate_score(
            features, self.weights, self.neutrals, self.readiness, self.essential, "TEST"
        )
        self.assertTrue(result.deferred)
        self.assertIn("obi", result.missing_features)
        self.assertEqual(result.score, Decimal("0"))

    def test_essential_not_ready(self):
        features = {
            "obi": 0.5,
            "tfi": 0.5,
            "delta_price": 0.1
        }
        readiness = self.readiness.copy()
        readiness["obi"] = False
        
        result = SignalScoreV2.calculate_score(
            features, self.weights, self.neutrals, readiness, self.essential, "TEST"
        )
        self.assertTrue(result.deferred)
        self.assertIn("obi", result.not_ready_features)

    def test_non_essential_missing_skips_score(self):
        features = {
            "obi": 0.5, # essential, present
            # tfi missing (non-essential)
            "delta_price": 0.1
        }
        # obi: 0.25
        # dp: 0.02
        # sum = 0.27
        # wabs = 0.5 (obi) + 0.2 (dp) = 0.7 (SKIP tfi)
        # score = 0.27 / 0.7 = 0.3857
        
        result = SignalScoreV2.calculate_score(
            features, self.weights, self.neutrals, self.readiness, self.essential, "TEST"
        )
        self.assertFalse(result.deferred)
        self.assertAlmostEqual(float(result.score), 0.385714, places=5)
        self.assertAlmostEqual(float(result.wabs), 0.7)

    def test_zero_weights_ignored(self):
        weights = self.weights.copy()
        weights["tfi"] = 0.0
        
        features = {
            "obi": 0.5,
            "tfi": 0.9, # Should be ignored
            "delta_price": 0.1
        }
        # obi: 0.25
        # dp: 0.02
        # sum = 0.27
        # wabs = 0.5 + 0.2 = 0.7
        
        result = SignalScoreV2.calculate_score(
            features, weights, self.neutrals, self.readiness, set(), "TEST"
        )
        self.assertAlmostEqual(float(result.score), 0.385714, places=5)

    def test_validation_fail(self):
        weights = {"foo": 1.0}
        neutrals = {} # Missing foo
        
        with self.assertRaises(ValueError):
            SignalScoreV2.validate_config(weights, neutrals, "TEST")

if __name__ == '__main__':
    unittest.main()
