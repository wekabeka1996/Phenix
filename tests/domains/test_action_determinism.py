"""
Determinism test: the same psi/regime/config produces the same action.
"""

import time
from vfoundation.core.protocol import Message


class Bus:
    def __init__(self):
        self.listeners = {}

    def listen(self, name, cb):
        self.listeners.setdefault(name, []).append(cb)

    def emit(self, name, payload=None, why=None, data_ref=None):
        for cb in self.listeners.get(name, []):
            cb(Message(op="EVT", verb=name.split(":")[
               1], src="test", dst="any", pld=payload or {}, why=why or "", data_ref=data_ref or []))


def _build_dm(cfg):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    bus = Bus()
    dm = DecisionMaking(fsm=bus, config=cfg)
    return dm


def test_action_determinism_same_psi_same_action():
    cfg = {
        "trading": {
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
                "bar_gating": {"enable": False},
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 10000,
                    "risk_fraction_q": 0.01,
                    "liquidity_kappa": 1.0,
                },
            },
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "execution": {"manage": {"auto": True, "brackets": {"sl": {"fixed_bps": 60}, "tp": {"fixed_bps": 120}}}},
            "tca_prefs": {"max_slippage_bps": 50.0},
            "risk_budgets": {"trade_cvar95_max_bps": 100.0},
        }
    }

    # add QoS under decision
    cfg["trading"]["decision"]["qos"] = {
        "symbol_cooldown_sec": 0.0,
        "exposure_block_cooldown_sec": 0.0,
        "mode": "shadow",
        "enforce": False,
        "max_intents_per_minute_per_symbol": 1000,
    }

    dm1 = _build_dm(cfg)
    dm2 = _build_dm(cfg)

    intents1, intents2 = [], []
    dm1.fsm.listen("EVT:TRADE_INTENT_PROPOSED", lambda m: intents1.append(m))
    dm2.fsm.listen("EVT:TRADE_INTENT_PROPOSED", lambda m: intents2.append(m))

    # shared test messages
    portfolio = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="test", dst="dm",
                        pld={"equity_total_usdt": 10000.0, "equity_free_usdt": 10000.0, "positions": []})
    risk = Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED", src="test", dst="dm",
                   pld={"symbol": "ETHUSDT", "risk_parameters": {"is_trading_allowed": True}})
    feats_pld = {
        "ts": int(time.time() * 1000),
        "symbol": "ETHUSDT",
        "features": {"obi": 0.4, "tfi": 0.3, "delta_price": 0.0, "price": 2000.0}
    }
    features = Message(op="EVT", verb="FEATURES_CALCULATED",
                       src="test", dst="dm", pld=feats_pld)

    # drive both DMs with identical events
    for dm in (dm1, dm2):
        dm.on_portfolio(portfolio)
        dm.on_risk(risk)
        dm.on_features(features)

    assert len(intents1) == 1 and len(intents2) == 1
    i1, i2 = intents1[0], intents2[0]
    assert i1.pld["side"] == i2.pld["side"]
    assert i1.pld["instrument"] == i2.pld["instrument"]
    # quantities must be equal after rounding (nested in order)
    assert str(i1.pld["order"]["qty"]) == str(
        i2.pld["order"]["qty"])  # deterministic sizing
