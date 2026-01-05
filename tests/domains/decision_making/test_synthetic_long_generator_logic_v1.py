from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.decision_making.decision_making import DecisionMaking


class _Bus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict | None]] = []

    def listen(self, _event: str, _handler: object) -> None:
        pass

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
        **_kwargs: object,
    ) -> None:
        self.emitted.append((event_name, payload))


def _dm_cfg(*, features_ttl_sec: int = 60):
    qos = SimpleNamespace(
        exposure_block_cooldown_sec=0,
        max_intents_per_minute_per_symbol=10_000,
        mode="enforce",
        symbol_cooldown_sec=0,
        enforce=True,
    )
    position_sizing = SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000)
    arming = SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1)
    features = SimpleNamespace(ttl_sec=features_ttl_sec)
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
        fail_closed_on_degraded_context=False,
        degraded_context_critical_keys=[],
        degraded_context_critical_keys_by_strategy={},
    )


def _mk_cfg(
    *,
    symbol: str,
    signal_threshold: float,
    side_bias_penalty_factor: float,
    scoring_version: str,
    normalize_signals_mode: str,
    directional_features: list[str],
    strength_features: list[str],
    strength_alpha: float,
    strength_cap: float,
    weights: dict[str, float],
    feature_neutrals: dict[str, float],
    essential_features: list[str],
):
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
            )
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    signal_threshold=signal_threshold,
                    retry_ttl_ms=1000,
                    retry_max_count=1,
                    retry_backoff_factor=1.0,
                    side_bias_penalty_factor=side_bias_penalty_factor,
                    side_bias_window_sec=60,
                    side_bias_target_ratio=0.6,
                    side_bias_min_intents=1,
                    regime_threshold_multipliers={"DEFAULT": 1.0},
                    signals=SimpleNamespace(
                        normalize_signals_mode=normalize_signals_mode,
                        enable_new_metrics=True,
                        delta_price_cap_pct=0.02,
                    ),
                    direction_strength_scoring=SimpleNamespace(
                        directional_features=directional_features,
                        strength_features=strength_features,
                        strength_alpha=strength_alpha,
                        strength_cap=strength_cap,
                    ),
                    kelly=None,
                ),
                assets={
                    symbol: SimpleNamespace(
                        enabled=True,
                        position_mode="STRICT",
                        allowed_regimes=[],
                        # Scoring config is read from instrument_cfg first in v2 path.
                        scoring_version=scoring_version,
                        weights=weights,
                        feature_neutrals=feature_neutrals,
                        essential_features=essential_features,
                        liquidity_gate=SimpleNamespace(enabled=False),
                    )
                },
            )
        ),
        strategies_registry=None,
    )


def _seed_dm_ready_state(dm: DecisionMaking, *, symbol: str, now_ms: int, feats: dict, ready: dict[str, bool]) -> None:
    dm.latest_portfolio = {"positions": [], "equity": "1000", "positions_last_ts_ms": now_ms}
    dm._per_symbol_regimes[symbol] = {
        "symbol": symbol,
        "regime": "MEAN_REVERSION",
        "confidence": 1.0,
        "warmup": {"full_ready": True, "ticks_seen": 999},
    }
    dm.symbol_states[symbol]["features"] = {
        "ts": now_ms,
        "symbol": symbol,
        "features": feats,
        "warmup": {"full_ready": True, "ready": dict(ready)},
        "price_motion": {
            "pm_norm_10s": 0.0,
            "pm_norm_60s": 0.0,
            "pm_norm_300s": 0.0,
            "vol_pct_10s": 0.0,
            "vol_pct_60s": 0.0,
            "vol_pct_300s": 0.0,
        },
    }
    dm.symbol_states[symbol]["risk"] = {
        "symbol": symbol,
        "ts": now_ms,
        "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0},
    }


def _get_last_intent_side(bus: _Bus) -> str | None:
    for evt, pld in reversed(bus.emitted):
        if evt == "EVT:TRADE_INTENT_PROPOSED" and isinstance(pld, dict):
            return str(pld.get("side")) if pld.get("side") is not None else None
    return None


def test_normalize_signals_true_cannot_emit_sell_with_nonnegative_weights():
    """
    If normalize_signals=True, code maps metrics into [0,1] and uses abs(delta_price),
    so score cannot be negative when weights are non-negative. SELL requires score <= -threshold.
    """
    symbol = "BTCUSDT"
    bus = _Bus()
    cfg = _mk_cfg(
        symbol=symbol,
        signal_threshold=0.1,
        side_bias_penalty_factor=0.0,
        scoring_version="v1",  # irrelevant for normalize_signals=True branch
        normalize_signals_mode="legacy_v1",
        directional_features=["delta_price"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        weights={"delta_price": 1.0},
        feature_neutrals={"delta_price": 0.0},
        essential_features=["delta_price"],
    )

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    now_ms = 1_700_000_000_000
    # "Bearish" raw delta_price is negative, but normalize_signals uses abs(delta_price) -> positive dp_phi.
    feats = {"price": Decimal("100"), "delta_price": Decimal("-2.0")}
    _seed_dm_ready_state(dm, symbol=symbol, now_ms=now_ms, feats=feats, ready={"delta_price": True})

    with patch("apps.reference.domains.decision_making.decision_making.wal.append", lambda *_a, **_k: None):
        with patch("time.time", return_value=now_ms / 1000.0):
            dm._check_and_trigger_decision_for_symbol(symbol)

    assert _get_last_intent_side(bus) == "buy"


def test_normalize_signals_false_v2_can_emit_sell_on_bearish_features():
    """
    With normalize_signals=False and scoring_version=v2, score preserves sign via (x - neutral),
    so sufficiently bearish synthetic features must yield SELL (score <= -threshold).
    """
    symbol = "BTCUSDT"
    bus = _Bus()
    cfg = _mk_cfg(
        symbol=symbol,
        signal_threshold=0.1,
        side_bias_penalty_factor=0.0,
        scoring_version="v2",
        normalize_signals_mode="signed_v2",
        directional_features=["obi", "tfi", "delta_price"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        weights={"obi": 0.15, "tfi": 0.15, "delta_price": 0.10},
        feature_neutrals={"obi": 0.0, "tfi": 0.0, "delta_price": 0.0},
        essential_features=["obi", "delta_price"],
    )

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    now_ms = 1_700_000_000_000
    feats = {
        "price": Decimal("100"),
        "obi": Decimal("-1"),
        "tfi": Decimal("-1"),
        # dp_raw=-2 => dp_pct=-0.02 => dp_norm=-1 (capped)
        "delta_price": Decimal("-2.0"),
    }
    _seed_dm_ready_state(
        dm,
        symbol=symbol,
        now_ms=now_ms,
        feats=feats,
        ready={"obi": True, "tfi": True, "delta_price": True},
    )

    with patch("apps.reference.domains.decision_making.decision_making.wal.append", lambda *_a, **_k: None):
        with patch("time.time", return_value=now_ms / 1000.0):
            dm._check_and_trigger_decision_for_symbol(symbol)

    assert _get_last_intent_side(bus) == "sell"


def test_side_bias_penalty_is_asymmetric_and_does_not_block_sell_when_buy_share_high():
    """
    With asymmetric thresholds, BUY overheating raises only thr_buy and must not raise thr_sell.
    Therefore SELL remains reachable even when BUY share is high.
    """
    symbol = "BTCUSDT"
    now_ms = 1_700_000_000_000
    now_sec = now_ms / 1000.0

    base_cfg_kwargs = dict(
        symbol=symbol,
        signal_threshold=0.1,
        scoring_version="v2",
        normalize_signals_mode="off",
        directional_features=["delta_price"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        weights={"delta_price": 1.0},
        feature_neutrals={"delta_price": 0.0},
        essential_features=["delta_price"],
    )

    # Case A: no penalty -> SELL should pass for score=-0.11 and threshold=0.1
    bus_a = _Bus()
    cfg_a = _mk_cfg(side_bias_penalty_factor=0.0, **base_cfg_kwargs)
    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm_a = DecisionMaking(fsm=bus_a, config=cfg_a)  # type: ignore[arg-type]

    feats = {"price": Decimal("1"), "delta_price": Decimal("-0.0022")}  # dp_norm=-0.11
    _seed_dm_ready_state(dm_a, symbol=symbol, now_ms=now_ms, feats=feats, ready={"delta_price": True})

    # Make history BUY-heavy (sell_share -> low).
    dm_a._side_intent_window = {symbol: {"buys": [now_sec - 1, now_sec - 2], "sells": []}}

    with patch("apps.reference.domains.decision_making.decision_making.wal.append", lambda *_a, **_k: None):
        with patch("time.time", return_value=now_sec):
            dm_a._check_and_trigger_decision_for_symbol(symbol)

    assert _get_last_intent_side(bus_a) == "sell"

    # Case B: strong penalty -> BUY threshold increases, but SELL threshold is unchanged.
    bus_b = _Bus()
    cfg_b = _mk_cfg(side_bias_penalty_factor=1.0, **base_cfg_kwargs)
    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm_b = DecisionMaking(fsm=bus_b, config=cfg_b)  # type: ignore[arg-type]

    _seed_dm_ready_state(dm_b, symbol=symbol, now_ms=now_ms, feats=feats, ready={"delta_price": True})
    dm_b._side_intent_window = {symbol: {"buys": [now_sec - 1, now_sec - 2], "sells": []}}

    with patch("apps.reference.domains.decision_making.decision_making.wal.append", lambda *_a, **_k: None):
        with patch("time.time", return_value=now_sec):
            dm_b._check_and_trigger_decision_for_symbol(symbol)

    assert _get_last_intent_side(bus_b) == "sell"

    # Case C: with the same BUY-heavy history, BUY should become harder (thr_buy increased).
    bus_c = _Bus()
    cfg_c = _mk_cfg(side_bias_penalty_factor=1.0, **base_cfg_kwargs)
    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg()
        dm_c = DecisionMaking(fsm=bus_c, config=cfg_c)  # type: ignore[arg-type]

    feats_bull = {"price": Decimal("1"), "delta_price": Decimal("0.0022")}  # dp_norm=+0.11
    _seed_dm_ready_state(dm_c, symbol=symbol, now_ms=now_ms, feats=feats_bull, ready={"delta_price": True})
    dm_c._side_intent_window = {symbol: {"buys": [now_sec - 1, now_sec - 2], "sells": []}}

    with patch("apps.reference.domains.decision_making.decision_making.wal.append", lambda *_a, **_k: None):
        with patch("time.time", return_value=now_sec):
            dm_c._check_and_trigger_decision_for_symbol(symbol)

    assert _get_last_intent_side(bus_c) is None


def test_features_ttl_blocks_trade_intent_on_stale_features():
    symbol = "BTCUSDT"
    bus = _Bus()
    cfg = _mk_cfg(
        symbol=symbol,
        signal_threshold=0.1,
        side_bias_penalty_factor=0.0,
        scoring_version="v2",
        normalize_signals_mode="off",
        directional_features=["obi", "delta_price"],
        strength_features=[],
        strength_alpha=0.5,
        strength_cap=1.0,
        weights={"obi": 1.0, "delta_price": 1.0},
        feature_neutrals={"obi": 0.0, "delta_price": 0.0},
        essential_features=["obi", "delta_price"],
    )

    with patch("apps.reference.domains.decision_making.decision_making.DomainConfigResolver") as MockResolver:
        # TTL=1s
        MockResolver.return_value.get_decision_making.return_value = _dm_cfg(features_ttl_sec=1)
        dm = DecisionMaking(fsm=bus, config=cfg)  # type: ignore[arg-type]

    now_ms = 1_700_000_000_000
    stale_ms = now_ms - 2_000
    feats = {"price": Decimal("100"), "obi": Decimal("1"), "delta_price": Decimal("2")}
    _seed_dm_ready_state(dm, symbol=symbol, now_ms=stale_ms, feats=feats, ready={"obi": True, "delta_price": True})

    with patch("apps.reference.domains.decision_making.decision_making.wal.append", lambda *_a, **_k: None):
        with patch("time.time", return_value=now_ms / 1000.0):
            dm._check_and_trigger_decision_for_symbol(symbol)

    assert _get_last_intent_side(bus) is None
