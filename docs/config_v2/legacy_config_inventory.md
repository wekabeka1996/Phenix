# Legacy Config Inventory (v1 → v2 перехід)

## 1. Пошукові патерни

- `rg -n "config/aurora/trading.yaml|config/aurora/system.yaml|config/aurora/regime.yaml|trading_v0\.2\.yaml|trading.staging.override.yaml|configs/master_config_v1.yaml"` — знайшов всі згадки у текстових документах.
- `rg -n "config/aurora" --type-add 'py:*.py' -tpy` — відфільтрував згадки у `.py` скриптах/тестах.
- `rg -n "open\('config/aurora" | rg -n "open\"config/aurora"` (декілька варіантів) підтвердили примітки про ручне читання файлiв через `open(...)`.

## 2. Знайдені згадки

| Path | Kind | Intent | Match | Migration plan |
|---|---|---|---|---|
| `apps/reference/config_features.py:26` | runtime | doc_example | Docstring mentions “legacy config/aurora/trading.yaml” as source for feature-engineering defaults. | `doc_only` (mention only; no actual open). |
| `apps/reference/config_regimes.py:25` | runtime | doc_example | Docstring references “legacy config/aurora/regime.yaml and trading.yaml” when building regime config. | `doc_only`. |
| `tools/validate_testnet.py:50` | tool | analysis_only | CLI helper prints “config/aurora/trading.yaml” when explaining how `trading_mode` is derived. | `migrate_to_v2` (point message at validator/ConfigLoader). |
| `tools/validate_configs.py:122` | tool | runtime_config | Validation suite lists `'config_file': Path('config/aurora/trading.yaml')`. | `migrate_to_v2` (switch validator to config v2 payloads). |
| `tools/validate_configs.py:127` | tool | runtime_config | Same suite points at `config/aurora/system.yaml`. | `migrate_to_v2`. |
| `tools/validate_configs.py:132` | tool | runtime_config | Same suite points at `config/aurora/regime.yaml`. | `migrate_to_v2`. |
| `tools/build_project_atlas.py:240` | tool | analysis_only | Atlas generator checks `configs/master_config_v1.yaml` when assembling merged defaults. | `mark_legacy_skip` (flag file as legacy documentation). |
| `tools/config_inventory.py:21` | tool | analysis_only | Inventory script lists `configs/master_config_v1.yaml` among legacy sources. | `mark_legacy_skip` (keep for historical snapshots). |
| `tests/tools/test_config_inventory.py:35` | test | fixture | Test ensures `configs/master_config_v1.yaml` gets enumerated alongside v2 files. | `mark_legacy_skip` (skip once v2-only). |
| `tests/test_order_40usd.py:16,230` | test | doc_example | Test prints banners/captions referencing `config/aurora/trading.yaml` when describing scenario setups. | `doc_only`. |
| `tests/test_phase10_documentation.py:279,341,353` | test | doc_example | Documentation-style test points readers to `config/aurora/trading.yaml` and even copies it to `/etc/aurora/trading.staging.yaml`. | `doc_only` (no runtime dependency). |
| `tests/domains/config_loader.py:65` | test helper | doc_example | Docstring explains default `config_dir` lies under `config/aurora`. | `doc_only`. |
| `tests/integration/test_hybrid_risk_source_override.py:43` | test | fixture | Temporary setup creates `config/aurora` dir (`config_dir = tmp_path / "config" / "aurora"`). | `keep_as_fixture` (needed to exercise legacy loader). |
| `docs/ANALYSIS_order_guardian_round1.md:5` (plus related docs such as `docs/ANALYSIS_execution_facts_round0.md`, `docs/ANALYSIS_duplication_round1.md`) | doc | analysis_only | Audit notes still cite `config/aurora/trading.yaml`, `config/aurora/regime.yaml` and `configs/master_config_v1.yaml` when tracing legacy behaviour chains. | `doc_only` (historical analysis). |
| `docs/config_analysis/config_inventory.md:51` | doc | analysis_only | Notes duplication between `trading.yaml` and `trading_v0.2.yaml` (legacy records). | `doc_only`. |

## 3. Попередні висновки

- Зібрано 14 конкретних згадок у виконуваному/тестовому коді та утилітах (`apps/reference/...`, `tools/...`, `tests/...`) і щонайменше 4 документальні звіти, що натякають на застарілі файли.
- Найбільший приорітет мають тулзи (`tools/validate_configs.py`, `tools/validate_testnet.py`, `tools/build_project_atlas.py`), які все ще відкрито читають `config/aurora/*.yaml` або `configs/master_config_v1.yaml` — їх треба замінити або виключити зі стандартного запуску.
- Тестові/документальні згадки (`tests/test_order_40usd.py`, `tests/test_phase10_documentation.py`, `docs/...`) можна залишити як `doc_only`, але варто позначити їх у майбутньому звіті чи відправити до `docs/` для уточнення, що реальний pipeline використовує config v2. Higher priority для фіксів мають `tools/` скрипти, де `migration_plan=migrate_to_v2`. This inventory sets the stage for targeted refactors described in TASK 7.11 (migrate-to-v2 vs keep legacy fixtures vs doc-only references).
