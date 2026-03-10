#!/usr/bin/env python3
"""
Build `bars_regime` dataset (basis TF), regime-conditioned distributions, and fees-aware quantile TP/SL.

Inputs (run bundle):
  reports/backtests/<run_id>/
    - result.json
    - resolved_config.json
    - manifest.json

Outputs (required) under:
  reports/backtests/<run_id>/analysis/
    - bars_regime_BTCUSDT_5m.parquet (or .csv fallback)
    - bars_regime_summary_by_regime.json
    - bars_regime_distributions.md
    - tpsl_recommendations_by_regime.yaml
    - plots/ (optional)

Fail-closed rules:
  - If basis timeframe (basis_tf_sec) cannot be found in resolved_config.json -> STOP (exit 2)
  - If market_regime cannot be reconstructed for every bar -> STOP with diagnosis (exit 3)
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, date, time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import polars as pl
import yaml


HORIZONS_BARS_DEFAULT = (3, 6, 12)
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


class AnalysisError(RuntimeError):
    pass


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise AnalysisError(f"Failed to read JSON: {path} ({e})") from e


def _maybe_parse_date(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        # accept YYYY-MM-DD or ISO datetime
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            pass
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _tf_str_from_sec(tf_sec: int) -> str:
    mapping = {
        60: "1m",
        180: "3m",
        300: "5m",
        900: "15m",
        1800: "30m",
        3600: "1h",
        14400: "4h",
        86400: "1d",
    }
    return mapping.get(int(tf_sec), f"{tf_sec}s")


def _find_latest_run_id(backtests_dir: Path) -> str:
    candidates: list[str] = []
    for p in backtests_dir.iterdir():
        if not p.is_dir():
            continue
        if (p / "resolved_config.json").exists() and (p / "result.json").exists() and (p / "manifest.json").exists():
            candidates.append(p.name)
    if not candidates:
        raise AnalysisError(f"No run bundle dirs found under: {backtests_dir}")
    return sorted(candidates)[-1]


def _extract_basis_tf_sec(resolved_cfg: dict) -> int:
    # The prompt expects regime.basis_tf_sec, but AuroraConfig uses top-level basis_tf_sec.
    # Fail-closed: we do not guess; we require an explicit basis_tf_sec field somewhere.
    if "basis_tf_sec" in resolved_cfg:
        return int(resolved_cfg["basis_tf_sec"])

    # Try nested search (defensive).
    def _walk(o: Any) -> Iterable[Any]:
        if isinstance(o, dict):
            for v in o.values():
                yield v
                yield from _walk(v)
        elif isinstance(o, list):
            for v in o:
                yield v
                yield from _walk(v)

    for node in _walk(resolved_cfg):
        if isinstance(node, dict) and "basis_tf_sec" in node:
            return int(node["basis_tf_sec"])

    raise AnalysisError(
        "FAIL-CLOSED: basis_tf_sec not found in resolved_config.json")


def _select_parquet_files(data_root: Path, symbol: str, tf_str: str) -> list[Path]:
    # Mirror BacktestEngine._find_data_files() behavior.
    candidates = [
        data_root / symbol / tf_str,
        data_root / symbol / "klines" / tf_str,
    ]
    for base in candidates:
        if not base.exists():
            continue
        all_files = sorted(base.glob("*.parquet"))
        month_to_file: dict[str, Path] = {}
        for f in all_files:
            if f.name.endswith("_enriched.parquet"):
                month_to_file[f.stem[: -len("_enriched")]] = f
        for f in all_files:
            if f.name.endswith("_enriched.parquet"):
                continue
            month_to_file.setdefault(f.stem, f)
        selected = [month_to_file[k] for k in sorted(month_to_file.keys())]
        if selected:
            return selected
    return []


def _load_ohlcv(
    *,
    symbol: str,
    tf_str: str,
    start_d: date,
    end_d: date,
    data_root: Path,
) -> pl.DataFrame:
    files = _select_parquet_files(data_root, symbol, tf_str)
    if not files:
        raise AnalysisError(
            f"Could not find OHLCV parquet files for {symbol} tf={tf_str} under {data_root}"
        )

    q = pl.scan_parquet([str(f) for f in files])
    schema = q.collect_schema()
    if "open_time" not in schema:
        raise AnalysisError(f"OHLCV schema missing 'open_time' in {files[0]}")
    if "close_time" not in schema:
        raise AnalysisError(f"OHLCV schema missing 'close_time' in {files[0]}")

    start_ts = datetime.combine(start_d, time.min)
    end_ts = datetime.combine(end_d, time.max)

    q = q.filter((pl.col("open_time") >= start_ts)
                 & (pl.col("open_time") <= end_ts))

    # Standardize / select required columns; keep close_time for ts_close.
    needed = ["open_time", "close_time", "open",
              "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in schema]
    if missing:
        raise AnalysisError(f"OHLCV schema missing columns: {missing}")

    df = q.select([pl.col(c) for c in needed]).sort(
        "open_time").collect(engine="streaming")
    if df.is_empty():
        raise AnalysisError(
            f"OHLCV empty after date filter for {symbol} tf={tf_str} range {start_d}..{end_d}"
        )
    return df


@dataclass(frozen=True)
class DetectorParams:
    sma_short_period: int
    sma_long_period: int
    confidence_min: float
    confidence_max: float
    confidence_multiplier: float
    uncertain_cutoff: float
    vol_enabled: bool
    atr_period: int
    atr_sma_length: int
    allow_close_to_close_atr: bool
    threshold_multiplier: float
    low_vol_multiplier: float
    high_vol_confidence_multiplier: float
    low_vol_confidence_multiplier: float
    mr_threshold: float
    mr_confidence_multiplier: float


def _extract_detector_params(resolved_cfg: dict) -> DetectorParams:
    models = resolved_cfg.get("models") or {}
    sma = models.get("sma_trend") or {}
    vol = models.get("volatility") or {}
    mr = models.get("mean_reversion") or {}

    def req(d: dict, k: str, *, path: str) -> Any:
        if k not in d:
            raise AnalysisError(f"Missing required config field: {path}.{k}")
        return d[k]

    return DetectorParams(
        sma_short_period=int(
            req(sma, "sma_short_period", path="models.sma_trend")),
        sma_long_period=int(
            req(sma, "sma_long_period", path="models.sma_trend")),
        confidence_min=float(
            req(sma, "confidence_min", path="models.sma_trend")),
        confidence_max=float(
            req(sma, "confidence_max", path="models.sma_trend")),
        confidence_multiplier=float(
            req(sma, "confidence_multiplier", path="models.sma_trend")),
        uncertain_cutoff=float(resolved_cfg.get("uncertain_cutoff", 0.0)),
        vol_enabled=bool(req(vol, "enabled", path="models.volatility")),
        atr_period=int(req(vol, "atr_period", path="models.volatility")),
        atr_sma_length=int(
            req(vol, "atr_sma_length", path="models.volatility")),
        allow_close_to_close_atr=bool(
            req(vol, "allow_close_to_close_atr", path="models.volatility")),
        threshold_multiplier=float(
            req(vol, "threshold_multiplier", path="models.volatility")),
        low_vol_multiplier=float(
            req(vol, "low_vol_multiplier", path="models.volatility")),
        high_vol_confidence_multiplier=float(
            req(vol, "high_vol_confidence_multiplier", path="models.volatility")),
        low_vol_confidence_multiplier=float(
            req(vol, "low_vol_confidence_multiplier", path="models.volatility")),
        mr_threshold=float(req(mr, "threshold", path="models.mean_reversion")),
        mr_confidence_multiplier=float(
            req(mr, "confidence_multiplier", path="models.mean_reversion")),
    )


def _rolling_sma(values: np.ndarray, period: int) -> np.ndarray:
    if period <= 0:
        raise ValueError("period must be > 0")
    out = np.full(values.shape[0], np.nan, dtype=np.float64)
    if values.shape[0] < period:
        return out
    csum = np.cumsum(values, dtype=np.float64)
    out[period - 1] = csum[period - 1] / period
    out[period:] = (csum[period:] - csum[:-period]) / period
    return out


def _compute_atr_and_baseline(
    *,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_period: int,
    atr_sma_length: int,
    allow_close_to_close_atr: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = close.shape[0]
    atr = np.full(n, np.nan, dtype=np.float64)
    atr_baseline = np.full(n, np.nan, dtype=np.float64)
    vol_ratio = np.full(n, np.nan, dtype=np.float64)

    tr_buf: list[float] = []
    atr_buf: list[float] = []
    last_atr: Optional[float] = None

    for i in range(n):
        if i == 0:
            continue
        prev_close = close[i - 1]
        tr: Optional[float] = None
        hi = high[i]
        lo = low[i]
        cl = close[i]

        if np.isfinite(hi) and np.isfinite(lo) and np.isfinite(prev_close):
            tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        elif allow_close_to_close_atr and np.isfinite(prev_close) and np.isfinite(cl):
            tr = abs(cl - prev_close)

        if tr is None or (not np.isfinite(tr)) or tr < 0:
            continue

        tr_buf.append(float(tr))
        if last_atr is None:
            if len(tr_buf) >= atr_period:
                init_atr = float(np.mean(tr_buf[-atr_period:]))
                last_atr = init_atr
                atr[i] = init_atr
        else:
            n_f = float(atr_period)
            updated = (last_atr * (n_f - 1.0) + float(tr)) / n_f
            last_atr = updated
            atr[i] = updated

        if np.isfinite(atr[i]):
            atr_buf.append(float(atr[i]))
            if len(atr_buf) >= atr_sma_length:
                base = float(np.mean(atr_buf[-atr_sma_length:]))
                atr_baseline[i] = base
                if base > 0:
                    vol_ratio[i] = float(atr[i] / base)

    return atr, atr_baseline, vol_ratio


def _calculate_confidence(
    *, sma_short: np.ndarray, sma_long: np.ndarray, confidence_min: float, confidence_max: float, confidence_multiplier: float
) -> np.ndarray:
    # Mirrors RegimeDetector._calculate_confidence()
    out = np.full(sma_short.shape[0], np.nan, dtype=np.float64)
    denom = sma_long
    with np.errstate(divide="ignore", invalid="ignore"):
        spread_ratio = (sma_short - sma_long) / denom
        conf = np.abs(spread_ratio * confidence_multiplier)
    conf = np.where(np.isfinite(conf), conf, np.nan)
    conf = np.clip(conf, confidence_min, confidence_max)
    out[:] = conf
    return out


def _detect_regime_per_bar(
    *,
    close: np.ndarray,
    sma_short: np.ndarray,
    sma_long: np.ndarray,
    atr: np.ndarray,
    atr_baseline: np.ndarray,
    vol_ratio: np.ndarray,
    params: DetectorParams,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = close.shape[0]
    regime = np.full(n, "UNCERTAIN", dtype=object)
    confidence = np.full(n, params.confidence_min, dtype=np.float64)
    source_model = np.full(n, "sma_trend_v1", dtype=object)

    conf_min = float(params.confidence_min)
    conf_max = float(params.confidence_max)

    sma_short_ready = np.isfinite(sma_short) & (sma_short > 0)
    sma_long_ready = np.isfinite(sma_long) & (sma_long > 0)
    price_ok = np.isfinite(close) & (close > 0)

    # Priority 1: Volatility regimes
    if params.vol_enabled:
        atr_ready = np.isfinite(atr) & (atr > 0)
        baseline_ready = np.isfinite(atr_baseline) & (atr_baseline > 0)
        ok = atr_ready & baseline_ready & price_ok & np.isfinite(vol_ratio)

        high_mask = ok & (vol_ratio > params.threshold_multiplier)
        if np.any(high_mask):
            excess = vol_ratio[high_mask] - params.threshold_multiplier
            conf = np.minimum(conf_max, conf_min + excess *
                              params.high_vol_confidence_multiplier)
            regime[high_mask] = "HIGH_VOLATILITY"
            confidence[high_mask] = conf
            source_model[high_mask] = "volatility_v2"

        low_mask = ok & (vol_ratio < params.low_vol_multiplier)
        if np.any(low_mask):
            calm = params.low_vol_multiplier - vol_ratio[low_mask]
            conf = np.minimum(conf_max, conf_min + calm *
                              params.low_vol_confidence_multiplier)
            regime[low_mask] = "LOW_VOLATILITY"
            confidence[low_mask] = conf
            source_model[low_mask] = "volatility_v2"

    # Priority 2: Mean reversion
    mr_mask_base = (
        regime == "UNCERTAIN") & sma_short_ready & sma_long_ready & price_ok
    if np.any(mr_mask_base):
        with np.errstate(divide="ignore", invalid="ignore"):
            sma_spread = np.abs(sma_short - sma_long) / sma_long
            dev_short = np.abs(close - sma_short) / sma_short
            dev_long = np.abs(close - sma_long) / sma_long
        tight = np.maximum.reduce([sma_spread, dev_short, dev_long])
        mr_ok = mr_mask_base & (sma_spread < params.mr_threshold) & (
            dev_short < params.mr_threshold) & (dev_long < params.mr_threshold)
        if np.any(mr_ok):
            tightness = params.mr_threshold - tight[mr_ok]
            conf = np.minimum(conf_max, conf_min + tightness *
                              params.mr_confidence_multiplier)
            regime[mr_ok] = "MEAN_REVERSION"
            confidence[mr_ok] = conf
            source_model[mr_ok] = "mean_reversion_v2"

    # Priority 3: SMA trend
    trend_mask_base = (
        regime == "UNCERTAIN") & sma_short_ready & sma_long_ready & price_ok
    if np.any(trend_mask_base):
        conf_trend = _calculate_confidence(
            sma_short=sma_short,
            sma_long=sma_long,
            confidence_min=conf_min,
            confidence_max=conf_max,
            confidence_multiplier=params.confidence_multiplier,
        )

        up = trend_mask_base & (sma_short > sma_long) & (close > sma_short)
        if np.any(up):
            regime[up] = "TREND_UP"
            confidence[up] = conf_trend[up]
            source_model[up] = "sma_trend_v1"

        down = trend_mask_base & (sma_short < sma_long) & (close < sma_short)
        if np.any(down):
            regime[down] = "TREND_DOWN"
            confidence[down] = conf_trend[down]
            source_model[down] = "sma_trend_v1"

    # uncertain_cutoff demotion
    if params.uncertain_cutoff and params.uncertain_cutoff > 0:
        demote = (regime != "UNCERTAIN") & np.isfinite(
            confidence) & (confidence < params.uncertain_cutoff)
        if np.any(demote):
            regime[demote] = "UNCERTAIN"
            confidence[demote] = conf_min
            source_model[demote] = "uncertain_cutoff_gate"

    return regime, confidence, source_model


def _compute_forward_excursions(df: pl.DataFrame, horizons: Iterable[int]) -> pl.DataFrame:
    out = df
    for h in horizons:
        h = int(h)
        if h <= 0:
            continue
        fut_max_high = pl.col("high").shift(-1).rolling_max(window_size=h, min_samples=h).shift(-(h - 1)).alias(
            f"_fut_max_high_h{h}"
        )
        fut_min_low = pl.col("low").shift(-1).rolling_min(window_size=h, min_samples=h).shift(-(h - 1)).alias(
            f"_fut_min_low_h{h}"
        )
        out = out.with_columns([fut_max_high, fut_min_low])
        out = out.with_columns(
            [
                ((pl.col(f"_fut_max_high_h{h}") - pl.col("close")
                  ) / pl.col("close")).alias(f"mfe_up_pct_H{h}"),
                ((pl.col("close") - pl.col(f"_fut_min_low_h{h}")) / pl.col(
                    "close")).alias(f"mae_down_pct_H{h}"),
                # Short symmetry
                ((pl.col("close") - pl.col(f"_fut_min_low_h{h}")) / pl.col(
                    "close")).alias(f"mfe_down_pct_H{h}"),
                ((pl.col(f"_fut_max_high_h{h}") - pl.col("close")
                  ) / pl.col("close")).alias(f"mae_up_pct_H{h}"),
            ]
        ).drop([f"_fut_max_high_h{h}", f"_fut_min_low_h{h}"])
    return out


def _as_float_or_none(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    return v


def _estimate_fees_bps_rt_from_fills(result: dict, *, symbol: str) -> Optional[float]:
    fills = result.get("fills") or []
    if not isinstance(fills, list) or not fills:
        return None
    bps: list[float] = []
    for f in fills:
        if not isinstance(f, dict):
            continue
        if f.get("symbol") != symbol:
            continue
        fee = _as_float_or_none(f.get("fee"))
        price = _as_float_or_none(f.get("price"))
        qty = _as_float_or_none(f.get("quantity") or f.get("filled_qty"))
        if fee is None or price is None or qty is None:
            continue
        notional = price * qty
        if notional <= 0:
            continue
        bps.append((fee / notional) * 10000.0)
    if len(bps) < 20:
        return None
    fee_bps_side = float(np.nanmedian(np.array(bps, dtype=np.float64)))
    return max(0.0, 2.0 * fee_bps_side)


def _extract_costs_bps_rt(resolved_cfg: dict, result: dict, *, symbol: str, buffer_bps: int) -> dict:
    # Fees
    fees_bps_rt = None
    for key in ("fees_bps_rt", "fee_bps_rt", "fees_bps", "fee_bps"):
        if key in resolved_cfg:
            fees_bps_rt = _as_float_or_none(resolved_cfg.get(key))
            break
        if key in result:
            fees_bps_rt = _as_float_or_none(result.get(key))
            break
    if fees_bps_rt is None:
        fees_bps_rt = _estimate_fees_bps_rt_from_fills(result, symbol=symbol)

    # Slippage: prefer explicit, fall back to 2x max_slippage_bps (budget, conservative).
    slippage_bps_rt = None
    for key in ("slippage_bps_rt", "slippage_bps"):
        if key in resolved_cfg:
            slippage_bps_rt = _as_float_or_none(resolved_cfg.get(key))
            break
        if key in result:
            slippage_bps_rt = _as_float_or_none(result.get(key))
            break

    if slippage_bps_rt is None:
        # Try config path: trading.tca_prefs.max_slippage_bps
        tca = (resolved_cfg.get("trading") or {}).get("tca_prefs") or {}
        max_slip = _as_float_or_none(tca.get("max_slippage_bps"))
        if max_slip is not None:
            slippage_bps_rt = 2.0 * max_slip
        else:
            slippage_bps_rt = 0.0

    fees_bps_rt = float(fees_bps_rt) if fees_bps_rt is not None else 0.0
    slippage_bps_rt = float(
        slippage_bps_rt) if slippage_bps_rt is not None else 0.0

    min_dist_bps = int(
        math.ceil(fees_bps_rt + slippage_bps_rt + float(buffer_bps)))
    min_dist_pct = min_dist_bps / 10000.0
    return {
        "fees_bps_rt": fees_bps_rt,
        "slippage_bps_rt": slippage_bps_rt,
        "buffer_bps": int(buffer_bps),
        "min_dist_bps": int(min_dist_bps),
        "min_dist_pct": float(min_dist_pct),
    }


def _group_quantiles(df: pl.DataFrame, metrics: list[str]) -> dict:
    # Returns nested dict: regime -> metric -> stats
    exprs: list[pl.Expr] = [pl.len().alias("__rows")]
    for m in metrics:
        exprs.extend(
            [
                pl.col(m).count().alias(f"{m}__count"),
                pl.col(m).mean().alias(f"{m}__mean"),
                pl.col(m).std().alias(f"{m}__std"),
            ]
        )
        for q in QUANTILES:
            exprs.append(pl.col(m).quantile(
                q, "linear").alias(f"{m}__p{int(q*100):02d}"))

    agg = df.group_by("market_regime").agg(exprs).sort("market_regime")
    out: dict[str, dict[str, Any]] = {}
    for row in agg.iter_rows(named=True):
        reg = str(row["market_regime"])
        reg_out: dict[str, Any] = {"rows": int(row["__rows"]), "metrics": {}}
        for m in metrics:
            m_out: dict[str, Any] = {
                "count": int(row.get(f"{m}__count") or 0),
                "mean": _as_float_or_none(row.get(f"{m}__mean")),
                "std": _as_float_or_none(row.get(f"{m}__std")),
                "quantiles": {},
            }
            for q in QUANTILES:
                key = f"p{int(q*100):02d}"
                m_out["quantiles"][key] = _as_float_or_none(
                    row.get(f"{m}__p{int(q*100):02d}"))
            reg_out["metrics"][m] = m_out
        out[reg] = reg_out
    return out


def _fmt_pct(x: Optional[float], *, dp: int = 4) -> str:
    if x is None:
        return "—"
    if not math.isfinite(float(x)):
        return "—"
    return f"{100.0*float(x):.{dp}f}%"


def _fmt_num(x: Optional[float], *, dp: int = 6) -> str:
    if x is None:
        return "—"
    if not math.isfinite(float(x)):
        return "—"
    return f"{float(x):.{dp}f}"


def _write_md_report(
    *,
    out_path: Path,
    run_id: str,
    symbol: str,
    tf_str: str,
    period: dict,
    detector_params: DetectorParams,
    costs: dict,
    summary_by_regime: dict,
    horizons: list[int],
) -> None:
    lines: list[str] = []
    lines.append(f"# bars_regime distributions — {run_id}\n")
    lines.append(f"- Symbol: `{symbol}`\n")
    lines.append(
        f"- Timeframe: `{tf_str}` (basis_tf_sec={period['basis_tf_sec']})\n")
    lines.append(
        f"- Period: `{period['start_date']}` → `{period['end_date']}`\n")
    lines.append(f"- Bars: `{period['bars']}`\n")
    lines.append("\n## Detector params\n")
    lines.append("```yaml\n")
    lines.append(
        yaml.safe_dump(
            {
                "sma_short_period": detector_params.sma_short_period,
                "sma_long_period": detector_params.sma_long_period,
                "confidence_min": detector_params.confidence_min,
                "confidence_max": detector_params.confidence_max,
                "confidence_multiplier": detector_params.confidence_multiplier,
                "uncertain_cutoff": detector_params.uncertain_cutoff,
                "volatility": {
                    "enabled": detector_params.vol_enabled,
                    "atr_period": detector_params.atr_period,
                    "atr_sma_length": detector_params.atr_sma_length,
                    "allow_close_to_close_atr": detector_params.allow_close_to_close_atr,
                    "threshold_multiplier": detector_params.threshold_multiplier,
                    "low_vol_multiplier": detector_params.low_vol_multiplier,
                    "high_vol_confidence_multiplier": detector_params.high_vol_confidence_multiplier,
                    "low_vol_confidence_multiplier": detector_params.low_vol_confidence_multiplier,
                },
                "mean_reversion": {"threshold": detector_params.mr_threshold, "confidence_multiplier": detector_params.mr_confidence_multiplier},
            },
            sort_keys=False,
        )
    )
    lines.append("```\n")

    lines.append("\n## Fees-aware minimum distance\n")
    lines.append("```yaml\n")
    lines.append(yaml.safe_dump(costs, sort_keys=False))
    lines.append("```\n")

    # Quick insights (required)
    # Use p90 to judge "largest"
    def _best(metric: str, qkey: str) -> tuple[str, Optional[float]]:
        best_reg = "—"
        best_val = None
        for reg, d in summary_by_regime.items():
            val = d["metrics"].get(metric, {}).get("quantiles", {}).get(qkey)
            if val is None:
                continue
            if best_val is None or val > best_val:
                best_val = val
                best_reg = reg
        return best_reg, best_val

    uw_reg, uw_val = _best("upper_wick_pct", "p90")
    lw_reg, lw_val = _best("lower_wick_pct", "p90")
    rng_reg, rng_val = _best("range_pct", "p90")
    lines.append("\n## Quick takeaways\n")
    lines.append(
        f"- Biggest **upper wick** (p90): `{uw_reg}` ({_fmt_pct(uw_val)})\n")
    lines.append(
        f"- Biggest **lower wick** (p90): `{lw_reg}` ({_fmt_pct(lw_val)})\n")
    lines.append(
        f"- Biggest **range** (p90): `{rng_reg}` ({_fmt_pct(rng_val)})\n")

    # Asymmetry in TREND_DOWN (upper vs lower wick)
    td = summary_by_regime.get("TREND_DOWN", {}).get("metrics", {})
    td_uw = td.get("upper_wick_pct", {}).get("quantiles", {}).get("p90")
    td_lw = td.get("lower_wick_pct", {}).get("quantiles", {}).get("p90")
    if td_uw is not None and td_lw is not None:
        asym = td_uw - td_lw
        lines.append(
            f"- `TREND_DOWN` wick asymmetry (p90 upper - p90 lower): `{_fmt_pct(asym)}`\n")

    # Tables
    lines.append("\n## Distributions by regime (geometry)\n")
    geom_metrics = ["range_pct", "upper_wick_pct",
                    "lower_wick_pct", "body_pct"]
    for m in geom_metrics:
        lines.append(f"\n### `{m}`\n\n")
        lines.append(
            "| regime | count | mean | std | p10 | p25 | p50 | p75 | p90 | p95 |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for reg, d in summary_by_regime.items():
            mm = d["metrics"].get(m, {})
            q = mm.get("quantiles", {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        reg,
                        str(mm.get("count") or 0),
                        _fmt_num(mm.get("mean")),
                        _fmt_num(mm.get("std")),
                        _fmt_num(q.get("p10")),
                        _fmt_num(q.get("p25")),
                        _fmt_num(q.get("p50")),
                        _fmt_num(q.get("p75")),
                        _fmt_num(q.get("p90")),
                        _fmt_num(q.get("p95")),
                    ]
                )
                + " |\n"
            )

    lines.append("\n## Distributions by regime (forward excursions)\n")
    for h in horizons:
        tf_sec = int(period.get("basis_tf_sec") or 0)
        horizon_sec = h * tf_sec if tf_sec > 0 else None
        if horizon_sec and horizon_sec % 60 == 0:
            horizon_label = f"{int(horizon_sec // 60)}m"
        elif horizon_sec:
            horizon_label = f"{int(horizon_sec)}s"
        else:
            horizon_label = "?"
        lines.append(f"\n### Horizon H={h} bars ({horizon_label})\n\n")
        for m in [f"mfe_up_pct_H{h}", f"mae_down_pct_H{h}", f"mfe_down_pct_H{h}", f"mae_up_pct_H{h}"]:
            lines.append(f"\n#### `{m}`\n\n")
            lines.append(
                "| regime | count | mean | std | p10 | p25 | p50 | p75 | p90 | p95 |\n")
            lines.append(
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for reg, d in summary_by_regime.items():
                mm = d["metrics"].get(m, {})
                q = mm.get("quantiles", {})
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            reg,
                            str(mm.get("count") or 0),
                            _fmt_num(mm.get("mean")),
                            _fmt_num(mm.get("std")),
                            _fmt_num(q.get("p10")),
                            _fmt_num(q.get("p25")),
                            _fmt_num(q.get("p50")),
                            _fmt_num(q.get("p75")),
                            _fmt_num(q.get("p90")),
                            _fmt_num(q.get("p95")),
                        ]
                    )
                    + " |\n"
                )

    lines.append("\n## Guardrails → aurora.yaml transfer\n")
    lines.append(
        "These regime-conditional TP/SL guardrails come directly from the MAE/MFE quantiles, "
        "with a hard floor at `min_dist_pct` (round-trip costs + buffer). "
        "To transfer into `aurora.yaml`, map per-regime `sl_pct_reco`/`tp_pct_reco` (and min/max) "
        "into your strategy’s regime thresholds / bracket settings.\n"
    )

    out_path.write_text("".join(lines), encoding="utf-8")


def _recommend_tpsl(
    *,
    df: pl.DataFrame,
    horizons: list[int],
    costs: dict,
    sl_q: float = 0.90,
    tp_q: float = 0.80,
    min_guard_q: float = 0.50,
    max_guard_q: float = 0.95,
) -> dict:
    min_dist_pct = float(costs["min_dist_pct"])
    out: dict[str, Any] = {}
    regimes = [r for r in df.select("market_regime").unique().sort(
        "market_regime").to_series().to_list()]

    for reg in regimes:
        sub = df.filter(pl.col("market_regime") == reg)
        reg_out: dict[str, Any] = {"long": {}, "short": {}}
        for h in horizons:
            h = int(h)
            long_mae = f"mae_down_pct_H{h}"
            long_mfe = f"mfe_up_pct_H{h}"
            short_mae = f"mae_up_pct_H{h}"
            short_mfe = f"mfe_down_pct_H{h}"

            def qv(col: str, q: float) -> Optional[float]:
                try:
                    v = sub.select(pl.col(col).quantile(q, "linear")).item()
                except Exception:
                    return None
                return _as_float_or_none(v)

            def reco_block(*, mae_col: str, mfe_col: str) -> dict:
                mae_reco = qv(mae_col, sl_q)
                mfe_reco = qv(mfe_col, tp_q)
                mae_min = qv(mae_col, min_guard_q)
                mae_max = qv(mae_col, max_guard_q)
                mfe_min = qv(mfe_col, min_guard_q)
                mfe_max = qv(mfe_col, max_guard_q)

                bumped_sl = False
                bumped_tp = False

                sl = mae_reco if mae_reco is not None else None
                tp = mfe_reco if mfe_reco is not None else None
                if sl is not None and sl < min_dist_pct:
                    sl = min_dist_pct
                    bumped_sl = True
                if tp is not None and tp < min_dist_pct:
                    tp = min_dist_pct
                    bumped_tp = True

                rr_raw = (
                    tp / sl) if (tp is not None and sl is not None and sl > 0) else None
                rr = rr_raw
                if rr is not None:
                    rr = float(max(1.0, min(4.0, rr)))

                return {
                    "sl": {
                        "reco_pct": sl,
                        "quantile": sl_q,
                        "min_pct": max(mae_min or 0.0, min_dist_pct),
                        "max_pct": mae_max,
                        "bumped_to_min_dist": bool(bumped_sl),
                    },
                    "tp": {
                        "reco_pct": tp,
                        "quantile": tp_q,
                        "min_pct": max(mfe_min or 0.0, min_dist_pct),
                        "max_pct": mfe_max,
                        "bumped_to_min_dist": bool(bumped_tp),
                    },
                    "rr_reco": rr,
                    "rr_raw": rr_raw,
                }

            reg_out["long"][f"H{h}"] = reco_block(
                mae_col=long_mae, mfe_col=long_mfe)
            reg_out["short"][f"H{h}"] = reco_block(
                mae_col=short_mae, mfe_col=short_mfe)

        out[str(reg)] = reg_out
    return out


def _maybe_make_plots(df: pl.DataFrame, out_dir: Path, *, horizons: list[int]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
    except Exception:
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = ["range_pct"]
    if horizons:
        h = int(horizons[0])
        metrics += [f"mfe_up_pct_H{h}", f"mae_down_pct_H{h}"]

    regimes = [r for r in df.select("market_regime").unique().sort(
        "market_regime").to_series().to_list()]

    for metric in metrics:
        # Histogram overlay (density)
        plt.figure(figsize=(10, 5))
        for reg in regimes:
            vals = df.filter(pl.col("market_regime") == reg).select(
                pl.col(metric)).to_series().drop_nulls().to_numpy()
            if vals.size < 100:
                continue
            plt.hist(vals, bins=60, alpha=0.35, density=True, label=reg)
        plt.title(f"Histogram — {metric}")
        plt.xlabel(metric)
        plt.ylabel("density")
        plt.legend(loc="best", fontsize=8)
        plt.tight_layout()
        plt.savefig(out_dir / f"hist_{metric}.png", dpi=140)
        plt.close()

        # ECDF
        plt.figure(figsize=(10, 5))
        for reg in regimes:
            vals = df.filter(pl.col("market_regime") == reg).select(
                pl.col(metric)).to_series().drop_nulls().to_numpy()
            if vals.size < 100:
                continue
            xs = np.sort(vals)
            ys = np.arange(1, xs.size + 1) / xs.size
            plt.plot(xs, ys, label=reg, linewidth=1.5)
        plt.title(f"ECDF — {metric}")
        plt.xlabel(metric)
        plt.ylabel("F(x)")
        plt.legend(loc="best", fontsize=8)
        plt.tight_layout()
        plt.savefig(out_dir / f"ecdf_{metric}.png", dpi=140)
        plt.close()


def build_bars_regime(run_dir: Path, *, symbol: str, data_root: Path, horizons: list[int], buffer_bps: int) -> None:
    resolved_cfg = _read_json(run_dir / "resolved_config.json")
    result = _read_json(run_dir / "result.json")

    basis_tf_sec = _extract_basis_tf_sec(resolved_cfg)
    tf_str = _tf_str_from_sec(basis_tf_sec)

    metadata = result.get("metadata") or {}
    start_d = _maybe_parse_date(metadata.get("start_date"))
    end_d = _maybe_parse_date(metadata.get("end_date"))
    if start_d is None or end_d is None:
        raise AnalysisError(
            "Could not determine analysis start/end date from result.json metadata")

    detector_params = _extract_detector_params(resolved_cfg)

    # Load OHLCV (from project dataset, matching backtest engine selection rules).
    ohlcv = _load_ohlcv(symbol=symbol, tf_str=tf_str,
                        start_d=start_d, end_d=end_d, data_root=data_root)

    # Build base frame
    df = (
        ohlcv.with_columns(
            [
                pl.col("close_time").cast(pl.Int64).alias("ts_close"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("volume").cast(pl.Float64),
            ]
        )
        .drop(["open_time", "close_time"])
        .with_columns(
            [
                ((pl.col("high") - pl.col("low")) /
                 pl.col("close")).alias("range_pct"),
                ((pl.col("close") - pl.col("open")).abs() /
                 pl.col("close")).alias("body_pct"),
                ((pl.col("high") - pl.max_horizontal(["open", "close"])) / pl.col(
                    "close")).alias("upper_wick_pct"),
                ((pl.min_horizontal(["open", "close"]) - pl.col("low")
                  ) / pl.col("close")).alias("lower_wick_pct"),
            ]
        )
    )

    # Compute ATR/SMA/regime using numpy to mirror RegimeDetector logic.
    close = df.select("close").to_series().to_numpy()
    high = df.select("high").to_series().to_numpy()
    low = df.select("low").to_series().to_numpy()

    sma_short = _rolling_sma(close.astype(np.float64),
                             detector_params.sma_short_period)
    sma_long = _rolling_sma(close.astype(np.float64),
                            detector_params.sma_long_period)

    atr, atr_base, vol_ratio = _compute_atr_and_baseline(
        high=high.astype(np.float64),
        low=low.astype(np.float64),
        close=close.astype(np.float64),
        atr_period=detector_params.atr_period,
        atr_sma_length=detector_params.atr_sma_length,
        allow_close_to_close_atr=detector_params.allow_close_to_close_atr,
    )

    regime, conf, source_model = _detect_regime_per_bar(
        close=close.astype(np.float64),
        sma_short=sma_short,
        sma_long=sma_long,
        atr=atr,
        atr_baseline=atr_base,
        vol_ratio=vol_ratio,
        params=detector_params,
    )

    # Fail-closed: market_regime must exist for every bar (even if UNCERTAIN).
    if regime.shape[0] != df.height or np.any(regime == None):  # noqa: E711
        raise AnalysisError(
            "FAIL-CLOSED: could not reconstruct market_regime for each bar. "
            "Regime is formed in apps/reference/domains/regime_detector/regime_detector.py (RegimeDetector.handle_event). "
            "To make this reproducible from run bundles, persist per-bar EVT:REGIME_DETECTED (ts, regime, confidence) "
            "or persist the feature stream (EVT:FEATURES_CALCULATED) for basis TF."
        )

    df = df.with_columns(
        [
            pl.Series("atr", atr).cast(pl.Float64),
            pl.Series("atr_baseline", atr_base).cast(pl.Float64),
            pl.Series("vol_ratio", vol_ratio).cast(pl.Float64),
            pl.Series("sma_short", sma_short).cast(pl.Float64),
            pl.Series("sma_long", sma_long).cast(pl.Float64),
            pl.Series("market_regime", regime).cast(pl.Utf8),
            pl.Series("regime_confidence", conf).cast(pl.Float64),
            pl.Series("regime_source_model", source_model).cast(pl.Utf8),
        ]
    ).with_columns(
        [
            pl.when(pl.col("market_regime") == "TREND_UP")
            .then(pl.lit(1))
            .when(pl.col("market_regime") == "TREND_DOWN")
            .then(pl.lit(-1))
            .otherwise(pl.lit(0))
            .alias("trend_flag"),
        ]
    )

    # Forward excursions
    df = _compute_forward_excursions(df, horizons=horizons)

    # Write outputs
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = analysis_dir / f"bars_regime_{symbol}_{tf_str}.parquet"
    csv_path = analysis_dir / f"bars_regime_{symbol}_{tf_str}.csv"

    wrote_parquet = False
    try:
        df.write_parquet(parquet_path, compression="zstd")
        wrote_parquet = True
        if csv_path.exists():
            csv_path.unlink()
    except Exception:
        df.write_csv(csv_path)
        if parquet_path.exists():
            parquet_path.unlink()

    # Summary stats
    metrics = [
        "range_pct",
        "upper_wick_pct",
        "lower_wick_pct",
        "body_pct",
        "atr",
        "atr_baseline",
        "vol_ratio",
    ]
    for h in horizons:
        metrics.extend(
            [f"mfe_up_pct_H{h}", f"mae_down_pct_H{h}", f"mfe_down_pct_H{h}", f"mae_up_pct_H{h}"])

    summary_by_regime = _group_quantiles(df, metrics=metrics)
    costs = _extract_costs_bps_rt(
        resolved_cfg, result, symbol=symbol, buffer_bps=buffer_bps)

    summary_out = {
        "run_id": str(run_dir.name),
        "symbol": symbol,
        "timeframe": tf_str,
        "basis_tf_sec": int(basis_tf_sec),
        "period": {"start_date": str(start_d), "end_date": str(end_d), "bars": int(df.height)},
        "data_source": {"data_root": str(data_root), "files_mode": "data/processed selection (BacktestEngine._find_data_files)"},
        "detector_params": detector_params.__dict__,
        "costs": costs,
        "by_regime": summary_by_regime,
        "artifacts": {"bars_regime_file": str(parquet_path if wrote_parquet else csv_path)},
    }
    (analysis_dir / "bars_regime_summary_by_regime.json").write_text(
        json.dumps(summary_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # TP/SL recommendations
    tpsl = _recommend_tpsl(df=df, horizons=horizons, costs=costs)
    tpsl_out = {
        "version": 1,
        "run_id": str(run_dir.name),
        "symbol": symbol,
        "timeframe": tf_str,
        "basis_tf_sec": int(basis_tf_sec),
        "horizons_bars": horizons,
        "costs": costs,
        "quantile_policy": {"sl_quantile": 0.90, "tp_quantile": 0.80, "guard_min_quantile": 0.50, "guard_max_quantile": 0.95},
        "recommendations": tpsl,
    }
    (analysis_dir / "tpsl_recommendations_by_regime.yaml").write_text(
        yaml.safe_dump(tpsl_out, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # MD report
    _write_md_report(
        out_path=analysis_dir / "bars_regime_distributions.md",
        run_id=str(run_dir.name),
        symbol=symbol,
        tf_str=tf_str,
        period={"start_date": str(start_d), "end_date": str(
            end_d), "bars": int(df.height), "basis_tf_sec": int(basis_tf_sec)},
        detector_params=detector_params,
        costs=costs,
        summary_by_regime=summary_by_regime,
        horizons=horizons,
    )

    # Optional plots (use first horizon for MAE/MFE)
    _maybe_make_plots(df, analysis_dir / "plots", horizons=horizons[:1])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="bars_regime dataset + distributions + quantile TP/SL (fees-aware)")
    ap.add_argument("--run-id", default=None,
                    help="Run id under reports/backtests/<run_id>/ (default: latest)")
    ap.add_argument("--symbol", default="BTCUSDT",
                    help="Symbol (default: BTCUSDT)")
    ap.add_argument("--data-root", default="data/processed",
                    help="OHLCV root (default: data/processed)")
    ap.add_argument("--buffer-bps", type=int, default=15,
                    help="Extra safety buffer in bps (default: 15)")
    ap.add_argument("--horizons", default="3,6,12",
                    help="Comma-separated horizons in bars (default: 3,6,12)")
    args = ap.parse_args()

    backtests_dir = Path("reports/backtests")
    run_id = str(args.run_id) if args.run_id else _find_latest_run_id(
        backtests_dir)
    run_dir = backtests_dir / run_id

    try:
        horizons = [int(x.strip())
                    for x in str(args.horizons).split(",") if x.strip()]
    except Exception as e:
        raise SystemExit(f"Bad --horizons value: {args.horizons} ({e})") from e
    if not horizons:
        horizons = list(HORIZONS_BARS_DEFAULT)

    try:
        build_bars_regime(
            run_dir,
            symbol=str(args.symbol),
            data_root=Path(args.data_root),
            horizons=horizons,
            buffer_bps=int(args.buffer_bps),
        )
    except AnalysisError as e:
        print(f"ERROR: {e}")
        return 2
    except Exception as e:
        print(f"ERROR (unexpected): {e}")
        return 3

    print(f"OK: wrote analysis outputs under {run_dir/'analysis'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
