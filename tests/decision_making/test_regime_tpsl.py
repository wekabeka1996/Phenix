"""
Unit tests for Regime-Based TP/SL (AURORA_REGIME_TP_SL_PLAN).

Tests the compute_regime_tpsl functionality in AuroraHandler:
1. pct_mult mode: correct SL/TP calculation with multipliers
2. atr mode: ATR-based calculation
3. Guardrails: min/max clamp, side validation
4. Fallback: DEFAULT key, disabled config
"""
import decimal
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestRegimeTpSlConfig:
    """Test RegimeTpSlConfig model validation."""

    def test_pct_mult_requires_default_in_sl_mult(self):
        """pct_mult mode: sl_mult must have DEFAULT key."""
        from apps.reference.config_models import RegimeTpSlConfig

        with pytest.raises(ValueError, match="sl_mult must contain 'DEFAULT' key"):
            RegimeTpSlConfig(
                enabled=True,
                mode="pct_mult",
                sl_mult={"TREND_UP": 1.1},  # Missing DEFAULT
                tp_mult={"DEFAULT": 1.0},
            )

    def test_pct_mult_requires_default_in_tp_mult(self):
        """pct_mult mode: tp_mult must have DEFAULT key."""
        from apps.reference.config_models import RegimeTpSlConfig

        with pytest.raises(ValueError, match="tp_mult must contain 'DEFAULT' key"):
            RegimeTpSlConfig(
                enabled=True,
                mode="pct_mult",
                sl_mult={"DEFAULT": 1.0},
                tp_mult={"TREND_UP": 1.25},  # Missing DEFAULT
            )

    def test_atr_mode_requires_sl_k_atr_default(self):
        """atr mode: sl_k_atr must have DEFAULT key."""
        from apps.reference.config_models import RegimeTpSlConfig

        with pytest.raises(ValueError, match="sl_k_atr must contain 'DEFAULT' key"):
            RegimeTpSlConfig(
                enabled=True,
                mode="atr",
                sl_k_atr={"TREND_UP": 6.5},  # Missing DEFAULT
                rr_by_regime={"DEFAULT": 0.9},
            )

    def test_atr_mode_requires_rr_by_regime_default(self):
        """atr mode: rr_by_regime must have DEFAULT key."""
        from apps.reference.config_models import RegimeTpSlConfig

        with pytest.raises(ValueError, match="rr_by_regime must contain 'DEFAULT' key"):
            RegimeTpSlConfig(
                enabled=True,
                mode="atr",
                sl_k_atr={"DEFAULT": 5.5},
                rr_by_regime={"TREND_UP": 1.3},  # Missing DEFAULT
            )

    def test_valid_pct_mult_config(self):
        """Valid pct_mult config passes validation."""
        from apps.reference.config_models import RegimeTpSlConfig

        cfg = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0, "TREND_UP": 1.1},
            tp_mult={"DEFAULT": 1.0, "TREND_UP": 1.25},
        )
        assert cfg.enabled is True
        assert cfg.mode == "pct_mult"

    def test_valid_atr_config(self):
        """Valid atr config passes validation."""
        from apps.reference.config_models import RegimeTpSlConfig

        cfg = RegimeTpSlConfig(
            enabled=True,
            mode="atr",
            sl_k_atr={"DEFAULT": 5.5, "TREND_UP": 6.5},
            rr_by_regime={"DEFAULT": 0.9, "TREND_UP": 1.3},
        )
        assert cfg.enabled is True
        assert cfg.mode == "atr"


class TestComputeRegimeTpsl:
    """Test _compute_regime_tpsl helper in AuroraHandler."""

    @pytest.fixture
    def mock_handler(self):
        """Create a minimal mock AuroraHandler for testing."""
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler, SymbolState

        # Build a proper mock config that passes _load_config validation
        mock_decision = MagicMock()
        mock_decision.signal_threshold = "0.1"
        mock_decision.side_bias_window_sec = 420
        mock_decision.side_bias_target_ratio = 0.72
        mock_decision.side_bias_penalty_factor = 0.25
        mock_decision.side_bias_min_intents = 18
        mock_decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
        mock_decision.operational_mode = "paranoid"
        mock_decision.direction_strength_scoring = None
        mock_decision.signals = None
        mock_decision.neutral_threshold = None
        mock_decision.holding_period = None
        mock_decision.reentry_cooldown_sec = None
        mock_decision.anti_churn = None
        mock_decision.gates = None
        mock_decision.scoring_version = "quadratic"
        mock_decision.scoring_engine = None
        mock_decision.quadratic_rollout = None

        mock_aurora = MagicMock()
        mock_aurora.timeframe_sec = 300
        mock_aurora.decision = mock_decision
        mock_aurora.assets = {}

        mock_strategies = MagicMock()
        mock_strategies.aurora = mock_aurora

        mock_config = MagicMock()
        mock_config.strategies = mock_strategies

        # Create handler with mocked emit_fn
        handler = AuroraHandler(
            config=mock_config,
            emit_fn=MagicMock(),
            strategy_id="test_aurora",
        )

        # Initialize symbol state
        handler._symbol_states["BTCUSDT"] = SymbolState()
        handler._symbol_states["BTCUSDT"].regime = "TREND_UP"
        handler._symbol_states["BTCUSDT"].regime_effective = "TREND_UP"
        handler.anti_churn_enabled = False

        return handler

    def test_disabled_returns_none(self, mock_handler):
        """When regime_tpsl.enabled=false, returns None."""
        from apps.reference.config_models import RegimeTpSlConfig

        # Build instr_cfg using MagicMock with proper nested structure
        regime_tpsl = RegimeTpSlConfig(
            enabled=False,  # Disabled
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="TREND_UP",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is None

    def test_pct_mult_buy_correct_sides(self, mock_handler):
        """BUY: SL below entry, TP above entry."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02  # 2%
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is not None
        assert result["stop_price"] < Decimal("50000")  # SL below entry
        assert result["target_price"] > Decimal("50000")  # TP above entry
        assert result["tpsl_ctx"]["mode"] == "pct_mult"

    def test_pct_mult_sell_correct_sides(self, mock_handler):
        """SELL: SL above entry, TP below entry."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="SELL",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is not None
        assert result["stop_price"] > Decimal("50000")  # SL above entry
        assert result["target_price"] < Decimal("50000")  # TP below entry

    def test_pct_mult_regime_multipliers_applied(self, mock_handler):
        """Regime multipliers are correctly applied."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0, "TREND_UP": 1.1},  # 10% wider SL
            tp_mult={"DEFAULT": 1.0, "TREND_UP": 1.25},  # 25% wider TP
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02  # 2% base
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        # Get DEFAULT result
        mock_handler._symbol_states["BTCUSDT"].regime_effective = None
        result_default = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        # Get TREND_UP result
        mock_handler._symbol_states["BTCUSDT"].regime_effective = None
        result_trend = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="TREND_UP",
            instr_cfg=instr_cfg,
            features={},
        )

        # TREND_UP should have wider SL (lower stop for BUY)
        assert result_trend["stop_price"] < result_default["stop_price"]
        # TREND_UP should have wider TP (higher target for BUY)
        assert result_trend["target_price"] > result_default["target_price"]

        # Verify tpsl_ctx
        assert result_trend["tpsl_ctx"]["sl_mult"] == 1.1
        assert result_trend["tpsl_ctx"]["tp_mult"] == 1.25

    def test_fallback_to_default_for_unknown_regime(self, mock_handler):
        """Unknown regime falls back to DEFAULT."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="UNKNOWN_REGIME",  # Not in config
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is not None
        assert result["tpsl_ctx"]["sl_mult"] == 1.0  # DEFAULT


class TestTpslGuardrails:
    """Test guardrail logic for TP/SL values."""

    @pytest.fixture
    def mock_handler(self):
        """Create a minimal mock AuroraHandler for testing."""
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler, SymbolState

        # Build a proper mock config
        mock_decision = MagicMock()
        mock_decision.signal_threshold = "0.1"
        mock_decision.side_bias_window_sec = 420
        mock_decision.side_bias_target_ratio = 0.72
        mock_decision.side_bias_penalty_factor = 0.25
        mock_decision.side_bias_min_intents = 18
        mock_decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
        mock_decision.operational_mode = "paranoid"
        mock_decision.direction_strength_scoring = None
        mock_decision.signals = None
        mock_decision.neutral_threshold = None
        mock_decision.holding_period = None
        mock_decision.reentry_cooldown_sec = None
        mock_decision.anti_churn = None
        mock_decision.gates = None
        mock_decision.scoring_version = "quadratic"
        mock_decision.scoring_engine = None
        mock_decision.quadratic_rollout = None

        mock_aurora = MagicMock()
        mock_aurora.timeframe_sec = 300
        mock_aurora.decision = mock_decision
        mock_aurora.assets = {}

        mock_strategies = MagicMock()
        mock_strategies.aurora = mock_aurora

        mock_config = MagicMock()
        mock_config.strategies = mock_strategies

        handler = AuroraHandler(
            config=mock_config,
            emit_fn=MagicMock(),
            strategy_id="test_aurora",
        )

        handler._symbol_states["BTCUSDT"] = SymbolState()
        handler.anti_churn_enabled = False

        return handler

    def test_guardrail_clamps_sl_to_min(self, mock_handler):
        """SL% below min_sl_pct gets clamped up."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
            min_sl_pct=0.003,  # 0.3%
            min_dist_bps=5,  # Lower min_dist_bps for this test
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.001  # 0.1% - below min_sl_pct (0.3%)
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        # Use tp_low_ratio=1.0 so TP = SL distance → passes min_dist_bps
        instr_cfg.take_profit = MagicMock(tp_low_ratio=1.0)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is not None
        assert result["tpsl_ctx"].get("guardrail_sl_clamp") == "min"

        # Verify SL is at min distance
        sl_dist = (Decimal("50000") - result["stop_price"]) / Decimal("50000")
        assert float(sl_dist) >= 0.003 - 0.0001  # ~0.3%

    def test_guardrail_clamps_sl_to_max(self, mock_handler):
        """SL% above max_sl_pct gets clamped down."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
            max_sl_pct=0.06,  # 6%
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.10  # 10% - above max_sl_pct (6%)
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is not None
        assert result["tpsl_ctx"].get("guardrail_sl_clamp") == "max"

        # Verify SL is at max distance
        sl_dist = (Decimal("50000") - result["stop_price"]) / Decimal("50000")
        assert float(sl_dist) <= 0.06 + 0.0001  # ~6%

    def test_guardrail_clamps_rr_to_max_records_pre_post(self, mock_handler):
        """RR above max_tp_rr gets clamped down and telemetry records rr_pre/rr_post."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
            max_tp_rr=3.0,
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        # tp_low_ratio is used as RR multiplier in pct_mult mode.
        instr_cfg.take_profit = MagicMock(tp_low_ratio=4.0)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is not None
        ctx = result["tpsl_ctx"]
        assert ctx.get("guardrail_rr_clamp") == "max"
        assert ctx.get("rr_pre") == pytest.approx(4.0)
        assert ctx.get("rr_post") == pytest.approx(3.0)
        assert ctx.get("rr_eff") == pytest.approx(3.0)


class TestAtrMode:
    """Test ATR-based TP/SL calculation."""

    @pytest.fixture
    def mock_handler(self):
        """Create a minimal mock AuroraHandler for testing."""
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler, SymbolState

        # Build a proper mock config
        mock_decision = MagicMock()
        mock_decision.signal_threshold = "0.1"
        mock_decision.side_bias_window_sec = 420
        mock_decision.side_bias_target_ratio = 0.72
        mock_decision.side_bias_penalty_factor = 0.25
        mock_decision.side_bias_min_intents = 18
        mock_decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
        mock_decision.operational_mode = "paranoid"
        mock_decision.direction_strength_scoring = None
        mock_decision.signals = None
        mock_decision.neutral_threshold = None
        mock_decision.holding_period = None
        mock_decision.reentry_cooldown_sec = None
        mock_decision.anti_churn = None
        mock_decision.gates = None
        mock_decision.scoring_version = "quadratic"
        mock_decision.scoring_engine = None
        mock_decision.quadratic_rollout = None

        mock_aurora = MagicMock()
        mock_aurora.timeframe_sec = 300
        mock_aurora.decision = mock_decision
        mock_aurora.assets = {}

        mock_strategies = MagicMock()
        mock_strategies.aurora = mock_aurora

        mock_config = MagicMock()
        mock_config.strategies = mock_strategies

        handler = AuroraHandler(
            config=mock_config,
            emit_fn=MagicMock(),
            strategy_id="test_aurora",
        )

        handler._symbol_states["BTCUSDT"] = SymbolState()
        handler.anti_churn_enabled = False

        return handler

    def test_atr_mode_requires_atr_feature(self, mock_handler):
        """ATR mode returns None when ATR feature is missing."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="atr",
            sl_k_atr={"DEFAULT": 5.5},
            rr_by_regime={"DEFAULT": 0.9},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},  # No ATR
        )

        assert result is None

    def test_atr_mode_calculates_correctly(self, mock_handler):
        """ATR mode calculates TP/SL based on ATR%."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="atr",
            sl_k_atr={"DEFAULT": 5.0},  # SL = 5 × ATR%
            rr_by_regime={"DEFAULT": 1.0},  # RR = 1:1
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit

        # ATR = 500 → ATR% = 500/50000 = 1%
        # SL% = 5 × 1% = 5%
        # TP = SL × RR = 5%
        features = {
            "volatility": {"atr_14": 500},
        }

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features=features,
        )

        assert result is not None
        assert result["tpsl_ctx"]["mode"] == "atr"
        assert result["tpsl_ctx"]["atr"] == 500

        # SL ~5% below entry
        expected_sl = Decimal("50000") * (1 - Decimal("0.05"))  # 47500
        assert abs(result["stop_price"] - expected_sl) < Decimal("1")

        # TP ~5% above entry
        expected_tp = Decimal("50000") * (1 + Decimal("0.05"))  # 52500
        assert abs(result["target_price"] - expected_tp) < Decimal("1")


class TestFailClosedLogic:
    """Test fail-closed behavior when config is missing."""

    @pytest.fixture
    def mock_handler(self):
        """Create a minimal mock AuroraHandler for testing."""
        from apps.reference.domains.decision_making.aurora_handler import AuroraHandler, SymbolState

        # Build a proper mock config
        mock_decision = MagicMock()
        mock_decision.signal_threshold = "0.1"
        mock_decision.side_bias_window_sec = 420
        mock_decision.side_bias_target_ratio = 0.72
        mock_decision.side_bias_penalty_factor = 0.25
        mock_decision.side_bias_min_intents = 18
        mock_decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
        mock_decision.operational_mode = "paranoid"
        mock_decision.direction_strength_scoring = None
        mock_decision.signals = None
        mock_decision.neutral_threshold = None
        mock_decision.holding_period = None
        mock_decision.reentry_cooldown_sec = None
        mock_decision.anti_churn = None
        mock_decision.gates = None
        mock_decision.scoring_version = "quadratic"
        mock_decision.scoring_engine = None
        mock_decision.quadratic_rollout = None

        mock_aurora = MagicMock()
        mock_aurora.timeframe_sec = 300
        mock_aurora.decision = mock_decision
        mock_aurora.assets = {}

        mock_strategies = MagicMock()
        mock_strategies.aurora = mock_aurora

        mock_config = MagicMock()
        mock_config.strategies = mock_strategies

        handler = AuroraHandler(
            config=mock_config,
            emit_fn=MagicMock(),
            strategy_id="test_aurora",
        )

        handler._symbol_states["BTCUSDT"] = SymbolState()
        handler.anti_churn_enabled = False

        return handler

    def test_fail_closed_missing_sl_pct(self, mock_handler):
        """pct_mult mode fails if sl_pct is None."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = None  # Missing!
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=0.5)

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is None  # Fail-closed

    def test_fail_closed_missing_tp_low_ratio(self, mock_handler):
        """pct_mult mode fails if tp_low_ratio is None."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = MagicMock(tp_low_ratio=None)  # Missing!

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is None  # Fail-closed

    def test_fail_closed_no_take_profit_config(self, mock_handler):
        """pct_mult mode fails if take_profit config is entirely missing."""
        from apps.reference.config_models import RegimeTpSlConfig

        regime_tpsl = RegimeTpSlConfig(
            enabled=True,
            mode="pct_mult",
            sl_mult={"DEFAULT": 1.0},
            tp_mult={"DEFAULT": 1.0},
        )

        mock_exit = MagicMock()
        mock_exit.sl_pct = 0.02
        mock_exit.regime_tpsl = regime_tpsl

        instr_cfg = MagicMock()
        instr_cfg.exit = mock_exit
        instr_cfg.take_profit = None  # Entirely missing!

        result = mock_handler._compute_regime_tpsl(
            symbol="BTCUSDT",
            entry_price=Decimal("50000"),
            side="BUY",
            regime="DEFAULT",
            instr_cfg=instr_cfg,
            features={},
        )

        assert result is None  # Fail-closed
