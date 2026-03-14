# P2 MR DOGE / High-Beta Hardening Report

## 1. Executive Summary
- Реалізовано вузький config-first hardening для токсичного класу `DOGEUSDT` `FLAT_LOW` SHORT setups.
- Новий контракт: per-asset override `mean_reversion.assets.<SYMBOL>.strategy.flat_low_short_min_bb_width`.
- Runtime тепер fail-closed блокує лише `FLAT_LOW` SHORT, якщо `%B` already wants SHORT, але `bb_width` нижчий за stricter per-symbol floor.
- Канонічний DOGE override виставлено в `0.015`, тоді як загальний `min_bb_width` лишився `0.005`.
- Execution domain, risk semantics, other strategies, global MR thresholds, cooldown/risk logic не змінювались.
- Пакет не є squeeze-expansion veto framework. Він лише прибирає найочевидніший DOGE/high-beta narrow-band breakout-fade class.

## 2. Scope

### Files changed
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/config/test_mean_reversion_yaml_contract.py`
- `reports/forensics/p2_mr_doge_high_beta_hardening_report.md`
- `JOURNAL.md`
- `TODO.md`

### Out of scope
- `execution_position`
- global `min_bb_width` bump for all assets
- momentum/slope framework
- regime redesign
- risk sizing / execution semantics

## 3. New Contract

### New config field
- `mean_reversion.assets.<SYMBOL>.strategy.flat_low_short_min_bb_width`
  - type: optional float
  - validation: strict Pydantic, `extra='forbid'`
  - semantics: if configured, applies only to `FLAT_LOW` SHORT candidate setups for that symbol

### Runtime rule
- Existing generic MR flow still runs first:
  - regime must map to flat
  - regime must be allowlisted
  - generic `min_bb_width <= bb_width <= max_bb_width`
  - `%B` must cross LONG/SHORT entry threshold
- New hardening adds one extra block:
  - if `flat_regime == FLAT_LOW`
  - and `%B` already implies `SHORT`
  - and `flat_low_short_min_bb_width` is configured
  - and `bb_width < flat_low_short_min_bb_width`
  - then emit neutral signal with `why=neutral:flat_low_short_bb_width_too_narrow:<actual><<threshold>`

### Canonical YAML change
- `DOGEUSDT.strategy.flat_low_short_min_bb_width: 0.015`
- No other symbol was changed.

## 4. Red -> Green Evidence

### RED before implementation
Command:
```text
pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q
```
Result:
```text
collected 4 items
FFFF
4 failed in 5.05s
```
What it proved:
- `MRStrategyConfig` had no `flat_low_short_min_bb_width`
- no targeted DOGE hardening seam existed in runtime

Command:
```text
pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q
```
Result:
```text
collected 2 items
F.
1 failed, 1 passed in 5.65s
```
What it proved:
- `MRStrategyOverrideConfig` rejected the new field as `extra_forbidden`
- handler had no typed path to wire the override

Command:
```text
pytest tests/config/test_mean_reversion_yaml_contract.py -q
```
Result:
```text
collected 2 items
.F
1 failed, 1 passed in 6.39s
```
What it proved:
- canonical YAML/typed contract had no visible field for the new hardening path

### GREEN after implementation
Command:
```text
pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q
```
Result:
```text
collected 4 items
....
4 passed in 2.40s
```
What it proves:
- narrow-band `DOGEUSDT` `FLAT_LOW` SHORT is now blocked
- wider-band DOGE `FLAT_LOW` SHORT still passes
- non-target symbols remain unchanged without explicit override
- the gate stays narrow to the toxic class only

Command:
```text
pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q
```
Result:
```text
collected 2 items
..
2 passed in 3.23s
```
What it proves:
- the typed per-asset override is accepted and wired into runtime strategy config

Command:
```text
pytest tests/config/test_mean_reversion_yaml_contract.py -q
```
Result:
```text
collected 2 items
..
2 passed in 3.89s
```
What it proves:
- canonical YAML now exposes the field
- strict contract still rejects misspelled keys instead of silently falling back

Command:
```text
pytest tests/domains/execution_position/test_split_brain_repro.py -q
```
Result:
```text
collected 5 items
.....
5 passed in 31.90s
```
What it proves:
- the strategy-only package did not regress the sentinel P0 execution split-brain suite

## 5. Design Notes
- Я обрав per-asset `FLAT_LOW` short width hardening, бо це найменший safe seam, який уже підтримується existing config merge path.
- Я не взяв глобальний `min_bb_width` bump, бо P1 review already showed that universal hardening is too blunt and would spread blast radius beyond DOGE/high-beta behavior.
- Я не додав squeeze engine, slope engine або momentum framework, бо для P2-A це був би broad redesign, а не мінімальний evidence-based удар по toxic DOGE class.
- `mean_reversion_handler.py` reuse-ить existing neutral-block plumbing: новий gate не відкриває окремий runtime pathway, лише додає один typed override і один explicit neutral reason.

## 6. Remaining Gaps
- Потрібен окремий P2-B пакет на squeeze-expansion veto.
  - Цей пакет блокує narrow-band toxic fades, але не моделює сам breakout expansion.
- Потрібен окремий P2-C пакет на momentum separation / slope veto.
  - Тут навмисно не додано drift/momentum model.
- Broader high-beta family config поки не реалізовано.
  - Поки що захарджено лише DOGE via existing per-asset override path, бо це мав прямий evidence base.

## 7. Commands Run
```text
pytest tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py -q
pytest tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py -q
pytest tests/config/test_mean_reversion_yaml_contract.py -q
pytest tests/domains/test_mean_reversion_strategy.py -q
pytest tests/domains/decision_making/test_mr_bar_gating.py -q
pytest tests/domains/decision_making/test_mean_reversion_handler_hardening_v1.py -q
pytest tests/domains/execution_position/test_split_brain_repro.py -q
```

## 8. Files Changed
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `tests/domains/feature_engineering/test_mean_reversion_doge_hardening.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/config/test_mean_reversion_yaml_contract.py`
- `reports/forensics/p2_mr_doge_high_beta_hardening_report.md`
- `JOURNAL.md`
- `TODO.md`

## 9. JOURNAL / TODO
- `JOURNAL.md` updated with the P2-A implementation entry, RED->GREEN evidence, and remaining follow-ups.
- `TODO.md` updated to mark P2-A complete and keep P2-B / P2-C / doc-sync follow-ups explicit.
