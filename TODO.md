# TODO

## VF-VERB-REG follow-ups
- VF-VERB-REG-02: periodically review `reports/VF-VERB-REG-02_diff.json` in CI logs and keep registry in sync with runtime.
- VF-VERB-REG-02: switch from warn-only to fail when coverage is ~100% (planned: warn-only → shadow-deny → hard-deny).
- VF-VERB-REG-03: continue replacing `owner: unknown` with real domain owners; add schemas where there is a confirmed JSON schema.
- VF-VERB-REG-04: use `reports/VF-VERB-REG-04_owner_suggestions.json` to batch-update owners with evidence (no guesses).
- VF-VERB-REG-05: gate now fails only when coverage ≥98% and missing>0; keep an eye on the threshold and adjust when registry matures.
- VF-VERB-REG-06: applied all owner suggestions with confidence ≥70%; next is to rerun VF-VERB-REG-04 regularly and batch-apply new high-confidence suggestions.
- VF-VERB-REG: decide SSOT policy for wildcards (keep default false; `UPD` currently allowed by policy).

## SOLUSDT / Aurora follow-ups (2026-02-13 forensic)
- Decide: disable FLIP for `SOLUSDT` vs restrict regimes (`UNCERTAIN`/`HIGH_VOLATILITY`) for entries.
- Adjust SOL exit RR guardrails: `take_profit.tp_low_ratio` and/or `exit.regime_tpsl.min_tp_rr`; re-run a short live-sim/backtest.
- Fix `NRR-046` flip CLOSE rejects: audit `execution_position.pending_entry_ttl` expectations for tf_sec=0/None and pick a safe TTL policy.
- Reduce `MAKER_ONLY_REJECT` frequency: tune `aurora.assets.SOLUSDT.volatility_entry_logic.regime_multipliers` and/or revisit `aurora.execution.entry_tif`.
- Add a grep/script to surface bracket fill/close events (SL/TP) for postmortems (WAL currently shows closure via ACCOUNT_UPDATE only).

## SOL follow-ups after TASK-SOL-REGIME-BLOCK-01 / TASK-SOL-SL-TIGHTEN-01 (2026-02-13)
- Regime gate is now strict for SOL (`UNCERTAIN` removed). Monitor live WAL for drop in `SOLUSDT` intents during `UNCERTAIN`.
- Keep `sl_pct=0.0135` for 1-2 sessions and compare stop-hit rate vs prior baseline (`0.01512`).
- Sizing verdict recorded: `REGIME-AWARE SIZING = YES` in DecisionMaking via `regime_sizing -> margin_pct_mult`.
- Decide if to add explicit `SOLUSDT.regime_sizing.DEFAULT` and/or `UNCERTAIN: 0.0` (or keep only allowlist gating).
- Optional next package (separate commit): additive `notional_mult_by_regime` schema/model/tests if we want deterministic per-regime size policy.

## EP-IDEMPOTENT-CANCEL-2011 (2026-02-24)

- [ ] EP-IDEMPOTENT-CANCEL-2011: P0 implemented (exception-path absorb + truthful _do_cancel gating). Close after merge.
- [ ] EP-IDEMPOTENT-CANCEL-2011-P1: optional in-flight cancel dedup in separate package.
## EP-01.3-SUPERSEDE-FILL-RACE-GUARD-P0 (2026-02-24)
- [ ] EP-01.3-SUPERSEDE-FILL-RACE-GUARD-P0 implemented; close only after merge.
