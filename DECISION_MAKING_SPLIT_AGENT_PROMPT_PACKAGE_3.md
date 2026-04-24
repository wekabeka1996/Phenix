# Decision Making — Package 3 Standalone Prompt (for fresh agent)

> This is a **full standalone brief** for a new agent who has no prior context.
> Read it end-to-end BEFORE touching anything. Then read the referenced files.
> Packages 1 and 2 are already complete and accepted. This brief covers **Package 3 only**.

---

## 0. Who you are, what you do

You are a migration-agent implementing the **third and final package** of a planned
`decision_making` domain refactor. Packages 1 and 2 landed locally, were accepted by the
controller, and their artifacts are on disk. Your job is Package 3: **Variant B physical
cross-domain split**.

You operate fail-closed. When anything is ambiguous, you write a `BLOCKED` report and stop,
rather than guessing. A human controller reads your report and either issues an Addendum that
unblocks you, or tells you to proceed with a specific decision.

You do not redesign. You do not change runtime behavior. You move files, rewrite imports,
update registry owners, and update guardrail tests — that is all.

---

## 1. Mandatory reading (in this order)

Read these files completely before any tool action other than reading:

1. [DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md](DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md)
   — the SSOT audit. Sections §7.B (Variant B skeleton), §7.B.2 (external consumer map),
   §7.B.3 (NRR/WhyCode decision), §7.B.4 (registry+guardrail changes), and §12 (automation
   plan) are your Package 3 charter.
2. [DECISION_MAKING_SPLIT_AGENT_PROMPT.md](DECISION_MAKING_SPLIT_AGENT_PROMPT.md)
   — the original executable prompt with 8 non-negotiable rules, operating procedure,
   reporting format, 9 stop conditions.
3. [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md)
   — Package 1 contract decisions. **Historical** — already applied, but §0 (git policy
   relax to `git mv` only, no push/PR) and §4 (`NRR stays in decision_making/contracts/`,
   NRR → vfoundation is OUT OF SCOPE) are still binding for you.
4. [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_02.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_02.md)
   — Package 1 registry `co_emitters` decision. Historical.
5. [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_03.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_03.md)
   — Package 2 placement for `position_queries.py` + `operational_mode.py`. §5 is binding
   for you: both files **stay in `decision_making/primitives/`** through Package 3 (no move).
6. [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_04.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_04.md)
   — Package 2 LAYER_RULES correction + `aurora_policy.py` relocation to `primitives/`.
   Historical.
7. [tools/migrations/dm_split/artifacts/PACKAGE_1_REPORT.md](tools/migrations/dm_split/artifacts/PACKAGE_1_REPORT.md)
   — what was done in P1.
8. [tools/migrations/dm_split/artifacts/PACKAGE_2_REPORT.md](tools/migrations/dm_split/artifacts/PACKAGE_2_REPORT.md)
   — what was done in P2, including final layout on disk.
9. Current tree:
   `apps/reference/domains/decision_making/` with subpackages
   `core/ gateway/ gates/ intent/ strategies/ primitives/ contracts/ observability/`.

After reading all nine, summarize in your first report section ("Section 0: context
confirmation") exactly three things:
- the current post-P2 file layout of `decision_making/` as a tree (from disk, not from memory);
- the existing `dm_split` artifact files you will reuse vs overwrite;
- every item in §4 of this document that you intend to skip (there MUST be none).

---

## 2. The 8 non-negotiable rules (restated)

These are from the base prompt. They override every optimization instinct you have.

1. **No redesign.** No new classes, no behavior changes, no algorithmic edits.
2. **No contract changes beyond §4 of this brief.** Schemas, WAL payloads, event shapes,
   typed-config fields, registry entries: only edits explicitly listed in this document
   are allowed.
3. **Package is revertable.** Every step must be recoverable via `git restore` /
   `git checkout` from a single commit group.
4. **`git mv` only.** Preserves history. No `rm + create_file`.
5. **Fail closed on ambiguity.** If the audit, addenda, or this brief do not unambiguously
   assign a destination for any file, STOP and write a BLOCKED report with the exact
   file path + the ambiguity.
6. **Import-only touches outside DM are allowed.** Any non-DM production file whose
   change exceeds "import path replacement" must be listed in §4, or it is a STOP.
7. **No shims without authorization.** Only shims explicitly authorized in Audit §7.A.4
   (already used in P2) or in this brief §5.2 may exist.
8. **Libcst for all import rewrites.** No regex. No `ast.unparse`. Use the existing
   `tools/migrations/dm_split/` rewriter from P2, extend it only if required.

---

## 3. Scope — Package 3 (Variant B)

### 3.1 In scope

| Category | Source (post-P2) | Destination (post-P3) |
| --- | --- | --- |
| Strategy runtimes | `apps/reference/domains/decision_making/strategies/**` | `apps/reference/domains/strategies/runtimes/**` |
| Strategy bridge | `.../decision_making/strategies/bridge.py` | `.../strategies/runtimes/bridge.py` |
| Shared decision primitives | `.../decision_making/primitives/{scoring_kernel,aurora_math,aurora_policy,entry_plan,exit_manager,tpsl_owner,sizing_margin_first,instrument_quantizer}.py` | `apps/reference/shared/decision_primitives/**` |
| Shared shields | `.../decision_making/primitives/shields/**` | `apps/reference/shared/decision_primitives/shields/**` |
| Registry owner updates | `apps/reference/dictionaries/verb_registry_v1.yaml` | see §4.1 |
| Guardrail tests | 3 test files listed in §5.3 | updated in-place |
| External consumer imports | see §4.2 map | libcst-rewritten |

### 3.2 Out of scope (HARD STOP if you touch these)

- `position_queries.py` and `operational_mode.py` — stay in `decision_making/primitives/`
  (Addendum #3 §5). Do not move.
- `normalized_reject_reasons.py` (NRR) — stays in `decision_making/contracts/`
  (Addendum #1 §4, Audit §B.3 decision 1).
- `why_codes.py` — stays in `decision_making/contracts/` (re-export layer).
- Anything under `vfoundation/`.
- Anything under `backtest_engine/`, `alpha_search` core logic, `objective_engine` core
  logic — you only touch their **imports**, not their business code.
- Strategy plugin files `apps/reference/domains/strategies/plugins/{aurora_builtin,mean_reversion,md_amr}.py`
  — **imports only** may change; no logic edits.
- Runtime behavior, event payloads, WAL schemas, typed config fields.
- Global pytest hooks.
- CI files, workflows, `.github/**`.
- Memory and docs (except the two controller-authorized doc touches in §5.4).

### 3.3 Explicitly deferred (will be Package 4 or later, DO NOT DO)

- NRR migration to `vfoundation/core/`.
- Removal of shim files created in P2.
- `DecisionMakingDomainConfig` aggregator restructure.
- Any renaming of `aurora_math.py` → `math_kernel.py` (mentioned as possible future in
  Audit §A.1). Keep file names as they are when moving.

---

## 4. Contract surface changes (the only ones allowed in P3)

### 4.1 Registry owner updates in `apps/reference/dictionaries/verb_registry_v1.yaml`

You MUST update exactly these verbs:

| Verb | Current `owner` | New `owner` | `co_emitters` |
| ---- | --------------- | ----------- | ------------- |
| `STRATEGY_SIGNAL_PRODUCED` | `decision_making` | `strategies` | unchanged |
| `STRATEGY_DECISION_BLOCKED` | `decision_making` | `strategies` | unchanged |

For `TRADE_INTENT_REJECTED`: **DO NOT CHANGE.** Audit §B.4 mentioned a conditional change,
but Addendum #1 §1.4 locked the current 4-shaper inventory with a passing test
(`tests/domains/decision_making/test_reject_truth_inventory.py`). Changing owner without
unifying the shaping would break that inventory. Leave it as is.

For any other verb whose sole emitter is a file you are moving to `strategies/runtimes/`:
**STOP** and produce a BLOCKED report listing every such verb with its current emitter file
path and proposed new owner. Do not change it on your own.

### 4.2 External consumer import map (from Audit §7.B.2, frozen for P3)

Libcst must rewrite exactly these import statements. Discover additional consumers via
pre-move grep; if any new consumer appears that is NOT on this list, include it in the
rewrite batch BUT also list it in the report's "Additional consumers found" section with
file path + old/new import.

| Consumer | Old import substring | New import substring |
| -------- | -------------------- | -------------------- |
| `apps/reference/domains/strategies/plugins/aurora_builtin.py` | `apps.reference.domains.decision_making.strategies.aurora.handler` | `apps.reference.domains.strategies.runtimes.aurora.handler` |
| `apps/reference/domains/strategies/plugins/mean_reversion.py` | `apps.reference.domains.decision_making.strategies.mean_reversion.handler` | `apps.reference.domains.strategies.runtimes.mean_reversion.handler` |
| `apps/reference/domains/strategies/plugins/md_amr.py` | `apps.reference.domains.decision_making.strategies.md_amr.handler` | `apps.reference.domains.strategies.runtimes.md_amr.handler` |
| `apps/reference/domains/alpha_search/models/aurora_adapter.py` | `apps.reference.domains.decision_making.primitives.scoring_kernel` | `apps.reference.shared.decision_primitives.scoring_kernel` |
| `apps/reference/domains/objective_engine/adapters.py` | `apps.reference.domains.decision_making.primitives.entry_plan` | `apps.reference.shared.decision_primitives.entry_plan` |
| `apps/reference/domains/objective_engine/adapters.py` | `apps.reference.domains.decision_making.primitives.position_queries` | **unchanged** (stays in DM) |
| `apps/reference/contracts/quadratic_rollout.py` | `apps.reference.domains.decision_making.primitives.scoring_kernel` | `apps.reference.shared.decision_primitives.scoring_kernel` |
| DM-internal callers of moved primitives | `apps.reference.domains.decision_making.primitives.<X>` for X in {scoring_kernel, aurora_math, aurora_policy, entry_plan, exit_manager, tpsl_owner, sizing_margin_first, instrument_quantizer, shields.*} | `apps.reference.shared.decision_primitives.<X>` |
| DM-internal callers of strategy runtimes | `apps.reference.domains.decision_making.strategies.<X>` | `apps.reference.domains.strategies.runtimes.<X>` |
| Test files | all of the above substrings | same rewrites |

### 4.3 Typed config / aggregator

`apps/reference/config/domains/_aggregator.py` must keep seeing `DecisionMakingDomainConfig`
from `apps/reference/config/domains/decision_making.py`. No changes required there. If
your import rewriter touches that path, STOP — that is a bug in the rewriter.

---

## 5. Physical plan

### 5.1 Directory moves (`git mv`)

Create destination directories with `__init__.py` (empty or docstring-only). Then run
`git mv` per the table below. After this, `decision_making/strategies/` and
`decision_making/primitives/{scoring_kernel,aurora_math,aurora_policy,entry_plan,exit_manager,tpsl_owner,sizing_margin_first,instrument_quantizer,shields}` should no longer exist.

```
apps/reference/domains/strategies/
├── registry.py                (exists, unchanged)
├── plugins/                   (exists, imports rewritten per §4.2)
└── runtimes/                  NEW
    ├── __init__.py            NEW empty
    ├── bridge.py              ← decision_making/strategies/bridge.py
    ├── aurora/
    │   ├── __init__.py        ← decision_making/strategies/aurora/__init__.py
    │   ├── handler.py
    │   ├── decision.py
    │   ├── tpsl.py
    │   ├── scoring_helpers.py
    │   ├── holding_period.py
    │   └── config_loader.py
    ├── mean_reversion/
    │   ├── __init__.py
    │   ├── handler.py
    │   └── logger.py
    └── md_amr/
        ├── __init__.py
        ├── handler.py
        └── entry_anchor_artifact.py

apps/reference/shared/decision_primitives/    NEW
├── __init__.py                NEW empty
├── scoring_kernel.py          ← decision_making/primitives/scoring_kernel.py
├── aurora_math.py             ← decision_making/primitives/aurora_math.py
├── aurora_policy.py           ← decision_making/primitives/aurora_policy.py
├── entry_plan.py              ← decision_making/primitives/entry_plan.py
├── exit_manager.py            ← decision_making/primitives/exit_manager.py
├── tpsl_owner.py              ← decision_making/primitives/tpsl_owner.py
├── sizing_margin_first.py     ← decision_making/primitives/sizing_margin_first.py
├── instrument_quantizer.py    ← decision_making/primitives/instrument_quantizer.py
└── shields/
    ├── __init__.py
    ├── base.py
    ├── null_shield.py
    ├── context_shield.py
    ├── memory_shield.py
    └── danger_zone.py
```

Files that **stay** in `decision_making/primitives/`:
- `position_queries.py` (Addendum #3 §2)
- `operational_mode.py` (Addendum #3 §2)

Record the full move-map in
`tools/migrations/dm_split/dm_move_map_p3.csv` with columns `source,destination,reason`.

### 5.2 Shims policy for Package 3

No new shims. Reason: external consumers are a small, known set (§4.2 has 7 files).
Rewrite them in-place. If you discover additional external consumers beyond §4.2 at a
rate greater than 10 files, STOP and ask for shim authorization.

The P2-authorized shims already on disk (e.g. `decision_making/aurora_handler.py` shim)
may continue to exist, unchanged. Do not extend them to cover new relocations. Do not
delete them.

### 5.3 Guardrail test updates

Three test files require targeted edits. All edits are import-path updates plus, where
noted, one new rule. No assertion semantics change.

1. `tests/domains/decision_making/test_layered_boundaries.py`
   - Keep the existing `LAYER_RULES` dict from Addendum #4 §2.
   - Add a new positive assertion: DM production code under
     `apps/reference/domains/decision_making/` MUST NOT import from
     `apps.reference.domains.strategies.runtimes` (this is the Variant B invariant).
   - Move the "DM primitives → DM-only" rule to a new companion function that verifies:
     DM production code that used to import `decision_making.primitives.<X>` now imports
     `shared.decision_primitives.<X>` for every X in §5.1 moved set.
2. `tests/domains/decision_making/test_fe_dm_boundary_guardrails.py`
   - Update target module paths to match the new DM tree.
   - Add rule: "DM production code MUST NOT import from strategies.runtimes".
3. `tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py`
   - Update target module paths. No new rules.

If any of these files has been substantially restructured after P2 in a way that makes
these instructions ambiguous, STOP with a targeted BLOCKED.

### 5.4 Documentation touches (authorized, limited)

- `apps/reference/domains/decision_making/README.md` — only the "Boundaries" / "Layout"
  section: update file inventory to reflect P3 tree. No prose rewrite.
- `apps/reference/domains/decision_making/contracts/domain_dict.json` — remove any verb
  entries whose owner changed to `strategies` in §4.1.

No other docs, no memory writes, no journal writes.

---

## 6. Operating procedure (7 steps, in order)

### Step 1. Baseline capture (BEFORE any change)

Run and save:

```powershell
cd c:\Users\user\Music\Phenix
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest `
  tests/domains/decision_making tests/ops/test_verb_registry_contracts.py `
  tests/domains/strategies tests/domains/alpha_search tests/domains/objective_engine `
  tests/domains/execution_position/test_ep_contract_boundary_guardrails.py `
  -q 2>&1 | Tee-Object -FilePath tools/migrations/dm_split/baseline_pytest_p3.txt
```

```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest -q 2>&1 `
  | Tee-Object -FilePath tools/migrations/dm_split/baseline_pytest_full_p3.txt
```

The expected pre-P3 state inherited from P2:
- focused slice: same 5 failing tests as `baseline_pytest_p2.txt` (aurora_tpsl_fallback
  x2, cmd_process_strategy x2, order_rejected_payload_normalization x1).
- full: 5 pre-existing `tools.*` collection errors, 0 failing.

If your captured baseline differs from that, STOP — something drifted since P2 was
accepted and you need controller direction.

### Step 2. Dependency-graph sanity check (BEFORE any move)

Before any `git mv`, run the P2 audit tool on the current tree:

```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe tools/migrations/dm_split/audit_imports.py `
  --root apps/reference/domains/decision_making `
  --out tools/migrations/dm_split/artifacts/package3_pre_audit.md
```

Confirm:
- `scoring_kernel` imports `aurora_math` and `aurora_policy` — all three move to
  `shared/decision_primitives/` together (same commit), so cycle risk is neutralized.
- `shields/*` imports only stdlib + `primitives/*` — safe to move as a unit.
- Strategy handlers import `primitives.*` — after move they will import from
  `shared.decision_primitives.*` — no cycle, crosses domain layer cleanly.
- No strategy handler imports `core.facade` or `gateway.*` directly (P2 invariant).

If any of these fail, STOP with the exact file + import that breaks the plan.

### Step 3. Plan artifacts (BEFORE any move)

Write:
- `tools/migrations/dm_split/dm_move_map_p3.csv` — all `git mv` rows.
- `tools/migrations/dm_split/artifacts/package3_rename_plan.json` — programmatic plan
  consumed by the libcst rewriter.
- `tools/migrations/dm_split/artifacts/package3_external_consumers_discovered.txt` —
  grep inventory of every file in `apps/` and `tests/` that imports any moved symbol.

### Step 4. Dry run

- Libcst dry-run over all of `apps/` and `tests/`, output unified diff to
  `tools/migrations/dm_split/artifacts/package3_dry.diff`.
- Verify no file outside §4 table scope receives more than import-line changes. If any
  non-import diff appears, STOP.

### Step 5. Apply

1. Create destination dirs with empty `__init__.py`.
2. `git mv` per move-map.
3. Run libcst rewriter (real apply).
4. Update `verb_registry_v1.yaml` per §4.1.
5. Update the 3 guardrail tests per §5.3.
6. Update docs per §5.4.
7. Single logical commit (local only — do NOT push, do NOT open a PR; Addendum #1 §0).

### Step 6. Verification (§12.8 adapted to P3)

All six must pass, artifacts saved to `tools/migrations/dm_split/artifacts/`:

- **C1. Package import.**
  `python -c "import apps.reference.domains.decision_making"` — succeeds.
  `python -c "import apps.reference.domains.strategies.runtimes"` — succeeds.
  `python -c "import apps.reference.shared.decision_primitives"` — succeeds.
  → `package3_package_import.txt`.
- **C2. Focused pytest parity.** Same failing set as `baseline_pytest_p3.txt`.
  → `package3_baseline_parity.txt`.
- **C3. Layered boundaries.** `tests/domains/decision_making/test_layered_boundaries.py`
  green, including the new §5.3.1 invariant. → `package3_layered_boundaries.txt`.
- **C4. Old import grep.**
  `rg -n "apps\.reference\.domains\.decision_making\.strategies\." apps/ tests/ --type py`
  returns zero hits. Same for the 8 moved-primitive module paths. Save to
  `package3_old_import_grep.txt`.
- **C5. DeprecationWarning clean.** `pytest -W error::DeprecationWarning` on the focused
  slice passes (no new deprecation source). Save to
  `package3_deprecationwarning_probe.txt`.
- **C6. Full pytest parity.** Same as `baseline_pytest_full_p3.txt` — collection errors
  identical set, failing set identical set.
  → `package3_full_baseline_parity.txt`.

If ANY of C1–C6 fails, STOP and file a BLOCKED report describing the single smallest
violation row. Do not attempt multi-failure recovery.

### Step 7. Report

Produce exactly two files:
- `tools/migrations/dm_split/artifacts/PACKAGE_3_REPORT.md`
- `tools/migrations/dm_split/artifacts/PACKAGE_3_REPORT.json`

Format (sections 1–8) identical to `PACKAGE_2_REPORT.md`. In section 7 "Open questions
(BLOCKED list)" put `Empty` if C1–C6 passed, otherwise the exact blocker.

Archive any intermediate blocked snapshot as
`PACKAGE_3_REPORT_BLOCKED_<SHORT_TAG>_2026-04-<DD>.md` alongside.

---

## 7. Stop conditions (any of these forces an immediate BLOCKED report)

1. Baseline capture differs from the expected P2-accepted state.
2. A file listed in §5.1 as "moves" does not exist, OR a file not listed as "moves" has
   no clear disposition from §5.1 + §3.2 alone.
3. Any import in `apps/` or `tests/` outside §4.2 table targets a moved symbol AND would
   require more than an import-path rewrite (e.g. because it references a private
   submodule that doesn't exist post-move).
4. A verb other than the two in §4.1 table has a sole-emitter file that is moving.
5. Any circular import appears post-move.
6. Any typed-config or aggregator test fails.
7. Layered-boundaries invariant from §5.3.1 conflicts with any existing production import.
8. Shim authorization implicitly required (see §5.2 threshold of 10 files).
9. Any runtime-behavior diff suggested by the rewriter (e.g. a symbol name collision
   across the two new packages).

For each blocker, the report must contain: file path, current import line, exact
ambiguity sentence, proposed resolution options (without picking one).

---

## 8. Reporting format (mandatory)

`PACKAGE_3_REPORT.md` structure — exactly these headings, nothing else:

```markdown
# Package 3 Report — Variant B Physical Cross-Domain Split

## 0. Context confirmation
(post-P2 tree; reused vs new artifacts; §4 skipped items — must be none)

## 1. Summary
(branch, commits, files moved, imports rewritten, shims added=0, tests added, tests modified)

## 2. Audit sections realized
(bulleted list of Audit + Addenda sections you executed)

## 3. Evidence
(every artifact path under tools/migrations/dm_split/artifacts/)

## 4. Success criteria checklist (§12.8 adapted)
(C1–C6 checkboxes with artifact references)

## 5. Decisions taken
(every non-trivial choice, anchored to this brief's §N or Audit §N.N)

## 6. Deviations from Audit
(None, or enumerated with anchors)

## 7. Open questions (BLOCKED list)
(Empty, or enumerated per §7 format)

## 8. Next package readiness
(either "Refactor complete. Package 4 (NRR → vfoundation) is a future cycle, out of scope."
 or BLOCKED reason)
```

JSON twin mirrors the same structure.

---

## 9. How to hand back

- If all six criteria are green and §7 is empty → the refactor is **complete**. Write
  that explicitly in §8 and do not propose Package 4 as in-scope.
- If any criterion fails or any §7 item is non-empty → STOP at that point, write the
  BLOCKED report, and wait. Do not make recovery attempts.

---

## 10. Quick reference

- Working directory: `c:\Users\user\Music\Phenix`
- Python: `c:/Users/user/Music/Phenix/.venv/Scripts/python.exe`
- Branch: `Phenix_v2`. Do not push. Do not tag. Local commits only.
- Test baseline file names are literal — use them verbatim.
- Artifact directory: `tools/migrations/dm_split/artifacts/` — reuse for consistency.
- Migration toolkit: `tools/migrations/dm_split/` — reuse P2 scripts; only extend if
  strictly necessary and document the extension in §5 of the report.

End of brief.
