# Neocortex ↔ Aurora Integration Data Contract Audit

**Package:** NEO-INTEGRATION-DATA-CONTRACT-AUDIT
**Date:** 2026-03-11
**Scope:** Audit-only. No code changes.
**Verdict:** ⚠️ PARTIAL LAUNCH POSSIBLE — Offline replay only. Shadow launch blocked by lifecycle/reward contract gaps.

---

## Executive Summary

Neocortex completed P1–P9 remediation and is contract-clean, production-shadow-gated, evaluator-equipped, advisory-forbidden, and policy-training-disabled. The Aurora trading system is undergoing an active refactoring of order/execution/lifecycle logic.

This audit establishes the **compatibility surface** between the neocortex contract requirements (post-P9) and the data/events actually produced by the current Aurora execution/trading stack.

### Key Findings

1. **EVT:FEATURES_CALCULATED** — **COMPATIBLE**. Neocortex consumes this successfully via MultiTailer/adapter pipeline. Fields (`symbol`, `ts`/`event_ts_ms`, `features`) are well-formed and stable.

2. **EVT:TRADE_INTENT_PROPOSED** — **COMPATIBLE**. Decision-making `intent_builder.py` emits a structured payload with `instrument`, `side`, `order`, `why[]`, `regime`, `dto_version`, `schema_ref`, `idempotent_key`. Sufficient for shadow comparison.

3. **EVT:POSITION_CLOSED** — **MISSING / TRANSITIONAL**. This is the **primary hard blocker**. Neocortex requires a structured `POSITION_CLOSED` event with `trade_id`, `close_ts_ms`, `realized_pnl_net`, `fees`. Aurora's `execution_position` detects position closures via **portfolio diffing** in `event_handlers.py:on_portfolio_state_updated()` — this produces only `symbol`, `realized_pnl` (from cached fill data), and `close_reason`, **without** the structured fields neocortex requires per its reward contract.

4. **Lifecycle Identity** — **PARTIALLY COMPATIBLE**. Neocortex expects `lifecycle_id`, `trade_id`, `order_id`, `client_order_id`. Aurora's execution side uses `rid` (request ID), `orderId` (exchange), `clientOrderId` (prefixed: `ENTRY-`, `SL-`, `TP-`, `CLOSE-`). There is **no authoritative `lifecycle_id`** concept on the Aurora side; mapping is possible but requires bridging logic.

5. **Time Contract** — **COMPATIBLE** with caveats. Both systems use epoch-millisecond timestamps. Neocortex normalizes via `_normalize_epoch_to_ms()`. Aurora uses `get_clock().now_ms()`. The causal ordering requirement is satisfied for live/shadow modes.

6. **Reward Contract** — **MISSING**. Neocortex requires `EpisodeReward` with `episode_id`, `trade_id`, `entry_ts_ms`, `close_ts_ms`, `entry_price`, `close_price`, `quantity`, `realized_pnl`, `fees`, `net_pnl`, `reward_complete`. Aurora does not produce a structured reward event. The `_episode_to_dict()` adapter method gracefully degrades (sets `reward_missing=True`), but without reward truth, all execution-quality samples become **diagnostics-only** and cannot enter trainable buffers.

---

## A. Required Input Contract from Neocortex (Post P1–P9)

### A.1 Time Contract

| Requirement | Status | Evidence |
|---|---|---|
| Canonical `event_ts_ms` (epoch_milliseconds, int) | REQUIRED | `domain.yaml` L14-16, `adapter.py` `_extract_event_ts_ms()` |
| Causal ordering | REQUIRED | `domain.yaml` L18 |
| Replay-safe timestamps (no wallclock dependency) | REQUIRED | `domain.yaml` L19 |
| Legacy `legacy_non_causal_file_offset` compatibility | OPTIONAL | `config_models.py` L797-816 |

### A.2 Lifecycle / Identity Contract

| Requirement | Status | Evidence |
|---|---|---|
| `lifecycle_id` as primary identity | REQUIRED | `domain.yaml` L23 |
| `order_id` / `client_order_id` as fallback | FALLBACK | `domain.yaml` L24-26 |
| `trade_id` for close resolution | REQUIRED for reward | `domain.yaml` L27, L59 |
| ORDER_FILLED as executed-entry anchor | REQUIRED | `domain.yaml` L31 |
| POSITION_CLOSED must resolve by `trade_id` | REQUIRED | `domain.yaml` L32 |
| Partial fill handling | REQUIRED | `domain.yaml` L34 |
| Unresolved lifecycle → fail-closed | ENFORCED | `domain.yaml` L33 |

### A.3 Reward Contract

| Requirement | Status | Evidence |
|---|---|---|
| `EpisodeReward` after authoritative close event | REQUIRED | `domain.yaml` L36-61 |
| Authoritative: POSITION_CLOSED or TRADE_CLOSED | REQUIRED | `domain.yaml` L38-39 |
| All 16 EpisodeReward fields | REQUIRED | `domain.yaml` L41-56 |
| Incomplete rewards → diagnostics-only | ENFORCED | `domain.yaml` L61 |

### A.4 Objective Families

| Family | Route | Status |
|---|---|---|
| `representation` | `train_async` | ACTIVE |
| `regime_supervision` | `train_regime_supervision` | ACTIVE |
| `execution_quality` | `execution_quality_buffer` | ACTIVE |
| `policy` | `train_policy` | **BLOCKED** (`policy_training_mode=disabled`) |

### A.5 Sequence Contract

| Requirement | Status |
|---|---|
| `stateless_per_event` inference mode | ACTIVE |
| `independent_rows` representation training | ACTIVE |
| Reset on replay start / symbol switch / objective switch / episode boundary | ENFORCED |

### A.6 Dataset / Provenance Contract

| Requirement | Status |
|---|---|
| `DatasetSampleProvenance` with all provenance fields | ENFORCED |
| Trainable admission explicit | ENFORCED |
| Policy samples rejected when disabled | ENFORCED |
| Legacy non-causal rows blocked from causal families | ENFORCED |

### A.7 Performance / Runtime Modes

| Mode | Status |
|---|---|
| `offline_replay` (default) | ACTIVE |
| `live_shadow` | DEFINED, requires `emit_all` + `stride=1` |
| Decimation only on observational outputs | ENFORCED |

### A.8 Gate Contract

| Gate | Status |
|---|---|
| ShadowGateEvaluator startup enforcement | ACTIVE |
| Advisory influence | HARD-FORBIDDEN |
| Policy training re-enable | HARD-FORBIDDEN |
| Live authority | HARD-FORBIDDEN |

---

## B. Actual Output/Data Contract from Aurora Trading System

### B.1 Event Taxonomy

| Event | Source | Shape | Status |
|---|---|---|---|
| `EVT:FEATURES_CALCULATED` | `feature_engineering` | `{symbol, ts, features{...}, price_ref}` | **STABLE** |
| `EVT:REGIME_DETECTED` | `regime_detector` | `{symbol, regime, confidence}` | STABLE |
| `EVT:TRADE_INTENT_PROPOSED` | `decision_making` | `{rid, instrument, side, order{qty,price,order_type,tif}, why[], regime, dto_version, idempotent_key}` | **STABLE** |
| `EVT:ORDER_ACK` | `execution_position` | `{orderId, symbol, rid}` | STABLE |
| `EVT:ORDER_FILL` | `execution_position` | `{orderId, symbol, quantity, price, side, rid, clientOrderId, realizedPnl, commission, tradeId}` | **STABLE** |
| `EVT:PORTFOLIO_STATE_UPDATED` | `position_tracking` | `{ts, equity, positions[], realized_pnl, unrealized_pnl}` | STABLE |
| `EVT:POSITION_CLOSED` | `execution_position` (portfolio diff) | **NOT STRUCTURED** — `{symbol, realized_pnl, close_reason}` only | **TRANSITIONAL** |
| `EVT:POSITION_OPENED` | NOT WIRED | Not emitted | **MISSING** |

### B.2 Time Semantics

| Aspect | Current State | Risk |
|---|---|---|
| Timestamp source | `get_clock().now_ms()` for execution; `ts` in features | LOW |
| Canonical `event_ts_ms` | Present in features, absent in close events | MEDIUM |
| Replay-safe ordering | Present for features | MEDIUM (unknown for lifecycle events) |

### B.3 Execution / Lifecycle Semantics

| Aspect | Current State | Gap |
|---|---|---|
| Order identity | `orderId` (Binance), `clientOrderId` (prefixed), `rid` | **No `lifecycle_id`** |
| Trade identity | `tradeId` in ORDER_FILL | Fills only |
| Position open detection | Via ORDER_FILL + portfolio update | **No structured POSITION_OPENED** |
| Position close detection | Portfolio diffing in `on_portfolio_state_updated()` | **INCOMPLETE**: no `trade_id`, `close_ts_ms`, `fees` |
| PnL truth | Cached `_last_realized_pnl_by_symbol` from fills | **BEST-EFFORT** |

### B.4 Reference Decision Surface

| Aspect | Status |
|---|---|
| Decision output | `EVT:TRADE_INTENT_PROPOSED` — **STABLE**, suitable for shadow comparison |
| Decision trace | `EVT:DECISION_TRACE_EMITTED` — AVAILABLE for deep analysis |

### B.5 Logging / Persistence

| Surface | Status |
|---|---|
| WAL | ACTIVE for intents, trades |
| Feature logs | AVAILABLE per-symbol |
| Order logger | ACTIVE (ORDER_INTENT, ORDER_FILLED, POSITION_CLOSED) |
| Trade lifecycle logger | ACTIVE |

---

## D. Launch Blockers

### D.1 Hard Blockers Before Real Shadow Launch

| # | Blocker | Location | Blocks Shadow? |
|---|---|---|---|
| HB-1 | No structured `EVT:POSITION_CLOSED` with `trade_id`/`close_ts_ms`/`realized_pnl_net`/`fees` | `execution_position/event_handlers.py` L153-263 | **YES** |
| HB-2 | No authoritative `lifecycle_id` on Aurora side | `event_handlers.py`, `intent_builder.py` | **YES** |
| HB-3 | No `EpisodeReward` producer in Aurora | No structured reward assembly | **YES** |

### D.2 Soft Blockers / Quality Risks

| # | Risk | Impact |
|---|---|---|
| SB-1 | `EVT:POSITION_OPENED` not wired | ORDER_FILL serves as entry anchor (acceptable for now) |
| SB-2 | PnL truth is best-effort cache | Can lose PnL data under concurrent fills |
| SB-3 | Close_reason tracking is best-effort | May misattribute close_reason |
| SB-4 | No `fees` in close detection path | Reward accuracy degraded |
| SB-5 | No stable `decision_id` for comparison corpus | `rid` adequate but not canonical |

---

## E. Minimum Launch-Ready Contract

### Phase 1: Offline Shadow Replay ✅ CAN LAUNCH NOW

- ✅ EVT:FEATURES_CALCULATED from feature logs
- ✅ Representation training (self-supervised)
- ✅ Regime supervision training (self-supervised)
- ✅ Shadow gate evaluator operational
- ✅ Dataset provenance pipeline operational
- ❌ Execution-quality training (no reward truth)
- ❌ Reward calibration reports

### Phase 2: Limited Shadow Runtime ❌ BLOCKED

Requires:
1. Structured `EVT:POSITION_CLOSED` with all required fields
2. `lifecycle_id` or deterministic lifecycle binding
3. `EpisodeReward` construction (Aurora-side or bridge)
4. Time causal ordering for execution events

### Phase 3: Full Shadow Acceptance Campaign ❌ BLOCKED

All Phase 2 plus stable Aurora execution contract, verified `reward_complete=true` for 100+ episodes, all SSOT configs frozen.

---

## Recommendation

**VERDICT: PARTIAL OFFLINE LAUNCH ONLY**

| Mode | Status | Rationale |
|---|---|---|
| Offline replay (representation + regime) | ✅ CAN LAUNCH | No dependency on execution lifecycle |
| Shadow with execution quality | ❌ BLOCKED | No structured close event, no reward truth |
| Acceptance campaign | ❌ BLOCKED | Data contract unstable during refactoring |
