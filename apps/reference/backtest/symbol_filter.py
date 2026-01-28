"""
Backtest symbol filtering logic to enforce separation of concerns from ConfigLoader.

This logic is exclusively used in backtest mode to restrict the universe of
traded symbols without modifying the canonical SSOT (strategies.yaml).
"""
import logging
from typing import Any, Dict, List

from apps.reference.config_contract import ConfigContractError

logger = logging.getLogger(__name__)


def apply_backtest_symbols_filter(resolved_config: Dict[str, Any]) -> None:
    """
    Backtest-only: allow running on a strict subset of SSOT symbols.

    Problem:
    - SSOT for active symbols is strategies.yaml assignments keys.
    - In backtest we often have historical data only for a subset (e.g., BTCUSDT).

    Contract:
    - If trading_mode == backtest and trading.symbols_to_track is set,
      then we FILTER strategies_registry.assignments down to that subset.
    - After filtering, the regular SSOT enforcement stays intact.
    
    Args:
        resolved_config: The raw dictionary of the resolved configuration before Pydantic validation.
    
    Raises:
        ConfigContractError: If filtering results in zero assignments.
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
    wanted_symbols = [str(s) for s in wanted if str(s).strip()]
    if not wanted_symbols:
        return

    sr = resolved_config.get("strategies_registry")
    if not isinstance(sr, dict):
        return
    assignments = sr.get("assignments")
    if not isinstance(assignments, dict):
        return

    # Perform filtering
    filtered = {k: v for k, v in assignments.items() if str(k) in set(wanted_symbols)}
    
    # Fail-closed if filter removed everything
    if not filtered:
        raise ConfigContractError(
            path="strategies_registry.assignments",
            why=(
                "Backtest symbols filter removed all assignments. "
                f"trading.symbols_to_track={wanted_symbols} had no overlap with strategies.yaml assignments."
            ),
        )

    # Apply changes if filtering occurred
    if len(filtered) != len(assignments):
        # We only care if the set of KEYS changed.
        # However, checking lengths covers the reduction case.
        # More precise checking:
        if set(filtered.keys()) != set(assignments.keys()):
            sr["assignments"] = filtered
            resolved_config["strategies_registry"] = sr
            logger.warning(
                "⚠️  [backtest] Filtered strategies_registry.assignments to symbols_to_track=%s",
                sorted(set(wanted_symbols)),
            )
