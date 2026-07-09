# P38C Instruction Contract

## Required Files

Instruction root: `docs/agent_arena_instructions/`

- `AGENT_ARENA_RULES.md`
- `AGENT_SKILLS.md`
- `AGENT_TRADING_STYLE.md`
- `FEATURE_TRUST_GUIDE.md`
- `SESSION_OBJECTIVE.md`
- `SUBAGENT_RULES.md`

Missing required files are not defaulted. The manifest marks them in `missing_files` and preflight emits `status: missing_required_files`.

## Manifest Entry

Each instruction entry contains:

- `path`
- `sha256`
- `version`
- `updated_at`
- `priority`
- `target_agents`
- `missing`

Paths must be safe relative paths. Absolute paths and `..` traversal are rejected.

## Manifest

`build_instruction_manifest(root_dir=".")` returns:

- `manifest_version`
- `generated_at`
- `instruction_root`
- ordered `instructions`
- `missing_files`

The manifest version is derived from instruction paths, hashes, versions, and missing state.

## Agent Preflight

`agent_instruction_preflight(...)`:

- loads current manifest
- compares against optional previous manifest
- returns changed files
- returns missing files
- emits an `agent_instruction_refresh` event payload
- marks `ack_required` when changed or missing files exist

This is a caller-invoked preflight layer. No background watcher or live agent loop was added in P38C.

## ACK

`acknowledge_instruction_manifest(...)` produces:

- `agent_id`
- `agent_number`
- `session_id`
- `manifest_version`
- `acknowledged_at`

Unsafe agent/session identifiers are rejected.
