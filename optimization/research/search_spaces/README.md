# Search Spaces — Optuna Research Domain

Ця директорія містить YAML файли, що визначають **простір пошуку** параметрів для `SelectiveOptimizer`.

Кожен файл відповідає одній **групі ваг** Aurora системи, яку можна тюнити незалежно або у комбінації з іншими.

---

## Доступні групи

| Файл | Група | Шлях в конфізі | Параметри |
|------|-------|----------------|-----------|
| `btc_weights.yaml` | `btc_weights` | `aurora.assets.BTCUSDT.weights.*` | obi, tfi, delta_price, ema_bias, volume_spike, volatility_state, depth_imbalance, macro_resid, absorption |
| `eth_weights.yaml` | `eth_weights` | `aurora.assets.ETHUSDT.weights.*` | те ж (ETH bounds) |
| `sol_weights.yaml` | `sol_weights` | `aurora.assets.SOLUSDT.weights.*` | те ж (SOL bounds) |
| `global_signal_weights.yaml` | `global_signal_weights` | `aurora.decision.signal_weights.*` | ти ж (глобальний fallback для всіх символів) |
| `feature_neutrals.yaml` | `feature_neutrals` | `aurora.decision.feature_neutrals.*` | neutral baseline для кожного сигналу |
| `regime_knobs.yaml` | `regime_knobs` | `aurora.decision.regime_threshold_multipliers.*`, `signal_threshold`, `gates.*`, `liquidity_gate.*` | 11 параметрів режимних порогів |
| `risk_weights.yaml` | `risk_weights` | `risk_management.risk_score_weights.*`, `max_risk_score` | 6 параметрів ризик-скоринга |
| `pillar_weights.yaml` | `pillar_weights` | `feature_engineering.pillars.weights.*`, `*.sensitivity` | вага та чутливість Quadratic Brain Pillars |

---

## YAML формат

Кожен файл має дві секції:

```yaml
meta:
  description: "..."
  target_path_prefix: "aurora.assets.BTCUSDT.weights"
  symbol: BTCUSDT  # (optional)
  strategy: aurora # (optional)

search_space:
  aurora:
    assets:
      BTCUSDT:
        weights:
          obi:
            type: float
            low: 0.05
            high: 0.50
          # ... інші параметри
```

### Підтримувані типи параметрів

| type | required | optional |
|------|----------|---------|
| `float` | `low`, `high` | `step` |
| `int` | `low`, `high` | `step` |
| `categorical` | `choices` | — |

---

## Як додати нову групу

1. Створити новий `.yaml` файл за шаблоном вище
2. Зареєструвати у `optimization/research/weight_registry.py`:
   ```python
   _WEIGHT_GROUPS: Dict[str, str] = {
       ...
       "my_new_group": "my_new_group.yaml",  # ← додати сюди
   }
   ```
3. Використати в CLI або API:
   ```bash
   python scripts/run_research_optuna.py --search-space my_new_group
   ```

---

## Як overlay застосовується до конфігу

Dotted path з YAML (наприклад `aurora.assets.BTCUSDT.weights.obi`) розкладається у вкладений dict і передається в `ConfigLoader(optuna_overlay=...)`.

ConfigLoader застосовує overlay **після** завантаження всіх YAML файлів через `deep_merge()` з найвищим пріоритетом (рядок 432 `config_loader.py`).

Тому можна безпечно задавати будь-який параметр не змінюючи yaml файли.

---

## Ключова примітка (Символи та SSOT)

Список символів у `SelectiveOptimizer(symbols=[...])` передається в overlay як `trading.symbols_to_track`.

`apply_backtest_symbols_filter` (в `symbol_filter.py`) читає це поле і фільтрує `strategies_registry.assignments` до запитаного підмножини символів. Саме через це можна запустити повний backtest на **підмножині** символів без зміни `strategies.yaml`.
