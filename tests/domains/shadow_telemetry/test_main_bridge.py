import shutil
from pathlib import Path
from typing import Any, Dict

import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.shadow_telemetry.ipc import (
    JsonlTcpQueueClient,
    JsonlTcpServer,
)
from apps.reference.domains.shadow_telemetry.main_bridge import (
    LLMIntentIngressBridge,
    register_llm_command_mapper,
)
from apps.reference.telemetry.metrics import generate_latest


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
        event_payload = payload if payload is not None else kwargs.get("payload") or {
        }
        self.emitted.append(
            {"event": event_name, "payload": event_payload, "why": why})
        for handler in self.listeners.get(event_name, []):
            handler(_StubEvent(event_payload))


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(f'{key}="{value}"' in line for key, value in labels.items()):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        return float(line.rsplit(" ", 1)[1])
    return 0.0


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
            "allowlist_events": ["EVT:FEATURES_CALCULATED", "EVT:TICK_FEATURES_CALCULATED"],
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
        "ledger": {
            "queue_maxsize": 100,
            "overflow_policy": "fail_closed",
            "enqueue_timeout_ms": 5,
            "shutdown_timeout_ms": 2000,
        },
        "lifecycle": {
            "stop_timeout_ms": 2000,
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
    strategies_data = yaml.safe_load(
        strategies_path.read_text(encoding="utf-8"))
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


def _eze_open_payload(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    payload = _llm_cmd_payload()
    payload["symbol"] = symbol
    payload["request_kind"] = "eze_open"
    return payload


def _llm_close_payload() -> Dict[str, Any]:
    return {
        "request_kind": "close_position",
        "request_id": "req-close-1",
        "action_id": "close-1",
        "ts_ms": 1_700_000_000_100,
        "lifecycle_id": "life-1",
        "symbol": "BNBUSDT",
        "reason": "guardian close",
        "qty": "0.5",
        "idempotency_key": "idem-close-1234",
    }


def _llm_bracket_amend_payload() -> Dict[str, Any]:
    return {
        "request_kind": "amend_brackets",
        "request_id": "req-amend-1",
        "action_id": "amend-1",
        "ts_ms": 1_700_000_000_200,
        "lifecycle_id": "life-1",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "entry_price": "100.0",
        "brackets": {
            "tp_price": "101.5",
            "sl_price": "99.2",
        },
        "reason": "guardian amend",
        "idempotency_key": "idem-amend-1234",
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


def test_llm_ingress_bridge_maps_owned_symbol_to_external_open_request(tmp_path: Path) -> None:
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
    assert "CMD:EXTERNAL_OPEN_REQUEST_V1" in event_names
    assert "CMD:OPEN" not in event_names
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in event_names

    ext_event = next(
        event for event in fsm.emitted if event["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
    payload = ext_event["payload"]
    assert payload["source"] == "external_llm"
    assert payload["intent_id"] == "intent-1"
    assert payload["symbol"] == "BNBUSDT"
    assert payload["side"] == "BUY"
    assert payload["qty"] == "0.5"
    assert payload["price"] == "100.0"
    assert payload["order_type"] == "LIMIT"
    assert payload["tif"] == "GTC"
    assert payload["rid"] == "intent-1"
    assert payload["stop_price"] == "99.0"
    assert payload["target_price"] == "101.0"


def test_llm_ingress_bridge_eze_open_bypasses_runtime_symbol_gate(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _configure_shadow_llm(cfg_dir, mode="hybrid_advisory")
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    fsm = _StubFSM()
    register_llm_command_mapper(fsm)
    bridge = LLMIntentIngressBridge(fsm=fsm, config=config)

    bridge._on_command(_eze_open_payload(symbol="BTCUSDT"))

    event_names = [event["event"] for event in fsm.emitted]
    assert "EVT:LLM_INTENT_ACCEPTED_V1" in event_names
    assert "CMD:EXTERNAL_OPEN_REQUEST_V1" in event_names
    assert "EVT:LLM_INTENT_REJECTED_V1" not in event_names

    accepted = next(event for event in fsm.emitted if event["event"] == "EVT:LLM_INTENT_ACCEPTED_V1")
    assert accepted["payload"]["ingress_mode"] == "eze_direct"
    ext_event = next(event for event in fsm.emitted if event["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
    assert ext_event["payload"]["symbol"] == "BTCUSDT"


def test_llm_direct_external_open_carries_idempotency_key(tmp_path: Path) -> None:
    fsm = _StubFSM()
    register_llm_command_mapper(fsm)

    # Mock the internal SUBMIT emit
    fsm.emit(
        "CMD:LLM_INTENT_SUBMIT_V1",
        payload=_llm_cmd_payload()
    )

    ext_event = next(
        event for event in fsm.emitted if event["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
    assert ext_event["payload"]["idempotent_key"] == "idem-key-1234"


def test_llm_ingress_bridge_maps_close_request_to_external_close_request(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _configure_shadow_llm(cfg_dir, mode="hybrid_advisory")
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    fsm = _StubFSM()
    register_llm_command_mapper(fsm)
    bridge = LLMIntentIngressBridge(fsm=fsm, config=config)

    bridge._on_command(_llm_close_payload())

    event_names = [event["event"] for event in fsm.emitted]
    assert "EVT:LLM_CLOSE_ACCEPTED_V1" in event_names
    assert "CMD:LLM_POSITION_CLOSE_V1" in event_names
    assert "CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1" in event_names

    ext_event = next(
        event for event in fsm.emitted if event["event"] == "CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1"
    )
    payload = ext_event["payload"]
    assert payload["action_id"] == "close-1"
    assert payload["lifecycle_id"] == "life-1"
    assert payload["symbol"] == "BNBUSDT"
    assert payload["source"] == "external_llm"
    assert payload["idempotent_key"] == "idem-close-1234"


def test_llm_ingress_bridge_maps_amend_request_to_external_bracket_amend_request(tmp_path: Path) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    _configure_shadow_llm(cfg_dir, mode="hybrid_advisory")
    config = ConfigLoader(config_dir=cfg_dir).load_config()
    fsm = _StubFSM()
    register_llm_command_mapper(fsm)
    bridge = LLMIntentIngressBridge(fsm=fsm, config=config)

    bridge._on_command(_llm_bracket_amend_payload())

    event_names = [event["event"] for event in fsm.emitted]
    assert "EVT:LLM_BRACKET_AMEND_ACCEPTED_V1" in event_names
    assert "CMD:LLM_BRACKET_AMEND_V1" in event_names
    assert "CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1" in event_names

    ext_event = next(
        event for event in fsm.emitted if event["event"] == "CMD:EXTERNAL_BRACKET_AMEND_REQUEST_V1"
    )
    payload = ext_event["payload"]
    assert payload["action_id"] == "amend-1"
    assert payload["lifecycle_id"] == "life-1"
    assert payload["symbol"] == "BNBUSDT"
    assert payload["side"] == "BUY"
    assert payload["tp_price"] == "101.5"
    assert payload["sl_price"] == "99.2"
    assert payload["source"] == "external_llm"


def test_queue_client_stop_accounts_for_undrained_payloads() -> None:
    reset_failure_outcomes()
    metric_before = _metric_value(
        "neocortex_async_forced_stop_total",
        component="shadow_bridge_test_client",
        reason_code="UNCLEAN_SHUTDOWN",
    )
    client = JsonlTcpQueueClient(
        endpoint="tcp://127.0.0.1:7999",
        queue_maxsize=2,
        overflow_policy="fail_closed",
        stop_timeout_ms=1,
        name="shadow_bridge_test_client",
    )

    assert client.enqueue({"event": "shadow"}) is True

    client.stop()

    assert client.enqueue({"event": "after-stop"}) is False
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN,
    ) == 1
    assert _metric_value(
        "neocortex_async_forced_stop_total",
        component="shadow_bridge_test_client",
        reason_code="UNCLEAN_SHUTDOWN",
    ) == metric_before + 1.0


def test_server_stop_accounts_for_owned_threads_that_survive() -> None:
    class _AliveThread:
        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

    reset_failure_outcomes()
    metric_before = _metric_value(
        "neocortex_async_forced_stop_total",
        component="shadow_bridge_test_server",
        reason_code="UNCLEAN_SHUTDOWN",
    )
    server = JsonlTcpServer(
        endpoint="tcp://127.0.0.1:7998",
        handler=lambda payload: None,
        stop_timeout_ms=1,
        name="shadow_bridge_test_server",
    )
    server._thread = _AliveThread()  # type: ignore[assignment]
    with server._state_lock:
        server._handler_threads.add(_AliveThread())

    server.stop()

    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.UNCLEAN_SHUTDOWN,
    ) == 1
    assert _metric_value(
        "neocortex_async_forced_stop_total",
        component="shadow_bridge_test_server",
        reason_code="UNCLEAN_SHUTDOWN",
    ) == metric_before + 1.0


def test_active_runtime_shutdown_stages_keep_shadow_ordering() -> None:
    source = Path("apps/reference/main.py").read_text(encoding="utf-8")

    tap_index = source.index('ShutdownStage("shadow_event_tap"')
    sink_index = source.index('ShutdownStage("shadow_telemetry_sink"')
    ingress_index = source.index('ShutdownStage("llm_ingress_bridge"')

    assert tap_index < sink_index < ingress_index
