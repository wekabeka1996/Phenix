import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from apps.reference.domains.decision_making.strategy_gateway import StrategyGateway
from apps.reference.domains.decision_making.intent_builder import IntentBuilder
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.config_resolver import DMConfigResolver

class TestArbitrationAtomicCommit:
    """TDD regression testing for DM-ARBITRATION-ATOMIC-COMMIT-PACK-R1.
    Ensure atomic arbitration check vs commit semantics, explicitly testing WAL and FSM fallbacks.
    """

    @pytest.fixture
    def environment(self):
        arb_signal_buffer = {}
        arb_window_winner = {}
        
        config = MagicMock()
        config.strategies = MagicMock()
        
        strategies_registry = MagicMock()
        strategies_registry.assignments = {"BTCUSDT": ["strat_A", "strat_B"]}
        strategies_registry.arbitration.mode = "priority"
        strategies_registry.arbitration.priority = {"strat_A": 1, "strat_B": 2}
        strategies_registry.arbitration.window_ms = 1000
        strategies_registry.arbitration.logging.rejected_why_prefix = "dropped"
        
        resolver = DMConfigResolver(
            config=config,
            strategies_registry=strategies_registry,
            arb_signal_buffer=arb_signal_buffer,
            arb_window_winner=arb_window_winner,
            flip_global_enabled=False,
            logger=MagicMock()
        )
        
        dm_mock = MagicMock()
        dm_mock._clock.now_ms.return_value = 1700000000000
        dm_mock.symbol_states = {"BTCUSDT": {"risk": {"risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}}}}
        dm_mock.config.domains.risk_management.trading_allowed_thresholds.max_risk_score = 100
        dm_mock.latest_portfolio = {"equity": 1000}
        
        dm_mock._check_strategy_arbitration = resolver.check_strategy_arbitration
        dm_mock._handle_flip_orchestration.return_value = None
        dm_mock._qos_enabled_for_strategy.return_value = False
        dm_mock._calculate_position_size.return_value = (Decimal("1.0"), "ok", None, None)
        dm_mock._precheck_exposure_cache.return_value = True
        dm_mock._warmup_gate_before_trade_intent.return_value = False
        dm_mock._degraded_context_gate_should_defer.return_value = False
        dm_mock._get_aurora_instrument_cfg.return_value = None
        
        gw = StrategyGateway(dm_mock)
        gw._reject = MagicMock()
        gw._defer = MagicMock()
        
        return gw, dm_mock, arb_signal_buffer, arb_window_winner, resolver

    def _make_msg(self, strategy_id="strat_A", ts_ms=1700000000000):
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
                "rid": f"test-{strategy_id}",
                "ts_ms": ts_ms,
                "tf_sec": 300,
                "intent_kind": "ENTRY",
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

    def _make_intent_builder(self, resolver):
        tca_mock = {"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": False}
        risk_mock = {"trade_cvar95_max_bps": 50, "session_cvar95_max_bps": 100}

        return IntentBuilder(
            logger=MagicMock(),
            fsm=MagicMock(),
            check_strategy_arbitration_fn=resolver.check_strategy_arbitration,
            clock=MagicMock(),
            config=MagicMock(),
            tca_prefs=tca_mock,
            risk_budgets=risk_mock,
            safe_decimal_fn=lambda x, default: Decimal(x) if x else default,
            warmup_gate_fn=lambda **kw: False,
            emit_rejected_fn=MagicMock(),
            record_blocked_fn=MagicMock(),
            record_accepted_fn=MagicMock(),
            emit_deferred_fn=MagicMock(),
            get_side_bias_params_fn=MagicMock(),
            side_intent_window={}
        )

    class MockSG:
        def __init__(self, strat="strat_A", ts_ms=1700000000000):
            self.intent_side = "BUY"
            self.trace_ts_ms = ts_ms
            self.strategy_id = strat
            self.why_short = ""
            self.signal_score = 0.5
            self.regime = "TREND_UP"
            self.regime_confidence = 0.9
            self.trend_dir = 1
            self.trend_run_length = 1
            self.delta_price = 0
            self.pm_norm_10s = 0
            self.pm_norm_60s = 0
            self.pm_norm_300s = 0
            self.vol_pct_10s = 0
            self.vol_pct_60s = 0
            self.vol_pct_300s = 0

    @patch("apps.reference.domains.decision_making.strategy_gateway.resolve_strategy_entry_prices")
    def test_precheck_does_not_mutate_window(self, mock_resolve, environment):
        """1. precheck_does_not_mutate_window
        Strategy A wins arbitration check but fails sizing. The window must NOT be poisoned for Strategy B.
        """
        mock_resolve.return_value = (None, None, None)
        gw, dm, arb_signal_buffer, arb_window_winner, resolver = environment
        
        dm._calculate_position_size.side_effect = Exception("Forced Downstream Failure")
        
        msg_A = self._make_msg(strategy_id="strat_A", ts_ms=1700000000000)
        gw.process_signal(msg_A)
        
        # Verify A aborted on exception at Pre-Check phase
        gw._reject.assert_called_once()
        assert "BTCUSDT" not in arb_signal_buffer
        assert "BTCUSDT" not in arb_window_winner
        
        dm._calculate_position_size.side_effect = None
        dm._calculate_position_size.return_value = (Decimal("1.0"), "ok", None, None)
        gw._reject.reset_mock()
        
        # Verify B passes cleanly
        msg_B = self._make_msg(strategy_id="strat_B", ts_ms=1700000000000)
        gw.process_signal(msg_B)
        
        gw._reject.assert_not_called()
        dm._propose_trade_intent.assert_called_once()

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_successful_path_commits_once(self, mock_resolve_policy, mock_wal, environment):
        """2. successful_path_commits_once
        When IntentBuilder proproses a trade fully, it successfully commits exactly once.
        """
        _, dm, arb_signal_buffer, arb_window_winner, resolver = environment
        mock_resolve_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "msgId"
        builder = self._make_intent_builder(resolver)

        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="123", reduce_only=False, strategy_id="strat_A",
            decision_ts_ms=1700000000000, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_A"),
        )
        
        assert "BTCUSDT" in arb_signal_buffer
        assert arb_signal_buffer["BTCUSDT"][1] == "strat_A"

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_post_commit_wal_failure_does_not_poison_window(self, mock_resolve_policy, mock_wal, environment):
        """3. post_commit_wal_failure_does_not_poison_window
        Simulate WAL append failure.
        Competing strategy B must still be able to proceed.
        """
        _, dm, arb_signal_buffer, arb_window_winner, resolver = environment
        mock_resolve_policy.return_value = ("LIMIT", "GTC", 10000)
        builder = self._make_intent_builder(resolver)
        
        # Simulate WAL failure
        mock_wal.side_effect = Exception("WAL append failed timeout lock")
        
        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="123", reduce_only=False, strategy_id="strat_A",
            decision_ts_ms=1700000000000, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_A"),
        )
        # Because WAL failed, the fsm.emit for intent wasn't reached and the commit wasn't reached
        emit_calls = [c for c in builder._fsm.emit.call_args_list if c.args[0] == "EVT:TRADE_INTENT_PROPOSED"]
        assert len(emit_calls) == 0
        
        # Window must remain cleanly OPEN
        assert "BTCUSDT" not in arb_signal_buffer
        assert "BTCUSDT" not in arb_window_winner

        # Strategy B comes along, WAL succeeds
        builder._fsm.emit.reset_mock()
        mock_wal.side_effect = None
        mock_wal.return_value = "success-id"
        
        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="456", reduce_only=False, strategy_id="strat_B",
            decision_ts_ms=1700000000000, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_B"),
        )
        assert builder._fsm.emit.call_count > 0
        assert "BTCUSDT" in arb_signal_buffer
        assert arb_signal_buffer["BTCUSDT"][1] == "strat_B"

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_post_commit_emit_failure_does_not_poison_window(self, mock_resolve_policy, mock_wal, environment):
        """4. post_commit_emit_failure_does_not_poison_window
        Simulate FSM emit failure.
        Competing strategy B must still be able to proceed.
        """
        _, dm, arb_signal_buffer, arb_window_winner, resolver = environment
        mock_resolve_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "id"
        builder = self._make_intent_builder(resolver)
        
        # FSM explicitly fails for TRACE
        def broken_emit(evt_name, **kwargs):
            raise Exception("Broker FSM emitted failed")
        builder._fsm.emit.side_effect = broken_emit
        
        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="123", reduce_only=False, strategy_id="strat_A",
            decision_ts_ms=1700000000000, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_A"),
        )
        
        # Window must remain cleanly OPEN because it failed before final commit
        assert "BTCUSDT" not in arb_signal_buffer
        assert "BTCUSDT" not in arb_window_winner
        
        # Strategy B comes along, FSM succeeds
        builder._fsm.emit.side_effect = None
        
        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="456", reduce_only=False, strategy_id="strat_B",
            decision_ts_ms=1700000000000, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_B"),
        )
        assert builder._fsm.emit.call_count > 0
        assert "BTCUSDT" in arb_signal_buffer
        assert arb_signal_buffer["BTCUSDT"][1] == "strat_B"

    @patch("apps.reference.domains.decision_making.strategy_gateway.resolve_strategy_entry_prices")
    def test_failed_candidate_does_not_create_sticky_winner(self, mock_resolve, environment):
        """5. failed_candidate_does_not_create_sticky_winner
        Downstream failures in Gateway should leave no ghost winner in the buffer.
        """
        mock_resolve.return_value = (None, None, None)
        gw, dm, arb_signal_buffer, arb_window_winner, resolver = environment
        
        dm._qos_enabled_for_strategy.return_value = True
        dm._qos_allow.return_value = (False, "rate_limited")
        dm.qos_enforce = True
        dm.qos_mode = "enforce"
        
        msg_A = self._make_msg(strategy_id="strat_A", ts_ms=1700000000000)
        gw.process_signal(msg_A)
        
        gw._reject.assert_called_once()
        assert gw._reject.call_args.kwargs["reason_code"] == "QOS_RATE_LIMIT"
        assert "BTCUSDT" not in arb_signal_buffer

    @patch("apps.reference.domains.decision_making.intent_builder.wal.append")
    @patch("apps.reference.domains.decision_making.intent_builder.IntentBuilder._resolve_order_policy")
    def test_deterministic_competing_strategy_behavior(self, mock_resolve_policy, mock_wal, environment):
        """6. deterministic_competing_strategy_behavior
        If A and B both reach IntentBuilder, A commits, B is correctly blocked by A.
        """
        _, dm, arb_signal_buffer, arb_window_winner, resolver = environment
        mock_resolve_policy.return_value = ("LIMIT", "GTC", 10000)
        mock_wal.return_value = "id"
        builder = self._make_intent_builder(resolver)
        builder._record_blocked = MagicMock()
            
        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="123", reduce_only=False, strategy_id="strat_A",
            decision_ts_ms=1700000000000, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_A", 1700000000000),
        )
        assert builder._fsm.emit.call_count > 0
        builder._fsm.emit.reset_mock()
            
        builder.build_and_emit(
            symbol="BTCUSDT", side="BUY", qty=Decimal("1.0"), price=Decimal("50000"),
            why_chain=[], rid="456", reduce_only=False, strategy_id="strat_B",
            decision_ts_ms=1700000000500, stop_price=None, target_price=None,
            entry_plan_trace=None, tf_sec=None, max_slippage_bps=None,
            max_latency_ms=None, risk_score=None, strategy_trace=None, sg=self.MockSG("strat_B", 1700000000500),
        )
        builder._fsm.emit.assert_not_called()
        builder._record_blocked.assert_called_once()
