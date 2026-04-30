# Neocortex Hot-Path Scope - Phase 5

```yaml
phase5_hot_path_scope:
  source_of_truth:
    - "docs/DeepMind/06_NEOCORTEX_MASTER_BLUEPRINT.md"
    - "docs/DeepMind/07_NEOCORTEX_EXECUTION_ROADMAP.md"
  included_modules:
    - path: "contracts/control_decision.py"
      reason: "Canonical Phase 5 authority request/response contract."
      mypy_included: true
      coverage_included: true
    - path: "logic/failure_ledger.py"
      reason: "Bridge-side failure counter used by Phase 5 fallback recording."
      mypy_included: true
      coverage_included: true
    - path: "transport/authority_bridge.py"
      reason: "Synchronous Phase 5 authority seam bridge owned by the Neocortex transport boundary."
      mypy_included: true
      coverage_included: true
  validation_only_modules:
    - path: "apps/reference/domains/decision_making/gateway/strategy_gateway.py"
      reason: "Inline authority apply/journal behavior is functionally regressed by Phase 5 seam tests, but the file is broader than the Neocortex-owned coverage target."
  excluded_patterns:
    - path: "apps/reference/domains/neocortex/config_models.py"
      classification: "phase4_hot_path"
      reason: "Validated under the broader Phase 4 closure; not part of the Phase 5 authority-specific coverage target."
    - path: "apps/reference/domains/neocortex/contracts/observation_envelope.py"
      classification: "phase4_hot_path"
      reason: "Pre-authority causal envelope remains a Phase 4 hot-path contract; Phase 5 closure targets the authority seam contract and bridge."
    - path: "apps/reference/domains/neocortex/contracts/failure_taxonomy.py"
      classification: "phase3_hot_path"
      reason: "Taxonomy contract was already closed in Phase 3; Phase 5 only counts the failure ledger that records bridge outcomes."
    - path: "apps/reference/domains/neocortex/logic/gates/shadow.py"
      classification: "phase4_hot_path"
      reason: "Startup shadow gate logic remains in the Phase 4 closure lane, not the Phase 5 authority seam lane."
    - path: "apps/reference/domains/neocortex/PPO/**/*.py"
      classification: "legacy_runtime"
      reason: "Quarantined PPO runtime is outside the active Phase 5 authority seam."
    - path: "apps/reference/domains/neocortex/experiments/*.py"
      classification: "offline_research"
      reason: "Offline experiments are not part of the live authority seam."
    - path: "apps/reference/domains/neocortex/logic/telemetry.py"
      classification: "offline_research"
      reason: "Observability sink remains Phase 7 follow-up, not a Phase 5 coverage target."
    - path: "apps/reference/domains/neocortex/transport/adapter.py"
      classification: "legacy_runtime"
      reason: "Legacy adapter is quarantined and must not enter the Phase 5 authority coverage target."
    - path: "apps/reference/domains/neocortex/logic/brain/*.py"
      classification: "legacy_runtime"
      reason: "Legacy brain service implementation remains outside the authority seam closure target except for explicit bridge-owned files."
  mypy_target_files:
    - "apps/reference/domains/neocortex/contracts/control_decision.py"
    - "apps/reference/domains/neocortex/logic/failure_ledger.py"
    - "apps/reference/domains/neocortex/transport/authority_bridge.py"
  coverage_target_modules:
    - "apps.reference.domains.neocortex.contracts.control_decision"
    - "apps.reference.domains.neocortex.logic.failure_ledger"
    - "apps.reference.domains.neocortex.transport.authority_bridge"
  coverage_target:
    branch_coverage: "100% on declared Phase 5 authority seam files"
  type_target:
    mypy: "0 errors on declared Phase 5 authority seam files"
```
