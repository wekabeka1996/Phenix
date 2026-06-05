# 📄 Semantic Configuration Passport: `apps/reference/domains/neocortex/config/replay.yaml` (Full File)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/replay_passport_gemini_v1.md
> - Scope: Full File of `apps/reference/domains/neocortex/config/replay.yaml`
> - Purpose: Capability mapping for Multi-Source Log Ingestion and Offline Replay.

Цей паспорт описує налаштування для збору історичних даних (Offline Replay). Він визначає, як саме Neocortex "читає минуле" для свого навчання, збираючи розрізнені логи системи в єдиний причинно-наслідковий таймлайн.

---

## 1. Log Sources (Джерела Правди)
- **`features_dir`:** Каталог з логами фічів (State - $S_t$).
- **`orders_file`:** Журнал ордерів (Actions - $A_t$). Тут зберігаються наміри (Intents) та результати їхнього виконання.
- **`core_log`:** Глобальний лог подій (Rewards - $R_t$). Звідси витягуються дані про закриття позицій та системний стрес.

## 2. Processing Parameters (Контроль Потоку)
- **Capability:** Механізми захисту від блокування (Non-blocking I/O) під час читання гігантських текстових файлів.
- **`batch_size: 100`:** Асинхронний парсер обробляє 100 подій і примусово віддає контроль (yield) головному циклу `asyncio`. Це гарантує, що важке читання логів не "повісить" процес Neocortex.
- **`max_*_lines_per_cycle`:** Жорсткі ліміти на кількість прочитаних рядків за одну ітерацію (напр., `1000` для фічів, `500` для ордерів). Збалансовує споживання ресурсів між різними потоками логів.

## 3. Timestamp Fallback (Вирішення проблеми Causality Leak)
- **`feature_missing_timestamp_policy: "legacy_non_causal_file_offset"`:** 
  - *Capability:* Глобальне перевизначення політики для старих логів.
  - *Причинність (Зв'язок з Red Team Audit):* Раніше старі логи фічів не мали точної мітки часу (`event_ts_ms`). Їх зшивали просто за порядком рядків у файлі (File Offset), що ідеально працювало лише якщо логи були ідеально синхронізовані, але створювало `Causality Leak` на практиці. Цей флаг дозволяє системі парсити старі архіви, використовуючи `legacy_feature_base_ts_ms` як базовий відлік. У нових логах система жорстко вимагає наявності каузального таймстемпу.

## 4. Symbol Filter (`symbols`)
- **Capability:** Перелік активів, які дозволено парсити для навчання. Усі інші активи (наприклад, тестовий `1000PEPEUSDT`) ігноруються під час побудови Replay Buffer, щоб ШІ вчився виключно на ліквідних та репрезентативних монетах.
