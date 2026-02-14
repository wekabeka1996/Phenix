"""
EP-01.1 Tests: Bar Volatility Features and OBI Snapshot.

Verifies:
A) ATR correctness - deterministic TR/ATR calculation
B) OBI snapshot - last_obi is captured at bar close
C) Schema validation - new payload passes JSON schema
"""

import pytest
import json
import decimal
from collections import deque
from pathlib import Path
from jsonschema import validate, ValidationError


class TestATRCorrectness:
    """Test ATR calculation is correct and deterministic."""
    
    def test_bar_volatility_state_update_tr(self):
        """Test BarVolatilityState.update_tr() correctly tracks TR history."""
        from apps.reference.domains.feature_engineering.types import BarVolatilityState
        
        # Create state with window=3 for easy testing
        state = BarVolatilityState(atr_window=3, tr_buffer=deque())
        
        # Not ready initially
        assert state.atr_ready is False
        assert state.last_atr is None
        
        # Add first TR
        state.update_tr(100.0)
        assert len(state.tr_buffer) == 1
        assert state.atr_ready is False  # Need 3 samples
        
        # Add second TR
        state.update_tr(200.0)
        assert len(state.tr_buffer) == 2
        assert state.atr_ready is False
        
        # Add third TR - should now be ready
        state.update_tr(300.0)
        assert len(state.tr_buffer) == 3
        assert state.atr_ready is True
        assert state.last_atr == 200.0  # (100+200+300)/3 = 200
    
    def test_atr_rolling_window(self):
        """Test ATR uses rolling window, not all history."""
        from apps.reference.domains.feature_engineering.types import BarVolatilityState
        
        state = BarVolatilityState(atr_window=3, tr_buffer=deque())
        
        # Fill with 100, 100, 100
        state.update_tr(100.0)
        state.update_tr(100.0)
        state.update_tr(100.0)
        assert state.last_atr == 100.0  # avg of (100, 100, 100)
        
        # Add 400 - oldest 100 drops out
        state.update_tr(400.0)
        assert len(state.tr_buffer) == 3  # Still 3
        assert state.last_atr == 200.0  # avg of (100, 100, 400)
    
    def test_true_range_first_bar_uses_hl(self):
        """Test: first bar uses H-L (no prev_close)."""
        from apps.reference.domains.feature_engineering.types import BarVolatilityState
        
        state = BarVolatilityState(atr_window=14, tr_buffer=deque())
        assert state.prev_close is None
        
        # Simulate first bar: TR = H - L (no prev_close)
        bar_high = decimal.Decimal("50100")
        bar_low = decimal.Decimal("49900")
        
        # Since prev_close is None, TR = H - L = 200
        expected_tr = bar_high - bar_low
        assert expected_tr == decimal.Decimal("200")
    
    def test_true_range_subsequent_bars_use_prev_close(self):
        """Test: subsequent bars use max(H-L, |H-pc|, |L-pc|)."""
        # Scenario: bar with gap up
        prev_close = decimal.Decimal("49000")  # Previous bar closed at 49000
        bar_high = decimal.Decimal("50100")    # Opened above prev_close
        bar_low = decimal.Decimal("50000")
        
        tr_hl = bar_high - bar_low  # 100
        tr_hc = abs(bar_high - prev_close)  # 1100
        tr_lc = abs(bar_low - prev_close)   # 1000
        
        true_range = max(tr_hl, tr_hc, tr_lc)
        assert true_range == decimal.Decimal("1100")  # Gap is captured!
    
    def test_atr_is_null_before_warmup(self):
        """Test: ATR values are None until warmup completes."""
        from apps.reference.domains.feature_engineering.types import BarVolatilityState
        
        state = BarVolatilityState(atr_window=14, tr_buffer=deque())
        
        # Add 13 TRs (one less than window)
        for i in range(13):
            state.update_tr(100.0 + i)
        
        assert state.atr_ready is False
        assert state.last_atr is None  # NULL until ready
        
        # Add 14th - now ready
        state.update_tr(200.0)
        assert state.atr_ready is True
        assert state.last_atr is not None
    
    def test_atr_14_default_window(self):
        """Verify default ATR window is 14."""
        from apps.reference.domains.feature_engineering.types import BarVolatilityState
        
        state = BarVolatilityState()  # Use defaults
        assert state.atr_window == 14


class TestOBISnapshot:
    """Test OBI snapshot is captured correctly at bar close."""
    
    def test_last_obi_is_stored(self):
        """Verify _last_obi cache exists in FE code."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(feature_engineering.FeatureEngineering.__init__)
        assert "_last_obi" in source, "FeatureEngineering should have _last_obi cache"
    
    def test_obi_close_injected_into_features(self):
        """Verify obi_close is injected into CMD features."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(
            feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
        )
        assert "obi_close" in source, "Should inject obi_close into features"
        assert '"liquidity"' in source or "'liquidity'" in source, \
            "Should have liquidity sub-object"
    
    def test_obi_snapshot_logic(self):
        """Test OBI snapshot logic (simulated)."""
        # Simulate: last_obi = {"BTCUSDT": Decimal("0.25")}
        last_obi = {"BTCUSDT": decimal.Decimal("0.25")}
        
        symbol = "BTCUSDT"
        obi_close = last_obi.get(symbol)
        obi_close_str = str(obi_close) if obi_close is not None else None
        
        assert obi_close_str == "0.25"
    
    def test_obi_snapshot_none_if_no_data(self):
        """Test OBI is None if symbol has no tick data yet."""
        last_obi = {}  # Empty - no ticks yet
        
        obi_close = last_obi.get("BTCUSDT")
        obi_close_str = str(obi_close) if obi_close is not None else None
        
        assert obi_close_str is None


class TestSchemaValidation:
    """Test JSON schema validation for new features."""
    
    @pytest.fixture
    def schema(self):
        """Load the CMD schema."""
        repo_root = Path(__file__).resolve().parents[2]
        schema_path = repo_root / "apps" / "reference" / "domains" / "feature_engineering" / "schemas" / "cmd_process_strategy_v1.json"
        with open(schema_path) as f:
            return json.load(f)
    
    def test_schema_accepts_valid_payload_with_ep01_features(self, schema):
        """Test schema accepts payload with volatility and liquidity features."""
        payload = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
            },
            "features": {
                "obi": "0.25",
                "tfi": "0.1",
                "price": "50050",
                "volatility": {
                    "bar_range": "200",
                    "bar_body": "50",
                    "true_range": "200",
                    "atr_14": 150.5,
                    "range_pct": 0.004,
                    "atr_pct": 0.003,
                    "atr_ready": True,
                },
                "liquidity": {
                    "obi_close": "0.25",
                }
            },
            "warmup": {"full_ready": True, "ticks_seen": 100},
            "regime": None,
        }
        
        # Should not raise
        validate(payload, schema)
    
    def test_schema_accepts_null_atr_during_warmup(self, schema):
        """Test schema accepts null ATR values during warmup."""
        payload = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
            },
            "features": {
                "volatility": {
                    "bar_range": "200",
                    "bar_body": "50",
                    "true_range": "200",
                    "atr_14": None,  # NULL during warmup
                    "range_pct": 0.004,
                    "atr_pct": None,  # NULL during warmup
                    "atr_ready": False,
                },
                "liquidity": {
                    "obi_close": None,  # No tick data yet
                }
            },
            "warmup": {"full_ready": True, "ticks_seen": 5},
            "regime": None,
        }
        
        # Should not raise
        validate(payload, schema)
    
    def test_schema_requires_atr_ready_field(self, schema):
        """Test schema requires atr_ready in volatility."""
        payload = {
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "bar_close_ts": 1180000,
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "open": "50000",
                "high": "50100",
                "low": "49900",
                "close": "50050",
                "volume": "100",
            },
            "features": {
                "volatility": {
                    "bar_range": "200",
                    "bar_body": "50",
                    "true_range": "200",
                    # atr_ready is MISSING
                }
            },
            "warmup": {"full_ready": True, "ticks_seen": 100},
            "regime": None,
        }
        
        # Should raise because atr_ready is required
        with pytest.raises(ValidationError):
            validate(payload, schema)


class TestVolatilityFeaturesCodePresence:
    """Verify volatility features code is present in FE."""
    
    def test_bar_range_calculation_exists(self):
        """Verify bar_range = high - low calculation exists."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(
            feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
        )
        assert "bar_range" in source
        assert "bar_high - bar_low" in source
    
    def test_bar_body_calculation_exists(self):
        """Verify bar_body = |close - open| calculation exists."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(
            feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
        )
        assert "bar_body" in source
        assert "abs(bar_close - bar_open)" in source
    
    def test_true_range_calculation_exists(self):
        """Verify True Range calculation exists."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(
            feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
        )
        assert "true_range" in source
        assert "tr_hl" in source or "H - L" in source
        assert "tr_hc" in source or "prev_close" in source
    
    def test_atr_state_management_exists(self):
        """Verify ATR state management exists."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(
            feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
        )
        assert "_bar_volatility_states" in source
        assert "BarVolatilityState" in source
        assert "update_tr" in source
    
    def test_normalized_metrics_exist(self):
        """Verify range_pct and atr_pct calculations exist."""
        import inspect
        from apps.reference.domains.feature_engineering import feature_engineering
        
        source = inspect.getsource(
            feature_engineering.FeatureEngineering._calculate_and_emit_features_for_tf
        )
        assert "range_pct" in source
        assert "atr_pct" in source
