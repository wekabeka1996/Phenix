"""
Tests for flip orchestration config loading in backtest mode.

Verifies that:
1. backtest_override.yaml flip config is correctly merged
2. DecisionMaking receives flip.hysteresis_mult = 1.5 from overlay
3. Flip logic respects backtest config values
"""
from __future__ import annotations

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class TestBacktestFlipConfigLoading:
    """Tests for flip config loading via backtest_override.yaml."""
    
    @pytest.fixture
    def backtest_config_dir(self, tmp_path):
        """Create temporary config dir with backtest mode enabled."""
        # Copy entire real config tree to temp directory (including strategies/)
        real_config = Path(__file__).resolve().parents[2] / "config" / "aurora"
        shutil.copytree(real_config, tmp_path, dirs_exist_ok=True)
        
        # Modify trading.yaml to set mode=backtest
        trading_yaml = tmp_path / "trading.yaml"
        content = trading_yaml.read_text()
        content = content.replace("mode: testnet", "mode: backtest")
        content = content.replace("mode: production", "mode: backtest")
        trading_yaml.write_text(content)
        
        return tmp_path
    
    @pytest.fixture
    def live_config_dir(self, tmp_path):
        """Create temporary config dir with live (testnet) mode."""
        real_config = Path(__file__).resolve().parents[2] / "config" / "aurora"
        shutil.copytree(real_config, tmp_path, dirs_exist_ok=True)
        
        # Force mode=testnet in trading.yaml
        import re
        trading_yaml = tmp_path / "trading.yaml"
        content = trading_yaml.read_text()
        content = re.sub(r'mode:\s*backtest', 'mode: testnet', content, flags=re.IGNORECASE)
        trading_yaml.write_text(content)
        
        # Force trading_mode=testnet in system.yaml (root level mode)
        system_yaml = tmp_path / "system.yaml"
        content = system_yaml.read_text()
        content = re.sub(r'trading_mode:\s*["\']?backtest["\']?', 'trading_mode: testnet', content, flags=re.IGNORECASE)
        system_yaml.write_text(content)
        
        return tmp_path
    
    def test_config_loader_merges_flip_from_backtest_overlay(self, backtest_config_dir):
        """Verify ConfigLoader deep-merges flip config from backtest_override.yaml."""
        # 1. Load config with config_dir pointing to backtest mode config
        loader = ConfigLoader(config_dir=backtest_config_dir)
        config = loader.load_config()
        
        # 2. Access flip config
        dm_cfg = config.domains.decision_making
        flip_cfg = dm_cfg.flip
        
        # 3. Assert backtest overlay values (from backtest_override.yaml)
        # flip:
        #   enabled: true
        #   hysteresis_mult: 1.5
        assert flip_cfg.enabled is True, "flip.enabled should be True from backtest_override.yaml"
        assert flip_cfg.hysteresis_mult == 1.5, (
            f"flip.hysteresis_mult should be 1.5 from backtest_override.yaml, got {flip_cfg.hysteresis_mult}"
        )
    
    def test_live_mode_has_different_flip_config(self, live_config_dir):
        """Verify live mode does NOT get backtest overlay flip values."""
        # 1. Load config with config_dir pointing to live mode config
        loader = ConfigLoader(config_dir=live_config_dir)
        config = loader.load_config()
        
        # 2. Access flip config
        dm_cfg = config.domains.decision_making
        flip_cfg = dm_cfg.flip
        
        # 3. Live mode should have base config, NOT backtest overlay
        # Base domains.yaml has hysteresis_mult = 1.3 (default)
        # This test confirms backtest overlay is NOT applied in live mode
        assert flip_cfg.hysteresis_mult != 1.5 or flip_cfg.hysteresis_mult == 1.3, (
            "Live mode should not have backtest overlay flip.hysteresis_mult=1.5"
        )


class TestDecisionMakingFlipInit:
    """Tests for DecisionMaking flip initialization from config."""
    
    @pytest.fixture
    def mock_bus(self):
        """Create mock FSM bus."""
        bus = MagicMock()
        bus.listen = MagicMock()
        bus.emit = MagicMock()
        return bus
    
    @pytest.fixture
    def dm_cfg_with_flip(self):
        """Create decision_making config with flip settings."""
        qos = SimpleNamespace(
            exposure_block_cooldown_sec=0,
            max_intents_per_minute_per_symbol=1000,
            mode="shadow",
            symbol_cooldown_sec=0,
            enforce=False,
        )
        flip = SimpleNamespace(enabled=True, hysteresis_mult=2.5)  # Backtest value
        return SimpleNamespace(
            qos=qos,
            position_sizing=SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000),
            arming=SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1),
            features=SimpleNamespace(ttl_sec=60),
            bar_gating=SimpleNamespace(enable=False, bar_ms=60_000),
            behavior_fsm=SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5),
            flip=flip,
            risk_skew=SimpleNamespace(
                max_skew_sec=999999,  # Backtest value
                max_defer_count=3,
                defer_cooldown_sec=2,
                defer_window_sec=60,
                until_refresh_retry_sec=30,
            ),
            risk_gate=SimpleNamespace(
                threshold_pct_testnet=20.0,
                threshold_pct_production=50.0,
                min_intents_for_check=10,
            ),
        )
    
    @pytest.fixture
    def base_config(self):
        """Create minimal config for DecisionMaking."""
        return SimpleNamespace(
            trading=SimpleNamespace(
                tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": "neutral"},
                risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200},
                mode="testnet",
            ),
            domains=SimpleNamespace(
                position_tracking=SimpleNamespace(positions_stale_ttl_sec=15),
                decision_making=SimpleNamespace(
                    directional_sanity=SimpleNamespace(enabled=False, min_abs_delta_price=0.0, min_confidence=0.0, consecutive_bars=2),
                    price_motion_sanity=SimpleNamespace(enabled=False, k_vol=2.0, flash_window_sec=10, bleed_window_sec=300, flash_threshold_norm=1.0, bleed_threshold_norm=0.7, require_bleed_ready=True),
                ),
            ),
            instruments={
                "BTCUSDT": SimpleNamespace(
                    tick_size="0.1",
                    step_size="0.001",
                    min_qty="0.001",
                    min_notional="5",
                    execution=SimpleNamespace(margin_mode="isolated", target_leverage=20, leverage_policy="verify_only", max_notional_utilization=0.8),
                    sizing=SimpleNamespace(margin_pct=0.02),
                )
            },
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    decision=SimpleNamespace(
                        signal_threshold=0.0,
                        retry_ttl_ms=1000,
                        retry_max_count=1,
                        retry_backoff_factor=1.0,
                        side_bias_penalty_factor=0.5,
                        side_bias_window_sec=60,
                        side_bias_target_ratio=0.6,
                        kelly=None,
                    ),
                    assets={"BTCUSDT": SimpleNamespace(position_mode="STRICT")},
                )
            ),
            strategies_registry=None,
        )
    
    def test_decision_making_receives_flip_mult_3(self, mock_bus, dm_cfg_with_flip, base_config):
        """Verify DecisionMaking stores flip.hysteresis_mult=2.5 from backtest config."""
        with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
            MockResolver.return_value.get_decision_making.return_value = dm_cfg_with_flip
            
            dm = DecisionMaking(fsm=mock_bus, config=base_config)
        
        # Verify flip settings were loaded correctly
        assert dm.flip_hysteresis_enabled is True
        assert dm.flip_hysteresis_mult == 2.5, (
            f"DecisionMaking.flip_hysteresis_mult should be 2.5, got {dm.flip_hysteresis_mult}"
        )
    
    def test_get_flip_config_returns_global_fallback(self, mock_bus, dm_cfg_with_flip, base_config):
        """Verify _get_flip_config returns global settings when no per-symbol override."""
        with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
            MockResolver.return_value.get_decision_making.return_value = dm_cfg_with_flip
            
            dm = DecisionMaking(fsm=mock_bus, config=base_config)
        
        # Get flip config for symbol (no per-symbol override)
        enabled, mult = dm._get_flip_config("BTCUSDT")
        
        assert enabled is True
        assert mult == 2.5


class TestFlipHysteresisEffect:
    """Tests for flip hysteresis behavior with backtest config."""
    
    @pytest.fixture
    def mock_bus_with_emit(self):
        """Create mock FSM bus that tracks emits."""
        bus = MagicMock()
        bus.emits = []
        
        def capture_emit(event_name, payload=None, why=None, data_ref=None):
            bus.emits.append((event_name, payload, why, data_ref))
        
        bus.emit = capture_emit
        bus.listen = MagicMock()
        return bus
    
    def test_flip_hysteresis_uses_configured_mult(self, mock_bus_with_emit):
        """Verify flip hysteresis calculation uses configured mult."""
        # Setup config with mult=2.5
        qos = SimpleNamespace(
            exposure_block_cooldown_sec=0,
            max_intents_per_minute_per_symbol=1000,
            mode="shadow",
            symbol_cooldown_sec=0,
            enforce=False,
        )
        dm_cfg = SimpleNamespace(
            qos=qos,
            position_sizing=SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000),
            arming=SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1),
            features=SimpleNamespace(ttl_sec=60),
            bar_gating=SimpleNamespace(enable=False, bar_ms=60_000),
            behavior_fsm=SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5),
            flip=SimpleNamespace(enabled=True, hysteresis_mult=2.5),
            risk_skew=SimpleNamespace(
                max_skew_sec=999999,
                max_defer_count=3,
                defer_cooldown_sec=2,
                defer_window_sec=60,
                until_refresh_retry_sec=30,
            ),
            risk_gate=SimpleNamespace(
                threshold_pct_testnet=20.0,
                threshold_pct_production=50.0,
                min_intents_for_check=10,
            ),
        )
        
        config = SimpleNamespace(
            trading=SimpleNamespace(
                tca_prefs={"max_slippage_bps": 10},
                risk_budgets={"trade_cvar95_max_bps": 100},
                mode="testnet",
            ),
            domains=SimpleNamespace(
                position_tracking=SimpleNamespace(positions_stale_ttl_sec=15),
                decision_making=SimpleNamespace(
                    directional_sanity=SimpleNamespace(enabled=False, min_abs_delta_price=0.0, min_confidence=0.0, consecutive_bars=2),
                    price_motion_sanity=SimpleNamespace(enabled=False, k_vol=2.0, flash_window_sec=10, bleed_window_sec=300, flash_threshold_norm=1.0, bleed_threshold_norm=0.7, require_bleed_ready=True),
                ),
            ),
            instruments={
                "BTCUSDT": SimpleNamespace(
                    tick_size="0.1",
                    step_size="0.001",
                    min_qty="0.001",
                    min_notional="5",
                    execution=SimpleNamespace(margin_mode="isolated", target_leverage=20, leverage_policy="verify_only", max_notional_utilization=0.8),
                    sizing=SimpleNamespace(margin_pct=0.02),
                )
            },
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    decision=SimpleNamespace(
                        signal_threshold=0.0,
                        retry_ttl_ms=1000,
                        retry_max_count=1,
                        retry_backoff_factor=1.0,
                        side_bias_penalty_factor=0.5,
                        side_bias_window_sec=60,
                        side_bias_target_ratio=0.6,
                        kelly=None,
                    ),
                    assets={"BTCUSDT": SimpleNamespace(position_mode="STRICT")},
                )
            ),
            strategies_registry=None,
        )
        
        with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
            MockResolver.return_value.get_decision_making.return_value = dm_cfg
            dm = DecisionMaking(fsm=mock_bus_with_emit, config=config)
        
        # Verify mult=2.5 is stored
        assert dm.flip_hysteresis_mult == 2.5
        
        # The hysteresis mult affects the minimum time between flips
        # A higher mult means longer cooldown between direction changes
        # This reduces churn in backtest (intended behavior)


class TestBacktestFlipE2E:
    """End-to-end tests for flip in backtest mode."""
    
    @pytest.fixture
    def backtest_config_dir(self, tmp_path):
        """Create temporary config dir with backtest mode enabled."""
        real_config = Path(__file__).resolve().parents[2] / "config" / "aurora"
        shutil.copytree(real_config, tmp_path, dirs_exist_ok=True)
        
        # Modify trading.yaml to set mode=backtest
        trading_yaml = tmp_path / "trading.yaml"
        content = trading_yaml.read_text()
        content = content.replace("mode: testnet", "mode: backtest")
        content = content.replace("mode: production", "mode: backtest")
        trading_yaml.write_text(content)
        
        return tmp_path
    
    @pytest.mark.slow
    def test_full_backtest_loads_flip_config(self, backtest_config_dir):
        """
        E2E: Verify full backtest simulation loads flip.hysteresis_mult=2.5.
        
        This test:
        1. Loads AuroraConfig with trading_mode=backtest
        2. Verifies domains.decision_making.flip.hysteresis_mult = 2.5
        """
        loader = ConfigLoader(config_dir=backtest_config_dir)
        config = loader.load_config()
        
        # Access via config object
        flip_cfg = config.domains.decision_making.flip
        
        assert flip_cfg.enabled is True, "Backtest should have flip.enabled=True"
        assert flip_cfg.hysteresis_mult == 2.5, (
            f"Backtest flip.hysteresis_mult should be 2.5 from overlay, got {flip_cfg.hysteresis_mult}"
        )
        
        # Verify other backtest-specific overrides as well
        dm_cfg = config.domains.decision_making
        
        # risk_skew.max_skew_sec should be 999999 (disabled for historical data)
        assert dm_cfg.risk_skew.max_skew_sec == 999999, (
            f"Backtest risk_skew.max_skew_sec should be 999999, got {dm_cfg.risk_skew.max_skew_sec}"
        )
        
        # directional_sanity.enabled should be False
        assert dm_cfg.directional_sanity.enabled is False, (
            "Backtest directional_sanity.enabled should be False"
        )
        
        # price_motion_sanity.enabled should be False
        assert dm_cfg.price_motion_sanity.enabled is False, (
            "Backtest price_motion_sanity.enabled should be False"
        )
