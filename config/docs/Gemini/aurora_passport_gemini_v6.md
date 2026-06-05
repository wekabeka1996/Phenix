# 📄 Semantic Configuration Passport: `config/aurora/strategies/aurora.yaml` (Part 6)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/aurora_passport_gemini_v6.md
> - Scope: Lines 501-600 of `config/aurora/strategies/aurora.yaml`
> - Purpose: Capability mapping for advanced asset-specific exit logic (SOL) and starting configuration for BTCUSDT.

Цей паспорт описує завершальну частину налаштувань для агресивного токена Solana, а також базові перевизначення для головного активу системи — Bitcoin (BTCUSDT).

---

## 6. Asset-Specific Overrides (`assets`) - Продовження

### `SOLUSDT` (Закінчення блоку)

#### `take_profit` та `trailing_stop` (Агресивний вихід)
На відміну від консервативного Ethereum, Solana налаштована на витискання тренду:
- **`take_profit`:** Рівні часткової фіксації значно ближчі до входу (`tp_low_ratio: 0.36`), і на першому рівні закривається лише `31%` позиції (`partial_exit_pct: 0.31`), залишаючи більшу частину для трейлінгу.
- **`trailing_stop.enabled: true`:** Увімкнено. Активується після `4.6%` прибутку (`activation_pct: 0.046`) і тягне стоп на відстані `1.8%` (`trail_pct: 0.018`). Це ідеально для високоволатильних активів, де ціна може дати X% за хвилину.

#### `allowed_regimes`
- **Capability:** `[TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY]`. 
- **Причинність:** Стратегії `aurora` для SOL **заборонено** торгувати в режимі `TREND_UP`. Це виглядає контрінтуїтивно, але оптимізація показала, що в цій конкретній версії моделі Шорти (TREND_DOWN) та боковики (MEAN_REVERSION) на Solana приносять стабільніший Risk/Reward, ніж спроби купувати на зростанні.

#### `holding_period`
- **`enabled: false`:** Для SOL знято обмеження на мінімальний час утримання позиції. Система може вийти з трейду миттєво, якщо сигнал розвернеться. `min_duration_sec: 1800.0` (30 хв) просто ігнорується.

---

### `BTCUSDT` (Король ринку)

Bitcoin має найскладнішу та найглибшу систему налаштувань, оскільки є базовим бенчмарком.

#### `weights` (Альфа-ваги для BTC)
- **Capability:** Математична матриця впливу фічів на фінальний сигнал.
- *Найвпливовіші:* **`volume_spike: 0.24`** та **`delta_price: 0.18`**. Як і в ETH, імпульс об'єму превалює. 
- *Negative Weights:* `ema_bias: -0.11` та `depth_imbalance: -0.08`. Вказують на реверсійну (Mean Reverting) складову в сигналі BTC.

#### `leverage`
- **Capability:** Плече.
- **Sensitivity:** `target: 35`. Це **найвище плече в системі** (інші альткоїни мають 20x). BTC вважається найменш волатильним і найстабільнішим активом, тому система витискає з нього максимальну капітальну ефективність (Capital Efficiency). Використовує виключно `ISOLATED` маржу.

#### `regime_thresholds` / `regime_sizing` (Режимний менеджмент)
- **Capability:** Асиметричні пороги входу.
- **Sensitivity:** 
  - `HIGH_VOLATILITY: 0.35` (низький поріг). Бот охоче торгує BTC під час шторму, але ріже сайзинг до `0.7` (`regime_sizing`).
  - `TREND_DOWN: 2.28` (екстремально високий поріг). Бот майже ніколи не шортить біткоїн, хіба що сигнал ідеальний.
  - `TREND_UP: 1.3` (збільшений сайзинг). Бот перевантажує портфель лонгами (130% від норми) на зростаючому ринку.

#### `exit.regime_tpsl` (Динамічні стопи)
- **Capability:** Стоп-лос (базовий `0.5%`) розширюється залежно від режиму.
- **Sensitivity:** У шторм (`HIGH_VOLATILITY`) стоп множиться на `1.65` (стає 0.825%), у флеті (`LOW_VOLATILITY`) — на `1.27`. Під час чистого тренду множник `1.0` (суворий короткий стоп).