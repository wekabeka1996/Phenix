# EXEC_POS_METRICS_DEDUP_REPORT (RID: METRICS-DEDUP-S1)

## 1. Current Tool Metrics
- **TCA (`apps/reference/tools/tca_execpos/`)**
  - Produces per-trade records (`ExecPosTCATradeRecord`) and summaries (`ExecPosTCASummary`) with: `total_volume`, `total_fees`, `trade_count`, `avg_slippage_bps`, `p95_slippage_bps` (actually p05 “worst tail”), `min_slippage_bps`, `max_slippage_bps`, `avg_time_to_fill_ms`. No canonical counters or label schema; win/loss not derived (no PnL).
  - Emits ad-hoc dicts via `compute_tca_for_period`; no Prometheus/text exposure.
- **OrderTrace V2 (`apps/reference/tools/order_trace/`)**
  - Focused on timeline reconstruction; no metric aggregation or counters today. CLI outputs timeline/table/json only.
- **Other metrics helpers**
  - `apps/reference/domains/execution_position/metrics_aggregator.py` (SUSPECT_DUPLICATE) counts risk clipping/reject/idempotent cancel events for legacy/runtime flows (not used by tools).
  - Runtime metrics (unchanged here): `watchdog_violations`, `watchdog_violations_by_kind`, `brackets_alerts`, trailing signals, etc., are produced inside ExecPosRuntimeV2 but not consumed/normalized by tools.

## 2. Overlaps & Drift
- Naming drift: TCA summaries use bespoke keys (e.g., `avg_slippage_bps`) with no labels. Runtime uses counters keyed by event kind/severity (`watchdog_violations_by_kind`), while tools have no matching schema.
- Duplicate/parallel metric layers: `metrics_aggregator.py` (legacy risk metrics) vs. no tooling consumer; runtime metrics exist but tools do not aggregate them, leading to gaps and inconsistent naming.
- Missing alignment for bracket/trailing/watchdog severities: watchdog now reports WARN/ALERT by kind, but no tool-side consumer aggregates `watchdog_violations_by_kind` or bracket/trailing signals.

## 3. Target Canonical Metrics (Tools Scope)
- Namespace prefix: `execpos_` for tooling outputs.
- Counters (with labels):
  - `execpos_trades_total{result="win|loss|flat|unknown",source="tca|trace|runtime"}` — derived from PnL when available; fallback `unknown` if PnL or exit info absent.
  - `execpos_bracket_violations_total{severity="WARN|ALERT",kind="MISSING_SL|ORPHAN_SL|TOO_MANY_SL|STALE_LEVELS|..."}`
  - `execpos_watchdog_alerts_total{severity="WARN|ALERT",kind="MISSING_SL|ORPHAN_SL|TOO_MANY_SL|STALE_LEVELS|..."}`
  - `execpos_trailing_signals_total{kind="EXIT|MOVE_SL|BREAKEVEN|TIME_EXIT|UNKNOWN"}`
  - Optional derived TCA counters: `execpos_tca_trades_total{role="ENTRY|SL|TP|CLOSE",source="tca"}` and aggregates for slippage buckets if needed.
- Derived (per-run) stats (non-counter):
  - `execpos_trade_hold_time_avg_ms`, `execpos_bracket_recalcs_per_trade_avg`, `execpos_trailing_exit_rate` — computed in tooling reports only, not exported as counters.
- Mapping (old → canonical):
  - TCA summaries → `execpos_trades_total{result="unknown",source="tca"}` + keep slippage stats as report-only fields.
  - Runtime `watchdog_violations_by_kind` → `execpos_watchdog_alerts_total{severity,kind}` (tools consume snapshots/logs and re-emit under canonical name).
  - Legacy `metrics_aggregator` risk events → out of scope for ExecPos tools; keep separate.

## 4. Implementation Notes (Tools Only)
- Add shared tooling module `apps/reference/tools/execpos_metrics_aggregator.py` to:
  - Normalize severities/labels.
  - Accumulate counters for trades/bracket plans/watchdog alerts/trailing signals.
  - Expose summaries as dict and Prometheus text exposition.
- TCA:
  - Reuse TCA records to increment `execpos_trades_total{result="unknown",source="tca"}` (pnl-less) and role counters; keep slippage stats as auxiliary.
  - Export canonical metrics alongside existing summaries (no runtime changes).
- OrderTrace CLI:
  - Add `--metrics-summary` option to emit canonical metrics derived from the reconstructed trace events (EXEC_TRADE → trades_total, WATCHDOG/BRACKET events → violations, TRAILING_SL_UPDATED → trailing signals).
  - Output JSON and/or Prometheus-friendly text for downstream consumption.

## 5. DoD Status
- PHASE 0 discovery captured current tool metrics, overlaps, and gaps.
- PHASE 1 target schema defined with canonical names/labels and mapping guidance (tools scope only; runtime untouched).
