from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.decision_making.decision_making import DecisionMaking


class _Bus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict | None]] = []

    def listen(self, _event: str, _handler: object) -> None:
        pass

    def emit(self, event_name: str, payload: dict | None = None, why: str | None = None, data_ref: object = None, **_kwargs: object) -> None:
        self.emitted.append((event_name, payload))


def _dm_cfg():
    qos = SimpleNamespace(
        exposure_block_cooldown_sec=0,
        max_intents_per_minute_per_symbol=1000,
        mode="shadow",
        symbol_cooldown_sec=0,
        enforce=False,
    )
    position_sizing = SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000)
    arming = SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1)
    features = SimpleNamespace(ttl_sec=60)
    bar_gating = SimpleNamespace(enable=False, bar_ms=60_000)
    behavior_fsm = SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5)
    directional_sanity = SimpleNamespace(enabled=False, min_abs_delta_price=0.0, min_confidence=0.0, consecutive_bars=2)
    price_motion_sanity = SimpleNamespace(
        enabled=False,
        k_vol=2.0,
        flash_window_sec=10,
        bleed_window_sec=300,
        flash_threshold_norm=1.0,
        bleed_threshold_norm=0.7,
        require_bleed_ready=True,
    )

    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        directional_sanity=directional_sanity,
        price_motion_sanity=price_motion_sanity,
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
        flip=SimpleNamespace(enabled=True),
        fail_closed_on_degraded_context=False,
        degraded_context_critical_keys=[],
        degraded_context_critical_keys_by_strategy={},
    )


def _mk_cfg(*, symbol: str):
    domains_decision_making = SimpleNamespace(
        directional_sanity=SimpleNamespace(enabled=False, min_abs_delta_price=0.0, min_confidence=0.0, consecutive_bars=2),
        price_motion_sanity=SimpleNamespace(
            enabled=False,
            k_vol=2.0,
            flash_window_sec=10,
            bleed_window_sec=300,
            flash_threshold_norm=1.0,
            bleed_threshold_norm=0.7,
            require_bleed_ready=True,
        ),
    )
    return SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": "neutral"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200},
            mode="testnet",
        ),
        domains=SimpleNamespace(
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
            decision_making=domains_decision_making,
        ),
        instruments={
            symbol: SimpleNamespace(
                tick_size="0.1",
                step_size="0.001",
                min_qty="0.001",
                min_notional="10",
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=20,
                    leverage_policy="verify_only",
                    max_notional_utilization=0.8,
                ),
                sizing=SimpleNamespace(margin_pct=0.02),
                flip=SimpleNamespace(enabled=True, hysteresis_mult=1.3),
            )
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                execution=SimpleNamespace(
                    entry_order_type="MARKET",
                ),
                # DM-SAFETY-BYPASSES-P1: Required for fail-closed safety_gates check
                safety_gates=SimpleNamespace(enabled=False),
                decision=SimpleNamespace(
                    signal_threshold=0.0,
                    retry_ttl_ms=1000,
                    retry_max_count=1,
                    retry_backoff_factor=1.0,
                    side_bias_penalty_factor=0.5,
                    side_bias_window_sec=60,
                    side_bias_target_ratio=0.6,
                    side_bias_min_intents=1,
                    signals=SimpleNamespace(
                        normalize_signals_mode="off",
                        enable_new_metrics=True,
                        delta_price_cap_pct=0.02,
                    ),
                    direction_strength_scoring=SimpleNamespace(
                        directional_features=["delta_price"],
                        strength_features=[],
                        strength_alpha=0.5,
                        strength_cap=1.0,
                    ),
                    kelly=None,
                ),
                assets={symbol: SimpleNamespace(enabled=True, position_mode="STRICT")},
            )
        ),
        strategies_registry=None,
    )


def test_side_bias_window_updates_on_emitted_open_intents():
    symbol = "BTCUSDT"
    rid = "r1"
    bus = _Bus()
    cfg = _mk_cfg(symbol=symbol)

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    # Warmup prerequisites for _warmup_gate_before_trade_intent()
    now_sec = 1000.0
    now_ms = int(now_sec * 1000)
    dm.latest_portfolio = {"positions": [], "equity": "1000", "positions_last_ts_ms": now_ms}
    dm.symbol_states[symbol]["features"] = {
        "ts": now_ms,
        "price": "100",
        "delta_price": "0.0",
        # TASK24.B warmup gate requires FeatureEngineering warmup evidence.
        "warmup": {"full_ready": True, "ready": {"obi": True, "delta_price": True}},
    }
    dm.symbol_states[symbol]["risk"] = {"ok": True}
    dm._per_symbol_regimes[symbol] = {"warmup": {"full_ready": True, "ticks_seen": 999}}

    with patch("apps.reference.domains.decision_making.intent_builder.wal.append", lambda *_args, **_kwargs: None):
        with patch("time.time", return_value=now_sec):
            dm._propose_trade_intent(
                symbol=symbol,
                side="buy",
                qty=dm.min_pos_size_usd,  # any positive qty
                price=dm.min_pos_size_usd,  # any positive price
                why_chain=["test"],
                rid=rid,
                reduce_only=False,
                strategy_id="aurora",
                decision_ts_ms=now_ms,
                tf_sec=300,
            )

            dm._propose_trade_intent(
                symbol=symbol,
                side="buy",
                qty=dm.min_pos_size_usd,
                price=dm.min_pos_size_usd,
                why_chain=["test2"],
                rid="r2",
                reduce_only=False,
                strategy_id="aurora",
                decision_ts_ms=now_ms + 1,
                tf_sec=300,
            )

    assert hasattr(dm, "_side_intent_window")
    window = dm._side_intent_window[symbol]
    assert len(window["buys"]) == 2
    assert len(window["sells"]) == 0
