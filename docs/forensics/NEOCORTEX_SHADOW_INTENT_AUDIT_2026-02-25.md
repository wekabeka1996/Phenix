# Neocortex / Shadow Intents — Forensic Audit (2026-02-25)

## TL;DR

- **PPO (regime_oracle) policy is effectively using only 2/5 actions:** `MEAN_REVERSION` and `EXHAUSTION`.
- **This is not explained by label imbalance.** Oracle “ground-truth” regimes are fairly diverse (MR ~53%, the rest ~10–14% each).
- **VAE latent is the bottleneck:** the latest latent-space diagnosis shows **heavy overlap** between `MEAN_REVERSION`, `TREND_*`, and `HIGH_VOLATILITY`, while **`EXHAUSTION` is separable**.
- Result: the agent learns “**EXHAUSTION vs everything else**”, and maps everything else to **`MEAN_REVERSION`** (mode collapse to a safe attractor).

Key artifacts generated during this audit:

- `docs/forensics/neocortex_latent_report_2026-02-25.md`
- `docs/forensics/neocortex_latent_pca_2026-02-25.png`
- `docs/forensics/neocortex_latent_tsne_2026-02-25.png`
- `docs/forensics/neocortex_shadow_latent_pca_actions_2026-02-25.png`

---

## 1) Що таке “Neocortex” у цьому репо (коротко по факту)

Neocortex тут — це **shadow-mode автономний “brain”**:

- **Ingest**: читає фічі (`logs/features/*.log`) через `MultiTailer/WalTailer`.
- **Normalize**: online z-score (глобально або per-symbol).
- **VAE**: стискає 20 фіч → `z[16]` (перцепція).
- **World Model**: вчиться динаміці в латенті (predict `z_{t+1}`).
- **PPO**:
  - у режимі `reward_mode: regime_oracle` не торгує long/short, а **передбачає майбутній “реалізований режим”**.
  - дії (5): `TREND_UP`, `TREND_DOWN`, `MEAN_REVERSION`, `HIGH_VOLATILITY`, `EXHAUSTION`.
- **Oracle settlement**: кожні `horizon_bars=5` барів “закриває” найстаріший прогноз → обчислює `realized_regime` і `reward` → формує епізод для PPO update.

Ключове: **PPO бачить тільки `z`**, а не raw фічі/історію барів. Якщо `z` не розділяє режими — PPO практично не має шансів.

---

## 2) Джерела даних (що саме я проаналізував)

Станом на момент запуску аудиту були зчитані ротації:

- `logs/neocortex_metrics.csv`, `logs/neocortex_metrics.csv.1` … `.5`
- `data/shadow_intents.jsonl`, `data/shadow_intents.jsonl.1` … `.5`
- `logs/domain_regime_detector.log` (окремий Aurora-regime detector; див. розділ 6)

**Вікно telemetry (metrics CSV):** `2026-02-25 00:56:56 → 2026-02-25 03:01:08`  
(файли ротуются, тож це “ковзне вікно”, не історія за весь час)

---

## 3) Факти з `neocortex_metrics.csv*`: policy vs realized (oracle)

### 3.1 Shadow intents — як PPO вибирає дії

У вікні аналізу було:

- `shadow_intents`: **185,711**

Розподіл `shadow_action_name`:

| Action | Count | Share |
|---|---:|---:|
| MEAN_REVERSION | 150,758 | 81.2% |
| EXHAUSTION | 34,179 | 18.4% |
| TREND_UP | 347 | 0.19% |
| TREND_DOWN | 309 | 0.17% |
| HIGH_VOLATILITY | 118 | 0.06% |

Висновок: **майже повна відсутність `TREND_*` і `HIGH_VOLATILITY`** як дій політики.

### 3.2 Realized regimes — що реально “відбулося” за oracle-лейблером

`settlements`: **185,711** (практично 1:1 з intents)

Розподіл `realized_regime`:

| Realized | Count | Share |
|---|---:|---:|
| MEAN_REVERSION | 97,904 | 52.7% |
| HIGH_VOLATILITY | 25,409 | 13.7% |
| EXHAUSTION | 21,938 | 11.8% |
| TREND_UP | 20,158 | 10.9% |
| TREND_DOWN | 20,302 | 10.9% |

Це **не** “ринок 99% MR”. Є і тренди, і high-vol, і exhaustion — oracle їх ставить регулярно.

### 3.3 Confusion matrix (rows = realized, cols = predicted)

```
pred    0    1      2   3      4
real
0      72   56  18945  24   1061
1      50   51  19155  27   1019
2     161  130  92505  40   5068
3      31   29  19770   8   5571
4      33   43    386  19  21457
```

Де (індекси): `0=T_UP, 1=T_DOWN, 2=MR, 3=H_VOL, 4=EXHAUST`.

### 3.4 Per-class recall (найважливіше)

- `TREND_UP` recall: **0.36%**
- `TREND_DOWN` recall: **0.25%**
- `HIGH_VOLATILITY` recall: **0.03%**
- `MEAN_REVERSION` recall: **94.5%**
- `EXHAUSTION` recall: **97.8%**

Це і є “пояснення” твоєї інтуїції: **система майже ніколи не *використовує* `TREND_*` і `HIGH_VOL` як дії**, тому recall для них ≈0.

### 3.5 PPO “entropy” (ознака колапсу)

З telemetry:

- `ppo_entropy_mean`: **0.014**
- `ppo_entropy_p50`: **0.0004** (майже детермінізм)
- `ppo_entropy_p90`: **0.049**

Політика дуже швидко стає **майже детермінованою** → “закріплює” колапс.

---

## 4) Latent-space візуалізації і що вони кажуть

Я запустив `tools/diagnose_latent.py` (200k settled samples, VAE checkpoint_latest) і отримав:

- `docs/forensics/neocortex_latent_report_2026-02-25.md`  
- `docs/forensics/neocortex_latent_pca_2026-02-25.png`  
- `docs/forensics/neocortex_latent_tsne_2026-02-25.png`

Ключовий результат з репорту:

- **Crucial test (MR vs HIGH_VOL):** `distance=0.4957`, `MR RMS radius=1.2765`, `ratio=0.388` → **OVERLAP RISK = YES**
- **TREND_UP vs TREND_DOWN**: центроїди практично збігаються (`~0.02`).
- **EXHAUSTION**: центроїд дуже далеко від інших (`~3.0`), тобто **EXHAUSTION добре виділяється**.

Це дуже добре узгоджується з тим, що робить PPO:

- воно “бачить” exhaustion → тому prediction `EXHAUSTION` має дуже високий recall;
- решту класів latent майже не розділяє → PPO “зливає” все в `MEAN_REVERSION`.

Додатково (по shadow intents latents):

- `docs/forensics/neocortex_shadow_latent_pca_actions_2026-02-25.png`  
  Це PCA по `latent_state` з `shadow_intents.jsonl*`, кольори = **predicted action**. Фактично видно дві маси точок: MR та EXHAUSTION.

---

## 5) Чому “завжди MEAN_REVERSION” і що з цим робити

### Відповідь “що не так” (по факту з логів)

1. **Oracle каже, що режими різні (не тільки MR).**
2. **PPO майже не вибирає `TREND_*` і `HIGH_VOL`** (≈0.1–0.2% сумарно).
3. **VAE latent не відокремлює** MR / trend / high-vol у просторі `z` (overlap великий).
4. Тому PPO не може навчитися коректно розрізняти ці класи з `z` і фіксується на “двійці”:  
   - `EXHAUSTION` (бо separable)  
   - `MEAN_REVERSION` (fallback/majority для “всього іншого”)

### Це проблема VAE чи PPO?

- **Первинно — VAE/representation + state definition** (PPO не отримує достатньо інформації).
- **Вторинно — PPO optimization/exploration** (entropy дуже низька → колапс консервується).

І важливе уточнення: це **не** виглядає як “fallback always MR через error”, бо:

- у shadow intents присутні `EXHAUSTION` і рідкі інші класи,
- `ppo_entropy/ppo_loss_*` присутні у telemetry,
- “fallback-like intents” (confidence=0 & value=0) у вибірці не домінують.

---

## 6) Додатково: Aurora `RegimeDetector` ≠ Neocortex oracle-regimes

У репо є окремий `apps/reference/domains/regime_detector` (SMA/ATR heuristics) який емiтить `MEAN_REVERSION/TREND_*/LOW_VOL/HIGH_VOL/UNCERTAIN`.

Це **інша** підсистема, незалежна від neocortex PPO oracle-класифікатора.
За `logs/domain_regime_detector.log` вона часто перемикається між `UNCERTAIN` і `MEAN_REVERSION`, але це не пояснює колапс PPO по oracle-лейблам.

---

## 7) 10 гіпотетичних причин (і як їх швидко перевірити)

Нижче — **гіпотези** (частина з них уже частково підтверджується поточними артефактами), і **короткий “check”** для кожної.

1) **Representation bottleneck (підтверджується)**
   - Симптом: overlap MR vs HIGH_VOL, TREND_UP≈TREND_DOWN у `z`.
   - Check: `docs/forensics/neocortex_latent_report_2026-02-25.md` (ratio=0.388).

2) **PPO бачить лише “EXHAUSTION vs rest”**
   - Симптом: recall(EXHAUSTION)≈98%, recall(H_VOL/TREND)≈0.
   - Check: confusion matrix у цьому документі.

3) **Надто низька exploration після раннього етапу**
   - Симптом: `ppo_entropy_p50≈0.0004` (майже детермінізм).
   - Check: entropy time-series по `neocortex_metrics.csv*` (чи є “заморожування” ентропії).

4) **Reward-matrix має локальний “атрактор” MR+EXHAUST**
   - Симптом: політика приносить позитивний середній reward, але ігнорує класи.
   - Check: порівняти expected reward для “always MR/always EXHAUST” vs empirical (policy correlated).

5) **`class_weights` з YAML не застосовуються в matrix-mode**
   - Факт: у `RegimeRewardCalculator` class_weights застосовані лише у Formula A; при `reward_matrix_enabled=true` вони не впливають.
   - Check: `apps/reference/domains/neocortex/logic/reward/reward_calculator.py`.

6) **Oracle-labeler може бути “шумний” для TREND/H_VOL у твоєму домені**
   - Симптом: тренд визначається delta_pct + ema_centered; якщо ema_bias малоінформативний, TREND стане noisy.
   - Check: histogram `ema_bias-0.5` та `delta_pct` у settled dataset.

7) **Стан без історії (single-state) недостатній для режимів**
   - Симптом: режим часто є “патерном на вікні”, а PPO отримує один `z` без контексту.
   - Check: додати простий baseline з rolling features (або world_model hidden) і порівняти separability.

8) **Normalizer (per_symbol z-score) може знищувати абсолютні “режимні” масштаби**
   - Симптом: якщо режими залежать від абсолютного рівня, z-score вирівнює і стирає.
   - Check: спробувати encode без нормалізації або з robust scaling і подивитися на centroid distances.

9) **Проблема в самих фічах / їхній стабільності**
   - Симптом: `volatility_state` може saturate, або `delta_price` стає дуже малим після трансформацій/кліпів.
   - Check: sanity-діапазони фіч у `logs/features/*.log` vs очікувані (percentiles).

10) **Архітектура VAE (MLP) не вміє “витягнути” режимні інваріанти**
   - Симптом: reconstruction OK, але класи не separable.
   - Check: спробувати (а) contrastive objective, (б) supervised encoder, (в) temporal encoder (GRU/Transformer) хоча б для `mu`.

---

## 8) Практичний next-step (що робити далі, щоб “розморозити” TREND/H_VOL)

Найкорисніші (на мою думку) експерименти, які швидко дадуть відповідь “де вузьке місце”:

1) **Baseline-класифікатор без VAE**: train простий LogisticRegression/MLP на *raw feature vector* → `realized_regime`.
   - Якщо baseline працює (macro-F1 нормальний) → проблема у VAE/latent.
   - Якщо baseline теж не працює → проблема у labeler/фічах/доменної постановки.

2) **Дати PPO більше інфи**: concatenation `[z, raw(volatility_state), raw(delta_pct), raw(ema_centered)]` або коротка історія.

3) **Підняти/перезапустити exploration**: тимчасово зафіксувати `entropy_coef` вище, додати min-entropy floor або temperature.

4) **Перевірити/підкрутити oracle thresholds** під твої реальні діапазони (особливо `high_vol_threshold`, `trend_*`).

5) **Зробити VAE “бачущим”**: посилити `regime_aux` (частіше/сильніше), або перейти на більш supervised/perceptual objective.

