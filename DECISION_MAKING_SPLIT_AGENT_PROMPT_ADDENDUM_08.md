# Agent Prompt — Addendum #8 (Package 3 P2 shim retargeting)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md),
> Addenda #5, #6, #7.
> This addendum resolves the Step 4 dry-run conflict between Package 3 brief §5.2
> ("P2 shims may continue to exist, unchanged") and the physical move of their
> targets out of `decision_making/`.

Effective date: 2026-04-24
Scope: Package 3, Step 5 apply — shim retargeting only.
Authorized by: controller.

---

## 1. Root cause

Package 3 brief §5.2 says the P2-authored shim files may continue to exist
unchanged. Package 3 §6 Steps 3-5 physically move the modules those shims
re-export (`strategies/*/handler`, `primitives/entry_plan`, `primitives/scoring_kernel`)
out of `apps/reference/domains/decision_making/`. Keeping the shims literally
unchanged leaves `from apps.reference.domains.decision_making.strategies.aurora.handler import *`
pointing to a path that no longer exists after apply.

§5.2 meant "do not delete the shims, do not change their public API, do not
change the deprecation surface". It did not mean "freeze the import path string
literals against a subsequent physical move". The dry-run correctly exposed
this gap. Agent correctly fail-closed.

---

## 2. Authorized edit class

Inside each shim in the §3 allowlist, the agent MAY update:

1. The `from <path> import *` statement's `<path>` — retarget to the Package 3
   post-move location.
2. The `from <path> import <Name>` statement's `<path>` — same retarget, same
   symbol name.
3. The post-move path substring inside the `warnings.warn("... is moved to
   <path>", ...)` message — keep the warning truthful.

The agent MUST NOT change, in any shim:

- The module docstring (historical old→new documentation stays as-is).
- The `import warnings` line.
- The `DeprecationWarning` category.
- The `stacklevel` argument.
- The `# noqa` comments.
- The set of re-exported names (the named `import <Name>` lines keep the same
  `<Name>`).
- The file path of the shim itself (the shim stays at its current path).
- Any behavior, order of statements, or addition of new statements.

No new shim files are authorized under this addendum. The shim count stays at
exactly 5 — see §3.

---

## 3. Explicit shim allowlist with retarget map

Only these five files are authorized for the §2 edit class. Any other shim
edit remains forbidden.

| Shim file (unchanged path) | Pre-move target string | Post-move target string |
|---|---|---|
| `apps/reference/domains/decision_making/aurora_handler.py` | `apps.reference.domains.decision_making.strategies.aurora.handler` | `apps.reference.domains.strategies.runtimes.aurora.handler` |
| `apps/reference/domains/decision_making/md_amr_handler.py` | `apps.reference.domains.decision_making.strategies.md_amr.handler` | `apps.reference.domains.strategies.runtimes.md_amr.handler` |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | `apps.reference.domains.decision_making.strategies.mean_reversion.handler` | `apps.reference.domains.strategies.runtimes.mean_reversion.handler` |
| `apps/reference/domains/decision_making/entry_plan.py` | `apps.reference.domains.decision_making.primitives.entry_plan` | `apps.reference.shared.decision_primitives.entry_plan` |
| `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` | `apps.reference.domains.decision_making.primitives.scoring_kernel` | `apps.reference.shared.decision_primitives.scoring_kernel` |

In every row the retarget is applied three times in the file: once in each of
the two `from … import` lines and once as the path substring inside
`warnings.warn(...)`.

Before committing, confirm that the post-move target strings above exactly
match the destinations recorded in `tools/migrations/dm_split/dm_move_map_p3.csv`
and `tools/migrations/dm_split/artifacts/package3_rename_plan.json`. If any
cell here disagrees with the plan artifacts, BLOCK and report — do not silently
adjust either side.

The other ten P2 shims not listed here must remain literally unchanged. If the
dry-run report names more than five shims under rewrite, BLOCK and report.

---

## 4. Brief §5.2 clarification

Read Package 3 brief §5.2 as:

> The P2-authored shim files continue to exist with their public API and
> deprecation surface unchanged. Their import-path string literals and their
> `warnings.warn` destination-path substring are retargeted to the Package 3
> post-move locations per Addendum #8 §3. No other shim edits are authorized.
> No new shim files are authorized.

This is a clarification, not a new authorization class. The shims' reason for
existing (keeping old call sites working for one deprecation cycle) is preserved.

---

## 5. Toolkit and apply sequencing

The agent's existing parameterized `04_rewrite_imports.py` will already
retarget the `from … import` lines inside the five shims as part of its normal
sweep. That behavior is now explicitly authorized for these five files.

The `warnings.warn(...)` message substring is a plain string literal, not an
import, so libcst will not retarget it. The agent MAY either:

- Do a single `str.replace(pre_move, post_move)` pass limited to the five
  files listed in §3, executed right after `04_rewrite_imports.py` finishes, or
- Edit each of the five `warnings.warn` strings directly.

Either approach is acceptable. Record the chosen approach in
`PACKAGE_3_REPORT.md §5 Decisions taken`.

After retarget, re-run pre-audit (`audit_imports.py`) to confirm zero stale
`apps.reference.domains.decision_making.strategies.*` or
`apps.reference.domains.decision_making.primitives.entry_plan` /
`apps.reference.domains.decision_making.primitives.scoring_kernel` imports
remain anywhere in `apps/` or `tests/` — including inside the shims.

---

## 6. Success criteria adjustments

Add to Addendum #6 §5 set-based parity check:

- C4 "old import grep": include the five shim files in the scan. Expected
  result after apply: zero remaining old-path occurrences repo-wide.
- C5 "DeprecationWarning clean probe": importing each of the five shims must
  still raise exactly one `DeprecationWarning` with the new (post-move) path
  substring in the message. The deprecation behavior is preserved; only the
  path inside the message is updated.

No changes to C1, C2, C3, C6.

---

## 7. Resume instruction

1. Re-run Step 4 dry-run after confirming the §3 retarget map matches the
   plan artifacts. Expected `changed_files` count is unchanged (the five shim
   rewrites were already counted in the 135-file dry-run).
2. Proceed to Step 5 apply: `git mv`, libcst real rewrite, shim message
   retarget per §5, verb_registry updates, the three guardrail test edits,
   doc touches.
3. After apply, run the extended pre-audit per §5 and confirm clean.
4. Execute Step 6 C1-C6 per Addendum #6 §5 set-based parity, now including
   §6 above.
5. Produce `PACKAGE_3_REPORT.{md,json}`. In §5 Decisions taken record:
   - "Shim retargeting follows Addendum #8 §2-§3."
   - Chosen approach for the `warnings.warn` message update (§5).
   - The five shims by path with before/after target strings (§3 table).

Archive the current blocker snapshot as
`PACKAGE_3_REPORT_BLOCKED_SHIM_POLICY_CONFLICT_2026-04-24.{md,json}` (already
done) next to the prior archive.

End of addendum.
