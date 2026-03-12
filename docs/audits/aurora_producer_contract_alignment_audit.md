# Aurora Producer Contract Alignment Audit

**Package:** NEO-PRODUCER-CONTRACT-ALIGNMENT-AUDIT-AND-IMPLEMENTATION-PLAN
**Date:** 2026-03-12
**Status:** AUDIT ONLY — No implementation in this package
**Auditor:** Principal vFoundation Architect
**Branch:** Phenix_v2

---

## Executive Summary

This audit re-validates the 4 hard blockers (HB-1 through HB-4) that block
execution-aware integration between the Aurora trading system and the neocortex
shadow domain. Each blocker was verified against the active codebase on branch
`Phenix_v2`.

**Verdict: ALL 4 HARD BLOCKERS CONFIRMED. All are producer-side gaps in Aurora.
No neocortex code changes required to resolve any of them.**

Key findings:
- `lifecycle_id` is architecturally absent — not a missing field, but a missing
  concept. The `rid` field changes identity semantics across pipeline stages.
- `trade_id` reaches ORDER_FILLED but is never cached for propagation to
  POSITION_CLOSED — a 3-line cache gap, 3-line emit gap.
- `fees` reach ORDER_FILLED but are never accumulated; `net_pnl` is never
  computed anywhere. A per-symbol accumulator cache is needed.
- The "structured" log path in `core_parser.py` never fires in production
  because Aurora emits POSITION_CLOSED as plain `LOG.info(...)` text, not as
  structured key=value or JSON inline. `trade_lifecycle.jsonl` is already
  structured but is not wired as neocortex's primary source.

**Implementation readiness:** Producer-side implementation packages PKG-1
through PKG-4 can begin immediately, in dependency order. No neocortex changes
are needed. No broad refactor required. Each package touches ≤5 focused files.

---

## Neocortex Required Producer Contract (Post P1–P9)

Neocortex P1–P9 remediation hardened the consumer side. The contracts it now
enforces — and which the producer must satisfy — are:

### Identity Contract (P2)
Neocortex requires a stable `lifecycle_id` that persists across:
- ORDER_INTENT (intent emission)
- ORDER_FILLED (entry fill)
- POSITION_CLOSED (close detection)

Without `lifecycle_id`, every `execution_quality` sample has `None` as its
`source_ref`, making deduplication, provenance, and gap detection unreliable.

Reference: `order_parser.py:143` — `lifecycle_id=_optional_str(data.get("lifecycle_id"))`
Reference: `datasets/contracts.py:37` — `lifecycle_id: Optional[str]` in `DatasetSampleProvenance`
Reference: `transport/adapter.py:908,970` — `lifecycle_id` expected in episode dict

### Reward Completeness Contract (P3)
Neocortex requires `reward_complete=True` for execution-quality training to
proceed. This requires:
- `trade_id` in the close event (for unambiguous close matching)
- `fees` (structured, not inferred)
- `net_pnl = realized_pnl - fees` (computed at close plane, not inferred)
- `close_price` (already present, but only via fill-price cache)

Reference: `transport/adapter.py:935-940` — `reward_complete` logic
Reference: `transport/adapter.py:940` — `reward_missing = reward is None or not reward_complete`

### Trade_id Contract (P2)
The close event must carry `trade_id` to allow neocortex to match the close
back to the originating fill without relying on symbol + timestamp heuristics.

Reference: `order_parser.py:144-148` — `trade_id` from `data.get("trade_id")` or `metadata.fill_trade_id`

### Structured Source Contract (P3)
Neocortex must be able to read close reward data from a structured source:
- Preferred: `order_log_v1.jsonl` POSITION_CLOSED entries with full fields
- Alternative: `trade_lifecycle.jsonl` as primary (structured JSONL exists)
- Forbidden: regex parsing of plain-text `aurora_core.log` as primary

---

## Hard Blocker Re-Validation

---

### HB-1 — `lifecycle_id` Not Emitted to Producer Surface

**Status: CONFIRMED**
**Severity: CRITICAL — blocks all execution_quality sample identity**

#### Root Cause

The concept of `lifecycle_id` does not exist in Aurora's producer implementation.
Instead, the `rid` field is used — but its semantics change across pipeline stages:

| Stage | `rid` value | Source |
|---|---|---|
| ORDER_INTENT | Decision UUID (strategy generates it) | `intent_builder.py:233` |
| ORDER_FILLED | `payload.get("rid") or event.rid` → fill-level clientOrderId | `event_handlers.py:352` |
| POSITION_CLOSED | `_last_lifecycle_rid_by_symbol[sym]` = fill-level rid | `event_handlers.py:221` |

No single stable identity propagates intent → fill → close.

The `idempotent_key` field in ORDER_INTENT is the closest to a `lifecycle_id`:
it is `str(uuid.uuid4())` created per intent (`intent_builder.py:255`).
However:
- It is buried in `metadata.idempotent_key` in the ORDER_INTENT log
  (`intent_builder.py:363` → `"metadata": {..., "idempotent_key": ...}`)
- It is NOT passed through to ORDER_FILLED log
- It is NOT passed through to POSITION_CLOSED log
- `order_parser.py:143` reads `data.get("lifecycle_id")` — field never present

#### Exact Code Anchors

```
intent_builder.py:255      — idempotent_key = str(uuid.uuid4())
intent_builder.py:357-364  — ORDER_INTENT log, no lifecycle_id field
event_handlers.py:352-353  — fill event: rid = payload.rid or event.rid
event_handlers.py:383-386  — _last_lifecycle_rid_by_symbol caches fill-rid
event_handlers.py:219-225  — POSITION_CLOSED reads cached fill-rid
event_handlers.py:246-261  — POSITION_CLOSED log, no lifecycle_id field
order_parser.py:143        — lifecycle_id=data.get("lifecycle_id") → always None
fsm.py:297                 — _last_lifecycle_rid_by_symbol: Dict[str, str]= {}
```

#### Blast Radius

- **All execution_quality samples** have `lifecycle_id=None` in `DatasetSampleProvenance`
- Episode-to-lifecycle matching in neocortex falls back to symbol+timestamp heuristics
- Deduplication across restarts is unreliable
- Disagreement corpus provenance is unboundedly incomplete

#### Alternative Solutions

**Option A (Recommended): Propagate `idempotent_key` as `lifecycle_id` at all three stages**
- At ORDER_INTENT: add top-level `"lifecycle_id": trade_intent["idempotent_key"]` to the log entry
- At ORDER_FILLED: cache intent `idempotent_key` per symbol (needs cache in FSM); add `"lifecycle_id"` to ORDER_FILLED log
- At POSITION_CLOSED: use `_last_lifecycle_ikey_by_symbol[sym]` for `lifecycle_id`; add to log

Trade-offs: Requires new per-symbol cache `_last_lifecycle_ikey_by_symbol`. Intent router must pass `idempotent_key` through CMD:OPEN payload (already present: `intent_router.py:75`). Minor blast radius.

**Option B: Use ORDER_INTENT `rid` (decision UUID) as `lifecycle_id`**
- Cache intent `rid` per symbol at fill time
- At POSITION_CLOSED: use cached intent_rid as `lifecycle_id`
- Add `lifecycle_id` to all three log entries using intent rid

Trade-offs: Simpler — `rid` is already available. But `rid` is also used as envelope
message identity, so semantic overloading. Low risk in practice since neocortex
only needs a stable per-trade key.

**Option C (Rejected): Introduce new lifecycle_id generator separate from rid/idempotent_key**
- Creates unnecessary third identity
- Does not reuse existing intent-level UUID
- Higher complexity for same outcome

**Recommendation:** Option A — use `idempotent_key` as `lifecycle_id`. It is
already a UUID4 created per intent, exactly the right semantic. The rename
clarifies intent without introducing new state.

#### Minimal Safe Fix

1. Add `"lifecycle_id": trade_intent["idempotent_key"]` to ORDER_INTENT log entry (`intent_builder.py:357`)
2. In `ExecPosFSM.__init__`, add `self._last_lifecycle_ikey_by_symbol: Dict[str, str] = {}`
3. In `on_order_fill`, store `idempotent_key` from order_index lookup (it's stored there already)
4. In `on_portfolio_state_updated` POSITION_CLOSED path, add `"lifecycle_id": cached_ikey` to log

---

### HB-2 — `trade_id` Missing from POSITION_CLOSED

**Status: CONFIRMED**
**Severity: HIGH — prevents canonical close-to-fill matching in neocortex**

#### Root Cause

The `tradeId` from Binance fill events IS received and logged in ORDER_FILLED:
```python
# event_handlers.py:426-430
"metadata": {
    "fill_trade_id": str(payload.get("tradeId", "")),
    ...
}
```

But it is NEVER cached per-symbol for propagation to POSITION_CLOSED.

The `ExecPosFSM` has per-symbol caches for:
- `_last_lifecycle_rid_by_symbol` (fill rid)
- `_last_lifecycle_fill_price_by_symbol` (fill price)
- `_last_realized_pnl_by_symbol` (fill PnL)
- `_last_close_reason_by_symbol` (close reason)

But NO `_last_trade_id_by_symbol` cache exists.

POSITION_CLOSED log (`event_handlers.py:246-261`) emits:
```python
{"rid": ..., "event_type": "POSITION_CLOSED", "symbol": sym, "side": "N/A",
 "metadata": {"close_price": ..., "realized_pnl": ...}}
```
No `trade_id` field.

#### Exact Code Anchors

```
event_handlers.py:349      — fill event handler start
event_handlers.py:426-430  — fill logs tradeId as metadata.fill_trade_id
event_handlers.py:246-261  — POSITION_CLOSED — no trade_id
fsm.py:294-302             — per-symbol caches — no _last_trade_id_by_symbol
order_parser.py:144-148    — parser reads trade_id from data or fill_trade_id
```

#### Additional Issue: `side` is "N/A"

POSITION_CLOSED logs `"side": "N/A"` because the position side is not tracked
at portfolio-diff time. The side was available when the entry order was placed
(ORDER_PLACED has `"side": side`) but is not cached for close emission.

This is a quality regression: neocortex requires `side` for execution quality
directional analysis.

#### Risk of Wrong Close Matching

Without `trade_id`:
- Neocortex matches close events by `(symbol, approx_timestamp)` heuristic
- Multiple fills for the same symbol in a short window → incorrect episode attribution
- Leg-in/leg-out sequences on same symbol → close mapped to wrong open

#### Alternative Solutions

**Option A (Recommended): Cache tradeId per-symbol at fill, emit at POSITION_CLOSED**
- Add `self._last_trade_id_by_symbol: Dict[str, str] = {}` to `ExecPosFSM`
- In `on_order_fill`: `self._fsm._last_trade_id_by_symbol[symbol] = str(payload.get("tradeId", ""))`
- In POSITION_CLOSED: emit `"trade_id": cached_trade_id`

**Option B: Reconstruct from fill ledger at close detection time**
- Query `order_log_v1.jsonl` backward for most recent ORDER_FILLED for symbol
- Extract `metadata.fill_trade_id`
- Fragile: requires synchronous log reads; race conditions under partial fill sequences

**Option C (Rejected): Use orderId as trade_id proxy**
- OrderId is not tradeId — different Binance semantics
- Breaks neocortex's intent to use exchange-canonical tradeId

**Recommendation:** Option A. Also add `side` caching for the same reason:
`_last_entry_side_by_symbol: Dict[str, str]`.

#### Minimal Safe Fix

1. Add `_last_trade_id_by_symbol: Dict[str, str] = {}` to `ExecPosFSM.__init__`
2. Add `_last_entry_side_by_symbol: Dict[str, str] = {}` to `ExecPosFSM.__init__`
3. In `on_order_fill`: cache `tradeId` and `side`
4. In POSITION_CLOSED log: add `"trade_id"` and correct `"side"` from cache

---

### HB-3 — No Structured `fees` / `net_pnl` in Close Path

**Status: CONFIRMED**
**Severity: HIGH — reward_complete=False on all execution_quality samples**

#### Root Cause

`commission` from fill events IS received and logged in ORDER_FILLED:
```python
# event_handlers.py:428-430
"commission": float(payload.get("commission", 0.0)),
"commissionAsset": str(payload.get("commissionAsset", "")),
```

But it is NEVER accumulated per-symbol. POSITION_CLOSED only emits:
```python
"metadata": {"close_price": ..., "realized_pnl": pos_pnl}
```

`net_pnl = realized_pnl - fees` is never computed anywhere in the close path.

The `TradeLifecycleLogger` has a `fill_fees` field on `TradeRecord` and accepts
`fees` in `on_fill()`, but:
1. The `on_close()` call (`event_handlers.py:231-235`) does NOT pass `fees` or `pnl_usdt`
2. Neocortex reads from `order_log_v1.jsonl`, not from `trade_lifecycle.jsonl`

#### Exact Code Anchors

```
event_handlers.py:392-399     — trade_lifecycle.on_fill(fees=commission) — correct
event_handlers.py:231-235     — trade_lifecycle.on_close() — no fees or net_pnl passed
event_handlers.py:254-261     — POSITION_CLOSED log — only realized_pnl, no fees or net_pnl
trade_lifecycle_logger.py:78  — TradeRecord.fill_fees field exists
trade_lifecycle_logger.py:283-300 — on_close() has pnl_pct, pnl_usdt — no fees parameter
fsm.py:300-302                 — _last_realized_pnl_by_symbol, _last_close_reason_by_symbol
                                  — no _accumulated_fees_by_symbol
```

#### Concurrency / Multi-Fill Risk

Close orders (SL/TP/CLOSE) may generate multiple fills for fractional position
sizes. Under partial fills:
- `commission` arrives per fill
- Accumulation must sum `commission` across all fills for the same symbol before close

Currently `_last_realized_pnl_by_symbol` only stores the LAST fill's `realizedPnl`,
not an accumulation. This is also a root cause for HB-3 and related accuracy risk.

#### What Is Actually Available at Close Detection Time

At portfolio-diff time (`on_portfolio_state_updated`):
- `positionAmt → 0` detected (close trigger)
- `positions[sym].realizedPnl` from portfolio payload (available but sometimes 0.0)
- Fallback: `_last_realized_pnl_by_symbol[sym]` from last fill

What is NOT available unless cached:
- `commission` (fill-level, needs per-symbol accumulator)
- `trade_id` (fill-level, needs per-symbol cache)
- `side` (entry-level, needs per-symbol cache)

#### Alternative Solutions

**Option A (Recommended): Accumulate fees per-symbol; compute net_pnl at close**
- Add `_accumulated_fees_by_symbol: Dict[str, float] = {}` to `ExecPosFSM`
- In `on_order_fill`: if close fill (SL/TP/CLOSE), add to accumulator
- In POSITION_CLOSED: emit `fees`, compute `net_pnl = realized_pnl - fees`
- Reset accumulator after close emission

**Option B: Emit authoritative reward payload from trade_lifecycle.jsonl side**
- `TradeLifecycleLogger` already accumulates fills with fees
- Wire neocortex to read from `trade_lifecycle.jsonl` as primary source
- Add `fees` and `net_pnl` computation to `on_close()` in `TradeLifecycleLogger`
- This does not require ORDER_FILLED changes

Trade-offs: Requires changing neocortex ingest config to point to a new source.
But it avoids touching `ExecPosFSM` event_handlers. Cleaner long-term.

**Option C (Rejected): Post-close reconciliation event**
- Adds async reconciler that joins fill log + portfolio snapshot
- Introduces timing race: reconciliation may fire before neocortex processes close
- Complexity not justified when in-process accumulation is simpler

**Recommendation:** Option A for ORDER_INTENT log plane (additive only to
`event_handlers.py`). Option B as parallel track for `trade_lifecycle.jsonl`
(resolves HB-4 simultaneously).

#### Minimal Safe Fix

1. Add `_accumulated_fees_by_symbol: Dict[str, float] = {}` to `ExecPosFSM.__init__`
2. In `on_order_fill` for close fills: accumulate `commission`
3. In POSITION_CLOSED path: compute `net_pnl`, add `fees` and `net_pnl` to metadata

---

### HB-4 — Unstructured Core-Log / Regex Reward Dependency

**Status: CONFIRMED**
**Severity: MEDIUM-HIGH — reward extraction always falls through to regex path (zero fields)**

#### Root Cause

`core_parser.py` has two paths:

**Path 1 (structured):** `lines 157–215`
Fires when "POSITION_CLOSED" or "TRADE_CLOSED" appears in a log line AND at
least one of `realized_pnl`, `realized_pnl_net`, `trade_id`, `close_price`,
`fees` is present as a parseable field.

**Path 2 (regex fallback):** `lines 218–231`
Fires for `[SYMBOL] Position closed (reason)` pattern.
Extracts ONLY: `symbol`, `reason`, `event_ts_ms`. NO reward data.

**What Aurora actually emits:**
```python
# event_handlers.py:211-214
LOG.info(
    f"[POSITION_CLOSED] {sym}: position closed (was {prev_amt}, now {now_amt})"
    f" | open_regime={_pos_close_regime.get('regime')} | realized_pnl={pos_pnl}"
)
```

This is a Python-formatted string. `_extract_field(line, "realized_pnl")` would
theoretically match `realized_pnl={pos_pnl}`, but the line contains
`[POSITION_CLOSED]` not `POSITION_CLOSED` at the start, and the check is
`if "POSITION_CLOSED" in line` — so this WOULD trigger Path 1.

However, the regex `_extract_field` looks for either:
- `"realized_pnl":\s*"?VALUE"?` (JSON-like)
- `realized_pnl\s*=\s*VALUE`

The log line `realized_pnl={pos_pnl}` — `pos_pnl` could be `0.0` or a float.
This might actually extract a value if it matches `realized_pnl\s*=\s*[^,\s}]+`.

**Critical finding:** Even if `realized_pnl` is extracted from the log line,
the following fields will NEVER appear because Aurora does not log them:
- `realized_pnl_net` — never logged
- `trade_id` — never in the log line
- `fees` — never in the log line
- `close_ts_ms` — not in the log line

So Path 1 extracts at most `symbol` + `realized_pnl`. Path 2 extracts `symbol`
+ `reason`. Neither path provides a `reward_complete=True` result.

The `trade_lifecycle.jsonl` file (at `logs/trade_lifecycle.jsonl`) IS structured
and would contain all needed fields — but neocortex's ingest config reads from
`aurora_core.log` (via `multi_tailer.py`), not from `trade_lifecycle.jsonl`.

#### Exact Code Anchors

```
core_parser.py:54-58        — POSITION_CLOSED_PATTERN regex (text-only fallback)
core_parser.py:157-215      — structured path (fires on POSITION_CLOSED in line)
core_parser.py:177-215      — structured path requires symbol + ≥1 reward field
event_handlers.py:211-214   — Aurora POSITION_CLOSED plain LOG.info text
trade_lifecycle_logger.py:53-97 — TradeRecord: full structured fields exist
trade_lifecycle_logger.py:188-205 — _flush() writes to JSONL
neocortex/logic/ingest/multi_tailer.py — log file tailer (reads core.log)
```

#### Current Risk

- `reward_complete=False` on 100% of execution_quality samples
- All reward truth is derived from LOG.info regex, missing `fees`, `net_pnl`, `trade_id`
- When `realized_pnl=0.0`, neocortex receives `reward=0.0` even if trade was profitable
- PPO training permanently gated (disabled by design), but evaluator quality is also degraded

#### Alternative Solutions

**Option A (Recommended): Emit POSITION_CLOSED as structured entry to `order_log_v1.jsonl`**
- Modify POSITION_CLOSED write in `event_handlers.py:246-261` to include:
  `trade_id`, `fees`, `net_pnl`, `lifecycle_id`, `side`, `close_ts_ms`
- Neocortex's `order_parser.py` reads this already — no neocortex changes
- This fixes HB-1, HB-2, HB-3, and HB-4 simultaneously at the same write site

**Option B: Wire trade_lifecycle.jsonl as neocortex structured primary source**
- Point neocortex multi_tailer to `logs/trade_lifecycle.jsonl`
- Add a lifecycle_parser.py that reads TradeRecord JSONL
- Requires neocortex ingest config change + new parser

Trade-offs: `trade_lifecycle.jsonl` has a different schema than `order_log_v1.jsonl`,
so it would need a new parser. However, it has richer data (entry price, brackets,
SL/TP). This approach decouples neocortex from Aurora's order log format.

**Option C (Rejected): Improve regex parsing of aurora_core.log**
- Makes the text dependency more elaborate, not less
- Aurora log format is not contractually frozen — fragile long-term
- Rejected by principle: no regex as SSOT for reward truth

**Recommendation:** Option A. It is strictly additive — the POSITION_CLOSED
`order_logger.write()` call already exists at `event_handlers.py:245-261`.
Adding 5–6 fields to that dict write resolves 3 blockers at once (HB-2, HB-3, HB-4)
while Option A for HB-1 adds `lifecycle_id`.

---

## Soft Blockers / Quality Risks

### SR-1: `rid` Semantics Differ Between ORDER_INTENT and ORDER_FILLED

**Status: CONFIRMED AND ACTIVE**

ORDER_INTENT uses the decision-making UUID (`decision.rid`).
ORDER_FILLED uses `payload.get("rid") or event.rid` from the fill event,
which equals `clientOrderId` (ENTRY-{symbol}-{hash}).

`order_parser.py` maps the ORDER_INTENT `rid` to `legacy_rid` (line 156), not
as canonical lifecycle identity. This is a known acknowledged workaround.

**Blocks:** Feature-to-execution linkage in disagreement analysis.
**Priority:** Address in PKG-1 via `lifecycle_id` propagation.

### SR-2: No Authoritative `POSITION_OPENED` Event

**Status: CONFIRMED**

There is no `POSITION_OPENED` event emitted to `order_log_v1.jsonl`. The
entry fill (ORDER_FILLED) is the closest proxy, but it is not semantically
an "authoritative open" — it's an exchange confirmation.

Neocortex's episode identity contract (P2) anchors episodes on ORDER_FILLED
(`entry_anchor_event`), not on a dedicated POSITION_OPENED event.

**Blocks:** None currently (neocortex adapted). Would be needed for full
comparison corpus when dual-fill sequences occur.
**Priority:** Defer — not blocking any current integration stage.

### SR-3: Feature Timestamp Exposure

**Status: PARTIALLY RESOLVED**

Feature engineering must embed `event_ts_ms` in every log line for neocortex's
P1 canonical time contract. This is tracked in TODO.md as SP-1.

**Blocks:** `fail_closed` timestamp policy in limited shadow runtime.
**Priority:** Required before shadow runtime phase, but not before PKG-1–4.

### SR-4: Decision Trace Not Persisted for Full Comparison Corpus

**Status: CONFIRMED**

`EVT:DECISION_TRACE_EMITTED` is emitted by `intent_builder.py:286-289` but
it goes to the FSM bus and is not reliably persisted to a queryable artifact.

`schemas/decision_trace_emitted_v1.json` schema exists but per-decision JSONL
is not written.

**Blocks:** Shadow comparison corpus for disagreement analysis.
**Priority:** Required for acceptance campaign, not for PKG-1–4.

### SR-5: `legacy_rid` Bridge Still Active

**Status: CONFIRMED**

`order_parser.py:156` maps `rid` field to `legacy_rid`. The comment in TODO.md
reads: "P2 follow-up: retire the temporary `legacy_rid` fill-resolution bridge
after canonical fill IDs are emitted upstream."

**Blocks:** Nothing immediately. Cleanup item post-PKG-1.
**Priority:** Retire after PKG-1 (`lifecycle_id`) is live and verified.

### SR-6: `trade_lifecycle.jsonl` Underused

**Status: CONFIRMED**

`logs/trade_lifecycle.jsonl` (source: `TradeLifecycleLogger`) is the richest
structured per-trade record in the system. It contains intent → order → fill →
brackets → close as a single record. Neocortex does NOT read it.

**Blocks:** Nothing directly (order_log_v1.jsonl is the primary neocortex source).
**Priority:** High-value for PKG-3/PKG-4 — can serve as alternative reward SSOT.

### SR-7: Analytics Amnesia on Restart

**Status: CONFIRMED (tracked separately in TODO.md — Aurora runtime audit)**

`runtime_analytics_restore.py` and `startup_hydration_planner.py` exist but
`build_startup_hydration_plan()` returns a report artifact without executing
hydration actions (READINESS_CONTRACTS_AUDIT.md: "FALSE-READY" finding).

**Blocks:** Deterministic neocortex ingest after restart (P7 performance contract
replay integrity).
**Priority:** Required for shadow runtime, tracked in Aurora runtime remediation.

### SR-8: Open P1–P9 Follow-ups That Block Integration

From TODO.md:
- P2 follow-up: retire `legacy_rid` bridge → blocked by HB-1 fix
- P3 follow-up: producer-side `lifecycle_id`/`fees`/`trade_id` → **THIS AUDIT**
- P3 follow-up: retire transitional parser shim → blocked by HB-4 fix
- P9 follow-up: shadow comparison corpus from persisted artifacts → blocked by SR-4

---

## Risk Analysis and Sequencing Constraints

### Cross-Blocker Dependencies

```
PKG-1 (lifecycle_id) ──→ enables PKG-2 (trade_id) to use same cache pattern
PKG-1 + PKG-2 + PKG-3 ──→ together enable reward_complete=True in PKG-4
PKG-4 (structured close surface) ──→ retires regex path (core_parser.py) gracefully
PKG-3 simultaneously ──→ populates trade_lifecycle.jsonl more completely
```

### Fail-Closed Constraints

1. `ExecPosFSM` per-symbol caches are `try/except`-wrapped throughout. Adding
   new caches follows the same pattern — no blast radius on existing paths.
2. All new fields to `order_logger.write()` are optional dict additions — the
   `OrderLoggerV1.write()` method is dict-based, schema validation only runs in
   TEST/DEBUG. Adding new keys does not break existing readers.
3. `trade_lifecycle_logger.on_close()` signature change (adding `fees`, `net_pnl`)
   would require all callers to be updated — only one call site in
   `event_handlers.py:231-235`. Low blast radius.

### Backward Compatibility

- Existing order log consumers: the WAL content grows but existing fields are
  unchanged. Additive-only.
- Existing neocortex parsers: `order_parser.py` already reads `lifecycle_id`
  from data (returns None today because it's absent). Adding it fills the gap.
- `core_parser.py` regex path: not removed by PKG-4. It becomes unreachable
  for close events once structured POSITION_CLOSED entries are complete.
  Explicitly deprecated in PKG-4, removed in a future cleanup package.

---

## Alternatives Summary

| Blocker | Preferred | Backup | Rejected |
|---|---|---|---|
| HB-1 | Use `idempotent_key` as `lifecycle_id` | Use intent `rid` as `lifecycle_id` | New separate lifecycle_id generator |
| HB-2 | Cache `tradeId` per-symbol at fill | Reconstruct from fill ledger | Use orderId as proxy |
| HB-3 | Accumulate fees per-symbol; compute net_pnl at close | Wire trade_lifecycle.jsonl directly | Post-close reconciliation event |
| HB-4 | Emit structured POSITION_CLOSED to order_log_v1.jsonl | Wire trade_lifecycle.jsonl as primary source | Improve regex parsing |
