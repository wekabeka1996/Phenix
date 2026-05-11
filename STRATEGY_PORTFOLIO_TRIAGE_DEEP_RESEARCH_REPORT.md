# STRATEGY_PORTFOLIO_TRIAGE_DEEP_RESEARCH_REPORT
**Audit Date:** 2026-05-09
**Mode:** Read-only deep research
**Scope:** Aurora, mean_reversion, md_amr, alpha_search shadow candidates
**Status:** COMPLETE

---

## EXECUTIVE VERDICT

**Primary:** Aurora — the only strategy with proven live gate activity, full symbol coverage, and a complete readiness contract. No evidence of other candidates matching its operational depth.

**Secondary:** md_amr on XRPUSDT — already assigned in strategies.yaml, config-valid, fail-closed gates present. BUT: the only direct economic evidence is negative (PF 0.65–0.68 on BNBUSDT, removed 2026-04-15 as loss-making). md_amr must remain in observation-only mode until replay proof of positive expectation on XRPUSDT is obtained.

**Mean reversion:** Effectively dormant. Its only enabled symbol (DOGEUSDT) was cut from strategies.yaml 2026-04-22. No activation without symbol re-assignment and economic proof.

**Alpha search models (mean_reversion, momentum, volatility, aurora_adapter):** Shadow/evaluation subsystem only. Not wired to any execution path. Score semantics are incompatible with live handler scores and cannot be compared.

**Recommendation: One secondary candidate — md_amr on XRPUSDT — in passive observation only.**

---

## SECTION 1: FACTS

F-01. strategies.yaml assigns symbols as follows:
  - ETHUSDT → aurora only (restored 2026-04-23, TREND_UP-only restriction)
  - SOLUSDT → aurora only
  - XRPUSDT → aurora (priority 1) + md_amr (priority 3)
  - BTCUSDT → aurora only
  - BNBUSDT → aurora only (md_amr removed 2026-04-15)
  - DOGEUSDT → no strategies assigned (fully cut 2026-04-22)
  - 1000PEPEUSDT → llm_microstructure (external intent, not self-signaling)

F-02. Arbitration mode is priority-based with a 1000ms window. Aurora (priority 1) always wins over md_amr (priority 3) within that window on XRPUSDT.

F-03. md_amr.yaml marks ETHUSDT and SOLUSDT as enabled=true, but strategies.yaml does NOT assign md_amr to those symbols. The arbitration gate checks strategies_registry assignments. This is a config split-brain: md_amr signals from ETHUSDT and SOLUSDT would be blocked at GATE 0 (arbitration_gate.py).

F-04. mean_reversion.yaml marks DOGEUSDT as enabled=true (bb_window=25). DOGEUSDT is not present in strategies.yaml assignments as of 2026-04-22. mean_reversion has zero active symbols.

F-05. md_amr was removed from BNBUSDT on 2026-04-15 after producing a profit factor of 0.65–0.68 (loss-making). This is the only direct economic performance evidence for md_amr.

F-06. Aurora order_log_v1.jsonl entry (2026-05-09 21:49): DECISION_INTENT_REJECTED on BTCUSDT, NRR-062, LOW_VOL_COST_FLOOR, regime=LOW_VOLATILITY(confidence=0.846). This confirms Aurora's gate stack is live and firing.

F-07. No md_amr signal events or mean_reversion signal events were found in the sampled log files. The logs (91 lines, order_log) contain only aurora/BTCUSDT reject events and portfolio state updates.

F-08. md_amr requires 96 bars of local history (DIR_COMPONENTS_REQUIRED_BARS) and 7200 seconds of mandatory live warmup (_MANDATORY_LIVE_WARMUP_SEC) before signaling.

F-09. Aurora requires regime readiness, microstructure context, and execution context. Aurora's readiness contract is enforced via fail-closed gates (from WARMUP_REGIME_SSOT_UNIFICATION, 2026-03-16).

F-10. mean_reversion only signals in FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, or MEAN_REVERSION regimes. Aurora's regime detector uses SMA (short=48, long=192) and ATR (period=14, sma=288). Current log shows LOW_VOLATILITY regime on BTCUSDT, which is the alias of FLAT_LOW — this is a mean_reversion-eligible regime, but mean_reversion has no active symbols.

F-11. Aurora's regime thresholds set UNCERTAIN to signal_threshold=99.0 (effectively blocked). All other regimes admit signals above 0.075–0.18.

F-12. alpha_search domain contains four shadow models (mean_reversion, momentum, volatility, aurora_adapter). These feed the Judge subsystem (chamber, verdict_synthesizer) and are not connected to CMD:OPEN or any live execution path.

F-13. md_amr YAML config fields max_hold_bars=16, scaleout_fraction=0.5, progress_tracking thresholds (early=0.25, partial=0.70, near_completion=1.0), and context_validity thresholds are all present and ordered. The handler references hold_edge_min (Package A runtime exit gate).

F-14. md_amr LLM gate is disabled (llm_gate: disabled). The dormant cognitive overlay fields are present in the Pydantic model (MDAMRLLMGateConfig) but inactive.

F-15. Aurora per-asset configs define regime_tpsl (pct_mult mode), trailing stops per asset, allowed_regimes per asset. ETHUSDT was restored to TREND_UP-only (2026-04-23).

F-16. The PROFIT_ROADMAP_CONTROL_PLAN v2.md identifies five main blockers: NNR/Policy Paralysis, Timer/Temporal Incoherence, Config SSOT Debt, Scoring Ownership Contamination, and Strategy Portfolio Frozen. This audit addresses blocker #5.

F-17. The aurora_adapter alpha model uses different signal weights than the live aurora handler (e.g., obi=0.15 in adapter vs 0.42 in live aurora quadratic kernel). These are not the same scoring system.

---

## SECTION 2: INFERENCES

I-01. md_amr's config split-brain (enabled=true in md_amr.yaml for ETHUSDT/SOLUSDT but not assigned in strategies.yaml) means md_amr has effectively one active slot: XRPUSDT. Not three.

I-02. The only live economic evidence for md_amr is the BNBUSDT PF 0.65–0.68 removal. This does not prove XRPUSDT would also lose money (different allowed_regimes: MEAN_REVERSION + TREND_DOWN vs BNBUSDT's presumably broader set), but it establishes a prior of economic risk without additional replay proof.

I-03. The absence of md_amr signal events in logs (sampled) is consistent with one or more of: (a) aurora winning all XRPUSDT slots within the 1000ms arbitration window, (b) md_amr not completing its 96-bar/7200s warmup within the current session, (c) regime conditions not matching XRPUSDT's md_amr allowed_regimes (MEAN_REVERSION, TREND_DOWN). This is not proof of a defect — it is expected behavior under current configuration.

I-04. Aurora's live rejection rate is non-zero (NRR-062 observed). This confirms the signal pipeline is active end-to-end. The rejection is economically appropriate: LOW_VOLATILITY with confidence 0.846 triggers cost-floor gate correctly.

I-05. Mean reversion's effective dormancy is intentional: DOGEUSDT was cut after economic underperformance evidence (Binance timeout -1007 + regime veto on DOGEUSDT TREND_UP/UNCERTAIN). Reactivation without a new assigned symbol and economic proof would be unsafe.

I-06. Alpha search models (mean_reversion, momentum, volatility) have incompatible score semantics with live handlers. The aurora_adapter deliberately uses different weights. These models serve evaluation/comparison purposes, not live signal generation.

I-07. md_amr's multi-timeframe weighting (d1=0.35, h1=0.30, m30=0.20, m15=0.15) introduces structural latency vs aurora's 5m bar-driven kernel. In fast-moving regimes, md_amr's d1 anchor may lag behind aurora's real-time microstructure signals.

I-08. md_amr's XRPUSDT allowed_regimes (MEAN_REVERSION, TREND_DOWN) are narrower than BNBUSDT's set was. This narrows exposure to the regimes where mean-reversion logic has theoretical edge. However, TREND_DOWN inclusion on XRPUSDT needs scrutiny — directional trending regimes are not canonical mean-reversion territory.

I-09. Aurora's per-asset complexity (weights, thresholds, trailing stops, regime multipliers all tuned per symbol) represents a calibration investment not replicated in mean_reversion or md_amr. This is an advantage for Aurora's signal quality but also a surface area for drift.

---

## SECTION 3: ASSUMPTIONS

A-01. The Explore agent's summary of strategies.yaml is accurate: md_amr is not assigned to ETHUSDT or SOLUSDT in strategies.yaml, only to XRPUSDT.

A-02. The strategies_registry assignment governs GATE 0 (arbitration_gate.py `dm._check_strategy_arbitration()`). md_amr signals for ETHUSDT/SOLUSDT would fail this gate.

A-03. The 91-line order_log_v1.jsonl sample is representative of recent runtime activity (not a truncated or corrupted file). Absence of md_amr events in the sample reflects current runtime state.

A-04. The MD_AMR_COGNITIVE_EVOLUTION_ROADMAP_v1.md was not found at the repo root; archival equivalents exist under docs/. The Package A/A.1 baseline is assumed to be the configuration visible in md_amr.yaml (max_hold_bars=16, progress_tracking thresholds, context_validity).

A-05. Alpha search models are not connected to any live execution path. Absence of a CMD wire is assumed based on the shadow_book, backtest_plugin, and ensemble structure found in the alpha_search directory.

---

## SECTION 4: UNKNOWNS

U-01. **md_amr XRPUSDT P&L**: No replay or live P&L data for md_amr on XRPUSDT. The BNBUSDT negative evidence may or may not transfer to XRPUSDT (different regimes, different instrument volatility profile).

U-02. **md_amr warmup completion**: Unknown whether md_amr on XRPUSDT has completed its 96-bar / 7200s warmup in the current runtime session. No log evidence confirms warmup_done=true for md_amr.

U-03. **Aurora P&L in hybrid mode**: No trade closure P&L data available from logs sampled. Only rejections and portfolio state events observed.

U-04. **md_amr hold_edge_min value**: The handler references hold_edge_min as a Package A runtime exit gate, but this field was not visible in the md_amr.yaml config excerpt. Unknown whether it is hardcoded in the handler or sourced from YAML.

U-05. **mean_reversion DOGEUSDT cut reason**: Logs/reports reference Binance timeout -1007 and regime veto on TREND_UP/UNCERTAIN as causal, but the decision to cut DOGEUSDT entirely (vs fix mean_reversion) is not documented in the files reviewed.

U-06. **aurora_adapter weight divergence justification**: The aurora_adapter uses obi=0.15 vs live aurora's obi=0.42. The rationale for this divergence (intentional evaluation reduction vs oversight) is unknown.

U-07. **Arbitration timing on XRPUSDT**: Unknown how often md_amr would actually win the arbitration window on XRPUSDT. If aurora fires on every CMD:PROCESS_STRATEGY cycle, md_amr may never win the window even when its signal is valid.

U-08. **INTENT_DEFERRED kernel defer audit**: From memory (P1 pending), aurora's INTENT_DEFERRED never triggers. Unknown impact on quadratic kernel statistics.

---

## SECTION 5: STRATEGY ASSIGNMENT MAP

| Symbol | Assigned Strategies | Priority Order | Arbitration | Aurora Enabled | md_amr Enabled | MR Enabled |
|--------|-------------------|---------------|-------------|---------------|----------------|-----------|
| ETHUSDT | aurora | aurora=1 | winner-take-all | yes (TREND_UP only) | config=yes / SSOT=no | no |
| SOLUSDT | aurora | aurora=1 | winner-take-all | yes | config=yes / SSOT=no | no |
| XRPUSDT | aurora, md_amr | aurora=1 > md_amr=3 | 1000ms priority | yes | yes (MEAN_REVERSION, TREND_DOWN) | no |
| BTCUSDT | aurora | aurora=1 | winner-take-all | yes | no | config=yes / disabled |
| BNBUSDT | aurora | aurora=1 | winner-take-all | yes | removed 2026-04-15 | no |
| DOGEUSDT | none | — | — | cut 2026-04-22 | disabled | config=yes / no SSOT slot |
| 1000PEPEUSDT | llm_microstructure | llm=4 | external intent | no | no | no |

**NOTE — Config Split-Brain on md_amr:** md_amr.yaml marks ETHUSDT and SOLUSDT as `enabled: true` but strategies.yaml does not assign md_amr to those symbols. The arbitration gate (GATE 0) enforces the strategies_registry as SSOT. md_amr is operationally active on XRPUSDT only.

---

## SECTION 6: STRATEGY-BY-STRATEGY READINESS TABLE

### 6.1 Aurora

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Config status | COMPLETE | aurora.yaml fully populated with per-asset weights, regime thresholds, TP/SL, trailing stops |
| Pydantic model | COMPLETE | AuroraStrategyConfig, RegimeTpSlConfig, per-asset validation, all validators present |
| Decision handler | ACTIVE | AuroraHandler + AuroraDecisionMixin + QuadraticScoringKernel, readiness contracts enforced |
| Runtime input requirements | Regime, microstructure ctx, execution ctx, portfolio state, FE pillars | All from shared domain caches |
| Allowed regimes | TREND_UP, TREND_DOWN, MEAN_REVERSION, LOW_VOLATILITY, HIGH_VOLATILITY; UNCERTAIN blocked (threshold=99.0) | Per-asset overrides in yaml |
| Score semantics | Directional quadratic kernel, range [-1,1], threshold ≥0.162 (per-asset overrides) | Not a probability; intent gate |
| Execution style | LIMIT+GTX, per-asset trailing/regime_tpsl, signal exit enabled | domains.yaml + aurora.yaml |
| Safety gates | Directional sanity, low-vol cost floor, danger zone shield, memory shield, context shield, holding period, objective engine | All fail-closed |
| Observed runtime activity | CONFIRMED: NRR-062 reject on BTCUSDT 2026-05-09 21:49; portfolio state cached (equity 2326.73 USDT, 2 positions) | order_log_v1.jsonl |
| Economic readiness | HIGHEST — full gate stack proven live; P&L unconfirmed but signal pipeline verified | Hybrid mode |

### 6.2 md_amr

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Config status | COMPLETE (XRPUSDT only via SSOT) | md_amr.yaml + strategies.yaml alignment on XRPUSDT |
| Pydantic model | COMPLETE | MDAMRStrategyConfig with setup/hold/validity quality models, Package A fields present |
| Decision handler | CODED, PARTIALLY ACTIVE | 96-bar cold start + 7200s mandatory warmup before signaling; unknown warmup state |
| Runtime input requirements | 15m bars (96 local), regime confidence, multi-TF bars (d1/h1/m30/m15), portfolio/exposure | Hydrates via REST on startup |
| Allowed regimes (XRPUSDT) | MEAN_REVERSION, TREND_DOWN | Narrower than ETHUSDT/SOLUSDT configs |
| Score semantics | conf_ratio [0,1]: composite of setup_quality + hold_quality + context_validity; threshold conf_min=0.22 | NOT comparable to aurora score |
| Execution style | LIMIT+GTX entry, MARKET exit, scaleout 50% at target, max_hold_bars=16 | md_amr.yaml |
| Safety gates | Cold-start gate, mandatory warmup, context validity (regime conf floor 0.35), concentration guard (max 2 entries), objective engine | Fail-closed |
| Observed runtime activity | NO signal events in sampled logs | Consistent with warmup not complete or aurora winning all XRPUSDT windows |
| Economic readiness | NEGATIVE PRIOR — BNBUSDT PF 0.65–0.68 (removed loss-making); XRPUSDT unproven | **Observation only** |

### 6.3 mean_reversion

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Config status | COMPLETE (but no active SSOT slots) | mean_reversion.yaml DOGEUSDT config present; strategies.yaml has no MR assignments |
| Pydantic model | COMPLETE | MeanReversion1mStrategyConfig with veto overlays (microstructure, squeeze-expansion, momentum-separation) |
| Decision handler | CODED, DORMANT | Handler exists but no CMD:PROCESS_STRATEGY would arrive for any symbol |
| Runtime input requirements | 1m bars, regime (FLAT_* only), BB/RSI/ATR features, TFI for microstructure veto | Lightweight vs Aurora |
| Allowed regimes | FLAT_LOW, FLAT_NORMAL, FLAT_HIGH, MEAN_REVERSION | Regime aliases map to LOW_VOLATILITY in detector |
| Score semantics | MRSignal: side (BUY/SELL/NONE) + stop/target prices; not a numeric score | Binary entry decision |
| Execution style | MARKET entry (no GTX), ATR-based stops, TP to midband | |
| Safety gates | Regime allowlist, liquidity gate (kappa), microstructure veto (TFI), directional bias (funding) | Fail-closed on regime/liquidity |
| Observed runtime activity | NONE — dormant | DOGEUSDT cut 2026-04-22 |
| Economic readiness | UNPROVEN / DORMANT — no active symbol, no P&L data, DOGEUSDT history mixed (timeout -1007 + regime veto) | **Do not activate** |

### 6.4 alpha_search Shadow Models (mean_reversion, momentum, volatility, aurora_adapter)

| Dimension | Status | Evidence |
|-----------|--------|----------|
| Operational path | SHADOW / EVALUATION | Judge subsystem only; no CMD:OPEN wire |
| Score semantics | [-1,1] directional scores; NOT compatible with live handler scores | Different weights, different architecture |
| Runtime activity | SHADOW only (shadow_book, ensemble, backtest_plugin) | Not in order_log or domain_decision_making.log |
| Economic readiness | UNPROVEN | No execution path, no P&L |
| Activation safety | DO NOT ACTIVATE | Would require new wiring, arbitration assignment, economic proof |

---

## SECTION 7: SCORE SEMANTICS COMPATIBILITY TABLE

| Strategy | Score Type | Range | Threshold to Act | Comparable To |
|----------|-----------|-------|-----------------|--------------|
| Aurora (live handler) | Quadratic directional kernel + shield multipliers | [-1, 1] raw; final score composite | 0.162 default (per-asset overrides) | **Incomparable to others** |
| md_amr (live handler) | conf_ratio: setup + hold + context_validity composite | [0, 1] | conf_min=0.22 (entry); 0.7 valid (context) | **Incomparable to aurora** |
| mean_reversion (live handler) | MRSignal: side enum + price levels | Binary (BUY/SELL/NONE) | entry_threshold=0.115 (%B position) | **Incomparable to aurora/md_amr** |
| alpha_search aurora_adapter | Adapted quadratic with different weights | [-1, 1] | N/A (evaluation only) | **NOT the live aurora score** |
| alpha_search mean_reversion | BB+RSI+SMA-dev+Stochastic composite | [-1, 1] | ±0.3 "strong signal" | **NOT the live MR handler score** |
| alpha_search momentum | Multi-TF momentum composite | [-1, 1] | N/A (evaluation only) | Not wired to any live handler |
| alpha_search volatility | ATR ratio + BB width + realized vol | [-1, 1] | N/A (evaluation only) | Not wired to any handler |

**Rule:** No cross-strategy score comparison is valid. Each score solves a different sub-problem and lives in a different value space.

---

## SECTION 8: ECONOMIC EVIDENCE SUMMARY

| Strategy | Positive Evidence | Negative Evidence | Verdict |
|----------|-----------------|-------------------|---------|
| Aurora | Live gate stack confirmed; pipeline end-to-end proven (rejects visible) | P&L not confirmed in hybrid mode | **Highest readiness** — proof of operation, not proof of profit |
| md_amr | Config-valid, fail-closed gates, Package A baseline present | PF 0.65–0.68 on BNBUSDT (loss-making, removed 2026-04-15) | **Negative prior** — must produce replay proof before any expansion |
| mean_reversion | Complete config, layered safety gates, FLAT-regime specialization is theoretically sound | DOGEUSDT cut (timeout -1007 + regime veto), zero active symbols | **Dormant** — no economic evidence in current runtime |
| alpha_search | Shadow evaluation framework architecturally complete | Not connected to execution | **Shadow only** — no economic evidence possible without wiring |

---

## SECTION 9: MD-AMR vs ROADMAP BASELINE CHECK

Checking md_amr.yaml and handler against Package A/A.1 baseline assumptions:

| Parameter | Roadmap Expectation | Current Config | Match |
|-----------|-------------------|---------------|-------|
| max_hold_bars | Finite hold cap (Package A) | 16 bars | ✓ |
| scaleout_fraction | 50% at target approach (Package A.1) | 0.5 | ✓ |
| scaleout_cost_model | Fee-aware exit | round_trip | ✓ |
| progress_tracking thresholds | Ordered: early < partial < near_completion | 0.25 < 0.70 < 1.0 | ✓ |
| context_validity.regime_confidence | floor < valid band | 0.35 (floor) / 0.60 (valid) | ✓ |
| context_validity.volatility_z | weakening < invalid band | 1.5 (weakening) / 3.0 (invalid) | ✓ |
| hold_edge_min | Package A runtime exit gate replaces hardcoded conf_min | Handler references it; YAML field not confirmed | UNKNOWN (U-04) |
| LLM gate | Dormant (cognitive overlay disabled) | llm_gate: disabled | ✓ |
| Concentration guard | Max simultaneous entries bounded | max_simultaneous_entries: 2 | ✓ |
| ETHUSDT/SOLUSDT assignment | In strategies.yaml for md_amr | Not assigned (split-brain) | ✗ MISMATCH |

**Baseline result:** Package A/A.1 config fields are present and correctly ordered. The critical mismatch is the ETHUSDT/SOLUSDT split-brain (md_amr.yaml=enabled vs strategies.yaml=not assigned).

---

## SECTION 10: STRATEGY READINESS CLASSIFICATION

| Strategy | Classification | Reason |
|----------|--------------|--------|
| Aurora | **Ready for live/hybrid observation** | Proven gate activity, full readiness contract, active on 5 symbols |
| md_amr (XRPUSDT) | **Config-valid, economically unproven, passive observation** | Active assignment, fail-closed gates, but negative economic prior from BNBUSDT; no XRPUSDT replay evidence |
| md_amr (ETHUSDT, SOLUSDT) | **Config-valid but SSOT-unassigned** | strategies.yaml does not assign md_amr here; arbitration gate would block; do not treat as active |
| mean_reversion | **Shadow only / dormant** | No active SSOT slots; DOGEUSDT cut; no economic evidence |
| alpha_search models | **Shadow/evaluation only** | No execution wire; score semantics incompatible with live handlers |
| llm_microstructure (1000PEPEUSDT) | **External intent path — separate audit required** | Hybrid_advisory mode; require_telemetry=true; not self-signaling; out of scope for this triage |

---

## SECTION 11: RECOMMENDED PRIMARY/SECONDARY FOCUS

### Primary: Aurora
- Rationale: Only strategy with confirmed live gate activity, complete readiness contract, full per-asset calibration, and broadest symbol coverage (5 symbols).
- Focus: Confirm P&L in hybrid mode. Investigate INTENT_DEFERRED never-trigger (U-08 / P1 pending). Monitor NRR breakdown by regime to identify which gates produce false-positive rejections.

### Secondary: md_amr on XRPUSDT (observation only)
- Rationale: The only strategy with a valid SSOT assignment alongside Aurora, complete Pydantic model, and Package A/A.1 baseline in config. Regime restriction (MEAN_REVERSION + TREND_DOWN on XRPUSDT) gives it a theoretically distinct niche from Aurora.
- Hard constraint: **Do NOT expand md_amr to additional symbols or increase concentration limit until XRPUSDT replay shows positive expectation.**
- Observation goal: Confirm warmup completion, confirm arbitration miss rate (how often aurora wins XRPUSDT within 1000ms), capture first md_amr signal events, compare exit outcomes vs SL/TP targets.

### Not Recommended for Activation:
- mean_reversion: No SSOT slot, no economic evidence, no symbol assigned.
- alpha_search models: Not execution-wired, incompatible score semantics.
- md_amr on ETHUSDT/SOLUSDT: strategies.yaml SSOT mismatch must be resolved first; activation without SSOT alignment is a split-brain risk.

---

## SECTION 12: ACTIVATION BLOCKERS

### Aurora (already active)
- AB-A-01: P&L confirmation gap — hybrid testnet execution means no real P&L until live mode. Requires explicit live-mode gate-opening decision.
- AB-A-02: INTENT_DEFERRED never fires — aurora's quadratic kernel defer path is unexercised. Unknown whether this is correct (very rare conditions) or a silent defect.
- AB-A-03: ETHUSDT TREND_UP-only restriction — limiting aurora's symbol utility on ETHUSDT.

### md_amr XRPUSDT (observation — not blocked from existing observation, blocked from expansion)
- AB-M-01: **No positive economic evidence** — BNBUSDT PF 0.65–0.68 is the only data point. XRPUSDT replay required before any signal is acted on beyond logging.
- AB-M-02: Warmup gate unknown state — 96-bar + 7200s warmup may not have completed in current runtime session.
- AB-M-03: Arbitration dominance by aurora — md_amr may never win the 1000ms window on XRPUSDT as long as aurora emits a valid signal.
- AB-M-04: TREND_DOWN inclusion on XRPUSDT allowed_regimes — mean-reversion in trending regime is theoretically questionable; needs regime co-occurrence analysis.
- AB-M-05: Config split-brain (ETHUSDT/SOLUSDT) — must be resolved (either align strategies.yaml or set enabled=false in md_amr.yaml) before any md_amr expansion.

### mean_reversion (blocked from activation)
- AB-R-01: No SSOT symbol assigned in strategies.yaml — cannot receive CMD:PROCESS_STRATEGY.
- AB-R-02: No positive economic evidence on any symbol.
- AB-R-03: DOGEUSDT cut decision not formally reversed.

### alpha_search (blocked permanently from this audit's scope)
- AB-AS-01: No execution wire exists.
- AB-AS-02: Score semantics incompatible with live arbitration.

---

## SECTION 13: MINIMAL PROOF PLAN

### Phase 1: Aurora P&L Baseline (prerequisite for everything)
1. Run hybrid mode for ≥7 days.
2. Collect: trades entered, closed, P&L per symbol, NRR breakdown by gate type.
3. Required outcome: At least 30 closed trades with profit factor ≥ 1.0 on ≥2 symbols.
4. Metric: `logs/domain_decision_making.log` + `logs/order_log_v1.jsonl` → trade lifecycle WAL.

### Phase 2: md_amr XRPUSDT Observation Window
1. Confirm md_amr warmup completion for XRPUSDT (check for `warmup_done=true` log event).
2. Collect md_amr signal events (EVT:STRATEGY_SIGNAL_PRODUCED where strategy=md_amr).
3. Track: arbitration miss rate (how often md_amr is blocked by aurora's priority), signal regime distribution (MEAN_REVERSION vs TREND_DOWN), signal conf_ratio distribution.
4. Required outcome: ≥10 md_amr signal observations with entry/exit lifecycle tracking.
5. Replay check: Run strategy_replay.py for XRPUSDT 90-day history under md_amr config. Minimum acceptable PF: 1.1 after fees (fee_bps=4.0 + slippage_buffer=2.0 = 6bps round-trip cost).

### Phase 3: md_amr XRPUSDT Economic Gate
- Gate condition: Phase 1 done (aurora baseline proven) AND Phase 2 shows PF ≥ 1.1 on XRPUSDT replay.
- Only then: evaluate whether to remove aurora's XRPUSDT arbitration priority for select regimes or expand md_amr to additional symbols.

### Phase 4 (deferred): mean_reversion re-evaluation
- Prerequisite: Phase 1 + Phase 2 complete.
- Requires: new symbol assignment in strategies.yaml, regime co-occurrence analysis for FLAT_* conditions, replay on at least one non-DOGE symbol (SOLUSDT or XRPUSDT FLAT_LOW history).
- Do not activate until Phase 4 complete.

---

## APPENDIX A: CONFIG SPLIT-BRAIN REGISTRY

| Split-Brain | File A | File B | Impact | Resolution |
|-------------|--------|--------|--------|-----------|
| md_amr ETHUSDT enabled vs not assigned | md_amr.yaml: enabled=true | strategies.yaml: no md_amr slot | Signals blocked at GATE 0 silently | Either assign in strategies.yaml OR set enabled=false in md_amr.yaml |
| md_amr SOLUSDT enabled vs not assigned | md_amr.yaml: enabled=true | strategies.yaml: no md_amr slot | Same as above | Same resolution |
| mean_reversion DOGEUSDT enabled vs DOGEUSDT cut | mean_reversion.yaml: DOGEUSDT enabled=true | strategies.yaml: DOGEUSDT fully cut | Signals blocked at GATE 0 silently | Set enabled=false in mean_reversion.yaml |

---

## APPENDIX B: TIMER / GATE DENSITY (Aurora, relevant to Phase 1)

| Gate / Timer | Value | Effect |
|-------------|-------|--------|
| signal_threshold (default) | 0.162 | Signal admission |
| cooldown_sec (aurora) | 6s | Min gap between aurora signals per symbol |
| side_bias window | 420s | Long/short balance enforcement |
| holding_period min_duration | 900s | Prevents early exit signals |
| reentry_cooldown_sec | 300s (per asset) | Post-exit lockout |
| LOW_VOL_COST_FLOOR gate | enforced in testnet/hybrid | Rejects when spread+fee > min_tp coverage |
| exposure_block_cooldown_sec | 60s | After exposure block, locks symbol |
| symbol_cooldown_sec | 3s | Inter-signal minimum |
| max_intents_per_minute_per_symbol | 20 | QoS rate cap |
| directional_sanity hard_veto_consecutive_bars | 2 | Consecutive adverse bar veto |
| UNCERTAIN regime threshold | 99.0 | Effective signal blackout |

*These timers interact multiplicatively. A signal arriving after a 6s cooldown but during a 300s reentry_cooldown will be rejected. Timer coherence audit (PROFIT_ROADMAP blocker #2) remains open.*

---

*Report generated: 2026-05-09. Read-only audit. No config changes made.*
