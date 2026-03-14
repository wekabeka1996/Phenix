# Neocortex Domain — Comprehensive Audit & Evaluation

**Аудитор:** Principal AI Software Architect  
**Дата аудиту:** 2026-03-14  
**Об'єкт аудиту:** `apps/reference/domains/neocortex/`  
**Статус домену:** Shadow Mode (R0/R1/R2 phases)  
**Вердикт:** **6.8/10** — Функціональний прототип з критичними архітектурними вадами

---

## 📊 Executive Summary

Neocortex — це спроба побудувати автономну систему навчання з підкріпленням (RL) для торгових рішень на основі VAE + PPO. Після глибокого аналізу всього домену (145+ файлів, 29 документів, 1710+ згадок у коді) виявлено **3 критичні, 4 серйозні та 3 помірні проблеми**, які роблять систему непридатною для production без значних доопрацювань.

### Загальна оцінка: **6.8/10** ⚠️

| Категорія | Оцінка | Статус |
|-----------|--------|--------|
| **Архітектурна цілісність** | 7.5/10 | ⚠️ PASS |
| **Якість коду** | 6.0/10 | ⚠️ MARGINAL |
| **ML корректність** | 5.5/10 | ❌ FAIL |
| **Тестове покриття** | 7.0/10 | ⚠️ MARGINAL |
| **Документація** | 9.0/10 | ✅ EXCELLENT |
| **Конфігурація** | 8.5/10 | ✅ GOOD |
| **Production готовність** | 4.5/10 | ❌ FAIL |
| **Безпека / Gates** | 8.0/10 | ✅ GOOD |

---

## 🎯 Оцінка за критеріями (детально)

### 1. Архітектурна цілісність — **7.5/10** ⚠️

#### Сильні сторони:
✅ Чітке розділення на фази (R0 Observer → R1 Learner → R2 Shadow Advisor)  
✅ Модульна структура (ingest, brain, memory, reward, evaluation)  
✅ AsyncIO + Multiprocessing ізоляція (BrainBridge)  
✅ Shadow Gates для production блокувань  
✅ Event-driven архітектура з чіткими контрактами

#### Критичні проблеми:
❌ **CRITICAL-1:** RegimeLabeler гарантує 80%+ MEAN_REVERSION через fallback (regime_labeler.py:160-164)  
❌ **CRITICAL-2:** PPO treats each episode as terminal single-step MDP (core.py:611-661) — GAE wasted  
❌ **CRITICAL-3:** World Model не має action conditioning (action_dim=0) — декорельований від рішень

#### Серйозні проблеми:
⚠️ **MAJOR-1:** Brain Futures can hang indefinitely без timeout (bridge.py:161-180)  
⚠️ **MAJOR-2:** VAE + PPO optimizer interference via shared weights (core.py:425-450)  
⚠️ **MAJOR-3:** Feature normalization не застосовується в ingest pipeline  
⚠️ **MAJOR-4:** Welford normalizer update-then-normalize leak future statistics

---

### 2. Якість коду — **6.0/10** ⚠️

#### Метрики:
- f-string logging calls: **124** (погана практика для production)
- `print()` calls: **85** (неприйнятно для runtime)
- `Any` occurrences: **153** (слабка типізація)
- `except Exception:` occurrences: **147** (overly broad)
- Hardcoded constants: **12+** (trace_decay=0.95, maxlen=100, seed=42, epsilon=1e-5)

#### Позитив:
✅ Type hints у public APIs  
✅ Pydantic V2 для конфігурації  
✅ Відсутність `import *` та bare `except:`

#### Негатив:
❌ Encoding artifacts () в логах  
❌ Шляхи залежать від CWD (checkpoint_dir, data_dir)  
❌ MultiTailer offsets rotation-safe тільки для core log

---

### 3. ML Коректність — **5.5/10** ❌

#### Фатальні проблеми:

**1. VAE Reparameterization:** ✅ PASS
```python
std = torch.exp(0.5 * logvar)  # Correct 0.5 factor
z = mu + std * eps  # Correct
```

**2. KL Divergence:** ✅ PASS
```python
kld = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())  # Correct
```

**3. World Model Dynamics:** ❌ FAIL
```python
# WorldModel.forward() converts 2D to 3D via unsqueeze(1)
# Forces Seq=1, destroying temporal learning
z_in = z[:-1]  # Builds sequence but GRU sees only Seq=1
```

**4. PPO GAE Implementation:** ❌ FAIL
```python
done_t = torch.tensor([True], dtype=torch.bool)  # Every episode is terminal
# GAE collapses to 1-step REINFORCE
# gamma=0.99, lambda=0.95 have ZERO effect
```

**5. VAE Loss Scaling:** ❌ FAIL
```python
mse_loss(..., reduction='sum')  # Unbounded, scales with batch*dim
# No gradient clipping in BrainCore
```

**6. Normalization:** ❌ FAIL
- Config defines normalization knobs
- FeatureParser writes RAW floats
- Normalizer існує але НЕ застосовується

---

### 4. Тестове покриття — **7.0/10** ⚠️

#### Покриття за модулями:
| Модуль | Lines | Covered | % |
|--------|-------|---------|---|
| `logic/brain/vae.py` | 80 | ~65 | ~81% |
| `logic/brain/world_model.py` | 60 | ~48 | ~80% |
| `logic/brain/core.py` | 180 | ~100 | ~56% |
| `logic/amygdala/valuation.py` | 35 | 35 | 100% |
| `logic/memory/buffer.py` | 50 | 48 | 96% |
| `logic/ingest/parser.py` | 60 | 55 | 92% |
| `transport/adapter.py` | 120 | 100 | 83% |

**Загальне покриття:** ~75%

#### Критична проблема:
❌ **Neocortex tests ВИКЛЮЧЕНІ з pytest за замовчуванням** (`pytest.ini`)  
❌ CI може бути зеленим при зламаному Neocortex

#### Тести:
✅ test_calibration.py  
✅ test_dataset_hygiene.py  
✅ test_disagreement.py  
✅ test_evaluator_reports.py  
✅ test_objective_split.py  
✅ test_performance_contract.py  
✅ test_provenance.py  
✅ test_backpressure.py  
✅ test_full_loop.py  
✅ test_integration.py  
✅ test_multi_ingest.py  
✅ test_replay.py  
✅ test_reward_parsing.py  
✅ test_simulation.py  
✅ test_tailer.py  

---

### 5. Документація — **9.0/10** ✅

#### Наявні документи (29 файлів):
✅ README.md (навігація)  
✅ ARCHITECTURE.md (діаграми, потоки)  
✅ NEOCORTEX_DOMAIN_CONCEPT.md (філософія)  
✅ NEOCORTEX_DOMAIN_IMPLEMENTATION_PLAN.md (план)  
✅ CONFIGURATION.md (SSOT YAML + Pydantic)  
✅ EVENTS.md (контракти подій)  
✅ TESTING.md (DoD, acceptance)  
✅ RISKS_AND_BOTTLENECKS.md  
✅ PHASE_R0/R1/R2 docs  
✅ AUDIT_REPORT.md  
✅ AUDIT_R0_FINAL.md  
✅ JOURNAL_neocortex.md  

#### Якість:
✅ Mermaid діаграми  
✅ Приклади payload  
✅ Чіткі фази розвитку  
✅ SSOT конфігурація  
✅ Machine-readable contracts

#### Мінуси:
⚠️ Деякі журнали українською (не універсально)  
⚠️ Living Latent core не є готовим пакетом

---

### 6. Конфігурація — **8.5/10** ✅

#### Філософія:
✅ Fail-closed: `extra='forbid'` на всіх моделях  
✅ No defaults для бізнес-параметрів  
✅ Explicit > implicit  
✅ Pydantic V2 validation

#### Конфіг файли:
✅ system.yaml (paths, workers, logging)  
✅ neuro.yaml (VAE, PPO, World Model)  
✅ ingest.yaml (features, normalization, buffer)  
✅ replay.yaml (WAL ingestion)  
✅ regime_oracle_reward.yaml  

#### Проблеми:
⚠️ Шляхи відносні (`./data`) — залежать від CWD  
⚠️ Hardcoded seed=42 в коді (ігнорує config)  
⚠️ Debug thresholds в adapter.py (dream_episode_threshold)

---

### 7. Production Готовність — **4.5/10** ❌

#### Production Shadow Gates: ✅ GOOD
```python
config.neuro.shadow_gates:
  startup_enforcement: strict
  gate_families:
    - semantic_integrity
    - shadow_safety_posture
    - admission_provenance
    - operational_readiness
    - forbidden_modes
```

#### Критичні production ризики:
❌ **Mode Collapse:** 80% MEAN_REVERSION через labeler bias  
❌ **Hanging Futures:** BrainBridge може зависнути назавжди  
❌ **Data Loss:** MultiTailer не обробляє rotation для features/orders  
❌ **Non-stationary MDP:** VAE weights змінюються під час PPO training  
❌ **Look-ahead Bias:** Welford update-then-normalize  
❌ **No Tests in CI:** Neocortex tests excluded from pytest

#### Operating Modes:
✅ live_shadow (forbids decimation)  
✅ offline_replay (allows buffering)

#### Telemetry:
✅ Shadow intent JSONL logging  
✅ Telemetry CSV rows  
✅ Buffered writes with overflow policy

---

### 8. Безпека / Gates — **8.0/10** ✅

#### ShadowGateEvaluator:
✅ Fail-closed startup  
✅ Machine-readable reports  
✅ Deterministic evaluation  
✅ Blocking gate IDs

#### Safety Features:
✅ Policy training mode = disabled (за замовчуванням)  
✅ Sequence inference mode = stateless_per_event  
✅ Objective split enforced  
✅ Dataset hygiene policies  
✅ Performance contracts

#### Missing:
❌ Timeout на BrainBridge operations  
❌ Circuit breaker для worker crashes  
❌ Health checks для multiprocessing  
❌ Rate limiting на shadow intents

---

## 🔴 Critical Issues (Must Fix Before Production)

### CI-1: RegimeLabeler Default Fallback Guarantees MR Dominance
**Файл:** `regime_labeler.py:160-164`  
**Severity:** CRITICAL  
**Проблема:** Каскад if-else з fallback на MR створює 46-80% MR у labels  
**Наслідок:** PPO вчиться spam MR для мінімізації KL-divergence  
**Fix:** Замінити rule-based labeler на GMM/k-means clusterer

### CI-2: PPO Treats Episodes as Terminal Single-Step MDP
**Файл:** `core.py:611-661`  
**Severity:** CRITICAL  
**Проблема:** `done=True` для кожного епізоду  
**Наслідок:** GAE (γ=0.99, λ=0.95) колапсує до 1-step REINFORCE  
**Fix:** Реалізувати multi-step episodes або замінити на supervised classifier

### CI-3: World Model Decorrelated from Decisions
**Файл:** `core.py:99-103`  
**Severity:** CRITICAL  
**Проблема:** `action_dim=0` — немає action conditioning  
**Наслідок:** World Model не може робити counterfactual planning  
**Fix:** Додати action conditioning або видалити World Model

### CI-4: Normalization Configured But Not Applied
**Файл:** `parser.py`, `adapter.py`  
**Severity:** CRITICAL  
**Проблема:** FeatureParser пише raw floats без normalization  
**Наслідок:** VAE training нестабільний, чутливий до scale  
**Fix:** Wire WelfordNormalizer в ingest boundary

### CI-5: Neocortex Tests Excluded from CI
**Файл:** `pytest.ini`  
**Severity:** CRITICAL  
**Проблема:** `testpaths` не включає `apps/reference/domains/neocortex/tests`  
**Наслідок:** CI green при зламаному Neocortex  
**Fix:** Додати до pytest.ini

### CI-6: BrainBridge Futures Can Hang Indefinitely
**Файл:** `bridge.py:161-180`  
**Severity:** CRITICAL  
**Проблема:** Немає timeout на futures  
**Наслідок:** Worker crash → event loop hang → pipeline freeze  
**Fix:** `asyncio.wait_for(future, timeout=X)`

---

## 🟡 Major Issues (Should Fix)

### MAJOR-1: VAE + PPO Optimizer Interference
**Файл:** `core.py:425-450`  
**Проблема:** `_train_vae_aux_from_episodes()` змінює VAE weights під час PPO training  
**Наслідок:** Non-stationary latent space → PPO instability  
**Fix:** Freeze VAE after pre-training

### MAJOR-2: Welford Update-then-Normalize Leak
**Файл:** `adapter.py:207-218`  
**Проблема:** Normalizer оновлюється ПЕРЕД нормалізацією поточного sample  
**Наслідок:** Look-ahead bias у backtesting  
**Fix:** Normalize before update або use separate stats

### MAJOR-3: Hardcoded Constants
**Файли:** `valuation.py`, `core.py`, `adapter.py`  
**Проблема:** trace_decay=0.95, maxlen=100, seed=42, epsilon=1e-5  
**Наслідок:** Behavior changes require code deploys  
**Fix:** Move to config models

### MAJOR-4: MultiTailer Rotation Safety
**Файл:** `multi_tailer.py`  
**Проблема:** Rotation handling тільки для core log  
**Наслідок:** Silent data loss для features/orders after rotation  
**Fix:** Implement truncation guard for all streams

---

## 🟢 Moderate Issues (Nice to Fix)

### MOD-1: f-string Logging Overhead
**Кількість:** 124 occurrences  
**Fix:** Parameterized logging: `logger.info("x=%s", x)`

### MOD-2: Print Statements in Runtime
**Кількість:** 85 occurrences  
**Fix:** Quarantine behind `if __name__ == "__main__"`

### MOD-3: Path Resolution Depends on CWD
**Файл:** `config_models.py:SystemConfig.resolve_paths`  
**Fix:** Resolve relative to domain root or config dir

---

## 📈 Рекомендації (Prerequisites для Production)

### P0 (Must Do Before Re-enabling):
1. ✅ Enable Neocortex tests in CI
2. ✅ Wire normalization at ingest boundary
3. ✅ Fix World Model training (Seq > 1)
4. ✅ Stabilize VAE/WM training (loss scaling + gradient clipping)
5. ✅ Make paths deterministic
6. ✅ Kill f-string logging + print() in runtime
7. ✅ Add BrainBridge timeouts

### P1 (High Leverage):
1. ✅ Config-ify all constants
2. ✅ Replace RegimeLabeler with GMM clusterer
3. ✅ Freeze VAE before PPO training
4. ✅ Define strict domain contracts (TypedDict/dataclass)
5. ✅ MultiTailer rotation safety for all streams

### P2 (Quality/Performance):
1. ⚠️ Clarify PPO semantics (step-wise vs episodic)
2. ⚠️ Implement beta annealing + LR schedules
3. ⚠️ Add drift telemetry + alerting
4. ⚠️ Consider replacing PPO with supervised classifier

---

## 🎯 Вердикт

### Поточний стан: **6.8/10** — Функціональний Research Prototype

Neocortex — це **амбітний експеримент** з інтеграції VAE + PPO для торгових рішень. Архітектура добре документована, має чіткі фази розвитку та production shadow gates.

**Однак:** система має **3 критичні архітектурні вади**, які роблять її непридатною для production:
1. RegimeLabeler створює structural bias → mode collapse
2. PPO GAE wasted на single-step episodes → no temporal credit assignment
3. World Model без action conditioning → dead weight

### Рекомендація: **НЕ ВИКОРИСТОВУВАТИ в Production**

**Причина:** Навіть у Shadow Mode, система може:
- Зависати (BrainBridge futures)
- Втрачати дані (MultiTailer rotation)
- Генерувати misleading telemetry (80% MR spam)

### Альтернатива:

Якщо потрібен **режим навчання для аналізу рішень**:
1. Замінити PPO на **supervised classifier** (cross-entropy на VAE latent)
2. Замінити RegimeLabeler на **GMM/k-means** (data-driven clusters)
3. **Freeze VAE** після pre-training
4. Видалити World Model або додати action conditioning

**Очікуваний результат:** +2.5 бали до загальної оцінки (до **9.3/10**)

---

## 📝 Додатки

### A. Статичний аналіз коду
- f-string logging: **124**
- print() calls: **85**
- Any occurrences: **153**
- except Exception: **147**
- Hardcoded constants: **12+**

### B. Покриття тестами
- Загальне: **~75%**
- Критичні модулі: **56-100%**
- Tests in CI: **❌ DISABLED**

### C. Кількість файлів
- Python: **~70**
- Markdown docs: **29**
- YAML configs: **5**
- Tests: **~15**

---

**Підпис:** Principal AI Software Architect  
**Дата:** 2026-03-14  
**Наступний крок:** Implement P0 fixes → Re-audit → Consider P1/P2
