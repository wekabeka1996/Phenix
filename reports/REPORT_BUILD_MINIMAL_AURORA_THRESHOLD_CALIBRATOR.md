# AGENT_REPORT_V1

## Executive Summary
Implemented a minimal dry-run Aurora threshold calibrator in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1) that reads only the live per-symbol threshold surface for assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds, parses observed QUADRATIC_DECISION_TRACE runtime evidence from aurora_core logs, and emits artifact-only overlay/report outputs without mutating production YAML.

## Proven Facts
- New implementation added at [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L1).
- CLI is defined in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L92) and supports:
  - --symbols
  - --from-date
  - --to-date
  - --input-source
  - --log-glob
  - --out-dir
  - --min-samples
  - --min-regime-samples
  - --target-quantile
  - --emit-overlay
  - --emit-report
- The tool reads only the live per-symbol threshold surface in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L191):
  - assets.<SYMBOL>.signal_threshold.enabled
  - assets.<SYMBOL>.signal_threshold.value
  - assets.<SYMBOL>.regime_thresholds
- The tool does not read or calibrate neutral_threshold, weights, cooldown, or holding_period. This is enforced by implementation scope and reflected in generated report text from [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L504).
- Runtime evidence source for v1 is QUADRATIC_DECISION_TRACE parsing from aurora_core logs via [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L271).
- Calibration logic is percentile-based and regime-aware in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L368):
  - candidate base threshold = quantile of observed |score|
  - candidate regime factor = regime quantile divided by proposed base threshold
  - only evidenced regimes with enough samples are emitted
- Overlay emission is artifact-only in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L487) and [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L692).
- Fail-closed behavior is implemented by CalibrationError handling in [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L718).
- Dry-run sample artifacts were generated successfully:
  - [reports/threshold_calibration/sample_20260320_eth_sol/candidate_threshold_overlay.yaml](reports/threshold_calibration/sample_20260320_eth_sol/candidate_threshold_overlay.yaml)
  - [reports/threshold_calibration/sample_20260320_eth_sol/report.md](reports/threshold_calibration/sample_20260320_eth_sol/report.md)

## Inferred Findings
- The implemented tool is minimal and production-safe for v1 because it is additive-only, artifact-only, and scoped to the threshold surface already proven relevant by prior ETH/SOL neutral-branch forensics.
- Using aurora_core QUADRATIC_DECISION_TRACE as v1 dataset is sufficient for threshold-surface estimation, but it remains a proxy for activation behavior rather than a full replay of all downstream gates.

## Contradictions / Evidence Gaps
- The tool does not prove downstream PnL or execution quality improvement. It only proposes threshold candidates aligned to observed runtime score distributions.
- The sample run used a single-day log window, so broader multi-day stability remains unproven.
- The emitted overlay fragment starts at assets:, which is overlay-ready for deep-merge workflows but is not a full standalone aurora.yaml file.

## Root Cause Candidates
- Not applicable as a primary purpose of this task. This task implemented a calibration tool rather than a new forensic diagnosis.

## Operational Risk
- Observability Gap
- Runtime

## Files / Areas Touched
- [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py)
- [reports/REPORT_BUILD_MINIMAL_AURORA_THRESHOLD_CALIBRATOR.md](reports/REPORT_BUILD_MINIMAL_AURORA_THRESHOLD_CALIBRATOR.md)
- Generated artifacts:
  - [reports/threshold_calibration/sample_20260320_eth_sol/candidate_threshold_overlay.yaml](reports/threshold_calibration/sample_20260320_eth_sol/candidate_threshold_overlay.yaml)
  - [reports/threshold_calibration/sample_20260320_eth_sol/report.md](reports/threshold_calibration/sample_20260320_eth_sol/report.md)

## Validation Performed
- Static editor diagnostics: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py) returned no Python errors.
- Dry-run generation command executed successfully:

```powershell
Set-Location 'c:\Users\user\Music\Phenix'
C:/Users/user/Music/Phenix/.venv/Scripts/python.exe tools/calibration/calibrate_aurora_thresholds.py --symbols ETHUSDT SOLUSDT --from-date 2026-03-20 --to-date 2026-03-20 --input-source aurora-logs --out-dir reports/threshold_calibration/sample_20260320_eth_sol --emit-overlay --emit-report
```

- Dry-run result summary:
  - ETHUSDT: current=0.090000 proposed=0.024928 activation(current=0.00%, proposed=21.54%)
  - SOLUSDT: current=0.090000 proposed=0.029709 activation(current=0.00%, proposed=24.62%)
- Fail-closed invalid-symbol validation executed successfully:

```powershell
Set-Location 'c:\Users\user\Music\Phenix'
C:/Users/user/Music/Phenix/.venv/Scripts/python.exe tools/calibration/calibrate_aurora_thresholds.py --symbols FAKEUSDT --from-date 2026-03-20 --to-date 2026-03-20 --input-source aurora-logs --out-dir reports/threshold_calibration/sample_invalid_symbol --emit-overlay --emit-report
```

- Invalid-symbol result:
  - FAIL-CLOSED: Symbol FAKEUSDT is absent from aurora.assets runtime config surface

## Residual Risk
- V1 is log-derived and does not reconstruct side-bias history, objective gating, or execution outcomes end-to-end.
- Sample proposals could be unstable in regimes with sparse coverage.
- Applying emitted overlay still requires human review and explicit config merge discipline.

## What Remains Unproven
- Whether the proposed ETH/SOL thresholds improve realized downstream trading behavior.
- Whether a replay-driven calibration would materially differ from the log-derived v1 proposal.
- Whether BTC control calibration should share the same percentile policy or a separate control workflow.

## Minimal Safe Verdict
The requested deliverable is complete: a narrow, dry-run Aurora threshold calibrator now exists and calibrates only assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds, emits overlay/report artifacts, excludes neutral_threshold and weights, and fails closed on invalid input.

## Implementation Notes
- Runtime surface extraction: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L191)
- Log parsing path: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L271)
- Percentile/regime fit: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L368)
- Overlay renderer: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L487)
- Markdown report renderer: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L504)
- Main dry-run flow: [tools/calibration/calibrate_aurora_thresholds.py](tools/calibration/calibrate_aurora_thresholds.py#L652)

## Key Code Fragments
```python
def _extract_live_threshold_surface(...):
    signal_threshold_cfg = asset_cfg.get("signal_threshold")
    ...
    regime_thresholds_raw = asset_cfg.get("regime_thresholds")
```

```python
proposed_signal_threshold_value = _percentile(absolute_scores, target_quantile)
...
factor = regime_effective_threshold / proposed_signal_threshold_value
```

```python
assets[calibration.symbol] = {
    "signal_threshold": {"value": _round_metric(calibration.proposed_signal_threshold_value)},
    "regime_thresholds": ordered_regime_thresholds,
}
```

## Example Generated Overlay
From [reports/threshold_calibration/sample_20260320_eth_sol/candidate_threshold_overlay.yaml](reports/threshold_calibration/sample_20260320_eth_sol/candidate_threshold_overlay.yaml):

```yaml
assets:
  ETHUSDT:
    signal_threshold:
      value: 0.024928
    regime_thresholds:
      DEFAULT: 1.0
      MEAN_REVERSION: 0.958946
      TREND_DOWN: 1.322609
  SOLUSDT:
    signal_threshold:
      value: 0.029709
    regime_thresholds:
      DEFAULT: 1.0
      MEAN_REVERSION: 0.984382
      TREND_DOWN: 1.345653
      UNCERTAIN: 0.740139
```

## Example Generated Report
See [reports/threshold_calibration/sample_20260320_eth_sol/report.md](reports/threshold_calibration/sample_20260320_eth_sol/report.md).

## V1 Limitations
- Input source is limited to aurora_core QUADRATIC_DECISION_TRACE logs.
- The tool calibrates only:
  - assets.<SYMBOL>.signal_threshold.value
  - assets.<SYMBOL>.regime_thresholds
- The tool does not calibrate:
  - neutral_threshold
  - weights
  - cooldown
  - holding_period
  - reentry
  - objective gates
