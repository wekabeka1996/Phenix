from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.parquet as pq


BACKTEST_PATH = Path("reports/backtests/backtest_20260312_010242.json")
ORDER_LOG_PATH = Path("logs/backtests/order_log_20260312_010242.jsonl")
BAR_GLOB = "data/processed/ETHUSDT/5m/2024-0[1-3]_enriched.parquet"
REPORT_PATH = Path("reports/eth_trend_down_counterfactual.md")
SUMMARY_PATH = Path("reports/eth_trend_down_counterfactual_summary.json")


@dataclass(frozen=True)
class TradeRecord:
    rid: str
    side: str
    close_reason: str
    pnl_usdt_net: float
    pnl_pct_net: float
    entry_ts_ms: int
    exit_ts_ms: int
    entry_price: float
    exit_price: float
    entry_qty: float
    exit_month: str
    entry_hour_utc: int
    entry_day_utc: str
    market_regime: str
    intent_seen: bool
    current_open: float
    current_high: float
    current_low: float
    current_close: float
    prev_close: float | None
    bar_range_pct: float
    bar_body_pct: float
    delta_prev_close_pct: float | None
    hold_minutes: float

    @property
    def is_red_bar(self) -> bool:
        return self.current_close < self.current_open

    @property
    def is_green_bar(self) -> bool:
        return self.current_close > self.current_open


@dataclass(frozen=True)
class FilterDefinition:
    code: str
    title: str
    description: str
    predicate: Callable[[TradeRecord], bool]


@dataclass(frozen=True)
class CohortStats:
    filter_code: str
    filter_title: str
    cohort: str
    baseline_n: int
    n: int
    kept_share: float
    total_pnl: float
    ev_per_trade: float
    win_rate: float
    avg_win: float
    avg_loss: float
    payoff: float | None
    largest_loss: float
    sl_count: int
    tp_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline counterfactual filters for ETHUSDT x TREND_DOWN LONG trades"
    )
    parser.add_argument("--backtest", type=Path, default=BACKTEST_PATH)
    parser.add_argument("--order-log", type=Path, default=ORDER_LOG_PATH)
    parser.add_argument("--bar-glob", default=BAR_GLOB)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--summary-json", type=Path, default=SUMMARY_PATH)
    return parser.parse_args()


def walk_trade_nodes(node: object, bucket: list[dict]) -> None:
    if isinstance(node, dict):
        if (
            node.get("symbol") == "ETHUSDT"
            and node.get("market_regime") == "TREND_DOWN"
            and node.get("side") == "LONG"
            and isinstance(node.get("entry"), dict)
            and isinstance(node.get("exit"), dict)
            and "pnl_usdt_net" in node
        ):
            bucket.append(node)
        for value in node.values():
            walk_trade_nodes(value, bucket)
        return
    if isinstance(node, list):
        for item in node:
            walk_trade_nodes(item, bucket)


def load_long_trend_down_trades(backtest_path: Path) -> list[dict]:
    payload = json.loads(backtest_path.read_text(encoding="utf-8"))
    raw: list[dict] = []
    walk_trade_nodes(payload, raw)

    deduped: list[dict] = []
    seen: set[tuple[object, ...]] = set()
    for trade in raw:
        key = (
            trade.get("rid"),
            trade["entry"].get("ts_ms"),
            trade["exit"].get("ts_ms"),
            trade.get("pnl_usdt_net"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(trade)
    return sorted(deduped, key=lambda item: item["exit"]["ts_ms"])


def load_intent_rids(order_log_path: Path) -> set[str]:
    intent_rids: set[str] = set()
    if not order_log_path.exists():
        return intent_rids
    for raw_line in order_log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        record = json.loads(line)
        if (
            record.get("event_type") == "ORDER_INTENT"
            and record.get("source_fsm") == "DecisionMaking"
            and record.get("symbol") == "ETHUSDT"
        ):
            rid = record.get("rid")
            if isinstance(rid, str):
                intent_rids.add(rid)
    return intent_rids


def load_bars(bar_glob: str) -> tuple[dict[int, tuple[float, float, float, float]], dict[int, float]]:
    paths = sorted(Path().glob(bar_glob))
    if not paths:
        raise FileNotFoundError(f"No parquet files matched {bar_glob}")

    tables = [
        pq.read_table(path, columns=["open_time", "open", "high", "low", "close"])
        for path in paths
    ]
    merged = pa.concat_tables(tables).to_pylist()

    rows: list[tuple[int, float, float, float, float]] = []
    for row in merged:
        open_time = row["open_time"].replace(tzinfo=UTC)
        ts_ms = int(open_time.timestamp() * 1000)
        rows.append(
            (
                ts_ms,
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
        )
    rows.sort(key=lambda item: item[0])

    bars = {row[0]: row[1:] for row in rows}
    prev_closes = {rows[index][0]: rows[index - 1][4] for index in range(1, len(rows))}
    return bars, prev_closes


def floor_to_5m(ts_ms: int) -> int:
    return (ts_ms // 300_000) * 300_000


def build_trade_records(
    trades: list[dict], intent_rids: set[str], bars: dict[int, tuple[float, float, float, float]], prev_closes: dict[int, float]
) -> list[TradeRecord]:
    records: list[TradeRecord] = []
    for trade in trades:
        entry_ts_ms = int(trade["entry"]["ts_ms"])
        exit_ts_ms = int(trade["exit"]["ts_ms"])
        bar_ts = floor_to_5m(entry_ts_ms)
        if bar_ts not in bars:
            continue

        current_open, current_high, current_low, current_close = bars[bar_ts]
        prev_close = prev_closes.get(bar_ts)
        bar_range_pct = ((current_high - current_low) / current_open) * 100.0 if current_open else 0.0
        bar_body_pct = ((current_close - current_open) / current_open) * 100.0 if current_open else 0.0
        delta_prev_close_pct = None
        if prev_close:
            delta_prev_close_pct = ((current_close - prev_close) / prev_close) * 100.0

        exit_dt = datetime.fromtimestamp(exit_ts_ms / 1000, tz=UTC)
        entry_dt = datetime.fromtimestamp(entry_ts_ms / 1000, tz=UTC)
        records.append(
            TradeRecord(
                rid=str(trade.get("rid") or ""),
                side=str(trade.get("side") or ""),
                close_reason=str(trade.get("close_reason") or ""),
                pnl_usdt_net=float(trade.get("pnl_usdt_net") or 0.0),
                pnl_pct_net=float(trade.get("pnl_pct_net") or 0.0),
                entry_ts_ms=entry_ts_ms,
                exit_ts_ms=exit_ts_ms,
                entry_price=float(trade["entry"].get("price") or 0.0),
                exit_price=float(trade["exit"].get("price") or 0.0),
                entry_qty=float(trade["entry"].get("qty") or 0.0),
                exit_month=exit_dt.strftime("%Y-%m"),
                entry_hour_utc=entry_dt.hour,
                entry_day_utc=entry_dt.strftime("%a"),
                market_regime=str(trade.get("market_regime") or ""),
                intent_seen=str(trade.get("rid") or "") in intent_rids,
                current_open=current_open,
                current_high=current_high,
                current_low=current_low,
                current_close=current_close,
                prev_close=prev_close,
                bar_range_pct=bar_range_pct,
                bar_body_pct=bar_body_pct,
                delta_prev_close_pct=delta_prev_close_pct,
                hold_minutes=(exit_ts_ms - entry_ts_ms) / 60_000.0,
            )
        )
    return records


def build_filters() -> list[FilterDefinition]:
    return [
        FilterDefinition("F0", "baseline", "All ETHUSDT x TREND_DOWN LONG trades", lambda trade: True),
        FilterDefinition("F1", "only-after-red-bar", "Keep LONG only if current 5m bar is red", lambda trade: trade.is_red_bar),
        FilterDefinition("F2", "reject-green-entry-bar", "Reject LONG if current 5m bar is green", lambda trade: not trade.is_green_bar),
        FilterDefinition(
            "F3",
            "require-negative-delta-vs-prev-close",
            "Keep LONG only if current 5m close is below previous 5m close",
            lambda trade: trade.delta_prev_close_pct is not None and trade.delta_prev_close_pct < 0.0,
        ),
        FilterDefinition(
            "F4",
            "reject-positive-delta-vs-prev-close",
            "Reject LONG if current 5m close is above previous 5m close",
            lambda trade: trade.delta_prev_close_pct is not None and trade.delta_prev_close_pct <= 0.0,
        ),
        FilterDefinition(
            "F5",
            "combined-conservative-dip-filter",
            "Keep LONG only if current bar is red and close is below previous close",
            lambda trade: trade.is_red_bar and trade.delta_prev_close_pct is not None and trade.delta_prev_close_pct < 0.0,
        ),
        FilterDefinition(
            "F6",
            "anti-exhaustion-green-bounce",
            "Reject green micro-bounce LONGs where 5m delta vs previous close exceeds +0.15%",
            lambda trade: not (
                trade.is_green_bar
                and trade.delta_prev_close_pct is not None
                and trade.delta_prev_close_pct > 0.15
            ),
        ),
    ]


def cohort_name(trade: TradeRecord) -> str | None:
    if trade.exit_month in {"2024-01", "2024-02"}:
        return "Jan+Feb"
    if trade.exit_month == "2024-03":
        return "March"
    return None


def compute_stats(filter_def: FilterDefinition, cohort: str, baseline_trades: list[TradeRecord], kept: list[TradeRecord]) -> CohortStats:
    wins = [trade.pnl_usdt_net for trade in kept if trade.pnl_usdt_net > 0]
    losses = [trade.pnl_usdt_net for trade in kept if trade.pnl_usdt_net <= 0]
    total_pnl = sum(trade.pnl_usdt_net for trade in kept)
    win_rate = (len(wins) / len(kept)) if kept else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    payoff = None
    if avg_win > 0 and avg_loss < 0:
        payoff = avg_win / abs(avg_loss)

    return CohortStats(
        filter_code=filter_def.code,
        filter_title=filter_def.title,
        cohort=cohort,
        baseline_n=len(baseline_trades),
        n=len(kept),
        kept_share=(len(kept) / len(baseline_trades)) if baseline_trades else 0.0,
        total_pnl=total_pnl,
        ev_per_trade=(total_pnl / len(kept)) if kept else 0.0,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff=payoff,
        largest_loss=min((trade.pnl_usdt_net for trade in kept), default=0.0),
        sl_count=sum(trade.close_reason == "SL" for trade in kept),
        tp_count=sum(trade.close_reason == "TP" for trade in kept),
    )


def build_results(records: list[TradeRecord], filters: list[FilterDefinition]) -> tuple[list[CohortStats], dict[str, dict[str, float]]]:
    jan_feb = [trade for trade in records if cohort_name(trade) == "Jan+Feb"]
    march = [trade for trade in records if cohort_name(trade) == "March"]
    q1 = list(records)
    cohorts = {"Jan+Feb": jan_feb, "March": march, "Q1": q1}

    baseline_jan_feb_wins = [trade for trade in jan_feb if trade.pnl_usdt_net > 0]
    baseline_positive_pnl = sum(trade.pnl_usdt_net for trade in baseline_jan_feb_wins)
    baseline_positive_count = len(baseline_jan_feb_wins)

    stats_rows: list[CohortStats] = []
    ranking: dict[str, dict[str, float]] = {}

    baseline_march_pnl = None
    for filter_def in filters:
        filtered_per_cohort: dict[str, list[TradeRecord]] = {}
        for cohort_label, baseline_trades in cohorts.items():
            kept = [trade for trade in baseline_trades if filter_def.predicate(trade)]
            filtered_per_cohort[cohort_label] = kept
            stats_rows.append(compute_stats(filter_def, cohort_label, baseline_trades, kept))

        kept_jan_feb = filtered_per_cohort["Jan+Feb"]
        kept_positive_pnl = sum(trade.pnl_usdt_net for trade in kept_jan_feb if trade.pnl_usdt_net > 0)
        kept_positive_count = sum(trade.pnl_usdt_net > 0 for trade in kept_jan_feb)
        march_total_pnl = sum(trade.pnl_usdt_net for trade in filtered_per_cohort["March"])
        if filter_def.code == "F0":
            baseline_march_pnl = march_total_pnl

        ranking[filter_def.code] = {
            "march_total_pnl": march_total_pnl,
            "march_improvement_vs_f0": 0.0,
            "janfeb_positive_pnl_retained_share": (kept_positive_pnl / baseline_positive_pnl) if baseline_positive_pnl else 0.0,
            "janfeb_positive_trade_retained_share": (kept_positive_count / baseline_positive_count) if baseline_positive_count else 0.0,
            "q1_total_pnl": sum(trade.pnl_usdt_net for trade in filtered_per_cohort["Q1"]),
        }

    if baseline_march_pnl is None:
        raise RuntimeError("Missing F0 baseline for ranking")

    for metrics in ranking.values():
        metrics["march_improvement_vs_f0"] = metrics["march_total_pnl"] - baseline_march_pnl
    return stats_rows, ranking


def format_pct(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "n/a"
    return f"{value * 100:.2f}%"


def format_num(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "n/a"
    return f"{value:.2f}"


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    separator = ["---"] * len(headers)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(separator) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def build_report(
    records: list[TradeRecord],
    filters: list[FilterDefinition],
    stats_rows: list[CohortStats],
    ranking: dict[str, dict[str, float]],
    report_path: Path,
    summary_path: Path,
) -> str:
    filter_map = {item.code: item for item in filters}
    grouped: dict[str, dict[str, CohortStats]] = {}
    for row in stats_rows:
        grouped.setdefault(row.filter_code, {})[row.cohort] = row

    baseline = grouped["F0"]
    by_march = sorted(ranking.items(), key=lambda item: item[1]["march_improvement_vs_f0"], reverse=True)
    by_retention = sorted(
        ranking.items(),
        key=lambda item: (
            item[1]["janfeb_positive_pnl_retained_share"],
            item[1]["march_improvement_vs_f0"],
        ),
        reverse=True,
    )

    best_march_code, best_march_metrics = by_march[0]
    best_retention_code, best_retention_metrics = by_retention[0]

    viable_filters = [
        (code, metrics)
        for code, metrics in ranking.items()
        if code != "F0" and metrics["march_improvement_vs_f0"] > 0.0
    ]
    balanced_candidate = None
    if viable_filters:
        balanced_candidate = max(
            viable_filters,
            key=lambda item: (
                item[1]["janfeb_positive_pnl_retained_share"],
                item[1]["march_improvement_vs_f0"],
            ),
        )

    baseline_rows = []
    for cohort in ["Jan+Feb", "March", "Q1"]:
        row = baseline[cohort]
        baseline_rows.append(
            [
                cohort,
                str(row.n),
                format_num(row.total_pnl),
                format_num(row.ev_per_trade),
                format_pct(row.win_rate),
                format_num(row.avg_win),
                format_num(row.avg_loss),
                format_num(row.payoff),
                str(row.sl_count),
                str(row.tp_count),
                format_num(row.largest_loss),
            ]
        )

    cf_rows: list[list[str]] = []
    for filter_code in [item.code for item in filters]:
        for cohort in ["Jan+Feb", "March", "Q1"]:
            row = grouped[filter_code][cohort]
            cf_rows.append(
                [
                    filter_code,
                    cohort,
                    str(row.n),
                    format_pct(row.kept_share),
                    format_num(row.total_pnl),
                    format_num(row.ev_per_trade),
                    format_pct(row.win_rate),
                    format_num(row.avg_win),
                    format_num(row.avg_loss),
                    format_num(row.payoff),
                    format_num(row.largest_loss),
                    str(row.sl_count),
                    str(row.tp_count),
                ]
            )

    rank_rows = []
    for filter_code, metrics in by_march:
        rank_rows.append(
            [
                filter_code,
                filter_map[filter_code].title,
                format_num(metrics["march_improvement_vs_f0"]),
                format_pct(metrics["janfeb_positive_pnl_retained_share"]),
                format_pct(metrics["janfeb_positive_trade_retained_share"]),
                format_num(metrics["q1_total_pnl"]),
            ]
        )

    intent_seen = sum(trade.intent_seen for trade in records)
    verdict_lines = []
    if balanced_candidate is None:
        verdict_lines.append(
            "No simple entry-phase filter improved March relative to F0, which points away from a clean patched7 phase-filter solution."
        )
    else:
        code, metrics = balanced_candidate
        verdict_lines.append(
            f"Best balanced candidate: {code} ({filter_map[code].title}) with March improvement {format_num(metrics['march_improvement_vs_f0'])} USDT and Jan+Feb winner pnl retention {format_pct(metrics['janfeb_positive_pnl_retained_share'])}."
        )
        if metrics["janfeb_positive_pnl_retained_share"] >= 0.75:
            verdict_lines.append(
                "Entry-phase filtering still looks viable enough to test before a full TP/SL or regime redesign."
            )
        else:
            verdict_lines.append(
                "The best March-reducing filter still destroys too much Jan+Feb winner value, so patched7 likely needs more than a pure phase gate."
            )

    report = "\n".join(
        [
            "# ETHUSDT TREND_DOWN Counterfactual Research",
            "*Scope: offline filters on existing ETHUSDT x TREND_DOWN LONG trades and 5m processed bars*",
            "*Source run: 20260312_010242*",
            "",
            "---",
            "",
            "## 1. Executive Verdict",
            "",
            *[f"- {line}" for line in verdict_lines],
            f"- Best raw March improvement: {best_march_code} ({filter_map[best_march_code].title}) at {format_num(best_march_metrics['march_improvement_vs_f0'])} USDT vs F0.",
            f"- Best Jan+Feb winner retention: {best_retention_code} ({filter_map[best_retention_code].title}) at {format_pct(best_retention_metrics['janfeb_positive_pnl_retained_share'])} retained positive pnl.",
            f"- Intent linkage coverage from order log: {intent_seen}/{len(records)} LONG trades.",
            "",
            "---",
            "",
            "## 2. Baseline ETH TREND_DOWN LONG Stats",
            "",
            render_table(
                [
                    "cohort",
                    "n",
                    "total_pnl",
                    "EV/trade",
                    "WR",
                    "avg_win",
                    "avg_loss",
                    "payoff",
                    "SL count",
                    "TP count",
                    "largest_loss",
                ],
                baseline_rows,
            ),
            "",
            "---",
            "",
            "## 3. Counterfactual Filters F0..F6",
            "",
            render_table(
                [
                    "filter",
                    "cohort",
                    "n",
                    "kept_share",
                    "total_pnl",
                    "EV/trade",
                    "WR",
                    "avg_win",
                    "avg_loss",
                    "payoff",
                    "largest_loss",
                    "SL count",
                    "TP count",
                ],
                cf_rows,
            ),
            "",
            "---",
            "",
            "## 4. Best Filter Candidates",
            "",
            render_table(
                [
                    "filter",
                    "title",
                    "March improvement vs F0",
                    "Jan+Feb winner pnl retained",
                    "Jan+Feb winner trade retained",
                    "Q1 total_pnl",
                ],
                rank_rows,
            ),
            "",
            "---",
            "",
            "## 5. Candidate Reading",
            "",
            f"- Best March cutter: {best_march_code} ({filter_map[best_march_code].description}).",
            f"- Least harmful to Jan+Feb winners: {best_retention_code} ({filter_map[best_retention_code].description}).",
            (
                f"- Best balanced candidate: {balanced_candidate[0]} ({filter_map[balanced_candidate[0]].description})."
                if balanced_candidate is not None
                else "- No balanced candidate cleared the positive-March-improvement gate."
            ),
            "",
            "---",
            "",
            "## 6. Is A Simple Entry-Phase Filter Enough?",
            "",
            (
                "A simple entry-phase filter looks promising enough for patched7 research if the balanced candidate preserves most Jan+Feb winner pnl while materially improving March."
                if balanced_candidate is not None and balanced_candidate[1]["janfeb_positive_pnl_retained_share"] >= 0.75
                else "A simple entry-phase filter alone does not look sufficient; TP/SL or regime redesign should remain active options."
            ),
            "",
            f"Summary JSON written alongside this report: {summary_path.as_posix()}",
            "",
        ]
    )
    report_path.write_text(report + "\n", encoding="utf-8")
    return report


def write_summary_json(
    records: list[TradeRecord], stats_rows: list[CohortStats], ranking: dict[str, dict[str, float]], summary_path: Path
) -> None:
    payload = {
        "meta": {
            "run_id": "20260312_010242",
            "trade_count": len(records),
        },
        "stats": [asdict(row) for row in stats_rows],
        "ranking": ranking,
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    trades = load_long_trend_down_trades(args.backtest)
    intent_rids = load_intent_rids(args.order_log)
    bars, prev_closes = load_bars(args.bar_glob)
    records = build_trade_records(trades, intent_rids, bars, prev_closes)
    filters = build_filters()
    stats_rows, ranking = build_results(records, filters)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    build_report(records, filters, stats_rows, ranking, args.report, args.summary_json)
    write_summary_json(records, stats_rows, ranking, args.summary_json)


if __name__ == "__main__":
    main()