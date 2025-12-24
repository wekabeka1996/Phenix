# 🐎 FIRST PONY SPEC — Індекс Документації

**Мета:** Формалізація range-scalp з режимним FSM на M15 барах з коротким TP/SL для невеликого капіталу.

**Статус:** 🚀 **В РОЗРОБЦІ** | Дата: 3 листопада 2025

---

## 📚 Структура Документації

### **📖 РОЗДІЛ 1: СПЕЦИФІКАЦІЯ & МАТЕМАТИКА**
- [**01_Mathematical_Foundation.md**](./01_Mathematical_Foundation.md)
  - Переклад §1–18 фундаментальної специфіки на проектну мову
  - Позначення, режимна машина, сигнали, сайзинг

### **🏗️ РОЗДІЛ 2: АРХІТЕКТУРА ПРОЕКТУ**
- [**02_Architecture_Mapping.md**](./02_Architecture_Mapping.md)
  - Які домени за що відповідають (RegimeDetector, DecisionMaking, FeatureEng, ExecPos)
  - Потік подій FSM
  - Конфігурація YAML

### **✅ РОЗДІЛ 3: ПОТОЧНИЙ СТАН РЕАЛІЗАЦІЇ**
- [**03_Implementation_Status.md**](./03_Implementation_Status.md)
  - Що вже реалізовано (✅) vs. що бракує (❌)
  - Покрита матриця: специфіка ↔ код

### **🛣️ РОЗДІЛ 4: ДОРОЖНА КАРТА ІНТЕГРАЦІЇ**
- [**04_Integration_Roadmap.md**](./04_Integration_Roadmap.md)
  - Phase-by-phase розвиток з DoD (Definition of Done)
  - Критичні залежності (що першим?)
  - Наслідувальні этапи

### **⚙️ РОЗДІЛ 5: КОНФІГИ & ПАРАМЕТРИ**
- [**05_Configuration_Template.md**](./05_Configuration_Template.md)
  - YAML структура: `models.volatility`, `decision.sizing_modifiers`
  - Параметри режимної детекції (Tension Index)
  - Kelly калькулятор, ризик-обмеження

### **🔍 РОЗДІЛ 6: ВАЛІДАЦІЯ & КРИТЕРІЇ ПРИЙНЯТНОСТІ**
- [**06_Validation_Criteria.md**](./06_Validation_Criteria.md)
  - Як перевіримо §19 критерії (Exp > 0, CVaR ≤ 0.10, MaxDD ≤ 0.20)
  - Walk-forward тестування
  - Safety-стопи & Fail-Closed правила

### **📊 РОЗДІЛ 7: WHY-CHAIN & ПОЯСНЮВАНІСТЬ**
- [**07_Why_Chain_Framework.md**](./07_Why_Chain_Framework.md)
  - Формальна вимога пояснюваності (§16)
  - Вектор ψ(t): які сигнали впливають на рішення
  - Детермінованість & повторюваність

### **🧪 РОЗДІЛ 8: ТЕСТУВАННЯ & СТЕНДИ**
- [**08_Testing_Harness.md**](./08_Testing_Harness.md)
  - Unit-тести для кожного домену
  - Integration тести (FSM потоки)
  - Сценарії (режимні переходи, сайзинг, TP/SL)

---

## 🎯 КЛЮЧОВІ КОМПОНЕНТИ ПЕРВОЇ КОНЯЧКИ

| Компонента | Статус | Файл | Примітка |
|-----------|--------|------|---------|
| **Режимна детекція (FSM)** | ✅ Готова | `regime_detector.py` | 5 режимів + Tension Index |
| **Вхідна сигналізація (OBI/TFI)** | ✅ Готова | `feature_engineering.py` | Динамічні сигнали |
| **Прийняття рішень** | ✅ Готова | `decision_making.py` | Вхід тільки в IdleFlat |
| **Сайзинг (Kelly)** | ✅ Готова | `decision_making.py` | Динамічна Kelly фракція |
| **Виконання позицій** | ✅ Готова | `execution_position/fsm.py` | Open/Manage/Close flows |
| **TP/SL управління** | ✅ Готова | `fsm_manage.py` | Трейл-止loss, часткові exits |
| **Why-Chain логування** | ⚠️ Частково | `decision_making.py` | Потреб. розширення |
| **Safety-Стопи** | ✅ Готова | `decision_making.py` | DD/CVaR/MaxDD гейти |

---

## 📋 РЕКОМЕНДОВАНА ПОСЛІДОВНІСТЬ ЧИТАННЯ

1. **👉 Почніть з:** `01_Mathematical_Foundation.md` — це "розстановщик сцени"
2. **Потім:** `02_Architecture_Mapping.md` — з'ясуйте, де це в коді
3. **Далі:** `03_Implementation_Status.md` — що вже є
4. **Стрибок до:** `04_Integration_Roadmap.md` — що робити далі?
5. **Деталізація:** `05_Configuration_Template.md` + `07_Why_Chain_Framework.md`
6. **Валідація:** `06_Validation_Criteria.md` + `08_Testing_Harness.md`

---

## 🚀 QUICK START

### Мета цієї інтеграції:
**Активувати range-scalp з режимним FSM так, щоб:**
- ✅ Всі 5 режимів детектувалися коректно
- ✅ Вхід відбувався ТІЛЬКИ в IdleFlat
- ✅ Сайзинг адаптувався по режимам (HIGH_VOL → -40%, тощо)
- ✅ TP/SL управління було частковим + трейл
- ✅ Why-chain покривав 100% рішень
- ✅ Safety-стопи блокували over-trading

### Результат:
**Walk-forward validation з:**
```
Exp > 0  ∧  CVaR₀.₉₅ ≤ 0.10  ∧  MaxDD ≤ 0.20  ∧  ρ_reject ≤ 0.08
```

---

## 🔗 ПОСИЛАННЯ НА ФУНДАМЕНТАЛЬНУ СПЕЦИФІКУ

- **Розділ 1–2:** Позначення, дані → `01_Mathematical_Foundation.md` §1–2
- **Розділ 3–5:** FSM, сигнали, вхід → `02_Architecture_Mapping.md`
- **Розділ 6–8:** Сайзинг, TP/SL, режимна інтеграція → `04_Integration_Roadmap.md`
- **Розділ 9–11:** Ризик-обмеження, цільова функція → `06_Validation_Criteria.md`
- **Розділ 16:** Why-chain → `07_Why_Chain_Framework.md`
- **Розділ 17–19:** Інваріанти, параметри, критерії → `05_Configuration_Template.md`

---

## ✨ УМОВНІ ПОЗНАЧЕННЯ

- ✅ — Реалізовано й протестовано
- ⚠️ — Частково реалізовано, потреби розширення
- ❌ — Не реалізовано, потреби розробки
- 📍 — Посилання на розділ специфіки
- 🔗 — Посилання на файл коду
- 🧮 — Математична формула

---

**Статус**: Документація створена 3 листопада 2025
**Автор**: GitHub Copilot (FSMP - First Pony Spec Migration Project)
**Версія**: v1.0 (Walk-Forward Ready)

