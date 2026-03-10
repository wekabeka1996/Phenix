# Domains YAML Field Support Audit — v2

**Date:** 2026-03-10  
**Branch baseline:** `stable_11_11`  
**Current HEAD:** working branch  
**Config SSOT:** `config/aurora/domains.yaml`

---

## Scope

Audit of fields that existed in `stable_11_11`'s `domains.yaml` but are candidates for removal or migration in the current branch. Groups audited:

- `execution_position.bracket_health_check.*`
- `execution_position.pending_entry_ttl.advanced_stale_cancel.*`
- `execution_position.pending_entry_ttl.supersede_reprice_guard.*`
- `execution_position.quiet_hours.*`
- `feature_engineering.absorption.dp_cap_pct`
- `feature_engineering.bar_ta.*`
- `feature_engineering.legacy_features_log.*`
- `shadow_telemetry.*`

---

## Method

Evidence collected across three independent axes:

1. **Code references exist** — any Python file in the repo reads or names the field (runtime modules, tests, tools).
2. **In current `DomainsConfig` schema** — the field is declared in a Pydantic model that is part of the `DomainsConfig` → `AuroraConfig` chain (validated with `extra='forbid'`).
3. **In current `domains.yaml` SSOT** — the field is present in `config/aurora/domains.yaml` on the current branch HEAD.

> **Critical distinction**: a field can have code references (axis 1) without being in the config schema (axis 2). It can also be in the schema without being in the YAML (axis 3). Only fields that are true in **all three axes** are fully supported end-to-end.

---

## Runtime Config Loading Path

```
ConfigLoader.load_config()
    → _load_yaml("domains.yaml")                        # raw dict
    → AuroraConfig.model_validate(merged_config)        # Pydantic extra='forbid'
          └─ domains: DomainsConfig (extra='forbid')
                ├─ debug
                ├─ decision_making
                ├─ feature_engineering
                ├─ risk_management
                ├─ position_tracking
                └─ execution_position: ExecutionPositionDomainConfig
                   # shadow_telemetry is NOT a field of DomainsConfig
```

**`DomainsConfig`** is defined at `config_models.py:3094` with `extra='forbid'` and has exactly these top-level sub-models:
`debug`, `decision_making`, `feature_engineering`, `risk_management`, `position_tracking`, `execution_position`.

**`shadow_telemetry` is NOT a field of `DomainsConfig`.** The shadow_telemetry service accesses config via `getattr(getattr(config, "domains", None), "shadow_telemetry", None)` — this is a defensive getattr, not a validated schema field. If `domains.shadow_telemetry` were present in the YAML, Pydantic's `extra='forbid'` would reject the entire config at startup with `ValidationError`.

---

## Summary Matrix

> Legend: ✅ Yes | ❌ No | ⚠️ Partial/Tool-only

| Field | Code refs exist | In `DomainsConfig` schema | In `domains.yaml` SSOT |
|---|:---:|:---:|:---:|
| **execution_position.bracket_health_check** | ❌ | ❌ | ❌ |
| execution_position.bracket_health_check.enabled | ❌ | ❌ | ❌ |
| execution_position.bracket_health_check.grace_period_ms | ❌ | ❌ | ❌ |
| execution_position.bracket_health_check.interval_sec | ❌ | ❌ | ❌ |
| execution_position.bracket_health_check.max_placements_per_cycle | ❌ | ❌ | ❌ |
| **execution_position.pending_entry_ttl.advanced_stale_cancel** | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.enabled | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.drift_away.atr_mult | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.drift_away.mode | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.may_cancel_regimes.BUY[] | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.may_cancel_regimes.SELL[] | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.min_age_before_cancel_sec | ⚠️ tool | ❌ | ❌ |
| advanced_stale_cancel.never_cancel_regimes[] | ⚠️ tool | ❌ | ❌ |
| **execution_position.pending_entry_ttl.supersede_reprice_guard** | ❌ | ❌ | ❌ |
| supersede_reprice_guard.enabled | ❌ | ❌ | ❌ |
| supersede_reprice_guard.enforce | ❌ | ❌ | ❌ |
| supersede_reprice_guard.min_price_improvement_atr_mult | ❌ | ❌ | ❌ |
| supersede_reprice_guard.min_price_improvement_bps | ❌ | ❌ | ❌ |
| **execution_position.quiet_hours** | ⚠️ ops path | ❌ | ❌ |
| execution_position.quiet_hours.enabled | ❌ | ❌ | ❌ |
| execution_position.quiet_hours.windows[] | ❌ | ❌ | ❌ |
| **feature_engineering.absorption.dp_cap_pct** (old path) | ❌ | ❌ | ❌ |
| feature_engineering.absorption.proxy.dp_cap_pct (new path) | ✅ | ✅ | ✅ |
| **feature_engineering.bar_ta** | ❌ | ❌ | ❌ |
| feature_engineering.bar_ta.bb_num_std | ❌ | ❌ | ❌ |
| feature_engineering.bar_ta.bb_window | ❌ | ❌ | ❌ |
| feature_engineering.bar_ta.rsi_period | ❌ | ❌ | ❌ |
| feature_engineering.bar_ta.stoch_d_period | ❌ | ❌ | ❌ |
| feature_engineering.bar_ta.stoch_k_period | ❌ | ❌ | ❌ |
| **feature_engineering.legacy_features_log** | ❌ | ❌ | ❌ |
| feature_engineering.legacy_features_log.mode | ❌ | ❌ | ❌ |
| feature_engineering.legacy_features_log.sample_every_n | ❌ | ❌ | ❌ |
| **shadow_telemetry** (top-level block) | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.enabled | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.enabled | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.auth_mode | ❌ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.host | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.port | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.tls | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.consequential | ⚠️ openapi | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.enabled | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.idempotency_ttl_sec | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.intents_endpoint | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.max_body_kb | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.rate_limit_per_min | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.require_snapshot_ref | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.api.write.symbol_allowlist[] | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.egress_to_main.ipc_commands_endpoint | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.egress_to_main.mode | ❌ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.egress_to_main.overflow_policy | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.egress_to_main.queue_maxsize | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.ingest.allowlist_events[] | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.ingest.ipc_endpoint | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.ingest.overflow_policy | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.ingest.queue_maxsize | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.ingest.source | ❌ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.required_for_mode | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.snapshot.tf_policy.bar_snapshots_enabled | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.snapshot.tf_policy.min_tf_sec_for_full | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.snapshot.tf_policy.tick_sample_every_n | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.snapshot.tf_policy.tick_snapshots_mode | ✅ runtime | ❌ schema | ❌ yaml |
| shadow_telemetry.snapshot.trigger_event | ✅ runtime | ❌ schema | ❌ yaml |

---

## Detailed Findings by Block

---

### `execution_position.bracket_health_check`

**All three axes: ❌**

Zero occurrences in any Python, YAML, or JSON file. Completely removed from runtime, schema, and config SSOT.

**What replaced it:** `execution_position.guardian.*` — modeled as `GuardianConfig` in `config_models.py:3000`, present in `domains.yaml:547–558`, consumed by `order_guardian.py`. The guardian handles orphan bracket reconciliation but has different semantics (no placement-rate throttle via `max_placements_per_cycle`).

---

### `execution_position.pending_entry_ttl.advanced_stale_cancel`

**Code refs: ⚠️ (tool only) | Schema: ❌ | YAML: ❌**

Field names appear only in `tools/log_forensics_cancel_audit.py:1600–1603` as string labels in a forensic report-generation function. That tool is not part of the runtime config path.

`PendingEntryTTLConfig` (`config_models.py:2810`) has these fields:
`enabled`, `ttl_by_tf_sec`, `reject_unknown_tf`, `cancel_on_regime_change`, `regime_change_cancel_mode`, `cancel_on_supersede`, `cancel_on_panic`, `supersede_cancel_timeout_sec`.

No `advanced_stale_cancel` sub-config exists in the schema. Runtime consumers (`entry_manager.py:147`, `open_executor.py:192`, `event_handlers.py:64`) access `pending_entry_ttl` but never any `advanced_stale_cancel` sub-field.

---

### `execution_position.pending_entry_ttl.supersede_reprice_guard`

**All three axes: ❌**

Zero occurrences repo-wide. No schema, no YAML, no code references.

---

### `execution_position.quiet_hours`

**Code refs: ⚠️ (different path) | Schema: ❌ | YAML: ❌**

The quiet-hours concept is alive in the system, but it lives in `ops.quiet_hours_utc` (a flat `List[str]` of UTC time windows), **not** in `domains.execution_position.quiet_hours`. The domain path never existed in the current schema; `ExecutionPositionDomainConfig` (`config_models.py:3029`) has no `quiet_hours` field.

Runtime tests that exercise quiet-hours: `tests/integration/test_panic_killswitch.py:29,116`, `tests/integration/test_panic_killswitch_simple.py:105,115` — all access `config.ops.quiet_hours_utc`.

**Migration note:** If you wish to re-introduce quiet-hours for execution specifically, it must go into `OpsConfig.quiet_hours_utc` (already exists), not into `DomainsConfig`.

---

### `feature_engineering.absorption.dp_cap_pct`

**Old path: Code: ❌ | Schema: ❌ | YAML: ❌**  
**New path `absorption.proxy.dp_cap_pct`: Code: ✅ | Schema: ✅ | YAML: ✅**

The field was reorganized under the `proxy` sub-block. Current location in `domains.yaml:306`:

```yaml
absorption:
  mode: full          # disabled | proxy | full
  proxy:
    dp_cap_pct: 0.02  # ← current SSOT location
```

`AbsorptionProxyConfig.dp_cap_pct` is Pydantic-validated (fail-closed when `mode=proxy`). Tests in `tests/unit/feature_integrity/test_r1r2_features.py:548–637` cover all validation paths.

---

### `feature_engineering.bar_ta`

**All three axes: ❌**

Zero occurrences in any Python file under `apps/` or `vfoundation/`. No `BarTaConfig` class in `config_models.py`. Not in `domains.yaml`. `FeatureEngineeringDomainConfig` (the Pydantic model for this domain) does not have a `bar_ta` field.

---

### `feature_engineering.legacy_features_log`

**All three axes: ❌**

Zero occurrences in any file. No schema model, no YAML entry. Fully removed.

---

### `shadow_telemetry`

**Code refs: ✅ (extensive) | Schema (DomainsConfig): ❌ | YAML: ❌**

This is the most nuanced case. The `shadow_telemetry` service module is fully alive in `apps/reference/domains/shadow_telemetry/`. However, `shadow_telemetry` is **not a field of `DomainsConfig`**.

#### Why it's architecturally decoupled from the DomainsConfig schema

`DomainsConfig` (`config_models.py:3094`) uses `extra='forbid'` and lists only:
`debug`, `decision_making`, `feature_engineering`, `risk_management`, `position_tracking`, `execution_position`.

If `domains.yaml` contained a `shadow_telemetry:` key, `AuroraConfig.model_validate()` would raise a `ValidationError` at startup and refuse to boot. The shadow telemetry service deliberately avoids the `DomainsConfig` Pydantic contract.

#### How it reads config instead

Both runtime consumers use defensive `getattr` patterns:

- **`main_bridge.py:89`** (`LLMIntentIngressBridge`):
  ```python
  shadow_cfg = getattr(getattr(config, "domains", None), "shadow_telemetry", None)
  self._enabled = bool(shadow_cfg and shadow_cfg.enabled and shadow_cfg.api.enabled and shadow_cfg.api.write.enabled)
  ```
  Reads: `shadow_telemetry.enabled`, `shadow_telemetry.api.enabled`, `shadow_telemetry.api.write.enabled`.

- **`main_bridge.py:41`** (`ShadowEventTapPublisher`):
  ```python
  self._enabled = bool(getattr(cfg, "enabled", False))
  ```
  Reads: `shadow_telemetry.enabled` (with default `False`).

- **`main.py:262`** (`create_shadow_telemetry_app`):
  ```python
  shadow_cfg = config.domains.shadow_telemetry  # direct attribute access — no getattr guard
  ```
  This would raise `AttributeError` if `shadow_telemetry` is not present on the domains object. The shadow service is launched as a **separate process** with its own `ConfigLoader`, which likely has a different schema or bypasses Pydantic for this domain.

#### Corrected field statuses for shadow_telemetry

| Field | Code reads it? | Notes |
|---|:---:|---|
| `shadow_telemetry.enabled` | ✅ | `main_bridge.py:41,92` — governs whether tap publisher and LLM ingress bridge activate |
| `shadow_telemetry.api.enabled` | ✅ | `main_bridge.py:93` — part of triple-gate for LLM ingress |
| `shadow_telemetry.api.auth_mode` | ❌ | Never read; auth is done via env-var bearer tokens |
| `shadow_telemetry.api.host` | ✅ | `main.py:873` |
| `shadow_telemetry.api.port` | ✅ | `main.py:874` |
| `shadow_telemetry.api.tls` | ✅ | `main.py:878` |
| `shadow_telemetry.api.write.consequential` | ⚠️ | Used only as OpenAPI metadata (`x-openai-isConsequential`), not a runtime gate |
| `shadow_telemetry.api.write.enabled` | ✅ | `main.py:332,436`; `main_bridge.py:94` |
| `shadow_telemetry.api.write.idempotency_ttl_sec` | ✅ | `main.py:284` |
| `shadow_telemetry.api.write.intents_endpoint` | ✅ | `main.py:274` |
| `shadow_telemetry.api.write.max_body_kb` | ✅ | `main.py:299,452` |
| `shadow_telemetry.api.write.rate_limit_per_min` | ✅ | `main.py:297` |
| `shadow_telemetry.api.write.require_snapshot_ref` | ✅ | `main.py:298,530` |
| `shadow_telemetry.api.write.symbol_allowlist[]` | ✅ | `main.py:295` |
| `shadow_telemetry.egress_to_main.ipc_commands_endpoint` | ✅ | `main.py:324,340,740`; `main_bridge.py:99` |
| `shadow_telemetry.egress_to_main.mode` | ❌ | Not read by any code |
| `shadow_telemetry.egress_to_main.overflow_policy` | ✅ | `main.py:326` |
| `shadow_telemetry.egress_to_main.queue_maxsize` | ✅ | `main.py:325` |
| `shadow_telemetry.ingest.allowlist_events[]` | ✅ | `main_bridge.py:42` — event allowlist filter |
| `shadow_telemetry.ingest.ipc_endpoint` | ✅ | `main.py:316,340,397` |
| `shadow_telemetry.ingest.overflow_policy` | ✅ | `main_bridge.py:47` (getattr with default) |
| `shadow_telemetry.ingest.queue_maxsize` | ✅ | `main_bridge.py:46` (getattr with default) |
| `shadow_telemetry.ingest.source` | ❌ | Not read by any code |
| `shadow_telemetry.required_for_mode` | ✅ | `main_bridge.py:43` — fail-closed overflow handling |
| `shadow_telemetry.snapshot.tf_policy.*` | ✅ | `main.py:307–310` → `SnapshotStore` constructor |
| `shadow_telemetry.snapshot.trigger_event` | ✅ | `main.py:306` |

---

## Fields vs Runtime / Schema / YAML

### Fields fully supported (all 3 axes ✅)

| Field | Evidence |
|---|---|
| `feature_engineering.absorption.proxy.dp_cap_pct` | `domains.yaml:306`, `AbsorptionProxyConfig`, FE runtime |
| `execution_position.pending_entry_ttl.*` (base fields) | `PendingEntryTTLConfig`, `domains.yaml:465–482`, `entry_manager.py:147` |
| (All `execution_position.*` fields present in `domains.yaml`) | `ExecutionPositionDomainConfig` — see `config_models.py:3029` |

### Fields where code reads it but schema/YAML does not include it

These are the `shadow_telemetry.*` fields — code module references are extensive, but `DomainsConfig` schema does not contain `shadow_telemetry`, and current `domains.yaml` does not have this block. The shadow service reads config via unguarded attribute access and bypasses `DomainsConfig` Pydantic validation.

> **Implication for migration:** Adding `shadow_telemetry:` to `domains.yaml` as-is would immediately break startup because `DomainsConfig` uses `extra='forbid'`. A new `ShadowTelemetryDomainConfig` Pydantic model must be added to `DomainsConfig` before the YAML block can be re-added.

### Fields with code refs only in tools (not runtime)

| Field | Location |
|---|---|
| `advanced_stale_cancel.*` | `tools/log_forensics_cancel_audit.py:1600–1603` |

### Fields with zero references anywhere (true dead code)

| Field |
|---|
| `bracket_health_check.*` |
| `supersede_reprice_guard.*` |
| `bar_ta.*` |
| `legacy_features_log.*` |
| `shadow_telemetry.api.auth_mode` |
| `shadow_telemetry.egress_to_main.mode` |
| `shadow_telemetry.ingest.source` |

---

## Replacement Map

| Old field (stable_11_11) | New field / logic (current branch) |
|---|---|
| `execution_position.bracket_health_check.*` | `execution_position.guardian.*` (`GuardianConfig`, `order_guardian.py`) |
| `execution_position.quiet_hours.windows[]` | `ops.quiet_hours_utc` (flat list in `OpsConfig`) |
| `feature_engineering.absorption.dp_cap_pct` | `feature_engineering.absorption.proxy.dp_cap_pct` |
| `shadow_telemetry.api.auth_mode` | Env vars: `SHADOW_TELEMETRY_BEARER_TOKEN`, `SHADOW_TELEMETRY_BEARER_TOKENS` |

---

## Migration Risk Assessment

### 🔴 Blocked without schema work

| Block | Blocker |
|---|---|
| `domains.shadow_telemetry.*` | `DomainsConfig` has `extra='forbid'` and no `shadow_telemetry` field. Adding to `domains.yaml` will crash startup until `ShadowTelemetryDomainConfig` is added to `DomainsConfig`. |

### 🔴 No runtime infrastructure (dead on arrival if re-added)

| Block | Reason |
|---|---|
| `bracket_health_check.*` | Zero code reads these fields. Replaced by `guardian.*`. |
| `supersede_reprice_guard.*` | Zero code reads these fields. No replacement found. |
| `bar_ta.*` | No FE pipeline for bar-level TA indicators exists. |
| `legacy_features_log.*` | No logging pipeline for this block exists. |

### 🟡 Requires path migration (concept alive, path changed)

| Field | Action required |
|---|---|
| `execution_position.quiet_hours` | Use `ops.quiet_hours_utc` (already works). Do not add domain path. |
| `feature_engineering.absorption.dp_cap_pct` | Already migrated to `absorption.proxy.dp_cap_pct`. No action needed. |

### 🟡 Runtime code exists but re-adding to YAML is blocked

| Field | Action required |
|---|---|
| `advanced_stale_cancel.*` | Must implement `AdvancedStaleCancelConfig` in `PendingEntryTTLConfig` and wire to `entry_manager.py`. Currently only forensic tool references exist. |

---

## Final Conclusion

**Blocks that are still alive in the current runtime core:**

- `execution_position.*` (guardian, shadow_check, pending_entry_ttl, exposure_guard, etc.) — fully in schema + YAML + code.
- `feature_engineering.*` (absorption, pillars, macro_resid, etc.) — fully in schema + YAML + code.
- `shadow_telemetry.*` code module — *code alive, but outside `DomainsConfig` schema contract*.

**Blocks cut from the new runtime contract (`DomainsConfig`):**

- `bracket_health_check` — replaced by `guardian`, no schema entry.
- `pending_entry_ttl.advanced_stale_cancel` — cut from schema; forensic tool still references it.
- `pending_entry_ttl.supersede_reprice_guard` — cut entirely.
- `quiet_hours` (domain path) — concept migrated to `ops.quiet_hours_utc`.
- `bar_ta` — cut entirely, no replacement in FE.
- `legacy_features_log` — cut entirely.
- `shadow_telemetry` — code alive, but **outside DomainsConfig**; adding to `domains.yaml` without schema update crashes startup.
