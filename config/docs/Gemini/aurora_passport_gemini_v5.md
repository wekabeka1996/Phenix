# 📄 Semantic Configuration Passport: `config/aurora/strategies/aurora.yaml` (Part 5)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/aurora_passport_gemini_v5.md
> - Scope: Lines 401-500 of `config/aurora/strategies/aurora.yaml`
> - Purpose: Capability mapping for advanced asset-specific exit logic (ETH) and starting configuration for SOLUSDT.

Цей паспорт описує тонке налаштування виходу з позицій для Ethereum, а також специфічну агресивну логіку для Solana (SOLUSDT).

---

## 6. Asset-Specific Overrides (`assets`) - Продовження

### `ETHUSDT` (Закінчення блоку)

#### `regime_tpsl` (Динамічні ліміти)
- **Capability:** Математичні обмеження для динамічних стопів.
- **Sensitivity:** 
  - `min_sl_pct: 0.003` (0.3%) / `max_sl_pct: 0.06` (6%). Запобігає надмірному звуженню або розширенню стопу незалежно від того, що каже режим.
  - `min_tp_rr: 0.5` / `max_tp_rr: 5.0`. Жорсткі рамки для співвідношення Risk/Reward. Стратегія не має права ставити профіт ближче ніж 0.5R, щоб не спалювати капітал на комісіях.

#### `take_profit` / `trailing_stop`
- **Capability:** Багаторівневий фіксатор прибутку.
- `tp_low_ratio: 1.0` / `tp_high_ratio: 1.65`. Система розраховує два рівні TP. 
- `partial_exit_pct: 0.5` — на першому рівні закривається 50% позиції.
- `trailing_stop.enabled: false`. Трейлінг вимкнено для ETHUSDT на користь фіксованих рівнів.

#### `allowed_regimes`
- **Capability:** `[TREND_UP]`. Це критичний інваріант для ETH. Згідно з оптимізацією, Ethereum наразі дозволено торгувати виключно в режимі зростаючого тренду. Всі інші режими (`MEAN_REVERSION`, `FLAT` тощо) — заблоковані.

#### `holding_period` (Override)
- **`min_duration_sec: 20.0`:** Для ETH мінімальний час утримання позиції значно коротший (20 секунд проти глобальних 900 секунд). Це дозволяє стратегії діяти майже як HFT (скальпінг) у тренді.
- **`emergency_exit_threshold: 0.7`:** Менш толерантний до розворотів. Екстрений вихід спрацьовує раніше.

---

### `SOLUSDT` (Специфічна логіка активу)

Для Solana налаштований зовсім інший профіль, ніж для BTC або ETH. Вона розглядається як актив з високою власною волатильністю (High-Beta).

#### `weights` (Альфа-ваги для SOL)
- Найбільший вплив має **`delta_price: 0.29`** (найвищий серед усіх активів) та **`tfi: 0.26`** (Trade Flow Imbalance). Для SOL імпульс ціни та агресивні маркет-ордери відіграють вирішальну роль.

#### `side_bias`
- **`penalty_factor: 0.0`:** Для SOLUSDT **вимкнено** штраф за однонаправлену торгівлю. Це означає, що стратегії дозволено "спамити" входами в одну сторону (наприклад, тільки LONG), якщо тренд сильний.

#### `regime_thresholds` / `regime_sizing`
- **Capability:** На відміну від ETH (якому дозволено лише `TREND_UP`), SOL налаштована на торгівлю у волатильних та флетових режимах:
  - Дозволені: `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `MEAN_REVERSION`.
  - Заблоковані (`99.0`): `UNCERTAIN` та `DEFAULT` (всі інші).
- **`regime_sizing`:** Розмір позиції варіюється: у `HIGH_VOLATILITY` він зрізається до `0.7`, а в `MEAN_REVERSION` торгує на повний об'єм (`1.0`).

#### `exit.regime_tpsl` (Мікро-менеджмент стопів для SOL)
- **Capability:** Масивна матриця мультиплікаторів для кожного існуючого режиму.
- **Sensitivity:** 
  - `MEAN_REVERSION`: `sl_mult: 1.35` / `tp_mult: 0.97`. У флеті стоп-лос сильно розширюється (щоб не вибило випадковим "шпилем"), а тейк-профіт звужується (швидка фіксація прибутку).
  - `TREND_UP`: `sl_mult: 1.15` / `tp_mult: 1.3`. У тренді стопи звичайні, а профіти тягнуться вище.
  - Ця матриця є результатом глибокої Data Science оптимізації мікроструктури саме для токена SOL.