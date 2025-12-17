# CFG-STRATEGIES-SSOT-01-AUDIT-FOUNDATION: Audit Report

**Date**: 2025-12-17  
**Scope**: Aurora + Mean Reversion strategy configurations and integrations  
**Symbols**: BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT  
**Domains**: decision_making, feature_engineering, regime_detector  

---

## Executive Summary

**Стратегії в системі:**
1. **Aurora (tick-based)**: Багатофакторна композитна стратегія з 8 сигналів, інтегрована через Alpha Models
2. **Mean Reversion 1m (bar-based)**: Bollinger Bands стратегія з 1-хвилинними барами, інтегрована через MeanReversionHandler

**Критичні знахідки:**
- ❌ Конфігурації **фрагментовані** між 5+ файлами без чіткого SSOT
- ❌ **Дублікація**: `mean_reversion_1m` параметри існують у 3 місцях (trading.yaml, strategies/, instruments/)
- ❌ **Конфлікт enabled**: aurora.enabled у instruments/*.yaml vs aurora_instruments.yaml
- ⚠️ **Мертві конфіги**: strategies/aurora_*.yaml не використовуються runtime
- ⚠️ **Fallback hell**: 3-4 рівні fallback'ів для кожного параметру

**Можливість SSOT-рефакторингу**: ✅ **ТАК**, але потребує обережного розділення Aurora vs MR параметрів

---

## 1️⃣ STRATEGY MAP

### Aurora Strategy (Tick-Based, Multi-Signal)

| Aspect | Details |
|--------|---------|
| **Де визначається** | `apps/reference/domains/decision_making/decision_making.py` (L1750-2000) |
| **Клас/Entry Point** | `DecisionMaking._make_decision_for_symbol()` → `self.alpha_registry.calculate_all_alpha()` |
| **Alpha Models** | - `MomentumAlphaModel` (imported L63)<br>- `MeanReversionAlphaModel` (L64)<br>- `VolatilityAlphaModel` (L65)<br>Registered L202-206 |
| **Використовується** | - `on_features_update()` (L1750+): отримує фічі → викликає alpha models<br>- `_make_decision_for_symbol()`: композує сигнали з alpha scores<br>- Емітує `EVT:TRADE_INTENT_PROPOSED` |
| **Config Keys (читає)** | 1. `config.aurora_instruments[symbol].*` (SSOT, L1241-1263)<br>2. `trading.decision.signal_threshold` (L1457-1476)<br>3. `trading.decision.regime_threshold_multipliers` (L1400-1425)<br>4. `trading.decision.sizing_modifiers` (L1427-1453)<br>5. `trading.decision.signal_weights` (not directly visible, likely in alpha models)<br>6. `trading.decision.side_bias_*` (L1370-1398) |
| **Fallback Chain** | `aurora_instruments[symbol]` → `trading.decision.*` → hardcoded defaults |
| **Дублі** | ❌ **aurora.enabled** дублюється:<br>- `config/aurora/instruments/{SYMBOL}.yaml` (L18-19 кожного)<br>- Логічно має бути в `aurora_instruments.yaml` але там немає поля `enabled` |
| **Режим роботи** | Tick-driven: отримує `EVT:FEATURES_PUBLISHED` кожні ~100-500ms, одразу генерує intent |

### Mean Reversion 1m Strategy (Bar-Based)

| Aspect | Details |
|--------|---------|
| **Де визначається** | `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` (L195-542) |
| **Клас/Entry Point** | `MeanReversion1mStrategy(config, timeframe_sec, regime_sizing)` |
| **Інтеграція** | `apps/reference/domains/decision_making/mean_reversion_handler.py` (L1-372)<br>- `MeanReversionHandler.__init__()` (L52-95): парсить конфіг<br>- `MeanReversionHandler.on_tick()` (L207-237): агрегує тіки в бари<br>- Емітує `EVT:MR_SIGNAL_PRODUCED` → gateway `_on_mr_signal_gateway()` (L618-970) |
| **Використовується** | - `DecisionMaking.__init__()` (L520-546): ініціалізує MR handler<br>- `DecisionMaking.on_tick()` (L589-614): форвардить тіки в MR handler<br>- `_on_mr_signal_gateway()` (L618+): застосовує gates (risk/regime/QoS/exposure/TTL)<br>- Емітує `EVT:TRADE_INTENT_PROPOSED` після проходження gates |
| **Config Keys (читає)** | 1. `config.mean_reversion_1m.enabled` (L99, L521)<br>2. `config.mean_reversion_1m.assets[symbol].enabled` (L117-124)<br>3. `config.mean_reversion_1m.strategy.*` (L135-167): bb_window, bb_num_std, min_bb_width, etc.<br>4. `config.mean_reversion_1m.assets[symbol].strategy.*` (L169-185): per-symbol overrides<br>5. `config.mean_reversion_1m.allowed_regimes` (L154)<br>6. `config.mean_reversion_1m.assets[symbol].allowed_regimes` (L186)<br>7. `config.mean_reversion_1m.regime_sizing` (L140-151) |
| **Fallback Chain** | `mean_reversion_1m.assets[symbol].strategy.*` → `mean_reversion_1m.strategy.*` (global) → MRStrategyConfig defaults |
| **Дублі** | ❌ **КРИТИЧНІ ДУБЛІ**:<br>1. `trading.yaml::trading.mean_reversion_1m` (L142-197)<br>2. `strategies/mean_reversion_1m.yaml::mean_reversion_1m` (L14-158)<br>3. `instruments/{SYMBOL}.yaml::mean_reversion_1m` (L87-101 кожного)<br>**ConfigLoader читає** (L315-333): strategies/mean_reversion_1m.yaml → merge в `merged_config["mean_reversion_1m"]` |
| **Режим роботи** | Bar-driven: агрегує тіки в 1m бари (BarResampler), генерує сигнал на закритті бару |

---

## 2️⃣ CONFIG USAGE MAP

### Aurora Parameters (aurora_instruments.yaml + instruments/*.yaml)

| Config Key | File Location | Runtime Reader (Class/Function) | Mode | Notes |
|------------|---------------|----------------------------------|------|-------|
| `aurora_instruments[symbol].weights.*` | aurora_instruments.yaml L17-26 (ETH), L73-82 (SOL), etc. | `DecisionMaking._get_aurora_instrument_cfg()` L1241-1263 | **SSOT** | ✅ Pydantic-typed, fail-closed (CFG-AURORA-INSTRUMENTS-SSOT-01-FIXPACK) |
| `aurora_instruments[symbol].side_bias.*` | aurora_instruments.yaml L28-31 (ETH), L84-87 (SOL) | `DecisionMaking._get_side_bias_params()` L1370-1398 | **SSOT** | Fallback: `trading.decision.side_bias_*` |
| `aurora_instruments[symbol].exit.sl_pct` | aurora_instruments.yaml L47, L101, etc. | `DecisionMaking._get_param()` L1342-1367 | **SSOT** | Used for SL calculation |
| `aurora_instruments[symbol].exit.max_hold_sec` | aurora_instruments.yaml L48, L102, etc. | `DecisionMaking._get_param()` | **SSOT** | Position hold time limit |
| `aurora_instruments[symbol].take_profit.*` | aurora_instruments.yaml L51-54, L105-108 | `DecisionMaking._get_param()` | **SSOT** | TP1/TP2 ratios + partial_exit_pct |
| `aurora_instruments[symbol].trailing_stop.*` | aurora_instruments.yaml L58-62, L112-116 | `DecisionMaking._get_param()` | **SSOT** | Trailing stop activation/trail pct |
| `aurora_instruments[symbol].regime_thresholds` | aurora_instruments.yaml L33-37, L89-93 | `DecisionMaking._get_regime_thresholds()` L1400-1425 | **SSOT** | Fallback: `trading.decision.regime_threshold_multipliers` |
| `aurora_instruments[symbol].regime_sizing` | aurora_instruments.yaml L39-42, L95-98 | `DecisionMaking._get_regime_sizing()` L1427-1453 | **SSOT** | Fallback: `trading.decision.sizing_modifiers` |
| `aurora_instruments[symbol].allowed_regimes` | aurora_instruments.yaml L64, L118 | `DecisionMaking._get_aurora_instrument_cfg()` + regime gate logic | **SSOT** | Regime filtering for Aurora |
| `aurora_instruments[symbol].cooldown_sec` | aurora_instruments.yaml L250 (BTCUSDT example) | `DecisionMaking._get_cooldown_sec()` L1318-1339 | **SSOT** | Fallback: `trading.decision.cooldown_sec` |
| **❌ aurora.enabled** | instruments/{SYMBOL}.yaml L18-19 | ❌ **NOT USED BY RUNTIME** | **DEAD** | Має бути в aurora_instruments або domains config |
| **❌ aurora.ema_clamp** | instruments/BTCUSDT.yaml L74-77 | ❌ **NOT FOUND in decision_making.py** | **DEAD** | Можливо legacy EMA обмеження |
| **❌ aurora.signal_threshold** | instruments/BTCUSDT.yaml L79-81 | ❌ **Conflict**: DecisionMaking читає з `trading.decision.signal_threshold` (L1457) | **DANGEROUS** | Per-symbol override не працює! |
| **❌ aurora.max_risk_score** | instruments/BTCUSDT.yaml L83-85 | ❌ **NOT FOUND** | **DEAD** | Можливо planned feature |

### Mean Reversion Parameters

| Config Key | File Location | Runtime Reader | Mode | Notes |
|------------|---------------|----------------|------|-------|
| `mean_reversion_1m.enabled` | trading.yaml L143 | `MeanReversionHandler._parse_config()` L99 | **PRIMARY** | Global enable/disable |
| `mean_reversion_1m.timeframe_sec` | strategies/mean_reversion_1m.yaml L19 | `MeanReversionHandler._init_strategies()` L133 | **SSOT** | 60s bar aggregation |
| `mean_reversion_1m.strategy.*` | **3 COPIES**:<br>1. trading.yaml L148-177<br>2. strategies/mean_reversion_1m.yaml L24-51<br>3. ConfigLoader merges (L315-333) | `MeanReversionHandler._init_strategies()` L135-167 | **DUPLICATE** | ⚠️ ConfigLoader читає strategies/*.yaml, але trading.yaml теж має копію! |
| `mean_reversion_1m.assets[symbol].enabled` | trading.yaml L147, L164, L179 | `MeanReversionHandler._parse_config()` L117-124 | **PRIMARY** | Per-symbol enable |
| `mean_reversion_1m.assets[symbol].strategy.*` | **2 COPIES**:<br>1. trading.yaml L148-177<br>2. instruments/{SYMBOL}.yaml L89-100 | `MeanReversionHandler._init_strategies()` L169-185 | **DUPLICATE** | ⚠️ Який має пріоритет? ConfigLoader не merge instruments/*.yaml MR секцію! |
| `mean_reversion_1m.assets[symbol].allowed_regimes` | **2 COPIES**:<br>1. trading.yaml L157, L175, L190<br>2. instruments/{SYMBOL}.yaml L101 | `DecisionMaking._get_mr_allowed_regimes()` L1265-1295 | **DUPLICATE** | Fallback: `trading.mean_reversion_1m.assets[symbol].allowed_regimes` → `mean_reversion_1m.allowed_regimes` |
| `mean_reversion_1m.regime_sizing` | strategies/mean_reversion_1m.yaml (NOT PRESENT in current file) | `MeanReversionHandler._init_strategies()` L140-151 | **MISSING** | Може бути в повному strategies/*.yaml |
| **❌ mean_reversion_1m.assets[symbol].sl_pct** | trading.yaml L196 (COMMENTED OUT) | ❌ **REMOVED**: Phase 3 switched to dynamic ATR-based SL | **DEAD** | Comment: "REMOVED: Enable dynamic ATR-based SL" |

### Global Decision Parameters (trading.decision.*)

| Config Key | File Location | Runtime Reader | Mode | Notes |
|------------|---------------|----------------|------|-------|
| `trading.decision.signal_threshold` | trading.yaml L14 | `DecisionMaking._get_signal_threshold()` L1455-1476 | **FALLBACK** | Fallback після aurora_instruments override |
| `trading.decision.regime_threshold_multipliers` | trading.yaml L26-33 | `DecisionMaking._get_regime_thresholds()` L1400-1425 | **FALLBACK** | Fallback після aurora_instruments |
| `trading.decision.side_bias_*` | trading.yaml L36-38 | `DecisionMaking._get_side_bias_params()` L1370-1398 | **FALLBACK** | Fallback після aurora_instruments |
| `trading.decision.cooldown_sec` | trading.yaml L40 | `DecisionMaking._get_cooldown_sec()` L1318-1339 | **FALLBACK** | Fallback після aurora_instruments |
| `trading.decision.sizing_modifiers` | trading.yaml L87-94 | `DecisionMaking._get_regime_sizing()` L1427-1453 | **FALLBACK** | Fallback після aurora_instruments.regime_sizing |
| `trading.decision.signal_weights` | trading.yaml L118-126 | ❌ **NOT DIRECTLY VISIBLE** | **UNCLEAR** | Можливо використовується в alpha models, потрібен grep по alpha_search/ |

---

## 3️⃣ DEAD / DANGEROUS CONFIGS

### 🔴 DEAD Configs (не читаються runtime)

| Config Key | Location | Why Dead | Impact |
|------------|----------|----------|--------|
| **strategies/aurora_*.yaml** (7 files) | config/aurora/strategies/ | ❌ ConfigLoader НЕ завантажує їх (тільки mean_reversion_1m.yaml) L315-323 | ⚠️ Misleading: виглядають як production конфіги, але не використовуються |
| `aurora.enabled` | instruments/{SYMBOL}.yaml L18-19 | ❌ DecisionMaking не перевіряє цей флаг при виклику alpha models | ❌ КРИТИЧНО: Неможливо disable Aurora per-symbol через конфіг! |
| `aurora.ema_clamp` | instruments/BTCUSDT.yaml L74-77 | ❌ Grep по decision_making.py не знайшов використання | Можливо legacy, можливо planned |
| `aurora.max_risk_score` | instruments/BTCUSDT.yaml L83-85 | ❌ Grep не знайшов | Можливо planned feature |
| `mean_reversion_1m.assets[symbol].sl_pct` | trading.yaml L196 (commented) | ✅ Intentionally removed в Phase 3 (switched to ATR-based) | Not a bug, but shows evolution |
| `trading.decision.signal_weights` | trading.yaml L118-126 | ⚠️ Можливо використовується в alpha models (не верифіковано) | Needs deeper grep в domains/alpha_search/ |

### 🟠 DUPLICATE Configs (конфлікт SSOT)

| Config Key | Locations | Conflict Description | Risk Level |
|------------|-----------|---------------------|------------|
| **mean_reversion_1m.strategy.\*** | 1. trading.yaml L148-177<br>2. strategies/mean_reversion_1m.yaml L24-51 | ConfigLoader merge strategies/*.yaml в `merged_config["mean_reversion_1m"]` (L333), але trading.yaml теж має `mean_reversion_1m.strategy` | 🔴 **HIGH**: Який має пріоритет? Deep_merge може перезаписати! |
| **mean_reversion_1m.assets[symbol].strategy.\*** | 1. trading.yaml L148-177<br>2. instruments/{SYMBOL}.yaml L89-100 | instruments/*.yaml MR секція **НЕ MERGE** ConfigLoader'ом! Тільки `aurora` секція є в instruments SSOT | 🔴 **HIGH**: instruments/{SYMBOL}.yaml::mean_reversion_1m **IGNORED**! |
| **mean_reversion_1m.assets[symbol].allowed_regimes** | 1. trading.yaml L157, L175, L190<br>2. instruments/{SYMBOL}.yaml L101 | Так само як вище — instruments/*.yaml MR ignored | 🟡 **MEDIUM**: Fallback працює, але дублікація confusing |
| **aurora.signal_threshold** | 1. instruments/BTCUSDT.yaml L79-81<br>2. trading.decision.signal_threshold L14 | DecisionMaking читає `aurora_instruments[symbol].signal_threshold` (L1455-1476), але цей ключ НЕ ІСНУЄ в aurora_instruments.yaml! Тільки в instruments/*.yaml як `aurora.signal_threshold` | 🔴 **CRITICAL**: Per-symbol override не працює! |

### 🟡 DANGEROUS Configs (неявна поведінка)

| Config Key | Issue | Impact |
|------------|-------|--------|
| **aurora_instruments[symbol] fallback chain** | 3-4 рівні fallback для кожного параметру:<br>aurora_instruments → trading.decision.* → hardcoded | 🟡 Складно передбачити поведінку, якщо конфіг частково відсутній |
| **mean_reversion_1m dual strategy** | MR конфіг має 2 джерела:<br>1. `config.mean_reversion_1m.*` (global + per-symbol)<br>2. Окремо `_get_mr_allowed_regimes()` читає з trading.mean_reversion_1m | 🟡 Inconsistent: один параметр може бути в одному місці, інший в іншому |
| **aurora.enabled vs MR.enabled** | Aurora: enable/disable через instruments/{SYMBOL}.yaml::aurora.enabled (NOT USED)<br>MR: enable/disable через trading.mean_reversion_1m.assets[symbol].enabled | 🔴 **ASYMMETRY**: Неможливо disable Aurora через конфіг! |
| **ConfigLoader merge order** | deep_merge(system → trading → regime → strategies) L326-330<br>Але aurora_instruments.yaml merge окремо L445-497 | ⚠️ Можливі race conditions якщо ключі перетинаються |

---

## 4️⃣ STRATEGY BOUNDARY ANALYSIS

### Чи є реально дві стратегії?

✅ **ТАК, є ДВІ ОКРЕМІ стратегії** з різними архітектурами:

| Аспект | Aurora (Tick-Based) | Mean Reversion 1m (Bar-Based) |
|--------|---------------------|-------------------------------|
| **Тригер** | `EVT:FEATURES_PUBLISHED` (кожні ~100-500ms) | Закриття 1m бару (кожні 60s) |
| **Логіка сигналу** | Композиція 8 фічей через Alpha Models:<br>- MomentumAlphaModel<br>- MeanReversionAlphaModel<br>- VolatilityAlphaModel | Bollinger Bands + RSI + ATR<br>Чисто bar-based статистика |
| **Entry point** | `DecisionMaking._make_decision_for_symbol()` | `MeanReversionHandler.on_tick()` → BarResampler → Strategy |
| **Signal emission** | Одразу `EVT:TRADE_INTENT_PROPOSED` (після gates) | `EVT:MR_SIGNAL_PRODUCED` → `_on_mr_signal_gateway()` → gates → `EVT:TRADE_INTENT_PROPOSED` |
| **Режим інтеграції** | Native в DecisionMaking (alpha registry) | External handler (MeanReversionHandler) |
| **Конфіг SSOT** | `aurora_instruments.yaml` (root level) | `mean_reversion_1m.*` (під trading) |

### Де проходить межа між Aurora і MR?

**Архітектурна межа:**
1. **Aurora**: Tick-driven → Features (8 metrics) → Alpha Models → Composite Signal → Intent
2. **MR**: Tick-driven → Bar Aggregation (1m) → BB/RSI/ATR → MR Signal → Gateway → Intent

**Конфігураційна межа (поточна):**
- Aurora: `config.aurora_instruments[symbol].*`
- MR: `config.mean_reversion_1m.assets[symbol].*`

**⚠️ ПРОБЛЕМА**: Межа розмита в:
- `allowed_regimes`: є у обох (aurora_instruments.allowed_regimes + mean_reversion_1m.assets.allowed_regimes)
- `regime_thresholds/sizing`: Aurora параметри, але впливають на MR через DecisionMaking gates
- `exit.sl_pct`: Aurora параметр, але MR теж має sl_atr_mult (різна семантика)

### Per-Symbol Strategy Mix (BTC має 1 чи 2 поведінки?)

| Symbol | Aurora Enabled | MR Enabled | Behavior Mix |
|--------|----------------|------------|--------------|
| **ETHUSDT** | ✅ YES (instruments/ETHUSDT.yaml L17) | ❌ NO | **Aurora-only** (Pure tick-based) |
| **SOLUSDT** | ✅ YES (instruments/SOLUSDT.yaml L17) | ❌ NO | **Aurora-only** |
| **DOGEUSDT** | ❌ NO (instruments/DOGEUSDT.yaml L19: `enabled: false`) | ✅ YES (trading.yaml L147) | **MR-only** (Champion asset) |
| **XRPUSDT** | ❌ NO (instruments/XRPUSDT.yaml L18) | ✅ YES (trading.yaml L179) | **MR-only** |
| **BTCUSDT** | ✅ YES (instruments/BTCUSDT.yaml L18) | ✅ YES (trading.yaml L164) | **HYBRID** (Both strategies active!) |

**✅ BTC має ДВІ НЕЗАЛЕЖНІ поведінки:**
1. **Aurora tick-based**: генерує intents на основі фічей кожні ~100-500ms
2. **MR bar-based**: генерує intents на закритті 1m бару

**⚠️ КОНФЛІКТ РИЗИКІВ:**
- Обидві стратегії можуть емітити intent одночасно для BTC
- QoS gates мають запобігти rapid-fire, але це не гарантує логічну несуперечність
- Якщо Aurora каже SELL, а MR каже BUY → хто виграє?

**Поточне рішення конфлікту:**
- Sequential processing через `_on_mr_signal_gateway()` gates (L618-970)
- Flip check (L782-847): якщо є позиція, перевіряє напрямок
- QoS symbol cooldown (L898-933): блокує rapid-fire
- **НО**: немає явної координації між Aurora і MR strategies

---

## 5️⃣ SSOT REFACTORING FEASIBILITY

### Чи можливо чисто винести стратегії в окремий SSOT?

✅ **ТАК, можливо**, але з обережністю:

### Запропонована структура:

```
config/aurora/strategies/
├── aurora.yaml          # Aurora strategy params (NEW)
│   ├── global:
│   │   ├── signal_weights: {...}
│   │   ├── signal_threshold: 0.1
│   │   └── alpha_models: [momentum, mean_reversion, volatility]
│   └── per_symbol:
│       ├── ETHUSDT: {...}  # Migrate from aurora_instruments.yaml
│       └── BTCUSDT: {...}
│
└── mean_reversion_1m.yaml  # MR strategy params (EXISTS, needs cleanup)
    ├── global: {...}
    └── per_symbol: {...}  # Migrate from trading.yaml
```

### План міграції:

#### Phase 1: Cleanup (Safe)
1. ✅ **Delete dead configs**:
   - strategies/aurora_*.yaml (7 files, not loaded by ConfigLoader)
   - instruments/*.yaml::aurora.ema_clamp, max_risk_score (dead keys)
2. ✅ **Remove duplicates**:
   - DELETE trading.yaml::trading.mean_reversion_1m.assets[symbol].strategy (keep in strategies/mean_reversion_1m.yaml)
   - DELETE instruments/{SYMBOL}.yaml::mean_reversion_1m (not loaded anyway)

#### Phase 2: Consolidate MR (Medium Risk)
3. ✅ **Single MR SSOT**:
   - MOVE trading.yaml::trading.mean_reversion_1m → strategies/mean_reversion_1m.yaml (full merge)
   - UPDATE ConfigLoader to ONLY load strategies/mean_reversion_1m.yaml (L315-333)
   - REMOVE trading.yaml::trading.mean_reversion_1m completely

#### Phase 3: Separate Aurora Strategy SSOT (High Risk)
4. ⚠️ **NEW strategies/aurora.yaml**:
   - MOVE aurora_instruments.yaml → strategies/aurora.yaml::per_symbol
   - ADD global section for signal_weights, signal_threshold
   - UPDATE DecisionMaking to read from `config.aurora.per_symbol[symbol]`
5. ⚠️ **Fix aurora.enabled**:
   - ADD `enabled: bool` to AuroraInstrumentConfig Pydantic model
   - READ from strategies/aurora.yaml::per_symbol[symbol].enabled
   - GATE alpha model calculation in DecisionMaking

#### Phase 4: Runtime Guards (Critical)
6. 🔴 **Strategy conflict detection**:
   - If symbol has BOTH aurora.enabled=true AND mean_reversion_1m.enabled=true:
     - LOG WARNING
     - Apply strategy priority (Aurora > MR or vice versa)
     - OR: Allow both but add inter-strategy cooldown

### Блокери:

| Blocker | Impact | Workaround |
|---------|--------|-----------|
| **aurora_instruments.yaml = execution params, not strategy** | HIGH | aurora_instruments містить exit/TP/SL — це execution, не strategy logic. Треба розділити:<br>- strategies/aurora.yaml (weights, signal logic)<br>- execution/aurora_instruments.yaml (exit, TP, SL) |
| **ConfigLoader merge order** | MEDIUM | Deep_merge може конфліктувати. Треба explicit priority у ConfigLoader |
| **Pydantic models** | MEDIUM | AuroraConfig.aurora_instruments expects Dict[str, AuroraInstrumentConfig]. Треба новий AuroraStrategyConfig model |
| **Backward compatibility** | LOW | Існуючі конфіги у users (testnet/live). Треба migration script |

---

## 6️⃣ FINAL RECOMMENDATIONS

### ❌ DO NOT (до цього аудиту):
1. ❌ Створювати strategies.yaml без чіткого розділення strategy vs execution
2. ❌ Рефакторити DecisionMaking без розуміння alpha models
3. ❌ Чіпати ConfigLoader merge logic без тестів

### ✅ SAFE NEXT STEPS:
1. ✅ **DELETE** strategies/aurora_*.yaml (7 мертвих файлів)
2. ✅ **CONSOLIDATE** mean_reversion_1m.yaml (видалити дублі з trading.yaml)
3. ✅ **ADD** aurora.enabled field до Pydantic моделі + runtime check
4. ✅ **DOCUMENT** strategy conflict resolution policy (Aurora vs MR для BTC)

### 🟡 NEEDS RESEARCH:
1. 🔍 Grep `apps/reference/domains/alpha_search/` — верифікувати signal_weights usage
2. 🔍 Trace alpha models execution — як саме 8 metrics композуються?
3. 🔍 Check instruments/*.yaml loading — ConfigLoader merge logic для instruments

---

## 7️⃣ ANNEXES

### File Inventory

**Strategy Implementation:**
- `apps/reference/domains/decision_making/decision_making.py` (4014 lines) — Aurora integration + MR gateway
- `apps/reference/domains/decision_making/mean_reversion_handler.py` (372 lines) — MR handler
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` (542 lines) — MR strategy core
- `apps/reference/domains/alpha_search/*.py` — Alpha models (not fully audited)

**Config Files (Active):**
- `config/aurora/trading.yaml` (496 lines) — trading.decision.*, trading.mean_reversion_1m.*
- `config/aurora/aurora_instruments.yaml` (253 lines) — Aurora per-symbol params (SSOT via CFG-AURORA-INSTRUMENTS-SSOT-01)
- `config/aurora/strategies/mean_reversion_1m.yaml` (158 lines) — MR strategy params
- `config/aurora/instruments/{SYMBOL}.yaml` (5 files) — Per-symbol instrument specs + aurora/MR sections

**Config Files (Dead):**
- `config/aurora/strategies/aurora_phase3_production.yaml` (NOT loaded)
- `config/aurora/strategies/aurora_optimal_full_v1.yaml` (NOT loaded)
- `config/aurora/strategies/aurora_optimal_production_v1.yaml` (NOT loaded)
- `config/aurora/strategies/aurora_fullscale_optuna_v1.yaml` (NOT loaded)
- `config/aurora/strategies/traiding_best_optuna_3_5m.yaml` (NOT loaded)
- `config/aurora/strategies/trading_1m_best_optuna.yaml` (NOT loaded)

### Code References (Key Functions)

**Aurora Strategy:**
- Entry: `DecisionMaking.on_features_update()` L1750+
- Signal: `self.alpha_registry.calculate_all_alpha(symbol, features)` L1777
- Gate: `DecisionMaking._make_decision_for_symbol()` L2000+
- Config: `DecisionMaking._get_aurora_instrument_cfg()` L1241-1263

**MR Strategy:**
- Entry: `MeanReversionHandler.on_tick()` L207-237
- Signal: `MeanReversion1mStrategy.on_tick()` (mean_reversion_strategy.py)
- Gateway: `DecisionMaking._on_mr_signal_gateway()` L618-970
- Config: `MeanReversionHandler._parse_config()` L96-129

**Config Loading:**
- Main: `ConfigLoader.load_config()` L280-550
- MR: `ConfigLoader.load_config()` L315-333 (strategies/mean_reversion_1m.yaml)
- Aurora: `ConfigLoader.load_config()` L445-497 (aurora_instruments.yaml)

---

**Audit Status**: ✅ **COMPLETE**  
**Quality Gate**: All 4 mandatory artifacts delivered  
**Next Action**: User review → SSOT design decision → Phase 2 implementation plan
