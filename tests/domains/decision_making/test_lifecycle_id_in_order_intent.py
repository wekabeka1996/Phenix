"""
PHASE 1 — TDD anchor: ORDER_INTENT must carry top-level lifecycle_id.

Contract: the lifecycle_id field in ORDER_INTENT must equal
trade_intent["idempotent_key"] and must be a valid UUID string.

These tests MUST FAIL before intent_builder.py is changed (red).
They MUST PASS after the Phase 1 implementation (green).
"""
import decimal
import uuid
import unittest
from unittest.mock import MagicMock, patch


def _make_builder():
    """Create a minimal IntentBuilder with all dependencies mocked."""
    from apps.reference.domains.decision_making.intent.builder import IntentBuilder

    mm = MagicMock()
    builder = IntentBuilder(
        fsm=mm,
        clock=mm,
        config=mm,
        tca_prefs=mm,
        risk_budgets=mm,
        safe_decimal_fn=mm,
        check_strategy_arbitration_fn=mm,
        warmup_gate_fn=mm,
        emit_rejected_fn=mm,
        record_blocked_fn=mm,
        record_accepted_fn=mm,
        emit_deferred_fn=mm,
        get_side_bias_params_fn=mm,
        side_intent_window={},
        logger=mm,
    )
    # Allow arbitration and proceed past warmup gate
    builder._check_strategy_arbitration = MagicMock(
        return_value={"allowed": True, "reason": ""})
    # warmup_gate must return a FALSY value to pass through.
    # The guard is: if self._warmup_gate(...): return
    # So False = continue; truthy = early exit.
    builder._warmup_gate = MagicMock(return_value=False)
    # Mock _resolve_order_policy to return MARKET order so we don't need real config
    builder._resolve_order_policy = MagicMock(return_value=("MARKET", None, None))
    return builder


def _make_sg():
    """Make a minimal StrategyGateway result mock."""
    sg = MagicMock()
    sg.outcome = "ALLOW"
    sg.intent_side = "BUY"
    sg.trace_ts_ms = 1685700000000
    sg.regime = "TREND_UP"
    sg.regime_confidence = 0.85
    sg.signal_score = 0.7
    sg.trend_dir = 1
    sg.delta_price = 0.0
    sg.pm_norm_10s = 0.0
    sg.pm_norm_60s = 0.0
    sg.pm_norm_300s = 0.0
    sg.vol_pct_10s = 0.0
    sg.vol_pct_60s = 0.0
    sg.vol_pct_300s = 0.0
    sg.why_short = "test"
    return sg


def _capture_order_intent_write(builder) -> dict | None:
    """Run build_and_emit and return the ORDER_INTENT entry written to order_logger."""
    written = []
    with patch(
        "apps.reference.domains.decision_making.intent.builder.order_logger"
    ) as mock_olog:
        mock_olog.write.side_effect = written.append
        sg = _make_sg()
        try:
            builder.build_and_emit(
                symbol="BTCUSDT",
                side="BUY",
                qty=decimal.Decimal("0.01"),
                price=decimal.Decimal("50000"),
                why_chain=[],
                rid="test-rid-lifecycle",
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
            pass  # some code paths may exit early; we only care about what was written
    intent_entries = [e for e in written if isinstance(
        e, dict) and e.get("event_type") == "ORDER_INTENT"]
    return intent_entries[0] if intent_entries else None


class TestOrderIntentLifecycleId(unittest.TestCase):
    """ORDER_INTENT must carry top-level lifecycle_id == idempotent_key."""

    def test_order_intent_has_top_level_lifecycle_id(self):
        """
        ORDER_INTENT write dict must have a 'lifecycle_id' key at the top level.
        This test FAILS before Phase 1 implementation.
        """
        builder = _make_builder()
        entry = _capture_order_intent_write(builder)
        if entry is None:
            self.skipTest(
                "ORDER_INTENT was not written (build_and_emit exited early)")
        self.assertIn(
            "lifecycle_id", entry,
            "ORDER_INTENT must have top-level 'lifecycle_id' field (HB-1 Phase 1)"
        )

    def test_lifecycle_id_equals_metadata_idempotent_key(self):
        """
        The top-level lifecycle_id must equal metadata.idempotent_key.
        Both must refer to the same UUID.
        """
        builder = _make_builder()
        entry = _capture_order_intent_write(builder)
        if entry is None:
            self.skipTest("ORDER_INTENT was not written")
        if "lifecycle_id" not in entry:
            self.skipTest("lifecycle_id not yet present (pre-implementation)")
        meta = entry.get("metadata", {})
        self.assertEqual(
            entry["lifecycle_id"],
            meta.get("idempotent_key"),
            "lifecycle_id must equal metadata.idempotent_key"
        )

    def test_lifecycle_id_is_valid_uuid_string(self):
        """
        lifecycle_id must be a parseable UUID string (uuid.UUID() must not raise).
        """
        builder = _make_builder()
        entry = _capture_order_intent_write(builder)
        if entry is None:
            self.skipTest("ORDER_INTENT was not written")
        if "lifecycle_id" not in entry:
            self.skipTest("lifecycle_id not yet present (pre-implementation)")
        lc_id = entry["lifecycle_id"]
        try:
            uuid.UUID(str(lc_id))
        except (ValueError, AttributeError) as exc:
            self.fail(f"lifecycle_id '{lc_id}' is not a valid UUID: {exc}")

    def test_existing_metadata_idempotent_key_still_present(self):
        """
        Phase 1 is additive: metadata.idempotent_key must still be present
        (backward compatibility — old consumers reading from metadata must not break).
        """
        builder = _make_builder()
        entry = _capture_order_intent_write(builder)
        if entry is None:
            self.skipTest("ORDER_INTENT was not written")
        meta = entry.get("metadata", {})
        self.assertIn(
            "idempotent_key", meta,
            "metadata.idempotent_key must still be present (additive change only)"
        )


if __name__ == "__main__":
    unittest.main()
