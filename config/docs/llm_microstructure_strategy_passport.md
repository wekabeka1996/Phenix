# Semantic Configuration Passport: `config/aurora/strategies/llm_microstructure.yaml`

Цей документ описує конфігурацію стратегії **LLM Microstructure** (тип `external_intent`).
**Статус:** Production / SSOT
**Owner:** `decision_making` / `shadow_telemetry`

---

## 1. Основні параметри
- `llm_microstructure.enabled` (bool): Master toggle для стратегії.
- `llm_microstructure.type` (str): Тип стратегії (`external_intent`). Вказує на те, що сигнали формуються зовнішнім агентом, а не внутрішнім математичним рушієм.
- `llm_microstructure.description` (str): Опис призначення стратегії (contract-first ingress, fail-closed gates).
- `llm_microstructure.timeframe_sec` (int): Базовий таймфрейм для виконання (напр. 60 секунд).

## 2. Налаштування виконання (`execution`)
Ці параметри визначають, як саме ордери від LLM будуть виконуватися на ринку.
- `entry_order_type` (str): Тип ордера на вхід (напр. `LIMIT`).
- `entry_tif` (str): Time-in-Force (напр. `GTC`).
- `exit_order_type` (str): Тип ордера на вихід (`MARKET`).
- `exit_tif` (str/null): TIF для виходу.
- `gtx_retry_max` (int): Максимальна кількість спроб для GTX. Для LLM intent встановлено `0` (без повторів).
- `gtx_retry_offset_bps` (float): Зсув ціни в bps при повторній спробі.
- `gtx_fallback_to_market` (bool): Чи дозволено fall back до маркету, якщо лімітний ордер не виконується (для LLM встановлено `false`, що означає жорстке скасування (fail-closed) у разі невдачі).

## 3. Гейти та безпека
- `safety_gates.enabled` (bool): Увімкнення базових гейтів безпеки. У цій стратегії гейти відіграють ключову роль, оскільки вхідні сигнали формуються зовнішнім LLM агентом, і система повинна строго валідувати (fail-closed) їх перед виконанням через Risk Management та Objective Engine.
