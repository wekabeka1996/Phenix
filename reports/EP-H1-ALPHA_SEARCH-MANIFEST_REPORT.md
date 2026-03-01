# EP-H1-ALPHA_SEARCH-MANIFEST REPORT

## Summary
Implemented required-feature manifest propagation for `ta_ensemble` and strict missing-feature gating in alpha_search plugin flow.

## Files changed
- `apps/reference/domains/alpha_search/ensemble.py`
- `apps/reference/domains/alpha_search/backtest_plugin.py`
- `tests/domains/alpha_search/test_ta_ensemble_manifest.py`
- `tests/domains/alpha_search/test_backtest_plugin.py`
- `JOURNAL.md`
- `TODO.md`

## Contract/result
- `EnsembleModel.get_required_features()` now provides non-empty union of child model requirements.
- When required features are missing, ensemble returns:
  - `score=0.0`
  - `confidence=0.0`
  - `why` includes `missing_features`.
- Backtest plugin now skips providers with missing required features and emits monitoring via `dlog`.

## Validation commands
- `pytest -q tests/domains/alpha_search/test_ta_ensemble_manifest.py` → **2 passed**
- `pytest -q tests/domains/alpha_search/test_backtest_plugin.py -k "missing or ensemble"` → **1 passed**
