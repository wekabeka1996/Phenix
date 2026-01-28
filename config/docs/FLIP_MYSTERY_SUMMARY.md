# 📌 FLIP MYSTERY: QUICK SUMMARY

## 🔴 ПРОБЛЕМА

| Факт | Доказ |
|---|---|
| **Конфіг каже:** | `domains.yaml:44` — `flip.enabled: false` |
| **Бектест показує:** | 19 FLIP closes з 56 trades (34%) — FLIP АКТИВНА |
| **Парадокс:** | Логіка вимкнена, але активна |

---

## 🔍 ROOT CAUSE (НАЙІМОВІРНІШЕ)

```python
# decision_making.py:314 — КРИТИЧНЕ МІСЦЕ
flip_cfg = getattr(dm_cfg, "flip", None)
self.flip_hysteresis_enabled = flip_cfg.enabled if flip_cfg else True
                                                         ↑
                                            ДЕФОЛТ = TRUE
```

**Механіка:**
1. Конфіг `domains.yaml` читається як об'єкт `dm_cfg`
2. Код шукає атрибут `flip` у `dm_cfg`
3. **ЯКЩО НЕ ЗНАЙДЕНО** → дефолт = **TRUE**
4. FLIP активується незалежно від `enabled: false`

---

## 🎯 WHAT'S HAPPENING AT RUNTIME

```
domains.yaml: flip.enabled: false
         ↓ (читання конфіга)
decision_making.__init__:
  flip_cfg = getattr(dm_cfg, "flip", None)
         ↓
  Якщо flip_cfg == None → self.flip_hysteresis_enabled = True
         ↓
  (Система ініціалізує FLIP з дефолтом TRUE)
         ↓
backtest execution:
  _handle_flip_orchestration() → FLIP закриває позиції
         ↓
Result: 34% FLIP closes (виглядає як активна логіка)
```

---

## 🔧 ЧОМ ДЕФОЛТ = TRUE

**У config_models.py:1069:**

```python
class FlipOrchestrationConfig(BaseModel):
    enabled: bool = Field(default=True)  ← ДЕФОЛТ TRUE!
    hysteresis_mult: float = Field(default=1.0)
```

**ПИТАННЯ:** Чому дефолт = True?
- Ймовірно, для safety (на випадок, якщо конфіг не прочитається)
- Але це означає, що **FLIP буде активна, доки її явно не вимкнеш**

---

## ✅ ЧО ЦЕ ОЗНАЧАЄ

| Сценарій | Статус | Дія |
|---|---|---|
| FLIP у конфігу: `enabled: false` | ✓ Є | Повинна вимкнути FLIP |
| Код читає конфіг: `getattr(dm_cfg, "flip", None)` | ⚠️ Залежить | Якщо `None` → дефолт |
| Дефолт у schema: `enabled: True` | ✓ Є | Fallback, якщо конфіг НЕ прочитається |
| Результат у бектесту: 34% FLIP closes | ✓ Є | **Доказ, що дефолт переважає** |

---

## 🚨 NEXT STEPS

1. **ДОДАТИ ЛОГУВАННЯ** в `decision_making.py:314`:
   ```python
   flip_cfg = getattr(dm_cfg, "flip", None)
   self.logger.info(f"DEBUG: flip_cfg={flip_cfg}")
   if flip_cfg:
       self.logger.info(f"DEBUG: flip_cfg.enabled={flip_cfg.enabled}")
   ```

2. **ЗАПУСТИТИ BACKTEST** з логуванням

3. **ПЕРЕВІРИТИ LOG:**
   - Чи `flip_cfg` буде `None`? (якщо так → дефолт переважає)
   - Чи `flip_cfg.enabled` буде `False`? (якщо так → конфіг прочитується)

4. **ЯКЩО `flip_cfg == None`:**
   - Проблема в завантаженні конфіга
   - Необхідно перевірити `dm_cfg` структуру

---

**ДЕТАЛЬНИЙ ЗВІТ:** [FLIP_MYSTERY_FORENSIC_REPORT.md](FLIP_MYSTERY_FORENSIC_REPORT.md)
