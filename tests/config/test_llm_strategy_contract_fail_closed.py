import shutil
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _set_llm_mode(cfg_dir: Path, *, symbols_llm: list[str], allowlist: list[str]) -> None:
    trading_path = cfg_dir / "trading.yaml"
    trading_data = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    trading_block = trading_data.setdefault("trading", {})
    trading_block["llm_orchestration"] = {
        "mode": "hybrid_advisory",
        "llm_role": "advisory",
        "require_telemetry": False,
        "symbols_llm": symbols_llm,
        "allowlist_symbols": allowlist,
        "intent_policy": {
            "max_open_intents": 3,
            "cooldown_sec": 30,
            "allow_limit_only": True,
            "require_tp_sl": True,
            "max_notional_usd": 100.0,
            "max_qty": 2.0,
            "max_price_deviation_bps": 20.0,
            "allowed_tif": ["GTC"],
        },
    }
    _write_yaml(trading_path, trading_data)


def test_llm_mode_rejects_missing_strategy_profile_when_enabled(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _set_llm_mode(cfg_dir, symbols_llm=["BNBUSDT"], allowlist=["BNBUSDT"])

    llm_profile = cfg_dir / "strategies" / "llm_microstructure.yaml"
    llm_profile.unlink()

    with pytest.raises(ValueError, match=r"strategy_config_missing\(llm_microstructure\)"):
        ConfigLoader(config_dir=cfg_dir).load_config()


def test_llm_mode_rejects_unassigned_owned_symbol(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _set_llm_mode(cfg_dir, symbols_llm=["BNBUSDT"], allowlist=["BNBUSDT"])

    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["BTCUSDT"] = ["llm_microstructure"]
    _write_yaml(strategies_path, strategies_data)

    with pytest.raises(ValueError, match=r"llm_microstructure not assigned for symbol BNBUSDT"):
        ConfigLoader(config_dir=cfg_dir).load_config()


def test_llm_mode_loads_llm_strategy_when_symbol_is_assigned(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _set_llm_mode(cfg_dir, symbols_llm=["BNBUSDT"], allowlist=["BNBUSDT"])

    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["BNBUSDT"] = ["llm_microstructure"]
    _write_yaml(strategies_path, strategies_data)

    config = ConfigLoader(config_dir=cfg_dir).load_config()

    assert config.trading.llm_orchestration.mode == "hybrid_advisory"
    assert config.trading.llm_orchestration.symbols_llm == ["BNBUSDT"]
    assert config.strategies.llm_microstructure is not None
