#!/usr/bin/env python3
"""
Aurora Core Configuration Loader

Simplified configuration loader for Aurora Core FSM federation.
Loads YAML configs and environment variables with basic validation.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from dotenv import load_dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


logger = logging.getLogger(__name__)


@dataclass
class AuroraConfig:
    """Aurora Core configuration container."""

    trading: Dict[str, Any]
    system: Dict[str, Any]
    binance_api_key: str
    binance_api_secret: str
    use_testnet: bool
    log_level: str
    trading_env: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "trading": self.trading,
            "system": self.system,
            "binance_api_key": self.binance_api_key,
            "binance_api_secret": self.binance_api_secret,
            "use_testnet": self.use_testnet,
            "log_level": self.log_level,
            "trading_env": self.trading_env,
        }


class ConfigLoader:
    """Simplified configuration loader for Aurora Core."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize config loader.

        Args:
            config_dir: Directory containing YAML config files (default: config/aurora)
        """
        self.config_dir = (
            config_dir or Path(__file__).parent.parent.parent / "config" / "aurora"
        )
        self._configs: Dict[str, Dict[str, Any]] = {}

        # Load environment variables from .env file if available
        if HAS_DOTENV:
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
            else:
                logger.warning(f".env file not found at {env_path}")

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """Load YAML configuration file."""
        if not HAS_YAML:
            raise ImportError(
                "PyYAML is required for YAML config loading. Install with: pip install PyYAML"
            )

        config_path = self.config_dir / filename
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _get_env_var(self, name: str, default: str = "", required: bool = False) -> str:
        """Get environment variable with validation."""
        value = os.environ.get(name, default)
        if required and not value:
            raise ValueError(f"Required environment variable '{name}' is not set")
        return value

    def load_config(self) -> AuroraConfig:
        """Load complete Aurora Core configuration.

        Returns:
            AuroraConfig: Complete configuration object

        Raises:
            FileNotFoundError: If config files are missing
            ValueError: If required environment variables are missing
        """
        # Load YAML configurations
        trading_config = self._load_yaml("trading.yaml")
        system_config = self._load_yaml("system.yaml")

        # Load environment variables
        use_testnet = self._get_env_var("USE_TESTNET", "true").lower() == "true"

        if use_testnet:
            binance_api_key = self._get_env_var(
                "BINANCE_TESTNET_API_KEY", required=True
            )
            binance_api_secret = self._get_env_var(
                "BINANCE_TESTNET_API_SECRET", required=True
            )
        else:
            # For mainnet, try mainnet keys first, fallback to testnet keys (for safety)
            binance_api_key = self._get_env_var(
                "BINANCE_MAINNET_API_KEY"
            ) or self._get_env_var("BINANCE_TESTNET_API_KEY", required=True)
            binance_api_secret = self._get_env_var(
                "BINANCE_MAINNET_API_SECRET"
            ) or self._get_env_var("BINANCE_TESTNET_API_SECRET", required=True)
        log_level = self._get_env_var("LOG_LEVEL", "DEBUG")
        trading_env = self._get_env_var("TRADING_ENV", "dev")

        # Create configuration object
        config = AuroraConfig(
            trading=trading_config,
            system=system_config,
            binance_api_key=binance_api_key,
            binance_api_secret=binance_api_secret,
            use_testnet=use_testnet,
            log_level=log_level,
            trading_env=trading_env,
        )

        logger.info(f"✅ Configuration loaded for environment: {trading_env}")
        logger.info(
            f"   Trading config version: {trading_config.get('config_version', 'unknown')}"
        )
        logger.info(
            f"   System config version: {system_config.get('config_version', 'unknown')}"
        )
        logger.info(f"   Log level: {log_level}")

        return config

    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration section."""
        if "trading" not in self._configs:
            self._configs["trading"] = self._load_yaml("trading.yaml")
        return self._configs["trading"]

    def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration section."""
        if "system" not in self._configs:
            self._configs["system"] = self._load_yaml("system.yaml")
        return self._configs["system"]


# Global config instance for easy access
_config_instance: Optional[AuroraConfig] = None


def get_config() -> AuroraConfig:
    """Get global configuration instance (lazy loading)."""
    global _config_instance
    if _config_instance is None:
        loader = ConfigLoader()
        _config_instance = loader.load_config()
    return _config_instance


def reload_config() -> AuroraConfig:
    """Reload configuration from files."""
    global _config_instance
    loader = ConfigLoader()
    _config_instance = loader.load_config()
    return _config_instance
