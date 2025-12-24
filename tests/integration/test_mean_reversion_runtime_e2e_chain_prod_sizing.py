from __future__ import annotations

import time
from decimal import Decimal, ROUND_FLOOR
from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


def _dm_cfg_prod_like():
    # Keep gates permissive for determinism, but use real sizing path.
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
    bar_gating = SimpleNamespace(enable=False, bar_ms=180_000)
    behavior_fsm = SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5)
    signals = SimpleNamespace(normalize=True)
    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        regime_threshold_multipliers={"DEFAULT": 1.0},
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        signals=signals,
    )


def _dm_cfg_prod_like_with_position_sizing(*, min_position_size_usd: int, liquidity_based_cap_usd: int):
    cfg = _dm_cfg_prod_like()
    cfg.position_sizing = SimpleNamespace(
        min_position_size_usd=min_position_size_usd,
        liquidity_based_cap_usd=liquidity_based_cap_usd,
    )
    return cfg


def _floor_to_step(qty: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return qty
    steps = (qty / step).to_integral_value(rounding=ROUND_FLOOR)
    return steps * step


@pytest.mark.parametrize(
    "case",
    [
        {
            "symbol": "BTCUSDT",
            "prices": ["100", "100", "50", "50"],
            "instrument": {
                "tick_size": "0.1",
                "step_size": "0.001",
                "min_qty": "0.001",
                "min_notional": "5",
                "margin_pct": 0.02,
                "leverage": 10,
            },
            "dm_position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10_000},
            "expect_intent": True,
        },
        {
            "symbol": "DOGEUSDT",
            "prices": ["0.13", "0.13", "0.065", "0.065"],
            "instrument": {
                "tick_size": "0.00001",
                "step_size": "1",
                "min_qty": "1",
                "min_notional": "5",
                "margin_pct": 0.02,
                "leverage": 10,
            },
            "dm_position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10_000},
            "expect_intent": True,
        },
        {
            "symbol": "XRPUSDT",
            "prices": ["2", "2", "1", "1"],
            "instrument": {
                "tick_size": "0.0001",
                "step_size": "0.1",
                "min_qty": "0.1",
                "min_notional": "5",
                "margin_pct": 0.02,
                "leverage": 10,
            },
            "dm_position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10_000},
            "expect_intent": True,
        },
        # Positive: liquidity cap should bind notional_target
        {
            "symbol": "CAPUSDT",
            "prices": ["100", "100", "50", "50"],
            "instrument": {
                "tick_size": "0.1",
                "step_size": "0.001",
                "min_qty": "0.001",
                "min_notional": "5",
                "margin_pct": 0.02,
                "leverage": 10,
            },
            "dm_position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 50},
            "expect_intent": True,
        },
        # Negative: sizing should fail exchange constraints (min_notional too high)
        {
            "symbol": "BADUSDT",
            "prices": ["100", "100", "50", "50"],
            "instrument": {
                "tick_size": "0.1",
                "step_size": "0.001",
                "min_qty": "0.001",
                "min_notional": "5000",
                "margin_pct": 0.02,
                "leverage": 10,
            },
            "dm_position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10_000},
            "expect_intent": False,
        },
        # Negative: sizing should fail exchange constraints (min_qty too high)
        {
            "symbol": "MINQTYUSDT",
            "prices": ["100", "100", "50", "50"],
            "instrument": {
                "tick_size": "0.1",
                "step_size": "0.001",
                "min_qty": "10",
                "min_notional": "5",
                "margin_pct": 0.02,
                "leverage": 10,
            },
            "dm_position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10_000},
            "expect_intent": False,
        },
    ],
)
def test_mean_reversion_e2e_chain_with_real_margin_first_sizing_multi_symbol(case: dict) -> None:
    symbol = case["symbol"]
    now_ms = int(time.time() * 1000)

    symbols = ["BTCUSDT", "DOGEUSDT", "XRPUSDT", "CAPUSDT", "BADUSDT", "MINQTYUSDT"]

    strategies_registry = SimpleNamespace(
        assignments={s: ["mean_reversion"] for s in symbols},
        arbitration=SimpleNamespace(
            mode="priority",
            priority={"mean_reversion": 1},
            logging=SimpleNamespace(rejected_why_prefix="ARBITRATION_REJECT", log_level="INFO"),
        ),
    )

    # 3m MR to match production requirement.
    mr_cfg = MeanReversion1mStrategyConfig(
        enabled=True,
        timeframe_sec=180,
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
            s: MRAssetConfig(
                enabled=True,
                strategy=None,
                risk=None,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
            for s in symbols
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
            decision=SimpleNamespace(
                signal_weights=SimpleNamespace(model_dump=lambda: {"obi": 1.0}),
            ),
        ),
        domains=SimpleNamespace(
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
            risk_management=SimpleNamespace(trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0)),
        ),
        instruments={
            s: SimpleNamespace(
                tick_size=(case["instrument"]["tick_size"] if s == symbol else "0.1"),
                step_size=(case["instrument"]["step_size"] if s == symbol else "0.001"),
                min_qty=(case["instrument"]["min_qty"] if s == symbol else "0.001"),
                min_notional=(case["instrument"]["min_notional"] if s == symbol else "5"),
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=(case["instrument"]["leverage"] if s == symbol else 10),
                    leverage_policy="verify_only",
                    max_notional_utilization=0.8,
                ),
                sizing=SimpleNamespace(margin_pct=(case["instrument"]["margin_pct"] if s == symbol else 0.02)),
            )
            for s in symbols
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    signal_threshold=0.0,
                    retry_ttl_ms=1000,
                    retry_max_count=1,
                    retry_backoff_factor=1.0,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    side_bias_penalty_factor=None,
                    side_bias_window_sec=None,
                    side_bias_target_ratio=None,
                    kelly=None,
                ),
                assets={},
            ),
            mean_reversion=mr_cfg,
        ),
        strategies_registry=strategies_registry,
    )

    bus = _Bus()

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        dm_ps = case["dm_position_sizing"]
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg_prod_like_with_position_sizing(
            min_position_size_usd=int(dm_ps["min_position_size_usd"]),
            liquidity_based_cap_usd=int(dm_ps["liquidity_based_cap_usd"]),
        )
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    # Minimal live state for DM gates
    dm.latest_portfolio = {"positions": [], "equity": "1000", "positions_last_ts_ms": now_ms}
    for s in symbols:
        dm.symbol_states[s]["features"] = {"symbol": s, "ts": now_ms, "features": {"price": 100}}
        dm.symbol_states[s]["risk"] = {
            "symbol": s,
            "ts": now_ms,
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0},
        }

    plugins = StrategyPluginRegistry()
    plugins.register(MeanReversionPlugin())
    StrategyRuntime(fsm=bus, config=cfg, registry=plugins).start()  # type: ignore[arg-type]

    with patch.object(dm, "_warmup_gate_before_trade_intent", return_value=False):
        # Use LOW_VOLATILITY (no ATR dependency)
        for s in symbols:
            bus.emit(
                "EVT:REGIME_DETECTED",
                {"symbol": s, "regime": "LOW_VOLATILITY", "warmup": {"full_ready": True}},
            )

        base = (now_ms // 180_000) * 180_000
        price_seq = [Decimal(p) for p in case["prices"]]
        tick_ts = [base + 0, base + 180_000, base + 360_000, base + 540_000]
        for ts_ms, price in zip(tick_ts, price_seq, strict=True):
            bus.emit(
                "EVT:MARKET_TICK_RECEIVED",
                {"symbol": symbol, "price": str(price), "buy_volume": "1", "sell_volume": "0", "ts": ts_ms},
            )

    assert any(evt == "EVT:STRATEGY_SIGNAL_PRODUCED" and pld.get("symbol") == symbol for evt, pld in bus.emitted)

    intents = [
        pld
        for (evt, pld) in bus.emitted
        if evt == "EVT:TRADE_INTENT_PROPOSED" and pld.get("instrument") == symbol
    ]

    if not case["expect_intent"]:
        assert len(intents) == 0
        return

    assert len(intents) == 1
    intent = intents[0]
    assert intent["strategy"] == "mean_reversion"

    # Assert qty matches real margin-first sizing formula.
    entry_price = Decimal(intent["order"]["price"])
    qty = Decimal(intent["order"]["qty"])

    equity = Decimal("1000")
    margin_pct = Decimal(str(case["instrument"]["margin_pct"]))
    leverage = Decimal(str(case["instrument"]["leverage"]))
    step = Decimal(str(case["instrument"]["step_size"]))
    min_notional = Decimal(str(case["instrument"]["min_notional"]))
    min_position_size_usd = Decimal(str(case["dm_position_sizing"]["min_position_size_usd"]))
    liq_cap_usd = Decimal(str(case["dm_position_sizing"]["liquidity_based_cap_usd"]))

    notional_target_raw = equity * margin_pct * leverage
    notional_target = notional_target_raw if notional_target_raw <= liq_cap_usd else liq_cap_usd
    expected_qty = _floor_to_step(notional_target / entry_price, step)

    assert qty == expected_qty
    assert qty > Decimal("0")
    assert (qty * entry_price) >= min_notional
    assert (qty * entry_price) >= min_position_size_usd
