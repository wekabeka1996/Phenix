from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.shadow_telemetry.main_bridge import (
    LLMIntentIngressBridge,
    register_llm_command_mapper,
)


class _StubEvent:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.pld = payload


class _StubFSM:
    def __init__(self) -> None:
        self.listeners: Dict[str, List[Any]] = {}
        self.emitted: List[Dict[str, Any]] = []

    def listen(self, event_name: str, handler: Any) -> None:
        self.listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        payload = kwargs.get("payload")
        why = kwargs.get("why")
        if payload is None and len(args) >= 1:
            payload = args[0]
        if why is None and len(args) >= 2:
            why = args[1]
        payload = payload if isinstance(payload, dict) else {}
        why = str(why or "")
        self.emitted.append({"event": event_name, "payload": payload, "why": why})
        for handler in self.listeners.get(event_name, []):
            handler(_StubEvent(payload))


def _cfg(mode: str) -> Any:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    cfg.trading.llm_orchestration.mode = mode
    cfg.trading.llm_orchestration.symbols_llm = ["BNBUSDT"]
    cfg.trading.llm_orchestration.allowlist_symbols = ["BNBUSDT"]
    cfg.domains.shadow_telemetry.enabled = True
    cfg.domains.shadow_telemetry.api.enabled = True
    cfg.domains.shadow_telemetry.api.write.enabled = True
    return cfg


def _cmd_payload(symbol: str = "BNBUSDT") -> Dict[str, Any]:
    ts_ms = int(time.time() * 1000)
    return {
        "request_id": "req-bridge-test",
        "intent_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "ts_ms": ts_ms,
        "symbol": symbol,
        "side": "BUY",
        "order": {"type": "LIMIT", "limit_price": "600.0", "qty": "0.1", "time_in_force": "GTC"},
        "brackets": {"tp_price": "602.4", "sl_price": "598.5"},
        "snapshot_ref": {"snapshot_id": "snap-1", "inputs_digest": "a" * 64},
        "model_meta": {"model": "pytest", "temperature": 0.0, "prompt_hash": "b" * 32},
        "why_short": "bridge_test",
        "idempotency_key": "idem-bridge-1",
    }


def test_bridge_rejects_in_baseline_mode() -> None:
    fsm = _StubFSM()
    bridge = LLMIntentIngressBridge(fsm=fsm, config=_cfg("baseline"))
    bridge._on_command(_cmd_payload())

    rejected = [e for e in fsm.emitted if e["event"] == "EVT:LLM_INTENT_REJECTED_V1"]
    submitted = [e for e in fsm.emitted if e["event"] == "CMD:LLM_INTENT_SUBMIT_V1"]
    assert rejected, "expected LLM intent reject in baseline mode"
    assert rejected[0]["payload"]["reason_code"] == "LLM_MODE_DISABLED"
    assert not submitted


def test_bridge_maps_to_strategy_signal_for_owned_symbol() -> None:
    fsm = _StubFSM()
    register_llm_command_mapper(fsm=fsm)
    bridge = LLMIntentIngressBridge(fsm=fsm, config=_cfg("hybrid_advisory"))
    bridge._on_command(_cmd_payload(symbol="BNBUSDT"))

    accepted = [e for e in fsm.emitted if e["event"] == "EVT:LLM_INTENT_ACCEPTED_V1"]
    submitted = [e for e in fsm.emitted if e["event"] == "CMD:LLM_INTENT_SUBMIT_V1"]
    mapped = [e for e in fsm.emitted if e["event"] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert accepted
    assert submitted
    assert mapped
    assert mapped[-1]["payload"]["strategy_id"] == "llm_microstructure"
    assert mapped[-1]["payload"]["rid"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
