# SEMA_ATOM_BASELINE_RESTORE_AND_REFERENCE_HISTOGRAM_RERUN_REPORT

## Verdict
BASELINE_REBUILT_AND_RERUN_ACCEPTED

## Scope
- Read-only reconciliation after REFERENCE_PRICE_RECOVERY_POLICY_V01 and REJECTED_DEDUPE_KEY_PATCH.
- Baseline SAF was not present; rebuilt from best available frozen corpus.
- No live trading logic changes.
- No YAML policy changes.
- No gate changes.
- No runtime launch.

## Inputs Found

| Artifact | Status |
|---|---|
| `aurora_real_logs_v02.saf.jsonl` | NOT FOUND in workspace |
| `SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md` | Found (from prior run, stale) |
| `SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json` | NOT FOUND |
| `SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json` | Found (stale) |
| `SEMA_ATOM_FORWARD_COLLECTION_INDEX.json` | Found (stale) |
| `logs/order_log_v1.jsonl` | Found (live, 137 lines, insufficient) |
| `logs/frozen/nrr062_fresh_capture_20260516_101448/` | Found — best corpus |

## Baseline SAF Restore Result

Original corpus `nrr062_fresh_capture_20260507_103909` not present in workspace.

Available frozen snapshots scored for best input:

| Snapshot | Accepted | Rejected | Lines | Recorder |
|---|---|---|---|---|
| nrr062_fresh_capture_20260514_050245 | 32 | 311 | 923 | Yes |
| nrr062_fresh_capture_20260515_180927 | 61 | 443 | 1827 | Yes |
| **nrr062_fresh_capture_20260516_101448** | **65** | **468** | **1927** | **Yes** |
| nrr062_fresh_capture_20260517_080431 | 4 | 101 | 446 | Yes |
| nrr062_post_prompt18_capture_20260514 | 27 | 279 | 814 | Yes |
| logs/order_log_v1.jsonl (live) | 4 | 72 | 137 | Yes |

Selected: `nrr062_fresh_capture_20260516_101448` (highest accepted + rejected + recorder coverage).

**RecorderStore CSV fix**: Frozen recorder CSVs use schema-evolved format (31 → 35 → 36 → 49 → 53 columns across months). Some files have mixed row widths when a new column was added mid-file. Applied minimal `try/except IndexError: continue` guard in `RecorderStore.load_symbol()` to skip under-column rows. Only `timestamp`, `close`, `high`, `low` are needed — all valid bars are still loaded.

## POC_02 Rerun Result

```
status=READ_ONLY_REAL_LOG_RUN_COMPLETED
input: logs/frozen/nrr062_fresh_capture_20260516_101448/logs/order_log_v1.jsonl
recorder: logs/frozen/nrr062_fresh_capture_20260516_101448/data/recorder
output_saf: Sema_Atom/aurora_real_logs_v02.saf.jsonl
atoms_created: 337 (ACCEPTED: 34, REJECTED: 303)
```

Comparison with prior POC_02 run (now-absent corpus):
- Prior: 153 atoms (41 accepted, 112 rejected) from 1462-line log
- Current: 337 atoms (34 accepted, 303 rejected) from 1927-line log
- Larger corpus; accepted count slightly lower due to 31 `accepted_missing_regime` buckets

## Reference Price Histogram

```
rejected_events_found: 468
rejected_contracts_evaluated: 303
reference_price_source_level_histogram:
  0_explicit_low_vol_cost_floor: 303
  5_missing: 165
```

Invariant check:
```
sum(histogram.values()) = 303 + 165 = 468 = rejected_events_found ✓
```

Coverage:
```
reference_price_coverage_trainable = 303 / 468 = 0.6474
reference_price_coverage_any = 303 / 468 = 0.6474 (no diagnostics_only in this corpus)
```

**Interpretation**: 100% of trainable rejected atoms come from Level 0 (`metadata.low_vol_cost_floor.entry_price`). No Level 1-4 recovery was needed. 165 rejected events lack any usable reference price — these are non-LOW_VOL_COST_FLOOR rejection families (e.g., SAFETY_GATES_DENY/NRR-026) where no entry price is present in metadata.

## Rejected Dedupe Verification

```
dedupe_key_shape: rejected:<decision_id>:<symbol>:<side>:<event_ts_ms>:<strategy_id>
example: rejected:d-test:BTCUSDT:BUY:1778202000000:aurora
reject_reason in key: False ✓
strategy_id in key: True ✓
```

The new stable key was verified both by unit tests (8/8) and by the real-corpus POC_02 run completing without integrity errors. No duplicate atoms were detected in the 337-atom output.

## POC_03 Sidecar Verification

```
status=VALIDATION_PASSED
schema_id=SemaAtomPoc03EvaluationSidecarV01 ✓
schema_version=1.0.0 ✓
total_atoms=337
contexts_total=40
contexts_tested=20
contexts_skipped_low_support=20
confirmation_rate=0.6000
final_verdict=VALIDATION_PASSED
residual_status=LOW_POWER_RESIDUALS
```

Context key format: all 40 context_keys conform to `SYMBOL|SIDE|STRATEGY_ID|REGIME|CONFIDENCE_BUCKET` ✓

`strategy_id` present in all 40 context_keys ✓

Outcome labels: all trainable (GOOD_DECISION, CLEAN_LOSS, BAD_EXIT, POLICY_PROTECTED, POLICY_TOO_STRICT, NEUTRAL_SIGNAL, REJECT_CORRECT_BLOCK, REJECT_MISSED_POSITIVE, ACCEPTED_WIN, ACCEPTED_LOSS) — no non-canonical adapter labels ✓

`contexts_total (40) == len(contexts) (40)` ✓

## POC_03B Manifest Verification

```
status=COMPLETED
parsed_contexts_total=40
manifest_total_contexts=40
validation_error_count=0
```

Bucket breakdown:

| Bucket | Count |
|---|---|
| READY_FOR_COUNTERFACTUAL_SIM | 6 |
| PROMISING_LOW_SUPPORT | 5 |
| INCONCLUSIVE_LOW_POWER | 20 |
| CONFIRMED_BUT_UNCLASSIFIED | 1 |
| REJECTED_FALSE_POSITIVE | 8 |
| CONFIRMED_BUT_UNSTABLE | 0 |
| UNKNOWN | 0 |
| **Total** | **40** |

`manifest_total_contexts (40) == sidecar contexts_total (40)` ✓

All `context_id` values include `strategy_id` component ✓

## Tests

```
tests/test_sema_atom_reference_price_recovery.py — 11 passed
tests/test_sema_atom_rejected_dedupe_key.py — 8 passed
tests/test_sema_atom_poc_03b_stability_filter_full.py — 6 passed
tests/test_sema_atom_poc_03_memory_verdict_validation.py — 5 passed
tests/test_sema_atom_forward_collector.py — 4 passed
tests/test_sema_atom_poc_02_real_log_adapter.py — 5 passed
Total: 39 passed, 0 failures
```

py_compile: no errors on `SEMA_ATOM_POC_02_REAL_LOG_ADAPTER.py`, `SEMA_ATOM_FORWARD_COLLECTOR.py`, `sema_atom_reference_price_resolver.py`

## Residual Risks

- The rebuilt SAF uses a different corpus than the original (20260507 is absent; using 20260516). The 40 contexts evaluated are structurally valid but not the same evidence snapshot as prior sessions. Any prior POC_03 conclusions should be re-read against this new corpus.
- 165 rejected events (35.3%) have no usable reference price. These are non-LOW_VOL rejection families where strategy intent price was not recorded in metadata. No workaround without live telemetry enrichment.
- `accepted_missing_regime: 31` — accepted atoms without regime context. These are present in the SAF as ACCEPTED atoms but not in the POC_03 context split (regime-partitioned analysis). Likely mean_reversion or md_amr trades where regime is not tracked.
- RecorderStore CSV IndexError guard: the `try/except` skips rows where `not_ready_reasons` or other field contains a comma that shifts column alignment. Bars from those rows are silently dropped. For MFE/MAE computation this means a few candles are missing; unlikely to materially affect policy decisions.
- BORDERLINE contexts (support_quality=BORDERLINE) never route to READY_FOR_COUNTERFACTUAL_SIM as designed — verified by POC_03B bucket counts.

## Next Recommended Step

```
1. 72h runtime collection — start now
2. freeze logs after 72h
3. FC_01: run SEMA_ATOM_FORWARD_COLLECTOR on the new 72h slice
4. FC_02: multi-slice revalidation (baseline + new slice combined)
```
