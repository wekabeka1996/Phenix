# Primary Cockpit Discovery

## FACTS

Search indicators were `package.json`, `server.ts`, `src/cockpit`, `src/agent`, `.agent_workspace`, and `.git` under `C:\Users\wekab\Music`.

| Path | Git | Package | Source files | Last source write UTC | Runtime |
|---|---:|---|---:|---|---|
| `deepseek-agent-os-p46-preserve` | yes | `react-example@0.0.0` | 422 baseline | Git checkout | validation clone only |
| `deepseek-agent-os-workspace-changes` | no | `react-example@0.0.0` | 432 | `2026-07-04T13:18:54.7806957Z` | Node PID 21984, ports 18081/24678 |

No other directory under the searched roots satisfied at least two Cockpit indicators. Phenix worktrees are separate Python/FastAPI terminal-agent implementations and are not copies of this React repository.

## INFERENCES

The snapshot is the authoritative primary-only source input; the clean clone is the remote canonical baseline and preservation target.

## ASSUMPTIONS

PID 21984 owns the observed snapshot runtime state; process current-directory attribution is not exposed by the captured Windows process record.

## UNKNOWNS

Whether historical Cockpit copies exist outside `C:\Users\wekab\Music` was out of scope.
