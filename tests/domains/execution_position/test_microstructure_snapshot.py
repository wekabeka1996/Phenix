from apps.reference.domains.execution_position.microstructure_snapshot import (
    attach_microstructure_snapshot,
    extract_microstructure_snapshot,
    get_microstructure_snapshot,
)


def test_extract_microstructure_snapshot_prefers_nested_canonical_fields() -> None:
    snapshot = extract_microstructure_snapshot(
        {
            "symbol": "btcusdt",
            "ts": 1_717_171,
            "tf_sec": 300,
            "features": {
                "price": "100.5",
                "obi": "0.20",
                "spread_bps": "4.5",
                "liquidity_kappa": "0.80",
                "volatility": {
                    "atr_14": "1.25",
                    "atr_pct": "0.0125",
                    "atr_ready": True,
                },
                "liquidity": {
                    "obi_close": "0.35",
                },
            },
            "price_motion": {
                "pm_norm_10s": "-0.8",
                "pm_norm_60s": "-1.2",
                "pm_norm_300s": "-0.4",
            },
            "warmup": {
                "full_ready": True,
            },
        }
    )

    assert snapshot is not None
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.atr_14 == 1.25
    assert snapshot.atr_pct == 0.0125
    assert snapshot.atr_ready is True
    assert snapshot.obi == 0.2
    assert snapshot.obi_close == 0.35
    assert snapshot.orderbook_imbalance == 0.2
    assert snapshot.spread_bps == 4.5
    assert snapshot.liquidity_kappa == 0.8
    assert snapshot.pm_norm_60s == -1.2
    assert snapshot.warmup_full_ready is True
    assert snapshot.source_paths["atr_14"] == "features.volatility.atr_14"
    assert snapshot.legacy_fallback_fields == []
    assert "atr_14" not in snapshot.missing_fields


def test_extract_microstructure_snapshot_uses_legacy_top_level_atr_explicitly() -> None:
    snapshot = extract_microstructure_snapshot(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 10,
            "features": {
                "price": "99.9",
                "atr_14": "2.50",
                "spread_bps": "6.0",
                "liquidity_kappa": "0.70",
                "orderbook_imbalance": "-0.40",
            },
        }
    )

    assert snapshot is not None
    assert snapshot.atr_14 == 2.5
    assert snapshot.orderbook_imbalance == -0.4
    assert "atr_14" in snapshot.legacy_fallback_fields
    assert "orderbook_imbalance" in snapshot.legacy_fallback_fields
    assert snapshot.source_paths["atr_14"] == "features.atr_14"


def test_extract_microstructure_snapshot_keeps_missing_atr_explicit() -> None:
    snapshot = extract_microstructure_snapshot(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 11,
            "features": {
                "price": "101.0",
                "obi": "0.15",
                "spread_bps": "3.0",
                "liquidity_kappa": "0.91",
            },
            "price_motion": {"pm_norm_60s": "0.2"},
        }
    )

    assert snapshot is not None
    assert snapshot.atr_14 is None
    assert "atr_14" in snapshot.missing_fields
    assert "atr_14" not in snapshot.legacy_fallback_fields
    assert snapshot.retained_fields == []


def test_attach_microstructure_snapshot_retains_last_bar_atr_explicitly() -> None:
    previous = attach_microstructure_snapshot(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 100,
            "tf_sec": 300,
            "features": {
                "price": "100.0",
                "obi": "0.10",
                "spread_bps": "4.0",
                "liquidity_kappa": "0.60",
                "volatility": {
                    "atr_14": "1.75",
                    "atr_ready": True,
                },
            },
        }
    )
    previous_snapshot = get_microstructure_snapshot(previous)

    enriched = attach_microstructure_snapshot(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 101,
            "features": {
                "price": "101.0",
                "obi": "-0.25",
                "spread_bps": "5.0",
                "liquidity_kappa": "0.55",
            },
        },
        previous_snapshot=previous_snapshot,
    )
    merged_snapshot = get_microstructure_snapshot(enriched)

    assert merged_snapshot is not None
    assert merged_snapshot.atr_14 == 1.75
    assert "atr_14" in merged_snapshot.retained_fields
    assert merged_snapshot.orderbook_imbalance == -0.25
    assert merged_snapshot.price == 101.0