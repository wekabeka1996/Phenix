# Plan: Create test_backtest_plugin_integration.py

## Goal
Create the file `c:\Users\user\Music\Phenix\apps\reference\domains\alpha_search\tests\test_backtest_plugin_integration.py` with 8 integration tests for `AlphaSearchBacktestPlugin`.

## Steps

1. **Create the test file** at the target path with the exact content the user provided. The file contains:
   - Module docstring describing T2 Backtest Plugin Integration Tests
   - Imports: `pytest`, `unittest.mock.MagicMock`, `AlphaSearchBacktestPlugin`, `get_default_config`, `get_default_system_config`
   - 3 test classes with a total of 8 tests:
     - `TestExtractPayload` (4 tests): `test_message_object`, `test_localbus_dict`, `test_raw_dict`, `test_non_dict_returns_none`
     - `TestFeatureCacheViaLocalBus` (3 tests): `test_feature_cache_populated`, `test_scoring_produces_event`, `test_fail_closed_on_missing_features`
     - `TestMultiProvider` (1 test): `test_multi_provider_scoring`

## Verification
- The target directory `apps\reference\domains\alpha_search\tests\` exists and already has an `__init__.py` and other test files.
- No additional files or changes are needed beyond writing the single test file.
