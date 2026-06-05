# 📄 Semantic Configuration Passport: `config/aurora/strategies/mean_reversion.yaml` (Part 2)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/mean_reversion_passport_gemini_v2.md
> - Scope: Lines 151-300 of `config/aurora/strategies/mean_reversion.yaml`
> - Purpose: Capability mapping for asset overrides and advanced microstructure/directional vetos.

Цей паспорт описує закінчення конфігурації контртрендової стратегії (перевизначення для активів та специфічні мікроструктурні гейти).

---

## 5. Asset-Specific Overrides (`assets`) - Продовження

### `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`
- **Capability:** Вимкнено (`enabled: false`).
- **Причинність:** Згідно з поточним планом (`strategies.yaml`), стратегія Mean Reversion наразі повністю вимкнена для цих активів на користь базової `aurora` або `md_amr`. Присутні конфіги (наприклад, `bb_window: 40` для BTC) є архівними оптимізаційними профілями і не впливають на поточний рантайм.

---

## 6. Advanced Vetos & Biases (Захисні механізми)

Ці блоки дозволяють накладати додаткові обмеження на класичну логіку Боллінджера, використовуючи мікроструктурні дані стакану (Order Book). Наразі більшість із них вимкнено (`enabled: false`), але їхні можливості закладені в архітектуру.

### `microstructure_veto`
- **Capability:** Вето на вхід на основі тиску в стакані.
- **Sensitivity:** 
  - `tfi_adverse_threshold: 0.3` / `obi_adverse_threshold: 0.3`: Блокує вхід проти тренду, якщо TFI (Trade Flow Imbalance) або OBI (Order Book Imbalance) показує сильний тиск *проти* очікуваного відскоку. (Тобто, не ловимо падаючий ніж, якщо стакан продовжують заливати агресивними продажами).
  - `absorption_wick_ratio_min: 0.4`: Вимагає підтвердження "тінню" свічки (Wick), що лімітні гравці поглинули удар (Absorption).

### `directional_bias`
- **Capability:** Асиметричне зсунення порогів входу на основі ставки фінансування (Funding Rate).
- **Sensitivity:** `funding_shift_magnitude: 0.02`. Знижує поріг входу (спрощує трейд) у сторону, яка отримує фінансування (роблячи стратегію Funding-Rate positive), і завищує поріг для трейдів, які повинні платити фінансування.

---

## 7. Regime-Based Sizing (`regime_sizing`)

Адаптація розміру позиції та стопів залежно від "якості" флету (Боковика).

- **`FLAT_LOW` (Низька волатильність):** 
  - `sizing_mult: 0.8`. Розмір позиції зменшено (ринок надто мертвий, рухи малі).
- **`FLAT_NORMAL` (Ідеальний боковик):** 
  - `sizing_mult: 1.0`. Базовий розмір позиції.
- **`FLAT_HIGH` (Широкий/волатильний боковик):** 
  - `sizing_mult: 0.7`. Розмір позиції зменшено для захисту капіталу.
  - `stop_mult: 1.5`. Стоп-лос розширено на 50%, щоб запобігти вибиванню випадковим шумом у широкому каналі.
  - `target_mult: 1.2`. Тейк-профіт розширено, оскільки волатильність дозволяє забрати більший рух.

---
*Аудит конфігу `mean_reversion.yaml` завершено.*