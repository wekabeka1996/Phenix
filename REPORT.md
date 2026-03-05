# VFOUNDATION ARCHITECTURE: FEATURES & METRICS INVENTORY

Цей документ є повним інвентарем всіх фічей, метрик та подій, які обчислюються, передаються та використовуються в екосистемі vFoundation. Зібрано на основі статичного аналізу коду (TDD & contract-first підхід).

---

## A1. Canonical Features Dictionary (Фічі)

Список фічей, які переважно генеруються модулем `FeatureEngineering` на основі `MARKET_TICK_RECEIVED` та `BAR_CLOSED`, і передаються у словнику `features` події `FEATURES_CALCULATED`.

| Feature Key | Тип / Діапазон | TF | Producer (Джерело) | Consumer (Споживач) | Event Sink |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `obi` | Float [-1.0, 1.0] | Tick | `feature_engineering.py:920` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `tfi` | Float [-1.0, 1.0] | Tick | `feature_engineering.py:921` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `delta_price` | Float (Raw USD) | Tick | `feature_engineering.py:943` | `aurora_scoring_kernel.py` (норм. до `dp_norm`) | `EVT:FEATURES_CALCULATED` |
| `depth_imbalance` | Float [0.0, 1.0] | Tick | `feature_engineering.py:944` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `liquidity_kappa` | Float [0.0, 1.0] | Tick | `feature_engineering.py:1477` | `decision_making.py` (Liquidity Gate) | `EVT:FEATURES_CALCULATED` |
| `absorption` | Float [-1.0, 1.0] | Tick | `feature_engineering.py:1057` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `ema_bias` | Float [0.0, 1.0] | Tick | `feature_engineering.py:927` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `volume_spike` | Float [0.0, 10.0] | Tick | `feature_engineering.py:935` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `volatility_state` | Float [0.0, 1.0] | Tick | `feature_engineering.py:940` | `aurora_scoring_kernel.py` | `EVT:FEATURES_CALCULATED` |
| `macro_resid` | Float [-3.0, 3.0] | Tick | `feature_engineering.py:998` | `aurora_scoring_kernel.py` (Directional) | `EVT:FEATURES_CALCULATED` |
| `macro_sync` | Float [0.0, 1.0] | Tick | `feature_engineering.py:948` | Telemetry/Neocortex (Legacy) | `EVT:FEATURES_CALCULATED` |
| `spread_bps` | Float [0.0, 10000] | Tick | `feature_engineering.py:1114` | FE Health Gate | `EVT:FEATURES_CALCULATED` |
| `large_trade_imbalance`| Float [0.0, 1.0] | Tick | `feature_engineering.py:1069` | UNKNOWN (computed but not active in V2 score)| `EVT:FEATURES_CALCULATED` |
| `volume_zscore` | Float [0.0, 1.0] | Tick | `feature_engineering.py:1064` | UNKNOWN (not active in V2 score) | `EVT:FEATURES_CALCULATED` |
| `volatility.atr_14` | Float (Raw USD) | Bar (3m/5m) | `feature_engineering.py:1468`| `aurora_handler.py:1448` (Entry Logic) | `EVT:FEATURES_CALCULATED` |
| `bb_width` / `pct_b` | Float | Bar | `mean_reversion_strategy.py`| `mean_reversion_handler.py:583` | `EVT:STRATEGY_SIGNAL_PRODUCED`|
| `rsi_14` / `stoch_k` | Float [0, 100] | Bar | `alpha_search/models/momentum.py` | Alpha Search Optimizer / Optuna | N/A (Offline Alpha Search) |

---

## A2. Canonical Metrics Dictionary (Метрики)

Внутрішні обчислення для скорингу, управління ризиками та системної стабільності.

| Metric Key | Тип / Діапазон | Producer (Файл) | Призначення (Why) |
| :--- | :--- | :--- | :--- |
| `signal_score` | Float [-1.0, 1.0] | `aurora_scoring_kernel.py` | Фінальний V2 score стратегії Aurora. Direction × Strength. |
| `risk_score` | Float [0.0, 1.0] | `risk_management.py` | Зважена метрика (delta_price, obi, tfi, absorption). Впливає на блокування інтентів. |
| `postfill_hold_margin_usd` | Float (USD) | `exposure_guard.py:947` | Відстеження заблокованої маржі pending ордерів у Risk/Exposure Guard. |
| `postfill_hold_count` | Integer | `exposure_guard.py:946` | Кількість активних postfill-резервацій для метрик Prometheus. |
| `lock_contention` / `lock_wait_ms`| Float | `wal.py` (tests) | Метрики затримок Write-Ahead-Log для оцінки QoS. |
| `pnl` / `calmar` / `sharpe` | Float | `backtest_engine/reporting.py` | Макро-метрики бектестів та Alpha Search для Optuna objective. |
| `pm_norm` (Price Motion) | Float [-1.0, 1.0] | `decision_making.py` | Sigma-normalized Motion Gate (Anti-Flat / Anti-FOMO) для блокування позицій. |

---

## A3. “Producer → Event → Consumer” Map (Ланцюжок подій)

| Об'єкт (Producer) | Подія (Event) | Об'єкт (Consumer) | Опис взаємодії |
| :--- | :--- | :--- | :--- |
| **BinanceAdapter** | `EVT:MARKET_TICK_RECEIVED` | `FeatureEngineering`, `BarAggregator` | Сирі дані стакана та угод. |
| **BarAggregator** | `EVT:BAR_CLOSED` | `FeatureEngineering` | Тригер закриття свічки (3m, 5m). |
| **FeatureEngineering** | `EVT:FEATURES_CALCULATED` | `RiskManagement`, `RegimeDetector`, `Neocortex` | Розсилка розрахованих фічей для оцінки ринку. |
| **FeatureEngineering** | `CMD:PROCESS_STRATEGY` | `MeanReversionHandler` | Синхронний виклик стратегії (Track B) після закриття бару. |
| **RiskManagement** | `EVT:RISK_ASSESSMENT_COMPLETED`| `DecisionMaking` | Розрахований `risk_score` та дозволи. |
| **RegimeDetector** | `EVT:REGIME_DETECTED` | `DecisionMaking` | Зміна режиму (HIGH_VOLATILITY, TREND_UP тощо). |
| **MeanReversionHandler**| `EVT:STRATEGY_SIGNAL_PRODUCED` | `DecisionMaking` | Готовий сигнал від MR (Long/Short, TP/SL). |
| **DecisionMaking** | `EVT:TRADE_INTENT_PROPOSED` | `ExecutionPosition` (FSM) | Фінальне рішення: відкрити/закрити/перевернути позицію. |
| **DecisionMaking** | `EVT:TRADE_INTENT_DEFERRED` | `DecisionMaking` (Scheduler) | Сигнал відкладено через QOS, Cooldown або Risk Skew. |

---

## B. "Must-capture events" для Shadow-Логера (Neocortex)

Для повного відновлення логіки прийняття рішень та ML-аналітики, Neocortex (через `transport/adapter.py`) ПОВИНЕН перехоплювати наступні `verb`:

1. **`FEATURES_CALCULATED`**: (Priority: High) Містить повний зліпок ринку (`obi`, `tfi`, `macro_resid`, `volatility`).
2. **`RISK_ASSESSMENT_COMPLETED`**: (Priority: High) Містить `risk_score` та дозволені ліміти.
3. **`REGIME_DETECTED`**: (Priority: High) Перемикачі режимів ринку.
4. **`STRATEGY_SIGNAL_PRODUCED`**: (Priority: Medium) Дискретні сигнали від додаткових стратегій (наприклад, MR).
5. **`TRADE_INTENT_PROPOSED`**: (Priority: Critical) Факт прийняття торгового рішення (з `why_chain` та `signal_score`).
6. **`TRADE_INTENT_REJECTED` / `TRADE_INTENT_DEFERRED`**: (Priority: Critical) Відхилення сигналів через Anti-Churn, QoS, Anti-FOMO. Дозволяє зрозуміти "чому ми НЕ зайшли".
7. **`POSITION_OPENED` / `POSITION_CLOSED`**: (Priority: Critical) Фактичне виконання та результати. 

*Цей звіт є контрактом. Будь-які нові фічі повинні додаватися до цього списку перед деплоєм у продакшн.*