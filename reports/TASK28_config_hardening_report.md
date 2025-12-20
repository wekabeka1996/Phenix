# TASK28 — CONFIG HARDENING (P1): Remove Optional-required Trap + Minimize Hydration

Дата: 2025-12-19

## TL;DR

- Вирівняно Pydantic-схему для root/meta/strategy блоків: прибрано пастки `Optional[...] = Field()` там, де loader раніше був змушений «підпирати» schema.
- `ConfigLoader` більше **не робить schema-compensation hydration** через `setdefault(...)`.
- Allowlisted мутації збережено:
  - legacy migration `root.guardian` → `execution.order_guardian`
  - runtime meta injection (але **тільки post-validation**, через `model_copy(update=...)`)
- Додано policy тести: schema‑gate, loader‑no‑injection, deterministic `symbols_to_track`, guardian allowlist, AST‑gate на singleton.

## Before/After: hydration / setdefault

### Видалені hydration блоки (було → стало)

- `meta.setdefault("system_config_version", None)` / `meta.setdefault("regime_config_version", None)` → прибрано; schema приймає відсутність цих ключів як `None`.
- `merged_config.setdefault("aurora", None)` / `merged_config.setdefault("mean_reversion", None)` → прибрано; optional strategy blocks **не інжектяться** як `null` лише заради валідації.
- `merged_config.setdefault("trading", {})` + `trading_block.setdefault("symbols_to_track", ...)` → прибрано; policy винесено в schema (див. нижче).
- `system_meta["runtime"].setdefault("config_name" ...)` / `setdefault("config_dir" ...)` **до validation** → прибрано; runtime meta інжектиться **після** успішної валідації.

### Докази (file:line)

- В `ConfigLoader` **немає** `setdefault(`:
  - `grep -n "setdefault(" apps/reference/config_loader.py` → (порожній вивід)

- Новий чистий merge-хук без hydration:
  - `apps/reference/config_loader.py` `def _merge_config_fragments(...)` — [apps/reference/config_loader.py](apps/reference/config_loader.py#L176-L358)

- Runtime meta injection **post-validation**:
  - `apps/reference/config_loader.py` `_inject_runtime_meta()` — [apps/reference/config_loader.py](apps/reference/config_loader.py#L360-L367)

## Before/After: Optional-required traps (P1 scope)

| Поле | Було | Стало | Причина |
|---|---|---|---|
| `SystemMetaConfig.system_config_version` | `Optional[str] = Field()` (required trap) | `Optional[str] = Field(default=None)` | YAML може не мати version; loader не має інжектити `null` |
| `SystemMetaConfig.regime_config_version` | `Optional[str] = Field()` (required trap) | `Optional[str] = Field(default=None)` | те саме |
| `SystemRuntimeMeta.config_name` | `Optional[str] = Field(...)` (required trap) | `Optional[str] = Field(default=None)` | runtime-only meta, не має бути required у YAML |
| `SystemRuntimeMeta.config_dir` | `Optional[str] = Field(...)` (required trap) | `Optional[str] = Field(default=None)` | те саме |
| `SystemMetaConfig.runtime` | `SystemRuntimeMeta = Field()` (forced presence) | `Optional[SystemRuntimeMeta] = Field(default=None)` | runtime meta інжектиться post-validation |
| `AuroraConfig.domains` | `Optional[DomainsConfig] = Field(...)` (trap) | `DomainsConfig = Field(...)` (required) | domains SSOT обов’язковий; fail‑closed |
| `AuroraConfig.strategies_registry` | `Optional[...] = Field()` (trap) | `Optional[...] = Field(default=None)` | optional block має бути truly optional |
| `AuroraConfig.mean_reversion` | `Optional[...] = Field()` (trap) | `Optional[...] = Field(default=None)` | optional block |
| `AuroraConfig.models` | `Optional[...] = Field()` (trap) | `Optional[...] = Field(default=None)` | optional block |
| `AuroraConfig.aurora` | `Optional[Dict] = Field()` (trap) | `Optional[Dict] = Field(default=None)` | optional block |

Докази (file:line):
- `SystemConfig/SystemMetaConfig/SystemRuntimeMeta/AuroraConfig` — [apps/reference/config_models.py](apps/reference/config_models.py#L1459-L1553)

## symbols_to_track policy (explicit & deterministic)

### Вибрана політика

- `TradingConfig.symbols_to_track` може бути відсутнім у YAML.
- Якщо відсутній — він **детерміністично** deriv’иться з `trading.decision.symbols_to_track`.
- Якщо немає обох — **fail-closed** (ValidationError).

Докази (file:line):
- `TradingConfig.symbols_to_track` + `@model_validator _derive_symbols_to_track` — [apps/reference/config_models.py](apps/reference/config_models.py#L1320-L1381)

## Guardian migration allowlist

- Єдина allowlisted root мутація: `guardian` → `execution.order_guardian`.
- Вона виконується **до** валідації як backward-compat міграція, бо root `extra=forbid`.

(Докази тестом: див. `test_guardian_migration_only_allowed_root_mutation`.)

## Тести (нові)

- `tests/config/test_task28_schema_no_optional_required_trap.py`
  - `test_optional_fields_have_defaults_or_not_optional_for_root_blocks`
  - `test_loader_does_not_inject_required_optional_keys_before_validation`
  - `test_symbols_to_track_policy_is_explicit_and_deterministic`
  - `test_guardian_migration_only_allowed_root_mutation`
- `tests/runtime/test_task28_no_config_singleton_in_domains.py`
  - AST‑gate: забороняє `get_config()` singleton у `apps/reference/domains/**`.

### Виконано

```bash
pytest -q tests/config/test_task28_schema_no_optional_required_trap.py tests/runtime/test_task28_no_config_singleton_in_domains.py
# 5 passed
```

## Validation commands (evidence)

### Python

```bash
python3 -c "import sys; print(sys.version)"
# 3.12.3 ...
```

### Loader validation (SSOT → validated config)

```bash
python3 -c "from apps.reference.config_loader import ConfigLoader; c=ConfigLoader().load_config(); print('OK', c.trading_mode, len(c.trading.symbols_to_track), bool(c.system_meta.runtime))"
# OK hybrid_live_data_testnet_exec 5 True
```

### Config structural validator

```bash
python3 tools/validate_configs.py
# ✅ All configurations are valid! (warn: missing BINANCE_TESTNET_API_KEY/SECRET)
```

## Tooling note: `rg` not available

Обов’язкові для SSOT команди `rg -n ...` неможливо виконати в цьому Linux середовищі (ripgrep не встановлено, і немає прав на `apt install`). Еквівалентні докази надані через:
- `grep -n` (0 збігів для `setdefault(` у loader)
- `nl -ba ... | sed -n ...` для точних `file:line` посилань

## Exceptions / Out of scope

- У `apps/reference/config_models.py` все ще є багато `Optional[...] = Field()` поза P1 scope (не root/meta/strategy). TASK28 змінює **лише** блокери, що змушували loader робити hydration.
- `TradingConfig.risk` dict — не чіпався (P2, не в scope).

