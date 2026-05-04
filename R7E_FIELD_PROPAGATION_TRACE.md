# R7E Field Propagation Trace

## Goal

Trace each R7C additive field from construction to raw JSONL persistence and mark whether the field is proven at each boundary.

## Summary Table

| Field | Constructed | Emitted | Transported | Persisted | Fresh Runtime Proof | Where Lost If Lost |
| --- | --- | --- | --- | --- | --- | --- |
| sidecar_config_snapshot | yes | yes | yes | yes | yes | nowhere in current runtime |
| peak_giveback_snapshot | yes | yes | yes | yes | yes | nowhere in current runtime |
| peak_giveback_state | yes | yes | yes | yes | yes | nowhere in current runtime |
| null_reasons | yes | yes | yes | yes | yes | nowhere in current runtime |
| policy_source | yes, on recommendation and close-request paths | yes, on recommendation and close-request paths | yes | yes | not observed in the current sampled rows because no recommendation or close-request row fired in that slice | nowhere proven; field is event-conditional |

## Field-By-Field Trace

### 1. sidecar_config_snapshot

- Constructed: yes. announce_mode_active adds sidecar_config_snapshot = self._sidecar_config_snapshot().
- Emitted: yes. _publish receives the mode-active payload unchanged.
- Transported: yes. LocalBus.emit forwards dict(payload) unchanged.
- Persisted: yes. _publish writes record = {"record_kind": "position_policy_sidecar", **payload} and append_trade_lifecycle_record raw-serializes that dict.
- Fresh runtime proof: yes. The current logs/trade_lifecycle.jsonl line 1 contains a POSITION_POLICY_SIDECAR_MODE_ACTIVE row with sidecar_config_snapshot present in raw JSONL.
- Where lost if lost: nowhere in the current runtime. The historical loss was specific to the stale pre-restart slice.

### 2. peak_giveback_snapshot

- Constructed: yes. _evaluate_symbol attaches peak_giveback_snapshot in both trigger and non-trigger evaluation paths before publish.
- Emitted: yes. suppressed, evaluated, scores, recommended, and close-request payloads inherit that snapshot.
- Transported: yes. There is no adapter layer on the raw trade_lifecycle write path.
- Persisted: yes. The serializer probe preserved nested peak_giveback_snapshot unchanged.
- Fresh runtime proof: yes. Current raw BNBUSDT Sidecar rows contain peak_giveback_snapshot in raw JSONL.
- Where lost if lost: nowhere in the current runtime.

### 3. peak_giveback_state

- Constructed: yes. _peak_giveback_snapshot computes peak_giveback_state from config, suppression state, and economics availability.
- Emitted: yes. It rides inside peak_giveback_snapshot.
- Transported: yes. No projection layer removes nested snapshot fields.
- Persisted: yes. The serializer probe preserved peak_giveback_state, and fresh runtime rows show peak_giveback_state = peak_giveback_not_ready.
- Fresh runtime proof: yes.
- Where lost if lost: nowhere in the current runtime.

### 4. null_reasons

- Constructed: yes. _peak_giveback_snapshot fills null_reasons for mark_price, entry_price, position_qty, side, unrealized_pnl_usdt, unrealized_pnl_pct, current_edge_usd, giveback_pct, and threshold_crossed when economics are unavailable.
- Emitted: yes. null_reasons is nested inside peak_giveback_snapshot on emitted policy rows.
- Transported: yes.
- Persisted: yes. The serializer probe preserved nested null_reasons unchanged.
- Fresh runtime proof: yes. Current raw BNBUSDT rows show explicit null_reasons in trade_lifecycle.jsonl.
- Where lost if lost: nowhere in the current runtime.

### 5. policy_source

- Constructed: yes, but only on recommendation and close-request paths. Standard recommendations stamp position_policy_sidecar; peak-giveback trigger paths stamp position_policy_sidecar:peak_giveback.
- Emitted: yes. recommended_payload and request_payload carry policy_source.
- Transported: yes. The transport path is the same direct _publish-to-logger path.
- Persisted: yes. The serializer probe preserved policy_source unchanged, and PositionPolicyCloseRequest.to_payload keeps event_type and policy_source together on close-request payloads.
- Fresh runtime proof: not yet observed in the current sampled raw rows because the sampled post-restart slice contains mode-active and startup-grace suppressed rows, not recommended or close-request rows.
- Where lost if lost: nowhere proven. The field is event-conditional rather than globally expected on every Sidecar row.

## Event Name And Writer Filter Check

- CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST is the command topic.
- POSITION_POLICY_SIDECAR_CLOSE_REQUESTED is the payload event_type emitted by PositionPolicyCloseRequest.to_payload and normalized by the mediator.
- trade_lifecycle raw persistence does not filter on event_type; the only policy-row hiding happens in iter_trade_lifecycle_records at read time and is keyed by record_kind.
- Therefore there is no writer-filter mismatch on the raw JSONL path.

## Historical Failure Localization

The original missing-field slice is best explained by stale runtime build, not by construction, transport, or serialization defects.

That conclusion is stronger now than before because the current restarted runtime directly writes sidecar_config_snapshot, peak_giveback_snapshot, peak_giveback_state, and null_reasons into raw trade_lifecycle JSONL.
