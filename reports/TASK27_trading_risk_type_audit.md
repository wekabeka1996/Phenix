# TASK27.2 — TradingConfig.risk Type Bomb Check

## Claim
“`TradingConfig.risk: Dict[str, Any]` breaks object-access (code expects `cfg.trading.risk.*`).”

## Status
PARTIAL

- ✅ Confirmed: `cfg.trading.risk` is **a dict** in the typed schema (so `cfg.trading.risk.some_attr` would be a bug).
- ❌ Disproved (runtime): repo runtime code that touches `cfg.trading.risk` treats it as a dict and type-checks it; no real object-access hits found in runtime code.

## Evidence

### Definition (schema)
- `apps/reference/config_models.py:1337` — `risk: Dict[str, Any] = Field(description='Legacy risk configuration (daily gate, etc)')`

### Runtime usage: explicit dict handling (safe vs “object-access bomb”)
- `apps/reference/domains/execution_position/exposure_guard.py:164` — `risk_cfg = self.config.trading.risk`
- `apps/reference/domains/execution_position/exposure_guard.py:165` — `if not isinstance(risk_cfg, dict): raise ConfigContractError(...)`
- `apps/reference/domains/risk_management/daily_gate.py:67` — comment states “Dict[str, Any]”
- `apps/reference/domains/risk_management/daily_gate.py:75` — dict access: `daily_cfg = risk_cfg["daily"] if isinstance(risk_cfg, dict) ...`

### “Object-access” hits (`cfg.trading.risk.*`)
- `tests/conftest.py:27` and `tests/conftest.py:28` — only hit; uses `MagicMock()` (test fixture), not the real typed `TradingConfig.risk`.
- Repo-wide grep for runtime `.trading.risk.` shows no other attribute-chain usages outside tests.

## Conclusion
`TradingConfig.risk` is intentionally a dict “legacy block”. This would break object/attribute access, but current runtime code uses dict access with explicit type checks, so the “type bomb” does not manifest in the current codepaths.

