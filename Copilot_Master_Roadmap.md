# Copilot Master Roadmap

## Completed Tasks

- [x] TASK19: Root strict freeze (commit: c8f13f8)
  - AuroraConfig extra='forbid' on root
  - Service/migration keys removed from runtime
  - Explicit schema enforced
  - Loader rejects _config_* keys
  - Tests green
  - Docs updated
- [x] TASK20: Zero defaults inventory and gate (commit: 3ee7b59)
  - Inventory tool created (tools/inventory_config_defaults.py)
  - Reports generated (reports/TASK20_defaults_inventory.md, .json)
  - Test-gate added (tests/config/test_no_defaults_in_config_models.py)
  - 489 defaults inventoried (no removal on this task)
  - CI gate ready for future zero defaults enforcement

- [x] TASK21: YAML SSOT autofill + strict runtime contracts (commit: a2c75f7)
  - Autofill tool added (tools/autofill_config_defaults_into_yaml.py)
  - Default-path mapping + generator (tools/config_default_path_map.yaml, tools/generate_config_default_path_map.py)
  - Plan/applied reports generated (reports/TASK21A_yaml_patch_plan.md, reports/TASK21A_yaml_patch_applied.md)
  - SSOT cleanup: deprecated configs rejected/removed; bridge required; trading.yaml cleanup
  - Tests added/updated: config strictness + runtime fail-closed contracts

- [x] TASK23.FIX: Optional-required null autofill + remove legacy SSOT aliases
  - `tools/autofill_config_defaults_into_yaml.py --autofill-optional-nulls` + reports
  - `TradingConfig` SSOT mirror fields removed (no second-truth in `trading.*`)
  - Loader/test fixtures hardened; `pytest -q tests/config tests/runtime` green

- [x] TASK24: Core correctness hardening (Feature/Regime/Retry)
  - Warmup/readiness gating in DecisionMaking (fail-closed) + `warmup_block_total`
  - FeatureEngineering fixes: `macro_sync` tail/ttl, dt-normalized `volume_spike`, volatility readiness
  - RegimeDetector strict typed config + ATR True Range/Wilder + data-quality fail-closed gates
  - RetryScheduler attempt SSOT, config-driven backoff/jitter, no-loop fail-fast, emit_compat-only + policy tests

- [x] TASK25: Runtime legacy config purge (domains)
  - Removed dict-thinking patterns in `apps/reference/domains/**` (`.get(..., default)`, `getattr(..., default)`, config `.to_dict()` fallback)
  - Fail-fast: dict passed as config → `TypeError`
  - Added AST policy gate + behavioral tests (`tests/runtime/test_task25_*`)
