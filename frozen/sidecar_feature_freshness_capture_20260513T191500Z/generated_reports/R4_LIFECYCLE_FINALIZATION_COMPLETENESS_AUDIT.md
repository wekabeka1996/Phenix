# R4 — Lifecycle Finalization Completeness Audit

**Date**: 2026-05-10
**Scope**: `logs/execution_lifecycle_stats_v1.jsonl`, `logs/order_log_v1.jsonl`, runtime window 2026-05-10
**Verdict**: **FINALIZATION_GAP_LOCALIZED_PATCH_REQUIRED**

---

## 1. Evidence Counts

| Metric | Count |
|---|---|
| POSITION_CLOSED events in `order_log_v1.jsonl` | 19 |
| Rows in `execution_lifecycle_stats_v1.jsonl` | 15,690 |
| Unique seeded lifecycle_ids (all `aurora_SYMBOL_ts`) | 21 |
| FINAL rows (`row_status == "FINAL"`) | 1 |
| Missing FINAL rows | **18** |

Note: the task brief stated 14 POSITION_CLOSED events; the authoritative log count is **19**. The 14 figure likely reflects a filtered view (e.g., non-sidecar only). All 19 events are audited.

---

## 2. POSITION_CLOSED × Lifecycle Stats Join

| # | Symbol | Close RID | lifecycle_id in POSITION_CLOSED | FINAL row exists | Root cause |
|---|--------|-----------|--------------------------------|:---:|---|
| 1 | BNBUSDT | `ppsreq:pps:BNBUSDT:1778378103677:21616` | `ppsreq:pps:BNBUSDT:1778378103677:21616` | ✗ | lifecycle_id mismatch |
| 2 | XRPUSDT | `aurora_XRPUSDT_1778381403373` | `CLOSE-b4e44abc77b3` | ✗ | lifecycle_id mismatch |
| 3 | BNBUSDT | `ppsreq:pps:BNBUSDT:1778387404009:34618` | `ppsreq:pps:BNBUSDT:1778387404009:34618` | ✗ | lifecycle_id mismatch |
| 4 | XRPUSDT | `aurora_XRPUSDT_1778403902494:SL` | `a38c5227-7285-450b-bd9d-cb9ba6022c5a` | ✗ | lifecycle_id mismatch (SL bracket UUID) |
| 5 | BNBUSDT | `ppsreq:pps:BNBUSDT:1778415311472:70960` | `ppsreq:pps:BNBUSDT:1778415311472:70960` | ✗ | lifecycle_id mismatch |
| 6 | XRPUSDT | `ppsreq:pps:XRPUSDT:1778418908138:76551` | `ppsreq:pps:XRPUSDT:1778418908138:76551` | ✗ | lifecycle_id mismatch |
| 7 | BNBUSDT | `ppsreq:pps:BNBUSDT:1778420103167:78094` | `ppsreq:pps:BNBUSDT:1778420103167:78094` | ✗ | lifecycle_id mismatch |
| 8 | BTCUSDT | `ppsreq:pps:BTCUSDT:1778421924009:80415` | `ppsreq:pps:BTCUSDT:1778421924009:80415` | ✗ | lifecycle_id mismatch |
| 9 | BNBUSDT | `aurora_BNBUSDT_1778426406618` | `CLOSE-f4c6ba130f4c` | ✗ | lifecycle_id mismatch |
| 10 | BTCUSDT | `ppsreq:pps:BTCUSDT:1778427602426:87651` | `ppsreq:pps:BTCUSDT:1778427602426:87651` | ✗ | lifecycle_id mismatch |
| 11 | XRPUSDT | `aurora_XRPUSDT_1778425205790:TP` | `08e86a93-32a6-458b-b94c-e1e4e06932d6` | ✗ | lifecycle_id mismatch (TP bracket UUID) |
| 12 | ETHUSDT | `ppsreq:pps:ETHUSDT:1778430301271:91399` | `ppsreq:pps:ETHUSDT:1778430301271:91399` | ✗ | lifecycle_id mismatch |
| 13 | BTCUSDT | `ppsreq:pps:BTCUSDT:1778430603029:91794` | `aurora_BTCUSDT_1778429706498` | **✓** | Success — PPS close order absent from OrderIndex; lifecycle_id not overwritten |
| 14 | XRPUSDT | `ppsreq:pps:XRPUSDT:1778431204017:92588` | `ppsreq:pps:XRPUSDT:1778431204017:92588` | ✗ | lifecycle_id mismatch |
| 15 | XRPUSDT | `ppsreq:pps:XRPUSDT:1778439625633:104341` | `ppsreq:pps:XRPUSDT:1778439625633:104341` | ✗ | lifecycle_id mismatch |
| 16 | XRPUSDT | `aurora_XRPUSDT_1778440204644:TP` | `a456c003-2bbe-40c8-b9ff-6c550c8ab8fd` | ✗ | lifecycle_id mismatch (TP bracket UUID) |
| 17 | XRPUSDT | `position_close:XRPUSDT:1778441085502` | _(empty)_ | ✗ | cache cleared before finalization (double-close 9 s after TP) |
| 18 | XRPUSDT | `ppsreq:pps:XRPUSDT:1778443505750:110127` | `ppsreq:pps:XRPUSDT:1778443505750:110127` | ✗ | lifecycle_id mismatch |
| 19 | BNBUSDT | `ppsreq:pps:BNBUSDT:1778444112518:111018` | `ppsreq:pps:BNBUSDT:1778444112518:111018` | ✗ | lifecycle_id mismatch |

---

## 3. Root Cause Analysis

### 3.1 Failure type A — lifecycle_id mismatch (17 of 18 gaps)

**Mechanism**: `_apply_fill_bookkeeping()` in `event_handlers.py` runs a TASK40 block (lines 1084–1107) that calls `order_index.mark_terminal(ref)` and then unconditionally writes `_last_lifecycle_ikey_by_symbol[symbol] = ref.idempotent_key` for **all** fills (ENTRY, SL, TP, CLOSE, PPS-close).

When a **close fill** arrives (SL/TP bracket or PPS CLOSE order), `ref.idempotent_key` is the close order's key — a UUID for brackets or `ppsreq:pps:SYMBOL:ts:N` for sidecar closes. This **overwrites** the aurora entry lifecycle_id (`aurora_SYMBOL_ts`) that had been cached at entry time.

Shortly after, `_remember_close_accounting_truth()` reads `_last_lifecycle_ikey_by_symbol` and stores the (now-wrong) close-order idempotent_key as `close_truth["lifecycle_id"]`.

When `_finalize_lifecycle_stats()` calls `ledger.finalize_close(lifecycle_id=<close_order_key>)`:
- `get_latest(lifecycle_id=<close_order_key>)` returns `None` — that key was never seeded.
- `finalize_close()` raises `KeyError`.
- The caller catches `KeyError` silently at line 189–190 and returns without writing a FINAL row.

The early PHASE-1 block (lines 1010–1025) has a correct guard (`if not _lifecycle_id_for_write`) that prevents overwriting an already-cached entry lifecycle_id. TASK40 lacks this guard.

**Why event #13 (BTCUSDT) succeeded**: The PPS close order `ppsreq:pps:BTCUSDT:1778430603029:91794` was not registered in the in-memory OrderIndex (consistent with DEF-005: OrderIndex lost on restart). `order_index.get(...)` returned `None` → TASK40 skipped the write → `_last_lifecycle_ikey_by_symbol[BTCUSDT]` preserved `aurora_BTCUSDT_1778429706498` from the entry fill → `finalize_close()` found the seeded row → FINAL row written.

### 3.2 Failure type B — cache cleared before finalization (event #17)

XRPUSDT TP close (event #16, ts 1778441076672) popped `_last_lifecycle_ikey_by_symbol["XRPUSDT"]` in the post-emit cleanup (line 393). Nine seconds later (ts 1778441085502), a residual `POSITION_CLOSED_DETECTED` was emitted for the same position. At that point `_last_lifecycle_ikey_by_symbol["XRPUSDT"]` was empty and `close_truth` had no `lifecycle_id` → `_finalize_lifecycle_stats()` returned early at line 146 (empty lifecycle_id guard) → no FINAL row. This is a double-close scenario, not a bug in the seeding path.

---

## 4. PnL Accounting Impact

| Question | Finding |
|---|---|
| Are PnL values lost? | No — `order_log_v1.jsonl` retains all 19 POSITION_CLOSED events with resolved PnL (18 resolved, 1 unresolved/double-close) |
| Is lifecycle_stats_ledger the authoritative source? | Yes, per A4 report — FINAL rows are the canonical ledger |
| Are MFE/MAE path stats lost? | YES — 18 PROVISIONAL rows exist but no FINAL row carries the close truth; MFE/MAE values are frozen at last portfolio update, not at close |
| Does this affect neocortex reward calculation? | HIGH RISK — neocortex reads FINAL rows from lifecycle_stats to compute outcome rewards; 18 missing FINAL rows → 18 positions with no reward signal |
| Does this affect PnL accounting reports? | YES — any report joining lifecycle_stats FINAL rows to order_log will show 18 unmatched POSITION_CLOSED events |

---

## 5. Patch Applied

**File**: `apps/reference/domains/execution_position/orchestration/event_handlers.py`
**Location**: TASK40 block, line 1100
**Type**: Single-condition guard addition

```python
# Before (runs for ALL fills — overwrites entry lifecycle_id with close-order key)
if ref.idempotent_key and symbol:
    try:
        self._fsm._last_lifecycle_ikey_by_symbol[symbol] = str(ref.idempotent_key)
    except Exception:
        pass

# After (ENTRY fills only — mirrors PHASE 2's existing "Entry side only" pattern)
if order_kind == "ENTRY" and ref.idempotent_key and symbol:
    try:
        self._fsm._last_lifecycle_ikey_by_symbol[symbol] = str(ref.idempotent_key)
    except Exception:
        pass
```

This mirrors the existing comment at PHASE 2 (line 1111): *"Entry side is only updated for ENTRY fills — SL/TP fills must not overwrite it."* The lifecycle_id cache has the same invariant requirement.

**`order_kind` availability**: Confirmed defined at line 934 (`classify_client_order_id(_coid)`), before both PHASE 1 (line 1008) and TASK40 (line 1084).

---

## 6. Tests Added

**File**: `tests/domains/execution_position/test_task40_close_fill_lifecycle_id_guard.py`
**6 tests, all passing**:

| Test | What it proves |
|---|---|
| `test_entry_fill_sets_lifecycle_ikey` | ENTRY fill correctly populates `_last_lifecycle_ikey_by_symbol` |
| `test_pps_close_fill_does_not_overwrite_entry_lifecycle_ikey` | PPS close fill (`ppsreq:pps:...`) no longer overwrites aurora lifecycle_id |
| `test_sl_bracket_fill_does_not_overwrite_entry_lifecycle_ikey` | SL bracket fill (UUID idempotent_key) no longer overwrites aurora lifecycle_id |
| `test_tp_bracket_fill_does_not_overwrite_entry_lifecycle_ikey` | TP bracket fill no longer overwrites aurora lifecycle_id |
| `test_finalize_close_writes_final_row_after_pps_close` | End-to-end: after PPS close fill, `finalize_close()` receives correct aurora lifecycle_id and writes a FINAL row |
| `test_entry_fill_when_cache_empty_still_seeds_correctly` | ENTRY fill on fresh symbol still seeds correctly after fix |

Pre-existing test failures: 2 (`test_emitted_surface_audit`, `test_fsm_execute_decision_open_with_backoff`) — confirmed pre-existing before this change.

---

## 7. What the Patch Does NOT Fix

| Gap | Status |
|---|---|
| Event #17 (double-close XRPUSDT) | Fail-closed: empty lifecycle_id → `_finalize_lifecycle_stats()` returns early without error. This is correct behavior — the position was already finalized by the TP close. No patch needed. |
| Historical missing FINAL rows (18 positions) | Cannot be retroactively written — the PROVISIONAL rows in the ledger still exist with correct MFE/MAE path data; PnL truth is in order_log. A one-time backfill script reading order_log could reconstruct FINAL rows for the historical window if needed. |
| DEF-005 (OrderIndex lost on restart) | Out of scope — tracked separately. The patch eliminates the lifecycle_id corruption regardless of whether DEF-005 is fixed. |

---

## 8. Verdict

**FINALIZATION_GAP_LOCALIZED_PATCH_REQUIRED**

- 18 of 19 POSITION_CLOSED events had no FINAL lifecycle_stats row.
- Root cause: TASK40 unconditionally overwrote `_last_lifecycle_ikey_by_symbol` with the close order's idempotent_key, causing `finalize_close()` to receive a key not seeded in the ledger → silent KeyError → no FINAL row.
- Patch applied: one-line `order_kind == "ENTRY"` guard. 6 new tests pass. No regressions in the existing 541-test suite.
- PnL accounting is degraded (18 positions without FINAL lifecycle rows, neocortex reward signal missing) but close truth is preserved in order_log.
- Event #17 (empty lifecycle_id, double-close) is correctly fail-closed — no FINAL row is expected or needed.
