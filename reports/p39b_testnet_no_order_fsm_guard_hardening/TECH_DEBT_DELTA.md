# Technical Debt Delta

This register tracks all elements of technical debt touched, retired, or deferred during this task.

---

## 1. Debt Categorization

| Debt Item | Status | Action Taken / Rationale |
|-----------|--------|--------------------------|
| **Weak URL-only Safety Guard** | **RETIRED** | URL matching has been demoted to a secondary safety double-check. The primary guard is now the formal FSM capability descriptor verification. |
| **Silent Failures on Unknown Env** | **CONVERTED_TO_RUNTIME_CHECK** | Unknown capability environments or missing descriptors now explicitly fail closed at handoff validation, transitioning command status to `rejected_by_fsm`. |
| **Missing Rejection Audit Trails** | **RETIRED** | Structured audit files (`audit_rejections.jsonl`) are now saved per session and globally with execution identifiers. |
| **Full Live Adapter Integration** | **DEFERRED_WITH_REASON** | Actual exchange adapter bindings and order filling states are deferred to P39C coordinator/runtime implementation to avoid premature execution side-effects. |
