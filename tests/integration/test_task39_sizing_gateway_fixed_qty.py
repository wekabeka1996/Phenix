import logging
import time
from types import SimpleNamespace

from vfoundation.core.protocol import Message


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


def test_gateway_sol_fixed_qty_emits_qty_1(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    fsm = _DummyFsm()
    dm = DecisionMaking.__new__(DecisionMaking)
    dm.fsm = fsm
    dm.logger = logging.getLogger("tests.task39.gateway")

    # Minimal config for sizing
    pos_sizing = SimpleNamespace(
        risk_fraction_q=None,
        liquidity_kappa_mode="dynamic",
        liquidity_kappa=1.0,
        sizing=SimpleNamespace(mode="fixed_qty", fixed_qty={"SOLUSDT": 1.0}),
    )
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(decision_making=SimpleNamespace(position_sizing=pos_sizing)),
        instruments={"SOLUSDT": SimpleNamespace(tick_size=0.01, step_size=0.01)},
    )
    dm.min_pos_size_usd = 0  # allow small, focus on fixed qty
    dm.liq_cap_usd = 10_000

    # Bypass unrelated gates
    now_ms = int(time.time() * 1000)
    dm.symbol_states = {
        "SOLUSDT": {
            "features": {"ts": now_ms},
            "risk": {
                "ts": now_ms,
                "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0},
            },
            "risk_skew_guard": {},
        }
    }
    dm.features_ttl_sec = 60
    dm.latest_portfolio = {"equity": "1000", "positions": []}
    dm._check_strategy_arbitration = lambda _symbol, _strategy_id, **_k: {"allowed": True, "reason": None}
    dm._qos_allow = lambda _symbol, *_a, **_k: (True, None)
    dm._handle_flip_orchestration = lambda *_a, **_k: None
    dm._warmup_gate_before_trade_intent = lambda **_k: False
    dm._record_blocked_intent = lambda *_a, **_k: None
    dm._record_accepted_intent = lambda *_a, **_k: None
    dm._record_qos_intent = lambda *_a, **_k: None
    dm._get_risk_skew_config = lambda *_a, **_k: 9999
    dm._get_aurora_instrument_cfg = lambda _symbol: SimpleNamespace(max_risk_score=1.0)
    dm._stable_retry_key = lambda **_k: "retry"
    dm._emit_intent_deferred_v1 = lambda **_k: None
    dm._compute_risk_contract_cap_notional = lambda *_a, **_k: None
    dm._compute_regime_scaled_notional = lambda *_a, **_k: None
    dm._precheck_exposure_cache = lambda *_a, **_k: True

    # Ensure _propose_trade_intent emits into our fsm without needing full config
    dm._tca_prefs = {"max_slippage_bps": 10, "max_latency_ms": 500, "maker_preference": "neutral"}
    dm._risk_budgets = {"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200}

    evt = Message(
        op="EVT",
        verb="STRATEGY_SIGNAL_PRODUCED",
        src="strategy",
        dst="decision_making",
        rid="rid-1",
        pld={
            "strategy_id": "mean_reversion",
            "symbol": "SOLUSDT",
            "side": "BUY",
            "rid": "sig-1",
            "why_chain": [],
            "ts_ms": now_ms,
            "price_ctx": {"entry_price": "20"},
        },
        why="test",
    )

    dm._on_strategy_signal_gateway(evt)

    intents = [payload for name, payload in fsm.emitted if name == "EVT:TRADE_INTENT_PROPOSED"]
    assert intents, "expected trade intent emission"
    qty = intents[-1]["order"]["qty"]
    assert str(qty) in ("1.0", "1.00")
