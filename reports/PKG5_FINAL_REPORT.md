# PKG5 FINAL REPORT

## Executive Summary

PKG-5 succeeded.

The repo now has a technically honest March proxy research harness for future bounded search.

What PKG-5 proved:

- scoring engine selection and fallback state are now artifact-visible,
- ETH+BTC proxy research can be expressed without violating strict config truth,
- the harness can fail closed on scoring fallback,
- the benchmarked proxy runs are artifact-proven quadratic-only on the observed surface.

What PKG-5 did not do:

- it did not run a search grid,
- it did not claim cross-period alpha,
- it did not convert the proxy into a canonical full-universe benchmark.

## Files Created / Updated

Created:

- `reports/RESEARCH_HARNESS_HARDENING_REPORT.md`
- `reports/SCORING_TELEMETRY_SPEC.md`
- `reports/PROXY_UNIVERSE_SPEC.md`
- `reports/HARNESS_BENCHMARK_REPORT.md`
- `reports/PKG5_FINAL_REPORT.md`

Updated:

- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/aurora_scoring_kernel.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/strategies/plugins/aurora_builtin.py`
- `apps/reference/main.py`
- `backtest_engine/reporting.py`
- `tools/backtest/backtest_summarize.py`
- `optimization/backtest_interface.py`
- `optimization/research/__init__.py`
- `optimization/research/proxy_runner.py`
- `scripts/diagnostics/run_research_proxy_backtest.py`
- tests listed in package reports
- `JOURNAL.md`
- `TODO.md`

## Commands Executed

- reference freeze via `git rev-parse HEAD` and `Get-FileHash`
- focused pytest for telemetry + proxy harness
- baseline proxy benchmark on ETH tradable + BTC context
- v1 proxy benchmark on the same proxy with `march_candidate_v1_block_eth_trend_down`
- `tools/backtest/backtest_summarize.py` on both new run reports

## Tests Run

- `tests/domains/decision_making/test_aurora_builtin_plugin.py`
- `tests/domains/decision_making/test_aurora_scoring_telemetry.py`
- `tests/backtest_engine/test_scoring_telemetry_reporting.py`
- `tests/optimization/test_research_proxy_runner.py`

Result:

- `9 passed in 0.47s`

## Runs Executed

- baseline proxy: `20260314_170343`
- v1 proxy: `20260314_172657`

## Top Findings

1. Existing `SelectiveOptimizer` was correctly bypassed; PKG-5 needed a dedicated strict-compatible proxy harness instead of another illegal overlay workaround.
2. Artifact-level scoring telemetry now proves whether the run actually remained on `quadratic_v1`.
3. ETH-only remains invalid; ETH tradable plus BTC context is the first acceptable honest proxy.
4. Real benchmark execution found and surfaced an actual plugin-boundary bug in telemetry export, and that bug is now fixed.
5. Windows shell encoding needed explicit UTF-8 handling for reproducible benchmark execution because runtime logs emit Unicode.

## Package Verdict

Package outcome: **accept**.

PKG-5 clears the harness/readiness blocker identified by PKG-4.

## Recommendation For Next Package

Next package should be:

**PKG-6 — bounded search on the ETH+BTC proxy harness with strict YAML-only search dimensions and artifact-level fallback rejection enabled.**

Rules for that next package:

1. Keep the proxy contract fixed to ETH tradable + BTC context.
2. Keep `fail_on_scoring_fallback` enabled.
3. Search only existing code-backed YAML knobs.
4. Treat Jan/Feb/Q2 claims as out of scope unless separate evidence is produced.