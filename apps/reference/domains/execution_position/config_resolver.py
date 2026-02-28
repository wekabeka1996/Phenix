"""
Config resolver helpers — Phase 14.2 extraction from fsm.py.

Encapsulates configuration traversal logic used by ExecPosFSM.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig

LOG = logging.getLogger(__name__)


class ConfigResolverMixin:
    """
    Mixin providing config-traversal methods for ExecPosFSM.

    Expects `self.config` to be an AuroraConfig instance.
    """

    config: Any  # AuroraConfig

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

    def _resolve_guardian_config(self) -> Dict[str, Any]:
        """Aggregate guardian config from SSOT: domains.execution_position.guardian.

        MAGIC-NUM-EXTRACTION: All guardian config now from domains.yaml, no hardcoded defaults.
        """
        # SSOT: domains.execution_position.guardian (fail-closed if missing)
        try:
            guardian_cfg = self.config.domains.execution_position.guardian
            if guardian_cfg is None:
                raise ValueError("guardian config is required in domains.execution_position")

            return {
                "unified": bool(guardian_cfg.unified),
                "emit_tidy_event": bool(guardian_cfg.emit_tidy_event),
                "poll_interval_ms": int(guardian_cfg.poll_interval_ms),
                "cleanup_ttl_ms": int(guardian_cfg.cleanup_ttl_ms),
                "symbol_cooldown_ms": int(guardian_cfg.symbol_cooldown_ms),
            }
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load guardian config from domains.execution_position: {e}. "
                "Check domains.yaml has execution_position.guardian section."
            ) from e

    def _collect_guardian_symbols(self) -> Set[str]:
        """Gather configured trading symbols for guardian ownership tracking."""
        symbols: Set[str] = set()
        instruments = self._get_config_value(
            ["trading", "instruments"], default={})
        if isinstance(instruments, dict):
            for sym in instruments.keys():
                if sym:
                    symbols.add(str(sym).upper())
        return symbols
