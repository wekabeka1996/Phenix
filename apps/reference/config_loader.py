#!/usr/bin/env python3
import os
import logging
import re
import copy
from pathlib import Path
from typing import Dict, Any, Optional

try:  # pragma: no cover - import guard for PyYAML
    import yaml
    HAS_YAML = True
except Exception:  # pragma: no cover
    yaml = None
    HAS_YAML = False

from dotenv import load_dotenv
from pydantic import ValidationError

from .config_models import AuroraConfig as PydanticAuroraConfig, ConfigV2
from .utils import compute_effective_trading_modes, get_domain_mode_from_mapping

# EP-CONFIG-INJECTION-S2: Import typed config resolver for execution_position
try:
    from .config.execution_position import resolve_execution_position_config
    from .domains.execution_position.config import ExecutionPositionConfig
    HAS_EXECPOS_TYPED_CONFIG = True
except ImportError:
    resolve_execution_position_config = None
    ExecutionPositionConfig = None
    HAS_EXECPOS_TYPED_CONFIG = False

LOG = logging.getLogger(__name__)


def _detect_project_root() -> Path:
    """Best-effort detection of repository root (folder that contains /config)."""
    env_root = os.environ.get("AURORA_PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "config").exists():
            return candidate

    current = Path(__file__).resolve()
    # Search for repo root (has .git or README.md + config/)
    for parent in current.parents:
        # Prefer directory with .git (true repo root)
        if (parent / ".git").exists() and (parent / "config").exists():
            return parent
        # Or directory with README.md + config/ (repo root without .git)
        if (parent / "README.md").exists() and (parent / "config").exists():
            return parent

    # Fallback: assume two levels up (repo/apps/reference → repo)
    return Path(__file__).resolve().parents[2]


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
        modes = getattr(self, "_effective_modes_cache", None)
        if modes is None:
            try:
                modes = compute_effective_trading_modes(self)
            except Exception:
                modes = compute_effective_trading_modes(self.model_dump())
            self._effective_modes_cache = modes
        return modes.for_domain(domain_name)

    # --- Legacy compatibility helpers -------------------------------------------------
    def _get_extra_field(self, key: str) -> Optional[Any]:
        extras = getattr(self, "__pydantic_extra__", None)
        if isinstance(extras, dict) and key in extras:
            return extras[key]
        return None

    @property
    def use_testnet(self) -> bool:
        """Legacy flag indicating whether testnet credentials are active."""
        extra_flag = self._get_extra_field("use_testnet")
        if extra_flag is not None:
            return bool(extra_flag)
        env_override = os.environ.get("USE_TESTNET")
        if env_override is not None:
            return str(env_override).lower() in {"1", "true", "yes"}
        mode = (getattr(self, "trading_mode", "") or "").lower()
        return "testnet" in mode

    @property
    def binance_api_key(self) -> Optional[str]:
        # Respect explicitly provided extras first
        extra_value = self._get_extra_field("binance_api_key")
        if extra_value is not None:
            return extra_value

        env_targets = []
        if self.use_testnet:
            env_targets.append("BINANCE_TESTNET_API_KEY")
        else:
            env_targets.extend([
                "BINANCE_MAINNET_API_KEY",
                "BINANCE_FUTURES_API_KEY_LIVE",
                "BINANCE_TESTNET_API_KEY",  # safety fallback
            ])
        for key in env_targets:
            value = os.environ.get(key)
            if value:
                return value

        try:
            if self.use_testnet:
                return self.binance_api.testnet.api_key
            return self.binance_api.live.api_key or self.binance_api.testnet.api_key
        except Exception:
            return None

    @property
    def binance_api_secret(self) -> Optional[str]:
        extra_value = self._get_extra_field("binance_api_secret")
        if extra_value is not None:
            return extra_value

        env_targets = []
        if self.use_testnet:
            env_targets.append("BINANCE_TESTNET_API_SECRET")
        else:
            env_targets.extend([
                "BINANCE_MAINNET_API_SECRET",
                "BINANCE_FUTURES_API_SECRET_LIVE",
                "BINANCE_TESTNET_API_SECRET",
            ])
        for key in env_targets:
            value = os.environ.get(key)
            if value:
                return value

        try:
            if self.use_testnet:
                return self.binance_api.testnet.api_secret
            return self.binance_api.live.api_secret or self.binance_api.testnet.api_secret
        except Exception:
            return None

    @property
    def log_level(self) -> Optional[str]:
        extra_value = self._get_extra_field("log_level")
        if extra_value is not None:
            return extra_value
        env_level = os.environ.get("LOG_LEVEL")
        if env_level:
            return env_level
        try:
            return self.system.logging.level
        except Exception:
            return None

    @property
    def trading_env(self) -> Optional[str]:
        extra_value = self._get_extra_field("trading_env")
        if extra_value is not None:
            return extra_value
        return os.environ.get("TRADING_ENV")


class AuroraConfigDict(dict):
    """Dict snapshot that preserves config_v2 attribute for legacy consumers."""

    def __init__(self, payload: Dict[str, Any], config_v2: Optional[ConfigV2]):
        super().__init__(payload)
        self.config_v2 = config_v2

    def copy(self):  # type: ignore[override]
        return AuroraConfigDict(dict(self), getattr(self, "config_v2", None))

    def __deepcopy__(self, memo):
        memo_id = id(self)
        if memo_id in memo:
            return memo[memo_id]
        cloned_payload = copy.deepcopy(dict(self), memo)
        cloned = AuroraConfigDict(
            cloned_payload,
            getattr(self, "config_v2", None),
        )
        memo[memo_id] = cloned
        return cloned


def _aurora_config_to_dict_with_v2(self: "AuroraConfig") -> Dict[str, Any]:
    payload = self.model_dump()
    return AuroraConfigDict(payload, getattr(self, "config_v2", None))


# type: ignore[assignment]
AuroraConfig.to_dict = _aurora_config_to_dict_with_v2


class ConfigLoader:
    _ENV_VAR_PATTERN = re.compile(r"\$\{\s*(\w+)\s*\}")

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialise loader for legacy YAML files.

        By default we point to the quarantined legacy location under
        config/aurora (if it exists) or config/archive/v1. Tests/scripts that
        need bespoke fixtures should pass config_dir explicitly instead of
        relying on implicit overrides.
        """
        self.project_root = _detect_project_root()
        print(
            f"DEBUG: ConfigLoader project_root detected as: {self.project_root}")
        if config_dir is not None:
            self.config_dir = Path(config_dir)
        else:
            candidates = []

            env_legacy_dir = os.environ.get("AURORA_LEGACY_CONFIG_DIR")
            if env_legacy_dir:
                env_path = Path(env_legacy_dir).expanduser().resolve()
                candidates.append(env_path)

            candidates.extend([
                self.project_root / "config" / "aurora",
                self.project_root / "Phenix_Arhive" / "aurora",
                self.project_root.parent / "Phenix_Arhive" / "aurora",
                self.project_root / "config" / "archive" / "v1",
            ])

            for candidate in candidates:
                if candidate and candidate.exists():
                    self.config_dir = candidate
                    break
            else:
                self.config_dir = candidates[-1]
        env_path = self.project_root / ".env"
        print(
            f"DEBUG: Checking .env at {env_path}, exists={env_path.exists()}")
        if env_path.exists():
            load_dotenv(env_path)
            print(
                f"DEBUG: Loaded .env. BINANCE_TESTNET_API_KEY present: {'BINANCE_TESTNET_API_KEY' in os.environ}")
        self._raw_cache: Dict[str, Dict[str, Any]] = {}

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        if not HAS_YAML:
            raise ImportError(
                "PyYAML is required for YAML config loading. Install with: pip install PyYAML")
        config_path = self.config_dir / filename
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8-sig", errors="replace") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def get_trading_config(self) -> Dict[str, Any]:
        """Expose raw trading.yaml content for legacy consumers/tests."""
        if "trading" not in self._raw_cache:
            payload = self._load_yaml_optional("trading.yaml")
            self._raw_cache["trading"] = payload or {}
        return self._raw_cache["trading"]

    def get_system_config(self) -> Dict[str, Any]:
        """Expose raw system.yaml content for legacy consumers/tests."""
        if "system" not in self._raw_cache:
            payload = self._load_yaml_optional("system.yaml")
            self._raw_cache["system"] = payload or {}
        return self._raw_cache["system"]

    def _load_yaml_optional(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load YAML file if exists, return None otherwise."""
        config_path = self.config_dir / filename
        if not config_path.exists():
            return None
        with open(config_path, "r", encoding="utf-8-sig", errors="replace") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _load_config_v2(self) -> ConfigV2:
        """Load config v2 files from config/ directory."""
        # Config v2 root is config/ (not config/aurora/)
        config_v2_root = self.project_root / "config"

        config_v2 = ConfigV2()

        # Load individual files
        config_v2.core = self._load_yaml_optional_from_path(
            config_v2_root / "core.yaml")
        config_v2.symbols = self._load_yaml_optional_from_path(
            config_v2_root / "symbols.yaml")
        config_v2.instruments = self._load_yaml_optional_from_path(
            config_v2_root / "instruments.yaml")
        config_v2.overrides = self._load_yaml_optional_from_path(
            config_v2_root / "overrides.yaml")
        config_v2.modes = self._load_yaml_optional_from_path(
            config_v2_root / "modes.yaml")

        # Load domains
        domains_dir = config_v2_root / "domains"
        if domains_dir.exists():
            for domain_file in domains_dir.glob("*.yaml"):
                domain_name = domain_file.stem  # e.g., execution.yaml -> execution
                domain_config = self._load_yaml_optional_from_path(domain_file)
                if domain_config is not None:
                    config_v2.domains[domain_name] = domain_config

        return config_v2

    def _normalize_trading_mode_alias(self, mode: Optional[str]) -> Optional[str]:
        """Map user-facing trading mode/profile strings to canonical runtime modes."""
        if not mode:
            return None

        candidate = str(mode).strip().lower()
        if not candidate:
            return None

        alias_map = {
            "shadow_live": "hybrid_live_data_testnet_exec",
            "hybrid": "hybrid_live_data_testnet_exec",
            "hybrid_live_data_testnet_exec": "hybrid_live_data_testnet_exec",
            "hybrid_live_data_testnet_execution": "hybrid_live_data_testnet_exec",
            "full_testnet": "testnet",
            "paper": "testnet",
            "sandbox": "testnet",
            "dev": "testnet",
            "full_live": "live",
            "production": "production",
        }
        if candidate in alias_map:
            return alias_map[candidate]

        if candidate in {"testnet", "live", "production", "hybrid_live_data_testnet_exec"}:
            return candidate

        return None

    def _select_trading_mode(self, legacy_root_mode: Optional[str], legacy_trading_mode: Optional[str],
                             config_v2: ConfigV2) -> str:
        """Determine the effective trading_mode for runtime consumers."""
        high_priority_envs = (
            os.environ.get("AURORA_TRADING_MODE"),
            os.environ.get("AURORA_TRADING_PROFILE"),
        )
        for candidate in high_priority_envs:
            normalized = self._normalize_trading_mode_alias(candidate)
            if normalized:
                return normalized

        env_testnet_fallback = None
        low_priority_envs = (
            os.environ.get("TRADING_MODE"),
            os.environ.get("TRADING_PROFILE"),
        )
        for candidate in low_priority_envs:
            normalized = self._normalize_trading_mode_alias(candidate)
            if not normalized:
                continue
            if normalized != "testnet":
                return normalized
            env_testnet_fallback = normalized

        legacy_candidates = (legacy_root_mode, legacy_trading_mode)
        for candidate in legacy_candidates:
            normalized = self._normalize_trading_mode_alias(candidate)
            if normalized and normalized != "testnet":
                return normalized

        v2_mode = None
        modes_cfg = getattr(config_v2, "modes", None)
        if isinstance(modes_cfg, dict) and modes_cfg:
            v2_mode = self._normalize_trading_mode_alias(
                self._default_trading_mode_from_v2(config_v2)
            )
        if v2_mode:
            return v2_mode

        for candidate in legacy_candidates:
            normalized = self._normalize_trading_mode_alias(candidate)
            if normalized:
                return normalized

        if env_testnet_fallback:
            return env_testnet_fallback

        return "testnet"

    def _load_yaml_optional_from_path(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load YAML from specific path if exists."""
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
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

    def _get_env_var(self, name: str, default: str = "", required: bool = False) -> str:
        """Legacy helper mirroring the shim interface used in older tests."""
        value = os.environ.get(name, default)
        if required and not value:
            raise ValueError(
                f"Required environment variable '{name}' is not set")
        return value

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
        system_config = self._load_yaml_optional("system.yaml") or {}
        trading_config = self._load_yaml_optional("trading.yaml") or {}
        # Legacy YAML пакети можуть бути відсутніми після переходу на config v2.
        # Раніше ми виводили WARNING, але тепер це нормальний шлях, тож попередження прибрано.

        # Merge: trading_config (source) → system_config (destination)
        merged_config: Dict[str, Any] = {}
        deep_merge(system_config, merged_config)  # Copy system first
        deep_merge(trading_config, merged_config)  # Overlay trading

        # Resolve environment variables
        resolved_config = self._resolve_env_vars(merged_config)

        # Apply mode-specific decision overrides
        self._resolve_mode_overrides(resolved_config)

        # Load config v2 (domains, instruments, etc.) and hydrate legacy shape when needed
        config_v2 = self._load_config_v2()
        self._hydrate_from_config_v2(resolved_config, config_v2)
        self._ensure_api_defaults(resolved_config)
        self._flatten_feature_engineering(resolved_config)

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
            resolved_config['config_v2'] = config_v2

            # EP-CONFIG-INJECTION-S2: Build typed ExecutionPositionConfig from config_v2
            if HAS_EXECPOS_TYPED_CONFIG:
                try:
                    raw_execution_cfg = config_v2.domains.get(
                        'execution') if config_v2 else None
                    if raw_execution_cfg is not None:  # Allow empty dict {} for defaults
                        ep_typed_cfg = resolve_execution_position_config(
                            raw_execution_cfg
                            # Uses default paths:
                            # - aggregated_oco_path = ("manage", "brackets", "aggregated_oco")
                            # - trailing_path = ("manage", "trailing")
                            # - close_path = ("manage", "close")
                        )
                        resolved_config['execution_position_cfg'] = ep_typed_cfg
                        LOG.info(
                            f"✅ ExecutionPositionConfig built: "
                            f"aggregated_oco.enabled={ep_typed_cfg.aggregated_oco.enabled}, "
                            f"sl_pct={ep_typed_cfg.aggregated_oco.sl_pct}, "
                            f"tp_rr={ep_typed_cfg.aggregated_oco.tp_rr}"
                        )
                    else:
                        LOG.debug(
                            "⚠️ No execution domain config found in config_v2, skipping ExecutionPositionConfig")
                except Exception as e:
                    LOG.warning(
                        f"⚠️ Failed to build ExecutionPositionConfig: {e}", exc_info=True)
                    # Non-fatal: system can still run with dict-based config
            else:
                LOG.debug(
                    "⚠️ ExecutionPositionConfig resolver not available (HAS_EXECPOS_TYPED_CONFIG=False)")

            # Convert back to our legacy-compatible wrapper
            return AuroraConfig(**resolved_config)
        except ValidationError as e:
            LOG.error("❌ Configuration validation failed:")
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                LOG.error(f"  {loc}: {error['msg']}")
            raise

    def _hydrate_from_config_v2(self, resolved_config: Dict[str, Any], config_v2: ConfigV2) -> None:
        """Populate legacy config shape using config v2 when legacy YAML is absent."""
        if config_v2 is None:
            return

        trading_cfg = resolved_config.setdefault("trading", {})

        selected_mode = self._select_trading_mode(
            resolved_config.get("trading_mode"),
            trading_cfg.get("mode"),
            config_v2,
        )
        trading_cfg["mode"] = selected_mode
        resolved_config["trading_mode"] = selected_mode

        # Instruments → legacy format
        if not trading_cfg.get("instruments"):
            instruments = self._build_instruments_from_v2(config_v2)
            if instruments:
                trading_cfg["instruments"] = instruments

        # TCA preferences
        if not trading_cfg.get("tca_prefs"):
            tca_prefs = self._build_tca_prefs_from_v2(config_v2)
            if tca_prefs:
                trading_cfg["tca_prefs"] = tca_prefs

        # Risk budgets (soft limits for DecisionMaking)
        if not trading_cfg.get("risk_budgets"):
            risk_budgets = self._build_risk_budgets_from_v2(config_v2)
            if risk_budgets:
                trading_cfg["risk_budgets"] = risk_budgets

        # Risk management data sources (for hybrid coherence checks)
        risk_management = trading_cfg.setdefault("risk_management", {})
        if not risk_management.get("data_sources"):
            data_sources = self._build_risk_data_sources_from_v2(config_v2)
            if data_sources:
                risk_management["data_sources"] = data_sources

        # Feature engineering structure (legacy nesting expected later for flattening)
        if not trading_cfg.get("feature_engineering"):
            fe_cfg = self._build_feature_engineering_from_v2(config_v2)
            if fe_cfg:
                trading_cfg["feature_engineering"] = fe_cfg

        # Market data macro sync needs to exist at both trading.market_data and root.market_data
        market_data = trading_cfg.setdefault("market_data", {})
        if not market_data.get("macro_sync"):
            macro_sync = self._build_macro_sync_from_v2(config_v2)
            if macro_sync:
                market_data["macro_sync"] = macro_sync

        # Mirror market_data at root for tests that expect it there
        resolved_market_data = resolved_config.setdefault("market_data", {})
        if not resolved_market_data and market_data:
            resolved_market_data.update(market_data)
        elif market_data.get("macro_sync") and "macro_sync" not in resolved_market_data:
            resolved_market_data["macro_sync"] = market_data["macro_sync"]

        # Provide domain configuration overrides from v2 modes when missing
        if not trading_cfg.get("domain_configuration"):
            domain_cfg = self._build_domain_configuration_from_v2(config_v2,
                                                                  trading_cfg.get("mode"))
            if domain_cfg:
                trading_cfg["domain_configuration"] = domain_cfg

    def _default_trading_mode_from_v2(self, config_v2: ConfigV2) -> str:
        modes = getattr(config_v2, "modes", None) or {}
        profiles = modes.get("profiles", {}) if isinstance(modes, dict) else {}

        # Check for explicit default_profile
        default_profile_name = modes.get(
            "default_profile") if isinstance(modes, dict) else None
        if default_profile_name and default_profile_name in profiles:
            default_profile = profiles[default_profile_name]
            if isinstance(default_profile, dict):
                return default_profile.get("trading_mode", "testnet")

        # Fallback to shadow_live if exists (legacy behavior)
        if "shadow_live" in profiles:
            return profiles["shadow_live"].get("trading_mode", "testnet")

        # Fallback to first profile
        if profiles:
            first_profile = next(iter(profiles.values()))
            if isinstance(first_profile, dict):
                return first_profile.get("trading_mode", "testnet")
        return "testnet"

    def _build_instruments_from_v2(self, config_v2: ConfigV2) -> Dict[str, Any]:
        instruments_payload = getattr(config_v2, "instruments", None) or {}
        instrument_defs = instruments_payload.get("instruments", {}) if isinstance(
            instruments_payload, dict) else {}
        overrides = (getattr(config_v2, "overrides", None)
                     or {}).get("symbols", {})
        instruments: Dict[str, Any] = {}
        for symbol, spec in instrument_defs.items():
            limits = spec.get("limits", {}) if isinstance(spec, dict) else {}
            precision = spec.get("precision", {}) if isinstance(
                spec, dict) else {}
            override_limits = overrides.get(symbol, {}).get("limits", {})
            merged_limits = {**limits, **override_limits}
            instruments[symbol] = {
                "symbol": symbol,
                "step_size": str(merged_limits.get(
                    "step_size", limits.get("step_size", "0.001"))),
                "tick_size": str(merged_limits.get(
                    "tick_size", limits.get("tick_size", "0.01"))),
                "min_notional": str(merged_limits.get(
                    "min_notional", limits.get("min_notional", "10"))),
                "min_qty": str(merged_limits.get(
                    "min_qty", limits.get("min_qty", "0.001"))),
                "precision": precision,
            }
        return instruments

    def _build_tca_prefs_from_v2(self, config_v2: ConfigV2) -> Optional[Dict[str, Any]]:
        tca_cfg = config_v2.domains.get("tca") if config_v2.domains else None
        if isinstance(tca_cfg, dict):
            prefs = tca_cfg.get("prefs") or tca_cfg.get("preferences")
            if isinstance(prefs, dict) and prefs:
                return prefs
        return {
            "max_slippage_pct": 0.5,
            "preferred_venue": "binance",
            "execution_priority": "speed",
        }

    def _build_risk_budgets_from_v2(self, config_v2: ConfigV2) -> Optional[Dict[str, Any]]:
        risk_cfg = config_v2.domains.get("risk") if config_v2.domains else None
        if isinstance(risk_cfg, dict):
            budgets = risk_cfg.get("budgets")
            if isinstance(budgets, dict) and budgets:
                return budgets
        return {
            "max_portfolio_risk_pct": 5.0,
            "max_single_position_risk_pct": 1.0,
            "max_daily_loss_pct": 2.0,
        }

    def _build_risk_data_sources_from_v2(self, config_v2: ConfigV2) -> Optional[Dict[str, Any]]:
        risk_cfg = config_v2.domains.get("risk") if config_v2.domains else None
        data_sources = None
        if isinstance(risk_cfg, dict):
            data_sources = risk_cfg.get("data_sources")
        if isinstance(data_sources, dict) and data_sources:
            return data_sources
        return {"portfolio_state": "testnet", "market_data": "live"}

    def _build_feature_engineering_from_v2(self, config_v2: ConfigV2) -> Optional[Dict[str, Any]]:
        features_cfg = config_v2.domains.get(
            "features") if config_v2.domains else None
        if not isinstance(features_cfg, dict):
            return None

        result: Dict[str, Any] = {}
        global_cfg = features_cfg.get("global", {})
        if isinstance(global_cfg, dict):
            result["enable_new_metrics"] = global_cfg.get(
                "enable_new_metrics", True)

        windows = features_cfg.get("windows", {})
        if isinstance(windows, dict):
            if isinstance(windows.get("ema"), dict):
                result.setdefault("ema", {}).update(windows["ema"])
            if isinstance(windows.get("volume"), dict):
                result.setdefault("volume", {}).update(windows["volume"])
            if isinstance(windows.get("volatility"), dict):
                result.setdefault("volatility", {}).update(
                    windows["volatility"])

        features_section = features_cfg.get("features", {})
        if isinstance(features_section, dict):
            result.setdefault("features", {})
            for key, value in features_section.items():
                if isinstance(value, dict):
                    result["features"].setdefault(key, {}).update(value)

        # Liquidity stanza lives under features.liquidity in legacy config
        liquidity = features_section.get("liquidity") if isinstance(
            features_section, dict) else None
        if isinstance(liquidity, dict):
            result.setdefault("liquidity", {}).update(liquidity)

        return result or None

    def _build_macro_sync_from_v2(self, config_v2: ConfigV2) -> Optional[Dict[str, Any]]:
        features_cfg = config_v2.domains.get(
            "features") if config_v2.domains else None
        if isinstance(features_cfg, dict):
            macro_sync = features_cfg.get("macro_sync")
            if isinstance(macro_sync, dict) and macro_sync:
                return macro_sync
        return {"enabled": True, "anchors": ["BTCUSDT", "ETHUSDT"], "window": 60, "emit_abs": False}

    def _build_domain_configuration_from_v2(self, config_v2: ConfigV2, profile: Optional[str]) -> Optional[Dict[str, Any]]:
        modes_cfg = getattr(config_v2, "modes", None)
        if not isinstance(modes_cfg, dict):
            return None
        profiles = modes_cfg.get("profiles", {})
        if not isinstance(profiles, dict) or not profiles:
            return None

        canonical_profile = (profile or "shadow_live").lower()
        target_profile = profiles.get(canonical_profile) or profiles.get(
            "shadow_live") or next(iter(profiles.values()))
        if not isinstance(target_profile, dict):
            return None

        domains = target_profile.get("domains", {})
        if not isinstance(domains, dict):
            return None

        return {domain: {"trading_mode": mode}
                for domain, mode in domains.items()}

    def _flatten_feature_engineering(self, resolved_config: Dict[str, Any]) -> None:
        """Flatten nested feature_engineering configs for Pydantic compatibility."""
        trading_block = resolved_config.get('trading')
        if not isinstance(trading_block, dict):
            return
        fe_cfg = trading_block.get('feature_engineering')
        if not isinstance(fe_cfg, dict):
            return

        flattened: Dict[str, Any] = {}

        if 'enable_new_metrics' in fe_cfg:
            flattened['enable_new_metrics'] = fe_cfg['enable_new_metrics']

        if 'ema' in fe_cfg and isinstance(fe_cfg['ema'], dict):
            flattened['ema_period_short'] = fe_cfg['ema'].get(
                'period_short', 3)
            flattened['ema_period_long'] = fe_cfg['ema'].get('period_long', 7)
        if 'volume' in fe_cfg and isinstance(fe_cfg['volume'], dict):
            flattened['volume_window_sec'] = fe_cfg['volume'].get(
                'window_sec', 60)
            flattened['volume_sma_length'] = fe_cfg['volume'].get(
                'sma_length', 5)
        if 'volatility' in fe_cfg and isinstance(fe_cfg['volatility'], dict):
            flattened['volatility_window_sec'] = fe_cfg['volatility'].get(
                'window_sec', 60)
            flattened['volatility_sma_length'] = fe_cfg['volatility'].get(
                'sma_length', 10)

        features_section = fe_cfg.get('features') if isinstance(
            fe_cfg.get('features'), dict) else None
        if isinstance(features_section, dict):
            ema_feat = features_section.get('ema') if isinstance(
                features_section.get('ema'), dict) else None
            if isinstance(ema_feat, dict):
                flattened['ema_bias_clamp'] = ema_feat.get('bias_clamp', 0.02)
            volume_feat = features_section.get('volume') if isinstance(
                features_section.get('volume'), dict) else None
            if isinstance(volume_feat, dict):
                flattened['volume_spike_cap'] = volume_feat.get(
                    'spike_cap', 3.0)
            vol_feat = features_section.get('volatility') if isinstance(
                features_section.get('volatility'), dict) else None
            if isinstance(vol_feat, dict):
                flattened['volatility_ratio_cap'] = vol_feat.get(
                    'ratio_cap', 3.0)
            liquidity_feat = features_section.get('liquidity') if isinstance(
                features_section.get('liquidity'), dict) else None
            if isinstance(liquidity_feat, dict):
                flattened['liquidity_depth_half'] = liquidity_feat.get(
                    'depth_half', 1000)
                flattened['liquidity_kappa_min'] = liquidity_feat.get(
                    'kappa_min', 0.3)
                flattened['liquidity_kappa_max'] = liquidity_feat.get(
                    'kappa_max', 1.0)
        else:
            flattened.setdefault('ema_bias_clamp', 0.02)
            flattened.setdefault('volume_spike_cap', 3.0)
            flattened.setdefault('volatility_ratio_cap', 3.0)
            flattened.setdefault('liquidity_depth_half', fe_cfg.get(
                'liquidity', {}).get('depth_half', 1000))
            flattened.setdefault('liquidity_kappa_min', 0.3)
            flattened.setdefault('liquidity_kappa_max', 1.0)

        macro_sync_cfg = fe_cfg.get('macro_sync') if isinstance(
            fe_cfg.get('macro_sync'), dict) else None
        if isinstance(macro_sync_cfg, dict):
            flattened['macro_sync_enabled'] = macro_sync_cfg.get(
                'enabled', False)
            flattened['macro_sync_anchors'] = macro_sync_cfg.get(
                'anchors', ["BTCUSDT", "ETHUSDT"])
            flattened['macro_sync_window'] = macro_sync_cfg.get('window', 60)
            trading_block.setdefault('market_data', {}).setdefault(
                'macro_sync', macro_sync_cfg)
        else:
            flattened.setdefault('macro_sync_enabled', False)
            flattened.setdefault('macro_sync_anchors', ["BTCUSDT", "ETHUSDT"])
            flattened.setdefault('macro_sync_window', 60)

        defaults = {
            'ema_period_short': 3,
            'ema_period_long': 7,
            'ema_bias_clamp': 0.02,
            'volume_window_sec': 60,
            'volume_sma_length': 5,
            'volume_spike_cap': 3.0,
            'volatility_window_sec': 60,
            'volatility_sma_length': 10,
            'volatility_ratio_cap': 3.0,
            'liquidity_depth_half': 1000,
            'liquidity_kappa_min': 0.3,
            'liquidity_kappa_max': 1.0,
            'macro_sync_enabled': False,
            'macro_sync_anchors': ["BTCUSDT", "ETHUSDT"],
            'macro_sync_window': 60,
        }
        for key, value in defaults.items():
            flattened.setdefault(key, value)

        trading_block['feature_engineering'] = flattened

    def _ensure_api_defaults(self, resolved_config: Dict[str, Any]) -> None:
        """Fill in placeholder Binance API credentials when legacy YAML is absent."""
        api_cfg = resolved_config.setdefault('binance_api', {})
        env_mappings = {
            'testnet': {
                'key': 'BINANCE_TESTNET_API_KEY',
                'secret': 'BINANCE_TESTNET_API_SECRET',
                'rest': 'BINANCE_TESTNET_REST_URL',
                'default_rest': 'https://testnet.binancefuture.com',
            },
            'live': {
                'key': 'BINANCE_FUTURES_API_KEY_LIVE',
                'secret': 'BINANCE_FUTURES_API_SECRET_LIVE',
                'rest': 'BINANCE_FUTURES_BASE_URL_LIVE',
                'default_rest': 'https://fapi.binance.com',
            },
        }

        mode = (resolved_config.get('trading_mode') or '').lower()
        required_envs = set()
        if 'live' in mode or mode in {'production'}:
            required_envs.add('live')
        if 'testnet' in mode or mode in {'paper', 'sandbox'}:
            required_envs.add('testnet')
        if not required_envs:
            required_envs.add('testnet')

        for env_name, env_keys in env_mappings.items():
            block = api_cfg.get(env_name)
            if block is None and env_name not in required_envs:
                continue

            block = api_cfg.setdefault(env_name, {})
            block.setdefault('api_key', os.environ.get(
                env_keys['key'], None if env_name not in required_envs else f'dev-{env_name}-key'))
            block.setdefault('api_secret', os.environ.get(
                env_keys['secret'], None if env_name not in required_envs else f'dev-{env_name}-secret'))
            block.setdefault('rest_url', os.environ.get(
                env_keys['rest'], env_keys['default_rest']))


_config_instance: Optional[AuroraConfig] = None


def get_config() -> AuroraConfig:
    global _config_instance
    if _config_instance is None:
        loader = ConfigLoader()
        _config_instance = loader.load_config()
    return _config_instance


def reload_config() -> AuroraConfig:
    """Reload Aurora configuration from YAML files (hotreload support)."""
    global _config_instance
    loader = ConfigLoader()
    _config_instance = loader.load_config()
    return _config_instance


def load_config(config_root: Optional[str] = None) -> AuroraConfig:
    """Utility for tests/scripts to load AuroraConfig from a specific config root."""
    config_dir = Path(config_root) if config_root else None
    loader = ConfigLoader(config_dir=config_dir)
    return loader.load_config()
