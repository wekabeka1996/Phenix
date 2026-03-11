"""
Feature Mirror Writer
=====================

Plugin for the main Aurora process that writes a canonical
alpha_input_v1.jsonl stream for standalone alpha_search consumption.

Subscribes to:
- EVT:FEATURES_CALCULATED: features + symbol + tf_sec
- EVT:REGIME_DETECTED: current regime per symbol

Correlates events by symbol to produce complete snapshots with regime context.

IMPORTANT: This is the ONLY file that interacts with apps/reference/main.py.
It's an optional plugin ΓÇö the standalone domain works with replay without it.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

LOG = logging.getLogger(__name__)


class FeatureMirrorWriter:
    """
    Mirror writer plugin that subscribes to main Aurora event bus
    and writes alpha_input_v1.jsonl for standalone alpha_search.

    Usage in main.py:
        mirror = FeatureMirrorWriter(event_bus=fsm, symbols=["BTCUSDT", "ETHUSDT"])

    The writer is stateless beyond caches. Every EVT:FEATURES_CALCULATED produces
    a line in the output JSONL with the latest known regime for that symbol.
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
            self._bus.listen("EVT:REGIME_DETECTED", self._on_regime)
            LOG.debug("FeatureMirrorWriter listeners registered")

    def _on_features(self, event: Any) -> None:
        """
        Handle EVT:FEATURES_CALCULATED.

        Extracts features and writes a complete alpha_input_v1 record
        with the latest cached regime for the symbol.
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

        # bar_close_ts from bar or payload
        bar = payload.get("bar") or {}
        bar_close_ts = (
            bar.get("close_ts")
            or bar.get("ts")
            or payload.get("bar_close_ts")
            or ts
        )

        # Extract price from features
        price = self._extract_price(features)

        # Build alpha_input_v1 record
        record = {
            "ts_ms": ts,
            "symbol": symbol,
            "tf_sec": tf_sec,
            "bar_close_ts": bar_close_ts,
            "price": price,
            "features": features,
            "regime": self._regime_cache.get(symbol, "DEFAULT"),
            "warmup_status": self._warmup_cache.get(symbol, {}),
            "source_verb": "FEATURES_CALCULATED",
            "source_trace_id": payload.get("trace_id", payload.get("rid", "")),
        }

        self._write_record(record)
        self._snapshots_written += 1

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

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "snapshots_written": self._snapshots_written,
            "snapshots_skipped": self._snapshots_skipped,
            "regime_cache": dict(self._regime_cache),
            "output_path": str(self._output_path),
        }
