# P46_1B_T0 CANONICAL BASE PROOF

```yaml
recorded_at: 2026-07-11T13:14:00+03:00
```

---

## SELECTED BASE

```
5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d
P42H: correct runtime_code_sha to c55489003 in RUN_READY_GATE and attestation reports
Author: wekabeka1996 <wekabeka1996@gmail.com>
Date:   Fri Jul 10 14:42:19 2026 +0300
```

---

## PROOF 1 — SHA RESOLVES LOCALLY

```
git rev-parse 5bc64f9b
=> 5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d  ✅
```

---

## PROOF 2 — SHA IS ON REMOTE

```
git ls-remote origin p46-1b-canonical-integration-primary-20260711
=> 5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d  refs/heads/p46-1b-canonical-integration-primary-20260711  ✅
```

---

## PROOF 3 — INTEGRATION BRANCH HEAD EQUALS BASE (before report commit)

```
git -C Phenix-p46-1b-canonical rev-parse HEAD
=> 5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d  ✅

git -C Phenix-p46-1b-canonical status --short --branch
=> ## p46-1b-canonical-integration-primary-20260711
   (no modified or staged files)  ✅
```

---

## PROOF 4 — ANCESTRY CHECKS

```
git merge-base --is-ancestor 5bc64f9b d18cc36e
=> exit 0  (5bc64f9b IS ancestor of P43B source candidate)  ✅

git merge-base --is-ancestor 5bc64f9b 7c43600f
=> exit 0  (5bc64f9b IS ancestor of secondary handoff)  ✅

git merge-base --is-ancestor 5bc64f9b 9a167896
=> exit 0  (5bc64f9b IS ancestor of P45A secondary preserve)  ✅

git merge-base --is-ancestor 74fb1079 f5cac010
=> exit 0  (P41X kernel IS ancestor of P41Y crash recovery)  ✅

git merge-base --is-ancestor 74fb1079 origin/p42f-...
=> exit 0  (P41X kernel reachable from remote)  ✅
```

---

## PROOF 5 — BASE CONTENT AUDIT

The base `5bc64f9b` is:

- Clean P42H reports-only correction on top of `91c866ab` (P42H attestation code)
- Contains no P41X/P41Y collective-memory source
- Contains no P42N gate bypasses, env-var authority, hardcoded sizing, or monkeypatching
- The attestation preflight source (`dual_agent_runner.py`) is present as a result of `91c866ab` which is below `5bc64f9b`
- All non-negotiable law checks pass at the base level

---

## PROOF 6 — INTEGRATION BRANCH LINEAGE

```
5bc64f9b  P42H: correct runtime_code_sha [BASE]
   └─ 91c866ab  P42H: attestation repair
      └─ c5548900  P42 Release
         └─ 1f84c49c  P42C finalize
            └─ ... (P42C chain → P42B → P42A → P40R baseline)
```

The selected base is on the existing remote release branch `origin/p42-dual-agent-runtime-integrated-primary-20260711` — it has already been through P42H attestation verification.

---

## REPORT COMMIT

This task adds a report commit on top of `5bc64f9b`. The report commit SHA will differ from the base. The base SHA (`5bc64f9b`) remains the **source baseline** for all subsequent feature-porting tasks. All P46-1B sub-agents must branch from:

```
origin/p46-1b-canonical-integration-primary-20260711
```

at their task start, not from the report commit SHA.

> [!IMPORTANT]
> The integration branch HEAD after this task equals the report commit, not `5bc64f9b`. The source baseline for feature porting is always `5bc64f9b`. P46-1B sub-agents should branch from the integration branch HEAD (which includes these reports) as their starting point.
