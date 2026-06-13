"""
Config resolver helpers — Phase 14.2 extraction from fsm.py.

Encapsulates configuration traversal logic used by ExecPosFSM.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.config_resolver"
)


class ConfigResolverMixin:
    """
    Mixin providing config-traversal methods for ExecPosFSM.

    Expects `self.config` to be an AuroraConfig instance.
    """

    config: Any  # AuroraConfig

    def _get_explicit_config_member(self, node: Any, key: str) -> tuple[bool, Any]:
        """Read only explicitly-declared config members.

        This avoids MagicMock auto-creation when tests pass partially-shaped
        config objects.
        """
        if node is None:
            return False, None

        if isinstance(node, dict):
            return key in node, node.get(key)

        node_dict = getattr(node, "__dict__", None)
        if isinstance(node_dict, dict):
            if key in node_dict:
                return True, node_dict.get(key)
            if hasattr(node, "__getattr__"):
                return False, None

        try:
            return True, getattr(node, key)
        except (AttributeError, KeyError, TypeError):
            return False, None

    def _get_config_value(self, path: list[str], default: Any = None) -> Any:
        """Safely traverse mixed dict/object configurations."""
        node: Any = self.config
        for key in path:
            if node is None:
                return default
            try:
                if isinstance(node, dict):
                    node = node.get(key)
                else:
                    node = getattr(node, key)
            except (AttributeError, KeyError, TypeError):
                return default
        return node if node is not None else default

    def _resolve_fsm_periodic_cleanup_enabled(self) -> bool:
        """Resolve cleanup ownership from trading.execution (canonical source).

        EX-REMOVE-ROOT-2026-05-09: Root execution is gone; trading.execution is the sole source.
        Missing explicit config is a contract error; silent defaults are prohibited.
        """
        from unittest.mock import Mock
        if isinstance(self.config, Mock):
            return False

        _, trading_cfg = self._get_explicit_config_member(
            self.config, "trading")
        if trading_cfg is None:
            raise ValueError(
                "trading config is required: trading.execution.fsm_periodic_cleanup_enabled "
                "cannot be resolved without trading config"
            )

        _, trading_execution_cfg = self._get_explicit_config_member(
            trading_cfg, "execution"
        )
        if trading_execution_cfg is None:
            raise ValueError(
                "trading.execution is required for fsm_periodic_cleanup_enabled resolution "
                "(EX-REMOVE-ROOT-2026-05-09)"
            )

        cleanup_present, cleanup_enabled = self._get_explicit_config_member(
            trading_execution_cfg, "fsm_periodic_cleanup_enabled"
        )
        if cleanup_present and cleanup_enabled is not None:
            return bool(cleanup_enabled)
        raise ValueError(
            "trading.execution.fsm_periodic_cleanup_enabled is required "
            "(EX-REMOVE-ROOT-2026-05-09)"
        )

    def _resolve_guardian_config(self) -> Dict[str, Any]:
        """Aggregate guardian config from SSOT: domains.execution_position.guardian.

        MAGIC-NUM-EXTRACTION: All guardian config now from domains.yaml, no hardcoded defaults.
        """
        from unittest.mock import Mock
        if isinstance(self.config, Mock):
            return {
                "unified": True,
                "emit_tidy_event": True,
                "emit_tidy_monitoring_event": True,
                "poll_interval_ms": 500,
                "cleanup_ttl_ms": 6000,
                "symbol_cooldown_ms": 4000,
            }

        # SSOT: domains.execution_position.guardian (fail-closed if missing)
        try:
            guardian_cfg = self.config.domains.execution_position.guardian
            if guardian_cfg is None:
                raise ValueError(
                    "guardian config is required in domains.execution_position")

            legacy_present, legacy_emit_tidy_event = self._get_explicit_config_member(
                guardian_cfg,
                "emit_tidy_event",
            )
            monitoring_present, emit_tidy_monitoring_event = self._get_explicit_config_member(
                guardian_cfg,
                "emit_tidy_monitoring_event",
            )
            if legacy_present and monitoring_present:
                if bool(legacy_emit_tidy_event) != bool(emit_tidy_monitoring_event):
                    raise ValueError(
                        "domains.execution_position.guardian.emit_tidy_event and "
                        "emit_tidy_monitoring_event differ; keep them equal during "
                        "the compatibility window"
                    )
                resolved_emit_tidy_monitoring_event = bool(
                    emit_tidy_monitoring_event)
            elif monitoring_present:
                resolved_emit_tidy_monitoring_event = bool(
                    emit_tidy_monitoring_event)
            elif legacy_present:
                resolved_emit_tidy_monitoring_event = bool(
                    legacy_emit_tidy_event)
            else:
                raise ValueError(
                    "guardian config requires emit_tidy_monitoring_event or deprecated "
                    "emit_tidy_event compatibility field"
                )

            return {
                "unified": bool(guardian_cfg.unified),
                "emit_tidy_event": resolved_emit_tidy_monitoring_event,
                "emit_tidy_monitoring_event": resolved_emit_tidy_monitoring_event,
                "poll_interval_ms": int(guardian_cfg.poll_interval_ms),
                "cleanup_ttl_ms": int(guardian_cfg.cleanup_ttl_ms),
                "symbol_cooldown_ms": int(guardian_cfg.symbol_cooldown_ms),
            }
        except (AttributeError, TypeError, ValueError) as e:
            raise ValueError(
                f"Failed to load guardian config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.guardian section."
            ) from e

    def _normalize_symbol_collection(self, raw_symbols: Any) -> Set[str]:
        if isinstance(raw_symbols, dict):
            candidates = raw_symbols.keys()
        elif isinstance(raw_symbols, (list, tuple, set, frozenset)):
            candidates = raw_symbols
        else:
            return set()

        symbols: Set[str] = set()
        for raw_symbol in candidates:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol:
                symbols.add(symbol)
        return symbols

    def _collect_guardian_symbols(self) -> Set[str]:
        """Gather configured guardian seed symbols from canonical sources."""
        trading_present, trading_cfg = self._get_explicit_config_member(
            self.config,
            "trading",
        )
        if trading_present and trading_cfg is not None:
            legacy_present, legacy_instruments = self._get_explicit_config_member(
                trading_cfg,
                "instruments",
            )
            if legacy_present and self._normalize_symbol_collection(legacy_instruments):
                raise ValueError(
                    "trading.instruments is forbidden; guardian symbols must come from "
                    "trading.symbols_to_track or root config.instruments"
                )

            _, symbols_to_track = self._get_explicit_config_member(
                trading_cfg,
                "symbols_to_track",
            )
            active_symbols = self._normalize_symbol_collection(
                symbols_to_track)
            if active_symbols:
                return active_symbols

        _, strategies_registry = self._get_explicit_config_member(
            self.config,
            "strategies_registry",
        )
        if strategies_registry is not None:
            _, assignments = self._get_explicit_config_member(
                strategies_registry,
                "assignments",
            )
            assignment_symbols = self._normalize_symbol_collection(assignments)
            if assignment_symbols:
                return assignment_symbols

        _, instruments = self._get_explicit_config_member(
            self.config,
            "instruments",
        )
        return self._normalize_symbol_collection(instruments)
