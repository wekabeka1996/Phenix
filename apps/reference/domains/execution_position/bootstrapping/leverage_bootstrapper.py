"""
LeverageBootstrapper — Startup Leverage/Margin Synchronization Service

P2: Active Leverage Management — Startup Guard

This service runs at startup to synchronize leverage and margin mode
on the exchange with the configuration from strategy configs.

Architecture:
- Input: BinanceAdapter + target LeverageConfig per symbol
- Logic: Compare current state → set margin mode → set leverage
- Output: List of symbols that failed to sync (blocked from trading)

Error Handling (Fail-Closed):
- MarginChangeError (-4047, -4048): Symbol blocked (position/orders exist)
- LeverageReductionError (-4161): Symbol blocked (ISOLATED reduction)
- MaxLeverageExceededError (-2027): Symbol blocked (notional too large)

Usage:
    bootstrapper = LeverageBootstrapper(adapter, logger)
    results = await bootstrapper.run({
        "BTCUSDT": LeverageConfig(target=20, mode="ISOLATED"),
        "ETHUSDT": LeverageConfig(target=20, mode="ISOLATED"),
    })
    if results.has_failures:
        # Block failed symbols from trading or crash
        for symbol in results.failed:
            log.error(f"Symbol {symbol} blocked: {results.failures[symbol].error_msg}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from apps.reference.adapters.binance_adapter import BinanceAdapter
    from apps.reference.config_models import LeverageConfig


@dataclass
class BootstrapResult:
    """Result of bootstrapping a single symbol.
    
    Attributes:
        symbol: Trading symbol
        success: True if sync completed without errors
        margin_changed: True if margin mode was changed
        leverage_changed: True if leverage was changed
        error_code: Binance error code if failed
        error_msg: Error message if failed
    """
    symbol: str
    success: bool
    margin_changed: bool = False
    leverage_changed: bool = False
    error_code: Optional[int] = None
    error_msg: Optional[str] = None


@dataclass
class BootstrapResults:
    """Aggregated results of bootstrapping all symbols.
    
    Provides easy access to succeeded/failed symbols and error details.
    """
    _results: Dict[str, BootstrapResult] = field(default_factory=dict)
    
    def add_success(self, symbol: str, result: BootstrapResult) -> None:
        """Add a successful result."""
        self._results[symbol] = result
    
    def add_failure(self, symbol: str, result: BootstrapResult) -> None:
        """Add a failed result."""
        self._results[symbol] = result
    
    @property
    def succeeded(self) -> List[str]:
        """List of symbols that synced successfully."""
        return [s for s, r in self._results.items() if r.success]
    
    @property
    def failed(self) -> List[str]:
        """List of symbols that failed to sync."""
        return [s for s, r in self._results.items() if not r.success]
    
    @property
    def failures(self) -> Dict[str, BootstrapResult]:
        """Dict of failed symbols → result details."""
        return {s: r for s, r in self._results.items() if not r.success}
    
    @property
    def all_succeeded(self) -> bool:
        """True if all symbols synced successfully."""
        return len(self.failed) == 0
    
    @property
    def has_failures(self) -> bool:
        """True if any symbol failed to sync."""
        return len(self.failed) > 0


class LeverageBootstrapper:
    """
    Startup service to synchronize leverage/margin settings on exchange.
    
    This runs BEFORE any trading starts to ensure:
    1. Margin mode matches config (ISOLATED/CROSSED)
    2. Leverage matches config (1-125x)
    
    If sync fails for a symbol, that symbol is blocked from trading (fail-closed).
    """
    
    def __init__(
        self,
        adapter: "BinanceAdapter",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize LeverageBootstrapper.
        
        Args:
            adapter: BinanceAdapter instance for API calls
            logger: Optional logger (defaults to module logger)
        """
        self._adapter = adapter
        self._log = logger or logging.getLogger(__name__)
    
    async def sync_symbol(
        self,
        symbol: str,
        target: "LeverageConfig",
    ) -> BootstrapResult:
        """
        Synchronize leverage/margin for a single symbol.
        
        Order of operations:
        1. Get current margin mode
        2. If mismatch → set_margin_mode (may fail if position exists)
        3. Get current leverage
        4. If mismatch → set_leverage (may fail if reducing in ISOLATED)
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            target: Target LeverageConfig from strategy
            
        Returns:
            BootstrapResult with success/failure details
        """
        # Import here to avoid circular imports
        from apps.reference.adapters.binance_adapter import (
            BinanceAPIError,
            LeverageReductionError,
            MarginChangeError,
            MaxLeverageExceededError,
        )
        
        margin_changed = False
        leverage_changed = False
        target_margin_mode = target.mode.lower()  # "isolated" or "crossed"
        target_leverage = target.target
        
        self._log.info(
            f"BOOTSTRAP_START: {symbol} → target={target_leverage}x, mode={target.mode}"
        )
        
        try:
            # ─────────────────────────────────────────────────────────────
            # Step 1: Check and sync margin mode
            # ─────────────────────────────────────────────────────────────
            current_margin = await self._adapter.get_margin_mode(symbol)
            
            if current_margin != target_margin_mode:
                self._log.info(
                    f"BOOTSTRAP_MARGIN: {symbol} current={current_margin}, "
                    f"target={target_margin_mode} → changing"
                )
                await self._adapter.set_margin_mode(symbol, target_margin_mode)
                margin_changed = True
            else:
                self._log.debug(
                    f"BOOTSTRAP_MARGIN: {symbol} already {current_margin} (no change)"
                )
            
            # ─────────────────────────────────────────────────────────────
            # Step 2: Check and sync leverage
            # ─────────────────────────────────────────────────────────────
            current_leverage = await self._adapter.get_current_leverage(symbol)
            
            if current_leverage != target_leverage:
                self._log.info(
                    f"BOOTSTRAP_LEVERAGE: {symbol} current={current_leverage}x, "
                    f"target={target_leverage}x → changing"
                )
                await self._adapter.set_leverage(symbol, target_leverage)
                leverage_changed = True
            else:
                self._log.debug(
                    f"BOOTSTRAP_LEVERAGE: {symbol} already {current_leverage}x (no change)"
                )
            
            # Success
            self._log.info(
                f"BOOTSTRAP_SUCCESS: {symbol} synced "
                f"(margin_changed={margin_changed}, leverage_changed={leverage_changed})"
            )
            return BootstrapResult(
                symbol=symbol,
                success=True,
                margin_changed=margin_changed,
                leverage_changed=leverage_changed,
            )
        
        except MarginChangeError as e:
            # -4047: Open orders exist
            # -4048: Position exists
            self._log.error(
                f"BOOTSTRAP_FAIL: {symbol} margin change blocked: [{e.code}] {e.msg}"
            )
            return BootstrapResult(
                symbol=symbol,
                success=False,
                margin_changed=False,
                leverage_changed=False,
                error_code=e.code,
                error_msg=e.msg,
            )
        
        except LeverageReductionError as e:
            # -4161: Cannot reduce leverage in ISOLATED with position
            self._log.error(
                f"BOOTSTRAP_FAIL: {symbol} leverage reduction blocked: [{e.code}] {e.msg}"
            )
            return BootstrapResult(
                symbol=symbol,
                success=False,
                margin_changed=margin_changed,
                leverage_changed=False,
                error_code=e.code,
                error_msg=e.msg,
            )
        
        except MaxLeverageExceededError as e:
            # -2027: Notional exceeds bracket for requested leverage
            self._log.error(
                f"BOOTSTRAP_FAIL: {symbol} leverage exceeds bracket: [{e.code}] {e.msg}"
            )
            return BootstrapResult(
                symbol=symbol,
                success=False,
                margin_changed=margin_changed,
                leverage_changed=False,
                error_code=e.code,
                error_msg=e.msg,
            )
        
        except BinanceAPIError as e:
            # Unexpected API error
            self._log.error(
                f"BOOTSTRAP_FAIL: {symbol} unexpected API error: [{e.code}] {e.msg}"
            )
            return BootstrapResult(
                symbol=symbol,
                success=False,
                margin_changed=margin_changed,
                leverage_changed=leverage_changed,
                error_code=e.code,
                error_msg=e.msg,
            )
    
    async def run(
        self,
        targets: Dict[str, "LeverageConfig"],
    ) -> BootstrapResults:
        """
        Run bootstrap for all target symbols.
        
        Iterates through all symbols and attempts to sync each one.
        Failures do NOT stop the loop — we try all symbols and report results.
        
        Args:
            targets: Dict of symbol → LeverageConfig
            
        Returns:
            BootstrapResults with succeeded/failed symbols
        """
        results = BootstrapResults()
        
        if not targets:
            self._log.info("BOOTSTRAP_RUN: No targets to sync")
            return results
        
        self._log.info(f"BOOTSTRAP_RUN: Syncing {len(targets)} symbols...")
        
        for symbol, target in targets.items():
            result = await self.sync_symbol(symbol, target)
            
            if result.success:
                results.add_success(symbol, result)
            else:
                results.add_failure(symbol, result)
        
        # Summary log
        self._log.info(
            f"BOOTSTRAP_DONE: {len(results.succeeded)} succeeded, "
            f"{len(results.failed)} failed"
        )
        
        if results.has_failures:
            self._log.warning(
                f"BOOTSTRAP_BLOCKED: Symbols blocked from trading: {results.failed}"
            )
        
        return results
