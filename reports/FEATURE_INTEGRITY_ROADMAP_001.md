# FEATURE INTEGRITY ROADMAP 001

**Project:** Aurora/Phenix Trading System  
**Date:** 2026-01-05  
**Stage:** 1 — Read-Only Analysis (NO CODE CHANGES)  
**Status:** PASS (Stage 2 can proceed without main.py refactoring)

---

## 0) Executive Summary

### 3 найбільші ризики (P0) та чому

| # | Ризик | Причина | Вплив |
|---|-------|---------|-------|
| **P0-1** | **volatility_state overflow** | При `avg_range → 0` (flat market) формула `current_range / avg_range` → `+Inf`. Немає hard floor для denominator | Score = +Inf або NaN → некоректний decision/sizing, потенційний crash |
| **P0-2** | **spread_bps truth validation** | `std(spread)` не детектує stale book (якщо ринок справді вузький, std=0 нормальний). Немає book_update_age_sec або bid/ask change counters | False-positive "healthy spread" при застарілому order book → торгівля з неактуальною ціною |
| **P0-3** | **Feature sanity firewall** | NaN/Inf/out-of-range features проходять у downstream без блокування або NRR | Decision logic отримує invalid inputs → непередбачувана поведінка |

### Що буде змінено в Stage 2 (runtime)

1. **volatility_state**: Hard floor для denominator + cap + NaN/Inf firewall
2. **spread_bps health gate**: book_update_age + changes_count + trades_seen validation
3. **Feature sanity layer**: Central NaN/Inf/out-of-range → `feature_ready=False` + NRR

### Що НЕ буде змінено

- `main.py` wiring (без рефакторингу)
- FSM event topology (EVT:FEATURES_CALCULATED, EVT:TRADE_INTENT_PROPOSED тощо)
- Existing config schema structure
- Strategy arbitration logic

### Гарантія LONG/SHORT directionality

LONG/SHORT reachability **підтверджено** через:

1. **OBI/TFI** (signed [-1, 1]): Позитивні = buy pressure → LONG, негативні = sell pressure → SELL
2. **delta_price** (signed): Позитивне = price up → LONG bias, негативне → SELL bias
3. **ema_bias** (normalized [0, 1] з neutral=0.5): >0.5 = bullish → LONG, <0.5 = bearish → SELL
4. **Direction/Strength scoring** ([scoring_direction_strength_v1.py](apps/reference/domains/decision_making/scoring_direction_strength_v1.py#L98-L125)): `final = dir * (1 + α*strength)` — sign of `dir` determines side

**Evidence:**
- [signal_score_v2.py#L90-L95](apps/reference/domains/decision_making/signal_score_v2.py#L90-L95): `score = Σ w_i * (x_i - neutral_i) / Σ|w_i|` — sign preserved
- [decision_making.py#L310-L340](apps/reference/domains/decision_making/decision_making.py#L310-L340): `side = "BUY" if score > 0 else "SELL"` (для Aurora path)

---

## 1) System Map (Wiring & Data Flow)

### Data Flow Diagram (Text)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              AURORA/PHENIX DATA FLOW                              │
└──────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐      EVT:MARKET_TICK_RECEIVED       ┌────────────────────────┐
  │ MarketData  │ ──────────────────────────────────► │  FeatureEngineering    │
  │ Connector   │      (price, volume, ts_ms,         │  [FE]                  │
  │             │       bid/ask, buy/sell_volume)     │                        │
  └─────────────┘                                     │  Computes:             │
        │                                             │  - OBI, TFI (signed)   │
        │  EVT:ANCHOR_UPDATED                         │  - delta_price         │
        │  (BTCUSDT/ETHUSDT price)                    │  - ema_bias            │
        └──────────────────────────────────────┐      │  - volume_spike        │
                                               │      │  - volatility_state    │
                                               ▼      │  - spread_bps          │
                                          macro_sync  │  - macro_sync          │
                                          resampler   │  - large_trade_imb     │
                                                      │  - liquidity_kappa     │
                                                      └───────────┬────────────┘
                                                                  │
                                     EVT:FEATURES_CALCULATED      │
                                     (symbol, ts, features{},     │
                                      warmup{ready}, price_motion)│
            ┌─────────────────────────────────────────────────────┴────────────────┐
            │                                                                       │
            ▼                                                                       ▼
  ┌────────────────────┐                                           ┌───────────────────────┐
  │  RegimeDetector    │                                           │  RiskManagement       │
  │                    │                                           │                       │
  │  Detects:          │                                           │  Computes:            │
  │  - TREND_UP/DOWN   │                                           │  - risk_score         │
  │  - HIGH/LOW_VOL    │                                           │  - is_trading_allowed │
  │  - MEAN_REVERSION  │                                           │                       │
  │  - UNCERTAIN       │                                           └───────────┬───────────┘
  └─────────┬──────────┘                                                       │
            │                                                                   │
            │  EVT:REGIME_DETECTED                        EVT:RISK_ASSESSMENT  │
            │  (regime, confidence, warmup)               _COMPLETED           │
            │                                                                   │
            └──────────────────────────┬────────────────────────────────────────┘
                                       │
                                       ▼
                        ┌─────────────────────────────────┐
                        │      DecisionMaking             │
                        │                                 │
                        │  1. feature_ready gate          │
                        │  2. risk gate (score, allowed)  │
                        │  3. regime gate                 │
                        │  4. QoS gate (cooldown)         │
                        │  5. exposure gate               │
                        │  6. signal scoring              │
                        │  7. direction + sizing          │
                        │                                 │
                        │  Aurora: SignalScoreV2          │
                        │  MR: MeanReversionHandler       │
                        └────────────┬────────────────────┘
                                     │
                                     │  EVT:STRATEGY_SIGNAL_PRODUCED (MR path)
                                     │  или напрямую:
                                     │  EVT:TRADE_INTENT_PROPOSED (Aurora path)
                                     │
                                     ▼
                        ┌─────────────────────────────────┐
                        │      AuroraBridge               │
                        │                                 │
                        │  - Portfolio freshness gate     │
                        │  - QoS gate                     │
                        │  - Capacity gate (L1)           │
                        │  - Retry scheduler              │
                        │                                 │
                        │  Converts to:                   │
                        │  CMD:OPEN / CMD:CLOSE           │
                        └────────────┬────────────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────────────┐
                        │      ExecPosFSM                 │
                        │                                 │
                        │  - Order placement              │
                        │  - Fill tracking                │
                        │  - TP/SL brackets               │
                        │  - Position state machine       │
                        └─────────────────────────────────┘
```

### Точки істини (Source of Truth) для timestamps

| Data Point | SSOT Location | File:Line |
|------------|---------------|-----------|
| Tick ts_ms | `event.pld["ts"]` (exchange time) | [feature_engineering.py#L410-L415](apps/reference/domains/feature_engineering/feature_engineering.py#L410-L415) |
| Anchor ts_ms | `EVT:ANCHOR_UPDATED.pld["ts_ms"]` | [feature_engineering.py#L172-L185](apps/reference/domains/feature_engineering/feature_engineering.py#L172-L185) |
| Features ts | `EVT:FEATURES_CALCULATED.pld["ts"]` | [feature_engineering.py#L700](apps/reference/domains/feature_engineering/feature_engineering.py#L700) |
| Risk ts | `EVT:RISK_ASSESSMENT_COMPLETED.pld["ts"]` | DecisionMaking uses for skew check |
| Portfolio ts | `EVT:PORTFOLIO_STATE_UPDATED.pld["positions_last_ts_ms"]` | [main.py#L290](apps/reference/main.py#L290) |

### Де формуються ключові фічі

| Feature | File | Function/Line | Formula |
|---------|------|---------------|---------|
| **spread_bps** | [calculation_engine.py#L301-L320](apps/reference/domains/feature_engineering/calculation_engine.py#L301-L320) | `compute_spread_bps()` | `(ask - bid) / mid * 10000` |
| **volatility_state** | [calculation_engine.py#L195-L255](apps/reference/domains/feature_engineering/calculation_engine.py#L195-L255) | `compute_volatility_state()` | `current_range / avg_range`, capped |
| **macro_sync** | [macro_sync_resampler.py#L130-L240](apps/reference/domains/feature_engineering/macro_sync_resampler.py#L130-L240) | `MacroSyncResampler.compute()` | Pearson corr on time-aligned returns |
| **liquidity_kappa** | [feature_engineering.py#L515-L520](apps/reference/domains/feature_engineering/feature_engineering.py#L515-L520) | inline in `_calculate_and_emit_features` | `depth_usd / (depth_usd + depth_half)` |
| **absorption** | N/A | Placeholder only | Returns `cfg.zero_value` (0.0) |
| **delta_price** | [feature_engineering.py#L505-L510](apps/reference/domains/feature_engineering/feature_engineering.py#L505-L510) | inline | `price - prev_price` (with spike filter) |
| **OBI** | [feature_engineering.py#L498-L500](apps/reference/domains/feature_engineering/feature_engineering.py#L498-L500) | inline | `(bid_size - ask_size) / (bid_size + ask_size)` |
| **TFI** | [feature_engineering.py#L502-L504](apps/reference/domains/feature_engineering/feature_engineering.py#L502-L504) | inline | `(buy_volume - sell_volume) / total_flow` |
| **depth_imbalance** | [calculation_engine.py#L355-L385](apps/reference/domains/feature_engineering/calculation_engine.py#L355-L385) | `compute_depth_imbalance()` | Laplace-smoothed `(ask+half)/(bid+half)` ratio |

---

## 2) Config SSOT Map

### Активні YAML файли в live (по entrypoint)

```
config/aurora/
├── system.yaml          # System/service meta, market_data, tick_ttl
├── trading.yaml         # binance_api, execution, risk soft_limits
├── domains.yaml         # CANONICAL domain configs (decision_making, feature_engineering, etc.)
├── instruments.yaml     # Per-symbol specs (step_size, leverage, min_qty)
├── strategies.yaml      # Strategy registry (assignments, arbitration)
├── strategies/
│   ├── aurora.yaml      # Aurora tick-based strategy config
│   └── mean_reversion.yaml  # MR bar-based strategy config
└── regime.yaml          # Regime detector models (SMA, volatility, MR)
```

### Config Loading Chain

```
ConfigLoader.load()
    └── Loads: system.yaml + trading.yaml + regime.yaml + domains.yaml
    └── Merges via deep_merge() with provenance tracking
    └── Loads: strategies.yaml → strategies/aurora.yaml + mean_reversion.yaml
    └── Loads: instruments.yaml
    └── Validates via PydanticAuroraConfig (extra='forbid')
    └── DomainConfigResolver wraps for typed access
```

### Config Key → YAML Path → Pydantic Field → Runtime Usage Matrix

| Config Key | YAML Path | Pydantic Field | Runtime File:Line |
|------------|-----------|----------------|-------------------|
| `normalize_signals_mode` | `strategies/aurora.yaml::aurora.decision.signals.normalize_signals_mode` | `AuroraDecisionConfig.signals.normalize_signals_mode` | [decision_making.py#L1100+](apps/reference/domains/decision_making/decision_making.py#L1100) via `compute_direction_strength_score()` |
| `directional_features` | `strategies/aurora.yaml::aurora.decision.direction_strength_scoring.directional_features` | `DirectionStrengthScoringConfig.directional_features` | [scoring_direction_strength_v1.py#L100](apps/reference/domains/decision_making/scoring_direction_strength_v1.py#L100) |
| `strength_features` | `strategies/aurora.yaml::aurora.decision.direction_strength_scoring.strength_features` | `DirectionStrengthScoringConfig.strength_features` | [scoring_direction_strength_v1.py#L101](apps/reference/domains/decision_making/scoring_direction_strength_v1.py#L101) |
| `strength_alpha` | `strategies/aurora.yaml::aurora.decision.direction_strength_scoring.strength_alpha` | `DirectionStrengthScoringConfig.strength_alpha` | [scoring_direction_strength_v1.py#L102](apps/reference/domains/decision_making/scoring_direction_strength_v1.py#L102) |
| `strength_cap` | `strategies/aurora.yaml::aurora.decision.direction_strength_scoring.strength_cap` | `DirectionStrengthScoringConfig.strength_cap` | [scoring_direction_strength_v1.py#L103](apps/reference/domains/decision_making/scoring_direction_strength_v1.py#L103) |
| `liquidity_gate.kappa_min` | `strategies/aurora.yaml::aurora.decision.liquidity_gate.kappa_min` | `LiquidityGateConfig.kappa_min` | DecisionMaking `_check_liquidity_gate()` |
| `feature_neutrals` | `strategies/aurora.yaml::aurora.decision.feature_neutrals` | `Dict[str, float]` | [signal_score_v2.py#L65](apps/reference/domains/decision_making/signal_score_v2.py#L65) |
| `signal_weights` | `strategies/aurora.yaml::aurora.decision.signal_weights` | `Dict[str, float]` | [signal_score_v2.py#L80](apps/reference/domains/decision_making/signal_score_v2.py#L80) |
| `volatility_state_cap` | `domains.yaml::feature_engineering.volatility_state.cap_max` | `VolatilityStateConfig.cap_max` | [calculation_engine.py#L250](apps/reference/domains/feature_engineering/calculation_engine.py#L250) |
| `macro_sync.anchors` | `domains.yaml::feature_engineering.macro_sync.anchors` | `MacroSyncConfig.anchors` | [feature_engineering.py#L110](apps/reference/domains/feature_engineering/feature_engineering.py#L110) |
| `essential_features` | `strategies/aurora.yaml::aurora.decision.essential_features` | `List[str]` | [signal_score_v2.py#L85](apps/reference/domains/decision_making/signal_score_v2.py#L85) |

### Must-Change Keys (Stage 2)

| Key | Current Location | Change Required |
|-----|------------------|-----------------|
| `volatility_state.hard_floor` | **NEW** in `domains.yaml::feature_engineering.volatility_state` | Add `tick_floor`, `hist_floor` |
| `spread_bps.health_gate` | **NEW** in `domains.yaml::feature_engineering` | Add `book_update_age_max_sec`, `min_changes_count` |
| `feature_sanity.nan_inf_firewall` | **NEW** in `domains.yaml::feature_engineering` | Add `enabled: true`, `fallback: neutral` |
| `absorption_mode` | **NEW** in `domains.yaml::feature_engineering` or `strategies/aurora.yaml` | Add `disabled\|proxy\|full` |
| `readiness_registry` | **NEW** in `domains.yaml::feature_engineering` | Add explicit list of declared ready keys |

---

## 2.5) Global Contract: No Silent Fallbacks / No Runtime Hardcodes

> **КРИТИЧНІСТЬ:** Цей контракт є **обов'язковим** для Stage 2 і всіх наступних етапів. Порушення = P0 блокер.

### Принцип

**Жодних silent fallbacks, жодних hardcoded значень у runtime** — усе через YAML → Pydantic → валідацію.

Причина: hardcoded fallbacks приховують проблеми конфігурації, роблять систему непередбачуваною, і ускладнюють налагодження ("чому система торгує з eps=1e-8, якого немає в конфізі?").

---

### Правила (без двозначностей)

1. **Будь-який параметр, що впливає на рішення/торгівлю** (пороги, eps, caps, lookbacks, tick multipliers, health thresholds, dedup thresholds, weight multipliers) **має бути в YAML**.

2. **Будь-який YAML key має бути в Pydantic model** і проходити `config-validate` при старті. Unknown keys = error (`extra='forbid'`).

3. **Runtime НЕ МАЄ ПРАВА робити `.get(key, default)` або `or <literal>`** для параметрів, що впливають на рішення.
   - ❌ Заборонено: `cfg.get("eps", 1e-8)`
   - ❌ Заборонено: `val = cfg.eps or 0.001`
   - ✅ Дозволено: `cfg.eps` (Pydantic гарантує наявність через required field або explicit default в schema)

4. **Єдиний допустимий "fallback"** — ТІЛЬКИ якщо:
   - Він **НЕ впливає на торгове рішення** (лише телеметрія/лог)
   - І це **явно прописано в контракті** (example: "fallback used only for telemetry when feature_ready=False")
   - І fallback value **не використовується в scoring/gates**

5. **Якщо ключ відсутній/невідомий/невалідний:**
   - На старті: **fail-fast** через ConfigContractError
   - У runtime: **DEFER** з явним `NRR/why_code` (не silent skip)

6. **Заборонені патерни в production коді:**
   ```python
   # ❌ FORBIDDEN
   denom = max(avg_range, 1e-8)  # hardcoded eps
   threshold = cfg.get("threshold", 0.5)  # silent default
   value = some_dict.get(key) or 0.0  # fallback to literal
   lookback = getattr(cfg, "lookback", 100)  # silent default via getattr
   
   # ✅ ALLOWED
   denom = max(avg_range, cfg.volatility_eps)  # from config
   threshold = cfg.threshold  # Pydantic guarantees presence
   value = cfg.feature_neutrals[key]  # KeyError if missing = fail-fast
   lookback = cfg.lookback  # required field in Pydantic
   ```

---

### Examples: Allowed vs Forbidden

| Context | Forbidden (hardcode) | Allowed (config-driven) |
|---------|---------------------|------------------------|
| **Volatility floor** | `denom = max(avg_range, 1e-8)` | `denom = max(avg_range, cfg.volatility_tick_floor)` |
| **Spread health age** | `if age > 5.0:` | `if age > cfg.spread_health_max_age_sec:` |
| **Dedup threshold** | `if corr > 0.8:` | `if corr > cfg.absorption_dedup_threshold:` |
| **Score cap** | `score = min(score, 3.0)` | `score = min(score, cfg.score_cap)` |
| **Fallback neutral** | `neutral = features.get("obi", 0.0)` | `neutral = cfg.feature_neutrals["obi"]` (KeyError = fail-fast) |
| **Lookback window** | `window = 100` | `window = cfg.volatility_lookback_bars` |
| **Epsilon for division** | `x / (y + 1e-10)` | `x / (y + cfg.division_eps)` |

**Єдиний виняток — математичні константи:**
```python
# ✅ Allowed: mathematical constants that are not configurable by design
import math
phi = (1 + math.sqrt(5)) / 2  # Golden ratio
pi = math.pi
```

---

### Enforcement Checklist (Stage 3 Audit)

| # | Check | Tool/Method | PASS Criteria |
|---|-------|-------------|---------------|
| 1 | **Grep for hardcoded fallbacks** | `grep -rn "\.get\(.*,\s*[0-9]" apps/` | 0 matches in decision/scoring paths |
| 2 | **Grep for `or <literal>`** | `grep -rn "or\s\+[0-9]\|or\s\+0\." apps/` | 0 matches in decision/scoring paths |
| 3 | **Grep for getattr with default** | `grep -rn "getattr.*,\s*[0-9]" apps/` | 0 matches for config params |
| 4 | **Pydantic extra=forbid** | Check all config models | All trading-related models have `extra='forbid'` |
| 5 | **Required fields audit** | Pydantic schema review | All P0/P1 params are `Field(...)` without `default=` or with explicit `default` in schema |
| 6 | **Config-validate test** | `pytest tests/config/` | Test that missing P0 params → ConfigContractError |
| 7 | **Runtime fallback audit** | Code review | All `.get()` usages have explicit comment: "telemetry only" |
| 8 | **Magic number scan** | `grep -rn "[0-9]\.[0-9]" apps/reference/domains/` | Review each: is it config-driven or mathematical constant? |

**Automated enforcement (recommended):**
```bash
# Add to CI/pre-commit
./scripts/audit_hardcodes.sh --fail-on-match
```

---

### Impact Statement: P0/P1 Parameters That MUST Be Config-Driven

| Priority | Parameter | Current State | Required Change |
|----------|-----------|---------------|-----------------|
| **P0-0** | `readiness_registry.declared_keys` | Hardcoded in FE | Move to `domains.yaml` |
| **P0-1** | `volatility_tick_floor` | **NEW** | Add to `domains.yaml::feature_engineering.volatility_state` |
| **P0-1** | `volatility_hist_floor` | **NEW** | Add to `domains.yaml::feature_engineering.volatility_state` |
| **P0-1** | `volatility_eps` (division safety) | Hardcoded or missing | Add to `domains.yaml` |
| **P0-2** | `spread_health_max_age_sec` | **NEW** | Add to `domains.yaml::feature_engineering.spread_bps` |
| **P0-2** | `spread_health_min_update_events` | **NEW** | Add to `domains.yaml::feature_engineering.spread_bps` |
| **P0-3** | `feature_bounds.*` | **NEW** | Add to `domains.yaml::feature_engineering.feature_sanity` |
| **P1** | `macro_resid_lookback` | **NEW** (if implementing) | Add to `domains.yaml::feature_engineering.macro_sync` |
| **P1** | `macro_resid_clamp` | **NEW** (if implementing) | Add to `domains.yaml::feature_engineering.macro_sync` |
| **P2** | `absorption_dedup_threshold` | **NEW** | Add to `domains.yaml::feature_engineering.absorption` |

---

### Contract Signature

> **КОНТРАКТ (Amendment A2):** Stage 2 agent ЗОБОВ'ЯЗАНИЙ:
> 1. Не додавати hardcoded значень для параметрів, що впливають на рішення
> 2. Усі нові параметри додавати в YAML + Pydantic schema
> 3. Використовувати `cfg.<param>` замість `.get(key, default)`
> 4. При code review перевіряти Enforcement Checklist
> 5. Якщо потрібен fallback для телеметрії — додати explicit коментар

---

## 3) P0 Plan: Safety + Truth Validation (Design)

### P0-0: Readiness Contract Audit (BLOCKER)

> **КРИТИЧНІСТЬ:** Цей пункт є **блокером** для всіх інших P0. Без нього система може мовчки зависнути в DEFER назавжди після одного рядка в YAML — і ти будеш тиждень думати, що "ринок такий".

**Проблема (Config Drift):**

```python
# SignalScoreV2 (signal_score_v2.py:L127)
is_ready = readiness.get(feat, False)  # Missing key = NOT ready!
if not is_ready:
    if feat in essential_features:
        not_ready.append(feat)  # → DEFER
```

Якщо `essential_features` (YAML) містить ключ, якого НЕМАЄ в `warmup.ready` (Python hardcode) → **silent DEFER forever**.

**Поточний стан:**

| Component | Location | Keys |
|-----------|----------|------|
| `ready_map` (hardcoded) | [feature_engineering.py#L636-L652](apps/reference/domains/feature_engineering/feature_engineering.py#L636-L652) | obi, tfi, delta_price, depth_imbalance, liquidity_kappa, absorption, ema_bias, volume_spike, volatility_state, macro_sync, spread_bps, large_trade_imbalance, volume_zscore |
| `essential_features` (config) | [aurora.yaml#L104-L106](config/aurora/strategies/aurora.yaml#L104-L106) | obi, delta_price |

**GAP:** Немає валідації `essential_features ⊆ ready_map.keys()`.

---

#### Deliverable 1: Startup Validation (Fail-Fast)

**Contract:** `essential_features ⊆ declared_ready_keys`

```python
# config_loader.py або domain_config.py — при завантаженні конфігу
def _validate_essential_features_contract(cfg: AuroraConfig) -> None:
    """
    Fail-fast: essential_features must be subset of declared readiness keys.
    """
    DECLARED_READY_KEYS = {
        "obi", "tfi", "delta_price", "depth_imbalance", "liquidity_kappa",
        "absorption", "ema_bias", "volume_spike", "volatility_state",
        "macro_sync", "spread_bps", "large_trade_imbalance", "volume_zscore"
    }
    
    essential = set(cfg.strategies.aurora.decision.essential_features)
    missing = essential - DECLARED_READY_KEYS
    
    if missing:
        raise ConfigContractError(
            path="strategies.aurora.decision.essential_features",
            why=f"Essential features {missing} are not in DECLARED_READY_KEYS registry. "
                f"Either add them to FE ready_map or remove from essential_features.",
        )
```

**Або краще — SSOT через config:**

```yaml
# domains.yaml::feature_engineering
readiness_registry:
  declared_keys:
    - obi
    - tfi
    - delta_price
    - depth_imbalance
    - liquidity_kappa
    - absorption
    - ema_bias
    - volume_spike
    - volatility_state
    - macro_sync
    - spread_bps
    - large_trade_imbalance
    - volume_zscore
```

**Acceptance:** Якщо `volatility_state` додано в `essential_features`, але його немає в registry → startup FAIL з чітким повідомленням.

---

#### Deliverable 2: Runtime Detection + Visibility

**Location:** [decision_making.py#L2517](apps/reference/domains/decision_making/decision_making.py#L2517)

```python
readiness_map = features_evt.get("warmup", {}).get("ready", {})

# P0-0: Detect missing ready keys BEFORE passing to scorer
essential_set = set(essential_features)
missing_ready_keys = essential_set - set(readiness_map.keys())

if missing_ready_keys:
    # 1. Log WARN (rate-limited)
    self.logger.warning(
        f"[{symbol}] MISSING_READY_KEYS: essential features {missing_ready_keys} "
        f"not in warmup.ready → will DEFER. This is likely a config/code drift."
    )
    
    # 2. Metric
    for key in missing_ready_keys:
        inc_missing_ready_key(domain="decision_making", feature=key, symbol=symbol)
    
    # 3. NRR with explicit reason
    self._emit_nrr(
        symbol=symbol,
        reason=NormalizedRejectReasons.MISSING_READY_KEYS,
        why=f"MISSING_READY_KEYS:{','.join(missing_ready_keys)}",
    )
    self._record_blocked_intent(symbol)
    return
```

**NRR Code (NEW):**

```python
# normalized_reject_reasons.py
class NormalizedRejectReasons:
    ...
    MISSING_READY_KEYS = "MISSING_READY_KEYS"  # essential feature key not in warmup.ready
```

**Metric (NEW):**

```python
# metrics.py
def inc_missing_ready_key(domain: str, feature: str, symbol: str) -> None:
    """Count missing ready key occurrences."""
    MISSING_READY_KEY_TOTAL.labels(domain=domain, feature=feature, symbol=symbol).inc()
```

---

#### Deliverable 3: Invariant `full_ready ⇒ no missing`

**Contract:** Якщо `warmup.full_ready=True`, то `missing_ready_keys == ∅`

```python
# feature_engineering.py, коли формуємо warmup dict
full_ready = all(ready_map.values())

# P0-0: Invariant check
if full_ready:
    # All keys that could be essential MUST be present
    required_keys = set(self.cfg.readiness_registry.declared_keys)
    actual_keys = set(ready_map.keys())
    if required_keys != actual_keys:
        self.logger.error(
            f"[{symbol}] INVARIANT VIOLATION: full_ready=True but "
            f"ready_map.keys()={actual_keys} != declared_keys={required_keys}"
        )
        inc_invariant_violation(domain="feature_engineering", invariant="full_ready_keys_mismatch")
        # Don't crash, but mark as not ready
        full_ready = False

warmup["full_ready"] = full_ready
```

---

#### P0-0 Config Changes

```yaml
# domains.yaml::feature_engineering
readiness_registry:
  # SSOT: all keys that FE can emit in warmup.ready
  declared_keys:
    - obi
    - tfi
    - delta_price
    - depth_imbalance
    - liquidity_kappa
    - absorption
    - ema_bias
    - volume_spike
    - volatility_state
    - macro_sync
    - spread_bps
    - large_trade_imbalance
    - volume_zscore

# ═══════════════════════════════════════════════════════════════════════════════
# WARMUP ENFORCEMENT: ОБОВ'ЯЗКОВИЙ РЕЖИМ (НЕ ПЕРЕМИКАЧ!)
# ═══════════════════════════════════════════════════════════════════════════════
# 
# КОНТРАКТ: Система ЗАВЖДИ чекає повного прогріву ВСІХ essential features
# перед торгівлею. Це НЕ опція, яку можна вимкнути.
#
# Цей параметр існує ТІЛЬКИ для backward compatibility та тестування.
# В production він ЗАВЖДИ має бути "fail_fast".
# 
# ⚠️  ЗАБОРОНЕНО встановлювати "warn_only" або "disabled" в production!
# ⚠️  CI/CD pipeline ПОВИНЕН перевіряти це при деплої.
# ═══════════════════════════════════════════════════════════════════════════════
warmup:
  # ОБОВ'ЯЗКОВО: fail_fast — система не торгує поки всі фічі не ready
  enforcement_mode: fail_fast  # LOCKED: fail_fast (warn_only/disabled заборонені в prod)
  
  # Валідація essential ⊆ declared_keys при старті
  validate_essential_subset: true  # LOCKED: true (не можна вимкнути)
  
  # Інваріант: full_ready=True ⇒ всі declared_keys присутні
  check_full_ready_invariant: true  # LOCKED: true (не можна вимкнути)
```

> **КОНТРАКТ (Amendment A3 — Warmup Mandatory):**
> 
> 1. **Warmup є ОБОВ'ЯЗКОВИМ** — система НІКОЛИ не торгує до повного прогріву всіх essential features
> 2. **Це НЕ перемикач** — параметр `enforcement_mode` існує тільки для тестів і backward compatibility
> 3. **В production `enforcement_mode` ЗАВЖДИ = `fail_fast`**
> 4. **CI/CD validation:** При деплої перевіряти: `enforcement_mode == "fail_fast"`, інакше FAIL pipeline
> 5. **Заборонено:** `warn_only` (логує але торгує) та `disabled` (ігнорує warmup)

---

#### P0-0 Acceptance Criteria

| Criterion | PASS | FAIL |
|-----------|------|------|
| Startup fails if `essential ⊄ declared_keys` | ConfigContractError raised | Silent pass |
| Runtime logs WARN on missing ready key | Log visible in stdout/file | Silent DEFER |
| Metric `missing_ready_key_total` incremented | Grafana shows spikes | No visibility |
| `full_ready=True` implies all declared keys present | Invariant holds | `full_ready=True` with missing keys |

---

### P0-1: Volatility_state Overflow Fix

**Поточна формула та місце в коді:**

```python
# calculation_engine.py:L240-L255
avg_range = decimal.Decimal(str(mean))  # from Welford stats
current_range = state.range_max - state.range_min
if avg_range > 0:
    ratio = current_range / avg_range  # ⚠️ OVERFLOW if avg_range → 0
    ratio_capped = min(ratio, self.cfg.volatility_state_cap)
    phi = ratio_capped / self.cfg.volatility_state_cap
```

**Причина overflow (математика):**
- Flat market: `range_max ≈ range_min` → `current_range → 0`
- Historical: якщо всі попередні бари теж flat → `avg_range → 0`
- Division: `0 / 0 = NaN` або `small / tiny = huge`

**Запропонована hard floor формула:**

> **КОНТРАКТ (Amendment A1-E):** `tick_floor` та `hist_floor` вимірюються в **price units** (не bps). Визначаються per-asset через instruments config. Типова формула: `tick_floor = tick_size * K`, де K — per-asset multiplier.

```python
# PROPOSED FIX:
# tick_floor/hist_floor in PRICE UNITS (per-asset from instruments.yaml)
tick_floor = Decimal(str(self.cfg.volatility_tick_floor))  # e.g., 0.01 for BTCUSDT (1 tick = $0.01)
hist_floor = Decimal(str(self.cfg.volatility_hist_floor))  # e.g., 1.0 for BTCUSDT (min $1 range)

denom = max(avg_range, tick_floor, hist_floor)  # Safe: denom >= tick_floor > 0
ratio = current_range / denom

# NaN/Inf firewall
if not ratio.is_finite():
    state.volatility_state_ready = False
    state.volatility_state_not_ready_reason = "overflow_nan_inf"
    return self.cfg.neutral_value

ratio_capped = min(ratio, self.cfg.volatility_state_cap)
phi = ratio_capped / self.cfg.volatility_state_cap
```

**Де буде реалізовано:**
- File: [calculation_engine.py](apps/reference/domains/feature_engineering/calculation_engine.py)
- Function: `compute_volatility_state()`
- Line: ~L245-L260

**Логування/NRR:**
- `inc_data_quality_drop(domain="feature_engineering", reason="volatility_overflow")`
- Warmup `reasons.append("volatility_state:overflow_nan_inf")`
- NRR code: `NRR-FEATURES-NOT-READY:volatility_state`

---

### P0-2: Spread Truth Validation (Book Health Gate)

**Чому std(spread) не можна використовувати як stale-detector:**

Ринкова причина: На справді ліквідних ринках (BTC, ETH під час low-vol periods) spread може бути stable AND tight (1-3 bps) протягом тривалого часу. `std(spread) ≈ 0` в цьому випадку — це НОРМАЛЬНО, не stale.

Stale book detection потребує **timestamp-based** або **update-count-based** validation.

**Запропонований health gate (Book Health Matrix):**

```python
@dataclass
class BookHealthGate:
    book_update_age_sec: float       # max(now - last_bid_update, now - last_ask_update)
    book_update_events_count: int    # # of ANY book updates (qty/levels/price) in window
    trades_seen: int                 # # of trades received in window
    
    def is_healthy(self, cfg: BookHealthConfig) -> bool:
        """
        3-Step Health Matrix:
        1. IF book_age > max_age → UNHEALTHY (hard fail, no exceptions)
        2. ELSE IF (book_updates >= min OR trades >= min) → HEALTHY
        3. ELSE → UNHEALTHY
        """
        # STEP 1: Hard age check — no exceptions
        if self.book_update_age_sec > cfg.max_age_sec:
            return False  # UNHEALTHY — book definitely stale
        
        # STEP 2: Activity check (book is fresh, check for activity)
        has_book_activity = self.book_update_events_count >= cfg.min_update_events
        has_trade_activity = self.trades_seen >= cfg.min_trades
        
        if has_book_activity or has_trade_activity:
            return True  # HEALTHY
        
        # STEP 3: No activity despite fresh timestamp
        return False  # UNHEALTHY — silent book
```

> **ВАЖЛИВО (Amendment A1-B):** `book_update_events_count` рахує **будь-які** оновлення order book (зміна qty, levels, price), а НЕ тільки зміну best bid/ask price. На ліквідних парах ціна може стояти, але глибина змінюється постійно — це HEALTHY.

> **КОНТРАКТ (Amendment A1-C):** Health gate має explicit 3-step матрицю: 1) `book_age > max` → UNHEALTHY (hard, без варіантів); 2) Інакше `(updates >= min OR trades >= min)` → HEALTHY; 3) Інакше → UNHEALTHY. OR-логіка застосовується ТІЛЬКИ якщо book свіжа.

**Config keys (NEW):**

```yaml
# domains.yaml::feature_engineering
spread_bps:
  health_gate:
    enabled: true
    max_age_sec: 5              # STEP 1: Hard fail if book older than this
    min_update_events: 1        # STEP 2: Min book update events (any: qty/levels/price)
    min_trades_count: 1         # STEP 2: Min trades in window (OR with update_events)
    window_sec: 10              # Lookback window for counting
```

**Runtime behavior при unhealthy:**
1. `feature_ready['spread_bps'] = False`
2. `warmup['reasons'].append("spread_bps:book_stale")`
3. `inc_data_quality_drop(domain="feature_engineering", reason="book_stale")`
4. НЕ робити zscore/ratio поки unhealthy
5. Downstream (DecisionMaking): feature not_ready → scoring skips or DEFERs

---

### P0-3: Feature Sanity Firewall

**Політика:**

```
NaN/Inf/out-of-range → feature_ready=False → DEFER, не торгувати
```

**Implementation location:**

```python
# feature_engineering.py, before adding to features{} dict
def _sanitize_feature(self, name: str, value: Decimal, hot: HotState) -> Decimal:
    """Central sanity check for all features."""
    
    # NaN/Inf check (Decimal doesn't have Inf, but float conversion might)
    try:
        val_float = float(value)
        if not math.isfinite(val_float):
            hot.set_feature_not_ready(name, "nan_or_inf")
            return self.cfg.neutral_value  # ONLY for telemetry, NOT for scoring
    except (ValueError, OverflowError):
        hot.set_feature_not_ready(name, "overflow")
        return self.cfg.neutral_value  # ONLY for telemetry, NOT for scoring
    
    # Range check (feature-specific bounds)
    bounds = self.cfg.feature_bounds.get(name)
    if bounds and not (bounds.min <= value <= bounds.max):
        hot.set_feature_not_ready(name, "out_of_range")
        return self.cfg.neutral_value  # ONLY for telemetry, NOT for scoring
    
    return value
```

> **КОНТРАКТ (Amendment A1-D):** Якщо `feature_ready=False`, значення фічі **НЕ МАЄ ПРАВА** входити в scoring/gates. Fallback value використовується **ТІЛЬКИ** для телеметрії/логів. Scoring kernel ОБОВ'ЯЗКОВО перевіряє `feature_ready` і виключає not_ready фічі з формули.

**Config (NEW):**

```yaml
# domains.yaml::feature_engineering
feature_sanity:
  enabled: true
  nan_inf_behavior: neutral_and_not_ready  # or: neutral_only | crash
  
  # ВАЖЛИВО: bounds відповідають семантиці фічі
  feature_bounds:
    # Signed features (directional)
    obi: {min: -1.0, max: 1.0}              # Order Book Imbalance
    tfi: {min: -1.0, max: 1.0}              # Trade Flow Imbalance
    delta_price: {min: -inf, max: +inf}     # Unbounded signed
    macro_resid: {min: -3.0, max: 3.0}      # Clamped z-score (signed)
    
    # Normalized features [0, 1]
    ema_bias: {min: 0.0, max: 1.0}
    volatility_state: {min: 0.0, max: 1.0}
    liquidity_kappa: {min: 0.0, max: 1.0}
    
    # Raw physical features (non-negative)
    spread_bps_raw: {min: 0.0, max: 10000.0}  # Physical spread, always ≥0
    volume_spike: {min: 0.0, max: +inf}       # Ratio, always ≥0
    
    # Signed deviation features (if implemented)
    # spread_dev: {min: -10.0, max: 10.0}     # z-score style, neutral=0
```

> **КОНТРАКТ (Amendment A1-A):** `spread_bps_raw` — фізичний спред, завжди ≥0. Якщо в майбутньому додаємо `spread_dev` (signed deviation від baseline), це ОКРЕМА фіча з власними bounds `{min: -X, max: +X}`. Одна фіча НІКОЛИ не змінює семантику (raw→signed) без явного перейменування.

---

## 4) P1 Plan: Feature Quality (Design)

### P1-1: macro_sync → macro_resid Enhancement

**Поточний стан:**
- `macro_sync` повертає correlation [0, 1] (normalized)
- Interpretation: 0.5 = neutral, >0.5 = correlated, <0.5 = anti-correlated

**Запропонована формула (macro_resid):**

```python
# NEW: Idiosyncratic return residual
# resid = r_alt - beta * r_btc
# Де: r_alt = return of altcoin, r_btc = return of BTC anchor

def compute_macro_resid(
    symbol_returns: List[float],
    anchor_returns: List[float],
    lookback: int = 60,
) -> MacroResidResult:
    """Compute beta-adjusted residual for direction signal."""
    
    if len(symbol_returns) < lookback or len(anchor_returns) < lookback:
        return MacroResidResult(resid=0.0, ready=False, why="insufficient_data")
    
    # Rolling beta via OLS or simplified formula
    x = anchor_returns[-lookback:]
    y = symbol_returns[-lookback:]
    
    cov_xy = np.cov(x, y)[0, 1]
    var_x = np.var(x)
    beta = cov_xy / max(var_x, 1e-10)  # Avoid div by zero
    
    # Current residual
    resid = y[-1] - beta * x[-1]
    
    # Robust scaling (MAD/Huber)
    resid_history = [y[i] - beta * x[i] for i in range(lookback)]
    mad = np.median(np.abs(np.array(resid_history) - np.median(resid_history)))
    
    if mad < 1e-10:
        resid_scaled = 0.0  # No variation = neutral
    else:
        resid_scaled = resid / (1.4826 * mad)  # Consistent with normal std
        resid_scaled = np.clip(resid_scaled, -3.0, 3.0)  # Clamp outliers
    
    return MacroResidResult(resid=resid_scaled, ready=True, why=None)
```

**Нейтраль:** `resid = 0` (ідеально слідує за BTC)  
**Signed:** Positive = outperforming BTC (bullish idio), Negative = underperforming  

**Config location:**

```yaml
# domains.yaml::feature_engineering.macro_sync
macro_resid:
  enabled: false  # P1 — opt-in
  lookback_bins: 60
  scaling_mode: mad  # mad | huber | zscore
  clamp: 3.0
```

---

### P1-2: liquidity_kappa — Gate Only

**Поточний стан:**
- `liquidity_kappa` обчислюється і включено в features{}
- Використовується як gate (not weighted) в DecisionMaking

**Запропоноване уточнення:**

1. **Gate only:** Залишити як hard gate (не weighted feature)
2. **Optional deviation metric:** Для penalty можна додати:

```python
# Optional: deviation from expected liquidity
kappa_baseline = rolling_mean(kappa_history, window=100)
kappa_deviation = (kappa - kappa_baseline) / max(kappa_baseline, 0.1)
```

Але це НЕ direction signal, лише penalty multiplier на sizing.

**Config validation:**

```yaml
# strategies/aurora.yaml
liquidity_gate:
  enabled: true
  mode: gate_only  # gate_only | gate_and_penalty
  kappa_min: 0.1
  kappa_max: 1.0
  # penalty config (if mode=gate_and_penalty)
  penalty:
    deviation_multiplier: 0.5  # reduce size by 50% of deviation
```

---

### P1-3: Dead/Constant Features Policy

**absorption placeholder:**
- Currently returns `cfg.zero_value` (0.0) always
- Should be `disabled` by default, weight=0

**Config-validate contract:**

```yaml
# strategies/aurora.yaml::aurora.decision
signal_weights:
  absorption: 0.0  # MUST be 0 if not implemented

# domains.yaml::feature_engineering
absorption:
  mode: disabled  # disabled | placeholder | proxy | full
```

**Validation at startup:**

```python
# ConfigLoader or DomainConfigResolver
def _validate_feature_weights_vs_implementation():
    absorption_mode = cfg.feature_engineering.absorption.mode
    absorption_weight = cfg.strategies.aurora.decision.signal_weights.get("absorption", 0)
    
    if absorption_mode == "disabled" and absorption_weight != 0:
        raise ConfigContractError(
            path="signal_weights.absorption",
            why="absorption weight must be 0 when mode=disabled"
        )
```

---

## 5) P2 Plan: Experimental (Design)

### P2-1: Absorption Implementation

**Config modes:**

```yaml
# domains.yaml::feature_engineering
absorption:
  mode: disabled  # disabled | proxy | full
  
  proxy:  # Only if mode=proxy
    source: aggressive_trade_imbalance  # НЕ TFI! Окрема фіча на основі buyer_maker
    correlation_threshold: 0.8  # Auto-mute if corr(proxy, TFI) > threshold → redundant
    
  full:  # Only if mode=full
    book_levels: 5
    sync_mode: timestamp_align  # Require book↔trades sync
```

> **КОНТРАКТ (Amendment A1-G):** `proxy.source` НІКОЛИ не може бути `tfi` — це логічний абсурд (corr=1.0 завжди → завжди mute). Proxy має бути ОКРЕМА фіча, яка корелює з absorption behavior, наприклад `aggressive_trade_imbalance` (buyer_maker weighted).

**Proxy режим:**
- Використовує **іншу** фічу (e.g., `aggressive_trade_imbalance`) як proxy для absorption
- **Deduplication guard:** Якщо `corr(proxy, TFI) > 0.8`, auto-mute proxy (воно redundant до TFI)
- Тільки для статистики/feature-health, не для direction

**Full режим:**
- Потребує: proven book↔trades sync
- **Definition of "proven":** 
  1. Book update timestamps correlate with trade timestamps (within 50ms)
  2. No systematic lag detected over 1000+ samples
  3. Manual verification on testnet for 24h

**Conditions to enable full:**

```yaml
# Stage 3 requirements before enabling absorption.mode=full:
# 1. Book/trades sync verified: corr(book_update_ts, trade_ts) > 0.95
# 2. No systematic lag: mean(trade_ts - book_ts) < 50ms
# 3. Test coverage: 100+ synthetic scenarios passed
# 4. Production soak: 48h on testnet with metrics collection
```

---

## 6) Strategy Coverage: Aurora + MR + Others

### Decision Paths Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    AURORA PATH (Tick-Based)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  EVT:FEATURES_CALCULATED                                         │
│         ↓                                                        │
│  DecisionMaking.on_features()                                    │
│         ↓                                                        │
│  1. Warmup gate (full_ready check)                               │
│  2. Risk gate (is_trading_allowed, risk_score)                   │
│  3. Features TTL gate                                            │
│  4. QoS gate (cooldown)                                          │
│  5. Signal Score V2: compute_direction_strength_score()          │
│         ↓                                                        │
│  side = "BUY" if dir_score > threshold else "SELL" if < -thresh  │
│         ↓                                                        │
│  EVT:TRADE_INTENT_PROPOSED                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    MR PATH (Bar-Based)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  EVT:MARKET_TICK_RECEIVED                                        │
│         ↓                                                        │
│  MeanReversionHandler._on_market_tick()                          │
│         ↓                                                        │
│  BarResampler.add_tick() → Bar completion?                       │
│         ↓ (if bar complete)                                      │
│  MeanReversion1mStrategy.on_bar_complete()                       │
│         ↓                                                        │
│  1. Regime gate (FLAT_* only)                                    │
│  2. Bollinger Bands signal (price vs bands)                      │
│  3. Cooldown gate                                                │
│         ↓                                                        │
│  EVT:STRATEGY_SIGNAL_PRODUCED                                    │
│         ↓                                                        │
│  DecisionMaking._on_strategy_signal_gateway()                    │
│         ↓                                                        │
│  [Same gates as Aurora: Risk, QoS, Exposure, Sizing]             │
│         ↓                                                        │
│  EVT:TRADE_INTENT_PROPOSED                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### P0/P1 Integration Points

**Shared components (global, affect both strategies):**

| Component | File | Used By |
|-----------|------|---------|
| FeatureEngineering (all features) | [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py) | Aurora, MR (via features dict) |
| volatility_state fix | [calculation_engine.py](apps/reference/domains/feature_engineering/calculation_engine.py) | Both |
| spread_bps health gate | [calculation_engine.py](apps/reference/domains/feature_engineering/calculation_engine.py) | Both |
| Feature sanity firewall | [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py) | Both |
| Warmup/readiness tracking | [feature_engineering.py#L640-L680](apps/reference/domains/feature_engineering/feature_engineering.py#L640-L680) | Both |

**Shared-library vs local adapters:**

```
SHARED (in vfoundation or apps/reference/utils):
├── Feature sanity utilities (NaN/Inf check)
├── Decimal safe operations
├── Timestamp normalization

LOCAL ADAPTERS (per-strategy):
├── Aurora: scoring_direction_strength_v1.py
├── MR: mean_reversion_strategy.py (Bollinger logic)
```

---

## 7) Test & Audit Plan (Stage 3 Preview)

### Unit Tests

| Test | File | Scenarios |
|------|------|-----------|
| **volatility_state overflow** | `tests/domains/feature_engineering/test_volatility_overflow.py` | avg_range=0, tiny avg_range, NaN injection |
| **spread health gate** | `tests/domains/feature_engineering/test_spread_health_gate.py` | stale book (age>5s), healthy book (age<5s + changes), edge cases |
| **macro_resid sign** | `tests/domains/feature_engineering/test_macro_resid.py` | outperform BTC→positive, underperform→negative |
| **directionality tests** | `tests/domains/decision_making/test_directionality.py` | SELL reachable with negative score, BUY with positive |
| **NaN/Inf firewall** | `tests/domains/feature_engineering/test_feature_sanity.py` | NaN input→neutral+not_ready, Inf→same |

### Synthetic Data Generation Spec

```python
# Scenario: Stale book + active trades
def generate_stale_book_scenario():
    return {
        "book_update_age_sec": 10.0,  # Stale
        "bid_changes_count": 0,
        "ask_changes_count": 0,
        "trades_seen": 50,  # Active trades = book might be lagging
        "expected": {"spread_ready": False, "reason": "book_stale"}
    }

# Scenario: Flat market avg_range→0
def generate_flat_market_scenario():
    bars = []
    for i in range(100):
        bars.append({
            "high": Decimal("50000.00"),
            "low": Decimal("50000.00"),  # No range
            "close": Decimal("50000.00"),
        })
    return {
        "bars": bars,
        "expected": {
            "volatility_state": Decimal("0.5"),  # neutral
            "volatility_state_ready": True,  # With fix, should be ready
            "used_floor": True,
        }
    }

# Scenario: Beta-following vs idio move
def generate_beta_following_scenario():
    btc_returns = [0.01, -0.005, 0.002, -0.001, 0.003]
    alt_returns = [0.01, -0.005, 0.002, -0.001, 0.003]  # Perfect tracking
    return {
        "btc_returns": btc_returns,
        "alt_returns": alt_returns,
        "expected": {"macro_resid": 0.0, "interpretation": "neutral"}
    }

def generate_idio_outperform_scenario():
    btc_returns = [0.01, -0.005, 0.002]
    alt_returns = [0.02, -0.002, 0.005]  # Outperforming
    return {
        "btc_returns": btc_returns,
        "alt_returns": alt_returns,
        "expected": {"macro_resid": ">0", "interpretation": "bullish_idio"}
    }

# Scenario: Tight tick spread stable but healthy
def generate_tight_healthy_spread_scenario():
    return {
        "spread_bps": 2.0,  # Tight
        "spread_std": 0.1,  # Low variance
        "book_update_age_sec": 0.5,  # Fresh
        "book_update_events_count": 10,  # ANY updates (qty/levels/price)
        "expected": {"spread_ready": True, "reason": None}
    }
```

### Acceptance Criteria (PASS/FAIL)

**Stage 2 Deployment:**

| Criterion | PASS | FAIL |
|-----------|------|------|
| volatility_state never returns NaN/Inf | All tests pass | Any NaN/Inf in output |
| spread_bps not_ready when book_age > 5s | 100% detection | Any false negative |
| **SELL Reachability Test** | На синтетиці з negative features (OBI<-0.3, TFI<-0.3, delta_price<0) система генерує SELL | 0 SELLs на негативному датасеті |
| Feature sanity blocks invalid inputs | NaN/Inf → not_ready in 100% cases | Any passthrough |
| Config validation at startup | Missing neutrals → ValueError | Silent ignore |

> **КОНТРАКТ (Amendment A1-F):** Acceptance criteria базуються на **reachability test**, а не на live ratio. Ринок може бути трендовим — 90% BUY це нормально. Але на СИНТЕТИЦІ з негативними directional features SELL **ОБОВ'ЯЗКОВО** має спрацювати.

**Stage 3 Full Audit:**

| Criterion | PASS | FAIL |
|-----------|------|------|
| 48h testnet soak without crashes | 0 exceptions | Any crash |
| No unexpected NRR spikes | NRR rate < 5% of decisions | > 10% |
| **SELL Sanity (live)** | SELL ≠ 0 за 7 днів торгівлі | 0 SELLs за 7+ днів (suspicious) |
| Latency p99 | < 50ms tick→intent | > 100ms |

---

## 8) Deployment Plan (Stage 2 Preview)

### Feature Flags / Safe Defaults

```yaml
# domains.yaml - Stage 2 deployment
feature_engineering:
  volatility_state:
    cap_max: 3.0
    hard_floor_enabled: true  # NEW
    tick_floor: 0.0001
    hist_floor: 0.001
    
  spread_bps:
    health_gate:
      enabled: true  # NEW
      max_age_sec: 5
      min_update_events: 1  # ANY book updates (qty/levels/price)
      
  feature_sanity:
    enabled: true  # NEW
    nan_inf_behavior: neutral_and_not_ready
```

### Rollout Order

```
Stage 2 Rollout:
├── Day 0: Deploy P0-0 (Readiness Contract Audit) **BLOCKER**
│           - Add readiness_registry to domains.yaml
│           - Add startup validation essential ⊆ declared_keys
│           - Add runtime detection missing_ready_keys + NRR + metric
│           - Add invariant check full_ready ⇒ no missing
│           - **MUST PASS before proceeding**
│
├── Day 1: Deploy P0-3 (Feature Sanity Firewall)
│           - Metrics only, no blocking
│           - Collect baseline NaN/Inf rates
│
├── Day 2: Enable P0-1 (volatility_state hard floor)
│           - Enable hard_floor_enabled: true
│           - Monitor volatility_state_not_ready reasons
│
├── Day 3: Enable P0-2 (spread health gate)
│           - Enable spread_bps.health_gate.enabled: true
│           - Monitor spread_bps_not_ready reasons
│
├── Day 4-7: Soak testing
│           - Full feature flags active
│           - Monitor NRR rates, direction ratio, latency
│           - Verify missing_ready_keys metric = 0
│
└── Day 7+: Proceed to Stage 3 if all green
```

### Rollback Plan

```yaml
# Rollback config (instant via config reload)
feature_engineering:
  volatility_state:
    hard_floor_enabled: false  # Revert to current behavior
    
  spread_bps:
    health_gate:
      enabled: false  # Revert
      
  feature_sanity:
    enabled: false  # Revert
```

**Rollback triggers:**
1. NRR rate > 20% for any symbol
2. Direction ratio < 20% BUY or < 20% SELL
3. Any production crash
4. Latency p99 > 100ms sustained

---

## Evidence Requirements (Summary)

### Exact file:line References

| Component | Location |
|-----------|----------|
| spread_bps computation | [calculation_engine.py#L301-L320](apps/reference/domains/feature_engineering/calculation_engine.py#L301-L320) |
| volatility_state computation | [calculation_engine.py#L195-L255](apps/reference/domains/feature_engineering/calculation_engine.py#L195-L255) |
| macro_sync computation | [macro_sync_resampler.py#L130-L240](apps/reference/domains/feature_engineering/macro_sync_resampler.py#L130-L240) |
| liquidity_kappa computation | [feature_engineering.py#L515-L520](apps/reference/domains/feature_engineering/feature_engineering.py#L515-L520) |
| SignalScoreV2 | [signal_score_v2.py#L1-L209](apps/reference/domains/decision_making/signal_score_v2.py#L1-L209) |
| Direction/Strength scoring | [scoring_direction_strength_v1.py#L1-L225](apps/reference/domains/decision_making/scoring_direction_strength_v1.py#L1-L225) |
| Strategy gateway | [decision_making.py#L301-L800](apps/reference/domains/decision_making/decision_making.py#L301-L800) |
| MR handler | [mean_reversion_handler.py#L1-L300](apps/reference/domains/decision_making/mean_reversion_handler.py#L1-L300) |
| Config loader | [config_loader.py#L1-L300](apps/reference/config_loader.py#L1-L300) |
| Domain resolver | [domain_config.py#L1-L332](apps/reference/domain_config.py#L1-L332) |

### Активні профілі (як обираються)

1. **Config Loading:** `ConfigLoader.load()` reads `config/aurora/*.yaml`
2. **Strategy Assignment:** `strategies.yaml::assignments` maps symbols → strategies
3. **Per-Symbol Overrides:** `strategies/aurora.yaml::aurora.assets.<SYMBOL>` overrides global
4. **Instruments:** `instruments.yaml::instruments.<SYMBOL>` for execution specs

### Must-Change Keys Summary

| Priority | Key | Action |
|----------|-----|--------|
| P0 | `feature_engineering.volatility_state.hard_floor_enabled` | ADD |
| P0 | `feature_engineering.volatility_state.tick_floor` | ADD |
| P0 | `feature_engineering.spread_bps.health_gate.*` | ADD section |
| P0 | `feature_engineering.feature_sanity.*` | ADD section |
| P1 | `feature_engineering.macro_resid.*` | ADD section (optional) |
| P2 | `feature_engineering.absorption.mode` | ADD |

---

## Definition of Done (Stage 1) — VERIFICATION

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Document created with all sections | ✅ PASS | This file |
| Executive summary covers top 3 risks | ✅ PASS | Section 0 |
| System map with data flow | ✅ PASS | Section 1 |
| Config SSOT matrix | ✅ PASS | Section 2 |
| P0 plan with formulas and locations | ✅ PASS | Section 3 |
| P1 plan with macro_resid and kappa | ✅ PASS | Section 4 |
| P2 plan with absorption modes | ✅ PASS | Section 5 |
| Strategy coverage (Aurora + MR) | ✅ PASS | Section 6 |
| Test plan with synthetic scenarios | ✅ PASS | Section 7 |
| Deployment plan with rollback | ✅ PASS | Section 8 |
| Stage 2 feasible without main.py refactor | ✅ PASS | All changes in domains, no main.py |

---

## Stage 2 Task List (Ordered)

| # | Task | Priority | Files to Change | Est. Effort |
|---|------|----------|-----------------|-------------|
| **0** | **Readiness contract audit (BLOCKER)** | **P0-0** | `config_loader.py`, `decision_making.py`, `feature_engineering.py`, `domains.yaml`, `normalized_reject_reasons.py` | **3h** |
| 1 | Add feature sanity firewall | P0-3 | `calculation_engine.py`, `feature_engineering.py`, `domains.yaml` | 2h |
| 2 | Implement volatility_state hard floor | P0-1 | `calculation_engine.py`, `domains.yaml` | 1h |
| 3 | Add spread_bps health gate | P0-2 | `calculation_engine.py`, `feature_engineering.py`, `domains.yaml` | 3h |
| 4 | Add config validation for feature_neutrals | P0 | `signal_score_v2.py`, ConfigLoader | 1h |
| 5 | Unit tests for P0 fixes | P0 | `tests/domains/feature_engineering/` | 4h |
| 6 | Add macro_resid (optional) | P1 | `calculation_engine.py`, `macro_sync_resampler.py` | 4h |
| 7 | Clarify liquidity_kappa as gate-only | P1 | Documentation, config validation | 1h |
| 8 | Add absorption mode config | P2 | `domains.yaml`, `calculation_engine.py` | 2h |
| 9 | Integration tests | P0 | `tests/integration/` | 4h |
| 10 | Testnet soak (48h) | P0 | N/A (monitoring) | 48h |

**Total estimated effort:** 21h coding + 48h soak test

> **ВАЖЛИВО:** Task #0 (P0-0) є **блокером** для всіх інших P0 tasks. Без нього система може мовчки DEFER усі рішення після додавання нової фічі в essential_features.

---

## Amendment A1: Pre-Stage-2 Contract Fixes

**Date:** 2026-01-05  
**Trigger:** External review identified 7 ambiguities/contradictions in original document  
**Status:** APPROVED — all fixes integrated inline + summarized below

### Summary of Contract Fixes

| ID | Issue | Original Text | Fixed Text | Location |
|----|-------|---------------|------------|----------|
| **H** | **Readiness contract audit missing** | Немає валідації `essential ⊆ ready_keys` | **P0-0 BLOCKER:** Startup validation + runtime detection + invariant check | Section 3, P0-0 |
| **I** | **Silent fallbacks / hardcoded values** | Hardcoded eps, thresholds в runtime | **КОНТРАКТ (A2):** Усе через YAML → Pydantic, заборона `.get(key, default)` | Section 2.5 |
| **J** | **Warmup як опціональний перемикач** | `validation_mode: fail_fast \| warn_only \| disabled` | **КОНТРАКТ (A3):** Warmup ОБОВ'ЯЗКОВИЙ, `enforcement_mode: fail_fast` LOCKED | Section 3, P0-0 |
| **A** | `spread_bps` bounds суперечать signed deviation | `spread_bps: {min: 0.0, max: 10000.0}` для всіх випадків | Розділено: `spread_bps_raw` (≥0) та `spread_dev` (signed, окремі bounds) | Section 3, P0-3 |
| **B** | "bid/ask changes" = тільки price changes | `bid_changes_count` / `ask_changes_count` | `book_update_events_count` — будь-які оновлення (qty/levels/price) | Section 3, P0-2 |
| **C** | OR-логіка без explicit priority | Неформалізована OR-логіка | 3-Step Matrix: 1) book_age hard fail → 2) OR-check → 3) else UNHEALTHY | Section 3, P0-2 |
| **D** | Fallback value при not_ready двозначний | Fallback використовується як input | **КОНТРАКТ:** Fallback ТІЛЬКИ для телеметрії, НЕ для scoring/gates | Section 3, P0-3 |
| **E** | Volatility floor units не вказані | `tick_floor: 0.0001` без одиниць | **КОНТРАКТ:** price units, per-asset через instruments.yaml | Section 3, P0-1 |
| **F** | "40/60 ratio" як acceptance criteria | `Direction ratio (BUY/SELL) | Between 40-60%` | **КОНТРАКТ:** Reachability test на синтетиці + live sanity (SELL ≠ 0 за 7 днів) | Section 7 |
| **G** | Absorption proxy = TFI (логічний абсурд) | `proxy.source: tfi` | **КОНТРАКТ:** `proxy.source ≠ tfi`, має бути окрема фіча | Section 5, P2-1 |

### Stage 2 Contract Checklist

Перед початком Stage 2 implementation, агент ПОВИНЕН перевірити:

**Warmup Mandatory (A3):**
- [ ] `warmup.enforcement_mode: fail_fast` — LOCKED, не перемикач
- [ ] Система НІКОЛИ не торгує до `full_ready=True`
- [ ] CI/CD перевіряє: `enforcement_mode != "warn_only" && != "disabled"`

**Global Contract (A2):**
- [ ] Жодних hardcoded eps/thresholds/caps у decision/scoring paths
- [ ] Усі нові параметри в YAML + Pydantic schema (`extra='forbid'`)
- [ ] Заборона `.get(key, default)` для trading params — тільки `cfg.<param>`
- [ ] Fallback тільки для телеметрії з explicit коментарем

**P0-0 BLOCKER:**
- [ ] `essential_features ⊆ readiness_registry.declared_keys`
- [ ] Runtime detection `missing_ready_keys` з логом/метрикою/NRR
- [ ] Invariant `full_ready=True ⇒ missing_ready_keys=∅`

**P0-1/P0-2/P0-3:**
- [ ] `spread_bps_raw` bounds = `{min: 0.0, max: ...}` (non-negative)
- [ ] Якщо додається `spread_dev` — окремі bounds `{min: -X, max: +X}`
- [ ] Health gate використовує `book_update_events_count`, не `bid_changes_count`
- [ ] Health gate має explicit 3-step matrix (hard age → OR → else)
- [ ] Fallback values НЕ входять у scoring при `feature_ready=False`
- [ ] Volatility floors мають per-asset config у price units
- [ ] Acceptance criteria = reachability test, не live ratio
- [ ] `absorption.proxy.source ≠ "tfi"`

### Definition of Done (Amendment A1 + A2 + A3)

| Check | Status |
|-------|--------|
| **A3:** Warmup ОБОВ'ЯЗКОВИЙ, не перемикач | ✅ Fixed |
| **A3:** `enforcement_mode: fail_fast` LOCKED в prod | ✅ Fixed |
| **A2:** Global Contract "No Silent Fallbacks" додано | ✅ Fixed |
| **A2:** Enforcement Checklist для Stage 3 audit | ✅ Fixed |
| **A2:** Impact Statement з P0/P1 params list | ✅ Fixed |
| **P0-0:** Readiness contract audit додано як BLOCKER | ✅ Fixed |
| Жодне місце не описує spread як signed з bounds ≥0 | ✅ Fixed |
| Health gate чітко визначений як 3-step matrix | ✅ Fixed |
| Fallback contract explicit | ✅ Fixed |
| Volatility units explicit | ✅ Fixed |
| Acceptance = reachability, не ratio | ✅ Fixed |
| Absorption proxy ≠ TFI | ✅ Fixed |

---

*Document generated: 2026-01-05*  
*Amendment A1 applied: 2026-01-05*  
*Amendment A2 applied: 2026-01-05*  
*Amendment A3 applied: 2026-01-05*  
*Stage: 1 (Read-Only Analysis) — COMPLETE*  
*Next: Stage 2 (Runtime Implementation)*
