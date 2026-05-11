# FEATURE_REGIME_INPUT_INTEGRITY_DEEP_RESEARCH_REPORT

## Executive verdict

Input integrity is partially preserved for the sampled Aurora deny flow. Producer layers emit explicit readiness, timeframe, bar-close, and regime provenance contracts, and the sampled low-vol reject trace retains enough economics context to explain why trade intent was denied. The main integrity seam is later: Feature Engineering emits top-level price_motion into CMD:PROCESS_STRATEGY, but the typed ProcessStrategy boundary does not promote additive fields such as price_motion, Aurora scoring only reads features.price_motion or the cached FEATURES copy, and thinner observability planes collapse detail. Based on sampled evidence, this is a Runtime plus Observability Gap, not a proven capital-loss defect in the deny path.

## FACTS

- SSOT scope for this audit is anchored to [Copilot_Master_Roadmap.md](Copilot_Master_Roadmap.md) and the report schema in [docs/ai/AGENT_REPORT_SCHEMA.md](docs/ai/AGENT_REPORT_SCHEMA.md).
- The canonical runtime readiness contract defines explicit states and scopes, including basis_bar_ready, regime_ready, microstructure_ready, strategy_ready_per_symbol, and trading_ready in [apps/reference/contracts/runtime_readiness.py](apps/reference/contracts/runtime_readiness.py#L16-L31).
- Feature Engineering explicitly tracks warmup.full_ready and warmup.reasons and documents that DecisionMaking should block until full_ready in [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L1750) and [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L1825).
- Feature Engineering emits top-level price_motion in both the FEATURES payload and the CMD:PROCESS_STRATEGY payload in [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2051), [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2295), [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2304), and [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2307).
- Regime Detector only consumes basis timeframe feature events, fail-closes stale input to UNCERTAIN, and emits basis_tf_sec, bar_close_ts_ms, and warmup metadata in [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L360), [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L415), [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L437), [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L456), and [apps/reference/domains/regime_detector/regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L464).
- DecisionMaking warmup and freshness gates explicitly check warmup and bar-aware TTL semantics in [apps/reference/domains/decision_making/gates/readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py#L151), [apps/reference/domains/decision_making/gates/readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py#L310), and [apps/reference/domains/decision_making/gates/readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py#L357). The configured feature TTL is 30 seconds in [config/aurora/domains.yaml](config/aurora/domains.yaml#L33).
- The typed boundary intentionally keeps additive fields out of first-class ProcessStrategyCmd fields. ProcessStrategyBoundary documents that diagnostics, price_motion, and regime snapshot flow through raw in [apps/reference/domains/decision_making/contracts/boundary_models.py](apps/reference/domains/decision_making/contracts/boundary_models.py#L45) and [apps/reference/domains/decision_making/contracts/boundary_models.py](apps/reference/domains/decision_making/contracts/boundary_models.py#L50). The mapper only promotes features, warmup, and raw in [apps/reference/domains/decision_making/contracts/boundary_mappers.py](apps/reference/domains/decision_making/contracts/boundary_mappers.py#L75) and [apps/reference/domains/decision_making/contracts/boundary_mappers.py](apps/reference/domains/decision_making/contracts/boundary_mappers.py#L101-L103). ProcessStrategyCmd itself has no typed price_motion field in [apps/reference/domains/decision_making/contracts/core_models.py](apps/reference/domains/decision_making/contracts/core_models.py#L56) and [apps/reference/domains/decision_making/contracts/core_models.py](apps/reference/domains/decision_making/contracts/core_models.py#L87).
- Aurora still documents the seam as if CMD omitted price_motion, caches the FEATURES copy, and scoring reads features.price_motion first, then cached_price_motion, in [apps/reference/domains/strategies/runtimes/aurora/handler.py](apps/reference/domains/strategies/runtimes/aurora/handler.py#L155), [apps/reference/domains/strategies/runtimes/aurora/handler.py](apps/reference/domains/strategies/runtimes/aurora/handler.py#L933-L935), [apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py](apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py#L34-L45). Aurora does read cmd.raw for bar identity and regime reconstruction, but the observed reads are bar/regime oriented rather than price_motion promotion in [apps/reference/domains/strategies/runtimes/aurora/handler.py](apps/reference/domains/strategies/runtimes/aurora/handler.py#L887-L889), [apps/reference/domains/strategies/runtimes/aurora/decision.py](apps/reference/domains/strategies/runtimes/aurora/decision.py#L455), [apps/reference/domains/strategies/runtimes/aurora/decision.py](apps/reference/domains/strategies/runtimes/aurora/decision.py#L469-L470), and [apps/reference/domains/strategies/runtimes/aurora/decision.py](apps/reference/domains/strategies/runtimes/aurora/decision.py#L670-L685).
- The low-vol trace enrichment path in DecisionMaking explicitly enriches price_motion_context from signal-gate fields and persists missing-input bookkeeping in [apps/reference/domains/decision_making/core/facade.py](apps/reference/domains/decision_making/core/facade.py#L442), [apps/reference/domains/decision_making/core/facade.py](apps/reference/domains/decision_making/core/facade.py#L500-L523), and [apps/reference/domains/decision_making/core/facade.py](apps/reference/domains/decision_making/core/facade.py#L538-L539).
- Runtime feature logs prove live feature availability for macro_resid, macro_sync, spread_bps, liquidity_kappa, and absorption in [logs/features/BNBUSDT.log](logs/features/BNBUSDT.log#L1).
- The sampled recorder row preserves many feat_* columns and regime join fields, but only collapses price-motion output to pm_norm and pm_raw in [data/recorder/2026-05-09/BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1).
- The regime confidence audit provides heartbeat-level regime evidence and direct decision linkage, including threshold verdict PASS and deny reason NRR-062, in [logs/regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L3-L4) and [logs/regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L19).
- The sampled order log retains a rich low_vol_cost_floor object including missing_inputs, price_motion_context, liquidity_context, economics_context, regime provenance, and persistence_context in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L1).
- The sampled shadow journal keeps only thin payload fragments for QUADRATIC_DECISION_TRACE, TRADE_INTENT_REJECTED, and DECISION_TRACE_EMITTED compared with the order log in [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L104-L108).
- There is a config-level asymmetry around macro_sync: trading market-data config disables anchor_update_from_ticks in [config/aurora/trading.yaml](config/aurora/trading.yaml#L76), while Aurora strategy config still carries macro_resid and macro_sync in signal weights and essential features in [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L198-L199) and [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L284-L287).

## INFERENCES

- The primary price_motion integrity seam is not FE producer emission. It is the typed boundary plus Aurora consumer access pattern: price_motion survives in raw transport payload, but not as a first-class ProcessStrategyCmd field, and Aurora scoring does not appear to rehydrate it from cmd.raw.
- The stale comment in Aurora handler and scoring helpers reflects contract drift. Code comments still describe FE CMD omission, but the producer code now emits price_motion top-level.
- Sampled deny-path economics are not fully lost downstream. The order logger still carries enough low-vol context to explain the deny decision, so the sampled low_vol_cost_floor path remains forensically legible even after typed boundary narrowing.
- Observability fidelity is tiered rather than uniform. The order log is the richest downstream proof surface, the recorder is a middle layer with normalized feature and regime columns, and the shadow journal is intentionally summary-grade.
- The sampled null values for ret_60s and ret_300s in the deny trace look like runtime missingness rather than a simple logging-only drop, because nearby liquidity and regime fields are present in the same payload.

## ASSUMPTIONS

- The sampled 2026-05-09 Aurora deny events are representative of the currently deployed deny path for low-vol blocking.
- The recorder schema sampled in [data/recorder/2026-05-09/BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1) is the active recorder surface for this runtime and not a stale migration artifact.
- No hidden Aurora consumer outside the searched runtime files rehydrates cmd.raw.price_motion before kernel scoring.

## UNKNOWNS

- The audit does not yet prove whether accepted TRADE_INTENT and execution paths preserve the same economics and price-motion context as the sampled deny path.
- The audit does not yet prove whether any Aurora branch outside the searched handler, decision, and scoring helper files reads cmd.raw.price_motion indirectly.
- The audit does not yet prove end-to-end integrity for non-Aurora strategies.
- The audit does not yet prove whether the macro_sync anchor_update_from_ticks asymmetry materially changes live macro feature freshness, only that the contract surfaces are not perfectly aligned.

## Feature availability matrix

| Input surface | FE producer emit | Typed CMD plus Aurora runtime | Deny trace and order log | Recorder and shadow surfaces |
| --- | --- | --- | --- | --- |
| Warmup full_ready and reasons | Full in [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L1750) and [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L1824-L1825) | Full typed warmup in [boundary_mappers.py](apps/reference/domains/decision_making/contracts/boundary_mappers.py#L101-L103) | Not explicit in sampled order-log payload | Recorder keeps ready and not_ready_reasons in [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1); shadow fragment omits it in [shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L104-L108) |
| price_motion block | Full top-level emit in [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2051) and [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2307) | Raw only at boundary; no typed field in [core_models.py](apps/reference/domains/decision_making/contracts/core_models.py#L56-L87); Aurora scoring reads features or cache in [scoring_helpers.py](apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py#L38-L45) | Subset preserved as price_motion_context in [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) | Recorder collapses to pm_norm and pm_raw in [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1); shadow fragment omits it in [shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L104-L108) |
| spread_bps, liquidity_kappa, absorption | Present in live FE proof in [BNBUSDT.log](logs/features/BNBUSDT.log#L1) | Present via features mapping; not separately promoted | Preserved as liquidity_context in [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) | Recorder keeps feat_absorption, feat_liquidity_kappa, feat_spread_bps in [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1); shadow fragment omits them |
| macro_resid and macro_sync | Present in live FE proof in [BNBUSDT.log](logs/features/BNBUSDT.log#L1) | Present in features dict; no separate downstream trace field was sampled | Not visible in sampled deny trace payload | Recorder keeps feat_macro_resid and feat_macro_sync in [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1); shadow fragment omits them |
| bar identity, tf_sec, bar_close_ts | Full contract via FE and runtime identity extraction in [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2295-L2307) and [aurora/handler.py](apps/reference/domains/strategies/runtimes/aurora/handler.py#L887-L889) | Preserved and used for identity reconstruction in [aurora/decision.py](apps/reference/domains/strategies/runtimes/aurora/decision.py#L455-L463) | Preserved as features_ts_ms and detector_event bar_close_ts_ms in [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) | Recorder keeps tf_sec and timestamp in [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1); shadow fragment reduces this to ts_ms |

Legend: Full means directly present and explicitly structured. Raw only means present only inside the raw transport payload, not as a typed first-class field. Subset means only selected fields survive.

## Regime integrity matrix

| Regime property | Producer contract | Decision and gate usage | Runtime proof surface | Thin proof surface |
| --- | --- | --- | --- | --- |
| basis timeframe ownership | RD basis-only contract in [regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L360) and [regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L464-L466) | Decision uses detector-event basis_tf_sec and bar_close_ts_ms in [regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L4) | Order log retains detector_event and structural regime reference in [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) | Shadow fragment only keeps regime and regime_confidence in [shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L108) |
| stale-data fail-closed behavior | RD emits UNCERTAIN on stale input in [regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L415-L421) and [regime_detector.py](apps/reference/domains/regime_detector/regime_detector.py#L437-L486) | Decision warmup and freshness gates remain explicit in [readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py#L151-L209) and [readiness_gates.py](apps/reference/domains/decision_making/gates/readiness_gates.py#L310-L379) | Recorder retains regime_warmup_full_ready and regime_warmup_reasons columns in [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1) | Shadow fragment omits warmup state |
| regime confidence and thresholding | RD heartbeat emits confidence and provenance in [regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L3) | Decision audit records threshold PASS and deny reason NRR-062 in [regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L4) and [regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L19) | Order log preserves regime_confidence and threshold metadata in [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) | Shadow fragment keeps regime_confidence but not the full threshold object in [shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L108) |
| regime provenance | Structured provenance contract present in runtime trace and order log | Decision trace preserves detector cache provenance in [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) | Rich in order log and decision trace | Summary only in shadow payload fragment |

## Boundary field-loss map

| Transition | Observed behavior | Operational effect | Evidence |
| --- | --- | --- | --- |
| FE internal state to FE logs | Feature values are logged, but the feature log line is value-only rather than full event envelope | Good proof of feature calculation, weak proof of readiness and price-motion envelope | [logs/features/BNBUSDT.log](logs/features/BNBUSDT.log#L1) |
| FE CMD emit to typed ProcessStrategy boundary | FE emits regime and price_motion top-level, but the typed boundary promotes only symbol, tf_sec, bar_close_ts, features, warmup, and raw | Additive fields survive only in raw unless a consumer explicitly rehydrates them | [feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L2295-L2307), [boundary_models.py](apps/reference/domains/decision_making/contracts/boundary_models.py#L50), [boundary_mappers.py](apps/reference/domains/decision_making/contracts/boundary_mappers.py#L101-L103), [core_models.py](apps/reference/domains/decision_making/contracts/core_models.py#L56-L87) |
| ProcessStrategyCmd to Aurora scoring | Aurora scoring helper checks features.price_motion and cached FEATURES copy; observed raw reads focus on bar identity and regime reconstruction, not price_motion promotion | Possible silent under-consumption of producer-emitted price_motion when cache is unavailable or out of sync | [handler.py](apps/reference/domains/strategies/runtimes/aurora/handler.py#L155), [handler.py](apps/reference/domains/strategies/runtimes/aurora/handler.py#L933-L935), [scoring_helpers.py](apps/reference/domains/strategies/runtimes/aurora/scoring_helpers.py#L38-L45), [decision.py](apps/reference/domains/strategies/runtimes/aurora/decision.py#L455-L470) |
| Decision trace enrichment to order log | Low-vol enrichment rebuilds price_motion_context and persists liquidity and economics context into the reject trace | Deny-path postmortem remains rich enough to explain low-vol blocking | [facade.py](apps/reference/domains/decision_making/core/facade.py#L442-L523), [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1) |
| Order log to shadow journal | Shadow journal stores summary payload fragments instead of the rich decision object | Shadow-only forensics cannot prove feature/economics integrity end to end | [order_log_v1.jsonl](logs/order_log_v1.jsonl#L1), [shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L104-L108) |
| Runtime trace to recorder CSV | Recorder keeps feat_* values and regime join metadata, but price-motion is normalized down to pm_norm and pm_raw | Recorder is useful for longitudinal analysis, but insufficient for full price-motion block forensics | [BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1) |

## Runtime proof / missing proof

### Runtime proof

- Live FE feature proof exists for macro_resid, macro_sync, spread_bps, liquidity_kappa, and absorption in [logs/features/BNBUSDT.log](logs/features/BNBUSDT.log#L1).
- Live regime heartbeat proof exists with basis_tf_sec, bar_close_ts_ms, structural_regime_ref, and stable confidence in [logs/regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L3).
- Live decision linkage proof exists with threshold PASS and low_vol_cost_floor_blocked deny in [logs/regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L4) and [logs/regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L19).
- Live deny-path economics proof exists in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L1), including price_motion_context, liquidity_context, thresholds, economics_context, and persistence_context.
- Live recorder proof exists for feature and regime column survival in [data/recorder/2026-05-09/BNBUSDT_300.csv](data/recorder/2026-05-09/BNBUSDT_300.csv#L1).

### Missing proof

- No sampled accepted TRADE_INTENT or execution-path payload was inspected in this audit.
- No sampled runtime artifact proves that Aurora kernel scoring directly consumes cmd.raw.price_motion.
- No thin journal artifact preserves the rich low-vol cost-floor payload at the same fidelity as the order log.

## Profit-impact findings

- The sampled deny flow still blocked low-confidence low-vol entries with adequate regime and economics context, which argues against an immediate capital-protection failure in the observed path.
- The main profit-risk vector is silent scoring drift before deny/trace persistence: if Aurora depends on cached FEATURES price_motion instead of the producer-emitted CMD payload, restart timing or ordering mismatches could make volatility-aware gating or scoring less faithful than the producer contract suggests.
- The main operational risk is forensic blindness rather than direct fill corruption. Operators need the order log and regime audit together; the shadow journal alone is too thin to explain why a trade was accepted or rejected from full feature context.

## Minimal next validation

1. Sample at least one accepted Aurora decision and verify whether TRADE_INTENT_PROPOSED, order, and execution surfaces retain the same price-motion and liquidity context seen in deny-path order logs.
2. Add a narrow audit check that compares FE CMD payload fields against the typed ProcessStrategyCmd fields plus raw payload for price_motion, regime, bar identity, and warmup.
3. If code changes become allowed later, either promote price_motion from cmd.raw into the Aurora consumer contract or update the stale CMD omission comments so operators do not reason from outdated code comments.

## AGENT_REPORT_V1

### Executive Summary

- Sampled Aurora deny-path feature and regime integrity is mostly intact, but one typed-boundary seam and two observability collapses remain material.

### Proven Facts

- FE emits explicit warmup metadata and top-level price_motion into CMD payloads.
- RD emits basis-bar regime heartbeat with provenance and fail-closes stale input to UNCERTAIN.
- ProcessStrategyCmd does not expose price_motion as a typed field.
- Aurora scoring reads features.price_motion or cached FEATURES state, not an observed cmd.raw price_motion rehydration path.
- Order-log reject traces preserve rich low-vol cost-floor context; shadow journal fragments do not.

### Inferred Findings

- The true price_motion seam is later than FE emit: typed boundary narrowing plus Aurora consumer access.
- Deny-path safety evidence is stronger than shadow-journal evidence; operators should treat order log as the authoritative downstream forensic surface.

### Contradictions / Evidence Gaps

- Aurora comments still say CMD omits price_motion, while FE producer code now emits it.
- Accepted trade paths were not sampled, so deny-path integrity cannot be generalized to fills or closures.

### Root Cause Candidates

- Intentional additive-only boundary design that preserves extras only in raw.
- Aurora consumer logic that did not evolve after FE started emitting price_motion in CMD.
- Intentional observability compression in recorder and shadow-journal surfaces.

### Operational Risk

- Runtime
- Observability Gap

### Files / Areas Touched

- Report only: [FEATURE_REGIME_INPUT_INTEGRITY_DEEP_RESEARCH_REPORT.md](FEATURE_REGIME_INPUT_INTEGRITY_DEEP_RESEARCH_REPORT.md)
- Read-only analysis across FE, RD, DecisionMaking contracts, Aurora runtime, config, and runtime logs.

### Validation Performed

- Cross-checked producer, boundary, consumer, and runtime-artifact surfaces.
- Verified sampled runtime deny traces in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L1), [logs/regime_confidence_audit_v1.jsonl](logs/regime_confidence_audit_v1.jsonl#L4), and [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl#L104-L108).

### Residual Risk

- Accepted-path persistence and execution-path integrity remain unproven.
- Aurora pre-trace scoring may still rely on cache timing for price_motion fidelity.

### What Remains Unproven

- End-to-end accepted trade flow.
- Non-Aurora strategies.
- Whether macro_sync contract asymmetry causes measurable freshness drift at runtime.

### Minimal Safe Verdict

- Safe conclusion: sampled deny-path safety evidence is adequate, but the producer-to-consumer price_motion contract is semantically drifted and the thin observability planes are insufficient for standalone audits.
