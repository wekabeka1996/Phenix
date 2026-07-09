# Next Batch Plan

## Repair Prompts

1. To the P35B smoke agent: publish `reports/p35b_final_integrated_cockpit_smoke/REPORT.md`, `VALIDATION.md`, `PATCH_DIFF.md`, and `RISKS.md` in the assigned worktree. Include exact smoke commands, browser/runtime proof, and the AGENT_IDENTITY block.
2. To the secondary coordination agent: publish `reports/p35_secondary_coordination/REPORT.md` plus any supporting docs that prove branch visibility, timing/cadence status, and whether the secondary side is synchronized with `agent-hub-integrated-2026-07-09`.

## Merge Validation Prompts

1. After the missing reports land, rerun `git status --short --branch`, `git branch --all`, `git worktree list`, and `git log --oneline --decorate -15`.
2. Re-run `git diff --stat` and `git diff --name-only` for the final candidate branches before any merge decision.
3. Do not accept any batch-close claim until P35B and the secondary report are both present.

## Safe Git Commands

- `git status --short --branch`
- `git branch --all`
- `git worktree list`
- `git log --oneline --decorate -15`
- `git fetch --all --prune`
- `git show --stat p35c-cli-proposal-ledger-primary-20260709`
- `git diff --stat agent-hub-sync-2026-07-08...agent-hub-integrated-2026-07-09`
- `git diff --stat agent-hub-sync-2026-07-08...p35c-cli-proposal-ledger-primary-20260709`

## Merge Guardrails

- No destructive git commands.
- No force push.
- No merge to `main` without operator approval.
- No batch-close claim until the missing P35B and secondary evidence exists.

## Next Batch Proposal

- If the missing reports arrive cleanly, keep `agent-hub-integrated-2026-07-09` as the next baseline and run one final regression sweep across cockpit smoke, proposal ledger, and timer/cadence surfaces before any broader release decision.
