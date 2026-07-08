# Filter parity history report

Production path: `ops/agent_bridge/parity_history/filter_parity_history_v1.jsonl`.

The writer uses an in-process lock plus `O_APPEND`, one encoded line per write, flush/fsync, a deterministic observation id, and duplicate-id rejection. Reads are bounded at 4 MiB and skip invalid lines. Rows contain only hashes/refs and classifications.

Runtime rows: 0 before P7 startup, 70 at evidence close across seven configured symbols. BTCUSDT and ETHUSDT each demonstrated `new`, periodic `unchanged`, a TTL-boundary `worsened` to stale, and recovery (`improved` for BTCUSDT, `resolved` for ETHUSDT). The representative sample contains those transitions.
