#!/usr/bin/env python3
from __future__ import annotations

import argparse
import decimal
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.operational_mode import ModeManager
from apps.reference.domains.decision_making.quadratic_scoring_kernel import QuadraticScoringKernel
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.config_models import OperationalMode
from tools.calibration.calibrate_aurora_thresholds import (
    _ReplayClock,
    _ReplayFsm,
    _bar_is_eligible,
    _build_detector_event,
    _build_scoring_features,
    _build_shield_cascade,
    _load_recorder_bars,
    _make_side_bias_state,
)


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    admission_mode: str
    sizing_mode: str
    admission_power: float | None = None
    sizing_power: float | None = None
    admission_shield_floor: float = 0.0


@dataclass(frozen=True)
class SymbolMetrics:
    eligible_bars: int
    neutral_bars: int
    side_bars: int
    allowed_side_bars: int
    nrr027_proxy_bars: int
    buy_bars: int
    sell_bars: int

    @property
    def neutral_ratio(self) -> float:
        return (self.neutral_bars / self.eligible_bars) if self.eligible_bars else 0.0

    @property
    def side_ratio(self) -> float:
        return (self.side_bars / self.eligible_bars) if self.eligible_bars else 0.0

    @property
    def nrr027_proxy_rate(self) -> float:
        return (self.nrr027_proxy_bars / self.side_bars) if self.side_bars else 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Aurora decision geometry candidates")
    parser.add_argument("--symbols", nargs="+",
                        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--tf-sec", type=int, default=300)
    parser.add_argument(
        "--aurora-yaml", default="config/aurora/strategies/aurora.yaml")
    parser.add_argument("--recorder-dir", default="data/recorder")
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def _resolve_symbol_thresholds(typed_config: Any, symbol: str) -> tuple[decimal.Decimal, dict[str, float], set[str]]:
    aurora = typed_config.strategies.aurora
    decision_cfg = aurora.decision
    asset_cfg = aurora.assets[symbol]

    threshold = decimal.Decimal(str(decision_cfg.signal_threshold))
    signal_threshold_cfg = getattr(asset_cfg, "signal_threshold", None)
    if signal_threshold_cfg is not None and getattr(signal_threshold_cfg, "enabled", False):
        threshold = decimal.Decimal(str(signal_threshold_cfg.value))

    regime_thresholds = dict(getattr(asset_cfg, "regime_thresholds", None) or getattr(
        decision_cfg, "regime_threshold_multipliers", {}))
    allowed_regimes = set(getattr(asset_cfg, "allowed_regimes", None) or [])
    return threshold, regime_thresholds, allowed_regimes


def _check_nrr027_proxy(
    *,
    side: str,
    regime_confidence: float | None,
    delta_hist: deque[float],
    min_regime_confidence: float,
    consecutive_bars: int,
) -> bool:
    if side not in {"buy", "sell"}:
        return False
    if len(delta_hist) < consecutive_bars:
        return False
    confidence_value = float(regime_confidence or 0.0)
    if confidence_value < min_regime_confidence:
        return False

    window = list(delta_hist)[-consecutive_bars:]
    if all(value > 0 for value in window) and side == "sell":
        return True
    if all(value < 0 for value in window) and side == "buy":
        return True
    return False


def _replay_candidate(
    *,
    typed_config: Any,
    symbol: str,
    bars: list[Any],
    candidate: CandidateSpec,
) -> SymbolMetrics:
    decision_cfg = typed_config.strategies.aurora.decision
    threshold, regime_thresholds, allowed_regimes = _resolve_symbol_thresholds(
        typed_config, symbol)
    op_mode = getattr(decision_cfg, "operational_mode",
                      OperationalMode.PARANOID)
    mode_manager = ModeManager(op_mode)
    shield_fn, memory_shield = _build_shield_cascade(
        decision_cfg, mode_manager)

    clock = _ReplayClock(now_ms=bars[0].timestamp_ms)
    fsm = _ReplayFsm()
    detector = RegimeDetector(typed_config, fsm, clock=clock)

    current_side = ""
    buy_history_ms: deque[int] = deque()
    sell_history_ms: deque[int] = deque()
    delta_hist: deque[float] = deque(maxlen=max(1, int(
        typed_config.domains.decision_making.directional_sanity.consecutive_bars)))
    prev_close: float | None = None

    eligible_bars = 0
    neutral_bars = 0
    side_bars = 0
    allowed_side_bars = 0
    nrr027_proxy_bars = 0
    buy_bars = 0
    sell_bars = 0

    for bar in bars:
        clock.set_now_ms(bar.timestamp_ms)
        detector.handle_event(_build_detector_event(symbol, bar))
        regime_payload = fsm.latest_regime_payload(symbol)
        features = _build_scoring_features(bar, regime_payload)

        if prev_close is not None:
            delta_hist.append(bar.close - prev_close)
        prev_close = bar.close

        if not _bar_is_eligible(bar):
            continue

        eligible_bars += 1
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
            base_threshold=threshold,
            regime_name=str(features.get("regime") or "UNCERTAIN"),
            regime_thresholds=regime_thresholds,
            side_bias_state=side_bias_state,
            direction_strength_cfg={},
            delta_price_cap_pct=decimal.Decimal(str(getattr(
                getattr(decision_cfg, "signals", None), "delta_price_cap_pct", "0.02"))),
            neutral_threshold=decimal.Decimal(
                str(getattr(decision_cfg, "neutral_threshold", "0.05"))),
            current_side=current_side,
            normalize_mode=str(getattr(
                getattr(decision_cfg, "signals", None), "normalize_signals_mode", "signed_v2")),
            shield_fn=shield_fn,
            score_multiplier=float(
                getattr(decision_cfg, "score_multiplier", 1.0)),
            linear_score=bar.pillar_sum,
            admission_mode=candidate.admission_mode,
            admission_power=candidate.admission_power,
            sizing_mode=candidate.sizing_mode,
            sizing_power=candidate.sizing_power,
            admission_shield_floor=candidate.admission_shield_floor,
        )

        current_side = result.side
        if result.side == "buy":
            buy_history_ms.append(bar.timestamp_ms)
            buy_bars += 1
            side_bars += 1
            if memory_shield is not None:
                memory_shield.record_visit(
                    symbol, features, bar_close_ts=bar.timestamp_ms // 1000)
        elif result.side == "sell":
            sell_history_ms.append(bar.timestamp_ms)
            sell_bars += 1
            side_bars += 1
            if memory_shield is not None:
                memory_shield.record_visit(
                    symbol, features, bar_close_ts=bar.timestamp_ms // 1000)
        else:
            neutral_bars += 1
            continue

        regime_name = str(features.get("regime") or "UNCERTAIN")
        if not allowed_regimes or regime_name in allowed_regimes:
            allowed_side_bars += 1

        if _check_nrr027_proxy(
            side=result.side,
            regime_confidence=regime_payload.get(
                "confidence") if isinstance(regime_payload, dict) else None,
            delta_hist=delta_hist,
            min_regime_confidence=float(
                typed_config.domains.decision_making.directional_sanity.min_regime_confidence),
            consecutive_bars=int(
                typed_config.domains.decision_making.directional_sanity.consecutive_bars),
        ):
            nrr027_proxy_bars += 1

    return SymbolMetrics(
        eligible_bars=eligible_bars,
        neutral_bars=neutral_bars,
        side_bars=side_bars,
        allowed_side_bars=allowed_side_bars,
        nrr027_proxy_bars=nrr027_proxy_bars,
        buy_bars=buy_bars,
        sell_bars=sell_bars,
    )


def _render_report(
    *,
    metrics: dict[str, dict[str, SymbolMetrics]],
    candidates: list[CandidateSpec],
    args: argparse.Namespace,
) -> str:
    lines: list[str] = []
    lines.append("# AURORA DECISION GEOMETRY VALIDATION")
    lines.append("")
    lines.append(f"- Symbols: {', '.join(args.symbols)}")
    lines.append(
        f"- Date window: {args.from_date.isoformat()} .. {args.to_date.isoformat()}")
    lines.append(
        "- Source: recorder bars + RegimeDetector + live shield cascade + current threshold surfaces")
    lines.append(
        "- NRR-027 metric: offline directional-sanity proxy, not live post-signal order-log replay")
    lines.append("")
    for symbol in args.symbols:
        lines.append(f"## {symbol}")
        lines.append("")
        lines.append(
            "| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |")
        lines.append(
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for candidate in candidates:
            item = metrics[candidate.name][symbol]
            lines.append(
                f"| {candidate.name} | {item.eligible_bars} | {item.neutral_ratio:.2%} | {item.side_ratio:.2%} | {item.allowed_side_bars} | {item.nrr027_proxy_bars} | {item.nrr027_proxy_rate:.2%} | {item.buy_bars} | {item.sell_bars} |"
            )
        lines.append("")
    lines.append("## FACTS")
    lines.append("")
    lines.append(
        "- Baseline and candidate metrics were computed on the same recorder/regime/shield path.")
    lines.append(
        "- Candidate 1 uses soft_power p=1.5 as a representative in-band soft-power check.")
    lines.append(
        "- Candidate 2 uses linear admission, quadratic sizing, admission shield floor 0.75.")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    config_dir = Path(args.aurora_yaml).resolve().parents[1]
    typed_config = ConfigLoader(config_dir=config_dir).load_config()

    bars_by_symbol = _load_recorder_bars(
        recorder_dir=Path(args.recorder_dir),
        symbols=[symbol.upper() for symbol in args.symbols],
        from_date=args.from_date,
        to_date=args.to_date,
        tf_sec=int(args.tf_sec),
    )

    candidates = [
        CandidateSpec(name="baseline_quadratic",
                      admission_mode="quadratic", sizing_mode="quadratic"),
        CandidateSpec(name="soft_power_p1_5", admission_mode="soft_power",
                      admission_power=1.5, sizing_mode="quadratic"),
        CandidateSpec(name="decoupled_linear_floor075", admission_mode="linear",
                      sizing_mode="quadratic", admission_shield_floor=0.75),
    ]

    all_metrics: dict[str, dict[str, SymbolMetrics]] = defaultdict(dict)
    for candidate in candidates:
        for symbol in args.symbols:
            bars = bars_by_symbol.get(symbol.upper(), [])
            if not bars:
                raise RuntimeError(f"No recorder bars for {symbol}")
            all_metrics[candidate.name][symbol.upper()] = _replay_candidate(
                typed_config=typed_config,
                symbol=symbol.upper(),
                bars=bars,
                candidate=candidate,
            )

    report = _render_report(metrics=all_metrics,
                            candidates=candidates, args=args)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
