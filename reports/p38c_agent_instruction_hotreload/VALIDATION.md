# Validation

## Commands

From `C:\Users\wekab\Music\Phenix-p38c-instruction-hotreload\tools\deepseek-terminal-agent`:

`python -m pytest tests/test_agent_instruction_manifest.py tests/test_agent_instruction_runtime.py`

Result:

`10 passed in 0.22s`

From `C:\Users\wekab\Music\Phenix-p38c-instruction-hotreload`:

`git diff --check`

Result:

No whitespace errors reported.

## Coverage

- `test_manifest_preserves_priority_ordering`
- `test_manifest_detects_file_change`
- `test_manifest_reports_missing_required_file`
- `test_instruction_path_traversal_is_rejected`
- `test_manifest_does_not_mutate_trading_config`
- `test_preflight_returns_changed_files_and_refresh_payload`
- `test_preflight_reports_missing_required_file`
- `test_acknowledge_instruction_manifest_produces_ack`
- `test_ack_rejects_path_traversal_identifiers`
- `test_preflight_does_not_mutate_trading_config`

## Not Proven

- No live agent loop was started.
- No dashboard endpoint was added.
- No runtime scheduler proof exists that agents will call preflight within minutes.
