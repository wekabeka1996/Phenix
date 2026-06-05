# AGENT_REPORT_V1

## verdict
FREEZE_CONTRACT_REPAIRED_AND_VALIDATED

## problem_framing
Package N proved that the active NRR-062 bundle contract was not sealing the decision_ledger at capture time. That left decision-terminal evidence outside the frozen bundle and forced Package N to read current-workspace authority for terminal_status and outcome interpretation. More NRR-062 economics work without sealing decision_ledger would keep authority-sensitive conclusions dependent on mutable workspace state instead of capture-time evidence.

## facts
- Pre-change branch was `main` at commit `34db9a74027833fa4031c232600371664cadb3fe`.
- Pre-change capture script hash for `tools/analysis/capture_nrr062_fresh_cohort.py` was `AF30331D864DDBD4BC732AED25AC2690F72182FD3A979DE4140B0E2D0F308C7F`.
- Pre-change live `logs/shadow_telemetry/decision_ledger_v1.jsonl` existed, had size `1803707` bytes, `356` rows, and sha256 `ea4e79520fb4736a667a8e51b96516d39590571f375a0edc33a2dfd3aa8863b8`.
- The pre-change capture script copied `logs/order_log_v1.jsonl`, `logs/shadow_critical_event_journal_v1.jsonl`, `logs/regime_confidence_audit_v1.jsonl`, `logs/trade_lifecycle.jsonl`, `logs/aurora_core.log*`, optional recorder CSVs, and selected reference reports, but it did not copy `logs/shadow_telemetry/decision_ledger_v1.jsonl`.
- The pre-change capture script did integrate `freeze_config_snapshot(...)` and wrote `config_snapshot_manifest.json` plus the `config_snapshot/` tree.
- The pre-change capture script did not generate `FREEZE_REPORT.md`; Package N had to add that file post-hoc.
- Package N report explicitly recorded that the fresh bundle `logs/frozen/nrr062_fresh_capture_20260529_065313` lacked a frozen decision_ledger surface.
- Package M evidence, read from git history because the root markdown is deleted in the current worktree, confirmed the accepted sidecar baseline remains `execution_position.position_policy_sidecar.mode = enable` and that I/J remain a separate dirty shadow cohort.
- Package O changed `tools/analysis/capture_nrr062_fresh_cohort.py` and `tests/tools/test_capture_nrr062_fresh_cohort.py` only among code files.
- Post-change capture script hash is `57E0821B43D8425CFB83805BDAC334EDCACD8194936D116713F47D30260F39A2`.
- The repaired script now defines `logs/order_log_v1.jsonl`, `logs/shadow_telemetry/decision_ledger_v1.jsonl`, and `logs/trade_lifecycle.jsonl` as required capture surfaces, while `logs/shadow_critical_event_journal_v1.jsonl` and `logs/regime_confidence_audit_v1.jsonl` are optional.
- The repaired script now records `required_missing`, `optional_missing`, `capture_verdict`, `authority_complete`, row counts, min/max timestamps, parse errors, and authority roles in `MANIFEST.json`.
- The repaired script now generates `FREEZE_REPORT.md` during capture.
- Focused pytest on `tests/tools/test_capture_nrr062_fresh_cohort.py` passed with `9 passed in 0.95s` after the repair.
- Final validation sweep passed: `12 passed in 9.10s` for `tests/tools/test_capture_nrr062_fresh_cohort.py`, `tests/tools/test_config_snapshot_freeze.py`, and `tests/test_calibrators_import_boundary.py`.
- Non-invasive smoke capture succeeded into `logs/frozen/package_o_smoke/nrr062_fresh_capture_20260605_133915` with `capture_verdict=CAPTURE_COMPLETE` and `authority_complete=true`.
- The smoke bundle `FREEZE_REPORT.md` records `Decision Ledger Present = True`, `Decision Ledger row_count = 356`, and decision_ledger sha256 `ea4e79520fb4736a667a8e51b96516d39590571f375a0edc33a2dfd3aa8863b8`.
- A direct hash comparison confirmed live and frozen decision_ledger sha256 matched exactly and source/destination size matched exactly.

## inferences
- The root capture-contract defect was not in runtime trading logic; it was in the evidence capture path omitting the decision-terminal authority surface.
- Package N economics should be treated as weaker than a fully sealed bundle because the decision-terminal interpretation was derived from current workspace authority, not from capture-time frozen authority.
- Package O closes that specific authority gap for future bundles by sealing decision_ledger and by emitting a capture-time FREEZE_REPORT.
- The change preserves config snapshot integration and does not alter the accepted enable-vs-shadow cohort interpretation established by Packages M and N.
- A fresh post-repair bundle is now a better authority basis for renewed NRR-062 economics work than the older Package N bundle.

## assumptions
- The active future NRR-062 collection path continues to use `tools/analysis/capture_nrr062_fresh_cohort.py` rather than a different wrapper.
- The current live decision_ledger schema will continue to expose parseable timestamp fields such as `request_ts_ms` and `response_ts_ms`.
- Keeping `config_snapshot_manifest.json` at bundle root is acceptable because Package O was constrained to evidence hardening only and not to unrelated snapshot path redesign.

## unknowns
- Whether future operators will want `logs/shadow_critical_event_journal_v1.jsonl` or `logs/regime_confidence_audit_v1.jsonl` promoted back to required surfaces for some other package lineage.
- Whether a fresh N-only replay rerun after the repaired capture contract will materially change the Package N economics narrative.
- Whether any downstream report generator assumes the older MANIFEST shape and needs its own compatibility update later.

## capture_contract_audit
| Surface | Before | After | Required | Notes |
| --- | --- | --- | --- | --- |
| logs/order_log_v1.jsonl | copied and probed only | copied, probed, and instrumented in MANIFEST/FREEZE_REPORT | yes | still blocks capture when absent because the cohort anchor is missing |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | not copied | copied into bundle and instrumented in MANIFEST/FREEZE_REPORT | yes | key Package O repair |
| logs/trade_lifecycle.jsonl | copied without parse stats | copied with row_count, min/max ts, parse_errors | yes | now participates in authority completeness |
| logs/shadow_critical_event_journal_v1.jsonl | hard-required | optional | no | still copied when present |
| logs/regime_confidence_audit_v1.jsonl | hard-required | optional | no | still copied when present |
| FREEZE_REPORT.md | absent from capture path | generated during capture | yes | no more Package-N-style post-hoc report sealing |
| MANIFEST.json | no capture_verdict / authority_complete / row stats | explicit verdict, completeness, missing lists, parse stats | yes | missing authority is now machine-visible |
| config snapshot | integrated | integrated unchanged | yes | Package O preserved existing snapshot pathing |

## required_surfaces
| Surface | Role | Required | Bundle Path |
| --- | --- | --- | --- |
| logs/order_log_v1.jsonl | Primary NRR-062 reject and override-admission evidence surface | yes | logs/order_log_v1.jsonl |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | Decision-terminal authority surface | yes | logs/shadow_telemetry/decision_ledger_v1.jsonl |
| logs/trade_lifecycle.jsonl | Downstream lifecycle/fill/close evidence surface | yes | logs/trade_lifecycle.jsonl |
| logs/shadow_critical_event_journal_v1.jsonl | Raw shadow journal diagnostics | no | logs/shadow_critical_event_journal_v1.jsonl |
| logs/regime_confidence_audit_v1.jsonl | Regime-confidence diagnostics | no | logs/regime_confidence_audit_v1.jsonl |
| data/recorder/... when requested | Recorder bars for coverage/replay support | no | data/recorder/<date>/<symbol>_<tf>.csv |
| config_snapshot/ + config_snapshot_manifest.json | Frozen config authority snapshot and manifest | yes | config_snapshot/ plus config_snapshot_manifest.json |
| MANIFEST.json | Machine-readable freeze manifest | yes | MANIFEST.json |
| FREEZE_REPORT.md | Human-readable capture verdict | yes | FREEZE_REPORT.md |

## changes_made
- tools/analysis/capture_nrr062_fresh_cohort.py
- tests/tools/test_capture_nrr062_fresh_cohort.py
- NRR062_CAPTURE_CONTRACT_AUDIT.md
- nrr062_capture_contract_audit.json
- NRR062_FREEZE_REQUIRED_SURFACES.md
- nrr062_freeze_required_surfaces.json
- CALIBRATORS_NRR_PACKAGE_O_FREEZE_CONTRACT_DECISION_LEDGER_REPAIR_REPORT.md

## smoke_result
| Check | Result | Notes |
| --- | --- | --- |
| Smoke capture created dedicated bundle | PASS | logs/frozen/package_o_smoke/nrr062_fresh_capture_20260605_133915 |
| decision_ledger copied into bundle | PASS | present at logs/shadow_telemetry/decision_ledger_v1.jsonl |
| MANIFEST includes decision_ledger metadata | PASS | row_count=356, parse_errors=0, sha256 present |
| FREEZE_REPORT generated by capture script | PASS | bundle root FREEZE_REPORT.md exists |
| config snapshot still integrated | PASS | config_snapshot/ tree plus config_snapshot_manifest.json present, required_present=8/8 |
| decision_ledger hash verified | PASS | live and frozen sha256 both ea4e79520fb4736a667a8e51b96516d39590571f375a0edc33a2dfd3aa8863b8 |
| capture verdict visible | PASS | CAPTURE_COMPLETE with authority_complete=true |

## validation
- `py -3 -m pytest tests/tools/test_capture_nrr062_fresh_cohort.py -q`
  - output: `9 passed in 0.95s`
- `py -3 tools/analysis/capture_nrr062_fresh_cohort.py --out-dir logs/frozen/package_o_smoke`
  - output: `status=CAPTURED`, `capture_verdict=CAPTURE_COMPLETE`, `authority_complete=true`, `freeze_path=logs/frozen/package_o_smoke/nrr062_fresh_capture_20260605_133915`
- `py -3 -m compileall tools/analysis/capture_nrr062_fresh_cohort.py tools/analysis/config_snapshot.py`
  - output: command completed with no compile errors
- `py -3 -m pytest tests/tools/test_capture_nrr062_fresh_cohort.py tests/tools/test_config_snapshot_freeze.py tests/test_calibrators_import_boundary.py -q`
  - output: `12 passed in 45.31s`
- Decision-ledger integrity check:
  - source sha256 = destination sha256 = `ea4e79520fb4736a667a8e51b96516d39590571f375a0edc33a2dfd3aa8863b8`
  - source size = destination size = `1803707`
- Manifest / FREEZE_REPORT parse checks:
  - smoke MANIFEST.json parsed successfully
  - smoke FREEZE_REPORT.md exists and contains capture verdict, decision_ledger status, and config snapshot summary

## runtime_behavior_change
- trading behavior changed: no
- NRR-062 behavior changed: no
- sidecar behavior changed: no
- config values changed: no
- YAML changed: no
- Pydantic production config changed: no
- runtime Python changed: no
- new events/commands added: no
- registry changed: no
- evidence capture behavior changed: yes

## risks
- Bundles are now larger because decision_ledger is copied into every future NRR-062 frozen capture.
- If decision_ledger is missing in a future run, the bundle can still be created, but it will now be visibly incomplete via `required_missing`, `capture_verdict`, `authority_complete=false`, and FREEZE_REPORT warnings.
- This repair hardens evidence capture only; it does not itself prove NRR-062 economics, replay alignment, or production readiness.

## next_recommended_package
RERUN_PACKAGE_N_WITH_REPAIRED_FREEZE_CONTRACT
