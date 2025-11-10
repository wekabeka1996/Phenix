# Остаточний план: Домен «Подієвої Впевненості» і заміна автозакриття позицій на основі ступеневої логіки

Мета: замінити поточну «поведінку автотрейдингу» керованим доменом впевненості, який приймає рішення про фіксацію прибутку (DEC:CLOSE ринком) на основі подієвого контексту, режиму та ризику, а біржові TP/SL використовуються як страхувальники (золотий стандарт безпеки).

---

## 1) Огляд поточної архітектури автотрейдингу (спрощена карта)

- Вхідні домени та події
  - `market_data` → `feature_engineering` → `risk_management` → `decision_making`
  - `decision_making` генерує `EVT:TRADE_INTENT_PROPOSED`, міст `AuroraBridge` вирішує коли конвертувати в `CMD:OPEN` (apps/reference/main.py:1).
- Домен виконання `execution_position` (ExecPosFSM)
  - Обгортка трьох FSM: `OpenFlowFSM` (apps/reference/domains/execution_position/fsm_open.py:1), `ManageFlowFSM` (apps/reference/domains/execution_position/fsm_manage.py:1), `CloseFlowFSM` (apps/reference/domains/execution_position/fsm_close.py:1).
  - Адаптер до біржі та допоміжні компоненти: `binance_execution_adapter.py`:1, `exposure_guard.py`:1, `watchdog.py`:1, `idempotent_cancel.py`:1, `metrics_*`.
- Поточні ролі
  - OpenFlow: гарди відкриття (кроки, мін. нотиціонал, cooldown), емісія `DEC:OPEN`.
  - ManageFlow: супровід позиції, стани TRACKING/BRACKETS_*, базові гачки для трейлінгу/BE/час‑стоп (стаби), взаємодія з TP/SL.
  - CloseFlow: прості правила закриття (час, REJECTED/EXPIRED), емісія `DEC:CLOSE`.
  - ExposureGuard: жорсткі й м’які ліміти (clip/reject), пост‑fill hold, анти‑гонки.
  - Контракти TP/SL: `contracts.py`:1 (валидації Binance: -2021, workingType, closePosition, тощо).
- Ризик (apps/reference/domains/risk_management/risk_management.py:1)
  - Обчислює параметри ризику, емісія `EVT:RISK_ASSESSMENT_COMPLETED` (risk_score, is_trading_allowed, добові ліміти, тощо).

Висновок: автозакриття зараз розподілене між ManageFlow (стаби) і CloseFlow (простий час/аварії). Заміну логіки «коли фіксувати прибуток» доречно сконцентрувати у новому домені «впевненості» й виразити через `DEC:CLOSE` з захистом SL/TP як страхувальниками.

---

## 2) Цільовий підхід: TP/SL як страховка, розумне закриття в коді

- Біржовий SL — завжди активний, консервативний, не чіпається доменом впевненості.
- Біржовий TP — за замовчуванням вимкнено або встановлений «аварійно далекий» (опційно), щоб уникнути OCO‑хореографії; фактичне фіксування прибутку робить система (`DEC:CLOSE` ринком із обмеженням проскальзування).
- Логіка прийняття рішення про фіксацію — у домені «confidence», на основі ступеневих порогів ROI у $ (1.20 → 2.20 → 3.20 …) та оцінки p_up на кожному порозі.

---

## 3) Новий домен: `confidence` (контракти, політика, сервіс)

Структура: `apps/reference/domains/confidence/`
- `contracts.py`
  - `ConfidenceEvaluationRequest` (Pydantic): position_id, symbol, side, entry_price, qty, roi_steps_usd: list[Decimal], current_step_idx, realized_roi_usd, unrealized_roi_usd, mark, local_high, drawdown_from_high_bps, regime, risk_score, alpha_conf, momentum, reward_events: dict, ts
  - `ConfidenceDecision` (Enum): HOLD_NOW | ADVANCE_STEP | CLOSE_NOW
  - `ConfidenceEvaluationResult`: p_up (0..1), threshold, decision, next_target_usd?: Decimal | None, valid_until_ts, why_code, features: dict
  - `StepPolicy`: пороги θᵢ, retrace_bps_cancel, max_hold_bars, timeout_ms, cooldown_ms
- `engine.py` — `ConfidenceEngine`
  - Отримує ознаки (alpha_conf, regime_conf, momentum, reward_event_pos/neg, risk_score, drawdown_from_high_bps)
  - rule‑based агрегатор: ваги з конфігу → `raw = Σ wᵢ xᵢ`, `p_up = σ(raw)` або clip лінійний; hard‑gate ризику/відкату
- `policy.py` — `SteppedRoiPolicy`
  - Визначає поточний ступінь Tᵢ за unrealized ROI; порівнює p_up з θᵢ; повертає рішення
- `service.py` — `ConfidenceService`
  - Тримає кеш стану по позиції, виконує evaluate(request), емісія `EVT:CONFIDENCE_EVALUATED`; надає синхронний API для FSM (`evaluate_sync` з таймаутом)
- `adapters/`
  - `reward_events_adapter.py` — читає інтенсивності з `alysha_core/reward_engine_v3plus/components/*` (див. §7)
  - `risk_adapter.py` — витягає risk_score/is_trading_allowed з останнього EVT risk
  - `regime_adapter.py` — дає regime_conf (TREND_UP/DOWN/MEAN_REVERSION/HIGH_VOLATILITY)
  - `pt_adapter.py` — ROI$, local_high, drawdown_from_high з position_tracking/PnL
- `logger.py` — окремий логгер/метрики (інкременти, latency, win‑rate ескалацій)

Контракт на виході (`ConfidenceAdvice`): action, p_up, threshold, next_target_usd?, why_code, features_dump — використовується ManageFlow для рішень.

---

## 4) Інтеграція з ExecPosFSM/ManageFlowFSM (акцент на «close by confidence»)

Точка інтеграції: `apps/reference/domains/execution_position/fsm_manage.py:1`
- У стабільних станах TRACKING/BRACKETS_PLACED при досягненні чергового порогу ROI Tᵢ:
  1) Формуємо `ConfidenceEvaluationRequest` з актуальними полями (через адаптери сервісу).
  2) Викликаємо `ConfidenceService.evaluate_sync(req, timeout_ms)`.
  3) Якщо `decision == ADVANCE_STEP` → продовжуємо утримувати позицію до Tᵢ₊₁ (біржовий TP не рухаємо).
  4) Якщо `decision == CLOSE_NOW` → ініціюємо `DEC:CLOSE` з `reduce_only=true` через CloseFlow/ExecPosFSM.
  5) Якщо таймаут/помилка → `EVT:CONFIDENCE_FALLBACK` і фолбек: не міняємо поведінку (SL як страховка).
- Безпечне закриття:
  - `atomic_close: true` (конфіг) — спочатку ідемпотентно скасувати відкриті SL/TP, потім закрити маркетом.
  - Контролювати проскальзування: `orders.market.slippage_cap_bps`.
- Ідемпотентність/WAL: `idempotent_key` з префіксом `CONF` та фіксація EVT у WAL.

Опційно: логування `EVT:CONFIDENCE_STEP_ADVANCED` при утриманні до Tᵢ₊₁ (для оцінки added value).

---

## 5) Взаємодія з доменом ризику (узгодження, уникнення конфліктів)

- Пріоритет/гейти:
  - `risk_management` надає `is_trading_allowed` і `risk_score` (жорсткий гейт). Якщо `is_trading_allowed = false` або `risk_score > risk_hard_gate.max_risk_score` — `ConfidenceEngine` повертає `HOLD_NOW` або `CLOSE_NOW` в залежності від політики «захистити прибуток» (конфігуровано; за замовчуванням — не ескалювати, можна закрити при значному відкаті).
  - Confidence не відкриває позицій; лише супроводжує відкриті. Таким чином прямого конфлікту із відкриттям/ризиком немає.
- Узгодження з ExposureGuard/soft‑limits: рішення CLOSE_NOW завжди дозволене (reduce_only), воно зменшує експозицію, тому з лімітами не конфліктує.
- Добові ліміти (max_daily_loss/drawdown): при спрацьовуванні — Confidence не ескалує і віддає CLOSE_NOW (завершує позиції).

---

## 6) Конфігурація (YAML) і фіча‑флаги

Файл: `config/aurora/trading.yaml:1`

Додати розділ:

```
trading:
  execution:
    manage:
      confidence_gate:
        enabled: false
        mode: shadow              # shadow|active
        steps_usd: [1.20, 2.20, 3.20]
        per_symbol_overrides: {}  # {SYMBOL: [..]}
        min_confidence:
          step_1: 0.60
          step_2: 0.70
          step_3: 0.80
        retrace_bps_cancel: 35
        max_hold_bars: 10
        timeout_ms: 150
        risk_hard_gate:
          max_risk_score: 0.85
        weights:
          alpha_conf: 0.35
          regime_conf: 0.20
          momentum: 0.15
          reward_event_pos: 0.15
          reward_event_neg: -0.25
      tp_insurance:
        enabled: false           # аварійний TP (за замовчуванням вимкнено)
        multiplier: 3.0          # від SL_bps, якщо вмикати
```

---

## 7) Повторне використання `alysha_core/reward_engine_v3plus` (як «ядро ознак»)

Використовуємо лише читання (read‑only) через адаптери:
- `alysha_core/reward_engine_v3plus/data_types.py` — структури даних (StateData, RewardComponentResult) — для типізації адаптера (за потреби — локальні лайти‑типи, щоб не тягнути зайве).
- `alysha_core/reward_engine_v3plus/components/event.py` — інтенсивності подій (позитивні/негативні): volatility_spike, volume_surge, regime_change, model_uncertainty, ARCE_ALERT…
- `alysha_core/reward_engine_v3plus/components/risk.py` — ризикові індикатори компонентного рівня (як ознаки, не як hard‑gate).
- `alysha_core/reward_engine_v3plus/components/risk_reward.py` — комбіновані метрики «risk‑reward» (за потреби як додаткові ознаки).
- `alysha_core/reward_engine_v3plus/normalizers.py` — нормалізація ознак (опційно, або свій простий scaler у `engine.py`).

Не використовуємо: `ppo_adapter.py`, `integration/*`, `tests/*` — щоб не ускладнювати залежності. Після стабілізації мінімальний піднабір переносимо в `confidence/adapters/` і видаляємо `reward_engine_v3plus` (окремим PR із регресійними тестами).

---

## 8) Контракти подій і JSON‑схеми

- Додати JSON‑схеми в `schemas/`:
  - `confidence_eval_request_v1.json` — схема запиту оцінки (EVT для журналювання/діагностики).
  - `confidence_evaluated_v1.json` — схема результату `EVT:CONFIDENCE_EVALUATED`.
  - `confidence_decision_v1.json` — схема внутрішнього рішення (action/threshold/p_up/targets).
- Узгодження з наявними `bracket_order_v1.json`, `bracket_error_v1.json`: нові схеми — незалежні; не ламаємо існуючі.

Мінімальні поля `confidence_evaluated_v1`:
- `position_id`, `symbol`, `roi_step_usd`, `current_step_idx`, `p_up`, `threshold`, `decision`, `next_target_usd?`, `why_code`, `ts`.

---

## 9) Логіка ухвалення рішення (детальна)

- Обчислення поточного ROI$ і кроку Tᵢ (відносно entry і qty; джерело — position_tracking/PnL).
- Формування ознак x:
  - `alpha_conf` (DecisionMaking або окремі моделі з `alpha_search`).
  - `regime_conf` (RegimeDetector): TREND_UP/DOWN/HV → унітарна оцінка 0..1.
  - `momentum` (короткий імпульс, нормалізований).
  - `reward_event_pos`/`neg` (адаптер до RE V3+ event component).
  - `risk_score` (RiskManagement) — hard‑gate/penalty.
  - `drawdown_from_high_bps` — штраф, якщо великий відкат.
- Агрегація: вагова сума → σ → `p_up`; якщо `risk_score > gate` → clamp p_up до 0..min(threshold-ε).
- Політика `StepPolicy`:
  - якщо `p_up ≥ θᵢ` → `ADVANCE_STEP` (не закривати, чекати Tᵢ₊₁)
  - якщо `p_up < θᵢ` → `CLOSE_NOW` (ринкове закриття з ідемпотентним скасуванням брекетів)
  - якщо `retrace_bps_cancel` перевищено → не ескалювати; при великому відкаті/ризику — `CLOSE_NOW`.
  - `max_hold_bars` обмежує кількість послідовних утримань на одному ступені.

---

## 10) Труднощі та рішення

- Біржові обмеження TP/SL (‑2021, workingType): використовуємо існуючі валідації з `contracts.py`:1 і `offset_bps`; SL — `MARK_PRICE` за замовчуванням.
- Відсутність справжнього OCO: `oco_emulation: true` + `atomic_close: true` — при CLOSE_NOW спочатку скасувати парні ордери, потім ринкове закриття; повторення безпечне завдяки idempotent cancel.
- Гонки/стани FSM: гейт викликаємо лише в TRACKING/BRACKETS_PLACED; в інших станах — дефер у коротку чергу або пропускаємо поки не стабілізується.
- Джерела даних відсутні/збій: таймаут evaluate → фолбек без змін; SL як страховка; логувати EVT:CONFIDENCE_FALLBACK.
- Надійність закриття ринком: обмежувати проскальзування (`slippage_cap_bps`), ретраї з backoff у адаптері; при багатьох збоях — optional emergency TP (як відкладений план).

---

## 11) Реалізаційні правила (coding guidelines)

- Fail‑closed: при помилках/таймаутах не міняти поведінку; завжди тримати SL.
- Ідемпотентність: всі DEC/EVT мають стабільний `idempotent_key` (префікс `CONF`).
- WAL/аудит: рішення домену впевненості логуються як EVT + breadcrumbs у `event_chain`.
- Жодних побічних ефектів у адаптерах (read‑only до інших доменів і RE V3+).
- Конфігурованість: всі пороги/ваги/кроки — у YAML, з overrides на символ.
- Тести перш ніж вмикати `mode=active`.

---

## 12) План робіт (фази, задачі)

Фаза A — ізоляція (shadow)
1. Створити `apps/reference/domains/confidence/` з файлами: `contracts.py`, `engine.py`, `policy.py`, `service.py`, `adapters/{reward_events_adapter.py, risk_adapter.py, regime_adapter.py, pt_adapter.py}`, `logger.py`.
2. Додати конфіг `trading.execution.manage.confidence_gate` у `config/aurora/trading.yaml:1` (enabled=false, mode=shadow).
3. Написати unit‑тести на `policy` (покриття варіантів θᵢ, retrace, max_hold_bars) і `engine` (агрегатор, hard‑gate, таймаут).
4. Додати EVT‑схеми у `schemas/` та валідатор схем у тестах.
5. Підключити `ConfidenceService` до ExecPosFSM як сервіс (без зміни поведінки): емісія тільки `EVT:CONFIDENCE_EVALUATED`.

Фаза B — інтеграція з ManageFlowFSM (flagged active)
1. Додати в `fsm_manage.py:1` хук `confidence_gate` у TRACKING/BRACKETS_PLACED перед діями з прибутком.
2. Якщо `enabled=true` і `mode=active` → виконувати CLOSE_NOW/ADVANCE_STEP; інакше — лише логувати.
3. Метрики/логи/EVT:CONFIDENCE_*; E2E тести з `simulated_adapter.py`:1 для сценаріїв: ескалація, відкат, ризик‑gate, таймаут.

Фаза C — стабілізація/міграція «ядра»
1. Зібрати статистику added value (avg_gain_from_advance, win‑rate ескалацій) на тестнет/реплеї.
2. Перенести мінімальний піднабір з `alysha_core/reward_engine_v3plus` у адаптери домену `confidence`; видалити `reward_engine_v3plus` (окремим PR).

---

## 13) DoD (Definition of Done)

- Код
  - Новий домен `confidence/` реалізований; API `ConfidenceService.evaluate_sync()` стабільний та покритий тестами.
  - Інтеграційний хук у `fsm_manage.py:1` активується фіче‑флагом; у shadow‑режимі не впливає на торги.
  - Жодних змін у SL‑контрактах/валідаціях — використовуються існуючі.
- Конфіг/Схеми
  - `trading.yaml` має `confidence_gate` і (опційно) `tp_insurance`; значення за замовчуванням — безпечні.
  - JSON‑схеми для EVT додані у `schemas/` і перевіряються в тестах.
- Тести
  - Unit‑тести: policy/engine/service (>=90% логіки); контрактні тести DTO.
  - Інтеграційні: симуляції з різними p_up/θᵢ/ризик/відкат; перевірка DEC:CLOSE і ідемпотентності.
  - Негативні: таймаути/порожні дані/високий risk_score → фолбек без побічних ефектів.
- Спостережуваність
  - Метрики evals/advances/fallbacks/latency; breadcrumbs у `event_chain`.
- Безпека
  - -2021 не відтворюється при оновленнях (TP не рухаємо); CLOSE_NOW використовує існуючі гарантії `atomic_close` + idempotent cancel; `slippage_cap_bps` налаштований.

---

## 14) Мапінг файлів/модулів (що чіпаємо і як)

- Нові файли: `apps/reference/domains/confidence/*`, `schemas/confidence_*.json`.
- Зміни мінімальні: `apps/reference/domains/execution_position/fsm_manage.py:1` (хук); `config/aurora/trading.yaml:1` (конфіг‑секція).
- Повторно використовуємо (read‑only):
  - `alysha_core/reward_engine_v3plus/components/{event.py,risk.py,risk_reward.py}`
  - `alysha_core/reward_engine_v3plus/{data_types.py,normalizers.py}` (опційно)
- Наявні адаптери/утиліти ExecPosFSM (не змінюємо логіку): `idempotent_cancel.py`:1, `watchdog.py`:1, `metrics_*`:1.

---

## 15) Зразки інтерфейсів (скорочено)

- ConfidenceEvaluationRequest
```
{
  "position_id": "uuid",
  "symbol": "ETHUSDT",
  "side": "LONG",
  "entry_price": "3450.00",
  "qty": "0.10",
  "roi_steps_usd": [1.20, 2.20, 3.20],
  "current_step_idx": 0,
  "unrealized_roi_usd": 1.25,
  "local_high": "3465.0",
  "drawdown_from_high_bps": 28,
  "regime": "TREND_UP",
  "risk_score": 0.42,
  "alpha_conf": 0.63,
  "momentum": 0.55,
  "reward_events": {"volume_surge": 0.7, "model_uncertainty": 0.1},
  "ts": 1730999999
}
```
- ConfidenceEvaluationResult
```
{
  "p_up": 0.67,
  "threshold": 0.60,
  "decision": "ADVANCE_STEP",
  "next_target_usd": 2.20,
  "why_code": "CONF_STEP_OK",
  "valid_until_ts": 1731000099,
  "features": {"alpha_conf": 0.63, "reward_event_pos": 0.7}
}
```

---

## 16) Порядок ввімкнення (safe rollout)

1) Shadow (логування лише) → 2) Active на testnet для одного символу → 3) Поступове розширення → 4) Оціночний період added value → 5) (опційно) аварійний TP, якщо потрібно → 6) Міграція ознак із RE V3+ і видалення зайвого коду.

---

Цей план враховує існуючі контракти/валидації, мінімізує ризик конфліктів з доменом ризику, забезпечує поетапну інтеграцію й чіткі критерії готовності (DoD) з тестовим покриттям і спостережуваністю.

---

## 17) Формальні DTO (Pydantic) і сигнатури сервісу

Типи та обмеження (скорочено; використати `pydantic.BaseModel`, Decimal):

```
from enum import Enum
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, List

class ConfidenceDecision(str, Enum):
    HOLD_NOW = "HOLD_NOW"
    ADVANCE_STEP = "ADVANCE_STEP"
    CLOSE_NOW = "CLOSE_NOW"

class StepPolicy(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    thresholds: List[Decimal] = Field(..., min_length=1, description="θ per step in [0,1]")
    retrace_bps_cancel: int = Field(35, ge=0, le=2000)
    max_hold_bars: int = Field(10, ge=0, le=1000)
    timeout_ms: int = Field(150, ge=10, le=5000)
    cooldown_ms: int = Field(0, ge=0, le=600000)

class ConfidenceEvaluationRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    position_id: str = Field(..., min_length=8, max_length=64)
    symbol: str = Field(..., min_length=3, max_length=20)
    side: str = Field(..., pattern=r"^(LONG|SHORT)$")
    entry_price: Decimal = Field(..., gt=Decimal("0"))
    qty: Decimal = Field(..., gt=Decimal("0"))
    roi_steps_usd: List[Decimal] = Field(..., min_length=1)
    current_step_idx: int = Field(..., ge=0)
    realized_roi_usd: Decimal = Field(default=Decimal("0"))
    unrealized_roi_usd: Decimal = Field(...)
    mark: Optional[Decimal] = Field(None, gt=Decimal("0"))
    local_high: Optional[Decimal] = Field(None, gt=Decimal("0"))
    drawdown_from_high_bps: int = Field(0, ge=0, le=10000)
    regime: Optional[str] = Field(None, description="TREND_UP|TREND_DOWN|...")
    risk_score: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("1"))
    alpha_conf: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("1"))
    momentum: Optional[Decimal] = Field(None, ge=Decimal("-1"), le=Decimal("1"))
    reward_events: Dict[str, Decimal] = Field(default_factory=dict)
    ts: int = Field(..., ge=0)

class ConfidenceEvaluationResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    p_up: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"))
    threshold: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"))
    decision: ConfidenceDecision
    next_target_usd: Optional[Decimal] = Field(None)
    valid_until_ts: Optional[int] = Field(None, ge=0)
    why_code: str = Field(..., min_length=1, max_length=64)
    features: Dict[str, Decimal] = Field(default_factory=dict)

class ConfidenceService:
    def evaluate_sync(self, req: ConfidenceEvaluationRequest, timeout_ms: int = 150) -> ConfidenceEvaluationResult: ...
    async def evaluate(self, req: ConfidenceEvaluationRequest) -> ConfidenceEvaluationResult: ...
```

Примітки:
- `momentum` нормалізується до [-1, 1] (див. §20); інші ознаки — [0,1].
- `thresholds` у `StepPolicy` відповідають крокам ROI; `current_step_idx` у межах `roi_steps_usd`.

---

## 18) JSON‑схеми імен подій/контрактів

Файли (створити у `schemas/`):
- `schemas/confidence_eval_request_v1.json`
- `schemas/confidence_evaluated_v1.json`
- `schemas/confidence_decision_v1.json`

Мінімальні версії схем:

```
// confidence_eval_request_v1.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ConfidenceEvaluationRequestV1",
  "type": "object",
  "required": ["position_id","symbol","side","entry_price","qty","roi_steps_usd","current_step_idx","unrealized_roi_usd","ts"],
  "properties": {
    "position_id": {"type": "string", "minLength": 8, "maxLength": 64},
    "symbol": {"type": "string", "minLength": 3, "maxLength": 20},
    "side": {"type": "string", "enum": ["LONG","SHORT"]},
    "entry_price": {"type": "string", "pattern": "^\\d+(\\.\\d+)?$"},
    "qty": {"type": "string", "pattern": "^\\d+(\\.\\d+)?$"},
    "roi_steps_usd": {"type": "array", "minItems": 1, "items": {"type": "number"}},
    "current_step_idx": {"type": "integer", "minimum": 0},
    "realized_roi_usd": {"type": "number"},
    "unrealized_roi_usd": {"type": "number"},
    "mark": {"type": ["string","null"], "pattern": "^\\d+(\\.\\d+)?$"},
    "local_high": {"type": ["string","null"], "pattern": "^\\d+(\\.\\d+)?$"},
    "drawdown_from_high_bps": {"type": "integer", "minimum": 0, "maximum": 10000},
    "regime": {"type": ["string","null"]},
    "risk_score": {"type": ["number","null"], "minimum": 0, "maximum": 1},
    "alpha_conf": {"type": ["number","null"], "minimum": 0, "maximum": 1},
    "momentum": {"type": ["number","null"], "minimum": -1, "maximum": 1},
    "reward_events": {"type": "object", "additionalProperties": {"type": "number"}},
    "ts": {"type": "integer", "minimum": 0}
  }
}
```

```
// confidence_evaluated_v1.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ConfidenceEvaluatedV1",
  "type": "object",
  "required": ["position_id","symbol","p_up","threshold","decision","ts"],
  "properties": {
    "position_id": {"type": "string"},
    "symbol": {"type": "string"},
    "roi_step_usd": {"type": ["number","null"]},
    "current_step_idx": {"type": ["integer","null"], "minimum": 0},
    "p_up": {"type": "number", "minimum": 0, "maximum": 1},
    "threshold": {"type": "number", "minimum": 0, "maximum": 1},
    "decision": {"type": "string", "enum": ["HOLD_NOW","ADVANCE_STEP","CLOSE_NOW"]},
    "next_target_usd": {"type": ["number","null"]},
    "why_code": {"type": ["string","null"]},
    "valid_until_ts": {"type": ["integer","null"], "minimum": 0},
    "features": {"type": "object", "additionalProperties": {"type": "number"}},
    "ts": {"type": "integer", "minimum": 0}
  }
}
```

```
// confidence_decision_v1.json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ConfidenceDecisionV1",
  "type": "object",
  "required": ["action","p_up","threshold"],
  "properties": {
    "action": {"type": "string", "enum": ["HOLD_NOW","ADVANCE_STEP","CLOSE_NOW"]},
    "p_up": {"type": "number", "minimum": 0, "maximum": 1},
    "threshold": {"type": "number", "minimum": 0, "maximum": 1},
    "next_target_usd": {"type": ["number","null"]},
    "why_code": {"type": ["string","null"]}
  }
}
```

Валідатори у тестах: використовувати `jsonschema`/`pydantic` для перевірки формату EVT.

---

## 19) Точний YAML‑патч до `config/aurora/trading.yaml`

```
trading:
  execution:
    manage:
      confidence_gate:
        enabled: false            # shadow за замовчуванням
        mode: shadow              # shadow|active
        steps_usd: [1.20, 2.20, 3.20]
        per_symbol_overrides:
          ETHUSDT:
            steps_usd: [1.00, 2.00, 3.00]
            min_confidence: { step_1: 0.55, step_2: 0.68, step_3: 0.78 }
            weights: { alpha_conf: 0.40, regime_conf: 0.20, momentum: 0.15, reward_event_pos: 0.15, reward_event_neg: -0.25 }
            retrace_bps_cancel: 30
            max_hold_bars: 12
        min_confidence: { step_1: 0.60, step_2: 0.70, step_3: 0.80 }
        retrace_bps_cancel: 35
        max_hold_bars: 10
        timeout_ms: 150
        risk_hard_gate: { max_risk_score: 0.85 }
        weights: { alpha_conf: 0.35, regime_conf: 0.20, momentum: 0.15, reward_event_pos: 0.15, reward_event_neg: -0.25 }
        sigmoid_k: 2.0           # чутливість σ (див. §20)
      tp_insurance:
        enabled: false
        multiplier: 3.0
```

---

## 20) Формула p_up: агрегація, нормалізація, штрафи

Ознаки (нормалізація):
- `alpha_conf ∈ [0,1]`, `regime_conf ∈ [0,1]`, `reward_event_pos/neg ∈ [0,1]`.
- `momentum ∈ [-1,1]`: `momentum = tanh(γ · r_t)`, де `r_t = (mark/mark_prev − 1)`, `γ ≈ 5` (конфігурований).
- `risk_score ∈ [0,1]`.

Агрегація (ваги з YAML):

```
raw = b
    + w_alpha * alpha_conf
    + w_regime * regime_conf
    + w_mom    * momentum
    + w_pos    * reward_event_pos
    + w_neg    * reward_event_neg   # w_neg < 0

p_up = clip( sigmoid(k * raw), 0.01, 0.99 )
```

де `sigmoid(x) = 1/(1+e^{-x})`, `k = sigmoid_k` (див. конфіг), `b=0` (за замовчуванням).

Штрафи/гейти:
- Якщо `risk_score > max_risk_score` → `p_up = min(p_up, θᵢ - 1e-3)` (деактивувати ескалацію на цьому ступені).
- Якщо `drawdown_from_high_bps ≥ retrace_bps_cancel` → `p_up = min(p_up, θᵢ - 1e-3)`; опційно додатковий множник `p_up *= 0.8`.
- Кепи: `p_up ∈ [0.01, 0.99]` для стабільності.

---

## 21) Точка ін’єкції у `fsm_manage.py` (стани, скелет коду)

Стан: викликати гейт у TRACKING/BRACKETS_PLACED на подіях `UPD:TICK|UPD:MARK_PRICE|EVT:FILL|EVT:PARTIAL_FILL` після оновлення PnL/портфелю.

Скелет:

```
# apps/reference/domains/execution_position/fsm_manage.py
class ManageFlowFSM:
    def __init__(...):
        self._conf_enabled = _cfg(["trading","execution","manage","confidence_gate","enabled"], False)
        self._conf_mode = _cfg(["trading","execution","manage","confidence_gate","mode"], "shadow")
        self._confidence_svc = ConfidenceService(...)

    def _maybe_confidence_gate(self, symbol: str) -> Optional[Message]:
        if not self._conf_enabled:
            return None
        # 1) Визначити ROI$ і Tᵢ з position state
        roi_usd = self._calc_unrealized_roi_usd(symbol)
        step_idx, step_val = self._detect_current_step(roi_usd)
        if step_idx is None:
            return None
        # 2) Зібрати ConfidenceEvaluationRequest (через адаптери)
        req = build_conf_req(symbol, step_idx, step_val, ...)
        res = self._confidence_svc.evaluate_sync(req, timeout_ms)
        emit("EVT:CONFIDENCE_EVALUATED", payload=to_json(res), why="CONF_EVAL")
        # 3) Рішення
        if self._conf_mode == "active" and res.decision == ConfidenceDecision.CLOSE_NOW:
            return Message(op="DEC", verb="CLOSE", pld={"reduce_only": True, "reason": "CONFIDENCE"}, idempotent_key=f"CONF_{symbol}_{step_idx}_{int(time.time()*1000)}")
        return None

    def handle(self, msg: Message) -> Optional[Message]:
        if self.state in (ManageState.TRACKING, ManageState.BRACKETS_PLACED):
            dec = self._maybe_confidence_gate(symbol)
            if dec:
                return dec
```

Фолбеки: при винятках/таймауті — логувати `EVT:CONFIDENCE_FALLBACK`, не емiтувати DEC.

---

## 22) Події, WAL‑поля та метрики

Події (EVT):
- `EVT:CONFIDENCE_EVAL_REQUEST` — опційно, для трейсингу вхідного запиту.
- `EVT:CONFIDENCE_EVALUATED` — результат оцінки (див. схему v1).
- `EVT:CONFIDENCE_STEP_ADVANCED` — утримання до Tᵢ₊₁.
- `EVT:CONFIDENCE_DEC_CLOSE` — емісія DEC через рішення CLOSE_NOW.
- `EVT:CONFIDENCE_FALLBACK` — таймаут/помилка/ризик‑gate.

WAL/WHY поля:
- `rid`, `corr_id`, `data_ref` (збереження ланцюжка), `idempotent_key` з патерном `CONF_{symbol}_{step}_{ts_ms}`.

Метрики (Prom‑стиль імена):
- `confidence_evals_total`
- `confidence_advances_total`
- `confidence_dec_closes_total`
- `confidence_fallbacks_total`
- `confidence_eval_latency_ms`
- `confidence_avg_gain_from_advance_usd` (обчислюється пост‑фактум)

---

## 23) Матриця тестів

Unit (policy/engine/service):
- Пороги θᵢ: p_up нижче/вище — HOLD/ADVANCE/CLOSE.
- Retrace: нижче/вище `retrace_bps_cancel`.
- Risk hard‑gate: `risk_score` <, =, > порога.
- Таймаут evaluate: повернення фолбек‑результату/виняток.
- Нормалізація momentum (tanh) і вплив `sigmoid_k`.

Інтеграційні (з `simulated_adapter.py`):
- Ескалація: T₁→T₂→… без закриття до останнього кроку.
- Відкат: на Tᵢ `p_up<θᵢ` → DEC:CLOSE; SL/TP не рухаються; atomic_close працює.
- Ризик‑gate: високий `risk_score` блокує ADVANCE; можливе CLOSE_NOW.
- Таймаут: сервіс не відповів → немає DEC; SL залишається.

Негативні/edge:
- Відсутні ознаки (alpha/regime/reward) → агрегатор працює з частковим вектором.
- Некоректні кроки ROI/індекси → без виклику гейта.
- Дублікати подій → ідемпотентність DEC (ключ `CONF_*`).

Фікстури:
- ROI генератор з кроками й випадковими відкатами.
- Заглушки адаптерів (risk/regime/reward_events/pt_adapter) з контрольованими значеннями.

---

## 24) Специфіка ідемпотентності

- Патерн ключа: `CONF_{position_id or symbol}_{step_idx}_{ts_ms}`.
- Повторні DEC:CLOSE з тим самим ключем поглинаються адаптером (див. idempotent_cancel).
- Всі EVT містять `rid`/`corr_id` для зв’язування рішень і дій.
