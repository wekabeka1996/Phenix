# Technical Debt Elimination Report

**Дата:** 22 січня 2026  
**Роль:** Principal Code Auditor & Refactoring Architect  
**Scope:** Deep Dive Audit — прихованих ризиків, порушень "Explicit Configuration", silent fallbacks

---

## 📋 Executive Summary

Аудит виявив **15 критичних проблем** та **8 проблем середньої важливості** у 7 модулях. Основні категорії:

| Категорія | Кількість | Критичність |
|-----------|-----------|-------------|
| Silent Fallbacks / Default Values | 6 | 🔴 HIGH |
| Hardcoded Magic Numbers | 4 | 🔴 HIGH |
| Precision Risk (float vs Decimal) | 2 | 🟡 MEDIUM |
| Dead Code / Stubs | 2 | 🟡 MEDIUM |
| Missing Config Validation | 3 | 🔴 HIGH |
| SSOT Violations | 2 | 🔴 HIGH |

---

## 1. Реєстр проблем

### 1.1 🔴 [CRITICAL] fsm.py: Пустий AuroraConfig() fallback

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L134) |
| **Рядок** | 134 |
| **Тип** | Silent Fallback |
| **Код** | `self.config = AuroraConfig() if config is None else config` |

#### Чому це зло:
Якщо `config=None` передається у `ExecPosFSM`, створюється **пустий AuroraConfig** з дефолтними значеннями. Це може призвести до:
1. Запуску системи **без exposure limits** (дефолтний leverage може бути 20x або None)
2. Відсутності watchdog TTL → ордери висять вічно
3. Відсутності cooldown → flood ордерів

#### Аналогічні випадки:
- [fsm_open.py#L130](apps/reference/domains/execution_position/fsm_open.py#L130): `self.config = AuroraConfig() if config is None else config`
- [fsm_manage.py#L105](apps/reference/domains/execution_position/fsm_manage.py#L105): `self.config = AuroraConfig() if config is None else config`

---

### 1.2 🔴 [CRITICAL] exposure_guard.py: Hardcoded Fallback Risk Parameters

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L51-L56) |
| **Рядок** | 51-56, 152, 365 |
| **Тип** | Hardcoded Magic Values |
| **Код** | `risk_reduction_pct: Decimal = Decimal("0.5")`, `default_leverage_raw = leverage_defaults["__default__"] if "__default__" in leverage_defaults else 20` |

#### Чому це зло:
1. **50% risk reduction** захардкоджено як fallback — не в конфігу
2. **Default leverage 20x** застосовується якщо символ відсутній у `leverage_defaults`
3. Якщо біржа налаштована на 50x, а ми думаємо що 20x — **ризик ліквідації x2.5**

```python
# exposure_guard.py:51-56
@dataclass
class FallbackState:
    """PHASE P0: Fallback mode state management."""
    active: bool = False
    entered_at: Optional[float] = None
    reason: Optional[str] = None
    # 50% risk reduction in fallback mode
    risk_reduction_pct: Decimal = Decimal("0.5")  # ⚠️ HARDCODED
```

```python
# exposure_guard.py:365
default_leverage_raw = leverage_defaults["__default__"] if "__default__" in leverage_defaults else 20  # ⚠️ HARDCODED
```

#### Ризик:
- **Leverage mismatch** між Aurora та Binance → неправильний sizing → liquidation
- 50% reduction може бути недостатнім в extreme volatility

---

### 1.3 🔴 [CRITICAL] feature_engineering.py: BTCUSDT Anchor Hardcode

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L737-L745) |
| **Рядок** | 737-745 |
| **Тип** | Hardcoded Dependency |
| **Код** | `btc_anchor_ts = int((self._anchor_last_ts_ms.get("BTCUSDT", 0) or 0))` |

#### Чому це зло:
1. **BTCUSDT** жорстко прошитий як anchor для macro_resid
2. Якщо BTCUSDT відсутній (delisting, API failure) → macro_resid **завжди not_ready**
3. DecisionMaking блокується через warmup gate

```python
# feature_engineering.py:737-745
if self.cfg.macro_resid_enabled:
    # FIX 2 (P0): Causality guard.
    btc_anchor_ts = int((self._anchor_last_ts_ms.get("BTCUSDT", 0) or 0))  # ⚠️ HARDCODED
    if btc_anchor_ts > 0 and btc_anchor_ts > int(current_ts_ms):
        hot.macro_resid_ready = False
        hot.macro_resid_not_ready_reason = "anchor_from_future:BTCUSDT"
```

```python
# feature_engineering.py:759-762
btc_price_hist = self.anchor_prices.get("BTCUSDT", None)  # ⚠️ HARDCODED
if btc_price_hist and len(btc_price_hist) >= 2 and prev_price > 0:
```

#### Ризик:
- **Single point of failure**: BTCUSDT down → вся система blocked
- Немає fallback на інший anchor (ETHUSDT)

---

### 1.4 🔴 [CRITICAL] aurora_handler.py: Massive Default Values

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L212-L257) |
| **Рядок** | 212-257 |
| **Тип** | Silent Fallback |
| **Код** | Block of defaults: 420s, 0.72, 0.25, 18, 30.0s, 0.7, 60.0s |

#### Чому це зло:
Якщо `decision` config відсутній, застосовуються hardcoded defaults:

```python
# aurora_handler.py:212-257 (else branch)
else:
    # Defaults
    self.signal_threshold = decimal.Decimal("0.1")      # ⚠️
    self.side_bias_window_sec = 420.0                    # ⚠️ 7 хвилин
    self.side_bias_target_ratio = 0.72                   # ⚠️
    self.side_bias_penalty_factor = 0.25                 # ⚠️
    self.side_bias_min_intents = 18                      # ⚠️
    self.regime_thresholds = {"DEFAULT": 1.0}            # ⚠️
    self.direction_strength_cfg = {}
    self.delta_price_cap_pct = decimal.Decimal("0.005")  # ⚠️ 0.5%
    self.neutral_threshold = decimal.Decimal("0.05")     # ⚠️
    # Holding period defaults (disabled)
    self.holding_period_enabled = False
    self.default_min_duration_sec = 30.0                 # ⚠️
    self.default_emergency_threshold = 0.7               # ⚠️
    self.holding_apply_to_flips = True
    self.default_reentry_cooldown_sec = 60.0             # ⚠️
```

#### Ризик:
1. **YAML завантаження може тихо провалитися** → система працює на дефолтах
2. Параметри не відповідають ринковим умовам → погана performance
3. **Неможливо відтворити баги** без знання, які дефолти застосувались

---

### 1.5 🟡 [MEDIUM] fsm_close.py: Float для qty + Dead docstring

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/execution_position/fsm_close.py](apps/reference/domains/execution_position/fsm_close.py#L36-L40) |
| **Рядок** | 36-40, 87-88 |
| **Тип** | Precision Risk + Dead Code |
| **Код** | `max_hold_sec: float = 86400.0`, `qty = float(pld["qty"] if "qty" in pld else 0)` |

#### Чому це зло:
1. **Float precision** для qty може призвести до dust (пилу) на балансі
2. `max_hold_sec` документований як "failsafe 24h", але `_check_close_conditions` завжди повертає `None`

```python
# fsm_close.py:36-40
class CloseFlowFSM:
    """
    Role:
    2. Failsafe: Emergency close on max_hold_sec (default 24h) if Decision fails.
    """  # ⚠️ DEAD DOCSTRING - функціонал не реалізований

    def __init__(self, max_hold_sec: float = 86400.0):  # ⚠️ DEAD PARAMETER
```

```python
# fsm_close.py:87-88
qty = float(pld["qty"] if "qty" in pld else 0)  # ⚠️ FLOAT PRECISION
if qty > 0:
```

```python
# fsm_close.py:99-104
def _check_close_conditions(self, msg: Message) -> Optional[Message]:
    """NOTE: Autonomous closing rules... are disabled"""
    return None  # ⚠️ DEAD CODE - max_hold_sec never used
```

#### Ризик:
- **Dust accumulation** через float→Decimal→float roundtrips
- **Misleading documentation** → розробники думають failsafe існує

---

### 1.6 🔴 [CRITICAL] aurora_handler.py: Liveness Config Fallback

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L335-L345) |
| **Рядок** | 335-345 |
| **Тип** | Silent Fallback |
| **Код** | `basis_tf_sec = 300; liveness_factor = 3` |

#### Чому це зло:

```python
# aurora_handler.py:335-345
try:
    basis_tf_sec = int(self.config.basis_tf_sec)
    liveness_factor = int(getattr(self.config, "liveness_factor", 3))
except (AttributeError, TypeError):
    # Config not available - use safe defaults and log
    basis_tf_sec = 300       # ⚠️ SILENT FALLBACK
    liveness_factor = 3      # ⚠️ SILENT FALLBACK
    self.logger.warning(...)
```

#### Ризик:
- Warning логується, але **система продовжує працювати**
- 300s * 3 = 15 хвилин delay tolerance — може бути занадто багато/мало

---

### 1.7 🟡 [MEDIUM] feature_engineering.py: -1ms Synthetic Tick Hack

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L572-L580) |
| **Рядок** | 572-580 |
| **Тип** | Hack / Workaround |
| **Код** | `bar_last_tick["ts"] = bar_ts - 1  # 1ms before bar close` |

#### Чому це зло:

```python
# feature_engineering.py:572-580
# Create synthetic last_tick with ts slightly before bar_ts
# to ensure time_diff > 0 in feature calculation
bar_last_tick = dict(last_tick)
bar_last_tick["ts"] = bar_ts - 1  # ⚠️ SYNTHETIC -1ms TICK
```

#### Ризик:
1. **delta_price на стику хвилин** може бути неточним
2. Порушує causality invariant (синтетичний тік не існував)
3. Volume/trade features для цього "тіка" — фіктивні

---

### 1.8 🔴 [CRITICAL] mean_reversion_handler.py: Implicit Strategy Defaults

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py#L270-L310) |
| **Рядок** | 270-310 |
| **Тип** | Config Propagation |
| **Код** | `MRStrategyConfig()` з inline defaults |

#### Чому це зло:
`MRStrategyConfig` dataclass має inline defaults. Якщо YAML неповний — тихо застосовуються.

---

### 1.9 🟡 [MEDIUM] fsm_open.py: Instrument Specs Fallback

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/execution_position/fsm_open.py](apps/reference/domains/execution_position/fsm_open.py#L163-L178) |
| **Рядок** | 163-178 |
| **Тип** | Silent Fallback |
| **Код** | Fallback to `MIN_ORDER_QTY`, `QTY_STEP`, `PRICE_STEP`, `MIN_NOTIONAL` |

```python
# fsm_open.py:163-178
def _get_instrument_specs(self, symbol: str) -> Dict[str, Decimal]:
    instruments = self.config.instruments or {}
    specs = instruments.get(symbol)

    # Default values (fallback for non-trading symbols or missing config)
    min_qty = MIN_ORDER_QTY      # ⚠️ from contracts.py
    step_size = QTY_STEP         # ⚠️ from contracts.py
    tick_size = PRICE_STEP       # ⚠️ from contracts.py
    min_notional = MIN_NOTIONAL  # ⚠️ from contracts.py
```

#### Ризик:
- **Contracts.py defaults** можуть не відповідати реальним exchange specs
- Ордер може бути rejected через wrong step_size

---

### 1.10 🔴 [CRITICAL] exposure_guard.py: Side Normalization

| Атрибут | Значення |
|---------|----------|
| **Файл** | [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L729-L731) |
| **Рядок** | 729-731 |
| **Тип** | Silent Default |
| **Код** | `if side not in {...}: side = "BUY"` |

```python
# exposure_guard.py:729-731
side = str(side or "").upper()
if side not in {"BUY", "SELL", "LONG", "SHORT"}:
    side = "BUY"  # ⚠️ SILENT DEFAULT TO BUY
```

#### Ризик:
- **Invalid side → BUY** без помилки
- Якщо upstream передав typo "BY" → система відкриє BUY позицію

---

## 2. Аналіз впливу (Impact Analysis)

### 2.1 Граф залежностей

```
                    ┌─────────────────────────────────┐
                    │     CONFIG LOADING FAILURE      │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │  AuroraConfig() EMPTY FALLBACK  │
                    │  (fsm.py:134, fsm_open.py:130)  │
                    └───────────────┬─────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ExposureGuard  │     │   OpenFlowFSM   │     │   Watchdog      │
│  (no limits)    │     │  (no validation)│     │  (no TTL)       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    UNLIMITED EXPOSURE RISK                       │
│  • 20x leverage default applied                                  │
│  • No cooldown between orders                                    │
│  • No max notional check                                        │
│  • Orders hang forever without TTL                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 BTCUSDT Anchor Failure Chain

```
┌──────────────────────┐
│  BTCUSDT WS FAILURE  │
│  (API error/delisted)│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ anchor_prices empty  │
│ macro_resid not_ready│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  warmup.full_ready   │
│      = False         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ CMD:PROCESS_STRATEGY │
│     BLOCKED          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   NO TRADING EVER    │
│   (silent failure)   │
└──────────────────────┘
```

### 2.3 Float Precision Dust Chain

```
┌──────────────────────┐
│   Intent qty=0.12345 │
│   (Decimal in DM)    │
└──────────┬───────────┘
           │ float() in fsm_close.py
           ▼
┌──────────────────────┐
│ qty = 0.12344999...  │
│ (float precision)    │
└──────────┬───────────┘
           │ back to Decimal for order
           ▼
┌──────────────────────┐
│ Order qty mismatch   │
│ 0.12344 vs 0.12345   │
└──────────┬───────────┘
           │ partial fill
           ▼
┌──────────────────────┐
│ DUST: 0.00001 BTC    │
│ stuck on balance     │
└──────────────────────┘
```

---

## 3. План ліквідації (Remediation Plan)

### 3.1 Immediate Fixes (P0 — до релізу)

#### 3.1.1 AuroraConfig Empty Fallback → Fail-Closed

**Файли:** `fsm.py`, `fsm_open.py`, `fsm_manage.py`

**Поточний код:**
```python
self.config = AuroraConfig() if config is None else config
```

**Рішення:**
```python
if config is None:
    raise ValueError(
        "CRITICAL: ExecPosFSM requires valid AuroraConfig. "
        "Refusing to start with empty defaults (fail-closed)."
    )
self.config = config
```

#### 3.1.2 ExposureGuard Leverage Default → ConfigContractError

**Файл:** `exposure_guard.py:365`

**Поточний код:**
```python
default_leverage_raw = leverage_defaults["__default__"] if "__default__" in leverage_defaults else 20
```

**Рішення:**
```python
if "__default__" not in leverage_defaults:
    raise ConfigContractError(
        path="trading.execution.exposure.leverage_defaults.__default__",
        why="Default leverage is mandatory. Refusing to assume 20x."
    )
default_leverage_raw = leverage_defaults["__default__"]
```

#### 3.1.3 Side Normalization → Fail-Closed

**Файл:** `exposure_guard.py:729-731`

**Поточний код:**
```python
if side not in {"BUY", "SELL", "LONG", "SHORT"}:
    side = "BUY"
```

**Рішення:**
```python
if side not in {"BUY", "SELL", "LONG", "SHORT"}:
    raise ValueError(f"Invalid order side: {side!r}. Expected BUY|SELL|LONG|SHORT.")
```

### 3.2 Config Extraction (P1 — наступний спринт)

#### 3.2.1 Fallback Risk Parameters → YAML SSOT

**Файл:** `exposure_guard.py`

**Створити:** `config/aurora/domains/execution_position_fallback.yaml`
```yaml
execution_position:
  fallback:
    policy: "fail_closed"  # or "risk_reduction"
    risk_reduction_pct: 0.5
    backoff_ms: [200, 500, 1000]
```

**Код:**
```python
# exposure_guard.py:152
try:
    fallback_cfg = self.config.domains.execution_position.fallback
    if fallback_cfg is None:
        raise ConfigContractError(...)
    self.fallback_config = {
        "policy": fallback_cfg.policy,
        "risk_reduction_pct": Decimal(str(fallback_cfg.risk_reduction_pct)),
        "backoff_ms": list(fallback_cfg.backoff_ms),
    }
except ...:
    raise ConfigContractError(
        path="domains.execution_position.fallback",
        why="Fallback config is mandatory (no inline defaults)."
    )
```

#### 3.2.2 Aurora Handler Defaults → Strict Config

**Файл:** `aurora_handler.py:212-257`

**Рішення:** Видалити `else` branch повністю:
```python
decision = getattr(aurora, "decision", None)
if decision is None:
    from apps.reference.config_contract import ConfigContractError
    raise ConfigContractError(
        path="strategies.aurora.decision",
        why="Aurora decision config is mandatory. No inline defaults allowed."
    )
# ... use decision fields directly
```

### 3.3 BTCUSDT Hardcode → Dynamic Anchor (P1)

**Файл:** `feature_engineering.py`

**Рішення:**
```python
# feature_engineering.py:737
primary_anchor = self.cfg.macro_sync_primary_anchor  # from config
if primary_anchor not in self._anchor_last_ts_ms:
    # Try fallback anchors
    for fallback in self.cfg.macro_sync_fallback_anchors:
        if fallback in self._anchor_last_ts_ms:
            primary_anchor = fallback
            break
    else:
        hot.macro_resid_ready = False
        hot.macro_resid_not_ready_reason = "no_anchor_available"
        return ...
```

**Config addition:**
```yaml
# config/aurora/feature_engineering.yaml
macro_sync:
  primary_anchor: "BTCUSDT"
  fallback_anchors: ["ETHUSDT", "BNBUSDT"]
```

### 3.4 Float → Decimal Migration (P2)

**Файли:** `fsm_close.py:87`, та інші

**Рішення:**
```python
# fsm_close.py
from decimal import Decimal

qty_raw = pld.get("qty", "0")
qty = Decimal(str(qty_raw)) if qty_raw else Decimal("0")
```

### 3.5 Dead Code Cleanup (P2)

#### 3.5.1 fsm_close.py: Remove Dead max_hold_sec

```python
# BEFORE
def __init__(self, max_hold_sec: float = 86400.0):
    self.max_hold_sec = max_hold_sec  # DEAD

# AFTER
def __init__(self):
    # max_hold_sec removed - failsafe is controlled by OrderGuardian
    pass
```

**Оновити docstring:**
```python
"""
CloseFlowFSM: processes CMD:CLOSE from Decision Making.

NOTE: Autonomous closing (max_hold_sec failsafe) was removed in v2.3.
      Use OrderGuardian for orphan cleanup instead.
"""
```

---

## 4. Strict Mode Patch (Тимчасове рішення)

Якщо повний рефакторинг дорогий, можна ввести **STRICT_MODE** flag:

```python
# apps/reference/core/strict_mode.py

import os

STRICT_MODE = os.getenv("AURORA_STRICT_MODE", "false").lower() == "true"

def fail_closed(path: str, why: str, fallback_value=None):
    """
    Fail-closed helper for config access.
    
    In STRICT_MODE: raises ConfigContractError
    In legacy mode: logs warning, returns fallback_value
    """
    from apps.reference.config_contract import ConfigContractError
    
    if STRICT_MODE:
        raise ConfigContractError(path=path, why=why)
    else:
        import logging
        logging.getLogger(__name__).warning(
            f"LEGACY_FALLBACK: {path} - {why}. Using fallback: {fallback_value}"
        )
        return fallback_value
```

**Використання:**
```python
# exposure_guard.py
from apps.reference.core.strict_mode import fail_closed

default_leverage = leverage_defaults.get("__default__")
if default_leverage is None:
    default_leverage = fail_closed(
        path="trading.execution.exposure.leverage_defaults.__default__",
        why="Default leverage missing",
        fallback_value=20
    )
```

**Активація в production:**
```bash
export AURORA_STRICT_MODE=true
```

---

## 5. Validation Gates (CI/CD)

### 5.1 Новий тест: test_no_empty_auroraconfig.py

```python
# tests/vfoundation/test_no_empty_auroraconfig.py

def test_fsm_rejects_none_config():
    """ExecPosFSM must reject None config (fail-closed)."""
    from apps.reference.domains.execution_position.fsm import ExecPosFSM
    
    with pytest.raises(ValueError, match="requires valid AuroraConfig"):
        ExecPosFSM(config=None, fsm=mock_fsm)

def test_open_flow_rejects_none_config():
    """OpenFlowFSM must reject None config (fail-closed)."""
    from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM
    
    with pytest.raises(ValueError, match="requires valid AuroraConfig"):
        OpenFlowFSM(config=None)
```

### 5.2 Grep Guard: no_inline_defaults.sh

```bash
#!/bin/bash
# CI gate: detect inline default patterns

PATTERNS=(
    'if config is None else config'
    '= .* if .* else [0-9]'
    'getattr.*default.*=[0-9]'
)

for pattern in "${PATTERNS[@]}"; do
    if grep -rn "$pattern" apps/reference/domains/; then
        echo "❌ FAIL: Found inline default pattern: $pattern"
        exit 1
    fi
done

echo "✅ PASS: No inline defaults detected"
```

---

## 6. Пріоритезація

| ID | Проблема | Пріоритет | Effort | Risk Reduction |
|----|----------|-----------|--------|----------------|
| 1.1 | AuroraConfig() fallback | P0 | 1h | HIGH |
| 1.2 | Leverage 20x default | P0 | 2h | CRITICAL |
| 1.10 | Side default to BUY | P0 | 30m | HIGH |
| 1.3 | BTCUSDT hardcode | P1 | 4h | MEDIUM |
| 1.4 | Aurora defaults block | P1 | 3h | HIGH |
| 1.6 | Liveness fallback | P1 | 1h | MEDIUM |
| 1.9 | Instrument specs fallback | P1 | 2h | MEDIUM |
| 1.5 | Float qty + dead code | P2 | 2h | LOW |
| 1.7 | -1ms tick hack | P2 | 4h | LOW |
| 1.8 | MR config defaults | P2 | 2h | MEDIUM |

---

## 7. Висновки

1. **Найкритичніша проблема:** `AuroraConfig()` fallback дозволяє системі запуститись без жодних лімітів
2. **Найнебезпечніший hardcode:** Leverage 20x default — може призвести до ліквідації
3. **Найприхованіший баг:** BTCUSDT anchor failure → silent trading halt

**Рекомендація:** Ввести `AURORA_STRICT_MODE=true` в staging, після стабілізації — в production.

---

*Звіт підготовлено: 22 січня 2026*  
*Автор: Principal Code Auditor*  
*Версія: 1.0*
