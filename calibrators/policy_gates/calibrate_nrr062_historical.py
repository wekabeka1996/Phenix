from __future__ import annotations
from vfoundation.core.protocol import Message
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
)
from apps.reference.shared.decision_primitives.entry_plan import (
    EntryPlan,
    EntryPlanParams,
    ObiMissingPolicy,
)
from apps.reference.shared.decision_primitives.aurora_confidence import (
    compute_aurora_strategy_confidence,
)
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.domains.feature_engineering.pillar_indicators import (
    aggregate_pillars,
    compute_operator,
    compute_strategist,
    compute_tactician,
)
from apps.reference.domains.decision_making.gates.low_vol_cost_floor import (
    LowVolCostFloorEvaluation,
    _coerce_decimal,
    _compute_tp_sl_bps,
    _resolve_direction_confidence,
    _resolve_gate_mode,
    evaluate_low_vol_cost_floor_gate,
)
from apps.reference.config.domains import decision_making as domain_dm
import argparse
import csv
import decimal
import json
import math
import sys
from types import SimpleNamespace
import urllib.parse
import urllib.request
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CONFIG_DIR = ROOT / "config" / "aurora"
DOMAINS_YAML = CONFIG_DIR / "domains.yaml"
AURORA_STRATEGY_YAML = CONFIG_DIR / "strategies" / "aurora.yaml"

DEFAULT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "BNBUSDT",
)
DEFAULT_START_DATE = "2025-04-01"
DEFAULT_END_DATE = "2026-05-04"
DEFAULT_TIMEFRAMES_SEC = (180, 300, 900)
PRIMARY_TF_SEC = 300
BINANCE_FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_INTERVAL = "1m"
BINANCE_LIMIT = 1500

RAW_DATA_DIR = ROOT / "data" / "raw" / "binance_um_klines"
PROCESSED_DIR = ROOT / "data" / "processed" / "nrr062_historical_calibration"
ARTIFACTS_DIR = ROOT / "artifacts" / "nrr062_historical_calibration"
REPORTS_DIR = ROOT / "reports"

REPORT_PATH = REPORTS_DIR / "NRR062_HISTORICAL_CALIBRATION_REPORT.md"
PATCH_PATH = REPORTS_DIR / "NRR062_CONFIG_PATCH_CANDIDATE.yaml"
RESULTS_PATH = ARTIFACTS_DIR / "results.json"

DEFAULT_TIMEOUT_BARS = 18

LEGACY_DIRECTION_CONTRACT = "legacy_raw_signal_score"
PATCHED_DIRECTION_CONTRACT = "patched_strategy_confidence"

GRID_TARGET_NET_FEE_MULTIPLES = (2.0, 1.75, 1.5)
GRID_MIN_TP_FEE_COVERAGE = (3.0, 2.5, 2.0, 1.5)
GRID_MIN_RR = (1.2, 1.0, 0.8, 0.6, 0.5)
GRID_LOW_VOL_MIN_REGIME_CONFIDENCE = (0.39, 0.35, 0.30)
GRID_LOW_VOL_MIN_DIRECTION_CONFIDENCE = (
    0.50,
    0.40,
    0.35,
    0.30,
    0.25,
    0.20,
    0.15,
    0.125,
    0.10,
    0.075,
    0.05,
)
NORMALIZED_DIRECTION_CONFIDENCE_SWEEP = (
    0.50,
    0.40,
    0.35,
    0.30,
    0.25,
    0.20,
    0.15,
    0.125,
    0.10,
    0.075,
    0.05,
)
RAW_MICRO_DIRECTION_CONFIDENCE_SWEEP = (
    0.051,
    0.05,
    0.04,
    0.03,
    0.02,
    0.01,
)


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    symbol: str
    tf_sec: int
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class GapRecord:
    expected_open_time_ms: int
    actual_open_time_ms: int


@dataclass(frozen=True, slots=True)
class RegimeObservation:
    symbol: str
    ts_ms: int
    regime: str
    regime_confidence: float
    regime_age_bars: int


@dataclass(frozen=True, slots=True)
class PillarConfigBundle:
    tactician_tf_sec: int
    tactician_roc_period: int
    tactician_sensitivity: float
    tactician_min_bars: int
    operator_tf_sec: int
    operator_linreg_period: int
    operator_adx_period: int
    operator_sensitivity: float
    operator_min_bars: int
    strategist_tf_sec: int
    strategist_sma_period: int
    strategist_sensitivity: float
    strategist_min_bars: int
    weights: dict[str, float]


@dataclass(frozen=True, slots=True)
class PillarSnapshot:
    ts_ms: int
    tactician: float | None
    operator: float | None
    strategist: float | None
    pillar_sum: float | None


@dataclass(frozen=True, slots=True)
class DecisionContract:
    signal_threshold: float
    neutral_threshold: float
    regime_thresholds: dict[str, float]
    score_multiplier: float
    delta_price_cap_pct: float
    admission_mode: str
    admission_power: float | None
    sizing_mode: str
    sizing_power: float | None
    admission_shield_floor: float
    tick_size: float | None
    allowed_regimes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GateObservation:
    symbol: str
    ts_ms: int
    timestamp_utc: str
    regime: str
    regime_confidence: float
    regime_age_bars: int
    side: str
    signal_score: float
    threshold_factor: float
    pillar_sum: float
    tactician: float | None
    operator: float | None
    strategist: float | None
    atr: float
    entry_price: float
    stop_price: float
    target_price: float
    entry_plan_confidence: float
    outcome: str
    exit_price: float | None
    exit_ts_ms: int | None
    fill_ts_ms: int | None
    pnl_pct: float
    r_multiple: float
    bars_held_1m: int
    signal_score_raw: float | None = None
    strategy_confidence: float | None = None
    strategy_confidence_side_scope: str | None = None
    direction_contract_mode: str = PATCHED_DIRECTION_CONTRACT


@dataclass(frozen=True, slots=True)
class SurfaceThresholds:
    target_net_fee_multiple: float
    min_tp_fee_coverage: float
    min_rr: float
    low_vol_min_regime_confidence: float
    low_vol_min_direction_confidence: float


@dataclass(frozen=True, slots=True)
class SurfaceMetrics:
    total_candidates: int
    allowed_count: int
    blocked_count: int
    allowed_tp_hits: int
    allowed_sl_hits: int
    allowed_timeout: int
    allowed_not_filled: int
    total_allowed_pnl_pct: float
    blocked_profitable: int
    blocked_outcomes: dict[str, int]
    violation_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class SurfaceEvaluation:
    label: str
    thresholds: SurfaceThresholds
    metrics: SurfaceMetrics


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    symbol: str
    start_open_time_ms: int
    end_open_time_ms: int
    bar_count_1m: int
    gaps_detected: int
    counts_by_tf: dict[str, int]


@dataclass(frozen=True, slots=True)
class PreparedGateSweepObservation:
    active: bool
    static_block: bool
    max_target_net_fee_multiple: float | None
    max_tp_fee_coverage: float | None
    max_rr: float | None
    max_regime_confidence: float | None
    max_direction_confidence: float | None
    outcome: str


class ReplayClock:
    def __init__(self) -> None:
        self._now_ms = 0
        self._anchor_ms = 0

    def set_now_ms(self, now_ms: int) -> None:
        if self._anchor_ms == 0:
            self._anchor_ms = int(now_ms)
        self._now_ms = int(now_ms)

    def now_ms(self) -> int:
        return int(self._now_ms)

    def now_sec(self) -> float:
        return float(self._now_ms) / 1000.0

    def monotonic(self) -> float:
        if self._anchor_ms == 0:
            return 0.0
        return max(0.0, (self._now_ms - self._anchor_ms) / 1000.0)


class CaptureFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list[Any]] = {}
        self.emit_count = 0
        self.last_event: tuple[str, dict[str, Any], str] | None = None

    def listen(self, event_name: str, handler: Any) -> None:
        self.listeners.setdefault(event_name, []).append(handler)

    def emit(
        self,
        event_name: str,
        payload: dict[str, Any],
        why: str = "",
        data_ref: Any = None,
    ) -> None:
        del data_ref
        self.emit_count += 1
        self.last_event = (str(event_name), dict(payload), str(why))


def safe_float(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def safe_int(value: Any) -> int | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_symbol(name: str) -> str:
    return str(name or "").strip().upper()


def iso_utc_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).isoformat()


def emit_progress(message: str) -> None:
    print(f"[nrr062] {message}", flush=True)


def parse_utc_date(value: str) -> date:
    return date.fromisoformat(str(value).strip())


def load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping in {path}")
    return raw


def to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: to_namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [to_namespace(item) for item in value]
    return value


def iter_month_windows(start_date: date, end_date_exclusive: date) -> list[tuple[date, date, date]]:
    windows: list[tuple[date, date, date]] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor < end_date_exclusive:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_start = max(cursor, start_date)
        month_end = min(next_month, end_date_exclusive)
        windows.append((cursor, month_start, month_end))
        cursor = next_month
    return windows


def date_to_ms(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=UTC).timestamp() * 1000)


def raw_month_path(raw_dir: Path, symbol: str, month_anchor: date) -> Path:
    return raw_dir / symbol / "1m" / f"{month_anchor.isoformat()[:7]}.json"


def _request_klines(
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    request_timeout_sec: int,
) -> list[list[Any]]:
    params = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": BINANCE_INTERVAL,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": BINANCE_LIMIT,
        }
    )
    url = f"{BINANCE_FAPI_KLINES_URL}?{params}"
    with urllib.request.urlopen(url, timeout=request_timeout_sec) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError(
            f"Unexpected Binance payload for {symbol}: {type(payload)}")
    rows: list[list[Any]] = []
    for row in payload:
        if not isinstance(row, list):
            raise ValueError(f"Malformed Binance kline row for {symbol}")
        rows.append(row)
    return rows


def download_month_1m_klines(
    *,
    symbol: str,
    start_ms: int,
    end_ms_exclusive: int,
    request_timeout_sec: int,
) -> list[list[Any]]:
    cursor = int(start_ms)
    rows: list[list[Any]] = []
    while cursor < end_ms_exclusive:
        batch = _request_klines(
            symbol=symbol,
            start_ms=cursor,
            end_ms=end_ms_exclusive - 1,
            request_timeout_sec=request_timeout_sec,
        )
        if not batch:
            break
        rows.extend(batch)
        last_open_time_ms = int(batch[-1][0])
        next_cursor = last_open_time_ms + 60_000
        if next_cursor <= cursor:
            raise RuntimeError(
                f"Non-advancing Binance cursor for {symbol} at {cursor}")
        cursor = next_cursor
        if len(batch) < BINANCE_LIMIT:
            break
    return rows


def normalize_raw_klines(symbol: str, raw_rows: Sequence[Sequence[Any]]) -> list[HistoricalBar]:
    bars: list[HistoricalBar] = []
    for row in raw_rows:
        if len(row) < 7:
            raise ValueError(
                f"Malformed kline row for {symbol}: expected >=7 columns")
        open_time_ms = int(row[0])
        open_price = float(row[1])
        high_price = float(row[2])
        low_price = float(row[3])
        close_price = float(row[4])
        volume = float(row[5])
        close_time_ms = int(row[6])
        bars.append(
            HistoricalBar(
                symbol=symbol,
                tf_sec=60,
                open_time_ms=open_time_ms,
                close_time_ms=close_time_ms,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
    deduped: dict[int, HistoricalBar] = {}
    for bar in bars:
        existing = deduped.get(bar.open_time_ms)
        if existing is None:
            deduped[bar.open_time_ms] = bar
            continue
        if existing != bar:
            raise ValueError(
                f"Conflicting duplicate 1m bars for {symbol} at {bar.open_time_ms}"
            )
    return [deduped[key] for key in sorted(deduped.keys())]


def write_raw_kline_cache(
    *,
    path: Path,
    symbol: str,
    window_start: date,
    window_end: date,
    raw_rows: Sequence[Sequence[Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "interval": BINANCE_INTERVAL,
                "window_start": window_start.isoformat(),
                "window_end_exclusive": window_end.isoformat(),
                "klines": list(raw_rows),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def load_or_download_1m_bars(
    *,
    symbol: str,
    start_date: date,
    end_date_exclusive: date,
    raw_dir: Path,
    request_timeout_sec: int,
) -> list[HistoricalBar]:
    collected: list[HistoricalBar] = []
    for month_anchor, window_start, window_end in iter_month_windows(start_date, end_date_exclusive):
        path = raw_month_path(raw_dir, symbol, month_anchor)
        start_ms = date_to_ms(window_start)
        end_ms = date_to_ms(window_end)
        expected_end_open_ms = end_ms - 60_000
        window_label = (
            f"{window_start.isoformat()}..{(window_end - timedelta(days=1)).isoformat()}"
        )
        if path.exists():
            emit_progress(
                f"{symbol}: loading cached 1m month {window_label} ({path.name})")
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw_rows = payload.get("klines") if isinstance(
                payload, dict) else payload
        else:
            emit_progress(f"{symbol}: downloading 1m month {window_label}")
            raw_rows = download_month_1m_klines(
                symbol=symbol,
                start_ms=start_ms,
                end_ms_exclusive=end_ms,
                request_timeout_sec=request_timeout_sec,
            )
            write_raw_kline_cache(
                path=path,
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                raw_rows=raw_rows,
            )
        month_bars = normalize_raw_klines(symbol, raw_rows)
        month_slice = [
            bar
            for bar in month_bars
            if start_ms <= bar.open_time_ms < end_ms
        ]
        month_gaps = detect_missing_1m_gaps(month_slice) if month_slice else []
        stale_cache = (
            (not month_slice)
            or month_slice[0].open_time_ms != start_ms
            or month_slice[-1].open_time_ms != expected_end_open_ms
            or bool(month_gaps)
        )
        if stale_cache:
            emit_progress(
                f"{symbol}: refreshing stale 1m cache for {window_label}")
            raw_rows = download_month_1m_klines(
                symbol=symbol,
                start_ms=start_ms,
                end_ms_exclusive=end_ms,
                request_timeout_sec=request_timeout_sec,
            )
            write_raw_kline_cache(
                path=path,
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                raw_rows=raw_rows,
            )
            month_bars = normalize_raw_klines(symbol, raw_rows)
            month_slice = [
                bar
                for bar in month_bars
                if start_ms <= bar.open_time_ms < end_ms
            ]
        collected.extend(
            month_slice
        )
    deduped: dict[int, HistoricalBar] = {}
    for bar in collected:
        deduped[bar.open_time_ms] = bar
    ordered = [deduped[key] for key in sorted(deduped.keys())]
    expected_start_ms = date_to_ms(start_date)
    if not ordered:
        raise ValueError(f"No 1m bars loaded for {symbol}")
    if ordered[0].open_time_ms != expected_start_ms:
        raise ValueError(
            f"{symbol} coverage starts at {ordered[0].open_time_ms}, expected {expected_start_ms}"
        )
    emit_progress(
        f"{symbol}: loaded {len(ordered)} x 1m bars through {iso_utc_from_ms(ordered[-1].open_time_ms)}"
    )
    return ordered


def detect_missing_1m_gaps(bars: Sequence[HistoricalBar]) -> list[GapRecord]:
    gaps: list[GapRecord] = []
    for previous, current in zip(bars, bars[1:]):
        expected = previous.open_time_ms + 60_000
        if current.open_time_ms != expected:
            gaps.append(
                GapRecord(
                    expected_open_time_ms=expected,
                    actual_open_time_ms=current.open_time_ms,
                )
            )
    return gaps


def aggregate_1m_bars(bars_1m: Sequence[HistoricalBar], timeframe_sec: int) -> list[HistoricalBar]:
    if timeframe_sec <= 60 or timeframe_sec % 60 != 0:
        raise ValueError(f"Unsupported aggregation timeframe: {timeframe_sec}")
    bucket_minutes = timeframe_sec // 60
    bucket_ms = timeframe_sec * 1000
    start_index = 0
    while start_index < len(bars_1m) and bars_1m[start_index].open_time_ms % bucket_ms != 0:
        start_index += 1
    result: list[HistoricalBar] = []
    index = start_index
    while index + bucket_minutes <= len(bars_1m):
        chunk = list(bars_1m[index:index + bucket_minutes])
        if chunk[0].open_time_ms % bucket_ms != 0:
            index += 1
            continue
        expected_open_ms = chunk[0].open_time_ms
        for bar in chunk:
            if bar.open_time_ms != expected_open_ms:
                raise ValueError(
                    f"Gap inside aggregation window for {bar.symbol} tf={timeframe_sec} at {expected_open_ms}"
                )
            expected_open_ms += 60_000
        result.append(
            HistoricalBar(
                symbol=chunk[0].symbol,
                tf_sec=timeframe_sec,
                open_time_ms=chunk[0].open_time_ms,
                close_time_ms=chunk[-1].close_time_ms,
                open=chunk[0].open,
                high=max(bar.high for bar in chunk),
                low=min(bar.low for bar in chunk),
                close=chunk[-1].close,
                volume=sum(bar.volume for bar in chunk),
            )
        )
        index += bucket_minutes
    return result


def write_bar_csv(path: Path, bars: Sequence[HistoricalBar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "tf_sec",
                "open_time_ms",
                "close_time_ms",
                "timestamp_utc",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        )
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "symbol": bar.symbol,
                    "tf_sec": bar.tf_sec,
                    "open_time_ms": bar.open_time_ms,
                    "close_time_ms": bar.close_time_ms,
                    "timestamp_utc": iso_utc_from_ms(bar.close_time_ms),
                    "open": f"{bar.open:.12f}",
                    "high": f"{bar.high:.12f}",
                    "low": f"{bar.low:.12f}",
                    "close": f"{bar.close:.12f}",
                    "volume": f"{bar.volume:.12f}",
                }
            )


def load_runtime_config() -> Any:
    regime_raw = load_yaml(CONFIG_DIR / "regime.yaml")
    system_raw = load_yaml(CONFIG_DIR / "system.yaml")
    domains_raw = load_yaml(DOMAINS_YAML)

    decision_making = (domains_raw.get("decision_making") or {})
    entry_plan_cfg = domain_dm.EntryPlanConfig.model_validate(
        decision_making.get("entry_plan") or {}
    )
    low_vol_gate_cfg = domain_dm.LowVolCostFloorGateConfig.model_validate(
        decision_making.get("low_vol_cost_floor_gate") or {}
    )

    regime_runtime = to_namespace(
        {
            **regime_raw,
            "system": system_raw.get("system") or {},
        }
    )
    regime_runtime.domains = SimpleNamespace(
        decision_making=SimpleNamespace(
            entry_plan=entry_plan_cfg,
            low_vol_cost_floor_gate=low_vol_gate_cfg,
        )
    )
    return regime_runtime


def load_pillar_contract() -> PillarConfigBundle:
    domains = load_yaml(DOMAINS_YAML)
    pillars = (
        ((domains.get("feature_engineering") or {}).get("pillars") or {})
        or ((domains.get("decision_making") or {}).get("pillars") or {})
        or (domains.get("pillars") or {})
    )
    tactician = pillars.get("tactician") or {}
    operator = pillars.get("operator") or {}
    strategist = pillars.get("strategist") or {}
    weights = pillars.get("weights") or {}
    return PillarConfigBundle(
        tactician_tf_sec=int(tactician.get("timeframe_sec")),
        tactician_roc_period=int(tactician.get("roc_period")),
        tactician_sensitivity=float(tactician.get("sensitivity")),
        tactician_min_bars=int(tactician.get("min_bars")),
        operator_tf_sec=int(operator.get("timeframe_sec")),
        operator_linreg_period=int(operator.get("linreg_period")),
        operator_adx_period=int(operator.get("adx_period")),
        operator_sensitivity=float(operator.get("sensitivity")),
        operator_min_bars=int(operator.get("min_bars")),
        strategist_tf_sec=int(strategist.get("timeframe_sec")),
        strategist_sma_period=int(strategist.get("sma_period")),
        strategist_sensitivity=float(strategist.get("sensitivity")),
        strategist_min_bars=int(strategist.get("min_bars")),
        weights={
            "tactician": float(weights.get("tactician")),
            "operator": float(weights.get("operator")),
            "strategist": float(weights.get("strategist")),
        },
    )


def load_aurora_strategy_contract() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    raw = load_yaml(AURORA_STRATEGY_YAML)
    aurora = raw.get("aurora") or {}
    decision = aurora.get("decision") or {}
    assets = aurora.get("assets") or {}
    if not isinstance(assets, dict):
        raise ValueError("aurora.assets must be a mapping")
    return decision, assets


def build_detector(config: Any) -> tuple[RegimeDetector, CaptureFSM, ReplayClock]:
    fsm = CaptureFSM()
    clock = ReplayClock()
    detector = RegimeDetector(config=config, fsm=fsm, clock=clock)
    return detector, fsm, clock


def replay_regimes(config: Any, bars_300: Sequence[HistoricalBar]) -> dict[int, RegimeObservation]:
    detector, fsm, clock = build_detector(config)
    observations: dict[int, RegimeObservation] = {}
    last_regime: str | None = None
    regime_age_bars = 0
    for bar in bars_300:
        clock.set_now_ms(bar.close_time_ms)
        baseline_emit_count = fsm.emit_count
        detector.handle_event(
            Message(
                op="EVT",
                verb="FEATURES_CALCULATED",
                src="nrr062_historical_calibration",
                dst="regime_detector",
                pld={
                    "symbol": bar.symbol,
                    "ts": bar.close_time_ms,
                    "tf_sec": PRIMARY_TF_SEC,
                    "close_boundary_ts_ms": bar.close_time_ms + 1,
                    "features": {
                        "price": bar.close,
                        "high": bar.high,
                        "low": bar.low,
                    },
                },
            )
        )
        if fsm.emit_count <= baseline_emit_count or fsm.last_event is None:
            raise RuntimeError(
                f"RegimeDetector did not emit EVT:REGIME_DETECTED for {bar.symbol} {bar.close_time_ms}"
            )
        event_name, payload, _why = fsm.last_event
        if event_name != "EVT:REGIME_DETECTED":
            raise RuntimeError(f"Unexpected emitted event {event_name!r}")
        regime = str(payload.get("regime") or "UNCERTAIN")
        confidence = safe_float(payload.get("confidence"))
        if confidence is None:
            raise RuntimeError(
                f"Missing regime confidence for {bar.symbol} {bar.close_time_ms}"
            )
        if regime == last_regime:
            regime_age_bars += 1
        else:
            regime_age_bars = 1
            last_regime = regime
        observations[bar.close_time_ms] = RegimeObservation(
            symbol=bar.symbol,
            ts_ms=bar.close_time_ms,
            regime=regime,
            regime_confidence=confidence,
            regime_age_bars=regime_age_bars,
        )
    return observations


def compute_atr_series(bars: Sequence[HistoricalBar], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("ATR window must be > 0")
    atr_values: list[float | None] = [None] * len(bars)
    true_ranges: list[float] = []
    running_sum = 0.0
    for index in range(1, len(bars)):
        previous_close = bars[index - 1].close
        current = bars[index]
        true_range = max(
            current.high - current.low,
            abs(current.high - previous_close),
            abs(current.low - previous_close),
        )
        true_ranges.append(true_range)
        running_sum += true_range
        if len(true_ranges) > window:
            running_sum -= true_ranges[-(window + 1)]
        if len(true_ranges) >= window:
            atr_values[index] = running_sum / float(window)
    return atr_values


def compute_pillar_snapshots(
    *,
    bars_300: Sequence[HistoricalBar],
    bars_900: Sequence[HistoricalBar],
    bars_4h: Sequence[HistoricalBar],
    bars_1d: Sequence[HistoricalBar],
    pillar_cfg: PillarConfigBundle,
) -> dict[int, PillarSnapshot]:
    m15_closes: list[float] = []
    h4_closes: list[float] = []
    h4_highs: list[float] = []
    h4_lows: list[float] = []
    d1_closes: list[float] = []

    m15_index = 0
    h4_index = 0
    d1_index = 0

    snapshots: dict[int, PillarSnapshot] = {}
    for bar in bars_300:
        while m15_index < len(bars_900) and bars_900[m15_index].close_time_ms <= bar.close_time_ms:
            m15_closes.append(bars_900[m15_index].close)
            m15_index += 1
        while h4_index < len(bars_4h) and bars_4h[h4_index].close_time_ms <= bar.close_time_ms:
            h4_closes.append(bars_4h[h4_index].close)
            h4_highs.append(bars_4h[h4_index].high)
            h4_lows.append(bars_4h[h4_index].low)
            h4_index += 1
        while d1_index < len(bars_1d) and bars_1d[d1_index].close_time_ms <= bar.close_time_ms:
            d1_closes.append(bars_1d[d1_index].close)
            d1_index += 1

        tactician = None
        if len(m15_closes) >= pillar_cfg.tactician_min_bars:
            tactician = compute_tactician(
                m15_closes,
                roc_period=pillar_cfg.tactician_roc_period,
                sensitivity=pillar_cfg.tactician_sensitivity,
            )

        operator = None
        if len(h4_closes) >= pillar_cfg.operator_min_bars:
            operator = compute_operator(
                h4_closes,
                h4_highs,
                h4_lows,
                linreg_period=pillar_cfg.operator_linreg_period,
                adx_period=pillar_cfg.operator_adx_period,
                sensitivity=pillar_cfg.operator_sensitivity,
            )

        strategist = None
        if len(d1_closes) >= pillar_cfg.strategist_min_bars:
            strategist = compute_strategist(
                d1_closes,
                sma_period=pillar_cfg.strategist_sma_period,
                sensitivity=pillar_cfg.strategist_sensitivity,
            )

        pillar_sum = aggregate_pillars(
            tactician,
            operator,
            strategist,
            pillar_cfg.weights,
        )
        snapshots[bar.close_time_ms] = PillarSnapshot(
            ts_ms=bar.close_time_ms,
            tactician=tactician,
            operator=operator,
            strategist=strategist,
            pillar_sum=pillar_sum,
        )
    return snapshots


def build_entry_plan(entry_plan_cfg: Any) -> EntryPlan:
    if not bool(getattr(entry_plan_cfg, "enabled", False)):
        raise ValueError("domains.decision_making.entry_plan is disabled")
    params = EntryPlanParams(
        atr_period=int(entry_plan_cfg.atr_period),
        entry_k_atr=float(entry_plan_cfg.entry_k_atr),
        sl_k_atr=float(entry_plan_cfg.sl_k_atr),
        tp_k_atr=float(entry_plan_cfg.tp_k_atr),
        obi_weight=float(entry_plan_cfg.obi_weight),
        obi_mod_clamp_min=float(entry_plan_cfg.obi_mod_clamp_min),
        obi_mod_clamp_max=float(entry_plan_cfg.obi_mod_clamp_max),
        require_atr=bool(entry_plan_cfg.require_atr),
        obi_missing_policy=ObiMissingPolicy(
            str(entry_plan_cfg.obi_missing_policy)),
        structural_stop_enabled=bool(entry_plan_cfg.structural_stop_enabled),
        base_atr_mult=float(entry_plan_cfg.base_atr_mult),
        confidence_scale=float(entry_plan_cfg.confidence_scale),
        min_stop_bps=int(entry_plan_cfg.min_stop_bps),
    )
    return EntryPlan(params)


def resolve_symbol_decision_contract(
    decision_cfg: dict[str, Any],
    asset_cfg: dict[str, Any],
) -> DecisionContract:
    signal_threshold = safe_float(decision_cfg.get("signal_threshold"))
    if signal_threshold is None:
        raise ValueError("aurora.decision.signal_threshold missing/invalid")

    asset_signal_threshold = asset_cfg.get("signal_threshold")
    if isinstance(asset_signal_threshold, dict):
        if bool(asset_signal_threshold.get("enabled")):
            override_value = safe_float(asset_signal_threshold.get("value"))
            if override_value is not None:
                signal_threshold = override_value
    else:
        direct_signal_threshold = safe_float(asset_signal_threshold)
        if direct_signal_threshold is not None:
            signal_threshold = direct_signal_threshold

    neutral_threshold = safe_float(decision_cfg.get("neutral_threshold"))
    if neutral_threshold is None:
        raise ValueError("aurora.decision.neutral_threshold missing/invalid")
    asset_neutral_threshold = asset_cfg.get("neutral_threshold")
    if isinstance(asset_neutral_threshold, dict):
        override_value = safe_float(asset_neutral_threshold.get("value"))
        if override_value is not None:
            neutral_threshold = override_value
    else:
        direct_neutral_threshold = safe_float(asset_neutral_threshold)
        if direct_neutral_threshold is not None:
            neutral_threshold = direct_neutral_threshold

    regime_thresholds = asset_cfg.get(
        "regime_thresholds") or decision_cfg.get("regime_thresholds") or {}
    normalized_regime_thresholds = {
        str(key).strip().upper(): float(value)
        for key, value in regime_thresholds.items()
        if safe_float(value) is not None
    }
    if "DEFAULT" not in normalized_regime_thresholds:
        raise ValueError(
            "regime_thresholds.DEFAULT missing for aurora symbol contract")

    signals_cfg = decision_cfg.get("signals") or {}
    geometry_cfg = decision_cfg.get("decision_geometry") or {}
    allowed_regimes = tuple(normalize_symbol(value)
                            for value in (asset_cfg.get("allowed_regimes") or []))

    return DecisionContract(
        signal_threshold=signal_threshold,
        neutral_threshold=neutral_threshold,
        regime_thresholds=normalized_regime_thresholds,
        score_multiplier=safe_float(
            decision_cfg.get("score_multiplier")) or 1.0,
        delta_price_cap_pct=safe_float(
            signals_cfg.get("delta_price_cap_pct")) or 0.02,
        admission_mode=str(geometry_cfg.get("admission_mode") or "linear"),
        admission_power=safe_float(geometry_cfg.get("admission_power")),
        sizing_mode=str(geometry_cfg.get("sizing_mode") or "quadratic"),
        sizing_power=safe_float(geometry_cfg.get("sizing_power")),
        admission_shield_floor=safe_float(
            geometry_cfg.get("admission_shield_floor")) or 0.0,
        tick_size=safe_float(asset_cfg.get("tick_size")),
        allowed_regimes=allowed_regimes,
    )


def outcome_pnl_pct(side: str, entry_price: float, exit_price: float) -> float:
    if side == "BUY":
        return ((exit_price - entry_price) / entry_price) * 100.0
    return ((entry_price - exit_price) / entry_price) * 100.0


def simulate_limit_path(
    *,
    side: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    future_bars_1m: Sequence[HistoricalBar],
) -> tuple[str, float | None, int | None, int | None, float, float, int]:
    filled = False
    fill_ts_ms: int | None = None
    bars_held = 0
    risk_fraction = abs(entry_price - stop_price) / \
        entry_price if entry_price > 0 else 0.0
    for bar in future_bars_1m:
        if not filled:
            fill_hit = bar.low <= entry_price if side == "BUY" else bar.high >= entry_price
            if not fill_hit:
                continue
            filled = True
            fill_ts_ms = bar.open_time_ms
        bars_held += 1
        if side == "BUY":
            stop_hit = bar.low <= stop_price
            tp_hit = bar.high >= target_price
        else:
            stop_hit = bar.high >= stop_price
            tp_hit = bar.low <= target_price

        if stop_hit and tp_hit:
            stop_hit = True
            tp_hit = False

        if stop_hit:
            pnl_pct = outcome_pnl_pct(side, entry_price, stop_price)
            r_multiple = (pnl_pct / 100.0) / \
                risk_fraction if risk_fraction > 0 else 0.0
            return "FILLED_SL", stop_price, bar.close_time_ms, fill_ts_ms, pnl_pct, r_multiple, bars_held

        if tp_hit:
            pnl_pct = outcome_pnl_pct(side, entry_price, target_price)
            r_multiple = (pnl_pct / 100.0) / \
                risk_fraction if risk_fraction > 0 else 0.0
            return "FILLED_TP", target_price, bar.close_time_ms, fill_ts_ms, pnl_pct, r_multiple, bars_held

    if not filled:
        return "NOT_FILLED_TIMEOUT", None, None, None, 0.0, 0.0, 0

    if not future_bars_1m:
        return "FILLED_TIMEOUT", entry_price, fill_ts_ms, fill_ts_ms, 0.0, 0.0, 0

    last_bar = future_bars_1m[-1]
    pnl_pct = outcome_pnl_pct(side, entry_price, last_bar.close)
    r_multiple = (pnl_pct / 100.0) / \
        risk_fraction if risk_fraction > 0 else 0.0
    return "FILLED_TIMEOUT", last_bar.close, last_bar.close_time_ms, fill_ts_ms, pnl_pct, r_multiple, bars_held


def build_gate_observations_for_symbol(
    *,
    symbol: str,
    bars_300: Sequence[HistoricalBar],
    bars_1m: Sequence[HistoricalBar],
    regime_by_ts: dict[int, RegimeObservation],
    pillar_by_ts: dict[int, PillarSnapshot],
    decision_cfg: dict[str, Any],
    asset_cfg: dict[str, Any],
    entry_plan: EntryPlan,
    entry_plan_cfg: Any,
    timeout_bars: int,
) -> list[GateObservation]:
    contract = resolve_symbol_decision_contract(decision_cfg, asset_cfg)
    atr_values = compute_atr_series(bars_300, int(entry_plan_cfg.atr_period))
    open_times_1m = [bar.open_time_ms for bar in bars_1m]
    observations: list[GateObservation] = []

    for index, bar in enumerate(bars_300):
        regime_obs = regime_by_ts.get(bar.close_time_ms)
        if regime_obs is None:
            continue
        if contract.allowed_regimes and regime_obs.regime not in contract.allowed_regimes:
            continue

        pillar_snapshot = pillar_by_ts.get(bar.close_time_ms)
        if pillar_snapshot is None or pillar_snapshot.pillar_sum is None:
            continue

        result = QuadraticScoringKernel.compute(
            symbol=symbol,
            features={
                "pillar_sum": pillar_snapshot.pillar_sum,
                "price": bar.close,
            },
            warmup_readiness={"pillar_sum": True},
            price=decimal.Decimal(str(bar.close)),
            signal_weights={},
            feature_neutrals={},
            essential_features=[],
            base_threshold=decimal.Decimal(str(contract.signal_threshold)),
            regime_name=regime_obs.regime,
            regime_thresholds=contract.regime_thresholds,
            side_bias_state=None,
            direction_strength_cfg={},
            delta_price_cap_pct=contract.delta_price_cap_pct,
            neutral_threshold=decimal.Decimal(str(contract.neutral_threshold)),
            current_side="",
            score_multiplier=contract.score_multiplier,
            admission_mode=contract.admission_mode,
            admission_power=contract.admission_power,
            sizing_mode=contract.sizing_mode,
            sizing_power=contract.sizing_power,
            admission_shield_floor=contract.admission_shield_floor,
        )
        if bool(getattr(result, "deferred", False)):
            continue
        side_raw = str(getattr(result, "side", "") or "").strip().lower()
        if side_raw not in {"buy", "sell"}:
            continue

        atr = atr_values[index]
        if atr is None:
            continue

        threshold_factor = safe_float(
            getattr(result, "threshold_factor", None)) or 1.0
        score_value = safe_float(getattr(result, "score", None))
        if score_value is None:
            continue
        strategy_confidence = compute_aurora_strategy_confidence(
            score=score_value,
            threshold_factor=threshold_factor,
        )
        if strategy_confidence is None:
            continue
        entry_plan_confidence = strategy_confidence

        try:
            entry_plan_result = entry_plan.compute(
                side=side_raw.upper(),
                ref_price=bar.close,
                atr=atr,
                obi=None,
                pillar_confidence=entry_plan_confidence,
                tick_size=contract.tick_size,
            )
        except Exception:
            continue

        horizon_1m = timeout_bars * (PRIMARY_TF_SEC // 60)
        future_start = bisect_right(open_times_1m, bar.close_time_ms)
        future_bars_1m = bars_1m[future_start:future_start + horizon_1m]

        outcome, exit_price, exit_ts_ms, fill_ts_ms, pnl_pct, r_multiple, bars_held = simulate_limit_path(
            side=side_raw.upper(),
            entry_price=float(entry_plan_result.entry_price),
            stop_price=float(entry_plan_result.stop_loss_price),
            target_price=float(entry_plan_result.take_profit_price),
            future_bars_1m=future_bars_1m,
        )
        observations.append(
            GateObservation(
                symbol=symbol,
                ts_ms=bar.close_time_ms,
                timestamp_utc=iso_utc_from_ms(bar.close_time_ms),
                regime=regime_obs.regime,
                regime_confidence=regime_obs.regime_confidence,
                regime_age_bars=regime_obs.regime_age_bars,
                side=side_raw.upper(),
                signal_score=score_value,
                threshold_factor=threshold_factor,
                pillar_sum=pillar_snapshot.pillar_sum,
                tactician=pillar_snapshot.tactician,
                operator=pillar_snapshot.operator,
                strategist=pillar_snapshot.strategist,
                atr=atr,
                entry_price=float(entry_plan_result.entry_price),
                stop_price=float(entry_plan_result.stop_loss_price),
                target_price=float(entry_plan_result.take_profit_price),
                entry_plan_confidence=entry_plan_confidence,
                outcome=outcome,
                exit_price=exit_price,
                exit_ts_ms=exit_ts_ms,
                fill_ts_ms=fill_ts_ms,
                pnl_pct=pnl_pct,
                r_multiple=r_multiple,
                bars_held_1m=bars_held,
                signal_score_raw=score_value,
                strategy_confidence=strategy_confidence,
                strategy_confidence_side_scope=side_raw.upper(),
                direction_contract_mode=PATCHED_DIRECTION_CONTRACT,
            )
        )
    return observations


def metrics_to_dict(metrics: SurfaceMetrics) -> dict[str, Any]:
    return {
        "total_candidates": metrics.total_candidates,
        "allowed_count": metrics.allowed_count,
        "blocked_count": metrics.blocked_count,
        "allowed_tp_hits": metrics.allowed_tp_hits,
        "allowed_sl_hits": metrics.allowed_sl_hits,
        "allowed_timeout": metrics.allowed_timeout,
        "allowed_not_filled": metrics.allowed_not_filled,
        "total_allowed_pnl_pct": metrics.total_allowed_pnl_pct,
        "blocked_profitable": metrics.blocked_profitable,
        "blocked_outcomes": dict(metrics.blocked_outcomes),
        "violation_counts": dict(metrics.violation_counts),
    }


def surface_to_dict(surface: SurfaceEvaluation) -> dict[str, Any]:
    return {
        "label": surface.label,
        "thresholds": {
            "target_net_fee_multiple": surface.thresholds.target_net_fee_multiple,
            "min_tp_fee_coverage": surface.thresholds.min_tp_fee_coverage,
            "min_rr": surface.thresholds.min_rr,
            "low_vol_min_regime_confidence": surface.thresholds.low_vol_min_regime_confidence,
            "low_vol_min_direction_confidence": surface.thresholds.low_vol_min_direction_confidence,
        },
        "metrics": metrics_to_dict(surface.metrics),
    }


def thresholds_key(thresholds: SurfaceThresholds) -> tuple[float, float, float, float, float]:
    return (
        thresholds.target_net_fee_multiple,
        thresholds.min_tp_fee_coverage,
        thresholds.min_rr,
        thresholds.low_vol_min_regime_confidence,
        thresholds.low_vol_min_direction_confidence,
    )


def surface_key(surface: SurfaceEvaluation) -> tuple[float, float, float, float, float]:
    return thresholds_key(surface.thresholds)


def month_key_from_ts_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).strftime("%Y-%m")


def format_markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "inf" if value > 0 else "-inf"
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return text if text else "0"
    return str(value)


def render_markdown_table(
    columns: Sequence[tuple[str, str]],
    rows: Sequence[dict[str, Any]],
) -> list[str]:
    if not rows:
        return ["_No rows._"]
    header = "| " + " | ".join(label for _key, label in columns) + " |"
    separator = "| " + " | ".join("---" for _key, _label in columns) + " |"
    body = [
        "| "
        + " | ".join(format_markdown_cell(row.get(key))
                     for key, _label in columns)
        + " |"
        for row in rows
    ]
    return [header, separator, *body]


def mutate_gate_cfg(
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    thresholds: SurfaceThresholds,
) -> domain_dm.LowVolCostFloorGateConfig:
    candidate = gate_cfg.model_copy(deep=True)
    candidate.thresholds.target_net_fee_multiple = thresholds.target_net_fee_multiple
    candidate.thresholds.min_tp_fee_coverage = thresholds.min_tp_fee_coverage
    candidate.thresholds.min_rr = thresholds.min_rr
    candidate.thresholds.min_regime_confidence_by_regime["LOW_VOLATILITY"] = (
        thresholds.low_vol_min_regime_confidence
    )
    candidate.thresholds.min_direction_confidence_by_regime["LOW_VOLATILITY"] = (
        thresholds.low_vol_min_direction_confidence
    )
    return candidate


def observation_signal_score_raw(observation: GateObservation) -> float:
    return observation.signal_score if observation.signal_score_raw is None else observation.signal_score_raw


def observation_strategy_confidence(observation: GateObservation) -> float:
    if observation.strategy_confidence is not None:
        return observation.strategy_confidence
    return observation.entry_plan_confidence


def observation_strategy_confidence_side_scope(observation: GateObservation) -> str:
    if observation.strategy_confidence_side_scope:
        return observation.strategy_confidence_side_scope
    return observation.side


def build_observation_strategy_trace(
    *,
    observation: GateObservation,
    contract_mode: str,
) -> dict[str, Any] | None:
    trace: dict[str, Any] = {
        "contract_mode": contract_mode,
        "final_score_raw": observation_signal_score_raw(observation),
        "signal_score": observation_signal_score_raw(observation),
        "signal_score_abs": abs(observation_signal_score_raw(observation)),
        "aurora_threshold_factor": observation.threshold_factor,
        "aurora_pillar_confidence_candidate": observation_strategy_confidence(observation),
    }
    if observation.threshold_factor > 0:
        trace["aurora_raw_score_to_threshold_ratio"] = abs(
            observation_signal_score_raw(observation)
        ) / observation.threshold_factor
    if contract_mode == PATCHED_DIRECTION_CONTRACT:
        trace["strategy_confidence"] = observation_strategy_confidence(
            observation)
        trace["strategy_confidence_candidate"] = observation_strategy_confidence(
            observation)
        trace["strategy_confidence_side_scope"] = observation_strategy_confidence_side_scope(
            observation
        )
    return trace


def evaluate_surface(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str = PATCHED_DIRECTION_CONTRACT,
) -> tuple[list[dict[str, Any]], SurfaceMetrics]:
    rows: list[dict[str, Any]] = []
    violation_counts: Counter[str] = Counter()
    blocked_outcomes: Counter[str] = Counter()

    allowed_count = 0
    blocked_count = 0
    allowed_tp_hits = 0
    allowed_sl_hits = 0
    allowed_timeout = 0
    allowed_not_filled = 0
    total_allowed_pnl_pct = 0.0
    blocked_profitable = 0

    for observation in observations:
        evaluation = evaluate_low_vol_cost_floor_gate(
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            regime=observation.regime,
            regime_confidence=observation.regime_confidence,
            side=observation.side,
            entry_price=observation.entry_price,
            target_price=observation.target_price,
            stop_price=observation.stop_price,
            strategy_trace=build_observation_strategy_trace(
                observation=observation,
                contract_mode=contract_mode,
            ),
            signal_score=observation_signal_score_raw(observation),
            reduce_only=False,
        )
        violations = [str(item) for item in (
            evaluation.details.get("violations") or [])]
        violation_counts.update(violations)
        if evaluation.block:
            blocked_count += 1
            blocked_outcomes[observation.outcome] += 1
            if observation.outcome == "FILLED_TP":
                blocked_profitable += 1
        else:
            allowed_count += 1
            total_allowed_pnl_pct += observation.pnl_pct
            if observation.outcome == "FILLED_TP":
                allowed_tp_hits += 1
            elif observation.outcome == "FILLED_SL":
                allowed_sl_hits += 1
            elif observation.outcome == "FILLED_TIMEOUT":
                allowed_timeout += 1
            elif observation.outcome == "NOT_FILLED_TIMEOUT":
                allowed_not_filled += 1

        rows.append(
            observation_to_row(
                observation=observation,
                evaluation=evaluation,
                contract_mode=contract_mode,
            )
        )

    metrics = SurfaceMetrics(
        total_candidates=len(observations),
        allowed_count=allowed_count,
        blocked_count=blocked_count,
        allowed_tp_hits=allowed_tp_hits,
        allowed_sl_hits=allowed_sl_hits,
        allowed_timeout=allowed_timeout,
        allowed_not_filled=allowed_not_filled,
        total_allowed_pnl_pct=total_allowed_pnl_pct,
        blocked_profitable=blocked_profitable,
        blocked_outcomes=dict(blocked_outcomes),
        violation_counts=dict(violation_counts),
    )
    return rows, metrics


def observation_to_row(
    *,
    observation: GateObservation,
    evaluation: LowVolCostFloorEvaluation,
    contract_mode: str,
) -> dict[str, Any]:
    details = evaluation.details
    return {
        "symbol": observation.symbol,
        "ts_ms": observation.ts_ms,
        "timestamp_utc": observation.timestamp_utc,
        "regime": observation.regime,
        "regime_confidence": observation.regime_confidence,
        "regime_age_bars": observation.regime_age_bars,
        "contract_mode": contract_mode,
        "side": observation.side,
        "signal_score": observation.signal_score,
        "signal_score_raw": observation_signal_score_raw(observation),
        "threshold_factor": observation.threshold_factor,
        "entry_plan_confidence": observation.entry_plan_confidence,
        "strategy_confidence": observation_strategy_confidence(observation),
        "strategy_confidence_side_scope": observation_strategy_confidence_side_scope(observation),
        "pillar_sum": observation.pillar_sum,
        "tactician": observation.tactician,
        "operator": observation.operator,
        "strategist": observation.strategist,
        "atr": observation.atr,
        "entry_price": observation.entry_price,
        "stop_price": observation.stop_price,
        "target_price": observation.target_price,
        "gate_mode": evaluation.gate_mode,
        "gate_active": evaluation.active,
        "gate_block": evaluation.block,
        "gate_reason": evaluation.reason,
        "gate_threshold_failed": evaluation.threshold_failed,
        "gate_violations": "|".join(str(item) for item in (details.get("violations") or [])),
        "required_gross_tp_bps": details.get("required_gross_tp_bps"),
        "actual_tp_bps": details.get("actual_tp_bps"),
        "actual_sl_bps": details.get("actual_sl_bps"),
        "tp_fee_coverage_ratio": details.get("tp_fee_coverage_ratio"),
        "rr_ratio": details.get("rr_ratio"),
        "resolved_min_regime_confidence": details.get("resolved_min_regime_confidence"),
        "resolved_min_direction_confidence": details.get("resolved_min_direction_confidence"),
        "direction_confidence_source": details.get("direction_confidence_source"),
        "selected_direction_confidence_source": details.get("direction_confidence_source"),
        "direction_confidence": details.get("direction_confidence"),
        "outcome": observation.outcome,
        "fill_ts_ms": observation.fill_ts_ms,
        "exit_ts_ms": observation.exit_ts_ms,
        "exit_price": observation.exit_price,
        "pnl_pct": observation.pnl_pct,
        "r_multiple": observation.r_multiple,
        "bars_held_1m": observation.bars_held_1m,
    }


def write_candidate_rows_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "ts_ms",
        "timestamp_utc",
        "regime",
        "regime_confidence",
        "regime_age_bars",
        "contract_mode",
        "side",
        "signal_score",
        "signal_score_raw",
        "threshold_factor",
        "entry_plan_confidence",
        "strategy_confidence",
        "strategy_confidence_side_scope",
        "pillar_sum",
        "tactician",
        "operator",
        "strategist",
        "atr",
        "entry_price",
        "stop_price",
        "target_price",
        "gate_mode",
        "gate_active",
        "gate_block",
        "gate_reason",
        "gate_threshold_failed",
        "gate_violations",
        "required_gross_tp_bps",
        "actual_tp_bps",
        "actual_sl_bps",
        "tp_fee_coverage_ratio",
        "rr_ratio",
        "resolved_min_regime_confidence",
        "resolved_min_direction_confidence",
        "direction_confidence_source",
        "selected_direction_confidence_source",
        "direction_confidence",
        "outcome",
        "fill_ts_ms",
        "exit_ts_ms",
        "exit_price",
        "pnl_pct",
        "r_multiple",
        "bars_held_1m",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_rows_csv(
    path: Path,
    rows: Sequence[dict[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def build_surface_grid(base: SurfaceThresholds) -> list[SurfaceThresholds]:
    grid: list[SurfaceThresholds] = []
    seen: set[tuple[float, float, float, float, float]] = set()

    def add_surface(surface: SurfaceThresholds) -> None:
        key = (
            surface.target_net_fee_multiple,
            surface.min_tp_fee_coverage,
            surface.min_rr,
            surface.low_vol_min_regime_confidence,
            surface.low_vol_min_direction_confidence,
        )
        if key in seen:
            return
        seen.add(key)
        grid.append(surface)

    add_surface(base)
    target_net_fee_values = sorted(
        {
            base.target_net_fee_multiple,
            *GRID_TARGET_NET_FEE_MULTIPLES,
        },
        reverse=True,
    )
    min_tp_fee_values = sorted(
        {
            base.min_tp_fee_coverage,
            *GRID_MIN_TP_FEE_COVERAGE,
        },
        reverse=True,
    )
    min_rr_values = sorted({base.min_rr, *GRID_MIN_RR}, reverse=True)
    regime_conf_values = sorted(
        {
            base.low_vol_min_regime_confidence,
            *GRID_LOW_VOL_MIN_REGIME_CONFIDENCE,
        },
        reverse=True,
    )
    direction_conf_values = sorted(
        {
            base.low_vol_min_direction_confidence,
            *GRID_LOW_VOL_MIN_DIRECTION_CONFIDENCE,
        },
        reverse=True,
    )
    for target_net_fee_multiple in target_net_fee_values:
        for min_tp_fee_coverage in min_tp_fee_values:
            for min_rr in min_rr_values:
                for low_vol_min_regime_confidence in regime_conf_values:
                    for low_vol_min_direction_confidence in direction_conf_values:
                        add_surface(
                            SurfaceThresholds(
                                target_net_fee_multiple=target_net_fee_multiple,
                                min_tp_fee_coverage=min_tp_fee_coverage,
                                min_rr=min_rr,
                                low_vol_min_regime_confidence=low_vol_min_regime_confidence,
                                low_vol_min_direction_confidence=low_vol_min_direction_confidence,
                            )
                        )
    return grid


def prepare_gate_sweep_observation(
    *,
    observation: GateObservation,
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str = PATCHED_DIRECTION_CONTRACT,
) -> PreparedGateSweepObservation:
    gate_mode = _resolve_gate_mode(
        enabled=bool(gate_cfg.enabled),
        trading_mode=str(trading_mode),
        enforce_in_modes=list(gate_cfg.enforce_in_modes),
        observe_only_in_modes=list(gate_cfg.observe_only_in_modes),
    )
    active = (
        observation.regime is not None
        and observation.regime in set(gate_cfg.regimes)
        and gate_mode != "disabled"
    )
    if not active:
        return PreparedGateSweepObservation(
            active=False,
            static_block=False,
            max_target_net_fee_multiple=None,
            max_tp_fee_coverage=None,
            max_rr=None,
            max_regime_confidence=None,
            max_direction_confidence=None,
            outcome=observation.outcome,
        )

    entry_decimal = _coerce_decimal(observation.entry_price)
    target_decimal = _coerce_decimal(observation.target_price)
    stop_decimal = _coerce_decimal(observation.stop_price)
    geometry_missing = (
        entry_decimal is None or target_decimal is None or stop_decimal is None
    )
    if geometry_missing:
        static_block = bool(gate_cfg.geometry.require_tpsl) and str(
            gate_cfg.geometry.missing_policy
        ) == "fail_closed"
        return PreparedGateSweepObservation(
            active=True,
            static_block=static_block,
            max_target_net_fee_multiple=None,
            max_tp_fee_coverage=None,
            max_rr=None,
            max_regime_confidence=None,
            max_direction_confidence=None,
            outcome=observation.outcome,
        )

    actual_tp_bps, actual_sl_bps = _compute_tp_sl_bps(
        side=observation.side,
        entry_price=entry_decimal,
        target_price=target_decimal,
        stop_price=stop_decimal,
    )
    if (
        actual_tp_bps is None
        or actual_sl_bps is None
        or actual_tp_bps <= 0
        or actual_sl_bps <= 0
    ):
        static_block = str(gate_cfg.geometry.missing_policy) == "fail_closed"
        return PreparedGateSweepObservation(
            active=True,
            static_block=static_block,
            max_target_net_fee_multiple=None,
            max_tp_fee_coverage=None,
            max_rr=None,
            max_regime_confidence=None,
            max_direction_confidence=None,
            outcome=observation.outcome,
        )

    direction_resolution = _resolve_direction_confidence(
        strategy_trace=build_observation_strategy_trace(
            observation=observation,
            contract_mode=contract_mode,
        ),
        allowed_sources=list(gate_cfg.direction_confidence.allowed_sources),
        side=observation.side,
        signal_score=observation_signal_score_raw(observation),
    )
    if direction_resolution.failure_reason is not None:
        static_block = bool(gate_cfg.direction_confidence.required) and str(
            gate_cfg.direction_confidence.missing_policy
        ) == "fail_closed"
        return PreparedGateSweepObservation(
            active=True,
            static_block=static_block,
            max_target_net_fee_multiple=None,
            max_tp_fee_coverage=None,
            max_rr=None,
            max_regime_confidence=None,
            max_direction_confidence=None,
            outcome=observation.outcome,
        )

    direction_confidence = direction_resolution.value
    if observation.regime_confidence is None or direction_confidence is None:
        return PreparedGateSweepObservation(
            active=True,
            static_block=True,
            max_target_net_fee_multiple=None,
            max_tp_fee_coverage=None,
            max_rr=None,
            max_regime_confidence=None,
            max_direction_confidence=None,
            outcome=observation.outcome,
        )

    round_trip_fee_bps = decimal.Decimal(str(gate_cfg.fee.open_fee_bps)) + decimal.Decimal(
        str(gate_cfg.fee.close_fee_bps)
    )
    slippage_buffer_bps = decimal.Decimal(str(gate_cfg.slippage.buffer_bps))
    tp_fee_coverage_ratio = (
        actual_tp_bps / round_trip_fee_bps if round_trip_fee_bps > 0 else None
    )
    rr_ratio = actual_tp_bps / actual_sl_bps if actual_sl_bps > 0 else None
    max_target_net_fee_multiple = math.inf
    if round_trip_fee_bps > 0:
        max_target_net_fee_multiple = float(
            ((actual_tp_bps - slippage_buffer_bps) / round_trip_fee_bps)
            - decimal.Decimal("1")
        )

    return PreparedGateSweepObservation(
        active=True,
        static_block=False,
        max_target_net_fee_multiple=max_target_net_fee_multiple,
        max_tp_fee_coverage=(
            float(tp_fee_coverage_ratio) if tp_fee_coverage_ratio is not None else None
        ),
        max_rr=float(rr_ratio) if rr_ratio is not None else None,
        max_regime_confidence=float(observation.regime_confidence),
        max_direction_confidence=float(direction_confidence),
        outcome=observation.outcome,
    )


def _flat_grid_size(shape: tuple[int, int, int, int, int]) -> int:
    return shape[0] * shape[1] * shape[2] * shape[3] * shape[4]


def _flat_grid_offset(
    shape: tuple[int, int, int, int, int],
    i0: int,
    i1: int,
    i2: int,
    i3: int,
    i4: int,
) -> int:
    return ((((i0 * shape[1]) + i1) * shape[2] + i2) * shape[3] + i3) * shape[4] + i4


def _add_hyperrectangle(
    diff: list[int],
    shape: tuple[int, int, int, int, int],
    upper_bounds: tuple[int, int, int, int, int],
    delta: int,
) -> None:
    ends = tuple(bound + 1 for bound in upper_bounds)
    for mask in range(32):
        i0 = ends[0] if mask & 1 else 0
        i1 = ends[1] if mask & 2 else 0
        i2 = ends[2] if mask & 4 else 0
        i3 = ends[3] if mask & 8 else 0
        i4 = ends[4] if mask & 16 else 0
        sign = -1 if (mask.bit_count() % 2) else 1
        diff[_flat_grid_offset(shape, i0, i1, i2, i3, i4)] += delta * sign


def _accumulate_hypergrid(
    diff: list[int],
    shape: tuple[int, int, int, int, int],
) -> list[int]:
    values = list(diff)

    for i0 in range(1, shape[0]):
        for i1 in range(shape[1]):
            for i2 in range(shape[2]):
                for i3 in range(shape[3]):
                    for i4 in range(shape[4]):
                        index = _flat_grid_offset(shape, i0, i1, i2, i3, i4)
                        values[index] += values[_flat_grid_offset(
                            shape, i0 - 1, i1, i2, i3, i4)]

    for i0 in range(shape[0]):
        for i1 in range(1, shape[1]):
            for i2 in range(shape[2]):
                for i3 in range(shape[3]):
                    for i4 in range(shape[4]):
                        index = _flat_grid_offset(shape, i0, i1, i2, i3, i4)
                        values[index] += values[_flat_grid_offset(
                            shape, i0, i1 - 1, i2, i3, i4)]

    for i0 in range(shape[0]):
        for i1 in range(shape[1]):
            for i2 in range(1, shape[2]):
                for i3 in range(shape[3]):
                    for i4 in range(shape[4]):
                        index = _flat_grid_offset(shape, i0, i1, i2, i3, i4)
                        values[index] += values[_flat_grid_offset(
                            shape, i0, i1, i2 - 1, i3, i4)]

    for i0 in range(shape[0]):
        for i1 in range(shape[1]):
            for i2 in range(shape[2]):
                for i3 in range(1, shape[3]):
                    for i4 in range(shape[4]):
                        index = _flat_grid_offset(shape, i0, i1, i2, i3, i4)
                        values[index] += values[_flat_grid_offset(
                            shape, i0, i1, i2, i3 - 1, i4)]

    for i0 in range(shape[0]):
        for i1 in range(shape[1]):
            for i2 in range(shape[2]):
                for i3 in range(shape[3]):
                    for i4 in range(1, shape[4]):
                        index = _flat_grid_offset(shape, i0, i1, i2, i3, i4)
                        values[index] += values[_flat_grid_offset(
                            shape, i0, i1, i2, i3, i4 - 1)]

    return values


def _build_fast_surface_metrics(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    surfaces: Sequence[SurfaceThresholds],
    contract_mode: str = PATCHED_DIRECTION_CONTRACT,
    emit_logs: bool = True,
) -> dict[tuple[float, float, float, float, float], SurfaceMetrics]:
    target_net_fee_values = sorted(
        {surface.target_net_fee_multiple for surface in surfaces}
    )
    min_tp_fee_values = sorted(
        {surface.min_tp_fee_coverage for surface in surfaces}
    )
    min_rr_values = sorted({surface.min_rr for surface in surfaces})
    regime_conf_values = sorted(
        {surface.low_vol_min_regime_confidence for surface in surfaces}
    )
    direction_conf_values = sorted(
        {surface.low_vol_min_direction_confidence for surface in surfaces}
    )

    shape = (
        len(target_net_fee_values) + 1,
        len(min_tp_fee_values) + 1,
        len(min_rr_values) + 1,
        len(regime_conf_values) + 1,
        len(direction_conf_values) + 1,
    )
    allowed_total_diff = [0] * _flat_grid_size(shape)
    allowed_pnl_diff: list[float] = [0.0] * _flat_grid_size(shape)
    allowed_by_outcome_diff: dict[str, list[int]] = {
        "FILLED_TP": [0] * _flat_grid_size(shape),
        "FILLED_SL": [0] * _flat_grid_size(shape),
        "FILLED_TIMEOUT": [0] * _flat_grid_size(shape),
        "NOT_FILLED_TIMEOUT": [0] * _flat_grid_size(shape),
    }

    constant_allowed_total = 0
    constant_allowed_pnl = 0.0
    constant_allowed_by_outcome: Counter[str] = Counter()
    total_outcomes: Counter[str] = Counter(
        observation.outcome for observation in observations
    )

    prepared_observations = [
        (
            observation,
            prepare_gate_sweep_observation(
                observation=observation,
                gate_cfg=gate_cfg,
                trading_mode=trading_mode,
                contract_mode=contract_mode,
            ),
        )
        for observation in observations
    ]
    active_count = sum(1 for _observation,
                       item in prepared_observations if item.active)
    static_block_count = sum(
        1 for _observation, item in prepared_observations if item.active and item.static_block
    )
    if emit_logs:
        emit_progress(
            f"candidate sweep prepared: active={active_count} static_block={static_block_count} inactive={len(prepared_observations) - active_count}"
        )

    for observation, prepared in prepared_observations:
        if not prepared.active:
            constant_allowed_total += 1
            constant_allowed_pnl += observation.pnl_pct
            constant_allowed_by_outcome[prepared.outcome] += 1
            continue
        if prepared.static_block:
            continue

        upper_bounds = (
            bisect_right(
                target_net_fee_values,
                prepared.max_target_net_fee_multiple,
            ) - 1,
            bisect_right(min_tp_fee_values, prepared.max_tp_fee_coverage) - 1,
            bisect_right(min_rr_values, prepared.max_rr) - 1,
            bisect_right(regime_conf_values,
                         prepared.max_regime_confidence) - 1,
            bisect_right(direction_conf_values,
                         prepared.max_direction_confidence) - 1,
        )
        if any(bound < 0 for bound in upper_bounds):
            continue

        _add_hyperrectangle(allowed_total_diff, shape, upper_bounds, 1)
        _add_hyperrectangle(allowed_pnl_diff, shape,
                            upper_bounds, observation.pnl_pct)
        outcome_diff = allowed_by_outcome_diff.get(prepared.outcome)
        if outcome_diff is not None:
            _add_hyperrectangle(outcome_diff, shape, upper_bounds, 1)

    allowed_total = _accumulate_hypergrid(allowed_total_diff, shape)
    allowed_pnl = _accumulate_hypergrid(allowed_pnl_diff, shape)
    allowed_by_outcome = {
        outcome: _accumulate_hypergrid(diff, shape)
        for outcome, diff in allowed_by_outcome_diff.items()
    }

    target_net_fee_index = {
        value: index for index, value in enumerate(target_net_fee_values)
    }
    min_tp_fee_index = {
        value: index for index, value in enumerate(min_tp_fee_values)
    }
    min_rr_index = {value: index for index, value in enumerate(min_rr_values)}
    regime_conf_index = {
        value: index for index, value in enumerate(regime_conf_values)
    }
    direction_conf_index = {
        value: index for index, value in enumerate(direction_conf_values)
    }

    metrics_by_surface: dict[
        tuple[float, float, float, float, float], SurfaceMetrics
    ] = {}
    total_candidates = len(observations)
    for surface in surfaces:
        index = _flat_grid_offset(
            shape,
            target_net_fee_index[surface.target_net_fee_multiple],
            min_tp_fee_index[surface.min_tp_fee_coverage],
            min_rr_index[surface.min_rr],
            regime_conf_index[surface.low_vol_min_regime_confidence],
            direction_conf_index[surface.low_vol_min_direction_confidence],
        )
        allowed_count = constant_allowed_total + allowed_total[index]
        total_allowed_pnl_pct = constant_allowed_pnl + allowed_pnl[index]
        allowed_tp_hits = constant_allowed_by_outcome["FILLED_TP"] + allowed_by_outcome[
            "FILLED_TP"
        ][index]
        allowed_sl_hits = constant_allowed_by_outcome["FILLED_SL"] + allowed_by_outcome[
            "FILLED_SL"
        ][index]
        allowed_timeout = constant_allowed_by_outcome["FILLED_TIMEOUT"] + allowed_by_outcome[
            "FILLED_TIMEOUT"
        ][index]
        allowed_not_filled = constant_allowed_by_outcome[
            "NOT_FILLED_TIMEOUT"
        ] + allowed_by_outcome["NOT_FILLED_TIMEOUT"][index]
        blocked_outcomes = {
            outcome: total_outcomes.get(outcome, 0) - allowed_value
            for outcome, allowed_value in {
                "FILLED_TP": allowed_tp_hits,
                "FILLED_SL": allowed_sl_hits,
                "FILLED_TIMEOUT": allowed_timeout,
                "NOT_FILLED_TIMEOUT": allowed_not_filled,
            }.items()
            if total_outcomes.get(outcome, 0) - allowed_value > 0
        }
        metrics_by_surface[
            (
                surface.target_net_fee_multiple,
                surface.min_tp_fee_coverage,
                surface.min_rr,
                surface.low_vol_min_regime_confidence,
                surface.low_vol_min_direction_confidence,
            )
        ] = SurfaceMetrics(
            total_candidates=total_candidates,
            allowed_count=allowed_count,
            blocked_count=total_candidates - allowed_count,
            allowed_tp_hits=allowed_tp_hits,
            allowed_sl_hits=allowed_sl_hits,
            allowed_timeout=allowed_timeout,
            allowed_not_filled=allowed_not_filled,
            total_allowed_pnl_pct=total_allowed_pnl_pct,
            blocked_profitable=total_outcomes.get(
                "FILLED_TP", 0) - allowed_tp_hits,
            blocked_outcomes=blocked_outcomes,
            violation_counts={},
        )
    return metrics_by_surface


def surface_distance(base: SurfaceThresholds, candidate: SurfaceThresholds) -> float:
    distance = 0.0
    if base.target_net_fee_multiple > 0:
        distance += max(0.0, (base.target_net_fee_multiple -
                        candidate.target_net_fee_multiple) / base.target_net_fee_multiple)
    if base.min_tp_fee_coverage > 0:
        distance += max(0.0, (base.min_tp_fee_coverage -
                        candidate.min_tp_fee_coverage) / base.min_tp_fee_coverage)
    if base.min_rr > 0:
        distance += max(0.0, (base.min_rr - candidate.min_rr) / base.min_rr)
    if base.low_vol_min_regime_confidence > 0:
        distance += max(0.0, (base.low_vol_min_regime_confidence -
                        candidate.low_vol_min_regime_confidence) / base.low_vol_min_regime_confidence)
    if base.low_vol_min_direction_confidence > 0:
        distance += max(0.0, (base.low_vol_min_direction_confidence -
                        candidate.low_vol_min_direction_confidence) / base.low_vol_min_direction_confidence)
    return distance


def strictly_dominates(baseline: SurfaceEvaluation, candidate: SurfaceEvaluation) -> bool:
    base = baseline.metrics
    cand = candidate.metrics
    return (
        cand.allowed_tp_hits > base.allowed_tp_hits
        and cand.allowed_sl_hits <= base.allowed_sl_hits
        and cand.allowed_timeout <= base.allowed_timeout
        and cand.allowed_not_filled <= base.allowed_not_filled
        and cand.blocked_profitable < base.blocked_profitable
    )


def select_patch_candidate(
    baseline: SurfaceEvaluation,
    candidates: Sequence[SurfaceEvaluation],
) -> tuple[SurfaceEvaluation, str]:
    baseline_sl_rate = (
        baseline.metrics.allowed_sl_hits / baseline.metrics.allowed_count
        if baseline.metrics.allowed_count > 0
        else 0.0
    )
    max_allowed_sl_rate = baseline_sl_rate * 1.10
    eligible = [
        candidate
        for candidate in candidates
        if candidate.metrics.allowed_count > baseline.metrics.allowed_count
        and (
            candidate.metrics.allowed_sl_hits / candidate.metrics.allowed_count
            if candidate.metrics.allowed_count > 0
            else math.inf
        ) <= max_allowed_sl_rate
    ]
    if not eligible:
        return baseline, "keep_current:no_candidate_meets_pnl_and_sl_rate_constraints"
    eligible.sort(
        key=lambda candidate: (
            -candidate.metrics.total_allowed_pnl_pct,
            -candidate.thresholds.low_vol_min_direction_confidence,
            surface_distance(baseline.thresholds, candidate.thresholds),
            -candidate.metrics.allowed_count,
        )
    )
    selected = eligible[0]
    return selected, "candidate_selected:max_allowed_pnl_with_sl_rate_guard"


def base_surface_thresholds(gate_cfg: domain_dm.LowVolCostFloorGateConfig) -> SurfaceThresholds:
    return SurfaceThresholds(
        target_net_fee_multiple=float(
            gate_cfg.thresholds.target_net_fee_multiple),
        min_tp_fee_coverage=float(gate_cfg.thresholds.min_tp_fee_coverage),
        min_rr=float(gate_cfg.thresholds.min_rr),
        low_vol_min_regime_confidence=float(
            gate_cfg.thresholds.min_regime_confidence_by_regime["LOW_VOLATILITY"]
        ),
        low_vol_min_direction_confidence=float(
            gate_cfg.thresholds.min_direction_confidence_by_regime["LOW_VOLATILITY"]
        ),
    )


def evaluate_candidate_surfaces(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str = PATCHED_DIRECTION_CONTRACT,
    emit_logs: bool = True,
) -> list[SurfaceEvaluation]:
    base = base_surface_thresholds(gate_cfg)
    surfaces = build_surface_grid(base)
    evaluations: list[SurfaceEvaluation] = []
    if emit_logs:
        emit_progress(
            f"evaluating {len(surfaces)} candidate gate surfaces over {len(observations)} observations"
        )
    fast_metrics = _build_fast_surface_metrics(
        observations=observations,
        gate_cfg=gate_cfg,
        trading_mode=trading_mode,
        surfaces=surfaces,
        contract_mode=contract_mode,
        emit_logs=emit_logs,
    )
    for index, thresholds in enumerate(surfaces, start=1):
        metrics = fast_metrics[
            (
                thresholds.target_net_fee_multiple,
                thresholds.min_tp_fee_coverage,
                thresholds.min_rr,
                thresholds.low_vol_min_regime_confidence,
                thresholds.low_vol_min_direction_confidence,
            )
        ]
        label = (
            "baseline"
            if thresholds == base
            else (
                f"tnf{thresholds.target_net_fee_multiple:.2f}_"
                f"tpcov{thresholds.min_tp_fee_coverage:.2f}_"
                f"rr{thresholds.min_rr:.2f}_"
                f"reg{thresholds.low_vol_min_regime_confidence:.2f}_"
                f"dir{thresholds.low_vol_min_direction_confidence:.2f}"
            )
        )
        evaluations.append(
            SurfaceEvaluation(
                label=label,
                thresholds=thresholds,
                metrics=metrics,
            )
        )
        if emit_logs and (index == 1 or index == len(surfaces) or index % 50 == 0):
            emit_progress(f"candidate gate surfaces: {index}/{len(surfaces)}")
    return evaluations


def find_surface_by_thresholds(
    surfaces: Sequence[SurfaceEvaluation],
    thresholds: SurfaceThresholds,
) -> SurfaceEvaluation:
    target_key = thresholds_key(thresholds)
    for surface in surfaces:
        if surface_key(surface) == target_key:
            return surface
    raise KeyError(f"Surface thresholds not found: {target_key}")


def build_near_dominant_pareto_table(
    baseline: SurfaceEvaluation,
    candidates: Sequence[SurfaceEvaluation],
    *,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int, int]:
    baseline_metrics = baseline.metrics
    candidate_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        delta_tp = candidate.metrics.allowed_tp_hits - baseline_metrics.allowed_tp_hits
        if delta_tp <= 0:
            continue
        candidate_rows.append(
            {
                "label": candidate.label,
                "target_net_fee_multiple": candidate.thresholds.target_net_fee_multiple,
                "min_tp_fee_coverage": candidate.thresholds.min_tp_fee_coverage,
                "min_rr": candidate.thresholds.min_rr,
                "low_vol_min_regime_confidence": candidate.thresholds.low_vol_min_regime_confidence,
                "low_vol_min_direction_confidence": candidate.thresholds.low_vol_min_direction_confidence,
                "delta_allowed_tp_hits": delta_tp,
                "delta_allowed_sl_hits": candidate.metrics.allowed_sl_hits - baseline_metrics.allowed_sl_hits,
                "delta_allowed_timeout": candidate.metrics.allowed_timeout - baseline_metrics.allowed_timeout,
                "delta_allowed_not_filled": candidate.metrics.allowed_not_filled - baseline_metrics.allowed_not_filled,
                "delta_blocked_profitable": candidate.metrics.blocked_profitable - baseline_metrics.blocked_profitable,
                "delta_blocked_count": candidate.metrics.blocked_count - baseline_metrics.blocked_count,
                "surface_distance": surface_distance(baseline.thresholds, candidate.thresholds),
            }
        )

    def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return (
            left["delta_allowed_tp_hits"] >= right["delta_allowed_tp_hits"]
            and left["delta_allowed_sl_hits"] <= right["delta_allowed_sl_hits"]
            and left["delta_allowed_timeout"] <= right["delta_allowed_timeout"]
            and left["delta_allowed_not_filled"] <= right["delta_allowed_not_filled"]
            and left["delta_blocked_profitable"] <= right["delta_blocked_profitable"]
            and (
                left["delta_allowed_tp_hits"] > right["delta_allowed_tp_hits"]
                or left["delta_allowed_sl_hits"] < right["delta_allowed_sl_hits"]
                or left["delta_allowed_timeout"] < right["delta_allowed_timeout"]
                or left["delta_allowed_not_filled"] < right["delta_allowed_not_filled"]
                or left["delta_blocked_profitable"] < right["delta_blocked_profitable"]
            )
        )

    frontier = [
        row
        for row in candidate_rows
        if not any(other is not row and dominates(other, row) for other in candidate_rows)
    ]
    frontier.sort(
        key=lambda row: (
            row["delta_blocked_profitable"],
            row["delta_allowed_sl_hits"],
            row["delta_allowed_timeout"],
            row["delta_allowed_not_filled"],
            -row["delta_allowed_tp_hits"],
            row["surface_distance"],
        )
    )
    return frontier[:limit], len(frontier), len(candidate_rows)


def build_symbol_month_blocked_breakdown(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not bool(row.get("gate_block")):
            continue
        symbol = str(row.get("symbol") or "")
        ts_ms = safe_int(row.get("ts_ms"))
        if ts_ms is None:
            continue
        month = month_key_from_ts_ms(ts_ms)
        key = (symbol, month)
        bucket = buckets.setdefault(
            key,
            {
                "symbol": symbol,
                "month": month,
                "blocked_total": 0,
                "blocked_profitable": 0,
                "saved_sl": 0,
                "blocked_timeout": 0,
                "blocked_not_filled": 0,
            },
        )
        bucket["blocked_total"] += 1
        outcome = str(row.get("outcome") or "")
        if outcome == "FILLED_TP":
            bucket["blocked_profitable"] += 1
        elif outcome == "FILLED_SL":
            bucket["saved_sl"] += 1
        elif outcome == "FILLED_TIMEOUT":
            bucket["blocked_timeout"] += 1
        elif outcome == "NOT_FILLED_TIMEOUT":
            bucket["blocked_not_filled"] += 1

    result = sorted(
        (
            {
                **bucket,
                "net_saved_sl_minus_blocked_profitable": bucket["saved_sl"] - bucket["blocked_profitable"],
            }
            for bucket in buckets.values()
        ),
        key=lambda item: (item["symbol"], item["month"]),
    )
    return result


def build_direction_blocker_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    blocked_count = 0
    sole_direction_count = 0
    joint_violations: Counter[str] = Counter()
    min_direction_confidence: float | None = None
    max_direction_confidence: float | None = None
    bins: Counter[str] = Counter()

    for row in rows:
        if not bool(row.get("gate_block")):
            continue
        blocked_count += 1
        violations = [item for item in str(
            row.get("gate_violations") or "").split("|") if item]
        if violations == ["direction_confidence_below_threshold"]:
            sole_direction_count += 1
        elif violations:
            joint_violations["|".join(sorted(violations))] += 1

        direction_confidence = safe_float(row.get("direction_confidence"))
        if direction_confidence is None:
            continue
        min_direction_confidence = (
            direction_confidence
            if min_direction_confidence is None
            else min(min_direction_confidence, direction_confidence)
        )
        max_direction_confidence = (
            direction_confidence
            if max_direction_confidence is None
            else max(max_direction_confidence, direction_confidence)
        )
        if direction_confidence < 0.40:
            bins["lt_0.40"] += 1
        elif direction_confidence < 0.45:
            bins["0.40_0.45"] += 1
        elif direction_confidence < 0.48:
            bins["0.45_0.48"] += 1
        elif direction_confidence < 0.51:
            bins["0.48_0.51"] += 1
        else:
            bins["ge_0.51"] += 1

    return {
        "blocked_count": blocked_count,
        "sole_direction_count": sole_direction_count,
        "joint_direction_count": blocked_count - sole_direction_count,
        "min_direction_confidence": min_direction_confidence,
        "max_direction_confidence": max_direction_confidence,
        "bins": dict(bins),
        "top_joint_violations": [
            {"violations": key, "count": value}
            for key, value in joint_violations.most_common(5)
        ],
    }


def build_unlock_cliff_table(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str = PATCHED_DIRECTION_CONTRACT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = base_surface_thresholds(gate_cfg)
    candidate_surfaces = [
        surface
        for surface in build_surface_grid(base)
        if thresholds_key(surface) != thresholds_key(base)
    ]
    candidate_surfaces.sort(
        key=lambda surface: (
            surface_distance(base, surface),
            surface.low_vol_min_direction_confidence,
            surface.min_rr,
            surface.min_tp_fee_coverage,
            surface.target_net_fee_multiple,
            surface.low_vol_min_regime_confidence,
        )
    )

    prepared_rows = [
        (observation, prepare_gate_sweep_observation(
            observation=observation,
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            contract_mode=contract_mode,
        ))
        for observation in observations
    ]

    blocked_rows = [
        (observation, prepared)
        for observation, prepared in prepared_rows
        if prepared.active
        and not prepared.static_block
        and not (
            prepared.max_target_net_fee_multiple is not None
            and prepared.max_tp_fee_coverage is not None
            and prepared.max_rr is not None
            and prepared.max_regime_confidence is not None
            and prepared.max_direction_confidence is not None
            and base.target_net_fee_multiple <= prepared.max_target_net_fee_multiple
            and base.min_tp_fee_coverage <= prepared.max_tp_fee_coverage
            and base.min_rr <= prepared.max_rr
            and base.low_vol_min_regime_confidence <= prepared.max_regime_confidence
            and base.low_vol_min_direction_confidence <= prepared.max_direction_confidence
        )
    ]

    rows_by_surface: dict[tuple[float, float,
                                float, float, float], dict[str, Any]] = {}
    unlockable_in_grid = 0
    locked_outside_grid = 0
    cumulative_total = 0
    cumulative_tp = 0
    cumulative_sl = 0
    cumulative_timeout = 0
    cumulative_not_filled = 0

    def surface_allows(prepared: PreparedGateSweepObservation, surface: SurfaceThresholds) -> bool:
        return (
            prepared.max_target_net_fee_multiple is not None
            and prepared.max_tp_fee_coverage is not None
            and prepared.max_rr is not None
            and prepared.max_regime_confidence is not None
            and prepared.max_direction_confidence is not None
            and surface.target_net_fee_multiple <= prepared.max_target_net_fee_multiple
            and surface.min_tp_fee_coverage <= prepared.max_tp_fee_coverage
            and surface.min_rr <= prepared.max_rr
            and surface.low_vol_min_regime_confidence <= prepared.max_regime_confidence
            and surface.low_vol_min_direction_confidence <= prepared.max_direction_confidence
        )

    for observation, prepared in blocked_rows:
        unlocking_surface = next(
            (surface for surface in candidate_surfaces if surface_allows(
                prepared, surface)),
            None,
        )
        if unlocking_surface is None:
            locked_outside_grid += 1
            continue
        unlockable_in_grid += 1
        key = thresholds_key(unlocking_surface)
        bucket = rows_by_surface.setdefault(
            key,
            {
                "label": (
                    f"tnf{unlocking_surface.target_net_fee_multiple:.2f}_"
                    f"tpcov{unlocking_surface.min_tp_fee_coverage:.2f}_"
                    f"rr{unlocking_surface.min_rr:.2f}_"
                    f"reg{unlocking_surface.low_vol_min_regime_confidence:.2f}_"
                    f"dir{unlocking_surface.low_vol_min_direction_confidence:.2f}"
                ),
                "surface_distance": surface_distance(base, unlocking_surface),
                "target_net_fee_multiple": unlocking_surface.target_net_fee_multiple,
                "min_tp_fee_coverage": unlocking_surface.min_tp_fee_coverage,
                "min_rr": unlocking_surface.min_rr,
                "low_vol_min_regime_confidence": unlocking_surface.low_vol_min_regime_confidence,
                "low_vol_min_direction_confidence": unlocking_surface.low_vol_min_direction_confidence,
                "newly_unblocked_total": 0,
                "newly_unblocked_tp": 0,
                "newly_unblocked_sl": 0,
                "newly_unblocked_timeout": 0,
                "newly_unblocked_not_filled": 0,
            },
        )
        bucket["newly_unblocked_total"] += 1
        if observation.outcome == "FILLED_TP":
            bucket["newly_unblocked_tp"] += 1
        elif observation.outcome == "FILLED_SL":
            bucket["newly_unblocked_sl"] += 1
        elif observation.outcome == "FILLED_TIMEOUT":
            bucket["newly_unblocked_timeout"] += 1
        elif observation.outcome == "NOT_FILLED_TIMEOUT":
            bucket["newly_unblocked_not_filled"] += 1

    ordered_rows = sorted(
        rows_by_surface.values(),
        key=lambda row: (
            row["surface_distance"],
            -row["newly_unblocked_total"],
            row["low_vol_min_direction_confidence"],
            row["min_rr"],
            row["min_tp_fee_coverage"],
            row["target_net_fee_multiple"],
            row["low_vol_min_regime_confidence"],
        ),
    )
    for row in ordered_rows:
        cumulative_total += row["newly_unblocked_total"]
        cumulative_tp += row["newly_unblocked_tp"]
        cumulative_sl += row["newly_unblocked_sl"]
        cumulative_timeout += row["newly_unblocked_timeout"]
        cumulative_not_filled += row["newly_unblocked_not_filled"]
        row["cumulative_unblocked_total"] = cumulative_total
        row["cumulative_unblocked_tp"] = cumulative_tp
        row["cumulative_unblocked_sl"] = cumulative_sl
        row["cumulative_unblocked_timeout"] = cumulative_timeout
        row["cumulative_unblocked_not_filled"] = cumulative_not_filled

    summary = {
        "blocked_considered": len(blocked_rows),
        "unlockable_in_relaxed_grid": unlockable_in_grid,
        "locked_outside_relaxed_grid": locked_outside_grid,
        "unlock_surface_count": len(ordered_rows),
        "first_unlock_surface": ordered_rows[0] if ordered_rows else None,
    }
    return ordered_rows, summary


def build_raw_unlock_cliff_table(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str = LEGACY_DIRECTION_CONTRACT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = base_surface_thresholds(gate_cfg)
    candidate_surfaces = [
        surface
        for surface in build_surface_grid(base)
        if thresholds_key(surface) != thresholds_key(base)
    ]
    candidate_surfaces.sort(
        key=lambda surface: (
            surface_distance(base, surface),
            surface.low_vol_min_direction_confidence,
            surface.min_rr,
            surface.min_tp_fee_coverage,
            surface.target_net_fee_multiple,
            surface.low_vol_min_regime_confidence,
        )
    )

    def rounded_requirement(value: float, digits: int) -> float:
        return round(float(value), digits)

    def first_grid_surface_for_requirement(requirement: SurfaceThresholds) -> SurfaceThresholds | None:
        return next(
            (
                surface
                for surface in candidate_surfaces
                if surface.target_net_fee_multiple <= requirement.target_net_fee_multiple
                and surface.min_tp_fee_coverage <= requirement.min_tp_fee_coverage
                and surface.min_rr <= requirement.min_rr
                and surface.low_vol_min_regime_confidence <= requirement.low_vol_min_regime_confidence
                and surface.low_vol_min_direction_confidence <= requirement.low_vol_min_direction_confidence
            ),
            None,
        )

    rows_by_requirement: dict[tuple[float, float,
                                    float, float, float], dict[str, Any]] = {}
    blocked_considered = 0
    within_grid_count = 0

    for observation in observations:
        prepared = prepare_gate_sweep_observation(
            observation=observation,
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            contract_mode=contract_mode,
        )
        if not prepared.active or prepared.static_block:
            continue
        if (
            prepared.max_target_net_fee_multiple is not None
            and prepared.max_tp_fee_coverage is not None
            and prepared.max_rr is not None
            and prepared.max_regime_confidence is not None
            and prepared.max_direction_confidence is not None
            and base.target_net_fee_multiple <= prepared.max_target_net_fee_multiple
            and base.min_tp_fee_coverage <= prepared.max_tp_fee_coverage
            and base.min_rr <= prepared.max_rr
            and base.low_vol_min_regime_confidence <= prepared.max_regime_confidence
            and base.low_vol_min_direction_confidence <= prepared.max_direction_confidence
        ):
            continue

        blocked_considered += 1
        requirement = SurfaceThresholds(
            target_net_fee_multiple=min(base.target_net_fee_multiple, float(
                prepared.max_target_net_fee_multiple or base.target_net_fee_multiple)),
            min_tp_fee_coverage=min(base.min_tp_fee_coverage, float(
                prepared.max_tp_fee_coverage or base.min_tp_fee_coverage)),
            min_rr=min(base.min_rr, float(prepared.max_rr or base.min_rr)),
            low_vol_min_regime_confidence=min(base.low_vol_min_regime_confidence, float(
                prepared.max_regime_confidence or base.low_vol_min_regime_confidence)),
            low_vol_min_direction_confidence=min(base.low_vol_min_direction_confidence, float(
                prepared.max_direction_confidence or base.low_vol_min_direction_confidence)),
        )
        rounded_key = (
            rounded_requirement(requirement.target_net_fee_multiple, 2),
            rounded_requirement(requirement.min_tp_fee_coverage, 2),
            rounded_requirement(requirement.min_rr, 2),
            rounded_requirement(requirement.low_vol_min_regime_confidence, 2),
            rounded_requirement(
                requirement.low_vol_min_direction_confidence, 6),
        )
        grid_surface = first_grid_surface_for_requirement(requirement)
        bucket = rows_by_requirement.setdefault(
            rounded_key,
            {
                "label": (
                    f"raw_tnf{rounded_key[0]:.2f}_"
                    f"tpcov{rounded_key[1]:.2f}_"
                    f"rr{rounded_key[2]:.2f}_"
                    f"reg{rounded_key[3]:.2f}_"
                    f"dir{rounded_key[4]:.6f}"
                ),
                "surface_distance": surface_distance(
                    base,
                    SurfaceThresholds(
                        target_net_fee_multiple=rounded_key[0],
                        min_tp_fee_coverage=rounded_key[1],
                        min_rr=rounded_key[2],
                        low_vol_min_regime_confidence=rounded_key[3],
                        low_vol_min_direction_confidence=rounded_key[4],
                    ),
                ),
                "target_net_fee_multiple": rounded_key[0],
                "min_tp_fee_coverage": rounded_key[1],
                "min_rr": rounded_key[2],
                "low_vol_min_regime_confidence": rounded_key[3],
                "low_vol_min_direction_confidence": rounded_key[4],
                "within_relaxed_grid": grid_surface is not None,
                "first_relaxed_grid_label": (
                    None
                    if grid_surface is None
                    else (
                        f"tnf{grid_surface.target_net_fee_multiple:.2f}_"
                        f"tpcov{grid_surface.min_tp_fee_coverage:.2f}_"
                        f"rr{grid_surface.min_rr:.2f}_"
                        f"reg{grid_surface.low_vol_min_regime_confidence:.2f}_"
                        f"dir{grid_surface.low_vol_min_direction_confidence:.2f}"
                    )
                ),
                "newly_unblocked_total": 0,
                "newly_unblocked_tp": 0,
                "newly_unblocked_sl": 0,
                "newly_unblocked_timeout": 0,
                "newly_unblocked_not_filled": 0,
            },
        )
        if grid_surface is not None:
            within_grid_count += 1
        bucket["newly_unblocked_total"] += 1
        if observation.outcome == "FILLED_TP":
            bucket["newly_unblocked_tp"] += 1
        elif observation.outcome == "FILLED_SL":
            bucket["newly_unblocked_sl"] += 1
        elif observation.outcome == "FILLED_TIMEOUT":
            bucket["newly_unblocked_timeout"] += 1
        elif observation.outcome == "NOT_FILLED_TIMEOUT":
            bucket["newly_unblocked_not_filled"] += 1

    ordered_rows = sorted(
        rows_by_requirement.values(),
        key=lambda row: (
            row["surface_distance"],
            -row["newly_unblocked_total"],
            row["low_vol_min_direction_confidence"],
            row["min_rr"],
            row["min_tp_fee_coverage"],
            row["target_net_fee_multiple"],
            row["low_vol_min_regime_confidence"],
        ),
    )
    cumulative_total = 0
    cumulative_tp = 0
    cumulative_sl = 0
    cumulative_timeout = 0
    cumulative_not_filled = 0
    for row in ordered_rows:
        cumulative_total += row["newly_unblocked_total"]
        cumulative_tp += row["newly_unblocked_tp"]
        cumulative_sl += row["newly_unblocked_sl"]
        cumulative_timeout += row["newly_unblocked_timeout"]
        cumulative_not_filled += row["newly_unblocked_not_filled"]
        row["cumulative_unblocked_total"] = cumulative_total
        row["cumulative_unblocked_tp"] = cumulative_tp
        row["cumulative_unblocked_sl"] = cumulative_sl
        row["cumulative_unblocked_timeout"] = cumulative_timeout
        row["cumulative_unblocked_not_filled"] = cumulative_not_filled

    summary = {
        "blocked_considered": blocked_considered,
        "raw_unlock_pattern_count": len(ordered_rows),
        "rows_with_raw_unlock_inside_relaxed_grid": within_grid_count,
        "rows_requiring_thresholds_outside_relaxed_grid": blocked_considered - within_grid_count,
        "first_raw_unlock": ordered_rows[0] if ordered_rows else None,
    }
    return ordered_rows, summary


def _build_direction_confidence_sweep_rows(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str,
    sweep_values: Sequence[float],
) -> list[dict[str, Any]]:
    base = base_surface_thresholds(gate_cfg)
    values = sorted(
        {
            base.low_vol_min_direction_confidence,
            *sweep_values,
        },
        reverse=True,
    )
    surfaces = [
        SurfaceThresholds(
            target_net_fee_multiple=base.target_net_fee_multiple,
            min_tp_fee_coverage=base.min_tp_fee_coverage,
            min_rr=base.min_rr,
            low_vol_min_regime_confidence=base.low_vol_min_regime_confidence,
            low_vol_min_direction_confidence=value,
        )
        for value in values
    ]
    metrics_by_surface = _build_fast_surface_metrics(
        observations=observations,
        gate_cfg=gate_cfg,
        trading_mode=trading_mode,
        surfaces=surfaces,
        contract_mode=contract_mode,
        emit_logs=False,
    )
    baseline_metrics = metrics_by_surface[thresholds_key(
        surfaces[values.index(base.low_vol_min_direction_confidence)])]
    result: list[dict[str, Any]] = []
    for surface in surfaces:
        metrics = metrics_by_surface[thresholds_key(surface)]
        result.append(
            {
                "contract_mode": contract_mode,
                "low_vol_min_direction_confidence": surface.low_vol_min_direction_confidence,
                "allowed_count": metrics.allowed_count,
                "blocked_count": metrics.blocked_count,
                "allowed_tp_hits": metrics.allowed_tp_hits,
                "allowed_sl_hits": metrics.allowed_sl_hits,
                "allowed_timeout": metrics.allowed_timeout,
                "allowed_not_filled": metrics.allowed_not_filled,
                "total_allowed_pnl_pct": metrics.total_allowed_pnl_pct,
                "blocked_profitable": metrics.blocked_profitable,
                "delta_allowed_tp_hits": metrics.allowed_tp_hits - baseline_metrics.allowed_tp_hits,
                "delta_allowed_sl_hits": metrics.allowed_sl_hits - baseline_metrics.allowed_sl_hits,
                "delta_allowed_timeout": metrics.allowed_timeout - baseline_metrics.allowed_timeout,
                "delta_allowed_not_filled": metrics.allowed_not_filled - baseline_metrics.allowed_not_filled,
                "delta_total_allowed_pnl_pct": metrics.total_allowed_pnl_pct - baseline_metrics.total_allowed_pnl_pct,
                "delta_blocked_profitable": metrics.blocked_profitable - baseline_metrics.blocked_profitable,
                "delta_blocked_count": metrics.blocked_count - baseline_metrics.blocked_count,
            }
        )
    return result


def build_direction_confidence_sweep(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
) -> list[dict[str, Any]]:
    return [
        *_build_direction_confidence_sweep_rows(
            observations=observations,
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            contract_mode=LEGACY_DIRECTION_CONTRACT,
            sweep_values=RAW_MICRO_DIRECTION_CONFIDENCE_SWEEP,
        ),
        *_build_direction_confidence_sweep_rows(
            observations=observations,
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            contract_mode=PATCHED_DIRECTION_CONTRACT,
            sweep_values=NORMALIZED_DIRECTION_CONFIDENCE_SWEEP,
        ),
    ]


def build_walk_forward_analysis(
    *,
    observations: Sequence[GateObservation],
    gate_cfg: domain_dm.LowVolCostFloorGateConfig,
    trading_mode: str,
    contract_mode: str = PATCHED_DIRECTION_CONTRACT,
    max_splits: int = 3,
) -> list[dict[str, Any]]:
    months = sorted({month_key_from_ts_ms(item.ts_ms)
                    for item in observations})
    if len(months) < 2:
        return []
    test_months = months[-min(max_splits, len(months) - 1):]
    results: list[dict[str, Any]] = []
    for test_month in test_months:
        train_observations = [
            item for item in observations if month_key_from_ts_ms(item.ts_ms) < test_month
        ]
        test_observations = [
            item for item in observations if month_key_from_ts_ms(item.ts_ms) == test_month
        ]
        if not train_observations or not test_observations:
            continue

        train_surfaces = evaluate_candidate_surfaces(
            observations=train_observations,
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            contract_mode=contract_mode,
            emit_logs=False,
        )
        train_baseline = next(
            surface for surface in train_surfaces if surface.label == "baseline"
        )
        train_selected, train_selection_reason = select_patch_candidate(
            train_baseline,
            [surface for surface in train_surfaces if surface.label != "baseline"],
        )

        test_surfaces = evaluate_candidate_surfaces(
            observations=test_observations,
            gate_cfg=gate_cfg,
            trading_mode=trading_mode,
            contract_mode=contract_mode,
            emit_logs=False,
        )
        test_baseline = next(
            surface for surface in test_surfaces if surface.label == "baseline"
        )
        test_selected = find_surface_by_thresholds(
            test_surfaces, train_selected.thresholds)

        results.append(
            {
                "test_month": test_month,
                "train_observations": len(train_observations),
                "test_observations": len(test_observations),
                "train_selection_reason": train_selection_reason,
                "selected_label": train_selected.label,
                "selected_target_net_fee_multiple": train_selected.thresholds.target_net_fee_multiple,
                "selected_min_tp_fee_coverage": train_selected.thresholds.min_tp_fee_coverage,
                "selected_min_rr": train_selected.thresholds.min_rr,
                "selected_low_vol_min_regime_confidence": train_selected.thresholds.low_vol_min_regime_confidence,
                "selected_low_vol_min_direction_confidence": train_selected.thresholds.low_vol_min_direction_confidence,
                "test_delta_allowed_tp_hits": test_selected.metrics.allowed_tp_hits - test_baseline.metrics.allowed_tp_hits,
                "test_delta_allowed_sl_hits": test_selected.metrics.allowed_sl_hits - test_baseline.metrics.allowed_sl_hits,
                "test_delta_allowed_timeout": test_selected.metrics.allowed_timeout - test_baseline.metrics.allowed_timeout,
                "test_delta_allowed_not_filled": test_selected.metrics.allowed_not_filled - test_baseline.metrics.allowed_not_filled,
                "test_delta_blocked_profitable": test_selected.metrics.blocked_profitable - test_baseline.metrics.blocked_profitable,
            }
        )
    return results


def coverage_to_dict(coverage: CoverageSummary) -> dict[str, Any]:
    return {
        "symbol": coverage.symbol,
        "start_open_time_ms": coverage.start_open_time_ms,
        "end_open_time_ms": coverage.end_open_time_ms,
        "start_utc": iso_utc_from_ms(coverage.start_open_time_ms),
        "end_utc": iso_utc_from_ms(coverage.end_open_time_ms),
        "bar_count_1m": coverage.bar_count_1m,
        "gaps_detected": coverage.gaps_detected,
        "counts_by_tf": dict(coverage.counts_by_tf),
    }


def _percentile(values: Sequence[float], ratio: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = max(0.0, min(1.0, ratio)) * (len(values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] + ((values[upper] - values[lower]) * weight))


def build_strategy_confidence_distribution(
    observations: Sequence[GateObservation],
) -> dict[str, Any]:
    values = sorted(observation_strategy_confidence(item)
                    for item in observations)
    return {
        "count": len(values),
        "min": values[0] if values else None,
        "p50": _percentile(values, 0.50),
        "p90": _percentile(values, 0.90),
        "max": values[-1] if values else None,
    }


def render_report(
    *,
    args: argparse.Namespace,
    coverage: Sequence[CoverageSummary],
    legacy_baseline: SurfaceEvaluation,
    baseline: SurfaceEvaluation,
    selected: SurfaceEvaluation,
    selection_reason: str,
    observations: Sequence[GateObservation],
    near_dominance_rows: Sequence[dict[str, Any]],
    near_dominance_frontier_count: int,
    near_dominance_tp_gain_count: int,
    blocked_breakdown_rows: Sequence[dict[str, Any]],
    direction_blocker_summary: dict[str, Any],
    unlock_cliff_rows: Sequence[dict[str, Any]],
    unlock_cliff_summary: dict[str, Any],
    raw_unlock_cliff_rows: Sequence[dict[str, Any]],
    raw_unlock_cliff_summary: dict[str, Any],
    direction_sweep_rows: Sequence[dict[str, Any]],
    walk_forward_rows: Sequence[dict[str, Any]],
    strategy_confidence_distribution: dict[str, Any],
    raw_micro_threshold_rows: Sequence[dict[str, Any]],
) -> str:
    legacy_baseline_metrics = legacy_baseline.metrics
    baseline_metrics = baseline.metrics
    selected_metrics = selected.metrics
    raw_051_row = next(
        (
            row
            for row in raw_micro_threshold_rows
            if abs(float(row.get("low_vol_min_direction_confidence") or 0.0) - 0.051) < 1e-9
        ),
        None,
    )
    raw_051_summary = (
        "not available"
        if raw_051_row is None
        else (
            "allowed="
            f"{raw_051_row.get('allowed_count')}, "
            "blocked="
            f"{raw_051_row.get('blocked_count')}, "
            "total_allowed_pnl_pct="
            f"{format_markdown_cell(raw_051_row.get('total_allowed_pnl_pct'))}"
        )
    )
    best_raw_micro_row = (
        None
        if not raw_micro_threshold_rows
        else max(
            raw_micro_threshold_rows,
            key=lambda row: (
                row.get("allowed_count", 0),
                row.get("total_allowed_pnl_pct", float("-inf")),
            ),
        )
    )
    generated_at = datetime.now(tz=UTC).isoformat()
    requested_end_open_ms = date_to_ms(parse_utc_date(
        args.end_date) + timedelta(days=1)) - 60_000
    actual_end_open_ms = min(
        item.end_open_time_ms for item in coverage) if coverage else requested_end_open_ms
    requested_end_utc = iso_utc_from_ms(requested_end_open_ms)
    actual_end_utc = iso_utc_from_ms(actual_end_open_ms)
    shortfall_minutes = max(
        0, (requested_end_open_ms - actual_end_open_ms) // 60_000)

    report_lines = [
        "# AGENT_REPORT_V1",
        "",
        "## Executive Summary",
        (
            f"NRR-062 historical calibration replay completed for {len(args.symbols)} symbols over "
            f"{args.start_date}..{args.end_date}; selection verdict = {selection_reason}."
        ),
        "",
        "## Proven Facts",
        f"- Generated at: {generated_at}",
        f"- Symbols: {', '.join(args.symbols)}",
        f"- Window: {args.start_date}..{args.end_date} inclusive UTC",
        f"- Requested end-of-window open timestamp: {requested_end_utc}; actual common available end-of-window open timestamp: {actual_end_utc}.",
        f"- Stored immutable raw 1m klines under data/raw/binance_um_klines and normalized aggregates under data/processed/nrr062_historical_calibration.",
        f"- Aggregated 1m candles into tf_sec values: {', '.join(str(value) for value in DEFAULT_TIMEFRAMES_SEC)}.",
        f"- Decision timestamp basis is {PRIMARY_TF_SEC}s bars; pillar inputs use 900s, 14400s, and 86400s SSOT pillar contracts from config/aurora/domains.yaml.",
        f"- Built {len(observations)} Aurora candidate intents with real EntryPlan geometry and real evaluate_low_vol_cost_floor_gate calls.",
        f"- Legacy raw baseline metrics: allowed={legacy_baseline_metrics.allowed_count}, blocked={legacy_baseline_metrics.blocked_count}, allowed_tp={legacy_baseline_metrics.allowed_tp_hits}, allowed_sl={legacy_baseline_metrics.allowed_sl_hits}, total_allowed_pnl_pct={format_markdown_cell(legacy_baseline_metrics.total_allowed_pnl_pct)}.",
        f"- Patched normalized baseline metrics: allowed={baseline_metrics.allowed_count}, blocked={baseline_metrics.blocked_count}, allowed_tp={baseline_metrics.allowed_tp_hits}, allowed_sl={baseline_metrics.allowed_sl_hits}, total_allowed_pnl_pct={format_markdown_cell(baseline_metrics.total_allowed_pnl_pct)}.",
        f"- Selected patched metrics: allowed={selected_metrics.allowed_count}, blocked={selected_metrics.blocked_count}, allowed_tp={selected_metrics.allowed_tp_hits}, allowed_sl={selected_metrics.allowed_sl_hits}, total_allowed_pnl_pct={format_markdown_cell(selected_metrics.total_allowed_pnl_pct)}.",
    ]
    if shortfall_minutes > 0:
        report_lines.append(
            f"- Final requested day is incomplete on source data; replay was aligned to the common available end, shortfall={shortfall_minutes} minutes."
        )
    for item in coverage:
        report_lines.append(
            f"- Coverage {item.symbol}: end={iso_utc_from_ms(item.end_open_time_ms)}, 1m={item.bar_count_1m}, 180s={item.counts_by_tf.get('180', 0)}, 300s={item.counts_by_tf.get('300', 0)}, 900s={item.counts_by_tf.get('900', 0)}, gaps={item.gaps_detected}."
        )

    report_lines.extend(
        [
            "",
            "## Inferred Findings",
            "- Patched candidate selection now optimizes total allowed PnL subject to two hard guards: allowed_count must exceed the patched baseline, and allowed SL rate cannot worsen by more than 10% versus the patched baseline.",
            f"- Dominant baseline violations: {', '.join(f'{key}={value}' for key, value in sorted(
                baseline_metrics.violation_counts.items())) if baseline_metrics.violation_counts else 'none'}.",
            f"- Legacy raw blocker range remains {format_markdown_cell(direction_blocker_summary.get('min_direction_confidence'))}..{format_markdown_cell(direction_blocker_summary.get('max_direction_confidence'))}; this is the evidence base for the raw micro-threshold diagnostic, not the patched selector.",
            (
                f"- Baseline blocked FILLED_SL={baseline_metrics.blocked_outcomes.get('FILLED_SL', 0)} exceeds blocked FILLED_TP={baseline_metrics.blocked_outcomes.get('FILLED_TP', 0)} "
                f"by {baseline_metrics.blocked_outcomes.get('FILLED_SL', 0) - baseline_metrics.blocked_outcomes.get('FILLED_TP', 0)}, supporting a guardrail interpretation rather than a clearly over-tight gate."
            ),
            (
                f"- Selected surface thresholds: target_net_fee_multiple={selected.thresholds.target_net_fee_multiple}, "
                f"min_tp_fee_coverage={selected.thresholds.min_tp_fee_coverage}, min_rr={selected.thresholds.min_rr}, "
                f"LOW_VOLATILITY.min_regime_confidence={selected.thresholds.low_vol_min_regime_confidence}, "
                f"LOW_VOLATILITY.min_direction_confidence={selected.thresholds.low_vol_min_direction_confidence}."
            ),
            "",
            "## Supplemental Analysis",
            f"- Near-dominance table below is the Pareto frontier over candidates with positive TP gain versus baseline; frontier_count={near_dominance_frontier_count}, tp_gain_candidates={near_dominance_tp_gain_count}, displayed_top={len(near_dominance_rows)}.",
            "- Blocked outcome breakdown groups baseline blocked rows by decision timestamp month and symbol; saved_sl means blocked FILLED_SL and blocked_profitable means blocked FILLED_TP.",
            (
                f"- Direction blocker summary: sole_direction_blocks={direction_blocker_summary.get('sole_direction_count', 0)}, "
                f"joint_direction_blocks={direction_blocker_summary.get('joint_direction_count', 0)}, "
                f"direction_confidence_range=[{format_markdown_cell(direction_blocker_summary.get('min_direction_confidence'))}, {format_markdown_cell(direction_blocker_summary.get('max_direction_confidence'))}], "
                f"bins={direction_blocker_summary.get('bins', {})}."
            ),
            (
                f"- Unlock cliff summary: blocked_considered={unlock_cliff_summary.get('blocked_considered', 0)}, "
                f"unlockable_in_relaxed_grid={unlock_cliff_summary.get('unlockable_in_relaxed_grid', 0)}, "
                f"locked_outside_relaxed_grid={unlock_cliff_summary.get('locked_outside_relaxed_grid', 0)}, "
                f"unlock_surface_count={unlock_cliff_summary.get('unlock_surface_count', 0)}."
            ),
            (
                f"- Raw unlock cliff summary: raw_unlock_pattern_count={raw_unlock_cliff_summary.get('raw_unlock_pattern_count', 0)}, "
                f"rows_with_raw_unlock_inside_relaxed_grid={raw_unlock_cliff_summary.get('rows_with_raw_unlock_inside_relaxed_grid', 0)}, "
                f"rows_requiring_thresholds_outside_relaxed_grid={raw_unlock_cliff_summary.get('rows_requiring_thresholds_outside_relaxed_grid', 0)}."
            ),
            "- Direction-confidence sweep now contains both contract modes in one CSV: legacy raw micro-threshold diagnostics and patched normalized threshold candidates.",
            "- Walk-forward uses expanding-train monthly splits over the last available observation months; each holdout month reuses the train-selected surface and compares it against baseline on the unseen month.",
            "",
            "## Legacy Raw Vs Patched Normalized Contract",
            f"- Legacy raw baseline: allowed={legacy_baseline_metrics.allowed_count}, blocked={legacy_baseline_metrics.blocked_count}, total_allowed_pnl_pct={format_markdown_cell(legacy_baseline_metrics.total_allowed_pnl_pct)}.",
            f"- Patched normalized baseline: allowed={baseline_metrics.allowed_count}, blocked={baseline_metrics.blocked_count}, total_allowed_pnl_pct={format_markdown_cell(baseline_metrics.total_allowed_pnl_pct)}.",
            f"- Patched minus legacy delta: allowed_count={baseline_metrics.allowed_count - legacy_baseline_metrics.allowed_count}, blocked_count={baseline_metrics.blocked_count - legacy_baseline_metrics.blocked_count}, total_allowed_pnl_pct={format_markdown_cell(baseline_metrics.total_allowed_pnl_pct - legacy_baseline_metrics.total_allowed_pnl_pct)}.",
            "",
            "## Why 0.051 Is Not The Fix",
            (
                "- Raw micro-threshold diagnostic rows are reported separately from the patched selector; they test the rejected config-only hypothesis against the legacy raw producer."
            ),
            (
                f"- Raw 0.051 row: {raw_051_summary}"
            ),
            (
                f"- Best raw micro-threshold row by allowed_count/PNL: {format_markdown_cell(best_raw_micro_row.get('low_vol_min_direction_confidence')) if best_raw_micro_row is not None else 'none'}"
            ),
            "",
            "## Patched strategy_confidence Distribution",
            f"- count={strategy_confidence_distribution.get('count', 0)}, min={format_markdown_cell(strategy_confidence_distribution.get('min'))}, p50={format_markdown_cell(strategy_confidence_distribution.get('p50'))}, p90={format_markdown_cell(strategy_confidence_distribution.get('p90'))}, max={format_markdown_cell(strategy_confidence_distribution.get('max'))}.",
            "",
            "## Selected Normalized Threshold Candidate",
            f"- selection_reason={selection_reason}.",
            f"- LOW_VOLATILITY.min_direction_confidence={selected.thresholds.low_vol_min_direction_confidence}.",
            f"- total_allowed_pnl_pct={format_markdown_cell(selected_metrics.total_allowed_pnl_pct)}, allowed_count={selected_metrics.allowed_count}, allowed_sl_hits={selected_metrics.allowed_sl_hits}.",
            "",
            "### Near-Dominance Pareto Top 20",
        ]
    )
    report_lines.extend(
        render_markdown_table(
            [
                ("label", "label"),
                ("low_vol_min_direction_confidence", "dir_conf"),
                ("min_rr", "min_rr"),
                ("min_tp_fee_coverage", "tp_cov"),
                ("target_net_fee_multiple", "tnf"),
                ("low_vol_min_regime_confidence", "reg_conf"),
                ("delta_allowed_tp_hits", "dTP"),
                ("delta_allowed_sl_hits", "dSL"),
                ("delta_allowed_timeout", "dTimeout"),
                ("delta_allowed_not_filled", "dNotFilled"),
                ("delta_blocked_profitable", "dBlockedProf"),
                ("surface_distance", "distance"),
            ],
            near_dominance_rows,
        )
    )
    report_lines.extend(["", "### Blocked Outcomes By Symbol / Month"])
    report_lines.extend(
        render_markdown_table(
            [
                ("symbol", "symbol"),
                ("month", "month"),
                ("blocked_total", "blocked"),
                ("blocked_profitable", "blocked_tp"),
                ("saved_sl", "saved_sl"),
                ("blocked_timeout", "blocked_timeout"),
                ("blocked_not_filled", "blocked_not_filled"),
                ("net_saved_sl_minus_blocked_profitable", "net_sl_minus_tp"),
            ],
            blocked_breakdown_rows,
        )
    )
    report_lines.extend(["", "### Direction-Confidence Sweep"])
    report_lines.extend(
        render_markdown_table(
            [
                ("low_vol_min_direction_confidence", "dir_conf"),
                ("blocked_count", "blocked"),
                ("allowed_tp_hits", "allowed_tp"),
                ("allowed_sl_hits", "allowed_sl"),
                ("allowed_timeout", "allowed_timeout"),
                ("allowed_not_filled", "allowed_not_filled"),
                ("blocked_profitable", "blocked_profitable"),
                ("delta_allowed_tp_hits", "dTP"),
                ("delta_allowed_sl_hits", "dSL"),
                ("delta_allowed_timeout", "dTimeout"),
                ("delta_allowed_not_filled", "dNotFilled"),
                ("delta_blocked_profitable", "dBlockedProf"),
            ],
            direction_sweep_rows,
        )
    )
    report_lines.extend(["", "### Unlock Cliff Table"])
    report_lines.extend(
        render_markdown_table(
            [
                ("label", "label"),
                ("low_vol_min_direction_confidence", "dir_conf"),
                ("min_rr", "min_rr"),
                ("min_tp_fee_coverage", "tp_cov"),
                ("target_net_fee_multiple", "tnf"),
                ("low_vol_min_regime_confidence", "reg_conf"),
                ("newly_unblocked_total", "new_rows"),
                ("newly_unblocked_tp", "new_tp"),
                ("newly_unblocked_sl", "new_sl"),
                ("newly_unblocked_timeout", "new_timeout"),
                ("newly_unblocked_not_filled", "new_not_filled"),
                ("cumulative_unblocked_total", "cum_rows"),
                ("cumulative_unblocked_tp", "cum_tp"),
                ("cumulative_unblocked_sl", "cum_sl"),
                ("surface_distance", "distance"),
            ],
            list(unlock_cliff_rows)[:20],
        )
    )
    report_lines.extend(["", "### Raw Unlock Cliff Table"])
    report_lines.extend(
        render_markdown_table(
            [
                ("label", "label"),
                ("low_vol_min_direction_confidence", "dir_conf"),
                ("min_rr", "min_rr"),
                ("min_tp_fee_coverage", "tp_cov"),
                ("target_net_fee_multiple", "tnf"),
                ("low_vol_min_regime_confidence", "reg_conf"),
                ("within_relaxed_grid", "in_grid"),
                ("first_relaxed_grid_label", "first_grid_surface"),
                ("newly_unblocked_total", "new_rows"),
                ("newly_unblocked_tp", "new_tp"),
                ("newly_unblocked_sl", "new_sl"),
                ("newly_unblocked_timeout", "new_timeout"),
                ("newly_unblocked_not_filled", "new_not_filled"),
                ("cumulative_unblocked_total", "cum_rows"),
                ("surface_distance", "distance"),
            ],
            list(raw_unlock_cliff_rows)[:20],
        )
    )
    report_lines.extend(["", "### Top Joint Direction Violations"])
    report_lines.extend(
        render_markdown_table(
            [
                ("violations", "violations"),
                ("count", "count"),
            ],
            direction_blocker_summary.get("top_joint_violations") or [],
        )
    )
    report_lines.extend(["", "### Walk-Forward Holdout"])
    report_lines.extend(
        render_markdown_table(
            [
                ("test_month", "test_month"),
                ("train_observations", "train_obs"),
                ("test_observations", "test_obs"),
                ("train_selection_reason", "train_selection"),
                ("selected_low_vol_min_direction_confidence", "selected_dir_conf"),
                ("test_delta_allowed_tp_hits", "test_dTP"),
                ("test_delta_allowed_sl_hits", "test_dSL"),
                ("test_delta_allowed_timeout", "test_dTimeout"),
                ("test_delta_allowed_not_filled", "test_dNotFilled"),
                ("test_delta_blocked_profitable", "test_dBlockedProf"),
            ],
            walk_forward_rows,
        )
    )
    report_lines.extend(
        [
            "",
            "## Contradictions / Evidence Gaps",
            "- Candle-only replay cannot reconstruct live OBI/TFI/depth/macro_resid inputs; v1 candidate generation therefore uses pillar_sum-driven Quadratic scoring with EntryPlan neutral OBI policy.",
            "- Regime replay uses production RegimeDetector with price/high/low feature payloads, but does not route through the full FeatureEngineering event surface.",
            "- Forward outcomes use a 1m passive-touch proxy for entry fills and fail-closed same-bar SL/TP tie-breaking; this is deterministic but still an OHLC proxy, not execution truth.",
            "",
            "## Root Cause Candidates",
            "- If profitable low-vol setups remain blocked, the likely root levers are min_rr, fee-floor thresholds, or LOW_VOLATILITY confidence floors rather than missing TP/SL geometry, because the replay evaluates the gate only after EntryPlan prices exist.",
            "- If no candidate surface dominates baseline, the current NRR-062 policy is more likely a true guardrail than an over-tight calibration error within this candle-only cohort.",
            "",
            "## Operational Risk",
            "- Observability Gap",
            "",
            "## Files / Areas Touched",
            "- calibrators/policy_gates/calibrate_nrr062_historical.py",
            "- tests/tools/test_calibrate_nrr062_historical.py",
            "",
            "## Validation Performed",
            "- Deterministic 1m gap detection and 180s/300s aggregation unit tests.",
            "- Real low_vol_cost_floor gate surface evaluation test with baseline and relaxed min_rr candidate.",
            "- Conservative patch-selection unit test for no-change fallback.",
            "",
            "## Residual Risk",
            "- Historical calibration still depends on Binance OHLC data quality and on passive-touch fill assumptions.",
            "- The report does not claim live execution profitability or microstructure equivalence.",
            "",
            "## What Remains Unproven",
            "- Runtime parity versus live FeatureEngineering-derived non-pillar inputs remains unproven in this v1 candle-only calibration.",
            "- Grid search does not optimize all possible gate dimensions or execution semantics.",
            "",
            "## Minimal Safe Verdict",
            f"- {selection_reason}.",
        ]
    )
    return "\n".join(report_lines) + "\n"


def build_patch_candidate_payload(
    *,
    baseline: SurfaceEvaluation,
    selected: SurfaceEvaluation,
    selection_reason: str,
) -> dict[str, Any]:
    return {
        "_meta": {
            "selection_reason": selection_reason,
            "direction_contract_mode": PATCHED_DIRECTION_CONTRACT,
            "baseline": surface_to_dict(baseline),
            "selected": surface_to_dict(selected),
        },
        "decision_making": {
            "low_vol_cost_floor_gate": {
                "thresholds": {
                    "min_direction_confidence_by_regime": {
                        "LOW_VOLATILITY": selected.thresholds.low_vol_min_direction_confidence,
                    },
                }
            }
        },
    }


def run_calibration(args: argparse.Namespace) -> dict[str, Any]:
    if args.timeout_bars <= 0:
        raise ValueError("--timeout-bars must be > 0")

    start_date = parse_utc_date(args.start_date)
    end_date = parse_utc_date(args.end_date)
    if end_date < start_date:
        raise ValueError("end-date must be >= start-date")
    end_date_exclusive = end_date + timedelta(days=1)

    raw_dir = Path(args.raw_data_dir)
    processed_dir = Path(args.processed_dir)
    artifacts_dir = Path(args.artifacts_dir)
    reports_dir = Path(args.reports_dir)

    emit_progress(
        f"starting calibration: symbols={','.join(args.symbols)} window={args.start_date}..{args.end_date} mode={args.trading_mode}"
    )

    runtime_cfg = load_runtime_config()
    decision_cfg, assets_cfg = load_aurora_strategy_contract()
    pillar_cfg = load_pillar_contract()
    entry_plan = build_entry_plan(
        runtime_cfg.domains.decision_making.entry_plan)
    gate_cfg = runtime_cfg.domains.decision_making.low_vol_cost_floor_gate

    processed_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    coverage: list[CoverageSummary] = []
    all_observations: list[GateObservation] = []
    loaded_bars_by_symbol: dict[str, list[HistoricalBar]] = {}
    common_end_open_ms = date_to_ms(end_date_exclusive) - 60_000

    for symbol in args.symbols:
        asset_cfg = assets_cfg.get(symbol)
        if not isinstance(asset_cfg, dict):
            raise ValueError(f"Missing aurora asset config for {symbol}")

        emit_progress(f"{symbol}: resolving 1m source bars")
        bars_1m = load_or_download_1m_bars(
            symbol=symbol,
            start_date=start_date,
            end_date_exclusive=end_date_exclusive,
            raw_dir=raw_dir,
            request_timeout_sec=args.request_timeout_sec,
        )
        gaps = detect_missing_1m_gaps(bars_1m)
        if gaps:
            first_gap = gaps[0]
            raise ValueError(
                f"Gap detected for {symbol}: expected {first_gap.expected_open_time_ms}, got {first_gap.actual_open_time_ms}"
            )

        loaded_bars_by_symbol[symbol] = bars_1m
        common_end_open_ms = min(common_end_open_ms, bars_1m[-1].open_time_ms)

    emit_progress(
        f"aligned common source end to {iso_utc_from_ms(common_end_open_ms)}"
    )

    for symbol in args.symbols:
        asset_cfg = assets_cfg.get(symbol)
        if not isinstance(asset_cfg, dict):
            raise ValueError(f"Missing aurora asset config for {symbol}")

        bars_1m = [
            bar
            for bar in loaded_bars_by_symbol[symbol]
            if bar.open_time_ms <= common_end_open_ms
        ]
        gaps = detect_missing_1m_gaps(bars_1m)
        if gaps:
            first_gap = gaps[0]
            raise ValueError(
                f"Gap detected after common-end trim for {symbol}: expected {first_gap.expected_open_time_ms}, got {first_gap.actual_open_time_ms}"
            )

        emit_progress(f"{symbol}: aggregating 1m bars into runtime timeframes")
        bars_180 = aggregate_1m_bars(bars_1m, 180)
        bars_300 = aggregate_1m_bars(bars_1m, 300)
        bars_900 = aggregate_1m_bars(bars_1m, 900)
        bars_4h = aggregate_1m_bars(bars_1m, pillar_cfg.operator_tf_sec)
        bars_1d = aggregate_1m_bars(bars_1m, pillar_cfg.strategist_tf_sec)

        write_bar_csv(processed_dir / f"{symbol}_180.csv", bars_180)
        write_bar_csv(processed_dir / f"{symbol}_300.csv", bars_300)
        write_bar_csv(processed_dir / f"{symbol}_900.csv", bars_900)

        emit_progress(
            f"{symbol}: replaying regime detector on {len(bars_300)} x 300s bars")
        regime_by_ts = replay_regimes(runtime_cfg, bars_300)
        emit_progress(f"{symbol}: computing pillar snapshots")
        pillar_by_ts = compute_pillar_snapshots(
            bars_300=bars_300,
            bars_900=bars_900,
            bars_4h=bars_4h,
            bars_1d=bars_1d,
            pillar_cfg=pillar_cfg,
        )

        emit_progress(f"{symbol}: building gate observations")
        observations = build_gate_observations_for_symbol(
            symbol=symbol,
            bars_300=bars_300,
            bars_1m=bars_1m,
            regime_by_ts=regime_by_ts,
            pillar_by_ts=pillar_by_ts,
            decision_cfg=decision_cfg,
            asset_cfg=asset_cfg,
            entry_plan=entry_plan,
            entry_plan_cfg=runtime_cfg.domains.decision_making.entry_plan,
            timeout_bars=args.timeout_bars,
        )
        all_observations.extend(observations)
        emit_progress(
            f"{symbol}: observations={len(observations)} 300s={len(bars_300)} 900s={len(bars_900)}"
        )

        coverage.append(
            CoverageSummary(
                symbol=symbol,
                start_open_time_ms=bars_1m[0].open_time_ms,
                end_open_time_ms=bars_1m[-1].open_time_ms,
                bar_count_1m=len(bars_1m),
                gaps_detected=len(gaps),
                counts_by_tf={
                    "180": len(bars_180),
                    "300": len(bars_300),
                    "900": len(bars_900),
                },
            )
        )

    emit_progress(
        f"evaluating baseline gate surface over {len(all_observations)} observations")
    legacy_baseline_rows, legacy_baseline_metrics = evaluate_surface(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
        contract_mode=LEGACY_DIRECTION_CONTRACT,
    )
    patched_baseline_rows, patched_baseline_metrics = evaluate_surface(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
        contract_mode=PATCHED_DIRECTION_CONTRACT,
    )
    candidate_surfaces = evaluate_candidate_surfaces(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
        contract_mode=PATCHED_DIRECTION_CONTRACT,
    )
    baseline_surface = next(
        surface for surface in candidate_surfaces if surface.label == "baseline")
    legacy_baseline_surface = SurfaceEvaluation(
        label="legacy_baseline",
        thresholds=baseline_surface.thresholds,
        metrics=legacy_baseline_metrics,
    )
    baseline_surface = SurfaceEvaluation(
        label=baseline_surface.label,
        thresholds=baseline_surface.thresholds,
        metrics=patched_baseline_metrics,
    )
    non_baseline_surfaces = [
        surface for surface in candidate_surfaces if surface.label != "baseline"]
    selected_surface, selection_reason = select_patch_candidate(
        baseline_surface, non_baseline_surfaces)
    emit_progress(f"surface selection verdict: {selection_reason}")

    near_dominance_rows, near_dominance_frontier_count, near_dominance_tp_gain_count = build_near_dominant_pareto_table(
        baseline_surface,
        non_baseline_surfaces,
    )
    blocked_breakdown_rows = build_symbol_month_blocked_breakdown(
        patched_baseline_rows)
    direction_blocker_summary = build_direction_blocker_summary(
        legacy_baseline_rows)
    unlock_cliff_rows, unlock_cliff_summary = build_unlock_cliff_table(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
        contract_mode=PATCHED_DIRECTION_CONTRACT,
    )
    raw_unlock_cliff_rows, raw_unlock_cliff_summary = build_raw_unlock_cliff_table(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
        contract_mode=LEGACY_DIRECTION_CONTRACT,
    )
    direction_sweep_rows = build_direction_confidence_sweep(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
    )
    raw_micro_threshold_rows = [
        row for row in direction_sweep_rows if row.get("contract_mode") == LEGACY_DIRECTION_CONTRACT
    ]
    walk_forward_rows = build_walk_forward_analysis(
        observations=all_observations,
        gate_cfg=gate_cfg,
        trading_mode=args.trading_mode,
        contract_mode=PATCHED_DIRECTION_CONTRACT,
    )
    strategy_confidence_distribution = build_strategy_confidence_distribution(
        all_observations
    )

    candidate_rows_path = processed_dir / "candidate_rows.csv"
    write_candidate_rows_csv(candidate_rows_path, patched_baseline_rows)
    near_dominance_path = artifacts_dir / "near_dominance_top20.csv"
    blocked_breakdown_path = artifacts_dir / "blocked_outcomes_by_symbol_month.csv"
    direction_sweep_path = artifacts_dir / "direction_confidence_sweep.csv"
    unlock_cliff_path = artifacts_dir / "unlock_cliff_table.csv"
    raw_unlock_cliff_path = artifacts_dir / "raw_unlock_cliff_table.csv"
    walk_forward_path = artifacts_dir / "walk_forward_summary.csv"
    write_rows_csv(
        near_dominance_path,
        near_dominance_rows,
        [
            "label",
            "target_net_fee_multiple",
            "min_tp_fee_coverage",
            "min_rr",
            "low_vol_min_regime_confidence",
            "low_vol_min_direction_confidence",
            "delta_allowed_tp_hits",
            "delta_allowed_sl_hits",
            "delta_allowed_timeout",
            "delta_allowed_not_filled",
            "delta_blocked_profitable",
            "delta_blocked_count",
            "surface_distance",
        ],
    )
    write_rows_csv(
        blocked_breakdown_path,
        blocked_breakdown_rows,
        [
            "symbol",
            "month",
            "blocked_total",
            "blocked_profitable",
            "saved_sl",
            "blocked_timeout",
            "blocked_not_filled",
            "net_saved_sl_minus_blocked_profitable",
        ],
    )
    write_rows_csv(
        direction_sweep_path,
        direction_sweep_rows,
        [
            "contract_mode",
            "low_vol_min_direction_confidence",
            "allowed_count",
            "blocked_count",
            "allowed_tp_hits",
            "allowed_sl_hits",
            "allowed_timeout",
            "allowed_not_filled",
            "total_allowed_pnl_pct",
            "blocked_profitable",
            "delta_allowed_tp_hits",
            "delta_allowed_sl_hits",
            "delta_allowed_timeout",
            "delta_allowed_not_filled",
            "delta_total_allowed_pnl_pct",
            "delta_blocked_profitable",
            "delta_blocked_count",
        ],
    )
    write_rows_csv(
        unlock_cliff_path,
        unlock_cliff_rows,
        [
            "label",
            "surface_distance",
            "target_net_fee_multiple",
            "min_tp_fee_coverage",
            "min_rr",
            "low_vol_min_regime_confidence",
            "low_vol_min_direction_confidence",
            "newly_unblocked_total",
            "newly_unblocked_tp",
            "newly_unblocked_sl",
            "newly_unblocked_timeout",
            "newly_unblocked_not_filled",
            "cumulative_unblocked_total",
            "cumulative_unblocked_tp",
            "cumulative_unblocked_sl",
            "cumulative_unblocked_timeout",
            "cumulative_unblocked_not_filled",
        ],
    )
    write_rows_csv(
        raw_unlock_cliff_path,
        raw_unlock_cliff_rows,
        [
            "label",
            "surface_distance",
            "target_net_fee_multiple",
            "min_tp_fee_coverage",
            "min_rr",
            "low_vol_min_regime_confidence",
            "low_vol_min_direction_confidence",
            "within_relaxed_grid",
            "first_relaxed_grid_label",
            "newly_unblocked_total",
            "newly_unblocked_tp",
            "newly_unblocked_sl",
            "newly_unblocked_timeout",
            "newly_unblocked_not_filled",
            "cumulative_unblocked_total",
            "cumulative_unblocked_tp",
            "cumulative_unblocked_sl",
            "cumulative_unblocked_timeout",
            "cumulative_unblocked_not_filled",
        ],
    )
    write_rows_csv(
        walk_forward_path,
        walk_forward_rows,
        [
            "test_month",
            "train_observations",
            "test_observations",
            "train_selection_reason",
            "selected_label",
            "selected_target_net_fee_multiple",
            "selected_min_tp_fee_coverage",
            "selected_min_rr",
            "selected_low_vol_min_regime_confidence",
            "selected_low_vol_min_direction_confidence",
            "test_delta_allowed_tp_hits",
            "test_delta_allowed_sl_hits",
            "test_delta_allowed_timeout",
            "test_delta_allowed_not_filled",
            "test_delta_blocked_profitable",
        ],
    )

    report_text = render_report(
        args=args,
        coverage=coverage,
        legacy_baseline=legacy_baseline_surface,
        baseline=baseline_surface,
        selected=selected_surface,
        selection_reason=selection_reason,
        observations=all_observations,
        near_dominance_rows=near_dominance_rows,
        near_dominance_frontier_count=near_dominance_frontier_count,
        near_dominance_tp_gain_count=near_dominance_tp_gain_count,
        blocked_breakdown_rows=blocked_breakdown_rows,
        direction_blocker_summary=direction_blocker_summary,
        unlock_cliff_rows=unlock_cliff_rows,
        unlock_cliff_summary=unlock_cliff_summary,
        raw_unlock_cliff_rows=raw_unlock_cliff_rows,
        raw_unlock_cliff_summary=raw_unlock_cliff_summary,
        direction_sweep_rows=direction_sweep_rows,
        walk_forward_rows=walk_forward_rows,
        strategy_confidence_distribution=strategy_confidence_distribution,
        raw_micro_threshold_rows=raw_micro_threshold_rows,
    )
    report_path = reports_dir / REPORT_PATH.name
    report_path.write_text(report_text, encoding="utf-8")

    patch_payload = build_patch_candidate_payload(
        baseline=baseline_surface,
        selected=selected_surface,
        selection_reason=selection_reason,
    )
    patch_path = reports_dir / PATCH_PATH.name
    patch_path.write_text(
        yaml.safe_dump(patch_payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )

    results_payload = {
        "meta": {
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
            "symbols": list(args.symbols),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "requested_end_open_utc": iso_utc_from_ms(date_to_ms(end_date_exclusive) - 60_000),
            "actual_common_end_open_utc": iso_utc_from_ms(common_end_open_ms),
            "trading_mode": args.trading_mode,
            "timeout_bars": args.timeout_bars,
            "timeframes_sec": list(DEFAULT_TIMEFRAMES_SEC),
            "selection_reason": selection_reason,
        },
        "coverage": [coverage_to_dict(item) for item in coverage],
        "legacy_contract_baseline": surface_to_dict(legacy_baseline_surface),
        "patched_contract_baseline": surface_to_dict(baseline_surface),
        "patched_selected_candidate": surface_to_dict(selected_surface),
        "raw_micro_threshold_diagnostic": {
            "contract_mode": LEGACY_DIRECTION_CONTRACT,
            "rows": raw_micro_threshold_rows,
        },
        "baseline": surface_to_dict(baseline_surface),
        "selected": surface_to_dict(selected_surface),
        "candidate_surface_count": len(candidate_surfaces),
        "supplemental_analysis": {
            "strategy_confidence_distribution": strategy_confidence_distribution,
            "near_dominance": {
                "tp_gain_candidate_count": near_dominance_tp_gain_count,
                "pareto_frontier_count": near_dominance_frontier_count,
                "top20": near_dominance_rows,
            },
            "blocked_outcomes_by_symbol_month": blocked_breakdown_rows,
            "direction_blocker_summary": direction_blocker_summary,
            "unlock_cliff": {
                "summary": unlock_cliff_summary,
                "rows": unlock_cliff_rows,
            },
            "raw_unlock_cliff": {
                "summary": raw_unlock_cliff_summary,
                "rows": raw_unlock_cliff_rows,
            },
            "direction_confidence_sweep": direction_sweep_rows,
            "walk_forward": {
                "method": "expanding_train_last_three_observation_months",
                "splits": walk_forward_rows,
            },
        },
        "artifacts": {
            "candidate_rows_csv": str(candidate_rows_path),
            "report_md": str(report_path),
            "patch_yaml": str(patch_path),
            "near_dominance_csv": str(near_dominance_path),
            "blocked_outcomes_by_symbol_month_csv": str(blocked_breakdown_path),
            "direction_confidence_sweep_csv": str(direction_sweep_path),
            "unlock_cliff_csv": str(unlock_cliff_path),
            "raw_unlock_cliff_csv": str(raw_unlock_cliff_path),
            "walk_forward_csv": str(walk_forward_path),
        },
    }
    results_path = artifacts_dir / RESULTS_PATH.name
    results_path.write_text(
        json.dumps(results_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    emit_progress(
        f"completed calibration; artifacts written to {results_path.parent} and {report_path.parent}"
    )

    return {
        "results_path": str(results_path),
        "report_path": str(report_path),
        "patch_path": str(patch_path),
        "candidate_rows_path": str(candidate_rows_path),
        "selection_reason": selection_reason,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NRR062 historical candle calibration using real low_vol_cost_floor gate evaluation",
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--trading-mode", default="testnet")
    parser.add_argument("--timeout-bars", type=int,
                        default=DEFAULT_TIMEOUT_BARS)
    parser.add_argument("--request-timeout-sec", type=int, default=30)
    parser.add_argument("--raw-data-dir", default=str(RAW_DATA_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--artifacts-dir", default=str(ARTIFACTS_DIR))
    parser.add_argument("--reports-dir", default=str(REPORTS_DIR))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_calibration(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
