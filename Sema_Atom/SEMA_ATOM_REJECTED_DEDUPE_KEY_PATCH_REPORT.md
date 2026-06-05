# SEMA_ATOM_REJECTED_DEDUPE_KEY_PATCH_REPORT

## Verdict
REJECTED_DEDUPE_KEY_PATCH_ACCEPTED

## Scope
- Narrow corpus-integrity patch for the offline SemaAtom forward-collector rejected-decision pipeline.
- No live trading logic changes.
- No YAML policy changes.
- No gate threshold changes.
- No runtime authority, advisory, shadow listener, or economics changes.
- No mutation of baseline SAF files.

## Files Changed

| File | Change |
|---|---|
| `Sema_Atom/SEMA_ATOM_FORWARD_COLLECTOR.py` | Patched 3 sites: `_rejected_dedupe_key()`, `_atom_dedupe_key_from_payload()`, processing loop + report |
| `tests/test_sema_atom_rejected_dedupe_key.py` | Created — 8 focused tests |

## Discovery / Duplication Check

Grep for `dedupe`, `dedupe_key`, `duplicates_detected`, `duplicates_skipped`, `reject_reason` in
key-construction context confirmed:

- **SEMA_ATOM_FORWARD_COLLECTOR.py**: all deduplication logic. Three sites:
  1. `_rejected_dedupe_key(contract: RawContract) -> str` — used by processing loop
  2. `_atom_dedupe_key_from_payload(atom: dict)` — used for baseline SAF loading
  3. Processing loop (rejected_contracts for-loop)
- **SEMA_ATOM_POC_02_REAL_LOG_ADAPTER.py**: no deduplication logic (single-pass encoder only).
- No shared helper library existed. All dedupe logic was self-contained in FC.

## Old Key

```
rejected:<decision_id>:<symbol>:<side>:<event_ts_ms>:<reject_reason>
```

Problem: `reject_reason` is not a stable decision identity. It is a gate-label that can change
after a why-code normalization, gate rename, or policy refactor without the underlying decision
changing. Two rows describing the same rejected decision with different reason labels would not
be recognized as duplicates, producing ghost atoms.

## New Key

```
rejected:<decision_id_or_rid>:<symbol>:<side>:<event_ts_ms>:<strategy_id>
```

`strategy_id` is included because the same `decision_id` with a different `strategy_id` represents
a different decision origin (e.g., aurora vs mean_reversion).

`reject_reason` is retained in the atom payload and provenance — it is NOT dropped from the atom.
It is only removed from the identity key.

## Incomplete Identity Handling

Two new fail-closed paths added to the processing loop:

| Condition | Counter | Outcome |
|---|---|---|
| `contract.decision_id` is None (no decision_id, no rid) | `incomplete_rejected_missing_identity` | Contract skipped, no atom |
| `contract.symbol` or `contract.side` or `contract.event_ts_ms` is None | `incomplete_rejected_missing_dedupe_key_fields` | Contract skipped, no atom |

Both counters are reported in the `## Deduplication` section of the FC report:
```
- incomplete_rejected_missing_identity: N
- incomplete_rejected_missing_dedupe_key_fields: N
```

The `_rejected_dedupe_key()` function itself now returns `str | None`, ensuring that if the
function is called directly (e.g., from `_atom_dedupe_key_from_payload` loading baseline SAF
atoms), it also returns `None` for missing-identity atoms rather than producing an unstable key.

## Tests

| # | Test | File | Status |
|---|---|---|---|
| 1 | Same decision_id/symbol/side/ts/strategy_id but different reject_reason → duplicate | test_sema_atom_rejected_dedupe_key.py | PASS |
| 2 | Different decision_id same reject_reason → not duplicate | test_sema_atom_rejected_dedupe_key.py | PASS |
| 3 | rid fallback works when decision_id resolved by collector | test_sema_atom_rejected_dedupe_key.py | PASS |
| 4 | Missing decision_id and rid → key is None | test_sema_atom_rejected_dedupe_key.py | PASS |
| 5 | Missing event_ts_ms → key is None | test_sema_atom_rejected_dedupe_key.py | PASS |
| 6 | Different strategy_id → not duplicate | test_sema_atom_rejected_dedupe_key.py | PASS |
| 7 | Dedupe report counts duplicates_detected / duplicates_skipped (end-to-end) | test_sema_atom_rejected_dedupe_key.py | PASS |
| 8 | Accepted dedupe key unchanged | test_sema_atom_rejected_dedupe_key.py | PASS |

## Validation Output

```
tests/test_sema_atom_rejected_dedupe_key.py — 8 passed
tests/test_sema_atom_forward_collector.py — 4 passed (regression: 0 failures)
tests/test_sema_atom_poc_02_real_log_adapter.py — 5 passed (regression: 0 failures)
tests/test_sema_atom_reference_price_recovery.py — 11 passed (regression: 0 failures)
tests/test_sema_atom_poc_03b_stability_filter_full.py — 6 passed
tests/test_sema_atom_poc_03_memory_verdict_validation.py — 5 passed
tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py — 2 passed
Total: 41 passed, 0 failures
```

## Residual Risks

- The `_rejected_dedupe_key()` function for contract objects (used in the processing loop) and
  the `_atom_dedupe_key_from_payload()` function (used for baseline SAF loading) now produce
  different intermediate variable names for the timestamp. The contract path uses `event_ts_ms`
  directly; the payload path reads `raw_contract.get("event_ts_ms")` via `_safe_int`. Both
  produce the same integer string in the final key. No mismatch risk.
- If a real corpus contains atoms written by the old key scheme (with reject_reason), those
  atoms will have a different baseline dedupe key under the new scheme. On the first FC run after
  this patch, old baseline atoms will not be recognized as duplicates for new-run atoms (because
  their stored keys use the old format). This is a **one-time corpus migration risk** — the first
  run may produce duplicate atoms for any re-collected slice that overlaps with the old baseline.
  Mitigation: restore and rerun from the canonical baseline SAF once the SAF is available. The
  issue is self-healing after one clean rerun.
- `strategy_id` defaults to `"aurora"` if absent in the contract. If the collector produces
  contracts with `strategy_id=None` for non-aurora strategies, they all collapse to the same
  `"aurora"` default. The collector already sets `strategy_id = _text(row.get("strategy_id")) or
  "aurora"` which mirrors this default.

## Next Recommended Step

```
1. Restore aurora_real_logs_v02.saf.jsonl
2. Rerun POC_02 to get real reference_price source-level histogram
3. Rerun FC on available slice to verify new dedupe key schema produces clean histogram
4. Run 72h runtime collection
5. Freeze logs
6. FC_01 new slice
7. FC_02 multi-slice revalidation
```
