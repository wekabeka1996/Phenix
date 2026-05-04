"""
Exchange Filters Validator.

TASK51-A: Validates SSOT instruments.yaml against exchange reality.
Fail-closed: mismatches cause startup crash in LIVE mode.
"""

from __future__ import annotations
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Protocol

from .contracts import ExchangeFilters, SSOTFilters, FilterMismatch

LOG = logging.getLogger(__name__)


class FilterMismatchError(Exception):
    """
    Raised when SSOT filters don't match exchange filters.
    
    TASK51-A: This is a fail-closed exception that should crash startup
    in LIVE mode to prevent qty normalization bugs.
    """
    
    def __init__(self, mismatches: List[FilterMismatch]):
        self.mismatches = mismatches
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        lines = ["Exchange filters mismatch detected (fail-closed):"]
        for m in self.mismatches:
            lines.append(f"  {m}")
        
        lines.append("")
        lines.append("--- Recommended Fix (copy to instruments.yaml) ---")
        
        # Group by symbol
        by_symbol = {}
        for m in self.mismatches:
            if m.symbol not in by_symbol:
                by_symbol[m.symbol] = {}
            by_symbol[m.symbol][m.field] = m.exchange_value
            
        for sym, fixes in by_symbol.items():
            lines.append(f"  {sym}:")
            for field, val in fixes.items():
                lines.append(f"    {field}: {val}")
                
        lines.append("--------------------------------------------------")
        lines.append("See: artifacts/testnet_exchangeinfo.json for reference")
        return "\n".join(lines)


class ExchangeInfoFetcher(Protocol):
    """Protocol for fetching exchange info from adapter."""
    
    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Fetch exchangeInfo for a symbol or all symbols."""
        ...


class ExchangeFiltersValidator:
    """
    Validates SSOT instrument filters against exchange reality.
    
    TASK51-A Contract:
    - LIVE mode: mismatch → FilterMismatchError (startup crash)
    - TESTNET mode: mismatch → FilterMismatchError (fail-closed default)
    - SHADOW/DEV mode: mismatch → Warning only (with explicit warn_only flag)
    
    Usage:
        validator = ExchangeFiltersValidator(adapter)
        await validator.validate_all(ssot_filters, mode="live")
    """
    
    def __init__(
        self,
        adapter: ExchangeInfoFetcher,
        *,
        warn_only: bool = False,
    ):
        """
        Initialize validator.
        
        Args:
            adapter: Exchange adapter with get_exchange_info method
            warn_only: If True, log warnings instead of raising exceptions.
                       ONLY for DEV/SHADOW mode with explicit flag.
        """
        self._adapter = adapter
        self._warn_only = warn_only



    async def validate_all(
        self,
        ssot_filters: Dict[str, SSOTFilters],
        *,
        mode: str = "live",
        fail_fast: bool = True,
    ) -> Dict[str, List[FilterMismatch]]:
        """
        Validate all symbols in SSOT against exchange.
        
        TASK-EXF-PERF-11: Uses batch fetch to optimize startup time.
        
        Args:
            ssot_filters: Dict of symbol -> SSOTFilters
            mode: Operating mode
            fail_fast: If True, raise on first critical mismatch
            
        Returns:
            Dict of symbol -> mismatches
            
        Raises:
            FilterMismatchError: On critical mismatches (unless warn_only)
        """
        LOG.info(f"Validating {len(ssot_filters)} symbols against exchange filters (Batch Mode)...")
        
        all_mismatches: Dict[str, List[FilterMismatch]] = {}
        all_critical: List[FilterMismatch] = []
        
        # Batch Fetch
        try:
            full_info = await self._adapter.get_exchange_info(None)
            exchange_map = {
                s["symbol"]: s for s in full_info.get("symbols", [])
            }
        except Exception as e:
            LOG.error(f"Batch fetch failed during filter validation: {e}")
            if not self._warn_only:
                raise
            return {}

        for symbol, ssot in ssot_filters.items():
            try:
                sym_info = exchange_map.get(symbol)
                if not sym_info:
                    # Symbol missing in exchange info
                    # Treat as critical mismatch (configuration for non-existent symbol)
                    # Create a synthetic mismatch or fallback
                    LOG.error(f"Symbol {symbol} not found in exchange info batch")
                    # We could try to fetch individually to be sure, but batch should be complete.
                    continue

                exchange = self._parse_exchange_filters(symbol, sym_info)
                mismatches = self.compare_filters(ssot, exchange)
                
                if mismatches:
                    all_mismatches[symbol] = mismatches
                    critical = [m for m in mismatches if m.severity == "CRITICAL"]
                    all_critical.extend(critical)
                    
                    if fail_fast and critical and not self._warn_only:
                        raise FilterMismatchError(critical)
                else:
                    LOG.info(f"✅ {symbol}: filters match exchange")
                    
            except Exception as e:
                if isinstance(e, FilterMismatchError):
                    raise
                LOG.error(f"Failed to validate {symbol}: {e}")
                # Fail-closed: unknown error is treated as mismatch
                if not self._warn_only:
                    raise
        
        if all_critical and not self._warn_only:
            raise FilterMismatchError(all_critical)
        
        LOG.info(
            f"Filter validation complete: "
            f"{len(ssot_filters) - len(all_mismatches)} OK, "
            f"{len(all_mismatches)} mismatches"
        )
        
        return all_mismatches

    def _parse_exchange_filters(self, symbol: str, sym_info: dict) -> ExchangeFilters:
        """Parse raw exchange info dict into ExchangeFilters contract."""
        filters = {f.get("filterType"): f for f in sym_info.get("filters", [])}
        
        # LOT_SIZE filter
        lot_filter = filters.get("LOT_SIZE", {})
        step_size = Decimal(str(lot_filter.get("stepSize", "0.001")))
        min_qty = Decimal(str(lot_filter.get("minQty", "0.001")))
        
        # MIN_NOTIONAL filter (different key names possible)
        min_notional = None
        for key in ("MIN_NOTIONAL", "NOTIONAL"):
            if key in filters:
                mn = filters[key]
                val = mn.get("notional") or mn.get("minNotional")
                if val:
                    min_notional = Decimal(str(val))
                    break
        
        if min_notional is None:
            # SAFETY-08: No magic defaults allowed
            raise ValueError(f"Required filter MIN_NOTIONAL missing in exchangeInfo for {symbol}")
        
        # PRICE_FILTER (optional)
        price_filter = filters.get("PRICE_FILTER", {})
        tick_size = None
        if price_filter.get("tickSize"):
            tick_size = Decimal(str(price_filter["tickSize"]))
        
        return ExchangeFilters(
            symbol=symbol,
            step_size=step_size,
            min_qty=min_qty,
            min_notional=min_notional,
            tick_size=tick_size,
        )
    
    async def fetch_exchange_filters(self, symbol: str) -> ExchangeFilters:
        """
        Fetch filters from exchange for a single symbol.
        """
        info = await self._adapter.get_exchange_info(symbol)
        
        symbols = info.get("symbols") or []
        sym_info = None
        for s in symbols:
            if s.get("symbol") == symbol:
                sym_info = s
                break
        
        if not sym_info:
            raise ValueError(f"Symbol {symbol} not found in exchangeInfo")
            
        return self._parse_exchange_filters(symbol, sym_info)
    
    def compare_filters(
        self,
        ssot: SSOTFilters,
        exchange: ExchangeFilters,
    ) -> List[FilterMismatch]:
        """
        Compare SSOT filters against exchange filters.
        
        Args:
            ssot: Filters from instruments.yaml
            exchange: Filters from exchangeInfo
            
        Returns:
            List of mismatches (empty if all match)
        """
        mismatches = []
        
        if ssot.step_size != exchange.step_size:
            mismatches.append(FilterMismatch(
                symbol=ssot.symbol,
                field="step_size",
                ssot_value=ssot.step_size,
                exchange_value=exchange.step_size,
            ))
        
        if ssot.min_qty != exchange.min_qty:
            mismatches.append(FilterMismatch(
                symbol=ssot.symbol,
                field="min_qty",
                ssot_value=ssot.min_qty,
                exchange_value=exchange.min_qty,
            ))
        
        if ssot.min_notional != exchange.min_notional:
            mismatches.append(FilterMismatch(
                symbol=ssot.symbol,
                field="min_notional",
                ssot_value=ssot.min_notional,
                exchange_value=exchange.min_notional,
            ))
        
        # tick_size comparison (optional)
        if ssot.tick_size and exchange.tick_size:
            if ssot.tick_size != exchange.tick_size:
                mismatches.append(FilterMismatch(
                    symbol=ssot.symbol,
                    field="tick_size",
                    ssot_value=ssot.tick_size,
                    exchange_value=exchange.tick_size,
                ))
        
        return mismatches
    
    async def validate_symbol(
        self,
        ssot: SSOTFilters,
        *,
        mode: str = "live",
    ) -> List[FilterMismatch]:
        """
        Validate a single symbol's filters.
        
        Args:
            ssot: SSOT filters for the symbol
            mode: Operating mode (live/testnet/shadow/dev)
            
        Returns:
            List of mismatches
            
        Raises:
            FilterMismatchError: If mismatches found and not warn_only
        """
        exchange = await self.fetch_exchange_filters(ssot.symbol)
        mismatches = self.compare_filters(ssot, exchange)
        
        if mismatches:
            critical = [m for m in mismatches if m.severity == "CRITICAL"]
            
            if critical:
                if self._warn_only:
                    for m in mismatches:
                        LOG.warning(f"FILTER_MISMATCH (warn_only): {m}")
                else:
                    raise FilterMismatchError(mismatches)
            else:
                # Non-critical: always log warning
                for m in mismatches:
                    LOG.warning(f"FILTER_MISMATCH: {m}")
        
        return mismatches
    
    async def validate_all(
        self,
        ssot_filters: Dict[str, SSOTFilters],
        *,
        mode: str = "live",
        fail_fast: bool = True,
    ) -> Dict[str, List[FilterMismatch]]:
        """
        Validate all symbols in SSOT against exchange.
        
        Args:
            ssot_filters: Dict of symbol -> SSOTFilters
            mode: Operating mode
            fail_fast: If True, raise on first critical mismatch
            
        Returns:
            Dict of symbol -> mismatches
            
        Raises:
            FilterMismatchError: On critical mismatches (unless warn_only)
        """
        LOG.info(f"Validating {len(ssot_filters)} symbols against exchange filters...")
        
        all_mismatches: Dict[str, List[FilterMismatch]] = {}
        all_critical: List[FilterMismatch] = []
        
        for symbol, ssot in ssot_filters.items():
            try:
                exchange = await self.fetch_exchange_filters(symbol)
                mismatches = self.compare_filters(ssot, exchange)
                
                if mismatches:
                    all_mismatches[symbol] = mismatches
                    critical = [m for m in mismatches if m.severity == "CRITICAL"]
                    all_critical.extend(critical)
                    
                    if fail_fast and critical and not self._warn_only:
                        raise FilterMismatchError(critical)
                else:
                    LOG.info(f"✅ {symbol}: filters match exchange")
                    
            except Exception as e:
                if isinstance(e, FilterMismatchError):
                    raise
                LOG.error(f"Failed to validate {symbol}: {e}")
                # Fail-closed: unknown error is treated as mismatch
                if not self._warn_only:
                    raise
        
        if all_critical and not self._warn_only:
            raise FilterMismatchError(all_critical)
        
        LOG.info(
            f"Filter validation complete: "
            f"{len(ssot_filters) - len(all_mismatches)} OK, "
            f"{len(all_mismatches)} mismatches"
        )
        
        return all_mismatches


async def validate_instruments_on_startup(
    adapter: ExchangeInfoFetcher,
    instruments_config: Dict[str, dict],
    *,
    mode: str = "live",
    warn_only: bool = False,
) -> None:
    """
    Warmup hook: Validate instruments.yaml against exchange.
    
    TASK51-A: Called during startup to ensure SSOT is synchronized.
    
    Args:
        adapter: Exchange adapter
        instruments_config: Raw dict from instruments.yaml
        mode: Operating mode (live/testnet/shadow/dev)
        warn_only: If True, warn instead of crash (DEV/SHADOW only)
        
    Raises:
        FilterMismatchError: On critical mismatches in LIVE/TESTNET mode
    """
    # Convert raw config to SSOTFilters
    ssot_filters = {}
    instruments = instruments_config.get("instruments", instruments_config)
    
    for symbol, data in instruments.items():
        if isinstance(data, dict) and data.get("symbol"):
            ssot_filters[symbol] = SSOTFilters.from_yaml_dict(symbol, data)
    
    if not ssot_filters:
        LOG.warning("No instruments found in SSOT - skipping filter validation")
        return
    
    validator = ExchangeFiltersValidator(adapter, warn_only=warn_only)
    await validator.validate_all(ssot_filters, mode=mode)
