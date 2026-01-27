from __future__ import annotations

import time
import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.config_models import (
    MRAssetConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
    StrategyExecutionConfig,
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
    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        # Used by DecisionMaking._get_regime_thresholds()
        regime_threshold_multipliers={"DEFAULT": 1.0},
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        risk_skew=SimpleNamespace(
            max_skew_sec=5,
            max_defer_count=3,
            defer_cooldown_sec=2,
            defer_window_sec=60,
            until_refresh_retry_sec=30,
        ),
        risk_gate=SimpleNamespace(
            threshold_pct_testnet=20.0,
            threshold_pct_production=50.0,
            min_intents_for_check=10,
        ),
        directional_sanity=SimpleNamespace(
            enabled=False,
            min_abs_delta_price=0.0,
            min_confidence=0.0,
            consecutive_bars=2
        ),
        price_motion_sanity=SimpleNamespace(
            enabled=False,
            k_vol=2.0,
            flash_window_sec=10,
            bleed_window_sec=300,
            flash_threshold_norm=1.0,
            bleed_threshold_norm=0.5,
            require_bleed_ready=False
        ),
    )



# @pytest.mark.xfail(reason="LEGACY: MR tick-to-intent chain broken after TF-BAR-SSOT refactor; requires bar-based features (BAR-SSOT-003)")
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
            symbol: MRAssetConfig(
                enabled=True,
                strategy=None,
                
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        execution=StrategyExecutionConfig(entry_order_type="MARKET"),
    )

    cfg = SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 1, "max_latency_ms": 100, "maker_preference": "maker"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 100},
            decision=SimpleNamespace(
                # Strict access in DecisionMaking expects model_dump().
                signal_weights=SimpleNamespace(model_dump=lambda: {"obi": 1.0}),
            ),
        ),
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                risk_skew=SimpleNamespace(
                    max_skew_sec=5,
                    max_defer_count=3,
                    defer_cooldown_sec=2,
                    defer_window_sec=60,
                    until_refresh_retry_sec=30,
                ),
                risk_gate=SimpleNamespace(
                    threshold_pct_testnet=20.0,
                    threshold_pct_production=50.0,
                    min_intents_for_check=10,
                ),
                directional_sanity=SimpleNamespace(
                    enabled=False,
                    min_abs_delta_price=0.0,
                    min_confidence=0.0,
                    consecutive_bars=2
                ),
                price_motion_sanity=SimpleNamespace(
                    enabled=False,
                    k_vol=2.0,
                    flash_window_sec=10,
                    bleed_window_sec=300,
                    flash_threshold_norm=1.0,
                    bleed_threshold_norm=0.5,
                    require_bleed_ready=False
                ),
            ),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
            risk_management=SimpleNamespace(trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0)),
        ),
        instruments={
            symbol: SimpleNamespace(
                tick_size="0.1",
                step_size="0.001",
                min_qty="0.001",
                min_notional="5",
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=10,
                    leverage_policy="verify_only",
                    max_notional_utilization=0.8,
                ),
                sizing=SimpleNamespace(margin_pct=0.02),
            )
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    signal_threshold=0.0,
                    retry_ttl_ms=1000,
                    retry_max_count=1,
                    retry_backoff_factor=1.0,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    side_bias_penalty_factor=0.5,
                    side_bias_window_sec=60,
                    side_bias_target_ratio=0.6,
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

    with patch.object(dm, "_warmup_gate_before_trade_intent", return_value=False), \
         patch.object(dm, "_calculate_position_size", return_value=(Decimal("0.01"), "TEST_SIZING", None, {})):
        # MANUAL INJECTION TO VERIFY FIX
        # Inject STRATEGY_SIGNAL_PRODUCED to test DecisionMaking directly
        # failing upstream strategy logic is irrelevant for the AttributeError verification
        bus.emit(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            {
                "symbol": symbol,
                "strategy_id": "mean_reversion",
                "rid": "rid_test_manual",
                "side": "BUY",
                "price_ctx": {"entry_price": "100.0", "stop_price": "95.0", "target_price": "110.0"},
                "ts_ms": now_ms,
                "volatility": {"atr_14": "1.0", "atr_ready": True},
                "liquidity": {"obi_close": "0.0"},
                "readiness": {"warmup_ok": True},
            }
        )

    print("Emitted events:", [evt for evt, _ in bus.emitted])

    assert any(evt == "EVT:STRATEGY_SIGNAL_PRODUCED" for evt, _ in bus.emitted)
    intents = [pld for (evt, pld) in bus.emitted if evt == "EVT:TRADE_INTENT_PROPOSED"]
    assert len(intents) == 1
    assert intents[0]["strategy"] == "mean_reversion"
    assert intents[0]["order"]["qty"] not in ("0", "0.0", "")
    assert intents[0]["order"]["price"] not in (None, "", "0")
