# 📄 Semantic Configuration Passport: `config/aurora/domains.yaml` (Part 3)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/domains_passport_gemini_v3.md
> - Scope: Lines 301-615 of `config/aurora/domains.yaml`
> - Purpose: Baseline passport extraction for domain-specific logic configurations.

Цей паспорт описує логіку та налаштування доменів: `risk_management`, `position_tracking`, `execution_position`, `shadow_telemetry` та `objective_engine`.

---

## 5. Risk Management Domain (`risk_management`)

Агрегований ризик-скоринг системи.

### `risk_score_weights`
- **Role:** Ваги компонентів для формування фінального `Risk Score`.
- `delta_price_pct`: 0.1, `obi`: 0.3, `tfi`: 0.3, `absorption_inverse`: 0.3, `absorption_feature`: 0.2.
- **`validation`:** Загальна сума ваг повинна знаходитися в межах від 0.5 до 2.0.

### `trading_allowed_thresholds`
- **`max_risk_score`:** `float` (0.96). Абсолютний ліміт ризику. Якщо скор вище 0.96 — система відхиляє всі нові трейди.

### `absorption_penalty`
- **Role:** Оверлей покарання за поглинання (absorption) у стакані (`use_absorption_penalty: true`).

---

## 6. Position Tracking Domain (`position_tracking`)

- **`precision`:** Математична точність портфелю (`decimal_places: 2`, `quantity_min_threshold: 1.0e-09`, `flat_position_threshold: 1.0e-12`). Допомагає уникнути багів з "пилом" (dust) на балансі.
- **`positions_stale_ttl_sec`:** `int` (15). Якщо оновлення позиції від біржі не надходило довше ніж 15 секунд, портфель вважається застарілим (stale).

---

## 7. Execution Position Domain (`execution_position`)

Величезний домен, який керує станом ордерів, взаємодіє з біржею та захищає виконання.

### `fallback` та `exposure_guard`
- **`fallback.policy`:** `fail_closed`. У разі невідомої помилки — нічого не робити, зупинити відкриття.
- **`exposure_guard`:** Жорсткі ліміти капіталу (`max_equity_utilization_pct: 150.0`, `max_directional_ratio: 20.0`, `max_concentration_pct: 500.0`).
- **`pending_ttl_sec`:** `int` (90). Час життя наміру на відкриття до таймауту.

### `inflight_reconcile` та `event_dedup`
- **`inflight_reconcile`:** Монітор "завислих" ордерів між станом відправки на біржу та отриманням ACK (`reconcile_interval_sec: 10`).
- **`event_dedup`:** Дедуплікація біржових подій (захист від подвійних заповнень). Розмір кешу `100000`, зберігає стан на диску у `execution_terminal_identity_cache_v1.json` (`warm_state.enabled: true`).

### `pending_entry_ttl` та `advanced_stale_cancel`
- **Role:** Інтелектуальне скасування ордерів, які ще не виконані (Pending Limit Orders).
- **`cancel_on_regime_change`:** `true`. Якщо ринковий режим змінився (наприклад, з `TREND_UP` на `FLAT`), ордер скасовується.
- **`supersede_reprice_guard`:** `true`. Дозволяє системі перевиставити ордер (reprice) за кращою ціною, якщо ціна покращилася мінімум на `5 bps` та `0.1 ATR`.
- **`advanced_stale_cancel`:** Скасовує старі ордери (понад 300 сек), якщо ціна відхилилася (drift away) більше ніж на `0.5 ATR`. Жорстко прописано, що `BUY` ордери скасовуються при `TREND_DOWN`, але ніколи не скасовуються при `UNCERTAIN` чи `MEAN_REVERSION`.

### `guardian`, `restore_artifact` та `startup_truth_artifact`
- **`guardian`:** Періодичний прибиральник (GC). `unified: true`, `emit_tidy_event: true`. 
- **`restore_artifact`:** Стан екзекуції зберігається у `execution_position_restore_envelope_v1.json` (`mode: authoritative`) кожні 30 секунд. Це основа Crash Recovery системи.
- **`startup_truth_artifact`:** Запис початкового стану у `writer_only` режимі при старті.

### 7.1. `position_policy_sidecar` (AI-Augmented Position Management)
"Сайдкар" (Sidecar) — це механізм, який може рекомендувати дострокове закриття позицій на основі мікроструктурного тиску.
- **`freshness` та `startup_grace`:** Сайдкар вимагає свіжих даних (не старіших за 15-30 сек) і має період "прогріву" після старту (`30000 ms`), протягом якого він не приймає рішень.
- **`profitability_guard`:** `min_unrealized_pnl_pct: 0.25`. Запобіжник, який забороняє сайдкару закривати прибуткові позиції завчасно.
- **`scoring`:** Оцінює позицію за критеріями: `microstructure_adverse_pressure`, `regime_exhaustion_hint`, `conviction_decay`.
- **`thresholds`:** Хард-ліміти. Рекомендує закриття, якщо скор перевищує `recommend_soft_close_at: 0.3`. Явно задає ворожі режими: `adverse_regimes_long: [TREND_DOWN]`.
- **`allowed_actions`:** Строгі межі впливу. Сайдкару дозволено лише `soft_close_symbol_current_net_only` (закрити поточну чисту позицію). Йому ЗАБОРОНЕНО мутувати брекети (`bracket_mutation: false`) або робити часткові скорочення. Це класичний приклад **Bounded Control**.
- **`logging`:** Активує запис у `logs/trade_lifecycle.jsonl` (це ті самі логи, які ми використовуємо для Offline RL та Оракула!).

---

## 8. Shadow Telemetry Domain (`shadow_telemetry`)
Інфраструктура для комунікації з LLM / ШІ (Neocortex) без блокування основного рантайму (Data Plane & Control Plane).
- **`ingest` (Читання):** Використовує IPC Tap (`tcp://127.0.0.1:7101`) для асинхронного "прослуховування" суворого переліку подій (від `EVT:FEATURES_CALCULATED` до `EVT:TRADE_EXECUTED`). Черга на `50000` подій із політикою `fail_closed`.
- **`api` (Запис від ШІ):** Запускає REST API (`port: 8443`) для прийому намірів від LLM.
  - Має жорсткий **Allowlist** символів (`1000PEPEUSDT`), щоб ШІ не втручався в основні активи.
  - Rate-limit: `30` запитів на хвилину.
  - Idempotency TTL: `300` секунд (захист від подвійних/відкладених команд).
- **`egress_to_main`:** Канал зворотного зв'язку в основну шину (`tcp://127.0.0.1:7102`).
- **`snapshot`:** Автоматично генерує зліпки стану (Snapshots) при події `EVT:FEATURES_CALCULATED` і складає їх у `data/shadow_telemetry/snapshots` (Це і є Observation Space $O_t$ для агента).

---

## 9. Objective Engine Domain (`objective_engine`)
Двигун формалізованої багатокомпонентної винагороди (Dense Multi-Objective Reward Function).
Оцінює дії (як системи, так і ШІ) за шістьма незалежними компонентами:
1. **`cost`:** Штрафи за комісії (`alpha_fee`) та проковзування (`alpha_slippage`).
2. **`risk`:** Оцінка портфельного ризику (`phi_inventory`) та волатильності (`phi_volatility`).
3. **`edge`:** Оцінка співвідношення Risk/Reward (`omega_rr`) та відстані до стопа (`phi_stop_distance`).
4. **`execution`:** Оцінка впливу ліквідності (`omega_liquidity`) та спреду (`phi_spread_drag`).
5. **`information`:** Штрафи за старі дані (`phi_staleness`) та впевненість у режимі (`omega_regime_confidence`).
6. **`behavior`:** Штрафи за системний стрес: блокування інтентів (`phi_blocked_intents: 0.08`), часті скасування (`phi_cancel_replace`), повторні входи (`phi_reentry`).

*Цей двигун є математичною основою для вирішення проблеми Reward Hacking (Крок 1.3 в R&D Альманасі).*
