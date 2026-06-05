# NRR_CONTEXT_APPENDIX_READONLY

- source_artifact: calibrators/datasets/nrr_inventory_post_03t_multiday/nrr_reject_inventory_readonly.json
- config_source_kind: live_workspace_yaml
- frozen_config_snapshot_present: False
- config_caveat: configured_enabled reflects the workspace domains.yaml at artifact build time because the 03U freeze bundle does not retain a config snapshot

| Gate | Runtime Cohort | Structured Fields | Config Authority | Patch Ready? |
| --- | --- | --- | --- | --- |
| NRR-062 | 153 | selected_source, selected_scale, threshold_family | conditional_live_yaml | False |
| NRR-027 | 0 | none | conditional_live_yaml | False |
| NRR-028 | 0 | none | conditional_live_yaml | False |
| NRR-029 | 0 | none | conditional_live_yaml | False |
| NRR-030 | 0 | none | conditional_live_yaml | False |
