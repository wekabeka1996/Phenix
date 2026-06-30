# Rotation and bounded-tail behavior report

Observed source sizes at the end of the window:

- `shadow_critical_event_journal_v1.jsonl`: 301,438,422 bytes, actively updated.
- `decision_ledger_v1.jsonl`: 2,370,977 bytes.
- `order_log_v1.jsonl`: 164,733 bytes, actively updated.

For each source, the reducer sought from EOF and read at most 524,288 bytes / 200 lines. Results were 200 journal rows, 103 decision rows, and 200 order rows. The journal and decision reads reported `leading_partial_line_discarded`, proving the live bounded offset path tolerated an initial partial record. Old events outside the window were intentionally omitted.

No destructive rotation stress was performed. The snapshot reducer is coded to select up to the three newest snapshot files and tolerate partial lines, but current BTCUSDT/ETHUSDT snapshot files were missing, so live newest-file rollover was not observed. Rotation tolerance remains unit-proven, not live-rotation-proven.

Packet latency was 2.09–2.44 seconds. Although no full scan occurred even on the 301 MB journal, this latency should be profiled before increasing poll frequency.
