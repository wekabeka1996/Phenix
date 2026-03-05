# Дослідження архівних конфігурацій та їх порівняння з Production

## Вступ
Цей звіт є результатом аналізу всіх YAML файлів у директорії `config/aurora/archive/` та їх порівняння з актуальними бойовими конфігураціями (`config/aurora/strategies/aurora.yaml`, `mean_reversion.yaml` та інші). Мета дослідження — визначити, які з архівних прогонів найбільше відповідають поточній архітектурі, які метрики є релевантними, та розмежувати підтримку полів на глобальному та пер-символьному рівнях.

---

## 1. Аналіз архівних прогонів (Archive YAMLs)

В архіві знаходяться результати різних етапів оптимізації (Optuna):

1. **`aurora_fullscale_optuna_v1.yaml`**: Оптимізація Mean Reversion на 1m (DOGE найкращий, Calmar 6.91). Використовує Bollinger Bands (BB), фіксовані TP (`tp_low_ratio`, `tp_high_ratio`), Trailing Stop, Cooldown.
2. **`aurora_optimal_full_v1.yaml`** (Phase 3+ Full): Тренд-фоловінг (ETH, XRP, BTC). Введено `take_profit` логіку, `trailing_stop`, `regime_sizing` та `regime_thresholds`.
3. **`aurora_optimal_production_v1.yaml`**: Стара Phase 2 (без розширених фаз виходу).
4. **`aurora_phase3_production.yaml`**: Розширений Phase 3. Введено `side_bias`, детальний `regime_sizing`, EMA Clamping, `risk_weights`.
5. **`traiding_best_optuna_3_5m.yaml`**: Найважливіший архівний прогін для поточної стратегії Aurora (Aurora Multi-Timeframe v4.0). Доводить, що **TFI (Trade Flow Imbalance) та OBI є головною альфою** (weight > 0.35 для більшості активів). Включає ETH на 5m та SOL на 3m.
6. **`trading_1m_best_optuna.yaml`**: R&D конфіг для Mean Reversion на 1m (позначено як не інтегрований, хоча зараз MR працює на 3m/5m базах з іншою структурою параметрів).

### Які прогони найбільше наближені до поточних конфігів?
- Для **Aurora**: `aurora_phase3_production.yaml` та `aurora_optimal_full_v1.yaml` найбільш структурно схожі на `aurora.yaml` в плані використання `side_bias`, `regime_sizing` та TP/SL. Однак поточний `aurora.yaml` пішов далі: запроваджено **V2 Scoring (Direction/Strength)** та динамічний `regime_tpsl`, чого не було в архівах.
- Для **Mean Reversion**: Жоден архівний файл не відповідає поточній структурі на 100%. В архіві вказано використання `min_vol_atr` та абсолютних значень `sl_pct`. В бойовому `mean_reversion.yaml` використовуються `sl_atr_mult`, `tp_to_mid` та специфічні режими (`FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`).

---

## 2. Підтримка полів у системі (Supported vs Unsupported)

Аналіз бази коду (включаючи `fsm.py`, `fsm_manage.py`, `aurora_handler.py` та схеми) показує наступне:

### Підтримуються та активно використовуються:
* **`take_profit`**: Підтримується (перевірено в `fsm_manage.py`). Обов'язкові поля `tp_low_ratio`, `tp_high_ratio` (хоча `partial_exit_pct` може не повністю підтримуватись біржею без складного ордер-менеджменту, логіка розрахунку дистанцій присутня).
* **`trailing_stop`**: Підтримується (`enabled`, `activation_pct`, `trail_pct`, `min_update_interval_sec`).
* **`regime_sizing`**: Підтримується. У поточних конфігах впливає на базовий розмір ордера залежно від режиму (HIGH_VOLATILITY, LOW_VOLATILITY тощо).
* **`regime_tpsl` (Нове, немає в архіві)**: Дуже активно використовується в `aurora.yaml` (`sl_mult`, `tp_mult` для різних режимів).
* **`side_bias`**: Підтримується (Anti-Persistency penalty).
* **`volatility_entry_logic`**: Підтримується (розумний відступ для LIMIT GTX ордерів).
* **`holding_period` & `reentry_cooldown_sec`**: Підтримуються (Anti-Churn gates).
* **`liquidity_gate`**: Підтримується на рівні символу.

### НЕ підтримуються, застарілі або змінені:
* `legacy_tick_path_enabled` — видалено.
* `kappa_mode`, `risk_fraction_q` — видалено.
* Розділ `account_observer` — видалено, система перейшла на Futures-only FSM.
* Всі старі конфігурації `trading_1m_best_optuna.yaml` (з RSI та 1m таймфреймом) для MR були адаптовані. В поточному коді MR використовує `sl_atr_mult` (замість статичного `sl_pct`) і генерується на основі 3m/5m барів.
* `macro_sync` як скоринг-метрика замінена на **`macro_resid`** у V2 Scoring. Стара метрика залишена лише для телеметрії.

---

## 3. Сфера застосування налаштувань (Global vs Per-Symbol)

У новій архітектурі SSOT (Single Source of Truth) спостерігається чітке розмежування:

### Глобально (Global / System-wide)
* `strategies_registry.assignments`: Якому символу яка стратегія належить (`BTCUSDT` -> `aurora`, `DOGEUSDT` -> `mean_reversion`). Арбітраж пріоритетів (`aurora`: 1, `mean_reversion`: 2).
* **Aurora Decision Gates (`aurora.decision`)**: `anchor_shock_veto`, `gates` (Anti-Flat, Anti-FOMO з `sigma`-показниками), `qos` (rate limiting на рівні інтентів).
* **V2 Scoring Base**: `direction_strength_scoring` (розподіл фічей на directional та strength, глобальні альфа-капи).
* **Feature Engineering**: Параметри розрахунку EMA, Volume, Volatility, OBI/TFI.

### Пер-Символьно (Per-Symbol - `assets.<SYMBOL>`)
Майже весь ризик та виконання конфігурується індивідуально:
* `leverage` (target, mode: "ISOLATED").
* `weights`: Ваги сигналів (наприклад, TFI/OBI домінують для SOL, `volume_spike` для BTC). **Зверніть увагу, що бойові ваги у `aurora.yaml` відкалібровані ridge регресією (2026-03-03) і можуть бути від'ємними (наприклад, `ema_bias`, `depth_imbalance`), чого не було в Optuna архівах.**
* `regime_thresholds` та `regime_sizing`.
* `exit`: Базовий `sl_pct` та динамічний блок `regime_tpsl` (мультиплікатори).
* `take_profit` (`tp_low_ratio`) та `trailing_stop`.
* `holding_period` та `reentry_cooldown_sec`: Агресивніші (довші) для ETH/SOL, і дуже короткі для BTC.

---

## 4. Які метрики з архівів ми дійсно можемо використати?

Звітні метрики в архівних файлах (такі як `pnl_usd`, `win_rate`, `calmar`, `trades` в розділах `training_metrics` або `performance`) є **ідеалізованими результатами бектестів**.

### Що МОЖНА використовувати:
1. **Відносна цінність фічей**: Якщо в архіві (наприклад, `traiding_best_optuna_3_5m.yaml`) TFI має вагу `0.471` для ETH і дає найкращий Win Rate (67.7%), це свідчить про високу інформативність фічі. Ми можемо використовувати ці знання для визначення базових конфігурацій передRidge калібруванням.
2. **Відносні рівні ризику**: Широкі стопи для DOGE/XRP (в архівах `sl_pct > 1.5%`) та вузькі для BTC (в архівах `0.5% - 1.5%`) підтверджуються волатильністю активів і мають бути перенесені в продакшн як стартові значення (що і зроблено в `regime_tpsl` min/max).
3. **Calmar Ratio / Expected PnL**: Можна використовувати для **ранжування** символів (наприклад, відключення BTC/SOL в MR стратегії, якщо їхній Calmar/PnL в архівах близький до нуля).

### Що НЕ МОЖНА переносити 1-в-1:
1. **Абсолютний PnL та частоту угод**: Поточна система Aurora має суворі `holding_period`, `reentry_cooldown_sec` (900s для SOL), та `qos.enforce`. Це означає, що кількість угод в лайві буде **значно меншою**, ніж в архівному Optuna бектесті, який не враховував цих Anti-Churn гейтів.
2. **Сигнальні ваги (Weights) для Aurora**: В архівах ваги були нормалізовані `[0, 1]`. У поточній продакшн версії (`v2 scoring`), ваги проходять Ridge-калібрування і можуть бути від'ємними (як-от `-0.089` для `depth_imbalance` у BTCUSDT), оскільки вони представляють коефіцієнти регресії, а не прості відсотки.

## Висновок
Архівні файли є чудовою історією еволюції стратегій (особливо підтвердження важливості Order Book Imbalance / Trade Flow Imbalance). Проте, поточний бойовий `aurora.yaml` значно перевершує їх за складністю управління ризиками (режимні мультиплікатори TPSL, Anti-Churn гейти, V2 Scoring, Volatility Entry). При порівнянні результатів слід спиратися на відносні параметри (які активи реагують на тренди, а які на волатильність), а не на абсолютні метрики прибутку.
