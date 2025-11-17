# TODO: Active Tasks

## ✅ COMPLETED: Quick Profit $2 Feature (2025-11-12)

- [x] **QUICK_PROFIT_V1**: Implement $2 quick profit closure → DONE [2025-11-12]
  - ✅ Config structure verified in `configs/master_config_v1.yaml`
  - ✅ Schema structure verified in `config/_schemas/trading.yaml`
  - ✅ ManageFlowFSM implementation confirmed (`_check_quick_profit()`)
  - ✅ Priority highest execution confirmed in `_check_rules()`
  - ✅ MetricsCollector integration confirmed (`record_quick_profit_close()`)
  - ✅ ExecPosFSM logging confirmed (QUICK_PROFIT_HIT)
  - ✅ Unit tests created and passing (6/6) in `tests/test_quick_profit_feature.py`
  - ✅ JOURNAL.md updated with implementation details
  - ✅ PR: [FSMP-QP-V1] feat(manage): validate quick profit $2 feature

---

# TODO: Regime Detector Domain Enhancement ✅ **COMPLETED**

## Phase 1: Conformance & Compatibility ✅ COMPLETED

### Schema & Event Compatibility Fixes
- [x] **EVT:REGIME_DETECTED Event Schema Update**
  - Location: `apps/reference/domains/regime_detector/regime_detector.py:440-445`
  - Change: Introduce primary field `model`
  - Change: Convert `confidence` to `float` in event payload
  - Add temporary `source_model` field for backward compatibility
  - Emit events only when regime is detected (no uncertainty events)

- [x] **Regime Naming Standardization**
  - Location: `apps/reference/domains/regime_detector/regime_detector.py` (_detect_sideways method)
  - Change: Rename "MEAN_REVERSION" to "SIDEWAYS" in output events
  - Change: Set `model` to `sideways_v1` (or similar) when this regime fires
  - Change: Standardize config parameter name to `deviation_threshold` to match docs

### Tests & Documentation Updates
- [x] **Test Suite Synchronization**
  - Location: `tests/domains/test_regime_detector.py`
  - Update assertions to check for `model` field presence
  - Verify SIDEWAYS regime naming in tests
  - Add tests for float confidence type

- [x] **Documentation Updates**
  - Location: `API_DEPENDENCIES.md`, `EVENTS.md`
  - Update event schema documentation for float confidence
  - Document `model` as primary field, `source_model` as deprecated
  - Update regime naming from MEAN_REVERSION to SIDEWAYS

## Phase 2: Reliability & Robustness ✅ COMPLETED

### Configuration Management
- [x] **Config Object Implementation**
  - Create new `config.py` file in regime_detector domain
  - Implement dataclasses for all models (SmaTrendConfig, VolatilityConfig, SidewaysConfig) with validation
  - Add backward compatibility for deprecated config names (short_period, sma_short_period)
  - Add deprecation warnings for old parameter names

- [x] **Safe Decimal Parsing**
  - Location: `apps/reference/domains/regime_detector/regime_detector.py:220-230`
  - Wrap Decimal conversions in try-except blocks
  - Add `WARNING` level logging for parsing failures
  - Skip events on parsing errors instead of crashing

### State Management
- [x] **LRU Cache Implementation**
  - Replace defaultdict with OrderedDict-based LRU cache
  - Set max_active_symbols=512 default
  - Implement ttl_seconds=None (no automatic expiration)
  - Add configuration options for cache parameters

## Phase 3: Refactoring & Simplification ✅ COMPLETED

### Code Cleanup
- [x] **Remove Fallback Indicator Logic**
  - Delete `_price_buf`, `_tr_buf`, `_atr_buf` buffers
  - Remove all related calculation code
  - Simplify component state to only essential data
  - Remove allow_fallback_indicators parameter entirely

- [x] **Remove Unused LRU Cache**
  - Delete LRUCache class entirely (no per-symbol state maintained)
  - Remove related imports (OrderedDict, time)
  - Clean up unused code paths

- [x] **Clean Dead Code**
  - Remove legacy backward compatibility fields (sma_short_period, atr_period, etc.)
  - Remove unused imports and type hints
  - Simplify __init__ method

### Architecture Improvements
- [x] **Handle Event Decomposition**
  - Split handle_event into private methods:
    - `_detect_volatility()`
    - `_detect_sideways()`
    - `_detect_trend()`
  - Improve code readability and testability
  - Isolate model detection logic

- [x] **Configuration Constants Extraction**
  - Move all magic numbers from confidence calculation logic
  - Create appropriate Config dataclass fields
  - Ensure all numerical constants are configurable
  - Add validation for configuration ranges

- [x] **Typed Config Integration**
  - Replace manual config parsing with typed dataclass access
  - Update all methods to use self.config.models.* instead of dict access
  - Fix config structure (models as object with attributes, not dict)
  - Ensure backward compatibility with from_dict/from_object

### Testing Enhancements
- [x] **UNCERTAIN Non-Emission Test**
  - Add test case to verify events are not emitted when all models return UNCERTAIN
  - Ensure specification compliance (no noise from uncertain signals)
  - Test covers all regime detection models

## Implementation Notes

- **Priority Order**: Phase 1 (compatibility) → Phase 2 (reliability) → Phase 3 (refactoring)
- **Backward Compatibility**: Maintain source_model field temporarily for migration
- **Testing**: All changes must pass existing test suite
- **Documentation**: Update all relevant docs before Phase 1 completion
- **Risk Assessment**: Phase 1 changes are low-risk, Phase 3 changes are high-impact refactoring

## Success Criteria ✅ ALL MET

- [x] All existing tests pass
- [x] Event schema matches documentation
- [x] SIDEWAYS regime properly named in outputs
- [x] Confidence values are float type in events
- [x] No crashes on invalid input data
- [x] No per-symbol state stored; no memory growth risk
- [x] Code complexity reduced through decomposition
- [x] All magic numbers moved to configuration
- [x] Typed config fully integrated
- [x] Dead code removed
- [x] UNCERTAIN events not emitted (specification compliance)
- [x] Model names unversioned in primary field

## Domain Status: ✅ **PRODUCTION READY**

**Completion Date**: 2025-11-09
**Total Duration**: 180 minutes
**Files Modified**: 3 (regime_detector.py, config.py, test_regime_detector.py)
**Tests Passing**: 7/7 (including new UNCERTAIN test and versioning guard)
**Research Gaps Resolved**: 6/6
**Next Domain**: Ready for execution_position domain enhancements

## Phase 1: Conformance & Compatibility ✅ COMPLETED

### Schema & Event Compatibility Fixes
- [x] **EVT:REGIME_DETECTED Event Schema Update**
  - Location: `apps/reference/domains/regime_detector/regime_detector.py:440-445`
  - Change: Introduce primary field `model`
  - Change: Convert `confidence` to `float` in event payload
  - Add temporary `source_model` field for backward compatibility
  - Emit events only when regime is detected (no uncertainty events)

- [x] **Regime Naming Standardization**
  - Location: `apps/reference/domains/regime_detector/regime_detector.py` (_detect_sideways method)
  - Change: Rename "MEAN_REVERSION" to "SIDEWAYS" in output events
  - Change: Set `model` to `sideways_v1` (or similar) when this regime fires
  - Change: Standardize config parameter name to `deviation_threshold` to match docs

### Tests & Documentation Updates
- [x] **Test Suite Synchronization**
  - Location: `tests/domains/test_regime_detector.py`
  - Update assertions to check for `model` field presence
  - Verify SIDEWAYS regime naming in tests
  - Add tests for float confidence type

- [x] **Documentation Updates**
  - Location: `API_DEPENDENCIES.md`, `EVENTS.md`
  - Update event schema documentation for float confidence
  - Document `model` as primary field, `source_model` as deprecated
  - Update regime naming from MEAN_REVERSION to SIDEWAYS

## Phase 2: Reliability & Robustness ✅ COMPLETED

### Configuration Management
- [x] **Config Object Implementation**
  - Create new `config.py` file in regime_detector domain
  - Implement dataclasses for all models (SmaTrendConfig, VolatilityConfig, SidewaysConfig) with validation
  - Add backward compatibility for deprecated config names (short_period, sma_short_period)
  - Add deprecation warnings for old parameter names

- [x] **Safe Decimal Parsing**
  - Location: `apps/reference/domains/regime_detector/regime_detector.py:220-230`
  - Wrap Decimal conversions in try-except blocks
  - Add `WARNING` level logging for parsing failures
  - Skip events on parsing errors instead of crashing

### State Management
- [x] **LRU Cache Implementation**
  - Replace defaultdict with OrderedDict-based LRU cache
  - Set max_active_symbols=512 default
  - Implement ttl_seconds=None (no automatic expiration)
  - Add configuration options for cache parameters

## Phase 3: Refactoring & Simplification ✅ COMPLETED

### Code Cleanup
- [x] **Remove Fallback Indicator Logic**
  - Delete `_price_buf`, `_tr_buf`, `_atr_buf` buffers
  - Remove all related calculation code
  - Simplify component state to only essential data
  - Remove allow_fallback_indicators parameter entirely

- [x] **Remove Unused LRU Cache**
  - Delete LRUCache class entirely (no per-symbol state maintained)
  - Remove related imports (OrderedDict, time)
  - Clean up unused code paths

- [x] **Clean Dead Code**
  - Remove legacy backward compatibility fields (sma_short_period, atr_period, etc.)
  - Remove unused imports and type hints
  - Simplify __init__ method

### Architecture Improvements
- [x] **Handle Event Decomposition**
  - Split handle_event into private methods:
    - `_detect_volatility()`
    - `_detect_sideways()`
    - `_detect_trend()`
  - Improve code readability and testability
  - Isolate model detection logic

- [x] **Configuration Constants Extraction**
  - Move all magic numbers from confidence calculation logic
  - Create appropriate Config dataclass fields
  - Ensure all numerical constants are configurable
  - Add validation for configuration ranges

- [x] **Typed Config Integration**
  - Replace manual config parsing with typed dataclass access
  - Update all methods to use self.config.models.* instead of dict access
  - Fix config structure (models as object with attributes, not dict)
  - Ensure backward compatibility with from_dict/from_object

### Testing Enhancements
- [x] **UNCERTAIN Non-Emission Test**
  - Add test case to verify events are not emitted when all models return UNCERTAIN
  - Ensure specification compliance (no noise from uncertain signals)
  - Test covers all regime detection models

## Implementation Notes

- **Priority Order**: Phase 1 (compatibility) → Phase 2 (reliability) → Phase 3 (refactoring)
- **Backward Compatibility**: Maintain source_model field temporarily for migration
- **Testing**: All changes must pass existing test suite
- **Documentation**: Update all relevant docs before Phase 1 completion
- **Risk Assessment**: Phase 1 changes are low-risk, Phase 3 changes are high-impact refactoring

## Success Criteria ✅ ALL MET

- [x] All existing tests pass
- [x] Event schema matches documentation
- [x] SIDEWAYS regime properly named in outputs
- [x] Confidence values are float type in events
- [x] No crashes on invalid input data
- [x] No per-symbol state stored; no memory growth risk
- [x] Code complexity reduced through decomposition
- [x] All magic numbers moved to configuration
- [x] Typed config fully integrated
- [x] Dead code removed
- [x] UNCERTAIN events not emitted (specification compliance)
- [x] Model names unversioned in primary field</content>
<parameter name="filePath">c:\Users\user\Music\Phenix\TODO.md
