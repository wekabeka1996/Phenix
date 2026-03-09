# Аналіз реалізацій Optuna в проекті Phenix

Цей звіт є результатом аудиту існуючої кодової бази, який оцінює поточний стан інтеграції Optuna, її готовність до роботи з новими конфігами (V2 Scoring, Quadratic Brain), виявлені вузькі місця, а також описує бачення подальшого використання Optuna для стратегій `aurora` та `mean_reversion`.

---

## 1. Поточний стан реалізацій Optuna

У проекті існують два паралельні підходи до оптимізації через Optuna:

### А. Спадковий "Плаский" підхід (Legacy Flat Runner)
- **Файл**: `backtest_engine/optuna_runner.py`
- **Опис**: Базова обгортка навколо `run_backtest_simulation`. Зчитує конфігурацію пошукового простору з `optuna_config.yaml`, генерує параметри (через dotted path overlay), проводить один бектест на епоху.
- **Цільова функція (Objective)**: Оптимізує `Calmar ratio` (ROI / Max Drawdown).
- **Гейти**: Прості обмеження (мінімальна кількість угод, максимальна просадка, мінімальна кількість інтентів), порушення яких повертає `-1e9`.

### Б. Ієрархічний підхід (Hierarchical 3-Stage Optimizer)
- **Файли**: `optimization/optimizer.py`, `optimization/objectives.py`, `optimization/backtest_interface.py`
- **Опис**: Просунута ієрархічна структура з 3-х стадій:
  - **Stage 0 (Regime Calibration)**: Налаштовує параметри Regime Detector (пошук стабільності режиму, максимізація `stability_score`). Не використовує PnL.
  - **Stage 1 (Alpha Search)**: Фіксує режими і шукає параметри альфи. Оптимізує `alpha_score` (Sharpe Ratio мінус штрафи за Churn, Reject Rate, MDD).
  - **Stage 2 (Robustness Validation)**: Тестування на стійкість (Walk-Forward validation, Execution Stress, Block Bootstrap).
  - **Holdout Gate**: Фінальна перевірка на повністю ізольованих "холодних" даних (останні N місяців).

---

## 2. Наскільки Optuna готова до роботи (Вузькі місця та проблеми)

### 2.1. Жорстка прив'язка (Hard-Lock) до Aurora і BTCUSDT
В ієрархічному оптимізаторі наявне серйозне вузьке місце у файлі `optimizer.py`:
```python
    def _validate_universe_lock_cfg(cfg: Dict[str, Any]) -> tuple[list[str], str]:
        # ...
        if symbols != ["BTCUSDT"] or strategy_id != "aurora":
            raise ValueError(
                "Optimization universe lock violation: expected "
                "data.symbols=['BTCUSDT'] and data.strategy_id='aurora'."
            )
```
**Проблема**: Цей замок унеможливлює використання ієрархічної оптимізації для стратегії `mean_reversion` або для інших символів (ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT) без прямого втручання в код. Це серйозно обмежує масштабованість.

### 2.2. Відставання від нових контрактів конфігів (Signal Score V2 & Quadratic Brain)
Механізм накладання параметрів (`_build_overlay` з dotted path) працює ідеально для динамічних схем Pydantic. **Але готовність системи цілком залежить від файлів `stage0_search_space.yaml` та `stage1_search_space.yaml`**. 
- Оскільки система перейшла на `SignalScoreV2` (де `liquidity` є hard gate, а не weighted feature) і додала `feature_neutrals`, а Фаза 9 запровадила `QuadraticScoringKernel` (сила експозиції через квадрат + `shield_multiplier`), старі пошукові простори з імовірністю 100% не актуальні. Optuna намагатиметься оптимізувати видалені ваги (наприклад, `liquidity_kappa` як вагу), що призведе або до помилок валідації Pydantic, або до марної втрати часу.

### 2.3. Парсинг метрик (Churn та Reject Rate)
У `backtest_interface.py` метрика відмов (Reject Rate) вираховується на основі статусу інтентів (`"intent_status" == "REJECTED"`, `"outcome".startswith("GUARD_REJECT")` тощо). Це добре працює для Aurora, але логування інтентів Mean Reversion має повністю відповідати цій же схемі, інакше штрафи (Penalties) в Optuna будуть працювати сліпо або некоректно каратимуть/нагороджуватимуть стратегію.

---

## 3. Бачення використання Optuna для Aurora та Mean Reversion

Опираючись на поточний стан архітектури та наявність потужних інструментів ієрархічної валідації (Walk-Forward, Bootstrap, Stress-тести), пропоную наступний план розвитку оптимізації.

### 3.1. Зняття кайданів "Universe Lock"
Необхідно негайно рефакторити `_validate_universe_lock_cfg` та `BacktestAdapter._enforce_universe_lock`, щоб вони читали цільову стратегію та символ з конфігурації епохи (або CLI). Це відкриє шлях до незалежної оптимізації:
- **Aurora**: BTCUSDT, ETHUSDT, SOLUSDT
- **Mean Reversion**: DOGEUSDT, XRPUSDT (та гібридний BTCUSDT).

### 3.2. Стратегія використання: Aurora (Trend / Directional)
Aurora тепер базується на `Direction / Strength Split` та `Quadratic Brain`. Оптимізацію Aurora слід розділити за логічними блоками (етапами) у `stage1_search_space`:
1. **Шар Режимів (Stage 0)**: Калібрування `regime_threshold_multipliers` та згладжування (`regime_smoothing`).
2. **Шар Сигналів**: Передача в Optuna для пошуку `feature_neutrals` (центрів сили) та `strength_alpha` / `strength_cap`. 
3. **Шар Гейтів**: Оптимізація `kappa_min` для ліквідності, та налаштувань Anti-FOMO/Anti-Flat.
*Завдання Optuna*: Знайти комбінацію нейтралей та множників, які при квадратичному прискоренні дають найвищий Sharpe, залишаючись в рамках лімітів MDD (через штрафи в `AlphaSearchObjective`).

### 3.3. Стратегія використання: Mean Reversion (Ranging / Sideways)
Для MR (Bollinger Bands, 1m bars) логіка оптимізації кардинально інша, і Optuna ідеально для цього підходить:
1. Оскільки MR працює лише у флетових режимах (`MEAN_REVERSION`, `LOW_VOLATILITY`), **Stage 0 (Regime Calibration)** є для неї абсолютно критичною. Якщо детектор режимів "запізнюється", MR буде купувати проти проривів. Тому Stage 0 для MR має оптимізувати чутливість визначення переходу з тренду у флет.
2. **Шар Альфи (Stage 1)** для MR має шукати: `bb_window`, `bb_num_std`, `entry_threshold` та `sl_atr_mult`.
3. Оскільки MR робить багато угод з коротким життям, `P_churn` (штраф за мікро-угоди) в `objectives.py` для MR потрібно або вимкнути, або значно послабити (шляхом передачі іншого `PenaltyConfig`), інакше оптимізатор штучно "заріже" найкращі прогони.

### 3.4. Застосування Stage 2 (Robustness) як Абсолютного Фільтра
Ядро `Stage 2` (Walk-Forward + Stress Execution) є найкращим елементом поточної системи. Враховуючи, що ми тестуємо на маржинальних ринках (Binance Futures), імплементований Execution Stress (рандомізація slippage_bps, latency_ms) і Block Bootstrap — це єдине, що захищає конфіги від overfitting'у. 
**Моє бачення**: Усі конфіги для `Aurora` та `Mean Reversion` перед злиттям у Production **повинні** проходити через `run_stage2()`. Якщо стратегія (будь-яка) "ламається" при збільшенні slippage з 2 до 10 bps (що імітує Stage 2 Execution Stress), Optuna повинна її відхиляти.

### Висновок
Інфраструктура Optuna (`optimizer.py`) написана на дуже високому архітектурному рівні, але зараз вона є "заручником" старого технічного боргу (жорстка фіксація на BTC/Aurora) та застарілих `.yaml` файлів конфігурації пошукового простору. Щойно ці обмеження будуть зняті (зміна 1 методу та оновлення YAML), оптимізатор стане універсальним інструментом калібровки обох стратегій у рамках нових фаз.