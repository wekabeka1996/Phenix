# PLAN — Risk Management Domain Remediation

Date: 2026-02-24
Branch: `backtest_1`
Scope: `apps/reference/domains/risk_management/*` + contract tests

## Goals

1. Preserve zero-regression for `tests/vfoundation`.
2. Enforce fail-closed behavior on invalid input/config/errors.
3. Restore traceability (`rid` continuity) for risk pipeline.
4. Align emitted payload contract with schema.
5. Remove silent numeric coercion in risk hot path.
6. Prevent intraday state amnesia after state-file corruption.

## RCA Summary (Step 1)

- `on_features_calculated` ignores `event.rid` and emits without `rid` passthrough.
- Emitted `risk_parameters` payload does not match `risk_assessment_v1.json` requirements.
- `_to_dec` swallows conversion errors and returns `Decimal("0")`.
- `DailyRiskState` resets after JSON corruption and re-anchors equity intraday, reopening gate incorrectly.
- `DailyRiskState` mutates shared state without lock.

## Refactoring Strategy (Atomic, TDD-first)

### Wave A — RID propagation

- Add RED test: emitted `EVT:RISK_ASSESSMENT_COMPLETED` must carry exact input `event.rid`.
- Implementation:
  - In `RiskManagement.on_features_calculated`, remove local `uuid` generation.
  - Extract `rid = event.rid` and pass to `fsm.emit(..., rid=rid)`.
  - Keep fail-closed catch block unchanged.
- Green criteria:
  - New RID test passes.
  - Existing `tests/vfoundation` remain green.

### Wave B — Schema alignment

- Add RED test: emitted payload validates against `risk_assessment_v1.json`.
- Implementation:
  - Update `risk_assessment_v1.json`:
    - include `risk_score` as allowed numeric field;
    - keep `is_trading_allowed` required;
    - make `kelly_fraction`, `cvar_limit_usd`, `max_drawdown_percent` optional because they are computed downstream.
  - Ensure runtime payload still includes `is_trading_allowed` and `risk_score` on normal path.
- Green criteria:
  - Contract test passes against JSON schema.
  - No schema-level rejection when validator is enabled.

### Wave C — Thread safety in `DailyRiskState`

- Add RED test: class exposes a lock and state operations are lock-protected (behavioral check via concurrent updates and stable, non-crashing execution).
- Implementation:
  - Inject `self._lock = threading.Lock()` in `DailyRiskState.__init__`.
  - Guard state mutation/read methods with lock:
    - `reset`, `_save_state`, `_load_state`, `_maybe_reset`, `on_portfolio`, `can_open`, `reference_equity` setter.
- Green criteria:
  - New thread-safety tests pass.
  - Existing daily gate tests pass unchanged.

### Wave D — State amnesia fix after corruption

- Add RED test: corrupted state file must not permit same-day re-anchoring and must remain blocked until next reset window/day.
- Implementation:
  - On `_load_state` corruption, set a strict fail-closed recovery mode flag (e.g. `_recovery_required = True`).
  - Pin `_last_reset_date` to active trading date and keep `equity_open=0` to block intraday opens.
  - In `on_portfolio`, skip re-anchor while recovery flag is active.
  - Clear recovery flag only after next trading-day reset (via `_maybe_reset`).
- Green criteria:
  - Corruption no longer causes intraday gate reopen.

### Wave E — Strict Decimal conversion

- Add RED test: `_to_dec("bad")` raises; `_to_dec(None)` raises.
- Implementation:
  - Replace permissive `_to_dec` with strict validator that raises `ValueError`/`TypeError`/`decimal.InvalidOperation`.
  - Keep fail-closed behavior by relying on existing `on_features_calculated` exception boundary.
- Green criteria:
  - Invalid numeric data blocks trading path rather than silently becoming zero.

## Verification Protocol

After each wave:

1. Run targeted tests for the wave.
2. Run `pytest tests/vfoundation -q` (zero-regression invariant).
3. Append status to `docs/docs_vfoundation/PROGRESS_LOG.md`.

Final verification:

- Domain tests:
  - `tests/domains/risk_management/*`
- vFoundation gate:
  - `pytest tests/vfoundation -q`
- Optional full run (if time):
  - `pytest --maxfail 0`

## Non-goals in this remediation

- No migration to Redis/WAL in this patch series.
- No broad refactor of downstream `decision_making` sizing logic.
- No unrelated API redesign outside `risk_management` contract surface.
