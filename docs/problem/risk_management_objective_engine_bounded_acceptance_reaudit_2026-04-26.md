# Acceptance Re-Audit: Risk Management / Objective Engine Bounded Patch

## Scope

Independent acceptance re-audit of the bounded risk_management + objective_engine audit line.

Explicit non-goals preserved:

- no new features
- no objective_engine refactor
- no risk_score formula change
- no absorption semantics change
- no Kelly / TradeIntent provenance changes
- no execution_position cleanup ownership work

## Verdict

ACCEPTED_WITH_RESIDUALS

The bounded patch is acceptable, behavior-bounded, and contract-safe for the proven defect surface.

One original runtime defect was real and is repaired:

- DailyRiskState init-time parsing of trading.risk.daily.max_drawdown_pct previously reused forgiving _d() and could silently normalize malformed config to Decimal("0")

The repair remains narrow:

- strict parser added only for config-only decimal parsing of max_drawdown_pct
- runtime equity payload coercion via _d() is unchanged
- daily can_open threshold semantics are unchanged for valid config
- no risk_score, absorption, objective_engine, builder, snapshot, or Pydantic config-model semantics changed in this patch

Residuals are non-blocking:

- when the daily gate is disabled and max_drawdown_pct is omitted, DailyRiskState still materializes an inert 0 placeholder; this is not consulted because can_open short-circuits on disabled gate, and the documented contract only requires max_drawdown_pct when enabled
- apps/reference/domains/risk_management/README.md still documents older daily-gate field names; this predates the patch and is not a blocker for accepting the repair

## Diff Review

### Original bounded patch files reviewed

- apps/reference/domains/risk_management/daily_gate.py
- tests/domains/risk_management/test_risk_management_coverage.py
- docs/problem/risk_management_objective_engine_bounded_audit_2026-04-25.md

### Additional acceptance-only change in this re-audit

- tests/domains/risk_management/test_risk_management_coverage.py
  - expanded invalid max_drawdown_pct regression from string-only to string + object via parametrization
- docs/problem/risk_management_objective_engine_bounded_acceptance_reaudit_2026-04-26.md

### Exact semantic diff conclusions

- daily_gate.py: one substantive behavior change in runtime code
  - added _parse_decimal_config()
  - switched DailyRiskState.__init__ max_drawdown_pct parsing from _d(max_dd) to _parse_decimal_config(max_dd, path="risk.daily.max_drawdown_pct") when the field is present
- test_risk_management_coverage.py: original patch added one regression; re-audit expanded that regression to cover object input too
- risk_management_objective_engine_bounded_audit_2026-04-25.md: docs-only artifact, no runtime semantics
- /memories/repo/config_contract_required_vs_default_drift_2026-04-24.md was updated outside the git repo; no git diff exists, but current line 11 records the same DailyRiskState config-ingress lesson

### Confirmed no unrelated codepath changes in this patch slice

`git diff --name-only -- apps/reference/domains/risk_management/risk_management.py apps/reference/domains/objective_engine/** apps/reference/domains/decision_making/gates/objective_gate_evaluator.py apps/reference/config_models.py`

Result: no output

Inference: the current working-tree patch does not modify risk_score formula surfaces, objective_engine, objective gate evaluator, or typed config models.

## FACTS

- config/aurora/trading.yaml defines trading.risk.daily.enabled, max_drawdown_pct, and reset_time_utc.
- config/docs/scoring_passport.md and config/docs/trading_passport.md both state that max_drawdown_pct and reset_time_utc are required when enabled.
- TradingConfig.risk remains Dict[str, Any] in apps/reference/config_models.py, so DailyRiskState's mixed object-root plus dict-leaf access is intentional compatibility rather than proven drift.
- Pre-patch execution of the HEAD version of daily_gate.py produced:
  - invalid_string -> NO_EXCEPTION 0 enabled True
  - invalid_object -> NO_EXCEPTION 0 enabled True
  - missing_enabled -> ConfigContractError
  - missing_disabled -> NO_EXCEPTION 0 enabled False
- Current runtime produced:
  - invalid_string -> ConfigContractError at risk.daily.max_drawdown_pct
  - invalid_object -> ConfigContractError at risk.daily.max_drawdown_pct
  - missing_enabled -> ConfigContractError at risk.daily
- The current patched code still uses _d("0") when max_drawdown_pct is absent, but only on the path where the field is absent; with enabled=True that path is already blocked by the required-fields guard.
- Current can_open logic still short-circuits to allowed=True when _enabled is false before consulting max_drawdown_pct.
- The objective_engine acceptance bundle and adjacent objective gate evaluator bundle pass unchanged.

## INFERENCES

- The original defect was real, reachable, and bounded to config ingestion, not ongoing runtime equity parsing.
- The patch removes silent normalization for malformed present values on the active config path without widening behavior elsewhere.
- The remaining missing-disabled placeholder path is inert under the documented contract and does not invalidate acceptance.
- The patch is behavior-bounded because executable validation plus diff review found no drift outside DailyRiskState config ingress and related tests/docs.

## ASSUMPTIONS

- The current contract statement "required when enabled" is authoritative for max_drawdown_pct and reset_time_utc.
- The git working tree still represents the bounded patch under acceptance, plus the acceptance-only test and report artifacts added in this re-audit.

## UNKNOWNS

- No live exchange or replay corpus was used here to exercise disabled-gate initialization with intentionally partial config outside unit-style probes.
- No broader documentation cleanup was performed for unrelated README drift in risk_management.

## Old vs New Behavior Map

| Scenario | Old behavior | New behavior | Acceptance reading |
| --- | --- | --- | --- |
| enabled=True, max_drawdown_pct="bad" | DailyRiskState initializes, cfg.max_drawdown_pct becomes 0 | ConfigContractError at risk.daily.max_drawdown_pct | defect fixed |
| enabled=True, max_drawdown_pct=object() | DailyRiskState initializes, cfg.max_drawdown_pct becomes 0 | ConfigContractError at risk.daily.max_drawdown_pct | defect fixed |
| enabled=True, max_drawdown_pct missing | ConfigContractError at risk.daily | ConfigContractError at risk.daily | unchanged fail-closed |
| enabled=False, max_drawdown_pct missing | DailyRiskState initializes with inert 0 placeholder | same | residual but non-blocking; can_open returns daily_gate_disabled before threshold use |
| valid enabled config + normal drawdown | initializes and gates normally | same | preserved |
| valid enabled config + drawdown >= threshold | blocks with MAX_DRAWDOWN | same | preserved |

## Suspicious Fallback Search Classification

Search terms reviewed in risk_management: Decimal("0"), except Exception, return D(...), max_drawdown_pct, daily.

### Classified remaining hits

| Location | Classification | Reason |
| --- | --- | --- |
| daily_gate.py::_d | runtime input fallback | Used for portfolio/state payload coercion and safe numeric handling, not config-only max_drawdown_pct parsing anymore |
| daily_gate.py::_fmt_pct, _fmt_usd | unrelated formatting fallback | String formatting only; no gate decision semantics |
| daily_gate.py trading_mode try/except | unrelated runtime compatibility | Controls persistence mode fallback, not drawdown threshold parsing |
| daily_gate.py _save_state/_load_state exception handling | runtime safety fallback | Persistence/corruption recovery, not config normalization |
| daily_gate.py max_drawdown_pct missing + enabled=False | config placeholder residual | Inert because can_open short-circuits when gate disabled |
| risk_management.py AlertManager/fsm/timestamp/absorption parse excepts | runtime safety / telemetry fallback | No config-contract fallback for daily gate threshold parsing |
| risk_management.py decimal zero initializers/clamps | runtime math behavior | Existing formula/clamp logic, unchanged by this patch |
| tests/* fixtures using daily/max_drawdown_pct | test fixture | not runtime |
| docs/* daily hits | unrelated documentation | not runtime |

No remaining active config-path fallback was found for malformed present max_drawdown_pct values.

## Valid Behavior Preservation

Evidence that valid behavior is preserved:

- current can_open still computes drawdown as `(1 - equity_now / equity_open) * 100`
- current can_open still blocks at `dd >= max_drawdown_pct`
- existing drawdown behavior test still passes
- full risk_management coverage file still passes
- absorption branch tests still pass without code changes in risk_management.py
- objective_engine and adjacent gate evaluator bundle still passes unchanged

## Invalid Behavior Now Fails Closed

### Pre-patch executable proof

```text
invalid_string NO_EXCEPTION 0 enabled True
invalid_object NO_EXCEPTION 0 enabled True
missing_enabled ConfigContractError CONFIG_CONTRACT_VIOLATION: Path='risk.daily' Reason='Daily gate config incomplete (max_drawdown_pct, reset_time_utc required)'
missing_disabled NO_EXCEPTION 0 enabled False
```

### Current executable proof

```text
invalid_string ConfigContractError CONFIG_CONTRACT_VIOLATION: Path='risk.daily.max_drawdown_pct' Reason='Invalid decimal config value: 'bad''
invalid_object ConfigContractError CONFIG_CONTRACT_VIOLATION: Path='risk.daily.max_drawdown_pct' Reason='Invalid decimal config value: <object object at 0x...>'
missing_enabled ConfigContractError CONFIG_CONTRACT_VIOLATION: Path='risk.daily' Reason='Daily gate config incomplete (max_drawdown_pct, reset_time_utc required)'
```

## Tests Run With Exact Output

### Expanded invalid-config regression

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py::test_daily_state_invalid_max_drawdown_pct_raises -q

collected 2 items
..

2 passed in 0.88s
```

### Full risk_management coverage file

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py -q

collected 23 items
.......................

23 passed in 0.97s
```

### Narrowed risk_management bundle

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py::test_risk_management_methods_and_validation_branches tests/domains/risk_management/test_risk_management_coverage.py::test_test_risk_thresholds_default_and_error_paths tests/domains/risk_management/test_risk_management_coverage.py::test_daily_state_invalid_max_drawdown_pct_raises tests/domains/risk_management/test_daily_gate_drawdown_8pct.py::test_daily_gate_uses_equity_cross_usdt_and_blocks_at_8pct_drawdown -q

collected 5 items
.....

5 passed in 0.85s
```

### Absorption branch checks

```text
pytest tests/domains/risk_management/test_risk_management_coverage.py::test_risk_score_high_and_price_invalid_paths tests/domains/risk_management/test_risk_management_coverage.py::test_risk_debug_override_emit_exception_and_clamp_paths -q

collected 2 items
..

2 passed in 0.96s
```

### objective_engine + adjacent objective gate evaluator bundle

```text
pytest tests/apps/reference/domains/objective_engine/test_objective_engine.py tests/apps/reference/domains/objective_engine/test_runtime.py tests/apps/reference/domains/objective_engine/test_realized_objective.py tests/domains/decision_making/test_objective_gate_evaluator.py -q

collected 37 items
.....................................

37 passed in 1.60s
```

## Docs / Passports

- No passport update is required for this patch itself.
- Existing config passports already describe the active contract:
  - config/docs/scoring_passport.md says max_drawdown_pct and reset_time_utc are required when enabled
  - config/docs/trading_passport.md documents max_drawdown_pct and the `dd_pct >= max_drawdown_pct` gate semantics
  - config/docs/Gemini/trading_passport_gemini.md already describes the same daily gate fields
- Unrelated doc drift remains in apps/reference/domains/risk_management/README.md, which still names older daily-gate field labels. That drift predates this patch and does not block acceptance.

## Remaining Risk

- The disabled-gate placeholder path could be made stricter in a future cleanup if the repo ever decides that omitted max_drawdown_pct should be rejected even when the gate is disabled. That would be a separate contract decision, not a requirement for this patch.
- objective_engine snapshot reversal/overshoot semantics remain a separate proof task but were not touched here.

## Closure

This closes the bounded risk_management / objective_engine audit line for the proven defect scope.

Why it closes:

- the only confirmed runtime defect is real and repaired
- regression coverage now proves old behavior would fail the new test
- valid daily-gate behavior is preserved
- no risk_score or objective_engine semantic drift was introduced

Why the verdict is not plain ACCEPTED:

- there is one non-blocking disabled-only placeholder residual on the config path
- there is unrelated pre-existing README drift outside the patch itself
