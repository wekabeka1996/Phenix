from __future__ import annotations

import time

from vfoundation.core.fsm_core import FSMCore

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons


def test_degraded_context_gate_can_defer_strategy_signal_per_strategy_override() -> None:
    cfg = ConfigLoader().load_config()

    # Enable gate via canonical domains.decision_making config.
    cfg.domains.decision_making.fail_closed_on_degraded_context = True

    # Global critical keys would not trigger (price provided), per-strategy override should.
    cfg.domains.decision_making.degraded_context_critical_keys = ["price"]
    cfg.domains.decision_making.degraded_context_critical_keys_by_strategy = {
        "stratX": ["ema_bias"],
    }

    fsm = FSMCore()
    deferred: list[dict] = []
    fsm.listen("EVT:INTENT_DEFERRED", lambda msg: deferred.append(msg.pld))

    dm = DecisionMaking(fsm=fsm, config=cfg)

    # Avoid test coupling to optional strategies registry arbitration.
    dm.strategies_registry = None

    symbol = "ETHUSDT"

    # Provide risk so the strategy gateway reaches feature-related gates.
    fsm.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {"symbol": symbol, "ts": int(time.time() * 1000), "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}},
        why="test",
    )

    # Provide features with only price; ema_bias missing => should defer when per-strategy override says ema_bias is critical.
    now_ms = int(time.time() * 1000)
    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        {"ts": now_ms, "symbol": symbol, "features": {"price": "100.0"}},
        why="test",
    )

    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "stratX", "symbol": symbol, "side": "BUY", "rid": "rid-1", "ts_ms": now_ms, "why_chain": ["test"], "readiness": {"warmup_ok": True}},
        why="test",
    )

    assert deferred, "Expected EVT:INTENT_DEFERRED from degraded-context gate"

    # Gate uses NRR SSOT code.
    reason = str(deferred[0].get("reason") or "")
    assert NormalizedRejectReasons.normalize(reason) == NormalizedRejectReasons.DATA_NOT_READY

    # Ensure details carry missing critical info.
    original_event = deferred[0].get("original_event") or {}
    payload_min = original_event.get("payload_min") or {}
    missing_critical = payload_min.get("missing_critical") or {}
    assert "ema_bias" in missing_critical
