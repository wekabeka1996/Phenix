# Звіт про прогрес: Калібрування та нові інсайти

Цей документ фіксує наші спільні знахідки та подальші кроки після детального аналізу структури даних `data/recorder`.

## 1. Підтвердження фільтрації warmup (ready=True)
Я перевірив код `tools/calibrate_aurora_signal_weights.py`. 
Скрипт **вже містить** правильну логіку фільтрації неповних даних (warmup):
```python
df = df[df["ready"] == True]
if "not_ready_reasons" in df.columns:
    reasons = df["not_ready_reasons"].fillna("").astype(str)
    df = df[reasons.str.len() == 0]
```
Він відкидає всі рядки, де `ready != True` або де є повідомлення у `not_ready_reasons`. Тобто ми гарантовано тренуємо регресію тільки на стабільних фічах без ефекту холодного старту.

## 2. Недооцінені фічі (pm_norm та інші)
Ти звернув увагу на критично важливу річ, яку я пропустив під час першого огляду колонок CSV. У нас є готові до використання фічі:
* `pm_norm`, `pm_raw`: Price momentum.
* `feat_absorption`, `feat_large_trade_imbalance`, `feat_spread_bps`, `feat_volume_zscore`: Нові мікроструктурні фічі.

**Що це означає на практиці?**
1. **Відродження MomentumAlphaModel:** Модель `MomentumAlphaModel` з сімейства Ensemble можна не замінювати на нову. Її можна просто переналаштувати на використання `pm_norm` (нормалізований ціновий моментум, розрахований на рівні Feature Engine). Це вирішує ще один шматок H1 проблеми!
2. **Нова Альфа в Ridge Regression:** Поточний конфіг `aurora.yaml` не знає про ці нові фічі. Якщо ми тимчасово додамо ці фічі (наприклад, `absorption`, `large_trade_imbalance`) у секцію `signal_weights` в `aurora.yaml` перед запуском калібрувального скрипту, Ridge-регресія оцінить їхній вплив. Якщо вони мають високу передбачувальну силу, ми отримаємо для них ненульові ваги і знайдемо нову Альфу!

## 3. Наступні кроки для виконання (Вимагає середовища Python)
Оскільки у мене наразі виникають помилки з `conpty.node` при спробі запустити Python через шелл, я не можу безпосередньо виконати скрипт. 

Що потрібно зробити (вам локально або як тільки шелл буде полагоджено):

**Дія А: Запуск калібрування з існуючими фічами**
```bash
# Калібрування для основних пар (horizon = 1 бар, тобто 5 хвилин)
python tools/calibrate_aurora_signal_weights.py --recorder-dir data/recorder --symbols BTCUSDT ETHUSDT SOLUSDT --tf-sec 300 --horizon-bars 1

# Калібрування для решти (DOGE, XRP)
python tools/calibrate_aurora_signal_weights.py --recorder-dir data/recorder --symbols DOGEUSDT XRPUSDT --tf-sec 300 --horizon-bars 1
```

**Дія B: Пошук нової Альфи (Ridge discovery)**
1. Тимчасово додати до `config/aurora/strategies/aurora.yaml` в секцію `aurora.decision.signal_weights` нульові ваги для нових фічей:
```yaml
      absorption: 0.0
      large_trade_imbalance: 0.0
      volume_zscore: 0.0
```
2. Запустити скрипт `calibrate_aurora_signal_weights.py` ще раз. 
3. Ridge регресія підбере оптимальні ваги для цих нових фічей. Якщо якась із них дасть стабільний PnL, ми впровадимо її в бойовий конфіг.

**Дія C: Реалізація коду (на моєму боці)**
Я готовий написати код для:
1. `MicrostructureReversionModel` (яка шукатиме відхилення в `ema_bias` та `macro_resid`).
2. Оновлення `MomentumAlphaModel` для використання `pm_norm`.
3. `OBIDivergenceModel`.

Чи можу я розпочати написання та інтеграцію цих нових/оновлених моделей у кодову базу?
