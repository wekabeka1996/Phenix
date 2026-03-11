# Aurora / Phenix — Independent Runtime Audit Report

> **Method:** Code-only. Sources traced: [apps/reference/main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py), [bootstrap/](file:///c:/Users/user/Music/Phenix/apps/reference/main.py#182-206), [config/aurora/domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml), all `contracts/`, `domains/market_data/`, `domains/feature_engineering/`, `domains/decision_making/`, `domains/regime_detector/`, `domains/strategies/`. Markdown docs, roadmaps, and previous audit reports are ignored as sources of truth.

---

## 1. Active Runtime Topology

### Entrypoint
[apps/reference/main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) is the single entrypoint. It runs a `asyncio.run(main())` style bootstrap:

| Step | What happens | Evidence |
|---|---|---|
| 1 | Logging + config load (`load_aurora_config`) | `main.py:~40-80` |
| 2 | Startup instrument validation (ping exchange) | [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) — `validate_startup_instruments` |
| 3 | WAL GC, AlertManager, EntropyMonitor init | before domain build |
| 4 | **[build_live_domains(config)](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/domain_builder.py#50-136)** → [LiveDomainBundle](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/domain_builder.py#25-39) | [bootstrap/domain_builder.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/domain_builder.py) |
| 5 | DR: `find_latest_snapshot()` → `replay_wal_after()` | only for `position_tracking` domain |
| 6 | [build_startup_analytics_restore_report()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/runtime_analytics_restore.py#311-373) | reporting only — **does NOT gate startup** |
| 7 | [build_startup_hydration_plan()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py#298-330) | reporting only — **does NOT gate startup** |
| 8 | Domains started sequentially; [StrategyRuntime](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#108-138) loads plugins | [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) |
| 9 | `AsyncLoopRuntime` for market data | separate thread |

### Active Domain Bundle ([LiveDomainBundle](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/domain_builder.py#25-39))
| Domain | Class | Notes |
|---|---|---|
| `market_data` | `MarketDataConnector` or `MarketDataProxy` | Conditional on `config.domains.market_data.use_proxy` |
| `feature_engineering` | `FeatureEngineering` | 89 KB; includes pillars, resampler, macros |
| `regime_detector` | `RegimeDetector` | single file, 28 KB |
| `risk_management` | wired | |
| `execution_position` | wired | |
| `decision_making` | `DecisionMaking` | 27 KB facade hosting [AuroraHandler](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#153-673), `MRHandler`, `mdAmrHandler`, [StrategyGateway](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py#22-797) |

### Active Strategy Plugins (from [StrategyRuntime](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#108-138))
From `domains/strategies/plugins/` and registry:
- `AuroraBuiltinPlugin` → [AuroraHandler](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#153-673)
- `MeanReversionPlugin` → `MeanReversionHandler` (FE-hosted strategy in [feature_engineering/mean_reversion_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/mean_reversion_strategy.py))
- `MDAMRPlugin` → [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py) (70 KB)
- `LlmMicrostructurePlugin` — registered, but conditional on config

### Strategy Assignment (SSOT)
`config/aurora/domains.yaml → strategies_registry.assignments` is the authoritative source.
- `AuroraHandler._is_symbol_enabled()` checks registry first, then falls back to legacy `aurora.assets.enabled`.
- **Risk:** dual assignment checks — potential divergence if both are configured inconsistently.

---

## 2. Canonical Bar Identity — Contract Adoption

### Contract defined: ✅
[contracts/runtime_bar_identity.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py) — [CanonicalBarIdentity](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#40-83), [CanonicalReplayIdentity](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#15-38), [RuntimeBarSourceMode](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#8-13) (LIVE / REPLAY / HYDRATION / BACKTEST).

### Attached at emission: ✅
`market_data/bar_aggregator.py:_emit_bar_closed()` calls [build_canonical_bar_identity()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#98-124) and [attach_canonical_bar_payload()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#282-309) on both the **WAL write** and the **FSM emit** payloads.

### Consumed at decision: ✅ (partially)
`aurora_decision.py:_process_decision()` calls [extract_canonical_bar_identity(cmd, ...)](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#126-236) to read `bar_end_ts_ms` — used as `bar_close_ts`.  
`aurora_handler.py:on_process_strategy()` also calls [extract_canonical_bar_identity](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#126-236) for Gate 4 (missing `bar_close_ts`).

### NOT consumed: ⚠️
- [source_mode](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#85-96) field is extracted but **never gates any logic** (LIVE vs REPLAY modes are not distinguished at decision time).
- `replay_generation` is always set to `0` — no replay-generation tracking is active.
- FE ([feature_engineering.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py)) receives `EVT:BAR_CLOSED` — whether it validates the identity before passing to strategies is not confirmed without tracing `feature_engineering.py:on_bar_closed`.

---

## 3. Readiness / Warmup Contract — Adoption State

### Contracts defined: ✅
- [contracts/runtime_readiness.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py) — [RuntimeReadinessScope](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#24-32) (8 scopes), [RuntimeReadinessState](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#16-22) (READY/COLD/PARTIAL/BLOCKED/INVALIDATED_GAP), [RuntimePermissions](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#85-106).
- [contracts/runtime_analytics_restore.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_analytics_restore.py) — [RuntimeAnalyticsRestoreScope](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_analytics_restore.py#26-36) (9 scopes), states, [restore_status_to_readiness_status](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_analytics_restore.py#272-324).

### Startup report built: ✅ (informational only)
`bootstrap/runtime_analytics_restore.py:build_startup_analytics_restore_report()` creates a [StartupAnalyticsRestoreReport](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/runtime_analytics_restore.py#18-50) with per-strategy-per-symbol scope states. Defaults ALL scopes to `COLD` unless:
1. Snapshot was loaded AND `execution_position` had data → `RESTORED`.
2. Strategy handler exposes `describe_runtime_analytics_restore(symbol)` → used as local hint.

### **CRITICAL BLOCKER: Report is NOT gating anything**
[main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) generates the [StartupAnalyticsRestoreReport](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/runtime_analytics_restore.py#18-50) and [StartupHydrationPlanReport](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py#110-126) for observability (e.g., telemetry/logging) **but does not use them to block startup, defer domains readiness, or enforce warmup barriers.** After cold start, strategies will fire as soon as FE produces `warmup.full_ready=True` regardless of analytics restore state.

### Readiness flow in AuroraDecisionMixin:
[aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) imports [restore_status_to_readiness_status](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_analytics_restore.py#272-324) and [combine_restore_permissions](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_analytics_restore.py#326-342) from the analytics restore contract — evidence they ARE used inside [_process_decision](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py#90-879). The `_analytics_restore_snapshots` dict is stored on [AuroraHandler](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#153-673) and [apply_runtime_analytics_restore_snapshot()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#228-235) is defined. **However — the mechanism to push snapshots from the startup report INTO the handler at boot is not confirmed.** If that wiring is missing, the handlers boot with empty `_analytics_restore_snapshots` dicts and proceed unguarded.

### Warmup enforcement actually active:
| Gate | Location | Behavior |
|---|---|---|
| FE warmup (`full_ready`) | `aurora_decision.py:_process_decision` L115 | Fail-closed if `enforcement_mode == "fail_fast"` (default); falls through on `warn_only`/`disabled` |
| Regime warmup | `readiness_gates.py:warmup_gate_before_trade_intent()` | Checks `per_symbol_regimes[symbol]["warmup"]["full_ready"]` |
| Features TTL | `readiness_gates.py:features_ready()` | Bar-aware TTL + ancient bar safety guard |
| Regime liveness heartbeat | `aurora_decision.py:_process_decision` L150 | Fail-closed — blocks if no heartbeat ever received |
| Strategy gateway warmup | `strategy_gateway.py:Gate 6` | Calls `dm._warmup_gate_before_trade_intent(...)` again |

**These are OLD-STYLE dict-based checks, not [RuntimeReadinessScope](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#24-32)-based checks.** The new contract [RuntimeReadinessScope](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#24-32) is DEFINED and used in [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) for payload construction but doesn't replace the legacy dict-based warmup gates.

---

## 4. Gap Policy Contract — Adoption State

### Contract defined: ✅
[contracts/runtime_gap_policy.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_gap_policy.py) — `attach_gap_status_payload`, `extract_gap_status`, `build_trading_status_from_gap`, `gap_blocks_open_new_risk`.

### Attached at bar emission: ✅
`bar_aggregator.py:_emit_bar_closed()` calls `extract_gap_status()` and conditionally `attach_gap_status_payload()` — only if `gap_status is not None` (i.e., `gap_bars_skipped > 0`).

### Consumed at decision: ✅ (imported)
[aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) imports `build_basis_bar_status_from_gap`, `build_trading_status_from_gap`, `gap_blocking_tokens`, `gap_blocks_open_new_risk`. This confirms the gap policy contributes to permission building.

### Gap detection logic: ⚠️
In [bar_aggregator.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/market_data/bar_aggregator.py):
- `gap_bars = (new_bar_start - expected_next) // tf_ms`
- `is_gap = gap_bars > 0`
- Gap is detected per-bar at close time. **No persistent gap state is maintained** — gap info lives only in the EVT:BAR_CLOSED payload.
- If `gap_bars_skipped == 0`, no gap payload is attached, and `extract_gap_status()` returns `None`. FE or decision-making receive bars without gap annotation.

---

## 5. Quadratic Rollout — Adoption State

### Contract: ✅ fully defined and wired
[contracts/quadratic_rollout.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py):
- [QuadraticRolloutMode](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#32-38): LEGACY_LIVE → V2_LIVE → QUADRATIC_SHADOW → QUADRATIC_LIVE → V2_ROLLBACK
- [resolve_requested_quadratic_rollout(decision_cfg)](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#183-214) → reads `scoring_version` and `quadratic_rollout.{shadow_enabled, rollback_armed, rollback_reason_chain}` from config.

### Config-driven mode selection: ✅
From [domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml) (confirmed): `scoring_version` field under `strategies.aurora.decision` determines whether Quadratic kernel is used.

### Shadow evaluation: ✅
`aurora_decision.py:_process_decision()` calls [evaluate_quadratic_shadow()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#222-266) on every bar BEFORE calling the live kernel. Shadow is mode `QUADRATIC_SHADOW` when `shadow_enabled=True` and live kernel is still v2.

### Rollback: ✅
[build_quadratic_rollout_snapshot()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#268-307) checks [rollback_armed](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#79-86) → sets `quadratic_can_open_new_risk=False` if armed.
[apply_live_quadratic_permission_gate()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#309-321) reduces live permissions when in quadratic mode.

### Fallback: ✅
If `QuadraticScoringKernel.compute()` raises, [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) falls back to `AuroraScoringKernel.compute()` with a logged error. Fallback is local-only (no event emitted about the downgrade).

### **ISSUE:** No config validation that `scoring_version` is a valid value.
[resolve_requested_quadratic_rollout()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/quadratic_rollout.py#183-214) does a `.strip().lower()` but any unrecognized string defaults to `LEGACY_LIVE` mode silently.

---

## 6. Strategy Gateway Gate Chain

Full chain in `strategy_gateway.py:process_signal()` — confirmed order:

| Gate | Condition | Action |
|---|---|---|
| Readiness contract | `readiness.warmup_ok != True` | REJECT (except md_amr reduce-only close path) |
| Runtime permissions | `can_open_new_risk == False` for entries | REJECT |
| Risk-skew guard | `until_refresh` flag set | DEFER |
| Gate 0: Strategy arbitration | cross-strategy conflict | REJECT |
| md_amr close path | FULL_CLOSE / PARTIAL_CLOSE | short-circuit to close, bypass sizing gates |
| Gate 1: Risk gate | `is_trading_allowed=False` or `risk_score > max_risk` | REJECT |
| Gate 1.5: Risk-skew + degraded context | `abs(features_ts - risk_ts) > max_skew_sec` | DEFER → eventually NO_TRADE_UNTIL_REFRESH |
| Gate 2: Flip gate | portfolio state unknown | DEFER |
| Gate 3: QoS rate control | rate limit exceeded | DEFER or REJECT (mode-dependent) |
| Gate 4: Exposure / sizing | `entry_price` missing, portfolio missing, sizing=None, exposure check | REJECT |
| Gate 5: Signal TTL | `now_ms - signal_ts_ms > bar_ttl_ms` | REJECT |
| Gate 6: Warmup | `dm._warmup_gate_before_trade_intent()` | REJECT |

**Note:** Warmup is checked **twice** — once in `aurora_decision.py:_process_decision()` and once in Gate 6 of [strategy_gateway.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py). This is redundant but not harmful.

**ISSUE — md_amr trace validation is a mandatory gate:**
For `strategy_id == "md_amr"`, signals with invalid/missing [trace](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py#94-153) dict fields (`dir_score`, `thr_buy`, `thr_sell`, `w_raw`, `w_norm`, `qty_base`, `qty_new`, `conf_ratio`) are **hard rejected** via `REJECT: WAL_TRACE_INVALID`. This means any md_amr signal that skips the trace contract is dead-on-arrival.

---

## 7. Disaster Recovery / WAL / Snapshot

| Component | Status |
|---|---|
| WAL writes | Active — `wal.append(msg.model_dump())` on every `EVT:BAR_CLOSED` and trade intent rejection |
| Snapshot find | `find_latest_snapshot("ops/snapshots")` on startup |
| WAL replay | `replay_wal_after(snapshot_ts)` — only for `position_tracking` domain |
| Analytics restore | Builds report from snapshot [analytics_restore](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#236-241) key if present; defaults all scopes to COLD otherwise |
| **FE/bar-state restore** | ❌ NOT wired — FE bars, pillar state, regime state are ALL cold on restart |
| WAL GC | Runs as background task, configured separately |

**CRITICAL BLOCKER:** After every restart, FE and regime detector start from a cold state. The analytics restore report records this as `COLD` for `BARS`, `FEATURE_ENGINEERING_CACHE`, `REGIME_DETECTOR_STATE`, and `PILLAR_STATE` scopes — but the system does NOT wait for warmup before accepting trades (see Section 3). The warmup gate is the only barrier, and it will clear as soon as regime + FE tick through their warmup windows, with **no historical bar data restored**.

---

## 8. MeanReversion and md_amr Status

### MeanReversion
- Strategy is in [feature_engineering/mean_reversion_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/mean_reversion_strategy.py) (22 KB) — **co-located in FE domain, not decision_making**.
- Also has a [mean_reversion_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/mean_reversion_handler.py) (55 KB) in decision_making.
- Compatibility profile: `required_basis_tf_sec = 300`, `basis_required_bars = min_bars (25)`, `needs_regime = True`, `needs_microstructure = False`, `degraded_mode_allowance = "NON_TRADING_ONLY"`.
- **ISSUE:** `protect_only_capability = False` — MR cannot operate in protect-only mode. If system goes into protect-only readiness, MR is fully dead.

### md_amr
- [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py) is 70 KB — the largest handler in the system.
- Compatibility profile: `required_basis_tf_sec = 900` (15m bars), `basis_required_bars = max(96, channel_window, atr_window, atr_stats_window)` → minimum 96 bars need to be seen.
- `local_hydration_contract = "md_amr_rest_hydration"` — **this hydration contract is named but its implementation and consumption are NOT confirmed in the code traced.** If `md_amr_rest_hydration` is not actually implemented, md_amr has no restore path.
- `degraded_mode_allowance = "PROTECT_ONLY"` → can run in protect-only.
- md_amr signals require a validated [trace](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py#94-153) dict in the signal payload (see Section 6). Any code path in [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py) that fails to attach a properly structured trace will be rejected at the gateway.

---

## 9. Objective Engine Integration

`aurora_decision.py:_process_decision()` includes full Objective Engine integration (L694-800+):
- Gated by `domains.objective_engine.enabled == True` AND `strategies.aurora.objective.enabled == True`.
- Requires `cost` and `behavior` components both enabled.
- Requires `_latest_portfolio`, `_latest_exposure_summary`, [regime](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#410-446), `regime_ts_ms`, and `entry_plan_res` to all be non-None — **any missing raises ValueError and the block is treated as an exception, not a soft fail.**
- `obj_score.is_blocked` → `OBJECTIVE_GATE_BLOCKED` → trade blocked.
- The objective trace is included in signal payload and validated by `strategy_gateway._validate_objective_trace()`.

**If objective engine is enabled and exposure summary is not available** (e.g., early in startup), every trade attempt will raise `OBJECTIVE_EXPOSURE_SUMMARY_MISSING` and be blocked. This is a potential live blocker if exposure summary publication is delayed.

---

## 10. Negative Cases / Hidden Issues

| # | Issue | Location | Severity |
|---|---|---|---|
| N-1 | Analytics restore snapshots built at boot but **not pushed to handlers** — handlers have empty `_analytics_restore_snapshots` if wiring is absent | [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) vs `aurora_handler.apply_runtime_analytics_restore_snapshot()` | 🔴 HIGH |
| N-2 | Hydration plan is informational only — **no actual bar hydration happens** on restart | [startup_hydration_planner.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py), [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) | 🔴 HIGH |
| N-3 | FE/regime state is fully COLD after restart; warmup window is the only barrier and clears quickly | DR section | 🔴 HIGH |
| N-4 | md_amr `local_hydration_contract = "md_amr_rest_hydration"` — contract named but not traced to implementation | [strategy_compatibility_matrix.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py) | 🔴 HIGH |
| N-5 | Dual assignment check for Aurora symbols (registry + legacy assets) — divergence risk | `aurora_handler._is_symbol_enabled()` | 🟡 MEDIUM |
| N-6 | `scoring_version` unrecognized string → silently falls back to LEGACY_LIVE | `quadratic_rollout.resolve_requested_quadratic_rollout()` | 🟡 MEDIUM |
| N-7 | Objective engine raises `ValueError` on missing exposure summary → exception path, not graceful block | `aurora_decision.py:~L729-731` | 🟡 MEDIUM |
| N-8 | Bar identity [source_mode](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#85-96) is always `LIVE` from `bar_aggregator` — replay/hydration bars would also need tagging upstream | `bar_aggregator._emit_bar_closed()` | 🟡 MEDIUM |
| N-9 | Warmup gate checked twice (AuroraDecisionMixin + StrategyGateway Gate 6) | [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py), [strategy_gateway.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/strategy_gateway.py) | 🟢 LOW (redundant, not harmful) |
| N-10 | `replay_generation` always `0` — no replay generation tracking | [bar_aggregator.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/market_data/bar_aggregator.py) | 🟢 LOW |
| N-11 | Quadratic fallback to v2 kernel on exception is not observable (no telemetry event emitted) | `aurora_decision.py:L340-352` | 🟢 LOW |

---

## 11. Questions Answered

| Question | Answer |
|---|---|
| What is actually running in runtime? | [AuroraHandler](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_handler.py#153-673) (v2 or quadratic depending on `scoring_version`), `MeanReversionHandler`, `md_amr_handler`, optional `LlmMicrostructurePlugin`. All gated by `strategies_registry.assignments`. |
| What exists but is NOT wired? | Analytics restore → strategy handler push (N-1). md_amr hydration contract (N-4). [RuntimeReadinessScope](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_readiness.py#24-32) not gating startup. |
| What startup/restart contracts are implemented? | WAL + snapshot for `position_tracking` only. Warmup gates (dict-based, not scope-based). Regime liveness heartbeat. Risk-skew guard. |
| Canonical bar identity adoption? | ✅ Attached at emission. ✅ Extracted at decision. ⚠️ source_mode not gating logic. |
| Replay identity adoption? | ⚠️ Contract defined, [extract_canonical_replay_identity](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/runtime_bar_identity.py#238-280) imported in [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) but replay path not confirmed in live flow. |
| Gap policy adoption? | ✅ Attached on gap bars. ✅ Imported for permission building. ⚠️ No persistent gap state — only per-bar annotation. |
| Quadratic rollout adoption? | ✅ Fully wired. Shadow evaluation active per bar. Fallback implemented. |
| MR status? | Active in FE domain and decision_making. `protect_only_capability=False` → fully blocked in protect-only mode. |
| md_amr status? | Active but requires strict trace contract in signal. Internal `md_amr_rest_hydration` contract named but not traced to implementation. |
| Critical blockers for live/testnet? | N-1 (analytics restore not pushed to handlers), N-2/N-3 (cold start without bar hydration), N-4 (md_amr hydration missing), N-7 (objective engine exception on missing exposure). |

---

## 12. Verdict: Live Readiness Blockers

> [!CAUTION]
> **3 critical blockers before safe live usage:**

1. **Cold-start warmup with no bar hydration** — Every restart begins with COLD FE, COLD regime, COLD pillar state. The only barrier is the warmup gate (typically clears in 1–2 basis timeframe bars). Strategies will fire quickly after restart with no historical context. This is the highest-severity issue for a live trading system.

2. **Analytics restore snapshots not pushed to handlers** — Unless [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) explicitly calls `aurora_handler.apply_runtime_analytics_restore_snapshot()` for each handler (not confirmed in the bootstrap code traced), the `_analytics_restore_snapshots` dict remains empty and the restore-based permission logic in [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) operates on stale/absent data.

3. **md_amr hydration contract not traced** — `local_hydration_contract = "md_amr_rest_hydration"` is declared in the compatibility matrix but no implementation was found in the traced code. If this is not implemented, md_amr has no state restore path and will be functionally cold after every restart regardless of WAL.
