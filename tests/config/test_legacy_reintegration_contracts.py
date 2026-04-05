import shutil
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AbsorptionConfig
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


class _DummyFSM:
    def listen(self, *_args, **_kwargs) -> None:
        return None

    def emit(self, *_args, **_kwargs) -> None:
        return None


def test_absorption_legacy_alias_migrates_to_proxy_dp_cap_pct() -> None:
    cfg = AbsorptionConfig.model_validate(
        {
            "mode": "proxy",
            "dp_cap_pct": 0.07,
            "proxy": {
                "source": "aggressive_trade_imbalance",
                "window": 30,
                "eps": 0.0001,
            },
        }
    )

    assert cfg.proxy is not None
    assert cfg.proxy.dp_cap_pct == pytest.approx(0.07)


def test_md_amr_profile_loads_when_assigned_in_registry(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["BTCUSDT"] = ["aurora", "md_amr"]
    _write_yaml(strategies_path, strategies_data)

    config = ConfigLoader(config_dir=cfg_dir).load_config()

    assert config.strategies.md_amr is not None
    assert config.strategies_registry is not None
    assert config.strategies_registry.assignments["BTCUSDT"] == [
        "aurora", "md_amr"]
    assert config.strategies_registry.arbitration.priority["md_amr"] == 3


def test_bracket_health_uses_md_amr_exit_profile(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["BTCUSDT"] = ["aurora", "md_amr"]
    _write_yaml(strategies_path, strategies_data)
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    ep = ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)
    ep._open_strategy_by_symbol["BTCUSDT"] = "md_amr"
    ep._last_regime_by_symbol["BTCUSDT"] = "LOW_VOLATILITY"

    sl_price, tp_price = ep._compute_health_check_brackets(
        symbol="BTCUSDT",
        entry_price=100.0,
        side="BUY",
    )

    assert sl_price == pytest.approx(99.6, abs=0.11)
    assert tp_price == pytest.approx(100.6, abs=0.11)


def test_bracket_health_uses_aurora_registry_assignment_for_eth_recovery(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["ETHUSDT"] = ["aurora"]
    _write_yaml(strategies_path, strategies_data)
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    ep = ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)
    ep._last_regime_by_symbol["ETHUSDT"] = "DEFAULT"

    owner_context = ep._resolve_health_check_bracket_context(
        symbol="ETHUSDT",
        entry_price=100.0,
        side="BUY",
    )

    assert owner_context["strategy_id"] == "aurora"
    assert owner_context["strategy_source"] == "registry_assignment"
    assert owner_context["owner_status"] == "resolved"
    assert owner_context["sl_price"] is not None
    assert owner_context["tp_price"] is not None
    assert owner_context["sl_price"] < 100.0 < owner_context["tp_price"]


def test_bracket_health_uses_registry_assignment_when_runtime_owner_missing(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["BTCUSDT"] = ["md_amr"]
    _write_yaml(strategies_path, strategies_data)
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    ep = ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)
    ep._last_regime_by_symbol["BTCUSDT"] = "LOW_VOLATILITY"

    owner_context = ep._resolve_health_check_bracket_context(
        symbol="BTCUSDT",
        entry_price=100.0,
        side="BUY",
    )

    assert owner_context["strategy_id"] == "md_amr"
    assert owner_context["strategy_source"] == "registry_assignment"
    assert owner_context["owner_status"] == "resolved"
    assert owner_context["sl_price"] == pytest.approx(99.6, abs=0.11)
    assert owner_context["tp_price"] == pytest.approx(100.6, abs=0.11)


def test_bracket_health_uses_md_amr_registry_assignment_for_xrp_recovery(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["XRPUSDT"] = ["md_amr"]
    _write_yaml(strategies_path, strategies_data)
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    ep = ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)
    ep._last_regime_by_symbol["XRPUSDT"] = "DEFAULT"

    owner_context = ep._resolve_health_check_bracket_context(
        symbol="XRPUSDT",
        entry_price=1.0,
        side="BUY",
    )

    assert owner_context["strategy_id"] == "md_amr"
    assert owner_context["strategy_source"] == "registry_assignment"
    assert owner_context["owner_status"] == "resolved"
    assert owner_context["sl_price"] is not None
    assert owner_context["tp_price"] is not None
    assert owner_context["sl_price"] < 1.0 < owner_context["tp_price"]


def test_bracket_health_mean_reversion_recovery_fails_closed_without_aurora_fallback(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["DOGEUSDT"] = ["mean_reversion"]
    _write_yaml(strategies_path, strategies_data)
    config = ConfigLoader(config_dir=cfg_dir).load_config()

    ep = ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)
    ep._open_strategy_by_symbol["DOGEUSDT"] = "aurora"
    ep._last_regime_by_symbol["DOGEUSDT"] = "DEFAULT"

    owner_context = ep._resolve_health_check_bracket_context(
        symbol="DOGEUSDT",
        entry_price=0.1,
        side="BUY",
    )

    assert owner_context["strategy_id"] == "mean_reversion"
    assert owner_context["strategy_source"] == "registry_assignment"
    assert owner_context["owner_status"] == "resolved"
    assert owner_context["sl_price"] is None
    assert owner_context["tp_price"] is None
    assert "unsupported_recovery_strategy:mean_reversion" in str(
        owner_context.get("detail") or "")


def test_feature_engineering_legacy_log_sampling_is_runtime_controlled(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    domains_path = cfg_dir / "domains.yaml"
    domains_data = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains_data["feature_engineering"]["legacy_features_log"] = {
        "mode": "sample",
        "sample_every_n": 2,
    }
    _write_yaml(domains_path, domains_data)

    config = ConfigLoader(config_dir=cfg_dir).load_config()
    fe = FeatureEngineering(_DummyFSM(), config)
    fe._feature_logs_dir = str(tmp_path)

    fe._log_features_to_file("BTCUSDT", {"seq": 1})
    fe._log_features_to_file("BTCUSDT", {"seq": 2})

    log_path = tmp_path / "BTCUSDT.log"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"seq": 2' in lines[0]
