# ARCHITECTURAL AUDIT — Aurora vs `alpha_search` (Phenix)
**Date:** 2026-02-01  
**Mission:** Determine whether Aurora is actually using the `alpha_search` domain (ensemble/models) or still running the legacy “linear weights from YAML” engine; assess Kelly + pyramiding readiness; propose an activation plan; evaluate `alpha_search` quality/completeness/relevance (score /10).

---

## 0) Executive Summary (TL;DR)

1) **Engine Status:** Aurora is running a **linear-weights scoring engine** (Score V2: Direction/Strength split) driven by `config/aurora/strategies/aurora.yaml` weights and executed in `AuroraHandler → AuroraScoringKernel`. The `alpha_search` **ensemble is not wired into Aurora trading decisions**.

2) **Pyramiding Readiness (`position_mode: DYNAMIC`):** **Partially implemented only as a DecisionMaking gate** (allows same-side entries), but **not end-to-end safe**:
   - sizing does not account for existing position risk/margin,
   - execution/management does not properly re-compute or re-place brackets on scale-in,
   - so DYNAMIC is **not production-ready** as-is.

3) **Kelly:** Config exists, but runtime uses **hardcoded** `p`, `payoff_ratio_r`, and `kelly_fraction`. There is **no real Kelly sizing implementation** in the live path.

4) **`alpha_search` domain quality score:** **3/10 overall** (good unit-testable scaffolding, but mismatched to current feature contract + ensemble implementation is not production-usable and not integrated).

---

## 1) Current Signal/Decision Wiring (What actually runs)

### 1.1 Strategy pipeline (SSOT runtime path)

**Aurora is a Strategy Plugin** started by `StrategyRuntime` and emits “raw” strategy signals:

- `apps/reference/domains/strategies/plugins/aurora_builtin.py`
  - Creates `AuroraHandler`
  - Registers listeners and emits `EVT:STRATEGY_SIGNAL_PRODUCED`

**Aurora scoring + signal emission happens here:**

- `apps/reference/domains/decision_making/aurora_handler.py`
  - Loads per-symbol weights and config
  - Calls `AuroraScoringKernel.compute(...)`
  - Emits `EVT:STRATEGY_SIGNAL_PRODUCED` with `scoring.score/thr_buy/thr_sell`

**DecisionMaking does NOT compute Aurora’s score**; it applies universal gates + sizing and then emits `EVT:TRADE_INTENT_PROPOSED`:

- `apps/reference/domains/decision_making/decision_making.py`
  - Listens to `EVT:STRATEGY_SIGNAL_PRODUCED` (`_on_strategy_signal_gateway`)
  - Applies risk/QoS/exposure/TTL/flip orchestration gates
  - Computes quantity via margin-first sizing
  - Emits `EVT:TRADE_INTENT_PROPOSED`

### 1.2 Where `alpha_search` currently sits

`alpha_search` is only instantiated inside DecisionMaking as **a best-effort monitoring add-on** during `EVT:FEATURES_CALCULATED` handling:

- `apps/reference/domains/decision_making/decision_making.py`
  - Initializes `AlphaModelRegistry` and registers a couple of models
  - On features, attempts `registry.calculate_all_alpha(...)`
  - Emits `EVT:ALPHA_SCORE_CALCULATED`

Important: **This alpha output is not consumed back into Aurora scoring or sizing.**

---

## 2) Task 1 — “Wiring Check”: Is Aurora using `alpha_search`?

### 2.1 Aurora uses linear weights (not the ensemble)

**Source of truth: strategy config contains explicit linear weights.**

- `config/aurora/strategies/aurora.yaml`
  - `aurora.decision.signal_weights` (global)
  - `aurora.assets.<SYMBOL>.weights` (per-symbol overrides)

**Those weights are loaded and applied by AuroraHandler:**

- `apps/reference/domains/decision_making/aurora_handler.py`
  - `_get_signal_weights(...)` prefers `instr_cfg.weights`, else falls back to `decision.signal_weights`
  - Calls `self.scoring_kernel_cls.compute(..., signal_weights=..., feature_neutrals=..., essential_features=...)`
  - Emits `EVT:STRATEGY_SIGNAL_PRODUCED` with score + thresholds

**AuroraScoringKernel is a deterministic linear scoring kernel (Direction/Strength split).**

- `apps/reference/domains/decision_making/aurora_scoring_kernel.py`
- `apps/reference/domains/decision_making/scoring_direction_strength_v1.py`
  - uses weighted sums via `SignalScoreV2.calculate_score(...)`

### 2.2 Does Aurora import/instantiate `AlphaModelRegistry` or `EnsembleModel`?

- `AlphaModelRegistry`: **Yes, but only in DecisionMaking**, not in Aurora scoring.
  - `apps/reference/domains/decision_making/decision_making.py` initializes a registry and emits `EVT:ALPHA_SCORE_CALCULATED` (monitoring).

- `EnsembleModel`: **No runtime wiring.**
  - No strategy/handler uses `apps/reference/domains/alpha_search/ensemble.py`.
  - Even `apps/reference/domains/alpha_search/__init__.py` does **not export** `EnsembleModel`, despite docs suggesting `from ...alpha_search import EnsembleModel`.

### 2.3 Practical outcome: `alpha_search` likely emits nothing in live/backtest

The current FeatureEngineering contract (core Aurora) emits features like:
`obi, tfi, delta_price, ema_bias, volume_spike, volatility_state, depth_imbalance, macro_* ...`

But the bundled `alpha_search` models require features such as:
- Momentum: `price_momentum_5m`, `rsi_14`, `macd_signal`, ...
- Mean reversion: Bollinger, RSI, stochastics...
- Volatility: `atr_ratio`, `realized_volatility_1h`, ...

These are **not in** the FeatureEngineering v1 payload (see `apps/reference/domains/feature_engineering/contracts.py`), so:
`AlphaModel.is_ready()` returns False, and the registry returns an empty list.

**Conclusion (Task 1):** Aurora is running **Legacy Linear Weights / Score V2**, not the `alpha_search` ensemble. `alpha_search` is currently **not part of the decision engine**.

---

## 3) Task 2 — Kelly + Pyramiding Feasibility

### 3.1 Kelly (status: config exists, runtime mostly stubbed)

Evidence:
- Config schema contains `KellyConfig`:
  - `apps/reference/config_models.py` (`KellyConfig`)
- Aurora strategy YAML defines `aurora.decision.kelly`:
  - `config/aurora/strategies/aurora.yaml`

Runtime reality:
- Trade intents hardcode:
  - `p` (probability),
  - `payoff_ratio_r`,
  - `size.kelly_fraction`.

See:
- `apps/reference/domains/decision_making/decision_making.py` inside `_propose_trade_intent`:
  - `"p": "0.75"`
  - `"payoff_ratio_r": "2.0"`
  - `"kelly_fraction": "0.1"`

**Conclusion:** Kelly is **not implemented as a real sizing engine**; it’s currently a placeholder/telemetry field.

### 3.2 Pyramiding (`position_mode: DYNAMIC`) — what is implemented vs missing

**What is implemented (DecisionMaking gate):**
- `apps/reference/domains/decision_making/decision_making.py`
  - `_resolve_position_mode(...)` reads `strategies.<strategy_id>.assets.<SYMBOL>.position_mode`
  - `_handle_flip_orchestration(...)`:
    - Same-side while in position:
      - `STRICT` → block (`ANTI_PYRAMIDING_BLOCK`)
      - `DYNAMIC` → allow same-side entry (pyramiding)

There are unit tests confirming this behavior:
- `tests/domains/decision_making/test_position_mode_pyramiding_v1.py`

**What is NOT implemented end-to-end (execution + position mgmt):**

1) **Sizing is not pyramiding-aware**
   - `apps/reference/domains/decision_making/decision_making.py::_calculate_position_size`
   - Uses `equity * margin_pct * leverage`, without adjusting for current position risk/margin usage.
   - Exposure precheck helps, but sizing can still be “too aggressive” for scale-in.

2) **Bracket management for scale-in is not robust**
   - `apps/reference/domains/execution_position/fsm_manage.py`
   - The internal `_on_fill(...)` “average down” logic exists, but it is only invoked on the transition `FLAT → (FILL|PARTIAL_FILL)`.
   - After brackets are placed (`BRACKETS_PLACED/TRACKING`), additional ENTRY fills do not trigger a recompute/replacement of SL/TP for the new aggregate position.

3) **Execution engine does not consult `position_mode`**
   - `apps/reference/domains/execution_position/fsm.py` routes `CMD:OPEN` without checking pyramiding policy.
   - Policy currently lives exclusively in DecisionMaking.

**Conclusion (Pyramiding readiness):**
- `position_mode: DYNAMIC` is **real in DecisionMaking**, not just a schema placeholder.
- But pyramiding is **not safe/complete** without:
  - pyramiding-aware sizing,
  - bracket recalculation + atomic bracket replace,
  - entry-fill detection for scale-ins,
  - and robust state sync from portfolio snapshots.

---

## 4) Deep Audit — `alpha_search` Domain Quality / Completeness / Relevance

### 4.1 What works well (positive)

- **Clean minimal framework:** `AlphaModel` + `AlphaScore` + `AlphaModelRegistry` are understandable and unit-testable.
- **Good failure isolation:** registry continues even if one model throws.
- **Deterministic unit tests exist and pass:**
  - `pytest -q tests/domains/alpha_search tests/test_ensemble.py` → **22 passed** (locally, 2026-02-01)

### 4.2 Critical gaps (why it’s not production-relevant right now)

1) **Not integrated into the strategy engine**
   - No strategy plugin consumes `alpha_search` and emits `EVT:STRATEGY_SIGNAL_PRODUCED` from it.
   - AuroraHandler does not consult alpha scores.

2) **Feature contract mismatch (most important)**
   - Current `alpha_search` models require RSI/MACD/Bollinger/ATR-like features that are not produced by FeatureEngineering’s v1 contract.
   - As a result, `AlphaModelRegistry.calculate_all_alpha(...)` will usually return `[]` in the Aurora pipeline.

3) **Ensemble implementation is not “real” yet**
   - `apps/reference/domains/alpha_search/ensemble.py` currently:
     - ignores provided `features` inside `generate_signal` (sets `features = {}`),
     - calls underlying models with `symbol=""` instead of the symbol being scored,
     - “performance” is based on model confidence, not realized PnL/returns.
   - This makes the ensemble unsuitable for live trading decisions without major rework.

4) **Docs claim much more than exists**
   - `apps/reference/domains/alpha_search/README.md` and `TESTING.md` describe an event-driven standalone domain, extra metrics, CI workflow, and tests that are not present or not wired.
   - `apps/reference/domains/alpha_search/ANALYSIS_SUMMARY.md` overstates integration and metrics.

5) **Heavy dependencies in the hot path**
   - Ensemble uses `pandas`/`numpy`. That’s fine for research/backtests, but is usually undesirable in a low-latency live decision loop.

### 4.3 Score (/10)

I’m scoring on **production readiness in this repo**, not on “idea quality”.

- **Correctness of core framework:** 6/10  
- **Model usefulness vs current features:** 2/10  
- **Ensemble correctness / learning:** 2/10  
- **Integration completeness:** 1/10  
- **Docs alignment with code:** 3/10  
- **Testing (unit-level):** 7/10  

**Overall `alpha_search` score:** **3/10**

---

## 5) Upgrade Path — How to activate the Ensemble (without breaking production)

### 5.1 First decision: what does “activate alpha_search” mean?

You have two viable architectures:

**Option A (recommended): `alpha_search` becomes a Strategy Plugin**  
`alpha_search` produces `EVT:STRATEGY_SIGNAL_PRODUCED` (like AuroraHandler). DecisionMaking stays strategy-agnostic and continues to gate/sizes/execute.

Pros:
- Clean separation (strategy vs gates/execution).
- Can run in shadow mode alongside Aurora and compare.
- Works naturally with `strategies_registry` arbitration.

Cons:
- Requires defining a proper scoring contract (alpha score → side + entry_price + thresholds).

**Option B: `alpha_search` becomes an input into Aurora scoring**  
Keep Aurora weights as the baseline, but inject `ensemble_alpha` as an additional feature/term.

Pros:
- Smaller change surface.
- Easier incremental rollout.

Cons:
- You still need to fix alpha_search feature alignment and ensemble correctness.
- Risk of double-counting signals or creating hard-to-debug interactions.

### 5.2 Phase plan (safe rollout)

**Phase 0 — Make alpha_search compatible with current FeatureEngineering**
Choose one:
- **0A:** Extend FeatureEngineering to produce the features required by alpha models (RSI, MACD, BB, ATR, etc.) + warmup readiness keys.
- **0B:** Rewrite alpha models to operate on the existing Aurora feature contract (obi/tfi/ema_bias/macro_resid/volatility_state/...).

**Phase 1 — Fix the Ensemble to be actually usable**
Minimum changes:
- Pass `symbol` through (don’t use `symbol=""`).
- Use the `features` argument (don’t overwrite it with `{}`).
- Remove `pandas` dependency from live scoring path (accept dict features/market_data directly).
- Define a real performance signal (realized returns / PnL attribution), not confidence.

**Phase 2 — Wire into runtime**
- Implement `AlphaSearchHandler` and register it as a strategy plugin:
  - `apps/reference/domains/strategies/plugins/alpha_search.py` (new)
- Add `strategies.alpha_search` config (SSOT YAML) + add to `strategies_registry.assignments`.
- Emit `EVT:STRATEGY_SIGNAL_PRODUCED` with `readiness`, `price_ctx`, `scoring`.

**Phase 3 — Shadow mode + parity checks**
- Run alpha_search side-by-side with Aurora in backtests:
  - do not execute, only log/emit signals and compare hit-rate, latency, stability.
- Add divergence telemetry similar to Aurora’s shadow kernel compare.

**Phase 4 — Controlled enablement**
- Enable alpha_search for 1 symbol (paper/testnet), strict limits.
- Increase coverage if stable.

### 5.3 How this ties to “dynamic rebalancing” + pyramiding

If you want **dynamic rebalancing** to actually matter:
- You must define:
  - prediction horizon,
  - target label (next-bar return? k-bar return?),
  - performance attribution per model,
  - update rule for weights (online learning).

If you want **pyramiding** safely:
- Add a scale-in aware “position manager” policy:
  - recompute SL/TP for *aggregate* position,
  - cancel/replace brackets atomically,
  - ensure manage state updates on every entry fill,
  - cap additional entries by exposure + risk budget.

---

## 6) Concrete Answers (Deliverable Questions)

1) **Engine Status:** **Legacy Linear Weights / Score V2** (AuroraHandler → AuroraScoringKernel). `alpha_search` is not driving Aurora decisions.

2) **Pyramiding Readiness:** **Not ready for `position_mode: DYNAMIC` in production.** The gate exists, but sizing + execution management do not support safe scale-in behavior.

3) **Upgrade Path:** Use the phase plan in §5. Prefer Option A (alpha_search as a Strategy Plugin) for a clean architecture and safe rollout.

