# Agent Prompt — Addendum #3 (Package 2 Variant A placement gaps)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT.md](DECISION_MAKING_SPLIT_AGENT_PROMPT.md),
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md),
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_02.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_02.md).
> This addendum extends Audit §7.A.1 with two previously missing Variant A placements.

Effective date: 2026-04-24
Scope: Package 2 only.
Authorized by: controller.

---

## 1. Why this addendum exists

Audit §7.A.1 was the SSOT for Variant A destinations, but two live modules under
`apps/reference/domains/decision_making/` were not assigned to any subpackage:

- `position_queries.py` — `PositionQueries` class; read-only portfolio snapshot
  interpretation + margin-first sizing candidates; no FSM emit; consumed by
  `decision_making.py`, `aurora_handler.py`, `objective_gate_evaluator.py`,
  `mean_reversion_handler.py`.
- `operational_mode.py` — `ModeManager` class; normalizes `OperationalMode`
  enum + computes memory-shield overrides; no FSM emit; consumed by
  `aurora_config_loader.py`, `aurora_handler.py`.

Both are side-effect-free helpers downstream of typed config, with no outbound
emit and no cross-domain dependency. They fit the `primitives/` layer defined
in §7.A.1 (pure helpers layered below handlers/core/gates/intent).

---

## 2. Binding placements

| Source | Variant A destination |
| --- | --- |
| `apps/reference/domains/decision_making/position_queries.py` | `apps/reference/domains/decision_making/primitives/position_queries.py` |
| `apps/reference/domains/decision_making/operational_mode.py` | `apps/reference/domains/decision_making/primitives/operational_mode.py` |

Both rows MUST be present in `tools/migrations/dm_split/dm_move_map.csv` with
identical formatting to the existing `primitives/*` rows.

---

## 3. Layer-rule impact (§12.5 LAYER_RULES)

Both modules become members of the `primitives` layer. That layer already has
the rule:

- Allowed imports: `contracts`, stdlib, typed config, other `primitives`.
- Forbidden imports: `core`, `gateway`, `gates`, `intent`, `strategies`,
  `observability`.

Verify before `git mv`:

- `position_queries.py` currently imports `.normalized_reject_reasons` and
  `.sizing_margin_first` — both are primitives per §7.A.1. Stays compliant.
- `operational_mode.py` currently imports `apps.reference.config_models` only.
  Stays compliant.

No layer-rule amendments are needed.

---

## 4. Consumer impact (handled by libcst rewriter, §12.3)

The rewriter must update these call sites without behavior changes:

- `decision_making.py:28` — `from .position_queries import PositionQueries`
  → `from .primitives.position_queries import PositionQueries`
- `aurora_handler.py:65,71`
- `aurora_config_loader.py:33`
- `objective_gate_evaluator.py:20`
- `mean_reversion_handler.py:73`

Equivalent absolute-import forms must also be rewritten. Any external repo
consumers discovered by the pre-move grep must also be rewritten in the same
commit batch (Variant A internal move allows cross-file import rewrites; still
no shim authorization — this is an internal restructure, external callers keep
the same public-api symbol path only if Audit §7.A.2 marks them; for these two
modules §7.A.2 lists nothing, so external repo callers, if any, must be updated
in place).

---

## 5. Audit §B.2 reconciliation

Audit §B.2 (Variant B consumer map) states that `position_queries.py` stays in
`decision_making/` in the Variant B physical split. That line is preserved and
is not in conflict with this addendum: Variant A moves it to
`decision_making/primitives/`, and Variant B (Package 3) would subsequently
keep it inside `decision_making/primitives/` — same tree root. When Package 3
starts, re-read §B.2 and confirm the Variant B destination is
`apps/reference/domains/decision_making/primitives/position_queries.py` (i.e.
no further move for it in Package 3).

`operational_mode.py` is not mentioned in §B.2; treat it the same way —
stays in `decision_making/primitives/` through both packages.

---

## 6. Acceptance for this addendum (Package 2 gate subset)

- `dm_move_map.csv` contains both rows above.
- After `git mv` + rewriter:
  - `grep -rn "from .position_queries import" apps/ tests/` returns zero hits.
  - `grep -rn "from .operational_mode import" apps/ tests/` returns zero hits.
  - `grep -rn "decision_making.position_queries" apps/ tests/` returns zero
    hits (old absolute path).
  - `grep -rn "decision_making.operational_mode" apps/ tests/` returns zero
    hits (old absolute path).
  - `grep -rn "decision_making.primitives.position_queries" apps/ tests/`
    returns exactly the five consumer sites listed in §4 plus the new module
    itself and the test inventory file if it references this module.
- `python -c "import apps.reference.domains.decision_making"` succeeds.
- `pytest tests/domains/decision_making tests/ops/test_verb_registry_contracts.py -q`
  produces the same failing-set as `baseline_pytest_p2.txt`.

The global Package 2 acceptance (§12.8 six criteria + LAYER_RULES test + shims
+ DeprecationWarning + full-run parity with `baseline_pytest_full_p2.txt`)
still applies on top of this subset.

---

## 7. Everything else unchanged

- Base prompt Package 2 scope unchanged.
- Addenda #1 and #2 unchanged and still in force.
- No new tests are mandated by this addendum. Any LAYER_RULES test written per
  §12.5 must include both modules implicitly via their new path.
- No runtime behavior may change.

---

## 8. Resume instruction

Proceed with Package 2: build `dm_move_map.csv` using §7.A.1 + this addendum,
dry-run the libcst rewriter, apply, run the full §12.6 runbook, produce
`PACKAGE_2_REPORT.{md,json}`. Anchor these two placements to "Addendum #3 §2".
