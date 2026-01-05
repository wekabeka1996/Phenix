#!/usr/bin/env python3
import os
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path: str | Path | None = None, *args, **kwargs):  # type: ignore[no-redef]
        """Minimal .env loader fallback (avoids hard dependency on python-dotenv).

        Supports simple KEY=VALUE lines with optional quotes; ignores comments/blank lines.
        """
        if dotenv_path is None:
            return False
        try:
            p = Path(dotenv_path)
            if not p.exists():
                return False
            for raw_line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export ") :].lstrip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if not key:
                    continue
                os.environ.setdefault(key, value)
            return True
        except Exception:
            return False
from pydantic import ValidationError

from .config_models import AuroraConfig as PydanticAuroraConfig
from .config_models import SystemRuntimeMeta
from .config_contract import ConfigContractError

LOG = logging.getLogger(__name__)


def deep_merge(source, destination, *, _path: str = "", _provenance: Optional[Dict[str, str]] = None, _source_name: Optional[str] = None):
    """Deep merge ``source`` dict into ``destination`` dict (fail-closed on type conflicts)."""
    if not isinstance(destination, dict):
        raise ConfigContractError(
            path=_path or "root",
            why=f"Invalid config merge target: expected dict, got {type(destination).__name__}",
        )

    for key, value in source.items():
        key_str = str(key)
        path = f"{_path}.{key_str}" if _path else key_str

        if isinstance(value, dict):
            if key not in destination:
                destination[key] = {}
            else:
                existing = destination.get(key)
                if existing is None:
                    raise ConfigContractError(
                        path=path,
                        why=(
                            "Type conflict during config merge: cannot deep-merge a mapping into null. "
                            "Remove the `: null` value or replace it with an explicit mapping `{}`."
                        ),
                    )
                if not isinstance(existing, dict):
                    raise ConfigContractError(
                        path=path,
                        why=(
                            f"Type conflict during config merge: cannot deep-merge a mapping into "
                            f"{type(existing).__name__}."
                        ),
                    )

            node = destination[key]
            deep_merge(value, node, _path=path, _provenance=_provenance, _source_name=_source_name)
        else:
            destination[key] = value
            if _provenance is not None and _source_name is not None:
                _provenance[path] = _source_name

    return destination


# Legacy wrapper for backwards compatibility
class AuroraConfig(PydanticAuroraConfig):
    """
    AuroraConfig wrapper that provides Pydantic V2 validation with strict fail-closed behavior.

    All config access must use typed attributes directly (e.g., config.strategies.aurora.decision.signal_threshold).
    No .get() fallback interface - missing fields cause AttributeError at startup.
    """

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
            required = (
                "system.yaml",
                "trading.yaml",
                "regime.yaml",
                "domains.yaml",
                "instruments.yaml",
                "strategies.yaml",
            )
            if tests_dir.exists() and all((tests_dir / f).exists() for f in required):
                self.config_dir = tests_dir
            else:
                self.config_dir = default_dir
        
        # CFG-RUNTIME-BOOTSTRAP-07: Store config name for diagnostic logging
        self.config_name = "aurora"  # Default config name
        
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            
        self.provenance_map: Dict[str, str] = {}

    @staticmethod
    def _flatten_leaf_paths(data: Any, *, prefix: str = "") -> Dict[str, Any]:
        """Flatten a nested mapping into leaf dot-paths for duplicate detection.

        Dicts are traversed recursively; lists/scalars are treated as leaf values.
        """
        out: Dict[str, Any] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                key = str(k)
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(v, dict):
                    out.update(ConfigLoader._flatten_leaf_paths(v, prefix=path))
                else:
                    out[path] = v
        else:
            if prefix:
                out[prefix] = data
        return out

    def _fail_on_duplicate_paths(self, *, sources: Dict[str, Dict[str, Any]]) -> None:
        """TASK47: crash-on-duplicate config paths across YAML fragments (fail-closed)."""
        seen: Dict[str, Dict[str, Any]] = {}
        for src_name, src_dict in sources.items():
            flat = self._flatten_leaf_paths(src_dict)
            for path, val in flat.items():
                bucket = seen.setdefault(path, {})
                bucket[src_name] = val

        dupes = {path: srcs for path, srcs in seen.items() if len(srcs) > 1}
        if not dupes:
            return

        lines: list[str] = []
        for path in sorted(dupes.keys())[:25]:
            srcs = ", ".join(sorted(dupes[path].keys()))
            lines.append(f"- {path}: {srcs}")
        more = "" if len(dupes) <= 25 else f"\n... and {len(dupes) - 25} more"
        raise ConfigContractError(
            path="config_loader.duplicates",
            why=(
                "Duplicate config paths detected across YAML sources (SSOT violation). "
                "Move each parameter to exactly one file.\n"
                + "\n".join(lines)
                + more
            ),
        )
    
    @staticmethod
    def _get_strict_mode() -> bool:
        """
        Get strict config validation mode.
        
        CFG-FREEZE-SSOT-06: Strict mode by default (opt-out for migrations).
        - Default: STRICT (STRICT_CONFIG_CONFLICTS not set or ="1")
        - Opt-out: export STRICT_CONFIG_CONFLICTS=0
        
        Returns:
            True if strict mode enabled (default), False otherwise.
        """
        return os.getenv("STRICT_CONFIG_CONFLICTS", "1").strip() in ("1", "true", "True", "yes")

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

    @staticmethod
    def _extract_system_meta(system_config: Dict[str, Any], regime_config: Dict[str, Any]) -> Dict[str, Any]:
        """Isolate service/runtime metadata from root to allow extra='forbid'."""

        meta: Dict[str, Any] = {}

        if isinstance(system_config, dict):
            mapping = {
                "config_version": "system_config_version",
                "sequential_tests": "sequential_tests",
                "risk_core": "risk_core",
                "kelly": "kelly",
                "calibrator": "calibrator",
                "hawkes": "hawkes",
                "hardening": "hardening",
                "position_tracking": "position_tracking",
            }
            for src_key, dst_key in mapping.items():
                if src_key in system_config:
                    meta[dst_key] = system_config.pop(src_key)

        # Ensure system_meta always contains required keys (SystemMetaConfig is strict).
        # These are runtime/meta-only and must not participate in SSOT dedup checks.
        if "position_tracking" not in meta:
            meta["position_tracking"] = {}
        if "hotreload_whitelist" not in meta:
            # Source of truth is regime.yaml root.hotreload_whitelist (keep it there; copy for meta).
            wl = []
            if isinstance(regime_config, dict):
                wl_val = regime_config.get("hotreload_whitelist")
                if isinstance(wl_val, list):
                    wl = wl_val
            meta["hotreload_whitelist"] = wl

        if isinstance(regime_config, dict) and "config_version" in regime_config:
            meta["regime_config_version"] = regime_config.pop("config_version")

        return meta

    def _merge_config_fragments(
        self,
        *,
        system_config: Dict[str, Any],
        trading_config: Dict[str, Any],
        regime_config: Dict[str, Any],
        domains_config: Dict[str, Any],
        system_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge YAML fragments into a single dict WITHOUT schema-compensation hydration.

        TASK28 invariant:
        - No setdefault-injection of optional/required keys to satisfy schema
        - Only SSOT canonical merges + allowlisted legacy migration happens elsewhere
        """

        # Merge: trading_config (source) → system_config (destination)
        merged_config: Dict[str, Any] = {}
        deep_merge(system_config, merged_config, _provenance=self.provenance_map, _source_name="system.yaml")
        deep_merge(trading_config, merged_config, _provenance=self.provenance_map, _source_name="trading.yaml")
        deep_merge(regime_config, merged_config, _provenance=self.provenance_map, _source_name="regime.yaml")

        # =========================================================================
        # CANONICAL domains.yaml LOGIC (CFG-DOMAINS-STEP-01)
        # =========================================================================
        if 'domains' in domains_config:
            merged_config['domains'] = domains_config['domains']
            flat_domains = self._flatten_leaf_paths(domains_config['domains'], prefix="domains")
            for p in flat_domains: self.provenance_map[p] = "domains.yaml"
        elif domains_config:
            merged_config['domains'] = domains_config
            flat_domains = self._flatten_leaf_paths(domains_config, prefix="domains")
            for p in flat_domains: self.provenance_map[p] = "domains.yaml"
        else:
            raise ValueError(
                "❌ CRITICAL: No domains configuration found! "
                "Expected config/aurora/domains.yaml (SSOT) with domain configs."
            )

        if 'trading' in merged_config and 'domains' in (merged_config.get('trading', {}) or {}):
            msg = (
                "⚠️  DEPRECATED: trading.domains detected! "
                "This section is IGNORED. SSOT is config/aurora/domains.yaml. "
                "Remove trading.domains from trading.yaml."
            )
            raise ConfigContractError(path="trading.domains", why=msg)

        if not merged_config.get('domains'):
            raise ValueError("❌ CRITICAL: domains config is empty after merge!")

        # =========================================================================
        # CANONICAL instruments.yaml LOGIC (CFG-INSTRUMENTS-AURORA-SSOT-01)
        # =========================================================================

        instruments_raw = self._load_yaml("instruments.yaml")
        if isinstance(instruments_raw, dict) and "instruments" in instruments_raw and isinstance(
            instruments_raw.get("instruments"), dict
        ):
            merged_config["instruments"] = instruments_raw["instruments"]
            flat_inst = self._flatten_leaf_paths(instruments_raw["instruments"], prefix="instruments")
            for p in flat_inst: self.provenance_map[p] = "instruments.yaml"
        else:
            merged_config["instruments"] = instruments_raw if isinstance(instruments_raw, dict) else {}
            flat_inst = self._flatten_leaf_paths(merged_config["instruments"], prefix="instruments")
            for p in flat_inst: self.provenance_map[p] = "instruments.yaml"

        if not merged_config.get("instruments"):
            raise ValueError(
                "❌ CRITICAL: No instruments configuration found or instruments is empty! "
                "Expected config/aurora/instruments.yaml (SSOT)."
            )

        trading_block = merged_config.get("trading")
        if not isinstance(trading_block, dict):
            raise ConfigContractError(
                path="trading",
                why="Invalid or missing trading block at root (expected mapping).",
            )

        trading_instruments = trading_block.get("instruments")
        if isinstance(trading_instruments, dict) and trading_instruments:
            msg = (
                "⚠️  DEPRECATED: trading.instruments detected! "
                "This section is IGNORED. SSOT is config/aurora/instruments.yaml. "
                "Remove trading.instruments from trading.yaml."
            )
            raise ConfigContractError(path="trading.instruments", why=msg)

        # =========================================================================
        # CANONICAL strategies.yaml LOGIC (CFG-STRATEGIES-SSOT-01-REGISTRY-ARBITRATION)
        # =========================================================================
        strategies_raw: Dict[str, Any] = {}
        try:
            raw = self._load_yaml("strategies.yaml")
            strategies_raw = raw if isinstance(raw, dict) else {}
        except FileNotFoundError as e:
            raise ConfigContractError(
                path="strategies.yaml",
                why=(
                    "❌ CRITICAL: strategies.yaml missing. "
                    "This file is the SSOT strategy assignment registry and is mandatory."
                ),
            ) from e
        if not strategies_raw:
            raise ConfigContractError(
                path="strategies.yaml",
                why=(
                    "❌ CRITICAL: strategies.yaml missing/empty. "
                    "This file is the SSOT strategy assignment registry and is mandatory."
                ),
            )
        merged_config["strategies_registry"] = strategies_raw

        # =========================================================================
        # REGISTRY-DRIVEN STRATEGY PROFILE LOADING (CFG-STRATEGIES-SSOT-03)
        # =========================================================================

        strategy_configs: Dict[str, Dict[str, Any]] = {}
        if strategies_raw and "assignments" in strategies_raw:
            assignments = strategies_raw.get("assignments")
            if isinstance(assignments, dict):
                strategy_ids = set()
                for symbol, strat_list in assignments.items():
                    if isinstance(strat_list, list):
                        strategy_ids.update(strat_list)

                strategies_dir = self.config_dir / "strategies"
                for strategy_id in strategy_ids:
                    profile_path = strategies_dir / f"{strategy_id}.yaml"
                    if not profile_path.exists():
                        raise ValueError(
                            f"❌ CRITICAL: Strategy '{strategy_id}' assigned in strategies.yaml "
                            f"but profile missing: {profile_path}. "
                            f"Expected: config/aurora/strategies/{strategy_id}.yaml"
                        )

                    with open(profile_path, "r", encoding="utf-8-sig", errors="replace") as f:
                        profile_raw = yaml.safe_load(f)

                    if isinstance(profile_raw, dict):
                        data_to_merge = profile_raw[strategy_id] if strategy_id in profile_raw else profile_raw
                        strategy_configs[strategy_id] = data_to_merge
                        
                        flat_strat = self._flatten_leaf_paths(data_to_merge, prefix=f"strategies.{strategy_id}")
                        for p in flat_strat:
                            self.provenance_map[p] = f"strategies/{strategy_id}.yaml"
                        
                        LOG.info(f"✅ Loaded strategy profile: {strategy_id} from {profile_path}")

        # Canonical runtime namespace (CFG-STRATEGY-SSOT-FREEZE-03)
        merged_config["strategies"] = strategy_configs

        # Attach system_meta under dedicated namespace (no runtime injection here)
        merged_config["system_meta"] = system_meta

        return merged_config

    def _inject_runtime_meta(self, config: AuroraConfig) -> AuroraConfig:
        """Inject runtime-only metadata AFTER successful validation."""
        runtime = SystemRuntimeMeta(config_name=self.config_name, config_dir=str(self.config_dir))
        return config.model_copy(
            update={
                "system_meta": config.system_meta.model_copy(update={"runtime": runtime})
            }
        )

    def _resolve_mode_overrides(self, config: Dict[str, Any]) -> None:
        """Apply mode-specific decision overrides from strategies.aurora.decision[mode] → decision.

        This resolver activates profile-based configs:
        - strategies.aurora.decision.testnet.* → decision.* (when trading_mode=testnet)
        - strategies.aurora.decision.production.* → decision.* (when trading_mode=production)

        ALSO applies risk[mode] → risk.trading_allowed_thresholds for risk gates.

        Preserves original decision.{testnet,production} blocks for documentation.
        """
        mode = config.get("trading_mode", "production")
        trading = config.get("trading", {})
        risk = trading.get("risk", {})

        strategies = config.get("strategies", {})
        aurora = strategies.get("aurora", {}) if isinstance(strategies, dict) else {}
        decision = aurora.get("decision", {}) if isinstance(aurora, dict) else {}

        if not isinstance(decision, dict):
            return

        mode_overrides = decision.get(mode, {})
        if not isinstance(mode_overrides, dict):
            return

        if mode_overrides:
            LOG.info(
                f"[mode-resolver] Applying '{mode}' mode decision overrides")
            for key, value in mode_overrides.items():
                # FAIL-CLOSED: never override required fields with null.
                # If an override key is present but null, treat it as "no override".
                if value is None:
                    continue
                old_val = decision.get(key)
                decision[key] = value
                if old_val is not None:
                    LOG.debug(f"  {key}: {old_val} → {value}")
                else:
                    LOG.debug(f"  {key}: (new) → {value}")

        # TASK28: Hybrid mode SSOT wiring (live data + testnet execution).
        # Keep this in the loader to avoid relying on repo-default YAML values.
        if mode == "hybrid_live_data_testnet_exec" and isinstance(trading, dict):
            dc = trading.get("domain_configuration")
            if not isinstance(dc, dict):
                dc = {}
                trading["domain_configuration"] = dc

            def _ensure_domain(name: str, trading_mode: str) -> None:
                block = dc.get(name)
                if not isinstance(block, dict):
                    block = {}
                    dc[name] = block
                block["trading_mode"] = trading_mode

            _ensure_domain("market_data", "live")
            _ensure_domain("feature_engineering", "live")
            _ensure_domain("decision_making", "live")
            _ensure_domain("audit_trail", "live")
            _ensure_domain("risk_management", "testnet")
            _ensure_domain("execution_position", "testnet")

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
        1) keys(strategies_registry.assignments) (SSOT)
        2) trading.symbols_to_track (derived from SSOT unless explicitly set)
        3) keys(config.instruments)
        """

        sr = resolved_config.get("strategies_registry")
        if isinstance(sr, dict):
            assignments = sr.get("assignments")
            if isinstance(assignments, dict) and assignments:
                return [str(s) for s in assignments.keys()]

        trading = resolved_config.get("trading")
        if isinstance(trading, dict):
            symbols_to_track = trading.get("symbols_to_track")
            if isinstance(symbols_to_track, list) and symbols_to_track:
                return [str(s) for s in symbols_to_track]

        instruments = resolved_config.get("instruments")
        if isinstance(instruments, dict) and instruments:
            return [str(s) for s in instruments.keys()]

        return []

    def _apply_trading_symbols_to_track_ssot(self, resolved_config: Dict[str, Any]) -> None:
        """Ensure trading.symbols_to_track exists and is SSOT-consistent.

        Canonical rule (CFG-STRATEGY-SSOT-FREEZE-03):
        - SSOT source for tracked symbols is strategies.yaml assignments keys.
        - trading.symbols_to_track may be explicitly set, but must match SSOT in strict mode.
        """
        if not isinstance(resolved_config, dict):
            return

        trading = resolved_config.get("trading")
        if not isinstance(trading, dict):
            return

        sr = resolved_config.get("strategies_registry")
        assignments: dict[str, Any] = {}
        if isinstance(sr, dict):
            a = sr.get("assignments")
            if isinstance(a, dict):
                assignments = a

        ssot_symbols = [str(s) for s in assignments.keys()] if assignments else []
        existing = trading.get("symbols_to_track")
        existing_symbols: list[str] = []
        if isinstance(existing, list) and existing:
            existing_symbols = [str(s) for s in existing]

        strict_mode = self._get_strict_mode()

        if ssot_symbols:
            if existing_symbols and set(existing_symbols) != set(ssot_symbols):
                msg = (
                    "SSOT conflict: trading.symbols_to_track disagrees with strategies.yaml assignments. "
                    f"trading.symbols_to_track={sorted(set(existing_symbols))} "
                    f"strategies.yaml(assignments)={sorted(set(ssot_symbols))}. "
                    "Fix: remove trading.symbols_to_track or make it match assignments keys."
                )
                if strict_mode:
                    raise ConfigContractError(path="trading.symbols_to_track", why=msg)
                LOG.warning("⚠️  %s", msg)
                existing_symbols = []

            if not existing_symbols:
                trading["symbols_to_track"] = sorted(set(ssot_symbols))
                self.provenance_map["trading.symbols_to_track"] = "strategies.yaml"
                resolved_config["trading"] = trading
                return

            trading["symbols_to_track"] = sorted(set(existing_symbols))
            resolved_config["trading"] = trading
            return

        # No assignments present: require explicit trading.symbols_to_track (fail-closed).
        if not existing_symbols:
            raise ConfigContractError(
                path="trading.symbols_to_track",
                why=(
                    "Missing trading.symbols_to_track and strategies.yaml assignments is empty. "
                    "Provide explicit trading.symbols_to_track or add assignments."
                ),
            )
        trading["symbols_to_track"] = sorted(set(existing_symbols))
        resolved_config["trading"] = trading

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
        
        strict_mode = self._get_strict_mode()
        
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
        """Startup fail-fast: ensure constraints exist for active symbols.

        SIZING-MARGIN-FIRST-SSOT-02 depends on:
        - tick_size, step_size
        - min_qty, min_notional
        """

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

            for field in ("tick_size", "step_size", "min_qty", "min_notional"):
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

    def _validate_execution_config_for_live(self, resolved_config: Dict[str, Any]) -> None:
        """TASK47c-A: Fail-closed validation for LIVE execution.
        
        Validates that all active symbols have complete execution config:
        - margin_mode (isolated | cross)
        - target_leverage (1-125)
        - leverage_policy (verify_only | set_and_verify)
        - max_notional_utilization (0.0-1.0)
        
        This is MANDATORY for LIVE execution. Missing any field → ValueError (startup crash).
        
        Raises:
            ValueError: If any active symbol is missing execution fields
        """
        active_symbols = self._extract_active_symbols(resolved_config)
        if not active_symbols:
            return
        
        instruments = resolved_config.get("instruments")
        if not isinstance(instruments, dict):
            raise ValueError(
                "LIVE execution fail-closed: instruments map is missing or invalid"
            )
        
        required_fields = ("margin_mode", "target_leverage", "leverage_policy", "max_notional_utilization")
        missing: list[str] = []
        
        for symbol in active_symbols:
            spec = instruments.get(symbol)
            if not isinstance(spec, dict):
                missing.append(f"{symbol} missing instrument spec")
                continue
            
            # Check for execution config (can be at root level or nested under 'execution')
            execution = spec.get("execution", spec)
            
            for field in required_fields:
                if execution.get(field) is None:
                    missing.append(f"{symbol} missing execution.{field}")
        
        if missing:
            missing_sorted = "; ".join(sorted(missing[:10]))  # Limit to first 10
            more = f" (and {len(missing) - 10} more)" if len(missing) > 10 else ""
            raise ValueError(
                f"LIVE execution fail-closed: Missing required execution config. "
                f"All active symbols need margin_mode, target_leverage, leverage_policy, max_notional_utilization. "
                f"Missing: {missing_sorted}{more}"
            )

    def _validate_sizing_config_for_live(self, resolved_config: Dict[str, Any]) -> None:
        """SIZING-MARGIN-FIRST-SSOT-02: Fail-closed validation for LIVE sizing SSOT.

        Validates that all active symbols have:
        - sizing.margin_pct in (0, 1]
        """
        active_symbols = self._extract_active_symbols(resolved_config)
        if not active_symbols:
            return

        instruments = resolved_config.get("instruments")
        if not isinstance(instruments, dict):
            raise ValueError("LIVE sizing fail-closed: instruments map is missing or invalid")

        missing: list[str] = []
        for symbol in active_symbols:
            spec = instruments.get(symbol)
            if not isinstance(spec, dict):
                missing.append(f"{symbol} missing instrument spec")
                continue
            sizing = spec.get("sizing", spec)
            raw = sizing.get("margin_pct") if isinstance(sizing, dict) else None
            if raw is None:
                missing.append(f"{symbol} missing sizing.margin_pct")
                continue
            try:
                pct = float(raw)
                if not (0.0 < pct <= 1.0):
                    missing.append(f"{symbol} invalid sizing.margin_pct")
            except (TypeError, ValueError):
                missing.append(f"{symbol} invalid sizing.margin_pct")

        if missing:
            missing_sorted = "; ".join(sorted(missing[:10]))
            more = f" (and {len(missing) - 10} more)" if len(missing) > 10 else ""
            raise ValueError(
                "LIVE sizing fail-closed: Missing/invalid sizing config. "
                "All active symbols need sizing.margin_pct in (0,1]. "
                f"Missing: {missing_sorted}{more}"
            )


    def load_config(
        self,
        *,
        strict_mode: bool | None = None,
        is_live_execution: bool = False,
    ) -> AuroraConfig:
        """Load and validate configuration using Pydantic.

        This method:
        1. Loads YAML files
        2. Resolves environment variables
        3. Applies mode-specific overrides
        4. Validates through Pydantic (fails fast if invalid)
        5. (TASK47c) Validates execution config for LIVE mode (fail-closed)

        Args:
            strict_mode: Override for strict config validation mode (default: env-based)
            is_live_execution: If True, fail-closed validation for execution fields

        Raises:
            ValidationError: If config doesn't match Pydantic schema
            FileNotFoundError: If config files missing
            ValueError: If LIVE execution missing required execution config
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
            LOG.info("domains.yaml not found")

        # TASK47: crash-on-duplicate leaf paths across the primary YAML fragments.
        # Run BEFORE any schema/meta extraction can mask shadowed values.
        self._fail_on_duplicate_paths(
            sources={
                "system.yaml": system_config if isinstance(system_config, dict) else {},
                "trading.yaml": trading_config if isinstance(trading_config, dict) else {},
                "regime.yaml": regime_config if isinstance(regime_config, dict) else {},
                "domains.yaml": domains_config if isinstance(domains_config, dict) else {},
            }
        )

        system_meta = self._extract_system_meta(system_config, regime_config)
        
        # =========================================================================
        # DEPRECATED FILE DETECTION (CFG-FEATURES-REGIME-SSOT-04)
        # =========================================================================
        # features.yaml is ORPHANED (not loaded, duplicate of domains.yaml)
        # Detect its presence and fail/warn based on strict mode
        # =========================================================================
        import os
        strict_mode = self._get_strict_mode()
        
        features_yaml_path = self.config_dir / "features.yaml"
        if features_yaml_path.exists():
            msg = (
                "⚠️  DEPRECATED: features.yaml detected! "
                "This file is NOT loaded by ConfigLoader (orphaned config). "
                "Feature engineering config is read from domains.yaml (SSOT). "
                "Action required: Remove features.yaml or migrate to domains.yaml."
            )
            raise ConfigContractError(path="features.yaml", why=msg)
        
        # =========================================================================
        # DEPRECATED MR DETECTION (CFG-STRATEGIES-SSOT-05-MR-TRADING-YAML-BURN-DOWN)
        # =========================================================================
        # mean_reversion is DEPRECATED in trading.yaml (SSOT: strategy profile)
        # Detect its presence and fail/warn based on strict mode
        # =========================================================================
        if isinstance(trading_config, dict) and "mean_reversion" in trading_config:
            mr_section = trading_config.get("mean_reversion")
            if isinstance(mr_section, dict) and mr_section:
                msg = (
                    "⚠️  DEPRECATED: mean_reversion detected in trading.yaml! "
                    "This section is IGNORED (strategy profiles have priority). "
                    "SSOT for MR config: config/aurora/strategies/mean_reversion.yaml. "
                    "Action required: Remove mean_reversion from trading.yaml."
                )
                raise ConfigContractError(path="trading.mean_reversion", why=msg)

        # =========================================================================
        # CFG-STRATEGY-SSOT-FREEZE-02: trading.decision must NOT live in trading.yaml
        # =========================================================================
        # Aurora policy SSOT moved to strategies/aurora.yaml (aurora.decision).
        # trading.yaml must not contain strategy policy to prevent drift.
        if isinstance(trading_config, dict):
            t = trading_config.get("trading")
            if isinstance(t, dict) and "decision" in t:
                raise ConfigContractError(
                    path="trading.decision",
                    why=(
                        "⚠️  DEPRECATED: trading.decision detected in trading.yaml! "
                        "Strategy policy SSOT is strategies/aurora.yaml (aurora.decision). "
                        "Action required: Remove trading.decision from trading.yaml."
                    ),
                )

        # =========================================================================
        # CFG-STRATEGY-SSOT-FREEZE-02: aurora_instruments.yaml retired
        # =========================================================================
        # Per-symbol Aurora params SSOT moved to strategies/aurora.yaml (aurora.assets).
        aurora_instruments_yaml_path = self.config_dir / "aurora_instruments.yaml"
        if aurora_instruments_yaml_path.exists():
            raise ConfigContractError(
                path="aurora_instruments.yaml",
                why=(
                    "⚠️  DEPRECATED: aurora_instruments.yaml detected! "
                    "Per-symbol Aurora params SSOT moved to strategies/aurora.yaml (aurora.assets). "
                    "Action required: Remove/migrate aurora_instruments.yaml."
                ),
            )
        
        # =========================================================================
        # DEPRECATED FEATURE_ENGINEERING DETECTION (CFG-FREEZE-SSOT-06)
        # =========================================================================
        # feature_engineering is DEPRECATED in trading.yaml (SSOT: domains.yaml)
        # Detect its presence and fail/warn based on strict mode
        # =========================================================================
        # Check multiple locations where feature_engineering might appear in trading.yaml
        feature_eng_found = False
        feature_eng_locations = []
        
        if isinstance(trading_config, dict):
            # Check root level: trading.feature_engineering
            if "feature_engineering" in trading_config:
                fe_section = trading_config.get("feature_engineering")
                if isinstance(fe_section, dict) and fe_section:
                    feature_eng_found = True
                    feature_eng_locations.append("trading.feature_engineering (root level)")
            
            # Check nested in trading: trading.trading.feature_engineering
            nested_trading = trading_config.get("trading", {})
            if isinstance(nested_trading, dict) and "feature_engineering" in nested_trading:
                fe_section = nested_trading.get("feature_engineering")
                if isinstance(fe_section, dict) and fe_section:
                    feature_eng_found = True
                    feature_eng_locations.append("trading.trading.feature_engineering (nested)")
        
        if feature_eng_found:
            locations_str = ", ".join(feature_eng_locations)
            msg = (
                f"⚠️  DEPRECATED: feature_engineering detected in trading.yaml at: {locations_str}! "
                "This section is IGNORED (domains.yaml has priority). "
                "SSOT for feature_engineering: config/aurora/domains.yaml. "
                "Action required: Remove feature_engineering from trading.yaml."
            )
            raise ConfigContractError(path="trading.feature_engineering", why=msg)

        merged_config = self._merge_config_fragments(
            system_config=system_config,
            trading_config=trading_config,
            regime_config=regime_config,
            domains_config=domains_config,
            system_meta=system_meta,
        )

        # Enforce service key hygiene before validation
        for key in list(merged_config.keys()):
            if isinstance(key, str) and key.startswith("_config_"):
                raise ConfigContractError(
                    path=f"root.{key}",
                    why="Service/migration keys with prefix '_config_' are forbidden at root (CFG-ROOT-STRICT-FREEZE-NO-EXTRAS-P1-19)",
                )

        # Migrate legacy root.guardian block into execution.order_guardian to satisfy strict root schema
        guardian_block = merged_config.pop("guardian", None)
        if isinstance(guardian_block, dict):
            import copy

            root_exec = merged_config.get("execution")
            if isinstance(root_exec, dict):
                exec_block = root_exec
            else:
                trading_exec = None
                trading_block = merged_config.get("trading")
                if isinstance(trading_block, dict):
                    trading_exec = trading_block.get("execution")

                # Prefer cloning trading.execution as the base to keep schema-valid required fields.
                exec_block = copy.deepcopy(trading_exec) if isinstance(trading_exec, dict) else {}
                merged_config["execution"] = exec_block

            if "order_guardian" in exec_block and exec_block.get("order_guardian") is not None:
                raise ConfigContractError(
                    path="execution.order_guardian",
                    why=(
                        "Conflicting guardian configuration sources: found legacy root.guardian AND "
                        "execution.order_guardian. Keep only one (prefer execution.order_guardian)."
                    ),
                )

            exec_block["order_guardian"] = guardian_block

        # Resolve environment variables
        resolved_config = self._resolve_env_vars(merged_config)

        # Apply mode-specific decision overrides
        self._resolve_mode_overrides(resolved_config)

        # Ensure tracked symbols are SSOT-consistent and present for strict TradingConfig
        self._apply_trading_symbols_to_track_ssot(resolved_config)

        # Startup fail-fast: precision check for active symbols
        self._fail_fast_validate_instruments_precision(resolved_config)

        # TASK47c-A: Fail-closed execution config validation for LIVE mode
        if is_live_execution:
            self._validate_execution_config_for_live(resolved_config)
            self._validate_sizing_config_for_live(resolved_config)
            self._validate_directional_sanity_for_live(resolved_config)
            self._validate_price_motion_sanity_for_live(resolved_config)

        # CFG-TRADING-YAML-BURN-DOWN-01: Check for SSOT conflicts
        self._validate_ssot_conflicts(resolved_config)

        # P0-0: Validate essential_features ⊆ readiness_registry.declared_keys
        self._validate_essential_features_readiness_contract(resolved_config)

        # TASK23B: Enforce SSOT precedence for timeframe_sec
        self._apply_timeframe_sec_ssot_precedence(resolved_config)

        try:
            config = AuroraConfig(**resolved_config)
            LOG.info(
                f"✅ Configuration validated for trading_mode: '{config.trading_mode}'"
            )

            # TASK47: Debug disables are DEV/SHADOW only (testnet execution). Fail-closed in live/prod.
            try:
                debug_cfg = getattr(config.domains, "debug", None)
                if debug_cfg is not None and str(config.trading.mode).lower() in ("live", "production"):
                    if bool(getattr(debug_cfg, "disable_positions_stale_gate", False)):
                        raise ConfigContractError(
                            path="domains.debug.disable_positions_stale_gate",
                            why="Debug override forbidden in live/production trading.mode",
                        )
                    if bool(getattr(debug_cfg, "disable_daily_loss_limit", False)):
                        raise ConfigContractError(
                            path="domains.debug.disable_daily_loss_limit",
                            why="Debug override forbidden in live/production trading.mode",
                        )
            except ConfigContractError:
                raise
            except Exception:
                # Keep loader tolerant to older configs without domains.debug.
                pass

            # CFG-RUNTIME-BOOTSTRAP-07: runtime-only meta injection (post-validation)
            return self._inject_runtime_meta(config)
        except ValidationError as e:
            LOG.error("❌ Configuration validation failed:")
            for error in e.errors():
                loc = ".".join(str(x) for x in error["loc"])
                LOG.error(f"  {loc}: {error['msg']}")
            raise

    def _validate_directional_sanity_for_live(self, resolved_config: dict) -> None:
        """Fail-fast: directional_sanity SSOT must exist for LIVE execution.

        DM-DIR-SSOT-STRICT-01:
        - No silent defaults for directional_sanity.
        - In LIVE execution, missing block is a configuration contract violation.
        """
        if not isinstance(resolved_config, dict):
            raise ValueError("LIVE config invalid: resolved_config is not a dict")

        domains = resolved_config.get("domains")
        if not isinstance(domains, dict):
            raise ValueError("LIVE config fail-closed: missing domains block")

        dm = domains.get("decision_making")
        if not isinstance(dm, dict):
            raise ValueError("LIVE config fail-closed: missing domains.decision_making")

        ds = dm.get("directional_sanity")
        if not isinstance(ds, dict):
            raise ValueError(
                "LIVE config fail-closed: missing required SSOT block "
                "domains.decision_making.directional_sanity (DM-DIR-SSOT-STRICT-01)"
            )

        missing = []
        for k in ("enabled", "min_abs_delta_price", "min_confidence", "consecutive_bars"):
            if k not in ds or ds.get(k) is None:
                missing.append(k)

        if missing:
            raise ValueError(
                "LIVE config fail-closed: directional_sanity missing required keys: "
                + ", ".join(missing)
            )

    def _validate_price_motion_sanity_for_live(self, resolved_config: dict) -> None:
        """Fail-fast: price_motion_sanity SSOT must exist for LIVE execution.

        PRICE-MOTION-SSOT-STRICT-01:
        - No silent defaults for price_motion_sanity.
        - In LIVE execution, missing block is a configuration contract violation.
        """
        if not isinstance(resolved_config, dict):
            raise ValueError("LIVE config invalid: resolved_config is not a dict")

        domains = resolved_config.get("domains")
        if not isinstance(domains, dict):
            raise ValueError("LIVE config fail-closed: missing domains block")

        dm = domains.get("decision_making")
        if not isinstance(dm, dict):
            raise ValueError("LIVE config fail-closed: missing domains.decision_making")

        pm = dm.get("price_motion_sanity")
        if not isinstance(pm, dict):
            raise ValueError(
                "LIVE config fail-closed: missing required SSOT block "
                "domains.decision_making.price_motion_sanity (PRICE-MOTION-SSOT-STRICT-01)"
            )

        missing = []
        for k in (
            "enabled",
            "k_vol",
            "flash_window_sec",
            "bleed_window_sec",
            "flash_threshold_norm",
            "bleed_threshold_norm",
            "require_bleed_ready",
        ):
            if k not in pm or pm.get(k) is None:
                missing.append(k)

        if missing:
            raise ValueError(
                "LIVE config fail-closed: price_motion_sanity missing required keys: "
                + ", ".join(missing)
            )

    def _validate_essential_features_readiness_contract(self, resolved_config: dict) -> None:
        """P0-0: Fail-fast: essential_features ⊆ declared_ready_keys.
        
        This prevents config/code drift where essential features are configured
        but never emitted by FeatureEngineering.
        
        Contract:
        - essential_features (from aurora.yaml) must be subset of
          readiness_registry.declared_keys (from domains.yaml)
        """
        if not isinstance(resolved_config, dict):
            return
        
        # Get declared_keys from domains.feature_engineering.readiness_registry
        domains = resolved_config.get("domains")
        if not isinstance(domains, dict):
            return
        
        fe = domains.get("feature_engineering")
        if not isinstance(fe, dict):
            return
        
        rr = fe.get("readiness_registry")
        if not isinstance(rr, dict):
            # No readiness_registry defined - skip validation (backward compat)
            LOG.debug("P0-0: readiness_registry not defined, skipping validation")
            return
        
        declared_keys = rr.get("declared_keys")
        if not isinstance(declared_keys, list) or not declared_keys:
            LOG.debug("P0-0: declared_keys empty or not a list, skipping validation")
            return
        
        declared_set = set(declared_keys)
        
        # Get essential_features from strategies.aurora.decision
        strategies = resolved_config.get("strategies")
        if not isinstance(strategies, dict):
            return
        
        aurora = strategies.get("aurora")
        if not isinstance(aurora, dict):
            return
        
        decision = aurora.get("decision")
        if not isinstance(decision, dict):
            return
        
        essential = decision.get("essential_features")
        if not isinstance(essential, list) or not essential:
            return
        
        essential_set = set(essential)
        
        # P0-0: Validate essential ⊆ declared
        missing = essential_set - declared_set
        if missing:
            raise ConfigContractError(
                path="strategies.aurora.decision.essential_features",
                why=(
                    f"P0-0 READINESS CONTRACT VIOLATION: Essential features {sorted(missing)} "
                    f"are NOT in readiness_registry.declared_keys. "
                    "Either add them to domains.yaml::feature_engineering.readiness_registry.declared_keys "
                    "or remove from essential_features."
                ),
            )
        
        LOG.info(f"✅ P0-0: essential_features {sorted(essential_set)} ⊆ declared_keys (contract valid)")

    def _apply_timeframe_sec_ssot_precedence(self, resolved_config: dict) -> None:
        """Apply strict SSOT precedence for timeframe_sec.

        Contract (TASK23B):
        1) strategies.aurora.assets.<SYM>.timeframe_sec (if set) wins
        2) strategies.mean_reversion.timeframe_sec from strategy profile
        3) If both absent while strategy assigned -> fail-closed (ConfigContractError)
        """
        if not isinstance(resolved_config, dict):
            return

        sr = resolved_config.get("strategies_registry")
        if not isinstance(sr, dict):
            return

        assignments = sr.get("assignments")
        if not isinstance(assignments, dict):
            return

        assigned_symbols: list[str] = []
        for symbol, strategy_ids in assignments.items():
            if not isinstance(symbol, str):
                continue
            if not isinstance(strategy_ids, list):
                continue
            if "mean_reversion" in strategy_ids:
                assigned_symbols.append(symbol)

        if not assigned_symbols:
            return

        strategies = resolved_config.get("strategies")
        if not isinstance(strategies, dict):
            strategies = {}

        aurora_cfg = strategies.get("aurora")
        aurora_assets: dict = {}
        if isinstance(aurora_cfg, dict):
            assets = aurora_cfg.get("assets")
            if isinstance(assets, dict):
                aurora_assets = assets

        overrides: set[int] = set()
        for symbol in assigned_symbols:
            inst_cfg = aurora_assets.get(symbol)
            if not isinstance(inst_cfg, dict):
                continue
            if "timeframe_sec" not in inst_cfg:
                continue
            raw = inst_cfg.get("timeframe_sec")
            if raw is None:
                continue
            try:
                overrides.add(int(raw))
            except Exception as e:
                raise ConfigContractError(
                    path=f"strategies.aurora.assets.{symbol}.timeframe_sec",
                    symbol=symbol,
                    why=f"Invalid timeframe_sec override: {raw!r} ({e})",
                )

        mr_block = strategies.get("mean_reversion")
        if mr_block is None:
            mr_dict: dict = {}
        elif isinstance(mr_block, dict):
            mr_dict = mr_block
        else:
            raise ConfigContractError(
                path="strategies.mean_reversion",
                why=f"Expected dict for strategies.mean_reversion config, got {type(mr_block).__name__}",
            )

        profile_raw = mr_dict.get("timeframe_sec", None)

        if overrides:
            if len(overrides) != 1:
                raise ConfigContractError(
                    path="strategies.aurora.assets.*.timeframe_sec",
                    why=f"Conflicting timeframe_sec overrides for mean_reversion across assigned symbols: {sorted(overrides)}",
                )
            effective = next(iter(overrides))
            if effective <= 0:
                raise ConfigContractError(
                    path="strategies.aurora.assets.*.timeframe_sec",
                    why=f"timeframe_sec override must be positive, got {effective}",
                )
            mr_dict["timeframe_sec"] = effective
            strategies["mean_reversion"] = mr_dict
            resolved_config["strategies"] = strategies
            return

        if profile_raw is None:
            raise ConfigContractError(
                path="strategies.mean_reversion.timeframe_sec",
                why="Missing timeframe_sec for assigned strategy mean_reversion. Set strategies.aurora.assets.<SYM>.timeframe_sec or strategies.mean_reversion.timeframe_sec",
            )

        try:
            profile_tf = int(profile_raw)
        except Exception as e:
            raise ConfigContractError(
                path="strategies.mean_reversion.timeframe_sec",
                why=f"Invalid timeframe_sec value: {profile_raw!r} ({e})",
            )

        if profile_tf <= 0:
            raise ConfigContractError(
                path="strategies.mean_reversion.timeframe_sec",
                why=f"timeframe_sec must be positive, got {profile_tf}",
            )


_config_instance: Optional[AuroraConfig] = None


def get_config() -> AuroraConfig:
    global _config_instance
    if _config_instance is None:
        loader = ConfigLoader()
        _config_instance = loader.load_config()
    return _config_instance
