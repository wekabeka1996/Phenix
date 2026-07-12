# Configuration And Contract

## FACTS

- YAML SSOT field: `memory.canonical_sessions_root: ".agent_memory/sessions"`.
- `MemoryConfig` forbids unknown fields and rejects absolute/traversing relative values.
- `load_settings` binds the resolved project root from the config file location.
- `Settings.canonical_memory_root()` fails when the field or config-root binding is absent and returns an absolute resolved path otherwise.
- `CanonicalMemoryStore` rejects missing/relative storage roots.
- Every record requires `record_id`, `session_id`, `agent_id`, `agent_number`, sequence, kind, timezone-aware `created_at`, content, `instruction_version`, and explicit event/command/source references.

## INFERENCES

- Relative YAML plus an explicit config-file anchor is portable while preventing current-working-directory authority.

## ASSUMPTIONS

- Config remains located either under `config/` or at an explicitly supplied project-root config path, as covered by loader tests.

## UNKNOWNS

- Container deployment path was not started; resolution is unit-tested only.

