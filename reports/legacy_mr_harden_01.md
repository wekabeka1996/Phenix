# LEGACY-MR-HARDEN-01 Report

**Date:** 2026-01-12
**Status:** SUCCESS

## 1. Summary

We successfully cleaned up `tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py` by removing contract tests for the **deprecated Tick Path**.
The `MeanReversionHandler` architecture has shifted to **T2B-03 CMD Orchestration** (Bar Path), rendering tick-level input validation tests (like dropped ticks counters) locally dead and misleading.

## 2. Changes

- **Deleted** tests that verified `ticks_dropped_*` counters incrementing on invalid ticks. Since `MeanReversionHandler._on_market_tick` is now a no-op (`pass`), these counters are never updated, and the logic they tested is handled upstream by Feature Engineering / Bar Aggregator.
  - `test_tick_drops_invalid_price_and_does_not_call_on_tick`
  - `test_tick_drops_missing_ts_and_does_not_call_on_tick`
  - `test_out_of_order_tick_dropped_and_counter_incremented`
  - `test_bars_completed_counts_once_per_bar_end_ts`
  - `test_bar_logging_exception_increments_counter_and_logs_warning`
- **Kept** configuration activation tests which remain valid:
  - `test_mr_activation_assigned_enabled_true_ok`
  - `test_mr_activation_assigned_enabled_false_raises`
  - `test_mr_no_assignments_enabled_true_stays_disabled`
- **Kept** unit tests for `normalize_ts_ms` utility function.

## 3. Rationale

The removed tests were enforcing invariants on an input channel (`_on_market_tick`) that is no longer used for decision making. Keeping them would require "faking" the tick path or hacking the handler to process ticks only for testing, which creates "Illusion of Coverage". By removing them, we ensure tests only cover the actual production path (CMD).

## 4. Verification

`pytest -v tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py` passed with 11/11 tests green.
