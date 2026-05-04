from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
import yaml

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig, SystemConfig, SystemMetaConfig, SystemRuntimeMeta


def _is_optional_union(tp: Any) -> bool:
    origin = get_origin(tp)
    _ = origin  # origin is not stable across typing/PEP604; rely on args
    return type(None) in get_args(tp)


def _assert_no_optional_required(model_cls: type, field_names: list[str] | None = None) -> None:
    fields = model_cls.model_fields
    names = field_names or list(fields.keys())
    for name in names:
        fi = fields[name]
        if _is_optional_union(fi.annotation):
            assert not fi.is_required(
            ), f"{model_cls.__name__}.{name} is Optional but required"


def _write_yaml(path: Path, obj: dict) -> None:
    path.write_text(yaml.safe_dump(obj, sort_keys=False,
                    allow_unicode=True), encoding="utf-8")


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


def test_optional_fields_have_defaults_or_not_optional_for_root_blocks() -> None:
    runtime_fields = SystemRuntimeMeta.model_fields
    assert _is_optional_union(runtime_fields["config_name"].annotation)
    assert runtime_fields["config_name"].is_required()
    assert _is_optional_union(runtime_fields["config_dir"].annotation)
    assert runtime_fields["config_dir"].is_required()

    meta_fields = SystemMetaConfig.model_fields
    assert _is_optional_union(meta_fields["system_config_version"].annotation)
    assert meta_fields["system_config_version"].is_required()
    assert _is_optional_union(meta_fields["regime_config_version"].annotation)
    assert meta_fields["regime_config_version"].is_required()
    assert _is_optional_union(meta_fields["runtime"].annotation)
    assert not meta_fields["runtime"].is_required()

    system_fields = SystemConfig.model_fields
    assert _is_optional_union(system_fields["market_data"].annotation)
    assert system_fields["market_data"].is_required()

    aurora_fields = AuroraConfig.model_fields
    assert _is_optional_union(aurora_fields["strategies_registry"].annotation)
    assert aurora_fields["strategies_registry"].is_required()
    assert _is_optional_union(aurora_fields["models"].annotation)
    assert aurora_fields["models"].is_required()

    # Domains is required (must not be Optional)
    domains_ann = AuroraConfig.model_fields["domains"].annotation
    assert not _is_optional_union(
        domains_ann), "AuroraConfig.domains must be required (not Optional)"


def test_loader_does_not_inject_required_optional_keys_before_validation(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve(
    ).parents[2] / "config" / "aurora").resolve()

    _copy_tree(repo_cfg, tmp_path)

    # Remove config_version keys so system_meta versions are absent in merged dict
    system_obj = yaml.safe_load(
        (tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_obj.pop("config_version", None)
    _write_yaml(tmp_path / "system.yaml", system_obj)

    regime_obj = yaml.safe_load(
        (tmp_path / "regime.yaml").read_text(encoding="utf-8"))
    assert isinstance(regime_obj, dict)
    regime_obj.pop("config_version", None)
    _write_yaml(tmp_path / "regime.yaml", regime_obj)

    # Keep canonical strategies.yaml assignments:
    # CFG-STRATEGY-SSOT-FREEZE-03 makes strategies.yaml mandatory for startup.

    loader = ConfigLoader(config_dir=tmp_path)

    # Build pre-validation merged dict (no runtime injection, no setdefault hydration)
    system_config = loader._load_yaml("system.yaml")
    trading_config = loader._load_yaml("trading.yaml")
    regime_config = loader._load_yaml("regime.yaml")
    domains_config = loader._load_yaml("domains.yaml")
    system_meta = loader._extract_system_meta(system_config, regime_config)

    merged = loader._merge_config_fragments(
        system_config=system_config,
        trading_config=trading_config,
        regime_config=regime_config,
        domains_config=domains_config,
        system_meta=system_meta,
    )

    assert "system_meta" in merged and isinstance(merged["system_meta"], dict)
    assert "runtime" not in merged["system_meta"], "runtime meta must not be injected pre-validation"
    assert merged["system_meta"]["system_config_version"] is None
    assert merged["system_meta"]["regime_config_version"] is None

    assert isinstance(merged.get(
        "strategies"), dict), "strategy profiles must be loaded under root.strategies"
    assert merged["strategies"].get(
        "aurora") is not None, "strategy profiles must be loaded from strategies.yaml (no null injection)"
    assigned_strategy_ids: set[str] = set()
    assignments = merged.get("strategies_registry", {}).get("assignments", {})
    if isinstance(assignments, dict):
        for per_symbol in assignments.values():
            if isinstance(per_symbol, list):
                for strategy_id in per_symbol:
                    if isinstance(strategy_id, str):
                        assigned_strategy_ids.add(strategy_id)
    if "mean_reversion" in assigned_strategy_ids:
        assert merged["strategies"].get("mean_reversion") is not None, (
            "assigned strategy profile mean_reversion must be loaded from strategies.yaml"
        )

    # Full load should still validate and then inject runtime meta post-validation
    cfg = loader.load_config()
    assert cfg.system_meta.runtime is not None
    assert cfg.system_meta.runtime.config_name == "aurora"
    assert cfg.system_meta.runtime.config_dir is not None


def test_symbols_to_track_policy_is_explicit_and_deterministic(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve(
    ).parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    # Remove any legacy system.yaml trading.symbols_to_track (canonical is derived from strategies.yaml assignments)
    system_obj = yaml.safe_load(
        (tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_trading = system_obj.get("trading")
    if isinstance(system_trading, dict):
        system_trading.pop("symbols_to_track", None)
    _write_yaml(tmp_path / "system.yaml", system_obj)

    # Ensure trading.symbols_to_track is absent (loader derives it from strategies.yaml assignments)
    trading_obj = yaml.safe_load(
        (tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)
    trading_block = trading_obj.get("trading")
    assert isinstance(trading_block, dict)
    trading_block.pop("symbols_to_track", None)
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

    loader = ConfigLoader(config_dir=tmp_path)
    cfg1 = loader.load_config()
    cfg2 = loader.load_config()

    assert cfg1.strategies_registry is not None
    expected = sorted(cfg1.strategies_registry.assignments.keys())
    assert expected

    assert cfg1.trading.symbols_to_track == expected
    assert cfg2.trading.symbols_to_track == expected


def test_guardian_migration_only_allowed_root_mutation(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve(
    ).parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    # Inject legacy root guardian block
    trading_obj = yaml.safe_load(
        (tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)

    # Ensure execution.order_guardian is absent to avoid conflict
    trading_block = trading_obj.get("trading")
    assert isinstance(trading_block, dict)
    exec_block = trading_block.get("execution")
    if isinstance(exec_block, dict):
        exec_block.pop("order_guardian", None)
    root_exec = trading_obj.get("execution")
    if isinstance(root_exec, dict):
        root_exec.pop("order_guardian", None)

    trading_obj["guardian"] = {"enabled": True, "max_open_orders": 123}
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

    system_obj = yaml.safe_load(
        (tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_exec = system_obj.get("execution")
    if isinstance(system_exec, dict):
        system_exec.pop("order_guardian", None)
    _write_yaml(tmp_path / "system.yaml", system_obj)

    loader = ConfigLoader(config_dir=tmp_path)

    system_config = loader._load_yaml("system.yaml")
    regime_config = loader._load_yaml("regime.yaml")
    system_meta = loader._extract_system_meta(system_config, regime_config)
    merged = loader._merge_config_fragments(
        system_config=system_config,
        trading_config=loader._load_yaml("trading.yaml"),
        regime_config=regime_config,
        domains_config=loader._load_yaml("domains.yaml"),
        system_meta=system_meta,
    )

    assert "guardian" in merged, "guardian must exist before allowlisted migration"

    cfg = loader.load_config()

    dumped = cfg.model_dump()
    assert "guardian" not in dumped, "legacy guardian must not survive validation"

    # Allowlisted migration target
    assert cfg.execution is not None
    assert isinstance(cfg.execution.order_guardian, dict)
    assert cfg.execution.order_guardian.get("enabled") is True
    assert cfg.execution.order_guardian.get("max_open_orders") == 123


@pytest.mark.parametrize(
    ("system_guardian", "trading_guardian"),
    [
        ({"unified": True, "ledger_db_path": "data/shared_order_ledger.db"}, None),
        (None, {"unified": True, "ledger_db_path": "data/shared_order_ledger.db"}),
        (
            {"unified": True, "ledger_db_path": "data/shared_order_ledger.db"},
            {"unified": True, "ledger_db_path": "data/shared_order_ledger.db"},
        ),
    ],
)
def test_order_guardian_surfaces_load_when_non_conflicting(
    tmp_path: Path,
    system_guardian: dict[str, Any] | None,
    trading_guardian: dict[str, Any] | None,
) -> None:
    repo_cfg = (Path(__file__).resolve(
    ).parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    system_obj = yaml.safe_load(
        (tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_exec = system_obj.get("execution")
    assert isinstance(system_exec, dict)
    system_exec["order_guardian"] = system_guardian
    _write_yaml(tmp_path / "system.yaml", system_obj)

    trading_obj = yaml.safe_load(
        (tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)
    trading_block = trading_obj.get("trading")
    assert isinstance(trading_block, dict)
    trading_exec = trading_block.get("execution")
    assert isinstance(trading_exec, dict)
    trading_exec["order_guardian"] = trading_guardian
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

    cfg = ConfigLoader(config_dir=tmp_path).load_config()

    assert cfg.execution is not None
    assert cfg.trading is not None
    assert cfg.trading.execution is not None
    assert cfg.execution.order_guardian == system_guardian
    assert cfg.trading.execution.order_guardian == trading_guardian


def test_order_guardian_surfaces_fail_when_divergent_at_config_load(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve(
    ).parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    system_obj = yaml.safe_load(
        (tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_exec = system_obj.get("execution")
    assert isinstance(system_exec, dict)
    system_exec["order_guardian"] = {
        "unified": True,
        "ledger_db_path": "data/root_order_ledger.db",
    }
    _write_yaml(tmp_path / "system.yaml", system_obj)

    trading_obj = yaml.safe_load(
        (tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)
    trading_block = trading_obj.get("trading")
    assert isinstance(trading_block, dict)
    trading_exec = trading_block.get("execution")
    assert isinstance(trading_exec, dict)
    trading_exec["order_guardian"] = {
        "unified": False,
        "ledger_db_path": "data/trading_order_ledger.db",
    }
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

    with pytest.raises(ConfigContractError, match=r"execution\.order_guardian") as exc_info:
        ConfigLoader(config_dir=tmp_path).load_config()

    message = str(exc_info.value)
    assert "trading.execution.order_guardian" in message
    assert "differ" in message


def test_root_guardian_conflict_with_existing_order_guardian_still_fails(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve(
    ).parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    trading_obj = yaml.safe_load(
        (tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)
    trading_obj["guardian"] = {"enabled": True, "max_open_orders": 123}
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

    with pytest.raises(ConfigContractError, match=r"legacy root\.guardian") as exc_info:
        ConfigLoader(config_dir=tmp_path).load_config()

    assert "execution.order_guardian" in str(exc_info.value)
