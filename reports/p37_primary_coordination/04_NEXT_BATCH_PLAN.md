# Next Batch Plan

## Next Prompts
1. If the operator wants full secondary symmetry, ask Agent 5 to publish the missing disable-map report and then rerun the secondary coordination summary.
2. If the operator wants a stronger UI gate for P37C, ask for a manual browser check on a browser-capable runner to confirm the event buttons post only recorded-only, `pending_fsm` actions.
3. If the operator wants to start the next implementation batch, use the published P37 contracts as the baseline and keep the event-first, testnet-only rule set unchanged.

## Safe Git Commands
- `git status --short --branch`
- `git branch --all`
- `git worktree list`
- `git show --stat p37a-event-fsm-surface-discovery-primary-20260709`
- `git show --stat p37b-agent-arena-event-contract-primary-20260709`
- `git show --stat p37c-cockpit-agent-event-buttons-primary-20260709`
- `git show --stat origin/p37-secondary-combined-report-20260709`
- `git diff --stat <base>...<branch>`
- `git diff --name-only <base>...<branch>`

## Merge Guidance
- No merge or push should happen from this coordinator task.
- No destructive git commands.
- No force push.
- No main merge until operator approval.

## Next Batch Proposal
- Start the next batch from the published P37 contracts, with P37B as the registry/contract anchor and P37C as the event-button entry surface.
- If browser parity matters, add a browser-capable verification task before any claim of full UI proof.
- Keep every command testnet-only, timestamped, attributable, and fail-closed on forbidden live/mainnet or raw-order fields.
