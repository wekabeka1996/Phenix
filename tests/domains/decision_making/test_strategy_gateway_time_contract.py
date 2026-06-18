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
                mode="runtime",
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0),
                safety_gates=SimpleNamespace(system_stress_policy="off"),
            ),
            test_strat=SimpleNamespace(
                mode="runtime",
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

    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.write_strategy_decision_blocked")
    def test_shadow_strategy_is_terminally_blocked_before_intent_builder(self, write_blocked, gateway):
        gw, dm = gateway
        dm.config.strategies.test_strat.mode = "shadow"
        write_blocked.return_value = {
            "strategy_id": "test_strat",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "stage": "STRATEGY",
            "reason_code": "AUTHORITY_MODE_SHADOW",
        }

        gw.process_signal(self._make_msg(1700000000000))

        write_blocked.assert_called_once()
        dm.fsm.emit.assert_called_once()
        assert dm.fsm.emit.call_args.args[0] == "EVT:STRATEGY_DECISION_BLOCKED"
        dm._propose_trade_intent.assert_not_called()

    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.write_strategy_decision_blocked")
    def test_entry_quarantine_blocks_xrp_sell_but_not_position_management(self, write_blocked, gateway):
        from types import SimpleNamespace

        gw, dm = gateway
        dm.config.strategies_registry = SimpleNamespace(
            entry_quarantine={"XRPUSDT": ["SELL"]})
        write_blocked.return_value = {
            "strategy_id": "test_strat",
            "symbol": "XRPUSDT",
            "side": "SELL",
            "stage": "STRATEGY",
            "reason_code": "ENTRY_SIDE_QUARANTINED",
        }
        msg = self._make_msg(1700000000000)
        msg.pld["symbol"] = "XRPUSDT"
        msg.pld["side"] = "SELL"

        gw.process_signal(msg)

        assert write_blocked.call_args.kwargs["reason_code"] == "ENTRY_SIDE_QUARANTINED"
        dm._propose_trade_intent.assert_not_called()

        write_blocked.reset_mock()
        dm._emit_reduce_only_close.return_value = True
        close_msg = self._make_msg(
            1700000000000, intent_kind="FULL_CLOSE", strategy_id="md_amr")
        close_msg.pld["symbol"] = "XRPUSDT"
        close_msg.pld["side"] = "SELL"
        gw.process_signal(close_msg)

        write_blocked.assert_not_called()
        dm._emit_reduce_only_close.assert_called_once()

    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.write_strategy_decision_blocked")
    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.resolve_strategy_entry_prices")
    def test_turnover_budget_blocks_repeated_entry_intent_attempt(
        self, mock_resolve, write_blocked, gateway
    ):
        from types import SimpleNamespace

        gw, dm = gateway
        mock_resolve.return_value = (None, None, None)
        dm.config.strategies_registry = SimpleNamespace(
            entry_quarantine={},
            turnover_budgets={
                "test_strat": {
                    "BTCUSDT": SimpleNamespace(
                        max_entry_intents_per_hour=6,
                        min_entry_spacing_sec=60,
                    )
                }
            },
        )
        write_blocked.return_value = {
            "strategy_id": "test_strat",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "stage": "STRATEGY",
            "reason_code": "TURNOVER_MIN_SPACING",
        }

        gw.process_signal(self._make_msg(1700000000000))
        dm._propose_trade_intent.assert_called_once()

        dm._propose_trade_intent.reset_mock()
        gw.process_signal(self._make_msg(1700000000000))

        dm._propose_trade_intent.assert_not_called()
        assert write_blocked.call_args.kwargs["reason_code"] == "TURNOVER_MIN_SPACING"

    @patch("apps.reference.domains.decision_making.gateway.strategy_gateway.order_logger.write")
    def test_nrr_overlay_is_capture_only_and_matches_exact_cohort(self, order_write, gateway):
        from types import SimpleNamespace

        gw, dm = gateway
        dm.config.strategies_registry = SimpleNamespace(
            counterfactual_overlays=[
                SimpleNamespace(
                    experiment_id="btc_md_amr_nrr063",
                    enabled=True,
                    strategy_id="md_amr",
                    symbol="BTCUSDT",
                    regime="TREND_DOWN",
                    sides=["BUY"],
                    nrr_codes=["NRR-063"],
                    holding_horizons_min=[15, 30, 60, 120],
                    minimum_independent_episodes=30,
                    minimum_market_days=3,
                )
            ]
        )

        gw._capture_nrr_counterfactual(
            symbol="BTCUSDT",
            strategy_id="md_amr",
            side="BUY",
            rid="nrr-overlay-1",
            reason_code="NRR-063",
            signal_payload={
                "structural_regime": "TREND_DOWN",
                "tf_sec": 300,
                "bar_close_ts": 1700000000,
            },
        )

        row = order_write.call_args.args[0]
        assert row["event_type"] == "NRR_COUNTERFACTUAL_CAPTURED"
        assert row["bar_close_ts"] == 1700000000000
        assert row["metadata"]["trading_authorized"] is False
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
