# SYSTEM NOT TRADING FORENSIC AUDIT

Date: 2026-03-15
Repo: Phenix / Aurora
Scope: runtime logs, active configs, decision/execution code, WAL, order ledger

## 1. Executive Verdict

Система зараз не торгує не через одну причину, а через стек реальних blocker'ів на різних шарах. Головний blocker для більшості runtime-active strategy scope це cold-start readiness: `aurora` на `BTCUSDT/ETHUSDT/SOLUSDT` заблокована вимогою `301` 5m bars і до останнього зафіксованого reject дійшла лише до `71/301`; `md_amr` на `XRPUSDT/BNBUSDT` заблокована вимогою `96` 15m bars і дійшла лише до `23/96`. Паралельно `mean_reversion` на `DOGEUSDT` не зламана, а системно гаситься власним regime gate (`regime_not_flat:TREND_UP/UNCERTAIN` на всіх сьогоднішніх bar decisions), а `llm_microstructure` взагалі не є автономною strategy і без зовнішнього `LLM_INTENT` ingress не може дійти до intent stage. Додатково execution runtime піднятий у `BACKTEST`/testnet path через конфлікт `system.yaml` vs `trading.yaml`, тому навіть при появі intent'ів live exchange path зараз не є коректно узгодженим. Факт дня: у WAL після старту немає жодного `TRADE_INTENT_PROPOSED`, у `data/order_ledger.db` немає ордерів за 2026-03-15.

## 2. Active Runtime Scope

| Strategy | Enabled | Active symbols | TF | Required history / warmup | Allowed regimes | Runtime status observed |
|---|---|---|---:|---|---|---|
| aurora | yes | BTCUSDT, ETHUSDT, SOLUSDT | 300s | `301` basis bars (`max(sma_long_period=192, atr_period + atr_sma_length - 1 = 301)`) | regime-driven, allowlist enforced in handler | Invoked, market/risk/regime alive, blocked by cold-start on all 3 symbols |
| mean_reversion | yes | DOGEUSDT | 300s | `min_bars=25` | `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`, `MEAN_REVERSION` | Invoked on 5m bars; today all observed bars neutral due non-flat regime |
| md_amr | yes | XRPUSDT, BNBUSDT | 900s | `96` basis bars | strategy-local regime/guard stack after readiness | Invoked on 15m bars; blocked by cold-start on both symbols |
| llm_microstructure | yes | 1000PEPEUSDT | 60s | no autonomous warmup path; external intent driven | external advisory flow | Features/risk present, but no autonomous decision loop and no external intents observed |

## 3. Timeline Reconstruction

- `2026-03-15 02:23:07` `domain_execution_position.log`: execution domain starts; runtime reports `ExecPosFSM using domain-specific mode: backtest`, `EXECUTION POSITION FSM MODE: BACKTEST`, adapter configured for testnet execution.
- `2026-03-15 02:23:07` `domain_regime_detector.log`: regime detector initialized, subscribed to `EVT:FEATURES_CALCULATED`.
- `2026-03-15 02:23:13` `domain_mean_reversion.log`: `MR_INIT` and `MR_REGISTER` for `DOGEUSDT`, timeframe `300`.
- `2026-03-15 02:23:19` `aurora_market_data.log`: market data worker starts, connects to Binance websocket, subscribes to `14` streams, begins continuous flow.
- `2026-03-15 02:30:04` to `02:30:05` `domain_regime_detector.log`: first regime states emitted for all 7 symbols.
- `2026-03-15 02:40:00` `domain_regime_detector.log`: stable regimes begin; `DOGEUSDT` goes `UNCERTAIN -> TREND_UP`, `1000PEPEUSDT` goes `UNCERTAIN -> MEAN_REVERSION`.
- `2026-03-15 02:34:59` through `06:24:59` UTC in `logs/mean_reversion/bars_300s.tsv/jsonl`: `DOGEUSDT` 5m bars are processed by MR; today all observed bars are neutral and blocked by non-flat regime.
- `2026-03-15 04:30:04` through `08:15:02` `logs/aurora_trades.log`: `md_amr` emits repeated `GUARD_REJECT: DECISION_REJECT` for `XRPUSDT` and `BNBUSDT`, progressing only from `8/96` to `23/96`.
- Throughout session `aurora_core.log`: `on_risk()` keeps reporting `is_trading_allowed=True` for all active symbols.
- Post-startup WAL (`ops/wal/2026-03-15.jsonl` after startup cutoff): `TRADE_INTENT_PROPOSED = 0`, `TRADE_INTENT_REJECTED > 0`, no order-placement evidence.

## 4. Blocker Taxonomy

### Category A — Data / Warmup blockers

- `aurora` cold-start gate on `BTCUSDT`, `ETHUSDT`, `SOLUSDT`
  - Evidence: WAL `BARS_REQUIRED_COLD_START`; latest observed reason `Cold-start: 71/301 bars seen`.
  - Impact: blocks all `aurora` symbols before candidate/intent stage.
- `md_amr` cold-start gate on `XRPUSDT`, `BNBUSDT`
  - Evidence: `logs/aurora_trades.log` repeated `md_amr_handler:cold_start:N/96`.
  - Impact: blocks both assigned md_amr symbols before decision can pass.
- Startup basis hydration path not confirmed in runtime logs
  - Evidence: code path exists in `apps/reference/main.py` and `apps/reference/bootstrap/startup_basis_hydrator.py`, but no `STARTUP_BASIS_EXECUTOR`, `STARTUP_BASIS_IMPORTED`, `STARTUP_BASIS_SEEDED`, or `MD_AMR_HYDRATION` entries were found in available logs.
  - Impact: high-probability cause of persistent cold-start on strategies that support seeding.

### Category B — Strategy logic blockers

- `mean_reversion` regime gate blocks `DOGEUSDT`
  - Evidence: `logs/mean_reversion/bars_300s.jsonl` today: `24` bars with `regime_not_flat:TREND_UP`, `23` bars with `regime_not_flat:UNCERTAIN`.
  - Impact: strategy runs, but never emits an actionable signal today.
- No evidence today that `mean_reversion` was blocked by warmup, liquidity, risk, qty, or execution filters
  - Evidence: no MR strategy reject in WAL except generic `NRR-046` decision noise; MR bar log shows explicit neutral reasons instead.

### Category C — Decision blockers

- `md_amr` decision guard reject
  - Evidence: `GUARD_REJECT: DECISION_REJECT - XRPUSDT/BNBUSDT buy (md_amr_handler:cold_start:N/96)`.
  - Impact: direct decision-layer veto after handler invocation.
- `aurora` strategy-level trade intent rejection
  - Evidence: WAL entries with `reason_code=BARS_REQUIRED_COLD_START`.
  - Impact: no candidate survives readiness gate.

### Category D — Risk blockers

- No confirmed current risk blocker
  - Evidence: `aurora_core.log` repeatedly reports `is_trading_allowed=True` for all 7 symbols.
  - Impact: risk is not the reason the system is currently not trading.

### Category E — Execution blockers

- No execution reject is needed to explain current no-trade state because no strategy reaches `TRADE_INTENT_PROPOSED`.
- Secondary execution-path blocker exists:
  - runtime execution domain is `BACKTEST`/testnet, so live exchange execution path is not aligned even if intents appeared.

### Category F — Config / Architecture blockers

- Global trading mode mismatch
  - Evidence: `config/aurora/system.yaml` sets `trading_mode: "backtest"`, while `config/aurora/trading.yaml` sets `mode: hybrid_live_data_testnet_exec`; runtime chooses `BACKTEST`.
  - Impact: exchange/runtime path is not operating under a clean, single SSOT mode.
- `llm_microstructure` is not an autonomous strategy
  - Evidence: plugin registers no FSM listeners; bridge only converts external `CMD:LLM_INTENT_SUBMIT_V1` into strategy signals.
  - Impact: `1000PEPEUSDT` cannot trade unless an external LLM producer is actually feeding intents.

## 5. Per-Strategy Analysis

### Strategy: aurora

- Config active scope
  - Symbols: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`
  - TF: `300s`
  - Basis requirement: `301` bars
- Observed log activity
  - Risk updates present continuously.
  - Regime detector active.
  - WAL contains repeated `BARS_REQUIRED_COLD_START`.
- Did it receive inputs?
  - Yes.
- Did it reach ready / warm state?
  - No.
- Did it produce candidate signal?
  - No confirmed candidate survived readiness gate.
- Did it get blocked? Where?
  - Yes, inside `aurora_handler` readiness/cold-start gate.
- Frequency of block reasons
  - WAL: `142` rejects per symbol (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`), representing duplicated handler + `_emit_strategy_blocked` writes for `71` live 5m bars.
- Primary blocker
  - `BARS_REQUIRED_COLD_START`
- Secondary blockers
  - Startup basis seeding/import not evidenced.
  - Global mode mismatch would affect downstream execution even if readiness were fixed.
- Confidence
  - High

### Strategy: mean_reversion

- Config active scope
  - Symbol: `DOGEUSDT`
  - TF: `300s`
  - Minimum bars: `25`
  - Allowed regimes: `FLAT_LOW`, `FLAT_NORMAL`, `FLAT_HIGH`, `MEAN_REVERSION`
- Observed log activity
  - `MR_INIT`, `MR_REGISTER`.
  - Dedicated MR bar logger records today’s DOGE 5m decisions.
- Did it receive inputs?
  - Yes.
- Did it reach ready / warm state?
  - Yes; today’s block reasons are not `insufficient_bars`.
- Did it produce candidate signal?
  - Not today.
- Did it get blocked? Where?
  - Yes, inside strategy logic before signal emission: non-flat regime veto.
- Frequency of block reasons
  - `47` observed DOGE 5m bars today in MR log.
  - `24` = `regime_not_flat:TREND_UP`
  - `23` = `regime_not_flat:UNCERTAIN`
- Primary blocker
  - Regime mismatch with MR allowlist / mapping.
- Secondary blockers
  - None confirmed today.
- Confidence
  - High

### Strategy: md_amr

- Config active scope
  - Symbols: `XRPUSDT`, `BNBUSDT`
  - TF: `900s`
  - Basis requirement: `96` bars
- Observed log activity
  - Repeated `GUARD_REJECT: DECISION_REJECT` in `logs/aurora_trades.log`.
- Did it receive inputs?
  - Yes, 15m bar cadence is visible through incrementing cold-start counter.
- Did it reach ready / warm state?
  - No.
- Did it produce candidate signal?
  - It reached decision guard evaluation, but readiness veto stopped it.
- Did it get blocked? Where?
  - Yes, `md_amr_handler` cold-start guard.
- Frequency of block reasons
  - `16` rejects for `XRPUSDT`, `16` rejects for `BNBUSDT` in today’s visible `aurora_trades.log` range.
  - Counter advanced only from `8/96` to `23/96`.
- Primary blocker
  - `md_amr_handler:cold_start`
- Secondary blockers
  - Missing runtime evidence that startup hydration seeded the handler.
- Confidence
  - High

### Strategy: llm_microstructure

- Config active scope
  - Symbol: `1000PEPEUSDT`
  - External advisory flow only
- Observed log activity
  - Feature and risk streams exist for the symbol.
  - No `LLM_INTENT` ingress observed in runtime logs/WAL.
- Did it receive inputs?
  - It receives market/risk context, but not autonomous strategy triggers.
- Did it reach ready / warm state?
  - Not applicable in the same sense; strategy depends on external intent ingress.
- Did it produce candidate signal?
  - No.
- Did it get blocked? Where?
  - Architectural block: no external LLM command was observed.
- Frequency of block reasons
  - `0` observed `LLM_INTENT` ingress events today.
- Primary blocker
  - External-intent dependency with no producer activity.
- Secondary blockers
  - Global mode mismatch would also affect execution path.
- Confidence
  - High

## 6. Per-Symbol Analysis

| Symbol | Strategy | Market data alive? | Warm / ready? | Actual blocker |
|---|---|---|---|---|
| BTCUSDT | aurora | Yes | No | `Cold-start: 71/301 bars seen` |
| ETHUSDT | aurora | Yes | No | `Cold-start: 71/301 bars seen` |
| SOLUSDT | aurora | Yes | No | `Cold-start: 71/301 bars seen` |
| DOGEUSDT | mean_reversion | Yes | Yes | Strategy-local regime veto: `TREND_UP` / `UNCERTAIN` |
| XRPUSDT | md_amr | Yes | No | `md_amr_handler:cold_start:23/96` |
| BNBUSDT | md_amr | Yes | No | `md_amr_handler:cold_start:23/96` |
| 1000PEPEUSDT | llm_microstructure | Yes | N/A | No external `LLM_INTENT` ingress; strategy is not autonomous |

## 7. Top Blockers Ranked

1. `aurora` cold-start on `BTCUSDT/ETHUSDT/SOLUSDT`
   - Largest affected scope.
   - `301` 5m bars means roughly 25 hours of live accumulation if startup seed fails.
2. `md_amr` cold-start on `XRPUSDT/BNBUSDT`
   - Full strategy class blocked.
   - `96` 15m bars means roughly 24 hours of live accumulation if startup seed fails.
3. `mean_reversion` regime veto on `DOGEUSDT`
   - Strategy is healthy but self-blocked on all observed bars today.
4. `llm_microstructure` external-intent dependency with zero ingress
   - `1000PEPEUSDT` is effectively non-participating without upstream producer.
5. Global mode mismatch: `system.yaml backtest` vs `trading.yaml hybrid_live_data_testnet_exec`
   - Not the cause of zero intents, but a real execution-path blocker / misconfiguration.
6. Startup basis hydration not evidenced in runtime logs
   - Best explanation for why warmup-sensitive strategies stayed cold despite live market data.

## 8. Confirmed vs Suspected Causes

### CONFIRMED by logs/code

- No `TRADE_INTENT_PROPOSED` after startup cutoff on 2026-03-15.
- No orders in `data/order_ledger.db` for 2026-03-15.
- `aurora` blocked by `BARS_REQUIRED_COLD_START` on all active aurora symbols.
- `md_amr` blocked by `md_amr_handler:cold_start` on both active md_amr symbols.
- `mean_reversion` processes `DOGEUSDT` bars and blocks itself with `regime_not_flat`.
- `llm_microstructure` is external-intent driven, and no `LLM_INTENT` ingress was observed today.
- Risk is not currently blocking trading.
- Market data and regime detector are alive.
- Execution runtime is in `BACKTEST` / testnet path.

### HIGH-PROBABILITY inferred

- Startup basis hydration did not successfully seed/import the required bars into the runtime consumers that matter for `aurora` and `md_amr`.
  - Reason: cold-start persists, handlers support seeding, executor exists in startup code, but no runtime log evidence of successful import/seed was found.

### LOW-CONFIDENCE hypotheses

- None needed to explain current no-trade state.

## 9. What Previous Cleanup / Audits Missed

- They fixated on `md_amr` cold-start and missed that `aurora` has a larger and more damaging cold-start blocker (`301` bars on 3 symbols).
- They risked misreading `NRR-046` spam as a blocker. It is mostly decision-layer noise from ignoring tick-level features for bar-only strategies, not the reason the system is not trading.
- They would have mislabeled `mean_reversion` as “no signals” without reading the dedicated MR bar log; the real reason today is regime veto, not missing inputs or risk reject.
- They would have treated `llm_microstructure` as a normal strategy, while in runtime it is advisory-only and requires external command ingress.
- They did not reconcile the configuration conflict between `system.yaml` (`backtest`) and `trading.yaml` (`hybrid_live_data_testnet_exec`).
- They did not verify whether startup basis executor telemetry actually appears in runtime logs.

## 10. Fix Recommendations

### Fix first

1. Make startup basis hydration fail-closed and observable.
   - Required outcome: for each active `(strategy, symbol, tf)` emit and retain `STARTUP_BASIS_EXECUTOR starting/done`, `STARTUP_BASIS_IMPORTED`, `STARTUP_BASIS_SEEDED`.
   - If required bars are not seeded, startup must declare strategy not ready explicitly instead of silently relying on 24h+ live accumulation.
2. Remove the config SSOT conflict for trading mode.
   - Pick one operational mode and make runtime obey one source.
   - If testnet execution is intended, `system.yaml` must not force `backtest`.

### Restore actual trade readiness

3. For `aurora`, either preload the full `301` 5m basis bars or reduce the basis requirement.
   - Current requirement means the strategy is structurally non-tradable for ~25h after restart if seed fails.
4. For `md_amr`, either preload the full `96` 15m basis bars or reduce the readiness threshold.
   - Current requirement means ~24h to become tradable after restart if seed fails.

### Strategy-local corrections

5. For `mean_reversion`, decide whether today’s `TREND_UP/UNCERTAIN` should truly be non-tradable.
   - If yes, this strategy is behaving correctly and is not a runtime fault.
   - If no, adjust regime mapping / allowlist / detector hysteresis for `DOGEUSDT`.
6. For `llm_microstructure`, either:
   - run the external LLM intent producer and instrument its ingress, or
   - stop counting `1000PEPEUSDT` as an active autonomous trading strategy.

### Architecture-level hardening

7. Add one runtime readiness dashboard per active strategy/symbol:
   - bars seen / required
   - last `CMD:PROCESS_STRATEGY`
   - last candidate count
   - last intent proposed count
   - last reject reason
8. Add an alert: if market data and risk are alive but `TRADE_INTENT_PROPOSED=0` for all active strategies over a configured window, emit a system-wide no-trade incident.
