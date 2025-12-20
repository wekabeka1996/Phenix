"""TASK23B — timeframe_sec SSOT precedence contract.

Contract (fail-closed):
1) aurora_instruments.<SYM>.timeframe_sec (if set) wins
2) strategy profile mean_reversion.timeframe_sec
3) If both absent while mean_reversion is assigned -> ConfigContractError
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(dst_config_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    shutil.copytree(src, dst_config_dir)


def _yaml_load(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    assert isinstance(payload, dict)
    return payload


def _yaml_dump(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _assign_mr_to_btc(config_dir: Path) -> None:
    strategies_path = config_dir / "strategies.yaml"
    payload = _yaml_load(strategies_path)
    payload["assignments"] = {"BTCUSDT": ["mean_reversion"]}
    payload["arbitration"] = {
        "mode": "priority",
        "priority": {"mean_reversion": 1},
        "logging": {"rejected_why_prefix": "ARBITRATION_REJECT", "log_level": "INFO"},
    }
    payload.setdefault("version", "1.0.0")
    _yaml_dump(strategies_path, payload)


class TestTimeframeSecSSOTPrecedence:
    def test_instrument_override_wins_over_profile(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)
        _assign_mr_to_btc(config_dir)

        # Profile default: 60
        mr_path = config_dir / "strategies" / "mean_reversion.yaml"
        mr_payload = _yaml_load(mr_path)
        mr_payload.setdefault("mean_reversion", {})
        mr_payload["mean_reversion"]["timeframe_sec"] = 60
        _yaml_dump(mr_path, mr_payload)

        # Instrument override: 180
        inst_path = config_dir / "aurora_instruments.yaml"
        inst_payload = _yaml_load(inst_path)
        inst_payload.setdefault("BTCUSDT", {})
        inst_payload["BTCUSDT"]["timeframe_sec"] = 180
        _yaml_dump(inst_path, inst_payload)

        config = ConfigLoader(config_dir=config_dir).load_config()
        assert config.mean_reversion is not None
        assert config.mean_reversion.timeframe_sec == 180

    def test_profile_used_when_no_instrument_override(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)
        _assign_mr_to_btc(config_dir)

        # Ensure no instrument override
        inst_path = config_dir / "aurora_instruments.yaml"
        inst_payload = _yaml_load(inst_path)
        inst_payload.setdefault("BTCUSDT", {})
        inst_payload["BTCUSDT"]["timeframe_sec"] = None
        _yaml_dump(inst_path, inst_payload)

        # Profile provides timeframe
        mr_path = config_dir / "strategies" / "mean_reversion.yaml"
        mr_payload = _yaml_load(mr_path)
        mr_payload.setdefault("mean_reversion", {})
        mr_payload["mean_reversion"]["timeframe_sec"] = 60
        _yaml_dump(mr_path, mr_payload)

        config = ConfigLoader(config_dir=config_dir).load_config()
        assert config.mean_reversion is not None
        assert config.mean_reversion.timeframe_sec == 60

    def test_missing_both_fails_closed(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)
        _assign_mr_to_btc(config_dir)

        # Ensure no instrument override
        inst_path = config_dir / "aurora_instruments.yaml"
        inst_payload = _yaml_load(inst_path)
        inst_payload.setdefault("BTCUSDT", {})
        inst_payload["BTCUSDT"]["timeframe_sec"] = None
        _yaml_dump(inst_path, inst_payload)

        # Remove profile timeframe_sec entirely
        mr_path = config_dir / "strategies" / "mean_reversion.yaml"
        mr_payload = _yaml_load(mr_path)
        mr_payload.setdefault("mean_reversion", {})
        mr_payload["mean_reversion"].pop("timeframe_sec", None)
        _yaml_dump(mr_path, mr_payload)

        with pytest.raises(ConfigContractError, match=r"Missing timeframe_sec"):
            ConfigLoader(config_dir=config_dir).load_config()
