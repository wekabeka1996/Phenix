# CONFIG_MODELS_ARCHITECTURE_AUDIT

**Target**: [apps/reference/config_models.py](apps/reference/config_models.py)
**Scope**: forensic architecture audit — decomposition decision under Aurora/Phenix laws.
**Mode**: Mode 3 (research / structural analysis). No code changes performed.
**Date**: 2026-04-18

---

## 1. Problem framing

The question is **not** "is this file too big?". The questions are:

1. Has ownership collapsed — i.e. do unrelated domains live in the same module only because Pydantic types happened to be added together?
2. Is the file a stable public boundary that downstream code depends on, or an implementation detail?
3. Are the cross-cutting validators (Aurora-wide invariants) *forced* to live next to their leaf models, or are they actually root-assembly truth that must stay centralized?
4. Are there dead/duplicated/legacy surfaces inside the file that would be silently propagated by a "blind split"?
5. Would a per-domain split improve maintainability, or merely scatter the same coupling across more files (and add forward-ref / circular-import risk)?

Under Phenix laws (YAML+Pydantic SSOT, no silent fallbacks, contract-first, additive-only, fail-closed), the cost of breaking this module's contract is high: any silent default introduced during a refactor would violate the no-silent-defaults law and could change runtime behavior without YAML changes.

---

## 2. FACTS

Hard, verifiable from the workspace at this commit.

- **Size**: 5,459 lines, **~190 top-level `class` definitions**, **~60 validators** (`@field_validator`, `@model_validator`, `@model_serializer`).
- **Single root**: one `AuroraConfig` (line 6084) is the assembly model.
- **External import surface is large**: `from apps.reference.config_models import …` appears in **80+ files** across `apps/`, `tools/`, and `tests/` (search truncated at 80 results). Frequently imported names: `AuroraConfig`, `AuroraInstrumentConfig`, `LeverageConfig`, `MRAssetConfig`, `MDAMRStrategyConfig`, `ExecutionGateConfig`, `ExecutionGateName`, `ExitManagerConfig`, `DangerZoneExitType`, `OperationalMode`, `RegimeShiftInceptionConfig`, `RegimeSmoothingConfig`, `MemoryShieldConfig`, `DashboardConfig`, `TAFeaturesDomainConfig`, `ObjectiveEngineDomainConfig`, `StrategyObjectiveConfig`, `InstrumentExecutionConfig`, `FallbackConfig`, `DomainsConfig`.
- **Module already imports from sibling packages**:
  ```
  from apps.reference.contracts.runtime_regime_layers import normalize_structural_regime_label
  from apps.reference.telemetry.shadow_journal import DEFAULT_CRITICAL_EVENTS
  ```
  (lines 15–16). Any split that re-imports config types into `contracts/` or `telemetry/` will create a cycle.
- **Duplicate class definitions exist within the same module** (silent shadowing — second definition wins at import time):
  - `DangerZoneShieldConfig` — line 1075 **and** line 3251
  - `ContextShieldConfig` — line 1099 **and** line 3162
  - `MemoryShieldConfig` — line 1137 **and** line 3214
  - `ScoringEngineConfig` — line 1193 **and** line 3270
- **Public back-compat aliases at end of file**:
  ```python
  AuroraTradingConfig = TradingConfig
  AuroraExposureConfig = ExposureConfig
  ```
- **Public factory**: `create_aurora_config(config_data)` (uses `AuroraConfig.model_construct`, i.e. **bypasses validation** when given a dict — explicitly noted as "testing/migration mode"). This is a public surface that a split must preserve unchanged.
- **Top-level helper sets / constants** are also exported, e.g. `STRESS_TRIGGER_KEYS`, `STRESS_PRICE_TRIGGERS`, `STRESS_ORDERBOOK_TRIGGERS`, `_POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS`, `_coerce_positive_decimal`.
- **Root validators on `AuroraConfig`** (cross-surface — they consult ≥2 sub-trees of the assembly):
  1. `validate_trading_mode_consistency` — ties `trading_mode` ↔ `trading.mode`.
  2. `_backcompat_root_execution_alias` — copies `trading.execution` → `execution` (root alias).
  3. `_fail_closed_validate_aurora_tpsl_ssot` — depends on `trading.execution`, `strategies_registry.assignments`, `instruments`, `strategies.aurora.assets`.
  4. `_validate_md_amr_assignments` — depends on `strategies_registry.assignments`, `instruments`, `strategies.md_amr.assets`.
  5. `_validate_mean_reversion_assignments` — depends on `strategies_registry.assignments`, `instruments`, `strategies.mean_reversion.assets`.
  6. `_validate_strategy_objective_regime_coverage` — depends on `strategies_registry.assignments`, all three of `strategies.{aurora, md_amr, mean_reversion}` and their per-asset `allowed_regimes` × per-strategy `objective.regimes`.
  7. `_validate_llm_strategy_contract` — depends on `trading.llm_orchestration`, `strategies_registry.assignments`, `strategies.llm_microstructure`.
- **Explicitly-flagged dead/removed surfaces (comments in file)**:
  - `# TASK-ZOMBIE-FIX: Removed FailsafeConfig` (after `ROIExitConfig`)
  - `# TASK-ZOMBIE-FIX: Removed ThreadTimeoutsConfig`
  - `# TASK-ZOMBIE-FIX: Removed MacroResidBoundsConfig`
  - `# TASK-ZOMBIE-FIX: Removed AbsorptionBoundsConfig`
  - `# PURGE-DIRTY-DOZEN: Removed KlinesConfig, ApiCallLimits`
  - `# PURGE-DIRTY-DOZEN: Removed hotreload_whitelist`
  - `# SCORCHED-EARTH-2026-01-27: hmm and features fields DELETED`
  - `# NOTE: AccountObserverDomainConfig removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)`
  - `# NOTE: bridge config removed (BRIDGE-SUNSET-01)`
- **Suspected legacy still present** (kept on inspection, not yet removed):
  - `MeanReversionConfig` (line 371) — predates `MeanReversion1mStrategyConfig` (line 802); superseded by it.
  - `RegimeModelConfig` (line 1639) co-exists with newer `RegimeModelsConfig` (line 1623).
  - `LegacyFeaturesLogConfig` (line 3302) — name itself declares legacy status.
  - Two copies each of `ContextShieldConfig`, `MemoryShieldConfig`, `DangerZoneShieldConfig`, `ScoringEngineConfig` (see duplicates above) — Phase-9 versions silently override pre-Phase-9 versions.

---

## 3. INFERENCES

Logically derivable but not directly verified.

- The file grew by **accretion of features** (Quadratic Brain, Phase 9 pillars, MR1m, MD-AMR, LLM microstructure, position policy sidecar, system stress) without ever extracting earlier surfaces. Section banners (`# ====`) imply topical groupings but no module boundary was ever introduced.
- The duplicate class definitions (`ContextShieldConfig` × 2, etc.) are **almost certainly unintended bugs**, not stylistic copies. Pydantic does not warn on redefinition; the second class wins silently. This is exactly the failure mode the no-silent-fallbacks law forbids and is **strong evidence the module is no longer safely maintainable in its present form**.
- The cross-strategy validators on `AuroraConfig` are written as **whole-tree consistency proofs** ("if symbol X is assigned strategy Y in `strategies_registry`, then `strategies.Y.assets[X]` must exist and be valid"). These cannot be relocated into per-strategy or per-domain leaf modules without re-introducing exactly the kind of late, scattered cross-checks the centralized assembly was designed to prevent.
- The `_backcompat_root_execution_alias` validator and the `AuroraTradingConfig`/`AuroraExposureConfig` aliases prove the module has already absorbed at least one round of renames behind a stable façade. A future split must therefore preserve `apps.reference.config_models` as an importable façade — not just for ergonomics but as part of the public API contract used by 80+ call sites.
- `feature_engineering/types.py` and `feature_engineering/feature_engineering.py` import config models **inside function bodies / `TYPE_CHECKING` blocks** (line 21 vs 308; 74 vs 117). This is consistent with **deliberate avoidance of import cycles already present today**, which means any naive top-level cross-import after a split will break import order.

---

## 4. ASSUMPTIONS

Stated explicitly so they can be challenged.

- A1. The module is loaded via a single canonical import path `apps.reference.config_models`. No code reaches inside the file by path manipulation. (Plausible, not exhaustively verified.)
- A2. All YAML loaders that produce dicts feed them through `AuroraConfig(**…)` (or a path that ultimately calls `AuroraConfig.model_validate`). The duplicate classes therefore affect runtime via the second (winning) definition only.
- A3. The cross-validators currently *do* run in production startup (i.e. config is built via `AuroraConfig(...)` with validation, not `model_construct`). If `create_aurora_config` is on the hot path with raw dicts, the cross-validators are **not** running today and the perceived "centralized truth" is partly nominal. This needs runtime verification before any decomposition claims rely on it.
- A4. The `from apps.reference.contracts.runtime_regime_layers import …` and `from apps.reference.telemetry.shadow_journal import …` imports do **not** themselves transitively import `apps.reference.config_models`. (If they do, even the current file is in a latent cycle.)
- A5. Tests under `tests/config/`, `tests/vfoundation/`, and `tests/apps/reference/tests/` are the dominant validators of this module's contract.

---

## 5. UNKNOWNS

- U1. Which of the duplicate-pair classes (Phase-9 vs earlier) is the one actually consumed by runtime — i.e. whether the silent shadowing has been benign or has changed semantics.
- U2. Whether `MeanReversionConfig` (line 371) has any *runtime* readers, or only stale references in tests / docs.
- U3. The full call graph of `create_aurora_config` — specifically whether production paths use it (which would skip validators, see A3).
- U4. Whether any YAML file in `config/aurora/` references fields that exist only on the **shadowed** (first) definition of `ContextShieldConfig`/`MemoryShieldConfig`/`DangerZoneShieldConfig`/`ScoringEngineConfig`. If yes, those keys are silently ignored today (`extra='forbid'` on the winning class would actually raise — needs check).
- U5. Whether the SystemStress, PositionPolicySidecar, ExecutionPosition, and ShadowTelemetry surfaces share any field names with overlapping semantic meaning across domains (potential duplicated shared types).

---

## 6. Ownership violations found

Ranked by operational severity.

| # | Severity | Violation | Evidence |
|---|---|---|---|
| O1 | **Critical** | Duplicate `class` definitions silently shadow earlier ones | `ContextShieldConfig`, `MemoryShieldConfig`, `DangerZoneShieldConfig`, `ScoringEngineConfig` each defined twice |
| O2 | High | Strategy-specific models (`MR…`, `MDAMR…`, `LLMMicrostructureStrategyConfig`, `AuroraInstrumentConfig`, `StrategyObjectiveConfig`) live in the same module as domain configs and root assembly | mixed lines 371–862, 4838–5478 |
| O3 | High | Domain-shared atoms (`SignalsConfig`, `QosConfig`, `PositionSizingConfig`, `KellyConfig`, `LiquidityGateConfig`, `SignalWeights`) are placed in the strategies-style top section but are reused by both decision-making and strategy domains | lines 186–358 |
| O4 | High | Multiple unrelated subsystems coexist as flat top-level classes: `SystemStress*`, `PositionPolicySidecar*`, `ExecutionPosition*`, `ShadowTelemetry*`, `Pillar*`, `Tactician/Operator/Strategist`, `MacroResid`, `Absorption*`, `MacroSync*`, `Pendant*` | lines 1669–1868, 3005–3297, 3795–4362, 4377–4481 |
| O5 | Medium | Legacy / deprecated models still occupy the file (`MeanReversionConfig`, `LegacyFeaturesLogConfig`, `RegimeModelConfig` next to `RegimeModelsConfig`) without freeze markers | lines 371, 1639, 3302 |
| O6 | Medium | Public back-compat aliases (`AuroraTradingConfig`, `AuroraExposureConfig`) and a "skip-validation" factory (`create_aurora_config` via `model_construct`) are not visibly documented as part of a contract | end of file |
| O7 | Medium | Cross-strategy / cross-instrument consistency validators are placed **on `AuroraConfig` itself** (correct), but the strategy-level sub-models that they consult are mixed in the same module — visually they look like leaf concerns even though they are consumed by root invariants | validators 6345–6506 |
| O8 | Low | Module-level constants such as `STRESS_TRIGGER_KEYS` and `_POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS` are defined inline next to the model that uses them, making them de-facto-public without an explicit export contract | lines ~1660, ~4063 |

The combination of **O1 + O7** is the load-bearing finding: the module is no longer a safe contract surface (O1) *and* the centralized validators that protect Aurora-wide invariants depend on the assembly layout being trustworthy (O7). A pre-emptive split without first resolving O1 would propagate the silent-shadowing bug into multiple files where it becomes harder, not easier, to detect.

---

## 7. Safe-vs-unsafe split candidates

### 7.1 Buckets (every top-level model classified)

**Bucket A — Shared primitives / reusable atoms** (safe-first move, true leaves, no validator depends on root):
`InstrumentSpec`, `InstrumentPrecisionSpec`, `LeverageConfig`, `InstrumentExecutionConfig`, `InstrumentSizingConfig`, `SignalWeights`, `BarGatingConfig`, `BehaviorFsmConfig`, `SignalsConfig`, `DirectionStrengthScoringConfig`, `LiquidityGateConfig`, `PositionSizingConfig`, `KellyConfig`, `QosConfig`, `ROIExitConfig`, `PrecisionConfig`, `OperationalMode`, `ExecutionGateName`, `DangerZoneExitType`.

**Bucket B — Domain configs** (move whole, after Bucket A):
- *decision_making/*: `DecisionMakingDomainConfig` and its sub-models — `DecisionConfig`, `DecisionGeometryConfig`, `DecisionModeOverrideConfig`, `AnchorShockVetoConfig`, `HoldingPeriodConfig`, `VolAdjGatesConfig`, `RegimeShiftInceptionConfig`, `RegimeSmoothingConfig`, `QuadraticRolloutConfig`, the **canonical (Phase-9)** `DangerZoneShieldConfig` / `ContextShieldConfig` / `MemoryShieldConfig` / `ScoringEngineConfig`, `DashboardConfig`, `ExecutionGateConfig`, `StructuralGateConfig`, `ExitManagerConfig`, `EntryPlanConfig`, `DegradedContextStrategyContractConfig`, `RegimeLossEmbargoConfig`, `FlipOrchestrationConfig`, `GlobalFlipKillswitchConfig`, `MoneyManagementConfig`, `DirectionalSanityConfig`, `PriceMotionSanityConfig`, `ArmingConfig`, `RiskSkewConfig`, `RiskGateConfig`, `FeaturesTtlConfig`, `SafetyGatesConfig`, `ReadinessRegistryConfig`, `WarmupEnforcementConfig`.
- *feature_engineering/*: `FeatureEngineeringDomainConfig`, `FeatureEngineeringConfig`, `EmaConfigDetailed`, `VolumeConfigDetailed`, `VolatilityConfigDetailed`, `LiquidityConfigDetailed`, `EmaBiasConfig`, `VolumeSpikeConfig`, `VolumeZScoreConfig`, `LargeTradeImbalanceConfig`, `MacroSyncMetricsConfig`, `VolatilityStateConfig`, `DepthImbalanceConfig`, `DeltaPriceConfig`, `FeatureDefaultsConfig`, `SpreadHealthGateConfig`, `SpreadBpsConfig`, `FeatureBoundsConfig`, `FeatureSanityConfig`, `MacroResidConfig`, `AbsorptionConfig`, `AbsorptionProxyConfig`, `AbsorptionDedupConfig`, `TacticianConfig`, `OperatorConfig`, `StrategistConfig`, `PillarWeightsConfig`, `PillarBackfillConfig`, `PillarsConfig`, `LegacyFeaturesLogConfig` (freeze candidate), `TAFeaturesDomainConfig`.
- *risk_management/*: `RiskManagementDomainConfig`, `RiskScoreWeightsConfig`, `TradingAllowedThresholdsConfig`, `RiskValidationConfig`.
- *position_tracking/*: `PositionTrackingDomainConfig`.
- *execution_position/*: `ExecutionPositionDomainConfig` and its ~30 sub-models (`ExposureGuardConfig`, `FsmOpenConfig`, `OrderIndexConfig`, `MetricsCollectorConfig`, `IdempotentCancelConfig`, `ExecutionUtilsConfig`, `InflightReconcileConfig`, `EventDedupConfig`, `EventDedupWarmStateConfig`, `DriftAwayConfig`, `AdvancedStaleCancelConfig`, `SupersedeRepriceGuardConfig`, `PendingEntryTTLConfig`, `MakerOnlyEntryConfig`, `OrderCapabilitiesConfig`, `BracketPlacementConfig`, `OrderLifecycleConfig`, `ShadowCheckConfig`, `GuardianConfig`, `BracketHealthCheckConfig`, `IntentBoundaryAuditConfig`, `PositionPolicySidecar*` (10 classes + Mode enum), `ExecutionPositionRestoreArtifactConfig` (+Mode), `ExecutionPositionStartupTruthArtifactConfig` (+Mode)).
- *shadow_telemetry/*: `ShadowTelemetryDomainConfig`, `ShadowTelemetryIngestConfig`, `ShadowTelemetryApiConfig`, `ShadowTelemetryApiWriteConfig`, `ShadowTelemetryEgressToMainConfig`, `ShadowTelemetryTfPolicyConfig`, `ShadowTelemetrySnapshotConfig`.
- *objective_engine/*: `ObjectiveEngineDomainConfig`, `ObjectiveNormalizationConfig`, `ObjectiveComponentConfig`, `ObjectiveDataRequirementsConfig`, `ObjectiveExplainabilityConfig`.
- *DomainsConfig* (`DomainsConfig`, `DomainsDebugConfig`) — root-of-domains aggregator.

**Bucket C — Strategy configs** (independent file per strategy, after Bucket B):
- *aurora*: `AuroraStrategyConfig`, `AuroraInstrumentConfig`, `AuroraSideBiasConfig`, `RegimeTpSlConfig`, `AuroraExitConfig`, `AuroraTakeProfitConfig`, `AuroraTrailingStopConfig`, `AuroraExecutionConfig`, `EmaClampConfig`, `SignalThresholdConfig`, `MaxRiskScoreConfig`, `VolatilityEntryConfig`, `StrategyExecutionConfig`.
- *mean_reversion*: `MeanReversion1mStrategyConfig`, `MRStrategyParamsConfig`, `MRRegimeThresholdsConfig`, `MRSqueezeExpansionVetoConfig`, `MRMomentumSeparationVetoConfig`, `MRMicrostructureVetoConfig`, `MRDirectionalBiasConfig`, `MRStrategyOverrideConfig`, `MRAssetConfig`, `MRRegimeSizingConfig`. (Old `MeanReversionConfig` at line 371 is a freeze/deprecate candidate.)
- *md_amr*: `MDAMRStrategyConfig`, `MDAMRWeightsConfig`, `MDAMRLLMGateConfig`, `MDAMRAssetConfig`, `MDAMRReconciliationConfig`, `MDAMRConcentrationGuardConfig`, `MDAMROptunaConfig`, `MDAMRProgressTrackingConfig`, `MDAMRSetupQualityConfig`, `MDAMRHoldQualityConfig`, `MDAMRContextValidityConfig`, `MDAMREntryAnchorPersistenceConfig`, `MDAMRExitConfig`.
- *llm_microstructure*: `LLMMicrostructureStrategyConfig`.
- *common*: `StrategyObjectiveConfig`, `StrategyObjectiveRegimeProfile`, `StrategyObjectiveGateConfig`, `StrategyObjectiveMultiplierConfig`, `StrategiesRegistryConfig`, `StrategiesArbitrationConfig`, `StrategiesArbitrationLoggingConfig`, `StrategiesConfig`.

**Bucket D — System / trading / observability / ops** (single horizontal split):
`TradingConfig`, `TradingRiskManagementConfig`, `RiskManagementDataSourcesConfig`, `BinanceApiConfig`, `BinanceApiEnv`, `LLMOrchestrationConfig`, `LLMIntentPolicyConfig`, `RiskBudgetsConfig`, `TCAPrefsConfig`, `DomainConfigurationConfig`, `DomainModeConfig`, `OpsConfig`, `SystemConfig`, `SystemMarketDataConfig`, `SystemMetaConfig`, `SystemRuntimeMeta`, `SystemStress*` (4 classes + key-set constants), `RegimeDetectorConfig`, `RegimeModelsConfig`, `RegimeModelConfig` (freeze candidate), `SMARegimeModelConfig`, `VolatilityRegimeModelConfig`, `MeanReversionRegimeModelConfig`, `MarketDataConfig`, `BarAggregatorConfig`, `MacroSyncConfig`, `ExecutionConfig`, `OrdersConfig`, `LimitOrdersConfig`, `FallbackConfig`, `WatchdogConfig`, `EmergencyConfig`, `OrphanMonitorConfig`, `ManageConfig`, `ExposureConfig`, `BracketsConfig`, `SLConfig`, `TPConfig`, `TrailingDefaultsConfig`, `ObservabilityConfig`, `ObservabilityLoggingConfig`, `LogRotationConfig`, `ConsoleLogConfig`, `CoreLogSinkConfig`, `DomainLogConfig`, `EventChainLogConfig`, `AlertsConfig`, `ShadowCriticalEventJournalConfig`.

**Bucket E — Root assembly (must NOT move)**:
`AuroraConfig`, the 7 cross-validators on it, `create_aurora_config`, `AuroraTradingConfig` / `AuroraExposureConfig` aliases, `_coerce_positive_decimal` helper.

### 7.2 Safe first-move candidates

True leaves with **no root coupling** and **no validator that reaches into another sub-tree** — these can move first with the lowest risk:

- All Bucket A atoms.
- `DashboardConfig` (only locally validated; already imported standalone by `dashboard.py`).
- `ExecutionGateConfig` / `ExecutionGateName`, `ExitManagerConfig` / `DangerZoneExitType` (already imported as standalone names in their domain files).
- `RegimeShiftInceptionConfig`, `RegimeSmoothingConfig` (already imported standalone).
- `MemoryShieldConfig` (imported standalone) — **but only after duplicate definition is resolved (O1)**.
- `LeverageConfig` (already a standalone import in many places) — **highest-value early move**.

### 7.3 Unsafe-without-prerequisite candidates

- Any of the four duplicated classes (O1) — must be **de-duplicated and one canonical version chosen** before extraction.
- `MeanReversionConfig` (legacy) — must be **frozen or deleted** before strategy split, otherwise both versions ship into `strategies/mean_reversion/`.
- `RegimeModelConfig` vs `RegimeModelsConfig` — clarify which is current before moving regime models.
- The Aurora-side cross-validators on `AuroraConfig` — **must remain on the root assembly** because each consults ≥2 of: `instruments`, `strategies_registry`, `strategies.<id>.assets`, `trading.execution`, `trading.llm_orchestration`. Relocating them into a leaf module would either (a) require the leaf to import the root (circular) or (b) require the validator to be re-armed at root from a different file (more surface, same coupling).
- `SignalsConfig`, `QosConfig`, `PositionSizingConfig`, `KellyConfig`, `LiquidityGateConfig` — used by both decision-making and strategy domains. If duplicated into both packages they violate "no duplicated shared types"; they belong in a `shared/` atoms module imported by both.

---

## 8. Proposed target package structure

Additive. Does **not** move `AuroraConfig`. Does **not** delete the existing public import path.

```
apps/reference/
├── config_models.py                  # FAÇADE: re-exports everything previously
│                                     # exported. Keeps AuroraConfig + cross-validators
│                                     # + create_aurora_config + back-compat aliases
│                                     # + _coerce_positive_decimal here.
└── config/
    ├── __init__.py                   # explicit re-export contract (for new callers)
    ├── shared/
    │   ├── __init__.py
    │   ├── atoms.py                  # SignalWeights, SignalsConfig, QosConfig,
    │   │                             #   PositionSizingConfig, KellyConfig,
    │   │                             #   LiquidityGateConfig, BarGatingConfig,
    │   │                             #   BehaviorFsmConfig, DirectionStrengthScoringConfig,
    │   │                             #   ROIExitConfig, PrecisionConfig
    │   ├── instruments.py            # InstrumentSpec, InstrumentPrecisionSpec,
    │   │                             #   InstrumentExecutionConfig, InstrumentSizingConfig,
    │   │                             #   LeverageConfig
    │   ├── enums.py                  # OperationalMode, ExecutionGateName,
    │   │                             #   DangerZoneExitType, *Mode enums
    │   └── decimal_utils.py          # _coerce_positive_decimal (re-export only)
    ├── domains/
    │   ├── decision_making.py        # DecisionMakingDomainConfig + sub-models +
    │   │                             #   the canonical (Phase-9) shield/scoring models
    │   ├── feature_engineering.py    # FeatureEngineeringDomainConfig + sub-models +
    │   │                             #   pillars + macro_resid + absorption
    │   ├── ta_features.py            # TAFeaturesDomainConfig
    │   ├── risk_management.py        # RiskManagementDomainConfig + sub-models
    │   ├── position_tracking.py      # PositionTrackingDomainConfig
    │   ├── execution_position.py     # ExecutionPositionDomainConfig + sub-models +
    │   │                             #   PositionPolicySidecar* + Restore/StartupTruth
    │   ├── shadow_telemetry.py       # ShadowTelemetryDomainConfig + sub-models
    │   ├── objective_engine.py       # ObjectiveEngineDomainConfig + sub-models
    │   └── _aggregator.py            # DomainsConfig, DomainsDebugConfig
    ├── strategies/
    │   ├── common.py                 # StrategiesConfig, StrategiesRegistryConfig,
    │   │                             #   StrategiesArbitrationConfig (+Logging),
    │   │                             #   StrategyObjective* (4 classes)
    │   ├── aurora.py                 # AuroraStrategyConfig + AuroraInstrumentConfig
    │   │                             #   + Aurora{Exit, TakeProfit, TrailingStop,
    │   │                             #             Execution, SideBias} + RegimeTpSl
    │   │                             #   + EmaClamp / SignalThreshold / MaxRiskScore /
    │   │                             #   VolatilityEntry / StrategyExecution
    │   ├── mean_reversion.py         # MeanReversion1mStrategyConfig + MR* + SafetyGates
    │   ├── md_amr.py                 # MDAMRStrategyConfig + MDAMR*
    │   └── llm_microstructure.py     # LLMMicrostructureStrategyConfig
    └── system/
        ├── trading.py                # TradingConfig, LLMOrchestration*, RiskBudgets,
        │                             #   TCAPrefs, DomainConfiguration*, DomainMode
        ├── binance.py                # BinanceApiConfig, BinanceApiEnv,
        │                             #   TradingRiskManagementConfig + sources
        ├── execution.py              # ExecutionConfig, OrdersConfig, LimitOrdersConfig,
        │                             #   FallbackConfig, BracketsConfig, SL/TP/Trailing,
        │                             #   Emergency, Watchdog, OrphanMonitor, Manage,
        │                             #   Exposure
        ├── regime.py                 # RegimeDetectorConfig, RegimeModelsConfig,
        │                             #   SMA/Volatility/MeanReversion regime models,
        │                             #   RegimeShiftInception (re-export)
        ├── system_stress.py          # SystemStressConfig + sub-models +
        │                             #   STRESS_*_TRIGGERS constants
        ├── market_data.py            # MarketDataConfig, BarAggregatorConfig,
        │                             #   MacroSyncConfig, SystemMarketDataConfig
        ├── observability.py          # ObservabilityConfig + ObservabilityLoggingConfig
        │                             #   + Log/Console/Core/Domain/EventChain configs
        │                             #   + AlertsConfig + ShadowCriticalEventJournalConfig
        ├── ops.py                    # OpsConfig
        └── meta.py                   # SystemConfig, SystemMetaConfig, SystemRuntimeMeta
```

Imports always flow **upward**: `shared/` ← `domains/` ← `strategies/` ← `system/` ← `config_models.py` (root). No domain or strategy module is allowed to import from `config_models.py`.

---

## 9. Recommended migration plan (phase by phase)

Strictly additive. Every phase is independently revertable. The public import path `apps.reference.config_models` is preserved at all times.

### Phase 0 — **PRE-SPLIT MANDATORY CLEANUP** (no decomposition yet)

P0 is a **hard gate**. Without it, the duplicate-class shadowing and dead surfaces will be propagated and obscured by the split.

1. Resolve **O1** (duplicate class definitions). For each of `ContextShieldConfig`, `MemoryShieldConfig`, `DangerZoneShieldConfig`, `ScoringEngineConfig`:
   - Compare both definitions line-by-line.
   - Verify against `config/aurora/*.yaml` which fields are populated at runtime.
   - Keep one canonical definition; delete the other; add a regression test that imports the class and asserts its field set.
2. Decide fate of legacy / suspected-dead surfaces:
   - `MeanReversionConfig` (line 371): grep runtime + tests; if no live consumer, delete; otherwise mark `# FROZEN: replaced by MeanReversion1mStrategyConfig` and forbid new fields.
   - `LegacyFeaturesLogConfig`: same treatment.
   - `RegimeModelConfig` vs `RegimeModelsConfig`: confirm canonical, freeze the other.
3. Audit `create_aurora_config` (`model_construct` path). If production loaders use it, this is a silent-validation hole; either remove it or restrict to test-only and add an explicit `model_validate` path for production. (This is a no-silent-defaults law check, not a refactor task.)
4. Land Phase 0 as one PR. Validation: full test suite + a new test that asserts each previously-duplicated class name resolves to **exactly one definition** (`len([c for c in vars(config_models).values() if getattr(c, "__name__", None) == name]) == 1`).

### Phase 1 — Shared atoms + enums (lowest blast radius)

5. Create `apps/reference/config/shared/{atoms.py, instruments.py, enums.py, decimal_utils.py}` containing the Bucket A models.
6. In `apps/reference/config_models.py`, replace the in-file definitions with `from apps.reference.config.shared.* import *` re-exports. Names exported by `config_models.py` must be **bit-identical** (`is` equality preserved — no shadow classes).
7. Validation:
   - Run full pytest.
   - Run `python -c "from apps.reference.config_models import LeverageConfig, OperationalMode, SignalsConfig, ExecutionGateName"` and equivalents for every previously-public name.
   - Static check: `grep -R "from apps.reference.config_models import" tests/ apps/ tools/` succeeds for the same set as before the change.

### Phase 2 — Domain configs (one PR per domain)

8. Move one domain at a time, in this safest order: `objective_engine` → `risk_management` → `position_tracking` → `shadow_telemetry` → `ta_features` → `feature_engineering` → `decision_making` → `execution_position`. Each PR moves only that domain's classes, leaves all root validators in place, and re-exports from `config_models.py`.
9. For `decision_making` and `feature_engineering`, ensure the **canonical (Phase-9)** versions of the previously-duplicated shield/scoring classes (Phase 0 outcome) are the ones moved.
10. Validation per PR: full pytest + targeted contract tests in `tests/config/`, `tests/vfoundation/`, `tests/apps/reference/tests/`. Add (if missing) a regression test that builds `AuroraConfig` from a representative YAML in `config/aurora/` and asserts no `ValidationError`.

### Phase 3 — Strategy configs

11. Move per strategy: `mean_reversion` → `md_amr` → `llm_microstructure` → `aurora`. Move `StrategyObjective*`, `StrategiesArbitration*`, `StrategiesRegistryConfig`, and `StrategiesConfig` into `strategies/common.py` last.
12. The cross-strategy validators on `AuroraConfig` stay where they are. They now import strategy types via the root façade only.
13. Validation: same as Phase 2, plus explicit assertion that the cross-validators still raise on the same error inputs (preserve a few negative test fixtures).

### Phase 4 — System / trading / observability / ops

14. Move Bucket D into `apps/reference/config/system/`.
15. `RegimeShiftInceptionConfig`, `RegimeSmoothingConfig`, `RegimeDetectorConfig`, `RegimeModelsConfig` move with `system/regime.py`. `SystemStressConfig` and `STRESS_*` constants move with `system/system_stress.py`.

### Phase 5 — Aggregator + final shape

16. Move `DomainsConfig` into `config/domains/_aggregator.py`. Re-export from `config_models.py`.
17. `config_models.py` is now ~300–500 lines: only `AuroraConfig`, its 7 cross-validators, `create_aurora_config`, the back-compat aliases, and a flat block of `from … import *` re-exports.
18. Optional: introduce `apps/reference/config/__init__.py` as the **new** preferred public entry point and add a deprecation note (only a note — no removal) to `config_models.py`. New code uses the package; old code keeps working.

### Phase 6 (optional, deferred) — Documentation + freeze of dead surfaces

19. Add `apps/reference/config/README.md` describing module ownership rules, the "atoms-only-up" import direction, and where new models go.
20. Remove (not freeze) any model still marked `# FROZEN` after one full release cycle with zero call sites.

---

## 10. Validation plan

For every phase:

1. **Bit-identical public surface check**: enumerate every name previously importable from `apps.reference.config_models` and assert the same name resolves after the change to the same class object (`is` identity).
2. **Real-config load test**: load each YAML under `config/aurora/` into `AuroraConfig` and assert no `ValidationError`. Cover at least: a baseline production-style config, a backtest config, and a config with `system_stress` enabled.
3. **Cross-validator regression suite**: keep negative fixtures for each of the 7 root validators (e.g. "symbol assigned to `aurora` but `strategies.aurora.assets[<symbol>].exit.sl_pct` missing"). Run them after every phase and confirm they still raise with the same `ValueError` substring.
4. **Import-cycle smoke**: at the end of every phase, run a clean process startup that imports `apps.reference.config_models`, `apps.reference.contracts.runtime_regime_layers`, and `apps.reference.telemetry.shadow_journal` in arbitrary orders. No `ImportError`.
5. **Static no-fallback audit**: grep the new modules for `default=` on any field that was previously `Field(...)` (required). The split must not change required-vs-optional status of any field.
6. **Existing repo verification tools**: run `tools/ci_cd/audit_yaml_loading.py`, `tools/maintenance/autofill_config_defaults_into_yaml.py --check`, and (where applicable) the `tests/vfoundation/` and `tests/config/` suites.
7. **Diff review**: each PR's diff must show only file moves + re-exports + (in Phase 0) the canonical de-duplication. A PR that touches both a domain move and an unrelated field default change is invalid and must be split.

---

## 11. Risks / unproven areas

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Circular import via `apps.reference.contracts.*` or `apps.reference.telemetry.*` once domain modules import shared atoms that those packages also import | Medium | High (startup failure) | Keep `shared/` strictly free of imports from `apps.reference.*` outside `apps.reference.config.*`; verify with import-cycle smoke (validation step 4) |
| R2 | `feature_engineering/types.py` and `feature_engineering.py` already import config models inside function bodies → split may surface latent cycles | Medium | Medium | Move feature_engineering domain with the same lazy-import pattern; do not "clean up" those `TYPE_CHECKING`/in-function imports in the same PR |
| R3 | The duplicate-class O1 issue may have been masking a real config field that exists only on the shadowed (first) definition; choosing the wrong canonical version silently loses a field at startup | High if not audited | High | Phase 0 step 1: compare *both* definitions and grep YAML for fields unique to the shadowed copy before deletion |
| R4 | `create_aurora_config(...)` uses `model_construct`, bypassing all 7 cross-validators; if production calls it with raw dicts, decomposition does not actually fix anything because the invariants are not enforced today | Unknown until A3 verified | High (silent invariant failure) | Phase 0 step 3: trace and either remove or downgrade to test-only |
| R5 | Test fixtures or other modules use `from apps.reference.config_models import …` for **non-public** symbols (e.g. `_POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS`, `_coerce_positive_decimal`); the façade must re-export these too | Medium | Medium | Validation step 1 (bit-identical surface) catches this |
| R6 | A naive split that moves `MeanReversionConfig` (legacy) into `strategies/mean_reversion.py` resurrects a dead surface as if it were canonical | Medium if Phase 0 is skipped | High | Phase 0 step 2 freezes/deletes legacy first |
| R7 | Cross-strategy validators on `AuroraConfig` use `getattr(self.strategies, "aurora", None)` etc.; if anyone re-types `strategies.aurora` in a leaf module with a slightly different shape, validators silently pass on wrong attributes | Low (Pydantic enforces shape) but worth gating | Medium | Validation step 3 keeps negative fixtures green |
| R8 | The 80+ external import call sites mean any name accidentally dropped from the façade re-export breaks a wide blast radius | High if re-exports are hand-written | Medium | Use `__all__` lists and an explicit registry test (validation step 1) instead of `from x import *` |

Unproven areas requiring runtime proof before *any* code edit:

- U1 (which duplicate wins / matters), U3 (`create_aurora_config` runtime usage), U4 (YAML keys against shadowed-vs-winning class), U5 (semantic overlap of similarly-named fields across domains).

---

## 12. Final verdict

> **Do not split yet. The decomposition is correct in principle, but it is currently blocked by Phase 0 prerequisites. Execute Phase 0 first; then proceed with a partial, additive split (Phases 1→5) that retains `AuroraConfig` and all 7 root cross-validators in `apps/reference/config_models.py` as the canonical assembly + façade.**

Why "blocked, then partial split" rather than "split now" or "keep as one file":

- **Not "split now"**: the file contains four silently-shadowed duplicate class definitions (O1) and at least three legacy/superseded models (`MeanReversionConfig`, `LegacyFeaturesLogConfig`, `RegimeModelConfig`). A blind split would propagate the silent shadowing into multiple files where it becomes harder to detect, and would resurrect dead models as if they were canonical. This violates the no-silent-fallbacks and contract-first laws.
- **Not "keep as one file"**: ~190 top-level classes with mixed ownership across 5,459 lines have crossed the legibility threshold. Quote from this file's own banners: at least 9 distinct sub-systems (decision-making, feature-engineering, system stress, position policy sidecar, execution position, shadow telemetry, objective engine, strategies, observability) coexist with no module boundary. The duplicate-class bug is direct evidence the file has lost reviewability.
- **Not "full split with new root location"**: `AuroraConfig` lives at `apps.reference.config_models.AuroraConfig` in 80+ call sites. Moving the root would require a coordinated cross-repo rename — disproportionate to the actual problem (ownership, not location).

The recommended path keeps the laws intact (root assembly stays the only place where Aurora-wide invariants are proven), reduces blast radius (one domain or strategy per PR), and resolves the maintainability problem without breaking any existing import.

**Definition of done for the audit (this document)**: an explicit, evidence-backed verdict (above), an explicit module/package layout (Section 8), an explicit migration sequence with verifiable per-phase success criteria (Sections 9–10), and an explicit list of what must be deleted or frozen *before* the split (Phase 0). Implementation is **not** in scope for this audit and is intentionally not started.
