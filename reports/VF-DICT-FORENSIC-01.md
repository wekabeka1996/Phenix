# VF-DICT-FORENSIC-01 — Инвентаризация словарей (факты)
Дата: 2026-01-08
## Найденные артефакты (git ls-files)
| Артефакт | Тип | В worktree | Валидность | Примечание |
|---|---:|:---:|:---:|---|
| apps/reference/dictionaries/global_v2_2.yaml | yaml | yes | ok | app global dictionary (intended) |
| apps/reference/domains/account_observer/docs/domain_dict.json | json | yes | ok | domain_dict.json (app domain metadata) |
| apps/reference/domains/decision_making/domain_dict.json | json | yes | ok | domain_dict.json (app domain metadata) |
| apps/reference/domains/feature_engineering/domain_dict.json | json | yes | ok | domain_dict.json (app domain metadata) |
| apps/reference/domains/position_tracking/domain_dict.json | json | yes | ok | domain_dict.json (app domain metadata) |
| apps/reference/domains/regime_detector/docs/domain_dict.json | json | yes | ok | domain_dict.json (app domain metadata) |
| apps/reference/domains/risk_management/domain_dict.json | json | yes | ok | domain_dict.json (app domain metadata) |
| docs/domains/account_balance/dictionaries.yaml | yaml | no | FAIL | yaml:ScannerError; docs domain dictionaries (documentation) |
| docs/domains/account_observer/dictionaries.yaml | yaml | no | FAIL | yaml:ScannerError; docs domain dictionaries (documentation) |
| vfoundation/dictionaries/domains/domain_decision_making.yaml | yaml | yes | ok | domain dictionary (framework) |
| vfoundation/dictionaries/domains/domain_execution_position.yaml | yaml | yes | ok | domain dictionary (framework) |
| vfoundation/dictionaries/domains/domain_feature_engineering.yaml | yaml | yes | ok | domain dictionary (framework) |
| vfoundation/dictionaries/domains/domain_market_data.yaml | yaml | yes | ok | domain dictionary (framework) |
| vfoundation/dictionaries/domains/domain_risk_management.yaml | yaml | yes | ok | domain dictionary (framework) |
| vfoundation/dictionaries/global_v2_2.yaml | yaml | yes | ok | global dictionary duplicate candidate |
| vfoundation/dictionaries/global_v2_2_framework.yaml | yaml | yes | FAIL | has code-fence; yaml:ScannerError; framework global dictionary (intended) |

## Дублирование: глобальные словари
- vfoundation/dictionaries/global_v2_2.yaml и apps/reference/dictionaries/global_v2_2.yaml отличаются (ниже diff).
```diff
--- vfoundation/dictionaries/global_v2_2.yaml
+++ apps/reference/dictionaries/global_v2_2.yaml
@@ -1,3 +1,4 @@
+
 version: 2.2
 ops: [ASK, DEC, CMD, EVT, UPD, ERR]
 stdlib_verbs: [EVAL, OPEN, CLOSE, SCALE, ADJUST, AUTH, READ, WRITE, PING, HEALTH, WHY, ALERT, RECONCILE]
@@ -18,3 +19,4 @@
   max_states_per_domain: 20
 security:
   sign_required_ops: [CMD, DEC]
+
```

## Что я доказал фактами
- В репозитории есть 3 global_v2_2*.yaml, плюс набор domain_* словарей в vfoundation и domain_dict.json в apps/reference/domains.
- vfoundation/dictionaries/global_v2_2_framework.yaml в текущем виде НЕ валидный YAML из-за code-fence.
- docs/domains/*/dictionaries.yaml (в HEAD) не парсятся как YAML (ScannerError) и сейчас отсутствуют в рабочем дереве.

## Что осталось неизвестным
- Является ли невалидность docs/domains/*/dictionaries.yaml следствием порчи/артефакта (надо смотреть историю/коммиты при необходимости).
- Является ли vfoundation/dictionaries/global_v2_2.yaml каноническим или просто дублем (это решается после VF-DICT-FORENSIC-02/03).
