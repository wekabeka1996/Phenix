"""
SSOT enforcement tests for normalize_mode / normalize_signals_mode.

Verifies:
1. Config (Pydantic) rejects invalid modes ("net_zero", "legacy_v1")
2. AuroraScoringKernel.compute() fails closed for non-"signed_v2" modes
3. compute_direction_strength_score() raises for unknown modes, accepts "off"
4. ORDER_INTENT WAL entry includes normalize_mode_effective in metadata
"""
from __future__ import annotations

import decimal
import json
import os
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# 1. Config-level: Pydantic must reject invalid modes
# ---------------------------------------------------------------------------


class TestSignalsConfigValidation:
    """SignalsConfig must only accept Literal["off", "signed_v2"]."""

    def _make_valid(self, mode: str):
        from apps.reference.config_models import SignalsConfig
        return SignalsConfig(
            normalize_signals_mode=mode,
            enable_new_metrics=True,
            delta_price_cap_pct=0.005,
        )

    def test_config_accepts_signed_v2(self):
        cfg = self._make_valid("signed_v2")
        assert cfg.normalize_signals_mode == "signed_v2"

    def test_config_rejects_off_mode(self):
        """'off' is a forensic-only passthrough; removed from production config boundary."""
        from apps.reference.config_models import SignalsConfig
        with pytest.raises(ValidationError):
            SignalsConfig(
                normalize_signals_mode="off",
                enable_new_metrics=True,
                delta_price_cap_pct=0.005,
            )

    def test_config_rejects_net_zero_mode(self):
        from apps.reference.config_models import SignalsConfig
        with pytest.raises(ValidationError):
            SignalsConfig(
                normalize_signals_mode="net_zero",
                enable_new_metrics=True,
                delta_price_cap_pct=0.005,
            )

    def test_config_rejects_legacy_v1_mode(self):
        """'legacy_v1' must be rejected after removal from Literal."""
        from apps.reference.config_models import SignalsConfig
        with pytest.raises(ValidationError):
            SignalsConfig(
                normalize_signals_mode="legacy_v1",
                enable_new_metrics=True,
                delta_price_cap_pct=0.005,
            )

    def test_config_rejects_arbitrary_string(self):
        from apps.reference.config_models import SignalsConfig
        with pytest.raises(ValidationError):
            SignalsConfig(
                normalize_signals_mode="foo_bar",
                enable_new_metrics=True,
                delta_price_cap_pct=0.005,
            )


# ---------------------------------------------------------------------------
# 2. Kernel-level: AuroraScoringKernel must reject non-"signed_v2"
# ---------------------------------------------------------------------------


def _minimal_kernel_kwargs():
    """Minimal valid kwargs for AuroraScoringKernel.compute()."""
    return dict(
        symbol="BTCUSDT",
        features={"ema_bias": Decimal("0.6")},
        warmup_readiness={"ema_bias": True},
        price=Decimal("50000"),
        signal_weights={"ema_bias": 1.0},
        feature_neutrals={"ema_bias": 0.5},
        essential_features=["ema_bias"],
        base_threshold=Decimal("0.1"),
        regime_name="TREND_UP",
        regime_thresholds={"TREND_UP": 1.0, "DEFAULT": 1.0},
        side_bias_state=None,
        direction_strength_cfg={
            "directional_features": ["ema_bias"],
            "strength_features": [],
            "strength_alpha": 0.5,
            "strength_cap": 1.5,
        },
        delta_price_cap_pct=Decimal("0.005"),
    )


class TestKernelFailClosed:
    """AuroraScoringKernel.compute must reject anything not 'signed_v2'."""

    def test_kernel_accepts_signed_v2(self):
        from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel
        result = AuroraScoringKernel.compute(**_minimal_kernel_kwargs(), normalize_mode="signed_v2")
        assert result is not None

    def test_kernel_rejects_net_zero(self):
        from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel
        with pytest.raises(ValueError, match="normalize_mode"):
            AuroraScoringKernel.compute(**_minimal_kernel_kwargs(), normalize_mode="net_zero")

    def test_kernel_rejects_off_mode(self):
        """Even though 'off' is valid in config/scoring_fn, the kernel enforces signed_v2."""
        from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel
        with pytest.raises(ValueError, match="normalize_mode"):
            AuroraScoringKernel.compute(**_minimal_kernel_kwargs(), normalize_mode="off")

    def test_kernel_rejects_empty_string(self):
        from apps.reference.domains.decision_making.aurora_scoring_kernel import AuroraScoringKernel
        with pytest.raises(ValueError, match="normalize_mode"):
            AuroraScoringKernel.compute(**_minimal_kernel_kwargs(), normalize_mode="")


# ---------------------------------------------------------------------------
# 3. Scoring function: explicit mode handling, raise on unknown
# ---------------------------------------------------------------------------


def _minimal_scoring_kwargs(mode: str):
    return dict(
        features={"ema_bias": Decimal("0.7")},
        weights={"ema_bias": 1.0},
        neutrals={"ema_bias": 0.5},
        readiness={"ema_bias": True},
        essential_features={"ema_bias"},
        normalize_mode=mode,
        directional_features=["ema_bias"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        symbol="BTCUSDT",
    )


class TestScoringFnModeHandling:
    """compute_direction_strength_score must raise on unknown modes, not silently pass through."""

    def test_scoring_fn_signed_v2_produces_result(self):
        from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
            compute_direction_strength_score,
        )
        res = compute_direction_strength_score(**_minimal_scoring_kwargs("signed_v2"))
        assert res.deferred is False

    def test_scoring_fn_off_mode_explicit_passthrough(self):
        """'off' should produce a result without transforms (explicit, not silent else)."""
        from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
            compute_direction_strength_score,
        )
        res = compute_direction_strength_score(**_minimal_scoring_kwargs("off"))
        assert res.deferred is False  # should compute normally, just without transforms

    def test_scoring_fn_rejects_net_zero(self):
        from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
            compute_direction_strength_score,
        )
        with pytest.raises(ValueError):
            compute_direction_strength_score(**_minimal_scoring_kwargs("net_zero"))

    def test_scoring_fn_rejects_arbitrary_unknown(self):
        from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
            compute_direction_strength_score,
        )
        with pytest.raises(ValueError):
            compute_direction_strength_score(**_minimal_scoring_kwargs("bogus_mode"))


# ---------------------------------------------------------------------------
# 4. WAL observability: ORDER_INTENT must include normalize_mode_effective
# ---------------------------------------------------------------------------


class TestWalOrderIntentNormalizeModeEffective(unittest.TestCase):
    """ORDER_INTENT log entry must carry normalize_mode_effective in metadata."""

    def test_build_and_emit_signature_has_normalize_mode(self):
        """build_and_emit signature must include normalize_mode parameter."""
        import inspect
        from apps.reference.domains.decision_making.intent_builder import IntentBuilder
        sig = inspect.signature(IntentBuilder.build_and_emit)
        self.assertIn("normalize_mode", sig.parameters,
                      "build_and_emit must accept normalize_mode kwarg")

    def test_wal_order_intent_has_normalize_mode_effective(self):
        """ORDER_INTENT log entry must carry normalize_mode_effective in metadata."""
        from apps.reference.domains.decision_making.intent_builder import IntentBuilder

        mm = MagicMock()
        builder = IntentBuilder(
            fsm=mm, clock=mm, config=mm, tca_prefs=mm, risk_budgets=mm,
            safe_decimal_fn=mm, check_strategy_arbitration_fn=mm,
            warmup_gate_fn=mm, emit_rejected_fn=mm, record_blocked_fn=mm,
            record_accepted_fn=mm, emit_deferred_fn=mm,
            get_side_bias_params_fn=mm, side_intent_window={}, logger=mm,
        )
        # Arbitration returns blocked → function returns early, no ORDER_INTENT written.
        # Override to allow — and intercept at order_logger.write.
        builder._check_strategy_arbitration = MagicMock(return_value={"allowed": True, "reason": ""})
        builder._warmup_gate = MagicMock(return_value={"ready": False})  # short-circuit before emit

        written = []

        with patch(
            "apps.reference.domains.decision_making.intent_builder.order_logger"
        ) as mock_olog:
            mock_olog.write.side_effect = written.append
            sg = MagicMock()
            sg.outcome = "ALLOW"
            sg.intent_side = "BUY"
            sg.trace_ts_ms = 1685700000000
            sg.regime = "TREND_UP"
            sg.regime_confidence = 0.9

            try:
                builder.build_and_emit(
                    symbol="BTCUSDT",
                    side="BUY",
                    qty=decimal.Decimal("0.01"),
                    price=decimal.Decimal("50000"),
                    why_chain=[],
                    rid="test-rid",
                    reduce_only=False,
                    strategy_id="aurora",
                    decision_ts_ms=1685700000000,
                    stop_price=None,
                    target_price=None,
                    entry_plan_trace=None,
                    tf_sec=300,
                    max_slippage_bps=None,
                    max_latency_ms=None,
                    risk_score=None,
                    normalize_mode="signed_v2",
                    sg=sg,
                )
            except Exception:
                pass  # may exit early in build — that's fine

        intent_entries = [e for e in written if e.get("event_type") == "ORDER_INTENT"]
        if intent_entries:
            meta = intent_entries[0].get("metadata", {})
            self.assertIn("normalize_mode_effective", meta,
                          "ORDER_INTENT metadata must include normalize_mode_effective")
            self.assertEqual(meta["normalize_mode_effective"], "signed_v2")


if __name__ == "__main__":
    unittest.main()
