# Phase 1 FAST — Walkthrough

## Зміни по PKG

### PKG-1: MAD Z-Score
- **Файли змінені:** 
  - `apps/reference/config_models.py` (added `robust_method`)
  - `apps/reference/domains/system_stress/system_stress_overlay.py` (implemented `_z_robust` with normal MAD scaling factor, updated `_emit` with 8 metrics)
  - `schemas/system_stress_state_updated_v1.json` (added `z_mad_atr`, `z_mad_vol`, `z_mad_gap`, `z_mad_range`)
  - `config/docs/regime_passport.md` (added `robust_method` documentation)
- **Файли створені:**
  - `tests/domains/system_stress/test_z_robust.py`
  - `tests/domains/system_stress/test_fat_tail_robustness.py`
- **Тести:** 6 tests, all passed.
- **Конфіг:** 
  - Added `robust_method: "none"` to `system_stress` section of `config/aurora/regime.yaml`.
- **Паспорт:** Додано запис для `system_stress.robust_method`.

### PKG-2: EMA Smoother
- **Файли змінені:**
  - `apps/reference/config_models.py` (added `RegimeSmoothingConfig`, `decision.regime_smoothing`)
  - `apps/reference/domains/decision_making/aurora_scoring_kernel.py` (hooked smoother inside `compute`)
  - `apps/reference/domains/decision_making/aurora_decision.py` (passed smoother to kernel compute kwargs)
  - `apps/reference/domains/decision_making/aurora_handler.py` (initialized `RegimeMultiplierSmoother`)
  - `config/aurora/strategies/aurora.yaml` (added `decision.regime_smoothing`)
  - `config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md` (added parameter docs)
- **Файли створені:**
  - `apps/reference/domains/decision_making/regime_smoother.py`
  - `tests/domains/decision_making/test_regime_smoother.py`
  - `tests/config/test_regime_smoothing_config.py`
- **Тести:** 9 tests, all passed.
- **Конфіг:** Додано блок `regime_smoothing` (fail-closed, `enabled: false`) до стратегії `aurora.yaml`.
- **Паспорт:** Додано `decision.regime_smoothing.enabled`, `method`, `ema_alpha`, `ramp_bars`.

### PKG-3: Inception Filter
- **Файли змінені:**
  - `apps/reference/config_models.py` (added `RegimeShiftInceptionConfig` into `AuroraConfig`)
  - `apps/reference/domains/decision_making/aurora_handler.py` (listens to `EVT:SYSTEM_STRESS_STATE_UPDATED`, caches `regime_raw_event` and `system_stress_state`)
  - `apps/reference/domains/decision_making/aurora_decision.py` (hooked inception filter before strict regime allowlist, scales position using `micro_size_fraction`, injects it via `sizing.margin_pct_mult`)
  - `apps/reference/domains/decision_making/strategy_gateway.py` (applies `margin_pct_mult` from `sizing` in strategy signal)
  - `apps/reference/domains/strategies/plugins/aurora_builtin.py` (added FSM listener for system stress)
  - `apps/reference/dictionaries/verb_registry_v1.yaml` (registered `EVT:REGIME_SHIFT_SUSPECTED`)
  - `config/aurora/regime.yaml` (added `regime_shift_inception`)
  - `config/docs/regime_passport.md` (added passport for new keys)
- **Файли створені:**
  - `apps/reference/domains/decision_making/inception_filter.py`
  - `apps/reference/domains/decision_making/schemas/regime_shift_suspected_v1.json`
  - `tests/domains/decision_making/test_inception_filter.py`
  - `tests/config/test_inception_config.py`
- **Тести:** 10 tests, all passed.
- **Конфіг:** Додано блок `regime_shift_inception` (`enabled: false`) в `regime.yaml`.
- **Паспорт:** Додано записи `regime_shift_inception.enabled`, `action`, `micro_size_fraction`.

## Тести
- Total tests (new added): 25
- All passing: yes
- Failing tests (if any): None

## Config Changes
| File | Field Added | Default | Type |
|------|------------|---------|------|
| `regime.yaml` | `system_stress.robust_method` | `"none"` | `str` |
| `aurora.yaml` | `decision.regime_smoothing` | `enabled: false, method: "ema", ema_alpha: 0.3, ramp_bars: 6` | `object` |
| `regime.yaml` | `regime_shift_inception` | `enabled: false, action: "none", micro_size_fraction: 0.25` | `object` |

## Passport Updates
| Passport File | Fields Added |
|---|---|
| `regime_passport.md` | `system_stress.robust_method`, `regime_shift_inception.enabled`, `action`, `micro_size_fraction` |
| `AURORA_STRATEGY_CONFIG_PASSPORT.md` | `decision.regime_smoothing.enabled`, `method`, `ema_alpha`, `ramp_bars` |

## Відомі обмеження
- **Scale-up rule:** Scale-up behavior (перехід з мікро-сайзу до повного сайзу) буде повністю перекрито логікою з Phase 2 або ExposureGuard. Зараз позиція залишається мікро-розміру (на основі `margin_pct_mult`) або закривається звичайними правилами виходу (якщо stable regime не підтверджує вхід). TODO: Реалізація автоматичного scale-up на льоту при підтвердженні режиму в майбутніх фазах.
- **Micro-size Application:** Скейлінг реалізовано через передачу `margin_pct_mult` в `EVT:STRATEGY_SIGNAL_PRODUCED` (`sizing` об'єкт) -> `strategy_gateway` перемножує його на базовий `margin_pct_mult` (що цілком сумісне з наявними VolAdjGates та StressGuard attenuation).

## Rollback
- PKG-1: `robust_method: "none"` в `config/aurora/regime.yaml`
- PKG-2: `regime_smoothing.enabled: false` в `config/aurora/strategies/aurora.yaml`
- PKG-3: `regime_shift_inception.enabled: false` в `config/aurora/regime.yaml`
