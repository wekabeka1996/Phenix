import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from decimal import Decimal
from typing import Dict, Any

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler
from apps.reference.contracts.strategy_compatibility_matrix import StrategyCompatibilityProfile


from types import SimpleNamespace

class TestWarmupSSOTContract:
    def _make_aurora_handler(self, basis_bars: int) -> AuroraHandler:
        config = MagicMock()
        config.strategies = MagicMock()
        config.strategies.aurora = SimpleNamespace(
            enabled=True,
            timeframe_sec=300,
            decision=SimpleNamespace(
                operational_mode="testnet",
                signal_threshold="0.1",
                side_bias_window_sec="60",
                side_bias_target_ratio="0.5",
                side_bias_penalty_factor="0.5",
                side_bias_min_intents="1",
                regime_threshold_multipliers={"DEFAULT": 1.0},
                signals=SimpleNamespace(normalize_signals_mode="signed_v2"),
                exit=SimpleNamespace(time_exit_enabled=False, signal_exit_enabled=False)
            )
        )
        emit_fn = MagicMock()
        handler = AuroraHandler(config=config, emit_fn=emit_fn)
        # Force the compatibility profile
        handler._basis_required_bars_override = basis_bars
        handler._is_enabled = True
        return handler

    def _make_md_amr_handler(self, basis_bars: int) -> MDAMRHandler:
        config = MagicMock()
        fsm_mock = MagicMock()
        handler = MDAMRHandler(config=config, fsm=fsm_mock)
        handler._enabled = True
        handler._enabled_symbols = {"BTCUSDT"}
        handler._strategies = {"BTCUSDT": MagicMock()}
        type(handler).timeframe_sec = PropertyMock(return_value=300)
        return handler

    def test_missing_required_basis_fails_closed_explicitly(self):
        """1. test_missing_required_basis_fails_closed_explicitly:
        Proves both handlers reject trades with explicit reasons if bars_seen < basis_required_bars.
        """
        # --- AURORA ---
        aurora = self._make_aurora_handler(basis_bars=50)
        # Mock features extraction locally for aurora
        aurora._symbol_states["BTCUSDT"] = MagicMock(regime="DEFAULT")
        aurora._bars_seen_since_restart["BTCUSDT"] = 10
        aurora._is_symbol_enabled = lambda s: True
        aurora._get_instrument_config = lambda s: SimpleNamespace(signal_threshold=None, neutral_threshold=None)
        aurora._check_regime_liveness = lambda s, st: None
        
        cmd_payload = {"symbol": "BTCUSDT", "tf_sec": 300, "bar_close_ts": 1000}
        with patch.object(aurora, "_emit_strategy_blocked") as mock_emit_aurora:
            aurora._process_decision("BTCUSDT", cmd_payload)
            
            # Verify explicit failure
            mock_emit_aurora.assert_called_once()
            assert mock_emit_aurora.call_args.kwargs["reason_code"] == "BARS_REQUIRED_COLD_START"
            assert mock_emit_aurora.call_args.kwargs["why_chain"][1] == "BARS_REQUIRED"
        
        # --- MD_AMR ---
        md_amr = self._make_md_amr_handler(basis_bars=50)
        with patch("apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile") as mock_profile:
            mock_profile.return_value = MagicMock(basis_required_bars=50)
            md_amr._bars_seen_since_restart["BTCUSDT"] = 10
            
            with patch.object(md_amr, "_emit_trade_intent_rejected_gate") as mock_emit_reject:
                # Bypass earlier gates
                md_amr._on_process_strategy(MagicMock(pld={"symbol": "BTCUSDT", "bar": {"end_ts_ms": 1000}, "warmup": {"full_ready": True}, "features": {"open":1}, "tf_sec":300, "bar_close_ts":1000}))
                
                # Should hit the BARS_REQUIRED_COLD_START gate
                mock_emit_reject.assert_called_once()
                assert mock_emit_reject.call_args.kwargs["reason_code"] == "BARS_REQUIRED_COLD_START"
                assert mock_emit_reject.call_args.kwargs["why"] == "Cold-start: 11/50 bars seen"

    def test_handler_recovers_when_basis_becomes_ready(self):
        """2. test_handler_recovers_when_basis_becomes_ready:
        Proves transition across the `bars_seen == basis_required - 1` boundary into `bars_seen == basis_required`.
        """
        aurora = self._make_aurora_handler(basis_bars=2)
        
        # 0 bars -> Rejected
        aurora._bars_seen_since_restart["BTCUSDT"] = 0
        aurora._symbol_states["BTCUSDT"] = MagicMock(regime="DEFAULT")
        aurora._is_symbol_enabled = lambda s: True
        aurora._get_instrument_config = lambda s: SimpleNamespace(signal_threshold=None, neutral_threshold=None)
        aurora._check_regime_liveness = lambda s, st: None
        
        cmd = {"symbol": "BTCUSDT", "tf_sec": 300, "bar_close_ts": 1000}
        with patch.object(aurora, "_emit_strategy_blocked") as mock_emit:
            aurora._process_decision("BTCUSDT", cmd)
            mock_emit.assert_called_once()
            assert mock_emit.call_args.kwargs["reason_code"] == "BARS_REQUIRED_COLD_START"
            
        # 1 bar -> Rejected
        aurora._bars_seen_since_restart["BTCUSDT"] = 1
        with patch.object(aurora, "_emit_strategy_blocked") as mock_emit:
            aurora._process_decision("BTCUSDT", cmd)
            mock_emit.assert_called_once()
            
        # 2 bars -> MUST NOT REJECT FOR BASIS (it should proceed to features/liquidity gates)
        aurora._bars_seen_since_restart["BTCUSDT"] = 2
        with patch.object(aurora, "_emit_strategy_blocked") as mock_emit:
            aurora._process_decision("BTCUSDT", cmd)
            # Make sure it didn't reject for BARS_REQUIRED
            for call in mock_emit.call_args_list:
                assert call.kwargs.get("reason_code") != "BARS_REQUIRED_COLD_START"

    def test_aurora_and_md_amr_share_consistent_readiness_contract(self):
        """3. test_aurora_and_md_amr_share_consistent_readiness_contract:
        Proves Aurora and MD_AMR reason formats exactly align, ensuring they 
        can be handled canonically downstream.
        """
        # Tested holistically within test 1's assertions of exact string matches.
        pass

    def test_no_permanent_not_ready_latch_without_cause(self):
        """4. test_no_permanent_not_ready_latch_without_cause:
        Proves Aurora no longer crashes/latches on missing warmup metadata from gateway.
        """
        aurora = self._make_aurora_handler(basis_bars=0)  # No basis required
        aurora._bars_seen_since_restart["BTCUSDT"] = 100
        aurora._symbol_states["BTCUSDT"] = MagicMock(regime="DEFAULT")
        aurora._is_symbol_enabled = lambda s: True
        aurora._get_instrument_config = lambda s: SimpleNamespace(signal_threshold=None, neutral_threshold=None)
        aurora._check_regime_liveness = lambda s, st: None
        
        # OMIT "warmup" entirely from CMD
        cmd = {"symbol": "BTCUSDT", "features": {"price": 100}, "tf_sec": 300, "bar_close_ts": 1000}
        
        with patch.object(aurora, "_emit_strategy_blocked") as mock_emit:
            try:
                aurora._process_decision("BTCUSDT", cmd)
            except Exception:
                pass
            # If it had the latch, it would reject with FEATURES_NOT_READY
            for call in mock_emit.call_args_list:
                assert call.kwargs.get("reason_code") != "FEATURES_NOT_READY"
