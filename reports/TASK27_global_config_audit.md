# TASK27.5 — Global Config via `config_symbols.py`

## Claim
“Project has a global config singleton via `config_symbols.py`.”

## Status
PARTIAL

- ✅ Confirmed: there is a **global config singleton** implemented in `apps/reference/config_loader.py` (`_config_instance` + `get_config()`).
- ❌ Disproved (narrow reading): `apps/reference/config_symbols.py` does **not** define or export a module-level `config` object; it only calls `get_config()` inside helper functions.

## Evidence

### `config_symbols.py` exists
- `apps/reference/config_symbols.py:20` — defines `get_trading_symbols()`

### `config_symbols.py` uses `get_config()` lazily (no module-scope singleton there)
- `apps/reference/config_symbols.py:40`–`apps/reference/config_symbols.py:42` — imports and calls `get_config()` inside the function body.

### Actual global singleton (module-level cache)
- `apps/reference/config_loader.py:934` — `_config_instance: Optional[AuroraConfig] = None`
- `apps/reference/config_loader.py:937`–`apps/reference/config_loader.py:942` — `get_config()` populates and returns `_config_instance`.

### Import surface of `config_symbols` (who depends on it)
- `tools/metrics_summary.py:131` (tools)
- `tests/test_config_symbols_hardcode_removal.py:3` (tests)
- `tests/config/test_config_symbols_one_truth.py:20` (tests)
- No runtime imports found under `apps/reference/domains/**` at time of audit.

## Conclusion
Global config access exists (singleton `get_config()`), but it is implemented in `config_loader`, not as a module-global exported from `config_symbols.py`. `config_symbols.py` is a thin helper layer that depends on that singleton.

