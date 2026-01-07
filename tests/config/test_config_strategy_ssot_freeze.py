"""
CFG-STRATEGY-SSOT-FREEZE-03 — Strategy SSOT freeze contracts (no legacy runtime paths).

Enforces:
- Fail-closed on missing/invalid assigned strategy configs
- Strict validation (extra='forbid') for strategy profiles
- No strategy-policy keys in trading.yaml/domains.yaml
- Provenance attributes strategy keys to strategies/*.yaml with stage=strategy
- Runtime reader compatibility for Aurora + Mean Reversion via config.strategies.*
- Legacy runtime paths are absent (no shim)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

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


class TestStrategySSOTFreezeFailClosed:
    def test_missing_mean_reversion_profile_fails_closed(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)

        mr_profile = config_dir / "strategies" / "mean_reversion.yaml"
        assert mr_profile.exists()
        mr_profile.unlink()

        with pytest.raises(ValueError):
            ConfigLoader(config_dir=config_dir).load_config()

    def test_missing_aurora_profile_fails_closed(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)

        aurora_profile = config_dir / "strategies" / "aurora.yaml"
        assert aurora_profile.exists()
        aurora_profile.unlink()

        with pytest.raises(ValueError):
            ConfigLoader(config_dir=config_dir).load_config()


class TestStrategySSOTFreezeStrictValidation:
    def test_unknown_key_in_mean_reversion_profile_fails(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)

        mr_path = config_dir / "strategies" / "mean_reversion.yaml"
        payload = _yaml_load(mr_path)
        payload.setdefault("mean_reversion", {})
        payload["mean_reversion"]["unknown_key"] = 123
        _yaml_dump(mr_path, payload)

        with pytest.raises(ValidationError):
            ConfigLoader(config_dir=config_dir).load_config()

    def test_mr_asset_top_level_duplicate_params_are_invalid(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)

        mr_path = config_dir / "strategies" / "mean_reversion.yaml"
        payload = _yaml_load(mr_path)
        payload.setdefault("mean_reversion", {})
        assets = payload["mean_reversion"].setdefault("assets", {})
        btc = assets.setdefault("BTCUSDT", {})
        btc["bb_window"] = 20  # INVALID: must live under assets.BTCUSDT.strategy.*
        _yaml_dump(mr_path, payload)

        with pytest.raises(ValidationError):
            ConfigLoader(config_dir=config_dir).load_config()

    def test_unknown_key_in_aurora_profile_fails(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config" / "aurora"
        _copy_canonical_config_dir(config_dir)

        aurora_path = config_dir / "strategies" / "aurora.yaml"
        payload = _yaml_load(aurora_path)
        payload.setdefault("aurora", {})
        payload["aurora"]["unknown_key"] = "nope"
        _yaml_dump(aurora_path, payload)

        with pytest.raises(ValidationError):
            ConfigLoader(config_dir=config_dir).load_config()


class TestStrategySSOTFreezeNoPolicyInTradingDomains:
    def test_no_strategy_policy_keys_in_trading_yaml_or_domains_yaml(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        trading_path = repo_root / "config" / "aurora" / "trading.yaml"
        domains_path = repo_root / "config" / "aurora" / "domains.yaml"

        trading = _yaml_load(trading_path)
        domains = _yaml_load(domains_path)

        assert "mean_reversion" not in trading, "mean_reversion must not exist in trading.yaml (SSOT: strategies/mean_reversion.yaml)"
        assert "trading" in trading and isinstance(trading["trading"], dict)
        assert "decision" not in trading["trading"], "trading.decision must not exist in trading.yaml (SSOT: strategies/aurora.yaml)"

        # Domains must not carry strategy policy blocks.
        assert "aurora" not in domains
        assert "mean_reversion" not in domains


class TestStrategySSOTFreezeProvenance:
    def test_provenance_map_points_to_strategy_files(self) -> None:
        loader = ConfigLoader(config_dir=Path("config/aurora"))
        cfg = loader.load_config()
        assert cfg is not None

        assert loader.provenance_map.get("strategies.mean_reversion.strategy.bb_window") == "strategies/mean_reversion.yaml"
        assert loader.provenance_map.get("strategies.aurora.decision.signal_threshold") == "strategies/aurora.yaml"
        assert loader.provenance_map.get("strategies.aurora.assets.BTCUSDT.weights.ema_bias") == "strategies/aurora.yaml"

    def test_auroractl_provenance_stage_is_strategy(self, tmp_path: Path) -> None:
        out_path = tmp_path / "prov.json"
        subprocess.check_call(
            ["python3", "tools/auroractl.py", "config-provenance", "--out", str(out_path), "--config-dir", "config/aurora"],
            cwd=Path(__file__).resolve().parents[2],
        )
        rows = json.loads(out_path.read_text(encoding="utf-8"))
        sample = {row["key"]: row for row in rows if row.get("key") in {"strategies.aurora.decision.signal_threshold", "strategies.aurora.assets.BTCUSDT.weights.ema_bias"}}
        assert sample["strategies.aurora.decision.signal_threshold"]["source_file"] == "strategies/aurora.yaml"
        assert sample["strategies.aurora.decision.signal_threshold"]["stage"] == "strategy"
        assert sample["strategies.aurora.assets.BTCUSDT.weights.ema_bias"]["source_file"] == "strategies/aurora.yaml"
        assert sample["strategies.aurora.assets.BTCUSDT.weights.ema_bias"]["stage"] == "strategy"


class TestStrategySSOTFreezeReaderCompatibility:
    def test_mean_reversion_reader_paths_exist(self) -> None:
        cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
        assert cfg.strategies.mean_reversion is not None
        assert cfg.strategies.mean_reversion.strategy.bb_window == 20
        assert "BTCUSDT" in cfg.strategies.mean_reversion.assets

    def test_aurora_reader_paths_exist(self) -> None:
        cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
        assert cfg.strategies.aurora is not None
        assert cfg.strategies.aurora.decision.signal_threshold == 0.12
        btc = cfg.strategies.aurora.assets["BTCUSDT"]
        assert btc.weights is not None
        assert btc.weights["ema_bias"] == 0.20

    def test_legacy_runtime_paths_are_absent(self) -> None:
        cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
        assert not hasattr(cfg, "aurora_instruments")
        assert not hasattr(cfg, "mean_reversion")
        assert not hasattr(cfg.trading, "decision")
