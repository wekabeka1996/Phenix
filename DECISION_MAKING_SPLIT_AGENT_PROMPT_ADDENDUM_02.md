# Agent Prompt — Addendum #2 (unblock §1.3 registry shape)

> Attach alongside
> [DECISION_MAKING_SPLIT_AGENT_PROMPT.md](DECISION_MAKING_SPLIT_AGENT_PROMPT.md)
> and
> [DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md](DECISION_MAKING_SPLIT_AGENT_PROMPT_ADDENDUM_01.md).
> This addendum supersedes Addendum #1 §1.3 only. Everything else in Addendum #1
> remains in force.

Effective date: 2026-04-24
Scope: Package 1 §1.3 only.
Authorized by: controller.

---

## 1. Why this addendum exists

Addendum #1 §1.3 authorized `owners`, `co_owners`, or "explicit bless of `co_emitters`"
for `ALPHA_SCORE_CALCULATED`. The agent correctly verified that
`apps/reference/dictionaries/verb_registry_v1.yaml` contains **no** `owners` or
`co_owners` fields anywhere, only `owner` and `co_emitters`. Under the fail-closed
rule, that forced a block.

Registry-wide evidence, collected by the controller:

- [apps/reference/dictionaries/verb_registry_v1.yaml:454](apps/reference/dictionaries/verb_registry_v1.yaml)
  `TRADE_EXECUTED` — `owner: position_tracking`, `co_emitters: [adapters, execution_position]`.
- [apps/reference/dictionaries/verb_registry_v1.yaml:468](apps/reference/dictionaries/verb_registry_v1.yaml)
  `TRADE_INTENT_REJECTED` — `owner: decision_making`, `co_emitters: [execution_position]`.
- [tests/domains/execution_position/test_ep_contract_boundary_guardrails.py](tests/domains/execution_position/test_ep_contract_boundary_guardrails.py)
  already contains the pattern
  `test_trade_intent_rejected_has_co_emitters` / `test_trade_executed_has_co_emitters`,
  asserting that `co_emitters` is the sanctioned shape for dual-emission contracts.

This is precedent. `co_emitters` is the registry's existing, tested representation
for exactly the situation at hand.

---

## 2. Binding decision

For `ALPHA_SCORE_CALCULATED`:

- Keep `owner: alpha_search` (unchanged).
- Add `co_emitters: [decision_making]`.
- Keep `schema:` and `since:` unchanged.
- Replace the current single-line `note:` with a line that mirrors the schema's
  dual-producer wording, e.g.:
  `note: "alpha_search is primary emitter; decision_making co-emits per schema variant (see apps/reference/domains/alpha_search/schemas/alpha_score_calculated_v1.json)."`
- Do **not** add `owners`, `co_owners`, or any other new field.
- Do **not** relocate the schema.
- Do **not** touch emitter source files.

This closes §1.3 using precedent only. No registry-format invention occurs.

---

## 3. Test coupling

The addendum-authorized test update from Addendum #1 §1.3 step 4 is narrowed:

- If `tests/ops/test_verb_registry_contracts.py` asserts `owner == alpha_search`
  for `ALPHA_SCORE_CALCULATED`, **leave it unchanged** — the owner is still
  `alpha_search`.
- If it asserts the verb has no `co_emitters`, update that assertion to accept
  `co_emitters == ["decision_making"]`.
- Add (optional, only if it fits the existing test file's convention one-to-one)
  a single assertion mirroring `test_trade_intent_rejected_has_co_emitters`:
  `test_alpha_score_calculated_has_co_emitters` that reads the registry and checks
  `"decision_making" in entry["co_emitters"]`. Put it in
  `tests/ops/test_verb_registry_contracts.py` only if that file already hosts
  similar per-verb checks; otherwise skip — the EP boundary test file is not the
  right home.

No other test changes.

---

## 4. Acceptance gate for §1.3 (redefined)

- `grep -nE "ALPHA_SCORE_CALCULATED|co_emitters:" apps/reference/dictionaries/verb_registry_v1.yaml`
  shows the verb entry with `owner: alpha_search` and `co_emitters: [decision_making]`.
- `tests/ops/test_verb_registry_contracts.py` green.
- `tests/domains/alpha_search/judge/test_expert_provider_integration.py::TestNonJudgeProviderUnchanged::test_non_judge_provider_emits_alpha_score_calculated`
  green.
- `tests/domains/execution_position/test_ep_contract_boundary_guardrails.py` green
  (regression check; unrelated but proves we did not break the `co_emitters` reader).

---

## 5. Everything else in Addendum #1 stays

- §1.1 (`QUADRATIC_DECISION_TRACE` → register) unchanged.
- §1.2 (`HANDLER_READINESS_DIAGNOSTICS` → remove) unchanged.
- §1.4 (`TRADE_INTENT_REJECTED` → document only, passing inventory test) unchanged.
- §2 Baseline parity rule unchanged (failing-set identical; passing-set may grow by
  exactly the one §1.4 inventory test; if §3 of this addendum adds the optional
  co_emitters per-verb check, that counts as a **second** allowed new passing test
  in Package 1 — noted here so it does not trigger a STOP).
- §4 Unauthorized items unchanged.

---

## 6. Resume instruction

Resume Package 1 from the point you blocked. Write a new `PACKAGE_1_REPORT.md` /
`.json` that supersedes the current blocked report. Archive the §1.3 blocked report
as `PACKAGE_1_REPORT_BLOCKED_1_3_2026-04-24.md`. Anchor §1.3 decisions to "Addendum #2 §2".
