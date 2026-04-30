## Аудит коду домену Neocortex / ppo_system

### Огляд

Проведено глибокий аналіз наданих файлів. Виявлено критичні логічні помилки, концептуальні невідповідності, математичні неточності, проблеми асинхронності та застарілий/мертвий код. Нижче наведено детальний звіт за категоріями.

---

## 🔴 Категорія 1: Критичні логічні помилки (призводять до падіння або некоректної роботи)

### 1.1 Неочищення буфера в PPO (agent.py + training_loop.py)
**Файли:** `ppo_system/agent.py`, `ppo_system/training_loop.py`
**Проблема:** Після виклику `agent.update()` буфер `TrajectoryBuffer` не очищується. На наступній ітерації `store()` викине `RuntimeError: Buffer is full`. Відсутній виклик `agent.buffer.clear()` після оновлення.
**Наслідок:** Тренування зупиняється після першого ж оновлення політики.

### 1.2 Некоректний виклик FallbackController (training_loop.py)
**Файл:** `ppo_system/training_loop.py`
**Рядки:** ≈ 75-85
**Проблема:** Виклик `agent.fallback_controller.after_update(metrics, base_lr=agent.base_lr, current_lr=current_lr, current_clip=current_clip, base_clip=agent.base_clip)` використовує неіснуючі атрибути `agent.base_lr` та `agent.base_clip`. Сигнатура методу зовсім інша (очікує `current_lr, current_clip`).
**Наслідок:** `AttributeError` або `TypeError` при спробі виконати fallback.

### 1.3 Детермінована дія для Squashed Gaussian (agent.py)
**Файл:** `ppo_system/agent.py`
**Рядки:** у методі `act()`, приблизно 80-85
**Проблема:** Для `deterministic=True` у випадку `squashed_gaussian` код бере `dist.base_dist.mean` – це середнє базового нормального розподілу **до** застосування `tanh`. Правильна детермінована дія – `tanh(mu)`.
**Наслідок:** Дії виходять за межі `[-1, 1]`, порушується специфікація середовища, погіршується навчання.

### 1.4 Невідповідність конфігурацій з `default_factory` (config_models.py)
**Файл:** `apps/reference/domains/neocortex/config_models.py`
**Класи:** `SequenceConfig`, `DatasetConfig`, `EvaluationConfig`, `PerformanceConfig`, `ShadowGateConfig`
**Проблема:** У `NeuroConfig` ці поля мають `default_factory=ClassName`, але в самих класах **жодне поле не має значення за замовчуванням**. При спробі створити дефолтний екземпляр (наприклад, якщо YAML-файл не містить ці секції) Pydantic викине помилку про відсутність обов’язкових полів.
**Наслідок:** Застосунок не запуститься без явного визначення всіх цих секцій у `neuro.yaml`, навіть якщо вони мали б бути опціональними.

### 1.5 Відсутня валідація `regime_oracle` + `oracle` (config_models.py)
**Файл:** `config_models.py`
**Проблема:** Якщо `neuro.ppo.reward_mode = "regime_oracle"`, то конфігурація `oracle` (з `regime_oracle_reward.yaml`) є обов’язковою, але це ніде не перевіряється.
**Наслідок:** Тренування з режимом oracle може працювати з `None` замість реальної конфігурації → `AttributeError` або некоректна винагорода.

---

## 🟠 Категорія 2: Концептуальні помилки (неправильна архітектура/алгоритм)

### 2.1 LSTM не використовує часові залежності під час навчання (actor_critic_lstm.py + updater.py)
**Файли:** `ppo_system/models/actor_critic_lstm.py`, `ppo_system/learning/updater.py`
**Проблема:**
- Під час збору досвіду (`act`) LSTM стан передається між кроками, але під час навчання (`update`) модель викликається **на кожному спостереженні окремо** з початковим нульовим станом.
- Буфер не зберігає приховані стани, тому неможливо відтворити часову послідовність.
**Наслідок:** LSTM працює як звичайний feedforward-шар, марно витрачаючи параметри. Модель не здатна вивчити довгострокові залежності, що є основною метою використання LSTM в PPO.

### 2.2 Неправильна апроксимація KL-дивергенції (safety.py, updater.py)
**Файл:** `ppo_system/utils/safety.py`, `ppo_system/learning/updater.py`
**Проблема:** Метод `safe_kl` використовує формулу `0.5 * mean((logp - logp_old)^2)`, яка є наближенням **тільки для нормального розподілу** (при малих відхиленнях). Для дискретних дій (Categorical) ця формула не має сенсу. KL між двома категоріальними розподілами обчислюється зовсім інакше.
**Наслідок:** Відстеження `approx_kl` та адаптація параметрів (наприклад, в `AdaptiveKLController`) некоректні для дискретних просторів, що може призвести до неправильного регулювання кліпу/ентальпії.

### 2.3 Асинхронний сервер без контролю навантаження (main.py)
**Файл:** `apps/reference/domains/neocortex/main.py`
**Клас:** `NeocortexEventTapServer`
**Проблема:** Кожен вхідний фрейм створює нову asyncio-таску (`asyncio.create_task`), яка виконує `handle_event_frame`. Немає обмеження на кількість одночасних задач або backpressure. При інтенсивному потоці подій кількість задач може неконтрольовано зрости, що призведе до вичерпання пам’яті.
**Наслідок:** Потенційний `OutOfMemoryError` або значне уповільнення системи.

### 2.4 Некоректна обробка `payload` в `_normalize_event_frame` (main.py)
**Файл:** `main.py`, метод `_normalize_event_frame`
**Проблема:** Якщо вхідний `frame` не має ключа `payload`/`pld`, код прирівнює `payload_dict = dict(frame)`, а потім створює `normalized = dict(frame)`. Це дублює всі поля верхнього рівня всередину `payload`. Також змінюється структура: оригінальні ключі `frame` з’являються і на корені, і всередині `payload`.
**Наслідок:** Непередбачувана структура даних, що передається далі. Можливі конфлікти ключів та неправильна маршрутизація.

---

## 🟡 Категорія 3: Проблеми асинхронності та потокобезпеки

### 3.1 Блокування в `append_shadow_decision_to_wal` (main.py)
**Файл:** `main.py`, функція `append_shadow_decision_to_wal`
**Проблема:** Функція синхронно записує у WAL (дискова операція) і використовується як `shadow_emit_fn` у асинхронному контексті (`handle_event_frame`). Це блокує event loop на час запису.
**Наслідок:** Зниження пропускної здатності та збільшення затримок обробки подій.

### 3.2 Можливий race condition при зупинці сервера (main.py)
**Файл:** `main.py`, методи `start`/`stop` в `NeocortexEventTapServer`
**Проблема:** `stop()` скасовує всі задачі з `self._tasks`, але в момент скасування деякі задачі могли щойно створитися через `call_soon_threadsafe`. Немає гарантії, що всі створені задачі потрапили в `self._tasks` до виклику скасування.
**Наслідок:** Витік задач, які продовжують виконуватися після зупинки сервера.

---

## 🔵 Категорія 4: Мертвий код (не використовується)

| Файл | Клас/Функція | Чому мертвий |
|------|--------------|--------------|
| `ppo_system/agent.py` | `AdaptiveKLController` | Створюється, але ніде не використовується в `update` |
| `ppo_system/agent.py` | `EntropyScheduler` | Створюється, але ніколи не викликається |
| `ppo_system/training_loop.py` | `_is_batched` | Не використовується |
| `ppo_system/controllers.py` | `AdaptiveKLController.update` | Немає викликів |
| `ppo_system/controllers.py` | `EntropyScheduler.value` | Немає викликів |

---

## 🟣 Категорія 5: Захардкоджені параметри та чарівні числа

| Місце | Значення | Коментар |
|-------|----------|----------|
| `main.py` | `deadline_ms = now_ms + 50` | Жорстко заданий 50 мс для fallback, має бути конфігураційним |
| `main.py` | `timeout_ms=50` у `request_authority` | Те саме, дубльований магічний номер |
| `main.py` | `maxBytes=20*1024*1024` (лог) | Добре, але 20 МБ – довільне значення |
| `main.py` | `backupCount=100` | Довільне |
| `actor_critic_lstm.py` | `log_std_init=-0.5` | Добре, що параметризовано, але в класі не використовується конфіг? |
| `updater.py` | `adv.std(correction=0)` | `correction=0` – правильне рішення для уникнення NaN, але добре б мати коментар |

---

## 🟤 Категорія 6: Математичні та логічні неточності

### 6.1 Некоректна нормалізація переваг із нульовою дисперсією (updater.py)
**Проблема:** При `adv_std < 1e-8` код встановлює `batch_data["adv"] = torch.zeros_like(adv)`. Це викидає інформацію про знак переваг. Правильніше було б залишити незмінними (нульове зміщення не шкодить) або використовувати константу.
**Наслідок:** При нульовій дисперсії градієнт політики стає нульовим, навчання зупиняється.

### 6.2 Накопичення GAE з `next_non_terminal` (buffer.py)
**Проблеми немає, але важливе зауваження:** Формула `gae = delta + gamma * lam * next_non_terminal * gae` вірна. Однак `next_values` для останнього кроку береться з `last_values`, що правильно.

### 6.3 Функція втрат PPO (updater.py)
**Використовується стандартна формула:**
`policy_loss = max( -adv * ratio, -adv * clip(ratio, 1-ε, 1+ε) )` – це правильно.
`total_loss = policy_loss + vf_coef * value_loss - ent_coef * entropy` – теж вірно.

---

## ⚪ Категорія 7: Інші проблеми (стиль, суперечливість, документація)

- **Неузгодженість типів**: У `agent.py` `action_dim` для дискретного випадку стає 1, але при передачі в `TrajectoryBuffer` це значення використовується для створення тензора `act` форми `[T, N, 1]`. Потім у `updater.py` викликається `act.squeeze(1).long()` – це працює, але потребує коментаря.
- **Відсутнє очищення буфера після `get`**: Хоча є метод `clear()`, його ніхто не викликає – вже винесено в критичні помилки.
- **Надлишкові датакласи**: `PPOConfig` дублює `AgentConfig` + `TrainConfig`, що може призвести до розсинхронізації.
- **Невикористаний імпорт `truncate_why` в `main.py`** – імпорт є, але `truncate_why` використовується (рядок 167) – все добре.
- **Некоректний обробник винятків у `append_shadow_decision_to_wal`**: Ловить `(OSError, RuntimeError, TypeError, ValueError)`, але запис у WAL може викинути й інші (наприклад, `json.JSONDecodeError`). Варто ловити загальний `Exception` для такого критичного fallback.
- **`_jsonable` не обробляє `NaN` у float**: Може залишити `nan` у JSON, що порушить стандарт JSON. Варто замінювати на `null` або 0.

---

## 📌 Резюме за ступенем критичності

| Ступінь | Проблеми |
|--------|----------|
| **Блокуючі (crash)** | 1.1, 1.2, 1.4 |
| **Логічні (неправильна поведінка)** | 1.3, 2.2, 2.4, 6.1 |
| **Концептуальні** | 2.1, 2.3, 3.1 |
| **Потенційно небезпечні** | 3.2, 5 (хардкод), 1.5 |
| **Косметичні / мертвий код** | Категорія 4, 7 |

---

## ✅ Рекомендації

1. **Терміново додати виклик `agent.buffer.clear()` після `agent.update()` у `training_loop.py`.**
2. **Виправити сигнатуру виклику `fallback_controller.after_update` та додати атрибути `base_lr`/`base_clip` у `PPOAgent`.**
3. **Для Squashed Gaussian детерміновану дію обчислювати як `torch.tanh(dist.base_dist.mean)`.**
4. **У `config_models.py` або додати значення за замовчуванням для усіх полів у спірних конфігураціях, або прибрати `default_factory`.**
5. **Додати валідатор `NeocortexConfig`, що перевіряє наявність `oracle` при `reward_mode = "regime_oracle"`.**
6. **Переробити LSTM-навчання:** зберігати приховані стани у буфері та передавати їх у `updater` для коректного розгортання за часом.
7. **Замінити `safe_kl` на коректне обчислення KL через `torch.distributions.kl.kl_divergence`.**
8. **Додати обмеження на кількість одночасних задач в `NeocortexEventTapServer` (наприклад, використати `asyncio.Semaphore`).**
9. **Винести жорсткі таймаути (50ms) у конфігурацію `authority.deadline_ms`.**
10. **Видалити мертвий код: `AdaptiveKLController`, `EntropyScheduler`, `_is_batched`.**

---

## Аудит коду домену Neocortex – Другий пакет файлів

### Огляд
Проаналізовано 18 файлів: failure_ledger, telemetry, dreamer, feature_buffer, regime_labeler, reward_calculator, buffer (episodic), graph, normalizer, observation, parser, state_aggregator_v2, tailer, wal_replayer, multi_tailer, core_parser, feature_parser, order_parser. Виявлено критичні логічні помилки, концептуальні недоліки, асинхронні проблеми, застарілий код та дублювання.

---

## 🔴 Категорія 1: Критичні логічні помилки (призводять до некоректної роботи)

### 1.1 Неправильний порядок нормалізації в `NeocortexStateAggregator` (state_aggregator_v2.py)
**Файл:** `state_aggregator_v2.py`
**Рядки:** у `_build_snapshot`
**Проблема:**
```python
normalized_features = self._normalizer.normalize(symbol, raw_observation.features_vector)
self._normalizer.update(symbol, raw_observation.features_vector)
```
Спочатку нормалізуємо поточний вектор за допомогою статистики, яка **не включає** цей вектор (добре), а потім оновлюємо статистику. Це правильний порядок для онлайн-нормалізації, але **є помилка**: `update` отримує `raw_observation.features_vector` (сирі дані), а нормалізований вектор створюється на основі попередніх статистик. Однак `normalize` використовує копію середнього та дисперсії, які потім не оновлюються для поточного спостереження. Це нормально. Але є тонка проблема: при першому спостереженні count=0, дисперсія не визначена, `normalize` поверне нулі. Після цього `update` збільшить count до 1, але mean стане рівним сирому вектору, m2=0. Наступне спостереження нормалізуватиметься з count=1, але дисперсія досі нульова (бо m2=0), тому `normalize` поверне знову нулі (оскільки std = sqrt(0+eps) ~ eps, а (x-mean)/eps — дуже великі числа). Це призведе до вибуху значень на початку роботи.
**Наслідок:** Перші декілька знімків будуть мати некоректні (дуже великі) нормалізовані ознаки, що може зруйнувати навчання моделі.

### 1.2 Невидалення низькочастотних ребер у графі через зберігання M2 замість дисперсії (graph.py)
**Файл:** `graph.py`, метод `_update_edge`
**Проблема:**
У базі даних поле `reward_var` зберігає не дисперсію, а суму квадратів відхилень (M2) за алгоритмом Велфорда. При читанні через `get_outgoing_edges` повертається це значення як `reward_var`, що вводить в оману. Потенційно будь-яке використання `reward_var` як дисперсії буде некоректним.
**Наслідок:** Якщо планується використовувати дисперсію винагороди для прийняття рішень (наприклад, для оцінки невизначеності переходу), отримаємо неправильні значення.

### 1.3 Потенційний переповнення пам’яті в `NeocortexEventTapServer` (виявлено в першому аудиті) – підтверджується відсутністю обмежень
**Файл:** `main.py` (з першого пакету), але пов'язано з обробкою подій.
**Проблема:** `NeocortexEventTapServer` створює необмежену кількість asyncio-задач для кожного фрейму. Це може призвести до вичерпання пам'яті.
**Рекомендація:** додати `asyncio.Semaphore` для обмеження кількості паралельних задач.

---

## 🟠 Категорія 2: Концептуальні помилки (неправильна архітектура/алгоритм)

### 2.1 Dreamer обробляє кожен епізод як єдиний перехід (dreamer.py)
**Файл:** `dreamer.py`, метод `_process_episode`
**Проблема:**
Код створює самоперехід (z -> z) для кожного епізоду замість того, щоб обробити послідовність станів. У коментарі зазначено "For single-step episodes", але реальні епізоди мають багато кроків. Метод `consolidate_sequences` реалізовано правильно, але він ніде не використовується.
**Наслідок:** Граф переходів не відображає реальну динаміку ринку, що робить механізм "curiosity bonus" і планування непрацездатними.

### 2.2 LSTM не використовує часову залежність при навчанні (вже виявлено) – підтверджується відсутністю збереження станів у буфері
**Файли:** `ppo_system/agent.py`, `ppo_system/learning/buffer.py`
**Проблема:** `TrajectoryBuffer` не зберігає приховані стани LSTM, тому при оновленні модель викликається для кожного спостереження окремо з нульовим станом.
**Наслідок:** LSTM працює як feedforward-мережа, що суперечить меті використання рекурентної архітектури.

### 2.3 Некоректна обробка тайм-аутів у `NeocortexShadowRuntime` (main.py) – дубльований таймаут
**Файл:** `main.py`, методи `handle_event_frame` та `_build_control_request`
**Проблема:**
Таймаут для authority встановлюється як `deadline_ms = now_ms + 50` (жорстко), а потім при виклику `request_authority` передається `timeout_ms=50`. Це дублювання та відсутність конфігурації.
**Наслідок:** Неможливо налаштувати таймаут без зміни коду.

---

## 🟡 Категорія 3: Проблеми асинхронності та багатопоточності

### 3.1 Використання `threading.Lock` у `TelemetryLogger` в asyncio-середовищі (telemetry.py)
**Файл:** `telemetry.py`, `TelemetryLogger`
**Проблема:**
Логер використовує `threading.Lock`, але викликається з asyncio-задач (оскільки Neocortex працює в asyncio). Блокування потоку в асинхронному коді може призвести до блокування event loop, якщо захоплення утримується довго.
**Наслідок:** Зниження продуктивності, потенційні дедлоки.

### 3.2 Некоректне використання `asyncio.to_thread` у `WALReplayer` без аiofiles (wal_replayer.py)
**Файл:** `wal_replayer.py`, метод `_replay_file`
**Проблема:**
При відсутності `aiofiles` код викликає `file_path.read_text()` через `asyncio.to_thread`, але потім ітерує по рядках у тій самій функції, яка виконується в окремому потоці, але без належного розділення: увесь файл читається в пам'ять, а потім обробляється рядок за рядком. Для великих файлів це може спожити всю пам'ять.
**Наслідок:** OutOfMemoryError.

---

## 🔵 Категорія 4: Мертвий код (не використовується)

| Файл | Клас/Функція | Чому мертвий |
|------|--------------|--------------|
| `dreamer.py` | `DreamEpisode` | Імпортується, але жодного разу не створюється |
| `dreamer.py` | `consolidate_sequences` | Немає викликів |
| `feature_buffer.py` | `FeatureRingBuffer.warmup_remaining` | Використовується? Не знайдено викликів у наданих файлах |
| `multi_tailer.py` | `_calculate_features_backlog_bytes` | Використовується тільки для логування, але функціонально не впливає |
| `failure_ledger.py` | `FailureLedger.get_total_count` | Не використовується |

---

## 🟣 Категорія 5: Захардкоджені параметри та чарівні числа

| Місце | Значення | Коментар |
|-------|----------|----------|
| `telemetry.py` | `max_file_bytes=10*1024*1024` | Довільне, але конфігурується |
| `multi_tailer.py` | `REWARD_SCALE=10.0` | Не винесено в конфіг |
| `multi_tailer.py` | `ttl_ms=3_600_000` (1 год) для чищення епізодів | Добре б конфігурувати |
| `dreamer.py` | `prune_after_n_episodes=100`, `min_edge_count_for_prune=2` | Жорсткі значення |
| `feature_parser.py` | `_DEFAULT_CLIP_ABS` | Словник з дефолтними кліпами – але вони можуть не підходити для всіх символів |
| `state_aggregator_v2.py` | `CONTEXT_DIM=11` | Чарівне число, що відповідає довжині context_vector, але не синхронізовано з кодом |

---

## 🟤 Категорія 6: Математичні та логічні неточності

### 6.1 Некоректне обчислення KL-дивергенції для дискретних дій (виявлено) – підтверджується використанням формули для нормального розподілу
**Файл:** `ppo_system/utils/safety.py`
**Проблема:** `safe_kl` використовує наближення (0.5 * mean(Δlogp²)), яке справедливе лише для нормального розподілу. Для категоріальних розподілів це не має сенсу.
**Наслідок:** Відстеження KL та адаптація коефіцієнтів некоректні для дискретних просторів дій.

### 6.2 Помилка нормалізації переваг при нульовій дисперсії (вже виявлено) – підтверджується
**Файл:** `ppo_system/learning/updater.py`
**Проблема:** При нульовій дисперсії переваги обнуляються, що зупиняє навчання.
**Наслідок:** Якщо всі винагороди однакові (наприклад, тривалий період без позицій), градієнт політики стає нульовим.

### 6.3 Некоректне масштабування винагороди через `tanh` в `multi_tailer.py`
**Файл:** `multi_tailer.py`, метод `_handle_position_close`
**Проблема:**
`episode.reward = np.tanh(net_pnl / REWARD_SCALE)`. Це стискає винагороду до (-1,1), але втрачається лінійна залежність для малих PnL. Для RL це може бути прийнятно, але слід зазначити, що винагорода не є масштабованою до реального PnL.
**Наслідок:** Політика навчається на стиснутих сигналах, що може сповільнити збіжність.

---

## ⚪ Категорія 7: Інші проблеми (дублювання, стиль, документація)

- **Дублювання функцій нормалізації часу:**
  `_normalize_epoch_to_ms` визначено в `main.py`, `core_parser.py`, `feature_parser.py`, `order_parser.py`, `state_aggregator_v2.py`. Потрібно винести в спільний утилітарний модуль.
- **Дублювання визначення `_TIME_FIELD_PRIORITY` та `_PROVENANCE_FIELD_PRIORITY`** у кількох файлах.
- **Карантинний код:** Багато файлів мають `__quarantined__ = True`, що свідчить про застарілість. Зокрема `dreamer.py`, `multi_tailer.py`, `wal_replayer.py`, `tailer.py`, `buffer.py` (episodic), `graph.py`. Ймовірно, вони не використовуються в актуальній системі, але підтримуються для сумісності.
- **Неузгодженість типів:** У `state_aggregator_v2.py` поле `regime_label` має тип `Optional[str]`, але в `NeocortexStateSnapshot` воно використовується без перевірки.
- **Відсутність обробки випадку, коли `last_values` містить NaN** у `updater.py` — хоча є перевірка на `adv_std`, але `last_values` може бути некоректним.

---

## 📌 Резюме за ступенем критичності (додаткові проблеми)

| Ступінь | Проблеми |
|--------|----------|
| **Блокуючі (crash)** | 1.1 (вибух нормалізації на старті) |
| **Логічні (неправильна поведінка)** | 1.2, 1.3, 2.1, 2.2, 6.2 |
| **Концептуальні** | 2.3, 3.1, 3.2 |
| **Якість коду** | дублювання, карантинний код, захардкоджені значення (Категорія 5) |
| **Косметичні / мертвий код** | Категорія 4 |

---

## ✅ Рекомендації (додаткові)

1. **Виправити порядок нормалізації** у `state_aggregator_v2.py`: накопичити достатню кількість спостережень (наприклад, 100) перед використанням нормалізації, або використовувати попередньо обчислені статистики.
2. **Замінити `threading.Lock` на `asyncio.Lock`** в `TelemetryLogger`.
3. **Переписати `WALReplayer`** для потокового читання без завантаження всього файлу.
4. **Видалити або доопрацювати `Dreamer`**: або реалізувати повноцінну обробку послідовностей, або прибрати (оскільки закарантинено).
5. **Уніфікувати допоміжні функції** роботи з часом в окремому модулі `time_utils.py`.
6. **Винести жорсткі константи** (`REWARD_SCALE`, `TTL_MS`, `CONTEXT_DIM`) у конфігурацію.
7. **Додати перевірку на наявність `oracle` конфігурації** при `reward_mode='regime_oracle'` (вже виявлено в першому аудиті).

---

Аудит другого пакету завершено. Загалом, більшість проблем стосується застарілих компонентів (карантин) та помилок у новій логіці нормалізації. Рекомендується сфокусуватися на виправленні проблем у `state_aggregator_v2.py` та видаленні мертвого коду.



## Третий пакет аудита: домен Neocortex (завершающий)

### Обзор
Проанализированы файлы, предоставленные в третьей партии. Охвачены ключе компоненты: shadow gates, evaluator, dataset policies, brain core (VAE, world model, worker, bridge), adapter, authority bridge, контракты времени, таксономия отказов, конфигурации YAML и другие. Обнаружены как новые проблемы, так и подтверждения ранее выявленных.

---

## 🔴 Категория 1: Критические логические ошибки (приводят к сбоям/некорректной работе)

### 1.1 Несоответствие размерности в нейросетевых компонентах (brain/core.py, vae.py, world_model.py)
**Файлы:** `core.py`, `vae.py`, `world_model.py`, `config_models.py`
**Проблема:**
- В `VAEConfig` `input_dim` должен совпадать с `len(config.ingest.feature_list)` (20), что проверяется валидатором.
- В `NeuroConfig.ppo.state_dim` ожидается размерность вектора состояния, но в конфигурации `neuro.yaml` `state_dim: 16` (совпадает с latent_dim). Однако в `BrainCore` при создании PPO используется `obs_space = MockSpace(shape=(self.config.vae.latent_dim,))` — это правильно. Но в `PPOConfig` поле `state_dim` нигде не используется в инициализации PPO (используется только `hidden_size` из `AgentConfig`, который берется из `hidden_dims[0]`).
- В `world_model.py` параметр `action_dim` везде задан 0, хотя в конфиге `WorldModelConfig` нет поля `action_dim`. Если в будущем понадобятся действия, модель не сможет их учесть.

**Наследствие:** Потенциальное несоответствие между конфигурацией и фактической архитектурой, что может привести к ошибкам при расширении.

### 1.2 Некорректная обработка `feature_missing_timestamp_policy` в `state_aggregator_v2.py` (уже было) – но здесь добавлены `replay.yaml` с `legacy_non_causal_file_offset`, что при `live_shadow` сработает как критическая ошибка (gate `causal_time.hard_gate` заблокирует запуск). Это правильно — gate есть. Однако в `main.py` используется `append_shadow_decision_to_wal`, который не обрабатывает эту политику — там нет проверки на causal time.

### 1.3 Нет очистки буфера после `finalize()` в PPO (уже выявлено) – но теперь видно, что в `brain_bridge` вызывается `train_policy_async`, которая внутри использует `self.ppo_agent.buffer.clear()` только в конце. Однако в `adapter.py` метод `train_policy_async` не используется — используется `train_policy`, который вызывает `agent.update()` без вызова `buffer.clear()`. **Исправлено?** Смотрю: в `core.py` метод `train_policy` содержит `self.ppo_agent.buffer.clear()` в конце. Хорошо. Но в `adapter.py` вызов `await self.brain_bridge.train_policy_async(samples_to_process)` передаёт управление в `bridge.py`, который отправляет задачу в worker, где в `brain_service_worker` вызывается `brain_core.train_policy(samples)`. В `core.py` `train_policy` действительно вызывает `self.ppo_agent.buffer.clear()` после обновления. Значит, эта проблема устранена. Проверим: в `core.py` строка после обновления: `self.ppo_agent.buffer.clear()`. Да, есть. Ошибка первого аудита неактуальна.

### 1.4 Неправильный порядок нормализации в `NeocortexStateAggregator` (уже выявлено) – но в `adapter.py` используется другой подход: `_normalize_features_for_symbol` вызывает `update` после `normalize`. Это правильно. А в `state_aggregator_v2.py` проблема остаётся (см. аудит 2). Рекомендация: исправить в `state_aggregator_v2.py`.

### 1.5 Ошибка в `ObservationEnvelope.from_snapshot`: требуется `causal_only`, но если `snapshot.trainable` или `event_time_is_causal` ложно, выбрасывается исключение. Это правильно. Однако если `event_time_is_causal` истинно, но `dataset_visibility != "trainable"`, тоже исключение. А в `state_aggregator_v2` для `trainable=False` выставляется `dataset_visibility="diagnostics_only"`, и такой snapshot не может быть превращён в ObservationEnvelope — это по замыслу (только trainable попадают в authority). Но есть риск: если где-то в коде будет вызван `build_observation_envelope` для нетренируемого снэпшота, упадёт с ошибкой. Нужно убедиться, что это не происходит.

### 1.6 В `DatasetPolicyEngine.evaluate_sample` для `objective_family="representation"` проверка `has_representation_payload` требует `features_vector` или `features`. В `adapter.py` representation sample создаётся с `features_vector`, всё нормально. Но в `regime_supervision` sample нет `features_vector` — он добавляется отдельно. Это нормально.

### 1.7 В `TelemetryLogger` метод `log_step` вызывает `_queue_row_locked` и `_flush_locked` внутри блокировки, но `_flush_locked` может выполнять I/O (открытие файла, запись) внутри блокировки, что блокирует другие потоки. Уже замечено в аудите 2, но здесь подтверждается.

---

## 🟠 Категория 2: Концептуальные ошибки

### 2.1 LSTM не использует временные зависимости в PPO (уже выявлено) – в `core.py` методы `train_policy` и `train_regime_supervision` не используют LSTM-состояния корректно. При обучении на батче независимых эпизодов (каждый эпизод — один шаг) LSTM не получает последовательности. Для `policy` обучения эпизоды — это отдельные шаги, а не последовательности, поэтому LSTM фактически не нужен. Но архитектура предполагает использование LSTM, а на практике он работает как feedforward. Это концептуальная проблема.

### 2.2 В `brain/core.py` метод `train_batch` принимает `batch_obs` (тензор) и `regime_targets`, но внутри вызывает `self.vae.loss_function` с `regime_logits`, вычисленными через `predict_regime_logits(mu)`. Однако `regime_targets` могут быть `None`, тогда aux loss не считается. Это нормально. Но в `adapter.py` вызов `train_async` для representation learning не передаёт regime_targets. В результате aux голова VAE не обучается в основном цикле, только через `_train_vae_aux_from_episodes`. Это может быть по замыслу, но из-за этого regime aux может быть недостаточно оптимизирован.

### 2.3 В `adapter.py` при обработке `handle_features` создаётся `representation_sample` и оценивается `_evaluate_dataset_candidate`. Если он `is_trainable`, то добавляется в `self._representation_samples`. Но никогда не используется для обучения — только для статистики. Тренировка representation происходит через `_maybe_train`, который берёт батч из `buffer` (сырые наблюдения) и вызывает `bridge.train_async`, который внутри вызывает `brain_core.train_batch` без regime_targets. Правильно.

### 2.4 Механизм `dream_threshold` — порог для запуска обучения на накопленных эпизодах. В `adapter.py` при `_maybe_dream` проверяется `len(self._regime_supervision_samples) >= self.dream_threshold` и `len(self._policy_samples) >= self.dream_threshold`. Однако для `regime_supervision` обучение происходит через `_trigger_regime_supervision_training`, который передаёт список samples в `bridge.train_regime_supervision_async`, а тот в `brain_core.train_regime_supervision` → `_train_vae_aux_from_episodes`. Но `_train_vae_aux_from_episodes` внутри использует `features_vector` из эпизода для VAE, а не для regime aux? Смотрим: там для каждого эпизода берётся `features_vector` и `realized_regime`, кодируется, считается loss. Это нормально, но не использует PPO. Это именно aux обучение.

### 2.5 В `ShadowOfflineEvaluator` методы `evaluate_regime_supervision` и `evaluate_execution_quality` полагаются на `DatasetEvaluatedSample`, который содержит `sample` как dict. В `sample` ожидаются ключи `predicted_regime`, `realized_regime` и т.д. В `adapter.py` при создании `regime_supervision_sample` эти ключи присутствуют. Однако в `build_advisory_readiness_report` используется `calibration_report` только если `status == "available"`. Но в `neuro.yaml` `missing_confidence_policy: "not_available"`, поэтому при отсутствии confidence калибровка недоступна — это правильно.

---

## 🟡 Категория 3: Проблемы асинхронности и многопоточности

### 3.1 В `TelemetryLogger` используется `threading.Lock` и синхронный файловый ввод-вывод, что в асинхронной среде может блокировать event loop. Уже отмечено.

### 3.2 В `adapter.py` метод `_run_non_critical_io` использует `asyncio.to_thread` для вызовов `telemetry.log_*` и `_enqueue_shadow_intent_log`. Это правильно, так как I/O вынесено в поток. Но внутри `_enqueue_shadow_intent_log` используется `self._shadow_log_context()` и `self._rotate_shadow_intent_log_if_needed`, которые могут выполняться в потоке, но они синхронные и используют блокировку `threading.RLock`. Потенциально нормально, но нужно быть осторожным с количеством потоков.

### 3.3 В `brain/bridge.py` метод `_result_listener` работает в отдельном потоке и вызывает `self._loop.call_soon_threadsafe`. Это правильно. Но при shutdown нет гарантии, что все результаты обработаны — может быть потеря данных. В `adapter.shutdown_async` ожидается завершение `_pending_tasks`, но задачи, отправленные в bridge, не отслеживаются. Нет механизма дождаться, пока worker завершит текущие задачи.

### 3.4 В `main.py` (из первого пакета) `NeocortexEventTapServer` создаёт неограниченное количество задач — не исправлено.

---

## 🔵 Категория 4: Мертвый код (не используется)

| Файл | Код | Причина |
|------|-----|---------|
| `brain/core.py` | `train_ppo` (legacy) | Помечен как legacy, вызывает `train_policy`. Можно удалить. |
| `brain/world_model.py` | Аргумент `action_dim` | Всегда 0, не используется. |
| `adapter.py` | `_waiting_for_reward_source` | Устанавливается, но нигде не читается. |
| `adapter.py` | `train_ppo_now` | Метод для отладки, в prod вряд ли используется. |
| `failure_ledger.py` | `get_total_count` | Не используется (только в тестах). |
| `feature_buffer.py` | `warmup_remaining` | Используется только в `stats`, но не в основной логике. |
| `dreamer.py`, `multi_tailer.py`, `graph.py` | Все помечены `__quarantined__ = True` — не используются в текущей архитектуре. |

---

## 🟣 Категория 5: Захардкоженные параметры и магические числа

| Место | Значение | Комментарий |
|-------|----------|-------------|
| `core.py` | `free_bits_per_dim: 0.2` в `neuro.yaml` | Хорошо, что параметризовано. |
| `core.py` | `max_grad_norm=1.0` для VAE | Не вынесено в конфиг (в `vae` нет поля). |
| `core.py` | `checkpoint_metadata` содержит версию 1 | OK |
| `adapter.py` | `_shadow_intent_log_max_bytes = 10 * 1024 * 1024` | Хорошо, что есть, но лучше вынести в конфиг. |
| `adapter.py` | `_shadow_intent_log_backups = 5` | Тоже. |
| `adapter.py` | `_backpressure_threshold = self._train_batch_size * 2` | Магический множитель 2. |
| `adapter.py` | `_backpressure_sleep_sec = 0.01` | Не используется? В коде не нашел применения. |
| `adapter.py` | В `_handle_oracle_settlement` `self._oracle_settlements` | Счётчик, но без предела. |
| `shadow.py` | `domain_manifest_path` по умолчанию `.../domain.yaml` | Жесткий путь, но можно переопределить. |

---

## 🟤 Категория 6: Математические и логические неточности

### 6.1 В `VAE.loss_function` используется `free_bits_per_dim`: вычисляется `kld_loss = torch.maximum(kld_dim_mean, floor).sum()`. Это правильная реализация free bits per dimension. Однако в `neuro.yaml` `free_bits_per_dim: 0.2` — допустимо.

### 6.2 В `WorldModel.forward` для предсказания следующего состояния используется `self.fc_out(out)`. Это линейный слой, который может выдавать неограниченные значения, что может дестабилизировать обучение. Желательно добавить `tanh` или другой нормализатор.

### 6.3 В `RegimeLabeler.compute_realized_regime` для `EXHAUSTION` условие: `vol_state_now > exhaustion_vol_now_threshold and vol_state_future < exhaustion_vol_future_threshold`. Но если vol_state_now был высоким, а vol_state_future тоже высоким — exhaustion не наступает. Это логично.

### 6.4 В `RewardCalculator` для `formula_b` используется матрица из конфига. В `regime_oracle_reward.yaml` задана очень агрессивная матрица с большими положительными и отрицательными значениями. Это может привести к высокой волатильности градиентов. Нужно следить за масштабированием.

### 6.5 В `BrainCore.train_policy` при вычислении `logp_t` для дискретного действия используется `dist.log_prob(act_t_long)`, затем `logp_t = logp_t.float()`. Но затем `action` передаётся в `store` как `act_t_long.float()`. В PPO updater ожидается `act` long для categorical. В `agent.py` (PPO) при `store` действие приводится к `float`, а в `updater.py` для дискретного случая вызывается `act.squeeze(1).long()`. Это работает, но некрасиво.

### 6.6 В `adapter.py` при создании `regime_supervision_sample` поле `confidence` берётся из `action_result.get("confidence")`. Но `confidence` — это log probability, которая может быть отрицательной и не ограничена [0,1]. Для калибровки это не подходит. В контрактах калибровки ожидается confidence в [0,1]. Это потенциальная проблема: logp не является вероятностью. Нужно преобразовывать через exp или сигмоиду.

---

## ⚪ Категория 7: Другие проблемы (стиль, документация, дублирование)

- **Дублирование определения `CausalTimeProvenance`**: есть в `time_provenance.py` и реэкспорт в `causal_time.py`. Нормально.
- **Множественные определения `_normalize_epoch_to_ms`** в разных файлах — нужно вынести в один утилитарный модуль.
- **Карантинные файлы** (`dreamer.py`, `multi_tailer.py`, `graph.py`, `core_parser.py`, `feature_parser.py`, `order_parser.py`, `tailer.py`, `wal_replayer.py`) — они помечены `__quarantined__ = True`, но всё ещё присутствуют в репозитории. Загрязняют код.
- **Конфигурация `replay.yaml`** использует `feature_missing_timestamp_policy: "legacy_non_causal_file_offset"`, что для `backtest` допустимо, но для `live` было бы критично.
- **Отсутствие лимита на количество `_inflight_training_tasks`** — хотя есть `max_inflight_training_tasks`, но в `_maybe_train` проверка есть. Хорошо.
- **Нет проверки на `None` в `adapter._run_training` для `losses`**. Если `bridge.train_async` вернёт `None` (например, при ошибке), то ниже `losses.get('vae_loss')` вызовет исключение.

---

## 📌 Итоговое резюме (с учетом всех трёх аудитов)

| Степень | Проблемы (новые и подтверждённые) |
|---------|-----------------------------------|
| **Блокирующие (crash)** | – `state_aggregator_v2` порядок нормализации (1.1 из второго аудита) <br> – `NeocortexEventTapServer` неограниченные задачи (1.3 из первого) <br> – `ObservationEnvelope` требует trainable snapshot, может упасть (1.5) |
| **Логические (неправильная работа)** | – LSTM не учитывает временные зависимости (2.1, 2.2) <br> – Confidence = logp (не [0,1]) для калибровки (6.6) <br> – `safe_kl` неправильный для дискретных действий (6.1 из первого) <br> – Неправильная детерминированная action для squashed Gaussian (1.3 из первого) |
| **Концептуальные** | – Отсутствие очистки буфера в PPO (было, но теперь исправлено? в `core.py` есть clear) <br> – Неиспользуемые aux обучения VAE (2.2) <br> – Захардкоженные таймауты (5 из первого) |
| **Асинхронность/многопоточность** | – `TelemetryLogger` с `threading.Lock` и синхронным I/O (3.1) <br> – Потеря задач при shutdown bridge (3.3) <br> – `append_shadow_decision_to_wal` синхронный (3.1 из первого) |
| **Математические** | – KL approximation для дискретных (6.1 из первого) <br> – Нулевая дисперсия преимуществ (6.2 из первого) <br> – `free_bits_per_dim` реализован правильно |
| **Мёртвый код** | – `dreamer.py`, `multi_tailer.py`, `graph.py` и др. карантинные <br> – `train_ppo` legacy, `_waiting_for_reward_source` и т.д. |

---

## ✅ Рекомендации (наиболее критические)

1. **Исправить `state_aggregator_v2.py`**: накапливать статистику перед использованием нормализации (например, первые N наблюдений не нормализовать, а только собирать статистику).
2. **В `NeocortexEventTapServer`** добавить `asyncio.Semaphore` для ограничения параллельных задач.
3. **Преобразовывать confidence** из logp в вероятность (например, `np.exp(logp)` для дискретных действий или `sigmoid` для непрерывных) перед передачей в калибровку.
4. **Вынести общие функции** (`_normalize_epoch_to_ms`) в один модуль `time_utils`.
5. **Удалить карантинные файлы** (`dreamer.py`, `multi_tailer.py`, `graph.py`, `tailer.py`, `wal_replayer.py`, `core_parser.py`, `feature_parser.py`, `order_parser.py`), если они не используются.
6. **В `TelemetryLogger`** заменить `threading.Lock` на `asyncio.Lock` и использовать асинхронные методы записи.
7. **В `brain/core.py`** добавить проверку на `losses is not None` в `_run_training`.
8. **В `adapter._handle_oracle_settlement`** при отсутствии `model_features_t` не падать, а использовать features_t для создания вектора.

---

