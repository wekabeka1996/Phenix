import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from vfoundation.core.protocol import Message


class TestStrategyGatewayTimeContract:
    """TDD regression testing for DM-TTL-NORMALIZATION-PACK-R1.
    Ensure canonical single-point normalization of ts_ms and downstream correctness.
    """

    @pytest.fixture
    def gateway(self):
        dm_mock = MagicMock()
        # Mock Clock setup so TTL doesn't trip on exactly perfectly normalized time
        dm_mock._clock.now_ms.return_value = 1700000000000

        # Mock state for gates to allow signal to pass entirely to proposal
        dm_mock.symbol_states = {"BTCUSDT": {
            "risk": {"risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}}}}
        dm_mock.config.domains.risk_management.trading_allowed_thresholds.max_risk_score = 100
        dm_mock.latest_portfolio = {"equity": 1000}
        # Configure safety_gates for test_strat to avoid DENY from MagicMock auto-attrs
        from types import SimpleNamespace
        dm_mock.config.strategies = SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0),
                safety_gates=SimpleNamespace(system_stress_policy="off"),
            ),
            test_strat=SimpleNamespace(
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0),
                safety_gates=SimpleNamespace(system_stress_policy="off"),
            ),
        )
        dm_mock._per_symbol_regimes = {}
        dm_mock._system_stress_states = {}

        # Mock Gate responses
        dm_mock._check_strategy_arbitration.return_value = {"allowed": True}
        dm_mock._handle_flip_orchestration.return_value = None
        dm_mock._qos_enabled_for_strategy.return_value = False
        dm_mock._calculate_position_size.return_value = (
            Decimal("1.0"), "ok", None, None)
        dm_mock._precheck_exposure_cache.return_value = True
        dm_mock._warmup_gate_before_trade_intent.return_value = False
        dm_mock._get_aurora_instrument_cfg.return_value = None
        dm_mock._degraded_context_gate_should_defer.return_value = False

        gw = StrategyGateway(dm_mock)
        gw._reject = MagicMock()
        gw._defer = MagicMock()
        return gw, dm_mock

    def _make_msg(self, ts_ms, intent_kind="ENTRY", strategy_id="test_strat"):
        return Message(
            op="EVT",
            verb="produced",
            src="feature_engineering",
            dst="decision_making",
            name="EVT:STRATEGY_SIGNAL_PRODUCED",
            pld={
                "strategy_id": strategy_id,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "rid": "test-123",
                "ts_ms": ts_ms,
                "tf_sec": 300,
                "intent_kind": intent_kind,
                "readiness": {"warmup_ok": True},
                "price_ctx": {"entry_price": 50000},
                "trace": {
                    "dir_score": 1, "thr_buy": 0.5, "thr_sell": 0.5,
                    "w_raw": {"d1": 1, "h1": 1, "m30": 1, "m15": 1},
                    "w_norm": {"d1": 1, "h1": 1, "m30": 1, "m15": 1},
                    "qty_base": 1, "qty_new": 1, "conf_ratio": 1
                }
            }
        )

    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.resolve_strategy_entry_prices")
    def test_canonical_time_normalization_ms_downstream_success(self, mock_resolve, gateway):
        """Test ms timestamp goes through entry flow, hits NO stale reject, and proposes correctly."""
        gw, dm = gateway
        mock_resolve.return_value = (None, None, None)

        # Exactly matching the mock clock so TTL is 0
        valid_ms_ts = 1700000000000
        msg = self._make_msg(valid_ms_ts)

        gw.process_signal(msg)

        gw._defer.assert_not_called()
        gw._reject.assert_not_called()
        dm._propose_trade_intent.assert_called_once()
        kwargs = dm._propose_trade_intent.call_args.kwargs
        assert kwargs["decision_ts_ms"] == valid_ms_ts

    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.resolve_strategy_entry_prices")
    def test_canonical_time_normalization_sec_downstream_success(self, mock_resolve, gateway):
        """Test sec timestamp is scaled to ms, avoids SIGNAL_STALE, and reaches downstream."""
        gw, dm = gateway
        mock_resolve.return_value = (None, None, None)

        valid_sec_ts = 1700000000
        msg = self._make_msg(valid_sec_ts)

        gw.process_signal(msg)

        gw._defer.assert_not_called()
        gw._reject.assert_not_called()
        dm._propose_trade_intent.assert_called_once()
        kwargs = dm._propose_trade_intent.call_args.kwargs
        assert kwargs["decision_ts_ms"] == valid_sec_ts * 1000

    def test_invalid_ts_ms_missing(self, gateway):
        """Test missing ts_ms properly fail-closes before any downstream calls."""
        gw, dm = gateway

        for bad_ts in [None, 0, "0", ""]:
            gw._reject.reset_mock()
            dm._propose_trade_intent.reset_mock()

            msg = self._make_msg(bad_ts)
            gw.process_signal(msg)

            gw._reject.assert_called_once()
            assert gw._reject.call_args.kwargs["reason_code"] == "MISSING_TS_MS"
            dm._propose_trade_intent.assert_not_called()

    def test_invalid_ts_ms_malformed(self, gateway):
        """Test malformed ts_ms properly fail-closes before downstream."""
        gw, dm = gateway

        for bad_ts in ["abc", -100, [], {}]:
            gw._reject.reset_mock()
            dm._propose_trade_intent.reset_mock()

            msg = self._make_msg(bad_ts)
            gw.process_signal(msg)

            gw._reject.assert_called_once()
            assert gw._reject.call_args.kwargs["reason_code"] == "INVALID_TS_MS"
            dm._propose_trade_intent.assert_not_called()

    def test_reduce_only_exits_exempt_from_ts_ms_missing(self, gateway):
        """Test md_amr FULL_CLOSE / PARTIAL_CLOSE are exempt from strict MISSING_TS_MS rejection."""
        gw, dm = gateway
        dm._get_portfolio_position_qty_signed.return_value = (
            Decimal("1.0"), "BTCUSDT")

        # Test FULL_CLOSE
        msg_full = self._make_msg(
            None, intent_kind="FULL_CLOSE", strategy_id="md_amr")
        gw.process_signal(msg_full)

        # FULL_CLOSE emits reduce_only_close directly
        gw._reject.assert_not_called()
        dm._emit_reduce_only_close.assert_called_once()

        # Test PARTIAL_CLOSE
        gw._reject.reset_mock()
        dm._propose_trade_intent.reset_mock()

        msg_partial = self._make_msg(
            "", intent_kind="PARTIAL_CLOSE", strategy_id="md_amr")
        msg_partial.pld["scaleout_fraction"] = 0.5
        gw.process_signal(msg_partial)

        gw._reject.assert_not_called()
        dm._propose_trade_intent.assert_called_once()
        kwargs = dm._propose_trade_intent.call_args.kwargs
        assert kwargs["decision_ts_ms"] == 1700000000000

    def test_reduce_only_with_invalid_ts_ms_fails_closed(self, gateway):
        """Even exempt reduce-only paths fail closed if provided a maliciously malformed timestamp."""
        gw, dm = gateway

        msg = self._make_msg(
            "abc", intent_kind="FULL_CLOSE", strategy_id="md_amr")
        gw.process_signal(msg)

        gw._reject.assert_called_once()
        assert gw._reject.call_args.kwargs["reason_code"] == "INVALID_TS_MS"
