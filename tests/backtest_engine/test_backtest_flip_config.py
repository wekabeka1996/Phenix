"""Tests for flip orchestration config loading.

Backtest is expected to run on the same SSOT config as live (no extra overlay layer).
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
    """Tests for flip config loading is consistent across modes."""
    
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
    
    def test_backtest_mode_uses_same_flip_config_as_ssot(self, backtest_config_dir):
        """Verify backtest mode uses SSOT flip config (no overlay)."""
        # 1. Load config with config_dir pointing to backtest mode config
        loader = ConfigLoader(config_dir=backtest_config_dir)
        config = loader.load_config()
        
        # 2. Access flip config
        dm_cfg = config.domains.decision_making
        flip_cfg = dm_cfg.flip
        
        # 3. Assert expected SSOT defaults (config/aurora/domains.yaml)
        assert flip_cfg.enabled is True

        # Per-symbol flip config lives in instruments.yaml (SSOT)
        btc_flip = config.instruments["BTCUSDT"].flip
        assert btc_flip.enabled is True
        assert btc_flip.hysteresis_mult == 3.0
    
    def test_live_mode_matches_ssot_flip_config(self, live_config_dir):
        """Verify live mode uses the same SSOT flip config."""
        # 1. Load config with config_dir pointing to live mode config
        loader = ConfigLoader(config_dir=live_config_dir)
        config = loader.load_config()
        
        # 2. Access flip config
        dm_cfg = config.domains.decision_making
        flip_cfg = dm_cfg.flip
        
        assert flip_cfg.enabled is True

        btc_flip = config.instruments["BTCUSDT"].flip
        assert btc_flip.enabled is True
        assert btc_flip.hysteresis_mult == 3.0


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
        flip = SimpleNamespace(enabled=True)  # Global killswitch only
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
                    flip=SimpleNamespace(enabled=True, hysteresis_mult=2.5),
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
        
        assert dm.flip_global_enabled is True
        enabled, mult = dm._get_flip_config("BTCUSDT")
        assert enabled is True
        assert mult == 2.5
    
    def test_get_flip_config_returns_global_fallback(self, mock_bus, dm_cfg_with_flip, base_config):
        """Verify global killswitch disables flip even when per-symbol is enabled."""
        dm_cfg_with_flip.flip.enabled = False
        with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
            MockResolver.return_value.get_decision_making.return_value = dm_cfg_with_flip
            
            dm = DecisionMaking(fsm=mock_bus, config=base_config)
        
        # Get flip config for symbol (no per-symbol override)
        enabled, mult = dm._get_flip_config("BTCUSDT")
        
        assert enabled is False
        assert mult == 1.0


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
            flip=SimpleNamespace(enabled=True),
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
                    flip=SimpleNamespace(enabled=True, hysteresis_mult=2.5),
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
        
        enabled, mult = dm._get_flip_config("BTCUSDT")
        assert enabled is True
        assert mult == 2.5
        
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
        E2E: Verify backtest loads SSOT flip config (no overlay).
        
        This test:
        1. Loads AuroraConfig with trading_mode=backtest
        2. Verifies domains.decision_making.flip is the SSOT default
        """
        loader = ConfigLoader(config_dir=backtest_config_dir)
        config = loader.load_config()
        
        # Access via config object
        flip_cfg = config.domains.decision_making.flip
        
        assert flip_cfg.enabled is True

        btc_flip = config.instruments["BTCUSDT"].flip
        assert btc_flip.enabled is True
        assert btc_flip.hysteresis_mult == 3.0
        
        # Verify other backtest-specific overrides as well
        dm_cfg = config.domains.decision_making
        
        assert dm_cfg.risk_skew.max_skew_sec == 5
        
        assert dm_cfg.directional_sanity.enabled is True
        
        assert dm_cfg.price_motion_sanity.enabled is True
