from __future__ import annotations
from vfoundation.core.protocol import Message
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.config_loader import ConfigLoader

import argparse
import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORTS_DIR = ROOT / "reports"
BINANCE_FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
INTERVAL = "5m"
TF_SEC = 300
KLINE_LIMIT = 1500
SUPPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
START_DATE = "2025-05-01"
END_DATE = "2026-05-04"


@dataclass
class Candle:
    symbol: str
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class DatasetRow:
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
class TradeRecord:
    symbol: str
    entry_timestamp: str
    exit_timestamp: str
    side: str
    entry_regime: str
    entry_regime_confidence: float
    entry_regime_age_bars: int
    entry_price: float
    exit_price: float
    exit_reason: str
    bars_held: int
    pnl_pct: float
    r_multiple: float
    sl_pct_used: float
    tp_pct_used: float


@dataclass
class ReportPaths:
    dataset_csv: Path
    trades_csv: Path
    summary_json: Path
    report_md: Path


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
        self.listeners: dict[str, list[Any]] = defaultdict(list)
        self.events: list[tuple[str, dict[str, Any], str]] = []

    def listen(self, event_name: str, handler: Any) -> None:
        self.listeners[event_name].append(handler)

    def emit(self, event_name: str, payload: dict[str, Any], why: str = "", data_ref: Any = None) -> None:
        self.events.append((event_name, dict(payload), str(why)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1",
    )
    parser.add_argument("--symbols", nargs="+",
                        default=list(SUPPORTED_SYMBOLS))
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--end-date", default=END_DATE)
    parser.add_argument(
        "--timeout-bars",
        type=int,
        default=None,
        help="Explicit timeout horizon in 5m bars. Required if asset max_hold_sec is null.",
    )
    parser.add_argument(
        "--output-prefix",
        default="BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_2026_05_04",
    )
    return parser.parse_args()


def parse_date_start_ms(date_text: str) -> int:
    dt = datetime.fromisoformat(date_text).replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def parse_date_end_ms(date_text: str) -> int:
    dt = datetime.fromisoformat(date_text).replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000) + ((24 * 60 * 60 * 1000) - 1)


def iso_utc_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


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


def fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list[Candle]:
    candles: list[Candle] = []
    next_start_ms = int(start_ms)

    while next_start_ms <= end_ms:
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": INTERVAL,
                "limit": KLINE_LIMIT,
                "startTime": next_start_ms,
                "endTime": end_ms,
            }
        )
        request = urllib.request.Request(
            f"{BINANCE_FAPI_KLINES_URL}?{query}",
            headers={"User-Agent": "Phenix-Forensics/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch Binance Futures klines for {symbol}: {exc}") from exc

        if not isinstance(payload, list):
            raise RuntimeError(
                f"Unexpected Binance Futures response for {symbol}: {payload!r}")
        if not payload:
            break

        batch: list[Candle] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                raise RuntimeError(
                    f"Malformed kline row for {symbol}: {row!r}")
            open_time_ms = int(row[0])
            close_time_ms = int(row[6])
            open_value = safe_float(row[1])
            high_value = safe_float(row[2])
            low_value = safe_float(row[3])
            close_value = safe_float(row[4])
            volume_value = safe_float(row[5])
            if None in (open_value, high_value, low_value, close_value, volume_value):
                raise RuntimeError(
                    f"Non-numeric kline row for {symbol}: {row!r}")
            batch.append(
                Candle(
                    symbol=symbol,
                    open_time_ms=open_time_ms,
                    close_time_ms=close_time_ms,
                    open=float(open_value),
                    high=float(high_value),
                    low=float(low_value),
                    close=float(close_value),
                    volume=float(volume_value),
                )
            )

        candles.extend(batch)
        last_open_ms = batch[-1].open_time_ms
        next_start_ms = last_open_ms + (TF_SEC * 1000)

        if len(batch) < KLINE_LIMIT:
            break

    deduped: dict[int, Candle] = {}
    for candle in candles:
        deduped[candle.open_time_ms] = candle
    ordered = [deduped[key] for key in sorted(
        deduped.keys()) if deduped[key].close_time_ms <= end_ms]
    if not ordered:
        raise RuntimeError(f"No Binance Futures candles returned for {symbol}")
    return ordered


def load_config() -> Any:
    loader = ConfigLoader(config_dir=ROOT / "config" / "aurora")
    return loader.load_config()


def resolve_timeout_bars(asset_cfg: Any, explicit_timeout_bars: int | None) -> tuple[int, str | None]:
    if explicit_timeout_bars is not None:
        if explicit_timeout_bars <= 0:
            raise ValueError("timeout-bars must be > 0 when provided")
        return int(explicit_timeout_bars), "explicit_cli_timeout_bars"

    exit_cfg = getattr(asset_cfg, "exit", None)
    max_hold_sec = getattr(exit_cfg, "max_hold_sec",
                           None) if exit_cfg is not None else None
    if max_hold_sec is None:
        raise ValueError(
            "Asset exit.max_hold_sec is null and --timeout-bars was not provided; fail-closed to avoid hidden constants."
        )
    timeout_bars = int(math.ceil(float(max_hold_sec) / float(TF_SEC)))
    if timeout_bars <= 0:
        raise ValueError("Derived timeout bars must be > 0")
    return timeout_bars, None


def resolve_tpsl_params(asset_cfg: Any, regime: str) -> tuple[float, float]:
    exit_cfg = getattr(asset_cfg, "exit", None)
    take_profit_cfg = getattr(asset_cfg, "take_profit", None)
    if exit_cfg is None or take_profit_cfg is None:
        raise ValueError("Missing exit or take_profit config")

    sl_pct_eff = safe_float(getattr(exit_cfg, "sl_pct", None))
    tp_rr_eff = safe_float(getattr(take_profit_cfg, "tp_low_ratio", None))
    if sl_pct_eff is None or tp_rr_eff is None:
        raise ValueError("Missing base sl_pct or tp_low_ratio config")

    regime_tpsl = getattr(exit_cfg, "regime_tpsl", None)
    regime_tpsl_enabled = bool(
        getattr(regime_tpsl, "enabled", False)) if regime_tpsl is not None else False
    regime_tpsl_mode = str(getattr(regime_tpsl, "mode", "")
                           ) if regime_tpsl is not None else ""

    if regime_tpsl_enabled and regime_tpsl_mode == "pct_mult":
        sl_mult_map = getattr(regime_tpsl, "sl_mult", {}) or {}
        tp_mult_map = getattr(regime_tpsl, "tp_mult", {}) or {}

        sl_mult = safe_float(sl_mult_map.get(regime))
        if sl_mult is None:
            sl_mult = safe_float(sl_mult_map.get("DEFAULT"))
        tp_mult = safe_float(tp_mult_map.get(regime))
        if tp_mult is None:
            tp_mult = safe_float(tp_mult_map.get("DEFAULT"))
        if sl_mult is None or tp_mult is None:
            raise ValueError(
                f"Missing regime_tpsl multiplier for regime={regime}")

        sl_pct_eff = sl_pct_eff * sl_mult
        tp_rr_eff = tp_rr_eff * tp_mult

        min_sl_pct = safe_float(getattr(regime_tpsl, "min_sl_pct", None))
        max_sl_pct = safe_float(getattr(regime_tpsl, "max_sl_pct", None))
        min_tp_rr = safe_float(getattr(regime_tpsl, "min_tp_rr", None))
        max_tp_rr = safe_float(getattr(regime_tpsl, "max_tp_rr", None))

        if min_sl_pct is not None:
            sl_pct_eff = max(min_sl_pct, sl_pct_eff)
        if max_sl_pct is not None:
            sl_pct_eff = min(max_sl_pct, sl_pct_eff)
        if min_tp_rr is not None:
            tp_rr_eff = max(min_tp_rr, tp_rr_eff)
        if max_tp_rr is not None:
            tp_rr_eff = min(max_tp_rr, tp_rr_eff)

    tp_pct_eff = sl_pct_eff * tp_rr_eff
    if sl_pct_eff <= 0 or tp_pct_eff <= 0:
        raise ValueError(
            f"Invalid resolved TP/SL parameters for regime={regime}")
    return float(sl_pct_eff), float(tp_pct_eff)


def build_detector(config: Any) -> tuple[RegimeDetector, CaptureFSM, ReplayClock]:
    fsm = CaptureFSM()
    clock = ReplayClock()
    detector = RegimeDetector(config=config, fsm=fsm, clock=clock)
    return detector, fsm, clock


def run_detector_for_symbol(detector: RegimeDetector, fsm: CaptureFSM, clock: ReplayClock, candles: list[Candle]) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    last_regime: str | None = None
    regime_age_bars = 0

    for candle in candles:
        clock.set_now_ms(candle.close_time_ms)
        baseline_event_count = len(fsm.events)
        message = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="offline_replay",
            dst="regime_detector",
            pld={
                "symbol": candle.symbol,
                "ts": candle.close_time_ms,
                "tf_sec": TF_SEC,
                "close_boundary_ts_ms": candle.close_time_ms + 1,
                "features": {
                    "price": candle.close,
                    "high": candle.high,
                    "low": candle.low,
                },
            },
        )
        detector.handle_event(message)
        if len(fsm.events) <= baseline_event_count:
            raise RuntimeError(
                f"RegimeDetector did not emit EVT:REGIME_DETECTED for {candle.symbol} {candle.close_time_ms}")

        event_name, payload, _why = fsm.events[-1]
        if event_name != "EVT:REGIME_DETECTED":
            raise RuntimeError(f"Unexpected emitted event {event_name!r}")

        regime = str(payload.get("regime") or "UNCERTAIN")
        confidence = safe_float(payload.get("confidence"))
        if confidence is None:
            raise RuntimeError(
                f"Missing regime confidence for {candle.symbol} {candle.close_time_ms}")

        if regime == last_regime:
            regime_age_bars += 1
        else:
            regime_age_bars = 1
            last_regime = regime

        rows.append(
            DatasetRow(
                timestamp=iso_utc_from_ms(candle.close_time_ms),
                symbol=candle.symbol,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                regime=regime,
                regime_confidence=float(confidence),
                regime_age_bars=regime_age_bars,
            )
        )

    return rows


def pnl_pct(side: str, entry_price: float, exit_price: float) -> float:
    if side == "LONG":
        return ((exit_price - entry_price) / entry_price) * 100.0
    return ((entry_price - exit_price) / entry_price) * 100.0


def exit_r_multiple(pnl_pct_value: float, sl_pct_used: float) -> float:
    if sl_pct_used <= 0:
        return 0.0
    return pnl_pct_value / (sl_pct_used * 100.0)


def evaluate_symbol_trades(dataset_rows: list[DatasetRow], asset_cfg: Any, timeout_bars: int) -> list[TradeRecord]:
    trades: list[TradeRecord] = []
    open_trade: dict[str, Any] | None = None

    for row in dataset_rows:
        if open_trade is None:
            if row.regime == "TREND_UP":
                sl_pct_used, tp_pct_used = resolve_tpsl_params(
                    asset_cfg, row.regime)
                open_trade = {
                    "side": "LONG",
                    "entry_regime": row.regime,
                    "entry_confidence": row.regime_confidence,
                    "entry_age": row.regime_age_bars,
                    "entry_price": row.close,
                    "entry_timestamp": row.timestamp,
                    "bars_held": 0,
                    "sl_pct_used": sl_pct_used,
                    "tp_pct_used": tp_pct_used,
                }
            elif row.regime == "TREND_DOWN":
                sl_pct_used, tp_pct_used = resolve_tpsl_params(
                    asset_cfg, row.regime)
                open_trade = {
                    "side": "SHORT",
                    "entry_regime": row.regime,
                    "entry_confidence": row.regime_confidence,
                    "entry_age": row.regime_age_bars,
                    "entry_price": row.close,
                    "entry_timestamp": row.timestamp,
                    "bars_held": 0,
                    "sl_pct_used": sl_pct_used,
                    "tp_pct_used": tp_pct_used,
                }
            continue

        open_trade["bars_held"] += 1
        side = str(open_trade["side"])
        entry_price = float(open_trade["entry_price"])
        sl_pct_used = float(open_trade["sl_pct_used"])
        tp_pct_used = float(open_trade["tp_pct_used"])

        if side == "LONG":
            sl_price = entry_price * (1.0 - sl_pct_used)
            tp_price = entry_price * (1.0 + tp_pct_used)
            sl_hit = row.low <= sl_price
            tp_hit = row.high >= tp_price
            regime_change = row.regime != "TREND_UP"
        else:
            sl_price = entry_price * (1.0 + sl_pct_used)
            tp_price = entry_price * (1.0 - tp_pct_used)
            sl_hit = row.high >= sl_price
            tp_hit = row.low <= tp_price
            regime_change = row.regime != "TREND_DOWN"

        if sl_hit and tp_hit:
            tp_hit = False

        exit_reason: str | None = None
        exit_price_value: float | None = None

        if sl_hit:
            exit_reason = "SL"
            exit_price_value = float(sl_price)
        elif tp_hit:
            exit_reason = "TP"
            exit_price_value = float(tp_price)
        elif int(open_trade["bars_held"]) >= timeout_bars:
            exit_reason = "TIMEOUT"
            exit_price_value = float(row.close)
        elif regime_change:
            exit_reason = "REGIME_CHANGE"
            exit_price_value = float(row.close)

        if exit_reason is None or exit_price_value is None:
            continue

        pnl_pct_value = pnl_pct(side, entry_price, exit_price_value)
        trades.append(
            TradeRecord(
                symbol=row.symbol,
                entry_timestamp=str(open_trade["entry_timestamp"]),
                exit_timestamp=row.timestamp,
                side=side,
                entry_regime=str(open_trade["entry_regime"]),
                entry_regime_confidence=float(open_trade["entry_confidence"]),
                entry_regime_age_bars=int(open_trade["entry_age"]),
                entry_price=entry_price,
                exit_price=float(exit_price_value),
                exit_reason=exit_reason,
                bars_held=int(open_trade["bars_held"]),
                pnl_pct=float(pnl_pct_value),
                r_multiple=float(exit_r_multiple(pnl_pct_value, sl_pct_used)),
                sl_pct_used=sl_pct_used,
                tp_pct_used=tp_pct_used,
            )
        )
        open_trade = None

    return trades


def compute_trade_metrics(trades: list[TradeRecord]) -> dict[str, Any]:
    if not trades:
        return {
            "trade_count": 0,
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "regime_change_count": 0,
            "win_rate": 0.0,
            "avg_pnl_pct": 0.0,
            "median_pnl_pct": 0.0,
            "avg_r_multiple": 0.0,
            "total_pnl_pct": 0.0,
            "avg_bars_held": 0.0,
        }

    pnls = [trade.pnl_pct for trade in trades]
    sorted_pnls = sorted(pnls)
    median_index = len(sorted_pnls) // 2
    if len(sorted_pnls) % 2 == 1:
        median_pnl = sorted_pnls[median_index]
    else:
        median_pnl = (sorted_pnls[median_index - 1] +
                      sorted_pnls[median_index]) / 2.0

    tp_count = sum(1 for trade in trades if trade.exit_reason == "TP")
    sl_count = sum(1 for trade in trades if trade.exit_reason == "SL")
    timeout_count = sum(
        1 for trade in trades if trade.exit_reason == "TIMEOUT")
    regime_change_count = sum(
        1 for trade in trades if trade.exit_reason == "REGIME_CHANGE")

    return {
        "trade_count": len(trades),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "regime_change_count": regime_change_count,
        "win_rate": tp_count / len(trades),
        "avg_pnl_pct": sum(pnls) / len(trades),
        "median_pnl_pct": median_pnl,
        "avg_r_multiple": sum(trade.r_multiple for trade in trades) / len(trades),
        "total_pnl_pct": sum(pnls),
        "avg_bars_held": sum(trade.bars_held for trade in trades) / len(trades),
    }


def summarize_by_key(trades: list[TradeRecord], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        grouped[str(getattr(trade, key))].append(trade)
    return {group_key: compute_trade_metrics(group_trades) for group_key, group_trades in sorted(grouped.items())}


def build_paths(output_prefix: str) -> ReportPaths:
    return ReportPaths(
        dataset_csv=REPORTS_DIR / f"{output_prefix}_dataset.csv",
        trades_csv=REPORTS_DIR / f"{output_prefix}_trades.csv",
        summary_json=REPORTS_DIR / f"{output_prefix}.json",
        report_md=REPORTS_DIR / f"{output_prefix}.md",
    )


def write_dataset_csv(path: Path, rows: list[DatasetRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "regime",
                "regime_confidence",
                "regime_age_bars",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_trades_csv(path: Path, trades: list[TradeRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "entry_timestamp",
                "exit_timestamp",
                "side",
                "entry_regime",
                "entry_regime_confidence",
                "entry_regime_age_bars",
                "entry_price",
                "exit_price",
                "exit_reason",
                "bars_held",
                "pnl_pct",
                "r_multiple",
                "sl_pct_used",
                "tp_pct_used",
            ],
        )
        writer.writeheader()
        for trade in trades:
            writer.writerow(asdict(trade))


def build_report_markdown(summary: dict[str, Any]) -> str:
    facts = summary["fact"]
    inferences = summary["inference"]
    assumptions = summary["assumption"]
    unknowns = summary["unknown"]
    overall = summary["trade_metrics"]["overall"]

    lines: list[str] = []
    lines.append("# BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(summary["executive_summary"])
    lines.append("")
    lines.append("## FACT")
    lines.append("")
    for item in facts:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## INFERENCE")
    lines.append("")
    for item in inferences:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## ASSUMPTION")
    lines.append("")
    for item in assumptions:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## UNKNOWN")
    lines.append("")
    for item in unknowns:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Overall Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for key in (
        "trade_count",
        "tp_count",
        "sl_count",
        "timeout_count",
        "regime_change_count",
        "win_rate",
        "avg_pnl_pct",
        "median_pnl_pct",
        "avg_r_multiple",
        "total_pnl_pct",
        "avg_bars_held",
    ):
        value = overall[key]
        if isinstance(value, float):
            lines.append(f"| {key} | {value:.6f} |")
        else:
            lines.append(f"| {key} | {value} |")
    lines.append("")
    lines.append("## By Symbol")
    lines.append("")
    lines.append(
        "| Symbol | Trades | Win Rate | Avg PnL% | Avg R | Total PnL% |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for symbol, metrics in summary["trade_metrics"]["by_symbol"].items():
        lines.append(
            f"| {symbol} | {metrics['trade_count']} | {metrics['win_rate']:.6f} | {metrics['avg_pnl_pct']:.6f} | {metrics['avg_r_multiple']:.6f} | {metrics['total_pnl_pct']:.6f} |"
        )
    lines.append("")
    lines.append("## By Entry Regime")
    lines.append("")
    lines.append(
        "| Regime | Trades | Win Rate | Avg PnL% | Avg R | Total PnL% |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for regime, metrics in summary["trade_metrics"]["by_entry_regime"].items():
        lines.append(
            f"| {regime} | {metrics['trade_count']} | {metrics['win_rate']:.6f} | {metrics['avg_pnl_pct']:.6f} | {metrics['avg_r_multiple']:.6f} | {metrics['total_pnl_pct']:.6f} |"
        )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append(f"- Dataset CSV: {summary['artifacts']['dataset_csv']}")
    lines.append(f"- Trades CSV: {summary['artifacts']['trades_csv']}")
    lines.append(f"- Summary JSON: {summary['artifacts']['summary_json']}")
    lines.append("")
    lines.append("## Minimal Safe Verdict")
    lines.append("")
    lines.append(summary["minimal_safe_verdict"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    symbols = [str(symbol).upper() for symbol in args.symbols]
    unsupported = [
        symbol for symbol in symbols if symbol not in SUPPORTED_SYMBOLS]
    if unsupported:
        raise ValueError(
            f"Unsupported symbols: {unsupported}. Supported: {SUPPORTED_SYMBOLS}")

    start_ms = parse_date_start_ms(args.start_date)
    end_ms = parse_date_end_ms(args.end_date)
    if end_ms < start_ms:
        raise ValueError("end-date must be >= start-date")

    config = load_config()
    artifacts = build_paths(args.output_prefix)

    all_dataset_rows: list[DatasetRow] = []
    all_trade_records: list[TradeRecord] = []
    per_symbol_dataset: dict[str, list[DatasetRow]] = {}

    explicit_timeout_source = None
    if args.timeout_bars is not None:
        explicit_timeout_source = f"explicit_cli_timeout_bars={args.timeout_bars}"

    for symbol in symbols:
        candles = fetch_klines(symbol=symbol, start_ms=start_ms, end_ms=end_ms)
        detector, fsm, clock = build_detector(config=config)
        dataset_rows = run_detector_for_symbol(
            detector=detector, fsm=fsm, clock=clock, candles=candles)
        per_symbol_dataset[symbol] = dataset_rows
        all_dataset_rows.extend(dataset_rows)

        asset_cfg = config.strategies.aurora.assets.get(symbol)
        if asset_cfg is None:
            raise ValueError(f"Missing aurora asset config for {symbol}")
        timeout_bars, timeout_source = resolve_timeout_bars(
            asset_cfg=asset_cfg, explicit_timeout_bars=args.timeout_bars)
        if timeout_source is not None:
            explicit_timeout_source = timeout_source
        symbol_trades = evaluate_symbol_trades(
            dataset_rows=dataset_rows, asset_cfg=asset_cfg, timeout_bars=timeout_bars)
        all_trade_records.extend(symbol_trades)

    all_dataset_rows.sort(key=lambda row: (row.symbol, row.timestamp))
    all_trade_records.sort(key=lambda trade: (
        trade.symbol, trade.entry_timestamp, trade.exit_timestamp))

    write_dataset_csv(artifacts.dataset_csv, all_dataset_rows)
    write_trades_csv(artifacts.trades_csv, all_trade_records)

    by_symbol_metrics = summarize_by_key(all_trade_records, "symbol")
    by_entry_regime_metrics = summarize_by_key(
        all_trade_records, "entry_regime")

    overall_metrics = compute_trade_metrics(all_trade_records)
    regime_distribution = Counter(row.regime for row in all_dataset_rows)
    source_model_note = (
        "Exact production RegimeDetector class used offline. Deviation is only offline event wiring, mocked bar-time clock, and direct Binance Futures klines instead of live FEATURES_CALCULATED bus ingress."
    )

    summary = {
        "task": "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1",
        "generated_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "inputs": {
            "symbols": symbols,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "market_type": "Binance Futures USDM perpetual",
            "interval": INTERVAL,
            "timeout_bars": args.timeout_bars,
            "timeout_source": explicit_timeout_source,
        },
        "dataset": {
            "row_count": len(all_dataset_rows),
            "row_count_by_symbol": {symbol: len(rows) for symbol, rows in per_symbol_dataset.items()},
            "regime_distribution": dict(sorted(regime_distribution.items())),
        },
        "trade_metrics": {
            "overall": overall_metrics,
            "by_symbol": by_symbol_metrics,
            "by_entry_regime": by_entry_regime_metrics,
        },
        "artifacts": {
            "dataset_csv": str(artifacts.dataset_csv.relative_to(ROOT)),
            "trades_csv": str(artifacts.trades_csv.relative_to(ROOT)),
            "summary_json": str(artifacts.summary_json.relative_to(ROOT)),
            "report_md": str(artifacts.report_md.relative_to(ROOT)),
        },
        "executive_summary": (
            f"Offline replay used Binance Futures 5m candles from {args.start_date}..{args.end_date} for {', '.join(symbols)} and the production RegimeDetector path. "
            f"Pure TREND state-machine replay produced {overall_metrics['trade_count']} trades with win_rate={overall_metrics['win_rate']:.6f}, "
            f"avg_pnl_pct={overall_metrics['avg_pnl_pct']:.6f}, avg_r_multiple={overall_metrics['avg_r_multiple']:.6f}, total_pnl_pct={overall_metrics['total_pnl_pct']:.6f}."
        ),
        "fact": [
            f"Market type used is Binance Futures USDM perpetual because Aurora runtime adapter is Binance Futures and BTC/ETH instrument configs are futures-isolated leverage configs.",
            f"Dataset row count is {len(all_dataset_rows)} across symbols {symbols} at 5m cadence.",
            f"Dataset schema contains exactly the required columns: timestamp, symbol, open, high, low, close, volume, regime, regime_confidence, regime_age_bars.",
            f"Exact production RegimeDetector class was used offline for regime labeling and confidence; no Aurora score side-selection logic was used.",
            f"Pure regime replay entry logic was stateful and deterministic: flat -> LONG on TREND_UP, flat -> SHORT on TREND_DOWN; exits only by TP, SL, timeout, or regime change.",
            f"TP/SL geometry came from config/aurora/strategies/aurora.yaml BTC/ETH asset configs with regime_tpsl multipliers and clamps applied exactly as configured.",
            source_model_note,
        ],
        "inference": [
            f"Standalone trend-regime edge is positive only if the reported win_rate, avg_r_multiple, and total_pnl_pct remain operationally acceptable after removing Aurora side-selection and score gating; the artifact values above are the relevant evidence.",
            f"Differences between TREND_UP and TREND_DOWN cohorts should be interpreted as regime-direction asymmetry, not Aurora scoring effects, because side is hard-mapped from regime label only.",
            f"If timeout exits dominate versus TP exits, the regime detector may identify directional persistence more weakly than TP geometry requires under current BTC/ETH exit settings.",
        ],
        "assumption": [
            f"Timeout horizon used in replay is explicit and not from strategy YAML because BTC/ETH exit.max_hold_sec is null; replay ran with {explicit_timeout_source or 'no explicit timeout source recorded'}.",
            "Intra-bar ambiguity where both TP and SL are touched is resolved SL-first to stay fail-closed.",
            "Regime-change exit occurs at bar close after TP/SL checks because regime labels are bar-close detector outputs.",
        ],
        "unknown": [
            "Live slippage, queue priority, and fill latency are not modeled by this historical bar replay.",
            "Production feature-engineering path includes broader FEATURES_CALCULATED payloads; this replay intentionally supplies only price/high/low so detector fallback SMA/ATR math is exercised offline.",
            "The task does not specify a canonical timeout horizon in SSOT for BTC/ETH; any chosen timeout remains an explicit replay assumption until governance defines one.",
        ],
        "minimal_safe_verdict": (
            "This replay is valid historical evidence for standalone TREND regime edge on BTCUSDT and ETHUSDT under Binance Futures 5m candles, but any runtime decision still depends on explicit timeout-governance because BTC/ETH max_hold_sec is null in current SSOT."
        ),
    }

    artifacts.summary_json.write_text(json.dumps(
        summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts.report_md.write_text(
        build_report_markdown(summary), encoding="utf-8")

    print(
        json.dumps(
            {
                "dataset_csv": str(artifacts.dataset_csv.relative_to(ROOT)),
                "trades_csv": str(artifacts.trades_csv.relative_to(ROOT)),
                "summary_json": str(artifacts.summary_json.relative_to(ROOT)),
                "report_md": str(artifacts.report_md.relative_to(ROOT)),
                "overall_trade_metrics": overall_metrics,
                "row_count_by_symbol": {symbol: len(rows) for symbol, rows in per_symbol_dataset.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
