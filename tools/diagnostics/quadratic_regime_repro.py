#!/usr/bin/env python3
"""
Quadratic regime reproducibility harness.

This tool runs one backtest through either:
  - classic launcher path (apps.reference.main.main), or
  - script launcher path (scripts.diagnostics.run_backtest_ladder internals),

while capturing event-level traces from FSMCore.emit for audit.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _deep_get(obj: Any, path: Iterable[str], default: Any = None) -> Any:
    cur = obj
    for key in path:
        if cur is None:
            return default
        try:
            cur = getattr(cur, key)
        except Exception:
            return default
    return cur


def _list_report_files() -> List[Path]:
    reports_dir = ROOT / "reports" / "backtests"
    if not reports_dir.exists():
        return []
    return sorted(
        [p for p in reports_dir.glob("backtest_*.json") if not p.name.endswith(".summary.json")]
    )


def _pick_new_report(before: List[Path], after: List[Path]) -> Optional[Path]:
    before_set = {str(p.resolve()) for p in before}
    new_files = [p for p in after if str(p.resolve()) not in before_set]
    if new_files:
        return sorted(new_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    if after:
        return sorted(after, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    return None


@dataclass
class EmitCapture:
    symbols_filter: Optional[set[str]] = None

    def __post_init__(self) -> None:
        self.regime_events: List[Dict[str, Any]] = []
        self.bar_events: List[Dict[str, Any]] = []
        self.feature_events: List[Dict[str, Any]] = []
        self._orig_emit = None

    def _accept_symbol(self, symbol: Any) -> bool:
        if self.symbols_filter is None:
            return True
        return isinstance(symbol, str) and symbol in self.symbols_filter

    def _normalize_emit_args(
        self,
        event_name: Any,
        payload: Optional[Dict[str, Any]],
        why: str,
    ) -> Tuple[str, Dict[str, Any], str]:
        try:
            from vfoundation.core.protocol import Message
        except Exception:
            Message = None  # type: ignore

        if Message is not None and isinstance(event_name, Message):
            msg = event_name
            normalized_name = f"{msg.op}:{msg.verb}"
            normalized_payload = dict(msg.pld or {})
            normalized_why = msg.why or why or ""
            return normalized_name, normalized_payload, normalized_why

        if isinstance(event_name, str):
            normalized_name = event_name
        else:
            normalized_name = str(event_name)

        normalized_payload = payload if isinstance(payload, dict) else {}
        normalized_why = why or ""
        return normalized_name, normalized_payload, normalized_why

    def _capture(self, event_name: str, payload: Dict[str, Any], why: str) -> None:
        symbol = payload.get("symbol")
        if not self._accept_symbol(symbol):
            return

        if event_name == "EVT:REGIME_DETECTED":
            warmup = payload.get("warmup") if isinstance(payload.get("warmup"), dict) else {}
            data_quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
            self.regime_events.append(
                {
                    "seq": len(self.regime_events),
                    "symbol": symbol,
                    "ts_ms": _to_int(payload.get("ts") or payload.get("ts_ms") or payload.get("timestamp_ms")),
                    "regime": payload.get("regime"),
                    "confidence": payload.get("confidence"),
                    "source_model": payload.get("source_model"),
                    "raw_regime": payload.get("raw_regime"),
                    "raw_confidence": payload.get("raw_confidence"),
                    "stable_confidence": payload.get("stable_confidence"),
                    "changed": payload.get("changed"),
                    "last_update_ts_ms": _to_int(payload.get("last_update_ts_ms")),
                    "calc_lag_ms": _to_int(payload.get("calc_lag_ms")),
                    "vol_ratio": payload.get("vol_ratio"),
                    "vol_ratio_slope": payload.get("vol_ratio_slope"),
                    "storm_rejected": payload.get("storm_rejected"),
                    "hysteresis_confirm_count": payload.get("hysteresis_confirm_count"),
                    "warmup_full_ready": warmup.get("full_ready"),
                    "warmup_reasons": list(warmup.get("reasons") or []),
                    "data_drops": list(data_quality.get("drops") or []),
                    "data_notes": list(data_quality.get("notes") or []),
                    "why": why,
                }
            )
            return

        if event_name == "EVT:BAR_CLOSED":
            self.bar_events.append(
                {
                    "seq": len(self.bar_events),
                    "symbol": symbol,
                    "tf_sec": _to_int(payload.get("tf_sec")),
                    "ts_ms": _to_int(
                        payload.get("close_ts")
                        or payload.get("kline_close_time")
                        or payload.get("end_ts_ms")
                        or payload.get("ts")
                    ),
                    "source": payload.get("source"),
                    "why": why,
                }
            )
            return

        if event_name == "EVT:FEATURES_CALCULATED":
            features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
            warmup = payload.get("warmup") if isinstance(payload.get("warmup"), dict) else {}
            self.feature_events.append(
                {
                    "seq": len(self.feature_events),
                    "symbol": symbol,
                    "tf_sec": _to_int(payload.get("tf_sec")),
                    "ts_ms": _to_int(payload.get("ts")),
                    "warmup_full_ready": warmup.get("full_ready"),
                    "pillar_sum": features.get("pillar_sum"),
                    "pillar_tactician": features.get("pillar_tactician"),
                    "pillar_operator": features.get("pillar_operator"),
                    "pillar_strategist": features.get("pillar_strategist"),
                    "pillar_contribs": features.get("pillar_contribs") if isinstance(features.get("pillar_contribs"), dict) else {},
                    "why": why,
                }
            )
            return

    def install(self) -> None:
        from vfoundation.core.fsm_core import FSMCore

        self._orig_emit = FSMCore.emit

        def _wrapped_emit(
            fsm_self: Any,
            event_name: Any,
            payload: Optional[Dict[str, Any]] = None,
            why: str = "",
            data_ref: Optional[List[str]] = None,
            rid: Optional[str] = None,
        ) -> Any:
            normalized_name, normalized_payload, normalized_why = self._normalize_emit_args(
                event_name, payload, why
            )
            self._capture(normalized_name, normalized_payload, normalized_why)
            return self._orig_emit(  # type: ignore[misc]
                fsm_self,
                event_name,
                payload,
                why,
                data_ref,
                rid,
            )

        FSMCore.emit = _wrapped_emit  # type: ignore[assignment]

    def restore(self) -> None:
        if self._orig_emit is None:
            return
        from vfoundation.core.fsm_core import FSMCore

        FSMCore.emit = self._orig_emit  # type: ignore[assignment]


def _snapshot_config(config: Any) -> Dict[str, Any]:
    trading = _deep_get(config, ["trading"])
    backtest = _deep_get(config, ["trading", "backtest"])
    system_md = _deep_get(config, ["system", "market_data"])
    bar_agg = _deep_get(config, ["system", "market_data", "bar_aggregator"])
    fe = _deep_get(config, ["domains", "feature_engineering"])
    pillars = _deep_get(config, ["domains", "feature_engineering", "pillars"])
    strategy_aurora = _deep_get(config, ["strategies", "aurora"])
    decision = _deep_get(config, ["strategies", "aurora", "decision"])
    models = _deep_get(config, ["models"])
    sma = _deep_get(config, ["models", "sma_trend"])
    vol = _deep_get(config, ["models", "volatility"])
    mr = _deep_get(config, ["models", "mean_reversion"])

    return {
        "trading_mode": getattr(config, "trading_mode", None),
        "backtest": {
            "start_date": getattr(backtest, "start_date", None) if backtest is not None else None,
            "end_date": getattr(backtest, "end_date", None) if backtest is not None else None,
            "initial_balance": getattr(backtest, "initial_balance", None) if backtest is not None else None,
            "backtest_mode": getattr(backtest, "backtest_mode", None) if backtest is not None else None,
        },
        "symbols_to_track": list(getattr(trading, "symbols_to_track", []) or []) if trading is not None else [],
        "basis_tf_sec": getattr(config, "basis_tf_sec", None),
        "uncertain_cutoff": getattr(config, "uncertain_cutoff", None),
        "hysteresis_bars": getattr(config, "hysteresis_bars", None),
        "vol_slope_gate_enabled": getattr(config, "vol_slope_gate_enabled", None),
        "vol_slope_gate_eps": getattr(config, "vol_slope_gate_eps", None),
        "vol_slope_gate_confirm_bars": getattr(config, "vol_slope_gate_confirm_bars", None),
        "models": {
            "sma_trend": {
                "enabled": getattr(sma, "enabled", None) if sma is not None else None,
                "sma_short_period": getattr(sma, "sma_short_period", None) if sma is not None else None,
                "sma_long_period": getattr(sma, "sma_long_period", None) if sma is not None else None,
                "confidence_multiplier": getattr(sma, "confidence_multiplier", None) if sma is not None else None,
                "confidence_min": getattr(sma, "confidence_min", None) if sma is not None else None,
                "confidence_max": getattr(sma, "confidence_max", None) if sma is not None else None,
            },
            "volatility": {
                "enabled": getattr(vol, "enabled", None) if vol is not None else None,
                "atr_period": getattr(vol, "atr_period", None) if vol is not None else None,
                "atr_sma_length": getattr(vol, "atr_sma_length", None) if vol is not None else None,
                "allow_close_to_close_atr": getattr(vol, "allow_close_to_close_atr", None) if vol is not None else None,
                "threshold_multiplier": getattr(vol, "threshold_multiplier", None) if vol is not None else None,
                "low_vol_multiplier": getattr(vol, "low_vol_multiplier", None) if vol is not None else None,
            },
            "mean_reversion": {
                "enabled": getattr(mr, "enabled", None) if mr is not None else None,
                "threshold": getattr(mr, "threshold", None) if mr is not None else None,
                "confidence_multiplier": getattr(mr, "confidence_multiplier", None) if mr is not None else None,
            },
            "model_root_present": models is not None,
        },
        "feature_engineering": {
            "enabled_timeframes_sec": list(getattr(fe, "enabled_timeframes_sec", []) or []) if fe is not None else [],
            "pillars_enabled": getattr(pillars, "enabled", None) if pillars is not None else None,
            "pillars": {
                "tactician_timeframe_sec": _deep_get(pillars, ["tactician", "timeframe_sec"]),
                "operator_timeframe_sec": _deep_get(pillars, ["operator", "timeframe_sec"]),
                "strategist_timeframe_sec": _deep_get(pillars, ["strategist", "timeframe_sec"]),
                "weights": {
                    "tactician": _deep_get(pillars, ["weights", "tactician"]),
                    "operator": _deep_get(pillars, ["weights", "operator"]),
                    "strategist": _deep_get(pillars, ["weights", "strategist"]),
                },
            },
        },
        "market_data": {
            "bar_aggregator_enabled": getattr(bar_agg, "enabled", None) if bar_agg is not None else None,
            "bar_aggregator_timeframes_sec": list(getattr(bar_agg, "timeframes_sec", []) or []) if bar_agg is not None else [],
            "tick_ttl_ms": getattr(system_md, "tick_ttl_ms", None) if system_md is not None else None,
            "bar_ttl_ms": getattr(system_md, "bar_ttl_ms", None) if system_md is not None else None,
        },
        "aurora_decision": {
            "scoring_version": getattr(decision, "scoring_version", None) if decision is not None else None,
            "regime_thresholds": dict(getattr(decision, "regime_thresholds", {}) or {}) if decision is not None else {},
            "regime_threshold_multipliers": dict(getattr(decision, "regime_threshold_multipliers", {}) or {}) if decision is not None else {},
            "regime_smoothing_enabled": _deep_get(decision, ["regime_smoothing", "enabled"]),
            "strategy_present": strategy_aurora is not None,
        },
    }


def _run_classic(args: argparse.Namespace) -> Tuple[Any, Dict[str, Any], Optional[Path]]:
    from apps.reference import main as main_mod
    from apps.reference.config_loader import ConfigLoader

    before_reports = _list_report_files()
    captured_cfg: Dict[str, Any] = {}
    original_load_config = ConfigLoader.load_config

    def _patched_load_config(self: Any, *a: Any, **kw: Any) -> Any:
        cfg = original_load_config(self, *a, **kw)
        cfg.trading.backtest.start_date = args.start_date
        cfg.trading.backtest.end_date = args.end_date
        cfg.trading.backtest.initial_balance = float(args.initial_balance)
        if hasattr(cfg.trading, "symbols_to_track"):
            cfg.trading.symbols_to_track = list(args.symbols)
        captured_cfg["config"] = cfg
        return cfg

    ConfigLoader.load_config = _patched_load_config  # type: ignore[assignment]
    try:
        main_mod.main()
    finally:
        ConfigLoader.load_config = original_load_config  # type: ignore[assignment]

    after_reports = _list_report_files()
    report_path = _pick_new_report(before_reports, after_reports)
    report_data: Dict[str, Any] = {}
    if report_path and report_path.exists():
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
    return captured_cfg.get("config"), report_data, report_path


def _run_script_launcher(args: argparse.Namespace) -> Tuple[Any, Dict[str, Any], Optional[Path]]:
    from apps.reference.main import run_backtest_simulation
    from scripts.diagnostics.run_backtest_ladder import _load_config_for_rung

    config_dir = Path(args.config_dir)
    cfg = _load_config_for_rung(
        config_dir=config_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        symbols=list(args.symbols),
        initial_balance=float(args.initial_balance),
    )
    _result, report_data = run_backtest_simulation(cfg, return_result=True)
    run_id = report_data.get("run_id")
    report_path = None
    if isinstance(run_id, str) and run_id:
        candidate = ROOT / "reports" / "backtests" / f"backtest_{run_id}.json"
        if candidate.exists():
            report_path = candidate
    return cfg, report_data, report_path


def _counter_dict(counter: Counter[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key, count in counter.items():
        out[str(key)] = int(count)
    return out


def run_once(args: argparse.Namespace) -> None:
    if args.launcher not in {"classic", "script"}:
        raise ValueError(f"Unsupported launcher: {args.launcher}")

    symbols_set = set(args.symbols) if args.symbols else None
    capture = EmitCapture(symbols_filter=symbols_set)
    capture.install()
    cfg = None
    report_data: Dict[str, Any] = {}
    report_path: Optional[Path] = None
    try:
        if args.launcher == "classic":
            cfg, report_data, report_path = _run_classic(args)
        else:
            cfg, report_data, report_path = _run_script_launcher(args)
    finally:
        capture.restore()

    if cfg is None:
        raise RuntimeError("Config capture failed")

    basis_tf_sec = _to_int(getattr(cfg, "basis_tf_sec", None))
    for row in capture.regime_events:
        row["tf_sec"] = basis_tf_sec
        row["tf_votes"] = None

    bar_tf_counts = Counter(_to_int(evt.get("tf_sec")) for evt in capture.bar_events)
    bar_tf_source_counts = Counter((evt.get("tf_sec"), evt.get("source")) for evt in capture.bar_events)
    features_tf_counts = Counter(_to_int(evt.get("tf_sec")) for evt in capture.feature_events)

    output = {
        "launcher": args.launcher,
        "config_dir": str(Path(args.config_dir).resolve()),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "symbols": list(args.symbols),
        "initial_balance": float(args.initial_balance),
        "config_snapshot": _snapshot_config(cfg),
        "report_run_id": report_data.get("run_id"),
        "report_path": str(report_path.resolve()) if report_path else None,
        "event_counts": {
            "regime_events": len(capture.regime_events),
            "bar_events": len(capture.bar_events),
            "feature_events": len(capture.feature_events),
        },
        "bar_tf_counts": _counter_dict(bar_tf_counts),
        "bar_tf_source_counts": _counter_dict(bar_tf_source_counts),
        "feature_tf_counts": _counter_dict(features_tf_counts),
        "events": {
            "regime": capture.regime_events,
            "bars": capture.bar_events,
            "features": capture.feature_events,
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Wrote trace: {out_path}")


def _norm_regime_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ts_ms": _to_int(row.get("ts_ms")),
        "tf_sec": _to_int(row.get("tf_sec")),
        "symbol": row.get("symbol"),
        "regime": row.get("regime"),
        "confidence": str(row.get("confidence")),
        "raw_regime": row.get("raw_regime"),
        "raw_confidence": str(row.get("raw_confidence")),
        "stable_confidence": str(row.get("stable_confidence")),
        "source_model": row.get("source_model"),
        "changed": row.get("changed"),
        "hysteresis_confirm_count": row.get("hysteresis_confirm_count"),
        "storm_rejected": row.get("storm_rejected"),
        "vol_ratio": str(row.get("vol_ratio")),
        "vol_ratio_slope": row.get("vol_ratio_slope"),
        "warmup_full_ready": row.get("warmup_full_ready"),
        "warmup_reasons": list(row.get("warmup_reasons") or []),
        "data_drops": list(row.get("data_drops") or []),
        "data_notes": list(row.get("data_notes") or []),
        "why": row.get("why"),
    }


def compare_runs(args: argparse.Namespace) -> None:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))
    symbol = args.symbol
    n = int(args.limit)

    left_reg = [
        _norm_regime_row(r)
        for r in (left.get("events", {}).get("regime", []) or [])
        if r.get("symbol") == symbol
    ]
    right_reg = [
        _norm_regime_row(r)
        for r in (right.get("events", {}).get("regime", []) or [])
        if r.get("symbol") == symbol
    ]

    left_first = left_reg[:n]
    right_first = right_reg[:n]

    min_len = min(len(left_first), len(right_first))
    divergence_index = None
    for idx in range(min_len):
        if left_first[idx] != right_first[idx]:
            divergence_index = idx
            break
    if divergence_index is None and len(left_first) != len(right_first):
        divergence_index = min_len

    equivalent_first_n = divergence_index is None and len(left_first) == len(right_first) == n

    out = {
        "symbol": symbol,
        "compare_limit": n,
        "left_path": str(Path(args.left).resolve()),
        "right_path": str(Path(args.right).resolve()),
        "left_launcher": left.get("launcher"),
        "right_launcher": right.get("launcher"),
        "left_regime_events_for_symbol": len(left_reg),
        "right_regime_events_for_symbol": len(right_reg),
        "equivalent_first_n": equivalent_first_n,
        "divergence_index": divergence_index,
        "left_at_divergence": left_first[divergence_index] if divergence_index is not None and divergence_index < len(left_first) else None,
        "right_at_divergence": right_first[divergence_index] if divergence_index is not None and divergence_index < len(right_first) else None,
        "left_first_n": left_first,
        "right_first_n": right_first,
        "config_left": left.get("config_snapshot"),
        "config_right": right.get("config_snapshot"),
        "bar_tf_counts_left": left.get("bar_tf_counts"),
        "bar_tf_counts_right": right.get("bar_tf_counts"),
        "bar_tf_source_counts_left": left.get("bar_tf_source_counts"),
        "bar_tf_source_counts_right": right.get("bar_tf_source_counts"),
        "feature_tf_counts_left": left.get("feature_tf_counts"),
        "feature_tf_counts_right": right.get("feature_tf_counts"),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Wrote comparison: {out_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quadratic regime launcher reproducibility harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run one launcher with event capture")
    run_p.add_argument("--launcher", choices=["classic", "script"], required=True)
    run_p.add_argument("--config-dir", default=str(ROOT / "config" / "aurora"))
    run_p.add_argument("--start-date", required=True)
    run_p.add_argument("--end-date", required=True)
    run_p.add_argument("--symbols", nargs="+", required=True)
    run_p.add_argument("--initial-balance", type=float, default=1000.0)
    run_p.add_argument("--out", required=True)

    cmp_p = sub.add_parser("compare", help="Compare two captured traces")
    cmp_p.add_argument("--left", required=True)
    cmp_p.add_argument("--right", required=True)
    cmp_p.add_argument("--symbol", required=True)
    cmp_p.add_argument("--limit", type=int, default=50)
    cmp_p.add_argument("--out", required=True)

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.cmd == "run":
        run_once(args)
        return
    if args.cmd == "compare":
        compare_runs(args)
        return
    raise RuntimeError(f"Unhandled command: {args.cmd}")


if __name__ == "__main__":
    main()

