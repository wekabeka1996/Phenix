# Neocortex Deep Domain Audit

Date: 2026-03-10
Workspace: `C:\Users\user\Music\Phenix`
Domain: `apps/reference/domains/neocortex`

## Executive Summary

`neocortex` already has a strong conceptual direction, but the current implementation is not yet a true latent-space RL brain for Aurora.

Today it is closer to:

- a standalone shadow observer,
- a per-bar latent encoder (`VAE`),
- a weak self-supervised regime predictor wrapped in a PPO interface,
- a log ingestor with partial episode reconstruction,
- a telemetry and shadow-intent emitter.

It is **not yet**:

- a coherent world-model planner,
- a fill-aware trading RL agent,
- a causally correct multi-symbol sequence learner,
- a contract-clean production domain.

My bottom-line evaluation:

- Current implementation quality: **4.6/10**
- Conceptual potential after redesign/fixes: **8.4/10**
- Safe production usage today: **observer / diagnostic / representation-research only**
- Unsafe usage today: **live policy modulation, fill-aware execution learning, PnL-driven RL**

## Scope And Evidence

I reviewed:

- domain code in `apps/reference/domains/neocortex/*`
- configs in `apps/reference/domains/neocortex/config/*.yaml`
- domain contract in `apps/reference/domains/neocortex/domain.yaml`
- tests in `apps/reference/domains/neocortex/tests/*`
- local runtime data in `logs/features/*`, `logs/order_log_v1.jsonl`, `logs/aurora_core.log`

Key runtime evidence from local logs:

- Feature tape volume: **2,454,196 rows** across 7 symbols
- Order log counts:
  - `ORDER_INTENT`: 215
  - `ORDER_REJECTED`: 218
  - `ORDER_PLACED`: 53
  - `ORDER_CANCELLED`: 24
  - `ORDER_FILLED`: 31
  - `POSITION_CLOSED`: 15
- All sampled and counted `ORDER_PLACED` entries had `adapter_response.executedQty = 0.00`
- `logs/order_log_v1.jsonl` contains **34 lines with `MagicMock` artifacts**
- `logs/aurora_core.log` contains:
  - 3 JSON-like `POSITION_CLOSED` messages
  - 5 plain text `Position closed` messages
  - 0 mentions of `realized_pnl_net`
  - 3 mentions of `realized_pnl=...` inside free-form message text

Testing status:

- `pytest apps/reference/domains/neocortex/tests -q` does **not** currently reach domain execution.
- Test collection is blocked earlier by a repo-level import error in `apps/reference/config_models.py:3572` because `Tuple` is not imported.

## What Neocortex Actually Is Today

From the code path in `main.py`, `transport/adapter.py`, `logic/brain/core.py` and `logic/ingest/multi_tailer.py`, the real runtime behavior is:

1. Read dense market features from log files.
2. Parse and normalize those features.
3. Encode each observation into a latent vector.
4. Ask a PPO-like policy head for a shadow action.
5. Emit and log a shadow intent.
6. Train VAE and world model in the background.
7. Optionally train PPO from either:
   - regime-oracle settled feature episodes, or
   - order/core-log episodes reconstructed from execution logs.

This means the domain is currently a **hybrid of self-supervised representation learning and shadow policy experimentation**, not a mature RL trading subsystem.

The most important architectural truth is this:

> The codebase talks about Dreamer/world-model planning, but the action path is currently just `features -> VAE latent -> PPO head -> shadow intent`.

The world model is trained, but it is not meaningfully used in online decision selection.

## Core Findings

## 1. The regime-oracle PPO pipeline is semantically contaminated

Severity: Critical

Why it matters:

- In `main.py:153-160`, `MultiTailer` is always wired with `episode_handler=adapter.add_completed_episode`.
- In `transport/adapter.py:403-431`, completed episodes from the tailer are appended into the same `_completed_episodes` buffer that also receives regime-oracle settlements from `_handle_oracle_settlement()` at `transport/adapter.py:749-850`.
- In `logic/brain/core.py:595-625`, PPO training maps plain trade sides `BUY/SELL` to action indices `0/1`, even when `action_dim == 5` and the action space is supposed to mean `TREND_UP/TREND_DOWN/MEAN_REVERSION/HIGH_VOLATILITY/EXHAUSTION`.

Consequence:

- The same PPO head is trained on two incompatible semantics:
  - oracle episodes: regime-class predictions,
  - log episodes: trade-side actions and execution outcomes.

This is a direct objective corruption bug.

Effect on RL/ML:

- The policy target is not stationary.
- The action space is overloaded.
- Metrics from PPO are not interpretable.

## 2. Temporal semantics are broken across the three data sources

Severity: Critical

Evidence:

- Feature logs in `logs/features/*.log` are pure JSON rows without timestamps.
- `parse_feature_log_line()` injects `time.time()` for pure JSON lines in `logic/ingest/parsers/feature_parser.py:99-115`.
- Order logs use epoch milliseconds, passed through raw in `logic/ingest/parsers/order_parser.py:83-96`.
- Core logs are parsed as seconds via `datetime.strptime(...).timestamp()` in `logic/ingest/parsers/core_parser.py:93-99`.

Consequence:

- `neocortex` mixes seconds, milliseconds and replay-wallclock time in one domain.
- Idempotent keys in `transport/adapter.py:667-672` become replay-time dependent instead of market-time dependent.
- stale episode cleanup in `logic/ingest/multi_tailer.py:733-746` is mathematically wrong when `episode.timestamp` is milliseconds and `current_time` is seconds.
- any future attempt at time-based credit assignment, latency analysis or horizon validation will be unreliable.

This is not a cosmetic issue. For a sequence model, time semantics are part of the state.

## 3. The current episode builder is not fill-aware and not lifecycle-safe

Severity: Critical

Evidence:

- Pending episodes are keyed only by symbol: `logic/ingest/multi_tailer.py:189-191`
- New entry episode is created on `ORDER_PLACED`: `logic/ingest/multi_tailer.py:477-491`
- `ORDER_FILLED` is parsed by `order_parser.py`, but `_handle_order_event()` does not use it
- reward completion is matched only by symbol in `_handle_position_close()`: `logic/ingest/multi_tailer.py:603-649`

Consequence:

- overlapping intents for the same symbol overwrite each other,
- partial fills are ignored,
- entry-time state is captured at placement, not fill,
- real execution latency/slippage/adverse-selection are absent from the training tuple,
- `trade_id`, `order_id`, `client_order_id`, `lifecycle_id` are effectively wasted.

From a quant perspective, this is the difference between learning a trading policy and learning from bookkeeping noise.

## 4. The current core-log parser does not match the actual `aurora_core.log` format

Severity: Critical

Evidence:

- `core_parser.py:124-158` expects structured `POSITION_CLOSED` fields such as `symbol=` or `"symbol": ...`.
- Actual `logs/aurora_core.log` close lines are JSON objects whose payload is embedded inside `"message"`, for example:
  - `"[POSITION_CLOSED] BTCUSDT: position closed ... | realized_pnl=1.0"`
- `REALIZED_PNL_PATTERN` is defined in `core_parser.py:72-75` but never used.

Consequence:

- structured reward extraction is mostly non-functional against the current log format,
- pnl-mode RL is effectively blocked,
- reward missing state becomes common and training falls into waiting/degraded behavior.

This also explains why the code had to pivot toward `reward_mode: regime_oracle`.

## 5. Sequence modeling is logically inconsistent

Severity: Critical

There are three independent sequence bugs:

- `logic/brain/core.py:362-370` treats the latest training batch as one single latent sequence: `z.unsqueeze(0)`, regardless of symbol or episode boundaries.
- `PPOAgent` keeps one global recurrent hidden state across inference calls: `ppo_system/agent.py:85-86, 113-115`.
- PPO training does not actually train on sequences; updater receives flattened independent rows and the model sees `SeqLen=1` in `ppo_system/learning/updater.py:95-99` and `ppo_system/models/actor_critic_lstm.py:96-117`.

Consequence:

- Inference leaks memory across different symbols.
- Training does not teach the LSTM the same temporal behavior used at inference.
- The world model learns cross-symbol/cross-regime transitions that never existed causally.

This is the single biggest RL/latent-space design flaw in the current implementation.

## 6. `state_dim` is declared, validated, and then ignored

Severity: High

Evidence:

- `config_models.py:660-665` validates `ppo.state_dim >= vae.latent_dim`
- but `logic/brain/core.py:229-232` builds PPO observation space from `self.config.vae.latent_dim`, not `ppo.state_dim`

Consequence:

- extra context is not wired,
- policy cannot consume position, risk, portfolio or execution context,
- current PPO head operates only on the VAE latent of market features.

So even the config contract tells a richer story than the implemented action model.

## 7. The domain claims fail-closed strict config, but implementation uses many hidden defaults and degraded modes

Severity: High

Examples:

- `SystemConfig.run_mode` default in `config_models.py:55-58`
- `SystemConfig.rng_seed` default in `config_models.py:61-65`
- ingestion defaults in `config_models.py:97-112`
- VAE auxiliary defaults in `config_models.py:179-217`
- PPO defaults in `config_models.py:356-398`
- replay default factory in `config_models.py:634-637`
- parser clip defaults in `logic/ingest/parser.py:22-27, 195-203`
- no-torch and CPU degraded behavior in `logic/brain/core.py:81-89, 133-168`
- adapter degraded continuation when bridge start fails in `transport/adapter.py:1051-1063`

Consequence:

- documentation and runtime behavior diverge,
- experiment provenance is weaker than advertised,
- production safety assumptions are overstated.

The philosophy is good. The implementation does not yet fully honor it.

## 8. Relative path resolution is inconsistent with the documented contract

Severity: High

Evidence:

- `system.yaml` says paths are relative to domain root
- `config_models.py:67-71` resolves them with `Path(v).resolve()`, which makes them relative to the current process working directory, not the config file location

Consequence:

- the same config can write checkpoints/logs to different physical locations depending on launch directory,
- reproducibility and ops hygiene suffer.

## 9. Log dataset quality is contaminated by test artifacts

Severity: High

Evidence from `logs/order_log_v1.jsonl`:

- 34 lines contain `MagicMock`
- `ORDER_FILLED` examples contain mock-looking `reservation_id` values and unusable fill metadata

Consequence:

- offline learning/evaluation data is not clean,
- fill-related outcomes are not trustworthy,
- training data provenance is compromised.

For any ML trading system, contaminated event logs are fatal unless quarantined.

## 10. The current shadow-intent hot path is too expensive for the observed data volume

Severity: High

Per feature row, the adapter currently does:

- parse,
- normalize,
- amygdala update,
- buffer add,
- latent encode via inter-process bridge,
- PPO act,
- JSONL shadow write,
- telemetry CSV write,
- optional oracle settlement,
- possible training trigger.

With ~2.45M feature rows in the local tape, this is extremely I/O-heavy and IPC-heavy.

There is no real batching for encode/act, and no decimation gate before shadow logging.

Consequence:

- offline replay is much slower than it needs to be,
- disk growth is amplified,
- model experimentation is coupled to operational logging cost.

## 11. The current representation is market-only, not agent-state-aware

Severity: Medium

Evidence:

- `config/ingest.yaml` includes only market features
- no inventory, margin, exposure, open-position age, execution state, risk gate state, or action history are present in model input

Consequence:

- even a perfect encoder cannot learn a truly trading-aware policy,
- the policy cannot reason about whether it is already long/short/flat,
- this is closer to regime classification than trading RL.

## 12. `Dreamer` and `CausalGraph` are mostly aspirational at this stage

Severity: Medium

Evidence:

- `logic/dreamer.py` is not on the main runtime path
- `_process_episode()` uses `z_next = z` placeholder in `logic/dreamer.py:209-223`
- feature vector extraction in dreamer uses plain `dict.values()` ordering in `logic/dreamer.py:177-190`

Consequence:

- these modules should be treated as R&D scaffolding, not production cognition.

## 13. The event contract has already drifted from the domain manifest

Severity: Medium

Evidence:

- `domain.yaml:29-48` exports `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED`, `EVT:NEOCORTEX_SHADOW_INTENT`, `EVT:NEOCORTEX_STATE_UPDATED`, `EVT:NEOCORTEX_ALERT`
- but `transport/adapter.py:675-679` emits `EVT:NEOCORTEX_REGIME_PREDICTION` in regime-oracle mode

Consequence:

- downstream consumers cannot rely on the manifest as SSOT,
- contract testing is incomplete.

## Perspective-Specific Assessment

## RL / ML Engineer View

Strong points:

- good instinct to split representation (`VAE`), dynamics (`WorldModel`) and policy (`PPO`)
- per-symbol normalization is directionally correct
- auxiliary regime supervision on latent mean is a useful bridge between self-supervised and task-aware representation learning
- numerical safety work in PPO updater is better than average prototype code

Weak points:

- the current PPO problem is not a clean MDP
- action semantics are unstable
- recurrent state handling is incorrect for multi-symbol data
- training/inference sequence assumptions do not match
- world model is trained but not used to plan
- latent is not tied to actual downstream decision context

Recommendation:

- treat the current default as **representation learning + supervised regime prediction**
- do not call it RL until action, reward, and transition semantics are clean

## Latent Space / World Model View

Today's latent space is useful as:

- a compressed embedding of market microstate,
- a candidate regime manifold,
- an anomaly / drift substrate,
- a future input to clustering or retrieval.

It is not yet useful as:

- a reliable planning state,
- a causal state for action-conditioned simulation,
- a stable cross-symbol recurrent memory.

What is missing for a serious latent-space system:

- explicit temporal index with canonical bar time
- per-symbol recurrent state
- action-conditioned transition learning with executed actions, not placed intents
- uncertainty estimation around latent transitions
- offline validation: reconstruction drift, clustering purity, regime separability, symbol transfer, OOD calibration

## Quant Trader View

From a quant perspective, the biggest issue is that the domain does not yet learn on the true trade lifecycle.

Correct trade-learning tuple should be:

- pre-trade state,
- actual executed action,
- fill quality,
- realized path,
- realized pnl net of fees/slippage,
- position/risk context.

Current implementation often learns from:

- feature snapshot at order placement,
- order rejection/cancellation proxies,
- symbol-level close matching,
- sparse or missing pnl extraction.

This makes the current RL story economically weak.

The good news is that the infrastructure direction is still valuable:

- regime oracle can be a solid self-supervised pretraining task,
- latent encoder can support downstream alpha/risk tasks,
- shadow intent divergence analysis can still be useful for diagnosis.

## Architecture / Algorithmic Systems View

Positive:

- modular layout is better than a monolith
- standalone shadow process is the right safety posture
- brain worker isolation is directionally correct
- telemetry and checkpoints already exist

Negative:

- `brain_workers` config is misleading because `BrainBridge` currently spawns one worker
- queue sizing config is ignored
- event bus contract and standalone log-tail contract are not unified
- `MultiTailer` is too symbol-centric and not lifecycle-centric
- there is no canonical dataset builder layer between raw logs and learning

The architectural shape is promising, but the data plane is still too ad hoc.

## What Neocortex Is Missing

The minimum missing pieces before this becomes a serious production ML domain:

1. Canonical event-time contract
2. Canonical episode identity contract
3. Fill-aware action semantics
4. Clean separation of tasks:
   - representation learning
   - regime classification
   - bandit / RL policy learning
   - risk diagnostics
5. Per-symbol recurrent state management
6. Proper dataset builder with train/val/test splits by time
7. Offline evaluator with pnl-aware metrics and calibration curves
8. Clean production data hygiene
9. Contract tests against real log samples
10. A real planner if world model is meant to matter

## How I Would Use It Right Now

Safe current usage:

- standalone, read-only observer
- `reward_mode: regime_oracle`
- `normalization_scope: per_symbol`
- no actuation into Aurora decisions
- use outputs for:
  - regime drift diagnostics,
  - latent clustering research,
  - anomaly monitoring,
  - shadow disagreement reporting,
  - dataset generation for future models

Unsafe current usage:

- pnl-mode online learning from current core logs
- interpreting PPO outputs as trade recommendations
- cross-symbol recurrent reasoning
- any live modulation of thresholds/sizing based on current policy output

Operational recommendations right now:

- quarantine contaminated log rows containing `MagicMock`
- stop mixing log-derived trade episodes into regime-oracle PPO training
- disable or downsample shadow-intent emission during long replays
- force deterministic inference for evaluation runs
- keep `brain_workers=1` until state partitioning and batching are redesigned

## How I Would Redesign It

## Phase A: Make the data plane correct

- Add explicit bar/event timestamp into `logs/features/*.log`
- Normalize all timestamps to one unit
- Build episodes by `rid/lifecycle_id/order_id/trade_id`, not by symbol
- Learn from `ORDER_FILLED` or `POSITION_OPENED`, not merely `ORDER_PLACED`
- Parse real close pnl from actual `aurora_core.log` structure or emit a dedicated structured feed

## Phase B: Split the objectives

- Task 1: self-supervised sequence encoder
- Task 2: supervised regime head
- Task 3: execution-quality / adverse-selection head
- Task 4: contextual bandit or offline RL head only after real executed reward data is clean

This will be much more stable than forcing everything through one PPO head.

## Phase C: Upgrade the latent model

Best options:

- temporal contrastive encoder (`TS2Vec` / CPC-style)
- masked time-series model
- RSSM / latent state-space model if you truly want Dreamer-like planning
- ensemble next-state model for uncertainty
- optional symbol embedding for cross-instrument transfer

## Phase D: Upgrade the policy layer

For the current data reality, the better order is:

1. supervised regime classifier
2. contextual bandit for modulation hints
3. conservative offline RL on true fill-aware trajectories
4. only then controlled actuation

## Scoring

| Criterion | Score / 10 | Comment |
|---|---:|---|
| Vision / Concept | 8.5 | Strong and ambitious direction |
| Domain Role Clarity | 7.0 | Clear as a shadow observer, unclear as true RL brain |
| Modularity | 7.5 | Good decomposition into ingest/brain/reward/memory |
| Contract Integrity | 4.0 | Manifest, runtime events and log formats have drifted |
| Data Semantics | 2.5 | Time units and episode identity are broken |
| Latent Representation Foundation | 6.0 | Useful base, but still shallow and market-only |
| World Model Usefulness | 3.0 | Trained, but not meaningfully used for planning |
| RL Objective Correctness | 2.0 | Mixed semantics, weak MDP definition |
| Quant Realism | 3.0 | Placement-based rather than fill-based learning |
| Reward Design | 5.0 | Regime oracle is useful; pnl reward path is weak |
| Safety / Fail-Closed Discipline | 4.5 | Better intent than implementation |
| Reproducibility | 4.0 | Hidden defaults, wallclock timestamps, stochastic shadow act |
| Observability | 7.5 | Telemetry/logging are decent |
| Testability | 4.5 | Domain tests exist, but repo-level blocker breaks collection |
| Performance Efficiency | 4.0 | IPC and file I/O on every feature row are expensive |
| Extensibility | 7.5 | High ceiling after data-plane cleanup |
| Production Readiness | 3.5 | Observer-only, research-grade |

### Weighted Overall Score

**4.6 / 10**

### Potential Score After Corrective Redesign

**8.4 / 10**

## Final Verdict

`neocortex` is a high-potential research domain with a good architectural instinct, but it is currently caught between three identities:

- latent self-supervised learner,
- regime classifier,
- RL trading policy.

Right now it does not fully satisfy any one of them.

The fastest path to a strong system is not "more PPO".

The fastest path is:

1. fix the data and episode contracts,
2. separate the objectives,
3. treat regime-oracle as supervised pretraining,
4. add fill-aware executed-action datasets,
5. only then revisit offline RL and world-model planning.

If you do that, `neocortex` can become one of the most strategically valuable domains in the whole Aurora stack:

- the system's latent market memory,
- regime intelligence layer,
- anomaly and drift detector,
- shadow policy laboratory,
- and eventually a tightly gated modulation advisor.
