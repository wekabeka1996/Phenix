# Claude Code Project Protocol

Read first:
- docs/ai/LLM_REASONING_CONSTITUTION.md
- docs/ai/AURORA_DOMAIN_PROTOCOL.md
- docs/ai/AGENT_TASK_PROMPT_STANDARD.md
- docs/ai/AGENT_REPORT_SCHEMA.md
- docs/ai/DONE_CRITERIA.md
- docs/ai/VERB_EVENT_INSTRUCTIONS.md
## Non-negotiable reasoning rules
- Separate FACTS, INFERENCES, ASSUMPTIONS, and UNKNOWNS.
- Do not present assumptions as facts.
- Fail closed when evidence is insufficient or contradictory.
- Distinguish symptom, root cause, contributing factor, and masking layer.
- Check contracts, invariants, and temporal event order.
- Do not confuse code presence, test presence, and runtime proof.
- Keep conclusion scope proportional to evidence scope.
- Rank findings by operational severity, not verbosity.
- Prefer minimal safe corrective action over broad refactors.

## Domain laws
- YAML + Pydantic are the SSOT. No business-logic fallbacks outside config.
- No silent fallbacks, hidden constants, or implicit overrides.
- Contract-first and additive-only changes.
- Any new event/command must be registered in the proper YAML registry.
- Runtime behavior outweighs docs; docs must be updated if code changed.
- A task is DONE only with a REPORT matching docs/ai/AGENT_REPORT_SCHEMA.md.

## Mandatory workflow
1. Gather context first.
2. Build a narrow plan.
3. Check for duplication before editing.
4. Make minimal safe changes.
5. Run relevant validation.
6. Produce a REPORT with explicit evidence, risks, and unproven areas.

## Never
- Never invent runtime evidence.
- Never claim “fixed” without validation.
- Never overgeneralize from one local finding to the whole system.
- Never hide uncertainty behind confident wording.
- Never rewrite broad areas before localizing the failure.
