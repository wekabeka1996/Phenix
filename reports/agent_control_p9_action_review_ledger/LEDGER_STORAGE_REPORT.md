# Ledger storage report

Path: `ops/agent_bridge/action_reviews/action_review_ledger_v1.jsonl`.

The store uses a thread lock, `O_APPEND`, one bounded JSON row, fsync, and strict typed reads. Identical review/revision appends are idempotent; conflicting duplicates fail. New reviews start at revision 1. Later revisions increment exactly once, carry an exact `supersedes_ref`, and preserve created time, mode/source, agent/model/operator refs, packet/symbol/horizon, PreActionNote, and ExecutionNote.

Runtime ledger: two rows, one review, revisions 1 and 2; offline lint errors: zero. The 4 MiB read bound and 16 KiB row bound prevent unbounded payload ingestion. Multi-process locking is not claimed.
