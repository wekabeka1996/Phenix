# SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_REPORT

## Verdict
REFERENCE_PRICE_RECOVERY_POLICY_ACCEPTED

## Scope
- Narrow policy-hardening package for the offline SemaAtom rejected-decision evidence path.
- No live trading logic changes.
- No YAML policy changes.
- No gate threshold changes.
- No runtime authority, advisory, shadow listener, or economics V2 implementation.

## Files Changed

| File | Change |
|---|---|
| `Sema_Atom/sema_atom_reference_price_resolver.py` | Created — standalone deterministic resolver |
| `Sema_Atom/SEMA_ATOM_POC_02_REAL_LOG_ADAPTER.py` | Patched `RejectedDecisionCollector` |
| `Sema_Atom/SEMA_ATOM_FORWARD_COLLECTOR.py` | Patched `RejectedDecisionCollector` |
| `Sema_Atom/SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01.md` | Policy contract document |
| `tests/test_sema_atom_reference_price_recovery.py` | 11 focused tests (10 required + 1 extra) |

## Discovery

Both `RejectedDecisionCollector` implementations previously used ad-hoc multi-path
`_extract_first_float` chains with no formal level ordering, no trainability classification,
no causal link validation for linked order intents, and no provenance provenance fields beyond
source path and line.

Specific gaps before this package:
1. Level 3 causal link validation was absent — a linked intent timestamped after the rejected
   event could silently become the reference price.
2. Level 4 (recorder-derived) was plumbed but not formally segregated as non-trainable.
3. No trainability field existed on the contract provenance.
4. No source-level histogram was reported in the collector summary.
5. The two collectors had divergent extraction logic (POC_02 vs FC) with no shared module.

## Recovery Hierarchy

| Level | Source | Trainability |
|---|---|---|
| 0 | `metadata.low_vol_cost_floor.entry_price` | trainable |
| 1 | `metadata.reference_price` / `intended_entry_price` (4 paths) | trainable |
| 2 | `metadata.economics_context.entry_price` | trainable |
| 3 | `metadata.linked_order_intent.entry_price` (with causal check) | trainable / invalid |
| 3 | `metadata.linked_planned_entry_price`, `planned_entry_price` (fallbacks) | trainable |
| 4 | `recorder_bar_price` (injected externally) | diagnostics_only |
| 5 | No usable price | missing |

## Trainable vs Diagnostics Policy

A REJECTED event is admitted as a training atom if and only if the resolver returns
`trainability == "trainable"` (Levels 0–3 passing causal check).

Three non-trainable outcomes:
- `invalid` — Level 3 causal link failed (`link_ts > row_ts`). Counted separately so
  the operator can investigate data provenance.
- `diagnostics_only` — Level 4 recorder price. Price exists but is market-observed,
  not strategy-intended. Counted for observability; never produces a trainable atom.
- `missing` — Level 5. No usable price found anywhere in the row.

## Collector Changes

Both collectors now:
- Import `resolve_reference_price` from the shared resolver module
- Maintain `self._source_level_counts: Counter[str]` over all scanned rows
- Gate contract creation on `resolution.trainability == TRAINABILITY_TRAINABLE`
- Add 5 provenance fields to every admitted contract:
  `reference_price_source`, `reference_price_source_level`,
  `reference_price_trainability`, `reference_price_recovery_reason`,
  `reference_price_causal_link_ok`
- Return `reference_price_source_level_histogram` in the summary dict

FC additionally reports coverage split (trainable vs any including diagnostics_only)
and backward-compatible `rejected_reference_price_coverage` alias.

## Report Metrics

Both collectors report:

```
reference_price_source_level_histogram: {level_key: count}
incomplete_rejected_buckets:
  incomplete_rejected_missing_reference_price: N
  incomplete_rejected_invalid_reference_price: N
  incomplete_rejected_diagnostics_only_reference_price: N
```

Invariant: `sum(histogram.values()) == rejected_events_found`

## Tests

| # | Test | File | Status |
|---|---|---|---|
| 1 | Level 0 low_vol_cost_floor.entry_price → trainable | test_sema_atom_reference_price_recovery.py | PASS |
| 2 | Level 1 metadata.reference_price → trainable | test_sema_atom_reference_price_recovery.py | PASS |
| 3 | Level 1 top-level intended_entry_price → trainable | test_sema_atom_reference_price_recovery.py | PASS |
| 4 | Level 2 economics_context.entry_price → trainable | test_sema_atom_reference_price_recovery.py | PASS |
| 5 | Level 3 linked_order_intent with valid causal link → trainable | test_sema_atom_reference_price_recovery.py | PASS |
| 6 | Level 3 linked_order_intent after rejected ts → invalid | test_sema_atom_reference_price_recovery.py | PASS |
| 7 | Level 4 recorder_bar_price → diagnostics_only, not trainable | test_sema_atom_reference_price_recovery.py | PASS |
| 8 | Level 5 no price → missing / no atom in collector | test_sema_atom_reference_price_recovery.py | PASS |
| 9 | No trainable atom from diagnostics_only (monkeypatched collector) | test_sema_atom_reference_price_recovery.py | PASS |
| 10 | Source-level histogram reconciles with rejected counts | test_sema_atom_reference_price_recovery.py | PASS |
| 11 | Level 5 missing in collector → skipped + bucket counted | test_sema_atom_reference_price_recovery.py | PASS |

## Validation Output

```
tests/test_sema_atom_reference_price_recovery.py — 11 passed
tests/test_sema_atom_forward_collector.py — 4 passed (regression: 0 failures)
tests/test_sema_atom_poc_02_real_log_adapter.py — 5 passed (regression: 0 failures)
tests/test_sema_atom_poc_03b_stability_filter_full.py — 6 passed
tests/test_sema_atom_poc_03_memory_verdict_validation.py — 5 passed
tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py — 2 passed
Total: 33 passed, 0 failures
```

## Residual Risks

- Level 4 (diagnostics_only) is never exercised through the collector naturally because
  neither POC_02 nor FC currently passes `recorder_bar_price` to the resolver. The
  diagnostics_only path in both collectors is reachable only if a future caller injects
  `recorder_bar_price`. The monkeypatched test (test 9) covers the code path; the
  end-to-end integration path is deferred.
- Level 3 fallback sources (`linked_planned_entry_price`, `planned_entry_price`) do not
  have a causal link timestamp to validate. They are admitted trainable on the assumption
  that planned prices are always computed before the decision event. If a future audit
  reveals otherwise, the causal check should be extended to these paths.
- The `reference_price_source_level_histogram` is reset on each `collect()` call. It does
  not accumulate across multiple runs within the same process.

## Next Recommended Step

- Restore the canonical baseline input `aurora_real_logs_v02.saf.jsonl`.
- Rerun POC_02 to measure real-world source-level histogram distribution.
- Rerun FC over a forward window to verify Level 0 remains the dominant source for
  `LOW_VOL_COST_FLOOR_DENY` rejections.
- If Level 4 coverage is needed for observability, wire `recorder_bar_price` injection
  into both collectors (look up the nearest candle timestamp from the recorder CSV).
