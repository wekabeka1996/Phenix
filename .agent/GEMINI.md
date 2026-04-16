# Gemini Project Protocol

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

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
