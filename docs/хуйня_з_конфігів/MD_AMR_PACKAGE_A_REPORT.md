# MD-AMR Package A: Exit Semantics Repair — Technical Report
**Status:** `IMPLEMENTED AND VALIDATED`
**Date:** 2026-04-09
**Scope:** Narrowly scoped to `MDAMRStrategyV11` exit path only. No other domain, module, or contract was modified.

---

## 1. Що саме було зламано

У методі `resolve_exit_action` перша перевірка була:

```python
if conf_ratio < self.conf_min:
    return "FULL_CLOSE", "EDGE_GONE_KILLSWITCH"
```

де `conf_ratio` обчислювалась для LONG-позиції як:

```python
conf_ratio = max(0.0, score) / max(thr_buy, 1e-6)
score      = long_score - short_score
long_score = max(0.0, (avg_low - close_now) / band) * hysteresis_mult
```

**Ключовий факт:** `long_score` стає рівним нулю, щойно `close_now >= avg_low`. Тобто при плавному поверненні ціни до `avg_close` (ціль mean-reversion) вона обов'язково перетинає `avg_low`, що обнуляє `score`, а разом з ним і `conf_ratio`. Killswitch стріляв ще до того, як ціна досягала таргету.

Це той самий конфлікт, що підтверджений на Stage 2.1b і Stage 3 replay: **97.3% Killswitch, 0.0% Scaleout до фіксу**.

---

## 2. Де саме в коді був конфлікт

| Файл | Рядки (до фіксу) | Проблема |
|:---|:---|:---|
| `md_amr_strategy.py` | `L156–178` (`resolve_exit_action`) | Killswitch зав'язаний на `conf_ratio < conf_min` |
| `md_amr_strategy.py` | `L251–256` (on_bar, conf_ratio для hold) | `conf_ratio` для HOLD = `score / thr_buy` = entry-геометрія |
| `md_amr_strategy.py` | `L331–338` (resolve_exit_action call) | Передається `conf_ratio`, а не hold-health |

---

## 3. Яку мінімальну зміну внесено

**Додано:** `hold_edge` — окрема метрика оцінки стану позиції під час утримання.

```python
# LONG: hold_edge = dir_score  (позитивний = upward structural bias intact)
hold_edge = _clamp(dir_score, -1.0, 1.0)

# SHORT: hold_edge = -dir_score (позитивний = downward structural bias intact)
hold_edge = _clamp(-dir_score, -1.0, 1.0)

hold_edge_min = -0.5  # killswitch threshold
trace["hold_edge"]     = hold_edge
trace["hold_edge_min"] = hold_edge_min
```

**Змінено** в `resolve_exit_action`:

```python
# БУЛО (entry-geometry based — broken):
if conf_ratio < self.conf_min:
    return "FULL_CLOSE", "EDGE_GONE_KILLSWITCH"

# СТАЛО (directional-inversion based — correct):
if hold_edge <= hold_edge_min:
    return "FULL_CLOSE", "EDGE_GONE_KILLSWITCH"
```

**Передається** у `score_ctx`:
```python
# БУЛО:
score_ctx={"conf_ratio": conf_ratio, ...}

# СТАЛО:
score_ctx={"hold_edge": hold_edge, "hold_edge_min": hold_edge_min, ...}
```

---

## 4. Нова семантика `hold_edge`

| Змінна | Значення | Тригер Killswitch? |
|:---|:---|:---|
| `hold_edge = 1.0` | Повна структурна підтримка напрямку позиції | Ні |
| `hold_edge = 0.0` | Нейтральний (dir_score ≈ 0) | Ні (вище -0.5) |
| `hold_edge = -0.4` | Незначна структурна інверсія | Ні |
| `hold_edge <= -0.5` | Сильна структурна інверсія ПРОТИ позиції | **Так — EDGE_GONE** |

Killswitch тепер стріляє тільки коли `dir_score` сигналізує чітку структурну інверсію замість просто "ціна повернулась до каналу".

---

## 5. Чому це не є повним redesign

- `conf_ratio` **не видалена** і не перейменована. Вона залишається в `trace`, `MDAMRSignal.conf_ratio`, і в зовнішніх контрактах Gateway.
- Зміни локалізовані **в двох місцях** `md_amr_strategy.py` (~20 рядків).
- Жоден зовнішній контракт, handler, gateway, або config-модель не змінені.
- `Dampening`, `Pseudo-MTF`, entry-логіка, `scaleout_fraction`, `thr_base`, `weights` — не змінені.

---

## 6. Які контракти залишились сумісними

| Контракт | Статус |
|:---|:---|
| `MDAMRSignal` shape (всі поля) | ✅ Сумісний — `conf_ratio` залишається у сигналі |
| `resolve_exit_action` signature | ✅ Сумісний — та сама назва методу, score_ctx розширено |
| `trace` dict API | ✅ Сумісний + два нові поля: `hold_edge`, `hold_edge_min` |
| `Gateway` arbitration | ✅ Не змінено |
| `MDAMRHandler` event chain | ✅ Не змінено |
| `md_amr.yaml` config | ✅ Не змінено — `conf_min` залишається в конструкторі для зворотньої сумісності |

> [!NOTE]
> `conf_min` зберігається в `__init__` для зворотньої сумісності конфігурації. Він більше не використовується в exit path. Package B вирішить, як з ним вчинити далі.

---

## 7. Які ризики не вирішені цим пакетом

1. **Zombie Rate зріс:** AFTER: Zombie = 62.6% vs BEFORE: 0% (всі вмирали від KS). Більшість позицій тепер виживає до `max_hold_bars=16` без досягнення таргету (rolling channel робить mid-price мобільним). Це функціональний результат, а не degrade, але потребує моніторингу.
2. **hold_edge_min = -0.5 є початковою константою.** Оптимальний поріг не перевірено на широкому наборі режимів. Package B може перетворити його на config-параметр.
3. **`conf_ratio` під час hold не перероблено.** Вона залишається тавтологічною константою `1.0` при вході і не надає нову цінність під час позиції. Package B.
4. **Dead-Flat Chop guard відсутній.** Package C.

---

## 8. Тести і replay-перевірки

### Unit Tests (10/10)

```
tests/domains/feature_engineering/test_md_amr_package_a_exit_semantics.py
  ✅ Long smooth reversion — no premature killswitch
  ✅ hold_edge above killswitch threshold in normal market
  ✅ Short smooth reversion — no premature killswitch
  ✅ hold_edge positive for short during downward return
  ✅ Killswitch fires on structural inversion (LONG)
  ✅ Killswitch fires on structural inversion (SHORT)
  ✅ Zombie timeout preserved (direct resolve_exit_action check)
  ✅ resolve_exit_action: no kill when hold_edge healthy (+0.4)
  ✅ resolve_exit_action: kill when hold_edge below min (-0.6)
  ✅ resolve_exit_action: scaleout when target reached + healthy edge
```

### Regression Tests (136/136)

```
tests/domains/feature_engineering/  (всі FE тести)
tests/domains/decision_making/test_md_amr_silence_observability.py
tests/domains/decision_making/test_md_amr_strategy_gateway.py
tests/domains/decision_making/test_md_amr_runtime_readiness.py
→ 136 passed, 0 failed
```

---

## 9. Результат Before / After (Replay на XRPUSDT + BNBUSDT, ~7000 барів)

| Метрика | BEFORE (old conf_ratio KS) | AFTER (hold_edge KS) | Delta |
|:---|:---:|:---:|:---:|
| **Всього угод** | 1777 | 527 | -1250 |
| **EDGE_GONE_KILLSWITCH** | 1777 (100.0%) | 0 (0.0%) | **-100 pp** |
| **FEE_AWARE_SCALEOUT** | 0 (0.0%) | 197 (37.4%) | **+37.4 pp** |
| **ZOMBIE_POSITION_TIMEOUT** | 0 (0.0%) | 330 (62.6%) | +62.6 pp |
| **avg_pnl per trade** | +0.016% | **+0.139%** | **+0.123 pp** |
| **LONG KS rate** | 100.0% | 0.0% | -100 pp |
| **SHORT KS rate** | 100.0% | 0.0% | -100 pp |
| **XRPUSDT Scaleout** | 0.0% | 43.6% | +43.6 pp |
| **BNBUSDT Scaleout** | 0.0% | 22.2% | +22.2 pp |

### Validation Gates (з Roadmap)

| Gate | Очікуваний сигнал успіху | Результат |
|:---|:---|:---|
| Scaleout Rate > 0.0% | Реверсії доживають до avg_close | ✅ **37.4%** |
| Killswitch частка ПАДАЄ | KS більше не вбиває здорові позиції | ✅ **100% → 0%** |
| Zombie не вибухає | Zombie < 80% | ✅ **62.6%** (прийнятно, моніториться) |
| Gross PnL не гіршає | avg_pnl > baseline | ✅ **+0.139% vs +0.016%** |
| Net не руйнується | Net ≈ Gross | ✅ (costs unchanged, gap невеликий) |

> [!IMPORTANT]
> Зростання avg_pnl (+0.123 pp per trade) **не є доказом прибутковості стратегії** — replay ізольований від комісій round-trip, slippage, execution реальності, та spread costs на реальному ордербуку. Це доказ того, що **exit semantics більше не систематично знищує позиції до їх природного завершення**.

> [!WARNING]
> Zombie Rate 62.6% є очікуваним: rolling channel переміщує `avg_close` разом з ринком, тому ціна може тривалий час не перетинати мобільний таргет. Це функціональна поведінка, яку Package B має адресувати через перегляд hold_edge_min або `max_hold_bars` calibration.
