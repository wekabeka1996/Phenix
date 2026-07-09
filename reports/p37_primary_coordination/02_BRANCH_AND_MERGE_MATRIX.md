# Branch And Merge Matrix

| Branch | Commit | Files changed | Tests run | Validation status | Merge recommendation | Merge order | Conflict risk | Likely conflicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `p37a-event-fsm-surface-discovery-primary-20260709` | `28cc5c36402464f00ac8b1d73d1ed28267e4cd49` | `reports/p37a_event_fsm_surface_discovery/*` | Static discovery commands for `event_bus`, `EVT:`, and `verb_registry` | PASS_STATIC_DISCOVERY | ACCEPT | 1 | Low | Report docs only |
| `p37b-agent-arena-event-contract-primary-20260709` | `49773094e331f38b540ca284d16600a279ec5885` | `apps/reference/dictionaries/verb_registry_v1.yaml`; `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_arena_contract.py`; `tools/deepseek-terminal-agent/tests/test_agent_arena_contract.py`; `reports/p37b_agent_arena_event_contract/*` | `pytest tools/deepseek-terminal-agent/tests/test_agent_arena_contract.py -v -s` -> 8 passed | PASS | ACCEPT | 2 | Medium | `apps/reference/dictionaries/verb_registry_v1.yaml`; arena contract schema/tests |
| `p37c-cockpit-agent-event-buttons-primary-20260709` | `4f3ab52e2b15d8f5e10288b44a8718bdddab2e08` | `tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/app.py`; `sessions/agent_event_registry.yaml`; `sessions/agent_events.py`; `tests/test_agent_event_api.py`; `tests/test_agent_events.py`; `reports/p37c_cockpit_agent_event_buttons/*` | `python -m pytest tests/test_agent_events.py tests/test_agent_event_api.py` -> 12 passed; `python -m pytest tests/test_agent_proposal_api.py tests/test_dashboard_chat_app.py` -> 13 passed | PASS_RECORDED_ONLY | ACCEPT_AFTER_MANUAL_UI_CHECK | 3 | High | `dashboard/app.py`; local event registry; event API tests |
| `origin/p37-secondary-combined-report-20260709` | `a8e1237acfa68294d8102d982b20fb1d6d0032f3` | `reports/p37_secondary_coordination/*`; Agent 5 disable-map review; Agent 6 event-audit readiness docs | Agent 6: `python -m pytest tools/deepseek-terminal-agent/tests/test_agent_action_audit.py` -> 4 passed; Agent 5: static discovery only | PASS_SECONDARY_READY | ACCEPT | 4 | Medium | Secondary coordination docs; future disable-map/profile work |

Merge guidance:
- P37B is the merge anchor because it owns the SSOT registry contract for arena commands/events.
- P37C should follow P37B only after a manual UI/API merge gate confirms recorded-only `pending_fsm` behavior.
- Secondary is ready now, but it still documents unknown authority surfaces and confirms `agent_arena_testnet` is not implemented.
- Current baseline before any approved merge: `agent-hub-integrated-2026-07-09@bc25105175bd6e41d677f8d74f72979cd7155b1e`.
