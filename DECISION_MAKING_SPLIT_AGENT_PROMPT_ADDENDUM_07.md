# Agent Prompt — Addendum #7 (Package 3 Step 2 shield import policy)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md),
> Addenda #5 and #6.
> This addendum corrects the Package 3 brief §6 Step 2 "shields import policy" check.

Effective date: 2026-04-24
Scope: Package 3, Step 2 pre-audit rule only.
Authorized by: controller.

---

## 1. Root cause

Package 3 brief §6 Step 2 bullet 2 said: `shields/* imports only stdlib + primitives/*`.

That wording was too narrow. The `apps/reference/core/` tree is a shared, cross-domain
utility layer (clocks, enums, bootstrap helpers). It is the project's equivalent of
stdlib-plus-framework. Shields already use it correctly: `memory_shield.py` lazy-imports
`LiveClock` from `apps.reference.core.time.clock` inside `__init__` as a fallback when
no clock is injected. That pattern remains valid after the shield unit moves to
`apps/reference/shared/decision_primitives/shields/`, because the target shared/ tree
is allowed to depend on `apps.reference.core.*` and `vfoundation.*` just like any other
shared utility.

Controller-verified facts:

- `LiveClock` definition: `apps/reference/core/time/clock.py:84`.
- Only shield that touches it: `primitives/shields/memory_shield.py:192` (lazy import
  inside `__init__`, with `clock: Optional["Clock"] = None` as the primary injection
  point).
- Other shields (`null_shield.py`, `danger_zone.py`, `context_shield.py`, `base.py`)
  import only from `primitives/shields/base.py` — no external deps.

This is an import-policy amendment, not a code change. Agent correctly fail-closed.

---

## 2. Binding rule correction

Replace Package 3 brief §6 Step 2 bullet 2 with:

> `shields/*` may import from: stdlib; `apps.reference.domains.decision_making.primitives.*`
> (pre-move) or `apps.reference.shared.decision_primitives.*` (post-move); shared
> cross-domain utilities under `apps.reference.core.*`; and `vfoundation.*`. Shields
> MUST NOT import from any other `apps.reference.domains.*` subtree, from `core/`,
> `gates/`, `gateway/`, `intent/`, `strategies/*`, or `observability/` of
> `decision_making/`.

Under this rule, `memory_shield.py`'s `from apps.reference.core.time.clock import LiveClock`
is compliant. The shield subtree may move as a unit as planned in brief §5.1.

---

## 3. Pre-audit tool update

The `tools/migrations/dm_split/audit_imports.py` script that the agent added in the
current attempt must encode the rule from §2. Specifically, its shield check must
treat these import-prefix whitelists as allowed:

- `apps.reference.domains.decision_making.primitives.`
- `apps.reference.shared.decision_primitives.`
- `apps.reference.core.`
- `vfoundation.`
- any stdlib module (no dot-prefix match to `apps.` or `tests.`)
- intra-package `apps.reference.domains.decision_making.primitives.shields.` imports

Any other `apps.` or `tests.` prefix remains a violation and still must BLOCK.

Re-run the pre-audit after updating the script. Expected result: the shield check
goes from `[ ]` to `[x]` with zero BLOCKED shield rows. Commit the new script along
with the final Package 3 move commit (same revertable group).

---

## 4. Post-move layer-rule guardrail update

After the shield unit moves to `apps/reference/shared/decision_primitives/shields/`,
update `tests/domains/decision_making/test_layered_boundaries.py` to add a positive
assertion mirroring §2 above:

- For every `.py` file under `apps/reference/shared/decision_primitives/shields/`, parse
  imports; every import starting with `apps.` must start with
  `apps.reference.shared.decision_primitives.` or `apps.reference.core.`.
- For every `.py` file under `apps/reference/shared/decision_primitives/` (not shields),
  every import starting with `apps.` must start with
  `apps.reference.shared.decision_primitives.` or `apps.reference.core.`.

No other LAYER_RULES rows change. This is a single positive assertion added to the
existing test file, not a new test file.

---

## 5. Scope guardrails (unchanged)

- No behavior changes to `memory_shield.py` or any other shield module.
- No changes to `apps/reference/core/time/clock.py`.
- No `LiveClock` inlining, no dependency inversion, no refactor.
- The lazy-import pattern in `memory_shield.py:192` stays as-is through the move.
- The shield unit moves together; no split-move of the 6 shield files.

---

## 6. Resume instruction

Proceed with Package 3 from Step 2 as follows:

1. Update `tools/migrations/dm_split/audit_imports.py` per §3 and re-run. Expected:
   all four Step 2 checks green.
2. Proceed to Step 3 (plan artifacts) with the shield unit included in the move-map.
3. Continue Steps 4–7 normally.
4. When writing `tests/domains/decision_making/test_layered_boundaries.py` updates
   during Step 5, include the §4 positive assertion for the new shared tree.
5. In the final `PACKAGE_3_REPORT.md §5`, record that "shield import policy follows
   Addendum #7 §2" and "pre-audit tool updated per Addendum #7 §3".

Archive the current blocker snapshot alongside prior P3 blockers with suffix
`_SHIELD_CLOCK_IMPORT_2026-04-24.md`.

End of addendum.
