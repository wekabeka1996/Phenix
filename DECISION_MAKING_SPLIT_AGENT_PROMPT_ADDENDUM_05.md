# Agent Prompt — Addendum #5 (Package 3 baseline path correction)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md).
> This addendum corrects the Step 1 baseline commands in that brief.

Effective date: 2026-04-24
Scope: Package 3, Step 1 only.
Authorized by: controller.

---

## 1. Root cause

The Package 3 brief §6 Step 1 focused-baseline command listed
`tests/domains/objective_engine` as a pytest target. That path does not exist in the
current workspace. The actual location of those tests is
`tests/apps/reference/domains/objective_engine/` (three files: `test_objective_engine.py`,
`test_runtime.py`, `test_realized_objective.py`). The agent correctly refused to
substitute the path on its own.

Verified by controller via file search:

- `tests/domains/alpha_search/` — **exists** (keep).
- `tests/domains/strategies/` — **exists** (keep).
- `tests/domains/execution_position/test_ep_contract_boundary_guardrails.py` — **exists** (keep).
- `tests/domains/objective_engine/` — **does not exist** (replace).
- `tests/apps/reference/domains/objective_engine/` — **exists, 3 test files** (use this).

This is a brief authoring error, not a repository drift. No file needs to be created or
restored.

---

## 2. Binding correction

Resolution option 1 from the blocker report is authorized: replace
`tests/domains/objective_engine` with `tests/apps/reference/domains/objective_engine` in
Step 1 and in all downstream parity comparisons.

The corrected Step 1 focused baseline command is:

```powershell
cd c:\Users\user\Music\Phenix
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest `
  tests/domains/decision_making tests/ops/test_verb_registry_contracts.py `
  tests/domains/strategies tests/domains/alpha_search `
  tests/apps/reference/domains/objective_engine `
  tests/domains/execution_position/test_ep_contract_boundary_guardrails.py `
  -q 2>&1 | Tee-Object -FilePath tools/migrations/dm_split/baseline_pytest_p3.txt
```

The full baseline command is unchanged:

```powershell
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest -q 2>&1 `
  | Tee-Object -FilePath tools/migrations/dm_split/baseline_pytest_full_p3.txt
```

---

## 3. Expected-state guidance (relaxed for first capture)

The brief's "expected pre-P3 state" sentence referenced a specific 5-failure focused set
from `baseline_pytest_p2.txt`. Because the focused slice is now wider (it adds
`tests/apps/reference/domains/objective_engine`, `tests/domains/strategies`, and
`tests/domains/alpha_search` that were not in the P2 focused slice), the exact failure
count may differ. Treat the current capture as **authoritative** for Package 3 parity.

Concretely:

- Capture `baseline_pytest_p3.txt` and `baseline_pytest_full_p3.txt` with the corrected
  commands in §2 above.
- Use those two files as the **sole** parity oracles for C2 and C6 in §6 Step 6.
- Do NOT cross-compare to `baseline_pytest_p2.txt` for Package 3. That file was P2's
  oracle; Package 3 has a different focused slice and its own oracle.
- In the final report §3 Evidence, cite `baseline_pytest_p3.txt` and
  `baseline_pytest_full_p3.txt` as the baselines; cite `package3_baseline_parity.txt`
  and `package3_full_baseline_parity.txt` as the post-apply parity reports.

If the captured focused baseline contains zero failures, that is acceptable — the parity
rule then reduces to "post-apply focused slice also has zero failures".

---

## 4. Scope guardrails (unchanged, restated)

- §4 of the Package 3 brief (contract surface changes allowed in P3) is unchanged.
- §5 (physical plan) is unchanged.
- §7 stop conditions are unchanged, with this clarification: stop condition 1
  ("Baseline capture differs from the expected P2-accepted state") is replaced for
  Package 3 by: "Baseline capture produces a collection error, environment import error,
  or Python interpreter error". A non-zero failure count in the captured baseline is
  **not** a stop condition; it becomes the new parity oracle.

---

## 5. Resume instruction

Resume Package 3 from Step 1 using the corrected commands in §2. Overwrite
`tools/migrations/dm_split/baseline_pytest_p3.txt` with the new capture. Proceed
through Steps 2–7 normally. Anchor the resume decision in the final
`PACKAGE_3_REPORT.md §5` to "Addendum #5 §2".

Archive the current blocker snapshot as
`tools/migrations/dm_split/artifacts/PACKAGE_3_REPORT_BLOCKED_BASELINE_DRIFT_2026-04-24.md`
(already done by the agent; leave in place).

End of addendum.
