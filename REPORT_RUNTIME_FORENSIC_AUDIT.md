# RUNTIME FORENSIC AUDIT: md_amr cold_start / Aurora inactivity / Quadratic visibility / FE integrity

## 1. Executive Summary
This deep forensic audit of the Aurora / Phenix runtime environment reveals several systemic issues blocking live trading and alpha search logic. `md_amr` (Mean Reversion) strategy is strictly bound to a 96-bar (24-hour) cold start counter that rejects its own signals until saturated. Even when strategies successfully pass the cold start and emit `TRADE_INTENT`, the Execution Guard abruptly blocks trades with a `local_manage_state_conflict` (even when both local and portfolio states are correctly `FLAT`). Furthermore, the Feature Engineering (FE) pipeline is systematically failing to produce required Technical Analysis (TA) features (`bb_position`, `rsi_14`, etc.), causing the Alpha Search `ta_ensemble` to fail-closed globally. Lastly, the current Quadratic observability is only partially implemented: `pillar_sum` is produced in FE, rich Quadratic traces exist in Aurora code, but the observed live Aurora path is mostly fail-closed on invalid `tf_sec` before Quadratic compute/logging, and the standard decision trace serialization still drops most Quadratic-specific fields.

## 2. Runtime Artefacts Used
- `logs/aurora_core.log` & `logs/aurora_trades.log` (Intent generation, Execution Guard rejects, FE feature payloads)
- `logs/domain_decision_making.log` (Risk scoring, MR signal generation)
- `logs/domain_execution_position.log` (Execution Guard FSM blockers, state conflicts)
- `logs/domain_mean_reversion.log` (MR strategy counters, initialization, bar tracking)
- `logs/alpha_search_runtime/.../aggregate/alpha_search_domain.log` (Ensemble strategy fail-closed reasons)

## 3. md_amr Cold Start Forensic Timeline
- **First observation:** `md_amr_handler` tracking bars and generating signals but immediately dropping them.
- **Evidence:** `GUARD_REJECT: DECISION_REJECT - XRPUSDT buy (md_amr_handler:cold_start:8/96)` at 05:00:02.
- **Increment:** The counter increments precisely every 15 minutes (e.g., `9/96` at 05:15:03, `10/96` at 05:30:04, up to `31/96` at 10:45:01).
- **Result:** The strategy natively generates decisions but a hard-coded guard drops them until exactly 96 bars are observed.

## 4. What md_amr Actually Needs At Startup
- `md_amr` operates purely on `EVT:BAR_CLOSED` to build its buffer.
- `domain_mean_reversion.log` shows counters: `ticks_seen: 0, bars_completed: 67, bars_received: 1389`.
- It relies entirely on receiving 96 bars of its underlying timeframe (15m, yielding a 24h cold start). Since it's merely a bar counter block, hydrating the system with 96 historical candles at startup will completely bypass this `cold_start` limitation.

## 5. Aurora Event / Decision / Intent Timeline
Using `DOGEUSDT` as the unblocked asset (surpassed cold start):
1. **BAR_CLOSED:** `08:35:02,207 - 📊 on_bar_closed: emitting bar-features for XRPUSDT tf_sec=300`
2. **STRATEGY SIGNAL:** `08:35:02,084 - [DOGEUSDT] MR Signal: LONG confidence=0.85 entry=0.094715 stop=0.09443750 target=0.096251... why=price_below_lower_bb:pct_b=-0.023;rsi_oversold:22.2;regime:FLAT_LOW`
3. **SIGNAL EMITTED:** `08:35:02,141 - EVT:STRATEGY_SIGNAL_PRODUCED emitted: BUY @ 0.094715`
4. **DECISION GATEWAY:** `08:35:02,089 - STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED`
5. **INTENT ROUTER:** `08:35:02,135 - Processing TRADE_INTENT -> CMD:OPEN (qty=97675 side=BUY type=MARKET)`
6. **EXECUTION GUARD:** `08:35:02,136 - EXECUTION_GUARD_BLOCKED ... block_reason: 'local_manage_state_conflict'` (Current states: `local=FLAT`, `portfolio=FLAT`).
7. **REJECT:** `08:35:02,137 - Execution Rejected: OPEN_GUARD_FAIL`

## 6. Why Aurora Is Not Trading
Aurora is successfully evaluating features, processing strategies, and generating high-confidence `TRADE_INTENT_PROPOSED` events. The entire decision-making pipeline works.
**The failure is entirely in the Execution Position domain.** The `ExposureGuard` FSM intercepts `CMD:OPEN` and erroneously raises `local_manage_state_conflict` even though both `local_manage_state` and `portfolio_truth_state` correctly read as `FLAT`. Additionally, other symbols (like `BTCUSDT`) are rejected for `COOLDOWN (Position recently closed)`.

## 7. Quadratic / Pillar / Regime Logging Audit

#### Quadratic Regime / Scoring Logging Audit
- **Does current runtime code contain Quadratic regime / scoring logic?** Yes. `apps/reference/domains/decision_making/quadratic_scoring_kernel.py` contains `QuadraticScoringKernel.compute()`, and Aurora runtime code builds a rich Quadratic decision trace in `aurora_decision.py`.
- **Where is it computed?** In Aurora only, after `AuroraHandler.on_process_strategy()` passes strict fail-closed input gates and delegates into `_process_decision()`, which calls the Quadratic kernel.
- **Where is it supposed to be logged?** There are three intended observability points in code: `QUADRATIC_DECISION_TRACE` at debug level, `KERNEL_DIAG` at info level, and compact `decision_trace` attached to blocked-strategy details. Trade intents and `EVT:DECISION_TRACE_EMITTED` additionally expose only generic fields like `regime`, `regime_confidence`, and `pm_norm_*`.
- **Which logger / sink / file / event should contain it?** Aurora emits through logger names `aurora_handler.<strategy_id>`. Those records should be visible through the core/root logging path (for example `logs/aurora_core.log`). They do **not** match the `decision_making` domain sink prefix used for `logs/domain_decision_making.log`, so that file is not a reliable sink for Aurora Quadratic logs.
- **Actual runtime evidence found:** live WAL confirms `aurora_handler` is executing in runtime, but the observed events are dominated by `TRADE_INTENT_REJECTED` with `NRR-046` reasons `CMD:PROCESS_STRATEGY missing tf_sec (fail-closed)` and `CMD:PROCESS_STRATEGY tf_sec=0 forbidden (fail-closed)`. No live `KERNEL_DIAG` or `QUADRATIC_DECISION_TRACE` records were found in searched logs.
- **What this means operationally:** Aurora path is alive, but the observed live calls are mostly rejected before `_process_decision()` and therefore before Quadratic compute/logging. Separately, even when Quadratic compute does happen, the standard emitted decision trace payload still omits the rich Quadratic fields (`pillar_sum`, `raw_exposure`, `final_score`, `shield_multiplier`, `side_why`, etc.), so operator-visible telemetry remains incomplete.
- **Primary missing-visibility causes:**
	1. Runtime entry reaches Aurora, but the observed live path usually exits early on `tf_sec` fail-closed validation before Quadratic computation.
	2. Aurora logger names are not routed into `logs/domain_decision_making.log` because the sink filter expects `apps.reference.domains.decision_making.*`, not `aurora_handler.*`.
	3. The generic decision trace / intent serialization does not preserve the full Quadratic trace even where the code constructs it.
- **Verdict:** `QUADRATIC_LOGGING_PARTIALLY_IMPLEMENTED`
- **Exact fix recommendation:**
	1. Fix the producer of `CMD:PROCESS_STRATEGY` so `tf_sec` is always present and non-zero.
	2. Route `aurora_handler.*` into an explicit decision/strategy sink or widen the decision-making sink filter so Aurora diagnostics land in a predictable file.
	3. Serialize the compact Quadratic trace into the standard `EVT:DECISION_TRACE_EMITTED` / `TRADE_INTENT_PROPOSED` observability payload so operators can see `pillar_sum`, score transformation, thresholds, shielding, and final side decision without relying on debug-only logger text.

## 8. Feature Engineering Integrity Audit
- **Massive Hole:** FE is failing to publish structural TA features.
- `apps.reference.domains.alpha_search.backtest_plugin` spams warnings every 5 minutes across ALL symbols: `Provider ta_ensemble skipped: missing required features: bb_position,bb_width,rsi_14,price_sma_20_deviation,volume_sma_ratio,stoch_k,stoch_d,price_momentum_5m`.
- The `alpha_search_runtime` continuously logs `"why": ["fail_closed:missing_features_for_bar"]`, effectively paralyzing the ensemble strategy.
- Existing features (`obi`, `tfi`, `pillar_sum`) are cleanly populated without nulls, pointing to a disabled or disconnected TA calculator module in the FE pipeline.

## 9. Confirmed Runtime Defects
1. **Execution FSM Bug:** `EXECUTION_GUARD_BLOCKED` throws `local_manage_state_conflict` when both local and portfolio states are `FLAT`, halting all valid trades.
2. **Missing FE TA Features:** `bb_position`, `rsi_14`, etc., are completely missing from the FE output payload, breaking `ta_ensemble`.
3. **Quadratic Logging Gap:** FE computes `pillar_sum`, Aurora contains real Quadratic compute/logging code, but observed live Aurora calls usually fail before Quadratic compute on invalid `tf_sec`, and the standard decision trace still omits the rich Quadratic fields.

## 10. Likely / Not Fully Proven Problems
- The `md_amr_handler` cold start of 96 bars implies a strict 24-hour waiting period. While it can likely be fixed by hydrating historical candles on startup, it's not proven if the regime detectors *also* require live latency to align with those candles.

## 11. Practical Next Steps
1. **Fix Execution FSM:** Inspect `ExposureGuard` in `domain_execution_position.py` to fix why `FLAT` vs `FLAT` triggers a `local_manage_state_conflict`.
2. **Restore FE TA Indicators:** Enable or fix the TA calculator in Feature Engineering to append `bb_position`, `rsi_14`, etc., to the feature payload.
3. **Hydrate md_amr:** Feed 96 historical bars at startup to bypass `md_amr_handler:cold_start`.
4. **Propagate Pillar Logging:** Update `DecisionMaking` logs to explicitly include `pillar_sum` and its risk/size multiplier.

## 12. Direct Answers to the 12 Questions
1. **Что саме блокує md_amr на старті?** Internal strategy bar counter (`md_amr_handler:cold_start`).
2. **md_amr cold_start залежить тільки від свічок чи ні?** Тільки від свічок (барів).
3. **Якщо тільки від свічок — які TF і скільки барів потрібні?** 96 барів (крок 15 хвилин, що дорівнює 24 годинам).
4. **Якщо не тільки від свічок — що ще є blocker-ом?** N/A.
5. **Aurora взагалі отримує CMD:PROCESS_STRATEGY?** Так, стратегії обробляють події та генерують сигнали.
6. **Aurora доходить до Quadratic kernel?** Кодово так, але в observed live runtime більшість викликів `aurora_handler` відсікаються раніше fail-closed перевіркою `tf_sec`, тому Quadratic compute/logging у зібраних артефактах не видно.
7. **Якщо доходить — чому не дає trade?** Блокується `ExposureGuard` через помилковий конфлікт станів (`local_manage_state_conflict`), хоча обидва стани `FLAT`.
8. **Де саме логується Quadratic / pillar / regime logic?** У FE добре видно `pillar_sum` і `pillar_contribs`; в Aurora code існують `QUADRATIC_DECISION_TRACE` і `KERNEL_DIAG`, але у live-артефактах вони не знайдені, бо observed path зазвичай падає на `tf_sec` gate ще до Quadratic compute. Стандартний decision trace event не несе rich Quadratic fields.
9. **Чи достатньо поточного логування, щоб дебажити Quadratic decisions?** Ні. Поточне логування частково імплементоване, але неоперабельне: нема стабільного sink routing для `aurora_handler.*`, а стандартний trace не серіалізує повну Quadratic explainability.
10. **Чи є в FE дірки / нульові / missing фічі?** Так, критичні дірки: повністю відсутні `bb_position`, `rsi_14`, `stoch_k` та інші TA фічі, через що `ta_ensemble` відхиляє всі бари.
11. **Які 3 найкритичніші runtime проблеми зараз по факту логів?** 1) Баг ExecutionGuard `local_manage_state_conflict`. 2) Відсутність базових TA-фіч у FE. 3) 24-годинний cold_start у `md_amr`.
12. **Який найкоротший practical next step after this audit?** Пофіксити логіку порівняння станів у `ExposureGuard` (FSM), щоб він пропускав інтенти для `FLAT`-стану.

---

### Table 1 — md_amr Startup Dependency Matrix
| Dependency | Observed in logs? | Candle-only? | Blocks startup? | Evidence | Verdict |
|------------|-------------------|--------------|-----------------|----------|---------|
| Bar Buffer | Yes | Yes | Yes | `md_amr_handler:cold_start:8/96` | Needs 96 bars hydration |
| FE Warmup | Yes (Implied) | No | No | Signals emitted despite cold start | FE is ready earlier |
| Regime State| Yes | No | No | `regime:FLAT_LOW` in MR | Regime is already populated |

### Table 2 — Aurora Decision Chain Breakpoints
| Stage | Observed? | Last good event | Failure / stop reason | Evidence |
|-------|-----------|-----------------|-----------------------|----------|
| FE Generation | Yes | `Calculated features...` | Misses TA indicators | `missing required features: bb_position...` |
| Strategy Signal | Yes | `EVT:STRATEGY_SIGNAL_PRODUCED`| N/A | `MR Signal: LONG confidence=0.85` |
| Decision Gate | Yes | `TRADE_INTENT_PROPOSED` | N/A | `All gates passed, emitting TRADE_INTENT_PROPOSED` |
| Execution Guard | **NO** | `Processing TRADE_INTENT -> CMD:OPEN` | `local_manage_state_conflict` | `Execution Rejected: OPEN_GUARD_FAIL` |

### Table 3 — FE Feature Integrity Matrix
| Feature | Observed populated? | Observed null/zero? | Suspicious? | Evidence |
|---------|---------------------|---------------------|-------------|----------|
| `obi`, `tfi` | Yes | No | No | Valid floats in FE payload |
| `pillar_sum` | Yes | No | No | Handled correctly across all symbols |
| `bb_position`, `rsi_14`| No | Yes (Missing) | **Yes (Critical)** | `Provider ta_ensemble skipped: missing...` |
| `macro_resid` | Yes | No | No | Populated in FE payload |

### Table 4 — Quadratic Logging Coverage
| Signal component | Logged where? | Sufficient? | Missing visibility? | Recommendation |
|------------------|---------------|-------------|---------------------|----------------|
| `pillar_sum` components | `FeatureEngineering` | Yes (for FE) | Missing in DM | Propagate to intent metadata |
| Risk Score (Toxicity) | `DecisionMaking` | Yes | None | N/A |
| Final exposure/score | Aurora code only (`KERNEL_DIAG`, `QUADRATIC_DECISION_TRACE`) | **No** | Not found in live logs; missing from standard decision trace serialization | Fix `CMD:PROCESS_STRATEGY.tf_sec`, route `aurora_handler.*` to a stable sink, and embed compact Quadratic trace into `TRADE_INTENT` / `EVT:DECISION_TRACE_EMITTED` |
