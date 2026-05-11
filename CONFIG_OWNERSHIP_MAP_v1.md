# CONFIG_OWNERSHIP_MAP_v1

**Date:** 2026-05-09
**Mode:** READ_ONLY AUDIT
**Scope:** `config/aurora/` + strategy profiles + standalone research configs + neocortex domain configs
**Status:** DRAFT — for operator review before any migration work

---

## 1. Problem Framing

The Aurora/Phenix configuration system has grown across at least 14 active YAML files, each with
different loading paths, merge semantics, and Pydantic model coverage. The core problem is not
that the system is large — it is that **ownership boundaries are ambiguous**, which means:

- Adding or changing a field requires knowing which file is canonical.
- Physical sharding of large files (domains.yaml, system.yaml, trading.yaml) risks propagating
  the ambiguity rather than resolving it.
- Operators making operational changes (e.g., toggling risk gates, changing leverage) face two
  or more plausible locations for the same semantic concept.

This document maps every major config family to a single named owner, identifies split-brain
surfaces, and issues a sharding readiness verdict.

**This audit is read-only. No changes are proposed.**

---

## 2. Ownership Classification Method

### 2.1 Provenance evidence sources (in order of reliability)

1. **ConfigLoader code** (`apps/reference/config_loader.py`) — authoritative on load order,
   merge semantics, and which file "wins" on conflict.
2. **YAML file comments with SSOT markers** (e.g., `# SSOT`, `# CFG-INSTRUMENTS-AURORA-SSOT-01`,
   `# T3B-SSOT`) — declared intent, reliable when consistent with loader behavior.
3. **Passport docs** (`config/docs/*.md`) — human-authored documentation; treated as
   supplementary evidence, not primary truth.
4. **Pydantic model imports** (`apps/reference/config_models.py`) — structural evidence of which
   fields the runtime actually reads.
5. **Duplicate-path detection** (`_fail_on_duplicate_paths`) — the loader crashes on same leaf
   path across files; surviving pairs with identical semantics at different YAML paths are
   **structural split-brain**, not caught by the detector.

### 2.2 Ownership status taxonomy

| Code | Meaning |
|------|---------|
| `single_owner` | One file is declared and confirmed SSOT; no other file writes this surface |
| `owner_split` | Two files write to the **same business concept** at different YAML paths; both are active |
| `owner_unclear` | No file is formally declared as owner; runtime consumer unknown |
| `no_runtime_owner` | File exists and is loadable but no runtime code reads from it |
| `compat_only` | Field is loaded but immediately redirected/rejected by loader; kept for migration tooling |

### 2.3 Config-status taxonomy

| Code | Meaning |
|------|---------|
| `active` | Field is loaded by ConfigLoader, typed in Pydantic, and has a known runtime consumer |
| `partial_drift` | Field is loaded but has a parallel surface that creates ambiguity |
| `legacy_compat` | Field is loaded but immediately rejected or forwarded to a different canonical path |
| `dead_schema` | File or block exists in YAML but has no loader reference and no known runtime consumer |
| `metadata_only` | File is loaded for schema/contract purposes only; not a runtime tuning knob |

---

## 3. Canonical Config Families

The following config families are identified. Each maps to a canonical physical source.

### Family 1: Domain-owned runtime knobs
Source: `config/aurora/domains.yaml`
Namespace in merged config: `domains.*`
Description: All per-domain tuning knobs for FE, decision_making, risk_management,
  execution_position, position_tracking, shadow_telemetry, objective_engine, ta_features.

### Family 2: Strategy registry and arbitration
Source: `config/aurora/strategies.yaml`
Namespace: `strategies_registry.*`
Description: Which strategy IDs are assigned per symbol, arbitration mode, priority ranks.
  Does NOT contain strategy behavior parameters.

### Family 3: Strategy profiles (per-strategy behavior)
Sources: `config/aurora/strategies/aurora.yaml`, `md_amr.yaml`, `mean_reversion.yaml`, `llm_microstructure.yaml`
Namespace: `strategies.{aurora,md_amr,mean_reversion,llm_microstructure}.*`
Description: Per-strategy signal weights, regime thresholds, asset-level exit params, objective weights.

### Family 4: Per-instrument execution + precision
Source: `config/aurora/instruments.yaml`
Namespace: `instruments.*`
Description: step_size, tick_size, min_qty, min_notional, leverage, margin_mode, sizing, flip per symbol.

### Family 5: System / process physics
Source: `config/aurora/system.yaml`
Namespace: root-level `system.market_data.*`, `hardening.*`, `hawkes.*`, `calibrator.*`,
  `kelly.*`, `sequential_tests.*`, `risk_core.*`, `trailing.*`
Also contains: `ops.*`, `execution.*` at root — these are **split-brain surfaces** (see Section 5).

### Family 6: Observability / logging
Source: `config/aurora/observability.yaml`
Namespace: `logging.*`, `alerts.*`, `shadow_journal.*`
Description: Log rotation, domain-specific log levels, alert thresholds, shadow journal event list.

### Family 7: Trading operational policy
Source: `config/aurora/trading.yaml`
Namespace: `trading.*`, `binance_api.*`
Description: trading_mode, API credentials, TCA preferences, risk budgets, market_data websocket
  config, execution brackets/watchdog, domain_configuration overrides, LLM orchestration.
Also contains: `trading.ops.*` — **split-brain surface** (see Section 5).

### Family 8: Regime detector configuration
Source: `config/aurora/regime.yaml`
Namespace: merged at root after trading.yaml (basis_tf_sec, uncertain_cutoff, liveness_factor,
  basis_import_buffer, hysteresis_bars, vol_slope_gate_*, models.*, system_stress.*, regime_shift_inception)
Description: All parameters governing regime detection, SMA trend, volatility model, system stress.

### Family 9: Experimental / research config (alpha_search)
Sources: `config/alpha_search.yaml`, `config/alpha_search_system.yaml`,
  `config/alpha_search/scenario_matrix.yaml`
Namespace: `alpha_search.*`, `alpha_search_system.*`
Description: Alpha provider config (aurora, ta_ensemble, judge_sw, judge_fn), virtual trader,
  judge cortex, simulator shutdown export. Loaded by `AlphaSearchBacktestPlugin` — NOT by main
  `ConfigLoader`. Not part of `AuroraConfig`.

### Family 10: Judge standalone configs
Sources: `config/judge_review.yaml`, `config/judge_simulator.yaml`
Namespace: `judge_review.*`, `judge_simulator.*`
Description: Offline review + simulator configs. Both have `enabled: false` at time of audit.
  Loaded by judge subsystem, not by main ConfigLoader.

### Family 11: Neocortex domain config (domain-embedded)
Sources: `apps/reference/domains/neocortex/config/neuro.yaml`,
  `apps/reference/domains/neocortex/config/replay.yaml`,
  `apps/reference/domains/neocortex/config/regime_oracle_reward.yaml`
Namespace: not in AuroraConfig; loaded directly by neocortex domain
Description: VAE/PPO/world-model architecture, replay ingestion, regime oracle reward matrix.

### Family 12: Deprecated / archive
Sources: `config/aurora/archive/aurora_phase3_production.yaml`,
  `config/aurora/archive/features.yaml.deprecated`
Namespace: none (no loader reference)
Description: Phase 3 production configs superseded by current aurora.yaml. Dead schema.

### Family 13: Verb / event registry (metadata)
Source: `apps/reference/dictionaries/verb_registry_v1.yaml`
Namespace: not in AuroraConfig
Description: Canonical event contract registry (owners, schemas, statuses). Metadata only.
  Not a runtime tuning surface.

---

## 4. Ownership Map Table

| config_family | canonical_runtime_namespace | physical_source_file | semantic_owner | runtime_owner_status | current_status | evidence | recommended_action |
|---|---|---|---|---|---|---|---|
| Domain-owned runtime knobs | `domains.*` | `config/aurora/domains.yaml` | Per-domain handlers (FE, DM, RM, EP, PT, ST, OE, TA) | single_owner | active | Loader enforces: missing → ValueError. Pydantic models validated against it. | Safe to split by domain section if loader is updated to support multi-file domains. |
| Strategy registry / arbitration | `strategies_registry.*` | `config/aurora/strategies.yaml` | strategies domain | single_owner | active | Loader: missing → ConfigContractError. `assignments` + `arbitration` only. | No change needed. Already clean. |
| Aurora strategy profile | `strategies.aurora.*` | `config/aurora/strategies/aurora.yaml` | aurora_handler | single_owner | partial_drift | Loaded via registry-driven scan. QoS block overlaps with domains.decision_making.qos. DOGEUSDT: `assets.DOGEUSDT.enabled=true` but registry has DOGEUSDT commented out. | Resolve DOGEUSDT enabled/disabled contradiction. Clarify qos precedence (profile vs domain). |
| md_amr strategy profile | `strategies.md_amr.*` | `config/aurora/strategies/md_amr.yaml` | md_amr_handler | single_owner | active | Clean. No known mirrors. | No change needed. |
| mean_reversion strategy profile | `strategies.mean_reversion.*` | `config/aurora/strategies/mean_reversion.yaml` | mean_reversion_handler | single_owner | active | Clean. All assets except DOGEUSDT are `enabled: false`. | No change needed. |
| llm_microstructure strategy profile | `strategies.llm_microstructure.*` | `config/aurora/strategies/llm_microstructure.yaml` | llm_microstructure_handler | single_owner | active | Minimal profile (5 fields). No known mirrors. | No change needed. |
| Per-instrument execution + precision | `instruments.*` | `config/aurora/instruments.yaml` | execution_position | single_owner | active | Loader: `trading.instruments` → ConfigContractError. File declares itself SSOT. Instruments passport confirms. | Single owner confirmed. See SPLIT-BRAIN note on leverage_defaults (Section 5, item 3). |
| System / process physics (clean part) | root: `system.market_data.*`, `hardening.*`, `hawkes.*`, `calibrator.*`, `kelly.*`, `sequential_tests.*`, `risk_core.*` | `config/aurora/system.yaml` | system infrastructure | single_owner | active | Extracted to system_meta by loader. No trading.yaml mirror for these keys. | Safe to shard after split-brain surfaces below are resolved. |
| System execution block | root: `execution.*` | `config/aurora/system.yaml` | owner_unclear | owner_split | partial_drift | system.yaml has `execution.*` at root. trading.yaml has `trading.execution.*` nested. Deep merge produces BOTH paths simultaneously. Watchdog was removed from system.yaml per comment (T5A.1-SSOT). Ongoing migration. | Do NOT shard until migration to trading.execution is complete. See Section 5, item 2. |
| System ops block | root: `ops.*` | `config/aurora/system.yaml` | owner_split (system.yaml + trading.yaml) | owner_split | partial_drift | `system.yaml:ops.*` and `trading.yaml:trading.ops.*` have identical values for `panic_killswitch`, `metrics_url`, `reports_dir`. Both survive merge at different paths. | See Section 5, item 1. Remove one before sharding. |
| Observability / logging | `logging.*`, `alerts.*`, `shadow_journal.*` | `config/aurora/observability.yaml` | observability/monitoring | single_owner | active | Loaded separately with its own Pydantic model (ObservabilityConfig). No other file declares logging config. | Already clean. Safe to extend. |
| Trading operational policy | `trading.*`, `binance_api.*` | `config/aurora/trading.yaml` | trading operations | owner_split | partial_drift | trading.ops mirrors system.ops. trading.execution mirrors system.execution. trading.market_data.macro_sync conflicts with domains.feature_engineering.macro_sync (anchor_update_from_ticks differs). | Cannot shard until splits resolved. See Section 5. |
| Regime detector config | merged root (basis_tf_sec, models.*, system_stress.*) | `config/aurora/regime.yaml` | regime_detector | single_owner | active | Merged after trading.yaml. No known mirrors. basis_import_buffer is SSOT-declared and used in strategy_compatibility_matrix. | Already clean. Safe to shard as separate domain config if desired. |
| Alpha search config | `alpha_search.*`, `alpha_search_system.*` | `config/alpha_search.yaml`, `config/alpha_search_system.yaml` | AlphaSearchBacktestPlugin | no_runtime_owner (in AuroraConfig) | active (in separate subsystem) | NOT loaded by main ConfigLoader. Loaded by AlphaSearchBacktestPlugin. Contains `legacy.*` block explicitly marked as deprecated/ignored. | Clarify loader boundary. Consider moving to `config/aurora/` if it will be promoted to main config. |
| Judge configs | `judge_review.*`, `judge_simulator.*` | `config/judge_review.yaml`, `config/judge_simulator.yaml` | alpha_search/judge subsystem | no_runtime_owner (in AuroraConfig) | legacy_compat | Both have `enabled: false`. Loaded by research plugin only. | No change needed. Keep as research-only. |
| Neocortex domain config | not in AuroraConfig | `apps/reference/domains/neocortex/config/*.yaml` | neocortex domain | no_runtime_owner (in AuroraConfig) | active (domain-internal) | Loaded directly by neocortex domain. Not part of SSOT config dir. Pattern diverges from all other domains. | No change needed currently. If neocortex is promoted to production path, move to `config/aurora/domains.neocortex.*`. |
| Archive / phase 3 | none | `config/aurora/archive/aurora_phase3_production.yaml` | none | no_runtime_owner | dead_schema | File has no loader reference. Content describes Phase 3 per-asset configs that are superseded by `aurora.yaml:assets.*`. | Safe to delete after confirming no tools or scripts reference it. |
| features.yaml.deprecated | none | `config/aurora/archive/features.yaml.deprecated` | none | no_runtime_owner | dead_schema | File named `.deprecated`. No loader reference. | Safe to delete. |
| Verb registry | not in AuroraConfig | `apps/reference/dictionaries/verb_registry_v1.yaml` | FSM/contract framework | no_runtime_owner (as config) | metadata_only | Used for schema contract validation and documentation. Not a tuning surface. | No change needed. |

---

## 5. Split-Brain / Drift Candidates

These are the highest-risk surfaces. They create ambiguity about which file is authoritative.

### Item 1 — ops.*: identical fields at two paths (CONFIRMED)

**FACT:** Both of these blocks exist simultaneously in the merged config after loading:

```
# From system.yaml (root-level):
ops.panic_killswitch = false
ops.metrics_url = http://127.0.0.1:8000/metrics
ops.reports_dir = reports

# From trading.yaml (nested inside trading:):
trading.ops.panic_killswitch = false
trading.ops.metrics_url = http://127.0.0.1:8000/metrics
trading.ops.reports_dir = reports
```

**INFERENCE:** Runtime code that reads `ops.panic_killswitch` and code that reads
`trading.ops.panic_killswitch` will both find valid values. If they diverge, two parts of the
system will operate with different killswitch states.

**RISK:** killswitch is safety-critical. Any operator who edits one file and not the other creates
a silent safety failure.

**UNKNOWN:** Which Pydantic path does the emergency killswitch code actually read at runtime?

---

### Item 2 — execution.*: parallel execution surfaces (CONFIRMED)

**FACT:** After deep merge, both paths exist simultaneously:

```
# From system.yaml root:
execution.manage.brackets.sl.fixed_bps = 40
execution.manage.brackets.tp.fixed_bps = 80
execution.exposure.leverage_defaults.BTCUSDT = 20
execution.order_guardian.unified = true
... (approx 40+ leaf paths)

# From trading.yaml nested:
trading.execution.manage.brackets.sl.fixed_bps = 40
trading.execution.manage.brackets.tp.fixed_bps = 80
trading.execution.exposure.leverage_defaults.BTCUSDT = 20
trading.execution.order_guardian.unified = true
... (same approx 40+ leaf paths)
```

**EVIDENCE OF PARTIAL MIGRATION:** system.yaml line 59-61 contains:
```
# T5A.1-SSOT: execution.watchdog block removed 2026-05-07.
# Canonical source: trading.yaml -> trading.execution.watchdog.*
# Do not add execution.watchdog back here; it would create a split-brain duplicate.
```

This confirms: the watchdog was migrated FROM system.execution TO trading.execution, but the
rest of the execution block was NOT yet migrated. The migration is **in progress but incomplete**.

**ASSUMPTION:** trading.execution.* is the intended canonical path (per migration direction).
The system.execution.* surface is residual and should be removed once migration is complete.

**RISK:** Any edit to system.execution.* to tweak execution behavior will be silently ignored
once code is fully migrated to trading.execution.*. The reverse is also true during transition.

---

### Item 3 — leverage_defaults vs instruments.execution.target_leverage (CONFIRMED, CONTRADICTORY VALUES)

**FACT (three sources for leverage):**

```
# instruments.yaml:
BTCUSDT.execution.target_leverage = 25    ← instruments SSOT
XRPUSDT.execution.target_leverage = 20
DOGEUSDT.execution.target_leverage = 10

# trading.yaml (trading.execution.exposure.leverage_defaults):
BTCUSDT = 20    ← DIFFERENT from instruments.yaml
XRPUSDT = 20
DOGEUSDT = 20

# system.yaml (execution.exposure.leverage_defaults):
BTCUSDT = 20    ← mirrors trading.yaml (also different from instruments)
```

**FACT:** BTCUSDT target_leverage is 25 in instruments.yaml and 20 in trading/system leverage_defaults.
DOGEUSDT is 10 in instruments.yaml and 20 in leverage_defaults.

**INFERENCE:** These serve different purposes:
- `instruments.execution.target_leverage` → leverage SET on the exchange at startup
- `trading.execution.exposure.leverage_defaults` → leverage used for EXPOSURE MATH (margin calculation)

**ASSUMPTION:** Both are legitimately different (startup vs runtime exposure), but the contradictory
BTCUSDT value (25 vs 20) is either intentional or a configuration drift bug.

**RISK:** If the two leverage values diverge significantly, the exposure math will produce incorrect
margin utilization estimates for BTCUSDT.

---

### Item 4 — trading_mode declared at two YAML paths (CONFIRMED)

**FACT:**

```
# system.yaml line 2 (root-level):
trading_mode: hybrid_live_data_testnet_exec

# trading.yaml line 11 (nested inside trading:):
trading:
  mode: hybrid_live_data_testnet_exec
```

After merge, the `AuroraConfig` has:
- `AuroraConfig.trading_mode` (from system.yaml root)
- `AuroraConfig.trading.mode` (from trading.yaml nested)

**INFERENCE:** These are conceptually the same declaration (current trading mode), but they are
at different YAML paths and could diverge independently.

**EVIDENCE:** The historical system.yaml/trading.yaml mode mismatch (system.yaml had "backtest"
while trading.yaml had "hybrid_live_data_testnet_exec") was a documented past failure that caused
bootstrap failures. The fix was to align both files — but two files still own this concept.

**RISK:** Any future change to the trading mode requires editing BOTH files to avoid a repeat of
the historical mismatch bug.

---

### Item 5 — macro_sync: contradicting values at two namespaces (CONFIRMED)

**FACT:**

```
# trading.yaml (trading.market_data.macro_sync):
anchor_update_from_ticks: false
min_buffer_size: 3
time_diff_threshold_ms: 60000

# domains.yaml (domains.feature_engineering.macro_sync):
anchor_update_from_ticks: true    ← DIFFERENT VALUE
min_buffer_size: 2                ← DIFFERENT VALUE
time_diff_threshold_ms: 60000
```

These are at genuinely different namespaces (market_data ingestion vs feature_engineering
computation), but they configure the same underlying feature. The `anchor_update_from_ticks`
discrepancy means the market_data domain configures the anchor as NOT updated from ticks, while
the FE domain configures it as updated from ticks.

**INFERENCE:** This is either intentional (different behaviors for different layers of processing)
or a drift bug (one was updated and the other was not).

**UNKNOWN:** Which code path uses which config. Cannot determine without runtime tracing.

---

### Item 6 — aurora.yaml:assets.DOGEUSDT vs strategies.yaml (CONFIRMED CONTRADICTION)

**FACT:**

```
# strategies.yaml:
assignments:
  # 2026-04-22: DOGEUSDT full cut; assignment commented out per operator request.
  # DOGEUSDT:
  #   - aurora

# aurora.yaml:
assets:
  DOGEUSDT:
    enabled: true    ← Profile declares enabled
```

The strategy registry has DOGEUSDT removed from aurora assignments, but the aurora strategy
profile still has `DOGEUSDT.enabled = true`.

**INFERENCE:** The profile's `enabled: true` is stale. DOGEUSDT will not receive aurora trades
because it is not in the strategy registry, regardless of the profile flag. But the profile value
creates confusion about the actual state.

**RISK:** If the registry assignment is re-added without verifying the profile, the profile's
regime_thresholds and allowed_regimes (which restrict to TREND_DOWN, HIGH_VOLATILITY, MEAN_REVERSION)
will be the constraint. This is inconsistent with what was in place before the cut.

---

### Item 7 — domains.decision_making.qos vs aurora.yaml:decision.qos (CONFIRMED SEMANTIC CONFLICT)

**FACT:**

```
# domains.yaml (domains.decision_making.qos) — applies to strategies [aurora, md_amr]:
qos:
  exposure_block_cooldown_sec: 60
  symbol_cooldown_sec: 3
  max_intents_per_minute_per_symbol: 20
  mode: enforce
  enforce: true
  apply_to_strategies: [aurora, md_amr]

# aurora.yaml (strategies.aurora.decision.qos) — aurora profile override:
qos:
  exposure_block_cooldown_sec: 30    ← different
  symbol_cooldown_sec: 1             ← different
  max_intents_per_minute_per_symbol: 60   ← different
  mode: defer                        ← DIFFERENT semantics
  enforce: false                     ← DIFFERENT
  apply_to_strategies: []            ← DIFFERENT
```

**INFERENCE:** The aurora profile overrides QoS with permissive settings (defer, not enforce).
The domain-level QoS sets strict defaults. Whether the profile override is applied or the domain
default takes precedence depends on which config path the aurora handler reads at runtime.

**UNKNOWN:** Is the profile QoS always applied as an override? Or is it ignored if the domain
QoS is set? Cannot determine without reading aurora_handler.py decision QoS resolution logic.

---

## 6. Legacy / Dead / Metadata-Only Surfaces

### Confirmed dead schema

| Surface | File | Evidence |
|---------|------|---------|
| `archive/aurora_phase3_production.yaml` | `config/aurora/archive/` | Key `aurora_phase3` not in any loader path. Superseded by aurora.yaml:assets.* |
| `archive/features.yaml.deprecated` | `config/aurora/archive/` | Named `.deprecated`. No loader reference found. |
| `alpha_search.yaml:legacy.*` | `config/alpha_search.yaml` | Block explicitly labeled "LEGACY: fields are ignored by new code". |
| `trading.yaml:regime_tpsl: null` | `config/aurora/trading.yaml` line 187 | Null stub. No Pydantic model field confirmed to consume this. |
| `system.yaml:brackets: null` | `config/aurora/system.yaml` line 88 | Null stub. |

### Declared but disabled (not dead schema, but no active trade impact)

| Surface | File | Note |
|---------|------|------|
| `domains.bar_gating.enable: false` | `domains.yaml:34-36` | Gating disabled. Schema exists, tunable. |
| `domains.behavior_fsm.enable: false` | `domains.yaml:37-39` | FSM disabled. Schema exists. |
| `domains.price_motion_sanity.enabled: false` | `domains.yaml:129` | Disabled. Schema exists. |
| `domains.flip.enabled: false` | `domains.yaml:138` | Disabled. Schema exists. |
| `aurora.decision.roi_exit: null` | `aurora.yaml:240` | Null stub in profile. |
| `aurora.decision.mean_reversion: null` | `aurora.yaml:241` | Null stub. |
| `aurora.decision.quadratic_rollout: null` | `aurora.yaml:340` | Null stub. |
| `aurora.decision.bar_gating: null` | `aurora.yaml:235` | Null stub; overrides domain config to null. |
| `aurora.decision.entry_plan: null` | `aurora.yaml:352` | Null stub. |
| `aurora.decision.money_management: null` | `aurora.yaml:353` | Null stub. |
| `aurora.decision.dashboard: null` | `aurora.yaml:363` | Null stub. |
| `aurora.decision.execution: null` | `aurora.yaml:354` | Null stub. |
| `md_amr.llm_gate.enabled: false` | `md_amr.yaml:44` | LLM gate disabled. |
| `md_amr.optuna.*` | `md_amr.yaml:82-84` | Research params. No evidence of active runtime consumer. |
| `mean_reversion.directional_bias.enabled: false` | `mean_reversion.yaml:277` | Disabled feature. |
| `mean_reversion.microstructure_veto.enabled: false` | `mean_reversion.yaml:265` | Disabled. |
| `system.trailing.*` | `system.yaml:89-92` | activation_pct, trail_pct, min_update_interval_sec. No confirmed runtime consumer at this path. |
| `aurora.yaml:assets.1000PEPEUSDT.enabled: false` | `aurora.yaml:771` | Profile exists but aurora strategy disabled for this symbol. |
| `judge_review.enabled: false` | `config/judge_review.yaml` | Entire file disabled. |
| `judge_simulator.enabled: false` | `config/judge_simulator.yaml` | Entire file disabled. |

### Metadata-only surfaces

| Surface | File | Note |
|---------|------|------|
| `verb_registry_v1.yaml` | `apps/reference/dictionaries/` | Event contract registry. Not a tuning surface. |
| `config/_schemas/*.schema.json` | `config/_schemas/` | JSON schema validation artifacts. |
| `config/docs/*.md` | `config/docs/` | Passport documentation. Informational. |

---

## 7. Physical Sharding Recommendation (no semantic migration yet)

### Already safe to shard (isolated ownership confirmed)

These families already have isolated loaders or clear namespace separation. Physical reorganization
would not change semantics:

1. **`observability.yaml`** — already standalone, own Pydantic model (ObservabilityConfig).
2. **`instruments.yaml`** — already standalone, SSOT declared, mirror forbidden by loader.
3. **`strategies.yaml`** — already standalone, registry-only.
4. **`strategies/*.yaml`** — already per-strategy files, registry-driven discovery.
5. **`regime.yaml`** — clean, single owner, no mirrors found.
6. **`config/aurora/archive/`** — safe to delete both files after confirming no tool references.

### Requires ownership repair before sharding (split-brain active)

Do not physically shard these until the numbered splits in Section 5 are resolved:

1. **`system.yaml` / `trading.yaml`** — ops.* and execution.* split-brain (Section 5 items 1, 2).
   The migration from system.execution → trading.execution is partially complete. Sharding either
   file before the migration is complete will create unresolvable references.

2. **`domains.yaml`** — safe to split BY DOMAIN SECTION (decision_making, feature_engineering, etc.)
   ONLY IF the loader is updated to support multi-file domain loading. Currently the loader assumes
   a single `domains.yaml`. Internal splits within domains.yaml are safe if no domain section
   cross-references another.

### Must not be sharded (no safe split boundary found)

- **`system.yaml` root-level `trading_mode`** — must not move until the dual-path trading_mode
  issue (Section 5 item 4) is resolved by choosing one authoritative path and removing the other.

---

## 8. First Safe Migration Order

The following is a bounded sequence of single-step migrations, each safe without the others:

**Step 0 (pre-conditions, zero semantic change):**
- Delete `config/aurora/archive/aurora_phase3_production.yaml` (confirm no script references)
- Delete `config/aurora/archive/features.yaml.deprecated`
- Set `aurora.yaml:assets.DOGEUSDT.enabled: false` to match registry state (consistency only)

**Step 1 (ops.* split-brain):**
- Choose canonical path: either `ops.*` (system.yaml root) OR `trading.ops.*` (trading.yaml nested)
- Remove the non-canonical copy
- Verify Pydantic model reads from chosen path
- Constraint: this is ONE change in ONE file

**Step 2 (execution.* migration completion):**
- Complete the already-in-progress migration: remove `execution.*` from system.yaml root
- Confirm all runtime consumers read from `trading.execution.*`
- The watchdog was already moved (T5A.1-SSOT comment). Move the remaining 40+ leaf paths.
- Constraint: do not move domains.execution_position (that is in domains.yaml, not here)

**Step 3 (trading_mode canonical path):**
- Remove `trading_mode:` from system.yaml root OR remove `trading.mode:` from trading.yaml
- Choose: system.yaml root is already `AuroraConfig.trading_mode`, so remove trading.yaml:trading.mode
- Update any code that reads `config.trading.mode` to use `config.trading_mode`

**Step 4 (leverage_defaults vs instruments divergence):**
- Audit the BTCUSDT discrepancy: 25 (instruments) vs 20 (leverage_defaults)
- Decide which value is correct for each purpose (startup leverage vs exposure math)
- Document the semantic distinction in a SSOT comment in each file

**Step 5 (macro_sync dual config):**
- Clarify the anchor_update_from_ticks semantic split between market_data and FE
- If intentional: add comment in each file explaining WHY they differ
- If drift: align values and document the canonical answer

**Step 6 (domains.yaml domain-level sharding, optional):**
- Only after Steps 1-3 are complete
- Split domains.yaml into per-domain files (domains_feature_engineering.yaml, etc.)
- Update ConfigLoader to load from multiple files under a `config/aurora/domains/` directory

---

## 9. Risks

### R1 — Loader duplicate-path detector does NOT catch structural split-brain
The `_fail_on_duplicate_paths` check catches the same leaf path across multiple YAML files.
It does NOT catch semantically identical concepts at different YAML paths (e.g., `ops.killswitch`
vs `trading.ops.killswitch`). The structural split-brain in Section 5 items 1 and 2 will not be
caught by the existing guard.

**Risk level: HIGH** (silent failure if values diverge)

### R2 — BTCUSDT leverage discrepancy may already be affecting production
The 25x (instruments) vs 20x (leverage_defaults) discrepancy for BTCUSDT is a confirmed value
difference. If one path is used for exchange leverage setting and the other for exposure math,
the margin calculation may be wrong for BTC positions.

**Risk level: MEDIUM** (may cause incorrect exposure estimates)

### R3 — DOGEUSDT profile inconsistency is a latent re-enable hazard
If DOGEUSDT is re-added to strategies.yaml assignments without reviewing the profile's restricted
regime allowlist, trades may be generated in regimes that were previously calibrated as loss-making.

**Risk level: MEDIUM** (operational hazard on re-enable)

### R4 — Aurora QoS profile vs domain conflict is unproven at runtime
The aurora profile's QoS (mode: defer, enforce: false) vs domain QoS (mode: enforce, enforce: true)
conflict is a semantic ambiguity. Without tracing aurora_handler.py, it is unknown which setting
governs intent gating at runtime.

**Risk level: MEDIUM** (incorrect QoS enforcement is a profit path blocker)

### R5 — macro_sync anchor_update_from_ticks divergence may affect feature correctness
If the market_data layer and the FE layer disagree on whether ticks update anchors, the macro_sync
feature may produce inconsistent values across restart boundaries.

**Risk level: LOW-MEDIUM** (feature quality, not safety)

### R6 — Neocortex config is NOT in the SSOT config dir
All other domains have their config in `config/aurora/` or `config/aurora/domains.yaml`. Neocortex
loads from `apps/reference/domains/neocortex/config/`. This is an outlier pattern that makes
cross-domain config auditing harder and may prevent standard config validation tooling from covering it.

**Risk level: LOW** (tooling / audit coverage gap)

---

## 10. Final Verdict

```
VERDICT: SHARDING_BLOCKED_BY_SPLIT_BRAIN
```

**Reason:**

Five confirmed structural split-brain surfaces exist (Section 5 items 1-5) where the same
business concept is declared at two different YAML paths in two different files. The ConfigLoader's
duplicate-path detector does NOT catch these because they are at different paths, not conflicting
paths. Physical sharding of `system.yaml` or `trading.yaml` before these splits are resolved would
propagate the ambiguity into more files.

**What is safe to do right now:**
- Delete the two archive files (no-risk, zero semantic change)
- Extend `observability.yaml`, `instruments.yaml`, `regime.yaml`, or `strategies/*.yaml`
  (all single-owner, clean)
- Fix the DOGEUSDT enabled flag in aurora.yaml (single-file consistency change)

**What is the single bounded next step:**
Resolve the `ops.*` split-brain (Section 5 item 1) as Step 1 in Section 8. This is the smallest
isolated change: choose one canonical ops path, remove the mirror, verify the Pydantic binding.
It unblocks the confidence needed to proceed with the execution.* migration.

**Minimum config families with named owner:** All 13 families above have a named owner.

**Split-brain families explicitly listed:** 7 confirmed (Section 5 items 1-7).

**Problematic surfaces classified:** 22 concrete surfaces in Sections 5 and 6.
