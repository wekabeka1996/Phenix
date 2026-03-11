"""
Backtest symbol filtering logic to enforce separation of concerns from ConfigLoader.

This logic is exclusively used in backtest mode to restrict the universe of
traded symbols without modifying the canonical SSOT in strategies.yaml.
"""

import logging
from typing import Any, Dict

from apps.reference.config_contract import ConfigContractError

logger = logging.getLogger(__name__)


def apply_backtest_symbols_filter(resolved_config: Dict[str, Any]) -> None:
    """
    Backtest-only: allow running on a strict subset of SSOT symbols.

    If trading mode is backtest and trading.symbols_to_track is set, filter
    strategies_registry.assignments down to that subset before Pydantic validation.
    """
    if not isinstance(resolved_config, dict):
        return

    root_mode = resolved_config.get("trading_mode")
    trading = resolved_config.get("trading")
    trading_mode = None
    if isinstance(trading, dict):
        trading_mode = trading.get("mode")

    is_backtest = False
    if isinstance(root_mode, str) and root_mode.strip().lower() == "backtest":
        is_backtest = True
    if isinstance(trading_mode, str) and trading_mode.strip().lower() == "backtest":
        is_backtest = True
    if not is_backtest:
        return

    if not isinstance(trading, dict):
        return

    wanted = trading.get("symbols_to_track")
    if not (isinstance(wanted, list) and wanted):
        return

    wanted_symbols = [str(symbol) for symbol in wanted if str(symbol).strip()]
    if not wanted_symbols:
        return

    strategies_registry = resolved_config.get("strategies_registry")
    if not isinstance(strategies_registry, dict):
        return

    assignments = strategies_registry.get("assignments")
    if not isinstance(assignments, dict):
        return

    wanted_set = set(wanted_symbols)
    filtered_assignments = {
        symbol: config for symbol, config in assignments.items() if str(symbol) in wanted_set
    }

    if not filtered_assignments:
        raise ConfigContractError(
            path="strategies_registry.assignments",
            why=(
                "Backtest symbols filter removed all assignments. "
                f"trading.symbols_to_track={wanted_symbols} had no overlap with strategies.yaml assignments."
            ),
        )

    if set(filtered_assignments.keys()) != set(assignments.keys()):
        strategies_registry["assignments"] = filtered_assignments
        resolved_config["strategies_registry"] = strategies_registry
        logger.warning(
            "[backtest] Filtered strategies_registry.assignments to symbols_to_track=%s",
            sorted(wanted_set),
        )
