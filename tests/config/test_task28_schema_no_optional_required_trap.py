from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
import yaml

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
            assert not fi.is_required(), f"{model_cls.__name__}.{name} is Optional but required"


def _write_yaml(path: Path, obj: dict) -> None:
    path.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True), encoding="utf-8")


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
    _assert_no_optional_required(SystemRuntimeMeta, ["config_name", "config_dir"])
    _assert_no_optional_required(SystemMetaConfig, ["system_config_version", "regime_config_version", "runtime"])
    _assert_no_optional_required(SystemConfig, ["market_data"])

    # Root-level optional strategy/meta blocks
    _assert_no_optional_required(
        AuroraConfig,
        [
            "strategies_registry",
            "models",
        ],
    )

    # Domains is required (must not be Optional)
    domains_ann = AuroraConfig.model_fields["domains"].annotation
    assert not _is_optional_union(domains_ann), "AuroraConfig.domains must be required (not Optional)"


def test_loader_does_not_inject_required_optional_keys_before_validation(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve().parents[2] / "config" / "aurora").resolve()

    _copy_tree(repo_cfg, tmp_path)

    # Remove config_version keys so system_meta versions are absent in merged dict
    system_obj = yaml.safe_load((tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_obj.pop("config_version", None)
    _write_yaml(tmp_path / "system.yaml", system_obj)

    regime_obj = yaml.safe_load((tmp_path / "regime.yaml").read_text(encoding="utf-8"))
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
    assert "system_config_version" not in merged["system_meta"], "versions must not be setdefault-injected"
    assert "regime_config_version" not in merged["system_meta"], "versions must not be setdefault-injected"

    assert isinstance(merged.get("strategies"), dict), "strategy profiles must be loaded under root.strategies"
    assert merged["strategies"].get("aurora") is not None, "strategy profiles must be loaded from strategies.yaml (no null injection)"
    assert merged["strategies"].get("mean_reversion") is not None, "strategy profiles must be loaded from strategies.yaml (no null injection)"

    # Full load should still validate and then inject runtime meta post-validation
    cfg = loader.load_config()
    assert cfg.system_meta.runtime is not None
    assert cfg.system_meta.runtime.config_name == "aurora"
    assert cfg.system_meta.runtime.config_dir is not None


def test_symbols_to_track_policy_is_explicit_and_deterministic(tmp_path: Path) -> None:
    repo_cfg = (Path(__file__).resolve().parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    # Remove any legacy system.yaml trading.symbols_to_track (canonical is derived from strategies.yaml assignments)
    system_obj = yaml.safe_load((tmp_path / "system.yaml").read_text(encoding="utf-8"))
    assert isinstance(system_obj, dict)
    system_trading = system_obj.get("trading")
    if isinstance(system_trading, dict):
        system_trading.pop("symbols_to_track", None)
    _write_yaml(tmp_path / "system.yaml", system_obj)

    # Ensure trading.symbols_to_track is absent (loader derives it from strategies.yaml assignments)
    trading_obj = yaml.safe_load((tmp_path / "trading.yaml").read_text(encoding="utf-8"))
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
    repo_cfg = (Path(__file__).resolve().parents[2] / "config" / "aurora").resolve()
    _copy_tree(repo_cfg, tmp_path)

    # Inject legacy root guardian block
    trading_obj = yaml.safe_load((tmp_path / "trading.yaml").read_text(encoding="utf-8"))
    assert isinstance(trading_obj, dict)

    # Ensure execution.order_guardian is absent to avoid conflict
    trading_block = trading_obj.get("trading")
    assert isinstance(trading_block, dict)
    exec_block = trading_block.get("execution")
    if isinstance(exec_block, dict):
        exec_block.pop("order_guardian", None)

    trading_obj["guardian"] = {"enabled": True, "max_open_orders": 123}
    _write_yaml(tmp_path / "trading.yaml", trading_obj)

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
