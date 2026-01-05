import logging

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class _Bus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, _event: str, _handler) -> None:
        return

    def emit(self, event_name: str, payload: dict | None = None, *_a, **_k) -> None:
        self.emitted.append((event_name, payload or {}))


def _mk_context(*, symbol: str, ts_ms: int, regime: str) -> dict:
    # Produce a deterministic bullish score between 0.05 and 0.10:
    # - Keep only essential directional features ready (obi, delta_price).
    # - Set delta_price so dp_norm ~= 0.15 => dir_score ~= (0.1*0.15)/(0.15+0.1) = 0.06
    features = {
        "price": 100.0,
        "liquidity_kappa": 0.5,
        "obi": 0.0,
        "delta_price": 0.3,  # dp_pct=0.003 => dp_norm=0.15 (cap=0.02)
    }
    return {
        "features": {
            "symbol": symbol,
            "ts": ts_ms,
            "features": features,
            "warmup": {"full_ready": True, "ready": {"obi": True, "delta_price": True}},
        },
        "risk_params": {"symbol": symbol, "ts": ts_ms, "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}},
        "portfolio": {"equity": "1000", "positions": [], "positions_last_ts_ms": ts_ms},
        "regime": {"symbol": symbol, "ts": ts_ms, "regime": regime, "warmup": {"full_ready": True}},
    }


def test_task47_lowered_mean_reversion_threshold_allows_intent_for_btc() -> None:
    symbol = "BTCUSDT"
    ts_ms = 1_700_000_000_000

    base_cfg = get_config()
    assert base_cfg.strategies.aurora is not None

    # Control case: MEAN_REVERSION multiplier at 1.0 -> threshold = 0.1, score=0.06 => neutral => no intent.
    btc_cfg = base_cfg.strategies.aurora.assets[symbol]
    btc_cfg_control = btc_cfg.model_copy(
        deep=True,
        update={
            "regime_thresholds": {**(btc_cfg.regime_thresholds or {}), "MEAN_REVERSION": 1.0},
            "allowed_regimes": list(set((btc_cfg.allowed_regimes or []) + ["MEAN_REVERSION"])),
        },
    )
    aurora_cfg_control = base_cfg.strategies.aurora.model_copy(
        deep=True, update={"assets": {**base_cfg.strategies.aurora.assets, symbol: btc_cfg_control}}
    )
    control_cfg = base_cfg.model_copy(
        deep=True,
        update={
            "strategies": base_cfg.strategies.model_copy(deep=True, update={"aurora": aurora_cfg_control})
        },
    )

    bus = _Bus()
    dm = DecisionMaking(fsm=bus, config=control_cfg)
    dm.logger = logging.getLogger("tests.task47.dm")
    dm.config.domains.decision_making.directional_sanity.enabled = False
    dm.config.domains.decision_making.price_motion_sanity.enabled = False
    dm.latest_portfolio = {"equity": "1000", "positions": [], "positions_last_ts_ms": ts_ms}
    dm._per_symbol_regimes[symbol] = {"warmup": {"full_ready": True}}
    dm._warmup_gate_before_trade_intent = lambda **_k: False  # bypass unrelated readiness
    dm._record_blocked_intent = lambda *_a, **_k: None
    dm._record_accepted_intent = lambda *_a, **_k: None

    dm._make_decision_for_symbol(symbol, _mk_context(symbol=symbol, ts_ms=ts_ms, regime="MEAN_REVERSION"), "rid-1")
    assert not any(evt == "EVT:TRADE_INTENT_PROPOSED" for evt, _ in bus.emitted)

    # Positive case: lower MEAN_REVERSION multiplier -> lower threshold -> same score becomes an intent.
    btc_cfg_low = btc_cfg.model_copy(
        deep=True,
        update={
            "regime_thresholds": {**(btc_cfg.regime_thresholds or {}), "MEAN_REVERSION": 0.5},
            "allowed_regimes": list(set((btc_cfg.allowed_regimes or []) + ["MEAN_REVERSION"])),
        },
    )
    aurora_cfg_low = base_cfg.strategies.aurora.model_copy(
        deep=True, update={"assets": {**base_cfg.strategies.aurora.assets, symbol: btc_cfg_low}}
    )
    low_cfg = base_cfg.model_copy(
        deep=True,
        update={
            "strategies": base_cfg.strategies.model_copy(deep=True, update={"aurora": aurora_cfg_low})
        },
    )

    bus2 = _Bus()
    dm2 = DecisionMaking(fsm=bus2, config=low_cfg)
    dm2.logger = logging.getLogger("tests.task47.dm")
    dm2.config.domains.decision_making.directional_sanity.enabled = False
    dm2.config.domains.decision_making.price_motion_sanity.enabled = False
    dm2.latest_portfolio = {"equity": "1000", "positions": [], "positions_last_ts_ms": ts_ms}
    dm2._per_symbol_regimes[symbol] = {"warmup": {"full_ready": True}}
    dm2._warmup_gate_before_trade_intent = lambda **_k: False
    dm2._record_blocked_intent = lambda *_a, **_k: None
    dm2._record_accepted_intent = lambda *_a, **_k: None

    dm2._make_decision_for_symbol(symbol, _mk_context(symbol=symbol, ts_ms=ts_ms, regime="MEAN_REVERSION"), "rid-2")
    intents = [pld for (evt, pld) in bus2.emitted if evt == "EVT:TRADE_INTENT_PROPOSED"]
    assert len(intents) == 1
    assert intents[0]["strategy"] == "aurora"
