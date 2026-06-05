# 📄 Semantic Configuration Passport: `config/aurora/strategies/llm_microstructure.yaml` (Full File)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/llm_microstructure_passport_gemini_v1.md
> - Scope: Lines 1-30 (Full File) of `config/aurora/strategies/llm_microstructure.yaml`
> - Purpose: Capability mapping for the External LLM Intent Ingress strategy.

Цей короткий паспорт описує міст між зовнішнім штучним інтелектом (LLM) та внутрішньою системою прийняття рішень (FSM).

---

## 1. Strategy Identity & Role

### `type` / `description`
- **Capability:** `external_intent` (Зовнішній Намір). Це не математична стратегія в класичному розумінні. Це "канал" (Ingress), через який зовнішня мовна модель може передавати свої торгові ідеї у FSM-ядро системи.
- **Причинність:** Дозволяє системі приймати сигнали ззовні, обробляти їх через стандартні Risk Gates (описані в `trading.yaml` та `domains.yaml`) і виконувати так само, як і власні алгоритмічні сигнали.

## 2. Timing & Execution

### `timeframe_sec` / `pending_entry_ttl_ms`
- **Capability:** Базовий "серцевий ритм" прийому команд — 60 секунд. Якщо намір від ШІ (TradeIntent) не виконано протягом 120 секунд (`120000 ms`), він автоматично відхиляється. Це захист від "застарілих" рішень ШІ (Stale Intents), коли ринок вже змінився, а модель продовжує думати про старі ціни.

### `execution`
- **`entry_order_type: LIMIT` / `entry_tif: GTC`:**
  - *Capability:* На відміну від `aurora`, яка використовує жорсткі `GTX` (Post-Only) ордери, ШІ дозволено використовувати `GTC` (Good-Till-Canceled) лімітки. Це означає, що ШІ може перетинати спред, якщо його лімітна ціна гірша за кращу ціну пропозиції.
  - *Sensitivity:* Збільшує шанси на виконання наказу від ШІ, але може призвести до плати Taker-комісії.
- **`gtx_retry_max: 0`:** Перевиставлення (Repricing) ордерів для ШІ вимкнено. Рішення приймається 1 раз.

### `safety_gates`
- **`enabled: false`:**
  - *Capability:* Системний захист від стресу на рівні *цієї стратегії-шлюзу* вимкнено.
  - *Причинність:* Відключення гейтів тут не означає, що ШІ отримує безконтрольний доступ. Це означає, що блокування ШІ під час ринкового шторму делеговано іншим рівням системи: жорстким лімітам в `trading.llm_orchestration.intent_policy` (описаним у `trading_passport`) та домену `shadow_telemetry`.

---
*Аудит конфігу `llm_microstructure.yaml` завершено.*