"""PKG-1 Judge Outcomes Materializer.

Reads Judge shadow telemetry + 1m candles and produces the strict
`data/simulator/outcomes.json` that the offline Judge Phase 5 simulator
expects, plus sidecar metadata artifacts:

  - data/simulator/outcomes_manifest.json
  - data/simulator/outcomes_skipped.jsonl
  - data/simulator/outcomes_diagnostics.jsonl

CONTRACT (binding):
  * outcomes.json must validate against outcome_input_v1.json (strict;
    additionalProperties: false). NO metadata fields beyond the 8 allowed.
  * One canonical outcome per CorrelationKey
    (strategy_id, symbol, tf_sec, bar_close_ts).
  * Duplicate CorrelationKey → hard fail BEFORE writing outcomes.json.
  * Bar-close invariant: ts_ms % (tf_sec*1000) == tf_sec*1000 - 1.
  * First eligible exit candle must satisfy: candle_open_ts_ms > bar_close_ts
    (no future leakage; decision candle is excluded).
  * No filter on `applied=true` (shadow mode has zero applied rows).
  * Materializer does NOT apply fee/slippage; pointers recorded in manifest.
  * USD ROI computed ONLY when config economics block is enabled (PKG-3).
  * No silent drops — every verdict either becomes one outcome or is
    written to outcomes_skipped.jsonl with a typed reason.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import logging
import sys
import time
from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

# Lazy import for jsonschema (only needed when writing/validating outcomes.json)
try:
    from jsonschema import Draft7Validator
except Exception:  # pragma: no cover
    Draft7Validator = None  # type: ignore[assignment]

from apps.reference.domains.alpha_search.judge.simulator.config_models import (
    EconomicsConfig,
    SimulatorConfig,
)
from tools.judge.notional import (
    InstrumentPrecision,
    compute_roi_usd,
    derive_notional_for_outcome,
    load_instrument_precision_map,
    manifest_pointer_strings,
)

LOG = logging.getLogger("judge.outcomes_materializer")

DEFAULT_HORIZON_BARS = 12
DEFAULT_REGIME_FRESHNESS_BARS = 5
SCHEMA_VERSION = "1"
STRATEGY_ID = "aurora"

OUTCOME_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "reference"
    / "domains"
    / "alpha_search"
    / "judge"
    / "simulator"
    / "schemas"
    / "outcome_input_v1.json"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CorrelationKey:
    strategy_id: str
    symbol: str
    tf_sec: int
    bar_close_ts: int


@dataclass
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    close_time_ms: int


@dataclass
class CanonicalPlan:
    plan_id: str
    source_verdict_id: str
    symbol: str
    tf_sec: int
    ts_ms: int
    entry_side: str  # "BUY" or "SELL"
    limit_price: float
    tp_price: float
    sl_price: float
    confidence: float
    confidence_tier: str


@dataclass
class Outcome:
    """The 8-field strict outcome row. NO other fields permitted."""
    strategy_id: str
    symbol: str
    tf_sec: int
    bar_close_ts: int
    matched_trade: bool
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_ts_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "tf_sec": self.tf_sec,
            "bar_close_ts": self.bar_close_ts,
            "matched_trade": self.matched_trade,
        }
        if self.matched_trade:
            d["entry_price"] = self.entry_price
            d["exit_price"] = self.exit_price
            d["exit_ts_ms"] = self.exit_ts_ms
        return d


@dataclass
class Skip:
    verdict_id: Optional[str]
    correlation_key: Optional[dict[str, Any]]
    skip_reason: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diagnostic:
    """Per-verdict diagnostic record (sidecar — NEVER written into outcomes.json)."""
    verdict_id: str
    correlation_key: dict[str, Any]
    plan_id: str
    chosen_tier: str
    candidate_plan_count: int
    actionable_candidate_count: int
    entry_side: str
    limit_price: float
    tp_price: float
    sl_price: float
    confidence: float
    fill_model: str
    matched_trade: bool
    entry_price: Optional[float]
    exit_price: Optional[float]
    exit_ts_ms: Optional[int]
    # FILLED_TP / FILLED_SL / TIMEOUT / NO_FILL / AMBIGUOUS_TP_SL_SAME_CANDLE
    exit_classification: str
    ambiguity_policy: Optional[str] = None
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    regime_ts_ms: Optional[int] = None
    regime_stale_bars: Optional[int] = None
    horizon_ms: Optional[int] = None
    notional_sidecar: Optional[dict[str, Any]] = None
    roi_usd: Optional[dict[str, Any]] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None


# ---------------------------------------------------------------------------
# JSONL loaders
# ---------------------------------------------------------------------------

def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                LOG.warning(
                    "Skipping malformed JSON line %s:%d (%s)", path, ln, exc)
                continue


def load_verdicts(judge_log_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(judge_log_dir.glob("verdict_*.jsonl")):
        rows.extend(_iter_jsonl(f))
    return rows


def load_shadow_plans(judge_log_dir: Path) -> dict[str, list[dict]]:
    by_verdict: dict[str, list[dict]] = {}
    for f in sorted(judge_log_dir.glob("shadow_entry_plan_*.jsonl")):
        for row in _iter_jsonl(f):
            svid = row.get("source_verdict_id")
            if not svid:
                continue
            by_verdict.setdefault(svid, []).append(row)
    return by_verdict


def load_envelopes(judge_log_dir: Path) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for f in sorted(judge_log_dir.glob("envelope_*.jsonl")):
        for row in _iter_jsonl(f):
            eid = row.get("envelope_id")
            if eid:
                by_id[eid] = row
    return by_id


# ---------------------------------------------------------------------------
# Candle loading
# ---------------------------------------------------------------------------

def _coerce_candle_from_raw_array(arr: list) -> Optional[Candle]:
    try:
        return Candle(
            open_time_ms=int(arr[0]),
            open=float(arr[1]),
            high=float(arr[2]),
            low=float(arr[3]),
            close=float(arr[4]),
            close_time_ms=int(arr[6]),
        )
    except (IndexError, ValueError, TypeError):
        return None


def load_raw_binance_candles(raw_1m_dir: Path) -> dict[str, list[Candle]]:
    """Load `data/raw_binance_klines_1m/<SYMBOL>/*.json` arrays.

    Returns dict[symbol] -> sorted/dedup list of Candle.
    """
    out: dict[str, dict[int, Candle]] = {}
    if not raw_1m_dir.is_dir():
        return {}
    for sym_dir in sorted(p for p in raw_1m_dir.iterdir() if p.is_dir()):
        symbol = sym_dir.name.upper()
        bucket = out.setdefault(symbol, {})
        for jf in sorted(sym_dir.glob("*.json")):
            try:
                payload = json.loads(jf.read_text(encoding="utf-8"))
            except Exception as exc:
                LOG.warning("Failed to read raw kline file %s (%s)", jf, exc)
                continue
            if not isinstance(payload, list):
                continue
            for entry in payload:
                if not isinstance(entry, list):
                    continue
                c = _coerce_candle_from_raw_array(entry)
                if c is None:
                    continue
                bucket[c.open_time_ms] = c
    return {sym: [b[k] for k in sorted(b.keys())] for sym, b in out.items()}


def load_recorder_candles(recorder_1m_dir: Path) -> dict[str, list[Candle]]:
    """Load `data/recorder_backfill_1m/**/<SYMBOL>_60.csv` files."""
    out: dict[str, dict[int, Candle]] = {}
    if not recorder_1m_dir.is_dir():
        return {}
    for csv_path in sorted(recorder_1m_dir.rglob("*_60.csv")):
        try:
            with csv_path.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        symbol = row["symbol"].upper()
                        close_ms = int(row["timestamp"])
                        open_ms = close_ms - 60_000 + 1  # close = open+60s-1ms
                        c = Candle(
                            open_time_ms=open_ms,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            close_time_ms=close_ms,
                        )
                    except (KeyError, ValueError) as exc:
                        LOG.warning("Skip recorder row in %s (%s)",
                                    csv_path, exc)
                        continue
                    out.setdefault(symbol, {})[c.open_time_ms] = c
        except Exception as exc:
            LOG.warning("Failed to read recorder CSV %s (%s)", csv_path, exc)
            continue
    return {sym: [b[k] for k in sorted(b.keys())] for sym, b in out.items()}


def merge_candle_sources(*sources: dict[str, list[Candle]]) -> dict[str, list[Candle]]:
    merged: dict[str, dict[int, Candle]] = {}
    for src in sources:
        for symbol, candles in src.items():
            bucket = merged.setdefault(symbol, {})
            for c in candles:
                # Raw cache wins over recorder (raw is exchange-original); we
                # only let recorder fill when key is absent.
                bucket.setdefault(c.open_time_ms, c)
    return {sym: [b[k] for k in sorted(b.keys())] for sym, b in merged.items()}


def candles_in_window(
    candles: list[Candle], strict_start_ts: int, end_ts_inclusive: int
) -> list[Candle]:
    """Return candles with open_time_ms > strict_start_ts AND open_time_ms <= end_ts_inclusive."""
    if not candles:
        return []
    opens = [c.open_time_ms for c in candles]
    # bisect_right(opens, strict_start_ts) gives index of first > strict_start_ts
    lo = bisect_right(opens, strict_start_ts)
    out: list[Candle] = []
    for i in range(lo, len(candles)):
        if candles[i].open_time_ms > end_ts_inclusive:
            break
        out.append(candles[i])
    return out


# ---------------------------------------------------------------------------
# Canonical plan selection
# ---------------------------------------------------------------------------

_TIER_PRIORITY = {"high": 3, "medium": 2, "low": 1}


def select_canonical_plan(plans: list[dict]) -> tuple[Optional[CanonicalPlan], int, int]:
    """v1 selection: prefer actionable+not-suppressed+priced plans, then highest tier,
    then highest confidence, then plan_id sort. Returns (chosen, total_count, actionable_count).
    """
    if not plans:
        return None, 0, 0
    actionable = []
    for p in plans:
        if not bool(p.get("actionable")):
            continue
        if bool(p.get("suppressed")):
            continue
        if p.get("limit_price") in (None,):
            continue
        if p.get("tp_price") in (None,) or p.get("sl_price") in (None,):
            continue
        side = p.get("entry_side")
        if side not in ("BUY", "SELL"):
            continue
        actionable.append(p)
    if not actionable:
        return None, len(plans), 0

    def _key(p: dict) -> tuple:
        tier = (p.get("confidence_tier") or "").lower()
        return (
            -_TIER_PRIORITY.get(tier, 0),
            -float(p.get("confidence") or 0.0),
            str(p.get("plan_id") or ""),
        )

    actionable.sort(key=_key)
    chosen_raw = actionable[0]
    chosen = CanonicalPlan(
        plan_id=str(chosen_raw["plan_id"]),
        source_verdict_id=str(chosen_raw["source_verdict_id"]),
        symbol=str(chosen_raw["symbol"]),
        tf_sec=int(chosen_raw["tf_sec"]),
        ts_ms=int(chosen_raw["ts_ms"]),
        entry_side=str(chosen_raw["entry_side"]),
        limit_price=float(chosen_raw["limit_price"]),
        tp_price=float(chosen_raw["tp_price"]),
        sl_price=float(chosen_raw["sl_price"]),
        confidence=float(chosen_raw.get("confidence") or 0.0),
        confidence_tier=str(chosen_raw.get("confidence_tier") or ""),
    )
    return chosen, len(plans), len(actionable)


# ---------------------------------------------------------------------------
# Fill / exit simulation
# ---------------------------------------------------------------------------

@dataclass
class ReplayResult:
    matched_trade: bool
    entry_price: Optional[float]
    exit_price: Optional[float]
    exit_ts_ms: Optional[int]
    exit_classification: str
    ambiguity_policy: Optional[str] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None


def replay_plan_on_candles(
    plan: CanonicalPlan,
    window_candles: list[Candle],
    fill_model: str = "optimistic_touch",
) -> ReplayResult:
    """v1 deterministic raw-fill/raw-exit replay on 1m candles.

    Fill model (optimistic_touch): LIMIT LONG fills if candle.low <= limit_price;
    LIMIT SHORT fills if candle.high >= limit_price. Entry price = limit_price
    (no slippage). Materializer never applies fee/slippage.

    Exit: walk from the fill candle (inclusive) forward. Same-candle TP+SL
    resolves to worst case (SL).
    """
    if not window_candles:
        return ReplayResult(False, None, None, None, "NO_FILL")

    side = plan.entry_side.upper()
    is_long = side == "BUY"
    limit = plan.limit_price
    tp = plan.tp_price
    sl = plan.sl_price

    # Locate first fill candle.
    fill_idx: Optional[int] = None
    for i, c in enumerate(window_candles):
        if is_long and c.low <= limit:
            fill_idx = i
            break
        if (not is_long) and c.high >= limit:
            fill_idx = i
            break
    if fill_idx is None:
        return ReplayResult(False, None, None, None, "NO_FILL")

    entry_price = limit
    entry_ts = window_candles[fill_idx].open_time_ms

    # Walk fill candle onward for TP/SL.
    mfe = 0.0
    mae = 0.0
    for c in window_candles[fill_idx:]:
        if is_long:
            mfe = max(mfe, c.high - entry_price)
            mae = max(mae, entry_price - c.low)
            tp_hit = c.high >= tp
            sl_hit = c.low <= sl
        else:
            mfe = max(mfe, entry_price - c.low)
            mae = max(mae, c.high - entry_price)
            tp_hit = c.low <= tp
            sl_hit = c.high >= sl
        if tp_hit and sl_hit:
            # Worst-case → SL for both directions.
            return ReplayResult(
                matched_trade=True,
                entry_price=entry_price,
                exit_price=sl,
                exit_ts_ms=c.close_time_ms,
                exit_classification="AMBIGUOUS_TP_SL_SAME_CANDLE",
                ambiguity_policy="worst_case",
                mfe=mfe,
                mae=mae,
            )
        if tp_hit:
            return ReplayResult(
                matched_trade=True,
                entry_price=entry_price,
                exit_price=tp,
                exit_ts_ms=c.close_time_ms,
                exit_classification="FILLED_TP",
                mfe=mfe,
                mae=mae,
            )
        if sl_hit:
            return ReplayResult(
                matched_trade=True,
                entry_price=entry_price,
                exit_price=sl,
                exit_ts_ms=c.close_time_ms,
                exit_classification="FILLED_SL",
                mfe=mfe,
                mae=mae,
            )
    # Timeout: exit at last candle close.
    last = window_candles[-1]
    return ReplayResult(
        matched_trade=True,
        entry_price=entry_price,
        exit_price=last.close,
        exit_ts_ms=last.close_time_ms,
        exit_classification="TIMEOUT",
        mfe=mfe,
        mae=mae,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@dataclass
class MaterializerConfig:
    horizon_bars: int = DEFAULT_HORIZON_BARS
    fill_model: str = "optimistic_touch"
    now_utc_ms: Optional[int] = None
    regime_freshness_bars: int = DEFAULT_REGIME_FRESHNESS_BARS


@dataclass
class MaterializerResult:
    outcomes: list[Outcome]
    skipped: list[Skip]
    diagnostics: list[Diagnostic]
    duplicate_correlation_keys: list[dict]
    applied_true_count: int
    applied_false_count: int
    verdict_total: int
    selected_plan_count: int


def _assert_bar_close_invariant(ts_ms: int, tf_sec: int) -> bool:
    return ts_ms % (tf_sec * 1000) == tf_sec * 1000 - 1


def _now_ms(cfg: MaterializerConfig) -> int:
    return cfg.now_utc_ms if cfg.now_utc_ms is not None else int(time.time() * 1000)


def materialize(
    verdicts: list[dict],
    shadow_plans: dict[str, list[dict]],
    envelopes: dict[str, dict],
    candles_by_symbol: dict[str, list[Candle]],
    sim_cfg: SimulatorConfig,
    mat_cfg: MaterializerConfig,
    precision_map: Optional[dict[str, InstrumentPrecision]] = None,
) -> MaterializerResult:
    outcomes: list[Outcome] = []
    skipped: list[Skip] = []
    diagnostics: list[Diagnostic] = []
    seen_keys: dict[tuple, dict] = {}
    duplicates: list[dict] = []
    applied_true = 0
    applied_false = 0
    selected = 0

    now_ms = _now_ms(mat_cfg)
    horizon_bars = mat_cfg.horizon_bars

    economics: Optional[EconomicsConfig] = sim_cfg.economics

    for v in verdicts:
        vid = v.get("verdict_id")
        if v.get("applied"):
            applied_true += 1
        else:
            applied_false += 1

        symbol = (v.get("symbol") or "").upper()
        tf_sec = int(v.get("tf_sec") or 0)
        ts_ms = int(v.get("ts_ms") or 0)
        ent = (v.get("entry_verdict") or "").upper()

        if ent not in ("OPEN_LONG", "OPEN_SHORT"):
            skipped.append(Skip(vid, None, "non_entry_verdict",
                                {"entry_verdict": ent, "symbol": symbol}))
            continue

        if tf_sec <= 0 or ts_ms <= 0:
            skipped.append(Skip(vid, None, "invalid_bar_close_ts",
                                {"tf_sec": tf_sec, "ts_ms": ts_ms}))
            continue

        if not _assert_bar_close_invariant(ts_ms, tf_sec):
            skipped.append(Skip(vid, None, "invalid_bar_close_ts",
                                {"tf_sec": tf_sec, "ts_ms": ts_ms,
                                 "expected_mod": tf_sec * 1000 - 1,
                                 "actual_mod": ts_ms % (tf_sec * 1000)}))
            continue

        plans = shadow_plans.get(vid or "", [])
        if not plans:
            skipped.append(Skip(vid, None, "missing_shadow_entry_plan",
                                {"symbol": symbol}))
            continue

        plan, total_n, actionable_n = select_canonical_plan(plans)
        if plan is None:
            skipped.append(Skip(vid, None, "no_actionable_plan",
                                {"symbol": symbol, "candidate_count": total_n}))
            continue

        # Side / TP/SL sanity (post-select):
        if plan.entry_side not in ("BUY", "SELL"):
            skipped.append(Skip(vid, None, "invalid_side",
                                {"side": plan.entry_side}))
            continue
        if not (plan.tp_price and plan.sl_price and plan.limit_price):
            skipped.append(Skip(vid, None, "missing_tp_or_sl",
                                {"symbol": symbol}))
            continue

        key = CorrelationKey(STRATEGY_ID, symbol, tf_sec, ts_ms)
        key_tuple = dataclasses.astuple(key)
        if key_tuple in seen_keys:
            # Hard fail signal — accumulate, decide at end.
            duplicates.append({
                "correlation_key": dataclasses.asdict(key),
                "verdict_id_first": seen_keys[key_tuple]["verdict_id"],
                "verdict_id_second": vid,
            })
            skipped.append(Skip(vid, dataclasses.asdict(key),
                                "duplicate_correlation_key",
                                {"first_verdict_id": seen_keys[key_tuple]["verdict_id"]}))
            continue
        seen_keys[key_tuple] = {"verdict_id": vid, "plan_id": plan.plan_id}

        horizon_ms = horizon_bars * tf_sec * 1000
        if ts_ms + horizon_ms > now_ms:
            skipped.append(Skip(vid, dataclasses.asdict(key),
                                "horizon_extends_past_current_time",
                                {"bar_close_ts": ts_ms, "horizon_ms": horizon_ms,
                                 "now_ms": now_ms}))
            continue

        sym_candles = candles_by_symbol.get(symbol, [])
        window = candles_in_window(sym_candles, ts_ms, ts_ms + horizon_ms)
        # We need at least the first eligible 1m candle.
        if not window or window[0].open_time_ms != ts_ms + 1:
            # Either no candles at all, or first eligible candle missing
            # (gap right after decision). Fail-closed.
            skipped.append(Skip(vid, dataclasses.asdict(key),
                                "missing_candle_coverage",
                                {"symbol": symbol,
                                 "expected_first_open_ms": ts_ms + 1,
                                 "got_first_open_ms": window[0].open_time_ms if window else None,
                                 "window_len": len(window)}))
            continue

        result = replay_plan_on_candles(plan, window, mat_cfg.fill_model)
        selected += 1

        # Envelope / regime (sidecar only).
        env = envelopes.get(v.get("envelope_id") or "")
        regime = env.get("regime") if env else None
        regime_conf = env.get("regime_confidence") if env else None
        regime_ts = env.get("regime_ts_ms") if env else None
        stale_bars: Optional[int] = None
        if regime_ts is not None:
            stale_bars = max(0, (ts_ms - int(regime_ts)) // (tf_sec * 1000))

        # USD ROI (optional, sidecar only).
        notional_sidecar: Optional[dict[str, Any]] = None
        roi_sidecar: Optional[dict[str, Any]] = None
        if economics is not None and precision_map is not None and result.matched_trade:
            nr = derive_notional_for_outcome(
                symbol=symbol,
                entry_price=result.entry_price,
                economics=economics,
                precision_map=precision_map,
            )
            notional_sidecar = nr.to_manifest_dict()
            if nr.ok and result.exit_price is not None:
                side = "LONG" if plan.entry_side == "BUY" else "SHORT"
                roi = compute_roi_usd(
                    entry_price=result.entry_price,
                    exit_price=result.exit_price,
                    qty=nr.normalized_qty,
                    side=side,
                    leverage=nr.leverage,
                )
                roi_sidecar = {
                    "roi_usd_absolute": str(roi["roi_usd_absolute"]),
                    "roi_usd_margin": (
                        str(roi["roi_usd_margin"]
                            ) if roi["roi_usd_margin"] is not None else None
                    ),
                }

        outcomes.append(Outcome(
            strategy_id=STRATEGY_ID,
            symbol=symbol,
            tf_sec=tf_sec,
            bar_close_ts=ts_ms,
            matched_trade=result.matched_trade,
            entry_price=result.entry_price,
            exit_price=result.exit_price,
            exit_ts_ms=result.exit_ts_ms,
        ))

        diagnostics.append(Diagnostic(
            verdict_id=vid or "",
            correlation_key=dataclasses.asdict(key),
            plan_id=plan.plan_id,
            chosen_tier=plan.confidence_tier,
            candidate_plan_count=total_n,
            actionable_candidate_count=actionable_n,
            entry_side=plan.entry_side,
            limit_price=plan.limit_price,
            tp_price=plan.tp_price,
            sl_price=plan.sl_price,
            confidence=plan.confidence,
            fill_model=mat_cfg.fill_model,
            matched_trade=result.matched_trade,
            entry_price=result.entry_price,
            exit_price=result.exit_price,
            exit_ts_ms=result.exit_ts_ms,
            exit_classification=result.exit_classification,
            ambiguity_policy=result.ambiguity_policy,
            regime=regime,
            regime_confidence=regime_conf,
            regime_ts_ms=regime_ts,
            regime_stale_bars=stale_bars,
            horizon_ms=horizon_ms,
            notional_sidecar=notional_sidecar,
            roi_usd=roi_sidecar,
            mfe=result.mfe,
            mae=result.mae,
        ))

    return MaterializerResult(
        outcomes=outcomes,
        skipped=skipped,
        diagnostics=diagnostics,
        duplicate_correlation_keys=duplicates,
        applied_true_count=applied_true,
        applied_false_count=applied_false,
        verdict_total=len(verdicts),
        selected_plan_count=selected,
    )


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _sort_outcomes(outcomes: list[Outcome]) -> list[Outcome]:
    return sorted(outcomes, key=lambda o: (o.strategy_id, o.symbol, o.tf_sec, o.bar_close_ts))


def build_outcomes_json(outcomes: list[Outcome]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "outcomes": [o.to_dict() for o in _sort_outcomes(outcomes)],
    }


def validate_outcomes_json(payload: dict) -> list[str]:
    if Draft7Validator is None:
        return ["jsonschema package not available"]
    schema = json.loads(OUTCOME_SCHEMA_PATH.read_text(encoding="utf-8"))
    v = Draft7Validator(schema)
    return [f"{list(e.absolute_path)}: {e.message}" for e in v.iter_errors(payload)]


def write_outcomes_file(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, indent=2,
                      ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def write_jsonl(rows: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(
    sim_cfg: SimulatorConfig,
    mat_cfg: MaterializerConfig,
    result: MaterializerResult,
    sim_config_path: Path,
    outcomes_path: Path,
    economics_present: bool,
) -> dict:
    pointers = manifest_pointer_strings(economics_present=economics_present)
    by_symbol: dict[str, dict[str, int]] = {}
    by_classification: dict[str, int] = {}
    for d in result.diagnostics:
        sym = d.correlation_key["symbol"]
        b = by_symbol.setdefault(sym, {
            "outcomes": 0, "matched_true": 0, "matched_false": 0,
            "tp": 0, "sl": 0, "timeout": 0, "ambiguous": 0,
        })
        b["outcomes"] += 1
        if d.matched_trade:
            b["matched_true"] += 1
        else:
            b["matched_false"] += 1
        b[{
            "FILLED_TP": "tp", "FILLED_SL": "sl", "TIMEOUT": "timeout",
            "AMBIGUOUS_TP_SL_SAME_CANDLE": "ambiguous", "NO_FILL": "matched_false",
        }.get(d.exit_classification, "matched_false")] += 1
        by_classification[d.exit_classification] = (
            by_classification.get(d.exit_classification, 0) + 1
        )

    skip_summary: dict[str, int] = {}
    for s in result.skipped:
        skip_summary[s.skip_reason] = skip_summary.get(s.skip_reason, 0) + 1

    return {
        "schema_version": "1",
        "generated_at_utc_ms": _now_ms(mat_cfg),
        "materializer_version": "pkg1.v1",
        "simulator_config_path": str(sim_config_path).replace("\\", "/"),
        "outcomes_path": str(outcomes_path).replace("\\", "/"),
        "outcomes_sha256": _file_sha256(outcomes_path) if outcomes_path.is_file() else None,
        "fee_source": "config/judge_simulator.yaml#judge_simulator.fee_per_cycle_bps",
        "slippage_source": "config/judge_simulator.yaml#judge_simulator.slippage_pct",
        "fee_per_cycle_bps_value": float(sim_cfg.fee_per_cycle_bps),
        "slippage_pct_value": float(sim_cfg.slippage_pct),
        "fee_slippage_applied_by_materializer": False,
        "notional_mode": pointers["notional_mode"],
        "notional_pointers": pointers,
        "notional_resolved": (
            sim_cfg.economics.model_dump() if sim_cfg.economics is not None else None
        ),
        "canonical_plan_selection_rule": {
            "version": 1,
            "filter": ["actionable=true", "suppressed=false", "tp/sl/limit present", "side in BUY/SELL"],
            "tier_priority": ["high", "medium", "low"],
            "tiebreak": "confidence desc, plan_id asc",
        },
        "fill_model": {
            "name": mat_cfg.fill_model,
            "limitations": (
                "optimistic_touch: LONG fills if low<=limit, SHORT fills if high>=limit. "
                "No spread/tick adjustment. No partial fills. Same-candle TP+SL resolved as worst-case (SL)."
            ),
        },
        "exit_model": {
            "horizon_bars": mat_cfg.horizon_bars,
            "ambiguity_policy": "worst_case",
            "timeout_exit": "last_candle_close_within_horizon",
        },
        "bar_close_invariant": "ts_ms % (tf_sec*1000) == tf_sec*1000 - 1",
        "no_future_leakage_rule": "first eligible candle open_time_ms > bar_close_ts",
        "applied_true_count": result.applied_true_count,
        "applied_false_count": result.applied_false_count,
        "verdict_total": result.verdict_total,
        "outcomes_count": len(result.outcomes),
        "skipped_count": len(result.skipped),
        "duplicate_correlation_key_count": len(result.duplicate_correlation_keys),
        "skip_summary": skip_summary,
        "exit_classification_summary": by_classification,
        "per_symbol_summary": by_symbol,
        "strategy_id": STRATEGY_ID,
    }


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_simulator_config(path: Path) -> SimulatorConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    section = raw.get("judge_simulator") or raw
    return SimulatorConfig(**section)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="PKG-1 Judge outcomes materializer.",
    )
    p.add_argument("--judge-log-dir", type=Path,
                   default=Path("logs/judge_experts"))
    p.add_argument("--raw-1m-dir", type=Path,
                   default=Path("data/raw_binance_klines_1m"))
    p.add_argument("--recorder-1m-dir", type=Path,
                   default=Path("data/recorder_backfill_1m"))
    p.add_argument("--simulator-config", type=Path,
                   default=Path("config/judge_simulator.yaml"))
    p.add_argument("--outcomes-path", type=Path,
                   default=Path("data/simulator/outcomes.json"))
    p.add_argument("--manifest-path", type=Path,
                   default=Path("data/simulator/outcomes_manifest.json"))
    p.add_argument("--skipped-path", type=Path,
                   default=Path("data/simulator/outcomes_skipped.jsonl"))
    p.add_argument("--diagnostics-path", type=Path,
                   default=Path("data/simulator/outcomes_diagnostics.jsonl"))
    p.add_argument("--report-path", type=Path,
                   default=Path("reports/PKG_1_JUDGE_OUTCOMES_MATERIALIZER_REPORT.md"))
    p.add_argument("--horizon-bars", type=int, default=DEFAULT_HORIZON_BARS)
    p.add_argument(
        "--fill-model", choices=["optimistic_touch"], default="optimistic_touch")
    p.add_argument("--now-utc-ms", type=int, default=None,
                   help="Override current time (UTC ms) for deterministic future-tail accounting.")
    p.add_argument("--write-report", action="store_true", default=False)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def run(args: argparse.Namespace) -> dict:
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    sim_cfg = load_simulator_config(args.simulator_config)
    economics_present = sim_cfg.economics is not None
    precision_map: Optional[dict[str, InstrumentPrecision]] = None
    if economics_present:
        precision_map = load_instrument_precision_map(
            sim_cfg.economics.instruments_config_path
        )

    LOG.info("Loading verdicts from %s", args.judge_log_dir)
    verdicts = load_verdicts(args.judge_log_dir)
    LOG.info("Loaded %d verdicts", len(verdicts))

    LOG.info("Loading shadow_entry_plan rows")
    plans = load_shadow_plans(args.judge_log_dir)
    LOG.info("Indexed plans for %d verdict ids", len(plans))

    LOG.info("Loading envelopes")
    envelopes = load_envelopes(args.judge_log_dir)
    LOG.info("Indexed %d envelopes", len(envelopes))

    LOG.info("Loading candles")
    raw = load_raw_binance_candles(args.raw_1m_dir)
    rec = load_recorder_candles(args.recorder_1m_dir)
    candles = merge_candle_sources(raw, rec)
    LOG.info("Loaded candles for symbols: %s",
             ", ".join(f"{s}:{len(c)}" for s, c in sorted(candles.items())))

    mat_cfg = MaterializerConfig(
        horizon_bars=args.horizon_bars,
        fill_model=args.fill_model,
        now_utc_ms=args.now_utc_ms,
    )
    result = materialize(verdicts, plans, envelopes,
                         candles, sim_cfg, mat_cfg, precision_map)

    if result.duplicate_correlation_keys:
        # Hard fail BEFORE writing outcomes.json.
        msg = (
            f"PKG-1 HARD FAIL: {len(result.duplicate_correlation_keys)} duplicate "
            f"CorrelationKey(s) detected — refusing to write outcomes.json."
        )
        # Still write skipped & diagnostics for forensics.
        write_jsonl(
            (dataclasses.asdict(s) for s in result.skipped), args.skipped_path,
        )
        write_jsonl(
            (dataclasses.asdict(d)
             for d in result.diagnostics), args.diagnostics_path,
        )
        # Also dump duplicates to manifest path for visibility.
        args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_path.write_text(json.dumps(
            {"error": "duplicate_correlation_keys",
             "duplicates": result.duplicate_correlation_keys},
            indent=2,
        ) + "\n", encoding="utf-8")
        LOG.error(msg)
        raise SystemExit(2)

    payload = build_outcomes_json(result.outcomes)
    errors = validate_outcomes_json(payload)
    if errors:
        LOG.error("outcomes.json failed schema validation: %s", errors[:5])
        # Write skip ledger so operator can debug.
        write_jsonl(
            (dataclasses.asdict(s) for s in result.skipped), args.skipped_path,
        )
        write_jsonl(
            (dataclasses.asdict(d)
             for d in result.diagnostics), args.diagnostics_path,
        )
        raise SystemExit(3)

    write_outcomes_file(payload, args.outcomes_path)
    write_jsonl((dataclasses.asdict(s)
                for s in result.skipped), args.skipped_path)
    write_jsonl((dataclasses.asdict(d)
                for d in result.diagnostics), args.diagnostics_path)
    manifest = build_manifest(
        sim_cfg=sim_cfg,
        mat_cfg=mat_cfg,
        result=result,
        sim_config_path=args.simulator_config,
        outcomes_path=args.outcomes_path,
        economics_present=economics_present,
    )
    args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    LOG.info(
        "Done. outcomes=%d, skipped=%d, duplicates=%d, applied_true=%d, applied_false=%d",
        len(result.outcomes), len(result.skipped),
        len(result.duplicate_correlation_keys),
        result.applied_true_count, result.applied_false_count,
    )
    return {
        "outcomes": len(result.outcomes),
        "skipped": len(result.skipped),
        "manifest": str(args.manifest_path),
        "duplicates": len(result.duplicate_correlation_keys),
    }


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        run(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
