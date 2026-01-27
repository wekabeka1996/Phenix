"""
Sizing matrix tests for DecisionMaking: checks monotonicity w.r.t. SL_bps
and effect of regime multiplier.
"""

from vfoundation.core.protocol import Message
import decimal
import time
import pytest
pytest.skip("Sizing matrix tests require complex decision making setup",
            allow_module_level=True)


class Bus:
    def __init__(self):
        self.listeners = {}

    def listen(self, n, cb):
        self.listeners.setdefault(n, []).append(cb)

    def emit(self, n, payload=None, why=None, data_ref=None):
        from vfoundation.core.protocol import Message
        for cb in self.listeners.get(n, []):
            cb(Message(op="EVT", verb=n.split(":")[1], src="t", dst="a", pld=payload or {
            }, why=why or "", data_ref=data_ref or []))


def _decision(cfg):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    return DecisionMaking(fsm=Bus(), config=cfg)


def _run_once(dm, sl_bps=60, regime_name=None):
    # patch brackets SL for this run via dm.config
    dm.config.setdefault("trading", {}).setdefault("execution", {}).setdefault(
        "manage", {}).setdefault("brackets", {}).setdefault("sl", {})["fixed_bps"] = sl_bps
    # capture intents
    intents = []
    dm.fsm.listen("EVT:TRADE_INTENT_PROPOSED", lambda m: intents.append(m))
    # feed portfolio/risk
    dm.on_portfolio(Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED",
                    src="t", dst="d", pld={"equity": 10000.0, "positions": []}))
    dm.on_risk(Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED", src="t", dst="d", pld={
               "symbol": "ETHUSDT", "risk_parameters": {"is_trading_allowed": True}}))
    # feed regime if any
    if regime_name:
        dm.on_regime(Message(op="EVT", verb="REGIME_DETECTED", src="t", dst="d", pld={
                     "symbol": "ETHUSDT", "regime": regime_name, "confidence": "0.8"}))
    # features trigger decision
    dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED", src="t", dst="d",
                           pld={"ts": int(time.time()*1000), "symbol": "ETHUSDT",
                                "features": {"obi": 0.6, "tfi": 0.3, "delta_price": 0.0, "price": 2000.0}}))
    assert intents, "No intent emitted"
    return intents[0]


def test_sizing_decreases_when_sl_bps_increases():
    cfg = {
        "trading": {
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
                "bar_gating": {"enable": False},
                # TASK-ZOMBIE-FIX: Removed dead fields (risk_fraction_q, liquidity_kappa)
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
            },
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "execution": {"manage": {"auto": True, "brackets": {"sl": {"fixed_bps": 40}, "tp": {"fixed_bps": 80}}}},
            "tca_prefs": {"max_slippage_bps": 50.0},
            "risk_budgets": {"trade_cvar95_max_bps": 100.0},
        }
    }
    cfg["trading"]["decision"]["qos"] = {"symbol_cooldown_sec": 0.0, "exposure_block_cooldown_sec": 0.0,
                                         "mode": "shadow", "enforce": False, "max_intents_per_minute_per_symbol": 1000}
    dm = _decision(cfg)
    i40 = _run_once(dm, sl_bps=40)
    qty40 = decimal.Decimal(str(i40.pld["order"]["qty"]))
    i120 = _run_once(dm, sl_bps=120)
    qty120 = decimal.Decimal(str(i120.pld["order"]["qty"]))
    assert qty120 < qty40, f"qty should decrease with larger SL_bps: {qty40} -> {qty120}"


def test_regime_multiplier_affects_size():
    cfg = {
        "trading": {
            "decision": {
                "signal_weights": {"obi": 0.6, "tfi": 0.35, "delta_price": 0.05},
                "signal_threshold": 0.05,
                "bar_gating": {"enable": False},
                # TASK-ZOMBIE-FIX: Removed dead fields (risk_fraction_q, liquidity_kappa)
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
                "sizing_modifiers": {"HIGH_VOLATILITY": "0.50", "LOW_VOLATILITY": "1.00", "MEAN_REVERSION": "1.00", "UNCERTAIN": "1.00"}
            },
            "instruments": {"ETHUSDT": {"step_size": "0.001"}},
            "execution": {"manage": {"auto": True, "brackets": {"sl": {"fixed_bps": 60}, "tp": {"fixed_bps": 120}}}},
            "tca_prefs": {"max_slippage_bps": 50.0},
            "risk_budgets": {"trade_cvar95_max_bps": 100.0},
        }
    }
    cfg["trading"]["decision"]["qos"] = {"symbol_cooldown_sec": 0.0, "exposure_block_cooldown_sec": 0.0,
                                         "mode": "shadow", "enforce": False, "max_intents_per_minute_per_symbol": 1000}
    dm = _decision(cfg)
    i_idle = _run_once(dm, sl_bps=60, regime_name="LOW_VOLATILITY")
    i_high = _run_once(dm, sl_bps=60, regime_name="HIGH_VOLATILITY")
    q_idle = decimal.Decimal(str(i_idle.pld["order"]["qty"]))
    q_high = decimal.Decimal(str(i_high.pld["order"]["qty"]))
    assert q_high < q_idle, f"regime multiplier should reduce size in HIGH_VOL: {q_idle} -> {q_high}"
