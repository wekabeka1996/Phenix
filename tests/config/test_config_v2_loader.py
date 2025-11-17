#!/usr/bin/env python3
"""Tests for config v2 loader functionality."""

from decimal import Decimal
import os

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from apps.reference.config_loader import ConfigLoader, AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.domains.execution_position.manage_config import resolve_execution_manage_config
from apps.reference.domains.execution_position.manage_config import clear_manage_config_cache
from apps.reference.config_risk import resolve_daily_risk_state


class TestConfigV2LoaderBasic:
    """Test config v2 loading functionality."""

    def test_config_v2_creation_without_files(self):
        """Test that ConfigV2 is created even when no v2 files exist."""
        with patch.object(ConfigLoader, '_load_config_v2', return_value=ConfigV2()):
            loader = ConfigLoader()
            config = loader.load_config()

        assert config.config_v2 is not None
        assert isinstance(config.config_v2, ConfigV2)
        assert not config.has_config_v2()

        # Check default structure
        assert config.config_v2.core is None
        assert config.config_v2.symbols is None
        assert config.config_v2.instruments is None
        assert config.config_v2.domains == {}
        assert config.config_v2.overrides is None
        assert config.config_v2.modes is None

    def test_config_v2_loading_with_test_files(self):
        """Test loading config v2 with temporary test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test config v2 files
            (temp_path / "core.yaml").write_text("core_key: core_value\n")
            (temp_path / "instruments.yaml").write_text("BTCUSDT:\n  symbol: BTCUSDT\n")
            (temp_path / "domains").mkdir()
            (temp_path / "domains" /
             "execution.yaml").write_text("manage:\n  auto: true\n")

            # Mock the config v2 root path
            with patch.object(ConfigLoader, '_load_config_v2') as mock_load:
                mock_config_v2 = ConfigV2()
                mock_config_v2.core = {"core_key": "core_value"}
                mock_config_v2.instruments = {"BTCUSDT": {"symbol": "BTCUSDT"}}
                mock_config_v2.domains = {
                    "execution": {"manage": {"auto": True}}}
                mock_load.return_value = mock_config_v2

                loader = ConfigLoader()
                config = loader.load_config()

                assert config.config_v2 is not None
                assert config.has_config_v2()

                # Check loaded data
                assert config.config_v2.core == {"core_key": "core_value"}
                assert config.config_v2.instruments == {
                    "BTCUSDT": {"symbol": "BTCUSDT"}}
                assert config.config_v2.domains["execution"] == {
                    "manage": {"auto": True}}

    def test_config_v2_partial_loading(self):
        """Test that missing v2 files don't break loading."""
        with patch.object(ConfigLoader, '_load_config_v2') as mock_load:
            mock_config_v2 = ConfigV2()
            mock_config_v2.modes = {"trading_mode": "testnet"}
            mock_load.return_value = mock_config_v2

            loader = ConfigLoader()
            config = loader.load_config()

            assert config.config_v2 is not None
            assert config.has_config_v2()

            # Only modes should be loaded
            assert config.config_v2.modes == {"trading_mode": "testnet"}
            assert config.config_v2.core is None
            assert config.config_v2.domains == {}


def _load_with_config_v2(config_v2: ConfigV2) -> AuroraConfig:
    """Helper that forces ConfigLoader to return a provided ConfigV2 payload."""
    with patch.object(ConfigLoader, '_load_config_v2', return_value=config_v2):
        loader = ConfigLoader()
        return loader.load_config()


@pytest.fixture(autouse=True)
def _manage_cache_guard():
    """Ensure execution manage cache is cleared between tests."""
    clear_manage_config_cache()
    yield
    clear_manage_config_cache()


class TestConfigV2LoaderDeterministic:
    """Deterministic coverage for config v2 loader + resolvers."""

    def test_empty_config_v2_populates_placeholder(self):
        config = _load_with_config_v2(ConfigV2())

        assert config.config_v2 is not None
        assert config.config_v2.domains == {}
        assert config.has_config_v2() is False

    def test_config_v2_loader_populates_sections(self):
        config_v2 = ConfigV2(
            core={"core_key": "core_value"},
            symbols={"BTCUSDT": {"precision_price": 2}},
            instruments={"BTCUSDT": {"symbol": "BTCUSDT"}},
            domains={"execution": {"manage": {"auto": True}}},
            overrides={"profile": "shadow_live"},
            modes={"profile": "shadow_live"},
        )

        config = _load_with_config_v2(config_v2)

        assert config.has_config_v2() is True
        assert config.config_v2.core == {"core_key": "core_value"}
        assert config.config_v2.instruments == {
            "BTCUSDT": {"symbol": "BTCUSDT"}}
        assert config.config_v2.domains["execution"]["manage"]["auto"] is True

    def test_partial_config_v2_preserves_missing_sections(self):
        config_v2 = ConfigV2(modes={"trading_mode": "testnet"})

        config = _load_with_config_v2(config_v2)

        assert config.has_config_v2() is True
        assert config.config_v2.modes == {"trading_mode": "testnet"}
        assert config.config_v2.core is None
        assert config.config_v2.domains == {}

    def test_skeleton_config_v2_does_not_override_legacy(self):
        """Skeleton config v2 files exist but do not change legacy behavior for unmigrated domains; migrated domains use v2."""
        skeleton_v2 = ConfigV2(
            core={},
            instruments={},
            domains={
                "execution": {
                    "exposure": {"max_equity_utilization_pct": 200.0},
                    # Add manage data for migrated domain
                    "manage": {"auto": True},
                },  # Migrated domain with data
                "risk": {},  # Unmigrated domain, skeleton empty
            },
        )

        config = _load_with_config_v2(skeleton_v2)

        # Execution domain is migrated, so should use v2
        exposure = resolve_exposure_policy(config)
        assert exposure.source == "config_v2"
        assert exposure.caps.max_equity_utilization_ratio == Decimal(
            "2.0")  # 200% as decimal

        manage = resolve_execution_manage_config(config)
        assert manage.source == "config_v2"

        # Risk domain not migrated, skeleton empty, so fallback to legacy
        risk_state = resolve_daily_risk_state(config)
        assert risk_state.cfg.max_realized_loss_usd == pytest.approx(
            250.0)  # legacy value

    def test_config_v2_domains_override_resolvers(self):
        execution_domain = {
            "manage": {
                "auto": False,
                "quick_profit": {
                    "enabled": True,
                    "mode": "fixed_usd",
                    "target_usd": "5.5",
                    "priority": "highest",
                },
                "brackets": {
                    "enable": True,
                    "oco_emulation": False,
                    "retry": {"max_attempts": 7, "backoff_ms": [50, 75]},
                },
                "guardian": {
                    "unified": False,
                    "emit_tidy_event": False,
                    "poll_interval_ms": 250,
                    "cleanup_ttl_ms": 5000,
                    "symbol_cooldown_ms": 1000,
                },
                "watchdog": {
                    "ack_ttl_ms": 12000,
                    "fill_ttl_ms": 60000,
                    "check_interval_ms": 1500,
                },
                "orphan_monitor": {
                    "enabled": False,
                    "run_on_startup": False,
                },
            },
            "exposure": {
                "max_equity_utilization_pct": 50,
                "max_portfolio_fraction": 0.70,
                "max_directional_ratio": 1.5,
                "max_side_utilization_pct": {"long": 40, "short": 35},
                "per_symbol_cap_pct": 4,
                "pending_ttl_sec": 30,
                "post_fill_hold_ttl_sec": 10,
                "positions_stale_ttl_sec": 15,
                "count_pending_orders": False,
                "exclude_reduce_only": False,
                "leverage_defaults": {"default": 12, "BTCUSDT": 15},
            },
        }
        risk_domain = {
            "daily_limits": {
                "max_loss_usd": 1337.0,
                "max_drawdown_pct": 4.2,
                "reset_time_utc": "01:30",
            }
        }

        config_v2 = ConfigV2(domains={
            "execution": execution_domain,
            "risk": risk_domain,
        })

        config = _load_with_config_v2(config_v2)

        exposure = resolve_exposure_policy(config)
        assert exposure.source == "config_v2"
        assert exposure.caps.max_equity_utilization_ratio == Decimal("0.5")
        assert exposure.caps.max_side_utilization_ratio["long"] == Decimal(
            "0.40")
        assert exposure.leverage_defaults.resolve_for(
            "BTCUSDT") == Decimal("15")

        manage = resolve_execution_manage_config(config)
        assert manage.source == "config_v2"
        assert manage.auto is False
        assert manage.quick_profit.enabled is True
        assert manage.quick_profit.target_usd == Decimal("5.5")

        risk_state = resolve_daily_risk_state(config)
        assert risk_state.cfg.max_realized_loss_usd == pytest.approx(1337.0)
        assert risk_state.cfg.max_drawdown_pct == pytest.approx(4.2)

    def test_shadow_live_alias_promotes_hybrid_mode(self):
        config_v2 = ConfigV2(modes={
            "profiles": {
                "shadow_live": {
                    "trading_mode": "shadow_live",
                    "domains": {
                        "market_data": "live",
                        "execution_position": "testnet",
                    },
                }
            }
        })

        with patch.object(ConfigLoader, '_load_config_v2', return_value=config_v2), \
                patch.object(ConfigLoader, '_load_yaml_optional', return_value={}), \
                patch.dict(os.environ, {
                    "TRADING_MODE": "shadow_live",
                    "BINANCE_TESTNET_API_KEY": "tn-key",
                    "BINANCE_TESTNET_API_SECRET": "tn-secret",
                    "BINANCE_FUTURES_API_KEY_LIVE": "live-key",
                    "BINANCE_FUTURES_API_SECRET_LIVE": "live-secret",
                }, clear=True):
            config = ConfigLoader().load_config()

        assert config.trading_mode == "hybrid_live_data_testnet_exec"
        assert config.binance_api.live.api_key == "live-key"
        assert config.binance_api.testnet.api_key == "tn-key"
        assert config.get_domain_mode("market_data") == "live"

    def test_low_priority_env_testnet_does_not_override_shadow_live(self):
        loader = object.__new__(ConfigLoader)
        with patch.dict(os.environ, {"TRADING_MODE": "testnet"}, clear=False):
            mode = loader._select_trading_mode(
                "hybrid_live_data_testnet_exec",
                "shadow_live",
                ConfigV2(),
            )
        assert mode == "hybrid_live_data_testnet_exec"

    def test_high_priority_env_forces_target_mode(self):
        loader = object.__new__(ConfigLoader)
        with patch.dict(os.environ, {"AURORA_TRADING_MODE": "full_testnet"}, clear=False):
            mode = loader._select_trading_mode(
                "hybrid_live_data_testnet_exec",
                "shadow_live",
                ConfigV2(),
            )
        assert mode == "testnet"
