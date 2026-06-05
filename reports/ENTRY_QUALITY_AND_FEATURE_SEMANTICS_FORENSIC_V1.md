# ENTRY_QUALITY_AND_FEATURE_SEMANTICS_FORENSIC_V1

Final verdict code: POSITION_MANAGEMENT_STATIC_GAP

## Scope
Read-only forensic audit. Код, YAML, схеми, тести, конфіги та runtime поведінка не змінювалися. Primary financial truth: logs/order_log_v1.jsonl.

## Proven Facts
- Активовано 27 реальних ENTRY lifecycle(s); неактивованих entry-order без fill: 6.
- Primary money-truth джерело: logs/order_log_v1.jsonl. Secondary: logs/trade_lifecycle.jsonl, domain_* logs, recorder CSV.
- Recorder data доступні у tf_sec=[180, 300, 900] для символів activated inventory.
- Decision ledger у logs/shadow_telemetry/decision_ledger_v1.jsonl: відсутній.
- Серед 27 activated entries стратегії розподілені так: {'aurora': 10, 'mean_reversion': 11, 'md_amr': 6}.
- SL-закриттів: 19, TP-закриттів: 4, OPEN: 4.

## Inference Rules
- Entry timing class будується з recorder-window heuristics: range percentile, pre-entry returns, volume/volatility expansion та immediate adverse excursion.
- Feature support/opposition визначається через sign-consistent vote по OBI/TFI/delta_price/depth_imbalance/pillar_sum/macro_resid з окремими warning-флагами для spread/kappa/volume_spike.
- GOOD_ENTRY vs BAD_ENTRY класифікація є forensic inference, а не runtime label системи.

## Telemetry Gaps
- Decision ledger відсутній, тому per-entry exact feature-ingress provenance не завжди доказується по окремому ledger record.
- 1m return не обчислювався: найдрібніший recorder tf у доступному наборі 180s, тому 1m помічено як DATA GAP.
- FeatureEngineering text logs не містять embedded epoch ts; alignment виконано через виведений log offset до domain_decision_making (+3h). Це доказовий, але похідний крок.

## Activated Inventory By Symbol
| Символ | Entries | TP | SL | OPEN | PnL_net_est | Late/Extreme |
| --- | --- | --- | --- | --- | --- | --- |
| BNBUSDT | 3 | 0 | 2 | 1 | -90.854433 | 1 |
| BTCUSDT | 3 | 0 | 3 | 0 | -120.41709 | 1 |
| DOGEUSDT | 11 | 2 | 9 | 0 | -233.885359 | 1 |
| ETHUSDT | 6 | 1 | 4 | 1 | -75.10555 | 0 |
| SOLUSDT | 1 | 0 | 0 | 1 | 0.0 | 0 |
| XRPUSDT | 3 | 1 | 1 | 1 | -46.000953 | 0 |

## Timing Aggregates
| TimingClass | Entries | TP | SL | PnL_net_est |
| --- | --- | --- | --- | --- |
| REVERSAL_TRAP | 11 | 2 | 6 | -202.349668 |
| MEAN_REVERSION_VALID | 8 | 1 | 7 | -174.62159 |
| MID_TREND_CONTINUATION | 5 | 1 | 3 | -29.492169 |
| LOCAL_TOP_BUY | 2 | 0 | 2 | -113.302746 |
| LATE_TREND_CHASE | 1 | 0 | 1 | -46.497211 |

## Feature Usage Aggregates
| FeatureUsageVerdict | Entries | PnL_net_est |
| --- | --- | --- |
| PARTIALLY_USED | 21 | -429.407999 |
| PIPELINE_ONLY | 6 | -136.855385 |

## Key Findings
- Activated entries: 27; no-entry timeouts/cancellations: 6.
- Late/extreme timing classes: 3. Noise class: 0.
- Microstructure opposed or contradicted side at decision snapshot: 5 entries.
- Warning visible before SL: 11. Warning visible but unused: 11.
- Strategy-level usage split: Aurora=partial semantic subset; MeanReversion=bar-semantic core plus direct microstructure veto; md_amr=bar/channel semantic core with limited FE microstructure carry-through.

## Representative Vertical Chains
### rid-c3b2a274dc7fd486
- Факти: DOGEUSDT BUY mean_reversion regime=LOW_VOLATILITY conf=0.17333728956940883 entry=0.11427 close=SL net_est=-92.35971518
- Timing: LOCAL_TOP_BUY | pre-15m=-26.340050046094625 bps | range_pos_15m=1.287037037037042 | reversed_soon=True
- Feature snapshot: support=CONTRADICTORY state=EXHAUSTION_WARNING age_ms=-71 notes=obi_opposes=-0.8069; tfi_opposes=-0.3466; delta_price_opposes_bps=-29.07; pillar_sum_opposes=-0.0218; macro_resid_opposes=-3.0000; volume_spike_extreme=1.0000
- Position management: WARNING_IGNORED | warning_before_sl=True | adaptive_seen=False
- Decision trace: order_log=yes, domain_dm=2, domain_ep=8, trade_lifecycle=8.

### mdamr-66dcd00bdc1de7b8
- Факти: XRPUSDT SELL md_amr regime=LOW_VOLATILITY conf=0.46706123640529734 entry=1.4361 close=SL net_est=-91.69864620999999
- Timing: REVERSAL_TRAP | pre-15m=-2.0889182884793858 bps | range_pos_15m=0.43103448275859296 | reversed_soon=True
- Feature snapshot: support=STALE state=STALE_OR_MISSING age_ms=1716388 notes=snapshot_age_ms=1716388
- Position management: STATIC_ONLY | warning_before_sl=False | adaptive_seen=False
- Decision trace: order_log=yes, domain_dm=0, domain_ep=8, trade_lifecycle=8.

### mdamr-0b475bd3751cfda4
- Факти: BNBUSDT BUY md_amr regime=LOW_VOLATILITY conf=0.85 entry=668.65 close=SL net_est=-69.91140132
- Timing: REVERSAL_TRAP | pre-15m=0.29906765658033796 bps | range_pos_15m=0.08333333333326157 | reversed_soon=True
- Feature snapshot: support=NEUTRAL state=MIXED_SIGNAL age_ms=-32 notes=obi_opposes=-0.6067; pillar_sum_opposes=-0.0350
- Position management: WARNING_IGNORED | warning_before_sl=True | adaptive_seen=False
- Decision trace: order_log=yes, domain_dm=2, domain_ep=8, trade_lifecycle=8.

### aurora_ETHUSDT_1778821204877
- Факти: ETHUSDT SELL aurora regime=TREND_DOWN conf=0.47260790411101244 entry=2262.89 close=TP net_est=87.69980115000001
- Timing: MID_TREND_CONTINUATION | pre-15m=-14.87106959175115 bps | range_pos_15m=0.44275491949907775 | reversed_soon=True
- Feature snapshot: support=SUPPORTS_SIDE state=STRONG_CONFIRMATION age_ms=30 notes=depth_imbalance_opposes=0.9951
- Position management: STATIC_ONLY | warning_before_sl=False | adaptive_seen=False
- Decision trace: order_log=yes, domain_dm=0, domain_ep=8, trade_lifecycle=8.

### rid-66cbd38c5b04afbf
- Факти: DOGEUSDT BUY mean_reversion regime=MEAN_REVERSION conf=0.17395290420184203 entry=0.11352 close=TP net_est=83.06270823
- Timing: REVERSAL_TRAP | pre-15m=-28.10839299046957 bps | range_pos_15m=0.22142857142857283 | reversed_soon=True
- Feature snapshot: support=STALE state=STALE_OR_MISSING age_ms=13120100 notes=snapshot_age_ms=13120100
- Position management: ADAPTIVE | warning_before_sl=False | adaptive_seen=True
- Decision trace: order_log=yes, domain_dm=0, domain_ep=8, trade_lifecycle=8.

### mdamr-82f0419baafb1fd8
- Факти: XRPUSDT SELL md_amr regime=LOW_VOLATILITY conf=0.6460433977072384 entry=1.432 close=TP net_est=45.69769359
- Timing: REVERSAL_TRAP | pre-15m=-0.6982996403756082 bps | range_pos_15m=0.7413793103448091 | reversed_soon=True
- Feature snapshot: support=STALE state=STALE_OR_MISSING age_ms=36815831 notes=snapshot_age_ms=36815831
- Position management: STATIC_ONLY | warning_before_sl=False | adaptive_seen=False
- Decision trace: order_log=yes, domain_dm=0, domain_ep=8, trade_lifecycle=8.

### mdamr-94395dd7f142ad00
- Факти: XRPUSDT BUY md_amr regime=MEAN_REVERSION conf=0.4756662973114831 entry=1.4256000000000002 close=unresolved net_est=None
- Timing: REVERSAL_TRAP | pre-15m=2.1047462026883856 bps | range_pos_15m=0.5403225806451928 | reversed_soon=True
- Feature snapshot: support=STALE state=STALE_OR_MISSING age_ms=30513438 notes=snapshot_age_ms=30513438
- Position management: UNPROVEN | warning_before_sl=False | adaptive_seen=False
- Decision trace: order_log=yes, domain_dm=0, domain_ep=8, trade_lifecycle=8.


## Static Consumption Verdict
- Aurora: entry side/allow використовують реальний semantic subset, але не весь FE surface. EP post-entry semantics мають confirmed gaps (cached ATR contract mismatch, sidecar alias mismatch).
- MeanReversion: entry side йде від BB/RSI/ATR/flat-regime, але існує реальний microstructure veto через TFI/OBI/price_motion/kappa. Це не telemetry-only path.
- md_amr: decision core реальний, але це channel/ATR/dir-score semantics, а не broad FE microstructure. FE carry-through у TPSL/cost є частковим, не повним.

## Final Answers
- 1. Чи входить система запізно: так, це підтверджено для частини activated entries; late/extreme class count=3.
- 2. Чи chase noise: масового noise-chase не доведено; noise count=0.
- 3. Чи плутає exhaustion з confirmation: так у тих entry, де local-extreme/late-chase поєднаний з contradictory або warning-state snapshot перед/відразу після fill.
- 4. Чи використовує microstructure для entry decisions: частково. Aurora використовує вузький subset; MeanReversion має прямий TFI/OBI/price_motion/kappa veto; md_amr decision core переважно bar/channel/ATR-driven.
- 5. Чи використовує microstructure для position management: переважно ні; warning_visible_before_sl=11, visible_but_unused=11.
- 6. Які features decision-critical: aurora pillar_sum/price_motion/liquidity_kappa/macro_resid/regime_confidence; MR bb_pct_b/rsi/atr + TFI/OBI/price_motion/kappa veto; md_amr channel/dir_score/atr_zscore/hold_health.
- 7. Які features генеруються, але не використовуються meaningfully: volume_spike, depth_imbalance та більша частина FE microstructure surface в aurora/md_amr post-entry path; sidecar aliases мають contract gap.
- 8. Чим більше пояснюються losses: у цьому зрізі більше bad entries + static exits, ніж самим ORDER_INTENT; primary loss path = real ENTRY fill -> SL.
- 9. LOW_VOLATILITY losses: змішана причина. Для MR/md_amr не все є noise; але observed losses по LOW_VOL slices часто йдуть через fragile/static post-entry handling і частково через late/extreme entries у non-MR paths.
- 10. Чи є profit edge після фільтра toxic classes: так, TP існує; casebook показує, що TP не зник, а концентрація SL вища у late/extreme/no-warning-ignored slices.

## Output Coverage
- ENTRY_QUALITY_CASEBOOK.csv rows: 27 (повинен дорівнювати activated ENTRY count).
- ENTRY_TIMING_CLASSIFICATION.csv rows: 27.
- ENTRY_FEATURE_CONSUMPTION_MAP.csv rows: 16.
- MICROSTRUCTURE_DECISION_USAGE_MATRIX.csv rows: 193.
- ENTRY_QUALITY_SUMMARY.json final_verdict_code: POSITION_MANAGEMENT_STATIC_GAP.