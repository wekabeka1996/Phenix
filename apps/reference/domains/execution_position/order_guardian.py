"""
Domain wrapper for OrderGuardian.

Thin delegation layer to services/order_guardian with optional Ledger store.
No own cleanup logic remains here when unified mode is enabled.
"""

from __future__ import annotations

from typing import Any, Optional

from apps.reference.services.order_guardian import OrderGuardian as ServicesGuardian
from apps.reference.services.ledger_store_adapter import LedgerStoreAdapter
from apps.clean_TP_SL.order_ledger import OrderLedger


class OrderGuardian:
    """Domain wrapper delegating to services OrderGuardian."""

    def __init__(
        self,
        adapter,
        config: Optional[Any] = None,
        poll_interval_ms: int = 0,
        bus: Optional[Any] = None,
    ):
        self._cfg = config or {}

        # Feature flag: guardian.unified (default True)
        unified = True
        try:
            if hasattr(self._cfg, 'guardian') and self._cfg.guardian:
                unified = bool(getattr(self._cfg.guardian, 'unified', True))
            elif isinstance(self._cfg, dict):
                unified = bool(self._cfg.get(
                    'guardian', {}).get('unified', True))
        except Exception:
            unified = True

        store = None
        if unified:
            # Optional DB path for ledger
            db_path = None
            try:
                if hasattr(self._cfg, 'guardian') and self._cfg.guardian:
                    db_path = getattr(self._cfg.guardian,
                                      'ledger_db_path', None)
                elif isinstance(self._cfg, dict):
                    db_path = self._cfg.get(
                        'guardian', {}).get('ledger_db_path')
            except Exception:
                db_path = None

            ledger = OrderLedger(db_path or ":memory:")
            store = LedgerStoreAdapter(ledger)

        # Always use services guardian; if not unified, fall back to in-memory store
        self._impl = ServicesGuardian(
            adapter=adapter,
            clock=None,
            store=store,  # None => InMemory store within services guardian
            poll_interval_ms=poll_interval_ms,
            bus=bus,
            config=self._cfg,
        )

    # Delegate API
    def register_entry(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return self._impl.register_entry(**kwargs)

    # type: ignore[no-untyped-def]
    def register_brackets(self, **kwargs) -> None:
        return self._impl.register_brackets(**kwargs)

    # type: ignore[no-untyped-def]
    async def should_place_brackets(self, *args, **kwargs):
        return await self._impl.should_place_brackets(*args, **kwargs)

    # type: ignore[no-untyped-def]
    def get_brackets_for_entry(self, *args, **kwargs):
        return self._impl.get_brackets_for_entry(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def get_our_open_brackets(self, *args, **kwargs):
        return await self._impl.get_our_open_brackets(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def cleanup_before_close(self, *args, **kwargs):
        return await self._impl.cleanup_before_close(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def cleanup_orphans(self, *args, **kwargs):
        return await self._impl.cleanup_orphans(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def reconcile_symbol(self, *args, **kwargs):
        return await self._impl.reconcile_symbol(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def cleanup_other_brackets_for_symbol(self, *args, **kwargs):
        return await self._impl.cleanup_other_brackets_for_symbol(*args, **kwargs)

    async def start(self):
        return await self._impl.start()

    async def stop(self):
        return await self._impl.stop()

    @property
    def poll_interval_ms(self) -> int:
        """Expose poll_interval_ms from underlying implementation."""
        return self._impl.poll_interval_ms

    def update_known_symbols(self, symbols: set[str]) -> None:
        """Best-effort propagation of configured symbols into services guardian."""
        try:
            self._impl.update_known_symbols(symbols)
        except AttributeError:
            pass

    def get_metrics(self) -> dict[str, Any]:
        """Expose guardian metrics for statdump aggregation."""
        try:
            return self._impl.get_metrics()
        except AttributeError:
            return {}
