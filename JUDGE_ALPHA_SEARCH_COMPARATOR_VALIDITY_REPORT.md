# JUDGE_ALPHA_SEARCH_COMPARATOR_VALIDITY_REPORT

Read-only audit of whether `alpha_search` and the LLM Judge stack can be used as a shadow comparator, calibration assistant, and strategy/gate evidence engine without becoming execution authority or contaminating live scoring.

## Executive Verdict

`alpha_search` plus the Judge stack are safe to use as a shadow comparator and offline evidence engine only. They are not safe as execution authority, and they must not own live scoring or open/close decisions.

The current implementation is shadow-gated in config and code, but the main residual risks are join incompleteness and a config-level source path in Aurora that could be wired into live scoring later if someone changed the wiring outside the audited path.

## FACTS

- `config/alpha_search.yaml` enables `alpha_search`, sets `shadow_mode: true`, uses the `EVT:FEATURES_CALCULATED -> EVT:TA_FEATURES_CALCULATED -> CMD:PROCESS_STRATEGY -> EVT:ALPHA_SCORE_CALCULATED` bridge, enables providers `aurora`, `ta_ensemble`, `judge_sw`, and `judge_fn`, sets thresholds `0.155`, `0.18`, and `0.162`, enables the virtual trader and objective feedback, and leaves `simulator_shutdown_export` disabled by default (`config/alpha_search.yaml:13-306`).
- `apps/reference/domains/alpha_search/runtime/config_resolver.py` force-sets standalone `alpha_search` into `enabled=true` and `shadow_mode=true`, so the runtime posture is shadow-only even if the config surface drifts (`runtime/config_resolver.py:228-245`).
- `apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py` is the only file that interacts with `main.py`; it mirrors `EVT:FEATURES_CALCULATED` and `EVT:REGIME_DETECTED` into `alpha_input_v1.jsonl` for standalone shadow replay (`runtime/feature_mirror_writer.py:72-170`).
- `apps/reference/domains/alpha_search/runtime/ingest.py`, `runtime/scenario_worker.py`, and `runtime/scenario_manager.py` form an isolated shadow pipeline: replay/live-tail ingest -> isolated `LocalBus` worker -> plugin scoring -> per-scenario shadow book -> aggregate reporter (`runtime/ingest.py:5-170`, `runtime/scenario_worker.py:5-223`, `runtime/scenario_manager.py:70-157`, `runtime/reporting.py:30-79`, `runtime/shadow_book.py:36-123`).
- `apps/reference/domains/alpha_search/backtest_plugin.py` listens to feature, TA, decision, trade, and objective events; judge-expert providers use a dedicated shadow path, do not emit `EVT:ALPHA_SCORE_CALCULATED`, and the chamber/verdict/policy cortex emissions are explicitly shadow-only (`backtest_plugin.py:312-339, 572-730, 1020-1440, 1461-1965`).
- `apps/reference/domains/alpha_search/judge/config_models.py` only admits `off` and `shadow` in runtime validation; `VerdictConfig` is constrained by chamber enablement, and `JudgeVerdict` must have `applied=false` in `off` or `shadow` modes (`judge/config_models.py:240-409`).
- `apps/reference/domains/alpha_search/judge/contracts.py` defines canonical `cycle_key` identity and enforces exact XOR verdict typing, shadow-only posture for verdicts, and shadow-only posture for shadow entry plans (`judge/contracts.py:8-16, 149-188, 206-337, 344-534`).
- `apps/reference/domains/alpha_search/judge/policy_cortex/*` is shadow-only throughout: the registry fail-closes on unknown surfaces, the classifier hardcodes `authority_mode="shadow"` with `applied=false`, and the evaluator emits shadow annotations only (`judge/policy_cortex/surface_registry.py:1-181`, `judge/policy_cortex/policy_classifier.py:1-172`, `judge/policy_cortex/cortex_evaluator.py:1-203`, `judge/policy_cortex/evidence_models.py:1-195`, `judge/policy_cortex/surface_key_builder.py:1-86`).
- `apps/reference/domains/alpha_search/judge/shadow_entry_plan.py` and `judge/shadow_simulator.py` are telemetry/offline tools only; the entry-plan model enforces `authority_mode="shadow"`, `applied=false`, and `shadow_only=true`, while the simulator replays plans against historical bars for forensic PnL only (`judge/shadow_entry_plan.py:1-192`, `judge/shadow_simulator.py:1-251`).
- `apps/reference/domains/alpha_search/judge/review/*` and `judge/simulator/*` are offline-only and rely on exact joins. The review engine joins verdicts to chambers/envelopes and outcomes by exact cycle identity and explicit fallback IDs, while the simulator correlates verdicts to outcomes by exact `(strategy_id, symbol, tf_sec, bar_close_ts)` keys (`judge/review/loaders.py:1-249`, `judge/review/engine.py:408-1455`, `judge/simulator/simulator_engine.py:1-760`, `judge/simulator/disagreement_analyzer.py:1-177`, `judge/simulator/expert_accuracy_reporter.py:1-115`, `judge/simulator/calibration_dataset_writer.py:1-260`, `judge/simulator/summary_report_writer.py:1-220`).
- `config/judge_review.yaml` and `config/judge_simulator.yaml` are both disabled by default, so the review/simulator stack is present but not active by config default (`config/judge_review.yaml:1-15`, `config/judge_simulator.yaml:1-8`).
- `config/aurora/domains.yaml` still allows `judge_confidence` as a directional confidence source and sets `neocortex_enforcement_mode: shadow`, which is a potential contamination seam at the config layer even though current `alpha_search` code does not prove any live wiring for it (`config/aurora/domains.yaml:118-145, 594-596`).
- `logs/judge_experts/judge.signal_weights_v1_BTCUSDT_2026-05-09.jsonl:1`, `chamber_BTCUSDT_2026-05-09.jsonl:1`, `envelope_BTCUSDT_2026-05-09.jsonl:1`, `verdict_BTCUSDT_2026-05-09.jsonl:1`, `policy_cortex_BTCUSDT_2026-05-09.jsonl:1`, and `shadow_entry_plan_BTCUSDT_2026-05-09.jsonl:1` show a canonical chain with the same `cycle_key`; the verdict and policy cortex outputs are shadow-only, and the observed BTCUSDT policy-cortex surface was classified `UNKNOWN` because the surface key was not present in the registry.
- `logs/order_log_v1.jsonl:1` shows a live decision trace with `rid` present but `decision_id` and `cycle_key` null in the provenance context, and `judge_confidence`, `strategy_confidence`, and `model_confidence` null in the score context.
- `logs/shadow_critical_event_journal_v1.jsonl:1` is a generic portfolio event with `rid` but no judge-specific payload, which means the shared shadow journal does not by itself close the judge join.
- `apps/reference/domains/alpha_search/judge/review/engine.py` states that incumbent-only baseline evidence is unavailable in the current repo-supported inputs, while chamber-only and final-judge comparisons are reconstructable when chamber artifacts exist (`judge/review/engine.py:1064-1455`).

## INFERENCES

- Because the runtime posture is shadow-only and the Judge verdict path keeps `authority_mode="shadow"` with `applied=false`, the stack is suitable as a shadow comparator and evidence engine, but not as execution authority.
- Because the review and simulator layers require exact cycle keys and exact outcome joins, structural comparisons are reliable on their own, but economic claims require the outcome join.
- Because the policy-cortex registry can return `UNKNOWN` for a real BTCUSDT surface, policy-cortex output should be treated as fail-closed surface evidence, not as universal proof of policy quality.
- Because the live order trace does not currently carry `decision_id` or `cycle_key`, live-to-judge correlation is incomplete and should not be inferred from symbol or timestamp alone.
- Because Aurora config allows `judge_confidence` as a source but the audited `alpha_search` code does not emit it, contamination risk is a wiring risk, not a proven current runtime path.

## ASSUMPTIONS

- The sampled log lines are representative of the current runtime shape, but they are not exhaustive of all historical behavior.
- "P0 profit work" means offline calibration, gating, and strategy-ranking work, not live trading changes.
- External outcome data is assumed trustworthy if it passes schema validation.
- No non-`alpha_search` subscriber was found in the audited path that consumes judge shadow events into live execution.

## UNKNOWNS

- Whether any downstream module outside the audited `alpha_search` tree subscribes to judge shadow events in a way that affects live scoring.
- Whether `judge_confidence` is used elsewhere in Aurora outside the audited config surfaces.
- Whether policy-cortex registry coverage is complete across all symbol/regime/timeframe surfaces.
- Whether the current outcome dataset covers enough matched cycles to generalize all comparator claims.

## Alpha_search Runtime Map

| Component | Observed setting | Why it matters | Source |
| --- | --- | --- | --- |
| Shadow posture | `enabled=true`, `shadow_mode=true`; standalone resolver forces both true | The runtime is shadow-only even if the config surface drifts | `config/alpha_search.yaml:13-306`, `runtime/config_resolver.py:228-245` |
| Event bridge | `EVT:FEATURES_CALCULATED`, `EVT:TA_FEATURES_CALCULATED`, `CMD:PROCESS_STRATEGY`, `EVT:ALPHA_SCORE_CALCULATED` | Features are cached first, then decision scoring is triggered | `config/alpha_search.yaml:20-24`, `backtest_plugin.py:312-339, 572-730` |
| Cache | `max_per_symbol=10`, `require_same_bar_close_ts=false` | Fuzzy matching is allowed, which reduces misses but weakens exactness | `config/alpha_search.yaml:26-29`, `backtest_plugin.py:593-630` |
| Providers | `aurora=0.155`, `ta_ensemble=0.18`, `judge_sw=0.162`, `judge_fn=0.162` | Mixed provider surface; judge providers are aligned to the Judge threshold | `config/alpha_search.yaml:34-140` |
| Virtual trader | `enabled=true`, `per_provider=true`, `notional_size=5000`, `max_bars=12`, `max_hold_sec=1800`, `max_drawdown_exit=1.2`, `cooldown_bars_after_close=3` | Shadow PnL is tracked internally only | `config/alpha_search.yaml:145-155`, `backtest_plugin.py:1504-1705` |
| Objective feedback | `enabled=true` | Closed virtual trades can feed provider learning, but only inside the shadow stack | `config/alpha_search.yaml:157-167`, `backtest_plugin.py:1628-1776` |
| Ingest path | FeatureMirrorWriter -> `alpha_input_v1.jsonl` -> IngestGateway -> ScenarioWorker -> AlphaSearchBacktestPlugin -> shadow logs | Shadow comparator data comes from a dedicated offline-ish mirror/replay path | `runtime/feature_mirror_writer.py:72-170`, `runtime/ingest.py:5-170`, `runtime/scenario_worker.py:5-223`, `runtime/scenario_manager.py:70-157`, `runtime/reporting.py:30-79` |
| Shutdown export | `simulator_shutdown_export.enabled=false` | Offline simulator export is present but not active by default | `config/alpha_search.yaml:298-306`, `backtest_plugin.py:1922-1965` |

## Judge Architecture Map

| Layer | What it does | Authority posture | Source |
| --- | --- | --- | --- |
| `ExpertOutput` | Typed expert response with exactly one verdict scope and canonical `cycle_key` | Shadow evidence only | `judge/contracts.py:149-188`, `judge/identity.py:8-35` |
| `ChamberAggregate` | Filters by scope, counts responding/abstaining experts, and evaluates admissibility and consensus | Shadow evidence only | `judge/contracts.py:206-273`, `judge/chamber/chamber_aggregator.py:28-168`, `judge/chamber/admissibility.py:18-65` |
| `JudgeEvidenceEnvelope` | Packages chamber output with regime, features_ref, position_context, and provenance | Shadow evidence only | `judge/contracts.py:280-337`, `judge/envelope/envelope_assembler.py:54-125` |
| `JudgeVerdict` | Deterministic mapping from chamber state to verdict | Shadow-only verdict; `applied=false` in off/shadow | `judge/contracts.py:344-423`, `judge/verdict/verdict_synthesizer.py:27-276` |
| `ShadowEntryPlan` | Derives hypothetical limit-plan telemetry from entry verdicts | Shadow telemetry only; `shadow_only=true` | `judge/contracts.py:425-534`, `judge/shadow_entry_plan.py:71-172` |
| Policy cortex | Builds a surface key, looks up evidence, classifies the surface, and emits a shadow annotation | Shadow-only surface evidence | `judge/policy_cortex/surface_key_builder.py:49-86`, `judge/policy_cortex/surface_registry.py:54-181`, `judge/policy_cortex/policy_classifier.py:52-105`, `judge/policy_cortex/cortex_evaluator.py:43-203` |
| Review / simulator | Joins verdicts to chambers, envelopes, and outcomes; computes disagreement, calibration, and expert accuracy | Offline comparator only | `judge/review/engine.py:408-1455`, `judge/simulator/simulator_engine.py:439-760`, `judge/simulator/disagreement_analyzer.py:57-177`, `judge/simulator/expert_accuracy_reporter.py:10-115`, `judge/simulator/calibration_dataset_writer.py:174-260`, `judge/simulator/summary_report_writer.py:193-220` |

## Isolation Proof / Gaps

Proof:

- A search across `apps/reference/domains/alpha_search/**/*.py` found no `CMD:OPEN` or `CMD:CLOSE` emissions in the alpha_search tree.
- `backtest_plugin.py` registers only feature, TA, decision, trade, and objective listeners; there is no open/close authority path in the listener set (`backtest_plugin.py:312-339`).
- The judge-expert branch explicitly says it does not emit `EVT:ALPHA_SCORE_CALCULATED`, and the chamber/verdict/policy cortex path is described as shadow-only and not consumed by `decision_making` or `execution_position` (`backtest_plugin.py:1020-1440`, `judge/policy_cortex/cortex_evaluator.py:11-17`, `judge/policy_cortex/evidence_models.py:145-195`).
- `JudgeCortexConfig` only admits `off` and `shadow`, and `JudgeVerdict` plus `PolicyCortexAnnotation` enforce shadow-only posture at the model level (`judge/config_models.py:351-409`, `judge/policy_cortex/evidence_models.py:117-195`).
- `ShadowEntryPlan` enforces `authority_mode="shadow"`, `applied=false`, and `shadow_only=true`; the offline simulator consumes these plans without executing anything (`judge/contracts.py:425-534`, `judge/shadow_simulator.py:16-64`).
- `FeatureMirrorWriter` is the only file that touches `main.py`, which keeps the mirror path narrow and observable (`runtime/feature_mirror_writer.py:14-33`).

Gaps:

- `config/aurora/domains.yaml` allows `judge_confidence` as a valid confidence source, so a future wiring change could contaminate live scoring even though the audited alpha_search code does not prove such wiring today.
- The BTCUSDT policy-cortex sample returned `UNKNOWN`, which means evidence coverage is incomplete at least for one observed surface.
- The live order trace lacks `decision_id` and `cycle_key`, so live-to-judge joins are not closed.
- The shared shadow journal sample is generic portfolio telemetry, not judge telemetry, so it does not close the judge evidence loop by itself.

## Comparator Validity Table

| Evidence surface | Current reliability | Why | Required join / limit |
| --- | --- | --- | --- |
| Expert disagreement | High for structure, conditional for economics | Chamber, verdict, and dissent are deterministic and cycle-keyed | Needs `cycle_key` and, for economics, an exact outcome join |
| Strategy comparison (final vs chamber vs no-judge) | High where chamber artifacts exist | Review engine reconstructs chamber-only, final-judge, suppression, and disagreement rows | Needs chamber and envelope artifacts plus exact outcome join for net return |
| Shadow PnL | Medium as an internal shadow metric only | Virtual trader and shadow book track internal PnL, drawdown, and win rate | Never treat as live PnL |
| Old vs new policy comparison | Partial | Review tooling supports policy surface comparisons, but incumbent-only baseline is unavailable in current repo-supported evidence | Requires registry coverage and comparable artifacts on both sides |
| Gate false positive / false negative support | High when outcome is joined | Disagreement and calibration records are deterministic and cohorted | Needs exact outcome join plus disagreement/calibration records |
| Policy cortex surface labels | Partial / coverage-dependent | Unknown surfaces fail closed instead of guessing | Use only as shadow surface evidence; do not promote UNKNOWN to positive evidence |

## Missing Evidence Joins

- `cycle_key`: canonical judge identity, present in judge artifacts but null in the live order sample.
- `decision_id`: null in the live decision trace, so it cannot currently serve as a reliable live-to-judge join key.
- `rid`: useful transport traceability, but not canonical judge identity.
- `lifecycle_id`: present in some transport or portfolio logs, but not part of the judge artifact contract.
- `symbol`, `regime`, and `tf_sec`: useful partition fields, but not sufficient by themselves.
- `outcome data`: external `data/simulator/outcomes.json` joined by exact `(strategy_id, symbol, tf_sec, bar_close_ts)`.
- `features_ref`: useful bar snapshot pointer, but not an outcome join.
- `source_file`: file partition metadata only; it is not authoritative identity.

## Recommended P0 Usage

- Use the Judge stack for accepted/rejected analysis at exact `cycle_key` granularity.
- Use exact outcome joins for gate calibration, abstain/suppress analysis, and disagreement cost.
- Use strategy comparison only where the chamber, verdict, and outcome joins are all present.
- Use policy-cortex outputs as fail-closed surface evidence and only where the registry returns a known surface.
- Use shadow PnL and expert accuracy as calibration inputs, not as live profit claims.
- Use the review engine to segment by `symbol`, `regime`, `tf_sec`, and `source_file` when you need stability checks across slices.

## Forbidden Uses

- Execution authority.
- Direct `CMD:OPEN` or `CMD:CLOSE`.
- Live order placement or live scoring ownership.
- Treating shadow PnL as live PnL.
- Treating expert verdict validity as proven without an outcome join.
- Promoting policy-cortex annotations or shadow entry plans into live gates without a separate authority audit.
- Using `judge_confidence` as a live confidence source unless a separate audited wiring path exists.
- Treating UNKNOWN policy-cortex surfaces as positive evidence.
- Hidden override of `decision_making` or `execution_position`.

## Bottom Line

Use `alpha_search` and Judge as a shadow comparator and calibration engine only. Keep the authority boundary hard, keep the joins exact, and keep the economic claims tied to matched outcomes rather than to shadow PnL or verdict confidence alone.
