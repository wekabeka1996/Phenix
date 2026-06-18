from unittest.mock import MagicMock

from vfoundation.core.protocol import Message

from apps.reference.domains.decision_making.core.event_handlers import DMEventHandlers
from apps.reference.domains.decision_making.gates.readiness_gates import ReadinessGates


def _handlers():
    clock = MagicMock()
    clock.now_ms.return_value = 1_700_000_001_000
    alpha_registry = MagicMock()
    alpha_registry.calculate_all_alpha.return_value = []
    return DMEventHandlers(
        fsm=MagicMock(),
        clock=clock,
        config=MagicMock(),
        symbol_states={},
        per_symbol_regimes={},
        shared_state={},
        dlog=MagicMock(),
        alpha_registry=alpha_registry,
        handle_regime_flip_fn=lambda _symbol, _payload: None,
        record_blocked_fn=lambda _symbol: None,
        arming_require_regime_warmup=True,
        behavior_enabled=False,
        behavior_state={},
        logger=MagicMock(),
    )


def test_decision_making_caches_trade_flow_metadata_without_blocking():
    handlers = _handlers()
    payload = {
        "ts": 1_700_000_000_000,
        "symbol": "BTCUSDT",
        "tf_sec": 180,
        "features": {"price": "100.0", "tfi": "0"},
        "warmup": {"full_ready": True, "ticks_seen": 10},
        "trade_flow_state": "degraded",
        "trade_flow_age_ms": 61_000,
        "trade_flow_last_trade_ts_ms": 1_699_999_939_000,
        "trade_flow_window_sec": 60,
    }

    handlers.on_features(
        Message(
            name="EVT:FEATURES_CALCULATED",
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld=payload,
        )
    )

    cached = handlers.symbol_states["BTCUSDT"]["features"]
    assert cached["trade_flow_state"] == "degraded"
    assert cached["trade_flow_age_ms"] == 61_000
    assert cached["_received_ts"] == handlers._clock.now_ms.return_value
    handlers.alpha_registry.calculate_all_alpha.assert_called_once()


def test_readiness_gate_ignores_trade_flow_state_in_t6c2():
    dm = MagicMock()
    dm._clock.now_ms.return_value = 1_700_000_001_000
    dm.config.system.market_data.bar_ttl_ms = 10_000
    dm.config.system.market_data.bar_event_age_mode = "received"
    dm.features_ttl_sec = 30.0
    dm.logger = MagicMock()

    features = {
        "ts": 1_700_000_000_000,
        "_received_ts": 1_700_000_000_500,
        "bar_close_ts": 1_700_000_000_000,
        "tf_sec": 180,
        "trade_flow_state": "degraded",
        "trade_flow_age_ms": 61_000,
    }

    assert ReadinessGates.features_ready(dm, "BTCUSDT", features) is True
