# 📄 Semantic Configuration Passport: `config/aurora/domains.yaml` (Part 2)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/domains_passport_gemini_v2.md
> - Scope: Lines 151-300 of `config/aurora/domains.yaml`
> - Purpose: Baseline passport extraction for domain-specific logic configurations.

Цей паспорт описує логіку та налаштування на рівні окремих доменів системи: закінчення `feature_engineering` та домен `ta_features`.

---

## 3. Feature Engineering Domain (`feature_engineering`) - Продовження

### `macro_sync`
- **Role:** Синхронізація "еталонних" активів (`anchors`: `BTCUSDT`, `ETHUSDT`) з поточним активом для виявлення розбіжностей у часі (`time_diff_threshold_ms: 60000`) та загального макро-тренду.
- Вирівнювання (Alignment) відбувається за принципом `align_mode: tail_min_len`.

### `readiness_registry` та `warmup`
- **`declared_keys`:** Повний перелік фічів, які домен зобов'язаний розрахувати (наприклад: `obi`, `tfi`, `delta_price`, `macro_resid` тощо).
- **`warmup.enforcement_mode`:** `fail_fast`. Якщо хоча б одна фіча з реєстру не готова (`check_full_ready_invariant: true`), домен сигналізує про неготовність усієї системи. Дозволені винятки вказані у `degraded_allowed_strategies`.

### `feature_sanity`
- **Role:** Жорсткі математичні межі для кожної фічі (Hard Bounds). Захищає від переповнення або екстремальних значень, які можуть зламати AI-моделі чи лінійні ваги стратегій.
- **`nan_inf_behavior`:** `neutral_and_not_ready`. У разі появи `NaN` або `Infinity`, фіча отримує нейтральне значення, а система переводиться у стан неготовності.
- Межі зафіксовані для `obi` [-1, 1], `tfi` [-1, 1], `macro_resid` [-3, 3], `volume_spike` [0, 10] тощо.

### `macro_resid` та `absorption`
- Оверлеї розрахунку макро-резидуалів (залишкових відхилень) та абсорбції об'ємів стакану.
- Визначають `beta_window: 60`, `winsor_percentile: 0.05` для зрізання викидів.
- Абсорбція розраховується з вікном `30`, дедуплікацією подій та жорстким кліпінгом `1.0`.

### `pillars` (Когнітивні опори сигналів)
- Трирівнева архітектура часових горизонтів (Hierarchical Timeframes):
  1. **`tactician`:** Короткостроковий (900 сек / 15 хв). `roc_period: 14`, `sensitivity: 8.0`.
  2. **`operator`:** Середньостроковий (14400 сек / 4 год). `linreg_period: 20`.
  3. **`strategist`:** Довгостроковий (86400 сек / 1 день). `sma_period: 200`.
- **`weights`:** Ваги цих рівнів при формуванні загального сигналу (Tactician: 0.65, Operator: 0.3, Strategist: 0.05). Це означає, що система має сильний short-term bias.
- **`backfill`:** Автоматичне завантаження історичних свічок при старті для миттєвого заповнення SMA/EMA (до 200 денних свічок).

---

## 4. TA Features Domain (`ta_features`)

Домен традиційного технічного аналізу (Technical Analysis), що працює на базі стандартних барів (OHLCV).

- **`timeframes_sec`:** `[180, 300, 900]`. Аналогічно до Feature Engineering, але фокус на класичних індикаторах.
- **`warm_up_bars`:** `int` (30). Кількість свічок, необхідна для прогріву індикаторів (наприклад, MACD, RSI) перед тим, як домен почне видавати валідні сигнали.
- **`buffer_max_bars`:** `int` (300). Розмір вікна зберігання історії в оперативній пам'яті для розрахунків.