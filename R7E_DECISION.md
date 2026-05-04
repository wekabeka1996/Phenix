# R7E Decision

The current source tree constructs the R7C fields, the direct trade_lifecycle write path preserves additive nested payloads, and the current restarted runtime now writes sidecar_config_snapshot, peak_giveback_snapshot, peak_giveback_state, and null_reasons into raw trade_lifecycle JSONL.

That current post-restart proof rules out serializer loss, event-bus normalization, missing source construction, and event-name mismatch as explanations for the original missing-field slice.

The strongest localization is therefore historical stale runtime deployment: the earlier slice that R7D inspected was not running the R7C-capable build, and restart onto the correct build resolved the observability gap without any code change.

STALE_RUNTIME_BUILD
