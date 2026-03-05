from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator

from fastapi.testclient import TestClient

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.shadow_telemetry.main import create_shadow_telemetry_app


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


@contextmanager
def _dummy_tcp_listener(port: int) -> Iterator[None]:
    stop_evt = threading.Event()

    def _run() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", int(port)))
        srv.listen(8)
        srv.settimeout(0.2)
        try:
            while not stop_evt.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(0.2)
                    while not stop_evt.is_set():
                        try:
                            buf = conn.recv(4096)
                        except socket.timeout:
                            continue
                        if not buf:
                            break
        finally:
            srv.close()

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    try:
        # Small delay so probe connects reliably.
        time.sleep(0.05)
        yield
    finally:
        stop_evt.set()
        th.join(timeout=1.0)


def _build_test_app() -> Any:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    ingest_port = _free_port()
    cmd_port = _free_port()
    cfg.domains.shadow_telemetry.ingest.ipc_endpoint = f"tcp://127.0.0.1:{ingest_port}"
    cfg.domains.shadow_telemetry.egress_to_main.ipc_commands_endpoint = f"tcp://127.0.0.1:{cmd_port}"

    cfg.domains.shadow_telemetry.enabled = True
    cfg.domains.shadow_telemetry.api.enabled = True
    cfg.domains.shadow_telemetry.api.write.enabled = True
    cfg.domains.shadow_telemetry.api.write.symbol_allowlist = ["BNBUSDT"]
    cfg.domains.shadow_telemetry.api.write.require_snapshot_ref = True

    cfg.trading.llm_orchestration.require_telemetry = True
    cfg.trading.llm_orchestration.symbols_llm = ["BNBUSDT"]
    cfg.trading.llm_orchestration.allowlist_symbols = ["BNBUSDT"]
    cfg.trading.llm_orchestration.intent_policy.max_notional_usd = 100.0
    cfg.trading.llm_orchestration.intent_policy.max_qty = 2.0
    cfg.trading.llm_orchestration.intent_policy.max_price_deviation_bps = 20.0
    cfg.trading.llm_orchestration.intent_policy.allowed_tif = ["GTC"]

    return create_shadow_telemetry_app(cfg), cmd_port


def _seed_snapshot(client: TestClient, app: Any, symbol: str = "BNBUSDT") -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)
    app.state.snapshot_store.ingest_event(
        {
            "frame_id": "seed-stage-a",
            "captured_ts_ms": now_ms,
            "event_name": "EVT:FEATURES_CALCULATED",
            "payload": {
                "symbol": symbol,
                "ts_ms": now_ms,
                "tf_sec": 60,
                "bar": {"open": "600", "high": "605", "low": "598", "close": "600", "volume": "1.0"},
                "features": {"price": "600"},
                "warmup": {"ready": True},
            },
            "why": "seed",
        }
    )
    resp = client.get("/snapshots/latest", params={"symbol": symbol})
    assert resp.status_code == 200
    return resp.json()


def _base_payload(snapshot_id: str, *, intent_id: str, idempotency_key: str) -> Dict[str, Any]:
    return {
        "intent_id": intent_id,
        "ts_ms": int(time.time() * 1000),
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order": {"type": "LIMIT", "limit_price": "600.00", "qty": "0.10", "time_in_force": "GTC"},
        "brackets": {"tp_price": "602.40", "sl_price": "598.50"},
        "snapshot_ref": {"snapshot_id": snapshot_id, "inputs_digest": "a" * 64},
        "model_meta": {"model": "pytest", "temperature": 0.0, "prompt_hash": "b" * 32},
        "why_short": "stage_a_ingress_test",
        "idempotency_key": idempotency_key,
    }


def test_ingress_accepts_and_replays_idempotent(monkeypatch: Any) -> None:
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "test-token")
    app, cmd_port = _build_test_app()
    headers = {"Authorization": "Bearer test-token"}

    with _dummy_tcp_listener(cmd_port):
        with TestClient(app) as client:
            h = client.get("/health")
            assert h.status_code == 200
            hb = h.json()
            assert hb.get("status") == "healthy"
            assert "queue_depth" in hb

            snapshot = _seed_snapshot(client, app)
            payload = _base_payload(
                snapshot_id=str(snapshot["snapshot_id"]),
                intent_id="11111111-1111-1111-1111-111111111111",
                idempotency_key="idem-stage-a-001",
            )

            r1 = client.post("/intents/llm/v1", json=payload, headers=headers)
            assert r1.status_code == 202
            body = r1.json()
            assert body["intent_id"] == payload["intent_id"]
            assert body["state"] == "queued"

            r2 = client.post("/intents/llm/v1", json=payload, headers=headers)
            assert r2.status_code == 202
            assert r2.json()["intent_id"] == payload["intent_id"]


def test_ingress_rejects_symbol_not_owned_and_tif_policy(monkeypatch: Any) -> None:
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "test-token")
    app, cmd_port = _build_test_app()
    headers = {"Authorization": "Bearer test-token"}

    with _dummy_tcp_listener(cmd_port):
        with TestClient(app) as client:
            snapshot = _seed_snapshot(client, app)
            bad_symbol = _base_payload(
                snapshot_id=str(snapshot["snapshot_id"]),
                intent_id="22222222-2222-2222-2222-222222222222",
                idempotency_key="idem-stage-a-002",
            )
            bad_symbol["symbol"] = "BTCUSDT"
            r1 = client.post("/intents/llm/v1", json=bad_symbol, headers=headers)
            assert r1.status_code == 400
            assert r1.json()["detail"]["reason_code"] == "SYMBOL_NOT_OWNED_BY_LLM"

            bad_tif = _base_payload(
                snapshot_id=str(snapshot["snapshot_id"]),
                intent_id="33333333-3333-3333-3333-333333333333",
                idempotency_key="idem-stage-a-003",
            )
            bad_tif["order"]["time_in_force"] = "IOC"
            r2 = client.post("/intents/llm/v1", json=bad_tif, headers=headers)
            assert r2.status_code == 400
            assert r2.json()["detail"]["reason_code"] == "LIMIT_ONLY_POLICY"

            market_type = _base_payload(
                snapshot_id=str(snapshot["snapshot_id"]),
                intent_id="33333333-3333-3333-3333-333333333334",
                idempotency_key="idem-stage-a-003b",
            )
            market_type["order"]["type"] = "MARKET"
            r3 = client.post("/intents/llm/v1", json=market_type, headers=headers)
            assert r3.status_code == 400
            assert r3.json()["detail"]["reason_code"] == "LIMIT_ONLY_POLICY"


def test_ingress_rejects_price_band_and_qty_cap(monkeypatch: Any) -> None:
    monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "test-token")
    app, cmd_port = _build_test_app()
    headers = {"Authorization": "Bearer test-token"}

    with _dummy_tcp_listener(cmd_port):
        with TestClient(app) as client:
            snapshot = _seed_snapshot(client, app)

            out_of_band = _base_payload(
                snapshot_id=str(snapshot["snapshot_id"]),
                intent_id="44444444-4444-4444-4444-444444444444",
                idempotency_key="idem-stage-a-004",
            )
            out_of_band["order"]["limit_price"] = "700.00"
            out_of_band["brackets"] = {"tp_price": "710.00", "sl_price": "690.00"}
            r1 = client.post("/intents/llm/v1", json=out_of_band, headers=headers)
            assert r1.status_code == 400
            assert r1.json()["detail"]["reason_code"] == "PRICE_OUT_OF_BAND"

            qty_overshoot = _base_payload(
                snapshot_id=str(snapshot["snapshot_id"]),
                intent_id="55555555-5555-5555-5555-555555555555",
                idempotency_key="idem-stage-a-005",
            )
            qty_overshoot["order"]["qty"] = "10"
            r2 = client.post("/intents/llm/v1", json=qty_overshoot, headers=headers)
            assert r2.status_code == 400
            assert r2.json()["detail"]["reason_code"] == "QTY_CAP_EXCEEDED"
