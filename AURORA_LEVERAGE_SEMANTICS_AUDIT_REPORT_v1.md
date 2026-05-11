# AURORA_LEVERAGE_SEMANTICS_AUDIT_REPORT_v1

**Date:** 2026-05-09
**Track:** config / SSOT / leverage ownership repair
**Scope:** LEV-03 — `strategies.aurora.assets.<SYM>.leverage.target`
**Verdict:** `READY_FOR_NARROW_IMPLEMENTATION`

---

## Section 1: Problem Framing

After removing `leverage_defaults` (LEV-REMOVE-DEFAULTS-2026-05-09), one leverage-related surface remains unclassified:

- `config/aurora/strategies/aurora.yaml` → `aurora.assets.<SYM>.leverage.target` (per-asset strategy config)

This surface coexists with the now-proven execution SSOT:

- `config/aurora/instruments.yaml` → `instruments.<SYM>.execution.target_leverage`

The audit determines whether these surfaces represent a conflict, a harmless semantic split, a legacy shell, or a unification candidate, and names the safest next bounded seam.

---

## Section 2: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `aurora.assets.BTCUSDT.leverage.target = 35` in `aurora.yaml` | `config/aurora/strategies/aurora.yaml` lines 577-580 |
| F-02 | `instruments.BTCUSDT.execution.target_leverage = 25` in `instruments.yaml` | `config/aurora/instruments.yaml` line 54 |
| F-03 | `aurora.assets.ETHUSDT.leverage.target = 20`; `instruments.ETHUSDT.execution.target_leverage = 20` — values agree | `aurora.yaml` lines 382-384; `instruments.yaml` line 35 |
| F-04 | `aurora.assets.DOGEUSDT.leverage.target = 20`; `instruments.DOGEUSDT.execution.target_leverage = 10` — values diverge by 10 | `aurora.yaml` lines 898-901; `instruments.yaml` line 71 |
| F-05 | `aurora.assets.<SYM>.leverage.mode = ISOLATED` for all three symbols; `instruments.<SYM>.execution.margin_mode = "isolated"` for all three — same semantic, different field naming | `aurora.yaml` leverage blocks; `instruments.yaml` execution blocks |
| F-06 | `aurora.assets.<SYM>.leverage.max_notional_value = null` for all three symbols | `aurora.yaml` leverage blocks |
| F-07 | `decision.py` line 1621 reads `target_leverage = getattr(leverage_cfg, "target", 20)` — hardcoded fallback of 20 if field absent | `apps/reference/domains/strategies/runtimes/aurora/decision.py:1621` |
| F-08 | `target_leverage` from `aurora.assets` is passed to `quantize_exposure(leverage=target_leverage, ...)` | `decision.py:1625-1633` |
| F-09 | Quantizer comment (line 186-187): "leverage only affects the estimated margin requirement here; it does not change the requested notional or qty." | `apps/reference/shared/decision_primitives/instrument_quantizer.py:186-187` |
| F-10 | `QuantizedPosition.margin_required = actual_notional / leverage` — the ONLY field affected by leverage in the quantizer | `instrument_quantizer.py:188-189` |
| F-11 | `QuantizedPosition.qty` and `QuantizedPosition.notional` are both leverage-independent — sizing is driven by `exposure_abs * max_notional_cap`, not by leverage | `instrument_quantizer.py:136-150` |
| F-12 | `margin_required` from the quantizer is emitted in `EVT:STRATEGY_SIGNAL_PRODUCED` payload but is NOT consumed by decision-making domain for any gate or score | Grep `apps/reference/domains/decision_making/` for `margin_required` → zero hits |
| F-13 | `ExposureGuard.resolve_symbol_leverage()` reads exclusively `instruments.<SYM>.execution.target_leverage` with fail-closed `ConfigContractError`; annotation: "SSOT: instruments.<SYM>.execution.target_leverage (instruments.yaml)" | `exposure_guard.py:374-422` |
| F-14 | `fsm_open.py` line 801: `expected_leverage = execution_config.target_leverage` — reads from `instruments` for exchange leverage verification | `fsm_open.py:801` |
| F-15 | `leverage_config.py:collect_configs()` comment: "LEVERAGE-SSOT-FIX-01: Read from instruments.<SYM>.execution.target_leverage instead of strategies.*.assets.<SYM>.leverage to avoid SSOT conflict." — explicit prior migration documented | `apps/reference/domains/execution_position/guards/leverage_config.py:99-100` |
| F-16 | `LeverageBootstrapper` receives `LeverageConfig` objects built from instruments values; calls `adapter.set_leverage(symbol, target_leverage)` → actual exchange API call | `leverage_bootstrapper.py:164-198` |
| F-17 | The `LeverageConfig` class (from `apps/reference/config/shared/instruments.py`) is reused: as model for `aurora.assets.<SYM>.leverage` (strategy-local) AND as return type of `collect_configs()` (built from instruments values) | `config/shared/instruments.py:32-47`; `leverage_config.py:151-155` |
| F-18 | No file other than `decision.py` in `apps/reference/domains/strategies/runtimes/aurora/` references `leverage` | Directory grep across `__init__.py`, `handler.py`, `holding_period.py`, `scoring_helpers.py`, `tpsl.py` |

---

## Section 3: INFERENCES

| # | Inference | Basis |
|---|-----------|-------|
| I-01 | `aurora.assets.leverage.target` is a **strategy-local margin estimate** — it feeds only `margin_required` in the quantizer, which is a diagnostic field in the signal payload. It does not affect qty, notional, exchange leverage, or any execution gate. | F-09, F-10, F-11, F-12 |
| I-02 | `instruments.execution.target_leverage` is the **execution-canonical leverage** — it drives actual exchange leverage setting, exposure guard margin accounting, and open-position leverage verification. It is the SSOT for all execution-layer leverage decisions. | F-13, F-14, F-15, F-16 |
| I-03 | The two surfaces serve distinct semantic layers. There is no execution-correctness conflict: execution always uses instruments (correct). The conflict is in **diagnostic accuracy**: `margin_required` in `EVT:STRATEGY_SIGNAL_PRODUCED` is computed with aurora's leverage (wrong for BTCUSDT and DOGEUSDT). | I-01, I-02, F-01, F-04 |
| I-04 | For BTCUSDT (aurora=35, instruments=25): margin_required in signal payload underestimates actual exchange margin by ~28%. For DOGEUSDT (aurora=20, instruments=10): margin_required underestimates actual exchange margin by ~50%. The operator who reads signal payloads for margin analysis sees incorrect values. | F-01, F-04, F-10 |
| I-05 | `aurora.assets.leverage.mode` is never consumed by any runtime code in the Aurora strategy. Only `leverage.target` and `leverage.max_notional_value` are read (decision.py lines 1620-1623). The `mode` field is dead config in the aurora strategy context. For execution, margin mode comes from `instruments.execution.margin_mode`. | F-18, F-05 |
| I-06 | The `LEVERAGE-SSOT-FIX-01` comment in `leverage_config.py` confirms that a prior migration deliberately moved away from reading `aurora.assets.leverage.target` for execution purposes. This migration was complete for execution-layer consumers but was NOT applied to the quantizer in `decision.py`. | F-15, F-08 |
| I-07 | The hardcoded fallback `getattr(leverage_cfg, "target", 20)` in decision.py line 1621 means that if `aurora.assets.<SYM>.leverage` is absent or null, the quantizer silently uses leverage=20. This is a silent default for a diagnostic field — acceptable but worth documenting. | F-07 |
| I-08 | LEV-03 is best classified as a **strategy-local diagnostic surface** that was intentionally not migrated during LEVERAGE-SSOT-FIX-01 (because it feeds a non-execution, non-gating field). The narrow safe seam is to repoint the quantizer to read from instruments SSOT, making margin_required accurate. | I-01 through I-07 |
| I-09 | `aurora.assets.leverage.max_notional_value = null` for all audited symbols. The quantizer's max_notional_cap therefore defaults to `Decimal("1000000")` USDT (hardcoded fallback). This is a second live dependency on the aurora leverage block — any repointing seam must also handle this field. | F-06, decision.py:1623 |

---

## Section 4: ASSUMPTIONS

| # | Assumption |
|---|-----------|
| A-01 | `aurora.assets.leverage.target` values (35 for BTCUSDT, 20 for DOGEUSDT) were not intentionally set higher than instruments values for a strategy-specific risk model. No design doc or comment explains the divergence as intentional. |
| A-02 | `margin_required` in `EVT:STRATEGY_SIGNAL_PRODUCED` is treated as a diagnostic/telemetry field, not as an input to downstream systems that gate or size trades. |
| A-03 | The hardcoded `max_notional_value = null` → `Decimal("1000000")` fallback in the quantizer is a conservative safe default and not an operator-tunable param today. |
| A-04 | No external tooling (dashboards, ops scripts) uses `margin_required` from the signal payload as a risk limit input. |

---

## Section 5: UNKNOWNS

| # | Unknown | Risk |
|---|---------|------|
| U-01 | Whether the divergence BTCUSDT=35 (aurora) vs 25 (instruments) was intentional at authorship time — e.g., the strategy author may have intended 35x leverage for sizing estimation while the exchange was set to 25x for safety | MEDIUM — without the original intent, repointing the quantizer is a behavior change to `margin_required`. However, since no gate or execution decision uses `margin_required`, the runtime risk is LOW |
| U-02 | Whether any WAL consumer, external reporting tool, or monitoring dashboard reads `margin_required` from the signal payload and uses it for limit-checking | LOW — no domain code in `apps/` consumes it; external tooling is unaudited |
| U-03 | Whether `aurora.assets.leverage.mode` was intended to drive margin mode selection on the exchange (independent of instruments.margin_mode) | LOW — no consumer of `leverage.mode` found in any aurora runtime file |
| U-04 | Whether `max_notional_value = null` → 1,000,000 USDT fallback was intentional or an oversight. If operators need per-symbol notional caps, this would need an explicit config surface. | LOW — the quantizer default of 1M USDT is large enough not to bind for typical trading |

---

## Section 6: Leverage Surface Inventory

### LEV-01 (closed): `trading.execution.exposure.leverage_defaults`
- **Status:** REMOVED (LEV-REMOVE-DEFAULTS-2026-05-09, FIXED_AND_VALIDATED)

### LEV-02 (active): `instruments.<SYM>.execution.target_leverage`
- **Physical file:** `config/aurora/instruments.yaml`
- **Model:** `InstrumentExecutionConfig.target_leverage: int` (ge=1, le=125)
- **Values:** BTCUSDT=25, ETHUSDT=20, SOLUSDT=20, XRPUSDT=20, DOGEUSDT=10
- **Status:** `active_single_owner` — all execution-layer consumers; SSOT annotation explicit

### LEV-03 (this audit): `aurora.assets.<SYM>.leverage.target`
- **Physical file:** `config/aurora/strategies/aurora.yaml`
- **Model:** `LeverageConfig.target: int` (ge=1, le=125) embedded in `AuroraInstrumentConfig.leverage`
- **Values:** BTCUSDT=35, ETHUSDT=20, DOGEUSDT=20 (SOLUSDT/XRPUSDT: not audited here)
- **Status:** `strategy_local_distinct` — single consumer (quantizer), non-execution semantic

### LEV-04 (co-located in LEV-03): `aurora.assets.<SYM>.leverage.max_notional_value`
- **Physical file:** `config/aurora/strategies/aurora.yaml`
- **Values:** All audited symbols = null
- **Status:** `strategy_local_distinct` — consumed by quantizer for max_notional_cap (defaulting to 1M USDT when null)

### LEV-05 (co-located in LEV-03): `aurora.assets.<SYM>.leverage.mode`
- **Physical file:** `config/aurora/strategies/aurora.yaml`
- **Values:** All audited symbols = ISOLATED
- **Status:** `dead_schema` in aurora runtime — no consumer in any aurora strategy file; exchange margin mode driven by `instruments.execution.margin_mode`

---

## Section 7: Ownership Classification Table

| surface_id | yaml_path | physical_file | semantic_concept | runtime_consumer | runtime_owner_status | current_status | evidence | recommended_action |
|---|---|---|---|---|---|---|---|---|
| LEV-02 | `instruments.<SYM>.execution.target_leverage` | `instruments.yaml` | Execution-canonical leverage: exchange setting, exposure guard margin, position verification | `ExposureGuard.resolve_symbol_leverage()`, `fsm_open.py:801`, `leverage_config.py:collect_configs()`, `LeverageBootstrapper.set_leverage()` | active_single_owner | Proven sole owner of all execution-layer leverage decisions | F-13 through F-16; LEVERAGE-SSOT-FIX-01 annotation | Preserve as-is; document as sole execution leverage SSOT |
| LEV-03 | `aurora.assets.<SYM>.leverage.target` | `aurora.yaml` | Strategy-local margin estimate: feeds only `QuantizedPosition.margin_required` in signal payload | `decision.py:1621` via `quantize_exposure(leverage=target_leverage)` | strategy_local_distinct | Active but isolated to diagnostic field; does not affect qty, notional, or execution gates | F-07 through F-12; quantizer comment lines 186-187 | Repoint to `instruments.execution.target_leverage` (LEV-REPOINT-QUANTIZER) |
| LEV-04 | `aurora.assets.<SYM>.leverage.max_notional_value` | `aurora.yaml` | Strategy-local notional cap for quantizer | `decision.py:1623` | strategy_local_distinct | Active but null for all audited symbols; defaults to 1M USDT | F-06, decision.py:1623 | Evaluate independently; do not touch in LEV-REPOINT-QUANTIZER seam |
| LEV-05 | `aurora.assets.<SYM>.leverage.mode` | `aurora.yaml` | Margin mode annotation (ISOLATED/CROSSED) | None — zero runtime consumers in aurora strategy runtime | dead_schema | Dead config: exchange margin mode driven by `instruments.execution.margin_mode` | F-05, F-18 | Document as dead; remove in a dedicated future seam after verifying no external reads |

---

## Section 8: Concrete Symbol Examples

### BTCUSDT — Divergent (highest risk)

```
aurora.assets.BTCUSDT.leverage.target = 35
instruments.BTCUSDT.execution.target_leverage = 25

Strategy signal path (decision.py):
  quantize_exposure(leverage=35, ...)
  → margin_required = notional / 35
  → e.g., 100,000 USDT notional → margin_required ≈ 2,857 USDT

Execution path (instruments SSOT):
  LeverageBootstrapper.set_leverage("BTCUSDT", 25)   → exchange set to 25x
  ExposureGuard.resolve_symbol_leverage("BTCUSDT")   → returns 25
  exposure_guard margin = notional / 25               → 100,000 / 25 = 4,000 USDT

Diagnostic gap: strategy signal emits margin_required ≈ 2,857 USDT
               actual execution margin = 4,000 USDT
               underestimate: ~28.6%
```

### ETHUSDT — Aligned (no gap)

```
aurora.assets.ETHUSDT.leverage.target = 20
instruments.ETHUSDT.execution.target_leverage = 20

Strategy signal path: margin_required = notional / 20
Execution path:      exchange set to 20x, exposure_guard = notional / 20
Diagnostic gap: zero — values agree
```

### DOGEUSDT — Divergent (largest relative gap)

```
aurora.assets.DOGEUSDT.leverage.target = 20
instruments.DOGEUSDT.execution.target_leverage = 10

Strategy signal path (decision.py):
  quantize_exposure(leverage=20, ...)
  → margin_required = notional / 20
  → e.g., 10,000 USDT notional → margin_required = 500 USDT

Execution path (instruments SSOT):
  LeverageBootstrapper.set_leverage("DOGEUSDT", 10)  → exchange set to 10x
  ExposureGuard.resolve_symbol_leverage("DOGEUSDT")  → returns 10
  exposure_guard margin = notional / 10              → 10,000 / 10 = 1,000 USDT

Diagnostic gap: strategy signal emits margin_required = 500 USDT
               actual execution margin = 1,000 USDT
               underestimate: 50%
```

---

## Section 9: Safe Next Implementation Seam

**Seam ID:** LEV-REPOINT-QUANTIZER-2026-05-09

**Problem:** `decision.py:1621` reads `aurora.assets.<SYM>.leverage.target` for the quantizer. The resulting `margin_required` field in `EVT:STRATEGY_SIGNAL_PRODUCED` underestimates actual execution margin for BTCUSDT (−28.6%) and DOGEUSDT (−50%).

**Proposed fix (narrow):**

Repoint line 1621 in `decision.py` from:
```python
leverage_cfg = getattr(instr_cfg, "leverage", None)
target_leverage = getattr(leverage_cfg, "target", 20)
```

To read from `config.instruments.<SYM>.execution.target_leverage` directly — the same path used by all execution-layer consumers.

**Why this is safe:**
- `margin_required` is diagnostic only (F-12). No gate or scoring depends on it.
- The execution layer is already correct (instruments SSOT is already in place).
- The change makes signal payload margin_required consistent with actual execution margin.
- It brings the quantizer in line with the LEVERAGE-SSOT-FIX-01 migration already applied to all other consumers.

**What is NOT in scope for this seam:**
- `aurora.assets.leverage.mode` (dead schema, separate seam)
- `aurora.assets.leverage.max_notional_value` (null for all active symbols; independent evaluation needed)
- Any changes to `instruments.yaml` values
- Removal of the `aurora.assets.<SYM>.leverage` block from aurora.yaml (that is a separate downstream seam, only after the repoint is proven)

**Pre-implementation checklist:**
1. Confirm `self._get_instrument_config(symbol)` has access to `config.instruments` in `decision.py` — or find the path from the handler context that reaches instruments config
2. Confirm no test explicitly asserts `margin_required == notional / aurora_leverage_target` (would need to update to instruments value)
3. Run focused validation on `EVT:STRATEGY_SIGNAL_PRODUCED` payloads in test suite

---

## Section 10: Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| BTCUSDT margin_required underestimate (~28.6%) misleads operator telemetry analysis | MEDIUM | Fixed by LEV-REPOINT-QUANTIZER; no runtime correctness impact today since margin_required is diagnostic only |
| DOGEUSDT margin_required underestimate (~50%) is most severe | MEDIUM | Fixed by LEV-REPOINT-QUANTIZER |
| Aurora's `leverage.target = 35` for BTCUSDT may be intentionally higher than instruments=25 — a risk model where the strategy estimates margin at higher leverage to appear more conservative in signal payloads | LOW-MEDIUM | Unknown intent (U-01). Repointing changes margin_required to be accurate, not conservative. If intent was conservatism, this is a behavior change to telemetry. |
| Hardcoded fallback `getattr(leverage_cfg, "target", 20)` silently defaults to 20 if aurora.assets.leverage is absent | LOW | After repoint, this fallback is replaced by a fail-closed read from instruments (which already has its own `ConfigContractError` guard) |
| `aurora.assets.leverage.mode` dead schema may confuse operators who add/edit it thinking it affects execution | LOW | Document as dead; tombstone comment in aurora.yaml |
| `max_notional_value = null` → 1M USDT cap may silently bind for very large positions | LOW | Out of scope; document as independent evaluation item |

---

## Section 11: Final Verdict

```
READY_FOR_NARROW_IMPLEMENTATION
```

**Rationale:**

LEV-03 (`aurora.assets.<SYM>.leverage.target`) is a **strategy-local margin estimate** consumed exclusively by the Aurora strategy quantizer in `decision.py:1621`. It feeds only `QuantizedPosition.margin_required` — a diagnostic field emitted in the strategy signal payload. It has zero impact on order sizing (qty and notional are leverage-independent), zero impact on exchange leverage setting, and zero impact on exposure guard accounting. There is no execution-correctness conflict.

**However, there is a diagnostic-accuracy conflict.** The aurora leverage values diverge from instruments for BTCUSDT (35 vs 25, −28.6% margin underestimate) and DOGEUSDT (20 vs 10, −50% margin underestimate). This makes `margin_required` in `EVT:STRATEGY_SIGNAL_PRODUCED` inaccurate for these symbols.

The safe seam is `LEV-REPOINT-QUANTIZER-2026-05-09`: repoint `decision.py:1621` to read from `instruments.<SYM>.execution.target_leverage` (the same path used by all execution-layer consumers since `LEVERAGE-SSOT-FIX-01`). This closes the diagnostic gap without changing any execution behavior.

**After the repoint:**
- `aurora.assets.<SYM>.leverage.target` becomes unused in runtime code
- `aurora.assets.<SYM>.leverage.mode` is already dead
- A follow-on seam can remove the `leverage:` block from each aurora.yaml asset entry
- The `LeverageConfig` class would no longer be embedded in `AuroraInstrumentConfig` (separate, later seam)

**OS entry recommended:** Register as OS-014 (aurora quantizer leverage repoint).
