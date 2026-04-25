from __future__ import annotations

import time

from vfoundation.core.fsm_core import FSMCore

from apps.reference.config_models import DegradedContextStrategyContractConfig
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons


def test_degraded_context_gate_can_defer_strategy_signal_per_strategy_override() -> None:
    cfg = ConfigLoader().load_config()

    # Enable gate via canonical domains.decision_making config.
    cfg.domains.decision_making.fail_closed_on_degraded_context = True

    # Strategy-scoped contract is the canonical SSOT; no hidden global fallback applies.
    cfg.domains.decision_making.degraded_context_critical_keys = []
    cfg.domains.decision_making.degraded_context_critical_keys_by_strategy = {}
    cfg.domains.decision_making.degraded_context_contracts_by_strategy = {
        "stratX": DegradedContextStrategyContractConfig(enabled=True, critical_keys=["ema_bias"]),
    }

    fsm = FSMCore()
    deferred: list[dict] = []
    fsm.listen("EVT:INTENT_DEFERRED", lambda msg: deferred.append(msg.pld))

    dm = DecisionMaking(fsm=fsm, config=cfg)

    # Avoid test coupling to optional strategies registry arbitration.
    dm.strategies_registry = None
    dm._cfg.strategies_registry = None
    dm._flip.handle_flip_orchestration = lambda *args, **kwargs: None
    dm._regime_loss_embargo.get_entry_block = lambda *_args, **_kwargs: None

    symbol = "ETHUSDT"

    # Provide risk so the strategy gateway reaches feature-related gates.
    fsm.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {"symbol": symbol, "ts": int(time.time(
        ) * 1000), "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}},
        why="test",
    )

    # Provide features with only price; ema_bias missing => should defer when per-strategy override says ema_bias is critical.
    now_ms = int(time.time() * 1000)
    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        {"ts": now_ms, "symbol": symbol, "tf_sec": 60, "features": {"price": "100.0", "delta_price": "0.0", "obi": "0.0", "tfi": "0.0", "absorption": "0.0"},
         "warmup": {"full_ready": True, "ticks_seen": 10},
         "price_motion": {"ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0},
         "bar": {"symbol": symbol, "timeframe_sec": 60, "start_ts_ms": now_ms, "end_ts_ms": now_ms, "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0.0"},
         "source_mode": "live",
         "diagnostics": {}},
        why="test",
    )

    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "stratX", "symbol": symbol, "side": "BUY", "rid": "rid-1",
            "ts_ms": now_ms, "why_chain": ["test"], "readiness": {"warmup_ok": True}},
        why="test",
    )

    assert deferred, "Expected EVT:INTENT_DEFERRED from degraded-context gate"

    # Gate uses NRR SSOT code.
    reason = str(deferred[0].get("reason") or "")
    assert NormalizedRejectReasons.normalize(
        reason) == NormalizedRejectReasons.DATA_NOT_READY

    # Ensure details carry missing critical info.
    original_event = deferred[0].get("original_event") or {}
    payload_min = original_event.get("payload_min") or {}
    missing_critical = payload_min.get("missing_critical") or {}
    assert "ema_bias" in missing_critical


def test_degraded_context_gate_ignores_global_lists_when_strategy_contract_absent() -> None:
    cfg = ConfigLoader().load_config()
    cfg.domains.decision_making.fail_closed_on_degraded_context = True
    cfg.domains.decision_making.degraded_context_critical_keys = ["ema_bias"]
    cfg.domains.decision_making.degraded_context_critical_keys_by_strategy = {
        "stratY": ["price"],
    }
    cfg.domains.decision_making.degraded_context_contracts_by_strategy = {}

    fsm = FSMCore()
    deferred: list[dict] = []
    fsm.listen("EVT:INTENT_DEFERRED", lambda msg: deferred.append(msg.pld))

    dm = DecisionMaking(fsm=fsm, config=cfg)
    dm.strategies_registry = None
    dm._cfg.strategies_registry = None
    dm._flip.handle_flip_orchestration = lambda *args, **kwargs: None
    dm._regime_loss_embargo.get_entry_block = lambda *_args, **_kwargs: None

    symbol = "ETHUSDT"
    now_ms = int(time.time() * 1000)
    fsm.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {"symbol": symbol, "ts": now_ms, "risk_parameters": {
            "is_trading_allowed": True, "risk_score": 0.0}},
        why="test",
    )
    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        {"ts": now_ms, "symbol": symbol, "tf_sec": 60, "features": {"price": "100.0", "delta_price": "0.0", "obi": "0.0", "tfi": "0.0", "absorption": "0.0"},
         "warmup": {"full_ready": True, "ticks_seen": 10},
         "price_motion": {"ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0},
         "bar": {"symbol": symbol, "timeframe_sec": 60, "start_ts_ms": now_ms, "end_ts_ms": now_ms, "open": "100.0", "high": "100.0", "low": "100.0", "close": "100.0", "volume": "0.0"},
         "source_mode": "live",
         "diagnostics": {}},
        why="test",
    )
    fsm.emit(
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        {"strategy_id": "stratZ", "symbol": symbol, "side": "BUY", "rid": "rid-absent",
            "ts_ms": now_ms, "why_chain": ["test"], "readiness": {"warmup_ok": True}},
        why="test",
    )

    assert deferred == []
