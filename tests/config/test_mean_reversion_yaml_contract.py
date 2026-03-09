"""MR YAML contract: every key is loaded (no silent defaults).

This test is intentionally strict: it pins the canonical
config/aurora/strategies/mean_reversion.yaml to the typed Pydantic model.

Goal: if ANY YAML line/key changes, this test forces a conscious update.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def _copy_canonical_config_dir(dst_config_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    import shutil

    shutil.copytree(src, dst_config_dir)


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "testnet_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "testnet_secret")
    monkeypatch.setenv("BINANCE_FUTURES_API_KEY_LIVE", "live_key")
    monkeypatch.setenv("BINANCE_FUTURES_API_SECRET_LIVE", "live_secret")
    monkeypatch.setenv("BINANCE_FUTURES_BASE_URL_LIVE", "https://fapi.binance.com")


def test_mean_reversion_profile_yaml_fully_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: load canonical config via ConfigLoader (SSOT)
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _set_required_env(monkeypatch)

    loader = ConfigLoader(config_dir=config_dir)
    cfg = loader.load_config()
    mr = cfg.strategies.mean_reversion
    assert mr is not None

    # Arrange: parse the canonical YAML as ground-truth text
    repo_root = Path(__file__).resolve().parents[2]
    mr_yaml_path = repo_root / "config" / "aurora" / "strategies" / "mean_reversion.yaml"
    raw = yaml.safe_load(mr_yaml_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    raw_mr = raw["mean_reversion"]

    # Top-level fields
    assert mr.enabled == raw_mr["enabled"]
    assert mr.timeframe_sec == raw_mr["timeframe_sec"]
    assert mr.timeframe_sec == 300
    assert mr.allowed_regimes == raw_mr["allowed_regimes"]
    # Strategy fields
    raw_strategy = raw_mr["strategy"]
    assert mr.strategy.bb_window == raw_strategy["bb_window"]
    assert mr.strategy.bb_num_std == raw_strategy["bb_num_std"]
    assert mr.strategy.atr_window == raw_strategy["atr_window"]
    assert mr.strategy.rsi_window == raw_strategy["rsi_window"]
    assert mr.strategy.entry_threshold == raw_strategy["entry_threshold"]
    assert mr.strategy.rsi_oversold == raw_strategy["rsi_oversold"]
    assert mr.strategy.rsi_overbought == raw_strategy["rsi_overbought"]
    assert mr.strategy.min_bars == raw_strategy["min_bars"]
    assert mr.strategy.min_bb_width == raw_strategy["min_bb_width"]
    assert mr.strategy.max_bb_width == raw_strategy["max_bb_width"]
    assert mr.strategy.sl_atr_mult == raw_strategy["sl_atr_mult"]
    assert mr.strategy.tp_to_mid == raw_strategy["tp_to_mid"]
    assert mr.strategy.cooldown_sec == raw_strategy["cooldown_sec"]

    # Regime thresholds
    raw_thr = raw_mr["regime_thresholds"]
    assert mr.regime_thresholds.high_vol_pct == raw_thr["high_vol_pct"]
    assert mr.regime_thresholds.low_vol_pct == raw_thr["low_vol_pct"]

    # Regime sizing mapping
    raw_rs = raw_mr["regime_sizing"]
    assert set(mr.regime_sizing.keys()) == set(raw_rs.keys())
    for regime_name, rs_cfg in mr.regime_sizing.items():
        expected = raw_rs[regime_name]
        assert rs_cfg.sizing_mult == expected["sizing_mult"]
        assert rs_cfg.stop_mult == expected["stop_mult"]
        assert rs_cfg.target_mult == expected["target_mult"]

    # Risk (global) purged: MRRiskConfig was DEAD CODE - never read in runtime.
    # Risk decisions are centralized in RiskManagement and PositionSizing domains.

    # Assets
    raw_assets = raw_mr["assets"]
    assert set(mr.assets.keys()) == set(raw_assets.keys())

    for symbol, raw_asset in raw_assets.items():
        a = mr.assets[symbol]
        assert a.enabled == raw_asset["enabled"]
        assert a.position_mode == raw_asset["position_mode"]
        assert a.allowed_regimes == raw_asset["allowed_regimes"]

        raw_asset_strategy = raw_asset.get("strategy")
        if raw_asset_strategy is None:
            assert a.strategy is None
        else:
            assert a.strategy is not None
            assert a.strategy.bb_window == raw_asset_strategy.get("bb_window")
            assert a.strategy.bb_num_std == raw_asset_strategy.get("bb_num_std")
            assert a.strategy.min_bb_width == raw_asset_strategy.get("min_bb_width")
            assert a.strategy.entry_threshold == raw_asset_strategy.get("entry_threshold")
            assert a.strategy.tp_to_mid == raw_asset_strategy.get("tp_to_mid")
            assert a.strategy.sl_atr_mult == raw_asset_strategy.get("sl_atr_mult")
            assert a.strategy.cooldown_sec == raw_asset_strategy.get("cooldown_sec")
            assert a.strategy.allowed_regimes == raw_asset_strategy.get("allowed_regimes")

        # MRAssetRiskConfig purged (DEAD CODE): per-asset risk fields were never read in runtime.
        # MRRiskConfig purged (DEAD CODE): global risk config was never read in runtime.
        # Risk decisions are centralized in RiskManagement and PositionSizing domains.


def test_mean_reversion_launch_contract_rejects_non_300_tf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _set_required_env(monkeypatch)

    mr_yaml_path = config_dir / "strategies" / "mean_reversion.yaml"
    raw = yaml.safe_load(mr_yaml_path.read_text(encoding="utf-8"))
    raw["mean_reversion"]["timeframe_sec"] = 180
    mr_yaml_path.write_text(
        yaml.safe_dump(raw, sort_keys=False), encoding="utf-8"
    )

    loader = ConfigLoader(config_dir=config_dir)
    with pytest.raises(ValueError, match="timeframe_sec must equal 300"):
        loader.load_config()
