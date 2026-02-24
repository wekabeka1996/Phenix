# Engineering Journal

## 2026-02-24: EP-01.3 P0 - queued supersede guarded by live position check + dispatch fix

**Mode:** TDD implementation.
**Scope:** `apps/reference/domains/execution_position/fsm.py`, `tests/domains/execution_position/test_supersede_fill_race_guard.py`

**Changes (additive-only, P0):**
1. `_process_queued_supersede()` is async and now checks live position state via `adapter.get_open_positions(symbol)` before replay.
2. If position is already open, queued supersede OPEN is aborted fail-closed.
3. If position query is unavailable, queued supersede OPEN is aborted fail-closed.
4. Dispatch defect fixed by executing queued decision through existing `_execute_decision()`.

**Tests added:**
- `test_supersede_timeout_blocks_open_when_live_position_exists`
- `test_supersede_timeout_blocks_open_when_position_query_unavailable_fail_closed`
- `test_supersede_timeout_allows_open_when_no_live_position`
- `test_process_queued_supersede_does_not_reference_missing_async_method`

**Validation:**
- `pytest -q tests/domains/execution_position/test_supersede_fill_race_guard.py` -> 4 passed
- `pytest -q tests/domains/execution_position/test_execpos_fsm_recovery_ordering_v2.py -k cancel` -> 7 passed
- `pytest -q tests/domains/execution_position/test_fsm_cancel_logging.py` -> 2 passed

---
## 2026-02-24: EP-IDEMPOTENT-CANCEL-2011 - implementation

- Implemented P0 exception-path absorption for cancel `-2011/-2013` in `idempotent_cancel.py` without retries.
- Implemented truth-aligned `_do_cancel` gating in `fsm.py`: watchdog/order_logger update only on success or idempotent-success.
- Added regression tests for exception-path absorption and cancel logging behavior.
- P1 in-flight cancel dedup intentionally deferred to a separate package.




## 2026-02-18: Forensic Audit — H1/H2/H3 Config Hypotheses Verification

**Mode:** Read-only. No code/config changes.
**Scope:** `apps/reference/domains/regime_detector/regime_detector.py`, `apps/reference/config_models.py`, `config/aurora/regime.yaml`

### What was checked
1. **H1** — Directionality of `uncertain_cutoff` on UNCERTAIN demotions.
2. **H2** — Directionality of `sma_trend.confidence_multiplier` on computed confidence.
3. **H3** — Existence of Grok-proposed YAML keys in Pydantic schemas + `extra='forbid'` enforcement.

### What was confirmed

**H1 — VERIFIED (TRUE):**
- `regime_detector.py:539`: `if regime != "UNCERTAIN" and float(confidence) < self._uncertain_cutoff: → regime = "UNCERTAIN"`
- Operator is `<`. Raising cutoff from 0.60 → 0.67 **expands** the demote zone → more UNCERTAIN. Confirmed.

**H2 — VERIFIED (TRUE with nuance):**
- `regime_detector.py:182-195`: formula = `abs(spread_ratio * confidence_multiplier)` clamped to `[conf_min, conf_max]`.
- Lowering multiplier (e.g. 30 → 16) lowers raw confidence. Floor is `conf_min` (cannot go below it), but if result falls below `uncertain_cutoff` while above `conf_min`, the regime is demoted to UNCERTAIN by H1 gate. Net effect: more UNCERTAIN or flat at floor.

**H3 — MOSTLY SAFE; ONE TRAP:**
- `volatility_entry_logic` — EXISTS at `AuroraInstrumentConfig:2791`.
- `regime_multipliers` — EXISTS **only inside** `VolatilityEntryConfig:2657`. As a top-level key under `AuroraInstrumentConfig` it does NOT exist → would crash under `extra='forbid'`.
  Correct path: `aurora.assets.<SYMBOL>.volatility_entry_logic.regime_multipliers`.
- `position_mode` — EXISTS at `AuroraInstrumentConfig:2724`.
- `leverage` — EXISTS at `AuroraInstrumentConfig:2729`.
- `holding_period.min_duration_sec` — EXISTS at `HoldingPeriodConfig:606`.
- `aurora.decision.gates.anti_fomo_sigma` — EXISTS via `DecisionConfig.gates` (`VolAdjGatesConfig:633`).
- `motion_window_sec`, `anti_flat_sigma` — EXISTS in `VolAdjGatesConfig:627,639`.

### Next action items (TODO — no code changes yet)
- [ ] **TODO-H3-TRAP**: Audit any Grok-generated config snippets that place `regime_multipliers` at the top level of an asset block. Must be nested under `volatility_entry_logic`.
- [ ] **TODO-H2-IMPACT**: If `sma_trend.confidence_multiplier` is lowered to 16, verify `conf_min` (floor) in `config/aurora/regime.yaml` models.sma_trend. If `conf_min > uncertain_cutoff`, then lowering multiplier has no visible effect (floor dominates). If `conf_min < uncertain_cutoff`, more UNCERTAIN events will appear.
- [ ] **TODO-H1-VALIDATE**: Run `tools/bars_regime_analysis.py` in dry mode with `uncertain_cutoff=0.62` vs `0.60` to quantify the UNCERTAIN rate delta before applying to live.

---

## 2026-02-13: SOLUSDT last filled order (loss) + FLIP audit

**Scope:** Forensics from `ops/wal/2026-02-13.jsonl`, `logs/*`, YAML SSOT under `config/aurora/`.

**Last filled SOLUSDT order (PnL-impacting):**
- rid: `aurora_SOLUSDT_1770973502430`
- side/qty: `SELL 5` (short)
- entry: `79.64` (LIMIT GTX, filled)
- SL/TP: `80.85 / 79.20` (strategy-provided, tick-rounded)
- regime at entry: `UNCERTAIN` (confidence=0.5 per regime detector)
- close: SOL position disappears at `2026-02-13T14:35:23.029Z`, wallet delta `-8.9628 USDT`

**why (facts / evidence pointers):**
- why: flip entry buy->sell (WAL `ops/wal/2026-02-13.jsonl:9746`)
- why: RR=0.36 (TP 0.544% vs SL 1.512%) (WAL `ops/wal/2026-02-13.jsonl:9746`)
- why: closed as mark>SL stop; TP orphan cleaned (WAL `ops/wal/2026-02-13.jsonl:14649`, `logs/aurora_core.log.1:35126`)

**FLIP operational issues observed:**
- why: flip CLOSE intents rejected (NRR-046: LIMIT needs tf_sec) (`ops/wal/2026-02-13.jsonl:14489`)
- why: flip OPEN attempts can be maker-only rejected (GTX post-only) (`ops/wal/2026-02-13.jsonl:14791`)

**Config candidates (YAML-only, not applied):**
- Block `UNCERTAIN` for `SOLUSDT` (or raise thresholds) to avoid low-quality flips.
- Raise SOL TP/RR guardrails (`take_profit.tp_low_ratio`, `exit.regime_tpsl.min_tp_rr`) to avoid RR=0.36.
- Unblock flip CLOSE TTL derivation (review `execution_position.pending_entry_ttl.*` behavior for tf_sec=0/None).
- Reduce maker-only rejects (tune `volatility_entry_logic` multipliers for SOL or revisit `aurora.execution.entry_tif`).

## 2026-01-30: DM QoS P2-Lite Purge and Wiring Audit

**Task:** DM_QOS_P2_LITE_PURGE_AND_WIRING_AUDIT
**Context:** Audited DecisionMaking QoS logic to reduce cognitive load and verify "Exposure Block" feature status without full refactor.

**Findings:**
1. **Dead Code Confirmed:** `_check_qos_rules` was strictly unreachable (0 callsites).
2. **Missing Wiring:** `_handle_exposure_block` is UNWIRED (no event listener calls it). It also contains a SPLIT-BRAIN BUG (writes to flat key, read by partitioned query). "Global Exposure Block" logic is effectively non-existent despite config presence.
3. **P2-Lite Action:**
    - **DELETED** `_check_qos_rules`.
    - **ANNOTATED** `_handle_exposure_block` with failure warning/TODO.
    - **VERIFIED** QoS tests pass.

## 2026-01-30: DM_SAFETY_BYPASSES_P1 — Critical Security Hardening

**Task:** DM_SAFETY_BYPASSES_P1
**Context:** Identified and fixed two critical security vulnerabilities in the `decision_making` domain.

**Vulnerabilities Fixed:**
1. **Hardcoded safety gates bypass:** `apply_safety_gates = str(strategy_id) == "aurora"` allowed any non-Aurora strategy to bypass directional sanity and price motion gates.
2. **Fail-open exposure cache:** Missing/stale/error cache conditions allowed trades, violating fail-closed principle.

**Changes:**
1. `decision_making.py`: Safety gates now read from `strategies.<id>.safety_gates.enabled` config. Missing config → FAIL-CLOSED (NRR-054).
2. `decision_making.py`: Exposure cache precheck now returns `False` (block) on missing/stale/error (NRR-053).
3. `normalized_reject_reasons.py`: Added NRR-053 (EXPOSURE_CACHE_UNAVAILABLE), NRR-054 (CONFIG_SAFETY_GATES_MISSING).
4. `config_models.py`: Added `SafetyGatesConfig` Pydantic model.
5. `aurora.yaml`, `mean_reversion.yaml`: Added explicit `safety_gates.enabled` field.

**Risk Note — Mean Reversion safety_gates.enabled=false:**
MR intentionally trades against trend (counter-trend), so directional sanity and price motion gates are DISABLED.
**Alternative guards protecting MR:**
- Regime gating: MR only trades in FLAT regimes (`allowed_regimes`).
- Bollinger Band boundaries: BB upper/lower provide entry structure.
- ATR-based stops: `sl_atr_mult` prevents runaway losses.
- Per-asset `max_risk_score` filtering in Phase 3+.

**P2 TODO:** Consider `safety_gates.profile: "counter_trend"` to formalize MR-specific gate logic (e.g., require oversold/overbought RSI instead of trend confirmation).

**Verification:**
- NRR-053/054 uniqueness confirmed.
- All strategy YAMLs updated.
- 22/22 tests passed.


## 2026-01-08: VF-DICT Forensics (Global/Domain Dictionaries)

**Task:** VF-DICT-FORENSIC (01..05)
**Context:** Investigate vFoundation Global/Domain Dictionaries as governance SSOT (op/verb/TTL/security/routing) and prove how/if they are used by runtime vs tooling.

**Outcome (facts):**
1. **Inventory:** Dictionary artifacts exist in three layers: global dictionaries (`global_v2_2*.yaml`), domain dictionaries (`vfoundation/dictionaries/domains/domain_*.yaml`), and app domain metadata (`apps/reference/domains/**/domain_dict.json`).
2. **Runtime usage:** vFoundation runtime does not parse these dictionary YAML files; enforcement currently lives in code (Message op allowlist, TTL range + expiry, signature required for DEC/CMD, NO_ROUTE for unknown handlers).
3. **CLI usage:** `vfound dict --global` only checks dictionary file existence (no content parsing).
4. **Data quality:** `vfoundation/dictionaries/global_v2_2_framework.yaml` contains a markdown code-fence and is not valid YAML for parsing; this is currently harmless because it's not parsed.

**Reports:**
- `reports/VF-DICT-FORENSIC-01.md` — inventory, validity, duplication signals
- `reports/VF-DICT-FORENSIC-02.md` — proven code/CLI references
- `reports/VF-DICT-FORENSIC-03.md` — where runtime validation lives today
- `reports/VF-DICT-FORENSIC-04.md` — Aurora event-space vs dictionary declarations (OP-level)
- `reports/VF-DICT-FORENSIC-05.md` — Option A/B/C evolution menu (no implementation)

## 2026-01-08: Config Contract Ghost Rejections Eliminated

**Task:** TASK-CFG-REJECT-INTEGRATE-01
**Context:** Previous forensic analysis revealed that `ConfigContractError` exceptions (raised when strictly typed config is missing or invalid) were being caught and logged but did not emit standard rejection events. This created "ghost" failures where the system would silently stop trading on a symbol without a trace in the event bus or order logs.

**Changes:**
1.  **NRR Integration:** Added `NRR-CFG-001` (MISSING) and `NRR-CFG-002` (INVALID) to `NormalizedRejectReasons`.
2.  **Strategy Gateway:** Modified `_on_strategy_signal_gateway` in `DecisionMaking` to emit `EVT:TRADE_INTENT_REJECTED` when a config contract violation occurs.
3.  **Feature Engine:** Modified `on_features` to emit `EVT:DECISION_BLOCKED` (new health event) when config errors prevent feature calculation.
4.  **Verification:** Updated `test_config_contract_block_normalization.py` to verify event emission.

**Outcome:**
All configuration-related trading blocks are now observable in the event stream. The "Ghost" class of errors has been eliminated.
- **2026-01-08:** Synced `EVT:DECISION_BLOCKED` to new SSOT `docs/FSM_EVENT_MAP.md` and added `decision_blocked_total` metric.
- **2026-01-08:** Deleted dead legacy spot `AccountObserver` domain (reachability=0 for Futures, unwired from main.py).
- **2026-01-08:** Fixed test env: FastAPI missing (installed in .venv but pytest not using it?).

## 2026-01-08: VF-VERB-REG — SSOT Verb Registry (seed + warn-only drift gate)

**Task:** VF-VERB-REG-01/02/03
**Context:** Prepare a single SSOT verb registry seeded from runtime string-scan (no runtime enforcement). Add a warn-only CI gate to surface drift immediately without breaking.

**Changes:**
1. **SSOT registry created:** `apps/reference/dictionaries/verb_registry_v1.yaml` generated from runtime scan (`.py` without `tests/**`).
2. **Warn-only gate:** `tests/vfoundation/test_verb_registry_warn_only.py` compares runtime scan vs registry and writes diffs into `reports/` without failing on coverage gaps.
3. **Owner labeling (top-N):** marked owner + status for the top-20 most frequent runtime tokens; schema is populated only when an exact `<verb_lower>_v1.json` exists (otherwise `null`).

**Reports:**
- `reports/VF-VERB-REG-01.md` — seed generation summary
- `reports/VF-VERB-REG-02.md` + `reports/VF-VERB-REG-02_diff.json` — warn-only drift output
- `reports/VF-VERB-REG-03.md` — owner labeling summary

**Non-goals (explicit):** no runtime deny/allow by verb; no attempt to extract registry from `Router.register` (not used in prod wiring).

## 2026-01-08: VF-VERB-REG-04/05 — Owner inference report + coverage threshold

**Task:** VF-VERB-REG-04/05
**Context:** Speed up cleanup of `owner: unknown` with evidence-based path heuristics (no auto-changes). Tighten drift gate so it fails only once coverage is basically complete.

**Changes:**
1. **Owner inference report (no autofix):** Added `tests/vfoundation/test_verb_owner_inference_report.py` which scans runtime `.py` (no tests), aggregates occurrences per file and per `apps/reference/domains/<X>/` bucket, and suggests owner only when ≥70% of occurrences land in one domain.
2. **Artifacts:** Writes `reports/VF-VERB-REG-04_owner_suggestions.json` and `reports/VF-VERB-REG-04.md`.
3. **Coverage gate policy:** Updated `tests/vfoundation/test_verb_registry_warn_only.py` to fail only if `coverage >= 98%` AND `runtime_not_in_registry > 0` (until then it stays warn-only).

## 2026-01-08: VF-VERB-REG-06 — Apply owner suggestions (>=70%)

**Task:** VF-VERB-REG-06
**Context:** Apply evidence-based owner suggestions to reduce `owner: unknown` without guesses.

**Changes:**
- Updated `apps/reference/dictionaries/verb_registry_v1.yaml` by changing **only** `owner` for entries where current owner was `unknown` and inference confidence was ≥70%.
- Regenerated VF-VERB-REG-04 reports after the update.

**Artifacts:**
- `reports/VF-VERB-REG-06_applied.json` — applied changes with confidence + evidence
- `reports/VF-VERB-REG-06.md` — short summary
- **2026-01-08:** Validated and Frozen 'Alpha Search' domain (Task ALPHA-FREEZE-01/02). Added determinism tests, safe metrics, and offline eval script.

## 2026-01-08: AGENT-NAV-VERB-REG-01 — Agent Navigation Playbook (registry-first)

**Task:** AGENT-NAV-VERB-REG-01
**Context:** After establishing SSOT for system language (Verb Registry) and governance dictionaries, we need an explicit, contract-first navigation instruction for Copilot/LLM agents.

**Changes:**
- Added a strict navigation playbook in `docs/AGENT_NAVIGATION_PLAYBOOK.md`.
- Rules are registry-first (`apps/reference/dictionaries/verb_registry_v1.yaml`), owner-boundary (`apps/reference/domains/<owner>/`), and policy-aware (global/domain governance YAML).

**Outcome:**
Copilot/agents now have a single official procedure that forbids guessing verbs/owners and forbids repo-wide wandering without a contract.

## 2026-01-08: Exchange Filters Startup Guard Integration

**Task:** TASK-EXF-IMPLEMENTATION (07..12)
**Context:** Implemented a critical startup guard that validates `config/aurora/instruments.yaml` against real-time exchange constraints (`/fapi/v1/exchangeInfo`). This prevents runtime rejections due to precision mismatches (LOT_SIZE, PRICE_FILTER) or missing filters.

**Changes:**
1.  **Validator Implementation (`validator.py`):**
    *   Added logic to fetch and parse exchange filters (`LOT_SIZE`, `PRICE_FILTER`, `MIN_NOTIONAL`).
    *   Implemented batch fetching (1 request for all symbols) to optimize startup time (~N -> 1 request).
    *   Removed unsafe defaults (e.g., `min_notional=5`) to ensure fail-closed behavior on missing data.
2.  **Configuration (`system.yaml`/`config_models.py`):**
    *   Added `validate_instruments_on_startup` (default: True).
    *   Added `warn_only_filters` (default: False) for Dev/Shadow environments.
3.  **Wiring (`main.py`):**
    *   Integrated validation logic immediately after config loading.
    *   Implemented blocking behavior on CRITICAL mismatches (SystemExit 1).
4.  **Testing:**
    *   Added `tests/contracts/test_exchange_filters_validation.py` (Unit).
    *   Added `tests/integration/test_startup_filters_wiring.py` (E2E Integration).

**Policies:**
*   **Fail-Closed:** In LIVE/TESTNET, any critical filter mismatch blocks startup.
*   **Warn-Only:** Available via config for non-critical environments.

**Artifacts:**
*   `docs/STARTUP_GUARDS.md`: Official documentation of the new guard.

## 2026-01-08: Execution Management (Zombie) Removal

**Task:** EM-ZOMBIE-01
**Context:** Domain `execution_management` was identified as a non-functional stub (not wired, no logic, tests only checking logs). It was creating confusion vs `execution_position` (the real execution domain).

**Changes:**
1.  **Removed:** `apps/reference/domains/execution_management/` and `tests/test_execution_management.py`.
2.  **Refactored:** `apps/reference/main.py` - Renamed log file `domain_execution_management.log` to `domain_execution_position.log` (as it was actually containing ExecPos logs).
3.  **Docs:** Added tombstone in `docs/deprecations/`.

**Validation:**
*   Confirmed 0 functional references in code/config.
*   Verified `main.py` wiring logic remains intact (integration tests passed).

## 2026-02-13: SOL hardening (UNCERTAIN gate off + tighter SL)

**Tasks:** TASK-SOL-REGIME-BLOCK-01, TASK-SOL-SL-TIGHTEN-01, TASK-SOL-GATE-TESTS-01, TASK-SIZING-FORENSIC-01

**Changes:**
1. `config/aurora/strategies/aurora.yaml`
   - `aurora.assets.SOLUSDT.allowed_regimes`: removed `UNCERTAIN`.
   - `aurora.assets.SOLUSDT.exit.sl_pct`: `0.01512 -> 0.0135`.
2. Added test `tests/domains/decision_making/test_sol_uncertain_gate.py::test_sol_uncertain_blocked`
   - Verifies `SOLUSDT` in `UNCERTAIN` emits `EVT:STRATEGY_DECISION_BLOCKED` with `REGIME_NOT_ALLOWLISTED` and no `EVT:STRATEGY_SIGNAL_PRODUCED`.
3. Updated and extended `tests/domains/test_tpsl_config_production.py`
   - Updated SOL assertions to `sl_pct=0.0135`.
   - Added `test_sol_sl_pct_applied` (SELL path, tick-quantized SL check).

**Forensic note (RID):**
- `rid=aurora_SOLUSDT_1770973502430` found in `ops/wal/2026-02-13.jsonl` with:
  - `TRADE_INTENT_PROPOSED` payload `order.qty="5"` and `order.price="79.6401785714285714300"`.
  - Followed by `DEC OPEN` with `qty="5"` and rounded entry `price="79.64"`.

**Sizing verdict:**
- Regime-aware sizing in DecisionMaking is present (`YES`) via `margin_pct_mult` from `aurora.assets.<symbol>.regime_sizing[regime]` in `_on_strategy_signal_gateway`.
- For `UNCERTAIN`, SOL has no regime multiplier key/default, so sizing falls back to base `instruments.SOLUSDT.sizing.margin_pct`.

**Validation run:**
- Targeted: `python -m pytest -q tests/domains/decision_making/test_sol_uncertain_gate.py::test_sol_uncertain_blocked tests/domains/test_tpsl_config_production.py::TestAuroraConfigLoading::test_solusdt_exit_config_loaded tests/domains/test_tpsl_config_production.py::TestBracketPriceCalculation::test_solusdt_sl_calculation tests/domains/test_tpsl_config_production.py::TestBracketPriceCalculation::test_sol_sl_pct_applied tests/domains/test_tpsl_config_production.py::TestEndToEndBracketCalculation::test_solusdt_full_bracket_path_uses_aurora_config tests/contracts/test_regime_allowlist.py -q` -> **102 passed**.
- Full suite: `python -m pytest -q` currently blocked by environment issues (`polars` missing and pytest marker `timeout` not registered).
