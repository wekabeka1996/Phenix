# Agent Prompt — Addendum #1 (Package 1 decisions)

> Hand this file to the executing agent together with
> [DECISION_MAKING_SPLIT_AGENT_PROMPT.md](DECISION_MAKING_SPLIT_AGENT_PROMPT.md).
> This addendum supersedes conflicting lines inside Package 1 of the base prompt.
> Audit document unchanged.

Effective date: 2026-04-24
Scope: Package 1 only. Package 2 and Package 3 remain as defined in the base prompt.
Authorized by: controller (user + controller agent).

---

## 0. Meta: relax git policy

Git housekeeping is handled by the user, not the agent.

- Drop base prompt rules about `git push --force`, history rewriting, staging
  discipline, `git diff --stat` gates, and PR opening. The agent still uses `git mv`
  for file relocations (so history is preserved) and still commits logically coherent
  chunks, but all branch pushes, PR lifecycles, merges, and `.gitignore` reasoning are
  out of scope.
- The `artifacts/` directory being `.gitignore`-d is fine. Reports go there. The user
  commits what they want.
- Every other NON-NEGOTIABLE RULE, STOP CONDITION, and REPORTING requirement in the
  base prompt **remains in force**. Only git-operational discipline is relaxed.

---

## 1. Contract decisions for Package 1

These four decisions are now authoritative. The agent MUST implement them exactly as
written. No further interpretation is permitted. If implementation details surface a
concrete sub-question, emit a `BLOCKED:` line per base-prompt policy; do not choose
silently.

### 1.1 `QUADRATIC_DECISION_TRACE` — REGISTER

Rationale: verb is actively emitted by
[apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py),
consumed by forensic tooling, already exported in local
[domain_dict.json](apps/reference/domains/decision_making/domain_dict.json).
Retiring a live emitter is a bigger change than registering it; registration is
additive and non-breaking.

Required change:

1. In [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml),
   add an entry for `QUADRATIC_DECISION_TRACE` with:
   - `owner: decision_making`
   - `kind: event`
   - `status: active`
   - `schema: apps/reference/domains/decision_making/schemas/quadratic_decision_trace_v1.json`
     (the file already exists — do not create a new schema).
   - `emitters`: list the one actual emitter module and function if the existing
     registry format expects it; otherwise mirror the shape used by sibling
     `decision_making`-owned events in the same file. Use grep on an existing entry
     as the template (e.g. `DECISION_TRACE_EMITTED`). Do not invent new fields.
2. Do not modify the schema file.
3. Do not modify the emitter call site.
4. No `domain_dict.json` change needed for this item in Package 1 (Package 3.B.4
   will rewrite that file anyway).

Acceptance for this item:

- `tests/ops/test_verb_registry_contracts.py` remains green.
- A grep proves the verb is now registered: `grep -n "QUADRATIC_DECISION_TRACE"
  apps/reference/dictionaries/verb_registry_v1.yaml` returns ≥1 match.

### 1.2 `HANDLER_READINESS_DIAGNOSTICS` — REMOVE

Rationale: registered in `verb_registry_v1.yaml` and exported in
[domain_dict.json](apps/reference/domains/decision_making/domain_dict.json), but
workspace search found **no runtime emitter**. A declared-but-unemitted verb is a
false observability contract. Removal is pure cleanup.

Required change:

1. Delete the `HANDLER_READINESS_DIAGNOSTICS` entry from
   [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml).
2. Delete its row from
   [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json).
3. Delete any JSON schema file uniquely dedicated to this verb. If the schema is
   shared, leave it and stop — emit a `BLOCKED:` note with the shared-schema path.
4. Fix any tests that hard-code the name by grep: if a test asserts this verb exists,
   either the test is stale (delete it) or the test asserts "all verbs in registry
   have schema" in which case no change is needed. Do not guess; if there is genuine
   test coupling, `BLOCKED:`.

Acceptance:

- `grep -rn "HANDLER_READINESS_DIAGNOSTICS" apps/ tests/` returns zero.
- Full pytest baseline parity preserved (`tests/ops/test_verb_registry_contracts.py`
  green).

### 1.3 `ALPHA_SCORE_CALCULATED` — EXPLICIT DUAL-OWNER

Rationale: two real emitters exist
([apps/reference/domains/decision_making/event_handlers.py](apps/reference/domains/decision_making/event_handlers.py)
and [apps/reference/domains/alpha_search/backtest_plugin.py](apps/reference/domains/alpha_search/backtest_plugin.py)),
and the schema
[apps/reference/domains/alpha_search/schemas/alpha_score_calculated_v1.json](apps/reference/domains/alpha_search/schemas/alpha_score_calculated_v1.json)
already documents two payload variants. Rename/migration would be invasive and is out
of scope for a contract-cleanup package. Making dual-ownership explicit is the
minimum-risk resolution.

Required change:

1. In `verb_registry_v1.yaml`, update the `ALPHA_SCORE_CALCULATED` entry:
   - If the registry format supports a list, set `owners: [alpha_search, decision_making]`.
   - If the format supports only a single `owner` scalar, add a co-owner field the
     registry already recognizes (grep for an existing dual-owner entry; otherwise
     add `co_owners: [decision_making]` IF AND ONLY IF a sibling entry demonstrates
     that field name elsewhere in the same file). If no precedent exists,
     `BLOCKED:` — do not invent a new registry field.
2. Leave the schema file untouched; its dual-variant documentation is already correct.
3. Update the accompanying registry comment or `description` (if such field exists)
   to match the schema wording: "Emitted by alpha_search and decision_making; two
   payload variants."
4. If `tests/ops/test_verb_registry_contracts.py` asserts single-owner semantics,
   update the test to assert the new dual-owner shape. This is the only test change
   authorized here. Do not touch production code.

Acceptance:

- `tests/ops/test_verb_registry_contracts.py` green.
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py::TestNonJudgeProviderUnchanged::test_non_judge_provider_emits_alpha_score_calculated`
  green.
- Registry entry visually shows both owners.

### 1.4 `TRADE_INTENT_REJECTED` — DOCUMENT THE SPLIT, DO NOT UNIFY

Rationale: four shaping paths
([intent_emitter.py](apps/reference/domains/decision_making/intent_emitter.py),
[aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py),
[mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py),
[md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py)) exist
today. Unification is a standalone refactor that does not belong to a contract-cleanup
package. The Audit §6 row #4 explicitly classifies this as "split truth," not a bug
to fix in Package 1.

Required change:

1. Add a read-only markdown memo:
   [docs/contracts/REJECT_TRUTH_SPLIT.md](docs/contracts/REJECT_TRUTH_SPLIT.md)
   (create the folder if missing). Content: list the 4 shaping paths with exact file
   paths and line citations, label each as canonical / handler-local-WAL /
   handler-local-emit, mark the whole surface as "frozen as-is; unification deferred
   to a dedicated future package."
2. Add a **passing inventory guardrail** test:
   `tests/domains/decision_making/test_reject_truth_inventory.py`. Shape:

   ```python
   # Asserts the known set of TRADE_INTENT_REJECTED shaping paths is unchanged.
   # Purpose: lock the current split until a dedicated unification package runs.
   EXPECTED_SHAPERS = {
       ("apps/reference/domains/decision_making/intent_emitter.py", "canonical"),
       ("apps/reference/domains/decision_making/aurora_handler.py", "handler_local_wal"),
       ("apps/reference/domains/decision_making/mean_reversion_handler.py", "handler_local_wal"),
       ("apps/reference/domains/decision_making/md_amr_handler.py", "handler_local_emit"),
   }
   ```
   The test scans those files for the known emit/WAL call patterns and asserts that
   the discovered set equals `EXPECTED_SHAPERS`. Passing today, it will fail if
   anyone later adds a fifth shaping path or removes one — exactly the fence we need.

3. **No failing test.** No `xfail`. No `skip`. The base prompt's instruction about
   "a failing guardrail test that documents the split" is superseded by this point:
   the guardrail is a passing inventory lock, not a failing assertion. This removes
   the internal conflict with the pytest-baseline-parity rule.

Acceptance:

- New memo exists.
- New test passes.
- `tests/domains/decision_making` roster grows by exactly one new passing test name.
  Baseline parity is redefined for Package 1 as: **no previously passing test starts
  failing; no previously failing test changes its failure signature; new passing
  tests are allowed only in the exact file added by Package 1.4**.

---

## 2. Baseline parity rule — explicit restatement

The original base-prompt wording ("bit-for-bit identical roster") is hereby refined:

- Set of **failing** test names: must be identical before and after Package 1.
  Every item in the pre-migration `baseline_pytest.txt` failing section appears in
  the post-Package 1 run with the same name and the same first-line reason.
- Set of **passing** test names: may grow by exactly one — the new inventory test
  from §1.4. Any other growth is a STOP condition.
- Set of **collected** test names: otherwise identical; no test disappears except
  stale tests deleted as part of §1.2 `HANDLER_READINESS_DIAGNOSTICS` removal (if any
  exists), in which case it must be explicitly listed in `PACKAGE_1_REPORT.md §5`.

This rule is the post-Package-1 acceptance gate. Package 2 and Package 3 revert to
the strict "no roster change at all" rule.

---

## 3. How to report back

Append the resolutions you implemented to `PACKAGE_1_REPORT.md §5 Decisions taken`,
one bullet per sub-section (§1.1–§1.4), each citing **this addendum section number**
as the Audit anchor. That satisfies the base-prompt requirement that every decision
be anchored.

Close out the prior `BLOCKED:` report by writing a new revision of
`PACKAGE_1_REPORT.md` / `.json` with `## 7. Open questions` empty. Keep the old
blocked version alongside it as `PACKAGE_1_REPORT_BLOCKED_2026-04-24.md` for audit
trail.

---

## 4. What is still NOT authorized in Package 1

Do not touch any of the following, despite proximity:

- The deferred scheduler removal rule from base prompt §Package 1.5 remains as
  written.
- The `DecisionMakingLogic` alias removal remains as written.
- The `__init__.py` narrowing remains as written.
- Any change to handler-local reject WAL/emit call sites.
- Any schema content change.
- Any change to `Copilot_Master_Roadmap.md`.

If you detect scope creep, STOP.

---

## 5. Reopen instruction

Once this addendum is loaded, resume Package 1 at
base-prompt Step 0 (Baseline capture). Treat the prior `BLOCKED:` report as history.
