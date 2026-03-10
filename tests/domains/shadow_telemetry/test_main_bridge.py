import shutil
from pathlib import Path
from typing import Any, Dict

import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.shadow_telemetry.main_bridge import (
    LLMIntentIngressBridge,
    register_llm_command_mapper,
)


class _StubEvent:
    def __init__(self, payload: Dict[str, Any]):
        self.pld = payload


class _StubFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.emitted: list[dict[str, Any]] = []

    def listen(self, event_name: str, handler) -> None:
        self.listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: Dict[str, Any] | None = None, why: str = "", **kwargs) -> None:
        event_payload = payload if payload is not None else kwargs.get("payload") or {}
        self.emitted.append({"event": event_name, "payload": event_payload, "why": why})
        for handler in self.listeners.get(event_name, []):
            handler(_StubEvent(event_payload))


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _configure_shadow_llm(cfg_dir: Path, *, mode: str) -> None:
    trading_path = cfg_dir / "trading.yaml"
    trading_data = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    trading_block = trading_data.setdefault("trading", {})
    trading_block["llm_orchestration"] = {
        "mode": mode,
        "llm_role": "advisory",
        "require_telemetry": False,
        "symbols_llm": ["BNBUSDT"],
        "allowlist_symbols": ["BNBUSDT"],
        "intent_policy": {
            "max_open_intents": 3,
            "cooldown_sec": 0,
            "allow_limit_only": True,
            "require_tp_sl": True,
            "max_notional_usd": 100.0,
            "max_qty": 2.0,
            "max_price_deviation_bps": 20.0,
            "allowed_tif": ["GTC"],
        },
    }
    _write_yaml(trading_path, trading_data)

    domains_path = cfg_dir / "domains.yaml"
    domains_data = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    domains_data["shadow_telemetry"] = {
        "enabled": True,
        "required_for_mode": False,
        "ingest": {
            "source": "ipc_tap",
            "ipc_endpoint": "tcp://127.0.0.1:7101",
            "allowlist_events": ["EVT:FEATURES_CALCULATED"],
            "queue_maxsize": 100,
            "overflow_policy": "fail_closed",
        },
        "api": {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 8443,
            "tls": False,
            "auth_mode": "bearer",
            "write": {
                "enabled": True,
                "intents_endpoint": "/intents/llm/v1",
                "rate_limit_per_min": 30,
                "max_body_kb": 64,
                "symbol_allowlist": ["BNBUSDT"],
                "require_snapshot_ref": True,
                "idempotency_ttl_sec": 300,
                "consequential": True,
            },
        },
        "egress_to_main": {
            "mode": "ipc",
            "ipc_commands_endpoint": "tcp://127.0.0.1:7102",
            "queue_maxsize": 100,
            "overflow_policy": "fail_closed",
        },
        "snapshot": {
            "trigger_event": "EVT:FEATURES_CALCULATED",
            "tf_policy": {
                "bar_snapshots_enabled": True,
                "tick_snapshots_mode": "sampled",
                "tick_sample_every_n": 20,
                "min_tf_sec_for_full": 60,
            },
            "output_dir": "data/shadow_telemetry/snapshots",
        },
    }
    _write_yaml(domains_path, domains_data)

    strategies_path = cfg_dir / "strategies.yaml"
    strategies_data = yaml.safe_load(strategies_path.read_text(encoding="utf-8"))
    strategies_data["assignments"]["BNBUSDT"] = ["llm_microstructure"]
    _write_yaml(strategies_path, strategies_data)


def _llm_cmd_payload() -> Dict[str, Any]:
    return {
        "request_id": "req-1",
        "intent_id": "intent-1",
        "ts_ms": 1_700_000_000_000,
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order": {
            "type": "LIMIT",
            "limit_price": "100.0",
            "qty": "0.5",
            "time_in_force": "GTC",
        },
        "brackets": {
            "tp_price": "101.0",
            "sl_price": "99.0",
        },
        "snapshot_ref": {
            "snapshot_id": "snap-1",
            "inputs_digest": "digest1234",
        },
        "why_short": "llm_test_signal",
        "idempotency_key": "idem-key-1234",
    }


def test_llm_ingress_bridge_rejects_baseline_mode(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _configure_shadow_llm(cfg_dir, mode="baseline")
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    fsm = _StubFSM()
    bridge = LLMIntentIngressBridge(fsm=fsm, config=config)

    bridge._on_command(_llm_cmd_payload())

    assert fsm.emitted[0]["event"] == "EVT:LLM_INTENT_REJECTED_V1"
    assert fsm.emitted[0]["payload"]["reason_code"] == "LLM_MODE_DISABLED"


def test_llm_ingress_bridge_maps_owned_symbol_to_strategy_signal(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _configure_shadow_llm(cfg_dir, mode="hybrid_advisory")
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    fsm = _StubFSM()
    register_llm_command_mapper(fsm)
    bridge = LLMIntentIngressBridge(fsm=fsm, config=config)

    bridge._on_command(_llm_cmd_payload())

    event_names = [event["event"] for event in fsm.emitted]
    assert "EVT:LLM_INTENT_ACCEPTED_V1" in event_names
    assert "CMD:LLM_INTENT_SUBMIT_V1" in event_names
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in event_names

    strategy_event = next(event for event in fsm.emitted if event["event"] == "EVT:STRATEGY_SIGNAL_PRODUCED")
    assert strategy_event["payload"]["strategy_id"] == "llm_microstructure"
    assert strategy_event["payload"]["symbol"] == "BNBUSDT"
    assert strategy_event["payload"]["price_ctx"]["entry_price"] == "100.0"
