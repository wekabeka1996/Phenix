# TASK26 Failure Modes

How the system fails closed (safe) in error conditions.

| Scenario | Trigger | Expected | Observed | Fail-Closed |
|----------|---------|----------|----------|-------------|
| test_warmup_gate_blocks_trade_intent_until_ready | full_ready=false, trade intent | blocked=true, no trade | blocked=True | ✅ |
| test_warmup_gate_reduce_only_bypasses | warmup incomplete, reduce_only=true | allowed (safety for position close) | blocked=False | ❌ |
| test_warmup_progressive_buffer_build | ticks_seen >= 50 | full_ready=true | full_ready=true | ✅ |
| test_macro_sync_insufficient_data_returns_explicit_flag | n < min_buffer (5 < 10) | macro_sync_ready=false + reason | ready=False, reason=insufficient_symbol_samples | ✅ |
| test_macro_sync_stale_anchor_explicit_block | anchor_age > TTL (600ms > 500ms) | macro_sync_ready=false, reason=stale | ready=False, reason=no_fresh_anchor_data | ✅ |
| test_macro_sync_valid_correlation_not_neutral | valid correlated anchor/symbol data | macro_sync_ready=true, phi > 0.7 | ready=True, phi=1 | ✅ |
| test_volume_spike_stable_across_tick_rates | same vol/sec, different dt | |spike_a - spike_b| < 0.01 | diff=0.0 | ✅ |
| test_volume_spike_varying_dt_normalized | varying dt (20, 200, 2000ms) with same vol/sec | max spike diff < 0.02 | max_diff=0.0 | ✅ |
| test_volume_spike_zero_dt_handled | dt_ms=0 | no exception, safe handling | no_exception=True | ✅ |
| test_regime_returns_uncertain_with_insufficient_features | missing key features | no regime emitted or UNCERTAIN | no regime event | ✅ |
| test_regime_handles_stale_feature_timestamp | stale features (1 hour old) | handled without crash | events_emitted=0 | ✅ |
| test_regime_warmup_blocks_detection | features with warmup.full_ready=false | no high-confidence regime | regime_events=0 | ✅ |
| test_retry_no_loop_drops_intent_with_metric | missing asyncio loop | intent dropped, metric incremented | no exception, pending=0 | ✅ |
| test_retry_bounded_by_max_attempts | attempts > max_attempts (3 > 2) | last event = INTENT_DROPPED | verb=INTENT_DROPPED | ✅ |
| test_duplicate_intent_creates_single_order | same correlation_id emitted twice | 1 order, second is DEDUPE | orders=1, result2=DEDUPE | ✅ |
| test_different_intents_create_separate_orders | two different correlation_ids | 2 separate orders | orders=2 | ✅ |
| test_idempotency_key_used_in_execution | generate_client_order_id called | unique order IDs per call | ids_unique=True | ✅ |
| test_retry_with_same_correlation_no_duplicate_order | 3 attempts with same correlation_id | 1 order, 2 skipped | orders=1, skip_count=2 | ✅ |