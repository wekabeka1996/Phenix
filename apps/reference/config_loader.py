#!/usr/bin/env python3
import os
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from .config_models import AuroraConfig as PydanticAuroraConfig

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


# Legacy wrapper for backwards compatibility
class AuroraConfig(PydanticAuroraConfig):
    """
    AuroraConfig wrapper that provides both Pydantic V2 validation and legacy .get() interface.

    This class allows gradual migration of code from dict-based .get() calls to typed attributes.
    Eventually all code should use typed attributes directly.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Legacy dict-like .get() interface for backwards compatibility."""
        try:
            # Try to get as Pydantic field
            return getattr(self, key, default)
        except AttributeError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for debugging/serialization."""
        return self.model_dump()

    def get_domain_mode(self, domain_name: str) -> str:
        """Get trading_mode for a specific domain from domain_configuration."""
        # This is for advanced domain-specific modes (if needed in future)
        return self.trading_mode


class ConfigLoader:
    _ENV_VAR_PATTERN = re.compile(r"\$\{\s*(\w+)\s*\}")

    def __init__(self, config_dir: Optional[Path] = None):
        # Prefer explicit arg
        if config_dir is not None:
            self.config_dir = config_dir
        else:
            # Detect test override directory if present
            project_root = Path(__file__).resolve().parents[3]
            tests_dir = project_root / "tests" / "config" / "aurora"
            default_dir = Path(__file__).resolve().parent.parent.parent / "config" / "aurora"
            self.config_dir = tests_dir if tests_dir.exists() else default_dir
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        config_path = self.config_dir / filename
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8-sig", errors="replace") as f:
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

    def _resolve_mode_overrides(self, config: Dict[str, Any]) -> None:
        """Apply mode-specific decision overrides from decision[mode] → decision.

        This resolver activates profile-based configs:
        - decision.testnet.* → decision.* (when trading_mode=testnet)
        - decision.production.* → decision.* (when trading_mode=production)

        ALSO applies risk[mode] → risk.trading_allowed_thresholds for risk gates.

        Preserves original decision.{testnet,production} blocks for documentation.
        """
        mode = config.get("trading_mode", "production")
        trading = config.get("trading", {})
        decision = trading.get("decision", {})
        risk = trading.get("risk", {})

        if not isinstance(decision, dict):
            return

        mode_overrides = decision.get(mode, {})
        if not isinstance(mode_overrides, dict):
            return

        if mode_overrides:
            LOG.info(
                f"[mode-resolver] Applying '{mode}' mode decision overrides")
            for key, value in mode_overrides.items():
                old_val = decision.get(key)
                decision[key] = value
                if old_val is not None:
                    LOG.debug(f"  {key}: {old_val} → {value}")
                else:
                    LOG.debug(f"  {key}: (new) → {value}")

        # Apply risk overrides
        if isinstance(risk, dict):
            risk_mode_overrides = risk.get(mode, {})
            if isinstance(risk_mode_overrides, dict) and risk_mode_overrides:
                LOG.info(
                    f"[mode-resolver] Applying '{mode}' mode risk overrides")
                # Ensure trading_allowed_thresholds exists
                if "trading_allowed_thresholds" not in risk:
                    risk["trading_allowed_thresholds"] = {}
                thresholds = risk["trading_allowed_thresholds"]

                for key, value in risk_mode_overrides.items():
                    old_val = thresholds.get(key)
                    thresholds[key] = value
                    if old_val is not None:
                        LOG.debug(
                            f"  risk.thresholds.{key}: {old_val} → {value}")
                    else:
                        LOG.debug(f"  risk.thresholds.{key}: (new) → {value}")

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
        """Load and validate configuration using Pydantic.

        This method:
        1. Loads YAML files
        2. Resolves environment variables
        3. Applies mode-specific overrides
        4. Validates through Pydantic (fails fast if invalid)

        Raises:
            ValidationError: If config doesn't match Pydantic schema
            FileNotFoundError: If config files missing
        """
        try:
            system_config = self._load_yaml("system.yaml")
            trading_config = self._load_yaml("trading.yaml")
            regime_config = self._load_yaml("regime.yaml")
            domains_config = self._load_yaml("domains.yaml")  # NEW: Load domains config
        except FileNotFoundError as e:
            LOG.error(f"Config file error: {e}")
            raise
        
        # Load strategy configs (optional, don't fail if missing)
        mr_1m_config: Dict[str, Any] = {}
        try:
            strategies_dir = self.config_dir / "strategies"
            if strategies_dir.exists():
                mr_1m_path = strategies_dir / "mean_reversion_1m.yaml"
                if mr_1m_path.exists():
                    with open(mr_1m_path, "r", encoding="utf-8-sig", errors="replace") as f:
                        mr_1m_raw = yaml.safe_load(f)
                    if isinstance(mr_1m_raw, dict) and "mean_reversion_1m" in mr_1m_raw:
                        mr_1m_config = mr_1m_raw["mean_reversion_1m"]
                        LOG.info(f"Loaded Mean Reversion 1m config from {mr_1m_path}")
        except Exception as e:
            LOG.warning(f"Failed to load mean_reversion_1m.yaml: {e}")

        # Merge: trading_config (source) → system_config (destination)
        merged_config: Dict[str, Any] = {}
        deep_merge(system_config, merged_config)  # Copy system first
        deep_merge(trading_config, merged_config)  # Overlay trading
        deep_merge(regime_config, merged_config)   # Overlay regime (models, hmm, etc.)
        
        # Add Mean Reversion 1m config at root level
        if mr_1m_config:
            merged_config["mean_reversion_1m"] = mr_1m_config
        
        # Merge domains config into root (and optionally trading.domains for backward compat if needed)
        if 'domains' in domains_config:
            merged_config['domains'] = domains_config['domains']
            
            # Also keep in trading.domains for consistency if TradingConfig has it
            if 'trading' not in merged_config:
                merged_config['trading'] = {}
            merged_config['trading']['domains'] = domains_config['domains']
        else:
            # If domains.yaml doesn't have top-level 'domains' key, merge all content as domains
            merged_config['domains'] = domains_config
            
            if 'trading' not in merged_config:
                merged_config['trading'] = {}
            merged_config['trading']['domains'] = domains_config

        # Resolve environment variables
        resolved_config = self._resolve_env_vars(merged_config)

        # Apply mode-specific decision overrides
        self._resolve_mode_overrides(resolved_config)

        # --- NEW: Validate through Pydantic (startup validation) ---
        try:
            pydantic_config = PydanticAuroraConfig(**resolved_config)
            LOG.info(
                f"✅ Configuration validated for trading_mode: '{pydantic_config.trading_mode}'"
            )
            # Back-compat mapping: expose trading.execution at root 'execution' if missing
            try:
                if 'execution' not in resolved_config:
                    tr = resolved_config.get('trading', {}) or {}
                    if isinstance(tr, dict) and tr.get('execution') is not None:
                        resolved_config['execution'] = tr.get('execution')
            except Exception:
                pass
            # Convert back to our legacy-compatible wrapper
            return AuroraConfig(**resolved_config)
        except ValidationError as e:
            LOG.error("❌ Configuration validation failed:")
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                LOG.error(f"  {loc}: {error['msg']}")
            raise


_config_instance: Optional[AuroraConfig] = None


def get_config() -> AuroraConfig:
    global _config_instance
    if _config_instance is None:
        loader = ConfigLoader()
        _config_instance = loader.load_config()
    return _config_instance
