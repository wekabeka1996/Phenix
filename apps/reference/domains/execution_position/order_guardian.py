"""
Domain wrapper for OrderGuardian.

Thin delegation layer to services/order_guardian with optional Ledger store.
No own cleanup logic remains here when unified mode is enabled.
"""

from __future__ import annotations

from typing import Any, Optional

from apps.reference.services.order_guardian import (
    OrderGuardian as ServicesGuardian,
    AggregatedOcoGuardianConfig,
    BracketSetMeta,
)
from apps.reference.services.ledger_store_adapter import LedgerStoreAdapter
from apps.clean_TP_SL.order_ledger import OrderLedger
from apps.reference.domains.execution_position.manage_config import (
    resolve_execution_manage_config,
)


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
        self._aggregated_guardian_cfg = self._resolve_aggregated_cfg()

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

            # Use file-based DB for thread safety (instead of :memory:)
            if db_path is None:
                import tempfile
                import os
                db_dir = os.path.join(tempfile.gettempdir(), 'phenix_ledger')
                os.makedirs(db_dir, exist_ok=True)
                db_path = os.path.join(db_dir, 'order_ledger.db')

            ledger = OrderLedger(db_path)
            store = LedgerStoreAdapter(ledger)

        # Always use services guardian; if not unified, fall back to in-memory store
        self._impl = ServicesGuardian(
            adapter=adapter,
            clock=None,
            store=store,  # None => InMemory store within services guardian
            poll_interval_ms=poll_interval_ms,
            bus=bus,
            config=self._cfg,
            aggregated_oco_cfg=self._aggregated_guardian_cfg,
        )

    # Delegate API
    def register_entry(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return self._impl.register_entry(**kwargs)

    # type: ignore[no-untyped-def]
    def register_brackets(self, **kwargs) -> None:
        return self._impl.register_brackets(**kwargs)

    # type: ignore[no-untyped-def]
    def on_fill(self, **kwargs) -> None:
        """Proxy to services guardian on_fill (per-entry fill tracking)."""
        return self._impl.on_fill(**kwargs)

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
    async def close_entry(self, *args, **kwargs):
        """Cancel brackets and report remaining qty/side for an entry."""
        return await self._impl.close_entry(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def cleanup_orphans(self, *args, **kwargs):
        return await self._impl.cleanup_orphans(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def reconcile_symbol(self, *args, **kwargs):
        return await self._impl.reconcile_symbol(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def cleanup_other_brackets_for_symbol(self, *args, **kwargs):
        return await self._impl.cleanup_other_brackets_for_symbol(*args, **kwargs)

    # type: ignore[no-untyped-def]
    def rehydrate_bracket_set_for_position(self, *args, **kwargs):
        return self._impl.rehydrate_bracket_set_for_position(*args, **kwargs)

    # type: ignore[no-untyped-def]
    async def link_existing_from_rest(self, *args, **kwargs):
        return await self._impl.link_existing_from_rest(*args, **kwargs)

    def list_entries(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        """List tracked entries (optionally by symbol)."""
        return self._impl.list_entries(*args, **kwargs)

    def list_bracket_sets(self) -> list[BracketSetMeta]:
        """Expose aggregated bracket metadata for diagnostics/watchdog."""

        try:
            return self._impl.list_all_bracket_sets()
        except AttributeError:
            return []

    async def start(self):
        return await self._impl.start()

    async def stop(self):
        return await self._impl.stop()

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

    def _resolve_aggregated_cfg(self) -> AggregatedOcoGuardianConfig:
        """Project execution.manage.brackets.aggregated_oco into guardian config."""
        try:
            manage_cfg = resolve_execution_manage_config(self._cfg)
        except Exception:
            return AggregatedOcoGuardianConfig()

        try:
            agg_meta = manage_cfg.brackets.aggregated_oco
        except Exception:
            agg_meta = None

        if not agg_meta or not getattr(agg_meta, "enabled", False):
            return AggregatedOcoGuardianConfig()

        ttl_ms = int(getattr(agg_meta, "ttl_protect_new_bracket_ms", 0) or 0)
        allow_unprotected = bool(
            getattr(agg_meta, "allow_unprotected_position", False)
        )

        return AggregatedOcoGuardianConfig(
            enabled=True,
            ttl_protect_new_bracket_ms=ttl_ms,
            allow_unprotected_position=allow_unprotected,
        )
