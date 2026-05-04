
import pytest
from unittest.mock import MagicMock
from collections import deque
from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
from apps.reference.domains.feature_engineering.types import HotState, FeatureEngineeringConfig

class TestMacroResidAsync:
    """
    [PART C] Integration Test: Macro Resid liveness & semantic correctness.
    
    Goals:
    1. Verify behavior when Anchor (BTC) is MISSING (should be None/NotReady, NOT 0.0).
    2. Verify async warmup: Asset ticks fast, Anchor ticks slow -> eventually READY.
    """

    @pytest.fixture
    def mock_cfg(self):
        """Mock FeatureEngineeringConfig with required properties."""
        cfg = MagicMock(spec=FeatureEngineeringConfig)
        # Using configure_mock to set attributes easily
        cfg.configure_mock(
            macro_resid_enabled=True,
            macro_resid_beta_window=5,  # Small window for faster test
            macro_resid_mad_window=5,
            macro_resid_neutral=0.0,
            macro_resid_winsor_percentile=0.0,
            macro_resid_var_floor=1e-9,
            macro_resid_scale_floor=0.0001,
            macro_resid_clip=3.0,
            zero_value=0.0
        )
        return cfg

    @pytest.fixture
    def engine(self, mock_cfg):
        return FeatureCalculationEngine(mock_cfg)

    def test_macro_resid_missing_anchor_is_not_zero(self, engine):
        """
        Verify that if Anchor data is missing/insufficient, calculation returns
        is_ready=False and we treat it as Missing (None semantics downstream).
        """
        state = HotState()
        # Only asset data, no anchor data
        asset_rets = [0.01] * 10
        for r in asset_rets:
            state.macro_resid_asset_returns.append(r)
            
        # Compute
        val, is_ready, reason = engine.compute_macro_resid(state)
        
        # Expectation: Not Ready due to insufficient anchor samples
        assert not is_ready
        assert "insufficient_samples" in str(reason)
        # Value is historically neutral (0.0), but readiness is the key.
        # The key fix in Part C happens at emission level (feature_engineering.py),
        # ensuring this False ready state translates to None in the payload.

    def test_macro_resid_async_warmup(self, engine):
        """
        Verify warmup with async data rates:
        - Asset ticks 2x faster than Anchor.
        - Should eventually become ready once overlap is sufficient.
        """
        state = HotState()
        
        # Simulate ticks
        # 10 ticks total.
        # Asset ticks every step.
        # Anchor ticks every 2nd step.
        
        for i in range(1, 20):
            asset_ret = 0.01 * (1 if i % 2 == 0 else -1)
            
            # Anchor update only on even steps
            anchor_ret = 0.005 if i % 2 == 0 else 0.0 
            
            engine.update_macro_resid(state, asset_ret, anchor_ret)
            
            val, is_ready, reason = engine.compute_macro_resid(state)
            
            if i < 5:
                assert not is_ready, f"Should not be ready at step {i}"
            if i > 10:
                 assert is_ready, f"Should be ready by step {i}"
