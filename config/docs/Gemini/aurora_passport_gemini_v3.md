# 📄 Semantic Configuration Passport: `config/aurora/strategies/aurora.yaml` (Part 3)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/aurora_passport_gemini_v3.md
> - Scope: Lines 201-300 of `config/aurora/strategies/aurora.yaml`
> - Purpose: Capability mapping for strategy scoring mechanics, Kelly criterion, and dynamic regime thresholds.

Цей паспорт описує механізми перетворення "сирого" сигналу в ймовірнісні моделі Келлі, а також динамічну адаптацію порогів (Thresholds) стратегії `aurora` під різні ринкові умови.

---

## 3. Core Decision Engine (`decision`) - Продовження

### `direction_strength_scoring`
- **Capability:** Розділяє фічі на ті, що вказують *напрямок* (Direction), і ті, що вказують на *силу* руху (Strength).
- Напрямок: `obi`, `tfi`, `delta_price`, `ema_bias`, `depth_imbalance`, `macro_resid`.
- Сила: `volume_spike`, `volatility_state`. 
- Сигнальна міць підсилюється (або гаситься) множником `strength_alpha: 0.5`. Це дозволяє стратегії агресивніше реагувати, коли об'єм торгів підтверджує ціновий рух.

### `kelly` (Сайзинг Келлі)
- **Capability:** Математичний інструмент для оптимізації розміру ставки (Bet Sizing) на основі ймовірності виграшу.
- **Sensitivity:** 
  - `p_min: 0.45` / `p_max: 0.65`: Затискає ймовірність успіху (Win Probability), розраховану моделлю, в цих межах. Це захищає від переоцінки системою власних можливостей (Overconfidence).
  - `payoff_ratio_r: 1.5`: Базове співвідношення Risk/Reward, яке очікує стратегія.
  - `kelly_cap: 0.25`: Фракційний Келлі. Стратегія ніколи не ризикне більше ніж 25% від теоретично-оптимального (по Келлі) розміру капіталу. Це класичний запобіжник від розорення (Ruin).

### `regime_thresholds` / `regime_threshold_multipliers`
- **Capability:** Динамічні пороги входу залежно від поточного ринкового режиму. Перевизначають базовий `signal_threshold`.
- **Sensitivity:** 
  - `HIGH_VOLATILITY: 0.18` (найвищий поріг). Стратегія стає надзвичайно вибагливою до сигналів під час шторму.
  - `MEAN_REVERSION: 0.075` (найнижчий поріг). Стратегія дуже чутлива у флеті, готова торгувати дрібні коливання.
  - `UNCERTAIN: 99.0` (нескінченність). Фактично блокує будь-яку торгівлю, якщо ринок непередбачуваний (Hard Fail-Closed).

### Фічі та їхня валідація
- **`neutral_threshold: 0.05`:** Якщо фінальний скор коливається в межах `[-0.05, 0.05]`, сигнал відкидається як "шум".
- **`scoring_version: quadratic`:** Використовує квадратичну (нелінійну) функцію штрафів/нагород замість простої суми.
- **`feature_neutrals`:** Точка відліку (Zero-baseline) для кожної фічі. Наприклад, для `ema_bias` або `depth_imbalance` нейтральним є `0.5`, а для `obi` — `0.0`.
- **`essential_features`:** `[obi, delta_price, macro_resid]`. 
  - *Capability:* Якщо хоча б одна з цих трьох критичних фічів відсутня (NaN), стратегія відмовляється генерувати сигнал, незалежно від стану інших 11 фічів.

### Зовнішні запобіжники (Gates & Vetos)
- **`liquidity_gate`:** `kappa_min: 0.1`. Блокує трейд, якщо оцінка ліквідності (глибина стакану) падає нижче 10% від нормальної. Захищає від проковзування на тонких ринках.
- **`anchor_shock_veto`:**
  - *Capability:* Захист від макро-шоків. Якщо еталонний актив (`anchor_symbol: BTCUSDT`) падає на понад `threshold: -2.0` (2 стандартні відхилення), накладається жорстке Вето (Veto) на всі покупки по всіх інших альткоїнах. Бот "пригинає голову", поки біткоїн падає.