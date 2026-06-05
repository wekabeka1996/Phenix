# CONFIG_MODELS_ROADMAP_ADDENDUM

**Initiative**: governance addendum for the [apps/reference/config_models.py](apps/reference/config_models.py) decomposition roadmap
**Companion artifacts**: [CONFIG_MODELS_GOVERNANCE_RECOVERY.md](CONFIG_MODELS_GOVERNANCE_RECOVERY.md), [CONFIG_MODELS_ROADMAP.md](CONFIG_MODELS_ROADMAP.md), [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md)
**Date**: 2026-04-18

---

## 1. Purpose

This addendum does **not** rewrite the technical roadmap. It inserts the missing governance re-entry gate required after Phase 0 was executed out of the originally intended order.

## 2. Addendum decision

- The main roadmap remains structurally valid.
- Frozen boundaries F1–F5 remain unchanged.
- Phase numbering remains unchanged.
- A new governance re-entry gate, **GR-0**, is inserted between the already-landed Phase 0 artifact set and any Phase 1 planning or implementation.

## 3. GR-0 — Governance re-entry gate before Phase 1

Before `[Phase 1]` may be opened, **all** of the following must be true:

1. [CONFIG_MODELS_GOVERNANCE_RECOVERY.md](CONFIG_MODELS_GOVERNANCE_RECOVERY.md) exists and is accepted as the truthful recovery artifact.
2. [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md) contains an explicit process-deviation / governance-recovery checkpoint.
3. A focused Phase 0 evidence re-review has classified the current failure at [tests/config/test_btcusdt_aurora_runtime_fields.py](tests/config/test_btcusdt_aurora_runtime_fields.py#L384) as one of:
   - unrelated post-Phase-0 branch drift, or
   - evidence against the old Phase 0 validation claim requiring a corrective journal note.
4. Only after step 3 may `[Phase 1]` be opened with `Status: planned` and reviewed in the normal linear workflow.

## 4. Non-effects

This addendum does **not**:

- reopen or erase the existing `[Phase 0]` journal entry
- authorize any new implementation work by itself
- change Phase 1 scope
- change the decomposition target structure

## 5. Addendum verdict

> The decomposition initiative resumes from the real Phase 0 artifact baseline, but not from a procedurally clean gate history. GR-0 is mandatory: governance recovery first, Phase 0 evidence re-review second, Phase 1 planning only after both are recorded.
