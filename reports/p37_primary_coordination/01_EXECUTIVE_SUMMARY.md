# P37 Executive Summary

Overall verdict: `P37_FINAL_SUMMARY_READY`. The P37A, P37B, and P37C primary reports are all present and internally consistent, and the secondary coordination package is visible through the remote ref proof. The batch is ready for review, but it is not a claim of live exchange execution: P37C is still recorded-only and returns `pending_fsm`, while the secondary combined report is partial because Agent 5 never published.

| Agent | Report | Branch / commit | Status | Evidence |
| --- | --- | --- | --- | --- |
| Agent 1 | `reports/p37a_event_fsm_surface_discovery/REPORT.md` | `p37a-event-fsm-surface-discovery-primary-20260709` / `28cc5c36402464f00ac8b1d73d1ed28267e4cd49` | Ready | Event registry, FSM path, and safe insertion points were localized with static discovery; no runtime wiring was claimed. |
| Agent 2 | `reports/p37b_agent_arena_event_contract/REPORT.md` | `p37b-agent-arena-event-contract-primary-20260709` / `49773094e331f38b540ca284d16600a279ec5885` | Ready | SSOT registry plus fail-closed Pydantic contract validated 8/8 tests and blocked live/mainnet, credentials, and implicit order defaults. |
| Agent 3 | `reports/p37c_cockpit_agent_event_buttons/REPORT.md` | `p37c-cockpit-agent-event-buttons-primary-20260709` / `4f3ab52e2b15d8f5e10288b44a8718bdddab2e08` | Ready, recorded-only | Cockpit event buttons and API ingress were added; accepted actions are attributable and timestamped, but execution remains FSM-pending. |
| Agent 6 | `origin/p37-secondary-combined-report-20260709:reports/p37_secondary_coordination/REPORT.md` | `p37e-fsm-event-audit-invariants-secondary-20260709` / `cd41166fbb149d352aef7b6c10084b85018dea41` | Partial timeout | Agent 6 validated event-audit invariants with 4 passing tests, but Agent 5 disable-map proof is missing. |

What changed:
- Event registry ownership is localized in the SSOT path and guarded by Pydantic validation.
- The FSM execution path is localized to event-bus subscriptions and an explicit safe insertion point.
- Cockpit agent buttons are event-first and record-only, with `pending_fsm` rather than direct exchange execution.
- The secondary audit branch is published remotely, but the combined coordination state is still partial.

What is proven:
- Event registry localized: yes.
- FSM path localized: yes.
- Agent buttons are event-first: yes.
- Actions are timestamped and attributable: yes.
- Proposal and audit payloads reject live/mainnet, secrets, and raw order shapes.
- No mainnet or raw-order activity occurred in the reported work.
- The second PC is partially synced through the remote combined report, but it is not fully equal because Agent 5 is missing.

What is unproven:
- Actual exchange execution wiring through the FSM gateway.
- Full second-PC symmetry, because Agent 5 did not publish the disable-map report.
- Live runtime proof beyond the recorded-only and test-backed paths.

What should not be merged yet:
- Do not claim P37C is live-execution wired; it is still `pending_fsm`.
- Do not claim the secondary machine is fully symmetric or complete.
- Do not promote any branch as mainnet-ready or raw-order-capable.

Exact missing evidence:
- Live FSM handoff proof for P37C beyond the recorded-only API path.
- Agent 5 disable-map report for the secondary coordination package.
