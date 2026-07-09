# P37 Executive Summary

Overall verdict: `P37_FINAL_SUMMARY_READY_SECONDARY_READY`. P37A, P37B, P37C, and the refreshed secondary coordination report are all present. Secondary coordination is no longer partial: Agent 5 disable-map evidence landed and Agent 6 event-audit invariants remain validated. The batch is ready for operator/reviewer handoff, with one important boundary intact: P37C is still recorded-only / `pending_fsm`, and actual exchange execution through the FSM remains unproven.

| Agent | Report | Branch / commit | Status | Evidence |
| --- | --- | --- | --- | --- |
| Agent 1 | `reports/p37a_event_fsm_surface_discovery/REPORT.md` | `p37a-event-fsm-surface-discovery-primary-20260709` / `28cc5c36402464f00ac8b1d73d1ed28267e4cd49` | Ready | Event registry, FSM path, and safe insertion points were localized through static discovery. |
| Agent 2 | `reports/p37b_agent_arena_event_contract/REPORT.md` | `p37b-agent-arena-event-contract-primary-20260709` / `49773094e331f38b540ca284d16600a279ec5885` | Ready, merge anchor | SSOT registry contract plus fail-closed Pydantic validation registered 8 arena commands/events and passed 8 tests. |
| Agent 3 | `reports/p37c_cockpit_agent_event_buttons/REPORT.md` | `p37c-cockpit-agent-event-buttons-primary-20260709` / `4f3ab52e2b15d8f5e10288b44a8718bdddab2e08` | Ready, manual gate | Cockpit event endpoints record attributable events and return `pending_fsm`; no exchange call path is wired. |
| Agent 6 | `origin/p37-secondary-combined-report-20260709:reports/p37_secondary_coordination/REPORT.md` | `p37-secondary-combined-report-20260709` / `a8e1237acfa68294d8102d982b20fb1d6d0032f3` | Ready | Secondary is no longer partial; Agent 5 mapped brain/strategy disable surfaces and Agent 6 validated event-audit invariants. |

What changed:
- Secondary coordination moved from partial to `P37_SECONDARY_COORDINATION_READY`.
- Agent 5 disable-map evidence is now integrated into the secondary report.
- P37B remains the registry/contract merge anchor.
- P37C remains the Cockpit API/button surface, but requires a manual UI/API merge gate.

What is proven:
- Event registry localized: yes.
- FSM path localized: yes.
- Agent buttons are event-first: yes.
- Actions are timestamped and attributable: yes.
- Secondary is no longer partial: yes.
- No mainnet, live, raw exchange order, or raw exchange call activity was reported.

What is unproven:
- Actual exchange execution through the FSM gateway.
- Runtime proof for an `agent_arena_testnet` profile; the profile is not implemented yet.
- Full coverage of secondary unknowns: `llm_microstructure`, `neocortex`, `md_amr`, and all adapter write-path `no_order` enforcement.

What should not be merged or claimed yet:
- Do not claim P37C executes exchange actions; it records `pending_fsm` events only.
- Do not claim `agent_arena_testnet` exists.
- Do not bypass the P37C manual UI/API merge gate.
