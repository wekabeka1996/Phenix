# EXECUTION_POSITION_CROSS_MODEL_REVIEW_2G

## Scope

Input reviewed: user-provided 2G model conclusion.

Evidence base: `/mnt/data/execution_position.zip`, extracted to local read-only workspace.

Mode: static cross-review only. No code changes. No tests run. No runtime logs checked.

## Coverage

```yaml
zip_python_files_available: 69
claims_reviewed: 24
claim_status:
  confirmed_or_mostly_confirmed: 15
  partially_confirmed_requires_test: 7
  not_confirmed_or_overstated: 2
runtime_proof: 0%
code_changes: 0
```

## Executive verdict

2G is useful and more aggressive than 1G. It contains several real defect candidates that should be merged into the master backlog. It also contains some overstatements, especially around Python task garbage collection and “CloseFlowFSM is dead decoration.”

The strongest new findings from 2G are:

1. `TradeIntentOpenIntake` and `TradeIntentOpenOrder` use `extra="ignore"` instead of `extra="forbid"`.
2. Open-intake numeric regex rejects scientific notation such as `1E-7`.
3. `OrderTimeoutWatchdog` can emit repeated `EVT:TRADE_EXECUTED` for unchanged `PARTIALLY_FILLED` cumulative quantity.
4. `pending_brackets_wal.py` silently skips malformed JSON rows during rehydrate.
5. `ExposureGuard.enter_fallback_mode()` exists but has no caller in the zip.
6. `SoftClipEngine` admits simplified directional clipping that collapses to `0`, not proportional clipping.
7. `OrderGuardian` poll-symbol discovery depends on config symbols plus a private `_data` fallback that only works for `InMemoryStore`, not ledger-backed stores.

## Claim review

### 1. Core FSM & Orchestration

#### 1.1 DEC/WAL state before async adapter execution

Status: CONFIRMED.

`ExecPosFSM._process_flow_result()` appends `DEC:*` to WAL before scheduling `_execute_decision()`. If no async loop exists, single DEC logs an error; BATCH branch has weaker terminal handling. This matches the previously found P1 candidate: DEC can become visible in the truth plane without guaranteed exchange-side terminal outcome.

Severity: P1.

Backlog mapping: already covered by `EXECUTION_SAFETY_GUARDRAILS`.

#### 1.2 `create_task()` without hard task references

Status: PARTIALLY CONFIRMED / OVERSTATED.

`AsyncSchedulingMixin._submit_async()` calls `target_loop.create_task(coro)` and does not keep the Task; `OrderGuardian.start()` keeps `_poller_task`, so this is not universal. The 2G claim that Python GC can simply kill all tasks before completion is too broad, but the real issue stands: fire-and-forget tasks have no result accounting, no done callback, and weak shutdown ownership.

Severity: P2, not P1 without a reproducer.

Required validation: schedule a coroutine that raises after await; assert visibility via log/event/metric.

#### 1.3 No locks around rapid sequential events

Status: PARTIALLY CONFIRMED.

There are locks in `fsm.py`, `order_guardian.py`, `order_index.py`, `order_ledger.py`, `truth_hardening.py`, and `metrics_collector.py`. So “absence of locks” is false globally. However, hot event ingress paths mutate several dictionaries without an obvious symbol-scoped lifecycle lock: `_pending_entry_meta`, `_last_lifecycle_*`, `manage_flows`, and sidecar symbol state.

Severity: P2 until a race reproducer exists.

#### 1.4 `CloseFlowFSM` is only a CMD:CLOSE producer seam

Status: MOSTLY CONFIRMED, but wording “dead decoration” is too strong.

`CloseFlowFSM._check_close_conditions()` explicitly returns `None` and states autonomous closing rules are disabled. `CMD:CLOSE` is adapted into `DEC:CLOSE`. The file still records shadow transitions and hydrates state, so it is not dead, but its autonomous FSM semantics are effectively disabled by design.

Severity: P3/P2 architectural debt.

## 2. State, Persistence & Recovery

#### 2.1 Split-brain across ManageFlowFSM / OrderIndex / OrderLedger / WAL

Status: CONFIRMED as architecture risk.

The domain does maintain multiple truth surfaces: in-memory FSM state, `OrderIndex`, ledger-backed order store, WAL/restore artifacts. The earlier master audit also flagged restart/restore truth as a high-risk zone. Static code does not prove an active bug, but lack of transaction semantics is real.

Severity: P2/P1 depending on path.

#### 2.2 OrderGuardian blind to ledger-backed symbols outside config

Status: MOSTLY CONFIRMED.

`OrderGuardian._iter_symbols_for_poll()` starts from `_known_symbols` extracted from config. It then tries `getattr(self.store, "_data", {})` to discover extra symbols. That fallback works only for `InMemoryStore`; ledger-backed `LedgerStoreAdapter` does not expose the same private `_data` map. Exceptions are swallowed.

Important nuance: this is not necessarily “blind to orders” everywhere, but poll discovery can miss symbols that are present only in ledger store and absent from config/known symbols.

Severity: P2.

#### 2.3 `pending_brackets_wal.py` silently skips corrupted JSON rows

Status: CONFIRMED.

The WAL rehydrate loop catches `json.JSONDecodeError` and `continue`s. There is a warning only around broader file read errors, not per-row corruption. For restore truth, silent row skip is dangerous: it can drop pending bracket truth without producing explicit degraded restore state.

Severity: P1/P2.

## 3. Risk, Exposure & Limits

#### 3.1 Flip logic ignores size

Status: CONFIRMED.

`ExposureManager` marks `is_flip=True` solely when current position side differs from intent side. It does not check whether the new order size fully closes, partially reduces, or truly flips the position. This matches the 1G review.

Severity: P1/P2.

#### 3.2 Directional ratio can be bypassed after flip subtraction

Status: PLAUSIBLE / NEEDS TEST.

`ExposureGuard.can_open()` subtracts `current_symbol_margin` when `is_flip=True`. If the order is only a tiny opposite-side order, projected side margins can become zero or even inconsistent if the current-symbol margin and aggregate side margin disagree. The directional ratio check only runs if `min_m > 0`; otherwise it is skipped.

The exact “denominator becomes < 0” case requires a concrete portfolio fixture. The broader defect is confirmed: size-blind `is_flip` can cause unsafe exposure subtraction.

Severity: P1/P2.

#### 3.3 Fallback mode exists but activation is unreachable

Status: CONFIRMED within zip.

`ExposureGuard.enter_fallback_mode()` is defined, but grep found no caller except the definition. `is_fallback_mode_active()` is checked inside `can_open()`, but the state is never entered by this zip’s code.

Severity: P2. This is an illusion of fallback readiness.

#### 3.4 Soft clipping is actually hard zero on directional breach

Status: CONFIRMED.

`SoftClipEngine.calculate_clipped_size()` contains a comment: “For now, simplified: if adding this order breaks ratio, reduce to 0.” It sets `delta_dir_notional = Decimal("0")` instead of solving the proportional maximum allowed notional.

Severity: P2. Documentation/comments should not imply true proportional clipping.

## 4. Contracts, Bridges & Intake

#### 4.1 `extra="ignore"` in `TradeIntentOpenIntake` / `TradeIntentOpenOrder`

Status: CONFIRMED.

Both models use `ConfigDict(extra="ignore")`.

This violates the project’s default law for money-impacting typed contracts. Unknown fields in the intake envelope can be silently dropped. The example `reduse_only` is not exact as a safety bypass because `reduce_only` defaults to `False`; however, silently accepting typoed fields is still contract-dangerous.

Severity: P1/P2.

#### 4.2 Decimal regex rejects scientific notation

Status: CONFIRMED.

Fields use pattern `^[0-9]+(\.[0-9]+)?$`, so values such as `1E-7` do not validate. If upstream stringifies small Decimals in scientific notation, valid exchange-scale values can fail open-intake validation.

Severity: P2.

#### 4.3 Missing idempotent key falls back to time-derived client order id

Status: PARTIALLY CONFIRMED.

`generate_client_order_id()` is deterministic if `idempotent_key` is provided, or if legacy callers pass `(role, rid, extra=symbol)`. Otherwise it includes `get_clock().now_ms()` in the hash. Open execution often uses `decision.idempotent_key or decision.rid`, so the worst case is not universal.

Still, the utility permits time-derived identity, and `intent_router` has external fallback ids like `ext-{time_ms}`. This should be treated as a duplication-protection weakness in any retry path missing stable idempotency.

Severity: P2.

## 5. Executors & Operations

#### 5.1 Bracket parallel placement can duplicate protective orders after partial failure

Status: CONFIRMED.

`BracketManager.place_brackets_parallel()` uses `asyncio.gather(..., return_exceptions=False)`. If one side succeeds or remains in-flight while the other raises, the fallback block attempts both SL and TP again with the same client IDs.

2G says “double SL” in one sentence and “TP” in another. The exact duplicated side depends on which coroutine succeeded before gather raised. The structural issue is partial-success retry without reconcile-by-clientOrderId before retry.

Severity: P1.

#### 5.2 GTX crossed/zero-spread guard proceeds unadjusted

Status: CONFIRMED, but severity depends on Binance behavior.

`OpenSubmissionPayload.apply_gtx_passive_guard()` returns unchanged price when `best_bid >= best_ask`. `OpenExecutor` logs a crossed/zero-spread warning and proceeds with unadjusted price. This can lead to maker-only reject rather than fail-closed pre-submit suppression.

Severity: P2. Not guaranteed “fatal,” but it is an avoidable reject path.

#### 5.3 Sidecar can spam close requests while closing position

Status: PARTIALLY CONFIRMED / OVERSTATED.

The sidecar evaluates on features, regime, order fill, order state, close reconciled, and portfolio updates. In `ENABLE` mode it can emit `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`.

However, there are suppressions:
- sidecar checks `manage_flow._closing_position`;
- mediator also suppresses if `_closing_position` is true;
- recommendation signature dedup suppresses same-state repeated recommendations;
- peak-giveback path resets armed state after command.

The real risk is not proven “rate-limit spam.” The real risk is that `_closing_position` lifecycle is fragile, and the close executor has paths where the flag can clear early or remain stuck. This should be tested, not asserted.

Severity: P2.

## 6. Telemetry & Infrastructure

#### 6.1 Watchdog repeated `TRADE_EXECUTED` for unchanged `PARTIALLY_FILLED`

Status: CONFIRMED strong candidate.

`OrderTimeoutWatchdog._poll_order_statuses()` emits `EVT:TRADE_EXECUTED` for status `FILLED` or `PARTIALLY_FILLED` whenever `executedQty > 0`. For `PARTIALLY_FILLED`, it intentionally keeps tracking and does not mark terminal. There is no visible check that cumulative `executedQty` increased since the last emitted event.

Therefore repeated polls can emit repeated `TRADE_EXECUTED` with the same cumulative executed quantity.

Severity: P1.

Required validation: fake `get_order_fn` returns same `PARTIALLY_FILLED executedQty` twice; expect only one incremental fill event or second event suppressed.

#### 6.2 Metrics collector rolling window claim is partly false

Status: CONFIRMED / LOW SEVERITY.

`MetricsCollector` stores `_rolling_data`, and `get_recent_rejections()` uses it. But `get_summary_metrics()` computes `rejection_rate` from process-lifetime counters. So the claim is partly true: summary rejection rate is lifetime-smoothed, not rolling-window based.

Severity: P3.

#### 6.3 Drift monitor false negatives with multi-fill

Status: PLAUSIBLE.

`compute_drift()` matches one decision to one event and marks unmatched events as false negatives. Multi-fill outcomes can produce extra unmatched events if there is one DEC and multiple FILL events under the same rid.

Severity: P3/P2 because the file says this is off-path shadow validation, not hot-path execution.

## New backlog items from 2G

```yaml
Package I:
  name: OPEN_INTAKE_STRICT_CONTRACT
  goal:
    - TradeIntentOpenIntake.extra -> forbid
    - TradeIntentOpenOrder.extra -> forbid
    - add regression for typoed fields

Package J:
  name: NUMERIC_STRING_DECIMAL_ACCEPTANCE
  goal:
    - replace brittle regex with Decimal parser validation
    - accept valid scientific notation only when finite and positive

Package K:
  name: WATCHDOG_PARTIAL_FILL_INCREMENTALITY
  goal:
    - repeated PARTIALLY_FILLED same cumulative qty must not emit duplicate TRADE_EXECUTED
    - emit only delta fill or suppress unchanged poll result

Package L:
  name: PENDING_BRACKETS_WAL_CORRUPTION_VISIBILITY
  goal:
    - JSONDecodeError row skip becomes explicit degraded restore record
    - corrupt rows counted and surfaced

Package M:
  name: GUARDIAN_LEDGER_SYMBOL_DISCOVERY
  goal:
    - remove private _data fallback as production symbol source
    - ledger-backed store must expose explicit symbols/orders iterator if polling needs it

Package N:
  name: EXPOSURE_FALLBACK_REACHABILITY
  goal:
    - either wire enter_fallback_mode to real portfolio/API failure path
    - or delete/mark fallback mode as dormant experimental surface

Package O:
  name: SOFT_CLIP_DIRECTIONAL_SOLVER_OR_RENAME
  goal:
    - implement proportional max notional solver
    - or rename/report current behavior as hard-zero directional clamp

Package P:
  name: GTX_CROSSED_BOOK_FAIL_CLOSED
  goal:
    - crossed/zero-spread GTX preflight returns terminal reject before exchange submit
    - no avoidable maker-only rejects when book is invalid
```

## Updated severity ranking after 1G + 2G

Highest priority test-first surfaces:

1. Bracket partial-success race and duplicate protective orders.
2. Watchdog repeated partial-fill emission.
3. Missing instrument config hardcoded fallback in open path.
4. Close `_closing_position` cleanup correctness.
5. Size-blind exposure flip semantics.
6. Open-intake `extra="ignore"` contract hole.
7. Pending bracket WAL corruption visibility.
8. Async DEC/WAL without terminal outcome when loop unavailable.

## Final scope note

2G adds several real issues. It should not replace the master audit; it should be merged into it as cross-model findings. Runtime root cause remains unproven until focused tests or logs confirm the paths.
