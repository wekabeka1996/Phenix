# CONFIG CONTRACT FREEZE — SSOT v1.0

- **Freeze date:** 2025-11-13
- **Version tag:** SSOT v1.0
- **Scope:** Trading configuration contract (execution, exposure, risk, domain modes, instruments).

## Canonical Artefacts

- Schema: `config_schema_v1.py`
- Resolver map: `config_contract_map.md`
- Validation pipeline: `config_validate.py`
- CI guardrail: `.github/workflows/config_contract_ci.yml`

## Freeze Declaration

1. **Structure Locked:** Additive-only changes permitted. Existing fields, defaults, and resolver outputs must remain backward compatible.
2. **Resolvers Mandatory:** `resolve_execution_manage_config`, `resolve_brackets_config`, `resolve_exposure_policy`, `get_trade_cooldown_sec_for_symbol`, daily risk resolver, and trading mode resolver are the only sanctioned entry-points for runtime access.
3. **Direct YAML Reads Forbidden:** Domain code must not navigate raw YAML paths. All config consumers must rely on the resolvers documented in `config_contract_map.md`.
4. **Validation Required:** Any config change must pass `python config_validate.py --ci` locally and via CI before merge.
5. **Freeze Break Procedure:** To introduce breaking structural changes, increment SSOT version, update schema + map, and re-freeze with explicit migration notes.

## Runtime Invariants

- Guardian polling/TTL values remain synchronised between manage resolver output and projected config nodes.
- Exposure caps and leverage defaults are normalised to ratio space ([0, 1]) unless explicitly documented in resolver contract.
- Daily risk limits are evaluated from SSOT snapshot; reset windows must be valid `HH:MM` strings.
- Domain mode mapping must always provide `__default__` fallback matching the selected profile.

## Stewardship Notes

- **Ownership:** Execution Position squad maintains guardian/manage schema; Risk Strategy squad maintains exposure + daily limits.
- **Change Control:** Update schema + contract map first, then code/tests. Do not bypass CI gate.
- **Documentation Sync:** Any resolver extension requires an additive update to `config_contract_map.md` and, if applicable, to freeze notes.
