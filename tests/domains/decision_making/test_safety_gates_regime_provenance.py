from apps.reference.domains.decision_making.gates.safety_gates import (
    _extract_regime,
    resolve_max_regime_confidence,
    resolve_min_regime_confidence,
)


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


def test_resolve_min_regime_confidence_uses_specific_runtime_regime() -> None:
    resolved = resolve_min_regime_confidence(
        "BULL_TREND",
        0.45,
        {"DEFAULT": 0.20, "TREND_UP": 0.52},
    )

    assert resolved.threshold == 0.52
    assert resolved.source == "domain_regime_specific"
    assert resolved.regime_key == "TREND_UP"
    assert resolved.mapping_present is True


def test_resolve_min_regime_confidence_uses_default_when_regime_key_absent() -> None:
    resolved = resolve_min_regime_confidence(
        "LOW_VOLATILITY",
        0.45,
        {"DEFAULT": 0.22, "TREND_UP": 0.52},
    )

    assert resolved.threshold == 0.22
    assert resolved.source == "domain_default"
    assert resolved.regime_key == "DEFAULT"
    assert resolved.mapping_present is True


def test_resolve_min_regime_confidence_strategy_specific_beats_domain_specific() -> None:
    resolved = resolve_min_regime_confidence(
        "TREND_UP",
        0.45,
        {"DEFAULT": 0.20, "TREND_UP": 0.52},
        strategy_id="aurora",
        strategy_by_regime={"DEFAULT": 0.40, "TREND_UP": 0.65},
    )

    assert resolved.threshold == 0.65
    assert resolved.source == "strategy_regime_specific"
    assert resolved.strategy_id == "aurora"
    assert resolved.regime_key == "TREND_UP"


def test_resolve_min_regime_confidence_strategy_symbol_specific_beats_strategy_specific() -> None:
    resolved = resolve_min_regime_confidence(
        "TREND_UP",
        0.45,
        {"DEFAULT": 0.20, "TREND_UP": 0.52},
        strategy_id="aurora",
        symbol="XRPUSDT",
        strategy_by_regime={"DEFAULT": 0.40, "TREND_UP": 0.65},
        strategy_symbol_by_regime={"DEFAULT": 0.675, "TREND_UP": 0.975},
    )

    assert resolved.threshold == 0.975
    assert resolved.source == "strategy_symbol_regime_specific"
    assert resolved.strategy_id == "aurora"
    assert resolved.regime_key == "TREND_UP"


def test_resolve_min_regime_confidence_strategy_symbol_default_beats_strategy_specific() -> None:
    resolved = resolve_min_regime_confidence(
        "TREND_UP",
        0.45,
        {"DEFAULT": 0.20, "TREND_UP": 0.52},
        strategy_id="aurora",
        symbol="XRPUSDT",
        strategy_by_regime={"DEFAULT": 0.40, "TREND_UP": 0.65},
        strategy_symbol_by_regime={"DEFAULT": 0.675},
    )

    assert resolved.threshold == 0.675
    assert resolved.source == "strategy_symbol_default"
    assert resolved.strategy_id == "aurora"
    assert resolved.regime_key == "DEFAULT"


def test_resolve_min_regime_confidence_strategy_default_beats_domain_specific() -> None:
    resolved = resolve_min_regime_confidence(
        "TREND_UP",
        0.45,
        {"DEFAULT": 0.20, "TREND_UP": 0.52},
        strategy_id="aurora",
        strategy_by_regime={"DEFAULT": 0.62},
    )

    assert resolved.threshold == 0.62
    assert resolved.source == "strategy_default"
    assert resolved.strategy_id == "aurora"
    assert resolved.regime_key == "DEFAULT"


def test_resolve_min_regime_confidence_strategy_symbol_regime_side_specific_beats_legacy_symbol_regime() -> None:
    resolved = resolve_min_regime_confidence(
        "TREND_DOWN",
        0.45,
        {"DEFAULT": 0.20, "TREND_DOWN": 0.52},
        strategy_id="aurora",
        symbol="ETHUSDT",
        side="SELL",
        strategy_by_regime={"DEFAULT": 0.40, "TREND_DOWN": 0.65},
        strategy_symbol_by_regime={"DEFAULT": 0.62, "TREND_DOWN": 0.75},
        strategy_symbol_by_regime_side={
            "TREND_DOWN": {
                "SELL": 0.81,
            }
        },
    )

    assert resolved.threshold == 0.81
    assert resolved.source == "strategy_symbol_regime_side_specific"
    assert resolved.strategy_id == "aurora"
    assert resolved.regime_key == "TREND_DOWN"
    assert resolved.disabled is False


def test_resolve_max_regime_confidence_buy_does_not_inherit_sell_disabled_override() -> None:
    resolved = resolve_max_regime_confidence(
        "TREND_DOWN",
        {"TREND_DOWN": 0.67},
        strategy_id="aurora",
        symbol="ETHUSDT",
        side="BUY",
        strategy_symbol_by_regime_side={
            "TREND_DOWN": {
                "SELL": {
                    "enabled": False,
                }
            }
        },
    )

    assert resolved.threshold == 0.67
    assert resolved.source == "domain_regime_specific"
    assert resolved.disabled is False


def test_resolve_max_regime_confidence_side_disable_is_explicit_and_distinct() -> None:
    resolved = resolve_max_regime_confidence(
        "TREND_DOWN",
        {"TREND_DOWN": 0.67},
        strategy_id="aurora",
        symbol="ETHUSDT",
        side="SELL",
        strategy_symbol_by_regime_side={
            "TREND_DOWN": {
                "SELL": {
                    "enabled": False,
                }
            }
        },
    )

    assert resolved.threshold is None
    assert resolved.source == "strategy_symbol_regime_side_specific_disabled"
    assert resolved.strategy_id == "aurora"
    assert resolved.regime_key == "TREND_DOWN"
    assert resolved.disabled is True


def test_resolve_min_regime_confidence_ignores_strategy_mapping_without_strategy_id() -> None:
    resolved = resolve_min_regime_confidence(
        "TREND_UP",
        0.45,
        {"DEFAULT": 0.20, "TREND_UP": 0.52},
        strategy_id=None,
        strategy_by_regime={"DEFAULT": 0.62, "TREND_UP": 0.65},
    )

    assert resolved.threshold == 0.52
    assert resolved.source == "domain_regime_specific"
    assert resolved.strategy_id is None
    assert resolved.regime_key == "TREND_UP"
