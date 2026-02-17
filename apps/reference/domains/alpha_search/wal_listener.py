"""
Alpha Score WAL Listener

Listens to EVT:ALPHA_SCORE_CALCULATED and persists to WAL for offline analysis.
Follows fail-closed design: WAL write failures are logged but never block the pipeline.
"""

import logging
from typing import Any

LOG = logging.getLogger(__name__)


class AlphaScoreWalListener:
    """Writes alpha score events to WAL for traceability and offline analysis."""

    def __init__(self, event_bus: Any):
        self.event_bus = event_bus
        self._count = 0
        self._register()

    def _register(self) -> None:
        if hasattr(self.event_bus, "listen"):
            self.event_bus.listen(
                "EVT:ALPHA_SCORE_CALCULATED", self._on_alpha_score
            )
            LOG.info("AlphaScoreWalListener registered")

    def _on_alpha_score(self, event: Any, **kwargs) -> None:
        payload = event.pld if hasattr(event, "pld") else event
        if not isinstance(payload, dict):
            return

        try:
            from vfoundation.dr import wal

            wal_record = {
                "op": "EVT",
                "verb": "ALPHA_SCORE_CALCULATED",
                "symbol": payload.get("symbol", ""),
                "provider_id": payload.get("provider_id", "unknown"),
                "model_name": payload.get("model_name", "unknown"),
                "score": payload.get("score", 0),
                "confidence": payload.get("confidence", 0),
                "ts_ms": payload.get("ts_ms", 0),
                "tf_sec": payload.get("tf_sec", 0),
                "bar_close_ts": payload.get("bar_close_ts", 0),
                "shadow": payload.get("shadow", True),
                "signal_id": payload.get("signal_id", ""),
                "why": "alpha_wal_listener",
            }
            wal.append(wal_record)
            self._count += 1
        except Exception as e:
            LOG.debug(f"Alpha WAL write failed: {e}")

    @property
    def events_written(self) -> int:
        return self._count
