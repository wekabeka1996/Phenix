from __future__ import annotations

from types import SimpleNamespace

from apps.reference.config_models import (
    MRAssetConfig,
    MRMomentumSeparationVetoConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRSqueezeExpansionVetoConfig,
    MRStrategyOverrideConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
    StrategyExecutionConfig,
    LeverageConfig,
    LiquidityGateConfig,
)
from apps.reference.domains.strategies.runtimes.mean_reversion.handler import MeanReversionHandler


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


def test_mr_handler_wires_asset_allowed_regimes_and_overrides() -> None:
    symbol = "BTCUSDT"

    mr_cfg = MeanReversion1mStrategyConfig(
        enabled=True,
        mode="shadow",
        timeframe_sec=180,
        strategy=MRStrategyParamsConfig(
            bb_window=20,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            score_multiplier=1.0,
            entry_threshold=0.05,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            min_bars=25,
            min_bb_width=0.001,
            max_bb_width=0.05,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=60,
            confidence_base=0.5,
            confidence_bb_slope=5.0,
            confidence_rsi_bonus=0.2,
        ),
        regime_thresholds=MRRegimeThresholdsConfig(
            high_vol_pct=0.003, low_vol_pct=0.001),
        assets={
            symbol: MRAssetConfig(
                enabled=True,
                leverage=LeverageConfig(
                    target=10, mode="ISOLATED", max_notional_value=None),
                position_mode="STRICT",
                liquidity_gate=None,
                allowed_regimes=["FLAT_LOW"],
                strategy=MRStrategyOverrideConfig(
                    microstructure_veto=None,
                    directional_bias=None,
                    entry_threshold=0.123,
                    tp_to_mid=False,
                    cooldown_sec=321,
                    bb_window=55,
                    bb_num_std=2.7,
                    min_bb_width=0.009,
                    flat_low_short_min_bb_width=0.015,
                    squeeze_expansion_veto=MRSqueezeExpansionVetoConfig(
                        enabled=True,
                        squeeze_width_max=0.010,
                        post_squeeze_width_max=0.020,
                        expansion_ratio_min=2.0,
                        regimes=["FLAT_LOW"],
                        sides=["LONG", "SHORT"],
                    ),
                    momentum_separation_veto=MRMomentumSeparationVetoConfig(
                        enabled=True,
                        lookback_bars=4,
                        min_drift_pct=0.02,
                        min_current_bb_width=0.02,
                        regimes=["FLAT_LOW"],
                        sides=["LONG", "SHORT"],
                    ),
                    sl_atr_mult=None,
                    sl_buffer_pct=None,
                    tp_buffer_pct=None,
                    allowed_regimes=["FLAT_HIGH"],
                    confidence_base=None,
                    confidence_bb_slope=None,
                    confidence_rsi_bonus=None,
                ),

            )
        },
        regime_sizing={
            "FLAT_LOW": MRRegimeSizingConfig(sizing_mult=0.8, stop_mult=0.6, target_mult=0.8),
            "FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0),
        },
        allowed_regimes=["FLAT_NORMAL"],
        liquidity_gate=LiquidityGateConfig(
            enabled=False, kappa_min=0.0, kappa_max=1.0, failsafe_qty_check=False),
        execution=StrategyExecutionConfig(
            entry_order_type="MARKET",
            entry_tif=None,
            exit_order_type=None,
            exit_tif=None,
            exit_limit_ttl_ms=None,
            gtx_retry_max=0,
            gtx_retry_offset_bps=2.0,
        ),
        safety_gates={
            "enabled": False,
            "system_stress_policy": "off",
            "stress_attenuation_factor": 0.5,
        },
        objective=None,
        microstructure_veto=None,
        directional_bias=None,
    )

    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(
            assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=mr_cfg),
    )

    handler = MeanReversionHandler(
        fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    strat = handler._strategies[symbol]
    s_cfg = strat.config

    # Ensure per-asset strategy overrides are applied
    assert s_cfg.bb_window == 55
    assert s_cfg.bb_num_std == 2.7
    assert str(s_cfg.min_bb_width) == "0.009"
    assert str(s_cfg.flat_low_short_min_bb_width) == "0.015"
    assert s_cfg.squeeze_expansion_veto is not None
    assert str(s_cfg.squeeze_expansion_veto.squeeze_width_max) == "0.01"
    assert str(s_cfg.squeeze_expansion_veto.post_squeeze_width_max) == "0.02"
    assert str(s_cfg.squeeze_expansion_veto.expansion_ratio_min) == "2.0"
    assert s_cfg.squeeze_expansion_veto.regimes == ["FLAT_LOW"]
    assert s_cfg.squeeze_expansion_veto.sides == ["LONG", "SHORT"]
    assert s_cfg.momentum_separation_veto is not None
    assert s_cfg.momentum_separation_veto.lookback_bars == 4
    assert str(s_cfg.momentum_separation_veto.min_drift_pct) == "0.02"
    assert str(s_cfg.momentum_separation_veto.min_current_bb_width) == "0.02"
    assert s_cfg.momentum_separation_veto.regimes == ["FLAT_LOW"]
    assert s_cfg.momentum_separation_veto.sides == ["LONG", "SHORT"]
    assert str(s_cfg.entry_threshold) == "0.123"
    assert s_cfg.tp_to_mid is False
    assert s_cfg.cooldown_sec == 321

    # Ensure allowed_regimes precedence ends up at the most specific override
    assert s_cfg.allowed_regimes == ["FLAT_HIGH"]

    # Ensure regime thresholds are passed into strategy (no hidden default)
    assert str(strat._flat_regime_thresholds.high_vol_pct) == "0.003"
    assert str(strat._flat_regime_thresholds.low_vol_pct) == "0.001"

    # Ensure regime sizing dict is passed through
    assert set(strat._regime_sizing.keys()) == {"FLAT_LOW", "FLAT_NORMAL"}


def test_mr_handler_uses_asset_allowed_regimes_when_no_strategy_override() -> None:
    symbol = "BTCUSDT"

    mr_cfg = MeanReversion1mStrategyConfig(
        enabled=True,
        mode="shadow",
        timeframe_sec=180,
        strategy=MRStrategyParamsConfig(
            bb_window=20,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            score_multiplier=1.0,
            entry_threshold=0.05,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            min_bars=25,
            min_bb_width=0.001,
            max_bb_width=0.05,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=60,
            confidence_base=0.5,
            confidence_bb_slope=5.0,
            confidence_rsi_bonus=0.2,
        ),
        regime_thresholds=MRRegimeThresholdsConfig(
            high_vol_pct=0.003, low_vol_pct=0.001),
        assets={
            symbol: MRAssetConfig(
                enabled=True,
                leverage=LeverageConfig(
                    target=10, mode="ISOLATED", max_notional_value=None),
                position_mode="STRICT",
                liquidity_gate=None,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
                strategy=None,

            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(
            sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_HIGH"],
        liquidity_gate=LiquidityGateConfig(
            enabled=False, kappa_min=0.0, kappa_max=1.0, failsafe_qty_check=False),
        execution=StrategyExecutionConfig(
            entry_order_type="MARKET",
            entry_tif=None,
            exit_order_type=None,
            exit_tif=None,
            exit_limit_ttl_ms=None,
            gtx_retry_max=0,
            gtx_retry_offset_bps=2.0,
        ),
        safety_gates={
            "enabled": False,
            "system_stress_policy": "off",
            "stress_attenuation_factor": 0.5,
        },
        objective=None,
        microstructure_veto=None,
        directional_bias=None,
    )

    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(
            assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=mr_cfg),
    )

    handler = MeanReversionHandler(
        fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    strat = handler._strategies[symbol]
    assert strat.config.allowed_regimes == ["FLAT_LOW", "FLAT_NORMAL"]
