"""
Regime-based threshold multiplier should affect entry frequency.
"""

import time
from vfoundation.core.protocol import Message


class Bus:
    def __init__(self):
        self.listeners = {}

    def listen(self, n, cb):
        self.listeners.setdefault(n, []).append(cb)

    def emit(self, n, payload=None, why=None, data_ref=None):
        for cb in self.listeners.get(n, []):
            cb(Message(op="EVT", verb=n.split(":")[1], src="t", dst="a", pld=payload or {
            }, why=why or "", data_ref=data_ref or []))


def _decision(cfg):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    return DecisionMaking(fsm=Bus(), config=cfg)


def _run(dm, regime_name, feats_score=0.1):
    intents = []
    dm.fsm.listen("EVT:TRADE_INTENT_PROPOSED", lambda m: intents.append(m))
    dm.on_portfolio(Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="t", dst="d", pld={
                    "equity_total_usdt": 10000.0, "equity_free_usdt": 10000.0, "positions": []}))
    dm.on_risk(Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED", src="t", dst="d", pld={
               "symbol": "ETHUSDT", "risk_parameters": {"is_trading_allowed": True}}))
    dm.on_regime(Message(op="EVT", verb="REGIME_DETECTED", src="t", dst="d", pld={
                 "symbol": "ETHUSDT", "regime": regime_name, "confidence": "0.8"}))
    dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED", src="t", dst="d",
                           pld={"ts": int(time.time()*1000), "symbol": "ETHUSDT", "features": {"obi": feats_score, "tfi": 0.0, "delta_price": 0.0, "price": 2000.0}}))
    return len(intents)


def test_threshold_multiplier_blocks_in_high_vol_and_allows_in_low_vol():
    cfg = {
        "trading": {
            "decision": {
                "signal_weights": {"obi": 1.0, "tfi": 0.0, "delta_price": 0.0},
                "signal_threshold": 0.1,
                "regime_threshold_multipliers": {"HIGH_VOLATILITY": 1.5, "LOW_VOLATILITY": 0.8, "DEFAULT": 1.0},
                "bar_gating": {"enable": False},
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000, "risk_fraction_q": 0.01, "liquidity_kappa": 1.0},
            },
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "execution": {"manage": {"auto": True, "brackets": {"sl": {"fixed_bps": 60}, "tp": {"fixed_bps": 120}}}},
            "tca_prefs": {"max_slippage_bps": 50.0},
            "risk_budgets": {"trade_cvar95_max_bps": 100.0},
        }
    }
    dm = _decision(cfg)
    # With obi=0.1 and base threshold 0.1:
    # HIGH_VOL threshold=0.15 -> no entry; LOW_VOL threshold=0.08 -> entry
    hv = _run(dm, "HIGH_VOLATILITY", feats_score=0.1)
    # sleep tiny to avoid QoS race in some environments
    time.sleep(0.01)
    lv = _run(dm, "LOW_VOLATILITY", feats_score=0.1)
    assert hv == 0 and lv == 1
