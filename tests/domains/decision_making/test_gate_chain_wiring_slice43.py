"""Integration tests for gate chain wiring — Slice 4.3.

Verifies that StrategyGateway.process_signal() uses the gate chain and
dispatches results correctly through _reject / _defer / _block.
"""
import decimal
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace

from apps.reference.domains.decision_making.strategy_gateway import StrategyGateway
from apps.reference.domains.decision_making.safety_gates import SafetyGateResult


def _make_dm(*, symbol="BTCUSDT", risk_score=0.3, risk_allowed=True,
             portfolio=None, features_ttl=60):
    """Build a mock DecisionMaking with sensible defaults."""
    dm = MagicMock()
    dm.logger = MagicMock()
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            risk_management=SimpleNamespace(
                trading_allowed_thresholds=SimpleNamespace(max_risk_score=0.8)),
            decision_making=SimpleNamespace(
                risk_skew=SimpleNamespace(
                    max_skew_sec=10,
                    max_defer_count=5,
                    defer_window_sec=60,
                    defer_cooldown_sec=2,
                    until_refresh_max_hold_sec=300,
                    until_refresh_retry_sec=5,
                )),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=30),
        ),
        strategies=SimpleNamespace(aurora=SimpleNamespace(
            decision=SimpleNamespace(
                retry_max_count=5, retry_backoff_factor=2.0),
            safety_gates=SimpleNamespace(system_stress_policy="off"),
        )),
        system=SimpleNamespace(market_data=None),
    )
    clock = MagicMock()
    clock.now_ms.return_value = 1_000_000
    dm._clock = clock

    dm.symbol_states = {symbol: {
        "risk": {
            "risk_parameters": {
                "risk_score": risk_score,
                "is_trading_allowed": risk_allowed,
            },
            "ts": 999_000,
        },
        "features": {"ts": 999_500, "features": {}},
    }}
    dm.latest_portfolio = portfolio or {"total_equity": 10000}
    dm.features_ttl_sec = features_ttl

    # Gate helper stubs
    dm._check_strategy_arbitration.return_value = {"allowed": True}
    dm._get_aurora_instrument_cfg.return_value = None
    dm._handle_flip_orchestration.return_value = None
    dm._qos_enabled_for_strategy.return_value = False
    dm._calculate_position_size.return_value = (
        decimal.Decimal("0.5"), "kelly:0.25", None, None)
    dm._precheck_exposure_cache.return_value = True
    dm._warmup_gate_before_trade_intent.return_value = False
    dm._degraded_context_gate_should_defer.return_value = False
    dm._per_symbol_regimes = {}
    dm._system_stress_states = {}

    return dm


def _make_event(*, symbol="BTCUSDT", side="BUY", strategy_id="aurora",
                ts_ms=999_000, entry_price="42000", **extra):
    pld = {
        "symbol": symbol,
        "side": side,
        "strategy_id": strategy_id,
        "ts_ms": ts_ms,
        "rid": "test-rid",
        "why_chain": [],
        "readiness": {"warmup_ok": True},
        "price_ctx": {"entry_price": entry_price},
        **extra,
    }
    return SimpleNamespace(pld=pld, name="EVT:STRATEGY_SIGNAL_PRODUCED")


class TestGateChainWiring:
    """Tests that process_signal() uses the gate chain correctly."""

    @patch("apps.reference.domains.decision_making.safety_gates.apply_safety_gates")
    def test_all_gates_pass_dispatches_to_propose(self, mock_asg):
        """When all gates pass, _propose_trade_intent is called."""
        mock_asg.return_value = SafetyGateResult(outcome="ALLOW")
        dm = _make_dm()
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._propose_trade_intent.assert_called_once()
        call_kw = dm._propose_trade_intent.call_args.kwargs
        assert call_kw["symbol"] == "BTCUSDT"
        assert call_kw["side"] == "BUY"
        assert call_kw["reduce_only"] is False

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_risk_gate_reject_calls_reject(self, mock_asg):
        """Risk score too high → _emit_trade_intent_rejected called."""
        dm = _make_dm(risk_score=0.95)
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._emit_trade_intent_rejected.assert_called_once()
        call_kw = dm._emit_trade_intent_rejected.call_args.kwargs
        assert call_kw["reason_code"] == "RISK_SCORE_TOO_HIGH"
        dm._propose_trade_intent.assert_not_called()
        # Safety gates should NOT have been called
        mock_asg.assert_not_called()

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_risk_gate_defer_calls_defer(self, mock_asg):
        """Missing risk data → defer emitted."""
        dm = _make_dm()
        dm.symbol_states["BTCUSDT"]["risk"] = None
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._emit_intent_deferred_v1.assert_called_once()
        call_kw = dm._emit_intent_deferred_v1.call_args.kwargs
        assert call_kw["reason"] == "NRR-DATA-NOT-READY"
        dm._propose_trade_intent.assert_not_called()
        mock_asg.assert_not_called()

    @patch("apps.reference.domains.decision_making.safety_gates.apply_safety_gates")
    def test_safety_gate_deny_handled_in_propose(self, mock_asg):
        """Safety gate DENY is now handled inside _propose_trade_intent (not chain)."""
        mock_asg.return_value = SafetyGateResult(
            outcome="DENY", deny_reason="NRR-029", why_short="flash_motion")
        dm = _make_dm()
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        # Safety gates run inside _propose_trade_intent, so it IS called
        dm._propose_trade_intent.assert_called_once()

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_warmup_block_calls_block(self, mock_asg):
        """Warmup not ready → _record_blocked_intent (BLOCK)."""
        dm = _make_dm()
        dm._warmup_gate_before_trade_intent.return_value = True
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._record_blocked_intent.assert_called()
        dm._propose_trade_intent.assert_not_called()
        mock_asg.assert_not_called()

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_accumulated_data_flows_to_dispatch(self, mock_asg):
        """After chain passes, accumulated qty/price used in _propose_trade_intent."""
        mock_asg.return_value = SafetyGateResult(outcome="ALLOW")
        dm = _make_dm()
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event(entry_price="50000"))

        call_kw = dm._propose_trade_intent.call_args.kwargs
        assert call_kw["qty"] == decimal.Decimal("0.5")
        assert call_kw["price"] == decimal.Decimal("50000")

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_qos_enabled_flag_carried_forward(self, mock_asg):
        """QoS enabled flag from accumulated controls post-emission state update."""
        mock_asg.return_value = SafetyGateResult(outcome="ALLOW")
        dm = _make_dm()
        dm._qos_enabled_for_strategy.return_value = True
        dm._qos_allow.return_value = (True, None)
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._propose_trade_intent.assert_called_once()
        dm._update_qos_state.assert_called_once()

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_arbitration_rejects_in_chain(self, mock_asg):
        """Arbitration blocked → reject via chain."""
        dm = _make_dm()
        dm._check_strategy_arbitration.return_value = {
            "allowed": False, "reason": "cooldown"}
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._emit_trade_intent_rejected.assert_called_once()
        call_kw = dm._emit_trade_intent_rejected.call_args.kwargs
        assert call_kw["reason_code"] == "ARBITRATION_BLOCKED"
        mock_asg.assert_not_called()

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_exposure_reject_before_safety(self, mock_asg):
        """Exposure precheck fail → reject before safety gates run."""
        dm = _make_dm()
        dm._precheck_exposure_cache.return_value = False
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._emit_trade_intent_rejected.assert_called_once()
        call_kw = dm._emit_trade_intent_rejected.call_args.kwargs
        assert call_kw["reason_code"] == "EXPOSURE_PRECHECK_FAILED"
        mock_asg.assert_not_called()

    @patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
    def test_md_amr_reduce_path_bypasses_chain(self, mock_asg):
        """md_amr FULL_CLOSE goes through reduce path, not the gate chain."""
        dm = _make_dm()
        dm._emit_reduce_only_close.return_value = True
        gw = StrategyGateway(dm)
        evt = _make_event(
            strategy_id="md_amr",
            intent_kind="FULL_CLOSE",
            trace={
                "dir_score": "0.8", "thr_buy": "0.5", "thr_sell": "0.5",
                "w_raw": {"d1": "0.3", "h1": "0.25", "m30": "0.25", "m15": "0.2"},
                "w_norm": {"d1": "0.3", "h1": "0.25", "m30": "0.25", "m15": "0.2"},
                "qty_base": "100", "qty_new": "100", "conf_ratio": "0.9",
                "strategy_params": {}, "ts_ms": 999000,
            },
        )
        gw.process_signal(evt)

        # Reduce path calls _emit_reduce_only_close, not _propose_trade_intent via chain
        dm._emit_reduce_only_close.assert_called_once()
        # Safety gates not called at gateway level (reduce path uses DM facade)
        mock_asg.assert_not_called()

    @patch("apps.reference.domains.decision_making.gates.risk_gate.check")
    def test_gate_chain_exception_fails_closed(self, mock_check):
        """If a gate raises an exception, the chain fails closed with REJECT."""
        mock_check.side_effect = ValueError("Unexpected boom")
        dm = _make_dm()
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        dm._emit_trade_intent_rejected.assert_called_once()
        call_kw = dm._emit_trade_intent_rejected.call_args.kwargs
        assert call_kw["reason_code"] == "GATE_CHAIN_EXCEPTION"
        assert "exception:ValueError" in call_kw["context"]
        dm._propose_trade_intent.assert_not_called()

    @patch("apps.reference.domains.decision_making.safety_gates.apply_safety_gates")
    def test_gate_chain_trace_emitted_on_pass(self, mock_asg):
        """Gate chain trace is emitted on pass."""
        mock_asg.return_value = SafetyGateResult(outcome="ALLOW")
        dm = _make_dm()
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        emit_calls = [call for call in dm.fsm.emit.call_args_list if call[0][0] == "EVT:GATE_CHAIN_TRACE"]
        assert len(emit_calls) == 1
        payload = emit_calls[0][0][1]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["final_outcome"] == "PASS"
        assert "gates" in payload
        assert len(payload["gates"]) > 0

    @patch("apps.reference.domains.decision_making.gates.risk_gate.check")
    def test_gate_chain_trace_emitted_on_exception(self, mock_check):
        """Gate chain trace is emitted even on fail-closed exception."""
        mock_check.side_effect = ValueError("Unexpected boom")
        dm = _make_dm()
        gw = StrategyGateway(dm)
        gw.process_signal(_make_event())

        emit_calls = [call for call in dm.fsm.emit.call_args_list if call[0][0] == "EVT:GATE_CHAIN_TRACE"]
        assert len(emit_calls) == 1
        payload = emit_calls[0][0][1]
        assert payload["final_outcome"] == "REJECT"
        assert any(g["reason_code"] == "exception:ValueError" for g in payload["gates"] if "reason_code" in g)

