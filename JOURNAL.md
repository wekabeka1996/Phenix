# Engineering Journal

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
