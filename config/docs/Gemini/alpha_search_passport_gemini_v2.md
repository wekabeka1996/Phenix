# 📄 Semantic Configuration Passport: `config/alpha_search.yaml` (Part 2)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/alpha_search_passport_gemini_v2.md
> - Scope: Lines 101-200 of `config/alpha_search.yaml`
> - Purpose: Capability mapping for Virtual Trader simulation and Objective Feedback loops.

Цей паспорт описує вбудовану систему внутрішньої оцінки сигналів (`Virtual Trader`), яка дозволяє оцінити якість "Альфи" без підключення до реального виконання.

---

## 4. Additional Providers (Judge Experts)

### `providers.judge_sw` / `providers.judge_fn`
- **Capability:** Експериментальні провайдери на основі експертних систем (`expert_type: signal_weights` та `feature_neutrals`).
- **Sensitivity:** Увімкнені (`enabled: true`), але працюють у fail-closed режимі з порогом `0.162` (ідентично до базової `aurora`).

## 5. Virtual Trader (`virtual_trader`)

Вбудований симулятор виконання (Shadow Book).

### `per_provider` / `notional_size`
- **Capability:** `per_provider: true`. Створює окрему незалежную книгу ордерів для кожного провайдера (aurora, ta_ensemble), щоб ізольовано оцінювати їхній PnL. Розмір тіньової позиції `5000` USD.
- **`flip_on_reversal`:** `false`. Забороняє миттєве перевертання позиції; трейд повинен закритися по стопу або тайм-ауту.

### `exit` (Правила виходу для симулятора)
- **`max_bars: 12`:** Жорсткий ліміт на утримання тіньової позиції (напр. 1 година при 5хв барі).
- **`max_drawdown_exit: 1.2`:** Аналог аварійного стопу.
- **`cooldown_bars_after_close: 3`:** (Захист від пінг-понгу). Блокує повторний вхід на 3 бари після закриття позиції, оскільки аналіз показав, що 91% миттєвих перезаходів приносять збиток (Reversal-exit rate).

## 6. Objective Feedback (`objective_feedback`)

Контур зворотного зв'язку для адаптивного перезважування провайдерів.

### `quality_metric_weights`
- **Capability:** Математична формула, за якою `virtual_trader` оцінює "якість" провайдера.
- **Sensitivity:** Оцінка залежить від:
  - `realized_quality_score` (0.40): Якість самого входу (наскільки ціна пішла в наш бік).
  - `realized_pnl` (0.35): Голий прибуток.
  - `duration_efficiency` (0.25): Ефективність часу (трейд, що приніс $10 за хвилину, оцінюється вище, ніж трейд, що приніс $10 за добу).
- **`min_provider_weight` / `max_provider_weight`:** [0.15, 0.70]. Межі перерозподілу довіри. Жоден провайдер не може бути повністю вимкнений (0.0) або отримати монополію (1.0).
