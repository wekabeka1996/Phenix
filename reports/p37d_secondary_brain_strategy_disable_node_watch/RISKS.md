# RISKS.md
# P37D — Risk Register

## Risk Summary

| ID | Risk | Severity | Likelihood | Mitigation |
|----|------|----------|------------|------------|
| R01 | `llm_microstructure` plugin has undiscovered autonomous authority | MEDIUM | UNKNOWN | Inspect plugin before enabling agent_arena_testnet in production |
| R02 | `neocortex` domain emits autonomous trade signals | MEDIUM | UNKNOWN | Inspect `domains/neocortex/` before activation |
| R03 | YAML `strategies_registry.assignments: {}` interpreted as truthy dict (not empty) | LOW | LOW | Confirmed: `registry.py` L220 checks `not assignments` — empty dict is falsy in Python |
| R04 | `md_amr` handler registers FSM listeners even when `enabled = False` | LOW | LOW | Pattern assumption from `alpha_mr_s01`; inspect before shipping |
| R05 | `shadow_mode_enabled: false` in Aurora config disables scoring shadow without disabling decision flow | LOW | LOW | Irrelevant if `aurora.enabled = false` — decision pipeline does not run |
| R06 | `CsvRecorder` stop called before all FSM events flushed | LOW | MEDIUM | Controlled by `ShutdownStage` with `timeout_sec=2.0` in `main.py` L1695 |
| R07 | `no_order_observation_mode` flag not respected by all adapters | MEDIUM | UNKNOWN | Only verified at `execution_readiness.py` read-path; write-path adapter enforcement unconfirmed |
| R08 | Layered config profile for `agent_arena_testnet` does not exist; requires new infrastructure | LOW | MEDIUM | No-code-change path is available: disable all strategies in base config |
| R09 | Open positions may remain unmanaged if exit manager is accidentally disabled | HIGH | LOW | Do NOT disable `domains.decision_making.exit` config |
| R10 | Agent command produces live order if testnet adapter misconfigured | CRITICAL | LOW | `is_live_execution` must be `False`; `no_order_observation_mode` must be `True` when agent is observing |

---

## Critical Safety Invariants

The following invariants must hold at all times in agent_arena_testnet mode:

```
1. runtime.is_live_execution == False
2. runtime.shadow_mode == True  (or no_order_observation_mode == True)
3. strategies.*.enabled == False  (all internal strategies)
4. strategies_registry.assignments == {}  (empty — no plugin handlers started)
5. No exchange credentials accessible from agent command handlers
6. All agent commands tagged: testnet_only = True
```

---

## P37C Status Note

P37C is recorded-only and still `pending_fsm`. This report does NOT claim P37C is live.
Disable map is a static analysis only. Execution proof requires a separate runtime validation task.
