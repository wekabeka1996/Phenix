import pytest
import decimal
from unittest.mock import MagicMock
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler, SymbolState

class DummyScoringKernel:
    @classmethod
    def compute(cls, *args, **kwargs):
        pass

class TestEventExportAuroraAnomalies:

    @pytest.fixture
    def emit_fn(self):
        return MagicMock()

    @pytest.fixture
    def dlog(self):
        return MagicMock()
        
    @pytest.fixture
    def mock_config(self):
        cfg = MagicMock()
        cfg.domains.decision_making.position_sizing.min_position_size_usd = decimal.Decimal("10.0")
        cfg.domains.decision_making.position_sizing.liquidity_based_cap_usd = decimal.Decimal("1000.0")
        return cfg

    @pytest.fixture
    def aurora(self, emit_fn, dlog, mock_config):
        # Create without calling __init__ to bypass complex setup
        handler = object.__new__(AuroraHandler)
        handler.strategy_id = "aurora-test"
        handler.timeframe_sec = 900
        handler.emit_fn = emit_fn
        handler.dlog = dlog
        handler.logger = MagicMock()
        handler.config = mock_config
        handler.wall_time_fn = lambda: 1000
        handler.score_multiplier = 1.0
        handler.normalize_signals_mode = "NONE"
        handler.direction_strength_cfg = None
        handler.delta_price_cap_pct = 0.05
        handler._emit_strategy_blocked = MagicMock()
        handler.signal_threshold = decimal.Decimal("0.5")
        handler.neutral_threshold = decimal.Decimal("0.1")
        handler._basis_required_bars_override = 0
        handler._is_symbol_enabled = lambda s: True
        
        # Bypass other gates
        handler.vol_gates_enabled = False
        handler.holding_period_enabled = False
        handler.execution_gate = MagicMock()
        handler.exit_manager = MagicMock()
        
        # mock instrument config
        instr_cfg = MagicMock()
        instr_cfg.signal_threshold = 0.5
        instr_cfg.neutral_threshold = 0.1
        handler._get_instrument_config = lambda s: instr_cfg
        
        # We need mock functions for _check_regime_liveness and _get_regime_thresholds
        handler._check_regime_liveness = lambda *a, **k: None
        handler._get_regime_thresholds = lambda *a, **k: {"MEAN_REVERSION": 1.0, "HIGH_VOLATILITY": 1.0}
        handler._get_side_bias_state = lambda *a, **k: {}
        
        return handler

    def test_quadratic_kernel_crash_export(self, aurora, emit_fn):
        """
        Prove that when the scoring kernel crashes, Aurora emits EVT:QUADRATIC_KERNEL_CRASH
        before propagating the failure.
        """
        class CrashKernel:
            @classmethod
            def compute(cls, *args, **kwargs):
                raise Exception("Simulated Kernel Panic")

        aurora.scoring_kernel_cls = CrashKernel
        
        # Trigger evaluation
        features = {"price": 50000}
        state = SymbolState()
        state.regime = "MEAN_REVERSION"
        state.system_stress_state = "NORMAL"
        
        aurora._symbol_states = {"BTCUSDT": state}
        aurora._process_decision(
            symbol="BTCUSDT",
            cmd={
                "bar_close_ts": 1000,
                "features": features
            }
        )
        
        # Verify emit
        found = False
        for call_args, call_kwargs in emit_fn.call_args_list:
            if call_args[0] == "EVT:QUADRATIC_KERNEL_CRASH":
                found = True
                assert call_args[1]["symbol"] == "BTCUSDT"
                assert "Simulated Kernel Panic" in call_args[1]["error"]
        assert found, "EVT:QUADRATIC_KERNEL_CRASH was not emitted"

    def test_regime_shift_suspected_export(self, aurora, emit_fn):
        """
        Prove that when a differing, allowed regime is detected via inception filters,
        Aurora emits EVT:REGIME_SHIFT_SUSPECTED.
        """
        class WorkingKernel:
            @classmethod
            def compute(cls, *args, **kwargs):
                class MockResult:
                    score = 0.5
                    psi_vector = {}
                    shield_multiplier = 1.0
                    side = "BUY"
                    deferred = False
                    defer_reason = None
                    thr_buy = 0.5
                    thr_sell = 0.5
                    threshold_factor = 1.0
                return MockResult()

        aurora.scoring_kernel_cls = WorkingKernel
        
        aurora.config.regime_shift_inception = MagicMock(enabled=True)
        aurora._get_instrument_config = lambda s: MagicMock(
            signal_threshold=0.5,
            neutral_threshold=0.1,
            allowed_regimes=["MEAN_REVERSION", "HIGH_VOLATILITY"]
        )
        
        features = {
            "price": 50000,
        }
        state = SymbolState()
        state.regime = "MEAN_REVERSION"
        state.regime_raw_event = "HIGH_VOLATILITY"
        state.system_stress_state = "NORMAL"
        
        aurora._symbol_states = {"BTCUSDT": state}
        aurora._process_decision(
            symbol="BTCUSDT",
            cmd={
                "bar_close_ts": 1000,
                "features": features
            }
        )
        
        found = False
        for call_args, call_kwargs in emit_fn.call_args_list:
            if call_args[0] == "EVT:REGIME_SHIFT_SUSPECTED":
                found = True
                assert call_args[1]["symbol"] == "BTCUSDT"
                assert call_args[1]["raw_regime"] == "HIGH_VOLATILITY"
                assert call_args[1]["stable_regime"] == "MEAN_REVERSION"
        assert found, "EVT:REGIME_SHIFT_SUSPECTED was not emitted"
