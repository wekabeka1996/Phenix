# AUDIT-DEPTH-IMBALANCE-CONFIG-AND-TESTS-008

Дата: 2026-01-05

## 0) Executive summary

`depth_imbalance` в текущей реализации — нормализованная $phi$ в $[0,1]$ с нейтралью $0.5$, где **большее значение означает доминирование ASK (sell pressure)**. Ранее в стратегических весах (Aurora) использовался положительный вес, что инвертировало смысловой вклад в net-zero scoring V2. Вес был перевёрнут на отрицательный.

Дополнительно выявлен wiring-gap: параметр `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` существовал в конфиге, но не использовался при вычислении. Внесено исправление: флаг теперь реально влияет на вычисление.

## 1) Spec / семантика (SSOT)

### 1.1 Формула (FeatureEngineering)

Реализация в [apps/reference/domains/feature_engineering/calculation_engine.py](../apps/reference/domains/feature_engineering/calculation_engine.py):

- `ratio = (ask + half) / (bid + half)`
- `imbalance = (ratio - 1) / (ratio + 1)`  (диапазон $[-1,1]$)
- `phi = (imbalance + 1) / 2`  (диапазон $[0,1]$)

### 1.2 Интерпретация

- `phi > 0.5` → ASK > BID → sell pressure → bearish
- `phi < 0.5` → BID > ASK → buy pressure → bullish
- `phi = 0.5` → баланс

Контракт диапазона: `domains.feature_engineering.feature_sanity.feature_bounds.depth_imbalance: [0,1]` в [config/aurora/domains.yaml](../config/aurora/domains.yaml).

## 2) Wiring / dataflow

### 2.1 FE → features

`FeatureEngineering` пишет `features["depth_imbalance"]` как строку (phi) после перевода размеров в USD.

### 2.2 features → DecisionContext

`DecisionContext` забирает `depth_imbalance` из `features` в `ctx.liquidity.depth_imbalance` (дефолт `0.5` при отсутствии).

### 2.3 DecisionMaking → scoring

`decision_making` прокидывает `depth_imbalance` в `SignalScoreV2` как одну из phi-фич.

## 3) Config contract audit

### 3.1 Active config

- Global параметр сглаживания: `domains.feature_engineering.liquidity.depth_half` (float>0)
- Флаг: `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` (bool)

Оба параметра валидируются pydantic-моделями в [apps/reference/config_models.py](../apps/reference/config_models.py).

### 3.2 Пер-инструмент настройки

В активном SSOT по инструментам [config/aurora/instruments.yaml](../config/aurora/instruments.yaml) параметров для depth-imbalance нет; используется validated global default из domains.

#### 3.2.1 Матрица покрытия (active instruments)

Источник активных символов: `config/aurora/instruments.yaml`.

| symbol | has_depth_cfg | depth_half | smoothing | source | validation |
|---|---:|---:|---:|---|---|
| BTCUSDT | no | `domains.feature_engineering.liquidity.depth_half` | `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` | global | pass (pydantic) |
| ETHUSDT | no | `domains.feature_engineering.liquidity.depth_half` | `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` | global | pass (pydantic) |
| SOLUSDT | no | `domains.feature_engineering.liquidity.depth_half` | `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` | global | pass (pydantic) |
| DOGEUSDT | no | `domains.feature_engineering.liquidity.depth_half` | `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` | global | pass (pydantic) |
| XRPUSDT | no | `domains.feature_engineering.liquidity.depth_half` | `domains.feature_engineering.depth_imbalance.use_laplace_smoothing` | global | pass (pydantic) |

Архивный файл [config/aurora/archive/aurora_instruments.yaml](../config/aurora/archive/aurora_instruments.yaml) содержит исторические веса/параметры, но он не является SSOT для live.

## 4) Strategy usage map

### 4.1 Aurora (active)

- Feature neutral: `depth_imbalance: 0.5`
- Weight: **отрицательный** (sell pressure → отрицательный вклад в score)

Файл: [config/aurora/strategies/aurora.yaml](../config/aurora/strategies/aurora.yaml)

**Polarity contract (Aurora / ScoreV2 net-zero):**

| strategy | role | neutral | polarity | implementation |
|---|---|---:|---|---|
| aurora | score (dir component) | 0.5 | `phi>0.5` ⇒ SELL pressure ⇒ score ↓ | `weight(depth_imbalance) < 0` |

### 4.2 MeanReversion (active)

MeanReversion — bar-based BB/ATR/RSI стратегия и `depth_imbalance` **не использует** (ни в score, ни как gate). Это корректно, потому что MR работает на агрегированных барах и собственных индикаторах.

Файл: [config/aurora/strategies/mean_reversion.yaml](../config/aurora/strategies/mean_reversion.yaml)

### 4.2 Research/backtests

Есть несколько независимых (research) реализаций depth imbalance/phi в `apps/research/**`. Они не являются live SSOT, но потенциально могут вводить в заблуждение при сравнении семантики.

## 5) Tests added / updated

### 5.1 FE formula tests

Добавлен [tests/unit/feature_engineering/test_depth_imbalance.py](../tests/unit/feature_engineering/test_depth_imbalance.py):

- Монотонность/нейтраль: ask>>bid → phi>0.5, bid>>ask → phi<0.5, equal → 0.5
- Edge cases без smoothing: 0/0 → neutral, ask-only → 1, bid-only → 0

### 5.2 Scoring polarity test

Расширен [tests/unit/decision_making/test_signal_score_v2.py](../tests/unit/decision_making/test_signal_score_v2.py):

- Негативный вес + `phi>0.5` даёт отрицательный score
- Негативный вес + `phi<0.5` даёт положительный score

### 5.3 Test config parity

Обновлён [tests/config/aurora/trading.yaml](../tests/config/aurora/trading.yaml): `depth_imbalance` weight `0.15 → -0.15`.

### 5.4 Instruments contract test (C3)

Добавлен [tests/integration/test_depth_imbalance_config_contract.py](../tests/integration/test_depth_imbalance_config_contract.py):

- Подтверждает, что `instruments.yaml` не содержит per-symbol `depth_imbalance` (по контракту)
- Подтверждает, что global defaults существуют и валидированы через Pydantic (`depth_half>0`, `use_laplace_smoothing` bool)

### 5.5 Synthetic reachability test (C4)

Добавлен [tests/integration/test_depth_imbalance_reachability_buy_sell.py](../tests/integration/test_depth_imbalance_reachability_buy_sell.py):

- BUY case: `phi=0.30` + bullish -> достигается `EVT:TRADE_INTENT_PROPOSED` с `side=BUY`
- SELL case: `phi=0.70` + bearish -> достигается `EVT:TRADE_INTENT_PROPOSED` с `side=SELL`

## 6) Risk assessment

- Изменение live-логики: **нет**, если `use_laplace_smoothing=true` (дефолт). Формула остаётся прежней.
- При `use_laplace_smoothing=false`: поведение определено и протестировано для нулевых глубин (устраняем деление на ноль и дрейф к NaN).
- Наиболее критично: знак веса в стратегии должен соответствовать семантике `phi` (это уже исправлено в Aurora).
