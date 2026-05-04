# R7D Peak-Giveback Gap List

## Gap 1

- Exact runtime gap: latest `POSITION_POLICY_SIDECAR_MODE_ACTIVE` row at 2026-04-25T23:00:46.264Z does not contain `sidecar_config_snapshot`.
- Category: deployment / wiring / observability
- Why it matters: runtime cannot prove `peak_giveback_close.enabled`, `edge_arm_usd`, `giveback_trigger_pct`, or freshness settings from startup evidence.
- Smallest safe next step: verify the deployed Sidecar build and the trade-lifecycle serialization path on the runtime host, then capture the first post-restart mode-active row again.

## Gap 2

- Exact runtime gap: all 49,362 non-mode Sidecar rows in the latest window are missing `peak_giveback_snapshot`.
- Category: observability
- Why it matters: peak-giveback states cannot be reconstructed at all; Q3 through Q5 remain unprovable.
- Smallest safe next step: confirm that the runtime host is actually running the R7C payload shape and that no serializer or flattening layer strips additive fields before writing logs/trade_lifecycle.jsonl.

## Gap 3

- Exact runtime gap: the only evaluated lifecycle rid in the latest window, `aurora_BNBUSDT_1777136102246`, has 296 evaluated rows but zero populated `mark_price`, zero populated `unrealized_pnl_usdt`, and zero explicit null-reason blocks.
- Category: economics / observability
- Why it matters: even the fallback economic surface is still missing, so runtime cannot distinguish quiet market from missing economics.
- Smallest safe next step: inspect the portfolio-to-sidecar payload path on the runtime host and confirm whether economic fields are lost before Sidecar serialization.

## Gap 4

- Exact runtime gap: no `POSITION_POLICY_SIDECAR_RECOMMENDED`, no `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`, and no downstream Sidecar provenance were found in trade lifecycle, order log, shadow journal, or execution-domain logs.
- Category: observability / routing proof
- Why it matters: absence of trigger evidence cannot be classified as quiet-by-market while the required observability fields are missing.
- Smallest safe next step: after deployment-path verification, capture another bounded runtime slice before making any policy or threshold changes.

## Gap 5

- Exact runtime gap: validator cross-check shows BNBUSDT fill ingress at 2026-04-26T05:17:12.496Z became a fresh candidate but never re-entered evaluated; first blocker after fill was `manage_flow_has_no_active_lifecycle`.
- Category: lifecycle / wiring
- Why it matters: this reduces peak-giveback observation coverage right where post-fill monitoring should have continued.
- Smallest safe next step: inspect execution-position lifecycle reconstruction for that symbol and rid after fill ingress, without changing peak-giveback policy logic.
