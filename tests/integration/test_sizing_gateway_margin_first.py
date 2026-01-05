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


def test_gateway_sol_margin_first_emits_qty(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    fsm = _DummyFsm()
    dm = DecisionMaking.__new__(DecisionMaking)
    dm.fsm = fsm
    dm.logger = logging.getLogger("tests.task39.gateway")

    # Minimal config for margin-first sizing (SSOT: instruments.<SYM>.sizing + instruments.<SYM>.execution)
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            risk_management=SimpleNamespace(trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0)),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
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
            "SOLUSDT": SimpleNamespace(
                tick_size="0.01",
                step_size="1",
                min_qty="1",
                min_notional="5",
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=10,
                    leverage_policy="verify_only",
                    max_notional_utilization=0.8,
                ),
                sizing=SimpleNamespace(margin_pct=0.02),
            )
        },
    )
    dm.min_pos_size_usd = 0  # allow tiny, focus on sizing wiring
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
    dm._get_aurora_instrument_cfg = lambda _symbol: SimpleNamespace(max_risk_score=None)
    dm._stable_retry_key = lambda **_k: "retry"
    dm._emit_intent_deferred_v1 = lambda **_k: None
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
    assert str(qty) in ("10", "10.0", "10.00")
