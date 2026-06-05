#!/usr/bin/env python3
"""Production Aurora threshold calibrator for active runtime surfaces only.

Calibration class
-----------------
production

Current production scope
------------------------
- assets.<SYMBOL>.signal_threshold.value
- assets.<SYMBOL>.regime_thresholds

Research and legacy exclusions
------------------------------
- signal_weights
- direction_strength_scoring
- feature_neutrals
- neutral_threshold
- cooldown, reentry, and holding-period tuning

Operational contract
--------------------
- emit overlay artifacts only; never mutate canonical YAML
- recorder-features-v2 is the production-aligned evidence path
- aurora-logs is retained as a research and diagnostic evidence path only
"""
from __future__ import annotations

import argparse
import csv
import decimal
import glob
import json
import logging
import math
import re
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOG = logging.getLogger(__name__)

CALIBRATION_STANDARD = "CALIBRATION_STANDARD_V1"
CALIBRATION_CLASS = "production"
PRODUCTION_INPUT_SOURCE = "recorder-features-v2"
RESEARCH_INPUT_SOURCE = "aurora-logs"
# PKG-A1 provenance sentinel: bars with pillar_sum recalculated by calibrator carry this class.
CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE = "aurora_calibrator_synthetic_pillar_sum"
PRIMARY_CANDIDATE_OVERLAY = "candidate_aurora_threshold_overlay.yaml"
LEGACY_CANDIDATE_OVERLAY = "candidate_threshold_overlay.yaml"
RECOMMENDED_ARTIFACTS = (
    PRIMARY_CANDIDATE_OVERLAY,
    "run_manifest.json",
    "baseline_metrics.json",
    "candidate_metrics.json",
    "validation_metrics.json",
    "forward_metrics.json",
    "report.md",
)
THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY = "asset-override-only"
THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE = "live-effective"
AURORA_ACTIVE_SURFACES = (
    "assets.<SYMBOL>.signal_threshold.value",
    "assets.<SYMBOL>.regime_thresholds",
)
AURORA_NON_GOALS = (
    "signal_weights",
    "direction_strength_scoring",
    "feature_neutrals",
    "neutral_threshold",
    "cooldown tuning",
    "reentry tuning",
    "holding-period tuning",
    "canonical YAML writeback",
)
AURORA_RUNTIME_TRUTH_ANCHORS = (
    "QuadraticScoringKernel is the active Aurora scoring path.",
    "Aurora live threshold resolution uses assets.<SYMBOL>.signal_threshold.value only when the per-symbol override is enabled; otherwise it falls back to decision.signal_threshold.",
    "Per-symbol regime_thresholds override the global regime threshold map in live runtime when present; otherwise live falls back to decision.regime_threshold_multipliers.",
    "signal_weights, feature_neutrals, and direction_strength_scoring are legacy compatibility surfaces for live Aurora math.",
    "Shield cascade is active runtime surface for Quadratic Aurora production mode.",
)


TRACE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?"
    r"\[(?P<symbol>[A-Z0-9_]+)\] QUADRATIC_DECISION_TRACE "
    r"score=(?P<score>[+-]?\d+(?:\.\d+)?)\s+"
    r"side=(?P<side>[A-Za-z]*)\s+"
    r"deferred=(?P<deferred>True|False)\s+"
    r"regime=(?P<regime>[A-Z_]+)"
)


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThresholdSurface:
    symbol: str
    signal_threshold_value: float
    regime_thresholds: dict[str, float]
    signal_threshold_source: str
    signal_threshold_path: str
    regime_threshold_source: str
    regime_threshold_path: str


@dataclass(frozen=True)
class ScoreSample:
    timestamp: datetime
    symbol: str
    regime: str
    score: float
    side: str
    deferred: bool
    source_file: str
    line_number: int


@dataclass(frozen=True)
class RegimeSummary:
    regime: str
    sample_count: int
    neutral_count: int
    side_count: int
    p50_abs_score: float
    p75_abs_score: float
    p80_abs_score: float
    p90_abs_score: float
    current_factor: float
    current_effective_threshold: float
    proposed_factor: float | None
    proposed_effective_threshold: float | None


@dataclass(frozen=True)
class SymbolCalibration:
    symbol: str
    surface: ThresholdSurface
    total_samples: int
    non_deferred_samples: int
    deferred_samples: int
    neutral_samples: int
    side_bearing_samples: int
    regime_counts: dict[str, int]
    current_estimated_activation_rate: float
    proposed_estimated_activation_rate: float
    p50_abs_score: float
    p75_abs_score: float
    p80_abs_score: float
    p90_abs_score: float
    proposed_signal_threshold_value: float
    proposed_regime_thresholds: dict[str, float]
    regime_summaries: list[RegimeSummary]
    warnings: list[str]


@dataclass(frozen=True)
class RecorderBar:
    timestamp: datetime
    timestamp_ms: int
    symbol: str
    tf_sec: int
    ready: bool
    not_ready_reasons: str
    close: float
    high: float | None
    low: float | None
    pillar_sum: float | None
    pillar_tactician: float | None
    pillar_operator: float | None
    pillar_strategist: float | None
    spread_bps: float | None
    volatility_state: float | None
    price_motion_norm: float | None
    # PKG-A1 provenance: empty string = live-feature-derived; non-empty = synthetic.
    # Set to CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE when pillar_sum is mutated
    # by the pillar_weights recalculation block. Downstream readers must check this
    # field before treating pillar_sum as a live feature-derived value.
    pillar_sum_provenance_class: str = ""


@dataclass(frozen=True)
class FeatureLogAudit:
    symbol: str
    exists: bool
    file_size_mb: float
    sampled_lines: int
    sampled_keys: list[str]
    has_timestamp_fields: bool
    warnings: list[str]


@dataclass(frozen=True)
class ReplayObservation:
    timestamp: datetime
    symbol: str
    split: str
    eligible: bool
    regime: str
    regime_confidence: float | None
    score: float | None
    side: str
    deferred: bool
    shield_multiplier: float | None
    threshold_factor: float | None
    thr_buy: float | None
    thr_sell: float | None
    forward_bps_1: float | None
    forward_bps_3: float | None


@dataclass(frozen=True)
class ReplayMetrics:
    eligible_bars: int
    active_bars: int
    buy_count: int
    sell_count: int
    activation_rate: float
    max_daily_activation_rate: float
    mean_forward_bps_1: float | None
    mean_forward_bps_3: float | None
    hit_rate_1: float | None
    hit_rate_3: float | None
    p50_abs_score: float | None
    p75_abs_score: float | None
    p80_abs_score: float | None
    p90_abs_score: float | None
    regime_counts: dict[str, int]


@dataclass(frozen=True)
class ReplayWindowSpec:
    train_days: list[str]
    validation_days: list[str]
    forward_days: list[str]


@dataclass(frozen=True)
class CandidateEvaluation:
    quantile: float
    surface: ThresholdSurface
    train_metrics: ReplayMetrics
    validation_metrics: ReplayMetrics
    forward_metrics: ReplayMetrics
    train_guardrails_ok: bool
    validation_guardrails_ok: bool
    forward_guardrails_ok: bool
    train_guardrail_failures: list[str]
    validation_guardrail_failures: list[str]
    forward_guardrail_failures: list[str]
    promotable: bool
    promotability_blockers: list[str]


@dataclass(frozen=True)
class V2SymbolCalibration:
    symbol: str
    surface: ThresholdSurface
    window_spec: ReplayWindowSpec
    recorder_bar_count: int
    feature_log_audit: FeatureLogAudit
    current_train_metrics: ReplayMetrics
    current_validation_metrics: ReplayMetrics
    current_forward_metrics: ReplayMetrics
    candidate: CandidateEvaluation | None
    candidate_blockers: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class CalibrationRunOutputs:
    overlay: dict[str, Any]
    report_text: str
    verdict: str
    baseline_metrics: dict[str, Any]
    candidate_metrics: dict[str, Any]
    validation_metrics: dict[str, Any]
    forward_metrics: dict[str, Any]
    run_manifest: dict[str, Any]


class _ReplayClock:
    def __init__(self, now_ms: int):
        self._now_ms = int(now_ms)

    def set_now_ms(self, now_ms: int) -> None:
        self._now_ms = int(now_ms)

    def now_sec(self) -> float:
        return self._now_ms / 1000.0

    def now_ms(self) -> int:
        return self._now_ms

    def monotonic(self) -> float:
        return self._now_ms / 1000.0

    def sleep_sec(self, seconds: float) -> None:
        self._now_ms += int(seconds * 1000)

    def sleep_ms(self, milliseconds: int) -> None:
        self._now_ms += int(milliseconds)


class _ReplayFsm:
    def __init__(self) -> None:
        self._last_regime_payload_by_symbol: dict[str, dict[str, Any]] = {}

    def emit(self, event_name: str, payload=None, why=None, *_args, **_kwargs) -> None:
        if event_name != "EVT:REGIME_DETECTED":
            return
        if isinstance(payload, dict):
            symbol = str(payload.get("symbol") or "")
            if symbol:
                self._last_regime_payload_by_symbol[symbol] = dict(payload)

    def listen(self, _event_name: str, _callback) -> None:
        return

    def latest_regime_payload(self, symbol: str) -> dict[str, Any]:
        return dict(self._last_regime_payload_by_symbol.get(symbol, {}))


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _parse_quantile_grid(values: Sequence[str]) -> list[float]:
    parsed: list[float] = []
    for raw in values:
        value = float(raw)
        if not (0.0 < value < 1.0):
            raise argparse.ArgumentTypeError(
                f"Invalid quantile {raw!r}; expected 0 < q < 1"
            )
        parsed.append(value)
    if not parsed:
        raise argparse.ArgumentTypeError("Quantile grid must not be empty")
    return parsed


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Production Aurora threshold calibrator for active runtime surfaces only. "
            "Use --input-source recorder-features-v2 for production-aligned candidate validation across "
            "train/validation/forward windows; "
            "aurora-logs is retained as a research and diagnostic evidence path only."
        ),
    )
    parser.add_argument(
        "--aurora-yaml",
        default="config/aurora/strategies/aurora.yaml",
        help="Aurora strategy YAML containing live per-symbol threshold surface.",
    )
    parser.add_argument(
        "--threshold-source-mode",
        choices=[
            THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY,
            THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE,
        ],
        default=THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY,
        help=(
            "Threshold baseline resolution contract. "
            "asset-override-only preserves the legacy per-symbol-only calibrator path; "
            "live-effective resolves the same threshold source that live Aurora currently uses "
            "(asset override when enabled, otherwise decision.signal_threshold)."
        ),
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Symbols to calibrate, for example ETHUSDT SOLUSDT.",
    )
    parser.add_argument(
        "--from-date",
        type=_parse_date,
        required=True,
        help="Inclusive start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--to-date",
        type=_parse_date,
        required=True,
        help="Inclusive end date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--input-source",
        choices=["aurora-logs", "recorder-features-v2"],
        default="aurora-logs",
        help=(
            "Observed runtime evidence source. aurora-logs is research-only diagnostic evidence; "
            "recorder-features-v2 is the production-aligned replay path."
        ),
    )
    parser.add_argument(
        "--log-glob",
        default="logs/aurora_core.log*",
        help="Glob for Aurora core log files when --input-source=aurora-logs.",
    )
    parser.add_argument(
        "--recorder-dir",
        default="data/recorder",
        help="Recorder root directory when --input-source=recorder-features-v2.",
    )
    parser.add_argument(
        "--feature-log-dir",
        default="logs/features",
        help="Feature log directory when --input-source=recorder-features-v2.",
    )
    parser.add_argument(
        "--tf-sec",
        type=int,
        default=300,
        help="Recorder timeframe in seconds for replay calibration.",
    )
    parser.add_argument(
        "--validation-days",
        type=int,
        default=5,
        help="Number of trailing unique eligible dates reserved for validation in V2 replay mode.",
    )
    parser.add_argument(
        "--forward-days",
        type=int,
        default=5,
        help="Number of trailing unique eligible dates reserved for forward evaluation in V2 replay mode.",
    )
    parser.add_argument(
        "--min-train-days",
        type=int,
        default=10,
        help="Minimum unique eligible dates required in the train window after reserving validation and forward holdouts.",
    )
    parser.add_argument(
        "--quantile-grid",
        nargs="+",
        default=["0.55", "0.60", "0.65", "0.70", "0.75"],
        help="Candidate quantiles searched in V2 replay mode.",
    )
    parser.add_argument(
        "--min-activation-rate",
        type=float,
        default=0.02,
        help="Minimum allowed active-bar rate for V2 candidate guardrails.",
    )
    parser.add_argument(
        "--max-activation-rate",
        type=float,
        default=0.35,
        help="Maximum allowed active-bar rate for V2 candidate guardrails.",
    )
    parser.add_argument(
        "--max-daily-activation-rate",
        type=float,
        default=0.45,
        help="Maximum allowed active-bar rate within any single validation day.",
    )
    parser.add_argument(
        "--min-activation-ratio-vs-baseline",
        type=float,
        default=0.50,
        help="Minimum allowed candidate activation-rate ratio versus baseline on validation/forward splits when baseline activation is non-zero.",
    )
    parser.add_argument(
        "--max-activation-ratio-vs-baseline",
        type=float,
        default=2.50,
        help="Maximum allowed candidate activation-rate ratio versus baseline on validation/forward splits when baseline activation is non-zero.",
    )
    parser.add_argument(
        "--min-forward-edge-bps",
        type=float,
        default=0.0,
        help="Minimum required mean forward 3-bar proxy edge in basis points on any guarded split.",
    )
    parser.add_argument(
        "--min-validation-improvement-bps",
        type=float,
        default=0.0,
        help="Minimum required validation improvement in mean forward 3-bar proxy edge versus baseline.",
    )
    parser.add_argument(
        "--max-forward-degradation-bps",
        type=float,
        default=0.0,
        help="Maximum allowed forward degradation in mean forward 3-bar proxy edge versus baseline.",
    )
    parser.add_argument(
        "--min-active-bars",
        type=int,
        default=8,
        help="Minimum number of active bars required in any guarded V2 split.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Output directory for candidate_aurora_threshold_overlay.yaml, run_manifest.json, "
            "baseline_metrics.json, candidate_metrics.json, validation_metrics.json, "
            "forward_metrics.json, and report.md."
        ),
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=20,
        help="Minimum eligible bars or non-deferred samples required in a guarded split, depending on mode.",
    )
    parser.add_argument(
        "--min-regime-samples",
        type=int,
        default=10,
        help="Minimum non-deferred samples required to emit a regime-specific factor.",
    )
    parser.add_argument(
        "--target-quantile",
        type=float,
        default=0.80,
        help="Quantile of |score| used to fit candidate thresholds in V1 log mode.",
    )
    parser.add_argument(
        "--emit-overlay",
        action="store_true",
        help="Write candidate_aurora_threshold_overlay.yaml overlay artifact only; never mutate canonical YAML.",
    )
    parser.add_argument(
        "--emit-report",
        action="store_true",
        help="Write report.md artifact. JSON manifest and metrics artifacts are always emitted with the run directory.",
    )
    args = parser.parse_args(argv)

    if args.to_date < args.from_date:
        raise SystemExit(
            "--to-date must be greater than or equal to --from-date")
    if args.min_samples <= 0:
        raise SystemExit("--min-samples must be positive")
    if args.min_regime_samples <= 0:
        raise SystemExit("--min-regime-samples must be positive")
    if not (0.0 < float(args.target_quantile) < 1.0):
        raise SystemExit("--target-quantile must be between 0 and 1")
    if args.tf_sec <= 0:
        raise SystemExit("--tf-sec must be positive")
    if args.validation_days <= 0:
        raise SystemExit("--validation-days must be positive")
    if args.forward_days <= 0:
        raise SystemExit("--forward-days must be positive")
    if args.min_train_days <= 0:
        raise SystemExit("--min-train-days must be positive")
    if args.min_active_bars <= 0:
        raise SystemExit("--min-active-bars must be positive")
    if not (0.0 <= args.min_activation_rate < 1.0):
        raise SystemExit("--min-activation-rate must satisfy 0 <= rate < 1")
    if not (0.0 < args.max_activation_rate <= 1.0):
        raise SystemExit("--max-activation-rate must satisfy 0 < rate <= 1")
    if args.min_activation_rate >= args.max_activation_rate:
        raise SystemExit(
            "--min-activation-rate must be smaller than --max-activation-rate")
    if not (0.0 < args.max_daily_activation_rate <= 1.0):
        raise SystemExit(
            "--max-daily-activation-rate must satisfy 0 < rate <= 1")
    if not (0.0 < args.min_activation_ratio_vs_baseline):
        raise SystemExit("--min-activation-ratio-vs-baseline must be positive")
    if args.max_activation_ratio_vs_baseline < args.min_activation_ratio_vs_baseline:
        raise SystemExit(
            "--max-activation-ratio-vs-baseline must be greater than or equal to --min-activation-ratio-vs-baseline"
        )
    if float(args.min_validation_improvement_bps) < 0.0:
        raise SystemExit(
            "--min-validation-improvement-bps must be non-negative")
    if float(args.max_forward_degradation_bps) < 0.0:
        raise SystemExit("--max-forward-degradation-bps must be non-negative")
    if (
        args.threshold_source_mode == THRESHOLD_SOURCE_MODE_LIVE_EFFECTIVE
        and args.input_source != PRODUCTION_INPUT_SOURCE
    ):
        raise SystemExit(
            "--threshold-source-mode=live-effective is supported only with --input-source=recorder-features-v2"
        )
    args.quantile_grid = _parse_quantile_grid(args.quantile_grid)
    if not args.emit_overlay and not args.emit_report:
        args.emit_overlay = True
        args.emit_report = True
    return args


def _load_aurora_profile(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "aurora" not in raw:
        raise CalibrationError(
            f"Invalid Aurora YAML: expected top-level 'aurora' in {path}"
        )
    aurora = raw["aurora"]
    if not isinstance(aurora, dict):
        raise CalibrationError(f"Invalid Aurora YAML structure in {path}")
    return aurora


def _load_typed_runtime_config(aurora_yaml_path: Path) -> Any:
    from apps.reference.config_loader import ConfigLoader

    config_dir = aurora_yaml_path.resolve().parents[1]
    return ConfigLoader(config_dir=config_dir).load_config()


def _parse_positive_surface_value(raw: Any, *, path: str) -> float:
    if raw is None:
        raise CalibrationError(f"Missing {path}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise CalibrationError(f"Invalid {path}: {raw!r}") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise CalibrationError(f"Non-positive {path}: {value}")
    return value


def _parse_positive_regime_thresholds(raw: Any, *, path: str) -> dict[str, float]:
    if not isinstance(raw, dict) or not raw:
        raise CalibrationError(f"Missing {path}")

    parsed: dict[str, float] = {}
    for regime_name, regime_raw in raw.items():
        regime_path = f"{path}.{regime_name}"
        parsed[str(regime_name)] = _parse_positive_surface_value(
            regime_raw,
            path=regime_path,
        )

    if "DEFAULT" not in parsed:
        raise CalibrationError(f"Missing {path}.DEFAULT")
    return parsed


def _extract_live_threshold_surface(
    aurora: dict[str, Any],
    *,
    symbol: str,
    threshold_source_mode: str,
) -> ThresholdSurface:
    decision_cfg = aurora.get("decision")
    if not isinstance(decision_cfg, dict):
        raise CalibrationError(
            "Aurora decision map missing or invalid in aurora.yaml")

    assets = aurora.get("assets")
    if not isinstance(assets, dict):
        raise CalibrationError(
            "Aurora assets map missing or invalid in aurora.yaml")

    asset_cfg = assets.get(symbol)
    if not isinstance(asset_cfg, dict):
        raise CalibrationError(
            f"Symbol {symbol} is absent from aurora.assets runtime config surface"
        )

    signal_threshold_cfg = asset_cfg.get("signal_threshold")
    if isinstance(signal_threshold_cfg, dict) and signal_threshold_cfg.get("enabled") is True:
        signal_threshold_path = f"assets.{symbol}.signal_threshold.value"
        signal_threshold_value = _parse_positive_surface_value(
            signal_threshold_cfg.get("value"),
            path=signal_threshold_path,
        )
        signal_threshold_source = "asset_override"
    elif threshold_source_mode == THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY:
        raise CalibrationError(
            f"Symbol {symbol} requires assets.{symbol}.signal_threshold.enabled=true for this calibrator"
        )
    else:
        signal_threshold_path = "decision.signal_threshold"
        signal_threshold_value = _parse_positive_surface_value(
            decision_cfg.get("signal_threshold"),
            path=signal_threshold_path,
        )
        signal_threshold_source = "global_decision"

    regime_thresholds_raw = asset_cfg.get("regime_thresholds")
    if isinstance(regime_thresholds_raw, dict) and regime_thresholds_raw:
        regime_threshold_path = f"assets.{symbol}.regime_thresholds"
        regime_thresholds = _parse_positive_regime_thresholds(
            regime_thresholds_raw,
            path=regime_threshold_path,
        )
        regime_threshold_source = "asset_override"
    elif threshold_source_mode == THRESHOLD_SOURCE_MODE_ASSET_OVERRIDE_ONLY:
        raise CalibrationError(
            f"Symbol {symbol} missing assets.{symbol}.regime_thresholds runtime surface"
        )
    else:
        regime_threshold_path = "decision.regime_threshold_multipliers"
        regime_thresholds = _parse_positive_regime_thresholds(
            decision_cfg.get("regime_threshold_multipliers"),
            path=regime_threshold_path,
        )
        regime_threshold_source = "global_decision"

    return ThresholdSurface(
        symbol=symbol,
        signal_threshold_value=signal_threshold_value,
        regime_thresholds=regime_thresholds,
        signal_threshold_source=signal_threshold_source,
        signal_threshold_path=signal_threshold_path,
        regime_threshold_source=regime_threshold_source,
        regime_threshold_path=regime_threshold_path,
    )


def _iter_log_paths(pattern: str) -> list[Path]:
    paths = [Path(path) for path in glob.glob(pattern)]
    return sorted(path for path in paths if path.is_file())


def _parse_trace_samples(
    *,
    log_paths: Iterable[Path],
    symbols: set[str],
    from_date: date,
    to_date: date,
) -> list[ScoreSample]:
    samples: list[ScoreSample] = []
    for log_path in log_paths:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                match = TRACE_PATTERN.search(raw_line)
                if match is None:
                    continue

                symbol = match.group("symbol").upper()
                if symbol not in symbols:
                    continue

                timestamp = datetime.strptime(
                    match.group("timestamp"), "%Y-%m-%d %H:%M:%S,%f"
                )
                if timestamp.date() < from_date or timestamp.date() > to_date:
                    continue

                score = float(match.group("score"))
                side = match.group("side").strip().lower()
                deferred = match.group("deferred") == "True"
                regime = match.group("regime").strip().upper()
                samples.append(
                    ScoreSample(
                        timestamp=timestamp,
                        symbol=symbol,
                        regime=regime,
                        score=score,
                        side=side,
                        deferred=deferred,
                        source_file=log_path.name,
                        line_number=line_number,
                    )
                )
    return samples


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise CalibrationError("Cannot compute percentile for empty value set")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])

    rank = (len(ordered) - 1) * quantile
    low_index = int(math.floor(rank))
    high_index = int(math.ceil(rank))
    low_value = float(ordered[low_index])
    high_value = float(ordered[high_index])
    if low_index == high_index:
        return low_value
    weight = rank - low_index
    return low_value + (high_value - low_value) * weight


def _round_metric(value: float) -> float:
    return round(float(value), 6)


def _current_factor_for_regime(surface: ThresholdSurface, regime: str) -> float:
    if regime in surface.regime_thresholds:
        return float(surface.regime_thresholds[regime])
    return float(surface.regime_thresholds["DEFAULT"])


def _proposed_factor_for_regime(proposed: dict[str, float], regime: str) -> float:
    if regime in proposed:
        return float(proposed[regime])
    return float(proposed["DEFAULT"])


def _estimated_activation_rate(
    samples: Iterable[ScoreSample],
    *,
    base_threshold: float,
    regime_thresholds: dict[str, float],
) -> float:
    relevant = [sample for sample in samples if not sample.deferred]
    if not relevant:
        return 0.0
    active = 0
    for sample in relevant:
        threshold = base_threshold * _proposed_factor_for_regime(
            regime_thresholds, sample.regime
        )
        if abs(sample.score) >= threshold:
            active += 1
    return active / len(relevant)


def _fit_symbol_calibration(
    *,
    symbol: str,
    surface: ThresholdSurface,
    samples: list[ScoreSample],
    min_samples: int,
    min_regime_samples: int,
    target_quantile: float,
) -> SymbolCalibration:
    total_samples = len(samples)
    deferred_samples = sum(1 for sample in samples if sample.deferred)
    non_deferred = [sample for sample in samples if not sample.deferred]
    if len(non_deferred) < min_samples:
        raise CalibrationError(
            f"Symbol {symbol} has only {len(non_deferred)} non-deferred samples; requires at least {min_samples}"
        )

    warnings: list[str] = []
    neutral_samples = sum(1 for sample in non_deferred if sample.side == "")
    side_bearing_samples = len(non_deferred) - neutral_samples
    if side_bearing_samples == 0:
        warnings.append(
            "No side-bearing non-deferred samples observed; v1 proposal is score-distribution based only."
        )

    absolute_scores = [abs(sample.score) for sample in non_deferred]
    proposed_signal_threshold_value = _percentile(
        absolute_scores, target_quantile)
    if not math.isfinite(proposed_signal_threshold_value) or proposed_signal_threshold_value <= 0.0:
        raise CalibrationError(
            f"Symbol {symbol} produced invalid proposed signal threshold {proposed_signal_threshold_value}"
        )

    proposed_regime_thresholds: dict[str, float] = {"DEFAULT": 1.0}
    regime_groups: dict[str, list[ScoreSample]] = defaultdict(list)
    for sample in non_deferred:
        regime_groups[sample.regime].append(sample)

    regime_summaries: list[RegimeSummary] = []
    for regime_name in sorted(regime_groups.keys()):
        regime_samples = regime_groups[regime_name]
        regime_abs_scores = [abs(sample.score) for sample in regime_samples]
        proposed_factor: float | None = None
        proposed_effective_threshold: float | None = None
        if len(regime_samples) >= min_regime_samples:
            regime_effective_threshold = _percentile(
                regime_abs_scores, target_quantile)
            factor = regime_effective_threshold / proposed_signal_threshold_value
            if not math.isfinite(factor) or factor <= 0.0:
                raise CalibrationError(
                    f"Symbol {symbol} regime {regime_name} produced invalid proposed factor {factor}"
                )
            proposed_factor = factor
            proposed_effective_threshold = proposed_signal_threshold_value * factor
            if regime_name != "DEFAULT":
                proposed_regime_thresholds[regime_name] = factor
        else:
            warnings.append(
                f"Regime {regime_name} for {symbol} has only {len(regime_samples)} non-deferred samples; no regime-specific factor emitted."
            )

        current_factor = _current_factor_for_regime(surface, regime_name)
        regime_summaries.append(
            RegimeSummary(
                regime=regime_name,
                sample_count=len(regime_samples),
                neutral_count=sum(
                    1 for sample in regime_samples if sample.side == ""),
                side_count=sum(
                    1 for sample in regime_samples if sample.side != ""),
                p50_abs_score=_percentile(regime_abs_scores, 0.50),
                p75_abs_score=_percentile(regime_abs_scores, 0.75),
                p80_abs_score=_percentile(regime_abs_scores, 0.80),
                p90_abs_score=_percentile(regime_abs_scores, 0.90),
                current_factor=current_factor,
                current_effective_threshold=surface.signal_threshold_value * current_factor,
                proposed_factor=proposed_factor,
                proposed_effective_threshold=proposed_effective_threshold,
            )
        )

    if "TREND_DOWN" not in proposed_regime_thresholds:
        warnings.append(
            f"No TREND_DOWN candidate emitted for {symbol}; current evidence was insufficient under min-regime-samples={min_regime_samples}."
        )

    current_activation_rate = _estimated_activation_rate(
        non_deferred,
        base_threshold=surface.signal_threshold_value,
        regime_thresholds=surface.regime_thresholds,
    )
    proposed_activation_rate = _estimated_activation_rate(
        non_deferred,
        base_threshold=proposed_signal_threshold_value,
        regime_thresholds=proposed_regime_thresholds,
    )

    return SymbolCalibration(
        symbol=symbol,
        surface=surface,
        total_samples=total_samples,
        non_deferred_samples=len(non_deferred),
        deferred_samples=deferred_samples,
        neutral_samples=neutral_samples,
        side_bearing_samples=side_bearing_samples,
        regime_counts=dict(
            sorted(Counter(sample.regime for sample in non_deferred).items())),
        current_estimated_activation_rate=current_activation_rate,
        proposed_estimated_activation_rate=proposed_activation_rate,
        p50_abs_score=_percentile(absolute_scores, 0.50),
        p75_abs_score=_percentile(absolute_scores, 0.75),
        p80_abs_score=_percentile(absolute_scores, target_quantile),
        p90_abs_score=_percentile(absolute_scores, 0.90),
        proposed_signal_threshold_value=proposed_signal_threshold_value,
        proposed_regime_thresholds=dict(
            sorted(proposed_regime_thresholds.items())),
        regime_summaries=regime_summaries,
        warnings=warnings,
    )


def _format_ratio(value: float) -> str:
    return f"{value * 100.0:.2f}%"


def _format_bps(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _ordered_regime_thresholds(regime_thresholds: dict[str, float]) -> dict[str, float]:
    ordered: dict[str, float] = {}
    if "DEFAULT" in regime_thresholds:
        ordered["DEFAULT"] = _round_metric(float(regime_thresholds["DEFAULT"]))
    for regime_name, factor in sorted(regime_thresholds.items()):
        if regime_name == "DEFAULT":
            continue
        ordered[regime_name] = _round_metric(float(factor))
    return ordered


def _surface_payload_from_values(
    *,
    symbol: str,
    signal_threshold_value: float,
    regime_thresholds: dict[str, float],
    signal_threshold_source: str | None = None,
    signal_threshold_path: str | None = None,
    regime_threshold_source: str | None = None,
    regime_threshold_path: str | None = None,
) -> dict[str, Any]:
    payload = {
        "symbol": symbol,
        "signal_threshold": {"value": _round_metric(signal_threshold_value)},
        "regime_thresholds": _ordered_regime_thresholds(regime_thresholds),
    }
    if signal_threshold_source is not None:
        payload["signal_threshold_source"] = signal_threshold_source
    if signal_threshold_path is not None:
        payload["signal_threshold_path"] = signal_threshold_path
    if regime_threshold_source is not None:
        payload["regime_threshold_source"] = regime_threshold_source
    if regime_threshold_path is not None:
        payload["regime_threshold_path"] = regime_threshold_path
    return payload


def _surface_payload(surface: ThresholdSurface) -> dict[str, Any]:
    return _surface_payload_from_values(
        symbol=surface.symbol,
        signal_threshold_value=surface.signal_threshold_value,
        regime_thresholds=surface.regime_thresholds,
        signal_threshold_source=surface.signal_threshold_source,
        signal_threshold_path=surface.signal_threshold_path,
        regime_threshold_source=surface.regime_threshold_source,
        regime_threshold_path=surface.regime_threshold_path,
    )


def _replay_metrics_payload(metrics: ReplayMetrics) -> dict[str, Any]:
    return {
        "eligible_bars": int(metrics.eligible_bars),
        "active_bars": int(metrics.active_bars),
        "buy_count": int(metrics.buy_count),
        "sell_count": int(metrics.sell_count),
        "activation_rate": _round_metric(metrics.activation_rate),
        "max_daily_activation_rate": _round_metric(metrics.max_daily_activation_rate),
        "selection_score": _round_metric(metrics.mean_forward_bps_3) if metrics.mean_forward_bps_3 is not None else None,
        "mean_forward_bps_1": _round_metric(metrics.mean_forward_bps_1) if metrics.mean_forward_bps_1 is not None else None,
        "mean_forward_bps_3": _round_metric(metrics.mean_forward_bps_3) if metrics.mean_forward_bps_3 is not None else None,
        "hit_rate_1": _round_metric(metrics.hit_rate_1) if metrics.hit_rate_1 is not None else None,
        "hit_rate_3": _round_metric(metrics.hit_rate_3) if metrics.hit_rate_3 is not None else None,
        "p50_abs_score": _round_metric(metrics.p50_abs_score) if metrics.p50_abs_score is not None else None,
        "p75_abs_score": _round_metric(metrics.p75_abs_score) if metrics.p75_abs_score is not None else None,
        "p80_abs_score": _round_metric(metrics.p80_abs_score) if metrics.p80_abs_score is not None else None,
        "p90_abs_score": _round_metric(metrics.p90_abs_score) if metrics.p90_abs_score is not None else None,
        "regime_counts": dict(metrics.regime_counts),
    }


def _window_spec_payload(window_spec: ReplayWindowSpec) -> dict[str, Any]:
    return {
        "train_days": list(window_spec.train_days),
        "validation_days": list(window_spec.validation_days),
        "forward_days": list(window_spec.forward_days),
    }


def _candidate_surface_contract_payload(
    *,
    symbol: str,
    promotable: bool,
    promotability_blockers: Sequence[str],
) -> dict[str, Any]:
    return {
        "candidate_surface_policy": "per-asset-only",
        "candidate_signal_threshold_path": f"assets.{symbol}.signal_threshold.value",
        "candidate_regime_threshold_path": f"assets.{symbol}.regime_thresholds",
        "promotable": promotable,
        "promotability_blockers": list(promotability_blockers),
    }


def _metric_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return float(candidate - baseline)


def _activation_ratio(
    candidate_metrics: ReplayMetrics,
    baseline_metrics: ReplayMetrics,
) -> float | None:
    if baseline_metrics.activation_rate <= 0.0:
        return None
    return float(candidate_metrics.activation_rate / baseline_metrics.activation_rate)


def _guardrail_check(
    *,
    name: str,
    passed: bool | None,
    actual: Any,
    requirement: str,
) -> dict[str, Any]:
    status = "not_applicable" if passed is None else (
        "pass" if passed else "fail")
    return {
        "name": name,
        "status": status,
        "passed": passed,
        "actual": actual,
        "requirement": requirement,
    }


def _build_split_comparison_payload(
    *,
    split_name: str,
    baseline_metrics: ReplayMetrics,
    candidate_metrics: ReplayMetrics | None,
    promotable: bool,
    promotability_blockers: Sequence[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    candidate_present = candidate_metrics is not None
    activation_ratio = (
        _activation_ratio(candidate_metrics, baseline_metrics)
        if candidate_metrics is not None
        else None
    )
    delta_forward_edge = (
        _metric_delta(candidate_metrics.mean_forward_bps_3,
                      baseline_metrics.mean_forward_bps_3)
        if candidate_metrics is not None
        else None
    )
    guardrails: list[dict[str, Any]] = [
        _guardrail_check(
            name="candidate_present",
            passed=candidate_present,
            actual=candidate_present,
            requirement="candidate surface must be selected",
        ),
        _guardrail_check(
            name="candidate_promotable_under_source_mode",
            passed=promotable if candidate_present else False,
            actual={
                "promotable": promotable,
                "blockers": list(promotability_blockers),
            },
            requirement="candidate surface must map cleanly onto per-asset overlay paths",
        ),
    ]
    if candidate_metrics is None:
        guardrails.extend(
            [
                _guardrail_check(
                    name="eligible_bars",
                    passed=None,
                    actual=None,
                    requirement=f">= {int(args.min_samples)}",
                ),
                _guardrail_check(
                    name="active_bars",
                    passed=None,
                    actual=None,
                    requirement=f">= {int(args.min_active_bars)}",
                ),
                _guardrail_check(
                    name="activation_rate_range",
                    passed=None,
                    actual=None,
                    requirement=(
                        f"between {float(args.min_activation_rate):.4f} and "
                        f"{float(args.max_activation_rate):.4f}"
                    ),
                ),
                _guardrail_check(
                    name="max_daily_activation_rate",
                    passed=None,
                    actual=None,
                    requirement=f"<= {float(args.max_daily_activation_rate):.4f}",
                ),
                _guardrail_check(
                    name="mean_forward_bps_3_floor",
                    passed=None,
                    actual=None,
                    requirement=f">= {float(args.min_forward_edge_bps):.4f}",
                ),
            ]
        )
    else:
        guardrails.extend(
            [
                _guardrail_check(
                    name="eligible_bars",
                    passed=candidate_metrics.eligible_bars >= int(
                        args.min_samples),
                    actual=int(candidate_metrics.eligible_bars),
                    requirement=f">= {int(args.min_samples)}",
                ),
                _guardrail_check(
                    name="active_bars",
                    passed=candidate_metrics.active_bars >= int(
                        args.min_active_bars),
                    actual=int(candidate_metrics.active_bars),
                    requirement=f">= {int(args.min_active_bars)}",
                ),
                _guardrail_check(
                    name="activation_rate_range",
                    passed=(
                        float(args.min_activation_rate)
                        <= candidate_metrics.activation_rate
                        <= float(args.max_activation_rate)
                    ),
                    actual=_round_metric(candidate_metrics.activation_rate),
                    requirement=(
                        f"between {float(args.min_activation_rate):.4f} and "
                        f"{float(args.max_activation_rate):.4f}"
                    ),
                ),
                _guardrail_check(
                    name="max_daily_activation_rate",
                    passed=candidate_metrics.max_daily_activation_rate <= float(
                        args.max_daily_activation_rate),
                    actual=_round_metric(
                        candidate_metrics.max_daily_activation_rate),
                    requirement=f"<= {float(args.max_daily_activation_rate):.4f}",
                ),
                _guardrail_check(
                    name="mean_forward_bps_3_floor",
                    passed=(candidate_metrics.mean_forward_bps_3 is not None)
                    and candidate_metrics.mean_forward_bps_3 >= float(args.min_forward_edge_bps),
                    actual=_round_metric(candidate_metrics.mean_forward_bps_3)
                    if candidate_metrics.mean_forward_bps_3 is not None
                    else None,
                    requirement=f">= {float(args.min_forward_edge_bps):.4f}",
                ),
                _guardrail_check(
                    name="activation_ratio_vs_baseline",
                    passed=(
                        None
                        if activation_ratio is None
                        else float(args.min_activation_ratio_vs_baseline)
                        <= activation_ratio
                        <= float(args.max_activation_ratio_vs_baseline)
                    ),
                    actual=_round_metric(
                        activation_ratio) if activation_ratio is not None else None,
                    requirement=(
                        "not applicable when baseline activation is zero; otherwise between "
                        f"{float(args.min_activation_ratio_vs_baseline):.4f} and "
                        f"{float(args.max_activation_ratio_vs_baseline):.4f}"
                    ),
                ),
            ]
        )
    if split_name == "validation":
        guardrails.append(
            _guardrail_check(
                name="validation_improvement_bps",
                passed=(
                    None
                    if delta_forward_edge is None
                    else delta_forward_edge >= float(args.min_validation_improvement_bps)
                ),
                actual=_round_metric(
                    delta_forward_edge) if delta_forward_edge is not None else None,
                requirement=f">= {float(args.min_validation_improvement_bps):.4f}",
            )
        )
    elif split_name == "forward":
        guardrails.append(
            _guardrail_check(
                name="forward_degradation_bps",
                passed=(
                    None
                    if delta_forward_edge is None
                    else delta_forward_edge >= -float(args.max_forward_degradation_bps)
                ),
                actual=_round_metric(
                    delta_forward_edge) if delta_forward_edge is not None else None,
                requirement=f">= -{float(args.max_forward_degradation_bps):.4f}",
            )
        )
    all_guardrails_pass = all(
        check["passed"] is not False for check in guardrails)
    return {
        "window": split_name,
        "decision_metric": "mean_forward_bps_3",
        "candidate_present": candidate_present,
        "candidate_promotable": promotable,
        "promotability_blockers": list(promotability_blockers),
        "baseline": _replay_metrics_payload(baseline_metrics),
        "candidate": _replay_metrics_payload(candidate_metrics) if candidate_metrics is not None else None,
        "delta": {
            "activation_rate": _round_metric(
                _metric_delta(
                    candidate_metrics.activation_rate,
                    baseline_metrics.activation_rate,
                )
            )
            if candidate_metrics is not None
            else None,
            "active_bars": (
                int(candidate_metrics.active_bars - baseline_metrics.active_bars)
                if candidate_metrics is not None
                else None
            ),
            "mean_forward_bps_3": _round_metric(delta_forward_edge) if delta_forward_edge is not None else None,
            "hit_rate_3": (
                _round_metric(
                    _metric_delta(candidate_metrics.hit_rate_3,
                                  baseline_metrics.hit_rate_3)
                )
                if candidate_metrics is not None
                and candidate_metrics.hit_rate_3 is not None
                and baseline_metrics.hit_rate_3 is not None
                else None
            ),
            "activation_ratio_vs_baseline": _round_metric(activation_ratio) if activation_ratio is not None else None,
        },
        "guardrails": guardrails,
        "all_guardrails_pass": all_guardrails_pass,
    }


def _candidate_status_blockers(
    candidate: CandidateEvaluation | None,
    candidate_blockers: Sequence[str],
) -> list[str]:
    if candidate is not None:
        return list(candidate.promotability_blockers)
    return list(candidate_blockers or ["candidate_missing"])


def _build_v1_baseline_metrics(calibrations: Sequence[SymbolCalibration]) -> dict[str, Any]:
    return {
        "input_source": RESEARCH_INPUT_SOURCE,
        "evidence_tier": "research-only",
        "symbols": {
            calibration.symbol: {
                "surface": _surface_payload(calibration.surface),
                "sample_counts": {
                    "total": int(calibration.total_samples),
                    "non_deferred": int(calibration.non_deferred_samples),
                    "deferred": int(calibration.deferred_samples),
                    "neutral": int(calibration.neutral_samples),
                    "side_bearing": int(calibration.side_bearing_samples),
                },
                "regime_counts": dict(calibration.regime_counts),
                "estimated_activation_rate": _round_metric(calibration.current_estimated_activation_rate),
                "abs_score_percentiles": {
                    "p50": _round_metric(calibration.p50_abs_score),
                    "p75": _round_metric(calibration.p75_abs_score),
                    "p80": _round_metric(calibration.p80_abs_score),
                    "p90": _round_metric(calibration.p90_abs_score),
                },
            }
            for calibration in calibrations
        },
    }


def _build_v1_candidate_metrics(calibrations: Sequence[SymbolCalibration]) -> dict[str, Any]:
    return {
        "input_source": RESEARCH_INPUT_SOURCE,
        "evidence_tier": "research-only",
        "symbols": {
            calibration.symbol: {
                "surface": _surface_payload_from_values(
                    symbol=calibration.symbol,
                    signal_threshold_value=calibration.proposed_signal_threshold_value,
                    regime_thresholds=calibration.proposed_regime_thresholds,
                ),
                "estimated_activation_rate": _round_metric(calibration.proposed_estimated_activation_rate),
                "warnings": list(calibration.warnings),
                "regime_breakdown": [
                    {
                        "regime": regime_summary.regime,
                        "sample_count": int(regime_summary.sample_count),
                        "neutral_count": int(regime_summary.neutral_count),
                        "side_count": int(regime_summary.side_count),
                        "current_factor": _round_metric(regime_summary.current_factor),
                        "current_effective_threshold": _round_metric(regime_summary.current_effective_threshold),
                        "proposed_factor": _round_metric(regime_summary.proposed_factor) if regime_summary.proposed_factor is not None else None,
                        "proposed_effective_threshold": _round_metric(regime_summary.proposed_effective_threshold) if regime_summary.proposed_effective_threshold is not None else None,
                    }
                    for regime_summary in calibration.regime_summaries
                ],
            }
            for calibration in calibrations
        },
    }


def _build_research_only_split_metrics(split_name: str) -> dict[str, Any]:
    return {
        "input_source": RESEARCH_INPUT_SOURCE,
        "evidence_tier": "research-only",
        "window": split_name,
        "status": "unavailable_in_research_mode",
        "reason": (
            "aurora-logs mode does not replay live RegimeDetector, shield cascade, side-bias state, "
            "or explicit train/validation/forward holdouts"
        ),
    }


def _build_v2_baseline_metrics(calibrations: Sequence[V2SymbolCalibration]) -> dict[str, Any]:
    return {
        "input_source": PRODUCTION_INPUT_SOURCE,
        "evidence_tier": "production-aligned",
        "symbols": {
            calibration.symbol: {
                "surface": _surface_payload(calibration.surface),
                "candidate_surface_contract": _candidate_surface_contract_payload(
                    symbol=calibration.symbol,
                    promotable=not calibration.candidate_blockers,
                    promotability_blockers=calibration.candidate_blockers,
                ),
                "window_spec": _window_spec_payload(calibration.window_spec),
                "recorder_bar_count": int(calibration.recorder_bar_count),
                "feature_log_audit": {
                    "exists": calibration.feature_log_audit.exists,
                    "file_size_mb": _round_metric(calibration.feature_log_audit.file_size_mb),
                    "sampled_lines": int(calibration.feature_log_audit.sampled_lines),
                    "sampled_keys": list(calibration.feature_log_audit.sampled_keys),
                    "has_timestamp_fields": calibration.feature_log_audit.has_timestamp_fields,
                    "warnings": list(calibration.feature_log_audit.warnings),
                },
                "train": _replay_metrics_payload(calibration.current_train_metrics),
                "validation": _replay_metrics_payload(calibration.current_validation_metrics),
                "forward": _replay_metrics_payload(calibration.current_forward_metrics),
                "warnings": list(calibration.warnings),
            }
            for calibration in calibrations
        },
    }


def _build_v2_candidate_metrics(calibrations: Sequence[V2SymbolCalibration]) -> dict[str, Any]:
    return {
        "input_source": PRODUCTION_INPUT_SOURCE,
        "evidence_tier": "production-aligned",
        "selection_metric": "validation.mean_forward_bps_3",
        "symbols": {
            calibration.symbol: {
                "candidate_present": calibration.candidate is not None,
                "quantile": _round_metric(calibration.candidate.quantile) if calibration.candidate is not None else None,
                "surface": _surface_payload(calibration.candidate.surface) if calibration.candidate is not None else None,
                "train": _replay_metrics_payload(calibration.candidate.train_metrics) if calibration.candidate is not None else None,
                "validation": _replay_metrics_payload(calibration.candidate.validation_metrics) if calibration.candidate is not None else None,
                "forward": _replay_metrics_payload(calibration.candidate.forward_metrics) if calibration.candidate is not None else None,
                "train_guardrails_ok": calibration.candidate.train_guardrails_ok if calibration.candidate is not None else False,
                "validation_guardrails_ok": calibration.candidate.validation_guardrails_ok if calibration.candidate is not None else False,
                "forward_guardrails_ok": calibration.candidate.forward_guardrails_ok if calibration.candidate is not None else False,
                "train_guardrail_failures": list(calibration.candidate.train_guardrail_failures) if calibration.candidate is not None else [],
                "validation_guardrail_failures": list(calibration.candidate.validation_guardrail_failures) if calibration.candidate is not None else _candidate_status_blockers(calibration.candidate, calibration.candidate_blockers),
                "forward_guardrail_failures": list(calibration.candidate.forward_guardrail_failures) if calibration.candidate is not None else _candidate_status_blockers(calibration.candidate, calibration.candidate_blockers),
                "promotable": calibration.candidate.promotable if calibration.candidate is not None else False,
                "promotability_blockers": _candidate_status_blockers(calibration.candidate, calibration.candidate_blockers),
                "candidate_surface_contract": _candidate_surface_contract_payload(
                    symbol=calibration.symbol,
                    promotable=calibration.candidate.promotable if calibration.candidate is not None else False,
                    promotability_blockers=_candidate_status_blockers(
                        calibration.candidate, calibration.candidate_blockers),
                ),
                "warnings": list(calibration.warnings),
            }
            for calibration in calibrations
        },
    }


def _build_v2_validation_metrics(
    calibrations: Sequence[V2SymbolCalibration],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "input_source": PRODUCTION_INPUT_SOURCE,
        "evidence_tier": "production-aligned",
        "decision_metric": "mean_forward_bps_3",
        "comparison_rule": (
            "candidate validation mean_forward_bps_3 must beat baseline by at least "
            f"{float(args.min_validation_improvement_bps):.4f} bps"
        ),
        "symbols": {
            calibration.symbol: _build_split_comparison_payload(
                split_name="validation",
                baseline_metrics=calibration.current_validation_metrics,
                candidate_metrics=(
                    calibration.candidate.validation_metrics
                    if calibration.candidate is not None
                    else None
                ),
                promotable=(
                    calibration.candidate.promotable
                    if calibration.candidate is not None
                    else False
                ),
                promotability_blockers=(
                    _candidate_status_blockers(
                        calibration.candidate, calibration.candidate_blockers)
                ),
                args=args,
            )
            for calibration in calibrations
        },
    }


def _build_v2_forward_metrics(
    calibrations: Sequence[V2SymbolCalibration],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "input_source": PRODUCTION_INPUT_SOURCE,
        "evidence_tier": "production-aligned",
        "decision_metric": "mean_forward_bps_3",
        "comparison_rule": (
            "candidate forward mean_forward_bps_3 must not degrade versus baseline by more than "
            f"{float(args.max_forward_degradation_bps):.4f} bps"
        ),
        "symbols": {
            calibration.symbol: _build_split_comparison_payload(
                split_name="forward",
                baseline_metrics=calibration.current_forward_metrics,
                candidate_metrics=(
                    calibration.candidate.forward_metrics
                    if calibration.candidate is not None
                    else None
                ),
                promotable=(
                    calibration.candidate.promotable
                    if calibration.candidate is not None
                    else False
                ),
                promotability_blockers=(
                    _candidate_status_blockers(
                        calibration.candidate, calibration.candidate_blockers)
                ),
                args=args,
            )
            for calibration in calibrations
        },
    }


def _build_run_manifest(
    *,
    args: argparse.Namespace,
    ordered_symbols: Sequence[str],
    threshold_surfaces: dict[str, ThresholdSurface],
    verdict: str,
    evidence_tier: str,
    promotable: bool,
    promotability_by_symbol: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    production_aligned = str(args.input_source) == PRODUCTION_INPUT_SOURCE
    return {
        "standard": CALIBRATION_STANDARD,
        "calibrator_class": CALIBRATION_CLASS,
        "strategy_id": "aurora",
        "input_source": str(args.input_source),
        "evidence_tier": evidence_tier,
        "production_aligned": production_aligned,
        "verdict": verdict,
        "promotable": promotable,
        "promotion_eligible": production_aligned and promotable and verdict == "GO_CANDIDATE",
        "writes_canonical_yaml": False,
        "threshold_source_mode": str(args.threshold_source_mode),
        "candidate_surface_policy": "per-asset-only",
        "active_runtime_surfaces": list(AURORA_ACTIVE_SURFACES),
        "non_goals": list(AURORA_NON_GOALS),
        "runtime_truth_anchors": list(AURORA_RUNTIME_TRUTH_ANCHORS),
        "recommended_artifacts": list(RECOMMENDED_ARTIFACTS),
        "symbols": list(ordered_symbols),
        "threshold_surfaces": {
            symbol: {
                "signal_threshold_source": surface.signal_threshold_source,
                "signal_threshold_path": surface.signal_threshold_path,
                "regime_threshold_source": surface.regime_threshold_source,
                "regime_threshold_path": surface.regime_threshold_path,
                **_candidate_surface_contract_payload(
                    symbol=symbol,
                    promotable=bool(promotability_by_symbol.get(
                        symbol, {}).get("promotable")),
                    promotability_blockers=promotability_by_symbol.get(
                        symbol, {}).get("promotability_blockers", []),
                ),
            }
            for symbol, surface in threshold_surfaces.items()
        },
        "date_window": {
            "from_date": args.from_date.isoformat(),
            "to_date": args.to_date.isoformat(),
        },
        "artifacts": {},
    }


def _build_overlay_from_v1(calibrations: list[SymbolCalibration]) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    for calibration in calibrations:
        ordered_regime_thresholds = _ordered_regime_thresholds(
            calibration.proposed_regime_thresholds)
        assets[calibration.symbol] = {
            "signal_threshold": {
                "value": _round_metric(calibration.proposed_signal_threshold_value),
            },
            "regime_thresholds": ordered_regime_thresholds,
        }
    return {"assets": assets}


def _render_v1_report(
    *,
    calibrations: list[SymbolCalibration],
    args: argparse.Namespace,
    overlay: dict[str, Any],
    data_source_description: str,
    log_paths: list[Path],
) -> str:
    verdict = "NO_GO_RESEARCH_ONLY"
    lines: list[str] = []
    lines.append("# Aurora Threshold Calibration Report")
    lines.append("")
    lines.append("## Verdict")
    lines.append(f"- {verdict}")
    lines.append("")
    lines.append("## Scope")
    lines.append(
        "- Calibration class: production calibrator operating on active Aurora threshold surfaces only."
    )
    lines.append(
        "- Objective: calibrate only live per-symbol Aurora threshold surface for assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds."
    )
    lines.append(
        "- Evidence tier for this run: research-only diagnostic mode because input-source=aurora-logs does not replay live RegimeDetector, shield cascade, or validation holdout."
    )
    lines.append(
        "- Non-goals: no weights, no direction_strength_scoring, no feature_neutrals, no neutral_threshold, no cooldown, no holding period, no business-logic mutation, no canonical YAML writeback."
    )
    lines.append(
        f"- Symbols: {', '.join(calibration.symbol for calibration in calibrations)}")
    lines.append(
        f"- Date window: {args.from_date.isoformat()} through {args.to_date.isoformat()} inclusive"
    )
    lines.append("")
    lines.append("## Runtime Truth Anchors")
    lines.append(
        "- FACT: active Aurora live math is QuadraticScoringKernel with shield cascade on the production path."
    )
    lines.append(
        "- FACT: per-symbol signal_threshold.value is read in Aurora decision path before kernel invocation when assets.<SYMBOL>.signal_threshold.enabled=true."
    )
    lines.append(
        "- FACT: per-symbol assets.<SYMBOL>.regime_thresholds override the global regime threshold map in live runtime."
    )
    lines.append(
        "- FACT: signal_weights, direction_strength_scoring, and feature_neutrals are legacy surfaces for current Aurora live math."
    )
    lines.append(
        "- FACT: this tool does not write back into aurora.yaml; it emits artifact-only overlay and report files."
    )
    lines.append("")
    lines.append("## Dataset Audit")
    lines.append(f"- Input source: {data_source_description}")
    lines.append(f"- Log files matched: {len(log_paths)}")
    for log_path in log_paths:
        lines.append(f"- {log_path.as_posix()}")
    lines.append("")
    lines.append("## Candidate Search Method")
    lines.append(
        "- Method: fit candidate signal_threshold.value from the chosen |score| quantile across non-deferred QUADRATIC_DECISION_TRACE samples."
    )
    lines.append(
        "- Method: emit regime-specific factors only when per-regime non-deferred sample coverage clears min-regime-samples."
    )
    lines.append(
        "- Limitation: this mode does not replay RegimeDetector, shield cascade, side-bias state, or validation holdout; therefore it cannot yield a production GO verdict."
    )
    lines.append("")
    lines.append("## Guardrails")
    lines.append(
        f"- min_samples={int(args.min_samples)}"
    )
    lines.append(
        f"- min_regime_samples={int(args.min_regime_samples)}"
    )
    lines.append(
        f"- target_quantile={float(args.target_quantile):.2f}"
    )
    lines.append(
        "- Fail-closed rule: log-only evidence remains NO_GO_RESEARCH_ONLY even when a candidate overlay is emitted."
    )
    lines.append("")
    lines.append("## Baseline vs Candidate")
    for calibration in calibrations:
        lines.append("")
        lines.append(f"### {calibration.symbol}")
        lines.append(
            f"- Sample counts: total={calibration.total_samples}, non_deferred={calibration.non_deferred_samples}, deferred={calibration.deferred_samples}, neutral={calibration.neutral_samples}, side_bearing={calibration.side_bearing_samples}"
        )
        lines.append(f"- Regime counts: {calibration.regime_counts}")
        lines.append(
            f"- Observed |score| percentiles: p50={calibration.p50_abs_score:.6f}, p75={calibration.p75_abs_score:.6f}, p80={calibration.p80_abs_score:.6f}, p90={calibration.p90_abs_score:.6f}"
        )
        lines.append(
            f"- Current signal_threshold.value: {calibration.surface.signal_threshold_value:.6f}"
        )
        lines.append(
            f"- Current regime_thresholds: {calibration.surface.regime_thresholds}")
        lines.append(
            f"- Proposed signal_threshold.value: {calibration.proposed_signal_threshold_value:.6f}"
        )
        lines.append(
            f"- Proposed regime_thresholds: {calibration.proposed_regime_thresholds}")
        lines.append(
            f"- Estimated activation rate: current={_format_ratio(calibration.current_estimated_activation_rate)}, proposed={_format_ratio(calibration.proposed_estimated_activation_rate)}"
        )
        lines.append("")
        lines.append("#### Regime Breakdown")
        lines.append(
            "| regime | samples | neutral | side | p50_abs | p75_abs | p80_abs | p90_abs | current_factor | current_effective | proposed_factor | proposed_effective |"
        )
        lines.append(
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        )
        for regime_summary in calibration.regime_summaries:
            proposed_factor = (
                f"{regime_summary.proposed_factor:.6f}"
                if regime_summary.proposed_factor is not None
                else "-"
            )
            proposed_effective = (
                f"{regime_summary.proposed_effective_threshold:.6f}"
                if regime_summary.proposed_effective_threshold is not None
                else "-"
            )
            lines.append(
                f"| {regime_summary.regime} | {regime_summary.sample_count} | {regime_summary.neutral_count} | {regime_summary.side_count} | {regime_summary.p50_abs_score:.6f} | {regime_summary.p75_abs_score:.6f} | {regime_summary.p80_abs_score:.6f} | {regime_summary.p90_abs_score:.6f} | {regime_summary.current_factor:.6f} | {regime_summary.current_effective_threshold:.6f} | {proposed_factor} | {proposed_effective} |"
            )
        if calibration.warnings:
            lines.append("")
            lines.append("#### Warnings")
            for warning in calibration.warnings:
                lines.append(f"- {warning}")
    lines.append("")
    lines.append("## Candidate Overlay")
    lines.append("```yaml")
    lines.append(yaml.safe_dump(overlay, sort_keys=False,
                 allow_unicode=False).rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## Facts")
    lines.append(
        "- FACT: the calibrator reads only aurora.assets.<SYMBOL>.signal_threshold.value and aurora.assets.<SYMBOL>.regime_thresholds from aurora.yaml."
    )
    lines.append(
        "- FACT: the calibrator does not read or tune neutral_threshold, weights, cooldown, or holding_period."
    )
    lines.append(
        "- FACT: the v1 dataset is log-derived from QUADRATIC_DECISION_TRACE entries in aurora_core logs."
    )
    lines.append("")
    lines.append("## Inferences")
    lines.append(
        "- INFERENCE: lowering per-symbol effective thresholds toward observed upper score quantiles should increase side activation rate relative to current config surface."
    )
    lines.append(
        "- INFERENCE: regime-specific factors are only emitted where regime sample coverage clears the configured minimum."
    )
    lines.append("")
    lines.append("## Assumptions")
    lines.append(
        "- ASSUMPTION: QUADRATIC_DECISION_TRACE score distribution is an acceptable v1 proxy for threshold crossing calibration without replaying full decision state."
    )
    lines.append(
        "- ASSUMPTION: deep-merge application of the emitted overlay preserves the existing signal_threshold.enabled=true flag in base config."
    )
    lines.append("")
    lines.append("## Unknowns")
    lines.append(
        "- UNKNOWN: whether the proposed threshold surface improves realized trading quality downstream after execution, objective gating, and risk controls."
    )
    lines.append(
        "- UNKNOWN: whether other time windows would suggest different regime factors for ETHUSDT and SOLUSDT."
    )
    lines.append("")
    lines.append("## Risks")
    lines.append(
        "- Risk: log-derived score quantiles can mask regime reconstruction, shield attenuation, and side-bias effects that materially alter live activation quality."
    )
    lines.append(
        "- Risk: promoting a log-only candidate directly would overstate evidence quality and violate fail-closed calibration governance."
    )
    lines.append("")
    lines.append("## Next Action")
    lines.append(
        "- Next action: rerun this calibrator with --input-source recorder-features-v2 before treating any threshold overlay as production-aligned."
    )
    return "\n".join(lines) + "\n"


def _safe_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "" or text.upper() == "NONE":
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _safe_bool(raw: Any) -> bool:
    return str(raw).strip().lower() == "true"


def _iter_dates(from_date: date, to_date: date) -> Iterable[date]:
    current = from_date
    while current <= to_date:
        yield current
        current += timedelta(days=1)


def _load_recorder_bars(
    *,
    recorder_dir: Path,
    symbols: Sequence[str],
    from_date: date,
    to_date: date,
    tf_sec: int,
    pillar_weights: dict[str, float] | None = None,
) -> dict[str, list[RecorderBar]]:
    bars_by_symbol: dict[str, list[RecorderBar]] = {
        symbol: [] for symbol in symbols}
    for day in _iter_dates(from_date, to_date):
        day_dir = recorder_dir / day.isoformat()
        if not day_dir.exists():
            continue
        for symbol in symbols:
            csv_path = day_dir / f"{symbol}_{tf_sec}.csv"
            if not csv_path.is_file():
                continue
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    timestamp_raw = row.get("timestamp")
                    timestamp_ms = _safe_float(timestamp_raw)
                    close = _safe_float(row.get("close"))
                    if timestamp_ms is None or close is None:
                        continue
                    try:
                        timestamp = datetime.fromtimestamp(
                            timestamp_ms / 1000.0)
                    except (OSError, OverflowError, ValueError):
                        continue
                    bars_by_symbol[symbol].append(
                        RecorderBar(
                            timestamp=timestamp,
                            timestamp_ms=int(timestamp_ms),
                            symbol=symbol,
                            tf_sec=int(_safe_float(
                                row.get("tf_sec")) or tf_sec),
                            ready=_safe_bool(row.get("ready")),
                            not_ready_reasons=str(
                                row.get("not_ready_reasons") or ""),
                            close=close,
                            high=_safe_float(row.get("high")),
                            low=_safe_float(row.get("low")),
                            pillar_sum=_safe_float(row.get("feat_pillar_sum")),
                            pillar_tactician=_safe_float(
                                row.get("feat_pillar_tactician")),
                            pillar_operator=_safe_float(
                                row.get("feat_pillar_operator")),
                            pillar_strategist=_safe_float(
                                row.get("feat_pillar_strategist")),
                            spread_bps=_safe_float(row.get("feat_spread_bps")),
                            volatility_state=_safe_float(
                                row.get("feat_volatility_state")),
                            price_motion_norm=_safe_float(row.get("pm_norm")),
                        )
                    )
    # Recalculate pillar_sum from raw pillars if pillar_weights override provided.
    # PROVENANCE: object.__setattr__ bypasses frozen dataclass to mutate pillar_sum
    # in-place. This is calibrator-only — live Aurora pillar_sum is set by feature
    # assembly and must NOT be mutated at runtime. Any replay consuming these bars
    # inherits calibrator-overridden pillar_sum, not the original live value.
    if pillar_weights:
        w_t = pillar_weights.get("tactician", 0.60)
        w_o = pillar_weights.get("operator", 0.25)
        w_s = pillar_weights.get("strategist", 0.15)
        mutated_count = 0
        for symbol in symbols:
            for bar in bars_by_symbol[symbol]:
                t = bar.pillar_tactician
                o = bar.pillar_operator
                s = bar.pillar_strategist
                if t is not None and o is not None and s is not None:
                    new_sum = t * w_t + o * w_o + s * w_s
                    object.__setattr__(bar, "pillar_sum", new_sum)
                    object.__setattr__(
                        bar,
                        "pillar_sum_provenance_class",
                        CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE,
                    )
                    mutated_count += 1
        LOG.warning(
            "SYNTHETIC_PILLAR_SUM: pillar_sum recalculated from raw pillars; "
            "provenance_class=%s live_feature_derived=False mutated_fields=['pillar_sum'] "
            "mutation_reason=pillar_weights_recalculation mutated_bars=%d pillar_weights=%s",
            CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE,
            mutated_count,
            pillar_weights,
        )
    for symbol in symbols:
        bars_by_symbol[symbol].sort(key=lambda item: item.timestamp_ms)
    return bars_by_symbol


def _collect_feature_log_audit(symbol: str, feature_log_dir: Path) -> FeatureLogAudit:
    log_path = feature_log_dir / f"{symbol}.log"
    warnings: list[str] = []
    if not log_path.is_file():
        return FeatureLogAudit(
            symbol=symbol,
            exists=False,
            file_size_mb=0.0,
            sampled_lines=0,
            sampled_keys=[],
            has_timestamp_fields=False,
            warnings=[
                f"Missing feature log file for {symbol}: {log_path.as_posix()}"],
        )

    sampled_keys: set[str] = set()
    sampled_lines = 0
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(
                    f"Unreadable JSON line encountered while sampling {log_path.name}")
                break
            if isinstance(payload, dict):
                sampled_keys.update(str(key) for key in payload.keys())
                sampled_lines += 1
            if sampled_lines >= 20:
                break

    has_timestamp_fields = any(
        key in {"ts", "timestamp", "datetime",
                "bar_close_ts", "close_boundary_ts_ms"}
        for key in sampled_keys
    )
    if not has_timestamp_fields:
        warnings.append(
            f"Sampled feature-log keys for {symbol} expose no explicit timestamp field; recorder remains the only auditable time axis."
        )
    if sampled_lines == 0:
        warnings.append(
            f"No parseable JSON lines sampled from {log_path.name}")

    return FeatureLogAudit(
        symbol=symbol,
        exists=True,
        file_size_mb=log_path.stat().st_size / (1024.0 * 1024.0),
        sampled_lines=sampled_lines,
        sampled_keys=sorted(sampled_keys),
        has_timestamp_fields=has_timestamp_fields,
        warnings=warnings,
    )


def _bar_is_eligible(bar: RecorderBar) -> bool:
    return bar.ready and bar.pillar_sum is not None and math.isfinite(bar.close)


def _window_spec_for_bars(
    bars: Sequence[RecorderBar],
    *,
    validation_days: int,
    forward_days: int,
    min_train_days: int,
) -> ReplayWindowSpec:
    eligible_days = sorted(
        {bar.timestamp.date().isoformat()
         for bar in bars if _bar_is_eligible(bar)}
    )
    required_days = int(validation_days) + \
        int(forward_days) + int(min_train_days)
    if len(eligible_days) < required_days:
        raise CalibrationError(
            "V2 replay requires at least "
            f"{required_days} unique eligible dates for train/validation/forward windows; "
            f"found only {len(eligible_days)}"
        )

    forward_start = len(eligible_days) - int(forward_days)
    validation_start = forward_start - int(validation_days)
    train_days = eligible_days[:validation_start]
    validation_window = eligible_days[validation_start:forward_start]
    forward_window = eligible_days[forward_start:]
    if len(train_days) < int(min_train_days):
        raise CalibrationError(
            "V2 replay train window is too short after reserving validation and forward holdouts: "
            f"train_days={len(train_days)} < min_train_days={int(min_train_days)}"
        )
    return ReplayWindowSpec(
        train_days=train_days,
        validation_days=validation_window,
        forward_days=forward_window,
    )


def _split_for_bar_timestamp(timestamp: datetime, window_spec: ReplayWindowSpec) -> str:
    day_iso = timestamp.date().isoformat()
    if window_spec.forward_days and day_iso >= window_spec.forward_days[0]:
        return "forward"
    if window_spec.validation_days and day_iso >= window_spec.validation_days[0]:
        return "validation"
    return "train"


def _build_scoring_features(bar: RecorderBar, regime_payload: dict[str, Any]) -> dict[str, Any]:
    features: dict[str, Any] = {
        "price": bar.close,
        "high": bar.high if bar.high is not None else bar.close,
        "low": bar.low if bar.low is not None else bar.close,
        "bar_close_ts": bar.timestamp_ms,
    }
    pillar_contribs: dict[str, float] = {}
    if bar.pillar_sum is not None:
        features["pillar_sum"] = bar.pillar_sum
    if bar.pillar_operator is not None:
        features["pillar_operator"] = bar.pillar_operator
        pillar_contribs["operator"] = bar.pillar_operator
    if bar.pillar_strategist is not None:
        features["pillar_strategist"] = bar.pillar_strategist
        pillar_contribs["strategist"] = bar.pillar_strategist
    if bar.spread_bps is not None:
        features["spread_bps"] = bar.spread_bps
    if bar.volatility_state is not None:
        features["volatility_state"] = bar.volatility_state
    if bar.price_motion_norm is not None:
        features["price_motion_norm"] = bar.price_motion_norm
    if pillar_contribs:
        features["pillar_contribs"] = pillar_contribs

    regime = str(regime_payload.get("regime") or "UNCERTAIN")
    features["regime"] = regime
    features["regime_ts_ms"] = int(regime_payload.get(
        "ts_ms") or regime_payload.get("ts") or bar.timestamp_ms)
    return features


def _build_detector_event(symbol: str, bar: RecorderBar) -> Any:
    from vfoundation.core.protocol import Message

    payload = {
        "symbol": symbol,
        "ts": int(bar.timestamp_ms),
        "tf_sec": int(bar.tf_sec),
        "close_boundary_ts_ms": int(bar.timestamp_ms),
        "features": {
            "price": bar.close,
            "high": bar.high if bar.high is not None else bar.close,
            "low": bar.low if bar.low is not None else bar.close,
        },
    }
    return Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="aurora_threshold_calibrator",
        dst="any",
        ts=int(bar.timestamp_ms),
        ttl_ms=min(30_000, max(1_000, int(bar.tf_sec * 1000))),
        pld=payload,
        why="offline_regime_replay",
    )


def _build_shield_cascade(decision_cfg: Any, mode_manager: Any) -> tuple[Any, Any | None]:
    from apps.reference.shared.decision_primitives.shields.base import ShieldCascade
    from apps.reference.shared.decision_primitives.shields.context_shield import ContextShield
    from apps.reference.shared.decision_primitives.shields.danger_zone import DangerZoneShield
    from apps.reference.shared.decision_primitives.shields.memory_shield import MemoryShield

    scoring_engine_cfg = getattr(decision_cfg, "scoring_engine", None)
    if scoring_engine_cfg is None or not getattr(scoring_engine_cfg, "shield_enabled", False):
        raise CalibrationError(
            "V2 replay requires scoring_engine.shield_enabled=true in Aurora config")

    shields: list[Any] = []

    dz_cfg = getattr(scoring_engine_cfg, "danger_zone_shield", None)
    if dz_cfg and getattr(dz_cfg, "enabled", True):
        shields.append(
            DangerZoneShield(
                vol_threshold=float(getattr(dz_cfg, "vol_threshold", 0.95)),
                spread_threshold=float(
                    getattr(dz_cfg, "spread_threshold", 50.0)),
                motion_threshold=float(
                    getattr(dz_cfg, "motion_threshold", 3.0)),
            )
        )

    ctx_cfg = getattr(scoring_engine_cfg, "context_shield", None)
    if ctx_cfg and getattr(ctx_cfg, "enabled", True):
        shields.append(
            ContextShield(
                regime_multipliers=dict(
                    getattr(ctx_cfg, "regime_multipliers", {})),
                default_multiplier=float(
                    getattr(ctx_cfg, "default_multiplier", 1.0)),
                no_regime_multiplier=float(
                    getattr(ctx_cfg, "no_regime_multiplier", 0.5)),
                ttl_ms=int(getattr(ctx_cfg, "ttl_ms", 14_400_000)),
                stale_mult_normal=float(
                    getattr(ctx_cfg, "stale_mult_normal", 0.7)),
                stale_mult_danger=float(
                    getattr(ctx_cfg, "stale_mult_danger", 0.35)),
                danger_regimes=list(
                    getattr(ctx_cfg, "danger_regimes", ["HIGH_VOLATILITY"])),
            )
        )

    memory_shield = None
    mem_cfg = getattr(scoring_engine_cfg, "memory_shield", None)
    if mem_cfg and getattr(mem_cfg, "enabled", True):
        if mode_manager is not None:
            mem_cfg = mode_manager.apply_memory_shield_overrides(mem_cfg)
        memory_shield = MemoryShield(
            decay_rate=float(getattr(mem_cfg, "decay_rate", 0.95)),
            max_states=int(getattr(mem_cfg, "max_states", 200)),
            unknown_threshold=float(
                getattr(mem_cfg, "unknown_threshold", 10.0)),
            exploring_threshold=float(
                getattr(mem_cfg, "exploring_threshold", 50.0)),
            unknown_multiplier=float(
                getattr(mem_cfg, "unknown_multiplier", 0.6)),
            exploring_multiplier=float(
                getattr(mem_cfg, "exploring_multiplier", 0.8)),
            known_multiplier=float(getattr(mem_cfg, "known_multiplier", 1.0)),
            storage_path=None,
            flush_interval_sec=float(
                getattr(mem_cfg, "flush_interval_sec", 60.0)),
        )
        shields.append(memory_shield)

    return ShieldCascade(shields), memory_shield


def _resolve_aurora_basis_required_bars(typed_config: Any) -> int:
    from apps.reference.contracts.strategy_compatibility_matrix import get_active_strategy_profile

    profile = get_active_strategy_profile(typed_config, "aurora")
    if profile is None:
        raise CalibrationError(
            "Active Aurora compatibility profile is missing; cannot resolve basis_required_bars"
        )
    return int(profile.basis_required_bars)


def _candidate_blockers_for_surface(surface: ThresholdSurface) -> list[str]:
    blockers: list[str] = []
    if surface.signal_threshold_source != "asset_override":
        blockers.append(
            f"Current live signal threshold resolves via {surface.signal_threshold_path}; candidate emission remains limited to assets.<SYMBOL>.signal_threshold.value and is therefore disabled in this mode."
        )
    if surface.regime_threshold_source != "asset_override":
        blockers.append(
            f"Current live regime thresholds resolve via {surface.regime_threshold_path}; candidate emission remains limited to assets.<SYMBOL>.regime_thresholds and is therefore disabled in this mode."
        )
    return blockers


def _prune_history(history: deque[int], cutoff_ms: int) -> None:
    while history and history[0] < cutoff_ms:
        history.popleft()


def _make_side_bias_state(
    decision_cfg: Any,
    buy_history_ms: deque[int],
    sell_history_ms: deque[int],
    now_ms: int,
) -> Any:
    from apps.reference.shared.decision_primitives.scoring_kernel import SideBiasState

    window_sec = float(getattr(decision_cfg, "side_bias_window_sec", 420.0))
    cutoff_ms = now_ms - int(window_sec * 1000.0)
    _prune_history(buy_history_ms, cutoff_ms)
    _prune_history(sell_history_ms, cutoff_ms)
    return SideBiasState(
        buy_count=len(buy_history_ms),
        sell_count=len(sell_history_ms),
        window_sec=window_sec,
        target_ratio=float(
            getattr(decision_cfg, "side_bias_target_ratio", 0.72)),
        penalty_factor=float(
            getattr(decision_cfg, "side_bias_penalty_factor", 0.25)),
        min_intents=int(getattr(decision_cfg, "side_bias_min_intents", 18)),
    )


def _forward_bps(bars: Sequence[RecorderBar], index: int, side: str, horizon: int) -> float | None:
    if side not in {"buy", "sell"}:
        return None
    target_index = index + horizon
    if target_index >= len(bars):
        return None
    entry = bars[index].close
    exit_price = bars[target_index].close
    if not math.isfinite(entry) or entry <= 0.0 or not math.isfinite(exit_price):
        return None
    raw_bps = ((exit_price - entry) / entry) * 10_000.0
    if side == "sell":
        raw_bps *= -1.0
    return raw_bps


def _summarize_metrics(observations: Sequence[ReplayObservation], split: str) -> ReplayMetrics:
    relevant = [obs for obs in observations if obs.eligible and obs.split ==
                split and not obs.deferred]
    active = [obs for obs in relevant if obs.side in {"buy", "sell"}]
    activation_rate = (len(active) / len(relevant)) if relevant else 0.0

    daily_totals: dict[date, int] = defaultdict(int)
    daily_active: dict[date, int] = defaultdict(int)
    regime_counts: Counter[str] = Counter()
    abs_scores: list[float] = []
    for obs in relevant:
        obs_date = obs.timestamp.date()
        daily_totals[obs_date] += 1
        regime_counts[obs.regime] += 1
        if obs.score is not None:
            abs_scores.append(abs(obs.score))
        if obs.side in {"buy", "sell"}:
            daily_active[obs_date] += 1

    max_daily_activation_rate = 0.0
    for obs_date, total in daily_totals.items():
        if total <= 0:
            continue
        max_daily_activation_rate = max(
            max_daily_activation_rate,
            daily_active.get(obs_date, 0) / total,
        )

    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _hit_rate(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(1 for value in values if value > 0.0) / len(values)

    forward_1 = [
        obs.forward_bps_1 for obs in active if obs.forward_bps_1 is not None]
    forward_3 = [
        obs.forward_bps_3 for obs in active if obs.forward_bps_3 is not None]

    return ReplayMetrics(
        eligible_bars=len(relevant),
        active_bars=len(active),
        buy_count=sum(1 for obs in active if obs.side == "buy"),
        sell_count=sum(1 for obs in active if obs.side == "sell"),
        activation_rate=activation_rate,
        max_daily_activation_rate=max_daily_activation_rate,
        mean_forward_bps_1=_mean([float(value) for value in forward_1]),
        mean_forward_bps_3=_mean([float(value) for value in forward_3]),
        hit_rate_1=_hit_rate([float(value) for value in forward_1]),
        hit_rate_3=_hit_rate([float(value) for value in forward_3]),
        p50_abs_score=_percentile(abs_scores, 0.50) if abs_scores else None,
        p75_abs_score=_percentile(abs_scores, 0.75) if abs_scores else None,
        p80_abs_score=_percentile(abs_scores, 0.80) if abs_scores else None,
        p90_abs_score=_percentile(abs_scores, 0.90) if abs_scores else None,
        regime_counts=dict(sorted(regime_counts.items())),
    )


def _replay_symbol(
    *,
    symbol: str,
    bars: Sequence[RecorderBar],
    typed_config: Any,
    surface: ThresholdSurface,
    window_spec: ReplayWindowSpec,
) -> list[ReplayObservation]:
    from apps.reference.config_models import OperationalMode
    from apps.reference.domains.decision_making.primitives.operational_mode import ModeManager
    from apps.reference.shared.decision_primitives.scoring_kernel import QuadraticScoringKernel
    from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

    if not bars:
        raise CalibrationError(
            f"No recorder bars available for symbol {symbol}")

    decision_cfg = typed_config.strategies.aurora.decision
    op_mode = getattr(decision_cfg, "operational_mode",
                      OperationalMode.PARANOID)
    mode_manager = ModeManager(op_mode)
    shield_fn, memory_shield = _build_shield_cascade(
        decision_cfg, mode_manager)
    basis_required_bars = _resolve_aurora_basis_required_bars(typed_config)

    clock = _ReplayClock(now_ms=bars[0].timestamp_ms)
    fsm = _ReplayFsm()
    detector = RegimeDetector(typed_config, fsm, clock=clock)

    current_side = ""
    buy_history_ms: deque[int] = deque()
    sell_history_ms: deque[int] = deque()
    bars_seen_since_restart = 0
    neutral_threshold = decimal.Decimal(
        str(getattr(decision_cfg, "neutral_threshold", "0.0")))
    delta_price_cap_pct = decimal.Decimal(
        str(getattr(getattr(decision_cfg, "signals", None),
            "delta_price_cap_pct", "0.02"))
    )
    score_multiplier = float(getattr(decision_cfg, "score_multiplier", 1.0))
    normalize_mode = str(
        getattr(getattr(decision_cfg, "signals", None),
                "normalize_signals_mode", "signed_v2")
    )

    observations: list[ReplayObservation] = []
    for index, bar in enumerate(bars):
        bars_seen_since_restart += 1
        clock.set_now_ms(bar.timestamp_ms)
        detector.handle_event(_build_detector_event(symbol, bar))
        regime_payload = fsm.latest_regime_payload(symbol)
        features = _build_scoring_features(bar, regime_payload)
        split = _split_for_bar_timestamp(bar.timestamp, window_spec)

        if basis_required_bars > 0 and bars_seen_since_restart < basis_required_bars:
            observations.append(
                ReplayObservation(
                    timestamp=bar.timestamp,
                    symbol=symbol,
                    split=split,
                    eligible=False,
                    regime=str(features.get("regime") or "UNCERTAIN"),
                    regime_confidence=_safe_float(
                        regime_payload.get("confidence")),
                    score=None,
                    side="",
                    deferred=False,
                    shield_multiplier=None,
                    threshold_factor=None,
                    thr_buy=None,
                    thr_sell=None,
                    forward_bps_1=None,
                    forward_bps_3=None,
                )
            )
            continue

        eligible = _bar_is_eligible(bar)

        if not eligible:
            observations.append(
                ReplayObservation(
                    timestamp=bar.timestamp,
                    symbol=symbol,
                    split=split,
                    eligible=False,
                    regime=str(features.get("regime") or "UNCERTAIN"),
                    regime_confidence=_safe_float(
                        regime_payload.get("confidence")),
                    score=None,
                    side="",
                    deferred=True,
                    shield_multiplier=None,
                    threshold_factor=None,
                    thr_buy=None,
                    thr_sell=None,
                    forward_bps_1=None,
                    forward_bps_3=None,
                )
            )
            continue

        side_bias_state = _make_side_bias_state(
            decision_cfg, buy_history_ms, sell_history_ms, bar.timestamp_ms)
        result = QuadraticScoringKernel.compute(
            symbol=symbol,
            features=features,
            warmup_readiness={},
            price=decimal.Decimal(str(bar.close)),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=decimal.Decimal(
                str(surface.signal_threshold_value)),
            regime_name=str(features.get("regime") or "UNCERTAIN"),
            regime_thresholds=dict(surface.regime_thresholds),
            side_bias_state=side_bias_state,
            direction_strength_cfg={},
            delta_price_cap_pct=delta_price_cap_pct,
            neutral_threshold=neutral_threshold,
            current_side=current_side,
            normalize_mode=normalize_mode,
            shield_fn=shield_fn,
            pillar_contribs=features.get("pillar_contribs", {}),
            score_multiplier=score_multiplier,
        )

        current_side = result.side
        if result.side == "buy":
            buy_history_ms.append(bar.timestamp_ms)
            if memory_shield is not None:
                memory_shield.record_visit(
                    symbol, features, bar_close_ts=bar.timestamp_ms // 1000)
        elif result.side == "sell":
            sell_history_ms.append(bar.timestamp_ms)
            if memory_shield is not None:
                memory_shield.record_visit(
                    symbol, features, bar_close_ts=bar.timestamp_ms // 1000)

        observations.append(
            ReplayObservation(
                timestamp=bar.timestamp,
                symbol=symbol,
                split=split,
                eligible=True,
                regime=str(features.get("regime") or "UNCERTAIN"),
                regime_confidence=_safe_float(
                    regime_payload.get("confidence")),
                score=float(result.score),
                side=str(result.side),
                deferred=bool(result.deferred),
                shield_multiplier=float(result.shield_multiplier),
                threshold_factor=float(result.threshold_factor),
                thr_buy=float(result.thr_buy),
                thr_sell=float(result.thr_sell),
                forward_bps_1=_forward_bps(bars, index, result.side, 1),
                forward_bps_3=_forward_bps(bars, index, result.side, 3),
            )
        )

    return observations


def _surface_from_observations(
    *,
    symbol: str,
    observations: Sequence[ReplayObservation],
    quantile: float,
    min_regime_samples: int,
) -> ThresholdSurface:
    train_scores = [
        abs(obs.score)
        for obs in observations
        if obs.eligible and obs.split == "train" and not obs.deferred and obs.score is not None
    ]
    positive_train_scores = [float(value)
                             for value in train_scores if float(value) > 0.0]
    if len(positive_train_scores) == 0:
        raise CalibrationError(
            f"No train scores available to fit V2 candidate for {symbol}")
    base_threshold = _percentile(positive_train_scores, quantile)
    if not math.isfinite(base_threshold) or base_threshold <= 0.0:
        raise CalibrationError(
            f"Invalid V2 base threshold for {symbol}: {base_threshold}")

    regime_scores: dict[str, list[float]] = defaultdict(list)
    for obs in observations:
        if not obs.eligible or obs.split != "train" or obs.deferred or obs.score is None:
            continue
        abs_score = abs(obs.score)
        if abs_score > 0.0:
            regime_scores[obs.regime].append(abs_score)

    proposed = {"DEFAULT": 1.0}
    for regime_name, values in sorted(regime_scores.items()):
        if len(values) < min_regime_samples:
            continue
        effective_threshold = _percentile(
            [float(value) for value in values], quantile)
        factor = effective_threshold / base_threshold
        if not math.isfinite(factor) or factor <= 0.0:
            raise CalibrationError(
                f"Invalid V2 regime factor for {symbol} regime {regime_name}: {factor}"
            )
        if regime_name != "DEFAULT":
            proposed[regime_name] = factor

    return ThresholdSurface(
        symbol=symbol,
        signal_threshold_value=base_threshold,
        regime_thresholds=proposed,
        signal_threshold_source="asset_override",
        signal_threshold_path=f"assets.{symbol}.signal_threshold.value",
        regime_threshold_source="asset_override",
        regime_threshold_path=f"assets.{symbol}.regime_thresholds",
    )


def _guardrail_failures(
    metrics: ReplayMetrics,
    args: argparse.Namespace,
    *,
    split_name: str,
    baseline_metrics: ReplayMetrics | None = None,
) -> list[str]:
    failures: list[str] = []
    if metrics.eligible_bars < int(args.min_samples):
        failures.append(
            f"{split_name}:eligible_bars={metrics.eligible_bars} < min_samples={int(args.min_samples)}"
        )
    if metrics.active_bars < int(args.min_active_bars):
        failures.append(
            f"{split_name}:active_bars={metrics.active_bars} < min_active_bars={int(args.min_active_bars)}"
        )
    if metrics.activation_rate < float(args.min_activation_rate):
        failures.append(
            f"{split_name}:activation_rate={metrics.activation_rate:.4f} < min_activation_rate={float(args.min_activation_rate):.4f}"
        )
    if metrics.activation_rate > float(args.max_activation_rate):
        failures.append(
            f"{split_name}:activation_rate={metrics.activation_rate:.4f} > max_activation_rate={float(args.max_activation_rate):.4f}"
        )
    if metrics.max_daily_activation_rate > float(args.max_daily_activation_rate):
        failures.append(
            f"{split_name}:max_daily_activation_rate={metrics.max_daily_activation_rate:.4f} > max_daily_activation_rate={float(args.max_daily_activation_rate):.4f}"
        )
    if metrics.mean_forward_bps_3 is None:
        failures.append(
            f"{split_name}:mean_forward_bps_3 is unavailable on this split")
    elif metrics.mean_forward_bps_3 < float(args.min_forward_edge_bps):
        failures.append(
            f"{split_name}:mean_forward_bps_3={metrics.mean_forward_bps_3:.2f} < min_forward_edge_bps={float(args.min_forward_edge_bps):.2f}"
        )
    if baseline_metrics is not None and baseline_metrics.activation_rate > 0.0:
        activation_ratio = metrics.activation_rate / baseline_metrics.activation_rate
        if activation_ratio < float(args.min_activation_ratio_vs_baseline):
            failures.append(
                f"{split_name}:activation_ratio_vs_baseline={activation_ratio:.4f} < min_activation_ratio_vs_baseline={float(args.min_activation_ratio_vs_baseline):.4f}"
            )
        if activation_ratio > float(args.max_activation_ratio_vs_baseline):
            failures.append(
                f"{split_name}:activation_ratio_vs_baseline={activation_ratio:.4f} > max_activation_ratio_vs_baseline={float(args.max_activation_ratio_vs_baseline):.4f}"
            )
    if split_name == "validation":
        baseline_edge = None if baseline_metrics is None else baseline_metrics.mean_forward_bps_3
        if baseline_edge is None and baseline_metrics is not None and (baseline_metrics.active_bars or 0) > 0:
            failures.append(
                "validation:baseline mean_forward_bps_3 is unavailable")
        elif baseline_edge is not None and metrics.mean_forward_bps_3 is not None:
            delta_edge = metrics.mean_forward_bps_3 - baseline_edge
            if delta_edge < float(args.min_validation_improvement_bps):
                failures.append(
                    f"validation:delta_mean_forward_bps_3={delta_edge:.2f} < min_validation_improvement_bps={float(args.min_validation_improvement_bps):.2f}"
                )
    if split_name == "forward":
        baseline_edge = None if baseline_metrics is None else baseline_metrics.mean_forward_bps_3
        if baseline_edge is None and baseline_metrics is not None and (baseline_metrics.active_bars or 0) > 0:
            failures.append(
                "forward:baseline mean_forward_bps_3 is unavailable")
        elif baseline_edge is not None and metrics.mean_forward_bps_3 is not None:
            delta_edge = metrics.mean_forward_bps_3 - baseline_edge
            if delta_edge < -float(args.max_forward_degradation_bps):
                failures.append(
                    f"forward:delta_mean_forward_bps_3={delta_edge:.2f} < -max_forward_degradation_bps=-{float(args.max_forward_degradation_bps):.2f}"
                )
    return failures


def _candidate_objective(metrics: ReplayMetrics) -> tuple[float, float, float]:
    return (
        float(metrics.mean_forward_bps_3 if metrics.mean_forward_bps_3 is not None else float("-inf")),
        float(metrics.hit_rate_3 or 0.0),
        float(metrics.active_bars),
    )


def _fit_v2_symbol_calibration(
    *,
    symbol: str,
    surface: ThresholdSurface,
    bars: Sequence[RecorderBar],
    feature_log_audit: FeatureLogAudit,
    typed_config: Any,
    args: argparse.Namespace,
) -> V2SymbolCalibration:
    if not bars:
        raise CalibrationError(f"No recorder data found for {symbol}")

    window_spec = _window_spec_for_bars(
        bars,
        validation_days=int(args.validation_days),
        forward_days=int(args.forward_days),
        min_train_days=int(args.min_train_days),
    )
    current_observations = _replay_symbol(
        symbol=symbol,
        bars=bars,
        typed_config=typed_config,
        surface=surface,
        window_spec=window_spec,
    )
    current_train = _summarize_metrics(current_observations, "train")
    current_validation = _summarize_metrics(current_observations, "validation")
    current_forward = _summarize_metrics(current_observations, "forward")

    warnings = list(feature_log_audit.warnings)
    if current_train.eligible_bars < int(args.min_samples):
        raise CalibrationError(
            f"Symbol {symbol} has only {current_train.eligible_bars} train bars after replay; requires at least {int(args.min_samples)}"
        )

    candidate_blockers = _candidate_blockers_for_surface(surface)
    if candidate_blockers:
        warnings.extend(candidate_blockers)
        return V2SymbolCalibration(
            symbol=symbol,
            surface=surface,
            window_spec=window_spec,
            recorder_bar_count=len(bars),
            feature_log_audit=feature_log_audit,
            current_train_metrics=current_train,
            current_validation_metrics=current_validation,
            current_forward_metrics=current_forward,
            candidate=None,
            candidate_blockers=candidate_blockers,
            warnings=warnings,
        )

    best_candidate: CandidateEvaluation | None = None
    for quantile in args.quantile_grid:
        candidate_surface = _surface_from_observations(
            symbol=symbol,
            observations=current_observations,
            quantile=float(quantile),
            min_regime_samples=int(args.min_regime_samples),
        )
        candidate_observations = _replay_symbol(
            symbol=symbol,
            bars=bars,
            typed_config=typed_config,
            surface=candidate_surface,
            window_spec=window_spec,
        )
        train_metrics = _summarize_metrics(candidate_observations, "train")
        validation_metrics = _summarize_metrics(
            candidate_observations, "validation")
        forward_metrics = _summarize_metrics(candidate_observations, "forward")
        train_failures = _guardrail_failures(
            train_metrics,
            args,
            split_name="train",
        )
        validation_failures = _guardrail_failures(
            validation_metrics,
            args,
            split_name="validation",
            baseline_metrics=current_validation,
        )
        forward_failures = _guardrail_failures(
            forward_metrics,
            args,
            split_name="forward",
            baseline_metrics=current_forward,
        )
        evaluation = CandidateEvaluation(
            quantile=float(quantile),
            surface=candidate_surface,
            train_metrics=train_metrics,
            validation_metrics=validation_metrics,
            forward_metrics=forward_metrics,
            train_guardrails_ok=not train_failures,
            validation_guardrails_ok=not validation_failures,
            forward_guardrails_ok=not forward_failures,
            train_guardrail_failures=train_failures,
            validation_guardrail_failures=validation_failures,
            forward_guardrail_failures=forward_failures,
            promotable=True,
            promotability_blockers=[],
        )
        if not evaluation.train_guardrails_ok:
            continue
        if best_candidate is None or _candidate_objective(validation_metrics) > _candidate_objective(best_candidate.validation_metrics):
            best_candidate = evaluation

    if best_candidate is None:
        warnings.append(
            f"No V2 candidate for {symbol} cleared train-time guardrails across quantile grid {args.quantile_grid}."
        )

    return V2SymbolCalibration(
        symbol=symbol,
        surface=surface,
        window_spec=window_spec,
        recorder_bar_count=len(bars),
        feature_log_audit=feature_log_audit,
        current_train_metrics=current_train,
        current_validation_metrics=current_validation,
        current_forward_metrics=current_forward,
        candidate=best_candidate,
        candidate_blockers=[],
        warnings=warnings,
    )


def _build_overlay_from_v2(calibrations: list[V2SymbolCalibration]) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    for calibration in calibrations:
        if calibration.candidate is None:
            continue
        surface = calibration.candidate.surface
        ordered_regime_thresholds = _ordered_regime_thresholds(
            surface.regime_thresholds)
        assets[calibration.symbol] = {
            "signal_threshold": {"value": _round_metric(surface.signal_threshold_value)},
            "regime_thresholds": ordered_regime_thresholds,
        }
    return {"assets": assets}


def _v2_verdict(calibrations: Sequence[V2SymbolCalibration]) -> str:
    if not calibrations:
        return "NO_GO_CANDIDATE"
    for calibration in calibrations:
        candidate = calibration.candidate
        if candidate is None:
            return "NO_GO_CANDIDATE"
        if not candidate.promotable:
            return "NO_GO_CANDIDATE"
        if not candidate.validation_guardrails_ok:
            return "NO_GO_CANDIDATE"
        if not candidate.forward_guardrails_ok:
            return "NO_GO_CANDIDATE"
    return "GO_CANDIDATE"


def _render_metrics_table_row(label: str, metrics: ReplayMetrics) -> str:
    return (
        f"| {label} | {metrics.eligible_bars} | {metrics.active_bars} | {_format_ratio(metrics.activation_rate)} | "
        f"{metrics.buy_count} | {metrics.sell_count} | {_format_ratio(metrics.max_daily_activation_rate)} | "
        f"{_format_bps(metrics.mean_forward_bps_1)} | {_format_bps(metrics.mean_forward_bps_3)} | "
        f"{_format_ratio(metrics.hit_rate_1) if metrics.hit_rate_1 is not None else '-'} | "
        f"{_format_ratio(metrics.hit_rate_3) if metrics.hit_rate_3 is not None else '-'} |"
    )


def _render_v2_report(
    *,
    calibrations: list[V2SymbolCalibration],
    args: argparse.Namespace,
    overlay: dict[str, Any],
    typed_config: Any,
) -> str:
    verdict = _v2_verdict(calibrations)
    lines: list[str] = []
    lines.append("# Aurora Threshold Calibration Report")
    lines.append("")
    lines.append("## Verdict")
    lines.append(f"- {verdict}")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Calibration class: production.")
    lines.append(
        "- Objective: calibrate only active Aurora threshold surfaces that are currently consumed by live runtime scoring."
    )
    lines.append(
        "- Evidence tier for this run: production-aligned proxy because replay reuses live RegimeDetector, QuadraticScoringKernel, shield cascade, and sequential side-bias state over recorder bars."
    )
    lines.append(
        "- Non-goals: no signal_weights tuning, no direction_strength_scoring tuning, no feature_neutrals tuning, no neutral_threshold tuning, no cooldown/reentry/holding-period changes, no canonical YAML writeback."
    )
    lines.append(
        f"- Symbols: {', '.join(calibration.symbol for calibration in calibrations)}")
    lines.append(
        f"- Date window: {args.from_date.isoformat()} through {args.to_date.isoformat()} inclusive"
    )
    lines.append(f"- Recorder timeframe: {int(args.tf_sec)}s")
    lines.append("")
    lines.append("## Active Runtime Surface Under Calibration")
    lines.append(
        "- Tuned surfaces only: assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds."
    )
    lines.append(
        "- Baseline-only surfaces that may be observed but are never written by this tool: decision.signal_threshold and decision.regime_threshold_multipliers."
    )
    for calibration in calibrations:
        lines.append(
            f"- {calibration.symbol}: signal_threshold source={calibration.surface.signal_threshold_source} path={calibration.surface.signal_threshold_path}; regime_threshold source={calibration.surface.regime_threshold_source} path={calibration.surface.regime_threshold_path}"
        )
    lines.append("")
    lines.append("## Threshold Source Mode")
    lines.append(f"- Selected mode: {args.threshold_source_mode}")
    lines.append(
        "- Candidate overlay policy: per-asset-only. The calibrator emits candidate_aurora_threshold_overlay.yaml and never mutates canonical aurora YAML."
    )
    lines.append(
        "- Promotable means the live baseline already resolves through the same per-asset surfaces that the candidate overlay can safely target."
    )
    lines.append(
        "- Non-promotable means the baseline resolves through a global decision surface, so emitting a per-asset overlay would not preserve source-path parity and is therefore blocked fail-closed."
    )
    lines.append("")
    lines.append("## Runtime Truth Anchors")
    lines.append(
        "- FACT: active Aurora scoring path is QuadraticScoringKernel with DangerZone -> Context -> Memory shield cascade."
    )
    lines.append(
        "- FACT: this V2 replay reuses live RegimeDetector, QuadraticScoringKernel, live side-bias parameters, and live shield config."
    )
    lines.append(
        "- FACT: in live-effective mode the baseline threshold source follows live Aurora runtime semantics: use assets.<SYMBOL>.signal_threshold.value only when the per-symbol override is enabled, otherwise fall back to decision.signal_threshold."
    )
    lines.append(
        "- FACT: per-symbol signal_threshold.value and per-symbol regime_thresholds are the only tuned surfaces emitted by this tool."
    )
    lines.append(
        "- FACT: signal_weights, direction_strength_scoring, and feature_neutrals are legacy Aurora surfaces and are not tuned here."
    )
    lines.append(
        "- FACT: feature logs are audited for schema evidence, but recorder is the only auditable timestamp backbone because sampled feature-log keys expose no explicit timestamp field."
    )
    lines.append("")
    lines.append("## Dataset Audit")
    lines.append(
        f"- Config timeframe_sec: {getattr(typed_config.strategies.aurora, 'timeframe_sec', 'unknown')}"
    )
    for calibration in calibrations:
        audit = calibration.feature_log_audit
        lines.append("")
        lines.append(f"### {calibration.symbol}")
        lines.append(
            f"- Recorder bars loaded: {calibration.recorder_bar_count}")
        lines.append(
            "- Window spec: "
            f"train_days={len(calibration.window_spec.train_days)}, "
            f"validation_days={len(calibration.window_spec.validation_days)}, "
            f"forward_days={len(calibration.window_spec.forward_days)}"
        )
        lines.append(
            f"- Validation window: {calibration.window_spec.validation_days[0]} -> {calibration.window_spec.validation_days[-1]}"
        )
        lines.append(
            f"- Forward window: {calibration.window_spec.forward_days[0]} -> {calibration.window_spec.forward_days[-1]}"
        )
        lines.append(
            f"- Feature log: exists={audit.exists}, size_mb={audit.file_size_mb:.2f}, sampled_lines={audit.sampled_lines}, has_timestamp_fields={audit.has_timestamp_fields}"
        )
        lines.append(f"- Sampled feature-log keys: {audit.sampled_keys}")
        if audit.warnings:
            for warning in audit.warnings:
                lines.append(f"- WARNING: {warning}")
    lines.append("")
    lines.append("## Candidate Search Method")
    lines.append(
        "- Method: replay the current surface first, then fit candidate thresholds from train-split absolute score quantiles."
    )
    lines.append(
        "- Method: replay each candidate surface through live RegimeDetector, live shield cascade, and QuadraticScoringKernel using identical recorder bars."
    )
    lines.append(
        "- Fail-closed rule: when the current live baseline resolves through a global decision threshold or global regime-threshold map, candidate emission is disabled because this tool still emits per-asset overlay surfaces only."
    )
    lines.append(
        "- Candidate ranking objective: among candidates that clear train guardrails, maximize validation metrics tuple (mean_forward_bps_3, hit_rate_3, active_bars)."
    )
    lines.append("")
    lines.append("## Guardrails")
    lines.append(f"- min_train_days={int(args.min_train_days)}")
    lines.append(f"- validation_days={int(args.validation_days)}")
    lines.append(f"- forward_days={int(args.forward_days)}")
    lines.append(f"- min_samples={int(args.min_samples)}")
    lines.append(f"- min_active_bars={int(args.min_active_bars)}")
    lines.append(
        f"- min_activation_rate={float(args.min_activation_rate):.4f}")
    lines.append(
        f"- max_activation_rate={float(args.max_activation_rate):.4f}")
    lines.append(
        f"- max_daily_activation_rate={float(args.max_daily_activation_rate):.4f}")
    lines.append(
        f"- activation_ratio_vs_baseline range=[{float(args.min_activation_ratio_vs_baseline):.4f}, {float(args.max_activation_ratio_vs_baseline):.4f}] when baseline activation is non-zero"
    )
    lines.append(
        f"- min_forward_edge_bps={float(args.min_forward_edge_bps):.2f}")
    lines.append(
        f"- min_validation_improvement_bps={float(args.min_validation_improvement_bps):.2f}")
    lines.append(
        f"- max_forward_degradation_bps={float(args.max_forward_degradation_bps):.2f}")
    lines.append(
        f"- quantile_grid={list(float(value) for value in args.quantile_grid)}")
    lines.append("")
    lines.append("## Baseline vs Candidate")
    for calibration in calibrations:
        validation_artifact = _build_split_comparison_payload(
            split_name="validation",
            baseline_metrics=calibration.current_validation_metrics,
            candidate_metrics=(
                calibration.candidate.validation_metrics
                if calibration.candidate is not None
                else None
            ),
            promotable=(
                calibration.candidate.promotable
                if calibration.candidate is not None
                else False
            ),
            promotability_blockers=(
                calibration.candidate.promotability_blockers
                if calibration.candidate is not None
                else calibration.candidate_blockers
            ),
            args=args,
        )
        forward_artifact = _build_split_comparison_payload(
            split_name="forward",
            baseline_metrics=calibration.current_forward_metrics,
            candidate_metrics=(
                calibration.candidate.forward_metrics
                if calibration.candidate is not None
                else None
            ),
            promotable=(
                calibration.candidate.promotable
                if calibration.candidate is not None
                else False
            ),
            promotability_blockers=(
                calibration.candidate.promotability_blockers
                if calibration.candidate is not None
                else calibration.candidate_blockers
            ),
            args=args,
        )
        lines.append("")
        lines.append(f"### {calibration.symbol}")
        lines.append(
            "| split | eligible_bars | active_bars | activation_rate | buy_count | sell_count | max_daily_activation | mean_fwd_1_bps | mean_fwd_3_bps | hit_rate_1 | hit_rate_3 |"
        )
        lines.append(
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        )
        lines.append(_render_metrics_table_row(
            "current/train", calibration.current_train_metrics))
        lines.append(_render_metrics_table_row(
            "current/validation", calibration.current_validation_metrics))
        lines.append(_render_metrics_table_row(
            "current/forward", calibration.current_forward_metrics))
        lines.append(
            f"- Current signal_threshold.value: {calibration.surface.signal_threshold_value:.6f}"
        )
        lines.append(
            f"- Current signal_threshold source: {calibration.surface.signal_threshold_source} ({calibration.surface.signal_threshold_path})"
        )
        lines.append(
            f"- Current regime_thresholds: {calibration.surface.regime_thresholds}"
        )
        lines.append(
            f"- Current regime_threshold source: {calibration.surface.regime_threshold_source} ({calibration.surface.regime_threshold_path})"
        )
        lines.append(
            f"- Promotable under current source mode: {not calibration.candidate_blockers}"
        )
        if calibration.candidate_blockers:
            lines.append("- Promotability blockers:")
            for blocker in calibration.candidate_blockers:
                lines.append(f"  - {blocker}")
        if calibration.candidate is not None:
            lines.append(_render_metrics_table_row(
                "candidate/train", calibration.candidate.train_metrics))
            lines.append(_render_metrics_table_row(
                "candidate/validation", calibration.candidate.validation_metrics))
            lines.append(_render_metrics_table_row(
                "candidate/forward", calibration.candidate.forward_metrics))
            lines.append(
                f"- Candidate quantile: {calibration.candidate.quantile:.2f}")
            lines.append(
                f"- Proposed signal_threshold.value: {calibration.candidate.surface.signal_threshold_value:.6f}"
            )
            lines.append(
                f"- Proposed regime_thresholds: {calibration.candidate.surface.regime_thresholds}"
            )
            lines.append(
                f"- Validation guardrails ok: {calibration.candidate.validation_guardrails_ok}"
            )
            lines.append(
                f"- Forward guardrails ok: {calibration.candidate.forward_guardrails_ok}"
            )
            if calibration.candidate.train_guardrail_failures:
                lines.append("- Train guardrail failures:")
                for failure in calibration.candidate.train_guardrail_failures:
                    lines.append(f"  - {failure}")
            if calibration.candidate.validation_guardrail_failures:
                lines.append("- Validation guardrail failures:")
                for failure in calibration.candidate.validation_guardrail_failures:
                    lines.append(f"  - {failure}")
            if calibration.candidate.forward_guardrail_failures:
                lines.append("- Forward guardrail failures:")
                for failure in calibration.candidate.forward_guardrail_failures:
                    lines.append(f"  - {failure}")
        else:
            lines.append("- No candidate cleared train-time guardrails.")
        lines.append(
            f"- Validation delta mean_forward_bps_3: {validation_artifact['delta']['mean_forward_bps_3']}"
        )
        lines.append(
            f"- Forward delta mean_forward_bps_3: {forward_artifact['delta']['mean_forward_bps_3']}"
        )
        if calibration.warnings:
            lines.append("- Symbol warnings:")
            for warning in calibration.warnings:
                lines.append(f"  - {warning}")
    lines.append("")
    lines.append("## Validation")
    for calibration in calibrations:
        validation_artifact = _build_split_comparison_payload(
            split_name="validation",
            baseline_metrics=calibration.current_validation_metrics,
            candidate_metrics=(
                calibration.candidate.validation_metrics
                if calibration.candidate is not None
                else None
            ),
            promotable=(
                calibration.candidate.promotable
                if calibration.candidate is not None
                else False
            ),
            promotability_blockers=(
                calibration.candidate.promotability_blockers
                if calibration.candidate is not None
                else calibration.candidate_blockers
            ),
            args=args,
        )
        lines.append("")
        lines.append(f"### {calibration.symbol}")
        lines.append(
            f"- Candidate present: {validation_artifact['candidate_present']} | promotable: {validation_artifact['candidate_promotable']} | all_guardrails_pass: {validation_artifact['all_guardrails_pass']}"
        )
        lines.append(
            f"- Validation delta mean_forward_bps_3: {validation_artifact['delta']['mean_forward_bps_3']}"
        )
        lines.append(
            f"- Validation activation ratio vs baseline: {validation_artifact['delta']['activation_ratio_vs_baseline']}"
        )
        for check in validation_artifact["guardrails"]:
            lines.append(
                f"- {check['name']}: {check['status']} (actual={check['actual']}, requirement={check['requirement']})"
            )
    lines.append("")
    lines.append("## Forward Evaluation")
    for calibration in calibrations:
        forward_artifact = _build_split_comparison_payload(
            split_name="forward",
            baseline_metrics=calibration.current_forward_metrics,
            candidate_metrics=(
                calibration.candidate.forward_metrics
                if calibration.candidate is not None
                else None
            ),
            promotable=(
                calibration.candidate.promotable
                if calibration.candidate is not None
                else False
            ),
            promotability_blockers=(
                calibration.candidate.promotability_blockers
                if calibration.candidate is not None
                else calibration.candidate_blockers
            ),
            args=args,
        )
        lines.append("")
        lines.append(f"### {calibration.symbol}")
        lines.append(
            f"- Candidate present: {forward_artifact['candidate_present']} | promotable: {forward_artifact['candidate_promotable']} | all_guardrails_pass: {forward_artifact['all_guardrails_pass']}"
        )
        lines.append(
            f"- Forward delta mean_forward_bps_3: {forward_artifact['delta']['mean_forward_bps_3']}"
        )
        lines.append(
            f"- Forward activation ratio vs baseline: {forward_artifact['delta']['activation_ratio_vs_baseline']}"
        )
        for check in forward_artifact["guardrails"]:
            lines.append(
                f"- {check['name']}: {check['status']} (actual={check['actual']}, requirement={check['requirement']})"
            )
    lines.append("")
    lines.append("## Candidate Overlay")
    lines.append("```yaml")
    lines.append(yaml.safe_dump(overlay, sort_keys=False,
                 allow_unicode=False).rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## Facts")
    lines.append(
        "- FACT: feature logs are present and schema-rich, but sampled lines do not expose explicit timestamp keys."
    )
    lines.append(
        "- FACT: recorder 300s bars expose price, high, low, pillar_sum, pillar_operator, pillar_strategist, spread_bps, volatility_state, pm_norm, readiness, and timestamp."
    )
    lines.append(
        "- FACT: recorder regime/regime_conf columns were not trusted for fitting; regimes are reconstructed offline through live RegimeDetector."
    )
    lines.append("")
    lines.append("## Inferences")
    lines.append(
        "- INFERENCE: if a V2 candidate clears train, validation, and forward guardrails while remaining promotable, it is a bounded GO_CANDIDATE for threshold-surface testing only."
    )
    lines.append(
        "- INFERENCE: if no candidate clears validation guardrails, the safest answer is NO_GO rather than widening scope into weight or shield changes."
    )
    lines.append("")
    lines.append("## Assumptions")
    lines.append(
        "- ASSUMPTION: forward 1-bar and 3-bar close-to-close directional proxies are acceptable restart-side sanity checks, not realized PnL estimates."
    )
    lines.append(
        "- ASSUMPTION: side-bias and memory-shield sequential replay over recorder bars is directionally representative enough for threshold validation, even though execution gating/objective gating are not replayed here."
    )
    lines.append("")
    lines.append("## Unknowns")
    lines.append(
        "- UNKNOWN: whether downstream execution gates, order routing, and market-impact effects preserve the same forward-edge ranking seen in offline bar replay."
    )
    lines.append(
        "- UNKNOWN: whether BTCUSDT control would suggest the same quantile family under the same date window if audited separately."
    )
    lines.append("")
    lines.append(
        "## Symptom / Root Cause / Contributing Factor / Masking Layer")
    if verdict == "GO_CANDIDATE":
        lines.append(
            "- Symptom: each symbol produced a promotable candidate that beat or matched validation requirements and did not materially degrade on forward evaluation."
        )
        lines.append(
            "- Root cause: train-fitted threshold surfaces aligned with observed score distribution without violating activation guardrails."
        )
    else:
        lines.append(
            "- Symptom: at least one symbol is non-promotable, candidate-missing, or fails validation/forward guardrails, so the package remains NO_GO_CANDIDATE."
        )
        lines.append(
            "- Root cause: source-path mismatch or proxy-edge/activation guardrails did not support safe candidate carry-forward."
        )
    lines.append(
        "- Contributing factor: sparse regime coverage, limited train support, or baseline source fallback to decision-level thresholds can all constrain candidate quality or promotability."
    )
    lines.append(
        "- Masking layer: offline replay does not include execution routing, objective gating, fills, or market impact, so proxy edge can overstate deployable quality."
    )
    lines.append("")
    lines.append("## Cause / Mechanism / Effect / Operational Risk")
    lines.append(
        "- Cause: threshold surfaces are fit from replayed train-split absolute score distributions under current live Aurora math."
    )
    lines.append(
        "- Mechanism: candidate surfaces are re-run through the live detector and shield stack, then accepted or rejected by activation and proxy-edge guardrails on validation and forward windows."
    )
    lines.append(
        "- Effect: the tool can emit either a bounded GO_CANDIDATE or a fail-closed NO_GO_CANDIDATE without silently widening into unrelated Aurora controls."
    )
    lines.append(
        "- Operational risk: even GO_CANDIDATE remains a bounded offline proxy and must not be treated as execution-parity proof or direct production truth."
    )
    lines.append("")
    lines.append("## Risks / Trust Boundary")
    lines.append(
        "- Risk: offline replay still excludes full execution-routing, fill-quality, and objective-stack behavior, so GO_CANDIDATE is bounded to threshold-surface candidate status, not direct production promotion."
    )
    lines.append(
        "- Risk: sparse regime coverage can produce DEFAULT-only overlays that are operationally safer than overfit regime factors but may miss true per-regime opportunities."
    )
    lines.append(
        "- Trust boundary: recorder bars are the time-axis truth for this tool; feature logs are schema evidence only; runtime truth outweighs documentation claims when conflicts appear."
    )
    lines.append(
        "- Trust boundary: the script emits additive overlay artifacts only and never rewrites canonical aurora YAML."
    )
    lines.append("")
    lines.append("## Next Action")
    if verdict == "GO_CANDIDATE":
        lines.append(
            "- Next action: treat the emitted overlay as a candidate-only threshold-surface package for downstream testnet or controlled restart validation, with promotion still gated outside this script."
        )
    else:
        lines.append(
            "- Next action: keep the emitted overlay in candidate-only status and investigate the failing guardrails before any restart or promotion decision."
        )
    return "\n".join(lines) + "\n"


def _default_out_dir(symbols: list[str]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_".join(symbols)
    return Path(f"reports/threshold_calibration/{timestamp}_{suffix}")


def _run_v1(
    args: argparse.Namespace,
    ordered_symbols: list[str],
    threshold_surfaces: dict[str, ThresholdSurface],
) -> CalibrationRunOutputs:
    log_paths = _iter_log_paths(args.log_glob)
    if not log_paths:
        raise CalibrationError(
            f"No log files matched --log-glob pattern {args.log_glob!r}")

    samples = _parse_trace_samples(
        log_paths=log_paths,
        symbols=set(ordered_symbols),
        from_date=args.from_date,
        to_date=args.to_date,
    )
    if not samples:
        raise CalibrationError(
            "No QUADRATIC_DECISION_TRACE samples found for the requested symbols/date range"
        )

    samples_by_symbol: dict[str, list[ScoreSample]] = defaultdict(list)
    for sample in samples:
        samples_by_symbol[sample.symbol].append(sample)

    calibrations: list[SymbolCalibration] = []
    for symbol in ordered_symbols:
        symbol_samples = samples_by_symbol.get(symbol, [])
        if not symbol_samples:
            raise CalibrationError(
                f"No QUADRATIC_DECISION_TRACE samples found for symbol {symbol}")
        calibrations.append(
            _fit_symbol_calibration(
                symbol=symbol,
                surface=threshold_surfaces[symbol],
                samples=symbol_samples,
                min_samples=int(args.min_samples),
                min_regime_samples=int(args.min_regime_samples),
                target_quantile=float(args.target_quantile),
            )
        )

    overlay = _build_overlay_from_v1(calibrations)
    verdict = "NO_GO_RESEARCH_ONLY"
    promotability_by_symbol = {
        calibration.symbol: {
            "promotable": False,
            "promotability_blockers": [
                "aurora-logs is research-only evidence and cannot produce a promotable writeback candidate",
                *_candidate_blockers_for_surface(calibration.surface),
            ],
        }
        for calibration in calibrations
    }
    report_text = _render_v1_report(
        calibrations=calibrations,
        args=args,
        overlay=overlay,
        data_source_description="aurora_core QUADRATIC_DECISION_TRACE log parsing",
        log_paths=log_paths,
    )

    print("Calibration summary:")
    for calibration in calibrations:
        print(
            f"  {calibration.symbol}: current={calibration.surface.signal_threshold_value:.6f} "
            f"proposed={calibration.proposed_signal_threshold_value:.6f} "
            f"activation(current={_format_ratio(calibration.current_estimated_activation_rate)}, "
            f"proposed={_format_ratio(calibration.proposed_estimated_activation_rate)})"
        )

    return CalibrationRunOutputs(
        overlay=overlay,
        report_text=report_text,
        verdict=verdict,
        baseline_metrics=_build_v1_baseline_metrics(calibrations),
        candidate_metrics=_build_v1_candidate_metrics(calibrations),
        validation_metrics=_build_research_only_split_metrics("validation"),
        forward_metrics=_build_research_only_split_metrics("forward"),
        run_manifest=_build_run_manifest(
            args=args,
            ordered_symbols=ordered_symbols,
            threshold_surfaces=threshold_surfaces,
            verdict=verdict,
            evidence_tier="research-only",
            promotable=False,
            promotability_by_symbol=promotability_by_symbol,
        ),
    )


def _run_v2(
    args: argparse.Namespace,
    ordered_symbols: list[str],
    threshold_surfaces: dict[str, ThresholdSurface],
    aurora_yaml_path: Path,
) -> CalibrationRunOutputs:
    typed_config = _load_typed_runtime_config(aurora_yaml_path)
    recorder_dir = Path(args.recorder_dir)
    feature_log_dir = Path(args.feature_log_dir)

    # Load pillar weights from domains.yaml to recalculate pillar_sum from raw pillars
    _pillar_weights: dict[str, float] | None = None
    try:
        import yaml as _yaml
        _domains_path = aurora_yaml_path.parent / "domains.yaml"
        if not _domains_path.is_file():
            _domains_path = aurora_yaml_path.parent.parent / "domains.yaml"
        if _domains_path.is_file():
            with _domains_path.open("r", encoding="utf-8") as _f:
                _domains_cfg = _yaml.safe_load(_f) or {}
            _fe_cfg = _domains_cfg.get("feature_engineering", {})
            _pw = _fe_cfg.get("pillars", {}).get("weights", {})
            if _pw and "tactician" in _pw:
                _pillar_weights = _pw
                print(f"Pillar weights from domains.yaml: {_pillar_weights}")
    except Exception as _exc:
        print(
            f"WARNING: could not load pillar weights from domains.yaml: {_exc}")

    bars_by_symbol = _load_recorder_bars(
        recorder_dir=recorder_dir,
        symbols=ordered_symbols,
        from_date=args.from_date,
        to_date=args.to_date,
        tf_sec=int(args.tf_sec),
        pillar_weights=_pillar_weights,
    )
    calibrations: list[V2SymbolCalibration] = []
    for symbol in ordered_symbols:
        bars = bars_by_symbol.get(symbol, [])
        if not bars:
            raise CalibrationError(
                f"No recorder bars found for {symbol} under {recorder_dir.as_posix()} for tf_sec={int(args.tf_sec)}"
            )
        audit = _collect_feature_log_audit(symbol, feature_log_dir)
        calibrations.append(
            _fit_v2_symbol_calibration(
                symbol=symbol,
                surface=threshold_surfaces[symbol],
                bars=bars,
                feature_log_audit=audit,
                typed_config=typed_config,
                args=args,
            )
        )

    overlay = _build_overlay_from_v2(calibrations)
    verdict = _v2_verdict(calibrations)
    promotability_by_symbol = {
        calibration.symbol: {
            "promotable": bool(
                calibration.candidate is not None and calibration.candidate.promotable
            ),
            "promotability_blockers": list(
                calibration.candidate.promotability_blockers
                if calibration.candidate is not None
                else (calibration.candidate_blockers or ["candidate_missing"])
            ),
        }
        for calibration in calibrations
    }
    report_text = _render_v2_report(
        calibrations=calibrations,
        args=args,
        overlay=overlay,
        typed_config=typed_config,
    )

    print(f"Verdict: {verdict}")
    for calibration in calibrations:
        candidate = calibration.candidate
        if calibration.candidate_blockers:
            print(
                f"  {calibration.symbol}: non-promotable under current source mode ({'; '.join(calibration.candidate_blockers)})"
            )
            continue
        if candidate is None:
            print(
                f"  {calibration.symbol}: no candidate cleared train-time guardrails")
            continue
        print(
            f"  {calibration.symbol}: q={candidate.quantile:.2f} current_validation_activation={_format_ratio(calibration.current_validation_metrics.activation_rate)} "
            f"candidate_validation_activation={_format_ratio(candidate.validation_metrics.activation_rate)} "
            f"candidate_validation_fwd3={_format_bps(candidate.validation_metrics.mean_forward_bps_3)}bps "
            f"validation_guardrails_ok={candidate.validation_guardrails_ok} "
            f"forward_guardrails_ok={candidate.forward_guardrails_ok}"
        )

    return CalibrationRunOutputs(
        overlay=overlay,
        report_text=report_text,
        verdict=verdict,
        baseline_metrics=_build_v2_baseline_metrics(calibrations),
        candidate_metrics=_build_v2_candidate_metrics(calibrations),
        validation_metrics=_build_v2_validation_metrics(calibrations, args),
        forward_metrics=_build_v2_forward_metrics(calibrations, args),
        run_manifest=_build_run_manifest(
            args=args,
            ordered_symbols=ordered_symbols,
            threshold_surfaces=threshold_surfaces,
            verdict=verdict,
            evidence_tier="production-aligned",
            promotable=all(
                payload["promotable"] for payload in promotability_by_symbol.values()
            )
            if promotability_by_symbol
            else False,
            promotability_by_symbol=promotability_by_symbol,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    aurora_yaml_path = Path(args.aurora_yaml)
    aurora = _load_aurora_profile(aurora_yaml_path)

    seen_symbols: set[str] = set()
    ordered_symbols: list[str] = []
    for raw_symbol in args.symbols:
        symbol = raw_symbol.upper()
        if symbol not in seen_symbols:
            ordered_symbols.append(symbol)
            seen_symbols.add(symbol)

    threshold_surfaces = {
        symbol: _extract_live_threshold_surface(
            aurora,
            symbol=symbol,
            threshold_source_mode=str(args.threshold_source_mode),
        )
        for symbol in ordered_symbols
    }

    if args.input_source == "aurora-logs":
        outputs = _run_v1(args, ordered_symbols, threshold_surfaces)
    elif args.input_source == "recorder-features-v2":
        outputs = _run_v2(
            args, ordered_symbols, threshold_surfaces, aurora_yaml_path)
    else:
        raise CalibrationError(
            f"Unsupported input source: {args.input_source}")

    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir(
        ordered_symbols)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_metrics_path = out_dir / "baseline_metrics.json"
    baseline_metrics_path.write_text(
        json.dumps(outputs.baseline_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Baseline metrics written to {baseline_metrics_path}")

    candidate_metrics_path = out_dir / "candidate_metrics.json"
    candidate_metrics_path.write_text(
        json.dumps(outputs.candidate_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Candidate metrics written to {candidate_metrics_path}")

    validation_metrics_path = out_dir / "validation_metrics.json"
    validation_metrics_path.write_text(
        json.dumps(outputs.validation_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Validation metrics written to {validation_metrics_path}")

    forward_metrics_path = out_dir / "forward_metrics.json"
    forward_metrics_path.write_text(
        json.dumps(outputs.forward_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Forward metrics written to {forward_metrics_path}")

    manifest = dict(outputs.run_manifest)
    manifest["artifacts"] = {
        "candidate_aurora_threshold_overlay": str((out_dir / PRIMARY_CANDIDATE_OVERLAY).as_posix()) if args.emit_overlay else None,
        "candidate_threshold_overlay_legacy": str((out_dir / LEGACY_CANDIDATE_OVERLAY).as_posix()) if args.emit_overlay else None,
        "run_manifest": str((out_dir / "run_manifest.json").as_posix()),
        "baseline_metrics": str(baseline_metrics_path.as_posix()),
        "candidate_metrics": str(candidate_metrics_path.as_posix()),
        "validation_metrics": str(validation_metrics_path.as_posix()),
        "forward_metrics": str(forward_metrics_path.as_posix()),
        "report": str((out_dir / "report.md").as_posix()),
    }

    if args.emit_overlay:
        primary_overlay_path = out_dir / PRIMARY_CANDIDATE_OVERLAY
        overlay_text = yaml.safe_dump(outputs.overlay, sort_keys=False,
                                      allow_unicode=False)
        primary_overlay_path.write_text(
            overlay_text,
            encoding="utf-8",
        )
        print(f"Overlay written to {primary_overlay_path}")

        legacy_overlay_path = out_dir / LEGACY_CANDIDATE_OVERLAY
        legacy_overlay_path.write_text(
            yaml.safe_dump(outputs.overlay, sort_keys=False,
                           allow_unicode=False),
            encoding="utf-8",
        )
        print(f"Legacy overlay written to {legacy_overlay_path}")

    if args.emit_report:
        report_path = out_dir / "report.md"
        report_path.write_text(outputs.report_text, encoding="utf-8")
        print(f"Report written to {report_path}")

    manifest_path = out_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Run manifest written to {manifest_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
