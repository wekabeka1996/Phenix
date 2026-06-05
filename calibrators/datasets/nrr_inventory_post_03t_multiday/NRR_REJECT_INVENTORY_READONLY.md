# NRR_REJECT_INVENTORY_READONLY

- config_source_path: config/aurora/domains.yaml
- config_source_kind: live_workspace_yaml
- frozen_config_snapshot_present: False
- config_interpretation_caveat: configured_enabled reflects the workspace domains.yaml at artifact build time because the 03U freeze bundle does not retain a config snapshot

| Gate | Enabled | Reject Count | Structured Fields Present | Evidence Quality | Patch Ready? |
| --- | --- | ---: | --- | --- | --- |
| NRR-027 | False | 0 | none | no_runtime_rows | False |
| NRR-028 | False | 0 | none | no_runtime_rows | False |
| NRR-029 | False | 0 | none | no_runtime_rows | False |
| NRR-030 | False | 0 | none | no_runtime_rows | False |
| NRR-062 | True | 153 | selected_source, selected_scale, threshold_family | structured_runtime_rejects_present | False |
