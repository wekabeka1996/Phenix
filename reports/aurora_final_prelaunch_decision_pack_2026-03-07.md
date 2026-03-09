# Aurora / Phenix Final Pre-Launch Decision Pack

## Scope

This document synthesizes:
- [aurora_forensic_report_2026-03-06_2026-03-07.md](/c:/Users/user/Music/Phenix/reports/aurora_forensic_report_2026-03-06_2026-03-07.md)
- [aurora_regime_forensic_uncertain_low_vol_2026-03-07.md](/c:/Users/user/Music/Phenix/reports/aurora_regime_forensic_uncertain_low_vol_2026-03-07.md)
- WAL evidence from `ops/wal/2026-03-06.jsonl` and `ops/wal/2026-03-07.jsonl`
- order lifecycle evidence from `logs/order_log_v1.jsonl`
- current config state in `config/aurora`
- operator's current symbol assignment in [strategies.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies.yaml)

No config was changed in this review.

## Evidence Baseline

- Reconstructed completed trades: `60`
- `aurora`: `44` trades, win rate `65.9%`, profit factor `1.43`, net PnL `+261.47`
- `mean_reversion`: `16` trades, win rate `43.8%`, profit factor `0.56`, net PnL `-208.83`
- Regime net PnL:
  - `MEAN_REVERSION`: `+293.57`
  - `UNCERTAIN`: `-141.67`
  - `LOW_VOLATILITY`: `-83.88`
  - `HIGH_VOLATILITY`: `-15.37`
- Confirmed execution conflict: `2026-03-07 09:30:03 UTC`, `SOLUSDT`, `aurora LONG` pending vs `md_amr SHORT` intent
- Cancel profile:
  - `CANCEL_SUPERSEDED`: `7`
  - `timeout_cancellation`: `6`
  - `manual_close`: `2`

## Step 1: Operator Symbol Assignment Validation

Current operator assignment in [strategies.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies.yaml):
- `XRPUSDT`, `BNBUSDT` -> `md_amr` only
- `DOGEUSDT` -> `mean_reversion` only
- `BTCUSDT`, `ETHUSDT`, `SOLUSDT` -> `aurora` only

Validation:

| Symbol Set | Verdict | Evidence |
| --- | --- | --- |
| `BTCUSDT`, `ETHUSDT`, `SOLUSDT` -> `aurora` only | Reasonable with restrictions | `aurora` is the only strategy with positive net PnL in the reconstructed live window |
| `DOGEUSDT` -> `mean_reversion` only | Reasonable only if MR is not launched at `180s` | live MR is losing overall; DOGE is stronger than XRP in the observed window, but current [mean_reversion.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies/mean_reversion.yaml) still has `timeframe_sec: 180` |
| `XRPUSDT` -> `md_amr` only | Reasonable as ownership split, not live-ready | XRP should not return to MR from this evidence; WAL and order log show `md_amr` activity on XRP via safety-gate rejects, but no direct open/fill evidence on XRP |
| `BNBUSDT` -> `md_amr` only | Not live-ready | [md_amr.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies/md_amr.yaml) has no explicit `BNBUSDT` asset block; WAL shows BNB market data and generic `NRR-046` tick-ignore events, but no `mdamr-*` BNB proposal/open/order lifecycle |

Net assessment:
- The operator split is directionally correct for ownership isolation.
- It is not sufficient by itself to make the next run launch-ready.

## Step 2: Final Regime Decisions

| Regime | Decision | Basis | Restriction |
| --- | --- | --- | --- |
| `MEAN_REVERSION` | `TRADE` | best observed regime, net PnL `+293.57` | live trading allowed for `aurora`; MR only after timeframe correction |
| `UNCERTAIN` | `DISABLE` | net PnL `-141.67`; detector confidence fixed at `0.42`; frequent post-entry regime flips | hard no-trade at runtime |
| `LOW_VOLATILITY` | `TRADE WITH RESTRICTIONS` | net PnL negative overall, but not uniformly bad; BTC aurora LOW_VOL was positive | allow only `BTCUSDT` for `aurora`; do not generalize LOW_VOL to MR taxonomy |
| `HIGH_VOLATILITY` | `TRADE WITH RESTRICTIONS` | weak sample, mildly negative; not the dominant loss driver | keep reduced-risk posture; monitor stopout density and maker-only rejects |
| `TREND_UP` | `TRADE WITH RESTRICTIONS` | insufficient direct sample in this window, but aurora is designed for trend regimes | aurora only; require strict monitoring |
| `TREND_DOWN` | `TRADE WITH RESTRICTIONS` | insufficient direct sample in this window, but aurora is designed for trend regimes | aurora only; require strict monitoring |

## Step 3: Final Strategy Decisions

| Strategy | Decision | Basis | Restriction |
| --- | --- | --- | --- |
| `aurora` | `ENABLE WITH RESTRICTIONS` | profitable in the observed live window | `UNCERTAIN` off; `LOW_VOLATILITY` only on `BTCUSDT`; enforce mutex/arbitration before broad rollout |
| `mean_reversion` | `ENABLE WITH RESTRICTIONS` | live window losing overall, but DOGE remains the only acceptable MR candidate | launch only on `DOGEUSDT`; do not arm live while `timeframe_sec` remains `180`; if `180` remains, treat MR as `SHADOW ONLY` |
| `md_amr` | `SHADOW ONLY` | direct WAL evidence shows it is active, but most intents are blocked by arbitration/safety gates; XRP has reject-only evidence; BNB has no direct md_amr lifecycle evidence | no live orders on `XRPUSDT` or `BNBUSDT` next run |

## Step 4: Final Risk / Execution Recommendations

### TP/SL

- Set `UNCERTAIN` to no-trade. Do not retune TP/SL for a regime that should be blocked.
- Do not use wider SL as the primary LOW_VOL fix. In the LOW_VOL audit, `0/6` losing LOW_VOL trades became profitable across the tested TP/SL grid.
- Keep `BTCUSDT` aurora LOW_VOL TP/SL unchanged for the next restricted run; it is the only aurora LOW_VOL symbol with positive evidence.
- Do not launch `ETHUSDT` or `SOLUSDT` aurora in LOW_VOL; this is a symbol-selection decision, not a TP/SL optimization problem.
- For `mean_reversion`, prioritize timeframe correction before TP/SL retuning. The observed live failure mode is entry timing, not an execution-side stop geometry problem.
- For `md_amr`, do not tune TP/SL for live until the strategy proves fillability and non-blocked operation on its actual assigned symbols.

### Execution / Arbitration

- `P0`: enforce symbol-level mutex before next broad rollout. A confirmed opposite-side overlap already reached pending/intention state.
- `P0`: move arbitration earlier than live intent/pending-order creation. Current arbitration is not early enough.
- `P0`: verify that registry ownership in [strategies.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies.yaml) is actually enforced at runtime. Prior evidence showed assignment drift.
- `P1`: monitor `CANCEL_SUPERSEDED` and touched-after-cancel ratio. The prior run showed plausible fill destruction.
- `P1`: monitor `timeout_cancellation` the same way. A timeout that later trades through the canceled price is evidence of TTL mismatch.

### WAL Precision

Persist these fields explicitly on every completed position:
- exact close fill price
- realized net PnL after fees
- explicit exit reason: `TP`, `SL`, `MANUAL`, `WATCHDOG`, `TIMEOUT`, `ARBITRATION`, `REGIME_BLOCK`
- strategy id at open and close
- regime at open and close
- position id / lifecycle id
- arbitration outcome and rejected strategy id
- safety-gate deny code
- maker-only reject plus fallback decision

## Step 5: Pre-Launch Monitoring Checklist

### By Strategy

- `aurora`: net PnL, fill rate, maker-only reject count, `manual_close` count, LOW_VOL trade count by symbol
- `mean_reversion`: DOGE trade count, long/short split, SL density in first hour, MFE before stop, average hold time
- `md_amr`: intents proposed, intents rejected by reason code, `DEC:OPEN` count, maker-only rejects, symbol split between XRP and BNB

### By Regime

- entry count by regime
- realized PnL by regime
- zero-entry confirmation for `UNCERTAIN`
- LOW_VOL exposure by symbol

### By Cancel / Reject Reason

- `CANCEL_SUPERSEDED`
- `timeout_cancellation`
- `manual_close`
- `MAKER_ONLY_REJECT`
- `ARBITRATION_BLOCKED`
- safety-gate reject codes `NRR-027`, `NRR-028`, `NRR-029`, `NRR-030`

### By Symbol

- `BTCUSDT`: aurora LOW_VOL viability and maker-only reject rate
- `ETHUSDT`: any forbidden LOW_VOL or UNCERTAIN entry must be treated as launch failure
- `SOLUSDT`: any forbidden LOW_VOL or UNCERTAIN entry must be treated as launch failure
- `DOGEUSDT`: MR stopout density and early adverse excursion
- `XRPUSDT`: md_amr reject-only vs open-intent progression
- `BNBUSDT`: any absence of md_amr lifecycle beyond generic market-data traces confirms shadow-only status

### By TP/SL Outcome

- TP count
- SL count
- `UNKNOWN` exit count
- average R by strategy and regime
- SL trades that recover through entry within 3 bars

## Risk-Ranked Action List

### Do Now

1. Set `UNCERTAIN` to hard no-trade in runtime.
2. Enforce symbol-level mutex before next broad rollout.
3. Move arbitration earlier so blocked strategies do not reach live intent or pending-entry state.
4. Do not arm `mean_reversion` live while [mean_reversion.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies/mean_reversion.yaml) remains at `timeframe_sec: 180`.
5. Restrict aurora `LOW_VOLATILITY` to `BTCUSDT` only.
6. Keep `md_amr` on `XRPUSDT` and `BNBUSDT` in shadow only for the next run.
7. Treat missing `BNBUSDT` asset configuration in [md_amr.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies/md_amr.yaml) as a launch blocker for BNB live.

### Do Later

1. Reconcile external `LOW_VOLATILITY` with MR `FLAT_*` taxonomy.
2. Revalidate whether `mean_reversion` should remain DOGE-only after a `300s` run.
3. Revalidate `md_amr` on XRP after shadow evidence exists on its assigned symbol.
4. Decide whether BNB should ever be promoted from shadow after explicit asset configuration and shadow traces exist.
5. Improve WAL lifecycle precision so exit attribution is no longer mark-estimated.

## PRE-LAUNCH CONFIG DECISIONS

- Keep `BTCUSDT`, `ETHUSDT`, `SOLUSDT` on `aurora` only.
- Keep `DOGEUSDT` on `mean_reversion` only.
- Keep `XRPUSDT` and `BNBUSDT` assigned to `md_amr` only as ownership routing, not as live-trading approval.
- Set `UNCERTAIN` to hard no-trade.
- Keep `LOW_VOLATILITY` live only for `BTCUSDT` aurora.
- Keep `ETHUSDT` aurora out of `LOW_VOLATILITY`.
- Keep `SOLUSDT` aurora out of `LOW_VOLATILITY`.
- Return `mean_reversion` to `300s` before enabling `DOGEUSDT` live.
- If `mean_reversion` remains at `180s`, run it in shadow only.
- Run `md_amr` on `XRPUSDT` and `BNBUSDT` in shadow only.
- Do not treat `BNBUSDT -> md_amr` as live-ready until `md_amr.yaml` has explicit asset coverage and shadow traces exist.
- Enforce symbol-level mutex before next broad rollout.
- Verify that registry ownership and regime bans are enforced at runtime, not only declared in YAML.

## Explicit Decision Table For Next Run

| Area | Next-Run State |
| --- | --- |
| `aurora` | `ENABLE WITH RESTRICTIONS` |
| `mean_reversion` | `ENABLE WITH RESTRICTIONS` only after `300s` revert; otherwise `SHADOW ONLY` |
| `md_amr` | `SHADOW ONLY` |
| `UNCERTAIN` | `DISABLE` |
| `LOW_VOLATILITY` | `TRADE WITH RESTRICTIONS` |
| `DOGEUSDT -> mean_reversion` | `LIVE ONLY AFTER 300s REVERT` |
| `XRPUSDT -> md_amr` | `SHADOW ONLY` |
| `BNBUSDT -> md_amr` | `SHADOW ONLY` |

## FINAL VERDICT

**NOT READY**

Reason:
- `UNCERTAIN` hard no-trade is not yet verified as runtime-enforced.
- symbol-level mutex / early arbitration is still a `P0` gap.
- `mean_reversion` is still configured at `180s`, while the acceptable next-run recommendation is DOGE-only after returning to `300s`.
- `BNBUSDT` is assigned to `md_amr`, but [md_amr.yaml](/c:/Users/user/Music/Phenix/config/aurora/strategies/md_amr.yaml) has no explicit `BNBUSDT` asset block and there is no direct `mdamr-*` BNB lifecycle evidence in the reviewed WAL/order logs.

If the `Do Now` items are applied, the system becomes **READY WITH RESTRICTIONS**, not fully ready.
