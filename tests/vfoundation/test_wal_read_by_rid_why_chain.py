from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def mock_wal_dir(tmp_path: Path) -> Path:
    """Redirect WAL writes to a temp directory for this test module."""
    wal_dir = tmp_path / "wal"
    wal_dir.mkdir()

    from vfoundation import config as vf_config

    vf_config.config.wal_dir = wal_dir

    from vfoundation.dr import wal

    wal.set_wal_dir(wal_dir)

    yield wal_dir


def test_read_by_rid_extracts_payload_why_and_message_data_ref() -> None:
    from vfoundation.core.protocol import Message
    from vfoundation.dr import wal

    rid = "rid-why-123"

    # Write out-of-order to validate chronological ordering on read.
    wal.append(
        Message(
            op="DEC",
            verb="OPEN",
            src="execution_position",
            dst="execution_position",
            rid=rid,
            why="OPEN_OK",
            data_ref=["b", "c"],
            pld={"rid": rid},
            ts=2000,
        ).model_dump()
    )

    wal.append(
        Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            rid=rid,
            why="trade_intent",
            data_ref=["a", "b"],
            pld={"rid": rid, "why": ["a", "b"]},
            ts=1000,
        ).model_dump()
    )

    events, why_chain, integrity_ok = wal.read_by_rid(rid)

    assert integrity_ok is True
    assert len(events) == 2
    assert events[0].get("ts") == 1000
    assert events[1].get("ts") == 2000

    # Chain must include reasons from payload["why"] and message-level data_ref.
    # Hot-path record["why"] is included only as a fallback when no chain evidence exists.
    assert why_chain == ["a", "b", "c"]
