"""
MemoryShield — State-Familiarity Attenuation (Doctrine v2.6, P0-3.1).

Tracks coarse-grained market-state visits via exponentially-decayed
counters.  Unknown/rare states get lower multipliers; well-known
states pass through at 1.0.

State hash: "{REGIME}|{VOL}|{STR}|{QUAL}" (~54 buckets).
Storage: O(1) per state — exponential decay counter, no unbounded lists.

Idempotency:
  A visit is recorded **at most once per (state_hash, bar_ts)**.
  Repeated evaluate() calls on the same bar do NOT inflate counters.

Persistence modes:
  storage_path=None  → RAM-only (safe for backtest & default).
  storage_path=<path> → atomic JSON persistence, throttled by
                        *flush_interval_sec* (default 60 s).
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set, Tuple

from apps.reference.domains.decision_making.shields.base import (
    BaseShield,
    ShieldResult,
)

logger = logging.getLogger(__name__)

# Maximum size of the idempotency dedup set (most recent bar keys kept).
_DEDUP_CAP = 512


# ---------------------------------------------------------------------------
# Bucket helpers  (use real FE feature keys)
# ---------------------------------------------------------------------------
def _regime_bucket(regime: Any) -> str:
    """Map canonical regime string → UP / DOWN / FLAT."""
    r = str(regime).upper() if regime is not None else ""
    if r in ("TREND_UP", "UP"):
        return "UP"
    if r in ("TREND_DOWN", "DOWN"):
        return "DOWN"
    return "FLAT"


def _vol_bucket_atr_pct(atr_pct: float) -> str:
    """Bucket by ATR-% of price (FE: ``features["volatility"]["atr_pct"]``).

    Boundaries calibrated to BTCUSDT 5m bars:
      LOW  : atr_pct < 0.002  (< 0.2 % of price)
      NORM : 0.002 .. 0.005
      HIGH : > 0.005
    """
    if atr_pct < 0.002:
        return "LOW"
    if atr_pct > 0.005:
        return "HIGH"
    return "NORM"


def _vol_bucket_state(vol_state: float) -> str:
    """Fallback bucket via normalised volatility_state ∈ [0, 1]."""
    if vol_state < 0.3:
        return "LOW"
    if vol_state > 0.7:
        return "HIGH"
    return "NORM"


def _strength_bucket(pillar_op: float) -> str:
    """Bucket by ``|pillar_operator|`` (ADX-weighted LinReg slope, [-1, +1]).

    <0.3 → WEAK,  0.3..0.7 → MID,  >0.7 → STRONG.
    """
    v = abs(pillar_op)
    if v < 0.3:
        return "WEAK"
    if v > 0.7:
        return "STRONG"
    return "MID"


def _quality_bucket(pillar_strat: float) -> str:
    """Bucket by ``pillar_strategist`` (long-term regime quality, [-1, +1]).

    |val| > 0.5 → CLEAN (consistent direction), else DIRTY.
    """
    if abs(pillar_strat) > 0.5:
        return "CLEAN"
    return "DIRTY"


# ---------------------------------------------------------------------------
# Decayed-counter state entry
# ---------------------------------------------------------------------------
class _StateEntry:
    """Compact exponentially-decayed visit counter."""
    __slots__ = ("visits", "last_ts")

    def __init__(self, visits: float = 0.0, last_ts: int = 0):
        self.visits = visits
        self.last_ts = last_ts

    def effective(self, now_ts: int, decay_rate: float) -> float:
        """Return decayed effective visits at *now_ts* (seconds)."""
        if self.last_ts <= 0 or now_ts <= self.last_ts:
            return self.visits
        days = (now_ts - self.last_ts) / 86400.0
        return self.visits * (decay_rate ** days)

    def record(self, now_ts: int, decay_rate: float) -> None:
        """Add one visit, decaying the old count first."""
        eff = self.effective(now_ts, decay_rate)
        self.visits = eff + 1.0
        self.last_ts = now_ts

    def to_dict(self) -> dict:
        return {"visits": self.visits, "last_ts": self.last_ts}

    @classmethod
    def from_dict(cls, d: dict) -> "_StateEntry":
        return cls(visits=float(d.get("visits", 0.0)),
                   last_ts=int(d.get("last_ts", 0)))


# ---------------------------------------------------------------------------
# MemoryShield
# ---------------------------------------------------------------------------
class MemoryShield(BaseShield):
    """State-familiarity shield (Doctrine v2.6, P0-3.1).

    Parameters
    ----------
    decay_rate : float
        Per-day exponential decay for visit counts (default 0.95).
    max_states : int
        LRU cap on tracked states (default 200).
    unknown_threshold, exploring_threshold : float
        Effective-visit boundaries for familiarity tiers.
    unknown_multiplier, exploring_multiplier, known_multiplier : float
        Attenuation factors for each tier.
    storage_path : str | None
        JSON path for LIVE persistence.  ``None`` → RAM-only (default).
        Callers MUST set this to ``None`` or omit it in backtest to
        guarantee no cross-run leakage and no filesystem I/O.
    flush_interval_sec : float
        Minimum seconds between disk flushes (default 60).
    """

    def __init__(
        self,
        *,
        decay_rate: float = 0.95,
        max_states: int = 200,
        unknown_threshold: float = 10.0,
        exploring_threshold: float = 50.0,
        unknown_multiplier: float = 0.6,
        exploring_multiplier: float = 0.8,
        known_multiplier: float = 1.0,
        storage_path: Optional[str] = None,
        flush_interval_sec: float = 60.0,
        clock: Optional["Clock"] = None,
    ):
        self._decay_rate = decay_rate
        self._max_states = max(1, max_states)
        self._unknown_thr = float(unknown_threshold)
        self._exploring_thr = float(exploring_threshold)
        self._unknown_mult = max(0.0, min(1.0, unknown_multiplier))
        self._exploring_mult = max(0.0, min(1.0, exploring_multiplier))
        self._known_mult = max(0.0, min(1.0, known_multiplier))
        self._storage_path: Optional[str] = storage_path or None
        self._flush_interval = max(1.0, flush_interval_sec)

        from apps.reference.core.time.clock import LiveClock
        self._clock = clock or LiveClock()

        # LRU-ordered state store: hash → _StateEntry
        self._states: OrderedDict[str, _StateEntry] = OrderedDict()

        # Idempotency: set of (state_hash, bar_ts) already recorded
        self._seen_keys: OrderedDict[Tuple[str, int], None] = OrderedDict()

        # Persistence throttle
        self._dirty = False
        self._last_flush_wall: float = self._clock.monotonic()

        # Load persisted state (LIVE only)
        if self._storage_path:
            self._load()

    # ------------------------------------------------------------------
    # BaseShield protocol
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return "MEMORY"

    def evaluate(
        self,
        symbol: str,
        features: Dict[str, Any],
        pillar_sum: float,
        raw_exposure: float,
    ) -> ShieldResult:
        """Compute familiarity multiplier and record visit (idempotent)."""
        now_ts = self._extract_ts(features)
        state_hash, missing = self._get_state_hash(features)

        # --- missing features → deterministic UNKNOWN (pure-read) ----
        if missing:
            reason = f"MEMORY:MISSING_FEATURES({missing})"
            logger.debug("[%s] %s → mult=%.2f", symbol, reason, self._unknown_mult)
            return ShieldResult(
                multiplier=self._unknown_mult,
                reasons=[reason],
                shield_name=self.name,
                details={"missing_keys": missing},
            )

        # --- decay + read effective visits ----------------------------
        entry = self._states.get(state_hash)
        if entry is None:
            ev = 0.0
        else:
            ev = entry.effective(now_ts, self._decay_rate)

        # --- multiplier mapping (Doctrine v2.6) -----------------------
        if ev < self._unknown_thr:
            mult = self._unknown_mult
            tag = "UNKNOWN"
        elif ev < self._exploring_thr:
            mult = self._exploring_mult
            tag = "EXPLORING"
        else:
            mult = self._known_mult
            tag = "KNOWN"

        # Defensive clamp
        clamped = max(0.0, min(1.0, mult))
        if clamped != mult:
            logger.warning("MEMORY: clamped mult %.4f→%.4f for %s", mult, clamped, state_hash)
            mult = clamped

        reason = f"MEMORY:{tag}(ev={ev:.1f})"
        logger.debug("[%s] %s hash=%s → mult=%.2f", symbol, reason, state_hash, mult)

        return ShieldResult(
            multiplier=mult,
            reasons=[reason],
            shield_name=self.name,
            details={"memory_state_hash": state_hash},
        )

    # ------------------------------------------------------------------
    # Public write-path (Fix BUG-2)
    # ------------------------------------------------------------------
    def record_visit(
        self,
        symbol: str,
        features: Dict[str, Any],
        bar_close_ts: Optional[int] = None,
        state_hash: Optional[str] = None,
    ) -> None:
        """Record a visit for the current state (idempotent per bar).

        MUST be called only when a valid trading intent is formed
        (or at end of bar processing if tracking all observed states).
        """
        if state_hash is None:
            state_hash, _ = self._get_state_hash(features)
        
        now_ts = bar_close_ts or self._extract_ts(features)
        self._maybe_record_visit(state_hash, now_ts)

    # ------------------------------------------------------------------
    # State hashing — uses real FE feature keys
    # ------------------------------------------------------------------
    @staticmethod
    def _get_state_hash(features: Dict[str, Any]) -> tuple[str, list[str]]:
        """Return ``(hash_str, missing_fields)``.

        Feature resolution order matches FE contract:
          regime      → ``features["regime"]`` (injected by handler)
          vol         → ``features["volatility"]["atr_pct"]``, fallback
                        ``features["volatility_state"]``
          strength    → ``features["pillar_operator"]``
          quality     → ``features["pillar_strategist"]``
        """
        missing: list[str] = []

        # -- Regime (injected by handler from EVT:REGIME_DETECTED) -----
        regime_raw = features.get("regime")
        if regime_raw is None:
            missing.append("regime")
        regime = _regime_bucket(regime_raw)

        # -- Volatility ------------------------------------------------
        vol = "UNKNOWN"
        vol_block = features.get("volatility")
        atr_pct = None
        if isinstance(vol_block, dict):
            atr_pct = vol_block.get("atr_pct")
        if atr_pct is not None:
            try:
                vol = _vol_bucket_atr_pct(float(atr_pct))
            except (TypeError, ValueError):
                atr_pct = None
        if atr_pct is None:
            # Fallback: normalised volatility_state (0-1)
            vs = features.get("volatility_state")
            if vs is not None:
                try:
                    vol = _vol_bucket_state(float(vs))
                except (TypeError, ValueError):
                    pass
                else:
                    vs = None  # suppress missing
            if vs is None and atr_pct is None and vol == "UNKNOWN":
                missing.append("volatility")

        # -- Strength (ADX-weighted signal) ----------------------------
        po_raw = features.get("pillar_operator")
        if po_raw is None:
            missing.append("pillar_operator")
            strength = "UNKNOWN"
        else:
            try:
                strength = _strength_bucket(float(po_raw))
            except (TypeError, ValueError):
                missing.append("pillar_operator")
                strength = "UNKNOWN"

        # -- Quality (long-horizon regime quality) ---------------------
        ps_raw = features.get("pillar_strategist")
        if ps_raw is None:
            # Graceful degradation: quality unknown but still usable
            missing.append("pillar_strategist")
            qual = "UNKNOWN"
        else:
            try:
                qual = _quality_bucket(float(ps_raw))
            except (TypeError, ValueError):
                missing.append("pillar_strategist")
                qual = "UNKNOWN"

        h = f"{regime}|{vol}|{strength}|{qual}"
        return h, missing

    # ------------------------------------------------------------------
    # Idempotent visit recording (max 1 per bar per state)
    # ------------------------------------------------------------------
    def _maybe_record_visit(self, state_hash: str, bar_ts: int) -> None:
        """Record visit only if (state_hash, bar_ts) not yet seen."""
        key = (state_hash, bar_ts)
        if key in self._seen_keys:
            return  # idempotent: already counted for this bar
        # Mark as seen (bounded dedup set)
        self._seen_keys[key] = None
        while len(self._seen_keys) > _DEDUP_CAP:
            self._seen_keys.popitem(last=False)
        # Actual recording
        self._record_visit(state_hash, bar_ts)

    def _record_visit(self, state_hash: str, now_ts: int) -> None:
        entry = self._states.get(state_hash)
        if entry is None:
            entry = _StateEntry()
            self._states[state_hash] = entry
        entry.record(now_ts, self._decay_rate)
        # Move to end (LRU touch)
        self._states.move_to_end(state_hash)
        # Evict oldest if over capacity
        while len(self._states) > self._max_states:
            self._states.popitem(last=False)
        # Mark dirty for throttled persistence
        self._dirty = True
        self._maybe_flush()

    # ------------------------------------------------------------------
    # Timestamp extraction
    # ------------------------------------------------------------------
    def _extract_ts(self, features: Dict[str, Any]) -> int:
        """Best-effort timestamp (seconds) from features, fallback wall clock.

        Handler MUST inject ``bar_close_ts`` into features for determinism.
        """
        for key in ("bar_close_ts", "now_ts_ms", "ts_ms"):
            val = features.get(key)
            if val is not None:
                try:
                    v = int(val)
                    # Convert ms → s if value looks like milliseconds
                    return v // 1000 if v > 1_700_000_000_000 else v
                except (TypeError, ValueError):
                    continue
        return int(self._clock.now_sec())

    # ------------------------------------------------------------------
    # Persistence (LIVE only, atomic write, throttled)
    # ------------------------------------------------------------------
    def _maybe_flush(self) -> None:
        """Flush to disk only if dirty AND flush interval elapsed."""
        if not self._storage_path or not self._dirty:
            return
        now = self._clock.monotonic()
        if now - self._last_flush_wall < self._flush_interval:
            return
        self._save()

    def flush(self) -> None:
        """Force flush (call on shutdown / end-of-backtest)."""
        if self._storage_path and self._dirty:
            self._save()

    def _save(self) -> None:
        if not self._storage_path:
            return
        try:
            data = {k: v.to_dict() for k, v in self._states.items()}
            dir_name = os.path.dirname(self._storage_path) or "."
            fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, self._storage_path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            self._dirty = False
            self._last_flush_wall = self._clock.monotonic()
        except Exception as exc:
            logger.error("MEMORY: save failed: %s", exc)

    def _load(self) -> None:
        if not self._storage_path or not os.path.isfile(self._storage_path):
            return
        try:
            with open(self._storage_path, "r") as f:
                raw = json.load(f)
            for k, v in raw.items():
                self._states[k] = _StateEntry.from_dict(v)
            logger.info("MEMORY: loaded %d states from %s", len(self._states), self._storage_path)
        except Exception as exc:
            logger.error("MEMORY: load failed (starting fresh): %s", exc)
            self._states.clear()

    # ------------------------------------------------------------------
    # Introspection helpers (for callers / debugging)
    # ------------------------------------------------------------------
    def get_effective_visits(self, state_hash: str, now_ts: Optional[int] = None) -> float:
        """Return current effective visits for a state (for testing/debugging)."""
        entry = self._states.get(state_hash)
        if entry is None:
            return 0.0
        ts = now_ts if now_ts is not None else int(self._clock.now_sec())
        return entry.effective(ts, self._decay_rate)

    def state_count(self) -> int:
        """Number of tracked states."""
        return len(self._states)
