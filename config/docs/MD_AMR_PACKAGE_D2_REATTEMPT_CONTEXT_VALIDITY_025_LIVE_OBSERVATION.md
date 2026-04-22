# MD_AMR Package D.2 Re-Attempt - Context Validity 0.25 Live Observation

## 1. Observation Window

- Post-fix live/testnet observation window used in this package: 2026-04-18 15:52:56 to 2026-04-18 21:59:30 local log time (2026-04-18T12:52:56Z to 2026-04-18T18:59:30Z), total duration 6:06:34.
- Window start anchor: `logs/domain_decision_making.log` records `MD_AMR registered ... symbols=['XRPUSDT'] tf=900` at 2026-04-18 15:52:56.
- Window contains one explicit restart contour at 2026-04-18 15:52:57 local via `CLEAN_START_UPGRADE`, but the same log line explicitly says `zero-positions confirmation` for XRPUSDT.
- Window end anchor: latest post-fix runtime activity across the used artifacts lands at approximately 2026-04-18 21:59:27 to 21:59:30 local.
- Observed live md_amr symbol surface in this runtime was narrower than the YAML enablement surface: the handler registered only XRPUSDT, even though the production md_amr YAML still marks ETHUSDT, SOLUSDT, and XRPUSDT as enabled.

## 2. Artifact Inventory

| Artifact | Time Range Used | Why It Was Used | What It Proved |
|---|---|---|---|
| `config/docs/MD_AMR_PACKAGE_D1_MATCHED_COHORT_ANALYSIS.md` | static SSOT reference | replay baseline and prior D.1 candidate thesis | CV 0.25 remained the only replay-derived candidate worthy of future study |
| `config/docs/MD_AMR_PACKAGE_D2_PRE_ENTRY_ANCHOR_PERSISTENCE_REPORT.md` | static SSOT reference | precondition package boundaries and intended live proof surface | D.2-PRE fixed persistence narrowly but did not itself collect live proof |
| `config/aurora/strategies/md_amr.yaml` | static config reference | frozen baseline and live advisory contracts | `max_hold_bars=16`, `target_approach_pct=0.0`, `entry_anchor_persistence.storage_path` defined, C.4 remains advisory-only |
| `logs/domain_decision_making.log` | 2026-04-18 15:52:56 to 21:59:27 local | startup, registration, restart contour | md_amr handler bound only XRPUSDT; one clean-start contour occurred with zero positions |
| `logs/shadow_critical_event_journal_v1.jsonl` | 2026-04-18T12:52:56Z to 2026-04-18T18:59:27Z | authoritative decision-event audit surface | exactly 3 md_amr live events were observed, all `EVT:TRADE_INTENT_REJECTED` on XRPUSDT |
| `logs/trade_lifecycle.jsonl` | 2026-04-18T12:52:56Z to 2026-04-18T18:59:27Z | active lifecycle / hold-state proof surface | 4,844 XRPUSDT records appeared, all `POSITION_POLICY_SIDECAR_SUPPRESSED` with `no_manage_flow_for_symbol`; no active XRP lifecycle existed |
| `logs/aurora_events.jsonl` | full file | order/fill proof surface | no XRPUSDT order-state events were emitted in the observation window |
| `logs/aurora_core.log`, `.1`, `.2` | post-fix slices containing 20:15, 21:30, 21:45 local rejects | corroborating text log surface | repeated `MD_AMR_REGIME_GATE_BLOCKED` lines align with the three XRPUSDT rejects |
| `ops/restore/md_amr_entry_anchor_state_v1.json` | artifact snapshot at 2026-04-18T09:43:18.882Z | persisted-anchor audit surface | artifact existed, but contained one BNBUSDT record only; no XRPUSDT persisted anchor record was present |

Additional direct scan result across the used live logs:

- Observed matches for `context_validity`: 0
- Observed matches for `context_penalty_reason`: 0
- Observed matches for `hold_quality`: 0
- Observed matches for `progress_pct`: 0
- Observed matches for `entry_target_price`: 0
- Observed matches for `MD_AMR_C1_ANCHOR_`: 0
- Observed matches for `MD_AMR_C4_CONTEXT_FALLBACK_UNKNOWN`: 0

This matters: the live window did not merely lack non-null CV scores; it lacked the entire in-position C.1/C.3/C.4 trace surface.

## 3. Anchor Restoration Audit

### Restart contour actually observed

| Case | Symbol | Evidence | Result |
|---|---|---|---|
| clean-start contour | XRPUSDT | `logs/domain_decision_making.log` records `[CLEAN_START_UPGRADE] XRPUSDT execution restore upgraded COLD->RESTORED via canonical position-tracking zero-positions confirmation` | restart happened, but this was not a holdover case |

### Required holdover-restoration checks

| Check | Live Result | Evidence |
|---|---|---|
| persisted target loads | not proven for active live symbol | persisted artifact existed, but only for BNBUSDT; no XRPUSDT record was present in `ops/restore/md_amr_entry_anchor_state_v1.json`; no runtime load marker was observed in logs |
| execution entry price reconstructed | not observed | restart contour explicitly confirmed zero positions; no live XRP position existed to reconstruct from execution truth |
| `_entry_anchor` restored | not observed | no holdover position, no anchor-restore marker, and no downstream C.1/C.4 traces |
| `progress_pct` available downstream | no | zero `progress_pct` matches across the live logs |
| `hold_quality` available downstream | no | zero `hold_quality` matches across the live logs |
| `context_validity` available downstream | no | zero `context_validity` matches across the live logs |

### Audit conclusion

The post-fix live window does not disprove the D.2-PRE implementation, but it also does not provide the proof surface D.2 needed. A restart contour was observed, yet it was a zero-position clean-start contour rather than a restart-holdover restoration. Therefore the most load-bearing proof surface remains unproven in live/testnet.

## 4. Per-Trade Context Validity Extraction

The live window did not produce any actual md_amr hold. The observable md_amr cases were limited to one zero-position restart contour and three fresh-entry rejects.

| Case | Path Class | Symbol | Timestamp (UTC) | Lifecycle Outcome | Min CV | Final CV | CV State Sequence | `CV < 0.25` Counterfactual |
|---|---|---|---|---|---|---|---|---|
| restart_xrpusdt_clean_start | restart_no_holdover | XRPUSDT | 2026-04-18T12:52:57.283Z | no position on restart; no restore attempt provable | NA | NA | none observed | not evaluable |
| fresh_reject_1 | fresh_entry_blocked_pre_hold | XRPUSDT | 2026-04-18T17:15:03.879Z | rejected before order emission | NA | NA | none observed | not evaluable |
| fresh_reject_2 | fresh_entry_blocked_pre_hold | XRPUSDT | 2026-04-18T18:30:05.343Z | rejected before order emission | NA | NA | none observed | not evaluable |
| fresh_reject_3 | fresh_entry_blocked_pre_hold | XRPUSDT | 2026-04-18T18:45:09.581Z | rejected before order emission | NA | NA | none observed | not evaluable |

Important distinction:

- There were zero live CV observations.
- There were also zero observed `UNKNOWN/MISSING_CONTEXT` snapshots.
- This is not evidence that restoration succeeded. It is evidence that no post-fix md_amr in-position scoring surface was reached at all.

## 5. Live Distribution Summary

### Q1. Does live/testnet now produce non-null `context_validity`?

No.

Measured counts in the post-fix window:

| Metric | Count |
|---|---|
| non-null `context_validity` observations | 0 |
| observed `UNKNOWN/MISSING_CONTEXT` snapshots | 0 |
| live md_amr in-position hold snapshots | 0 |
| fresh-entry path CV observations | 0 |
| restart-holdover path CV observations | 0 |
| symbols with non-null CV observations | none |

By symbol:

| Symbol | Registered In Runtime | md_amr decision events | actual md_amr holds | non-null CV |
|---|---|---:|---:|---:|
| XRPUSDT | yes | 3 rejects | 0 | 0 |
| BNBUSDT | no | 0 | 0 | 0 |
| ETHUSDT | no runtime proof | 0 | 0 | 0 |
| SOLUSDT | no runtime proof | 0 | 0 | 0 |

Distribution summary:

- score range: not available
- mean: not available
- median: not available
- state distribution: VALID 0, WEAKENING 0, INVALID 0, UNKNOWN 0 observed

The zero-state result is a zero-sample result, not a healthy-distribution result.

## 6. 0.25 Counterfactual Analysis

### Q4. What would `CV < 0.25` have flagged in live?

Nothing evaluable was produced in this post-fix window.

| Counterfactual Surface | Result |
|---|---|
| trades or hold snapshots flagged by `CV < 0.25` | 0 evaluable |
| losing trades potentially helped | 0 measurable |
| profitable trades potentially harmed | 0 measurable |
| pre-entry rejects that can be thresholded by CV | 0 |

Reason:

- all three live md_amr fresh-entry attempts were blocked by the regime gate before order emission;
- the one observed restart contour contained zero positions;
- no in-position `context_validity` scores existed to threshold.

Therefore this package cannot claim either help or harm for `CV < 0.25` under live conditions.

## 7. Slow Reversion Risk Review

The required slow-reversion question also remains unproven in live.

| Question | Live Result |
|---|---|
| were any slow profitable reversion analogues observed after the fix? | no |
| did any live hold dip below 0.25 and later recover profitably? | not observable |
| did `CV < 0.25` threaten profitable slow reversions in live? | not measurable |

Because no post-fix md_amr hold was observed, there is no live evidence either supporting or falsifying the replay-derived slow-reversion safety thesis.

## 8. Replay vs Live Comparison

### D.1 replay thesis used for comparison

- D.1 replay dataset: 369 total trades, 353 overlay-equipped trades.
- Combined replay CV correlation to returns: `r = 0.4134`.
- Combined replay median CV split: below `0.302` vs at-or-above `0.302`.
- Published replay quartile surface: Q1 `< 0.244`, Q4 `>= 0.381`.
- Slow profitable replay reversions (n=19) had mean CV `0.341`, median CV `0.326`, minimum CV `0.228`.
- Replay counterfactual at `CV < 0.25`: 95 trades removed, 73 bad removed, 22 good removed, `+0.294` PnL delta, 2 of 19 slow reversions lost.
- Replay by symbol at `CV 0.25`: BNBUSDT lost 2 of 8 slow reversions; XRPUSDT lost 0 of 11.

### Live comparison outcome

| Comparison Surface | Replay | Live Re-Attempt | Assessment |
|---|---|---|---|
| symbol surface | BNBUSDT and XRPUSDT | XRPUSDT only in runtime | narrower live surface |
| scored CV observations | 353 overlay-equipped replay trades | 0 live scored holds | no distributional comparison possible |
| score range / quartile surface | published replay quartiles available | no live scores | not comparable |
| mean / median | replay median published; slow-reversion mean and median published | no live scores | not comparable |
| state distribution | not published in D.1 report | zero observed live states because zero sample | not comparable |
| fresh-entry vs restored-hold path split | not explicitly segmented in D.1 report | fresh-entry path = 3 rejects, restored-hold path = 1 zero-position contour | live path split observed but unscored |
| restart-holdover restoration | replay assumed populated overlay data | no live holdover restore case observed | not proven live |

### Q3. Does live CV distribution now resemble the replay surface enough to continue the study?

No distributional resemblance can be claimed from this re-attempt.

This is not because live contradicted replay. It is because live never produced a usable CV surface after the fix within the bounded observation window.

## 9. What Is Proven

1. The post-fix md_amr runtime bound only XRPUSDT in the observed live/testnet window.
2. One restart contour occurred after the fix, and it explicitly confirmed zero positions rather than a holdover position.
3. Exactly three md_amr live decision events were observed after startup, all `EVT:TRADE_INTENT_REJECTED` on XRPUSDT with `REGIME_GATE_BLOCKED` and `REGIME=LOW_VOLATILITY`.
4. No XRPUSDT md_amr order-state or fill surface appeared in `logs/aurora_events.jsonl` during the observation window.
5. No active XRP lifecycle surface appeared in `logs/trade_lifecycle.jsonl`; all 4,844 XRPUSDT records in the window were `POSITION_POLICY_SIDECAR_SUPPRESSED` with `no_manage_flow_for_symbol`.
6. No live `progress_pct`, `hold_quality`, `context_validity`, `context_penalty_reason`, anchor marker, or C.4 fallback marker was observed in the used logs.
7. This package made no behavioral, threshold, or config changes.

## 10. What Remains Unproven

1. Whether persisted target state is actually loaded for the active live symbol during startup.
2. Whether execution entry price is reconstructed from canonical execution truth during a real restart-holdover case.
3. Whether `_entry_anchor` is restored in live/testnet when both trusted parts exist.
4. Whether `progress_pct`, `hold_quality`, and `context_validity` become available downstream after a real holdover restore.
5. Whether live `context_validity` scores resemble the D.1 replay surface by range, median, mean, or state mix.
6. Whether `CV < 0.25` would help losing live trades or harm profitable live trades.
7. Whether slow profitable live reversions would dip below `0.25` and later recover.

## 11. Promotion-Study Readiness Assessment

### Q5. Does CV 0.25 remain worthy of future promotion study?

Still insufficient evidence.

Reasoning:

- D.1 remains the frozen replay basis for considering `CV 0.25` a candidate.
- This D.2 re-attempt did not falsify that replay thesis.
- However, it also did not advance the live proof surface enough to justify promotion-study readiness.

The blocker is no longer the already-fixed code defect itself. The blocker is evidence insufficiency in the observed post-fix live window:

- zero live non-null CV observations,
- zero live `UNKNOWN/MISSING_CONTEXT` observations,
- zero live md_amr holds,
- zero live restart-holdover restore cases.

Therefore the correct governance posture is:

- do not tune thresholds,
- do not promote CV 0.25,
- do not open a promotion package off this live re-attempt alone,
- continue only with an extended live observation window that actually captures scored fresh-entry holds and, ideally, at least one real restart-holdover restore case.

## 12. Final Verdict

EVIDENCE INSUFFICIENT — EXTENDED LIVE OBSERVATION REQUIRED
