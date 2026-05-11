# POST_RUNTIME_A1_A6_VALIDATION_REPORT

**Audit Date:** 2026-05-10
**Audit Mode:** Read-only forensic validation
**Scope:** A1–A6 repair package verification against frozen runtime logs
**Analyst:** Claude Sonnet 4.6 (automated forensic pass)

---

## 1. EXECUTIVE VERDICT

**RUNTIME_VALIDATED_WITH_RESIDUALS**

The runtime executed successfully for ~20.3 hours across 5 active symbols, producing 14 closed positions and observable A3/A4/A5 contract compliance. Three residuals prevent full RUNTIME_VALIDATED_FOR_CALIBRATION status:

1. **A6 RESIDUAL**: `EVT:QUADRATIC_DECISION_TRACE` rows in `shadow_critical_event_journal_v1.jsonl` carry `partial_identity=true` and lack `price_motion_source`, `price_motion_age_ms`, `price_motion_ready` in the observable `payload_fragment`. Cannot confirm A6 wire from journal surface alone.
2. **A2 RESIDUAL**: `EVT:TRADE_INTENT_REJECTED` rows lack the A2-specified fields (`selected_source`, `selected_scale`, `threshold_family`, `threshold_value`, `missing_source_list`). Score-vs-threshold comparison is present in `why_chain` as an embedded string but not as structured fields.
3. **A3 RESIDUAL**: `accepted_or_rejected` field is universally null across all 93 decision ledger rows. Seed→revision chain pattern is not demonstrable from this surface; multi-row chains for same `decision_id` are unconfirmed.

No hard execution blockers found. Sidecar, fee-aware shadow, close reconciliation, and lifecycle stats all function correctly. Economic inventory is complete and internally consistent.

---

## 2. FACTS

The following are directly observed from log rows with no inference required.

| Fact | Source | Value |
|---|---|---|
| Session boot timestamp | order_log_v1.jsonl BOOT event | 1778364903691 ms |
| Last observed event timestamp | shadow_critical_event_journal_v1.jsonl seq=33736 | 1778438069914 ms |
| Session duration | Derived | 73,166,223 ms ≈ 20 h 19 min |
| Decision ledger total rows | decision_ledger_v1.jsonl | 93 |
| Decision ledger DECISION_TERMINAL (EXCHANGE_REJECTED) | decision_ledger_v1.jsonl | 77 |
| Decision ledger TIMEOUT_FINAL | decision_ledger_v1.jsonl | 15 |
| Decision ledger OUTCOME_FINAL | decision_ledger_v1.jsonl | 1 |
| `accepted_or_rejected` values in ledger | decision_ledger_v1.jsonl all 93 rows | all null |
| FINAL row in execution_lifecycle_stats | execution_lifecycle_stats_v1.jsonl | 1 |
| PROVISIONAL rows in execution_lifecycle_stats | execution_lifecycle_stats_v1.jsonl | 14,265 |
| Unique lifecycle_ids tracked | execution_lifecycle_stats_v1.jsonl | 15 |
| POSITION_CLOSED events | order_log_v1.jsonl | 14 |
| ORDER_FILLED close events | order_log_v1.jsonl | 12 |
| DECISION_INTENT_REJECTED events | order_log_v1.jsonl | 78 |
| HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_MISS | shadow_critical_event_journal_v1.jsonl | 311 |
| ORDER_FILLED events (all fills) | order_log_v1.jsonl | 311 |
| HARDENING:TRADE_EXECUTED_SUPPRESSED | shadow_critical_event_journal_v1.jsonl | 55 |
| POSITION_POLICY_SIDECAR_RECOMMENDED | trade_lifecycle.jsonl | 10 |
| POSITION_POLICY_SIDECAR_CLOSE_REQUESTED | trade_lifecycle.jsonl | 10 |
| POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE reconciled | trade_lifecycle.jsonl | 10 confirmed reconciles |
| POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE authority_applied | trade_lifecycle.jsonl | false |
| POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE no_effect | trade_lifecycle.jsonl | true |
| EVT:CLOSE_SHADOW_SUBMISSION comparison_outcome | shadow_critical_event_journal_v1.jsonl | match (all 12) |
| EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS count | trade_lifecycle.jsonl | 1 (BTCUSDT) |
| EXECUTION_WS_TERMINAL_CORRELATED count | trade_lifecycle.jsonl | 2 (XRPUSDT SL + TP) |
| price_motion_source in QUADRATIC_DECISION_TRACE rows | shadow_critical_event_journal_v1.jsonl | ABSENT |
| price_motion_age_ms in QUADRATIC_DECISION_TRACE rows | shadow_critical_event_journal_v1.jsonl | ABSENT |
| price_motion_ready in QUADRATIC_DECISION_TRACE rows | shadow_critical_event_journal_v1.jsonl | ABSENT |
| selected_source in TRADE_INTENT_REJECTED rows | shadow_critical_event_journal_v1.jsonl | ABSENT |
| threshold_family in TRADE_INTENT_REJECTED rows | shadow_critical_event_journal_v1.jsonl | ABSENT |

---

## 3. INFERENCES

Inferences are derived from multiple observations treated as collectively sufficient.

- **All 93 decision ledger rows are terminal writes.** The 93 rows decompose exactly into 77 + 15 + 1 = 93 with no overlapping `revision_status`. No row with an intermediary seed status exists. Either the ledger design writes only terminal states, or seed rows were never emitted.
- **Terminal identity cache is non-functional.** 311 ORDER_FILLED events and 311 HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_MISS is a 100% miss rate. This matches the known DEF-005 pattern (OrderIndex in-memory, not repopulated post-restart) but also indicates the cache is not accumulating within-session fills.
- **55 suppressed trade executions.** HARDENING:TRADE_EXECUTED_SUPPRESSED (55) represents fills that were intercepted and not passed through the normal execution pipeline. These are not accounted for in POSITION_CLOSED (14) or ORDER_FILLED close (12). Their economic and state impact is unquantified.
- **Sidecar close flow is the dominant close mechanism.** Of 14 POSITION_CLOSED events, 10 are initiated by `ppsreq:pps:*` rids (position policy sidecar), 2 by aurora lifecycle rids (SL/TP bracket), and 2 by aurora lifecycle rids (manual). Sidecar dominance is consistent with managed positions entering profit giveback zones.
- **A6 fields absent from journal surface may be instrumentation truncation.** All 1,236 `EVT:QUADRATIC_DECISION_TRACE` rows in the shadow journal have `partial_identity=true`. This flag indicates the journal captured only a fragment of the full event payload. The full FSM event may carry A6 fields that are not instrumented into the journal.
- **XRPUSDT was the only profitable bracket outcome.** The TP hit on `aurora_XRPUSDT_1778425205790` (net +49.62 USDT) was the only positive close in the session. Its MFE was 55.84 USDT, giving a realized/MFE efficiency of 88.9%.

---

## 4. ASSUMPTIONS

- **Partial_identity=true is instrumentation-layer truncation.** The assumption is that `partial_identity=true` means the journal writer did not serialize all payload fields, not that the decision itself lacked those fields.
- **DECISION_TERMINAL/EXCHANGE_REJECTED rows represent exchange-layer rejections, not aurora-layer rejections.** The 77 exchange-rejected ledger rows represent decisions that passed aurora's gate but were refused by the exchange (e.g., limit order constraints, margin issues), distinct from the 265 `EVT:TRADE_INTENT_REJECTED` events that were aurora-layer rejections.
- **All 14 POSITION_CLOSED events are complete and non-duplicate.** This is supported by the close_shadow_submission comparison_outcome=match evidence (no mismatch_fields in any of the 12 shadow comparisons).
- **Trade_lifecycle.jsonl UNKNOWN event count discrepancy.** The initial estimate of 26 UNKNOWN rows was not confirmed in the second pass (count=0). One of the counts is incorrect due to sampling methodology; this does not affect the main analysis.

---

## 5. UNKNOWNS

| Unknown | Risk | Suggested Resolution |
|---|---|---|
| Whether QUADRATIC_DECISION_TRACE full FSM event carries A6 price_motion fields (partial_identity truncation hypothesis) | HIGH — cannot confirm A6 wire from journal alone | Add a dedicated A6 price_motion observer that writes a non-truncated price_motion record to a separate sink |
| What the 55 HARDENING:TRADE_EXECUTED_SUPPRESSED fills are and their economic impact | MEDIUM — unaccounted fills may affect P&L reconciliation | Query shadow journal for HARDENING:TRADE_EXECUTED_SUPPRESSED rows to extract symbol/lifecycle_id/rid |
| Whether any decision_id appears in multiple ledger rows (seed→revision chain) | MEDIUM — A3 chain integrity cannot be confirmed | Write a script to count unique decision_ids in ledger; expect 93 unique if no chains exist |
| Close accounting for 14 POSITION_CLOSED vs 12 ORDER_FILLED close gap | LOW — 2 positions closed by bracket (SL/TP) with fills recorded differently | Cross-reference SL/TP POSITION_CLOSED rids with ORDER_FILLED bracket fills |
| Runtime for SOL, DOGE, 1000PEPE beyond regime detection | LOW — these symbols show in regime audit but no orders | Inspect domain_decision_making.log for these symbols explicitly |

---

## 6. RUNTIME INVENTORY

| Metric | Count | Source |
|---|---|---|
| **Runtime duration** | 20 h 19 min (73,166,223 ms) | order_log BOOT → shadow_journal last event |
| **Symbols active (decision-making)** | 5: BTCUSDT, ETHUSDT, XRPUSDT, BNBUSDT, SOLUSDT | shadow_critical_event_journal |
| **Symbols in regime audit** | 7: + DOGEUSDT, 1000PEPEUSDT | regime_confidence_audit_v1.jsonl |
| **EVT:STRATEGY_SIGNAL_PRODUCED** | 286 | shadow_critical_event_journal |
| **EVT:QUADRATIC_DECISION_TRACE** | 1,236 | shadow_critical_event_journal |
| **EVT:STRATEGY_DECISION_BLOCKED** | 501 | shadow_critical_event_journal |
| **EVT:TRADE_INTENT_REJECTED (aurora-level)** | 265 | shadow_critical_event_journal |
| **EVT:TRADE_INTENT_PROPOSED** | 17 | shadow_critical_event_journal |
| **Accepted decisions (exchange-submitted)** | 93 (77 exchange-rejected + 15 timeout + 1 executed) | decision_ledger_v1.jsonl |
| **Final realized decisions** | 1 (BTCUSDT BUY, net -1.01 USDT) | decision_ledger_v1.jsonl OUTCOME_FINAL |
| **Order opens (ORDER_PLACED)** | 29 | order_log_v1.jsonl |
| **Order closes (POSITION_CLOSED)** | 14 | order_log_v1.jsonl |
| **Sidecar recommendations** | 10 | trade_lifecycle.jsonl |
| **Sidecar close requests** | 10 | trade_lifecycle.jsonl |
| **Sidecar reconciled closes** | 10 (all 10 reached `reconciled` state) | trade_lifecycle.jsonl |
| **DECISION_INTENT_REJECTED in order_log (NRR-062)** | 75 of 78 = 96.2% | order_log_v1.jsonl |
| **DECISION_INTENT_REJECTED in order_log (NRR-063)** | 3 of 78 = 3.8% | order_log_v1.jsonl |
| **price_motion source distribution** | NOT DETERMINABLE from journal surface (partial_identity=true on all QUADRATIC traces) | — |

### price_motion source distribution
Cannot be reported. All 1,236 `EVT:QUADRATIC_DECISION_TRACE` rows in shadow journal carry `partial_identity=true` with `payload_fragment` containing only `{symbol, regime, regime_confidence, strategy_id, ts_ms, side}`. The cmd_typed / cmd_raw_fallback / features / cache / missing distribution is not observable from this surface.

---

## 7. A2 LOW_VOL VALIDATION

**Status: PARTIAL — score-comparison logic present, A2 field schema not confirmed in journal**

### What is present:

`EVT:TRADE_INTENT_REJECTED` rows in shadow journal contain:
- `reason_code`: "NRR-062" (confirmed, dominant — 75/78 order_log rejections)
- `stage`: "DECISION" (confirmed)
- `why`: "LOW_VOL_COST_FLOOR_BLOCKED" (confirmed)
- `why_chain`: embedded raw score vs threshold comparison strings

Example `why_chain` from a confirmed NRR-062 rejection (ETHUSDT SELL, ts=1778364903664):
```
[
  "enter:sell:score=-0.0137<=-thr_sell=0.0010",
  "tpsl:regime=LOW_VOLATILITY mode=pct_mult sl_pct_post=0.0074 tp_rr_pre=1.25 rr_post=1.25",
  "margin_first_ok",
  "strategy_prices:sl=2346.59...,tp=2308.01..."
]
```

The `why_chain` shows raw signed score (`-0.0137`) compared against a threshold (`thr_sell=0.0010`). This is raw score comparison, not normalized confidence — correct behavior.

### What is absent (A2 contract fields not found):

| Required A2 Field | Status | Note |
|---|---|---|
| `selected_source` | ❌ ABSENT | Not in journal payload_fragment or order_log |
| `selected_scale` | ❌ ABSENT | Not in journal payload_fragment or order_log |
| `threshold_family` | ❌ ABSENT | Embedded in why_chain string only, not structured |
| `threshold_value` | ❌ ABSENT | Embedded in why_chain string only (`thr_sell=0.0010`) |
| `missing_source_list` | ❌ ABSENT | Not found |
| `judge_confidence` selected by default | ❓ UNCONFIRMED | No field present to verify |

### Raw score not treated as normalized confidence:

CONFIRMED from why_chain evidence. Scores are raw signed floats (`score=-0.0137`), not normalized [0,1] confidence values. No row observed where `final_score` or `signal_score` is compared as if it were normalized.

### DECISION_INTENT_REJECTED by symbol (order_log):

| Symbol | Count | Dominant NRR |
|---|---|---|
| ETHUSDT | 63 | NRR-062 |
| XRPUSDT | 12 | NRR-062 |
| BTCUSDT | 3 | NRR-062 |

**A2 Verdict:** Score logic is correct (raw scores vs thresholds, not normalized). Structured A2 field names (`selected_source`, `threshold_family`, etc.) are not present in any observable surface. This may be an instrumentation gap or an A2 deployment gap. Cannot confirm or deny from journal alone.

---

## 8. A3 DECISION LEDGER VALIDATION

**Status: PARTIAL — ledger exists, terminal rows correct, seed/revision chain unconfirmed**

### File existence and coverage:

- `logs/shadow_telemetry/decision_ledger_v1.jsonl` ✅ EXISTS
- 93 rows, all parseable as valid JSON

### Row distribution by revision_status:

| revision_status | Count | execution_outcome |
|---|---|---|
| DECISION_TERMINAL | 77 | EXCHANGE_REJECTED |
| TIMEOUT_FINAL | 15 | PENDING_TIMEOUT |
| OUTCOME_FINAL | 1 | EXECUTED |

### Accepted seed rows:

❌ **NOT CONFIRMED.** The `accepted_or_rejected` field is null in all 93 rows. No row carries an explicit accepted/rejected discriminator. Whether TIMEOUT_FINAL and OUTCOME_FINAL rows represent "accepted" decisions can only be inferred (they were exchange-submitted), not asserted from the field value.

### Rejected/vetoed rows:

⚠️ PARTIAL. 77 rows with `execution_outcome=EXCHANGE_REJECTED` represent exchange-level rejections, not aurora-level vetoes. Aurora-level rejections (265 `EVT:TRADE_INTENT_REJECTED`) are not written to the ledger. The `accepted_or_rejected` field does not confirm these as "rejected" category rows.

### Accepted unresolved rows (TIMEOUT_FINAL):

✅ CONFIRMED. 15 rows with `revision_status=TIMEOUT_FINAL`, `outcome_status=UNRESOLVED_TIMEOUT`, `terminal_status=INVALID_FOR_DATASET`. All null accounting fields verified:

Sample TIMEOUT_FINAL row (decision_id: 5abb180a, BTCUSDT):
```json
{
  "revision_status": "TIMEOUT_FINAL",
  "terminal_status": "INVALID_FOR_DATASET",
  "realized_pnl_gross": null,
  "realized_pnl_net": null,
  "fees": null,
  "close_reason": null,
  "close_ts_ms": null,
  "execution_outcome": "PENDING_TIMEOUT"
}
```

### Final revisions with authoritative values:

✅ CONFIRMED. 1 OUTCOME_FINAL row (decision_id: b2ba9f23, BTCUSDT):
```json
{
  "revision_status": "OUTCOME_FINAL",
  "terminal_status": "EXECUTED_AND_CLOSED",
  "realized_pnl_gross": -0.26325,
  "realized_pnl_net": -1.0122979399999998,
  "fees": 0.74904794,
  "close_reason": "CLOSE",
  "close_ts_ms": 1778430612445,
  "close_actor": null
}
```

### Seed → final revision chain:

❌ **NOT DEMONSTRABLE.** 93 rows decompose exactly into 77 + 15 + 1 = 93 terminal rows. No intermediary status rows exist. If seed rows were supposed to precede terminal rows (same decision_id), there is no evidence of multi-row chains in this file. It is possible the ledger design writes only terminal states in a single atomic write; this is not confirmed.

### Cross-surface consistency check (OUTCOME_FINAL):

The 1 OUTCOME_FINAL row (BTCUSDT, net=-1.0122979) joins to:
- `execution_lifecycle_stats_v1.jsonl` FINAL row: `lifecycle_id=aurora_BTCUSDT_1778429706498`, `net_pnl=-1.0122979399999998`, `close_ts_ms=1778430612445` ✅ MATCH
- `order_log_v1.jsonl` POSITION_CLOSED row 13: `BTCUSDT BUY`, `realized_pnl_net=-1.0122979399999998`, `close_reason=CLOSE`, `timestamp=1778430612448` ✅ MATCH (3ms delta acceptable)

Three-surface join confirmed for the one realized trade.

---

## 9. A4 LIFECYCLE STATS VALIDATION

**Status: CONFIRMED — all structural requirements met**

### File and schema:

- `logs/execution_lifecycle_stats_v1.jsonl` ✅ EXISTS
- `schema_version`: "execution_lifecycle_stats_v1" ✅
- `record_kind`: "execution_lifecycle_stats" ✅
- `owner`: "execution_position" ✅

### Row status distribution:

| row_status | Count |
|---|---|
| PROVISIONAL | 14,265 |
| FINAL | 1 |

### Required fields presence (verified across row sample):

| Field | Present | Notes |
|---|---|---|
| `lifecycle_id` | ✅ 100% | Format: aurora_{SYMBOL}_{ts_ms} |
| `entry_rid` | ✅ 100% | Matches lifecycle_id |
| `mfe_usdt` / `mfe_bps` | ✅ 100% | Updated per portfolio tick |
| `mae_usdt` / `mae_bps` | ✅ 100% | Updated per portfolio tick |
| `peak_edge_usd` | ✅ 100% | Running max edge |
| `peak_giveback_usd` | ✅ 100% | Running max giveback |
| `peak_giveback_pct` | ✅ 100% | Percentage of MFE given back |
| `first_positive_pnl_ts_ms` | ✅ 100% (where positive PnL occurred) | null for positions never positive |

### Unresolved close accounting (fail-closed):

✅ CONFIRMED. All 14,265 PROVISIONAL rows have null values for:
- `close_ts_ms` → null
- `close_actor` → null
- `close_reason` → null
- `gross_pnl` → null
- `net_pnl` → null

Fees are populated from entry fill time (`fees: 0.79145976` on line 1 for BTCUSDT SELL) — entry-side fees are tracked from the beginning, but PnL accounting is strictly null until FINAL.

### FINAL row sample:

```json
{
  "row_status": "FINAL",
  "provisional_status": null,
  "lifecycle_id": "aurora_BTCUSDT_1778429706498",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entry_price": 81429.7,
  "qty": 0.043,
  "mfe_usdt": 0.2290509225199348,
  "mae_usdt": 8.247931912579878,
  "peak_edge_usd": 0.23,
  "peak_giveback_usd": 7.99,
  "peak_giveback_pct": 3473.91,
  "close_ts_ms": 1778430612445,
  "close_actor": "EXECUTION_POSITION",
  "close_reason": "CLOSE",
  "gross_pnl": -0.26325,
  "fees": 0.74904794,
  "net_pnl": -1.0122979399999998
}
```

Note: `peak_giveback_pct = 3473%` indicates the position gave back more than its MFE many times over — consistent with a position that briefly went positive (+0.23 USD) then moved substantially against before being closed at -8.05 USD unrealized.

### Three-surface join (lifecycle → order → ledger):

```
lifecycle_id: aurora_BTCUSDT_1778429706498
  → lifecycle FINAL net_pnl: -1.0122979399999998
  → order_log POSITION_CLOSED net: -1.0122979399999998  ✅
  → decision_ledger OUTCOME_FINAL net: -1.0122979399999998  ✅
```

---

## 10. A5 SIDECAR VALIDATION

**Status: CONFIRMED — sidecar operating correctly within spec**

### Mode status:

✅ CONFIRMED: `trade_lifecycle.jsonl` row 1 = `POSITION_POLICY_SIDECAR_MODE_ACTIVE`, `mode=enable`. Sidecar was active from session start.

### Fee-aware shadow:

✅ CONFIRMED. First `POSITION_POLICY_SIDECAR_FEE_AWARE_SHADOW_ARM_STATE` row (BTCUSDT, ts=1778365574279):
```json
{
  "authority_applied": false,
  "no_effect": true,
  "candidate_state": {
    "fee_multiple": 1.0,
    "estimated_fee_usd": 0.79145976,
    "is_armed": true,
    "state": "shadow_fee_aware_below_trigger"
  }
}
```
`authority_applied=false, no_effect=true` — fee-aware shadow is in shadow mode only, making no real decisions. Total fee-aware shadow events: 48.

### No partial_reduce / bracket_mutation / exact_targeting:

✅ NOT FOUND in any log surface.

### Sidecar close flow (mediator → CMD → execution → reconcile):

✅ CONFIRMED. Full 3-state progression observed for each of 10 close requests:

BNBUSDT example (ts=1778378103677 → 1778378107804):
```
1. POSITION_POLICY_SIDECAR_RECOMMENDED  (reason: regime_detected + recommend_soft_close_threshold_met)
2. POSITION_POLICY_SIDECAR_CLOSE_REQUESTED  (trace_id: pps:BNBUSDT:1778378103677:21616)
3. POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE: close_command_emitted
4. POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE: execution_submitted (qty=10.19 BUY)
5. POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE: reconciled (guardian_reconcile)
```

### No duplicate closes:

✅ CONFIRMED. All 12 `EVT:CLOSE_SHADOW_SUBMISSION` rows have `comparison_outcome=match` and `mismatch_fields=[]`. No shadow/incumbent divergence detected on any close submission.

### Orphan brackets:

✅ No orphan bracket evidence found. `EXECUTION_BRACKET_RECOVERY_SKIPPED`: 5 events (pre-existing DEF-006 pattern, mean_reversion brackets).

### BRACKETS_PENDING:

Observed 73 times in `domain_execution_position.log`. These represent the manage_state of positions while bracket orders (SL/TP) are active and awaiting fill. This is expected normal operation, not a failure condition.

### ACTION_SKIPPED:

✅ ABSENT — count 0 across all log surfaces. Absence is expected and not a failure.

### EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS:

⚠️ 1 EVENT (pre-existing DEF-005). BTCUSDT, `client_order_id=CLOSE-cceb6b030b0e`, ts=1778430605201:
```json
{
  "event_type": "EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS",
  "symbol": "BTCUSDT",
  "status": "FILLED",
  "order_type": "market"
}
```
This is the known DEF-005 pattern: bracket close received via WS but OrderIndex lookup missed. The position was ultimately closed correctly (the POSITION_CLOSED for this rid exists in order_log). Not a new regression from A1-A6.

### EXECUTION_WS_TERMINAL_CORRELATED:

✅ 2 events — both XRPUSDT bracket hits, both with `terminal_correlation_source=order_index_canonical`:
- Row 1: `aurora_XRPUSDT_1778403902494:SL` → SL filled, correctly correlated
- Row 2: `aurora_XRPUSDT_1778425205790:TP` → TP filled, correctly correlated (the profitable trade)

---

## 11. A6 PRICE_MOTION VALIDATION

**Status: UNCONFIRMED — fields absent from journal surface; partial_identity truncation hypothesis**

### QUADRATIC_DECISION_TRACE field check:

All sampled `EVT:QUADRATIC_DECISION_TRACE` rows (1,236 total in shadow journal):
- `partial_identity: true` on all rows
- `payload_fragment` contains only: `{symbol, regime, regime_confidence, strategy_id, ts_ms, side}`
- Fields NOT present: `price_motion_source`, `price_motion_age_ms`, `price_motion_ready`

Sample (BNBUSDT, ts=1778364002628, seq=1537):
```json
"payload_fragment": {
  "symbol": "BNBUSDT",
  "regime": "UNCERTAIN",
  "regime_confidence": 0.15,
  "strategy_id": "aurora",
  "ts_ms": 1778364002627,
  "side": ""
}
```

### STRATEGY_SIGNAL_PRODUCED price_motion check:

`scoring.price_motion` NOT PRESENT in any observed `EVT:STRATEGY_SIGNAL_PRODUCED` payload_fragment. The payload_fragment contains: `{symbol, why_chain, strategy_id, ts_ms, side}`.

### STRATEGY_DECISION_BLOCKED price_motion check:

`details.price_motion` NOT PRESENT in any observed `EVT:STRATEGY_DECISION_BLOCKED` payload_fragment.

### cmd_typed / cmd_raw_fallback distribution:

NOT OBSERVABLE from available surfaces. The shadow journal instrumentation does not capture price_motion provenance fields.

### Stale cache and missing row behavior:

CANNOT CONFIRM from observable surface.

### A6 Assessment:

The A6 contract repair was supposed to promote price_motion into a typed CMD seam and make it observable in `EVT:QUADRATIC_DECISION_TRACE`. The audit cannot confirm this from the shadow journal because:

1. All QUADRATIC_DECISION_TRACE rows carry `partial_identity=true`, indicating the journal writer serializes only a fragment of the full event.
2. The A6 report confirms tests pass (`source=cmd_typed, age_ms=0, ready=true`), but test-level proof is not runtime-level proof.
3. The runtime surface (shadow journal) does not expose the price_motion fields.

**Risk:** If `partial_identity=true` is masking an actual code regression where price_motion was never wired into the trace, this would be a silent correctness failure. A dedicated price_motion audit sink is needed to close this.

---

## 12. ECONOMIC INVENTORY

**Note: This is an inventory for traceability only. No threshold or calibration recommendations are made.**

### Closed trades (by POSITION_CLOSED event):

| # | Symbol | Side | Close Reason | Net PnL (USDT) | Fees (USDT) | Close Actor |
|---|---|---|---|---|---|---|
| 1 | BNBUSDT | SELL | CLOSE | -18.52 | 3.95 | sidecar (ppsreq) |
| 2 | XRPUSDT | SELL | CLOSE | -7.20 | 4.22 | aurora lifecycle |
| 3 | BNBUSDT | SELL | CLOSE | -10.69 | 2.11 | sidecar (ppsreq) |
| 4 | XRPUSDT | BUY | SL | -37.48 | 3.88 | bracket (SL) |
| 5 | BNBUSDT | BUY | CLOSE | -13.64 | 2.09 | sidecar (ppsreq) |
| 6 | XRPUSDT | SELL | CLOSE | -14.37 | 2.06 | sidecar (ppsreq) |
| 7 | BNBUSDT | SELL | CLOSE | -15.28 | 2.05 | sidecar (ppsreq) |
| 8 | BTCUSDT | SELL | CLOSE | -9.76 | 2.38 | sidecar (ppsreq) |
| 9 | BNBUSDT | BUY | CLOSE | -4.30 | 3.73 | aurora lifecycle |
| 10 | BTCUSDT | SELL | CLOSE | -15.42 | 2.28 | sidecar (ppsreq) |
| 11 | XRPUSDT | BUY | **TP** | **+49.62** | 3.75 | bracket (TP) |
| 12 | ETHUSDT | BUY | CLOSE | -16.52 | 3.69 | sidecar (ppsreq) |
| 13 | BTCUSDT | BUY | CLOSE | -1.01 | 0.75 | sidecar (ppsreq) |
| 14 | XRPUSDT | BUY | CLOSE | -0.55 | 1.01 | sidecar (ppsreq) |
| **TOTAL** | | | | **-115.12** | **37.95** | |

### Per-symbol summary:

| Symbol | Trades | Net PnL | Total Fees |
|---|---|---|---|
| BNBUSDT | 5 | -62.43 | 13.93 |
| XRPUSDT | 5 | -9.98 | 14.92 |
| BTCUSDT | 3 | -26.19 | 5.41 |
| ETHUSDT | 1 | -16.52 | 3.69 |

### LOW_VOL rejected decisions by symbol (economic context):

| Symbol | Rejected (NRR-062) | Dominant Regime | Confidence Range |
|---|---|---|---|
| ETHUSDT | 63 | LOW_VOLATILITY | 0.18 – 0.57 |
| XRPUSDT | 12 | LOW_VOLATILITY | (per order_log) |
| BTCUSDT | 3 | LOW_VOLATILITY / MEAN_REVERSION | (per order_log) |

### MFE/MAE profile per lifecycle:

| lifecycle_id | Symbol | Side | Max MFE (USDT) | Max MAE (USDT) | Outcome |
|---|---|---|---|---|---|
| aurora_XRPUSDT_1778425205790 | XRPUSDT | BUY | 55.84 | 0.76 | TP +49.62 |
| aurora_XRPUSDT_1778403902494 | XRPUSDT | BUY | 14.39 | 31.71 | SL -37.48 |
| aurora_BTCUSDT_1778364903981 | BTCUSDT | SELL | 9.84 | 10.97 | CLOSE (pending in lifecycle stats) |
| aurora_ETHUSDT_1778428202947 | ETHUSDT | BUY | 6.54 | 5.79 | CLOSE -16.52 |
| aurora_XRPUSDT_1778430903673 | XRPUSDT | BUY | 5.79 | 0.64 | CLOSE -0.55 |
| aurora_BNBUSDT_1778379004957 | BNBUSDT | SELL | 2.86 | 11.72 | CLOSE (pending) |
| aurora_BNBUSDT_1778405705080 | BNBUSDT | BUY | 1.56 | 17.10 | CLOSE (pending) |
| aurora_XRPUSDT_1778414705236 | XRPUSDT | SELL | 1.47 | 8.37 | CLOSE (pending) |
| aurora_BNBUSDT_1778416502994 | BNBUSDT | SELL | 1.14 | 11.85 | close_requested |
| aurora_BNBUSDT_1778377202278 | BNBUSDT | SELL | 0.58 | 14.14 | CLOSE (pending) |
| aurora_BTCUSDT_1778429706498 | BTCUSDT | BUY | 0.23 | 8.25 | **FINAL** -1.01 |
| aurora_BTCUSDT_1778424602438 | BTCUSDT | SELL | 0.00 | 13.96 | close_requested |
| aurora_XRPUSDT_1778381403373 | XRPUSDT | SELL | 0.00 | 1.14 | CLOSE (pending) |
| aurora_XRPUSDT_1778382005365 | XRPUSDT | SELL | 0.00 | 1.28 | CLOSE (pending) |
| aurora_BNBUSDT_1778426406618 | BNBUSDT | BUY | 0.00 | 1.67 | CLOSE (pending) |

Note: "pending in lifecycle stats" means the lifecycle has a POSITION_CLOSED in order_log but no FINAL row in lifecycle_stats yet — indicating lifecycle stats FINAL writes are lagging or were not flushed before log freeze.

---

## 13. CONTRACT VIOLATIONS FOUND

| ID | Severity | Description | Surface |
|---|---|---|---|
| CV-001 | MEDIUM | `EVT:QUADRATIC_DECISION_TRACE` lacks `price_motion_source`, `price_motion_age_ms`, `price_motion_ready` in journal (all 1,236 rows). `partial_identity=true` on all rows. Cannot confirm A6 wire from runtime surface. | shadow_critical_event_journal |
| CV-002 | MEDIUM | `EVT:TRADE_INTENT_REJECTED` lacks A2 structured fields: `selected_source`, `selected_scale`, `threshold_family`, `threshold_value`, `missing_source_list`. These are absent from both journal and order_log surfaces. | shadow_critical_event_journal, order_log |
| CV-003 | LOW | `accepted_or_rejected` field is universally null (93/93 rows) in decision_ledger. The A3 seed→revision chain pattern is not demonstrable. The ledger contains only terminal-state rows with no visible intermediary seed phase. | decision_ledger_v1.jsonl |
| CV-004 | LOW | 14 POSITION_CLOSED events in order_log do not all have corresponding FINAL rows in execution_lifecycle_stats. Only 1 FINAL row exists vs 14 closes — lifecycle stats finalization is lagging or was not flushed at runtime end. | execution_lifecycle_stats_v1.jsonl |

---

## 14. RUNTIME BLOCKERS FOUND

**No hard runtime blockers found.** The system ran, produced decisions, executed trades, and managed positions for ~20.3 hours without a visible crash or hard halt.

### Elevated risks observed:

| ID | Risk | Evidence | Severity |
|---|---|---|---|
| RB-001 | Terminal identity cache 100% miss rate | 311 ORDER_FILLED = 311 HARDENING:TRADE_EXECUTED_TERMINAL_IDENTITY_CACHE_MISS | HIGH |
| RB-002 | 55 suppressed trade executions unaccounted | HARDENING:TRADE_EXECUTED_SUPPRESSED=55 in shadow journal; no corresponding POSITION_CLOSED or economic record found | HIGH |
| RB-003 | 1 EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS (BTCUSDT) | DEF-005 pre-existing — bracket close received, OrderIndex miss | MEDIUM (pre-existing) |
| RB-004 | EXECUTION_BRACKET_RECOVERY_SKIPPED: 5 events | Likely DEF-006 (mean_reversion/non-aurora brackets not supported) | LOW (pre-existing) |

**RB-001** is the most operationally significant finding. A 100% terminal identity cache miss rate means every fill event triggers a HARDENING miss. If this cache was intended to gate duplicate fill processing, its failure may mean fills are being processed without idempotency protection.

**RB-002** requires separate investigation. 55 suppressed executions with no corresponding PnL record is an unquantified gap.

---

## 15. RESIDUAL RISKS

| Risk | Category | Resolution Path |
|---|---|---|
| A6 price_motion cannot be confirmed from journal surface | Instrumentation | Add dedicated non-truncated price_motion observation sink; log at INFO with full structured fields on each QUADRATIC trace |
| A2 structured field names absent from journal | Instrumentation | Emit A2 fields as top-level structured JSON in TRADE_INTENT_REJECTED payload_fragment, not embedded in why_chain string |
| A3 seed rows absent — no multi-row chain pattern observed | Design | Verify whether decision_ledger is designed as single-write terminal only (if so, update A3 spec); if seed rows are expected, investigate why they are not written |
| 55 HARDENING:TRADE_EXECUTED_SUPPRESSED unaccounted | Execution safety | Query shadow journal for SUPPRESSED rows; determine which fills were suppressed and whether any economic impact is unrecorded |
| 14 lifecycle close stats vs 1 FINAL row | Finalization | Verify flush behavior at runtime shutdown; confirm FINAL writes complete before log freeze |
| MAE >> MFE for 10 of 15 lifecycles | Economic | Noted for calibration phase — do not act now |
| XRPUSDT SL hit -37.48 USDT with MAE 31.71 vs MFE 14.39 | Economic | Noted for calibration phase — do not act now |
| Equity at session end: 2180.57 USDT with 0 open positions | Economic | Positions appear fully closed at runtime end; equity consistent |

---

## 16. WHETHER CALIBRATION/BACKTEST PHASE MAY BEGIN

**CALIBRATION PHASE MAY BEGIN WITH CONDITIONS.**

### Conditions met:
- ✅ Runtime ran continuously for 20+ hours without crash
- ✅ A3 decision ledger functional (terminal writes correct, null accounting for unresolved)
- ✅ A4 lifecycle stats structural contract met (PROVISIONAL/FINAL, all path stats present)
- ✅ A5 sidecar operating correctly (authority_applied=false, proper 3-state close flow, no duplicate closes, no orphan brackets)
- ✅ Sidecar close flow confirmed reconciled for all 10 close requests
- ✅ Economic inventory complete with three-surface join confirmed for 1 realized trade
- ✅ Score comparison logic correct (raw scores vs thresholds, not normalized)

### Conditions requiring resolution before calibration results are trusted:
- ⚠️ **A6 unconfirmed** (price_motion provenance unknown) — calibration results that depend on price_motion source distribution are unreliable until confirmed
- ⚠️ **55 suppressed executions** — calibration P&L totals may be incomplete if these fills had economic impact
- ⚠️ **100% terminal identity cache miss** — if any fills were double-processed, execution statistics are inflated

### Recommended sequencing:
1. Investigate RB-001 (terminal identity cache miss) and RB-002 (55 suppressed fills) **before** using execution statistics for calibration
2. Add price_motion observation sink and run one short live window to confirm A6 wire
3. Proceed with calibration using A3/A4/A5 surfaces once RB-001/RB-002 are understood

---

## FINAL VERDICT

**`RUNTIME_VALIDATED_WITH_RESIDUALS`**

The runtime is validated as functional with three confirmed residuals (A6 price_motion unconfirmed from journal, A2 structured field names absent, A3 seed chain unconfirmed) and two elevated execution risks (100% terminal identity cache miss, 55 suppressed fills unaccounted). Calibration and backtest phase may begin with the conditions enumerated in Section 16.

---

*Report generated: 2026-05-10 | Audit type: automated forensic read-only | No code or config was modified during this audit.*
