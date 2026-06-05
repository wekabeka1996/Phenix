#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (  # noqa: E402
    JudgeShadowCalibrationRowV1,
)


SCHEMA_VERSION = "1.0.0"
CALCULATION_BASIS = "diagnostic_counterfactual_not_realized_pnl"

CandidateSide = Literal["BUY", "SELL", "NONE", "UNKNOWN"]
CoverageStatus = Literal["COMPLETE", "PARTIAL", "MISSING"]
CounterfactualLabel = Literal[
    "MISSED_OPPORTUNITY_LONG",
    "MISSED_OPPORTUNITY_SHORT",
    "AVOIDED_LOSS_LONG",
    "AVOIDED_LOSS_SHORT",
    "NEUTRAL_NO_OPPORTUNITY",
    "INSUFFICIENT_FORWARD_DATA",
    "SIDE_UNKNOWN",
    "MARKET_DATA_MISSING",
    "NOT_COUNTERFACTUAL_ELIGIBLE",
]


class MarketDataBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    first_bar_ts_ms: int | None = None
    last_bar_ts_ms: int | None = None
    bars_used: int = Field(ge=0)
    coverage_status: CoverageStatus


class CounterfactualBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: CounterfactualLabel
    reference_price: float | None = None
    reference_price_source: str | None = None
    max_favorable_usd: float | None = None
    max_adverse_usd: float | None = None
    terminal_return_usd: float | None = None
    max_favorable_bps: float | None = None
    max_adverse_bps: float | None = None
    terminal_return_bps: float | None = None
    estimated_fee_usd: float | None = None
    estimated_slippage_usd: float | None = None
    net_opportunity_usd: float | None = None
    net_opportunity_bps: float | None = None
    calculation_basis: Literal["diagnostic_counterfactual_not_realized_pnl"] = CALCULATION_BASIS


class CounterfactualSourceRefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rid: str | None = None
    decision_id: str | None = None
    lifecycle_id: str | None = None
    order_id: str | None = None


class JudgeCounterfactualOpportunityLabelV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    label_id: str
    source_shadow_row_id: str
    created_ts_ms: int = Field(ge=0)
    decision_ts_ms: int = Field(ge=0)
    symbol: str
    candidate_side: CandidateSide
    judge_verdict: str
    judge_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    horizon_sec: int = Field(gt=0)
    market_data: MarketDataBlock
    counterfactual: CounterfactualBlock
    source_refs: CounterfactualSourceRefs
    reason_codes: list[str] = Field(default_factory=list)
    promotion_allowed: Literal[False] = False


@dataclass(frozen=True)
class MarketBar:
    ts_ms: int
    symbol: str
    open: float
    high: float
    low: float
    close: float
    source_path: str


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _diagnostic_side_reason_codes(row: JudgeShadowCalibrationRowV1) -> list[str]:
    reason_codes: list[str] = []
    for reason_code in row.diagnostics.reason_codes:
        if reason_code.startswith("candidate_side_source:") or reason_code.startswith("side_source:"):
            reason_codes.append(reason_code)
        if reason_code.startswith("side_conflict"):
            reason_codes.append(reason_code)
    return reason_codes


def load_shadow_rows(path: Path) -> list[JudgeShadowCalibrationRowV1]:
    rows: list[JudgeShadowCalibrationRowV1] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            if isinstance(payload.get("payload"), dict):
                payload = payload["payload"]
            rows.append(JudgeShadowCalibrationRowV1.model_validate(payload))
    return rows


def load_recorder_bars(recorder_root: Path, symbols: Iterable[str]) -> dict[str, list[MarketBar]]:
    wanted = set(symbols)
    bars_by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    if not recorder_root.exists():
        return bars_by_symbol
    for csv_path in sorted(recorder_root.rglob("*.csv")):
        stem_parts = csv_path.stem.rsplit("_", 1)
        if len(stem_parts) != 2 or stem_parts[0] not in wanted:
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                ts = _to_int(row.get("timestamp"))
                symbol = str(row.get("symbol") or stem_parts[0])
                open_price = _to_float(row.get("open"))
                high = _to_float(row.get("high"))
                low = _to_float(row.get("low"))
                close = _to_float(row.get("close"))
                if ts is None or open_price is None or high is None or low is None or close is None:
                    continue
                bars_by_symbol[symbol].append(
                    MarketBar(ts_ms=ts, symbol=symbol, open=open_price, high=high, low=low, close=close, source_path=csv_path.as_posix())
                )
    return {symbol: sorted(bars, key=lambda bar: bar.ts_ms) for symbol, bars in bars_by_symbol.items()}


def candidate_side_for_row(row: JudgeShadowCalibrationRowV1) -> tuple[CandidateSide, list[str]]:
    reason_codes = _diagnostic_side_reason_codes(row)
    if row.side in {"BUY", "SELL"}:
        return row.side, ["candidate_side_from_shadow_row", *reason_codes]
    return "UNKNOWN", ["candidate_side_unknown", *reason_codes]


def _select_forward_bars(bars: Sequence[MarketBar], decision_ts_ms: int, horizon_sec: int) -> list[MarketBar]:
    horizon_end = decision_ts_ms + horizon_sec * 1000
    return [bar for bar in bars if decision_ts_ms < bar.ts_ms <= horizon_end]


def _bps(value: float | None, reference_price: float | None) -> float | None:
    if value is None or reference_price in (None, 0):
        return None
    return (value / reference_price) * 10000.0


def classify_counterfactual(
    *,
    side: CandidateSide,
    net_opportunity_usd: float | None,
    max_adverse_usd: float | None,
    threshold_usd: float,
    threshold_bps: float,
    net_opportunity_bps: float | None,
) -> CounterfactualLabel:
    if side == "BUY":
        if net_opportunity_usd is not None and net_opportunity_bps is not None:
            if net_opportunity_usd > threshold_usd and net_opportunity_bps > threshold_bps:
                return "MISSED_OPPORTUNITY_LONG"
        if max_adverse_usd is not None and max_adverse_usd < -threshold_usd:
            return "AVOIDED_LOSS_LONG"
        return "NEUTRAL_NO_OPPORTUNITY"
    if side == "SELL":
        if net_opportunity_usd is not None and net_opportunity_bps is not None:
            if net_opportunity_usd > threshold_usd and net_opportunity_bps > threshold_bps:
                return "MISSED_OPPORTUNITY_SHORT"
        if max_adverse_usd is not None and max_adverse_usd < -threshold_usd:
            return "AVOIDED_LOSS_SHORT"
        return "NEUTRAL_NO_OPPORTUNITY"
    return "SIDE_UNKNOWN"


def build_label_for_row(
    row: JudgeShadowCalibrationRowV1,
    *,
    horizon_sec: int,
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    created_ts_ms: int,
    reference_price_policy: str,
    fee_bps: float | None,
    slippage_bps: float | None,
    min_move_usd: float,
    min_move_bps: float,
) -> JudgeCounterfactualOpportunityLabelV1:
    side, reason_codes = candidate_side_for_row(row)
    symbol_bars = list(bars_by_symbol.get(row.symbol, []))
    forward_bars = _select_forward_bars(symbol_bars, row.decision_ts_ms, horizon_sec)
    source_refs = CounterfactualSourceRefs(
        rid=row.source_refs.rid,
        decision_id=row.source_refs.decision_id,
        lifecycle_id=row.source_refs.lifecycle_id,
        order_id=row.source_refs.order_id,
    )
    label_prefix = f"judge_cf_v1_{row.row_id}_{horizon_sec}"

    if not symbol_bars:
        reason_codes.append("market_data_missing")
        return JudgeCounterfactualOpportunityLabelV1(
            label_id=label_prefix,
            source_shadow_row_id=row.row_id,
            created_ts_ms=created_ts_ms,
            decision_ts_ms=row.decision_ts_ms,
            symbol=row.symbol,
            candidate_side=side,
            judge_verdict=row.verdict.verdict or "UNKNOWN",
            judge_confidence=row.verdict.confidence,
            horizon_sec=horizon_sec,
            market_data=MarketDataBlock(source="data/recorder", bars_used=0, coverage_status="MISSING"),
            counterfactual=CounterfactualBlock(label="MARKET_DATA_MISSING"),
            source_refs=source_refs,
            reason_codes=sorted(set(reason_codes)),
        )
    if side == "UNKNOWN":
        reason_codes.append("side_required_for_counterfactual")
        return JudgeCounterfactualOpportunityLabelV1(
            label_id=label_prefix,
            source_shadow_row_id=row.row_id,
            created_ts_ms=created_ts_ms,
            decision_ts_ms=row.decision_ts_ms,
            symbol=row.symbol,
            candidate_side=side,
            judge_verdict=row.verdict.verdict or "UNKNOWN",
            judge_confidence=row.verdict.confidence,
            horizon_sec=horizon_sec,
            market_data=MarketDataBlock(
                source="data/recorder",
                first_bar_ts_ms=forward_bars[0].ts_ms if forward_bars else None,
                last_bar_ts_ms=forward_bars[-1].ts_ms if forward_bars else None,
                bars_used=len(forward_bars),
                coverage_status="PARTIAL" if forward_bars else "MISSING",
            ),
            counterfactual=CounterfactualBlock(label="SIDE_UNKNOWN"),
            source_refs=source_refs,
            reason_codes=sorted(set(reason_codes)),
        )
    if not forward_bars:
        reason_codes.append("insufficient_forward_bars")
        return JudgeCounterfactualOpportunityLabelV1(
            label_id=label_prefix,
            source_shadow_row_id=row.row_id,
            created_ts_ms=created_ts_ms,
            decision_ts_ms=row.decision_ts_ms,
            symbol=row.symbol,
            candidate_side=side,
            judge_verdict=row.verdict.verdict or "UNKNOWN",
            judge_confidence=row.verdict.confidence,
            horizon_sec=horizon_sec,
            market_data=MarketDataBlock(source="data/recorder", bars_used=0, coverage_status="MISSING"),
            counterfactual=CounterfactualBlock(label="INSUFFICIENT_FORWARD_DATA"),
            source_refs=source_refs,
            reason_codes=sorted(set(reason_codes)),
        )

    reference_bar = forward_bars[0]
    reference_price = reference_bar.open if reference_price_policy == "first_bar_open" else reference_bar.close
    reference_price_source = reference_price_policy
    max_high = max(bar.high for bar in forward_bars)
    min_low = min(bar.low for bar in forward_bars)
    terminal_close = forward_bars[-1].close

    if side == "BUY":
        max_favorable_usd = max_high - reference_price
        max_adverse_usd = min_low - reference_price
        terminal_return_usd = terminal_close - reference_price
    else:
        max_favorable_usd = reference_price - min_low
        max_adverse_usd = reference_price - max_high
        terminal_return_usd = reference_price - terminal_close

    fee_estimate = (reference_price * fee_bps / 10000.0) if fee_bps is not None else None
    slippage_estimate = (reference_price * slippage_bps / 10000.0) if slippage_bps is not None else None
    if fee_estimate is None and slippage_estimate is None:
        reason_codes.append("fee_slippage_not_estimated")
    else:
        reason_codes.append("diagnostic_fee_slippage_estimated")
    cost_estimate = (fee_estimate or 0.0) + (slippage_estimate or 0.0)
    net_opportunity_usd = max_favorable_usd - cost_estimate
    net_opportunity_bps = _bps(net_opportunity_usd, reference_price)
    label = classify_counterfactual(
        side=side,
        net_opportunity_usd=net_opportunity_usd,
        max_adverse_usd=max_adverse_usd,
        threshold_usd=min_move_usd,
        threshold_bps=min_move_bps,
        net_opportunity_bps=net_opportunity_bps,
    )
    horizon_end = row.decision_ts_ms + horizon_sec * 1000
    coverage_status = "COMPLETE" if forward_bars[-1].ts_ms >= horizon_end else "PARTIAL"
    if coverage_status == "PARTIAL":
        reason_codes.append("partial_forward_horizon")

    return JudgeCounterfactualOpportunityLabelV1(
        label_id=label_prefix,
        source_shadow_row_id=row.row_id,
        created_ts_ms=created_ts_ms,
        decision_ts_ms=row.decision_ts_ms,
        symbol=row.symbol,
        candidate_side=side,
        judge_verdict=row.verdict.verdict or "UNKNOWN",
        judge_confidence=row.verdict.confidence,
        horizon_sec=horizon_sec,
        market_data=MarketDataBlock(
            source="data/recorder",
            first_bar_ts_ms=forward_bars[0].ts_ms,
            last_bar_ts_ms=forward_bars[-1].ts_ms,
            bars_used=len(forward_bars),
            coverage_status=coverage_status,
        ),
        counterfactual=CounterfactualBlock(
            label=label,
            reference_price=reference_price,
            reference_price_source=reference_price_source,
            max_favorable_usd=max_favorable_usd,
            max_adverse_usd=max_adverse_usd,
            terminal_return_usd=terminal_return_usd,
            max_favorable_bps=_bps(max_favorable_usd, reference_price),
            max_adverse_bps=_bps(max_adverse_usd, reference_price),
            terminal_return_bps=_bps(terminal_return_usd, reference_price),
            estimated_fee_usd=fee_estimate,
            estimated_slippage_usd=slippage_estimate,
            net_opportunity_usd=net_opportunity_usd,
            net_opportunity_bps=net_opportunity_bps,
        ),
        source_refs=source_refs,
        reason_codes=sorted(set(reason_codes)),
    )


def build_labels(
    rows: Sequence[JudgeShadowCalibrationRowV1],
    *,
    bars_by_symbol: Mapping[str, Sequence[MarketBar]],
    horizons_sec: Sequence[int],
    created_ts_ms: int | None = None,
    reference_price_policy: str = "first_bar_open",
    fee_bps: float | None = None,
    slippage_bps: float | None = None,
    min_move_usd: float = 0.0,
    min_move_bps: float = 0.0,
) -> list[JudgeCounterfactualOpportunityLabelV1]:
    if reference_price_policy not in {"first_bar_open", "first_bar_close"}:
        raise ValueError("reference_price_policy must be first_bar_open or first_bar_close")
    if any(horizon <= 0 for horizon in horizons_sec):
        raise ValueError("horizons must be positive")
    stamp = created_ts_ms if created_ts_ms is not None else max((row.created_ts_ms for row in rows), default=0)
    labels: list[JudgeCounterfactualOpportunityLabelV1] = []
    for row in rows:
        for horizon_sec in horizons_sec:
            labels.append(
                build_label_for_row(
                    row,
                    horizon_sec=horizon_sec,
                    bars_by_symbol=bars_by_symbol,
                    created_ts_ms=stamp,
                    reference_price_policy=reference_price_policy,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                    min_move_usd=min_move_usd,
                    min_move_bps=min_move_bps,
                )
            )
    return labels


def write_jsonl(labels: Sequence[JudgeCounterfactualOpportunityLabelV1], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for label in labels:
            handle.write(json.dumps(label.model_dump(mode="json"), sort_keys=True) + "\n")


def build_summary(labels: Sequence[JudgeCounterfactualOpportunityLabelV1]) -> dict[str, Any]:
    label_counts = Counter(label.counterfactual.label for label in labels)
    summary = {
        "diagnostic_only": True,
        "promotion_allowed": False,
        "auto_apply": False,
        "total_labels": len(labels),
        "labels_by_horizon": dict(Counter(label.horizon_sec for label in labels)),
        "labels_by_symbol": dict(Counter(label.symbol for label in labels)),
        "labels_by_candidate_side": dict(Counter(label.candidate_side for label in labels)),
        "label_distribution": dict(label_counts),
        "coverage_status": dict(Counter(label.market_data.coverage_status for label in labels)),
        "missed_opportunity_count": sum(
            label_counts.get(name, 0) for name in ("MISSED_OPPORTUNITY_LONG", "MISSED_OPPORTUNITY_SHORT")
        ),
        "avoided_loss_count": sum(label_counts.get(name, 0) for name in ("AVOIDED_LOSS_LONG", "AVOIDED_LOSS_SHORT")),
        "neutral_count": label_counts.get("NEUTRAL_NO_OPPORTUNITY", 0),
        "insufficient_forward_data_count": label_counts.get("INSUFFICIENT_FORWARD_DATA", 0),
        "side_unknown_count": label_counts.get("SIDE_UNKNOWN", 0),
    }
    return summary


def write_summary(summary: Mapping[str, Any], labels: Sequence[JudgeCounterfactualOpportunityLabelV1], json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    md_path = json_path.with_suffix(".md")
    lines = [
        "# Judge Counterfactual Opportunity Summary",
        "",
        f"- diagnostic_only: `{summary['diagnostic_only']}`",
        f"- promotion_allowed: `{summary['promotion_allowed']}`",
        f"- auto_apply: `{summary['auto_apply']}`",
        f"- total_labels: `{summary['total_labels']}`",
        f"- label_distribution: `{summary['label_distribution']}`",
        f"- labels_by_horizon: `{summary['labels_by_horizon']}`",
        f"- labels_by_candidate_side: `{summary['labels_by_candidate_side']}`",
        "",
        "| label | count |",
        "| --- | ---: |",
    ]
    for label, count in sorted(summary["label_distribution"].items()):
        lines.append(f"| {label} | {count} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_horizons(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build diagnostic counterfactual labels for Judge shadow rows.")
    parser.add_argument("--input-enriched-jsonl", required=True)
    parser.add_argument("--recorder-root", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--diagnostics-json", required=True)
    parser.add_argument("--horizons-sec", default="60,300,900")
    parser.add_argument("--fee-bps", type=float)
    parser.add_argument("--slippage-bps", type=float)
    parser.add_argument("--min-move-usd", type=float, default=0.0)
    parser.add_argument("--min-move-bps", type=float, default=0.0)
    parser.add_argument("--side-policy", choices=["explicit_only"], default="explicit_only")
    parser.add_argument("--reference-price-policy", choices=["first_bar_open", "first_bar_close"], default="first_bar_open")
    parser.add_argument("--allow-gross-counterfactual", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        if args.allow_gross_counterfactual:
            raise ValueError("gross counterfactual monetization is not supported in Phase 10H")
        rows = load_shadow_rows(Path(args.input_enriched_jsonl))
        symbols = {row.symbol for row in rows}
        bars_by_symbol = load_recorder_bars(Path(args.recorder_root), symbols)
        labels = build_labels(
            rows,
            bars_by_symbol=bars_by_symbol,
            horizons_sec=parse_horizons(args.horizons_sec),
            reference_price_policy=args.reference_price_policy,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            min_move_usd=args.min_move_usd,
            min_move_bps=args.min_move_bps,
        )
        write_jsonl(labels, Path(args.output_jsonl))
        write_summary(build_summary(labels), labels, Path(args.diagnostics_json))
        return 0
    except Exception as exc:
        print(f"counterfactual opportunity labeling failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
