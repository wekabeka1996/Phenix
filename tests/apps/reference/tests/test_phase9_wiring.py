from __future__ import annotations

import decimal
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_loader import get_config
from apps.reference.domains.strategies.runtimes.aurora.handler import (
    AuroraHandler,
    ScoringResult,
)
from apps.reference.shared.decision_primitives.shields.memory_shield import (
    MemoryShield,
)


class TestPhase9Wiring(unittest.TestCase):
    def setUp(self):
        self.config = get_config()
        self.emit_fn = MagicMock()
        self.handler = AuroraHandler(
            config=self.config,
            emit_fn=self.emit_fn,
            wall_time_fn=lambda: 1700000000.0,
        )

    def test_emit_signal_quantization_wiring(self):
        """Verify BUG-5: Quantizer is wired and injects payload."""
        result = ScoringResult(
            score=0.8,
            regime="TREND_UP",
            side="BUY",
            thr_buy=0.5,
            thr_sell=-0.5,
            why_chain=["QuadraticScoring"],
            psi_vector={"trend": 0.8},
        )

        features = {
            "price": "50000.0",
            "volatility": {"atr_14": 100.0},
            "liquidity": {"kappa": 0.9},
        }

        with patch.object(self.handler, "_get_instrument_config") as mock_get_instr:
            instr_cfg = SimpleNamespace(
                leverage=SimpleNamespace(max_notional_value=decimal.Decimal("1000000")),
                volatility_entry_logic=SimpleNamespace(enabled=False),
            )
            mock_get_instr.return_value = instr_cfg

            self.handler._emit_signal(
                symbol="BTCUSDT",
                result=result,
                features=features,
                source_event={},
            )

        self.emit_fn.assert_called_once()
        args, _ = self.emit_fn.call_args
        event_name, payload = args

        self.assertEqual(event_name, "EVT:STRATEGY_SIGNAL_PRODUCED")
        self.assertIn("quantization", payload)

        q = payload["quantization"]
        qty = decimal.Decimal(q["qty"])
        self.assertGreaterEqual(qty, 0)
        self.assertTrue(q["qty"])

    def test_memory_shield_recording(self):
        """Verify BUG-2: MemoryShield.record_visit is called idempotently."""
        self.handler._memory_shield = MagicMock(spec=MemoryShield)

        result = ScoringResult(
            score=0.8,
            regime="TREND_UP",
            side="BUY",
            thr_buy=0.5,
            thr_sell=-0.5,
            why_chain=[],
            psi_vector={},
        )
        result.details = {"memory_state_hash": "hash_xyz_789"}

        features = {
            "price": "50000.0",
            "volatility": {"atr_14": 100.0},
        }

        with patch.object(self.handler, "_get_instrument_config") as mock_get_instr:
            mock_get_instr.return_value = SimpleNamespace(
                leverage=SimpleNamespace(max_notional_value=decimal.Decimal("1000000")),
                volatility_entry_logic=SimpleNamespace(enabled=False),
            )
            self.handler._emit_signal("BTCUSDT", result, features, {})

        self.handler._memory_shield.record_visit.assert_called_once()
        call_args = self.handler._memory_shield.record_visit.call_args
        self.assertEqual(call_args.kwargs["state_hash"], "hash_xyz_789")
        self.assertEqual(call_args.kwargs["bar_close_ts"], 1700000000)


if __name__ == "__main__":
    unittest.main()
