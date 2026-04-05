# FORENSIC AUDIT: Order Closures, Realized PnL Clusters, and "Jitter" Behavior

**Date**: 2026-04-05
**Audit Window**: 2026-04-03 17:00 UTC through 2026-04-04 21:00 UTC
**Runtime Session**: 2026-04-04 ~00:16 UTC to ~21:00 UTC (WAL coverage)
**Structured Logging Session**: 2026-04-04 ~08:01 UTC to ~21:27 UTC (shadow/lifecycle/order_log)

---

## 1. Executive Verdict

The "jitter" pattern of multiple realized PnL rows at the same second is caused by **expected exchange trade fragmentation** compounded by a **known-but-not-yet-deployed bracket child OrderIndex registration bug**. The exchange fills one SL/TP market order across multiple counterparty trades (each producing a separate realized PnL row in the Binance UI). The system's bracket-child fills were **not lost economically** — the exchange executed them correctly and the positions were closed at the intended SL/TP prices. However, the system's internal close-truth pipeline **failed to process these fills** because bracket child orders were never registered in `OrderIndex`, causing every bracket close fill to be dropped as `EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS` and subsequently misattributed as `unknown_disappearance`. The code fix for this (Blocker 4 from the deep audit) exists in the current branch but was **not deployed to the runtime that produced these logs**. The economic outcome is correct; the observability and internal state management are broken.

---

## 2. Screenshot Pattern Summary

| Screenshot Timestamp | Symbol(s) | Rows | Reconciliation Status |
|---|---|---|---|
| 2026-04-04 14:01:32 | BTCUSDT | 3 | **FULLY RECONCILED** — 3 partial fills (2x PARTIALLY_FILLED + 1x FILLED) for SL bracket order `13021119614` |
| 2026-04-04 10:59:44 | BTCUSDT, DOGEUSDT, ETHUSDT | multi | **UNPROVEN** — no runtime artifacts exist at this timestamp; may be from a prior session or timezone offset |
| 2026-04-04 03:28:02 | BTCUSDT | multi | **UNPROVEN** — WAL shows only ACCOUNT_UPDATE heartbeats; structured logs don't cover this window |
| 2026-04-03 17:23:04 | ETHUSDT | multi | **UNPROVEN** — 42-minute WAL gap (17:16–17:58 UTC); zero events recorded |

**Timezone Note**: The fully-reconciled cluster (14:01:32) maps precisely to 11:01:31–32 UTC when interpreted as UTC+3 (Kyiv local time). The domain_execution_position.log confirms UTC+3 timestamps. The Binance exchange UI likely displays in the user's browser timezone (UTC+3).

---

## 3. FACTS (Evidence-Backed Only)

### F1. Four positions were opened on 2026-04-04, all SHORT:

| Symbol | RID | Entry Order | Entry Price | Qty | Entry Time (UTC) |
|---|---|---|---|---|---|
| ETHUSDT | `aurora_ETHUSDT_1775291703165` | `8631350636` | 2052.82 | 4.874 | 08:35:04 |
| BTCUSDT | `aurora_BTCUSDT_1775295903852` | `13021057010` | 66949.60 | 0.096 | 10:02:43 |
| SOLUSDT | `aurora_SOLUSDT_1775297700554` | `1835689621` | 80.03 | 91.0 | 10:16:08 |
| DOGEUSDT | `rid-b295a2c6eec569b8` | `765794352` | 0.09139 | 88410 | 15:10:04 |

### F2. All four positions had SL/TP brackets placed on the exchange:

| Symbol | SL algoId | SL clientAlgoId | SL Trigger | TP algoId | TP clientAlgoId | TP Trigger |
|---|---|---|---|---|---|---|
| ETHUSDT | `1000000041768639` | `EeduzEeoPMZf571SSChNaO` | 2063.05 | `1000000041768643` | `CTvkgP2EmIAeObSIIetreV` | 2047.84 |
| BTCUSDT | `1000000041808641` | `sMfFVMJzRjxHzj8dp6WUip` | 67199.00 | `1000000041808652` | `YUUCj9kSzoTMN2XRse0ccb` | 66529.60 |
| SOLUSDT | `1000000041814502` | `8ORxbVohNkkTxKxSUJcDKt` | 80.10 | `1000000041814509` | `9wHbekyZ5vmpJsEm873uYi` | 79.89 |
| DOGEUSDT | `1000000041936137` | `LNFcAsgt7pr0JufdudXlmT` | 0.09148 | `1000000041936139` | `Ug9jAPXvo0O9KOFVwUOlgm` | 0.09070 |

**Source**: `domain_execution_position.log` bracket placement lines + `order_guardian.log` registration entries.

### F3. All four positions were closed by exchange-side bracket fills, all ORDERINDEX_MISS:

| Symbol | Triggered Bracket | clientOrderId (= clientAlgoId) | Exchange OID | Fill Status | Fill Time (UTC) |
|---|---|---|---|---|---|
| ETHUSDT | **TP** | `CTvkgP2EmIAeObSIIetreV` | `8631380178` | FILLED (1 fill) | 10:12:03 |
| BTCUSDT | **SL** | `sMfFVMJzRjxHzj8dp6WUip` | `13021119614` | **3 fills** (2x PARTIAL + 1x FILLED) | 11:01:31 |
| SOLUSDT | **SL** | `8ORxbVohNkkTxKxSUJcDKt` | `1835694621` | FILLED (1 fill) | 10:28:01 |
| DOGEUSDT | **SL** | `LNFcAsgt7pr0JufdudXlmT` | `765795835` | FILLED (1 fill) | 15:12:30 |

**Critical proof**: The `clientOrderId` in each WS fill event EXACTLY matches the `clientAlgoId` from the bracket placement response. This proves these fills are the system's own bracket orders, not external/manual closes.

### F4. BTCUSDT SL bracket filled in 3 separate exchange trades:

| Event# | ts_ms | event_ts_ms | Status | Delta from #1 |
|---|---|---|---|---|
| 1 | 1775300491810 | 1775300492079 | PARTIALLY_FILLED | 0ms |
| 2 | 1775300491814 | 1775300492079 | PARTIALLY_FILLED | 4ms |
| 3 | 1775300491816 | 1775300492079 | FILLED | 6ms |

All three had identical `event_ts_ms` (same exchange batch), same order `13021119614`, same clientOrderId `sMfFVMJzRjxHzj8dp6WUip`. This is a single SL market order filled against 3 counterparty orders on the Binance matching engine within 6ms.

### F5. All four fills produced `unknown_disappearance` attribution:

| Symbol | Disappearance ts_ms | Delta from fill | Attribution |
|---|---|---|---|
| ETHUSDT | 1775297526013 | 2,247ms | `unknown_disappearance` |
| SOLUSDT | 1775298483425 | 1,631ms | `unknown_disappearance` |
| BTCUSDT | 1775300495230 | 3,414ms | `unknown_disappearance` |
| DOGEUSDT | 1775315596587 | 5,852ms | `unknown_disappearance` |

### F6. Bracket orders were registered in OrderGuardian but NOT in OrderIndex:

- `order_guardian.log` confirms all 8 bracket orders (4 SL + 4 TP) were registered via `register_bracket()`.
- The bracket child exchange order IDs (`13021119614`, `8631380178`, `1835694621`, `765795835`) appear in ZERO lines of: WAL, order_log, shadow journal.
- The `clientAlgoId` strings appear ONLY in the placement response logs, never in OrderIndex registration.

### F7. No CMD:CLOSE, DEC:CLOSE, or system-initiated close commands were issued for any symbol during the audit window.

### F8. The BRACKET-HEALTH recovery loop ran every ~47s and consistently received Binance error `-4130` ("An open stop or take profit order with GTE and closePosition in the direction is existing"), confirming the brackets remained active on the exchange until triggered.

### F9. No `realized_pnl`, `realized_delta`, `POSITION_CLOSED`, or `TRADE_LIFECYCLE_CLOSED` events exist in any of the 4 log sinks (trade_lifecycle, order_log, shadow, WAL) for any symbol.

### F10. The trade_lifecycle.jsonl file is 99.96% `position_policy_sidecar` records (65,448 of 65,474 lines). Only 26 lines contain execution/lifecycle events.

---

## 4. Reconstructed Close Chains

### ETHUSDT — Closed by Take Profit

```
08:35:03 UTC  TRADE_INTENT_PROPOSED (SELL 4.874 @ 2051.35, regime=LOW_VOLATILITY conf=0.81)
08:35:04 UTC  ORDER_PLACED (oid=8631350636, coid=ENTRY-cfbd97c3cedb)
08:35:04 UTC  TRADE_EXECUTED partial (0.01 @ 2052.82, trade_id=255261077)
08:35:05 UTC  TRADE_EXECUTED remainder (4.864 @ 2052.82, trade_id=255261078)
08:35:06 UTC  BRACKET_DEFERRED_PLACED (SL=1000000041768639 @ 2063.05, TP=1000000041768643 @ 2047.84)
  ... 97 minutes of BRACKET-HEALTH checks (all -4130, brackets exist on exchange) ...
10:12:03 UTC  Exchange TP triggers → child market order 8631380178 (clientOrderId=CTvkgP2EmIAeObSIIetreV)
              WS: ORDER_TRADE_UPDATE FILLED → binance_ws_client → OrderIndex lookup MISS
              → EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS logged to trade_lifecycle
              → EVT:TRADE_EXECUTED NOT emitted → ManageFlowFSM stays BRACKETS_PENDING
10:12:06 UTC  PositionTracking detects ETH absent from portfolio snapshot
              → POSITION_DISAPPEARANCE_ATTRIBUTED: unknown_disappearance (qty=-4.874)
              → Internal state: manage_state=BRACKETS_PENDING, portfolio=FLAT (diverged)
```

**Close trigger**: TP bracket at 2047.84 (price fell below TP for SHORT position).
**Economic outcome**: Position closed correctly at exchange. Position closed at TP as intended.
**System outcome**: Close fill dropped. Internal state stale. False "unknown" attribution.

### BTCUSDT — Closed by Stop Loss (3 Partial Fills = 3 Realized PnL Rows)

```
09:45:05 UTC  ORDER_PLACED (oid=13021057010, coid=ENTRY-1ef69c3cd01a)
10:02:43 UTC  TRADE_EXECUTED (fill 0.096 @ 66949.6, trade_id=471930369)
10:02:45 UTC  BRACKET_DEFERRED_PLACED (SL=1000000041808641 @ 67199.00, TP=1000000041808652 @ 66529.60)
  ... 59 minutes of BRACKET-HEALTH checks (-4130) ...
11:01:31 UTC  Exchange SL triggers → child market order 13021119614 (clientOrderId=sMfFVMJzRjxHzj8dp6WUip)
              WS: ORDER_TRADE_UPDATE PARTIALLY_FILLED (trade #1) → OrderIndex MISS → ORDERINDEX_MISS
              WS: ORDER_TRADE_UPDATE PARTIALLY_FILLED (trade #2, +4ms) → OrderIndex MISS → ORDERINDEX_MISS
              WS: ORDER_TRADE_UPDATE FILLED (trade #3, +6ms) → OrderIndex MISS → ORDERINDEX_MISS
              → THREE EVT:TRADE_EXECUTED NOT emitted
11:01:35 UTC  POSITION_DISAPPEARANCE_ATTRIBUTED: unknown_disappearance (qty=-0.096)
```

**Close trigger**: SL bracket at 67199.00 (price rose above SL for SHORT position).
**3 realized PnL rows explained**: Binance matched the SL market order against 3 counterparty limit orders within 6ms. Each match produces a separate `ORDER_TRADE_UPDATE` and a separate realized PnL row in the exchange UI. This is standard exchange matching engine behavior for market orders.
**Screenshot match**: 11:01:31 UTC = 14:01:31 UTC+3 → matches screenshot "14:01:32" precisely.

### SOLUSDT — Closed by Stop Loss

```
10:15:01 UTC  ORDER_PLACED (oid=1835689621, coid=ENTRY-98c2144a44c9)
10:16:08 UTC  TRADE_EXECUTED (fill 91.0 @ 80.03)
10:16:09 UTC  BRACKET_DEFERRED_PLACED (SL=1000000041814502 @ 80.10, TP=1000000041814509 @ 79.89)
  ... ~12 minutes ...
10:28:01 UTC  Exchange SL triggers → child market order 1835694621 (clientOrderId=8ORxbVohNkkTxKxSUJcDKt)
              WS: ORDER_TRADE_UPDATE FILLED → OrderIndex MISS → ORDERINDEX_MISS
10:28:03 UTC  POSITION_DISAPPEARANCE_ATTRIBUTED: unknown_disappearance (qty=-91)
```

**Close trigger**: SL bracket at 80.10 (price rose above SL for SHORT position).

### DOGEUSDT — Closed by Stop Loss

```
15:10:03 UTC  ORDER_PLACED (oid=765794352, coid=ENTRY-e3afb9af8606)
15:10:04 UTC  TRADE_EXECUTED (fill 88410 @ 0.09139)
15:10:04 UTC  BRACKET_PRIMARY_PLACED (SL=1000000041936137 @ 0.09148, TP=1000000041936139 @ 0.09070)
  ... ~2.5 minutes ...
15:12:30 UTC  Exchange SL triggers → child market order 765795835 (clientOrderId=LNFcAsgt7pr0JufdudXlmT)
              WS: ORDER_TRADE_UPDATE FILLED → OrderIndex MISS → ORDERINDEX_MISS
15:12:36 UTC  POSITION_DISAPPEARANCE_ATTRIBUTED: unknown_disappearance (qty=-88410)
```

**Close trigger**: SL bracket at 0.09148 (price rose above SL for SHORT position).

---

## 5. Duplicate / Jitter Analysis

### BTCUSDT 14:01:32 (3 rows) — EXPECTED EXCHANGE FRAGMENTATION

| Fill # | Status | Exchange Mechanism |
|---|---|---|
| 1 | PARTIALLY_FILLED | Market order matched against resting limit order #1 |
| 2 | PARTIALLY_FILLED | Market order matched against resting limit order #2 |
| 3 | FILLED | Market order matched against resting limit order #3 (final fill) |

**Classification**: `EXPECTED_EXCHANGE_FRAGMENTATION`

The SL at 67199.00 triggered a closePosition market order. The exchange matching engine filled it against 3 separate counterparty offers. Each fill is a distinct exchange trade with its own `trade_id`, `last_fill_qty`, and `realized_pnl` contribution. The Binance UI shows each trade as a separate realized PnL row. The fills arrive as 3 separate `ORDER_TRADE_UPDATE` WS messages within 6ms.

**This is not a bug. This is how limit order book matching works.** A market order consuming N price levels or N resting orders produces N separate fills.

### ETHUSDT, SOLUSDT, DOGEUSDT (1 row each) — SINGLE FILLS

Each had a single FILLED event (no partial fills). The exchange matched each SL/TP market order against a single counterparty. One fill = one realized PnL row. No jitter.

### No Repeated Close Commands

Zero `CMD:CLOSE` or `DEC:CLOSE` events exist for any symbol in the entire audit window. The only close mechanism that fired was the exchange-side bracket execution. There is no evidence of the system issuing duplicate close orders.

### No Duplicate Terminal Processing

Each bracket fill WS event was processed exactly once by the WS client. The ORDERINDEX_MISS was logged once per WS event (6 total: 3 for BTCUSDT partials, 1 each for ETH/SOL/DOGE). No duplication in processing — the problem is that processing was DROP (miss-and-skip), not DUPLICATE.

---

## 6. Bracket / Terminal Truth Findings

### Root Cause: Bracket Child OrderIndex Registration Gap

The bracket placement flow registers brackets in:
- `OrderGuardian` — YES (confirmed in guardian log, all 8 brackets registered)
- `CorrelationStore` — YES (via bracket_manager)
- `OrderIndex` — **NO** (the fix for Blocker 4 exists in code but was NOT deployed to this runtime)

When Binance fires an SL/TP algo, it creates a **child market order** with:
- A NEW `exchange_order_id` (not the algo's `algoId`)
- The algo's `clientAlgoId` as the child's `clientOrderId`

The WS client receives the fill and looks up by `clientOrderId` then `exchangeOrderId` in OrderIndex. Both miss because:
1. `clientAlgoId` was never registered as a lookup key
2. The child's `exchange_order_id` is a new ID unknown to the system

### Guardian Recovery Path — NOT Active in This Runtime

The code fix adds a fallback: on OrderIndex miss, ask `OrderGuardian.resolve_terminal_bracket_context()`. This guardian-backed recovery exists in the current branch but was **not deployed** — the domain_execution_position.log shows zero `resolve_terminal_bracket_context` calls or `correlation_recovered` events.

### ManageFlowFSM State Divergence

All four positions remained in `manage_state=BRACKETS_PENDING` after the bracket filled on the exchange. ManageFlowFSM never transitioned to FLAT because it never received the fill event. The sidecar records confirm this: `manage_flow_created: false`, `closing_position: false`, `manage_state: BRACKETS_PENDING`.

### PositionTracking Disappearance Fallback

When the next `ACCOUNT_UPDATE` arrived showing the symbol absent, PositionTracking used set-difference detection and attributed the closure as `unknown_disappearance`. The fix for this (checking `ExecPosFSM.get_recent_terminal_close_proof()` first) exists in code but was not deployed.

---

## 7. Exchange UI vs Runtime Reconciliation

### BTCUSDT 14:01:32 (3 rows in Binance UI)

| Question | Answer |
|---|---|
| Distinct economic close events? | **1** — one SL bracket triggered, one market order placed |
| Exchange trades/fills? | **3** — market order matched against 3 counterparties |
| Runtime close-bearing events processed? | **0** — all 3 were ORDERINDEX_MISS, dropped |
| Realized PnL UI rows? | **3** — one per exchange trade (expected Binance behavior) |
| Extra rows explained by? | **Exchange fragmentation** — not a system bug |

### Other Clusters (10:59:44, 03:28:02, 17:23:04)

| Question | Answer |
|---|---|
| Runtime artifacts available? | **NO** — these timestamps fall outside structured log coverage or during WAL gaps |
| Can they be reconciled? | **NO** — insufficient evidence |
| Most likely explanation? | Same mechanism (bracket fills from a prior runtime session), but UNPROVEN |

---

## 8. Root Cause Verdict

### Ranked by Severity and Confidence

| Rank | Classification | Confidence | Evidence |
|---|---|---|---|
| **1** | `EXPECTED_EXCHANGE_FRAGMENTATION` | **HIGH** (proven for BTCUSDT 14:01:32) | 3 partial fills for 1 SL market order within 6ms, same exchange_order_id, same event batch |
| **2** | `ORDER_CORRELATION_FAILURE` | **HIGH** (proven for all 4 symbols) | All bracket child fills dropped as ORDERINDEX_MISS due to unregistered child IDs |
| **3** | `LIFECYCLE_TRUTH_DIVERGENCE` | **HIGH** (proven) | ManageFlowFSM stuck at BRACKETS_PENDING; PositionTracking attributed as unknown_disappearance; internal state diverged from exchange truth |
| **4** | `POSITION_DISAPPEARANCE_MISATTRIBUTION` | **HIGH** (proven) | All 4 closures labeled "unknown_disappearance" instead of "proven_exchange_bracket_close" (SL or TP) |

### NOT Present

| Classification | Status | Evidence |
|---|---|---|
| `REPEATED_CLOSE_COMMAND_PATH` | **NOT FOUND** | Zero CMD:CLOSE or DEC:CLOSE events in audit window |
| `RUNTIME_DUPLICATE_TERMINAL_EVENT_HANDLING` | **NOT FOUND** | Each WS event processed exactly once (as a miss) |
| `EXPECTED_BRACKET_CHILD_MULTI_FILL` | N/A | Not applicable — the multi-fill is at the exchange level, not the bracket-child level |

### Dominant Cause

**`MIXED_CAUSE`**: The screenshot "jitter" is caused by `EXPECTED_EXCHANGE_FRAGMENTATION` (exchange fills a market order in pieces). The system's failure to properly handle these is caused by `ORDER_CORRELATION_FAILURE` (bracket children not in OrderIndex). The false attribution is `POSITION_DISAPPEARANCE_MISATTRIBUTION`. All three are concurrent and compound into the visible symptoms.

---

## 9. Operational Severity

### Is this mostly cosmetic?

**NO.** The exchange UI appearance (multiple realized PnL rows at the same second) IS cosmetic — it's standard exchange behavior. But the underlying system failure is NOT cosmetic:

1. **Internal state divergence is MODERATE severity**: ManageFlowFSM stays BRACKETS_PENDING while position is FLAT on exchange. This blocks new entries for the symbol (OPEN_GUARD_FAIL observed for all 4 symbols post-close).
2. **Close truth pipeline completely broken is MODERATE-HIGH severity**: Zero bracket fills reach the system's truth pipeline. The system has no knowledge that its own brackets executed.
3. **Disappearance misattribution is MODERATE severity**: Operators see "unknown_disappearance" instead of "proven SL/TP close", destroying operational trust and auditability.
4. **No economic double-close risk**: The exchange-side brackets use `closePosition=True` and are OCO-managed by the exchange. Once one bracket fills, the other is automatically canceled by Binance. No duplicate economic action occurs.

### Is it a real trading-risk issue?

**PARTIALLY.** No double-close or economic loss occurs. But:
- The system cannot learn from its own close outcomes (no close_reason attribution for strategy feedback)
- Post-close entry for the same symbol is blocked by stale BRACKETS_PENDING state until TTL sweep (up to 3600s)
- sidecar/lifecycle/strategy layers operate on false premises

### Is it phase-blocking for current execution/sidecar work?

**YES.** The sidecar cannot evaluate positions that have already closed because it reads stale `manage_state=BRACKETS_PENDING` with `portfolio_snapshot_status=symbol_absent`. This was already identified as Blocker 6 in the deep audit.

---

## 10. What Is Proven vs Still Unproven

### PROVEN

1. BTCUSDT 14:01:32 UTC+3 (11:01:32 UTC): 3 realized PnL rows caused by 3 partial fills of 1 SL market order — `EXPECTED_EXCHANGE_FRAGMENTATION`
2. All 4 bracket close fills were ORDERINDEX_MISS — `ORDER_CORRELATION_FAILURE` due to bracket children not registered in OrderIndex
3. The `clientAlgoId` from bracket placement IS the `clientOrderId` in the WS fill event — the IDs are recoverable but the system doesn't use them
4. All 4 positions were misattributed as `unknown_disappearance` instead of proven bracket close
5. ManageFlowFSM state diverges from exchange truth on every bracket close
6. No duplicate close commands, no repeated economic actions, no double-close risk
7. The code fixes (Blocker 4 + guardian recovery + disappearance attribution) exist in the Phenix_v2 branch but were NOT deployed to this runtime
8. BTCUSDT closed by SL, SOLUSDT closed by SL, DOGEUSDT closed by SL, ETHUSDT closed by TP

### UNPROVEN

1. Screenshot clusters at 10:59:44, 03:28:02, and 2026-04-03 17:23:04 — no runtime artifacts exist for these timestamps
2. Whether those unreconciled clusters are from a prior runtime session or represent a different mechanism
3. Whether partial fill quantities for BTCUSDT bracket close sum correctly (fill quantities not captured in ORDERINDEX_MISS diagnostic records)
4. Whether DOGEUSDT entry fill anomaly (empty trade_id, zero commission) affects downstream behavior
5. Whether the deployed code fix (Blocker 4) would eliminate ALL ORDERINDEX_MISS events or only some
6. The `BRACKET-HEALTH` recovery loop's `-4130` errors — whether this loop adds latency or affects bracket trigger reliability
7. Whether the earlier BTCUSDT position (aurora_BTCUSDT_1775265304831, entry at 01:15 UTC) closed via the same bracket mechanism at one of the unreconciled timestamps

---

## 11. Next Exact Step

**Deploy the bracket-child-OrderIndex-registration fix (Blocker 4) to the live runtime and validate that bracket fills are correctly correlated, close-truth propagates to ManageFlowFSM (transition to FLAT), disappearance attribution shows `proven_exchange_bracket_close`, and the sidecar receives fresh lifecycle state.**

This single deployment addresses the root cause of findings #2, #3, and #4 from section 8. After deployment, run one trading session and verify:
1. Zero `EXECUTION_WS_BRACKET_CHILD_ORDERINDEX_MISS` events in trade_lifecycle
2. `ManageFlowFSM` transitions to FLAT within seconds of bracket fill
3. `POSITION_DISAPPEARANCE_ATTRIBUTED` shows `proven_exchange_bracket_close` (not `unknown_disappearance`)
4. New entries for the same symbol are allowed immediately after close (no OPEN_GUARD_FAIL stall)

If partial fills (like BTCUSDT's 3 trades) are still expected, confirm that only the LAST fill (status=FILLED) drives the terminal lifecycle transition, while PARTIALLY_FILLED events correctly update position quantity without premature flattening.

---

## Appendix A: Evidence Files Inspected

| File | Size | Coverage |
|---|---|---|
| `ops/wal/2026-04-04.jsonl` | 22.5 MB | 2026-04-04 00:16–20:59 UTC |
| `ops/wal/old/2026-04-03.jsonl` | 20.5 MB | 2026-04-02 21:00–2026-04-03 20:59 UTC |
| `ops/wal/old/2026-04-04.jsonl` | 2.9 MB | 2026-04-03 21:00–23:38 UTC |
| `logs/trade_lifecycle.jsonl` | 105 MB | 2026-04-04 08:01–21:27 UTC (65,474 lines) |
| `logs/order_log_v1.jsonl` | 335 KB | 2026-04-04 08:25–21:20 UTC (185 lines) |
| `logs/shadow_critical_event_journal_v1.jsonl` | 17.3 MB | 2026-04-04 08:01–21:27 UTC |
| `logs/domain_execution_position.log` | 4.2 MB | 2026-04-04 session |
| `logs/order_guardian.log` | 3.4 MB | 2026-04-04 session |
| `logs/aurora_trades.log` | 9.5 KB | 2026-04-04 session (UTC+3 timestamps) |
| `logs/aurora_events.jsonl` | 1.6 KB | 2026-04-04 session |
| `logs/execution_truth_warm_state_v1.json` | 1.5 KB | Snapshot at 15:10:04 UTC |

## Appendix B: Bracket Child ID Mapping (Proof Chain)

| Symbol | Bracket Type | algoId (system knows) | clientAlgoId (system generates) | Child exchangeOrderId (exchange generates) | Child clientOrderId (= clientAlgoId) |
|---|---|---|---|---|---|
| ETHUSDT | TP | 1000000041768643 | CTvkgP2EmIAeObSIIetreV | 8631380178 | CTvkgP2EmIAeObSIIetreV |
| BTCUSDT | SL | 1000000041808641 | sMfFVMJzRjxHzj8dp6WUip | 13021119614 | sMfFVMJzRjxHzj8dp6WUip |
| SOLUSDT | SL | 1000000041814502 | 8ORxbVohNkkTxKxSUJcDKt | 1835694621 | 8ORxbVohNkkTxKxSUJcDKt |
| DOGEUSDT | SL | 1000000041936137 | LNFcAsgt7pr0JufdudXlmT | 765795835 | LNFcAsgt7pr0JufdudXlmT |

**Key insight**: `clientAlgoId` (known at placement time) = `clientOrderId` (received at fill time). The system already possesses the correlation key but never registers it in OrderIndex.

## Appendix C: Timeline of All Close-Related Events (UTC)

```
10:12:03  ETHUSDT   TP bracket fills (1 fill)    → ORDERINDEX_MISS → unknown_disappearance (10:12:06)
10:28:01  SOLUSDT   SL bracket fills (1 fill)    → ORDERINDEX_MISS → unknown_disappearance (10:28:03)
11:01:31  BTCUSDT   SL bracket fills (3 fills)   → 3x ORDERINDEX_MISS → unknown_disappearance (11:01:35)
15:12:30  DOGEUSDT  SL bracket fills (1 fill)    → ORDERINDEX_MISS → unknown_disappearance (15:12:36)
```

All closes are bracket-originated. No manual/external closes. No system-initiated CMD:CLOSE. No duplicate close processing. The exchange did exactly what the system asked it to do. The system just couldn't hear the answer.
