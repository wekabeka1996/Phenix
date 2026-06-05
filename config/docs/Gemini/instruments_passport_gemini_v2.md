# 📄 Semantic Configuration Passport: `config/aurora/instruments.yaml` (Part 2)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/instruments_passport_gemini_v2.md
> - Scope: Lines 101-132 of `config/aurora/instruments.yaml`
> - Purpose: Capability mapping for additional instrument precision and execution policies.

Цей паспорт описує завершальну частину налаштувань торгових інструментів (для `BNBUSDT` та `1000PEPEUSDT`). Структура полів та їхня семантика (Capability/Sensitivity) повністю ідентичні до описаних у Part 1, тому тут задокументовані лише специфічні особливості цих активів.

---

## 5. Additional Instruments (`instruments.*`)

### `BNBUSDT`
- **Capability:** Конфігурація для торгівлі нативним токеном біржі Binance.
- **Особливості:** Успадковує логіку управління капіталом від іншої "важкої" альти (`SOLUSDT`). Має крок ціни (`tick_size`) `"0.01"` та мінімальний розмір ордера (`min_notional`) `"5"` USDT. Використовує плече `20x`.

### `1000PEPEUSDT` (Meme-Coin / AI Sandbox)
- **Capability:** Конфігурація для високоризикового мем-коїну. 
- **Причинність:** Цей актив використовується як "пісочниця" (Sandbox) для зовнішнього штучного інтелекту (згадується в `trading.yaml` у секції `llm_orchestration.allowlist_symbols`).
- **Особливості:** 
  - Екстремально дрібний крок ціни: `tick_size: "0.0000001"`. 
  - Крок кількості: `step_size: "1"`.
  - Ці параметри вимагають жорсткого математичного округлення в двигуні виконання, оскільки помилка в "нулях" (floating point error) при передачі ордера через API біржі призведе до миттєвого відхилення (`Filter failure: PRICE_FILTER`).
  - Використовує ізольовану маржу (`margin_mode: "isolated"`) з плечем `20x`, що локалізує збитки ШІ виключно в межах цього активу, захищаючи основний депозит.
  - Множник перевороту (`hysteresis_mult: 1.3`) дозволяє швидкі реверси (агресивна поведінка порівняно з BTC).
