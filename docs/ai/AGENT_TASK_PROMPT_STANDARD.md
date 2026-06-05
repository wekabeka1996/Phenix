# AGENT_TASK_PROMPT_V1

Use this structure whenever creating a task prompt for an IDE/CLI agent.

```text
[TASK OBJECTIVE]
Your task is to achieve the following exact goal:
<exact goal>

[SCOPE]
In scope:
- <files/modules/logs/configs/docs>
Out of scope:
- <explicit exclusions>

[EVIDENCE BASE]
Use only directly inspectable evidence from:
- <artifacts>

Do not infer system-wide claims from local evidence.
Do not trust docs over code/runtime when they conflict.

[REASONING PROTOCOL]
Follow strict fail-closed reasoning:
1. Separate FACTS, INFERENCES, ASSUMPTIONS, and UNKNOWNS.
2. Do not present assumptions as facts.
3. If evidence is missing or contradictory, explicitly state what cannot be concluded.
4. Distinguish symptom, root cause, contributing factor, and masking layer.
5. For each major conclusion, explain:
   - cause
   - mechanism
   - effect
   - operational risk
6. Check contracts, invariants, and temporal event order.
7. Do not confuse code presence, tests, and runtime proof.
8. Keep alternative hypotheses alive until evidence rules them out.
9. Keep conclusion scope proportional to evidence scope.
10. Prefer narrow proven conclusions over broad speculative ones.

[CONSTRAINTS]
- Prefer minimal safe change over broad refactor.
- Check for duplication before editing.
- No silent fallbacks.
- No hidden business constants.
- Respect YAML + Pydantic SSOT.
- Register new events/commands if introduced.

[DELIVERABLES]
Return:
1. Executive Summary
2. Proven Facts
3. Inferred Findings
4. Contradictions / Evidence Gaps
5. Root Cause Candidates
6. Risk Ranking
7. Minimal Safe Action
8. Validation Plan
9. What remains unproven

[VALIDATION]
Validation must specify:
- exact files touched
- invariant protected
- tests run
- runtime-facing proof or observability signal
- residual risk

[DONE CRITERIA]
The task is complete only if:
- every major claim is evidence-linked
- uncertainty is localized explicitly
- root cause is not confused with symptom
- proposed action is minimal and testable
- validation is defined
- final REPORT is provided

[PROHIBITED BEHAVIORS]
- Do not invent missing runtime evidence.
- Do not overgeneralize from one module to the whole system.
- Do not call something fixed without validation.
- Do not hide uncertainty with polished language.
- Do not recommend a broad rewrite before localizing the failure.
```
