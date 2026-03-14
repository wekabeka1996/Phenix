# Decision Making Domain Refactoring Plan (v2: Safe Execution Edition)

## 1. Executive Summary
The `apps/reference/domains/decision_making` directory is currently a "God Domain" containing almost 40 Python files. This structure makes the codebase difficult to navigate, increases cognitive load, and obfuscates distinct responsibilities (scoring, safety validation, execution planning, telemetry, context etc.).

This document outlines an **architecturally strict but operationally staged** plan to refactor the domain. Breaking up 40+ files and 176+ external imports in a single atomic "big bang" PR is far too risky to review and debug. Instead, this v2 plan focuses on a behavior-preserving, staged file movement strategy, stabilizing internal hierarchies before rolling out external renames. We also establish explicit public facades to minimize unnecessary global churn.

## 2. Target Architecture (Taxonomy)

The domain will be split into the following sub-packages, with strict dependency rules:

```text
apps/reference/domains/decision_making/
├── decision_making.py         # (PUBLIC FACADE) Re-exports from routing/
├── strategy_gateway.py        # (PUBLIC FACADE) Re-exports from routing/
│
├── schemas/            # (BOTTOM TIER) Pure data models, types, and context.
│   ├── schemas.py                 
│   ├── schemas_decision_blocked.py
│   ├── domain_dict.json           
│   ├── decision_context.py        # Moved here to prevent circular imports
│   ├── operational_mode.py        
│   └── position_queries.py        
│
├── telemetry/          # Logging adapters, WAL, and metrics
│   ├── why_codes.py
│   ├── normalized_reject_reasons.py
│   ├── trade_intent_reject_wal.py
│   ├── dm_log_adapter.py
│   ├── mean_reversion_logger.py
│   └── dashboard.py
│
├── scoring/            # Math, score normalization, and regime handling
│   ├── quadratic_scoring_kernel.py
│   ├── aurora_scoring_helpers.py
│   └── regime_smoother.py
│
├── shields/            # Validation, limits, and anti-pyramiding
│   ├── base.py
│   ├── context_shield.py
│   ├── danger_zone.py
│   ├── memory_shield.py
│   ├── null_shield.py
│   ├── readiness_gates.py
│   ├── safety_gates.py
│   ├── execution_gate.py
│   ├── inception_filter.py
│   ├── flip_orchestration.py
│   └── qos_rate_control.py
│
├── execution_planning/ # Sizing, quantization, and intent generation
│   ├── sizing_margin_first.py
│   ├── instrument_quantizer.py
│   ├── entry_plan.py
│   ├── exit_manager.py
│   ├── intent_builder.py
│   └── intent_emitter.py
│
├── strategies/         # Concrete strategy logic and handlers
│   ├── aurora/
│   │   ├── aurora_handler.py
│   │   ├── aurora_decision.py
│   │   ├── aurora_config_loader.py
│   │   ├── aurora_holding_period.py
│   │   └── aurora_tpsl.py
│   ├── mean_reversion/
│   │   └── mean_reversion_handler.py
│   └── md_amr/
│   │   └── md_amr_handler.py
│
└── routing/            # Domain initialization & state management
    ├── _decision_making_impl.py
    ├── _strategy_gateway_impl.py 
    ├── event_handlers.py
    ├── config_resolver.py
    └── deferred_scheduler.py
```

### 2.1 Critical Architectural Principles
1. **No Wildcard Proxies (`import *`)**: We will **never** use `from .subdir import *` proxy files. They ruin static typing, IDE completion, and obscure naming collisions. 
2. **Explicit Public Facades**: To maintain stability, entry points like `decision_making.py` and potentially `strategy_gateway.py` will remain at the root level, exposing specific, explicitly typed functions/classes from their implementation files in `routing/`.
3. **Internal vs. External Stability**: We will fix internal structuring first, ensuring tests pass at each stage, before updating the 176+ external callers in one massive rename sweep.

## 3. Implementation Plan (Staged Execution)

This migration must be executed step-by-step. Each stage must pass Pytest and Pyre/MyPy before moving to the next.

### Stage 0: Dependency Census & Audit
*Before moving any files*, we must capture the current state:
- Build a real import graph to identify latent circular dependencies.
- Identify "gravity wells" (files that everyone imports from).
- Map all external consumers out of `apps/reference/domains/decision_making/...`.
- Define what constitutes the *Public API* vs *Internal API*.

### Stage 1: Foundations First
Move the bedrock components that have no internal `decision_making` dependencies:
- Move `schemas.py`, `decision_context.py`, `operational_mode.py`, and `position_queries.py` into `schemas/`.
- Run Pytest and Pyre. Fix any newly introduced relative/absolute import paths across the remaining 35+ files.

### Stage 2: Low-Risk Packages
Move domains that primarily depend on schemas and third-party libs (but not other siblings):
- Move `telemetry/` files.
- Move `scoring/` files.
- Run Pytest and Pyre. Update imports internally.

### Stage 3: High-Risk Packages
Move highly intertwined logic files:
- Move `shields/`. (Danger: strong coupling to schemas and potentially execution_planning).
- Move `execution_planning/`.
- Resolve any internal boundary friction. Run Pytest and Pyre.

### Stage 4: Strategies & Routing
- Move `aurora_*`, `mean_reversion_*`, `md_amr_*` into `strategies/`.
- Move `event_handlers.py`, `config_resolver.py`, `deferred_scheduler.py` into `routing/`.
- Create the implementation files `routing/_decision_making_impl.py` and `routing/_strategy_gateway_impl.py`.
- Leave explicit facade files `decision_making.py` and `strategy_gateway.py` at the root.

### Stage 5: External Consumer Sweep (The Big Rename)
Once the internal packages are stable and the root folder is clean (except for facades):
- Execute a global search and replace across `apps/`, `tests/`, and `tools/` to update callers from the old absolute paths to the newly scoped package paths (e.g. `apps...decision_making.shields.safety_gates`).
- Verify the build.

## 4. Policy: Public Import Surfaces vs. Internal Paths

To prevent the domain from degrading into a tangled mess again, we mandate strict import surfaces:

| Audience | Allowed Imports | Forbidden Imports |
|----------|-----------------|-------------------|
| **External Domains** (e.g. Alpha Search, CMD) | Root Facades (`decision_making.py`), explicitly public telemetry interfaces or simple schemas. | *Forbidden* from deep-importing internal strategies (e.g. `strategies/aurora/aurora_handler.py`), shields, or execution planners. |
| **Sibling Sub-packages** (e.g. `strategies/` to `shields/`) | Allowed to import across specified package boundaries (see Dependency Graph below). | *Forbidden* from bypassing the DAG (e.g., `schemas/` cannot import `routing/`). |

## 5. Target Dependency Graph Invariants

While we acknowledge real-world nuances (e.g., `strategies/` genuinely wanting a `telemetry/` helper), the core one-way DAG imperative is:

1. **`schemas/` (Foundation):** ZERO internal dependencies.
2. **`telemetry/`:** Can only import from `schemas/`.
3. **`scoring/`:** Can import from `schemas/`, `telemetry/`.
4. **`execution_planning/`:** Can import from `schemas/`, `telemetry/`, `scoring/`.
5. **`shields/`:** Can import from `schemas/`, `telemetry/`, `scoring/`, and potentially `execution_planning/` (interfaces).
6. **`strategies/`:** Can import from `schemas/`, `scoring/`, `shields/`, and `execution_planning/`.
7. **`routing/` (Orchestrator):** Can import from ALL sub-packages. **No other package imports from `routing/`.**

### 5.1 Dependency Enforcement
A declaration in `markdown` is useless without programmatic enforcement. As part of this refactoring, we will implement an automated dependency check (e.g., using `pytest-archon`, `import-linter`, or a custom Python AST crawler in `tests/architecture/`) to enforce the DAG above. Any PR violating this graph (e.g., `shields/` importing `strategies/`) will automatically fail CI.

## 6. Migration Mapping Table

| Old Module | New Target Package | Risk Level | Notes |
|:---|:---|:---|:---|
| `decision_context.py` | `schemas/` | High | Used everywhere. Move first. |
| `operational_mode.py` | `schemas/` | High | Core Enum. Used everywhere. |
| `dm_log_adapter.py` | `telemetry/` | Low | Simple move. |
| `quadratic_scoring_kernel.py`| `scoring/` | Medium | Verify caller references. |
| `safety_gates.py` | `shields/` | High | Highly coupled to context/planners. |
| `entry_plan.py` | `execution_planning/`| Medium | |
| `mean_reversion_handler.py`| `strategies/mean_reversion/` | High | Beware circular handler dependencies. |
| `decision_making.py` | `decision_making.py` (Facade) | Ext. High | Keep root representation; code in `routing/`. |
| `strategy_gateway.py`| `strategy_gateway.py` (Facade) | Ext. High | Keep root representation; code in `routing/`. |

## 7. Next Steps
1. Approve this execution-ready V2 plan.
2. Begin **Stage 0: Dependency Census**.