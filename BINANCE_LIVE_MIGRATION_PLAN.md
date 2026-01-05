# План миграции Aurora/Phenix: Hybrid (live data + testnet exec) → Full Live (real market)

## 0) Контекст и цель

**Текущая ситуация (подтверждено конфигом):**
- Market data: `live`
- Execution/positions и источник portfolio state: `testnet`
- Глобальный режим системы: `hybrid_live_data_testnet_exec`

**Цель миграции:**
- Перевести **execution_position** и **risk_management.portfolio_state** на `live`.
- Устранить конфиг-расхождения (URL’ы testnet vs официальная документация).
- Сделать переход контролируемым (preflight → canary → full), с явным rollback.

**Важно:** прямо сейчас у вас есть риск логических рассинхронов: стратегия может принимать решения по live-рынку, но портфель/ордера/позиции и риск-ядро опираются на testnet-состояние.

## 1) Что является источником правды

### 1.1 Конфиг Binance API
Источник: `config/aurora/trading.yaml`.
- Live env:
  - `BINANCE_FUTURES_API_KEY_LIVE`
  - `BINANCE_FUTURES_API_SECRET_LIVE`
  - `BINANCE_FUTURES_BASE_URL_LIVE`
- Testnet env:
  - `BINANCE_TESTNET_API_KEY`
  - `BINANCE_TESTNET_API_SECRET`

**Наблюдение:** `README.md` описывает `BINANCE_MAINNET_API_KEY/BINANCE_MAINNET_API_SECRET`, но фактический конфиг использует **другие имена переменных** (см. выше). Это критичный источник ошибок при ручной настройке.

### 1.2 Режимы доменов
Источник: `config/aurora/trading.yaml` → `trading.domain_configuration` и `trading.risk_management.data_sources`.

### 1.3 Глобальный режим
Источник: `config/aurora/system.yaml` → `trading_mode`.

## 2) Официальные базовые URL (Binance Developers)

Ниже — то, что подтверждено актуальной документацией Binance Developers (USDⓈ-M Futures):

### 2.1 Futures (USDⓈ-M) — production
- REST base: `https://fapi.binance.com`
- User Data Stream WS base: `wss://fstream.binance.com`
- User Data Stream path: `/ws/<listenKey>`

### 2.2 Futures (USDⓈ-M) — testnet (важно)
Документация указывает:
- REST testnet base: `https://demo-fapi.binance.com`
- WS testnet base: `wss://fstream.binancefuture.com`

**Расхождение с текущим конфигом:**
- Сейчас в `trading.yaml`:
  - `rest_url: https://testnet.binancefuture.com`
  - `ws_url: wss://stream.testnet.binancefuture.com`

Рекомендация: считать документацию источником правды и **перед любым переключением** выровнять testnet URL’ы (чтобы staging окружение оставалось корректным).

### 2.3 User Data Streams (listenKey) — ключевые правила
- `listenKey` валиден 60 минут после создания.
- `PUT` по `listenKey` продлевает валидность ещё на 60 минут.
- `DELETE` закрывает поток и инвалидирует ключ.
- Один WS-коннект валиден 24 часа (ожидайте дисконнект на отметке 24h).

## 3) Предмиграционные решения (обязательные)

### 3.1 Spot vs Futures несогласованность
В кодовой базе присутствует Spot-вызов `myTrades` (через `python-binance`) в домене account observer, при том что execution у вас — Futures.

Перед full-live нужно выбрать одно:
- Вариант А (самый простой/безопасный): **отключить account_observer** (fail-closed/disabled) на время миграции, если он не критичен.
- Вариант B: переработать account observer на Futures-эквиваленты (если он нужен именно для Futures-портфеля).

Если этого не сделать, вы рискуете смешать spot-trades и futures-positions в одном “портфельном” представлении.

### 3.2 Политика ключей
Для live-ключей:
- Включить минимум необходимого (Read + Trade, без Withdrawals).
- Включить IP allowlist (если инфраструктура статична).
- Убедиться, что Futures account активирован.

## 4) План изменений конфигов (минимальный)

### 4.1 Сделать full-live доменную карту
Файл: `config/aurora/trading.yaml`

Изменить:
- `trading.domain_configuration.risk_management.trading_mode: live`
- `trading.domain_configuration.execution_position.trading_mode: live`
- `trading.risk_management.data_sources.portfolio_state: live`

Оставить `market_data` как `live` (у вас уже так).

### 4.2 Глобальный режим
Файл: `config/aurora/system.yaml`

Изменить:
- `trading_mode: "live"`

(Судя по комментарию в файле, это валидный вариант.)

### 4.3 Уточнить/выровнять Futures base URL в live
Файл: `config/aurora/trading.yaml`

Рекомендуемое значение:
- `BINANCE_FUTURES_BASE_URL_LIVE=https://fapi.binance.com`

### 4.4 Выровнять testnet URL’ы с документацией (чтобы testnet оставался рабочим)
Файл: `config/aurora/trading.yaml`

Рекомендуемые значения:
- `binance_api.testnet.rest_url: https://demo-fapi.binance.com`
- `binance_api.testnet.ws_url: wss://fstream.binancefuture.com`

Примечание: сделайте это отдельно от переключения в live (как “staging hardening”), чтобы не смешивать причины отказов.

## 5) Preflight-проверки (до первого live-ордера)

### 5.1 Конфиг/секреты
- Все live env vars присутствуют и не пустые:
  - `BINANCE_FUTURES_API_KEY_LIVE`
  - `BINANCE_FUTURES_API_SECRET_LIVE`
  - `BINANCE_FUTURES_BASE_URL_LIVE`

### 5.2 Time sync / recvWindow
- Любые ошибки `-1021` (“timestamp out of window”) должны быть устранены до live.
- В логике клиента должен быть корректный timestamp (и желательно контроль drift через serverTime).

### 5.3 ListenKey keepalive
- Убедиться, что есть периодический `PUT` keepalive (например, раз в 30 минут) и авто-recreate listenKey при `-1125`.

### 5.4 Лимиты и backoff
- При `429` обязательно backoff.
- При `418` — понимать, что это autoban.
- На `503 Unknown error` — трактовать статус исполнения как UNKNOWN (проверять через WS/опрос orderId, чтобы не наделать дублей).

## 6) Rollout (канареечный запуск)

Рекомендуемая последовательность (минимально рискованная):

### Этап 1 — Live-readonly
- Перевести `risk_management` на `live` источники, но **не включать реальную постановку ордеров**.
- Проверить:
  - WS market data
  - WS user data
  - корректность portfolio_state (live)
  - отсутствие “shadow/fail-closed” в execution

### Этап 2 — Live-canary orders
- Allowlist: 1 символ (например, `BTCUSDT`).
- Минимальный размер позиции/ордера.
- Включить торговлю на короткое окно времени.
- Остановить, сверить:
  - ордера/позиции
  - комиссии
  - PnL
  - корректность close/reduce-only сценариев

### Этап 3 — Full live
- Расширить список символов.
- Постепенно поднять лимиты (exposure, max_equity_utilization и т.п.).

## 7) Rollback-план (обязателен заранее)

Rollback должен быть одним действием конфигом:
- Вернуть:
  - `execution_position: testnet`
  - `risk_management: testnet`
  - `portfolio_state: testnet`
- (Опционально) вернуть `trading_mode: hybrid_live_data_testnet_exec`.

Иметь под рукой:
- текущие рабочие значения `binance_api.testnet.*`
- отдельный `.env`/секреты для testnet

## 8) Места в коде, которые важно перепроверить перед live

Это не изменения, а точки контроля поведения:
- Domain routing live/testnet через `binance_api` и `domain_configuration`:
  - `apps/reference/domains/market_data/market_data_connector.py`
  - `apps/reference/domains/execution_position/fsm.py`
- Futures REST клиент и обработка ошибок/ретраев:
  - `apps/reference/adapters/binance_adapter.py`
- Futures WS user-data listenKey + reconnect:
  - `apps/reference/adapters/binance_ws_client.py`
- Spot account observer (решить судьбу для futures-live):
  - `apps/reference/domains/account_observer/account_observer.py`

## 9) Неблокирующая, но очень желательная уборка
- Привести `README.md` и `.env.example` в соответствие с реальными именами env vars из `config/aurora/trading.yaml`.

---

Если хочешь, следующим шагом я могу:
1) Сгенерировать конкретный diff для `config/aurora/trading.yaml` и `config/aurora/system.yaml` (только изменения режимов/URL).
2) Добавить небольшой “config preflight” скрипт, который валидирует наличие нужных env vars и печатает выбранные live/testnet base URL без выполнения торговых операций.
