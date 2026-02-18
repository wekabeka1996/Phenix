



# Neocortex Fix Plan v2.1 (скориговано за ревʼю)

## Summary
Мета: закрити три блоки одночасно без зміни політики `Structured Only`:
1. Прибрати starvation у `MultiTailer` (fair ingestion).
2. Заповнити PPO/episode telemetry у `neocortex_metrics.csv`.
3. Довести до робочого стану e2e delivery structured reward для `POSITION_CLOSED`.

Ключове рішення: **primary канал для Phase 3 — Structured Log** (через `execution_position/fsm.py`), не Event Bus.

## Locked Decisions (зафіксовано)
1. Reward fallback на equity-delta не повертаємо.
2. Phase 3 робимо через structured log line у `aurora_core.log` як основний production path.
3. Event Bus path лишається secondary/optional (не блокує цей цикл).
4. `batch_size` у `MultiTailer` лишається як micro-yield параметр; `quota` додається як hard cap на цикл.
5. `TelemetryLogger.log_episode` сигнатуру не змінюємо; логування episode робимо тільки коли reward валідний.
6. Симуляція PnL використовує `price` із feature-потоку, але з явною політикою time alignment (див. Phase 4).

## Public Interfaces / Contracts (оновлення)
1. `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py`:
   - Додати в `MultiSourceConfig`:
   - `max_feature_lines_total_per_cycle: int = 1000`
   - `max_feature_lines_per_symbol_per_cycle: int = 200`
   - `max_order_lines_per_cycle: int = 500`
   - `max_core_lines_per_cycle: int = 500`
2. `apps/reference/domains/neocortex/logic/telemetry.py`:
   - Розширити `log_buffer_stats(...)` параметром `episodes_processed: Optional[int] = None`.
3. `apps/reference/domains/neocortex/transport/adapter.py`:
   - У `_trigger_ppo_training(...)` логувати PPO метрики в CSV.
   - У `add_completed_episode(...)` логувати episode reward/pnl у CSV лише для trainable episode.
4. `apps/reference/domains/execution_position/fsm.py`:
   - Оновити log формування close event: лог-рядок має містити structured поля `symbol`, `trade_id`, `close_ts_ms`, `realized_pnl_net`, `fees` у форматі key=value.
5. `apps/reference/domains/neocortex/logic/ingest/parsers/core_parser.py`:
   - Не змінювати контракт; він уже готовий парсити structured `POSITION_CLOSED` key=value.

## Phase 1: Fair Ingestion (MultiTailer)
1. Рефактор циклу обробки так, щоб кожен stream читав bounded кількість рядків за ітерацію.
2. Для features реалізувати round-robin між символами з двома лімітами: per-symbol + total-per-cycle.
3. `orders` і `core` теж читати по quota, не до EOF.
4. Після кожного stream блоку робити `await asyncio.sleep(0)`.
5. `batch_size` залишити як внутрішній yield у межах stream; `quota` — верхня межа рядків на цикл.
6. Зберегти поточну offset/rotation/truncate логіку.
7. Додати діагностичні поля у progress log: backlog bytes по features/orders/core та `pending_episodes`.

### DoD Phase 1
1. На synthetic test: `orders_processed > 0` до того, як `features_processed` перетне 5000 (за heavy feature backlog).
2. Немає необмежених read-to-EOF у stream processors у межах однієї ітерації run-loop.
3. `Progress` лог показує інтерлівінг (ростуть не лише features).

## Phase 2: PPO + Episode Telemetry
1. У `_trigger_ppo_training(...)` після успішного result писати:
   - `ppo_loss_pi`, `ppo_loss_v`, `ppo_entropy`.
2. Додати defensive key mapping для PPO result:
   - policy: `loss_pi` або `policy_loss` або `ppo_loss_pi`.
   - value: `loss_v` або `value_loss` або `ppo_loss_v`.
   - entropy: `entropy` або `ppo_entropy`.
3. Якщо PPO result частковий, логувати warning і записувати доступні поля без падіння.
4. У `add_completed_episode(...)`:
   - якщо `reward_missing=False`, викликати `telemetry.log_episode(reward=..., pnl=...)`.
   - якщо `reward_missing=True`, не писати fake reward=0 у `log_episode`.
5. Писати `episodes_collected`/`episodes_processed` через `log_buffer_stats(...)`.

### DoD Phase 2
1. У CSV зʼявляються непорожні `ppo_loss_pi|ppo_loss_v|ppo_entropy`.
2. У CSV зʼявляються `last_reward|last_pnl` для trainable episodes.
3. `cumulative_reward` не накручується від reward_missing case.

## Phase 3: Structured Reward E2E (Primary: Structured Log)
1. У `execution_position/fsm.py` close-log змінити на structured формu:
   - містить `EVT:POSITION_CLOSED symbol=... trade_id=... close_ts_ms=... realized_pnl_net=... fees=...`.
2. Не видаляти існуючий emit на bus; але bus не є primary критерієм цієї фази.
3. Перевірити, що `core_parser` парсить новий рядок у `CoreEventType.POSITION_CLOSED` з заповненим `realized_pnl_net`.
4. Перевірити downstream у `MultiTailer._handle_position_close(...)`: episode закривається з reward/pnl.
5. Якщо `realized_pnl_net` відсутній: `reward_missing=True`, training gated, alert `NO_STRUCTURED_REWARD_RECEIVED`.

### DoD Phase 3
1. У runtime логах є `EPISODE COMPLETE ... pnl=... reward=...`.
2. У CSV ростуть `last_pnl|last_reward` після фактичних closes.
3. Політика no-fallback підтверджена (ніякого equity-delta reward).

## Phase 4: Simulation PnL/WinRate (аналітика)
1. Додати evaluator script для `shadow_intents.jsonl*` + `features` price stream.
2. Явно зафіксувати time alignment policy:
   - якщо вхідні features без source timestamp, симуляція працює по послідовності (sequence-based), а не wall-clock.
   - у звіті позначати режим `sequence_time`.
3. Правила симуляції:
   - entry: наступний доступний tick після intent.
   - exit: через horizon або reverse intent.
   - fee: 4 bps round-trip.
   - slippage: 1 bp entry + 1 bp exit.
4. Вихідні артефакти:
   - `reports/neocortex_shadow_simulation_*.csv`
   - `reports/neocortex_shadow_simulation_summary_*.md`

### DoD Phase 4
1. Звіт відтворюваний (повторний запуск дає ті ж метрики за той самий input).
2. У summary явно вказано, чи це `sequence_time` чи `wall_clock_time`.

## Test Plan
1. Unit:
   - quota reader behavior (features/orders/core).
   - PPO telemetry mapping keys.
   - episode telemetry (trainable vs reward_missing).
2. Integration:
   - heavy features + sparse orders/core starvation regression.
   - execution_position close log -> core_parser -> episode close -> adapter telemetry.
3. Regression:
   - no-fallback policy.
   - graceful shutdown з pending tasks.
4. Runtime acceptance:
   - `Progress` показує зростання `Orders`/`Episodes` разом із `Features`.
   - `PPO update complete` корелює з непорожніми PPO колонками у CSV.
   - зʼявляються `EPISODE COMPLETE` та `last_pnl/last_reward`.

## Rollout Gates
1. G1 Fairness: starvation test green.
2. G2 Telemetry: PPO/episode поля в CSV заповнюються.
3. G3 Reward Contract: structured close log стабільно парситься у staging.
4. G4 Analytics: симуляційний звіт генерується щоденно без помилок.
5. G5 Shadow Stability: 24h без crash і без деградації ingestion.

## Assumptions
1. `Structured Only` policy незмінна.
2. CPU-only залишається валідним runtime режимом.
3. `run_mode` не змінюємо автоматично у цьому циклі.
4. Stale cleanup для pending episodes вже існує і не є окремим блокером цієї ітерації.
