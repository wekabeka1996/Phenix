# RUNTIME_ACCEPTED_REJECTED_ECONOMICS_DEEP_RESEARCH_REPORT

## Executive verdict

Aurora was net negative on the accepted-and-closed cohort in this retained runtime slice, while the dominant reject mechanism was not uniformly protective. The strongest over-blocking evidence is the low-vol cost-floor direction-confidence gate on BTCUSDT longs: 5 rejected `NRR-062` rows had safe recorder-bar evidence that TP geometry was reached before SL geometry, with expected net-at-TP already positive after configured fee assumptions. The strongest toxic-accept evidence is the accepted MEAN_REVERSION short cohort in BNBUSDT and XRPUSDT: both resolved closes were net losers, and XRPUSDT specifically showed a positive excursion that was fully given back before a sidecar-driven close.

## FACTS

- Primary runtime window from retained evidence:
  - earliest retained primary event: `2026-05-09T13:55:16.960Z`
  - latest retained primary event used here: `2026-05-09T18:54:15.714Z`
  - local time in `Europe/Kyiv`: `2026-05-09 16:55:16` to `21:54:15`
- Runtime event counts in the retained slice:
  - `strategy signals`: `56` via `EVT:STRATEGY_SIGNAL_PRODUCED`
  - `trade intents proposed`: `7` via `EVT:TRADE_INTENT_PROPOSED`
  - `trade intents rejected`: `49` via `EVT:TRADE_INTENT_REJECTED`
  - `accepted opens`: `7` decision-layer `ORDER_INTENT` rows from `DecisionMaking`
  - `order acks`: `0` explicit `EVT:ORDER_ACK` rows retained
  - `order placed`: `7` via `EVT:ORDER_PLACED`
  - `fills`: `8` total `ORDER_FILLED` rows
  - `entry fills`: `5`
  - `terminal fills`: `3`
  - `closes`: `3` via `POSITION_CLOSED`
  - `sidecar records`: `23,492` `position_policy_sidecar` rows in `trade_lifecycle.jsonl`
  - `sidecar actionable rows`: `10`
  - `low-vol cost-floor blocked rejects`: `32`
  - `regime events`: `413` via `EVT:REGIME_DETECTED`
  - `regime audit bar-close rows`: `433`
- Sidecar actionable event breakdown:
  - `POSITION_POLICY_SIDECAR_RECOMMENDED`: `2`
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`: `2`
  - `POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE`: `6`
- Reject families in runtime:
  - `32` rejects were `NRR-062` with `why=LOW_VOL_COST_FLOOR_BLOCKED`
  - `17` rejects carried `reason_code=ANTI_PYRAMIDING_BLOCK`
- Reject distribution:
  - by symbol:
    - `BTCUSDT`: `26`
    - `ETHUSDT`: `18`
    - `XRPUSDT`: `6`
  - by gate:
    - `low_vol_cost_floor`: `32`
    - `flip_gate`: `17`
  - by regime:
    - `LOW_VOLATILITY`: `35`
    - `TREND_UP`: `8`
    - `MEAN_REVERSION`: `6`
  - by timeframe:
    - all retained Aurora rows in this slice resolve to `300s`
  - by strategy:
    - all retained reject rows in this slice were `aurora`
- Accepted open outcomes:
  - `7` accepted opens
  - `2` cancelled before fill
  - `3` resolved terminal closes
  - `2` remained open/unresolved at the end of the retained slice
- Accepted-and-closed realized economics:
  - gross PnL sum: `-3.3429 USDT`
  - fees sum: `6.74474221 USDT`
  - net PnL sum: `-10.08764221 USDT`
- Resolved accepted trades:
  - `aurora_BTCUSDT_1778344204188`: closed `TP`, net `+8.86243800 USDT`
  - `aurora_BNBUSDT_1778345109617`: closed `CLOSE`, net `-10.19342272 USDT`
  - `aurora_XRPUSDT_1778343903334`: closed `CLOSE`, net `-8.75665749 USDT`
- Counterfactual results for the `32` low-vol rejects with persisted geometry:
  - `target_before_stop`: `5`
  - `stop_before_target`: `19`
  - `favorable_drift_only`: `8`
  - `ambiguous_same_bar`: `0`
  - `no_favorable_move`: `0`
- All 5 `target_before_stop` low-vol counterfactual wins were `BTCUSDT BUY` rejects.
- The 17 `ANTI_PYRAMIDING_BLOCK` rejects overlapped live same-symbol accepted positions:
  - `11` overlapped an active BTCUSDT long
  - `6` overlapped active ETHUSDT or XRPUSDT positions
- `config/aurora/domains.yaml` shows:
  - `position_policy_sidecar.mode: enable`
  - `emit_internal_bus_events: true`
  - `write_trade_lifecycle_jsonl: true`
  - `allowed_actions.soft_close_symbol_current_net_only: true`
- `config/aurora/strategies/aurora.yaml` shows `position_mode: STRICT` for BTCUSDT, ETHUSDT, XRPUSDT, and BNBUSDT.

## INFERENCES

- The low-vol cost-floor gate is over-blocking at least one real profitable subset, specifically BTCUSDT low-vol BUY setups in this slice.
- The runtime problem is not "rejects are bad" in aggregate. The low-vol gate had both protective rejects and profitable misses in the same window.
- The accepted toxic cohort is concentrated in MEAN_REVERSION shorts, not in the TREND_UP accepted longs.
- XRPUSDT is more consistent with a giveback/exit-governance problem than a pure no-edge entry problem, because it had a positive bar-level excursion before being closed at a net loss.
- BNBUSDT is a stronger entry-quality false-negative candidate than XRPUSDT, because its favorable excursion was minimal before the trade moved materially against the position.
- The `ANTI_PYRAMIDING_BLOCK` family looks policy-protective rather than profit-destructive in this slice because those rows occurred while `position_mode: STRICT` and same-symbol positions were already open.
- There is an observability mismatch in the flip gate surface: the runtime reject context string says `strategy_signal_gateway:flip_unknown_state` even when the reason code is `ANTI_PYRAMIDING_BLOCK`, which makes downstream audit harder than it should be.
- The sidecar did not demonstrate profit capture in this slice; its actionable close behavior appears after PnL deterioration, not at a preserved profitable edge.

## ASSUMPTIONS

- Recorder-bar counterfactuals use the first fully closed `300s` bar after the decision timestamp. This is conservative and avoids claiming intrabar path knowledge before the event was fully emitted.
- Accepted-trade MFE/MAE and giveback calculations also use only fully closed `300s` bars after entry fill time.
- Low-vol counterfactual profitability is treated as "safe favorable" only when TP was reached before SL in different retained bars and the persisted gate economics already showed positive `expected_net_if_tp_bps`.
- Fee assumptions for rejected low-vol counterfactuals come from the persisted gate payload itself:
  - `round_trip_fee_bps = 8.0`
  - `slippage_buffer_bps = 2.0`
- No extra slippage beyond the persisted low-vol gate assumptions is added in the reject counterfactual section.

## UNKNOWNS

- The final realized economics for the still-open accepted `ETHUSDT` and late `BTCUSDT` longs are unknown in this retained slice.
- Intrabar path ordering inside a single `300s` candle remains unknown; this report therefore does not claim same-bar TP-vs-SL ordering.
- There is no retained `logs/shadow_telemetry/decision_ledger_v1.jsonl` file in this checkout, so downstream dataset-admission truth cannot be verified here.
- There are no explicit retained `EVT:ORDER_ACK` rows, so ack-level timing cannot be reconstructed independently from `ORDER_PLACED`.

## Runtime dataset summary

- Runtime logs used:
  - `logs/order_log_v1.jsonl`
  - `logs/trade_lifecycle.jsonl`
  - `logs/shadow_critical_event_journal_v1.jsonl`
  - `logs/domain_decision_making.log`
  - `logs/domain_execution_position.log`
  - `logs/regime_confidence_audit_v1.jsonl`
- Recorder data used:
  - `data/recorder/2026-05-09/*_300.csv`
- Config/code used only to explain mechanism, not to prove runtime:
  - `config/aurora/domains.yaml`
  - `config/aurora/strategies/aurora.yaml`
  - `config/aurora/regime.yaml`
  - `apps/reference/domains/decision_making/gates/low_vol_cost_floor.py`
  - `apps/reference/domains/decision_making/gates/safety_gates.py`
  - `apps/reference/domains/decision_making/gates/flip_gate.py`
  - `apps/reference/domains/decision_making/intent/flip.py`
  - `apps/reference/domains/execution_position/position_policy_sidecar.py`
  - `apps/reference/telemetry/order_logger.py`
  - `apps/reference/telemetry/trade_lifecycle_logger.py`
- Requested-but-missing evidence surface:
  - `logs/shadow_telemetry/decision_ledger_v1.jsonl`

## Join-key methodology

- Reject cohort root:
  - start from `EVT:TRADE_INTENT_REJECTED` in `logs/shadow_critical_event_journal_v1.jsonl`
  - use `rid` as the canonical join key
  - enrich with `logs/order_log_v1.jsonl` when a matching `DECISION_INTENT_REJECTED` row exists
- Accepted cohort root:
  - start from decision-layer `ORDER_INTENT` rows where `source_fsm=DecisionMaking`
  - join to `ORDER_PLACED` by the same `rid`
  - join to `ORDER_FILLED` by `lifecycle_id = accepted rid`
  - join terminal `POSITION_CLOSED` by close-fill `order_id` or close-fill `client_order_id`
- Regime enrichment:
  - prefer regime fields already persisted in `order_log_v1.jsonl`
  - otherwise use nearest prior `regime_confidence_audit_v1.jsonl` row for the same symbol
- Sidecar causation:
  - use `trade_lifecycle.jsonl` `record_kind=position_policy_sidecar`
  - link to accepted trade by `fill_correlation.rid`
- Recorder join:
  - use same-symbol `2026-05-09` `*_300.csv`
  - join by timestamp and analyze only bars strictly after the decision or fill timestamp

## Accepted lifecycle economics

### Per-trade table

| RID | Symbol | Side | Regime | Status | Gross PnL | Fees | Net PnL | MFE bps | MAE bps | Peak Giveback bps | Time in Trade min | Close Reason |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `aurora_XRPUSDT_1778343903334` | XRPUSDT | SELL | MEAN_REVERSION | CLOSED | -6.5949 | 2.16175749 | -8.75665749 | 27.138 | -18.679 | 45.464 | 64.68 | CLOSE |
| `aurora_BNBUSDT_1778343904302` | BNBUSDT | SELL | MEAN_REVERSION | CANCELLED | - | - | - | - | - | - | - | timeout_cancellation |
| `aurora_BTCUSDT_1778344204188` | BTCUSDT | BUY | MEAN_REVERSION | CLOSED | 11.2850 | 2.42256200 | 8.86243800 | 34.770 | -6.582 | 6.768 | 112.37 | TP |
| `aurora_BNBUSDT_1778344504861` | BNBUSDT | SELL | MEAN_REVERSION | CANCELLED | - | - | - | - | - | - | - | timeout_cancellation |
| `aurora_BNBUSDT_1778345109617` | BNBUSDT | SELL | MEAN_REVERSION | CLOSED | -8.0330 | 2.16042272 | -10.19342272 | 2.542 | -29.816 | 24.885 | 8.86 | CLOSE |
| `aurora_ETHUSDT_1778348403439` | ETHUSDT | BUY | TREND_UP | OPEN_UNRESOLVED | - | 0.66221726 entry only | - | 31.694 | -17.875 | 31.694 | 62.49 to slice end | - |
| `aurora_BTCUSDT_1778352004210` | BTCUSDT | BUY | TREND_UP | OPEN_UNRESOLVED | - | 1.50472140 entry only | - | 0.810 | -6.298 | 0.810 | 6.02 to slice end | - |

### Cohort findings

- Closed accepted cohort net was `-10.08764221 USDT`.
- Toxic accepted trades:
  - `aurora_BNBUSDT_1778345109617`
    - only `2.542 bps` favorable excursion before `-29.816 bps` adverse excursion
    - net close `-10.19342272 USDT`
    - runtime shape is consistent with weak entry edge rather than missed profit capture
  - `aurora_XRPUSDT_1778343903334`
    - reached `27.138 bps` favorable excursion, then gave back `45.464 bps`
    - net close `-8.75665749 USDT`
    - runtime shape is consistent with a giveback/exit problem
- Favorable accepted trade:
  - `aurora_BTCUSDT_1778344204188`
    - TP close
    - net `+8.86243800 USDT`
    - low giveback relative to MFE (`6.768 bps`)

## Rejected intent counterfactuals

### Low-vol cost-floor rejects with persisted geometry

- Total geometry-safe low-vol rows evaluated: `32`
- Counterfactual outcome split:
  - `5` `target_before_stop`
  - `19` `stop_before_target`
  - `8` `favorable_drift_only`

### Safe favorable rejected trades

These are the strongest over-blocking candidates because TP was reached before SL on retained `300s` bars and the persisted low-vol payload already showed positive expected net economics:

| RID | Symbol | Side | Regime | Direction Confidence | Threshold | Expected Net if TP bps | Max Favorable bps | Verdict |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `aurora_BTCUSDT_1778335202415` | BTCUSDT | BUY | LOW_VOLATILITY | 0.00624569 | 0.25 | 69.375 | 84.665 | target_before_stop |
| `aurora_BTCUSDT_1778335808487` | BTCUSDT | BUY | LOW_VOLATILITY | 0.00702927 | 0.25 | 69.375 | 90.574 | target_before_stop |
| `aurora_BTCUSDT_1778336403925` | BTCUSDT | BUY | LOW_VOLATILITY | 0.00093656 | 0.25 | 69.375 | 88.123 | target_before_stop |
| `aurora_BTCUSDT_1778337007216` | BTCUSDT | BUY | LOW_VOLATILITY | 0.00093656 | 0.25 | 69.375 | 94.781 | target_before_stop |
| `aurora_BTCUSDT_1778337601919` | BTCUSDT | BUY | LOW_VOLATILITY | 0.00055454 | 0.25 | 69.375 | 99.150 | target_before_stop |

### Protective rejected trades

- `19` low-vol rejects were protective on retained bar evidence because SL geometry was reached before TP geometry.
- The worst-safe rejects were concentrated in:
  - `ETHUSDT SELL` low-vol shorts
  - `BTCUSDT SELL` low-vol shorts
  - `XRPUSDT SELL` low-vol shorts
- Example protective rows:
  - `aurora_ETHUSDT_1778336402081`
  - `aurora_ETHUSDT_1778337006254`
  - `aurora_BTCUSDT_1778338202961`
  - `aurora_XRPUSDT_1778339406344`

### Rows that remain insufficient for profit claims

- `8` low-vol rejects had favorable drift but no safe TP-before-SL proof before the retained slice ended.
- `17` `ANTI_PYRAMIDING_BLOCK` rejects do not carry standalone TP/SL geometry in the retained payloads, so they are not valid for pure geometry-based missed-profit claims.
- Those 17 rows were not random misses:
  - each overlapped an already active same-symbol position
  - the relevant assets are configured `position_mode: STRICT`

## Gate false-positive candidates

- `P0 candidate: low_vol_cost_floor` on `BTCUSDT BUY` in `LOW_VOLATILITY`
  - runtime proof: `5` rejects hit TP geometry before SL geometry
  - mechanism proof: all 5 were blocked by the low-vol direction-confidence rule, not by missing gross TP economics
  - persisted gate payload shows:
    - `expected_net_if_tp_bps = 69.375`
    - `direction_confidence` was compared against `0.25`
    - winning rejected rows had selected direction-confidence values between `0.00055454` and `0.00702927`
- `P1 candidate: low_vol_cost_floor` marginal drift bucket
  - `8` more low-vol rejects had favorable movement but no safe TP-before-SL proof
  - they are not counted as proven profitable misses, but they strengthen the case that the gate is conservative on the BTC long side

## Gate false-negative candidates

- `P0 candidate: accepted BNBUSDT short aurora_BNBUSDT_1778345109617`
  - accepted in `MEAN_REVERSION`
  - closed net `-10.19342272 USDT`
  - only `2.542 bps` MFE before `-29.816 bps` MAE
  - candidate interpretation: weak entry quality was admitted
- `P0 candidate: accepted XRPUSDT short aurora_XRPUSDT_1778343903334`
  - accepted in `MEAN_REVERSION`
  - closed net `-8.75665749 USDT`
  - had `27.138 bps` MFE, then `45.464 bps` peak giveback before close
  - candidate interpretation: accepted entry was not strongly bad at inception, but exit governance failed to preserve the early edge
- `P1 candidate: sidecar close logic as late-loss containment`
  - BNBUSDT and XRPUSDT both produced sidecar `RECOMMENDED` then `CLOSE_REQUESTED`
  - both recommendations happened when current edge was already negative
  - in both actionable rows the sidecar surface still reported `peak_giveback_not_armed_below_edge`

## Top P0 profit bottlenecks

- `P0-1: BTC low-vol long over-blocking`
  - 5 BTCUSDT BUY rejects were provably profitable by safe TP-before-SL geometry
  - all were blocked by low-vol direction-confidence gating despite positive persisted fee-adjusted TP economics
- `P0-2: toxic accepted MEAN_REVERSION shorts`
  - BNBUSDT and XRPUSDT MEAN_REVERSION shorts were admitted and jointly lost `-18.95008021 USDT` net
  - this alone overwhelmed the single profitable accepted BTC TP win
- `P0-3: sidecar closes acted after loss, not after protected profit`
  - BNBUSDT close recommendation fired with `peak_edge_usd = 0.0` and `current_edge_usd = -9.3`
  - XRPUSDT close recommendation fired with `peak_edge_usd = 6.21` and `current_edge_usd = -8.98`
  - in both cases the main peak-giveback state remained `peak_giveback_not_armed_below_edge`, which implies the active arm threshold was too high for the observed position economics

## Data quality limitations

- `logs/shadow_telemetry/decision_ledger_v1.jsonl` was requested but absent in this checkout.
- Explicit `EVT:ORDER_ACK` rows were not retained, so ack-level timing could not be reconstructed.
- Two accepted trades remained open at slice end, so realized accepted economics are incomplete for the full session.
- `MFE`, `MAE`, and counterfactual TP/SL sequencing are based on retained `300s` bars only; no intrabar tick-path claims are made.
- The shadow journal was still live while analysis was performed, so counts reflect the retained-file snapshot at read time, not a previously frozen archive.
- `ANTI_PYRAMIDING_BLOCK` rows do not carry full TP/SL geometry, so they are policy-auditable but not safe for standalone geometry profit reconstruction.

## Next required runtime collection

- Freeze the next comparable slice immediately after session end:
  - copy `order_log_v1.jsonl`, `trade_lifecycle.jsonl`, `shadow_critical_event_journal_v1.jsonl`, `regime_confidence_audit_v1.jsonl`, and both domain logs to a dated immutable bundle
- Restore or redirect the missing decision-ledger surface so dataset-admission truth is auditable from the same slice.
- Persist accepted-trade structure at accept time into a stable artifact:
  - entry price
  - stop price
  - target price
  - objective score
  - active threshold
- Emit an explicit order-ack artifact if exchange ack timing matters operationally.
- Separate flip-gate observability from the current misleading context string so `ANTI_PYRAMIDING_BLOCK` is not emitted under `strategy_signal_gateway:flip_unknown_state`.
- Persist sidecar close trigger semantics more explicitly:
  - active arm threshold
  - whether close was driven by giveback, soft-close pressure, or another branch
  - the exact threshold comparison that caused `CLOSE_REQUESTED`
