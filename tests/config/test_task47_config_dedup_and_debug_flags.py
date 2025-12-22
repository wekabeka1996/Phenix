import shutil
from pathlib import Path

import pytest
import yaml

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_task47_duplicate_paths_fail_closed(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    _write_yaml(
        cfg_dir / "system.yaml",
        {
            "trading_mode": "testnet",
            "system": {"logging": {"level": "INFO", "file": "x", "format": "json", "rotation": {"max_bytes": 1, "backup_count": 1}}},
            "ops": {"panic_killswitch": True, "panic_ttl_sec": None, "quiet_hours_utc": [], "allowlist_symbols": [], "metrics_url": "x", "reports_dir": "x"},
            "bridge": {"retry_scheduler": {"max_attempts": 1, "min_retry_delay_ms": 1, "backoff_factor": 1.0, "jitter_ms": 0}},
            "trading": {"market_data": {"websocket_streams": ["trade"]}},
        },
    )
    _write_yaml(
        cfg_dir / "trading.yaml",
        {"trading": {"mode": "testnet", "market_data": {"websocket_streams": ["trade"]}}},
    )
    _write_yaml(cfg_dir / "regime.yaml", {"hmm": {}, "features": {}, "hotreload_whitelist": []})
    _write_yaml(cfg_dir / "domains.yaml", {"debug": {"disable_positions_stale_gate": False, "disable_daily_loss_limit": False}})

    loader = ConfigLoader(config_dir=cfg_dir)
    with pytest.raises(ConfigContractError) as ei:
        loader.load_config()

    assert "Duplicate config paths" in str(ei.value)
    assert "trading.market_data.websocket_streams" in str(ei.value)


def test_task47_debug_disables_forbidden_in_live_mode(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)

    system_path = cfg_dir / "system.yaml"
    system = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    system["trading_mode"] = "live"
    system_path.write_text(yaml.safe_dump(system, sort_keys=False), encoding="utf-8")

    trading_path = cfg_dir / "trading.yaml"
    trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    trading["trading"]["mode"] = "live"
    trading_path.write_text(yaml.safe_dump(trading, sort_keys=False), encoding="utf-8")

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains.setdefault("debug", {})
    domains["debug"]["disable_positions_stale_gate"] = True
    domains_path.write_text(yaml.safe_dump(domains, sort_keys=False), encoding="utf-8")

    loader = ConfigLoader(config_dir=cfg_dir)
    with pytest.raises(ConfigContractError) as ei:
        loader.load_config()

    assert "domains.debug.disable_positions_stale_gate" in str(ei.value)


def test_task47_debug_disables_allowed_in_testnet_mode(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)

    # Ensure testnet execution mode + enable flag.
    trading_path = cfg_dir / "trading.yaml"
    trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    trading["trading"]["mode"] = "testnet"
    trading_path.write_text(yaml.safe_dump(trading, sort_keys=False), encoding="utf-8")

    domains_path = cfg_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains.setdefault("debug", {})
    domains["debug"]["disable_positions_stale_gate"] = True
    domains_path.write_text(yaml.safe_dump(domains, sort_keys=False), encoding="utf-8")

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()
    assert cfg.domains.debug.disable_positions_stale_gate is True
