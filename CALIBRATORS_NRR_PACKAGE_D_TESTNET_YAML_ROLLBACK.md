# CALIBRATORS_NRR_PACKAGE_D_TESTNET_YAML_ROLLBACK

## rollback_status
- No YAML patch was applied in this package.

## rollback_required
- no

## exact_rollback_instruction
- Leave [config/aurora/domains.yaml](config/aurora/domains.yaml) unchanged.
- Confirm the file hash remains cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962.

## rollback_snippet
```yaml
# No rollback snippet is needed because no package-level YAML mutation was applied.
```

## operator_note
- If a later package introduces a testnet-only LOW_VOL threshold candidate, that package must record a new before/after hash pair and provide a real revert snippet for the edited threshold keys.
