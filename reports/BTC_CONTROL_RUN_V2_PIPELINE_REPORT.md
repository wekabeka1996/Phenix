# BTC_CONTROL_RUN_V2_PIPELINE — REPORT

## 1. Executive Verdict

BTC_CONTROL_FAIL

The strongest justified conclusion is narrow: the canonical ETH/SOL V2 replay entrypoint is the recorder-features-v2 branch of [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py), and BTCUSDT does not traverse that same entrypoint. The run fails closed at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L433) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L457) because [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L758) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L760) set `assets.BTCUSDT.signal_threshold.enabled=false`.

Separately, the same V2 harness does not replay the full Aurora signal-emission contract. Its `_replay_symbol()` loop directly replays recorder bars into live RegimeDetector and directly calls QuadraticScoringKernel, but it does not instantiate AuroraHandler, does not call `_process_decision`, does not call `_emit_signal`, and does not traverse StrategyGateway or downstream execution/objective gates. Therefore this path is not a proven control baseline for the full V2 decision path requested in this task.

## 2. Scope Confirmed

Checked:

- the canonical ETH/SOL V2 replay/evaluator artifact at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md)
- the user-facing V2 entrypoint at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py)
- live DecisionMaking and Aurora signal-emission contract surfaces at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py) and [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json)
- BTC runtime config surface at [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml)
- BTC recorder and feature artifacts under [data/recorder](data/recorder) and [logs/features](logs/features)
- an actual BTC run on the identical recorder-features-v2 entrypoint

Not checked:

- no threshold tuning
- no weight tuning
- no code changes to make BTC admissible to the harness
- no substitution with another replay path
- no use of live 2026-03-20 BTC signal logs as a surrogate for the canonical V2 replay harness

Missing from workspace at audit time:

- `Вставленная ​​уценка.md` was searched and not found
- `Копіпаст і технічні блокери.txt` was searched and not found

## 3. Canonical V2 Path

Entrypoint:

- [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py)
- same ETH/SOL V2 artifact: [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L1)

Why this is the canonical ETH/SOL V2 path:

- the existing ETH/SOL report explicitly states V2 replay semantics: it uses recorder timeframe 300s, a trailing 5-day validation holdout, and states that the V2 replay reuses live RegimeDetector, QuadraticScoringKernel, live side-bias parameters, and live shield config at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L9) through [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L18)
- the same tool exposes two input modes: `aurora-logs` and `recorder-features-v2`; only the latter is the replay path, as defined in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L281) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L338)
- `_run_v2()` loads recorder bars, audits feature logs, loads typed runtime config, and calls `_fit_v2_symbol_calibration()`, which in turn calls `_replay_symbol()` on recorder bars. This is the actual evaluator path for the ETH/SOL V2 artifact in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py)

Module chain:

1. [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1941) parses args and loads Aurora YAML.
2. [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1947) builds `threshold_surfaces` via `_extract_live_threshold_surface()`.
3. [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py) routes `recorder-features-v2` into `_run_v2()`.
4. `_run_v2()` loads recorder bars and feature-log audit, then calls `_fit_v2_symbol_calibration()`.
5. `_fit_v2_symbol_calibration()` calls `_replay_symbol()`.
6. `_replay_symbol()` reconstructs regime via live RegimeDetector and directly calls QuadraticScoringKernel on each eligible bar.
7. The tool emits ReplayObservation metrics and a markdown report.

Inputs:

- config source: [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml)
- typed runtime config via ConfigLoader from `config/aurora`
- recorder bars from [data/recorder](data/recorder)
- feature-log audit from [logs/features](logs/features)

Outputs:

- overlay artifact and markdown report under `reports/threshold_calibration/*`
- no live event emission and no order/execution artifacts from the V2 harness itself

## 4. ACTIVE vs LEGACY vs DECLARED-BUT-NOT-USED

| surface | status | evidence | operational meaning |
| --- | --- | --- | --- |
| recorder 300s bars | ACTIVE | ETH/SOL V2 report shows recorder bars loaded at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L24) and [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L31); `_run_v2()` loads bars in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py) | V2 replay is bar-driven, not log-only |
| feature-log schema audit | ACTIVE | ETH/SOL V2 report shows feature-log existence and sampled keys at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L26) through [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L34) | feature logs are inspected for schema evidence, not as the primary timestamp axis |
| live RegimeDetector reconstruction | ACTIVE | ETH/SOL V2 report states regimes are reconstructed offline through live RegimeDetector at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L75); `_replay_symbol()` builds detector events and feeds RegimeDetector in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1086) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1351) | replay uses live regime logic rather than recorder regime labels |
| QuadraticScoringKernel | ACTIVE | ETH/SOL V2 report states active scoring path is QuadraticScoringKernel at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L15); `_replay_symbol()` calls `QuadraticScoringKernel.compute()` directly in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1361) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1382) | evaluator path exercises kernel math |
| shield cascade: DangerZone -> Context -> Memory | ACTIVE | ETH/SOL V2 report states active shield cascade at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L15); `_build_shield_cascade()` constructs these in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1121) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1194) | replay includes shield multipliers |
| sequential side-bias history | ACTIVE | `_make_side_bias_state()` and `_replay_symbol()` maintain buy/sell history in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1197) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1219) and [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1312) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1409) | replay is sequential and stateful across bars |
| per-symbol `signal_threshold.enabled/value` and per-symbol `regime_thresholds` | ACTIVE | `_extract_live_threshold_surface()` enforces them in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L433) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L505) | entry contract hard-blocks symbols that lack enabled per-symbol threshold surface |
| `aurora-logs` mode | LEGACY | tool exposes `aurora-logs` and `recorder-features-v2` side by side at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L281) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L338); the ETH/SOL V2 report uses the replay semantics, not the log proxy | `aurora-logs` is adjacent evidence mode, not the canonical replay path for this audit |
| feature-log timestamps | DECLARED BUT NOT USED | ETH/SOL V2 report states sampled feature-log keys expose no explicit timestamp field at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L27) and [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L34) | feature logs cannot serve as the auditable time backbone |
| recorder `regime` and `regime_conf` columns | DECLARED BUT NOT USED | ETH/SOL V2 report explicitly says recorder regime columns were not trusted at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L75) | replay reconstructs regime instead of trusting recorder labels |
| AuroraHandler readiness gates and `_emit_signal()` path | DECLARED BUT NOT USED | `_replay_symbol()` directly calls QuadraticScoringKernel and never instantiates AuroraHandler; live handler gating and signal emission live in [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L170) through [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L320) and [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L485) through [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L780) | canonical V2 harness does not prove full live decision contract |
| StrategyGateway, execution gating, objective gating | DECLARED BUT NOT USED | V2 report itself states side-bias and memory-shield replay is representative even though execution gating and objective gating are not replayed at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1790) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1795) | downstream route/no-route behavior is outside this replay path |
| `EVT:STRATEGY_SIGNAL_PRODUCED`, `EVT:STRATEGY_DECISION_BLOCKED`, `EVT:HANDLER_READINESS_DIAGNOSTICS` on the traced V2 harness | UNPROVEN | these events are declared in [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L25) through [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L36), but the canonical V2 harness stops before event emission for BTC and does not traverse AuroraHandler for eligible symbols | event-level proof is absent on the canonical V2 replay path |

## 5. BTC Trace

### 5.1 Same-path invocation

Executed command:

`C:/Users/user/Music/Phenix/.venv/Scripts/python.exe tools/calibration/calibrate_aurora_thresholds.py --symbols BTCUSDT --from-date 2026-02-08 --to-date 2026-03-20 --input-source recorder-features-v2 --out-dir reports/threshold_calibration/btc_control_v2_probe --emit-overlay --emit-report`

Observed result:

- process exited with code 1
- exact stop reason: `CalibrationError: Symbol BTCUSDT requires assets.BTCUSDT.signal_threshold.enabled=true for this calibrator`

Stopping point in code:

1. `main()` builds `threshold_surfaces` before routing to `_run_v2()` at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1941) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1954)
2. `_extract_live_threshold_surface()` inspects `assets.BTCUSDT.signal_threshold.enabled` at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L449) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L457)
3. BTC config provides `enabled: false` and `value: null` at [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L758) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L760)
4. `_run_v2()` is never entered for BTC

### 5.2 Input artifacts exist, but were not consumed by the same-path run

Recorder artifacts:

- 41 BTC recorder files exist in the same date window from `2026-02-08` through `2026-03-20`
- first file: `data/recorder/2026-02-08/BTCUSDT_300.csv`
- last file: `data/recorder/2026-03-20/BTCUSDT_300.csv`
- sample recorder row from [data/recorder/2026-03-20/BTCUSDT_300.csv](data/recorder/2026-03-20/BTCUSDT_300.csv#L2):
  - `symbol=BTCUSDT`
  - `tf_sec=300`
  - `timestamp=1773874799999`
  - `ready=False`
  - `regime=PENDING`
  - `feat_pillar_sum=-0.20088692108426912`

Feature artifacts:

- [logs/features](logs/features) contains `BTCUSDT.log`
- observed file size from terminal inspection: `330.28 MB`
- sampled first lines from terminal inspection show feature keys and values including `obi`, `tfi`, `delta_price`, `absorption`, `price`, `liquidity_kappa`, `ema_bias`, `volume_spike`, `volatility_state`, `depth_imbalance`, `macro_sync`, `macro_resid`, `volume_zscore`, `large_trade_imbalance`, `spread_bps`

Meaning:

- BTC has bars and feature artifacts available for replay
- the canonical V2 run still stops before bar loading, feature-log audit, readiness evaluation, regime reconstruction, scoring, thresholds, gates, effective side, or event emission
- therefore the stop is a harness-entry contract failure, not an input-data absence

### 5.3 What the canonical BTC run did not reach

Not observed on the same-path BTC run because `_run_v2()` was never entered:

- bars seen by `_load_recorder_bars()`
- feature-log audit by `_collect_feature_log_audit()`
- `_split_date_for_bars()`
- `_replay_symbol()`
- RegimeDetector output
- QuadraticScoringKernel output
- `thr_buy` / `thr_sell`
- `effective_side`
- any gate verdict after kernel
- any event emission surface

## 6. Event / Contract Evidence

Observed on the canonical BTC V2 run:

- no event surfaces
- no `EVT:QUADRATIC_DECISION_TRACE`
- no `EVT:STRATEGY_SIGNAL_PRODUCED`
- no `EVT:STRATEGY_DECISION_BLOCKED`
- no `EVT:HANDLER_READINESS_DIAGNOSTICS`

Reason:

- the run stops in `_extract_live_threshold_surface()` before `_run_v2()` and before `_replay_symbol()`

Live contract surfaces that exist in code:

- canonical signal event is declared in [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L16) and emitted in live Aurora at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L1099) through [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L1537)
- `EVT:QUADRATIC_DECISION_TRACE` is emitted in live Aurora at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L498) through [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L519)
- blocked-event surfaces are declared in [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L25) through [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L36)

But the canonical V2 harness does not prove those contracts:

- `_replay_symbol()` directly computes kernel output and stores ReplayObservation fields; it does not emit the live event contract
- the ETH/SOL V2 report itself explicitly limits replay fidelity and states execution/objective gating are not replayed

Separate evidence that exists but is outside scope:

- live 2026-03-20 Aurora runtime logs already show BTC signal emission and downstream path in [reports/REPORT_AURORA_ETH_SOL_SILENT_PATH_FORENSIC.md](reports/REPORT_AURORA_ETH_SOL_SILENT_PATH_FORENSIC.md#L19) through [reports/REPORT_AURORA_ETH_SOL_SILENT_PATH_FORENSIC.md](reports/REPORT_AURORA_ETH_SOL_SILENT_PATH_FORENSIC.md#L31) and [reports/REPORT_AURORA_ETH_SOL_PRESIGNAL_BRANCH_FORENSIC.md](reports/REPORT_AURORA_ETH_SOL_PRESIGNAL_BRANCH_FORENSIC.md#L20) through [reports/REPORT_AURORA_ETH_SOL_PRESIGNAL_BRANCH_FORENSIC.md](reports/REPORT_AURORA_ETH_SOL_PRESIGNAL_BRANCH_FORENSIC.md#L31)
- that is not the same path as the canonical V2 recorder-features-v2 harness and therefore does not satisfy this task’s same-path requirement

## 7. FACTS

- FACT: the only concrete ETH/SOL V2 replay artifact found in the workspace is [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md)
- FACT: that artifact describes a V2 replay that reuses live RegimeDetector, QuadraticScoringKernel, live side-bias parameters, and live shield config at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L15) through [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md#L18)
- FACT: the user-facing entrypoint for that path is [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py)
- FACT: `main()` builds threshold surfaces before choosing `_run_v2()` at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1941) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1954)
- FACT: `_extract_live_threshold_surface()` requires `assets.<SYMBOL>.signal_threshold.enabled=true` at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L449) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L457)
- FACT: BTC config violates that requirement because [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L758) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L760) set `enabled=false` and `value=null`
- FACT: the actual BTC run on the identical entrypoint failed with `CalibrationError` before `_run_v2()`
- FACT: BTC recorder and feature artifacts exist in the inspected date window; the stop was not due to missing input files
- FACT: `_replay_symbol()` directly calls QuadraticScoringKernel and does not instantiate AuroraHandler or StrategyGateway in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1292) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1411)
- FACT: the ETH/SOL V2 report explicitly states execution gating and objective gating are not replayed in this harness at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1790) through [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1795)
- FACT: `EVT:STRATEGY_SIGNAL_PRODUCED` is canonical in the live DecisionMaking domain contract at [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L16) and [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json#L33)
- FACT: the requested files `Вставленная ​​уценка.md` and `Копіпаст і технічні блокери.txt` were not present in the workspace search results

## 8. INFERENCES

- INFERENCE: the canonical ETH/SOL V2 harness is a narrower evaluator/calibration replay harness, not a full replay of the live Aurora signal-emission contract
- INFERENCE: BTC cannot serve as a same-path control symbol on the current canonical V2 entrypoint because the entry contract rejects BTC before replay begins
- INFERENCE: because the harness does not traverse AuroraHandler, `_emit_signal`, StrategyGateway, or downstream gates, it cannot prove the full chain requested by this task: `input data -> feature state -> scoring/evaluator -> threshold chain -> gate verdicts -> effective_side -> EVT:STRATEGY_SIGNAL_PRODUCED or neutral/block`
- INFERENCE: further ETH/SOL per-symbol threshold tuning based on this harness remains premature if the objective is to validate the full V2 decision path rather than only kernel-side replay behavior

## 9. ASSUMPTIONS

- ASSUMPTION: the ETH/SOL V2 artifact at [reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md](reports/threshold_calibration/testnet_fasttrack_eth_sol_v2/report.md) is the intended prior V2 path because no alternative ETH/SOL replay artifact with stronger same-path evidence was found
- ASSUMPTION: using the same date window `2026-02-08` through `2026-03-20`, default `tf_sec=300`, and `input-source=recorder-features-v2` preserves the same entry methodology used by the ETH/SOL V2 artifact

## 10. UNKNOWNS

- UNKNOWN: whether an unpublished or currently absent BTC-capable V2 replay entrypoint exists elsewhere outside the inspected workspace evidence
- UNKNOWN: whether BTC would produce actionable replay observations if the harness were extended to support BTC’s global-threshold configuration instead of requiring per-symbol threshold enablement
- UNKNOWN: whether a higher-fidelity replay that instantiates AuroraHandler and traverses `_emit_signal` would validate BTC as a control symbol on the same data window
- UNKNOWN: whether the ETH/SOL V2 report’s zero-activation outcome is caused only by symbol geometry or partly by replay fidelity limitations relative to live AuroraHandler gating

## 11. Root Cause Assessment

Pipeline valid / invalid / unproven:

- invalid as a control-baseline for this task
- not proven as a full V2 decision-path replay

Mechanism:

- entry-contract defect for control use: the canonical V2 entrypoint requires per-symbol threshold enablement, but BTC is configured to use the global threshold surface instead of a per-symbol enabled override
- fidelity gap: the harness replays regime reconstruction and kernel scoring, but it does not replay AuroraHandler readiness path, signal emission, StrategyGateway, or downstream gates/events

Effect:

- BTC cannot be run through the identical ETH/SOL V2 entrypoint without changing the methodology
- the requested control proof cannot be completed on the same path
- a PASS verdict would exceed the evidence

Operational risk:

- replay/evaluator findings can be mistaken for full decision-path truth even though the harness is narrower than the live event contract
- symbol tuning on ETH/SOL can proceed on a replay surface whose fidelity to live signal emission is not yet proven

## 12. Next Action

V2_EVALUATOR_REPLAY_FIDELITY_AUDIT

Why this and not the ETH/SOL geometry package:

- the blocker is upstream of symbol tuning
- the canonical V2 path is not BTC-capable under the same entry contract
- the canonical V2 path also does not traverse the full live Aurora decision contract
- until replay fidelity is audited against AuroraHandler, `_emit_signal`, and the declared event surfaces, any ETH/SOL feature/regime/score geometry work would still rest on an incomplete proof chain
