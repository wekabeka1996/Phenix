from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "reports"
RECORDER_DIR = ROOT / "data" / "recorder"
CONFIG_DIR = ROOT / "config" / "aurora"

DOMAINS_YAML = CONFIG_DIR / "domains.yaml"
AURORA_STRATEGY_YAML = CONFIG_DIR / "strategies" / "aurora.yaml"

TREND_REGIMES = {"TREND_UP", "TREND_DOWN"}
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DEFAULT_MAX_BARS = 18
DEFAULT_PURE_DATASET = REPORTS_DIR / \
    "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"
DEFAULT_OUTPUT_PREFIX = "AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1_2026_05_04"


@dataclass
class PureRow:
    timestamp_ms: int
    timestamp: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    regime: str
    regime_confidence: float
    regime_age_bars: int


@dataclass
class RecorderRow:
    timestamp_ms: int
    timestamp: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    regime: str
    regime_confidence: float | None
    pillar_sum: float | None


@dataclass
class JoinedBar:
    timestamp: str
    timestamp_ms: int
    symbol: str
    regime: str
    regime_confidence: float
    regime_age_bars: int
    open: float
    high: float
    low: float
    close: float
    pure_trend_side: str
    aurora_side: str
    aurora_score: float | None
    aurora_signal_emitted: str
    aurora_reject_reason: str
    aurora_entry_timestamp: str
    aurora_entry_price: float | None
    pure_entry_timestamp: str
    pure_entry_price: float
    entry_delay_bars: int | None
    entry_price_delta_bps: float | None
    local_position_in_range: float | None
    tp_distance_bps: float | None
    sl_distance_bps: float | None
    timeout_bars: int
    pure_outcome: str
    aurora_outcome: str
    pure_pnl_pct: float
    aurora_pnl_pct: float | None
    mfe_bps_after_aurora_entry: float | None
    mae_bps_after_aurora_entry: float | None
    mfe_bps_after_pure_entry: float
    mae_bps_after_pure_entry: float
    pure_exit_reason: str
    pure_exit_timestamp: str
    aurora_exit_timestamp: str
    recorder_regime: str
    recorder_regime_confidence: float | None
    regime_match: bool | None
    segment_bar_index: int
    segment_length_bars: int


@dataclass
class TradeSummary:
    entry_timestamp_ms: int
    entry_timestamp: str
    entry_price: float
    side: str
    outcome: str
    pnl_pct: float
    exit_reason: str
    exit_timestamp: str
    exit_timestamp_ms: int
    bars_held: int
    tp_distance_bps: float
    sl_distance_bps: float
    mfe_bps: float
    mae_bps: float


@dataclass
class SegmentSummary:
    symbol: str
    segment_start_ms: int
    segment_end_ms: int
    segment_length_bars: int
    regime: str
    pure_side: str
    pure_trade: TradeSummary
    aurora_trade: TradeSummary | None
    first_aurora_entry_index: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1",
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--pure-dataset", default=str(DEFAULT_PURE_DATASET))
    parser.add_argument("--window-start", default=None)
    parser.add_argument("--window-end", default=None)
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def safe_float(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def safe_int(value: Any) -> int | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def iso_to_ms(text: str) -> int:
    normalized = str(text).replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).timestamp() * 1000)


def ms_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping in {path}")
    return raw


def dates_in_range(start_day: date, end_day: date) -> list[date]:
    current = start_day
    days: list[date] = []
    while current <= end_day:
        days.append(current)
        current += timedelta(days=1)
    return days


def find_recorder_coverage() -> tuple[date, date]:
    if not RECORDER_DIR.exists():
        raise ValueError(f"Recorder directory does not exist: {RECORDER_DIR}")
    days: list[date] = []
    for child in RECORDER_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            days.append(date.fromisoformat(child.name))
        except ValueError:
            continue
    if not days:
        raise ValueError("No recorder day directories found")
    return min(days), max(days)


def resolve_overlap_window(
    pure_rows: list[PureRow],
    user_start: str | None,
    user_end: str | None,
) -> tuple[date, date]:
    recorder_start, recorder_end = find_recorder_coverage()
    pure_days = [datetime.fromtimestamp(
        row.timestamp_ms / 1000.0, tz=UTC).date() for row in pure_rows]
    pure_start = min(pure_days)
    pure_end = max(pure_days)
    start_day = max(recorder_start, pure_start)
    end_day = min(recorder_end, pure_end)
    if user_start is not None:
        start_day = max(start_day, date.fromisoformat(user_start))
    if user_end is not None:
        end_day = min(end_day, date.fromisoformat(user_end))
    if end_day < start_day:
        raise ValueError(
            f"No overlap window between pure dataset and recorder coverage: pure={pure_start}..{pure_end}, recorder={recorder_start}..{recorder_end}"
        )
    return start_day, end_day


def load_pure_dataset(path: Path, symbols: set[str]) -> list[PureRow]:
    if not path.exists():
        raise ValueError(f"Pure dataset not found: {path}")
    rows: list[PureRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for record in reader:
            symbol = str(record.get("symbol") or "").upper()
            if symbol not in symbols:
                continue
            timestamp = str(record.get("timestamp") or "")
            timestamp_ms = iso_to_ms(timestamp)
            open_value = safe_float(record.get("open"))
            high_value = safe_float(record.get("high"))
            low_value = safe_float(record.get("low"))
            close_value = safe_float(record.get("close"))
            volume_value = safe_float(record.get("volume"))
            confidence = safe_float(record.get("regime_confidence"))
            regime_age = safe_int(record.get("regime_age_bars"))
            regime = str(record.get("regime") or "").upper()
            if None in (
                open_value,
                high_value,
                low_value,
                close_value,
                volume_value,
                confidence,
                regime_age,
            ):
                continue
            rows.append(
                PureRow(
                    timestamp_ms=timestamp_ms,
                    timestamp=timestamp,
                    symbol=symbol,
                    open=float(open_value),
                    high=float(high_value),
                    low=float(low_value),
                    close=float(close_value),
                    volume=float(volume_value),
                    regime=regime,
                    regime_confidence=float(confidence),
                    regime_age_bars=int(regime_age),
                )
            )
    if not rows:
        raise ValueError("No pure dataset rows loaded for requested symbols")
    return sorted(rows, key=lambda row: (row.symbol, row.timestamp_ms))


def load_recorder_rows(symbols: set[str], start_day: date, end_day: date) -> list[RecorderRow]:
    rows: list[RecorderRow] = []
    for day in dates_in_range(start_day, end_day):
        day_dir = RECORDER_DIR / day.isoformat()
        if not day_dir.exists():
            continue
        for symbol in symbols:
            csv_path = day_dir / f"{symbol}_300.csv"
            if not csv_path.exists():
                continue
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for record in reader:
                    ready = str(record.get("ready") or "").strip().lower()
                    if ready not in ("true", "1"):
                        continue
                    regime = str(record.get("regime") or "").strip().upper()
                    if not regime:
                        regime = "PENDING"
                    timestamp_ms = safe_int(record.get("timestamp"))
                    open_value = safe_float(record.get("open"))
                    high_value = safe_float(record.get("high"))
                    low_value = safe_float(record.get("low"))
                    close_value = safe_float(record.get("close"))
                    confidence = safe_float(record.get("regime_conf"))
                    pillar_sum = safe_float(record.get("feat_pillar_sum"))
                    if None in (
                        timestamp_ms,
                        open_value,
                        high_value,
                        low_value,
                        close_value,
                    ):
                        continue
                    rows.append(
                        RecorderRow(
                            timestamp_ms=int(timestamp_ms),
                            timestamp=ms_to_iso(int(timestamp_ms)),
                            symbol=symbol,
                            open=float(open_value),
                            high=float(high_value),
                            low=float(low_value),
                            close=float(close_value),
                            regime=regime,
                            regime_confidence=(
                                float(confidence) if confidence is not None else None),
                            pillar_sum=(float(pillar_sum)
                                        if pillar_sum is not None else None),
                        )
                    )
    if not rows:
        raise ValueError(
            "No recorder rows loaded for requested symbols and overlap window")
    return sorted(rows, key=lambda row: (row.symbol, row.timestamp_ms))


def resolve_regime_threshold(regime: str, mapping: dict[str, Any], default: float | None) -> float | None:
    direct = safe_float(mapping.get(regime)) if isinstance(
        mapping, dict) else None
    if direct is not None:
        return direct
    fallback = safe_float(mapping.get("DEFAULT")) if isinstance(
        mapping, dict) else None
    if fallback is not None:
        return fallback
    return default


def side_from_score(score: float, threshold: float) -> str:
    if score >= threshold:
        return "LONG"
    if score <= -threshold:
        return "SHORT"
    return ""


def load_cfg() -> tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]:
    strategy_data = load_yaml(AURORA_STRATEGY_YAML)
    aurora = strategy_data.get("aurora") or {}
    decision_cfg = aurora.get("decision") or {}
    signal_threshold = safe_float(decision_cfg.get("signal_threshold"))
    if signal_threshold is None:
        raise ValueError("Missing aurora.decision.signal_threshold")
    assets_cfg = aurora.get("assets") or {}
    if not isinstance(assets_cfg, dict):
        raise ValueError("aurora.assets must be mapping")

    domains = load_yaml(DOMAINS_YAML)
    decision_making = domains.get("decision_making") or {}
    directional_cfg = decision_making.get("directional_sanity") or {}
    low_vol_cfg = decision_making.get("low_vol_cost_floor_gate") or {}
    return float(signal_threshold), assets_cfg, directional_cfg, low_vol_cfg


def apply_current_gates(
    regime: str,
    regime_confidence: float,
    pillar_sum: float,
    side: str,
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    if not side:
        return False, "NO_SIDE"

    min_default = safe_float(directional_cfg.get("min_regime_confidence"))
    min_map = directional_cfg.get("min_regime_confidence_by_regime") or {}
    max_map = directional_cfg.get("max_regime_confidence_by_regime") or {}

    min_required = resolve_regime_threshold(regime, min_map, min_default)
    if min_required is not None and regime_confidence < min_required:
        return False, "REGIME_CONFIDENCE_BELOW_MIN"

    max_allowed = resolve_regime_threshold(regime, max_map, None)
    if max_allowed is not None and regime_confidence > max_allowed:
        return False, "REGIME_CONFIDENCE_ABOVE_MAX"

    gated_regimes = [str(item).strip().upper()
                     for item in (low_vol_cfg.get("regimes") or [])]
    if regime == "LOW_VOLATILITY" and "LOW_VOLATILITY" in gated_regimes:
        thresholds = low_vol_cfg.get("thresholds") or {}
        dir_map = thresholds.get("min_direction_confidence_by_regime") or {}
        min_dir = resolve_regime_threshold("LOW_VOLATILITY", dir_map, None)
        if min_dir is not None and abs(pillar_sum) < min_dir:
            return False, "LOW_VOL_DIRECTION_CONFIDENCE_BELOW_MIN"

    return True, None


def resolve_known_regime_gate(
    regime: str,
    regime_confidence: float,
    directional_cfg: dict[str, Any],
) -> str | None:
    min_default = safe_float(directional_cfg.get("min_regime_confidence"))
    min_map = directional_cfg.get("min_regime_confidence_by_regime") or {}
    max_map = directional_cfg.get("max_regime_confidence_by_regime") or {}

    min_required = resolve_regime_threshold(regime, min_map, min_default)
    if min_required is not None and regime_confidence < min_required:
        return "REGIME_CONFIDENCE_BELOW_MIN"

    max_allowed = resolve_regime_threshold(regime, max_map, None)
    if max_allowed is not None and regime_confidence > max_allowed:
        return "REGIME_CONFIDENCE_ABOVE_MAX"
    return None


def resolve_tpsl(asset_cfg: dict[str, Any], regime: str) -> tuple[float, float] | None:
    exit_cfg = asset_cfg.get("exit") or {}
    take_profit_cfg = asset_cfg.get("take_profit") or {}
    regime_tpsl = exit_cfg.get("regime_tpsl") or {}
    if not bool(regime_tpsl.get("enabled")):
        return None
    if str(regime_tpsl.get("mode") or "pct_mult") != "pct_mult":
        return None

    sl_base = safe_float(exit_cfg.get("sl_pct"))
    tp_low_ratio = safe_float(take_profit_cfg.get("tp_low_ratio"))
    if sl_base is None or tp_low_ratio is None:
        return None

    sl_map = regime_tpsl.get("sl_mult") or {}
    tp_map = regime_tpsl.get("tp_mult") or {}
    sl_mult = safe_float(sl_map.get(regime))
    if sl_mult is None:
        sl_mult = safe_float(sl_map.get("DEFAULT"))
    tp_mult = safe_float(tp_map.get(regime))
    if tp_mult is None:
        tp_mult = safe_float(tp_map.get("DEFAULT"))
    if sl_mult is None or tp_mult is None:
        return None

    sl_pct = sl_base * sl_mult
    tp_pct = sl_pct * tp_low_ratio * tp_mult
    if sl_pct <= 0 or tp_pct <= 0:
        return None
    return float(sl_pct), float(tp_pct)


def simulate_exit(
    bars: list[JoinedBar],
    entry_index: int,
    side: str,
    entry_price: float,
    sl_pct: float,
    tp_pct: float,
    timeout_bars: int,
    regime_exit: bool,
    regime_for_exit: str,
) -> TradeSummary:
    if side == "LONG":
        stop_price = entry_price * (1.0 - sl_pct)
        target_price = entry_price * (1.0 + tp_pct)
    else:
        stop_price = entry_price * (1.0 + sl_pct)
        target_price = entry_price * (1.0 - tp_pct)

    tp_distance_bps = tp_pct * 10000.0
    sl_distance_bps = sl_pct * 10000.0
    mfe_bps = 0.0
    mae_bps = 0.0
    exit_reason = "END_OF_DATA"
    exit_index = entry_index
    exit_price = entry_price

    for offset, bar in enumerate(bars[entry_index + 1:], start=1):
        if side == "LONG":
            favorable = (bar.close - entry_price) / entry_price * 10000.0
            adverse = (bar.low - entry_price) / entry_price * 10000.0
            sl_hit = bar.low <= stop_price
            tp_hit = bar.high >= target_price
        else:
            favorable = (entry_price - bar.close) / entry_price * 10000.0
            adverse = (entry_price - bar.high) / entry_price * 10000.0
            sl_hit = bar.high >= stop_price
            tp_hit = bar.low <= target_price

        mfe_bps = max(mfe_bps, favorable)
        mae_bps = min(mae_bps, adverse)

        if sl_hit and tp_hit:
            tp_hit = False

        if sl_hit:
            exit_reason = "SL"
            exit_index = entry_index + offset
            exit_price = stop_price
            break
        if tp_hit:
            exit_reason = "TP"
            exit_index = entry_index + offset
            exit_price = target_price
            break
        if regime_exit and bar.regime != regime_for_exit:
            exit_reason = "REGIME_CHANGE"
            exit_index = entry_index + offset
            exit_price = bar.close
            break
        if offset >= timeout_bars:
            exit_reason = "TIMEOUT"
            exit_index = entry_index + offset
            exit_price = bar.close
            break
    else:
        if len(bars) > entry_index + 1:
            exit_index = len(bars) - 1
            exit_price = bars[-1].close

    if side == "LONG":
        pnl_pct = (exit_price - entry_price) / entry_price * 100.0
    else:
        pnl_pct = (entry_price - exit_price) / entry_price * 100.0

    return TradeSummary(
        entry_timestamp_ms=bars[entry_index].timestamp_ms,
        entry_timestamp=bars[entry_index].timestamp,
        entry_price=float(entry_price),
        side=side,
        outcome=exit_reason,
        pnl_pct=float(pnl_pct),
        exit_reason=exit_reason,
        exit_timestamp=bars[exit_index].timestamp,
        exit_timestamp_ms=bars[exit_index].timestamp_ms,
        bars_held=max(0, exit_index - entry_index),
        tp_distance_bps=float(tp_distance_bps),
        sl_distance_bps=float(sl_distance_bps),
        mfe_bps=float(mfe_bps),
        mae_bps=float(mae_bps),
    )


def build_joined_bars(
    pure_rows: list[PureRow],
    recorder_rows: list[RecorderRow],
) -> list[JoinedBar]:
    recorder_by_key = {(row.symbol, row.timestamp_ms)                       : row for row in recorder_rows}
    joined: list[JoinedBar] = []
    for pure_row in pure_rows:
        recorder_row = recorder_by_key.get(
            (pure_row.symbol, pure_row.timestamp_ms))
        if recorder_row is None:
            continue
        if pure_row.regime not in TREND_REGIMES:
            continue
        joined.append(
            JoinedBar(
                timestamp=pure_row.timestamp,
                timestamp_ms=pure_row.timestamp_ms,
                symbol=pure_row.symbol,
                regime=pure_row.regime,
                regime_confidence=pure_row.regime_confidence,
                regime_age_bars=pure_row.regime_age_bars,
                open=pure_row.open,
                high=pure_row.high,
                low=pure_row.low,
                close=pure_row.close,
                pure_trend_side="LONG" if pure_row.regime == "TREND_UP" else "SHORT",
                aurora_side="",
                aurora_score=recorder_row.pillar_sum,
                aurora_signal_emitted="UNKNOWN",
                aurora_reject_reason="",
                aurora_entry_timestamp="",
                aurora_entry_price=None,
                pure_entry_timestamp="",
                pure_entry_price=0.0,
                entry_delay_bars=None,
                entry_price_delta_bps=None,
                local_position_in_range=None,
                tp_distance_bps=None,
                sl_distance_bps=None,
                timeout_bars=DEFAULT_MAX_BARS,
                pure_outcome="",
                aurora_outcome="",
                pure_pnl_pct=0.0,
                aurora_pnl_pct=None,
                mfe_bps_after_aurora_entry=None,
                mae_bps_after_aurora_entry=None,
                mfe_bps_after_pure_entry=0.0,
                mae_bps_after_pure_entry=0.0,
                pure_exit_reason="",
                pure_exit_timestamp="",
                aurora_exit_timestamp="",
                recorder_regime=recorder_row.regime,
                recorder_regime_confidence=recorder_row.regime_confidence,
                regime_match=(
                    pure_row.regime == recorder_row.regime if recorder_row.regime in TREND_REGIMES else None),
                segment_bar_index=0,
                segment_length_bars=0,
            )
        )
    if not joined:
        raise ValueError(
            "No TREND rows joined between pure dataset and recorder")
    return sorted(joined, key=lambda row: (row.symbol, row.timestamp_ms))


def group_segments(rows: list[JoinedBar]) -> dict[str, list[list[JoinedBar]]]:
    by_symbol: dict[str, list[JoinedBar]] = defaultdict(list)
    for row in rows:
        by_symbol[row.symbol].append(row)

    grouped: dict[str, list[list[JoinedBar]]] = {}
    for symbol, symbol_rows in by_symbol.items():
        symbol_rows.sort(key=lambda row: row.timestamp_ms)
        segments: list[list[JoinedBar]] = []
        current: list[JoinedBar] = []
        previous_regime: str | None = None
        previous_ts_ms: int | None = None
        for row in symbol_rows:
            continuous = previous_ts_ms is not None and (
                row.timestamp_ms - previous_ts_ms) == 300000
            if current and row.regime == previous_regime and continuous:
                current.append(row)
            else:
                if current:
                    segments.append(current)
                current = [row]
            previous_regime = row.regime
            previous_ts_ms = row.timestamp_ms
        if current:
            segments.append(current)
        grouped[symbol] = segments
    return grouped


def local_position(index: int, segment_length: int) -> float:
    if segment_length <= 1:
        return 0.0
    return index / float(segment_length - 1)


def analyze_segments(
    joined_rows: list[JoinedBar],
    signal_threshold: float,
    assets_cfg: dict[str, Any],
    directional_cfg: dict[str, Any],
    low_vol_cfg: dict[str, Any],
    max_bars: int,
) -> tuple[list[JoinedBar], list[SegmentSummary], dict[str, Any]]:
    rows_by_symbol = defaultdict(list)
    for row in joined_rows:
        rows_by_symbol[row.symbol].append(row)
    for symbol_rows in rows_by_symbol.values():
        symbol_rows.sort(key=lambda row: row.timestamp_ms)

    segments = group_segments(joined_rows)
    segment_summaries: list[SegmentSummary] = []
    counters: Counter[str] = Counter()
    mismatch_count = 0

    for symbol, symbol_segments in segments.items():
        asset_cfg = assets_cfg.get(symbol)
        if not isinstance(asset_cfg, dict):
            raise ValueError(f"Missing aurora asset config for {symbol}")
        regime_thresholds = asset_cfg.get("regime_thresholds") or {}

        for segment in symbol_segments:
            segment_length = len(segment)
            pure_side = segment[0].pure_trend_side
            pure_entry_price = segment[0].close
            pure_entry_timestamp = segment[0].timestamp
            pure_regime = segment[0].regime

            pure_tpsl = resolve_tpsl(asset_cfg, pure_regime)
            if pure_tpsl is None:
                raise ValueError(
                    f"Missing TP/SL config for {symbol} regime={pure_regime}")
            pure_sl_pct, pure_tp_pct = pure_tpsl
            pure_trade = simulate_exit(
                bars=segment,
                entry_index=0,
                side=pure_side,
                entry_price=pure_entry_price,
                sl_pct=pure_sl_pct,
                tp_pct=pure_tp_pct,
                timeout_bars=max_bars,
                regime_exit=True,
                regime_for_exit=pure_regime,
            )

            first_aurora_index: int | None = None
            aurora_trade: TradeSummary | None = None

            for index, row in enumerate(segment):
                factor = safe_float(regime_thresholds.get(row.regime))
                if factor is None:
                    factor = safe_float(regime_thresholds.get("DEFAULT"))
                if factor is None:
                    row.aurora_side = ""
                    row.aurora_signal_emitted = "FALSE"
                    row.aurora_reject_reason = "MISSING_REGIME_THRESHOLD"
                else:
                    known_gate = resolve_known_regime_gate(
                        row.regime,
                        row.regime_confidence,
                        directional_cfg,
                    )
                    if known_gate is not None:
                        row.aurora_side = ""
                        row.aurora_signal_emitted = "FALSE"
                        row.aurora_reject_reason = known_gate
                        counters["bars_with_proven_gate_reject"] += 1
                        ok = False
                    elif row.aurora_score is None:
                        row.aurora_side = ""
                        row.aurora_signal_emitted = "UNKNOWN"
                        row.aurora_reject_reason = "SCORE_SURFACE_UNAVAILABLE"
                        counters["bars_with_unknown_score_surface"] += 1
                        ok = False
                    else:
                        threshold = signal_threshold * factor
                        side = side_from_score(row.aurora_score, threshold)
                        ok, reason = apply_current_gates(
                            row.regime,
                            row.regime_confidence,
                            row.aurora_score,
                            side,
                            directional_cfg,
                            low_vol_cfg,
                        )
                        row.aurora_side = side
                        row.aurora_signal_emitted = "TRUE" if ok else "FALSE"
                        row.aurora_reject_reason = "" if ok else str(
                            reason or "REJECTED")

                    if ok and first_aurora_index is None:
                        first_aurora_index = index
                        tpsl = resolve_tpsl(asset_cfg, row.regime)
                        if tpsl is not None:
                            aurora_sl_pct, aurora_tp_pct = tpsl
                            aurora_trade = simulate_exit(
                                bars=segment,
                                entry_index=index,
                                side=side,
                                entry_price=row.close,
                                sl_pct=aurora_sl_pct,
                                tp_pct=aurora_tp_pct,
                                timeout_bars=max_bars,
                                regime_exit=False,
                                regime_for_exit=row.regime,
                            )

                row.segment_bar_index = index
                row.segment_length_bars = segment_length
                row.timeout_bars = max_bars
                row.pure_entry_timestamp = pure_entry_timestamp
                row.pure_entry_price = pure_entry_price
                row.pure_outcome = pure_trade.outcome
                row.pure_pnl_pct = pure_trade.pnl_pct
                row.pure_exit_reason = pure_trade.exit_reason
                row.pure_exit_timestamp = pure_trade.exit_timestamp
                row.mfe_bps_after_pure_entry = pure_trade.mfe_bps
                row.mae_bps_after_pure_entry = pure_trade.mae_bps
                if row.regime_match is False:
                    mismatch_count += 1

            if first_aurora_index is not None and aurora_trade is not None:
                entry_row = segment[first_aurora_index]
                entry_delay = first_aurora_index
                entry_price_delta_bps = (
                    (entry_row.close - pure_entry_price) / pure_entry_price) * 10000.0
                position_ratio = local_position(
                    first_aurora_index, segment_length)
                for row in segment:
                    row.aurora_entry_timestamp = entry_row.timestamp
                    row.aurora_entry_price = entry_row.close
                    row.entry_delay_bars = entry_delay
                    row.entry_price_delta_bps = float(entry_price_delta_bps)
                    row.local_position_in_range = float(position_ratio)
                    row.tp_distance_bps = aurora_trade.tp_distance_bps
                    row.sl_distance_bps = aurora_trade.sl_distance_bps
                    row.aurora_outcome = aurora_trade.outcome
                    row.aurora_pnl_pct = aurora_trade.pnl_pct
                    row.mfe_bps_after_aurora_entry = aurora_trade.mfe_bps
                    row.mae_bps_after_aurora_entry = aurora_trade.mae_bps
                    row.aurora_exit_timestamp = aurora_trade.exit_timestamp
                counters["segments_with_aurora_entry"] += 1
                if aurora_trade.side != pure_side:
                    counters["segments_with_side_mismatch"] += 1
                if entry_delay > 0:
                    counters["segments_with_delayed_entry"] += 1
            else:
                for row in segment:
                    row.aurora_outcome = "NO_ENTRY"
                    row.aurora_exit_timestamp = ""
                    row.aurora_reject_reason = row.aurora_reject_reason or "NO_ACCEPTED_BAR_IN_SEGMENT"
                counters["segments_without_aurora_entry"] += 1
                if any(row.aurora_reject_reason == "SCORE_SURFACE_UNAVAILABLE" for row in segment):
                    counters["segments_with_unknown_score_surface"] += 1

            segment_summaries.append(
                SegmentSummary(
                    symbol=symbol,
                    segment_start_ms=segment[0].timestamp_ms,
                    segment_end_ms=segment[-1].timestamp_ms,
                    segment_length_bars=segment_length,
                    regime=pure_regime,
                    pure_side=pure_side,
                    pure_trade=pure_trade,
                    aurora_trade=aurora_trade,
                    first_aurora_entry_index=first_aurora_index,
                )
            )

            counters[f"segments_{symbol}"] += 1
            counters[f"segments_{pure_regime}"] += 1

    localization = {
        "segment_count": len(segment_summaries),
        "regime_mismatch_row_count": mismatch_count,
        "segments_with_aurora_entry": counters["segments_with_aurora_entry"],
        "segments_without_aurora_entry": counters["segments_without_aurora_entry"],
        "segments_with_side_mismatch": counters["segments_with_side_mismatch"],
        "segments_with_delayed_entry": counters["segments_with_delayed_entry"],
        "segments_with_unknown_score_surface": counters["segments_with_unknown_score_surface"],
        "bars_with_proven_gate_reject": counters["bars_with_proven_gate_reject"],
        "bars_with_unknown_score_surface": counters["bars_with_unknown_score_surface"],
    }
    return joined_rows, segment_summaries, localization


def summarize_damage(segments: list[SegmentSummary]) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float))
    by_regime: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float))
    reasons: Counter[str] = Counter()

    for segment in segments:
        pure_trade = segment.pure_trade
        aurora_trade = segment.aurora_trade
        symbol_bucket = by_symbol[segment.symbol]
        regime_bucket = by_regime[segment.regime]
        symbol_bucket["pure_total_pnl_pct"] += pure_trade.pnl_pct
        regime_bucket["pure_total_pnl_pct"] += pure_trade.pnl_pct
        symbol_bucket["segment_count"] += 1
        regime_bucket["segment_count"] += 1
        if aurora_trade is None:
            reasons["NO_ENTRY"] += 1
            continue
        symbol_bucket["aurora_total_pnl_pct"] += aurora_trade.pnl_pct
        regime_bucket["aurora_total_pnl_pct"] += aurora_trade.pnl_pct
        reasons[aurora_trade.outcome] += 1
        if aurora_trade.side != segment.pure_side:
            reasons["SIDE_MISMATCH"] += 1
        if segment.first_aurora_entry_index and segment.first_aurora_entry_index > 0:
            reasons["DELAYED_ENTRY"] += 1

    return {
        "by_symbol": {key: dict(value) for key, value in sorted(by_symbol.items())},
        "by_regime": {key: dict(value) for key, value in sorted(by_regime.items())},
        "driver_counts": dict(sorted(reasons.items())),
    }


def write_joined_csv(path: Path, rows: list[JoinedBar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def build_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1")
    lines.append("")
    lines.append("## FACT")
    lines.append("")
    for item in payload["fact"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## INFERENCE")
    lines.append("")
    for item in payload["inference"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## ASSUMPTION")
    lines.append("")
    for item in payload["assumption"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## UNKNOWN")
    lines.append("")
    for item in payload["unknown"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Localization Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for key, value in payload["localization"].items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## Driver Counts")
    lines.append("")
    lines.append("| Driver | Count |")
    lines.append("| --- | --- |")
    for key, value in payload["damage_summary"]["driver_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## By Symbol")
    lines.append("")
    lines.append("| Symbol | Segments | Pure Total PnL% | Aurora Total PnL% |")
    lines.append("| --- | --- | --- | --- |")
    for symbol, metrics in payload["damage_summary"]["by_symbol"].items():
        lines.append(
            f"| {symbol} | {int(metrics.get('segment_count', 0))} | {metrics.get('pure_total_pnl_pct', 0.0):.6f} | {metrics.get('aurora_total_pnl_pct', 0.0):.6f} |"
        )
    lines.append("")
    lines.append("## By Regime")
    lines.append("")
    lines.append("| Regime | Segments | Pure Total PnL% | Aurora Total PnL% |")
    lines.append("| --- | --- | --- | --- |")
    for regime, metrics in payload["damage_summary"]["by_regime"].items():
        lines.append(
            f"| {regime} | {int(metrics.get('segment_count', 0))} | {metrics.get('pure_total_pnl_pct', 0.0):.6f} | {metrics.get('aurora_total_pnl_pct', 0.0):.6f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    symbols = {str(symbol).upper() for symbol in args.symbols}
    pure_rows = load_pure_dataset(Path(args.pure_dataset), symbols)
    start_day, end_day = resolve_overlap_window(
        pure_rows, args.window_start, args.window_end)
    pure_rows = [
        row
        for row in pure_rows
        if start_day <= datetime.fromtimestamp(row.timestamp_ms / 1000.0, tz=UTC).date() <= end_day
    ]
    recorder_rows = load_recorder_rows(symbols, start_day, end_day)
    signal_threshold, assets_cfg, directional_cfg, low_vol_cfg = load_cfg()

    joined_rows = build_joined_bars(pure_rows, recorder_rows)
    joined_rows, segments, localization = analyze_segments(
        joined_rows,
        signal_threshold,
        assets_cfg,
        directional_cfg,
        low_vol_cfg,
        args.max_bars,
    )
    damage_summary = summarize_damage(segments)

    output_prefix = args.output_prefix
    joined_csv = REPORTS_DIR / f"{output_prefix}_joined.csv"
    summary_json = REPORTS_DIR / f"{output_prefix}.json"
    report_md = REPORTS_DIR / f"{output_prefix}.md"

    write_joined_csv(joined_csv, joined_rows)

    fact = [
        f"Overlap window constrained to recorder coverage and pure dataset intersection: {start_day.isoformat()}..{end_day.isoformat()}.",
        f"Joined TREND bar rows: {len(joined_rows)} across symbols {sorted(symbols)}.",
        f"TREND segments analyzed: {len(segments)}.",
        f"Aurora accepted at least one bar in {localization['segments_with_aurora_entry']} segments and never entered in {localization['segments_without_aurora_entry']} segments.",
        f"Aurora side on accepted entry mismatched pure trend side in {localization['segments_with_side_mismatch']} segments.",
        f"Regime label mismatch between pure and recorder rows occurred on {localization['regime_mismatch_row_count']} joined TREND rows.",
        f"Retained recorder rows had no serialized Aurora score surface on {localization['bars_with_unknown_score_surface']} TREND bars; those bars remain UNKNOWN beyond any provable regime-confidence reject.",
    ]
    inference = [
        "If a segment has no Aurora accepted bar while pure trend still opens immediately, the loss localizes first to gate admission or side generation rather than TP/SL geometry.",
        "If Aurora enters later than the pure segment start and outcome degrades, the loss localizes to entry timing even when the eventual side matches.",
        "If Aurora side differs from the deterministic pure trend side on the first accepted bar, the loss localizes to side selection before exit policy is even considered.",
        "If pure exits by REGIME_CHANGE while Aurora remains exposed until TIMEOUT or SL, that is evidence of exit-life mismatch rather than missing entry alone.",
    ]
    assumption = [
        f"Aurora timeout is replayed with {args.max_bars} bars, matching the current TREND timeout forensic baseline rather than a live max_hold_sec contract for BTC/ETH.",
    ]
    unknown = [
        "This retained BTC/ETH recorder cohort does not serialize Aurora side score fields such as signal_score, decision_score, final_score, or feat_pillar_sum, so side-selection and late-entry localization remain UNKNOWN on bars that are not already rejected by regime-confidence gates.",
        "This forensic does not reconstruct position overlap suppression or execution-position state; it localizes trend edge loss at bar, segment, and replayed first-entry level only.",
    ]

    payload = {
        "task": "AURORA_TREND_FAILURE_LOCALIZATION_FORENSIC_V1",
        "generated_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "inputs": {
            "symbols": sorted(symbols),
            "pure_dataset": str(Path(args.pure_dataset)),
            "window_start": start_day.isoformat(),
            "window_end": end_day.isoformat(),
            "max_bars": args.max_bars,
            "signal_threshold": signal_threshold,
        },
        "artifacts": {
            "joined_csv": str(joined_csv),
            "summary_json": str(summary_json),
            "report_md": str(report_md),
        },
        "localization": localization,
        "damage_summary": damage_summary,
        "fact": fact,
        "inference": inference,
        "assumption": assumption,
        "unknown": unknown,
    }

    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_md.write_text(build_report(payload), encoding="utf-8")
    print(json.dumps(payload["artifacts"], indent=2))


if __name__ == "__main__":
    main()
