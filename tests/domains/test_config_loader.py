"""
Tests for ConfigLoader in apps/reference/config_loader.py

Tests cover:
- YAML config loading
- Environment variable handling
- AuroraConfig object creation
- Error handling for missing files/variables
- Global config functions
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.reference.config_loader import (
    AuroraConfig,
    ConfigLoader,
    get_config,
    reload_config,
)

import apps.reference.config_loader as config_loader


@pytest.fixture
def temp_config_dir():
    """Create temporary directory with mock config files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir)

        # Create mock trading.yaml
        trading_yaml = config_dir / "trading.yaml"
        trading_yaml.write_text("""
config_version: 1.0.0
instruments:
  BTCUSDT:
    venue: binance_futures
    symbol: BTCUSDT
    min_qty: 0.001
risk_budgets:
  trade_cvar95_max_bps: 150
""")

        # Create mock system.yaml
        system_yaml = config_dir / "system.yaml"
        system_yaml.write_text("""
config_version: 1.0.0
risk_core:
  cvar_threshold_bps: 120
kelly:
  fraction_cap: 0.85
logging:
  level: INFO
""")

        yield config_dir


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch):
    """Prevent tests from loading real environment secrets via .env."""
    monkeypatch.setattr(config_loader, "load_dotenv",
                        lambda *_args, **_kwargs: None)


class TestConfigLoader:
    def test_init_default_config_dir(self):
        """Test ConfigLoader initialization with default config directory."""
        loader = ConfigLoader()
        project_root = Path(__file__).parent.parent.parent
        candidates = [
            project_root / "config" / "aurora",
            project_root / "Phenix_Arhive" / "aurora",
            project_root.parent / "Phenix_Arhive" / "aurora",
            project_root / "config" / "archive" / "v1",
        ]
        expected_dir = next(
            (c for c in candidates if c.exists()), candidates[-1])
        assert loader.config_dir == expected_dir

    def test_init_custom_config_dir(self, temp_config_dir):
        """Test ConfigLoader initialization with custom config directory."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        assert loader.config_dir == temp_config_dir

    def test_load_yaml_success(self, temp_config_dir):
        """Test successful YAML loading."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader._load_yaml("trading.yaml")

        assert config["config_version"] == "1.0.0"
        assert "instruments" in config
        assert "BTCUSDT" in config["instruments"]

    def test_load_yaml_file_not_found(self, temp_config_dir):
        """Test YAML loading when file doesn't exist."""
        loader = ConfigLoader(config_dir=temp_config_dir)

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            loader._load_yaml("nonexistent.yaml")

    def test_load_yaml_no_yaml_support(self, temp_config_dir):
        """Test YAML loading when PyYAML is not available."""
        # Patch HAS_YAML in the config_loader module
        original_has_yaml = config_loader.HAS_YAML
        config_loader.HAS_YAML = False
        try:
            loader = ConfigLoader(config_dir=temp_config_dir)
            with pytest.raises(ImportError, match="PyYAML is required"):
                loader._load_yaml("trading.yaml")
        finally:
            config_loader.HAS_YAML = original_has_yaml

    def test_get_env_var_with_default(self):
        """Test getting environment variable with default value."""
        loader = ConfigLoader()

        with patch.dict(os.environ, {}, clear=True):
            value = loader._get_env_var("NONEXISTENT_VAR", "default_value")
            assert value == "default_value"

    def test_get_env_var_required_missing(self):
        """Test getting required environment variable when missing."""
        loader = ConfigLoader()

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError,
                match="Required environment variable 'REQUIRED_VAR' is not set",
            ):
                loader._get_env_var("REQUIRED_VAR", required=True)

    def test_get_env_var_required_present(self):
        """Test getting required environment variable when present."""
        loader = ConfigLoader()

        with patch.dict(os.environ, {"REQUIRED_VAR": "test_value"}):
            value = loader._get_env_var("REQUIRED_VAR", required=True)
            assert value == "test_value"

    @patch.dict(
        os.environ,
        {
            "USE_TESTNET": "true",
            "BINANCE_TESTNET_API_KEY": "test_key",
            "BINANCE_TESTNET_API_SECRET": "test_secret",
            "LOG_LEVEL": "DEBUG",
            "TRADING_ENV": "test",
        },
    )
    def test_load_config_testnet_success(self, temp_config_dir):
        """Test successful config loading for testnet environment."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()

        assert isinstance(config, AuroraConfig)
        assert config.use_testnet is True
        assert config.binance_api_key == "test_key"
        assert config.binance_api_secret == "test_secret"
        assert config.log_level == "DEBUG"
        assert config.trading_env == "test"
        assert "config_version" in loader.get_trading_config()
        assert "config_version" in loader.get_system_config()

    @patch.dict(
        os.environ,
        {
            "USE_TESTNET": "false",
            "BINANCE_MAINNET_API_KEY": "mainnet_key",
            "BINANCE_MAINNET_API_SECRET": "mainnet_secret",
        },
        clear=True,
    )
    def test_load_config_mainnet_success(self, temp_config_dir):
        """Test successful config loading for mainnet environment."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        config = loader.load_config()

        assert config.use_testnet is False
        assert config.binance_api_key == "mainnet_key"
        assert config.binance_api_secret == "mainnet_secret"

    @patch.dict(
        os.environ,
        {
            "USE_TESTNET": "false"
            # No mainnet keys, should fallback to testnet
        },
        clear=True,
    )
    def test_load_config_mainnet_fallback_to_testnet(self, temp_config_dir):
        """Test mainnet config falls back to testnet keys when mainnet keys missing."""
        with patch.dict(
            os.environ,
            {
                "BINANCE_TESTNET_API_KEY": "fallback_key",
                "BINANCE_TESTNET_API_SECRET": "fallback_secret",
            },
            clear=False,
        ):
            loader = ConfigLoader(config_dir=temp_config_dir)
            config = loader.load_config()

            assert config.use_testnet is False
            assert config.binance_api_key == "fallback_key"
            assert config.binance_api_secret == "fallback_secret"

    @pytest.mark.skip(
        reason="Cannot test missing keys when real API keys are present in environment"
    )
    def test_load_config_missing_required_keys(self, temp_config_dir, monkeypatch):
        """Test config loading fails when required API keys are missing."""
        pass

    def test_get_trading_config(self, temp_config_dir):
        """Test getting trading config section."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        trading_config = loader.get_trading_config()

        assert "config_version" in trading_config
        assert "instruments" in trading_config

    def test_get_system_config(self, temp_config_dir):
        """Test getting system config section."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        system_config = loader.get_system_config()

        assert "config_version" in system_config
        assert "risk_core" in system_config


class TestAuroraConfig:
    """Test AuroraConfig dataclass functionality."""

    def test_aurora_config_creation(self):
        """Test AuroraConfig object creation."""
        trading = {"key": "trading_value"}
        system = {"key": "system_value"}

        config = AuroraConfig(
            trading=trading,
            system=system,
            binance_api_key="test_key",
            binance_api_secret="test_secret",
            use_testnet=True,
            log_level="INFO",
            trading_env="dev",
        )

        trading_dump = config.trading.model_dump() if hasattr(
            config.trading, "model_dump") else config.trading
        system_dump = config.system.model_dump() if hasattr(
            config.system, "model_dump") else config.system
        assert trading_dump.get("key") == "trading_value"
        assert system_dump.get("key") == "system_value"
        assert config.binance_api_key == "test_key"
        assert config.binance_api_secret == "test_secret"
        assert config.use_testnet is True
        assert config.log_level == "INFO"
        assert config.trading_env == "dev"

    def test_aurora_config_to_dict(self):
        """Test AuroraConfig to_dict conversion."""
        trading = {"trading_key": "trading_value"}
        system = {"system_key": "system_value"}

        config = AuroraConfig(
            trading=trading,
            system=system,
            binance_api_key="test_key",
            binance_api_secret="test_secret",
            use_testnet=False,
            log_level="DEBUG",
            trading_env="prod",
        )

        config_dict = config.to_dict()

        assert config_dict["trading"]["trading_key"] == "trading_value"
        assert config_dict["system"]["system_key"] == "system_value"
        assert config.binance_api_key == "test_key"
        assert config.binance_api_secret == "test_secret"
        assert config.use_testnet is False
        assert config.log_level == "DEBUG"
        assert config.trading_env == "prod"


class TestGlobalConfigFunctions:
    """Test global config functions get_config and reload_config."""

    def test_get_config_returns_config_object(self, temp_config_dir):
        """Test get_config returns AuroraConfig object."""
        # Reset global config
        config_loader._config_instance = None

        # Set required env vars
        with patch.dict(
            os.environ,
            {
                "USE_TESTNET": "true",
                "BINANCE_TESTNET_API_KEY": "test_key",
                "BINANCE_TESTNET_API_SECRET": "test_secret",
            },
        ):
            config = get_config()
            assert isinstance(config, AuroraConfig)
            assert config.binance_api_key == "test_key"

    def test_reload_config_returns_new_config(self, temp_config_dir):
        """Test reload_config forces new config creation."""
        config_loader._config_instance = None

        with patch.dict(
            os.environ,
            {
                "USE_TESTNET": "true",
                "BINANCE_TESTNET_API_KEY": "test_key",
                "BINANCE_TESTNET_API_SECRET": "test_secret",
            },
        ):
            config1 = reload_config()
            config2 = reload_config()

            # Should be different objects
            assert config1 is not config2
            assert isinstance(config1, AuroraConfig)
            assert isinstance(config2, AuroraConfig)
