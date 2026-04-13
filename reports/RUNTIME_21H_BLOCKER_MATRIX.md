# RUNTIME_21H_BLOCKER_MATRIX

| Blocker Class | Symptom | Root Cause | Mechanism | Operational Effect | Severity | Owner Domain | Frequency (window) | Proof Level |
|---|---|---|---|---|---|---|---|---|
| warmup_not_full_ready | CMD:PROCESS_STRATEGY reject/degraded path | Feature readiness not fully satisfied at evaluation time | FE warmup fail_fast enforcement | Repeated suppression windows before full readiness | HIGH | feature_engineering | high recurring | FACT |
| regime_gate_downtrend (NRR-027) | DECISION_INTENT_REJECTED with downtrend blocks | Directional safety gate veto | Decision safety gate deny on trend mismatch | Prevents trade intent emission | HIGH | decision_making | 10 | FACT |
| regime_confidence_gate (NRR-026) | DECISION_INTENT_REJECTED confidence below min | min_regime_confidence threshold active | Confidence threshold gate deny | Late-window no-trade pressure | HIGH | decision_making | 25 | FACT |
| price_motion_or_transition (NRR-028/029/030) | Additional decision rejects | Price-motion and transition protection gates | Sanity gate deny on adverse structure | Localized suppression in volatile periods | MEDIUM | decision_making | 7 | FACT |
| sidecar_startup_grace_suppression | POSITION_POLICY_SIDECAR_SUPPRESSED | Startup grace plus freshness/lifecycle policy suppressors in sidecar shadow flow | suppression reasons dominated by no_manage_flow/features_stale families | Sidecar recommendations frequently suppressed | LOW | position_policy_sidecar | 93964 | FACT |
| exchange_order_reject | ORDER_REJECTED not present | no reject event found | n/a | Not a blocker in this run | LOW | execution_position/exchange path | 0 | FACT |

## Blocker Ranking
1. warmup_not_full_ready (high recurrence + multi-symbol blast radius)
2. regime_confidence_gate (high recurrence in late runtime)
3. regime_gate_downtrend (high impact directional veto)
4. price_motion_or_transition gates (medium recurrence)
5. sidecar startup suppressions (lower severity, expected policy behavior)

## Evidence Anchors
- FeatureEngineering FE_WARMUP and CMD:PROCESS_STRATEGY reject/allow lines in domain_feature_engineering logs.
- DECISION_INTENT_REJECTED NRR code evidence in order_log_v1.jsonl.
- Startup grace sidecar suppression in trade_lifecycle.jsonl.
- ORDER_REJECTED absence in order_log_v1.jsonl searches.
