# GEMINI.md

@./AGENTS.md

## Gemini-specific adapter

Treat `AGENTS.md` as the canonical operating policy for this repository.
This file adds only Gemini CLI-specific guidance.

When working in this repository:
- rely on the hierarchical context system, but keep policy centralized in `AGENTS.md`
- if active instructions seem inconsistent or incomplete, inspect them with `/memory show` or `/memory list`, and reload with `/memory refresh` after changes
- prefer the nearest path-specific context only for local specialization; do not override the non-negotiable invariants from `AGENTS.md`
- do not turn every task into a heavy research workflow; choose the lightest valid operating mode

## Emphasis for Gemini

- Root-node thinking is for choosing the right problem, not for overcomplicating trivial tasks.
- Minimal legible baselines come before broader architecture.
- Use bounded experiments and explicit success criteria before escalating scope.
