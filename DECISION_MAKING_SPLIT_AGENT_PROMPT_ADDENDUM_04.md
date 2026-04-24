# Agent Prompt — Addendum #4 (Package 2 layer-rule corrections + aurora_policy relocation)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT.md](DECISION_MAKING_SPLIT_AGENT_PROMPT.md),
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md),
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_02.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_02.md),
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_03.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_03.md).
> This addendum resolves the three blockers in
> `tools/migrations/dm_split/artifacts/PACKAGE_2_REPORT.md §7`.

Effective date: 2026-04-24
Scope: Package 2 only.
Authorized by: controller.

---

## 1. Root-cause classification

The three blockers split cleanly into two categories:

| # | Blocker | Cause | Decision type |
| - | ------- | ----- | ------------- |
| 1 | `core/facade.py` imports `intent.emitter` | LAYER_RULES over-restriction by controller | Rule correction |
| 2 | `core/facade.py` imports `intent.builder` | LAYER_RULES over-restriction by controller | Rule correction |
| 3 | `primitives/scoring_kernel.py` imports `strategies.aurora.policy` | Misplacement of `aurora_policy.py` during Package 2 physical move | Placement correction |
| 4 | `aurora_handler` shim grep target ambiguity | §12.8 criterion 4 wording ambiguity | Criterion clarification |

All four are resolved below. No behavior changes. No contract changes.

---

## 2. LAYER_RULES correction (blockers 1 + 2)

`core` is the composition root. It is the facade that wires
`gates → builder → emitter`. It MUST be allowed to import `intent.builder`
and `intent.emitter`; forbidding those was my error when I wrote §12.5.

Apply this exact `LAYER_RULES` dictionary in
`tests/domains/decision_making/test_layered_boundaries.py`:

```python
LAYER_RULES = {
    # core is the composition root; it wires downstream layers.
    # It must not import concrete strategy runtimes (they are plugin-loaded).
    "core": {"forbid": ["strategies"]},
    # gateway owns strategy dispatch but via registry, not direct strategy imports.
    "gateway": {"forbid": ["strategies"]},
    # gates evaluate pre-emit policy; they do not compose intent.
    "gates": {"forbid": ["strategies", "intent.builder", "intent.emitter"]},
    # intent emits canonical records; strategies are orchestrated above it.
    "intent": {"forbid": ["strategies"]},
    # primitives are pure helpers; no upward imports, no strategies.
    "primitives": {"forbid": ["core", "gateway", "gates", "intent", "strategies", "observability"]},
    # contracts are leaf definitions.
    "contracts": {"forbid": ["core", "gateway", "gates", "intent", "strategies", "primitives"]},
    # observability is side-channel; no strategy coupling.
    "observability": {"forbid": ["strategies"]},
}
```

The only diff from the previously-implemented rules is the `core` row:
`["strategies", "intent.builder", "intent.emitter"]` → `["strategies"]`.

No other layer rules change. No new positive tests required beyond what
Package 2 already added.

### 2.1 Rationale footnote for the test file

Append a short comment above `LAYER_RULES` stating:

```python
# Rule: core is the composition root and may import any layer below it,
# except concrete strategy runtimes (those are registry/plugin-mediated).
# See DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_04.md §2.
```

---

## 3. `aurora_policy.py` relocation (blocker 3)

### 3.1 Evidence

`apps/reference/domains/decision_making/strategies/aurora/policy.py:1-18`
explicitly documents itself as a pure policy module:

- no emit, no mutation, no lifecycle truth
- no config-tree access, no handler state
- all public functions pure, state passed explicitly

This is the textbook definition of a `primitives/` resident. Its current
placement under `strategies/aurora/` reflects name grouping ("aurora*"), not
layer semantics. The layered-boundary violation in `scoring_kernel.py` is the
structural proof: a primitive needs it, so it must be a primitive.

### 3.2 Binding placement

Move:

- `apps/reference/domains/decision_making/strategies/aurora/policy.py`
  → `apps/reference/domains/decision_making/primitives/aurora_policy.py`

Use `git mv` so history is preserved. Update
`tools/migrations/dm_split/dm_move_map.csv` with this corrective row
(append only; do not rewrite prior rows).

### 3.3 Consumer rewrites (libcst)

Exactly two call sites (confirmed by the controller via grep):

| File | Old import | New import |
| ---- | ---------- | ---------- |
| `apps/reference/domains/decision_making/primitives/scoring_kernel.py:34` | `from apps.reference.domains.decision_making.strategies.aurora.policy import (...)` | `from apps.reference.domains.decision_making.primitives.aurora_policy import (...)` |
| `apps/reference/domains/decision_making/strategies/aurora/scoring_helpers.py:14` | `from apps.reference.domains.decision_making.strategies.aurora.policy import SideBiasState` | `from apps.reference.domains.decision_making.primitives.aurora_policy import SideBiasState` |

Run the same libcst rewriter you used in the main Package 2 pass over the
whole repo; any missed external consumer MUST also be rewritten in-place
(same rule as before: no external shims authorized outside of those already
listed in §12.4; this module is internal and had no public-API export in
§7.A.2).

### 3.4 Layer compliance after move

- `primitives/aurora_policy.py` imports only stdlib + `dataclasses` — pure.
  LAYER_RULES for `primitives` are satisfied.
- `primitives/scoring_kernel.py` → `primitives/aurora_policy`: same-layer
  import, allowed.
- `strategies/aurora/scoring_helpers.py` → `primitives/aurora_policy`:
  strategies → primitives, allowed.

---

## 4. §12.8 criterion 4 clarification (blocker 4)

The original criterion said: "old `aurora_handler` import grep finds exactly
the shim". That was intended to prove the shim is the only surviving surface
of the old path. The agent implemented shims without echoing the old import
literal inside them, so the grep returns zero hits — which is actually the
stronger outcome.

Revised criterion (replaces §12.8 item 4 for Package 2 only):

> **Criterion 4 (revised).** Both of the following must hold:
> 1. `ripgrep -n "from apps.reference.domains.decision_making.aurora_handler"
>    -- apps/ tests/` returns zero hits outside of the shim file itself.
> 2. `python -c "from apps.reference.domains.decision_making.aurora_handler
>    import AuroraHandler"` succeeds via the shim.
>
> If (1) is zero everywhere including the shim file, item (2) proves the
> shim still resolves and that is acceptable. If (1) has hits only inside
> the shim file(s) at the old location, that is also acceptable.

Record the exact ripgrep output and the import-probe stdout as artifacts
`package2_aurora_handler_grep.txt` and `package2_aurora_handler_import.txt`.

---

## 5. Order of operations for resume

1. Patch `LAYER_RULES` per §2. Do not touch any other test logic.
2. `git mv` `strategies/aurora/policy.py` → `primitives/aurora_policy.py`.
3. Update `dm_move_map.csv` (append row only).
4. Run libcst rewriter over repo; capture `package2_aurora_policy_rewrite.diff`.
5. Re-run `pytest tests/domains/decision_making/test_layered_boundaries.py` — green.
6. Re-run `python -c "import apps.reference.domains.decision_making"` — green.
7. Re-run §12.6 verification steps that were skipped after the first blocker:
   - Focused `pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py -q`
     against `baseline_pytest_p2.txt` — failing-set identical.
   - Full `pytest -q` against `baseline_pytest_full_p2.txt` — failing-set identical.
   - `-W error::DeprecationWarning` for shim loads — either green, or list every
     DeprecationWarning as an expected BLOCKED item.
   - Revised criterion 4 artifacts per §4.
8. Write final `PACKAGE_2_REPORT.{md,json}`. Archive the blocked snapshot as
   `PACKAGE_2_REPORT_BLOCKED_LAYER_2026-04-24.md`.
9. `§7 Open questions` must be empty.

---

## 6. Out of scope for this addendum

- No changes to `gateway/strategy_gateway.py`.
- No changes to `intent/` internals.
- No new shims.
- No alterations to `config_models` or typed config.
- No changes to strategy plugin registration paths.

If any additional layer violation appears AFTER steps 1–7 complete, stop and
produce a new BLOCKED report enumerating the exact violation rows.

---

## 7. Resume instruction

Continue Package 2 from step 1 of §5. Anchor the decisions in
`PACKAGE_2_REPORT.md §5` to `Addendum #4 §2` (LAYER_RULES), `Addendum #4 §3`
(aurora_policy move), and `Addendum #4 §4` (criterion 4).
