# P46_1B_T0 REMOTE REF INVENTORY

```yaml
recorded_at: 2026-07-11T13:13:51+03:00
verified_via: git ls-remote origin
```

---

## INTEGRATION BRANCH

| Remote Ref | SHA | Status |
|---|---|---|
| `refs/heads/p46-1b-canonical-integration-primary-20260711` | `5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d` | ✅ VERIFIED |

---

## PRIMARY MACHINE PRESERVATION REFS (pushed this task)

| Remote Ref | SHA | Points To | Pushed This Task |
|---|---|---|---|
| `refs/heads/p46-preserve/primary-p43b-20260711` | `d18cc36e9777a51ef6271c3531c2cfdd3af1546e` | P43B branch tip (reports on top of `998c813f`) | ✅ |
| `refs/heads/p46-preserve/primary-p41x-local-20260711` | `d2d22e0fdaa15cf220b400714dd873d9455d585e` | P41X local worktree tip (reports on top of `74fb1079`) | ✅ |
| `refs/heads/p46-preserve/primary-p41y-local-20260711` | `f5cac0107c16fe43c2ec28fbafa8117f1e665096` | P41Y local worktree tip (crash recovery on top of P41X) | ✅ |
| `refs/heads/p46-preserve/primary-p43a-local-20260711` | `60053454c3351a02f82557c018f858e65fe802fc` | P43A local worktree tip | ✅ |

---

## SECONDARY MACHINE PRESERVATION REFS (pre-existing from secondary push)

| Remote Ref | SHA | Points To |
|---|---|---|
| `refs/heads/p46-handoff-secondary-audit-20260711` | `7c43600fadc11b94885768864e588bd544d6eeb6` | Secondary P46-1A audit artifacts |
| `refs/heads/p46-preserve/secondary-p42n-20260711` | `299beb6d573fcef9e79529503194d3e110dbac74` | P42N full tip (REJECTED as integration source) |
| `refs/heads/p46-preserve/secondary-p42o-20260711` | `096f1fd8b241436d9fc65b500e590b441bc13b31` | P42O forensic comparison report |
| `refs/heads/p46-preserve/secondary-p45a-20260711` | `9a167896cfa808eecdcceb011b20370b737388c1` | P42M/P45A CLI session runtime logs |

---

## ADDITIONAL REMOTE REFS CONTAINING REQUIRED SHAS

| Required SHA | Found In Remote Ref |
|---|---|
| `74fb107971443bc19720900a9ba07649d6d7f5e0` (P41X kernel) | `origin/p42f-dual-agent-mvp-final-coordination-primary-20260710` (as ancestor); `p46-preserve/primary-p41x-local-20260711` (as ancestor of `d2d22e0f`) |
| `f5cac0107c16fe43c2ec28fbafa8117f1e665096` (P41Y) | `p46-preserve/primary-p41y-local-20260711` (as tip) |
| `d18cc36e` (P43B source) | `p46-preserve/primary-p43b-20260711` (as tip); `origin/p42f...` (as ancestor) |

---

## COCKPIT BASELINE

| Item | Value | Location |
|---|---|---|
| Cockpit baseline SHA | `15e63ce57a5be75b6f08a594259ba517428cff1f` | `deepseek-agent-os` repo, branch `workspace-changes` |
| Verified by | Agent 3 secondary preservation report | Secondary machine confirmed clean clone at this SHA |
| Not present in Phenix repo | Expected — separate repository | — |

---

## ALL ls-remote OUTPUT (raw)

```
7e0b04da1bcec573ccb8fcdaa9d8ef2d7a8dc2aa  refs/heads/p42f-dual-agent-mvp-final-coordination-primary-20260710
5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d  refs/heads/p46-1b-canonical-integration-primary-20260711
7c43600fadc11b94885768864e588bd544d6eeb6  refs/heads/p46-handoff-secondary-audit-20260711
d2d22e0fdaa15cf220b400714dd873d9455d585e  refs/heads/p46-preserve/primary-p41x-local-20260711
f5cac0107c16fe43c2ec28fbafa8117f1e665096  refs/heads/p46-preserve/primary-p41y-local-20260711
60053454c3351a02f82557c018f858e65fe802fc  refs/heads/p46-preserve/primary-p43a-local-20260711
d18cc36e9777a51ef6271c3531c2cfdd3af1546e  refs/heads/p46-preserve/primary-p43b-20260711
299beb6d573fcef9e79529503194d3e110dbac74  refs/heads/p46-preserve/secondary-p42n-20260711
096f1fd8b241436d9fc65b500e590b441bc13b31  refs/heads/p46-preserve/secondary-p42o-20260711
9a167896cfa808eecdcceb011b20370b737388c1  refs/heads/p46-preserve/secondary-p45a-20260711
```
