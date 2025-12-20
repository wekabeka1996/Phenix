# TASK27.6 — `.to_dict()` Regression Vector Check

## Claim
“Presence of `.to_dict()` is an architectural hole / regression vector (typed config can leak back into dict-thinking).”

## Status
PARTIAL

- ✅ Confirmed: `AuroraConfig.to_dict()` exists (config → dict conversion is available).
- ✅ Mitigated (runtime domains): policy gates explicitly ban `.to_dict()` usage in `apps/reference/domains/**` except a small DTO/payload allowlist.
- ⚠️ Residual risk: tests and non-domain modules can still call `config.to_dict()` unless separately gated.

## Evidence

### Config `.to_dict()` exists
- `apps/reference/config_loader.py:64` — `class AuroraConfig(PydanticAuroraConfig)`
- `apps/reference/config_loader.py:72`–`apps/reference/config_loader.py:75` — `def to_dict(self) -> Dict[str, Any]: return self.model_dump()`

### Runtime policy gates against config-to-dict relapse in domains
- `tests/runtime/test_task24_policy_gates.py:56`–`tests/runtime/test_task24_policy_gates.py:82`
  - AST gate: fails if `config.to_dict()` is detected in `apps/reference/domains/**`.
- `tests/runtime/test_task25_no_legacy_config_access_in_domains.py:7`–`tests/runtime/test_task25_no_legacy_config_access_in_domains.py:14`
  - `.to_dict()` allowed only for DTO/payload serialization in allowlisted domain files.

### Current runtime `.to_dict()` uses inside `apps/reference/` are DTO/payload-oriented (not config fallback)
Examples:
- `apps/reference/domains/execution_position/drift_monitor.py:101` — serializing drift report payload.
- `apps/reference/domains/execution_position/fsm.py:1236` — `p.to_dict()` behind `hasattr(...)` for payload objects.
- `apps/reference/services/order_guardian.py:412` — `raw_order.to_dict()` for order payload normalization.

### No `config.to_dict()` usage in `apps/reference/main.py`
- Repo grep found no `.to_dict()` calls in `apps/reference/main.py` at time of audit.

## Conclusion
`.to_dict()` exists on the config object (so the regression vector exists in principle), but runtime domain code is guarded by AST policy tests that block config-to-dict relapse. The remaining risk is primarily outside the domains directory (and in tests), where `.to_dict()` can still be used unless additional gates are added.

