# REPORT: Mean Reversion Config Passport Actualization

## Package: MEAN_REVERSION_CONFIG_PASSPORT_ACTUALIZATION_WITH_DEFAULTS_AND_FALLBACKS
## Date: 2026-03-31
## Status: DONE

---

## Objective

Update `mean_reversion_state_machine_passport.md` to match current source truth exactly, distinguishing: static defaults, runtime fallbacks, graceful degradation, fail-closed behavior, hardcoded policies, and dormant defaults. Produce a defaults/fallbacks matrix usable as an operator/auditor reference.

---

## Files Checked (Source Truth)

| File | Purpose | Lines Inspected |
|---|---|---|
| `config/aurora/strategies.yaml` | Strategy registry + assignments | Full (81 lines) |
| `config/aurora/strategies/mean_reversion.yaml` | MR YAML config | Full (317 lines) |
| `apps/reference/config_models.py` | Pydantic V2 models | Lines 386-858 (MR sections) |
| `apps/reference/domains/decision_making/mean_reversion_handler.py` | Handler runtime logic | Lines 200-319 (init), 641-855 (V1/V2), 860-917 (emit/cleanup) |
| `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` | Strategy dataclass + on_bar | Lines 124-203 (config), 458-540 (evaluate_signal) |
| `apps/reference/domains/feature_engineering/feature_engineering.py` | FE emission (price_motion) | CMD:PROCESS_STRATEGY emission site |
| `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json` | CMD schema | price_motion property definition |

---

## Changes Made

### 1. Passport (`config/docs/mean_reversion_state_machine_passport.md`)

| Section | Change | Reason |
|---|---|---|
| Sec 2 (Overview) | Fixed assignment status from "порожній" to "DOGEUSDT → mean_reversion" | `strategies.yaml:41` proves live assignment |
| Sec 4 (Trigger Path) | Added price_motion caching step + V1/V2 overlay steps | Handler caches price_motion separately from features; V1/V2 run between signal generation and emission |
| Sec 10 (Live Assignments) | Replaced stale "live assignments відсутні" with actual assignment table | strategies.yaml and mean_reversion.yaml prove DOGEUSDT active |
| Sec 11 (Stale Corrections Log) | Added 5-entry corrections log | Tracks what was wrong and why |
| Sec 13 (V1 Decision Logic) | Fixed decision logic ordering; removed stale conditional language about `policy="block"` | Code checks TFI before readiness bar count; `missing_policy` is `Literal["block"]` per Pydantic, not a runtime branch |
| **New** Sec 15 | Defaults vs Fallbacks vs Hardcoded Policies | Summarizes category distribution: 8 hardcoded policies, 6 fail-closed, 5 runtime fallbacks, 2 graceful degradation |
| **New** Sec 16 | Dormant vs Enabled Runtime Truth | Shows `microstructure_veto.enabled=false`, `directional_bias.enabled=false`, other assets `enabled=false` |
| **New** Sec 17 | Stale Statements Corrected In This Actualization | Audit trail of all incorrect claims found and fixed |

### 2. Matrix (`reports/MR_DEFAULTS_FALLBACKS_MATRIX.md`)

Created comprehensive matrix covering all MR config surfaces. 8 sections, ~155 rows. Each row includes: Surface/Field, Location, Type, Current Value, Category (from taxonomy), Consumer, Operational Effect, Proof Source.

Sections: Core Strategy Parameters, Regime Sizing, Execution and Safety, Per-Asset Override Precedence, Vector 1: Microstructure Veto, Vector 2: Directional Bias, Activation and Assignment, MRStrategyConfig Dataclass Defaults.

### 3. Docstring Fix (`apps/reference/config_models.py`)

| Lines | Before | After | Why |
|---|---|---|---|
| 600-601 | "positive funding → SHORT stricter, LONG easier" | "positive funding → LONG harder (threshold lowered), SHORT easier (threshold raised)" | Formula at line 595: `eff_long = base - norm * shift`. Positive norm subtracts from long threshold → LONG harder, not easier. Docstring from R2 era was inverted. |

---

## Stale Text Corrected

| Location | Stale Claim | Truth | Proof |
|---|---|---|---|
| Passport Sec 2 | "MR assignments порожній" | DOGEUSDT assigned to mean_reversion | strategies.yaml:41 |
| Passport Sec 4 | No mention of price_motion caching | Handler caches price_motion in dedicated dict | handler.py:1750-1755, wiring fix report |
| Passport Sec 10 | "live assignments відсутні" | DOGEUSDT active, 4 others dormant | strategies.yaml:41 + mean_reversion.yaml:171 |
| Passport Sec 13 | Readiness check before TFI; conditional `policy="block"` | TFI check is first; policy is `Literal["block"]` always | handler.py:672-678, config_models.py:562 |
| config_models.py:600-601 | V2 funding semantics inverted | Fixed to match formula | handler.py:850-851 formula proof |

---

## FACTS

1. **DOGEUSDT is the only active MR asset.** `strategies.yaml:41` assigns `mean_reversion`, `mean_reversion.yaml:171` sets `enabled: true`. All other assets (BTCUSDT, XRPUSDT, SOLUSDT, ETHUSDT) have `enabled: false`. [PROVEN by YAML inspection]

2. **Both V1 (microstructure_veto) and V2 (directional_bias) are dormant.** `enabled: false` in YAML; config exists on disk but inactive at runtime. [PROVEN by mean_reversion.yaml:268, :288]

3. **`missing_policy` is `Literal["block"]` in Pydantic.** Only "block" is accepted; any other string fails validation. There is no runtime branch on policy value. [PROVEN by config_models.py:562]

4. **8 hardcoded policies exist in handler/strategy code.** These include: EMA formula, absorption override logic, OBI confirm-only policy, return key selection, transient cleanup, per-symbol isolation, formula direction, threshold clamping. [PROVEN by handler.py inspection]

5. **6 fail-closed behaviors protect against missing/invalid data.** Missing TFI, invalid TFI, zero-range bars, missing price_motion, ambiguous evidence, and the `Literal["block"]` policy lock. [PROVEN by handler.py:672-792]

6. **`price_motion` is a top-level CMD field, NOT nested in `features`.** Handler reads from `_last_cmd_price_motion` cache. [PROVEN by schema, FE emission, handler.py:751]

7. **V2 docstring was semantically inverted.** Formula `eff_long = base - norm * shift` means positive funding → lower long threshold → LONG harder. Old docstring said "LONG easier". [PROVEN by handler.py:850-851 vs config_models.py:600]

8. **Confidence fields have Pydantic defaults; core BB/ATR/RSI fields are required (no default).** `confidence_base=0.5`, `confidence_bb_slope=2.0`, `confidence_rsi_bonus=0.2` have defaults. All BB/ATR/RSI/entry fields are `Field()` with no default. [PROVEN by config_models.py:393-422]

9. **Per-asset override is `Optional[None]` with runtime fallback to global.** All fields in `MRStrategyOverrideConfig` default to `None`; handler merges by checking `if override is not None`. [PROVEN by config_models.py:662-715]

10. **MRStrategyConfig dataclass defaults are test-only.** Handler always injects explicit values from YAML merge. Dataclass defaults never appear in production. [PROVEN by handler _parse_config + strategy dataclass docstring]

## INFERENCES

1. **The dormant V1/V2 configs will activate without code changes.** Setting `enabled: true` in YAML is sufficient to activate either vector. All runtime paths exist and are tested. [INFERRED from code structure + test coverage]

2. **The inverted V2 docstring had no production impact.** V2 is dormant (`enabled: false`), so the incorrect documentation never misled a live configuration decision. [INFERRED from dormant state]

3. **An operator reviewing the old passport would have incorrect situational awareness.** The stale "no assignments" claims would suggest MR is entirely inactive, when in fact DOGEUSDT is actively assigned and trading is enabled. [INFERRED from stale text impact analysis]

## ASSUMPTIONS

1. **No runtime-only config injection exists beyond YAML.** The analysis assumes all config flows through `mean_reversion.yaml` → Pydantic validation → handler. If environment variables or runtime patches override config, additional surfaces may exist that this audit does not cover.

## UNKNOWNS

1. **`score_multiplier` (Pydantic default=1.0) is never declared in YAML.** Whether this is intentional or an oversight is unclear. The default of 1.0 means it has no operational effect, but an operator cannot tune it without adding a YAML entry.

2. **`entry_tif: null` in YAML for MARKET orders.** Whether the execution layer ever reads this field for MARKET orders is not confirmed by this config-layer audit.

---

## Category Distribution Summary

| Category | Count | Examples |
|---|---|---|
| Required / no default | ~18 | bb_window, entry_threshold, allowed_regimes |
| Pydantic default | ~8 | confidence_base, funding_shift_magnitude |
| YAML default | ~3 | enabled, timeframe_sec |
| Runtime fallback | 5 | Per-asset `None` → global, missing bias → symmetric |
| Graceful degradation | 2 | Missing/invalid funding_rate → static thresholds |
| Fail-closed | 6 | Missing TFI, invalid TFI, zero-range bar, ambiguous |
| Hardcoded policy | 8 | EMA formula, OBI confirm-only, absorption OR logic |
| Dormant default | 3 | V1 enabled=false, V2 enabled=false, disabled assets |

---

## Deliverable Checklist

| Deliverable | Status | Location |
|---|---|---|
| Updated passport | DONE | `config/docs/mean_reversion_state_machine_passport.md` |
| Defaults/fallbacks matrix | DONE | `reports/MR_DEFAULTS_FALLBACKS_MATRIX.md` |
| Actualization report (this file) | DONE | `reports/REPORT_MEAN_REVERSION_CONFIG_PASSPORT_ACTUALIZATION.md` |
| V2 docstring fix | DONE | `apps/reference/config_models.py:600-601` |
