# 📄 Semantic Configuration Passport: `config/aurora/observability.yaml` (Full File)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/observability_passport_gemini_v1.md
> - Scope: Lines 1-109 (Full File) of `config/aurora/observability.yaml`
> - Purpose: Capability mapping for system logging, alerting, and shadow telemetry (WAL).

Цей паспорт описує підсистему спостережуваності (Observability). Він керує тим, як система звітує про свій стан, як реагує на аномалії (Alerts), та які саме події записуються у фундаментальний журнал `shadow_journal` (який використовується для Crash Recovery та Offline RL).

---

## 1. Logging Routing (`logging`)

Цей блок налаштовує децентралізоване логування. Замість одного монолітного файлу, система розбиває логи по доменах, щоб уникнути "пляшкового горлечка" I/O операцій та полегшити дебаг.

- **`logging.core`:** 
  - *Capability:* Записує події низькорівневої шини (`FSMCore` / `FSMv2`) у `logs/aurora_core.log`.
  - *Sensitivity:* Встановлено на рівень `DEBUG`. Може генерувати гігабайти даних при високій активності. Ротація файлів (`max_bytes: 10485760`, `backup_count: 50`) запобігає переповненню диска.
- **`logging.domains.*`:** 
  - *Capability:* Кожен домен (`feature_engineering`, `execution_position` тощо) має свій власний ізольований логгер із власними лімітами ротації. Це дозволяє, наприклад, вимкнути (`enabled: false`) детальні логи генерації фічів, залишивши увімкненими логи екзекуції.
- **`logging.event_chain`:** 
  - *Capability:* Спеціалізований логгер, що пише у форматі `json` у файл `logs/event_chain.log`. Його мета — машиночитний запис ланцюгів причинності (Causality Chains), що ідеально підходить для парсингу скриптами аналітики (напр., `multi_tailer.py`).

---

## 2. Alerts & Entropy Monitor (`alerts`)

Блок визначає пороги, при перетині яких система генерує тривожні сповіщення (Alerts).

- **`slack_webhook_url`:** Точка інтеграції для зовнішніх сповіщень. Наразі `null` (вимкнено).
- **`deduplication_window_sec`:** `int` (300).
  - *Capability:* Захист від спаму алертами. Якщо та сама помилка стається 100 разів за 5 хвилин, система надішле лише одне сповіщення.
- **`max_alerts_per_hour`:** `int` (10). Жорсткий глобальний ліміт.
- **`risk_gate_threshold_pct`:** `int` (80). 
  - *Sensitivity:* Якщо ризик-скор системи сягає 80% (наближаючись до хард-ліміту 0.96 з `domains.yaml`), генерується превентивний алерт.
- **`wal_size_threshold_mb`:** `int` (500). Попередження про те, що невідротований журнал WAL став занадто великим (що може сповільнити Crash Recovery).
- **`cb_active_threshold_sec`:** `int` (60). Якщо Circuit Breaker (запобіжник) зупинив систему і вона не може відновитися довше 60 секунд, це вважається інцидентом (Incident).
- **`entropy_volume_threshold` / `entropy_error_rate_threshold`:** 
  - *Capability:* Налаштування для компонента `EntropyMonitor` (який керує `MetaFSMv2`). Якщо частота подій або рівень помилок перевищує ці пороги, система може автоматично перейти у режим `DEGRADED`.

---

## 3. Shadow Journal / WAL (`shadow_journal`)

Найважливіший конфіг цього файлу. Визначає Write-Ahead Log (WAL) для відновлення стану системи (Crash Recovery) та побудови наборів даних для навчання ШІ (RL Replay Buffers).

- **`path`:** `logs/shadow_critical_event_journal_v1.jsonl`.
- **`schema_version` / `instrumentation_version`:** Версіонування схеми для зворотної сумісності парсерів.
- **`critical_events`:** `list[string]`. 
  - *Capability:* **Суворий Allowlist (білий список)** подій. Тільки події з цього списку мають право бути записаними на диск у `shadow_journal`.
  - *Причинність:* Внесення події до цього списку гарантує, що вона буде доступна для відновлення після крашу. Якщо події тут немає, вона існує лише в оперативній пам'яті (Transient State).
  - *Склад списку:*
    - **Intents & Decisions:** `EVT:TRADE_INTENT_PROPOSED`, `EVT:DECISION_BLOCKED`.
    - **Execution (Order Lifecycle):** `CMD:OPEN`, `EVT:ORDER_ACK`, `EVT:TRADE_EXECUTED`, `CMD:CLOSE`.
    - **State Updates:** `EVT:PORTFOLIO_STATE_UPDATED`, `EVT:REGIME_DETECTED`.
    - **Crash Recovery Markers (RESTORE / ORDER_INDEX):** `RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD`, `ORDER_INDEX:UPSERT_OPEN`. Це маркери, які дозволяють системі реконструювати стан індексів ордерів після падіння.
    - **Hardening & AI Telemetry:** `HARDENING:TRADE_EXECUTED_MISMATCH`, `SHADOW:POSITION_POLICY_SIDECAR_EVALUATED`. Логує конфлікти стейтів та дії нашого ШІ-сайдкару.
  - *Sensitivity:* 🔽 Якщо прибрати ключову подію з цього списку (наприклад `EVT:ORDER_PLACED`), функція відновлення `restore_artifact` втратить частину контексту, що може призвести до дублювання ордерів при рестарті. 🔼 Додавання надто частих подій (як `EVT:MARK_PRICE_UPDATED`) призведе до розростання журналу на десятки гігабайт за день (I/O Bottleneck).