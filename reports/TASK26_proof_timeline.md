# TASK26 Proof Timeline

## Scenarios

### test_regime_returns_uncertain_with_insufficient_features

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1770639495834 | REGIME_SETUP | scenario_runner | {"detector": "RegimeDetector", "test": "... |
| 1770639495834 | REGIME_RESULT | regime_detector | {"features_sent": ["symbol", "ts"], "emi... |

### test_regime_handles_stale_feature_timestamp

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1770639495837 | REGIME_STALE_FEATURES | scenario_runner | {"ts": 1770635895837, "age_ms": 3600000} |
| 1770639495837 | REGIME_RESULT | regime_detector | {"emitted_count": 0, "stale_data": true} |

### test_regime_warmup_blocks_detection

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1770639495839 | REGIME_WARMUP_CHECK | scenario_runner | {"full_ready": false, "ticks_seen": 5} |
| 1770639495839 | REGIME_RESULT | regime_detector | {"emitted_count": 0, "regime_events": 0} |
