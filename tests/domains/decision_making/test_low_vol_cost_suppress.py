"""
Tests for LOW_VOL_COST_SUPPRESS gate.

LOW_VOL_COST_SUPPRESS-IMPLEMENT-004:
- Block TREND entries when rv_bps < factor * cost_bps
- Allow reduce-only (close) orders
- Allow non-TREND regimes
- Fallback to default_cost_bps when spread/fees not available

VERIFY-005 HARDENING:
- volatility_state proxy disabled by default
- BPS sanity guard (> 200 = garbage)
- Telemetry counters
"""

import time
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []
        self._listeners: dict[str, list] = {}

    def emit(self, event_name: str, payload=None, why=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}, why))

    def listen(self, event_name: str, callback) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)


@pytest.fixture
def mock_config():
    """Create a minimal mock config for testing."""
    from apps.reference.config_loader import ConfigLoader
    return ConfigLoader().load_config()


@pytest.fixture
def decision_making(mock_config):
    """Create DecisionMaking instance with mock FSM."""
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    
    fsm = _DummyFsm()
    dm = DecisionMaking(fsm=fsm, config=mock_config)
    return dm


class TestLowVolCostSuppressGate:
    """Tests for _check_low_vol_cost_suppress_gate method."""
    
    def test_gate_disabled_passes(self, decision_making):
        """When gate is disabled, all trades should pass."""
        decision_making._low_vol_cost_suppress_enabled = False
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features={"rv_bps": 1.0},  # Very low vol
            reduce_only=False,
        )
        
        assert should_block is False
        assert details["result"] == "PASS:disabled"
    
    def test_blocks_trend_entry_when_rv_too_low(self, decision_making):
        """
        Test 1: Block TREND entry when rv_bps < factor * cost_bps.
        
        Setup:
        - regime=TREND_UP
        - rv_bps=3.0 (explicit from features)
        - cost_bps=4.0 (default)
        - factor=1.5
        - threshold=6.0
        
        Expected: 3.0 < 6.0 → BLOCK
        """
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        decision_making._low_vol_cost_suppress_allow_rv_proxy = False  # VERIFY-005
        
        # Explicit rv_bps
        features = {"rv_bps": 3.0, "spread_bps": 0}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        assert should_block is True
        assert details["result"] == "BLOCK"
        assert details["rv_bps"] == 3.0
        assert details["cost_bps"] == 4.0  # default
        assert details["threshold"] == 6.0  # 1.5 * 4.0
    
    def test_allows_when_rv_sufficient(self, decision_making):
        """
        Test 2: Allow when rv_bps >= factor * cost_bps.
        
        Setup:
        - rv_bps=6.0 (explicit)
        - cost_bps=3.0 (computed from spread)
        - factor=1.5
        - threshold=4.5
        
        Expected: 6.0 >= 4.5 → PASS
        """
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        decision_making._low_vol_cost_suppress_allow_rv_proxy = False  # VERIFY-005
        
        # Explicit rv_bps + spread
        features = {"rv_bps": 6.0, "spread_bps": 3.0}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        assert should_block is False
        assert details["result"] == "PASS"
        assert details["rv_bps"] == 6.0
        assert details["cost_bps"] == 3.0  # from spread
        assert details["threshold"] == 4.5  # 1.5 * 3.0
    
    def test_reduce_only_not_blocked(self, decision_making):
        """
        Test 3: Reduce-only orders bypass the gate.
        """
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        decision_making._low_vol_cost_suppress_allow_reduce_only = True
        
        # Very low volatility that would normally block
        features = {"rv_bps": 1.0}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=True,  # Close order
        )
        
        assert should_block is False
        assert details["result"] == "PASS:reduce_only"
    
    def test_fallback_to_default_cost(self, decision_making):
        """
        Test 4: When spread/fees not available, use default_cost_bps.
        """
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 5.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        decision_making._low_vol_cost_suppress_allow_rv_proxy = False
        
        # Explicit rv_bps, no spread in features
        features = {"rv_bps": 3.0}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_DOWN",
            features=features,
            reduce_only=False,
        )
        
        # rv_bps=3.0 < 1.5 * 5.0=7.5 → BLOCK
        assert should_block is True
        assert details["cost_bps"] == 5.0  # default
        assert details["cost_source"] == "default"
        assert details["threshold"] == 7.5
    
    def test_non_trend_regime_passes(self, decision_making):
        """Non-TREND regimes should always pass."""
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        
        # Very low vol that would block TREND
        features = {"rv_bps": 1.0}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="MEAN_REVERSION",
            features=features,
            reduce_only=False,
        )
        
        assert should_block is False
        assert "PASS:regime_not_covered" in details["result"]
    
    def test_rv_bps_missing_passes_and_increments_counter(self, decision_making):
        """
        When rv_bps cannot be determined, don't block (fail-open for data gaps).
        VERIFY-005: Also verify counter is incremented.
        """
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        decision_making._low_vol_cost_suppress_allow_rv_proxy = False  # No proxy
        
        # No volatility data (and proxy disabled)
        features = {"spread_bps": 2.0}  # Only spread, no rv
        
        initial_missing_count = decision_making._low_vol_cost_suppress_stats["rv_bps_missing"]
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        assert should_block is False
        assert details["result"] == "PASS:rv_bps_missing"
        assert details["rv_bps_source"] == "missing"
        # VERIFY-005: Counter incremented
        assert decision_making._low_vol_cost_suppress_stats["rv_bps_missing"] == initial_missing_count + 1


class TestLowVolCostSuppressProxyHardening:
    """VERIFY-005: Tests for proxy disabling and sanity guards."""
    
    def test_proxy_disabled_by_default(self, decision_making):
        """volatility_state proxy should be disabled by default."""
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_allow_rv_proxy = False  # Default
        
        # volatility_state present, but no rv_bps
        features = {"volatility_state": 0.5, "spread_bps": 2.0}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        # Should NOT use proxy → rv_bps missing → PASS
        assert should_block is False
        assert details["result"] == "PASS:rv_bps_missing"
    
    def test_proxy_works_when_enabled(self, decision_making):
        """When proxy is explicitly enabled, it should work."""
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_allow_rv_proxy = True  # Explicitly enabled
        decision_making._low_vol_cost_suppress_rv_proxy_scale = 10.0
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP"}
        
        # volatility_state=0.3 → rv_bps=3.0
        features = {"volatility_state": 0.3}
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        # Should use proxy: 3.0 < 6.0 → BLOCK
        assert should_block is True
        assert details["rv_bps"] == 3.0
        assert "volatility_state" in details["rv_bps_source"]
    
    def test_bps_sanity_guard_rejects_garbage(self, decision_making):
        """Values > bps_sanity_max should be treated as garbage and trigger fallback."""
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_bps_sanity_max = 200.0
        decision_making._low_vol_cost_suppress_factor = 1.5
        decision_making._low_vol_cost_suppress_default_cost_bps = 4.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP"}
        
        # Garbage spread (> 200 bps = obviously wrong)
        features = {"rv_bps": 5.0, "spread_bps": 500.0}  # 500 bps is garbage
        
        initial_fallback_count = decision_making._low_vol_cost_suppress_stats["bps_sanity_fallback"]
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        # Garbage spread should be zeroed out, default cost used
        assert details["sanity_fallback_used"] is True
        assert details["spread_bps"] == 0.0  # Garbage was zeroed
        assert details["cost_bps"] == 4.0  # Default fallback
        # Counter incremented
        assert decision_making._low_vol_cost_suppress_stats["bps_sanity_fallback"] == initial_fallback_count + 1


class TestLowVolCostSuppressConfig:
    """Tests for configuration loading."""
    
    def test_config_loads_from_domains_yaml(self, mock_config):
        """Verify config is parsed correctly from domains.yaml."""
        dm_cfg = mock_config.domains.decision_making
        lvcs_cfg = dm_cfg.low_vol_cost_suppress
        
        assert lvcs_cfg.enabled is True  # We enabled it in domains.yaml
        assert lvcs_cfg.factor == 1.5
        assert lvcs_cfg.default_cost_bps == 4.0
        assert "TREND_UP" in lvcs_cfg.apply_to_regimes
        assert "TREND_DOWN" in lvcs_cfg.apply_to_regimes
        assert lvcs_cfg.allow_reduce_only is True
        # VERIFY-005 fields
        assert lvcs_cfg.allow_rv_proxy_from_volatility_state is False  # Disabled by default
        assert lvcs_cfg.bps_sanity_max == 200.0
    
    def test_pydantic_validation_forbids_extra_keys(self):
        """Extra keys in config should raise ValidationError."""
        from pydantic import ValidationError
        from apps.reference.config_models import LowVolCostSuppressConfig
        
        with pytest.raises(ValidationError):
            LowVolCostSuppressConfig(
                enabled=True,
                factor=1.5,
                default_cost_bps=4.0,
                unknown_key="should_fail",  # Extra key
            )
    
    def test_factor_bounds_validation(self):
        """Factor must be > 0 and <= 10."""
        from pydantic import ValidationError
        from apps.reference.config_models import LowVolCostSuppressConfig
        
        # Too low
        with pytest.raises(ValidationError):
            LowVolCostSuppressConfig(enabled=True, factor=0.0)
        
        # Too high
        with pytest.raises(ValidationError):
            LowVolCostSuppressConfig(enabled=True, factor=15.0)


class TestLowVolCostSuppressTelemetry:
    """VERIFY-005: Test telemetry counters."""
    
    def test_block_increments_counter(self, decision_making):
        """BLOCK should increment blocks counter."""
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 2.0
        decision_making._low_vol_cost_suppress_default_cost_bps = 5.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP", "TREND_DOWN"}
        
        features = {"rv_bps": 2.0}  # rv_bps=2.0 < 2.0*5.0=10.0
        
        initial_blocks = decision_making._low_vol_cost_suppress_stats["blocks"]
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="ETHUSDT",
            regime="TREND_DOWN",
            features=features,
            reduce_only=False,
        )
        
        assert should_block is True
        assert decision_making._low_vol_cost_suppress_stats["blocks"] == initial_blocks + 1
    
    def test_pass_increments_counter(self, decision_making):
        """PASS should increment passes counter."""
        decision_making._low_vol_cost_suppress_enabled = True
        decision_making._low_vol_cost_suppress_factor = 1.0
        decision_making._low_vol_cost_suppress_default_cost_bps = 2.0
        decision_making._low_vol_cost_suppress_regimes = {"TREND_UP"}
        
        features = {"rv_bps": 10.0}  # rv_bps=10.0 >= 1.0*2.0=2.0
        
        initial_passes = decision_making._low_vol_cost_suppress_stats["passes"]
        
        should_block, details = decision_making._check_low_vol_cost_suppress_gate(
            symbol="BTCUSDT",
            regime="TREND_UP",
            features=features,
            reduce_only=False,
        )
        
        assert should_block is False
        assert details["result"] == "PASS"
        assert decision_making._low_vol_cost_suppress_stats["passes"] == initial_passes + 1
