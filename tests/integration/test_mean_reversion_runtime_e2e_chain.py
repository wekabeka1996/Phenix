from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.config_models import (
    MRAssetConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRRiskConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
)
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.strategies.plugins.mean_reversion import MeanReversionPlugin
from apps.reference.domains.strategies.registry import StrategyPluginRegistry, StrategyRuntime


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list[object]] = {}
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event_name: str, payload: dict | None = None, why: str | None = None, data_ref: object = None) -> None:
        pld = payload or {}
        self.emitted.append((event_name, pld))
        for handler in list(self.listeners.get(event_name, [])):
            handler(SimpleNamespace(pld=pld))


def _dm_cfg():
    qos = SimpleNamespace(
        exposure_block_cooldown_sec=0,
        max_intents_per_minute_per_symbol=1000,
        mode="monitor",
        symbol_cooldown_sec=0,
        enforce=False,
    )
    position_sizing = SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000)
    arming = SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1)
    features = SimpleNamespace(ttl_sec=60)
    bar_gating = SimpleNamespace(enable=False, bar_ms=60_000)
    behavior_fsm = SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5)
    signals = SimpleNamespace(normalize=True)
    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        signals=signals,
    )


def test_mean_reversion_e2e_tick_to_intent_chain() -> None:
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

    strategies_registry = SimpleNamespace(
        assignments={symbol: ["mean_reversion"]},
        arbitration=SimpleNamespace(
            mode="priority",
            priority={"mean_reversion": 1},
            logging=SimpleNamespace(rejected_why_prefix="ARBITRATION_REJECT", log_level="INFO"),
        ),
    )

    mr_cfg = MeanReversion1mStrategyConfig(
        enabled=True,
        timeframe_sec=60,
        strategy=MRStrategyParamsConfig(
            bb_window=3,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            entry_threshold=0.2,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            min_bars=3,
            min_bb_width=0.0001,
            max_bb_width=10.0,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=0,
        ),
        regime_thresholds=MRRegimeThresholdsConfig(high_vol_pct=0.003, low_vol_pct=0.001),
        assets={
            symbol: MRAssetConfig(
                enabled=True,
                strategy=None,
                risk=None,
                bb_window=None,
                min_vol_atr=None,
                sl_pct=None,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        risk=MRRiskConfig(
            position_size_usd=100.0,
            max_concurrent_positions=1,
            daily_loss_limit_usd=10_000.0,
            expected_pnl_multiplier=1.0,
            fees_pct=0.0,
            slippage_pct=0.0,
        ),
        emit_trade_intent_directly=False,
    )

    cfg = SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 1, "max_latency_ms": 100, "maker_preference": "maker"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 100},
            decision=SimpleNamespace(signal_threshold=0.0),
        ),
        domains=SimpleNamespace(
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
            risk_management=SimpleNamespace(trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0)),
        ),
        instruments={symbol: SimpleNamespace(tick_size=0.1, step_size=0.001)},
        aurora_instruments={},
        strategies_registry=strategies_registry,
        mean_reversion=mr_cfg,
    )

    bus = _Bus()

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    dm.latest_portfolio = {"positions": [], "equity": "1000", "positions_last_ts_ms": now_ms}
    dm.symbol_states[symbol]["features"] = {"symbol": symbol, "ts": now_ms, "features": {"price": 100}}
    dm.symbol_states[symbol]["risk"] = {
        "symbol": symbol,
        "ts": now_ms,
        "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0},
    }

    plugins = StrategyPluginRegistry()
    plugins.register(MeanReversionPlugin())
    StrategyRuntime(fsm=bus, config=cfg, registry=plugins).start()  # type: ignore[arg-type]

    with patch.object(dm, "_warmup_gate_before_trade_intent", return_value=False):
        bus.emit(
            "EVT:REGIME_DETECTED",
            {"symbol": symbol, "regime": "MEAN_REVERSION", "warmup": {"full_ready": True}},
        )

        base = (now_ms // 60_000) * 60_000
        ticks = [
            (base + 0, Decimal("100")),
            (base + 60_000, Decimal("100")),
            (base + 120_000, Decimal("50")),
            (base + 180_000, Decimal("50")),  # closes 3rd bar (price=50) and triggers eval
        ]
        for ts_ms, price in ticks:
            bus.emit(
                "EVT:MARKET_TICK_RECEIVED",
                {"symbol": symbol, "price": str(price), "buy_volume": "1", "sell_volume": "0", "ts": ts_ms},
            )

    assert any(evt == "EVT:STRATEGY_SIGNAL_PRODUCED" for evt, _ in bus.emitted)
    intents = [pld for (evt, pld) in bus.emitted if evt == "EVT:TRADE_INTENT_PROPOSED"]
    assert len(intents) == 1
    assert intents[0]["strategy"] == "mean_reversion"
    assert intents[0]["order"]["qty"] not in ("0", "0.0", "")
    assert intents[0]["entry_price"] not in (None, "", "0")
