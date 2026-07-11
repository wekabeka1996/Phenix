# P46_1B_T0 RISKS

```yaml
recorded_at: 2026-07-11T13:14:00+03:00
```

---

## FACTS (Known Risks)

### R1 — P41X cherry-pick dashboard conflict
- **Type:** DEFERRED_WITH_REASON
- **Risk level:** MEDIUM
- **Description:** `74fb1079` (P41X kernel) modifies `tools/.../dashboard/app.py`. P43B (`998c813f`) adds `trading_agent_runtime.py`. If both are ported in sequence, `dashboard/app.py` may conflict depending on P43B's imports. Must be inspected at cherry-pick time (T2).
- **Mitigation:** P46-1B T2 agent must inspect `app.py` changes in both commits before cherry-pick; resolve manually if needed.

### R2 — P41Y collective_memory.py patch dependency
- **Type:** DEFERRED_WITH_REASON
- **Risk level:** MEDIUM
- **Description:** `f5cac010` (P41Y) patches `collective_memory.py` and `collective_memory_models.py` which are introduced by `74fb1079` (P41X). Cherry-picking P41Y before P41X will fail.
- **Mitigation:** Strict ordering enforced in manifest: T2 (P41X) must precede T3 (P41Y). T3 agent verifies ancestry before cherry-pick.

### R3 — P43B config.py vs apps/reference/config_models.py overlap
- **Type:** DEFERRED_WITH_REASON
- **Risk level:** MEDIUM
- **Description:** P43B adds `p42_config.py` (separate file). P42N (rejected) added to `apps/reference/config_models.py`. These are distinct files with no direct conflict. However, if any future port of config models is attempted, the rejected `api_agent_order_submit_enabled` field must not be included.
- **Mitigation:** `REJECTED_REF_INVENTORY.md` explicitly documents P42N violations. T1 agent verifies no P42N fields are present in any ported config.

### R4 — Cockpit `15e63ce5` local divergence
- **Type:** DEFERRED_WITH_REASON
- **Risk level:** LOW-MEDIUM
- **Description:** Agent 3 confirmed secondary Cockpit is at `15e63ce5` with a clean clone. However the primary Cockpit non-Git snapshot has 22 primary-only files and 101 same-path mismatches. The selective 14-file Agent Feed port is bounded but must be typecheck-verified.
- **Mitigation:** Cockpit T-tasks must run `tsc --noEmit` before and after each Agent Feed file group.

### R5 — `74fb1079` not on a dedicated named remote ref
- **Type:** MITIGATED
- **Risk level:** LOW
- **Description:** `74fb1079` is reachable from `origin/p42f-dual-agent-mvp-final-coordination-primary-20260710` and transitively from `p46-preserve/primary-p41x-local-20260711`. It has no dedicated single-SHA remote ref.
- **Mitigation:** Both parent refs are durable. T2 agent verifies `git rev-parse 74fb1079` resolves before cherry-pick. If remote durability is needed independently, T2 can create a dedicated tag.

### R6 — Report commit SHA differs from source baseline
- **Type:** MITIGATED
- **Risk level:** LOW
- **Description:** After this task commits reports, the integration branch HEAD will differ from `5bc64f9b`. P46-1B sub-agents must use the base SHA `5bc64f9b` for ancestry checks, not the post-report HEAD.
- **Mitigation:** `CANONICAL_BASE_PROOF.md` explicitly documents this distinction. All T-task agents must read T0 reports before branching.

---

## INFERENCES

- No unmitigated risks were found for the T0 task itself (preservation-only; no source modified).
- All medium-risk items are deferred to the appropriate feature-porting sub-tasks.

---

## ASSUMPTIONS

- Origin remote remains non-force-pushed and stable between sub-task handoffs.

---

## UNKNOWNS

- Whether a P46-1B task interleaving creates branch head races if multiple agents push to the same integration branch concurrently. Recommendation: T1–T4 agents should work on separate worktree branches and merge sequentially.
