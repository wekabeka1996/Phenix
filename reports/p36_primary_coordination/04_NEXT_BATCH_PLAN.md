# Next Batch Plan

## Next Prompts

1. If the operator requires interactive browser evidence, request a Linux-capable browser runner or a manual browser proof for P36B.
2. If static browser proof is sufficient, start the next batch from `agent-hub-integrated-2026-07-09@e95df59f3ccf0ba652b7319c1f8aca9ce70549fc`.

## Merge Validation Prompts

1. Re-run `git status --short --branch`, `git branch --all`, `git worktree list`, and `git log --oneline --decorate -15` before any follow-up batch.
2. Re-check the P36B and P36C report artifacts if any new publication lands.
3. Do not merge to `main` without operator approval.

## Safe Git Commands

- `git fetch --all --prune`
- `git status --short --branch`
- `git branch --all`
- `git worktree list`
- `git log --oneline --decorate -15`
- `git rev-parse HEAD`
- `git show --stat --oneline e95df59f3ccf0ba652b7319c1f8aca9ce70549fc`
- `git show --stat --oneline e2395937`
- `git show --stat --oneline ec424ecc`

## Next Batch Proposal

- The next batch can proceed on the current baseline once the browser-proof caveat is accepted.
- If the browser proof must be symmetric, hold the batch open for a manual browser run and then re-run the coordinator refresh.
