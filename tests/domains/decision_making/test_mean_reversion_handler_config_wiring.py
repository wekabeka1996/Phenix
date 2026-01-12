from __future__ import annotations

from types import SimpleNamespace

from apps.reference.config_models import (
    MRAssetConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRRiskConfig,
    MRStrategyOverrideConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
    StrategyExecutionConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler


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
        timeframe_sec=180,
        strategy=MRStrategyParamsConfig(
            bb_window=20,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            entry_threshold=0.05,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            min_bars=25,
            min_bb_width=0.001,
            max_bb_width=0.05,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=60,
        ),
        regime_thresholds=MRRegimeThresholdsConfig(high_vol_pct=0.003, low_vol_pct=0.001),
        assets={
            symbol: MRAssetConfig(
                enabled=True,
                position_mode="STRICT",
                allowed_regimes=["FLAT_LOW"],
                strategy=MRStrategyOverrideConfig(
                    entry_threshold=0.123,
                    tp_to_mid=False,
                    cooldown_sec=321,
                    bb_window=55,
                    bb_num_std=2.7,
                    min_bb_width=0.009,
                    sl_atr_mult=None,
                    allowed_regimes=["FLAT_HIGH"],
                ),
                risk=None,
            )
        },
        regime_sizing={
            "FLAT_LOW": MRRegimeSizingConfig(sizing_mult=0.8, stop_mult=0.6, target_mult=0.8),
            "FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0),
        },
        allowed_regimes=["FLAT_NORMAL"],
        risk=MRRiskConfig(
            position_size_usd=100.0,
            max_concurrent_positions=1,
            daily_loss_limit_usd=10_000.0,
            expected_pnl_multiplier=1.0,
            fees_pct=0.0,
            slippage_pct=0.0,
        ),
        emit_trade_intent_directly=False,
        execution=StrategyExecutionConfig(
            entry_order_type="MARKET",
            entry_tif=None,
        ),
    )

    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=mr_cfg),
    )

    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    strat = handler._strategies[symbol]
    s_cfg = strat.config

    # Ensure per-asset strategy overrides are applied
    assert s_cfg.bb_window == 55
    assert s_cfg.bb_num_std == 2.7
    assert str(s_cfg.min_bb_width) == "0.009"
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
        timeframe_sec=180,
        strategy=MRStrategyParamsConfig(
            bb_window=20,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            entry_threshold=0.05,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            min_bars=25,
            min_bb_width=0.001,
            max_bb_width=0.05,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=60,
        ),
        regime_thresholds=MRRegimeThresholdsConfig(high_vol_pct=0.003, low_vol_pct=0.001),
        assets={
            symbol: MRAssetConfig(
                enabled=True,
                position_mode="STRICT",
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
                strategy=None,
                risk=None,
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_HIGH"],
        risk=MRRiskConfig(
            position_size_usd=100.0,
            max_concurrent_positions=1,
            daily_loss_limit_usd=10_000.0,
            expected_pnl_multiplier=1.0,
            fees_pct=0.0,
            slippage_pct=0.0,
        ),
        emit_trade_intent_directly=False,
        execution=StrategyExecutionConfig(
            entry_order_type="MARKET",
            entry_tif=None,
        ),
    )

    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=mr_cfg),
    )

    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    strat = handler._strategies[symbol]
    assert strat.config.allowed_regimes == ["FLAT_LOW", "FLAT_NORMAL"]
