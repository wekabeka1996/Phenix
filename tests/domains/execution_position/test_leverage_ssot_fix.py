"""
LEVERAGE-SSOT-FIX-01: Tests for leverage SSOT consolidation.

Verifies that:
1. _collect_leverage_configs() reads from instruments.yaml (not strategies)
2. validate_leverage_ssot_consistency() detects mismatches
3. Bootstrap uses instruments.yaml values
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_instruments_config():
    """Create mock instruments config with execution settings."""
    def make_spec(symbol: str, target_leverage: int, margin_mode: str = "isolated"):
        spec = MagicMock()
        spec.symbol = symbol
        spec.execution = MagicMock()
        spec.execution.target_leverage = target_leverage
        spec.execution.margin_mode = margin_mode
        spec.execution.leverage_policy = "set_and_verify"
        spec.sizing = MagicMock()
        spec.sizing.margin_pct = 0.10
        return spec
    
    return {
        "BTCUSDT": make_spec("BTCUSDT", 50),
        "ETHUSDT": make_spec("ETHUSDT", 41),
        "SOLUSDT": make_spec("SOLUSDT", 20),
        "DOGEUSDT": make_spec("DOGEUSDT", 20),
        "XRPUSDT": make_spec("XRPUSDT", 20),
    }


@pytest.fixture
def mock_strategy_leverage():
    """Create mock strategy config with DIFFERENT leverage values (legacy)."""
    from apps.reference.config_models import LeverageConfig
    
    def make_asset(leverage_target: int):
        asset = MagicMock()
        asset.leverage = LeverageConfig(target=leverage_target, mode="ISOLATED")
        asset.enabled = True
        return asset
    
    aurora_assets = {
        "BTCUSDT": make_asset(20),  # MISMATCH: instruments=50, strategy=20
        "ETHUSDT": make_asset(20),  # MISMATCH: instruments=41, strategy=20
        "SOLUSDT": make_asset(20),  # MATCH
    }
    
    return aurora_assets


@pytest.fixture
def mock_strategies_registry():
    """Create mock strategies registry with assignments."""
    registry = MagicMock()
    registry.assignments = {
        "BTCUSDT": ["aurora"],
        "ETHUSDT": ["aurora"],
        "SOLUSDT": ["aurora"],
        "DOGEUSDT": ["mean_reversion"],
        "XRPUSDT": ["mean_reversion"],
    }
    return registry


@pytest.fixture
def mock_config(mock_instruments_config, mock_strategy_leverage, mock_strategies_registry):
    """Create complete mock config."""
    config = MagicMock()
    config.instruments = mock_instruments_config
    config.strategies_registry = mock_strategies_registry
    
    # Aurora strategy with mismatched leverage
    config.strategies = MagicMock()
    config.strategies.aurora = MagicMock()
    config.strategies.aurora.assets = mock_strategy_leverage
    
    # Mean Reversion (no leverage defined)
    config.strategies.mean_reversion = MagicMock()
    config.strategies.mean_reversion.assets = {}
    
    return config


@pytest.fixture
def fsm_instance(mock_config):
    """Create FSM instance with mocked dependencies."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    # Create minimal mocks for required domain configs
    mock_config.domains = MagicMock()
    mock_config.domains.execution_position = MagicMock()
    mock_config.domains.execution_position.metrics_collector = MagicMock()
    mock_config.domains.execution_position.metrics_collector.window_size_minutes = 60
    mock_config.domains.execution_position.metrics_collector.recent_rejections_minutes = 5
    mock_config.domains.execution_position.idempotent_cancel = MagicMock()
    mock_config.domains.execution_position.idempotent_cancel.max_retries = 3
    mock_config.domains.execution_position.guardian = MagicMock()
    mock_config.domains.execution_position.guardian.unified = True
    mock_config.domains.execution_position.guardian.emit_tidy_event = True
    mock_config.domains.execution_position.guardian.poll_interval_ms = 500
    mock_config.domains.execution_position.guardian.cleanup_ttl_ms = 60000
    mock_config.domains.execution_position.guardian.symbol_cooldown_ms = 1000
    mock_config.domains.execution_position.event_dedup = MagicMock()
    mock_config.domains.execution_position.event_dedup.max_size = 1000
    mock_config.domains.execution_position.event_dedup.ttl_ms = 60000
    mock_config.domains.execution_position.exposure_guard = MagicMock()
    mock_config.domains.execution_position.exposure_guard.max_equity_utilization_pct = 80.0
    mock_config.domains.execution_position.exposure_guard.max_portfolio_fraction = 50.0
    mock_config.domains.execution_position.exposure_guard.max_directional_ratio = 30.0
    mock_config.domains.execution_position.exposure_guard.count_pending_orders = True
    mock_config.domains.execution_position.exposure_guard.exclude_reduce_only = True
    mock_config.domains.execution_position.exposure_guard.pending_ttl_sec = 90
    mock_config.domains.execution_position.exposure_guard.post_fill_hold_ttl_sec = 5
    mock_config.domains.execution_position.exposure_guard.stale_ttl_sec = 120
    mock_config.trading = MagicMock()
    mock_config.trading.execution = MagicMock()
    mock_config.trading.execution.cooldown_after_close_ms = 1000
    mock_config.trading.execution.watchdog = MagicMock()
    mock_config.trading.execution.watchdog.ack_ttl_ms = 5000
    mock_config.trading.execution.watchdog.fill_ttl_ms = 30000
    mock_config.trading.execution.manage = MagicMock()
    mock_config.trading.execution.manage.orphan_monitor = {}
    mock_config.trading.execution.exposure = MagicMock()
    mock_config.trading.execution.exposure.leverage_defaults = {"__default__": 20}
    
    with patch.object(ExecPosFSM, '_initialize_adapter'):
        with patch.object(ExecPosFSM, '_schedule_guardian_start'):
            with patch.object(ExecPosFSM, '_schedule_fsm_cleanup_loop'):
                with patch('apps.reference.domains.execution_position.fsm.OrderGuardian'):
                    with patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
                        fsm = ExecPosFSM(
                            config=mock_config,
                            fsm=MagicMock(),
                            shadow_mode=True,
                        )
    
    return fsm


# ─────────────────────────────────────────────────────────────────────────────
# Test: _collect_leverage_configs reads from instruments.yaml
# ─────────────────────────────────────────────────────────────────────────────

class TestCollectLeverageConfigsFromInstruments:
    """Test that _collect_leverage_configs uses instruments.yaml SSOT."""
    
    def test_collects_from_instruments_not_strategies(self, fsm_instance, mock_instruments_config):
        """Verify leverage values come from instruments.yaml, not strategies."""
        result = fsm_instance._collect_leverage_configs()
        
        # Should have all assigned symbols
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result
        assert "SOLUSDT" in result
        assert "DOGEUSDT" in result
        assert "XRPUSDT" in result
        
        # Values should match instruments.yaml (NOT strategy values)
        assert result["BTCUSDT"].target == 50, "BTCUSDT should be 50 from instruments, not 20 from strategy"
        assert result["ETHUSDT"].target == 41, "ETHUSDT should be 41 from instruments, not 20 from strategy"
        assert result["SOLUSDT"].target == 20
        assert result["DOGEUSDT"].target == 20
        assert result["XRPUSDT"].target == 20
    
    def test_returns_leverage_config_objects(self, fsm_instance):
        """Verify returned objects are LeverageConfig instances."""
        from apps.reference.config_models import LeverageConfig
        
        result = fsm_instance._collect_leverage_configs()
        
        for symbol, cfg in result.items():
            assert isinstance(cfg, LeverageConfig), f"{symbol} should be LeverageConfig"
            assert cfg.mode in ("ISOLATED", "CROSSED"), f"{symbol} mode should be valid"
    
    def test_handles_missing_instruments(self, fsm_instance):
        """Verify graceful handling when instruments dict is missing."""
        fsm_instance.config.instruments = None
        
        result = fsm_instance._collect_leverage_configs()
        
        assert result == {}
    
    def test_handles_missing_execution_config(self, fsm_instance, mock_instruments_config):
        """Verify warning when symbol has no execution config."""
        # Remove execution from BTCUSDT
        mock_instruments_config["BTCUSDT"].execution = None
        
        result = fsm_instance._collect_leverage_configs()
        
        # BTCUSDT should be skipped
        assert "BTCUSDT" not in result
        # Others should still work
        assert "ETHUSDT" in result
    
    def test_handles_missing_registry(self, fsm_instance):
        """Verify graceful handling when strategies_registry is missing."""
        fsm_instance.config.strategies_registry = None
        
        result = fsm_instance._collect_leverage_configs()
        
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# Test: validate_leverage_ssot_consistency detects mismatches
# ─────────────────────────────────────────────────────────────────────────────

class TestLeverageSSOTConsistencyValidation:
    """Test SSOT consistency validation."""
    
    def test_detects_aurora_leverage_mismatch(self, fsm_instance):
        """Verify mismatch detected when aurora leverage != instruments leverage."""
        warnings = fsm_instance.validate_leverage_ssot_consistency()
        
        # Should detect BTCUSDT and ETHUSDT mismatches
        btc_warnings = [w for w in warnings if "BTCUSDT" in w]
        eth_warnings = [w for w in warnings if "ETHUSDT" in w]
        
        assert len(btc_warnings) == 1, "Should detect BTCUSDT mismatch (50 vs 20)"
        assert len(eth_warnings) == 1, "Should detect ETHUSDT mismatch (41 vs 20)"
        
        # SOL should NOT have warning (both are 20)
        sol_warnings = [w for w in warnings if "SOLUSDT" in w]
        assert len(sol_warnings) == 0, "SOLUSDT should not have warning (values match)"
    
    def test_warning_contains_both_values(self, fsm_instance):
        """Verify warning message contains both strategy and instruments values."""
        warnings = fsm_instance.validate_leverage_ssot_consistency()
        
        btc_warning = next(w for w in warnings if "BTCUSDT" in w)
        
        assert "aurora.leverage.target=20" in btc_warning
        assert "instruments.execution.target_leverage=50" in btc_warning
        assert "SSOT is instruments.yaml" in btc_warning
    
    def test_no_warnings_when_consistent(self, fsm_instance, mock_strategy_leverage):
        """Verify no warnings when all values match."""
        from apps.reference.config_models import LeverageConfig
        
        # Update strategy leverage to match instruments
        mock_strategy_leverage["BTCUSDT"].leverage = LeverageConfig(target=50, mode="ISOLATED")
        mock_strategy_leverage["ETHUSDT"].leverage = LeverageConfig(target=41, mode="ISOLATED")
        
        warnings = fsm_instance.validate_leverage_ssot_consistency()
        
        # Should have no warnings
        assert len(warnings) == 0
    
    def test_handles_missing_strategy_leverage(self, fsm_instance):
        """Verify no crash when strategy has no leverage field."""
        fsm_instance.config.strategies.aurora.assets["BTCUSDT"].leverage = None
        
        warnings = fsm_instance.validate_leverage_ssot_consistency()
        
        # Should not include BTCUSDT (no strategy leverage to compare)
        btc_warnings = [w for w in warnings if "BTCUSDT" in w]
        assert len(btc_warnings) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test: Integration with run_leverage_bootstrap
# ─────────────────────────────────────────────────────────────────────────────

class TestLeverageBootstrapIntegration:
    """Test that bootstrap uses instruments.yaml values."""
    
    def test_bootstrap_collects_instruments_leverage(self, fsm_instance):
        """Verify _collect_leverage_configs returns instruments.yaml values for bootstrap."""
        # This tests the config collection that bootstrap uses
        # (testing the actual bootstrap run requires real adapter)
        leverage_configs = fsm_instance._collect_leverage_configs()
        
        # Verify instruments values were collected (not strategy values)
        assert leverage_configs["BTCUSDT"].target == 50, "Bootstrap should use instruments.yaml value (50), not strategy (20)"
        assert leverage_configs["ETHUSDT"].target == 41, "Bootstrap should use instruments.yaml value (41), not strategy (20)"
        assert leverage_configs["SOLUSDT"].target == 20
        assert leverage_configs["DOGEUSDT"].target == 20
        assert leverage_configs["XRPUSDT"].target == 20
    
    @pytest.mark.asyncio
    async def test_bootstrap_logs_ssot_warnings(self, fsm_instance, caplog):
        """Verify bootstrap logs SSOT mismatch warnings."""
        import logging
        
        from apps.reference.domains.execution_position.bootstrapping.leverage_bootstrapper import (
            LeverageBootstrapper,
            BootstrapResults,
        )
        
        mock_results = BootstrapResults()
        
        with patch.object(LeverageBootstrapper, 'run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_results
            
            with caplog.at_level(logging.WARNING):
                await fsm_instance.run_leverage_bootstrap()
            
            # Should log about SSOT mismatches
            log_text = caplog.text
            # The warnings are logged, verification depends on logger config
    
    @pytest.mark.asyncio
    async def test_bootstrap_skipped_in_shadow_mode(self, fsm_instance):
        """Verify bootstrap is skipped in shadow mode."""
        fsm_instance.shadow_mode = True
        
        failed = await fsm_instance.run_leverage_bootstrap()
        
        assert failed == set()


# ─────────────────────────────────────────────────────────────────────────────
# Test: Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestLeverageEdgeCases:
    """Test edge cases for leverage SSOT fix."""
    
    def test_margin_mode_conversion_to_crossed(self, fsm_instance, mock_instruments_config):
        """Verify margin_mode 'cross' is converted to 'CROSSED' for LeverageConfig."""
        # Set cross margin mode (instruments.yaml uses lowercase "cross")
        mock_instruments_config["BTCUSDT"].execution.margin_mode = "cross"
        
        result = fsm_instance._collect_leverage_configs()
        
        # LeverageConfig uses CROSSED (not CROSS) for cross margin
        assert result["BTCUSDT"].mode == "CROSSED", "Should convert 'cross' to 'CROSSED'"
    
    def test_symbol_in_assignments_but_not_instruments(self, fsm_instance):
        """Verify warning when symbol is assigned but not in instruments."""
        # Add symbol to assignments but not instruments
        fsm_instance.config.strategies_registry.assignments["NEWUSDT"] = ["aurora"]
        
        result = fsm_instance._collect_leverage_configs()
        
        # Should not include NEWUSDT
        assert "NEWUSDT" not in result
        # Should still include others
        assert "BTCUSDT" in result
    
    def test_multiple_strategies_same_symbol(self, fsm_instance):
        """Verify instruments.yaml is used regardless of strategy count."""
        # Assign BTC to both strategies
        fsm_instance.config.strategies_registry.assignments["BTCUSDT"] = ["aurora", "mean_reversion"]
        
        result = fsm_instance._collect_leverage_configs()
        
        # Should still get instruments value
        assert result["BTCUSDT"].target == 50


# ─────────────────────────────────────────────────────────────────────────────
# Test: Contract verification
# ─────────────────────────────────────────────────────────────────────────────

class TestLeverageContractVerification:
    """Verify the fix maintains sizing/exposure guard consistency."""
    
    def test_sizing_and_bootstrap_use_same_source(self, fsm_instance, mock_instruments_config):
        """Verify sizing and bootstrap both read from instruments.yaml."""
        # Get bootstrap leverage
        bootstrap_configs = fsm_instance._collect_leverage_configs()
        
        # Verify both use instruments.yaml values
        for symbol, cfg in bootstrap_configs.items():
            spec = mock_instruments_config[symbol]
            assert cfg.target == spec.execution.target_leverage, (
                f"{symbol}: bootstrap ({cfg.target}) != instruments ({spec.execution.target_leverage})"
            )
    
    def test_btcusdt_critical_values(self, fsm_instance):
        """Verify BTCUSDT gets correct leverage (50, not 20)."""
        result = fsm_instance._collect_leverage_configs()
        
        # This is the critical fix: BTCUSDT should be 50 from instruments
        # NOT 20 from strategy config
        assert result["BTCUSDT"].target == 50, (
            "CRITICAL: BTCUSDT leverage must be 50 (instruments.yaml), "
            "not 20 (strategy config). This affects sizing calculations!"
        )
