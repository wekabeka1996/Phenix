# 📄 Semantic Configuration Passport: `apps/reference/domains/neocortex/config/system.yaml` (Full File)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/neocortex_system_passport_gemini_v1.md
> - Scope: Full File of `apps/reference/domains/neocortex/config/system.yaml`
> - Purpose: Capability mapping for the overarching OS-level settings of the Neocortex domain.

Цей короткий паспорт описує базові системні (OS-level) налаштування домену `neocortex`: керування потоками, файлову систему та відтворюваність (Reproducibility).

---

## 1. System Paths (`data_dir`, `checkpoint_dir`)
- **Capability:** Точки зберігання даних домену. `checkpoint_dir` — це каталог, куди Offline Learner буде складати згенеровані файли `neocortex_checkpoint.pt`, і звідки Runtime Actor буде їх "гаряче" завантажувати (Async Hot-Reload) під час роботи.

## 2. Reproducibility (`rng_seed: 42`)
- **Capability:** Детермінізм (Determinism). Встановлює єдиний `seed` для всіх генераторів псевдовипадкових чисел (Numpy, PyTorch, Random).
- **Причинність:** Це критичний інваріант для R&D (як зазначено в Альманасі). Без зафіксованого seed-у кожен перезапуск симулятора або Offline-навчання даватиме різні результати PPO, що зробить неможливим A/B тестування архітектур або доказ покращення нагороди (Reward Improvement).

## 3. Concurrency (`multiprocessing`)
- **`brain_workers: 1`:** 
  - *Capability:* Кількість паралельних процесів (OS Processes), виділених під розрахунки нейромережі.
  - *Sensitivity:* Наразі зафіксовано на 1 (оскільки Neocortex працює в режимі одного потоку на етапі прототипу). Масштабування цього параметра дозволить розпаралелити інференс (Inference) для десятків активів одночасно, обходячи GIL у Python.
- **`queue_maxsize: 1000`:** Розмір буфера обміну (IPC Queue) між `multi_tailer` та `brain_worker`. Якщо `multi_tailer` читає швидше, ніж ШІ встигає думати (Inference Lag), черга захистить систему від витоку пам'яті (Memory Leak), сповільнивши парсер.

## 4. Run Mode (`run_mode`)
- **`run_mode: "backtest"`:**
  - *Capability:* Глобальний прапорець безпеки. Домен примусово встановлено в режим тестування. Жоден рядок коду не ініціює з'єднання з бойовими (live) модулями або брокерами.
