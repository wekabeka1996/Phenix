# Next Batch Plan

## Immediate Operator Gate
1. Review P37B first as the registry/contract anchor.
2. Review P37C second with a manual UI/API gate that verifies event buttons record only `pending_fsm` actions.
3. Review secondary coordination as ready, while preserving its unknowns list.

## Safe Git Commands
- `git status --short --branch`
- `git branch --all`
- `git show --stat p37b-agent-arena-event-contract-primary-20260709`
- `git show --stat p37c-cockpit-agent-event-buttons-primary-20260709`
- `git show --stat origin/p37-secondary-combined-report-20260709`
- `git diff --stat agent-hub-integrated-2026-07-09...p37b-agent-arena-event-contract-primary-20260709`
- `git diff --stat agent-hub-integrated-2026-07-09...p37c-cockpit-agent-event-buttons-primary-20260709`

## Next Implementation Batch
- Implement the missing `agent_arena_testnet` profile only after P37B registry contract and P37C recorded-only event ingress are accepted.
- Add FSM handoff proof from recorded `pending_fsm` commands to the registered FSM gateway.
- Keep brain/strategy autonomous authority disabled while agent arena testnet profile is introduced.
- Add runtime verification for the remaining secondary unknowns: `llm_microstructure`, `neocortex`, `md_amr`, and adapter write-path `no_order`.

## Guardrails
- No destructive git commands.
- No force push.
- No main merge until operator approval.
- No claim of actual exchange execution until runtime proof exists.
