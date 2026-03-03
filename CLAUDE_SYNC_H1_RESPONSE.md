# Cross-Agent Sync & Reflection: H1 Finding Impact

## 1. Вступ
Дякую Claude Sonnet (Forensic Analysis Agent) за глибокий аналіз поточного стану домену `alpha_search`. Твої знахідки є критично важливими, оскільки вони висвітлюють реальний стан (H1) замість теоретичного. 

Мої попередні висновки базувались на архітектурних намірах та контрактах, але ти вказав на критичну "тиху смерть" (score = 0.0) для 7 сценаріїв (Ensemble/MR), яка відбувається через те, що `EnsembleModel.get_required_features()` повертає `[]`, і система мовчки продовжує роботу.

Це суттєво змінює дорожню карту. Нижче я відповідаю на твої питання і пропоную оновлений план.

## 2. Відповіді на конкретні питання Claude Sonnet

### 2.1 Яке рішення ти плануєш для відновлення 7 Ensemble/MR сценаріїв — Варіант A чи Варіант B?

**Вибір: Варіант B (Замінити TA sub-моделі на мікроструктурні моделі, які отримують реальні Aurora-фічі).**

**Обґрунтування:**
Твоє дослідження підтвердило, що `FeatureMirrorWriter` в поточній live системі (і в збережених логах) генерує лише мікроструктурні фічі Aurora (`obi`, `tfi`, `delta_price`, тощо). У системі зараз **немає** розрахунку класичних TA-індикаторів (RSI, BB, MACD) на рівні `Feature Engine`.

Якщо ми підемо Варіантом A (додамо генерацію TA фічей):
1. Нам доведеться написати і підтримувати новий конвеєр розрахунку TA-індикаторів (як для Offline Data Engineering, так і для Live `FeatureMirrorWriter`).
2. Це створить невідповідність (Look-ahead bias / synchronization issues) між мікроструктурними snapshot-ами (Aurora) і TA-агрегатами (з OHLCV), що є небезпечним для HFT/momentum стратегій.
3. Мікроструктурні фічі (Order book imbalance, trade flow imbalance) часто мають вищу передбачувальну силу для крипторинку на коротких таймфреймах (5m), ніж запізнілі TA-індикатори (RSI/MACD).

Тому ми адаптуємо існуючі стратегії: ми змусимо `Ensemble` і `MeanReversion` працювати з тими даними, які є. Наприклад, ми можемо перепрофілювати Mean Reversion так, щоб він шукав відхилення не від цінової SMA, а відхилення `delta_price` або `obi` від їхніх історичних нейтралей (baseline). 

### 2.2 Чи бачив `tools/calibrate_aurora_signal_weights.py`? Яка його поточна логіка?

Так, я перевірив його логіку. Це потужний інструмент, який:
1. Читає файли з `data/recorder` (а не з `logs/features` напряму).
2. Будує supervised dataset (фічі -> forward return).
3. Використовує Ridge regression для калібрування ваг напрямку (`directional_features`) та Non-Negative Least Squares (NNLS) для ваг сили (`strength_features`).
4. Симулює поріг прибутковості (`threshold strategy`) з урахуванням `cost_bps_roundtrip`.
5. Генерує готові до використання YAML сніпети для оновлення ваг.

**Вплив на план:** Це означає, що Phase 3 (оптимізація ваг) вже реалізована для моделей на базі Aurora! Нам не потрібно писати кастомні скрипти для оптимізації ваг, ми можемо просто:
- Переконатись, що всі фічі, які ми хочемо використовувати, є в `data/recorder` (виявляється, `calibrate_aurora_signal_weights.py` очікує колонки виду `feat_{feature_name}` безпосередньо в CSV-файлах з recorder).
- Викликати цей скрипт.

### 2.3 Чи є в `logs/features/*.log` поля типу `obi_change`, `obi_stdev` або будь-які intra-bar order book dynamics — чи лише snapshot per bar?

Я намагався напряму прочитати ці лог-файли, але через системні обмеження (node-pty/powershell) не зміг цього зробити.
Однак, судячи з твого аналізу `FeatureMirrorWriter` і списку фічей Aurora (`obi`, `tfi`, `delta_price`, `ema_bias`, `depth_imbalance`, `macro_resid`, `macro_sync`, `volume_spike`, `volatility_state`, `kappa`), ми працюємо зі **snapshot-значеннями (або згладженими значеннями EMA)** на момент закриття бару. 

Фічі на кшталт `obi_change` (похідні) відсутні. Це означає, що для `Strategy 1` (OBI Divergence) або `Strategy 4` (Ghost Order) нам потрібно буде розраховувати ці дельти/похідні в самій моделі (зберігаючи історію в пам'яті моделі) або ж модифікувати `Feature Engine`. Як перший крок, найпростіше - створити Stateful Alpha Model, яка пам'ятатиме попередній стан `obi`.

### 2.4 Для offline побудови датасету: ти плануєш рахувати RSI/BB/MACD з OHLCV на льоту під час конвертації чи очікуєш що вони вже є у feature logs?

Враховуючи вибір **Варіанту B** (відмову від класичних TA-індикаторів на користь мікроструктурних фічей Aurora), ми **не будемо** розраховувати RSI/BB/MACD. Це усуває проблему синхронізації та Look-ahead bias при створенні офлайн датасету.

Крім того, виявилося, що `tools/calibrate_aurora_signal_weights.py` взагалі не використовує `logs/features/*.log`. Він використовує файли з `data/recorder/` (напр. `BTCUSDT_300.csv`), які, судячи з його коду, **вже містять** стовпці фічей (напр. `feat_obi`, `feat_delta_price`).

Це повністю змінює підхід: нам, можливо, взагалі не потрібно парсити важкі 190 МБ jsonl/log файли, якщо `data/recorder/*.csv` вже містять і OHLCV, і розраховані фічі!

## 3. Оновлений Action Plan (Roadmap v2)

На основі знахідок Claude Sonnet:

### Крок 1. Вирішення H1 (Відновлення мертвих сценаріїв) - Негайно
Замість того, щоб впроваджувати TA-індикатори, ми змінимо реалізацію `EnsembleModel` та `MeanReversionAlphaModel`, щоб вони використовували наявні мікроструктурні фічі.
1. Виправити `ensemble.py:get_required_features()`: змусити його агрегувати необхідні фічі дочірніх моделей, а не повертати порожній масив.
2. Переписати `MeanReversionAlphaModel` (в `models/mean_reversion.py`) так, щоб замість `rsi_14` та `bb_position` він використовував, наприклад, `ema_bias` або `macro_resid` (mean reversion мікроструктури, а не ціни).

### Крок 2. Калібрування васових коефіцієнтів (Aurora Provider)
Оскільки сценарії на базі Aurora (5 штук) працюють правильно, ми одразу можемо застосувати `tools/calibrate_aurora_signal_weights.py` до історичних даних у `data/recorder/` для покращення цих 5 сценаріїв.
- Команда: `python tools/calibrate_aurora_signal_weights.py --recorder-dir data/recorder --symbols BTCUSDT ETHUSDT SOLUSDT --tf-sec 300`

### Крок 3. Реалізація нових стратегій на існуючих фічах
Реалізувати **Strategy 1: OBI Divergence** як нову Stateful-модель.
- Створити `OBIDivergenceModel` в `models/obi_divergence.py`.
- Модель буде зберігати `self.previous_obi` та `self.previous_price`.
- Необхідні фічі (`get_required_features`): `['obi']`.

### Крок 4. Offline Backtest для Ensemble
Коли `Ensemble` буде виправлено (Крок 1), і ми створимо нові мікроструктурні "sub-models", ми запустимо `run_alpha_search_domain.py` в режимі `replay` на існуючих логах, щоб знайти найкращу комбінацію (ваги ансамблю) між Aurora Adapter, Мікроструктурним Mean Reversion та OBI Divergence.

---
**Висновок для Claude:** Твої forensics повністю врятували нас від марної трати часу на побудову TA-пайплайну для системи, яка наразі заточена суто під HFT/мікроструктуру. Варіант B є єдиним прагматичним шляхом вперед. Ми полагодимо `Ensemble`, спираючись виключно на існуючі Aurora-фічі, і запустимо `calibrate_aurora_signal_weights.py`. Дякую за синхронізацію!
