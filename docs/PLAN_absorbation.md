# P1/P2: Повна інтеграція `absorption` у Decision + Risk (з калібруванням ваг)

## Короткий summary
FE-частина `absorption` вже готова (обчислення, SSOT-конфіг, тести, warmup-safe dedup). Далі потрібно:
1) **Підключити `absorption` у Aurora decision scoring** (schema + config + ваги + нейтраль + directional_features, включно з per-asset weights, бо вони override-ять global).  
2) **Інтегрувати absorption у RiskManagement** без semantic mismatch — через **toxicity proxy** (directionless): `toxicity = abs(tfi) * impact_norm(delta_price_pct)` і додати у risk_score під existing `use_absorption_penalty`.  
3) **Калібрувати вагу** (і за потреби `signal_threshold`) на історичних recorder-даних, з out-of-sample DoD.

---

## Важливі принципи/обмеження (SSOT + HITL)
- **HITL required** для:
  - будь-яких змін у `apps/reference/domains/risk_management/*` (Red Lines у `project_state_update.md`),
  - будь-яких змін `signal_weights` в production (`ALPHA_SEARCH_ROADMAP.md`).
- **No hardcoded params**: усі параметри нормалізації/капи — з конфігу або з already-SSOT параметрів.
- FE `absorption` лишається **SIGNED [-1, +1]**, neutral `0.0`.

---

## Семантика, яку реалізуємо (decision vs risk)
### Decision (Aurora scoring)
- Використовуємо існуючу FE-фічу `absorption` як **directional feature**:
  - `absorption > 0` → bullish (підтримує BUY)
  - `absorption < 0` → bearish (підтримує SELL)
  - `absorption = 0` → momentum/aligned або “no absorption signal”.

### Risk (RiskManagement)
- **Не використовуємо SIGNED `absorption` напряму**.  
- Вводимо **directionless “absorption toxicity proxy”** у risk_management:
  - `impact_norm = clip(delta_price_pct / absorption_dp_cap_pct, 0..1)`
  - `toxicity = abs(tfi) * impact_norm`  (0..1)
  - `risk += toxicity * weights.absorption_inverse` (під existing `use_absorption_penalty`)

Це:
- симетрично до знаку (BUY/SELL),
- не дає постійного штрафу при нейтралі (бо при `tfi≈0` → `toxicity≈0`),
- масштабується через конфіг `absorption_dp_cap_pct` (SSOT, без 0.02 у коді).

---

## Phase 1 — Decision: підключити `absorption` у Aurora scoring (schema + config + тести)

### 1.1. Schema зміни (Pydantic)
**Файли:**
- `apps/reference/config_models.py`

**Зміни:**
1) `class SignalWeights`:
- Додати поле `absorption: float = Field(default=0.0, description="R2 absorption (SIGNED [-1,1])")`
  - Чому default 0.0: backward compat; фіча “вмикається” тільки коли вага > 0 + readiness True.

2) `CANONICAL_WEIGHT_KEYS`:
- Додати `"absorption"` у set.
- Коментар: ключ має відповідати FE feature name (`features["absorption"]`).

### 1.2. Aurora config wiring (нейтралі + directional_features + ваги)
**Файли:**
- `config/aurora/strategies/aurora.yaml`

**Зміни:**
1) `aurora.decision.direction_strength_scoring.directional_features`:
- Додати `absorption`.

2) `aurora.decision.feature_neutrals`:
- Додати `absorption: 0.0`.

3) `aurora.decision.signal_weights`:
- Додати `absorption: <W_GLOBAL>` (див. Phase 2 про вибір).

4) Per-asset overrides (ВАЖЛИВО: override-ять global):
- Додати `absorption: <W_ETH/W_SOL/W_BTC>` у:
  - `aurora.assets.ETHUSDT.weights`
  - `aurora.assets.SOLUSDT.weights`
  - `aurora.assets.BTCUSDT.weights`

### 1.3. Alpha-search parity (щоб kernel-адаптер не відставав)
**Файл:**
- `apps/reference/domains/alpha_search/models/aurora_adapter.py`

**Зміни:**
- У `_FALLBACK_SIGNAL_WEIGHTS` додати `"absorption": 0.0` (або узгоджене з базовим профілем).
- У `_FALLBACK_FEATURE_NEUTRALS` додати `"absorption": 0.0`.
- У `_FALLBACK_DIRECTION_STRENGTH_CFG["directional_features"]` додати `"absorption"`.

### 1.4. Тести для decision/schema
**Файли (оновити):**
- `tests/config/test_task54_weight_key_validation.py`
  - Очікуваний set `CANONICAL_WEIGHT_KEYS` +1 ключ (`absorption`), len=10.
- `tests/unit/test_config_models_direct.py`
  - Переконатись, що `SignalWeights(...)` проходить з default `absorption` або додати явне поле в тесті.
- Додати/оновити тест, що `get_config()` вантажить `aurora.yaml`, і global/per-asset weights не містять неканонічних ключів (існуючі тести вже це перевіряють — оновити очікування).
- Додати тест, що `SignalScoreV2.validate_config` не кидає помилку, коли `absorption` має non-zero вагу і є у `feature_neutrals`.

**Команди:**
- `pytest -q tests/config/test_task54_weight_key_validation.py`
- `pytest -q tests/unit/test_config_models_direct.py`
- `pytest -q tests/unit/feature_integrity/test_r1r2_features.py`

**DoD Phase 1:**
- `get_config()` проходить strict validation.
- `AuroraHandler` бачить `absorption` у `signal_weights` (global і per-asset).
- Kernel не ігнорує absorption (бо є і в `directional_features`, і у weights, і в neutrals).

---

## Phase 2 — Калібрування ваги `absorption` + (опційно) `signal_threshold`

### 2.1. Зробити calibration tool придатним на старих recorder-даних (де `feat_absorption` = 0)
**Файл:**
- `tools/calibrate_aurora_signal_weights.py`

**Зміни:**
- У `_build_xy()` додати special-case для `feat == "absorption"`:
  - Якщо `feat_absorption` відсутній **або** має ~нульову дисперсію (наприклад `std < 1e-12`) → **перерахувати absorption** з:
    - `feat_tfi`, `feat_delta_price`, `close`
    - `dp_pct = feat_delta_price / close`
    - `dp_norm = clip(dp_pct / cfg.delta_price_cap_pct, -1..1)` *(використовуємо вже-SSOT `signals.delta_price_cap_pct` з aurora.yaml)*
    - `absorption_raw = -sign(tfi) * abs(tfi) * (1 - abs(dp_norm))` якщо `(tfi * dp_norm) < 0`, інакше `0.0`
    - clip до [-1,1].

> Це має збігатися з FE-формулою (без dedup), щоб tuning був еквівалентний production math.

### 2.2. Процедура вибору ваги (decision-complete rule)
1) Взяти recorder-дані за N днів (мінімум 2 дні, краще 7–14) для `BTCUSDT/ETHUSDT/SOLUSDT` на `tf_sec=300`.
2) Split:
   - Train: перші 70% дат (за днем)
   - Test: останні 30% дат
3) Для кожного символу прогнати калібрування + оцінку:
   - baseline vs calibrated (script вже це друкує)
4) Вибір ваги `absorption`:
   - Беремо калібровані ваги, якщо **на test**:
     - Sharpe не гірший за baseline,
     - total_pnl_bps не гірший за baseline,
     - trades не виростає > +25% (анти-churn constraint).
   - Якщо constraint порушено → clamp `absorption` у діапазоні `[0.03 .. 0.12]` і повторити оцінку grid-search по `absorption` (крок 0.01) з фіксованими іншими вагами.
5) `signal_threshold`:
   - Якщо trades падає занадто сильно/або виростає → робимо grid по threshold (наприклад 0.12..0.22 крок 0.01) і вибираємо той, що повертає trades у ±15% baseline при найкращому Sharpe.

**DoD Phase 2:**
- Є конкретні значення `W_ETH/W_SOL/W_BTC` і (за потреби) оновлений `signal_threshold` з test-результатами, які задовольняють constraints.

---

## Phase 3 — Risk: інтеграція toxicity proxy під `use_absorption_penalty` (HITL)

### 3.1. Додати SSOT параметр нормалізації impact у risk домен
**Файли:**
- `apps/reference/config_models.py`
- `config/aurora/domains.yaml`

**Зміни:**
1) У `RiskManagementDomainConfig` додати поле:
- `absorption_dp_cap_pct: Optional[float] = Field(default=None, gt=0.0, le=1.0, description="Cap for delta_price_pct normalization in toxicity penalty")`
2) Валідатор:
- якщо `use_absorption_penalty == True` → `absorption_dp_cap_pct` MUST be set, інакше `ValueError`.

3) У `config/aurora/domains.yaml` в секції `risk_management:` додати:
- `absorption_dp_cap_pct: 0.02`
- `use_absorption_penalty` лишити `false` за замовчуванням (активація тільки після HITL).

### 3.2. Заміна risk формули (тільки absorption-term)
**Файл:**
- `apps/reference/domains/risk_management/risk_management.py`

**Зміни:**
- Замість `(1 - absorption) * absorption_inverse_weight` використовувати:
  - `impact_norm = clip(delta_price_pct / absorption_dp_cap_pct, 0..1)` (тільки якщо penalty enabled)
  - `toxicity = abs(tfi) * impact_norm`
  - `+ toxicity * absorption_inverse_weight`

> Поле `features["absorption"]` можна залишити в parsing для backward compat/логів, але не використовувати у math.

### 3.3. Тести risk (обов’язково)
**Новий файл:**
- `tests/domains/risk_management/test_absorption_toxicity_penalty.py`

**Сценарії:**
1) `use_absorption_penalty=False` → toxicity term = 0, risk_score не змінюється.
2) `use_absorption_penalty=True`, `absorption_dp_cap_pct=0.02`:
   - sign-symmetry: `tfi=+0.8` і `tfi=-0.8` дають однаковий risk_score.
   - `delta_price=0` → penalty 0.
   - `tfi=0` → penalty 0.
   - `delta_price_pct >= cap` → `impact_norm=1`.
3) Валідація: `use_absorption_penalty=True` без `absorption_dp_cap_pct` → fail-fast (ValidationError/ValueError).

**Команди:**
- `pytest -q tests/domains/risk_management/test_absorption_toxicity_penalty.py`

**DoD Phase 3:**
- Risk penalty семантично узгоджений (directionless), bounded, без константного штрафу на нейтралі.
- Увімкнення penalty без SSOT cap — неможливе (fail-closed).

---

## Phase 4 — Rollout (production-safe, HITL)
1) **Ship (no-impact):**
   - `absorption.mode` можна лишити `disabled` (або `proxy`, але з вагою 0) до моменту включення.
   - `signal_weights.absorption = 0.0` (або відсутній → default 0.0).
   - `use_absorption_penalty=false`.
2) **Enable FE emission (no decision impact):**
   - `domains.yaml: absorption.mode = proxy`, але `signal_weights.absorption` все ще 0.0 → тільки збір даних.
3) **Enable decision weight (controlled):**
   - Виставити `absorption` ваги (global + ETH/SOL/BTC per-asset) за результатами Phase 2.
   - Підігнати `signal_threshold` за grid rule (Phase 2.2).
4) **Enable risk penalty (last):**
   - `use_absorption_penalty=true` + `absorption_dp_cap_pct` заданий.
   - Спочатку в shadow/обмеженому середовищі, потім production.

---

## Публічні зміни інтерфейсів/контрактів
- `SignalWeights` (Pydantic) отримує новий ключ `absorption` (default 0.0).
- `CANONICAL_WEIGHT_KEYS` розширюється ключем `absorption`.
- `RiskManagementDomainConfig` отримує `absorption_dp_cap_pct` (optional; required when `use_absorption_penalty=true`).
- Risk absorption-penalty семантика змінюється на `toxicity` (directionless proxy).

---

## Загальний DoD (повністю)
- Config strict-load (`get_config()`) проходить.
- Aurora scoring реально враховує `absorption` при mode!=disabled + weight>0.
- Calibration tool здатен згенерувати корисний `absorption` навіть якщо recorder писав нулі (ретро-аналіз).
- Risk toxicity penalty працює, симетричний до знаку, bounded, без “постійного +weight” на нейтралі.
- Всі тести з чекліста проходять.
- Є зафіксовані значення `absorption` ваг і (за потреби) `signal_threshold`, отримані за чітким out-of-sample правилом.
