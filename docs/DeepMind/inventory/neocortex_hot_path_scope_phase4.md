# Neocortex Hot-Path Scope - Phase 4

```yaml
hot_path_scope:
  source_of_truth: "docs/DeepMind/inventory/neocortex_surface_inventory.md"
  included_modules:
    - path: "__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "config_models.py"
      reason: "Canonical startup/runtime config contracts for the active Stage 0.3 path."
      mypy_included: true
      coverage_included: true
    - path: "contracts/__init__.py"
      reason: "Contract package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "contracts/causal_time.py"
      reason: "Canonical causal-time decision contract."
      mypy_included: true
      coverage_included: true
    - path: "contracts/control_decision.py"
      reason: "Canonical Phase 5 authority request/response contract."
      mypy_included: true
      coverage_included: true
    - path: "contracts/failure_taxonomy.py"
      reason: "Typed failure taxonomy and reason-code contract."
      mypy_included: true
      coverage_included: true
    - path: "contracts/observation_envelope.py"
      reason: "Causal-only pre-authority envelope boundary."
      mypy_included: true
      coverage_included: true
    - path: "main.py"
      reason: "Standalone shadow-baseline bootstrap and event-tap runtime."
      mypy_included: true
      coverage_included: true
    - path: "logic/__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "logic/datasets/__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "logic/datasets/contracts.py"
      reason: "Dataset provenance contract used by active causal-time and admission boundaries."
      mypy_included: false
      coverage_included: true
    - path: "logic/datasets/time_provenance.py"
      reason: "Canonical provenance classifier used by parsers and state aggregation."
      mypy_included: true
      coverage_included: true
    - path: "logic/gates/__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "logic/gates/shadow.py"
      reason: "Production-shadow startup gate evaluator."
      mypy_included: true
      coverage_included: true
    - path: "logic/failure_ledger.py"
      reason: "In-process failure counter backing Phase 3 taxonomy assertions."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "logic/ingest/normalizer.py"
      reason: "Active normalization primitive used by state aggregation."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/observation.py"
      reason: "Tensor-ready observation contract used in active ingest/runtime path."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/parser.py"
      reason: "Active payload-to-observation parser for Stage 0.3 runtime."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/state_aggregator_v2.py"
      reason: "Causal state aggregation and snapshot assembly."
      mypy_included: true
      coverage_included: true
    - path: "logic/brain/__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "logic/brain/baseline_inference.py"
      reason: "Fail-closed baseline artifact loader and predictor boundary."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/parsers/__init__.py"
      reason: "Package marker only; no executable domain logic."
      mypy_included: false
      coverage_included: false
    - path: "logic/ingest/parsers/core_parser.py"
      reason: "Core log parser feeding causal-time and close-event boundaries."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/parsers/feature_parser.py"
      reason: "Feature log parser feeding causal-time and dataset admission boundaries."
      mypy_included: true
      coverage_included: true
    - path: "logic/ingest/parsers/order_parser.py"
      reason: "Order log parser feeding causal-time/order boundary evidence."
      mypy_included: true
      coverage_included: true
    - path: "transport/__init__.py"
      reason: "Package marker for the Phase 5 transport authority seam; must remain import-safe."
      mypy_included: false
      coverage_included: false
    - path: "transport/authority_bridge.py"
      reason: "Synchronous Phase 5 authority seam bridge owned by Neocortex transport boundary."
      mypy_included: true
      coverage_included: true
  excluded_modules:
    - path: "logic/evaluation/*.py"
      classification: "offline_research"
      reason: "Offline evaluation/reporting surface used for advisory evidence, not active runtime."
    - path: "logic/datasets/hygiene.py"
      classification: "offline_research"
      reason: "Offline dataset hygiene/reporting surface, not the active runtime decision path."
    - path: "logic/telemetry.py"
      classification: "offline_research"
      reason: "Observability sink kept for offline analysis and Phase 7 follow-up."
    - path: "logic/amygdala/*.py"
      classification: "legacy_runtime"
      reason: "Quarantined valuation helpers retained for adapter compatibility."
    - path: "logic/memory/*.py"
      classification: "legacy_runtime"
      reason: "Quarantined replay/memory helpers retained for legacy adapter compatibility."
    - path: "logic/reward/*.py"
      classification: "legacy_runtime"
      reason: "Quarantined reward/regime helpers retained for legacy adapter compatibility."
    - path: "logic/dreamer.py"
      classification: "legacy_runtime"
      reason: "Quarantined legacy RL surface outside the active hot path."
    - path: "logic/brain/core.py"
      classification: "legacy_runtime"
      reason: "Quarantined legacy brain service implementation."
    - path: "logic/brain/bridge.py"
      classification: "legacy_runtime"
      reason: "Quarantined legacy IPC bridge."
    - path: "logic/brain/worker.py"
      classification: "legacy_runtime"
      reason: "Quarantined worker process implementation."
    - path: "logic/brain/vae.py"
      classification: "legacy_runtime"
      reason: "Quarantined legacy VAE path."
    - path: "logic/brain/world_model.py"
      classification: "legacy_runtime"
      reason: "Quarantined world model path."
    - path: "logic/ingest/tailer.py"
      classification: "legacy_runtime"
      reason: "Quarantined file tailing path."
    - path: "logic/ingest/multi_tailer.py"
      classification: "legacy_runtime"
      reason: "Quarantined multi-source tailing path."
    - path: "logic/ingest/wal_replayer.py"
      classification: "legacy_runtime"
      reason: "Quarantined WAL replay path pending strict-mode follow-up."
    - path: "transport/adapter.py"
      classification: "legacy_runtime"
      reason: "Quarantined legacy transport adapter surface."
    - path: "PPO/**/*.py"
      classification: "legacy_runtime"
      reason: "Quarantined PPO library implementation."
    - path: "PPO/ppo_library_v2/examples/*.py"
      classification: "offline_research"
      reason: "Offline demo scripts outside production closure."
    - path: "experiments/*.py"
      classification: "offline_research"
      reason: "Research notebooks/scripts not part of active runtime."
    - path: "tests/*.py"
      classification: "tests_only"
      reason: "Test-only helpers and legacy parity fixtures."
  mypy_target_files:
    - "apps/reference/domains/neocortex/main.py"
    - "apps/reference/domains/neocortex/config_models.py"
    - "apps/reference/domains/neocortex/contracts/causal_time.py"
    - "apps/reference/domains/neocortex/contracts/control_decision.py"
    - "apps/reference/domains/neocortex/contracts/failure_taxonomy.py"
    - "apps/reference/domains/neocortex/contracts/observation_envelope.py"
    - "apps/reference/domains/neocortex/logic/datasets/time_provenance.py"
    - "apps/reference/domains/neocortex/logic/failure_ledger.py"
    - "apps/reference/domains/neocortex/logic/gates/shadow.py"
    - "apps/reference/domains/neocortex/logic/ingest/normalizer.py"
    - "apps/reference/domains/neocortex/logic/ingest/observation.py"
    - "apps/reference/domains/neocortex/logic/ingest/parser.py"
    - "apps/reference/domains/neocortex/logic/ingest/state_aggregator_v2.py"
    - "apps/reference/domains/neocortex/logic/ingest/parsers/core_parser.py"
    - "apps/reference/domains/neocortex/logic/ingest/parsers/feature_parser.py"
    - "apps/reference/domains/neocortex/logic/ingest/parsers/order_parser.py"
    - "apps/reference/domains/neocortex/logic/brain/baseline_inference.py"
    - "apps/reference/domains/neocortex/transport/authority_bridge.py"
  coverage_target_modules:
    - "apps.reference.domains.neocortex.config_models"
    - "apps.reference.domains.neocortex.contracts.causal_time"
    - "apps.reference.domains.neocortex.contracts.control_decision"
    - "apps.reference.domains.neocortex.contracts.failure_taxonomy"
    - "apps.reference.domains.neocortex.contracts.observation_envelope"
    - "apps.reference.domains.neocortex.main"
    - "apps.reference.domains.neocortex.logic.datasets.contracts"
    - "apps.reference.domains.neocortex.logic.datasets.time_provenance"
    - "apps.reference.domains.neocortex.logic.gates.shadow"
    - "apps.reference.domains.neocortex.logic.failure_ledger"
    - "apps.reference.domains.neocortex.logic.ingest.normalizer"
    - "apps.reference.domains.neocortex.logic.ingest.observation"
    - "apps.reference.domains.neocortex.logic.ingest.parser"
    - "apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2"
    - "apps.reference.domains.neocortex.logic.brain.baseline_inference"
    - "apps.reference.domains.neocortex.logic.ingest.parsers.core_parser"
    - "apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser"
    - "apps.reference.domains.neocortex.logic.ingest.parsers.order_parser"
    - "apps.reference.domains.neocortex.transport.authority_bridge"
  coverage_target:
    branch_coverage: "100% on declared hot-path"
  type_target:
    mypy: "0 errors on declared hot-path"
```
