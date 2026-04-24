from apps.reference.domains.decision_making.gates.safety_gates import _extract_regime


def test_extract_regime_returns_detector_cache_provenance() -> None:
    per_symbol_regimes = {
        "ETHUSDT": {
            "regime": "TREND_DOWN",
            "confidence": "0.85",
            "cache_write_ts_ms": 1775105700300,
            "regime_provenance": {
                "source_kind": "detector_event",
                "detector_event": {
                    "event_name": "EVT:REGIME_DETECTED",
                    "rid": "rid-detector-heartbeat-eth",
                    "ts_ms": 1775105700000,
                    "last_update_ts_ms": 1775105700256,
                    "structural_regime_ref": "structural:ETHUSDT:1775105700000",
                    "changed": False,
                    "regime": "TREND_DOWN",
                    "confidence": "0.85",
                    "raw_regime": "TREND_DOWN",
                    "raw_confidence": "0.85",
                },
                "cache_snapshot": {
                    "cache_write_ts_ms": 1775105700300,
                    "regime": "TREND_DOWN",
                    "confidence": 0.85,
                },
            },
        }
    }

    regime, confidence, provenance = _extract_regime(
        per_symbol_regimes, "ETHUSDT")

    assert regime == "TREND_DOWN"
    assert confidence == 0.85
    assert provenance["source_kind"] == "detector_cache"
    assert provenance["detector_event"]["rid"] == "rid-detector-heartbeat-eth"
    assert provenance["detector_event"]["structural_regime_ref"] == "structural:ETHUSDT:1775105700000"
    assert provenance["cache_snapshot"]["cache_write_ts_ms"] == 1775105700300
    assert provenance["cache_snapshot"]["confidence"] == 0.85


def test_extract_regime_returns_unknown_provenance_when_missing() -> None:
    regime, confidence, provenance = _extract_regime({}, "ETHUSDT")

    assert regime is None
    assert confidence is None
    assert provenance["source_kind"] == "unknown"
    assert provenance["detector_event"] is None
    assert provenance["cache_snapshot"] is None
