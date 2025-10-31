#!/usr/bin/env python3
import os
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv

LOG = logging.getLogger(__name__)


def deep_merge(source, destination):
    """Deep merge source dict into destination dict."""
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value
    return destination


class AuroraConfig:
    def __init__(self, config_dict: Dict[str, Any]):
        self._config = config_dict

    def __getattr__(self, name: str) -> Any:
        value = self._config.get(name)
        if isinstance(value, dict):
            return AuroraConfig(value)
        return value

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return self._config

    def get_domain_mode(self, domain_name: str) -> str:
        """Get trading_mode for a specific domain from domain_configuration."""
        domain_config = self._config.get("domain_configuration", {})
        if isinstance(domain_config, AuroraConfig):
            domain_config = domain_config.to_dict()
        domain_spec = domain_config.get(domain_name, {})
        if isinstance(domain_spec, dict):
            return domain_spec.get(
                "trading_mode", self._config.get("trading_mode", "live")
            )
        # If domain_spec is AuroraConfig object
        return getattr(
            domain_spec, "trading_mode", self._config.get("trading_mode", "live")
        )


class ConfigLoader:
    _ENV_VAR_PATTERN = re.compile(r"\$\{\s*(\w+)\s*\}")

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = (
            config_dir
            or Path(__file__).resolve().parent.parent.parent / "config" / "aurora"
        )
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        config_path = self.config_dir / filename
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _resolve_env_vars(self, config_part: Any) -> Any:
        if isinstance(config_part, dict):
            return {k: self._resolve_env_vars(v) for k, v in config_part.items()}
        if isinstance(config_part, list):
            return [self._resolve_env_vars(i) for i in config_part]
        if isinstance(config_part, str):
            return self._ENV_VAR_PATTERN.sub(
                lambda m: os.environ.get(m.group(1), m.group(0)), config_part
            )
        return config_part

    def _validate_config(self, config: Dict[str, Any]):
        if "trading_mode" not in config:
            raise ValueError("Missing 'trading_mode' in configuration.")
        if "binance_api" not in config:
            raise ValueError("Missing 'binance_api' in configuration.")
        mode = config["trading_mode"]
        api_config = config["binance_api"]
        if mode in ["live", "hybrid_live_data_testnet_exec"]:
            if "live" not in api_config or not all(
                api_config["live"].get(k) for k in ["api_key", "api_secret"]
            ):
                raise ValueError(
                    "Missing required keys in 'binance_api.live' for mode."
                )
        if mode in ["testnet", "hybrid_live_data_testnet_exec"]:
            if "testnet" not in api_config or not all(
                api_config["testnet"].get(k) for k in ["api_key", "api_secret"]
            ):
                raise ValueError(
                    "Missing required keys in 'binance_api.testnet' for mode."
                )

    def load_config(self) -> AuroraConfig:
        system_config = self._load_yaml("system.yaml")
        trading_config = self._load_yaml("trading.yaml")
        # Merge: trading_config (source) → system_config (destination)
        # This ensures system_config gets updated with trading parameters
        merged_config = {}
        deep_merge(system_config, merged_config)  # Copy system first
        deep_merge(trading_config, merged_config)  # Overlay trading
        resolved_config = self._resolve_env_vars(merged_config)

        # --- NEW: Risk portfolio source resolution (FSMP-P3-T01) ---
        ds = resolved_config.get("trading", {}).get("risk_management", {}).get("data_sources", {})
        exec_mode = resolved_config.get("trading", {}).get("domain_configuration", {}).get("execution_position", {}).get("trading_mode", "testnet") # Default to testnet for safety
        portfolio_src = ds.get("portfolio_state", "follow_execution")

        if portfolio_src == "follow_execution":
            portfolio_src = "testnet" if exec_mode != "live" else "live"

        if exec_mode == "testnet" and portfolio_src == "live": # Fail-closed: if execution is testnet, risk portfolio source must be testnet
            LOG.warning(
                f"Risk portfolio source '{portfolio_src}' overridden to 'testnet' "
                f"under hybrid/testnet execution mode (fail-closed). "
                f"Original config: trading.risk_management.data_sources.portfolio_state='{ds.get('portfolio_state')}'"
            )
            portfolio_src = "testnet"
        
        # Ensure _resolved section exists
        if "_resolved" not in resolved_config:
            resolved_config["_resolved"] = {}
        resolved_config["_resolved"]["risk_portfolio_source"] = portfolio_src
        # --- END NEW ---

        self._validate_config(resolved_config)
        LOG.info(
            f"Configuration loaded for trading_mode: '{resolved_config['trading_mode']}'"
        )
        return AuroraConfig(resolved_config)


_config_instance: Optional[AuroraConfig] = None


def get_config() -> AuroraConfig:
    global _config_instance
    if _config_instance is None:
        loader = ConfigLoader()
        _config_instance = loader.load_config()
    return _config_instance
