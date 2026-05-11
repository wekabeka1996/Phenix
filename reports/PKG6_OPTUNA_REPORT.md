# PKG6 OPTUNA REPORT

## Status

PKG-6 bounded search completed as a rejection package.

The search was executed honestly on the hardened ETH+BTC proxy, but no distinct completed March candidate was recovered before the study exceeded practical runtime budget.

## What Was Executed

1. The hardened proxy harness was revalidated first through smoke run `20260314_180946`.
2. The bounded search surface was fixed to 6 runtime-backed knobs only.
3. A bounded Optuna study was launched on top of the v1 anchor with fail-closed fallback rejection enabled.
4. The live study proved materially more expensive than the nominal 10-trial budget implied.
5. The study was terminated after recovering the completed March runs that already existed on disk.

## Recovered March Search Runs

- `20260314_181857`
- `20260314_183705`
- `20260314_192436`
- `20260314_201516`
- `20260314_203520`

All five recovered completed runs satisfied the hardened-proxy safety conditions:

- `quadratic_fallback_count = 0`
- `fail_closed_on_scoring_fallback = true`
- proxy lock preserved: `ETHUSDT` tradable, `BTCUSDT` context

## Why No Candidate Was Selected

Every recovered completed March search run had the same resolved `config_hash` as the v1 anchor `20260314_172657`:

- `a593200968fdb4b1c3330c42e27fde50e73bd6da8426eece5cd41aa51b7a2dd1`

The recovered completed runs were therefore not honest distinct candidates. Their March outcomes also collapsed to the same surface as the v1 anchor:

- `+51.38 USDT`
- `+5.1384% ROI`
- `18 trades`
- `~4.08% max DD`
- zero observed quadratic fallbacks

Because the over-budget study was terminated before producing a completed non-duplicate state, there is no honest top-candidate set to promote.

## Package Decision

PKG-6 rejects candidate promotion.

This is not a harness-failure rejection. It is a bounded-search non-signal rejection:

- the hardened proxy worked,
- the fail-closed path stayed clean,
- but recovered completed March trials did not materialize a distinct alpha hint beyond the v1 anchor.

## Artifacts

- `artifacts/pkg6_optuna_trials.csv`
- `artifacts/pkg6_top_candidates.json`