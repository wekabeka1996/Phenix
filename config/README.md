# Config Namespace — SSOT Contract

## Canonical Runtime Config

| Path | Role | Loaded by |
|---|---|---|
| `config/aurora/` | **Primary runtime config directory (SSOT)** | `ConfigLoader` in `apps/reference/config_loader.py`, `main.py` |
| `config/alpha_search.yaml` | Alpha-search domain config | `apps/reference/domains/alpha_search/` |
| `config/alpha_search_system.yaml` | Alpha-search system config | `apps/reference/domains/alpha_search/` |
| `config/overlays/` | Runtime YAML patch overlays | Applied on top of `config/aurora/` at load time |

## Support Files (not loaded as config)

| Path | Role |
|---|---|
| `config/_schemas/` | JSON Schema definitions for config validation |
| `config/docs/` | Strategy and domain passports (documentation) |
| `config/alpha_search/` | Alpha-search scenario definitions |

## Archived Snapshots

Historical config snapshots are stored outside this namespace in
`archive/config_snapshots/`. They are **never loaded by runtime**.
See `archive/config_snapshots/README.md` for details.

## Rules

1. `config/aurora/` is the **only** canonical runtime config directory.
2. Additional config root directories under `config/` are **forbidden** unless explicitly approved.
3. All runtime-impacting config changes go into `config/aurora/` or `config/overlays/`.
4. Non-runtime snapshots, baselines, or backtest profiles must live outside `config/` (in `archive/`).
