"""MR YAML contract: every key is loaded (no silent defaults).

This test is intentionally strict: it pins the canonical
config/aurora/strategies/mean_reversion.yaml to the typed Pydantic model.

Goal: if ANY YAML line/key changes, this test forces a conscious update.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import (
    MRMomentumSeparationVetoConfig,
    MRSqueezeExpansionVetoConfig,
    MRStrategyOverrideConfig,
)


def _copy_canonical_config_dir(dst_config_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "config" / "aurora"
    import shutil

    shutil.copytree(src, dst_config_dir)


def _assign_mean_reversion(config_dir: Path) -> None:
    strategies_path = config_dir / "strategies.yaml"
    payload = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    assert isinstance(payload, dict)
    assignments = payload.setdefault("assignments", {})
    assert isinstance(assignments, dict)
    assigned = assignments.setdefault("BTCUSDT", [])
    assert isinstance(assigned, list)
    if "mean_reversion" not in assigned:
        assigned.append("mean_reversion")
    strategies_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    mr_profile_path = config_dir / "strategies" / "mean_reversion.yaml"
    mr_payload = yaml.safe_load(mr_profile_path.read_text(encoding="utf-8"))
    assert isinstance(mr_payload, dict)
    mr_root = mr_payload.setdefault("mean_reversion", {})
    assert isinstance(mr_root, dict)
    assets = mr_root.setdefault("assets", {})
    assert isinstance(assets, dict)
    btc = assets.setdefault("BTCUSDT", {})
    assert isinstance(btc, dict)
    btc["enabled"] = True
    mr_profile_path.write_text(yaml.safe_dump(mr_payload, sort_keys=False), encoding="utf-8")


def test_mean_reversion_profile_yaml_fully_loaded(tmp_path: Path) -> None:
    # Arrange: load canonical config via ConfigLoader (SSOT)
    config_dir = tmp_path / "config" / "aurora"
    _copy_canonical_config_dir(config_dir)
    _assign_mean_reversion(config_dir)

    loader = ConfigLoader(config_dir=config_dir)
    cfg = loader.load_config()
    mr = cfg.strategies.mean_reversion
    assert mr is not None

    # Arrange: parse the canonical YAML as ground-truth text
    mr_yaml_path = config_dir / "strategies" / "mean_reversion.yaml"
    raw = yaml.safe_load(mr_yaml_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    raw_mr = raw["mean_reversion"]

    # Top-level fields
    assert mr.enabled == raw_mr["enabled"]
    assert mr.timeframe_sec == raw_mr["timeframe_sec"]
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
            assert a.strategy.flat_low_short_min_bb_width == raw_asset_strategy.get("flat_low_short_min_bb_width")
            raw_squeeze_veto = raw_asset_strategy.get("squeeze_expansion_veto")
            if raw_squeeze_veto is None:
                assert a.strategy.squeeze_expansion_veto is None
            else:
                assert a.strategy.squeeze_expansion_veto is not None
                assert a.strategy.squeeze_expansion_veto.enabled == raw_squeeze_veto["enabled"]
                assert a.strategy.squeeze_expansion_veto.squeeze_width_max == raw_squeeze_veto["squeeze_width_max"]
                assert a.strategy.squeeze_expansion_veto.post_squeeze_width_max == raw_squeeze_veto["post_squeeze_width_max"]
                assert a.strategy.squeeze_expansion_veto.expansion_ratio_min == raw_squeeze_veto["expansion_ratio_min"]
                assert a.strategy.squeeze_expansion_veto.regimes == raw_squeeze_veto["regimes"]
                assert a.strategy.squeeze_expansion_veto.sides == raw_squeeze_veto["sides"]
            raw_momentum_veto = raw_asset_strategy.get("momentum_separation_veto")
            if raw_momentum_veto is None:
                assert a.strategy.momentum_separation_veto is None
            else:
                assert a.strategy.momentum_separation_veto is not None
                assert a.strategy.momentum_separation_veto.enabled == raw_momentum_veto["enabled"]
                assert a.strategy.momentum_separation_veto.lookback_bars == raw_momentum_veto["lookback_bars"]
                assert a.strategy.momentum_separation_veto.min_drift_pct == raw_momentum_veto["min_drift_pct"]
                assert a.strategy.momentum_separation_veto.min_current_bb_width == raw_momentum_veto["min_current_bb_width"]
                assert a.strategy.momentum_separation_veto.regimes == raw_momentum_veto["regimes"]
                assert a.strategy.momentum_separation_veto.sides == raw_momentum_veto["sides"]
            assert a.strategy.entry_threshold == raw_asset_strategy.get("entry_threshold")
            assert a.strategy.tp_to_mid == raw_asset_strategy.get("tp_to_mid")
            assert a.strategy.sl_atr_mult == raw_asset_strategy.get("sl_atr_mult")
            assert a.strategy.cooldown_sec == raw_asset_strategy.get("cooldown_sec")
            assert a.strategy.allowed_regimes == raw_asset_strategy.get("allowed_regimes")

        # MRAssetRiskConfig purged (DEAD CODE): per-asset risk fields were never read in runtime.
        # MRRiskConfig purged (DEAD CODE): global risk config was never read in runtime.
        # Risk decisions are centralized in RiskManagement and PositionSizing domains.


def test_mr_override_rejects_unknown_flat_low_short_hardening_key() -> None:
    with pytest.raises(ValidationError):
        MRStrategyOverrideConfig(flat_low_short_min_bb_wdith=0.015)


def test_mr_squeeze_expansion_veto_rejects_inverted_width_contract() -> None:
    with pytest.raises(ValidationError):
        MRSqueezeExpansionVetoConfig(
            enabled=True,
            squeeze_width_max=0.02,
            post_squeeze_width_max=0.01,
            expansion_ratio_min=2.0,
            regimes=["FLAT_LOW"],
            sides=["SHORT"],
        )


def test_mr_momentum_separation_veto_rejects_zero_lookback() -> None:
    with pytest.raises(ValidationError):
        MRMomentumSeparationVetoConfig(
            enabled=True,
            lookback_bars=0,
            min_drift_pct=0.02,
            min_current_bb_width=0.02,
            regimes=["FLAT_LOW"],
            sides=["SHORT"],
        )
