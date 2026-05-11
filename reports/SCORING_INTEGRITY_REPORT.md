# SCORING INTEGRITY REPORT

## Scope

- Research label: MARCH / SIDE B / DEGRADED PARTIAL-UNIVERSE.
- Reference artifacts:
  - baseline March run: `20260314_041537`
  - v1 reference run: `20260314_041758`
  - March anchor bundle: `20260312_132130`

## Phase 0 Freeze

- Reference commit: `cf074c7229252aaca83aed7dc70331115018866d`
- Frozen file hashes:
  - `config/aurora/strategies.yaml` → `67107C2528F58FC2EB61A20A33C62E52FCF0395A449DC88571EC9EF4112E3CC1`
  - `config/aurora/strategies/aurora.yaml` → `9760D13D91EF101E2AA502C5629D8A327A2A77AA0B7AED077871842963B97FB7`
  - `scripts/diagnostics/run_single_backtest.py` → `33DF421F8DF79AD807A5C29E48D6C611E7073DF20BE59BCE1B56CF47F7992273`
- Reference launcher command family:
  - `python scripts/diagnostics/run_single_backtest.py --side B --start 2024-03-01 --end 2024-03-31`
  - `python scripts/diagnostics/run_single_backtest.py --side B --start 2024-03-01 --end 2024-03-31 --overlay-yaml config/overlays/march_candidate_v1_block_eth_trend_down.yaml`

## Code Path Audit

### Observed routing

Current quadratic routing is controlled by `strategies.aurora.decision.scoring_version` in `config/aurora/strategies/aurora.yaml` and loaded in `apps/reference/domains/decision_making/aurora_config_loader.py`.

Current runtime behavior:

1. `aurora_config_loader.py` activates `QuadraticScoringKernel` when `scoring_version == "quadratic"`.
2. `aurora_decision.py` calls `self.scoring_kernel_cls.compute(...)`.
3. If that call raises and `self.scoring_kernel_cls is QuadraticScoringKernel`, runtime logs:
   - `QUADRATIC_FALLBACK: ... falling back to AuroraScoringKernel (local only)`
4. It then retries locally via `AuroraScoringKernel.compute(...)`.

This is a real fail-open path, not dead code.

## Log Scan Results

### Fallback events

Search performed across current runtime logs:

- pattern: `QUADRATIC_FALLBACK|FALLBACK ALSO FAILED`
- files searched: `logs/*.log`, `logs/*.log.*`

Observed result:

- `QUADRATIC_FALLBACK`: zero observed matches
- `FALLBACK ALSO FAILED`: zero observed matches

### Kernel engine diagnostics

Search performed across available March runtime windows in `logs/aurora_core.log`.

Sample observed lines show:

- `KERNEL_DIAG: engine=quadratic_v1 ...`

Window count for the two March reference run windows:

- observed `quadratic_v1` lines: `671`
- observed non-quadratic engine labels: none in the scanned window set

## Artifact Limitation

Current backtest run bundles do **not** persist fallback counts in `result.json`, summary JSON, or manifest metadata.

Implication:

- scoring integrity is only log-observed, not bundle-proven.
- package conclusion is therefore: **zero observed fallback contamination in available March logs, but no artifact-level fallback counter exists yet**.

## Contamination Verdict

- Code-path contamination risk: **real** because fail-open fallback exists.
- Observed contamination in available March logs: **zero**.
- Status classification for PKG-4: **zero observed contamination, but not artifact-hardened**.

## Research Consequence

Phase 1 gate is treated as passed with an explicit caveat:

- bounded search is not blocked by observed fallback contamination;
- however, future research should add artifact-level fallback accounting or a fail-closed research mode before larger-scale search packages.

## Additional Harness Finding

The existing `SelectiveOptimizer` research path is not currently safe to reuse unchanged on this repo truth.

Reason:

- it injects `trading.symbols_to_track` through overlay,
- current strict config contract rejects that field as an SSOT violation during `ConfigLoader.load_config()`.

This is not a scoring-integrity blocker, but it is a real Phase 4 execution-path blocker for off-the-shelf Optuna research tooling.