# Validation And Risk Register

## Validations Reported
- P37A: static discovery localized event registry, FSM subscriptions, hybrid testnet path, and brain/strategy authority surfaces.
- P37B: `pytest tools/deepseek-terminal-agent/tests/test_agent_arena_contract.py -v -s` -> 8 passed.
- P37C: `python -m pytest tests/test_agent_events.py tests/test_agent_event_api.py` -> 12 passed.
- P37C: `python -m pytest tests/test_agent_proposal_api.py tests/test_dashboard_chat_app.py` -> 13 passed.
- Secondary P37E: `python -m pytest tools/deepseek-terminal-agent/tests/test_agent_action_audit.py` -> 4 passed.
- Secondary P37D: static discovery mapped brain/strategy disable surfaces; no code/config/runtime execution was performed.

## Updated Evidence
- Secondary coordination verdict is now `P37_SECONDARY_COORDINATION_READY`.
- Agent 5 status is now `P37D_BRAIN_STRATEGY_DISABLE_SURFACES_MAPPED`.
- Agent 6 status remains `P37E_FSM_EVENT_AUDIT_INVARIANTS_VALIDATED`.
- The secondary report states `agent_arena_testnet` is not implemented yet.

## Root Cause Claims And Evidence Level
- Event registry localized: high confidence from P37A and P37B.
- FSM path localized: high confidence from P37A.
- Agent buttons event-first: high confidence from P37C API/event tests.
- All accepted actions timestamped and attributable: high confidence from P37C and P37E.
- Actual exchange execution through FSM: unproven; P37C records events as `pending_fsm`.
- Brain/strategy authority disabled: mapped by Agent 5 through static discovery, not runtime-proven.

## Risks
| Severity | Risk | Evidence |
| --- | --- | --- |
| P0 | None observed | No mainnet/live execution, no raw exchange calls, and no raw order submission were reported. |
| P1 | P37C could be mistaken for execution wiring | Its verdict is `P37C_RECORDED_ONLY_FSM_PENDING`; it records events only. |
| P1 | `agent_arena_testnet` profile absent | Secondary report explicitly says the profile is not implemented yet. |
| P1 | Runtime disable proof remains incomplete | Agent 5 used static discovery; no runtime proof of all strategy/brain disable paths. |
| P1 | Manual UI/API gate needed for P37C | P37C touches `dashboard/app.py` and new event endpoints. |
| P2 | Remaining secondary unknowns | `llm_microstructure`, `neocortex`, `md_amr`, and adapter write-path `no_order` enforcement are not fully proven. |

## Lane Checks
- Coordinator refresh: no code changes, no merge, no push.
- YAML/config: coordinator did not edit YAML; P37B/P37C YAML changes are worker-owned contract surfaces.
- Runtime/trading: no Aurora runtime started; no mainnet/live; no raw exchange calls.
- Direct order authority risk: controlled at this stage by P37B/P37C validators and the recorded-only `pending_fsm` boundary.
