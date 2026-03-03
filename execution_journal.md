- **Timestamp:** 2026-02-25T20:23:04+02:00
- **Task Objective:** Baseline initialization of project_state_update.md
- **Files Scanned:** `README.md`, `requirements.txt`, `config/aurora/system.yaml`, `apps/reference/domains/*`, `alysha_core/reward_engine_v3plus/*`
- **Files Generated:** project_state_update.md
- **Logic Rationale:** Derived system context from `README.md`, determined hardware constraints absence via `grep_search`, evaluated the ML/DL footprint using the `neocortex` and `alysha_core` folders, extracted module flow (market data -> risk -> execution) by observing FSM and adapter topologies, and identified specific Python stack packages directly out of `requirements.txt`.
- **Unresolved Edge Cases:** Explicit constraints for memory / GPU usage were absent in the YAML configs and required manual input prompts. Full runtime mapping inside `decision_making` (Neocortex) is complex and partially opaque without running metrics. No pre-recorded environment memory limits could be sourced locally.

- **Timestamp:** 2026-02-25T20:26:57+02:00
- **Task Objective:** Architectural alignment update (prioritizing vFoundation / domains)
- **Files Scanned:** `apps/reference/dictionaries/verb_registry_v1.yaml`, `vfoundation/README.md`
- **Files Generated:** project_state_update.md (Updated)
- **Logic Rationale:** Received explicit instructions to ignore `alysha_core` as legacy/irrelevant and pivot focus completely to `apps/reference/domains`. Discovered that the environment runs atop the `vFoundation` FSM-LLM framework, utilizing it for low-level asynchronous routing, Meta-FSMs, WAL, and DR. Furthermore, recognized `apps/reference/dictionaries` as the centralized ontology/schema mapping for the FSM events (verbs). Updated the `project_state_update.md` content and C4 chart to reflect the true structural hierarchy.
- **Unresolved Edge Cases:** None currently.

---

## H2 Forensics — NRR-046 Root Cause Investigation

- **Timestamp:** 2026-03-01T00:00:00+02:00
- **Objective:** H2 Forensics — Identify root cause of 10,930 NRR-046 errors ("EP-01.3-INT: LIMIT requires tf_sec to derive valid_for_ms") blocking flip/close intent execution. Aurora Drawdown: -53%.

---

### Findings

#### 1. NRR-046 Definition & Gate Location

**File:** `apps/reference/domains/decision_making/normalized_reject_reasons.py:77`
```python
# OBS/LEGACY: Missing timeframe context (tf_sec missing/0 where forbidden)
MISSING_TF_SEC = "NRR-046"
```

**Gate fires at:** `apps/reference/domains/decision_making/decision_making.py:3443`
```python
# EP-01.3-INT: Calculate valid_for_ms ONLY for LIMIT (pending entry TTL, fail-closed).
if order_type_u == "LIMIT":
    if tf_sec is None:  # ← ALWAYS None for flip/close path
        self._emit_trade_intent_rejected(
            reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
            context="EP-01.3-INT: LIMIT requires tf_sec to derive valid_for_ms",
        )
        return None  # ← Intent SILENTLY DROPPED
```

`order_type_u` is derived from `strategies.aurora.execution.entry_order_type` (line 3334). When Aurora is configured with `entry_order_type = "LIMIT"`, this gate applies to **all** intents routed through `_propose_trade_intent` — including reduce-only close/flip intents.

---

#### 2. The Missing tf_sec: Flip Orchestration Path

**Root call site:** `_emit_reduce_only_close` → `_propose_trade_intent`

**File:** `apps/reference/domains/decision_making/decision_making.py:3820`
```python
self._propose_trade_intent(
    symbol=symbol,
    side=close_side,
    qty=decimal.Decimal(str(qty_abs)),
    price=decimal.Decimal("0"),   # Market/Best-effort
    why_chain=["flip_orchestration_close", reason],
    rid=rid,
    reduce_only=True,
    strategy_id=str(strategy_id),
    # ← tf_sec NOT passed → defaults to None
)
```

`_propose_trade_intent` signature (line 2854) has `tf_sec: int | None = None`. When called from `_emit_reduce_only_close`, the `tf_sec` parameter is never populated — because the flip orchestration path derives the close from **portfolio state** (qty from current position), not from the original bar feature event that carried `tf_sec`.

**Second affected call site:** `_handle_regime_flip` at line 2519:
```python
self._propose_trade_intent(
    symbol=symbol,
    side=close_side,
    qty=...,
    price=decimal.Decimal("0"),
    why_chain=why_chain,
    rid=rid,
    reduce_only=True,
    # ← tf_sec also NOT passed
)
```

Both regime-triggered close and flip-orchestration close suffer from the same omission.

---

#### 3. Full Execution Chain (Annotated)

```
EVT:STRATEGY_SIGNAL_PRODUCED
  └─ strategy_signal_gateway (dm.py:~831)
       └─ GATE 2: _handle_flip_orchestration (dm.py:4255)
            └─ opposite-side detected → calls _emit_reduce_only_close (dm.py:3785)
                 └─ _propose_trade_intent(reduce_only=True, tf_sec=None)  ← GAP
                      └─ ORDER-POLICY-01: order_type resolved from config
                           │   strategies.aurora.execution.entry_order_type = "LIMIT"
                           └─ EP-01.3-INT guard (dm.py:3443):
                                if order_type == "LIMIT" and tf_sec is None:
                                    → emit TRADE_INTENT_REJECTED (NRR-046)  ← FIRE
                                    → return None  ← CLOSE INTENT DROPPED
```

The flip sequence therefore:
1. Emits the CLOSE intent → immediately rejected with NRR-046
2. Defers the OPEN intent via `_emit_intent_deferred_v1` (FLIP_CLOSE_PENDING)
3. On retry, same-side position still exists → another flip cycle → another NRR-046
4. Position never closes → OPEN never unblocks → stuck position accumulates

---

#### 4. Contract Asymmetry: cmd_open_v1 vs Close Path

**File:** `apps/reference/domains/execution_position/schemas/cmd_open_v1.json:40-78`

`cmd_open_v1.json` declares `valid_for_ms` as **required** for LIMIT orders:
```json
"if": { "properties": { "order_type": { "const": "LIMIT" } } },
"then": { "required": ["price", "tif", "valid_for_ms"] }
```

There is **no equivalent `cmd_close_v1.json` schema**. The close path does not use the
`cmd_open_v1` schema and has no formal contract specifying how `tf_sec` / `valid_for_ms`
should be supplied for reduce-only LIMIT orders.

**Contract gap:** The `_propose_trade_intent` function uses the same `entry_order_type` config
for both entry and close intents, but only the entry path (via feature events) naturally carries
`tf_sec`. The close path (flip orchestration, regime flip) has no mechanism to source `tf_sec`.

---

#### 5. Validator Location Clarification

The `order_guardian.py` in `execution_position` domain (`apps/reference/domains/execution_position/order_guardian.py`) is a **thin delegation layer** to `apps/reference/services/order_guardian.py` (LedgerStoreAdapter / ServicesGuardian). It handles bracket/TP/SL lifecycle, NOT the NRR-046 gate.

**NRR-046 is enforced exclusively in:** `apps/reference/domains/decision_making/decision_making.py` function `_propose_trade_intent` at line 3443. It is a Decision Making domain gate, not an execution_position guardian check.

**NRR-025 is a separate gate** at `fsm.py:3582-3583`: `"EP-01.3-INT: LIMIT requires valid_for_ms"` — this fires in the execution_position FSM if a LIMIT order reaches it without `valid_for_ms`. NRR-046 fires earlier, in DM, before the intent even reaches execution_position.

---

### Test Coverage Gap

#### Pattern: All flip-close tests mock `_propose_trade_intent`

Every test in the flip/regime-close suite intercepts `_propose_trade_intent` at the boundary,
bypassing the entire ORDER-POLICY-01 + EP-01.3-INT validator chain:

| Test File | Line | Mock Assignment |
|-----------|------|-----------------|
| `tests/domains/decision_making/test_flip_orchestration_v1.py` | 163 | `dm._propose_trade_intent = _fake_propose_trade_intent` |
| `tests/domains/decision_making/test_regime_flip_close.py` | 165, 212, 257, 296, 324, 356 | `dm._propose_trade_intent = _mock_propose` |
| `tests/integration/test_flip_vertical_dm_bridge_execpos.py` | 219 | `dm._propose_trade_intent = _emit_intent` |

**Effect:** Tests assert that a close call *was made* (reduce_only=True, correct side/qty), but
never execute the actual `_propose_trade_intent` body. The NRR-046 check at line 3443 is
therefore unreachable from any existing test.

#### Secondary gap: test fixtures omit `execution.entry_order_type`

Test config fixtures in `test_flip_orchestration_v1.py` define:
```python
strategies=SimpleNamespace(
    aurora=SimpleNamespace(
        decision=SimpleNamespace(...),
        assets={symbol: SimpleNamespace(position_mode=position_mode)},
        # ← NO execution block → entry_order_type would be None
    )
)
```
Even if the mock were removed, `order_type` would resolve to `None` → intent rejected with
`NRR-047 (ORDER_TYPE_MISSING)` before reaching the `NRR-046` gate. This means a test without
the mock would fail at a different gate, still never catching the tf_sec omission for the LIMIT case.

#### Missing test cases (not present anywhere):
- Flip close with `entry_order_type = "LIMIT"` and **no tf_sec** → should produce NRR-046
- Flip close with `entry_order_type = "LIMIT"` and **tf_sec provided** → should succeed
- Regime flip close with `entry_order_type = "LIMIT"` → same gap
- End-to-end integration: signal → flip → close emitted → `valid_for_ms` in downstream CMD:OPEN

---

### Summary

| Dimension | Finding |
|-----------|---------|
| **Root cause** | `_emit_reduce_only_close` and `_handle_regime_flip` call `_propose_trade_intent` without `tf_sec`; when `aurora.execution.entry_order_type = "LIMIT"`, the EP-01.3-INT gate at `decision_making.py:3443` rejects every close intent with NRR-046 |
| **Gate location** | `apps/reference/domains/decision_making/decision_making.py:3443` (inside `_propose_trade_intent`) |
| **Emission sites missing tf_sec** | `_emit_reduce_only_close` (line 3820) and `_handle_regime_flip` (line 2519) |
| **Contract gap** | `cmd_open_v1.json` requires `valid_for_ms` for LIMIT; no `cmd_close_v1.json` exists; close path re-uses `entry_order_type` config with no tf_sec source |
| **WAL error string** | `"EP-01.3-INT: LIMIT requires tf_sec to derive valid_for_ms"` (context field of NRR-046 reject) |
| **Second gate (exec_pos)** | `fsm.py:3582` emits NRR-025 if `valid_for_ms` is absent — would fire if NRR-046 were bypassed |
| **Tests** | All 3 flip-close test files mock `_propose_trade_intent` → NRR-046 path never exercised |
| **Drawdown linkage** | 10,930 rejected close intents → flip positions remain open → forced SL exits → -53% drawdown |

---

## H4 Forensics — MagicMock Leak in Production Execution Path

**[2026-03-01T01:00:00+02:00] | Objective: H4 MagicMock Leak Forensics | 14 WAL ADAPTER_ERROR events: `TypeError: '>' not supported between instances of 'MagicMock' and 'int'`**

---

### Findings

#### 1. ADAPTER_ERROR Emission Point

**File:** `apps/reference/domains/execution_position/fsm.py:4167`

```python
# ← Outer try/except starting at ~fsm.py:3225 wraps the full adapter decision execution
except Exception as e:
    ...
    order_logger.write({...})
    wal.append(Message(..., pld={"reason_code": "ADAPTER_ERROR", "reason_text": str(e)[:200], ...}))
```

The catch-all `Exception` at line 4114 captures **any** unhandled exception raised inside the adapter execution path (DEC:OPEN, DEC:CLOSE processing) and writes it to WAL as `ADAPTER_ERROR`. The 14 WAL entries with `TypeError: '>' not supported between 'MagicMock' and 'int'` are captured by this handler.

---

#### 2. Root Cause: MagicMock as Watchdog Config Dict

**Primary leak site:** `tests/domains/execution_position/test_bracket_health_check.py:49`

```python
class TestWatchdogFillPayload:
    def test_fill_payload_has_qty_field(self, fsm_config):
        from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog

        wd = OrderTimeoutWatchdog(config=fsm_config)  # ← fsm_config is MagicMock()
```

`fsm_config` is a top-level `MagicMock()` from `tests/domains/execution_position/conftest.py:35`. It is passed as the `config` parameter to `OrderTimeoutWatchdog`, which expects a plain `dict`.

**Contamination mechanism in `watchdog.py.__init__`:**

```python
# watchdog.py:58
self.config = config or {}        # → fsm_config (MagicMock is truthy, not replaced by {})

# watchdog.py:60-62
self.ack_ttl_ms  = self.config["ack_ttl_ms"]  if "ack_ttl_ms"  in self.config else ack_ttl_ms
self.fill_ttl_ms = self.config["fill_ttl_ms"] if "fill_ttl_ms" in self.config else fill_ttl_ms
self.check_interval_ms = self.config["check_interval_ms"] if "check_interval_ms" in self.config else ...

# watchdog.py:91  ← KEY LINE
self._rps_limit = self.config["rps_limit"] if "rps_limit" in self.config else 10
```

`MagicMock.__contains__(key)` always returns a truthy `MagicMock`, so every `"key" in MagicMock()` evaluates to `True`. Therefore `self.config["rps_limit"]` is called, which returns `MagicMock().__getitem__("rps_limit")` → a new `MagicMock` object. `self._rps_limit` is now a `MagicMock`, not `int(10)`.

**Error firing point** — `watchdog.py:121`:

```python
def _check_rps_limit(self) -> bool:
    ...
    if self._rps_request_count < self._rps_limit:   # ← int(0) < MagicMock()
```

Python 3 comparison protocol for `a < b`:
1. `int.__lt__(MagicMock())` → `NotImplemented`  (int cannot compare with MagicMock)
2. Reflected: `MagicMock().__gt__(0)` → also `NotImplemented` when the auto-generated magic returns in a way Python cannot accept as a rich comparison result
3. Python raises: **`TypeError: '>' not supported between instances of 'MagicMock' and 'int'`**

Note: Python reports `'>'` in the error because the TypeError is raised during the **reflected** `>` operation, even though the original operator was `<`.

**`_check_rps_limit()` call path:**

```
_watchdog_loop()          [async task, created by watchdog.start()]
  └─ _poll_order_statuses()
       └─ _check_rps_limit()      ← int(0) < MagicMock() → TypeError
```

When the async event loop runs and the watchdog polling is active, this TypeError propagates up through the async task and into the adapter execution context, getting caught by the FSM's catch-all at `fsm.py:4114` → written to WAL as `ADAPTER_ERROR`.

---

#### 3. Production Path vs Test Path Asymmetry

Production `ExecPosFSM.__init__` (fsm.py:372-444) does NOT pass `config=` to the watchdog:

```python
# fsm.py:440 — PRODUCTION INIT (safe)
self.watchdog = OrderTimeoutWatchdog(
    ack_ttl_ms=ack_ttl_ms,     # int, extracted and cast explicitly
    fill_ttl_ms=fill_ttl_ms,   # int, extracted and cast explicitly
    on_timeout_callback=self._handle_order_timeout
    # config= is NOT passed → watchdog uses self.config = {} → "rps_limit" not in {} → default 10
)
```

The `rps_limit` problem exists ONLY when `config=MagicMock()` is passed directly, which happens solely via `test_bracket_health_check.py:49`. This test incorrectly initializes `OrderTimeoutWatchdog` with the full `fsm_config` MagicMock instead of extracting a proper dict.

**Conftest also lacks `rps_limit` assignment:**

```python
# tests/domains/execution_position/conftest.py:37-39
cfg.trading.execution.watchdog.ack_ttl_ms = 5000
cfg.trading.execution.watchdog.fill_ttl_ms = 5000
# ← missing: cfg.trading.execution.watchdog.rps_limit = 10
```

Even if `rps_limit` were set here, it would be on the wrong sub-path
(`cfg.trading.execution.watchdog.rps_limit`), while `test_bracket_health_check.py` passes
the root `fsm_config` as config directly, not the watchdog sub-dict.

---

#### 4. MagicMock Imports in Production Code

Scanned `apps/reference/` for `import MagicMock` / `from unittest.mock import` in **non-test** files. Result:

| File | Line | Nature |
|------|------|--------|
| `apps/reference/domains/execution_position/order_guardian.py:28` | Comment only | Safe |
| `apps/reference/domains/decision_making/aurora_handler.py:278` | Comment (defensive note) | Safe |
| `apps/reference/telemetry/order_logger.py:17` | Comment | Safe |

**No production module imports MagicMock.** The contamination is 100% test-infrastructure origin.

**Secondary risk — `AuroraConfig = MagicMock` fallback in test conftest:**

```python
# tests/domains/execution_position/conftest.py:9-12
try:
    from apps.reference.config_models import AuroraConfig
except ImportError:
    AuroraConfig = MagicMock   # ← module-level MagicMock class assignment
```

If `AuroraConfig` import fails during CI (ImportError due to missing dependency/env issue), the symbol `AuroraConfig` in this conftest module is set to the MagicMock **class itself**. Any call to `AuroraConfig()` would then create a MagicMock instance instead of a typed config. This is a silent contamination vector that can leak MagicMock instances into code that calls `AuroraConfig(...)`.

---

#### 5. Session-Scoped / Leaked Patches Audit

Searched all conftest files for `patch.start()` and `scope="session"` fixtures that apply patches.

| File | Finding |
|------|---------|
| `tests/conftest.py` | No `patch.start()` without `stop()`, no session-scoped patches |
| `tests/domains/conftest.py` | No patches |
| `tests/domains/execution_position/conftest.py` | `with patch(...):` context managers — properly scoped, no leaks |
| `tests/adapters/conftest.py` | Not checked (not relevant to this path) |
| `tests/e2e/conftest.py` | Not checked |

**No orphaned `patch.start()` calls found.** The MagicMock leak is NOT from a session-scoped global patch. It is from a structural test construction error: direct passing of `fsm_config` MagicMock to `OrderTimeoutWatchdog(config=...)`.

---

#### 6. The `> ` Comparison — Exact Parameter Identification

The `>` error occurs on the RPS rate limiter field:

```
Parameter: self._rps_limit
Type at runtime: MagicMock (should be int, default 10)
Source: watchdog.py:91 — self.config["rps_limit"] on a MagicMock config
Comparison: self._rps_request_count (int=0) < self._rps_limit (MagicMock)
Reported as: TypeError: '>' not supported between instances of 'MagicMock' and 'int'
                        ↑ reflected operation name (< uses reflected >)
```

This is the REST polling RPS throttle. The MagicMock did not reach financial parameters
(balance, margin, qty, price) — only the polling rate limiter. However, the same dict-access
contamination pattern in `watchdog.py:60-62` could also infect `ack_ttl_ms` and `fill_ttl_ms`
if the test config does not stop `_check_rps_limit` from running first.

---

### Edge Cases: Test Isolation Gaps

| Gap | Description |
|-----|-------------|
| **Direct construction bypass** | `test_bracket_health_check.py:49` skips the production `ExecPosFSM.__init__` watchdog init path and calls `OrderTimeoutWatchdog(config=fsm_config)` directly, exposing the dict-access vulnerability |
| **MagicMock `__contains__` always truthy** | `"key" in MagicMock()` returns truthy unconditionally; any `if key in config: return config[key]` guard is bypassed, turning every config field into a MagicMock |
| **Missing `rps_limit` in conftest** | `tests/domains/execution_position/conftest.py` sets `ack_ttl_ms` and `fill_ttl_ms` on `cfg.trading.execution.watchdog` but omits `rps_limit` — even if the test passed the correct sub-dict, this field would still be MagicMock |
| **AuroraConfig ImportError fallback** | `conftest.py:9-12`: `AuroraConfig = MagicMock` on ImportError means a broken import silently poisons all downstream `AuroraConfig()` calls in that test module |
| **Root conftest MagicMock fields** | `tests/conftest.py:55-56`: `MockAuroraConfig` sets `tca_prefs = MagicMock()` and `risk_budgets = MagicMock()` — these reach `_propose_trade_intent` and return MagicMock when accessed via `aget()`, which are then cast to string; currently safe but fragile |

---

## H1 Forensics — ta_ensemble Frozen: score=0.0 in 100% of Cases

**[2026-03-01T02:00:00+02:00] | Objective: H1 ta_ensemble Forensics | 9,104/9,104 inferences return score=0.0 (ensemble_3_models)**

---

### Findings

#### 1. Architecture Overview

**Provider entry point:** `apps/reference/domains/alpha_search/backtest_plugin.py`
**Ensemble model:** `apps/reference/domains/alpha_search/ensemble.py`
**Individual TA models:** `apps/reference/domains/alpha_search/models/{momentum,mean_reversion,volatility}.py`
**Config:** `config/alpha_search.yaml` (ta_ensemble provider) + `config/alpha_search_system.yaml` (tuning params)

The `ta_ensemble` provider is constructed at `backtest_plugin.py:215-248`:
```python
elif cfg.ensemble:
    # TA ensemble
    from .ensemble import EnsembleModel, EnsembleConfig
    from .models.momentum import MomentumAlphaModel
    from .models.mean_reversion import MeanReversionAlphaModel
    from .models.volatility import VolatilityAlphaModel

    models = {}
    for model_name, model_cfg in cfg.ensemble.models.items():
        if model_cfg.enabled and model_name in model_map:
            models[model_name] = model_class(config=model_params)

    ensemble = EnsembleModel(config=ensemble_cfg, models=models)
    ensemble._system_config = sys_cfg.ensemble   # ← EnsembleSystemConfig injected here
    return ensemble
```

`EnsembleModel.__init__` (ensemble.py:64-97) calls `_initialize_weights()` → sets equal weights of `1/3` per model. Weights are **not** zero at startup.

---

#### 2. Primary Root Cause: Feature Domain Mismatch

**The ta_ensemble's 3 TA models require a completely different feature set than what the Aurora pipeline provides.**

**Features provided by Aurora `EVT:FEATURES_CALCULATED`:**
```
obi, tfi, delta_price, ema_bias, volume_spike, volatility_state,
depth_imbalance, macro_resid, macro_sync, kappa
```

**Features required by the TA models (accessed via `features.get(key, default)`):**

| Model | Required Features | Default When Absent |
|-------|------------------|---------------------|
| `momentum_v1` | `price_momentum_5m`, `price_momentum_1h`, `price_momentum_1d`, `volume_momentum_5m`, `rsi_14`, `macd_signal` | 0, 0, 0, 0, 50, 0 |
| `mean_reversion_v1` | `bb_position`, `bb_width`, `rsi_14`, `price_sma_20_deviation`, `volume_sma_ratio`, `stoch_k`, `stoch_d` | 0.5, 0.1, 50, 0, 1, 50, 50 |
| `volatility_v1` | `atr_ratio`, `bb_width`, `bb_width_change`, `realized_volatility_1h`, `realized_volatility_1d`, `volume_volatility_ratio`, `price_range_ratio` | 1, 0.05, 0, 0, 0, 1, 1 |

**None of the required TA features appear in the Aurora pipeline.** All models receive Aurora-domain features (`obi`, `tfi`, etc.) that they do not consume, plus their own features all defaulting to neutral values.

**All 3 models use defensive `.get(key, default)` access — no `KeyError` fires.** Models execute normally with entirely neutral inputs.

---

#### 3. Score Calculation With All-Default Inputs

With all TA-specific features set to their neutral defaults:

**`momentum_v1`:** `price_momentum_5m=price_momentum_1h=price_momentum_1d=volume_momentum_5m=0`, `rsi_14=50`, `macd_signal=0`
- All momentum timeframe signals = 0 → weighted sum = 0 → `final_score = 0.0`
- RSI = 50 → not overbought/oversold → `rsi_confidence = 1.0`
- `macd_signal = 0` → no confirmation → `macd_confidence = 1.0`
- All signals agree at zero → `consistency_factor ≥ 0.7`
- **`confidence = 0.8 * 1.0 * 1.0 * consistency_factor ≥ 0.56`**

**`mean_reversion_v1`:** `bb_position=0.5` (neutral band center), `rsi=50` (neutral), `stoch_k=stoch_d=50` (neutral)
- No BB extreme signal, no RSI extreme, no stochastic extreme
- "No strong signals" path in `_calculate_confidence()` → `confidence = 0.3` (base)
- `final_score ≈ 0.0`

**`volatility_v1`:** `atr_ratio=1.0` (neutral), `bb_width=0.05` (neutral), `bb_width_change=0` (flat), `realized_volatility=0`
- "No strong signals" path in `_calculate_confidence()` → `confidence = 0.4` (no_signal)
- `final_score ≈ 0.0`

**`confidence_threshold = Decimal("0.1")** (from `EnsembleSystemConfig.confidence_threshold`, default 0.1, injected via `ensemble._system_config = sys_cfg.ensemble`).

All three models produce `confidence ≥ 0.3 > 0.1`. They all enter `valid_scores`. `_combine_scores()` computes the weighted average of three scores ≈ 0.0 → **final ensemble score = 0.0 (legitimately)**.

`AlphaScore.score` and `.confidence` are Pydantic `Decimal` fields — no `float/Decimal` TypeError risk at the comparison.

---

#### 4. The Fail-Safe Is a Symptom, Not the Cause

The `generate_signal()` loop in `ensemble.py:181-213`:
```python
for model_name, model in self.models.items():
    try:
        score = model.calculate_alpha(...)
        model_scores[model_name] = score
        if score.confidence > confidence_threshold:      # ← Decimal comparison, safe
            valid_scores.append((model_name, score))
    except Exception as e:
        self.logger.warning(f"Error getting score from {model_name}: {e}")
        continue                                          # ← SILENT SWALLOW

if not valid_scores:
    return AlphaScore(score=Decimal("0.0"), why=["no_valid_scores"])  # ← only if all fail
```

**With neutral-default inputs, all 3 models succeed and `valid_scores` has 3 entries.** The `no_valid_scores` path is NOT triggered in the nominal case. The 0.0 score comes from `_combine_scores()` returning the weighted average of three near-zero signals — a legitimate computation, not a fail-safe trip.

**However:** the `except Exception: continue` block is a **second-order hazard**. It silently swallows any future runtime errors in all 3 models. Only a `WARNING` log is emitted. No WAL entry, no telemetry, no counter increment. A model that crashes on every call would produce the same 0.0 output as a model running normally with neutral features — indistinguishable from the WAL.

---

#### 5. Pre-Call Feature Gate — Non-Blocking

`backtest_plugin.py:388-396` has an early-exit gate:
```python
if hasattr(model, "get_required_features"):
    _required = model.get_required_features()
    if _required and all(f not in features for f in _required):
        LOG.debug(f"[{symbol}] Skipping {provider_id}: required features absent ...")
        continue
```

**Why it does not fire for ta_ensemble:**
`EnsembleModel` inherits `get_required_features()` from `AlphaModel` (alpha_model.py:97-102):
```python
def get_required_features(self) -> List[str]:
    return []  # ← base implementation returns empty list
```

The `EnsembleModel` class does NOT override `get_required_features()`. The gate condition: `_required and all(...)` — `_required = []` → falsy → gate body never executes. **The ensemble is called on every bar regardless of feature availability.**

The gate was designed for this exact scenario (comment: `"e.g. ta_ensemble needs rsi_14/bb_position/macd — absent on tick data"`), but `EnsembleModel` was never given the implementation.

---

#### 6. No TA Feature Pipeline Exists

There is no component in the system that computes `rsi_14`, `bb_position`, `macd_signal`, `stoch_k`, `atr_ratio`, `realized_volatility_1h`, `price_momentum_5m`, etc. from bar data.

The Aurora feature pipeline computes: `obi`, `tfi`, `delta_price`, `ema_bias`, `volume_spike`, `volatility_state`, `depth_imbalance`, `macro_resid`, `kappa`. These are market microstructure/order flow features — structurally incompatible with the TA indicator set the ensemble models were built for.

`config/alpha_search.yaml` routes `EVT:FEATURES_CALCULATED` (Aurora bar features) directly to ta_ensemble with no transformation step. The two-phase bridge at `backtest_plugin.py:278-373` caches and replays these features verbatim.

---

### Summary

| Dimension | Finding |
|-----------|---------|
| **Root cause** | `ta_ensemble` receives Aurora microstructure features (`obi`, `tfi`, etc.) but its 3 TA models require computed technical indicators (`rsi_14`, `bb_position`, `macd_signal`, etc.). No TA indicator pipeline exists. All TA features default to neutral values on every bar. |
| **Score mechanics** | All 3 models compute with all-neutral inputs → score≈0.0, confidence≥0.3. `valid_scores` has 3 entries. `_combine_scores()` returns weighted average of ~0.0 = 0.0. Output is legitimate, not a fail-safe trip. |
| **9,104 zero scores** | Each bar for each symbol produces a valid but context-free signal of 0.0. No signal ever crosses `threshold=0.18`. Virtual trader opens 0 positions. |
| **Silent hazard** | `ensemble.py:201-204`: `except Exception: continue` with WARNING-only logging hides any future model crashes. No WAL entry, no telemetry counter, no discriminator between "zero from neutral inputs" and "zero from crash". |
| **Gate non-activation** | `backtest_plugin.py:388-396` early-exit gate designed for absent TA features never fires because `EnsembleModel.get_required_features()` returns `[]` (base class default, not overridden). |
| **Config observation** | `alpha_search.yaml` models have no `weight` fields (`enabled: true` only); `EnsembleModelConfig.weight: Optional[float] = None` → `_initialize_weights()` sets equal 1/3 weights. Not the cause of 0.0 but worth noting weights are never persisted. |
| **Contract gap** | `cmd_open_v1.json` / `cmd_close_v1.json` gap from H2 is a separate dimension; no schema enforces TA feature presence before ensemble invocation. |

### ML Edge Cases

| Gap | Description |
|-----|-------------|
| **Feature domain isolation** | ta_ensemble and aurora provider share the same `EVT:FEATURES_CALCULATED` event bus. Aurora features are incompatible with TA model inputs. No feature router, transformer, or domain separator exists. |
| **`get_required_features()` not overridden** | `EnsembleModel` inherits base empty-list implementation. The pre-call gate at `backtest_plugin.py:388` is designed to skip the provider when TA features are absent but cannot activate without override. Each sub-model would need to contribute its required features upward. |
| **Silent `except Exception: continue`** | All model exceptions are downgraded to WARNING log entries. An exception in `model.calculate_alpha()`, `score.confidence > threshold` comparison, or any Pydantic validation error is indistinguishable from a normal zero-signal run in the WAL. |
| **`_rebalance_weights()` cold-start** | `model_performance[name] = []` on init. Performance-based rebalancing cannot promote any model until trades are fed back via `on_trade_result()`. With shadow mode and permanent 0.0 scores, no virtual trades execute, no PnL feedback arrives, weights remain frozen at 1/3 indefinitely. |
| **No TA feature computation stage** | The alpha search pipeline has no bar-processor that computes RSI, Bollinger Bands, MACD, Stochastic, ATR, realized volatility, or price momentum from OHLCV data. The feature computation stage is architecturally missing. |
