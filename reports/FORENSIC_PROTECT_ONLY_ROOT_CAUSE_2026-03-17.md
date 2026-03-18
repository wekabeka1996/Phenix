# FORENSIC REPORT: PROTECT_ONLY Root Cause Analysis
**Date:** 2026-03-17
**Analyst Role:** Principal Runtime Safety Auditor / Contract Forensics Engineer
**Scope:** `mean_reversion:DOGEUSDT` — permanent `mode=PROTECT_ONLY` for entire live session
**WAL:** `ops/wal/2026-03-17.jsonl`
**Severity:** CRITICAL — 100% entry signal loss for strategy over entire session

---

## EXECUTIVE SUMMARY

`MeanReversionHandler` (symbol: `DOGEUSDT`) operates with `runtime_permissions.mode = PROTECT_ONLY` (`can_manage_existing_risk=True`, `can_open_new_risk=False`) for the **entire** 2026-03-17 live session. This causes `strategy_signal_gateway` to reject every entry signal with `READINESS_OPEN_NEW_RISK_NOT_ALLOWED`. **No single trade was opened.** 9 qualified entry signals were lost.

**Root cause:** `ops/snapshots/` directory does not exist on the filesystem. This causes `find_latest_snapshot()` to return `None` silently (logged at DEBUG only—invisible in production). `snapshot_loaded_successfully` stays `False` for the entire startup. `build_startup_analytics_restore_report(snapshot_loaded=False)` assigns `execution_status=COLD` to every strategy/symbol pair. This COLD snapshot is injected into `MeanReversionHandler` and never updated again. On every signal emission, `combine_restore_permissions_live_first()` sees `execution_status != RESTORED` and forces `can_open_new_risk=False`. PROTECT_ONLY is permanent and sticky for the duration of the session.

This is a **HYDRATION/RESTORE BUG** — specifically a *sticky cold-start latch caused by missing snapshot infrastructure*, compounded by silent failure at startup.

**This is incorrect fail-closed behavior** in this specific case, because: the account has zero open positions throughout the session (confirmed by WAL `ACCOUNT_UPDATE_RECEIVED` entries with `positions: []`), and the `mean_reversion` strategy profile explicitly declares `protect_only_capability=False` — it cannot operate in PROTECT_ONLY mode at all.

---

## 1. READINESS CONTRACT (Canonical Model)

**File:** `apps/reference/contracts/runtime_readiness.py:83-104`

`RuntimePermissions` is a frozen dataclass with a `mode` computed property:

```
mode = "OPEN_AND_MANAGE"  if can_manage=True  AND can_open=True
mode = "PROTECT_ONLY"     if can_manage=True  AND can_open=False   ← OBSERVED
mode = "CLOSED"           if can_manage=False AND can_open=False
```

The `mode` string is a derived label — the primary signals are the two boolean fields.

---

## 2. PRODUCER CHAIN — Full Traced Path to PROTECT_ONLY

The chain runs from filesystem state through startup code into the live emission path.

### Layer 0 — Filesystem (Root)

**`ops/snapshots/` directory does not exist.**

Confirmed by terminal:
```
Test-Path "ops/snapshots" → "Directory does not exist"
```

This directory is required by the DR (disaster recovery) subsystem to store/load position snapshots between sessions.

### Layer 1 — DR startup (`main.py:534-555`)

```python
# apps/reference/main.py:534-555
snapshot_loaded_successfully = False                       # ← initial false
snapshot_dir_path = str(project_root / "ops" / "snapshots")
latest_snapshot_path = find_latest_snapshot(snapshot_dir_path)  # → None
                                                           # (ops/snapshots/ missing)
if latest_snapshot_path:                                   # False → skipped
    ...
    snapshot_loaded_successfully = True                    # NEVER REACHED
```

### Layer 2 — `find_latest_snapshot()` (`vfoundation/dr/dr_loader.py:60-83`)

```python
def find_latest_snapshot(snapshot_dir: str) -> Optional[Path]:
    path = Path(snapshot_dir)
    if not path.exists():
        logger.debug(...)     # ← DEBUG ONLY, no WARNING, no ERROR
        return None           # ← silent return, no exception
    ...
```

**Critical observability gap:** Missing snapshot directory is reported only at `DEBUG` level. Production log verbosity does not surface this. Operator has no visible signal that DR is disabled.

### Layer 3 — Restore report builder (`bootstrap/runtime_analytics_restore.py:154-175`)

`main.py:828` calls `build_startup_analytics_restore_report(snapshot_loaded=False)`.

For every (strategy, symbol) assignment, `_build_default_snapshot(snapshot_loaded=False)` is called:

```python
execution_status = (
    restored_restore_status(why=["execution_snapshot_loaded"], ...)
    if snapshot_loaded          # False → else branch
    else cold_restore_status(
        why=["execution_restore_missing"],   # ← COLD
        ...
    )
)
```

Result: `execution_status.state = COLD` for all strategies including `mean_reversion:DOGEUSDT`.

### Layer 4 — Handler injection

`main.py` iterates the restore report and injects snapshots into each handler:

```python
# main.py (startup phase)
for snapshot in restore_report.snapshots:
    handler.apply_runtime_analytics_restore_snapshot(snapshot)
```

`MeanReversionHandler._analytics_restore_snapshots["DOGEUSDT"]` now holds a `StrategyAnalyticsRestoreSnapshot` with `execution_status.state = COLD`.

**This snapshot is set once and never updated** — there is no live mechanism to upgrade it to `RESTORED`.

### Layer 5 — Signal emission (`mean_reversion_handler.py:_emit_signal`)

On every qualified signal:

```python
# Step 1: build base from live market data
base_permissions = make_permissions(
    can_open_new_risk=not gap_blocks_open_new_risk(gap_status)  # gap=CLEAR → True
)
# base_permissions = {can_manage=True, can_open=True}

# Step 2: apply restore gate — THIS IS WHERE PROTECT_ONLY IS SET
runtime_permissions = combine_restore_permissions_live_first(
    base_permissions,
    self._analytics_restore_snapshots.get("DOGEUSDT")  # NOT None, state=COLD
)
# → can_open_new_risk=False, mode=PROTECT_ONLY

# Step 3: startup warmup gate (no effect — gate already released)
runtime_permissions = apply_startup_warmup_permission_overlay(runtime_permissions)
# → unchanged (startup_warmup_gate_active() == False)
```

### Layer 6 — `combine_restore_permissions_live_first` (`contracts/runtime_analytics_restore.py:360-391`)

```python
def combine_restore_permissions_live_first(base_permissions, snapshot):
    if snapshot is None:
        return base_permissions           # full permissions — NOT triggered (snapshot exists)

    execution_status = lookup_restore_status(snapshot, EXECUTION_STATE)

    if execution_status is None or execution_status.state == RESTORED:
        return base_permissions           # full permissions — NOT triggered (state=COLD)

    # execution_status.state == COLD → forced block
    return make_permissions(
        can_manage_existing_risk=True,   # preserve manage capability
        can_open_new_risk=False,          # ← LOCKED FALSE
    )
```

### Layer 7 — Strategy signal gateway (`strategy_gateway.py:385-391`)

```python
if (not is_reduce_path) and runtime_permissions.get("can_open_new_risk") is False:
    self._emit_trade_intent_rejected(
        reason_code="READINESS_OPEN_NEW_RISK_NOT_ALLOWED",
        ...
    )
    return
```

---

## 3. RUNTIME TIMELINE

| WAL Line | Timestamp (ms) | Side | Signal Reason | Status |
|----------|---------------|------|---------------|--------|
| 1 | (genesis, `_prev=000...`) | — | Session start | PROTECT_ONLY set at startup |
| 95 | 1773698704287 | SELL | `price_above_upper_bb:pct_b=0.975;regime:FLAT_LOW` | **REJECTED** |
| 176 | 1773699004538 | SELL | `price_above_upper_bb:pct_b=1.160;rsi_overbought:70.9;regime:FLAT_LOW` | **REJECTED** |
| 7665 | 1773726304653 | BUY | `price_below_lower_bb:pct_b=-0.015;rsi_oversold:22.6;regime:FLAT_LOW` | **REJECTED** |
| 9149 | 1773731704736 | SELL | `price_above_upper_bb:pct_b=0.985;regime:FLAT_LOW` | **REJECTED** |
| 9232 | 1773732004413 | SELL | `price_above_upper_bb:pct_b=1.190;rsi_overbought:71.3;regime:FLAT_LOW` | **REJECTED** |
| 9315 | 1773732304676 | SELL | `price_above_upper_bb:pct_b=1.040;regime:FLAT_LOW` | **REJECTED** |
| 10467 | 1773736504111 | SELL | `price_above_upper_bb:pct_b=1.012;regime:FLAT_LOW` | **REJECTED** |
| 10632 | 1773737105314 | SELL | `price_above_upper_bb:pct_b=0.976;regime:FLAT_LOW` | **REJECTED** |
| 12021 | 1773742204798 | BUY | `price_below_lower_bb:pct_b=0.031;regime:FLAT_LOW` | **REJECTED** |

**Key observations:**
- First reject at WAL line 95 — within the first ~100 events of the session. PROTECT_ONLY was active from session start.
- No `READINESS_RESTORE_UPGRADE` or `EXECUTION_STATE_UPDATED` event appears anywhere in WAL — the COLD latch was never released.
- All `ACCOUNT_UPDATE_RECEIVED` entries in WAL show `positions: []` — account genuinely had zero open positions throughout. There was literally no risk to protect.
- All `BAR_CLOSED` events show `gap_state: CLEAR` — gap_blocks was never the cause.

**Duration of PROTECT_ONLY lock:** From WAL genesis (session start) through at least WAL line 12021 — spanning ≥12,000 WAL entries with no exit.

---

## 4. GATEWAY REJECT PAYLOADS (Verbatim)

Every reject carries an identical permissions payload:

```json
{
  "reason_code": "READINESS_OPEN_NEW_RISK_NOT_ALLOWED",
  "stage": "DECISION",
  "why": "strategy_signal_gateway:open_new_risk_not_allowed",
  "strategy_id": "mean_reversion",
  "symbol": "DOGEUSDT",
  "details": {
    "runtime_permissions": {
      "can_manage_existing_risk": true,
      "can_open_new_risk": false,
      "mode": "PROTECT_ONLY"
    }
  }
}
```

The `why_chain` field on each reject correctly encodes the full signal qualification chain, terminating with `"open_new_risk_not_allowed"`. This confirms the MR signal logic itself is healthy — the signals were legitimate and qualified; it is solely the permissions gate that blocks them.

---

## 5. SECONDARY FINDING: STRATEGY PROFILE MISMATCH

**File:** `apps/reference/contracts/strategy_compatibility_matrix.py:215-234`

The `mean_reversion` strategy compatibility profile declares:

```python
protect_only_capability=False       # MR cannot operate in PROTECT_ONLY
degraded_mode_allowance="NON_TRADING_ONLY"  # MR cannot trade at all in degraded modes
needs_execution_context=True        # MR requires execution context restore
```

The combined effect: PROTECT_ONLY does not just limit MR — it completely eliminates it. The strategy is declared as requiring full OPEN_AND_MANAGE for any trades. This means the COLD execution state and resulting PROTECT_ONLY is a **total block**, not a soft restriction.

There is no graceful degradation for MR. Once PROTECT_ONLY fires, MR is entirely inactive.

---

## 6. ROOT CAUSE VERDICT

**Class:** HYDRATION / RESTORE BUG — Missing snapshot infrastructure causes permanent silent cold-latch at startup.

**Root cause (single line):** `ops/snapshots/` directory does not exist → `find_latest_snapshot()` returns `None` at DEBUG log level → `snapshot_loaded_successfully=False` → `execution_status=COLD` for `mean_reversion:DOGEUSDT` → `combine_restore_permissions_live_first()` forces `can_open_new_risk=False` → PROTECT_ONLY is permanent.

**Is this correct fail-closed behavior?**

| Criterion | Assessment |
|-----------|------------|
| Intended design | Yes — COLD execution state should block new risk opening |
| Applied correctly given actual state | **No** — account had zero positions, no risk existed to protect |
| Self-healing possible | **No** — no live upgrade path from COLD to RESTORED |
| Operator-visible | **No** — silent DEBUG log, no WAL event, no alert |
| Strategy can tolerate PROTECT_ONLY | **No** — `protect_only_capability=False` in profile |

Verdict: **The fail-closed mechanism is correct in design but becomes a defect in this scenario because**: (a) the precondition that triggered it (missing snapshot directory) is a deployment gap, not a runtime event; (b) the account state confirms there is nothing to protect; (c) the system has no self-healing path to exit COLD once confirmed zero positions from live `ACCOUNT_UPDATE`; (d) the failure is operationally invisible.

**Three compound failures driving this:**

1. **F1 (INFRA):** `ops/snapshots/` directory never created. `SnapshotScheduler` creates it at `__init__` time (`snapshot_scheduler.py:50: self.snapshot_dir.mkdir(parents=True, exist_ok=True)`) — but if `SnapshotScheduler` was never initialized or never ran a save cycle, no directory exists. First-time deployment or environment reset leaves no snapshot.

2. **F2 (OBSERVABILITY):** `find_latest_snapshot()` logs missing directory at `DEBUG` only. This is a critical startup condition — DR is entirely disabled — yet it produces no `WARNING`, no `ERROR`, and no WAL event. Operator has zero visibility.

3. **F3 (DESIGN):** No self-healing path. The restore snapshot is set once at startup (`apply_runtime_analytics_restore_snapshot`) and no live mechanism exists to upgrade `execution_status` from `COLD` to `RESTORED` when `ACCOUNT_UPDATE_RECEIVED` confirms `positions: []`. The COLD status is a permanent latch for the session.

---

## 7. BLOCKED SIGNAL SUMMARY

All 9 rejected signals were structurally valid (regime=`FLAT_LOW`, Bollinger Band thresholds met, RSI conditions satisfied). The `why_chain` field on each WAL entry confirms proper signal qualification. None of the blockers were market-condition-based — all terminated with `"open_new_risk_not_allowed"`.

Two BUY signals:
- Line 7665: `pct_b=-0.015`, `rsi_oversold:22.6` — high-quality oversold signal at lower BB
- Line 12021: `pct_b=0.031`, regime FLAT_LOW — lower BB bounce setup

Seven SELL signals (overbought extension):
- Lines 95, 176, 9149, 9232, 9315, 10467, 10632 — all `pct_b > 0.97`, multiple with RSI overbought confirmation

All would have been valid entry attempts under normal OPEN_AND_MANAGE permissions.

---

## 8. FIX TARGETS

### FIX-1 (IMMEDIATE, INFRA): Create ops/snapshots/ directory

```bash
mkdir -p ops/snapshots
```

**Effect:** On next restart, `find_latest_snapshot()` will find the directory (empty), return `None`, and `snapshot_loaded_successfully` remains `False`. This alone does NOT fix the COLD latch — but it is a prerequisite for FIX-3 and stops `SnapshotScheduler` from failing to write snapshots.

**Alone, this is not sufficient.**

### FIX-2 (CRITICAL, OBSERVABILITY): Elevate log level in find_latest_snapshot

**File:** `vfoundation/dr/dr_loader.py:72`

Change:
```python
logger.debug(f"Snapshot directory does not exist: {snapshot_dir}")
```
To:
```python
logger.warning(f"[DR] Snapshot directory does not exist: {snapshot_dir}. DR is disabled for this session.")
```

And in `main.py` after `find_latest_snapshot` returns `None`:
```python
if latest_snapshot_path is None:
    LOG.warning("[DR] No snapshot found — execution_status will be COLD for all strategies. New risk will be blocked until live account state confirms zero positions.")
```

**Effect:** Missing snapshot directory becomes operator-visible in production logs immediately.

### FIX-3 (CRITICAL, DESIGN): Self-healing upgrade from COLD on zero-position confirmation

**File:** `apps/reference/domains/decision_making/mean_reversion_handler.py` (and equivalent in other handlers)

When an `ACCOUNT_UPDATE_RECEIVED` event arrives with `positions: []` for `DOGEUSDT`, the handler should call:

```python
def _maybe_upgrade_restore_snapshot_on_zero_positions(self, symbol: str) -> None:
    """
    If execution_status is COLD and live account update confirms zero positions,
    upgrade to a synthetic RESTORED status. There is no risk to protect.
    """
    snapshot = self._analytics_restore_snapshots.get(symbol)
    if snapshot is None:
        return
    execution_status = lookup_restore_status(snapshot, RuntimeAnalyticsRestoreScope.EXECUTION_STATE)
    if execution_status is None or execution_status.state == RuntimeAnalyticsRestoreState.RESTORED:
        return
    # COLD + zero positions confirmed → no existing risk, safe to open new
    upgraded_snapshot = replace_execution_status(
        snapshot,
        restored_restore_status(
            why=["execution_upgrade_zero_positions_confirmed"],
            source="account_update:live",
            evidence_ref=f"account_update:{symbol}:positions_empty",
        )
    )
    self._analytics_restore_snapshots[symbol] = upgraded_snapshot
    LOG.info(f"[DR] Upgraded execution_status COLD→RESTORED for {symbol}: zero live positions confirmed")
```

**Semantic correctness:** "No snapshot AND no live positions" = clean start, no risk to protect. The PROTECT_ONLY intent is to prevent opening new risk when existing positions may be unknown. When live data proves there are no positions, that precondition is satisfied.

### FIX-4 (OPTIONAL, DESIGN): cold_start_allow_if_no_positions flag in strategy profile

For strategies with `protect_only_capability=False` (MR, etc.), add a compatibility flag `cold_start_allow_if_no_positions=True` that lets `_build_default_snapshot` use `restored_restore_status` when `has_open_position=False AND snapshot_loaded=False`.

This is a more conservative, declarative approach compared to FIX-3 but requires profile schema change.

---

## 9. EVIDENCE SOURCES

| Source | Location | Role |
|--------|----------|------|
| WAL 2026-03-17 | `ops/wal/2026-03-17.jsonl` | 9 PROTECT_ONLY rejects, ACCOUNT_UPDATE positions=[], genesis block |
| Readiness contract | `apps/reference/contracts/runtime_readiness.py:83-104` | `RuntimePermissions.mode` property definition |
| Gateway reject logic | `apps/reference/domains/decision_making/strategy_gateway.py:385-391` | `READINESS_OPEN_NEW_RISK_NOT_ALLOWED` emit condition |
| Handler emit chain | `apps/reference/domains/decision_making/mean_reversion_handler.py:840-850` | Restore + warmup overlay calls |
| Restore combinator | `apps/reference/contracts/runtime_analytics_restore.py:384-400` | `combine_restore_permissions_live_first` — primary PROTECT_ONLY producer |
| Snapshot builder | `apps/reference/bootstrap/runtime_analytics_restore.py:154-175` | `_build_default_snapshot` — COLD assignment |
| Startup DR logic | `apps/reference/main.py:534-555` | `snapshot_loaded_successfully` flag |
| DR loader | `vfoundation/dr/dr_loader.py:60-83` | `find_latest_snapshot` — silent None on missing dir |
| Strategy profile | `apps/reference/contracts/strategy_compatibility_matrix.py:215-234` | `protect_only_capability=False` for MR |
| Filesystem check | Terminal (confirmed) | `ops/snapshots/` directory does not exist |

---

## 10. CONFIDENCE AND UNKNOWNS

**Confidence: HIGH** on root cause. The causal chain is fully traceable from filesystem state through every code layer to WAL output, with no speculation.

**Unknowns / areas to verify:**

1. **When was `ops/snapshots/` last present?** Check git log for the directory or any mention in deployment scripts. If it was deleted, determine when and why.

2. **Does `SnapshotScheduler` actually run in this deployment?** Check `main.py` for `SnapshotScheduler` initialization. If it was never initialized, the directory was never created, and no snapshots were ever written — this whole session chain is the permanently recurring state.
   - `apps/reference/main.py:919` shows `"snapshot_dir": "ops/snapshots"` in a dict — but does this actually instantiate `SnapshotScheduler`? Verify.

3. **What is the `snapshot_loaded_successfully` value logged at startup?** If startup logging was preserved in `logs/`, a grep for `"Successfully loaded state from snapshot"` vs `"no snapshots found"` would confirm if this was the first-ever startup without snapshots.

4. **Are other strategies (aurora, md_amr) also affected?** The same `build_startup_analytics_restore_report(snapshot_loaded=False)` runs for ALL strategy assignments. Other strategies may have `protect_only_capability=True` and can limp-trade in PROTECT_ONLY, but they share the same COLD execution state at startup.

---

*Report generated from full producer-chain forensic trace. No speculation — every finding is grounded in source file/line or WAL evidence.*
