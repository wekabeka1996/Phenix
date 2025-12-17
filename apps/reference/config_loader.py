#!/usr/bin/env python3
import os
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
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

    def _extract_active_symbols(self, resolved_config: Dict[str, Any]) -> List[str]:
        """Extract list of active/tradable symbols from already-loaded config sources.

        Priority (most explicit first):
        1) trading.symbols_to_track
        2) trading.decision.symbols_to_track
        3) keys(config.aurora_instruments) — CANONICAL SSOT (CFG-AURORA-INSTRUMENTS-SSOT-01)
        4) keys(config.instruments)
        """

        trading = resolved_config.get("trading")
        if not isinstance(trading, dict):
            return []

        symbols_to_track = trading.get("symbols_to_track")
        if isinstance(symbols_to_track, list) and symbols_to_track:
            return [str(s) for s in symbols_to_track]

        decision = trading.get("decision")
        if isinstance(decision, dict):
            decision_symbols = decision.get("symbols_to_track")
            if isinstance(decision_symbols, list) and decision_symbols:
                return [str(s) for s in decision_symbols]

        # CFG-AURORA-INSTRUMENTS-SSOT-01: Read from root config.aurora_instruments (CANONICAL)
        aurora_instruments = resolved_config.get("aurora_instruments")
        if isinstance(aurora_instruments, dict) and aurora_instruments:
            return [str(s) for s in aurora_instruments.keys()]

        instruments = resolved_config.get("instruments")
        if isinstance(instruments, dict) and instruments:
            return [str(s) for s in instruments.keys()]

        return []

    def _validate_ssot_conflicts(self, resolved_config: Dict[str, Any]) -> None:
        """
        CFG-TRADING-YAML-BURN-DOWN-01: Validate that SSOT files have priority.
        
        Check if trading.yaml contains duplicate sections that conflict with SSOT:
        - domains.yaml → config.domains (SSOT)
        - instruments.yaml → config.instruments (SSOT)
        
        Policy:
        - If strict_config_conflicts=true (env STRICT_CONFIG_CONFLICTS=1) → FAIL
        - Otherwise → WARNING only (default)
        
        Raises:
            ValueError: If conflicts detected in strict mode
        """
        import os
        
        strict_mode = os.getenv("STRICT_CONFIG_CONFLICTS", "0").strip() in ("1", "true", "True", "yes")
        
        conflicts_found = []
        
        # Check 1: domains conflict
        canonical_domains = resolved_config.get("domains", {})
        trading_block = resolved_config.get("trading", {})
        
        if isinstance(trading_block, dict):
            # Note: trading.domains is now a MIRROR, but check if it was DIFFERENT before mirror
            # We already handle this in load_config, but this is extra validation
            pass
        
        # Check 2: instruments conflict (already handled by load_config warnings)
        # This method serves as a central audit point for future SSOT conflicts
        
        # Check 3: NEW - detect if trading.yaml has deprecated SSOT-duplicating sections
        # These sections should NOT exist in trading.yaml anymore
        deprecated_ssot_keys = [
            # Format: (trading.yaml_path, ssot_file, description)
            # Example: ("trading.aurora_instruments", "instruments.yaml", "Per-symbol Aurora params"),
        ]
        
        # For now, this is a placeholder for future burn-down phases
        # Current phase: audit only
        
        if conflicts_found:
            msg = "⚠️  CONFIG CONFLICTS detected:\n" + "\n".join(conflicts_found)
            if strict_mode:
                raise ValueError(msg)
            else:
                LOG.warning(msg)

    def _fail_fast_validate_instruments_precision(self, resolved_config: Dict[str, Any]) -> None:
        """Startup fail-fast: ensure tick_size & step_size exist for active symbols."""

        active_symbols = self._extract_active_symbols(resolved_config)
        if not active_symbols:
            return

        instruments = resolved_config.get("instruments")
        if not isinstance(instruments, dict):
            raise ValueError(
                "Missing instruments precision: instruments map is missing or invalid"
            )

        missing: list[str] = []
        for symbol in active_symbols:
            spec = instruments.get(symbol)
            if not isinstance(spec, dict):
                spec = None

            if spec is None:
                missing.append(f"{symbol} missing instrument spec")
                continue

            for field in ("tick_size", "step_size"):
                raw = spec.get(field)
                if raw is None:
                    missing.append(f"{symbol} missing {field}")
                    continue
                try:
                    if float(raw) <= 0:
                        missing.append(f"{symbol} missing {field}")
                except (TypeError, ValueError):
                    missing.append(f"{symbol} missing {field}")

        if missing:
            missing_sorted = "; ".join(sorted(missing))
            raise ValueError(f"Missing instruments precision: {missing_sorted}")

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
        except FileNotFoundError as e:
            LOG.error(f"Config file error: {e}")
            raise
        
        # Load domains.yaml (optional if trading.yaml has domains)
        domains_config: Dict[str, Any] = {}
        try:
            domains_config = self._load_yaml("domains.yaml")
        except FileNotFoundError:
            LOG.info("domains.yaml not found, will check trading.domains as fallback")
        
        # =========================================================================
        # DEPRECATED FILE DETECTION (CFG-FEATURES-REGIME-SSOT-04)
        # =========================================================================
        # features.yaml is ORPHANED (not loaded, duplicate of domains.yaml)
        # Detect its presence and fail/warn based on strict mode
        # =========================================================================
        import os
        strict_mode = os.getenv("STRICT_CONFIG_CONFLICTS", "0").strip() in ("1", "true", "True", "yes")
        
        features_yaml_path = self.config_dir / "features.yaml"
        if features_yaml_path.exists():
            msg = (
                "⚠️  DEPRECATED: features.yaml detected! "
                "This file is NOT loaded by ConfigLoader (orphaned config). "
                "Feature engineering config is read from domains.yaml (SSOT). "
                "Action required: Remove features.yaml or migrate to domains.yaml."
            )
            
            if strict_mode:
                raise ValueError(msg)
            else:
                LOG.warning(msg)

        # Merge: trading_config (source) → system_config (destination)
        merged_config: Dict[str, Any] = {}
        deep_merge(system_config, merged_config)  # Copy system first
        deep_merge(trading_config, merged_config)  # Overlay trading
        deep_merge(regime_config, merged_config)   # Overlay regime (models, hmm, etc.)
        
        # ============================================================================
        # CANONICAL domains.yaml LOGIC (CFG-DOMAINS-STEP-01)
        # ============================================================================
        # ПРАВИЛО: domains.yaml → ЄДИНЕ ДЖЕРЕЛО ПРАВДИ для AuroraConfig.domains
        # - domains.yaml завжди має пріоритет
        # - trading.domains (якщо є) — DEPRECATED mirror, НЕ використовується
        # ============================================================================
        
        legacy_used = False
        
        # 1. Якщо domains.yaml має 'domains' ключ → use it as canonical
        if 'domains' in domains_config:
            merged_config['domains'] = domains_config['domains']
        # 2. Якщо domains.yaml — це самі дані (без обгортки), merge all content as domains
        elif domains_config:
            merged_config['domains'] = domains_config
        else:
            # CFG-TRADING-YAML-BURN-DOWN-02: FAIL FAST, no fallback to trading.domains
            raise ValueError(
                "❌ CRITICAL: No domains configuration found! "
                "Expected config/aurora/domains.yaml (SSOT) with domain configs."
            )
        
        # CFG-TRADING-YAML-BURN-DOWN-02: Detect deprecated trading.domains and FAIL in strict mode
        if 'trading' in merged_config and 'domains' in merged_config.get('trading', {}):
            import os
            strict_mode = os.getenv("STRICT_CONFIG_CONFLICTS", "0").strip() in ("1", "true", "True", "yes")
            
            msg = (
                "⚠️  DEPRECATED: trading.domains detected! "
                "This section is IGNORED. SSOT is config/aurora/domains.yaml. "
                "Remove trading.domains from trading.yaml."
            )
            
            if strict_mode:
                raise ValueError(msg)
            else:
                LOG.warning(msg)
        
        # Consistency check
        if not merged_config.get('domains'):
            raise ValueError("❌ CRITICAL: domains config is empty after merge!")
        
        # ============================================================================
        # END CANONICAL domains.yaml LOGIC
        # ============================================================================

        # =========================================================================
        # CANONICAL instruments.yaml LOGIC (CFG-INSTRUMENTS-AURORA-SSOT-01)
        # =========================================================================
        # ПРАВИЛО: config/aurora/instruments.yaml → ЄДИНЕ ДЖЕРЕЛО ПРАВДИ для AuroraConfig.instruments
        # - instruments.yaml завжди має пріоритет
        # - trading.instruments — DEPRECATED mirror для legacy runtime
        # =========================================================================

        instruments_yaml_present = False
        instruments_payload: Dict[str, Any] = {}
        try:
            instruments_raw = self._load_yaml("instruments.yaml")
            instruments_yaml_present = True

            if isinstance(instruments_raw, dict) and "instruments" in instruments_raw and isinstance(
                instruments_raw.get("instruments"), dict
            ):
                instruments_payload = instruments_raw["instruments"]
            else:
                instruments_payload = instruments_raw if isinstance(instruments_raw, dict) else {}
        except FileNotFoundError:
            instruments_yaml_present = False

        # Canonical mapping: merged_config['instruments']
        if instruments_yaml_present:
            merged_config["instruments"] = instruments_payload
        else:
            # CFG-TRADING-YAML-BURN-DOWN-02: FAIL FAST, no fallback to trading.instruments
            raise ValueError(
                "❌ CRITICAL: No instruments configuration found! "
                "Expected config/aurora/instruments.yaml (SSOT)."
            )

        # CFG-TRADING-YAML-BURN-DOWN-02: Detect deprecated trading.instruments and FAIL in strict mode
        trading_block = merged_config.setdefault("trading", {})
        if not isinstance(trading_block, dict):
            trading_block = {}
            merged_config["trading"] = trading_block

        trading_instruments = trading_block.get("instruments")
        
        if isinstance(trading_instruments, dict) and trading_instruments:
            import os
            strict_mode = os.getenv("STRICT_CONFIG_CONFLICTS", "0").strip() in ("1", "true", "True", "yes")
            
            msg = (
                "⚠️  DEPRECATED: trading.instruments detected! "
                "This section is IGNORED. SSOT is config/aurora/instruments.yaml. "
                "Remove trading.instruments from trading.yaml."
            )
            
            if strict_mode:
                raise ValueError(msg)
            else:
                LOG.warning(msg)

        if not merged_config.get("instruments"):
            raise ValueError("❌ CRITICAL: instruments config is empty after merge!")

        # =========================================================================
        # END CANONICAL instruments.yaml LOGIC
        # =========================================================================

        # =========================================================================
        # CANONICAL strategies.yaml LOGIC (CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION)
        # =========================================================================
        # ПРАВИЛО: config/aurora/strategies.yaml → ЄДИНЕ ДЖЕРЕЛО ПРАВДИ для strategy assignments + arbitration
        # Strict mode: missing file → ValueError
        # =========================================================================
        import os
        strict_mode = os.getenv("STRICT_CONFIG_CONFLICTS", "0").strip() in ("1", "true", "True", "yes")
        
        strategies_yaml_present = False
        strategies_payload: Dict[str, Any] = {}
        try:
            strategies_raw = self._load_yaml("strategies.yaml")
            strategies_yaml_present = True
            
            if isinstance(strategies_raw, dict):
                strategies_payload = strategies_raw
        except FileNotFoundError:
            strategies_yaml_present = False
        
        # Fail-closed in strict mode
        if not strategies_yaml_present:
            msg = (
                "⚠️  strategies.yaml NOT found! "
                "Expected config/aurora/strategies.yaml for strategy registry (assignments + arbitration)."
            )
            if strict_mode:
                raise ValueError(msg)
            else:
                LOG.warning(msg)
                merged_config["strategies_registry"] = None
        else:
            merged_config["strategies_registry"] = strategies_payload
        
        # =========================================================================
        # END CANONICAL strategies.yaml LOGIC
        # =========================================================================

        # =========================================================================
        # REGISTRY-DRIVEN STRATEGY PROFILE LOADING (CFG-STRATEGIES-SSOT-03)
        # =========================================================================
        # ПРАВИЛО: Завантажувати strategy profiles YAML ЛИШЕ за strategies_registry.assignments
        # - Не сканувати директорію
        # - Strict: strategy_id в assignments але файл відсутній → ValueError
        # =========================================================================
        
        strategy_configs: Dict[str, Dict[str, Any]] = {}
        
        if strategies_payload and "assignments" in strategies_payload:
            assignments = strategies_payload["assignments"]
            if isinstance(assignments, dict):
                # Collect unique strategy_ids from all assignments
                strategy_ids = set()
                for symbol, strat_list in assignments.items():
                    if isinstance(strat_list, list):
                        strategy_ids.update(strat_list)
                
                # Load each strategy profile from config/aurora/strategies/{id}.yaml
                strategies_dir = self.config_dir / "strategies"
                for strategy_id in strategy_ids:
                    profile_path = strategies_dir / f"{strategy_id}.yaml"
                    
                    if not profile_path.exists():
                        # FAIL-CLOSED: assigned strategy missing profile → ValueError
                        raise ValueError(
                            f"❌ CRITICAL: Strategy '{strategy_id}' assigned in strategies.yaml "
                            f"but profile missing: {profile_path}. "
                            f"Expected: config/aurora/strategies/{strategy_id}.yaml"
                        )
                    
                    try:
                        with open(profile_path, "r", encoding="utf-8-sig", errors="replace") as f:
                            profile_raw = yaml.safe_load(f)
                        
                        if isinstance(profile_raw, dict):
                            # Support both wrapped format ({strategy_id: {...}}) and flat
                            if strategy_id in profile_raw:
                                strategy_configs[strategy_id] = profile_raw[strategy_id]
                            else:
                                strategy_configs[strategy_id] = profile_raw
                            
                            LOG.info(f"✅ Loaded strategy profile: {strategy_id} from {profile_path}")
                    except Exception as e:
                        raise ValueError(
                            f"❌ CRITICAL: Failed to parse strategy profile '{strategy_id}' "
                            f"from {profile_path}: {e}"
                        )
        
        # Inject strategy configs at root level (e.g., mean_reversion_1m)
        for strategy_id, config_data in strategy_configs.items():
            merged_config[strategy_id] = config_data
        
        # =========================================================================
        # END REGISTRY-DRIVEN STRATEGY PROFILE LOADING
        # =========================================================================

        # =========================================================================
        # CANONICAL aurora_instruments.yaml LOGIC (CFG-AURORA-INSTRUMENTS-SSOT-01-FIXPACK)
        # =========================================================================
        # ПРАВИЛО: config/aurora/aurora_instruments.yaml → ЄДИНЕ ДЖЕРЕЛО ПРАВДИ для AuroraConfig.aurora_instruments
        # - aurora_instruments.yaml завжди має пріоритет
        # - trading.aurora_instruments — DEPRECATED (fail-closed в strict mode)
        # =========================================================================
        
        # STEP 1: Detect deprecated trading.aurora_instruments in RAW trading_config (BEFORE Pydantic parse)
        if isinstance(trading_config, dict) and "aurora_instruments" in trading_config:
            trading_aurora_instruments = trading_config.get("aurora_instruments")
            if isinstance(trading_aurora_instruments, dict) and trading_aurora_instruments:
                msg = (
                    "⚠️  DEPRECATED: trading.aurora_instruments detected! "
                    "This section is IGNORED. SSOT is config/aurora/aurora_instruments.yaml. "
                    "Remove trading.aurora_instruments from trading.yaml."
                )
                if strict_mode:
                    raise ValueError(msg)
                else:
                    LOG.warning(msg)

        # STEP 2: Load aurora_instruments.yaml (CANONICAL SSOT)
        aurora_instruments_yaml_present = False
        aurora_instruments_payload: Dict[str, Any] = {}
        try:
            aurora_instruments_raw = self._load_yaml("aurora_instruments.yaml")
            aurora_instruments_yaml_present = True

            # Support both wrapped and flat formats
            if isinstance(aurora_instruments_raw, dict):
                if "aurora_instruments" in aurora_instruments_raw and isinstance(
                    aurora_instruments_raw.get("aurora_instruments"), dict
                ):
                    aurora_instruments_payload = aurora_instruments_raw["aurora_instruments"]
                else:
                    # Flat format (symbol keys at root)
                    aurora_instruments_payload = aurora_instruments_raw
        except FileNotFoundError:
            aurora_instruments_yaml_present = False

        # STEP 3: Fail-closed policy in strict mode
        if not aurora_instruments_yaml_present:
            msg = (
                "⚠️  aurora_instruments.yaml NOT found! "
                "Expected config/aurora/aurora_instruments.yaml for per-symbol Aurora overrides."
            )
            if strict_mode:
                raise ValueError(msg)
            else:
                LOG.warning(msg)
                merged_config["aurora_instruments"] = {}
        else:
            merged_config["aurora_instruments"] = aurora_instruments_payload

        # =========================================================================
        # END CANONICAL aurora_instruments.yaml LOGIC
        # =========================================================================

        # Resolve environment variables
        resolved_config = self._resolve_env_vars(merged_config)

        # Apply mode-specific decision overrides
        self._resolve_mode_overrides(resolved_config)

        # Startup fail-fast: precision check for active symbols
        self._fail_fast_validate_instruments_precision(resolved_config)

        # CFG-TRADING-YAML-BURN-DOWN-01: Check for SSOT conflicts
        self._validate_ssot_conflicts(resolved_config)

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
