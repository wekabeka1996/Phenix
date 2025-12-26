# CFG_EXECUTION_SSOT_FAIL_CLOSED_DONE.md

## Статус: ✅ ЗАВЕРШЕНО

**Дата:** 2025-01-XX  
**Мета:** Видалити ВСІ hardcoded fallback значення з execution domain. YAML через Pydantic — єдине джерело істини.

---

## Зміни

### 1. Нові Pydantic моделі (config_models.py)

```python
class EventDedupConfig(BaseModel):
    max_size: int = 100000
    ttl_ms: int = 86400000

class TrailingDefaultsConfig(BaseModel):
    activation_pct: float = 0.003
    trail_pct: float = 0.006
    min_update_interval_sec: int = 5

class EmergencyConfig(BaseModel):
    enabled: bool = False
    wait_mode_bars: int = 2
    emergency_sl_bps: int = 100  # NEW
```

### 2. YAML конфігурація

**domains.yaml:220-221**
```yaml
event_dedup:
  max_size: 100000
  ttl_ms: 86400000
```

**trading.yaml:106-108**
```yaml
emergency:
  enabled: false
  wait_mode_bars: 2
  emergency_sl_bps: 100
```

**system.yaml:40-42**
```yaml
trailing:
  activation_pct: 0.003
  trail_pct: 0.006
  min_update_interval_sec: 5
```

### 3. Fail-closed код

| Файл | Параметр | Було | Стало |
|------|----------|------|-------|
| fsm.py | event_dedup | `dedup_max = 100000` fallback | `raise ValueError("event_dedup config is required")` |
| fsm.py | idempotent_cancel | `max_retries = 2` fallback | `raise ValueError("idempotent_cancel config is required")` |
| fsm_manage.py | anti_race_close_ms | `800` fallback | `raise ValueError("anti_race_close_ms is required")` |
| fsm_manage.py | emergency | inline defaults | fail-closed when enabled |
| fsm_manage.py | trailing | `0.003/0.006` fallback | `raise ValueError("trailing config is required")` |
| fsm_open.py | idempotency_window_sec | `60` fallback | `raise ValueError("idempotency_window_sec is required")` |

### 4. Тести

**tests/config/test_fail_closed_config_loading.py** — 9 тестів:
- `test_fsm_fails_without_event_dedup_config`
- `test_fsm_loads_event_dedup_from_config`
- `test_fsm_fails_without_idempotent_cancel_config`
- `test_manage_fsm_fails_without_anti_race_close_ms`
- `test_open_fsm_fails_without_idempotency_window`
- `test_production_config_has_all_required_values`
- `test_no_fallback_patterns_in_fsm`
- `test_no_fallback_patterns_in_fsm_manage`
- `test_no_fallback_patterns_in_fsm_open`

---

## SSOT Summary Table

| Config | YAML Location | Pydantic Model | Code Location |
|--------|--------------|----------------|---------------|
| sl.fixed_bps=40 | trading.yaml:99 | BracketsConfig | fsm.py (resolver) |
| tp.fixed_bps=80 | trading.yaml:101 | BracketsConfig | fsm.py (resolver) |
| anti_race_close_ms=800 | trading.yaml:108 | ExecutionConfig | fsm_manage.py |
| event_dedup.max_size=100000 | domains.yaml:220 | EventDedupConfig | fsm.py |
| event_dedup.ttl_ms=86400000 | domains.yaml:221 | EventDedupConfig | fsm.py |
| emergency.wait_mode_bars=2 | trading.yaml:107 | EmergencyConfig | fsm_manage.py |
| emergency.emergency_sl_bps=100 | trading.yaml:108 | EmergencyConfig | fsm_manage.py |
| trailing.activation_pct=0.003 | system.yaml:40 | TrailingDefaultsConfig | fsm_manage.py |
| trailing.trail_pct=0.006 | system.yaml:41 | TrailingDefaultsConfig | fsm_manage.py |
| idempotency_window_sec=60 | domains.yaml:193 | FsmOpenConfig | fsm_open.py |
| idempotent_cancel.max_retries=2 | domains.yaml:212 | IdempotentCancelConfig | fsm.py |

---

## Тестування

```bash
# Execution domain tests
python3 -m pytest tests/domains/execution_position/ -v
# Result: 205 passed in 2.65s

# Fail-closed policy tests
python3 -m pytest tests/config/test_fail_closed_config_loading.py -v
# Result: 9 passed in 0.22s
```

---

## Правила (SSOT Policy)

1. **Ніяких hardcoded defaults в runtime коді** — тільки YAML через Pydantic
2. **Fail-closed при відсутності конфігу** — `ValueError`, не silent fallback
3. **Кожен параметр задокументований** у SSOT таблиці
4. **Тести перевіряють fail-closed поведінку** та production конфіг

---

## Наступні кроки

- [ ] Аудит інших domains на аналогічні fallback patterns
- [ ] Regression тести для кожного нового параметра
- [ ] Моніторинг production логів на `ValueError` при старті
