from __future__ import annotations

from collections import Counter

from fastapi import Request

from apps.reference.domains.shadow_telemetry import main as shadow_main
from tests.domains.shadow_telemetry.test_p46_2c_read_model import NoopClient, NoopServer, fixture


class ProofClient(NoopClient):
    instances: list["ProofClient"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.instances.append(self)


shadow_main.JsonlTcpServer = NoopServer
shadow_main.JsonlTcpQueueClient = ProofClient
config, _, authority, service = fixture()
app = shadow_main.create_shadow_telemetry_app(config, read_model_service=service)
app.state.auth_mode = "bearer"
app.state.proof_methods = Counter()


@app.middleware("http")
async def count_methods(request: Request, call_next):
    app.state.proof_methods[request.method] += 1
    return await call_next(request)


@app.get("/p46-2c-proof-counters")
def proof_counters() -> dict[str, object]:
    return {
        "methods": dict(app.state.proof_methods),
        "execution_commands": sum(len(client.enqueued) for client in ProofClient.instances),
        "authority_decisions": len(authority.decisions()),
        "adapter_calls": 0,
        "exchange_calls": 0,
        "provider_calls": 0,
    }
