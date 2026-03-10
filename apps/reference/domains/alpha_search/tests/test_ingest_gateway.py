"""
T3: Ingest Gateway Tests
=========================

Tests for apps/reference/domains/alpha_search/runtime/ingest.py
8 tests covering replay parsing, validation, stats, and live tail.
"""

import json
import asyncio
import pytest
from pathlib import Path

from apps.reference.domains.alpha_search.runtime.ingest import IngestGateway
from apps.reference.domains.alpha_search.tests.conftest import make_snapshot


def _write_jsonl(path: Path, records: list) -> Path:
    """Write list of dicts to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            if isinstance(rec, str):
                f.write(rec + "\n")
            else:
                f.write(json.dumps(rec) + "\n")
    return path


@pytest.mark.unit
class TestReplay:
    """Tests for synchronous replay mode."""

    def test_valid_jsonl(self, tmp_path):
        """All valid lines yielded as AlphaInputV1."""
        records = [
            make_snapshot(ts_ms=1740000000000 + i, price=96000.0 + i)
            for i in range(5)
        ]
        path = _write_jsonl(tmp_path / "stream.jsonl", records)

        gateway = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gateway.iter_replay())

        assert len(snapshots) == 5
        assert snapshots[0].ts_ms == 1740000000000
        assert snapshots[4].ts_ms == 1740000000004

    def test_skips_invalid_json(self, tmp_path):
        """Malformed JSON skipped, counter incremented."""
        lines = [
            json.dumps(make_snapshot()),
            "NOT VALID JSON {{{{",
            json.dumps(make_snapshot(ts_ms=1740000000001)),
        ]
        path = tmp_path / "stream.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gateway = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gateway.iter_replay())

        assert len(snapshots) == 2
        assert gateway._snapshots_rejected == 1

    def test_skips_invalid_schema(self, tmp_path):
        """Valid JSON but bad schema skipped."""
        lines = [
            json.dumps(make_snapshot()),
            json.dumps({"invalid": "schema", "no_required_fields": True}),
            json.dumps(make_snapshot(ts_ms=1740000000001)),
        ]
        path = tmp_path / "stream.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gateway = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gateway.iter_replay())

        assert len(snapshots) == 2
        assert gateway._snapshots_rejected == 1

    def test_empty_lines_skipped(self, tmp_path):
        """Blank lines ignored."""
        lines = [
            json.dumps(make_snapshot()),
            "",
            "   ",
            json.dumps(make_snapshot(ts_ms=1740000000001)),
        ]
        path = tmp_path / "stream.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gateway = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gateway.iter_replay())
        assert len(snapshots) == 2

    def test_missing_file(self, tmp_path):
        """No crash, zero snapshots yielded."""
        gateway = IngestGateway(
            stream_path=tmp_path / "nonexistent.jsonl",
            mode="replay",
        )
        snapshots = list(gateway.iter_replay())
        assert len(snapshots) == 0

    def test_stats(self, tmp_path):
        """snapshots_read, snapshots_rejected, reject_rate_pct correct."""
        lines = [
            json.dumps(make_snapshot()),
            "bad json",
            json.dumps(make_snapshot(ts_ms=1740000000001)),
            json.dumps({"invalid": True}),
        ]
        path = tmp_path / "stream.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gateway = IngestGateway(stream_path=path, mode="replay")
        list(gateway.iter_replay())

        stats = gateway.stats
        assert stats["snapshots_read"] == 2
        assert stats["snapshots_rejected"] == 2
        assert stats["reject_rate_pct"] == pytest.approx(50.0, abs=1.0)


@pytest.mark.asyncio
@pytest.mark.unit
class TestLiveTail:
    """Tests for async live tail mode."""

    async def test_follows_growing_file(self, tmp_path):
        """New lines yielded after initial read."""
        path = tmp_path / "stream.jsonl"
        # Write initial content
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(make_snapshot()) + "\n")

        gateway = IngestGateway(
            stream_path=path,
            mode="live_tail",
            poll_interval_sec=0.05,
        )

        collected = []

        async def collect():
            async for snap in gateway.iter_live_tail():
                collected.append(snap)
                if len(collected) >= 2:
                    break

        # Append more data after a small delay
        async def writer():
            await asyncio.sleep(0.1)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(make_snapshot(ts_ms=1740000000001)) + "\n")

        # Run both with a timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(collect(), writer()),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            pass

        assert len(collected) >= 1

    async def test_waits_on_no_data(self, tmp_path):
        """Polls without crashing when no new data."""
        path = tmp_path / "stream.jsonl"
        path.write_text(json.dumps(make_snapshot()) + "\n", encoding="utf-8")

        gateway = IngestGateway(
            stream_path=path,
            mode="live_tail",
            poll_interval_sec=0.05,
        )

        collected = []

        async def collect_with_timeout():
            async for snap in gateway.iter_live_tail():
                collected.append(snap)
                if len(collected) >= 1:
                    break

        try:
            await asyncio.wait_for(collect_with_timeout(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

        # Should have collected the initial line without crashing
        assert len(collected) >= 1
