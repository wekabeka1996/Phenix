# Copilot Master Roadmap (SSOT)

Этот файл — SSOT по инкрементальным пакетам работ (и связанным артефактам).
`TODO.md` остаётся производным и не заменяет SSOT.

## vFoundation Dictionaries / Verb Registry

### VF-VERB-REG
- VF-VERB-REG-01: Seed SSOT verb registry из runtime → `apps/reference/dictionaries/verb_registry_v1.yaml`, `reports/VF-VERB-REG-01.md`.
- VF-VERB-REG-02: Warn-only drift gate (runtime vs registry) → `tests/vfoundation/test_verb_registry_warn_only.py`, `reports/VF-VERB-REG-02_diff.json`, `reports/VF-VERB-REG-02.md`.
- VF-VERB-REG-03: Owner labeling top-N → `reports/VF-VERB-REG-03.md`.
- VF-VERB-REG-04: Evidence-based owner inference report → `tests/vfoundation/test_verb_owner_inference_report.py`, `reports/VF-VERB-REG-04_owner_suggestions.json`, `reports/VF-VERB-REG-04.md`.
- VF-VERB-REG-05: Coverage-threshold fail policy (>=98%) → `tests/vfoundation/test_verb_registry_warn_only.py`.
- VF-VERB-REG-06: Apply owner suggestions (>=70%) (only owner field) → `reports/VF-VERB-REG-06_applied.json`, `reports/VF-VERB-REG-06.md`.

### VF-DICT
- VF-DICT-A-01: Parse-all dictionary YAML + minimal invariants (ops/ttl) → `tests/vfoundation/test_dictionaries_parse_all.py`.
