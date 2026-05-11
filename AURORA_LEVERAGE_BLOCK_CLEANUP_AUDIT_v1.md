# AURORA_LEVERAGE_BLOCK_CLEANUP_AUDIT_v1

**Date:** 2026-05-10
**Track:** config / SSOT / leverage block cleanup
**Scope:** aurora.assets.<SYM>.leverage.{target, mode, max_notional_value} removal readiness
**Verdict:** `MUST_SPLIT_MAX_NOTIONAL_VALUE`

---

## Section 1: Scope

Following `AURORA_QUANTIZER_LEVERAGE_REPOINT_REPORT_v1` (verdict: FIXED_AND_VALIDATED), this audit determines whether the three remaining fields of the `aurora.assets.<SYM>.leverage` block in `aurora.yaml` — `target` (LEV-03), `mode` (LEV-05), and `max_notional_value` (LEV-04) — are safe to remove.

**Candidate seam**: Remove `leverage.target` and `leverage.mode` from `aurora.yaml` and the supporting Pydantic model, while deferring `max_notional_value` to a separate seam.

---

## Section 2: Field Classification

| Field | LEV tag | YAML values (7 symbols) | Runtime reads | Classification |
|-------|---------|-------------------------|---------------|----------------|
| `target` | LEV-03 | 10–35 (per-symbol) | `validate_ssot_consistency()` comparison/logging only | dead_schema (logging survivor) |
| `mode` | LEV-05 | ISOLATED (all 7) | None (no runtime reads confirmed) | dead_schema |
| `max_notional_value` | LEV-04 | null (all 7) | `decision.py:1630` — live read, robust to None | metadata_only (live path, all null) |

---

## Section 3: FACTS

| # | Fact | Evidence |
|---|------|----------|
| F-01 | `leverage_config.py:183` reads `asset_cfg.leverage.target` in `validate_ssot_consistency()` | `leverage_config.py:163-218` |
| F-02 | `validate_ssot_consistency()` is purely diagnostic: compares aurora value vs instruments SSOT, logs a WARNING string, returns list. No conditional branching on the value affects execution. | `leverage_config.py:163-218` |
| F-03 | `validate_ssot_consistency()` aurora block is wrapped in `try/except AttributeError: pass` (line 193). If `asset_cfg.leverage` is None or absent → silently skips. Removal of `leverage.target` from aurora.yaml → function returns empty warnings list. | `leverage_config.py:178-194` |
| F-04 | `decision.py` (post-LEV-REPOINT-QUANTIZER-2026-05-09) no longer reads `aurora.assets.<SYM>.leverage.target` for any computation. | `AURORA_QUANTIZER_LEVERAGE_REPOINT_REPORT_v1 S3` |
| F-05 | `leverage.mode` has zero runtime reads across all aurora runtime files. `validate_ssot_consistency()` reads only `target`, not `mode`. | Full codebase search — no reads of `asset_cfg.leverage.mode` outside config loading |
| F-06 | `decision.py:1630`: `max_notional_cap = getattr(leverage_cfg, "max_notional_value", None) or decimal.Decimal("1000000")` — live read of `aurora.assets.<SYM>.leverage.max_notional_value`. | `decision.py:1630` (post-repair) |
| F-07 | All 7 aurora symbols have `max_notional_value: null` in `aurora.yaml`. The live code path at F-06 always resolves to the default `1_000_000 USDT`. No per-symbol notional cap is operationally in effect. | `config/aurora/strategies/aurora.yaml` (BTCUSDT:579, ETHUSDT:384, SOLUSDT:469, DOGEUSDT:900, XRPUSDT:1004, BNBUSDT:685, 1000PEPEUSDT:790) |
| F-08 | If `leverage_cfg = None` (because aurora.yaml leverage block is absent), `getattr(None, "max_notional_value", None)` → `None` → defaults to `decimal.Decimal("1000000")`. The code is already robust to leverage block removal via the `getattr` pattern. | `decision.py:1628-1630` |
| F-09 | `test_btcusdt_aurora_runtime_fields.py:146`: `assert btc_cfg.leverage.target == 21` — direct assertion on `config.strategies.aurora.assets["BTCUSDT"].leverage.target` (aurora config). This test would fail if `target` is removed from aurora.yaml (Pydantic required field → load fails) or if `LeverageConfig` is removed from `AuroraInstrumentConfig`. | `tests/config/test_btcusdt_aurora_runtime_fields.py:146` |
| F-10 | Same test line 63 comment: `# Leverage (stale copy in aurora.yaml, kept for legacy audit)` — the test explicitly documents this as a legacy audit field. | `tests/config/test_btcusdt_aurora_runtime_fields.py:63` |
| F-11 | `test_btcusdt_aurora_runtime_fields.py:264-265`: `assert leverage_cfgs["BTCUSDT"].target == 21` and `assert leverage_cfgs["BTCUSDT"].mode == "ISOLATED"` — these test `collect_configs()` return value. `collect_configs()` reads exclusively from `instruments.yaml` SSOT (not aurora). The `21` comes from `instruments_data["instruments"]["BTCUSDT"]["execution"]["target_leverage"] = 21` (test line 53). Does NOT test aurora.yaml leverage values. | `leverage_config.py:96-161`, `tests/config/test_btcusdt_aurora_runtime_fields.py:53,264-265` |
| F-12 | `test_leverage_runtime_wiring.py:282-283`: `assert configs["BTCUSDT"].target == 20` and `assert configs["BTCUSDT"].mode == "ISOLATED"` with comment `# From instruments`. Tests `collect_configs()` return, instruments-derived. Does NOT test aurora.yaml leverage values. | `tests/domains/execution_position/test_leverage_runtime_wiring.py:280-283` |
| F-13 | `AuroraInstrumentConfig.leverage: Optional[LeverageConfig] = Field(...)` — optional type but required presence in YAML. `LeverageConfig.target: int = Field(...)` and `.mode: Literal[...] = Field(...)` are both required (no default). Removing `target`/`mode` from aurora.yaml while keeping a `leverage:` key would cause Pydantic validation failure at load. | `apps/reference/config/strategies/aurora.py:272-274`, `apps/reference/config/shared/instruments.py:32-47` |
| F-14 | `LeverageConfig` is also the return type of `collect_configs()` — used for both aurora asset config representation and the instruments-derived bootstrap config. Both usages coexist in the same model. | `leverage_config.py:151-155`, `apps/reference/config_models.py` |

---

## Section 4: Blocker Analysis

### LEV-03 (`leverage.target`) — REMOVABLE WITH TEST UPDATE

**Runtime blockers**: None.
- `validate_ssot_consistency()` reads it for logging only, protected by `try/except AttributeError`. Removing `target` from aurora.yaml → function silently skips the comparison for that symbol. Zero execution consequence.
- `decision.py` no longer reads it (post-repoint).

**Test blockers**: One soft blocker.
- `test_btcusdt_aurora_runtime_fields.py:146`: `assert btc_cfg.leverage.target == 21` — directly asserts on aurora config. Must be updated as part of the cleanup seam. The test comment (F-10) explicitly labels this as a legacy audit line.
- `test_btcusdt_aurora_runtime_fields.py:64-65`: Sets `btc["leverage"]["target"] = 21` and `btc["leverage"]["mode"] = "ISOLATED"` in the test mutation helper. Must be removed if the leverage block is removed.

**Model blocker**: Requires resolving (see Section 5).
- `LeverageConfig.target` is `Field(...)` (required). Must be made optional OR the field removed from the model. The safest approach for a targeted `target`+`mode` removal while keeping `max_notional_value` is to introduce a slim `AuroraLeverageOverrideConfig` with only `max_notional_value: Optional[Decimal]`.

### LEV-05 (`leverage.mode`) — REMOVABLE

**Runtime blockers**: None.
- No runtime code reads `asset_cfg.leverage.mode` outside of config loading.
- `validate_ssot_consistency()` does NOT read mode.

**Test blockers**: None on aurora config directly.
- Lines 264-265 and test_leverage_runtime_wiring.py:282-283 assert on `collect_configs()` return (instruments-derived). Those tests are unaffected by aurora.yaml mode removal.
- Test line 65 sets `btc["leverage"]["mode"] = "ISOLATED"` — must be removed alongside `target`.

### LEV-04 (`leverage.max_notional_value`) — SEPARATE SEAM REQUIRED

**Runtime status**: Live read in `decision.py:1630`. All 7 symbols have `null`. Code is robust to `None` via `getattr` fallback (F-08). But the code path is active and `max_notional_value` is the only field in the leverage block with any forward-utility — it provides a future mechanism to cap per-symbol notional exposure.

**Decision**: Cannot remove in the same seam as `target` + `mode` without explicit evaluation of whether per-symbol notional caps are needed. Operational impact today = zero (all null → always defaults to 1M). But the cap mechanism is architecturally intentional.

---

## Section 5: Seam Design for target + mode Removal

To remove `leverage.target` and `leverage.mode` while keeping `leverage.max_notional_value`:

### Option A — Slim override model (recommended)

Replace `AuroraInstrumentConfig.leverage: Optional[LeverageConfig]` with a new `AuroraLeverageOverrideConfig` containing only `max_notional_value`:

```python
class AuroraLeverageOverrideConfig(BaseModel):
    max_notional_value: Optional[Decimal] = Field(None, ...)

class AuroraInstrumentConfig(BaseModel):
    ...
    leverage: Optional[AuroraLeverageOverrideConfig] = Field(None, ...)
```

Update `aurora.yaml` per symbol:
```yaml
leverage:
  max_notional_value: null   # all 7 symbols currently null
```

Update `decision.py` to use `AuroraLeverageOverrideConfig` (unchanged in effect since max_notional_value is still present).

Remove `validate_ssot_consistency()` `target` read OR simplify to only check that aurora leverage block exists.

### Option B — Set leverage to null in aurora.yaml

Set `leverage: null` for all 7 symbols in aurora.yaml. `Optional[LeverageConfig]` allows None. The `getattr(leverage_cfg, "max_notional_value", None)` fallback handles None gracefully (F-08). `LeverageConfig` model is unchanged.

**Trade-off**: Loses `max_notional_value` override capability completely (it would always be None → always default to 1M). This is operationally equivalent to current state but removes the future cap mechanism.

### Option C — Make target and mode Optional in LeverageConfig

```python
class LeverageConfig(BaseModel):
    target: Optional[int] = Field(None, ge=1, le=125, ...)
    mode: Optional[Literal["ISOLATED", "CROSSED"]] = Field(None, ...)
    max_notional_value: Optional[Decimal] = Field(None, ...)
```

Update aurora.yaml to omit `target` and `mode` (or keep with null). `collect_configs()` is unchanged (still reads from instruments).

**Trade-off**: `LeverageConfig.target` is no longer required — weakens the model contract for callers who expect instruments-derived values (test assertions at F-11/F-12 rely on it being an int). Would need careful review of all `LeverageConfig` usages.

---

## Section 6: What Is NOT Affected

| Surface | Status |
|---------|--------|
| `instruments.execution.target_leverage` | Unchanged — canonical SSOT for all execution consumers and quantizer |
| `collect_configs()` return type | Unchanged — reads instruments, returns `LeverageConfig` |
| `test_leverage_runtime_wiring.py:282-283` | Unchanged — tests instruments-derived values |
| `test_btcusdt_aurora_runtime_fields.py:264-265` | Unchanged — tests instruments-derived values |
| `decision.py` quantizer leverage read | Unchanged — already repointed to instruments (LEV-REPOINT-QUANTIZER-2026-05-09) |
| All execution-layer leverage consumers | Unchanged |

---

## Section 7: Residual State Map

| Field | Status after this audit |
|-------|------------------------|
| `LEV-03`: `aurora.assets.<SYM>.leverage.target` | **READY FOR REMOVAL** — zero execution reads. One test assertion must be updated. Model change required (see Section 5). |
| `LEV-05`: `aurora.assets.<SYM>.leverage.mode` | **READY FOR REMOVAL** — zero runtime reads. No test assertions on aurora config mode directly. Requires same model change as target. |
| `LEV-04`: `aurora.assets.<SYM>.leverage.max_notional_value` | **MUST DEFER** — live code path in `decision.py:1630`. All null (zero operational impact). Per-symbol notional cap mechanism. Separate seam: confirm whether explicit notional caps are needed; if not, remove and replace with constants. |

---

## Section 8: Recommended Next Seam

**Seam ID:** LEV-TARGET-MODE-REMOVE-2026-05-10
**Approach:** Option A (slim override model)

Steps:
1. Introduce `AuroraLeverageOverrideConfig(max_notional_value: Optional[Decimal])` in `config/strategies/aurora.py`
2. Update `AuroraInstrumentConfig.leverage` type from `LeverageConfig` to `AuroraLeverageOverrideConfig`
3. Update `aurora.yaml` — remove `target` and `mode` from all 7 leverage blocks, keep `max_notional_value: null`
4. Remove `asset_cfg.leverage.target` read from `validate_ssot_consistency()` aurora block (or remove the aurora check entirely — the SSOT validation is now moot since aurora no longer carries an authoritative leverage value)
5. Update `test_btcusdt_aurora_runtime_fields.py`: remove lines 64-65 (test mutation) and line 146 (assertion on aurora config leverage.target). Line 264-265 assertions are unaffected.

**Estimate**: 5 files, ~20 line change, zero new regressions expected.

---

## Section 9: Final Verdict

```
MUST_SPLIT_MAX_NOTIONAL_VALUE
```

`leverage.target` (LEV-03) and `leverage.mode` (LEV-05): **removable in the next seam**. Zero execution reads post-LEV-REPOINT-QUANTIZER-2026-05-09. One test assertion on aurora config (`test_btcusdt_aurora_runtime_fields.py:146`) must be updated as part of the seam; it is explicitly labeled as legacy. Model change required to keep `max_notional_value` without `target`/`mode`.

`leverage.max_notional_value` (LEV-04): **must be deferred**. Live code path in `decision.py:1630`. All 7 symbols are null (zero operational impact today). Requires explicit decision on whether per-symbol notional caps are needed before removal.

The `test_leverage_runtime_wiring.py` and `test_btcusdt_aurora_runtime_fields.py:264-265` assertions are NOT blockers — they test `collect_configs()` which reads exclusively from instruments SSOT. Only line 146 (direct aurora config assertion) requires updating.
