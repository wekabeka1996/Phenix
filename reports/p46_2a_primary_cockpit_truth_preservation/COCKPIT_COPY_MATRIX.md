# Cockpit Copy Matrix

## FACTS

| Candidate | Classification | Basis |
|---|---|---|
| `C:\Users\wekab\Music\deepseek-agent-os-p46-preserve` | `REMOTE_CANONICAL_CLONE` | Git clone at exact `workspace-changes@15e63ce5` |
| `C:\Users\wekab\Music\deepseek-agent-os-workspace-changes` | `PRIMARY_SOURCE_SNAPSHOT` | no `.git`; 14 substantive source differences; active runtime state |
| snapshot `dist/` | `GENERATED_BUILD` | Vite output, excluded |
| snapshot `.agent_workspace/runtime_store/` | `RUNTIME_STATE_ONLY` | live SQLite and runtime artifacts, excluded |
| Phenix terminal dashboard copies | `UNRELATED_PROJECT` | FastAPI/Jinja session tool, not React `deepseek-agent-os` clone |

The source comparison is recorded in `cockpit_source_comparison.json` and `cockpit_normalized_source_comparison.json`.

## INFERENCES

Creating another application is unnecessary; preservation is additive to the existing remote repository.

## ASSUMPTIONS

Line-ending-only differences carry no source semantics.

## UNKNOWNS

No detached Git metadata for the snapshot was found.
