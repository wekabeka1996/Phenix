# REPORT — VF-CTX-ATLAS + EP-LIFECYCLE-FORENSICS

**Audit date:** 2026-03-20  
**Auditor mode:** Forensic architecture auditor (fail-closed)  
**Scope:** vfoundation runtime substrate + execution_position lifecycle FSM system + FSMv2 migration viability  
**Evidence base:** Direct code reads of 20+ files; no runtime logs available.

---

## 1. Executive Verdict

### `GO ONLY AFTER PRE-STABILIZATION`

**Rationale:**  
[FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) is a well-designed, production-grade engine but is **not currently wired into any execution lifecycle path**. The only real FSMv2 consumer is [MetaFSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py#38-265) (cross-domain meta-coordinator, not execution-critical). The execution lifecycle ([ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827), [OpenFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#105-590), [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181)) uses a fully imperative, per-instance stateful pattern with no formal transition table. Multiple pre-stabilization blockers exist before any FSMv2 adoption is safe:

1. `CloseFlowFSM._check_close_conditions()` **always returns None** — autonomous close logic is a stub.
2. [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) has **no internal locking** — concurrency safety relies entirely on `ExecPosFSM._flows_lock` (coarse `threading.Lock`), which does not extend across async boundaries.
3. Several lifecycle-critical verbs carry `schema: null` in the registry (`CMD:CLOSE`, `DEC:CLOSE`, `DEC:ADJUST`, `DEC:BATCH`, `ORDER_PLACED`, etc.).
4. [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181) is a shallow pass-through — it transitions through CLOSE_COND → EMIT_DEC_CLOSE → DONE in a single call, without durable state.
5. Multiple deprecated verbs (`FILL`, `PARTIAL_FILL`, `EXPIRED`, `REJECTED`) remain in live [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) and [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181) dispatch paths, creating semantic drift.

No big-bang migration is recommended. A staged, shadow-first approach with pre-stabilization work is the safe path.

---

## 2. Evidence Base

### vfoundation
| File | Lines | Read |
|---|---|---|
| [vfoundation/core/fsm_v2.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py) | 423 | Full |
| [vfoundation/core/fsm_core.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py) | 179 | Full |
| [vfoundation/core/fsm_emit_compat.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py) | 121 | Full |
| [vfoundation/core/meta_fsm_v2.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py) | 265 | Full |
| [vfoundation/core/protocol.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/protocol.py) | Not read (imported) | — |

### execution_position
| File | Lines | Read |
|---|---|---|
| [fsm.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py) (ExecPosFSM) | 2083 | Lines 1–680, 800–1200 |
| [fsm_open.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py) (OpenFlowFSM) | 590 | Full |
| [fsm_manage.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py) (ManageFlowFSM) | 1827 | Lines 1–1200 |
| [fsm_close.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py) (CloseFlowFSM) | 181 | Full |
| [order_index.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/order_index.py) | 283 | Full |
| [lifecycle.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/lifecycle.py) | 209 | Full |
| [domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/domain_dict.json) | 87 | Full |

### decision_making / contracts / registries
| File | Lines | Read |
|---|---|---|
| [apps/reference/dictionaries/verb_registry_v1.yaml](file:///c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml) | 590 | Full |

### Tests
- **Not read.** Test coverage is explicitly marked UNKNOWN throughout.

### Docs / passports
- Not read directly (would require additional tool calls). Prior KI summaries referenced.

---

## 3. Verified Facts

**F1.** [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) ([vfoundation/core/fsm_v2.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py)) is a complete, thread-safe FSM engine with: per-key state store, `threading.RLock`, transition registration, guard evaluation, on_enter/on_exit callbacks, WAL writer hook, rollback on on_enter failure, [validate_reachability()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#341-371), [to_dot()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#372-388), [snapshot()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#328-332)/[restore()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#333-340).

**F2.** [FSMCore](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#18-179) ([vfoundation/core/fsm_core.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py)) is a pure pub/sub event bus with `threading.RLock`-protected listener dispatch and optional JSON schema validation via `schema_registry`.

**F3.** [MetaFSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py#38-265) ([meta_fsm_v2.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py)) is the **only current production consumer of FSMv2**. Its domain is cross-domain meta-coordination (NORMAL/LOW_RISK/COOLDOWN/DEGRADED), not execution lifecycle.

**F4.** [ExecPosFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#161-2083) is wired to [FSMCore](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#18-179) as its event bus (`self.bus = self.fsm`). It does NOT use [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) anywhere.

**F5.** [OpenFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#105-590) has exactly 3 declared states: `IDLE`, `DONE`, `ERROR`. Its handle() method processes `CMD:OPEN` imperatively — no [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) instance is used. The FSM state field (`self.state`) is mutated directly.

**F6.** [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181) declares 6 states (`FLAT`, `OPENED`, `CLOSE_COND`, `EMIT_DEC_CLOSE`, `DONE`, `ERROR`) but [_check_close_conditions()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#131-142) unconditionally returns `None` (autonomous closing is disabled/"soldier" pattern). `CMD:CLOSE` transitions through CLOSE_COND → EMIT_DEC_CLOSE → DONE in a **single synchronous call**.

**F7.** [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) declares 8 states: `FLAT`, `OPENED`, `TRACKING`, `BRACKETS_PENDING`, `BRACKETS_PLACED`, `EMIT_DEC_ADJUST`, `ERROR`, `EMERGENCY`, `WAIT_MODE`. Of these, `OPENED` appears only as a guard check target but is never transitioned into via standard event dispatch (FLAT → BRACKETS_PENDING on fill, skipping OPENED). The OPENED → TRACKING path exists in some code but is not proven reachable from the main [handle()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#185-309) dispatch in the audited range.

**F8.** [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) has **no internal locking**. Thread safety relies entirely on `ExecPosFSM._flows_lock` (`threading.Lock`), which guards flow dict access but does not span async operations.

**F9.** [OrderIndex](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/order_index.py#33-283) is the runtime SSOT for order tracking. It uses `threading.RLock`, supports CAS reservation ([try_reserve_entry](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/order_index.py#182-233)), TTL expiry, and multi-key lookup (rid/clientOrderId/exchangeOrderId).

**F10.** [domain_dict.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/domain_dict.json) explicitly states: `"order_state": "OrderIndex is runtime SSOT"`, `"position_state": "ManageFlowFSM is runtime SSOT"`.

**F11.** Verb registry contains `schema: null` for `CMD:CLOSE`, `DEC:CLOSE`, `DEC:ADJUST`, `DEC:BATCH`, `DEC:CANCEL_ORDER`, `DEC:PLACE_ORDER`, `ERR:OPEN`, `ORDER_PLACED`, `ORDER_REJECTED`, `ORDER_STATE_CHANGED`, `ORDER_TIMEOUT`, and many others.

**F12.** `EVT:FILL`, `EVT:PARTIAL_FILL`, `EVT:EXPIRED`, `EVT:REJECTED` are all marked `deprecated` in the registry. `ManageFlowFSM.handle()` still dispatches on `"PARTIAL_FILL"`, `"FILL"`, `"TRADE_EXECUTED"`. `CloseFlowFSM.handle()` dispatches on `"TRADE_EXECUTED"`, `"PARTIAL_FILL"`.

**F13.** `ExecPosFSM.__init__` enforces fail-closed on FSM bus: if [fsm](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/lifecycle.py#89-101) argument lacks [listen](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#33-45)/[emit](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#46-139) and `shadow_mode` is False, it raises `RuntimeError` (BUS-FAILCLOSED-01).

**F14.** [emit_compat](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py#48-118) ([fsm_emit_compat.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py)) is a compatibility shim that tries [emit(Message)](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#46-139) → [emit(op,verb,payload,why)](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#46-139) → [emit(op,payload,why)](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#46-139) — hides interface drift between FSMCore and other potential bus implementations.

**F15.** `ManageFlowFSM._place_brackets()` self-mutates `sl_order_id`, `tp_order_id`, `tp1_order_id`, `tp2_order_id` inside the method (before exchange confirmation), setting `state = BRACKETS_PENDING`. These field mutations happen in the same synchronous call that returns a `DEC:BATCH` message.

**F16.** `FSMv2.handle()` maintains `threading.RLock` across the full transition: state read → guard eval → on_exit → state write → on_enter → WAL write → action call.

**F17.** [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) enforces `MAX_STATES_PER_FSM = 20` and `MAX_VERBS_PER_DOMAIN = 12`. The current [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) has 9 states — within the limit.

**F18.** `fsm_emit_compat.emit_compat` is used in the watchdog polling path (fills from REST polling) to re-emit `TRADE_EXECUTED` events via [FSMCore](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#18-179).

---

## 4. Invalidated or Unproven Claims

| Claim | Status | Evidence |
|---|---|---|
| "FSMv2 is not materially production-wired" | **CONFIRMED** — only MetaFSMv2 uses it (not execution lifecycle) | F3, F4 |
| "ManageFlowFSM is the runtime SSOT for position tracking" | **CONFIRMED** by domain_dict.json | F10 |
| "OrderIndex is the runtime SSOT for order tracking" | **CONFIRMED** by domain_dict.json | F9, F10 |
| "Current lifecycle has scattered imperative state mutation" | **CONFIRMED** — all 3 sub-FSMs use direct `self.state = ...` | F5, F6, F7 |
| "Some states may be dead, phantom, or weakly enforced" | **CONFIRMED** — `OPENED` in ManageFlowFSM appears unreachable from main dispatch | F7 |
| "Transition legality not centrally validated" | **CONFIRMED** — no transition table exists; dispatch is pure imperative if/elif | F5, F6, F7 |
| "Thread/concurrency safety may be insufficient" | **CONFIRMED** — ManageFlowFSM has no lock; async operations cross lock boundary | F8 |
| "Shadow migration path may be safer than direct replacement" | **INFERENCE** (not proven) — supported by FSMv2 design but no shadow harness exists yet | UNKNOWN |
| "CloseFlowFSM handles autonomous closes" | **FALSIFIED** — _check_close_conditions always returns None | F6 |
| "ManageFlowFSM OPENED state is reachable from main event flow" | **UNPROVEN** — cannot confirm from audited code range; hydrate() sets OPENED but hydrate() call-site not verified | UNKNOWN |

---

## 5. vfoundation Atlas

### Module Responsibility Table

| Module | Owner | Runtime Role | Status |
|---|---|---|---|
| [fsm_core.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py) / [FSMCore](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#18-179) | vfoundation | Pub/sub event bus. [listen()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#33-45) + [emit()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py#46-139). Schema validation hook. Domain registry. | **Active** — wired to all domains |
| [fsm_v2.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py) / [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) | vfoundation | Stateful FSM engine. Per-key state store, transitions, guards, on_enter/on_exit, WAL, RLock, rollback. | **Partial** — only MetaFSMv2 uses it |
| [meta_fsm_v2.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py) / [MetaFSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py#38-265) | vfoundation | Cross-domain meta-coordinator (entropy/degraded/low_risk states). Uses FSMv2. | **Active** (meta-only) |
| [fsm_emit_compat.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py) / [emit_compat](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py#48-118) | vfoundation | Compatibility shim for heterogeneous emit() interfaces. Async-aware. | **Active** — used by watchdog |
| [schema_registry.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/schema_registry.py) | vfoundation | JSON schema validation registry. Plugged into FSMCore.emit(). | **Active** (partial — many schema: null) |
| [protocol.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/protocol.py) / [Message](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py#8-22) | vfoundation | Canonical message envelope (op/verb/src/dst/rid/pld/why/data_ref). | **Active** |
| `obs/correlation.py` / `CorrelationStore` | vfoundation | WHY-chain correlation. Used by ExecPosFSM. | **Active** |
| `obs/domain_bridge.py` / `DomainBridge` | vfoundation | Health registration for orphaned domains. | **Active** |
| `dr/wal.py` | vfoundation | WAL writer (imported, pluggable into FSMv2 wal_writer). Not verified if used in EP. | **Unknown** |
| [core/lifecycle.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/lifecycle.py) | vfoundation | Stub/thin lifecycle utilities. | **Unknown** |
| [core/retry_scheduler.py](file:///c:/Users/user/Music/Phenix/vfoundation/core/retry_scheduler.py) | vfoundation | Async retry scheduling. | **Unknown** |

### Key Gaps in vfoundation
- `FSMv2.handle()` is **synchronous**; no async variant exists. Execution lifecycle is heavily async.
- [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) operates on string-keyed state store; the EP domain uses per-symbol instances, not per-key state within one FSM instance.
- The WAL writer interface (`wal_writer: Optional[Callable[[Dict], Any]]`) is optional and passable at construction — not integrated with `vfoundation.dr.wal` automatically.

---

## 6. Execution Lifecycle Atlas

### Open Flow
1. `EVT:TRADE_INTENT_PROPOSED` → `ExecPosFSM._on_trade_intent_proposed` → `IntentRouter.on_trade_intent_proposed`
2. Intent Router checks ExposureGuard, OrderIndex (CAS reserve), supersede logic
3. If cleared: → `OpenFlowFSM.handle_async(CMD:OPEN)` (leverage check if live) → `OpenFlowFSM.handle()`
4. Guards: panic killswitch, idempotency, CmdOpenPayload Pydantic validation, min_qty, min_notional, cooldown
5. Output: `DEC:OPEN` → adapter → exchange order placement
6. Exchange ack → `EVT:ORDER_ACK` → ExecPosFSM._on_order_ack → watchdog registration
7. Exchange fill → `EVT:ORDER_FILL` → ExecPosFSM._on_order_fill → ManageFlowFSM.handle(TRADE_EXECUTED)
8. ManageFlowFSM FLAT → BRACKETS_PENDING → [_place_brackets()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#832-1074) → `DEC:BATCH` (SL + TP1 + TP2)

### Manage Flow
9. `EVT:ORDER_UPDATED` on bracket → `ManageFlowFSM._on_bracket_placed` → BRACKETS_PLACED
10. TRACKING/BRACKETS_PLACED: [_check_rules()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#1312-1401) on tick → trailing stop, max_hold_sec, partial exit
11. Max hold exceeded → `DEC:CLOSE` emitted from ManageFlowFSM

### Close Flow
12. `CMD:CLOSE` from decision_making → `ExecPosFSM._on_trade_intent_proposed` → eventually `CloseFlowFSM.handle(CMD:CLOSE)`
13. CloseFlowFSM emits `DEC:CLOSE` (reduce_only=True) passthrough
14. `DEC:CLOSE` → adapter → market close order placed
15. Fill on close → `EVT:TRADE_EXECUTED` → position_tracking updates
16. `EVT:PORTFOLIO_STATE_UPDATED` → ExecPosFSM._on_portfolio_state_updated → lifecycle flush

### Reject / Timeout / Fallback
- Order timeout → `OrderTimeoutWatchdog` fires → REST polling → [emit_compat(TRADE_EXECUTED)](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py#48-118) or timeout event
- Orphan cleanup → `OrderGuardian.cleanup_orphans()` (periodic)
- Bracket health check → [_bracket_health_loop()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#1081-1104) (periodic)
- Pending entry TTL → `EntryManager` cancels stale limit entries

### Side-Effect Points (Risk-critical)
| Point | Location | Side effect |
|---|---|---|
| ManageFlowFSM._place_brackets() | fsm_manage.py ~L832 | Mutates sl_order_id, tp_order_id fields before exchange confirms |
| CloseFlowFSM._emit_close() | fsm_close.py L145-170 | Transitions CLOSE_COND→EMIT_DEC_CLOSE→DONE in single call, then sets position_active=False |
| ExecPosFSM._pending_brackets | fsm.py L296 | WAL-persisted pending brackets (restored on startup except backtest) |
| ExecPosFSM._symbol_brackets | fsm.py L276 | In-memory SL/TP order IDs per symbol for atomic cleanup |

---

## 7. State Machine Forensics

### Per-FSM State Table

| FSM | Declared States | Likely Reachable | Dead/Phantom States | Notes |
|---|---|---|---|---|
| [OpenFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#105-590) | IDLE, DONE, ERROR | IDLE→DONE (success), IDLE→ERROR (guard fail) | None confirmed dead. IDLE is also the reset state — not cleared between calls. | Single global state per instance (not per-symbol). state=IDLE is perpetually reused. |
| [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181) | FLAT, OPENED, CLOSE_COND, EMIT_DEC_CLOSE, DONE, ERROR | FLAT→OPENED (fill), FLAT→CLOSE_COND→EMIT_DEC_CLOSE→DONE (CMD:CLOSE) | OPENED is reachable but immediately followed by [_check_close_conditions() → None](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#131-142) so is transient. CLOSE_COND is phantom (transitions in and immediately out in same call). | Autonomous close stub: _check_close_conditions() always returns None. No rules execute. |
| [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) | FLAT, OPENED, TRACKING, BRACKETS_PENDING, BRACKETS_PLACED, EMIT_DEC_ADJUST, ERROR, EMERGENCY, WAIT_MODE | FLAT→BRACKETS_PENDING→TRACKING (entry skip brackets), FLAT→BRACKETS_PENDING (entry+brackets), BRACKETS_PENDING→BRACKETS_PLACED (ORDER_UPDATED), TRACKING/BRACKETS_PLACED→EMIT_DEC_ADJUST | OPENED: **appears phantom in main flow** (set in hydrate() but the hydrate() call-site was not audited; not set by standard event dispatch). EMIT_DEC_ADJUST: set inside _check_rules() — not confirmed terminal. EMERGENCY: reachable from error paths (not confirmed). | WAIT_MODE exits via TTL on any tick event; no explicit re-entry gate. |
| [ExecPosFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py#161-2083) | No states (coordinator, not FSM) | n/a | n/a | Delegates to 3 sub-FSMs per-symbol. _flows_lock guards dict access. |

### OpenFlowFSM: Forbidden/Weak Transitions
- State never truly reset between positions; [reset()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#517-521) is only called from tests.
- `self.state = OpenState.ERROR` on guard fail means next CMD:OPEN from IDLE (which it still is!) can succeed — ERROR has no blocking effect on subsequent calls.
- **FINDING**: `OpenState.ERROR` sets `self.state = ERROR` but the next [handle()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#185-309) call checks `if msg.op == "CMD" and msg.verb == "OPEN":` — which always runs regardless of state. **State field is decorative; OpenFlowFSM is effectively stateless** between calls except for idempotency store and cooldown timestamp.

### CloseFlowFSM: Forbidden/Weak Transitions
- CLOSE_COND and EMIT_DEC_CLOSE are phantom intermediate states — created and destroyed within a single [_emit_close()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#143-171) call (L145→L168).
- [reset()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#517-521) sets state=FLAT but does NOT clear position tracking across close events (only called from tests).
- No guard prevents double-close: if CMD:CLOSE arrives twice rapidly, two DEC:CLOSE messages are emitted. Idempotency relies on exchange-level dedup only.

### ManageFlowFSM: Notable Transition Risks
- FLAT→BRACKETS_PENDING: guarded only by [_is_exit_fill_payload()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#457-469) — false negatives on unusual pay load shapes could open false brackets.
- BRACKETS_PENDING: if [_place_brackets()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#832-1074) raises and returns None, state is set to TRACKING but bracket IDs remain None. The position is now without SL/TP and in TRACKING state permanently.
- TRACKING/BRACKETS_PLACED→FLAT: occurs via [_clear_lifecycle_tracking()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#422-453) on exit fill. If an exit fill arrives while state is BRACKETS_PENDING (race), guard blocks it (no handler), creating a stuck lifecycle.

---

## 8. Contract Surface Audit

### Critical Verb Table

| Verb | Owner | Schema | Emitter(s) | Consumer(s) | Lifecycle-Critical | Migration Risk |
|---|---|---|---|---|---|---|
| `CMD:OPEN` | execution_position | ✅ cmd_open_v1.json | ExecPosFSM (self-emit) | OpenFlowFSM | YES | Low (schema exists, Pydantic validated) |
| `DEC:OPEN` | execution_position | ✅ dec_open_v1.json | OpenFlowFSM | Adapter | YES | Low |
| `CMD:CLOSE` | execution_position | ❌ null | decision_making | CloseFlowFSM | YES | **HIGH** — no schema, co-consumed by EP |
| `DEC:CLOSE` | execution_position | ❌ null | CloseFlowFSM | Adapter | YES | **HIGH** — no schema |
| `DEC:BATCH` | execution_position | ❌ null | ManageFlowFSM | Adapter | YES | **HIGH** — brackets placed via this |
| `DEC:ADJUST` | execution_position | ❌ null | ManageFlowFSM | Adapter | YES | **HIGH** |
| `EVT:TRADE_EXECUTED` | position_tracking | ✅ trade_executed_v1.json | adapter (WS), EP watchdog (REST fallback) | position_tracking, ManageFlowFSM, CloseFlowFSM | YES | HIGH — co-emission complexity |
| `EVT:TRADE_INTENT_PROPOSED` | decision_making | ✅ trade_intent_v1.json | decision_making | ExecPosFSM | YES | Medium |
| `EVT:ORDER_ACK` | execution_position | Partial (schemas/order_ack_v1.json) | adapter | ExecPosFSM | YES | Medium |
| `EVT:ORDER_FILL` | execution_position | Partial (order_fill_v1.json) | adapter | ExecPosFSM | YES | Medium |
| `EVT:PORTFOLIO_STATE_UPDATED` | position_tracking | ✅ | position_tracking | ExecPosFSM | YES | Medium |
| `EVT:PARTIAL_FILL` | **deprecated** | ❌ null | (deprecated) | ManageFlowFSM, CloseFlowFSM still dispatch on it | **YES** (live path) | **CRITICAL** — deprecated but active |
| `EVT:FILL` | **deprecated** | ❌ null | (deprecated) | ManageFlowFSM still dispatches on it | YES | **CRITICAL** |
| `EVT:EXPOSURE_SUMMARY_UPDATED` | execution_position | ✅ | EP only | risk_management, decision_making | YES | Low |
| `DEC:CANCEL_ORDER` | execution_position | ❌ null | ExecPosFSM | Adapter | YES | HIGH |
| `EVT:SYMBOL_TIDY` | execution_position | ✅ | OrderGuardian | ExecPosFSM | Medium | Low |

### Co-Emission Policy (per domain_dict.json)
- `EVT:TRADE_INTENT_REJECTED`: EP co-emits when intent fails at execution boundary (intent_router.py).
- `EVT:TRADE_EXECUTED`: EP watchdog co-emits as REST polling fallback.
- `EVT:EXPOSURE_SUMMARY_UPDATED`: EP is sole emitter.

### Schema Gaps (Migration-blocking)
The following lifecycle-critical verbs have **no JSON schema**:
- `CMD:CLOSE`, `DEC:CLOSE`, `DEC:ADJUST`, `DEC:BATCH`, `DEC:CANCEL_ORDER`, `DEC:PLACE_ORDER`, `ORDER_PLACED`, `ORDER_REJECTED`, `ORDER_STATE_CHANGED`, `ORDER_TIMEOUT`

Any FSMv2 transition that emits these will be **unvalidated** — no schema enforcement is possible until schemas are added.

---

## 9. Risk Register

### CRITICAL

**R1 — Deprecated verbs active on live dispatch paths**
- **Symptom:** ManageFlowFSM and CloseFlowFSM dispatch on `PARTIAL_FILL`, `FILL`, `TRADE_EXECUTED` (mixed new+deprecated).
- **Root cause:** Registry deprecated `FILL`/`PARTIAL_FILL` (2026-03-14) but no migration of consumers was completed.
- **Effect:** If adapters stop emitting deprecated verbs, ManageFlowFSM may miss fill events, creating stuck open positions with no SL/TP.
- **Confidence:** HIGH (code confirmed)

**R2 — CloseFlowFSM._check_close_conditions() is a stub**
- **Symptom:** Autonomous close (max_hold from CloseFlow) never fires.
- **Root cause:** Method unconditionally returns None. Deliberate "soldier" pattern but not documented as a safety gap.
- **Effect:** Time-based position exits in CloseFlow are silently disabled. Only ManageFlowFSM's [_check_max_hold_time()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#322-365) provides time-based closing.
- **Confidence:** HIGH (code confirmed)

**R3 — ManageFlowFSM has no internal locking; bracket mutations cross async boundary**
- **Symptom:** [_place_brackets()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#832-1074) mutates `sl_order_id`, `tp_order_id` before exchange confirmation, in sync context.
- **Root cause:** No `threading.Lock` or async lock in ManageFlowFSM.
- **Effect:** If two EVT:TRADE_EXECUTED events arrive concurrently (WS + REST polling), bracket IDs can be double-written or bracket placement can be duplicated.
- **Confidence:** MEDIUM (no runtime proof of race; code structure creates plausible window)

### HIGH

**R4 — Double-close race on CMD:CLOSE**
- **Symptom:** Two CMD:CLOSE messages (e.g., strategy + regime flip) both pass through CloseFlowFSM with no guard, emitting two DEC:CLOSE messages.
- **Root cause:** CloseFlowFSM.handle(CMD:CLOSE) has no state-based guard — it emits DEC:CLOSE regardless of current state.
- **Effect:** Two reduce_only close orders placed. Exchange dedup (net position semantics) limits blast radius, but second order may fail noisily or trade unexpected slippage.
- **Confidence:** HIGH (code confirmed; no guard present in audited code)

**R5 — OpenFlowFSM.state is decorative**
- **Symptom:** `OpenState.ERROR` set on guard failure but no downstream guard checks state before next [handle()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#185-309) call.
- **Root cause:** Imperative dispatch ignores state field after returning ERR.
- **Effect:** State field provides no safety value; it is misleading instrumentation.
- **Confidence:** HIGH (code confirmed)

**R6 — ManageFlowFSM stuck lifecycle when exit fill arrives during BRACKETS_PENDING**
- **Symptom:** Exit fill during bracket placement phase has no handler in BRACKETS_PENDING state.
- **Root cause:** [handle()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#185-309) dispatches FILL/TRADE_EXECUTED in BRACKETS_PENDING only via the FLAT guard branch (L697–L747) — if state is already BRACKETS_PENDING, the fill hits the guard at L749–L779, which blocks unknown fills but may let exit fills fall through without clearing lifecycle.
- **Effect:** ManageFlowFSM stuck in BRACKETS_PENDING with a closed position, exposing wrong lifecycle state to downstream.
- **Confidence:** MEDIUM (requires deeper trace into L749 guard logic not fully read)

**R7 — Schema-null critical verbs prevent schema validation in FSMCore.emit()**
- **Symptom:** `CMD:CLOSE`, `DEC:CLOSE`, `DEC:BATCH`, `DEC:ADJUST` emitted with no schema validation.
- **Root cause:** verb_registry entries carry `schema: null`.
- **Effect:** Malformed payloads pass unchecked through bus. Silent corruption risk on close/bracket paths.
- **Confidence:** HIGH (registry confirmed)

### MEDIUM

**R8 — emit_compat() masks interface drift**
- [emit_compat](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_emit_compat.py#48-118) silently falls back through 3 emit signatures. A regression in FSMCore interface would not be immediately visible.
- **Confidence:** MEDIUM

**R9 — WAL-restored _pending_brackets on startup can rehydrate stale bracket intent**
- Bracketed positions restored from WAL on startup may be stale if exchange already placed/cancelled brackets. No reconciliation step validates WAL state against exchange state before using it.
- **Confidence:** MEDIUM (code confirmed; reconciliation is best-effort only)

**R10 — OrderFlowFSM.state resets to IDLE via reset() only in tests**
- Production open flow has no clean state reset per trade; idempotency store has TTL cleanup but state itself persists. Edge case: ERROR state on one trade does not prevent the next.
- **Confidence:** MEDIUM

### LOW

**R11 — WAIT_MODE exit is time-based, not event-based**
- ManageFlowFSM WAIT_MODE exits when `now_ts >= _wait_mode_until_ts` on any tick — implies if no tick arrives, WAIT_MODE sticks indefinitely.
- **Confidence:** LOW (tick normally available in production)

---

## 10. FSMv2 Fit Assessment

### What FSMv2 Can Already Support (today)

| Capability | FSMv2 Status |
|---|---|
| Formal transition table | ✅ Complete |
| Guard functions per transition | ✅ Complete |
| on_enter / on_exit callbacks | ✅ Complete |
| Per-key state store (symbol-based) | ✅ Complete — use symbol as key |
| Thread-safe state access | ✅ `threading.RLock` in handle() |
| Fail-closed on illegal transition | ✅ Returns `ERR:NO_TRANSITION` |
| WAL recording of transitions | ✅ Optional pluggable writer |
| Rollback on on_enter failure | ✅ State reverted |
| State reachability validation | ✅ [validate_reachability()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#341-371) |
| Observability / metrics | ✅ [_FSMv2Metrics](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#416-423) (transitions/rejected/errors/rollbacks) |
| DOT export | ✅ [to_dot()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#372-388) |
| Snapshot / restore (DR) | ✅ [snapshot()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#328-332) / [restore()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#333-340) |

### What FSMv2 Cannot Do Today / Needs Adapters

| Gap | Severity | Required Adapter |
|---|---|---|
| **Async actions** — [handle()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#185-309) is synchronous; all EP async calls (adapter, guardian) cannot be actions | **BLOCKER** for production cutover | Async wrapper FSM or action dispatch via coroutine queue |
| **Side-effect ordering** — EP transitions must place exchange orders after state commit; FSMv2 actions fire inside the lock | **BLOCKER** | Separate action executor outside the lock boundary |
| **Multi-FSM coordinator** — ExecPosFSM coordinates 3 sub-FSMs per symbol; FSMv2 is one FSM per entity | **Design gap** | Coordinator layer wrapping 3 FSMv2 instances per symbol |
| **State hydration from WAL/REST** — current ManageFlowFSM hydrates from position snapshots | **Required before cutover** | Hydration adapter calling `FSMv2.set_state()` |
| **Emit co-ordination** — on-transition event emission to FSMCore bus must be coordinated | Design work | on_enter/on_exit callbacks can emit to bus |
| **Max 12 verbs per domain** (constitution limit) | Potential constraint — EP has more than 12 events that affect lifecycle | Likely requires event normalization pass |

### FSMv2 Is NOT Viable For Direct Cutover Today Because:
1. All execution adapter calls are async; FSMv2.handle() is synchronous.
2. No shadow harness exists to run FSMv2 in parallel with the current imperative FSMs.
3. ManageFlowFSM OPENED state reachability is unproven — migrating before state graph is fully mapped risks data loss.
4. Critical verb schemas are missing — FSMv2 transitions that emit DEC:CLOSE, DEC:BATCH, etc. would be unvalidated.
5. No test baseline for FSMv2 ManageFlow semantics.

### FSMv2 Is Viable For Shadow Adoption Because:
- Per-key state store maps naturally to per-symbol scoping.
- RLock exists and is compatible with current threading model.
- WAL writer interface can be wired to existing `vfoundation.dr.wal`.
- [to_dot()](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#372-388) enables graph-based visual validation before cutover.

---

## 11. Migration Strategy

### Migration Package Table

| Package | Objective | Scope | Prerequisites | Validation | Rollback Need |
|---|---|---|---|---|---|
| **PKG-0: Pre-stabilization** | Fix known correctness bugs before migration. | CloseFlowFSM double-close guard; OpenFlowFSM state enforcement; ManageFlowFSM stuck-lifecycle on exit fill in BRACKETS_PENDING | None | Unit tests for each bug; regression suite | N/A (code fixes) |
| **PKG-1: Schema stabilization** | Add JSON schemas for all lifecycle-critical null-schema verbs | `CMD:CLOSE`, `DEC:CLOSE`, `DEC:BATCH`, `DEC:ADJUST`, `DEC:CANCEL_ORDER` schemas | PKG-0 complete | Schema validation passes on all emitted payloads; no regression in live tests | Revert schema files |
| **PKG-2: Verb normalization** | Remove deprecated verb paths from ManageFlowFSM, CloseFlowFSM | Remove `FILL`, `PARTIAL_FILL` dispatch (keep `TRADE_EXECUTED` only); update any producer that still emits deprecated verbs | PKG-1; verify all adapters emit `TRADE_EXECUTED` | Log-based verification: no FILL/PARTIAL_FILL events reach FSM consumers in staging | Feature flag: re-enable deprecated paths |
| **PKG-3: FSMv2 shadow harness** | Run FSMv2 instance(s) in parallel with existing ManageFlowFSM, compare state transitions | ManageFlowFSM only (highest-value, highest-risk) | PKG-0, PKG-1, PKG-2; async FSMv2 wrapper | Shadow diff log: FSMv2 state agrees with ManageFlowFSM on all fill/bracket/exit events | Disable shadow harness (no production impact) |
| **PKG-4: Async FSMv2 adapter** | Wrap FSMv2.handle() to support async action dispatch (coroutine queue or post-transition emitter) | vfoundation/core only (additive) | PKG-3 running cleanly | Unit tests: async actions fire after state commit; no deadlock under concurrency | Remove adapter (FSMv2 still usable sync) |
| **PKG-5: ManageFlowFSM cutover (narrow)** | Replace ManageFlowFSM imperative dispatch with FSMv2-backed state for one symbol in staging | Single symbol (BTCUSDT or lowest-risk) | PKG-4; hydration adapter; shadow diff clean ≥48h | Full fill/bracket/exit cycle on staging; compare OrderIndex and ManageFlowFSM state vs FSMv2 state | Per-symbol feature flag: revert to ManageFlowFSM |
| **PKG-6: Full ManageFlow cutover** | Extend FSMv2 ManageFlow to all symbols | All configured symbols | PKG-5 stable ≥72h on staging | Bracket health check passes; no orphaned SL/TP orders; no stuck BRACKETS_PENDING states | Per-symbol rollback flag (rehydrate ManageFlowFSM from FSMv2 snapshot) |
| **PKG-7: CloseFlow cutover** | Replace CloseFlowFSM (simpler, currently stub-level) | All symbols | PKG-6 stable; double-close guard in place | CMD:CLOSE to DEC:CLOSE chain verified in staging; no duplicate close orders | Revert to CloseFlowFSM |
| **PKG-8: OpenFlow cutover** | Replace OpenFlowFSM state tracking with FSMv2 | All symbols | PKG-7 stable | CMD:OPEN pass-through + guard chain verified; no false rejects | Revert to OpenFlowFSM |
| **PKG-9: Legacy removal** | Remove old imperative FSM code, reset() methods, decorative state fields | OpenFlowFSM, CloseFlowFSM, ManageFlowFSM legacy | All above stable ≥7 days production | No test failures; clean state graph via validate_reachability() | N/A |

### Migration Order Rationale
- **ManageFlowFSM first** (not CloseFlowFSM or OpenFlowFSM): ManageFlowFSM has the most complex stateful behavior, the most real states, and the highest correctness value from a formal FSM. However, it also has the highest risk surface. Shadow first; cutover last.
- **CloseFlowFSM second**: It is currently a shallow pass-through (stub autonomous close). The FSMv2 version will immediately provide better state visibility. Low blast radius.
- **OpenFlowFSM last**: Currently the most stateless (state field is decorative). FSMv2 provides the least marginal value here; replace last.

---

## 12. Validation Plan

### Before Any Cutover (Required Evidence)
1. **State graph completeness**: `FSMv2.validate_reachability()` must return `valid=True` for all state machines.
2. **Shadow diff log**: ≥48 hours of shadow mode showing FSMv2 state matches incumbent FSM state on every fill, bracket, and close event.
3. **Schema validation pass**: No payload validation errors in staging on `CMD:CLOSE`, `DEC:CLOSE`, `DEC:BATCH`, `DEC:ADJUST`.
4. **Double-close guard test**: Explicit test that two rapid CMD:CLOSE messages produce exactly one DEC:CLOSE (after PKG-0 fix).
5. **Bracket integrity test**: Fill event → brackets placed → exit fill → ManageFlowFSM state = FLAT → no orphaned SL/TP on exchange.
6. **Locking stress test**: Concurrent EVT:ORDER_FILL + REST polling fill arriving simultaneously → no bracket duplication.
7. **WAL rehydration test**: Simulate restart with pending_brackets WAL → brackets reconciled vs exchange open orders → no double-placement.

### Mandatory Replay Validation
- Replay production fill sequence from logs against FSMv2 shadow and verify state sequence matches expected (FLAT → BRACKETS_PENDING → TRACKING → FLAT).

### Rollback Triggers
- Any FSMv2 `ERR:NO_TRANSITION` in production on a lifecycle-critical path.
- Any ManageFlowFSM state disagreement between FSMv2 shadow and incumbent after PKG-3.
- Any missed SL/TP bracket placement detected by bracket health check in production.
- **Capital risk threshold**: If a position remains open without SL/TP for > [max_hold_sec](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#304-321), abort migration and investigate.

---

## 13. Done / Not Done

### What This Package Proved
- [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414) is code-complete, thread-safe, and feature-rich, but not wired to the execution lifecycle.
- [MetaFSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/meta_fsm_v2.py#38-265) is the only production consumer of [FSMv2](file:///c:/Users/user/Music/Phenix/vfoundation/core/fsm_v2.py#60-414); it operates at meta-level, not trading execution.
- All 3 sub-FSMs ([OpenFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#105-590), [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827), [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181)) are imperative, non-table-driven, and have clear correctness gaps.
- [CloseFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_close.py#34-181) autonomous close is a confirmed stub (always returns None).
- `OpenFlowFSM.state` is decorative and provides no enforcement.
- [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) has correct position tracking semantics but no internal locking.
- `ManageFlowFSM.OPENED` state reachability from the main event path is **unproven** by this audit.
- Multiple schema-null lifecycle-critical verbs represent a contract safety gap independent of any migration.
- Deprecated verbs (`FILL`, `PARTIAL_FILL`) are still active in live dispatch despite registry marking them deprecated.
- The migration order should start with pre-stabilization, then shadow, then ManageFlowFSM cutover first (not CloseFlowFSM first).

### What Remains Open / Not Proven
- `ManageFlowFSM.OPENED` state reachability: [hydrate()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#1782-1822) call-sites not audited.
- `ManageFlowFSM._check_rules()` full logic (lines 1200–1827 not read): trailing stop, max_hold, partial exit — assumed present from init code but not verified.
- `IntentRouter.on_trade_intent_proposed()` full flow not traced — it delegates, chain not fully read.
- Test coverage of any FSM state: not inspected.
- Actual runtime behavior on concurrent WS + REST polling fills: no runtime logs available.
- [vfoundation/dr/wal.py](file:///c:/Users/user/Music/Phenix/vfoundation/dr/wal.py) actual API: not read; integration with FSMv2 wal_writer is possible but unconfirmed.
- Whether `EVT:ORDER_FILL` vs `EVT:TRADE_EXECUTED` semantics are fully normalized in all adapter paths (partial fill handling).
- Decision_making domain_dict and its full import/export surface: not inspected in detail.

---

## Appendix: Concurrency Hazard Table

| Surface | Race Scenario | Current Protection | Missing Protection | Severity |
|---|---|---|---|---|
| [ManageFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_manage.py#55-1827) state mutation | Concurrent TRADE_EXECUTED (WS) + REST polling fill → double bracket placement | `ExecPosFSM._flows_lock` (coarse Lock on dict access) | No lock inside ManageFlowFSM methods; async boundaries uncovered | HIGH |
| `CloseFlowFSM.handle()` double-close | Two CMD:CLOSE arrive simultaneously | None | State-based guard (check `self.state != DONE` before emitting) | HIGH |
| [OpenFlowFSM](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#105-590) idempotency store | Concurrent CMD:OPEN with same idempotent_key | `self.idempotency_store` dict (no lock) | Lock around [_cleanup_idempotency_store](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#224-238) + store update | MEDIUM |
| `ExecPosFSM._pending_brackets` WAL rehydration | Startup restore races with early TRADE_EXECUTED events | Backtest check skips WAL | No startup gate for live mode | MEDIUM |
| [OrderIndex](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/order_index.py#33-283) concurrent entry reserve | Two trade intents for same symbol pass [has_in_flight_entry](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/order_index.py#156-181) simultaneously | `threading.RLock` + CAS [try_reserve_entry](file:///c:/Users/user/Music/Phenix/apps/reference/domains/execution_position/order_index.py#182-233) | ✅ Properly protected | N/A (mitigated) |

