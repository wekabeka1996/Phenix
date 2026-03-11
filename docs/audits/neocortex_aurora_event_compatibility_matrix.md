# Neocortex ↔ Aurora Event Compatibility Matrix

**Package:** NEO-INTEGRATION-DATA-CONTRACT-AUDIT
**Date:** 2026-03-11

---

## Legend

| Status | Meaning |
|---|---|
| COMPATIBLE | Neocortex requirement fully satisfied by Aurora output |
| PARTIALLY_COMPATIBLE | Requirement partially met; usable with degraded quality |
| MISSING | Requirement not met; Aurora does not produce this data |
| TRANSITIONAL_ONLY | Data exists but in unstable/transient form during refactoring |
| UNSAFE | Data exists but would produce incorrect results if used |

---

## Compatibility Matrix

| # | Neocortex Contract Item | Aurora Source / Event / Field | Status | Evidence | Blocker? | Notes |
|---|---|---|---|---|---|---|
| 1 | `EVT:FEATURES_CALCULATED` with `symbol`, `ts`, `features{}` | `feature_engineering` domain → `EVT:FEATURES_CALCULATED` | COMPATIBLE | `feature_engineering/` emits per-symbol, per-bar; `adapter.py` L444-555 consumes | No | Stable, well-tested path |
| 2 | `event_ts_ms` (canonical causal timestamp, epoch_ms int) | Feature events: `ts` / `timestamp` field | COMPATIBLE | `adapter.py:_extract_event_ts_ms()` L429-434 normalizes from `event_ts_ms`/`timestamp`/`ts` | No | Auto-normalization handles multiple field names |
| 3 | `EVT:TRADE_INTENT_PROPOSED` with `instrument`, `side`, `order{}`, `why[]` | `decision_making/intent_builder.py` → `EVT:TRADE_INTENT_PROPOSED` | COMPATIBLE | `intent_builder.py` L233-261 assembles full payload with regime, idempotent_key, schema_ref | No | Suitable for shadow disagreement comparison |
| 4 | `EVT:REGIME_DETECTED` with `symbol`, `regime`, `confidence` | `regime_detector` domain → `EVT:REGIME_DETECTED` | COMPATIBLE | `event_handlers.py:on_regime_detected()` L48-94 | No | Used for conditioning/gates |
| 5 | `EVT:ORDER_ACK` with `orderId`, `symbol` | `execution_position` → `EVT:ORDER_ACK` | COMPATIBLE | `event_handlers.py:on_order_ack()` L305-330 | No | |
| 6 | `EVT:ORDER_FILL` with `orderId`, `symbol`, `quantity`, `price`, `tradeId`, `realizedPnl`, `commission` | `execution_position` → `EVT:ORDER_FILL` | COMPATIBLE | `event_handlers.py:on_order_fill()` L332-511 | No | Rich payload including lifecycle logger integration |
| 7 | `lifecycle_id` (primary episode identity) | **Not produced by Aurora** | MISSING | No `lifecycle_id` concept in `execution_position` or `decision_making` | **YES — HB-2** | Would need bridge logic to synthesize from `rid`/`clientOrderId` |
| 8 | `trade_id` (close resolution identity) | `tradeId` in ORDER_FILL payload | PARTIALLY_COMPATIBLE | `event_handlers.py` L415: `fill_trade_id` in metadata | Partial | Present in fills but NOT in close detection path |
| 9 | `EVT:POSITION_CLOSED` with `trade_id`, `close_ts_ms`, `realized_pnl_net`, `fees` | Portfolio diffing in `event_handlers.py:on_portfolio_state_updated()` | TRANSITIONAL_ONLY | L153-263: detects close via `abs(prev) > ε && abs(now) < ε`; emits only `symbol`, `realized_pnl`, `close_reason` | **YES — HB-1** | Missing: `trade_id`, `close_ts_ms`, `fees`, structured reward fields |
| 10 | `EVT:POSITION_OPENED` (authoritative open event) | **Not wired** | MISSING | `domain.yaml` L31: "until POSITION_OPENED is wired as authoritative" | No (soft) — SB-1 | ORDER_FILL used as fallback entry anchor |
| 11 | `EpisodeReward` (16-field structured reward) | **No reward producer in Aurora** | MISSING | No structured reward assembly; `adapter.py:_episode_to_dict()` L896-992 gracefully degrades to `reward_missing=True` | **YES — HB-3** | All execution-quality samples degraded to diagnostics-only |
| 12 | `reward_complete=true` (authoritative close truth) | **Cannot be asserted** by Aurora currently | MISSING | Requires structured close + all reward fields; currently always false for execution path | **YES** | Blocks calibration/evaluator reports |
| 13 | `fees` in episode/reward data | `commission` in ORDER_FILL; **absent** from close detection | PARTIALLY_COMPATIBLE | `event_handlers.py` L417: commission logged in fill metadata but not propagated to close | Partial — SB-4 | Could be accumulated from fills if lifecycle binding exists |
| 14 | Causal ordering for execution events | `get_clock().now_ms()` used consistently | PARTIALLY_COMPATIBLE | Consistent timebase but no replay-safe guarantee for execution events | No | Replay from logs may lose ordering |

---

## Summary Statistics

| Status | Count | Items |
|---|---|---|
| COMPATIBLE | 6 | #1, #2, #3, #4, #5, #6 |
| PARTIALLY_COMPATIBLE | 3 | #8, #13, #14 |
| MISSING | 4 | #7, #10, #11, #12 |
| TRANSITIONAL_ONLY | 1 | #9 |
| UNSAFE | 0 | — |

---

## Critical Gaps (Hard Blockers)

| Blocker ID | Matrix Item(s) | Root Cause | Required Fix |
|---|---|---|---|
| HB-1 | #9 | Position close detected by portfolio diffing, not structured event | Implement structured `EVT:POSITION_CLOSED` event with required fields |
| HB-2 | #7 | No `lifecycle_id` concept in Aurora execution stack | Define and emit `lifecycle_id` (or provide deterministic mapping from `rid` ↔ `lifecycle_id`) |
| HB-3 | #11, #12 | No `EpisodeReward` assembly in Aurora | Implement reward producer OR neocortex-side bridge adapter |
