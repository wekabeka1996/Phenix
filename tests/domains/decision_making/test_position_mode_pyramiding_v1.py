from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.decision_making.core.facade import DecisionMaking


class _Bus:
    def listen(self, _event: str, _handler: object) -> None:
        pass

    def emit(self, _event_name: str, _payload: dict | None = None, _why: str | None = None, data_ref: object = None) -> None:
        pass


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
        neocortex_enforcement_mode="shadow",
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


def _dm_cfg_with_flip(*, enabled: bool):
    cfg = _dm_cfg()
    cfg.flip.enabled = enabled
    return cfg


def _mk_cfg(*, symbol: str, position_mode: str):
    return SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": "neutral"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200},
        ),
        domains=SimpleNamespace(position_tracking=SimpleNamespace(positions_stale_ttl_sec=60)),
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
                flip=SimpleNamespace(enabled=True, hysteresis_mult=1.3),
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
                assets={symbol: SimpleNamespace(position_mode=position_mode)},
            )
        ),
        strategies_registry=None,
    )


def test_position_mode_dynamic_allows_same_side_entry():
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    cfg = _mk_cfg(symbol=symbol, position_mode="DYNAMIC")

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=_Bus(), config=cfg)  # type: ignore[arg-type]

    # Existing LONG position (SSOT: net_position)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1", "avg_entry_price": "100", "venues": ["binance"]}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="BUY",
        original_pld={"rid": "r1"},
        source="aurora",
    )
    assert res is None


def test_position_mode_strict_blocks_same_side_entry():
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    cfg = _mk_cfg(symbol=symbol, position_mode="STRICT")

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=_Bus(), config=cfg)  # type: ignore[arg-type]

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1", "avg_entry_price": "100", "venues": ["binance"]}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="BUY",
        original_pld={"rid": "r1"},
        source="aurora",
    )
    assert res == "ANTI_PYRAMIDING_BLOCK"


def test_position_mode_strict_blocks_same_side_entry_when_flip_disabled():
    """Regression: anti-pyramiding must not be bypassed when flip.enabled=False."""
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    cfg = _mk_cfg(symbol=symbol, position_mode="STRICT")

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg_with_flip(enabled=False)
        dm = DecisionMaking(fsm=_Bus(), config=cfg)  # type: ignore[arg-type]

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "-1", "avg_entry_price": "100", "venues": ["binance"]}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="SELL",
        original_pld={"rid": "r2"},
        source="aurora",
    )
    assert res == "ANTI_PYRAMIDING_BLOCK"


def test_position_mode_dynamic_allows_same_side_entry_when_flip_disabled():
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    cfg = _mk_cfg(symbol=symbol, position_mode="DYNAMIC")

    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg_with_flip(enabled=False)
        dm = DecisionMaking(fsm=_Bus(), config=cfg)  # type: ignore[arg-type]

    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "-1", "avg_entry_price": "100", "venues": ["binance"]}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="SELL",
        original_pld={"rid": "r3"},
        source="aurora",
    )
    assert res is None
