import json
from pathlib import Path

import pytest

try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False

from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    attach_canonical_bar_payload,
    build_canonical_bar_identity,
    extract_canonical_bar_identity,
    extract_canonical_replay_identity,
)


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
CMD_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "reference"
    / "domains"
    / "feature_engineering"
    / "schemas"
    / "cmd_process_strategy_v1.json"
)


def _load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def test_attach_canonical_bar_payload_adds_identity_and_bridge_fields() -> None:
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_700_000_000_000,
        close_boundary_ts_ms=1_700_000_300_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1_700_000_300_123,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_299_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
    }

    attach_canonical_bar_payload(payload, identity=identity, replay_generation=0)

    assert payload["bar_close_ts"] == 1_700_000_299_999
    assert payload["close_boundary_ts_ms"] == 1_700_000_300_000
    assert payload["source_mode"] == "live"
    assert payload["bar_identity"]["close_boundary_ts_ms"] == 1_700_000_300_000
    assert payload["replay_identity"]["replay_generation"] == 0
    assert payload["bar"]["bar_identity"]["bar_end_ts_ms"] == 1_700_000_299_999


def test_live_and_replay_extract_same_downstream_meaning() -> None:
    live = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1_700_000_300_123,
        "bar_close_ts": 1_700_000_299_999,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_299_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
        "source_mode": "live",
    }
    replay = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1_700_000_999_999,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_299_999,
            "close_boundary_ts_ms": 1_700_000_300_000,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
        "source_mode": "replay",
        "replay_generation": 4,
    }

    live_identity = extract_canonical_bar_identity(live, default_source_mode=RuntimeBarSourceMode.LIVE)
    replay_identity = extract_canonical_bar_identity(replay, default_source_mode=RuntimeBarSourceMode.REPLAY)
    replay_token = extract_canonical_replay_identity(replay, default_source_mode=RuntimeBarSourceMode.REPLAY)

    assert live_identity is not None
    assert replay_identity is not None
    assert replay_token is not None
    assert live_identity.symbol == replay_identity.symbol
    assert live_identity.timeframe_sec == replay_identity.timeframe_sec
    assert live_identity.bar_start_ts_ms == replay_identity.bar_start_ts_ms
    assert live_identity.bar_end_ts_ms == replay_identity.bar_end_ts_ms
    assert live_identity.close_boundary_ts_ms == replay_identity.close_boundary_ts_ms
    assert replay_token.close_boundary_ts_ms == replay_identity.close_boundary_ts_ms
    assert replay_token.replay_generation == 4
    assert live_identity.source_mode == RuntimeBarSourceMode.LIVE
    assert replay_identity.source_mode == RuntimeBarSourceMode.REPLAY


def test_warmup_import_derives_canonical_identity_from_open_ts() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 14400,
        "source_mode": "warmup_import",
        "bar": {
            "open_ts": 1_700_000_000_000,
            "o": 100.0,
            "h": 110.0,
            "l": 95.0,
            "c": 108.0,
            "v": 12.0,
        },
    }

    identity = extract_canonical_bar_identity(
        payload,
        default_source_mode=RuntimeBarSourceMode.WARMUP_IMPORT,
    )

    assert identity is not None
    assert identity.bar_start_ts_ms == 1_700_000_000_000
    assert identity.close_boundary_ts_ms == 1_700_014_400_000
    assert identity.bar_end_ts_ms == 1_700_014_399_999
    assert identity.source_mode == RuntimeBarSourceMode.WARMUP_IMPORT


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_bar_closed_schema_accepts_canonical_identity_fields() -> None:
    schema = _load_schema("bar_closed_v1.json")
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_700_000_000_000,
        close_boundary_ts_ms=1_700_000_300_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    payload = {
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_300_123,
        "tf_sec": 300,
        "bar_close_ts": 1_700_000_299_999,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_299_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
    }
    attach_canonical_bar_payload(payload, identity=identity, replay_generation=0)
    validate(instance=payload, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_cmd_process_strategy_schema_accepts_canonical_identity_fields() -> None:
    with open(CMD_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=300,
        bar_start_ts_ms=1_700_000_000_000,
        close_boundary_ts_ms=1_700_000_300_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1_700_000_299_999,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_299_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
        "features": {},
        "warmup": {"full_ready": True, "ticks_seen": 100},
        "regime": {"regime": "TREND_UP"},
    }
    attach_canonical_bar_payload(payload, identity=identity, replay_generation=0)
    validate(instance=payload, schema=schema)
