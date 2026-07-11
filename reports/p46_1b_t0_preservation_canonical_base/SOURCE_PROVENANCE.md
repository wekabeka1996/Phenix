# P46_1B_T0 SOURCE PROVENANCE

```yaml
recorded_at: 2026-07-11T13:14:00+03:00
```

---

## FACTS

### Integration Branch Base

| Field | Value |
|---|---|
| Base SHA | `5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d` |
| Base commit message | P42H: correct runtime_code_sha to c55489003 in RUN_READY_GATE and attestation reports |
| Base author | wekabeka1996 (primary machine) |
| Base date | 2026-07-10 14:42:19 +0300 |
| Base origin | Produced in P42H attestation repair task on primary machine |
| On remote | `origin/p42-dual-agent-runtime-integrated-primary-20260711` (as ancestor of `5bc64f9b`) |

### Source Candidates (Provenance of Required Refs)

| SHA | Commit Message | Author Machine | Branch of Origin | Integration Role |
|---|---|---|---|---|
| `d18cc36e` | P43B add API CLI adapter evidence reports | Primary | `p43b-api-cli-agent-runtime-adapters-primary-20260710` | Cherry-pick source (T1) |
| `998c813f` | P43B add API and restricted CLI runtime adapters | Primary | `p43b-api-cli-agent-runtime-adapters-primary-20260710` | Cherry-pick source (T1 — actual code) |
| `74fb1079` | P41X add collective memory coordination kernel | Primary | `p41x-collective-memory-coordination-ultra-20260710` | Cherry-pick source (T2) |
| `f5cac010` | P41Y harden memory crash recovery and recall | Primary | `p41y-memory-fault-injection-semantic-recall-ultra-20260710` | Cherry-pick source (T3, depends on T2) |
| `67ead971` | P43A: add final coordination reports | Primary | `p43-collective-memory-dual-runtime-integrated-primary-20260710` | Reports-only (T4) |
| `7c43600f` | P46 handoff secondary preservation audit artifacts | Secondary | `p46-handoff-secondary-audit-20260711` | Evidence only (read by T0) |
| `9a167896` | P42M: Complete CLI trading agent analytical session | Secondary | `p46-preserve/secondary-p45a-20260711` | Reports/evidence only |
| `096f1fd8` | P42O: Forensic comparison | Secondary | `p46-preserve/secondary-p42o-20260711` | Evidence only |

### Cockpit Provenance

| Field | Value |
|---|---|
| Cockpit baseline SHA | `15e63ce57a5be75b6f08a594259ba517428cff1f` |
| Repository | `deepseek-agent-os` (separate repo) |
| Branch | `workspace-changes` |
| Author machine | Secondary |
| Confirmed by | Agent 3 secondary preservation report |
| Integration role | Cockpit baseline for selective Agent Feed port (Cockpit tasks) |
| 14-file Agent Feed package | Defined in `P46_COCKPIT_SELECTIVE_PORT_MANIFEST.md` |

---

## INFERENCES

- `d18cc36e` and `998c813f` are both authored on the primary machine, on the same branch. `998c813f` is the actual source-code commit; `d18cc36e` adds reports on top. Cherry-pick target for T1 is `998c813f` with optional `d18cc36e` for reports.
- `74fb1079` is reachable from `origin/p42f-...` making it remote-durable without a dedicated single-SHA ref. However `p46-preserve/primary-p41x-local-20260711` also makes it reachable via its ancestor `d2d22e0f`.
- All secondary-produced source commits are either rejected (P42N) or reports-only/evidence-only.

---

## ASSUMPTIONS

- The `deepseek-agent-os` Cockpit repo at `15e63ce5` has not been force-pushed or modified on the secondary machine since Agent 3 filed the preservation report.

---

## UNKNOWNS

- Exact file hashes of the 14 Agent Feed files have not been verified against the secondary Cockpit manifest in this task (Cockpit tasks will verify).
