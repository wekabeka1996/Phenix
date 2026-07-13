from __future__ import annotations

from collections import Counter
from datetime import timedelta

from fastapi import Request

from apps.reference.domains.shadow_telemetry import main as shadow_main
from apps.reference.domains.shadow_telemetry.read_model_contract import (
    ContextSourceSnapshot,
    LifecycleSourceSnapshot,
)
from apps.reference.domains.shadow_telemetry.read_model_service import PhenixReadModelService
from tests.domains.shadow_telemetry.test_p46_2c_read_model import NoopClient, NoopServer
from tests.domains.shadow_telemetry.test_p46_2d_proposal_dry_run import fixture


class ProofClient(NoopClient):
    instances: list["ProofClient"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.instances.append(self)


shadow_main.JsonlTcpServer = NoopServer
shadow_main.JsonlTcpQueueClient = ProofClient
config, clock, authority, dry_run_service, exposure_calls = fixture()
context_version = {"value": "manifest-v9"}


def context_reader(session_id: str) -> ContextSourceSnapshot:
    assert session_id == "phenix-p46-2d"
    return ContextSourceSnapshot(
        manifest_version=context_version["value"],
        content_hash=f"sha256:{context_version['value']}",
        instruction_version="instructions-v7",
        created_at=clock(),
        stale_after=clock() + timedelta(minutes=5),
        source_references=(f"memory://manifest/{context_version['value']}",),
    )


def lifecycle_reader(session_id: str) -> LifecycleSourceSnapshot:
    assert session_id == "phenix-p46-2d"
    return LifecycleSourceSnapshot(
        reconciliation_state="RECONCILED",
        reconciliation_divergence=False,
        last_reconciled_at=clock(),
        source_kind="P46_2D_RECORDING_RUNTIME",
        source_references=("fsm://recording-runtime/reconciliation",),
    )


read_model_service = PhenixReadModelService(
    authority=authority,
    context_reader=context_reader,
    lifecycle_reader=lifecycle_reader,
    policy=config.domains.shadow_telemetry.api.read_model,
    clock=clock,
)
app = shadow_main.create_shadow_telemetry_app(
    config,
    read_model_service=read_model_service,
    proposal_dry_run_service=dry_run_service,
)
app.state.auth_mode = "bearer"
app.state.proof_methods = Counter()
app.state.proof_dry_run_posts = 0


@app.middleware("http")
async def count_methods(request: Request, call_next):
    app.state.proof_methods[request.method] += 1
    if request.method == "POST" and request.url.path.startswith("/proposal-dry-run/v1/sessions/"):
        app.state.proof_dry_run_posts += 1
    return await call_next(request)


@app.post("/p46-2d-proof/context/{manifest_version}")
def change_context(manifest_version: str) -> dict[str, str]:
    context_version["value"] = manifest_version
    return {"manifest_version": manifest_version}


@app.get("/p46-2d-proof-counters")
def proof_counters() -> dict[str, object]:
    results = list(dry_run_service._results.values())
    return {
        "methods": dict(app.state.proof_methods),
        "dry_run_posts": app.state.proof_dry_run_posts,
        "proposals_evaluated": len(results),
        "exposure_preview_calls": len(exposure_calls),
        "execution_commands": sum(len(client.enqueued) for client in ProofClient.instances),
        "fsm_calls": 0,
        "adapter_calls": 0,
        "exchange_calls": 0,
        "provider_calls": 0,
        "side_effects": [item.side_effects.model_dump() for item in results],
    }
