# Agent Prompt — Addendum #9 (Package 3 shared-tree config_models policy)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md),
> Addenda #5, #6, #7, #8.
> This addendum amends Addendum #7 §4 shared-tree positive assertion to include
> the shared config-schema namespace.

Effective date: 2026-04-24
Scope: Addendum #7 §4 shared-tree import-prefix rule only.
Authorized by: controller.

---

## 1. Root cause

Addendum #7 §4 wrote:

> For every `.py` file under `apps/reference/shared/decision_primitives/` (not
> shields), every import starting with `apps.` must start with
> `apps.reference.shared.decision_primitives.` or `apps.reference.core.`.

That enumeration was incomplete. `apps/reference/config_models.py` is a single
shared module that houses Pydantic config schemas (`ExitManagerConfig`,
`DangerZoneExitType`, etc.). It is cross-domain infrastructure — the config
equivalent of `apps.reference.core.*` — not a runtime domain. The moved
`apps/reference/shared/decision_primitives/exit_manager.py` legitimately imports
from it to type its config surface; this was already true pre-P2, was unchanged
by P2, and is unchanged by P3. Addendum #7 §4 simply failed to list that prefix.

Same failure pattern as the `memory_shield.py` → `LiveClock` case that produced
Addendum #7: controller enumerated allowed prefixes too narrowly and omitted a
legitimate shared-infrastructure namespace. Agent correctly fail-closed.

---

## 2. Classification

Shared infrastructure namespaces that any module under
`apps/reference/shared/decision_primitives/` may import, with no further
authorization, are:

- `apps.reference.core.*` — runtime infrastructure (clocks, enums, bootstrap).
- `apps.reference.config_models` — config-schema Pydantic models (single module).
- `vfoundation.*` — project-wide foundation utilities.
- stdlib.

These are treated as the "platform + schema layer" of the repo. They are
deliberately allowed across all shared/ and domain-primitive trees because
re-homing them into any single domain would create a worse coupling. No other
`apps.*` prefix is authorized from `shared/decision_primitives/`.

---

## 3. Addendum #7 §4 amendment

Replace Addendum #7 §4 in its entirety with:

> After the shield unit moves to `apps/reference/shared/decision_primitives/shields/`,
> update `tests/domains/decision_making/test_layered_boundaries.py` to add a
> positive assertion mirroring Addendum #7 §2 and Addendum #9 §2:
>
> - For every `.py` file under `apps/reference/shared/decision_primitives/shields/`,
>   parse imports; every import starting with `apps.` must start with
>   `apps.reference.shared.decision_primitives.`, `apps.reference.core.`, or
>   `apps.reference.config_models`.
> - For every `.py` file under `apps/reference/shared/decision_primitives/`
>   (not shields), every import starting with `apps.` must start with
>   `apps.reference.shared.decision_primitives.`, `apps.reference.core.`, or
>   `apps.reference.config_models`.
>
> No other LAYER_RULES rows change. This is a single positive assertion added
> to the existing test file, not a new test file.

---

## 4. Pre-audit tool update

`tools/migrations/dm_split/audit_imports.py` shield and shared-tree checks must
add `apps.reference.config_models` to the allowed-prefix whitelist alongside
the existing `apps.reference.core.` entry. Re-run the pre-audit after updating
the script. Expected: zero BLOCKED rows for the shared tree, including
`exit_manager.py`.

Under this rule, the line
`from apps.reference.config_models import ExitManagerConfig, DangerZoneExitType`
in `apps/reference/shared/decision_primitives/exit_manager.py` is compliant.

---

## 5. Scope guardrails (unchanged)

- No runtime/behavior changes to `exit_manager.py`, `config_models.py`, or any
  other moved file.
- No config-surface relocation. `apps/reference/config_models.py` stays where it
  is. Option 3 from the agent's blocker report is explicitly declined —
  relocating the shared config module is not a Package 3 task and introducing it
  here would exceed brief scope.
- No file-specific exemptions in the guardrail test. Option 2 from the agent's
  blocker report is explicitly declined — the rule must hold for every file
  under the shared tree, and the fix is to list all legitimate shared-infra
  prefixes generically.
- Addendum #8 shim retargeting scope is unchanged.
- LAYER_RULES (runtime `test_layered_boundaries` rows unrelated to shared/)
  unchanged.
- Shim count unchanged.

---

## 6. Resume instruction

From the current partial-apply state, continue:

1. Update `tools/migrations/dm_split/audit_imports.py` per §4 and re-run the
   shared-tree check. Expected: clean, including `exit_manager.py`.
2. Complete Addendum #8 §7 step 2 remaining items:
   - Shim `warnings.warn(...)` message retarget per Addendum #8 §5 (the
     five-file scoped `str.replace` or direct edit).
   - `verb_registry_v1.yaml` owner updates for `STRATEGY_SIGNAL_PRODUCED`
     and `STRATEGY_DECISION_BLOCKED` → `owner=strategies` (per P3 brief §5;
     `TRADE_INTENT_REJECTED` unchanged per Addendum #1 §1.4).
   - Three guardrail test edits: the existing `test_layered_boundaries.py`
     update now carries the revised §3 positive assertion.
   - `README.md` layout touch + `domain_dict.json` cleanup per P3 brief.
3. Step 6: verify C1-C6 per Addendum #6 §5 set-based parity plus
   Addendum #8 §6.
4. Step 7: produce `PACKAGE_3_REPORT.{md,json}`. In §5 Decisions taken record:
   - "Shared-tree import policy follows Addendum #9 §2-§3."
   - The three allowed shared-infra `apps.*` prefixes from §2.

Archive the current blocker snapshot as
`PACKAGE_3_REPORT_BLOCKED_SHARED_TREE_IMPORT_POLICY_2026-04-24.{md,json}`
(already done) next to the prior archives.

End of addendum.
