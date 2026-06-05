"""
Feature Mirror Writer
=====================

Plugin for the main Aurora process that writes a canonical
alpha_input_v1.jsonl stream for standalone alpha_search consumption.

Subscribes to:
- EVT:FEATURES_CALCULATED: base feature plane + symbol + tf_sec
- EVT:TA_FEATURES_CALCULATED: supplemental TA feature plane for the same bar
- EVT:REGIME_DETECTED: current regime per symbol

Correlates events by symbol + timeframe + bar_close_ts to produce complete
snapshots with regime context and explicit TA warmup state.

IMPORTANT: This is the ONLY file that interacts with apps/reference/main.py.
It's an optional plugin - the standalone domain works with replay without it.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from apps.reference.domains.ta_features.contracts import extract_ta_feature_vector

LOG = logging.getLogger(__name__)


class FeatureMirrorWriter:
    """
    Mirror writer plugin that subscribes to main Aurora event bus
    and writes alpha_input_v1.jsonl for standalone alpha_search.

    Usage in main.py:
        mirror = FeatureMirrorWriter(event_bus=fsm, symbols=["BTCUSDT", "ETHUSDT"])

    The writer is stateless beyond caches. A line is written only when the base
    FEATURES_CALCULATED payload and the TA supplement for the same bar are both
    available, so ta_ensemble can consume the same alpha_input stream as aurora.
    """

    def __init__(
        self,
        event_bus: Any,
        output_path: Optional[Path] = None,
        symbols: Optional[List[str]] = None,
    ):
        self._bus = event_bus
        self._output_path = Path(
            output_path or "logs/alpha_input/alpha_input_v1.jsonl"
        )
        self._symbols: Optional[Set[str]] = set(symbols) if symbols else None

        # Caches for correlation
        self._regime_cache: Dict[str, str] = {}  # symbol -> last known regime
        # symbol -> warmup flags
        self._warmup_cache: Dict[str, Dict[str, bool]] = {}
        # (symbol, tf_sec, bar_close_ts) -> pending base snapshot pieces
        self._feature_cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
        # (symbol, tf_sec, bar_close_ts) -> pending TA supplement
        self._ta_cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}

        # Stats
        self._snapshots_written = 0
        self._snapshots_skipped = 0

        # Ensure output directory
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        # Register listeners
        self._register()

        LOG.info(
            f"FeatureMirrorWriter initialized: "
            f"output={self._output_path}, "
            f"symbols={self._symbols or 'ALL'}"
        )

    def _register(self) -> None:
        """Subscribe to required events on the main event bus."""
        if hasattr(self._bus, "listen"):
            self._bus.listen("EVT:FEATURES_CALCULATED", self._on_features)
            self._bus.listen("EVT:TA_FEATURES_CALCULATED", self._on_ta_features)
            self._bus.listen("EVT:REGIME_DETECTED", self._on_regime)
            LOG.debug("FeatureMirrorWriter listeners registered")

    def _on_features(self, event: Any) -> None:
        """
        Handle EVT:FEATURES_CALCULATED.

        Extracts the base feature plane and caches it until the matching
        EVT:TA_FEATURES_CALCULATED payload arrives for the same bar.
        """
        payload = self._extract_payload(event)
        if not payload:
            return

        symbol = payload.get("symbol", "")
        if not symbol:
            return

        # Symbol filter
        if self._symbols and symbol not in self._symbols:
            self._snapshots_skipped += 1
            return

        features = payload.get("features", {})
        if not features:
            self._snapshots_skipped += 1
            return

        tf_sec = payload.get("tf_sec", 300)
        # Only write bar-close events (tf_sec >= 60).
        # Tick-level events (tf_sec=0) lack bar-aggregated TA indicators
        # (bb_position, rsi_14, bb_width, stoch_k, etc.) which ta_ensemble
        # requires. Replaying tick records causes CMD:PROCESS_STRATEGY with
        # tf_sec=0 and a spurious "missing required features" warning.
        # Mirrors the identical gate in feature_engineering.py:1370 and
        # aurora_handler.py:600.
        if not tf_sec or tf_sec < 60:
            self._snapshots_skipped += 1
            return
        ts = payload.get("ts", 0) or int(time.time() * 1000)

        bar_close_ts = self._bar_close_ts(payload, ts)

        # Extract price from features
        price = self._extract_price(features)

        key = self._snapshot_key(symbol, tf_sec, bar_close_ts)
        self._feature_cache[key] = {
            "ts_ms": ts,
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
            "price": price,
            "features": dict(features),
            "regime": self._regime_cache.get(symbol, "DEFAULT"),
            "warmup_status": dict(payload.get("warmup_status") or self._warmup_cache.get(symbol, {})),
            "source_verb": "FEATURES_CALCULATED+TA_FEATURES_CALCULATED",
            "source_trace_id": payload.get("trace_id", payload.get("rid", "")),
        }
        self._maybe_write_snapshot(key)

    def _on_ta_features(self, event: Any) -> None:
        """
        Handle EVT:TA_FEATURES_CALCULATED.

        Cache the TA feature plane and write a merged alpha_input_v1 record once
        the corresponding base FEATURES_CALCULATED payload exists for the same bar.
        """
        payload = self._extract_payload(event)
        if not payload:
            return

        symbol = payload.get("symbol", "")
        if not symbol:
            return

        if self._symbols and symbol not in self._symbols:
            self._snapshots_skipped += 1
            return

        tf_sec = payload.get("tf_sec", 300)
        if not tf_sec or tf_sec < 60:
            self._snapshots_skipped += 1
            return

        ts = payload.get("ts", 0) or int(time.time() * 1000)
        bar_close_ts = self._bar_close_ts(payload, ts)
        key = self._snapshot_key(symbol, tf_sec, bar_close_ts)

        warmup_status = dict(self._warmup_cache.get(symbol, {}))
        warmup_status["ta_features"] = bool(payload.get("is_warm", False))
        self._warmup_cache[symbol] = warmup_status

        self._ta_cache[key] = {
            "features": extract_ta_feature_vector(payload),
            "warmup_status": warmup_status,
            "source_trace_id": payload.get("trace_id", payload.get("rid", "")),
        }
        self._maybe_write_snapshot(key)

    def _on_regime(self, event: Any) -> None:
        """
        Handle EVT:REGIME_DETECTED.

        Cache the latest regime per symbol for inclusion in feature snapshots.
        """
        payload = self._extract_payload(event)
        if not payload:
            return

        symbol = payload.get("symbol", "")
        regime = payload.get("regime", "DEFAULT")

        if symbol:
            self._regime_cache[symbol] = regime
            LOG.debug(f"[{symbol}] Regime updated: {regime}")

    def _maybe_write_snapshot(self, key: Tuple[str, int, int]) -> None:
        feature_record = self._feature_cache.get(key)
        ta_record = self._ta_cache.get(key)
        if feature_record is None or ta_record is None:
            return

        merged_record = dict(feature_record)
        merged_features = dict(feature_record.get("features", {}))
        merged_features.update(ta_record.get("features", {}))
        merged_record["features"] = merged_features

        merged_warmup = dict(feature_record.get("warmup_status", {}))
        merged_warmup.update(ta_record.get("warmup_status", {}))
        merged_record["warmup_status"] = merged_warmup

        if not merged_record.get("price"):
            merged_record["price"] = self._extract_price(merged_features)
        if not merged_record.get("source_trace_id"):
            merged_record["source_trace_id"] = ta_record.get("source_trace_id", "")

        self._write_record(merged_record)
        self._snapshots_written += 1
        self._feature_cache.pop(key, None)
        self._ta_cache.pop(key, None)

    def _write_record(self, record: Dict[str, Any]) -> None:
        """Append a single JSONL record with immediate flush."""
        try:
            with open(self._output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
                f.flush()
        except Exception as e:
            LOG.error(f"Failed to write mirror record: {e}")

    @staticmethod
    def _extract_price(features: Dict[str, Any]) -> float:
        """Extract price from feature dict (best effort)."""
        for key in ("price", "close", "last_price", "mark_price"):
            val = features.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def _extract_payload(event: Any) -> Optional[Dict[str, Any]]:
        """Extract payload from event (compatible with FSMCore and LocalBus)."""
        if isinstance(event, dict):
            return event.get("pld", event)
        if hasattr(event, "pld"):
            return event.pld
        return None

    @staticmethod
    def _bar_close_ts(payload: Dict[str, Any], ts_ms: int) -> int:
        bar = payload.get("bar") or {}
        return int(
            bar.get("close_ts")
            or bar.get("ts")
            or payload.get("bar_close_ts")
            or ts_ms
        )

    @staticmethod
    def _snapshot_key(symbol: str, tf_sec: int, bar_close_ts: int) -> Tuple[str, int, int]:
        return symbol, int(tf_sec), int(bar_close_ts)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "snapshots_written": self._snapshots_written,
            "snapshots_skipped": self._snapshots_skipped,
            "regime_cache": dict(self._regime_cache),
            "pending_feature_snapshots": len(self._feature_cache),
            "pending_ta_snapshots": len(self._ta_cache),
            "output_path": str(self._output_path),
        }
