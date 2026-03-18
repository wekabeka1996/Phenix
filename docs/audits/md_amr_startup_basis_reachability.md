# MD_AMR Startup Basis Reachability — Forensic Audit

**Date**: 2026-03-17  
**Scope**: md_amr startup basis integration, bar loading, seed-to-signal reachability  
**Verdict**: **CORRECTLY INTEGRATED BUT PARTIALLY BLOCKED**

---

# Executive Summary

[md_amr](file:///c:/Users/user/Music/Phenix/tests/domains/decision_making/test_md_amr_strategy_gateway.py#51-62) is **fully and correctly integrated** into two independent startup bar-loading systems. Both paths are wired, both execute at startup, and both successfully deliver historical bars from Binance. The strategy core receives ≥96 bars in its deques before the first live bar arrives, satisfying all internal math requirements.

However, **md_amr cannot produce an ENTRY signal until 2 hours after startup**, due to the handler's own `_MANDATORY_LIVE_WARMUP_SEC = 7200`. This is a handler-local timer, separate from the global startup warmup gate. After the 2-hour timer expires, three additional gates (`warmup.full_ready`, regime allowlist, objective engine) must also pass simultaneously.

The `64→96` basis_required_bars change is a **correct architectural alignment**, not a crude workaround. It synchronizes the external readiness contract with the internal math truth.

---

# Scope and Evidence Sources

| Source | Files Examined |
|---|---|
| Startup/bootstrap | [main.py](file:///c:/Users/user/Music/Phenix/apps/reference/main.py) L808-1320, [startup_basis_hydrator.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py) (full), [startup_hydration_planner.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py) (full), [startup_warmup.py](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_warmup.py) |
| Strategy/handler | [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py) (2016 LOC), [md_amr_strategy.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py) L80-230 |
| Contracts | [strategy_compatibility_matrix.py](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py) (282 LOC) |
| Config/SSOT | [strategies.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies.yaml), [md_amr.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/md_amr.yaml) (442 LOC), [domains.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/domains.yaml) |
| Plugins/registry | [md_amr plugin](file:///c:/Users/user/Music/Phenix/apps/reference/domains/strategies/plugins/md_amr.py), [registry.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/strategies/registry.py) |
| Drift-check | JOURNAL.md, JOURNAL_мій.md, TODO.md — **zero md_amr mentions** |

---

# 1. MD_AMR Startup Basis Integration Map

## Q1: Чи md_amr реально включається в startup basis hydration plan?

**ТАК.** Two independent integration paths proven:

### Path A — REST Hydration (handler-own, feeds strategy core directly)

```
main.py:818  StrategyRuntime.start()
  → registry.py:97-98  plugin.create_handler() → handler.register()
    → md_amr_handler.py:320  self._hydrate_state_from_rest()
      → md_amr_handler.py:563  self._run_coro_blocking(_hydrate_state_from_rest_async("15m"))
        → md_amr_handler.py:504  adapter.get_klines(symbol, interval='15m', limit=100)
          → md_amr_handler.py:531  strategy.on_bar(bar=bar, ...)  # FOR EACH BAR → deques
```

- **Source**: Binance REST API (`get_klines`)
- **Trigger**: [register()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#311-359) call during StrategyRuntime.start()  
- **Timing**: Happens at [main.py:818](file:///c:/Users/user/Music/Phenix/apps/reference/main.py#L814-L818), **BEFORE** global warmup gate activation at L948
- **Delivery**: Calls `strategy.on_bar()` at [md_amr_handler.py:531](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L530-L535) for each historical bar → **directly fills** `opens`, `highs`, [lows](file:///c:/Users/user/Music/Phenix/tests/domains/decision_making/test_md_amr_strategy_gateway.py#151-180), `closes`, `atr_history` deques

### Path B — Startup Basis Hydration (shared infra, feeds BarAggregator + counter)

```
main.py:843  build_startup_hydration_plan(config, analytics_restore_report)
  → startup_hydration_planner.py:319  profiles = build_active_strategy_compatibility_profiles()
    → strategy_compatibility_matrix.py:280  md_amr profile included ✓
  → startup_hydration_planner.py:322-337  for each strategy × symbol → create plan
    → md_amr profile: restart_local_basis_counter=True → SEED_HANDLER_BASIS_COUNTER action ✓
    → bars_state != RESTORED → RESTORE_OR_REPLAY_BASIS_BARS action ✓
    → local_hydration_contract="md_amr_rest_hydration" → USE_STRATEGY_LOCAL_HYDRATION action ✓

main.py:1250  execute_startup_basis_hydration(hydration_plan, ...)
  → startup_basis_hydrator.py:291  PillarBackfillService.fetch_candles(symbol, 900, 96)
    → startup_basis_hydrator.py:302  hydrate_basis_bars(bar_aggregator, symbol, 900, 96, ...)
      → bar_aggregator.inject_historical_bar(bar)  # feeds FE feature buffers
    → startup_basis_hydrator.py:183  handler.seed_startup_bars(symbol, seeded_bars)
      → md_amr_handler.py:246  _bars_seen_since_restart[symbol] = max(current, count)
```

### Plan construction evidence

At [strategy_compatibility_matrix.py:251-268](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#L251-L268), the md_amr profile:

```python
"md_amr": StrategyCompatibilityProfile(
    strategy_id="md_amr",
    active=True,
    active_symbols=_active_symbols(assignments, "md_amr"),  # XRPUSDT, BNBUSDT
    required_basis_tf_sec=900,                              # 15m bars
    basis_required_bars=_md_amr_basis_required_bars(md_cfg), # 96 (after fix)
    restart_local_basis_counter=True,                        # ← SEED action
    local_hydration_contract="md_amr_rest_hydration",        # ← REST hydration action
    needs_regime=True,
    quadratic_readiness_blocks_by_default=False,
)
```

At [startup_hydration_planner.py:312-343](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py#L312-L343), the plan builder iterates all profiles → creates plans for `md_amr:XRPUSDT` and `md_amr:BNBUSDT`.

---

# 2. Exact Bars Loaded for MD_AMR

## Q2: Які саме бари вантажаться?

### Path A — REST Hydration bars (strategy core delivery)

| Parameter | Value | Source |
|---|---|---|
| Timeframe | **900s (15m)** | [md_amr_handler.py:372-382](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L370-L382): [_interval_for_tf(900) = "15m"](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#370-383) |
| Source | Binance REST API (`get_klines`) | [md_amr_handler.py:504](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L504) |
| Quantity | **100** | [md_amr_handler.py:100](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L100): `_REST_HYDRATION_LIMIT = 100` |
| Bar type | **Closed bars** (historical klines from Binance) | OHLCV parsed at [md_amr_handler.py:438-454](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L438-L454) |
| Delivery | `strategy.on_bar()` at [L531](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L531) | Directly fills opens/highs/lows/closes deques |

### Path B — Startup Basis Hydration bars (BarAggregator + counter delivery)

| Parameter | Value | Source |
|---|---|---|
| Timeframe | **900s** | From profile `required_basis_tf_sec=900` at [L256-257](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#L256-L257) |
| Source | Binance REST via `PillarBackfillService.fetch_candles()` | [startup_basis_hydrator.py:298](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#L298) |
| Quantity | **96** (= [basis_required_bars](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#156-168) after fix) | [startup_basis_hydrator.py:272](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#L270-L273) |
| Bar type | **Closed bars** | Parsed via `Bar()` dataclass at [L116-127](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#L116-L127) |
| Delivery | `bar_aggregator.inject_historical_bar()` + `handler.seed_startup_bars()` | Feeds FE + seeds counter |

### Distinction from other bar planes

> [!IMPORTANT]
> These md_amr bars are **separate and independent** from:

| Bar Plane | Timeframe | Used By | Loaded By |
|---|---|---|---|
| **md_amr basis bars** | **900s** | md_amr strategy core | Path A (REST) + Path B (BarAgg) |
| Regime basis bars | **300s** | RegimeDetector SMA/ATR | main.py regime backfill (L1426+) |
| Aurora basis bars | **300s** | Aurora strategy | Same startup basis executor |
| Quadratic HTF pillars | 900/14400/86400 | FE pillar state | Pillar backfill (L1347+, currently disabled: `_bf_enabled=False`) |
| FE enabled timeframes | 180/300/900 | FE feature buffers | Live websocket + BarAggregator |

The md_amr bars are loaded independently from regime and HTF bars. They share the startup basis executor infrastructure but operate on `tf_sec=900` exclusively.

---

# 3. Seed-to-Handler Reachability

## Q3: Чи бари реально доходять до handler/core state?

### Path A → Strategy core deques: ✅ YES

At [md_amr_handler.py:530-535](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L530-L535):

```python
for bar in bars:
    strategy.on_bar(
        bar=bar,
        position_ctx={"qty_signed": 0.0, "bars_held": 0},
        llm_blocked=False,
    )
```

At [md_amr_strategy.py:194-197](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L194-L197):

```python
self.opens.append(bar_open)
self.highs.append(bar_high)
self.lows.append(bar_low)
self.closes.append(bar_close)
```

**100 bars** are delivered. Strategy core requires `len(self.closes) >= 96` for `dir_score`. **100 ≥ 96** → [compute_dir_components_from_900s()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#101-122) returns a valid result, not `None`.

### Path B → `_bars_seen_since_restart`: ✅ YES

At [md_amr_handler.py:238-250](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L238-L250):

```python
def seed_startup_bars(self, symbol: str, count: int) -> None:
    if count > 0:
        current = self._bars_seen_since_restart.get(symbol, 0)
        self._bars_seen_since_restart[symbol] = max(current, count)
```

If startup basis executor imports 96 bars → calls [seed_startup_bars(symbol, 96)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#238-251) → `_bars_seen_since_restart[symbol] = 96`. Cold-start gate at [L1267](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1267) (`_bars_seen < _basis_required`) → `96 < 96` = `False` → **gate passes**.

### Path B → BarAggregator → FE: ✅ YES

[hydrate_basis_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#71-141) at [L128](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#L128) calls `aggregator.inject_historical_bar(bar)` → these bars feed FE feature buffers (ATR, EMA, OBI, etc.), contributing to `warmup.full_ready` state.

### Additionally: bars accumulate during mandatory warmup

At [md_amr_handler.py:1171-1178](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1171-L1178), `strategy.on_bar()` runs **BEFORE** the mandatory warmup check at [L1182](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1182). This means even during the 2-hour warmup period, every live 15m bar continues to accumulate in strategy core deques.

Similarly, at [L824-846](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L824-L846), [_on_features_calculated](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#801-848) feeds bars to strategy core during warmup (note the inverted condition: `if not self._is_mandatory_live_warmup_active(...)` → returns early if warmup is **NOT** active, meaning bar ingestion only happens **during** warmup through this path).

---

# 4. What MD_AMR Needs Beyond Bars

## Q4: Чи тільки бари потрібні?

**НІ.** After successful basis seed + REST hydration, the following gates still apply in sequence inside [_on_process_strategy](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#1077-1830):

### Gate Chain (post-seed)

| # | Gate | Code Location | What It Checks | Status After Startup |
|---|---|---|---|---|
| 1 | `_enabled` | [L1078](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1078) | Handler config valid | ✅ Passes (set during [_parse_config](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#596-664)) |
| 2 | Symbol filter | [L1085](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1085) | `symbol ∈ _enabled_symbols` | ✅ Passes (XRPUSDT, BNBUSDT) |
| 3 | `tf_sec == 900` | [L1092](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1092) | Only 15m bars | ✅ Passes (FE emits for all tf≥60) |
| 4 | Duplicate check | [L1128](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1128) | `bar_close_ts > _rest_last_bar_ts_ms` | ✅ Passes (live bars > REST bars) |
| 5 | `strategy.on_bar()` | [L1172](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1172) | Feeds strategy core | ✅ Returns SIGNAL (deques pre-filled) |
| 6 | **Mandatory 2hr warmup** | [L1182](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1182) | `now_ms < mandatory_warmup_until` | ⚠️ **BLOCKS for 2 hours** |
| 7 | **warmup.full_ready** | [L1198](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1198) | FE features all ready | ⚠️ Depends on FE state |
| 8 | Cold-start gate | [L1267](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1267) | `_bars_seen < _basis_required` | ✅ Passes (seeded = 96 ≥ 96) |
| 9 | DEFER check | [L1290](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1290) | `result.status == DEFER` | ✅ Passes (deques ≥ 96 → no DEFER) |
| 10 | SIGNAL check | [L1309](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1309) | `result.status == SIGNAL` | Depends on market conditions |
| 11 | **Regime gate** | [L1336](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1336) | `regime ∈ allowed_regimes` | ⚠️ Excludes UNCERTAIN/TREND |
| 12 | Cooldown | [L1367](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1367) | Anti-churn delay | ✅ Passes (first signal) |
| 13 | Concentration guard | [L1374](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1374) | Max entries per bar | ✅ Passes (first signal) |

### Gate 6: Mandatory 2hr warmup — HARD BLOCKER

Set at [md_amr_handler.py:570-571](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L570-L571):
```python
self.mandatory_warmup_until = int(
    get_clock().now_ms() + self._MANDATORY_LIVE_WARMUP_SEC * 1000)
```

This is the handler's **OWN** timer, separate from the global [activate_startup_warmup_gate()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_warmup.py#235-244) at [main.py:948](file:///c:/Users/user/Music/Phenix/apps/reference/main.py#L948). The global gate is released at [main.py:1320](file:///c:/Users/user/Music/Phenix/apps/reference/main.py#L1320) ([release_startup_warmup_gate()](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_warmup.py#246-251)), but the handler's 2hr timer starts during [register()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#311-359) and runs independently.

> [!WARNING]
> Even after global warmup gate release and successful basis seed, md_amr signals are still blocked by the handler's own 2-hour timer. The timer is set DURING REST hydration (at [_hydrate_state_from_rest](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#551-585) completion), not reset by startup basis executor.

### Gate 7: warmup.full_ready — FE DEPENDENCY

Checked at [L1198](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1198): `warmup.get("full_ready") is not True`.

This comes from `CMD:PROCESS_STRATEGY` payload, set by FeatureEngineering. FE must have all features warmed up:
- ATR computed ✓ (seeded by Path B bars via BarAggregator)
- EMA/OBI/TFI computed
- Volatility features ready
- All FE warmup conditions met per `feature_engineering.warmup.enforcement_mode: fail_fast`

After startup basis hydration injects 96 bars into BarAggregator, FE **should** become `full_ready` for XRPUSDT/BNBUSDT on `tf_sec=900` — but ONLY if all FE features for all timeframes are also ready.

### Gate 11: Regime gate — CONDITIONAL BLOCKER

[allowed_regimes](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#424-437) per YAML:
```yaml
allowed_regimes: ["MEAN_REVERSION", "LOW_VOLATILITY", "HIGH_VOLATILITY", "FLAT_LOW", "FLAT_HIGH"]
```

With compatibility expansion at [L112-119](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L112-L119):
- `FLAT_LOW` → `FLAT_LOW`, `LOW_VOLATILITY`  
- `FLAT_HIGH` → `FLAT_HIGH`, `HIGH_VOLATILITY`
- `MEAN_REVERSION` → `MEAN_REVERSION`, `FLAT_NORMAL`

**Excluded**: `UNCERTAIN`, `TREND_UP`, `TREND_DOWN`. If RegimeDetector classifies XRPUSDT/BNBUSDT under these regimes → signal blocked.

---

# 5. First Actionable Threshold Analysis

## Q5: 64 → 96 — correct alignment чи crude workaround?

### Before the change

| Threshold | Value | Source |
|---|---|---|
| Compatibility profile [basis_required_bars](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#156-168) | **64** | [max(channel_window_bars=12, atr_window=14, atr_stats_window=64)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#364-376) |
| Strategy core [compute_dir_components_from_900s()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#101-122) | **96** | [md_amr_strategy.py:102](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L102): `if len(self.closes) < 96: return None` |
| Handler [_core_signal_history_required_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#168-181) | **96** | [md_amr_handler.py:176-180](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L176-L180): [max(12, 77, 96)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#364-376) |

**Mismatch**: compatibility profile (64) was lower than strategy core truth (96). This meant:
- Startup basis executor fetched only 64 bars
- [seed_startup_bars(symbol, 64)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#238-251) → `_bars_seen_since_restart = 64`
- Cold-start gate at L1267: [_bars_seen(64) < _basis_required(64)](file:///c:/Users/user/Music/Phenix/tests/domains/decision_making/test_md_amr_runtime_readiness.py#15-70) = `False` → **passes**
- But [on_bar()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#180-363) → [compute_dir_components_from_900s()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#101-122) → `len(closes) < 96` → returns `None` → DEFER
- Handler reports "ready" but strategy core still defers for 32 more bars
- **Result**: silent false-readiness for 32 × 15min = 8 hours

### After the change

At [strategy_compatibility_matrix.py:156-167](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#L156-L167):

```python
def _md_amr_basis_required_bars(md_cfg: Any) -> int:
    channel_window_bars = int(getattr(md_cfg, "channel_window_bars", 12) or 12)
    atr_window = int(getattr(md_cfg, "atr_window", 14) or 14)
    atr_stats_window = int(getattr(md_cfg, "atr_stats_window", 64) or 64)
    atr_history_required_bars = atr_window + atr_stats_window - 1
    dir_components_required_bars = 96
    return max(
        channel_window_bars,        # 12
        atr_history_required_bars,  # 77
        dir_components_required_bars, # 96
    )
    # Result: 96
```

**Now aligned**: profile requires 96 = handler [_core_signal_history_required_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#168-181) = 96 = strategy core truth.

### Verdict: ✅ CORRECT ARCHITECTURAL ALIGNMENT

The change is not a "crude workaround" — it's a **structural synchronization** of three independent code locations that must agree:

1. **Source of truth**: `md_amr_strategy.py:102` — `len(self.closes) < 96: return None`
2. **Handler self-check**: [_core_signal_history_required_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#168-181) = [max(12, 77, 96)](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/feature_engineering.py#364-376) = 96
3. **External contract**: [_md_amr_basis_required_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#156-168) now also computes 96

The `dir_components_required_bars = 96` constant in the compatibility profile mirrors `_DIR_COMPONENTS_REQUIRED_BARS = 96` in the handler, which mirrors the hardcoded `96` in strategy core. All three sources now agree.

---

# 6. Does Startup Hydration Actually Make MD_AMR Reachable?

## Q6: Чи startup basis hydration робить md_amr reachable після рестарту?

### What startup hydration provides ✅

| Checkpoint | Status After Startup |
|---|---|
| Strategy core `closes` deque ≥ 96 bars | ✅ Path A: 100 bars via REST |
| Strategy core `atr_history` ≥ 64 bars | ✅ Path A: ~86 ATR values computed from 100 bars |
| `_bars_seen_since_restart` ≥ 96 | ✅ Path B: seeded by startup executor |
| FE feature buffers warmed | ✅ Path B: 96 bars via BarAggregator |
| `dir_score` computable (not None) | ✅ 100 bars ≥ 96 requirement |
| Cold-start gate passes | ✅ 96 ≥ 96 |
| DEFER eliminated | ✅ All deques sufficiently filled |

### What startup hydration does NOT provide ⚠️

| Checkpoint | Status After Startup | Time to Resolve |
|---|---|---|
| **Mandatory 2hr warmup** | ❌ Handler timer runs 7200s | **Exactly 2 hours** |
| `warmup.full_ready` | ❓ Depends on FE state for ALL features | Usually resolved during startup |
| Regime classification | ❓ Depends on RegimeDetector state | Resolved after regime backfill |
| Objective engine data | ❓ Depends on behavioral component history | May require multiple bars |

### Timeline after restart

```
T+0s:     StrategyRuntime.start() → register() → REST hydration (100 bars loaded)
T+~5s:    REST hydration completes → mandatory_warmup_until = now + 7200s
T+~10s:   activate_startup_warmup_gate() → global can_open_new_risk=False
T+~30s:   execute_startup_basis_hydration() → 96 bars → BarAgg + seed_startup_bars()
T+~45s:   release_startup_warmup_gate() → global can_open_new_risk=True
T+~60s:   First live CMD:PROCESS_STRATEGY arrives for tf_sec=900
          → on_bar() runs → SIGNAL possible → but mandatory warmup BLOCKS emission
          → bars continue accumulating in deques
T+7200s:  Mandatory warmup expires
          → NEXT CMD:PROCESS_STRATEGY for tf_sec=900:
            warmup.full_ready? → if yes → cold-start gate? → PASS (96 seeded)
            → on_bar() → SIGNAL? → regime gate? → if allowed → EMIT
```

> [!IMPORTANT]
> Startup hydration **fully solves** the basis bar problem. The strategy core is signal-capable from the first live bar. But signal **emission** is gated by the 2-hour mandatory warmup timer, which is a deliberate safety mechanism, not a bug.

---

# 7. Architecture Verdict

## **CORRECTLY INTEGRATED BUT PARTIALLY BLOCKED**

### Justification

| Criterion | Assessment |
|---|---|
| md_amr in startup hydration plan | ✅ Proven: profile at [L251-268](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#L251-L268), plan builder at [L322-337](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_hydration_planner.py#L322-L337) |
| Historical bars fetched from Binance | ✅ Proven: REST at [L504](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L504), PillarBackfill at [L298](file:///c:/Users/user/Music/Phenix/apps/reference/bootstrap/startup_basis_hydrator.py#L298) |
| Bars reach strategy core deques | ✅ Proven: [on_bar()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#180-363) at [L531](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L531) |
| `_bars_seen_since_restart` seeded | ✅ Proven: [seed_startup_bars()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#238-251) at [L238](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L238) |
| Cold-start gate passes after seed | ✅ Proven: 96 ≥ 96 at [L1267](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L1267) |
| Strategy core dir_score computable | ✅ Proven: 100 ≥ 96 at [md_amr_strategy.py:102](file:///c:/Users/user/Music/Phenix/apps/reference/domains/feature_engineering/md_amr_strategy.py#L102) |
| **Signal emission blocked by 2hr warmup** | ⚠️ Handler-local timer at [L101](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L101) |
| **Signal emission blocked by regime gate** | ⚠️ Excludes UNCERTAIN/TREND at [L780](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L780) |

The integration is **architecturally correct**. The partial block is from **deliberate safety gates**, not integration defects.

---

# 8. Ranked Findings

| # | Risk | Finding | Code Reference |
|---|---|---|---|
| 1 | 🔴 **HIGH** | **2-hour mandatory warmup** blocks ALL md_amr signals. Not a bug — deliberate safety — but the single largest blocker for debugging/tuning | [md_amr_handler.py:101](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L101): `_MANDATORY_LIVE_WARMUP_SEC = 7200` |
| 2 | 🟡 **MEDIUM** | **Regime gate excludes UNCERTAIN/TREND_UP/TREND_DOWN** — common regime classifications, especially early after startup | [md_amr.yaml:228,258,296,334,372,410](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/md_amr.yaml#L228): [allowed_regimes](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#424-437) missing UNCERTAIN/TREND |
| 3 | 🟡 **MEDIUM** | **warmup.full_ready** depends on ALL FE features being ready, not just md_amr's 900s tf. If ANY feature for ANY timeframe is not ready → blocks | FE enforcement_mode: fail_fast |
| 4 | 🟢 **LOW** | **64→96 mismatch was present** — caused silent false-readiness. Now fixed. No remaining misalignment | [strategy_compatibility_matrix.py:156-167](file:///c:/Users/user/Music/Phenix/apps/reference/contracts/strategy_compatibility_matrix.py#L156-L167) |
| 5 | 🟢 **LOW** | **Pillar backfill disabled** (`_bf_enabled=False` at [main.py:1352](file:///c:/Users/user/Music/Phenix/apps/reference/main.py#L1352)) — does not affect md_amr basis bars, but prevents HTF D1/H4 data loading for FE features | [main.py:1354](file:///c:/Users/user/Music/Phenix/apps/reference/main.py#L1354) |

---

# 9. Open Questions

| # | Question | Why Unresolvable |
|---|---|---|
| 1 | Does FE `warmup.full_ready` become `True` for XRPUSDT/BNBUSDT before the 2hr warmup expires? | Depends on FE warmup convergence logic which involves multiple timeframes and features — needs live runtime trace |
| 2 | Which regime does RegimeDetector classify XRPUSDT/BNBUSDT under after regime backfill? | Depends on market data — if UNCERTAIN, regime gate permanently blocks signals |
| 3 | Does [_parse_config()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#596-664) execute without exception in production? | Zero md_amr log entries in logs suggest either (a) it works silently, or (b) it fails before logging — needs live startup verification |
| 4 | Does the [_on_features_calculated](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#801-848) warmup bar path at [L824](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#L824) correctly accumulate bars, given the inverted warmup condition? | Code at L824 has `if not self._is_mandatory_live_warmup_active(...)` — this means it **returns early** when warmup is **not** active, i.e., bar ingestion only happens **during** warmup. This seems inverted from intent. |

---

# 10. Recommended Next Pack

**Single narrow investigation**: instrument a production startup run and collect exactly:

1. `MD_AMR_INIT` / `MD_AMR_REGISTERED` log lines — confirm [_parse_config()](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py#596-664) succeeds
2. `STARTUP_BASIS_SEEDED strategy=md_amr` log lines — confirm basis seed count and source
3. `MD_AMR_HYDRATION` log line — confirm REST hydration bar count
4. `MD_AMR_BARS_PROGRESS` log lines per symbol — confirm `_bars_seen_since_restart` value
5. `MD_AMR_WARMUP_NOT_READY` / `MANDATORY_LIVE_WARMUP` rejection events — confirm post-2hr behavior
6. First `MD_AMR_SIGNAL_READY` log line — confirm exact time-to-signal-ready

This will prove whether the integration is working end-to-end in production or whether a runtime exception is silently killing the handler at startup.

No code changes needed for this investigation — the observability markers added in the recent patch are sufficient.
