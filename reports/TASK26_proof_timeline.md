# TASK26 Proof Timeline

## Scenarios

### test_warmup_gate_reduce_only_bypasses

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978440 | WARMUP_STATE | scenario_runner | {"full_ready": null, "reduce_only": true... |
| 1769597978440 | WARMUP_GATE_CHECK | decision_making | {"blocked": false, "reduce_only": true} |

### test_warmup_progressive_buffer_build

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978441 | WARMUP_PROGRESS | scenario_runner | {"ticks_seen": 10, "required": 50, "full... |
| 1769597978441 | WARMUP_PROGRESS | scenario_runner | {"ticks_seen": 25, "required": 50, "full... |
| 1769597978441 | WARMUP_PROGRESS | scenario_runner | {"ticks_seen": 49, "required": 50, "full... |
| 1769597978441 | WARMUP_PROGRESS | scenario_runner | {"ticks_seen": 50, "required": 50, "full... |
| 1769597978441 | WARMUP_PROGRESS | scenario_runner | {"ticks_seen": 100, "required": 50, "ful... |

### test_macro_sync_insufficient_data_returns_explicit_flag

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978442 | MACRO_SYNC_BUFFER | scenario_runner | {"samples": 5, "min_required": 10} |
| 1769597978442 | MACRO_SYNC_RESULT | feature_engineering | {"phi": "0.5", "macro_sync_ready": false... |

### test_macro_sync_stale_anchor_explicit_block

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978444 | MACRO_SYNC_BUFFER | scenario_runner | {"samples": 20, "anchor_ttl_ms": 500} |
| 1769597978444 | MACRO_SYNC_RESULT | feature_engineering | {"phi": "0.5", "macro_sync_ready": false... |

### test_macro_sync_valid_correlation_not_neutral

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978445 | MACRO_SYNC_RESULT | feature_engineering | {"phi": "1", "macro_sync_ready": true, "... |

### test_volume_spike_stable_across_tick_rates

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978446 | VOLUME_SPIKE_A | scenario_runner | {"dt_ms": 100, "vol_per_tick": 1, "impli... |
| 1769597978446 | VOLUME_SPIKE_B | scenario_runner | {"dt_ms": 1000, "vol_per_tick": 10, "imp... |

### test_volume_spike_varying_dt_normalized

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978447 | VOLUME_SPIKE_DT | scenario_runner | {"dt_ms": 20, "vol_per_tick": 0.2, "spik... |
| 1769597978447 | VOLUME_SPIKE_DT | scenario_runner | {"dt_ms": 200, "vol_per_tick": 2, "spike... |
| 1769597978447 | VOLUME_SPIKE_DT | scenario_runner | {"dt_ms": 2000, "vol_per_tick": 20, "spi... |

### test_volume_spike_zero_dt_handled

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978448 | VOLUME_SPIKE_ZERO_DT | scenario_runner | {"dt_ms": 0} |

### test_regime_returns_uncertain_with_insufficient_features

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978450 | REGIME_SETUP | scenario_runner | {"detector": "RegimeDetector", "test": "... |
| 1769597978450 | REGIME_RESULT | regime_detector | {"features_sent": ["symbol", "ts"], "emi... |

### test_regime_handles_stale_feature_timestamp

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978451 | REGIME_STALE_FEATURES | scenario_runner | {"ts": 1769594378451, "age_ms": 3600000} |
| 1769597978451 | REGIME_RESULT | regime_detector | {"emitted_count": 0, "stale_data": true} |

### test_regime_warmup_blocks_detection

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978452 | REGIME_WARMUP_CHECK | scenario_runner | {"full_ready": false, "ticks_seen": 5} |
| 1769597978452 | REGIME_RESULT | regime_detector | {"emitted_count": 0, "regime_events": 0} |

### test_retry_no_loop_drops_intent_with_metric

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978453 | RETRY_SCHEDULER_SETUP | scenario_runner | {"loop_bound": false, "max_attempts": 2} |
| 1769597978453 | RETRY_REGISTER_RESULT | retry_scheduler | {"exception_raised": false, "result": fa... |

### test_retry_bounded_by_max_attempts

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978454 | RETRY_MAX_ATTEMPTS_SETUP | scenario_runner | {"max_attempts": 2, "loop_bound": true} |
| 1769597978486 | RETRY_MAX_ATTEMPTS_RESULT | retry_scheduler | {"emitted_count": 3, "verbs": ["MR_SIGNA... |

### test_retry_attempt_increments

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978510 | RETRY_ATTEMPT_INCREMENT | scenario_runner | {"registrations": 2, "emitted": 2, "whys... |

### test_duplicate_intent_creates_single_order

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978511 | INTENT_PROPOSED | scenario_runner | {"correlation_id": "intent-450d6e01-1dc8... |
| 1769597978511 | ORDER_ATTEMPT_1 | execution | {"intent_id": "intent-450d6e01-1dc8-4270... |
| 1769597978511 | ORDER_ATTEMPT_2 | execution | {"intent_id": "intent-450d6e01-1dc8-4270... |

### test_different_intents_create_separate_orders

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978512 | INTENT_1 | scenario_runner | {"id": "intent-e26ede99-5fa6-49e7-9349-0... |
| 1769597978512 | INTENT_2 | scenario_runner | {"id": "intent-084dbf69-cf63-427d-847e-d... |
| 1769597978512 | ORDER_RESULTS | execution | {"result1": "CREATED", "result2": "CREAT... |

### test_idempotency_key_used_in_execution

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978513 | CLIENT_ORDER_ID_GEN | scenario_runner | {"order_id_1": "BTCUSDT-c3472379ea", "or... |

### test_retry_with_same_correlation_no_duplicate_order

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978514 | INTENT_ATTEMPT_1 | scenario_runner | {"action": "ORDER_CREATED", "order_id": ... |
| 1769597978514 | INTENT_ATTEMPT_2 | scenario_runner | {"action": "SKIP_DUPLICATE", "existing_o... |
| 1769597978514 | INTENT_ATTEMPT_3 | scenario_runner | {"action": "SKIP_DUPLICATE", "existing_o... |

### test_block_trade_not_lost_to_dust

| ts_ms | event_type | source | payload |
|-------|------------|--------|---------|
| 1769597978515 | LTI_RESULT | feature_engineering | {"phi": "0.833333333333277777777777787",... |
