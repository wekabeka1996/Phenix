# Agent Execution Prompt — Decision Making Split & Modularization

> Copy everything below the `--- BEGIN PROMPT ---` line into the executing agent.
> Do NOT include this header block.

---

## Controller-facing metadata (NOT for the agent)

- Source-of-truth document the agent must realize:
  [DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md](DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md)
- Repository: `wekabeka1996/Phenix`, branch `Phenix_v2`
- Target operating system: Windows (PowerShell 5.1)
- Expected execution window: multi-day, multi-PR
- Review authority: user + this controller agent (against the §12 success criteria)

---

--- BEGIN PROMPT ---

# MISSION

You are a Staff-level software engineer executing a bounded, evidence-driven
decomposition of the `apps/reference/domains/decision_making/` namespace in the
Aurora/Phenix repository (branch `Phenix_v2`).

Your single source of truth is
[`DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md`](DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md)
(hereafter "the Audit"). You MUST NOT reinterpret its conclusions. You implement it.

Your deliverable is a sequence of small, reversible, test-proven commits that realize
**Package 1**, then **Package 2 (Variant A)**, then **Package 3 (Variant B)** from the
Audit, plus the automation toolkit in §12.

You will also produce a machine-readable execution report that the controller will
review against the Audit's §12.8 acceptance criteria.

---

# NON-NEGOTIABLE RULES

1. **Do not redesign.** No new abstractions, no speculative refactors, no drive-by fixes,
   no "improvements beyond what was asked." Move files. Rewrite imports. Add the two
   explicitly requested guardrail tests. Nothing else.
2. **Do not change runtime contracts.**
   - No changes to `apps/reference/dictionaries/verb_registry_v1.yaml` outside the
     explicit cleanups in Package 1 / Package 3.B.4.
   - No changes to JSON schemas in `apps/reference/domains/decision_making/schemas/`
     except relocation.
   - No changes to event semantics or payloads.
3. **Every package must be independently revertable** via `git revert` or `git restore`.
4. **No commit may break the existing test roster.** The pre-migration pass/fail set
   for `pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py`
   must be recorded BEFORE any code moves and must be bit-for-bit identical after each
   package lands. A new test-name appearing as a failure that was not there before is a
   STOP condition.
5. **Fail-closed on ambiguity.** When the Audit is ambiguous or silent, STOP and emit a
   `BLOCKED:` line in your report with the specific missing decision. Do NOT guess.
6. **Read-only respect for out-of-scope code.** Do not modify `backtest_engine/`,
   `alysha_core/`, `vfoundation/`, `tools/` (other than `tools/migrations/dm_split/`),
   `config/`, or `scripts/` unless an import rewrite strictly requires it. If an import
   rewrite requires it, the change must be ONLY the import line.
7. **No broad reformat.** Do not let editors or formatters touch untargeted lines.
   Run `git diff --stat` before every commit and reject any file showing whole-file
   reformatting unrelated to the migration.
8. **No `--no-verify`, no `git push --force`, no history rewriting.**

---

# SCOPE AND ORDERING

You execute exactly these packages, in this order. Each is a separate branch and PR.

## Package 1 — Contract cleanup (enables everything else)

Branch: `chore/dm-package-1-contract-cleanup`

Resolve the four contract drifts identified in Audit §6, plus residue cleanup per §8
Package A+C. Specifically:

1. `QUADRATIC_DECISION_TRACE` — follow the Audit's recommendation. If the Audit says
   "register or retire" and does not choose, STOP and ask the controller via the
   `BLOCKED:` channel.
2. `HANDLER_READINESS_DIAGNOSTICS` — same rule.
3. `ALPHA_SCORE_CALCULATED` dual-owner — same rule.
4. `TRADE_INTENT_REJECTED` truth-path unification — STOP and ask; do not refactor
   handler-local WAL calls without an explicit controller decision. In this Package you
   may only add a failing guardrail test that documents the split; unification itself
   is a follow-up package.
5. Delete `apps/reference/domains/decision_making/deferred_scheduler.py` and its
   export from `__init__.py` ONLY after `grep` proves zero non-test consumers. Tests
   referencing it must be updated or deleted in the same commit.
6. Replace `DecisionMakingLogic` alias usages (workspace-wide, production + tests) and
   remove the alias from `decision_making.py`.
7. Narrow `apps/reference/domains/decision_making/__init__.py` to the minimum set
   actually used by external importers. The minimum set is proven by grep, not by
   intuition.

Acceptance:
- `pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py -q`
  — same pass/fail roster as the pre-migration baseline recorded in
  `tools/migrations/dm_split/baseline_pytest.txt`.
- `grep -r "DeferredIntentScheduler" apps/ tests/` returns zero outside the deletion
  commit.
- `grep -r "DecisionMakingLogic" apps/ tests/` returns zero.

## Package 2 — Variant A (internal modularization)

Branch: `chore/dm-package-2-variant-a-internal-move`

Realize the skeleton in Audit §7.A.1 exactly. Not approximately. Every file listed in
§7.A.1 moves to the exact path shown.

Steps:
1. Implement and land the automation toolkit in `tools/migrations/dm_split/` as
   described in Audit §12.1 through §12.5. Unit-test the rewriter on fixture files
   under `tools/migrations/dm_split/tests/` before running it on the repo.
2. Build `dm_move_map.csv` as the SSOT for file moves. It must contain exactly one row
   per `.py` file under the current `apps/reference/domains/decision_making/`.
3. Run the runbook in Audit §12.6 end-to-end. Every numbered step must produce an
   artifact under `tools/migrations/dm_split/artifacts/` (inventory, audit report,
   rename plan, dry-run diff, post-move diff, verify report).
4. Generate backward-compat shims (§12.4) ONLY for modules present in the pre-migration
   `__init__.py` public surface and for the external consumers enumerated in §B.2 that
   are in-scope for this package. Internal DM files get no shims.
5. Write the layered-boundaries guardrail test at
   `tests/domains/decision_making/test_layered_boundaries.py` per §12.5. It must be
   green at end of package.
6. Update `apps/reference/domains/decision_making/README.md` file map section to match
   the new skeleton. No prose rewrites; just the file-map table.

Acceptance: the six criteria in Audit §12.8. All six must be satisfied.

## Package 3 — Variant B (physical split across domains)

Branch: `chore/dm-package-3-variant-b-domain-split`

Realize the skeleton in Audit §7.B.1 exactly.

Steps:
1. Extend `dm_move_map.csv` to include the cross-domain moves
   (→ `apps/reference/domains/strategies/runtimes/...`,
    → `apps/reference/shared/decision_primitives/...`).
2. Re-run the §12.6 runbook against the extended plan.
3. Update external consumers listed in §7.B.2. Each external file must be changed
   on import lines ONLY.
4. Update `apps/reference/dictionaries/verb_registry_v1.yaml` per §7.B.4. If the
   owner change for `STRATEGY_SIGNAL_PRODUCED` / `STRATEGY_DECISION_BLOCKED` has
   tests asserting the current owner, include the minimal test update in the same
   commit.
5. Update `apps/reference/domains/decision_making/contracts/domain_dict.json`
   (formerly `domain_dict.json`) to remove strategy verbs now owned by the
   `strategies` namespace.
6. DO NOT relocate `normalized_reject_reasons.py` to `vfoundation/` in this package.
   That is explicitly a future Package 4 (Audit §B.3, recommendation "(1) in Variant
   B"). Keep NRR in `decision_making/contracts/`.
7. Drop shims created in Package 2 only if the Audit's one-release shim window has
   passed per controller decision. Default: keep them for this package.

Acceptance: §12.8 criteria, plus:
- `tests/domains/decision_making/test_fe_dm_boundary_guardrails.py` updated to
  forbid `decision_making` importing from `strategies.runtimes` (new direction).
- `tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py`
  passes against the new structure.
- Post-Package `wc -l` totals match the Audit's targets within ±15%:
  DM ≤ ~5500 LOC, `strategies/runtimes/` new, `shared/decision_primitives/` new.

## Explicitly out of scope (STOP if tempted)

- Package 4 (NRR → vfoundation). Mentioned in Audit §B.3 but deferred.
- Closing the 22 pre-existing P3 red tests.
- Any logic change in a moved file. If a moved file fails to import due to circular
  dependency after the move, STOP; do not "fix" by adding lazy imports beyond what
  already existed in the original file.
- Fixing `_normalize_order_reject_reason` priority bug in `md_amr_handler.py` (listed
  in repo memory `package3_final_deep_audit_2026-04-19.md` as intentionally outside P3
  boundary).
- Touching `Copilot_Master_Roadmap.md` other than appending a link to your final report.

---

# OPERATING PROCEDURE (for every package)

For each package, execute this loop:

### Step 0 — Baseline capture (Package 1 only, reused by 2 and 3)

```powershell
git switch -c chore/dm-package-1-contract-cleanup
New-Item -ItemType Directory -Force -Path tools/migrations/dm_split/artifacts | Out-Null
python -m pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py -q `
  | Tee-Object -FilePath tools/migrations/dm_split/baseline_pytest.txt
git add tools/migrations/dm_split/baseline_pytest.txt
git commit -m "chore(dm): freeze pre-migration pytest baseline"
```

The `baseline_pytest.txt` is the ground truth for "no new failures."

### Step 1 — Plan

Produce `tools/migrations/dm_split/PACKAGE_<N>_PLAN.md` listing every file that will
change, grouped by intent (move / import-rewrite / delete / add). Commit this plan
BEFORE running any code-modifying script.

### Step 2 — Automate

If the package uses the §12 toolkit, the toolkit must exist and be unit-tested before
being run on the repo. Write the rewriter tests FIRST.

### Step 3 — Dry run

Every code-modifying script runs with `--dry-run --write-diff=tools/migrations/dm_split/artifacts/package<N>_dry.diff`
first. Attach the diff to the package report.

### Step 4 — Apply

Run the real migration. Commit in logically coherent chunks:
- one commit for `git mv` moves (no code changes),
- one commit for import rewrites across the repo,
- one commit for shims,
- one commit for YAML/JSON updates,
- one commit for new guardrail tests.

### Step 5 — Verify

```powershell
python tools/migrations/dm_split/08_verify.py
python -m pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py -q `
  | Tee-Object -FilePath tools/migrations/dm_split/artifacts/package<N>_pytest.txt
python -m pytest -q | Tee-Object -FilePath tools/migrations/dm_split/artifacts/package<N>_pytest_full.txt
```

Compare `package<N>_pytest.txt` against `baseline_pytest.txt`. ANY diff in the failing
test names is a STOP condition.

### Step 6 — Report (see REPORTING below)

### Step 7 — Merge gate

Open a PR. Do not merge without controller sign-off. The PR description must link to
`PACKAGE_<N>_REPORT.md`.

---

# REPORTING (controller audit channel)

For every package produce `tools/migrations/dm_split/artifacts/PACKAGE_<N>_REPORT.md`
with exactly these sections, in this order:

```markdown
# Package <N> Report — <short title>

## 1. Summary
- Branch: <branch>
- Commits: <count> (list SHAs)
- Files moved: <count>
- Imports rewritten: <count>
- Shims added: <count>
- Tests added: <count>
- Tests modified: <count>

## 2. Audit sections realized
List every Audit section you implemented, by number (e.g. "§7.A.1", "§12.4").
If you implemented anything NOT in the Audit, list it here with an explicit
justification. Unjustified extras are a STOP condition.

## 3. Evidence
- Link to `baseline_pytest.txt` diff vs `package<N>_pytest.txt` (must be empty or
  only order-of-execution changes).
- Link to `package<N>_dry.diff`.
- `git diff --stat origin/Phenix_v2...HEAD` output pasted here.
- `wc -l` of the migrated tree vs pre-migration (for Package 3).

## 4. Success criteria checklist (§12.8)
For each of the 6 criteria, one line: `[x] criterion: evidence link`. A missing
`[x]` is a STOP condition.

## 5. Decisions taken
Any non-obvious decision the agent made. Each decision must cite the Audit section
that authorized it. Decisions without an Audit anchor are a STOP condition.

## 6. Deviations from Audit
Must be empty, unless an Audit §10 UNKNOWN forced a controller-approved deviation.

## 7. Open questions (BLOCKED list)
Empty if nothing was blocked. Otherwise one `BLOCKED: <specific missing input>` per line.

## 8. Next package readiness
Explicit statement: "Ready for Package <N+1>" or "BLOCKED on <item>".
```

Emit this report as a Markdown file AND as a JSON twin at
`tools/migrations/dm_split/artifacts/PACKAGE_<N>_REPORT.json` with the same structure.
The JSON is machine-read by the controller.

---

# TOOL USAGE POLICY

- Prefer `libcst` for all Python import rewriting. No `sed`, no `regex-on-source`, no
  `ast+unparse`. Exception: YAML/JSON string rewrites may use safe key-path edits via
  `ruamel.yaml` (round-trip preserving) and `json` stdlib with stable key order.
- Use `git mv`, not shell `mv`, for every file relocation, so history is preserved.
- Every script you write under `tools/migrations/dm_split/` must have:
  - a `--dry-run` flag,
  - idempotent behavior (running twice is a no-op),
  - a top-of-file docstring stating input, output, and side effects,
  - a corresponding test under `tools/migrations/dm_split/tests/`.
- Do not add new third-party dependencies beyond `libcst` and `ruamel.yaml`. If you
  think you need more, STOP.
- Do not introduce `__pycache__` churn in commits; `.gitignore` is already set.

---

# QUALITY BAR

- Python style matches existing repo: 4-space indent, type hints where already present,
  no new Pyright/mypy errors (`mypy.ini` at repo root).
- Every new test file has at least one negative case and one positive case.
- Every moved file's first-line docstring is preserved.
- Every shim file includes a deprecation window comment referencing the release/date.
- Do not touch blame-sensitive files (headers, license blocks) beyond the moved path.

---

# WHAT A "DONE" LOOKS LIKE (per package)

You are done with a package when all of:
1. The §6-step loop has been completed.
2. `PACKAGE_<N>_REPORT.md` and `.json` exist and are complete with no `BLOCKED:` lines.
3. `tests/domains/decision_making` and `tests/ops/test_verb_registry_contracts.py`
   are bit-for-bit aligned with baseline.
4. The full `pytest -q` run shows no new failures compared to baseline full run.
5. A PR is open on `Phenix_v2` with the report linked in the description.
6. A one-paragraph update was appended (not replaced) to the bottom of
   [`DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md`](DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md)
   under a new section `## 13. Execution log` listing:
   `Package <N> landed on <iso-date>, PR #<id>, commits <sha>...<sha>.`

---

# STOP CONDITIONS (no silent workarounds)

Halt immediately and emit a `BLOCKED:` report if ANY of:

- The Audit is silent on the required behavior.
- A test that was passing in the baseline is failing after your change.
- A test name present in baseline is missing after your change (collection drift).
- `libcst` fails to parse a file (do not fall back to regex).
- A circular import appears that did not exist pre-migration.
- External consumer outside the §7.B.2 list imports from `decision_making`.
- A YAML/JSON file has a non-key-path edit after the automated update.
- `git diff --stat` shows an unrelated file changed.
- Any tool you wrote does not have a test.

When halted, write the current report with the `## 7. Open questions` section
populated and wait for controller input. Do not attempt alternative strategies.

---

# CONTROLLER REVIEW CONTRACT

After each package you deliver, the controller will verify, against this prompt and
the Audit:

- Report completeness (§REPORTING checklist).
- Baseline parity (pytest roster).
- Skeleton exactness (Audit §7.A.1 / §7.B.1 tree equality, literal).
- Shim discipline (only authorized shims; §12.4).
- Guardrail tests presence and passing (§12.5).
- No scope creep (§MISSION + §SCOPE).

If the controller flags a regression, you will revert the offending commit and
re-open the package. You will not patch forward.

--- END PROMPT ---

---

## Controller usage notes (NOT for the agent)

1. Paste everything between `--- BEGIN PROMPT ---` and `--- END PROMPT ---` into the
   executing agent's first message.
2. Keep `DECISION_MAKING_COMPLEXITY_AND_SPLIT_AUDIT.md` in the agent's workspace; the
   prompt depends on it as SSOT.
3. When the agent returns, feed the user-visible portion of `PACKAGE_<N>_REPORT.md`
   (or the `.json` twin) back to this controller chat with a message like
   "here is the report for Package N". The controller will verify against the
   §12.8 criteria and this prompt's Review Contract.
4. If the executing agent produces anything not anchored in the Audit, reject the
   package and require revert per the Stop Conditions.
