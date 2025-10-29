# 🏗️ ПЛАН #1 — Архітектурна Переробка

**RID**: `PLAN-1-ARCHITECTURE-READINESS`  
**Дата Старту**: 27 жовтня 2025  
**Статус**: 🟢 **ГОТОВО ДО ЗАПУСКУ**  
**Тривалість**: 5-7 днів  
**Мета**: Стабілізація архітектури та готовність до mainnet

---

## 📋 ЧИМ ЗАНІМАЄТЬСЯ План #1

### Етап 1: Аналіз Архітектури (1 день)
- [ ] Огляд всіх 6 доменів (market_data, feature_eng, risk, decision, execution, audit)
- [ ] Визначення критичних узвичаїв та залежностей
- [ ] Карта даних потоків (data flow diagram)
- [ ] Документація архітектури v1.0

### Етап 2: Config & Режими (2 дні)
- [ ] Структурувати domain-level режими (live/testnet/hybrid)
- [ ] Розширити FSMCore Message з mode полями
- [ ] Оновити ConfigLoader для режимів на рівні домену
- [ ] Синхронізація тестів з новою конфігурацією

### Етап 3: API Синхронізація (1-2 дні)
- [ ] ExecPosFSM: додати flow методи або оновити тести
- [ ] Feature Engineering: синхронізувати ім'я атрибутів
- [ ] Risk Management: перевірити API контракти
- [ ] Оновити контракти в dictionaries/

### Етап 4: Тестування & Валідація (1-2 дні)
- [ ] Запустити повний тест suite (644/644 target)
- [ ] Проанализувати failures та виправити
- [ ] Інтеграційне тестування 3+ доменів
- [ ]准готність до mainnet

---

## 📊 ВХІДНІ ДАНІ З План #2

### Успішні Фіксації (5 з 6)
✅ env vars override — YAML → ${VAR}  
✅ market_data mock — BinanceAdapter REST  
✅ FSM mock — FSMCore event bus  
✅ async testing — aiohttp context managers  
✅ import sys — базові залежності  

### Статистика Тестів
- 87/671 PASSED (базові фіксації працюють)
- 4 FAILED (старі тести, потребують рефакторингу)
- 1 ERROR (не критичне)

### Архітектурні Знахідки
- BinanceAdapter використовує REST (не WebSocket)
- FSMCore — event bus для міжdomain комунікацій
- Config підтримує env var templates
- MarketData — REST polling замість streaming

---

## 🎯 КРИТИЧНІ ОБЛАСТІ План #1

### 1. Domain-Level Mode Configuration (HIGH PRIORITY)
**Проблема**: Система розроблена на глобальний режим, потрібні режими на рівні домену  
**Рішення**: Структурувати config з `domain_configuration` для кожного домену  
**Тести Impacted**: ~15 тестів у config_loader та domain setup

### 2. FSM Message Contract Extension (HIGH PRIORITY)
**Проблема**: Message не містить `mode` поля  
**Рішення**: Розширити контракт з `mode` та `mode_contract`  
**Тести Impacted**: ~10 тестів у FSM контрактах

### 3. ExecPosFSM API Alignment (MEDIUM PRIORITY)
**Проблема**: 11 тестів очікують методи які не існують  
**Рішення**: Додати flow методи або оновити на verb-routing  
**Тести Impacted**: 11 тестів у test_execution_position_fsm.py

### 4. Feature Engineering API Sync (MEDIUM PRIORITY)
**Проблема**: Ім'я атрибутів не синхронізовано  
**Рішення**: Синхронізувати self.last_tick_data та інші  
**Тести Impacted**: 8 тестів у test_feature_engineering.py

### 5. Config Keys Validation (MEDIUM PRIORITY)
**Проблема**: Тестові config не мають `decision` ключ  
**Рішення**: Додати в тестові fixtures  
**Тести Impacted**: 6 тестів у test_fail_closed_behavior.py

---

## 📈 ОЧІКУВАНІ РЕЗУЛЬТАТИ

**Поточний стан**: 87/671 PASSED  
**Цільовий стан**: 600+/671 PASSED  
**Критичні фіксації**: 5/5 з План #2 ✅  
**Нові фіксації План #1**: ~20-25 тестів

### Успіх Критерій
- [ ] 600+ тестів PASSED
- [ ] 0 critical failures
- [ ] Всі 6 доменів готові
- [ ] Архітектура документована
- [ ] Готовність до mainnet

---

## 🗓️ ГРАФІК План #1

| День | Завдання | Результат |
|------|----------|-----------|
| День 1 | Архітектурний аналіз | Data flow diagram, archit docs |
| День 2-3 | Config & Mode структурування | domain-level режими working |
| День 4 | API синхронізація | ExecPosFSM, Feature Eng OK |
| День 5-6 | Тестування & валідація | 600+ PASSED |
| День 7 | Фінальна готовність | Mainnet ready |

---

## 🚀 ЗАПУСК План #1

### Команда для Старту
```bash
# 1. Архітектурний аналіз
python scripts/analyze_architecture.py

# 2. Запустити базові тести
pytest tests/domains/ -v

# 3. Перевірити failures
pytest tests/domains/ -v --tb=short | grep FAILED

# 4. Слідувати інструкціям для кожного failure
```

### Ключові Команди
```bash
# Запустити тести
pytest --ignore=tests/test_acl_stub_smoke.py -v

# Запустити з покриттям
pytest --ignore=tests/test_acl_stub_smoke.py --cov=apps --cov-report=term-missing

# Запустити конкретний домен
pytest tests/domains/test_execution_position_fsm.py -v
```

---

## 📚 ДОКУМЕНТАЦІЯ План #1

### Підготовка
1. ✅ План #2 завершено
2. ✅ Архітектурні знахідки зібрані
3. ✅ Критичні області визначені
4. 📋 Готово до детальної реалізації

### Документи які будуть створені
- [ ] ARCHITECTURE_ANALYSIS.md
- [ ] DOMAIN_CONFIG_DESIGN.md
- [ ] FSM_MESSAGE_EXTENSION.md
- [ ] API_SYNC_PLAN.md
- [ ] PLAN_1_PROGRESS_REPORT.md

---

## ⚠️ КРИТИЧНІ БІЛЬ ТОЧКИ

1. **Mode Configuration Complexity**
   - Глобальний vs domain-level режими
   - Потребує careful design

2. **FSM Contract Changes**
   - Message structure розширення
   - Потребує migration path

3. **API Divergence**
   - Кілька тестів очікує стари API
   - Потребує systematic migration

4. **Integration Points**
   - 3+ домени взаємодіють
   - Потребує E2E тестування

---

## ✨ ПЛАН ДІЙ

### Фаза 1: Розумення (День 1)
1. Прочитати цей документ повністю
2. Подивитись JOURNAL_Plan2_Completion.md
3. Запустити базові тести та посмотрети failures
4. Створити data flow diagram

### Фаза 2: Планування (День 1-2)
1. Визначити критичні зміни
2. Спланувати migration path
3. Підготувати PR scheme
4. Готово до запуску

### Фаза 3: Реалізація (День 2-7)
1. Слідувати графіку План #1
2. Виправити критичні області
3. Запустити тести для кожної фіксації
4. Документувати progress

---

## 🎯 УСПІХ КРИТЕРІЙ

✅ План #1 вважається завершеною коли:
- [ ] 600+/671 тестів PASSED
- [ ] Всі 5 критичних областей вирішено
- [ ] Архітектура документована
- [ ] 0 critical failures
- [ ] Система готова до mainnet

---

## 📞 КОНТАКТИ & ДОПОМОГА

Якщо під час План #1 виникнуть питання:
1. Перевірте JOURNAL_Plan2_Completion.md для архітектурних знахідок
2. Посмотрите в PLAN_2_PROGRESS_REPORT.md для техніки
3. Запустіть конкретний тест з `-vvs` для деталей

---

**RID**: `PLAN-1-ARCHITECTURE-READINESS` 🚀

**СИСТЕМА ГОТОВА ДО План #1!** ✅
