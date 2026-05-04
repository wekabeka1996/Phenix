# MD-AMR Stage 3: Empirical Replay Audit

Цей аудит спирається на bar-level math-симуляцію ядра `MDAMRStrategyV11`, ізольовану від downstream execute/gateway lifecycle. 

## 1. Параметри тестування (Methodology)
- **Data Range & Symbols:** Агреговані сесії з `data/recorder/` для `XRPUSDT` та `BNBUSDT` (таймфрейм 15 хвилин). Загальний обсяг: ~7,000 барів.
- **Replay Modes:** 
  - `gross` (без витрат).
  - `net_config` (реалістичні комісії: fee=4.0 bps, slippage=2.0 bps, згідно `md_amr.yaml`).
  - `net_no_dampening` (вимкнений volatility dampening).
- **Caveats:** Реплей є "чистим strategy-truth", а не end-to-end exchange runtime. Канали `avg_high` / `avg_low` переобчислювалися динамічно (rolling channel), що відображає чесну поведінку порогів в часі. Оцінка прибутковості або загального PnL не є репрезентативною для production pipeline; мета симуляції — стрес-тест локальної логіки виходів стратегії.

---

## 2. Відповіді на ключові питання (TL;DR)

1. **Killswitch vs Scaleout:** Killswitch є абсолютно домінуючим (97.3% виходів). Scaleout дорівнює **0.0%**. Динамічний (rolling) канал не рятує позицію. Поточна exit semantics на tested surface майже повністю ламає mean-reversion monetization.
2. **Long / Short:** Проблема конфлікту абсорбції поширюється рівномірно на Long (96.6% killswitch) і Short (98.2% killswitch).
3. **Volatility Dampening:** Працює чітко як атенюатор ризику. Згладжує старші ваги (~0.35 -> ~0.25) під час високої волатильності, але загальний знак вектора розвертається винятково рідко (11 барів з 446 високоволатильних вікон).
4. **Pseudo-MTF:** Емпірик-check показав **0** аномально важких помилкових сигналів через одиничні старі спайки в нормальних умовах. Це концептуальна крихкість, яка на 15m `XRP/BNB` виявилася рідким edge case.
5. **Confidence:** `conf_ratio` математично завжди зводиться до константи (`1.0`) на момент пробиття `thr_buy`. Кореляція зі `score` неможлива (Pearson = NaN), оскільки змінна не несе нової вільної інформаційної мірності під час входу.
6. **Dead-Flat Chop:** Гіпотеза thin-band whipsawing залишається теоретично обґрунтованою (через відсутність хардкодної нижньої межі каналу окрім 1e-6), проте попередня статистика про 5.8% збиткових барів була артефактом збору даних. Потребує подальшого цільового стрес-тесту в ультра-вузьких смугах.

---

## Додаток A: Exit Outcome Matrix (MD_AMR_EXIT_OUTCOME_MATRIX)

Розподіл результатів для **Net Config Replay** (витрати 12 bps R-T включено):

| Metric | Total | Killswitch% (`EDGE_GONE`) | Scaleout% (`FEE_AWARE`) | Zombie% (`TIMEOUT`) |
| :--- | :--- | :--- | :--- | :--- |
| **All Trades** | 677 | **97.3%** | **0.0%** | 2.7% |
| **Long Side** | 348 | **96.6%** | **0.0%** | 3.4% |
| **Short Side** | 329 | **98.2%** | **0.0%** | 1.8% |

**З вимкненими комісіями (Gross Replay):**
Статистика абсолютно ідентична (97.3% Killswitch, 0.0% Scaleout). Це доводить, що нульовий scaleout є наслідком **математичного дефекту скорингу**, а не високих комісій. Сцена, де EDGE_GONE вимагає `conf_ratio < conf_min` (що гарантовано стається на вхідній межі), блокує дохід до центрального тейк-профіту.

### Наочні приклади (Killswitch Before Target Reach)
Усі 10 кейсів закрилися з мінімальним PnL через завчасний `EDGE_GONE`, так і не дочекавшись таргету.

`TOP 5 LONG KILLSWITCH CASES:`
1. **XRPUSDT** | Entry: 2026-02-10T05:59 | Exit: 2026-02-10T06:14 | Bars: 1 | PnL: +0.0100
2. **XRPUSDT** | Entry: 2026-02-10T08:29 | Exit: 2026-02-10T10:44 | Bars: 9 | PnL: -0.0069
3. **XRPUSDT** | Entry: 2026-02-10T12:44 | Exit: 2026-02-10T15:29 | Bars: 11 | PnL: -0.0059
4. **XRPUSDT** | Entry: 2026-02-10T16:44 | Exit: 2026-02-10T17:29 | Bars: 3 | PnL: +0.0056
5. **XRPUSDT** | Entry: 2026-02-10T20:29 | Exit: 2026-02-10T22:44 | Bars: 9 | PnL: -0.0014

`TOP 5 SHORT KILLSWITCH CASES:`
1. **XRPUSDT** | Entry: 2026-02-10T19:29 | Exit: 2026-02-10T20:14 | Bars: 3 | PnL: +0.0034
2. **BNBUSDT** | Entry: 2026-02-11T02:29 | Exit: 2026-02-11T08:14 | Bars: 4 | PnL: +0.0303
3. **BNBUSDT** | Entry: 2026-02-11T13:29 | Exit: 2026-02-11T15:14 | Bars: 7 | PnL: +0.0067
4. **XRPUSDT** | Entry: 2026-02-11T16:14 | Exit: 2026-02-11T16:44 | Bars: 2 | PnL: +0.0188
5. **XRPUSDT** | Entry: 2026-02-11T19:44 | Exit: 2026-02-11T21:59 | Bars: 9 | PnL: -0.0039

---

## Додаток B: Dampening Analysis (MD_AMR_DAMPENING_ANALYSIS)

Ми виокремили 446 барів з аномальною волатильністю (`atr_zscore > 2.20` на BNB та XRP):
- **Без Dampening (Counterfactual):** Середня вага для `D1` тренду складала `0.350`.
- **З Dampening:** Вага `D1` впала до `0.259` (HTF bias пригнічено).
- **Inverted Sign:** Лише у 11 з 446 випадків (2.4%) зсув ваги повністю розвернув кумулятивний bias з Лонгу на Шорт або навпаки.

**Висновок:** Волатиліті-дампінг не є шкідливим "суїцидальним ножів-кетчером". Він діє як плавний атенюатор, який дещо послаблює HTF, але не перемикає модель в сліпий моментум на повну міць.

---

## Додаток C: Pseudo-MTF Casebook (MD_AMR_PSEUDO_MTF_CASEBOOK)

Шукалися бари, де `d1/h1` slope має сильне відхилення через 1 старий тік:
- Випадків, де `abs(dir_comp_d1) > 0.9` при абсолютно стагнуючій (flat) тенденції SMA_96 (slope < 5bps): **0 випадків**.
**Висновок:** Через те, що 15-хвилинні дані достатньо щільні, point-to-point momentum статистично часто співпадає з реальною агресованою тенденцією. Хоча теоретично крихка, на практиці ця апроксимація майже не завдає збитків на цих парах.

---

## Додаток D: Confidence Correlation (MD_AMR_CONFIDENCE_CORRELATION)

Аналіз корелятивних метрик на момент входу (`entry_ts`):
- Pearsons *r* (`|dir_score|` vs `conf_ratio`): **NaN** (Array is constant).
- Spearmans *rho* (`|dir_score|` vs `conf_ratio`): **NaN** (Array is constant).

**Висновок:** Усі входи відбуваються за умови `score >= thr_buy`, що призводить до того, що `conf_ratio` масово затискається в `1.0` через обмеження `min(1.0, score / thr_buy)`. Отже, змінна `conf_ratio` емпірично не додає ніякої дисперсії чи нової інформаційної цінності на момент входу (вона ідеально плоска = 1). Гіпотеза 'Confidence is non-orthogonal' дуже правдоподібна, хоча для повної картини варто ще дослідити її поведінку на *впродовж* життя позиції.

---

## Додаток E: Фінальне Ранжування Ризиків (Final Ledger)

### 🔴 CONFIRMED EMPIRICALLY (Критичні баги математики)
1. **Killswitch vs Scaleout Conflict**
   - **Severity:** CRITICAL (P0)
   - **Frequency:** 97.3% simulated exits are preempted by Killswitch.
   - **Evidence:** 0.0% Scaleout reach rate across both Gross and Net; explicitly tracked in cases where the asset moves towards `avg_close` but inevitably spikes Killswitch at `avg_low`/`avg_high`.
   - **Operational Impact:** Стратегія систематично руйнує потенціал mean-reversion monetization.

### 🟡 WEAKENED EMPIRICALLY (Крихкощі, які не руйнують систему)
2. **Volatility Dampening Bias Redistribution**
   - **Evidence Strength:** Протестовано, але розвертає bias лише у ~2% серйозних випадків. 
   - **Operational Impact:** Прийнятний smoothing-mechanic, не вимагає негайного фіксу.
3. **Pseudo-MTF Fragility**
   - **Evidence Strength:** Небажаних патернів від старих спайків на `XRP/BNB` знайти не вдалося (0 випадків).
   - **Operational Impact:** Низький (Regular Nuisance).

### ⚪ STILL UNPROVEN / DELEGATED TO FURTHER RESEARCH
4. **Dead-Flat Chop Whipsawing**
   - Хоча математично вузька смуга є вразливою для шуму, попередні дані про 5.8% фейкових score-ів базувались на неправильно відлоггованій константі і підлягають скасуванню. Вимагає окремої таргетованої емпірики для підтвердження.
5. **Confidence Value during Hold**
   - На вході конфігурація тавтологічна (=1.0). Операційна цінність цієї метрики протягом життя позицій досі не доведена і підлягає ревізії.
