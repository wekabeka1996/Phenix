# Calibration Tool Registry

This file records the current calibration class of each calibrator in the repository.

Class is not the same thing as promotability.
Use [config/docs/CALIBRATION_STANDARD_V1.md](../../config/docs/CALIBRATION_STANDARD_V1.md) for the normative governance contract.

| Script | Class | Primary target surface | Operational note |
| --- | --- | --- | --- |
| calibrate_aurora_thresholds.py | production | Aurora assets.<SYMBOL>.signal_threshold.value and assets.<SYMBOL>.regime_thresholds | Use recorder-features-v2 for production-aligned runs with explicit train/validation/forward evaluation, GO_CANDIDATE or NO_GO_CANDIDATE verdicts, and stable artifact emission including candidate_aurora_threshold_overlay.yaml plus validation_metrics.json and forward_metrics.json. For control replays against current live fallback semantics, use --threshold-source-mode live-effective; candidate emission remains fail-closed when the live source is global decision.signal_threshold. aurora-logs remains research-only diagnostic evidence. |
| calibrate_aurora_signal_weights.py | research | Legacy Aurora signal_weights, direction_strength_scoring, feature_neutrals | Legacy surface only. Not the active Aurora production calibration path. |
| calibrate_md_amr_weights.py | production | md_amr.weights plus selected strategy-local md_amr params | Production-aligned MD-AMR calibrator with train/validation/forward evaluation, explicit GO/NO_GO verdicts, overlay-only output, stable artifact emission, and optional selected strategy-local base-param mutation for tooling-only exploration. |
| calibrate_mean_reversion_params.py | production | mean_reversion strategy parameters under asset strategy overlays | Production-aligned Mean Reversion calibrator with train/validation/forward evaluation, explicit GO/NO_GO verdicts, asset-scoped overlay output, and stable artifact emission. |
| calibrate_aurora_regime_params.py | research | Aurora regime overlay search | Research tool for regime overlay exploration. Not the stage-1 Aurora production threshold calibrator. |
| calibrate_objective_stack.py | meta | Stage-2 bundle and objective search over stage-1 outputs | Meta or stage-2 orchestrator. Not a stage-1 production calibrator. |
| calibrate_system_stress_weights.py | production | system_stress.aggregation.weights | Active runtime surface, but current script remains advisory and artifact-light. Promotion still requires standard evidence. |

## Notes

- Production class means active runtime surface alignment, not automatic GO.
- Research class means legacy, exploratory, or insufficiently proven active-surface alignment.
- Meta class means bundle or orchestration tooling above stage-1 surface calibration.
