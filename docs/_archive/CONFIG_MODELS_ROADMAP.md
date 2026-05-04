# CONFIG_MODELS_ROADMAP

**Initiative**: Safe decomposition and cleanup of [apps/reference/config_models.py](apps/reference/config_models.py)
**SSOT inputs**: [CONFIG_MODELS_ARCHITECTURE_AUDIT.md](CONFIG_MODELS_ARCHITECTURE_AUDIT.md), [apps/reference/config_models.py](apps/reference/config_models.py)
**Companion log**: [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md)
**Mode**: planning-only. No code edits, no file moves, no refactor execution authorized by this document.
**Date**: 2026-04-18

**Governance recovery note**: after Phase 0 was executed before the originally intended planning/review gate, see [CONFIG_MODELS_GOVERNANCE_RECOVERY.md](CONFIG_MODELS_GOVERNANCE_RECOVERY.md) and [CONFIG_MODELS_ROADMAP_ADDENDUM.md](CONFIG_MODELS_ROADMAP_ADDENDUM.md) before any Phase 1 work.

---

## 1. Executive summary

The audit established that `apps/reference/config_models.py` (5,459 LOC, ~190 top-level classes, ~60 validators, root `AuroraConfig` + 7 cross-validators, 80+ external import sites) has crossed the legibility and ownership-collapse threshold, **and** contains four silently-shadowed duplicate class definitions plus at least three legacy/superseded models. The audit verdict — *"do not split yet; execute Phase 0 cleanup first; then partial additive split that retains `AuroraConfig` and the 7 cross-validators in `config_models.py` as canonical assembly + façade"* — is adopted as the policy for this roadmap.

This roadmap is the formal execution plan that translates that verdict into discrete, validation-gated work packages, each suitable for a single PR. No package may begin until the previous package's closure evidence is recorded in [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md).

## 2. Problem framing

The problem is not file size. It is:

1. **Ownership collapse**: nine distinct subsystems (decision-making, feature-engineering, system stress, position policy sidecar, execution position, shadow telemetry, objective engine, strategies, observability) coexist as flat top-level classes with no module boundary.
2. **Silent shadowing**: four classes are defined twice in the same module; Pydantic does not warn; the second definition wins. Failure mode forbidden by the no-silent-fallbacks law.
3. **Latent invariant erosion**: 7 root cross-validators on `AuroraConfig` enforce Aurora-wide invariants, but `create_aurora_config` uses `model_construct`, which would bypass them if used on the production hot path.
4. **Wide blast radius**: the file is the public import boundary for ≥80 call sites across `apps/`, `tools/`, `tests/`.

Root problem is **ownership/contract discipline**, not layout aesthetics. Roadmap's job is to fix ownership without losing any invariant.

## 3. FACTS

Carried verbatim from the audit (Section 2). Re-asserted as planning truth:

- Size: 5,459 lines; ~190 top-level classes; ~60 validators.
- Single root: `AuroraConfig` (line 6084) with 7 cross-validators (`validate_trading_mode_consistency`, `_backcompat_root_execution_alias`, `_fail_closed_validate_aurora_tpsl_ssot`, `_validate_md_amr_assignments`, `_validate_mean_reversion_assignments`, `_validate_strategy_objective_regime_coverage`, `_validate_llm_strategy_contract`).
- Public factory `create_aurora_config(...)` uses `AuroraConfig.model_construct` (validation-bypass path documented in source).
- Public back-compat aliases: `AuroraTradingConfig = TradingConfig`, `AuroraExposureConfig = ExposureConfig`.
- Module-level helpers/constants are part of the implicit public surface: `_coerce_positive_decimal`, `STRESS_TRIGGER_KEYS`, `STRESS_PRICE_TRIGGERS`, `STRESS_ORDERBOOK_TRIGGERS`, `_POSITION_POLICY_SIDECAR_CANONICAL_STRUCTURAL_REGIME_LABELS`.
- Module already imports siblings: `apps.reference.contracts.runtime_regime_layers`, `apps.reference.telemetry.shadow_journal`. Any new cross-import that pulls config types back into those packages closes a cycle.
- Duplicate class definitions in the same module (second wins): `DangerZoneShieldConfig` (1075/3251), `ContextShieldConfig` (1099/3162), `MemoryShieldConfig` (1137/3214), `ScoringEngineConfig` (1193/3270).
- Suspected legacy still present: `MeanReversionConfig` (371), `RegimeModelConfig` (1639) vs `RegimeModelsConfig` (1623), `LegacyFeaturesLogConfig` (3302).
- External import surface: ≥80 files import from `apps.reference.config_models`.

## 4. INFERENCES

- File grew by accretion across multiple feature epochs (Quadratic Brain, Phase 9 pillars, MR1m, MD-AMR, LLM microstructure, position policy sidecar, system stress) with no extraction step.
- The four duplicate-class pairs are almost certainly unintended re-pastes during Phase-9 work, not stylistic. Their existence is direct evidence the module is no longer reviewable end-to-end.
- The 7 cross-validators each consult ≥2 sub-trees of the assembly; they are root-assembly truth and cannot be relocated to leaves without circular imports or re-armed validators of equal scope.
- `feature_engineering/types.py` and `feature_engineering/feature_engineering.py` already use `TYPE_CHECKING` and in-function imports of config models — pre-existing latent cycle; any split must not "tidy" those imports while moving classes.

## 5. ASSUMPTIONS

- A1. Canonical import path is `apps.reference.config_models`; no path-manipulation reads.
- A2. Production loaders feed YAML through `AuroraConfig(...)` / `model_validate`, not `model_construct`. (Phase 0 verifies/falsifies.)
- A3. `contracts/` and `telemetry/` siblings imported by the file do not transitively import `config_models`.
- A4. Tests in `tests/config/`, `tests/vfoundation/`, `tests/apps/reference/tests/` are dominant contract validators today.
- A5. Each duplicated pair has a single semantically-correct winner (later/Phase-9). To be confirmed in Phase 0.

## 6. UNKNOWNS

- U1. Which of the duplicate-pair classes is actually consumed by runtime YAML keys.
- U2. Whether `MeanReversionConfig` (legacy) has any runtime reader.
- U3. Full call graph of `create_aurora_config`; whether any production path uses it.
- U4. Whether any YAML key references a field unique to the *shadowed* (first) class definition.
- U5. Whether any field name overlaps semantically across `SystemStress*`, `PositionPolicySidecar*`, `ExecutionPosition*`, `ShadowTelemetry*`.

Each Unknown must be answered (or recorded as remaining unproven) before its dependent phase opens.

## 7. Why implementation is blocked right now

Implementation is blocked on **Phase 0 prerequisites**:

1. Duplicate-class shadowing (O1) leaves "what is canonical" unanswered for four classes; blind extraction would propagate the shadow.
2. Three legacy/superseded models are still importable without freeze markers; naive strategy split would resurrect them as canonical.
3. `create_aurora_config` validation-bypass may make centralized invariants nominal; if true, the entire premise is false and priorities shift.
4. There is no bit-identical public-surface manifest to compare against post-split. Without it, breakage in the 80+ call-site fan-out is not detectable in CI.

Until those four are resolved by Phase 0 closure evidence in [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md), no later phase may begin.

## 8. Architectural laws for this initiative

1. **YAML + Pydantic SSOT**. No business logic outside config. No Python-level fallbacks for missing config keys.
2. **No silent fallbacks**. Required fields stay `Field(...)`. No new `default=` introduced during a move.
3. **Contract-first, additive-only**. Bit-identical public import surface preserved at every package.
4. **Root invariants stay centralized**. `AuroraConfig` and its 7 cross-validators remain in `apps/reference/config_models.py`. Relocation requires explicit roadmap addendum.
5. **Runtime truth outweighs static assumptions**. Phase 0 must produce runtime evidence for U1–U5 before later phases consume those answers.
6. **Fail closed when evidence is weak**. Ambiguous duplicate → safer (more restrictive) version is canonical.
7. **One narrow package per PR**. Mixing a class move with a behavior fix in one PR is forbidden.
8. **No closure without journal entry**. A package is DONE only when its entry is recorded in [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md) with validation evidence.

## 9. Frozen boundaries

- **F1. `AuroraConfig` location**: stays at `apps.reference.config_models.AuroraConfig`. Public import path unchanged.
- **F2. The 7 root cross-validators**: stay defined on `AuroraConfig` in `apps/reference/config_models.py`. No leaf split allowed by this roadmap.
- **F3. `apps/reference/config_models.py` as façade**: every name previously importable from `apps.reference.config_models` remains importable with `is`-identical class objects. Enforced by the public-surface manifest test (Section 14).
- **F4. `create_aurora_config`**: public name and signature stable. Internal behavior may be tightened in Phase 0 (validation-required path), but the symbol is not removed.
- **F5. Back-compat aliases** (`AuroraTradingConfig`, `AuroraExposureConfig`): preserved verbatim until at least one full release after Phase 5 closes.

## 10. Phase map

| Phase | Title | Gate-dependency |
|-------|-------|-----------------|
| 0 | Mandatory cleanup / blocker removal | none (entry point) |
| 1 | Shared atoms + enums extraction | Phase 0 closed |
| 2 | Domain-by-domain extraction | Phase 1 closed |
| 3 | Strategy-by-strategy extraction | Phase 2 closed |
| 4 | System / trading / observability / ops extraction | Phase 3 closed |
| 5 | Final façade stabilization | Phase 4 closed |

Phases sequential at gate level. Inside Phases 2/3/4, **packages** (one per domain/strategy/area) are PR'd one at a time; no two packages from the same phase in flight simultaneously without journal-recorded approval.

## 11. Phase definitions

### Phase 0 — Mandatory cleanup / blocker removal

- **Objective**: remove all blockers that would corrupt later phases. Produce runtime-truth answers for U1–U4.
- **Scope**: resolve 4 duplicate class definitions; classify/freeze/delete `MeanReversionConfig`, `LegacyFeaturesLogConfig`, `RegimeModelConfig`-vs-`RegimeModelsConfig`; investigate `create_aurora_config` runtime usage; generate the **public-surface manifest** test.
- **Non-goals**: no class moves; no package extraction; no signature changes beyond F4.
- **Risks**: wrong canonical chosen (R3); production use of `model_construct` (R4); legacy class with hidden runtime reader (R6).
- **Preconditions**: roadmap and journal exist; baseline test suite green on `Phenix_v2`.
- **Surfaces likely affected**: lines 371, 1075, 1099, 1137, 1193, 1639, 3162, 3214, 3251, 3270, 3302 of `config_models.py`; new test under `tests/config/`; possibly tightening of `create_aurora_config`.
- **Validation requirements**:
  - V0.a: each previously-duplicated name resolves to exactly one class in `vars(config_models)`.
  - V0.b: full pytest pass on `Phenix_v2`.
  - V0.c: real-config load test against every YAML in `config/aurora/` succeeds.
  - V0.d: cross-validator negative-fixture suite (one per validator) raises with same `ValueError` substring as today.
  - V0.e: written runtime evidence answering U3 — recorded in journal.
- **Exit gate**: V0.a–V0.e green AND `[Phase 0]` journal entry recorded AND public-surface manifest committed.
- **Rollback strategy**: revert the single Phase 0 PR.
- **Journal requirements**: one `[Phase 0]` entry covering: which duplicate became canonical for each pair, what happened to each legacy class, what runtime evidence answered U3, public-surface manifest hash.

### Phase 1 — Shared atoms + enums extraction

- **Objective**: extract Bucket A (true leaves) into `apps/reference/config/shared/`; turn `config_models.py` into a re-exporter for those names.
- **Scope** (Bucket A): `InstrumentSpec`, `InstrumentPrecisionSpec`, `LeverageConfig`, `InstrumentExecutionConfig`, `InstrumentSizingConfig`, `SignalWeights`, `BarGatingConfig`, `BehaviorFsmConfig`, `SignalsConfig`, `DirectionStrengthScoringConfig`, `LiquidityGateConfig`, `PositionSizingConfig`, `KellyConfig`, `QosConfig`, `ROIExitConfig`, `PrecisionConfig`, `OperationalMode`, `ExecutionGateName`, `DangerZoneExitType`. Plus `_coerce_positive_decimal` (re-exported helper).
- **Non-goals**: no domain or strategy moves; no logic/signature change.
- **Risks**: missing re-export breaks 80+ call sites (R8); forward-ref order if a leaf accidentally imports a domain type (R1).
- **Preconditions**: Phase 0 closed; public-surface manifest test in place.
- **Surfaces likely affected**: new package `apps/reference/config/`, sub-package `shared/`; `apps/reference/config_models.py` (re-export block).
- **Validation**: V1.a manifest test (`is`-identical), V1.b pytest, V1.c import-cycle smoke, V1.d real-config load.
- **Exit gate**: V1.a–V1.d green AND `[Phase 1]` journal entry recorded.
- **Rollback strategy**: revert the Phase 1 PR.
- **Journal requirements**: one `[Phase 1]` entry listing extracted names, façade re-export strategy, deferred edge cases.

### Phase 2 — Domain-by-domain extraction

- **Objective**: extract each domain's models into `apps/reference/config/domains/<domain>.py`. One package per domain. One PR per package.
- **Scope per package** (Bucket B; safest order first):
  1. `objective_engine`
  2. `risk_management`
  3. `position_tracking`
  4. `shadow_telemetry`
  5. `ta_features`
  6. `feature_engineering` (uses canonical Phase-9 shield/scoring classes)
  7. `decision_making` (uses canonical Phase-9 shield/scoring classes)
  8. `execution_position` (largest; includes `PositionPolicySidecar*`, `ExecutionPositionRestoreArtifact*`, `ExecutionPositionStartupTruthArtifact*`)
  9. `_aggregator` (`DomainsConfig`, `DomainsDebugConfig`) — last package
- **Non-goals**: no field renames; no new defaults; no logic changes; no strategy moves; no `AuroraConfig` change.
- **Risks**: domain accidentally imports a strategy or root type (R1/R2); shadow-class field disappearance (R3) — should be impossible after Phase 0 V0.c, but reverify per package.
- **Preconditions**: Phase 1 closed; previous Phase 2 package closed and journaled.
- **Surfaces likely affected**: `apps/reference/config/domains/<domain>.py`; `config_models.py` re-exports.
- **Validation**: V2.a manifest, V2.b pytest, V2.c import-cycle, V2.d real-config load on representative subset, V2.e cross-validator negative fixtures still raise.
- **Exit gate per package**: V2.a–V2.e green AND `[Phase 2 / Pkg N]` journal entry.
- **Rollback strategy**: revert only the affected package's PR.
- **Journal requirements**: one entry per package: domain, classes moved, count of re-exports added, classes deliberately *not* moved, validation evidence.

### Phase 3 — Strategy-by-strategy extraction

- **Objective**: extract each strategy's models into `apps/reference/config/strategies/<strategy>.py`. One package per strategy.
- **Scope per package** (Bucket C; `aurora` last because heaviest cross-validator coupling):
  1. `mean_reversion` (excludes legacy `MeanReversionConfig` already handled in Phase 0)
  2. `md_amr`
  3. `llm_microstructure`
  4. `aurora`
  5. `common` (`StrategyObjective*`, `StrategiesArbitration*`, `StrategiesRegistryConfig`, `StrategiesConfig`) — last package
- **Non-goals**: no per-strategy or root validator changes.
- **Risks**: cross-validators on `AuroraConfig` use `getattr(self.strategies, "aurora", None)`; shape drift could let validators pass on wrong attributes (R7).
- **Preconditions**: Phase 2 closed.
- **Surfaces likely affected**: `apps/reference/config/strategies/<strategy>.py`; `config_models.py` re-exports.
- **Validation**: V3.a–V3.d as in Phase 2; V3.e cross-validator negative fixtures **explicitly** for every validator that mentions the strategy being moved.
- **Exit gate per package**: V3.a–V3.e green AND `[Phase 3 / Pkg N]` entry.
- **Rollback strategy**: per-package PR revert.
- **Journal requirements**: one entry per package; explicitly list which root validator was re-exercised by which negative fixture.

### Phase 4 — System / trading / observability / ops extraction

- **Objective**: extract Bucket D into `apps/reference/config/system/`. Packages grouped by horizontal concern.
- **Scope per package**:
  1. `system/observability.py`
  2. `system/ops.py`
  3. `system/market_data.py`
  4. `system/regime.py`
  5. `system/system_stress.py` (includes `STRESS_*` constants)
  6. `system/execution.py`
  7. `system/binance.py`
  8. `system/trading.py`
  9. `system/meta.py` — last package
- **Non-goals**: no `AuroraConfig` change; no removal of back-compat aliases.
- **Risks**: `STRESS_*` constants are de-facto-public; manifest must include them (R5/R8). `regime.yaml` is loaded directly elsewhere — any field reordering must be cosmetic-only.
- **Preconditions**: Phase 3 closed.
- **Surfaces likely affected**: `apps/reference/config/system/*.py`; `config_models.py` re-exports.
- **Validation**: V4.a–V4.d as Phase 2; V4.e full real-config load test.
- **Exit gate per package**: V4.a–V4.e green AND `[Phase 4 / Pkg N]` entry.
- **Rollback strategy**: per-package revert.
- **Journal requirements**: one entry per package; explicitly list any module-level constant moved.

### Phase 5 — Final façade stabilization

- **Objective**: bring `apps/reference/config_models.py` to its final shape — only `AuroraConfig`, the 7 cross-validators, `create_aurora_config`, back-compat aliases, `_coerce_positive_decimal`, and an explicit re-export block. Optionally introduce `apps/reference/config/__init__.py` as new preferred entry point (purely additive).
- **Scope**: reduce `config_models.py` to ~300–500 LOC; replace ad-hoc re-exports with `__all__`-driven explicit list reconciled against the public-surface manifest; add `apps/reference/config/README.md`.
- **Non-goals**: no removal of `apps.reference.config_models` import path; no removal of back-compat aliases; no enforcement of new entry point.
- **Risks**: drift between explicit `__all__` and what callers actually import (mitigated by manifest test).
- **Preconditions**: Phase 4 closed.
- **Surfaces likely affected**: `apps/reference/config_models.py` (final cleanup), `apps/reference/config/__init__.py` (new, optional), `apps/reference/config/README.md` (new).
- **Validation**: V5.a–V5.d as Phase 2; V5.e `__all__` is a strict superset of the Phase 0 manifest (no name dropped).
- **Exit gate**: V5.a–V5.e green AND `[Phase 5]` AND `[Initiative Closed]` entries recorded.
- **Rollback strategy**: revert Phase 5 PR; system reverts to "Phase 4 done" state, fully functional.
- **Journal requirements**: `[Phase 5]` entry plus `[Initiative Closed]` summary covering total LOC delta on `config_models.py`, count of new modules, deferred items.

## 12. Package strategy

- **One narrow package per PR**. Package = one directory move + corresponding façade re-exports + manifest reconciliation. Nothing else.
- **No mixed-purpose package**. PR mixing class move + field default fix + module rename is invalid; split it.
- **No implementation before previous package closure evidence**. Closure evidence = a journal entry with status `validated` and links to test runs.
- **No simultaneous in-flight packages from same phase** without explicit journal note.
- **Public-surface manifest test** is the gate test for every package, every phase, from Phase 1 onward.

## 13. Phase 0 — required deep-dive (non-skippable)

### 13.1 Duplicate class resolution (O1)

For each pair (`ContextShieldConfig`, `MemoryShieldConfig`, `DangerZoneShieldConfig`, `ScoringEngineConfig`):

1. Read both definitions in `config_models.py` (lines 1075/3251, 1099/3162, 1137/3214, 1193/3270).
2. Diff field sets and validators.
3. Grep `config/aurora/*.yaml` and `config/aurora/strategies/*.yaml` for every field present in only one of the two definitions.
4. Decision rule:
   - If only the *later* (Phase-9) definition has YAML-used fields → later wins; delete earlier.
   - If the *earlier* definition has any YAML-referenced field absent from the later → **stop**, file a sub-task. Fail closed.
5. Add a regression test asserting the canonical `model_fields` set.

### 13.2 Legacy / frozen surface classification

- `MeanReversionConfig` (line 371): grep `apps/`, `tools/`, `tests/` for runtime readers. Zero → delete; tests-only → freeze with `# FROZEN: replaced by MeanReversion1mStrategyConfig (Phase-0 audit)`.
- `LegacyFeaturesLogConfig` (line 3302): same procedure.
- `RegimeModelConfig` (1639) vs `RegimeModelsConfig` (1623): identify which `regime.yaml` loader uses; freeze the other.

### 13.3 `create_aurora_config` runtime truth investigation

- Trace every caller in `apps/`, `tools/`, `tests/`.
- Classify: (a) tests/migration only, (b) production startup, (c) ambiguous.
- If any (b): centralized invariants are nominal today. Either:
  - Switch the production caller to `AuroraConfig.model_validate(...)`, OR
  - Modify `create_aurora_config` to use `model_validate` by default and require explicit `unsafe: bool = False` opt-in for test-only (preserves F4 — public name and existing-positional-arg signature stay).
- Record chosen path and evidence in journal.

### 13.4 Validator-bypass risk closure

- Confirm by direct test that all 7 cross-validators run on a representative production-shaped config.
- Phase 0 PR adds (or reaffirms) one negative fixture per validator under `tests/config/` for use as the cross-validator regression suite.

## 14. Validation doctrine

Every package from Phase 1 onward must pass:

1. **Bit-identical public surface check** (manifest test): frozen list of every name currently exported by `apps.reference.config_models`. For each name, asserts same `__name__`, same `model_fields` set (Pydantic), and `is`-identity stable across the migration. New names added only by explicit roadmap update.
2. **Real YAML load check**: load each YAML under `config/aurora/` (plus a backtest-style and a system-stress-enabled fixture) into `AuroraConfig`. No `ValidationError`.
3. **Cross-validator negative-fixture suite**: one fixture per cross-validator on `AuroraConfig`. Each must raise `ValueError` with same substring as before. Introduced in Phase 0; used unchanged thereafter.
4. **Import-cycle smoke**: clean-process startup importing `apps.reference.config_models`, `apps.reference.contracts.runtime_regime_layers`, `apps.reference.telemetry.shadow_journal`, and the moved-package's new module path, in arbitrary order. No `ImportError`.
5. **No-fallback / static drift check**: scan comparing every field's required-vs-optional status before and after the move. Field that was `Field(...)` (required) before must remain required. New `default=` forbidden.
6. **Diff hygiene**: each PR's diff shows only file moves + re-exports + manifest reconciliation. Unrelated changes split.

## 15. Definition of DONE per phase

A phase is DONE only if **all** hold:

- All planned packages of the phase have landed on `Phenix_v2`.
- Each package has a `validated`-status entry in [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md).
- Full validation doctrine (Section 14) is green at the tip of the phase.
- Frozen boundaries (Section 9) unchanged.
- A phase-closure summary entry `[Phase N closed]` written: packages landed, manifest delta (added names, none removed), deferred items.

## 16. Global risks / unproven areas

| ID | Risk / unproven | Phase that resolves or contains it |
|----|-----------------|-------------------------------------|
| GR1 | Wrong duplicate chosen as canonical → silent field loss | Phase 0 (V0.a, runtime evidence) |
| GR2 | `create_aurora_config` bypasses validators in production | Phase 0 (Section 13.3) |
| GR3 | Façade re-export drops a public name → 80+ call sites break | Public-surface manifest (Phase 0 onward) |
| GR4 | Latent import cycle through `contracts/` or `telemetry/` | Import-cycle smoke (Phase 1 onward) |
| GR5 | Field default silently introduced during a move | Static drift check (Phase 2 onward) |
| GR6 | Legacy class resurrected as canonical during strategy split | Phase 0 freeze + Phase 3 review |
| GR7 | Cross-validator silently passes on shape-drifted leaf | Cross-validator negative fixtures (Phase 0 onward) |
| GR8 | Module-level constant (e.g. `STRESS_TRIGGER_KEYS`) forgotten in re-export | Manifest test must include constants, not just classes |

Unproven areas (must remain in journal until answered): U1–U5 from Section 6. Each closed only by explicit journal note citing evidence.

## 17. Recommended execution order

1. Approve this roadmap and freeze it as SSOT.
2. Initialize [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md).
3. Open and land Phase 0 PR. Record `[Phase 0]` entry. Verify all V0.* checks.
4. Open and land Phase 1 PR. Record `[Phase 1]` entry.
5. Open Phase 2 packages one at a time: `objective_engine` → `risk_management` → `position_tracking` → `shadow_telemetry` → `ta_features` → `feature_engineering` → `decision_making` → `execution_position` → `_aggregator`. Per-package entries; phase-closure entry.
6. Open Phase 3 packages one at a time: `mean_reversion` → `md_amr` → `llm_microstructure` → `aurora` → `common`. Per-package entries; phase-closure entry.
7. Open Phase 4 packages in the order in Section 11. Per-package entries; phase-closure entry.
8. Open and land Phase 5 PR. Record `[Phase 5]` and `[Initiative Closed]` entries.

## 18. Final roadmap verdict

> **Adopted.** This roadmap converts the audit's "blocked → partial split" verdict into a sequence of narrow, validation-gated packages. No package may begin without prior package closure evidence in [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md). Frozen boundaries (Section 9) and architectural laws (Section 8) are non-negotiable for the lifetime of this initiative. Implementation begins only after Phase 0 closes and is recorded as `validated`.
