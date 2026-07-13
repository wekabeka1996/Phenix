from __future__ import annotations

import socket
import json
import multiprocessing
import os
import shutil
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import yaml
from fastapi.testclient import TestClient

from apps.reference.domains.shadow_telemetry.authority_query import (
    AuthorityQueryRequest,
    MainProcessAuthorityQueryClient,
    RuntimeAuthorityQueryService,
)
from apps.reference.domains.shadow_telemetry.ipc import (
    JsonlTcpRequestError,
    JsonlTcpRequestReplyClient,
    JsonlTcpServer,
)
from apps.reference.domains.shadow_telemetry.main import create_shadow_telemetry_app
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.shadow_telemetry.read_model_contract import (
    ContextSourceSnapshot,
    LifecycleSourceSnapshot,
)
from apps.reference.domains.shadow_telemetry.read_model_service import PhenixReadModelService
from tests.domains.shadow_telemetry.test_p46_2d_proposal_dry_run import (
    NOW,
    fixture as dry_run_fixture,
    proposal,
)
from tests.domains.shadow_telemetry.test_p46_2c_read_model import NoopClient, NoopServer


def _free_endpoint() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"tcp://127.0.0.1:{sock.getsockname()[1]}"


def _service() -> tuple[object, RuntimeAuthorityQueryService]:
    config, clock, authority, dry_run, _ = dry_run_fixture()

    def context_reader(session_id: str) -> ContextSourceSnapshot:
        assert session_id == "phenix-p46-2d"
        return ContextSourceSnapshot(
            manifest_version="manifest-v9",
            content_hash="sha256:context-v9",
            instruction_version="instructions-v7",
            created_at=NOW,
            stale_after=NOW + timedelta(minutes=5),
            source_references=("memory://manifest/9",),
        )

    def lifecycle_reader(session_id: str) -> LifecycleSourceSnapshot:
        assert session_id == "phenix-p46-2d"
        return LifecycleSourceSnapshot(
            reconciliation_state="IN_SYNC",
            reconciliation_divergence=False,
            last_reconciled_at=NOW,
            source_kind="EXEC_POS_FSM_RECONCILIATION",
            source_references=("fsm://reconciliation/current",),
        )

    read_model = PhenixReadModelService(
        authority=authority,
        context_reader=context_reader,
        lifecycle_reader=lifecycle_reader,
        policy=config.domains.shadow_telemetry.api.read_model,
        clock=clock,
    )
    policy = config.domains.shadow_telemetry.authority_query_bridge
    service = RuntimeAuthorityQueryService(
        read_model=read_model,
        dry_run=dry_run,
        runtime_id=config.domains.shadow_telemetry.api.read_model.runtime_id,
        environment=config.domains.shadow_telemetry.api.read_model.environment,
        runtime_generation="generation-test-1",
        supported_kinds=policy.supported_query_kinds,
        max_idempotency_entries=policy.max_idempotency_entries,
        clock=clock,
    )
    return config, service


def _main_query_process(endpoint: str, ready, stop) -> None:
    _, service = _service()
    server = JsonlTcpServer(endpoint, service.handle, stop_timeout_ms=1000)
    server.start()
    ready.set()
    stop.wait(15)
    server.stop()


def _fastapi_edge_process(config_dir: str, query_endpoint: str, http_port: int, ready, stop) -> None:
    import uvicorn

    os.environ["SHADOW_TELEMETRY_BEARER_TOKEN"] = "p46-s1-multiprocess-token"
    config = ConfigLoader(config_dir=Path(config_dir)).load_config()
    query_policy = config.domains.shadow_telemetry.authority_query_bridge
    client = MainProcessAuthorityQueryClient(
        JsonlTcpRequestReplyClient(
            query_endpoint,
            timeout_ms=query_policy.timeout_ms,
            max_payload_kb=query_policy.max_payload_kb,
        ),
        runtime_id=config.domains.shadow_telemetry.api.read_model.runtime_id,
        environment=config.domains.shadow_telemetry.api.read_model.environment,
        timeout_ms=query_policy.timeout_ms,
        clock=lambda: NOW,
    )
    app = create_shadow_telemetry_app(config, authority_query_client=client)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=http_port, log_level="error", access_log=False
    ))

    def monitor() -> None:
        stop.wait(15)
        server.should_exit = True

    threading.Thread(target=monitor, daemon=True).start()
    ready.set()
    server.run()
    os.environ.pop("SHADOW_TELEMETRY_BEARER_TOKEN", None)


def _request(kind: str, *, request_id: str = "request-0001", payload=None) -> dict:
    return AuthorityQueryRequest(
        schema_version="p46.authority-query.v1",
        request_kind=kind,
        request_id=request_id,
        correlation_id="correlation-0001",
        session_id="phenix-p46-2d",
        deadline=NOW + timedelta(seconds=2),
        requested_at=NOW,
        caller_runtime_id="phenix-main",
        expected_environment="binance_futures_testnet",
        payload=payload,
    ).model_dump(mode="json")


def test_real_tcp_round_trip_handshake_read_and_dry_run_has_no_execution_effects() -> None:
    config, service = _service()
    endpoint = _free_endpoint()
    server = JsonlTcpServer(endpoint, service.handle, stop_timeout_ms=1000)
    server.start()
    time.sleep(0.05)
    transport = JsonlTcpRequestReplyClient(endpoint, timeout_ms=1000, max_payload_kb=128)
    client = MainProcessAuthorityQueryClient(
        transport,
        runtime_id=config.domains.shadow_telemetry.api.read_model.runtime_id,
        environment=config.domains.shadow_telemetry.api.read_model.environment,
        timeout_ms=1000,
        clock=service.clock,
    )
    try:
        compatibility = client.handshake()
        assert compatibility["read_model_available"] is True
        assert client.read_model("phenix-p46-2d")["context"]["manifest_version"] == "manifest-v9"
        result = client.dry_run("phenix-p46-2d", proposal().model_dump(mode="json"))
        assert result["decision"] == "ACCEPTED"
        assert result["derived_quantity"] is not None
        assert result["side_effects"] == {
            "session_mutations": 0,
            "lease_mutations": 0,
            "exposure_reservations": 0,
            "command_emissions": 0,
            "fsm_calls": 0,
            "adapter_calls": 0,
            "exchange_calls": 0,
        }
        assert service.dry_run_handler_calls == 1
    finally:
        server.stop()


def test_query_idempotency_conflict_schema_and_unknown_kind_fail_closed() -> None:
    _, service = _service()
    raw = _request("QUERY:READ_MODEL_SESSION_V1")
    first = service.handle(raw)
    assert service.handle(raw) == first
    assert service.handler_calls == 1
    conflicting = dict(raw, session_id="another-session")
    assert service.handle(conflicting)["status"] == "CONFLICT"
    assert service.handle(dict(raw, schema_version="unsupported"))["error_code"] == "QUERY_SCHEMA_INVALID"
    assert service.handle(dict(raw, request_kind="QUERY:UNKNOWN"))["error_code"] == "QUERY_SCHEMA_INVALID"


def test_transport_rejects_disconnect_timeout_oversize_and_invalid_reply() -> None:
    dead = JsonlTcpRequestReplyClient(_free_endpoint(), timeout_ms=50, max_payload_kb=1)
    with pytest.raises(JsonlTcpRequestError, match="IPC_QUERY_(?:UNAVAILABLE|TIMEOUT)"):
        dead.request({"request": "small"})
    with pytest.raises(JsonlTcpRequestError, match="IPC_PAYLOAD_TOO_LARGE"):
        dead.request({"request": "x" * 2048})

    endpoint = _free_endpoint()
    slow = JsonlTcpServer(endpoint, lambda _: (time.sleep(0.2), {"ok": True})[1], stop_timeout_ms=1000)
    slow.start()
    time.sleep(0.05)
    with pytest.raises(JsonlTcpRequestError, match="IPC_QUERY_TIMEOUT"):
        JsonlTcpRequestReplyClient(endpoint, timeout_ms=20, max_payload_kb=1).request({"request": "small"})
    slow.stop()

    endpoint = _free_endpoint()
    invalid = JsonlTcpServer(endpoint, lambda _: ["not", "a", "mapping"], stop_timeout_ms=1000)  # type: ignore[arg-type,return-value]
    invalid.start()
    time.sleep(0.05)
    with pytest.raises(JsonlTcpRequestError, match="IPC_REPLY_INVALID"):
        JsonlTcpRequestReplyClient(endpoint, timeout_ms=1000, max_payload_kb=1).request({"request": "small"})
    invalid.stop()


def test_client_rejects_wrong_correlation_runtime_environment_and_generation() -> None:
    config, service = _service()

    class RewritingTransport:
        def __init__(self, field: str, value: str) -> None:
            self.field = field
            self.value = value

        def request(self, payload: dict) -> dict:
            reply = service.handle(payload)
            reply[self.field] = self.value
            return reply

    args = {
        "runtime_id": config.domains.shadow_telemetry.api.read_model.runtime_id,
        "environment": config.domains.shadow_telemetry.api.read_model.environment,
        "timeout_ms": 1000,
        "clock": service.clock,
    }
    for field, value, reason in (
        ("correlation_id", "wrong-correlation", "IPC_CORRELATION_MISMATCH"),
        ("source_runtime_id", "wrong-runtime", "IPC_COMPATIBILITY_MISMATCH"),
        ("environment", "wrong-environment", "IPC_REPLY_INVALID"),
    ):
        client = MainProcessAuthorityQueryClient(RewritingTransport(field, value), **args)  # type: ignore[arg-type]
        with pytest.raises(JsonlTcpRequestError, match=reason):
            client.handshake()

    client = MainProcessAuthorityQueryClient(RewritingTransport("runtime_generation", "generation-test-1"), **args)  # type: ignore[arg-type]
    client.handshake()
    client.transport = RewritingTransport("runtime_generation", "generation-test-2")  # type: ignore[assignment]
    with pytest.raises(JsonlTcpRequestError, match="IPC_RUNTIME_GENERATION_CHANGED"):
        client.read_model("phenix-p46-2d")


def test_fastapi_edge_uses_ipc_client_without_local_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    config, service = _service()
    endpoint = _free_endpoint()
    server = JsonlTcpServer(endpoint, service.handle, stop_timeout_ms=1000)
    server.start()
    time.sleep(0.05)
    query_client = MainProcessAuthorityQueryClient(
        JsonlTcpRequestReplyClient(endpoint, timeout_ms=1000, max_payload_kb=128),
        runtime_id=config.domains.shadow_telemetry.api.read_model.runtime_id,
        environment=config.domains.shadow_telemetry.api.read_model.environment,
        timeout_ms=1000,
        clock=service.clock,
    )
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "p46-s1-token")
    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpServer", NoopServer)
    monkeypatch.setattr("apps.reference.domains.shadow_telemetry.main.JsonlTcpQueueClient", NoopClient)
    app = create_shadow_telemetry_app(config, authority_query_client=query_client)
    assert app.state.read_model_service is None
    assert app.state.proposal_dry_run_service is None
    headers = {"Authorization": "Bearer p46-s1-token"}
    try:
        with TestClient(app) as http:
            assert http.get("/read-model/v1/sessions/phenix-p46-2d", headers=headers).status_code == 200
            response = http.post(
                "/proposal-dry-run/v1/sessions/phenix-p46-2d",
                headers=headers,
                json=proposal().model_dump(mode="json"),
            )
            assert response.status_code == 200
            assert response.json()["decision"] == "ACCEPTED"
    finally:
        server.stop()


@pytest.mark.skipif(os.name != "nt", reason="P46-2D-S1 requires Windows spawn proof")
def test_windows_spawn_main_and_fastapi_processes_query_current_authority(tmp_path: Path) -> None:
    query_endpoint = _free_endpoint()
    ingest_endpoint = _free_endpoint()
    http_port = int(_free_endpoint().rsplit(":", 1)[1])
    config_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), config_dir)
    domains_path = config_dir / "domains.yaml"
    domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
    shadow = domains["shadow_telemetry"]
    shadow["ingest"]["ipc_endpoint"] = ingest_endpoint
    shadow["egress_to_main"]["ipc_commands_endpoint"] = query_endpoint
    shadow["authority_query_bridge"]["ipc_endpoint"] = query_endpoint
    shadow["api"]["auth_mode"] = "bearer"
    shadow["snapshot"]["output_dir"] = str(tmp_path / "snapshots")
    domains_path.write_text(yaml.safe_dump(domains, sort_keys=False), encoding="utf-8")

    context = multiprocessing.get_context("spawn")
    main_ready, main_stop = context.Event(), context.Event()
    edge_ready, edge_stop = context.Event(), context.Event()
    main_process = context.Process(
        target=_main_query_process,
        args=(query_endpoint, main_ready, main_stop),
        name="p46-main-authority",
    )
    edge_process = context.Process(
        target=_fastapi_edge_process,
        args=(str(config_dir), query_endpoint, http_port, edge_ready, edge_stop),
        name="p46-fastapi-edge",
    )
    main_process.start()
    assert main_ready.wait(10)
    edge_process.start()
    assert edge_ready.wait(10)
    assert main_process.pid != edge_process.pid != os.getpid()
    headers = {"Authorization": "Bearer p46-s1-multiprocess-token"}
    base = f"http://127.0.0.1:{http_port}"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(Request(f"{base}/read-model/v1/health", headers=headers), timeout=1) as response:
                    assert response.status == 200
                break
            except (OSError, HTTPError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

        with urlopen(Request(
            f"{base}/read-model/v1/sessions/phenix-p46-2d", headers=headers
        ), timeout=3) as response:
            read_model = json.loads(response.read())
        assert read_model["context"]["manifest_version"] == "manifest-v9"

        body = json.dumps(proposal().model_dump(mode="json")).encode("utf-8")
        with urlopen(Request(
            f"{base}/proposal-dry-run/v1/sessions/phenix-p46-2d",
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        ), timeout=3) as response:
            result = json.loads(response.read())
        assert result["decision"] == "ACCEPTED"
        assert result["side_effects"]["command_emissions"] == 0
        assert result["side_effects"]["fsm_calls"] == 0
        assert result["side_effects"]["adapter_calls"] == 0
        assert result["side_effects"]["exchange_calls"] == 0
    finally:
        edge_stop.set()
        main_stop.set()
        edge_process.join(10)
        main_process.join(10)
        if edge_process.is_alive():
            edge_process.terminate()
        if main_process.is_alive():
            main_process.terminate()
    assert edge_process.exitcode == 0
    assert main_process.exitcode == 0
