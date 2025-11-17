# Config v2 Migration Audit — 2025-11-15

## Scope & Method
- Reviewed SSOT docs (`docs/For_GPT/config_contract_map.md`, `docs/trading_config_wiring_v2.md`, `docs/config_v2/specification.md`, `docs/config_v2/migration_progress.md`).
- Inspected all v2 YAML assets under `config/` plus legacy fallbacks in `configs/` and `tests/config/aurora/`.
- Traced how resolvers consume those configs (`apps/reference/config_loader.py`, `config_exposure_policy.py`, `domains/execution_position/*`).
- Surveyed validator/tests/tooling (`tools/config_validator_v2.py`, `tests/integration/test_config_v2_e2e.py`, `tests/test_exposure_guard_config.py`, `tools/metrics_summary.py`).

## Findings
### F1 — Brackets resolver never reads v2 data
- **Impact:** `resolve_brackets_config` (`apps/reference/domains/execution_position/brackets_config.py`) expects `config_v2.domains["execution"]["brackets"]`, but `config/domains/execution.yaml` stores the block under `manage.brackets`. As a result the resolver always falls back to legacy paths that no longer exist, forcing defaults (50/100/5) and ignoring any v2 edits.
- **Evidence:** `_get_v2_execution_brackets_cfg` (lines 39‑51) retrieves a top-level `brackets` node; the YAML only defines `manage.brackets` (lines 18‑46). Tests/validator never call the resolver in a way that asserts `result.source == "config_v2"`.
- **Recommendation:** Move the `brackets` block to top-level (`domains/execution.yaml: brackets:`) or update `_get_v2_execution_brackets_cfg` to look under `manage`. Add coverage in `tests/integration/test_config_v2_e2e.py` and validator to assert `ResolvedBrackets.source == "config_v2"`.

### F2 — Exposure TTL overrides lost because of key mismatch
- **Impact:** `config/domains/execution.yaml` defines `pending_reservation_ttl_sec`, but `resolve_exposure_policy` (`apps/reference/config_exposure_policy.py`, lines 185‑199) only looks for `pending_ttl_sec`, `post_fill_hold_ttl_sec`, and `positions_stale_ttl_sec`. Consequently, the intended 45s reservation TTL plus shorter stale windows never apply; the guard reverts to defaults (90/5/5), extending orphan lifetime.
- **Recommendation:** Rename the key to `pending_ttl_sec` and add explicit `post_fill_hold_ttl_sec` / `positions_stale_ttl_sec` entries per spec. Extend the validator to flag when v2 TTLs equal defaults so regressions are visible.

### F3 — Guardian/watchdog/fallback tuning still lives only in `configs/master_config_v1.yaml`
- **Impact:** The v2 execution config contains `manage.auto/brackets/quick_profit/orphan_monitor` but omits `order_guardian`, `watchdog`, and `fallback`. `resolve_execution_manage_config` therefore drops back to hardcoded defaults (poll_interval_ms 500, cleanup_ttl_ms 6000, fallback backoff 200/500/1000). Those tuned values still exist only in `configs/master_config_v1.yaml`, yet ConfigLoader never ingests that file, so runtime ignores them while scripts/tests referencing it (e.g., `tests/test_exposure_guard_config.py`, `tools/metrics_summary.py`) get a false sense of safety.
- **Recommendation:** Port guardian/watchdog/fallback blocks into `config/domains/execution.yaml`, keep legacy fallback only for dual-read, and update tooling/tests to load `ConfigLoader().load_config()` instead of reading `configs/master_config_v1.yaml` directly.

### F4 — Instrument overrides cannot change leverage/limits
- **Impact:** `config/overrides.yaml` stores `symbols.<symbol>.max_leverage` at the top level, but `_build_instrument_profile_from_v2` (`apps/reference/config_symbols.py`, lines 176‑233) only reads `limits.max_leverage`. Net effect: leverage stays at the default 20x even though `execution.exposure.leverage_defaults` advertises 125x, so position sizing and adapters work with inconsistent numbers.
- **Recommendation:** Nest leverage/limit overrides under `limits` (e.g., `symbols.SOLUSDT.limits.max_leverage: 125`) and backfill missing base fields (`min_qty`, `min_price`, `max_position_size`) in `config/instruments.yaml` so resolvers stop inferring critical values.

### F5 — Risk soft limits and score weights never migrated
- **Impact:** `config/domains/risk.yaml` only supplies `daily_limits`. `ExposureGuard._load_soft_limit_config` still reads `trading.risk.soft_limits` (legacy path) and therefore falls back to defaults (clip_min_notional=10 USD, directional_ratio_max=3). Score weights and `trading_allowed_thresholds` remain unmigrated, so `risk_management` cannot be tuned via v2.
- **Recommendation:** Extend the risk v2 file with `soft_limits`, `score_weights`, and `trading_allowed_thresholds`, then teach the relevant resolvers to pull from v2 first. Add validator coverage that fails when those sections are absent.

### F6 — Runtime vs. test configs diverge
- **Impact:** `ConfigLoader` defaults to `tests/config/aurora` whenever that folder exists (see `apps/reference/config_loader.py::__init__`). Production `main()` explicitly passes `project_root / "config" / "aurora"`, but that directory is missing from the repo, so runtime loads no legacy YAML at all and relies solely on config v2. Meanwhile every unit test/utility (e.g., `tests/test_config_auto_trading.py`, `tools/verify_config.py`) exercises the toy legacy fixture under `tests/config/aurora`, so regressions in the real runtime path go unnoticed.
- **Recommendation:** Commit the actual `config/aurora/*.yaml` or change ConfigLoader defaulting logic so both runtime and tests load the same source. Remove direct references to `tests/config/aurora` from scripts, and require tests to inject config_v2 payloads explicitly.

### F7 — Validation gaps let broken v2 fields ship
- **Impact:** `tests/integration/test_config_v2_e2e.py` checks only five resolvers and never asserts `.source`. `tools/config_validator_v2.py` does call `resolve_brackets_config`, but it only inspects TP/SL magnitudes, not the source, so miswired placements (F1) pass silently. Likewise, incorrect key names (F2) simply fall back to defaults without being flagged.
- **Recommendation:** Expand the e2e test to cover `resolve_brackets_config`, `resolve_daily_risk_state.source`, and reservation TTLs. Update the validator to assert `result.source == "config_v2"` (or at least warn) and to compare TTLs against expected values rather than just checking ranges.

### F8 — Published schemas still describe legacy monolith
- **Impact:** `config/_schemas/aurora_trading.schema.json` (736 lines) still mandates `config_version`, `instruments.*.min_qty`, and monolithic `trading.*` sections. None of the new modular files conform to it, so schema validation is meaningless and newcomers get contradictory instructions.
- **Recommendation:** Either regenerate the schema to mirror the v2 directory layout (one schema per domain) or clearly mark the existing file as deprecated to avoid drift.

## Supporting Observations
- `config/domains/tca.yaml` and `config/core.yaml` remain placeholders; document whether they should be deleted or populated.
- `docs/config_v2/migration_progress.md` claims "v2 primary" for most domains, but findings above show execution/risk/instrument domains still depend on fallback behavior.
- `docs/config_analysis/*` and multiple TODO/JOURNAL entries continue to treat `configs/master_config_v1.yaml` as SSOT even though ConfigLoader never reads it; this mismatch should be called out in those docs once remediation is complete.
