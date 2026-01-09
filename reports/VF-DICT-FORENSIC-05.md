# VF-DICT-FORENSIC-05 — Варианты эволюции (без имплементации)
Дата: 2026-01-08

## Контекст (что известно из VF-DICT-FORENSIC-01..04)
- Есть global dictionary и domain dictionaries как governance-артефакты (SSOT).
- В текущем коде vfoundation нет runtime-loader’а этих YAML; enforcement (TTL/signature/op) реализован в коде.
- `vfoundation/dictionaries/global_v2_2_framework.yaml` сейчас невалидный YAML из-за code-fence — это ок пока он не парсится.
- Реальный event-space в Aurora представлен набором `OP:VERB` токенов, но global v2.2 не содержит реестр всех VERB.

## Option A — Docs-only + CI (минимальный риск)
- Суть: оставить словари как SSOT/документацию, но добавить CI-проверки консистентности и валидности формата.
- Плюсы: нулевой риск для рантайма; фиксирует drift; улучшает качество артефактов.
- Минусы: runtime всё ещё не fail-closed по verb; гарантии только через CI.
- Порядок внедрения (additive-only): (1) валидировать YAML/JSON; (2) CI lint: сравнение OP allowlist, TTL ranges, schema presence; (3) отчёт о drift.

## Option B — Tooling-first (loader для CLI/линтинга/миграции)
- Суть: написать загрузчик словарей только для `vfound` (analyze/migrate/lint), рантайм не трогать.
- Плюсы: практическая польза (графы, проверки, миграции); изоляция риска.
- Минусы: остаётся разрыв runtime vs SSOT; нужно договориться о каноничности файлов и формате.
- Порядок внедрения: (1) нормализовать формат (убрать code-fence, решить где framework/app); (2) добавить `vfound dict validate` (парсинг+schema); (3) `vfound analyze imports` читает domain_dict/domain_*.yaml.

## Option C — Runtime-enforced (наибольшая чистота, наибольший риск)
- Суть: рантайм-router/fsm-core начинает применять словарь: неизвестные verb → DENY; TTL/security/limits берутся из словаря.
- Плюсы: настоящий fail-closed по контракту; единое SSOT.
- Минусы: высокий риск поломок при неполном словаре; нужен полноценный реестр всех VERB + стратегия миграции/переходных режимов.
- Порядок внедрения (additive-only): (1) собрать полный реестр VERB; (2) режимы: warn-only → shadow-deny (emit ERR) → hard-deny; (3) метрики/алерты на drift.

## Открытые вопросы (нужно решить перед любым вариантом)
- Какой артефакт является каноничным: `vfoundation/dictionaries/global_v2_2.yaml` vs framework+app split?
- Где хранится полный реестр `OP:VERB`: в global dictionary, в domain dictionaries, или в schemas/?
- Как обрабатывать legacy verb и временные эксперименты (feature flags, shadow-only)?
