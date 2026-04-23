# R7B SIDECAR RUNTIME GAP LIST

This file lists only gaps that materially block a bounded-runtime conclusion for peak-giveback correctness. These are observability and proof gaps, not redesign requests.

| Gap | Runtime evidence | Why it matters | Minimal evidence needed to close it |
|---|---|---|---|
| No runtime proof of loaded `peak_giveback_close` config | No hits for `peak_giveback_close`, `edge_arm_usd`, or `giveback_trigger_pct` in `logs/**`, `ops/**`, or `artifacts/**` | Without a runtime artifact, the audit cannot prove that the observed process loaded the intended `enabled=true`, `edge_arm_usd=25.0`, `giveback_trigger_pct=50.0` block | One startup artifact or structured log row showing the loaded sidecar peak-giveback config |
| Evaluated payloads omit mark/PnL economics | All 1013 evaluated rows have blank/null `mark_price`, `unrealized_pnl_usdt`, and `unrealized_pnl_pct` | Peak-giveback is an economic trigger. Without runtime economics, arm/trigger correctness cannot be proven | Persist `mark_price`, `unrealized_pnl_usdt`, and `unrealized_pnl_pct` in evaluated runtime rows |
| No arming-state or threshold-crossing evidence | No hits for `peak_giveback_threshold_met`, `peak_edge_usd`, `giveback_pct`, or any explicit arming marker | The audit cannot distinguish quiet-by-market from an unobservable trigger path | One additive runtime marker for `armed`, `peak_edge_usd`, or threshold-cross reason codes |
| No peak-giveback-specific downstream event chain | No `POSITION_POLICY_SIDECAR_RECOMMENDED`, no `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`, no `policy_source=position_policy_sidecar:peak_giveback` in bounded logs | Without downstream chain evidence, the audit cannot prove that the new trigger path actually emitted an action when conditions were met | One recommendation or close-request runtime trace carrying peak-giveback provenance |
| No admission-grade discriminator between safe quiet and silent non-proof | Current slice shows live evaluation and safe suppressions, but zero observable trigger economics | This is the root reason the final decision must fail closed | A future slice where at least one lifecycle exposes real PnL/mark values, whether or not it triggers |

## What These Gaps Do Not Mean

- They do **not** prove the peak-giveback logic is broken.
- They do **not** prove the config is missing.
- They do **not** justify package redesign.
- They do justify a fail-closed runtime verdict for the new path.

## Narrow Follow-Up Evidence Goals

1. Preserve one post-restart runtime slice with startup config proof for the sidecar block.
2. Preserve evaluated rows with non-empty `mark_price` and `unrealized_pnl_*` fields.
3. Preserve either a real peak-giveback trigger chain or a non-trigger slice where arm-threshold exposure can be disproven from runtime values.
