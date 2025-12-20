# TASK27.4 — ConfigLoader Hydration / setdefault Audit

## Claim
“`ConfigLoader` uses hydration (`setdefault`, dict migrations) as a schema workaround (masking schema problems).”

## Status
CONFIRMED

`apps/reference/config_loader.py` performs multiple pre-validation mutations that exist specifically to satisfy strict Pydantic schema requirements (including “Optional-but-required” fields), plus legacy key migration/hygiene.

## Evidence: all `setdefault(...)` in `apps/reference/config_loader.py`

### 1) System meta “zero-defaults contract” (service/meta)
- `apps/reference/config_loader.py:173`–`apps/reference/config_loader.py:176`
  - `meta.setdefault("system_config_version", None)`
  - `meta.setdefault("regime_config_version", None)`
- Schema target: `apps/reference/config_models.py:1451`–`apps/reference/config_models.py:1452`
  - `SystemMetaConfig.system_config_version: Optional[str] = Field()`
  - `SystemMetaConfig.regime_config_version: Optional[str] = Field()`
- What it proves: these keys are `Optional[...]` but required by schema; loader forces presence.

### 2) Ensure `trading` is a mapping (structural)
- `apps/reference/config_loader.py:556` and `apps/reference/config_loader.py:584`
  - `merged_config.setdefault("trading", {})`
- Purpose: defensive merge/hydration; prevents crashes when earlier config fragments are not dicts.

### 3) Hydrate `trading.symbols_to_track` (business/schema alignment)
- `apps/reference/config_loader.py:589`–`apps/reference/config_loader.py:595`
  - `trading_block.setdefault("symbols_to_track", decision_block.get("symbols_to_track"))`
  - else derive from `merged_config["instruments"]`
- Schema target: `apps/reference/config_models.py:1327` (`TradingConfig.symbols_to_track: List[str] = Field(...)`)
- Proof of necessity: deleting `trading.symbols_to_track` from a validated config dict yields `ValidationError: Field required` at `('trading','symbols_to_track')` (runtime assertion).

### 4) Force optional strategy blocks to exist (schema workaround)
- `apps/reference/config_loader.py:692`–`apps/reference/config_loader.py:695`
  - `merged_config.setdefault("aurora", None)`
  - `merged_config.setdefault("mean_reversion", None)`
- Schema targets:
  - `apps/reference/config_models.py:1522` — `AuroraConfig.aurora: Optional[Dict[str, Any]] = Field(...)`
  - `apps/reference/config_models.py:1503` — `AuroraConfig.mean_reversion: Optional[...] = Field(...)`
- What it proves: these are `Optional[...]` fields but required (no default); loader injects explicit `null` when absent.

### 5) Migrate legacy root `guardian` block → `execution.order_guardian` (legacy schema hygiene)
- `apps/reference/config_loader.py:765`–`apps/reference/config_loader.py:770`
  - `guardian_block = merged_config.pop("guardian", None)`
  - `exec_block = merged_config.setdefault("execution", {})`
  - `exec_block.setdefault("order_guardian", guardian_block)`
- Effect: avoids `extra='forbid'` failure at root by relocating a legacy key to a schema-accepted namespace.

### 6) Inject runtime metadata under `system_meta.runtime` (service/meta)
- `apps/reference/config_loader.py:772`–`apps/reference/config_loader.py:776`
  - `system_meta.setdefault("runtime", {})`
  - `system_meta["runtime"].setdefault("config_name", self.config_name)`
  - `system_meta["runtime"].setdefault("config_dir", str(self.config_dir))`
- Schema target:
  - `apps/reference/config_models.py:1442`–`apps/reference/config_models.py:1443`
  - `SystemRuntimeMeta.config_name: Optional[str] = Field(...)`
  - `SystemRuntimeMeta.config_dir: Optional[str] = Field(...)`
- Proof of strict requirement: deleting `system_meta` from validated config dict yields `ValidationError: Field required` at `('system_meta',)` (runtime assertion).

### 7) Re-inject metadata after env resolution (service/meta, best-effort)
- `apps/reference/config_loader.py:812`–`apps/reference/config_loader.py:817`
  - ensures `resolved_config["system_meta"]["runtime"]["config_name|config_dir"]` exist.

## Conclusion
Hydration in `ConfigLoader` is not incidental; it is used to:
- satisfy strict schema requirements (including Optional-but-required fields),
- provide backward-compat migrations under `extra='forbid'`,
- inject runtime metadata.

