# Apps Reference Layer Remediation Plan

## Summary
This remediation cleans `apps/reference/`, migrates framework-grade modules to `vfoundation`, removes string-to-Decimal hot-path parsing, and restructures `main.py` around a Builder/Factory runtime.

Execution is atomic with validation gates after each step, and `docs/docs_vfoundation/PROGRESS_LOG.md` is updated after each step.

## Public API / Interface / Type Changes
1. Add canonical framework modules:
- `vfoundation/dr/dr_loader.py`
- `vfoundation/core/retry_scheduler.py`

2. Keep compatibility shims for one phase:
- `apps/reference/dr_loader.py` becomes a thin deprecated re-export wrapper.
- `apps/reference/retry_scheduler.py` becomes a thin deprecated wrapper exposing `RetryScheduler` and `emit_compat`.

3. Retry scheduler constructor update:
- `on_no_loop: Callable[[], None] | None = None` for metric DI in framework module.

4. Config type changes:
- In `apps/reference/config_models.py`, change precision fields from `str` to `Decimal` with pre-validation coercion.
- Apply to both `InstrumentPrecisionSpec` and `InstrumentSpec`.

5. Config SSOT extension:
- Add typed config flag for debug event listener.
- Remove ad-hoc env bypasses from `main.py`.

## Execution Steps
1. Create baseline, run:
   - `pytest tests/`
   - `python -m mypy apps vfoundation tests` (conditional when available)
2. Relocate dead/debug scripts from `apps/reference` to `scripts/reproductions/`.
3. Migrate `dr_loader` into `vfoundation/dr` and keep app shim.
4. Migrate `retry_scheduler` into `vfoundation/core` with DI hook, keep app shim.
5. Remove string-to-Decimal hot paths and type precision fields as `Decimal`.
6. Add `domain_builder.py`, `async_runtime.py`, and `backtest_runner.py`; slim `main.py`.
7. Enforce SSOT in `main.py` (remove direct env bypasses).
8. Final sweep and full validation gates.

## Validation
- `pytest tests/` after each atomic step.
- `python -m mypy apps vfoundation tests` when mypy is installed.

## Definition of Done
- `apps/reference/` has zero `reproduce_*.py` files.
- `dr_loader.py` and `retry_scheduler.py` canonical implementations live in `vfoundation`.
- `config_models.py` precision specifiers are strongly typed `Decimal`.
- `main.py` follows builder/factory composition and safe async loop boundaries.
- Imports and full tests remain green.
