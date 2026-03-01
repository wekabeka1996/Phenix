from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.decision_making.decision_making import DecisionMaking


class _Bus:
    def __init__(self) -> None:
        self.emits: list[tuple[str, dict | None, str | None, object]] = []

    def listen(self, _event: str, _handler: object) -> None:
        return

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
    ) -> None:
        self.emits.append((event_name, payload, why, data_ref))


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
    flip = SimpleNamespace(enabled=True, hysteresis_mult=1.0)
    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        flip=flip,
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


def _mk_cfg(*, symbol: str, position_mode: str, stale_ttl_sec: int = 15):
    return SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": "neutral"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200},
            mode="testnet",
        ),
        domains=SimpleNamespace(
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=stale_ttl_sec),
            decision_making=SimpleNamespace(
                directional_sanity=SimpleNamespace(
                    enabled=False,
                    min_abs_delta_price=0.0,
                    min_confidence=0.0,
                    consecutive_bars=2,
                ),
                price_motion_sanity=SimpleNamespace(
                    enabled=False,
                    k_vol=2.0,
                    flash_window_sec=10,
                    bleed_window_sec=300,
                    flash_threshold_norm=1.0,
                    bleed_threshold_norm=0.7,
                    require_bleed_ready=True,
                ),
            ),
        ),
        instruments={
            symbol: SimpleNamespace(
                tick_size="0.1",
                step_size="0.001",
                min_qty="0.001",
                min_notional="5",
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
                    entry_order_type="LIMIT",
                    entry_tif="GTX",
                    exit_order_type="MARKET",
                    exit_tif=None,
                    exit_limit_ttl_ms=None,
                ),
                safety_gates=SimpleNamespace(enabled=False),
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
                assets={symbol: SimpleNamespace(position_mode=position_mode)},
            )
        ),
        strategies_registry=None,
    )


def _mk_dm(*, symbol: str, position_mode: str, stale_ttl_sec: int = 15) -> tuple[DecisionMaking, _Bus]:
    bus = _Bus()
    cfg = _mk_cfg(symbol=symbol, position_mode=position_mode, stale_ttl_sec=stale_ttl_sec)
    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]
    return dm, bus


def test_flip_long_to_short_emits_reduce_only_close_and_defer():
    symbol = "BTCUSDT"
    dm, bus = _mk_dm(symbol=symbol, position_mode="STRICT", stale_ttl_sec=15)

    now_ms = 1_700_000_000_000

    dm.latest_portfolio = {
        "positions": [
            {
                "symbol": symbol,
                # SSOT
                "net_position": "1.25",
                # legacy may be missing in some feeds
                "avg_entry_price": "42000",
                "venues": ["binance"],
            }
        ],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    proposed: list[dict] = []

    def _fake_propose_trade_intent(**kwargs):
        proposed.append(dict(kwargs))
        return {"ok": True}

    dm._propose_trade_intent = _fake_propose_trade_intent  # type: ignore[method-assign]

    with patch("time.time", return_value=now_ms / 1000.0):
        res = dm._handle_flip_orchestration(
            symbol=symbol,
            intent_side="SELL",  # opposite of LONG => flip
            original_pld={"rid": "r1", "why_chain": ["x"], "price_ctx": {"entry_price": 1}},
            source="aurora",
        )

    assert res == "FLIP_CLOSE_PENDING"

    assert proposed, "Expected reduce-only close to be proposed"
    close = proposed[0]
    assert close["symbol"] == symbol
    assert close["reduce_only"] is True
    assert close["side"] == "SELL"
    assert str(close["qty"]) == "1.25"

    deferred = [e for e in bus.emits if e[0] == "EVT:INTENT_DEFERRED"]
    assert deferred, "Expected INTENT_DEFERRED emitted"
    payload = deferred[0][1] or {}
    assert payload.get("reason") == "FLIP_CLOSE_PENDING"
    assert payload.get("symbol") == symbol
    assert payload.get("retry_key", "").startswith(f"flip:{symbol}:SELL:")
    assert payload.get("next_allowed_ts") == now_ms + 15_000

    original_event = payload.get("original_event")
    assert isinstance(original_event, dict)
    assert "event_name" in original_event
    assert "payload_min" in original_event


def test_flip_unknown_portfolio_fail_closed_returns_nrr():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    dm.latest_portfolio = None
    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="BUY",
        original_pld={"rid": "r1"},
        source="aurora",
    )
    assert res == "NRR-PORTFOLIO-UNKNOWN"


def test_flip_flat_allows_open_returns_none():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    dm.latest_portfolio = {
        "positions": [],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="BUY",
        original_pld={"rid": "r1"},
        source="aurora",
    )
    assert res is None


def test_same_side_missing_position_mode_returns_config_invalid():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    # Force same-side scenario (LONG + BUY), but remove per-symbol position_mode config.
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }
    dm.config.strategies.aurora.assets = {}  # type: ignore[attr-defined]

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="BUY",
        original_pld={"rid": "r1"},
        source="aurora",
    )
    assert res == "CONFIG_POSITION_MODE_INVALID"


def test_emit_reduce_only_close_uses_legacy_positionAmt_when_net_position_missing():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "positionAmt": "0.7"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    proposed: list[dict] = []

    def _fake_propose_trade_intent(**kwargs):
        proposed.append(dict(kwargs))
        return {"ok": True}

    dm._propose_trade_intent = _fake_propose_trade_intent  # type: ignore[method-assign]

    dm._emit_reduce_only_close(symbol, reason="r", rid="rid-close", strategy_id="aurora")

    assert proposed, "Expected close intent to be proposed"
    assert str(proposed[0]["qty"]) == "0.7"
    assert proposed[0]["side"] == "SELL"  # LONG -> SELL
    assert proposed[0]["reduce_only"] is True


def test_emit_reduce_only_close_fail_closed_on_invalid_qty_skips_emit():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    # Ensure qty extraction will fail but position state is forced LONG.
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "bad"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    proposed: list[dict] = []

    def _fake_propose_trade_intent(**kwargs):
        proposed.append(dict(kwargs))
        return {"ok": True}

    dm._propose_trade_intent = _fake_propose_trade_intent  # type: ignore[method-assign]
    dm._get_position_state = lambda _symbol: "LONG"  # type: ignore[method-assign]

    dm._emit_reduce_only_close(symbol, reason="r", rid="rid-close", strategy_id="aurora")
    assert not proposed, "Expected fail-closed: invalid qty should skip emit"


def test_emit_reduce_only_close_noop_when_position_not_long_or_short():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "0"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    proposed: list[dict] = []

    def _fake_propose_trade_intent(**kwargs):
        proposed.append(dict(kwargs))
        return {"ok": True}

    dm._propose_trade_intent = _fake_propose_trade_intent  # type: ignore[method-assign]
    dm._get_position_state = lambda _symbol: "FLAT"  # type: ignore[method-assign]

    dm._emit_reduce_only_close(symbol, reason="r", rid="rid-close", strategy_id="aurora")
    assert not proposed


def test_flip_missing_positions_stale_ttl_is_fail_closed_error():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }
    dm.config.domains.position_tracking.positions_stale_ttl_sec = None  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="positions_stale_ttl_sec"):
        dm._handle_flip_orchestration(
            symbol=symbol,
            intent_side="SELL",
            original_pld={"rid": "r1"},
            source="aurora",
        )


def test_flip_close_with_market_exit_succeeds():
    symbol = "BTCUSDT"
    dm, bus = _mk_dm(symbol=symbol, position_mode="STRICT")
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "0.9"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }
    dm.config.strategies.aurora.execution.entry_order_type = "LIMIT"  # type: ignore[attr-defined]
    dm.config.strategies.aurora.execution.entry_tif = "GTX"  # type: ignore[attr-defined]
    dm.config.strategies.aurora.execution.exit_order_type = "MARKET"  # type: ignore[attr-defined]
    dm.config.strategies.aurora.execution.exit_tif = None  # type: ignore[attr-defined]
    dm.config.strategies.aurora.execution.exit_limit_ttl_ms = None  # type: ignore[attr-defined]

    ok = dm._emit_reduce_only_close(symbol, reason="flip", rid="rid-market", strategy_id="aurora")
    assert ok is True

    proposed = [e for e in bus.emits if e[0] == "EVT:TRADE_INTENT_PROPOSED"]
    assert proposed, "Expected reduce-only close intent to be proposed"

    rejected = [
        e for e in bus.emits
        if e[0] == "EVT:TRADE_INTENT_REJECTED" and isinstance(e[1], dict) and e[1].get("reason_code") == "NRR-046"
    ]
    assert not rejected, "reduce_only close must not be rejected with NRR-046"


def test_flip_close_with_limit_exit_and_missing_ttl_degrades_to_market():
    symbol = "BTCUSDT"
    dm, bus = _mk_dm(symbol=symbol, position_mode="STRICT")
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1.1"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }
    dm.config.strategies.aurora.execution.exit_order_type = "LIMIT"  # type: ignore[attr-defined]
    dm.config.strategies.aurora.execution.exit_tif = "GTX"  # type: ignore[attr-defined]
    dm.config.strategies.aurora.execution.exit_limit_ttl_ms = None  # type: ignore[attr-defined]

    ok = dm._emit_reduce_only_close(symbol, reason="flip", rid="rid-limit", strategy_id="aurora")
    assert ok is True

    proposed = [e for e in bus.emits if e[0] == "EVT:TRADE_INTENT_PROPOSED"]
    assert proposed, "Expected degraded intent to still be proposed"
    payload = proposed[-1][1] or {}
    order = payload.get("order", {})
    assert order.get("order_type") == "MARKET"

    degraded = [e for e in bus.emits if e[0] == "EVT:TRADE_INTENT_DEGRADED"]
    assert degraded, "Expected TRADE_INTENT_DEGRADED event"
    assert degraded[-1][2] == "MISSING_TTL_FOR_LIMIT_EXIT"

    rejected = [
        e for e in bus.emits
        if e[0] == "EVT:TRADE_INTENT_REJECTED" and isinstance(e[1], dict) and e[1].get("reason_code") == "NRR-046"
    ]
    assert not rejected, "reduce_only close must not be rejected with NRR-046 when degraded"


def test_emit_reduce_only_close_returns_false_when_intent_rejected():
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode="STRICT")
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "0.4"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    def _rejecting_propose(**_kwargs):
        return None

    dm._propose_trade_intent = _rejecting_propose  # type: ignore[method-assign]
    ok = dm._emit_reduce_only_close(symbol, reason="flip", rid="rid-reject", strategy_id="aurora")
    assert ok is False


@pytest.mark.parametrize("position_mode", ["STRICT", "DYNAMIC"])
def test_same_side_behavior_unchanged(position_mode: str):
    symbol = "BTCUSDT"
    dm, _bus = _mk_dm(symbol=symbol, position_mode=position_mode)

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1"}],
        "equity": "1000",
        "positions_last_ts_ms": int(time.time() * 1000),
    }

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="BUY",  # same side for LONG
        original_pld={"rid": "r1"},
        source="aurora",
    )

    if position_mode == "DYNAMIC":
        assert res is None
    else:
        assert res == "ANTI_PYRAMIDING_BLOCK"
