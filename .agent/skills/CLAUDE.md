# CLAUDE.md

@./AGENTS.md

## Claude-specific adapter

Treat `AGENTS.md` as the canonical operating policy for this repository.
This file exists only to adapt that policy to Claude Code’s memory system.

When working in this repository:
- follow the operating mode that matches the task instead of defaulting to maximum depth
- prefer short plans before broad edits
- respect more local path-specific `CLAUDE.md` files when you enter subtrees, but do not violate the non-negotiable invariants from `AGENTS.md`
- if behavior seems inconsistent with repository policy, inspect loaded memory with `/memory`
- use imports and local files to stay modular; do not duplicate large policy blocks across many `CLAUDE.md` files

## Emphasis for Claude

- Keep reasoning visible through baselines, diffs, and verification summaries.
- Do not let conversational fluency replace evidence.
- For architecture or research tasks, explicitly separate root framing, baseline, and scale-up.
- For local fixes, stay surgical.
