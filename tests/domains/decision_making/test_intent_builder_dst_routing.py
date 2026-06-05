"""
Regression tests: IntentBuilder WAL message must target ``execution_position``
not the decommissioned ``bridge`` domain (BRIDGE-SUNSET-01).

Covers:
1. WAL payload carries ``dst = "execution_position"``
2. FSM emit still fires after successful WAL write
3. No "bridge" token anywhere in the WAL-persisted dict
"""

import decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.decision_making.intent.builder import IntentBuilder


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
    trend_run_length = None
    delta_price = 0
    pm_norm_10s = pm_norm_60s = pm_norm_300s = 0
    vol_pct_10s = vol_pct_60s = vol_pct_300s = 0


def _make_config():
    kelly_cfg = SimpleNamespace(
        base_probability="0.5",
        kelly_cap="0.25",
        kelly_alpha="0.8",
        payoff_ratio_r="1.5",
        p_min="0.45",
        p_max="0.65",
        uplift_factor="0.2",
    )
    strategy_cfg = SimpleNamespace(
        execution=SimpleNamespace(entry_order_type="LIMIT", entry_tif="GTC"),
        decision=SimpleNamespace(kelly=kelly_cfg),
    )
    return SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=strategy_cfg,
            strat_A=strategy_cfg,
        )
    )


def _make_builder(*, arb_fn=None) -> IntentBuilder:
    clock = MagicMock()
    clock.now_ms.return_value = 1700000000000
    clock.now_sec.return_value = 1700000000
    return IntentBuilder(
        logger=MagicMock(),
        fsm=MagicMock(),
        clock=clock,
        config=_make_config(),
        tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100,
                   "maker_preference": False},
        risk_budgets={"trade_cvar95_max_bps": 50,
                      "session_cvar95_max_bps": 100},
        safe_decimal_fn=lambda x, default: decimal.Decimal(
            x) if x else default,
        check_strategy_arbitration_fn=arb_fn or MagicMock(
            return_value={"allowed": True}),
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


@pytest.fixture(autouse=True)
def _side_effect_sinks():
    with patch("apps.reference.domains.decision_making.intent.builder.order_logger.write") as mock_order_write, \
            patch("apps.reference.domains.decision_making.intent.builder.print"):
        yield mock_order_write


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIntentBuilderDstRouting:
    """BRIDGE-SUNSET-01: WAL messages must not reference decommissioned bridge."""

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
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

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
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

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
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

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
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

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
    def test_emit_failure_keeps_pre_emit_artifacts_and_stops_post_emit_work(
        self,
        mock_policy,
        mock_wal,
        _side_effect_sinks,
    ):
        """Emit failure must occur after accepted metrics/WAL and before post-emit bookkeeping."""
        mock_policy.return_value = ("LIMIT", "GTC", 10000)

        call_order: list[str] = []
        arb_fn = MagicMock(
            side_effect=lambda *_, commit=False, **__: (
                call_order.append(f"arb_commit_{commit}"),
                {"allowed": True},
            )[1]
        )
        builder = _make_builder(arb_fn=arb_fn)
        builder._record_accepted.side_effect = lambda symbol: call_order.append(
            f"accepted:{symbol}"
        )
        mock_wal.side_effect = lambda _payload: (
            call_order.append("wal_append"),
            "wal-ok",
        )[1]

        def _emit_side_effect(event_name, *args, **kwargs):
            if event_name == "EVT:DECISION_TRACE_EMITTED":
                call_order.append("decision_trace_emit")
                return None
            if event_name == "EVT:TRADE_INTENT_PROPOSED":
                call_order.append("intent_emit")
                raise RuntimeError(
                    "Payload validation failed for EVT:TRADE_INTENT_PROPOSED: "
                    "Additional properties are not allowed ('trace' was unexpected)"
                )
            raise AssertionError(f"Unexpected emit call: {event_name}")

        builder._fsm.emit.side_effect = _emit_side_effect

        builder.build_and_emit(
            **{
                **_COMMON_KWARGS,
                "strategy_trace": {"objective": {"score": 0.9}, "model": "aurora"},
            }
        )

        assert call_order == [
            "arb_commit_False",
            "decision_trace_emit",
            "accepted:BTCUSDT",
            "wal_append",
            "intent_emit",
        ]
        assert arb_fn.call_count == 1
        _side_effect_sinks.assert_not_called()

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
    def test_emit_failure_log_includes_event_rid_and_validation_reason(
        self,
        mock_policy,
        mock_wal,
    ):
        """Emit-failure log must be self-diagnosing for the execution-critical boundary."""
        mock_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "wal-ok"

        builder = _make_builder()

        def _emit_side_effect(event_name, *args, **kwargs):
            if event_name == "EVT:DECISION_TRACE_EMITTED":
                return None
            if event_name == "EVT:TRADE_INTENT_PROPOSED":
                raise RuntimeError(
                    "Payload validation failed for EVT:TRADE_INTENT_PROPOSED: "
                    "Additional properties are not allowed ('trace' was unexpected)"
                )
            raise AssertionError(f"Unexpected emit call: {event_name}")

        builder._fsm.emit.side_effect = _emit_side_effect

        builder.build_and_emit(
            **{
                **_COMMON_KWARGS,
                "strategy_trace": {"objective": {"score": 0.5}},
            }
        )

        assert builder.logger.error.call_count == 1
        log_line = builder.logger.error.call_args[0][0]
        assert "EVT:TRADE_INTENT_PROPOSED" in log_line
        assert "RID=rid-dst-001" in log_line
        assert "Additional properties are not allowed" in log_line

    @patch("apps.reference.domains.decision_making.intent.builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
    def test_builder_propagates_tpsl_owner_context_to_trace_and_intent(
        self,
        mock_policy,
        mock_wal,
    ):
        mock_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "wal-ok"

        builder = _make_builder()
        owner_ctx = {
            "intended_owner": "regime_tpsl",
            "final_owner": "entry_plan",
            "owner_loss_reason": "TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
        }

        builder.build_and_emit(
            **{
                **_COMMON_KWARGS,
                "tpsl_owner_ctx": owner_ctx,
            }
        )

        wal_dict = mock_wal.call_args[0][0]
        assert wal_dict["pld"]["tpsl_owner_ctx"] == owner_ctx

        decision_trace_payload = None
        trade_intent_payload = None
        for call in builder._fsm.emit.call_args_list:
            if call.args[0] == "EVT:DECISION_TRACE_EMITTED":
                decision_trace_payload = call.kwargs["payload"]
            if call.args[0] == "EVT:TRADE_INTENT_PROPOSED":
                trade_intent_payload = call.kwargs["payload"]

        assert decision_trace_payload is not None
        assert trade_intent_payload is not None
        assert decision_trace_payload["tpsl_owner_ctx"] == owner_ctx
        assert trade_intent_payload["tpsl_owner_ctx"] == owner_ctx
        assert any(
            call.args == (
                "[%s] TPSL_OWNER_INTENT intended=%s final=%s reason=%s",
                "BTCUSDT",
                "regime_tpsl",
                "entry_plan",
                "TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
            )
            for call in builder.logger.info.call_args_list
        )
