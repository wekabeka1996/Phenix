# SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01

## Status
POLICY_ACTIVE — 2026-05-18

## Scope
Defines the canonical, deterministic reference price resolution hierarchy for
rejected decision contracts entering the SemaAtom offline evidence pipeline.

Applies to:
- `Sema_Atom/SEMA_ATOM_POC_02_REAL_LOG_ADAPTER.py` — `RejectedDecisionCollector`
- `Sema_Atom/SEMA_ATOM_FORWARD_COLLECTOR.py` — `RejectedDecisionCollector`

Does NOT apply to:
- Accepted decision contracts (entry_price comes from ORDER_FILLED events)
- Live trading logic — SemaAtom has zero runtime authority
- Gate thresholds, YAML policies, or runtime handlers

## Resolver Module
`Sema_Atom/sema_atom_reference_price_resolver.py` — single canonical implementation.
Both collectors import from this module. No duplicate extraction logic elsewhere.

## Recovery Hierarchy

### Level 0 — `metadata.low_vol_cost_floor.entry_price`
- Trainability: `trainable`
- Causal link: ok
- Recovery reason: `level_0_explicit_low_vol_cost_floor`
- Rationale: Emitted by the low-volatility cost floor gate at the exact moment of
  rejection. Price is strategy-intended and rejection-contemporaneous — the highest
  fidelity signal for why the entry was blocked.

### Level 1 — `metadata.reference_price` / `intended_entry_price`
- Sources (in priority order):
  1. `metadata.reference_price`
  2. `metadata.intended_entry_price`
  3. `reference_price` (top-level)
  4. `intended_entry_price` (top-level)
- Trainability: `trainable`
- Causal link: ok
- Recovery reason: `level_1_explicit_reference_or_intended`
- Rationale: Explicitly declared strategy-intended price before evaluation.

### Level 2 — `metadata.economics_context.entry_price`
- Trainability: `trainable`
- Causal link: ok
- Recovery reason: `level_2_explicit_economics_context`
- Rationale: Strategy-derived economics snapshot. Still strategy-authored and
  rejection-contemporaneous, though one level of indirection removed.

### Level 3 — `metadata.linked_order_intent.entry_price`
- Trainability: `trainable` (if causal link valid) or `invalid` (if causal link broken)
- Causal link validation: `linked_order_intent.timestamp` MUST NOT be after the
  rejected event timestamp. If `link_ts > row_ts`, the resolution is `invalid` and
  `reference_price` is returned as `None`. This prevents a future strategy intent
  from being attributed to an earlier rejection.
- Recovery reason: `level_3_linked_order_intent` (valid) or
  `level_3_causal_link_failed_timestamp_after_rejected` (invalid)
- Fallback sources (Level 3, no causal check):
  1. `metadata.linked_planned_entry_price`
  2. `metadata.planned_entry_price`
  3. `planned_entry_price` (top-level)
- Fallback recovery reason: `level_3_linked_order_intent_fallback`
- Rationale: Derived from a linked prior order intent rather than the decision row
  itself. Valid when the linked intent precedes the rejection; structurally suspect
  when the link timestamp is newer.

### Level 4 — Recorder-derived bar price
- Source: `recorder_bar_price` (must be injected externally by the caller)
- Trainability: `diagnostics_only` — **NEVER trainable**
- Causal link: not ok
- Recovery reason: `level_4_recorder_derived_diagnostics_only`
- Rationale: Market-observed OHLCV candle price. It tells us what price the market
  traded at near the rejection time, but it is NOT the price the strategy intended to
  enter at. Using it as a training reference would conflate market movement with
  strategy intent. It is admitted only for observability dashboards.

### Level 5 — No usable price
- Trainability: `missing`
- Causal link: not ok
- Recovery reason: `level_5_missing_no_usable_price`
- Outcome: The rejected event is counted in the incomplete-rejection bucket
  (`incomplete_rejected_missing_reference_price`) and does NOT become a training atom.

## Trainable Admission Rule

A rejected decision contract is admitted as a REJECTED training atom if and only if:

```
resolution.trainability == "trainable"
```

This means:
- Levels 0, 1, 2, 3 (with valid causal link) → admitted
- Level 3 with broken causal link → DROPPED (invalid, not diagnostics)
- Level 4 recorder-derived → DROPPED (diagnostics_only)
- Level 5 no price → DROPPED (missing)

Any `continue` from the collector's trainability gate is recorded in
`incomplete_rejected_buckets` under the appropriate key.

## Output Fields on RejectedDecisionContract

Every admitted REJECTED contract carries these provenance fields in `provenance`:

| Field | Type | Description |
|---|---|---|
| `reference_price_source` | str | Dot-path of the winning source field |
| `reference_price_source_level` | str | `"0_explicit_low_vol_cost_floor"` … `"5_missing"` |
| `reference_price_trainability` | str | `trainable` \| `diagnostics_only` \| `missing` \| `invalid` |
| `reference_price_recovery_reason` | str | Human-readable reason code |
| `reference_price_causal_link_ok` | bool | Whether causal link check passed |

Dropped contracts (invalid / diagnostics_only / missing) do NOT appear in the
atom file. Their counts are reported in the collector summary.

## Collector Metrics

Both collectors report the following fields in their summary return dict:

| Key | Description |
|---|---|
| `rejected_events_found` | Raw rejected events scanned |
| `reference_price_source_level_histogram` | `{level_key: count}` for all scanned rows |
| `incomplete_rejected_buckets["incomplete_rejected_missing_reference_price"]` | Level 5 skips |
| `incomplete_rejected_buckets["incomplete_rejected_invalid_reference_price"]` | Level 3 causal link failures |
| `incomplete_rejected_buckets["incomplete_rejected_diagnostics_only_reference_price"]` | Level 4 skips |

FC additionally reports:
- `rejected_reference_price_trainable_count` (synonym for `rejected_with_reference_price`)
- `rejected_reference_price_diagnostics_only_count`
- `rejected_missing_reference_price`
- `rejected_invalid_reference_price`
- `reference_price_coverage_trainable` — trainable / total
- `reference_price_coverage_any` — (trainable + diagnostics_only) / total
- `rejected_reference_price_coverage` (backward-compat alias = coverage_trainable)

## Invariants

1. The histogram over `reference_price_source_level` must sum to `rejected_events_found`.
2. `len(trainable_contracts)` + missing + invalid + diagnostics_only == `rejected_events_found`
   (no event is silently discarded).
3. Recorder-derived price (Level 4) MUST appear only via explicit `recorder_bar_price`
   kwarg injection. No code path in the resolver promotes it automatically.
4. `causal_link_ok=False` on Levels 4 and 5 is structural — they are not defects.
   `causal_link_ok=False` on Level 3 invalid IS a defect in the source data.

## Version History

| Version | Date | Change |
|---|---|---|
| V01 | 2026-05-18 | Initial policy. Created resolver module + both collector patches. |
