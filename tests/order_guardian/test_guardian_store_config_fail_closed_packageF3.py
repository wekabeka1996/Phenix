from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.order_guardian import InMemoryStore, OrderGuardian


CONFIG_DIR = Path("config/aurora")


class _FakeOrderLedger:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path


class _FakeLedgerStoreAdapter:
    def __init__(self, ledger: _FakeOrderLedger) -> None:
        self.ledger = ledger


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())


def _write_yaml(path: Path, obj: dict) -> None:
    path.write_text(
        yaml.safe_dump(obj, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _root_only_config(order_guardian: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        execution=SimpleNamespace(order_guardian=order_guardian),
        trading=SimpleNamespace(
            execution=SimpleNamespace(order_guardian=None)),
    )


def test_order_guardian_config_none_keeps_manual_inmemory_store_path() -> None:
    guardian = OrderGuardian(adapter=None, poll_interval_ms=0)

    assert isinstance(guardian.store, InMemoryStore)


def test_order_guardian_explicit_unified_true_builds_ledger_store(tmp_path: Path) -> None:
    db_path = str(tmp_path / "order_ledger.sqlite")
    cfg = _root_only_config({"unified": True, "ledger_db_path": db_path})

    with patch(
        "apps.reference.domains.execution_position.order_guardian._get_ledger_store",
        return_value=(_FakeLedgerStoreAdapter, _FakeOrderLedger),
    ):
        guardian = OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)

    assert isinstance(guardian.store, _FakeLedgerStoreAdapter)
    assert guardian.store.ledger.db_path == db_path


def test_order_guardian_explicit_unified_false_keeps_inmemory_store() -> None:
    cfg = _root_only_config(
        {"unified": False, "ledger_db_path": "ignored.sqlite"})

    guardian = OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)

    assert isinstance(guardian.store, InMemoryStore)


def test_order_guardian_missing_store_config_raises_fail_closed() -> None:
    cfg = _root_only_config(None)

    with pytest.raises(ValueError, match="store config is required"):
        OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)


def test_order_guardian_unified_true_requires_explicit_ledger_path() -> None:
    cfg = _root_only_config({"unified": True})

    with pytest.raises(ValueError, match="ledger_db_path"):
        OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)


def test_order_guardian_constructor_still_fails_fast_on_divergent_surfaces() -> None:
    cfg = SimpleNamespace(
        execution=SimpleNamespace(
            order_guardian={"unified": True, "ledger_db_path": ":memory:"}
        ),
        trading=SimpleNamespace(
            execution=SimpleNamespace(
                order_guardian={"unified": False, "ledger_db_path": ":memory:"}
            )
        ),
    )

    with pytest.raises(ValueError, match=r"execution\.order_guardian"):
        OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)


def test_order_guardian_current_repo_config_still_builds_store() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    with patch(
        "apps.reference.domains.execution_position.order_guardian._get_ledger_store",
        return_value=(_FakeLedgerStoreAdapter, _FakeOrderLedger),
    ):
        guardian = OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)

    assert cfg.execution is not None
    assert isinstance(guardian.store, _FakeLedgerStoreAdapter)
    assert guardian.store.ledger.db_path == cfg.execution.order_guardian["ledger_db_path"]


def test_order_guardian_root_guardian_migration_still_builds_store(tmp_path: Path) -> None:
    _copy_tree(CONFIG_DIR.resolve(), tmp_path)

    trading_obj = yaml.safe_load(
        (tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)
    trading_block = trading_obj.get("trading")
    assert isinstance(trading_block, dict)
    trading_exec = trading_block.get("execution")
    if isinstance(trading_exec, dict):
        trading_exec.pop("order_guardian", None)
    root_exec = trading_obj.get("execution")
    if isinstance(root_exec, dict):
        root_exec.pop("order_guardian", None)
    trading_obj["guardian"] = {"unified": True, "ledger_db_path": ":memory:"}
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

    system_obj = yaml.safe_load(
        (tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_exec = system_obj.get("execution")
    if isinstance(system_exec, dict):
        system_exec.pop("order_guardian", None)
    _write_yaml(tmp_path / "system.yaml", system_obj)

    cfg = ConfigLoader(config_dir=tmp_path).load_config()

    with patch(
        "apps.reference.domains.execution_position.order_guardian._get_ledger_store",
        return_value=(_FakeLedgerStoreAdapter, _FakeOrderLedger),
    ):
        guardian = OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0)

    assert isinstance(guardian.store, _FakeLedgerStoreAdapter)
    assert guardian.store.ledger.db_path == ":memory:"
