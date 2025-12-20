# TASK32 — Strategy Plugin Registry & Strategy-Agnostic DecisionMaking

## Summary (Before/After)

**Before**
- `DecisionMaking` був жорстко зв’язаний з конкретною стратегією: напряму ініціалізував MR handler, форвардив тики в handler і мав MR-специфічний gateway/event (`EVT:MR_SIGNAL_PRODUCED`).
- Архітектура унеможливлювала масштабування стратегій без правок в `DecisionMaking` (і без ризику “магічних if mr”).
- Невідомі/незареєстровані стратегії не мали явного fail-closed контракту на bootstrap.

**After**
- Додано **Strategy Plugin Registry (allowlist)** без dynamic imports: `strategy_id → plugin → handler`.
- `DecisionMaking` став **strategy-agnostic gateway**:
  - слухає `EVT:STRATEGY_SIGNAL_PRODUCED`,
  - застосовує універсальні гейти (assignment/arbitration, risk, risk-skew, flip orchestration, QoS, exposure, TTL, warmup),
  - емітить `EVT:TRADE_INTENT_PROPOSED`.
- Mean Reversion працює як **звичайний плагін**:
  - handler сам підписується на `EVT:MARKET_TICK_RECEIVED` і `EVT:REGIME_DETECTED`,
  - емітить **generic** `EVT:STRATEGY_SIGNAL_PRODUCED`.
- Fail-closed на bootstrap: якщо strategy assigned у `strategies.yaml`, але plugin не зареєстрований → `ConfigContractError`.

---

## Changed / Added Files

**Strategy plugins (new)**
- `apps/reference/domains/strategies/registry.py` — `StrategyPluginRegistry` + `StrategyRuntime` (SSOT assignments → handlers).
- `apps/reference/domains/strategies/plugins/mean_reversion.py` — `MeanReversion1mPlugin`.
- `apps/reference/domains/strategies/plugins/aurora_builtin.py` — no-op plugin для `aurora` (Phase 1 placeholder).

**DecisionMaking / MR**
- `apps/reference/domains/decision_making/decision_making.py` — видалено hardcoded MR wiring + додано `_on_strategy_signal_gateway`.
- `apps/reference/domains/decision_making/mean_reversion_handler.py` — handler більше не залежить від `DecisionMaking`, працює як plugin handler і емітить `EVT:STRATEGY_SIGNAL_PRODUCED`.

**Composition root**
- `apps/reference/main.py` — реєстрація allowlist plugins + запуск `StrategyRuntime`.

**Tests**
- `tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py` — DM не містить MR hardcoding.
- `tests/domains/strategies/test_task32_strategy_plugin_registry.py` — registry start + fail-closed на missing plugin.
- `tests/integration/test_task32_two_strategies_arbitration.py` — 2 strategies на 1 символі, arbitration працює.

---

## Removed Hardcoded Places (key)

- `DecisionMaking` більше не створює MR handler, не форвардить тики і не слухає `EVT:MR_SIGNAL_PRODUCED`.
- MR-специфічні гейти/хелпери в `DecisionMaking` прибрані; DM працює тільки з `strategy_id`.

---

## Event Flow (Phase 1)

```text
MarketData → EVT:MARKET_TICK_RECEIVED
RegimeDetector → EVT:REGIME_DETECTED

StrategyHandler (plugin)
  └─ emits EVT:STRATEGY_SIGNAL_PRODUCED {strategy_id,symbol,side,score,why,ts_ms,price_ctx,...}

DecisionMaking (gateway)
  └─ universal gates (assignment/arbitration/risk/qos/exposure/ttl/warmup/flip)
     └─ emits EVT:TRADE_INTENT_PROPOSED
```

---

## EVT:STRATEGY_SIGNAL_PRODUCED (minimal contract)

Required:
- `strategy_id`, `symbol`, `side`, `why`, `ts_ms`

Recommended:
- `score`
- `price_ctx: {entry_price, stop_price?, target_price?}`
- `qty_hint` and/or `position_size_usd`
- `rid`, `why_chain`

---

## Tests

Command:
`pytest -q tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py tests/domains/strategies/test_task32_strategy_plugin_registry.py tests/integration/test_task32_two_strategies_arbitration.py`

Output:
```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.1, pluggy-1.6.0
rootdir: /home/wekabeka/Музыка/Phenix
configfile: pytest.ini
collected 4 items

tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py . [ 25%]
tests/domains/strategies/test_task32_strategy_plugin_registry.py ..      [ 75%]
tests/integration/test_task32_two_strategies_arbitration.py .            [100%]

============================== 4 passed in 0.16s ===============================
```

