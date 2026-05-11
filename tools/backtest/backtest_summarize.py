#!/usr/bin/env python3
"""
Backtest report summarizer (post-processing only).

Reads a raw backtest report JSON (reports/backtests/backtest_*.json, report_version>=2)
and produces a compact *.summary.json next to it.

Key idea:
  - Build rid -> regime map by parsing intents[].why (string list).
  - Group trades by that regime and aggregate counts + pnl stats + close reasons.

Constraints:
  - Does NOT modify backtest engine/core.
  - Handles missing keys gracefully.
  - Rounds floats to reduce output size.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import bisect
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


# Matches e.g. "regime:FLAT_NORMAL", "flat_regime=FLAT_NORMAL", including when embedded in ";...;regime:FLAT_NORMAL;..."
REGIME_RE = re.compile(r"(?i)(?:^|[;\s,\[\(\{])(?:flat_)?regime\s*[:=]\s*([A-Z_]+)")


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _safe_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    try:
        s = str(x)
    except Exception:
        return None
    return s if s else None


def _round(x: Optional[float], nd: int) -> Optional[float]:
    if x is None:
        return None
    if not math.isfinite(x):
        return None
    try:
        return round(float(x), nd)
    except Exception:
        return None


def _round_obj(value: Any, *, money_dp: int, ratio_dp: int) -> Any:
    """
    Recursively round floats inside dict/list.
    Heuristic:
      - keys containing 'pct'/'rate'/'ratio' use ratio_dp
      - keys containing 'pnl'/'fee'/'balance'/'equity' use money_dp
      - otherwise: ratio_dp
    """
    if isinstance(value, float):
        return _round(value, ratio_dp)
    if isinstance(value, list):
        return [_round_obj(v, money_dp=money_dp, ratio_dp=ratio_dp) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            kk = str(k).lower()
            if isinstance(v, float):
                if any(t in kk for t in ("pct", "rate", "ratio")):
                    out[k] = _round(v, ratio_dp)
                elif any(t in kk for t in ("pnl", "fee", "balance", "equity", "drawdown")):
                    out[k] = _round(v, money_dp)
                else:
                    out[k] = _round(v, ratio_dp)
            else:
                out[k] = _round_obj(v, money_dp=money_dp, ratio_dp=ratio_dp)
        return out
    return value


def _parse_regime_from_why(why: Any) -> Optional[str]:
    """
    why is expected to be a list of strings (from intents[].why), but can be anything.
    We try to extract something like:
      - "regime:FLAT_NORMAL"
      - "flat_regime=FLAT_NORMAL"
      - "...;regime:MEAN_REVERSION;..."
    """
    if isinstance(why, str):
        m = REGIME_RE.search(why)
        return m.group(1).upper() if m else None
    if isinstance(why, list):
        for item in why:
            if not isinstance(item, str):
                continue
            m = REGIME_RE.search(item)
            if m:
                return m.group(1).upper()
    return None


def _extract_regime_from_intent(intent: dict[str, Any]) -> Optional[str]:
    # Prefer explicit/why-chain regime (often contains MR's FLAT_* regime),
    # fall back to attached market regime fields (often needed for Aurora).
    parsed = _parse_regime_from_why(intent.get("why"))
    if parsed:
        return parsed.upper()
    for key in ("market_regime", "regime", "flat_regime"):
        v = intent.get(key)
        if isinstance(v, str) and v:
            return v.upper()
    return None


def build_rid_to_regime(report: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    intents = report.get("intents") or []
    if not isinstance(intents, list):
        return out
    for intent in intents:
        if not isinstance(intent, dict):
            continue
        rid = _safe_str(intent.get("rid"))
        if not rid:
            continue
        regime = _extract_regime_from_intent(intent)
        if regime:
            out[rid] = regime
    return out


def build_symbol_intent_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Builds a per-symbol sorted index of intents with (emitted_ts_ms, regime).
    Used as a fallback when trade.rid doesn't match intent.rid (common in practice).
    """
    intents = report.get("intents") or []
    if not isinstance(intents, list):
        return {}

    by_symbol: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for intent in intents:
        if not isinstance(intent, dict):
            continue
        sym = _safe_str(intent.get("instrument")) or _safe_str(intent.get("symbol"))
        if not sym:
            continue
        ts = intent.get("emitted_ts_ms")
        try:
            ts_i = int(ts) if ts is not None else None
        except Exception:
            ts_i = None
        if ts_i is None:
            continue
        regime = _extract_regime_from_intent(intent)
        if not regime:
            continue
        by_symbol[sym].append((ts_i, regime))

    idx: dict[str, dict[str, Any]] = {}
    for sym, rows in by_symbol.items():
        rows.sort(key=lambda x: x[0])
        idx[sym] = {
            "ts": [r[0] for r in rows],
            "regime": [r[1] for r in rows],
        }
    return idx


def infer_regime_for_trade(
    *,
    trade: dict[str, Any],
    rid_to_regime: dict[str, str],
    intent_index: dict[str, dict[str, Any]],
    tf_ms: int,
) -> str:
    # 0) Direct trade fields (newer reports may include these)
    for key in ("market_regime", "intent_market_regime", "regime"):
        v = trade.get(key)
        if isinstance(v, str) and v:
            return v.upper()

    # 0.5) If trade carries intent rid explicitly, use that.
    intent_rid = _safe_str(trade.get("intent_rid"))
    if intent_rid and intent_rid in rid_to_regime:
        return rid_to_regime[intent_rid]

    # 1) Direct rid join (requested in spec)
    rid = _safe_str(trade.get("rid"))
    if rid and rid in rid_to_regime:
        return rid_to_regime[rid]

    # 2) Fallback: nearest preceding intent by (symbol, entry_ts_ms) within a window.
    entry = trade.get("entry") if isinstance(trade.get("entry"), dict) else {}
    sym = _safe_str(trade.get("symbol")) or _safe_str(entry.get("symbol"))
    if not sym:
        return "UNKNOWN"

    try:
        entry_ts = int(entry.get("ts_ms")) if entry.get("ts_ms") is not None else None
    except Exception:
        entry_ts = None
    if entry_ts is None:
        return "UNKNOWN"

    data = intent_index.get(sym)
    if not data:
        return "UNKNOWN"
    ts_list = data.get("ts")
    rg_list = data.get("regime")
    if not isinstance(ts_list, list) or not isinstance(rg_list, list) or not ts_list:
        return "UNKNOWN"

    # rightmost intent ts <= entry_ts
    pos = bisect.bisect_right(ts_list, entry_ts) - 1
    if pos < 0:
        return "UNKNOWN"

    # window: allow up to 2 bars back by default
    window_ms = max(60_000, 2 * max(1, tf_ms))
    if entry_ts - int(ts_list[pos]) > window_ms:
        return "UNKNOWN"
    try:
        return str(rg_list[pos]).upper()
    except Exception:
        return "UNKNOWN"


def dominant_regime_by_symbol_from_counts(report: dict[str, Any]) -> dict[str, str]:
    """
    Fallback for reports that don't include regime in intents[].why (e.g. Aurora),
    and don't provide per-intent market_regime. This uses overall regime counts
    (counts_by_symbol) and picks the dominant regime for each symbol.
    NOTE: This is an approximation (no per-trade timeline).
    """
    regimes = report.get("regimes") if isinstance(report.get("regimes"), dict) else {}
    counts_by_symbol = regimes.get("counts_by_symbol") if isinstance(regimes.get("counts_by_symbol"), dict) else {}
    out: dict[str, str] = {}
    for sym, counts in counts_by_symbol.items():
        if not isinstance(sym, str) or not isinstance(counts, dict) or not counts:
            continue
        best_k = None
        best_v = None
        for k, v in counts.items():
            try:
                vi = int(v)
            except Exception:
                continue
            if best_v is None or vi > best_v:
                best_v = vi
                best_k = str(k)
        if best_k:
            out[sym] = best_k.upper()
    return out


def build_order_id_to_intent_regime(report: dict[str, Any]) -> dict[str, str]:
    """
    Best-effort linkage for rid-loss scenarios:
      orders[].source.order_logger.(reservation_id|metadata.corr_id) == intents[].idempotent_key

    Returns: entry_order_id -> regime_string
    """
    intents = report.get("intents") or []
    if not isinstance(intents, list):
        intents = []
    intents_by_idem: dict[str, dict[str, Any]] = {}
    for it in intents:
        if not isinstance(it, dict):
            continue
        idem = _safe_str(it.get("idempotent_key"))
        if not idem:
            continue
        intents_by_idem[idem] = it

    orders = report.get("orders") or []
    if not isinstance(orders, list) or not orders:
        return {}

    out: dict[str, str] = {}
    for o in orders:
        if not isinstance(o, dict):
            continue
        oid = _safe_str(o.get("order_id"))
        if not oid:
            continue
        src = o.get("source")
        if not isinstance(src, dict):
            continue
        ol = src.get("order_logger")
        if not isinstance(ol, dict):
            continue
        corr_id = _safe_str(ol.get("reservation_id"))
        md = ol.get("metadata")
        if corr_id is None and isinstance(md, dict):
            corr_id = _safe_str(md.get("corr_id"))
        if not corr_id:
            continue
        it = intents_by_idem.get(corr_id)
        if not it:
            continue
        regime = _extract_regime_from_intent(it)
        if regime:
            out[oid] = regime
    return out


@dataclass
class Agg:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl_net: float = 0.0
    pnl_gross: float = 0.0
    fees: float = 0.0
    gross_profit: float = 0.0
    gross_loss_abs: float = 0.0
    close_reasons: dict[str, int] = None  # type: ignore[assignment]
    open_modes: dict[str, int] = None  # type: ignore[assignment]
    exit_modes: dict[str, int] = None  # type: ignore[assignment]
    pnl_buckets: dict[str, int] = None  # type: ignore[assignment]

    def add(self, *, pnl_net: float, pnl_gross: float, fees: float) -> None:
        if self.close_reasons is None:
            self.close_reasons = defaultdict(int)
        if self.open_modes is None:
            self.open_modes = defaultdict(int)
        if self.exit_modes is None:
            self.exit_modes = defaultdict(int)
        if self.pnl_buckets is None:
            self.pnl_buckets = defaultdict(int)
        self.trades += 1
        self.pnl_net += pnl_net
        self.pnl_gross += pnl_gross
        self.fees += fees
        if pnl_net > 0:
            self.wins += 1
            self.gross_profit += pnl_net
        elif pnl_net < 0:
            self.losses += 1
            self.gross_loss_abs += -pnl_net

    def to_dict(self) -> dict[str, Any]:
        profit_factor = None
        if self.gross_loss_abs > 0:
            profit_factor = self.gross_profit / self.gross_loss_abs
        win_rate = (self.wins / self.trades) if self.trades else None
        avg_pnl = (self.pnl_net / self.trades) if self.trades else None
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": win_rate,
            "pnl_usdt_net": self.pnl_net,
            "pnl_usdt_gross": self.pnl_gross,
            "fees_usdt": self.fees,
            "avg_pnl_usdt_net": avg_pnl,
            "profit_factor": profit_factor,
            "close_reasons": dict(sorted((self.close_reasons or {}).items(), key=lambda kv: (-kv[1], kv[0]))),
            "open_mode": dict(sorted((self.open_modes or {}).items(), key=lambda kv: (-kv[1], kv[0]))),
            "exit_mode": dict(sorted((self.exit_modes or {}).items(), key=lambda kv: (-kv[1], kv[0]))),
            "pnl_buckets_usdt_net": dict(sorted((self.pnl_buckets or {}).items(), key=lambda kv: (float(kv[0].split(",")[0][1:]) if kv[0].startswith("[") else 0.0))),
        }


def _bucket_pnl_usdt(pnl: float, edges: list[float]) -> str:
    """
    Returns a label like "[-inf,-50)", "[-50,-20)", ..., "[20,50)", "[50,inf)"
    """
    if not edges:
        return "ALL"
    # edges must be sorted ascending
    idx = bisect.bisect_right(edges, pnl)
    lo = -math.inf if idx == 0 else edges[idx - 1]
    hi = math.inf if idx == len(edges) else edges[idx]
    def fmt(x: float) -> str:
        if x == math.inf:
            return "inf"
        if x == -math.inf:
            return "-inf"
        if abs(x) >= 10:
            return str(int(x))
        return str(x)
    return f"[{fmt(lo)},{fmt(hi)})"


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    rid_to_regime = build_rid_to_regime(report)
    intent_index = build_symbol_intent_index(report)
    dominant_regime_by_symbol = dominant_regime_by_symbol_from_counts(report)
    order_id_to_regime = build_order_id_to_intent_regime(report)
    strict_regime_available = bool(rid_to_regime) or bool(intent_index)

    tf_ms = 0
    try:
        md = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        tf = md.get("timeframe")
        if isinstance(tf, str) and tf.endswith("m"):
            tf_ms = int(tf[:-1]) * 60_000
        elif isinstance(tf, str) and tf.endswith("h"):
            tf_ms = int(tf[:-1]) * 3_600_000
        else:
            tf_ms = 0
    except Exception:
        tf_ms = 0

    trades = report.get("trades") or []
    if not isinstance(trades, list):
        trades = []

    by_regime: dict[str, Agg] = defaultdict(Agg)
    by_regime_by_strategy: dict[str, dict[str, Agg]] = defaultdict(lambda: defaultdict(Agg))

    matched = 0
    pnl_edges = [-100.0, -50.0, -20.0, -10.0, -5.0, -1.0, 0.0, 1.0, 5.0, 10.0, 20.0, 50.0, 100.0]
    for tr in trades:
        if not isinstance(tr, dict):
            continue

        # Preferred linkage: trade.entry.order_id -> order -> corr_id/idempotent_key -> intent -> regime
        entry = tr.get("entry") if isinstance(tr.get("entry"), dict) else {}
        entry_oid = _safe_str(entry.get("order_id"))
        regime = order_id_to_regime.get(entry_oid) if entry_oid else None
        if not regime:
            regime = infer_regime_for_trade(
                trade=tr,
                rid_to_regime=rid_to_regime,
                intent_index=intent_index,
                tf_ms=tf_ms,
            )
        if regime == "UNKNOWN":
            # Approx fallback: dominant regime per symbol (helps make column visible)
            sym = _safe_str(tr.get("symbol"))
            if sym and sym in dominant_regime_by_symbol:
                regime = dominant_regime_by_symbol[sym]
        if regime != "UNKNOWN":
            matched += 1

        strategy = _safe_str(tr.get("strategy")) or "UNKNOWN"
        close_reason = _safe_str(tr.get("close_reason")) or "UNKNOWN"
        entry = tr.get("entry") if isinstance(tr.get("entry"), dict) else {}
        exit_ = tr.get("exit") if isinstance(tr.get("exit"), dict) else {}
        open_mode = _safe_str(entry.get("open_mode")) or "UNKNOWN"
        exit_mode = _safe_str(exit_.get("open_mode")) or "UNKNOWN"

        pnl_net = _safe_float(tr.get("pnl_usdt_net"))
        if pnl_net is None:
            # fallback
            pnl_gross = _safe_float(tr.get("pnl_usdt_gross")) or 0.0
            fees = _safe_float(tr.get("fees_usdt")) or 0.0
            pnl_net = pnl_gross - fees
        pnl_gross = _safe_float(tr.get("pnl_usdt_gross")) or (pnl_net + (_safe_float(tr.get("fees_usdt")) or 0.0))
        fees = _safe_float(tr.get("fees_usdt")) or max(0.0, pnl_gross - pnl_net)

        by_regime[regime].add(pnl_net=float(pnl_net), pnl_gross=float(pnl_gross), fees=float(fees))
        by_regime[regime].close_reasons[close_reason] += 1  # type: ignore[index]
        by_regime[regime].open_modes[open_mode] += 1  # type: ignore[index]
        by_regime[regime].exit_modes[exit_mode] += 1  # type: ignore[index]
        by_regime[regime].pnl_buckets[_bucket_pnl_usdt(float(pnl_net), pnl_edges)] += 1  # type: ignore[index]

        by_regime_by_strategy[regime][strategy].add(
            pnl_net=float(pnl_net), pnl_gross=float(pnl_gross), fees=float(fees)
        )
        by_regime_by_strategy[regime][strategy].close_reasons[close_reason] += 1  # type: ignore[index]
        by_regime_by_strategy[regime][strategy].open_modes[open_mode] += 1  # type: ignore[index]
        by_regime_by_strategy[regime][strategy].exit_modes[exit_mode] += 1  # type: ignore[index]
        by_regime_by_strategy[regime][strategy].pnl_buckets[_bucket_pnl_usdt(float(pnl_net), pnl_edges)] += 1  # type: ignore[index]

    # Extract Alpha Search stats (NEW)
    alpha_search = report.get("alpha_search")
    alpha_summary = None
    if isinstance(alpha_search, dict) and alpha_search.get("enabled"):
         ensemble = alpha_search.get("ensemble") or {}
         virtual = alpha_search.get("virtual_trader") or {}
         perf = ensemble.get("performance") or {}
         
         alpha_summary = {
             "enabled": True,
             "mode": alpha_search.get("mode"),
             "signals": alpha_search.get("signals_generated"),
             "virtual_trader": {
                 "pnl_usdt": _safe_float(virtual.get("total_pnl")),
                 "win_rate": _safe_float(virtual.get("win_rate")),
                 "trades": virtual.get("trades_count")
             },
             "ensemble_perf": _safe_float(perf.get("ensemble_performance"))
         }

    scoring = report.get("scoring_telemetry") if isinstance(report.get("scoring_telemetry"), dict) else {}
    scoring_summary = None
    if scoring:
        scoring_summary = {
            "quadratic_engine_selected_count": scoring.get("quadratic_engine_selected_count"),
            "quadratic_fallback_count": scoring.get("quadratic_fallback_count"),
            "fallback_also_failed_count": scoring.get("fallback_also_failed_count"),
            "engine_names_observed": scoring.get("engine_names_observed") or [],
            "observed_engine_counts": scoring.get("observed_engine_counts") or {},
        }

    proxy_universe = report.get("proxy_universe") if isinstance(report.get("proxy_universe"), dict) else None
    search_provenance = report.get("search_provenance") if isinstance(report.get("search_provenance"), dict) else None
    if search_provenance:
        search_provenance = {
            "trial_id": search_provenance.get("trial_id"),
            "arm_id": search_provenance.get("arm_id"),
            "parent_anchor": search_provenance.get("parent_anchor"),
            "overlay_hash": search_provenance.get("overlay_hash"),
            "effective_config_hash": search_provenance.get("effective_config_hash"),
            "effective_strategy_slice_hash": search_provenance.get("effective_strategy_slice_hash"),
            "preflight_passed": search_provenance.get("preflight_passed"),
            "rejection_reason": search_provenance.get("rejection_reason"),
            "manifest_path": search_provenance.get("manifest_path"),
        }

    # Top-level metrics (keep compact)
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}

    out: dict[str, Any] = {
        "summary_version": "1.2.0",
        "run_id": report.get("run_id"),
        "alpha_search": alpha_summary,  # Added here
        "scoring_telemetry": scoring_summary,
        "proxy_universe": proxy_universe,
        "search_provenance": search_provenance,
        "range": {
            "start_date": (report.get("metadata") or {}).get("start_date") if isinstance(report.get("metadata"), dict) else None,
            "end_date": (report.get("metadata") or {}).get("end_date") if isinstance(report.get("metadata"), dict) else None,
            "timeframe": (report.get("metadata") or {}).get("timeframe") if isinstance(report.get("metadata"), dict) else None,
        },
        "overall": {
            "total_trades_engine": _safe_float(metrics.get("total_trades")) if isinstance(metrics, dict) else None,
            "pnl_usdt": _safe_float(metrics.get("total_pnl")) if isinstance(metrics, dict) else None,
            "roi_pct": _safe_float(metrics.get("roi_pct")) if isinstance(metrics, dict) else None,
            "max_drawdown": _safe_float(metrics.get("max_drawdown")) if isinstance(metrics, dict) else None,
            "win_rate": _safe_float(metrics.get("win_rate")) if isinstance(metrics, dict) else None,
            "end_balance": _safe_float(metrics.get("end_balance")) if isinstance(metrics, dict) else None,
        },
        "trades": {
            "closed_trades_reconstructed": sum(a.trades for a in by_regime.values()),
            "with_regime_match": matched,
            "regime_match_rate": (matched / max(1, sum(a.trades for a in by_regime.values()))),
            "regime_source": (
                "intent_fields_or_why"
                if strict_regime_available
                else ("dominant_regime_counts_by_symbol" if dominant_regime_by_symbol else "none")
            ),
        },
        "by_regime": {},
    }

    for regime in sorted(by_regime.keys()):
        agg = by_regime[regime]
        out["by_regime"][regime] = {
            **agg.to_dict(),
            "by_strategy": {
                strat: by_regime_by_strategy[regime][strat].to_dict()
                for strat in sorted(by_regime_by_strategy[regime].keys())
            },
        }

    return out


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("Root JSON must be an object")
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize a raw backtest report into a compact JSON.")
    ap.add_argument("report", type=str, help="Path to raw backtest report JSON (reports/backtests/backtest_*.json)")
    ap.add_argument("--out", type=str, default=None, help="Output path (.summary.json). Default: next to input.")
    ap.add_argument("--money-dp", type=int, default=2, help="Decimal places for money-like fields (default: 2)")
    ap.add_argument("--ratio-dp", type=int, default=4, help="Decimal places for ratio-like fields (default: 4)")
    args = ap.parse_args()

    src = Path(args.report)
    if not src.exists():
        raise SystemExit(f"Input not found: {src}")

    report = load_json(src)
    summ = summarize(report)
    summ = _round_obj(summ, money_dp=int(args.money_dp), ratio_dp=int(args.ratio_dp))

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = src.with_suffix("")  # drop .json
        out_path = out_path.with_name(out_path.name + ".summary.json")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summ, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
