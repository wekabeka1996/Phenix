# TASK26 Failure Modes

How the system fails closed (safe) in error conditions.

| Scenario | Trigger | Expected | Observed | Fail-Closed |
|----------|---------|----------|----------|-------------|
| test_regime_returns_uncertain_with_insufficient_features | missing key features | no regime emitted or UNCERTAIN | no regime event | ✅ |
| test_regime_handles_stale_feature_timestamp | stale features (1 hour old) | handled without crash | events_emitted=0 | ✅ |
| test_regime_warmup_blocks_detection | features with warmup.full_ready=false | no high-confidence regime | regime_events=0 | ✅ |