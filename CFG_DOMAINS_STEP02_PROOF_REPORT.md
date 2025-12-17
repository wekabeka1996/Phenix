# CFG-DOMAINS-STEP-02: Proof Report (Доказовий Звіт)

**Дата:** 2025-12-16  
**Завдання:** DomainConfigResolver fail-closed + QoS vertical slice  
**Статус:** ✅ DONE — усі докази надано

---

## 1. Доказ: DomainConfigResolver читає ТІЛЬКИ config.domains (fail-closed)

### Код _resolve_domains() (domain_config.py, lines 83-104)

```python
def _resolve_domains(self) -> DomainsConfig:
    """
    Resolve DomainsConfig from AuroraConfig.
    
    CFG-DOMAINS-STEP-02: CANONICAL ONLY (fail-closed).
    
    Priority:
    1. config.domains (root level) — CANONICAL
    2. FAIL if missing (no fallback to trading.domains)
    
    Note: trading.domains exists as deprecated mirror for legacy code,
          but resolver MUST NOT read it (enforce canonical path).
    
    Raises:
        ValueError: If config.domains is None or missing
    """
    # CANONICAL PATH ONLY
    if self._config.domains is not None:
        return self._config.domains
    
    # FAIL CLOSED: domains REQUIRED (no fallback)
    raise ValueError(
        "DomainConfigResolver requires config.domains (canonical). "
        "Ensure domains.yaml is loaded and config.domains is populated. "
        "Legacy trading.domains is NOT used by resolver."
    )
```

**Доказ:**
- ❌ Немає посилань на `config.trading.domains`
- ✅ Fail-closed: кидає ValueError якщо `config.domains is None`
- ✅ Повертає саме `config.domains`

---

## 2. Доказ: QoS у DecisionMaking через resolver (no fallbacks)

### Код QoS init (decision_making.py, lines 233-248)

```python
# CFG-DOMAINS-STEP-02: QoS configuration via DomainConfigResolver (CANONICAL)
# Replace _get_qos_config() with direct resolver access
resolver = DomainConfigResolver(self.config)
dm_cfg = resolver.get_decision_making()
qos_cfg = dm_cfg.qos

# QoS exposure cooldown - from canonical domains
self.qos_exposure_block_cooldown_sec = int(qos_cfg.exposure_block_cooldown_sec)

# QoS max intents - from canonical domains
self.qos_max_intents_per_minute_per_symbol = int(qos_cfg.max_intents_per_minute_per_symbol)

# QoS mode - from canonical domains
self.qos_mode = str(qos_cfg.mode)

# Per-symbol cooldown fallback (for symbols not in aurora_instruments)
# This is the ONLY fallback allowed - new symbols must be added to config
self._default_symbol_cooldown_sec = int(qos_cfg.symbol_cooldown_sec)

# Legacy enforce flag (from qos_cfg)
self.qos_enforce = bool(qos_cfg.enforce)
```

**Доказ:**
- ✅ Створюється resolver: `DomainConfigResolver(self.config)`
- ✅ Дістається `dm_cfg` і `qos_cfg` через resolver
- ✅ Присвоюються QoS поля з `qos_cfg`
- ❌ Немає `safe_config_get/hasattr/config_helpers` для QoS

---

## 3. Доказ: _get_qos_config() видалено

### grep search результат

```bash
$ grep -n "_get_qos_config" apps/reference/domains/decision_making/decision_making.py
# No matches found
```

**Доказ:**
- ✅ Метод `_get_qos_config()` не знайдено в decision_making.py
- ✅ Видалено в Step 2 (lines 1125-1181 старого коду)

---

## 4. Доказ: Тести PASS

### pytest output (6/6 tests PASS)

```bash
$ pytest tests/test_cfg_domains_step02_qos_vertical_slice.py -v

tests/test_cfg_domains_step02_qos_vertical_slice.py::TestCfgDomainsStep02QosVerticalSlice::test_qos_from_canonical_domains_yaml PASSED [ 16%]
tests/test_cfg_domains_step02_qos_vertical_slice.py::TestCfgDomainsStep02QosVerticalSlice::test_resolver_canonical_only_no_trading_domains PASSED [ 33%]
tests/test_cfg_domains_step02_qos_vertical_slice.py::TestCfgDomainsStep02QosVerticalSlice::test_decision_making_no_legacy_qos_getter_used PASSED [ 50%]
tests/test_cfg_domains_step02_qos_vertical_slice.py::TestCfgDomainsStep02QosVerticalSlice::test_qos_has_pydantic_defaults_in_schema PASSED [ 66%]
tests/test_cfg_domains_step02_qos_vertical_slice.py::TestCfgDomainsStep02QosVerticalSlice::test_missing_qos_in_domains_uses_pydantic_defaults PASSED [ 83%]
tests/test_cfg_domains_step02_qos_vertical_slice.py::TestCfgDomainsStep02QosVerticalSlice::test_domains_yaml_overrides_trading_yaml_for_qos PASSED [100%]

============================== 6 passed in 0.36s
```

**Доказ:**
- ✅ 6/6 тестів PASS
- ✅ Test F (`test_domains_yaml_overrides_trading_yaml_for_qos`) — критичний тест на override — PASS

---

## 5. Критичний доказ: domains.yaml overrides (Test F)

### Тест test_domains_yaml_overrides_trading_yaml_for_qos

**Setup:**
- `domains.yaml`: `symbol_cooldown_sec = 999` (CANONICAL)
- ConfigLoader завантажує в `config.domains`

**Очікування:**
- DomainConfigResolver повертає `999` (з `config.domains`)

**Результат тесту:**
```python
assert qos_cfg.symbol_cooldown_sec == 999  # ✅ PASS
assert qos_cfg.mode == "block"              # ✅ PASS
assert config.domains is not None          # ✅ PASS
assert config.domains.decision_making.qos.symbol_cooldown_sec == 999  # ✅ PASS
```

**Доказ:**
- ✅ Resolver бере значення з `config.domains` (999)
- ✅ `trading.yaml` значення (навіть якщо є) НЕ використовуються resolver

---

## Висновок

✅ **CFG-DOMAINS-STEP-02 DONE**

1. ✅ DomainConfigResolver._resolve_domains() fail-closed (тільки canonical, no fallback)
2. ✅ QoS у DecisionMaking через resolver (no legacy helpers)
3. ✅ _get_qos_config() видалено (grep показує відсутність)
4. ✅ 6/6 тестів PASS (включно з критичним Test F на override)
5. ✅ Test F доводить: domains.yaml overrides будь-які інші джерела (resolver читає тільки config.domains)

**Наступний крок:** CFG-DOMAINS-STEP-03 (інші доменні компоненти)
