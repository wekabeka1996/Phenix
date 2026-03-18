"""
Regression tests: IntentBuilder WAL message must target ``execution_position``
not the decommissioned ``bridge`` domain (BRIDGE-SUNSET-01).

Covers:
1. WAL payload carries ``dst = "execution_position"``
2. FSM emit still fires after successful WAL write
3. No "bridge" token anywhere in the WAL-persisted dict
"""

import decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.decision_making.intent_builder import IntentBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeSG:
    """Minimal SafetyGateResult stub."""
    intent_side = "LONG"
    trace_ts_ms = 1700000000000
    why_short = ""
    signal_score = 0.5
    regime = "TREND_UP"
    regime_confidence = 0.9
    trend_dir = 1
    delta_price = 0
    pm_norm_10s = pm_norm_60s = pm_norm_300s = 0
    vol_pct_10s = vol_pct_60s = vol_pct_300s = 0


def _make_builder(*, arb_fn=None) -> IntentBuilder:
    return IntentBuilder(
        logger=MagicMock(),
        fsm=MagicMock(),
        clock=MagicMock(),
        config=MagicMock(),
        tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100,
                   "maker_preference": False},
        risk_budgets={"trade_cvar95_max_bps": 50,
                      "session_cvar95_max_bps": 100},
        safe_decimal_fn=lambda x, default: decimal.Decimal(
            x) if x else default,
        check_strategy_arbitration_fn=arb_fn or (
            lambda *a, **kw: {"allowed": True}),
        warmup_gate_fn=lambda **kw: False,
        emit_rejected_fn=MagicMock(),
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0, 600, 0.6, 0.9)),
        side_intent_window={},
    )


_COMMON_KWARGS = dict(
    symbol="BTCUSDT", side="BUY",
    qty=decimal.Decimal("1.0"), price=decimal.Decimal("50000"),
    why_chain=["unit_test"], rid="rid-dst-001",
    reduce_only=False, strategy_id="strat_A",
    decision_ts_ms=1700000000000,
    stop_price=None, target_price=None,
    entry_plan_trace=None, tf_sec=300,
    max_slippage_bps=None, max_latency_ms=None,
    risk_score=None, strategy_trace=None,
    sg=_FakeSG(),
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIntentBuilderDstRouting:
    """BRIDGE-SUNSET-01: WAL messages must not reference decommissioned bridge."""

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_wal_message_dst_is_execution_position(self, mock_policy, mock_wal):
        """WAL-persisted Message must have dst='execution_position'."""
        mock_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "wal-ok"

        builder = _make_builder()
        builder.build_and_emit(**_COMMON_KWARGS)

        mock_wal.assert_called_once()
        wal_dict = mock_wal.call_args[0][0]
        assert wal_dict["dst"] == "execution_position", (
            f"WAL message must target execution_position, got {wal_dict['dst']!r}"
        )

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_wal_message_has_no_bridge_reference(self, mock_policy, mock_wal):
        """No field in the WAL dict should contain 'bridge'."""
        mock_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "wal-ok"

        builder = _make_builder()
        builder.build_and_emit(**_COMMON_KWARGS)

        wal_dict = mock_wal.call_args[0][0]
        for key, val in wal_dict.items():
            if isinstance(val, str):
                assert "bridge" not in val.lower(), (
                    f"WAL field {key!r}={val!r} contains stale 'bridge' token"
                )

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_fsm_emit_fires_after_wal_write(self, mock_policy, mock_wal):
        """FSM emit must fire after successful WAL write."""
        mock_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "wal-ok"

        builder = _make_builder()
        builder.build_and_emit(**_COMMON_KWARGS)

        emit_calls = [
            c for c in builder._fsm.emit.call_args_list
            if c[0][0] == "EVT:TRADE_INTENT_PROPOSED"
        ]
        assert len(
            emit_calls) == 1, "FSM must emit exactly one TRADE_INTENT_PROPOSED"

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_wal_src_is_decision_making(self, mock_policy, mock_wal):
        """WAL message src must be 'decision_making'."""
        mock_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "wal-ok"

        builder = _make_builder()
        builder.build_and_emit(**_COMMON_KWARGS)

        wal_dict = mock_wal.call_args[0][0]
        assert wal_dict["src"] == "decision_making"
        assert wal_dict["op"] == "EVT"
        assert wal_dict["verb"] == "TRADE_INTENT_PROPOSED"
