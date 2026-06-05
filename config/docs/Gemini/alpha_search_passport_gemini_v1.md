# 📄 Semantic Configuration Passport: `config/alpha_search.yaml` (Part 1)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/alpha_search_passport_gemini_v1.md
> - Scope: Lines 1-100 of `config/alpha_search.yaml`
> - Purpose: Capability mapping for the Alpha Search routing and multi-provider event bridge.

Цей паспорт описує базові налаштування "генератора сигналів" (Data Plane), який створює потоки скорингу для подальшого споживання FSM або Neocortex.

---

## 1. Global Settings (`alpha_search`)

### `enabled` / `shadow_mode`
- **Capability:** Головні перемикачі домену.
- **Sensitivity:** `shadow_mode: true` (інваріант). Означає, що сигнали, які генеруються тут, лише записуються в логи (`alpha_input_v1.jsonl`), але **не** відправляються безпосередньо як накази на виконання. Це інфраструктура дослідження (Shadow), а не управління.

## 2. Event Bridge Configuration (`triggers` & `cache`)
- **Capability:** Роутинг подій. Визначає, які івенти від `FSMCore` пробуджують систему.
- **`feature_event` / `ta_feature_event`:** Слухає `EVT:FEATURES_CALCULATED` (мікроструктура) та `EVT:TA_FEATURES_CALCULATED` (макро-індикатори), кешуючи їх (`cache.max_per_symbol: 10`).
- **`decision_event`:** `CMD:PROCESS_STRATEGY`. Сигнал, що запускає фінальний скоринг і генерацію `EVT:ALPHA_SCORE_CALCULATED`.

## 3. Providers (Джерела Альфи)

### `providers.aurora`
- **Capability:** Провайдер, що генерує сигнали на основі логіки базової стратегії `aurora`.
- **`threshold`:** `0.155`. Поріг активації для генерації сигналу.
- **`adapter`:** 
  - *Capability:* Емуляція логіки `decision_making`.
  - Містить жорстко зафіксовані ваги (`signal_weights`), такі як `obi: 0.42`, `delta_price: 0.15`, які перенесені сюди для ретроспективного тестування (SSOT для `alpha_search`).
  - *Sensitivity:* Зміна ваг тут вплине лише на *тіньовий* потік сигналів, який аналізується в репортах, але не на реальну торгівлю `vfoundation` (поки Neocortex не почне ними користуватися).

### `providers.ta_ensemble`
- **Capability:** Провайдер технічного аналізу (Ансамбль з трьох моделей: `mean_reversion_v1`, `momentum_v1`, `volatility_v1`).
- **`min_tf_sec: 300`:** Пропускає швидкі 3-хвилинні бари, оскільки класичний TA потребує довших горизонтів для стабільності.
- **`ensemble`:** 
  - *Capability:* Динамічне ребалансування ваг між моделями (`rebalance_frequency_days: 7`, `performance_window_days: 30`). Моделі, які показали кращий PnL в минулому місяці, отримують вищу вагу.
