# TASK23B — timeframe_sec forensic (SSOT precedence)

## TL;DR

`timeframe_sec` for **mean_reversion_1m** comes from the strategy profile SSOT by default, but can be overridden per-symbol via `aurora_instruments.<SYM>.timeframe_sec`. We enforce a single precedence contract and fail-closed when both sources are missing.

## SSOT sources (YAML)

### Strategy profile (default)

- File: `config/aurora/strategies/mean_reversion_1m.yaml`
- Key: `mean_reversion_1m.timeframe_sec`
- Previously observed mismatch: value `180` with comment “1 minute bars”
  - Fixed to `60` to match 1-minute bars.

### Per-symbol override

- File: `config/aurora/aurora_instruments.yaml`
- Key: `BTCUSDT.timeframe_sec` (and other symbols)
- This key is nullable (often `null`) and acts as an override when set.

## Code consumption

### Mean Reversion handler

- File: `apps/reference/domains/decision_making/mean_reversion_handler.py`
- Uses `self._mr_config.timeframe_sec` as the bar timeframe.
- Removed silent fallback (`or 60`) to avoid hidden defaults; missing values must be caught by the config contract.

### Loader (where precedence is applied)

- File: `apps/reference/config_loader.py`
- Function: `ConfigLoader._apply_timeframe_sec_ssot_precedence()`
- Called during `ConfigLoader.load_config()` before Pydantic validation.

## Effective precedence (contract)

For strategy `mean_reversion_1m` **when it is assigned in** `strategies_registry.assignments`:

1. `aurora_instruments.<SYM>.timeframe_sec` if not null (highest precedence)
2. `mean_reversion_1m.timeframe_sec` from strategy profile
3. If both are missing → **ConfigContractError** (fail-closed)

## Why this fixes “180 != 60”

The observed mismatch was traced to the SSOT profile value in `mean_reversion_1m.yaml` (comment/value inconsistency). After correcting SSOT to `60` and enforcing a single precedence path, tests stop depending on accidental runtime fallbacks or magic.
