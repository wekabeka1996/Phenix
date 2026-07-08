"""Local no-model/no-execution AgentIntent fixture and validation CLI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from apps.reference.domains.agent_bridge.agent_intent import AgentIntentV0
from apps.reference.domains.agent_bridge.agent_intent_dry_run import (
    AgentIntentDryRunLedger,
    AgentIntentDryRunRecordV1,
    validate_intent_dry_run,
)


def load_packet(path: Path) -> dict:
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        raise ValueError("packet sample is empty")
    envelope = json.loads(lines[-1])
    return envelope.get("packet", envelope)


def make_intent(packet: dict, *, case_id: str, action: str, symbol: str, expired: bool = False) -> AgentIntentV0:
    packet_ref = f"agent-feed://packet/{packet['packet_id']}"
    memory = packet.get("action_review_memory") or {}
    memory_refs = [memory.get("scenario_memory_index_ref")]
    memory_refs += [item.get("review_ref") for item in memory.get("latest_scenario_memory", [])]
    memory_refs = [item for item in memory_refs if item]
    side = "LONG" if action in {"DRY_RUN_OPEN_LONG", "DRY_RUN_CLOSE", "DRY_RUN_PROTECT"} else "SHORT" if action == "DRY_RUN_OPEN_SHORT" else "NONE"
    produced = int(packet["produced_ts_ms"])
    created = produced - 10_000 if expired else produced
    expiry = produced - 1 if expired else produced + 600_000
    mechanical = action.startswith("DRY_RUN_")
    return AgentIntentV0.model_validate({
        "intent_id": f"intent_p18_{case_id}",
        "created_ts_ms": created,
        "source": "deterministic_fixture",
        "agent_id": "p18.local.no-model-fixture",
        "model_id": None,
        "model_call_ref": None,
        "rank": "unranked_no_model",
        "mode": "dry_run_no_execution",
        "symbol": symbol,
        "horizon": "micro_observation",
        "action": action,
        "side": side,
        "confidence": 0.55,
        "thesis": f"Classify {action} for {symbol} mechanically without model or execution authority.",
        "invalidation": "Packet, capability, parity, lifecycle, or expiry evidence is invalid.",
        "expected_scenarios": [
            {"scenario_id": "no_clear_scenario", "confidence": 0.6, "thesis": "The dry-run may remain mechanically inconclusive."},
            {"scenario_id": "volatility_expansion", "confidence": 0.4, "thesis": "Volatility context may change without granting permission."},
        ],
        "used_packet_refs": [packet_ref],
        "used_memory_refs": memory_refs,
        "acknowledged_warnings": [
            "dry-run acceptance is not trading permission",
            "no exchange interaction is allowed",
        ],
        "requested_execution_semantics": {
            "shape": "MARKET" if action in {"DRY_RUN_OPEN_LONG", "DRY_RUN_OPEN_SHORT"} else "REFERENCE_ONLY" if mechanical else "NONE",
            "quantity": ("0.001" if symbol == "BTCUSDT" else "0.01") if action in {"DRY_RUN_OPEN_LONG", "DRY_RUN_OPEN_SHORT"} else None,
            "reduce_only_requested": action in {"DRY_RUN_CLOSE", "DRY_RUN_PROTECT"},
            "context_ref": None,
            "non_executable": True,
        },
        "risk_note": "This representation cannot submit, route, cancel, amend, or touch an exchange.",
        "expiry_ts_ms": expiry,
        "trace_id": f"trace_p18_{case_id}",
    })


def fixture_intents(packet: dict) -> list[AgentIntentV0]:
    return [
        make_intent(packet, case_id="btc_observe", action="OBSERVE", symbol="BTCUSDT"),
        make_intent(packet, case_id="eth_wait", action="WAIT", symbol="ETHUSDT"),
        make_intent(packet, case_id="btc_open_long", action="DRY_RUN_OPEN_LONG", symbol="BTCUSDT"),
        make_intent(packet, case_id="eth_open_short", action="DRY_RUN_OPEN_SHORT", symbol="ETHUSDT"),
        make_intent(packet, case_id="eth_close_no_position", action="DRY_RUN_CLOSE", symbol="ETHUSDT"),
        make_intent(packet, case_id="eth_expired", action="OBSERVE", symbol="ETHUSDT", expired=True),
    ]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fixtures = sub.add_parser("fixtures")
    fixtures.add_argument("--packet-sample", required=True)
    fixtures.add_argument("--examples-output", required=True)
    fixtures.add_argument("--results-output", required=True)
    fixtures.add_argument("--project-root", default=".")
    generate = sub.add_parser("generate")
    generate.add_argument("--packet-sample", required=True)
    generate.add_argument("--action", choices=["WAIT", "OBSERVE"], required=True)
    generate.add_argument("--symbol", choices=["BTCUSDT", "ETHUSDT"], required=True)
    generate.add_argument("--output", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--packet-sample", required=True)
    validate.add_argument("--intent-json", required=True)
    validate.add_argument("--project-root", default=".")
    validate.add_argument("--write-ledger", action="store_true")
    rotate = sub.add_parser("rotate")
    rotate.add_argument("--project-root", default=".")
    rotate.add_argument("--created-utc")
    rotate.add_argument("--manifest-output")
    index = sub.add_parser("rebuild-index")
    index.add_argument("--project-root", default=".")
    index.add_argument("--generated-utc")
    index.add_argument("--output")
    recover = sub.add_parser("recover")
    recover.add_argument("--project-root", default=".")
    recover.add_argument("--created-utc")
    recover.add_argument("--quarantine-temporary-files", action="store_true")
    recover.add_argument("--output")
    reconstruct = sub.add_parser("reconstruct-manifest")
    reconstruct.add_argument("--project-root", default=".")
    reconstruct.add_argument("--archive-filename", required=True)
    reconstruct.add_argument("--operator-approval-ref", required=True)
    reconstruct.add_argument("--reason", required=True)
    reconstruct.add_argument("--created-utc")
    reconstruct.add_argument("--output")
    args = parser.parse_args()
    if args.command == "rotate":
        ledger = AgentIntentDryRunLedger(Path(args.project_root).resolve() / "ops/agent_bridge/agent_intents")
        manifest = ledger.rotate(created_utc=args.created_utc)
        payload = manifest.model_dump(mode="json", exclude_none=True)
        if args.manifest_output:
            write_json(Path(args.manifest_output), payload)
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    if args.command == "rebuild-index":
        ledger = AgentIntentDryRunLedger(Path(args.project_root).resolve() / "ops/agent_bridge/agent_intents")
        payload = ledger.rebuild_manifest_index(generated_utc=args.generated_utc, persist=True)
        if args.output:
            write_json(Path(args.output), payload)
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    if args.command == "recover":
        ledger = AgentIntentDryRunLedger(Path(args.project_root).resolve() / "ops/agent_bridge/agent_intents")
        payload = ledger.recover(created_utc=args.created_utc, quarantine_temporary_files=args.quarantine_temporary_files)
        if args.output:
            write_json(Path(args.output), payload)
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    if args.command == "reconstruct-manifest":
        ledger = AgentIntentDryRunLedger(Path(args.project_root).resolve() / "ops/agent_bridge/agent_intents")
        manifest = ledger.reconstruct_orphan_manifest(
            archive_filename=args.archive_filename, operator_approval_ref=args.operator_approval_ref,
            reconstruction_reason=args.reason, created_utc=args.created_utc,
        )
        payload = manifest.model_dump(mode="json", exclude_none=True)
        if args.output: write_json(Path(args.output), payload)
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    packet = load_packet(Path(args.packet_sample))
    if args.command == "generate":
        intent = make_intent(packet, case_id=f"generated_{args.symbol.lower()}_{args.action.lower()}", action=args.action, symbol=args.symbol)
        write_json(Path(args.output), intent.model_dump(mode="json", exclude_none=True))
        print(intent.model_dump_json(exclude_none=True))
        return 0
    ledger = AgentIntentDryRunLedger(Path(args.project_root).resolve() / "ops/agent_bridge/agent_intents")
    if args.command == "validate":
        intent = AgentIntentV0.model_validate_json(Path(args.intent_json).read_text(encoding="utf-8"))
        result = validate_intent_dry_run(intent, packet, now_ms=int(time.time() * 1000))
        record = AgentIntentDryRunRecordV1(intent=intent, result=result)
        appended = ledger.append(record) if args.write_ledger else False
        print(json.dumps({"appended": appended, "record": record.model_dump(mode="json", exclude_none=True)}, separators=(",", ":")))
        return 0
    intents = fixture_intents(packet)
    records = []
    appended = 0
    now_ms = int(time.time() * 1000)
    for intent in intents:
        result = validate_intent_dry_run(intent, packet, now_ms=now_ms)
        record = AgentIntentDryRunRecordV1(intent=intent, result=result)
        appended += int(ledger.append(record))
        records.append(record)
    write_json(Path(args.examples_output), {
        "schema_version": "agent-intent-examples/p18",
        "items": [item.model_dump(mode="json", exclude_none=True) for item in intents],
    })
    results_path = Path(args.results_output)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        "".join(item.model_dump_json(exclude_none=True) + "\n" for item in records), encoding="utf-8"
    )
    print(json.dumps({
        "generated": len(records),
        "appended": appended,
        "statuses": [item.result.validation_status for item in records],
        "submitted": sum(item.result.submitted for item in records),
        "exchange_touched": sum(item.result.exchange_touched for item in records),
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
