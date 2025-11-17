# Duplicate & Dead Code Analysis Round 1

## 1. Вступ
Аналіз проведено по коду Aurora/vFoundation з метою перевірки трьох гіпотез про дублювання або мертвий код; джерела — репозиторій `apps/reference`, `vfoundation`, BIOS-документація (`docs/For_GPT`, `docs/config_analysis`, `docs_arhive` і `JOURNAL`). Гіпотези — про неіснуючий каталог `confsig/`, колекцію збирачів у `bridge/` і перетин між `vfoundation/config.py` та YAML-хелперами в `vfoundation/configs/`.

## 2. Гіпотеза 1: confsig/
- **Чи існує каталог:** фізично `confsig/` в репо нема — `rg` нічого не знайшов, `Test-Path` повернув False. Документація (`docs/For_GPT/apps_structure.md`) прямо стверджує, що «There is no dedicated `confsig/` directory today» і що всю «signature» логіку тримають у `config/_schemas` та `configs/frozen`.
- **Які файли:** нема.
- **Імпорти:** ніяких `import confsig` або `from confsig` у коді нема; `rg "confsig"` повертає лише коментарні згадки.
- **Схеми/підписи:** усе, що є, лежить у `config/_schemas` (Aurora/risk/ops) і шаблони заморожених конфігів; окремого каталогу `confsig` немає.
- **Висновок:** **мертвий**/відсутній — жодного живого каталогу/файлу/імпорту, сторінки описують його як «не існує». Можна не тримати під увагою, можна видалити посилання-помилки в документах.

## 3. Гіпотеза 2: bridge/
- **Список файлів:** `bridge/bridge_feature_collection.py`, `bridge/live_feature_collector.py`.
- **Опис (класи/функції):**
  - `LiveBridgeCollector` (bridge_feature_collection.py): збирає дані bookTicker/aggTrade, обчислює `obi`, `tfi`, `delta_price`, записує результати в `logs/features.jsonl`. Використовує `BinanceWebSocketApiManager`, читає символи з env або `vfoundation.config_symbols.get_trading_symbols()`. Скрипт запускається лише через `__main__`, не імпортується іншими модулями.
  - `LiveFeatureCollector` (live_feature_collector.py): схожа логіка, стріми ticker, обчислення `obi/tfi/delta_price`, акумулює статистику та друкує summary, також викликається лише з `__main__`.
- **Де викликається/імпортується:** `rg` показує, що назви класів/файлів не з'являються за межами власних файлів (крім документації/журналів). У коді `apps/reference` чи `vfoundation` їх імпорти відсутні.
- **Чи дублюють FeatureEngineering:** Так. Обидва модуля виводять `obi`, `tfi`, `delta_price`, обчислюють їх з Binance data, аналогічно до `apps/reference/domains/feature_engineering/feature_engineering.py` (там також створюються фічі, що використовуються в режимі). `bridge/` не гарантує інтеграції з pipeline; їх результати записуються у JSONL, але не йдуть у FSM. Функціональність `FeatureEngineering` (агрегація в домені, матеріалізовані фічі) виконує схожі розрахунки і використовується напряму в `execution_position`.
- **Висновок:** **мертвий/частково активний** — скрипти існують, але жодна частина коду їх не викликає; схожі функції є в домені feature_engineering. Якщо потрібно спростити, можна перевести ці файли в інструменти експериментів або архівувати.

## 4. Гіпотеза 3: `vfoundation/config.py` vs `vfoundation/configs/`
- **Функції в `vfoundation/config.py`:** клас `Config` і множина `_get_*` утиліт (_get_int_env, _get_float_env, _get_optional_env, _get_admin_tokens, _get_execution_mode тощо) читають ENV і встановлюють параметри: RBAC токени, WAL-пути, circuit breaker, idempotency, drift monitor, execution adapter timeouts/retries/circuit breaker, redis, worker_id тощо. Внизу модуля створюється single-інстанс `config = Config()`.
- **Хто імпортує:** `rg "from vfoundation.config import config"` показує використання в `vfoundation/security/rbac_abac.py`, `vfoundation/dr/wal.py`, `vfoundation/core/retry_cb.py`, `vfoundation/core/idempotency/idempotency.py`, `apps/reference/adapters/sdk_adapter_binance.py`, `apps/reference/config_symbols.py`, `apps/reference/telemetry/order_logger.py`, `apps/reference/adapters/execution_adapter.py`, `apps/reference/domains/execution_position/drift_monitor.py`, тестах (`tests/test_ci_smoke.py`, `tests/test_final_90_percent.py` тощо). Жодного імпорту `config` з кореневого `config.py` нема (його фізично немає), і лише цей інстанс `vfoundation.config.config` використовується.
- **Порівняння з `vfoundation/configs/`:** там два YAML-файли (`adapter.yaml`, `idempotency.yaml`). Ці файли описують retry/backoff/rate limit/timeouts, і згадані в `docs/config_analysis/config_inventory.md`. Вони не експортують функції, їх читають через `vfoundation/config.py` (мапінг `Config` зчитує env, але YAML з `vfoundation/configs` використовується там для дефолтних значень або factory). Є невеликий перетин у темах (timeouts, adapter retries), але `Config` ліпить об’єкт з ENV, а YAML – просто структури (без імпортів). Неможливо прямо `import config` з YAML.
- **Висновок:** **ок / не дубль** — `vfoundation/config.py` запускає runtime-логіку (чить, `Config`), а `vfoundation/configs/` — статичні YAML-набори. Є тематичне перетин (timeout/rate-limit), але не повторення коду чи конфігів, бо використання різне. Немає кореневого `config.py` у репо, тож нічого не видаляти.

## 5. Загальний висновок
- **Що потенційно можна архівувати:** `bridge/bridge_feature_collection.py` і `bridge/live_feature_collector.py` — існують лише як утиліти, не імпортуються в pipeline, дублюють обчислення фіч з `feature_engineering`; можна перевести в `docs/arhive` або позначити як експериментальні.
- **Які файли потребують ручної перевірки:** перевірити `trading_v0.2.yaml`/`trading.staging.override.yaml` на предмет синхронності з `trading.yaml` (dup/per pipeline). Перевірити `risk`/`exposure` значення у `config/aurora/system.yaml` vs `configs/master_config_v1.yaml` та `vfoundation/configs/adapter.yaml` – документувати, звідки насправді читається.
- **Які модулі точно зайві:** `confsig/` відсутній — нічого не очищати, але можна видалити згадки. Bridge-скрипти не мають споживачів і потенційно зайві для робочого pipeline (якщо не потрібні для ad-hoc збору фіч). Config-клас в `vfoundation` запускає env-резольвери — його тримати, YAML з `vfoundation/configs` теж потрібні.
