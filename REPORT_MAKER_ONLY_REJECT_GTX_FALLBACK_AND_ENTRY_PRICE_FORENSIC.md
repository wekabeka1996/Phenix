# AGENT_REPORT_V1

## Executive Summary
Current inspected runtime evidence says `NRR-018 / MAKER_ONLY_REJECT` is a real execution-stage venue/policy reject, not a hidden strategy-gate alias and not a hidden stale-position conflict. For the inspected live incident set, the canonical case is one `BNBUSDT` short from `md_amr`.

The proved runtime chain is:
- `MDAMRStrategyV11` sets `price_ref = bar_close`
- `MDAMRHandler` forwards that same value as `price_ctx.entry_price`
- `StrategyGateway` and `intent_builder` forward the same value into `TRADE_INTENT_PROPOSED`
- `execution_position.fsm_open` only rounds it to tick size
- `open_executor` submits `LIMIT + GTX`
- Binance rejects with `-5022`, normalized to `MAKER_ONLY_REJECT / NRR-018`

No inspected evidence proves a real `gtx_fallback_to_market` execution path after the reject. Current inspected code and runtime instead show a declared fallback flag, bookkeeping/log intent in handler code, and execution/runtime comments saying `NO FALLBACK`. This is a real declared-vs-runtime contract mismatch.

## Proven Facts
- `NRR-018` is emitted by execution, not decision:
  - `apps/reference/domains/execution_position/open_executor.py` catches maker-only reject codes and writes `ORDER_REJECTED` with `nrr_code="NRR-018"` and `why=MAKER_ONLY_REJECT`.
- Canonical maker-only reject reason is explicitly defined in `apps/reference/domains/execution_position/reasons.py`:
  - `MAKER_ONLY_REJECT = "MAKER_ONLY_REJECT"`
  - documented meaning: GTX/post-only order rejected because it would cross the book
  - documented behavior: `NO FALLBACK to market. Entry is aborted.`
- Websocket normalization independently classifies the same family in `apps/reference/adapters/binance_ws_client.py`:
  - `EXPIRED` + `timeInForce == "GTX"` + entry order + `executedQty == 0` => `MAKER_ONLY_REJECT`
  - payload is stamped with `fallback = "NONE"`
- `MDAMRStrategyV11` forms entry price as `bar_close`, not book-aware maker price:
  - in `apps/reference/domains/feature_engineering/md_amr_strategy.py`, both long and short `ENTRY` signals set `price_ref=bar_close`
  - no maker-safe offset, no bid/ask reference, and no GTX-specific repricing logic were found in that strategy core
- `MDAMRHandler` forwards the same value downstream:
  - `price_ctx.entry_price = signal.price_ref`
  - `price_ctx.price_ref = signal.price_ref`
- `intent_builder` forwards the same value into the execution intent:
  - `order.price = str(price)` and `order.price_ref = str(price)`
- `execution_position.fsm_open` does not derive a new maker-safe price:
  - it validates payload
  - rounds LIMIT price down to tick size
  - enforces `GTX` only if global maker-only entry is enabled
  - no top-of-book repricing or `gtx_retry_offset_bps` usage is present there
- `binance_adapter.place_limit_entry()` submits the provided price verbatim as `LIMIT` with supplied `timeInForce`
  - documented note says GTX is post-only/maker-only and will be rejected if it would cross the book
- `gtx_retry_offset_bps` exists in typed config and YAML:
  - `apps/reference/config_models.py::StrategyExecutionConfig`
  - `config/aurora/strategies/md_amr.yaml`
  - but no inspected runtime code consumed it for price formation or reprice in the traced `md_amr -> intent -> execution` path
- `gtx_fallback_to_market` exists in typed config and YAML:
  - `apps/reference/config_models.py::StrategyExecutionConfig`
  - `config/aurora/strategies/md_amr.yaml` sets it to `true`
- `md_amr_handler._on_order_rejected()` contains only retry/fallback bookkeeping:
  - increments `_gtx_retries`
  - logs `MD_AMR_GTX_REJECT_RETRY`
  - if retries exhausted and `gtx_fallback_to_market` is true, logs `MD_AMR_GTX_FALLBACK ... -> MARKET`
  - comment says actual fallback would be handled upstream by signal intent
  - no concrete market re-emit or `CMD:OPEN` with `order_type=MARKET` was found in the inspected code path
- Global execution-domain commentary contradicts strategy YAML fallback declaration:
  - `config/aurora/domains.yaml` says maker-only entry rejects are `NO FALLBACK to market. Entry aborted on reject.`
- Strategy passport also already documents the weakness of the field name:
  - `config/docs/md_amr_strategy_passport.md` says `gtx_fallback_to_market` does not execute a real fallback by itself and is currently bookkeeping/logging only
- Canonical runtime evidence in `logs/order_log_v1.jsonl` shows exactly one `NRR-018` incident in the inspected window:
  - `BNBUSDT`, side `SELL`, rid `mdamr-928db2e77a75188e`
- For that incident, the runtime chain is directly evidenced:
  - `logs/aurora_trades.log`: `EVENT_TRADE_INTENT_PROPOSED - BNBUSDT SELL (price=643.4150) (qty=14.330000)`
  - `logs/domain_decision_making.log`: `QTY_CALC: price=$643.415`
  - `logs/domain_execution_position.log`: `GUARD_ADJUST: Price rounded to tick - original=643.415, rounded=643.41`
  - `logs/domain_execution_position.log`: `GUARD_PASSED ... price=643.41, order_type=LIMIT`
  - `logs/domain_execution_position.log`: `MAKER_ONLY_REJECT: GTX order rejected (code=-5022)`
  - `logs/order_log_v1.jsonl`: canonical `ORDER_REJECTED`, `NRR-018`, `why="MAKER_ONLY_REJECT"`
- The shadow journal for the same rid proves only this execution chain:
  - `EVT:TRADE_INTENT_PROPOSED`
  - `CMD:OPEN`
  - `DEC:OPEN`
  - no later `CMD:OPEN` with `MARKET` for the same rid was found in the inspected journal slice
- `logs/domain_execution_position.log` later records:
  - `IntentBoundaryAudit terminal reject ... reason=NRR-EXECUTION-NO-DOWNSTREAM-EVENT route=CMD:OPEN`
  - this is downstream wrapper/audit evidence, not the first concrete reject

## Incident Table
| symbol | rid | strategy | side | proposed_price | execution_price | tif | venue_result | canonical_result | observed_fallback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BNBUSDT | mdamr-928db2e77a75188e | md_amr | SELL | 643.415 | 643.41 | GTX | Binance reject `-5022` | `NRR-018 / MAKER_ONLY_REJECT` | No proven fallback |

## Code Path Map
| stage | owner | file | proved behavior |
| --- | --- | --- | --- |
| signal creation | MD-AMR strategy | `apps/reference/domains/feature_engineering/md_amr_strategy.py` | entry `price_ref` is `bar_close` |
| strategy payload build | MD-AMR handler | `apps/reference/domains/decision_making/md_amr_handler.py` | `price_ctx.entry_price = signal.price_ref` |
| gateway handoff | StrategyGateway | `apps/reference/domains/decision_making/strategy_gateway.py` | forwards `entry_price_dec` to intent builder |
| intent assembly | DecisionMaking intent builder | `apps/reference/domains/decision_making/intent_builder.py` | trade intent keeps same `price` and `price_ref` |
| exec guard | ExecPos open FSM | `apps/reference/domains/execution_position/fsm_open.py` | tick-round only; no maker-safe repricing |
| venue submit | Binance adapter | `apps/reference/adapters/binance_adapter.py` | submits LIMIT at provided price with provided `timeInForce` |
| reject normalization | ExecPos open executor | `apps/reference/domains/execution_position/open_executor.py` | `-5022/-1131` -> `MAKER_ONLY_REJECT` -> `NRR-018` |
| WS reject normalization | Binance WS client | `apps/reference/adapters/binance_ws_client.py` | `GTX + EXPIRED + 0 fill` -> `MAKER_ONLY_REJECT`, `fallback=NONE` |
| retry/fallback bookkeeping | MD-AMR handler | `apps/reference/domains/decision_making/md_amr_handler.py` | logs retry/fallback intent only; no proved market re-submit |

## Entry Price Formation Analysis
### Proven
- For `md_amr`, entry price is currently the strategy bar close.
- The BNB incident shows the exact path:
  - strategy/features price around incident: `643.415`
  - trade intent price: `643.415`
  - execution guard rounded price: `643.41`
  - submitted order remains a `LIMIT + GTX` entry
- No inspected code injects a maker-safe directional offset before venue submission.

### Inference
- This makes current `md_amr` LIMIT+GTX entries policy-fragile, because the chosen entry price is not explicitly derived to stay passive relative to current book state.
- A bar-close reference can be compatible with GTX sometimes, but it is not intrinsically maker-safe. Therefore `NRR-018` is an expected venue outcome under some market states, not necessarily a coding bug at the reject point itself.

## Fallback Audit
### Proven
- Strategy YAML declares:
  - `gtx_retry_max: 2`
  - `gtx_retry_offset_bps: 2.0`
  - `gtx_fallback_to_market: true`
- `md_amr_handler._on_order_rejected()` only updates retry state and logs intent.
- No inspected code in that handler emits a new trade intent or a market `CMD:OPEN`.
- Execution-side canonical reason and WS-path both say `NO FALLBACK` / `fallback=NONE`.
- For the observed BNB incident, runtime logs show the reject, but no `MD_AMR_GTX_REJECT_RETRY`, no `MD_AMR_GTX_FALLBACK`, and no follow-up market open for the same rid were found in the inspected evidence.

### Inference
- `gtx_fallback_to_market=true` is not a proved live capability in the inspected runtime.
- The most defensible interpretation is that the field currently overstates runtime behavior.

## Classification
| item | classification | rationale |
| --- | --- | --- |
| `NRR-018 / MAKER_ONLY_REJECT` itself | Not-a-bug / normal venue-policy reject | Binance GTX/post-only is supposed to reject if order would cross |
| MD-AMR entry price formation for LIMIT+GTX | Policy issue | strategy uses `bar_close`, not explicit maker-safe book-aware pricing |
| `gtx_retry_offset_bps` live behavior | Contract gap | declared in config but not proven in traced pricing/retry path |
| `gtx_fallback_to_market=true` for md_amr | Runtime/contract defect | declared true, but inspected code and runtime do not prove real market fallback |
| BNB reject downstream trace after `NRR-018` | Observability defect | boundary audit shows terminal wrapper, but downstream retry/fallback evidence is absent |

## Contradictions / Evidence Gaps
- Strategy config says `gtx_fallback_to_market: true`, while global execution-domain comments and canonical reason text say `NO FALLBACK`.
- Strategy passport already warns that fallback is only bookkeeping/logging, which means documentation inside the repo is itself split between declarative config meaning and traced runtime meaning.
- `gtx_retry_offset_bps` is declared, but no inspected end-to-end reprice logic used it in the live BNB chain.
- The absence of retry/fallback markers for the BNB incident leaves two bounded possibilities:
  - handler retry/fallback branch was not reached downstream
  - handler branch exists but was not observably triggered in this incident
- This report does not prove what top-of-book looked like at the reject instant, so it does not prove the precise crossing geometry. It proves the system submitted a passive-only GTX order at a price derived from bar close, and the venue rejected it as crossing/non-passive.

## Root Cause Candidates
- Primary cause of the observed BNB incident:
  - policy mismatch between `LIMIT + GTX` venue semantics and strategy-side entry price formation based on `bar_close` without proved maker-safe repricing
- Secondary cause family:
  - declared runtime capability drift around `gtx_fallback_to_market`
- Tertiary issue:
  - downstream observability gap after execution reject, evidenced by boundary audit wrapper and missing retry/fallback markers

## Validation Performed
- Read and correlated:
  - `apps/reference/domains/feature_engineering/md_amr_strategy.py`
  - `apps/reference/domains/decision_making/md_amr_handler.py`
  - `apps/reference/domains/decision_making/strategy_gateway.py`
  - `apps/reference/domains/decision_making/intent_builder.py`
  - `apps/reference/domains/execution_position/fsm_open.py`
  - `apps/reference/domains/execution_position/open_executor.py`
  - `apps/reference/domains/execution_position/reasons.py`
  - `apps/reference/adapters/binance_adapter.py`
  - `apps/reference/adapters/binance_ws_client.py`
  - `apps/reference/config_models.py`
  - `config/aurora/strategies/md_amr.yaml`
  - `config/aurora/domains.yaml`
  - `config/docs/md_amr_strategy_passport.md`
- Correlated runtime artifacts:
  - `logs/order_log_v1.jsonl`
  - `logs/aurora_trades.log`
  - `logs/domain_decision_making.log`
  - `logs/domain_execution_position.log`
  - `logs/aurora_core.log.2`
  - `logs/shadow_critical_event_journal_v1.jsonl`

## Residual Risk
- As long as strategy entry price is not explicitly maker-safe, more `NRR-018` incidents remain expected under live spread/book conditions.
- As long as config declares fallback that runtime does not prove, operators may overestimate recovery behavior.
- As long as downstream retry/fallback markers are absent after reject, live forensics will keep mixing root cause with audit-wrapper symptoms.

## What Remains Unproven
- Exact order-book state at the BNB reject instant.
- Whether any hidden uninspected component can re-drive `md_amr` into a later market fallback outside the inspected evidence set.
- Whether `gtx_retry_offset_bps` is used elsewhere in another non-inspected execution retry path.

## Minimal Safe Verdict
- `NRR-018 / MAKER_ONLY_REJECT` is a real venue/post-only reject family.
- In the inspected `md_amr` path, entry price is formed from `bar_close` and only tick-rounded downstream.
- That price formation is not proven compatible with GTX maker-only semantics.
- `gtx_fallback_to_market=true` is not proven as a real live fallback capability in the inspected runtime.
- The BNBUSDT case is best classified as:
  - venue-policy reject at execution stage
  - enabled by strategy-side pricing policy mismatch
  - with an additional runtime/contract gap around fallback semantics
  - plus an observability gap after reject

## One Best Next Action
Implement one explicit, audited GTX repricing contract before venue submission for `md_amr` entries, using a maker-safe live-book reference plus deterministic offset policy, and fail closed when that repricing context is unavailable. Until that exists, treat `gtx_fallback_to_market` as non-live behavior.
