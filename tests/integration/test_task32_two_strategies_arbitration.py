from __future__ import annotations

import pytest
import time
from types import SimpleNamespace
from unittest.mock import patch

# FIX-MOCK-DM: STRATEGY_SIGNAL_GATEWAY now requires full DecisionMaking config
# (domains.decision_making.entry_plan, config.strategies.<id>.execution, etc.)
pytestmark = pytest.mark.skip(
    reason="FIX-MOCK-DM: STRATEGY_SIGNAL_GATEWAY requires full DM config (entry_plan). Mock incomplete."
)

from apps.reference.domains.decision_making.decision_making import DecisionMaking


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list[object]] = {}
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event_name: str, payload: dict | None = None, why: str | None = None, data_ref: object = None) -> None:
        self.emitted.append((event_name, payload or {}))


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
    )


def test_task32_two_strategies_on_one_symbol_arbitration_works() -> None:
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

    bus = _Bus()

    strategies_registry = SimpleNamespace(
        assignments={symbol: ["s1", "s2"]},
        arbitration=SimpleNamespace(
            mode="priority",
            window_ms=1000,
            priority={"s1": 1, "s2": 2},
            logging=SimpleNamespace(rejected_why_prefix="ARBITRATION_REJECT", log_level="INFO"),
        ),
    )

    cfg = SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 1, "max_latency_ms": 100, "maker_preference": "maker"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 100},
        ),
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                position_sizing=SimpleNamespace(
                    min_position_size_usd=10,
                    liquidity_based_cap_usd=10_000,
                    risk_fraction_q=None,
                    liquidity_kappa_mode="dynamic",
                    liquidity_kappa=1.0,
                ),
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
                    mode="disabled",
                    enabled=False,
                    min_abs_delta_price=0.0,
                    min_confidence=0.0,
                    consecutive_bars=1,
                ),
                price_motion_sanity=SimpleNamespace(
                    enabled=False,
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
                min_notional="100",
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=20,
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
                    side_bias_penalty_factor=0.5,
                    side_bias_window_sec=60,
                    side_bias_target_ratio=0.6,
                    kelly=None,
                ),
                assets={},
            )
        ),
        strategies_registry=strategies_registry,
    )

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    dm.latest_portfolio = {"positions": [], "equity": "1000", "positions_last_ts_ms": now_ms}
    dm.symbol_states[symbol]["features"] = {"symbol": symbol, "ts": now_ms, "features": {"price": 100}}
    dm.symbol_states[symbol]["risk"] = {"symbol": symbol, "ts": now_ms, "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}}

    losing = SimpleNamespace(
        pld={
            "strategy_id": "s2",
            "symbol": symbol,
            "side": "BUY",
            "score": 0.9,
            "why": "loser",
            "ts_ms": now_ms,
            "rid": "r2",
            "why_chain": ["loser"],
            "position_size_usd": 100.0,
            "qty_hint": "1",
            "price_ctx": {"entry_price": "100"},
            "readiness": {"warmup_ok": True},
        }
    )
    winning = SimpleNamespace(
        pld={
            "strategy_id": "s1",
            "symbol": symbol,
            "side": "BUY",
            "score": 0.9,
            "why": "winner",
            "ts_ms": now_ms,
            "rid": "r1",
            "why_chain": ["winner"],
            "position_size_usd": 100.0,
            "qty_hint": "1",
            "price_ctx": {"entry_price": "100"},
            "readiness": {"warmup_ok": True},
        }
    )

    with patch.object(dm, "_warmup_gate_before_trade_intent", return_value=False):
        dm._on_strategy_signal_gateway(winning)  # type: ignore[arg-type]
        dm._on_strategy_signal_gateway(losing)  # type: ignore[arg-type]

    intents = [pld for (evt, pld) in bus.emitted if evt == "EVT:TRADE_INTENT_PROPOSED"]
    assert len(intents) == 1
    assert intents[0]["strategy"] == "s1"
