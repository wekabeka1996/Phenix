# AGENT_REPORT_V1

## Executive Summary

Phase 1A shows that the current reusable baseline engines are the two production calibrators, not the legacy forensics wrappers. `tools/calibration/calibrate_md_amr_weights.py` is safe to reuse as-is for full-range md_amr baseline replay on the requested live/candidate surfaces. `tools/calibration/calibrate_mean_reversion_params.py` is safe to reuse as-is for offline-only DOGE candidate study when an explicit study registry artifact is supplied and the run is clearly labeled not live assigned. `tools/forensics/full_surface_calibration.py` must remain quarantined. `tools/forensics/mr_signal_surface_audit.py` is also quarantined for this package because it hardcodes a stale DOGE window contract and fails on missing historical manifests.

No production code changes were required for the adequacy audit.

## Tool Verdicts

| Tool | Verdict | Why |
| --- | --- | --- |
| tools/calibration/calibrate_mean_reversion_params.py | REUSE_AS_IS | Reads current MR YAML, enforces registry scope, supports train/validation/forward, emits machine-readable artifacts, and passed targeted pytest. |
| tools/forensics/mr_signal_surface_audit.py | QUARANTINE | Hardcodes DOGE-only historical manifest paths; direct run fails because the expected manifest is absent in the current repo state. |
| tools/calibration/calibrate_md_amr_weights.py | REUSE_AS_IS | Reads current md_amr YAML, supports per-symbol full-range replay with per-regime artifacts, and passed targeted pytest. |
| tools/analysis/md_amr_integrated_validation.py | NOT_RELEVANT | Useful only as bounded A.1-vs-integrated comparator; it is not a current-profile aggression-search or baseline engine. |
| tools/forensics/full_surface_calibration.py | QUARANTINE | Hardcoded root path, symbols, registry, thresholds, and mixed constants violate SSOT and no-hidden-constants rules. |

## Per Tool Audit

### tools/calibration/calibrate_mean_reversion_params.py

- Reads current YAML/Pydantic SSOT: yes for `config/aurora/strategies/mean_reversion.yaml`; registry path is CLI-configurable and defaults to `config/aurora/strategies.yaml`.
- Hardcodes assignments, symbols, thresholds: no hardcoded symbols or assignments, but the search surface and `--cost-bps-roundtrip` default are explicit code/CLI constants.
- Supports per-symbol runs: yes.
- Supports per-regime grouping: yes via `--per-regime`.
- Supports train/validation/forward split: yes.
- Outputs machine-readable artifacts: yes, including `run_manifest.json`, `baseline_metrics.json`, `candidate_metrics.json`, `validation_metrics.json`, `forward_metrics.json`, overlay YAML, optional `per_regime_analysis.json`, optional `tpsl_surface.json`, and optional `mfe_mae_analysis.json`.
- Handles missing features fail-closed: yes. It validates requested recorder CSVs, validates YAML shape, validates assignment scope, and emits `failed_closed` manifests on insufficient data.
- Computes net after fees/slippage: yes, as a report-only roundtrip bps cost model.
- Supports aggression search dimensions needed here: supports now for `bb_window`, `bb_num_std`, `entry_threshold`, `sl_atr_mult`, `cooldown_sec`, `min_bb_width`, `max_bb_width`; wider MR fields are loaded into runtime config but not searched yet.
- Safe to reuse as-is: yes for offline replay. The current live registry still blocks DOGE under real SSOT, so the dormant DOGE study must be labeled as an explicit offline candidate scope.
- Exact minimal patch if future reuse needs to be cleaner: add an explicit dormant-candidate report-only mode so a temporary study registry is unnecessary.

### tools/forensics/mr_signal_surface_audit.py

- Reads current YAML/Pydantic SSOT: yes for MR YAML.
- Hardcodes assignments, symbols, thresholds: yes. It hardcodes `DOGEUSDT` and two historical manifest paths.
- Supports per-symbol runs: no.
- Supports per-regime grouping: yes.
- Supports train/validation/forward split: only through the hardcoded manifest windows.
- Outputs machine-readable artifacts: yes JSON, if the hardcoded manifest dependency exists.
- Handles missing features fail-closed: only partially. In current repo state it fails on missing manifest file rather than exposing a clean operator contract.
- Computes net after fees/slippage: no.
- Supports aggression search dimensions needed here: no; audit-only.
- Safe to reuse as-is: no.
- Exact minimal patch if future reuse is desired: move repo-root bootstrap above intra-repo imports, add CLI for symbol and window selection or manifest paths, and remove the hardcoded early/recent manifest dependency.

### tools/calibration/calibrate_md_amr_weights.py

- Reads current YAML/Pydantic SSOT: yes for `config/aurora/strategies/md_amr.yaml`.
- Hardcodes assignments, symbols, thresholds: no hardcoded active symbol scope, but the current mutation surface is weights-only.
- Supports per-symbol runs: yes.
- Supports per-regime grouping: yes via `--per-regime`.
- Supports train/validation/forward split: yes.
- Outputs machine-readable artifacts: yes, including `run_manifest.json`, `baseline_metrics.json`, `candidate_metrics.json`, `validation_metrics.json`, `forward_metrics.json`, overlay YAML, and optional `per_regime_analysis.json`.
- Handles missing features fail-closed: yes. It fails closed on missing YAML keys, missing assets, no recorder rows, and insufficient contiguous warmup history. It also records CSV parse fallback and gap resets explicitly.
- Computes net after fees/slippage: yes, from current YAML `fee_bps` and `slippage_buffer_bps`.
- Supports aggression search dimensions needed here: current search mutates weights only, but many required md_amr dimensions are already extracted from YAML and could be added with a small patch.
- Safe to reuse as-is: yes for full-range baseline replay on XRP live and ETH/SOL offline candidates.
- Exact minimal patch if Phase 2 grid expands: extend the mutation surface and overlay serializer beyond weights to the already-extracted base params.

### tools/analysis/md_amr_integrated_validation.py

- Reads current YAML/Pydantic SSOT: yes, through the md_amr calibrator loader.
- Hardcodes assignments, symbols, thresholds: defaults symbols in CLI and hardcodes A.1 baseline constants for `max_hold_bars` and `target_approach_pct`.
- Supports per-symbol runs: yes.
- Supports per-regime grouping: only indirectly through cohort outputs, not as a calibration grid.
- Supports train/validation/forward split: no.
- Outputs machine-readable artifacts: yes CSV plus markdown report.
- Handles missing features fail-closed: yes for no-data/no-symbol conditions.
- Computes net after fees/slippage: yes.
- Supports aggression search dimensions needed here: no.
- Safe to reuse as-is: not for current-profile baseline or Phase 2 search. It remains supplemental evidence only.
- Exact minimal patch if future reuse is desired: move repo-root bootstrap above imports for direct script execution and add a non-A.1 current-profile mode.

### tools/forensics/full_surface_calibration.py

- Reads current YAML/Pydantic SSOT: no.
- Hardcodes assignments, symbols, thresholds: yes, extensively.
- Supports per-symbol runs: no reliable contract.
- Supports per-regime grouping: ad hoc only.
- Supports train/validation/forward split: no explicit contract.
- Outputs machine-readable artifacts: yes, but through a legacy mixed-surface contract.
- Handles missing features fail-closed: no.
- Computes net after fees/slippage: yes, but with hardcoded cost models.
- Supports aggression search dimensions needed here: not under current SSOT rules.
- Safe to reuse as-is: no.
- Exact minimal patch if reuse were desired: not a small patch. It would require a redesign around current YAML/Pydantic loaders and explicit CLI contracts.

## Execution Evidence

- `calibrate_mean_reversion_params.py` with current checked-in registry failed closed exactly as expected for DOGE with `SCOPE_INVALID`.
- `calibrate_mean_reversion_params.py` with an explicit offline study registry artifact completed on DOGE and emitted the full artifact set.
- `calibrate_md_amr_weights.py` completed on XRPUSDT, ETHUSDT, and SOLUSDT over their full recorder ranges and emitted the full artifact set.
- `md_amr_integrated_validation.py` succeeded when invoked as a module and wrote summary/report CSV/markdown artifacts.
- `mr_signal_surface_audit.py` still failed because `reports/mean_reversion_real_run_validation_early/run_manifest.json` is missing in the current workspace.
- Direct script entry for `md_amr_integrated_validation.py` and `mr_signal_surface_audit.py` is brittle because intra-repo imports happen before repo-root path bootstrap.

## Validation Performed

- Dry-run current-SSOT MR scope check: DOGE correctly failed closed under the real strategies registry.
- Full-range baseline runs: XRPUSDT md_amr, ETHUSDT md_amr, SOLUSDT md_amr, DOGEUSDT mean_reversion offline candidate.
- Targeted tool tests: `pytest tests/tools/test_mean_reversion_param_calibrator.py tests/tools/test_md_amr_weight_calibrator.py tests/tools/test_md_amr_integrated_validation.py`.
- Result: 14 tests passed.

## Minimal Safe Verdict

The current baseline engines are adequate for Phase 1 baseline replay, but not yet for the full Phase 2 aggression grid. The safe reuse set is the two calibrators. The two legacy forensics tools should not drive Phase 2 work without repair or redesign.
