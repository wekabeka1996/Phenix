# ACTIVE_POSITION_LIFECYCLE_AND_SIDECAR_POSITION_POLICY_DISCOVERY_REPORT

## 1. Executive Summary

Current runtime open-position management is split, not unified.

- `OrderIndex` owns order identity, reservation, and terminal-order bookkeeping.
- `ManageFlowFSM` owns local position/bracket lifecycle truth.
- `CloseFlowFSM` is now a soldier path for explicit `CMD:CLOSE`, not an autonomous close-policy engine.
- `CloseExecutor` owns actual `DEC:CLOSE` execution, including partial close, bracket teardown, and reconcile.
- `OrderGuardian` owns bracket ownership mapping and cleanup/reconcile telemetry, but tidy is explicitly not business-close truth.

Key runtime truths:

- The one proven execution-side position lifetime timer is `ManageFlowFSM._check_max_hold_time()`.
- Most other timers are order-centric: ACK timeout, fill timeout, pending-entry TTL, limit-order timeout, orphan cleanup cadence.
- Live close/reduce paths already include TP1 partial exit, TP2/legacy TP full exit, SL full exit, explicit `CMD:CLOSE`, max-hold `DEC:CLOSE`, and a decision-side regime-flip close path.
- Exchange-side trailing stop adjustment is live in `ManageFlowFSM`.
- Dynamic TP extension or TP replacement was not proven live.
- Aurora also has a live post-entry evaluation surface in `ExitManager`; exact downstream execution effect of every branch was not fully proven here.

Major conclusion:

- Cause: state ownership and policy ownership are already distributed.
- Mechanism: position truth, close execution, and cleanup are handled by different owners.
- Effect: a future sidecar can be additive only if it does not claim SSOT and does not bypass existing close hardening.
- Operational risk: a sidecar that writes bracket state or duplicates close authority will race current FSMs.

## 2. FACTS

- `execution_position/domain_dict.json` assigns order state to `OrderIndex` and position state to `ManageFlowFSM`.
- `ExecPosFSM` stores `manage_flows` and `close_flows` per symbol.
- `ManageFlowFSM` stores position qty, entry, side, open timestamp, entry IDs, bracket IDs, and trailing state.
- `ManageFlowFSM.has_active_lifecycle()` treats bracket IDs alone on `FLAT` as insufficient lifecycle truth.
- `CloseFlowFSM._check_close_conditions()` returns `None`; autonomous close logic is disabled.
- `CloseExecutor.execute_close()` performs partial/full reduce-only close plus bracket cleanup and reconcile.
- `OrderGuardian.cleanup_orphans()` emits tidy events with `business_close_reconciled=false`.
- `OrderGuardian.reconcile_symbol()` emits `EVT:EXECUTION_CLOSE_RECONCILED` with `business_close_reconciled=true`.
- `ExecPosFSM` suppresses duplicate close propagation and duplicate non-`CMD` `DEC:CLOSE` execution.
- `ManageFlowFSM._check_max_hold_time()` emits `DEC:CLOSE`.
- `ManageFlowFSM` has live TP1/TP2 handling and live trailing stop replacement.
- `ManageFlowFSM` contains a TODO for breakeven after TP1; no runtime branch implements it.
- `EntryManager.handle_order_timeout()` emits `EVT:ORDER_TIMEOUT` and cancels the timed-out order.
- `LimitOrderMonitor` emits `EVT:LIMIT_ORDER_TIMEOUT` and cancels expired limit orders.
- `IntentRouter` routes `reduce_only` intents to `CMD:CLOSE`.
- `test_regime_flip_close_path_p0.py` proves a live decision-side regime-flip close path.
- `aurora_decision.py` calls `exit_manager.check_exit()` when `current_position_side != ""`.
- `features_calculated_v1.json` proves runtime payload support for OBI, TFI, delta_price, liquidity_kappa, absorption, and price-motion.
- `REPORT.md` proves watchdog ACK/FILL TTLs are wired, but watchdog `check_interval_ms` and `rps_limit` are not wired from the FSM boundary.

## 3. INFERENCES

- `ManageFlowFSM` is the nearest runtime SSOT for "position is open / reducing / flat" inside `execution_position`.
- `OrderGuardian` is a cleanup/reconcile owner, not a trading-policy owner.
- A future sidecar needs both execution truth and decision/feature context, so strategy-local ownership is weak.
- The future sidecar will overlap existing policy unless precedence is explicit against regime-flip, max-hold, trailing, and Aurora exit evaluation.

## 4. UNKNOWNS

- UNPROVEN: whether every Aurora `ExitManager` forced-exit branch reaches a live reduce-only close command end to end.
- UNPROVEN: whether `ExitManager` stop-loss override mutates already-open exchange brackets rather than only changing upstream signal payload.
- UNPROVEN: whether the current runtime exposes a stable cross-event `position_id` or lifecycle ID.
- UNPROVEN: whether `EVT:TICK_FEATURES_CALCULATED` is a clean current runtime dependency for a position-life sidecar.

## 5. Current Runtime SSOT for Orders vs Positions

| Surface | Authoritative owner | Runtime role | Status |
| --- | --- | --- | --- |
| Pending order identity / reservation | `OrderIndex` | client/exchange IDs, reservation, terminal bookkeeping | ACTIVE |
| Timed-out order action | `OrderTimeoutWatchdog` + `EntryManager` | ACK/FILL timeout handling | ACTIVE |
| Local open-position lifecycle | `ManageFlowFSM` | position qty, side, entry, brackets, trailing, active-lifecycle truth | ACTIVE |
| Explicit close intent | `CloseFlowFSM` | `CMD:CLOSE` -> `DEC:CLOSE` | ACTIVE |
| Close execution | `CloseExecutor` | reduce-only close, bracket teardown, reconcile | ACTIVE |
| Bracket cleanup / reconcile | `OrderGuardian` | orphan cleanup, tidy, authoritative close reconcile | ACTIVE |
| Portfolio snapshot | `position_tracking` | account/position state feed into EP and DM | ACTIVE |

State transition map:

1. `TRADE_INTENT_PROPOSED` enters EP.
2. `IntentRouter` routes to `CMD:OPEN` or `CMD:CLOSE`.
3. Entry fill activates `ManageFlowFSM` lifecycle and bracket placement.
4. `ManageFlowFSM` handles bracket fills, trailing, and max-hold.
5. Explicit close / regime-flip close / max-hold close become `DEC:CLOSE`.
6. `CloseExecutor` closes and `OrderGuardian` reconciles.

Major conclusion:

- Cause: order truth and position truth are intentionally separated.
- Mechanism: `OrderIndex` handles order identity while `ManageFlowFSM` handles position lifecycle.
- Effect: a future sidecar must not infer "position open" from order metadata or orphan bracket state.
- Operational risk: bracket remnants can create phantom lifecycle assumptions if used as SSOT.

## 6. Current Close / Reduce / Timeout Trigger Inventory

| Trigger | Owner | Applies to | Runtime action | Status |
| --- | --- | --- | --- | --- |
| SL fill | `ManageFlowFSM` | Open position | full close | ACTIVE |
| TP1 fill | `ManageFlowFSM` | Open position | partial reduce | ACTIVE |
| TP2 / legacy TP fill | `ManageFlowFSM` | Open position | full close | ACTIVE |
| Trailing stop adjust | `ManageFlowFSM` | Open position | replace SL | ACTIVE |
| Max hold time | `ManageFlowFSM` | Open position | emit `DEC:CLOSE` | ACTIVE |
| Explicit `CMD:CLOSE` | `CloseFlowFSM` + `CloseExecutor` | Open position or partial reduce | close execution | ACTIVE |
| Reduce-only intent | `IntentRouter` | Open position | route to `CMD:CLOSE` | ACTIVE |
| Regime-flip close | decision side | Open position | reduce-only close request | ACTIVE |
| Pending-entry stale regime cancel | `EntryManager` / EP handlers | Pending order only | cancel entry | ACTIVE |
| Watchdog timeout | watchdog + `EntryManager` | Pending order only | cancel timed-out order | ACTIVE |
| Limit-order timeout | `LimitOrderMonitor` | Pending limit order only | cancel expired limit | ACTIVE |
| Orphan cleanup | `OrderGuardian` | Orphan reduce-only brackets | tidy cleanup | ACTIVE |
| Close reconcile | `OrderGuardian` | Closed symbol | authoritative reconcile event | ACTIVE |

Time-based logic ledger:

| Timer | Owner | Scope | Effect | Verdict |
| --- | --- | --- | --- | --- |
| ACK TTL | watchdog | Order | expire unacked order | ACTIVE |
| FILL TTL | watchdog | Order | expire unfilled order | ACTIVE |
| LIMIT timeout | limit monitor | Order | cancel expired limit | ACTIVE |
| Pending-entry TTL | pending-entry path | Order | stale entry cancellation | ACTIVE |
| Max hold sec | `ManageFlowFSM` | Position | `DEC:CLOSE` | ACTIVE |
| Trailing min update interval | `ManageFlowFSM` | Position | rate-limit SL replacement | ACTIVE |
| Reentry cooldown | Aurora decision | Post-close policy | suppress re-entry | ACTIVE |
| Holding period | Aurora decision | Open-position policy | suppress soft exit/flip | ACTIVE |

Explicit fake-assumption callout:

`ORDER_TIMEOUT` and `LIMIT_ORDER_TIMEOUT` are not position-life intelligence. They are order expiry surfaces.

## 7. Dynamic TP / Trailing / TP Replacement Reality Audit

| Mechanism | Owner | Status | What it does |
| --- | --- | --- | --- |
| Initial SL placement | EP bracket path | ACTIVE | places exchange SL after entry |
| Initial TP / TP1 / TP2 placement | EP bracket path | ACTIVE | places exchange TP orders |
| TP1 partial exit | `ManageFlowFSM` | ACTIVE | reduces qty and preserves runner logic |
| TP2 / legacy TP full exit | `ManageFlowFSM` | ACTIVE | flattens lifecycle |
| Exchange-side trailing stop replacement | `ManageFlowFSM` | ACTIVE | cancel old SL, place new SL |
| Aurora synthetic trailing exit | `ExitManager` | ACTIVE as decision surface | evaluates exit pressure upstream |
| Aurora danger-zone tighten/exit | `ExitManager` | ACTIVE as decision surface | forces exit or stop override upstream |
| Aurora time exit / signal reversal | `ExitManager` | ACTIVE as decision surface | evaluates exit upstream |
| Break-even after TP1 | none proven | DECLARED-BUT-NOT-USED | TODO only |
| Dynamic TP replacement | none proven | UNPROVEN | no live mutation path traced |
| TP extension | none proven | UNPROVEN | no live mutation path traced |
| `TRAILING_STOP_MARKET.callbackRate` | trading params | DECLARED-BUT-NOT-USED | no runtime consumer proven |

Major conclusion:

- Cause: bracket ownership already exists in execution runtime, but broader TP lifecycle policy does not.
- Mechanism: `ManageFlowFSM` owns exchange-side bracket mutation; Aurora `ExitManager` is upstream evaluation, not proven exchange bracket owner.
- Effect: future sidecar scope can include hold/reduce/early-close reasoning, but TP mutation is not a free insertion point.
- Operational risk: direct TP/SL mutation by a sidecar would fight existing bracket ownership.

## 8. Microstructure-Based Early Cut Feasibility

| Signal / context | Proven source | Accessible without breaking contracts? | Notes | Verdict |
| --- | --- | --- | --- | --- |
| `obi` | `EVT:FEATURES_CALCULATED.features.obi` | Yes | already used in risk scoring and Aurora entry plan per existing repo report | FEASIBLE, duplication-sensitive |
| `tfi` | `EVT:FEATURES_CALCULATED.features.tfi` | Yes | already used in risk scoring and mean-reversion veto per existing repo report | FEASIBLE, duplication-sensitive |
| `delta_price` | `EVT:FEATURES_CALCULATED.features.delta_price` | Yes | already used in risk scoring | FEASIBLE |
| `liquidity_kappa` | `EVT:FEATURES_CALCULATED.features.liquidity_kappa` | Yes | may overlap liquidity/risk gates | FEASIBLE |
| `spread_bps` | FE additive feature surface | Yes if emitted | likely overlaps danger-zone / spread-health logic | FEASIBLE |
| `price_motion` / `pm_norm_*` | `EVT:FEATURES_CALCULATED.price_motion` | Yes | overlaps Aurora price-motion sanity | FEASIBLE, high double-count risk |
| `macro_resid` | FE additive feature surface | Yes if emitted | macro-context already embedded | FEASIBLE, very high double-count risk |
| Structural regime + confidence | `EVT:REGIME_DETECTED` | Yes | includes raw/stable and confidence fields | FEASIBLE |
| Portfolio / exposure | `PORTFOLIO_STATE_UPDATED`, `EXPOSURE_SUMMARY_UPDATED` | Yes | account/risk context, not position-health by itself | FEASIBLE |
| `absorption` | feature contract | Yes | current shared bar schema still describes it as placeholder | FEASIBLE but weak |
| Time-in-position | derived only | Only via local sidecar state | no shared contract field | FEASIBLE if sidecar keeps state |
| MAE / adverse excursion | none proven | No clean shared contract | requires new derivation/contract | UNPROVEN |

Likely strongest future signals:

- local structural regime deterioration
- OBI/TFI reversal with worsening delta/price motion
- liquidity/spread deterioration

Likely noisiest signals:

- current shared-contract `absorption`
- `macro_resid`
- raw `pm_norm_*` used alone

Major conclusion:

- Cause: contracts already expose rich feature context.
- Mechanism: `EVT:FEATURES_CALCULATED` plus `EVT:REGIME_DETECTED` can seed a sidecar cache.
- Effect: microstructure-based early cut is technically feasible today.
- Operational risk: several candidate signals are already live elsewhere, so unbounded reuse will double-count.

## 9. Sidecar Position-Policy Feasibility

| Candidate | Ownership fit | Conflict risk | Additive-only fit | Verdict |
| --- | --- | --- | --- | --- |
| New file in `decision_making` | Weak to medium | High with `ExitManager`, holding period, regime-flip | Weak | REJECT as primary owner |
| New file in `execution_position` | Strong | Medium if command-through-existing-owner | Strong | STRONGEST CANDIDATE |
| Strategy-local overlay | Weak | High and fragmented | Weak | REJECT |
| Separate domain/service | Medium | Medium to high because state cache must be rebuilt | Medium | SECONDARY candidate later |

Why `execution_position` is strongest:

- it already owns position/bracket truth and close hardening
- it can still subscribe to regime/features/portfolio events
- it can remain additive if it emits recommendations or close/reduce requests through existing paths

Major conclusion:

- Cause: future logic needs the richest live position truth plus safe close execution.
- Mechanism: `execution_position` already holds both.
- Effect: the sidecar belongs nearest `ManageFlowFSM`, not as a replacement for it.
- Operational risk: if it becomes a parallel execution FSM, blast radius expands immediately.

## 10. Event Subscription Matrix

Minimum viable set:

| Event | Why needed | Payload sufficiency |
| --- | --- | --- |
| `EVT:TRADE_EXECUTED` | actual fills, price, qty, timing | Medium |
| `EVT:ORDER_FILL` | additive fill aliases and richer order context | Medium |
| `EVT:ORDER_STATE_CHANGED` | terminal non-fill states | High for order state |
| `EVT:REGIME_DETECTED` | local regime and confidence | High |
| `EVT:FEATURES_CALCULATED` | microstructure, liquidity, motion, macro features | High for bar-driven sidecar |
| `EVT:PORTFOLIO_STATE_UPDATED` | account/position snapshot | Medium |
| `EVT:EXECUTION_CLOSE_RECONCILED` | authoritative close confirmation | High |
| `EVT:EXIT_MATCH_ATTEMPTED` / `FAILED` | exit-fill attribution | High |

Nice-to-have:

- `EVT:EXPOSURE_SUMMARY_UPDATED`
- `EVT:ORDER_TIMEOUT`
- `EVT:LIMIT_ORDER_TIMEOUT`
- `EVT:EXECUTION_TIDY_PERFORMED` / `EVT:SYMBOL_TIDY`

Missing fields that matter:

- stable `position_id` / lifecycle ID
- explicit entry-vs-exit role on canonical fill/trade events
- consistent close reason propagation end to end
- position-health attribution fields if sidecar logic is added later

## 11. Conflict / Duplication Risk Matrix

| Severity | Surface | What collides | Worst case |
| --- | --- | --- | --- |
| HIGH | `CMD:CLOSE` / `DEC:CLOSE` hardening | sidecar issues close while another close is already in flight | duplicate close suppression hides root cause |
| HIGH | `ManageFlowFSM` trailing/brackets | sidecar mutates TP/SL directly | bracket race and split-brain exits |
| HIGH | Regime-flip close | sidecar adds second regime-driven close | same regime event triggers two close systems |
| HIGH | Aurora `ExitManager` | sidecar duplicates danger-zone, time exit, or signal reversal | double-counted policy pressure |
| HIGH | Macro features | sidecar reuses `macro_resid` or anchor context as separate exit reason | macro context counted twice |
| MEDIUM | OBI / TFI reuse | sidecar reuses signals already active in risk and MR veto | invisible semantic double-count |
| MEDIUM | Price-motion reuse | sidecar reuses motion already consumed by Aurora gates | entry/exit logic drift |
| MEDIUM | Timeout confusion | order timers mistaken for position-life timers | wrong lifecycle action |
| LOW | Tidy vs close reconcile | cleanup mistaken for business close | local context reset too early |

## 12. Observability Gaps

Current strengths:

- exit-match attribution is strong
- tidy vs business-close split is strong
- structural regime payload is reasonably rich

Current gaps:

- no standard position-health trace
- no explicit policy-source field across close flows
- no stable position lifecycle ID across all relevant events
- no shared time-in-position, MFE, or MAE contract
- no standard explanation for "held", "reduced", "extended target", or "soft early cut"

Masking layers:

- tidy telemetry can be misread as business close if `business_close_reconciled` is ignored
- duplicate-close suppression can hide competing close sources
- decision-side exit evaluation can be mistaken for execution-side ownership

## 13. What Must Not Be Changed Yet

- Do not move position truth out of `ManageFlowFSM`.
- Do not bypass `CloseExecutor` or current `DEC:CLOSE` hardening.
- Do not let a sidecar write bracket state directly.
- Do not treat order timeout surfaces as substitutes for position-life policy.
- Do not mutate structural regime semantics to encode position health.
- Do not merge tidy and business-close meanings.

## 14. Final Verdict

Yes, a new standalone event-driven sidecar file is feasible, but only as an additive policy layer and not as a new state owner.

The safest current attachment point is inside `execution_position`, with these rules:

- subscribe to existing events
- keep only derived local context
- emit recommendation or close/reduce requests through existing command paths
- leave `ManageFlowFSM`, `CloseExecutor`, and `OrderGuardian` as the single owners of lifecycle truth, close execution, and reconcile semantics

The main RFC blockers are contract clarity and overlap control, not missing execution machinery:

- position-scoped identity is weak
- Aurora already has overlapping post-entry evaluation
- current observability is not rich enough yet for safe position-health rollout without new trace fields
