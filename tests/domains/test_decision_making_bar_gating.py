"""
Test that bar gating prevents multiple decisions within the same M15 bar
when enabled in configuration.
"""

import time
from vfoundation.core.protocol import Message


class FSMCore:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def listen(self, event_name: str, callback) -> None:
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload: dict, why: str, data_ref=None) -> None:
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                callback(
                    Message(
                        op="EVT",
                        verb=event_name.split(":")[1],
                        src="test",
                        dst="any",
                        pld=payload,
                        why=why,
                        data_ref=data_ref or [],
                    )
                )


def test_bar_gating_allows_only_one_intent_per_bar(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    bar_ms = 15 * 60 * 1000
    now_ms = int(time.time() * 1000)
    bar_index = now_ms // bar_ms
    ts_bar = bar_index * bar_ms + (bar_ms - 1000)  # near bar end

    cfg = {
        "trading": {
            "mode": "testnet",
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
                "bar_gating": {"enable": True, "bar_ms": bar_ms},
                "position_sizing": {
                    "min_position_size_usd": 10.0,
                    "liquidity_based_cap_usd": 10000.0,
                },
            },
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "tca_prefs": {"max_slippage_bps": 50.0},
            "risk_budgets": {"trade_cvar95_max_bps": 100.0},
        }
    }

    fsm = FSMCore()
    dm = DecisionMaking(fsm=fsm, config=cfg)

    # Track emitted intents
    emitted = []

    def on_intent(msg: Message):
        emitted.append(msg)

    dm.fsm.listen("EVT:TRADE_INTENT_PROPOSED", on_intent)

    # Provide portfolio and risk
    dm.on_portfolio(
        Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="test",
            dst="decision_making",
            pld={"equity_total_usdt": 10000.0,
                 "equity_free_usdt": 10000.0, "positions": []},
        )
    )

    dm.on_risk(
        Message(
            op="EVT",
            verb="RISK_ASSESSMENT_COMPLETED",
            src="test",
            dst="decision_making",
            pld={"symbol": "ETHUSDT", "risk_parameters": {
                "is_trading_allowed": True}},
        )
    )

    # Emit two features events within the same bar
    feats = {
        "ts": ts_bar,
        "symbol": "ETHUSDT",
        "features": {"obi": 0.5, "tfi": 0.4, "delta_price": 0.0, "price": 2000.0},
    }
    dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED",
                   src="test", dst="decision_making", pld=feats))
    # Second event with ts slightly later but same bar index
    feats2 = dict(feats)
    feats2["ts"] = ts_bar + 500
    dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED",
                   src="test", dst="decision_making", pld=feats2))

    # Assert only one intent emitted
    assert len(emitted) == 1, f"Expected 1 intent, got {len(emitted)}"
