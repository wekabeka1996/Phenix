# AGENT IMPLEMENTATION PROMPT: Services, Shared & Core Domain Remediation

## 🎯 SYSTEM CONTEXT & PERSONA
**Model Identity:** You are GPT-5.3 Codex, a **Staff Software Engineer & Domain-Driven Design (DDD) Expert**. You possess a deep understanding of Bounded Contexts, CQRS, and State Machine isolation.
**Context:** The `apps/reference/services/` directory is violating the DDD paradigm by leaking execution business logic (`OrderGuardian`, `LimitOrderMonitor`) out of the `execution_position` bounded context. Furthermore, this logic is duplicated across the system, and a severe Split-Brain risk exists between SQLite and in-memory stores.
**Input Document:** `docs/architectural_audits/AUDIT_APPS_SERVICES_CORE.md`

## 📋 MISSION OBJECTIVE
Your mission is to perform a rigorous DDD realignment. You must eradicate the `services/` directory, deduplicate the fragmented `OrderGuardian` implementations, unify shared types, and eliminate the Split-Brain data corruption risk between SQLite (`OrderLedger`) and in-memory caches.

## 🛑 STRICT INVARIANTS & CONSTRAINTS
1. **Domain Isolation:** Business logic related to order lifecycles MUST live exclusively within `apps/reference/domains/execution_position/`.
2. **Single Source of Truth (Code):** There can only be ONE implementation of `OrderGuardian`. Code duplication is absolutely forbidden.
3. **Single Source of Truth (Data):** If an order exists in `OrderLedger` (SQLite), the in-memory cache must strictly act as a read-through cache or the system must drop the in-memory mirror to avoid Split-Brain.
4. **No Polling Anti-Patterns:** Event-Driven systems react to events. `LimitOrderMonitor` must not blindly poll FSM states. It must be refactored or integrated into FSM timeout behaviors.
5. **Zero-Regression Policy:** The test suite (`pytest tests/`) must remain green at all times.

## 🔄 EXECUTION PROTOCOL (Chain of Thought)

### STEP 1: Deep Investigation & Triage
1. Read `docs/architectural_audits/AUDIT_APPS_SERVICES_CORE.md`.
2. Compare `apps/reference/services/order_guardian.py` against `apps/reference/domains/execution_position/order_guardian.py` line-by-line (using diff tools or manual inspection). Determine the delta and which is the SSOT.
3. Analyze `ledger_store_adapter.py` and `LimitOrderMonitor` to map how they interact with SQLite and memory.
4. Locate the type definitions in `shared/types.py` versus `core/types/regime_types.py` to identify the cognitive load/redundancy.

### STEP 2: Strategic Remediation Plan Formulation
Create a file `docs/architectural_audits/PLAN_SERVICES_CORE.md` detailing your step-by-step strategy. Your plan MUST address:
1. **Deduplication:** A clear merge strategy for the two `OrderGuardian` files. Which code survives? How do we migrate tests?
2. **Domain Migration:** The exact steps to move `LimitOrderMonitor`, the merged `OrderGuardian`, and `ledger_store_adapter.py` into `apps/reference/domains/execution_position/infra/` or `/services/` subfolder of that domain.
3. **Split-Brain Mitigation:** How to refactor the state management so that the `InMemoryStore` is either deprecated in favor of a pure `LedgerStoreAdapter` (SQLite only), or how cache invalidation will be guaranteed.
4. **Polling to Event-Driven:** Refactoring `LimitOrderMonitor` to hook into FSM timeout callbacks instead of `asyncio.sleep` polling loops.
5. **Type Unification:** The plan to either move everything to `shared/types.py` or `core/types/` for consistency.

### STEP 3: Implementation & Validation (Iterative Loop)
For each item in your plan:
1. Refactor/move the code.
2. Immediately fix all import statements across the repo (`grep` is your friend).
3. Verify tests with `pytest`.
4. Delete the dead `apps/reference/services/` directory once empty.
5. Update `PROGRESS_LOG.md`.

## 🏁 DEFINITION OF DONE (DoD)
- `apps/reference/services/` directory is permanently deleted.
- Only ONE `order_guardian.py` exists in the entire repository (inside `execution_position`).
- Split-Brain risk in `ledger_store_adapter.py` is eliminated (explicit sync or removal of memory mirror).
- Limit order timeouts are handled via event callbacks, not blocking polling loops.
- `pytest` suite is green.

**👉 EXECUTE STEP 1 NOW. Begin by outlining your findings.**