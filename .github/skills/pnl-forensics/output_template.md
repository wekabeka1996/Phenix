# Фінансове розслідування — PnL Forensics

## Вхідні параметри
- Часовий діапазон:
- Символи:
- Опис аномалії:
- Задіяні джерела доказів:

---

## Розділ 1 — Підсумок балансу

| Метрика | Значення | Джерело |
|---------|----------|---------|
| Поточний equity (USDT) | | extract_equity_free_usdt.py |
| Free USDT | | extract_equity_free_usdt.py |
| Зміна балансу за період | | |
| Unrealized PnL | | check_positions.py |

---

## Розділ 2 — Підрахунок ORDER_INTENT подій

| Фаза (source_fsm) | Кількість | % від загального |
|-------------------|-----------|-----------------|
| ExposureGuard | | |
| DecisionMaking | | |
| ExecPosFSM | | |
| **ВСЬОГО** | | 100% |

### Відхилені інтенти (DECISION_INTENT_REJECTED)

| NRR-код | Кількість | Причина |
|---------|-----------|---------|
| | | |

---

## Розділ 3 — Класифікація позицій

| Категорія | Кількість | % |
|-----------|-----------|---|
| ACTIVATED (є fill) | | |
| REJECTED (валідація) | | |
| ORPHANED_TTL | | |
| **ВСЬОГО** | | 100% |

---

## Розділ 4 — Детальний аналіз позицій

### Позиція #1
**rid**: `...`
**Символ**: | **Сторона**: | **Режим**: | **Впевненість**: 

#### Фаза відкриття (ORDER_INTENT)
| Параметр | Значення |
|----------|----------|
| Час (UTC) | |
| source_fsm | |
| Ціна | |
| Кількість | |
| Режим | |
| NRR-verdict | |

#### Мікроструктура ринку при відкритті (features)
| Feature | Значення | Інтерпретація |
|---------|----------|---------------|
| obi (order book imbalance) | | |
| tfi (trade flow imbalance) | | |
| delta_price | | |
| spread_bps | | |
| volatility_state | | |
| pillar_sum | | |
| pillar_strategist | | |
| pillar_tactician | | |

**Відповідність features рішенню системи**: ✓ Підтверджено / ✗ Суперечність / ? Невизначено

#### Виконання (FILL)
| Параметр | Значення |
|----------|----------|
| Час fill (UTC) | |
| fill_price | |
| fill_qty | |
| fill_fees (USDT) | |
| Відхилення від order_price | |

#### Закриття позиції
| Параметр | Значення |
|----------|----------|
| Час закриття (UTC) | |
| close_reason | |
| Механізм закриття | TP / SL / TTL / NRR / Policy / Sidecar |

#### Мікроструктура ринку при закритті (features)
| Feature | Значення | Зміна відносно входу |
|---------|----------|---------------------|
| pillar_sum | | |
| volatility_state | | |
| delta_price | | |

#### PnL розрахунок
| Показник | Значення (USDT) |
|----------|-----------------|
| PnL_gross | |
| fill_fees | |
| **PnL_net** | |

**Статус**: ПРИБУТОК / ЗБИТОК / БЕЗЗБИТКОВО

---

## Розділ 5 — Агрегована PnL таблиця

### По символу
| Символ | Кількість позицій | PnL_net (USDT) | Середній PnL | Win rate |
|--------|------------------|----------------|--------------|----------|
| | | | | |

### По причині закриття
| close_reason | К-ть | PnL_net (USDT) | Внесок у збиток |
|---|---|---|---|
| TP | | | |
| SL | | | |
| TTL_EXPIRED_3600s | | | |
| NRR-EXECUTION-REJECTED | | | |
| CMD_OPEN_VALIDATION_FAIL | | | |
| POSITION_DISAPPEARANCE_ATTRIBUTED | | | |
| **ВСЬОГО** | | | |

### По режиму
| Режим | К-ть | PnL_net (USDT) | Avg regime_confidence |
|-------|------|----------------|----------------------|
| | | | |

---

## Розділ 6 — Sidecar та Policy аналіз

| Подія | Кількість | Вплив |
|-------|-----------|-------|
| POSITION_POLICY_SIDECAR_SUPPRESSED | | |
| startup_grace_active | | |
| evaluation_mode=phase1_recommendation_only | | |

**Висновок щодо Sidecar**: 

---

## Розділ 7 — Gate аналіз

| Gate | Кількість блокувань | Avg rv_bps | Avg cost_bps | Вплив на PnL |
|------|--------------------:|-----------|-------------|-------------|
| LOW_VOL_COST_SUPPRESS | | | | |

**Висновок щодо Gate**: 

---

## Розділ 8 — Хронологічна реконструкція (UTC)

```
[YYYY-MM-DD HH:MM:SS UTC] rid=... ORDER_INTENT (ExposureGuard) — reservation_created
[YYYY-MM-DD HH:MM:SS UTC] rid=... ORDER_INTENT (DecisionMaking) — regime=X conf=Y
[YYYY-MM-DD HH:MM:SS UTC] rid=... ORDER_INTENT (ExecPosFSM) — LIMIT price=Z
[YYYY-MM-DD HH:MM:SS UTC] rid=... FILL — fill_price=A qty=B fees=C
  [features] obi=D tfi=E spread=F pillar_sum=G
[YYYY-MM-DD HH:MM:SS UTC] rid=... CLOSE — close_reason=H PnL_net=I
  [features] obi=J tfi=K pillar_sum=L
```

---

## Розділ 9 — Первинна причина збитку

**Основна причина** [ФАКТ / ВИСНОВОК / НЕПІДТВЕРДЖЕНО]:

**Сприяючі фактори** [ФАКТ / ВИСНОВОК]:
1.
2.
3.

**Патерн втрати коштів**:

---

## Розділ 10 — Рекомендації

| Пріоритет | Проблема | Рекомендація | Інструмент/Конфіг |
|-----------|----------|--------------|-------------------|
| P0 | | | |
| P1 | | | |
| P2 | | | |

---

## Рішення
- **Статус**: КРИТИЧНО / ПІДТВЕРДЖЕНО / ПОТРЕБУЄ ПЕРЕВІРКИ / ЗАБЛОКОВАНО
- **Обґрунтування**:
- **Наступні кроки**:
