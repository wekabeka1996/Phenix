#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

try:
    import duckdb  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "duckdb is required. Run with the project venv:\n"
        "  ./.venv/bin/python tools/dir_strength_forensics.py ...\n"
        f"Import error: {e}"
    )

# Ensure project imports resolve when running as a script.
sys.path.append(os.getcwd())

from apps.reference.domains.decision_making.scoring_direction_strength_v1 import (
    compute_direction_strength_score,
)


def _parse_dt(s: str) -> str:
    # DuckDB accepts ISO-like strings directly; keep as-is.
    _ = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return s


def _load_aurora_cfg(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "aurora" not in raw:
        raise SystemExit(f"Invalid aurora strategy profile YAML: {path}")
    return raw["aurora"]


def _pick_symbol_config(aurora: dict[str, Any], symbol: str) -> tuple[dict[str, float], dict[str, float]]:
    decision = aurora.get("decision") or {}
    assets = aurora.get("assets") or {}
    asset = assets.get(symbol) or {}

    weights = asset.get("weights") or (decision.get("signal_weights") or {})
    neutrals = asset.get("feature_neutrals") or (decision.get("feature_neutrals") or {})

    if not isinstance(weights, dict) or not weights:
        raise SystemExit(f"Missing weights for {symbol} (aurora.assets.{symbol}.weights or aurora.decision.signal_weights)")
    if not isinstance(neutrals, dict) or not neutrals:
        raise SystemExit(f"Missing feature_neutrals (aurora.decision.feature_neutrals)")

    return {str(k): float(v) for k, v in weights.items()}, {str(k): float(v) for k, v in neutrals.items()}


def _get_decision_block(aurora: dict[str, Any]) -> dict[str, Any]:
    decision = aurora.get("decision")
    if not isinstance(decision, dict):
        raise SystemExit("aurora.decision missing/invalid in strategy profile")
    return decision


def _compute_dp_norm(*, price: float, dp_raw: float, cap_pct: float) -> float:
    if price <= 0 or cap_pct <= 0:
        return 0.0
    dp_pct = dp_raw / price
    dp_pct = max(-cap_pct, min(cap_pct, dp_pct))
    return dp_pct / cap_pct


def _to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def main() -> int:
    ap = argparse.ArgumentParser(description="Forensic: compute dir/strength scores from DuckDB feature store")
    ap.add_argument("--db", default="data/features.db", help="Path to DuckDB features.db")
    ap.add_argument("--table", default="features", help="DuckDB table: features/features_5m/features_15m/... ")
    ap.add_argument("--aurora-yaml", default="config/aurora/strategies/aurora.yaml", help="Aurora strategy profile SSOT")
    ap.add_argument("--symbol", action="append", required=True, help="Symbol (repeatable), e.g. BTCUSDT")
    ap.add_argument("--since", type=_parse_dt, default=None, help="ISO timestamp inclusive, e.g. 2026-01-04T00:00:00")
    ap.add_argument("--until", type=_parse_dt, default=None, help="ISO timestamp exclusive")
    ap.add_argument("--limit", type=int, default=5000, help="Max rows per symbol")
    ap.add_argument("--normalize-mode", choices=["off", "signed_v2"], default=None, help="Override normalize_signals_mode")
    args = ap.parse_args()

    aurora = _load_aurora_cfg(Path(args.aurora_yaml))
    decision = _get_decision_block(aurora)

    signals = decision.get("signals") or {}
    cap_pct = float(signals.get("delta_price_cap_pct"))
    normalize_mode = args.normalize_mode or str(signals.get("normalize_signals_mode") or "off")

    ds_cfg = decision.get("direction_strength_scoring") or {}
    directional_features = list(ds_cfg.get("directional_features") or [])
    strength_features = list(ds_cfg.get("strength_features") or [])
    strength_alpha = float(ds_cfg.get("strength_alpha"))
    strength_cap = float(ds_cfg.get("strength_cap"))

    essential_features = set(decision.get("essential_features") or [])

    con = duckdb.connect(str(args.db), read_only=True)

    for symbol in args.symbol:
        weights, neutrals = _pick_symbol_config(aurora, symbol)

        where = ["symbol = ?"]
        params: list[Any] = [symbol]
        if args.since:
            where.append("timestamp >= ?")
            params.append(args.since)
        if args.until:
            where.append("timestamp < ?")
            params.append(args.until)
        where_sql = " AND ".join(where)

        query = f"""
            SELECT timestamp, features
            FROM {args.table}
            WHERE {where_sql}
            ORDER BY timestamp ASC
            LIMIT {int(args.limit)}
        """
        rows = con.execute(query, params).fetchall()

        scores: list[float] = []
        neg = pos = zero = 0
        examples: list[dict[str, Any]] = []

        for ts, feat_json in rows:
            try:
                feats = json.loads(feat_json) if isinstance(feat_json, str) else feat_json
            except Exception:
                continue
            if not isinstance(feats, dict):
                continue

            price = _to_float(feats.get("price"))
            dp_raw = _to_float(feats.get("delta_price"))
            dp_norm = _compute_dp_norm(price=price, dp_raw=dp_raw, cap_pct=cap_pct)

            eval_feats = dict(feats)
            eval_feats["delta_price"] = dp_norm

            # No warmup readiness in this store; treat as ready for forensic distribution.
            readiness = {k: True for k in eval_feats.keys()}

            res = compute_direction_strength_score(
                features=eval_feats,
                weights=weights,
                neutrals=neutrals,
                readiness=readiness,
                essential_features=essential_features,
                normalize_mode=normalize_mode,
                directional_features=directional_features,
                strength_features=strength_features,
                strength_alpha=strength_alpha,
                strength_cap=strength_cap,
                symbol=symbol,
            )
            if res.deferred:
                continue

            s = float(res.final_score)
            if s > 0:
                pos += 1
            elif s < 0:
                neg += 1
            else:
                zero += 1
            scores.append(s)

            if len(examples) < 5 and (abs(s) >= 0.7):
                examples.append(
                    {
                        "timestamp": str(ts),
                        "final_score": s,
                        "dir_score": float(res.dir_score),
                        "strength_score": float(res.strength_score),
                        "dir_contribs_top": sorted(
                            res.dir_result.contribs.items(), key=lambda kv: abs(kv[1]), reverse=True
                        )[:5],
                        "strength_contribs_top": sorted(
                            res.strength_result.contribs.items(), key=lambda kv: abs(kv[1]), reverse=True
                        )[:5],
                    }
                )

        if not scores:
            print(json.dumps({"symbol": symbol, "rows": len(rows), "usable": 0, "error": "no usable rows"}))
            continue

        scores_sorted = sorted(scores)
        def q(p: float) -> float:
            if not scores_sorted:
                return float("nan")
            idx = int(round((len(scores_sorted) - 1) * p))
            return scores_sorted[max(0, min(len(scores_sorted) - 1, idx))]

        summary = {
            "symbol": symbol,
            "table": args.table,
            "rows": len(rows),
            "usable": len(scores),
            "normalize_mode": normalize_mode,
            "pos": pos,
            "neg": neg,
            "zero": zero,
            "pos_share": pos / len(scores),
            "neg_share": neg / len(scores),
            "q10": q(0.10),
            "q50": q(0.50),
            "q90": q(0.90),
            "examples": examples,
        }
        print(json.dumps(summary, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
