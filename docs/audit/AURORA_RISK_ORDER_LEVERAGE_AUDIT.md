# 🧠 AURORA RISK, ORDER & LEVERAGE AUDIT (SSOT)

## Розділ 1 — Executive Summary

Даний аудит проведено для верифікації математичних розрахунків, механізмів побудови ордерів та використання конфігурацій (SSOT) в системі Aurora/Phenix. 

**Ключові висновки:**
*   **Реальність:** Система має розвинену багаторівневу систему гейтів (Risk, QoS, Exposure, Warmup) та гнучке позиційне сайзінг-ядро.
*   **Відсутність:** **Leverage та Margin Mode не є частиною торгового контракту** на рівні виконання (`fsm_open.py` / `AuroraAdapter`). Кредитне плече використовується лише локально в `ExposureGuard` для розрахунку маржинальних резервацій, але не передається на біржу.
*   **Системні дірки:** Відсутня синхронізація Margin Mode (Isolated/Cross) з біржею; налаштування плеча в `trading.yaml` є "декоративним" для виконання, хоча критичним для лімітів експозиції.
*   **Fail-Closed:** Принцип дотримується майже скрізь (якщо конфіг або дані відсутні — ордер блокується), за винятком `tpsl_math` (який інтегрований як логіка всередині FSM).

---

## Розділ 2 — Повна карта математики (SSOT)

| Layer | Formula / Rule | File:Line | Inputs | Config Keys | Fail-Closed? | Tests |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Risk** | `risk_score = Σ(feat_i * weight_i)` | `risk_management.py:292` | `delta_price`, `obi`, `tfi`, `absorption` | `domains.risk_management.risk_score_weights` | **YES** | `test_risk_thresholds` |
| **Daily Gate** | `dd = (1 - eq_now / eq_open) * 100` | `daily_gate.py:165` | `equity_free_usdt` | `trading.risk.daily.max_drawdown_pct` | **YES** | `DailyRiskState.can_open` |
| **Sizing (V2)** | `qty = (equity * pct) / price` | `decision_making.py:3092` | `equity`, `percent_equity` | `domains.decision_making.position_sizing.sizing.percent_equity` | **YES** | `_calculate_position_size` |
| **Exposure** | `util = (Σmargin) / equity` | `exposure_guard.py:525` | `marg_used`, `equity` | `trading.execution.exposure.max_equity_utilization_pct` | **YES** | `ExposureGuard.can_open` |
| **Rounding** | `qty = (qty // step) * step` | `fsm_open.py:209` | `qty`, `step_size` | `instruments[symbol].specs.step_size` | **YES** | `OpenFlowFSM.handle` |
| **TP/SL** | `dist = price * bps / 10000` | `fsm_manage.py` (internal) | `entry_price`, `bps` | `trading.execution.manage.brackets.sl.fixed_bps` | **NO** (defaults) | Manual verification |

---

## Розділ 3 — Order Construction Flow

1.  **Intent Generation** (`decision_making.py:666`): Формується `qty` (Decimal) на основі обраного режиму сайзінгу (SSOT: `domains.decision_making.position_sizing`).
2.  **Trade Proposing** (`decision_making.py:314`): Емітується `EVT:TRADE_INTENT_PROPOSED` з сирим Decimal qty.
3.  **Opening Guard** (`fsm_open.py:209`):
    *   Округлення `qty` до `step_size` (SSOT: `instruments.yaml`).
    *   Округлення `price` до `tick_size` (тільки для LIMIT).
4.  **Min Notional Check** (`fsm_open.py:243`): Перевірка `qty * price >= min_notional`.
5.  **DEC Emission** (`fsm_open.py:306`): Емітується `DEC:OPEN`.
6.  **Bridge Translation** (`AuroraBridge`): Конвертація Decimal в string для API запиту.

---

## Розділ 4 — Leverage & Margin: факт vs реальність

| Аспект | Binance вимагає | У коді Aurora | У конфігах | Ризик |
| :--- | :--- | :--- | :--- | :--- |
| **Leverage Setting** | `POST /fapi/v1/leverage` перед трейдом | **ВІДСУТНЄ**. Код ніколи не викликає API налаштування плеча. | `leverage_defaults` у `trading.yaml` | Misalignment між кодом (що думає 20x) та біржею (де може бути 125x). |
| **Margin Mode** | `POST /fapi/v1/marginType` (ISOLATED/CROSS) | **ВІДСУТНЄ**. Система працює в режимі, який виставлений на біржі вручну. | Відсутнє в SSOT. | Непередбачувана ліквідація "всього гаманця" при Cross, якщо планувався Isolated. |
| **Margin Control** | Maintenance Margin > Wallet Balance | Тільки локальна перевірка в `ExposureGuard` на основі `equity_free_usdt`. | `max_equity_utilization_pct` | Не враховується Funding та Unrealized PnL інших позицій біржею в момент `fsm_open`. |

---

## Розділ 5 — Виявлені розриви (GAPS)

1.  **GAP-LEV-01: No Remote Leverage Sync**
    *   **Evidence:** `fsm_open.py` та `AuroraBridge` не мають логіки для відправки команди `SET_LEVERAGE`.
    *   **Danger:** `ExposureGuard` дозволяє відкривати позиції, розраховуючи на 20x плече (менша маржа), а біржа може мати 5x (більша маржа), що призведе до `Insufficient Margin` помилки.
    *   **Блокує Live:** ТАК (ризик відхилення ордерів біржею).

2.  **GAP-MAR-01: Margin Mode Blindness**
    *   **Evidence:** У всій системі `execution_position` немає жодного згадування `Isolated/Cross`.
    *   **Danger:** Ризик каскадних ліквідацій.
    *   **Блокує Live:** НІ (але критично для безпеки капіталу).

3.  **GAP-MATH-01: Sizing vs Precision Conflict**
    *   **Evidence:** `DecisionMaking` розраховує `qty` без знання про `step_size`, а `fsm_open.py` округлює його пізніше.
    *   **Danger:** Розрахований `notional` може зменшитись після округлення нижче `min_notional` (особливо на маленьких депо).
    *   **Блокує Live:** ТАК (фіктивні відхилення ордерів).

---

## Розділ 6 — Обмеження аудиту

*   Агент не мав доступу до приватного API Binance для перевірки реальних лімітів акаунта (Account Tier).
*   Аудит проводився суто по статичному аналізу коду гілки `reference`.
*   Не перевірялися латентність мережі та реальні рейміти Binance (Rate Limits), що можуть впливати на QoS.

---
**Документ зафіксовано як SSOT для планування TASK47c+**
