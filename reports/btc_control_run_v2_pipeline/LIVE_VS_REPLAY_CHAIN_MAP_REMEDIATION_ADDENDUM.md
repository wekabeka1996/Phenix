# LIVE_VS_REPLAY_CHAIN_MAP Remediation Addendum

Package: AURORA_BTC_REPLAY_FIDELITY_REMEDIATION

Evaluation date: 2026-04-01

Updated hard result: NO_GO_REPLAY_FOUNDATION_STILL_NOT_TRUSTWORTHY

## Facts

- The canonical production-class BTC replay now executes through tools/calibration/calibrate_aurora_thresholds.py when called with --input-source recorder-features-v2 and --threshold-source-mode live-effective.
- The selected repair strategy is explicit dual-mode threshold resolution: asset-override-only preserves the legacy per-asset calibrator contract, while live-effective resolves the same baseline threshold source used by live Aurora.
- The repaired run resolved BTCUSDT baseline threshold from decision.signal_threshold and BTC regime thresholds from assets.BTCUSDT.regime_thresholds.
- Candidate emission remained fail-closed and emitted an empty overlay because the current live BTC threshold source is global, while the production calibration target surface remains assets.<SYMBOL>.signal_threshold.value only.
- Replay now enforces active Aurora basis_required_bars before scoring, reducing cold-start contract drift.
- Updated repaired micro-slices still diverge materially from live on score magnitude, shield attenuation, and hold-state continuity.

## Updated Contract Matrix

| contract surface | before remediation | after remediation | status after remediation | operational impact |
| --- | --- | --- | --- | --- |
| threshold surface entry contract | canonical BTC run aborted before replay because assets.BTCUSDT.signal_threshold.enabled=false | canonical BTC run passes in explicit live-effective mode; baseline source/path are recorded in manifest and metrics | partial_repaired | control replay is now contract-valid, but promotion remains blocked because the live source is global and candidate surface policy is still per-asset-only |
| readiness and cold-start | replay ignored active Aurora basis_required_bars | replay now enforces basis_required_bars before scoring | partial_repaired | replay is closer to live startup semantics, but still does not reproduce full warmup.readiness or blocked/deferred evidence |
| envelope validation | direct recorder loop bypassed CMD envelope checks | unchanged direct recorder loop | unchanged_mismatch | replay still lacks malformed-command rejection and reject-WAL parity |
| feature provenance / time axis | recorder was the only auditable time axis | unchanged recorder-only time axis | unchanged_blocker | exact feature-to-bar parity remains unproven |
| hold-state continuity | replay emitted neutral where live emitted hold:sell | unchanged on the repaired slices | unchanged_blocker | actionable continuation behavior still diverges |
| score scale | replay score magnitude materially below live | unchanged on repaired slices | unchanged_blocker | threshold-surface trust is still not proven |
| shield attenuation | replay shield multipliers materially above live | unchanged on repaired slices | unchanged_blocker | attenuation semantics still drift |
| signal / gateway semantics | replay stopped at ReplayObservation | unchanged | unchanged_blocker | downstream trade-intent truth is still outside replay evidence |

## Delta Interpretation

- The remediation solved the entry-contract blocker without mutating live YAML or silently widening the calibration target surface.
- The remediation did not solve feature provenance, hold-state continuity, score-scale drift, shield attenuation drift, or the signal-to-gateway semantic gap.
- The replay foundation is therefore improved at the control-entry layer but still not trustworthy enough for stage-1 BTC threshold-surface calibration.
