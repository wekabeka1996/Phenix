# ActionReviewV1 contract design

ActionReviewV1 is a versioned envelope with immutable identity and three layers:

- `PreActionNoteV1`: packet-linked observation, proposed scoped action, thesis/invalidation, up to three expected scenarios, warnings/data/tool refs, confidence, and literal no-execution flag.
- `ExecutionNoteV1`: one of five non-submission statuses, `submitted=false`, no-execution detail, and no order/fill fields.
- `OutcomeReviewV1`: later packet window, factual observation, realized scenario/confidence, expected/unexpected flags, explanation, lesson, future-review flag, and literal no-PnL-claim flag.

P9 sources are deterministic fixture, manual operator, or no-model local sample. `model_id` and `model_call_ref` are null. Raw material is referenced rather than embedded. Full rows are capped at 16 KiB and 1,200 estimated tokens.
