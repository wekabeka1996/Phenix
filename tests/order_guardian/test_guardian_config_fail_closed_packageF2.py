from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.order_guardian import OrderGuardian


CONFIG_DIR = Path("config/aurora")


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


def test_order_guardian_resolve_guardian_cfg_allows_aligned_root_and_trading() -> None:
    shared = {"unified": True, "ledger_db_path": ":memory:"}
    cfg = SimpleNamespace(
        execution=SimpleNamespace(order_guardian=dict(shared)),
        trading=SimpleNamespace(
            execution=SimpleNamespace(order_guardian=dict(shared))
        ),
    )

    resolved = OrderGuardian._resolve_guardian_cfg(cfg)

    assert resolved == shared


def test_order_guardian_resolve_guardian_cfg_raises_on_conflict() -> None:
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
        OrderGuardian._resolve_guardian_cfg(cfg)


def test_order_guardian_resolve_guardian_cfg_matches_current_repo_config() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    assert cfg.execution is not None
    assert cfg.trading is not None
    assert cfg.trading.execution is not None
    assert cfg.execution.order_guardian == cfg.trading.execution.order_guardian
    assert OrderGuardian._resolve_guardian_cfg(
        cfg) == cfg.execution.order_guardian


def test_order_guardian_legacy_root_guardian_migration_still_resolves(tmp_path: Path) -> None:
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

    assert cfg.execution is not None
    assert cfg.execution.order_guardian == {
        "unified": True, "ledger_db_path": ":memory:"}
    assert OrderGuardian._resolve_guardian_cfg(
        cfg) == cfg.execution.order_guardian
