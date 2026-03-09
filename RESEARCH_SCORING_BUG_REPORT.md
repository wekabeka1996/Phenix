# Звіт: Дослідження багу скорингової системи (net_zero vs signed_v2)

## 1. Мета дослідження
Запит полягав у тому, щоб перевірити підозру щодо того, що система працює на хардкоді `net_zero` (як фолбек), а режим `signed_v2` насправді не реалізований або не працює під капотом. Мета — зрозуміти, чи дійсно працює скоринг, або ж це лише ілюзія.

## 2. Аналіз коду: де і як реалізовано `signed_v2`
Режим `signed_v2` **фізично реалізований** у коді. Логіка нормалізації описана у файлі `apps/reference/domains/decision_making/scoring_direction_strength_v1.py` у функції `_apply_signed_v2_transforms`:
- Для фічей з нейтральним значенням `0.5` (наприклад, `ema_bias`) вона розтягує значення, щоб центрувати їх у діапазоні `[-1, 1]`.
- Для фічей з нейтральним значенням `0.0` вона обрізає значення до діапазону `[-1, 1]`.

Сама функція `compute_direction_strength_score` має перевірку:
```python
    if normalize_mode == "signed_v2":
        features_eval = _apply_signed_v2_transforms(...)
    else:
        features_eval = features
```
Тобто, якщо передається `signed_v2`, нормалізація відбувається. Якщо передається щось інше, фічі йдуть далі у "сирому" вигляді (без жодних змін, що рівнозначно режиму `"off"`).

## 3. Корінь проблеми: хардкод `net_zero` у ядрі Aurora
Попри те, що `signed_v2` налаштовується у конфігурації (через `SignalsConfig.normalize_signals_mode` у `apps/reference/config_models.py`), ця конфігурація **ігнорується головним торговим ядром**.

У файлі `apps/reference/domains/decision_making/aurora_scoring_kernel.py`, який відповідає за прийняття рішень, виклик скорингової функції жорстко захардкоджений на `net_zero`:
```python
        # 4. Compute direction strength score
        ds_score = compute_direction_strength_score(
            features=v2_features,
            weights=signal_weights,
            neutrals=feature_neutrals,
            readiness=warmup_readiness,
            essential_features=essential_set,
            normalize_mode="net_zero", # <--- ОСЬ ТУТ ПРОБЛЕМА (ХАРДКОД)
            directional_features=list(direction_strength_cfg["directional_features"]),
            strength_features=list(direction_strength_cfg["strength_features"]),
            ...
        )
```

## 4. Наслідки для системи (чи працює скоринг?)
Оскільки ядро завжди передає `normalize_mode="net_zero"`, а функція `compute_direction_strength_score` не має обробки для значення `"net_zero"`, код завжди потрапляє у гілку `else`:
```python
    else:
        features_eval = features
```
**Що це означає:**
1. Значення `signed_v2` з конфігурації ніколи не доходить до ядра прийняття рішень під час реальної торгівлі/симуляції в `aurora_scoring_kernel.py`.
2. Всі вхідні фічі (сигнали) обробляються системою **без нормалізації** (у сирому вигляді).
3. Якщо скорингові моделі (ваги) та пороги розраховувались в аналітиці/бектестах з урахуванням того, що фічі будуть центровані від -1 до 1 (`signed_v2`), то в проді (через хардкод `net_zero`) скоринг отримує ненормалізовані дані (наприклад, від 0 до 1). Це призводить до **повністю спотвореного або хибного підсумкового балу (score)**.
4. Ваша підозра підтвердилася: система дійсно працює на фолбеці `net_zero`, який технічно вимикає будь-яку нормалізацію. `signed_v2` хоч і написаний в утилітах та тестах, у головному робочому циклі ядра не використовується.

## 5. Висновок
Скоринг під капотом працює **некоректно** (не так, як очікується конфігурацією). Він просто сумує сирі фічі, ігноруючи трансформації `signed_v2`. Я залишив код без змін згідно з вашим запитом, але для виправлення необхідно буде прибрати хардкод `normalize_mode="net_zero"` у `aurora_scoring_kernel.py` і прокинути туди значення з конфігурації `decision_cfg.signals.normalize_signals_mode`.
