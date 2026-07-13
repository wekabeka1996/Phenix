"""Deterministic production-component harness for the P46-1F runtime proof."""
from __future__ import annotations

import json
import logging
import shutil
import socket
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from fastapi.testclient import TestClient

from apps.reference.config_loader import ConfigLoader
from apps.reference.core.time.clock import MockClock, reset_clock, set_clock
from apps.reference.domains.decision_making.primitives.position_queries import PositionQueries
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentTradeIntentV2Processor,
    PositionQueriesSizingAdapterV2,
)
from apps.reference.domains.shadow_telemetry.main import create_shadow_telemetry_app
from apps.reference.domains.shadow_telemetry.main_bridge import LLMIntentIngressBridge
from apps.reference.domains.shadow_telemetry.trading_session_authority import (
    CanonicalV2AuthorityProvider,
    Participant,
    SymbolLease,
    TradingSession,
    TradingSessionAuthorityStore,
)
from vfoundation.core import FSMCore
from vfoundation.core.schema_registry import init_global_registry


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 12, 14, 0, tzinfo=timezone.utc)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ObservedFSMCore(FSMCore):
    def __init__(self) -> None:
        super().__init__()
        self.emissions: list[tuple[str, dict[str, Any], str]] = []

    def emit(self, event_name, payload=None, why="", data_ref=None, rid=None):
        name = event_name if isinstance(event_name, str) else f"{event_name.op}:{event_name.verb}"
        resolved_payload = payload if payload is not None else getattr(event_name, "pld", {})
        self.emissions.append((name, dict(resolved_payload or {}), why))
        return super().emit(event_name, payload, why, data_ref, rid)


class RecordingExchangeAdapter:
    network_enabled = False
    base_url = "https://testnet.invalid"

    def __init__(self) -> None:
        self.submit_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[dict[str, Any]] = []
        self.amend_calls: list[dict[str, Any]] = []

    async def place_order(self, message):
        self.submit_calls.append(dict(message.pld or {}))
        return {"status": "RECORDED_NOT_SENT"}

    async def cancel_order(self, message):
        self.cancel_calls.append(dict(message.pld or {}))
        return {"status": "RECORDED_NOT_SENT"}


class P46RuntimeHarness:
    def __init__(self, root_dir: Path, monkeypatch) -> None:
        self.root_dir = root_dir.resolve()
        self.monkeypatch = monkeypatch
        self.clock = MockClock(start_ms=int(NOW.timestamp() * 1000))
        set_clock(self.clock)
        self.config = self._load_isolated_config()
        init_global_registry(project_root=str(ROOT))
        self.bus = ObservedFSMCore()
        self.execution_fsm = ExecPosFSM(
            config=self.config,
            fsm=self.bus,
            shadow_mode=True,
            is_live_execution=False,
        )
        self.adapter = RecordingExchangeAdapter()
        self.execution_fsm.adapter = self.adapter
        self.fsm_ingress: list[Any] = []
        self.fsm_results: list[Any] = []
        real_handle = self.execution_fsm.handle

        def observed_handle(message):
            self.fsm_ingress.append(message)
            result = real_handle(message)
            self.fsm_results.append(result)
            return result

        self.execution_fsm.handle = observed_handle
        self._seed_portfolio()
        self.authority_store = TradingSessionAuthorityStore(
            self.config.domains.shadow_telemetry.agent_authority,
            self.now,
        )
        self._seed_authority()
        self.decision_fixture = SimpleNamespace(
            latest_portfolio={
                "equity": "1000",
                "positions": [],
                "ts_ms": self.clock.now_ms(),
            },
            latest_portfolio_ref="account:test:1",
            symbol_states={
                "ETHUSDT": {
                    "current_price": "2500",
                    "snapshot_ref": "market:test:1",
                    "timestamp_ms": self.clock.now_ms(),
                }
            },
        )
        sizing = PositionQueries(
            config=self.config,
            get_portfolio=lambda: self.decision_fixture.latest_portfolio,
            min_pos_size_usd=Decimal("5"),
            liq_cap_usd=Decimal("500"),
            logger=logging.getLogger("p46_1f.sizing"),
        )
        self.processor = AgentTradeIntentV2Processor(
            authority_provider=CanonicalV2AuthorityProvider(
                self.authority_store, self.decision_fixture
            ),
            sizing_adapter=PositionQueriesSizingAdapterV2(sizing),
        )
        self.bridge = LLMIntentIngressBridge(
            fsm=self.bus,
            config=self.config,
            v2_processor=self.processor,
        )
        self.monkeypatch.setenv("SHADOW_TELEMETRY_BEARER_TOKEN", "p46-1f-test-token")
        self.app = create_shadow_telemetry_app(self.config)
        self.client_context = None
        self.client = None

    def _load_isolated_config(self):
        config_dir = self.root_dir / "config"
        shutil.copytree(ROOT / "config" / "aurora", config_dir)
        domains_path = config_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        shadow = domains["shadow_telemetry"]
        shadow["ingest"]["ipc_endpoint"] = f"tcp://127.0.0.1:{_free_port()}"
        shadow["egress_to_main"]["ipc_commands_endpoint"] = f"tcp://127.0.0.1:{_free_port()}"
        shadow["snapshot"]["output_dir"] = str(self.root_dir / "snapshots")
        shadow["api"]["auth_mode"] = "bearer"
        domains_path.write_text(
            yaml.safe_dump(domains, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        trading_path = config_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        trading["trading"]["execution"]["order_guardian"]["ledger_db_path"] = ":memory:"
        trading_path.write_text(
            yaml.safe_dump(trading, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        return ConfigLoader(config_dir=config_dir).load_config()

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.clock.now_sec(), tz=timezone.utc)

    def _seed_authority(self) -> None:
        policy = self.config.domains.shadow_telemetry.agent_authority
        self.authority_store.create_session(TradingSession(
            session_id="session-runtime-1",
            status="ACTIVE",
            created_at=self.now(),
            started_at=self.now(),
            expires_at=self.now() + timedelta(hours=4),
            instrument_universe=["ETHUSDT"],
            participants=[],
            config_version=policy.config_version,
            instruction_version="instructions-runtime-v1",
        ))
        self.authority_store.register_participant(Participant(
            participant_id="participant-api-1",
            agent_id="api_agent_01",
            participant_type="MAIN_AGENT",
            enabled=True,
            session_id="session-runtime-1",
        ))
        self.authority_store.acquire_lease(SymbolLease(
            lease_id="lease-runtime-1",
            session_id="session-runtime-1",
            symbol="ETHUSDT",
            owner_participant_id="participant-api-1",
            acquired_at=self.now(),
            expires_at=self.now() + timedelta(seconds=policy.lease_ttl_sec),
            version=1,
        ))

    def _seed_portfolio(self) -> None:
        now_ms = self.clock.now_ms()
        self.bus.emit("EVT:PORTFOLIO_STATE_UPDATED", {
            "ts": now_ms,
            "equity": "1000",
            "equity_free_usdt": "1000",
            "equity_cross_usdt": "1000",
            "equity_ts": now_ms,
            "realized_pnl": "0",
            "unrealized_pnl": "0",
            "available_balance": "1000",
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            "positions_by_side": {"long_margin": "0", "short_margin": "0"},
            "positions_last_ts_ms": now_ms,
            "positions": [],
        }, "p46_1f_authoritative_account_fixture")

    def start(self) -> "P46RuntimeHarness":
        self.bridge.start()
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        return self

    def stop(self) -> None:
        if self.client_context is not None:
            self.client_context.__exit__(None, None, None)
        self.bridge.stop()
        self.execution_fsm.shutdown()
        reset_clock()

    def payload(self, **updates: Any) -> dict[str, Any]:
        payload = {
            "contract_version": "2.0",
            "session_id": "session-runtime-1",
            "participant_id": "participant-api-1",
            "agent_id": "api_agent_01",
            "symbol": "ETHUSDT",
            "intent_type": "OPEN",
            "side": "BUY",
            "strategy_or_reason": "Thirty minute deterministic runtime proof",
            "confidence": "0.75",
            "max_position_horizon_sec": 7200,
            "context_version": 3,
            "context_ack_version": 3,
            "evidence_refs": ["evidence-runtime-1"],
            "subagent_acknowledgements": [],
            "lease_reference": "lease-runtime-1",
            "client_intent_id": "intent-runtime-0001",
            "created_at": (self.now() - timedelta(seconds=30)).isoformat(),
        }
        payload.update(updates)
        return payload

    def post(self, payload: dict[str, Any]):
        assert self.client is not None
        return self.client.post(
            "/intents/llm/v2",
            json=payload,
            headers={"Authorization": "Bearer p46-1f-test-token", "x-request-id": "ipc-runtime-1"},
        )

    def send_tcp(self, payload: dict[str, Any]) -> None:
        endpoint = self.config.domains.shadow_telemetry.egress_to_main.ipc_commands_endpoint
        host_port = endpoint.removeprefix("tcp://")
        host, port_text = host_port.rsplit(":", 1)
        with socket.create_connection((host, int(port_text)), timeout=2) as sock:
            sock.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii"))

    def wait_for(self, predicate, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("runtime harness condition timed out")

    @property
    def command_emissions(self) -> list[tuple[str, dict[str, Any], str]]:
        return [row for row in self.bus.emissions if row[0] == "CMD:EXTERNAL_OPEN_REQUEST_V1"]

    @property
    def adapter_call_count(self) -> int:
        return len(self.adapter.submit_calls) + len(self.adapter.cancel_calls) + len(self.adapter.amend_calls)
