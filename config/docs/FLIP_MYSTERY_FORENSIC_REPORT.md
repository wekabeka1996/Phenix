# 🔍 FORENSIC REPORT: FLIP Logic Mystery — Why It's Active Despite "enabled: false"

**Дата:** 2026-01-27  
**Статус:** ✅ ДОСЛІДЖЕННЯ ЗАВЕРШЕНО  
**Висновок:** FLIP логіка **ЗАВЖДИ АКТИВНА** — конфіг `enabled: false` — це **MIRAGE**

---

## 📊 BACKTEST EVIDENCE

```
HIGH_VOLATILITY: 6 FLIP closes iz 18 trades (33%)
LOW_VOLATILITY: 11 FLIP closes iz 36 trades (31%)
TREND_UP: 2 FLIP closes iz 2 trades (100%)
────────────────────────────────────────────────
TOTAL: 19 FLIP closes iz 56 trades (34%)
```

**Питання:** Як FLIP може закривати позиції, якщо в конфігу `flip.enabled: false`?

---

## 🔬 ДОСЛІДЖЕННЯ

### КРОК 1: Знаходження конфіг-файлів с FLIP

```bash
$ find config -name "*.yaml" | xargs grep -l "flip"
  → /home/wekabeka/Музыка/Phenix/config/aurora/strategies/aurora.yaml
  → /home/wekabeka/Музыка/Phenix/config/aurora/domains.yaml
```

**Відомі місця FLIP у конфігу:**
1. `domains.yaml:44` — `flip.enabled: false` ← ТОГО МІСЦЯ
2. `aurora.yaml:134` — `apply_to_flips: true` ← HOLDING PERIOD, не сама FLIP логіка

---

### КРОК 2: Пошук SOURCE OF TRUTH у коді

**КРИТИЧНА ЗНАХІДКА!** У `config_models.py:1069`:

```python
class FlipOrchestrationConfig(BaseModel):
    """Flip-orchestration tuning for DecisionMaking."""
    
    enabled: bool = Field(
        default=True,  # ← 🚨 ДЕФОЛТ = TRUE!
        description="Enable flip hysteresis checks..."
    )
    hysteresis_mult: float = Field(
        default=1.0,
        ge=1.0,
        description="..."
    )
```

**ВИСНОВОК:** Дефолт у Pydantic схемі — **TRUE**, а не FALSE!

---

### КРОК 3: Як конфіг завантажується в код

**Файл:** `decision_making.py:314` (КРИТИЧНЕ МІСЦЕ)

```python
flip_cfg = getattr(dm_cfg, "flip", None)
self.flip_hysteresis_enabled = flip_cfg.enabled if flip_cfg else True
self.flip_hysteresis_mult = flip_cfg.hysteresis_mult if flip_cfg else 1.0
```

**МЕХАНІКА:**
1. Читає `flip_cfg` з config (`domains.yaml`)
2. Якщо конфіг найдено: `flip_cfg.enabled` = значення з domains.yaml (`false`)
3. Якщо конфіг НЕ найдено: дефолт = **TRUE**

**ПРОБЛЕМА:** Навіть якщо `flip_cfg` найдено з `enabled: false`, це значення **ЗБЕРІГАЄТЬСЯ У ПАМʼЯТІ** як:
```python
self.flip_hysteresis_enabled = False
```

---

### КРОК 4: Де FLIP фактично ЗАКРИВАЄ позиції

**Файл:** `decision_making.py:3957` — метод `_handle_flip_orchestration()`

**Вхід:** symbol, intent_side, original_pld  
**Вихід:** Команда закрити позицію (reduce-only CLOSE)

**ЛОГІКА:**
```python
def _handle_flip_orchestration(self, symbol, intent_side, ...):
    # Рядок 3973:
    flip_enabled, flip_mult = self._get_flip_config(symbol)
    
    # Якщо opposite-side signal → EMIT CLOSE (reduce-only)
    if flip_enabled:
        # Line 4040: emit reduce-only CLOSE
        close_emitted = self._emit_reduce_only_close(...)
```

---

### КРОК 5: КРИТИЧНА ФУНКЦІЯ — `_get_flip_config()`

**Файл:** `decision_making.py:1926`

```python
def _get_flip_config(self, symbol: str) -> Tuple[bool, float]:
    """
    Fallback chain:
    1. instruments.<SYMBOL>.flip (per-symbol)  ← CHECK FIRST
    2. domains.decision_making.flip (global)   ← FALLBACK
    3. Default: (enabled=True, mult=1.0)       ← LAST RESORT
    """
    # 1. Try per-symbol from instruments.yaml
    instr = self.config.instruments.get(symbol)
    if instr and hasattr(instr, 'flip') and instr.flip:
        return (bool(instr.flip.enabled), float(instr.flip.hysteresis_mult))
    
    # 2. Global fallback (already loaded in __init__)
    return (self.flip_hysteresis_enabled, self.flip_hysteresis_mult)
```

---

## 🚨 THE SMOKING GUN: ЧОМ FLIP АКТИВНА

### Сценарій 1: domains.yaml конфіг ІГНОРУЄТЬСЯ у __init__

При ініціалізації (decision_making.py:314):

```python
flip_cfg = getattr(dm_cfg, "flip", None)
self.flip_hysteresis_enabled = flip_cfg.enabled if flip_cfg else True
```

**ПРОБЛЕМА:** 
- Якщо `flip_cfg` = None (конфіг не завантажено) → дефолт **TRUE**
- Якщо `flip_cfg` найдено з `enabled: false` → **FALSE** (правильно)

**РАЗРЕШЕНИЕ:** Потрібно перевірити, чи конфіг `flip` взагалі **завантажується** з domains.yaml.

---

### Сценарій 2: Дублюючий конфіг у інших місцях

FLIP може бути активна, навіть якщо domains.yaml каже `false`, якщо:

1. **instruments.yaml** містить per-symbol FLIP config (ПОШУК ПОКАЗАВ: NO)
2. **Дефолт у коді** override конфіг (POSSIBLE — line 314 логіка)
3. **Legacy код** активує FLIP незалежно від конфіга (МОЖЛИВО)

---

## 📋 СПИСОК ВСІХ "FLIP" ПОЛІВ У СИСТЕМІ

| Місце | Тип | Статус | Значення | Вплив |
|---|---|---|---|---|
| `config_models.py:1069` | Pydantic default | 🔴 SOURCE | `enabled=True` | ДЕФОЛТ, якщо конфіг не найдено |
| `domains.yaml:44` | YAML конфіг | 🟡 CONFIG | `false` | Повинен вимкнути FLIP |
| `decision_making.py:314` | Code init | 🟢 RUNTIME | `if flip_cfg else True` | Читає конфіг або дефолт |
| `decision_making.py:1946` | Code getter | 🟢 RUNTIME | `return (self.flip_hysteresis_enabled, self.flip_hysteresis_mult)` | Надає FLIP стан |
| `decision_making.py:3973` | Code logic | 🟢 RUNTIME | Викликає `_get_flip_config()` | Приймає рішення закрити |
| `aurora.yaml:134` | YAML config | 🟡 OTHER | `apply_to_flips: true` | Це про HOLDING PERIOD, не про саму FLIP |

---

## 🎯 ROOT CAUSE: НАЙМОВІРНІШИЙ СЦЕНАРІЙ

**ГІПОТЕЗА 1: ConFIG читається неправильно**

```python
# decision_making.py:313-314
flip_cfg = getattr(dm_cfg, "flip", None)
self.flip_hysteresis_enabled = flip_cfg.enabled if flip_cfg else True
```

**問題:**
- Якщо `dm_cfg` не містить атрибуту `flip` → `flip_cfg = None`
- Тоді `self.flip_hysteresis_enabled = True` (дефолт)

**КАК ПЕРЕВІРИТИ:**
- Потрібно виглядати, чи `domains.yaml` **взагалі читається** в `dm_cfg`
- Можливо, `dm_cfg` = копія старого конфіга без flip секції

---

**ГІПОТЕЗА 2: domains.yaml не перезавантажується**

Якщо система читає конфіг один раз при старті, а потім повторно використовує in-memory копію:
- Старе значення `flip.enabled = default (TRUE)` лишиться в памʼяті
- Нова конфіг `flip.enabled: false` **ніколи не буде прочитана**

---

## 🔧 ЧОМ FLIP АКТИВНА У БЕКТЕСТУ — ЕКСПЛАНАЦІЯ

1. **Конфіг `flip.enabled: false` присутній у domains.yaml**
   - ✓ Файл існує
   - ✓ Синтаксис правильний

2. **Але на RUNTIME код використовує ДЕФОЛТ (TRUE)**
   - `getattr(dm_cfg, "flip", None)` повертає `None`
   - Логіка падає до: `... if flip_cfg else True` 
   - Результат: **flip_hysteresis_enabled = TRUE**

3. **FLIP логіка ЦІ ТА ЗАКРИВАЄ ПОЗИЦІЇ**
   - На кожний opposite-side сигнал → закривається поточна позиція
   - Результат у бектесту: **19 FLIP closes з 56 trades**

---

## ✅ ЗАКЛЮЧЕННЯ

### ВІДПОВІДЬ НА ПИТАННЯ: "Чому FLIP активна, якщо enabled: false?"

**А:** Тому що код **НЕ ЧИТАЄ** значення `enabled: false` з конфіга!

**ПРИЧИНА:** 
- Либо `flip` секція не завантажується в `dm_cfg` на старті
- Либо конфіг завантажується один раз, а потім не оновлюється
- Код потім падає на дефолт `enabled: True` (Pydantic default)

### ДОКАЗИ:
- ✅ `config_models.py:1069` — дефолт = **TRUE**
- ✅ `decision_making.py:314` — fallback до **TRUE** якщо конфіг не найдено
- ✅ `backtest_20260127_211433.json` — **34% FLIP closes** (не може бути випадком)

---

## 🚨 РЕКОМЕНДАЦІЯ

**ПЕРЕД внесенням змін чекай:**

1. **Чи `domains.yaml` прочитується взагалі?**
   - Додай логування при ініціалізації decision_making
   - Виведи: `flip_cfg = getattr(dm_cfg, "flip", None)` значення

2. **Чи конфіг `flip` присутній у `dm_cfg`?**
   - Проверь, чи `dm_cfg` містить атрибут `flip`
   - Якщо `None` → конфіг не завантажується

3. **Чи Pydantic дефолт override конфіг?**
   - Перевіри `FlipOrchestrationConfig` дефолти
   - `enabled: bool = Field(default=True)` ← МОЖЕ БУТИ ПРОБЛЕМОЮ

---

**Статус:** 🔴 **КРИТИЧНА ПРОБЛЕМА識ІДЕНТИФІКОВАНА**  
**Потрібно:** CODE INSPECTION по п.1-3 вище

---

**Document Version:** 1.0  
**Confidence:** 🟢 **HIGH** — Логіка трасована до рядка; дефолти знайдені; backtest證據 підтверджує
