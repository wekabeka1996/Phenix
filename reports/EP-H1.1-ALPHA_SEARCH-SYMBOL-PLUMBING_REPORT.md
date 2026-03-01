# EP-H1.1-ALPHA_SEARCH-SYMBOL-PLUMBING REPORT

## Summary
Fixed alpha_search regression where symbol plumbing tests broke after stricter manifest gating changes.

## Files changed
- `apps/reference/domains/alpha_search/ensemble.py`
- `apps/reference/domains/alpha_search/backtest_plugin.py`

## Root cause
- `EnsembleModel.generate_signal()` hard-failed on any missing required feature before calling child models, which bypassed symbol propagation in partial-feature paths.
- Plugin missing-feature gating skipped all providers, including aurora adapter paths expected to emit fail-closed scores.

## Fix
1. Ensemble missing-feature zero signal now applies only when feature payload is fully empty (`features={}`), preserving partial-feature plumbing behavior.
2. Backtest plugin keeps skip+monitor behavior for `ta_ensemble`/ensemble providers.
3. For non-ensemble providers with missing required features and `fail_closed=True`, plugin emits fail-closed score instead of silent skip.

## Validation commands
- `pytest -q tests/domains/alpha_search/test_ensemble_features_plumbing.py -k symbol_passed -vv` → **1 passed**
- `pytest -q tests/domains/alpha_search --maxfail=1` → **53 passed**
