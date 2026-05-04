from __future__ import annotations

from pathlib import Path


def _frame(event_name: str, payload: dict, *, why: str) -> dict:
    return {
        "frame_id": f"frame-{event_name}",
        "captured_ts_ms": int(payload.get("ts", 0) or 0),
        "event_name": event_name,
        "payload": payload,
        "why": why,
    }


def _tick_payload(symbol: str, ts: int) -> dict:
    return {
        "ts": ts,
        "symbol": symbol,
        "tf_sec": 0,
        "features": {
            "obi": "0.1",
            "tfi": "0.0",
            "delta_price": "0.0",
            "absorption": "0.0",
            "price": "100.0",
            "liquidity_kappa": "0.5",
        },
        "warmup": {
            "full_ready": False,
            "ticks_seen": 1,
            "ready": {},
            "reasons": ["tick"],
        },
        "price_motion": {
            "ret_10s": 0.0,
            "ret_60s": 0.0,
            "ret_300s": 0.0,
            "vol_pct_10s": 0.0,
            "vol_pct_60s": 0.0,
            "vol_pct_300s": 0.0,
            "pm_norm_10s": 0.0,
            "pm_norm_60s": 0.0,
            "pm_norm_300s": 0.0,
        },
        "bar": None,
        "source_mode": "live",
        "diagnostics": {"fe": {"features_emitted": 1}},
    }


def _bar_payload(symbol: str, tf_sec: int, ts: int) -> dict:
    return {
        "ts": ts,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "features": {
            "obi": "0.2",
            "tfi": "0.1",
            "delta_price": "0.0",
            "absorption": "0.0",
            "price": "100.0",
            "liquidity_kappa": "0.6",
        },
        "warmup": {
            "full_ready": True,
            "ticks_seen": 20,
            "ready": {},
            "reasons": [],
        },
        "price_motion": {
            "ret_10s": 0.0,
            "ret_60s": 0.0,
            "ret_300s": 0.0,
            "vol_pct_10s": 0.0,
            "vol_pct_60s": 0.0,
            "vol_pct_300s": 0.0,
            "pm_norm_10s": 0.0,
            "pm_norm_60s": 0.0,
            "pm_norm_300s": 0.0,
        },
        "bar": {
            "symbol": symbol,
            "timeframe_sec": tf_sec,
            "start_ts_ms": ts - (tf_sec * 1000),
            "end_ts_ms": ts - 1,
            "open": "99.0",
            "high": "101.0",
            "low": "98.0",
            "close": "100.0",
            "volume": "1000.0",
        },
        "source_mode": "live",
        "regime": None,
        "diagnostics": {"fe": {"features_emitted": 1, "cmd_emitted": 0}},
    }


def test_shadow_telemetry_handles_tick_and_bar_feature_verbs(tmp_path: Path) -> None:
    from apps.reference.domains.shadow_telemetry.snapshot_store import SnapshotStore

    store = SnapshotStore(
        output_dir=str(tmp_path / "snapshots"),
        trigger_event="EVT:FEATURES_CALCULATED",
        bar_snapshots_enabled=True,
        tick_snapshots_mode="sampled",
        tick_sample_every_n=1,
        min_tf_sec_for_full=60,
    )

    symbol = "BTCUSDT"
    tick_ts = 1_700_000_000_000
    bar_ts = tick_ts + 180_000

    store.ingest_event(
        _frame(
            "EVT:TICK_FEATURES_CALCULATED",
            _tick_payload(symbol, tick_ts),
            why="tick_features",
        )
    )
    store.ingest_event(
        _frame(
            "EVT:FEATURES_CALCULATED",
            _bar_payload(symbol, 180, bar_ts),
            why="bar_features",
        )
    )

    tick_snapshot = store.latest(symbol, 0)
    bar_snapshot = store.latest(symbol, 180)
    assert tick_snapshot is not None
    assert bar_snapshot is not None
    assert tick_snapshot["tf_sec"] == 0
    assert bar_snapshot["tf_sec"] == 180
    assert bar_snapshot["bar"] is not None

    # Old mixed-semantic bar verb should not be reinterpreted as tick traffic.
    store.ingest_event(
        _frame(
            "EVT:FEATURES_CALCULATED",
            _tick_payload(symbol, tick_ts + 1),
            why="old_tick_leak",
        )
    )

    assert len(store.tail(symbol, 10)) == 2
