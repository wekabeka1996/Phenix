"""Tests for vfoundation.dr.snapshot — Phase 1.10."""
from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pytest

from vfoundation.dr import snapshot


@pytest.fixture()
def tmp_snap_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Redirect SNAP_DIR to a temp directory."""
    monkeypatch.setattr(snapshot, "SNAP_DIR", tmp_path / "snapshots")
    return tmp_path / "snapshots"


def test_save_creates_file(tmp_snap_dir: pathlib.Path) -> None:
    path = snapshot.save("dm", {"mode": "normal"})
    p = pathlib.Path(path)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mode"] == "normal"


def test_save_load_roundtrip(tmp_snap_dir: pathlib.Path) -> None:
    state = {"x": 1, "nested": {"a": True}}
    snapshot.save("mydomain", state)
    loaded = snapshot.load_latest("mydomain")
    assert loaded == state


def test_load_latest_returns_none_for_missing(tmp_snap_dir: pathlib.Path) -> None:
    assert snapshot.load_latest("no_such_domain") is None


def test_load_latest_returns_most_recent(tmp_snap_dir: pathlib.Path) -> None:
    snapshot.save("d", {"v": 1})
    snapshot.save("d", {"v": 2})
    loaded = snapshot.load_latest("d")
    assert loaded is not None
    assert loaded["v"] == 2
