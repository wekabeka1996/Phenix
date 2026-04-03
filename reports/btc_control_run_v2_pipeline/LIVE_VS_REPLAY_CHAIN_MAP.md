# LIVE_VS_REPLAY_CHAIN_MAP

## Scope

Package: BTC_CONTROL_RUN_V2_PIPELINE

Question under test: can the current Aurora V2 recorder-features-v2 replay path reproduce the active live BTCUSDT Aurora decision chain closely enough to be trusted as the stage-1 foundation for future Aurora calibration work?

Evaluation date: 2026-04-01

## Proven Facts

- BTCUSDT is assigned to Aurora in config/aurora/strategies.yaml:34-35.
- The live Aurora trigger is AuroraHandler.on_process_strategy in apps/reference/domains/decision_making/aurora_handler.py:694. AuroraHandler.on_features_calculated in the same file at 816 is a data-only compatibility wrapper and does not trigger decision logic.
- The live decision core is AuroraDecisionMixin._process_decision in apps/reference/domains/decision_making/aurora_decision.py:200.
- The live signal emission path is AuroraDecisionMixin._emit_signal in apps/reference/domains/decision_making/aurora_decision.py:1229.
- The live downstream actionable path continues through StrategyGateway.process_signal in apps/reference/domains/decision_making/strategy_gateway.py:214.
- The replay path used by tools/calibration/calibrate_aurora_thresholds.py loads recorder bars at 1238, filters bars with _bar_is_eligible at 1356, builds reduced scoring features at 1370, audits feature logs at 1298, and replays bars through _replay_symbol at 1601.
- The current BTC asset block in config/aurora/strategies/aurora.yaml:762-764 has signal_threshold.enabled: false and signal_threshold.value: null.
- The canonical threshold calibrator hard-requires assets.<SYMBOL>.signal_threshold.enabled=true in tools/calibration/calibrate_aurora_thresholds.py:535.
- The feature-log audit explicitly warns that sampled BTC feature-log keys contain no timestamp field, so recorder is the only auditable time axis in tools/calibration/calibrate_aurora_thresholds.py:1339.

## Contract Matrix

| Contract surface | Live BTC chain | Replay BTC chain | Status | Operational impact |
| --- | --- | --- | --- | --- |
| Strategy assignment | BTCUSDT resolves to Aurora via registry assignment. | Replay can target BTCUSDT as a CLI symbol and recorder files exist. | MATCH | Control symbol selection is aligned. |
| Entry trigger | CMD:PROCESS_STRATEGY enters AuroraHandler.on_process_strategy and passes envelope validation before scoring. | Replay iterates recorder rows and calls _replay_symbol directly. | MISMATCH | Replay bypasses the real live command envelope. |
| Envelope validation | Live rejects malformed or disabled commands, wrong tf_sec, missing bar_close_ts, and writes reject evidence before scoring. | No equivalent command-envelope validation exists in replay. | MISMATCH | Replay can score bars that would never reach the live kernel path. |
| Cold-start and readiness | Live increments _bars_seen_since_restart only after envelope checks and blocks on basis_required/readiness before quadratic scoring. | Replay eligibility is only ready and finite close and finite pillar_sum. | MISMATCH | Replay does not enforce the same readiness contract as live. |
| Regime liveness | Live blocks stale regime state before scoring. | Replay rebuilds regime locally with RegimeDetector, but not through the live heartbeat cache path. | PARTIAL | Core regime model is reused, but liveness semantics are not identical. |
| Feature time axis | Live decisions consume CMD features plus cached EVT feature data and canonical bar identity. | Replay uses recorder CSV columns and audits feature logs only for existence and sample keys. | MISMATCH | Replay does not join live feature log payloads to decision bars. |
| Feature-log provenance | Live runtime has bar-by-bar event context and timestamps. | Replay sampled BTC feature logs expose no explicit timestamp field; recorder remains the only auditable time axis. | MISMATCH | Replay cannot prove bar-exact feature equivalence from feature logs. |
| Scoring kernel family | Live uses QuadraticScoringKernel under Aurora config loader strict path. | Replay also uses QuadraticScoringKernel. | MATCH | Core scoring family matches. |
| Shield cascade family | Live uses configured shield cascade in quadratic mode. | Replay rebuilds shield cascade from the same typed config. | PARTIAL | Same shield family is reused, but slice evidence shows materially different realized shield multipliers. |
| Threshold surface extraction | Live BTC currently trades with the global decision.signal_threshold because the BTC symbol-level threshold override is disabled. | Canonical replay/calibrator refuses to run unless BTC symbol-level signal_threshold.enabled=true. | BLOCKED | The stage-1 replay entrypoint is not valid for current live BTC config. |
| Signal emission semantics | Live emits EVT:STRATEGY_SIGNAL_PRODUCED with signal payload, TP/SL context, and rollout metadata. | Replay emits ReplayObservation records only. | MISMATCH | Replay is not the live event contract. |
| Gateway and trade intent | Live passes signals into StrategyGateway and can emit EVT:TRADE_INTENT_PROPOSED and execution intents. | Replay stops at offline observations and forward-return proxy metrics. | MISMATCH | Replay cannot prove downstream live behavior. |
| Hold-state semantics | Live can propagate hold-side behavior across bars, evidenced by TRADE_INTENT_PROPOSED why=hold:sell on BTC. | Replay only records per-bar side decisions and showed neutral on one live hold slice. | MISMATCH | Replay misses stateful continuation behavior that affects actionable outputs. |

## Micro-Slice Evidence

### Slice A: 2026-03-31 07:30 live bar

- Live evidence from logs/aurora_core.log.28:7020-7027:
  - regime=TREND_UP
  - score=-0.135080
  - side=sell
  - shield_mult=0.600
  - thr_sell=0.01620
  - downstream gateway emitted TRADE_INTENT_PROPOSED
- Replay evidence from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:
  - timestamp=2026-03-31 07:29:59.999000
  - regime=TREND_UP
  - score=-0.0259507
  - side=sell
  - shield_multiplier=0.8
  - thr_sell=0.0162
- Conclusion: regime label and threshold factor align, but score magnitude differs by about 5.2x and realized shield attenuation differs materially.

### Slice B: 2026-03-31 07:35 live hold-state bar

- Live evidence from logs/aurora_core.log.28:10451-10458:
  - regime=TREND_UP
  - score=-0.139757
  - side=sell
  - gateway continued to trade intent emission
- Live downstream truth from logs/shadow_critical_event_journal_v1.jsonl:15609:
  - why=hold:sell:score=-0.1398<=-thr_neutral=-0.0500
- Replay evidence from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:
  - timestamp=2026-03-31 07:34:59.999000
  - regime=TREND_UP
  - score=-0.03472356
  - side=""
  - deferred=false
- Conclusion: replay missed the live hold-state continuation and emitted neutral where live produced another actionable sell path.

### Slice C: 2026-03-31 19:05 live bar

- Live evidence from logs/aurora_core.log.16:267-274:
  - regime=MEAN_REVERSION
  - score=-0.147459
  - side=sell
  - shield_mult=0.450
  - thr_sell=0.011340
  - gateway emitted TRADE_INTENT_PROPOSED
- Replay evidence from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:
  - timestamp=2026-03-31 19:04:59.999000
  - regime=MEAN_REVERSION
  - score=-0.02899209
  - side=sell
  - shield_multiplier=0.75
  - thr_sell=0.01134
- Conclusion: regime and threshold factor align, but score magnitude again differs by about 5.1x and shield attenuation differs materially.

## Inference

The current replay path is not equivalent to the live BTC Aurora decision chain. It reuses some live math components, but it fails the current BTC config contract at the canonical harness entrypoint and still diverges materially on stateful and score-scale behavior even when that harness block is bypassed for diagnostic replay.

## Hard Result

NO_GO_REPLAY_FIDELITY_NOT_PROVEN
