# Agent Prompt — Addendum #6 (Package 3 full-baseline error-roster policy)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_PACKAGE_3.md)
> and [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_05.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_05.md).
> This addendum resolves the contradiction between Addendum #5 §3 and §4.

Effective date: 2026-04-24
Scope: Package 3, Step 1 baseline interpretation + Step 6 C6 parity rule only.
Authorized by: controller.

---

## 1. Root cause

Addendum #5 §3 said "treat the current capture as authoritative for Package 3 parity".
Addendum #5 §4 said "Baseline capture produces a collection error … is a stop condition."
Those two sentences contradict each other when the repository already has pre-existing
collection errors that are orthogonal to decision_making (the well-known `tools.*`
module-not-found roster, plus a `neocortex` PPO test that needs `torch`). The agent
correctly flagged the contradiction.

The intent of Addendum #5 §4 was to block ONLY on errors that are themselves caused by
decision_making (e.g. a broken `import apps.reference.domains.decision_making...`). It was
not meant to block on pre-existing environment / missing-module errors that have nothing
to do with the refactor. §4 was sloppily worded. This addendum fixes it.

---

## 2. Binding definitions

Treat the full baseline as a set of "collection / error signatures" and a set of
"failing tests". P3 parity is set-comparison, not textual equality.

- `baseline_collection_errors` := the set of test file paths that appear as
  `ERROR <path>` in `baseline_pytest_full_p3.txt` (the corrected capture from
  Addendum #5). For the current capture, this set is exactly:
  1. `tests/apps/reference/domains/neocortex/PPO/ppo_library_v2/tests/test_buffer.py`
  2. `tests/integration/test_metrics_summary.py`
  3. `tests/test_data_contract.py`
  4. `tests/test_parquet_pipeline.py`
  5. `tests/test_stress_actuator.py`
- `baseline_failures` := the set of `FAILED <nodeid>` lines in the same file
  (currently 0 from the agent's report).
- Same for `focused_baseline_errors` / `focused_baseline_failures` from
  `baseline_pytest_p3.txt`. Current focused set: 5 failures, 0 errors, all named in
  the agent's §3.

These 4 sets are the **sole** Package 3 parity oracle.

---

## 3. DM-caused-error classifier

A collection or failure is "DM-caused" if and only if the traceback contains any import
chain that includes one of these substrings:

- `apps.reference.domains.decision_making`
- `apps.reference.domains.strategies.runtimes`
- `apps.reference.shared.decision_primitives`
- `apps/reference/domains/decision_making/`
- `apps/reference/domains/strategies/runtimes/`
- `apps/reference/shared/decision_primitives/`

Any other import error — `torch`, `tools.metrics_summary`, `tools.parquet_contract`,
`tools.parquet_pipeline`, `tools.system_stress_calibration`, a timeout, a fixture
environment issue — is **not DM-caused** and is allowed in the baseline oracle.

---

## 4. Corrected stop condition (replaces Addendum #5 §4 last paragraph)

Stop condition 1 for Package 3 is:

> The baseline capture produces a collection error, failure, or Python crash whose
> traceback matches a DM-caused signature per §3. A pre-existing non-DM collection error
> or environment import error is explicitly **allowed** and becomes part of the oracle.

The current capture contains zero DM-caused errors and zero DM-caused failures at
baseline (all 5 errors and 5 focused failures are pre-existing, not DM-caused). Step 1
is therefore **complete**. Resume from Step 2.

---

## 5. Corrected C6 parity rule (replaces Package 3 brief §6 Step 6 C6 wording)

For Package 3 full-pytest parity, the post-apply run must satisfy:

- `post_collection_errors ⊆ baseline_collection_errors` — that is, P3 does NOT introduce
  a new error. It MAY reduce the set (some tests might collect after the refactor that
  did not before, which is fine). It MUST NOT add to the set.
- `post_failures ⊆ baseline_failures ∪ focused_baseline_failures` — that is, P3 does NOT
  introduce a new failure. The union with the focused set covers the case where the
  focused slice surfaces failures that the full slice skipped/erroed around.
- For any element `post ⊖ baseline` (symmetric-difference non-empty), classify per §3:
  - if any new element is DM-caused → STOP with BLOCKED naming that element.
  - if the set strictly shrank and no element is DM-caused → accept as parity pass and
    note the shrinkage under `Deviations from Audit` with the one-line note
    "Environment improved; no DM-caused delta".

The focused slice (C2) rule is the same logic applied to
`baseline_pytest_p3.txt` vs the post-apply focused capture.

---

## 6. Environment freeze

Do NOT install `torch` or reconstruct `tools.metrics_summary`, `tools.parquet_contract`,
`tools.parquet_pipeline`, or `tools.system_stress_calibration` as part of Package 3.
Those are outside Package 3 scope and would add non-Package-3 changes to a revertable
commit group. They remain pre-existing environment drift, documented and frozen.

---

## 7. Acceptance snapshot recorded here

For record, Package 3's baseline oracles are now locked:

| Oracle | Count | Description |
| ------ | ----: | ----------- |
| `focused_baseline_failures` | 5 | aurora_tpsl x2, cmd_process_strategy x2, order_rejected_payload_normalization x1 |
| `focused_baseline_errors` | 0 | — |
| `baseline_collection_errors` | 5 | neocortex PPO test_buffer, metrics_summary, data_contract, parquet_pipeline, stress_actuator |
| `baseline_failures` | 0 | — |

Any post-P3 deviation from these sets that is DM-caused is a Package 3 regression.
Anything else is orthogonal environment behavior and is ignored.

---

## 8. Resume instruction

Proceed to Package 3 Step 2 (pre-audit) immediately using the currently captured
baseline files as the oracle. Record in `PACKAGE_3_REPORT.md §5` that "baseline
interpretation follows Addendum #6 §2–§5" and that "all 5 baseline collection errors and
5 focused baseline failures are pre-existing and non-DM-caused per §3 classifier".

Archive the current blocker snapshot as
`tools/migrations/dm_split/artifacts/PACKAGE_3_REPORT_BLOCKED_FULL_BASELINE_IMPORT_ERRORS_2026-04-24.md`
(already done by the agent; leave in place).

End of addendum.
