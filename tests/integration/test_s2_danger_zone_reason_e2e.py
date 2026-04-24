"""
S2-2: Integration test — DangerZone reason format end-to-end.

Verifies the exact reason string format produced by DangerZoneShield for each
trigger type, and that these reasons propagate through ShieldCascade correctly.
"""
import unittest

from apps.reference.shared.decision_primitives.shields.danger_zone import (
    DangerZoneShield,
)
from apps.reference.shared.decision_primitives.shields.base import ShieldCascade


class TestDangerZoneReasonFormat(unittest.TestCase):
    """Verify DangerZone reason strings follow DANGER_ZONE:<metric>=<val>><thr> format."""

    def test_vol_reason_format(self):
        """vol trigger → 'DANGER_ZONE:vol=<float>><threshold>'"""
        shield = DangerZoneShield(vol_threshold=0.9)
        result = shield.evaluate("BTC", {"volatility_state": 0.95}, 0.5, 0.25)
        self.assertEqual(result.multiplier, 0.0)
        reason = result.reasons[0]
        self.assertTrue(
            reason.startswith("DANGER_ZONE:vol="),
            f"Expected DANGER_ZONE:vol=..., got: {reason}",
        )
        self.assertIn(">0.9", reason)

    def test_spread_reason_format(self):
        """spread trigger → 'DANGER_ZONE:spread=<float>bps><threshold>'"""
        shield = DangerZoneShield(spread_threshold=30.0)
        result = shield.evaluate("BTC", {"spread_bps": 50.0}, 0.5, 0.25)
        self.assertEqual(result.multiplier, 0.0)
        reason = result.reasons[0]
        self.assertTrue(
            reason.startswith("DANGER_ZONE:spread="),
            f"Expected DANGER_ZONE:spread=..., got: {reason}",
        )
        self.assertIn("bps>", reason)

    def test_motion_reason_format(self):
        """motion trigger → 'DANGER_ZONE:motion=<float>σ><threshold>'"""
        shield = DangerZoneShield(motion_threshold=3.0)
        result = shield.evaluate("BTC", {"price_motion_norm": 4.5}, 0.5, 0.25)
        self.assertEqual(result.multiplier, 0.0)
        reason = result.reasons[0]
        self.assertTrue(
            reason.startswith("DANGER_ZONE:motion="),
            f"Expected DANGER_ZONE:motion=..., got: {reason}",
        )
        self.assertIn("σ>", reason)

    def test_no_trigger_empty_reasons(self):
        """Below all thresholds → multiplier 1.0, no reasons."""
        shield = DangerZoneShield(
            vol_threshold=0.95, spread_threshold=50.0, motion_threshold=3.0
        )
        result = shield.evaluate(
            "BTC",
            {"volatility_state": 0.5, "spread_bps": 10.0, "price_motion_norm": 1.0},
            0.5,
            0.25,
        )
        self.assertEqual(result.multiplier, 1.0)
        self.assertEqual(len(result.reasons), 0)

    def test_priority_vol_before_spread(self):
        """When both vol and spread trigger, vol wins (first check)."""
        shield = DangerZoneShield(vol_threshold=0.9, spread_threshold=30.0)
        result = shield.evaluate(
            "BTC",
            {"volatility_state": 0.95, "spread_bps": 50.0},
            0.5,
            0.25,
        )
        self.assertTrue(result.reasons[0].startswith("DANGER_ZONE:vol="))


class TestDangerZoneCascadeE2E(unittest.TestCase):
    """Verify DangerZone reasons propagate through ShieldCascade."""

    def test_cascade_propagates_dz_reason(self):
        """DZ veto in cascade → final multiplier=0.0, reason visible."""
        dz = DangerZoneShield(vol_threshold=0.9)
        cascade = ShieldCascade(shields=[dz])
        mult, reasons = cascade("BTC", {"volatility_state": 0.95}, 0.5, 0.25)
        self.assertEqual(mult, 0.0)
        self.assertTrue(any("DANGER_ZONE:vol" in r for r in reasons))

    def test_cascade_dz_pass_through(self):
        """DZ passes → cascade returns 1.0."""
        dz = DangerZoneShield(vol_threshold=0.99)
        cascade = ShieldCascade(shields=[dz])
        mult, reasons = cascade("BTC", {"volatility_state": 0.5}, 0.5, 0.25)
        self.assertEqual(mult, 1.0)

    def test_negative_motion_triggers(self):
        """Negative price_motion_norm also triggers (abs check)."""
        shield = DangerZoneShield(motion_threshold=3.0)
        result = shield.evaluate("BTC", {"price_motion_norm": -4.5}, 0.5, 0.25)
        self.assertEqual(result.multiplier, 0.0)
        self.assertIn("DANGER_ZONE:motion=", result.reasons[0])


if __name__ == "__main__":
    unittest.main()
