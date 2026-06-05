from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.analysis.order_reconstruction_tp_sl_common import write_csv
from tools.analysis.target_roi_history_inventory import (
    canonical_entry_identity,
    dedupe_canonical_entries,
    discover_runtime_root_candidates,
    discover_wal_files,
    reconstruct_wal_only_canonical_entries,
    scan_wal_open_inventory,
)
from tools.order_log_scenario_backtest.candles import (
    CandleCoverageError,
    load_1m_candles,
    preflight_1m_coverage,
)
from tools.order_log_scenario_backtest.config_loader import load_backtest_config
from tools.order_log_scenario_backtest.exit_policies import materialize_trade_result, target_roi_exit
from tools.order_log_scenario_backtest.models import ScenarioRuntime
from tools.order_log_scenario_backtest.reconstruct import reconstruct_canonical_entries
from tools.order_log_scenario_backtest.reporting import summarize_trade_results, write_json

DEFAULT_TARGET_ROI_PCTS = (7.0, 8.0, 9.0, 10.0)
DEFAULT_HORIZON_MODES = ("actual_close_window", "fixed_24h_window")
DEFAULT_RECORDER_ROOTS = (
    Path("data/raw_binance_klines_1m"),
    Path("data/recorder_backfill_1m"),
    Path("data/recorder"),
)


def _parse_csv_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in str(raw).split(",") if item.strip()]


def _parse_csv_strings(raw: str) -> list[str]:
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _resolve_recorder_roots(
    workspace_root: Path,
    recorder_roots: Iterable[Path | str] | None,
) -> list[Path]:
    candidates = list(recorder_roots or DEFAULT_RECORDER_ROOTS)
    resolved: list[Path] = []
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = (workspace_root / path).resolve(strict=False)
        else:
            path = path.resolve(strict=False)
        if path not in resolved:
            resolved.append(path)
    return resolved


def _target_replay_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_trade_results(rows)
    target_hits = sum(1 for row in rows if str(
        row.get("target_hit") or "").lower() == "true")
    ambiguous_sl_first = sum(1 for row in rows if row.get(
        "exit_reason") == "historical_sl_first_ambiguous_intrabar")
    historical_sl_hits = sum(1 for row in rows if row.get(
        "exit_reason") == "historical_sl_hit")
    window_end_count = sum(
        1
        for row in rows
        if row.get("exit_reason") in {"actual_close_window_end", "replay_window_end"}
    )
    summary.update(
        {
            "target_hits": target_hits,
            "target_hit_rate": round(target_hits / len(rows), 6) if rows else 0.0,
            "historical_sl_hits": historical_sl_hits,
            "ambiguous_sl_first": ambiguous_sl_first,
            "window_end_count": window_end_count,
        }
    )
    return summary


def _group_summary(rows: list[dict[str, Any]], *fields: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row.get(field)
                           for field in fields), []).append(row)
    payload: list[dict[str, Any]] = []
    for key, group_rows in sorted(grouped.items()):
        summary = _target_replay_summary(group_rows)
        for index, field in enumerate(fields):
            summary[field] = key[index]
        payload.append(summary)
    return payload


def _build_report(summary_rows: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    lines = [
        "# Target ROI Replay Report",
        "",
        "## FACTS",
        f"- Runtime root: {manifest['runtime_root']}",
        f"- Report root: {manifest['report_root']}",
        f"- Canonical entries: {manifest['canonical_entries']}",
        f"- Result rows: {manifest['result_rows']}",
        f"- Target ROI set: {', '.join(str(item) for item in manifest['target_roi_pcts'])}",
        f"- Horizon modes: {', '.join(manifest['horizon_modes'])}",
        f"- Strict candle coverage: {manifest['strict']}",
        "",
        "| target_net_roi_pct | horizon_mode | trades | target_hits | target_hit_rate | losses | unresolved | avg_net_roi | total_net_roi |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['target_net_roi_pct']} | {row['horizon_mode']} | {row['trades']} | {row['target_hits']} | {row['target_hit_rate']} | "
            f"{row['losses']} | {row['unresolved']} | {row['avg_net_roi']} | {row['total_net_roi']} |"
        )
    lines.extend(
        [
            "",
            "## ASSUMPTIONS",
            "- Historical SL is taken from retained order-log decision geometry, not recomputed from current TP/SL config.",
            "- Net ROI targets are converted using actual leverage and retained round_trip_fee_bps when available.",
            "- Intrabar ambiguity remains fail-closed to SL-first when TP and SL are both touched inside one 1m candle.",
            "",
            "## UNKNOWNS",
            "- Multi-slice runtime inventory and cross-snapshot dedupe are not part of this first implementation slice.",
            "- If a runtime slice lacks retained historical stop geometry, those rows stay unresolved rather than silently falling back to current config.",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_history_report(summary_rows: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    inventory = manifest.get("inventory") or {}
    wal_inventory = manifest.get("wal_inventory") or {}
    lines = [
        "# Target ROI Historical Replay Report",
        "",
        "## FACTS",
        f"- Status: {manifest.get('status', 'unknown')}",
        f"- Report root: {manifest['report_root']}",
        f"- Runtime sources discovered: {inventory.get('runtime_sources_discovered', 0)}",
        f"- Runtime sources used: {inventory.get('runtime_sources_used', 0)}",
        f"- Raw canonical entries across sources: {inventory.get('raw_canonical_entries', 0)}",
        f"- Unique canonical entries after dedupe: {inventory.get('unique_canonical_entries', 0)}",
        f"- Duplicate candidates dropped: {inventory.get('duplicate_entries_dropped', 0)}",
        f"- WAL files scanned: {wal_inventory.get('wal_files', 0)}",
        f"- WAL open RIDs matched to runtime inventory: {wal_inventory.get('matched_open_rids', 0)}",
        f"- WAL-only open RIDs: {wal_inventory.get('wal_only_open_rids', 0)}",
        f"- Result rows: {manifest.get('result_rows', 0)}",
        f"- Target ROI set: {', '.join(str(item) for item in manifest.get('target_roi_pcts', []))}",
        f"- Horizon modes: {', '.join(manifest.get('horizon_modes', []))}",
        f"- Strict candle coverage: {manifest.get('strict')}",
        "",
    ]
    if summary_rows:
        lines.extend(
            [
                "| target_net_roi_pct | horizon_mode | trades | target_hits | target_hit_rate | losses | unresolved | avg_net_roi | total_net_roi |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in summary_rows:
            lines.append(
                f"| {row['target_net_roi_pct']} | {row['horizon_mode']} | {row['trades']} | {row['target_hits']} | {row['target_hit_rate']} | "
                f"{row['losses']} | {row['unresolved']} | {row['avg_net_roi']} | {row['total_net_roi']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## ASSUMPTIONS",
            "- Historical SL/TP geometry is preserved from retained runtime evidence and never silently recomputed from current config.",
            "- Frozen captures are treated as overlapping runtime slices and deduped by canonical identity, preferring the richer retained evidence when duplicates disagree.",
            "- WAL is used as an anti-gap inventory layer for actual opened positions; bracket-only RIDs such as :TP and :SL and unfilled intent-only rows are excluded from open-entry counts.",
            "",
            "## UNKNOWNS",
            "- WAL fallback reconstruction is bounded to actual opened positions with TRADE_EXECUTED support; rows that never reach execution stay outside the canonical corpus.",
            "- Source precedence is evidence-weighted rather than semantically perfect; conflicting duplicate slices still need manual adjudication if they retain different historical geometry.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_target_roi_replay(
    *,
    workspace_root: Path,
    runtime_root: Path,
    report_root: Path,
    recorder_roots: Iterable[Path | str] | None = None,
    target_roi_pcts: Iterable[float] = DEFAULT_TARGET_ROI_PCTS,
    horizon_modes: Iterable[str] = DEFAULT_HORIZON_MODES,
    strict: bool = True,
) -> dict[str, Any]:
    report_root.mkdir(parents=True, exist_ok=True)
    canonical_entries, unresolved_rows, reconstruction_manifest = reconstruct_canonical_entries(
        workspace_root,
        runtime_root,
        report_root / "_reconstruct",
    )
    config = load_backtest_config(workspace_root)
    resolved_recorder_roots = _resolve_recorder_roots(
        workspace_root, recorder_roots)

    try:
        coverage_result = preflight_1m_coverage(
            workspace_root,
            canonical_entries,
            report_root,
            resolved_recorder_roots,
            strict=strict,
        )
    except CandleCoverageError as exc:
        coverage_result = exc.result
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace_root": str(workspace_root),
            "runtime_root": str(runtime_root),
            "report_root": str(report_root),
            "strict": strict,
            "target_roi_pcts": [float(item) for item in target_roi_pcts],
            "horizon_modes": [str(item) for item in horizon_modes],
            "canonical_entries": len(canonical_entries),
            "unresolved_order_rows": len(unresolved_rows),
            "reconstruction": reconstruction_manifest,
            "candle_coverage": {
                "strict_1m_ok": coverage_result.strict_1m_ok,
                "required_windows": len(coverage_result.required_windows),
                "resolved_recorder_roots": [str(path) for path in coverage_result.resolved_recorder_roots],
            },
            "status": "failed_strict_candle_coverage",
        }
        write_json(report_root / "run_manifest.json", manifest)
        return manifest

    candles_by_symbol = load_1m_candles(
        workspace_root, resolved_recorder_roots)
    runtime = ScenarioRuntime(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        config=config,
        candles_by_symbol=candles_by_symbol,
        strict=strict,
    )

    trade_rows: list[dict[str, Any]] = []
    for entry in canonical_entries:
        for target_roi_pct in target_roi_pcts:
            for horizon_mode in horizon_modes:
                exit_event, extras = target_roi_exit(
                    entry,
                    runtime,
                    float(target_roi_pct),
                    horizon_mode=str(horizon_mode),
                )
                row = materialize_trade_result(
                    "target_roi_replay",
                    entry,
                    runtime,
                    exit_event,
                    extras,
                )
                context = extras.get("target_roi_context") or {}
                row.update(
                    {
                        "target_net_roi_pct": float(target_roi_pct),
                        "horizon_mode": str(horizon_mode),
                        "target_hit": extras.get("target_hit", "false"),
                        "historical_target_price": entry.historical_target_price if entry.historical_target_price is not None else "",
                        "historical_stop_price": entry.historical_stop_price if entry.historical_stop_price is not None else "",
                        "historical_geometry_source": entry.historical_geometry_source or "",
                        "historical_round_trip_fee_bps": entry.historical_round_trip_fee_bps if entry.historical_round_trip_fee_bps is not None else "",
                        "target_gross_roi_pct": context.get("target_gross_roi_pct", ""),
                        "target_move_pct": context.get("target_move_pct", ""),
                        "original_sl_move_pct": context.get("original_sl_move_pct", ""),
                        "original_sl_net_roi_pct": context.get("original_sl_net_roi_pct", ""),
                        "rr_vs_original_sl": context.get("rr_vs_original_sl", ""),
                    }
                )
                trade_rows.append(row)

    summary_by_target_horizon = _group_summary(
        trade_rows, "target_net_roi_pct", "horizon_mode")
    summary_by_symbol = _group_summary(
        trade_rows, "symbol", "target_net_roi_pct", "horizon_mode")
    unresolved_geometry_rows = [row for row in trade_rows if row.get(
        "exit_reason") == "target_roi_unresolved"]

    trade_headers = list(trade_rows[0].keys()) if trade_rows else []
    summary_headers = list(
        summary_by_target_horizon[0].keys()) if summary_by_target_horizon else []
    summary_symbol_headers = list(
        summary_by_symbol[0].keys()) if summary_by_symbol else []
    if trade_rows:
        write_csv(report_root / "target_roi_trade_results.csv",
                  trade_headers, trade_rows)
    if summary_by_target_horizon:
        write_csv(report_root / "target_roi_summary_by_target_horizon.csv",
                  summary_headers, summary_by_target_horizon)
    if summary_by_symbol:
        write_csv(report_root / "target_roi_summary_by_symbol.csv",
                  summary_symbol_headers, summary_by_symbol)
    if unresolved_geometry_rows:
        write_csv(report_root / "target_roi_unresolved_geometry.csv",
                  trade_headers, unresolved_geometry_rows)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "runtime_root": str(runtime_root),
        "report_root": str(report_root),
        "strict": strict,
        "target_roi_pcts": [float(item) for item in target_roi_pcts],
        "horizon_modes": [str(item) for item in horizon_modes],
        "canonical_entries": len(canonical_entries),
        "unresolved_order_rows": len(unresolved_rows),
        "reconstruction": reconstruction_manifest,
        "resolved_recorder_roots": [str(path) for path in resolved_recorder_roots],
        "candle_coverage": {
            "strict_1m_ok": coverage_result.strict_1m_ok,
            "required_windows": len(coverage_result.required_windows),
        },
        "result_rows": len(trade_rows),
        "unresolved_geometry_rows": len(unresolved_geometry_rows),
        "status": "ok",
    }
    write_json(report_root / "run_manifest.json", manifest)
    write_json(
        report_root / "target_roi_summary.json",
        {
            "by_target_horizon": summary_by_target_horizon,
            "by_symbol": summary_by_symbol,
        },
    )
    (report_root / "report.md").write_text(
        _build_report(summary_by_target_horizon, manifest),
        encoding="utf-8",
    )
    return manifest


def run_target_roi_history_replay(
    *,
    workspace_root: Path,
    runtime_root: Path | None,
    report_root: Path,
    extra_runtime_roots: Iterable[Path | str] | None = None,
    include_frozen: bool = True,
    include_wal: bool = True,
    wal_paths: Iterable[Path | str] | None = None,
    recorder_roots: Iterable[Path | str] | None = None,
    target_roi_pcts: Iterable[float] = DEFAULT_TARGET_ROI_PCTS,
    horizon_modes: Iterable[str] = DEFAULT_HORIZON_MODES,
    strict: bool = True,
) -> dict[str, Any]:
    report_root.mkdir(parents=True, exist_ok=True)
    runtime_sources = discover_runtime_root_candidates(
        workspace_root,
        runtime_root=runtime_root,
        extra_runtime_roots=extra_runtime_roots,
        include_frozen=include_frozen,
    )
    if not runtime_sources:
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace_root": str(workspace_root),
            "report_root": str(report_root),
            "strict": strict,
            "target_roi_pcts": [float(item) for item in target_roi_pcts],
            "horizon_modes": [str(item) for item in horizon_modes],
            "inventory": {
                "runtime_sources_discovered": 0,
                "runtime_sources_used": 0,
                "raw_canonical_entries": 0,
                "unique_canonical_entries": 0,
                "duplicate_entries_dropped": 0,
            },
            "sources": [],
            "wal_inventory": {
                "enabled": bool(include_wal),
                "wal_files": 0,
                "open_rids": 0,
                "matched_open_rids": 0,
                "wal_only_open_rids": 0,
                "wal_only_open_rids_preview": [],
            },
            "status": "failed_no_runtime_sources",
        }
        write_json(report_root / "run_manifest.json", manifest)
        (report_root / "report.md").write_text(
            _build_history_report([], manifest),
            encoding="utf-8",
        )
        return manifest

    candidate_entries: list[tuple[Any, dict[str, Any]]] = []
    source_rows: list[dict[str, Any]] = []
    for source in runtime_sources:
        source_row = {
            "runtime_root": source["runtime_root"],
            "source_kind": source["source_kind"],
            "source_label": source["source_label"],
            "report_dir_name": source["report_dir_name"],
            "has_aurora_core": source["has_aurora_core"],
            "has_trade_lifecycle": source["has_trade_lifecycle"],
            "has_execution_lifecycle_stats": source["has_execution_lifecycle_stats"],
            "has_regime_confidence_audit": source["has_regime_confidence_audit"],
            "support_score": source["support_score"],
            "discovery_index": source["discovery_index"],
            "runtime_root_path": source["runtime_root_path"],
        }
        source_report_root = report_root / \
            "_sources" / source_row["report_dir_name"]
        canonical_entries, unresolved_rows, reconstruction_manifest = reconstruct_canonical_entries(
            workspace_root,
            source_row["runtime_root_path"],
            source_report_root,
        )
        source_row.update(
            {
                "canonical_entries_raw": len(canonical_entries),
                "unresolved_order_rows": len(unresolved_rows),
                "retained_rows": reconstruction_manifest.get("retained_rows", 0),
                "core_regime_rows": reconstruction_manifest.get("core_regime_rows", 0),
                "core_log_offset_ms": reconstruction_manifest.get("core_log_offset_ms", ""),
            }
        )
        source_rows.append(source_row)
        for entry in canonical_entries:
            candidate_entries.append((entry, source_row))

    selected_infos, entry_inventory_rows = dedupe_canonical_entries(
        candidate_entries)
    raw_entry_count = len(candidate_entries)
    unique_entry_count = len(selected_infos)
    duplicate_entries_dropped = raw_entry_count - unique_entry_count

    if not selected_infos:
        serializable_sources = []
        for source_row in source_rows:
            serializable_sources.append(
                {
                    "runtime_root": source_row["runtime_root"],
                    "source_kind": source_row["source_kind"],
                    "source_label": source_row["source_label"],
                    "support_score": source_row["support_score"],
                    "has_aurora_core": source_row["has_aurora_core"],
                    "has_trade_lifecycle": source_row["has_trade_lifecycle"],
                    "has_execution_lifecycle_stats": source_row["has_execution_lifecycle_stats"],
                    "has_regime_confidence_audit": source_row["has_regime_confidence_audit"],
                    "canonical_entries_raw": source_row["canonical_entries_raw"],
                    "unresolved_order_rows": source_row["unresolved_order_rows"],
                    "retained_rows": source_row["retained_rows"],
                    "core_regime_rows": source_row["core_regime_rows"],
                    "core_log_offset_ms": source_row["core_log_offset_ms"],
                    "selected_entries": 0,
                    "duplicate_entries_dropped": 0,
                }
            )
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace_root": str(workspace_root),
            "report_root": str(report_root),
            "strict": strict,
            "target_roi_pcts": [float(item) for item in target_roi_pcts],
            "horizon_modes": [str(item) for item in horizon_modes],
            "inventory": {
                "runtime_sources_discovered": len(runtime_sources),
                "runtime_sources_used": len(serializable_sources),
                "raw_canonical_entries": raw_entry_count,
                "unique_canonical_entries": 0,
                "duplicate_entries_dropped": duplicate_entries_dropped,
            },
            "sources": serializable_sources,
            "wal_inventory": {
                "enabled": bool(include_wal),
                "wal_files": 0,
                "open_rids": 0,
                "matched_open_rids": 0,
                "wal_only_open_rids": 0,
                "wal_only_open_rids_preview": [],
            },
            "status": "failed_empty_inventory",
        }
        write_json(report_root / "run_manifest.json", manifest)
        (report_root / "report.md").write_text(
            _build_history_report([], manifest),
            encoding="utf-8",
        )
        return manifest

    selected_counts = Counter(info["source"]["runtime_root"]
                              for info in selected_infos)
    serializable_sources: list[dict[str, Any]] = []
    for source_row in source_rows:
        selected_entries = selected_counts.get(source_row["runtime_root"], 0)
        serializable_sources.append(
            {
                "runtime_root": source_row["runtime_root"],
                "source_kind": source_row["source_kind"],
                "source_label": source_row["source_label"],
                "support_score": source_row["support_score"],
                "has_aurora_core": source_row["has_aurora_core"],
                "has_trade_lifecycle": source_row["has_trade_lifecycle"],
                "has_execution_lifecycle_stats": source_row["has_execution_lifecycle_stats"],
                "has_regime_confidence_audit": source_row["has_regime_confidence_audit"],
                "canonical_entries_raw": source_row["canonical_entries_raw"],
                "unresolved_order_rows": source_row["unresolved_order_rows"],
                "retained_rows": source_row["retained_rows"],
                "core_regime_rows": source_row["core_regime_rows"],
                "core_log_offset_ms": source_row["core_log_offset_ms"],
                "selected_entries": selected_entries,
                "duplicate_entries_dropped": max(source_row["canonical_entries_raw"] - selected_entries, 0),
            }
        )

    selected_info_by_identity: dict[str, dict[str, Any]] = {}
    selected_entries = []
    for info in selected_infos:
        entry = info["entry"]
        identity_key = canonical_entry_identity(entry)
        selected_info_by_identity[identity_key] = info
        selected_entries.append(entry)

    wal_inventory_rows: list[dict[str, Any]] = []
    wal_only_inventory_rows: list[dict[str, Any]] = []
    wal_reconstructed_entries: list[Any] = []
    wal_unreconstructed_inventory_rows: list[dict[str, Any]] = []
    wal_files = discover_wal_files(
        workspace_root, wal_paths) if include_wal else []
    config = load_backtest_config(workspace_root)
    if include_wal:
        wal_inventory_rows = scan_wal_open_inventory(wal_files)
        order_log_rids = {
            str(entry.rid)
            for entry in selected_entries
            if str(entry.rid or "").strip()
        }
        wal_only_inventory_rows = [
            row for row in wal_inventory_rows if str(row.get("rid") or "") not in order_log_rids
        ]
        if wal_inventory_rows:
            wal_headers = list(wal_inventory_rows[0].keys())
            write_csv(report_root / "wal_open_inventory.csv",
                      wal_headers, wal_inventory_rows)
        if wal_only_inventory_rows:
            wal_only_headers = list(wal_only_inventory_rows[0].keys())
            write_csv(report_root / "wal_only_open_inventory.csv",
                      wal_only_headers, wal_only_inventory_rows)
            wal_reconstructed_entries = reconstruct_wal_only_canonical_entries(
                wal_files,
                candidate_rids={str(row.get("rid") or "") for row in wal_only_inventory_rows},
                instrument_context=config.get("instruments") or {},
            )
            reconstructed_rids = {entry.rid for entry in wal_reconstructed_entries}
            wal_unreconstructed_inventory_rows = [
                row for row in wal_only_inventory_rows if str(row.get("rid") or "") not in reconstructed_rids
            ]
            if wal_reconstructed_entries:
                wal_runtime_root = str((workspace_root / "ops" / "wal").resolve(strict=False))
                serializable_sources.append(
                    {
                        "runtime_root": wal_runtime_root,
                        "source_kind": "wal_fallback",
                        "source_label": "wal_fallback",
                        "support_score": 0,
                        "has_aurora_core": False,
                        "has_trade_lifecycle": False,
                        "has_execution_lifecycle_stats": False,
                        "has_regime_confidence_audit": False,
                        "canonical_entries_raw": len(wal_reconstructed_entries),
                        "unresolved_order_rows": 0,
                        "retained_rows": 0,
                        "core_regime_rows": 0,
                        "core_log_offset_ms": "",
                        "selected_entries": len(wal_reconstructed_entries),
                        "duplicate_entries_dropped": 0,
                    }
                )
                for entry in wal_reconstructed_entries:
                    identity_key = canonical_entry_identity(entry)
                    wal_info = {
                        "identity_key": identity_key,
                        "entry": entry,
                        "source": {
                            "runtime_root": wal_runtime_root,
                            "source_kind": "wal_fallback",
                            "source_label": "wal_fallback",
                        },
                        "candidate_count": 1,
                        "duplicate_count": 0,
                    }
                    selected_infos.append(wal_info)
                    selected_info_by_identity[identity_key] = wal_info
                    selected_entries.append(entry)
                    entry_inventory_rows.append(
                        {
                            "identity_key": identity_key,
                            "symbol": entry.symbol,
                            "side": entry.side,
                            "entry_ts_ms": entry.entry_ts_ms,
                            "selected_runtime_root": wal_runtime_root,
                            "selected_source_kind": "wal_fallback",
                            "selected_source_label": "wal_fallback",
                            "candidate_count": 1,
                            "duplicate_count": 0,
                            "candidate_runtime_roots": wal_runtime_root,
                            "historical_geometry_complete": "true"
                            if entry.historical_target_price is not None and entry.historical_stop_price is not None
                            else "false",
                            "historical_geometry_source": entry.historical_geometry_source or "",
                        }
                    )
        else:
            wal_unreconstructed_inventory_rows = []
    else:
        wal_unreconstructed_inventory_rows = []

    source_headers = list(serializable_sources[0].keys())
    write_csv(report_root / "history_source_inventory.csv",
              source_headers, serializable_sources)
    entry_inventory_headers = list(entry_inventory_rows[0].keys())
    write_csv(report_root / "history_entry_inventory.csv",
              entry_inventory_headers, entry_inventory_rows)

    selected_entry_rows: list[dict[str, Any]] = []
    for info in selected_infos:
        entry = info["entry"]
        identity_key = canonical_entry_identity(entry)
        row = entry.to_row()
        row.update(
            {
                "inventory_identity_key": identity_key,
                "inventory_source_kind": info["source"].get("source_kind") or "",
                "inventory_source_label": info["source"].get("source_label") or "",
                "inventory_runtime_root": info["source"].get("runtime_root") or "",
                "inventory_candidate_count": info.get("candidate_count") or 1,
                "inventory_duplicate_count": info.get("duplicate_count") or 0,
            }
        )
        selected_entry_rows.append(row)
    selected_entry_headers = list(selected_entry_rows[0].keys())
    write_csv(report_root / "historical_canonical_entries.csv",
              selected_entry_headers, selected_entry_rows)
    (report_root / "historical_canonical_entries.json").write_text(
        json.dumps(selected_entry_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    wal_inventory_summary = {
        "enabled": bool(include_wal),
        "wal_files": len(wal_files),
        "open_rids": len(wal_inventory_rows),
        "matched_open_rids": len(wal_inventory_rows) - len(wal_unreconstructed_inventory_rows),
        "wal_only_open_rids": len(wal_unreconstructed_inventory_rows),
        "wal_reconstructed_entries": len(wal_reconstructed_entries),
        "wal_only_open_rids_before_fallback": len(wal_only_inventory_rows),
        "wal_only_open_rids_preview": [row.get("rid") for row in wal_unreconstructed_inventory_rows[:20]],
    }

    inventory_summary = {
        "runtime_sources_discovered": len(runtime_sources),
        "runtime_sources_used": len(serializable_sources),
        "raw_canonical_entries": raw_entry_count,
        "unique_canonical_entries": unique_entry_count,
        "duplicate_entries_dropped": duplicate_entries_dropped,
    }

    if wal_unreconstructed_inventory_rows:
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace_root": str(workspace_root),
            "report_root": str(report_root),
            "strict": strict,
            "target_roi_pcts": [float(item) for item in target_roi_pcts],
            "horizon_modes": [str(item) for item in horizon_modes],
            "inventory": inventory_summary,
            "sources": serializable_sources,
            "wal_inventory": wal_inventory_summary,
            "status": "failed_wal_entry_gap",
        }
        write_json(report_root / "run_manifest.json", manifest)
        (report_root / "report.md").write_text(
            _build_history_report([], manifest),
            encoding="utf-8",
        )
        return manifest

    resolved_recorder_roots = _resolve_recorder_roots(
        workspace_root, recorder_roots)
    try:
        coverage_result = preflight_1m_coverage(
            workspace_root,
            selected_entries,
            report_root,
            resolved_recorder_roots,
            strict=strict,
        )
    except CandleCoverageError as exc:
        coverage_result = exc.result
        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "workspace_root": str(workspace_root),
            "report_root": str(report_root),
            "strict": strict,
            "target_roi_pcts": [float(item) for item in target_roi_pcts],
            "horizon_modes": [str(item) for item in horizon_modes],
            "inventory": inventory_summary,
            "sources": serializable_sources,
            "wal_inventory": wal_inventory_summary,
            "candle_coverage": {
                "strict_1m_ok": coverage_result.strict_1m_ok,
                "required_windows": len(coverage_result.required_windows),
                "resolved_recorder_roots": [str(path) for path in coverage_result.resolved_recorder_roots],
            },
            "status": "failed_strict_candle_coverage",
        }
        write_json(report_root / "run_manifest.json", manifest)
        (report_root / "report.md").write_text(
            _build_history_report([], manifest),
            encoding="utf-8",
        )
        return manifest
    candles_by_symbol = load_1m_candles(
        workspace_root, resolved_recorder_roots)
    base_runtime_root = runtime_root or (workspace_root / "logs")
    runtime = ScenarioRuntime(
        workspace_root=workspace_root,
        runtime_root=base_runtime_root.resolve(strict=False),
        report_root=report_root,
        config=config,
        candles_by_symbol=candles_by_symbol,
        strict=strict,
    )

    trade_rows: list[dict[str, Any]] = []
    for entry in selected_entries:
        identity_key = canonical_entry_identity(entry)
        source_info = selected_info_by_identity[identity_key]
        for target_roi_pct in target_roi_pcts:
            for horizon_mode in horizon_modes:
                exit_event, extras = target_roi_exit(
                    entry,
                    runtime,
                    float(target_roi_pct),
                    horizon_mode=str(horizon_mode),
                )
                row = materialize_trade_result(
                    "target_roi_replay",
                    entry,
                    runtime,
                    exit_event,
                    extras,
                )
                context = extras.get("target_roi_context") or {}
                row.update(
                    {
                        "target_net_roi_pct": float(target_roi_pct),
                        "horizon_mode": str(horizon_mode),
                        "target_hit": extras.get("target_hit", "false"),
                        "historical_target_price": entry.historical_target_price if entry.historical_target_price is not None else "",
                        "historical_stop_price": entry.historical_stop_price if entry.historical_stop_price is not None else "",
                        "historical_geometry_source": entry.historical_geometry_source or "",
                        "historical_round_trip_fee_bps": entry.historical_round_trip_fee_bps if entry.historical_round_trip_fee_bps is not None else "",
                        "target_gross_roi_pct": context.get("target_gross_roi_pct", ""),
                        "target_move_pct": context.get("target_move_pct", ""),
                        "original_sl_move_pct": context.get("original_sl_move_pct", ""),
                        "original_sl_net_roi_pct": context.get("original_sl_net_roi_pct", ""),
                        "rr_vs_original_sl": context.get("rr_vs_original_sl", ""),
                        "inventory_identity_key": identity_key,
                        "inventory_source_kind": source_info["source"].get("source_kind") or "",
                        "inventory_source_label": source_info["source"].get("source_label") or "",
                        "inventory_runtime_root": source_info["source"].get("runtime_root") or "",
                        "inventory_candidate_count": source_info.get("candidate_count") or 1,
                        "inventory_duplicate_count": source_info.get("duplicate_count") or 0,
                    }
                )
                trade_rows.append(row)

    summary_by_target_horizon = _group_summary(
        trade_rows, "target_net_roi_pct", "horizon_mode")
    summary_by_symbol = _group_summary(
        trade_rows, "symbol", "target_net_roi_pct", "horizon_mode")
    summary_by_source = _group_summary(
        trade_rows,
        "inventory_source_label",
        "target_net_roi_pct",
        "horizon_mode",
    )
    unresolved_geometry_rows = [
        row for row in trade_rows if row.get("exit_reason") == "target_roi_unresolved"
    ]

    trade_headers = list(trade_rows[0].keys()) if trade_rows else []
    summary_headers = list(
        summary_by_target_horizon[0].keys()) if summary_by_target_horizon else []
    summary_symbol_headers = list(
        summary_by_symbol[0].keys()) if summary_by_symbol else []
    summary_source_headers = list(
        summary_by_source[0].keys()) if summary_by_source else []
    if trade_rows:
        write_csv(report_root / "target_roi_trade_results.csv",
                  trade_headers, trade_rows)
    if summary_by_target_horizon:
        write_csv(
            report_root / "target_roi_summary_by_target_horizon.csv",
            summary_headers,
            summary_by_target_horizon,
        )
    if summary_by_symbol:
        write_csv(
            report_root / "target_roi_summary_by_symbol.csv",
            summary_symbol_headers,
            summary_by_symbol,
        )
    if summary_by_source:
        write_csv(
            report_root / "target_roi_summary_by_source.csv",
            summary_source_headers,
            summary_by_source,
        )
    if unresolved_geometry_rows:
        write_csv(
            report_root / "target_roi_unresolved_geometry.csv",
            trade_headers,
            unresolved_geometry_rows,
        )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "report_root": str(report_root),
        "strict": strict,
        "target_roi_pcts": [float(item) for item in target_roi_pcts],
        "horizon_modes": [str(item) for item in horizon_modes],
        "inventory": inventory_summary,
        "sources": serializable_sources,
        "wal_inventory": wal_inventory_summary,
        "resolved_recorder_roots": [str(path) for path in resolved_recorder_roots],
        "candle_coverage": {
            "strict_1m_ok": coverage_result.strict_1m_ok,
            "required_windows": len(coverage_result.required_windows),
        },
        "result_rows": len(trade_rows),
        "unresolved_geometry_rows": len(unresolved_geometry_rows),
        "status": "ok",
    }
    write_json(report_root / "run_manifest.json", manifest)
    write_json(
        report_root / "target_roi_summary.json",
        {
            "by_target_horizon": summary_by_target_horizon,
            "by_symbol": summary_by_symbol,
            "by_source": summary_by_source,
        },
    )
    (report_root / "report.md").write_text(
        _build_history_report(summary_by_target_horizon, manifest),
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--runtime-root", default="logs")
    parser.add_argument("--report-root")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--include-frozen",
                        dest="include_frozen", action="store_true")
    parser.add_argument("--no-include-frozen",
                        dest="include_frozen", action="store_false")
    parser.add_argument("--include-wal", dest="include_wal",
                        action="store_true")
    parser.add_argument("--no-include-wal",
                        dest="include_wal", action="store_false")
    parser.add_argument("--extra-runtime-root", action="append")
    parser.add_argument("--wal-path", action="append")
    parser.add_argument("--recorder-root", action="append")
    parser.add_argument("--target-roi-pcts", default="7,8,9,10")
    parser.add_argument("--horizon-modes",
                        default="actual_close_window,fixed_24h_window")
    parser.add_argument("--strict", dest="strict", action="store_true")
    parser.add_argument("--no-strict", dest="strict", action="store_false")
    parser.set_defaults(strict=True, include_frozen=True, include_wal=True)
    args = parser.parse_args(argv)

    workspace_root = Path(args.workspace_root).resolve(strict=False)
    runtime_root = Path(args.runtime_root)
    if not runtime_root.is_absolute():
        runtime_root = (workspace_root / runtime_root).resolve(strict=False)
    default_report_root = (
        "reports/target_roi_history_replay"
        if args.history
        else "reports/target_roi_runtime_replay"
    )
    report_root = Path(args.report_root or default_report_root)
    if not report_root.is_absolute():
        report_root = (workspace_root / report_root).resolve(strict=False)

    if args.history:
        manifest = run_target_roi_history_replay(
            workspace_root=workspace_root,
            runtime_root=runtime_root,
            report_root=report_root,
            extra_runtime_roots=args.extra_runtime_root,
            include_frozen=bool(args.include_frozen),
            include_wal=bool(args.include_wal),
            wal_paths=args.wal_path,
            recorder_roots=args.recorder_root,
            target_roi_pcts=_parse_csv_floats(args.target_roi_pcts),
            horizon_modes=_parse_csv_strings(args.horizon_modes),
            strict=bool(args.strict),
        )
    else:
        manifest = run_target_roi_replay(
            workspace_root=workspace_root,
            runtime_root=runtime_root,
            report_root=report_root,
            recorder_roots=args.recorder_root,
            target_roi_pcts=_parse_csv_floats(args.target_roi_pcts),
            horizon_modes=_parse_csv_strings(args.horizon_modes),
            strict=bool(args.strict),
        )
    print(f"status={manifest['status']}")
    print(f"report_root={manifest['report_root']}")
    print(f"result_rows={manifest.get('result_rows', 0)}")
    return 0 if manifest["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
