"""
Ingest Gateway
==============

Reads alpha_input_v1.jsonl stream and yields validated AlphaInputV1 snapshots.

Two modes:
- replay: read entire file sequentially (for backtesting)
- live_tail: follow growing file in real-time (for live shadow)
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Iterator, AsyncIterator, Dict, Any

from .contracts import AlphaInputV1

LOG = logging.getLogger(__name__)


class IngestGateway:
    """
    Read and validate alpha_input_v1 snapshots from JSONL stream.

    Supports replay (sequential read) and live_tail (follow) modes.
    Invalid lines are rejected with counters (fail-closed per snapshot).
    """

    def __init__(
        self,
        stream_path: Path,
        mode: str = "replay",
        poll_interval_sec: float = 0.5,
    ):
        self._stream_path = Path(stream_path)
        self._mode = mode
        self._poll_interval = poll_interval_sec

        self._offset: int = 0
        self._snapshots_read: int = 0
        self._snapshots_rejected: int = 0
        self._lines_read: int = 0
        self._eof_reached: bool = False

    def iter_replay(self) -> Iterator[AlphaInputV1]:
        """
        Synchronous replay iterator: read entire file and yield valid snapshots.

        Invalid lines are logged and skipped (fail-closed per line).
        """
        if not self._stream_path.exists():
            LOG.error(f"Stream file not found: {self._stream_path}")
            return

        LOG.info(f"Ingest replay started: {self._stream_path}")

        with open(self._stream_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                self._lines_read += 1
                line = line.strip()
                if not line:
                    continue

                snapshot = self._parse_line(line, line_no)
                if snapshot:
                    self._snapshots_read += 1
                    yield snapshot
                else:
                    self._snapshots_rejected += 1

        self._eof_reached = True
        LOG.info(
            f"Ingest replay complete: read={self._snapshots_read}, "
            f"rejected={self._snapshots_rejected}, lines={self._lines_read}"
        )

    async def iter_live_tail(self) -> AsyncIterator[AlphaInputV1]:
        """
        Async live tail iterator: follow growing JSONL file.

        Follows the MultiTailer pattern from neocortex:
        - Track byte offset
        - Poll for new lines at poll_interval
        - Yield valid snapshots
        """
        import asyncio

        LOG.info(f"Ingest live tail started: {self._stream_path}")

        _missing_warn_interval = 30  # warn every N seconds when file absent
        _idle_warn_interval = 120    # warn every N seconds when 0 new snapshots
        _last_missing_warn: float = 0.0
        _last_idle_warn: float = 0.0
        _idle_since: float = time.monotonic()

        while True:
            if not self._stream_path.exists():
                now = time.monotonic()
                if now - _last_missing_warn >= _missing_warn_interval:
                    LOG.warning(
                        f"[live_tail] Stream file does not exist yet: {self._stream_path}. "
                        f"FeatureMirrorWriter in main.py must be running to create it. "
                        f"If doing offline analysis, switch source_mode to 'replay' in scenario_matrix.yaml."
                    )
                    _last_missing_warn = now
                await asyncio.sleep(self._poll_interval)
                continue

            with open(self._stream_path, "r", encoding="utf-8") as f:
                f.seek(self._offset)
                lines_found = 0

                for line in f:
                    self._lines_read += 1
                    line = line.strip()
                    if not line:
                        continue

                    snapshot = self._parse_line(line, self._lines_read)
                    if snapshot:
                        self._snapshots_read += 1
                        lines_found += 1
                        _idle_since = time.monotonic()
                        yield snapshot
                    else:
                        self._snapshots_rejected += 1

                self._offset = f.tell()

            if lines_found == 0:
                now = time.monotonic()
                idle_secs = now - _idle_since
                if idle_secs >= _idle_warn_interval and now - _last_idle_warn >= _idle_warn_interval:
                    LOG.warning(
                        f"[live_tail] No new snapshots for {idle_secs:.0f}s "
                        f"(total read={self._snapshots_read}). "
                        f"Check that main.py + FeatureMirrorWriter are running and writing to {self._stream_path}."
                    )
                    _last_idle_warn = now
                await asyncio.sleep(self._poll_interval)

    def _parse_line(self, line: str, line_no: int) -> Optional[AlphaInputV1]:
        """Parse and validate a single JSONL line."""
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            LOG.debug(f"Line {line_no}: JSON parse error: {e}")
            return None

        try:
            return AlphaInputV1.model_validate(raw)
        except Exception as e:
            LOG.debug(f"Line {line_no}: Validation error: {e}")
            return None

    @property
    def stats(self) -> Dict[str, Any]:
        """Return current ingest statistics."""
        return {
            "stream_path": str(self._stream_path),
            "mode": self._mode,
            "snapshots_read": self._snapshots_read,
            "snapshots_rejected": self._snapshots_rejected,
            "lines_read": self._lines_read,
            "offset_bytes": self._offset,
            "eof_reached": self._eof_reached,
            "reject_rate_pct": (
                round(self._snapshots_rejected /
                      max(self._lines_read, 1) * 100, 2)
            ),
        }
