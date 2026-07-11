# P46_1B_T0 REJECTED REF INVENTORY

```yaml
recorded_at: 2026-07-11T13:14:00+03:00
```

---

## DECISION

The following commits and their source lines are **rejected as canonical integration sources** per the P46-1A final verdict `P46_BASELINE_SELECTED_WITH_MANUAL_CONFLICT_PACKAGE` and the common context non-negotiable laws.

They are **preserved historically** on their respective remote refs but must not be cherry-picked, merged, or reimplemented in P46-1B integration branches.

---

## REJECTED: P42N SOURCE LINE

| Commit | SHA | Rejection Reason |
|---|---|---|
| P42N gate addition (config_models.py) | `6a2ff2c9` | Adds `api_agent_order_submit_enabled` env/gate bypass to `AgentArenaConfig` — environment-variable authority gate |
| P42N env-var gate | `e8d21fb4` | Adds `API_AGENT_ORDER_SUBMIT_ENABLED` env-var override — env-var authority gate |
| P42N runner script | `bf876bc7` | `run_p42n_session.py` — direct adapter internals, secret/env access |
| P42N final reports | `299beb6d` | Session reports + helper script with monkeypatching and hardcoded leverage mutation |

**Remote preservation ref:** `refs/heads/p46-preserve/secondary-p42n-20260711` → `299beb6d`

**Status:** Historically preserved. NOT an integration source.

### Specific Violations Found in P42N

| Non-negotiable Law Violated | Location |
|---|---|
| No environment-variable authority gates | `API_AGENT_ORDER_SUBMIT_ENABLED` env var in `agent_order_lifecycle_harness.py` |
| YAML + Pydantic are SSOT | Gate bypasses hardcoded outside YAML SSOT |
| No hardcoded sizing, notional, leverage, or execution authority | Hardcoded leverage mutation in session runner |
| No monkeypatching to simulate runtime behavior | Monkeypatching in P42N runner for adapter simulation |
| No direct raw exchange calls from agent-facing code | Direct adapter internals in `run_p42n_session.py` |
| Registered FSM/event ingress is the only execution authority path | Submit gate allows order submission outside FSM registered path |

---

## REJECTED: `c5548900` AS CANONICAL BASE

| Commit | SHA | Rejection Reason |
|---|---|---|
| P42 Release | `c5548900` | Ancestor of selected base `5bc64f9b` — superseded by P42H attestation repair chain |

**Reason:** `5bc64f9b` is the correct tip of the P42 release branch including attestation repairs. `c5548900` is an ancestor and would omit the `dual_agent_runner.py` preflight attestation code.

---

## PRESERVED BUT NOT PROMOTED

The following commits are preserved but their source is not directly cherry-picked; selective manual reimplementation is required per P46-1A ordered manifest:

| Commit | SHA | Status | Reason |
|---|---|---|---|
| `299beb6d` | P42N full tip | Preserved, not promoted | P42N violations (see above) |
| `60053454` | P43A local worktree | Preserved, not promoted | Reports-only; superseded by `5bc64f9b` |
| `d2d22e0f` | P41X local tip | Preserved, not promoted | Reports-only; P41X source is at `74fb1079` |
| `67ead971` | P43A remote tip | Preserved, not promoted | Reports-only on p43-... branch |
