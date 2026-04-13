# 21-HOUR RUNTIME FORENSIC CONTEXT PACK

**Date**: 2026-04-11
**Analyst**: Claude (forensic context collection)
**Session analyzed**: 2026-04-10 22:56 UTC → 2026-04-11 19:34 UTC (20h 38m wall-clock)
**Process**: Single continuous run, PID 24488, ZERO restarts

---

## 1. Executive Verdict

**CONTEXT_PACK_READY_WITH_GAPS**

The 21-hour runtime is coherently reconstructed. Strategy/decision/execution/regime behavior is documented with counts and timelines. However, **Phase 5 closure cannot be confirmed** from this run because:
- No restart occurred during the window, so no degraded-startup path was exercised.
- The `unknown_truth_records` field IS deployed in code (proven by its first appearance in operational JSONL on 2026-04-10 17:54), but it was never populated in a live degraded scenario during this run.
- The proof-of-concept scenario (report artifacts from Apr 10 15:11) demonstrates the mechanism works, but that is test evidence, not runtime evidence from this 21-hour session.

Additionally, three P0/P1 production defects overshadow any Phase 5 assessment:
1. Brackets never created (BracketsConfig.enable AttributeError)
2. MagicMock leak causing ORDER_REJECTED
3. FLIP_GATE_UNKNOWN blocking 130+ signals session-wide

---

## 2. Scope Checked

### Files Inspected
| Category | Files | Notes |
|----------|-------|-------|
| WAL | `ops/wal/2026-04-10.jsonl` (18,668 lines), `ops/wal/2026-04-11.jsonl` (17,302 lines) | Full decision/execution event stream |
| Core logs | `logs/aurora_core.log` through `.log.21` (22 rotations, ~220 MB total) | Full process lifetime |
| Domain logs | `domain_decision_making.log` (×3), `domain_execution_position.log` (×2), `domain_feature_engineering.log` (×16), `domain_regime_detector.log`, `domain_risk_management.log`, `domain_mean_reversion.log` | All active domains |
| Shadow journal | `logs/shadow_critical_event_journal_v1.jsonl` (30,426 records, 36.6 MB) | Critical event telemetry |
| Trade lifecycle | `logs/trade_lifecycle.jsonl` (100,817 records, 171.5 MB) | 99.4% sidecar evaluation records |
| Order log | `logs/order_log_v1.jsonl` (422 records) | Full order lifecycle |
| Aurora events | `logs/aurora_events.jsonl` (317 records) | Regime/feature summaries |
| Regime audit | `logs/regime_confidence_audit_v1.jsonl` (1,698 records) | Regime confidence trail |
| Terminal cache | `logs/execution_terminal_identity_cache_v1.json` (315 entries) | Terminal close identity |
| Restore envelope | `ops/restore/execution_position_restore_envelope_v1.json` | Live restore state (Apr 11 16:31) |
| Startup truth | `ops/restore/execution_position_startup_truth_v1.jsonl` (7 lines) | Full startup truth ledger |
| Proof artifacts | `reports/runtime_restore_unknown_startup_proof_20260410/` (6 files) | Phase 5 proof scenario |
| Config | `config/aurora/domains.yaml`, `instruments.yaml`, `strategies.yaml`, `strategies/aurora.yaml`, `strategies/md_amr.yaml` | Active declarations |
| Source | `apps/reference/domains/execution_position/fsm_manage.py`, `config_models.py`, `telemetry/order_logger.py` | Bug verification |
| Prior reports | `P1_24H_TESTNET_FORENSIC_REPORT_2026-04-10.md`, `PHASE5_CLOSURE_UNKNOWN_STARTUP_TRUTH_ROWS_REPORT_20260410.md` | Interpretation context |
| Roadmap | `VFOUNDATION_METAFSM2_ROADMAP_SSOT_v1.md` | Phase 5 exit criteria |
| Passports | `system_passport.md`, `trading_passport.md` | Config semantics |

### Runtime Window Analyzed
- **Start**: 2026-04-10 22:56:33 UTC (STARTUP log line)
- **End**: 2026-04-11 19:34 UTC (last log activity)
- **Duration**: 20h 38m
- **Restarts**: 0
- **Process**: Single continuous session

---

## 3. FACTS

1. **Single process, no restarts**: The entire 21-hour window is one continuous process with PID 24488. Zero shutdowns, zero restarts.
2. **BracketsConfig.enable AttributeError**: `fsm_manage.py:1261` accesses `self._manage_cfg.brackets.enable` but `BracketsConfig` (config_models.py:1464) has no `enable` field. This raises `AttributeError` on every `EVT:TRADE_EXECUTED`, meaning **zero bracket SL/TP orders were placed during the entire run**.
3. **36 positions opened, 3 closed**: WAL shows 24 OPEN on Apr 10, 12 on Apr 11. Only 3 CLOSE events occurred — all `position_policy_sidecar_soft_close` on BTCUSDT.
4. **6 OBJECTIVE_REALIZED_V1 entries**: 5 mean_reversion DOGEUSDT trades (net -5.74 USDT), 1 md_amr XRPUSDT trade (-55.97 USDT). Net realized: -61.72 USDT.
5. **Wallet drawdown**: 2950.38 → 2735.64 USDT (-7.3%, -214.74 USDT).
6. **Portfolio flip**: Started with 3 short positions (SOL, ETH, BTC), ended with 3 long positions (BNB, DOGE, XRP).
7. **REGIME_NOT_ALLOWLISTED dominates Apr 11**: 621/622 STRATEGY_DECISION_BLOCKED are regime-gated. Affects BTC (208), ETH (208), SOL (206) — all aurora symbols.
8. **FLIP_GATE_UNKNOWN**: 130 TRADE_INTENT_REJECTED across both days, session-wide (not cold-start only).
9. **10 ORDER_REJECTED with MagicMock**: All on Apr 10, error message `'>' NOT SUPPORTED BETWEEN INSTANCES OF 'MAGICMOCK' AND 'INT'` — a test mock object reached the production adapter comparison.
10. **Startup restore artifact was stale**: Age 7197s at startup (22:56:44), threshold 300s. No authoritative records applied.
11. **unknown_truth_records field deployed**: First appears in operational startup_truth JSONL at line 5 (2026-04-10 17:54:59 UTC). Lines 1-4 (Apr 7-9) lack the field entirely.
12. **Three DNS outage windows**: (a) 23:25 transient, (b) 13:09-15:21 intermittent (~2h12m, including 9-min and 5.4-min market data blackouts), (c) 18:32-18:55 (~23min, including 18-min market data blackout).
13. **Entropy spike spam**: `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED x84` and `EVT:BALANCE_UPDATE_RECEIVED x11` fire every ~60s for the entire run (~1200+ CRITICAL lines). Threshold=10 is too low for production tick rates.
14. **Shadow telemetry offline**: 24,370 failed deliveries to `tcp://127.0.0.1:7101`.
15. **Schema validation errors**: (a) `EVT:MARKET_TICK_RECEIVED` rejects negative scientific notation floats (`-6.10e-11`) — new bug surfaced at 18:33+. (b) `EVT:EXPOSURE_SUMMARY_UPDATED` missing `exposure_summary` required property (2 occurrences).
16. **SOLUSDT bracket_truth_source permanently UNKNOWN**: Across all 7 startup truth entries and the live restore envelope, SOLUSDT has never been resolved.
17. **ETHUSDT deferred bracket stale**: `entry_order_id: 8634021930` has been in `DEFERRED_PENDING_WAL` state since at least Apr 8 (4+ days), never progressing to `LINKED_ACTIVE`.

---

## 4. INFERENCES

1. **All 460 fills (154 + 306) are bracket-unprotected**: Since `_should_place_brackets()` raises AttributeError on every call and no bracket orders appear in order log, every open position runs without SL/TP until the sidecar soft-close or manual intervention.
2. **The 10 MagicMock ORDER_REJECTED suggest a test mock leaked into production scope**: The `order_logger.py` already imports `unittest.mock` and has MagicMock-aware serialization, but the comparison `'>' NOT SUPPORTED BETWEEN INSTANCES OF 'MAGICMOCK' AND 'INT'` indicates a different code path where a mock replaces a numeric config value. Likely linked to brackets or adapter initialization.
3. **FLIP_GATE_UNKNOWN is caused by missing position lifecycle state**: After a position closes, the flip tracker has no way to determine the last side. This is the same DEF-005 (OrderIndex not restored on restart) issue identified in prior audits, compounded by lack of initial flip state from portfolio REST.
4. **Aurora is effectively regime-blocked on Apr 11**: 621 regime blocks vs only 5 proposals that passed. The structural regime for BTC/ETH/SOL was not in aurora's allowlist for most of the day — likely LOW_VOLATILITY or MEAN_REVERSION states which aurora does not trade.
5. **The -55.97 XRPUSDT loss was a 10.2h hold without functional SL**: md_amr opened a LONG, brackets failed to place, position drifted until the sidecar eventually soft-closed it at a loss.
6. **DNS instability is likely ISP/network, not application**: The pattern (getaddrinfo failed for both `fstream.binance.com` and `testnet.binancefuture.com`) indicates OS-level DNS resolution failure, not Binance-side. Affects all subsystems simultaneously.

---

## 5. ASSUMPTIONS

1. The 21-hour window (Apr 10 22:56 to Apr 11 19:34) is representative of current system behavior under the deployed codebase.
2. The proof-of-concept scenario at `reports/runtime_restore_unknown_startup_proof_20260410/` was generated by a controlled test, not an organic production restart.
3. `aurora_trades.log` (7.6 KB, last write 17:40) contains the subset of trade events actually written to the trades sink (low volume because most fills route through WAL/lifecycle instead).
4. The `BARS_REQUIRED_COLD_START` rejections (336 on Apr 10, 0 on Apr 11) confirm the warmup gate functions correctly — it blocks during initial warmup then releases.
5. The `BracketsConfig.enable` bug has been present since the field was removed (referenced as `TASK-ZOMBIE-FIX` at config_models.py:1471), and is NOT new to this session.

---

## 6. UNKNOWNS

1. **When exactly was `BracketsConfig.enable` removed?** The `TASK-ZOMBIE-FIX` comment at config_models.py:1471 references removing `stop_loss_bps`, but the `enable` field removal is not annotated. Unknown if this regression is days or weeks old.
2. **What is the MagicMock leak path?** The mock comparison error happens in the adapter layer but no production code in `apps/reference/` directly instantiates MagicMock except in test files and the serialization guard. The exact injection point is unknown from logs alone.
3. **Would a live degraded restart actually populate `unknown_truth_records`?** The proof scenario says yes, but no organic degraded restart occurred during this run. It remains unproven in real production conditions.
4. **Is ETHUSDT deferred bracket (8634021930) a live exchange order or stale?** It has persisted for 4+ days without resolution. Unknown whether Binance still holds this order.
5. **What regime states are BTC/ETH/SOL in when aurora allows trading?** The 621 REGIME_NOT_ALLOWLISTED blocks suggest aurora's allowlist may be too narrow for current market conditions, but the specific regime-vs-allowlist mismatch is not clear from WAL alone (regime_confidence_audit JSONL would need cross-referencing with strategy allowlists).
6. **Why did SOLUSDT never resolve from UNKNOWN?** Across all 7 startup truth entries and the live restore envelope, its bracket_truth_source is UNKNOWN. No guardian reconstruction, no WAL bracket reference, no runtime progression.

---

## 7. Runtime Timeline Reconstruction

### Phase 1: STARTUP + WARMUP (22:56 — 23:05 UTC)
| Time (UTC) | Event |
|---|---|
| 22:56:33 | **STARTUP** — Logging configured, trading mode `hybrid_live_data_testnet_exec` |
| 22:56:33 | Startup guard: validating 7 symbols exchange filters |
| 22:56:37-38 | Subsystems initialized: WAL GC, AlertManager, EntropyMonitor, SchemaRegistry, FSMCore, MarketDataProxy (7 symbols), FeatureEngineering, BarAggregator, RiskManagement, ExposureGuard, OrderGuardian |
| 22:56:39 | RegimeDetector initialized (sma_trend_v1, basis_tf=300s) |
| 22:56:41 | WebSocket connected successfully (initial) |
| 22:56:44 | **Execution restore: artifact STALE** (age=7197s, threshold=300s) — NO authoritative records applied |
| 22:56:44-46 | Strategies registered: aurora (BTC/ETH/SOL), md_amr (BNB/XRP), mean_reversion (DOGE) |
| 22:56:46 | STARTUP_HYDRATION_PLAN emitted: 6 strategy/symbol pairs, all COLD |
| 22:56:49 | **STARTUP_WARMUP_GATE activated** |
| 22:57:00-17 | FE warmup begins; rapid warm-up bar replay |
| **22:58:18** | **CRITICAL: First entropy spike** — `LOOP_DETECTED: BALANCE_UPDATE x11` (continues every ~60s for entire run) |
| 23:05:01 | First regime detection: all 7 symbols initially UNCERTAIN |

### Phase 2: REGIME TRANSITION + FIRST TRADES (23:05 — 23:40)
| Time (UTC) | Event |
|---|---|
| 23:10:01 | Regime confirmed: all 7 symbols → TREND_UP (hysteresis 2-bar) |
| **23:15:01** | **FIRST TRADE**: SOLUSDT SELL proposed (price=85.33, qty=71) |
| 23:15:03 | SOLUSDT SELL ACK (order_id=1839259132) |
| **23:18:21** | **BUG: BracketsConfig.enable AttributeError** on EVT:TRADE_EXECUTED (bracket creation fails) |
| 23:20:02 | SOLUSDT SELL FLIP_GATE_UNKNOWN rejection |
| 23:25:18 | **DNS failure #1**: `getaddrinfo failed` on account balance (transient, resolves quickly) |
| 23:40:03 | ETHUSDT SELL + BTCUSDT SELL proposed+ACK |

### Phase 3: OVERNIGHT TRADING (23:40 — 09:00)
| Time (UTC) | Event |
|---|---|
| 00:05 | SOLUSDT SELL ACK |
| 00:20 | Regime shift: SOL/ETH/DOGE → UNCERTAIN |
| 00:25-00:30 | BNB → UNCERTAIN, XRP → LOW_VOLATILITY |
| 01:00-01:30 | BNB buy ×3 REGIME_GATE_BLOCKED (md_amr) |
| 01:40 | DOGEUSDT BUY ACK (MR, price=0.0938) — BracketsConfig error |
| 02:00 | BNBUSDT BUY ACK (md_amr, price=607.07) — BracketsConfig error |
| 02:30 | XRPUSDT BUY ACK (md_amr, price=1.3555) — BracketsConfig error |
| 04:25-09:00 | DOGEUSDT BUY/SELL cycles (MR strategy), all unprotected by brackets |

### Phase 4: DNS OUTAGE #2 — MAJOR (13:09 — 15:21)
| Time (UTC) | Event |
|---|---|
| 12:37 | Market data WS: first No PONG warning |
| **13:09:33** | **DNS outage begins**: `getaddrinfo failed` for `fstream.binance.com`, exponential backoff |
| 13:09:51 | Market data WS recovers (first reconnect) |
| 13:09-14:09 | 54 DNS errors, 8 WS failures — intermittent |
| **14:15-14:24** | **9-minute market data blackout** |
| 14:25 | Regime shift: all symbols → LOW_VOLATILITY |
| 14:34-15:21 | Intermittent gaps: 2-min, 2.5-min, **5.4-min** blackouts |

### Phase 5: RECOVERY + AFTERNOON (15:21 — 18:15)
| Time (UTC) | Event |
|---|---|
| 15:21+ | Market data stabilizes |
| 16:20 | Regime shift: ETH/BTC → MEAN_REVERSION, 1000PEPE → LOW_VOLATILITY |
| 16:30 | ETHUSDT SELL ACK, DOGEUSDT BUY ACK — BracketsConfig errors |
| 17:00-17:40 | BTCUSDT SELL proposed ×3 → all OPEN_GUARD_FAIL |

### Phase 6: DNS OUTAGE #3 (18:32 — 18:55)
| Time (UTC) | Event |
|---|---|
| 18:17 | Schema error: `EVT:EXPOSURE_SUMMARY_UPDATED` missing field |
| **18:32-18:55** | DNS cascade: execution WS dies + reconnects twice, **18-min market data blackout** |
| 18:33:47 | **NEW BUG**: `EVT:MARKET_TICK_RECEIVED` schema rejects negative floats (`-6.10e-11`) |

### Phase 7: STABLE TAIL (18:55 — 19:34)
| Time (UTC) | Event |
|---|---|
| 18:55+ | All connectivity recovered |
| 19:23+ | Features calculating normally, system stable |

---

## 8. Strategy Activity Matrix

| Strategy | Symbols | Intents Proposed | Intents Rejected | Blocked | Fills | Closes | Net PnL | Verdict |
|---|---|---|---|---|---|---|---|---|
| **aurora** | BTC, ETH, SOL | 55 (50+5) | 152 (cold-start 336, flip 111, guard 37) | 621 REGIME_NOT_ALLOWLISTED | ~130 | 3 (sidecar) | unknown (unrealized) | **REGIME-GATED on Apr 11**; active overnight; all positions unprotected by brackets |
| **md_amr** | XRP, BNB | 7 (all Apr 11) | 0 | ~100 REGIME (overnight) | ~261 | 1 | **-55.97** | First live intents; XRPUSDT 10.2h unprotected LONG stopped out |
| **mean_reversion** | DOGE | 18 (11+7) | 1 (OPEN_GUARD_FAIL) | 0 | ~11 | 5 | **-5.74** | Most active closer; 2 TP wins, 3 SL losses |
| **llm_microstructure** | 1000PEPE | 0 | 0 | 0 | 0 | 0 | 0 | **SILENT**: shadow tap offline (24,370 delivery failures). Expected: shadow-only, but no telemetry flowing |

### Per-strategy notes:

**aurora**: Proposed 50 intents on Apr 10 (warmup window), only 5 on Apr 11. The collapse from 50→5 is explained by REGIME_NOT_ALLOWLISTED (621 blocks on Apr 11) — BTC/ETH/SOL entered LOW_VOLATILITY or MEAN_REVERSION states which aurora does not trade. This is expected gating behavior but indicates aurora traded actively for ~2 hours then was regime-suppressed for ~18 hours.

**md_amr**: First time producing live trade intents (7 on Apr 11). XRP and BNB positions were opened. The XRPUSDT -55.97 loss (10.2h hold, SL exit) accounts for 90% of the day's realized losses. **All md_amr positions were unprotected by brackets** due to the BracketsConfig bug.

**mean_reversion**: Most consistent — 18 intents across both days, 5 completed trade cycles. Win rate 40% (2 TP, 3 SL). Net -5.74 USDT. This is the only strategy with functional close behavior (via sidecar evaluation).

**llm_microstructure**: Completely silent. 1000PEPEUSDT is assigned to this strategy but the shadow telemetry IPC tap at `tcp://127.0.0.1:7101` is not running. 24,370 failed delivery attempts confirm no LLM intent pipeline is operational.

---

## 9. Decision / Reject / Defer Analysis

### Quantitative Summary

| Decision Class | Apr 10 | Apr 11 | Total |
|---|---|---|---|
| TRADE_INTENT_PROPOSED | 61 | 19 | **80** |
| TRADE_INTENT_REJECTED | 492 | 23 | **515** |
| STRATEGY_DECISION_BLOCKED | 609 | 622 | **1,231** |
| INTENT_DEFERRED | 0 | 0 | **0** |
| DECISION_BLOCKED | 0 | 0 | **0** |

### Reject Reason Breakdown

| Reason | Count | Symbols | Mechanism | Expected? |
|---|---|---|---|---|
| **BARS_REQUIRED_COLD_START** | 336 | all | Warmup gate, releases after hydration | YES — normal cold-start |
| **REGIME_NOT_ALLOWLISTED** | 800 (179+621) | BTC, ETH, SOL (aurora); BNB, XRP (md_amr) | Structural regime not in strategy allowlist | YES for gating, PATHOLOGICAL for duration (18h suppression) |
| **FLIP_GATE_UNKNOWN** | 130 (111+19) | SOL(6), ETH(7), BTC(4), DOGE(9) + others | Flip state tracker uninitialized, no portfolio REST seed | NO — session-wide defect (DEF-005 related) |
| **NRR-EXECUTION-REJECTED (OPEN_GUARD_FAIL)** | 41 (37+4) | BTC(3), DOGE(1) + others | Open position already exists for symbol | YES — expected guard |
| **ARBITRATION_BLOCKED** | 8 | unknown | Strategy arbitration priority conflict | YES — normal |
| **HOLDING_PERIOD_ACTIVE** | 44 | unknown | Hold timer active | YES — expected |
| **REENTRY_COOLDOWN** | 22 | unknown | Cooldown after close | YES — expected |
| **GATE_ANTI_FLAT_SIGMA** | 17 | unknown | Signal too close to flat threshold | YES — expected |
| **ANCHOR_SHOCK_VETO** | 11 | unknown | Anchor price shock detected | YES — expected |
| **LIQUIDITY_LOW** | 2 | unknown | Insufficient liquidity | YES — expected |

### Key Findings:
1. **INTENT_DEFERRED still zero** — confirms the kernel defer path is never activated (same as prior audit).
2. **DECISION_BLOCKED still zero** — the old taxonomy verb is unused.
3. **REGIME_NOT_ALLOWLISTED is 65% of all blocks** — the most significant suppression mechanism.
4. **FLIP_GATE_UNKNOWN is the only pathological rejection** — 130 legitimate trading signals suppressed by a known defect.

---

## 10. Execution / Lifecycle Findings

### Order Lifecycle
| Metric | Apr 10 | Apr 11 | Total |
|---|---|---|---|
| ORDER_PLACED | 24 | 12 | **36** |
| ORDER_FILLED (fills) | 154 | 306 | **460** |
| ORDER_REJECTED | 10 | 0 | **10** |
| CANCEL_ORDER | 23 | 7 | **30** |
| ORDER_STATE_CHANGED | 2 | 3 | **5** |
| POSITION OPEN | 24 | 12 | **36** |
| POSITION CLOSE | 3 | 0 | **3** |
| OBJECTIVE_REALIZED_V1 | 0 | 6 | **6** |

### Critical Execution Defects

**DEF-BRACKET-ENABLE (P0)**: `fsm_manage.py:1261` accesses `self._manage_cfg.brackets.enable` but `BracketsConfig` (config_models.py:1464) has no `enable` field (only `sl`, `tp`, `oco_emulation`, `offset_bps`). This raises `AttributeError` on every `EVT:TRADE_EXECUTED` → `_should_place_brackets()` → no brackets placed → all 36 positions run without SL/TP protection. The error is logged as `BracketsConfig.enable` in core logs. **Every trade in this session is unprotected.**

**DEF-MOCK-LEAK (P1)**: 10 ORDER_REJECTED on Apr 10 with `'>' NOT SUPPORTED BETWEEN INSTANCES OF 'MAGICMOCK' AND 'INT'`. A test mock object reached a production comparison in the adapter layer. `order_logger.py` imports `unittest.mock` and has MagicMock-aware serialization, which may be the injection vector. The exact production comparison path is unconfirmed.

### Close Analysis
- Only 3 position closes occurred, all `position_policy_sidecar_soft_close` on BTCUSDT (Apr 10).
- 6 OBJECTIVE_REALIZED_V1 entries (5 DOGEUSDT MR, 1 XRPUSDT md_amr) — these imply closes happened but through the sidecar/lifecycle path rather than bracket-triggered exits.
- No bracket-triggered SL/TP closes (consistent with brackets never being placed).

### Position State at End of Run
| Symbol | Side | Qty | Status |
|---|---|---|---|
| BNBUSDT | LONG | 10.08 | Open, unprotected |
| DOGEUSDT | LONG | 32,775 | Open, unprotected |
| XRPUSDT | LONG | 4,521.6 | Open, unprotected |

### Execution Verdict
**Unhealthy execution continuity.** The bracket placement mechanism is completely broken. All positions are protected only by the sidecar soft-close policy (shadow mode). The mean_reversion strategy achieved 5 closes through the sidecar; aurora and md_amr positions accumulated without protection.

---

## 11. Restart Truth / Startup Truth Findings

### Startup Truth Ledger (7 entries, Apr 7-11)

| Line | Timestamp (UTC) | symbols_considered | unknown_truth_records | artifact_state | applied_records |
|---|---|---|---|---|---|
| 1 | Apr 7 07:21 | [] | FIELD ABSENT | N/A | 0 |
| 2 | Apr 8 10:44 | [] | FIELD ABSENT | stale (dark_read) | 0 |
| 3 | Apr 8 23:32 | [] | FIELD ABSENT | stale | 0 |
| 4 | Apr 9 09:52 | [DOGE,ETH,SOL] | FIELD ABSENT | stale | 0 |
| **5** | **Apr 10 17:54** | [] | **PRESENT** (empty []) | stale | 0 |
| **6** | **Apr 10 17:56** | [ETH,SOL] | **PRESENT** (empty []) | **VALID** (age=78s) | **2** |
| **7** | **Apr 10 19:56** | [] | **PRESENT** (empty []) | stale | 0 |

### Key Findings

1. **unknown_truth_records field IS deployed**: First appears at line 5 (2026-04-10 17:54:59). Lines 1-4 lack the field entirely. Code change was deployed between Apr 9 09:52 and Apr 10 17:54.

2. **unknown_truth_records is empty [] in all live startups**: Reasons:
   - Lines 5, 7: `symbols_considered` empty (no exchange positions found) → no candidates for unknown classification
   - Line 6: Artifact was VALID (78s old) → authoritative restore applied → degraded path not taken; both ETH and SOL were portfolio-absent → don't qualify for "portfolio_present_without_restored_lifecycle_truth"

3. **Line 6 is the most informative startup** (Apr 10 17:56): The restore artifact was valid (under 300s), so 2 records were applied. `mixed_certainty: true` with `mixed_certainty_symbols: ["ETHUSDT"]`. symbol_statuses show:
   - ETHUSDT: bracket_state=`exact` (DEFERRED_PENDING_WAL), manage_phase=`unknown`, close_phase=`unknown`
   - SOLUSDT: all `unknown` across all three fields

4. **The proof scenario demonstrates population works**: At `reports/runtime_restore_unknown_startup_proof_20260410/`, a fabricated stale artifact + portfolio-present ETHUSDT correctly produced 1 unknown_truth_record with proper reason codes.

5. **No degraded startup occurred during the 21-hour run**: The session started once at 22:56 with a stale artifact (line 7 in the ledger), applied 0 records, found 0 symbols_considered. No restart occurred afterward. The degraded-startup-with-populated-unknown-truth path was never exercised.

### Restore Envelope State (Live, Apr 11 16:31)
| Symbol | bracket_state | bracket_truth_source | manage_phase |
|---|---|---|---|
| BNBUSDT | LINKED_ACTIVE | RUNTIME_LOCAL | BRACKETS_PENDING |
| BTCUSDT | LINKED_ACTIVE | RUNTIME_LOCAL | BRACKETS_PENDING |
| DOGEUSDT | LINKED_ACTIVE | RUNTIME_LOCAL | BRACKETS_PENDING |
| ETHUSDT | DEFERRED_PENDING_WAL | RESTORED_PENDING_WAL | FLAT |
| SOLUSDT | **UNKNOWN** | **UNKNOWN** | FLAT |
| XRPUSDT | LINKED_ACTIVE | RUNTIME_LOCAL | BRACKETS_PENDING |

### Persistent Truth Anomalies

- **SOLUSDT is UNKNOWN everywhere**: Never resolved across any startup, any restore envelope, any runtime. No guardian reconstruction, no WAL bracket reference.
- **ETHUSDT deferred bracket stale 4+ days**: `entry_order_id: 8634021930` in DEFERRED_PENDING_WAL since Apr 8. Never progressed.
- **manage_phase = BRACKETS_PENDING but brackets never placed**: 4 symbols show BRACKETS_PENDING in restore envelope, but no brackets were created due to the BracketsConfig bug. This is phantom manage_phase state.
- **runtime_truth_records empty in all live startups**: No guardian-based bracket reconstruction has succeeded in production during this window.

### Phase 5 Closure Assessment

**Cannot confirm Phase 5 closure from this run.**

| Phase 5 Exit Gate | Status | Evidence |
|---|---|---|
| Restart restores working execution state without semantic guessing | **UNPROVEN** | No restart occurred during the 21-hour run |
| Execution lifecycle snapshot separate from portfolio snapshot | **PARTIAL** | Restore envelope exists independently, but SOLUSDT is permanently UNKNOWN |
| Operator can explain restored/reconstructed/unknown | **PARTIAL** | Field deployed + proof scenario works, but never exercised in live degraded conditions |
| unknown_truth_records populated in degraded startup | **UNPROVEN IN PROD** | Proof scenario shows it works; no live degraded startup to exercise |
| restored_exact / reconstructed / unknown / cache_only all separable | **PARTIAL** | All 4 categories exist structurally; only cache_only and restored_exact have been exercised live |

---

## 12. Freshness / Liveness Findings

### Regime Detector
- **Operational**: Produced 1,698 regime confidence audit records across the run.
- **Regime states observed**: TREND_UP, UNCERTAIN, LOW_VOLATILITY, MEAN_REVERSION.
- **Freshness**: Emitting on 5-min bar basis (300s) as configured.
- **Issue**: POST-DNS-OUTAGE regime shifts to LOW_VOLATILITY may be driven by stale data gaps rather than genuine market conditions. The 14:25 → LOW_VOLATILITY transition immediately follows the 9-min market data blackout.

### Feature Engineering
- **Operational**: 16 log rotations (~80 MB) confirm continuous feature calculation for all 7 symbols.
- **Warmup**: Completed correctly. 336 BARS_REQUIRED_COLD_START rejections on Apr 10, zero on Apr 11.
- **ATR/TR seeding**: Functional (prior fix deployed).
- **Staleness**: No explicit feature staleness alerts found in domain logs during the stable periods.

### Portfolio / Exposure
- **Freshness issue**: `EVT:EXPOSURE_SUMMARY_UPDATED` schema error (missing `exposure_summary` field) at 08:58 and 18:17 — 2 exposure freshness gaps.
- **Balance updates**: 11,369 ACCOUNT_UPDATE_RECEIVED on Apr 11 (continuous Binance WebSocket feed).
- **Entropy spike**: Balance updates trigger 11-event bursts → LOOP_DETECTED every 60s, but the updates themselves are fresh.

### Startup Seed / Warmup
- **Warmup functional**: Cold-start gate activated at 22:56:49, warmup bars replayed 22:57-23:05, first regime at 23:05:01, first trade at 23:15:01. ~18 minutes from startup to first trade — normal.
- **Startup artifact**: Stale at boot (7197s age), so no authoritative restore. This is expected for a fresh start after extended downtime.

### Cache-Only Surfaces
- **execution_truth_cache**: Empty (0 entries loaded) in all live startups. The terminal identity cache file (`execution_terminal_identity_cache_v1.json`) has 315 entries but these were not consumed at startup. This cache contributes nothing to startup truth.

---

## 13. Runtime-vs-SSOT Drift Findings

Only material drifts identified:

| Drift | SSOT Declares | Runtime Shows | Impact |
|---|---|---|---|
| **BracketsConfig.enable** | `BracketsConfig` has `sl`, `tp`, `oco_emulation`, `offset_bps` (config_models.py:1464-1472) | `fsm_manage.py:1261` accesses `.enable` (non-existent field) | **CRITICAL**: All bracket placement broken |
| **manage_phase = BRACKETS_PENDING** | BRACKETS_PENDING implies brackets are being placed | No brackets placed (enable bug) | Phantom lifecycle state in restore envelope |
| **llm_microstructure shadow_telemetry** | domains.yaml declares shadow_telemetry `enabled: true`, IPC tap on port 7101 | 24,370 failed deliveries to 7101, zero LLM intents | Shadow subsystem declared but offline; 1000PEPEUSDT entirely inert |
| **Flip orchestration** | domains.yaml: `enabled: false` globally | FLIP_GATE_UNKNOWN rejections (130) | Flip is disabled in config yet the flip gate still rejects — the gate checks pre-flip state even when flip is disabled |
| **Position Policy Sidecar** | domains.yaml: `mode: shadow` | Sidecar produced 99.4% of trade_lifecycle records (100,135/100,817) and executed the only 3 closes | Sidecar is doing more than "shadow" — it's the primary close mechanism |
| **QoS enforcement** | domains.yaml: `mode: enforce` for aurora, md_amr | No QoS-related rejections visible in WAL | Cannot confirm QoS enforcement is operational (may silently pass) |
| **ETHUSDT deferred bracket** | Restore envelope: DEFERRED_PENDING_WAL | 4+ days without resolution | WAL-deferred bracket reference is effectively dead state |
| **SOLUSDT truth** | Restore envelope: bracket_truth_source=UNKNOWN | Permanently unknown across all startups | No resolution mechanism exists for this symbol's bracket truth |

---

## 14. Quantitative Summary

| Metric | Value |
|---|---|
| **Run duration** | 20h 38m |
| **Startups / restarts** | 1 / 0 |
| **Active symbols** | 7 (BTC, ETH, SOL, XRP, BNB, DOGE, 1000PEPE) |
| **Trading symbols** | 6 (1000PEPE inactive) |
| **aurora intents proposed** | 55 |
| **md_amr intents proposed** | 7 |
| **mean_reversion intents proposed** | 18 |
| **llm_microstructure intents** | 0 |
| **Total intents proposed** | 80 |
| **Total intents rejected** | 515 |
| **Total strategy-blocked** | 1,231 |
| **Total intents deferred** | 0 |
| **Orders placed** | 36 |
| **Orders filled** | 460 fills across 36 orders |
| **Orders rejected** | 10 (MagicMock leak) |
| **Orders cancelled** | 30 |
| **Positions opened** | 36 |
| **Positions closed** | 3 (all sidecar soft-close) |
| **Realized trades (OBJECTIVE_REALIZED)** | 6 |
| **Realized net PnL** | -61.72 USDT |
| **Wallet start → end** | 2950.38 → 2735.64 USDT (-7.3%) |
| **Major reject reason #1** | REGIME_NOT_ALLOWLISTED (800) |
| **Major reject reason #2** | BARS_REQUIRED_COLD_START (336) |
| **Major reject reason #3** | FLIP_GATE_UNKNOWN (130) |
| **Bracket SL/TP orders placed** | **0** (BracketsConfig.enable bug) |
| **DNS outage windows** | 3 (transient / 2h12m intermittent / 23min) |
| **Market data blackout (worst)** | 18 minutes (18:36-18:54) |
| **Entropy CRITICAL spam** | ~1,200+ events |
| **Shadow telemetry delivery failures** | 24,370 |
| **Degraded startup truth incidents** | 0 (no restart occurred) |
| **Schema validation errors** | 2 types (negative float, missing exposure_summary) |

---

## 15. Priority Findings for Next Work

### Ranked by severity and impact:

**P0-1. BracketsConfig.enable — ALL BRACKETS BROKEN**
- `fsm_manage.py:1261` accesses non-existent `.enable` field on `BracketsConfig`
- **Impact**: Every position in every strategy runs without SL/TP protection. 36 position opens, 0 bracket orders. The -55.97 XRPUSDT loss was a bracket-unprotected 10.2h hold.
- **Fix scope**: Single line — either add `enable: bool` field to `BracketsConfig` or change `fsm_manage.py:1261` to check for the presence of `sl` and `tp` configs.
- **Risk**: HIGH — positions accumulate unprotected losses.

**P0-2. MagicMock leak into production adapter**
- 10 ORDER_REJECTED with `'>' NOT SUPPORTED BETWEEN INSTANCES OF 'MAGICMOCK' AND 'INT'`
- **Impact**: Legitimate orders rejected due to test mock object in production comparison path.
- **Fix scope**: Unknown — need to trace the exact injection path in the adapter layer.
- **Risk**: MEDIUM — only appeared on Apr 10, 0 on Apr 11 (possibly timing-related).

**P1-3. FLIP_GATE_UNKNOWN — session-wide signal suppression**
- 130 legitimate trading signals rejected because flip state tracker is uninitialized.
- **Impact**: Blocks direction changes for all symbols, session-wide (not just cold-start).
- **Root cause**: Known DEF-005 (OrderIndex not restored on restart) + no initial flip state from portfolio REST.

**P1-4. REGIME_NOT_ALLOWLISTED — 18h aurora suppression**
- 621 blocks on Apr 11 for BTC/ETH/SOL. Aurora was effectively inactive for 18 of 20 hours.
- **Assessment**: The gating mechanism is working correctly — aurora's allowlist excludes LOW_VOLATILITY and MEAN_REVERSION. But this means aurora trades only in brief TREND_UP windows. This may be by design, but the 90% suppression rate should be reviewed against strategy intent.

**P1-5. Sidecar is the de facto close mechanism, not brackets**
- Position Policy Sidecar in "shadow" mode produced 99.4% of trade_lifecycle records and executed all 3 closes.
- With brackets broken, sidecar is the only risk control mechanism actually operating.
- This is accidental — sidecar should be monitoring, not primary risk management.

**P2-6. SOLUSDT and ETHUSDT truth stuck**
- SOLUSDT: bracket_truth_source=UNKNOWN across all startups and restore envelopes, never resolved.
- ETHUSDT: DEFERRED_PENDING_WAL with same order ID for 4+ days.
- These are dead-state artifacts that pollute truth assessment.

**P2-7. Schema validation regressions**
- `EVT:MARKET_TICK_RECEIVED`: negative scientific notation (`-6.10e-11`) rejected by schema pattern.
- `EVT:EXPOSURE_SUMMARY_UPDATED`: missing `exposure_summary` required field.
- Both are data freshness/correctness risks.

---

## 16. Recommended Next Exact Step

**Fix the BracketsConfig.enable P0 defect, then re-run a 24h session.**

### Rationale:
1. The BracketsConfig bug makes ALL other analysis unreliable — execution behavior, position lifecycle, close analysis, profitability, even Phase 5 restore truth (manage_phase=BRACKETS_PENDING is phantom state) are distorted by the absence of brackets.
2. The fix is a single-line change with high confidence: either add `enable: bool = Field()` to `BracketsConfig` or change `fsm_manage.py:1261` to `return bool(self._manage_cfg.brackets.sl and self._manage_cfg.brackets.tp)`.
3. After brackets are functional, a clean 24h run would produce meaningful execution lifecycle data that actually tests the Phase 5 truth model under real open/manage/close cycles.
4. **Phase 5 closure audit should NOT be re-run until**: (a) brackets work, (b) a restart occurs during a session with live positions so the degraded path is exercised, (c) unknown_truth_records are populated from a real degraded startup.

### Why NOT re-run Phase 5 closure audit now:
- No restart occurred → no degraded startup → unknown_truth_records never populated in production.
- manage_phase=BRACKETS_PENDING is phantom state (brackets never placed) → restore envelope is unreliable.
- Execution lifecycle is broken → truth model is built on broken lifecycle data.

### Why NOT jump to Phase 6:
- Phase 5 exit gate requires: "restart can restore working execution state without semantic guessing" — this is UNPROVEN.
- Phase 5 exit gate requires: "operator can explain exactly what was restored, what was reconstructed, and what remains unknown" — SOLUSDT is permanently unknown with no resolution path.
- No degraded-startup runtime proof exists from production conditions.

---

*End of forensic context pack.*
