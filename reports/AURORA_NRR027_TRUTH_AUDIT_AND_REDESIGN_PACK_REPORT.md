# AURORA_NRR027_TRUTH_AUDIT_AND_REDESIGN_PACK REPORT

## Scope

- Requested objective: determine whether live NRR-027 rejects were true fail-closed decisions or overblocking, then implement the smallest justified redesign.
- Non-goals preserved: no geometry retuning, no broad safety-gate refactor, no UNCERTAIN allowlist changes, no blanket disabling of directional sanity.

## Evidence Base

### Runtime artifacts inspected

- `logs/order_log_v1.jsonl`
- `logs/domain_decision_making.log`
- `logs/aurora_core.log.1`
- `logs/aurora_core.log`

### Code and SSOT inspected

- `apps/reference/domains/decision_making/safety_gates.py`
- `apps/reference/domains/decision_making/event_handlers.py`
- `apps/reference/domains/feature_engineering/feature_engineering.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `apps/reference/domains/decision_making/intent_builder.py`
- `apps/reference/config_models.py`
- `config/aurora/domains.yaml`

## Facts

### F1. Exact live NRR-027 contract before redesign

- `NRR-027` fired only when `_check_directional_gate(...)` saw `trend_dir == "UP" && intent_side == "SHORT"` or `trend_dir == "DOWN" && intent_side == "LONG"`.
- `trend_dir` was not sourced from strategist/operator trend state.
- `trend_dir` came from `_delta_price_hist` inside `symbol_states`.
- `_delta_price_hist` was populated only from `features["delta_price"]` in `event_handlers.py`.
- With `config/aurora/domains.yaml` set to `consecutive_bars: 1`, a single non-zero filtered bar delta was sufficient to mark trend as `UP` or `DOWN`.
- `regime_confidence` gate was separate and already passed in the live `NRR-027` cases.

### F2. Fired live case inventory after geometry repair

Six live `ORDER_REJECTED` events with `nrr_code="NRR-027"` were present:

| RID | Symbol | Reject ts | Why |
|---|---|---:|---|
| `aurora_ETHUSDT_1774122301402` | ETHUSDT | 1774122301445 | `SAFETY_GATES:uptrend blocks short` |
| `aurora_ETHUSDT_1774122601677` | ETHUSDT | 1774122601688 | `SAFETY_GATES:uptrend blocks short` |
| `aurora_ETHUSDT_1774122902006` | ETHUSDT | 1774122902012 | `SAFETY_GATES:uptrend blocks short` |
| `aurora_BTCUSDT_1774122902057` | BTCUSDT | 1774122902063 | `SAFETY_GATES:uptrend blocks short` |
| `aurora_ETHUSDT_1774123798001` | ETHUSDT | 1774123798011 | `SAFETY_GATES:uptrend blocks short` |
| `aurora_ETHUSDT_1774124098569` | ETHUSDT | 1774124098580 | `SAFETY_GATES:uptrend blocks short` |

### F3. What the system actually saw in those six cases

For all six cases:

- Aurora kernel emitted a bearish SELL signal before safety deny.
- Structural regime at the Aurora decision point was `LOW_VOLATILITY`.
- Regime confidence was above the live floor of `0.42`.
- The directional hard veto was driven by a positive last filtered `delta_price` bar, not by a directional structural regime.

Observed live slices:

| Case | Regime | Regime conf | Decision score | Last bar `delta_price` used by DM |
|---|---|---:|---:|---:|
| ETH 21:45 | `LOW_VOLATILITY` | 0.6191 | -0.169676 | +1.040 |
| ETH 21:50 | `LOW_VOLATILITY` | above 0.42 | -0.169308 | +0.390 |
| ETH 21:55 | `LOW_VOLATILITY` | above 0.42 | -0.169308 | +0.530 |
| BTC 21:55 | `LOW_VOLATILITY` | 0.6111 | -0.141319 | +5.20 |
| ETH 22:09 | `LOW_VOLATILITY` | above 0.42 | -0.166552 | +0.700 |
| ETH 22:14 | `LOW_VOLATILITY` | above 0.42 | -0.166552 | +0.590 |

### F4. Contract mismatch behind the reject reason

- The reject payload said `uptrend blocks short`.
- The actual runtime contract only proved `one positive filtered bar delta` when `consecutive_bars: 1`.
- No inspected case proved a structural `TREND_UP` regime at the decision point.
- No inspected case proved multi-bar directional confirmation prior to hard veto.

## Inferences

### I1. The live NRR-027 family was overconservative, not truth-faithful

- A bearish Aurora stack with `decision_score` around `-0.14` to `-0.17` was being vetoed by a one-bar positive delta proxy.
- In `LOW_VOLATILITY`, a single positive bar is consistent with a short-lived bounce inside a range and does not justify the stronger semantic claim `uptrend`.
- Therefore the hard veto severity was stronger than the underlying evidence.

### I2. Simple config changes would not have solved the right problem

- Raising `consecutive_bars` from `1` to `2` without redesign would convert many cases from `NRR-027` to `NRR-026` rather than allowing them.
- Raising `min_abs_delta_price` would likewise suppress the trend label, but still keep the fail-closed deny path on ambiguous trend.
- Disabling directional sanity in low-volatility regimes would be broader than justified by the evidence.

## Unproven / Not Claimed

- No claim is made that every future single-bar countertrend bounce should be tradeable.
- No claim is made that all six rejected trades would have been profitable.
- No full live replay or long-horizon PnL validation was run in this package.
- No claim is made that NRR-029 or other downstream guards are perfectly calibrated.

## Verdict

### Per-case classification

- All six inspected NRR-027 live rejects are classified as `LIKELY_FALSE_REJECT` / `LIKELY_OVERBLOCK`.

Reason:

- the system had bearish Aurora intent,
- structural regime was non-directional (`LOW_VOLATILITY`),
- and the hard countertrend veto was triggered by a one-bar positive delta proxy.

## Redesign Candidates Considered

### Rejected

1. `consecutive_bars: 2` only
   - Rejected because it mainly shifts blocks from `NRR-027` to `NRR-026`.

2. Increase `min_abs_delta_price`
   - Rejected because it treats the symptom and still leaves ambiguous-trend fail-closed denial.

3. Disable directional sanity in `LOW_VOLATILITY`
   - Rejected because it is broader than the evidence requires.

### Chosen

`NRR027-REDESIGN-01`: separate trend read from hard-veto severity.

- Keep one-bar directional read for traceability and observability.
- Require repeated same-sign filtered bars before emitting hard `NRR-027` countertrend veto.
- Implemented as additive config `hard_veto_consecutive_bars` with backward-safe default `1`.
- Live SSOT set to `hard_veto_consecutive_bars: 2`.

## Implemented Changes

### Runtime

- Added `hard_veto_consecutive_bars` to `DirectionalSanityConfig`.
- Added `trend_run_length` computation in `safety_gates.py`.
- `NRR-027` now fires only when countertrend condition is present and trailing same-sign filtered delta run length meets `hard_veto_consecutive_bars`.
- Single-bar countertrend reads remain visible in trace via soft allow reasons.

### Observability

- Added `trend_run_length` to allow and deny decision traces.

### SSOT

- `config/aurora/domains.yaml` now sets `hard_veto_consecutive_bars: 2`.

## Validation

### Targeted tests run

1. `pytest tests/integration/test_directional_sanity_sol_downtrend_no_long_open.py`
   - Result: `3 passed`
   - Covers:
     - existing downtrend-long deny remains blocked,
     - one-bar ETH uptick no longer hard-blocks bearish short when veto requires two bars,
     - BTC two-bar uptick still hard-blocks short.

2. `pytest tests/config/test_directional_sanity_ssot_strict_live.py tests/integration/test_price_motion_sanity_blocks_entry.py`
   - Result: `1 passed, 3 skipped`
   - Confirms directional_sanity SSOT strictness still holds.

### Bounded before/after conclusion

- Before: one positive filtered bar could hard-deny bearish shorts as `NRR-027`.
- After: one positive filtered bar is traced but not escalated to hard veto; two-bar confirmation still hard-denies.
- This is a true overblocking reduction, not just a code remap from `NRR-027` to `NRR-026`.

## Garbage-Flood Risk Assessment

- The redesign is bounded because it removes only the one-bar hard-veto escalation.
- Genuine repeated countertrend runs still deny.
- Flash/bleed price-motion guards remain available for stronger adverse movement.
- No evidence from this package suggests the change creates an unbounded garbage-signal flood, but no full live soak was run here.

## BTC Non-Regression Statement

- Bounded BTC regression was validated in synthetic integration form: with two positive BTC bars and `hard_veto_consecutive_bars: 2`, the short is still denied with `NRR-027`.
- Full BTC live replay / production soak was not executed in this package.

## Final Conclusion

The inspected live `NRR-027` rejects were not truth-faithful representations of an established uptrend/downtrend. They were hard vetoes produced by escalating a one-bar `delta_price` sign into a directional block while Aurora itself remained bearish and structural regime remained `LOW_VOLATILITY`.

The minimal justified redesign is to require repeated same-sign bars before hard `NRR-027` countertrend veto, while retaining one-bar directional read for traceability. That redesign has been implemented, validated in bounded tests, and applied in live SSOT as `hard_veto_consecutive_bars: 2`.