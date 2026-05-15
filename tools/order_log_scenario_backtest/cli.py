from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .candles import CandleCoverageError, load_1m_candles, preflight_1m_coverage
from .config_loader import load_backtest_config
from .exit_policies import (
    build_sidecar_request_index,
    load_sidecar_requests,
    materialize_trade_result,
)
from .models import CanonicalEntry, ScenarioRuntime
from .reconstruct import reconstruct_canonical_entries
from .reporting import write_json, write_scenario_artifacts
from .scenario_registry import build_scenario_registry
from .schema_probe import probe_schema


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _selected_scenarios(raw: str, registry: dict[str, object]) -> list[str]:
    if str(raw).strip().lower() == "all":
        return list(registry.keys())
    selected = [item.strip() for item in str(raw).split(",") if item.strip()]
    unknown = [item for item in selected if item not in registry]
    if unknown:
        raise ValueError(f"Unknown scenario ids: {', '.join(unknown)}")
    if selected and "tp_sl_only" not in selected:
        return ["tp_sl_only", *selected]
    return selected or ["tp_sl_only"]


def _run_scenario(
    scenario_id: str,
    entries: list[CanonicalEntry],
    runtime: ScenarioRuntime,
    registry: dict[str, object],
    report_root: Path,
    baseline_summary: dict | None,
) -> dict:
    scenario = registry[scenario_id]
    blocked_rows: list[dict] = []
    trade_rows: list[dict] = []
    request_join_audit_rows: list[dict] = []

    for entry in entries:
        decision = scenario.entry_filter(entry, runtime)
        if not decision.allowed:
            blocked_rows.append(decision.to_row(scenario_id, entry))
            continue
        exit_event, extras = scenario.exit_policy(entry, runtime)
        extras["allow_regime_flip_exits"] = "true" if scenario.allow_regime_flip_exits else "false"
        if extras.get("request_join_audit"):
            request_join_audit_rows.append(extras["request_join_audit"])
        trade_rows.append(materialize_trade_result(scenario_id, entry, runtime, exit_event, extras))

    assumptions = [
        "Replay horizon is max(actual_close_ts_ms, entry_ts_ms + 24h).",
        "TP/SL geometry is reconstructed from current Aurora pct_mult config and runtime guardrails.",
        "Missing gate surfaces are treated fail-closed for NRR entry-filter scenarios.",
    ]
    unknowns = []
    if scenario_id.startswith("nrr") and not any(
        row.get("support_quality") == "runtime_parity" for row in blocked_rows
    ):
        unknowns.append("No gate denials with high-support parity evidence were produced for this scenario.")
    if scenario_id == "sidecar_only":
        unknowns.append("Sidecar exits remain unresolved when no recorded sidecar request or next 1m candle open is available.")
    return write_scenario_artifacts(
        report_root / scenario_id,
        scenario_id,
        scenario.report_contract,
        trade_rows,
        blocked_rows,
        request_join_audit_rows,
        baseline_summary,
        assumptions,
        unknowns,
    )


def run_backtest(
    *,
    workspace_root: Path,
    runtime_root: Path,
    report_root: Path,
    recorder_root: Path,
    extra_recorder_roots: Iterable[Path | str] | None = None,
    scenarios: str = "all",
    strict: bool = True,
) -> dict:
    report_root.mkdir(parents=True, exist_ok=True)
    strict = _parse_bool(strict)
    registry = build_scenario_registry()
    selected = _selected_scenarios(scenarios, registry)
    recorder_roots = [recorder_root, *(extra_recorder_roots or [])]

    schema = probe_schema(runtime_root / "order_log_v1.jsonl", report_root)
    canonical_entries, unresolved_rows, reconstruction_manifest = reconstruct_canonical_entries(
        workspace_root,
        runtime_root,
        report_root,
    )

    coverage_result = None
    try:
        coverage_result = preflight_1m_coverage(
            workspace_root,
            canonical_entries,
            report_root,
            recorder_roots,
            strict=strict,
        )
    except CandleCoverageError as exc:
        coverage_result = exc.result
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace_root": str(workspace_root),
            "runtime_root": str(runtime_root),
            "report_root": str(report_root),
            "selected_scenarios": selected,
            "strict": strict,
            "schema_probe": {
                "captured_families": len(schema.get("captured_families") or []),
                "missing_families": len(schema.get("missing_families") or []),
            },
            "reconstruction": reconstruction_manifest,
            "canonical_entries": len(canonical_entries),
            "unresolved_order_rows": len(unresolved_rows),
            "candle_coverage": {
                "strict_1m_ok": coverage_result.strict_1m_ok,
                "required_windows": len(coverage_result.required_windows),
            },
            "status": "failed_strict_candle_coverage",
        }
        write_json(report_root / "run_manifest.json", manifest)
        return manifest

    candles_by_symbol = load_1m_candles(workspace_root, recorder_roots)
    config = load_backtest_config(workspace_root)
    runtime = ScenarioRuntime(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        config=config,
        candles_by_symbol=candles_by_symbol,
        strict=strict,
    )
    if "sidecar_only" in selected:
        sidecar_requests = load_sidecar_requests(runtime_root)
        runtime.sidecar_requests = sidecar_requests
        runtime.sidecar_request_index = build_sidecar_request_index(sidecar_requests)

    scenario_summaries: dict[str, dict] = {}
    baseline_summary = None
    for scenario_id in selected:
        summary = _run_scenario(
            scenario_id,
            canonical_entries,
            runtime,
            registry,
            report_root,
            baseline_summary,
        )
        scenario_summaries[scenario_id] = summary
        if scenario_id == "tp_sl_only":
            baseline_summary = summary

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "runtime_root": str(runtime_root),
        "report_root": str(report_root),
        "selected_scenarios": selected,
        "strict": strict,
        "schema_probe": {
            "captured_families": len(schema.get("captured_families") or []),
            "missing_families": len(schema.get("missing_families") or []),
        },
        "reconstruction": reconstruction_manifest,
        "canonical_entries": len(canonical_entries),
        "unresolved_order_rows": len(unresolved_rows),
        "candle_coverage": {
            "strict_1m_ok": coverage_result.strict_1m_ok if coverage_result is not None else False,
            "required_windows": len(coverage_result.required_windows) if coverage_result is not None else 0,
        },
        "scenario_summaries": scenario_summaries,
        "status": "complete",
    }
    write_json(report_root / "run_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="logs")
    parser.add_argument("--report-root", default="reports/order_log_scenario_backtest")
    parser.add_argument("--recorder-root", default="data/recorder")
    parser.add_argument(
        "--extra-recorder-root",
        action="append",
        default=["data/recorder_backfill_1m"],
    )
    parser.add_argument("--scenarios", default="all")
    parser.add_argument("--strict", default="true")
    args = parser.parse_args(argv)

    workspace_root = Path.cwd()
    manifest = run_backtest(
        workspace_root=workspace_root,
        runtime_root=(workspace_root / args.runtime_root).resolve(),
        report_root=(workspace_root / args.report_root).resolve(),
        recorder_root=(workspace_root / args.recorder_root).resolve(),
        extra_recorder_roots=[
            (workspace_root / item).resolve() if not Path(item).is_absolute() else Path(item)
            for item in args.extra_recorder_root
        ],
        scenarios=args.scenarios,
        strict=_parse_bool(args.strict),
    )
    return 0 if manifest.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
