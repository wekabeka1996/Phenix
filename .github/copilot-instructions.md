# Repository custom instructions for GitHub Copilot

Use `.agent/skills/AGENTS.md` as the canonical agent policy for this repository.
This file is intentionally short to avoid conflicts with `AGENTS.md` and any path-specific instructions.

Archived / superseded policy docs live in `docs/_archive/` and must not be used.

## Required behavior

- Choose the lightest operating mode that fits the task.
- For non-trivial work, first identify whether the request targets a symptom or a root problem.
- Establish a minimal legible baseline before proposing larger architecture.
- Keep edits surgical unless the task explicitly requires redesign.
- Do not perform drive-by refactors.
- Prefer visible verification: tests, logs, diffs, metrics, or reproducible checks.
- State assumptions and remaining uncertainty instead of hiding them.
- Prefer simple, readable mainline code and isolate experimental complexity.
- For risky or autonomy-heavy changes, add boundaries, rollback, and explicit verification gates.

## Avoid

- speculative abstractions
- code bloat
- opaque fixes without evidence
- broad rewrites without a proved need
- metric-free optimization
