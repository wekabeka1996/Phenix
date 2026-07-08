# Files changed

## Phenix

- `.gitignore`: allowlist P9 reports.
- `apps/reference/domains/agent_bridge/action_review.py`: contracts, taxonomy, lint, ledger, revisions, compact projection.
- `apps/reference/domains/agent_bridge/contracts.py`: packet memory models and P9 publisher version.
- `apps/reference/domains/agent_bridge/reducer.py`: bounded ActionReview memory projection and budget trimming.
- `apps/reference/main.py`: P9 publisher version.
- `scripts/validate_action_review_ledger.py`: offline validation command.
- `tests/domains/agent_bridge/test_action_review.py`: schema, guards, ledger, revision, outcome, packet, concurrency tests.
- `reports/agent_control_p9_action_review_ledger/`: evidence and samples.

## Adjacent Cockpit workspace

- `src/shared/contracts/agentFeed.ts`: compact ActionReview validation.
- `src/components/agentFeed/AgentFeedPanel.tsx`: read-only Action Review card.
- `tests/trading-agent/AgentFeedBridge.test.ts`: compact memory fixture/parser coverage.

Unrelated worktree changes were not modified.
