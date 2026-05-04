"""
Leverage configuration management for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles leverage bootstrap, config collection from instruments.yaml SSOT,
and SSOT consistency validation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Set

if TYPE_CHECKING:
    from apps.reference.config_models import LeverageConfig

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.leverage_config"
)


class LeverageConfigManager:
    """Manages leverage configuration and bootstrap for execution_position."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    @property
    def config(self) -> Any:
        return self._fsm.config

    @property
    def adapter(self) -> Any:
        return self._fsm.adapter

    @property
    def shadow_mode(self) -> bool:
        return self._fsm.shadow_mode

    async def run_bootstrap(self) -> Set[str]:
        """Run leverage bootstrap to sync margin mode and leverage with exchange.

        P3: Active Leverage Management — Runtime Integration

        This method:
        1. Collects LeverageConfig from all active strategy configs
        2. Runs LeverageBootstrapper to sync each symbol
        3. Returns set of symbols that failed (blocked from trading)

        MUST be called AFTER _initialize_adapter() and BEFORE trading starts.

        Returns:
            Set of symbols that failed to sync (should be blocked from trading)
        """
        if self.shadow_mode or self.adapter is None:
            LOG.info("TASK47c-P3: Leverage bootstrap skipped (shadow mode or no adapter)")
            return set()

        # LEVERAGE-SSOT-FIX-01: Validate consistency and log warnings
        ssot_warnings = self.validate_ssot_consistency()
        if ssot_warnings:
            LOG.warning(
                f"LEVERAGE-SSOT-FIX-01: Found {len(ssot_warnings)} legacy leverage values in strategy configs. "
                "These are IGNORED. SSOT is instruments.yaml."
            )

        # Import here to avoid circular imports
        from .bootstrapping.leverage_bootstrapper import (
            LeverageBootstrapper,
        )

        # Collect leverage configs from strategies
        leverage_configs = self.collect_configs()

        if not leverage_configs:
            LOG.warning("TASK47c-P3: No leverage configs found, bootstrap skipped")
            return set()

        LOG.info(f"TASK47c-P3: Running leverage bootstrap for {len(leverage_configs)} symbols")

        bootstrapper = LeverageBootstrapper(adapter=self.adapter, logger=LOG)
        results = await bootstrapper.run(leverage_configs)

        if results.has_failures:
            LOG.error(
                f"TASK47c-P3: Leverage bootstrap FAILED for {len(results.failed)} symbols: {results.failed}"
            )
            for sym in results.failed:
                fail_result = results.failures.get(sym)
                if fail_result:
                    LOG.error(f"  {sym}: code={fail_result.error_code}, msg={fail_result.error_msg}")
        else:
            LOG.info(f"TASK47c-P3: Leverage bootstrap SUCCESS for all {len(leverage_configs)} symbols")

        return set(results.failed)

    def collect_configs(self) -> Dict[str, "LeverageConfig"]:
        """Collect LeverageConfig from instruments.yaml SSOT.

        LEVERAGE-SSOT-FIX-01: Read from instruments.<SYM>.execution.target_leverage
        instead of strategies.*.assets.<SYM>.leverage to avoid SSOT conflict.

        Returns:
            Dict mapping symbol -> LeverageConfig (only active symbols with execution config)
        """
        from apps.reference.config_models import LeverageConfig

        result: Dict[str, LeverageConfig] = {}

        # Get active symbols from strategies_registry assignments
        try:
            registry = self.config.strategies_registry
            if registry is None or not hasattr(registry, 'assignments'):
                LOG.warning("LEVERAGE-SSOT-FIX-01: No strategies_registry.assignments found")
                return result
            assignments = registry.assignments or {}
        except AttributeError:
            LOG.warning("LEVERAGE-SSOT-FIX-01: Failed to read strategies_registry.assignments")
            return result

        # Get instruments dict
        instruments = getattr(self.config, 'instruments', None)
        if not isinstance(instruments, dict):
            LOG.warning("LEVERAGE-SSOT-FIX-01: No instruments dict found in config")
            return result

        for symbol in assignments.keys():
            spec = instruments.get(symbol)
            if spec is None:
                LOG.warning(f"LEVERAGE-SSOT-FIX-01: Symbol {symbol} in assignments but not in instruments")
                continue

            exec_cfg = getattr(spec, 'execution', None)
            if exec_cfg is None:
                LOG.warning(f"LEVERAGE-SSOT-FIX-01: Symbol {symbol} has no execution config")
                continue

            target_leverage = getattr(exec_cfg, 'target_leverage', None)
            margin_mode = getattr(exec_cfg, 'margin_mode', 'isolated')

            if target_leverage is None:
                LOG.warning(f"LEVERAGE-SSOT-FIX-01: Symbol {symbol} has no target_leverage")
                continue

            # Convert margin_mode to LeverageConfig format
            mode_map = {"isolated": "ISOLATED", "cross": "CROSSED"}
            mode_normalized = mode_map.get(
                margin_mode.lower() if isinstance(margin_mode, str) else "isolated",
                "ISOLATED"
            )

            result[symbol] = LeverageConfig(
                target=int(target_leverage),
                mode=mode_normalized,
                max_notional_value=None,
            )

        LOG.info(
            f"LEVERAGE-SSOT-FIX-01: Collected leverage from instruments.yaml for {len(result)} symbols: "
            f"{[(s, c.target) for s, c in result.items()]}"
        )
        return result

    def validate_ssot_consistency(self) -> List[str]:
        """Validate that strategy leverage configs match instruments SSOT.

        LEVERAGE-SSOT-FIX-01: Startup guard to detect legacy/stale strategy leverage.

        Returns:
            List of warning messages for mismatches (empty if consistent)
        """
        warnings: List[str] = []

        instruments = getattr(self.config, 'instruments', None)
        if not isinstance(instruments, dict):
            return warnings

        # Check Aurora strategy assets
        try:
            aurora = self.config.strategies.aurora
            if aurora and aurora.assets:
                for symbol, asset_cfg in aurora.assets.items():
                    if asset_cfg and asset_cfg.leverage:
                        strategy_lev = asset_cfg.leverage.target
                        spec = instruments.get(symbol)
                        if spec and spec.execution:
                            inst_lev = spec.execution.target_leverage
                            if strategy_lev != inst_lev:
                                warnings.append(
                                    f"LEVERAGE_SSOT_MISMATCH: {symbol} aurora.leverage.target={strategy_lev} "
                                    f"!= instruments.execution.target_leverage={inst_lev} "
                                    f"(SSOT is instruments.yaml, strategy value is IGNORED)"
                                )
        except AttributeError:
            pass

        # Check MeanReversion strategy assets
        try:
            mr = self.config.strategies.mean_reversion
            if mr and mr.assets:
                for symbol, asset_cfg in mr.assets.items():
                    if asset_cfg and asset_cfg.leverage:
                        strategy_lev = asset_cfg.leverage.target
                        spec = instruments.get(symbol)
                        if spec and spec.execution:
                            inst_lev = spec.execution.target_leverage
                            if strategy_lev != inst_lev:
                                warnings.append(
                                    f"LEVERAGE_SSOT_MISMATCH: {symbol} mean_reversion.leverage.target={strategy_lev} "
                                    f"!= instruments.execution.target_leverage={inst_lev} "
                                    f"(SSOT is instruments.yaml, strategy value is IGNORED)"
                                )
        except AttributeError:
            pass

        for warn in warnings:
            LOG.warning(warn)

        return warnings
