# ALPHA SEARCH EXPERIMENT MATRIX

## Reference State

- Full-surface baseline reference: `20260314_041537`
- Full-surface regime-first reference: `20260314_041758`
- March anchor bundle: `20260312_132130`

## Experiment Arms

| Arm | Config surface | Hypothesis | Success criteria | Failure criteria |
| --- | --- | --- | --- | --- |
| ARM 0 | Current side B SSOT | Control | Reproduces current March loss behavior | Any mismatch with known March reference behavior |
| ARM 1 | v1 coarse ETH `TREND_DOWN` block | Regime/context-first anchor | Preserves March DD compression and positive/near-flat outcome | Reintroduces ETH TREND_DOWN toxicity or collapses into artifact triviality |
| ARM 2 | Preserve current regime surface; tune only Family B subset | Scoring-first | Improves March score quality without killing trade count or relying on v1 regime block | Still dominated by ETH TREND_DOWN toxicity or only wins by collapsing participation |
| ARM 3 | Start from v1; add tiny Family B refinement | Mixed minimal | Beats or matches v1 while retaining its drawdown compression | Gives back v1 drawdown benefit without clear compensating robustness |

## Metrics That Matter

Primary metrics:

- PnL / ROI
- max drawdown
- total trades / closed trades
- Sharpe / alpha score

Anti-degenerate checks:

- reject zero-trade or near-zero-trade triviality
- reject giant PnL with ugly drawdown
- reject winners that simply delete all participation
- inspect whether ETH TREND_DOWN toxicity remains or vanishes causally

## Practical Execution Surface

### Full-surface truth

The package respects full March side B baseline/v1 reference artifacts.

### Search execution proxy

For actual search execution, the smallest honest runtime proxy identified was:

- BTC tracked as anchor context
- ETH as the only active Aurora trading symbol

Why:

- ETH-only proxy collapses into zero trades because macro-resid readiness fails when BTC anchor context is removed.
- ETH+BTC proxy remains causally aligned with the dominant March loss engine while keeping runtime materially below full side B.

## Planned Search Budget

Minimal honest budget if Phase 4 were executed:

- scoring-first family: tiny bounded Optuna budget
- mixed family: tiny bounded Optuna budget
- fixed references: baseline and v1

Package verdict:

- the matrix is methodologically valid;
- actual bounded search execution was rejected in this package because the search harness and compute budget were not yet honest enough for Phase 4 + Phase 5 completion.