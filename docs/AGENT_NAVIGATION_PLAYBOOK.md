# AGENT NAVIGATION PLAYBOOK (Aurora / vFoundation)

Цей документ — **офіційний контракт навігації** для GitHub Copilot / LLM-агентів у системі Aurora / vFoundation.

**Інваріант:** агент орієнтується по системі **через SSOT-артефакти** (Verb Registry + governance dictionaries), а не через «вільний пошук по коду».

---

## 1) Роль Copilot / агента

Агент у цій системі:

- Діє як **інженер у contract-first системі**.
- **Не “шукає код”** для здогадок.
- **Виконує навігацію через контракти**: спочатку знаходить декларації (SSOT), потім переходить у відповідний домен.
- **Не вигадує** нові `verb`, не вгадує `owner`, не порушує доменні межі.

---

## 2) Точка входу в систему (ОБОВʼЯЗКОВО)

**ЗАВЖДИ** починай із Verb Registry:

- Файл SSOT мови: **apps/reference/dictionaries/verb_registry_v1.yaml**

### Обовʼязковий порядок дій

1. Відкрий **apps/reference/dictionaries/verb_registry_v1.yaml**.
2. Знайди запис для потрібного `verb`.
3. Зчитай поля **до будь-яких переходів у код**:
   - `op`
   - `verb`
   - `owner`
   - `status`
   - `schema`
4. Перейди **ТІЛЬКИ** у домен власника:
   - **apps/reference/domains/<owner>/**

### Заборонено (жорстко)

- ❌ Робити `grep` / пошук по всьому репозиторію, щоб “знайти щось схоже”.
- ❌ Визначати `owner` за назвою файлу/папки/класу.
- ❌ «Стрибати» між доменами без контрактної підстави (без запису в registry).

### Приклад (правильно)

- ✅ Потрібно працювати з `EVT:...` / `CMD:...` / `DEC:...`:
  1) відкрив registry → 2) знайшов `verb` → 3) взяв `owner` → 4) працюєш лише в **apps/reference/domains/<owner>/**.

### Приклад (неправильно)

- ❌ “Я зробив пошук по репо на `:VERB` і знайшов щось схоже.”

---

## 3) Правила роботи з `verb` (інваріанти)

### 3.1 Заборони

- ❌ **НЕ створювати новий `verb`**, не перевіривши його відсутність у **apps/reference/dictionaries/verb_registry_v1.yaml**.
- ❌ **НЕ змінювати `owner`**, якщо він уже заданий у registry.
- ❌ **НЕ використовувати `verb` зі статусом `deprecated`.**
- ❌ **НЕ вгадувати `owner`.** Якщо `owner: unknown` — агент **ЗУПИНЯЄТЬСЯ** і виконує процедуру додавання/уточнення (див. розділ 4).

### 3.2 Дозволено тільки за контрактом

- ✅ Працювати з `verb` **лише після** того, як знайдено відповідний запис у registry.

### 3.3 Якщо `verb` відсутній у registry

- ✅ Спочатку **додати `verb` у registry**.
- ✅ Дочекатися CI / review-процесу (див. розділ 4).
- ✅ Лише потім писати/змінювати runtime-код.

---

## 4) Як агент додає новий `verb` (playbook)

Цей playbook — єдиний дозволений шлях додавання нової мовної сутності.

### Кроки

1. Відкрий **apps/reference/dictionaries/verb_registry_v1.yaml**.
2. Додай новий запис із полями:
   - `op`: (наприклад `EVT`, `CMD`, `DEC`, `UPD`)
   - `verb`: (новий токен)
   - `owner`: (існуючий домен із **apps/reference/domains/<owner>/**)
   - `status: experimental`
   - `schema: null`
3. Запусти CI/перевірки локально (мінімальний набір):
   - `pytest -q tests/vfoundation/test_verb_registry_warn_only.py`
   - `pytest -q tests/vfoundation/test_verb_owner_inference_report.py`
4. Переконайся, що:
   - drift-gate відпрацював очікувано (warn-only або fail залежно від поточного порогу покриття),
   - registry є єдиним джерелом істини для цього `verb`.
5. Лише після цього переходь до коду в **apps/reference/domains/<owner>/** і реалізуй логіку.

### Приклад (правильно)

- ✅ “Мені потрібен новий `CMD:FOO_BAR`. Я додав його в registry як `experimental`, вказав owner, прогнав gate, і тільки потім додав handler у домені owner.”

### Приклад (неправильно)

- ❌ “Я додав `CMD:FOO_BAR` у коді, а registry не чіпав, бо CI не впав.”

---

## 5) Як агент орієнтується в політиках (governance dictionaries)

**Governance dictionaries — це політики і рамки**, не runtime-конфіг.

### Де дивитися політики

- Global governance:
  - vfoundation/dictionaries/global_v2_2_framework.yaml
  - apps/reference/dictionaries/global_v2_2.yaml
- Domain governance:
  - vfoundation/dictionaries/domains/domain_*.yaml

### Що саме агент повинен там перевіряти

- **TTL / expiry правила** (допустимі діапазони, профілі TTL).
- **Security / signing** (які `op` потребують підпису/валідації).
- **Ops policy** (дозволені `op`/категорії, інваріанти контракту).

### Інваріанти

- ✅ Governance YAML використовується як **контракт/рамка**, а не як «підказка для реалізації».
- ❌ Governance YAML **НЕ є** runtime-логікою та **НЕ є** runtime-конфігом.

---

## 6) Антипатерни (заборонено)

Агент **НЕ має права** робити наступне:

- ❌ “Я знайшов схожий код і скопіював.”
- ❌ “Я додав новий `verb` напряму в код.”
- ❌ “Я не оновлював registry, бо CI не впав.”
- ❌ “Я не знаю owner, але думаю, що це risk/portfolio/execution.”
- ❌ “Я просто зробив `grep -R` по репо і вибрав перший збіг.”

---

## 7) Мінімальний протокол роботи агента (шпаргалка)

1. **Registry-first:** знайди `verb` у **apps/reference/dictionaries/verb_registry_v1.yaml**.
2. **Owner-boundary:** працюй тільки в **apps/reference/domains/<owner>/**.
3. **No guessing:** немає запису або `owner: unknown` → **STOP** і оновлення registry.
4. **Policy-aware:** звір TTL/security/ops у governance dictionaries.
5. **Тільки після цього — код.**
