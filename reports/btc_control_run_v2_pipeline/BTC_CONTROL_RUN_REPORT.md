# BTC_CONTROL_RUN_REPORT

## Objective

Prove or falsify whether the current Aurora V2 replay/evaluator path is sufficiently faithful to live Aurora BTCUSDT decision logic to serve as the stage-1 calibration foundation.

## Facts

### 1. Canonical control run failed before replay execution

Command used:

python tools/calibration/calibrate_aurora_thresholds.py --input-source recorder-features-v2 --symbols BTCUSDT --from-date 2026-03-01 --to-date 2026-03-31 --recorder-dir data/recorder --feature-log-dir logs/features --tf-sec 300 --out-dir reports/btc_control_run_v2

Observed result:

- The run aborted in tools/calibration/calibrate_aurora_thresholds.py main() while building threshold_surfaces.
- Failure message:
  - Symbol BTCUSDT requires assets.BTCUSDT.signal_threshold.enabled=true for this calibrator
- Raw artifact:
  - reports/btc_control_run_v2_pipeline/canonical_btc_control_run_output.txt

Current live BTC config evidence:

- config/aurora/strategies/aurora.yaml:762-764 shows:
  - signal_threshold.enabled: false
  - signal_threshold.value: null

Implication:

- The current production-class stage-1 entrypoint cannot run on BTCUSDT without bypassing or changing the current live config contract.

### 2. Diagnostic replay required a non-canonical manual threshold surface

To inspect replay behavior after the canonical harness failure, a diagnostic-only replay was executed with:

- the same typed Aurora config loader
- the same live RegimeDetector
- the same QuadraticScoringKernel
- the same shield cascade reconstruction
- a manually supplied BTC ThresholdSurface using:
  - decision.signal_threshold=0.162
  - BTC regime_thresholds from config/aurora/strategies/aurora.yaml

This diagnostic replay is not the canonical stage-1 harness because it bypasses the very precondition that blocks BTC in the production-class calibrator.

Artifact:

- reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json

### 3. Feature-log provenance is not bar-exact inside replay

The replay path does not join feature-log records into per-bar scoring inputs. It only samples the feature log for audit metadata.

Observed BTC audit result from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:

- feature_log_audit.exists=true
- sampled_lines=20
- has_timestamp_fields=false
- warning:
  - Sampled feature-log keys for BTCUSDT expose no explicit timestamp field; recorder remains the only auditable time axis.

Implication:

- The replay cannot prove exact live feature-to-bar equivalence from the BTC feature log.

### 4. Warmed replay metrics still do not prove fidelity

Diagnostic replay summary for 2026-03-01 through 2026-03-31:

- split_date=2026-03-28
- train eligible bars=2972
- train activation rate=0.17429340511440108
- validation eligible bars=993
- validation activation rate=0.14904330312185296
- validation mean forward 3-bar proxy edge=-1.9264990413382086 bps
- validation sell count=148
- validation buy count=0

These are replay summary metrics only. They are not proof that the live event chain, hold semantics, or downstream gateway outcomes are faithfully reproduced.

### 5. Micro-slice evidence shows material live-vs-replay divergence

#### Slice A: live 2026-03-31 07:30 versus replay 2026-03-31 07:29:59.999

Live from logs/aurora_core.log.28:7020-7027:

- regime=TREND_UP
- score=-0.135080
- side=sell
- shield_mult=0.600
- thr_sell=0.01620
- gateway emitted TRADE_INTENT_PROPOSED

Replay from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:

- regime=TREND_UP
- score=-0.0259507
- side=sell
- shield_multiplier=0.8
- thr_sell=0.0162

Observed divergence:

- Same regime and threshold factor.
- Materially different score scale.
- Materially different shield attenuation.

#### Slice B: live 2026-03-31 07:35 versus replay 2026-03-31 07:34:59.999

Live from logs/aurora_core.log.28:10451-10458 and logs/shadow_critical_event_journal_v1.jsonl:15609:

- regime=TREND_UP
- score=-0.139757
- side=sell
- downstream why=hold:sell:score=-0.1398<=-thr_neutral=-0.0500

Replay from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:

- regime=TREND_UP
- score=-0.03472356
- side=""
- deferred=false

Observed divergence:

- Replay emitted neutral on a bar where live preserved an actionable sell hold-state through gateway and trade-intent emission.

#### Slice C: live 2026-03-31 19:05 versus replay 2026-03-31 19:04:59.999

Live from logs/aurora_core.log.16:267-274:

- regime=MEAN_REVERSION
- score=-0.147459
- side=sell
- shield_mult=0.450
- thr_sell=0.011340
- gateway emitted TRADE_INTENT_PROPOSED

Replay from reports/btc_control_run_v2_pipeline/diagnostic_replay_slice.json:

- regime=MEAN_REVERSION
- score=-0.02899209
- side=sell
- shield_multiplier=0.75
- thr_sell=0.01134

Observed divergence:

- Same regime and threshold factor.
- Materially different score scale.
- Materially different shield attenuation.

## Inferences

- The canonical BTC stage-1 harness is blocked by a current config/calibrator contract mismatch, so stage-1 fidelity is not proven even before comparing math outputs.
- The replay path reuses core live math components, but it does not reproduce the full live BTC decision contract because it bypasses command-envelope validation, readiness gates, live signal emission, gateway processing, and stateful hold behavior.
- The micro-slice score and shield mismatches are too large to treat the current replay as a faithful stand-in for live BTC Aurora threshold decisions.

## Unproven

- This package did not prove or falsify replay fidelity for ETHUSDT, SOLUSDT, or non-BTC Aurora symbols.
- This package did not implement a remediation to make the BTC harness canonical.
- This package did not prove exact root cause for the replay score-scale mismatch beyond the observed chain differences and missing live-state surfaces.

## Hard Verdict

NO_GO_REPLAY_FIDELITY_NOT_PROVEN
