# R7B SIDECAR RUNTIME OBSERVATION REPORT

**Package**: R7B - Peak-Giveback Sidecar Runtime Observation Audit
**Date**: 2026-04-23
**Mode**: bounded runtime observation only
**Scope**: determine, from real runtime evidence, whether the new peak-giveback Sidecar path is behaving correctly in live/testnet operation

---

## Problem Framing

This audit does not redesign the package and does not re-litigate the R7A code review. The only question is whether the post-restart runtime slice proves correct live behavior for the new peak-giveback Sidecar path.

The controlling implementation remains:

- `apps/reference/domains/execution_position/position_policy_sidecar.py`
- `config/aurora/domains.yaml`
- `apps/reference/domains/execution_position/schemas/cmd_position_policy_sidecar_close_request_v1.json`

The runtime audit is bounded to observed evidence, primarily `logs/trade_lifecycle.jsonl`, with secondary checks in `logs/domain_execution_position.log*`, `logs/order_log_v1.jsonl`, `logs/aurora_core.log*`, and `logs/shadow_critical_event_journal_v1.jsonl`.

Observation window from sidecar runtime evidence:

- first sidecar row: `ts_ms=1776883274831`
- last sidecar row: `ts_ms=1776958534115`
- observed slice length: about `20.9h`

---

## FACTS

### F1: Sidecar activation after restart is directly proven

`logs/trade_lifecycle.jsonl` starts with:

- `event_type=POSITION_POLICY_SIDECAR_MODE_ACTIVE`
- `symbol=__DOMAIN__`
- `ts_ms=1776883274831`
- `mode=enable`
- `evaluation_mode=bounded_soft_close_policy`
- `reason_codes=["sidecar_initialized"]`

This is direct restart-boundary proof that the Sidecar booted and entered active mode in the observed slice.

### F2: Standard sidecar evaluation path definitely ran at runtime

Aggregated counts from `logs/trade_lifecycle.jsonl`:

- `POSITION_POLICY_SIDECAR_MODE_ACTIVE = 1`
- `POSITION_POLICY_SIDECAR_EVALUATED = 1013`
- `POSITION_POLICY_SIDECAR_SCORES = 1013`
- `POSITION_POLICY_SIDECAR_SUPPRESSED = 99391`

This proves that the normal Sidecar control loop was live and repeatedly evaluating runtime positions.

### F3: Only three symbols reached evaluated/open lifecycle state

Evaluated counts by symbol:

- `BNBUSDT = 434`
- `BTCUSDT = 133`
- `XRPUSDT = 446`

Suppressed-only symbols in the slice:

- `1000PEPEUSDT`
- `DOGEUSDT`
- `ETHUSDT`
- `SOLUSDT`

These suppressed-only symbols never reached an observed evaluated window.

### F4: Seven distinct evaluated lifecycles were observed

Grouped by `fill_correlation.rid`, the evaluated lifecycles were:

- `aurora_BNBUSDT_1776888006471` - 8 evaluated rows
- `aurora_BNBUSDT_1776903303598` - 423 evaluated rows
- `aurora_BNBUSDT_1776957305906` - 3 evaluated rows
- `aurora_BTCUSDT_1776945606579` - 133 evaluated rows
- `aurora_XRPUSDT_1776884702659` - 17 evaluated rows
- `aurora_XRPUSDT_1776907803152` - 369 evaluated rows
- `aurora_XRPUSDT_1776940804421` - 60 evaluated rows

All seven evaluated lifecycles show `manage_state=BRACKETS_PENDING` and a real non-empty `side`.

### F5: Evaluated payloads show active positions, but not mark/PnL economics

Representative evaluated payloads show:

- non-empty `side`
- non-empty `position_qty`
- non-empty `entry_price`
- non-empty `portfolio_position_amt`
- `manage_state=BRACKETS_PENDING`
- `portfolio_snapshot_status=present`

But across the entire evaluated slice:

- `mark_price` is blank/null
- `unrealized_pnl_usdt` is blank/null
- `unrealized_pnl_pct` is blank/null

Parsed PnL summary over all 1013 evaluated rows:

- `BNBUSDT`: `valid=0`, `positive=0`, `armed25=0`
- `BTCUSDT`: `valid=0`, `positive=0`, `armed25=0`
- `XRPUSDT`: `valid=0`, `positive=0`, `armed25=0`

This is the key economic observability gap of the entire audit.

### F6: No peak-giveback-specific runtime signatures were observed

Across the bounded runtime sources, there were no hits for:

- `peak_giveback_threshold_met`
- `position_policy_sidecar:peak_giveback`
- `POSITION_POLICY_SIDECAR_RECOMMENDED`
- `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`

This absence held in:

- `logs/trade_lifecycle.jsonl`
- `logs/domain_execution_position.log*`
- `logs/order_log_v1.jsonl`
- `logs/shadow_critical_event_journal_v1.jsonl`

### F7: No sidecar-attributed downstream close routing was observed

Searches over `logs/domain_execution_position.log*` and `logs/order_log_v1.jsonl` found no runtime evidence of:

- `POSITION_POLICY_SIDECAR_CLOSE_REQUEST`
- `policy_source=position_policy_sidecar:peak_giveback`
- sidecar-attributed downstream close ownership

There is therefore no runtime proof that the peak-giveback-specific branch actually emitted a close request in this slice.

### F8: Post-close behavior was safe and bounded

Seven sidecar rows were triggered by `EXECUTION_CLOSE_RECONCILED`, all with:

- `event_type=POSITION_POLICY_SIDECAR_SUPPRESSED`
- `suppression_reason=manage_flow_has_no_active_lifecycle`
- `manage_state=FLAT`
- `portfolio_snapshot_status=symbol_absent`

Observed rows:

- `XRPUSDT` at `1776886571530`
- `BNBUSDT` at `1776888653891`
- `BNBUSDT` at `1776936437416`
- `XRPUSDT` at `1776936437425`
- `XRPUSDT` at `1776945998516`
- `BTCUSDT` at `1776956129098`
- `BNBUSDT` at `1776957835168`

Each evaluated lifecycle cleanly transitions into a no-active-lifecycle suppression after close reconciliation. No duplicate close storm or sidecar persistence after reconciliation was observed.

### F9: Terminal ambiguity suppressions were safe

Five `recent_terminal_order_state_detected` suppressions were observed, all on the same XRP lifecycle:

- symbol: `XRPUSDT`
- incumbent owner: `OrderGuardian`
- lifecycle: `aurora_XRPUSDT_1776884702659`
- triggers: `REGIME_DETECTED`, `ORDER_STATE_CHANGED`, `FEATURES_CALCULATED`, `PORTFOLIO_STATE_UPDATED`

All five occurred while `manage_state=BRACKETS_PENDING` and `portfolio_snapshot_status=present`.

This is direct proof that the Sidecar did not continue into action while terminal order-state ambiguity was recent.

### F10: Suppression mix is consistent with bounded-safe operation

Aggregate suppression reasons in the slice:

- `no_manage_flow_for_symbol = 69166`
- `manage_flow_has_no_active_lifecycle = 14563`
- `features_snapshot_missing_or_stale = 12099`
- `startup_grace_active = 1748`
- `regime_snapshot_missing_or_stale = 1644`
- `post_fill_grace_active = 166`
- `recent_terminal_order_state_detected = 5`

This suppression distribution is exactly what a conservative sidecar should emit when most symbols are inactive or stale.

### F11: No sidecar-specific startup downgrade or error evidence was found

Searches for sidecar startup warnings/errors in:

- `logs/domain_execution_position.log*`
- `logs/aurora_core.log*`

found no sidecar-specific warning, error, fail-closed downgrade, or peak-giveback startup fault signature.

This is weaker than a positive config dump, but it does rule out one easy failure mode: obvious startup disablement with logged downgrade.

### F12: No runtime config-dump proof exists for `peak_giveback_close`

Searches for:

- `peak_giveback_close`
- `edge_arm_usd`
- `giveback_trigger_pct`

returned no runtime hits in:

- `logs/**`
- `ops/**`
- `artifacts/**`

This means the audit has no direct runtime artifact proving the loaded peak-giveback config block and values.

### F13: No anomaly evidence was found in the observed slice

The anomaly scan found:

- no `POSITION_POLICY_SIDECAR_RECOMMENDED`
- no `recommendation_duplicate_same_state`
- no shadow critical journal entries for `position_policy_sidecar`
- no malformed-sidecar payload evidence in the bounded search slice

---

## INFERENCES

### I1: The Sidecar is definitely live after restart

`POSITION_POLICY_SIDECAR_MODE_ACTIVE` plus 1013 evaluated rows is enough to prove that the Sidecar booted and ran in real runtime conditions.

### I2: The standard sidecar path is proven; the peak-giveback-specific path is not

Observed runtime proves:

- activation
- evaluation
- scoring
- suppression
- post-close suppression cleanup

Observed runtime does not prove:

- arming at `edge_arm_usd=25.0`
- giveback calculation from real PnL
- threshold crossing at `giveback_trigger_pct=50.0`
- recommendation emission
- close-request emission

### I3: No split-brain routing evidence exists in this slice

There is no runtime evidence that the Sidecar directly owned execution or emitted duplicate close actions in parallel with the incumbent execution_position flow.

### I4: The current slice is compatible with two explanations

The absence of peak-giveback trigger evidence can mean either:

1. quiet-by-market: no observed position ever armed or crossed the giveback threshold
2. observability gap: the trigger path may have been reachable in-memory, but runtime evidence is insufficient to prove it

Because PnL and mark fields are blank, this audit cannot discriminate between these two explanations.

### I5: Safety behavior is positively supported

Terminal suppressions, stale-data suppressions, startup grace, post-fill grace, and post-close no-lifecycle suppressions all point in the safe direction. The evidence does not suggest dangerous over-activation.

---

## ASSUMPTIONS

### A1: `logs/trade_lifecycle.jsonl` is the authoritative primary runtime surface for this audit

If a hidden or rotated surface contains sidecar trigger evidence not present here, this audit would not see it.

### A2: A real peak-giveback trigger would leave at least one observable trace

The expected traces would be one or more of:

- `POSITION_POLICY_SIDECAR_RECOMMENDED`
- `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`
- `policy_source=position_policy_sidecar:peak_giveback`
- reason code such as `peak_giveback_threshold_met`

None were observed.

### A3: Blank PnL/mark fields are not enough to prove a runtime logic defect

They prove an observability problem for this audit. They do not, by themselves, prove that the in-memory trigger math was wrong.

---

## UNKNOWNS

### U1: Did any evaluated lifecycle ever exceed the 25 USDT arm threshold?

Unknown from runtime evidence.

### U2: Did any armed lifecycle ever retrace by 50 percent?

Unknown from runtime evidence.

### U3: Was the loaded `peak_giveback_close` config exactly the expected YAML block at runtime?

Unknown from runtime evidence because no config dump or startup artifact was found.

### U4: Did the code enter an internal armed state without a log signature?

Unknown from runtime evidence.

### U5: Are there relevant events outside this bounded post-restart slice or in rotated/missing logs?

Unknown from this audit.

---

## Restart Boundary And Activation Proof

The runtime slice begins with a sidecar boot row in `logs/trade_lifecycle.jsonl`.

After that boundary, the first evaluated/open proofs are:

- `XRPUSDT` first evaluated at `1776885003031`
- `BNBUSDT` first evaluated at `1776888302967`
- `BTCUSDT` first evaluated at `1776945900078`

This is enough to prove that the Sidecar was not merely configured; it was actively evaluating live position snapshots after restart.

---

## Case Split A/B/C/D/E

### Case A: Sidecar active and standard evaluated path behaving normally

**Status**: PROVEN

Evidence:

- boot row present
- 1013 evaluated rows
- 1013 score rows
- seven evaluated lifecycles with real position payloads

Conclusion:

The standard bounded Sidecar loop is active and functioning.

### Case B: Peak-giveback-specific arm/trigger path behaving correctly

**Status**: NOT PROVEN

Evidence:

- no peak-giveback-specific runtime events
- no valid runtime PnL values in evaluated payloads
- no runtime config proof for `peak_giveback_close`

Conclusion:

Current runtime evidence cannot prove arm-threshold or giveback-threshold correctness.

### Case C: Routing and ownership remain with incumbent execution_position path

**Status**: SUPPORTED

Evidence:

- no sidecar-attributed close request traces
- terminal suppressions cite `OrderGuardian`
- post-close rows show clean no-active-lifecycle suppressions

Conclusion:

The observed slice shows no split-brain routing and no direct sidecar execution ownership.

### Case D: Safety suppressions are behaving correctly

**Status**: PROVEN

Evidence:

- `startup_grace_active`
- `features_snapshot_missing_or_stale`
- `regime_snapshot_missing_or_stale`
- `post_fill_grace_active`
- `recent_terminal_order_state_detected`
- `manage_flow_has_no_active_lifecycle`

Conclusion:

The Sidecar fails closed in the observed high-risk boundary states.

### Case E: Anomalies such as storms, malformed payloads, or duplicate recommendation spam

**Status**: NOT OBSERVED

Evidence:

- no recommendation spam
- no sidecar shadow-critical entries
- no post-close trigger storm
- no malformed-sidecar evidence in the bounded anomaly scan

Conclusion:

The slice is operationally quiet and bounded, not chaotic.

---

## Routing And Suppression Analysis

The routing result is asymmetric:

- positive proof exists that the Sidecar observes and evaluates open lifecycles
- negative proof exists that it suppresses safely after reconciliation and under terminal ambiguity
- no positive proof exists that the peak-giveback branch emitted recommendation or close-request actions

This asymmetry matters. It means the audit can confidently say the Sidecar is active and conservative, but cannot honestly say that the new peak-giveback trigger was runtime-proven.

---

## Anomaly Analysis

No observed anomaly suggests unsafe behavior of the new path.

What was explicitly not observed:

- duplicate same-state recommendations
- repeated sidecar close requests
- malformed sidecar payload rows in the bounded search slice
- sidecar entries in the shadow critical journal
- sidecar-attributed downstream execution artifacts

This is evidence against trigger storm or routing corruption.

---

## Economic Observations

This is the decisive limitation of the audit.

The evaluated rows prove active positions, but the exact fields needed for peak-giveback economics are missing from runtime payloads:

- `mark_price`
- `unrealized_pnl_usdt`
- `unrealized_pnl_pct`

Because these fields are blank for all evaluated rows, the audit cannot answer:

- whether any lifecycle armed at 25 USDT
- whether any armed lifecycle retraced by 50 percent
- whether the absence of trigger events means quiet-by-market or missing observability

This is why the final conclusion must fail closed.

---

## Final Verdict

The bounded runtime slice proves that the Position Policy Sidecar is active after restart, evaluates live open lifecycles, and suppresses safely under no-lifecycle, stale-data, post-fill, terminal-order-state, and post-close conditions. It also proves the absence of observed recommendation storms, duplicate sidecar action spam, or sidecar-owned execution split-brain in this slice.

The same slice does **not** prove that the new peak-giveback path is behaving correctly at the economic trigger level. Runtime evidence contains no valid mark/PnL fields, no config-load proof for `peak_giveback_close`, and no peak-giveback-specific recommendation or close-request traces. The only defensible bounded-runtime conclusion is therefore:

- active Sidecar path: proven
- safe bounded suppression behavior: proven
- peak-giveback-specific arm/trigger correctness: unproven from runtime evidence
