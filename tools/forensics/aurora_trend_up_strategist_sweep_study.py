#!/usr/bin/env python3
"""Research-only Aurora TREND_UP strategist sweep study."""
from __future__ import annotations

import argparse
import csv
import dataclasses
import decimal
import glob
import hashlib
import json
import math
import statistics
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import OperationalMode
from apps.reference.domains.decision_making.primitives.operational_mode import ModeManager
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
    SideBiasState,
)
from tools.calibration.calibrate_aurora_thresholds import _build_shield_cascade


TF_SEC = 300
TF_MS = TF_SEC * 1000
BASELINE_SENSITIVITY = 1.50
BASELINE_STRATEGIST_WEIGHT = 0.15
BASELINE_STRATEGIST_SMA = 200
BASELINE_WEIGHTS = {
    "tactician": 0.60,
    "operator": 0.25,
    "strategist": 0.15,
}
SENSITIVITY_LADDER = [1.40, 1.30, 1.20, 1.05, 0.90, 0.75]
WEIGHT_LADDER = [0.14, 0.13, 0.12, 0.11, 0.10, 0.09]
SMA_LADDER = [190, 180, 170, 160, 150, 140]
PROMISING_FALSE_BUY_MAX = 0.05
PROMISING_SELL_REDUCTION_MIN = 0.20
CHURN_MULT_MAX = 1.5
SPILLOVER_TREND_DOWN_BUY_MAX = 0.05
SPILLOVER_TREND_DOWN_FLIP_MAX = 0.10
PARITY_TOL = 1e-6
PRE_ROLL_BARS = 288
HORIZON_3 = 3
HORIZON_6 = 6


class StudyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecorderPoint:
    symbol: str
    bar_close_ts_ms: int
    timestamp_ms: int
    timestamp_iso: str
    tf_sec: int
    source_file: str
    ready: bool
    not_ready_reasons: str
    open: float
    high: float
    low: float
    close: float
    pillar_tactician: float | None
    pillar_operator: float | None
    pillar_strategist: float | None
    pillar_sum: float | None
    spread_bps: float | None
    volatility_state: float | None
    price_motion_norm: float | None
    macro_resid: float | None
    feat_regime: str | None
    feat_regime_ts_ms: int | None
    regime_join_status: str
    regime_join_mode: str


@dataclass(frozen=True)
class RegimeEvidence:
    symbol: str
    bar_close_ts_ms: int
    regime: str
    confidence: float
    raw_confidence: float | None
    stable_confidence: float | None
    local_timestamp: str
    source_file: str
    line_no: int


@dataclass(frozen=True)
class DecisionEvidence:
    symbol: str
    bar_close_ts_ms: int
    regime: str
    score: float
    decision_score: float
    sizing_score: float
    raw_side: str
    deferred: bool
    defer_reason: str | None
    thr_buy: float | None
    thr_sell: float | None
    shield_mult: float | None
    admission_shield_mult: float | None
    s_linear: float | None
    final_signal_side: str | None
    trace_source_file: str
    trace_line_no: int
    diag_source_file: str | None
    diag_line_no: int | None
    signal_source_file: str | None
    signal_line_no: int | None


@dataclass(frozen=True)
class SideEvidence:
    symbol: str
    bar_close_ts_ms: int
    rid: str
    emitted_side: str | None
    decision_outcome: str | None
    decision_regime: str | None
    decision_confidence: float | None
    shadow_side: str | None
    shadow_why: str | None
    trade_side: str | None
    trade_regime: str | None
    executed_short: bool
    has_shadow_or_trade: bool


@dataclass(frozen=True)
class FrozenWindowSpec:
    start_ts_ms: int
    end_ts_ms: int
    symbols: tuple[str, ...]
    timezone: str
    sources: tuple[str, ...]
    htf_seed_manifest: str | None
    completeness_flags: dict[str, bool]
    latest_common_recorder_ts_ms: int
    chosen_segment_index: int
    segment_bar_count: int
    qualifying_failure_count: int
    parent_segment_start_ts_ms: int
    parent_segment_end_ts_ms: int
    parent_segment_bar_count: int
    latest_failure_ts_ms: int
    selection_mode: str
    refinement_reason: str | None


@dataclass(frozen=True)
class ControlWindowSpec:
    name: str
    target_regime: str
    start_ts_ms: int
    end_ts_ms: int
    segment_bar_count: int
    chosen_segment_index: int


@dataclass(frozen=True)
class ScenarioSpec:
    family: str
    scenario_id: str
    baseline_value: float
    scenario_value: float
    redistribution_rule: str
    htf_seed_ref: str | None


@dataclass(frozen=True)
class CandidateDefinition:
    name: str
    description: str
    thresholds: dict[str, float]


@dataclass(frozen=True)
class CandidateEvaluation:
    name: str
    true_count: int
    false_count: int
    separation_score: float
    mean_true_fwd6_bps: float
    baseline_dependency_abs_corr: float
    selection_score: float


@dataclass(frozen=True)
class ScenarioMetrics:
    family: str
    scenario_id: str
    scenario_value: float
    status: str
    window_points: int
    label_complete_points: int
    sell_active_pct_full: float | None
    neutral_pct_full: float | None
    buy_active_pct_full: float | None
    sell_active_pct_growth: float | None
    neutral_pct_growth: float | None
    buy_active_pct_growth: float | None
    sell_active_pct_non_growth: float | None
    neutral_pct_non_growth: float | None
    buy_active_pct_non_growth: float | None
    mean_distance_to_buy: float | None
    median_distance_to_buy: float | None
    p90_distance_to_buy: float | None
    mean_sell_depth: float | None
    median_sell_depth: float | None
    p90_sell_depth: float | None
    moved_sell_to_neutral: int
    moved_neutral_to_buy: int
    buy_during_growth_pct: float | None
    growth_captured_as_buy_pct: float | None
    false_buy_outside_growth_pct: float | None
    missed_buy_inside_growth_pct: float | None
    side_flip_count: int
    churn_rate: float
    oscillation_flag: bool
    baseline_sell_to_neutral_delta: int
    baseline_neutral_to_buy_delta: int
    promising: bool
    dangerous: bool
    blocked_reason: str | None = None
    spillover_risk: str | None = None


@dataclass
class SideAuditAccumulator:
    symbol: str
    bar_close_ts_ms: int | None = None
    rid: str | None = None
    emitted_side: str | None = None
    decision_outcome: str | None = None
    decision_regime: str | None = None
    decision_confidence: float | None = None
    shadow_side: str | None = None
    shadow_why: str | None = None
    trade_side: str | None = None
    trade_regime: str | None = None
    executed_short: bool = False

    def to_side_evidence(self) -> SideEvidence | None:
        if not self.rid or self.bar_close_ts_ms is None:
            return None
        has_shadow_or_trade = bool(self.shadow_side or self.trade_side)
        return SideEvidence(
            symbol=self.symbol,
            bar_close_ts_ms=self.bar_close_ts_ms,
            rid=self.rid,
            emitted_side=self.emitted_side,
            decision_outcome=self.decision_outcome,
            decision_regime=self.decision_regime,
            decision_confidence=self.decision_confidence,
            shadow_side=self.shadow_side,
            shadow_why=self.shadow_why,
            trade_side=self.trade_side,
            trade_regime=self.trade_regime,
            executed_short=self.executed_short,
            has_shadow_or_trade=has_shadow_or_trade,
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministic Aurora TREND_UP strategist sweep study"
    )
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "config" / "aurora"))
    parser.add_argument("--strategies-yaml", default=str(REPO_ROOT / "config" / "aurora" / "strategies.yaml"))
    parser.add_argument("--recorder-dir", default=str(REPO_ROOT / "data" / "recorder"))
    parser.add_argument("--aurora-core-glob", default=str(REPO_ROOT / "logs" / "aurora_core.log*"))
    parser.add_argument("--decision-log-glob", default=str(REPO_ROOT / "logs" / "domain_decision_making.log*"))
    parser.add_argument("--shadow-journal", default=str(REPO_ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl"))
    parser.add_argument("--trade-lifecycle", default=str(REPO_ROOT / "logs" / "trade_lifecycle.jsonl"))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "reports" / "aurora_trend_up_strategist_sweep_2026-04-14"))
    parser.add_argument("--timezone", default="Europe/Kiev")
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--tf-sec", type=int, default=TF_SEC)
    return parser.parse_args(argv)


def _safe_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, float):
        return raw if math.isfinite(raw) else None
    text = str(raw).strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _safe_int(raw: Any) -> int | None:
    value = _safe_float(raw)
    return None if value is None else int(value)


def _safe_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _normalize_recorder_bar_close_ts(raw_ts_ms: int, tf_sec: int) -> int:
    tf_ms = int(tf_sec) * 1000
    if raw_ts_ms % tf_ms == 0:
        return raw_ts_ms
    if raw_ts_ms % 1000 == 999:
        return raw_ts_ms + 1
    return raw_ts_ms


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * q
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    lo_val = ordered[lo]
    hi_val = ordered[hi]
    if lo == hi:
        return lo_val
    weight = rank - lo
    return lo_val + (hi_val - lo_val) * weight


def _mean(values: Iterable[float]) -> float | None:
    values_list = [float(v) for v in values]
    return statistics.fmean(values_list) if values_list else None


def _median(values: Iterable[float]) -> float | None:
    values_list = [float(v) for v in values]
    return statistics.median(values_list) if values_list else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ordered_rotated_paths(pattern: str) -> list[Path]:
    paths = [Path(raw) for raw in glob.glob(pattern)]

    def sort_key(path: Path) -> tuple[int, int, str]:
        name = path.name
        parts = name.rsplit(".", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return (0, -int(parts[1]), name)
        return (1, 0, name)

    return sorted(paths, key=sort_key)


def _iso_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).isoformat()


def _render_num(value: float | int | None, digits: int = 6) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}f}"


def _render_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100.0:.2f}%"


def _json_default(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Unsupported JSON type: {type(obj)!r}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _parse_aurora_symbols(strategies_yaml: Path) -> list[str]:
    raw = yaml.safe_load(strategies_yaml.read_text(encoding="utf-8")) or {}
    assignments = raw.get("assignments") or {}
    out: list[str] = []
    for symbol, strategies in assignments.items():
        if isinstance(strategies, list) and "aurora" in [str(item) for item in strategies]:
            out.append(str(symbol))
    if not out:
        raise StudyError("No Aurora symbols found in strategies.yaml assignments")
    return sorted(out)


def _load_typed_config(config_dir: Path) -> Any:
    loader = ConfigLoader(config_dir=config_dir)
    return loader.load_config()


def _resolve_symbol_thresholds(typed_config: Any, symbol: str) -> tuple[decimal.Decimal, dict[str, float]]:
    aurora = typed_config.strategies.aurora
    decision_cfg = aurora.decision
    asset_cfg = aurora.assets[symbol]
    threshold = decimal.Decimal(str(decision_cfg.signal_threshold))
    signal_threshold_cfg = getattr(asset_cfg, "signal_threshold", None)
    if signal_threshold_cfg is not None and getattr(signal_threshold_cfg, "enabled", False):
        threshold = decimal.Decimal(str(signal_threshold_cfg.value))
    regime_thresholds = dict(
        getattr(asset_cfg, "regime_thresholds", None)
        or getattr(decision_cfg, "regime_threshold_multipliers", {})
    )
    return threshold, regime_thresholds


def _load_recorder_points(
    recorder_dir: Path,
    symbols: Sequence[str],
    tf_sec: int,
) -> tuple[dict[str, dict[int, RecorderPoint]], dict[str, list[RecorderPoint]], set[Path]]:
    point_map: dict[str, dict[int, RecorderPoint]] = {symbol: {} for symbol in symbols}
    point_series: dict[str, list[RecorderPoint]] = {symbol: [] for symbol in symbols}
    used_files: set[Path] = set()
    day_dirs = sorted([p for p in recorder_dir.iterdir() if p.is_dir()], key=lambda p: p.name)
    for day_dir in day_dirs:
        for symbol in symbols:
            csv_path = day_dir / f"{symbol}_{tf_sec}.csv"
            if not csv_path.is_file():
                continue
            used_files.add(csv_path)
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    raw_ts = _safe_int(row.get("feat_bar_close_ts") or row.get("timestamp"))
                    close = _safe_float(row.get("close"))
                    open_price = _safe_float(row.get("open"))
                    high = _safe_float(row.get("high"))
                    low = _safe_float(row.get("low"))
                    if raw_ts is None or close is None or open_price is None or high is None or low is None:
                        continue
                    bar_close_ts_ms = _normalize_recorder_bar_close_ts(raw_ts, tf_sec)
                    point = RecorderPoint(
                        symbol=symbol,
                        bar_close_ts_ms=bar_close_ts_ms,
                        timestamp_ms=_safe_int(row.get("timestamp")) or raw_ts,
                        timestamp_iso=str(row.get("datetime") or ""),
                        tf_sec=int(_safe_int(row.get("tf_sec")) or tf_sec),
                        source_file=str(csv_path),
                        ready=_safe_bool(row.get("ready")),
                        not_ready_reasons=str(row.get("not_ready_reasons") or ""),
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        pillar_tactician=_safe_float(row.get("feat_pillar_tactician")),
                        pillar_operator=_safe_float(row.get("feat_pillar_operator")),
                        pillar_strategist=_safe_float(row.get("feat_pillar_strategist")),
                        pillar_sum=_safe_float(row.get("feat_pillar_sum")),
                        spread_bps=_safe_float(row.get("feat_spread_bps")),
                        volatility_state=_safe_float(row.get("feat_volatility_state")),
                        price_motion_norm=_safe_float(row.get("pm_norm")),
                        macro_resid=_safe_float(row.get("feat_macro_resid")),
                        feat_regime=(str(row.get("feat_regime")) if row.get("feat_regime") else None),
                        feat_regime_ts_ms=_safe_int(row.get("feat_regime_ts_ms")),
                        regime_join_status=str(row.get("regime_join_status") or ""),
                        regime_join_mode=str(row.get("regime_join_mode") or ""),
                    )
                    point_map[symbol][bar_close_ts_ms] = point
                    point_series[symbol].append(point)
    for symbol in symbols:
        point_series[symbol].sort(key=lambda item: item.bar_close_ts_ms)
    return point_map, point_series, used_files


def _parse_aurora_core_logs(
    log_paths: Sequence[Path],
    symbols: Sequence[str],
) -> tuple[dict[tuple[str, int], RegimeEvidence], dict[tuple[str, int], DecisionEvidence], set[Path]]:
    import re

    regime_map: dict[tuple[str, int], RegimeEvidence] = {}
    decision_partial: dict[tuple[str, int], dict[str, Any]] = {}
    used_files: set[Path] = set()
    symbols_set = set(symbols)
    last_bar_ts_by_symbol: dict[str, int] = {}

    audit_re = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[(?P<symbol>[A-Z0-9_]+)\]\s+REGIME_AUDIT bar_close bar_ts=(?P<bar_ts>\d+)\s+tf=(?P<tf>\d+)\s+regime=(?P<regime>[A-Z_]+).*?raw_conf=(?P<raw_conf>[-+0-9.]+)\s+stable_conf=(?P<stable_conf>[-+0-9.]+)\s+emitted_conf=(?P<conf>[-+0-9.]+)"
    )
    trace_re = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[(?P<symbol>[A-Z0-9_]+)\]\s+QUADRATIC_DECISION_TRACE\s+score=(?P<score>[-+0-9.eE]+)\s+decision_score=(?P<decision>[-+0-9.eE]+)\s+sizing_score=(?P<sizing>[-+0-9.eE]+)\s+side=(?P<side>[a-z]*)\s+deferred=(?P<deferred>True|False)\s+regime=(?P<regime>[A-Z_]+)"
    )
    diag_re = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[(?P<symbol>[A-Z0-9_]+)\]\s+KERNEL_DIAG:.*?s_linear=(?P<s_linear>[-+0-9.eE]+)\s+decision_score=(?P<decision>[-+0-9.eE]+)\s+sizing_score=(?P<sizing>[-+0-9.eE]+)\s+shield_mult=(?P<shield>[-+0-9.eE]+)\s+admission_shield_mult=(?P<ashield>[-+0-9.eE]+)\s+deferred=(?P<deferred>True|False)\s+defer_reason=(?P<reason>[^ ]+)\s+side=(?P<side>[a-z]*)\s+thr_buy=(?P<thr_buy>[-+0-9.eE]+)\s+thr_sell=(?P<thr_sell>[-+0-9.eE]+)"
    )
    signal_re = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?\[(?P<symbol>[A-Z0-9_]+)\]\s+SIGNAL:\s+(?P<side>BUY|SELL)\s+score=(?P<score>[-+0-9.eE]+)\s+\(thr_buy=(?P<thr_buy>[-+0-9.eE]+),\s+thr_sell=(?P<thr_sell>[-+0-9.eE]+)\)"
    )

    for path in log_paths:
        used_files.add(path)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                if "aurora_handler.aurora" not in line and "regime_detector" not in line:
                    continue
                match = audit_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol not in symbols_set:
                        continue
                    bar_ts = int(match.group("bar_ts"))
                    regime_map[(symbol, bar_ts)] = RegimeEvidence(
                        symbol=symbol,
                        bar_close_ts_ms=bar_ts,
                        regime=match.group("regime"),
                        confidence=float(match.group("conf")),
                        raw_confidence=float(match.group("raw_conf")),
                        stable_confidence=float(match.group("stable_conf")),
                        local_timestamp=match.group("ts"),
                        source_file=str(path),
                        line_no=line_no,
                    )
                    last_bar_ts_by_symbol[symbol] = bar_ts
                    continue
                match = trace_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol not in symbols_set or symbol not in last_bar_ts_by_symbol:
                        continue
                    bar_ts = last_bar_ts_by_symbol[symbol]
                    rec = decision_partial.setdefault((symbol, bar_ts), {})
                    rec.update(
                        {
                            "symbol": symbol,
                            "bar_close_ts_ms": bar_ts,
                            "regime": match.group("regime"),
                            "score": float(match.group("score")),
                            "decision_score": float(match.group("decision")),
                            "sizing_score": float(match.group("sizing")),
                            "raw_side": match.group("side"),
                            "deferred": match.group("deferred") == "True",
                            "trace_source_file": str(path),
                            "trace_line_no": line_no,
                        }
                    )
                    continue
                match = diag_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol not in symbols_set or symbol not in last_bar_ts_by_symbol:
                        continue
                    bar_ts = last_bar_ts_by_symbol[symbol]
                    rec = decision_partial.setdefault((symbol, bar_ts), {})
                    rec.update(
                        {
                            "symbol": symbol,
                            "bar_close_ts_ms": bar_ts,
                            "s_linear": float(match.group("s_linear")),
                            "thr_buy": float(match.group("thr_buy")),
                            "thr_sell": float(match.group("thr_sell")),
                            "shield_mult": float(match.group("shield")),
                            "admission_shield_mult": float(match.group("ashield")),
                            "defer_reason": None if match.group("reason") == "-" else match.group("reason"),
                            "diag_source_file": str(path),
                            "diag_line_no": line_no,
                        }
                    )
                    continue
                match = signal_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol not in symbols_set or symbol not in last_bar_ts_by_symbol:
                        continue
                    bar_ts = last_bar_ts_by_symbol[symbol]
                    rec = decision_partial.setdefault((symbol, bar_ts), {})
                    rec.update(
                        {
                            "symbol": symbol,
                            "bar_close_ts_ms": bar_ts,
                            "final_signal_side": match.group("side").lower(),
                            "signal_source_file": str(path),
                            "signal_line_no": line_no,
                        }
                    )

    decision_map: dict[tuple[str, int], DecisionEvidence] = {}
    for key, payload in decision_partial.items():
        required = {
            "symbol",
            "bar_close_ts_ms",
            "regime",
            "score",
            "decision_score",
            "sizing_score",
            "raw_side",
            "deferred",
            "trace_source_file",
            "trace_line_no",
        }
        if not required.issubset(payload.keys()):
            continue
        decision_map[key] = DecisionEvidence(
            symbol=str(payload["symbol"]),
            bar_close_ts_ms=int(payload["bar_close_ts_ms"]),
            regime=str(payload["regime"]),
            score=float(payload["score"]),
            decision_score=float(payload["decision_score"]),
            sizing_score=float(payload["sizing_score"]),
            raw_side=str(payload["raw_side"]),
            deferred=bool(payload["deferred"]),
            defer_reason=payload.get("defer_reason"),
            thr_buy=payload.get("thr_buy"),
            thr_sell=payload.get("thr_sell"),
            shield_mult=payload.get("shield_mult"),
            admission_shield_mult=payload.get("admission_shield_mult"),
            s_linear=payload.get("s_linear"),
            final_signal_side=payload.get("final_signal_side"),
            trace_source_file=str(payload["trace_source_file"]),
            trace_line_no=int(payload["trace_line_no"]),
            diag_source_file=payload.get("diag_source_file"),
            diag_line_no=payload.get("diag_line_no"),
            signal_source_file=payload.get("signal_source_file"),
            signal_line_no=payload.get("signal_line_no"),
        )
    return regime_map, decision_map, used_files


def _parse_side_evidence(
    decision_log_paths: Sequence[Path],
    shadow_journal: Path,
    trade_lifecycle: Path,
    symbols: Sequence[str],
) -> tuple[dict[tuple[str, int], SideEvidence], set[Path]]:
    import re

    symbols_set = set(symbols)
    by_rid: dict[str, SideAuditAccumulator] = {}
    used_files: set[Path] = set()
    last_bar_ts_by_symbol: dict[str, int] = {}
    bar_audit_re = re.compile(
        r"\[(?P<symbol>[A-Z0-9_]+)\]\s+REGIME_AUDIT bar_close bar_ts=(?P<bar_ts>\d+)"
    )
    gateway_re = re.compile(
        r"\[(?P<symbol>[A-Z0-9_]+)\]\s+STRATEGY_SIGNAL_GATEWAY:\s+Processing\s+(?P<side>BUY|SELL)\s+signal\s+rid=(?P<rid>aurora_[A-Z0-9_]+_\d+)\s+strategy_id=aurora"
    )
    decision_re = re.compile(
        r"\[(?P<symbol>[A-Z0-9_]+)\]\s+REGIME_AUDIT decision rid=(?P<rid>aurora_[A-Z0-9_]+_\d+)\s+strategy=aurora\s+outcome=(?P<outcome>[A-Z]+)\s+regime=(?P<regime>[A-Z_]+)\s+conf=(?P<conf>[-+0-9.eE]+).*?bar_ts=(?P<bar_ts>\d+)"
    )
    for path in decision_log_paths:
        used_files.add(path)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = bar_audit_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol in symbols_set:
                        last_bar_ts_by_symbol[symbol] = int(match.group("bar_ts"))
                    continue
                match = gateway_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol not in symbols_set:
                        continue
                    rid = match.group("rid")
                    acc = by_rid.setdefault(rid, SideAuditAccumulator(symbol=symbol, rid=rid))
                    acc.emitted_side = match.group("side").lower()
                    if acc.bar_close_ts_ms is None and symbol in last_bar_ts_by_symbol:
                        acc.bar_close_ts_ms = last_bar_ts_by_symbol[symbol]
                    continue
                match = decision_re.search(line)
                if match:
                    symbol = match.group("symbol")
                    if symbol not in symbols_set:
                        continue
                    rid = match.group("rid")
                    acc = by_rid.setdefault(rid, SideAuditAccumulator(symbol=symbol, rid=rid))
                    acc.bar_close_ts_ms = int(match.group("bar_ts"))
                    acc.decision_outcome = match.group("outcome")
                    acc.decision_regime = match.group("regime")
                    acc.decision_confidence = float(match.group("conf"))

    if shadow_journal.is_file():
        used_files.add(shadow_journal)
        with shadow_journal.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = payload.get("rid")
                symbol = payload.get("symbol")
                if not rid or not symbol or symbol not in symbols_set or not str(rid).startswith("aurora_"):
                    continue
                if payload.get("event_name") != "EVT:TRADE_INTENT_PROPOSED":
                    continue
                acc = by_rid.setdefault(str(rid), SideAuditAccumulator(symbol=str(symbol), rid=str(rid)))
                acc.shadow_side = (str(payload.get("side")).lower() if payload.get("side") else None)
                why = payload.get("payload_fragment", {}).get("why")
                if isinstance(why, list):
                    acc.shadow_why = " | ".join(str(item) for item in why[:5])
                elif isinstance(why, str):
                    acc.shadow_why = why

    if trade_lifecycle.is_file():
        used_files.add(trade_lifecycle)
        with trade_lifecycle.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = payload.get("rid")
                symbol = payload.get("symbol")
                if not rid or not symbol or symbol not in symbols_set:
                    continue
                if payload.get("strategy_id") != "aurora":
                    continue
                acc = by_rid.setdefault(str(rid), SideAuditAccumulator(symbol=str(symbol), rid=str(rid)))
                side = payload.get("side")
                if side:
                    acc.trade_side = str(side)
                    if str(side).upper() == "SHORT":
                        acc.executed_short = True
                regime = payload.get("regime")
                if regime:
                    acc.trade_regime = str(regime)

    by_bar: dict[tuple[str, int], SideEvidence] = {}
    for acc in by_rid.values():
        ev = acc.to_side_evidence()
        if ev is not None:
            by_bar[(ev.symbol, ev.bar_close_ts_ms)] = ev
    return by_bar, used_files


def _compute_common_recorder_timestamps(
    recorder_points: dict[str, dict[int, RecorderPoint]],
    symbols: Sequence[str],
) -> list[int]:
    common: set[int] | None = None
    for symbol in symbols:
        timestamps = set(recorder_points[symbol].keys())
        common = timestamps if common is None else common.intersection(timestamps)
    return sorted(common or set())


def _build_completeness_map(
    common_recorder_ts: Sequence[int],
    recorder_points: dict[str, dict[int, RecorderPoint]],
    regime_map: dict[tuple[str, int], RegimeEvidence],
    decision_map: dict[tuple[str, int], DecisionEvidence],
    symbols: Sequence[str],
) -> dict[int, bool]:
    completeness: dict[int, bool] = {}
    for bar_ts in common_recorder_ts:
        ok = True
        for symbol in symbols:
            if bar_ts not in recorder_points[symbol]:
                ok = False
                break
            if (symbol, bar_ts) not in regime_map:
                ok = False
                break
            if (symbol, bar_ts) not in decision_map:
                ok = False
                break
        completeness[bar_ts] = ok
    return completeness


def _build_complete_segments(
    common_recorder_ts: Sequence[int],
    completeness: dict[int, bool],
    tf_ms: int,
) -> list[list[int]]:
    segments: list[list[int]] = []
    current: list[int] = []
    prev_ts: int | None = None
    for bar_ts in common_recorder_ts:
        if not completeness.get(bar_ts, False):
            if current:
                segments.append(current)
                current = []
            prev_ts = None
            continue
        if prev_ts is None or bar_ts - prev_ts == tf_ms:
            current.append(bar_ts)
        else:
            if current:
                segments.append(current)
            current = [bar_ts]
        prev_ts = bar_ts
    if current:
        segments.append(current)
    return segments


def _segment_has_primary_failure(
    segment: Sequence[int],
    symbols: Sequence[str],
    regime_map: dict[tuple[str, int], RegimeEvidence],
    decision_map: dict[tuple[str, int], DecisionEvidence],
    side_evidence: dict[tuple[str, int], SideEvidence],
) -> tuple[bool, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    for bar_ts in segment:
        for symbol in symbols:
            regime = regime_map[(symbol, bar_ts)]
            decision = decision_map[(symbol, bar_ts)]
            side = side_evidence.get((symbol, bar_ts))
            emitted_sell = decision.final_signal_side == "sell"
            executed_short = bool(side and side.executed_short)
            if regime.regime != "TREND_UP":
                continue
            if not (emitted_sell or executed_short):
                continue
            if side is None or not side.has_shadow_or_trade:
                continue
            failures.append(
                {
                    "timestamp_utc": _iso_utc(bar_ts),
                    "bar_close_ts_ms": int(bar_ts),
                    "symbol": symbol,
                    "regime": regime.regime,
                    "raw_side": decision.raw_side,
                    "final_signal_side": decision.final_signal_side,
                    "rid": side.rid,
                    "shadow_side": side.shadow_side,
                    "trade_side": side.trade_side,
                    "executed_short": side.executed_short,
                }
            )
    return bool(failures), failures


def _choose_latest_failure_segment(
    segments: Sequence[Sequence[int]],
    symbols: Sequence[str],
    regime_map: dict[tuple[str, int], RegimeEvidence],
    decision_map: dict[tuple[str, int], DecisionEvidence],
    side_evidence: dict[tuple[str, int], SideEvidence],
) -> tuple[int, list[int], list[dict[str, Any]]]:
    for reverse_index, segment in enumerate(reversed(list(segments))):
        segment_index = len(segments) - 1 - reverse_index
        has_failure, failures = _segment_has_primary_failure(
            segment=segment,
            symbols=symbols,
            regime_map=regime_map,
            decision_map=decision_map,
            side_evidence=side_evidence,
        )
        if has_failure:
            return segment_index, list(segment), failures
    raise StudyError("No fully reconstructable complete segment with Aurora TREND_UP SELL/SHORT failure was found")


def _build_good_subsegments(
    segment: Sequence[int],
    bad_bar_ts: set[int],
    tf_ms: int,
) -> list[list[int]]:
    subsegments: list[list[int]] = []
    current: list[int] = []
    prev_ts: int | None = None
    for bar_ts in segment:
        if bar_ts in bad_bar_ts:
            if current:
                subsegments.append(current)
                current = []
            prev_ts = None
            continue
        if prev_ts is None or bar_ts - prev_ts == tf_ms:
            current.append(bar_ts)
        else:
            if current:
                subsegments.append(current)
            current = [bar_ts]
        prev_ts = int(bar_ts)
    if current:
        subsegments.append(current)
    return subsegments


def _refine_segment_to_parity_clean_subwindow(
    *,
    segment: Sequence[int],
    failure_rows: Sequence[dict[str, Any]],
    mismatches: Sequence[dict[str, Any]],
    tf_ms: int,
    min_future_bars: int,
) -> tuple[list[int], list[dict[str, Any]], str] | None:
    bad_bar_ts = {
        int(datetime.fromisoformat(str(row["timestamp"])).replace(tzinfo=UTC).timestamp() * 1000)
        for row in mismatches
    }
    if not bad_bar_ts:
        return list(segment), list(failure_rows), "original parity-clean segment"

    good_subsegments = _build_good_subsegments(segment, bad_bar_ts, tf_ms)
    if not good_subsegments:
        return None

    latest_failure_ts = max(int(row["bar_close_ts_ms"]) for row in failure_rows)
    for subsegment in reversed(good_subsegments):
        if latest_failure_ts not in subsegment:
            continue
        failure_idx = subsegment.index(latest_failure_ts)
        if len(subsegment) - failure_idx - 1 < min_future_bars:
            continue
        kept_failures = [row for row in failure_rows if int(row["bar_close_ts_ms"]) in set(subsegment)]
        if not kept_failures:
            continue
        reason = (
            "latest exact-parity clean contiguous subwindow containing the latest qualified TREND_UP SELL/SHORT "
            f"failure with at least {min_future_bars} future bars for growth labeling"
        )
        return list(subsegment), kept_failures, reason

    for subsegment in reversed(good_subsegments):
        sub_failures = [row for row in failure_rows if int(row["bar_close_ts_ms"]) in set(subsegment)]
        if not sub_failures:
            continue
        latest_sub_failure_ts = max(int(row["bar_close_ts_ms"]) for row in sub_failures)
        failure_idx = subsegment.index(latest_sub_failure_ts)
        if len(subsegment) - failure_idx - 1 < min_future_bars:
            continue
        reason = (
            "latest exact-parity clean contiguous subwindow containing a qualified TREND_UP SELL/SHORT "
            f"failure with at least {min_future_bars} future bars for growth labeling"
        )
        return list(subsegment), sub_failures, reason
    return None


def _choose_control_segment(
    name: str,
    target_regimes: Sequence[str],
    segments: Sequence[Sequence[int]],
    symbols: Sequence[str],
    regime_map: dict[tuple[str, int], RegimeEvidence],
) -> ControlWindowSpec | None:
    target_set = set(target_regimes)
    for reverse_index, segment in enumerate(reversed(list(segments))):
        segment_index = len(segments) - 1 - reverse_index
        hit = False
        hit_regime = None
        for bar_ts in segment:
            for symbol in symbols:
                regime = regime_map[(symbol, bar_ts)].regime
                if regime in target_set:
                    hit = True
                    hit_regime = regime
                    break
            if hit:
                break
        if hit and hit_regime is not None:
            return ControlWindowSpec(
                name=name,
                target_regime=hit_regime,
                start_ts_ms=int(segment[0]),
                end_ts_ms=int(segment[-1]),
                segment_bar_count=len(segment),
                chosen_segment_index=segment_index,
            )
    return None


def _weight_scenario_map(new_strategist_weight: float) -> dict[str, float]:
    delta = BASELINE_STRATEGIST_WEIGHT - new_strategist_weight
    base_non_s = BASELINE_WEIGHTS["tactician"] + BASELINE_WEIGHTS["operator"]
    tactician_share = BASELINE_WEIGHTS["tactician"] / base_non_s
    operator_share = BASELINE_WEIGHTS["operator"] / base_non_s
    return {
        "tactician": BASELINE_WEIGHTS["tactician"] + delta * tactician_share,
        "operator": BASELINE_WEIGHTS["operator"] + delta * operator_share,
        "strategist": new_strategist_weight,
    }


def _derive_raw_strategist_signal(baseline_value: float) -> float:
    clamped = max(-0.999999, min(0.999999, baseline_value))
    return math.atanh(clamped) / BASELINE_SENSITIVITY


def _rebuild_strategist_from_sensitivity(baseline_value: float, sensitivity: float) -> float:
    raw = _derive_raw_strategist_signal(baseline_value)
    return math.tanh(raw * sensitivity)


def _compute_point_biserial(binary_flags: Sequence[bool], values: Sequence[float]) -> float:
    pairs = [(1.0 if flag else 0.0, float(value)) for flag, value in zip(binary_flags, values, strict=False)]
    if len(pairs) < 2:
        return 0.0
    xs = [flag for flag, _ in pairs]
    ys = [value for _, value in pairs]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    sum_xy = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    sum_xx = sum((x - mean_x) ** 2 for x in xs)
    sum_yy = sum((y - mean_y) ** 2 for y in ys)
    if sum_xx <= 0.0 or sum_yy <= 0.0:
        return 0.0
    return float(sum_xy / math.sqrt(sum_xx * sum_yy))


def _fetch_klines(rest_url: str, symbol: str, interval: str, limit: int) -> list[list[Any]]:
    path = "/fapi/v1/klines"
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    url = f"{rest_url.rstrip('/')}{path}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "aurora-study/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise StudyError(f"Unexpected klines response for {symbol}/{interval}: {type(payload)!r}")
    return payload


def _freeze_htf_seed(
    out_dir: Path,
    rest_url: str,
    symbols: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], str | None]:
    raw_dir = out_dir / "htf_seed_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, Any]] = {}
    try:
        for symbol in symbols:
            manifest[symbol] = {}
            for interval, limit in (("1d", 260), ("4h", 120)):
                payload = _fetch_klines(rest_url, symbol, interval, limit)
                out_path = raw_dir / f"{symbol}_{interval}.json"
                _write_json(out_path, payload)
                manifest[symbol][interval] = {
                    "file": str(out_path),
                    "row_count": len(payload),
                    "sha256": _sha256_file(out_path),
                    "limit": limit,
                    "rest_url": rest_url,
                    "path": "/fapi/v1/klines",
                    "frozen_at_utc": datetime.now(tz=UTC).isoformat(),
                }
    except Exception as exc:
        manifest["blocked_reason"] = {"message": str(exc)}
        out_path = out_dir / "htf_seed_manifest.json"
        _write_json(out_path, manifest)
        return manifest, None
    out_path = out_dir / "htf_seed_manifest.json"
    _write_json(out_path, manifest)
    return manifest, str(out_path)


def _load_d1_series_from_manifest(
    htf_manifest: dict[str, Any],
) -> dict[str, list[tuple[int, float]]]:
    series: dict[str, list[tuple[int, float]]] = {}
    for symbol, payload in htf_manifest.items():
        if symbol == "blocked_reason":
            continue
        path = Path(payload["1d"]["file"])
        raw = json.loads(path.read_text(encoding="utf-8"))
        d1_series: list[tuple[int, float]] = []
        for item in raw:
            try:
                d1_series.append((int(item[0]), float(item[4])))
            except Exception:
                continue
        d1_series.sort(key=lambda item: item[0])
        series[symbol] = d1_series
    return series


def _utc_day_start_ms(ts_ms: int) -> int:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
    day_start = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
    return int(day_start.timestamp() * 1000)


def _compute_strategist_from_d1(
    d1_series: Sequence[tuple[int, float]],
    bar_close_ts_ms: int,
    sma_period: int,
    sensitivity: float,
    include_current_open_day: bool,
) -> float | None:
    day_start_ms = _utc_day_start_ms(bar_close_ts_ms)
    closes: list[float] = []
    for open_ts_ms, close in d1_series:
        if include_current_open_day:
            if open_ts_ms <= day_start_ms:
                closes.append(close)
        else:
            if open_ts_ms < day_start_ms:
                closes.append(close)
    if len(closes) < sma_period:
        return None
    sma = statistics.fmean(closes[-sma_period:])
    if not math.isfinite(sma) or sma == 0:
        return None
    current_close = closes[-1]
    raw = (current_close - sma) / abs(sma)
    if not math.isfinite(raw):
        return None
    return math.tanh(raw * sensitivity)


def _choose_d1_inclusion_rule(
    d1_series_by_symbol: dict[str, list[tuple[int, float]]],
    frozen_rows: Sequence[dict[str, Any]],
) -> dict[str, bool]:
    decision: dict[str, bool] = {}
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in frozen_rows:
        by_symbol[str(row["symbol"])].append(row)
    for symbol, rows in by_symbol.items():
        series = d1_series_by_symbol.get(symbol)
        if not series:
            raise StudyError(f"Missing D1 seed for symbol {symbol}")
        errors: dict[bool, float] = {False: 0.0, True: 0.0}
        counts: dict[bool, int] = {False: 0, True: 0}
        for include_current in (False, True):
            for row in rows:
                recorded = row.get("pillar_strategist")
                if recorded is None:
                    continue
                computed = _compute_strategist_from_d1(
                    d1_series=series,
                    bar_close_ts_ms=int(row["bar_close_ts_ms"]),
                    sma_period=BASELINE_STRATEGIST_SMA,
                    sensitivity=BASELINE_SENSITIVITY,
                    include_current_open_day=include_current,
                )
                if computed is None:
                    continue
                errors[include_current] += abs(float(recorded) - computed)
                counts[include_current] += 1
        if counts[False] == 0 and counts[True] == 0:
            raise StudyError(f"Could not validate D1 inclusion rule for {symbol}")
        error_prev = errors[False] / max(1, counts[False])
        error_curr = errors[True] / max(1, counts[True])
        decision[symbol] = error_curr < error_prev
    return decision


def _bar_features(
    recorder: RecorderPoint,
    regime: RegimeEvidence,
    pillar_tactician: float,
    pillar_operator: float,
    pillar_strategist: float,
    pillar_sum: float,
) -> dict[str, Any]:
    return {
        "price": recorder.close,
        "high": recorder.high,
        "low": recorder.low,
        "bar_close_ts": regime.bar_close_ts_ms,
        "regime": regime.regime,
        "regime_ts_ms": regime.bar_close_ts_ms,
        "pillar_tactician": pillar_tactician,
        "pillar_operator": pillar_operator,
        "pillar_strategist": pillar_strategist,
        "pillar_sum": pillar_sum,
        "spread_bps": recorder.spread_bps,
        "volatility_state": recorder.volatility_state,
        "price_motion_norm": recorder.price_motion_norm,
        "macro_resid": recorder.macro_resid,
    }


def _build_target_row(
    *,
    family: str,
    scenario_id: str,
    symbol: str,
    bar_close_ts_ms: int,
    regime: RegimeEvidence,
    result: Any,
    pillar_tactician: float,
    pillar_operator: float,
    pillar_strategist: float,
    pillar_sum: float,
    baseline_row: dict[str, Any] | None,
    active_growth_phase: bool,
    active_growth_complete: bool,
    final_side_optional: str | None,
) -> dict[str, Any]:
    final_score = float(getattr(result, "decision_score", result.score))
    raw_side = str(result.side)
    baseline_raw_side = baseline_row["raw_side"] if baseline_row else None
    return {
        "timestamp": _iso_utc(bar_close_ts_ms),
        "bar_close_ts_ms": bar_close_ts_ms,
        "symbol": symbol,
        "regime": regime.regime,
        "regime_confidence": regime.confidence,
        "pillar_tactician": pillar_tactician,
        "pillar_operator": pillar_operator,
        "pillar_strategist": pillar_strategist,
        "pillar_sum": pillar_sum,
        "final_score": final_score,
        "thr_buy": float(result.thr_buy),
        "thr_sell": float(result.thr_sell),
        "raw_side": raw_side,
        "baseline_raw_side": baseline_raw_side,
        "final_side_optional": final_side_optional,
        "active_growth_phase": bool(active_growth_phase),
        "active_growth_complete": bool(active_growth_complete),
        "changed_vs_baseline": raw_side != baseline_raw_side,
        "family": family,
        "scenario_id": scenario_id,
    }


def _replay_window(
    *,
    typed_config: Any,
    symbol: str,
    joined_series: Sequence[dict[str, Any]],
    target_bar_ts_set: set[int],
    scenario: ScenarioSpec,
    d1_series: Sequence[tuple[int, float]] | None,
    d1_inclusion_rule: bool | None,
    logged_final_side_by_bar: dict[int, str | None] | None,
    active_growth_by_bar: dict[int, tuple[bool, bool]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decision_cfg = typed_config.strategies.aurora.decision
    threshold, regime_thresholds = _resolve_symbol_thresholds(typed_config, symbol)
    op_mode = getattr(decision_cfg, "operational_mode", OperationalMode.PARANOID)
    mode_manager = ModeManager(op_mode)
    shield_fn, _memory_shield = _build_shield_cascade(decision_cfg, mode_manager)
    score_multiplier = float(getattr(decision_cfg, "score_multiplier", 1.0))
    geometry_cfg = getattr(decision_cfg, "decision_geometry", None)
    admission_mode = str(getattr(geometry_cfg, "admission_mode", "quadratic"))
    admission_power = (
        float(getattr(geometry_cfg, "admission_power"))
        if getattr(geometry_cfg, "admission_power", None) is not None
        else None
    )
    sizing_mode = str(getattr(geometry_cfg, "sizing_mode", "quadratic"))
    sizing_power = (
        float(getattr(geometry_cfg, "sizing_power"))
        if getattr(geometry_cfg, "sizing_power", None) is not None
        else None
    )
    admission_shield_floor = float(getattr(geometry_cfg, "admission_shield_floor", 0.0) or 0.0)
    neutral_threshold = decimal.Decimal(str(getattr(decision_cfg, "neutral_threshold", "0.05")))
    delta_price_cap_pct = decimal.Decimal(
        str(getattr(getattr(decision_cfg, "signals", None), "delta_price_cap_pct", "0.02"))
    )
    current_side = ""
    all_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    no_bias = SideBiasState(
        buy_count=0,
        sell_count=0,
        window_sec=float(getattr(decision_cfg, "side_bias_window_sec", 420.0)),
        target_ratio=float(getattr(decision_cfg, "side_bias_target_ratio", 0.72)),
        penalty_factor=float(getattr(decision_cfg, "side_bias_penalty_factor", 0.25)),
        min_intents=int(getattr(decision_cfg, "side_bias_min_intents", 18)),
    )

    if scenario.family == "weight":
        scenario_weights = _weight_scenario_map(scenario.scenario_value)
    else:
        scenario_weights = dict(BASELINE_WEIGHTS)

    for item in joined_series:
        recorder = item["recorder"]
        regime = item["regime"]
        baseline_row = item["baseline_row"]
        tactician = recorder.pillar_tactician
        operator = recorder.pillar_operator
        strategist = recorder.pillar_strategist
        if tactician is None or operator is None or strategist is None:
            current_side = ""
            continue
        if scenario.family == "sensitivity":
            strategist = _rebuild_strategist_from_sensitivity(strategist, scenario.scenario_value)
        elif scenario.family == "sma":
            if d1_series is None or d1_inclusion_rule is None:
                raise StudyError(f"SMA scenario {scenario.scenario_id} requested without D1 seed")
            rebuilt = _compute_strategist_from_d1(
                d1_series=d1_series,
                bar_close_ts_ms=recorder.bar_close_ts_ms,
                sma_period=int(scenario.scenario_value),
                sensitivity=BASELINE_SENSITIVITY,
                include_current_open_day=d1_inclusion_rule,
            )
            if rebuilt is None:
                raise StudyError(f"SMA scenario {scenario.scenario_id} could not compute strategist for {symbol} @ {recorder.bar_close_ts_ms}")
            strategist = rebuilt

        pillar_sum = (
            tactician * scenario_weights["tactician"]
            + operator * scenario_weights["operator"]
            + strategist * scenario_weights["strategist"]
        )
        features = _bar_features(
            recorder=recorder,
            regime=regime,
            pillar_tactician=tactician,
            pillar_operator=operator,
            pillar_strategist=strategist,
            pillar_sum=pillar_sum,
        )
        result = QuadraticScoringKernel.compute(
            symbol=symbol,
            features=features,
            warmup_readiness={},
            price=decimal.Decimal(str(recorder.close)),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=threshold,
            regime_name=regime.regime,
            regime_thresholds=regime_thresholds,
            side_bias_state=no_bias,
            direction_strength_cfg={},
            delta_price_cap_pct=delta_price_cap_pct,
            neutral_threshold=neutral_threshold,
            current_side=current_side,
            normalize_mode=str(getattr(getattr(decision_cfg, "signals", None), "normalize_signals_mode", "signed_v2")),
            shield_fn=shield_fn,
            score_multiplier=score_multiplier,
            linear_score=pillar_sum,
            admission_mode=admission_mode,
            admission_power=admission_power,
            sizing_mode=sizing_mode,
            sizing_power=sizing_power,
            admission_shield_floor=admission_shield_floor,
        )
        current_side = str(result.side)
        growth_flag, growth_complete = active_growth_by_bar.get(recorder.bar_close_ts_ms, (False, False))
        final_side_optional = None if logged_final_side_by_bar is None else logged_final_side_by_bar.get(recorder.bar_close_ts_ms)
        row = _build_target_row(
            family=scenario.family,
            scenario_id=scenario.scenario_id,
            symbol=symbol,
            bar_close_ts_ms=recorder.bar_close_ts_ms,
            regime=regime,
            result=result,
            pillar_tactician=tactician,
            pillar_operator=operator,
            pillar_strategist=strategist,
            pillar_sum=pillar_sum,
            baseline_row=baseline_row,
            active_growth_phase=growth_flag,
            active_growth_complete=growth_complete,
            final_side_optional=final_side_optional,
        )
        all_rows.append(row)
        if recorder.bar_close_ts_ms in target_bar_ts_set:
            target_rows.append(row)
    return all_rows, target_rows


def _build_joined_series(
    *,
    symbol: str,
    recorder_points: dict[str, dict[int, RecorderPoint]],
    regime_map: dict[tuple[str, int], RegimeEvidence],
    decision_map: dict[tuple[str, int], DecisionEvidence],
    start_ts_ms: int,
    end_ts_ms: int,
    pre_roll_bars: int,
) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    pre_roll_start = start_ts_ms - pre_roll_bars * TF_MS
    for bar_ts in sorted(recorder_points[symbol].keys()):
        if bar_ts < pre_roll_start or bar_ts > end_ts_ms:
            continue
        recorder = recorder_points[symbol].get(bar_ts)
        regime = regime_map.get((symbol, bar_ts))
        decision = decision_map.get((symbol, bar_ts))
        if recorder is None or regime is None or decision is None:
            continue
        series.append({"recorder": recorder, "regime": regime, "decision": decision, "baseline_row": None})
    return series


def _run_baseline_replay(
    *,
    typed_config: Any,
    symbols: Sequence[str],
    recorder_points: dict[str, dict[int, RecorderPoint]],
    regime_map: dict[tuple[str, int], RegimeEvidence],
    decision_map: dict[tuple[str, int], DecisionEvidence],
    frozen_segment: Sequence[int],
    active_growth_flags: dict[tuple[str, int], tuple[bool, bool]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    baseline_spec = ScenarioSpec(
        family="baseline",
        scenario_id="BASELINE",
        baseline_value=BASELINE_SENSITIVITY,
        scenario_value=BASELINE_SENSITIVITY,
        redistribution_rule="none",
        htf_seed_ref=None,
    )
    all_target_rows: list[dict[str, Any]] = []
    per_symbol_series: dict[str, list[dict[str, Any]]] = {}
    per_symbol_target: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        joined_series = _build_joined_series(
            symbol=symbol,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            start_ts_ms=int(frozen_segment[0]),
            end_ts_ms=int(frozen_segment[-1]),
            pre_roll_bars=PRE_ROLL_BARS,
        )
        target_bar_ts_set = set(frozen_segment)
        logged_final_side = {bar_ts: decision_map[(symbol, bar_ts)].final_signal_side for bar_ts in target_bar_ts_set}
        growth_lookup = {bar_ts: active_growth_flags.get((symbol, bar_ts), (False, False)) for bar_ts in target_bar_ts_set}
        all_rows, target_rows = _replay_window(
            typed_config=typed_config,
            symbol=symbol,
            joined_series=joined_series,
            target_bar_ts_set=target_bar_ts_set,
            scenario=baseline_spec,
            d1_series=None,
            d1_inclusion_rule=None,
            logged_final_side_by_bar=logged_final_side,
            active_growth_by_bar=growth_lookup,
        )
        per_symbol_series[symbol] = all_rows
        per_symbol_target[symbol] = target_rows
        all_target_rows.extend(target_rows)
    all_target_rows.sort(key=lambda row: (row["bar_close_ts_ms"], row["symbol"]))
    baseline_lookup: list[dict[str, Any]] = []
    for row in all_target_rows:
        decision = decision_map[(row["symbol"], row["bar_close_ts_ms"])]
        regime = regime_map[(row["symbol"], row["bar_close_ts_ms"])]
        row["logged_score"] = decision.score
        row["logged_thr_buy"] = decision.thr_buy
        row["logged_thr_sell"] = decision.thr_sell
        row["logged_raw_side"] = decision.raw_side
        row["logged_regime"] = regime.regime
        row["pillar_strategist"] = row["pillar_strategist"]
        baseline_lookup.append(row)
    return baseline_lookup, per_symbol_series, all_target_rows


def _run_scenario_replay(
    *,
    typed_config: Any,
    symbols: Sequence[str],
    recorder_points: dict[str, dict[int, RecorderPoint]],
    regime_map: dict[tuple[str, int], RegimeEvidence],
    decision_map: dict[tuple[str, int], DecisionEvidence],
    frozen_segment: Sequence[int],
    growth_flags: dict[tuple[str, int], tuple[bool, bool]],
    scenario: ScenarioSpec,
    baseline_lookup: dict[tuple[str, int], dict[str, Any]],
    d1_series_by_symbol: dict[str, Sequence[tuple[int, float]]],
    d1_rule_by_symbol: dict[str, bool],
) -> list[dict[str, Any]]:
    scenario_rows: list[dict[str, Any]] = []
    target_bar_ts_set = set(frozen_segment)
    for symbol in symbols:
        joined_series = _build_joined_series(
            symbol=symbol,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            start_ts_ms=int(frozen_segment[0]),
            end_ts_ms=int(frozen_segment[-1]),
            pre_roll_bars=PRE_ROLL_BARS,
        )
        for item in joined_series:
            item["baseline_row"] = baseline_lookup.get((symbol, item["recorder"].bar_close_ts_ms))
        growth_lookup = {bar_ts: growth_flags.get((symbol, bar_ts), (False, False)) for bar_ts in target_bar_ts_set}
        _all_rows, target_rows = _replay_window(
            typed_config=typed_config,
            symbol=symbol,
            joined_series=joined_series,
            target_bar_ts_set=target_bar_ts_set,
            scenario=scenario,
            d1_series=d1_series_by_symbol.get(symbol),
            d1_inclusion_rule=d1_rule_by_symbol.get(symbol),
            logged_final_side_by_bar=None,
            active_growth_by_bar=growth_lookup,
        )
        scenario_rows.extend(target_rows)
    scenario_rows.sort(key=lambda row: (row["bar_close_ts_ms"], row["symbol"]))
    return scenario_rows


def _validate_baseline_parity(
    baseline_rows: Sequence[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]]]:
    mismatches: list[dict[str, Any]] = []
    for row in baseline_rows:
        reason_codes: list[str] = []
        if row["regime"] != row["logged_regime"]:
            reason_codes.append("regime")
        if abs(float(row["final_score"]) - float(row["logged_score"])) > PARITY_TOL:
            reason_codes.append("decision_score")
        if row["raw_side"] != row["logged_raw_side"]:
            reason_codes.append("raw_side")
        if row["thr_buy"] is None or row["logged_thr_buy"] is None or abs(float(row["thr_buy"]) - float(row["logged_thr_buy"])) > PARITY_TOL:
            reason_codes.append("thr_buy")
        if row["thr_sell"] is None or row["logged_thr_sell"] is None or abs(float(row["thr_sell"]) - float(row["logged_thr_sell"])) > PARITY_TOL:
            reason_codes.append("thr_sell")
        if reason_codes:
            mismatches.append(
                {
                    "timestamp": row["timestamp"],
                    "symbol": row["symbol"],
                    "mismatch_fields": ",".join(reason_codes),
                    "replay_score": row["final_score"],
                    "logged_score": row["logged_score"],
                    "replay_raw_side": row["raw_side"],
                    "logged_raw_side": row["logged_raw_side"],
                    "replay_thr_buy": row["thr_buy"],
                    "logged_thr_buy": row["logged_thr_buy"],
                    "replay_thr_sell": row["thr_sell"],
                    "logged_thr_sell": row["logged_thr_sell"],
                }
            )
    return not mismatches, mismatches


def _build_symbol_index(series: Sequence[RecorderPoint]) -> dict[int, int]:
    return {point.bar_close_ts_ms: idx for idx, point in enumerate(series)}


def _future_feature_payload(
    series: Sequence[RecorderPoint],
    index_by_ts: dict[int, int],
    point: RecorderPoint,
) -> dict[str, Any]:
    idx = index_by_ts[point.bar_close_ts_ms]
    close = point.close
    future3 = series[idx + HORIZON_3] if idx + HORIZON_3 < len(series) else None
    future6 = series[idx + HORIZON_6] if idx + HORIZON_6 < len(series) else None
    bullish_next3 = 0
    for step in range(1, HORIZON_3 + 1):
        if idx + step >= len(series):
            break
        prev_close = series[idx + step - 1].close
        curr_close = series[idx + step].close
        if curr_close > prev_close:
            bullish_next3 += 1
    future_slice = series[idx + 1: idx + HORIZON_6 + 1]
    long_mfe_6 = None
    short_benefit_6 = None
    if len(future_slice) == HORIZON_6 and close > 0:
        long_mfe_6 = ((max(item.high for item in future_slice) - close) / close) * 10_000.0
        short_benefit_6 = ((close - min(item.low for item in future_slice)) / close) * 10_000.0
    return {
        "fwd_ret_3_bps": None if future3 is None or close <= 0 else ((future3.close - close) / close) * 10_000.0,
        "fwd_ret_6_bps": None if future6 is None or close <= 0 else ((future6.close - close) / close) * 10_000.0,
        "bullish_closes_next3": bullish_next3 if idx + HORIZON_3 < len(series) else None,
        "long_mfe_6_bps": long_mfe_6,
        "short_benefit_6_bps": short_benefit_6,
    }


def _compute_growth_calibration_thresholds(
    feature_rows: Sequence[dict[str, Any]],
) -> dict[str, float]:
    abs_fwd3 = [abs(float(row["fwd_ret_3_bps"])) for row in feature_rows if row["fwd_ret_3_bps"] is not None]
    abs_fwd6 = [abs(float(row["fwd_ret_6_bps"])) for row in feature_rows if row["fwd_ret_6_bps"] is not None]
    long_mfe = [float(row["long_mfe_6_bps"]) for row in feature_rows if row["long_mfe_6_bps"] is not None]
    thr_r3 = max(12.0, _percentile(abs_fwd3, 0.60) or 12.0)
    thr_r6 = max(18.0, _percentile(abs_fwd6, 0.60) or 18.0)
    thr_mfe = max(15.0, _percentile(long_mfe, 0.60) or 15.0)
    return {"thr_r3_bps": thr_r3, "thr_r6_bps": thr_r6, "thr_mfe_6_bps": thr_mfe}


def _candidate_flag(candidate_name: str, payload: dict[str, Any], thresholds: dict[str, float]) -> bool:
    if candidate_name == "Candidate A":
        return (
            payload["fwd_ret_3_bps"] is not None
            and payload["fwd_ret_6_bps"] is not None
            and payload["fwd_ret_3_bps"] >= thresholds["thr_r3_bps"]
            and payload["fwd_ret_6_bps"] >= thresholds["thr_r6_bps"]
        )
    if candidate_name == "Candidate B":
        return (
            payload["bullish_closes_next3"] is not None
            and payload["fwd_ret_3_bps"] is not None
            and payload["bullish_closes_next3"] >= 2
            and payload["fwd_ret_3_bps"] >= thresholds["thr_r3_bps"]
        )
    if candidate_name == "Candidate C":
        return (
            payload["fwd_ret_3_bps"] is not None
            and payload["long_mfe_6_bps"] is not None
            and payload["short_benefit_6_bps"] is not None
            and payload["fwd_ret_3_bps"] > 0.0
            and payload["long_mfe_6_bps"] >= thresholds["thr_mfe_6_bps"]
            and payload["long_mfe_6_bps"] >= payload["short_benefit_6_bps"] * 1.5
        )
    raise StudyError(f"Unknown candidate label: {candidate_name}")


def _evaluate_growth_candidates(
    frozen_rows: Sequence[dict[str, Any]],
    recorder_series: dict[str, list[RecorderPoint]],
) -> tuple[CandidateDefinition, list[CandidateEvaluation], dict[tuple[str, int], tuple[bool, bool]], list[dict[str, Any]], dict[str, float]]:
    series_index = {symbol: _build_symbol_index(series) for symbol, series in recorder_series.items()}
    point_lookup = {
        (symbol, point.bar_close_ts_ms): point
        for symbol, series in recorder_series.items()
        for point in series
    }
    enriched_rows: list[dict[str, Any]] = []
    for row in frozen_rows:
        symbol = str(row["symbol"])
        payload = _future_feature_payload(recorder_series[symbol], series_index[symbol], point_lookup[(symbol, row["bar_close_ts_ms"])])
        enriched = dict(row)
        enriched.update(payload)
        enriched_rows.append(enriched)

    label_complete = [
        row for row in enriched_rows
        if row["fwd_ret_3_bps"] is not None
        and row["fwd_ret_6_bps"] is not None
        and row["bullish_closes_next3"] is not None
        and row["long_mfe_6_bps"] is not None
        and row["short_benefit_6_bps"] is not None
    ]
    thresholds = _compute_growth_calibration_thresholds(label_complete)
    candidates = [
        CandidateDefinition(name="Candidate A", description="Forward-return reward label on H={3,6} bars", thresholds=dict(thresholds)),
        CandidateDefinition(name="Candidate B", description="Bullish persistence in next 3 bars + cumulative return", thresholds=dict(thresholds)),
        CandidateDefinition(name="Candidate C", description="Long-vs-short payoff asymmetry on H=6 bars", thresholds=dict(thresholds)),
    ]
    candidate_evals: list[CandidateEvaluation] = []
    for candidate in candidates:
        flags = [_candidate_flag(candidate.name, row, candidate.thresholds) for row in label_complete]
        baseline_scores = [float(row["final_score"]) for row in label_complete]
        long_minus_short = [float(row["long_mfe_6_bps"]) - float(row["short_benefit_6_bps"]) for row in label_complete]
        true_values = [metric for flag, metric in zip(flags, long_minus_short, strict=False) if flag]
        false_values = [metric for flag, metric in zip(flags, long_minus_short, strict=False) if not flag]
        true_fwd6 = [float(row["fwd_ret_6_bps"]) for flag, row in zip(flags, label_complete, strict=False) if flag]
        separation = (statistics.fmean(true_values) if true_values else 0.0) - (statistics.fmean(false_values) if false_values else 0.0)
        dependency = abs(_compute_point_biserial(flags, baseline_scores))
        selection_score = separation + 0.25 * (statistics.fmean(true_fwd6) if true_fwd6 else 0.0) - 10.0 * dependency
        candidate_evals.append(
            CandidateEvaluation(
                name=candidate.name,
                true_count=sum(1 for flag in flags if flag),
                false_count=sum(1 for flag in flags if not flag),
                separation_score=separation,
                mean_true_fwd6_bps=statistics.fmean(true_fwd6) if true_fwd6 else 0.0,
                baseline_dependency_abs_corr=dependency,
                selection_score=selection_score,
            )
        )
    candidate_evals.sort(key=lambda item: item.selection_score, reverse=True)
    chosen_name = candidate_evals[0].name
    chosen_candidate = next(candidate for candidate in candidates if candidate.name == chosen_name)
    growth_flags: dict[tuple[str, int], tuple[bool, bool]] = {}
    for row in enriched_rows:
        complete = (
            row["fwd_ret_3_bps"] is not None
            and row["fwd_ret_6_bps"] is not None
            and row["bullish_closes_next3"] is not None
            and row["long_mfe_6_bps"] is not None
            and row["short_benefit_6_bps"] is not None
        )
        growth_flags[(str(row["symbol"]), int(row["bar_close_ts_ms"]))] = (
            _candidate_flag(chosen_candidate.name, row, chosen_candidate.thresholds) if complete else False,
            complete,
        )
    return chosen_candidate, candidate_evals, growth_flags, enriched_rows, thresholds


def _compute_metrics(
    rows: Sequence[dict[str, Any]],
    *,
    baseline_lookup: dict[tuple[str, int], dict[str, Any]],
    family: str,
    scenario_id: str,
    scenario_value: float,
    status: str,
    blocked_reason: str | None = None,
) -> ScenarioMetrics:
    if status != "ok":
        return ScenarioMetrics(
            family=family, scenario_id=scenario_id, scenario_value=scenario_value, status=status,
            window_points=len(rows), label_complete_points=0,
            sell_active_pct_full=None, neutral_pct_full=None, buy_active_pct_full=None,
            sell_active_pct_growth=None, neutral_pct_growth=None, buy_active_pct_growth=None,
            sell_active_pct_non_growth=None, neutral_pct_non_growth=None, buy_active_pct_non_growth=None,
            mean_distance_to_buy=None, median_distance_to_buy=None, p90_distance_to_buy=None,
            mean_sell_depth=None, median_sell_depth=None, p90_sell_depth=None,
            moved_sell_to_neutral=0, moved_neutral_to_buy=0,
            buy_during_growth_pct=None, growth_captured_as_buy_pct=None,
            false_buy_outside_growth_pct=None, missed_buy_inside_growth_pct=None,
            side_flip_count=0, churn_rate=0.0, oscillation_flag=False,
            baseline_sell_to_neutral_delta=0, baseline_neutral_to_buy_delta=0,
            promising=False, dangerous=True, blocked_reason=blocked_reason,
        )

    def occupancy(subset: Sequence[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
        if not subset:
            return None, None, None
        total = len(subset)
        sell = sum(1 for row in subset if row["raw_side"] == "sell")
        neutral = sum(1 for row in subset if row["raw_side"] == "")
        buy = sum(1 for row in subset if row["raw_side"] == "buy")
        return sell / total, neutral / total, buy / total

    growth_rows = [row for row in rows if row["active_growth_complete"] and row["active_growth_phase"]]
    non_growth_rows = [row for row in rows if row["active_growth_complete"] and not row["active_growth_phase"]]
    label_complete_rows = [row for row in rows if row["active_growth_complete"]]
    full_occ = occupancy(rows)
    growth_occ = occupancy(growth_rows)
    non_growth_occ = occupancy(non_growth_rows)
    distance_to_buy = [max(0.0, float(row["thr_buy"]) - float(row["final_score"])) for row in rows]
    sell_depth = [
        max(0.0, (-float(row["thr_sell"])) - float(row["final_score"])) if float(row["final_score"]) <= -float(row["thr_sell"]) else 0.0
        for row in rows
    ]
    moved_sell_to_neutral = 0
    moved_neutral_to_buy = 0
    baseline_sell_to_neutral_delta = 0
    baseline_neutral_to_buy_delta = 0
    for row in rows:
        baseline = baseline_lookup[(row["symbol"], row["bar_close_ts_ms"])]
        if baseline["raw_side"] == "sell" and row["raw_side"] == "":
            moved_sell_to_neutral += 1
            baseline_sell_to_neutral_delta += 1
        if baseline["raw_side"] == "" and row["raw_side"] == "buy":
            moved_neutral_to_buy += 1
            baseline_neutral_to_buy_delta += 1
    complete_buy_rows = [row for row in label_complete_rows if row["raw_side"] == "buy"]
    buy_during_growth_pct = (sum(1 for row in complete_buy_rows if row["active_growth_phase"]) / len(complete_buy_rows) if complete_buy_rows else None)
    growth_captured_as_buy_pct = (sum(1 for row in growth_rows if row["raw_side"] == "buy") / len(growth_rows) if growth_rows else None)
    false_buy_outside_growth_pct = (sum(1 for row in non_growth_rows if row["raw_side"] == "buy") / len(non_growth_rows) if non_growth_rows else None)
    missed_buy_inside_growth_pct = (sum(1 for row in growth_rows if row["raw_side"] != "buy") / len(growth_rows) if growth_rows else None)

    side_flip_count = 0
    oscillation_flag = False
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    for symbol_rows in by_symbol.values():
        symbol_rows.sort(key=lambda row: row["bar_close_ts_ms"])
        raw_sides = [row["raw_side"] for row in symbol_rows]
        prev_side = None
        for side in raw_sides:
            if prev_side is not None and side != prev_side:
                side_flip_count += 1
            prev_side = side
        for a, b, c in zip(raw_sides, raw_sides[1:], raw_sides[2:], strict=False):
            if a and b and c and a == c and a != b:
                oscillation_flag = True
    churn_rate = side_flip_count / max(1, len(rows) - len(by_symbol))

    promising = (
        (
            complete_buy_rows and buy_during_growth_pct is not None and buy_during_growth_pct > 0.0
            and false_buy_outside_growth_pct is not None and false_buy_outside_growth_pct <= PROMISING_FALSE_BUY_MAX
        )
        or (
            len(growth_rows) > 0
            and sum(1 for row in growth_rows if baseline_lookup[(row["symbol"], row["bar_close_ts_ms"])]["raw_side"] == "sell") > 0
            and (
                (
                    sum(1 for row in growth_rows if baseline_lookup[(row["symbol"], row["bar_close_ts_ms"])]["raw_side"] == "sell")
                    - sum(1 for row in growth_rows if row["raw_side"] == "sell")
                ) / max(1, sum(1 for row in growth_rows if baseline_lookup[(row["symbol"], row["bar_close_ts_ms"])]["raw_side"] == "sell"))
            ) >= PROMISING_SELL_REDUCTION_MIN
            and churn_rate <= CHURN_MULT_MAX
        )
    )
    dangerous = bool(false_buy_outside_growth_pct is not None and false_buy_outside_growth_pct > PROMISING_FALSE_BUY_MAX) or oscillation_flag

    return ScenarioMetrics(
        family=family, scenario_id=scenario_id, scenario_value=scenario_value, status=status,
        window_points=len(rows), label_complete_points=len(label_complete_rows),
        sell_active_pct_full=full_occ[0], neutral_pct_full=full_occ[1], buy_active_pct_full=full_occ[2],
        sell_active_pct_growth=growth_occ[0], neutral_pct_growth=growth_occ[1], buy_active_pct_growth=growth_occ[2],
        sell_active_pct_non_growth=non_growth_occ[0], neutral_pct_non_growth=non_growth_occ[1], buy_active_pct_non_growth=non_growth_occ[2],
        mean_distance_to_buy=_mean(distance_to_buy), median_distance_to_buy=_median(distance_to_buy), p90_distance_to_buy=_percentile(distance_to_buy, 0.90),
        mean_sell_depth=_mean(sell_depth), median_sell_depth=_median(sell_depth), p90_sell_depth=_percentile(sell_depth, 0.90),
        moved_sell_to_neutral=moved_sell_to_neutral, moved_neutral_to_buy=moved_neutral_to_buy,
        buy_during_growth_pct=buy_during_growth_pct, growth_captured_as_buy_pct=growth_captured_as_buy_pct,
        false_buy_outside_growth_pct=false_buy_outside_growth_pct, missed_buy_inside_growth_pct=missed_buy_inside_growth_pct,
        side_flip_count=side_flip_count, churn_rate=churn_rate, oscillation_flag=oscillation_flag,
        baseline_sell_to_neutral_delta=baseline_sell_to_neutral_delta, baseline_neutral_to_buy_delta=baseline_neutral_to_buy_delta,
        promising=promising, dangerous=dangerous,
    )


def _deterministic_signature(rows: Sequence[dict[str, Any]]) -> str:
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _scenario_report_name(family: str, idx: int) -> str:
    return f"SCENARIO_{family.upper()}_{idx:02d}_REPORT.md"


def _scenario_output_prefix(family: str, idx: int) -> str:
    return f"SCENARIO_{family.upper()}_{idx:02d}_OUTPUT"


def _metrics_to_row(metrics: ScenarioMetrics) -> dict[str, Any]:
    return dataclasses.asdict(metrics)


def _compute_churn_rate(rows: Sequence[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    side_flips = 0
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    for symbol_rows in by_symbol.values():
        symbol_rows.sort(key=lambda row: row["bar_close_ts_ms"])
        prev_side = None
        for row in symbol_rows:
            side = str(row["raw_side"])
            if prev_side is not None and side != prev_side:
                side_flips += 1
            prev_side = side
    return side_flips / max(1, len(rows) - len(by_symbol))


def _growth_sell_reduction(
    metrics: ScenarioMetrics,
    baseline_growth_sell_pct: float | None,
) -> float:
    if baseline_growth_sell_pct is None or baseline_growth_sell_pct <= 0.0 or metrics.sell_active_pct_growth is None:
        return 0.0
    return max(0.0, (baseline_growth_sell_pct - metrics.sell_active_pct_growth) / baseline_growth_sell_pct)


def _write_window_freeze_report(path: Path, *, window_spec: FrozenWindowSpec, failure_rows: Sequence[dict[str, Any]], source_files: Sequence[Path]) -> None:
    lines = [
        "# AURORA TREND_UP WINDOW FREEZE REPORT", "",
        "## FACTS",
        f"- Exact start timestamp (UTC): `{_iso_utc(window_spec.start_ts_ms)}`",
        f"- Exact end timestamp (UTC): `{_iso_utc(window_spec.end_ts_ms)}`",
        f"- Symbols included: `{', '.join(window_spec.symbols)}`",
        f"- Latest common recorder bar considered: `{_iso_utc(window_spec.latest_common_recorder_ts_ms)}`",
        f"- Chosen complete segment index: `{window_spec.chosen_segment_index}`",
        f"- Parent complete segment: `{_iso_utc(window_spec.parent_segment_start_ts_ms)}` .. `{_iso_utc(window_spec.parent_segment_end_ts_ms)}` with `{window_spec.parent_segment_bar_count}` common bars",
        f"- Final frozen window bar count: `{window_spec.segment_bar_count}` common bars x `{len(window_spec.symbols)}` symbols",
        f"- Qualifying TREND_UP SELL/SHORT failures inside segment: `{window_spec.qualifying_failure_count}`",
        f"- Latest qualified failure timestamp (UTC): `{_iso_utc(window_spec.latest_failure_ts_ms)}`",
        f"- Selection mode: `{window_spec.selection_mode}`",
        f"- Evidence sources: `{', '.join(window_spec.sources)}`", "",
        "## INFERENCES",
        "- The frozen window is the latest exact-parity clean contiguous subwindow that preserves the latest qualified TREND_UP SELL/SHORT failure while remaining fully reconstructable across recorder rows, regime evidence, and Aurora decision traces.", "",
        "## ASSUMPTIONS",
        "- Recorder `feat_bar_close_ts` rows ending in `.999` are normalized to the exact bar-close boundary used by runtime logs.",
        "- Side-bearing failure qualification requires either a logged emitted `SELL` or a trade-lifecycle `SHORT`, plus shadow or trade-lifecycle evidence for the same `rid`.", "",
        "## UNKNOWNS",
        "- Final emitted side is fully proven only where a runtime `SIGNAL:` line or downstream lifecycle evidence exists.", "",
        "## Metrics",
        f"- Completeness flags: `{json.dumps(window_spec.completeness_flags, sort_keys=True)}`",
        f"- Source file count hashed into manifest: `{len(list(source_files))}`", "",
        "## Evidence",
    ]
    if window_spec.refinement_reason:
        lines.append(f"- Refinement reason: `{window_spec.refinement_reason}`")
    for row in failure_rows[:10]:
        lines.append(f"- `{row['timestamp_utc']}` `{row['symbol']}` raw=`{row['raw_side']}` emitted=`{row['final_signal_side']}` trade=`{row['trade_side']}` rid=`{row['rid']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_active_growth_report(path: Path, *, chosen_candidate: CandidateDefinition, evaluations: Sequence[CandidateEvaluation], thresholds: dict[str, float]) -> None:
    lines = [
        "# ACTIVE GROWTH PHASE DEFINITION", "",
        "## FACTS",
        f"- Candidate thresholds: `thr_r3_bps={thresholds['thr_r3_bps']:.2f}`, `thr_r6_bps={thresholds['thr_r6_bps']:.2f}`, `thr_mfe_6_bps={thresholds['thr_mfe_6_bps']:.2f}`",
        f"- Selected final definition: `{chosen_candidate.name}`",
        f"- Selected description: `{chosen_candidate.description}`", "",
        "## INFERENCES",
        "- The winning label is the one with the strongest separation between future long payoff and future short benefit, while also keeping lower dependency on baseline Aurora score polarity.", "",
        "## ASSUMPTIONS",
        "- Horizons are fixed at 3 and 6 future 5m bars inside the frozen-window market context.", "",
        "## UNKNOWNS",
        "- The chosen label is local to this experiment and does not prove a globally optimal definition of growth across other dates or symbols.", "",
        "## Metrics",
    ]
    for evaluation in evaluations:
        lines.append(f"- `{evaluation.name}` true={evaluation.true_count} false={evaluation.false_count} separation={evaluation.separation_score:.2f} mean_true_fwd6={evaluation.mean_true_fwd6_bps:.2f} abs_corr={evaluation.baseline_dependency_abs_corr:.4f} selection_score={evaluation.selection_score:.2f}")
    lines.extend(["", "## Evidence",
                  "- Candidate A formula: `fwd_ret_3_bps >= thr_r3_bps and fwd_ret_6_bps >= thr_r6_bps`",
                  "- Candidate B formula: `bullish_closes_next3 >= 2 and fwd_ret_3_bps >= thr_r3_bps`",
                  "- Candidate C formula: `fwd_ret_3_bps > 0 and long_mfe_6_bps >= thr_mfe_6_bps and long_mfe_6_bps >= 1.5 * short_benefit_6_bps`"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_scenario_report(path: Path, *, scenario: ScenarioSpec, metrics: ScenarioMetrics, rows: Sequence[dict[str, Any]], baseline_lookup: dict[tuple[str, int], dict[str, Any]]) -> None:
    lines = [
        f"# {scenario.scenario_id} REPORT", "",
        "## FACTS",
        f"- Family: `{scenario.family}`",
        f"- Scenario value: `{scenario.scenario_value}`",
        f"- Baseline value: `{scenario.baseline_value}`",
        f"- Redistribution rule: `{scenario.redistribution_rule}`",
        f"- Status: `{metrics.status}`",
    ]
    if metrics.blocked_reason:
        lines.append(f"- Blocked reason: `{metrics.blocked_reason}`")
    lines.extend(["", "## INFERENCES"])
    if metrics.status == "ok":
        if metrics.promising:
            lines.append("- This scenario looks promising under the local TREND_UP experiment because it either captured at least one BUY during active growth with bounded false BUY outside growth, or materially reduced SELL-active pressure inside growth without excessive churn.")
        elif metrics.dangerous:
            lines.append("- This scenario is locally misleading or dangerous: it either creates false BUY outside growth, introduces oscillation, or does not improve directional alignment enough to justify the blast radius.")
        else:
            lines.append("- This scenario mostly neutralizes or shifts scores without creating a convincing selective-BUY profile during active growth.")
    else:
        lines.append("- This scenario could not be proven under the frozen-input contract and is therefore treated as blocked/unproven.")
    lines.extend([
        "", "## ASSUMPTIONS",
        "- Primary success metric is `raw_side`; `final_side_optional` is supplemental only.",
        "", "## UNKNOWNS",
        "- Policy-layer rewrites are not replayed for scenario outputs unless they were independently frozen from runtime logs.",
        "", "## Metrics",
        f"- Window points: `{metrics.window_points}`",
        f"- Label-complete points: `{metrics.label_complete_points}`",
        f"- Full-window occupancy: sell={_render_pct(metrics.sell_active_pct_full)} neutral={_render_pct(metrics.neutral_pct_full)} buy={_render_pct(metrics.buy_active_pct_full)}",
        f"- Growth occupancy: sell={_render_pct(metrics.sell_active_pct_growth)} neutral={_render_pct(metrics.neutral_pct_growth)} buy={_render_pct(metrics.buy_active_pct_growth)}",
        f"- Non-growth occupancy: sell={_render_pct(metrics.sell_active_pct_non_growth)} neutral={_render_pct(metrics.neutral_pct_non_growth)} buy={_render_pct(metrics.buy_active_pct_non_growth)}",
        f"- Distance to BUY mean/median/p90: `{_render_num(metrics.mean_distance_to_buy)}` / `{_render_num(metrics.median_distance_to_buy)}` / `{_render_num(metrics.p90_distance_to_buy)}`",
        f"- SELL depth mean/median/p90: `{_render_num(metrics.mean_sell_depth)}` / `{_render_num(metrics.median_sell_depth)}` / `{_render_num(metrics.p90_sell_depth)}`",
        f"- Transitions: sell->neutral=`{metrics.moved_sell_to_neutral}` neutral->buy=`{metrics.moved_neutral_to_buy}`",
        f"- Growth alignment: buy_during_growth={_render_pct(metrics.buy_during_growth_pct)} growth_captured={_render_pct(metrics.growth_captured_as_buy_pct)} false_buy_outside_growth={_render_pct(metrics.false_buy_outside_growth_pct)} missed_buy_inside_growth={_render_pct(metrics.missed_buy_inside_growth_pct)}",
        f"- Stability: side_flips=`{metrics.side_flip_count}` churn=`{metrics.churn_rate:.4f}` oscillation=`{metrics.oscillation_flag}`",
        "", "## Evidence",
    ])
    changed_examples = [row for row in rows if baseline_lookup[(row["symbol"], row["bar_close_ts_ms"])]["raw_side"] != row["raw_side"]][:10]
    if not changed_examples:
        lines.append("- No raw-side changes versus baseline in the frozen window.")
    else:
        for row in changed_examples:
            baseline = baseline_lookup[(row["symbol"], row["bar_close_ts_ms"])]
            lines.append(f"- `{row['timestamp']}` `{row['symbol']}` baseline=`{baseline['raw_side']}` scenario=`{row['raw_side']}` growth=`{row['active_growth_phase']}` score=`{row['final_score']:.6f}` thr_buy=`{row['thr_buy']:.6f}` thr_sell=`{row['thr_sell']:.6f}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_spillover_report(path: Path, *, spillover_rows: Sequence[dict[str, Any]], notes: Sequence[str]) -> None:
    lines = ["# SPILLOVER SANITY CHECK REPORT", "", "## FACTS"]
    if not spillover_rows:
        lines.append("- No scenario reached the promising threshold for spillover execution, or no qualified control window was reconstructable under the frozen contract.")
    else:
        for row in spillover_rows:
            lines.append(f"- `{row['scenario_id']}` window=`{row['window_name']}` target_regime=`{row['target_regime']}` sell_to_buy_flip_pct=`{row['sell_to_buy_flip_pct']:.2%}` buy_active_pct=`{row['buy_active_pct']:.2%}` churn_mult=`{row['churn_mult']:.2f}` verdict=`{row['verdict']}`")
    lines.extend(["", "## INFERENCES", "- Spillover checks are bounded blast-radius probes, not full global validation.", "", "## ASSUMPTIONS", "- Hard reject thresholds follow the experiment contract exactly for TREND_DOWN flips, TREND_DOWN BUY-active occupancy, and churn multiplication.", "", "## UNKNOWNS", "- A clean spillover sanity result does not prove the candidate is safe in all regimes or dates.", "", "## Metrics"])
    for note in notes:
        lines.append(f"- {note}")
    lines.extend(["", "## Evidence", "- Control windows are frozen from the same reconstructable common-bar segments used by the primary study."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_master_report(path: Path, *, metrics_rows: Sequence[ScenarioMetrics], winner_family: str | None, winner_scenario: ScenarioMetrics | None, baseline_growth_sell_pct: float | None) -> None:
    family_groups: dict[str, list[ScenarioMetrics]] = defaultdict(list)
    for metrics in metrics_rows:
        family_groups[metrics.family].append(metrics)
    family_rank_rows: list[str] = []
    for family, items in sorted(family_groups.items()):
        ok_items = [item for item in items if item.status == "ok"]
        if not ok_items:
            family_rank_rows.append(f"- `{family}`: no proven scenario output under the frozen contract.")
            continue
        best = sorted(
            ok_items,
            key=lambda item: (
                (item.growth_captured_as_buy_pct if item.growth_captured_as_buy_pct is not None else -1.0),
                -(item.false_buy_outside_growth_pct if item.false_buy_outside_growth_pct is not None else 1.0),
                _growth_sell_reduction(item, baseline_growth_sell_pct),
                -float(item.churn_rate),
                1.0 if item.spillover_risk == "pass" else 0.0 if item.spillover_risk == "not_run" else -1.0,
            ),
            reverse=True,
        )[0]
        family_rank_rows.append(
            f"- `{family}` best=`{best.scenario_id}` growth_capture={_render_pct(best.growth_captured_as_buy_pct)} "
            f"false_buy={_render_pct(best.false_buy_outside_growth_pct)} growth_sell_reduction={_render_pct(_growth_sell_reduction(best, baseline_growth_sell_pct))} "
            f"churn=`{best.churn_rate:.4f}` spillover=`{best.spillover_risk or 'not_run'}`"
        )

    lines = [
        "# AURORA TREND_UP STRATEGIST SWEEP MASTER REPORT", "",
        "## FACTS",
        f"- Scenario count: `{len(metrics_rows)}`",
        f"- Winner family: `{winner_family or 'none'}`",
        f"- Winner scenario: `{winner_scenario.scenario_id if winner_scenario else 'none'}`", "",
        "## INFERENCES",
    ]
    if winner_scenario is None:
        lines.append("- No scenario produced a convincing selective-BUY improvement with an acceptable local blast radius.")
    else:
        lines.append(f"- `{winner_scenario.scenario_id}` is the current near-winner because it ranks highest on growth capture first, then on false-BUY control, pathological-SELL reduction, churn, and spillover safety.")
    lines.extend([
        "",
        "## ASSUMPTIONS",
        "- Ranking is lexicographic: growth capture, false BUY outside growth, SELL reduction inside growth, churn, then spillover risk.",
        "",
        "## UNKNOWNS",
        "- This master ranking is local to the frozen window and bounded control checks; it is not a production rollout proof.",
        "",
        "## Metrics",
        "| Scenario | Status | Growth Capture | False Buy Outside Growth | Growth SELL Reduction | Churn | Spillover | Promising | Dangerous |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for metrics in metrics_rows:
        lines.append(
            f"| {metrics.scenario_id} | {metrics.status} | {_render_pct(metrics.growth_captured_as_buy_pct)} | "
            f"{_render_pct(metrics.false_buy_outside_growth_pct)} | {_render_pct(_growth_sell_reduction(metrics, baseline_growth_sell_pct))} | "
            f"{_render_num(metrics.churn_rate, 4)} | {metrics.spillover_risk or 'not_run'} | {metrics.promising} | {metrics.dangerous} |"
        )
    lines.extend(["", "## Evidence", "- All 18 main-sweep scenarios are included in the table above.", "", "## Family Ranking"])
    lines.extend(family_rank_rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_validation_report(path: Path, *, parity_ok: bool, mismatches: Sequence[dict[str, Any]], scenario_count: int, rerun_ok: bool, spillover_executed: bool, unknowns: Sequence[str]) -> None:
    lines = [
        "# AURORA TREND_UP STRATEGIST SWEEP VALIDATION REPORT", "",
        "## FACTS",
        f"- Baseline parity gate passed: `{parity_ok}`",
        f"- Scenario count executed or blocked under contract: `{scenario_count}`",
        f"- Deterministic rerun signature match: `{rerun_ok}`",
        f"- Spillover execution attempted on promising scenarios: `{spillover_executed}`", "",
        "## INFERENCES",
        "- The frozen-input replay reproduces the live Quadratic scoring path on the selected window within tolerance." if parity_ok else "- The frozen-input replay failed parity, so any downstream sweep conclusions must be treated as blocked.",
        "", "## ASSUMPTIONS",
        "- Parity requires exact regime and raw side equality plus decision-score and threshold tolerance <= 1e-6.", "",
        "## UNKNOWNS",
    ]
    for unknown in unknowns:
        lines.append(f"- {unknown}")
    lines.extend(["", "## Metrics", f"- Mismatch count: `{len(mismatches)}`", "", "## Evidence"])
    if not mismatches:
        lines.append("- No parity mismatches recorded.")
    else:
        for row in mismatches[:20]:
            lines.append(f"- `{row['timestamp']}` `{row['symbol']}` fields=`{row['mismatch_fields']}` replay_score=`{row['replay_score']}` logged_score=`{row['logged_score']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_final_report(path: Path, *, proven_findings: Sequence[str], most_promising_lever: str, unsafe_levers: Sequence[str], remaining_unknowns: Sequence[str], next_package: str) -> None:
    lines = ["# AURORA TREND_UP STRATEGIST SWEEP FINAL REPORT", "", "## Proven findings"]
    for item in proven_findings:
        lines.append(f"- {item}")
    lines.extend(["", "## Most promising lever", f"- {most_promising_lever}", "", "## Unsafe or misleading levers"])
    for item in unsafe_levers:
        lines.append(f"- {item}")
    lines.extend(["", "## Remaining unknowns"])
    for item in remaining_unknowns:
        lines.append(f"- {item}")
    lines.extend(["", "## Recommended next package", f"- {next_package}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    strategies_yaml = Path(args.strategies_yaml)
    symbols = list(args.symbols) if args.symbols else _parse_aurora_symbols(strategies_yaml)
    typed_config = _load_typed_config(Path(args.config_dir))
    recorder_points, recorder_series, recorder_files = _load_recorder_points(Path(args.recorder_dir), symbols, int(args.tf_sec))
    aurora_core_paths = _ordered_rotated_paths(args.aurora_core_glob)
    decision_log_paths = _ordered_rotated_paths(args.decision_log_glob)
    regime_map, decision_map, aurora_log_files = _parse_aurora_core_logs(aurora_core_paths, symbols)
    side_evidence, side_files = _parse_side_evidence(decision_log_paths + aurora_core_paths, Path(args.shadow_journal), Path(args.trade_lifecycle), symbols)
    common_recorder_ts = _compute_common_recorder_timestamps(recorder_points, symbols)
    if not common_recorder_ts:
        raise StudyError("No common recorder timestamps across Aurora symbols")
    completeness = _build_completeness_map(common_recorder_ts, recorder_points, regime_map, decision_map, symbols)
    complete_segments = _build_complete_segments(common_recorder_ts, completeness, TF_MS)
    if not complete_segments:
        raise StudyError("No complete common segments were found")
    segment_index, parent_segment, parent_failure_rows = _choose_latest_failure_segment(complete_segments, symbols, regime_map, decision_map, side_evidence)
    frozen_segment = list(parent_segment)
    failure_rows = list(parent_failure_rows)
    selection_mode = "latest_complete_failure_segment"
    refinement_reason = None
    control_trend_down = _choose_control_segment("TREND_DOWN_CONTROL", ["TREND_DOWN"], complete_segments, symbols, regime_map)
    control_other = _choose_control_segment("ALT_REGIME_CONTROL", ["MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"], complete_segments, symbols, regime_map)

    baseline_rows, _baseline_all_series, _baseline_target_rows = _run_baseline_replay(
        typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map,
        decision_map=decision_map, frozen_segment=frozen_segment, active_growth_flags={},
    )
    parity_ok, mismatches = _validate_baseline_parity(baseline_rows)
    if not parity_ok:
        refined = _refine_segment_to_parity_clean_subwindow(
            segment=parent_segment,
            failure_rows=parent_failure_rows,
            mismatches=mismatches,
            tf_ms=TF_MS,
            min_future_bars=HORIZON_6,
        )
        if refined is not None:
            refined_segment, refined_failures, refinement_reason = refined
            if refined_segment != frozen_segment:
                frozen_segment = refined_segment
                failure_rows = refined_failures
                selection_mode = "parity_refined_failure_subwindow"
                baseline_rows, _baseline_all_series, _baseline_target_rows = _run_baseline_replay(
                    typed_config=typed_config, symbols=symbols, recorder_points=recorder_points, regime_map=regime_map,
                    decision_map=decision_map, frozen_segment=frozen_segment, active_growth_flags={},
                )
                parity_ok, mismatches = _validate_baseline_parity(baseline_rows)

    rest_url = str(typed_config.binance_api.live.rest_url)
    htf_manifest, htf_manifest_path = _freeze_htf_seed(out_dir, rest_url, symbols)
    htf_blocked = "blocked_reason" in htf_manifest
    source_files = sorted(set(recorder_files) | set(aurora_log_files) | set(side_files))
    frozen_manifest = {
        "sources": [{"path": str(path), "sha256": _sha256_file(path)} for path in source_files],
        "latest_common_recorder_ts_ms": common_recorder_ts[-1],
        "chosen_segment_index": segment_index,
        "chosen_segment_start_ts_ms": frozen_segment[0],
        "chosen_segment_end_ts_ms": frozen_segment[-1],
        "parent_segment_start_ts_ms": parent_segment[0],
        "parent_segment_end_ts_ms": parent_segment[-1],
        "parent_segment_bar_count": len(parent_segment),
        "qualifying_failure_count": len(failure_rows),
        "latest_failure_ts_ms": max(int(row["bar_close_ts_ms"]) for row in failure_rows),
        "selection_mode": selection_mode,
        "refinement_reason": refinement_reason,
        "completeness_flags": {
            "all_symbols_have_recorder_rows": True,
            "all_symbols_have_regime_evidence": True,
            "all_symbols_have_decision_traces": True,
            "qualifying_failures_have_shadow_or_trade_evidence": True,
        },
        "htf_seed_manifest": htf_manifest_path,
    }
    _write_json(out_dir / "frozen_window_manifest.json", frozen_manifest)
    window_spec = FrozenWindowSpec(
        start_ts_ms=int(frozen_segment[0]), end_ts_ms=int(frozen_segment[-1]),
        symbols=tuple(symbols), timezone=str(args.timezone),
        sources=tuple(str(path) for path in source_files), htf_seed_manifest=htf_manifest_path,
        completeness_flags=dict(frozen_manifest["completeness_flags"]),
        latest_common_recorder_ts_ms=int(common_recorder_ts[-1]), chosen_segment_index=segment_index,
        segment_bar_count=len(frozen_segment), qualifying_failure_count=len(failure_rows),
        parent_segment_start_ts_ms=int(parent_segment[0]), parent_segment_end_ts_ms=int(parent_segment[-1]),
        parent_segment_bar_count=len(parent_segment), latest_failure_ts_ms=max(int(row["bar_close_ts_ms"]) for row in failure_rows),
        selection_mode=selection_mode, refinement_reason=refinement_reason,
    )
    growth_candidate, candidate_evals, growth_flags, _growth_feature_rows, growth_thresholds = _evaluate_growth_candidates(baseline_rows, recorder_series)
    for row in baseline_rows:
        growth_flag, growth_complete = growth_flags.get((row["symbol"], row["bar_close_ts_ms"]), (False, False))
        row["active_growth_phase"] = growth_flag
        row["active_growth_complete"] = growth_complete
    baseline_lookup = {(row["symbol"], row["bar_close_ts_ms"]): row for row in baseline_rows}
    baseline_metrics = _compute_metrics(
        rows=baseline_rows,
        baseline_lookup=baseline_lookup,
        family="baseline",
        scenario_id="BASELINE",
        scenario_value=BASELINE_SENSITIVITY,
        status="ok",
    )
    baseline_growth_sell_pct = baseline_metrics.sell_active_pct_growth
    _write_csv(out_dir / "BASELINE_REPLAY.csv", baseline_rows)
    _write_json(out_dir / "BASELINE_REPLAY.json", baseline_rows)
    _write_window_freeze_report(out_dir / "AURORA_TREND_UP_WINDOW_FREEZE_REPORT.md", window_spec=window_spec, failure_rows=failure_rows, source_files=source_files)
    _write_active_growth_report(out_dir / "ACTIVE_GROWTH_PHASE_DEFINITION.md", chosen_candidate=growth_candidate, evaluations=candidate_evals, thresholds=growth_thresholds)
    if not parity_ok:
        _write_validation_report(out_dir / "AURORA_TREND_UP_STRATEGIST_SWEEP_VALIDATION_REPORT.md", parity_ok=False, mismatches=mismatches, scenario_count=0, rerun_ok=False, spillover_executed=False, unknowns=["Main sweep blocked because baseline replay parity did not match the frozen live trace.", "No scenario metrics should be treated as proven until parity is restored."])
        return 1

    d1_series_by_symbol = _load_d1_series_from_manifest(htf_manifest) if not htf_blocked else {}
    d1_rule_by_symbol = _choose_d1_inclusion_rule(d1_series_by_symbol, baseline_rows) if not htf_blocked else {}
    scenario_specs: list[ScenarioSpec] = []
    for idx, value in enumerate(SENSITIVITY_LADDER, start=1):
        scenario_specs.append(ScenarioSpec("sensitivity", f"SCENARIO_SENSITIVITY_{idx:02d}", BASELINE_SENSITIVITY, float(value), "none", htf_manifest_path))
    for idx, value in enumerate(WEIGHT_LADDER, start=1):
        scenario_specs.append(ScenarioSpec("weight", f"SCENARIO_WEIGHT_{idx:02d}", BASELINE_STRATEGIST_WEIGHT, float(value), "strategist delta redistributed to tactician/operator in baseline ratio 0.60:0.25", htf_manifest_path))
    for idx, value in enumerate(SMA_LADDER, start=1):
        scenario_specs.append(ScenarioSpec("sma", f"SCENARIO_SMA_{idx:02d}", BASELINE_STRATEGIST_SMA, float(value), "none", htf_manifest_path))
    scenario_output_rows: dict[str, list[dict[str, Any]]] = {}
    metrics_list: list[ScenarioMetrics] = []
    control_specs = [spec for spec in (control_trend_down, control_other) if spec is not None]
    for scenario in scenario_specs:
        scenario_rows: list[dict[str, Any]] = []
        status = "ok"
        blocked_reason = None
        try:
            if scenario.family == "sma" and htf_blocked:
                raise StudyError(str(htf_manifest["blocked_reason"]["message"]))
            scenario_rows = _run_scenario_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=frozen_segment,
                growth_flags=growth_flags,
                scenario=scenario,
                baseline_lookup=baseline_lookup,
                d1_series_by_symbol=d1_series_by_symbol,
                d1_rule_by_symbol=d1_rule_by_symbol,
            )
        except Exception as exc:
            status = "blocked"
            blocked_reason = str(exc)
            scenario_rows = []
        metrics = _compute_metrics(rows=scenario_rows, baseline_lookup=baseline_lookup, family=scenario.family, scenario_id=scenario.scenario_id, scenario_value=scenario.scenario_value, status=status, blocked_reason=blocked_reason)
        metrics_list.append(metrics)
        scenario_output_rows[scenario.scenario_id] = scenario_rows
        family_idx = int(scenario.scenario_id.rsplit("_", 1)[1])
        prefix = _scenario_output_prefix(scenario.family, family_idx)
        _write_json(out_dir / f"{prefix}.json", scenario_rows)
        _write_csv(out_dir / f"{prefix}.csv", scenario_rows)
        _write_scenario_report(out_dir / _scenario_report_name(scenario.family, family_idx), scenario=scenario, metrics=metrics, rows=scenario_rows, baseline_lookup=baseline_lookup)

    summary_rows = [_metrics_to_row(metrics) for metrics in metrics_list]
    _write_json(out_dir / "SCENARIO_SUMMARY.json", summary_rows)
    _write_csv(out_dir / "SCENARIO_SUMMARY.csv", summary_rows)
    rerun_ok = True
    metrics_by_id = {metrics.scenario_id: metrics for metrics in metrics_list}
    for scenario in scenario_specs:
        expected_metrics = metrics_by_id[scenario.scenario_id]
        rerun_rows: list[dict[str, Any]] = []
        rerun_status = "ok"
        try:
            if scenario.family == "sma" and htf_blocked:
                raise StudyError(str(htf_manifest["blocked_reason"]["message"]))
            rerun_rows = _run_scenario_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=frozen_segment,
                growth_flags=growth_flags,
                scenario=scenario,
                baseline_lookup=baseline_lookup,
                d1_series_by_symbol=d1_series_by_symbol,
                d1_rule_by_symbol=d1_rule_by_symbol,
            )
        except Exception:
            rerun_status = "blocked"
            rerun_rows = []
        if rerun_status != expected_metrics.status or _deterministic_signature(rerun_rows) != _deterministic_signature(scenario_output_rows[scenario.scenario_id]):
            rerun_ok = False
            break
    spillover_rows: list[dict[str, Any]] = []
    spillover_notes: list[str] = []
    control_baseline_lookup_by_name: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    control_baseline_churn_by_name: dict[str, float] = {}
    for control in control_specs:
        control_segment = list(range(control.start_ts_ms, control.end_ts_ms + TF_MS, TF_MS))
        control_baseline_rows, _control_all_series, _control_target_rows = _run_baseline_replay(
            typed_config=typed_config,
            symbols=symbols,
            recorder_points=recorder_points,
            regime_map=regime_map,
            decision_map=decision_map,
            frozen_segment=control_segment,
            active_growth_flags={},
        )
        control_baseline_lookup_by_name[control.name] = {
            (row["symbol"], row["bar_close_ts_ms"]): row for row in control_baseline_rows
        }
        control_baseline_churn_by_name[control.name] = _compute_churn_rate(control_baseline_rows)
    promising_metrics = [item for item in metrics_list if item.promising and item.status == "ok"]
    for metrics in promising_metrics:
        scenario = next(spec for spec in scenario_specs if spec.scenario_id == metrics.scenario_id)
        for control in control_specs:
            control_segment = list(range(control.start_ts_ms, control.end_ts_ms + TF_MS, TF_MS))
            control_baseline_lookup = control_baseline_lookup_by_name.get(control.name, {})
            control_rows = _run_scenario_replay(
                typed_config=typed_config,
                symbols=symbols,
                recorder_points=recorder_points,
                regime_map=regime_map,
                decision_map=decision_map,
                frozen_segment=control_segment,
                growth_flags={},
                scenario=scenario,
                baseline_lookup=control_baseline_lookup,
                d1_series_by_symbol=d1_series_by_symbol,
                d1_rule_by_symbol=d1_rule_by_symbol,
            )
            if not control_rows:
                continue
            sell_to_buy_flips = 0
            denominator = 0
            for row in control_rows:
                baseline = control_baseline_lookup.get((row["symbol"], row["bar_close_ts_ms"]))
                if baseline is None:
                    continue
                if baseline["raw_side"] == "sell":
                    denominator += 1
                    if row["raw_side"] == "buy":
                        sell_to_buy_flips += 1
            sell_to_buy_flip_pct = sell_to_buy_flips / max(1, denominator)
            buy_active_pct = sum(1 for row in control_rows if row["raw_side"] == "buy") / max(1, len(control_rows))
            control_baseline_churn = control_baseline_churn_by_name.get(control.name, 0.0)
            scenario_control_churn = _compute_churn_rate(control_rows)
            if control_baseline_churn <= 1e-9:
                churn_mult = 1.0 if scenario_control_churn <= 1e-9 else float("inf")
            else:
                churn_mult = scenario_control_churn / control_baseline_churn
            reject = sell_to_buy_flip_pct > SPILLOVER_TREND_DOWN_FLIP_MAX or (control.target_regime == "TREND_DOWN" and buy_active_pct > SPILLOVER_TREND_DOWN_BUY_MAX) or churn_mult > CHURN_MULT_MAX
            verdict = "reject" if reject else "pass"
            spillover_rows.append({"scenario_id": scenario.scenario_id, "window_name": control.name, "target_regime": control.target_regime, "sell_to_buy_flip_pct": sell_to_buy_flip_pct, "buy_active_pct": buy_active_pct, "churn_mult": churn_mult, "verdict": verdict})
            spillover_notes.append(f"{scenario.scenario_id} on {control.name}: sell_to_buy_flip_pct={sell_to_buy_flip_pct:.2%}, buy_active_pct={buy_active_pct:.2%}, churn_mult={churn_mult:.2f}, verdict={verdict}")
    spillover_verdicts: dict[str, list[str]] = defaultdict(list)
    for row in spillover_rows:
        spillover_verdicts[str(row["scenario_id"])].append(str(row["verdict"]))
    metrics_list = [
        dataclasses.replace(
            metrics,
            spillover_risk=(
                "reject" if "reject" in spillover_verdicts.get(metrics.scenario_id, [])
                else "pass" if "pass" in spillover_verdicts.get(metrics.scenario_id, [])
                else "not_run"
            ),
        )
        for metrics in metrics_list
    ]
    summary_rows = [_metrics_to_row(metrics) for metrics in metrics_list]
    _write_json(out_dir / "SCENARIO_SUMMARY.json", summary_rows)
    _write_csv(out_dir / "SCENARIO_SUMMARY.csv", summary_rows)
    _write_spillover_report(out_dir / "SPILLOVER_SANITY_CHECK_REPORT.md", spillover_rows=spillover_rows, notes=spillover_notes)
    ranked_metrics = [item for item in metrics_list if item.status == "ok"]
    ranked_metrics.sort(
        key=lambda item: (
            (item.growth_captured_as_buy_pct if item.growth_captured_as_buy_pct is not None else -1.0),
            -(item.false_buy_outside_growth_pct if item.false_buy_outside_growth_pct is not None else 1.0),
            _growth_sell_reduction(item, baseline_growth_sell_pct),
            -float(item.churn_rate),
            1.0 if item.spillover_risk == "pass" else 0.0 if item.spillover_risk == "not_run" else -1.0,
        ),
        reverse=True,
    )
    winner = ranked_metrics[0] if ranked_metrics else None
    _write_master_report(
        out_dir / "AURORA_TREND_UP_STRATEGIST_SWEEP_MASTER_REPORT.md",
        metrics_rows=metrics_list,
        winner_family=winner.family if winner else None,
        winner_scenario=winner,
        baseline_growth_sell_pct=baseline_growth_sell_pct,
    )
    _write_validation_report(out_dir / "AURORA_TREND_UP_STRATEGIST_SWEEP_VALIDATION_REPORT.md", parity_ok=parity_ok, mismatches=mismatches, scenario_count=len(scenario_specs), rerun_ok=rerun_ok, spillover_executed=bool(spillover_rows), unknowns=["Scenario final_side_optional is preserved only where runtime logs independently proved an emitted side; policy rewrites are not re-simulated for hypothetical scenarios.", "SMA family remains blocked/unproven if the frozen HTF seed fetch failed or did not satisfy the replay contract."])

    unsafe_levers = []
    if any(item.family == "sma" and item.status != "ok" for item in metrics_list):
        unsafe_levers.append("SMA-period sweeps are semantically wider and remain blocked whenever the one-time D1 seed cannot be frozen and validated.")
    if any(item.family == "weight" and item.dangerous for item in metrics_list):
        unsafe_levers.append("Weight reductions can look attractive locally but become misleading when they create false BUY outside active growth or unstable side churn.")
    if any(item.family == "sensitivity" and item.dangerous for item in metrics_list):
        unsafe_levers.append("Sensitivity reductions can neutralize SELL pressure without producing genuine BUY capture during growth.")
    proven_findings = [
        f"Frozen window: {_iso_utc(window_spec.start_ts_ms)} .. {_iso_utc(window_spec.end_ts_ms)} with {window_spec.qualifying_failure_count} qualifying TREND_UP SELL/SHORT failures.",
        f"Baseline parity gate passed with {len(mismatches)} mismatches.",
        f"Selected active-growth definition: {growth_candidate.name}.",
    ]
    if winner is not None:
        proven_findings.append(f"Top local scenario: {winner.scenario_id} ({winner.family}={winner.scenario_value}) growth_capture={_render_pct(winner.growth_captured_as_buy_pct)} false_buy_outside_growth={_render_pct(winner.false_buy_outside_growth_pct)} churn={winner.churn_rate:.4f}.")
    _write_final_report(out_dir / "AURORA_TREND_UP_STRATEGIST_SWEEP_FINAL_REPORT.md", proven_findings=proven_findings, most_promising_lever=(f"{winner.family} via {winner.scenario_id}" if winner is not None else "No single-factor winner was proven"), unsafe_levers=unsafe_levers or ["No additional unsafe lever was proven beyond the explicit evidence limits."], remaining_unknowns=["This experiment is still local to one frozen TREND_UP episode plus bounded spillover probes.", "Policy-layer final-side behavior for hypothetical scenarios remains supplemental rather than primary truth."], next_package=("local refinement around winner family" if winner is not None else "reject and move to threshold overlay experiments instead"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
