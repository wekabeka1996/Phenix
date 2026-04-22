# CONFIG_MODELS_GOVERNANCE_RECOVERY

**Initiative**: governance recovery for the [apps/reference/config_models.py](apps/reference/config_models.py) decomposition workstream
**Authoritative inputs**: [CONFIG_MODELS_ARCHITECTURE_AUDIT.md](CONFIG_MODELS_ARCHITECTURE_AUDIT.md), [CONFIG_MODELS_ROADMAP.md](CONFIG_MODELS_ROADMAP.md), [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md)
**Mode**: governance/documentation only. No runtime or config-logic edits performed by this artifact.
**Date**: 2026-04-18

---

## 1. Problem framing

The issue is not whether Phase 0 work happened. The issue is whether project history still reflects the **agreed governance sequence** truthfully.

The agreed sequence was:

1. audit
2. roadmap
3. journal initialization
4. formal Phase 0 planning / review gate
5. only then implementation

Current repo state contains real Phase 0 technical artifacts, but [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md) records `[Phase 0]` directly as `validated` without the planned/review gate that the journal rules themselves require. Governance recovery therefore must restore truthful chronology **without falsifying the fact that real work landed**.

## 2. FACTS

- [CONFIG_MODELS_ARCHITECTURE_AUDIT.md](CONFIG_MODELS_ARCHITECTURE_AUDIT.md) is an audit-only artifact and explicitly says no implementation was started there.
- [CONFIG_MODELS_ROADMAP.md](CONFIG_MODELS_ROADMAP.md) defines a validation-gated sequence and says implementation begins only after Phase 0 closes and is journaled.
- [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md#L34) requires linear status progression: `planned -> in_progress -> validated|blocked`.
- [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md#L76) says the Phase 0 slot is reserved for later status progression.
- [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md#L125) explicitly says: do not begin Phase 0 implementation until the planning entry exists and is reviewed.
- [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md#L127) nevertheless contains a direct `[Phase 0]` entry with `Status: validated` and completed technical work.
- Current repo state contains real Phase 0 artifacts on disk:
  - [apps/reference/config_models.py](apps/reference/config_models.py#L1069) contains the Phase 0 shadow-removal provenance banner.
  - [apps/reference/config_models.py](apps/reference/config_models.py#L1500) contains the docs-only provenance comment on `RegimeModelConfig`.
  - [apps/reference/config_models.py](apps/reference/config_models.py#L3113) contains the restored `MemoryShieldConfig._validate_thresholds` validator.
  - [tools/dev/snapshot_config_models_public_surface.py](tools/dev/snapshot_config_models_public_surface.py) exists.
  - [tests/config/_artifacts/config_models_public_surface.json](tests/config/_artifacts/config_models_public_surface.json) exists.
  - [tests/config/test_config_models_public_surface.py](tests/config/test_config_models_public_surface.py) exists.
  - [tests/config/test_config_models_cross_validators_inventory.py](tests/config/test_config_models_cross_validators_inventory.py) exists.
- Current narrow Phase 0 evidence bundle is reproducible on HEAD:
  - `pytest tests/config/test_config_models_public_surface.py tests/config/test_config_models_cross_validators_inventory.py -q` -> `8 passed in 0.51s`
  - manifest SHA on disk matches the journal claim exactly: `fcf40b1913cbaf78d88e3514f73518536c70aa95fc9a46ed346ec05ba1a0153a`
- Current full config slice is **not** fully reproducible on HEAD:
  - `pytest tests/config/ -q` currently fails at [tests/config/test_btcusdt_aurora_runtime_fields.py](tests/config/test_btcusdt_aurora_runtime_fields.py#L384)
  - current result: `1 failed, 328 passed, 3 skipped, 1 deselected`
- Current branch is not pristine for this initiative alone. The diff against `main` includes unrelated or concurrent work outside the decomposition package, including [apps/reference/config_models.py](apps/reference/config_models.py#L2259) (`RegimeLossEmbargoConfig`) and multiple decision-making / execution-position changes.

## 3. INFERENCES

- A real process deviation occurred: the planning/review gate was bypassed or, at minimum, not recorded in the journal before implementation and validation were recorded.
- The existing `[Phase 0]` entry is **not fabricated**. It corresponds to observable code/test/artifact changes that still exist.
- The distortion is primarily at the governance layer: the journal currently implies a sanctioned linear sequence that did not actually occur.
- The current full-suite mismatch means the `[Phase 0]` entry is not fully sufficient as a **current-state** truth statement, even if it was authored in good faith at the time.
- The failing full-suite test looks more consistent with branch drift outside the narrow duplicate-class cleanup than with the Phase 0 artifact set itself, but that causality is not yet proven.

## 4. ASSUMPTIONS

- The `[Phase 0]` entry was written in good faith after actual work landed.
- No hidden off-repo approval artifact exists that would satisfy the missing planning/review gate.
- The current failure in [tests/config/test_btcusdt_aurora_runtime_fields.py](tests/config/test_btcusdt_aurora_runtime_fields.py#L384) may be unrelated to the decomposition package, but that has not yet been formally classified.

## 5. UNKNOWNS

- Whether the full `tests/config/` slice was green at the exact moment the `[Phase 0]` journal entry was written.
- Whether the current failing test was introduced before or after the Phase 0 package landed.
- Whether any additional non-config slices have drifted since the Phase 0 entry was written.
- Whether a human review checkpoint happened out of band and simply was not recorded.

## 6. Agreed process vs actual process

| Step | Agreed process | Actual process observed in repo history |
|---|---|---|
| 1 | Audit | Audit completed |
| 2 | Roadmap | Roadmap completed |
| 3 | Journal initialization | Journal initialized |
| 4 | Formal Phase 0 planning / review gate | **No recorded gate found** |
| 5 | Phase 0 implementation | Phase 0 technical artifacts landed |
| 6 | Linear status progression in journal | `[Phase 0]` appears directly as `validated` |
| 7 | Open Phase 1 only after clean closure | Not yet opened, but current journal wording would allow it unless corrected |

## 7. Nature of deviation

Classification:

- **Procedural**: yes
  - the journal rules and explicit checkpoint instruction were bypassed
  - no `planned` / `in_progress` progression exists for Phase 0
- **Technical + procedural**: partially
  - technical work really landed, so this is not a fake-completion entry
  - but the `validated` label overstates governance cleanliness
- **Evidence mismatch**: yes
  - the narrow Phase 0 evidence still holds
  - the full `tests/config/` claim recorded in the Phase 0 entry is not fully reproducible on current HEAD

This is therefore **not** a pure technical invalidation of Phase 0. It is a **procedural deviation with a current evidence-reproducibility mismatch**.

## 8. Current truth baseline decision

Decision:

- **Accept the Phase 0 artifact set as the canonical technical baseline of the decomposition initiative.**
- **Do not treat the existing `[Phase 0]` entry as a complete governance proof.**
- **Preserve the existing `[Phase 0]` entry unchanged** to avoid falsifying history.
- **Contextualize it with a recovery checkpoint** stating that Phase 0 was executed before the intended planning/review gate and that one validation claim is not currently reproducible on HEAD.

Historical truth outcome:

- **Preserved**: the repo really contains Phase 0 code/test/artifact changes.
- **Distorted before recovery**: the governance chronology in the journal implied a clean linear gate sequence that did not occur.
- **Normalized after recovery**: the chronology becomes truthful again without erasing the old Phase 0 record.

## 9. Recommended governance recovery action

1. Create this recovery document as the authoritative governance-normalization artifact.
2. Append a new checkpoint entry to [JOURNAL_CONFIG.md](JOURNAL_CONFIG.md) that explicitly records the deviation.
3. Freeze Phase 1 from starting immediately.
4. Require a narrow Phase 0 evidence re-review before Phase 1 may legally begin:
   - classify the current failure at [tests/config/test_btcusdt_aurora_runtime_fields.py](tests/config/test_btcusdt_aurora_runtime_fields.py#L384)
   - decide whether it is unrelated branch drift or whether the Phase 0 validation record itself needs amendment
5. Only after that open `[Phase 1]` with `Status: planned` and review it normally.

## 10. Exact journal changes required

Required journal action:

- append a new entry named `[Checkpoint — Process deviation / governance recovery]` (or equivalent)
- explicitly state that Phase 0 was executed before the originally intended planning/review gate
- distinguish procedural deviation from technical validity
- state that Phase 0 is accepted as canonical technical baseline
- state that current HEAD does not fully reproduce the old full-suite claim because of the failure at [tests/config/test_btcusdt_aurora_runtime_fields.py](tests/config/test_btcusdt_aurora_runtime_fields.py#L384)
- state the next legal step: Phase 0 evidence re-review, then `[Phase 1] planned`, then review

Explicitly **not** required:

- rewriting the old `[Phase 0]` entry
- silently changing the old status labels
- changing any runtime/config logic

## 11. Whether roadmap addendum is needed

**Yes, a small addendum is warranted.**

Reason:

- the core roadmap remains structurally valid
- the phase contents, frozen boundaries, and technical sequencing do not change
- but the roadmap does not currently describe the **re-entry gate** required after an out-of-order Phase 0 execution

Therefore a narrow addendum is appropriate to document the recovered baseline truth and the extra governance gate that must occur before Phase 1 may start.

## 12. Final verdict

1. **Did a process deviation occur?** Yes.
2. **Agreed workflow vs actual workflow?** The planned/review gate was skipped or not recorded before Phase 0 implementation and validation were recorded.
3. **Is the current `[Phase 0]` entry truthful about repo state?** Materially yes for the technical artifacts, but not sufficient as a clean governance record; one validation claim is not currently reproducible on HEAD.
4. **Should Phase 0 be accepted as the new baseline?** Yes, as the canonical technical baseline for this initiative.
5. **What is the next legal step?** Governance recovery acceptance plus a narrow Phase 0 evidence re-review; only then may `[Phase 1]` be opened as `planned`.
6. **Does the roadmap need revision?** Not a structural rewrite; only a narrow addendum defining the re-entry gate.

**Recovered baseline verdict**:

> Phase 0 is accepted as the initiative's canonical technical baseline, but the project may not proceed directly to Phase 1. The historical record must remain intact, the procedural deviation must remain visible, and the current full-suite evidence mismatch must be explicitly reviewed before any further implementation begins.
