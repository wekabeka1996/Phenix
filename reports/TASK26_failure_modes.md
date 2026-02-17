# TASK26 Failure Modes

How the system fails closed (safe) in error conditions.

| Scenario | Trigger | Expected | Observed | Fail-Closed |
|----------|---------|----------|----------|-------------|
| test_macro_sync_insufficient_data_returns_explicit_flag | n < min_buffer (5 < 10) | macro_sync_ready=false + reason | ready=False, reason=insufficient_symbol_samples | ✅ |
| test_macro_sync_stale_anchor_explicit_block | anchor_age > TTL (600ms > 500ms) | macro_sync_ready=false, reason=stale | ready=False, reason=no_fresh_anchor_data | ✅ |
| test_macro_sync_valid_correlation_not_neutral | valid correlated anchor/symbol data | macro_sync_ready=true, phi > 0.7 | ready=True, phi=1 | ✅ |