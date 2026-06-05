from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.execution_position.guardian.order_guardian import InMemoryStore, OrderGuardian


class _ExplodingOrderLedger:
    def __init__(self, db_path: str) -> None:
        raise OSError(f"cannot open ledger at {db_path}")


class _FakeLedgerStoreAdapter:
    def __init__(self, ledger: object) -> None:
        self.ledger = ledger


def _root_only_config(order_guardian: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        execution=SimpleNamespace(order_guardian=order_guardian),
        trading=SimpleNamespace(
            execution=SimpleNamespace(order_guardian=None),
        ),
    )


def test_order_guardian_explicit_store_override_still_wins_over_config() -> None:
    store = InMemoryStore()
    cfg = _root_only_config(
        {"unified": True, "ledger_db_path": "data/order_ledger.db"})

    with patch(
        "apps.reference.domains.execution_position.guardian.order_guardian._get_ledger_store",
        side_effect=AssertionError(
            "explicit store override should bypass ledger construction"),
    ):
        guardian = OrderGuardian(
            adapter=None,
            store=store,
            config=cfg,
            poll_interval_ms=0,
        )

    assert guardian.store is store


def test_order_guardian_explicit_ledger_failure_raises_without_inmemory_fallback() -> None:
    cfg = _root_only_config(
        {"unified": True, "ledger_db_path": "data/bad/order_ledger.db"})

    with patch(
        "apps.reference.domains.execution_position.guardian.order_guardian._get_ledger_store",
        return_value=(_FakeLedgerStoreAdapter, _ExplodingOrderLedger),
    ):
        with pytest.raises(ValueError, match="No InMemoryStore fallback is allowed"):
            OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)


def test_order_guardian_explicit_ledger_import_failure_raises_without_inmemory_fallback() -> None:
    cfg = _root_only_config(
        {"unified": True, "ledger_db_path": "data/order_ledger.db"})

    with patch(
        "apps.reference.domains.execution_position.guardian.order_guardian._get_ledger_store",
        side_effect=ImportError("ledger adapter import failed"),
    ):
        with pytest.raises(ValueError, match="LedgerStoreAdapter"):
            OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)
