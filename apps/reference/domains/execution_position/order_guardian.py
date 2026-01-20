"""
Domain wrapper for OrderGuardian.

Thin delegation layer to services/order_guardian with optional Ledger store.
No own cleanup logic remains here when unified mode is enabled.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from apps.reference.services.order_guardian import OrderGuardian as ServicesGuardian
from apps.reference.services.ledger_store_adapter import LedgerStoreAdapter
from apps.reference.domains.execution_position.infra.order_ledger import OrderLedger
from apps.reference.utils.accessors import aget


class OrderGuardian:
    """Domain wrapper delegating to services OrderGuardian."""

    @staticmethod
    def _resolve_guardian_cfg(cfg: Any) -> Any:
        """Resolve SSOT guardian config block from typed AuroraConfig."""
        if cfg is None:
            return None

        # NOTE: Many tests use MagicMock configs; attribute access on MagicMock
        # auto-creates nested mocks (truthy), which would incorrectly select a
        # non-real config block. Prefer explicitly-set attributes when possible.
        cfg_dict = getattr(cfg, "__dict__", None)

        exec_cfg = None
        if isinstance(cfg_dict, dict) and "execution" in cfg_dict:
            exec_cfg = cfg_dict.get("execution")
        else:
            try:
                exec_cfg = getattr(cfg, "execution", None)
            except Exception:
                exec_cfg = None

        if exec_cfg is not None:
            exec_dict = getattr(exec_cfg, "__dict__", None)
            if isinstance(exec_dict, dict) and "order_guardian" in exec_dict:
                og = exec_dict.get("order_guardian")
            else:
                try:
                    og = getattr(exec_cfg, "order_guardian", None)
                except Exception:
                    og = None
            if og is not None and (isinstance(og, dict) or isinstance(og, str)):
                return og
            if og is not None and not hasattr(cfg, "__getattr__"):
                return og

        trading = None
        if isinstance(cfg_dict, dict) and "trading" in cfg_dict:
            trading = cfg_dict.get("trading")
        else:
            try:
                trading = getattr(cfg, "trading", None)
            except Exception:
                trading = None

        trading_exec = getattr(trading, "execution", None) if trading is not None else None
        if trading_exec is not None:
            og = getattr(trading_exec, "order_guardian", None)
            if og is not None and (isinstance(og, dict) or isinstance(og, str)):
                return og

        # Legacy (non-SSOT) fallback
        legacy = None
        if isinstance(cfg_dict, dict) and "guardian" in cfg_dict:
            legacy = cfg_dict.get("guardian")
        else:
            try:
                legacy = getattr(cfg, "guardian", None)
            except Exception:
                legacy = None
        return legacy

    def __init__(
        self,
        adapter,
        config: Optional[Any] = None,
        poll_interval_ms: int = 0,
        bus: Optional[Any] = None,
    ):
        if isinstance(config, dict):
            raise TypeError("OrderGuardian requires typed config object, got dict")

        self._cfg = config or {}

        guardian_cfg = self._resolve_guardian_cfg(self._cfg)

        # Feature flag: execution.order_guardian.unified (default True)
        unified = True
        if guardian_cfg is not None:
            if isinstance(guardian_cfg, dict):
                unified = bool(guardian_cfg.get("unified", True))
            else:
                unified = bool(aget(guardian_cfg, "unified", True))

        store = None
        if unified:
            # Optional DB path for ledger
            db_path = None
            if guardian_cfg is not None:
                if isinstance(guardian_cfg, dict):
                    db_path = guardian_cfg.get("ledger_db_path")
                else:
                    db_path = aget(guardian_cfg, "ledger_db_path", None)

            # Ensure parent directory exists for persistent sqlite DB file.
            if isinstance(db_path, Path):
                db_path = str(db_path)
            if db_path and isinstance(db_path, str) and db_path != ":memory:":
                try:
                    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    # Best-effort only; OrderLedger init will surface errors if path is invalid.
                    pass
            elif not isinstance(db_path, str):
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
