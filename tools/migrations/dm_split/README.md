# Decision Making Split Toolkit

This directory contains the Package 2 migration toolkit for the bounded
`apps/reference/domains/decision_making/` Variant A internal modularization.

Runbook:

```powershell
python tools/migrations/dm_split/01_collect_inventory.py
python tools/migrations/dm_split/audit_imports.py --root apps/reference/domains/decision_making --out tools/migrations/dm_split/artifacts/package3_pre_audit.md
python tools/migrations/dm_split/03_audit_dynamic_imports.py
python tools/migrations/dm_split/02_build_rename_plan.py
python tools/migrations/dm_split/04_rewrite_imports.py --dry-run --write-diff=tools/migrations/dm_split/artifacts/package2_dry.diff
python tools/migrations/dm_split/05_move_files.py
python tools/migrations/dm_split/04_rewrite_imports.py
python tools/migrations/dm_split/06_write_shims.py
python tools/migrations/dm_split/07_update_yaml_json.py
python tools/migrations/dm_split/08_verify.py
```

`dm_move_map.csv` is the source of truth for Python file moves. Every script is
idempotent and supports `--dry-run`.
