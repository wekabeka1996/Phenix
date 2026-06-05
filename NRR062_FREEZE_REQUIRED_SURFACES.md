# NRR062_FREEZE_REQUIRED_SURFACES

| Surface | Role | Required | Bundle Path |
| --- | --- | --- | --- |
| logs/order_log_v1.jsonl | Primary NRR-062 reject and override-admission evidence surface. | yes | logs/order_log_v1.jsonl |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | Decision-terminal authority surface sealing terminal_status and realized outcome context. | yes | logs/shadow_telemetry/decision_ledger_v1.jsonl |
| logs/trade_lifecycle.jsonl | Downstream lifecycle/fill/close evidence surface. | yes | logs/trade_lifecycle.jsonl |
| logs/shadow_critical_event_journal_v1.jsonl | Raw shadow/critical journal override truth and diagnostics. | no | logs/shadow_critical_event_journal_v1.jsonl |
| logs/regime_confidence_audit_v1.jsonl | Regime-confidence diagnostics for boundary review. | no | logs/regime_confidence_audit_v1.jsonl |
| data/recorder/... when --include-recorder is requested | Recorder bars for coverage and replay support. | no | data/recorder/<date>/<symbol>_<tf>.csv |
| config_snapshot/ + config_snapshot_manifest.json | Frozen config authority snapshot and manifest. | yes | config_snapshot/ plus config_snapshot_manifest.json |
| MANIFEST.json | Top-level machine-readable freeze manifest. | yes | MANIFEST.json |
| FREEZE_REPORT.md | Top-level human-readable freeze verdict and missing-surface summary. | yes | FREEZE_REPORT.md |

## Surface Rules

| Surface | Row Count Method | Timestamp Range Method | Missing Behavior |
| --- | --- | --- | --- |
| logs/order_log_v1.jsonl | valid JSON object rows | generic JSONL timestamp scan over ts_ms, ts, timestamp, event_ts_ms, request_ts_ms, response_ts_ms, close_ts_ms, created_ts_ms, updated_ts_ms, snapshot_ts_ms, order_ts_ms, fill_ts_ms, intent_ts_ms, bar_close_ts_ms | block capture if absent because the NRR-062 probe cannot run |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | valid JSON object rows | same generic JSONL timestamp scan; in practice request_ts_ms/response_ts_ms dominate | explicit required_missing entry, capture_verdict CAPTURE_WITH_MISSING_DECISION_LEDGER, authority_complete=false |
| logs/trade_lifecycle.jsonl | valid JSON object rows | same generic JSONL timestamp scan | explicit required_missing entry and capture_verdict CAPTURE_WITH_MISSING_REQUIRED_SURFACES |
| logs/shadow_critical_event_journal_v1.jsonl | valid JSON object rows | same generic JSONL timestamp scan | optional_missing only |
| logs/regime_confidence_audit_v1.jsonl | valid JSON object rows | same generic JSONL timestamp scan | optional_missing only |
| data/recorder/... | CSV data rows excluding header | min/max open_time, ts, or timestamp column when present | copied only when --include-recorder is requested; otherwise not part of the active capture request |
| config_snapshot_manifest.json | not applicable | not applicable | generated whenever capture creates a bundle; summary records any missing config files |
| MANIFEST.json | not applicable | not applicable | generated at end of capture |
| FREEZE_REPORT.md | not applicable | not applicable | generated at end of capture from manifest state |

## Notes

- Package O intentionally preserved the existing config snapshot pathing: the copied config tree lives under config_snapshot/ while the manifest remains at bundle root as config_snapshot_manifest.json.
- Authority completeness for NRR-062 is now tied to the presence of order_log, decision_ledger, and trade_lifecycle, not to optional diagnostics.
